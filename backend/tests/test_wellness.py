import re

import pytest

from app.services import scoring


def test_scoring_formula_known_values():
    r = scoring.compute(stress=1, anxiety=1, mood=5, sleep_hours=8, sleep_quality=5, academic_pressure=1)
    assert r["wellness_index"] == 100.0
    r = scoring.compute(stress=5, anxiety=5, mood=1, sleep_hours=3, sleep_quality=1, academic_pressure=5)
    assert r["wellness_index"] == 0.0
    r = scoring.compute(stress=3, anxiety=3, mood=3, sleep_hours=8, sleep_quality=3, academic_pressure=3)
    # mood 50, stress 50, anxiety 50, sleep (50+100)/2=75, academic 50 -> 50 + 0.2*25 = 55
    assert r["sleep_score"] == 75.0 and r["wellness_index"] == 55.0


def test_scoring_is_deterministic():
    args = dict(stress=4, anxiety=2, mood=3, sleep_hours=6.5, sleep_quality=4, academic_pressure=5)
    assert scoring.compute(**args) == scoring.compute(**args)


@pytest.mark.parametrize("hours,expected", [(7, 100), (9, 100), (5, 50), (3, 0), (2, 0), (11, 50), (13, 0)])
def test_sleep_hours_curve(hours, expected):
    assert scoring.sleep_hours_score(hours) == expected


def test_missing_inputs_reweight_or_withhold_index():
    r = scoring.compute(mood=5, stress=1)
    assert r["wellness_index"] is None and r["items_answered"] == 2
    r = scoring.compute(mood=5, stress=1, anxiety=1)
    assert r["wellness_index"] == 100.0 and r["items_answered"] == 3


def test_checkin_api_valid_invalid_and_history(register_student):
    s = register_student()
    assert s.post("/api/checkins", {"stress": 7}).status_code == 422
    assert s.post("/api/checkins", {"stress": "high"}).status_code == 422
    assert s.post("/api/checkins", {"sleep_hours": 30}).status_code == 422
    assert s.post("/api/checkins", {"stressors": ["aliens"]}).status_code == 422
    assert s.post("/api/checkins", {}).status_code == 422
    assert s.post("/api/checkins", {"mood": 3, "date": "2001-01-01"}).status_code == 422
    r = s.post("/api/checkins", {"stress": 4, "anxiety": 3, "mood": 2, "sleep_hours": 6, "sleep_quality": 2,
                                 "academic_pressure": 5, "stressors": ["exams"]})
    assert r.status_code == 201
    body = r.get_json()["data"]
    assert body["xp_awarded"] == 10 and body["checkin"]["source"] == "self_report"
    assert any(b["code"] == "first_checkin" for b in body["new_badges"])
    # same day again updates rather than duplicating, and earns no extra XP
    r2 = s.post("/api/checkins", {"mood": 4, "stress": 2, "anxiety": 2})
    assert r2.status_code == 200 and r2.get_json()["data"]["xp_awarded"] == 0
    hist = s.get("/api/checkins").get_json()["data"]
    assert len(hist) == 1


def test_student_can_correct_and_delete_own_checkin_only(register_student):
    a = register_student()
    b = register_student()
    cid = a.post("/api/checkins", {"mood": 2, "stress": 4, "anxiety": 4}).get_json()["data"]["checkin"]["id"]
    r = a.patch(f"/api/checkins/{cid}", {"mood": 4})
    assert r.status_code == 200 and r.get_json()["data"]["inputs"]["mood"] == 4
    assert r.get_json()["data"]["indicators"]["mood_level"] == 75.0
    assert b.patch(f"/api/checkins/{cid}", {"mood": 1}).status_code == 404
    assert b.delete(f"/api/checkins/{cid}").status_code == 404
    assert a.delete(f"/api/checkins/{cid}").status_code == 200


def test_summary_contains_no_diagnostic_labels(register_student):
    s = register_student()
    s.post("/api/checkins", {"stress": 5, "anxiety": 5, "mood": 1, "sleep_hours": 3, "academic_pressure": 5})
    text = str(s.get("/api/wellness/summary").get_json()).lower()
    for word in ["depress", "disorder", "diagnosed", "mentally ill", "at risk", "severe"]:
        assert word not in text, word
    assert "not a clinical" in text


def test_methodology_is_public_and_documented(make_client):
    r = make_client().get("/api/wellness/methodology")
    data = r.get_json()["data"]
    assert abs(sum(data["weights"].values()) - 1.0) < 1e-9
    assert re.search("not clinically validated", data["clinical_status"], re.I)
