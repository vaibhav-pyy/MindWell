import re

from flask import Blueprint, g
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, limiter
from ..models import ConsentRecord, StudentProfile, StudentProgress, User, utcnow
from ..security import ensure_csrf_token, login_required, login_user, logout_user
from ..utils import ApiError, json_body, normalize_email, ok, req_bool, req_str

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

TERMS_VERSION = "terms-v1"
AI_CONSENT_VERSION = "ai-v1"
# Compared against when the email is unknown, so response time doesn't reveal which emails exist.
_DUMMY_HASH = generate_password_hash("timing-equaliser-not-a-real-password")


def validate_password(pw):
    if not isinstance(pw, str) or not 10 <= len(pw) <= 128:
        raise ApiError("Password must be 10-128 characters.", 422, "validation_error", {"password": "length"})
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise ApiError("Password must include at least one letter and one number.", 422, "validation_error",
                       {"password": "weak"})
    return pw


def user_dict(user):
    data = {"id": user.id, "email": user.email, "role": user.role, "display_name": user.display_name,
            "is_demo": user.is_demo}
    if user.role == "student" and user.student_profile:
        p = user.student_profile
        data["privacy"] = {"ai_processing_consent": p.ai_processing_consent, "memory_enabled": p.memory_enabled,
                           "personalize_with_checkins": p.personalize_with_checkins}
    return data


def create_student(email, password, display_name, ai_consent, is_demo=False):
    user = User(email=email, password_hash=generate_password_hash(password), role="student",
                display_name=display_name, is_demo=is_demo)
    db.session.add(user)
    db.session.flush()
    db.session.add(StudentProfile(user_id=user.id, ai_processing_consent=ai_consent, memory_enabled=True))
    db.session.add(StudentProgress(student_id=user.id))
    db.session.add(ConsentRecord(student_id=user.id, consent_type="terms", granted=True, version=TERMS_VERSION))
    db.session.add(ConsentRecord(student_id=user.id, consent_type="ai_processing", granted=ai_consent,
                                 version=AI_CONSENT_VERSION))
    return user


@bp.get("/csrf")
def csrf():
    return ok({"csrf_token": ensure_csrf_token()})


@bp.post("/register")
@limiter.limit("5 per hour; 20 per day")
def register():
    data = json_body()
    email = normalize_email(req_str(data, "email", max_len=254))
    password = validate_password(data.get("password"))
    name = req_str(data, "display_name", min_len=1, max_len=80, label="Name")
    if req_bool(data, "accept_terms", False) is not True:
        raise ApiError("Please read and accept how MindWell handles your data.", 422, "validation_error",
                       {"accept_terms": "required"})
    ai_consent = req_bool(data, "ai_processing_consent", False)
    if User.query.filter_by(email=email).first():
        raise ApiError("An account with this email already exists.", 409, "email_taken")
    user = create_student(email, password, name, ai_consent)
    user.last_login_at = utcnow()
    db.session.commit()
    login_user(user)
    return ok({"user": user_dict(user), "csrf_token": ensure_csrf_token()}, 201)


@bp.post("/login")
@limiter.limit("10 per minute; 60 per hour")
def login():
    data = json_body()
    email = (data.get("email") or "").strip().lower() if isinstance(data.get("email"), str) else ""
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    expected_role = data.get("role")
    user = User.query.filter_by(email=email).first() if email else None
    valid = check_password_hash(user.password_hash if user else _DUMMY_HASH, password)
    if not user or not valid or not user.is_active:
        raise ApiError("Email or password is incorrect.", 401, "invalid_credentials")
    if expected_role in ("student", "teacher") and user.role != expected_role:
        raise ApiError(f"This is a {user.role} account. Please use the {user.role} sign-in.", 403, "wrong_portal")
    user.last_login_at = utcnow()
    db.session.commit()
    login_user(user)
    return ok({"user": user_dict(user), "csrf_token": ensure_csrf_token()})


@bp.post("/logout")
def logout():
    logout_user()
    return ok({"csrf_token": ensure_csrf_token()})


@bp.get("/me")
@login_required
def me():
    return ok({"user": user_dict(g.user), "csrf_token": ensure_csrf_token()})
