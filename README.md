# JobPilot

A bilingual (Arabic RTL / English) "ERP for job seekers". It collects jobs from legal sources
across 20 markets for a chosen country, scores each one against the user's real CV, tailors an
honest ATS-ready CV and cover letter, fills and submits applications on the employer's own form,
and tracks every application and follow-up.

Backend is **FastAPI** (not Flask) + MongoDB; frontend is **React** (CRA + craco) + shadcn/ui + Tailwind.

See `plan/plan.md` for the product plan and `memory/PRD.md` for what is implemented.

---

## Running it locally

The project was originally built to run on the Emergent cloud platform. Everything below sets
up an equivalent stack on a plain machine — no Docker required.

### 1. Prerequisites

- Python **3.12** (3.14+ is not supported by the pinned dependencies)
- Node.js 18+ (developed on Node 24)
- MongoDB

```powershell
winget install --id Python.Python.3.12
winget install --id MongoDB.Server      # installs the MongoDB service, which starts automatically
```

Auto-apply drives a real browser, so it also needs Chromium. This is a separate ~150 MB download
and is only required for that feature; the rest of the app runs without it:

```powershell
cd backend
.\.venv\Scripts\python.exe -m playwright install chromium
```

### 2. Backend

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
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | seeded super admin — must be a normal-looking address (`.local` is rejected by `EmailStr`) |
| `TEST_USER_EMAIL` / `TEST_USER_PASSWORD` | seeded demo user, which also gets a seeded master CV |
| `COOKIE_SECURE` | `0` for local HTTP, `1` behind HTTPS (see below) |

Two settings that matter specifically for local dev:

- **`COOKIE_SECURE=0`** — auth cookies are cross-site (`:3000` → `:8000`), so in production they
  are `Secure; SameSite=None`. Browsers drop such a cookie over plain HTTP, which makes every
  authenticated call 401. Local HTTP therefore needs `SameSite=Lax`. Set it back to `1` for any
  real deployment.
- **`LOCAL_STORAGE=1`** — stores uploaded CVs and exports encrypted on local disk instead of
  calling the Emergent object store, which is unreachable offline.

On first boot the app creates indexes, seeds the three plans, the job sources, both accounts,
and a master CV for the demo user, then schedules the reminder / source-fetch / ghost-check jobs.

### 3. Frontend

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

### 4. Sign in

| Role | Credentials |
|---|---|
| Super admin | the `ADMIN_EMAIL` / `ADMIN_PASSWORD` you set |
| Demo user | the `TEST_USER_EMAIL` / `TEST_USER_PASSWORD` you set |

---

## AI configuration

AI features (CV parsing, job review, CV tailoring, interview prep, validation) need a provider.
There are two ways to supply one, and they are equivalent from the app's point of view:

1. **From the admin panel** — `Admin → AI → AI providers`. Add a key for Anthropic, OpenAI,
   NVIDIA NIM, Google Gemini, or a custom OpenAI-compatible endpoint. Keys are encrypted with
   `ENCRYPTION_KEY` before being stored and are never sent back to the browser — the panel only
   shows a mask such as `sk-l…abcd`. A provider that is in use by a tier cannot be removed.
2. **From `.env`** — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `NVIDIA_API_KEY`, `GEMINI_API_KEY`,
   or `AI_CUSTOM_API_KEY`. These are used as a fallback and appear as `configured · env`.

**Model lists are discovered automatically.** Once a provider has a key, the panel calls that
provider's `GET /models` endpoint and populates the scoring and writing dropdowns from the
response, so newly released models can be selected without a code change. The list is cached for
an hour; `Load models` forces a refresh. Embedding, guard and reranker models are filtered out
since they cannot serve chat prompts. If a provider is unreachable the panel falls back to the
short catalog in `backend/ai.py` and shows why.

Providers are called directly. `openai`, `nvidia`, `gemini` and `custom` speak the
OpenAI chat-completions format; `anthropic` uses its native Messages API. Any OpenAI-compatible
gateway (OpenRouter, Groq, Together, Ollama, LM Studio, vLLM) works by adding a `Custom`
provider and pointing it at that gateway's base URL.

With no key at all, a provider that is in the shipped catalog still routes through the Emergent
universal gateway when `EMERGENT_LLM_KEY` is set.

### Admin-managed secrets

