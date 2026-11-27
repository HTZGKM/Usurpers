from restaurant.business_time import current_table_window
from restaurant.db.database import begin_write, get_connection, insert_id
from .booking_service import booking_conflict, table_has_booking, table_has_call, table_has_visit
from .common import ServiceError, phone_number, positive_int, required_text


def require_seatable_table(db, table_id, party_size=0, booking=None, *, allow_call=False, window=None):
    table = db.execute("SELECT capacity FROM dining_tables WHERE table_id=?", (table_id,)).fetchone()
    if not table:
        raise ServiceError("餐桌不存在。", 404, "table_id", "NOT_FOUND")
    if table["capacity"] < party_size:
        raise ServiceError("餐桌容量不足。", 409, "table_id", "CAPACITY_INSUFFICIENT")
    if table_has_visit(db, table_id) or (not allow_call and table_has_call(db, table_id)):
        raise ServiceError("餐桌当前已占用。", 409, "table_id", "TABLE_UNAVAILABLE")
    date, slot = window or current_table_window()
    if booking and table_has_booking(db, table_id, booking["booking_date"], booking["time_slot"], booking["booking_id"]):
        raise ServiceError("该桌在预订时段已被其他顾客预订。", 409, "table_id", "TABLE_UNAVAILABLE")
    if slot and table_has_booking(db, table_id, date, slot, booking["booking_id"] if booking else None):
        raise ServiceError("该桌当前时段已被预订。", 409, "table_id", "TABLE_UNAVAILABLE")
    return table["capacity"]


def register_arrival(booking_id, table_id=None, *, change_table=False, expected_version=None):
    bid=positive_int(booking_id,"booking_id")
    if table_id is not None and not change_table:
        raise ServiceError("Refresh the page and use Change table to seat this guest at another table.",
                           409, code="CHECK_IN_REFRESH_REQUIRED")
    if change_table and expected_version is None:
        raise booking_conflict()
    with get_connection() as db:
        begin_write(db, legacy_allocation=True)
        booking=db.execute("SELECT * FROM bookings WHERE booking_id=?",(bid,)).fetchone()
        if not booking: raise ServiceError("预订不存在。",404,"booking_id","NOT_FOUND")
        if booking["status"]!="booked": raise ServiceError("该预订已签到或已取消。",409,"status","STATE_CONFLICT")
        if change_table and booking["version"] != positive_int(expected_version, "expected_version"):
            raise booking_conflict()
        window = current_table_window()
        if booking["booking_date"] != window[0]:
            raise ServiceError("Check in is only available on the reservation date.", 409,
                               "booking_date", "CHECK_IN_DATE_MISMATCH")
        tid=positive_int(table_id,"table_id") if change_table else booking["table_id"]
        if tid is None: raise ServiceError("签到前必须分配餐桌。",400,"table_id")
        require_seatable_table(db, tid, booking["party_size"], booking, window=window)
        arrived = db.execute("""UPDATE bookings SET status='arrived',table_id=?,version=version+1
            WHERE booking_id=? AND status='booked' AND version=? RETURNING booking_id""",
            (tid, bid, booking["version"])).fetchone()
        if not arrived:
            raise booking_conflict()
        visit_id = insert_id(db, """INSERT INTO dining_sessions
            (booking_id,customer_phone,contact_name,phone_number,party_size,table_id,status)
            VALUES(?,?,?,?,?,?,'seated')""",
            (bid,booking["customer_phone"],booking["contact_name"],booking["phone_number"],booking["party_size"],tid), "visit_id")
        db.execute("""UPDATE orders SET visit_id=?,table_id=?
            WHERE booking_id=? AND order_type='preorder' AND visit_id IS NULL AND status<>'cancelled'""",
            (visit_id, tid, bid))
        return {"visit_id":visit_id,"table_id":tid,"status":"seated"}


def register_walk_in(party_size, table_id, contact_name=None, phone=None):
    size=positive_int(party_size,"party_size"); tid=positive_int(table_id,"table_id")
    name=required_text(contact_name,"contact_name",limit=100) if contact_name is not None else None
    phone=phone_number(phone) if phone else None
    with get_connection() as db:
        begin_write(db, legacy_allocation=True)
        require_seatable_table(db, tid, size)
        visit_id = insert_id(db, "INSERT INTO dining_sessions(contact_name,phone_number,party_size,table_id,status) VALUES(?,?,?,?,'seated')",
                             (name,phone,size,tid), "visit_id")
        return {"visit_id":visit_id,"table_id":tid,"status":"seated"}


