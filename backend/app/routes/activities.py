from flask import Blueprint, current_app, g
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from ..extensions import db, limiter, user_or_ip
from ..models import (Activity, ActivityCompletion, ActivityRecommendation, ActivitySession, Badge, JournalEntry,
                      StudentBadge, XPTransaction, utcnow)
from ..security import student_required
from ..services import ai_validation, gamification, prompts, recommendations
from ..services.gemini import AIUnavailable, get_ai, to_contents
from ..utils import ApiError, iso, json_body, local_today, ok, opt_int, req_bool, req_str

bp = Blueprint("activities", __name__, url_prefix="/api")

JOURNAL_MIN_CHARS = 20


def activity_dict(a):
    return {
        "id": a.id, "slug": a.slug, "title": a.title, "description": a.description, "category": a.category,
        "kind": a.kind, "instructions": a.instructions, "config": a.config or {},
        "duration_minutes": a.duration_minutes, "difficulty": a.difficulty,
        "completion_criteria": a.completion_criteria, "xp_reward": a.xp_reward, "safety_notes": a.safety_notes,
        "source": a.source, "is_personal": a.owner_student_id is not None,
    }


def visible_activity(activity_id):
    a = (Activity.query.filter(Activity.id == activity_id, Activity.is_active,
                               or_(Activity.owner_student_id.is_(None), Activity.owner_student_id == g.user.id))
         .first())
    if a is None:
        raise ApiError("Activity not found.", 404, "not_found")
    return a


@bp.get("/activities")
@student_required
def list_activities():
    rows = (Activity.query.filter(Activity.is_active,
                                  or_(Activity.owner_student_id.is_(None), Activity.owner_student_id == g.user.id))
            .order_by(Activity.owner_student_id.is_(None), Activity.created_at.desc()).all())
    return ok([activity_dict(a) for a in rows])


@bp.get("/activities/<int:activity_id>")
@student_required
def get_activity(activity_id):
    return ok(activity_dict(visible_activity(activity_id)))


@bp.delete("/activities/<int:activity_id>")
@student_required
def remove_personal_activity(activity_id):
    a = Activity.query.filter_by(id=activity_id, owner_student_id=g.user.id).first()
    if a is None:
        raise ApiError("Only your own AI-generated activities can be removed.", 404, "not_found")
    a.is_active = False
    db.session.commit()
    return ok({"removed": True})


@bp.get("/recommendations/today")
@student_required
def today_recommendations():
    recs = recommendations.ensure_today(g.user.id)
    out = []
    for r in recs:
        a = db.session.get(Activity, r.activity_id)
        if a and a.is_active:
            out.append({"id": r.id, "status": r.status, "source": r.source, "reason": r.reason,
                        "activity": activity_dict(a)})
    return ok(out)


@bp.post("/recommendations/<int:rec_id>/dismiss")
@student_required
def dismiss_recommendation(rec_id):
    rec = ActivityRecommendation.query.filter_by(id=rec_id, student_id=g.user.id).first()
    if rec is None:
        raise ApiError("Recommendation not found.", 404, "not_found")
    if rec.status == "suggested":
        rec.status = "dismissed"
        db.session.commit()
    return ok({"id": rec.id, "status": rec.status})


@bp.post("/activities/<int:activity_id>/sessions")
@student_required
@limiter.limit("60 per hour", key_func=user_or_ip)
def start_session(activity_id):
    a = visible_activity(activity_id)
    s = ActivitySession(student_id=g.user.id, activity_id=a.id)
    db.session.add(s)
    db.session.commit()
    min_seconds = int(a.duration_minutes * 60 * current_app.config["ACTIVITY_MIN_COMPLETION_RATIO"])
    return ok({"session_id": s.id, "started_at": iso(s.started_at), "min_seconds": min_seconds,
               "activity": activity_dict(a)}, 201)


def _completion_payload(completion, already, new_badges=None, note=None):
    return {"completion_id": completion.id, "already_completed": already, "xp_awarded": 0 if already else completion.xp_awarded,
            "xp_note": note, "new_badges": new_badges or [], "progress": gamification.summary(g.user.id)}


