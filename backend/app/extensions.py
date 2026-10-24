from flask import session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def user_or_ip():
    """Rate-limit key: the authenticated user when known, otherwise the client IP."""
    uid = session.get("uid")
    return f"user:{uid}" if uid else f"ip:{get_remote_address()}"


limiter = Limiter(key_func=get_remote_address, default_limits=["300 per minute"])


# SQLite (used by the test-suite) ignores foreign keys unless asked; MySQL/InnoDB enforces them natively.
from sqlalchemy import event  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402


@event.listens_for(Engine, "connect")
def _sqlite_fk_pragma(dbapi_connection, connection_record):
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
