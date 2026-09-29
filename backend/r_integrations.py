import os
import base64
import secrets
import warnings
from datetime import timedelta
from email.message import EmailMessage
import stripe
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from typing import Optional
from core import (db, iso, now, parse_dt, uid, NOID, get_current_user, get_plan, usage_of, audit, encrypt_str, decrypt_str, integration_secrets, integration_value,
                  APP_URL, DEFAULT_PLANS)
from r_apps import get_app, event, get_tl, render_export

router = APIRouter(prefix="/api")

# ---------- Gmail (drafts + send only; inbox scanning is Phase 2) ----------
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose", "openid", "https://www.googleapis.com/auth/userinfo.email"]
REDIRECT_URI = f"{APP_URL}/api/oauth/gmail/callback"


async def _google_creds():
    """OAuth client credentials, resolved per call from the admin secret store then the env."""
    stored = await integration_secrets()
    return (await integration_value("GOOGLE_CLIENT_ID", stored), await integration_value("GOOGLE_CLIENT_SECRET", stored))


async def _moyasar_creds():
    stored = await integration_secrets()
    return (await integration_value("MOYASAR_PUBLISHABLE_KEY", stored), await integration_value("MOYASAR_SECRET_KEY", stored),
            (await integration_value("MOYASAR_APPLE_PAY", stored)) == "1")


async def _stripe_creds():
    stored = await integration_secrets()
    return (await integration_value("STRIPE_SECRET_KEY", stored), await integration_value("STRIPE_WEBHOOK_SECRET", stored))


def _flow(client_id, client_secret):
    from google_auth_oauthlib.flow import Flow
    return Flow.from_client_config({"web": {"client_id": client_id, "client_secret": client_secret,
                                            "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}},
                                   scopes=GMAIL_SCOPES, redirect_uri=REDIRECT_URI)


@router.get("/gmail/status")
async def gmail_status(user=Depends(get_current_user)):
    tok = await db.gmail_tokens.find_one({"user_id": user["user_id"]}, {"_id": 0, "email": 1, "created_at": 1})
    plan = await get_plan(user)
    client_id, client_secret = await _google_creds()
    return {"configured": bool(client_id and client_secret), "connected": bool(tok), "email": (tok or {}).get("email"),
            "plan_allows": plan["features"].get("gmail", False)}


@router.get("/gmail/connect")
async def gmail_connect(user=Depends(get_current_user)):
    client_id, client_secret = await _google_creds()
    if not (client_id and client_secret):
        raise HTTPException(503, "Gmail is not configured yet")
    if not (await get_plan(user))["features"].get("gmail"):
        raise HTTPException(402, {"code": "feature_locked", "kind": "gmail"})
    url, state = _flow(client_id, client_secret).authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    await db.oauth_states.insert_one({"state": state, "user_id": user["user_id"], "expires_at": iso(now() + timedelta(minutes=10))})
    return {"url": url}


@router.get("/oauth/gmail/callback")
async def gmail_callback(code: str = "", state: str = "", error: str = ""):
    st = await db.oauth_states.find_one_and_delete({"state": state})
    if error or not st or parse_dt(st["expires_at"]) < now():
        return RedirectResponse(f"{APP_URL}/app/settings?gmail=error")
    flow = _flow(*await _google_creds())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
        flow.fetch_token(code=code)
    c = flow.credentials
    email = ""
    try:
        from googleapiclient.discovery import build
        email = build("oauth2", "v2", credentials=c).userinfo().get().execute().get("email", "")
    except Exception:
        pass
    enc = encrypt_str(c.to_json())
    await db.gmail_tokens.replace_one({"user_id": st["user_id"]}, {"user_id": st["user_id"], "enc": enc, "email": email, "created_at": iso()}, upsert=True)
    await db.users.update_one({"user_id": st["user_id"]}, {"$set": {"gmail_connected": True}})
    await db.consents.insert_one({"user_id": st["user_id"], "type": "gmail_send", "granted": True, "created_at": iso()})
    await audit(st["user_id"], "gmail_connected", {"email": email})
    return RedirectResponse(f"{APP_URL}/app/settings?gmail=connected")


@router.post("/gmail/disconnect")
async def gmail_disconnect(user=Depends(get_current_user)):
    await db.gmail_tokens.delete_one({"user_id": user["user_id"]})
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"gmail_connected": False}})
    await audit(user["user_id"], "gmail_disconnected")
    return {"ok": True}


