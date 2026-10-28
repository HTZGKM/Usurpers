from flask import Blueprint, jsonify, request, session

from restaurant.db.database import get_connection, hash_password

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
STAFF_ROLES = { "frontdesk", "kitchen"}

def find_user(account: str, password: str) -> dict[str, str] | None:
    account = account.strip()
    password = hash_password(password)
    
    with get_connection() as connection:
        staff = connection.execute(
            """
            SELECT email, name, role, password
            FROM staff
            WHERE email = ?
            """,
            (account,),
        ).fetchone()

        if staff and staff["password"] == password:
            return {
                "username": staff["email"],
                "name": staff["name"],
                "role": staff["role"],
            }
        
        customer = connection.execute(
            """
            SELECT customer_phone, name, password
            FROM customers
            WHERE customer_phone = ?
            """,
            (account,),
        ).fetchone()

        if customer and customer["password"] == password:
            return {
                "username": customer["customer_phone"],
                "name": customer["name"],
                "role": "customer",
            }
    return None


def new_user(name: str, phone: str, role: str, email: str, password: str) -> dict[str, str] | None:
    name = name.strip()
    phone = phone.strip()
    role = role.strip().lower()
    email = email.strip().lower()
    password = hash_password(password)

    with get_connection() as connection:
        if role == "customer":
            existing_customer = connection.execute(
                """
                SELECT 1
                FROM customers
                WHERE customer_phone = ?
                """,
                (phone,),
            ).fetchone()
            if existing_customer:
                return None

            connection.execute(
                """
                INSERT INTO customers (customer_phone, name, password)
                VALUES (:customer_phone, :name, :password)
                """,
                {
                    "customer_phone": phone,
                    "name": name,
                    "password": password,
                },
            )
            connection.commit()
            return {
                "username": phone,
                "name": name,
                "role": "customer",
            }

        if role in STAFF_ROLES:
            existing_staff = connection.execute(
                """
                SELECT 1
                FROM staff
                WHERE email = ? OR phone = ?
                """,
                (email, phone),
            ).fetchone()
            if existing_staff:
                return None

            connection.execute(
                """
                INSERT INTO staff (name, role, phone, email, password)
                VALUES (:name, :role, :phone, :email, :password)
                """,
                {
                    "name": name,
                    "role": role,
                    "phone": phone,
                    "email": email,
                    "password": password,
                },
            )
            connection.commit()
            return {
                "username": email,
                "name": name,
                "role": role,
            }

    return None

@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({
            "ok": False,
            "message": "请填写用户名和密码。"
        }), 400

    user = find_user(username, password)
    if not user:
        return jsonify({
            "ok": False,
            "message": "用户名或密码不正确。"
        }), 401

    session["user"] = user

    return jsonify({
        "ok": True,
        "user": user
    })

@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "customer").strip().lower()

    if not name or not password:
        return jsonify({
            "ok": False,
            "message": "请填写姓名和密码。"
        }), 400

    if role == "customer" and not phone:
        return jsonify({
            "ok": False,
            "message": "顾客注册需要填写手机号。"
        }), 400

    if role in STAFF_ROLES and (not phone or not email):
        return jsonify({
            "ok": False,
            "message": "员工注册需要填写手机号和邮箱。"
        }), 400

    if role != "customer" and role not in STAFF_ROLES:
        return jsonify({
            "ok": False,
            "message": "角色不合法。"
        }), 400

    user = new_user(name, phone, role, email, password)
    if not user:
        return jsonify({
            "ok": False,
            "message": "账号已存在，或注册信息不完整。"
        }), 409

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
