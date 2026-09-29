import os
import re
import json
import time
import uuid
import base64
import hashlib
from datetime import datetime, timedelta, timezone

import httpx
from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
from core import db, iso, uid, NOID, logger, now, parse_dt, decrypt_str, encrypt_str

LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
DEFAULT_MODELS = {
    "scoring": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    "writing": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
}
MODEL_CATALOG = {
    "anthropic": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"],
    "openai": ["gpt-5.4-mini", "gpt-5.4", "gpt-5.5"],
    "gemini": ["gemini-3-flash-preview", "gemini-3.1-pro-preview"],
    # Verified live against integrate.api.nvidia.com. The previously listed
    # meta/llama-3.3-70b-instruct and nvidia/llama-3.1-nemotron-70b-instruct now return
    # 410 Gone / 404 for this key, so selecting them failed with a raw upstream error.
    "nvidia": ["nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3-ultra-550b-a55b"],
}

# Providers an admin can add a key for from Admin > AI. `api` selects the wire format:
#   "openai"    -> POST {base_url}/chat/completions, GET {base_url}/models, Bearer auth
#   "anthropic" -> POST {base_url}/messages,         GET {base_url}/models, x-api-key auth
# "openai" covers every OpenAI-compatible endpoint, so gateways (OpenRouter, Groq, Together,
# Ollama, LM Studio, vLLM) work by pointing base_url at them.
PROVIDERS = {
    "anthropic": {"label": "Anthropic", "api": "anthropic", "env": "ANTHROPIC_API_KEY",
                  "base_url": "https://api.anthropic.com/v1"},
    "openai": {"label": "OpenAI", "api": "openai", "env": "OPENAI_API_KEY",
               "base_url": "https://api.openai.com/v1"},
    "nvidia": {"label": "NVIDIA NIM", "api": "openai", "env": "NVIDIA_API_KEY",
               "base_url": "https://integrate.api.nvidia.com/v1"},
    "gemini": {"label": "Google Gemini", "api": "openai", "env": "GEMINI_API_KEY",
               "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"},
    "custom": {"label": "Custom / OpenAI-compatible", "api": "openai", "env": "AI_CUSTOM_API_KEY",
               "base_url": "", "needs_base_url": True},
}

# Per-million-token (input, output) USD. Unlisted models fall back to the (1, 5) estimate in
# _log(); add an entry here when a provider's published price is known.
PRICES = {"claude-haiku-4-5-20251001": (1, 5), "claude-sonnet-4-6": (3, 15), "gpt-5.4-mini": (0.4, 1.6),
          "gpt-5.4": (2.5, 10), "gpt-5.5": (5, 20), "gemini-3-flash-preview": (0.5, 3), "gemini-3.1-pro-preview": (2, 12)}
LANG_NAMES = {"en": "English", "ar": "Arabic (Modern Standard, formal)"}

CV_SCHEMA = """{"name":"","headline":"","contact":{"email":"","phone":"","location":"","links":[]},"summary":"",
"experience":[{"company":"","title":"","location":"","start":"YYYY-MM","end":"YYYY-MM|Present","bullets":[""]}],
"education":[{"institution":"","degree":"","field":"","start":"","end":""}],"skills":[""],
"projects":[{"name":"","description":""}],"languages":[{"name":"","level":""}],"certifications":[{"name":"","issuer":"","year":""}]}"""

