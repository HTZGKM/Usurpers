from flask import Flask, jsonify, render_template

from restaurant.auth.routes import auth_bp
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
        return render_template("customer/index.html")

    @app.get("/album")
    def album():
        return render_template("customer/album.html")

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
