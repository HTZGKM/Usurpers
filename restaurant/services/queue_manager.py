from restaurant.business_time import utc_clock
from restaurant.db.database import begin_write, get_connection, insert_id, using_postgres
from .common import ServiceError, date_time, phone_number, positive_int, required_text
from .dining_service import require_seatable_table


class QueueManager:
    @staticmethod
    def available_tables():
        with get_connection() as db:
            tables = []
            for row in db.execute("SELECT table_id FROM dining_tables ORDER BY table_id"):
                table_id = row["table_id"]
                try:
                    capacity = require_seatable_table(db, table_id)
                except ServiceError as error:
                    if error.status_code != 409:
                        raise
                    continue
                tables.append({"table_id": table_id, "capacity": capacity})
            return tables

    @staticmethod
    def join_waitlist(party_size, contact_name=None, phone=None, customer_phone=None, table_type=None):
        size=positive_int(party_size,"party_size")
        phone=phone_number(phone) if phone else None
        contact_name=required_text(contact_name,"contact_name",limit=100) if contact_name is not None else None
        table_type=positive_int(table_type,"table_type") if table_type is not None else None
        with get_connection() as db:
            begin_write(db)
            QueueManager.expire_calls(db)
            if db.execute("SELECT 1 FROM waiting_queue WHERE (phone_number=? OR customer_phone=?) AND status IN ('waiting','called')",(phone,customer_phone)).fetchone():
                raise ServiceError("该顾客已在等位队列中。",409,"phone_number","DUPLICATE")
            seats = max(size, table_type or 0)
            if not db.execute("SELECT 1 FROM dining_tables WHERE capacity>=?", (seats,)).fetchone():
                raise ServiceError("没有能容纳该人数的餐桌。", 409, "party_size", "CAPACITY_INSUFFICIENT")
            position=db.execute("SELECT COALESCE(MAX(queue_position),0)+1 FROM waiting_queue WHERE status IN ('waiting','called')").fetchone()[0]
            queue_id = insert_id(db, """INSERT INTO waiting_queue
                (contact_name,phone_number,customer_phone,party_size,table_type,queue_position)
                VALUES(?,?,?,?,?,?)""", (contact_name,phone,customer_phone,size,table_type,position), "queue_id")
            return {"queue_id":queue_id,"queue_position":position,"status":"waiting"}

    @staticmethod
    def list_waiting():
        QueueManager.expire_called()
        with get_connection() as db: return [dict(r) for r in db.execute("SELECT * FROM waiting_queue WHERE status IN ('waiting','called') ORDER BY queue_position")]

    @staticmethod
    def get_customer_entry(customer_phone):
        QueueManager.expire_called()
        with get_connection() as db:
            row=db.execute("""SELECT q.*, (SELECT COUNT(*) FROM waiting_queue ahead
                WHERE ahead.status IN ('waiting','called') AND ahead.queue_position<q.queue_position) AS parties_ahead
                FROM waiting_queue q WHERE q.customer_phone=? AND q.status IN ('waiting','called')
                ORDER BY q.queue_id DESC LIMIT 1""", (customer_phone,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def expire_called(timeout_minutes=10):
        with get_connection() as db:
            return QueueManager.expire_calls(db, timeout_minutes)

    @staticmethod
    def expire_calls(db, timeout_minutes=10):
        return db.execute("UPDATE waiting_queue SET status='expired' WHERE status='called' AND called_at < ?",
                          (utc_clock(int(timeout_minutes)),)).rowcount

    @staticmethod
    def enqueue_due_preorders(now=None):
        """Promote accepted preorder lines only when their requested prep time arrives AND the customer is seated."""
        with get_connection() as db:
            begin_write(db)
            ready_at = "l.estimated_ready_at" if using_postgres() else "datetime(l.estimated_ready_at)"
            sql=f"""SELECT l.* FROM order_items l JOIN orders h USING(order_id)
                   JOIN dining_sessions ds ON ds.visit_id = h.visit_id
                   WHERE h.order_type='preorder' AND h.status='active' AND l.status='waiting' AND l.estimated_ready_at IS NOT NULL
                   AND {ready_at}<=?
                   AND ds.status='seated'
                   AND NOT EXISTS(SELECT 1 FROM kitchen_queue q WHERE q.order_item_id=l.order_item_id)"""
            due=db.execute(sql,(date_time(str(now)) if now is not None else utc_clock(),)).fetchall()
            for line in due:
                db.execute("INSERT INTO kitchen_queue(order_id,order_item_id,dish_id,quantity,estimated_ready_at) VALUES(?,?,?,?,?)",(line["order_id"],line["order_item_id"],line["dish_id"],line["quantity"],line["estimated_ready_at"]))
            return len(due)

    @staticmethod
    def call_next(table_id):
        tid=positive_int(table_id,"table_id")
        with get_connection() as db:
            begin_write(db)
            return QueueManager.call_for_available_table(db, tid)

    @staticmethod
    def call_for_available_table(db, table_id, *, skip_conflict=False):
        QueueManager.expire_calls(db)
        try:
            capacity = require_seatable_table(db, table_id)
        except ServiceError as error:
            if skip_conflict and error.status_code == 409:
                return None
            raise
        while True:
            nextrow = db.execute("""SELECT queue_id FROM waiting_queue WHERE status='waiting' AND party_size<=?
                AND (table_type IS NULL OR table_type<=?) ORDER BY queue_position LIMIT 1""", (capacity, capacity)).fetchone()
            if not nextrow:
                return None
            queue_id = nextrow["queue_id"]
            called = db.execute("""UPDATE waiting_queue SET status='called',called_at=?,called_table_id=?
                WHERE queue_id=? AND status='waiting' RETURNING queue_id""", (utc_clock(), table_id, queue_id)).fetchone()
            if called:
                return {"queue_id":queue_id,"table_id":table_id,"status":"called"}

    @staticmethod
    def seat(queue_id, table_id):
        qid=positive_int(queue_id,"queue_id"); tid=positive_int(table_id,"table_id")
        with get_connection() as db:
            begin_write(db)
            lock = " FOR UPDATE" if using_postgres() else ""
            item=db.execute("SELECT * FROM waiting_queue WHERE queue_id=? AND status='called'" + lock,(qid,)).fetchone()
            if not item:
                raise ServiceError("This waitlist ticket is no longer ready to seat.", 409, code="WAITLIST_CHANGED")
            if item["called_table_id"] not in (None, tid):
                raise ServiceError("请使用叫号时分配的餐桌。",409,"table_id","TABLE_UNAVAILABLE")
            require_seatable_table(db, tid, max(item["party_size"], item["table_type"] or 0), allow_call=item["called_table_id"] == tid)
            seated = db.execute("""UPDATE waiting_queue SET status='seated'
                WHERE queue_id=? AND status='called' AND called_at>=? RETURNING queue_id""",
                (qid, utc_clock(10))).fetchone()
            if not seated:
                raise ServiceError("This waitlist ticket is no longer ready to seat.", 409, code="WAITLIST_CHANGED")
            visit_id = insert_id(db, """INSERT INTO dining_sessions
                (contact_name,phone_number,customer_phone,party_size,table_id,status) VALUES(?,?,?,?,?,'seated')""",
                (item["contact_name"],item["phone_number"],item["customer_phone"],item["party_size"],tid), "visit_id")
            return {"queue_id":qid,"visit_id":visit_id,"table_id":tid,"status":"seated"}

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
            begin_write(db)
            ready_at = "l.estimated_ready_at" if using_postgres() else "datetime(l.estimated_ready_at)"
            line=db.execute(f"""SELECT l.*,h.order_type,s.status AS visit_status,
                {ready_at}<=CURRENT_TIMESTAMP AS is_due
                FROM order_items l JOIN orders h USING(order_id)
                LEFT JOIN dining_sessions s USING(visit_id) WHERE l.order_item_id=?""",(iid,)).fetchone()
            if not line: raise ServiceError("订单菜品不存在。",404)
            if line["status"]!='waiting': raise ServiceError("只有待制作菜品可以加入厨房队列。",409)
            if line["order_type"] == "preorder" and (line["visit_status"] != "seated" or not line["is_due"]):
                raise ServiceError("预点菜品须等顾客入座且到达制作时间。",409,code="STATE_CONFLICT")
            queue_id = insert_id(db, """INSERT INTO kitchen_queue
                (order_id,order_item_id,dish_id,quantity,priority,estimated_ready_at) VALUES(?,?,?,?,?,?)
                ON CONFLICT(order_item_id) DO NOTHING""",
                (line["order_id"],iid,line["dish_id"],line["quantity"],priority,estimated_ready_at), "queue_id")
            return {"queue_id":queue_id,"order_item_id":iid,"enqueued":queue_id is not None}