PROMPTS = {
    "parse_cv": {"version": "parse_cv@1.0", "tier": "scoring",
                 "system": "You are a precise CV parser. You convert raw CV text into strict JSON. Never infer, guess or invent anything. If a field is absent, leave it empty. Keep the original language and wording of the CV. Output ONLY JSON.",
                 "user": "Schema:\n" + CV_SCHEMA + "\n\nCV text:\n<<PAYLOAD>>"},
    "normalize_job": {"version": "normalize_job@1.0", "tier": "scoring",
                      "system": "You normalize job postings into strict JSON. Never invent facts that are not in the posting. Output ONLY JSON.",
                      "user": 'Schema: {"title":"","company":"","location":"","city":"","country_code":"ISO-2 or empty","remote":"remote|onsite|hybrid","seniority":"junior|mid|senior|lead|manager|executive|","salary_min":null,"salary_max":null,"currency":"","description":"full cleaned description","requirements":[""],"deadline":"YYYY-MM-DD or null","apply_email":""}\n\nPosting:\n<<PAYLOAD>>'},
    "review": {"version": "review@1.2", "tier": "scoring",
               "system": "You are a senior GCC recruiter. You assess how well a candidate's master CV fits a job. Reason in English internally regardless of the output language, then write the free-text fields in the requested language. Only use facts present in the CV and the job. Consider GCC specifics: Saudization/Nitaqat or nationality-restricted roles, mandatory professional licences (SCFHS, SCE, SOCPA etc.), visa sponsorship, Arabic requirements, location/relocation, salary vs market. Output ONLY JSON.",
               "user": 'Write all free-text values in <<LANG>>. Keep skill names as they appear.\nSchema: {"score":0-100,"hard_blockers":["only true dealbreakers: nationality restriction the candidate does not meet, missing mandatory licence/degree, completely different profession"],"summary":"one sentence","matched_skills":[""],"missing_skills":[""],"keyword_gaps":[""],"red_flags":["concerns that are NOT dealbreakers"],"notes":{"salary":"","visa":"","location":""},"reasons":["3-5 concise reasons"]}\nScoring rubric (sum): core skills/requirements coverage 0-45; relevant years & seniority 0-25; same domain/industry 0-15; language, location, other 0-15.\nCalibration: same profession with transferable skills but a seniority/years gap or 1-2 missing must-haves is a PARTIAL fit and should score 45-70 (not below 45). Reserve scores under 45 for different professions or when most core requirements are absent. Do not put seniority gaps or missing non-mandatory tools in hard_blockers.\n\nInput:\n<<PAYLOAD>>'},
    "salary_benchmark": {"version": "salary_benchmark@1.0", "tier": "scoring",
                         "system": "You are a compensation analyst for the GCC and global markets. Estimate typical gross monthly salary ranges for a role in a city based on your market knowledge. Be conservative and honest about uncertainty. Output ONLY JSON.",
                         "user": 'Write notes in <<LANG>>.\nSchema: {"currency":"ISO code of local currency","period":"month","p25":0,"median":0,"p75":0,"confidence":"low|medium|high","notes":"one short sentence on assumptions (allowances, seniority)"}\n\nRole:\n<<PAYLOAD>>'},
    "tailor": {"version": "tailor@1.2", "tier": "writing",
               "system": "You are an expert ATS CV writer. HARD RULE: never invent experience, employers, job titles, dates, skills, numbers, degrees, certifications or achievements. You may ONLY reorder, rephrase, condense, omit or emphasize content that exists in the master CV. Keep company names, dates and all numbers exactly as in the master CV (Western digits). If a job requirement is not supported by the master CV, do NOT add it. Output ONLY JSON.",
               "user": 'Output language: <<LANG>>. Translate descriptive text if needed but keep proper names (companies, institutions, product names) exactly as in the master CV.\nReturn {"cv": <same schema as master CV>, "cover_letter": "plain text, 180-280 words, addressed to the hiring team, only real facts", "changes": ["short notes on what was reordered/emphasized"]}\nPrioritise bullets and skills most relevant to the job, mirror the job\'s keywords ONLY where the master CV genuinely supports them.\n\nInput:\n<<PAYLOAD>>'},
    "interview_prep": {"version": "interview_prep@1.0", "tier": "writing",
                       "system": "You are an interview coach for GCC employers. Build a practical interview-prep pack. Draw answers ONLY from facts in the candidate's master CV; never invent experience or numbers. Output ONLY JSON.",
                       "user": 'Write in <<LANG>>.\nSchema: {"questions":[{"q":"likely interview question","why":"why they will ask","answer_outline":"STAR-style outline using only real CV facts"}],"questions_to_ask":["smart questions for the interviewer"],"research":["what to research about the company/role"],"gaps_to_prepare":["how to honestly address missing requirements"]}\nGive 8 questions (mix of technical, behavioural, motivation, GCC context such as relocation/Arabic/notice period).\n\nInput:\n<<PAYLOAD>>'},
    "validate": {"version": "validate@1.1", "tier": "scoring",
                 "system": "You are a strict fact-checker. Compare a TAILORED CV and cover letter against the MASTER CV (the only source of truth). Flag every employer, job title, date, skill, number, degree, certification or achievement claim in the tailored version that is not supported by the master CV. Rephrasing and translation of supported facts is fine. Output ONLY JSON.",
                 "user": 'Schema: {"flags":[{"path":"dot path in tailored cv e.g. experience.0.bullets.2 or skills.4 or cover_letter","type":"employer|title|date|skill|number|degree|certification|claim","value":"offending text","reason":"why unsupported"}]}\nReturn {"flags":[]} if everything is supported.\n\nInput:\n<<PAYLOAD>>'},
}


