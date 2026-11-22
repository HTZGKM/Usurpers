from restaurant.db.database import get_connection
from .common import ServiceError, phone_number, positive_int, required_text, valid_date


def find_available_tables(booking_date, time_slot_id, party_size, exclude_booking_id=None):
    booking_date = valid_date(booking_date)
    slot = positive_int(time_slot_id, "time_slot_id")
    size = positive_int(party_size, "party_size")
    with get_connection() as db:
        if not db.execute("SELECT 1 FROM time_slots WHERE time_slot_id=?", (slot,)).fetchone():
            raise ServiceError("用餐时段不存在。", field="time_slot_id")
        query = """SELECT t.table_id,t.capacity FROM dining_tables t WHERE t.capacity>=?
          AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.table_id=t.table_id AND b.booking_date=?
            AND b.time_slot_id=? AND b.status='booked' AND (? IS NULL OR b.booking_id<>?))
          AND NOT EXISTS (SELECT 1 FROM dining_sessions s WHERE s.table_id=t.table_id AND s.status IN ('waiting','seated'))
          ORDER BY t.capacity,t.table_id"""
        return [dict(r) for r in db.execute(query, (size, booking_date, slot, exclude_booking_id, exclude_booking_id))]


def create_booking(contact_name, phone, booking_date, time_slot_id, party_size, customer_phone=None):
    name = required_text(contact_name, "contact_name", limit=100)
    phone = phone_number(phone)
    date = valid_date(booking_date)
    slot = positive_int(time_slot_id, "time_slot_id")
    size = positive_int(party_size, "party_size")
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        available = find_available_tables(date, slot, size)
        if not available:
            raise ServiceError("该时段没有容量合适的空桌。", 409)
        table_id = available[0]["table_id"]
        cur = db.execute("INSERT INTO bookings(contact_name,phone_number,booking_date,time_slot_id,party_size,table_id,customer_phone) VALUES(?,?,?,?,?,?,?)", (name, phone, date, slot, size, table_id, customer_phone))
        return {"booking_id": cur.lastrowid, "table_id": table_id, "status": "booked"}


def update_booking(booking_id, booking_date, time_slot_id, party_size, customer_phone=None):
    bid = positive_int(booking_id, "booking_id")
    date = valid_date(booking_date)
    slot = positive_int(time_slot_id, "time_slot_id")
    size = positive_int(party_size, "party_size")
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT status,customer_phone FROM bookings WHERE booking_id=?", (bid,)).fetchone()
        if not current: raise ServiceError("预订不存在。", 404)
        if customer_phone and current["customer_phone"] != customer_phone: raise ServiceError("无权修改此预订。",403,code="FORBIDDEN")
        if current["status"] != "booked": raise ServiceError("当前预订状态不可修改。", 409)
        tables = find_available_tables(date, slot, size, bid)
        if not tables: raise ServiceError("新时段没有容量合适的空桌，原预订已保留。", 409)
        db.execute("UPDATE bookings SET booking_date=?,time_slot_id=?,party_size=?,table_id=? WHERE booking_id=?", (date, slot, size, tables[0]["table_id"], bid))
        return {"booking_id": bid, "table_id": tables[0]["table_id"], "status": "booked"}


def cancel_booking(booking_id, customer_phone=None):
    bid = positive_int(booking_id, "booking_id")
    with get_connection() as db:
        query="UPDATE bookings SET status='cancelled',table_id=NULL WHERE booking_id=? AND status='booked'"
        args=[bid]
        if customer_phone: query += " AND customer_phone=?"; args.append(customer_phone)
        cur = db.execute(query,args)
        if not cur.rowcount: raise ServiceError("预订不存在或已到店/取消。", 409)
        return {"booking_id": bid, "status": "cancelled"}


def get_all_bookings(booking_date=None, time_slot_id=None, phone=None):
    filters, args = [], []
    if booking_date is not None: filters.append("booking_date=?"); args.append(valid_date(booking_date))
    if time_slot_id is not None: filters.append("time_slot_id=?"); args.append(positive_int(time_slot_id,"time_slot_id"))
    if phone is not None: filters.append("phone_number=?"); args.append(phone_number(phone))
    sql="SELECT * FROM bookings" + (" WHERE "+" AND ".join(filters) if filters else "") + " ORDER BY booking_date,time_slot_id,booking_id"
    with get_connection() as db: return [dict(r) for r in db.execute(sql,args)]


def get_customer_bookings(customer_phone):
    with get_connection() as db:
        return [dict(r) for r in db.execute("SELECT * FROM bookings WHERE customer_phone=? ORDER BY booking_date,time_slot_id",(customer_phone,))]


def get_table_occupancy(booking_date, time_slot_id):
    date=valid_date(booking_date); slot=positive_int(time_slot_id,"time_slot_id")
    with get_connection() as db:
        return [dict(r) for r in db.execute("""SELECT t.table_id,t.capacity,
          CASE WHEN s.visit_id IS NOT NULL THEN 'occupied' WHEN b.booking_id IS NOT NULL THEN 'reserved' ELSE 'available' END status
          FROM dining_tables t LEFT JOIN dining_sessions s ON s.table_id=t.table_id AND s.status IN ('waiting','seated')
          LEFT JOIN bookings b ON b.table_id=t.table_id AND b.booking_date=? AND b.time_slot_id=? AND b.status='booked'
          ORDER BY t.table_id""",(date,slot))]
