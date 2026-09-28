# JobPilot

A bilingual (Arabic RTL / English) "ERP for job seekers". It collects jobs from legal sources
for a chosen country, scores each one against the user's real CV, tailors an honest ATS-ready
CV and cover letter, and tracks every application and follow-up.

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

---

## Job sources and Saudi coverage

Sources live in `db.sources` and are managed from **Admin → Source health**.

**Keyless sources** (work with no account): the ATS feeds (Greenhouse, Lever, Ashby, Workable,
SmartRecruiters), plus Remotive and Arbeitnow for remote roles. These need a **board token** — the
employer's account slug, which is the path segment in their careers URL:

| Platform | Where the token is |
|---|---|
| Workable | `apply.workable.com/<board>/j/...` |
| Greenhouse | `job-boards.greenhouse.io/<board>` |
| Lever | `jobs.lever.co/<board>` |
| Ashby | `jobs.ashbyhq.com/<board>` |
| SmartRecruiters | `jobs.smartrecruiters.com/<board>` |

Board tokens are not guessable, so the **Test** button probes them without saving: it reports the
job count and the Saudi share per token so you only add the ones that work. Testing does not modify
the saved list; the field saves when you click away.

**Sources that need a key** (set in `backend/.env`, then appear as `not_connected` until set):

| Source | Variables | Saudi support |
|---|---|---|
| Careerjet | `CAREERJET_AFFID` | yes, strong coverage |
| Jooble | `JOOBLE_API_KEY` | yes |
| Adzuna | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | **no** — Adzuna has no `sa` market |

To get the widest Saudi coverage, add Careerjet and Jooble keys; the ATS feeds cover individual
employers and are limited to boards you list.

Useful scripts in `backend/scripts/`:

| Script | Purpose |
|---|---|
| `check_sources.py` | live status of every source and job counts |
| `find_saudi_boards.py` | test candidate board tokens through the real fetchers |
| `apply_saudi_boards.py` | write the verified board list and run every source |
| `retag_countries.py` | recompute country tags after changing detection |
| `check_saudi_coverage.py` | verify the Saudi feed end to end over the API |

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