async def get_models():
    s = await db.settings.find_one({"key": "ai_models"}, NOID)
    return {**DEFAULT_MODELS, **((s or {}).get("value") or {})}


# ---------- provider credentials (admin-managed, encrypted at rest) ----------
# Keys live in db.settings under "ai_providers" as Fernet ciphertext. They are never returned
# over the API -- only a masked hint. Resolution order is stored key first, then the
# environment variable, so an operator can still configure a provider through .env alone.
CREDS_KEY = "ai_providers"


def mask_key(k):
    if not k:
        return ""
    k = str(k)
    if len(k) <= 8:
        return "•" * len(k)
    return f"{k[:4]}…{k[-4:]}"


async def get_provider_creds():
    return (await db.settings.find_one({"key": CREDS_KEY}, NOID) or {}).get("value") or {}


async def provider_key(provider):
    spec = PROVIDERS.get(provider)
    if not spec:
        return ""
    entry = (await get_provider_creds()).get(provider) or {}
    if entry.get("api_key_enc"):
        try:
            return decrypt_str(entry["api_key_enc"])
        except Exception as e:
            logger.error(f"Could not decrypt stored key for {provider}: {e}")
    return (os.environ.get(spec["env"]) or "").strip()


async def provider_base_url(provider):
    entry = (await get_provider_creds()).get(provider) or {}
    return (entry.get("base_url") or "").strip().rstrip("/") or PROVIDERS[provider]["base_url"]


async def provider_configured(provider):
    """Whether a tier may select this provider.

    True when an admin stored a key (and a base URL, where one is required), or when the
    provider is reachable through the Emergent universal gateway, which needs no per-provider
    key of its own. The custom endpoint is gateway-invisible, so it needs a real key.
    """
    spec = PROVIDERS.get(provider)
    if not spec:
        return False
    if spec.get("needs_base_url"):
        return bool(await provider_key(provider)) and bool(await provider_base_url(provider))
    if await provider_key(provider):
        return True
    return bool(LLM_KEY.strip()) and provider in MODEL_CATALOG


# ---------- live model discovery ----------
MODEL_CACHE_TTL = 3600  # seconds; provider model lists change slowly
_model_cache = {}


def _auth_headers(spec, key):
    if spec["api"] == "anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}
    return {"Authorization": f"Bearer {key}"}


# NVIDIA and several gateways publish non-chat models (embeddings, guards, rerankers) in the
# same list. Offering those in a "pick a chat model" dropdown only produces runtime failures.
_NON_CHAT = re.compile(r"embed|guard|rerank|retriev|nemo-guard|safety|nv-embed|pii|topic-control|codegemma|paraphrase", re.I)


def _usable_models(ids):
    return sorted({i for i in ids if isinstance(i, str) and i and not _NON_CHAT.search(i)})


async def fetch_provider_models(provider, refresh=False):
    """Model ids for a provider, fetched live from its /models endpoint.

    Cached in-process and in the database. Falls back to the shipped catalog when the provider
    has no key or the endpoint is unreachable, so the admin UI still renders offline.
    """
    spec = PROVIDERS.get(provider)
    if not spec:
        return []
    base = await provider_base_url(provider)
    key = await provider_key(provider)
    fallback = MODEL_CATALOG.get(provider, [])

    if not key or not base:
        return {"models": fallback, "source": "catalog", "error": None}
    if not refresh:
        hit = _model_cache.get(provider)
        if hit and hit["expires"] > time.time():
            return {**hit["payload"], "source": "cache"}
        cached = await db.settings.find_one({"key": f"ai_models_{provider}"}, NOID)
        if cached and (parse_dt((cached.get("value") or {}).get("fetched_at")) or datetime.min.replace(tzinfo=timezone.utc)) > now() - timedelta(seconds=MODEL_CACHE_TTL):
            payload = {"models": _usable_models((cached.get("value") or {}).get("models") or []), "source": "cache", "error": None}
            if payload["models"]:
                _model_cache[provider] = {"expires": time.time() + MODEL_CACHE_TTL, "payload": payload}
                return payload

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{base}/models", headers=_auth_headers(spec, key))
        if r.status_code >= 400:
            return {"models": fallback, "source": "catalog", "error": _friendly_http_error(r.status_code, r.text)}
        data = r.json().get("data") or []
        models = _usable_models([m.get("id") for m in data if isinstance(m, dict)])
    except Exception as e:
        return {"models": fallback, "source": "catalog", "error": f"{type(e).__name__}: {str(e)[:180]}"}

    if not models:
        return {"models": fallback, "source": "catalog", "error": "Provider returned no usable models"}
    await db.settings.update_one({"key": f"ai_models_{provider}"},
                                 {"$set": {"value": {"models": models, "fetched_at": iso()}}}, upsert=True)
    payload = {"models": models, "source": "live", "error": None}
    _model_cache[provider] = {"expires": time.time() + MODEL_CACHE_TTL, "payload": payload}
    return payload


