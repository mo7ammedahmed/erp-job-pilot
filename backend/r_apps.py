from datetime import timedelta, datetime, time as dtime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Optional
from core import (db, iso, now, parse_dt, norm_iso, uid, NOID, get_current_user, check_limit, inc_usage, audit, notify,
                  put_file, get_plan, send_email, email_layout)
from ai import llm_json, validate_tailored, remove_path, compact
from exporter import to_pdf, to_docx
from r_cv import get_master

router = APIRouter(prefix="/api")
STATUSES = ["saved", "preparing", "applied", "interview", "offer", "rejected", "ghosted"]
APPLIED_LIKE = {"applied", "interview", "offer", "rejected", "ghosted"}


def event(kind, text, **meta):
    return {"event_id": uid("evt_"), "kind": kind, "text": text, "meta": meta, "at": iso()}


async def get_app(app_id, user_id):
    a = await db.applications.find_one({"application_id": app_id, "user_id": user_id}, NOID)
    if not a:
        raise HTTPException(404, "Application not found")
    return a


# ---------- reminders scheduling ----------
async def _add_reminder(user_id, app_id, rtype, title, due):
    await db.reminders.insert_one({"reminder_id": uid("rem_"), "user_id": user_id, "application_id": app_id, "type": rtype,
                                   "title": title, "due_at": iso(due), "deliver_at": iso(due), "status": "pending", "auto": True, "created_at": iso()})


async def schedule_rules(user, app):
    uid_, aid = user["user_id"], app["application_id"]
    await db.reminders.delete_many({"application_id": aid, "auto": True, "status": {"$in": ["pending", "snoozed"]}})
    label = f"{app.get('title', '')} @ {app.get('company', '')}".strip(" @")
    t = now()
    if app["status"] == "applied" and app.get("applied_at"):
        due = parse_dt(app["applied_at"]) + timedelta(days=user.get("followup_days", 7))
        if app.get("followup_at"):
            due = parse_dt(app["followup_at"])
        if due > t:
            await _add_reminder(uid_, aid, "follow_up", f"Follow up: {label}", due)
    if app.get("interview_at") and app["status"] in ("applied", "interview", "preparing", "saved"):
        iv = parse_dt(app["interview_at"])
        for hrs, rtype in ((24, "interview_24h"), (1, "interview_1h")):
            if iv - timedelta(hours=hrs) > t:
                await _add_reminder(uid_, aid, rtype, f"Interview in {hrs}h: {label}", iv - timedelta(hours=hrs))
    if app.get("deadline_at") and app["status"] in ("saved", "preparing"):
        d = parse_dt(app["deadline_at"]) - timedelta(days=2)
        if d > t:
            await _add_reminder(uid_, aid, "deadline", f"Deadline in 2 days: {label}", d)


# ---------- applications ----------
class AppIn(BaseModel):
    job_id: Optional[str] = None
    title: str = ""
    company: str = ""
    url: str = ""
    status: str = "saved"
    location: str = ""


@router.get("/applications")
async def list_apps(user=Depends(get_current_user)):
    return await db.applications.find({"user_id": user["user_id"]}, {"_id": 0, "timeline": 0}).sort("updated_at", -1).to_list(1000)


@router.post("/applications")
async def create_app(body: AppIn, user=Depends(get_current_user)):
    if body.job_id:
        ex = await db.applications.find_one({"user_id": user["user_id"], "job_id": body.job_id}, NOID)
        if ex:
            return ex
    await check_limit(user, "applications")
    data = body.model_dump()
    source = "manual"
    if body.job_id:
        job = await db.jobs.find_one({"job_id": body.job_id}, NOID)
        if not job:
            raise HTTPException(404, "Job not found")
        data.update(title=job["title"], company=job["company"], url=job.get("url") or "", location=job.get("location", ""))
        source = job["source"]
    if data["status"] not in STATUSES:
        data["status"] = "saved"
    doc = {**data, "application_id": uid("app_"), "user_id": user["user_id"], "source": source, "notes": [], "contacts": [],
           "documents": [], "reached": [data["status"]], "timeline": [event("created", f"Added to {data['status']}")],
           "applied_at": iso() if data["status"] == "applied" else None, "interview_at": None, "followup_at": None,
           "deadline_at": None, "salary": "", "tailored_id": None, "ghost_suggested": False, "created_at": iso(), "updated_at": iso()}
    await db.applications.insert_one(doc)
    doc.pop("_id", None)
    await schedule_rules(user, doc)
    return doc


