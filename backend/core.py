import os
import re
import uuid
import asyncio
import logging
import ipaddress
from pathlib import Path
from datetime import datetime, timezone, timedelta
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import bcrypt
import jwt
import httpx
import requests
from fastapi import Request, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from cryptography.fernet import Fernet

logger = logging.getLogger("jobpilot")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
fernet = Fernet(os.environ["ENCRYPTION_KEY"].encode())
JWT_SECRET = os.environ["JWT_SECRET"]
APP_URL = os.environ["FRONTEND_URL"].rstrip("/")
APP_NAME = "jobpilot"
NOID = {"_id": 0}
USER_PROJ = {"_id": 0, "password_hash": 0}


def now():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or now()).astimezone(timezone.utc).isoformat()


def parse_dt(v):
    if not v:
        return None
    d = v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def norm_iso(v):
    d = parse_dt(v)
    return iso(d) if d else None


def uid(prefix=""):
    return f"{prefix}{uuid.uuid4().hex[:16]}"


def client_ip(request: Request):
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "").split(",")[0].strip()


def encrypt_str(s: str) -> str:
    return fernet.encrypt(s.encode()).decode()


def decrypt_str(s: str) -> str:
    return fernet.decrypt(s.encode()).decode()


# ---------- auth ----------
def hash_password(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p, h):
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False


def make_token(sub, kind, ttl):
    return jwt.encode({"sub": sub, "type": kind, "exp": now() + ttl}, JWT_SECRET, algorithm="HS256")


# Auth cookies are cross-site (frontend :3000 -> API :8000), which browsers only accept with
# Secure + SameSite=None. Over plain HTTP -- i.e. local dev, which is most of this project's
# run setups -- such a cookie is dropped, so every authenticated call 401s. COOKIE_SECURE=0
# downgrades to SameSite=Lax, which still works because both ports share the same site.
# Leave it at the default (1) for any real deployment, which is served over HTTPS.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1").strip().lower() not in ("0", "false", "no", "off")
COOKIE_OPTS = dict(httponly=True, secure=COOKIE_SECURE, samesite="none" if COOKIE_SECURE else "lax", path="/")


def set_auth_cookies(resp, user_id):
    resp.set_cookie("access_token", make_token(user_id, "access", timedelta(minutes=15)), max_age=900, **COOKIE_OPTS)
    resp.set_cookie("refresh_token", make_token(user_id, "refresh", timedelta(days=7)), max_age=604800, **COOKIE_OPTS)


def clear_auth_cookies(resp):
    for k in ("access_token", "refresh_token", "session_token"):
        resp.delete_cookie(k, path="/", secure=COOKIE_SECURE,
                           samesite="none" if COOKIE_SECURE else "lax")


async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    bearer = auth[7:] if auth.startswith("Bearer ") else None
    user_id = None
    for t in filter(None, [request.cookies.get("access_token"), bearer]):
        try:
            p = jwt.decode(t, JWT_SECRET, algorithms=["HS256"])
            if p.get("type") == "access":
                user_id = p["sub"]
                break
        except jwt.InvalidTokenError:
            pass
    if not user_id:
        st = request.cookies.get("session_token") or bearer
        if st:
            s = await db.user_sessions.find_one({"session_token": st}, NOID)
            if s and parse_dt(s["expires_at"]) > now():
                user_id = s["user_id"]
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    user = await db.users.find_one({"user_id": user_id}, USER_PROJ)
    if not user:
        raise HTTPException(401, "User not found")
    if user.get("suspended"):
        raise HTTPException(403, "Account suspended")
    return user