async def known_models(provider):
    """Every model id the app will accept for a provider: live list plus shipped catalog."""
    live = (await fetch_provider_models(provider)).get("models") or []
    return set(live) | set(MODEL_CATALOG.get(provider, []))


def _extract_json(text):
    t = re.sub(r"```(?:json)?", "", text).strip()
    return json.loads(t[t.find("{"): t.rfind("}") + 1])


def _friendly_http_error(status, body):
    """Turn an upstream 401/403/404/410 into a message an admin can act on."""
    detail = body[:200] if body else ""
    if status in (401, 403):
        return f"{status}: provider rejected the API key. Check the key for this provider."
    if status == 404:
        return "404: endpoint or model not found. The model may be retired, or the base URL may be wrong."
    if status == 410:
        return "410: the provider reports this model as retired. Pick a different one."
    if status == 429:
        return "429: rate limited or out of quota. Try again shortly."
    return f"{status}: {detail}"


async def _call_openai(base, key, model, system, prompt):
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                         json={"model": model, "temperature": 0.2, "max_tokens": 6000,
                               "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
    if r.status_code >= 400:
        raise RuntimeError(_friendly_http_error(r.status_code, r.text))
    return r.json()["choices"][0]["message"]["content"]


async def _call_anthropic(base, key, model, system, prompt):
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{base}/messages",
                         headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                         json={"model": model, "max_tokens": 6000, "temperature": 0.2,
                               "system": system, "messages": [{"role": "user", "content": prompt}]})
    if r.status_code >= 400:
        raise RuntimeError(_friendly_http_error(r.status_code, r.text))
    return "".join(b.get("text", "") for b in r.json().get("content") or [] if b.get("type") == "text")


async def _call(provider, model, system, prompt):
    """Route a prompt to the provider's own API when an admin has configured a key for it.

    Falls back to the Emergent universal gateway (LlmChat) for a provider with no stored key,
    which is how the app ran before keys were admin-manageable.
    """
    spec = PROVIDERS.get(provider)
    if spec:
        key = await provider_key(provider)
        base = await provider_base_url(provider)
        if key and base:
            return await (_call_anthropic if spec["api"] == "anthropic" else _call_openai)(base, key, model, system, prompt)
    chat = LlmChat(api_key=LLM_KEY, session_id=uuid.uuid4().hex, system_message=system).with_model(provider, model)
    out = []
    async for ev in chat.stream_message(UserMessage(text=prompt)):
        if isinstance(ev, TextDelta):
            out.append(ev.content)
        elif isinstance(ev, StreamDone):
            break
    return "".join(out)


async def _log(user_id, feature, meta, tin, tout, cached):
    pin, pout = PRICES.get(meta["model"], (1, 5))
    cost = 0 if cached else round((tin * pin + tout * pout) / 1_000_000, 6)
    await db.ai_logs.insert_one({"log_id": uid("ai_"), "user_id": user_id, "feature": feature, **meta, "input_tokens": tin,
                                 "output_tokens": tout, "cost_usd": cost, "cached": cached, "created_at": iso()})


