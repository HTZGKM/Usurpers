from restaurant.db.database import begin_read, begin_write, get_connection
from .common import ServiceError, positive_int


def get_waiting_items():
    return _queue_items("waiting", "q.priority DESC, COALESCE(q.estimated_ready_at, q.created_at)")


def get_cooking_items():
    return _queue_items("cooking", "q.started_at")


def get_ready_items():
    return _queue_items("ready", "q.completed_at")


def get_active_items():
    return _queue_items(None, """
        CASE WHEN q.status='waiting' THEN q.priority ELSE 0 END DESC,
        CASE q.status WHEN 'waiting' THEN COALESCE(q.estimated_ready_at, q.created_at)
            WHEN 'cooking' THEN q.started_at ELSE q.completed_at END
    """)


def _queue_items(status, sort):
    condition = "q.status=?" if status else "q.status IN ('waiting','cooking','ready')"
    params = (status,) if status else ()
    with get_connection() as db:
        rows = db.execute(f"""
            SELECT q.queue_id,q.order_id,q.order_item_id,q.dish_id,q.quantity,q.status,
                   q.created_at,q.started_at,q.completed_at,q.estimated_ready_at,
                   i.note,i.status AS item_status,o.table_id,o.order_type,o.version AS order_version
            FROM kitchen_queue q
            JOIN order_items i USING (order_item_id)
            JOIN orders o ON o.order_id=q.order_id
            WHERE {condition}
            ORDER BY {sort}, q.queue_id
        """, params)
        return [dict(row) for row in rows]


def get_order_details(order_id):
    oid = positive_int(order_id, "order_id")
    with get_connection() as db:
        begin_read(db)
        order = db.execute(
            "SELECT order_id,table_id,order_type,status,version FROM orders WHERE order_id=?", (oid,)
        ).fetchone()
        if not order:
            raise ServiceError("Order not found.", 404, "order_id")
        items = db.execute("""SELECT i.order_item_id,i.dish_id,d.dish_name,i.quantity,i.note,i.status,
                q.status AS kitchen_status
            FROM order_items i JOIN dishes d USING(dish_id)
            LEFT JOIN kitchen_queue q USING(order_item_id)
            WHERE i.order_id=? ORDER BY i.order_item_id""", (oid,))
        return {**dict(order), "items": [dict(item) for item in items]}


def _transition(item_id, expected, target, expected_version=None):
    iid=positive_int(item_id,"order_item_id")
    with get_connection() as db:
        begin_write(db)
        if expected_version is not None:
            order = db.execute("""SELECT o.version FROM orders o JOIN order_items i USING(order_id)
                                  WHERE i.order_item_id=?""", (iid,)).fetchone()
            if order and order["version"] != expected_version:
                raise ServiceError("The order changed. Check the updated dish and quantity before starting.",
                                   409, code="ORDER_CHANGED")
        cur=db.execute("""UPDATE order_items SET status=? WHERE order_item_id=? AND status=?
            AND EXISTS (SELECT 1 FROM kitchen_queue WHERE order_item_id=? AND status=?)""",
            (target,iid,expected,iid,expected))
        if cur.rowcount:
            if target == "cooking": db.execute("UPDATE kitchen_queue SET status=?,started_at=CURRENT_TIMESTAMP WHERE order_item_id=? AND status=?",(target,iid,expected))
            elif target in ("ready","served"): db.execute("UPDATE kitchen_queue SET status=?,completed_at=CURRENT_TIMESTAMP WHERE order_item_id=? AND status IN ('cooking','ready')",(target,iid))
            if target == "served":
                from .order_service import refresh_order_status
                parent=db.execute("SELECT order_id FROM order_items WHERE order_item_id=?",(iid,)).fetchone()
                refresh_order_status(db,parent[0])
            return {"order_item_id":iid,"status":target}
        row=db.execute("SELECT status FROM order_items WHERE order_item_id=?",(iid,)).fetchone()
        if not row: raise ServiceError("订单菜品不存在。",404,"order_item_id","NOT_FOUND")
        if row["status"] == expected:
            raise ServiceError("菜品还没有进入该厨房队列。",409,"status","STATE_CONFLICT")
        raise ServiceError(f"不能从 {row['status']} 转为 {target}。",409,"status","STATE_CONFLICT")


def start_item(order_item_id, expected_version=None):
    return _transition(order_item_id, "waiting", "cooking", expected_version)
def finish_item(order_item_id): return _transition(order_item_id,"cooking","ready")
def serve_item(order_item_id): return _transition(order_item_id,"ready","served")
def check_order_complete(order_id):
    oid=positive_int(order_id,"order_id")
    with get_connection() as db:
        if not db.execute("SELECT 1 FROM orders WHERE order_id=?",(oid,)).fetchone(): raise ServiceError("订单不存在。",404)
        return not db.execute("SELECT 1 FROM order_items WHERE order_id=? AND status NOT IN ('served','cancelled')",(oid,)).fetchone()
