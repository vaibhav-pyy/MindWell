"""Reference data: built-in activity catalog and badge definitions (idempotent upsert)."""
from .extensions import db
from .models import Activity, Badge
from .services.gamification import xp_for_duration

BUILTIN_ACTIVITIES = [
    {
        "slug": "box-breathing-4",
        "title": "Calm Breathing (4-4-6)",
        "description": "A paced breathing exercise: breathe in for 4, hold for 4, breathe out slowly for 6.",
        "category": "breathing", "kind": "breathing", "duration_minutes": 4, "difficulty": "easy",
        "instructions": ["Sit comfortably and relax your shoulders.",
                         "Follow the circle: breathe in through your nose as it grows.",
                         "Hold gently while it pauses.",
                         "Breathe out slowly through your mouth as it shrinks.",
                         "If you feel light-headed, stop and breathe normally."],
        "config": {"pattern": [{"phase": "Breathe in", "seconds": 4}, {"phase": "Hold", "seconds": 4},
                               {"phase": "Breathe out", "seconds": 6}]},
        "completion_criteria": "Follow the breathing guide for at least 60% of the session time.",
        "safety_notes": "Stop if you feel dizzy or uncomfortable. Breathing exercises are not a substitute for medical care.",
    },
    {
        "slug": "five-minute-breathing-reset",
        "title": "5-Minute Breathing Reset",
        "description": "A slightly longer, gentle breathing session (in 4, out 6) to slow down between study blocks.",
        "category": "breathing", "kind": "breathing", "duration_minutes": 5, "difficulty": "easy",
        "instructions": ["Put your phone on silent if you can.", "Breathe in for 4 as the circle grows.",
                         "Breathe out for 6 as it shrinks.", "Let your thoughts come and go without judging them."],
        "config": {"pattern": [{"phase": "Breathe in", "seconds": 4}, {"phase": "Breathe out", "seconds": 6}]},
        "completion_criteria": "Follow the breathing guide for at least 60% of the session time.",
        "safety_notes": "Stop if you feel dizzy. Breathe normally whenever you need to.",
    },
    {
        "slug": "five-senses-grounding",
        "title": "5-4-3-2-1 Grounding",
        "description": "Bring attention back to the present by noticing things around you with each sense.",
        "category": "mindfulness", "kind": "guided_steps", "duration_minutes": 3, "difficulty": "easy",
        "instructions": ["Notice 5 things you can see around you.", "Notice 4 things you can physically feel.",
                         "Notice 3 things you can hear.", "Notice 2 things you can smell (or like the smell of).",
                         "Notice 1 thing you can taste, or take one slow sip of water."],
        "config": {"seconds_per_step": 30},
        "completion_criteria": "Go through all five steps.",
        "safety_notes": None,
    },
    {
        "slug": "worry-journal",
        "title": "Worry Download Journal",
        "description": "Write down what's on your mind, then separate what you can act on from what you can't control.",
        "category": "journaling", "kind": "journal", "duration_minutes": 5, "difficulty": "easy",
        "instructions": ["Write freely for a few minutes — spelling doesn't matter.",
                         "Then answer the prompts below.", "You choose whether to save it to your private journal."],
        "config": {"prompts": ["What is on my mind right now?",
                               "Which part of this can I do something about this week?",
                               "What is one small next step?"]},
        "completion_criteria": "Write at least a couple of sentences (20+ characters).",
        "safety_notes": "If writing brings up intense feelings, pause and consider talking to someone you trust.",
    },
    {
        "slug": "three-good-things",
        "title": "Three Good Things",
        "description": "A short gratitude reflection: note three things that went okay today, however small.",
        "category": "gratitude", "kind": "journal", "duration_minutes": 3, "difficulty": "easy",
        "instructions": ["Think back over today.", "Write three things that went okay or that you appreciated.",
                         "Optionally note why each one happened."],
        "config": {"prompts": ["One thing that went okay today:", "Something or someone I appreciated:",
                               "A small moment I'd like to remember:"]},
        "completion_criteria": "Write at least a couple of sentences (20+ characters).",
        "safety_notes": None,
    },
    {
        "slug": "pomodoro-study-break",
        "title": "Structured Study Break",
        "description": "A short, screen-free break between study sessions to stretch, hydrate and reset.",
        "category": "study_break", "kind": "guided_steps", "duration_minutes": 5, "difficulty": "easy",
        "instructions": ["Stand up and step away from your screen.", "Stretch your arms, neck and shoulders gently.",
                         "Drink some water.", "Look at something far away for 20 seconds to rest your eyes.",
                         "Decide on the single task for your next study block."],
        "config": {"seconds_per_step": 45},
        "completion_criteria": "Go through all five steps.",
        "safety_notes": "Only stretch within a comfortable range.",
    },
    {
        "slug": "mindful-walk",
        "title": "Mindful Walk",
        "description": "A slow walk, indoors or somewhere safe outside, paying attention to each step and your surroundings.",
        "category": "movement", "kind": "guided_steps", "duration_minutes": 10, "difficulty": "easy",
        "instructions": ["Choose a safe, familiar place to walk.", "Walk a little slower than usual.",
                         "Notice the feeling of your feet touching the ground.",
                         "Notice sounds and colours around you.", "When your mind wanders, gently return to your steps."],
        "config": {"seconds_per_step": 120},
        "completion_criteria": "Go through all steps of the walk.",
        "safety_notes": "Walk only where you feel safe. Skip this if you are unwell or it is unsafe to go out.",
    },
    {
        "slug": "sleep-wind-down",
        "title": "Sleep Wind-Down Reflection",
        "description": "Reflect on your evening routine and pick one small change that might make winding down easier.",
        "category": "sleep", "kind": "journal", "duration_minutes": 4, "difficulty": "easy",
        "instructions": ["Think about the last hour before you usually sleep.", "Answer the prompts honestly.",
                         "Pick one small, realistic change to try tonight."],
        "config": {"prompts": ["What do I usually do in the hour before sleep?",
                               "What tends to keep me awake?",
                               "One small change I could try tonight:"]},
        "completion_criteria": "Write at least a couple of sentences (20+ characters).",
        "safety_notes": "Ongoing sleep problems are worth discussing with a doctor or counsellor.",
    },
    {
        "slug": "progressive-relaxation",
        "title": "Quick Muscle Relaxation",
        "description": "Gently tense and release muscle groups to notice the difference between tension and relaxation.",
        "category": "relaxation", "kind": "guided_steps", "duration_minutes": 5, "difficulty": "easy",
        "instructions": ["Sit or lie comfortably.", "Gently clench your hands for 5 seconds, then release.",
                         "Raise your shoulders towards your ears for 5 seconds, then let them drop.",
                         "Scrunch your face gently for 5 seconds, then relax it.",
                         "Press your feet into the floor for 5 seconds, then release.",
                         "Take three slow breaths and notice how your body feels."],
        "config": {"seconds_per_step": 40},
        "completion_criteria": "Go through all six steps.",
        "safety_notes": "Tense gently — never to the point of discomfort. Skip any area that is injured.",
    },
    {
        "slug": "weekly-priorities",
        "title": "Three Priorities Planner",
        "description": "A short time-management reflection to pick what matters most this week and plan the first step.",
        "category": "time_management", "kind": "journal", "duration_minutes": 5, "difficulty": "easy",
        "instructions": ["List what is due or worrying you this week.", "Pick the three that matter most.",
                         "Write the very first small step for each."],
        "config": {"prompts": ["Everything on my plate this week:",
                               "My top three priorities:",
                               "The first small step for each:"]},
        "completion_criteria": "Write at least a couple of sentences (20+ characters).",
        "safety_notes": None,
    },
]