async def llm_json(task, payload, user_id, lang="en"):
    p = PROMPTS[task]
    cfg = (await get_models())[p["tier"]]
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    prompt = p["user"].replace("<<LANG>>", LANG_NAMES.get(lang, "English")).replace("<<PAYLOAD>>", body)
    meta = {"prompt_version": p["version"], "provider": cfg["provider"], "model": cfg["model"]}
    key = hashlib.sha256(f'{p["version"]}|{cfg["provider"]}|{cfg["model"]}|{prompt}'.encode()).hexdigest()
    hit = await db.ai_cache.find_one({"key": key}, NOID)
    if hit:
        await _log(user_id, task, meta, 0, 0, True)
        return hit["result"], meta
    err, text = None, ""
    for attempt in range(2):
        text = await _call(cfg["provider"], cfg["model"], p["system"], prompt if attempt == 0 else prompt + "\n\nReturn ONLY valid JSON, no prose.")
        try:
            result = _extract_json(text)
            break
        except Exception as e:
            err = e
    else:
        raise RuntimeError(f"AI returned invalid JSON: {err}")
    await db.ai_cache.insert_one({"key": key, "task": task, "result": result, "created_at": iso()})
    await _log(user_id, task, meta, len(p["system"] + prompt) // 4, len(text) // 4, False)
    return result, meta


# ---------- quick match (deterministic, free) ----------
def finalize_review(res):
    res["score"] = max(0, min(100, int(res.get("score") or 0)))
    blockers = [b for b in (res.get("hard_blockers") or []) if b]
    res["hard_blockers"] = blockers
    res["verdict"] = "skip" if blockers else "apply" if res["score"] >= 75 else "maybe" if res["score"] >= 45 else "skip"
    res["red_flags"] = blockers + [f for f in (res.get("red_flags") or []) if f not in blockers]
    return res


def quick_match(cv, job):
    skills = [s for s in (cv or {}).get("skills", []) if isinstance(s, str) and len(s) > 1]
    if not skills:
        return None
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    hits = sum(1 for s in skills if s.lower() in text)
    return min(100, round(100 * hits / max(5, min(len(skills), 15))))


# ---------- validation ----------
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_PRESENT = ("present", "current", "now", "حتى الآن", "الآن", "حاليا", "حاليًا")


def _nd(s):
    return str(s or "").translate(_AR_DIGITS)


def deterministic_flags(master, tailored, lang):
    mtext = _nd(json.dumps(master, ensure_ascii=False)).lower()
    flags = []

    def add(path, typ, value, reason):
        flags.append({"path": path, "type": typ, "value": str(value), "reason": reason, "source": "rule"})

    for i, e in enumerate(tailored.get("experience") or []):
        if not e:
            continue
        comp = str(e.get("company") or "").strip()
        if comp and comp.lower() not in mtext:
            add(f"experience.{i}.company", "employer", comp, "Employer not found in master CV")
        if lang == "en":
            t = str(e.get("title") or "").strip()
            if t and t.lower() not in mtext:
                add(f"experience.{i}.title", "title", t, "Job title not found in master CV")
        for f in ("start", "end"):
            v = _nd(e.get(f)).strip()
            if v and re.search(r"\d", v) and v.lower() not in mtext and not any(p in v.lower() for p in _PRESENT):
                add(f"experience.{i}.{f}", "date", v, "Date not found in master CV")
        for j, b in enumerate(e.get("bullets") or []):
            for n in re.findall(r"\d+(?:[.,]\d+)?", _nd(b)):
                if n not in mtext:
                    add(f"experience.{i}.bullets.{j}", "number", n, "Number not found in master CV")
    if lang == "en":
        for i, s in enumerate(tailored.get("skills") or []):
            if s and str(s).lower() not in mtext:
                add(f"skills.{i}", "skill", s, "Skill not found in master CV")
        for i, ed in enumerate(tailored.get("education") or []):
            if ed and ed.get("institution") and str(ed["institution"]).lower() not in mtext:
                add(f"education.{i}.institution", "degree", ed["institution"], "Institution not found in master CV")
    return flags


async def validate_tailored(master, tailored_cv, cover, lang, user_id):
    flags = deterministic_flags(master, tailored_cv, lang)
    meta = None
    try:
        res, meta = await llm_json("validate", {"master_cv": master, "tailored_cv": tailored_cv, "cover_letter": cover}, user_id, lang)
        for f in res.get("flags") or []:
            if f.get("value"):
                flags.append({**{k: f.get(k, "") for k in ("path", "type", "value", "reason")}, "source": "ai"})
    except Exception as e:
        flags.append({"path": "", "type": "claim", "value": "AI validation unavailable", "reason": str(e)[:200], "source": "system"})
    seen, out = set(), []
    for f in flags:
        k = (f["path"], f["value"].lower())
        if k not in seen:
            seen.add(k)
            out.append({**f, "flag_id": uid("flg_"), "status": "open"})
    return out, meta


def remove_path(cv, path):
    parts = [p for p in path.split(".") if p]
    obj = cv
    try:
        for p in parts[:-1]:
            obj = obj[int(p)] if isinstance(obj, list) else obj.get(p)
        last = parts[-1]
        if isinstance(obj, list):
            obj[int(last)] = None
        elif isinstance(obj, dict):
            obj[last] = ""
    except (ValueError, IndexError, KeyError, AttributeError, TypeError):
        pass
    return cv


def compact(v):
    if isinstance(v, list):
        return [compact(x) for x in v if x not in (None, "")]
    if isinstance(v, dict):
        return {k: compact(x) for k, x in v.items()}
    return v


# ---------- image generation ----------
# The provider and model are chosen in Admin > AI > Image, not hardcoded, and the key is taken from
# the same admin-managed credential store as the chat tiers. This used to call the Emergent gateway
# through `LlmChat.send_message_multimodal_response`, which the local shim cannot do, so image
# generation always failed with "Image generation needs the Emergent LLM gateway".
IMAGE_SETTINGS_KEY = "ai_image"
DEFAULT_IMAGE = {"provider": "gemini", "model": "gemini-3.1-flash-image-preview"}

# Providers whose image API is the OpenAI-style POST {base}/images/generations -> data[].b64_json.
# Everything else is called through Gemini's native :generateContent with responseModalities IMAGE.
_OPENAI_IMAGE_APIS = {"openai", "custom"}


async def image_settings():
    s = await db.settings.find_one({"key": IMAGE_SETTINGS_KEY}, NOID)
    return {**DEFAULT_IMAGE, **((s or {}).get("value") or {})}


def _mime_from_b64(b64):
    """Sniff the subtype from the decoded magic bytes; the APIs do not always label it."""
    try:
        head = base64.b64decode(b64[:32], validate=False)[:12]
    except Exception:
        return "image/png"
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


async def _image_via_openai(base, key, model, prompt):
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{base}/images/generations",
                         headers={"Authorization": f"Bearer {key}"},
                         json={"model": model, "prompt": prompt, "n": 1})
    if r.status_code >= 400:
        raise RuntimeError(f"{model} returned {r.status_code}: {r.text[:300]}")
    data = (r.json() or {}).get("data") or []
    if not data:
        raise RuntimeError(f"{model} returned no image")
    d = data[0]
    if d.get("b64_json"):
        return base64.b64decode(d["b64_json"]), _mime_from_b64(d["b64_json"])
    if d.get("url"):
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
            img = await c.get(d["url"])
        img.raise_for_status()
        return img.content, img.headers.get("content-type", "image/png")
    raise RuntimeError(f"{model} returned neither b64_json nor url")