def _gmail_service(enc):
    import json
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GReq
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_info(json.loads(decrypt_str(enc)), GMAIL_SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(GReq())
    return build("gmail", "v1", credentials=creds, cache_discovery=False), creds


class ComposeIn(BaseModel):
    application_id: str
    to: str = Field(min_length=3, max_length=200)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    tailored_id: Optional[str] = None
    attach: str = "pdf"
    mode: str = "draft"


@router.post("/gmail/compose")
async def gmail_compose(body: ComposeIn, user=Depends(get_current_user)):
    tok = await db.gmail_tokens.find_one({"user_id": user["user_id"]}, NOID)
    if not tok:
        raise HTTPException(400, "Connect Gmail first")
    app = await get_app(body.application_id, user["user_id"])
    msg = EmailMessage()
    msg["To"], msg["Subject"] = body.to, body.subject
    msg.set_content(body.body)
    if body.tailored_id:
        t = await get_tl(body.tailored_id, user["user_id"])
        if t["status"] != "approved":
            raise HTTPException(400, "Only approved CVs can be attached")
        data, mime = render_export(t, "pdf" if body.attach == "pdf" else "docx", "cv")
        main, sub = mime.split("/", 1)
        msg.add_attachment(data, maintype=main, subtype=sub, filename=f"CV_{(t['cv'].get('name') or 'CV').replace(' ', '_')}.{body.attach}")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    svc, creds = _gmail_service(tok["enc"])
    try:
        if body.mode == "send":
            svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        else:
            svc.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    except Exception as e:
        raise HTTPException(502, f"Gmail error: {str(e)[:150]}")
    await db.gmail_tokens.update_one({"user_id": user["user_id"]}, {"$set": {"enc": encrypt_str(creds.to_json())}})
    kind = "email_sent" if body.mode == "send" else "email_draft"
    upd = {"$push": {"timeline": event(kind, f"{'Email sent' if body.mode == 'send' else 'Gmail draft created'} to {body.to}: {body.subject}")}}
    await db.applications.update_one({"application_id": app["application_id"]}, upd)
    await audit(user["user_id"], kind, {"application_id": app["application_id"], "to": body.to})
    return {"ok": True, "mode": body.mode}


# ---------- Moyasar (mada, Apple Pay, STC Pay) ----------
class MoyasarOrderIn(BaseModel):
    plan_id: str


@router.post("/billing/moyasar/order")
async def moyasar_order(body: MoyasarOrderIn, user=Depends(get_current_user)):
    moyasar_pk, moyasar_sk, apple_pay = await _moyasar_creds()
    if not (moyasar_pk and moyasar_sk):
        raise HTTPException(503, "payments_not_configured")
    plan = await db.plans.find_one({"plan_id": body.plan_id}, NOID)
    if not plan or plan["price_sar"] <= 0:
        raise HTTPException(400, "Invalid plan")
    order = {"order_id": uid("ord_"), "user_id": user["user_id"], "plan_id": plan["plan_id"], "amount": int(round(plan["price_sar"] * 100)),
             "currency": "SAR", "status": "pending", "provider": "moyasar", "created_at": iso()}
    await db.payment_transactions.insert_one(order)
    return {"order_id": order["order_id"], "amount": order["amount"], "currency": "SAR", "publishable_key": moyasar_pk,
            "description": f"JobPilot {plan['name']} — 1 month", "apple_pay": apple_pay}


@router.get("/billing/moyasar/verify")
async def moyasar_verify(id: str, order_id: str, user=Depends(get_current_user)):
    import httpx
    _, moyasar_sk, _ = await _moyasar_creds()
    order = await db.payment_transactions.find_one({"order_id": order_id, "user_id": user["user_id"]}, NOID)
    if not order:
        raise HTTPException(404, "Order not found")
    if order["status"] == "paid":
        return {"ok": True, "already_processed": True}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"https://api.moyasar.com/v1/payments/{id}", auth=(moyasar_sk, ""))
        r.raise_for_status()
        p = r.json()
    except Exception:
        raise HTTPException(502, "Unable to verify payment")
    if not (p.get("status") == "paid" and p.get("amount") == order["amount"] and p.get("currency") == order["currency"]):
        await db.payment_transactions.update_one({"order_id": order_id}, {"$set": {"status": p.get("status") or "failed", "updated_at": iso()}})
        raise HTTPException(400, "Payment was not accepted")
    if await db.payment_transactions.find_one({"moyasar_payment_id": p["id"]}):
        return {"ok": True, "already_processed": True}
    res = await db.payment_transactions.update_one({"order_id": order_id, "status": {"$ne": "paid"}},
                                                   {"$set": {"status": "paid", "payment_status": "paid", "moyasar_payment_id": p["id"], "updated_at": iso()}})
    if res.modified_count:
        u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "plan": 1, "plan_expires_at": 1})
        start = parse_dt(u.get("plan_expires_at")) if u.get("plan") == order["plan_id"] and u.get("plan_expires_at") and parse_dt(u["plan_expires_at"]) > now() else now()
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"plan": order["plan_id"], "plan_expires_at": iso(start + timedelta(days=30))}})
        await audit(user["user_id"], "plan_purchased", {"plan": order["plan_id"], "provider": "moyasar", "amount": order["amount"]})
    return {"ok": True, "already_processed": res.modified_count == 0}


