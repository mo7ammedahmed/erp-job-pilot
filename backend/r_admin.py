import os
import base64
import json
import asyncio
from datetime import timedelta
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Optional
from core import (db, iso, now, NOID, USER_PROJ, get_current_user, require_admin, audit, client_ip, usage_of, period,
                  clear_auth_cookies, get_file, encrypt_str)
import ai as ai_providers
from ai import MODEL_CATALOG, get_models, PROMPTS
from sources import run_all_sources, run_source

router = APIRouter(prefix="/api")

# ---------- Admin ----------


@router.get("/admin/stats")
async def admin_stats(admin=Depends(require_admin)):
    since = iso(now() - timedelta(days=30))
    cost = await db.ai_logs.aggregate([{"$match": {"created_at": {"$gte": since}}}, {"$group": {"_id": None, "c": {"$sum": "$cost_usd"}, "n": {"$sum": 1}}}]).to_list(1)
    plans = await db.users.aggregate([{"$group": {"_id": "$plan", "n": {"$sum": 1}}}]).to_list(10)
    return {"users": await db.users.count_documents({}), "jobs": await db.jobs.count_documents({}),
            "applications": await db.applications.count_documents({}), "ai_cost_30d": round(cost[0]["c"], 4) if cost else 0,
            "ai_calls_30d": cost[0]["n"] if cost else 0, "plans": {p["_id"]: p["n"] for p in plans}}


@router.get("/admin/users")
async def admin_users(q: str = "", admin=Depends(require_admin)):
    f = {"$or": [{"email": {"$regex": q, "$options": "i"}}, {"name": {"$regex": q, "$options": "i"}}]} if q else {}
    users = await db.users.find(f, USER_PROJ).sort("created_at", -1).to_list(200)
    since = iso(now().replace(day=1, hour=0, minute=0, second=0, microsecond=0))
    costs = {c["_id"]: c["c"] for c in await db.ai_logs.aggregate([{"$match": {"created_at": {"$gte": since}}}, {"$group": {"_id": "$user_id", "c": {"$sum": "$cost_usd"}}}]).to_list(1000)}
    for u in users:
        u["usage"] = await usage_of(u["user_id"])
        u["ai_cost_month"] = round(costs.get(u["user_id"], 0), 4)
    return users


class UserPatch(BaseModel):
    plan: Optional[str] = None
    plan_days: Optional[int] = None
    suspended: Optional[bool] = None
    role: Optional[str] = None


@router.patch("/admin/users/{user_id}")
async def admin_patch_user(user_id: str, body: UserPatch, request: Request, admin=Depends(require_admin)):
    upd = body.model_dump(exclude_none=True)
    if "role" in upd and upd["role"] not in ("user", "admin"):
        raise HTTPException(400, "Invalid role")
    if "plan" in upd and upd["plan"] not in ("free", "pro", "premium"):
        raise HTTPException(400, "Invalid plan")
    days = upd.pop("plan_days", None)
    if days and "plan" not in upd:
        raise HTTPException(400, "plan_days requires plan")
    if "plan" in upd:
        upd["plan_expires_at"] = iso(now() + timedelta(days=days)) if days and days > 0 and upd["plan"] != "free" else None
    if user_id == admin["user_id"] and (upd.get("suspended") or upd.get("role") == "user"):
        raise HTTPException(400, "You cannot suspend or demote yourself")
    await db.users.update_one({"user_id": user_id}, {"$set": upd})
    await audit(user_id, "admin_user_update", upd, actor_id=admin["user_id"], ip=client_ip(request))
    return {"ok": True}


@router.get("/admin/plans")
async def admin_plans(admin=Depends(require_admin)):
    return await db.plans.find({}, NOID).sort("order", 1).to_list(10)


class TrialIn(BaseModel):
    plan: str
    days: int


@router.get("/admin/trial")
async def get_trial(admin=Depends(require_admin)):
    return (await db.settings.find_one({"key": "trial"}, NOID) or {}).get("value") or {"plan": "pro", "days": 0}


