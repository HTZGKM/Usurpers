from contextlib import closing
from hmac import compare_digest
from sqlite3 import IntegrityError

from flask import Blueprint, flash, jsonify, redirect, render_template, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from restaurant.db.database import get_connection, hash_password

from .forms import LoginForm, LogoutForm, RegisterForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _is_active_staff(member):
    return member is not None and (
        "is_active" not in member.keys() or member["is_active"] == 1
    )


def _authenticate(account, password):
    with closing(get_connection()) as connection, connection:
        if "@" in account:
            member = connection.execute(
                "SELECT * FROM staff WHERE email = ?",
                (account.lower(),),
            ).fetchone()
            if not _is_active_staff(member):
                return None
            identity = {"staff_id": member["staff_id"]}
            update_password = "UPDATE staff SET password = ? WHERE staff_id = ? AND password = ?"
            key = member["staff_id"]
        else:
            member = connection.execute(
                "SELECT customer_phone, password FROM customers WHERE customer_phone = ?",
                (account,),
            ).fetchone()
            identity = {"customer_phone": account}
            update_password = "UPDATE customers SET password = ? WHERE customer_phone = ? AND password = ?"
            key = account

        if member is None:
            return None

        stored_password = member["password"]
        if "$" in stored_password:
            return identity if check_password_hash(stored_password, password) else None
        if not compare_digest(stored_password, hash_password(password)):
            return None

        connection.execute(update_password, (generate_password_hash(password), key, stored_password))
        return identity


def current_account():
    identity = session.get("account")
    if not identity:
        return None

    with closing(get_connection()) as connection:
        if "staff_id" in identity:
            member = connection.execute(
                "SELECT * FROM staff WHERE staff_id = ?",
                (identity["staff_id"],),
            ).fetchone()
            if _is_active_staff(member):
                return {"username": member["email"], "name": member["name"], "role": member["role"]}
        else:
            customer = connection.execute(
                "SELECT customer_phone, name FROM customers WHERE customer_phone = ?",
                (identity["customer_phone"],),
            ).fetchone()
            if customer:
                return {
                    "username": customer["customer_phone"],
                    "name": customer["name"],
                    "role": "customer",
                }

    session.pop("account", None)
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        identity = _authenticate(form.account.data, form.password.data)
        if identity is not None:
            session.clear()
            session["account"] = identity
            user = current_account()
            if user:
                section = "account" if user["role"] == "customer" else "workspace"
                return redirect(url_for("home", _anchor=section), code=303)
        form.account.errors.append("Invalid account or password.")

    return render_template("auth/form.html", form=form, title="Log In", endpoint="auth.login")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            with closing(get_connection()) as connection, connection:
                connection.execute(
                    """
                    INSERT INTO customers (customer_phone, name, password)
                    VALUES (?, ?, ?)
                    """,
                    (form.phone_number.data, form.name.data, generate_password_hash(form.password.data)),
                )
        except IntegrityError:
            form.phone_number.errors.append("This phone number is already registered.")
        else:
            flash("Your account was created. Please log in.", "success")
            return redirect(url_for("auth.login"), code=303)

    return render_template(
        "auth/form.html", form=form, title="Create a Customer Account", endpoint="auth.register"
    )


@auth_bp.get("/me")
def me():
    user = current_account()
    if user is None:
        return jsonify(ok=False, message="You are not logged in."), 401
    return jsonify(ok=True, user=user)


@auth_bp.post("/logout")
def logout():
    form = LogoutForm()
    if not form.validate_on_submit():
        return "Invalid logout request.", 400
    session.clear()
    return redirect(url_for("auth.login"), code=303)
