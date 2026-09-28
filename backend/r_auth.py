import secrets
from datetime import timedelta
import httpx
import jwt
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from core import (db, iso, now, parse_dt, uid, NOID, USER_PROJ, hash_password, verify_password, make_token, set_auth_cookies,
                  clear_auth_cookies, get_current_user, audit, client_ip, JWT_SECRET, COOKIE_OPTS, send_email, email_layout,
                  get_plan, usage_of, put_file, get_file)
from ai import generate_image

router = APIRouter(prefix="/api")


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=120)
    lang: str = "en"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def new_user_doc(email, name, **kw):
    doc = {"user_id": uid("user_"), "workspace_id": uid("ws_"), "email": email, "name": name, "picture": "", "role": "user",
           "plan": "free", "lang": "en", "country": "SA", "city": "", "timezone": "Asia/Riyadh", "quiet_start": "22:00",
           "quiet_end": "08:00", "weekly_goal": 10, "followup_days": 7, "ghost_days": 21, "onboarded": False, "suspended": False,
           "gmail_connected": False, "consents": {}, "created_at": iso()}
    doc.update(kw)
    return doc


async def create_user(doc):
    trial = (await db.settings.find_one({"key": "trial"}, NOID) or {}).get("value") or {}
    if doc.get("role") != "admin" and trial.get("days", 0) > 0 and trial.get("plan") in ("pro", "premium"):
        doc.update(plan=trial["plan"], plan_expires_at=iso(now() + timedelta(days=int(trial["days"]))), trial=True)
    await db.users.insert_one(doc)
    await db.workspaces.insert_one({"workspace_id": doc["workspace_id"], "owner_id": doc["user_id"], "type": "personal", "created_at": iso()})


async def me_payload(user_id):
    user = await db.users.find_one({"user_id": user_id}, USER_PROJ)
    user["plan_info"] = await get_plan(user)
    user["usage"] = await usage_of(user_id)
    return user


@router.post("/auth/register")
async def register(body: RegisterIn, request: Request, response: Response):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Email already registered")
    doc = new_user_doc(email, body.name.strip(), password_hash=hash_password(body.password), lang=body.lang if body.lang in ("en", "ar") else "en")
    await create_user(doc)
    set_auth_cookies(response, doc["user_id"])
    await audit(doc["user_id"], "register", ip=client_ip(request))
    return await me_payload(doc["user_id"])


@router.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.lower()
    ident = f"{client_ip(request)}:{email}"
    att = await db.login_attempts.find_one({"identifier": ident}, NOID)
    if att and att.get("locked_until") and parse_dt(att["locked_until"]) > now():
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        count = (att or {}).get("count", 0) + 1
        upd = {"count": count, "updated_at": iso()}
        if count >= 5:
            upd = {"count": 0, "locked_until": iso(now() + timedelta(minutes=15))}
        await db.login_attempts.update_one({"identifier": ident}, {"$set": upd}, upsert=True)
        raise HTTPException(401, "Invalid email or password")
    if user.get("suspended"):
        raise HTTPException(403, "Account suspended")
    await db.login_attempts.delete_one({"identifier": ident})
    set_auth_cookies(response, user["user_id"])
    await audit(user["user_id"], "login", {"method": "password"}, ip=client_ip(request))
    return await me_payload(user["user_id"])


class GoogleIn(BaseModel):
    session_id: str


@router.post("/auth/google/session")
async def google_session(body: GoogleIn, request: Request, response: Response):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get("https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data", headers={"X-Session-ID": body.session_id})
    if r.status_code != 200:
        raise HTTPException(401, "Google sign-in failed")
    data = r.json()
    email = data["email"].lower()
    user = await db.users.find_one({"email": email}, NOID)
    if not user:
        user = new_user_doc(email, data.get("name") or email.split("@")[0], picture=data.get("picture", ""))
        await create_user(user)
    elif user.get("suspended"):
        raise HTTPException(403, "Account suspended")
    elif not user.get("picture") and data.get("picture"):
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"picture": data["picture"]}})
    await db.user_sessions.insert_one({"user_id": user["user_id"], "session_token": data["session_token"],
                                       "expires_at": iso(now() + timedelta(days=7)), "created_at": iso()})
    response.set_cookie("session_token", data["session_token"], max_age=604800, **COOKIE_OPTS)
    set_auth_cookies(response, user["user_id"])
    await audit(user["user_id"], "login", {"method": "google"}, ip=client_ip(request))
    return await me_payload(user["user_id"])