@router.put("/admin/trial")
async def set_trial(body: TrialIn, admin=Depends(require_admin)):
    if body.plan not in ("pro", "premium") or not 0 <= body.days <= 365:
        raise HTTPException(400, "Invalid trial")
    await db.settings.update_one({"key": "trial"}, {"$set": {"value": body.model_dump()}}, upsert=True)
    await audit(admin["user_id"], "admin_trial_update", body.model_dump())
    return {"ok": True}


class PlanIn(BaseModel):
    name: str
    price_usd: float
    price_sar: float
    limits: dict
    features: dict


@router.put("/admin/plans/{plan_id}")
async def admin_update_plan(plan_id: str, body: PlanIn, admin=Depends(require_admin)):
    await db.plans.update_one({"plan_id": plan_id}, {"$set": body.model_dump()})
    await audit(admin["user_id"], "admin_plan_update", {"plan_id": plan_id, **body.model_dump()})
    return {"ok": True}


@router.get("/admin/sources")
async def admin_sources(admin=Depends(require_admin)):
    items = await db.sources.find({}, NOID).to_list(50)
    for s in items:
        s["jobs"] = await db.jobs.count_documents({"sources": s["source_id"]})
    return items


class SourcePatch(BaseModel):
    enabled: Optional[bool] = None
    config: Optional[dict] = None


class BoardsIn(BaseModel):
    boards: list[str] = Field(default_factory=list, max_length=200)


@router.post("/admin/sources/{sid}/probe")
async def admin_probe_boards(sid: str, body: BoardsIn, admin=Depends(require_admin)):
    """Test candidate ATS board tokens without saving or writing any jobs.

    Board tokens are employer account slugs that are not guessable, so the admin needs to know
    which ones work before saving them. Reports per-board job counts and Saudi share.
    """
    import httpx
    import sources as S

    src = await db.sources.find_one({"source_id": sid}, NOID)
    if not src:
        raise HTTPException(404, "Source not found")
    fn = S.FETCHERS.get(sid)
    if not fn:
        raise HTTPException(400, "This source has no board list; its coverage depends on an API key.")
    boards = [b.strip() for b in body.boards if b and b.strip()][:60]
    if not boards:
        return {"results": []}

    async with httpx.AsyncClient(timeout=40, follow_redirects=True,
                                 headers={"User-Agent": "JobPilot/1.0 (+jobs aggregator)"}) as c:
        async def one(b):
            try:
                jobs = await fn(c, [], {"boards": [b]})
            except Exception as e:
                return {"board": b, "jobs": 0, "saudi": 0, "error": str(e)[:120]}
            sa = sum(1 for j in jobs
                     if S.detect_country(" ".join(str(j.get(k) or "") for k in ("location", "title", "city"))) == "SA"
                     or any(t in " ".join(str(j.get(k) or "") for k in ("location", "title", "city", "description")).lower()
                            for t in S.COUNTRY_HINTS["SA"]))
            return {"board": b, "jobs": len(jobs), "saudi": sa}

        results = await asyncio.gather(*(one(b) for b in boards))
    return {"results": list(results)}


@router.patch("/admin/sources/{sid}")
async def admin_patch_source(sid: str, body: SourcePatch, admin=Depends(require_admin)):
    await db.sources.update_one({"source_id": sid}, {"$set": body.model_dump(exclude_none=True)})
    await audit(admin["user_id"], "admin_source_update", {"source_id": sid, **body.model_dump(exclude_none=True)})
    return {"ok": True}


@router.post("/admin/sources/run")
async def admin_run_sources(bg: BackgroundTasks, source_id: str = "", admin=Depends(require_admin)):
    if source_id:
        src = await db.sources.find_one({"source_id": source_id}, NOID)
        from sources import _queries
        return {"new": await run_source(src, await _queries())}
    bg.add_task(run_all_sources)
    return {"started": True}