# ---------- Billing (Stripe) ----------
@router.get("/billing/plans")
async def plans(user=Depends(get_current_user)):
    items = await db.plans.find({}, NOID).sort("order", 1).to_list(10)
    eff = await get_plan(user)
    stripe_key, _ = await _stripe_creds()
    moyasar_pk, moyasar_sk, _ = await _moyasar_creds()
    return {"plans": items or DEFAULT_PLANS, "current": eff["plan_id"], "plan_expires_at": user.get("plan_expires_at") if user.get("role") != "admin" else None,
            "is_admin": user.get("role") == "admin", "usage": await usage_of(user["user_id"]),
            "applications": await db.applications.count_documents({"user_id": user["user_id"]}), "payments_enabled": bool(stripe_key),
            "moyasar_enabled": bool(moyasar_pk and moyasar_sk)}


class CheckoutIn(BaseModel):
    plan_id: str
    origin_url: str


async def _stripe_ready():
    """Load the Stripe key into the SDK at call time and return it ("" when unconfigured).

    The key can now be set from the dashboard, so it cannot be assigned once at import.
    """
    key, _ = await _stripe_creds()
    if key:
        stripe.api_key = key
    return key


@router.post("/billing/checkout")
async def checkout(body: CheckoutIn, user=Depends(get_current_user)):
    if not await _stripe_ready():
        raise HTTPException(503, "payments_not_configured")
    plan = await db.plans.find_one({"plan_id": body.plan_id}, NOID)
    if not plan or plan["price_usd"] <= 0:
        raise HTTPException(400, "Invalid plan")
    prices = stripe.Price.list(lookup_keys=[f"{body.plan_id}_monthly"], active=True, limit=1).data
    if not prices:
        raise HTTPException(500, "Price not found")
    session = stripe.checkout.Session.create(
        line_items=[{"price": prices[0].id, "quantity": 1}], mode="subscription", customer_email=user["email"],
        success_url=f"{body.origin_url}/app/billing?session_id={{CHECKOUT_SESSION_ID}}", cancel_url=f"{body.origin_url}/app/billing",
        metadata={"user_id": user["user_id"], "plan_id": body.plan_id})
    await db.payment_transactions.insert_one({"session_id": session.id, "user_id": user["user_id"], "plan_id": body.plan_id,
                                              "amount": float(plan["price_usd"]), "currency": "usd", "status": "initiated",
                                              "payment_status": "pending", "created_at": iso(), "updated_at": iso()})
    return {"checkout_url": session.url, "session_id": session.id}


async def _mark_paid(session_id, sub_id=None):
    res = await db.payment_transactions.find_one_and_update({"session_id": session_id, "payment_status": {"$ne": "paid"}},
                                                            {"$set": {"status": "completed", "payment_status": "paid", "stripe_subscription_id": sub_id, "updated_at": iso()}})
    if res:
        await db.users.update_one({"user_id": res["user_id"]}, {"$set": {"plan": res["plan_id"], "stripe_subscription_id": sub_id}})
        await audit(res["user_id"], "plan_upgraded", {"plan": res["plan_id"]})