async def require_admin(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return user


# ---------- plans & usage ----------
DEFAULT_PLANS = [
    {"plan_id": "free", "name": "Free", "price_usd": 0, "price_sar": 0, "order": 0,
     "limits": {"reviews": 10, "tailors": 2, "cvs": 1, "applications": 25},
     "features": {"email_reminders": False, "gmail": False, "whatsapp": False, "auto_review": False, "priority_ai": False}},
    {"plan_id": "pro", "name": "Pro", "price_usd": 12, "price_sar": 45, "order": 1,
     "limits": {"reviews": 150, "tailors": 30, "cvs": 5, "applications": -1},
     "features": {"email_reminders": True, "gmail": True, "whatsapp": False, "auto_review": True, "priority_ai": False}},
    {"plan_id": "premium", "name": "Premium", "price_usd": 25, "price_sar": 95, "order": 2,
     "limits": {"reviews": 500, "tailors": 100, "cvs": 10, "applications": -1},
     "features": {"email_reminders": True, "gmail": True, "whatsapp": True, "auto_review": True, "priority_ai": True}},
]
USAGE_FOR = {"reviews": "reviews", "tailors": "tailors", "cvs": "parses"}


def period():
    return now().strftime("%Y-%m")


async def get_plan(user):
    pid = user.get("plan", "free")
    if user.get("role") == "admin":
        pid = "premium"
    elif user.get("plan_expires_at") and parse_dt(user["plan_expires_at"]) < now():
        pid = "free"
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"plan": "free", "plan_expires_at": None}})
    return await db.plans.find_one({"plan_id": pid}, NOID) or DEFAULT_PLANS[0]


async def usage_of(user_id):
    u = await db.usage.find_one({"user_id": user_id, "period": period()}, NOID) or {}
    return {k: u.get(k, 0) for k in ("reviews", "tailors", "parses")}


async def check_limit(user, kind):
    plan = await get_plan(user)
    limit = plan["limits"].get(kind, -1)
    if limit < 0:
        return
    if kind == "applications":
        used = await db.applications.count_documents({"user_id": user["user_id"]})
    else:
        used = (await usage_of(user["user_id"]))[USAGE_FOR[kind]]
    if used >= limit:
        raise HTTPException(402, {"code": "limit_reached", "kind": kind, "limit": limit, "plan": plan["plan_id"]})


async def inc_usage(user_id, kind):
    await db.usage.update_one({"user_id": user_id, "period": period()}, {"$inc": {kind: 1}}, upsert=True)


async def audit(user_id, action, meta=None, actor_id=None, ip=None):
    await db.audit_logs.insert_one({"log_id": uid("log_"), "user_id": user_id, "actor_id": actor_id or user_id,
                                    "action": action, "meta": meta or {}, "ip": ip, "created_at": iso()})


async def notify(user_id, title, body="", link="", kind="info"):
    await db.notifications.insert_one({"notification_id": uid("ntf_"), "user_id": user_id, "title": title, "body": body,
                                       "link": link, "kind": kind, "read": False, "created_at": iso()})


# ---------- object storage (encrypted at rest) ----------
# Two backends: the Emergent object store (hosted) and a local disk directory (offline dev).
# Pick with LOCAL_STORAGE=1. Files are always Fernet-encrypted before they hit either backend.
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
_storage_key = None

LOCAL_STORAGE = os.environ.get("LOCAL_STORAGE", "").strip().lower() in ("1", "true", "yes", "on")
LOCAL_STORAGE_DIR = Path(__file__).parent / (os.environ.get("LOCAL_STORAGE_DIR", ".local_storage").strip() or ".local_storage")
StorageUnavailable = RuntimeError("Object storage is not reachable (Emergent object store unavailable and "
                                  "LOCAL_STORAGE is off). Set LOCAL_STORAGE=1 to store files on local disk.")


def init_storage(force=False):
    global _storage_key
    if LOCAL_STORAGE:
        LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        return "local"
    if _storage_key and not force:
        return _storage_key
    r = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ.get("EMERGENT_LLM_KEY", "")}, timeout=30)
    r.raise_for_status()
    _storage_key = r.json()["storage_key"]
    return _storage_key


