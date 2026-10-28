from flask import Flask, jsonify
from flask_cors import CORS

from restaurant.auth.routes import auth_bp
from restaurant.db import ensure_database

def create_app() -> Flask:
    app = Flask(__name__)

    app.config["SECRET_KEY"] = "dev-secret-key"
    CORS(app, supports_credentials=True)

    ensure_database()
    app.register_blueprint(auth_bp)

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