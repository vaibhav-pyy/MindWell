"""Relational schema (MySQL 8, InnoDB, utf8mb4).

Enumerated values are stored as short VARCHARs validated in application code and
constrained by CHECK constraints, which keeps the schema portable to the SQLite
database used by the automated tests.

Ownership rule: every student-private table carries ``student_id`` with
``ON DELETE CASCADE`` so deleting an account removes all of that student's data.
"""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _in(table, col, values):
    quoted = ",".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{col} IN ({quoted})", name=f"ck_{table}_{col}")


FK_USER = "users.id"
ROLES = ("student", "teacher")


# ---------------------------------------------------------------------------
# Users and roles
# ---------------------------------------------------------------------------
class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (_in("users", "role", ROLES),)

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_demo = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_login_at = db.Column(db.DateTime)

    student_profile = db.relationship("StudentProfile", uselist=False, back_populates="user",
                                      cascade="all, delete-orphan", passive_deletes=True)


class StudentProfile(db.Model):
    __tablename__ = "student_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), primary_key=True)
    pronouns = db.Column(db.String(40))
    year_of_study = db.Column(db.String(40))
    # Consent flags (history of changes lives in consent_records)
    ai_processing_consent = db.Column(db.Boolean, nullable=False, default=False)
    memory_enabled = db.Column(db.Boolean, nullable=False, default=True)
    personalize_with_checkins = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="student_profile")


class TeacherProfile(db.Model):
    __tablename__ = "teacher_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), primary_key=True)
    department = db.Column(db.String(120))


class ConsentRecord(db.Model):
    """Append-only audit trail of consent decisions (what, granted?, text version, when)."""
    __tablename__ = "consent_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False, index=True)
    consent_type = db.Column(db.String(40), nullable=False)
    granted = db.Column(db.Boolean, nullable=False)
    version = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------
class Classroom(db.Model):
    __tablename__ = "classrooms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False, index=True)
    join_code = db.Column(db.String(12), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class ClassMembership(db.Model):
    __tablename__ = "class_memberships"
    __table_args__ = (UniqueConstraint("class_id", "student_id", name="uq_class_student"),)

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False, index=True)
    # Student explicitly opts in to contributing de-identified check-in numbers to class aggregates.
    share_aggregates = db.Column(db.Boolean, nullable=False, default=False)
    joined_at = db.Column(db.DateTime, nullable=False, default=utcnow)


# ---------------------------------------------------------------------------
# Conversations and memory
# ---------------------------------------------------------------------------
MESSAGE_ROLES = ("user", "assistant")
MESSAGE_SOURCES = ("student", "gemini", "safety_template")
SAFETY_LEVELS = ("none", "concern", "crisis")


class Conversation(db.Model):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conv_student_updated", "student_id", "updated_at"),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(120), nullable=False, default="New conversation")
    summarized_through_message_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    messages = db.relationship("Message", backref="conversation", cascade="all, delete-orphan",
                               passive_deletes=True, order_by="Message.id")


class Message(db.Model):
    __tablename__ = "messages"
    __table_args__ = (_in("messages", "role", MESSAGE_ROLES), _in("messages", "source", MESSAGE_SOURCES),
                      _in("messages", "safety_level", SAFETY_LEVELS))

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id", ondelete="CASCADE"),
                                nullable=False, index=True)
    role = db.Column(db.String(16), nullable=False)
    source = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    safety_level = db.Column(db.String(10), nullable=False, default="none")
    suggested_activity_ids = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


MEMORY_KINDS = ("student_note", "ai_summary")


class MemoryItem(db.Model):
    """What MindWell may remember across conversations.

    ``student_note``: written by the student, verbatim ("what I told MindWell").
    ``ai_summary``: generated by Gemini from a conversation; always labelled as an AI interpretation.
    """
    __tablename__ = "memory_items"
    __table_args__ = (_in("memory_items", "kind", MEMORY_KINDS), Index("ix_memory_student_created", "student_id", "created_at"))

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False)
    kind = db.Column(db.String(16), nullable=False)
    content = db.Column(db.String(1000), nullable=False)
    source_conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


