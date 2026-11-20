from restaurant.db.database import get_connection
from .common import ServiceError, money, positive_int, required_text


def create_refund(order_id, amount, reason, staff_id, idempotency_key):
    oid=positive_int(order_id,"order_id"); sid=positive_int(staff_id,"staff_id")
    value=money(amount,"amount"); why=required_text(reason,"reason",limit=500); key=required_text(idempotency_key,"idempotency_key",limit=120)
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        existing=db.execute("SELECT * FROM refunds WHERE idempotency_key=?",(key,)).fetchone()
        if existing:
            if existing["order_id"]!=oid or round(float(existing["amount"]),2)!=float(value):
                raise ServiceError("幂等键已用于不同退款请求。",409,code="IDEMPOTENCY_CONFLICT")
            return {**dict(existing),"already_refunded":True}
        payment=db.execute("SELECT * FROM payments WHERE order_id=?",(oid,)).fetchone()
        if not payment: raise ServiceError("订单尚无付款记录。",409,code="PAYMENT_REQUIRED")
        if not db.execute("SELECT 1 FROM staff WHERE staff_id=? AND is_active=1",(sid,)).fetchone(): raise ServiceError("操作员工不存在或已停用。",403,code="FORBIDDEN")
        refunded=float(db.execute("SELECT COALESCE(SUM(amount),0) FROM refunds WHERE payment_id=?",(payment["payment_id"],)).fetchone()[0])
        if float(value)+refunded>float(payment["amount"]): raise ServiceError("累计退款金额不能超过原付款金额。",409,code="REFUND_EXCEEDS_PAYMENT")
        cur=db.execute("INSERT INTO refunds(payment_id,order_id,amount,reason,staff_id,idempotency_key) VALUES(?,?,?,?,?,?)",(payment["payment_id"],oid,str(value),why,sid,key))
        return dict(db.execute("SELECT * FROM refunds WHERE refund_id=?",(cur.lastrowid,)).fetchone())


def get_refunds(order_id):
    oid=positive_int(order_id,"order_id")
    with get_connection() as db:
        return [dict(r) for r in db.execute("SELECT * FROM refunds WHERE order_id=? ORDER BY refund_id",(oid,))]
