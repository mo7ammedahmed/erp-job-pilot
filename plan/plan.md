# JobPilot — Plan

A bilingual (Arabic RTL / English) "ERP for job seekers" that collects jobs for a chosen country, tracks every application, and sends reminders.
AI scores each job against the user's real CV and writes a tailored CV and cover letter. Nothing is sent or applied without the user's approval.

## Who it's for

- **Job seekers**, starting with Saudi Arabia and the wider GCC, and able to expand to any country. Mostly mid-career professionals who apply to many roles and lose track of them.
- **Super admin (owner)** who runs the platform, plans, sources, and AI costs.
- **Career coaches** who manage several candidates (Phase 3).

## Core features and experience

**1. Accounts, workspaces, plans**
- Sign in with email/password or Google. Every user gets a private workspace. Coach workspaces with several candidates come later.
- Three plans with monthly usage limits, paid through Stripe:
  - **Free**: 1 master CV, 10 AI job reviews, 2 tailored CVs, 25 tracked applications, in-app reminders only.
  - **Pro** (USD 12 / ~SAR 45 per month): 150 reviews, 30 tailored CVs, unlimited tracking, email reminders, Gmail sending.
  - **Premium** (USD 25 / ~SAR 95 per month): 500 reviews, 100 tailored CVs, priority AI, plus WhatsApp reminders and inbox scanning once Phase 2 ships.
- The user can always see a usage meter. Hitting a limit opens a prompt to upgrade and never deletes data.

**2. CV vault (master CV)**
- Upload a PDF or DOCX. AI reads it into a structured profile: experience, skills, education, projects, languages, and certifications.
- The user checks and edits the result, then saves it as the **master CV**. Every save creates a new version, and older versions can be viewed or restored.
- The master CV is the only source of truth for all AI writing.

**3. Job feed**
- Search preferences: country, city, remote/on-site/hybrid, keywords, seniority, and minimum salary. Users can save several searches.
- Jobs are fetched on a schedule, only from legal sources (see "Job sources" below). They are converted to one common format, and duplicates across sources are merged.
- A filterable feed shows the source, posting date, location, salary if listed, and a match badge after review. Each saved search can send new-match alerts (in-app, plus an email digest).
- **Add a job manually**: paste a job description or link. This covers LinkedIn, Bayt, and company sites without scraping them.

**4. AI job review**
- One click, or automatic for new matches on paid plans. Output:
  - match score from 0 to 100
  - matched skills and missing skills
  - keyword gaps
  - red flags
  - notes on salary, visa/nationality (for example Saudization-only roles) and location
  - a verdict of **Apply / Maybe / Skip**, with reasons
- A job is reviewed once per CV version. Repeat views are free and don't count toward usage.

**5. AI CV tailoring**
- Master CV + job description gives a tailored, ATS-friendly CV and cover letter, in Arabic or English.
- **Hard rule: nothing is invented.** The AI can only reorder, rephrase, and emphasize content that is in the master CV.
- A separate automatic **validation check** compares the tailored CV with the master CV. It flags any employer, title, date, skill, number, or degree that isn't in the master CV. The user sees each flag and must remove or confirm it before approving.
- A side-by-side diff against the master CV shows what changed. The user edits, approves, then exports to PDF or DOCX. Each approved version is linked to its application.

**6. Application tracker**
- Kanban board: Saved, Preparing, Applied, Interview, Offer, Rejected, Ghosted. Cards can be dragged between columns, and there is a list view too.
- Each application has notes, contacts (recruiter or hiring manager), documents (CV versions and files), a timeline of every change, interview dates, and follow-up dates.
- An application that gets no reply for 21 days (the user can change this) is suggested for "Ghosted". It never moves automatically.

**7. Reminders**
- Rules:
  - follow up N days after applying (default 7)
  - interview prep 24 hours and 1 hour before
  - application deadline 2 days before
  - custom reminders
- Channels: in-app and email in Phase 1, WhatsApp in Phase 2.
- Each user's timezone and quiet hours are respected. The default is 22:00–08:00, and reminders that fall inside quiet hours go out when they end.
- Each reminder can be marked done or snoozed (1 hour, 1 day, 1 week).

