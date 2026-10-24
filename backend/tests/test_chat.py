import json

from conftest import chat_reply

from app.models import MemoryItem, Message
from app.services.gemini import AIUnavailable, GeminiService


def _new_conv(client):
    r = client.post("/api/conversations")
    assert r.status_code == 201
    return r.get_json()["data"]["id"]


def test_chat_round_trip_persists(register_student, fake_ai):
    s = register_student()
    cid = _new_conv(s)
    fake_ai.queue(chat_reply(slugs=["box-breathing-4", "not-a-real-slug"]))
    r = s.post(f"/api/conversations/{cid}/messages", {"content": "I have three exams next week and feel overwhelmed"})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()["data"]
    assert data["assistant_message"]["source"] == "gemini"
    assert [a["title"] for a in data["assistant_message"]["suggested_activities"]] == ["Calm Breathing (4-4-6)"]
    assert data["conversation"]["title"] == "Exam stress"
    conv = s.get(f"/api/conversations/{cid}").get_json()["data"]
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    # The chat suggestion became a recommendation for today
    recs = s.get("/api/recommendations/today").get_json()["data"]
    assert any(r["source"] == "chat" for r in recs)


def test_gemini_not_configured_is_reported_honestly(app, register_student):
    app.extensions["gemini"] = GeminiService(api_key="", model="gemini-test")
    s = register_student()
    cid = _new_conv(s)
    r = s.post(f"/api/conversations/{cid}/messages", {"content": "hello"})
    assert r.status_code == 503
    err = r.get_json()["error"]
    assert err["code"] == "ai_unavailable" and err["details"]["reason"] == "not_configured"
    assert Message.query.count() == 0  # nothing fabricated or stored


def test_quota_and_provider_failure(register_student, fake_ai):
    s = register_student()
    cid = _new_conv(s)
    fake_ai.queue(AIUnavailable("quota", "limit"), AIUnavailable("provider_error", "down"))
    r1 = s.post(f"/api/conversations/{cid}/messages", {"content": "hello"})
    r2 = s.post(f"/api/conversations/{cid}/messages", {"content": "hello again"})
    assert r1.status_code == r2.status_code == 503
    assert r1.get_json()["error"]["details"]["reason"] == "quota"
    assert Message.query.count() == 0


def test_malformed_model_output_rejected(register_student, fake_ai):
    s = register_student()
    cid = _new_conv(s)
    fake_ai.queue({"reply": "", "risk_level": "none", "suggested_activity_slugs": [], "conversation_title": "x"},
                  {"reply": "ok", "risk_level": "catastrophic", "suggested_activity_slugs": [], "conversation_title": "x"},
                  {"unexpected": True})
    for _ in range(3):
        r = s.post(f"/api/conversations/{cid}/messages", {"content": "hi"})
        assert r.status_code == 503 and r.get_json()["error"]["details"]["reason"] == "invalid_output"


def test_crisis_language_bypasses_ai_and_shows_support(register_student, fake_ai):
    s = register_student()
    cid = _new_conv(s)
    r = s.post(f"/api/conversations/{cid}/messages", {"content": "I don't want to live anymore, I want to end my life"})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert fake_ai.calls == []  # the deterministic screen handled it without the LLM
    assert data["safety"]["level"] == "crisis" and data["safety"]["show_support"] is True
    msg = data["assistant_message"]
    assert msg["source"] == "safety_template"
    assert "14416" in msg["content"] and "112" in msg["content"]
    assert msg["suggested_activities"] == []
    assert "contacted" not in msg["content"].lower() or "can't contact" in msg["content"].lower()


def test_crisis_support_available_without_ai_consent(register_student, fake_ai):
    s = register_student(ai_consent=False)
    cid = _new_conv(s)
    r = s.post(f"/api/conversations/{cid}/messages", {"content": "i want to kill myself"})
    assert r.status_code == 200 and r.get_json()["data"]["safety"]["level"] == "crisis"
    r = s.post(f"/api/conversations/{cid}/messages", {"content": "just a normal message"})
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "ai_consent_required"


