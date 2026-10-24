"""Aggregate, de-identified class statistics for teachers.

Privacy rules implemented here (server-side, not in the UI):
* Only students who explicitly opted in (ClassMembership.share_aggregates) contribute.
* Inputs are check-in numbers and activity completions only — never chats, notes or journals.
* Each student's values are first averaged within the week, so every contributor counts once.
* Any week with fewer than MIN_COHORT_SIZE contributors is suppressed entirely, and the
  exact count below the threshold is not revealed.
* Filters are restricted to fixed period lengths (4, 8 or 12 weeks) on whole weeks — there
  are no demographic or per-student filters to combine.
* Values are rounded to whole numbers. No ranking, no per-student rows, no drill-down.
"""
from collections import defaultdict
from datetime import timedelta
from statistics import mean

from flask import current_app

from ..extensions import db
from ..models import Activity, ActivityCompletion, CheckIn, ClassMembership
from ..utils import local_today, week_start
from .scoring import STRESSOR_CATEGORIES, describe_trend

ALLOWED_PERIODS = (4, 8, 12)
METRICS = {
    "wellness_index": "Wellness index (higher = better)",
    "stress_level": "Stress level (higher = more stress)",
    "anxiety_level": "Worry level (higher = more worry)",
    "academic_pressure_level": "Academic pressure (higher = more pressure)",
    "sleep_score": "Sleep score (higher = better)",
    "mood_level": "Mood (higher = better)",
}


def _rnd(v):
    return None if v is None else int(round(v))


def class_statistics(classroom, weeks):
    k = current_app.config["MIN_COHORT_SIZE"]
    memberships = ClassMembership.query.filter_by(class_id=classroom.id).all()
    consenting = [m.student_id for m in memberships if m.share_aggregates]
    today = local_today()
    first_week = week_start(today) - timedelta(weeks=weeks - 1)

    result = {
        "class_id": classroom.id,
        "class_name": classroom.name,
        "period_weeks": weeks,
        "min_cohort_size": k,
        "member_count": len(memberships),
        "contributing_members": len(consenting) if len(consenting) >= k else None,
        "sufficient_data": len(consenting) >= k,
        "weeks": [],
        "metric_labels": METRICS,
        "stressor_labels": STRESSOR_CATEGORIES,
        "source": "recorded_self_reports",
    }
    if len(consenting) < k:
        return result

    checkins = (CheckIn.query.filter(CheckIn.student_id.in_(consenting), CheckIn.checkin_date >= first_week)
                .all())
    completions = (db.session.query(ActivityCompletion.student_id, ActivityCompletion.completion_date,
                                    Activity.category)
                   .join(Activity, Activity.id == ActivityCompletion.activity_id)
                   .filter(ActivityCompletion.student_id.in_(consenting),
                           ActivityCompletion.completion_date >= first_week).all())

    by_week_student = defaultdict(lambda: defaultdict(list))
    stressors_by_week = defaultdict(lambda: defaultdict(set))
    for c in checkins:
        wk = week_start(c.checkin_date)
        by_week_student[wk][c.student_id].append(c)
        for code in (c.stressors or []):
            if code in STRESSOR_CATEGORIES:
                stressors_by_week[wk][code].add(c.student_id)

    comp_by_week = defaultdict(list)
    for sid, d, cat in completions:
        comp_by_week[week_start(d)].append((sid, cat))

    for i in range(weeks):
        wk = first_week + timedelta(weeks=i)
        students = by_week_student.get(wk, {})
        n = len(students)
        entry = {"week_start": wk.isoformat(), "is_current_week": wk == week_start(today)}
        if n >= k:
            metrics = {}
            for key in METRICS:
                per_student = []
                for rows in students.values():
                    vals = [getattr(r, key) for r in rows if getattr(r, key) is not None]
                    if vals:
                        per_student.append(mean(vals))
                metrics[key] = _rnd(mean(per_student)) if len(per_student) >= k else None
            entry.update({
                "suppressed": False,
                "contributors": n,
                "metrics": metrics,
                "stressors_pct": {code: _rnd(len(ids) / n * 100)
                                  for code, ids in stressors_by_week.get(wk, {}).items()},
            })
        else:
            entry.update({"suppressed": True, "contributors": None, "metrics": None, "stressors_pct": None})

        comps = comp_by_week.get(wk, [])
        participants = {sid for sid, _ in comps}
        by_cat = defaultdict(int)
        for _, cat in comps:
            by_cat[cat] += 1
        entry["participation"] = {
            "participation_pct": _rnd(len(participants) / len(consenting) * 100),
            "completions": len(comps),
            "by_category": dict(by_cat) if len(participants) >= k else None,
        }
        result["weeks"].append(entry)
    return result


