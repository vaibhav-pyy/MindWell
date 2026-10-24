# Security & privacy notes

## Authentication & sessions
* Passwords: Werkzeug `scrypt` hashes; policy 10–128 chars with a letter and a digit. Login compares against a dummy
  hash for unknown emails and returns one generic error (no user enumeration by message or timing).
* Sessions: Flask signed cookie `mindwell_session` — `HttpOnly`, `SameSite=Lax`, `Secure` when
  `SESSION_COOKIE_SECURE=true`; absolute lifetime 8 h, idle timeout 60 min; session cleared and CSRF token rotated on
  login. The session's role is re-checked against the database on every request.
* CSRF: synchroniser token stored in the session; every non-GET `/api` request must echo it in `X-CSRF-Token`.
* Students self-register; teacher accounts are created only by an administrator (`flask create-teacher`). There are
  no default or shared passwords. Demo accounts get random one-time passwords and are refused in production.

## Authorisation
* Enforced server-side by decorators (`student_required`, `teacher_required`) **and** per-record ownership filters
  (`…filter_by(id=…, student_id=g.user.id)`). Other users' ids return `404`, not `403`, to avoid confirming existence.
* No teacher endpoint queries messages, memory, journal, emergency tables or per-student rows for output.
* IDs, XP amounts, roles and notification destinations from the client are never trusted: XP is computed server-side,
  the alert destination comes from the stored contact, and the role comes from the database.

## Input handling, injection, XSS
* All DB access through SQLAlchemy with bound parameters (no string-built SQL).
* Every field is type-, length- and range-validated; phones normalised to E.164 with `phonenumbers`; emails with
  `email-validator`.
* React escapes all rendered text; `dangerouslySetInnerHTML` is not used anywhere. API responses carry
  `Content-Security-Policy: default-src 'none'`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cache-Control: no-store`.
* Errors return generic messages; stack traces are only logged server-side.

## Rate limiting (Flask-Limiter)
Login 10/min & 60/h per IP · register 5/h · chat 20/min & 300/day per user · new conversation 30/h ·
AI activity 10/h · teacher insight 10/h · emergency alerts 5/h & 10/day + 10-min cooldown · password/account
changes 5/h · global 300/min. Use Redis storage (`RATELIMIT_STORAGE_URI`) with multiple workers.

## Logging
Request bodies are never logged. Logs contain only operational events (e.g. "Gemini server error code=503"), never
chat text, check-in values, contacts or emergency messages.

## What is sent to Google Gemini

| Feature | Sent | Never sent |
|---|---|---|
| Chat | system instructions; activity catalog; last ≤ 12 messages of the current conversation; if memory is on: the student's own notes and ≤ 3 AI summaries; if opted in: latest check-in indicator numbers | name, email, emergency contact, journal, check-in notes, other students' data |
| Memory summary | messages of one conversation (not crisis conversations) | identifiers (and any contact details are stripped from the result) |
| AI activity | the student's short description, time available, preferred type | identifiers |
| Teacher insight | suppressed weekly class aggregates only | any per-student value or identifier |

All Gemini calls go through the backend; the key never reaches the browser. The student must opt in to AI
processing (recorded with timestamp in `consent_records`) and can withdraw at any time. Google processes this data
under its Gemini API terms — MindWell cannot promise absolute confidentiality and says so in the UI.

## AI output safety
* Structured JSON with a response schema for every call; output is parsed and validated (types, lengths, enums,
  whitelisted fields). Truncated (`MAX_TOKENS`), malformed or non-JSON output is discarded.
* Chat may only reference activity slugs from the catalog; suggestions are dropped during a crisis.
* AI activities: unsafe-term filter (fasting, cold exposure, medication, long breath-holds, cure/clinical claims,
  contact details…), duration caps; XP is set by the backend, `suggested_xp` and any extra fields are ignored.
* Summaries and teacher insights: rejected if they contain diagnostic, labelling or surveillance language
  ("disorder", "has depression", "identify students", "statistically significant", …).
* On any AI failure the UI states that no reply was generated — nothing is fabricated or presented as Gemini output.

## Crisis and emergency safeguards
* A deterministic, auditable phrase screen (English + common romanised Hindi) runs **before** the AI. A crisis hit
  returns a fixed, human-written safety message (labelled "pre-written, not AI-generated") with Tele-MANAS, 112 and
  the student's trusted-contact call button, and opens the support panel. The AI's `risk_level` can only escalate the
  response, never downgrade a rule hit.
* **Nothing is sent to anyone automatically** — not from chat content, AI risk scores, low indicators or
  inactivity. (An automatic workflow was deliberately not implemented; the requirement was optional and the
  risk of false positives/negatives disclosing sensitive information outweighed the benefit for this project.)
* Emergency messages require: a saved contact the student confirmed has agreed, sharing enabled with explicit consent
  (recorded), a preview of the exact text, and a confirmation click. Content is limited to the fields the student
  enabled (name / callback number / short note) plus time and helpline numbers — never chats, journal or scores.
* Delivery status is truthful: `not_configured` / `dev_outbox` / `failed` are shown as **NOT SENT**;
  `accepted_by_provider` explains that receipt cannot be confirmed. Retries (2) only on transient errors; idempotency key
  and cooldown prevent duplicates. Logs store a masked destination only.
* `tel:` links use the stored E.164 number; the UI explains that a tap doesn't mean a call connected.
* Helplines are reachable without signing in (landing, login and register pages) and from every student screen.
* Limitations: the phrase screen will miss indirect language and can over-trigger; Gemini's risk flag is
  probabilistic. MindWell cannot reliably detect every crisis and says so to students.

## Teacher analytics privacy
* Opt-in per class (`share_aggregates`, recorded as consent); withdrawing removes the student from all future figures.
* Per-student weekly averaging, then class mean; weeks with fewer than `MIN_COHORT_SIZE` (≥ 3, default 5)
  contributors are fully suppressed and the exact small count is not revealed; values rounded to integers.
* Only fixed periods (4/8/12 whole weeks) — no demographic or ad-hoc filters to intersect.
* No names, rosters, rankings, drill-downs or per-student rows. Member count only.
* Residual risk (documented, not eliminated): a teacher who knows exactly when one student joined/left a class could
  compare weeks; mitigated by rounding and the cohort threshold but not by formal differential privacy.

## Deployment checklist
* Serve over HTTPS and set `SESSION_COOKIE_SECURE=true`, `APP_ENV=production`.
* Serve `frontend/dist` and proxy `/api` to Waitress/Gunicorn from the same origin (keeps cookies first-party).
* Use a dedicated MySQL user with privileges on `mindwell.*` only; enable MySQL TLS if the DB is remote.
* Redis for rate-limit storage; schedule `flask purge-expired` daily; rotate `SECRET_KEY` to invalidate sessions.
* Local development uses plain HTTP on localhost — acceptable only for development.