# ---------------------------------------------------------------------------
# Wellness check-ins (self-report) — the only input to the wellness indicators
# ---------------------------------------------------------------------------
class CheckIn(db.Model):
    __tablename__ = "checkins"
    __table_args__ = (
        UniqueConstraint("student_id", "checkin_date", name="uq_checkin_student_day"),
        CheckConstraint("stress IS NULL OR (stress BETWEEN 1 AND 5)", name="ck_checkins_stress"),
        CheckConstraint("anxiety IS NULL OR (anxiety BETWEEN 1 AND 5)", name="ck_checkins_anxiety"),
        CheckConstraint("mood IS NULL OR (mood BETWEEN 1 AND 5)", name="ck_checkins_mood"),
        CheckConstraint("sleep_quality IS NULL OR (sleep_quality BETWEEN 1 AND 5)", name="ck_checkins_sleep_quality"),
        CheckConstraint("sleep_hours IS NULL OR (sleep_hours BETWEEN 0 AND 16)", name="ck_checkins_sleep_hours"),
        CheckConstraint("academic_pressure IS NULL OR (academic_pressure BETWEEN 1 AND 5)", name="ck_checkins_academic"),
        Index("ix_checkin_student_date", "student_id", "checkin_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False)
    checkin_date = db.Column(db.Date, nullable=False)  # local date (APP_TIMEZONE)
    stress = db.Column(db.SmallInteger)
    anxiety = db.Column(db.SmallInteger)
    mood = db.Column(db.SmallInteger)
    sleep_hours = db.Column(db.Float)
    sleep_quality = db.Column(db.SmallInteger)
    academic_pressure = db.Column(db.SmallInteger)
    stressors = db.Column(db.JSON)  # list of fixed category codes
    note = db.Column(db.String(1000))  # private; never sent to teachers
    # Derived values (deterministic, recomputed whenever the inputs change)
    stress_level = db.Column(db.Float)
    anxiety_level = db.Column(db.Float)
    mood_level = db.Column(db.Float)
    sleep_score = db.Column(db.Float)
    academic_pressure_level = db.Column(db.Float)
    wellness_index = db.Column(db.Float)
    items_answered = db.Column(db.SmallInteger, nullable=False, default=0)
    scoring_version = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------------------
# Activities, recommendations, sessions and completions
# ---------------------------------------------------------------------------
ACTIVITY_KINDS = ("breathing", "journal", "guided_steps")
ACTIVITY_CATEGORIES = ("breathing", "mindfulness", "journaling", "gratitude", "movement",
                       "study_break", "relaxation", "sleep", "time_management")
DIFFICULTIES = ("easy", "moderate")


class Activity(db.Model):
    __tablename__ = "activities"
    __table_args__ = (_in("activities", "kind", ACTIVITY_KINDS), _in("activities", "category", ACTIVITY_CATEGORIES),
                      _in("activities", "difficulty", DIFFICULTIES),
                      CheckConstraint("duration_minutes BETWEEN 1 AND 30", name="ck_activities_duration"))

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(64), unique=True)  # built-in catalog only
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(400), nullable=False)
    category = db.Column(db.String(20), nullable=False, index=True)
    kind = db.Column(db.String(16), nullable=False)
    instructions = db.Column(db.JSON, nullable=False)  # list of step strings
    config = db.Column(db.JSON)  # kind-specific (breathing pattern, journal prompts)
    duration_minutes = db.Column(db.SmallInteger, nullable=False)
    difficulty = db.Column(db.String(10), nullable=False, default="easy")
    completion_criteria = db.Column(db.String(300), nullable=False)
    xp_reward = db.Column(db.SmallInteger, nullable=False)  # always computed by the backend
    safety_notes = db.Column(db.String(300))
    source = db.Column(db.String(10), nullable=False, default="builtin")  # builtin | ai
    owner_student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


REC_STATUSES = ("suggested", "dismissed", "completed")


class ActivityRecommendation(db.Model):
    __tablename__ = "activity_recommendations"
    __table_args__ = (
        _in("activity_recommendations", "status", REC_STATUSES),
        UniqueConstraint("student_id", "activity_id", "for_date", name="uq_rec_student_activity_day"),
        Index("ix_rec_student_date", "student_id", "for_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False)
    for_date = db.Column(db.Date, nullable=False)
    source = db.Column(db.String(10), nullable=False)  # rule | ai | chat
    reason = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(10), nullable=False, default="suggested")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class ActivitySession(db.Model):
    """Started on the server so completion time can be validated; completes at most once."""
    __tablename__ = "activity_sessions"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False, index=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    completed_at = db.Column(db.DateTime)


class ActivityCompletion(db.Model):
    __tablename__ = "activity_completions"
    __table_args__ = (Index("ix_completion_student_date", "student_id", "completion_date"),)

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("activity_sessions.id", ondelete="CASCADE"),
                           nullable=False, unique=True)  # one completion per session
    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True)
    completion_date = db.Column(db.Date, nullable=False)
    elapsed_seconds = db.Column(db.Integer, nullable=False)
    xp_awarded = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class JournalEntry(db.Model):
    """Only stored when the student ticks "save to my private journal"."""
    __tablename__ = "journal_entries"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False, index=True)
    completion_id = db.Column(db.Integer, db.ForeignKey("activity_completions.id", ondelete="SET NULL"))
    prompt = db.Column(db.String(300))
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


