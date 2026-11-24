from datetime import datetime, timedelta, timezone

from restaurant.db.database import get_connection
from .common import ServiceError, phone_number, positive_int, required_text


RESTAURANT_TIME = timezone(timedelta(hours=8))


def _current_time_slot():
    """根据当前北京时间推算用餐时段字符串。非营业时段返回 None。"""
    now = datetime.now(RESTAURANT_TIME)
    hour = now.hour
    if 11 <= hour < 14:
        return "11:00-14:00"
    if 17 <= hour < 19:
        return "17:00-19:00"
    if 19 <= hour < 21:
        return "19:00-21:00"
    return None


def register_arrival(booking_id, table_id=None):
    bid=positive_int(booking_id,"booking_id")
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        booking=db.execute("SELECT * FROM bookings WHERE booking_id=?",(bid,)).fetchone()
        if not booking: raise ServiceError("预订不存在。",404,"booking_id","NOT_FOUND")
        if booking["status"]!="booked": raise ServiceError("该预订已签到或已取消。",409,"status","STATE_CONFLICT")
        tid=positive_int(table_id,"table_id") if table_id is not None else booking["table_id"]
        if tid is None: raise ServiceError("签到前必须分配餐桌。",400,"table_id")
        table=db.execute("SELECT capacity FROM dining_tables WHERE table_id=?",(tid,)).fetchone()
        if not table: raise ServiceError("餐桌不存在。",404,"table_id","NOT_FOUND")
        if table["capacity"]<booking["party_size"]: raise ServiceError("餐桌容量不足。",409,"table_id","RESOURCE_CONFLICT")
        if db.execute("SELECT 1 FROM dining_sessions WHERE table_id=? AND status IN ('waiting','seated')",(tid,)).fetchone(): raise ServiceError("餐桌当前已占用。",409,"table_id","RESOURCE_CONFLICT")
        cur=db.execute("INSERT INTO dining_sessions(booking_id,customer_phone,contact_name,phone_number,party_size,table_id,status) VALUES(?,?,?,?,?,?,'seated')",(bid,booking["customer_phone"],booking["contact_name"],booking["phone_number"],booking["party_size"],tid))
        db.execute("UPDATE bookings SET status='arrived',table_id=? WHERE booking_id=? AND status='booked'",(tid,bid))
        return {"visit_id":cur.lastrowid,"table_id":tid,"status":"seated"}


def register_walk_in(party_size, table_id, contact_name=None, phone=None):
    size=positive_int(party_size,"party_size"); tid=positive_int(table_id,"table_id")
    name=required_text(contact_name,"contact_name",limit=100) if contact_name is not None else None
    phone=phone_number(phone) if phone else None
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        table=db.execute("SELECT capacity FROM dining_tables WHERE table_id=?",(tid,)).fetchone()
        if not table: raise ServiceError("餐桌不存在。",404,"table_id","NOT_FOUND")
        if table["capacity"]<size: raise ServiceError("餐桌容量不足。",409,"table_id","RESOURCE_CONFLICT")
        if db.execute("SELECT 1 FROM dining_sessions WHERE table_id=? AND status IN ('waiting','seated')",(tid,)).fetchone(): raise ServiceError("餐桌当前已占用。",409,"table_id","RESOURCE_CONFLICT")
        # 检查该桌当前日期/时段是否已被预订
        slot = _current_time_slot()
        if slot:
            booked = db.execute(
                "SELECT 1 FROM bookings WHERE table_id=? AND booking_date=date('now','+8 hours') AND time_slot=? AND status='booked'",
                (tid, slot),
            ).fetchone()
            if booked:
                raise ServiceError("该桌当前时段已被预订。", 409, "table_id", "RESOURCE_CONFLICT")
        cur=db.execute("INSERT INTO dining_sessions(contact_name,phone_number,party_size,table_id,status) VALUES(?,?,?,?,'seated')",(name,phone,size,tid))
        return {"visit_id":cur.lastrowid,"table_id":tid,"status":"seated"}


def close_dining_session(visit_id):
    vid=positive_int(visit_id,"visit_id")
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT status FROM dining_sessions WHERE visit_id=?",(vid,)).fetchone()
        if not row: raise ServiceError("到店记录不存在。",404)
        if row["status"]!="seated": raise ServiceError("该到店记录已结束。",409)
        unpaid=db.execute("SELECT 1 FROM orders WHERE visit_id=? AND status<>'cancelled' AND payment_status<>'paid'",(vid,)).fetchone()
        if unpaid: raise ServiceError("仍有未结清订单，不能释放餐桌。",409)
        table_id=db.execute("SELECT table_id FROM dining_sessions WHERE visit_id=?",(vid,)).fetchone()["table_id"]
        db.execute("UPDATE dining_sessions SET status='closed',closed_at=CURRENT_TIMESTAMP WHERE visit_id=? AND status='seated'",(vid,))
    from .queue_manager import QueueManager
    called=QueueManager.call_next(table_id) if table_id else None
    return {"visit_id":vid,"status":"closed","next_queue":called}


def get_dining_sessions():
    with get_connection() as db: return [dict(r) for r in db.execute("SELECT * FROM dining_sessions ORDER BY arrived_at DESC")]


def get_active_customer_visit(customer_phone):
    with get_connection() as db:
        row=db.execute("SELECT visit_id FROM dining_sessions WHERE customer_phone=? AND status='seated' ORDER BY arrived_at DESC LIMIT 1",(customer_phone,)).fetchone()
        if not row: raise ServiceError("没有进行中的堂食记录。",404,code="NOT_FOUND")
        return row["visit_id"]


def assign_table(visit_id, table_id):
    vid=positive_int(visit_id,"visit_id"); tid=positive_int(table_id,"table_id")
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        visit=db.execute("SELECT party_size FROM dining_sessions WHERE visit_id=? AND status='waiting'",(vid,)).fetchone()
        table=db.execute("SELECT capacity FROM dining_tables WHERE table_id=?",(tid,)).fetchone()
        if not visit: raise ServiceError("等待中的到店记录不存在。",404)
        if not table: raise ServiceError("餐桌不存在。",404)
        if table["capacity"]<visit["party_size"]: raise ServiceError("餐桌容量不足。",409)
        if db.execute("SELECT 1 FROM dining_sessions WHERE table_id=? AND status IN ('waiting','seated')",(tid,)).fetchone(): raise ServiceError("餐桌当前已占用。",409)
        db.execute("UPDATE dining_sessions SET table_id=?,status='seated' WHERE visit_id=? AND status='waiting'",(tid,vid))
        return {"visit_id":vid,"table_id":tid,"status":"seated"}