@router.get("/admin/ai-costs")
async def admin_ai_costs(days: int = 30, admin=Depends(require_admin)):
    since = iso(now() - timedelta(days=days))
    m = {"$match": {"created_at": {"$gte": since}}}
    by_feature = await db.ai_logs.aggregate([m, {"$group": {"_id": {"f": "$feature", "m": "$model"}, "cost": {"$sum": "$cost_usd"}, "calls": {"$sum": 1},
                                                            "cached": {"$sum": {"$cond": ["$cached", 1, 0]}}}}, {"$sort": {"cost": -1}}]).to_list(100)
    by_user = await db.ai_logs.aggregate([m, {"$group": {"_id": "$user_id", "cost": {"$sum": "$cost_usd"}, "calls": {"$sum": 1}}}, {"$sort": {"cost": -1}}, {"$limit": 25}]).to_list(25)
    emails = {u["user_id"]: u["email"] async for u in db.users.find({"user_id": {"$in": [u["_id"] for u in by_user]}}, {"_id": 0, "user_id": 1, "email": 1})}
    return {"by_feature": [{"feature": r["_id"]["f"], "model": r["_id"]["m"], "cost": round(r["cost"], 5), "calls": r["calls"], "cached": r["cached"]} for r in by_feature],
            "by_user": [{"user_id": r["_id"], "email": emails.get(r["_id"], "—"), "cost": round(r["cost"], 5), "calls": r["calls"]} for r in by_user]}


