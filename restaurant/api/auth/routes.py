from restaurant.route_utils import require_form_request

from contextlib import closing
from sqlite3 import IntegrityError
from psycopg import IntegrityError as PostgresIntegrityError
from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import generate_password_hash
from restaurant.db.database import get_connection
from restaurant.services import session_service
from restaurant.services.common import ServiceError
from .forms import LoginForm, LogoutForm, RegisterForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def current_account():
    if "account" not in g:
        account = session_service.session_account(session.get("session_token"))
        g.account_inactive = account is not None and not account.pop("is_active")
        g.account = None if g.account_inactive else account
        if g.account is None:
            session.pop("session_token", None)
            session.pop("account", None)
            session.pop("user", None)
    return g.account


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        require_form_request()
    form = LoginForm()
    if form.validate_on_submit():
        token = session_service.sign_in(form.account.data, form.password.data, session.get("session_token"))
        if token:
            session.clear()
            session["session_token"] = token
            user = current_account()
            if user:
                section = "account" if user["role"] == "customer" else "workspace"
                return redirect(url_for("home", _anchor=section), code=303)
        form.account.errors.append("Invalid account or password.")
    return render_template(
        "auth/form.html", form=form, title="Log In", endpoint="auth.login"
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        require_form_request()
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            with closing(get_connection()) as connection, connection:
                connection.execute(
                    "\n                    INSERT INTO customers (customer_phone, name, password_hash)\n                    VALUES (?, ?, ?)\n                    ",
                    (
                        form.phone_number.data,
                        form.name.data,
                        generate_password_hash(form.password.data),
                    ),
                )
        except (IntegrityError, PostgresIntegrityError):
            form.phone_number.errors.append("This phone number is already registered.")
        else:
            flash("Your account was created. Please log in.", "success")
            return redirect(url_for("auth.login"), code=303)
    return render_template(
        "auth/form.html",
        form=form,
        title="Create a Customer Account",
        endpoint="auth.register",
    )


@auth_bp.get("/me")
def me():
    user = current_account()
    if user is None:
        raise ServiceError("You are not logged in.", 401)
    return jsonify(ok=True, user=user)


@auth_bp.post("/logout")
def logout():
    require_form_request()
    form = LogoutForm()
    if not form.validate_on_submit():
        return ("Invalid logout request.", 400)
    session_service.revoke_session(session.get("session_token"))
    session.clear()
    return redirect(url_for("auth.login"), code=303)
