# JobPilot — Technical Blueprint (Phase 1 / MVP)

## 1. Architecture
```
 ┌──────────────────────── Browser (React SPA, EN/AR RTL) ────────────────────────┐
 │ Landing · Auth · Onboarding · Dashboard · Jobs · Job detail · CV vault ·       │
 │ Tailor studio · Kanban tracker · Reminders · Settings · Billing · Admin        │
 └───────────────▲──────────────── HTTPS /api (cookies: JWT / Google session) ────┘
                 │
 ┌───────────────┴──────────── FastAPI (single service, modular routers) ─────────┐
 │ r_auth   – JWT + Emergent Google auth, onboarding, consents, avatar (Nano Banana)│
 │ r_cv     – upload → text extract (pypdf/python-docx) → AI parse → versions      │
 │ r_jobs   – feed query, saved searches, manual add (AI normalize), AI review     │
 │ r_apps   – applications, notes/contacts/docs/timeline, tailor+validate, export, │
 │            reminders engine, notifications, dashboard                           │
 │ r_integrations – Gmail (OAuth, drafts/send), Stripe checkout/webhook            │
 │ r_admin  – users, plans, sources, AI cost & model switch, audit, privacy        │
 │ ai.py    – prompt registry (versioned), model router, cache, cost log, validator│
 │ sources.py – fetchers + normaliser + dedupe + alerts                            │
 │ APScheduler: reminders (1 min) · sources (6 h) · ghost check (12 h)             │
 └──────┬──────────────┬───────────────┬────────────────┬─────────────────────────┘
        │              │               │                │
     MongoDB     Object storage     LLM providers    External APIs
   (all data)  (Fernet-encrypted   (Claude Haiku 4.5 (Careerjet, Jooble, Greenhouse,
               CVs & docs)          / Sonnet 4.6,     Lever, Remotive, Arbeitnow,
                                    GPT, Gemini, NIM) Gmail API, Stripe, Resend email)
```
Stack note: built on FastAPI + React + MongoDB (platform stack) instead of Laravel + MySQL; module boundaries map 1:1 to the requested modules. Redis queues are replaced by the in-process scheduler plus background tasks. For horizontal scale, move the scheduler into a dedicated worker.

## 2. Module boundaries
| Module | Owns collections | Talks to |
|---|---|---|
| Auth/Workspace | users, workspaces, user_sessions, login_attempts, password_reset_tokens | email |
| CV vault | cv_versions, files | ai, storage |
| Job aggregation | jobs, sources, searches | fetchers, notifications, email |
| AI review | reviews, ai_cache, ai_logs | ai |
| Tailoring | tailored | ai, exporter, applications |
| Tracker | applications | reminders |
| Reminders | reminders, notifications | email (Phase 2: WhatsApp) |
| Integrations | gmail_tokens, oauth_states, payment_transactions | Google, Stripe |
| Billing | plans, usage | Stripe |
| Admin/Privacy | audit_logs, consents, settings | all (read) |