@router.get("/billing/status/{session_id}")
async def pay_status(session_id: str):
    rec = await db.payment_transactions.find_one({"session_id": session_id}, NOID)
    if not rec:
        raise HTTPException(404, "Transaction not found")
    if rec["payment_status"] != "paid" and await _stripe_ready():
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            if s.payment_status == "paid" or s.status == "complete":
                await _mark_paid(session_id, s.subscription)
                rec = await db.payment_transactions.find_one({"session_id": session_id}, NOID)
        except stripe.error.StripeError:
            pass
    return {"session_id": rec["session_id"], "status": rec["status"], "payment_status": rec["payment_status"]}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    _, webhook_secret = await _stripe_creds()
    try:
        ev = stripe.Webhook.construct_event(payload, request.headers.get("stripe-signature", ""), webhook_secret)
    except Exception:
        raise HTTPException(400, "Invalid signature")
    obj = ev["data"]["object"]
    if ev["type"] == "checkout.session.completed":
        await _mark_paid(obj["id"], obj.get("subscription"))
    elif ev["type"] == "customer.subscription.deleted":
        await db.users.update_one({"stripe_subscription_id": obj["id"]}, {"$set": {"plan": "free"}})
    return {"status": "ok"}


# ---------- Gmail Inbox Scanning (Phase 2) ----------

async def _scan_gmail_inbox(user_id: str):
    """Scan Gmail inbox for interview-related emails and suggest status updates."""
    tok = await db.gmail_tokens.find_one({"user_id": user_id}, NOID)
    if not tok:
        return

    try:
        svc, creds = _gmail_service(tok["enc"])

        # Check if token needs refresh
        if not creds.valid and creds.refresh_token:
            creds.refresh(GReq())
            await db.gmail_tokens.update_one(
                {"user_id": user_id},
                {"$set": {"enc": encrypt_str(creds.to_json())}}
            )
            svc, _ = _gmail_service(tok["enc"])  # Recreate service with refreshed creds

        # Get user's applications to match against
        apps_cursor = db.applications.find(
            {"user_id": user_id, "status": {"$in": ["applied", "preparing"]}},
            {"_id": 0, "application_id": 1, "title": 1, "company": 1, "job_id": 1}
        )
        apps = {a["application_id"]: a async for a in apps_cursor}

        if not apps:
            return

        # Search for recent emails (last 24 hours) that might be interview-related
        query = (
            "in:inbox "
            "newer_than:1d "
            "(interview OR \"thank you\" OR \"next steps\" OR "
            "\"we were impressed\" OR \"move forward\" OR "
            "rejection OR \"not selected\" OR \"unfortunately\")"
        )

        results = svc.users().messages().list(userId="me", q=query, maxResults=20).execute()
        messages = results.get("messages", [])

        for msg in messages:
            # Get full message
            msg_data = svc.users().messages().get(userId="me", id=msg["id"], format="metadata",
                                                 metadataHeaders=["Subject", "From", "Date"]).execute()

            headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
            subject = headers.get("Subject", "").lower()
            sender = headers.get("From", "").lower()
            date_str = headers.get("Date", "")

            # Determine if this is interview-related and what status to suggest
            suggested_status = None
            if any(word in subject for word in ["interview", "talk", "chat", "meet"]):
                if any(word in subject for word in ["scheduled", "schedule", "book", "confirm"]):
                    suggested_status = "interview"
                elif any(word in subject for word in ["thank", "thanks", "appreciate"]):
                    suggested_status = "interview"  # Post-interview thank you
            elif any(word in subject for word in ["rejection", "not selected", "unfortunately",
                                                 "regret", "cannot offer", "position filled"]):
                suggested_status = "rejected"
            elif any(word in subject for word in ["offer", "congratulations", "pleased to offer"]):
                suggested_status = "offer"

            if suggested_status:
                # Find matching applications by company/job title similarity
                for app_id, app in apps.items():
                    company_match = (
                        app["company"].lower() in sender or
                        any(word in sender for word in app["company"].lower().split() if len(word) > 3) or
                        any(word in app["company"].lower() for word in sender.split() if len(word) > 3)
                    )

                    title_match = (
                        app["title"].lower() in subject or
                        any(word in subject for word in app["title"].lower().split() if len(word) > 3)
                    )

                    if company_match or title_match:
                        # Create a notification suggesting status update
                        await notify(
                            user_id,
                            f"Email suggests updating {app['company']} - {app['title']} to {suggested_status}",
                            link=f"/app/tracker?app={app_id}",
                            kind="gmail_suggestion"
                        )

                        # Add a timeline event to the application
                        await db.applications.update_one(
                            {"application_id": app_id},
                            {"$push": {
                                "timeline": event(
                                    "gmail_suggestion",
                                    f"Email suggested status update to {suggested_status}: {subject[:100]}..."
                                )
                            }}
                        )
                        break  # Only notify once per email

    except Exception as e:
        logger.error(f"Gmail inbox scan failed for user {user_id}: {e}")
        # Don't raise - we don't want to crash the scheduler


