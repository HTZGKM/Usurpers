from flask import Blueprint

from .forms import LoginForm, LogoutForm, RegisterForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def current_account():
    # TODO: Load the current account through the agreed service interface.
    pass


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        # TODO: Authenticate, establish the session, and redirect by role.
        pass

    # TODO: Show the login form or errors.


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        # TODO: Create a customer account and redirect to login.
        pass

    # TODO: Show the registration form or errors.


@auth_bp.get("/me")
def me():
    # TODO: Return the current account or a not-logged-in response.
    pass


@auth_bp.post("/logout")
def logout():
    form = LogoutForm()
    if form.validate_on_submit():
        # TODO: End the session and redirect to login.
        pass

    # TODO: Handle form errors.
