# JobPilot — PRD

## Original problem statement
Multi-tenant SaaS "ERP for job seekers" (JobPilot). It collects jobs for a chosen country (Saudi Arabia/GCC first), tracks applications, sends reminders, connects to Gmail (WhatsApp in Phase 2), and uses AI to review jobs against the user's CV and generate tailored CVs. The UI is bilingual Arabic RTL / English. The user approves everything before it is sent. The approved plan is in the conversation; the technical blueprint is in /app/memory/BLUEPRINT.md.

## Personas
- Job seekers (GCC, mid-career)
- Super admin (owner)
- Career coaches (Phase 3)

## Architecture
- FastAPI (modular routers r_*.py) + MongoDB + React SPA (i18n EN/AR RTL)
- APScheduler jobs: reminders every 1 min, source fetch every 6 h, ghost check every 12 h
- Emergent object storage, with files Fernet-encrypted
- AI on the Emergent LLM key: Claude Haiku 4.5 for scoring, Sonnet 4.6 for writing; admin can switch to GPT, Gemini or NVIDIA
- Nano Banana for avatars
- Resend-managed email

## Implemented (2026-06, Phase 1 MVP)
- JWT + Emergent Google auth, onboarding, consents, super admin seed
- CV vault: upload, AI parse, editor, versions, restore
- Job feed: Remotive, Arbeitnow, Greenhouse (careem, tamara), plus Careerjet and Jooble, which activate when keys are supplied
  - dedupe, filters, saved searches with in-app/email alerts, manual add with AI normalization
- AI review with caching per CV version
- AI tailoring + cover letter
  - validation: rules + LLM, with remove/confirm per flag
  - side-by-side diff, approval gate, PDF/DOCX export (Arabic supported)
- Kanban tracker: drag and drop, list view, drawer with notes, contacts, documents, timeline and dates
- Reminders: rules + custom, done/snooze, timezone and quiet hours, in-app + email
- Gmail drafts and send, with a confirm step; needs Google OAuth client ID/secret
- Dashboard: funnel, response and interview rates, sources, weekly goal
- Billing: plans + usage meters + 402 upgrade prompt
  - Stripe checkout code is ready but NOT ACTIVE, because the sandbox is unavailable for Saudi Arabia; the admin assigns plans manually
- Admin panel: stats, users, plans, source health, AI cost + model switch, audit log
- Privacy: consent history, JSON export, account deletion
- Bilingual legal pages

## Implemented (2026-06, Phase 2 + Phase 3 items)
- Interview-prep pack per application (AI, answers drawn only from real CV facts)
- Admin AI evaluation runner: 6 EN/AR cases in backend/eval/cases.json, measuring verdict agreement, skill recall, validator recall on seeded fakes, and cost
- WhatsApp Cloud API: OTP opt-in, reminder template, webhook handling done/snooze/STOP. Inactive until WHATSAPP_* env keys are set
- Adzuna fetcher (inactive until ADZUNA_APP_ID/KEY are set)
- "Save job from any site" bookmarklet, which prefills /app/jobs?add_text=&add_url=
- Installable PWA (manifest + service worker)
- Coach workspaces: candidate grants access by coach email; coach sees the pipeline and comments; candidate is notified and can revoke
- Admin anonymised insights: response rate by weekday and by source
- Plans:
  - admin is always on Premium
  - admin can grant Pro/Premium for N days, with automatic expiry back to Free
  - optional new-user trial (Admin > Plans)
- Guard: admin cannot select NVIDIA models without NVIDIA_API_KEY

## Backlog
- P0: add Google OAuth credentials (Gmail), Careerjet/Jooble keys, and Stripe keys or a local gateway (Moyasar/Tap)
- P1: Gmail inbox scanning (needs Google verification), Moyasar/Tap payments (needs merchant keys), grow the eval set to 30 cases
- P2: salary benchmark, push notifications, coach billing
