"""XP, levels, streaks and badges. Everything here is computed server-side.

Rules (documented in docs/GAMIFICATION.md):
* XP comes only from the ledger (xp_transactions). Each source (a check-in, an
  activity completion) can award XP at most once — enforced by a unique key.
* Level L requires LEVEL_XP_STEP * L * (L - 1) total XP (L1 = 0, L2 = 50, L3 = 150 ...).
* An "active day" is a local calendar day with at least one check-in or completed activity.
* The streak counts consecutive active days. Missing a day simply starts a new streak
  on the next active day. XP, levels and badges are never taken away.
"""
from datetime import timedelta

from flask import current_app
from sqlalchemy import func

from ..extensions import db
from ..models import (Activity, ActivityCompletion, Badge, CheckIn, StudentBadge, StudentProgress,
                      XPTransaction)
from ..utils import iso, local_today


def xp_for_duration(minutes, app_config=None):
    cfg = app_config or current_app.config
    raw = minutes * cfg["XP_PER_ACTIVITY_MINUTE"]
    return max(cfg["XP_ACTIVITY_MIN"], min(cfg["XP_ACTIVITY_MAX"], raw))


def level_info(total_xp):
    step = current_app.config["LEVEL_XP_STEP"]
    level = 1
    while step * (level + 1) * level <= total_xp:
        level += 1
    floor = step * level * (level - 1)
    nxt = step * (level + 1) * level
    return {
        "level": level,
        "total_xp": total_xp,
        "level_floor_xp": floor,
        "next_level_xp": nxt,
        "progress_pct": round((total_xp - floor) / (nxt - floor) * 100, 1),
    }


def get_progress(student_id):
    progress = db.session.get(StudentProgress, student_id)
    if progress is None:
        progress = StudentProgress(student_id=student_id, total_xp=0, current_streak=0, longest_streak=0)
        db.session.add(progress)
        db.session.flush()
    return progress


def award_xp(student_id, amount, reason, source_type, source_id):
    """Idempotent: returns 0 if this source already earned XP."""
    exists = XPTransaction.query.filter_by(source_type=source_type, source_id=source_id).first()
    if exists or amount <= 0:
        return 0
    db.session.add(XPTransaction(student_id=student_id, amount=amount, reason=reason[:120],
                                 source_type=source_type, source_id=source_id))
    progress = get_progress(student_id)
    progress.total_xp = (progress.total_xp or 0) + amount
    return amount


def record_active_day(student_id, day):
    progress = get_progress(student_id)
    last = progress.last_active_date
    if last == day:
        return progress
    if last is not None and last > day:
        return progress  # never rewrite history for backdated events
    if last is not None and day - last == timedelta(days=1):
        progress.current_streak = (progress.current_streak or 0) + 1
    else:
        progress.current_streak = 1
    progress.longest_streak = max(progress.longest_streak or 0, progress.current_streak)
    progress.last_active_date = day
    return progress


def displayed_streak(progress, today=None):
    """A streak is 'current' if the student was active today or yesterday."""
    today = today or local_today()
    if progress.last_active_date is None:
        return 0
    if today - progress.last_active_date <= timedelta(days=1):
        return progress.current_streak
    return 0


def _count_category(student_id, categories):
    return (db.session.query(func.count(ActivityCompletion.id))
            .join(Activity, Activity.id == ActivityCompletion.activity_id)
            .filter(ActivityCompletion.student_id == student_id, Activity.category.in_(categories))
            .scalar())


def evaluate_badges(student_id):
    """Award any newly satisfied badges. Returns the list of newly earned badge dicts."""
    progress = get_progress(student_id)
    owned = {code for (code,) in db.session.query(Badge.code).join(StudentBadge)
             .filter(StudentBadge.student_id == student_id).all()}
    completions = ActivityCompletion.query.filter_by(student_id=student_id).count()
    checkins = CheckIn.query.filter_by(student_id=student_id).count()
    distinct_categories = (db.session.query(func.count(func.distinct(Activity.category)))
                           .join(ActivityCompletion, Activity.id == ActivityCompletion.activity_id)
                           .filter(ActivityCompletion.student_id == student_id).scalar())
    lvl = level_info(progress.total_xp)["level"]

    rules = {
        "first_checkin": checkins >= 1,
        "first_activity": completions >= 1,
        "streak_3": (progress.longest_streak or 0) >= 3,
        "streak_7": (progress.longest_streak or 0) >= 7,
        "breathing_5": _count_category(student_id, ["breathing"]) >= 5,
        "journal_5": _count_category(student_id, ["journaling", "gratitude"]) >= 5,
        "explorer": distinct_categories >= 4,
        "level_5": lvl >= 5,
    }
    new = []
    badges = {b.code: b for b in Badge.query.all()}
    for code, satisfied in rules.items():
        if satisfied and code not in owned and code in badges:
            db.session.add(StudentBadge(student_id=student_id, badge_id=badges[code].id))
            new.append(badge_dict(badges[code]))
    return new


def badge_dict(badge, earned_at=None):
    return {"code": badge.code, "name": badge.name, "description": badge.description,
            "icon": badge.icon, "earned_at": iso(earned_at)}


def summary(student_id):
    progress = get_progress(student_id)
    info = level_info(progress.total_xp)
    info.update({
        "current_streak": displayed_streak(progress),
        "longest_streak": progress.longest_streak or 0,
        "last_active_date": iso(progress.last_active_date),
    })
    return info
