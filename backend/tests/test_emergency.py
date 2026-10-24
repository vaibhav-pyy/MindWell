import json

import pytest

from app.models import EmergencyAlert, EmergencyContact
from app.services import notifications

CONTACT = {"name": "Priya Sharma", "relationship": "Sister", "phone": "98765 43210", "email": "priya@example.com",
           "preferred_method": "email", "confirm": True}


def _setup(client, **prefs):
    assert client.put("/api/emergency/contact", CONTACT).status_code == 200
    body = {"alerts_enabled": True, "consent": True, "share_name": True, **prefs}
    r = client.put("/api/emergency/preferences", body)
    assert r.status_code == 200, r.get_json()


def test_contact_crud_and_tel_link(register_student):
    s = register_student()
    r = s.put("/api/emergency/contact", CONTACT)
    c = r.get_json()["data"]
    assert c["phone"] == "+919876543210" and c["tel_href"] == "tel:+919876543210"
    r = s.put("/api/emergency/contact", {**CONTACT, "name": "Priya S"})
    assert r.get_json()["data"]["name"] == "Priya S"
    assert EmergencyContact.query.count() == 1
    assert s.get("/api/emergency").get_json()["data"]["contact"]["tel_href"] == "tel:+919876543210"
    assert s.delete("/api/emergency/contact").status_code == 200
    assert s.get("/api/emergency").get_json()["data"]["contact"] is None


@pytest.mark.parametrize("override", [
    {"phone": "123"}, {"phone": "not a phone"}, {"email": "bad@"}, {"preferred_method": "carrier-pigeon"},
    {"name": ""}, {"confirm": False}, {"preferred_method": "email", "email": ""},
])
def test_invalid_contact_rejected(register_student, override):
    s = register_student()
    assert s.put("/api/emergency/contact", {**CONTACT, **override}).status_code == 422


def test_contact_private_to_owner(register_student, teacher_client):
    a = register_student()
    b = register_student()
    a.put("/api/emergency/contact", CONTACT)
    assert b.get("/api/emergency").get_json()["data"]["contact"] is None
    assert b.delete("/api/emergency/contact").status_code == 404
    t = teacher_client()
    assert t.get("/api/emergency").status_code == 403
    assert t.get("/api/emergency/alerts").status_code == 403


def test_helpline_public_without_login(make_client):
    data = make_client().get("/api/public/support").get_json()["data"]
    assert data["helpline"]["short_code"] == "14416"
    assert data["helpline"]["toll_free"] == "1800-891-4416"


def test_alerts_require_consent(register_student):
    s = register_student()
    s.put("/api/emergency/contact", CONTACT)
    assert s.put("/api/emergency/preferences", {"alerts_enabled": True}).status_code == 422  # consent missing
    r = s.post("/api/emergency/alerts", {"client_request_id": "req-00000001", "confirm": True})
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "alerts_disabled"


def test_message_contains_only_authorised_fields(register_student, fake_ai):
    s = register_student(name="Ravi Kumar")
    s.post("/api/checkins", {"stress": 5, "mood": 1, "anxiety": 5, "note": "PRIVATE-NOTE"})
    s.post("/api/memory", {"content": "PRIVATE-MEMORY"})
    _setup(s, share_name=False, share_callback_phone=False)
    msg = s.get("/api/emergency/alert-preview").get_json()["data"]["message"]
    assert "Ravi" not in msg and "PRIVATE" not in msg and "+91" not in msg
    assert "14416" in msg and "112" in msg
    _setup(s, share_name=True, share_callback_phone=True, callback_phone="9123456780",
           share_custom_note=True, custom_note="Please call me")
    msg = s.get("/api/emergency/alert-preview").get_json()["data"]["message"]
    assert "Ravi Kumar" in msg and "+919123456780" in msg and "Please call me" in msg
    assert "PRIVATE" not in msg and "wellness" not in msg.lower().replace("wellbeing", "")


def test_missing_provider_reported_honestly(register_student):
    s = register_student()
    _setup(s)
    r = s.post("/api/emergency/alerts", {"client_request_id": "req-00000001", "confirm": True})
    assert r.status_code == 201
    alert = r.get_json()["data"]["alert"]
    assert alert["status"] == "not_configured" and alert["delivered_confirmed"] is False
    assert alert["status_text"].startswith("NOT SENT")
    assert "priya@example.com" not in json.dumps(alert)  # destination is masked


def test_failed_delivery_not_reported_as_success(app, register_student, monkeypatch):
    app.config.update(NOTIFY_PROVIDER_EMAIL="smtp", SMTP_HOST="smtp.invalid", SMTP_FROM="mw@example.com")
    calls = []

    def boom(cfg, to, body):
        calls.append(to)
        raise notifications.TransientFailure("ConnectionRefusedError")
    monkeypatch.setattr(notifications, "send_email", boom)
    s = register_student()
    _setup(s)
    alert = s.post("/api/emergency/alerts", {"client_request_id": "req-00000002", "confirm": True}) \
        .get_json()["data"]["alert"]
    assert alert["status"] == "failed" and len(alert["attempts"]) == app.config["NOTIFY_MAX_ATTEMPTS"]
    assert len(calls) == app.config["NOTIFY_MAX_ATTEMPTS"]


def test_accepted_by_provider_is_not_called_delivered(app, register_student, monkeypatch):
    app.config.update(NOTIFY_PROVIDER_EMAIL="smtp", SMTP_HOST="smtp.example.com", SMTP_FROM="mw@example.com")
    sent = []
    monkeypatch.setattr(notifications, "send_email", lambda cfg, to, body: sent.append((to, body)))
    s = register_student()
    _setup(s)
    r = s.post("/api/emergency/alerts", {"client_request_id": "req-00000003", "confirm": True})
    alert = r.get_json()["data"]["alert"]
    assert alert["status"] == "accepted_by_provider" and alert["delivered_confirmed"] is False
    assert "cannot confirm" in alert["status_text"]
    assert sent[0][0] == "priya@example.com"


def test_duplicate_and_cooldown(app, register_student, monkeypatch):
    app.config.update(NOTIFY_PROVIDER_EMAIL="smtp", SMTP_HOST="smtp.example.com", SMTP_FROM="mw@example.com")
    sent = []
    monkeypatch.setattr(notifications, "send_email", lambda cfg, to, body: sent.append(to))
    s = register_student()
    _setup(s)
    r1 = s.post("/api/emergency/alerts", {"client_request_id": "same-request-1", "confirm": True})
    r2 = s.post("/api/emergency/alerts", {"client_request_id": "same-request-1", "confirm": True})
    assert r1.status_code == 201 and r2.status_code == 200 and r2.get_json()["data"]["duplicate_request"]
    r3 = s.post("/api/emergency/alerts", {"client_request_id": "another-request", "confirm": True})
    assert r3.status_code == 429 and r3.get_json()["error"]["code"] == "alert_cooldown"
    assert len(sent) == 1 and EmergencyAlert.query.count() == 1


def test_call_only_contact_cannot_be_messaged(register_student):
    s = register_student()
    s.put("/api/emergency/contact", {**CONTACT, "preferred_method": "call_only"})
    s.put("/api/emergency/preferences", {"alerts_enabled": True, "consent": True})
    r = s.post("/api/emergency/alerts", {"client_request_id": "req-00000004", "confirm": True})
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "call_only"


def test_alert_requires_confirmation(register_student):
    s = register_student()
    _setup(s)
    assert s.post("/api/emergency/alerts", {"client_request_id": "req-00000005"}).status_code == 422