@router.get("/applications/{aid}")
async def get_application(aid: str, user=Depends(get_current_user)):
    a = await get_app(aid, user["user_id"])
    a["reminders"] = await db.reminders.find({"application_id": aid}, NOID).sort("due_at", 1).to_list(50)
    a["tailored_versions"] = await db.tailored.find({"application_id": aid}, {"_id": 0, "tailored_id": 1, "status": 1, "lang": 1, "created_at": 1}).to_list(20)
    return a


class AppPatch(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    url: Optional[str] = None
    location: Optional[str] = None
    salary: Optional[str] = None
    interview_at: Optional[str] = None
    followup_at: Optional[str] = None
    deadline_at: Optional[str] = None


@router.patch("/applications/{aid}")
async def patch_app(aid: str, body: AppPatch, user=Depends(get_current_user)):
    a = await get_app(aid, user["user_id"])
    upd = body.model_dump(exclude_none=True)
    for k in ("interview_at", "followup_at", "deadline_at"):
        if k in upd:
            upd[k] = norm_iso(upd[k]) if upd[k] else None
    evts = [event("updated", f"{k.replace('_at', '').replace('_', ' ')} set", field=k, value=upd[k]) for k in upd if k.endswith("_at") and upd[k]]
    await db.applications.update_one({"application_id": aid}, {"$set": {**upd, "updated_at": iso()}, "$push": {"timeline": {"$each": evts}}})
    a.update(upd)
    await schedule_rules(user, a)
    return await get_application(aid, user)


class MoveIn(BaseModel):
    status: str


@router.post("/applications/{aid}/move")
async def move_app(aid: str, body: MoveIn, user=Depends(get_current_user)):
    if body.status not in STATUSES:
        raise HTTPException(400, "Invalid status")
    a = await get_app(aid, user["user_id"])
    upd = {"status": body.status, "updated_at": iso(), "ghost_suggested": False}
    if body.status == "applied" and not a.get("applied_at"):
        upd["applied_at"] = iso()
    await db.applications.update_one({"application_id": aid}, {"$set": upd, "$addToSet": {"reached": body.status},
                                                                "$push": {"timeline": event("status", f"{a['status']} → {body.status}", **{"from": a["status"], "to": body.status})}})
    a.update(upd)
    await schedule_rules(user, a)
    return {"ok": True, "status": body.status}


@router.delete("/applications/{aid}")
async def delete_app(aid: str, user=Depends(get_current_user)):
    await get_app(aid, user["user_id"])
    await db.applications.delete_one({"application_id": aid})
    await db.reminders.delete_many({"application_id": aid})
    return {"ok": True}


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


@router.post("/applications/{aid}/notes")
async def add_note(aid: str, body: NoteIn, user=Depends(get_current_user)):
    await get_app(aid, user["user_id"])
    note = {"note_id": uid("note_"), "text": body.text, "created_at": iso()}
    await db.applications.update_one({"application_id": aid}, {"$push": {"notes": note, "timeline": event("note", "Note added")}, "$set": {"updated_at": iso()}})
    return note


@router.delete("/applications/{aid}/notes/{nid}")
async def del_note(aid: str, nid: str, user=Depends(get_current_user)):
    await db.applications.update_one({"application_id": aid, "user_id": user["user_id"]}, {"$pull": {"notes": {"note_id": nid}}})
    return {"ok": True}


class ContactIn(BaseModel):
    name: str = Field(min_length=1)
    role: str = ""
    email: str = ""
    phone: str = ""


@router.post("/applications/{aid}/contacts")
async def add_contact(aid: str, body: ContactIn, user=Depends(get_current_user)):
    await get_app(aid, user["user_id"])
    c = {**body.model_dump(), "contact_id": uid("ct_")}
    await db.applications.update_one({"application_id": aid}, {"$push": {"contacts": c, "timeline": event("contact", f"Contact added: {body.name}")}})
    return c


@router.delete("/applications/{aid}/contacts/{cid}")
async def del_contact(aid: str, cid: str, user=Depends(get_current_user)):
    await db.applications.update_one({"application_id": aid, "user_id": user["user_id"]}, {"$pull": {"contacts": {"contact_id": cid}}})
    return {"ok": True}


@router.post("/applications/{aid}/documents")
async def add_document(aid: str, file: UploadFile = File(...), user=Depends(get_current_user)):
    await get_app(aid, user["user_id"])
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 8 MB)")
    f = await put_file(user["user_id"], data, file.filename, file.content_type or "application/octet-stream", kind="document")
    d = {"file_id": f["file_id"], "filename": f["filename"], "kind": "file", "created_at": iso()}
    await db.applications.update_one({"application_id": aid}, {"$push": {"documents": d, "timeline": event("document", f"Document: {f['filename']}")}})
    return d