INTEGRATIONS = [
    ("Moyasar (mada, Apple Pay, STC Pay)", ["MOYASAR_PUBLISHABLE_KEY", "MOYASAR_SECRET_KEY"], "Optional: MOYASAR_APPLE_PAY=1 after verifying your domain in the Moyasar dashboard.", None),
    ("WhatsApp Business Cloud API", ["WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET"],
     "Create approved templates 'jobpilot_verify' (body: {{1}} code) and 'jobpilot_reminder' (body: {{1}} reminder text) in EN and AR.", "/api/whatsapp/webhook"),
    ("Gmail (Google OAuth)", ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"], "Authorised redirect URI below. Scope: gmail.compose.", "/api/oauth/gmail/callback"),
    ("Stripe", ["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"], "Needs a Stripe account in a supported country.", "/api/stripe/webhook"),
    ("Careerjet", ["CAREERJET_AFFID"], "Free publisher key from careerjet.com/partners.", None),
    ("Jooble", ["JOOBLE_API_KEY"], "Free key from jooble.org/api/about.", None),
    ("Adzuna", ["ADZUNA_APP_ID", "ADZUNA_APP_KEY"], "Free key from developer.adzuna.com (non-GCC countries).", None),
    ("NVIDIA NIM", ["NVIDIA_API_KEY"], "Optional alternative AI provider.", None),
]


@router.get("/admin/integrations")
async def admin_integrations(admin=Depends(require_admin)):
    from core import APP_URL
    return [{"name": n, "keys": [{"key": k, "set": bool(os.environ.get(k))} for k in keys], "configured": all(os.environ.get(k) for k in keys[:2] if k),
             "help": h, "url": f"{APP_URL}{path}" if path else None} for n, keys, h, path in INTEGRATIONS]


@router.get("/admin/models")
async def admin_models(admin=Depends(require_admin)):
    return {"current": await get_models(), "catalog": MODEL_CATALOG,
            "prompts": {k: {"version": v["version"], "tier": v["tier"]} for k, v in PROMPTS.items()}}


class ModelsIn(BaseModel):
    scoring: dict
    writing: dict


@router.put("/admin/models")
async def admin_set_models(body: ModelsIn, admin=Depends(require_admin)):
    for tier in (body.scoring, body.writing):
        provider, model = tier.get("provider"), tier.get("model")
        if provider not in MODEL_CATALOG and provider not in ai_providers.PROVIDERS:
            raise HTTPException(400, f"Unknown provider '{provider}'")
        # Accept a model the admin picked from the provider's live /models list, not just the
        # shipped catalog, so newly released models are usable without a code change.
        if model not in await ai_providers.known_models(provider):
            raise HTTPException(400, f"Unknown model '{model}' for provider '{provider}'")
        if not await ai_providers.provider_configured(provider):
            raise HTTPException(400, f"No API key configured for '{provider}'. Add one under AI providers first.")
    await db.settings.update_one({"key": "ai_models"}, {"$set": {"value": body.model_dump()}}, upsert=True)
    await audit(admin["user_id"], "admin_models_update", body.model_dump())
    return {"ok": True}


# ---------- AI provider credentials ----------
class ProviderIn(BaseModel):
    api_key: str = Field(default="", max_length=500)
    base_url: str = Field(default="", max_length=300)


async def _provider_view(pid):
    spec = ai_providers.PROVIDERS[pid]
    entry = (await ai_providers.get_provider_creds()).get(pid) or {}
    key = await ai_providers.provider_key(pid)
    return {"provider": pid, "label": spec["label"], "api": spec["api"],
            "env_var": spec["env"], "default_base_url": spec["base_url"],
            "base_url": await ai_providers.provider_base_url(pid),
            "configured": await ai_providers.provider_configured(pid),
            "source": "dashboard" if entry.get("api_key_enc") else ("env" if key else "none"),
            "key_hint": ai_providers.mask_key(key), "needs_base_url": bool(spec.get("needs_base_url"))}


@router.get("/admin/ai/providers")
async def admin_ai_providers(admin=Depends(require_admin)):
    return {"providers": [await _provider_view(p) for p in ai_providers.PROVIDERS]}


@router.put("/admin/ai/providers/{pid}")
async def admin_set_provider(pid: str, body: ProviderIn, request: Request, admin=Depends(require_admin)):
    if pid not in ai_providers.PROVIDERS:
        raise HTTPException(404, f"Unknown provider '{pid}'")
    if body.base_url and not body.base_url.startswith("https://"):
        raise HTTPException(400, "Base URL must start with https://")
    entry = (await ai_providers.get_provider_creds()).get(pid) or {}
    if body.api_key.strip():
        entry["api_key_enc"] = encrypt_str(body.api_key.strip())
    if body.base_url.strip():
        entry["base_url"] = body.base_url.strip().rstrip("/")
    if not entry.get("api_key_enc") and not entry.get("base_url"):
        raise HTTPException(400, "Provide an API key, a base URL, or both")
    entry["updated_at"] = iso()
    entry["updated_by"] = admin["user_id"]
    # Write only this provider's slot. Setting the whole "value" document here would silently
    # drop every other provider key the admin had saved.
    await db.settings.update_one({"key": ai_providers.CREDS_KEY}, {"$set": {f"value.{pid}": entry}}, upsert=True)
    # The credential change may have unlocked a live model list; drop any stale cache.
    ai_providers._model_cache.pop(pid, None)
    await db.settings.delete_one({"key": f"ai_models_{pid}"})
    # Audit the change without ever recording the secret itself.
    await audit(admin["user_id"], "admin_ai_provider_update", {"provider": pid, "key_set": bool(body.api_key.strip()),
                                                              "base_url_set": bool(body.base_url.strip())},
                actor_id=admin["user_id"], ip=client_ip(request))
    return await _provider_view(pid)


@router.delete("/admin/ai/providers/{pid}")
async def admin_delete_provider(pid: str, request: Request, admin=Depends(require_admin)):
    if pid not in ai_providers.PROVIDERS:
        raise HTTPException(404, f"Unknown provider '{pid}'")
    if any(t.get("provider") == pid for t in (await get_models()).values()):
        raise HTTPException(400, f"A tier is still using '{pid}'. Point it at another provider first.")
    await db.settings.update_one({"key": ai_providers.CREDS_KEY}, {"$unset": {f"value.{pid}": ""}}, upsert=True)
    await db.settings.delete_one({"key": f"ai_models_{pid}"})
    ai_providers._model_cache.pop(pid, None)
    await audit(admin["user_id"], "admin_ai_provider_delete", {"provider": pid}, actor_id=admin["user_id"], ip=client_ip(request))
    return await _provider_view(pid)


@router.get("/admin/ai/providers/{pid}/models")
async def admin_provider_models(pid: str, refresh: bool = False, admin=Depends(require_admin)):
    if pid not in ai_providers.PROVIDERS:
        raise HTTPException(404, f"Unknown provider '{pid}'")
    return await ai_providers.fetch_provider_models(pid, refresh=refresh)


@router.get("/admin/audit")
async def admin_audit(action: str = "", admin=Depends(require_admin)):
    q = {"action": {"$regex": action, "$options": "i"}} if action else {}
    logs = await db.audit_logs.find(q, NOID).sort("created_at", -1).to_list(300)
    emails = {u["user_id"]: u["email"] async for u in db.users.find({}, {"_id": 0, "user_id": 1, "email": 1})}
    for l in logs:
        l["user_email"] = emails.get(l["user_id"], "deleted")
        l["actor_email"] = emails.get(l["actor_id"], "deleted")
    return logs


# ---------- Privacy (PDPL / GDPR) ----------
class ConsentIn(BaseModel):
    type: str
    granted: bool


CONSENT_TYPES = ("terms", "ai_processing", "email_messaging", "whatsapp_messaging", "inbox_scanning")


@router.get("/privacy/consents")
async def get_consents(user=Depends(get_current_user)):
    history = await db.consents.find({"user_id": user["user_id"]}, NOID).sort("created_at", -1).to_list(200)
    return {"current": user.get("consents", {}), "history": history}


@router.post("/privacy/consents")
async def set_consent(body: ConsentIn, request: Request, user=Depends(get_current_user)):
    if body.type not in CONSENT_TYPES:
        raise HTTPException(400, "Unknown consent type")
    await db.consents.insert_one({"user_id": user["user_id"], "type": body.type, "granted": body.granted, "ip": client_ip(request), "created_at": iso()})
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {f"consents.{body.type}": body.granted}})
    await audit(user["user_id"], "consent_" + ("granted" if body.granted else "withdrawn"), {"type": body.type})
    return {"ok": True}


