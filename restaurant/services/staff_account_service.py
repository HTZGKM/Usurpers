import re
from werkzeug.security import generate_password_hash

from restaurant.db.database import begin_write, get_connection, insert_id
from .common import ServiceError, positive_int, required_text

STAFF_ROLES={"frontdesk","kitchen"}

def get_staff_accounts(role=None):
    with get_connection() as db:
        if role and role not in STAFF_ROLES: raise ServiceError("员工角色不合法。",field="role")
        sql="SELECT staff_id,name,role,phone,email,is_active FROM staff"+(" WHERE role=?" if role else "")+" ORDER BY staff_id"
        return [dict(r) for r in db.execute(sql,(role,) if role else ())]

def create_staff_account(name,phone,email,password,role):
    name=required_text(name,"name",limit=100); phone=required_text(phone,"phone_number",limit=20)
    email=required_text(email,"email",limit=254).lower(); role=required_text(role,"role",limit=20)
    if role not in STAFF_ROLES: raise ServiceError("只能创建前台或厨房账号。",field="role")
    if not re.fullmatch(r"\+?[0-9 -]{7,20}",phone): raise ServiceError("手机号格式不正确。",field="phone_number")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email): raise ServiceError("邮箱格式不正确。",field="email")
    if not isinstance(password,str) or len(password)<6: raise ServiceError("密码至少需要6位。",field="password")
    with get_connection() as db:
        begin_write(db)
        if db.execute("SELECT 1 FROM staff WHERE phone=? OR email=?",(phone,email)).fetchone(): raise ServiceError("手机号或邮箱已存在。",409,"email","DUPLICATE")
        staff_id = insert_id(db, "INSERT INTO staff(name,role,phone,email,password_hash) VALUES(?,?,?,?,?)",
                             (name,role,phone,email,generate_password_hash(password)), "staff_id")
        return {"staff_id":staff_id,"name":name,"role":role,"phone":phone,"email":email,"is_active":1}

def update_staff_account(staff_id,name,phone,email,role):
    sid=positive_int(staff_id,"staff_id"); name=required_text(name,"name",limit=100)
    phone=required_text(phone,"phone_number",limit=20); email=required_text(email,"email",limit=254).lower()
    if role not in STAFF_ROLES: raise ServiceError("员工角色不合法。",field="role")
    if not re.fullmatch(r"\+?[0-9 -]{7,20}",phone): raise ServiceError("手机号格式不正确。",field="phone_number")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email): raise ServiceError("邮箱格式不正确。",field="email")
    with get_connection() as db:
        begin_write(db)
        _require_managed_staff(db, sid)
        if db.execute("SELECT 1 FROM staff WHERE (phone=? OR email=?) AND staff_id<>?",(phone,email,sid)).fetchone(): raise ServiceError("手机号或邮箱已被其他账号使用。",409)
        db.execute("UPDATE staff SET name=?,phone=?,email=?,role=? WHERE staff_id=?",(name,phone,email,role,sid))
        return {"staff_id":sid,"name":name,"phone":phone,"email":email,"role":role}

def set_staff_active(staff_id,is_active):
    sid=positive_int(staff_id,"staff_id")
    if is_active not in (True,False,0,1): raise ServiceError("启用状态不合法。",field="is_active")
    with get_connection() as db:
        begin_write(db)
        _require_managed_staff(db, sid)
        db.execute("UPDATE staff SET is_active=? WHERE staff_id=?",(int(is_active),sid))
        return {"staff_id":sid,"is_active":bool(is_active)}

def reset_staff_password(staff_id,password="123456"):
    sid=positive_int(staff_id,"staff_id")
    if not isinstance(password,str) or len(password)<6: raise ServiceError("密码至少需要6位。",field="password")
    with get_connection() as db:
        begin_write(db)
        _require_managed_staff(db, sid)
        db.execute("UPDATE staff SET password_hash=? WHERE staff_id=?",(generate_password_hash(password),sid))
        return {"staff_id":sid,"reset":True}


def _require_managed_staff(db, staff_id):
    member = db.execute("SELECT role FROM staff WHERE staff_id=?", (staff_id,)).fetchone()
    if not member:
        raise ServiceError("员工账号不存在。",404)
    if member["role"] not in STAFF_ROLES:
        raise ServiceError("此操作仅适用于前台或厨房账号。",409,code="STATE_CONFLICT")
