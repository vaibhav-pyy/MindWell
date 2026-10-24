from flask import Blueprint, current_app
from sqlalchemy import text

from ..extensions import db
from ..services import notifications
from ..utils import ok

bp = Blueprint("public", __name__, url_prefix="/api")


@bp.get("/public/support")
def support():
    """Helpline details — no login required, so help is reachable even when signed out."""
    return ok(current_app.config["SUPPORT"])


@bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db.session.rollback()
        db_ok = False
    return ok({"status": "ok" if db_ok else "degraded", "database": db_ok,
               "gemini_configured": current_app.extensions["gemini"].configured,
               "gemini_model": current_app.config["GEMINI_MODEL"],
               "notification_channels": notifications.channel_status()}, 200 if db_ok else 503)
