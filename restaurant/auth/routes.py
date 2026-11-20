from flask import Blueprint, jsonify, request, session

from restaurant.services.auth_service import authenticate, register_customer
from restaurant.services.common import ServiceError

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
STAFF_ROLES = { "frontdesk", "kitchen"}

def find_user(account: str, password: str) -> dict[str, str] | None:
    return authenticate(account,password)


def new_user(name: str, phone: str, role: str, email: str, password: str) -> dict[str, str] | None:
    if not isinstance(role,str) or role.strip().lower() != "customer": raise ServiceError("公开注册仅支持顾客账号。",403,field="role",code="FORBIDDEN")
    return register_customer(name,phone,password)

@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data,dict): raise ServiceError("请求体必须是 JSON 对象。")
    username = data.get("account",data.get("username"))
    password = data.get("password") or ""

    if not username or not password:
        raise ServiceError("请填写账号和密码。")

    user = find_user(username, password)
    if not user:
        raise ServiceError("账号或密码不正确。",401,code="UNAUTHENTICATED")

    session["user"] = user

    return jsonify({
        "ok": True,
        "user": user
    })

@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True)
    if not isinstance(data,dict): raise ServiceError("请求体必须是 JSON 对象。")
    name = data.get("name")
    phone = data.get("phone_number",data.get("phone"))
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "customer")

    if not name or not password:
        raise ServiceError("请填写姓名和密码。")

    if role == "customer" and not phone:
        raise ServiceError("顾客注册需要填写手机号。",field="phone_number")

    if role in STAFF_ROLES and (not phone or not email):
        raise ServiceError("员工注册需要填写手机号和邮箱。")

    if role != "customer":
        raise ServiceError("公开注册仅支持顾客账号。",403,code="FORBIDDEN")

    user = new_user(name, phone, role, email, password)
    if not user:
        raise ServiceError("账号已存在。",409,code="DUPLICATE")

    session["user"] = user

    return jsonify({
        "ok": True,
        "user": user
    }), 201

#session管理
@auth_bp.get("/me")
def me():
    user = session.get("user")
    if not user:
        return jsonify({
            "ok": False,
            "message": "未登录。"
        }), 401

    if user.get("role")=="customer":
        from restaurant.db.database import get_connection
        with get_connection() as db:
            row=db.execute("SELECT is_active FROM customers WHERE customer_phone=?",(user.get("username"),)).fetchone()
        if not row or not row["is_active"]:
            session.pop("user",None)
            return jsonify({"ok":False,"error":"FORBIDDEN","message":"顾客账号已停用。"}),403

    return jsonify({
        "ok": True,
        "user": user
    })
@auth_bp.post("/logout")
def logout():
    session.pop("user", None)
    return jsonify({
        "ok": True
    })
