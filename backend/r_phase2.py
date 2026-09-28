import os
import json
import copy
import hmac
import random
import hashlib
from datetime import timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from core import db, iso, now, parse_dt, uid, NOID, get_current_user, require_admin, get_plan, audit, client_ip, check_limit, inc_usage
from ai import llm_json, validate_tailored, finalize_review
from wa import wa_configured, wa_send_template, norm_phone, WA_VERIFY, WA_APP_SECRET, TPL_VERIFY
from r_apps import get_app, event
from r_cv import get_master

router = APIRouter(prefix="/api")


# ---------- Interview prep pack ----------
@router.post("/applications/{aid}/prep")
async def interview_prep(aid: str, user=Depends(get_current_user)):
    a = await get_app(aid, user["user_id"])
    master = await get_master(user["user_id"])
    if not master:
        raise HTTPException(400, "Upload and save your master CV first")
    job = await db.jobs.find_one({"job_id": a.get("job_id")}, NOID) if a.get("job_id") else None
    await check_limit(user, "reviews")
    payload = {"master_cv": master["data"], "job": {k: (job or a).get(k) for k in ("title", "company", "location", "description")}}
    try:
        res, meta = await llm_json("interview_prep", payload, user["user_id"], user.get("lang", "en"))
    except Exception as e:
        raise HTTPException(502, f"AI prep failed: {str(e)[:150]}")
    for q in res.get("questions") or []:
        ao = q.get("answer_outline")
        if isinstance(ao, dict):
            q["answer_outline"] = "\n".join(f"{k[:1].upper()}: {v}" for k, v in ao.items())
        elif isinstance(ao, list):
            q["answer_outline"] = "\n".join(map(str, ao))
    prep = {**res, "model": meta["model"], "prompt_version": meta["prompt_version"], "created_at": iso()}
    await db.applications.update_one({"application_id": aid}, {"$set": {"prep": prep}, "$push": {"timeline": event("prep", "Interview-prep pack generated")}})
    await inc_usage(user["user_id"], "reviews")
    return prep


# ---------- AI evaluation set ----------
CASES = json.loads((Path(__file__).parent / "eval" / "cases.json").read_text(encoding="utf-8"))


async def run_eval(run_id):
    results = []
    for c in CASES:
        r = {"id": c["id"], "lang": c["lang"], "expected": c["expected_verdict"]}
        try:
            rev, meta = await llm_json("review", {"master_cv": c["cv"], "job": c["job"]}, "eval", c["lang"])
            rev = finalize_review(rev)
            matched = {s.lower() for s in rev.get("matched_skills") or []}
            exp = [s.lower() for s in c["expected_matched"]]
            r.update(verdict=rev.get("verdict"), score=rev.get("score"), verdict_ok=rev.get("verdict") == c["expected_verdict"],
                     skill_recall=round(sum(1 for s in exp if any(s in m for m in matched)) / len(exp), 2) if exp else 1.0, model=meta["model"])
            fake = copy.deepcopy(c["cv"])
            fake["skills"] = list(fake.get("skills") or []) + [c["seeded_fake"]]
            flags, _ = await validate_tailored(c["cv"], fake, "", c["lang"], "eval")
            r["fake_caught"] = any(c["seeded_fake"].lower() in (f.get("value") or "").lower() for f in flags)
        except Exception as e:
            r["error"] = str(e)[:200]
        results.append(r)
    ok = [x for x in results if "error" not in x]
    n = max(len(ok), 1)
    metrics = {"cases": len(results), "errors": len(results) - len(ok),
               "verdict_agreement": round(100 * sum(x["verdict_ok"] for x in ok) / n),
               "skill_recall": round(100 * sum(x["skill_recall"] for x in ok) / n),
               "validator_recall": round(100 * sum(x["fake_caught"] for x in ok) / n),
               "arabic_verdict_agreement": round(100 * sum(x["verdict_ok"] for x in ok if x["lang"] == "ar") / max(1, sum(1 for x in ok if x["lang"] == "ar")))}
    cost = await db.ai_logs.aggregate([{"$match": {"user_id": "eval", "created_at": {"$gte": (await db.eval_runs.find_one({"run_id": run_id}))["created_at"]}}},
                                       {"$group": {"_id": None, "c": {"$sum": "$cost_usd"}}}]).to_list(1)
    metrics["cost_usd"] = round(cost[0]["c"], 4) if cost else 0
    await db.eval_runs.update_one({"run_id": run_id}, {"$set": {"status": "done", "results": results, "metrics": metrics, "finished_at": iso()}})


@router.post("/admin/eval/run")
async def eval_run(bg: BackgroundTasks, admin=Depends(require_admin)):
    from ai import get_models, PROMPTS
    models = await get_models()
    run = {"run_id": uid("eval_"), "status": "running", "models": models, "prompts": {k: v["version"] for k, v in PROMPTS.items()}, "created_at": iso()}
    await db.eval_runs.insert_one(run)
    bg.add_task(run_eval, run["run_id"])
    await audit(admin["user_id"], "eval_run_started", {"run_id": run["run_id"]})
    return {"run_id": run["run_id"]}


