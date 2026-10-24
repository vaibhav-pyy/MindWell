import logging

from flask import Flask, request
from werkzeug.exceptions import HTTPException

from .config import Config
from .extensions import db, limiter
from .services.gemini import GeminiService
from .utils import ApiError, error_response


def create_app(config_object=Config):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Copy .env.example to .env and set a long random SECRET_KEY.")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Request logging never includes bodies, so chat content is not written to logs.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    db.init_app(app)
    limiter.init_app(app)
    app.extensions["gemini"] = GeminiService(app.config["GEMINI_API_KEY"], app.config["GEMINI_MODEL"],
                                             app.config["GEMINI_TIMEOUT_SECONDS"],
                                             fallback_model=app.config["GEMINI_FALLBACK_MODEL"],
                                             max_retries=app.config["GEMINI_MAX_RETRIES"],
                                             thinking_level=app.config["GEMINI_THINKING_LEVEL"])

    from .security import check_csrf, load_current_user

    @app.before_request
    def _before():
        load_current_user(app)
        if request.path.startswith("/api/"):
            check_csrf(request)

    @app.after_request
    def _headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return resp

    @app.errorhandler(ApiError)
    def _api_error(exc):
        db.session.rollback()  # never leave half-applied changes pending
        return error_response(exc.message, exc.status, exc.code, exc.details)

    @app.errorhandler(HTTPException)
    def _http_error(exc):
        if exc.code == 429:
            return error_response("Too many requests. Please slow down and try again shortly.", 429, "rate_limited")
        return error_response(exc.description or exc.name, exc.code, exc.name.lower().replace(" ", "_"))

    @app.errorhandler(Exception)
    def _unhandled(exc):
        db.session.rollback()
        app.logger.exception("Unhandled error on %s %s", request.method, request.path)
        return error_response("Something went wrong on our side. Please try again.", 500, "server_error")

    from .routes import activities, auth, chat, emergency, profile, public, teacher, wellness
    for module in (auth, profile, chat, wellness, activities, emergency, teacher, public):
        app.register_blueprint(module.bp)

    from . import cli
    cli.register(app)
    return app