async def _scan_gmail_inbox_for_user(user_id: str):
    """Scan Gmail inbox for a specific user for interview-related emails and suggest status updates."""
    tok = await db.gmail_tokens.find_one({"user_id": user_id}, NOID)
    if not tok:
        return

    try:
        svc, creds = _gmail_service(tok["enc"])

        # Check if token needs refresh
        if not creds.valid and creds.refresh_token:
            creds.refresh(GReq())
            await db.gmail_tokens.update_one(
                {"user_id": user_id},
                {"$set": {"enc": encrypt_str(creds.to_json())}}
            )
            svc, _ = _gmail_service(tok["enc"])  # Recreate service with refreshed creds

        # Get user's applications to match against
        apps_cursor = db.applications.find(
            {"user_id": user_id, "status": {"$in": ["applied", "preparing"]}},
            {"_id": 0, "application_id": 1, "title": 1, "company": 1, "job_id": 1}
        )
        apps = {a["application_id"]: a async for a in apps_cursor}

        if not apps:
            return

        # Search for recent emails (last 24 hours) that might be interview-related
        query = (
            "in:inbox "
            "newer_than:1d "
            "(interview OR \"thank you\" OR \"next steps\" OR "
            "\"we were impressed\" OR \"move forward\" OR "
            "rejection OR \"not selected\" OR \"unfortunately\")"
        )

        results = svc.users().messages().list(userId="me", q=query, maxResults=20).execute()
        messages = results.get("messages", [])

        for msg in messages:
            # Get full message
            msg_data = svc.users().messages().get(userId="me", id=msg["id"], format="metadata",
                                                 metadataHeaders=["Subject", "From", "Date"]).execute()

            headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
            subject = headers.get("Subject", "").lower()
            sender = headers.get("From", "").lower()
            date_str = headers.get("Date", "")

            # Determine if this is interview-related and what status to suggest
            suggested_status = None
            if any(word in subject for word in ["interview", "talk", "chat", "meet"]):
                if any(word in subject for word in ["scheduled", "schedule", "book", "confirm"]):
                    suggested_status = "interview"
                elif any(word in subject for word in ["thank", "thanks", "appreciate"]):
                    suggested_status = "interview"  # Post-interview thank you
            elif any(word in subject for word in ["rejection", "not selected", "unfortunately",
                                                 "regret", "cannot offer", "position filled"]):
                suggested_status = "rejected"
            elif any(word in subject for word in ["offer", "congratulations", "pleased to offer"]):
                suggested_status = "offer"

            if suggested_status:
                # Find matching applications by company/job title similarity
                for app_id, app in apps.items():
                    company_match = (
                        app["company"].lower() in sender or
                        any(word in sender for word in app["company"].lower().split() if len(word) > 3) or
                        any(word in app["company"].lower() for word in sender.split() if len(word) > 3)
                    )

                    title_match = (
                        app["title"].lower() in subject or
                        any(word in subject for word in app["title"].lower().split() if len(word) > 3)
                    )

                    if company_match or title_match:
                        # Create a notification suggesting status update
                        await notify(
                            user_id,
                            f"Email suggests updating {app['company']} - {app['title']} to {suggested_status}",
                            link=f"/app/tracker?app={app_id}",
                            kind="gmail_suggestion"
                        )

                        # Add a timeline event to the application
                        await db.applications.update_one(
                            {"application_id": app_id},
                            {"$push": {
                                "timeline": event(
                                    "gmail_suggestion",
                                    f"Email suggested status update to {suggested_status}: {subject[:100]}..."
                                )
                            }}
                        )
                        break  # Only notify once per email

    except Exception as e:
        logger.error(f"Gmail inbox scan failed for user {user_id}: {e}")
        # Don't raise - we don't want to crash the scheduler


async def _scan_gmail_inbox():
    """Scan Gmail inbox for all users with Gmail connected."""
    # Find all users who have Gmail connected
    users_cursor = db.users.find({"gmail_connected": True}, {"_id": 0, "user_id": 1})
    users = [u["user_id"] async for u in users_cursor]

    # Scan each user's inbox
    for user_id in users:
        await _scan_gmail_inbox_for_user(user_id)