def test_ai_high_risk_escalates_but_never_contacts(register_student, fake_ai, app):
    from app.models import EmergencyAlert
    s = register_student()
    cid = _new_conv(s)
    fake_ai.queue(chat_reply(reply="I'm concerned about you.", risk="high", slugs=["box-breathing-4"]))
    r = s.post(f"/api/conversations/{cid}/messages", {"content": "everything feels pointless lately"})
    data = r.get_json()["data"]
    assert data["safety"]["level"] == "crisis"
    assert data["assistant_message"]["suggested_activities"] == []  # no activities during a crisis
    assert EmergencyAlert.query.count() == 0


def test_bounded_context_and_no_cross_user_leakage(app, register_student, fake_ai):
    alice = register_student(name="Alice")
    bob = register_student(name="Bob")
    alice.post("/api/memory", {"content": "ALICE-SECRET: I play the violin"})
    bob.post("/api/memory", {"content": "BOB-SECRET: I play cricket"})
    a_cid = _new_conv(alice)
    for i in range(10):
        fake_ai.queue(chat_reply(reply=f"reply {i}"))
        alice.post(f"/api/conversations/{a_cid}/messages", {"content": f"alice message {i}"})
    fake_ai.calls.clear()
    fake_ai.queue(chat_reply())
    alice.post(f"/api/conversations/{a_cid}/messages", {"content": "latest"})
    sent = json.dumps(fake_ai.calls[-1])
    assert "ALICE-SECRET" in sent and "BOB-SECRET" not in sent
    assert len(fake_ai.calls[-1]["contents"]) <= app.config["CHAT_CONTEXT_MESSAGES"]
    assert "Alice" not in fake_ai.calls[-1]["system"]  # name / email are not sent
    assert alice.user["email"] not in sent

    b_cid = _new_conv(bob)
    fake_ai.queue(chat_reply())
    bob.post(f"/api/conversations/{b_cid}/messages", {"content": "hi"})
    sent_b = json.dumps(fake_ai.calls[-1])
    assert "ALICE-SECRET" not in sent_b and "alice message" not in sent_b


def test_cannot_access_other_students_conversations(register_student, fake_ai):
    alice = register_student()
    bob = register_student()
    cid = _new_conv(alice)
    assert bob.get(f"/api/conversations/{cid}").status_code == 404
    assert bob.post(f"/api/conversations/{cid}/messages", {"content": "hi"}).status_code == 404
    assert bob.delete(f"/api/conversations/{cid}").status_code == 404
    assert alice.get(f"/api/conversations/{cid}").status_code == 200


def test_memory_summary_and_controls(register_student, fake_ai):
    s = register_student()
    cid = _new_conv(s)
    for _ in range(2):
        fake_ai.queue(chat_reply())
        s.post(f"/api/conversations/{cid}/messages", {"content": "exams are stressing me"})
    fake_ai.queue({"summary": "In this conversation the student said exams are stressful."})
    _new_conv(s)  # starting a new conversation summarises the previous one
    items = s.get("/api/memory").get_json()["data"]["items"]
    assert len(items) == 1 and items[0]["kind"] == "ai_summary"
    assert "AI-generated" in items[0]["label"]
    assert s.delete(f"/api/memory/{items[0]['id']}").status_code == 200
    assert s.get("/api/memory").get_json()["data"]["items"] == []


def test_diagnostic_summary_is_rejected(register_student, fake_ai):
    s = register_student()
    cid = _new_conv(s)
    for _ in range(2):
        fake_ai.queue(chat_reply())
        s.post(f"/api/conversations/{cid}/messages", {"content": "can't sleep"})
    fake_ai.queue({"summary": "The student has depression and an anxiety disorder."})
    _new_conv(s)
    assert MemoryItem.query.count() == 0


def test_memory_disabled_sends_no_memory(register_student, fake_ai):
    s = register_student()
    s.post("/api/memory", {"content": "REMEMBER-ME note"})
    s.patch("/api/privacy", {"memory_enabled": False})
    cid = _new_conv(s)
    fake_ai.queue(chat_reply())
    s.post(f"/api/conversations/{cid}/messages", {"content": "hello"})
    assert "REMEMBER-ME" not in fake_ai.calls[-1]["system"]


def test_delete_all_conversations(register_student, fake_ai):
    s = register_student()
    _new_conv(s)
    _new_conv(s)
    assert s.delete("/api/conversations").get_json()["data"]["deleted"] == 2
    assert s.get("/api/conversations").get_json()["data"] == []
