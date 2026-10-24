"""Application configuration. Every secret and tunable comes from environment variables."""
import json
import os
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUPPORT_CONFIG_PATH = PROJECT_ROOT / "shared" / "support-config.json"


def _bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def load_support_config():
    with open(SUPPORT_CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def build_database_uri():
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    user = os.environ.get("MYSQL_USER", "mindwell")
    password = os.environ.get("MYSQL_PASSWORD", "")
    host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    port = os.environ.get("MYSQL_PORT", "3306")
    name = os.environ.get("MYSQL_DATABASE", "mindwell")
    from urllib.parse import quote_plus
    return f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}?charset=utf8mb4"


class Config:
    # --- Core -------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY")
    APP_ENV = os.environ.get("APP_ENV", "development")
    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Kolkata")
    FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")

    # --- Database ---------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # --- Sessions (cookie based, HttpOnly, CSRF header required for writes) -
    SESSION_COOKIE_NAME = "mindwell_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)  # set true behind HTTPS
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int("SESSION_LIFETIME_HOURS", 8))
    SESSION_IDLE_MINUTES = _int("SESSION_IDLE_MINUTES", 60)

    # --- Rate limiting ----------------------------------------------------
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_ENABLED = _bool("RATELIMIT_ENABLED", True)
    RATELIMIT_HEADERS_ENABLED = True

    # --- Gemini -----------------------------------------------------------
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "")
    GEMINI_TIMEOUT_SECONDS = _int("GEMINI_TIMEOUT_SECONDS", 30)
    GEMINI_MAX_RETRIES = _int("GEMINI_MAX_RETRIES", 2)
    GEMINI_THINKING_LEVEL = os.environ.get("GEMINI_THINKING_LEVEL", "low")  # minimal|low|medium|high, empty = model default
    CHAT_CONTEXT_MESSAGES = _int("CHAT_CONTEXT_MESSAGES", 12)  # bounded window sent to Gemini
    MEMORY_SUMMARIES_IN_CONTEXT = _int("MEMORY_SUMMARIES_IN_CONTEXT", 3)
    MAX_MESSAGE_CHARS = _int("MAX_MESSAGE_CHARS", 2000)

    # --- Gamification (rewards are configurable, never set by the AI) ------
    XP_CHECKIN = _int("XP_CHECKIN", 10)
    XP_PER_ACTIVITY_MINUTE = _int("XP_PER_ACTIVITY_MINUTE", 3)
    XP_ACTIVITY_MIN = _int("XP_ACTIVITY_MIN", 5)
    XP_ACTIVITY_MAX = _int("XP_ACTIVITY_MAX", 40)
    XP_AWARDS_PER_ACTIVITY_PER_DAY = _int("XP_AWARDS_PER_ACTIVITY_PER_DAY", 2)
    LEVEL_XP_STEP = _int("LEVEL_XP_STEP", 25)  # XP to reach level L = STEP * L * (L - 1)
    ACTIVITY_MIN_COMPLETION_RATIO = float(os.environ.get("ACTIVITY_MIN_COMPLETION_RATIO", "0.6"))

    # --- Teacher analytics privacy ---------------------------------------
    MIN_COHORT_SIZE = max(3, _int("MIN_COHORT_SIZE", 5))

    # --- Emergency notifications -----------------------------------------
    NOTIFY_PROVIDER_EMAIL = os.environ.get("NOTIFY_PROVIDER_EMAIL", "")  # "smtp" or empty
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = _int("SMTP_PORT", 587)
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_USE_TLS = _bool("SMTP_USE_TLS", True)
    SMTP_FROM = os.environ.get("SMTP_FROM", "")
    NOTIFY_PROVIDER_SMS = os.environ.get("NOTIFY_PROVIDER_SMS", "")  # "twilio" or empty
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")
    NOTIFY_DEV_OUTBOX = _bool("NOTIFY_DEV_OUTBOX", False)  # writes to a local file, NOT delivered
    NOTIFY_DEV_OUTBOX_PATH = os.environ.get("NOTIFY_DEV_OUTBOX_PATH", str(PROJECT_ROOT / "backend" / "instance" / "dev_outbox.log"))
    ALERT_COOLDOWN_MINUTES = _int("ALERT_COOLDOWN_MINUTES", 10)
    NOTIFY_MAX_ATTEMPTS = _int("NOTIFY_MAX_ATTEMPTS", 2)
    DEFAULT_PHONE_REGION = os.environ.get("DEFAULT_PHONE_REGION", "IN")

    # --- Retention (enforced by `flask purge-expired`) --------------------
    CHAT_RETENTION_DAYS = _int("CHAT_RETENTION_DAYS", 180)
    ALERT_LOG_RETENTION_DAYS = _int("ALERT_LOG_RETENTION_DAYS", 90)

    SUPPORT = load_support_config()


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key-not-for-production"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    RATELIMIT_ENABLED = False
    GEMINI_API_KEY = ""
    NOTIFY_PROVIDER_EMAIL = ""
    NOTIFY_PROVIDER_SMS = ""
    NOTIFY_DEV_OUTBOX = False