Every integration key — the AI providers above, plus Careerjet, Jooble, Adzuna, Gmail/Google OAuth,
Moyasar, Stripe and WhatsApp — can be set from **Admin → Integrations** instead of `.env`. Values are
encrypted with `ENCRYPTION_KEY` before storage and are never returned to the browser; the API
reports only a `configured` boolean and the panel shows a masked value.

Resolution order is **stored secret, then environment variable, then empty**, so a key entered in
the dashboard takes effect immediately without a redeploy. Clearing a stored value falls back to the
environment. Keyless sources are shown as *No key needed* rather than *API key required*.

### Image generation

`Admin → AI → Image` configures the provider used to generate job imagery. It works with either
Google Gemini (native `generativelanguage.googleapis.com` image generation) or any
OpenAI-compatible `/images/generations` endpoint, and handles both base64 and URL responses. The
selection is stored under the `ai_image` settings key and is audited on every change.

### When AI is unavailable

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

The plan limit meters the AI parse, not the upload, so a user can never be locked out of their own
CV vault.

---

## Auto-apply

Auto-apply fills and submits the **employer's real application form** in a headless browser
(Playwright/Chromium), using the details in **Settings → Apply profile** plus the user's master CV.
There is no separate "apply API": the browser opens the ATS page the job came from and drives the
form on it.

Supported platforms — anything else is refused rather than driven:

| Platform | Forms are driven at |
|---|---|
| Greenhouse | the job page's inline form |
| Lever | `jobs.lever.co/<board>/<id>/apply` |
| Ashby | the job's `applyUrl` |
| Workable | `apply.workable.com/<board>/j/<id>` |
| SmartRecruiters | the job page's apply modal |

Each job stores `apply_url`, `ats` and `ats_board` at ingest, so the form is addressed directly
rather than re-derived. Jobs that predate this are backfilled on the next source refresh.

### What it will and will not do

Auto-apply writes to a third party on the user's behalf, so it is deliberately conservative:

- **It never bypasses bot protection.** reCAPTCHA, hCaptcha, Turnstile, Cloudflare, DataDome and
  PerimeterX all stop the run as `needs_human`. It does not attempt to solve or evade them.
- **It never submits a half-filled form.** Any required field it cannot confidently populate also
  returns `needs_human`, naming the field, rather than sending blanks.
- **It is never silent.** Every run records a status, a reason, the final URL and a screenshot of
  the form, and the tracker only advances on a verified submission. A blocked or failed run leaves
  the application exactly where it was.
- **It is always user-initiated.** Runs only start when the user presses the button. `POST
  /api/apply/preview` fills the form and screenshots it *without* submitting, so the user can check
  the data first.

Outcomes are `submitted`, `filled` (preview only), `needs_human`, `unsupported`, `failed` and
`unknown` (submitted but the confirmation could not be verified). Runs are capped per month per
user to keep the shared egress IP from hammering a handful of ATS platforms.

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

---

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests test_sources_unit.py -q
```

The suite talks to a **running** API over HTTP, so start the backend first. `backend/tests/conftest.py`
reads the target URL and the seeded credentials from `backend/.env`, so no shell setup is needed;
export `REACT_APP_BACKEND_URL`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `TEST_USER_EMAIL` and
`TEST_USER_PASSWORD` to point it somewhere else.

`RUN_AI_TESTS=1` additionally enables the slow AI tests. The AI-heavy endpoints take 40–90s, so
they are off by default.

`backend/pytest.ini` pins `addopts = -n 2 --dist loadscope`, so the suite runs two workers in
parallel by default. **Do not edit that line**; pass `-n 0` to force serial execution, or
`-o addopts=` to drop it entirely.

`test_apply_engine.py` is deliberately *not* part of this suite. It needs a live Chromium and a
local HTTP server, and it must never submit to a real employer, so it runs standalone:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\test_apply_engine.py
```

---

## Job sources and market coverage

Sources live in `db.sources` and are managed from **Admin → Source health**.

**Keyless sources** (work with no account). The ATS feeds need a **board token** — the employer's
account slug, which is the path segment in their careers URL:

| Platform | Where the token is |
|---|---|
| Workable | `apply.workable.com/<board>/j/...` |
| Greenhouse | `job-boards.greenhouse.io/<board>` |
| Lever | `jobs.lever.co/<board>` |
| Ashby | `jobs.ashbyhq.com/<board>` |
| SmartRecruiters | `jobs.smartrecruiters.com/<board>` |