def _last_two(weeks_data):
    visible = [w for w in weeks_data if not w["suppressed"]]
    return (visible[-2], visible[-1]) if len(visible) >= 2 else (None, visible[-1] if visible else None)


def rule_based_observations(stats):
    """Deterministic observations computed directly from the statistics (no AI)."""
    if not stats["sufficient_data"]:
        return [{"text": f"Not enough students have opted in to share anonymous statistics yet "
                         f"(at least {stats['min_cohort_size']} are needed), so no class trends are shown.",
                 "metric": "general", "kind": "data_availability"}]
    prev, last = _last_two(stats["weeks"])
    obs = []
    if last is None:
        return [{"text": "No week in this period has enough check-ins to show aggregate figures.",
                 "metric": "general", "kind": "data_availability"}]
    if prev is None:
        obs.append({"text": "Only one week in this period has enough check-ins, so changes over time can't be described yet.",
                    "metric": "general", "kind": "data_availability"})
    else:
        for key, label in [("academic_pressure_level", "academic pressure"), ("stress_level", "stress"),
                           ("wellness_index", "wellness index"), ("sleep_score", "sleep score")]:
            trend = describe_trend(last["metrics"].get(key), prev["metrics"].get(key))
            if trend and trend["direction"] != "steady":
                word = "rose" if trend["direction"] == "up" else "fell"
                obs.append({
                    "text": f"Average self-reported {label} {word} from {prev['metrics'][key]} to "
                            f"{last['metrics'][key]} (out of 100) between the weeks of {prev['week_start']} "
                            f"and {last['week_start']}.",
                    "metric": key, "kind": "trend"})
    stressors = last.get("stressors_pct") or {}
    if stressors:
        code, pct = max(stressors.items(), key=lambda kv: kv[1])
        if pct >= 40:
            obs.append({"text": f"In the week of {last['week_start']}, {pct}% of contributing students selected "
                                f"'{STRESSOR_CATEGORIES[code]}' as something weighing on them.",
                        "metric": f"stressor:{code}", "kind": "stressor"})
    weeks = stats["weeks"]
    if len(weeks) >= 2:
        a, b = weeks[-2]["participation"]["participation_pct"], weeks[-1]["participation"]["participation_pct"]
        if a is not None and b is not None and abs(b - a) >= 10:
            word = "increased" if b > a else "decreased"
            obs.append({"text": f"Participation in wellness activities {word} from {a}% to {b}% of opted-in "
                                f"students week-on-week{' (current week still in progress)' if weeks[-1]['is_current_week'] else ''}.",
                        "metric": "participation", "kind": "participation"})
    return obs


SUGGESTIONS = {
    "academic_pressure_level": "Consider a short, optional study-planning or exam-preparation session for the class.",
    "stress_level": "Consider reminding the class about campus counselling services and Tele-MANAS (14416), and building in a short break during long sessions.",
    "sleep_score": "Consider sharing general sleep-hygiene tips and avoiding very late deadlines where possible.",
    "wellness_index": "Consider an informal check-in with the whole class about workload, and reminding students where support is available.",
    "participation": "Consider mentioning that short wellbeing activities are available and entirely optional.",
}


def rule_based_suggestions(observations):
    seen, out = set(), []
    for o in observations:
        key = o["metric"] if not o["metric"].startswith("stressor") else "stress_level"
        if o["kind"] in ("trend", "stressor", "participation") and key in SUGGESTIONS and key not in seen:
            seen.add(key)
            out.append(SUGGESTIONS[key])
    return out


def ai_input(stats):
    """The ONLY data passed to the insight model: suppressed weekly aggregates, no identifiers."""
    return {
        "period_weeks": stats["period_weeks"],
        "min_cohort_size": stats["min_cohort_size"],
        "weeks": [{k: w[k] for k in ("week_start", "is_current_week", "suppressed", "contributors", "metrics",
                                    "stressors_pct", "participation")} for w in stats["weeks"]],
        "metric_definitions": METRICS,
        "stressor_labels": STRESSOR_CATEGORIES,
    }
