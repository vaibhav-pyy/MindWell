"""MindWell Wellness Indicators — scoring version mw-1.

A project-specific, NON-CLINICAL self-reflection framework. It is not a validated
screening instrument and must never be used to diagnose or label anyone.
Full methodology: docs/WELLNESS_SCORING.md (keep the two in sync).

Inputs come only from the student's own daily check-in. Nothing here is inferred
from chat messages.

Item scales (1-5 Likert unless noted):
    stress            1 = not at all stressed ... 5 = extremely stressed
    anxiety           1 = not at all worried/on edge ... 5 = extremely
    mood              1 = very low ... 5 = very good
    sleep_quality     1 = very poor ... 5 = very good
    sleep_hours       0-16 hours (last night)
    academic_pressure 1 = none ... 5 = overwhelming

Normalisation to 0-100:
    level(x) = (x - 1) / 4 * 100       (keeps the item's own direction)
    sleep_hours_score(h) = 100 for 7 <= h <= 9, falling linearly to 0 at 3 h and at 13 h
    sleep_score = mean of available {level(sleep_quality), sleep_hours_score(sleep_hours)}

Wellness index (higher = better self-reported wellbeing), weighted mean over the
components that were answered, weights re-normalised to the answered set:
    mood                     0.25
    100 - stress_level       0.20
    100 - anxiety_level      0.20
    sleep_score              0.20
    100 - academic_pressure  0.15
At least 3 of the 5 components must be present, otherwise the index is None
("not enough information").
"""
from statistics import mean

SCORING_VERSION = "mw-1"
MIN_COMPONENTS_FOR_INDEX = 3

WEIGHTS = {
    "mood": 0.25,
    "stress": 0.20,
    "anxiety": 0.20,
    "sleep": 0.20,
    "academic_pressure": 0.15,
}

STRESSOR_CATEGORIES = {
    "exams": "Exams",
    "assignments": "Assignments & deadlines",
    "sleep": "Sleep",
    "relationships": "Friends & relationships",
    "family": "Family",
    "finances": "Finances",
    "health": "Health",
    "future": "Career & future",
    "other": "Something else",
}

INDICATOR_DEFINITIONS = {
    "stress_level": "How stressed you said you felt today (0 = not at all, 100 = extremely). Higher means more stress.",
    "anxiety_level": "How worried, nervous or on edge you said you felt (0 = not at all, 100 = extremely). Higher means more worry.",
    "mood_level": "How you rated your overall mood (0 = very low, 100 = very good). Higher is better.",
    "sleep_score": "Blend of your sleep-quality rating and how close last night's sleep was to 7-9 hours. Higher is better.",
    "academic_pressure_level": "How much academic pressure you reported (0 = none, 100 = overwhelming). Higher means more pressure.",
    "wellness_index": "A weighted summary of the above (higher is better). A project-specific reflection aid, not a clinical score.",
}


def level(x):
    return None if x is None else round((x - 1) / 4 * 100, 1)


def sleep_hours_score(hours):
    if hours is None:
        return None
    if 7 <= hours <= 9:
        return 100.0
    if hours < 7:
        return round(max(0.0, (hours - 3) / 4 * 100), 1)
    return round(max(0.0, (13 - hours) / 4 * 100), 1)


def compute(stress=None, anxiety=None, mood=None, sleep_hours=None, sleep_quality=None, academic_pressure=None):
    stress_level = level(stress)
    anxiety_level = level(anxiety)
    mood_level = level(mood)
    academic_level = level(academic_pressure)
    sleep_parts = [v for v in (level(sleep_quality), sleep_hours_score(sleep_hours)) if v is not None]
    sleep_score = round(mean(sleep_parts), 1) if sleep_parts else None

    components = {
        "mood": mood_level,
        "stress": None if stress_level is None else 100 - stress_level,
        "anxiety": None if anxiety_level is None else 100 - anxiety_level,
        "sleep": sleep_score,
        "academic_pressure": None if academic_level is None else 100 - academic_level,
    }
    present = {k: v for k, v in components.items() if v is not None}
    if len(present) >= MIN_COMPONENTS_FOR_INDEX:
        total_weight = sum(WEIGHTS[k] for k in present)
        index = round(sum(WEIGHTS[k] * v for k, v in present.items()) / total_weight, 1)
    else:
        index = None

    return {
        "stress_level": stress_level,
        "anxiety_level": anxiety_level,
        "mood_level": mood_level,
        "sleep_score": sleep_score,
        "academic_pressure_level": academic_level,
        "wellness_index": index,
        "items_answered": len(present),
        "scoring_version": SCORING_VERSION,
    }


def apply_to_checkin(checkin):
    result = compute(checkin.stress, checkin.anxiety, checkin.mood, checkin.sleep_hours,
                     checkin.sleep_quality, checkin.academic_pressure)
    for key, value in result.items():
        setattr(checkin, key, value)
    return checkin


def describe_trend(current, previous, threshold=5.0):
    """Plain-language, non-diagnostic description of a change between two averages."""
    if current is None or previous is None:
        return None
    diff = round(current - previous, 1)
    if abs(diff) < threshold:
        return {"direction": "steady", "change": diff}
    return {"direction": "up" if diff > 0 else "down", "change": diff}
