from flask import Flask, jsonify, render_template
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from restaurant.auth.routes import auth_bp
from restaurant.db import ensure_database
from restaurant.services.common import ServiceError
from restaurant.api_routes import api_bp

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
    app.register_blueprint(api_bp)

    @app.errorhandler(ServiceError)
    def service_error(error: ServiceError):
        return jsonify(error.as_dict()), error.status_code

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        return jsonify({"ok":False,"success":False,"error":error.name.upper().replace(" ","_"),"message":error.description}), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error: Exception):
        app.logger.exception("Unhandled backend error", exc_info=error)
        return jsonify({"ok":False,"success":False,"error":"INTERNAL_SERVER_ERROR","message":"服务器处理请求时发生错误。"}),500

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
