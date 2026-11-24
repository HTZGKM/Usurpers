from restaurant.db.database import get_connection
from .common import ServiceError, phone_number, positive_int, required_text, valid_date


# 兼容旧的 time_slot_id 整数传入，映射为时间段字符串
TIME_SLOT_MAP = {
    1: "11:00-14:00",
    2: "17:00-19:00",
    3: "19:00-21:00",
    "1": "11:00-14:00",
    "2": "17:00-19:00",
    "3": "19:00-21:00",
}


def _normalize_time_slot(value):
    """把传入的 time_slot 统一为字符串。整数 ID 走映射，字符串直接用。"""
    if value is None:
        raise ServiceError("用餐时段不能为空。", field="time_slot")
    if value in TIME_SLOT_MAP:
        return TIME_SLOT_MAP[value]
    return str(value)


def find_available_tables(booking_date, time_slot, party_size, exclude_booking_id=None):
    booking_date = valid_date(booking_date)
    slot = _normalize_time_slot(time_slot)
    size = positive_int(party_size, "party_size")
    with get_connection() as db:
        query = """SELECT t.table_id,t.capacity FROM dining_tables t WHERE t.capacity>=?
          AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.table_id=t.table_id AND b.booking_date=?
            AND b.time_slot=? AND b.status='booked' AND (? IS NULL OR b.booking_id<>?))
          AND NOT EXISTS (SELECT 1 FROM dining_sessions s WHERE s.table_id=t.table_id AND s.status IN ('waiting','seated'))
          ORDER BY t.capacity,t.table_id"""
        return [dict(r) for r in db.execute(query, (size, booking_date, slot, exclude_booking_id, exclude_booking_id))]


def _resolve_table(db, date, slot, size, table_id, exclude_booking_id=None):
    """校验并返回最终分配的桌号。指定了 table_id 则校验容量和可用性，否则自动分配。"""
    if table_id is not None:
        table = db.execute("SELECT capacity FROM dining_tables WHERE table_id=?", (table_id,)).fetchone()
        if not table:
            raise ServiceError("餐桌不存在。", 404, "table_id", "NOT_FOUND")
        if table["capacity"] < size:
            raise ServiceError("该桌容量不足。", 409, "table_id", "CAPACITY_INSUFFICIENT")
        occupied = db.execute(
            "SELECT 1 FROM bookings WHERE table_id=? AND booking_date=? AND time_slot=? AND status='booked'"
            + (" AND booking_id<>?" if exclude_booking_id else ""),
            (table_id, date, slot, exclude_booking_id) if exclude_booking_id else (table_id, date, slot),
        ).fetchone()
        if occupied:
            raise ServiceError("该桌此时段已被预订。", 409, "table_id", "TABLE_UNAVAILABLE")
        return table_id
    available = find_available_tables(date, slot, size, exclude_booking_id)
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
        db.execute("BEGIN IMMEDIATE")
        table_id_final = _resolve_table(db, date, slot, size, tid)
        cur = db.execute("INSERT INTO bookings(contact_name,phone_number,booking_date,time_slot,party_size,table_id,customer_phone) VALUES(?,?,?,?,?,?,?)", (name, phone, date, slot, size, table_id_final, customer_phone))
        return {"booking_id": cur.lastrowid, "table_id": table_id_final, "status": "booked"}


def update_booking(booking_id, booking_date, time_slot, party_size, customer_phone=None, table_id=None):
    bid = positive_int(booking_id, "booking_id")
    date = valid_date(booking_date)
    slot = _normalize_time_slot(time_slot)
    size = positive_int(party_size, "party_size")
    tid = positive_int(table_id, "table_id") if table_id is not None else None
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT status,customer_phone FROM bookings WHERE booking_id=?", (bid,)).fetchone()
        if not current: raise ServiceError("预订不存在。", 404)
        if customer_phone and current["customer_phone"] != customer_phone: raise ServiceError("无权修改此预订。",403,code="FORBIDDEN")
        if current["status"] != "booked": raise ServiceError("当前预订状态不可修改。", 409)
        table_id_final = _resolve_table(db, date, slot, size, tid, bid)
        db.execute("UPDATE bookings SET booking_date=?,time_slot=?,party_size=?,table_id=? WHERE booking_id=?", (date, slot, size, table_id_final, bid))
        return {"booking_id": bid, "table_id": table_id_final, "status": "booked"}


def cancel_booking(booking_id, customer_phone=None):
    bid = positive_int(booking_id, "booking_id")
    with get_connection() as db:
        query="UPDATE bookings SET status='cancelled',table_id=NULL WHERE booking_id=? AND status='booked'"
        args=[bid]
        if customer_phone: query += " AND customer_phone=?"; args.append(customer_phone)
        cur = db.execute(query,args)
        if not cur.rowcount: raise ServiceError("预订不存在或已到店/取消。", 409)
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
          CASE WHEN s.visit_id IS NOT NULL THEN 'occupied' WHEN b.booking_id IS NOT NULL THEN 'reserved' ELSE 'available' END status
          FROM dining_tables t LEFT JOIN dining_sessions s ON s.table_id=t.table_id AND s.status IN ('waiting','seated')
          LEFT JOIN bookings b ON b.table_id=t.table_id AND b.booking_date=? AND b.time_slot=? AND b.status='booked'
          ORDER BY t.table_id""",(date,slot))]