@bp.post("/activity-sessions/<int:session_id>/complete")
@student_required
def complete_session(session_id):
    """Completion rules: session belongs to the student, enough real time has passed (server clock),
    journal activities include some writing. Each session completes once; XP is awarded at most
    XP_AWARDS_PER_ACTIVITY_PER_DAY times per activity per day."""
    cfg = current_app.config
    session_row = ActivitySession.query.filter_by(id=session_id, student_id=g.user.id).first()
    if session_row is None:
        raise ApiError("Activity session not found.", 404, "not_found")
    existing = ActivityCompletion.query.filter_by(session_id=session_row.id).first()
    if existing:
        return ok(_completion_payload(existing, already=True))

    activity = db.session.get(Activity, session_row.activity_id)
    data = json_body()
    elapsed = int((utcnow() - session_row.started_at).total_seconds())
    min_seconds = int(activity.duration_minutes * 60 * cfg["ACTIVITY_MIN_COMPLETION_RATIO"])
    if elapsed < min_seconds:
        raise ApiError(f"This activity needs a little more time before it counts as complete "
                       f"({min_seconds - elapsed}s to go).", 422, "too_early",
                       {"seconds_remaining": min_seconds - elapsed})

    journal_text = None
    if activity.kind == "journal":
        journal_text = req_str(data, "journal_text", min_len=JOURNAL_MIN_CHARS, max_len=5000,
                               label="Your reflection")
    save_journal = req_bool(data, "save_to_journal", False)

    today = local_today()
    awarded_today = (ActivityCompletion.query
                     .filter(ActivityCompletion.student_id == g.user.id,
                             ActivityCompletion.activity_id == activity.id,
                             ActivityCompletion.completion_date == today,
                             ActivityCompletion.xp_awarded > 0).count())
    completion = ActivityCompletion(session_id=session_row.id, student_id=g.user.id, activity_id=activity.id,
                                    completion_date=today, elapsed_seconds=elapsed, xp_awarded=0)
    session_row.completed_at = utcnow()
    db.session.add(completion)
    try:
        db.session.flush()
    except IntegrityError:  # concurrent duplicate request for the same session
        db.session.rollback()
        existing = ActivityCompletion.query.filter_by(session_id=session_id).first()
        return ok(_completion_payload(existing, already=True))

    note = None
    if awarded_today < cfg["XP_AWARDS_PER_ACTIVITY_PER_DAY"]:
        completion.xp_awarded = gamification.award_xp(g.user.id, activity.xp_reward, f"Completed: {activity.title}",
                                                      "activity", completion.id)
    else:
        note = "You've already earned XP for this activity today — it still counts towards your streak."

    if journal_text and save_journal:
        prompt_list = (activity.config or {}).get("prompts") or []
        db.session.add(JournalEntry(student_id=g.user.id, completion_id=completion.id,
                                    prompt=(prompt_list[0] if prompt_list else activity.title)[:300],
                                    content=journal_text))
    (ActivityRecommendation.query
     .filter_by(student_id=g.user.id, activity_id=activity.id, for_date=today)
     .update({"status": "completed"}))
    gamification.record_active_day(g.user.id, today)
    new_badges = gamification.evaluate_badges(g.user.id)
    db.session.commit()
    return ok(_completion_payload(completion, already=False, new_badges=new_badges, note=note), 201)


