"""Daily activity suggestions.

Transparent rules on the student's most recent check-in (last 3 days). Each rule
yields a plain-language reason that is shown to the student. At most 3 suggestions
per day; dismissed ones are not re-added that day. Students are never required
to do any of them.
"""
from datetime import timedelta

from ..extensions import db
from ..models import Activity, ActivityRecommendation, CheckIn
from ..utils import local_today

DAILY_LIMIT = 3
FALLBACK_ROTATION = ["five-senses-grounding", "pomodoro-study-break", "three-good-things",
                     "mindful-walk", "progressive-relaxation", "five-minute-breathing-reset"]


def _rules(checkin):
    if checkin is None:
        return []
    out = []
    if (checkin.stress_level or 0) >= 50 or (checkin.anxiety_level or 0) >= 50:
        out.append(("box-breathing-4", "You mentioned feeling stressed or on edge recently."))
    if checkin.sleep_score is not None and checkin.sleep_score < 50:
        out.append(("sleep-wind-down", "Your recent check-in mentioned less restful sleep."))
    if (checkin.academic_pressure_level or 0) >= 50:
        out.append(("weekly-priorities", "You reported a lot of academic pressure."))
    if checkin.mood_level is not None and checkin.mood_level <= 50:
        out.append(("three-good-things", "A small gratitude reflection can be a gentle lift on low days."))
    return out


def ensure_today(student_id):
    today = local_today()
    recs = ActivityRecommendation.query.filter_by(student_id=student_id, for_date=today).all()
    if any(r.source == "rule" for r in recs):
        return recs

    latest = (CheckIn.query.filter(CheckIn.student_id == student_id,
                                   CheckIn.checkin_date >= today - timedelta(days=3))
              .order_by(CheckIn.checkin_date.desc()).first())
    candidates = _rules(latest)
    rotation_start = today.toordinal() % len(FALLBACK_ROTATION)
    for i in range(len(FALLBACK_ROTATION)):
        slug = FALLBACK_ROTATION[(rotation_start + i) % len(FALLBACK_ROTATION)]
        candidates.append((slug, "A short activity picked for today."))

    by_slug = {a.slug: a for a in Activity.query.filter(Activity.slug.isnot(None), Activity.is_active).all()}
    taken = {r.activity_id for r in recs}
    added = 0
    for slug, reason in candidates:
        if added >= DAILY_LIMIT:
            break
        activity = by_slug.get(slug)
        if activity is None or activity.id in taken:
            continue
        rec = ActivityRecommendation(student_id=student_id, activity_id=activity.id, for_date=today,
                                     source="rule", reason=reason)
        db.session.add(rec)
        recs.append(rec)
        taken.add(activity.id)
        added += 1
    db.session.commit()
    return recs


def add_recommendation(student_id, activity_id, source, reason):
    today = local_today()
    rec = ActivityRecommendation.query.filter_by(student_id=student_id, activity_id=activity_id,
                                                 for_date=today).first()
    if rec is None:
        rec = ActivityRecommendation(student_id=student_id, activity_id=activity_id, for_date=today,
                                     source=source, reason=reason[:200])
        db.session.add(rec)
    elif rec.status == "dismissed":
        rec.status = "suggested"
    return rec
