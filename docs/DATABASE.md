# Database design

MySQL 8, InnoDB, `utf8mb4`. Defined in [backend/app/models.py](../backend/app/models.py); created by
`flask init-db` (idempotent `CREATE IF NOT EXISTS` semantics via `create_all`); DDL exported to
[database/schema.sql](../database/schema.sql). All timestamps are UTC `DATETIME`; "day" fields (`checkin_date`,
`completion_date`, `for_date`) are local dates in `APP_TIMEZONE` (Asia/Kolkata).

Enumerated columns are `VARCHAR` + named `CHECK` constraints (portable to the SQLite test database).

## Entities and relationships

```
users (role: student|teacher)
 ├─1:1─ student_profiles        consent flags: ai_processing, memory, personalise
 ├─1:1─ teacher_profiles
 ├─1:N─ consent_records         append-only consent audit trail
 ├─1:N─ classrooms (teacher)  ──1:N── class_memberships ──N:1── users (student)  [share_aggregates opt-in]
 │                              └─1:N── class_insights (aggregate statistics + validated AI narrative)
 ├─1:N─ conversations ──1:N── messages (role, source gemini|safety_template|student, safety_level)
 ├─1:N─ memory_items (student_note | ai_summary) ──N:1── conversations (SET NULL)
 ├─1:N─ checkins (unique per student per day; raw answers + derived indicators + scoring_version)
 ├─1:N─ activities (owner_student_id NULL = built-in catalog; set = personal AI activity)
 ├─1:N─ activity_recommendations ──N:1── activities   (unique student+activity+day)
 ├─1:N─ activity_sessions ──1:1── activity_completions ──1:0..1── journal_entries
 ├─1:N─ xp_transactions         (unique source_type+source_id → idempotent XP)
 ├─1:1─ student_progress        (cached totals / streak)
 ├─1:N─ student_badges ──N:1── badges
 ├─1:1─ emergency_contacts
 ├─1:1─ emergency_sharing_preferences
 └─1:N─ emergency_alerts ──1:N── notification_attempts
```

## Integrity rules worth knowing

| Rule | How it's enforced |
|---|---|
| A student owns only their records | Every private table has `student_id → users.id ON DELETE CASCADE`; every query filters on the session user |
| XP can't be awarded twice | `UNIQUE(xp_transactions.source_type, source_id)` + check before insert |
| An activity session completes once | `UNIQUE(activity_completions.session_id)`; concurrent duplicate → `IntegrityError` caught → returns existing |
| One check-in per day | `UNIQUE(student_id, checkin_date)`; re-submitting updates it |
| Duplicate emergency alerts | `UNIQUE(student_id, client_request_id)` + time-window cooldown |
| One emergency contact per student | `UNIQUE(emergency_contacts.student_id)` |
| Valid ranges | `CHECK` constraints on Likert items (1-5), sleep hours (0-16), duration (1-30), enums |
| Multi-step writes | Single transaction per request (commit at end; rollback on any error, including validation errors) |

Indexes cover the hot paths: `(student_id, updated_at)` on conversations, `(student_id, checkin_date)`,
`(student_id, completion_date)`, `(student_id, for_date)`, `(student_id, created_at)` on XP/alerts/memory, plus FK columns.

## Sensitive data and minimisation

| Data | Stored? | Notes |
|---|---|---|
| Passwords | scrypt hash only | Werkzeug `generate_password_hash` |
| Chat messages | yes, by necessity (continuity) | deletable per conversation / all; retention purge |
| AI summaries | short (≤600 chars), validated | contact details stripped; diagnostic language rejected; crisis conversations are never auto-summarised |
| Journal text | **only if** the student ticks "save" | otherwise discarded after the completion check |
| Emergency contact | name, relationship, E.164 phone, optional email | never exposed to teachers or sent to Gemini |
| Alert logs | channel, **masked** destination, status, attempts | message body is not stored |
| Provider secrets | never in DB | environment variables only |
| Class insights | aggregate statistics (already suppressed) + AI text | no identifiers |

## Retention & deletion

| What | Default | Mechanism |
|---|---|---|
| Conversations (and their messages) | 180 days since last activity | `flask purge-expired` (schedule daily with Task Scheduler/cron) |
| Emergency alert logs | 90 days | `flask purge-expired` |
| Everything else | until the student deletes it | per-item deletes in the UI |
| Whole account | immediate | `DELETE /api/account` → cascades through every table above |

Not removable by MindWell: aggregate class figures a teacher already viewed (they were never individual), and
content previously sent to Google Gemini (governed by Google's API data-retention terms).
