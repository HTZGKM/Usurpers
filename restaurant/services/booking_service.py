from datetime import datetime, timezone

from restaurant.business_time import MEAL_SLOTS, current_table_window, utc_clock
from restaurant.db.database import begin_write, get_connection, insert_id
from .common import ServiceError, phone_number, positive_int, required_text, valid_date


TIME_SLOT_MAP = {str(index): slot for index, slot in enumerate(MEAL_SLOTS, 1)}


def _normalize_time_slot(value):
    raw = str(value).strip()
    slot = TIME_SLOT_MAP.get(raw, raw)
    if slot not in MEAL_SLOTS:
        raise ServiceError("请选择有效的用餐时段。", field="time_slot")
    return slot


def table_has_booking(db, table_id, date, slot, exclude_booking_id=None):
    return db.execute("""SELECT 1 FROM bookings
        WHERE table_id=? AND booking_date=? AND time_slot=? AND status='booked'
        AND (CAST(? AS INTEGER) IS NULL OR booking_id<>?)""",
        (table_id, date, slot, exclude_booking_id, exclude_booking_id)).fetchone() is not None


def table_has_visit(db, table_id):
    return db.execute("""SELECT 1 FROM dining_sessions
        WHERE table_id=? AND status IN ('waiting','seated')""", (table_id,)).fetchone() is not None


def table_has_call(db, table_id):
    return db.execute("""SELECT 1 FROM waiting_queue
        WHERE called_table_id=? AND status='called' AND called_at>=?""",
        (table_id, utc_clock(10))).fetchone() is not None


def _available_tables(db, date, slot, size, exclude_booking_id=None):
    live = (date, slot) == current_table_window()
    rows = db.execute("""SELECT t.table_id,t.capacity FROM dining_tables t
        WHERE t.capacity>=? AND NOT EXISTS (
            SELECT 1 FROM bookings b WHERE b.table_id=t.table_id AND b.booking_date=?
            AND b.time_slot=? AND b.status='booked' AND (CAST(? AS INTEGER) IS NULL OR b.booking_id<>?))
        AND (NOT ? OR (NOT EXISTS (
            SELECT 1 FROM dining_sessions s WHERE s.table_id=t.table_id AND s.status IN ('waiting','seated'))
        AND NOT EXISTS (SELECT 1 FROM waiting_queue q WHERE q.called_table_id=t.table_id
            AND q.status='called' AND q.called_at>=?)))
        ORDER BY t.capacity,t.table_id""", (size, date, slot, exclude_booking_id, exclude_booking_id, live, utc_clock(10)))
    return [dict(row) for row in rows]


def find_available_tables(booking_date, time_slot, party_size, exclude_booking_id=None):
    booking_date = valid_date(booking_date)
    slot = _normalize_time_slot(time_slot)
    size = positive_int(party_size, "party_size")
    with get_connection() as db:
        return _available_tables(db, booking_date, slot, size, exclude_booking_id)


def _resolve_table(db, date, slot, size, table_id, exclude_booking_id=None):
    """校验并返回最终分配的桌号。指定了 table_id 则校验容量和可用性，否则自动分配。"""
    available = _available_tables(db, date, slot, size, exclude_booking_id)
    if table_id is not None:
        table = db.execute("SELECT capacity FROM dining_tables WHERE table_id=?", (table_id,)).fetchone()
        if not table:
            raise ServiceError("餐桌不存在。", 404, "table_id", "NOT_FOUND")
        if table["capacity"] < size:
            raise ServiceError("该桌容量不足。", 409, "table_id", "CAPACITY_INSUFFICIENT")
        if not any(table["table_id"] == table_id for table in available):
            raise ServiceError("该桌此时段不可用。", 409, "table_id", "TABLE_UNAVAILABLE")
        return table_id
    if not available:
        raise ServiceError("该时段没有容量合适的空桌。", 409)
    return available[0]["table_id"]


def create_booking(contact_name, phone, booking_date, time_slot, party_size, customer_phone=None, table_id=None):
    name = required_text(contact_name, "contact_name", limit=100)
    phone = phone_number(phone)
    date = valid_date(booking_date)
    slot = _normalize_time_slot(time_slot)
    size = positive_int(party_size, "party_size")
    tid = positive_int(table_id, "table_id") if table_id is not None else None
    with get_connection() as db:
        begin_write(db)
        table_id_final = _resolve_table(db, date, slot, size, tid)
        booking_id = insert_id(db, """INSERT INTO bookings
            (contact_name,phone_number,booking_date,time_slot,party_size,table_id,customer_phone)
            VALUES(?,?,?,?,?,?,?)""", (name, phone, date, slot, size, table_id_final, customer_phone), "booking_id")
        return {"booking_id": booking_id, "table_id": table_id_final, "status": "booked"}


