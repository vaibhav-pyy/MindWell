# Gamification rules

All calculations happen on the backend ([services/gamification.py](../backend/app/services/gamification.py)).
The frontend only displays server-confirmed values; the AI can never award XP.

## XP

| Event | XP | Limit |
|---|---|---|
| Daily check-in (first save of the day) | `XP_CHECKIN` (10) | once per day; edits earn nothing extra |
| Completing an activity | `clamp(duration_min × XP_PER_ACTIVITY_MINUTE, XP_ACTIVITY_MIN, XP_ACTIVITY_MAX)` = 3/min, 5–40 | max `XP_AWARDS_PER_ACTIVITY_PER_DAY` (2) XP awards per activity per day |

XP lives in an append-only ledger (`xp_transactions`) with a unique `(source_type, source_id)`, so retries, double
clicks and concurrent requests can't duplicate an award. XP is never deducted.

## What counts as "completed"

1. The student starts a session (server records `started_at`).
2. At least `ACTIVITY_MIN_COMPLETION_RATIO` (60%) of the activity's duration has passed on the **server clock**.
3. Guided-step activities: all steps visited (UI). Journal activities: ≥ 20 characters written (server-checked).
4. Each session completes once (unique constraint). Stopping early is fine — it simply earns no XP.

## Levels

Level *L* requires `LEVEL_XP_STEP × L × (L − 1)` total XP (default step 25): L1 = 0, L2 = 50, L3 = 150, L4 = 300,
L5 = 500, L6 = 750 …

## Streaks

* An **active day** = a local calendar day with at least one check-in or completed activity.
* The streak counts consecutive active days. If a day is missed, the next active day starts a new streak at 1.
* The displayed current streak is 0 if the last active day was before yesterday. The longest streak is kept forever.
* Nothing is lost by missing days — no XP, level or badge is ever removed, and the UI never uses guilt language.

## Badges

| Code | Badge | Condition |
|---|---|---|
| first_checkin | First Check-in | ≥ 1 check-in |
| first_activity | First Step | ≥ 1 completed activity |
| streak_3 | 3-Day Rhythm | longest streak ≥ 3 |
| streak_7 | 7-Day Rhythm | longest streak ≥ 7 |
| breathing_5 | Steady Breather | 5 breathing completions |
| journal_5 | Reflective Writer | 5 journaling/gratitude completions |
| explorer | Explorer | activities from 4 categories |
| level_5 | Level 5 | reach level 5 |

Badges are evaluated after every check-in or completion and awarded once (`UNIQUE(student_id, badge_id)`).

## Healthy-engagement principles

* No rewards are tied to *what* a student discloses (chat content never affects XP).
* Activities are always optional with a visible "Not today"/"Stop — that's okay".
* Daily caps discourage grinding; there are no leaderboards and teachers never see individual progress.
* During a detected crisis, the chatbot suggests no activities.