## 3. Data model (MongoDB, string ids, `_id` never exposed)
- **users** {user_id, workspace_id, email, name, password_hash?, role(user|admin), plan, lang, country, city, timezone, quiet_start, quiet_end, weekly_goal, followup_days, ghost_days, onboarded, suspended, consents{}, avatar_file_id, gmail_connected}
- **workspaces** {workspace_id, owner_id, type(personal|coach)}
- **consents** {user_id, type, granted, ip, created_at} (append-only history)
- **cv_versions** {cv_version_id, user_id, version, data(CV JSON), file_id, is_master, note}
- **files** {file_id, user_id, storage_path, filename, content_type, size, kind(cv|document|avatar), is_deleted}
- **jobs** {job_id, fingerprint, source, sources[], source_ref, title, company, location, city, country, remote, description, url, salary_min/max, currency, posted_at, fetched_at, owner_user_id(null=global | manual)}
- **sources** {source_id, name, kind, env_key, enabled, config{boards}, status, last_run, last_count, last_new, last_error, attribution}
- **searches** {search_id, user_id, name, country, city, keywords, remote, seniority, min_salary, alerts, last_alert_at}
- **reviews** {review_id, user_id, job_id, cv_version_id, result{score, verdict, matched_skills, missing_skills, keyword_gaps, red_flags, notes, reasons, summary}, model, provider, prompt_version}
- **tailored** {tailored_id, user_id, job_id, application_id, cv_version_id, lang, cv, cover_letter, changes[], flags[{flag_id,path,type,value,reason,source(rule|ai),status(open|removed|confirmed)}], status(draft|approved)}
- **applications** {application_id, user_id, job_id, title, company, source, status, reached[], notes[], contacts[], documents[], timeline[], applied_at, interview_at, followup_at, deadline_at, tailored_id, ghost_suggested}
- **reminders** {reminder_id, user_id, application_id, type(follow_up|interview_24h|interview_1h|deadline|custom), title, due_at, deliver_at, status(pending|snoozed|sent|done), auto, channels[]}
- **notifications**, **usage** {user_id, period YYYY-MM, reviews, tailors, parses}, **plans**, **ai_cache** {key, result}, **ai_logs** {user_id, feature, provider, model, prompt_version, tokens, cost_usd, cached}, **audit_logs**, **settings** {key: ai_models}, **gmail_tokens** {user_id, enc(Fernet)}, **payment_transactions**.

## 4. Integrations
- **Job sources**: Careerjet (publisher key `CAREERJET_AFFID`), Jooble (`JOOBLE_API_KEY`), Greenhouse and Lever public boards (admin-managed board list, seeded with careem and tamara), Remotive, Arbeitnow, and manual paste. Each source has an on/off switch and health stats. Dedupe uses sha1(title|company|city), and duplicates merge their `sources[]`. Excluded: LinkedIn, Bayt, Indeed, GulfTalent, Jadarat (terms forbid scraping).
- **Gmail**: OAuth web flow, scope `gmail.compose` only (drafts + send, no restricted read scope). Tokens are Fernet-encrypted. Every send requires an explicit confirm dialog and is logged on the timeline and in the audit log. Needs `GOOGLE_CLIENT_ID/SECRET`. Redirect URI: `{FRONTEND_URL}/api/oauth/gmail/callback`.
- **WhatsApp (Phase 2)**: Cloud API, number opt-in with an OTP, Meta-approved templates `reminder_followup`, `reminder_interview`, and an inbound webhook that parses `done`, `snooze 1d` and `STOP`.
- **Payments**: Stripe subscriptions (`{plan}_monthly` lookup keys) plus a webhook at `/api/stripe/webhook`. The automatic Stripe sandbox could not be created for Saudi Arabia, so checkout is enabled only once `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` are set. Until then, the admin assigns plans manually. Phase 2: Moyasar or Tap for mada, Apple Pay and STC Pay.
- **Email**: Emergent-managed Resend (sender "JobPilot"). Only server-side templates are used, for reminders, alerts and password reset.

## 5. AI pipeline
`CV text → parse_cv (cheap) → master CV JSON (user-edited, versioned)`
`Job → normalize_job (cheap, manual adds only) → quick_match (deterministic skill overlap, free) → review (cheap) → tailor (strong) → validate (rules + cheap LLM) → user resolves flags → approve → export`

| Prompt | Version | Tier | Output schema |
|---|---|---|---|
| parse_cv | parse_cv@1.0 | scoring | CV JSON (name, headline, contact, summary, experience[], education[], skills[], projects[], languages[], certifications[]) |
| normalize_job | normalize_job@1.0 | scoring | title, company, location, country_code, remote, seniority, salary, requirements[], deadline |
| review | review@1.1 | scoring | score, verdict, matched/missing skills, keyword_gaps, red_flags, notes{salary,visa,location}, reasons |
| tailor | tailor@1.2 | writing | {cv, cover_letter, changes[]} under a hard no-invention rule |
| validate | validate@1.1 | scoring | flags[{path,type,value,reason}] |