**8. Gmail (Phase 1: drafts and send)**
- Opt-in "Connect Gmail" through Google's own consent screen.
- JobPilot builds an application or follow-up email with the approved CV attached, and saves it as a Gmail draft or sends it from the user's own account. The user presses Send inside JobPilot. Nothing is sent automatically.
- Sent emails are logged on the application timeline.
- Inbox scanning to auto-detect recruiter replies is Phase 2, also opt-in.

**9. WhatsApp (Phase 2)**
- Only the official WhatsApp Business Cloud API.
- Explicit opt-in: the user enters a number, confirms a code, and ticks a consent box.
- Reminders use Meta-approved templates.
- Replies such as "done" or "snooze 1d" update the reminder or tracker. "STOP" opts the user out.

**10. Dashboard**
- The funnel (Saved → Applied → Interview → Offer), response rate, interview rate, and the sources that bring the most interviews.
- Weekly goals, for example "apply to 10", with progress, plus upcoming interviews and follow-ups due.

**11. Admin panel**
- Users: search, plan, usage, suspend.
- Plans and limits: edit.
- Source health: last run, jobs fetched, errors.
- AI cost per user and per feature, with model settings.
- Audit log of sensitive actions: logins, exports, deletions, emails sent, admin actions.

**12. Privacy and data rights (Saudi PDPL, GDPR-ready)**
- Separate consents are recorded with a timestamp: terms, AI processing of the CV, email/WhatsApp messaging, and inbox scanning.
- Users can export everything they own (JSON + files) and permanently delete their account. Deletion wipes CVs, files, and connected-account access.
- CV files, Gmail access, and other stored secrets are encrypted. AI providers get only what each task needs, and no CV data is used to train models.
- Privacy policy and terms pages are included in both languages.

### Job sources

| Source | Coverage | Phase | Notes / risk |
|---|---|---|---|
| Careerjet Publisher API | SA, AE, QA, OM, KW, BH + ~90 countries | 1 | Official and free with a publisher key. Results link back to Careerjet, and attribution is required. |
| Jooble Partner API | Most countries, including GCC | 1 | Official and free with a key. Rate limits are shared, and results link back to Jooble. |
| Company ATS job boards (Greenhouse, Lever, Ashby, Workable, SmartRecruiters) | Any employer that uses them | 1 | Public, documented feeds. The admin keeps a list of GCC employers. Very low risk. |
| Remote boards (Remotive, Arbeitnow) | Remote roles worldwide | 1 | Public APIs. Attribution is required. |
| Manual add (paste text or link) | Anything, incl. LinkedIn, Bayt, Indeed | 1 | The user brings the content themselves, and JobPilot does not crawl the site. |
| Adzuna API | UK, EU, US, IN, AU and more (no GCC) | 2 | Used for expansion beyond the GCC. |
| Browser "save job" button | Any site the user is viewing | 2 | Only captures what the user sees and clicks to save. |
| JSearch / third-party aggregators | Global | Not planned | Their licensing of scraped data is unclear, so they stay excluded until licensing is clear. |
| LinkedIn, Bayt, Indeed, GulfTalent, Jadarat/Taqat | — | Excluded | No public job API, and their terms forbid scraping. |

### AI design (what the user will experience)
- The pipeline runs in this order: read CV → normalize job → quick match → full review → tailor → validate. Each step returns structured data, so the screens always show consistent fields.
- A cheap, fast model handles parsing, scoring, and validation. A stronger model handles writing.
  - Default: Claude Haiku 4.5 for scoring and Claude Sonnet 4.6 for writing, both on the Emergent universal key.
  - GPT and Gemini models, and the user's NVIDIA NIM key, are available as switchable alternatives in the admin panel.
- Every prompt has a version, and each AI result records the prompt version and model used. This lets quality and cost be compared over time.
- Results are cached: the same job and the same CV version are never paid for twice.
- An evaluation set of about 30 real anonymized CV/job pairs has expected verdicts and "must-not-appear" facts. It tracks:
  - verdict agreement
  - skill-match accuracy
  - hallucination rate (target 0 unflagged invented facts)
  - Arabic output quality
  - cost per task

