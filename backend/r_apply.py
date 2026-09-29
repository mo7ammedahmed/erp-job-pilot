from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from apply import run_apply_async
from core import db, iso, uid, NOID, get_current_user, audit, notify, put_file, get_file, period
from r_cv import get_master
from r_apps import APPLIED_LIKE, event

router = APIRouter(prefix="/api")

# Auto-apply is a real outbound action against a third party, so every run is recorded and the
# user can see exactly what happened. Runs are rate limited per month to keep the shared egress IP
# from hammering a handful of ATS platforms.
MONTHLY_RUN_LIMIT = 120


class ProfileIn(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    website: str = ""
    location: str = ""
    cover_letter: str = ""
    attach_cv: bool = True


class ApplyIn(BaseModel):
    job_id: str
    # False previews the form: it is filled and screenshotted but never submitted.
    submit: bool = True
    note: str = ""


async def _profile(user):
    p = await db.apply_profiles.find_one({"user_id": user["user_id"]}, NOID)
    if p:
        return p
    # Seed from the account so a user can try a preview before filling anything in.
    name = (user.get("name") or "").strip()
    parts = name.split()
    return {"user_id": user["user_id"], "first_name": parts[0] if parts else "",
            "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
            "email": user.get("email") or "", "phone": "", "linkedin": "", "website": "",
            "location": " ".join(x for x in (user.get("city"), "") if x), "cover_letter": "",
            "attach_cv": True, "created_at": None}


@router.get("/apply/profile")
async def get_profile(user=Depends(get_current_user)):
    return await _profile(user)


@router.put("/apply/profile")
async def put_profile(body: ProfileIn, user=Depends(get_current_user)):
    doc = {"user_id": user["user_id"], **body.model_dump(), "updated_at": iso()}
    await db.apply_profiles.update_one({"user_id": user["user_id"]}, {"$set": doc}, upsert=True)
    await audit(user["user_id"], "apply_profile_update", {"email": doc["email"]})
    doc.pop("_id", None)
    return doc


@router.post("/apply/preview")
async def preview(body: ApplyIn, user=Depends(get_current_user)):
    """Fill the real form without submitting, so the user can see it worked before committing."""
    return await _run(body, user, submit=False)


@router.post("/apply")
async def apply_job(body: ApplyIn, user=Depends(get_current_user)):
    return await _run(body, user, submit=body.submit)


async def _run(body: ApplyIn, user, submit: bool):
    user_id = user["user_id"]
    job = await db.jobs.find_one({"job_id": body.job_id}, NOID)
    if not job:
        raise HTTPException(404, "Job not found")
    apply_url = job.get("apply_url") or job.get("url")
    if not apply_url:
        raise HTTPException(400, "This job has no application link")

    prof = await _profile(user)
    if not prof.get("email"):
        raise HTTPException(400, "Add your email to the apply profile first")

    used = await db.apply_runs.count_documents({"user_id": user_id, "period": period()})
    if used >= MONTHLY_RUN_LIMIT:
        raise HTTPException(402, {"code": "limit_reached", "kind": "auto_apply",
                                  "limit": MONTHLY_RUN_LIMIT, "period": period()})

    cv = None
    if prof.get("attach_cv", True):
        master = await get_master(user_id)
        if master and master.get("file_id"):
            try:
                data, doc = await get_file(master["file_id"], user_id)
                cv = (data, doc)
            except Exception:
                cv = None

    payload = {k: prof.get(k) for k in ("first_name", "last_name", "email", "phone",
                                        "linkedin", "website", "location", "cover_letter")}
    result = await run_apply_async(apply_url, payload, cv=cv, submit=submit)

    shot_id = None
    if result.get("screenshot"):
        try:
            with open(result["screenshot"], "rb") as fh:
                f = await put_file(user_id, fh.read(), "apply-evidence.png", "image/png", kind="apply_evidence")
            shot_id = f["file_id"]
        except Exception:
            shot_id = None

    run = {"run_id": uid("run_"), "user_id": user_id, "job_id": body.job_id,
           "title": job.get("title"), "company": job.get("company"),
           "ats": job.get("ats") or "unknown", "apply_url": apply_url,
           "status": result["status"], "message": result["message"], "filled": result.get("filled") or [],
           "blockers": result.get("blockers") or [], "submitted": bool(result.get("submitted")),
           "final_url": result.get("final_url") or "", "evidence_file_id": shot_id,
           "preview": not submit, "note": body.note, "period": period(), "created_at": iso()}
    await db.apply_runs.insert_one(run)
    run.pop("_id", None)

    # Only a verified submission may move the tracker. A needs_human or failed run leaves the
    # application exactly where it was so the user can finish it themselves.
    if result.get("submitted") and result["status"] == "submitted":
        app = await db.applications.find_one({"user_id": user_id, "job_id": body.job_id}, NOID)
        if app and app.get("status") not in APPLIED_LIKE:
            await db.applications.update_one(
                {"application_id": app["application_id"]},
                {"$set": {"status": "applied", "applied_at": iso(), "updated_at": iso()},
                 "$push": {"timeline": event("apply", "Applied automatically", run_id=run["run_id"])}})
        elif not app:
            await db.applications.insert_one({
                "application_id": uid("app_"), "user_id": user_id, "job_id": body.job_id,
                "title": job.get("title") or "", "company": job.get("company") or "",
                "url": job.get("url") or "", "location": job.get("location") or "",
                "status": "applied", "source": job.get("source"), "notes": [], "contacts": [],
                "documents": [], "reached": ["applied"], "applied_at": iso(), "interview_at": None,
                "followup_at": None, "deadline_at": None, "salary": "", "tailored_id": None,
                "ghost_suggested": False, "created_at": iso(), "updated_at": iso(),
                "timeline": [event("apply", "Applied automatically", run_id=run["run_id"])]})

    await audit(user_id, "auto_apply", {"job_id": body.job_id, "status": result["status"],
                                        "submitted": run["submitted"], "preview": run["preview"]})
    if result["status"] == "submitted":
        await notify(user_id, f"Applied: {job.get('title')}", link=f"/app/jobs/{body.job_id}", kind="apply")

    run["evidence_file_id"] = shot_id
    return run


@router.get("/apply/runs")
async def list_runs(limit: int = 50, user=Depends(get_current_user)):
    cur = db.apply_runs.find({"user_id": user["user_id"]}, NOID).sort("created_at", -1).limit(min(limit, 200))
    return await cur.to_list(length=min(limit, 200))
