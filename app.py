import json
from pathlib import Path

from flask import Flask, jsonify, render_template

from restaurant.auth.forms import LoginForm, LogoutForm, RegisterForm
from restaurant.auth.routes import auth_bp, current_account
from restaurant.db import ensure_database

def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="restaurant/templates",
        static_folder="restaurant/static",
        static_url_path="/static",
    )

    app.config["SECRET_KEY"] = "dev-secret-key"

    ensure_database()
    app.register_blueprint(auth_bp)

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
