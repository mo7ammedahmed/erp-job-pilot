import re
import time
import statistics
from datetime import timedelta
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
from core import db, iso, uid, NOID, get_current_user, check_limit, inc_usage, get_plan, logger
from ai import llm_json, quick_match, finalize_review
from sources import job_query, run_all_sources, mk, upsert_jobs, fingerprint
from r_cv import get_master

router = APIRouter(prefix="/api")
LIST_PROJ = {"_id": 0, "description": 0, "fingerprint": 0}
_last_refresh = {}


@router.get("/jobs")
async def list_jobs(country: str = "", city: str = "", keywords: str = "", remote: str = "", seniority: str = "",
                    min_salary: Optional[float] = None, source: str = "", verdict: str = "", page: int = 1,
                    user=Depends(get_current_user)):
    f = dict(country=country, city=city, keywords=keywords, remote=remote, seniority=seniority, min_salary=min_salary, source=source)
    q = job_query(f, user["user_id"])
    master = await get_master(user["user_id"])
    reviews = {}
    if master:
        async for r in db.reviews.find({"user_id": user["user_id"], "cv_version_id": master["cv_version_id"]}, {"_id": 0, "job_id": 1, "result": 1}):
            reviews[r["job_id"]] = r["result"]
    if verdict:
        q["$and"].append({"job_id": {"$in": [j for j, r in reviews.items() if r.get("verdict") == verdict]}})
    total = await db.jobs.count_documents(q)
    docs = await db.jobs.find(q, {"_id": 0, "fingerprint": 0}).sort([("posted_at", -1), ("fetched_at", -1)]).skip((page - 1) * 30).limit(30).to_list(30)
    items = []
    for d in docs:
        r = reviews.get(d["job_id"])
        d["quick_score"] = quick_match(master and master["data"], d)
        d["review"] = {"score": r.get("score"), "verdict": r.get("verdict")} if r else None
        d["snippet"] = (d.pop("description", "") or "")[:220]
        items.append(d)
    return {"items": items, "total": total, "page": page}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user=Depends(get_current_user)):
    job = await db.jobs.find_one({"job_id": job_id, "$or": [{"owner_user_id": None}, {"owner_user_id": user["user_id"]}]}, {"_id": 0, "fingerprint": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    master = await get_master(user["user_id"])
    review = None
    if master:
        review = await db.reviews.find_one({"user_id": user["user_id"], "job_id": job_id, "cv_version_id": master["cv_version_id"]}, NOID)
    app = await db.applications.find_one({"user_id": user["user_id"], "job_id": job_id}, {"_id": 0, "application_id": 1, "status": 1})
    tailored = await db.tailored.find({"user_id": user["user_id"], "job_id": job_id}, {"_id": 0, "tailored_id": 1, "status": 1, "lang": 1, "created_at": 1}).sort("created_at", -1).to_list(20)
    return {"job": job, "review": review, "application": app, "tailored": tailored,
            "quick_score": quick_match(master and master["data"], job), "has_master": bool(master)}


class ManualIn(BaseModel):
    text: str = Field(min_length=40, max_length=30000)
    url: str = ""


@router.post("/jobs/manual")
async def add_manual(body: ManualIn, user=Depends(get_current_user)):
    try:
        n, _ = await llm_json("normalize_job", body.text, user["user_id"])
    except Exception as e:
        raise HTTPException(502, f"AI normalization failed: {str(e)[:150]}")
    job = mk("manual", uid(), n.get("title") or "Untitled role", n.get("company") or "", n.get("location") or n.get("city") or "",
             body.url, n.get("description") or body.text, country=n.get("country_code") or None,
             remote=n.get("remote") if n.get("remote") in ("remote", "onsite", "hybrid") else "onsite",
             posted_at=iso(), salary_min=n.get("salary_min"), salary_max=n.get("salary_max"), currency=n.get("currency") or None,
             owner_user_id=user["user_id"], requirements=n.get("requirements") or [], deadline=n.get("deadline"),
             seniority=n.get("seniority"), apply_email=n.get("apply_email") or "")
    job["fingerprint"] = fingerprint(job["title"], job["company"], f"{job['city']}|{user['user_id']}")
    job.update(job_id=uid("job_"), sources=["manual"], fetched_at=iso(), last_seen=iso())
    await db.jobs.insert_one(job)
    job.pop("_id", None)
    return job


async def run_review(user, job_id, force=False):
    master = await get_master(user["user_id"])
    if not master:
        raise HTTPException(400, "Upload and save your master CV first")
    key = {"user_id": user["user_id"], "job_id": job_id, "cv_version_id": master["cv_version_id"]}
    existing = await db.reviews.find_one(key, NOID)
    if existing and not force:
        return existing
    job = await db.jobs.find_one({"job_id": job_id}, NOID)
    if not job:
        raise HTTPException(404, "Job not found")
    await check_limit(user, "reviews")
    payload = {"master_cv": master["data"], "job": {k: job.get(k) for k in ("title", "company", "location", "country", "remote", "salary_min", "salary_max", "currency", "description")}}
    try:
        res, meta = await llm_json("review", payload, user["user_id"], user.get("lang", "en"))
    except Exception as e:
        raise HTTPException(502, f"AI review failed: {str(e)[:150]}")
    res = finalize_review(res)
    doc = {**key, "review_id": uid("rev_"), "result": res, **meta, "created_at": iso()}
    await db.reviews.replace_one(key, doc, upsert=True)
    await inc_usage(user["user_id"], "reviews")
    doc.pop("_id", None)
    return doc


class ReviewIn(BaseModel):
    force: bool = False


@router.post("/jobs/{job_id}/review")
async def review(job_id: str, body: ReviewIn, user=Depends(get_current_user)):
    return await run_review(user, job_id, body.force)


@router.post("/jobs/refresh")
async def refresh(bg: BackgroundTasks, user=Depends(get_current_user)):
    if time.time() - _last_refresh.get("t", 0) < 300:
        return {"started": False, "message": "A refresh ran in the last 5 minutes"}
    _last_refresh["t"] = time.time()
    bg.add_task(run_all_sources)
    return {"started": True}


SENIORITY_WORDS = r"\b(senior|sr\.?|junior|jr\.?|lead|principal|head of|intern|trainee|i{1,3}|iv)\b"


@router.get("/jobs/{job_id}/salary")
async def salary_benchmark(job_id: str, user=Depends(get_current_user)):
    from core import parse_dt, now
    job = await db.jobs.find_one({"job_id": job_id}, {"_id": 0, "title": 1, "city": 1, "country": 1, "seniority": 1, "location": 1})
    if not job:
        raise HTTPException(404, "Job not found")
    role = re.sub(r"\s+", " ", re.sub(SENIORITY_WORDS, "", re.sub(r"\(.*?\)|[-|/,].*$", "", job["title"].lower()))).strip() or job["title"].lower()
    country = job.get("country") or user.get("country") or "SA"
    city = (job.get("city") or "").lower()
    key = f"{role}|{city}|{country}|{user.get('lang', 'en')}"
    cached = await db.salary_benchmarks.find_one({"key": key}, NOID)
    if cached and parse_dt(cached["created_at"]) > now() - timedelta(days=30):
        return cached["value"]
    comps = await db.jobs.find({"country": country, "salary_max": {"$ne": None}, "title": {"$regex": re.escape(role[:40]), "$options": "i"}},
                               {"_id": 0, "salary_min": 1, "salary_max": 1, "currency": 1}).to_list(300)
    mids = sorted(((c.get("salary_min") or c["salary_max"]) + c["salary_max"]) / 2 for c in comps if c.get("salary_max"))
    if len(mids) >= 5:
        q = statistics.quantiles(mids, n=4)
        cur = max({c.get("currency") for c in comps}, key=lambda x: sum(1 for c in comps if c.get("currency") == x)) or ""
        value = {"source": "listings", "sample_size": len(mids), "currency": cur, "period": "listing", "p25": round(q[0]), "median": round(q[1]), "p75": round(q[2]), "confidence": "medium", "notes": ""}
    else:
        try:
            res, meta = await llm_json("salary_benchmark", {"role": job["title"], "seniority": job.get("seniority") or "", "city": job.get("city") or "", "country": country}, user["user_id"], user.get("lang", "en"))
            value = {"source": "ai_estimate", "sample_size": len(mids), **{k: res.get(k) for k in ("currency", "period", "p25", "median", "p75", "confidence", "notes")}, "model": meta["model"]}
        except Exception as e:
            # Do not cache this: a provider outage must not poison the benchmark for 30 days.
            # Report the gap honestly instead of returning an error or inventing a number.
            logger.warning(f"salary_benchmark AI estimate failed for role={role!r}: {e}")
            return {"role": role, "source": "unavailable", "sample_size": len(mids), "currency": "",
                    "period": "", "p25": None, "median": None, "p75": None, "confidence": "none",
                    "notes": "Not enough comparable listings, and the AI estimate is temporarily unavailable. Try again shortly."}
    value["role"] = role
    await db.salary_benchmarks.replace_one({"key": key}, {"key": key, "value": value, "created_at": iso()}, upsert=True)
    return value


@router.get("/meta/sources")
async def meta_sources(user=Depends(get_current_user)):
    return await db.sources.find({}, {"_id": 0, "source_id": 1, "name": 1, "attribution": 1, "enabled": 1, "status": 1}).to_list(50)


class SearchIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    country: str = "SA"
    city: str = ""
    keywords: str = ""
    remote: str = ""
    seniority: str = ""
    min_salary: Optional[float] = None
    alerts: bool = True


@router.get("/searches")
async def list_searches(user=Depends(get_current_user)):
    return await db.searches.find({"user_id": user["user_id"]}, NOID).sort("created_at", -1).to_list(50)


@router.post("/searches")
async def create_search(body: SearchIn, bg: BackgroundTasks, user=Depends(get_current_user)):
    doc = {**body.model_dump(), "search_id": uid("srch_"), "user_id": user["user_id"], "created_at": iso(), "last_alert_at": iso()}
    await db.searches.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/searches/{sid}")
async def update_search(sid: str, body: SearchIn, user=Depends(get_current_user)):
    await db.searches.update_one({"search_id": sid, "user_id": user["user_id"]}, {"$set": body.model_dump()})
    return await db.searches.find_one({"search_id": sid}, NOID)


@router.delete("/searches/{sid}")
async def delete_search(sid: str, user=Depends(get_current_user)):
    await db.searches.delete_one({"search_id": sid, "user_id": user["user_id"]})
    return {"ok": True}
