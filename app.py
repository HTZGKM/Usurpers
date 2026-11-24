import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from restaurant.api.auth.forms import LoginForm, LogoutForm, RegisterForm
from restaurant.api.auth.routes import auth_bp, current_account
from restaurant.db import ensure_database
from restaurant.services.common import ServiceError
from restaurant.api.admin.routes import admin_bp
from restaurant.api.customer.routes import customer_bp
from restaurant.api.frontdesk.routes import frontdesk_bp
from restaurant.api.kitchen.routes import kitchen_bp
from restaurant.presentation import restaurant_view, seating_view

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

    ensure_database()
    app.register_blueprint(auth_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(frontdesk_bp)
    app.register_blueprint(kitchen_bp)
    app.register_blueprint(admin_bp)

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

    @app.errorhandler(ServiceError)
    def service_error(error: ServiceError):
        return jsonify(error.as_dict()), error.status_code

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        return jsonify({"ok":False,"success":False,"error":error.name.upper().replace(" ","_"),"message":error.description}), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error: Exception):
        app.logger.exception("Unhandled backend error", exc_info=error)
        return jsonify({"ok":False,"success":False,"error":"INTERNAL_SERVER_ERROR","message":"An internal server error occurred."}),500

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