def update_booking(booking_id, booking_date, time_slot, party_size, customer_phone=None, table_id=None):
    bid = positive_int(booking_id, "booking_id")
    date = valid_date(booking_date)
    slot = _normalize_time_slot(time_slot)
    size = positive_int(party_size, "party_size")
    tid = positive_int(table_id, "table_id") if table_id is not None else None
    with get_connection() as db:
        begin_write(db)
        current = db.execute("SELECT status,customer_phone,booking_date,time_slot FROM bookings WHERE booking_id=?", (bid,)).fetchone()
        if not current: raise ServiceError("预订不存在。", 404)
        if customer_phone and current["customer_phone"] != customer_phone: raise ServiceError("无权修改此预订。",403,code="FORBIDDEN")
        if current["status"] != "booked": raise ServiceError("当前预订状态不可修改。", 409)
        table_id_final = _resolve_table(db, date, slot, size, tid, bid)
        db.execute("UPDATE bookings SET booking_date=?,time_slot=?,party_size=?,table_id=? WHERE booking_id=?", (date, slot, size, table_id_final, bid))
        db.execute("""UPDATE orders SET table_id=?
            WHERE booking_id=? AND order_type='preorder' AND visit_id IS NULL AND status='active'""", (table_id_final, bid))
        if (date, slot) != (current["booking_date"], current["time_slot"]):
            old_start = datetime.fromisoformat(current["booking_date"] + " " + current["time_slot"][:5] + ":00+08:00")
            new_start = datetime.fromisoformat(date + " " + slot[:5] + ":00+08:00")
            delta = new_start - old_start
            lines = db.execute("""SELECT i.order_item_id, i.estimated_ready_at
                FROM order_items i JOIN orders o USING (order_id)
                WHERE i.status='waiting' AND o.booking_id=? AND o.order_type='preorder'
                AND o.visit_id IS NULL AND o.status='active'""", (bid,)).fetchall()
            changes = []
            for line in lines:
                ready_at = line["estimated_ready_at"]
                if ready_at:
                    updated = datetime.fromisoformat(ready_at) + delta
                    if updated.tzinfo is not None:
                        updated = updated.astimezone(timezone.utc).replace(tzinfo=None)
                else:
                    updated = new_start.astimezone(timezone.utc).replace(tzinfo=None)
                changes.append((updated.isoformat(sep=" ", timespec="seconds"), line["order_item_id"]))
            db.executemany("UPDATE order_items SET estimated_ready_at=? WHERE order_item_id=?", changes)
        return {"booking_id": bid, "table_id": table_id_final, "status": "booked"}


def cancel_booking(booking_id, customer_phone=None):
    bid = positive_int(booking_id, "booking_id")
    with get_connection() as db:
        begin_write(db)
        query="UPDATE bookings SET status='cancelled',table_id=NULL WHERE booking_id=? AND status='booked'"
        args=[bid]
        if customer_phone: query += " AND customer_phone=?"; args.append(customer_phone)
        cur = db.execute(query,args)
        if not cur.rowcount: raise ServiceError("预订不存在或已到店/取消。", 409)
        if db.execute("""SELECT 1 FROM orders JOIN order_items USING(order_id)
            WHERE booking_id=? AND order_type='preorder' AND orders.status<>'cancelled'
            AND (payment_status='paid' OR order_items.status IN ('cooking','ready','served'))""", (bid,)).fetchone():
            raise ServiceError("关联预点单已制作或结账，不能取消预订。",409,code="STATE_CONFLICT")
        preorder_filter = "SELECT order_id FROM orders WHERE booking_id=? AND order_type='preorder' AND status='active'"
        db.execute("UPDATE order_items SET status='cancelled' WHERE order_id IN (" + preorder_filter + ") AND status='waiting'", (bid,))
        db.execute("UPDATE kitchen_queue SET status='cancelled',completed_at=CURRENT_TIMESTAMP WHERE order_id IN (" + preorder_filter + ") AND status='waiting'", (bid,))
        db.execute("UPDATE orders SET status='cancelled' WHERE order_id IN (" + preorder_filter + ")", (bid,))
        return {"booking_id": bid, "status": "cancelled"}


def get_all_bookings(booking_date=None, time_slot=None, phone=None):
    filters, args = [], []
    if booking_date is not None: filters.append("booking_date=?"); args.append(valid_date(booking_date))
    if time_slot is not None: filters.append("time_slot=?"); args.append(_normalize_time_slot(time_slot))
    if phone is not None: filters.append("phone_number=?"); args.append(phone_number(phone))
    sql="SELECT *, substr(time_slot,1,5) AS starts_at, substr(time_slot,7,5) AS ends_at FROM bookings" + (" WHERE "+" AND ".join(filters) if filters else "") + " ORDER BY booking_date,time_slot,booking_id"
    with get_connection() as db: return [dict(r) for r in db.execute(sql,args)]


def get_customer_bookings(customer_phone):
    with get_connection() as db:
        return [dict(r) for r in db.execute("SELECT *, substr(time_slot,1,5) AS starts_at, substr(time_slot,7,5) AS ends_at FROM bookings WHERE customer_phone=? ORDER BY booking_date,time_slot",(customer_phone,))]


def get_table_occupancy(booking_date, time_slot):
    date=valid_date(booking_date); slot=_normalize_time_slot(time_slot)
    with get_connection() as db:
        return [dict(r) for r in db.execute("""SELECT t.table_id,t.capacity,
          CASE WHEN s.visit_id IS NOT NULL THEN 'occupied' WHEN b.booking_id IS NOT NULL OR EXISTS (
              SELECT 1 FROM waiting_queue q WHERE q.called_table_id=t.table_id AND q.status='called'
              AND q.called_at>=?) THEN 'reserved' ELSE 'available' END status
          FROM dining_tables t LEFT JOIN dining_sessions s ON s.table_id=t.table_id AND s.status IN ('waiting','seated')
          LEFT JOIN bookings b ON b.table_id=t.table_id AND b.booking_date=? AND b.time_slot=? AND b.status='booked'
          ORDER BY t.table_id""",(utc_clock(10),date,slot))]
