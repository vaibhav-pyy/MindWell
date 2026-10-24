"""Emergency contact & alerts — accessible ONLY to the owning student (no teacher routes touch these tables)."""
import re

from flask import Blueprint, current_app, g

from ..extensions import db, limiter, user_or_ip
from ..models import (NOTIFY_METHODS, ConsentRecord, EmergencyAlert, EmergencyContact,
                      EmergencySharingPreference, utcnow)
from ..security import student_required
from ..services import notifications
from ..utils import ApiError, iso, json_body, mask_email, mask_phone, normalize_email, normalize_phone, ok, \
    req_bool, req_str

bp = Blueprint("emergency", __name__, url_prefix="/api/emergency")

SHARING_EXPLANATION = {
    "what": "Only what you switch on below: your name, a callback phone number, and a short note you write. "
            "Plus the time of the alert and helpline numbers. Never your chats, journal, check-ins or scores.",
    "who": "Only the one trusted contact you saved here.",
    "channel": "The method you choose for that contact (email or SMS), and only if this server has that "
               "provider configured. Otherwise nothing is sent and you'll be told so.",
    "when": "Only when you press 'Send alert' and confirm. MindWell never sends alerts automatically — not "
            "from chat messages, low scores or inactivity.",
    "limits": "MindWell cannot confirm that your contact received or read a message, and it is not an "
              "emergency service. In immediate danger call 112. Calling someone directly is always faster.",
}


def contact_dict(c):
    if c is None:
        return None
    return {"id": c.id, "name": c.name, "relationship": c.relationship, "phone": c.phone_e164,
            "tel_href": f"tel:{c.phone_e164}", "email": c.email, "preferred_method": c.preferred_method,
            "updated_at": iso(c.updated_at)}


def prefs_dict(p):
    if p is None:
        return {"alerts_enabled": False, "share_name": True, "share_callback_phone": False, "callback_phone": None,
                "share_custom_note": False, "custom_note": None, "consented_at": None}
    return {"alerts_enabled": p.alerts_enabled, "share_name": p.share_name,
            "share_callback_phone": p.share_callback_phone, "callback_phone": p.callback_phone_e164,
            "share_custom_note": p.share_custom_note, "custom_note": p.custom_note,
            "consented_at": iso(p.consented_at)}


def _contact():
    return EmergencyContact.query.filter_by(student_id=g.user.id).first()


@bp.get("")
@student_required
def overview():
    return ok({
        "contact": contact_dict(_contact()),
        "preferences": prefs_dict(db.session.get(EmergencySharingPreference, g.user.id)),
        "channels_configured": notifications.channel_status(),
        "explanation": SHARING_EXPLANATION,
        "support": current_app.config["SUPPORT"],
    })


@bp.put("/contact")
@student_required
@limiter.limit("30 per hour", key_func=user_or_ip)
def save_contact():
    data = json_body()
    name = req_str(data, "name", max_len=80, label="Contact name")
    relationship = req_str(data, "relationship", max_len=40, label="Relationship")
    phone = normalize_phone(data.get("phone"))
    email = data.get("email")
    email = normalize_email(email) if isinstance(email, str) and email.strip() else None
    method = data.get("preferred_method", "call_only")
    if method not in NOTIFY_METHODS:
        raise ApiError("Unknown notification method.", 422, "validation_error", {"preferred_method": "invalid"})
    if method == "email" and not email:
        raise ApiError("Add an email address to use email alerts.", 422, "validation_error", {"email": "required"})
    if req_bool(data, "confirm", False) is not True:
        raise ApiError("Please confirm this person has agreed to be your emergency contact.", 422,
                       "validation_error", {"confirm": "required"})
    if re.sub(r"\D", "", phone) == re.sub(r"\D", "", current_app.config["SUPPORT"]["helpline"]["short_code"]):
        raise ApiError("Please enter a personal contact's number.", 422, "validation_error")

    c = _contact()
    if c is None:
        c = EmergencyContact(student_id=g.user.id)
        db.session.add(c)
    c.name, c.relationship, c.phone_e164, c.email, c.preferred_method = name, relationship, phone, email, method
    db.session.add(ConsentRecord(student_id=g.user.id, consent_type="emergency_contact_saved", granted=True,
                                 version=notifications.CONSENT_VERSION))
    db.session.commit()
    return ok(contact_dict(c))


