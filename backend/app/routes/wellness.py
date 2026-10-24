from datetime import date, timedelta
from statistics import mean

from flask import Blueprint, current_app, g, request

from ..extensions import db
from ..models import CheckIn
from ..security import student_required
from ..services import gamification, scoring
from ..utils import ApiError, iso, json_body, local_today, ok, opt_float, opt_int, req_str

bp = Blueprint("wellness", __name__, url_prefix="/api")

ITEM_FIELDS = ("stress", "anxiety", "mood", "sleep_quality", "academic_pressure")
LEVEL_FIELDS = ("stress_level", "anxiety_level", "mood_level", "sleep_score", "academic_pressure_level",
                "wellness_index")


def checkin_dict(c):
    return {
        "id": c.id, "date": c.checkin_date.isoformat(),
        "inputs": {"stress": c.stress, "anxiety": c.anxiety, "mood": c.mood, "sleep_hours": c.sleep_hours,
                   "sleep_quality": c.sleep_quality, "academic_pressure": c.academic_pressure},
        "stressors": c.stressors or [], "note": c.note,
        "indicators": {k: getattr(c, k) for k in LEVEL_FIELDS},
        "items_answered": c.items_answered, "scoring_version": c.scoring_version,
        "source": "self_report", "created_at": iso(c.created_at), "updated_at": iso(c.updated_at),
    }


def _apply_inputs(checkin, data, partial=False):
    for f in ITEM_FIELDS:
        if not partial or f in data:
            setattr(checkin, f, opt_int(data, f, 1, 5))
    if not partial or "sleep_hours" in data:
        checkin.sleep_hours = opt_float(data, "sleep_hours", 0, 16)
    if not partial or "stressors" in data:
        stressors = data.get("stressors") or []
        if not isinstance(stressors, list) or any(s not in scoring.STRESSOR_CATEGORIES for s in stressors):
            raise ApiError("Unknown stressor category.", 422, "validation_error", {"stressors": "invalid"})
        checkin.stressors = sorted(set(stressors))
    if not partial or "note" in data:
        checkin.note = req_str(data, "note", max_len=1000, required=False)
    answered = sum(getattr(checkin, f) is not None for f in ITEM_FIELDS) + (checkin.sleep_hours is not None)
    if answered == 0:
        raise ApiError("Please answer at least one question.", 422, "validation_error")
    scoring.apply_to_checkin(checkin)


@bp.post("/checkins")
@student_required
def upsert_checkin():
    """One check-in per local day. Submitting again on the same day updates it."""
    data = json_body()
    today = local_today()
    day = today
    if data.get("date"):
        try:
            day = date.fromisoformat(str(data["date"]))
        except ValueError:
            raise ApiError("Invalid date.", 422, "validation_error", {"date": "invalid"})
        if day not in (today, today - timedelta(days=1)):
            raise ApiError("Check-ins can be added for today or yesterday only.", 422, "validation_error",
                           {"date": "range"})
    checkin = CheckIn.query.filter_by(student_id=g.user.id, checkin_date=day).first()
    created = checkin is None
    if created:
        checkin = CheckIn(student_id=g.user.id, checkin_date=day)
    _apply_inputs(checkin, data)
    db.session.add(checkin)
    db.session.flush()
    xp = 0
    if created:
        xp = gamification.award_xp(g.user.id, current_app.config["XP_CHECKIN"], "Daily check-in", "checkin",
                                   checkin.id)
        gamification.record_active_day(g.user.id, day)
    new_badges = gamification.evaluate_badges(g.user.id)
    db.session.commit()
    return ok({"checkin": checkin_dict(checkin), "created": created, "xp_awarded": xp,
               "new_badges": new_badges, "progress": gamification.summary(g.user.id)}, 201 if created else 200)


def _own_checkin(checkin_id):
    c = CheckIn.query.filter_by(id=checkin_id, student_id=g.user.id).first()
    if c is None:
        raise ApiError("Check-in not found.", 404, "not_found")
    return c


@bp.patch("/checkins/<int:checkin_id>")
@student_required
def correct_checkin(checkin_id):
    c = _own_checkin(checkin_id)
    _apply_inputs(c, json_body(), partial=True)
    db.session.commit()
    return ok(checkin_dict(c))


@bp.delete("/checkins/<int:checkin_id>")
@student_required
def delete_checkin(checkin_id):
    c = _own_checkin(checkin_id)
    db.session.delete(c)
    db.session.commit()
    return ok({"deleted": True})


@bp.get("/checkins")
@student_required
def list_checkins():
    days = min(max(request.args.get("days", 30, type=int), 1), 365)
    since = local_today() - timedelta(days=days - 1)
    rows = (CheckIn.query.filter(CheckIn.student_id == g.user.id, CheckIn.checkin_date >= since)
            .order_by(CheckIn.checkin_date.desc()).all())
    return ok([checkin_dict(c) for c in rows])


def _avg(rows, key):
    vals = [getattr(r, key) for r in rows if getattr(r, key) is not None]
    return round(mean(vals), 1) if vals else None


@bp.get("/wellness/summary")
@student_required
def wellness_summary():
    today = local_today()
    rows = (CheckIn.query.filter(CheckIn.student_id == g.user.id, CheckIn.checkin_date >= today - timedelta(days=29))
            .order_by(CheckIn.checkin_date).all())
    this_week = [r for r in rows if r.checkin_date > today - timedelta(days=7)]
    last_week = [r for r in rows if today - timedelta(days=14) < r.checkin_date <= today - timedelta(days=7)]
    current = {k: _avg(this_week, k) for k in LEVEL_FIELDS}
    previous = {k: _avg(last_week, k) for k in LEVEL_FIELDS}
    trends = {k: scoring.describe_trend(current[k], previous[k]) if len(this_week) >= 2 and len(last_week) >= 2
              else None for k in LEVEL_FIELDS}
    latest = rows[-1] if rows else None
    return ok({
        "latest": checkin_dict(latest) if latest else None,
        "checked_in_today": bool(latest and latest.checkin_date == today),
        "last_7_days": {"checkins": len(this_week), "averages": current},
        "previous_7_days": {"checkins": len(last_week), "averages": previous},
        "trends": trends,
        "history": [{"date": r.checkin_date.isoformat(), **{k: getattr(r, k) for k in LEVEL_FIELDS}} for r in rows],
        "definitions": scoring.INDICATOR_DEFINITIONS,
        "scoring_version": scoring.SCORING_VERSION,
        "disclaimer": "These indicators summarise your own answers. They are a project-specific reflection aid, "
                      "not a clinical assessment or diagnosis.",
    })


@bp.get("/wellness/methodology")
def methodology():
    return ok({
        "version": scoring.SCORING_VERSION,
        "weights": scoring.WEIGHTS,
        "min_components_for_index": scoring.MIN_COMPONENTS_FOR_INDEX,
        "definitions": scoring.INDICATOR_DEFINITIONS,
        "stressor_categories": scoring.STRESSOR_CATEGORIES,
        "normalisation": {
            "likert": "(answer - 1) / 4 x 100",
            "sleep_hours": "100 for 7-9 hours, falling linearly to 0 at 3 hours and at 13 hours",
            "sleep_score": "mean of sleep-quality level and sleep-hours score (whichever are answered)",
            "wellness_index": "weighted mean of mood, 100-stress, 100-worry, sleep, 100-academic pressure; "
                              "weights re-normalised over answered items; needs 3 of 5",
        },
        "clinical_status": "Not clinically validated. Not a screening or diagnostic tool.",
    })
