from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from core import db, iso, uid, NOID, get_current_user, require_admin, audit, notify, client_ip
from r_apps import event, STATUSES

router = APIRouter(prefix="/api")


class GrantIn(BaseModel):
    coach_email: EmailStr


@router.post("/coach/grant")
async def grant(body: GrantIn, request: Request, user=Depends(get_current_user)):
    coach = await db.users.find_one({"email": body.coach_email.lower()}, {"_id": 0, "user_id": 1, "name": 1})
    if not coach:
        raise HTTPException(404, "No JobPilot account with that email")
    if coach["user_id"] == user["user_id"]:
        raise HTTPException(400, "You cannot coach yourself")
    await db.coach_links.update_one({"coach_id": coach["user_id"], "candidate_id": user["user_id"]},
                                    {"$setOnInsert": {"link_id": uid("cl_"), "created_at": iso()}}, upsert=True)
    await db.consents.insert_one({"user_id": user["user_id"], "type": "coach_access", "granted": True, "meta": {"coach_id": coach["user_id"]}, "ip": client_ip(request), "created_at": iso()})
    await notify(coach["user_id"], f"{user['name']} shared their job search with you", link="/app/coach", kind="coach")
    await audit(user["user_id"], "coach_access_granted", {"coach_id": coach["user_id"]})
    return {"ok": True}


@router.delete("/coach/grant/{coach_id}")
async def revoke(coach_id: str, user=Depends(get_current_user)):
    await db.coach_links.delete_one({"coach_id": coach_id, "candidate_id": user["user_id"]})
    await audit(user["user_id"], "coach_access_revoked", {"coach_id": coach_id})
    return {"ok": True}


async def _people(ids):
    return {u["user_id"]: u async for u in db.users.find({"user_id": {"$in": ids}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1})}


@router.get("/coach/overview")
async def overview(user=Depends(get_current_user)):
    mine = await db.coach_links.find({"candidate_id": user["user_id"]}, NOID).to_list(20)
    cands = await db.coach_links.find({"coach_id": user["user_id"]}, NOID).to_list(200)
    people = await _people([l["coach_id"] for l in mine] + [l["candidate_id"] for l in cands])
    candidates = []
    for l in cands:
        apps = await db.applications.find({"user_id": l["candidate_id"]}, {"_id": 0, "status": 1, "updated_at": 1}).to_list(2000)
        candidates.append({**people.get(l["candidate_id"], {}), "by_status": {s: sum(1 for a in apps if a["status"] == s) for s in STATUSES},
                           "last_activity": max((a["updated_at"] for a in apps), default=None)})
    return {"coaches": [people.get(l["coach_id"], {"user_id": l["coach_id"]}) for l in mine], "candidates": candidates}


async def _require_link(coach_id, cid):
    if not await db.coach_links.find_one({"coach_id": coach_id, "candidate_id": cid}):
        raise HTTPException(403, "No access to this candidate")


@router.get("/coach/candidates/{cid}/applications")
async def cand_apps(cid: str, user=Depends(get_current_user)):
    await _require_link(user["user_id"], cid)
    return await db.applications.find({"user_id": cid}, {"_id": 0, "timeline": 0, "contacts": 0, "documents": 0, "prep": 0}).sort("updated_at", -1).to_list(500)


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/coach/candidates/{cid}/applications/{aid}/comments")
async def comment(cid: str, aid: str, body: CommentIn, user=Depends(get_current_user)):
    await _require_link(user["user_id"], cid)
    c = {"comment_id": uid("cm_"), "coach_id": user["user_id"], "coach_name": user["name"], "text": body.text, "created_at": iso()}
    res = await db.applications.update_one({"application_id": aid, "user_id": cid}, {"$push": {"coach_comments": c, "timeline": event("coach", f"Coach {user['name']} commented")}})
    if not res.matched_count:
        raise HTTPException(404, "Application not found")
    await notify(cid, f"New comment from your coach {user['name']}", link=f"/app/tracker?app={aid}", kind="coach")
    return c


@router.get("/admin/insights")
async def insights(admin=Depends(require_admin)):
    from core import parse_dt
    apps = await db.applications.find({"applied_at": {"$ne": None}}, {"_id": 0, "applied_at": 1, "reached": 1, "status": 1, "source": 1}).to_list(20000)
    days = [{"day": d, "applied": 0, "responded": 0} for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")]
    src = {}
    for a in apps:
        responded = bool({"interview", "offer", "rejected"} & set(a.get("reached") or [a["status"]]))
        d = days[parse_dt(a["applied_at"]).weekday()]
        d["applied"] += 1
        d["responded"] += responded
        s = src.setdefault(a.get("source", "manual"), {"source": a.get("source", "manual"), "applied": 0, "responded": 0})
        s["applied"] += 1
        s["responded"] += responded
    rate = lambda x: {**x, "rate": round(100 * x["responded"] / x["applied"]) if x["applied"] else 0}
    return {"total_applied": len(apps), "by_weekday": [rate(d) for d in days], "by_source": sorted([rate(s) for s in src.values()], key=lambda s: -s["rate"])}
