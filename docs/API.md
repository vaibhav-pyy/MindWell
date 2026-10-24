# API reference

Base path `/api`. JSON in, JSON out.

* Success: `{"ok": true, "data": …}`
* Error: `{"ok": false, "error": {"code": "…", "message": "…", "details": {…}}}`
* Auth: session cookie `mindwell_session` (HttpOnly, SameSite=Lax). Get one via login/register.
* CSRF: every non-GET request must send header `X-CSRF-Token` with the token from `GET /api/auth/csrf`
  (also returned by login/register/me/logout). Missing/invalid → `403 csrf_failed`.
* Roles: **S** = student only, **T** = teacher only, **A** = any signed-in user, **P** = public.
* Ownership: every resource id is checked against the signed-in user; other users' ids return `404`.
* Common codes: `401 unauthenticated`, `403 forbidden`, `404 not_found`, `422 validation_error`, `429 rate_limited`,
  `503 ai_unavailable` (`details.reason`: `not_configured | quota | provider_error | timeout | invalid_output | blocked`).

## Auth
| Method | Path | Role | Notes / limits |
|---|---|---|---|
| GET | `/auth/csrf` | P | `{csrf_token}` |
| POST | `/auth/register` | P | `{email, password, display_name, accept_terms: true, ai_processing_consent}` → student. 5/h, 20/day per IP |
| POST | `/auth/login` | P | `{email, password, role?}` (`role` rejects wrong portal). 10/min, 60/h per IP |
| POST | `/auth/logout` | P | clears session |
| GET | `/auth/me` | A | user + privacy flags |

## Profile, privacy, account
| Method | Path | Role | Notes |
|---|---|---|---|
| GET/PATCH | `/profile` | A | `display_name`, `pronouns`, `year_of_study` |
| PATCH | `/privacy` | S | `ai_processing_consent`, `memory_enabled`, `personalize_with_checkins` (each change → consent record) |
| GET | `/privacy/consents` | S | consent history |
| POST | `/account/password` | A | `{current_password, new_password}` 5/h |
| GET | `/account/export` | S | all of the student's data as JSON. 10/h |
| DELETE | `/account` | A | `{password, confirm: "DELETE"}` — cascades all data |
| GET | `/classes/mine` | S | memberships |
| POST | `/classes/join` | S | `{join_code, share_aggregates}` |
| PATCH | `/classes/<id>/sharing` | S | `{share_aggregates}` |
| DELETE | `/classes/<id>/membership` | S | leave class |

## Chat & memory
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/conversations` | S | list (own) |
| POST | `/conversations` | S | new; summarises previous conversation into memory if enabled. 30/h |
| GET/DELETE | `/conversations/<id>` | S | messages / delete |
| DELETE | `/conversations` | S | delete all |
| POST | `/conversations/<id>/messages` | S | `{content}` ≤2000 chars. 20/min, 300/day. Returns `user_message`, `assistant_message` (`source`: `gemini` or `safety_template`), `safety {level, show_support, has_emergency_contact}`. On AI failure → 503 and **nothing is stored** |
| POST | `/conversations/<id>/summarize` | S | manual summary. 20/h |
| GET | `/memory` | S | `{memory_enabled, items[]}` with `kind` `student_note`/`ai_summary` |
| POST | `/memory` | S | `{content}` student note (max 50) |
| DELETE | `/memory/<id>`, `/memory` | S | delete one / all |

## Wellness
| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/checkins` | S | upsert today's (or `date` = yesterday) check-in: `stress, anxiety, mood, sleep_quality, academic_pressure` (1-5, optional), `sleep_hours` (0-16), `stressors[]`, `note`. Returns indicators, XP, new badges |
| GET | `/checkins?days=30` | S | history (≤365 days) |
| PATCH/DELETE | `/checkins/<id>` | S | correct / delete |
| GET | `/wellness/summary` | S | latest, 7-day & previous 7-day averages, trends, 30-day series, definitions |
| GET | `/wellness/methodology` | P | weights, formulas, version |

## Activities & gamification
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/activities` | S | built-in + own AI activities |
| GET | `/activities/<id>` | S | |
| DELETE | `/activities/<id>` | S | remove own AI activity |
| POST | `/activities/generate` | S | `{concern, available_minutes 2-20, preference?}` → Gemini activity (validated, XP set by server). 10/h |
| GET | `/recommendations/today` | S | rule-based daily suggestions (≤3) + chat/AI ones |
| POST | `/recommendations/<id>/dismiss` | S | |
| POST | `/activities/<id>/sessions` | S | start → `{session_id, min_seconds}`. 60/h |
| POST | `/activity-sessions/<id>/complete` | S | `{journal_text?, save_to_journal?}`; idempotent; `422 too_early` before `min_seconds` |
| GET | `/progress` | S | level, XP, streaks, badges, XP history, recent completions, rules |
| GET | `/journal` / DELETE `/journal/<id>` | S | private journal |

## Emergency
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/emergency` | S | contact (with `tel_href`), preferences, configured channels, plain-language explanation, helpline config |
| PUT/DELETE | `/emergency/contact` | S | `{name, relationship, phone, email?, preferred_method: call_only|email|sms, confirm: true}` |
| PUT | `/emergency/preferences` | S | `{alerts_enabled, consent: true, share_name, share_callback_phone, callback_phone, share_custom_note, custom_note}` |
| GET | `/emergency/alert-preview` | S | exact message text, channel, masked destination, whether a provider is configured |
| POST | `/emergency/alerts` | S | `{client_request_id, confirm: true}`; idempotent per request id; 10-min cooldown; 5/h. Status ∈ `not_configured, dev_outbox, accepted_by_provider, failed`; `delivered_confirmed` is always `false` |
| GET | `/emergency/alerts` | S | own alert history (masked) |

## Teacher
| Method | Path | Role | Notes |
|---|---|---|---|
| GET/POST | `/teacher/classes` | T | list / create `{name}` |
| POST | `/teacher/classes/<id>/rotate-code` | T | |
| DELETE | `/teacher/classes/<id>` | T | |
| GET | `/teacher/classes/<id>/analytics?weeks=4|8|12` | T | suppressed weekly aggregates, rule-based observations & suggestions, latest AI insight |
| POST | `/teacher/classes/<id>/insights` | T | `{weeks}` → persists insight; Gemini only receives aggregates. 10/h |

## Public
| Method | Path | Notes |
|---|---|---|
| GET | `/public/support` | helpline numbers (no login) |
| GET | `/health` | DB status, Gemini configured, notification channels |