@bp.post("/activities/generate")
@student_required
@limiter.limit("10 per hour", key_func=user_or_ip)
def generate_activity():
    if not g.user.student_profile.ai_processing_consent:
        raise ApiError("AI-generated activities need AI processing to be allowed in Privacy settings.", 403,
                       "ai_consent_required")
    data = json_body()
    concern = req_str(data, "concern", min_len=3, max_len=300, label="What's on your mind")
    minutes = opt_int(data, "available_minutes", 2, 20) or 5
    preference = data.get("preference")
    if preference not in (None, "", "breathing", "journal", "guided_steps"):
        raise ApiError("Unknown preference.", 422, "validation_error")
    request_text = (f"Student's concern (their words): {concern}\nAvailable time: {minutes} minutes\n"
                    f"Preferred type: {preference or 'no preference'}")
    try:
        raw = get_ai().generate_json(system_instruction=prompts.ACTIVITY_SYSTEM,
                                     contents=to_contents([("user", request_text)]),
                                     schema=prompts.ACTIVITY_SCHEMA, temperature=0.8, max_output_tokens=900)
        spec = ai_validation.validate_activity(raw, minutes)
    except AIUnavailable as exc:
        raise ApiError(exc.message, 503, "ai_unavailable", {"reason": exc.reason})

    config = {}
    if spec["kind"] == "journal":
        config["prompts"] = spec["journal_prompts"]
    elif spec["kind"] == "breathing":
        config["pattern"] = [{"phase": "Breathe in", "seconds": 4}, {"phase": "Breathe out", "seconds": 6}]
    else:
        config["seconds_per_step"] = max(20, int(spec["duration_minutes"] * 60 / len(spec["instructions"])))
    activity = Activity(
        title=spec["title"], description=spec["description"], category=spec["category"], kind=spec["kind"],
        instructions=spec["instructions"], config=config, duration_minutes=spec["duration_minutes"],
        difficulty=spec["difficulty"], completion_criteria=spec["completion_criteria"],
        safety_notes=spec["safety_notes"] or None, source="ai", owner_student_id=g.user.id,
        xp_reward=gamification.xp_for_duration(spec["duration_minutes"]),  # backend decides, never the AI
    )
    db.session.add(activity)
    db.session.flush()
    recommendations.add_recommendation(g.user.id, activity.id, "ai", "Created for you by the AI from what you shared.")
    db.session.commit()
    return ok(activity_dict(activity), 201)


@bp.get("/progress")
@student_required
def progress():
    sid = g.user.id
    earned = {sb.badge_id: sb.earned_at for sb in StudentBadge.query.filter_by(student_id=sid).all()}
    badges = [{**gamification.badge_dict(b, earned.get(b.id)), "earned": b.id in earned}
              for b in Badge.query.order_by(Badge.id).all()]
    ledger = (XPTransaction.query.filter_by(student_id=sid).order_by(XPTransaction.created_at.desc())
              .limit(20).all())
    recent = (db.session.query(ActivityCompletion, Activity).join(Activity, Activity.id == ActivityCompletion.activity_id)
              .filter(ActivityCompletion.student_id == sid).order_by(ActivityCompletion.created_at.desc())
              .limit(10).all())
    return ok({
        "summary": gamification.summary(sid),
        "badges": badges,
        "xp_history": [{"amount": x.amount, "reason": x.reason, "at": iso(x.created_at)} for x in ledger],
        "recent_completions": [{"activity_id": a.id, "title": a.title, "category": a.category,
                                "xp_awarded": c.xp_awarded, "at": iso(c.created_at)} for c, a in recent],
        "rules": {
            "checkin_xp": current_app.config["XP_CHECKIN"],
            "level_formula": f"Level L needs {current_app.config['LEVEL_XP_STEP']} x L x (L-1) XP",
            "streak": "A day counts when you check in or complete an activity. Missing a day just starts a "
                      "new streak — you never lose XP, levels or badges.",
            "daily_xp_cap": current_app.config["XP_AWARDS_PER_ACTIVITY_PER_DAY"],
        },
    })


@bp.get("/journal")
@student_required
def list_journal():
    rows = JournalEntry.query.filter_by(student_id=g.user.id).order_by(JournalEntry.created_at.desc()).limit(100).all()
    return ok([{"id": j.id, "prompt": j.prompt, "content": j.content, "created_at": iso(j.created_at)} for j in rows])


@bp.delete("/journal/<int:entry_id>")
@student_required
def delete_journal(entry_id):
    j = JournalEntry.query.filter_by(id=entry_id, student_id=g.user.id).first()
    if j is None:
        raise ApiError("Journal entry not found.", 404, "not_found")
    db.session.delete(j)
    db.session.commit()
    return ok({"deleted": True})