def close_dining_session(visit_id):
    from .queue_manager import QueueManager

    vid=positive_int(visit_id,"visit_id")
    with get_connection() as db:
        begin_write(db, legacy_allocation=True)
        row=db.execute("SELECT status,table_id FROM dining_sessions WHERE visit_id=?",(vid,)).fetchone()
        if not row: raise ServiceError("到店记录不存在。",404)
        if row["status"]!="seated": raise ServiceError("该到店记录已结束。",409)
        unpaid=db.execute("SELECT 1 FROM orders WHERE visit_id=? AND status<>'cancelled' AND payment_status<>'paid'",(vid,)).fetchone()
        if unpaid: raise ServiceError("仍有未结清订单，不能释放餐桌。",409)
        unfinished = db.execute("""SELECT 1 FROM orders JOIN order_items USING(order_id)
            WHERE visit_id=? AND (order_items.status NOT IN ('served','cancelled') OR order_items.supply_issue IS NOT NULL) LIMIT 1""", (vid,)).fetchone()
        if unfinished:
            raise ServiceError("仍有未上菜的菜品，不能释放餐桌。", 409, code="VISIT_UNFINISHED_ITEMS")
        db.execute("UPDATE dining_sessions SET status='closed',closed_at=CURRENT_TIMESTAMP WHERE visit_id=? AND status='seated'",(vid,))
        called = QueueManager.call_for_available_table(db, row["table_id"], skip_conflict=True) if row["table_id"] else None
    return {"visit_id":vid,"status":"closed","next_queue":called}


def get_dining_sessions():
    with get_connection() as db: return [dict(r) for r in db.execute("SELECT * FROM dining_sessions ORDER BY arrived_at DESC")]


def get_frontdesk_visits():
    with get_connection() as db:
        rows = db.execute("""
            SELECT v.visit_id, v.booking_id, v.table_id, v.contact_name, v.party_size, v.status,
                   COUNT(DISTINCT CASE WHEN EXISTS (
                       SELECT 1 FROM order_items ri WHERE ri.order_id=o.order_id AND ri.status='ready'
                   ) AND NOT EXISTS (
                       SELECT 1 FROM order_items ui WHERE ui.order_id=o.order_id
                         AND (ui.status NOT IN ('ready','served','cancelled') OR ui.supply_issue IS NOT NULL)
                   ) THEN o.order_id END) AS ready_count,
                   COUNT(DISTINCT CASE WHEN o.payment_status='unpaid' THEN o.order_id END) AS unpaid_count
            FROM dining_sessions v
            LEFT JOIN orders o ON o.visit_id=v.visit_id AND o.status<>'cancelled'
            LEFT JOIN order_items i ON i.order_id=o.order_id
            WHERE v.status IN ('waiting', 'seated')
            GROUP BY v.visit_id
            ORDER BY v.arrived_at DESC, v.visit_id DESC
        """)
        return [dict(row) for row in rows]


def get_active_customer_visit(customer_phone):
    with get_connection() as db:
        row=db.execute("SELECT visit_id FROM dining_sessions WHERE customer_phone=? AND status='seated' ORDER BY arrived_at DESC LIMIT 1",(customer_phone,)).fetchone()
        if not row: raise ServiceError("没有进行中的堂食记录。",404,code="NOT_FOUND")
        return row["visit_id"]


def assign_table(visit_id, table_id):
    vid=positive_int(visit_id,"visit_id"); tid=positive_int(table_id,"table_id")
    with get_connection() as db:
        begin_write(db, legacy_allocation=True)
        visit=db.execute("SELECT party_size FROM dining_sessions WHERE visit_id=? AND status='waiting'",(vid,)).fetchone()
        if not visit: raise ServiceError("等待中的到店记录不存在。",404)
        require_seatable_table(db, tid, visit["party_size"])
        db.execute("UPDATE dining_sessions SET table_id=?,status='seated' WHERE visit_id=? AND status='waiting'",(tid,vid))
        return {"visit_id":vid,"table_id":tid,"status":"seated"}