# ---------- tailoring ----------
class TailorIn(BaseModel):
    job_id: str
    application_id: Optional[str] = None
    lang: str = "en"


@router.post("/tailor")
async def tailor(body: TailorIn, user=Depends(get_current_user)):
    master = await get_master(user["user_id"])
    if not master:
        raise HTTPException(400, "Upload and save your master CV first")
    job = await db.jobs.find_one({"job_id": body.job_id}, NOID)
    if not job:
        raise HTTPException(404, "Job not found")
    await check_limit(user, "tailors")
    lang = body.lang if body.lang in ("en", "ar") else "en"
    payload = {"master_cv": master["data"], "job": {k: job.get(k) for k in ("title", "company", "location", "description", "requirements")}}
    try:
        res, meta = await llm_json("tailor", payload, user["user_id"], lang)
    except Exception as e:
        raise HTTPException(502, f"AI tailoring failed: {str(e)[:150]}")
    cv = res.get("cv") or {}
    cover = res.get("cover_letter") or ""
    flags, vmeta = await validate_tailored(master["data"], cv, cover, lang, user["user_id"])
    doc = {"tailored_id": uid("tl_"), "user_id": user["user_id"], "job_id": body.job_id, "application_id": body.application_id,
           "cv_version_id": master["cv_version_id"], "cv_version": master["version"], "lang": lang, "cv": cv, "cover_letter": cover,
           "changes": res.get("changes") or [], "flags": flags, "status": "draft", "ai": meta, "validation_ai": vmeta,
           "job_title": job["title"], "company": job["company"], "created_at": iso(), "updated_at": iso()}
    await db.tailored.insert_one(doc)
    await inc_usage(user["user_id"], "tailors")
    doc.pop("_id", None)
    return doc


async def get_tl(tid, user_id):
    t = await db.tailored.find_one({"tailored_id": tid, "user_id": user_id}, NOID)
    if not t:
        raise HTTPException(404, "Tailored CV not found")
    return t


@router.get("/tailor/{tid}")
async def get_tailored(tid: str, user=Depends(get_current_user)):
    t = await get_tl(tid, user["user_id"])
    mv = await db.cv_versions.find_one({"cv_version_id": t["cv_version_id"]}, {"_id": 0, "data": 1})
    t["master"] = (mv or {}).get("data", {})
    return t


class TailorPatch(BaseModel):
    cv: Optional[dict] = None
    cover_letter: Optional[str] = None


@router.patch("/tailor/{tid}")
async def patch_tailored(tid: str, body: TailorPatch, user=Depends(get_current_user)):
    t = await get_tl(tid, user["user_id"])
    if t["status"] == "approved":
        raise HTTPException(400, "Approved versions are locked")
    upd = body.model_dump(exclude_none=True)
    await db.tailored.update_one({"tailored_id": tid}, {"$set": {**upd, "updated_at": iso()}})
    return await get_tailored(tid, user)


