from restaurant.db.database import begin_write, get_connection
from .common import ServiceError, phone_number


def set_customer_active(customer_phone, is_active):
    phone=phone_number(customer_phone,"customer_phone")
    if not isinstance(is_active,bool): raise ServiceError("is_active 必须是布尔值。",field="is_active")
    with get_connection() as db:
        begin_write(db)
        if is_active:
            db.execute("""DELETE FROM web_sessions WHERE customer_phone=?
                          AND EXISTS (SELECT 1 FROM customers WHERE customer_phone=? AND is_active=0)""", (phone, phone))
        cur=db.execute("UPDATE customers SET is_active=? WHERE customer_phone=?",(int(is_active),phone))
        if not cur.rowcount: raise ServiceError("顾客账号不存在。",404)
        row=db.execute("SELECT customer_phone,name,is_active FROM customers WHERE customer_phone=?",(phone,)).fetchone()
        return dict(row)


def get_customer_accounts():
    with get_connection() as db:
        return [dict(r) for r in db.execute("SELECT customer_phone,name,is_active FROM customers ORDER BY name,customer_phone")]