async def _image_via_gemini(key, model, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                         json={"contents": [{"parts": [{"text": prompt}]}],
                               "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}})
    if r.status_code >= 400:
        raise RuntimeError(f"{model} returned {r.status_code}: {r.text[:300]}")
    parts = ((r.json() or {}).get("candidates") or [{}])[0].get("content", {}).get("parts") or []
    for p in parts:
        inline = p.get("inlineData") or p.get("inline_data")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"]), inline.get("mimeType") or inline.get("mime_type") or "image/png"
    raise RuntimeError(f"{model} returned no image data")


async def generate_image(prompt):
    cfg = await image_settings()
    provider, model = cfg["provider"], cfg["model"]
    if provider not in PROVIDERS:
        raise RuntimeError(f"Unknown image provider '{provider}'. Set it under Admin > AI > Image.")
    key = await provider_key(provider)
    if not key:
        raise RuntimeError(
            f"No API key for image provider '{provider}'. Add one under Admin > AI > Providers, or set {PROVIDERS[provider]['env']}."
        )
    if provider in _OPENAI_IMAGE_APIS:
        base = await provider_base_url(provider)
        return await _image_via_openai(base, key, model, prompt)
    if provider == "gemini":
        return await _image_via_gemini(key, model, prompt)
    raise RuntimeError(
        f"Provider '{provider}' has no image API. Use gemini, openai, or a custom OpenAI-compatible endpoint."
    )
