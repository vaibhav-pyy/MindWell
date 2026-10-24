from flask import Blueprint, g
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, limiter
from ..models import (ActivityCompletion, CheckIn, Classroom, ClassMembership, ConsentRecord, Conversation,
                      EmergencyAlert, EmergencyContact, EmergencySharingPreference, JournalEntry, MemoryItem,
                      XPTransaction)
from ..security import login_required, logout_user, student_required
from ..utils import ApiError, iso, json_body, ok, req_bool, req_str
from .auth import AI_CONSENT_VERSION, user_dict, validate_password

bp = Blueprint("profile", __name__, url_prefix="/api")


@bp.get("/profile")
@login_required
def get_profile():
    data = user_dict(g.user)
    if g.user.role == "student":
        p = g.user.student_profile
        data.update({"pronouns": p.pronouns, "year_of_study": p.year_of_study})
    return ok(data)


@bp.patch("/profile")
@login_required
def update_profile():
    data = json_body()
    if "display_name" in data:
        g.user.display_name = req_str(data, "display_name", max_len=80, label="Name")
    if g.user.role == "student":
        p = g.user.student_profile
        if "pronouns" in data:
            p.pronouns = req_str(data, "pronouns", max_len=40, required=False)
        if "year_of_study" in data:
            p.year_of_study = req_str(data, "year_of_study", max_len=40, required=False)
    db.session.commit()
    return get_profile()


@bp.patch("/privacy")
@student_required
def update_privacy():
    data = json_body()
    p = g.user.student_profile
    changes = {
        "ai_processing_consent": ("ai_processing", AI_CONSENT_VERSION),
        "memory_enabled": ("memory", "memory-v1"),
        "personalize_with_checkins": ("personalize_with_checkins", "personalize-v1"),
    }
    for field, (consent_type, version) in changes.items():
        value = req_bool(data, field)
        if value is not None and value != getattr(p, field):
            setattr(p, field, value)
            db.session.add(ConsentRecord(student_id=g.user.id, consent_type=consent_type, granted=value,
                                         version=version))
    db.session.commit()
    return ok(user_dict(g.user)["privacy"])


@bp.get("/privacy/consents")
@student_required
def consent_history():
    rows = (ConsentRecord.query.filter_by(student_id=g.user.id)
            .order_by(ConsentRecord.created_at.desc()).limit(100).all())
    return ok([{"type": r.consent_type, "granted": r.granted, "version": r.version, "at": iso(r.created_at)}
               for r in rows])


@bp.post("/account/password")
@login_required
@limiter.limit("5 per hour")
def change_password():
    data = json_body()
    if not check_password_hash(g.user.password_hash, data.get("current_password") or ""):
        raise ApiError("Current password is incorrect.", 403, "invalid_credentials")
    g.user.password_hash = generate_password_hash(validate_password(data.get("new_password")))
    db.session.commit()
    return ok({"changed": True})


@bp.delete("/account")
@login_required
@limiter.limit("5 per hour")
def delete_account():
    """Permanently delete the account. ON DELETE CASCADE removes every owned record."""
    data = json_body()
    if not check_password_hash(g.user.password_hash, data.get("password") or ""):
        raise ApiError("Password is incorrect.", 403, "invalid_credentials")
    if data.get("confirm") != "DELETE":
        raise ApiError("Type DELETE to confirm.", 422, "validation_error")
    db.session.delete(g.user)
    db.session.commit()
    logout_user()
    return ok({"deleted": True})


