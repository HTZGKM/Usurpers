from restaurant.db.database import begin_write, get_connection, hash_password
from .common import ServiceError, phone_number, required_text


def authenticate(account, password):
    account=required_text(account,"account",limit=254)
    if not isinstance(password,str) or not password: raise ServiceError("密码不能为空。",field="password")
    hashed=hash_password(password)
    with get_connection() as db:
        staff=db.execute("SELECT email,name,role,password_hash FROM staff WHERE email=? AND is_active=1",(account,)).fetchone()
        if staff and staff["password_hash"]==hashed: return {"username":staff["email"],"name":staff["name"],"role":staff["role"]}
        customer=db.execute("SELECT customer_phone,name,password_hash FROM customers WHERE customer_phone=? AND is_active=1",(account,)).fetchone()
        if customer and customer["password_hash"]==hashed: return {"username":customer["customer_phone"],"name":customer["name"],"role":"customer"}
    return None


def set_customer_active(customer_phone, is_active):
    phone=phone_number(customer_phone,"customer_phone")
    if not isinstance(is_active,bool): raise ServiceError("is_active 必须是布尔值。",field="is_active")
    with get_connection() as db:
        begin_write(db)
        cur=db.execute("UPDATE customers SET is_active=? WHERE customer_phone=?",(int(is_active),phone))
        if not cur.rowcount: raise ServiceError("顾客账号不存在。",404)
        row=db.execute("SELECT customer_phone,name,is_active FROM customers WHERE customer_phone=?",(phone,)).fetchone()
        return dict(row)


def get_customer_accounts():
    with get_connection() as db:
        return [dict(r) for r in db.execute("SELECT customer_phone,name,is_active FROM customers ORDER BY name,customer_phone")]


def register_customer(name, phone, password):
    name=required_text(name,"name",limit=100); phone=phone_number(phone,"phone_number")
    if not isinstance(password,str) or len(password)<6: raise ServiceError("密码至少需要6位。",field="password")
    with get_connection() as db:
        begin_write(db)
        if db.execute("SELECT 1 FROM customers WHERE customer_phone=?",(phone,)).fetchone(): raise ServiceError("手机号已注册。",409,"phone_number","DUPLICATE")
        db.execute("INSERT INTO customers(customer_phone,name,password_hash) VALUES(?,?,?)",(phone,name,hash_password(password)))
        return {"username":phone,"name":name,"role":"customer"}