@router.post("/tailor/{tid}/revalidate")
async def revalidate(tid: str, user=Depends(get_current_user)):
    t = await get_tl(tid, user["user_id"])
    mv = await db.cv_versions.find_one({"cv_version_id": t["cv_version_id"]}, {"_id": 0, "data": 1})
    confirmed = {(f["path"], f["value"].lower()) for f in t["flags"] if f["status"] == "confirmed"}
    flags, _ = await validate_tailored(mv["data"], compact(t["cv"]), t["cover_letter"], t["lang"], user["user_id"])
    for f in flags:
        if (f["path"], f["value"].lower()) in confirmed:
            f["status"] = "confirmed"
    await db.tailored.update_one({"tailored_id": tid}, {"$set": {"flags": flags, "updated_at": iso()}})
    return await get_tailored(tid, user)


class FlagIn(BaseModel):
    action: str


@router.post("/tailor/{tid}/flags/{fid}")
async def resolve_flag(tid: str, fid: str, body: FlagIn, user=Depends(get_current_user)):
    t = await get_tl(tid, user["user_id"])
    if body.action not in ("remove", "confirm", "reopen"):
        raise HTTPException(400, "Invalid action")
    for f in t["flags"]:
        if f["flag_id"] == fid:
            if body.action == "remove" and f["path"] and f["path"] != "cover_letter":
                remove_path(t["cv"], f["path"])
            f["status"] = {"remove": "removed", "confirm": "confirmed", "reopen": "open"}[body.action]
    await db.tailored.update_one({"tailored_id": tid}, {"$set": {"flags": t["flags"], "cv": t["cv"], "updated_at": iso()}})
    await audit(user["user_id"], "validation_flag_" + body.action, {"tailored_id": tid, "flag_id": fid})
    return await get_tailored(tid, user)


@router.post("/tailor/{tid}/approve")
async def approve(tid: str, user=Depends(get_current_user)):
    t = await get_tl(tid, user["user_id"])
    if any(f["status"] == "open" for f in t["flags"]):
        raise HTTPException(400, "Resolve all validation flags before approving")
    aid = t.get("application_id")
    if not aid:
        ex = await db.applications.find_one({"user_id": user["user_id"], "job_id": t["job_id"]}, {"_id": 0, "application_id": 1})
        aid = ex["application_id"] if ex else (await create_app(AppIn(job_id=t["job_id"], status="preparing"), user))["application_id"]
    await db.tailored.update_one({"tailored_id": tid}, {"$set": {"status": "approved", "cv": compact(t["cv"]), "application_id": aid, "approved_at": iso()}})
    await db.applications.update_one({"application_id": aid}, {"$set": {"tailored_id": tid, "updated_at": iso()},
                                                                "$push": {"documents": {"tailored_id": tid, "filename": f"Tailored CV ({t['lang'].upper()})", "kind": "tailored", "created_at": iso()},
                                                                          "timeline": event("tailored", "Tailored CV approved", tailored_id=tid)}})
    await audit(user["user_id"], "tailored_cv_approved", {"tailored_id": tid})
    return {"ok": True, "application_id": aid}


def render_export(t, fmt, doc):
    cv = compact(t["cv"])
    if fmt == "pdf":
        return to_pdf(cv, t["cover_letter"], t["lang"], doc), "application/pdf"
    return to_docx(cv, t["cover_letter"], t["lang"], doc), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/tailor/{tid}/export")
async def export(tid: str, fmt: str = "pdf", doc: str = "cv", user=Depends(get_current_user)):
    t = await get_tl(tid, user["user_id"])
    if t["status"] != "approved":
        raise HTTPException(400, "Approve the tailored CV before exporting")
    data, mime = render_export(t, "pdf" if fmt == "pdf" else "docx", "cover" if doc == "cover" else "cv")
    name = f"{(t['cv'].get('name') or 'CV').replace(' ', '_')}_{'CoverLetter' if doc == 'cover' else 'CV'}_{t['company'][:20].replace(' ', '_')}.{fmt}"
    await audit(user["user_id"], "export", {"tailored_id": tid, "fmt": fmt, "doc": doc})
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/tailored")
async def list_tailored(user=Depends(get_current_user)):
    return await db.tailored.find({"user_id": user["user_id"]}, {"_id": 0, "cv": 0, "cover_letter": 0, "flags": 0}).sort("created_at", -1).to_list(200)