The remaining keyless sources need no token and cover whole markets:

| Source | Scope |
|---|---|
| Remotive, Arbeitnow | remote roles, worldwide |
| Jobb.ae | Saudi/Gulf, via RSS |
| JobHunt | UAE/Gulf aggregator |

Board tokens are not guessable, so the **Test** button probes them without saving: it reports the
job count and the Saudi share per token so you only add the ones that work. Testing does not modify
the saved list; the field saves when you click away.

**Sources that need a key** (set in `backend/.env`, then appear as `not_connected` until set):

| Source | Variables | Saudi support |
|---|---|---|
| Careerjet | `CAREERJET_AFFID` | yes |
| Jooble | `JOOBLE_API_KEY` | yes |
| Adzuna | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | **no** — Adzuna has no `sa` market |

To widen Saudi coverage, add Careerjet and Jooble keys; the ATS feeds cover individual employers and
are limited to the boards you list.

### Cities and countries

City matching is data-driven: `backend/sources.py` holds a canonical key per city with English and
Arabic aliases, and both the country filter and the city picker read from it. That is currently
**76 Saudi cities plus 182 cities across 19 other markets (258 keys total)**, with Mecca/Makkah and
Medina/Madinah resolved to one key each.

Matching is word-boundary based and longest-alias-first, so `Duba` is never swallowed by `Dubai` and
`Al Ula` is never read as `Ula`. One deliberate trade-off: Arabic `صور` is both Sur (Oman) and Sidon
(Lebanon), so Sidon keeps it and Sur is reachable in Latin script only.

`validate_cities.py` enforces all of this, including that no alias maps to two cities and that every
city detects its own market:

```powershell
cd backend
.\.venv\Scripts\python.exe -X utf8 scripts\validate_cities.py
```

The frontend city list is generated from the backend, never hand-edited, so the two cannot drift:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\gen_frontend_cities.py   # prints the block
.\.venv\Scripts\python.exe -X utf8 scripts\patch_frontend_markets.py # splices it into constants.js
```

Useful scripts in `backend/scripts/`:

| Script | Purpose |
|---|---|
| `check_sources.py` | live status of every source and job counts |
| `find_saudi_boards.py` | test candidate board tokens through the real fetchers |
| `apply_saudi_boards.py` | write the verified board list and run every source |
| `retag_countries.py` | recompute country tags after changing detection |
| `check_saudi_coverage.py` | verify the Saudi feed end to end over the API |
| `validate_cities.py` | assert the city/alias data and cross-market detection |
| `check_i18n.py` | assert no duplicate Arabic keys, no missing translations, no unwrapped copy |
| `check_city_filter.py` | check the live `/jobs` city and country filters |
| `gen_frontend_cities.py` | print the generated city list for the frontend |
| `patch_frontend_markets.py` | splice that list into `constants.js` (idempotent) |
| `test_apply_engine.py` | drive the apply engine against mock ATS forms |
| `reset_login_lockout.py` | clear Mongo `login_attempts` after repeated test logins |

---

## Analytics

`frontend/public/index.html` ships no analytics by default. Emergent's hosted-preview integration
(PostHog with **session recording**) is opt-in, because session replay on this app would capture
CVs, salary figures and contact details, and ad blockers turn it into failed requests in the
console.

To re-enable it (for example when previewing on the Emergent platform), build with:

```powershell
$env:REACT_APP_EMERGENT_ANALYTICS="1"; npm run build
```

The default build contains no reference to `ap.emergent.sh` at all.

---

## Repository layout

```
backend/     FastAPI app: core.py (auth, plans, storage, email), r_*.py routers, ai.py, sources.py
            apply.py (auto-apply browser engine), r_apply.py (its API)
frontend/    CRA + craco React app, shadcn/ui components
memory/      PRD and technical blueprint
plan/        Product plan
test_reports/  Verification reports from the hosted-preview runs
```

## Notes on local-only shims

`backend/emergentintegrations/` is a local stand-in for Emergent's private `emergentintegrations`
package, which is not published to PyPI. It re-implements the small surface `ai.py` uses and
routes to any OpenAI-compatible endpoint. Delete the directory if you install the real package.

`backend/requirements.local.txt` lists only what is needed to boot. The pinned
`requirements.txt` is a full snapshot of the hosted image's `site-packages`, including
transitive and dev-only packages, and is not installable offline.
