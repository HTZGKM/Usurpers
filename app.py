import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from psycopg.errors import LockNotAvailable
from werkzeug.exceptions import HTTPException

from restaurant.api.auth.forms import LoginForm, LogoutForm, RegisterForm
from restaurant.api.auth.routes import auth_bp, current_account
from restaurant.db import ensure_database
from restaurant.db.database import using_postgres
from restaurant.services.common import ServiceError
from restaurant.api.admin.routes import admin_bp
from restaurant.api.customer.routes import customer_bp
from restaurant.api.frontdesk.routes import frontdesk_bp
from restaurant.api.kitchen.routes import kitchen_bp
from restaurant.api.reservation_routes import reservation_bp
from restaurant.presentation import restaurant_view, seating_view
from restaurant.services import allocation

def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="restaurant/templates",
        static_folder="restaurant/static",
        static_url_path="/static",
    )

    https = os.environ.get("USURPERS_HTTPS") == "1"
    secret = os.environ.get("USURPERS_SECRET_KEY")
    if https and not secret:
        raise RuntimeError("Set USURPERS_SECRET_KEY before serving the app over HTTPS.")
    app.config.update(
        SECRET_KEY=secret or "dev-secret-key",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=https,
    )

    on_vercel = os.environ.get("VERCEL") == "1"
    if on_vercel and (not using_postgres() or not secret or not https):
        raise RuntimeError("Set DATABASE_URL, USURPERS_SECRET_KEY and USURPERS_HTTPS=1 for Vercel.")
    if not using_postgres():
        ensure_database()
    app.register_blueprint(auth_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(frontdesk_bp)
    app.register_blueprint(kitchen_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(reservation_bp)
    api_blueprints = {bp.name for bp in (customer_bp, frontdesk_bp, kitchen_bp, admin_bp, reservation_bp)}

    @app.after_request
    def protect_rendered_pages(response):
        if response.mimetype == "text/html":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; connect-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com https://cdn.fontshare.com; img-src 'self' data:; "
                "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
            )
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "same-origin"
            response.headers["Cache-Control"] = "no-store"
        return response

    def error_response(status, data, response=None):
        wants_json = (
            request.blueprint in api_blueprints
            or request.endpoint in {"health", "auth.me"}
            or request.is_json
            or request.accept_mimetypes.best_match(("text/html", "application/json")) == "application/json"
        )
        if response is None:
            response = app.response_class(status=status)
        if wants_json:
            response.set_data(app.json.dumps(data))
            response.mimetype = "application/json"
        else:
            title, message = {
                400: ("Unable to open this page", "Check the address or return to the restaurant."),
                401: ("Sign-in required", "Sign in to continue to this page."),
                403: ("Access denied", "Your account cannot open this page."),
                404: ("Page not found", "This address may have changed. Return to the restaurant to continue."),
                405: ("This action is unavailable", "Return to the restaurant and try again from the page."),
                500: ("Something went wrong", "We couldn't load this page. Please try again in a moment."),
            }.get(status, ("Unable to load this page", "Return to the restaurant and try again."))
            response.set_data(render_template("errors/error.html", status=status, title=title, message=message))
            response.mimetype = "text/html"
        response.vary.add("Accept")
        return response

    @app.errorhandler(ServiceError)
    def service_error(error: ServiceError):
        return error_response(error.status_code, error.as_dict())

    @app.errorhandler(LockNotAvailable)
    def database_busy(error: LockNotAvailable):
        app.logger.warning("Database lock unavailable: %s", error.sqlstate)
        unavailable = ServiceError("The restaurant is busy. Try the same request again shortly.", 503, code="DATABASE_BUSY")
        return error_response(unavailable.status_code, unavailable.as_dict())

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        response = error.get_response()
        status = response.status_code
        message = "An internal server error occurred." if status >= 500 else error.description
        return error_response(status, ServiceError(message, status).as_dict(), response)

    @app.errorhandler(Exception)
    def unexpected_error(error: Exception):
        app.logger.exception("Unhandled backend error", exc_info=error)
        return error_response(500, {
            "ok": False, "success": False, "error": "INTERNAL_SERVER_ERROR",
            "message": "An internal server error occurred.",
        })

    @app.get("/")
    def home():
        account = current_account()
        if request.args.get("fragment") == "seating":
            if not account:
                return "", 401
            if account["role"] not in ("customer", "frontdesk"):
                return "", 403
            return render_template("_seating_data.html", visits=seating_view(account)), {"Cache-Control": "no-store"}
        fonts = Path(app.static_folder) / "fonts"
        return render_template(
            "customer/guest.html",
            account=account,
            login_form=LoginForm() if account is None else None,
            register_form=RegisterForm() if account is None else None,
            logout_form=LogoutForm() if account else None,
            has_cheltenham=(fonts / "CheltenhamBT-Roman.woff2").is_file(),
            has_local_satoshi=(fonts / "Satoshi-Light.local.woff2").is_file(),
            reservation_flow=allocation.enabled(),
            **restaurant_view(app.root_path),
        ), {"Cache-Control": "no-store"}

    @app.get("/health")
    def health():
        return jsonify({
            "ok": True,
            "message": "后端正常启动"
        })

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=False)
