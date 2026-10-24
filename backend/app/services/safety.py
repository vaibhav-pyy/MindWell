"""Conservative, deterministic safety screen that runs BEFORE any AI call.

It is deliberately simple and auditable: phrase patterns that indicate possible
self-harm or suicide intent ("crisis") or serious distress ("concern"). It will
miss things and will sometimes over-trigger — both are documented limitations.
A positive result only changes what the student is SHOWN (a support panel and a
fixed safety message); it never contacts anyone automatically.
"""
import re

# Patterns are matched against a lower-cased, whitespace-normalised message.
CRISIS_PATTERNS = [
    r"\b(kill|killing|hurt|hurting|harm|harming)\s+my\s?self\b",
    r"\bkms\b",
    r"\bsuicid",
    r"\bend(ing)?\s+(my|it|this)\s+(life|all)\b",
    r"\bend\s+it\s+all\b",
    r"\b(want|wanna|going|plan|planning)\s+to\s+die\b",
    r"\bdon'?t\s+want\s+to\s+(live|be\s+alive|exist|wake\s+up)\b",
    r"\b(no|not\s+any)\s+(reason|point)\s+(to|in)\s+(live|living|go\s+on|going\s+on)\b",
    r"\bbetter\s+off\s+(dead|without\s+me)\b",
    r"\b(take|taking)\s+my\s+(own\s+)?life\b",
    r"\bself[\s-]?harm",
    r"\bcut(ting)?\s+my\s?self\b",
    r"\boverdose\b",
    r"\bjump\s+off\b",
    r"\bhang\s+my\s?self\b",
    r"\bsleeping\s+pills\s+to\b",
    # Common Hinglish / Hindi (romanised) expressions
    r"\bkhudkushi\b",
    r"\baatmahatya\b",
    r"\bmarna\s+chah?ta\b",
    r"\bmarna\s+chah?ti\b",
    r"\bmar\s+jaun?a?\b",
    r"\bjeena\s+nahi\s+chah?t",
]

CONCERN_PATTERNS = [
    r"\bhopeless\b",
    r"\bcan'?t\s+(go\s+on|take\s+(it|this)\s+any\s?more|cope)\b",
    r"\bgive\s+up\s+on\s+(everything|life)\b",
    r"\bnobody\s+would\s+(care|notice|miss\s+me)\b",
    r"\bworthless\b",
    r"\bpanic\s+attack",
    r"\b(being|been|getting)\s+(abused|hit|beaten)\b",
    r"\bnot\s+safe\b",
]

_crisis = [re.compile(p) for p in CRISIS_PATTERNS]
_concern = [re.compile(p) for p in CONCERN_PATTERNS]


def screen(text: str) -> str:
    """Return 'crisis', 'concern' or 'none'."""
    norm = re.sub(r"\s+", " ", (text or "").lower()).replace("’", "'")
    if any(p.search(norm) for p in _crisis):
        return "crisis"
    if any(p.search(norm) for p in _concern):
        return "concern"
    return "none"


def combine(rule_level: str, ai_risk: str | None) -> str:
    """Escalate-only combination: the AI can raise the level to show support, never lower a rule hit."""
    order = {"none": 0, "concern": 1, "crisis": 2}
    ai_level = {"high": "crisis", "elevated": "concern"}.get(ai_risk or "", "none")
    return rule_level if order[rule_level] >= order[ai_level] else ai_level


def crisis_message(helpline, emergency, has_contact: bool) -> str:
    """Fixed, human-written safety response. Shown instead of an AI reply on a crisis hit."""
    contact_line = ("You can call your trusted contact right now using the button below. "
                    if has_contact else
                    "If there is someone you trust nearby — a friend, family member, hostel warden or counsellor — please reach out to them now. ")
    return (
        "I'm really glad you told me, and I'm taking what you said seriously. "
        "It sounds like you're in a lot of pain right now, and you deserve support from a real person.\n\n"
        f"{contact_line}"
        f"You can also call {helpline['name']} on {helpline['short_code']} or {helpline['toll_free']} — "
        "it's free, confidential and available 24x7.\n\n"
        f"If you are in immediate danger or might act on these thoughts, please call {emergency['number']} "
        "or go to the nearest hospital emergency department.\n\n"
        "I'm an AI, so I can't contact anyone for you or check that you're safe, but I'm still here to keep talking "
        "while you reach out. Would you be willing to contact someone now?"
    )