@router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    tok = request.cookies.get("refresh_token")
    try:
        p = jwt.decode(tok or "", JWT_SECRET, algorithms=["HS256"])
        assert p.get("type") == "refresh"
    except Exception:
        raise HTTPException(401, "Invalid refresh token")
    response.set_cookie("access_token", make_token(p["sub"], "access", timedelta(minutes=15)), max_age=900, **COOKIE_OPTS)
    return {"ok": True}


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    st = request.cookies.get("session_token")
    if st:
        await db.user_sessions.delete_one({"session_token": st})
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return await me_payload(user["user_id"])


class ForgotIn(BaseModel):
    email: EmailStr


@router.post("/auth/forgot-password")
async def forgot(body: ForgotIn):
    user = await db.users.find_one({"email": body.email.lower()}, NOID)
    if user and user.get("password_hash"):
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({"token": token, "user_id": user["user_id"], "used": False,
                                                   "expires_at": iso(now() + timedelta(hours=1))})
        ar = user.get("lang") == "ar"
        await send_email(to=user["email"], subject="إعادة تعيين كلمة المرور" if ar else "Reset your JobPilot password",
                         html=email_layout("إعادة تعيين كلمة المرور" if ar else "Reset your password",
                                           ["الرابط صالح لمدة ساعة واحدة." if ar else "This link is valid for one hour. Ignore this email if you did not request it."],
                                           "تعيين كلمة مرور جديدة" if ar else "Set a new password", f"/reset-password?token={token}", rtl=ar))
    return {"ok": True}


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=8)


@router.post("/auth/reset-password")
async def reset(body: ResetIn):
    t = await db.password_reset_tokens.find_one({"token": body.token}, NOID)
    if not t or t["used"] or parse_dt(t["expires_at"]) < now():
        raise HTTPException(400, "Invalid or expired link")
    await db.users.update_one({"user_id": t["user_id"]}, {"$set": {"password_hash": hash_password(body.password)}})
    await db.password_reset_tokens.update_one({"token": body.token}, {"$set": {"used": True}})
    await audit(t["user_id"], "password_reset")
    return {"ok": True}


class ProfileIn(BaseModel):
    name: Optional[str] = None
    lang: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    timezone: Optional[str] = None
    quiet_start: Optional[str] = None
    quiet_end: Optional[str] = None
    weekly_goal: Optional[int] = Field(None, ge=1, le=100)
    followup_days: Optional[int] = Field(None, ge=1, le=60)
    ghost_days: Optional[int] = Field(None, ge=7, le=120)


@router.patch("/me")
async def update_me(body: ProfileIn, user=Depends(get_current_user)):
    upd = body.model_dump(exclude_none=True)
    if upd:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    return await me_payload(user["user_id"])


class OnboardIn(ProfileIn):
    consents: dict


@router.post("/onboarding")
async def onboarding(body: OnboardIn, request: Request, user=Depends(get_current_user)):
    c = body.consents
    if not c.get("terms") or not c.get("ai_processing"):
        raise HTTPException(400, "Terms and AI-processing consent are required")
    upd = body.model_dump(exclude_none=True, exclude={"consents"})
    consents = {k: bool(c.get(k)) for k in ("terms", "ai_processing", "email_messaging")}
    for k, v in consents.items():
        await db.consents.insert_one({"user_id": user["user_id"], "type": k, "granted": v, "ip": client_ip(request), "created_at": iso()})
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {**upd, "consents": consents, "onboarded": True}})
    await audit(user["user_id"], "onboarding_completed", consents)
    return await me_payload(user["user_id"])


class AvatarIn(BaseModel):
    style: str = "minimal flat illustration"


@router.post("/me/avatar")
async def gen_avatar(body: AvatarIn, user=Depends(get_current_user)):
    initials = "".join(w[0] for w in user["name"].split()[:2]).upper()
    prompt = (f"A professional, friendly profile avatar for a job seeker's CV platform. Style: {body.style[:80]}. "
              f"Abstract geometric portrait silhouette, deep emerald and warm sand palette, subtle monogram '{initials}', "
              "clean background, centered, square composition, no text other than the monogram.")
    try:
        data, mime = await generate_image(prompt)
    except Exception as e:
        raise HTTPException(502, f"Image generation failed: {str(e)[:120]}")
    f = await put_file(user["user_id"], data, "avatar.png", mime, kind="avatar")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"avatar_file_id": f["file_id"]}})
    return {"avatar_file_id": f["file_id"]}


@router.get("/me/avatar")
async def get_avatar(user=Depends(get_current_user)):
    from fastapi.responses import Response as R
    if not user.get("avatar_file_id"):
        raise HTTPException(404, "No avatar")
    data, doc = await get_file(user["avatar_file_id"], user["user_id"])
    return R(content=data, media_type=doc["content_type"])