BADGES = [
    ("first_checkin", "First Check-in", "Completed your first wellness check-in.", "sprout"),
    ("first_activity", "First Step", "Completed your first activity.", "footprints"),
    ("streak_3", "3-Day Rhythm", "Active on 3 days in a row.", "flame"),
    ("streak_7", "7-Day Rhythm", "Active on 7 days in a row.", "sun"),
    ("breathing_5", "Steady Breather", "Completed 5 breathing sessions.", "wind"),
    ("journal_5", "Reflective Writer", "Completed 5 journaling activities.", "pen"),
    ("explorer", "Explorer", "Tried activities from 4 different categories.", "compass"),
    ("level_5", "Level 5", "Reached level 5.", "star"),
]


def seed_reference_data():
    existing = {a.slug: a for a in Activity.query.filter(Activity.slug.isnot(None)).all()}
    for item in BUILTIN_ACTIVITIES:
        fields = dict(item)
        fields["xp_reward"] = xp_for_duration(item["duration_minutes"])
        activity = existing.get(item["slug"])
        if activity is None:
            db.session.add(Activity(source="builtin", **fields))
        else:
            for key, value in fields.items():
                setattr(activity, key, value)
    existing_badges = {b.code: b for b in Badge.query.all()}
    for code, name, description, icon in BADGES:
        badge = existing_badges.get(code)
        if badge is None:
            db.session.add(Badge(code=code, name=name, description=description, icon=icon))
        else:
            badge.name, badge.description, badge.icon = name, description, icon
    db.session.commit()