USER_COLLECTIONS = ["cv_versions", "searches", "reviews", "applications", "tailored", "reminders", "notifications", "consents", "usage", "files"]


@router.get("/privacy/export")
async def export_data(request: Request, user=Depends(get_current_user)):
    out = {"exported_at": iso(), "profile": user}
    for c in USER_COLLECTIONS:
        out[c] = await db[c].find({"user_id": user["user_id"]}, NOID).to_list(5000)
    out["manual_jobs"] = await db.jobs.find({"owner_user_id": user["user_id"]}, {"_id": 0, "fingerprint": 0}).to_list(2000)
    out["file_contents"] = []
    for f in out["files"]:
        if f.get("is_deleted"):
            continue
        try:
            data, _ = await get_file(f["file_id"], user["user_id"])
            out["file_contents"].append({"file_id": f["file_id"], "filename": f["filename"], "base64": base64.b64encode(data).decode()})
        except Exception:
            pass
    await audit(user["user_id"], "data_export", ip=client_ip(request))
    return Response(content=json.dumps(out, ensure_ascii=False, default=str), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="jobpilot-export.json"'})


class DeleteIn(BaseModel):
    confirm: str


@router.delete("/privacy/account")
async def delete_account(body: DeleteIn, request: Request, response: Response, user=Depends(get_current_user)):
    if body.confirm != "DELETE":
        raise HTTPException(400, "Type DELETE to confirm")
    if user.get("role") == "admin" and await db.users.count_documents({"role": "admin"}) <= 1:
        raise HTTPException(400, "The last admin account cannot be deleted")
    uid_ = user["user_id"]
    await db.files.update_many({"user_id": uid_}, {"$set": {"is_deleted": True, "storage_path": None}})
    for c in USER_COLLECTIONS + ["gmail_tokens", "user_sessions", "ai_logs"]:
        if c != "files":
            await db[c].delete_many({"user_id": uid_})
    await db.jobs.delete_many({"owner_user_id": uid_})
    await db.users.delete_one({"user_id": uid_})
    await db.workspaces.delete_many({"owner_id": uid_})
    await audit(uid_, "account_deleted", {"email_hash": hash(user["email"])}, ip=client_ip(request))
    clear_auth_cookies(response)
    return {"ok": True}
