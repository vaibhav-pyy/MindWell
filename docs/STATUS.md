# Project status (updated 2026-10-24)

## Feature checklist

| Feature | Status | Notes |
|---|---|---|
| Student registration/login/logout, teacher login | ✅ Done | teachers created via CLI |
| Role & ownership authorisation, CSRF, rate limits, idle timeout | ✅ Done | |
| AI chatbot (Gemini) | ✅ Done, verified live | retries + fallback model on 5xx/429; thinking budget capped |
| Conversation memory (notes + AI summaries, bounded context, deletion) | ✅ Done, verified live | |
| Safety screen + crisis response | ✅ Done | deterministic + AI escalation; never auto-notifies |
| Wellness check-ins & indicators (history, trends, correction, methodology) | ✅ Done | non-clinical, documented |
| Rule-based daily recommendations + dismiss | ✅ Done | |
| AI-generated personal activities (validated) | ✅ Done, verified live | |
| Interactive activities: breathing, guided steps, journaling | ✅ Done | 10 built-in |
| XP ledger, levels, streaks, badges | ✅ Done | idempotent, capped |
| Student dashboard, wellness, activities, progress, settings pages | ✅ Done | responsive, checked at 390 px and 1366 px |
| Teacher dashboard: classes, join codes, aggregate trends, observations | ✅ Done | k-threshold suppression, opt-in |
| Teacher AI insights (aggregate-only, validated) | ✅ Done, verified live | |
| Emergency contact CRUD, `tel:` calling, Tele-MANAS & 112 | ✅ Done | |
| Consent-scoped emergency messages (preview → confirm) | ✅ Done | |
| Email delivery (SMTP) / SMS delivery (Twilio) | ⚠️ Implemented, **not verified with real credentials** | tested with mocked providers; dev outbox verified live |
| Data export, account deletion, retention purge | ✅ Done | |
| MySQL | ✅ Verified live on MySQL 8.0.46 | `init-db` creates 24 InnoDB tables, 30 FKs, 18 CHECKs; cascades verified |

## Verification actually performed

1. **Automated backend tests:** `python -m pytest -q` → **83 passed** (auth, CSRF, roles, cross-user access, idle
   expiry, cascade deletion, chat persistence, missing key / quota / provider failure / malformed / truncated output,
   crisis handling, memory scoping & no cross-user leakage, scoring formula & validation, recommendations, XP
   idempotency & caps, too-early completion, levels, streaks, badges, AI activity validation, emergency contact
   validation & privacy, consent enforcement, message field scoping, truthful delivery statuses, duplicate/cooldown,
   teacher suppression, consent exclusion, aggregate correctness, no identifiers, filter restrictions, AI insight
   validation, Gemini retry/fallback logic).
2. **Frontend build:** `npm run build` succeeds (Vite 6).
3. **Live end-to-end run** (Flask + Waitress + Vite proxy + **real Gemini API**, SQLite file DB, seeded demo data):
   28/28 scripted checks passed — registration, check-in, recommendations, real Gemini chat reply with activity
   suggestions, crisis safety template, persistence, real AI activity generation, server-timed activity completion
   with real waiting, duplicate-completion protection, emergency contact/preferences/preview, dev-outbox alert reported
   as NOT SENT, class join, teacher analytics, teacher blocked from chats and emergency data, logout. AI teacher insight
   and AI memory summary also verified live.
4. **Headless browser walkthrough** (Edge via Playwright) of every student and teacher page at desktop and mobile
   widths: no console errors, page errors, 5xx responses or horizontal overflow (after fixing a mobile header overflow).

5. **MySQL run (2026-10-24):** `flask init-db` + `seed-demo` on MySQL 8.0.46, then 36/36 live end-to-end checks
   with real Gemini, including direct SQL checks of password hashing, message persistence, the XP ledger and
   account-deletion cascades; headless walkthrough of 28 page views clean. Fixed during this run: `init-db` could
   not create the database (SQLAlchemy 2.1 URL handling), Gemini 504 timeouts no longer retry the same model,
   and a mobile table overflow on the Wellness page.

## Known issues / limitations

* Real email/SMS delivery needs provider credentials and was not exercised end to end.
* `gemini-3.8-flash` was frequently overloaded (HTTP 503/429) during testing; the fallback model handled it, adding
  latency (up to ≈30 s when Google returns a gateway timeout before the fallback answers).
* Crisis detection is best-effort (phrase list + AI flag); it cannot catch every crisis and may over-trigger.
* Teacher aggregates use k-anonymity-style suppression, not formal differential privacy.
* No automated frontend unit tests; the UI was verified by build + headless walkthrough.
* The UI has no dark mode and is English-only.
* Rate-limit counters are in memory by default (reset on restart; use Redis in production).
