"""Emergency-contact alerts.

Truthful status model (stored on EmergencyAlert.status):
  not_configured        no delivery provider is configured — NOTHING was sent
  dev_outbox            written to a local development file — NOTHING was sent
  accepted_by_provider  the email server / SMS provider accepted the message for delivery.
                        This is NOT confirmation that the contact received or read it.
  failed                every attempt failed — NOTHING was sent

The message contains only fields the student consented to (EmergencySharingPreference)
and never includes chat content, journal entries or wellness scores.
"""
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

import requests
from flask import current_app

from ..extensions import db
from ..models import EmergencyAlert, NotificationAttempt, utcnow
from ..utils import ApiError, local_tz, mask_email, mask_phone

log = logging.getLogger(__name__)

CONSENT_VERSION = "emergency-v1"


class PermanentFailure(Exception):
    pass


class TransientFailure(Exception):
    pass


# --- Composition -------------------------------------------------------------

def compose_message(student, contact, prefs, when=None):
    support = current_app.config["SUPPORT"]
    helpline = support["helpline"]
    when = when or datetime.now(timezone.utc)
    local = when.astimezone(local_tz()).strftime("%d %b %Y, %I:%M %p")

    who = student.display_name if prefs.share_name else "A MindWell user who listed you as a trusted contact"
    lines = [
        f"Hi {contact.name},",
        "",
        f"{who} has asked MindWell to let you know they would like support right now. "
        "Please try to reach out to them as soon as you can.",
        "",
        f"Alert started: {local} ({current_app.config['APP_TIMEZONE']})",
    ]
    if prefs.share_callback_phone and prefs.callback_phone_e164:
        lines.append(f"You can call them on: {prefs.callback_phone_e164}")
    if prefs.share_custom_note and prefs.custom_note:
        lines.append(f"Their message: \"{prefs.custom_note}\"")
    lines += [
        "",
        f"If you think they may be in immediate danger, call {support['emergency_services']['number']}.",
        f"{helpline['name']} (free, 24x7 mental-health support): {helpline['short_code']} or {helpline['toll_free']}.",
        "",
        "This alert was sent at their request by MindWell, a student wellbeing app. It does not include any of "
        "their conversations or health information. " + support["affiliation_disclaimer"],
    ]
    return "\n".join(lines)


# --- Providers ----------------------------------------------------------------

def email_configured(cfg):
    return cfg["NOTIFY_PROVIDER_EMAIL"] == "smtp" and bool(cfg["SMTP_HOST"] and cfg["SMTP_FROM"])


def sms_configured(cfg):
    return cfg["NOTIFY_PROVIDER_SMS"] == "twilio" and bool(
        cfg["TWILIO_ACCOUNT_SID"] and cfg["TWILIO_AUTH_TOKEN"] and cfg["TWILIO_FROM_NUMBER"])


def channel_status(cfg=None):
    cfg = cfg or current_app.config
    return {"email": email_configured(cfg), "sms": sms_configured(cfg), "dev_outbox": bool(cfg["NOTIFY_DEV_OUTBOX"])}


def send_email(cfg, to_addr, body):
    msg = EmailMessage()
    msg["Subject"] = "Someone you know has asked for support (MindWell)"
    msg["From"] = cfg["SMTP_FROM"]
    msg["To"] = to_addr
    msg.set_content(body)
    try:
        with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15) as smtp:
            if cfg["SMTP_USE_TLS"]:
                smtp.starttls()
            if cfg["SMTP_USERNAME"]:
                smtp.login(cfg["SMTP_USERNAME"], cfg["SMTP_PASSWORD"])
            refused = smtp.send_message(msg)
            if refused:
                raise PermanentFailure("recipient_refused")
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
        raise PermanentFailure("recipient_refused") from exc
    except smtplib.SMTPAuthenticationError as exc:
        raise PermanentFailure("smtp_auth_failed") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise TransientFailure(type(exc).__name__) from exc
    return None


def send_sms(cfg, to_number, body):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{cfg['TWILIO_ACCOUNT_SID']}/Messages.json"
    try:
        resp = requests.post(url, data={"To": to_number, "From": cfg["TWILIO_FROM_NUMBER"], "Body": body[:1500]},
                             auth=(cfg["TWILIO_ACCOUNT_SID"], cfg["TWILIO_AUTH_TOKEN"]), timeout=15)
    except requests.RequestException as exc:
        raise TransientFailure(type(exc).__name__) from exc
    if resp.status_code in (200, 201):
        return (resp.json() or {}).get("sid")
    if resp.status_code == 429 or resp.status_code >= 500:
        raise TransientFailure(f"http_{resp.status_code}")
    raise PermanentFailure(f"http_{resp.status_code}")