@bp.delete("/contact")
@student_required
def delete_contact():
    c = _contact()
    if c is None:
        raise ApiError("No emergency contact saved.", 404, "not_found")
    db.session.delete(c)
    prefs = db.session.get(EmergencySharingPreference, g.user.id)
    if prefs:
        prefs.alerts_enabled = False
    db.session.add(ConsentRecord(student_id=g.user.id, consent_type="emergency_contact_saved", granted=False,
                                 version=notifications.CONSENT_VERSION))
    db.session.commit()
    return ok({"deleted": True})


@bp.put("/preferences")
@student_required
def save_preferences():
    data = json_body()
    p = db.session.get(EmergencySharingPreference, g.user.id)
    if p is None:
        p = EmergencySharingPreference(student_id=g.user.id)
        db.session.add(p)
    alerts_enabled = req_bool(data, "alerts_enabled", False)
    if alerts_enabled and _contact() is None:
        raise ApiError("Save an emergency contact first.", 422, "no_contact")
    if alerts_enabled and req_bool(data, "consent", False) is not True:
        raise ApiError("Please confirm you understand and agree to what will be shared.", 422,
                       "validation_error", {"consent": "required"})
    p.share_name = req_bool(data, "share_name", True)
    p.share_callback_phone = req_bool(data, "share_callback_phone", False)
    if p.share_callback_phone:
        p.callback_phone_e164 = normalize_phone(data.get("callback_phone"), key="callback_phone")
    else:
        p.callback_phone_e164 = None
    p.share_custom_note = req_bool(data, "share_custom_note", False)
    p.custom_note = req_str(data, "custom_note", max_len=200, required=p.share_custom_note,
                            label="Your note") if p.share_custom_note else None
    if alerts_enabled != p.alerts_enabled or alerts_enabled:
        db.session.add(ConsentRecord(student_id=g.user.id, consent_type="emergency_sharing",
                                     granted=alerts_enabled, version=notifications.CONSENT_VERSION))
    p.alerts_enabled = alerts_enabled
    if alerts_enabled:
        p.consent_version = notifications.CONSENT_VERSION
        p.consented_at = utcnow()
    db.session.commit()
    return ok(prefs_dict(p))


def _ready():
    contact = _contact()
    prefs = db.session.get(EmergencySharingPreference, g.user.id)
    if contact is None:
        raise ApiError("You haven't saved an emergency contact yet.", 422, "no_contact")
    if prefs is None or not prefs.alerts_enabled:
        raise ApiError("Emergency message sharing is turned off. You can still call your contact or a helpline.",
                       403, "alerts_disabled")
    return contact, prefs


@bp.get("/alert-preview")
@student_required
def alert_preview():
    contact, prefs = _ready()
    channel, destination = notifications.resolve_channel(contact)
    cfg = current_app.config
    configured = (notifications.email_configured(cfg) if channel == "email" else notifications.sms_configured(cfg))
    return ok({
        "channel": channel,
        "destination": mask_email(destination) if channel == "email" else mask_phone(destination),
        "contact_name": contact.name,
        "message": notifications.compose_message(g.user, contact, prefs),
        "provider_configured": configured,
        "dev_outbox": bool(cfg["NOTIFY_DEV_OUTBOX"]) and not configured,
    })


@bp.post("/alerts")
@student_required
@limiter.limit("5 per hour; 10 per day", key_func=user_or_ip)
def send_alert():
    data = json_body()
    if req_bool(data, "confirm", False) is not True:
        raise ApiError("Please confirm before sending.", 422, "validation_error", {"confirm": "required"})
    request_id = req_str(data, "client_request_id", min_len=8, max_len=64, label="Request id")
    contact, prefs = _ready()
    alert, created = notifications.send_alert(g.user, contact, prefs, request_id)
    return ok({"alert": notifications.alert_dict(alert), "duplicate_request": not created}, 201 if created else 200)


@bp.get("/alerts")
@student_required
def list_alerts():
    rows = (EmergencyAlert.query.filter_by(student_id=g.user.id).order_by(EmergencyAlert.created_at.desc())
            .limit(20).all())
    return ok([notifications.alert_dict(a) for a in rows])
