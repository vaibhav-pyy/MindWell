import json
from datetime import timedelta

from conftest import join_class

from app.extensions import db
from app.models import CheckIn
from app.services import scoring
from app.utils import local_today, week_start
from app.services.gemini import AIUnavailable

PRIVATE_MARKERS = ["PRIVATE-NOTE", "PRIVATE-CHAT", "PRIVATE-MEMORY", "contact@example.com"]


def _class(teacher, name="Section A"):
    r = teacher.post("/api/teacher/classes", {"name": name})
    assert r.status_code == 201
    return r.get_json()["data"]


def _add_checkins(student_id, values, days_ago_list):
    today = local_today()
    for days_ago in days_ago_list:
        c = CheckIn(student_id=student_id, checkin_date=today - timedelta(days=days_ago), stressors=["exams"],
                    note="PRIVATE-NOTE", **values)
        scoring.apply_to_checkin(c)
        db.session.add(c)
    db.session.commit()


def _populate(register_student, code, n, share=True, values=None):
    students = []
    for _ in range(n):
        s = register_student()
        join_class(s, code, share)
        _add_checkins(s.user["id"], values or dict(stress=3, anxiety=3, mood=3, sleep_hours=8, sleep_quality=3,
                                                   academic_pressure=3), [0])
        students.append(s)
    return students


def test_teacher_only_sees_own_classes(teacher_client, register_student):
    t1, t2 = teacher_client(), teacher_client()
    c = _class(t1)
    assert t2.get(f"/api/teacher/classes/{c['id']}/analytics").status_code == 404
    assert t2.post(f"/api/teacher/classes/{c['id']}/insights", {"weeks": 4}).status_code == 404
    assert t1.get(f"/api/teacher/classes/{c['id']}/analytics").status_code == 200
    s = register_student()
    assert s.get(f"/api/teacher/classes/{c['id']}/analytics").status_code == 403


def test_small_cohort_suppressed(app, teacher_client, register_student, fake_ai):
    t = teacher_client()
    c = _class(t)
    _populate(register_student, c["join_code"], app.config["MIN_COHORT_SIZE"] - 1)
    data = t.get(f"/api/teacher/classes/{c['id']}/analytics?weeks=4").get_json()["data"]
    stats = data["statistics"]
    assert stats["sufficient_data"] is False and stats["weeks"] == []
    assert stats["contributing_members"] is None  # exact count below threshold not revealed
    assert "Not enough students" in data["observations"][0]["text"]
    r = t.post(f"/api/teacher/classes/{c['id']}/insights", {"weeks": 4}).get_json()["data"]
    assert r["ai_narrative"] is None and r["ai_status"] == "skipped_insufficient_data"
    assert fake_ai.calls == []  # no fabricated insight for empty/small data


def test_non_consenting_students_excluded(app, teacher_client, register_student):
    t = teacher_client()
    c = _class(t)
    k = app.config["MIN_COHORT_SIZE"]
    _populate(register_student, c["join_code"], k - 1, share=True)
    _populate(register_student, c["join_code"], 3, share=False)
    stats = t.get(f"/api/teacher/classes/{c['id']}/analytics").get_json()["data"]["statistics"]
    assert stats["member_count"] == k + 2 and stats["sufficient_data"] is False


def test_aggregates_correct_and_contain_no_individual_data(app, teacher_client, register_student):
    t = teacher_client()
    c = _class(t)
    k = app.config["MIN_COHORT_SIZE"]
    low = dict(stress=1, anxiety=1, mood=5, sleep_hours=8, sleep_quality=5, academic_pressure=1)  # index 100
    high = dict(stress=5, anxiety=5, mood=1, sleep_hours=3, sleep_quality=1, academic_pressure=5)  # index 0
    students = _populate(register_student, c["join_code"], k - 1, values=low)
    students += _populate(register_student, c["join_code"], 1, values=high)
    # A student who checks in many times still counts once (per-student averaging)
    _add_checkins(students[-1].user["id"], high, [1, 2])
    resp = t.get(f"/api/teacher/classes/{c['id']}/analytics?weeks=4")
    data = resp.get_json()["data"]
    current = [w for w in data["statistics"]["weeks"] if w["week_start"] == week_start(local_today()).isoformat()][0]
    if not current["suppressed"]:
        expected = round(((k - 1) * 100 + 0) / k)
        assert current["metrics"]["wellness_index"] == expected
        assert current["stressors_pct"]["exams"] == 100
    blob = resp.get_data(as_text=True)
    for marker in PRIVATE_MARKERS:
        assert marker not in blob
    for s in students:
        assert s.user["email"] not in blob and s.user["display_name"] not in blob


def test_invalid_period_filter_rejected(teacher_client):
    t = teacher_client()
    c = _class(t)
    assert t.get(f"/api/teacher/classes/{c['id']}/analytics?weeks=1").status_code == 422
    assert t.get(f"/api/teacher/classes/{c['id']}/analytics?weeks=3").status_code == 422


def test_ai_insight_gets_only_aggregates_and_is_validated(app, teacher_client, register_student, fake_ai):
    t = teacher_client()
    c = _class(t)
    students = _populate(register_student, c["join_code"], app.config["MIN_COHORT_SIZE"])
    fake_ai.queue({"observations": [{"text": "Average academic pressure was 50 out of 100 this week.",
                                     "metric": "academic_pressure_level"}],
                   "suggestions": ["Consider an optional study-planning session."],
                   "caveats": ["Figures are descriptive and come from a small group."]})
    r = t.post(f"/api/teacher/classes/{c['id']}/insights", {"weeks": 4}).get_json()["data"]
    assert r["ai_status"] == "generated" and r["ai_narrative"]["suggestions"]
    sent = json.dumps(fake_ai.calls[-1])
    for s in students:
        assert s.user["email"] not in sent and s.user["display_name"] not in sent
    assert "PRIVATE-NOTE" not in sent

    fake_ai.queue({"observations": [{"text": "Several students have clinical depression.", "metric": "x"}],
                   "suggestions": ["Identify the students who scored lowest."], "caveats": ["none"]})
    r = t.post(f"/api/teacher/classes/{c['id']}/insights", {"weeks": 4}).get_json()["data"]
    assert r["ai_narrative"] is None and r["ai_status"] == "ai_unavailable:invalid_output"

    fake_ai.queue(AIUnavailable("quota", "q"))
    r = t.post(f"/api/teacher/classes/{c['id']}/insights", {"weeks": 4}).get_json()["data"]
    assert r["ai_status"] == "ai_unavailable:quota" and r["observations"]


def test_student_can_withdraw_from_aggregates(app, teacher_client, register_student):
    t = teacher_client()
    c = _class(t)
    students = _populate(register_student, c["join_code"], app.config["MIN_COHORT_SIZE"])
    assert t.get(f"/api/teacher/classes/{c['id']}/analytics").get_json()["data"]["statistics"]["sufficient_data"]
    students[0].patch(f"/api/classes/{c['id']}/sharing", {"share_aggregates": False})
    assert not t.get(f"/api/teacher/classes/{c['id']}/analytics").get_json()["data"]["statistics"]["sufficient_data"]
