"""Teacher endpoints. They only ever return aggregate, suppressed statistics.

No endpoint here reads conversations, messages, memory, journal entries, emergency
contacts/alerts, or per-student check-in rows for display.
"""
import json
import secrets
import string

from flask import Blueprint, g, request

from ..extensions import db, limiter, user_or_ip
from ..models import ClassInsight, Classroom, ClassMembership
from ..security import teacher_required
from ..services import ai_validation, analytics, prompts
from ..services.gemini import AIUnavailable, get_ai, to_contents
from ..utils import ApiError, iso, json_body, ok, req_str

bp = Blueprint("teacher", __name__, url_prefix="/api/teacher")

_CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1")


def _new_code():
    while True:
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        if not Classroom.query.filter_by(join_code=code).first():
            return code


def own_class(class_id):
    c = Classroom.query.filter_by(id=class_id, teacher_id=g.user.id).first()
    if c is None:  # 404 rather than 403 so other teachers' class ids are not confirmed
        raise ApiError("Class not found.", 404, "not_found")
    return c


def class_dict(c):
    count = ClassMembership.query.filter_by(class_id=c.id).count()
    return {"id": c.id, "name": c.name, "join_code": c.join_code, "member_count": count,
            "created_at": iso(c.created_at)}


@bp.get("/classes")
@teacher_required
def list_classes():
    return ok([class_dict(c) for c in Classroom.query.filter_by(teacher_id=g.user.id).order_by(Classroom.name)])


@bp.post("/classes")
@teacher_required
@limiter.limit("20 per hour", key_func=user_or_ip)
def create_class():
    name = req_str(json_body(), "name", min_len=2, max_len=120, label="Class name")
    c = Classroom(name=name, teacher_id=g.user.id, join_code=_new_code())
    db.session.add(c)
    db.session.commit()
    return ok(class_dict(c), 201)


@bp.post("/classes/<int:class_id>/rotate-code")
@teacher_required
def rotate_code(class_id):
    c = own_class(class_id)
    c.join_code = _new_code()
    db.session.commit()
    return ok(class_dict(c))


@bp.delete("/classes/<int:class_id>")
@teacher_required
def delete_class(class_id):
    c = own_class(class_id)
    db.session.delete(c)
    db.session.commit()
    return ok({"deleted": True})


def _weeks():
    weeks = request.args.get("weeks", 4, type=int)
    if weeks not in analytics.ALLOWED_PERIODS:
        raise ApiError("Period must be 4, 8 or 12 weeks.", 422, "validation_error")
    return weeks


def insight_dict(i):
    if i is None:
        return None
    return {"id": i.id, "period_weeks": i.period_weeks, "observations": i.observations,
            "ai_narrative": i.ai_narrative, "ai_status": i.ai_status, "created_at": iso(i.created_at)}


@bp.get("/classes/<int:class_id>/analytics")
@teacher_required
def class_analytics(class_id):
    c = own_class(class_id)
    weeks = _weeks()
    stats = analytics.class_statistics(c, weeks)
    observations = analytics.rule_based_observations(stats)
    latest = (ClassInsight.query.filter_by(class_id=c.id, period_weeks=weeks)
              .order_by(ClassInsight.created_at.desc()).first())
    return ok({"statistics": stats, "observations": observations,
               "suggestions": analytics.rule_based_suggestions(observations),
               "latest_ai_insight": insight_dict(latest)})


@bp.post("/classes/<int:class_id>/insights")
@teacher_required
@limiter.limit("10 per hour", key_func=user_or_ip)
def generate_insight(class_id):
    c = own_class(class_id)
    data = json_body()
    weeks = data.get("weeks", 4)
    if weeks not in analytics.ALLOWED_PERIODS:
        raise ApiError("Period must be 4, 8 or 12 weeks.", 422, "validation_error")
    stats = analytics.class_statistics(c, weeks)
    observations = analytics.rule_based_observations(stats)
    visible_weeks = [w for w in stats["weeks"] if not w["suppressed"]]

    narrative, status = None, "skipped_insufficient_data"
    if stats["sufficient_data"] and visible_weeks:
        payload = json.dumps(analytics.ai_input(stats), default=str)
        try:
            raw = get_ai().generate_json(system_instruction=prompts.INSIGHT_SYSTEM,
                                         contents=to_contents([("user", payload)]),
                                         schema=prompts.INSIGHT_SCHEMA, temperature=0.3, max_output_tokens=900)
            allowed = set(analytics.METRICS) | {"participation", "general"} | \
                {f"stressor:{k}" for k in stats["stressor_labels"]}
            narrative = ai_validation.validate_insight(raw, allowed)
            status = "generated"
        except AIUnavailable as exc:
            status = f"ai_unavailable:{exc.reason}"

    insight = ClassInsight(class_id=c.id, period_weeks=weeks, statistics=analytics.ai_input(stats),
                           observations=observations, ai_narrative=narrative, ai_status=status)
    db.session.add(insight)
    db.session.commit()
    return ok(insight_dict(insight), 201)
