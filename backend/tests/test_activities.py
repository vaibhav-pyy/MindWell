from datetime import date, timedelta

from app.extensions import db
from app.models import Activity, ActivitySession, StudentProgress, XPTransaction
from app.services import gamification
from app.services.gemini import AIUnavailable


def _activity(slug):
    return Activity.query.filter_by(slug=slug).first()


def _start(client, activity_id, rewind_seconds=10_000):
    r = client.post(f"/api/activities/{activity_id}/sessions")
    assert r.status_code == 201
    sid = r.get_json()["data"]["session_id"]
    s = db.session.get(ActivitySession, sid)
    s.started_at = s.started_at - timedelta(seconds=rewind_seconds)
    db.session.commit()
    return sid


def test_recommendations_assigned_and_dismissable(register_student):
    s = register_student()
    s.post("/api/checkins", {"stress": 5, "anxiety": 4, "mood": 2, "sleep_hours": 4, "academic_pressure": 5})
    recs = s.get("/api/recommendations/today").get_json()["data"]
    assert 1 <= len(recs) <= 3
    assert recs[0]["activity"]["slug"] == "box-breathing-4"
    assert all(r["reason"] for r in recs)
    r = s.post(f"/api/recommendations/{recs[0]['id']}/dismiss")
    assert r.get_json()["data"]["status"] == "dismissed"
    again = s.get("/api/recommendations/today").get_json()["data"]
    assert len(again) == len(recs)  # not regenerated within the day


def test_completion_awards_xp_once(register_student):
    s = register_student()
    a = _activity("box-breathing-4")
    sid = _start(s, a.id)
    r = s.post(f"/api/activity-sessions/{sid}/complete", {})
    assert r.status_code == 201
    data = r.get_json()["data"]
    assert data["xp_awarded"] == a.xp_reward and data["progress"]["total_xp"] == a.xp_reward
    dup = s.post(f"/api/activity-sessions/{sid}/complete", {}).get_json()["data"]
    assert dup["already_completed"] is True and dup["xp_awarded"] == 0
    assert dup["progress"]["total_xp"] == a.xp_reward
    assert XPTransaction.query.filter_by(source_type="activity").count() == 1


def test_completion_too_early_rejected(register_student):
    s = register_student()
    a = _activity("box-breathing-4")
    sid = _start(s, a.id, rewind_seconds=5)
    r = s.post(f"/api/activity-sessions/{sid}/complete", {})
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "too_early"


def test_journal_requires_text_and_saves_only_on_request(register_student):
    s = register_student()
    a = _activity("worry-journal")
    sid = _start(s, a.id)
    assert s.post(f"/api/activity-sessions/{sid}/complete", {"journal_text": "short"}).status_code == 422
    r = s.post(f"/api/activity-sessions/{sid}/complete",
               {"journal_text": "I am worried about my physics exam on Monday.", "save_to_journal": False})
    assert r.status_code == 201
    assert s.get("/api/journal").get_json()["data"] == []
    sid2 = _start(s, a.id)
    s.post(f"/api/activity-sessions/{sid2}/complete",
           {"journal_text": "Writing it down helped me plan.", "save_to_journal": True})
    assert len(s.get("/api/journal").get_json()["data"]) == 1


def test_daily_xp_cap_per_activity(register_student, app):
    s = register_student()
    a = _activity("five-senses-grounding")
    awarded = []
    for _ in range(app.config["XP_AWARDS_PER_ACTIVITY_PER_DAY"] + 1):
        sid = _start(s, a.id)
        awarded.append(s.post(f"/api/activity-sessions/{sid}/complete", {}).get_json()["data"]["xp_awarded"])
    assert awarded[:-1] == [a.xp_reward] * app.config["XP_AWARDS_PER_ACTIVITY_PER_DAY"]
    assert awarded[-1] == 0


def test_cannot_complete_another_students_session(register_student):
    a_client = register_student()
    b_client = register_student()
    sid = _start(a_client, _activity("box-breathing-4").id)
    assert b_client.post(f"/api/activity-sessions/{sid}/complete", {}).status_code == 404


def test_levels(app):
    assert gamification.level_info(0)["level"] == 1
    assert gamification.level_info(49)["level"] == 1
    assert gamification.level_info(50)["level"] == 2
    assert gamification.level_info(150)["level"] == 3
    info = gamification.level_info(100)
    assert info["level_floor_xp"] == 50 and info["next_level_xp"] == 150 and info["progress_pct"] == 50.0


def test_streak_rules(app, register_student):
    s = register_student()
    sid = s.user["id"]
    d0 = date(2026, 3, 1)
    gamification.record_active_day(sid, d0)
    gamification.record_active_day(sid, d0)  # same day doesn't double count
    gamification.record_active_day(sid, d0 + timedelta(days=1))
    gamification.record_active_day(sid, d0 + timedelta(days=2))
    p = db.session.get(StudentProgress, sid)
    assert p.current_streak == 3 and p.longest_streak == 3
    gamification.record_active_day(sid, d0 + timedelta(days=5))  # missed days -> new streak, nothing lost
    assert p.current_streak == 1 and p.longest_streak == 3
    assert gamification.displayed_streak(p, today=d0 + timedelta(days=6)) == 1
    assert gamification.displayed_streak(p, today=d0 + timedelta(days=8)) == 0


def test_badges_awarded(app, register_student):
    s = register_student()
    a = _activity("box-breathing-4")
    sid = _start(s, a.id)
    data = s.post(f"/api/activity-sessions/{sid}/complete", {}).get_json()["data"]
    assert "first_activity" in [b["code"] for b in data["new_badges"]]
    prog = s.get("/api/progress").get_json()["data"]
    earned = [b["code"] for b in prog["badges"] if b["earned"]]
    assert earned == ["first_activity"]


VALID_ACTIVITY = {
    "title": "Desk Reset", "description": "A short break to reset your posture and attention.",
    "category": "study_break", "kind": "guided_steps",
    "instructions": ["Stand up slowly.", "Roll your shoulders five times.", "Take three slow breaths."],
    "journal_prompts": [], "duration_minutes": 3, "difficulty": "easy",
    "completion_criteria": "Go through all steps.", "safety_notes": "Move gently.", "suggested_xp": 9999,
}


def test_ai_generated_activity_validated_and_xp_set_by_backend(register_student, fake_ai, app):
    s = register_student()
    fake_ai.queue(dict(VALID_ACTIVITY))
    r = s.post("/api/activities/generate", {"concern": "too much screen time while studying", "available_minutes": 5})
    assert r.status_code == 201, r.get_json()
    act = r.get_json()["data"]
    assert act["xp_reward"] == gamification.xp_for_duration(3) and act["xp_reward"] != 9999
    assert act["is_personal"] and act["source"] == "ai"
    other = register_student()
    assert other.get(f"/api/activities/{act['id']}").status_code == 404


def test_unsafe_or_malformed_ai_activity_rejected(register_student, fake_ai):
    s = register_student()
    unsafe = dict(VALID_ACTIVITY, instructions=["Skip meals today.", "Take a cold shower.", "Fast until dinner."])
    too_long = dict(VALID_ACTIVITY, duration_minutes=25)
    bad_kind = dict(VALID_ACTIVITY, kind="hypnosis")
    fake_ai.queue(unsafe, too_long, bad_kind, AIUnavailable("quota", "q"))
    for _ in range(4):
        r = s.post("/api/activities/generate", {"concern": "stress", "available_minutes": 10})
        assert r.status_code == 503
    assert Activity.query.filter_by(source="ai").count() == 0
