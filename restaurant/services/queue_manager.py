from restaurant.db.database import get_connection
from .common import ServiceError, date_time, phone_number, positive_int, required_text


class QueueManager:
    @staticmethod
    def join_waitlist(party_size, contact_name=None, phone=None, customer_phone=None, table_type=None):
        size=positive_int(party_size,"party_size")
        phone=phone_number(phone) if phone else None
        contact_name=required_text(contact_name,"contact_name",limit=100) if contact_name is not None else None
        table_type=positive_int(table_type,"table_type") if table_type is not None else None
        with get_connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if phone and db.execute("SELECT 1 FROM waiting_queue WHERE phone_number=? AND status IN ('waiting','called')",(phone,)).fetchone():
                raise ServiceError("该顾客已在等位队列中。",409,"phone_number","DUPLICATE")
            position=db.execute("SELECT COALESCE(MAX(queue_position),0)+1 FROM waiting_queue WHERE status IN ('waiting','called')").fetchone()[0]
            cur=db.execute("INSERT INTO waiting_queue(contact_name,phone_number,customer_phone,party_size,table_type,queue_position) VALUES(?,?,?,?,?,?)",(contact_name,phone,customer_phone,size,table_type,position))
            return {"queue_id":cur.lastrowid,"queue_position":position,"status":"waiting"}

    @staticmethod
    def list_waiting():
        QueueManager.expire_called()
        with get_connection() as db: return [dict(r) for r in db.execute("SELECT * FROM waiting_queue WHERE status IN ('waiting','called') ORDER BY queue_position")]

    @staticmethod
    def get_customer_entry(customer_phone):
        with get_connection() as db:
            row=db.execute("SELECT * FROM waiting_queue WHERE customer_phone=? AND status IN ('waiting','called') ORDER BY queue_id DESC LIMIT 1",(customer_phone,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def expire_called(timeout_minutes=10):
        with get_connection() as db:
            cur=db.execute("UPDATE waiting_queue SET status='expired' WHERE status='called' AND called_at < datetime('now',?)",(f"-{int(timeout_minutes)} minutes",))
            return cur.rowcount

    @staticmethod
    def enqueue_due_preorders(now=None):
        """Promote accepted preorder lines only when their requested prep time arrives AND the customer is seated."""
        with get_connection() as db:
            db.execute("BEGIN IMMEDIATE")
            sql="""SELECT l.* FROM order_items l JOIN orders h USING(order_id)
                   JOIN dining_sessions ds ON ds.booking_id = h.booking_id
                   WHERE h.order_type='preorder' AND l.status='waiting' AND l.estimated_ready_at IS NOT NULL
                   AND l.estimated_ready_at<=COALESCE(?,CURRENT_TIMESTAMP)
                   AND ds.status='seated'
                   AND NOT EXISTS(SELECT 1 FROM kitchen_queue q WHERE q.order_item_id=l.order_item_id)"""
            due=db.execute(sql,(now,)).fetchall()
            for line in due:
                db.execute("INSERT INTO kitchen_queue(order_id,order_item_id,dish_id,quantity,estimated_ready_at) VALUES(?,?,?,?,?)",(line["order_id"],line["order_item_id"],line["dish_id"],line["quantity"],line["estimated_ready_at"]))
            return len(due)

    @staticmethod
    def call_next(table_id):
        tid=positive_int(table_id,"table_id")
        with get_connection() as db:
            db.execute("BEGIN IMMEDIATE")
            table=db.execute("SELECT capacity FROM dining_tables WHERE table_id=?",(tid,)).fetchone()
            if not table: raise ServiceError("餐桌不存在。",404,"table_id","NOT_FOUND")
            occupied=db.execute("SELECT 1 FROM dining_sessions WHERE table_id=? AND status IN ('waiting','seated')",(tid,)).fetchone()
            booked=db.execute("SELECT 1 FROM bookings WHERE table_id=? AND status='booked' AND booking_date=date('now')",(tid,)).fetchone()
            if occupied or booked: raise ServiceError("餐桌当前不可分配。",409,"table_id","RESOURCE_CONFLICT")
            nextrow=db.execute("SELECT * FROM waiting_queue WHERE status='waiting' AND party_size<=? AND (table_type IS NULL OR table_type<=?) ORDER BY queue_position LIMIT 1",(table["capacity"],table["capacity"])).fetchone()
            if not nextrow: return None
            db.execute("UPDATE waiting_queue SET status='called',called_at=CURRENT_TIMESTAMP WHERE queue_id=? AND status='waiting'",(nextrow["queue_id"],))
            return {"queue_id":nextrow["queue_id"],"table_id":tid,"status":"called"}

    @staticmethod
    def seat(queue_id, table_id):
        qid=positive_int(queue_id,"queue_id"); tid=positive_int(table_id,"table_id")
        with get_connection() as db:
            db.execute("BEGIN IMMEDIATE")
            item=db.execute("SELECT * FROM waiting_queue WHERE queue_id=? AND status='called'",(qid,)).fetchone()
            if not item: raise ServiceError("等位记录不存在或未叫号。",409)
            table=db.execute("SELECT capacity FROM dining_tables WHERE table_id=?",(tid,)).fetchone()
            if not table or table["capacity"]<item["party_size"]: raise ServiceError("餐桌不存在或容量不足。",409)
            if db.execute("SELECT 1 FROM dining_sessions WHERE table_id=? AND status IN ('waiting','seated')",(tid,)).fetchone(): raise ServiceError("餐桌已被分配。",409)
            cur=db.execute("INSERT INTO dining_sessions(contact_name,phone_number,customer_phone,party_size,table_id,status) VALUES(?,?,?,?,?,'seated')",(item["contact_name"],item["phone_number"],item["customer_phone"],item["party_size"],tid))
            db.execute("UPDATE waiting_queue SET status='seated' WHERE queue_id=? AND status='called'",(qid,))
            return {"queue_id":qid,"visit_id":cur.lastrowid,"table_id":tid,"status":"seated"}

    @staticmethod
    def cancel(queue_id, customer_phone=None):
        qid=positive_int(queue_id,"queue_id")
        with get_connection() as db:
            sql="UPDATE waiting_queue SET status='cancelled' WHERE queue_id=? AND status IN ('waiting','called')"; args=[qid]
            if customer_phone: sql += " AND customer_phone=?"; args.append(customer_phone)
            cur=db.execute(sql,args)
            if not cur.rowcount: raise ServiceError("等位记录不存在或已结束。",404)
            return {"queue_id":qid,"status":"cancelled"}

    @staticmethod
    def enqueue_order_item(order_item_id, priority=0, estimated_ready_at=None):
        iid=positive_int(order_item_id,"order_item_id")
        if isinstance(priority,bool) or not isinstance(priority,int) or priority<0: raise ServiceError("priority 必须是非负整数。",field="priority")
        estimated_ready_at=date_time(estimated_ready_at) if estimated_ready_at is not None else None
        with get_connection() as db:
            db.execute("BEGIN IMMEDIATE")
            line=db.execute("SELECT * FROM order_items WHERE order_item_id=?",(iid,)).fetchone()
            if not line: raise ServiceError("订单菜品不存在。",404)
            if line["status"]!='waiting': raise ServiceError("只有待制作菜品可以加入厨房队列。",409)
            cur=db.execute("INSERT OR IGNORE INTO kitchen_queue(order_id,order_item_id,dish_id,quantity,priority,estimated_ready_at) VALUES(?,?,?,?,?,?)",(line["order_id"],iid,line["dish_id"],line["quantity"],priority,estimated_ready_at))
            return {"queue_id":cur.lastrowid,"order_item_id":iid,"enqueued":bool(cur.rowcount)}
