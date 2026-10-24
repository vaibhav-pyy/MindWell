"""Session authentication, role checks and CSRF protection.

Sessions are Flask's signed cookies (HttpOnly, SameSite=Lax). Every state-changing
request must also carry an ``X-CSRF-Token`` header equal to the token stored in the
session; a cross-site form cannot read the token, so it cannot forge requests.
"""
import secrets
import time
from functools import wraps

from flask import g, session

from .extensions import db
from .models import User
from .utils import ApiError

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def ensure_csrf_token():
    token = session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf"] = token
    return token


def check_csrf(request):
    if request.method in SAFE_METHODS:
        return
    expected = session.get("csrf")
    supplied = request.headers.get("X-CSRF-Token", "")
    if not expected or not secrets.compare_digest(expected, supplied):
        raise ApiError("Your session security token is missing or expired. Please reload the page.",
                       403, "csrf_failed")


def login_user(user):
    session.clear()
    session.permanent = True
    session["uid"] = user.id
    session["role"] = user.role
    session["last_seen"] = int(time.time())
    session["csrf"] = secrets.token_urlsafe(32)  # rotate on login


def logout_user():
    session.clear()


def load_current_user(app):
    g.user = None
    uid = session.get("uid")
    if not uid:
        return
    idle_limit = app.config["SESSION_IDLE_MINUTES"] * 60
    last_seen = session.get("last_seen", 0)
    now = int(time.time())
    if now - last_seen > idle_limit:
        session.clear()
        return
    user = db.session.get(User, uid)
    if user is None or not user.is_active or user.role != session.get("role"):
        session.clear()
        return
    session["last_seen"] = now
    g.user = user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if g.get("user") is None:
            raise ApiError("Please sign in to continue.", 401, "unauthenticated")
        return fn(*args, **kwargs)
    return wrapper


def role_required(role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = g.get("user")
            if user is None:
                raise ApiError("Please sign in to continue.", 401, "unauthenticated")
            if user.role != role:
                raise ApiError("You do not have access to this resource.", 403, "forbidden")
            return fn(*args, **kwargs)
        return wrapper
    return decorator


student_required = role_required("student")
teacher_required = role_required("teacher")
