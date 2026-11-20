from restaurant.db.database import get_connection
from .common import ServiceError, positive_int, required_text


def create_remake(order_item_id, reason, staff_id):
    iid=positive_int(order_item_id,"order_item_id"); sid=positive_int(staff_id,"staff_id")
    why=required_text(reason,"reason",limit=500)
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        item=db.execute("SELECT l.*,h.order_id FROM order_lines l JOIN order_headers h USING(order_id) WHERE l.order_item_id=? AND l.status='served'",(iid,)).fetchone()
        if not item: raise ServiceError("只有已送达的菜品可以登记补做。",409,code="STATE_CONFLICT")
        if not db.execute("SELECT 1 FROM staff WHERE staff_id=? AND is_active=1",(sid,)).fetchone(): raise ServiceError("操作员工不存在或已停用。",403,code="FORBIDDEN")
        if db.execute("SELECT 1 FROM remake_tickets WHERE order_item_id=? AND status IN ('waiting','cooking','ready')",(iid,)).fetchone():
            raise ServiceError("该菜品已有未完成的补做任务。",409,code="DUPLICATE_REMAKE")
        cur=db.execute("INSERT INTO remake_tickets(order_item_id,reason,staff_id) VALUES(?,?,?)",(iid,why,sid))
        return dict(db.execute("SELECT * FROM remake_tickets WHERE remake_id=?",(cur.lastrowid,)).fetchone())


def list_remakes(status="waiting"):
    with get_connection() as db:
        return [dict(r) for r in db.execute("SELECT r.*,l.order_id,l.dish_id,l.quantity,d.dish_name FROM remake_tickets r JOIN order_lines l USING(order_item_id) JOIN dishes d USING(dish_id) WHERE r.status=? ORDER BY r.created_at,r.remake_id",(status,))]


def transition(remake_id, expected, target):
    rid=positive_int(remake_id,"remake_id")
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        changes=db.execute("UPDATE remake_tickets SET status=?,started_at=CASE WHEN ?='cooking' THEN CURRENT_TIMESTAMP ELSE started_at END,completed_at=CASE WHEN ?='completed' THEN CURRENT_TIMESTAMP ELSE completed_at END WHERE remake_id=? AND status=?",(target,target,target,rid,expected)).rowcount
        if changes: return dict(db.execute("SELECT * FROM remake_tickets WHERE remake_id=?",(rid,)).fetchone())
        row=db.execute("SELECT status FROM remake_tickets WHERE remake_id=?",(rid,)).fetchone()
        if not row: raise ServiceError("补做任务不存在。",404)
        raise ServiceError("补做任务状态已变化。",409,code="STATE_CONFLICT")


def start_remake(remake_id): return transition(remake_id,"waiting","cooking")
def complete_remake(remake_id): return transition(remake_id,"cooking","completed")