@bp.get("/account/export")
@student_required
@limiter.limit("10 per hour")
def export_data():
    """Everything MindWell stores about the student, as JSON (data portability)."""
    sid = g.user.id
    p = g.user.student_profile
    contact = EmergencyContact.query.filter_by(student_id=sid).first()
    prefs = db.session.get(EmergencySharingPreference, sid)
    out = {
        "account": {"email": g.user.email, "display_name": g.user.display_name, "created_at": iso(g.user.created_at),
                    "pronouns": p.pronouns, "year_of_study": p.year_of_study},
        "privacy": user_dict(g.user)["privacy"],
        "consents": [{"type": r.consent_type, "granted": r.granted, "version": r.version, "at": iso(r.created_at)}
                     for r in ConsentRecord.query.filter_by(student_id=sid).all()],
        "conversations": [{"title": c.title, "created_at": iso(c.created_at),
                           "messages": [{"role": m.role, "source": m.source, "content": m.content,
                                         "at": iso(m.created_at)} for m in c.messages]}
                          for c in Conversation.query.filter_by(student_id=sid).all()],
        "memory": [{"kind": m.kind, "content": m.content, "at": iso(m.created_at)}
                   for m in MemoryItem.query.filter_by(student_id=sid).all()],
        "checkins": [{"date": c.checkin_date.isoformat(), "stress": c.stress, "anxiety": c.anxiety, "mood": c.mood,
                      "sleep_hours": c.sleep_hours, "sleep_quality": c.sleep_quality,
                      "academic_pressure": c.academic_pressure, "stressors": c.stressors, "note": c.note,
                      "wellness_index": c.wellness_index} for c in CheckIn.query.filter_by(student_id=sid).all()],
        "journal": [{"prompt": j.prompt, "content": j.content, "at": iso(j.created_at)}
                    for j in JournalEntry.query.filter_by(student_id=sid).all()],
        "activity_completions": [{"activity_id": a.activity_id, "date": a.completion_date.isoformat(),
                                  "xp": a.xp_awarded} for a in ActivityCompletion.query.filter_by(student_id=sid).all()],
        "xp_ledger": [{"amount": x.amount, "reason": x.reason, "at": iso(x.created_at)}
                      for x in XPTransaction.query.filter_by(student_id=sid).all()],
        "emergency_contact": None if not contact else {
            "name": contact.name, "relationship": contact.relationship, "phone": contact.phone_e164,
            "email": contact.email, "preferred_method": contact.preferred_method},
        "emergency_preferences": None if not prefs else {
            "alerts_enabled": prefs.alerts_enabled, "share_name": prefs.share_name,
            "share_callback_phone": prefs.share_callback_phone, "callback_phone": prefs.callback_phone_e164,
            "share_custom_note": prefs.share_custom_note, "custom_note": prefs.custom_note,
            "consented_at": iso(prefs.consented_at)},
        "emergency_alerts": [{"channel": a.channel, "status": a.status, "at": iso(a.created_at)}
                             for a in EmergencyAlert.query.filter_by(student_id=sid).all()],
        "classes": [{"class": c.name, "share_aggregates": m.share_aggregates, "joined_at": iso(m.joined_at)}
                    for m, c in db.session.query(ClassMembership, Classroom)
                    .join(Classroom, Classroom.id == ClassMembership.class_id)
                    .filter(ClassMembership.student_id == sid).all()],
    }
    return ok(out)


# --- Class membership (student side) ----------------------------------------------

def _membership_dict(m, c):
    return {"class_id": c.id, "name": c.name, "share_aggregates": m.share_aggregates, "joined_at": iso(m.joined_at)}


@bp.get("/classes/mine")
@student_required
def my_classes():
    rows = (db.session.query(ClassMembership, Classroom).join(Classroom, Classroom.id == ClassMembership.class_id)
            .filter(ClassMembership.student_id == g.user.id).all())
    return ok([_membership_dict(m, c) for m, c in rows])


@bp.post("/classes/join")
@student_required
@limiter.limit("20 per hour")
def join_class():
    data = json_body()
    code = req_str(data, "join_code", min_len=4, max_len=12, label="Join code").upper()
    share = req_bool(data, "share_aggregates", False)
    classroom = Classroom.query.filter_by(join_code=code).first()
    if classroom is None:
        raise ApiError("No class found with that code.", 404, "not_found")
    if ClassMembership.query.filter_by(class_id=classroom.id, student_id=g.user.id).first():
        raise ApiError("You're already in this class.", 409, "already_member")
    m = ClassMembership(class_id=classroom.id, student_id=g.user.id, share_aggregates=share)
    db.session.add(m)
    db.session.add(ConsentRecord(student_id=g.user.id, consent_type=f"class_aggregates:{classroom.id}",
                                 granted=share, version="aggregates-v1"))
    db.session.commit()
    return ok(_membership_dict(m, classroom), 201)


def _own_membership(class_id):
    row = (db.session.query(ClassMembership, Classroom).join(Classroom, Classroom.id == ClassMembership.class_id)
           .filter(ClassMembership.student_id == g.user.id, ClassMembership.class_id == class_id).first())
    if row is None:
        raise ApiError("Class membership not found.", 404, "not_found")
    return row


@bp.patch("/classes/<int:class_id>/sharing")
@student_required
def update_sharing(class_id):
    m, c = _own_membership(class_id)
    share = req_bool(json_body(), "share_aggregates")
    if share is None:
        raise ApiError("share_aggregates is required.", 422, "validation_error")
    m.share_aggregates = share
    db.session.add(ConsentRecord(student_id=g.user.id, consent_type=f"class_aggregates:{c.id}",
                                 granted=share, version="aggregates-v1"))
    db.session.commit()
    return ok(_membership_dict(m, c))


@bp.delete("/classes/<int:class_id>/membership")
@student_required
def leave_class(class_id):
    m, _ = _own_membership(class_id)
    db.session.delete(m)
    db.session.commit()
    return ok({"left": True})

