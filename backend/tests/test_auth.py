from conftest import PASSWORD
from app.extensions import db


def test_register_login_logout_flow(make_client):
    c = make_client()
    r = c.post("/api/auth/register", {"email": "Asha@Example.com", "password": PASSWORD, "display_name": "Asha",
                                      "accept_terms": True, "ai_processing_consent": True})
    assert r.status_code == 201
    user = r.get_json()["data"]["user"]
    assert user["role"] == "student" and user["email"] == "asha@example.com"
    assert c.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/me").status_code == 401
    r = c.post("/api/auth/login", {"email": "asha@example.com", "password": PASSWORD})
    assert r.status_code == 200
    assert c.get("/api/auth/me").status_code == 200


def test_password_is_hashed(app, register_student):
    from app.models import User
    s = register_student()
    u = db.session.get(User, s.user["id"])
    assert PASSWORD not in u.password_hash and u.password_hash.startswith(("scrypt:", "pbkdf2:"))


def test_register_validation(make_client):
    c = make_client()
    base = {"email": "x@example.com", "password": PASSWORD, "display_name": "X", "accept_terms": True}
    assert c.post("/api/auth/register", {**base, "password": "short1"}).status_code == 422
    assert c.post("/api/auth/register", {**base, "password": "nodigitsatall"}).status_code == 422
    assert c.post("/api/auth/register", {**base, "email": "not-an-email"}).status_code == 422
    assert c.post("/api/auth/register", {**base, "accept_terms": False}).status_code == 422
    assert c.post("/api/auth/register", base).status_code == 201
    c2 = make_client()
    assert c2.post("/api/auth/register", base).status_code == 409


def test_invalid_credentials_generic_message(make_client, register_student):
    s = register_student()
    c = make_client()
    r1 = c.post("/api/auth/login", {"email": "nobody@example.com", "password": PASSWORD})
    r2 = c.post("/api/auth/login", {"email": s.user["email"], "password": "WrongPass999"})
    assert r1.status_code == r2.status_code == 401
    assert r1.get_json()["error"]["message"] == r2.get_json()["error"]["message"]


def test_teacher_login_and_portal_check(teacher_client, make_client):
    t = teacher_client(email="t@example.com")
    assert t.user["role"] == "teacher"
    c = make_client()
    r = c.post("/api/auth/login", {"email": "t@example.com", "password": PASSWORD, "role": "student"})
    assert r.status_code == 403


def test_students_cannot_self_register_as_teacher(make_client):
    c = make_client()
    r = c.post("/api/auth/register", {"email": "sneaky@example.com", "password": PASSWORD, "display_name": "S",
                                      "accept_terms": True, "role": "teacher"})
    assert r.status_code == 201 and r.get_json()["data"]["user"]["role"] == "student"


def test_csrf_required_for_writes(register_student):
    s = register_student()
    r = s.post("/api/checkins", {"mood": 4}, csrf=False)
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "csrf_failed"
    assert s.post("/api/checkins", {"mood": 4}).status_code == 201


def test_unauthenticated_access_rejected(make_client):
    c = make_client()
    for url in ["/api/conversations", "/api/wellness/summary", "/api/emergency", "/api/progress",
                "/api/teacher/classes", "/api/memory"]:
        assert c.get(url).status_code == 401, url


def test_role_separation(register_student, teacher_client):
    s = register_student()
    t = teacher_client()
    assert s.get("/api/teacher/classes").status_code == 403
    for url in ["/api/conversations", "/api/emergency", "/api/wellness/summary", "/api/memory", "/api/journal",
                "/api/checkins", "/api/emergency/alerts"]:
        assert t.get(url).status_code == 403, url


def test_idle_session_expires(app, register_student):
    s = register_student()
    with s.c.session_transaction() as sess:
        sess["last_seen"] = 0
    assert s.get("/api/auth/me").status_code == 401


def test_account_deletion_cascades(app, register_student):
    from app.models import CheckIn, Conversation, User
    s = register_student()
    s.post("/api/checkins", {"mood": 3, "stress": 3, "sleep_hours": 7})
    s.post("/api/conversations")
    uid = s.user["id"]
    assert s.delete("/api/account", {"password": "wrong", "confirm": "DELETE"}).status_code == 403
    assert s.delete("/api/account", {"password": PASSWORD, "confirm": "DELETE"}).status_code == 200
    assert db.session.get(User, uid) is None
    assert CheckIn.query.filter_by(student_id=uid).count() == 0
    assert Conversation.query.filter_by(student_id=uid).count() == 0
