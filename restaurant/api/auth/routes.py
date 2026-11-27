from restaurant.route_utils import require_form_request, require_api_role, validated_data

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
from .forms import (ProfileForm, RecoveryEmailForm, ForgotPasswordForm, VerifyEmailForm,
                    ResetPasswordForm, LinkRequestForm, LinkConfirmationForm)
from restaurant.services import account_recovery, account_linking

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


@auth_bp.get("/settings")
def settings():
    denied = require_api_role("customer")
    if denied is not None:
        return denied
    return jsonify(ok=True, profile=account_recovery.profile(g.account["username"]))


@auth_bp.post("/profile")
def update_profile():
    denied = require_api_role("customer")
    if denied is not None:
        return denied
    data = validated_data(ProfileForm)
    return jsonify(ok=True, **account_recovery.change_name(g.account["username"], data["name"]))


@auth_bp.post("/recovery-email")
def change_recovery_email():
    denied = require_api_role("customer")
    if denied is not None:
        return denied
    data = validated_data(RecoveryEmailForm)
    return jsonify(ok=True, **account_recovery.request_email_change(g.account["username"], data["email"], data["current_password"]))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        require_form_request()
    form = ForgotPasswordForm()
    message, failed, status = "", False, 200
    if form.validate_on_submit():
        try:
            message = account_recovery.request_password_reset(form.phone_number.data, request.remote_addr or "unknown")["message"]
        except ServiceError as error:
            message, failed, status = error.message, True, error.status_code
    return render_template("auth/recovery.html", form=form, title="Reset your password", message=message, failed=failed,
                           explanation="Enter your sign-in phone number. Reset links go only to the recovery email you previously verified."), status


@auth_bp.route("/verify-email", methods=["GET", "POST"])
def verify_recovery_email():
    if request.method == "POST":
        require_form_request()
    form = VerifyEmailForm()
    if request.method == "GET":
        form.token.data = request.args.get("token", "")
    message, failed = "", False
    if form.validate_on_submit():
        try:
            message = account_recovery.verify_email(form.token.data)["message"]
            form = None
        except ServiceError as error:
            message, failed = error.message, True
    return render_template("auth/recovery.html", form=form, title="Verify recovery email", message=message, failed=failed,
                           explanation="Confirm to bind this recovery email. Your phone number remains your sign-in identifier.")


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_customer_password():
    if request.method == "POST":
        require_form_request()
    form = ResetPasswordForm()
    if request.method == "GET":
        form.token.data = request.args.get("token", "")
    message, failed = "", False
    if form.validate_on_submit():
        try:
            message = account_recovery.reset_password(form.token.data, form.password.data)["message"]
            session.clear()
            form = None
        except ServiceError as error:
            message, failed = error.message, True
    return render_template("auth/recovery.html", form=form, title="Choose a new password", message=message, failed=failed,
                           explanation="Use 6 to 128 characters. After resetting, all old sessions are signed out; your restaurant records are kept.")


@auth_bp.route("/link-requests", methods=["GET", "POST"])
def link_requests():
    denied = require_api_role("customer") if request.method == "GET" else require_api_role("frontdesk", "admin")
    if denied is not None:
        return denied
    if request.method == "GET":
        return jsonify(ok=True, requests=account_linking.pending_links(g.account["username"]))
    data = validated_data(LinkRequestForm)
    result = account_linking.request_link(data["target_type"], data["target_id"], data["candidate_phone"],
                                          g.account["role"] + ":" + g.account["username"])
    return jsonify(ok=True, request=result), 201


@auth_bp.post("/link-requests/<int:link_id>/<action>")
def resolve_link_request(link_id, action):
    denied = require_api_role("customer")
    if denied is not None:
        return denied
    data = validated_data(LinkConfirmationForm)
    return jsonify(ok=True, **account_linking.resolve_link(link_id,g.account["username"],action,data.get("expected_version") or None))