# ---------------------------------------------------------------------------
# Gamification
# ---------------------------------------------------------------------------
class XPTransaction(db.Model):
    """Ledger of XP. The unique (source_type, source_id) pair makes awards idempotent."""
    __tablename__ = "xp_transactions"
    __table_args__ = (UniqueConstraint("source_type", "source_id", name="uq_xp_source"),
                      Index("ix_xp_student_created", "student_id", "created_at"))

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(120), nullable=False)
    source_type = db.Column(db.String(20), nullable=False)  # checkin | activity
    source_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class StudentProgress(db.Model):
    """Cached totals derived from the XP ledger and activity days."""
    __tablename__ = "student_progress"

    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), primary_key=True)
    total_xp = db.Column(db.Integer, nullable=False, default=0)
    current_streak = db.Column(db.Integer, nullable=False, default=0)
    longest_streak = db.Column(db.Integer, nullable=False, default=0)
    last_active_date = db.Column(db.Date)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class Badge(db.Model):
    __tablename__ = "badges"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), nullable=False, unique=True)
    name = db.Column(db.String(60), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    icon = db.Column(db.String(20), nullable=False)


class StudentBadge(db.Model):
    __tablename__ = "student_badges"
    __table_args__ = (UniqueConstraint("student_id", "badge_id", name="uq_student_badge"),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False, index=True)
    badge_id = db.Column(db.Integer, db.ForeignKey("badges.id", ondelete="CASCADE"), nullable=False)
    earned_at = db.Column(db.DateTime, nullable=False, default=utcnow)


# ---------------------------------------------------------------------------
# Emergency support
# ---------------------------------------------------------------------------
NOTIFY_METHODS = ("call_only", "email", "sms")


class EmergencyContact(db.Model):
    __tablename__ = "emergency_contacts"
    __table_args__ = (_in("emergency_contacts", "preferred_method", NOTIFY_METHODS),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False, unique=True)
    name = db.Column(db.String(80), nullable=False)
    relationship = db.Column(db.String(40), nullable=False)
    phone_e164 = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(254))
    preferred_method = db.Column(db.String(10), nullable=False, default="call_only")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class EmergencySharingPreference(db.Model):
    """Exactly which fields may appear in an alert. Enforced server-side when composing it."""
    __tablename__ = "emergency_sharing_preferences"

    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), primary_key=True)
    alerts_enabled = db.Column(db.Boolean, nullable=False, default=False)
    share_name = db.Column(db.Boolean, nullable=False, default=True)
    share_callback_phone = db.Column(db.Boolean, nullable=False, default=False)
    callback_phone_e164 = db.Column(db.String(20))
    share_custom_note = db.Column(db.Boolean, nullable=False, default=False)
    custom_note = db.Column(db.String(200))
    consent_version = db.Column(db.String(20))
    consented_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


ALERT_STATUSES = ("not_configured", "dev_outbox", "accepted_by_provider", "failed")


class EmergencyAlert(db.Model):
    """A student-initiated request to notify their contact. Status never claims delivery."""
    __tablename__ = "emergency_alerts"
    __table_args__ = (_in("emergency_alerts", "status", ALERT_STATUSES),
                      UniqueConstraint("student_id", "client_request_id", name="uq_alert_request"),
                      Index("ix_alert_student_created", "student_id", "created_at"))

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey(FK_USER, ondelete="CASCADE"), nullable=False)
    client_request_id = db.Column(db.String(64), nullable=False)
    channel = db.Column(db.String(10), nullable=False)
    destination_masked = db.Column(db.String(60), nullable=False)  # never the full address
    trigger = db.Column(db.String(20), nullable=False, default="student_manual")
    status = db.Column(db.String(24), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    attempts = db.relationship("NotificationAttempt", backref="alert", cascade="all, delete-orphan",
                               passive_deletes=True, order_by="NotificationAttempt.id")


class NotificationAttempt(db.Model):
    __tablename__ = "notification_attempts"

    id = db.Column(db.Integer, primary_key=True)
    alert_id = db.Column(db.Integer, db.ForeignKey("emergency_alerts.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_no = db.Column(db.SmallInteger, nullable=False)
    provider = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(24), nullable=False)
    provider_reference = db.Column(db.String(100))
    error_code = db.Column(db.String(60))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


# ---------------------------------------------------------------------------
# Class insights (aggregate only)
# ---------------------------------------------------------------------------
class ClassInsight(db.Model):
    __tablename__ = "class_insights"

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True)
    period_weeks = db.Column(db.SmallInteger, nullable=False)
    statistics = db.Column(db.JSON, nullable=False)  # the aggregate input, already suppressed
    observations = db.Column(db.JSON, nullable=False)  # rule-based, computed from statistics
    ai_narrative = db.Column(db.JSON)  # Gemini output (validated) or null
    ai_status = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
