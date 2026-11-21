import json
from pathlib import Path

from flask import Flask, jsonify, render_template
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from restaurant.auth.forms import LoginForm, LogoutForm, RegisterForm
from restaurant.auth.routes import auth_bp, current_account
from restaurant.db import ensure_database
from restaurant.services.common import ServiceError
from restaurant.admin.routes import admin_bp
from restaurant.customer.routes import customer_bp
from restaurant.frontdesk.routes import frontdesk_bp
from restaurant.kitchen.routes import kitchen_bp

def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="restaurant/templates",
        static_folder="restaurant/static",
        static_url_path="/static",
    )

    app.config["SECRET_KEY"] = "dev-secret-key"
    CORS(app, supports_credentials=True)

    ensure_database()
    app.register_blueprint(auth_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(frontdesk_bp)
    app.register_blueprint(kitchen_bp)
    app.register_blueprint(admin_bp)

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
        with (Path(app.root_path) / "restaurant/customer/catalog.json").open(encoding="utf-8") as source:
            catalog = json.load(source)
        return render_template(
            "customer/guest.html",
            account=account,
            login_form=LoginForm() if account is None else None,
            register_form=RegisterForm() if account is None else None,
            logout_form=LogoutForm() if account else None,
            has_cheltenham=(Path(app.static_folder) / "fonts/CheltenhamBT-Roman.woff2").is_file(),
            catalog=catalog,
            categories={"burger": "Burgers", "pizza": "Pizzas", "sides": "Sides", "drinks": "Drinks"},
            slots=("17:30", "18:00", "19:30"),
            tables=[
                ("A1", 2, 16, 23), ("A2", 2, 42, 23), ("A3", 4, 67, 23),
                ("B1", 4, 19, 53), ("B2", 4, 48, 53), ("B3", 6, 77, 53),
                ("C1", 2, 19, 81), ("C2", 6, 48, 81),
            ],
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
