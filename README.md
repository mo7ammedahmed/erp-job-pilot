# JobPilot

> **Language / اللغة:** [English](#english) · [العربية](#العربية)

A bilingual (Arabic RTL / English) "ERP for job seekers". It collects jobs from legal sources
across 20 markets, scores each one against the user's real CV, tailors an honest ATS-ready CV and
cover letter, fills and submits applications on the employer's own form, and tracks every
application and follow-up.

**Contents** — [English](#english) · [العربية](#العربية)

---
<a name="english"></a>

# English

## 1. What the system does

JobPilot is a multi-tenant SaaS application with three roles: a **job seeker**, a **career coach**
who supervises a candidate's pipeline, and a **super admin** who owns the platform. The job-seeker
flow is the core:

1. **Build a CV.** Upload a CV once. It is stored encrypted, parsed by AI into structured fields,
   and kept as versions. A master CV is the one that gets tailored and applied with.
2. **Discover jobs.** A background collector pulls postings from legal sources, normalises each one
   to a canonical city and country, and stores it in a searchable corpus. No scraping of sites that
   forbid it, and no LinkedIn.
3. **Review against the real CV.** AI scores a job against the actual CV, with per-criterion
   reasoning and a cached result per CV version, so re-reading the same job is free.
4. **Tailor honestly.** AI produces a CV and cover letter targeted at one job, and then *validates*
   its own output. Claims it cannot support in the source CV are flagged for the user to remove or
   confirm, and nothing is exportable until the user approves it.
5. **Apply.** Auto-apply opens the employer's real application form in a headless browser, fills
   it from the apply profile, and submits it — or deliberately stops and asks for a human.
6. **Track.** Every application becomes a card on a Kanban tracker with notes, contacts, documents,
   dates, and interview-prep packs. Reminders fire on rules or on a schedule.

## 2. Architecture

| Layer | Choice |
|---|---|
| Backend | **FastAPI** + MongoDB (Motor async driver) |
| Frontend | **React** (CRA + craco) + shadcn/ui + Tailwind |
| Scheduling | APScheduler in-process |
| Background browser | Playwright / Chromium (auto-apply only) |
| Secrets at rest | Fernet (`ENCRYPTION_KEY`) |
| Auth | JWT in cookies, plus Google OAuth |

Routers are split by domain (`r_jobs.py`, `r_cv.py`, `r_apply.py`, …) and all share `core.py` for
auth, plans, storage, email and encryption.

**Scheduled jobs** (registered at startup):

| Job | Interval |
|---|---|
| `process_reminders` | every 1 minute |
| `_scan_gmail_inbox` | every 1 hour |
| `run_all_sources` | every 6 hours |
| `ghost_check` | every 12 hours |
| `initial_fetch` | once, on boot, if the corpus is empty |

**Data model.** 30 Mongo collections. The load-bearing ones:

| Collection | Holds |
|---|---|
| `users`, `user_sessions`, `login_attempts` | accounts, sessions, and the rate-limit counter behind the 429 lockout |
| `cv_versions`, `files`, `reviews` | the CV vault, encrypted uploads, and cached AI reviews |
| `jobs`, `sources`, `searches` | the corpus, the source registry, saved searches with alerts |
| `tailored`, `ai_logs`, `ai_cache` | tailored CVs, per-call AI cost logs, and the response cache |
| `applications`, `apply_runs`, `apply_profiles` | the tracker, auto-apply evidence, and form data |
| `reminders`, `notifications` | reminder rules and in-app notifications |
| `plans`, `usage`, `payment_transactions` | entitlements, per-period meters, and payment records |
| `audit_logs`, `settings` | the admin audit trail, and the encrypted secrets / provider config |
| `coach_links`, `workspaces` | coach-to-candidate grants |
| `wa_otps`, `gmail_tokens`, `oauth_states` | WhatsApp opt-in, Gmail OAuth tokens, CSRF states |

## 3. Running it locally

Originally built for the Emergent cloud platform. Everything below sets up an equivalent stack on a
plain machine — no Docker required.

### 3.1 Prerequisites

- Python **3.12** (3.14+ is not supported by the pinned dependencies)
- Node.js 18+ (developed on Node 24)
- MongoDB

```powershell
winget install --id Python.Python.3.12
winget install --id MongoDB.Server      # installs the service, which starts automatically
```

Auto-apply drives a real browser, so it also needs Chromium — a separate ~150 MB download, only
required for that feature:

```powershell
cd backend
.\.venv\Scripts\python.exe -m playwright install chromium
```

### 3.2 Backend

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.local.txt
Copy-Item .env.example .env             # then fill it in — see below
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
```

`GET http://localhost:8000/api/health` should return `{"ok":true}`.

**Required `.env` values**

| Key | Notes |
|---|---|
| `MONGO_URL` | e.g. `mongodb://localhost:27017` |
| `DB_NAME` | e.g. `jobpilot` |
| `ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `JWT_SECRET` | any long random string |
| `FRONTEND_URL` | the frontend origin, used to build links in emails |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | seeded super admin — must be a normal-looking address (`.local` is rejected by `EmailStr`) |
| `TEST_USER_EMAIL` / `TEST_USER_PASSWORD` | seeded demo user, which also gets a seeded master CV |
| `COOKIE_SECURE` | `0` for local HTTP, `1` behind HTTPS |

Two settings that matter specifically for local dev:

- **`COOKIE_SECURE=0`** — auth cookies are cross-site (`:3000` → `:8000`), so in production they are
  `Secure; SameSite=None`. Browsers drop such a cookie over plain HTTP, which makes every
  authenticated call 401. Local HTTP therefore needs `SameSite=Lax`. Set it back to `1` for any real
  deployment.
- **`LOCAL_STORAGE=1`** — stores uploaded CVs encrypted on local disk instead of calling the Emergent
  object store, which is unreachable offline.

On first boot the app creates indexes, seeds the three plans, the job sources, both accounts and a
master CV for the demo user, then starts the scheduled jobs.

### 3.3 Frontend

```powershell
cd frontend
npm install
npm start            # http://localhost:3000
```

`frontend/.env` must point at the API:

```
REACT_APP_BACKEND_URL=http://localhost:8000
DISABLE_EMERGENT_OVERLAY=true
```

### 3.4 Sign in

| Role | Credentials |
|---|---|
| Super admin | the `ADMIN_EMAIL` / `ADMIN_PASSWORD` you set |
| Demo user | the `TEST_USER_EMAIL` / `TEST_USER_PASSWORD` you set |

The UI defaults to Arabic; the language toggle is in the header.

## 4. AI configuration

AI features (CV parsing, job review, CV tailoring, interview prep, validation, avatars and job
imagery) need a provider. There are two ways to supply one, equivalent from the app's point of view:

1. **From the admin panel** — `Admin → AI → AI providers`. Add a key for Anthropic, OpenAI,
   NVIDIA NIM, Google Gemini, or a custom OpenAI-compatible endpoint. Keys are encrypted with
   `ENCRYPTION_KEY` before storage and are never sent back to the browser — the panel only shows a
   mask such as `sk-l…abcd`. A provider in use by a tier cannot be removed.
2. **From `.env`** — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `NVIDIA_API_KEY`, `GEMINI_API_KEY`, or
   `AI_CUSTOM_API_KEY`. These act as a fallback and appear as `configured · env`.

**Model lists are discovered automatically.** Once a provider has a key, the panel calls that
provider's `GET /models` endpoint and populates the scoring and writing dropdowns from the response,
so newly released models can be selected without a code change. The list is cached for an hour;
`Load models` forces a refresh. Embedding, guard and reranker models are filtered out since they
cannot serve chat prompts. If a provider is unreachable the panel falls back to the short catalog in
`backend/ai.py` and says why.

Providers are called directly. `openai`, `nvidia`, `gemini` and `custom` speak the OpenAI
chat-completions format; `anthropic` uses its native Messages API. Any OpenAI-compatible gateway
(OpenRouter, Groq, Together, Ollama, LM Studio, vLLM) works by adding a `Custom` provider and
pointing it at that gateway's base URL.

With no key at all, a provider in the shipped catalog still routes through the Emergent universal
gateway when `EMERGENT_LLM_KEY` is set.

### 4.1 Admin-managed secrets

Every integration key — the AI providers above, plus Careerjet, Jooble, Adzuna, Gmail/Google OAuth,
Moyasar, Stripe and WhatsApp — can be set from **Admin → Integrations** instead of `.env`. Values are
encrypted with `ENCRYPTION_KEY` before storage and are never returned to the browser; the API
reports only a `configured` boolean and the panel shows a masked value.

Resolution order is **stored secret, then environment variable, then empty**, so a key entered in the
dashboard takes effect immediately without a redeploy. Clearing a stored value falls back to the
environment. Keyless sources are shown as *No key needed* rather than *API key required*.

Stored under the `settings` collection: `integration_secrets` (all integration keys), `ai_providers`
(provider config), `ai_image` (image generation settings).

### 4.2 Image generation

`Admin → AI → Image` configures the provider used to generate job imagery and avatars. It works with
either Google Gemini (native `generativelanguage.googleapis.com` image generation) or any
OpenAI-compatible `/images/generations` endpoint, and handles both base64 and URL responses, detecting
PNG/JPEG/WebP from the bytes. The selection is stored under the `ai_image` settings key and every
change is written to the audit log.

### 4.3 When AI is unavailable

CV parsing never fails the upload. `POST /api/cv/upload` stores the file first, then attempts to
parse it, and always returns `200`:

```json
{ "file_id": "file_…", "filename": "cv.docx", "parsed": { … } | null, "ai": { … } | null,
  "parse_error": null | "human-readable reason" }
```

If the provider is overloaded, misconfigured, or the plan's AI-parse allowance for the period is
spent, `parsed` is `null` and `parse_error` explains why. The file is still stored and the user can
fill the profile in by hand. `POST /api/cv/parse` with `{ "file_id": … }` re-runs parsing later
without re-uploading; it returns `402` if the period's allowance is already spent and `502` if the
provider is failing.

The plan limit meters the AI parse, not the upload, so a user can never be locked out of their own CV
vault. Intermittent provider overload (for example NVIDIA returning `503`) is treated as non-fatal
degradation rather than an error.

## 5. Plans and billing

Three plans are seeded. The admin is always on Premium; other users are assigned a plan by the admin
or by an optional new-user trial, and a granted plan expires automatically back to Free.

| Plan | Price | Reviews | Tailors | CVs | Applications | WhatsApp |
|---|---|---|---|---|---|---|
| Free | $0 | 10 | 2 | 1 | 25 | no |
| Pro | $12 / 45 SAR | 150 | 30 | 5 | unlimited | no |
| Premium | $25 / 95 SAR | 500 | 100 | 10 | unlimited | yes |

`USAGE_FOR` maps the limit names onto the meters that consume them. When a meter is exhausted the API
returns `402` with an upgrade prompt.

**Payments are inactive by default.** Stripe checkout and Moyasar (Tap's Saudi gateway) code paths
exist, but the Stripe sandbox is unavailable for Saudi Arabia, so the admin assigns plans manually.
Set the relevant secrets in `Admin → Integrations` to activate a gateway.

## 6. Auto-apply

Auto-apply fills and submits the **employer's real application form** in a headless browser
(Playwright/Chromium), using **Settings → Apply profile** plus the user's master CV. There is no
separate "apply API": the browser opens the ATS page the job came from and drives the form on it.

Supported platforms — anything else is refused rather than driven:

| Platform | Forms are driven at |
|---|---|
| Greenhouse | the job page's inline form |
| Lever | `jobs.lever.co/<board>/<id>/apply` |
| Ashby | the job's `applyUrl` |
| Workable | `apply.workable.com/<board>/j/<id>` |
| SmartRecruiters | the job page's apply modal |

Each job stores `apply_url`, `ats` and `ats_board` at ingest, so the form is addressed directly rather
than re-derived. Jobs that predate this are backfilled on the next source refresh, and `upsert_jobs`
keeps all three current on every re-ingest.

### 6.1 What it will and will not do

Auto-apply writes to a third party on the user's behalf, so it is deliberately conservative:

- **It never bypasses bot protection.** reCAPTCHA, hCaptcha, Turnstile, Cloudflare, DataDome and
  PerimeterX all stop the run as `needs_human`. It does not attempt to solve or evade them.
- **It never submits a half-filled form.** Any required field it cannot confidently populate also
  returns `needs_human`, naming the field, rather than sending blanks.
- **It is never silent.** Every run records a status, a reason, the final URL and a screenshot of the
  form, and the tracker only advances on a verified submission. A blocked or failed run leaves the
  application exactly where it was.
- **It is always user-initiated.** Runs only start when the user presses the button. `POST
  /api/apply/preview` fills the form and screenshots it *without* submitting, so the user can check
  the data first.

Outcomes are `submitted`, `filled` (preview only), `needs_human`, `unsupported`, `failed` and
`unknown` (submitted but the confirmation could not be verified). Runs are capped per month per user
to keep the shared egress IP from hammering a handful of ATS platforms.

| Endpoint | Purpose |
|---|---|
| `GET` / `PUT /api/apply/profile` | read and save the apply profile |
| `POST /api/apply/preview` | fill the form, screenshot it, submit nothing |
| `POST /api/apply` | fill and submit |
| `GET /api/apply/runs` | run history with per-run evidence |

Set `JOBPILOT_APPLY_EXTRA_HOSTS` (comma-separated) to add a self-hosted ATS to the allowlist; the
defaults are unchanged.

To check the browser engine without submitting anything to a real employer:

```powershell
cd backend
.\.venv\Scripts\python.exe -X utf8 scripts\test_apply_engine.py
```

It serves mock ATS forms locally and asserts that fields are filled, that a CAPTCHA stops the run
before submission, and that an unmodelled host is refused.

## 7. Job sources and market coverage

Sources live in `db.sources` and are managed from **Admin → Source health**.

**Keyless ATS feeds.** These need a **board token** — the employer's account slug, which is the path
segment in their careers URL:

| Platform | Where the token is | Boards enabled |
|---|---|---|
| Greenhouse | `job-boards.greenhouse.io/<board>` | 10 |
| Lever | `jobs.lever.co/<board>` | 10 |
| Ashby | `jobs.ashbyhq.com/<board>` | 7 |
| Workable | `apply.workable.com/<board>/j/...` | 18 |
| SmartRecruiters | `jobs.smartrecruiters.com/<board>` | 5 |

**50 board tokens in total, every one verified to return live Saudi postings.** A token seen in a URL
is not sufficient evidence: slugs get reassigned between employers, and several plausible-looking
tokens turned out to belong to unrelated companies. `scripts/validate_board_tokens.py` runs each
candidate through the production fetcher and reports the job count and the Saudi share, so only
boards that genuinely help are enabled.

**Keyless sources that need no token** and cover whole markets:

| Source | Kind | Scope |
|---|---|---|
| Remotive | public API | remote roles, worldwide |
| Arbeitnow | public API | remote roles, worldwide |
| Jobb.ae | RSS | Saudi/GCC |
| JobHunt | HTML index | UAE/GCC aggregator |

**Sources that need a key** (appear as `not_connected` until set):

| Source | Variables | Saudi support |
|---|---|---|
| Careerjet | `CAREERJET_AFFID` | yes |
| Jooble | `JOOBLE_API_KEY` | yes |
| Adzuna | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | **no** — Adzuna has no `sa` market |

Board tokens are not guessable, so the **Test** button probes them without saving. Testing does not
modify the saved list; the field saves when you click away.

### 7.1 What cannot be covered, and why

**The largest Saudi employers are not reachable through ATS feeds.** Aramco, SABIC, stc, NEOM,
PIF/Qiddiya and the banks run Oracle Taleo, SAP SuccessFactors or proprietary career portals, none of
which publish board tokens. They would need a licensed aggregator feed; scraping them is not an
option. The public-token platforms serve international companies with a Saudi presence and
Saudi-founded startups — which is why the enabled boards skew toward fintech, logistics and giga-project
contractors.

**LinkedIn is intentionally absent.** There is no public jobs API and its User Agreement forbids
scraping. LinkedIn-listed roles reach JobPilot through the employers' own ATS boards. A licensed
aggregator allowed to redistribute LinkedIn postings can be added as a normal `partner_api` source:
add its `env_key` plus an `f_<name>` fetcher, and it plugs into `run_source`/`upsert_jobs` unchanged.

**28% of the corpus is untagged** and therefore invisible to every country filter. These are jobs in
cities outside the 20 supported markets (Madrid, Tokyo, Singapore, Zurich, São Paulo …). Adding those
markets is a scope decision, not a defect; none of them are recoverable from the current city map.

To widen Saudi coverage today, add Careerjet and Jooble keys. The ATS feeds cover individual employers
and are limited to the boards you list.

### 7.2 Cities and countries

City matching is data-driven: `backend/sources.py` holds a canonical key per city with English and
Arabic aliases, and the country filter, the city picker and the front-end list all read from it. That
is **76 Saudi cities plus 182 cities across 20 markets (258 keys total)**, with Mecca/Makkah and
Medina/Madinah resolved to one key each.

Matching is word-boundary based and longest-alias-first, so `Duba` is never swallowed by `Dubai` and
`Al Ula` is never read as `Ula`. A few rules that exist because real data demanded them:

- **Spaceless spellings.** ATS feeds routinely write `alkhubar` for `Al Khobar`, so the spaceless form
  of every multi-word alias is registered as a variant of the same city.
- **Transliteration variants.** `Khubar`/`Khobar` and `Buraydah`/`Buraidah` are the same city, so both
  are aliases of one key. Arabic is stored in the correct script, never as Latin transliteration.
- **City names beat country names.** `kuwait` is the country *and* the alias for Kuwait City, so a
  known city name is matched before the "this is a country, not a city" check runs.
- **A recognised city settles the country.** Greenhouse published one role as
  `"Abu Dhabi, Saudi Arabia"`; scanning the whole location string matched "saudi" and filed a UAE job
  under Saudi Arabia. The city now decides its own market.
- One deliberate trade-off: Arabic `صور` is both Sur (Oman) and Sidon (Lebanon), so Sidon keeps it and
  Sur is reachable in Latin script only.

`validate_cities.py` enforces all of this, including that no alias maps to two cities, that every city
detects its own market, and that no alias mixes Arabic and Latin scripts:

```powershell
cd backend
.\.venv\Scripts\python.exe -X utf8 scripts\validate_cities.py
```

The front-end city list is generated from the backend and written into
`frontend/src/lib/constants.js` in place, so the two cannot drift. It is never hand-edited:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\gen_frontend_cities.py   # rewrites constants.js
```

When the city model changes, re-run `migrate_city_keys.py` to recompute `city_key` and `country` for
already-stored jobs. It calls the same `resolve_location()` the ingest path uses, so a rule added in
one place applies to both.

## 8. Internationalisation

Arabic and English are both first-class. The UI defaults to Arabic (`jp_lang` in local storage) and
switches to `dir="rtl"` when Arabic is active.

Every user-facing string goes through `t()` in `frontend/src/lib/i18n.js`, with Arabic in
`frontend/src/lib/ar.js`. `check_i18n.py` is a gate, not a lint suggestion — it fails on a duplicate
key (a later entry silently shadows an earlier one), a `t()` key with no Arabic, or an unwrapped
literal in a component:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\check_i18n.py
```

Current state: 485 translation pairs, 378 required keys, zero failures. Backend `HTTPException`
messages are English-only and follow one punctuation convention.

## 9. Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q -o addopts=
```

Current state: **93 passed, 3 skipped.** The 3 skips are the slow AI tests.

The suite talks to a **running** API over HTTP, so start the backend first. `backend/tests/conftest.py`
reads the target URL and the seeded credentials from `backend/.env`, so no shell setup is needed;
export `REACT_APP_BACKEND_URL`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `TEST_USER_EMAIL` and
`TEST_USER_PASSWORD` to point it somewhere else.

`RUN_AI_TESTS=1` additionally enables the slow AI tests. The AI-heavy endpoints take 40–90s, so they
are off by default.

`backend/pytest.ini` pins `addopts = -n 2 --dist loadscope`, so the suite runs two workers in
parallel by default. **Do not edit that line**; pass `-n 0` to force serial execution, or
`-o addopts=` to drop it entirely.

Repeated test logins can trip the login rate limiter and return 429. Clear it with:

```powershell
.\.venv\Scripts\python.exe scripts\reset_login_lockout.py
```

`test_apply_engine.py` is deliberately *not* part of this suite. It needs a live Chromium and a local
HTTP server, and it must never submit to a real employer, so it runs standalone.

## 10. Operations scripts

All live in `backend/scripts/`.

| Script | Purpose |
|---|---|
| `check_sources.py` | live status of every source and job counts |
| `validate_board_tokens.py` | run candidate board tokens through the real fetchers and report Saudi share |
| `migrate_board_tokens.py` | add the verified board list to existing databases (`--dry-run`, `--replace`) |
| `ingest_ats_boards.py` | ingest the ATS boards and report per-board and per-city coverage |
| `validate_cities.py` | assert the city/alias data and cross-market detection |
| `check_city_filter.py` | check the live `/jobs` city and country filters against the real database |
| `check_i18n.py` | assert no duplicate Arabic keys, no missing translations, no unwrapped copy |
| `gen_frontend_cities.py` | regenerate the front-end city list into `constants.js` |
| `migrate_city_keys.py` | recompute `city_key` and `country` for stored jobs |
| `audit_city_keys.py` | report stored city keys that are not canonical |
| `audit_filter_coverage.py` | measure how much of the corpus the filters can actually reach |
| `audit_mixed_script_aliases.py` | find city aliases that mix Arabic and Latin |
| `list_routes.py` | print every registered API route, grouped by module |
| `check_readme.py` | assert this file has no corrupted characters, balanced code fences, valid anchors |
| `check_saudi_coverage.py` | verify the Saudi feed end to end over the API |
| `retag_countries.py` | recompute country tags after changing detection |
| `test_apply_engine.py` | drive the apply engine against mock ATS forms |
| `reset_login_lockout.py` | clear Mongo `login_attempts` after repeated test logins |

`migrate_board_tokens.py` exists because `server.py` seeds sources with `$setOnInsert`: changing
`DEFAULT_SOURCES` only reaches brand-new databases, so an existing deployment needs a migration to
pick up new board tokens. It unions rather than replaces, so hand-edited board lists survive.

## 11. Security and compliance notes

- **Everything sensitive is encrypted at rest** with `ENCRYPTION_KEY`: CVs, exports, OAuth tokens,
  WhatsApp OTPs and every integration key. Secrets are never returned by any API; only a `configured`
  boolean and a masked value reach the browser.
- **Uploads are validated and scoped.** A CV file is owned by exactly one user, and parse and
  download endpoints check ownership rather than trusting an id.
- **Login is rate limited** with a persisted counter, returning 429 and a lockout after repeated
  failures.
- **Admin mutations are audited** — user and plan changes, provider keys, image settings, and eval
  runs all land in `audit_logs`.
- **The app refuses to scrape what forbids it.** Only sources that publish an API, an RSS feed, or
  permit crawling in `robots.txt` are used.
- **The admin AI evaluation runner** (`backend/eval/cases.json`, 8 EN/AR cases) measures verdict
  agreement, skill recall, validator recall on seeded fakes, and cost, so a model or prompt change
  can be judged rather than assumed.

## 12. API reference

116 routes under `/api`, grouped by domain:

| Prefix | Domain |
|---|---|
| `/api/auth`, `/api/oauth`, `/api/onboarding`, `/api/me` | authentication, Google OAuth, profile, avatar |
| `/api/cv`, `/api/files` | CV vault, versions, restore, encrypted file download |
| `/api/jobs`, `/api/meta`, `/api/searches` | the corpus, filters, manual add, AI review, salary, saved searches |
| `/api/tailor`, `/api/tailored` | tailoring, validation flags, approval, export |
| `/api/applications`, `/api/apply` | the tracker, and the auto-apply profile, runs and preview |
| `/api/reminders`, `/api/notifications`, `/api/dashboard` | reminders, in-app notifications, analytics |
| `/api/gmail`, `/api/whatsapp` | Gmail drafts and inbox scan, WhatsApp OTP and reminders |
| `/api/billing`, `/api/stripe` | plans, checkout, Moyasar and Stripe callbacks |
| `/api/coach` | coach grants, candidate pipelines, comments |
| `/api/admin` | stats, users, plans, source health, integrations, AI providers, models, image settings, audit, eval, insights |
| `/api/privacy` | consent history, JSON export, account deletion |

Regenerate the full list with `scripts/list_routes.py` rather than trusting this table.

## 13. Repository layout

```
backend/     FastAPI app: core.py (auth, plans, storage, email), r_*.py routers, ai.py, sources.py
            apply.py (auto-apply browser engine), r_apply.py (its API)
            scripts/ (operations and validation scripts), tests/, eval/cases.json
frontend/    CRA + craco React app, shadcn/ui components, i18n in src/lib
memory/      PRD and technical blueprint
plan/        Product plan
```

## 14. Notes on local-only shims

`backend/emergentintegrations/` is a local stand-in for Emergent's private `emergentintegrations`
package, which is not published to PyPI. It re-implements the small surface `ai.py` uses and routes
to any OpenAI-compatible endpoint. Delete the directory if you install the real package.

`backend/requirements.local.txt` lists only what is needed to boot. The pinned `requirements.txt` is
a full snapshot of the hosted image's `site-packages`, including transitive and dev-only packages, and
is not installable offline.

`frontend/public/index.html` ships no analytics by default. Emergent's hosted-preview integration
(PostHog with **session recording**) is opt-in, because session replay on this app would capture CVs,
salary figures and contact details. To re-enable it: `$env:REACT_APP_EMERGENT_ANALYTICS="1"; npm run
build`. The default build contains no reference to `ap.emergent.sh` at all.

---
<a name="العربية"></a>

# العربية

## ١. ما الذي يفعله النظام؟

JobPilot تطبيق SaaS متعدد المستأجرين بواجهة ثنائية اللغة (عربي من اليمين إلى اليسار / إنجليزي).
يجمع الوظائف من مصادر قانونية في **٢٠ سوقاً**، ويقيّم كل وظيفة مقابل السيرة الذاتية الحقيقية للمستخدم،
ويعدّل سيرة ذاتية وخطاب تغطية صادقين وجاهزين لأنظمة التقديم (ATS)، ويملأ نماذج التقديم على موقع
صاحب العمل نفسه ويرسلها، ويتابع كل طلب وكل متابعة.

الأدوار ثلاثة: **باحث عن عمل**، و**مدرّب مهني** يتابع خط مرشّحه، و**مدير نظام** يملك المنصة.
مسار الباحث هو الأساسي:

١. **بناء سيرة ذاتية.** تُرفع السيرة مرة واحدة، وتُخزَّن مشفّرة، ويفكّها الذكاء الاصطناعي إلى حقول
منظّمة، وتُحفظ بنسخ. النسخة المرجعية (master) هي التي يُعدَّل عليها ويُقدَّم بها.
٢. **اكتشاف الوظائف.** جامع يعمل في الخلفية يسحب الإعلانات من المصادر القانونية، ويوحّد كل إعلان
إلى مدينة ودولة معياريتين، ويخزّنه في فهرس قابل للبحث. لا كشط للمواقع التي تمنعه، ولا لينكدإن.
٣. **التقييم مقابل السيرة الحقيقية.** الذكاء الاصطناعي يقيّم الوظيفة مقابل السيرة الفعلية مع تعليل
لكل معيار، والنتيجة مخزّنة مؤقتاً لكل نسخة سيرة، فتُعاد القراءة نفسها بلا تكلفة.
٤. **تعديل صادق.** يُنتج الذكاء الاصطناعي سيرة ورسالة تغطية موجّهتين لوظيفة واحدة، ثم **يتحقق** من
ناتجه. أي ادعاء لا يدعمه السجل الأصلي يظهر كعلامة للمستخدم ليحذفه أو يؤكده، ولا يمكن التصدير قبل
موافقة المستخدم.
٥. **التقديم.** يفتح التقديم التلقائي نموذج صاحب العمل الحقيقي في متصفح مخفي، ويملؤه من ملف
التقديم، ويرسله — أو يتوقف عمداً ويطلب تدخّل إنسان.
٦. **المتابعة.** كل طلب تصبح بطاقة في لوحة كانبان، مع ملاحظات وجهات اتصال ومستندات وتواريخ وحزم
تحضير مقابلات. وتُطلق التذكيرات حسب قواعد أو حسب جدول.

## ٢. البنية التقنية

| الطبقة | الاختيار |
|---|---|
| الخلفية | **FastAPI** + MongoDB (تشغّال Motor غير متزامن) |
| الواجهة | **React** (CRA + craco) + shadcn/ui + Tailwind |
| الجدولة | APScheduler داخل العملية |
| متصفح الخلفية | Playwright / Chromium (للتقديم التلقائي فقط) |
| التشفير عند التخزين | Fernet (`ENCRYPTION_KEY`) |
| المصادقة | JWT داخل الكوكيز، إضافة إلى Google OAuth |

الموجّهات مقسّمة حسب المجال (`r_jobs.py`، `r_cv.py`، `r_apply.py` …) وجميعها تشترك في `core.py`
للمصادقة والخطط والتخزين والبريد والتشفير.

**المهام المجدولة** (تُسجَّل عند الإقلاع):

| المهمة | الفترة |
|---|---|
| `process_reminders` | كل دقيقة |
| `_scan_gmail_inbox` | كل ساعة |
| `run_all_sources` | كل ٦ ساعات |
| `ghost_check` | كل ١٢ ساعة |
| `initial_fetch` | مرة واحدة عند الإقلاع، إذا كان الفهرس فارغاً |

**نموذج البيانات.** ٣٠ مجموعة في Mongo. الأهم منها:

| المجموعة | المحتوى |
|---|---|
| `users`، `user_sessions`، `login_attempts` | الحسابات والجلسات وعدّاد حدّ محاولات الدخول الذي يعطي 429 |
| `cv_versions`، `files`، `reviews` | خزانة السير الذاتية، والملفات المشفّرة، ونتائج التقييم المخزّنة |
| `jobs`، `sources`، `searches` | الفهرس، وسجل المصادر، والبحثات المحفوظة مع التنبيهات |
| `tailored`، `ai_logs`، `ai_cache` | السير الذاتية المعدّلة، وسجلات تكلفة كل نداء، وذاكرة الردود |
| `applications`، `apply_runs`، `apply_profiles` | لوحة المتابعة، وأدلة التقديم التلقائي، وبيانات النموذج |
| `reminders`، `notifications` | قواعد التذكير والإشعارات داخل التطبيق |
| `plans`، `usage`، `payment_transactions` | الصلاحيات، وعدّادات الفترة، وسجلات الدفع |
| `audit_logs`، `settings` | سجل تدقيق المدير، والأسرار ومزوّدي الذكاء الاصطناعي مشفّرة |
| `coach_links`، `workspaces` | ربط المدرّبين بالمرشحين |
| `wa_otps`، `gmail_tokens`، `oauth_states` | موافقة واتساب، ورموز Gmail OAuth، وحالات CSRF |

## ٣. التشغيل محلياً

بُني المشروع أصلاً لمنصة Emergent السحابية، وكل ما يلي يوفّر مكافئاً على جهاز عادي — بدون Docker.

### ٣.١ المتطلبات

- Python **3.12** (الإصدار 3.14+ غير مدعوم بالاعتماديات المثبّتة)
- Node.js 18+ (تطوّر عليه Node 24)
- MongoDB

```powershell
winget install --id Python.Python.3.12
winget install --id MongoDB.Server      # يثبّت الخدمة، وتبدأ تلقائياً
```

التقديم التلقائي يشغّل متصفحاً حقيقياً، ويحتاج أيضاً Chromium — تنزيل منفصل بحجم ~١٥٠ ميجابايت،
مطلوب لهذه الميزة فقط:

```powershell
cd backend
.\.venv\Scripts\python.exe -m playwright install chromium
```

### ٣.٢ الخلفية

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.local.txt
Copy-Item .env.example .env             # املأه — انظر أدناه
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
```

يجب أن يُرجع `GET http://localhost:8000/api/health` القيمة `{"ok":true}`.

**القيم المطلوبة في `.env`**

| المفتاح | ملاحظات |
|---|---|
| `MONGO_URL` | مثل `mongodb://localhost:27017` |
| `DB_NAME` | مثل `jobpilot` |
| `ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `JWT_SECRET` | أي سلسلة عشوائية طويلة |
| `FRONTEND_URL` | أصل الواجهة، يُستخدم لبناء الروابط في البريد |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | مدير النظام المزروع — يجب أن يكون عنواناً طبيعياً (‏`.local` مرفوض من `EmailStr`) |
| `TEST_USER_EMAIL` / `TEST_USER_PASSWORD` | المستخدم التجريبي المزروع، ويُمنح سيرة مرجعية مزروعة |
| `COOKIE_SECURE` | `0` لـ HTTP محلي، `1` خلف HTTPS |

إعدادان يهمّان تحديداً في التطوير المحلي:

- **`COOKIE_SECURE=0`** — كوكيز المصادقة عابرة للموقع (`:3000` ← `:8000`)، لذلك في الإنتاج تكون
  `Secure; SameSite=None`. المتصفحات تُسقط هذه الكوكي عبر HTTP العادي، فيصبح كل نداء مصادَق عليه 401.
  لذا يحتاج HTTP المحلي إلى `SameSite=Lax`. أعِدها إلى `1` في أي نشر حقيقي.
- **`LOCAL_STORAGE=1`** — يخزّن السير الذاتية مشفّرة على القرص المحلي بدل استدعاء مخزن كائنات
  Emergent غير المتاح دون اتصال.

عند أول إقلاع ينشئ التطبيق الفهارس، ويزرع الخطط الثلاث، ومصادر الوظائف، والحسابين، وسيرة مرجعية
للمستخدم التجريبي، ثم يبدأ المهام المجدولة.

### ٣.٣ الواجهة

```powershell
cd frontend
npm install
npm start            # http://localhost:3000
```

يجب أن يشير `frontend/.env` إلى الـ API:

```
REACT_APP_BACKEND_URL=http://localhost:8000
DISABLE_EMERGENT_OVERLAY=true
```

### ٣.٤ تسجيل الدخول

| الدور | بيانات الدخول |
|---|---|
| مدير النظام | `ADMIN_EMAIL` / `ADMIN_PASSWORD` التي ضبطتها |
| المستخدم التجريبي | `TEST_USER_EMAIL` / `TEST_USER_PASSWORD` التي ضبطتها |

الواجهة تبدأ بالعربية افتراضياً، ومبدّل اللغة في الشريط العلوي.

## ٤. إعداد الذكاء الاصطناعي

ميزات الذكاء الاصطناعي (فتح السيرة، تقييم الوظيفة، تعديل السيرة، تحضير المقابلة، التحقق، الصورة
الشخصية، وصور الوظائف) تحتاج مزوّداً. هناك طريقتان، متكافئتان من منظور التطبيق:

١. **من لوحة الإدارة** — `Admin → AI → AI providers`. أضف مفتاحاً لـ Anthropic أو OpenAI أو
   NVIDIA NIM أو Google Gemini أو نقطة نهاية متوافقة مع OpenAI. تُشفَّر المفاتيح بـ `ENCRYPTION_KEY`
   قبل تخزينها ولا تعود إلى المتصفح أبداً — اللوحة تعرض القناع فقط مثل `sk-l…abcd`. ولا يمكن حذف
   مزوّد مستخدَم في إحدى الخطط.
٢. **من `.env`** — `ANTHROPIC_API_KEY` أو `OPENAI_API_KEY` أو `NVIDIA_API_KEY` أو `GEMINI_API_KEY`
   أو `AI_CUSTOM_API_KEY`. تُستخدم كبديل وتظهر كـ `configured · env`.

**قوائم النماذج تُكتشف تلقائياً.** بمجرد وجود مفتاح، تستدعي اللوحة نقطة `GET /models` لدى المزوّد
وتملأ القوائم المنسدلة للتقييم والكتابة من الاستجابة، فتُختار النماذج الجديدة دون تعديل الكود. تُخزَّن
القائمة ساعة واحدة، و`Load models` يفرض التحديث. وتُستبعد نماذج التضمين والحُرّاس وإعادة الترتيب لأنها
لا تصلح لمطالبات المحادثة. وإذا تعذّر الوصول للمزوّد ترجع اللوحة إلى القائمة المختصرة في
`backend/ai.py` وتوضّح السبب.

يُستدعى المزوّدون مباشرةً. أما `openai` و`nvidia` و`gemini` و`custom` فتتحدث صيغة
chat-completions المفتوحة، بينما `anthropic` يستخدم واجهة Messages الأصلية. وأي بوابة متوافقة مع
OpenAI (OpenRouter أو Groq أو Together أو Ollama أو LM Studio أو vLLM) تعمل بإضافة مزوّد `Custom`
وتوجيهه إلى عنوان تلك البوابة.

وفي غياب أي مفتاح، يمرّ مزوّد موجود في القائمة المشحونة عبر البوابة الشاملة من Emergent عند ضبط
`EMERGENT_LLM_KEY`.

### ٤.١ الأسرار المُدارة من لوحة الإدارة

كل مفتاح تكامل — مزوّدو الذكاء الاصطناعي أعلاه، إضافة إلى Careerjet وJooble وAdzuna وGmail/Google
OAuth وMoyasar وStripe وWhatsApp — يمكن ضبطه من **Admin → Integrations** بدل `.env`. تُشفَّر القيم
بـ `ENCRYPTION_KEY` قبل التخزين ولا تعيدها أي واجهة برمجية؛ بل تُبلّغ فقط عن قيمة `configured`
منطقية وتعرض اللوحة قيمة مقنّعة.

ترتيب الاستخراج هو **السر المخزَّن، ثم متغيّر البيئة، ثم الفراغ**، فيسري المفتاح المدخل من اللوحة فوراً
دون إعادة نشر. ومسح القيمة المخزّنة يعود إلى البيئة. وتُعرض المصادر التي لا تحتاج مفتاحاً كـ
*No key needed* بدل *API key required*.

تُخزَّن ضمن مجموعة `settings`: `integration_secrets` (كل مفاتيح التكامل)، و`ai_providers` (إعداد
المزوّدات)، و`ai_image` (إعدادات توليد الصور).

### ٤.٢ توليد الصور

يضبط `Admin → AI → Image` المزوّد المستخدم لتوليد صور الوظائف والصور الشخصية. يعمل مع Google Gemini
(التوليد الأصلي عبر `generativelanguage.googleapis.com`) أو أي نقطة
OpenAI-compatible `/images/generations`، ويتعامل مع ردود base64 وروابط، مع كشف PNG/JPEG/WebP من
البايتات نفسها. يُخزَّن الاختيار تحت مفتاح `ai_image` وكل تغيير يُكتب في سجل التدقيق.

### ٤.٣ عند تعذّر الذكاء الاصطناعي

فتح السيرة لا يُفشل الرفع أبداً. يخزّن `POST /api/cv/upload` الملف أولاً، ثم يحاول تحليله، ويعيد دائماً
`200`:

```json
{ "file_id": "file_…", "filename": "cv.docx", "parsed": { … } | null, "ai": { … } | null,
  "parse_error": null | "سبب مفهوم بالإنجليزية" }
```

إذا كان المزوّد محمّلاً أو مُهيّأ خطأً أو استُنفد حدّ التحليل للفترة، تكون `parsed` فارغة ويشرح
`parse_error` السبب. ويبقى الملف مخزّناً ويستطيع المستخدم ملء ملفه يدوياً. و`POST /api/cv/parse` مع
`{ "file_id": … }` يعيد التحليل لاحقاً دون إعادة رفع، ويعيد `402` إذا استُنفد حدّ الفترة و`502` إذا كان
المزوّد يتعطّل.

الحدّ يقيس **التحليل** لا الرفع، فلا يُحرَم المستخدم أبداً من خزانة سيرته. ويُعامَل التحميل المؤقت
للخدمة (مثل إرجاع NVIDIA للرمز `503`) كانحلال غير قاتل لا كخطأ.

## ٥. الخطط والدفع

تُزرع ثلاث خطط. المدير دائماً على Premium، بينما تُسنَد للمستخدمين الآخرين خطة من المدير أو من تجربة
جديدة اختيارية، وتُنتهي الخطة الممنوحة تلقائياً بالعودة إلى Free.

| الخطة | السعر | مراجعات | تعديلات | سير ذاتية | طلبات | واتساب |
|---|---|---|---|---|---|---|
| Free | $0 | ١٠ | ٢ | ١ | ٢٥ | لا |
| Pro | $12 / 45 ر.س | ١٥٠ | ٣٠ | ٥ | غير محدود | لا |
| Premium | $25 / 95 ر.س | ٥٠٠ | ١٠٠ | ١٠ | غير محدود | نعم |

يربط `USAGE_FOR` أسماء الحدود بالعدادات التي تستهلكها. وإذا استُنفد عدّاد تُرجع الواجهة `402` مع طلب
ترقية.

**الدفع معطّل افتراضياً.** مسارات Stripe وMoyasar (بوابة Tap السعودية) موجودة في الكود، لكن بيئة Stripe
الاختبارية غير متاحة للسعودية، فيسنّد المدير الخطط يدوياً. اضبط الأسرار في `Admin → Integrations`
لتنشيط بوابة.

## ٦. التقديم التلقائي

يملأ التقديم التلقائي **نموذج صاحب العمل الحقيقي** ويرسله في متصفح مخفي (Playwright/Chromium)،
باستخدام **Settings → Apply profile** مع السيرة المرجعية. لا توجد واجهة «تقديم» منفصلة: المتصفح يفتح
صفحة ATS التي جاءت منها الوظيفة ويشغّل النموذج عليها.

المنصات المدعومة — وأي شيء آخر يُرفض بدل تشغيله:

| المنصة | مكان تشغيل النموذج |
|---|---|
| Greenhouse | النموذج المدمج في صفحة الوظيفة |
| Lever | `jobs.lever.co/<board>/<id>/apply` |
| Ashby | حقل `applyUrl` الخاص بالوظيفة |
| Workable | `apply.workable.com/<board>/j/<id>` |
| SmartRecruiters | نافذة التقديم في صفحة الوظيفة |

تخزّن كل وظيفة `apply_url` و`ats` و`ats_board` وقت الجلب، فيُوجَّه النموذج مباشرةً بدل إعادة اشتقاقه.
والوظائف الأقدم من ذلك تُستكمل عند التحديث التالي للمصادر، ويحافظ `upsert_jobs` على تحديث الثلاثة في كل
إعادة جلب.

### ٦.١ ما يفعله وما لا يفعله

التقديم التلقائي يكتب نيابةً عن المستخدم لدى طرف ثالث، لذلك فهو متحفّظ عمداً:

- **لا يتجاوز حماية الروبوتات.** فـ reCAPTCHA وhCaptcha وTurnstile وCloudflare وDataDome وPerimeterX
  توقف التشغيل كلها بحالة `needs_human`. ولا يحاول حلّها أو التحايل عليها.
- **لا يرسل نموذجاً ناقص الحقول.** أي حقل إلزامي لا يثق بملئه يُرجع `needs_human` مع تسمية الحقل، بدل
  إرسال فراغات.
- **لا يعمل بصمت.** يسجّل كل تشغيل حالةً وسبباً والرابط النهائي وصورة للشاشة، ولا تتقدّم لوحة المتابعة
  إلا على إرسال مؤكَّد. والتوقف أو الفشل يترك الطلب كما كان تماماً.
- **دائماً بطلب المستخدم.** لا يبدأ أي تشغيل إلا بضغط المستخدم زراً. و`POST /api/apply/preview` يملأ
  النموذج ويلتقط صورة **دون إرسال**، ليتأكد المستخدم من البيانات أولاً.

الحالات: `submitted` و`filled` (معاينة فقط) و`needs_human` و`unsupported` و`failed` و`unknown` (أُرسل
لكن لم يُؤكَّد التأكيد). وتُحدّ التشغيلات شهرياً لكل مستخدم كي لا يُرهق عنوان IP المشترك عدداً قليلاً
من منصات ATS.

| الواجهة البرمجية | الغرض |
|---|---|
| `GET` / `PUT /api/apply/profile` | قراءة ملف التقديم وحفظه |
| `POST /api/apply/preview` | ملء النموذج والتقاط صورة دون إرسال |
| `POST /api/apply` | الملء والإرسال |
| `GET /api/apply/runs` | سجل التشغيلات مع أدلة كل تشغيل |

اضبط `JOBPILOT_APPLY_EXTRA_HOSTS` (مفصولة بفواصل) لإضافة ATS ذاتي الاستضافة إلى القائمة المسموحة؛
والافتراضيات دون تغيير.

لاختبار محرّك المتصفح دون إرسال أي شيء لصاحب عمل حقيقي:

```powershell
cd backend
.\.venv\Scripts\python.exe -X utf8 scripts\test_apply_engine.py
```

يقدّم نماذج ATS وهمية محلياً ويتأكد من تعبئة الحقول، ومن أن كابتشا توقف التشغيل قبل الإرسال، ومن رفض
مضيف غير معرَّف.

## ٧. مصادر الوظائف وتغطية الأسواق

تعيش المصادر في `db.sources` ويُدار من **Admin → Source health**.

**خلاصات ATS بلا مفاتيح.** تحتاج **رمز لوحة** — وهو معرّف حساب صاحب العمل، أي المقطع في مسار رابط
وظيفته:

| المنصة | أين يوجد الرمز | لوحات مُفعّلة |
|---|---|---|
| Greenhouse | `job-boards.greenhouse.io/<board>` | ١٠ |
| Lever | `jobs.lever.co/<board>` | ١٠ |
| Ashby | `jobs.ashbyhq.com/<board>` | ٧ |
| Workable | `apply.workable.com/<board>/j/...` | ١٨ |
| SmartRecruiters | `jobs.smartrecruiters.com/<board>` | ٥ |

**٥٠ رمز لوحة إجمالاً، وكل رمز مُتحقَّق أنه يعيد إعلانات سعودية حيّة.** وجود الرمز في رابط ليس دليلاً
كافياً: فالمعرّفات تُعاد إسنادها بين أصحاب العمل، وعدة رموز تبدو معقولة اتضح أنها تخصّ شركات غير
ذات صلة. ويمرّر `scripts/validate_board_tokens.py` كل مرشّح عبر دوال الجلب الفعلية ويلتقط عدد الوظائف
وحصّتها من السعودية، فلا تُفعَّل إلا اللوحات النافعة فعلاً.

**مصادر بلا مفاتيح ولا رموز** تغطي أسواقاً كاملة:

| المصدر | النوع | النطاق |
|---|---|---|
| Remotive | واجهة عامة | وظائف عن بُعد، عالمياً |
| Arbeitnow | واجهة عامة | وظائف عن بُعد، عالمياً |
| Jobb.ae | RSS | سعودي/خليجي |
| JobHunt | فهرس HTML | مجمّع إماراتي/خليجي |

**مصادر تحتاج مفتاحاً** (تظهر `not_connected` حتى تُضبط):

| المصدر | المتغيّرات | الدعم السعودي |
|---|---|---|
| Careerjet | `CAREERJET_AFFID` | نعم |
| Jooble | `JOOBLE_API_KEY` | نعم |
| Adzuna | `ADZUNA_APP_ID`، `ADZUNA_APP_KEY` | **لا** — لا يوجد سوق `sa` في Adzuna |

رموز اللوحات غير قابلة للخمّن، لذلك يفحص زر **Test** الرمز دون حفظه. والفحص لا يغيّر القائمة
المحفوظة، والحقل يُحفظ عند النقر خارجها.

### ٧.١ ما لا يمكن تغطيته، ولماذا

**كبر أصحاب العمل السعوديين غير قابلين للتغطية عبر خلاصات ATS.** فأرامكو وسابك وstc نيوم
والصندوق الاستثماري والقدية والبنوك تعمل بأنظمة Oracle Taleo أو SAP SuccessFactors أو بوابات توظيف
خاصة، ولا ينشر أيٌّ منها رموز لوحات. ويحتاجون خط تغذية مرخّص من مجمّع؛ أما الكشط فليس خياراً. أما
منصات الرموز المفتوحة فتخدم شركات دولية لها حضور سعودي وشركات سعودية ناشئة — ولهذا تميل اللوحات
المُفعّلة إلى التمويل والتقارير اللوجستية ومتعاقدي المشاريع الضخمة.

**لينكدإن غائب عن قصد.** لا توجد واجهة عامة للوظائف، واتفاقية المستخدم تمنع الكشط. أما الوظائف
المُعلنة على لينكدإن فتصل إلى JobPilot عبر لوحات ATS الخاصة بأصحاب العمل. ويمكن إضافة مجمّع مرخّص
يجوز له إعادة توزيع إعلانات لينكدإن كمصدر `partner_api` عادي: أضِف `env_key` وجامعاً `f_<name>`،
فتتكامل مع `run_source`/`upsert_jobs` دون تغيير.

**٢٨٪ من الفهرس بلا وسم**، وبالتالي غير مرئية لأي مرشّح دولة. هذه وظائف في مدن خارج الأسواق العشرين
المدعومة (مدريد وطوكيو وسنغافورة وزيورخ وساو باولو …). وإضافة تلك الأسواق قرار نطاق وليس عيباً؛ ولا
يمكن استرجاع أيٍّ منها من خريطة المدن الحالية.

لتوسيع التغطية السعودية اليوم، أضِف مفاتيح Careerjet وJooble. أما خلاصات ATS فتغطي أصحاب العمل
الأفراد وتُحصر في اللوحات التي تسردها.

### ٧.٢ المدن والدول

مطابقة المدن قائمة على بيانات: يحتفظ `backend/sources.py` بمفتاح معياري لكل مدينة مع مرادفات إنجليزية
وعربية، ويقرأه مرشّح الدولة وقائمة المدن في الواجهة والقائمة في الواجهة الأمامية. والمجموع **٧٦ مدينة
سعودية إضافة إلى ١٨٢ مدينة في ٢٠ سوقاً (٢٥٨ مفتاحاً)**، مع توحيد مكة/مكة المكرمة والمدينة/المدينة
المنورة في مفتاح واحد.

المطابقة قائمة على حدود الكلمة وبأطول مرادف أولاً، فلا يبتلع `Duba` في `Dubai` ولا تُقرأ `Al Ula` كـ
`Ula`. وهناك قواعد وُجدت لأن البيانات الحقيقية فرضتها:

- **الإملاء بلا مسافات.** تغذّي خلاصات ATS غالباً `alkhubar` بدل `Al Khobar`، لذا تُسجَّل الصيغة بلا
  مسافة من كل مرادف متعدّد الكلمات كصيغة بديلة لنفس المدينة.
- **تنويعات النقل.** `Khubar`/`Khobar` و`Buraydah`/`Buraidah` مدينة واحدة، لذا كلاهما مرادف لمفتاح
  واحد. ويُخزَّن العربي بالحرف الصحيح لا بالنقل اللاتيني.
- **اسم المدينة يسبق اسم الدولة.** فـ `kuwait` اسم دولة **ومرادف** لمدينة الكويت، لذا يُطابَق اسم
  المدينة المعروف قبل فحص «هذا بلد لا مدينة».
- **المدينة المعروفة تحدّد الدولة.** نشرت Greenhouse وظيفة واحدة بعنوان
  `"Abu Dhabi, Saudi Arabia"`؛ فمسح النص كله التقط كلمة "saudi" وسجّل وظيفة إماراتية تحت السعودية. الآن
  هي تحدّد سوقها بنفسها.
- مقايضة مقصودة: كلمة `صور` بالعربية تعني صُور (عُمان) وصيدا (لبنان) معاً، فتُبقي صيدا هذا المرادف
  وتبقى صُور متاحة بالحرف اللاتيني فقط.

يفرض `validate_cities.py` كل ذلك، بما فيه أن لا يرتبط مرادف بمدينتين، وأن كل مدينة تكشف سوقها، وأن لا
يخلط أي مرادف بين العربية واللاتينية:

```powershell
cd backend
.\.venv\Scripts\python.exe -X utf8 scripts\validate_cities.py
```

قائمة مدن الواجهة الأمامية مولّدة من الخلفية وتُكتب في `frontend/src/lib/constants.js` في مكانها، فلا
يمكن أن تختلف الاثنتان. ولا تُعدَّل يدوياً أبداً:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\gen_frontend_cities.py   # يعيد كتابة constants.js
```

وعند تغيّر نموذج المدن، أعد تشغيل `migrate_city_keys.py` لإعادة حساب `city_key` و`country` للوظائف
المخزّنة مسبقاً. وهو يستدعي نفس `resolve_location()` الذي يستخدمه مسار الجلب، فالقاعدة المضافة في مكان
واحد تنطبق على الاثنين.

## ٨. التعريب

العربية والإنجليزية primeraويتان متساويتان. تبدأ الواجهة بالعربية (`jp_lang` في التخزين المحلي)
وتتحوّل إلى `dir="rtl"` عند تفعيل العربية.

يمرّ كل نص ظاهر للمستخدم عبر `t()` في `frontend/src/lib/i18n.js`، والعربية في
`frontend/src/lib/ar.js`. و`check_i18n.py` بوابة تحرس المشروع وليست مجرد تنبيه: فهو يفشل عند تكرار مفتاح (المدخل
اللاحق يحجب السابق دون أن يُقال)، أو عند مفتاح `t()` بلا عربية، أو عند نص حرفي غير ملفوف داخل مكوّن:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\check_i18n.py
```

الحالة الحالية: ٤٨٥ زوج ترجمة، و٣٧٨ مفتاحاً مطلوباً، وصفر إخفاقات. أما رسائل `HTTPException` في
الخلفية فبالإنجليزية فقط وتتبع قاعدة واحدة لعلامات الترقيم.

## ٩. الاختبارات

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q -o addopts=
```

الحالة الحالية: **٩٣ ناجح، ٣ متخطّاة.** والمتخطّاة هي اختبارات الذكاء الاصطناعي البطيئة.

تتخاطب المجموعة مع **واجهة برمجية قيد التشغيل** عبر HTTP، لذا شغّل الخلفية أولاً. ويقرأ
`backend/tests/conftest.py` عنوان الهدف وبيانات الاعتماد المزروعة من `backend/.env`، فلا حاجة لإعداد
في الطرفية؛ صدّر `REACT_APP_BACKEND_URL` و`ADMIN_EMAIL` و`ADMIN_PASSWORD` و`TEST_USER_EMAIL` و
`TEST_USER_PASSWORD` لتوجيهها إلى مكان آخر.

`RUN_AI_TESTS=1` يفعّل إضافة اختبارات الذكاء الاصطناعي البطيئة. ونقاط الذكاء الاصطناعي تستغرق
٤٠–٩٠ ثانية، لذلك تكون معطّلة افتراضياً.

يثبّت `backend/pytest.ini` الخيار `addopts = -n 2 --dist loadscope`، فتعمل المجموعة بعمّالين متوازيين
افتراضياً. **لا تحرّر هذا السطر**؛ مرّر `-n 0` لإجبار التنفيذ التسلسلي، أو `-o addopts=` لحذفه كلياً.

قد تؤدي محاولات تسجيل دخول متكرّرة من الاختبارات إلى تفعيل محدّد الدخول وإرجاع 429. امسحه بـ:

```powershell
.\.venv\Scripts\python.exe scripts\reset_login_lockout.py
```

و`test_apply_engine.py` ليس جزءاً من هذه المجموعة عمداً: فهو يحتاج Chromium حيّاً وخادماً HTTP محلياً،
ويجب ألّا يرسل أبداً إلى صاحب عمل حقيقي، لذا يعمل منفرداً.

## ١٠. سكربتات التشغيل

كلها في `backend/scripts/`.

| السكربت | الغرض |
|---|---|
| `check_sources.py` | حالة كل مصدر حيّاً وعدد الوظائف |
| `validate_board_tokens.py` | تشغيل رموز اللوحات المرشّحة عبر دوال الجلب الفعلية والإبلاغ عن نسبة الوظائف السعودية |
| `migrate_board_tokens.py` | إضافة قائمة اللوحات المتحقَّق منها إلى قواعد البيانات القائمة (`--dry-run`، `--replace`) |
| `ingest_ats_boards.py` | جلب لوحات ATS والإبلاغ عن التغطية لكل لوحة وكل مدينة |
| `validate_cities.py` | التحقق من بيانات المدن والمرادفات وكشف السوق عبر الأسواق |
| `check_city_filter.py` | فحص مرشّحات المدينة والدولة الحيّة في `/jobs` على قاعدة البيانات الحقيقية |
| `check_i18n.py` | التحقق من عدم تكرار مفاتيح العربية وعدم نقص الترجمات وعدم وجود نص غير ملفوف |
| `gen_frontend_cities.py` | إعادة توليد قائمة مدن الواجهة الأمامية في `constants.js` |
| `migrate_city_keys.py` | إعادة حساب `city_key` و`country` للوظائف المخزّنة |
| `audit_city_keys.py` | إبلاغ عن مفاتيح المدن المخزّنة غير المعيارية |
| `audit_filter_coverage.py` | قياس نسبة الفهرس التي يصل إليها المرشّحات فعلاً |
| `audit_mixed_script_aliases.py` | العثور على مرادفات مدن تخلط العربية باللاتينية |
| `list_routes.py` | طباعة كل واجهة برمجية مسجّلة، مجمّعة حسب الوحدة |
| `check_readme.py` | التأكد من خلوّ هذا الملف من المحارف التالفة، واتزان أسوار الشيفرة، وصحة الروابط الداخلية |
| `check_saudi_coverage.py` | التحقق من التغذية السعودية من طرف إلى طرف عبر الـ API |
| `retag_countries.py` | إعادة حساب وسم الدول بعد تغيير الكشف |
| `test_apply_engine.py` | تشغيل محرّك التقديم على نماذج ATS وهمية |
| `reset_login_lockout.py` | مسح `login_attempts` في Mongo بعد محاولات دخول متكرّرة |

ويُوجد `migrate_board_tokens.py` لأن `server.py` يزرع المصادر بـ `$setOnInsert`: فتغيير
`DEFAULT_SOURCES` لا يصل إلا إلى قواعد بيانات جديدة تماماً، فتحتاج القاعدة القائمة إلى ترحيل لالتقاط
رموز اللوحات الجديدة. وهو **يجمع** ولا يستبدل، فتبقى قوائم اللوحات المعدَّلة يدوياً.

## ١١. ملاحظات أمنية وامتثال

- **كل ما هو حسّاس مشفَّر عند التخزين** بـ `ENCRYPTION_KEY`: السير الذاتية، والتصديرات، ورموز OAuth،
  ورموز واتساب، وكل مفاتيح التكامل. ولا تُعيد أي واجهة برمجية الأسرار؛ فيصل إلى المتصفح قيمة
  `configured` منطقية وقيمة مقنّعة فقط.
- **الملفات المرفوعة مُتحقَّق منها ومُقيَّدة بمالكها.** ينتمي ملف السيرة إلى مستخدم واحد بالضبط، وتتحقق
  نقاط التحليل والتنزيل من الملكية بدل الوثوق بالمعرّف.
- **تسجيل الدخول محدود المعدل** بعدّاد محفوظ، فيُرجع 429 وقفلاً بعد محاولات متكرّرة فاشلة.
- **تغييرات المدير مُدقَّقة**: تغييرات المستخدمين والخطط ومفاتيح المزوّدات وإعدادات الصور وتشغيلات
  التقييم كلها تُسجَّل في `audit_logs`.
- **يرفض التطبيق كشط ما يمنعه.** لا تُستخدم إلا مصادر تنشر واجهة برمجية أو تغذية RSS أو تسمح بالكشط في
  `robots.txt`.
- **مشغّل تقييم الذكاء الاصطناعي للمدير** (`backend/eval/cases.json`، ٨ حالات إنجليزية وعربية) يقيس
  توافق الأحكام، واستدعاء المهارات، واستدعاء أداة التحقق على بيانات مزيّفة، والتكلفة، ليُحكَم على
  تغيير النموذج أو الموجّه بدل افتراضه.

## ١٢. مرجع الواجهات البرمجية

١١٦ مساراً تحت `/api`، مجمّعة حسب المجال:

| البادئة | المجال |
|---|---|
| `/api/auth`، `/api/oauth`، `/api/onboarding`، `/api/me` | المصادقة، وGoogle OAuth، والملف الشخصي، والصورة |
| `/api/cv`، `/api/files` | خزانة السيرة، والنسخ، والاستعادة، وتنزيل الملفات المشفّرة |
| `/api/jobs`، `/api/meta`، `/api/searches` | الفهرس، والمرشّحات، والإضافة اليدوية، والتقييم بالذكاء الاصطناعي، والراتب، والبحثات المحفوظة |
| `/api/tailor`، `/api/tailored` | التعديل، وعلامات التحقق، والموافقة، والتصدير |
| `/api/applications`، `/api/apply` | لوحة المتابعة، وملف التقديم والتشغيلات والمعاينة |
| `/api/reminders`، `/api/notifications`، `/api/dashboard` | التذكيرات، والإشعارات، والتحليلات |
| `/api/gmail`، `/api/whatsapp` | مسودات Gmail وفحص صندوق الوارد، وواتساب ورموز التحقق والتذكيرات |
| `/api/billing`، `/api/stripe` | الخطط، والدفع، ونداءات Moyasar وStripe |
| `/api/coach` | منح المدرّب، وخطوط المرشحين، والتعليقات |
| `/api/admin` | الإحصاءات، والمستخدمون، والخطط، وصحة المصادر، والتكاملات، ومزوّدو الذكاء الاصطناعي، والنماذج، وإعدادات الصور، والتدقيق، والتقييم، والرؤى |
| `/api/privacy` | سجل الموافقات، والتصدير JSON، وحذف الحساب |

أعد توليد القائمة الكاملة بـ `scripts/list_routes.py` بدلاً من الاعتماد على هذا الجدول.

## ١٣. هيكل المستودع

```
backend/     تطبيق FastAPI: core.py (المصادقة، الخطط، التخزين، البريد)، وموجّهات r_*.py،
             وai.py، وsources.py، وapply.py (محرّك المتصفح)، وr_apply.py (واجهته)،
             وscripts/ (سكربتات التشغيل والتحقق)، وtests/، وeval/cases.json
frontend/    تطبيق React بـ CRA + craco، ومكوّنات shadcn/ui، والتعريب في src/lib
memory/      وثيقة متطلبات المنتج والمخطط التقني
plan/        خطة المنتج
```

## ١٤. ملاحظات على البدائل المحلية

`backend/emergentintegrations/` بديل محلي لحزمة Emergent الخاصة `emergentintegrations` غير المنشورة على
PyPI. يعيد تنفيذ المساحة الصغيرة التي يستخدمها `ai.py` ويوجّه الطلبات إلى أي نقطة متوافقة مع OpenAI.
احذف المجلد إذا ثبّتت الحزمة الحقيقية.

و`backend/requirements.local.txt` يذكر ما يلزم للإقلاع فقط. أما `requirements.txt` المثبّت فهو لقطة
كاملة لـ `site-packages` في الصورة المستضافة، ويشمل حزماً غير مباشرة وأدوات تطوير، ولا يمكن تثبيته دون
اتصال.

ولا تشحن `frontend/public/index.html` أي تحليلات افتراضياً. تكاملEmergent للمعاينة المستضافة
(PostHog مع **تسجيل الجلسات**) اختياري، لأن إعادة تشغيل الجلسة في هذا التطبيق ستمرّ على السير الذاتية
وأرقام الرواتب وبيانات الاتصال. لإعادة تفعيله:
`$env:REACT_APP_EMERGENT_ANALYTICS="1"; npm run build`. ولا يحتوي البناء الافتراضي أي إشارة إلى
`ap.emergent.sh`.

---
*Last reviewed against the codebase on 2026-09-29: 93 tests passing, 116 API routes, 258 city keys,
50 ATS board tokens, 485 translation pairs.*
