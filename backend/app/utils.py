"""Response helpers, request validation and local-time helpers."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import phonenumbers
from email_validator import EmailNotValidError, validate_email
from flask import current_app, jsonify, request


class ApiError(Exception):
    def __init__(self, message, status=400, code="bad_request", details=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.details = details


def ok(data=None, status=200):
    return jsonify({"ok": True, "data": data}), status


def error_response(message, status, code, details=None):
    body = {"ok": False, "error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object.", 400, "invalid_json")
    return data


# --- Field validators ------------------------------------------------------

def req_str(data, key, *, min_len=1, max_len=200, required=True, label=None):
    label = label or key
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ApiError(f"{label} is required.", 422, "validation_error", {key: "required"})
        return None
    if not isinstance(value, str):
        raise ApiError(f"{label} must be text.", 422, "validation_error", {key: "type"})
    value = value.strip()
    if len(value) < min_len or len(value) > max_len:
        raise ApiError(f"{label} must be between {min_len} and {max_len} characters.", 422,
                       "validation_error", {key: "length"})
    return value


def req_bool(data, key, default=None):
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ApiError(f"{key} must be true or false.", 422, "validation_error", {key: "type"})
    return value


def opt_int(data, key, lo, hi):
    value = data.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ApiError(f"{key} must be a whole number.", 422, "validation_error", {key: "type"})
    value = int(value)
    if not lo <= value <= hi:
        raise ApiError(f"{key} must be between {lo} and {hi}.", 422, "validation_error", {key: "range"})
    return value


def opt_float(data, key, lo, hi):
    value = data.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiError(f"{key} must be a number.", 422, "validation_error", {key: "type"})
    if not lo <= value <= hi:
        raise ApiError(f"{key} must be between {lo} and {hi}.", 422, "validation_error", {key: "range"})
    return round(float(value), 1)


def normalize_email(value, key="email"):
    try:
        return validate_email(value, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise ApiError("Please enter a valid email address.", 422, "validation_error", {key: "invalid"})


def normalize_phone(value, key="phone"):
    """Return the number in E.164 form or raise. Accepts local Indian numbers by default."""
    if not isinstance(value, str) or not value.strip():
        raise ApiError("A phone number is required.", 422, "validation_error", {key: "required"})
    try:
        parsed = phonenumbers.parse(value.strip(), current_app.config["DEFAULT_PHONE_REGION"])
    except phonenumbers.NumberParseException:
        raise ApiError("Please enter a valid phone number.", 422, "validation_error", {key: "invalid"})
    if not phonenumbers.is_valid_number(parsed):
        raise ApiError("Please enter a valid phone number.", 422, "validation_error", {key: "invalid"})
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def mask_phone(e164):
    return e164[:3] + "•" * max(0, len(e164) - 6) + e164[-3:] if e164 else ""


def mask_email(email):
    if not email or "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    return f"{local[:1]}•••@{domain}"


# --- Time ------------------------------------------------------------------

def local_tz():
    return ZoneInfo(current_app.config["APP_TIMEZONE"])


def local_today() -> date:
    return datetime.now(local_tz()).date()


def to_local_date(utc_naive: datetime) -> date:
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(local_tz()).date()


def iso(dt):
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    return dt.isoformat()


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())
