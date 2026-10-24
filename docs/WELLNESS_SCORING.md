# MindWell Wellness Indicators — methodology (version `mw-1`)

> **Status: project-specific, NOT clinically validated.** These indicators summarise a student's own answers to help
> them notice patterns. They are not a screening instrument, must not be used to diagnose or label anyone, and have
> no clinical thresholds. Implementation: [backend/app/services/scoring.py](../backend/app/services/scoring.py).

## Why not a standard instrument?

Validated questionnaires such as PHQ-9 (depression) and GAD-7 (anxiety) are free to use but are *clinical screening
tools*: their scores map to severity bands intended for interpretation by a clinician, with follow-up pathways.
Embedding them in a gamified student app — with daily repetition and optional class-level aggregation — would be
outside their intended use and risk students self-labelling. The WHO-5 Well-Being Index is closer in spirit but uses a
two-week recall window, which doesn't match a daily check-in. We therefore use simple, transparent single items and
call the result a *reflection aid*, not a score with clinical meaning.

## Inputs (how they are obtained)

Only from the student's daily check-in form. Every item is optional. Nothing is inferred from chat messages.

| Item | Question | Scale |
|---|---|---|
| `mood` | How has your mood been today? | 1 very low … 5 very good |
| `stress` | How stressed have you felt today? | 1 not at all … 5 extremely |
| `anxiety` | How worried, nervous or on edge have you felt? | 1 not at all … 5 extremely |
| `sleep_quality` | How well did you sleep last night? | 1 very poorly … 5 very well |
| `sleep_hours` | Roughly how many hours did you sleep? | 0–16 |
| `academic_pressure` | How much academic pressure are you feeling? | 1 none … 5 overwhelming |
| `stressors` | Is anything weighing on you? | multi-select categories (not scored) |

## Normalisation (to 0–100)

* Likert item: `level = (answer − 1) / 4 × 100` (keeps the question's own direction).
* Sleep hours: `100` for 7–9 h, falling linearly to `0` at 3 h and at 13 h. (7–9 h follows general public-health
  sleep guidance for young adults; it is used only as a reference range, not a clinical cut-off.)
* `sleep_score` = mean of whichever of `level(sleep_quality)` and the sleep-hours score were answered.

## Indicators

| Indicator | Meaning | Direction |
|---|---|---|
| `stress_level` | level(stress) | higher = more stress |
| `anxiety_level` (shown as "Worry") | level(anxiety) | higher = more worry |
| `mood_level` | level(mood) | higher = better |
| `sleep_score` | see above | higher = better |
| `academic_pressure_level` | level(academic_pressure) | higher = more pressure |
| `wellness_index` | weighted summary below | higher = better |

## Wellness index

Weighted mean over components oriented so that higher = better:

| Component | Weight |
|---|---|
| mood_level | 0.25 |
| 100 − stress_level | 0.20 |
| 100 − anxiety_level | 0.20 |
| sleep_score | 0.20 |
| 100 − academic_pressure_level | 0.15 |

**Missing data:** unanswered components are dropped and the remaining weights are re-normalised to sum to 1.
At least **3 of 5** components are required; otherwise the index is `null` and the UI says "not enough data".

Example: all items 3 and 8 h sleep → mood 50, stress 50, worry 50, sleep (50+100)/2 = 75, academic 50 →
0.25·50 + 0.2·50 + 0.2·50 + 0.2·75 + 0.15·50 = **55**.

## When values update

* Computed deterministically when a check-in is saved, and recomputed when the student corrects it.
* Stored on the check-in row with `scoring_version`, so history stays reproducible if the formula changes.
* "Last 7 days" = mean of check-ins in the last 7 local days. A trend ("up/down/about the same", ±5-point band) is
  only shown when both the last and the previous 7 days have ≥ 2 check-ins. No trend is labelled good or bad
  beyond the stated direction of each indicator.

## Student control

Students can view every raw answer, correct any check-in, or delete it (XP already earned is kept, so correcting is
never penalised). Check-in numbers are sent to Gemini only if the student enables "Personalise chat with my check-in
numbers"; the private note is never sent anywhere.

## Teacher view

Teachers see only weekly class means of these indicators, computed after averaging each student within the week,
from students who opted in, and only when ≥ `MIN_COHORT_SIZE` (default 5) contribute. See
[SECURITY_PRIVACY.md](SECURITY_PRIVACY.md).
