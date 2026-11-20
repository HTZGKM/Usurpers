from restaurant.db.database import get_connection
from .common import ServiceError, positive_int
from .inventory_service import consume_for_order_line


def get_waiting_items():
    from .queue_manager import QueueManager
    from .remake_service import list_remakes
    QueueManager.enqueue_due_preorders()
    with get_connection() as db: items=[dict(r) for r in db.execute("SELECT q.*,l.note,l.status item_status,'order' task_type FROM kitchen_queue q JOIN order_lines l USING(order_item_id) WHERE q.status='waiting' ORDER BY q.priority DESC,COALESCE(q.estimated_ready_at,q.created_at),q.queue_id")]
    items.extend({**r,"task_type":"remake"} for r in list_remakes("waiting"))
    return items


def get_cooking_items():
    from .remake_service import list_remakes
    with get_connection() as db: items=[dict(r) for r in db.execute("SELECT q.*,l.note,'order' task_type FROM kitchen_queue q JOIN order_lines l USING(order_item_id) WHERE q.status='cooking' ORDER BY q.started_at,q.queue_id")]
    items.extend({**r,"task_type":"remake"} for r in list_remakes("cooking"))
    return items


def get_ready_items():
    from .remake_service import list_remakes
    with get_connection() as db: items=[dict(r) for r in db.execute("SELECT q.*,l.note,'order' task_type FROM kitchen_queue q JOIN order_lines l USING(order_item_id) WHERE q.status='ready' ORDER BY q.completed_at,q.queue_id")]
    items.extend({**r,"task_type":"remake"} for r in list_remakes("ready"))
    return items


def _transition(item_id, expected, target):
    iid=positive_int(item_id,"order_item_id")
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        cur=db.execute("UPDATE order_lines SET status=? WHERE order_item_id=? AND status=?",(target,iid,expected))
        if cur.rowcount:
            if target == "cooking": consume_for_order_line(db,iid)
            now="CURRENT_TIMESTAMP" if target in ("cooking","ready") else "NULL"
            if target == "cooking": db.execute("UPDATE kitchen_queue SET status=?,started_at=CURRENT_TIMESTAMP WHERE order_item_id=? AND status=?",(target,iid,expected))
            elif target in ("ready","served"): db.execute("UPDATE kitchen_queue SET status=?,completed_at=CURRENT_TIMESTAMP WHERE order_item_id=? AND status IN ('cooking','ready')",(target,iid))
            if target == "served":
                from .order_service import refresh_order_status
                parent=db.execute("SELECT order_id FROM order_lines WHERE order_item_id=?",(iid,)).fetchone()
                refresh_order_status(db,parent[0])
            return {"order_item_id":iid,"status":target}
        row=db.execute("SELECT status FROM order_lines WHERE order_item_id=?",(iid,)).fetchone()
        if not row: raise ServiceError("订单菜品不存在。",404,"order_item_id","NOT_FOUND")
        raise ServiceError(f"不能从 {row['status']} 转为 {target}。",409,"status","STATE_CONFLICT")


def start_item(order_item_id): return _transition(order_item_id,"waiting","cooking")
def finish_item(order_item_id): return _transition(order_item_id,"cooking","ready")
def serve_item(order_item_id): return _transition(order_item_id,"ready","served")
def check_order_complete(order_id):
    oid=positive_int(order_id,"order_id")
    with get_connection() as db:
        if not db.execute("SELECT 1 FROM order_headers WHERE order_id=?",(oid,)).fetchone(): raise ServiceError("订单不存在。",404)
        return not db.execute("SELECT 1 FROM order_lines WHERE order_id=? AND status NOT IN ('served','cancelled')",(oid,)).fetchone()