The owner can re-run it from the admin panel whenever prompts or models change.

## User flow

1. Sign up (email or Google). Choose language (Arabic/English), country, city, timezone, and quiet hours. Accept terms and AI-processing consent.
2. Upload a CV, check the parsed profile, and save it as the master CV.
3. Set job preferences and save a search. The feed fills from the sources, and more jobs arrive on a schedule.
4. Open a job and run the AI review to see the score, gaps, and an Apply/Maybe/Skip verdict. Save it to the tracker.
5. Click "Tailor CV", then review the diff and any validation flags. Edit, approve, and export the PDF/DOCX. The version is linked to the application.
6. Optionally connect Gmail. Review the email draft with the CV attached, then send it or save it as a draft. The card moves to "Applied".
7. Reminders arrive for follow-ups, interview prep, and deadlines. Mark them done or snooze them.
8. Log updates as they happen: interview dates, contacts, and notes. The dashboard shows the funnel and weekly goal progress.
9. Upgrade from Free to Pro/Premium through Stripe checkout when limits are reached.
10. Admin: watch users, source health, and AI spend, adjust plans, and review audit logs.

## UI/UX feel

- A calm, focused productivity tool rather than a flashy job board. It is information-dense but uncluttered, and suited to daily use over weeks of job hunting.
- Full Arabic RTL: layouts, icons, and the Kanban direction all mirror. English and Arabic both use purpose-chosen typefaces, and dates and numbers follow the chosen language.
- The verdict and match score are the visual anchor on every job. Diffs and validation flags are highlighted clearly, so approving a CV feels safe and deliberate.
- The app is responsive, so the tracker and reminders work on a phone. The final visual direction comes from a dedicated design pass before building.

## Implementation phases

### Phase 1 — MVP (built now) · about 7–9 weeks of solo effort, compressed here
- Email/password + Google sign-in, personal workspaces, and a super admin account.
- Onboarding for language, country, timezone, quiet hours, and consents. Full Arabic/English with RTL.
- CV vault: PDF/DOCX upload, AI parsing, an editable master CV, and version history.
- Job feed covering:
  - Careerjet, Jooble, company ATS boards, Remotive/Arbeitnow, and manual add
  - scheduled fetching and de-duplication
  - filters, saved searches, and in-app/email alerts
- AI job review and AI CV + cover-letter tailoring with the validation check, diff, approval, and PDF/DOCX export.
- Kanban tracker with notes, contacts, documents, timeline, and interview/follow-up dates.
- Rule-based reminders through in-app and email, with timezone and quiet hours.
- Gmail connect: create drafts and send from the user's account, with approval every time.
- Dashboard with funnel, response rate, best sources, and weekly goals.
- Stripe subscriptions (Free/Pro/Premium) with usage limits and meters.
- Admin panel: users, plans, source health, AI cost per user, and audit logs.
- Data export, account deletion, consent records, encrypted secrets and files, and bilingual privacy/terms pages.
- A technical blueprint document in the project: architecture diagram, module boundaries, database schema, prompt outlines, and the evaluation plan.

### Phase 2 — v1 · about 5–6 weeks
- WhatsApp Business Cloud API: opt-in, approved reminder templates, and "done"/"snooze" replies that update the tracker.
- Opt-in Gmail inbox scanning. It suggests status changes (such as "Interview invite detected") for the user to confirm.
- Local Saudi payments through Moyasar or Tap (mada, Apple Pay, STC Pay) alongside Stripe, with SAR pricing.
- Adzuna and more countries, a browser "save job" button, and an admin screen for running the AI evaluation set.
- Interview-prep pack per application: likely questions drawn from the job and the user's real experience.

### Phase 3 — v2 · about 6–8 weeks
- Career coach workspaces: several candidates, shared tracker views, comments, and coach billing.
- Expansion to more countries with local source lists, plus an optional salary benchmark per role and city.
- Installable mobile app experience (PWA) with push notifications.
- Anonymized platform insights, such as the best days to apply and the response rate by source.