def _local_path(path):
    # Object keys come from this app only, but resolve-and-check anyway so a stored key can
    # never escape the storage directory.
    p = (LOCAL_STORAGE_DIR / path).resolve()
    if not str(p).startswith(str(LOCAL_STORAGE_DIR.resolve())):
        raise StorageUnavailable(f"Refusing to read outside local storage: {path}")
    return p


def _put(path, data, ctype):
    if LOCAL_STORAGE:
        init_storage()
        p = _local_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return {"path": path}
    r = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(), "Content-Type": ctype}, data=data, timeout=120)
    if r.status_code == 404:
        r = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(True), "Content-Type": ctype}, data=data, timeout=120)
    r.raise_for_status()
    return r.json()


def _get(path):
    if LOCAL_STORAGE:
        init_storage()
        p = _local_path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Object not found in local storage: {path}")
        return p.read_bytes()
    r = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage()}, timeout=60)
    r.raise_for_status()
    return r.content


async def put_file(user_id, data: bytes, filename, content_type, kind="document", meta=None):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    path = f"{APP_NAME}/users/{user_id}/{uuid.uuid4().hex}.{ext}.enc"
    res = await asyncio.to_thread(_put, path, fernet.encrypt(data), "application/octet-stream")
    doc = {"file_id": uid("file_"), "user_id": user_id, "storage_path": res["path"], "filename": filename,
           "content_type": content_type, "size": len(data), "kind": kind, "meta": meta or {}, "is_deleted": False, "created_at": iso()}
    await db.files.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_file(file_id, user_id=None):
    q = {"file_id": file_id, "is_deleted": False}
    if user_id:
        q["user_id"] = user_id
    doc = await db.files.find_one(q, NOID)
    if not doc:
        raise HTTPException(404, "File not found")
    raw = await asyncio.to_thread(_get, doc["storage_path"])
    return fernet.decrypt(raw), doc


# ---------- email (Emergent managed) ----------
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ["EMERGENT_EMAIL_KEY"]
EMAIL_FROM_NAME = os.environ["EMAIL_FROM_NAME"]
_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv", "send us your password",
             "enter your password below", "confirm your card number", "your full card number", "seed phrase",
             "recovery phrase", "verify your card", "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host):
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown, real):
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors, self._href, self._text = set(), [], [], None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject, html):
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Links must be absolute https: {url!r} (G3)")
        if not _host_ok(urlparse(low).hostname or "") or urlparse(low).username is not None:
            raise ValueError(f"Unsafe URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text host mismatch (G3)")


async def send_email(*, to, subject, html):
    _assert_safe_email(subject, html)
    payload = {"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{EMAIL_BASE_URL}/api/v1/email/send", headers={"X-Email-Key": EMAIL_KEY}, json=payload)
        r.raise_for_status()
        return r.json().get("id")
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return None


def email_layout(title, lines, cta_text=None, cta_path="/app", rtl=False):
    d = "rtl" if rtl else "ltr"
    align = "right" if rtl else "left"
    body = "".join(f'<p style="margin:0 0 12px">{escape(line)}</p>' for line in lines)
    cta = (f'<p><a href="{APP_URL}{cta_path}" style="background:#064E3B;color:#fff;padding:10px 18px;border-radius:6px;'
           f'text-decoration:none;display:inline-block">{escape(cta_text)}</a></p>') if cta_text else ""
    return (f'<table role="presentation" width="100%" dir="{d}"><tr><td style="padding:24px;font-family:Arial,sans-serif;'
            f'color:#0F172A;text-align:{align}"><h2 style="margin:0 0 16px;color:#064E3B">{escape(title)}</h2>{body}{cta}'
            f'<p style="font-size:12px;color:#94A3B8;margin-top:24px">Sent by {escape(EMAIL_FROM_NAME)}. '
            f'We never ask for your password or card details by email.</p></td></tr></table>')