# ---------- reminders ----------
class ReminderIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: str
    application_id: Optional[str] = None


@router.get("/reminders")
async def list_reminders(status: str = "", user=Depends(get_current_user)):
    q = {"user_id": user["user_id"]}
    if status:
        q["status"] = {"$in": status.split(",")}
    return await db.reminders.find(q, NOID).sort("due_at", 1).to_list(500)


@router.post("/reminders")
async def create_reminder(body: ReminderIn, user=Depends(get_current_user)):
    due = norm_iso(body.due_at)
    doc = {"reminder_id": uid("rem_"), "user_id": user["user_id"], "application_id": body.application_id, "type": "custom",
           "title": body.title, "due_at": due, "deliver_at": due, "status": "pending", "auto": False, "created_at": iso()}
    await db.reminders.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/reminders/{rid}/done")
async def reminder_done(rid: str, user=Depends(get_current_user)):
    await db.reminders.update_one({"reminder_id": rid, "user_id": user["user_id"]}, {"$set": {"status": "done", "done_at": iso()}})
    return {"ok": True}


class SnoozeIn(BaseModel):
    minutes: int = Field(ge=5, le=60 * 24 * 14)


@router.post("/reminders/{rid}/snooze")
async def reminder_snooze(rid: str, body: SnoozeIn, user=Depends(get_current_user)):
    t = iso(now() + timedelta(minutes=body.minutes))
    await db.reminders.update_one({"reminder_id": rid, "user_id": user["user_id"]}, {"$set": {"status": "snoozed", "deliver_at": t, "due_at": t}})
    return {"ok": True, "due_at": t}


@router.delete("/reminders/{rid}")
async def reminder_delete(rid: str, user=Depends(get_current_user)):
    await db.reminders.delete_one({"reminder_id": rid, "user_id": user["user_id"]})
    return {"ok": True}


def quiet_until(user, at):
    tz = ZoneInfo(user.get("timezone") or "Asia/Riyadh")
    local = at.astimezone(tz)
    qs = dtime.fromisoformat(user.get("quiet_start") or "22:00")
    qe = dtime.fromisoformat(user.get("quiet_end") or "08:00")
    t = local.time()
    in_quiet = (qs <= t or t < qe) if qs > qe else (qs <= t < qe)
    if not in_quiet:
        return None
    end = datetime.combine(local.date(), qe, tzinfo=tz)
    if end <= local:
        end += timedelta(days=1)
    return end


async def process_reminders():
    t = now()
    async for r in db.reminders.find({"status": {"$in": ["pending", "snoozed"]}, "deliver_at": {"$lte": iso(t)}}, NOID).limit(200):
        user = await db.users.find_one({"user_id": r["user_id"]}, {"_id": 0, "password_hash": 0})
        if not user:
            continue
        q = quiet_until(user, t)
        if q:
            await db.reminders.update_one({"reminder_id": r["reminder_id"]}, {"$set": {"deliver_at": iso(q)}})
            continue
        link = f"/app/tracker?app={r['application_id']}" if r.get("application_id") else "/app/reminders"
        await notify(user["user_id"], r["title"], link=link, kind="reminder")
        channels = ["in_app"]
        plan = await get_plan(user)
        if plan["features"].get("whatsapp") and user.get("whatsapp_opt_in") and user.get("whatsapp_phone"):
            from wa import wa_send_template, TPL_REMINDER
            if await wa_send_template(user["whatsapp_phone"], TPL_REMINDER, [r["title"]], user.get("lang", "en")):
                channels.append("whatsapp")
        if plan["features"].get("email_reminders") and user.get("consents", {}).get("email_messaging"):
            ar = user.get("lang") == "ar"
            if await send_email(to=user["email"], subject=f"JobPilot: {r['title']}", html=email_layout(
                    "تذكير" if ar else "Reminder", [r["title"]], "فتح JobPilot" if ar else "Open JobPilot", link, rtl=ar)):
                channels.append("email")
        await db.reminders.update_one({"reminder_id": r["reminder_id"]}, {"$set": {"status": "sent", "sent_at": iso(), "channels": channels}})