- **Validation** has two layers. (1) Deterministic rules: employer, title, dates, skills, institutions and every number in the bullets must appear in the master CV JSON (Arabic digits are normalised). (2) An LLM fact-checker. Flags are merged and de-duplicated, and approval is blocked while any flag is open. "Remove" deletes the element at the flag's path. "Confirm" records that the user vouches for the claim, and the confirmation is audited.
- **Caching**: sha256(prompt_version|provider|model|prompt) → `ai_cache`, so identical work is never paid for twice. Reviews are unique per (user, job, cv_version), and repeat views are free.
- **Models**: the admin-switchable router lives in `settings.ai_models`. Defaults are Haiku 4.5 (scoring) and Sonnet 4.6 (writing). OpenAI, Gemini and NVIDIA NIM (`NVIDIA_API_KEY`) are alternatives.
- **Cost**: every call is logged with estimated tokens × price. The admin sees cost per feature, model and user.
- **Limits**: per-plan monthly counters (reviews, tailors, CV parses, applications). A 402 response opens the upgrade dialog.

## 6. Evaluation plan
- Set: 30 anonymised CV/job pairs (10 strong fit, 10 partial, 10 poor or blocked, e.g. Saudization-only roles), with 10 in Arabic. Each pair has: expected verdict, expected matched/missing skills, and a list of "must-not-appear" facts.
- Metrics:
  - verdict agreement (target ≥ 85%)
  - skill precision/recall (≥ 0.8)
  - hallucination rate = invented facts in tailored output that the validator did not flag (target 0)
  - validator recall on seeded fake facts (≥ 95%)
  - Arabic quality (1–5 human rating, ≥ 4)
  - p95 latency and cost per task
- Process: run on every prompt or model change, store results with prompt_version, and compare against the previous run. An admin UI to run the set is planned for Phase 2.

## 7. Roadmap
- **Phase 1 (done in this build)**: everything above.
- **Phase 2 (5–6 weeks)**:
  - WhatsApp Cloud API (1.5 weeks, blocked on Meta verification)
  - Gmail inbox scanning with status suggestions (1 week, blocked on Google verification)
  - Moyasar/Tap payments (1 week)
  - Adzuna and more countries (0.5 week)
  - browser save-job extension (1 week)
  - eval runner UI (0.5 week)
  - interview-prep pack (0.5 week)
- **Phase 3 (6–8 weeks)**: coach workspaces and billing, more countries with a salary benchmark, PWA with push notifications, anonymised insights.

## 8. Risks → mitigations
- **Scraping/legal**: official APIs, public ATS feeds and user-pasted content only, with attributions and per-source kill switches.
- **Gmail verification**: compose-only scope in Phase 1. The 100-test-user cap applies until Google verification completes. Inbox reading waits for the CASA assessment.
- **WhatsApp bans**: templates only, opt-in, STOP handling, frequency caps and quiet hours.
- **Hallucination**: rules plus LLM validator, an approval gate and the eval set.
- **AI cost**: plan limits, caching, the cheap model for high-volume steps, and an admin cost dashboard.
- **Rate limits and outages**: 6-hour throttled fetch, health monitoring and multiple sources.
- **PDPL/GDPR**: consent history, encryption at rest (files, tokens), export/delete, minimal AI payloads, and disclosure of cross-border processing.

## 9. Pricing and cost (per 100 users, ~60 active)
AI $100–160 · hosting/DB/storage $40–90 · email $0–20 · WhatsApp (Phase 2) $20–40 · Stripe fees ~$15 → **≈ $175–325/month**. Revenue at 30% paid conversion ≈ $400–500/month. Plans: Free, Pro $12 (~SAR 45), Premium $25 (~SAR 95).
