"""Validation of Gemini JSON before anything is stored or shown.

The model's output is treated as untrusted data: only whitelisted fields are read,
lengths and enums are enforced, unsafe content is rejected, and any field that
looks like a privileged instruction (XP, permissions, emergency settings) is ignored.
"""
import re

from ..models import ACTIVITY_CATEGORIES, ACTIVITY_KINDS, DIFFICULTIES
from .gemini import USER_MESSAGES, AIUnavailable

# Terms that must never appear in AI-generated activities.
UNSAFE_ACTIVITY_TERMS = [
    r"\bmedicat", r"\bpill", r"\bdose\b", r"\bdosage", r"\bsupplement", r"\balcohol", r"\bcannabis", r"\bweed\b",
    r"\bfast(ing)?\b", r"\bstarv", r"\bskip (a )?meals?", r"\bice bath", r"\bcold plunge", r"\bcold shower",
    r"\bhold (your|the) breath for (8|9|\d{2,}) ", r"\bhyperventilat", r"\bblade", r"\bknife",
    r"\bdiagnos", r"\bcure[sd]?\b", r"\btreat(s|ment)? (your|the) (anxiety|depression|disorder)",
    r"\bclinically proven", r"\bguaranteed?\b", r"\bat night alone\b", r"\bmidnight walk",
]
DIAGNOSTIC_TERMS = [
    r"\bdiagnos", r"\bdisorder\b", r"\bclinical(ly)? (depress|anxious|anxiety)", r"\bmentally ill\b",
    r"\bsuffers? from\b", r"\bhas (depression|anxiety|adhd|ocd|ptsd|bipolar)", r"\bpsychiatric condition",
    r"\bat[- ]risk students?\b", r"\bidentify (the )?students\b", r"\bsingle out\b", r"\bdisciplin",
    r"\bstatistically significant\b",
]
_unsafe = [re.compile(p, re.I) for p in UNSAFE_ACTIVITY_TERMS]
_diag = [re.compile(p, re.I) for p in DIAGNOSTIC_TERMS]
_contact_info = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s-]{8,}\d")


def _invalid():
    return AIUnavailable("invalid_output", USER_MESSAGES["invalid_output"])


def _text(value, max_len, min_len=1):
    if not isinstance(value, str):
        raise _invalid()
    value = value.strip()
    if not (min_len <= len(value) <= max_len):
        raise _invalid()
    return value


def validate_chat(data, catalog_slugs):
    reply = _text(data.get("reply"), 4000)
    risk = data.get("risk_level")
    if risk not in ("none", "elevated", "high"):
        raise _invalid()
    slugs = data.get("suggested_activity_slugs") or []
    if not isinstance(slugs, list):
        raise _invalid()
    slugs = [s for s in slugs if isinstance(s, str) and s in catalog_slugs][:2]
    if risk == "high":
        slugs = []
    title = data.get("conversation_title")
    title = title.strip()[:80] if isinstance(title, str) and title.strip() else None
    return {"reply": reply, "risk_level": risk, "slugs": slugs, "title": title}


def validate_summary(data):
    summary = data.get("summary")
    if not isinstance(summary, str):
        raise _invalid()
    summary = summary.strip()
    if not summary:
        return None
    if len(summary) > 600 or any(p.search(summary) for p in _diag):
        raise _invalid()
    # Strip anything that looks like contact details rather than storing it.
    return _contact_info.sub("[removed]", summary)


def validate_activity(data, max_minutes):
    title = _text(data.get("title"), 80, 3)
    description = _text(data.get("description"), 400, 10)
    category = data.get("category")
    kind = data.get("kind")
    difficulty = data.get("difficulty")
    if category not in ACTIVITY_CATEGORIES or kind not in ACTIVITY_KINDS or difficulty not in DIFFICULTIES:
        raise _invalid()
    steps = data.get("instructions")
    if not isinstance(steps, list) or not 3 <= len(steps) <= 8:
        raise _invalid()
    steps = [_text(s, 240, 3) for s in steps]
    prompts = data.get("journal_prompts") or []
    if not isinstance(prompts, list):
        raise _invalid()
    prompts = [_text(p, 240, 3) for p in prompts][:4]
    if kind == "journal" and len(prompts) < 1:
        raise _invalid()
    duration = data.get("duration_minutes")
    if isinstance(duration, bool) or not isinstance(duration, int) or not 2 <= duration <= min(20, max_minutes):
        raise _invalid()
    criteria = _text(data.get("completion_criteria"), 300, 5)
    safety = data.get("safety_notes")
    safety = safety.strip()[:300] if isinstance(safety, str) else ""

    blob = " ".join([title, description, criteria, safety, *steps, *prompts])
    if any(p.search(blob) for p in _unsafe) or _contact_info.search(blob):
        raise _invalid()
    # 'suggested_xp' and any other keys are deliberately ignored: rewards are set by the backend.
    return {
        "title": title, "description": description, "category": category, "kind": kind,
        "instructions": steps, "journal_prompts": prompts, "duration_minutes": duration,
        "difficulty": difficulty, "completion_criteria": criteria, "safety_notes": safety,
    }


def validate_insight(data, allowed_metrics):
    obs = data.get("observations")
    sug = data.get("suggestions")
    cav = data.get("caveats")
    if not all(isinstance(x, list) for x in (obs, sug, cav)):
        raise _invalid()
    observations = []
    for item in obs[:4]:
        if not isinstance(item, dict):
            raise _invalid()
        text = _text(item.get("text"), 400, 5)
        metric = item.get("metric") if item.get("metric") in allowed_metrics else "general"
        observations.append({"text": text, "metric": metric})
    suggestions = [_text(s, 400, 5) for s in sug[:4]]
    caveats = [_text(c, 400, 5) for c in cav[:3]]
    blob = " ".join([o["text"] for o in observations] + suggestions + caveats)
    if any(p.search(blob) for p in _diag):
        raise _invalid()
    return {"observations": observations, "suggestions": suggestions, "caveats": caveats}