async def ghost_check():
    async for a in db.applications.find({"status": "applied", "ghost_suggested": False}, NOID):
        user = await db.users.find_one({"user_id": a["user_id"]}, {"_id": 0, "ghost_days": 1})
        if user and parse_dt(a["updated_at"]) < now() - timedelta(days=user.get("ghost_days", 21)):
            await db.applications.update_one({"application_id": a["application_id"]}, {"$set": {"ghost_suggested": True}})
            await notify(a["user_id"], f"No reply from {a['company']} — mark as Ghosted?", link=f"/app/tracker?app={a['application_id']}", kind="ghost")


# ---------- notifications & dashboard ----------
@router.get("/notifications")
async def notifications(user=Depends(get_current_user)):
    items = await db.notifications.find({"user_id": user["user_id"]}, NOID).sort("created_at", -1).to_list(50)
    return {"items": items, "unread": sum(1 for i in items if not i["read"])}


@router.post("/notifications/read-all")
async def read_all(user=Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["user_id"]}, {"$set": {"read": True}})
    return {"ok": True}


@router.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    apps = await db.applications.find({"user_id": user["user_id"]}, {"_id": 0, "timeline": 0, "notes": 0}).to_list(2000)
    reached = lambda a, s: bool(set(a.get("reached", [])) & s) or a["status"] in s
    applied = [a for a in apps if reached(a, APPLIED_LIKE)]
    interviews = [a for a in apps if reached(a, {"interview", "offer"})]
    responded = [a for a in applied if reached(a, {"interview", "offer", "rejected"})]
    offers = [a for a in apps if reached(a, {"offer"})]
    by_src = {}
    for a in applied:
        s = by_src.setdefault(a.get("source", "manual"), {"source": a.get("source", "manual"), "applied": 0, "interviews": 0})
        s["applied"] += 1
        s["interviews"] += 1 if a in interviews else 0
    tz = ZoneInfo(user.get("timezone") or "Asia/Riyadh")
    local = now().astimezone(tz)
    week_start = datetime.combine((local - timedelta(days=(local.weekday() + 1) % 7)).date(), dtime(0), tzinfo=tz)
    this_week = sum(1 for a in apps if a.get("applied_at") and parse_dt(a["applied_at"]) >= week_start)
    upcoming = sorted([a for a in apps if a.get("interview_at") and parse_dt(a["interview_at"]) > now()], key=lambda a: a["interview_at"])[:5]
    rems = await db.reminders.find({"user_id": user["user_id"], "status": {"$in": ["pending", "snoozed", "sent"]}}, NOID).sort("due_at", 1).to_list(8)
    recent = await db.reviews.find({"user_id": user["user_id"]}, {"_id": 0, "job_id": 1, "result.score": 1, "result.verdict": 1, "created_at": 1}).sort("created_at", -1).to_list(6)
    for r in recent:
        j = await db.jobs.find_one({"job_id": r["job_id"]}, {"_id": 0, "title": 1, "company": 1})
        r.update(j or {})
    pct = lambda n, d: round(100 * n / d) if d else 0
    return {"funnel": [{"stage": "saved", "count": len(apps)}, {"stage": "applied", "count": len(applied)},
                       {"stage": "interview", "count": len(interviews)}, {"stage": "offer", "count": len(offers)}],
            "by_status": {s: sum(1 for a in apps if a["status"] == s) for s in STATUSES},
            "response_rate": pct(len(responded), len(applied)), "interview_rate": pct(len(interviews), len(applied)),
            "sources": sorted(by_src.values(), key=lambda s: (-s["interviews"], -s["applied"])),
            "weekly": {"goal": user.get("weekly_goal", 10), "done": this_week},
            "upcoming_interviews": [{k: a.get(k) for k in ("application_id", "title", "company", "interview_at")} for a in upcoming],
            "reminders": rems, "recent_reviews": recent,
            "ghost_suggestions": [{k: a.get(k) for k in ("application_id", "title", "company")} for a in apps if a.get("ghost_suggested")]}