@router.get("/admin/eval/runs")
async def eval_runs(admin=Depends(require_admin)):
    runs = await db.eval_runs.find({}, NOID).sort("created_at", -1).to_list(20)
    return {"runs": runs, "cases": len(CASES)}


# ---------- WhatsApp Business Cloud API ----------
@router.get("/whatsapp/status")
async def wa_status(user=Depends(get_current_user)):
    plan = await get_plan(user)
    return {"configured": wa_configured(), "plan_allows": plan["features"].get("whatsapp", False),
            "opted_in": bool(user.get("whatsapp_opt_in")), "phone": user.get("whatsapp_phone")}


class WaStart(BaseModel):
    phone: str = Field(min_length=8, max_length=20)


@router.post("/whatsapp/start")
async def wa_start(body: WaStart, user=Depends(get_current_user)):
    if not wa_configured():
        raise HTTPException(503, "WhatsApp is not configured yet")
    if not (await get_plan(user))["features"].get("whatsapp"):
        raise HTTPException(402, {"code": "feature_locked", "kind": "whatsapp"})
    code = f"{random.randint(0, 999999):06d}"
    await db.wa_otps.replace_one({"user_id": user["user_id"]}, {"user_id": user["user_id"], "phone": norm_phone(body.phone),
                                                                "code_hash": hashlib.sha256(code.encode()).hexdigest(), "tries": 0, "expires_at": iso(now() + timedelta(minutes=10))}, upsert=True)
    if not await wa_send_template(body.phone, TPL_VERIFY, [code], user.get("lang", "en")):
        raise HTTPException(502, "Could not send the WhatsApp code")
    return {"ok": True}


class WaVerify(BaseModel):
    code: str
    consent: bool


@router.post("/whatsapp/verify")
async def wa_verify(body: WaVerify, request: Request, user=Depends(get_current_user)):
    o = await db.wa_otps.find_one({"user_id": user["user_id"]}, NOID)
    if not body.consent:
        raise HTTPException(400, "Consent is required")
    if not o or parse_dt(o["expires_at"]) < now() or o["tries"] >= 5:
        raise HTTPException(400, "Code expired. Request a new one.")
    if not hmac.compare_digest(o["code_hash"], hashlib.sha256(body.code.strip().encode()).hexdigest()):
        await db.wa_otps.update_one({"user_id": user["user_id"]}, {"$inc": {"tries": 1}})
        raise HTTPException(400, "Wrong code")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"whatsapp_phone": o["phone"], "whatsapp_opt_in": True, "consents.whatsapp_messaging": True}})
    await db.consents.insert_one({"user_id": user["user_id"], "type": "whatsapp_messaging", "granted": True, "ip": client_ip(request), "created_at": iso()})
    await db.wa_otps.delete_one({"user_id": user["user_id"]})
    await audit(user["user_id"], "whatsapp_opt_in", {"phone_last4": o["phone"][-4:]})
    return {"ok": True}


@router.post("/whatsapp/opt-out")
async def wa_opt_out(user=Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"whatsapp_opt_in": False, "consents.whatsapp_messaging": False}})
    await audit(user["user_id"], "whatsapp_opt_out", {"via": "app"})
    return {"ok": True}


@router.get("/whatsapp/webhook")
async def wa_webhook_verify(request: Request):
    q = request.query_params
    if WA_VERIFY and q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == WA_VERIFY:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "Verification failed")


SNOOZE = {"1h": 60, "1d": 1440, "1w": 10080}


@router.post("/whatsapp/webhook")
async def wa_webhook(request: Request):
    raw = await request.body()
    if WA_APP_SECRET:
        sig = request.headers.get("x-hub-signature-256", "")
        if not hmac.compare_digest(sig, "sha256=" + hmac.new(WA_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()):
            raise HTTPException(403, "Bad signature")
    data = json.loads(raw or b"{}")
    for entry in data.get("entry", []):
        for ch in entry.get("changes", []):
            for m in (ch.get("value") or {}).get("messages", []):
                text = ((m.get("text") or {}).get("body") or (m.get("button") or {}).get("text") or "").strip().lower()
                user = await db.users.find_one({"whatsapp_phone": norm_phone(m.get("from"))}, {"_id": 0, "user_id": 1})
                if not user:
                    continue
                if text in ("stop", "الغاء", "إلغاء", "توقف"):
                    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"whatsapp_opt_in": False, "consents.whatsapp_messaging": False}})
                    await audit(user["user_id"], "whatsapp_opt_out", {"via": "STOP"})
                    continue
                rem = await db.reminders.find_one({"user_id": user["user_id"], "status": "sent"}, NOID, sort=[("sent_at", -1)])
                if not rem:
                    continue
                if text in ("done", "تم"):
                    await db.reminders.update_one({"reminder_id": rem["reminder_id"]}, {"$set": {"status": "done", "done_at": iso()}})
                elif text.startswith("snooze") or text.startswith("تأجيل"):
                    mins = next((v for k, v in SNOOZE.items() if k in text), 1440)
                    t = iso(now() + timedelta(minutes=mins))
                    await db.reminders.update_one({"reminder_id": rem["reminder_id"]}, {"$set": {"status": "snoozed", "deliver_at": t, "due_at": t}})
    return {"ok": True}
