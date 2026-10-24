import itertools

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import Classroom, ClassMembership, TeacherProfile, User
from app.seed_data import seed_reference_data
from app.services.gemini import AIUnavailable

PASSWORD = "CorrectHorse42"
_counter = itertools.count(1)


class FakeAI:
    """Stands in for GeminiService. Records every call so tests can inspect what was sent."""

    def __init__(self):
        self.configured = True
        self.responses = []  # queue of dicts or AIUnavailable instances
        self.calls = []

    def queue(self, *items):
        self.responses.extend(items)

    def generate_json(self, *, system_instruction, contents, schema, temperature=0.7, max_output_tokens=1024):
        self.calls.append({"system": system_instruction, "contents": contents, "schema": schema})
        if not self.responses:
            raise AIUnavailable("provider_error", "no fake response queued")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        seed_reference_data()
        app.extensions["gemini"] = FakeAI()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def fake_ai(app):
    return app.extensions["gemini"]


class ApiClient:
    def __init__(self, flask_client):
        self.c = flask_client
        self.csrf = None
        self.refresh_csrf()

    def refresh_csrf(self):
        self.csrf = self.c.get("/api/auth/csrf").get_json()["data"]["csrf_token"]

    def _send(self, method, url, json=None, csrf=True):
        headers = {"X-CSRF-Token": self.csrf} if csrf else {}
        resp = getattr(self.c, method)(url, json=json, headers=headers)
        body = resp.get_json(silent=True) or {}
        token = (body.get("data") or {}).get("csrf_token") if isinstance(body.get("data"), dict) else None
        if token:
            self.csrf = token
        return resp

    def get(self, url):
        return self.c.get(url)

    def post(self, url, json=None, csrf=True):
        return self._send("post", url, json if json is not None else {}, csrf)

    def put(self, url, json=None):
        return self._send("put", url, json if json is not None else {})

    def patch(self, url, json=None):
        return self._send("patch", url, json if json is not None else {})

    def delete(self, url, json=None):
        return self._send("delete", url, json)


@pytest.fixture
def make_client(app):
    def _make():
        return ApiClient(app.test_client())
    return _make


@pytest.fixture
def register_student(make_client):
    def _register(ai_consent=True, name=None):
        n = next(_counter)
        client = make_client()
        resp = client.post("/api/auth/register", {
            "email": f"student{n}@example.com", "password": PASSWORD, "display_name": name or f"Student {n}",
            "accept_terms": True, "ai_processing_consent": ai_consent})
        assert resp.status_code == 201, resp.get_json()
        client.user = resp.get_json()["data"]["user"]
        return client
    return _register


@pytest.fixture
def teacher_client(app, make_client):
    def _make(email=None):
        email = email or f"teacher{next(_counter)}@example.com"
        user = User(email=email, password_hash=generate_password_hash(PASSWORD), role="teacher",
                    display_name="Teacher")
        db.session.add(user)
        db.session.flush()
        db.session.add(TeacherProfile(user_id=user.id))
        db.session.commit()
        client = make_client()
        resp = client.post("/api/auth/login", {"email": email, "password": PASSWORD})
        assert resp.status_code == 200
        client.user = resp.get_json()["data"]["user"]
        return client
    return _make


def chat_reply(reply="That sounds hard. What feels most urgent?", risk="none", slugs=None, title="Exam stress"):
    return {"reply": reply, "risk_level": risk, "suggested_activity_slugs": slugs or [], "conversation_title": title}


def join_class(student_client, code, share=True):
    resp = student_client.post("/api/classes/join", {"join_code": code, "share_aggregates": share})
    assert resp.status_code == 201, resp.get_json()