def write_dev_outbox(cfg, channel, destination, body):
    path = Path(cfg["NOTIFY_DEV_OUTBOX_PATH"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"===== DEV OUTBOX (NOT DELIVERED) {utcnow().isoformat()}Z channel={channel} to={destination}\n")
        fh.write(body + "\n\n")


# --- Orchestration --------------------------------------------------------------

def resolve_channel(contact):
    if contact.preferred_method == "email":
        if not contact.email:
            raise ApiError("Your contact has no email address saved.", 422, "no_destination")
        return "email", contact.email
    if contact.preferred_method == "sms":
        return "sms", contact.phone_e164
    raise ApiError("Your contact is set to 'call only', so MindWell can't send them a message. "
                   "You can change this in Emergency settings, or call them directly.", 422, "call_only")


def send_alert(student, contact, prefs, client_request_id):
    cfg = current_app.config
    existing = EmergencyAlert.query.filter_by(student_id=student.id, client_request_id=client_request_id).first()
    if existing:
        return existing, False

    window_start = utcnow() - timedelta(minutes=cfg["ALERT_COOLDOWN_MINUTES"])
    recent = (EmergencyAlert.query
              .filter(EmergencyAlert.student_id == student.id, EmergencyAlert.created_at >= window_start,
                      EmergencyAlert.status.in_(["accepted_by_provider", "dev_outbox"]))
              .order_by(EmergencyAlert.created_at.desc()).first())
    if recent:
        raise ApiError(f"An alert was already sent to your contact in the last {cfg['ALERT_COOLDOWN_MINUTES']} "
                       "minutes. Please call them or Tele-MANAS directly if you need help now.",
                       429, "alert_cooldown")

    channel, destination = resolve_channel(contact)
    masked = mask_email(destination) if channel == "email" else mask_phone(destination)
    body = compose_message(student, contact, prefs)
    alert = EmergencyAlert(student_id=student.id, client_request_id=client_request_id, channel=channel,
                           destination_masked=masked, trigger="student_manual", status="failed")
    db.session.add(alert)
    db.session.flush()

    configured = email_configured(cfg) if channel == "email" else sms_configured(cfg)
    if not configured:
        if cfg["NOTIFY_DEV_OUTBOX"]:
            write_dev_outbox(cfg, channel, masked, body)
            alert.status = "dev_outbox"
            db.session.add(NotificationAttempt(alert_id=alert.id, attempt_no=1, provider="dev_outbox",
                                               status="dev_outbox"))
        else:
            alert.status = "not_configured"
            db.session.add(NotificationAttempt(alert_id=alert.id, attempt_no=1, provider="none",
                                               status="not_configured", error_code="provider_not_configured"))
        db.session.commit()
        return alert, True

    sender = send_email if channel == "email" else send_sms
    provider = "smtp" if channel == "email" else "twilio"
    for attempt in range(1, cfg["NOTIFY_MAX_ATTEMPTS"] + 1):
        try:
            ref = sender(cfg, destination, body)
            db.session.add(NotificationAttempt(alert_id=alert.id, attempt_no=attempt, provider=provider,
                                               status="accepted_by_provider", provider_reference=ref))
            alert.status = "accepted_by_provider"
            break
        except PermanentFailure as exc:
            db.session.add(NotificationAttempt(alert_id=alert.id, attempt_no=attempt, provider=provider,
                                               status="failed", error_code=str(exc)[:60]))
            break
        except TransientFailure as exc:
            db.session.add(NotificationAttempt(alert_id=alert.id, attempt_no=attempt, provider=provider,
                                               status="failed", error_code=str(exc)[:60]))
            log.warning("Alert %s attempt %s transient failure", alert.id, attempt)
    db.session.commit()
    return alert, True


STATUS_TEXT = {
    "not_configured": "NOT SENT — no message provider is configured on this server. Please call your contact or a helpline instead.",
    "dev_outbox": "NOT SENT — development mode wrote the message to a local file only. Please call your contact or a helpline instead.",
    "accepted_by_provider": "Handed to the {channel} provider for delivery. MindWell cannot confirm your contact has received or read it — calling them is the most reliable option.",
    "failed": "NOT SENT — the provider returned an error. Please call your contact or a helpline instead.",
}


def alert_dict(alert):
    from ..utils import iso
    return {
        "id": alert.id,
        "channel": alert.channel,
        "destination": alert.destination_masked,
        "status": alert.status,
        "delivered_confirmed": False,
        "status_text": STATUS_TEXT[alert.status].format(channel=alert.channel),
        "created_at": iso(alert.created_at),
        "attempts": [{"attempt_no": a.attempt_no, "provider": a.provider, "status": a.status,
                      "error_code": a.error_code, "at": iso(a.created_at)} for a in alert.attempts],
    }