### Key risks and how they are handled
- **Legal and scraping**: only official APIs, public ATS feeds, and user-provided content are used, and each source has an on/off switch. Required attributions and link-backs are shown.
- **Gmail verification**: Google requires app verification, and a security assessment for mail-reading access. Until then the app is limited to 100 approved test users. Phase 1 uses only send and draft access. Inbox reading waits for Phase 2, after verification starts.
- **WhatsApp bans and spam**: templates only, strict opt-in, easy STOP, caps on how often messages go out, and quiet hours. Meta business verification should start early, since it can take weeks.
- **AI hallucination**: the validation check, a user approval gate, and the evaluation set with a zero-tolerance target.
- **AI cost overrun**: per-plan limits, caching, the cheap model for high-volume tasks, and an admin cost dashboard with alerts.
- **Source rate limits and outages**: throttled scheduled fetches, source health monitoring, and multiple sources per country.
- **Personal data**: consent records, encryption, export/delete, and minimal data sent to AI. Using AI providers means data is processed outside the Kingdom, so the privacy policy must disclose this, which PDPL requires.

### Estimated monthly cost per 100 users (about 60 active)
| Item | Estimate (USD/month) |
|---|---|
| AI: ~100 reviews + ~15 tailored CVs per active user (≈ $0.006 per review, ≈ $0.07 per tailored CV incl. validation) | 100 – 160 |
| Hosting, database, file storage | 40 – 90 |
| Transactional email | 0 – 20 |
| WhatsApp templates (Phase 2, ~30 per active user, ~$0.01–0.02 each) | 20 – 40 |
| Stripe fees (~3% + $0.30 per payment) | ~ 15 on $400 revenue |
| **Total** | **≈ 175 – 325** |

At a 30% paid conversion with a Pro/Premium mix, 100 users bring in roughly USD 400–500 per month.

## Assumptions

- The app is built on this platform's own stack instead of Laravel, as agreed. Modules, behaviour, and scope stay as specified.
- Several options were picked for the integration phasing, so the recommended split was used. Gmail drafts and send are in Phase 1. WhatsApp and inbox scanning are in Phase 2, because Meta and Google verification take weeks and shouldn't block launch.
- Both payment options were picked. Stripe goes first, starting in test mode, and the account can be claimed to go live. Moyasar/Tap (mada) comes in Phase 2 and will need the owner's merchant keys.
- Several AI options were picked, so the model choice is admin-switchable:
  - Default: Claude Haiku 4.5 for scoring and Claude Sonnet 4.6 for writing, on the Emergent universal key.
  - GPT-5.4-mini/GPT-5.5, Gemini 3 Flash/3.1 Pro, and the provided NVIDIA NIM key are available as alternatives.
  - The NVIDIA key was shared in chat, so rotating it on build.nvidia.com and supplying the new one is advised. It is stored only as a server secret.
- For sign-in, both email/password and Google sign-in are included.
- Gmail needs a Google Cloud OAuth client ID and secret from the owner. Careerjet and Jooble each need a free publisher key from the owner. Until these are supplied, those features show as "not connected", and the rest of the app, including ATS boards, remote boards, and manual add, still works.
- Email reminders go through the platform's managed email service. The sender is shown as "JobPilot".
- Plan names, prices, and limits are those listed above and can be edited in the admin panel.
- The default reminder rules are: follow-up 7 days after applying, interview prep 24 hours and 1 hour before, deadline 2 days before, ghosted suggestion after 21 days, and quiet hours 22:00–08:00 in the user's timezone.
- The launch languages are Arabic and English. The launch countries are the six GCC states, with Saudi Arabia as the default, and any country Careerjet or Jooble supports can be selected.
- The detailed technical blueprint (diagram, schema, prompt outlines, evaluation plan) is delivered as a document inside the project during the Phase 1 build, not in this approval plan.
- Time estimates assume one full-time developer. Cost figures are estimates based on current public prices and typical usage.
