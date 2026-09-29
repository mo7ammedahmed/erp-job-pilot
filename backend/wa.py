import os
import re
import httpx
from core import logger, integration_secrets, integration_value

TPL_VERIFY = os.environ.get("WHATSAPP_TEMPLATE_VERIFY", "jobpilot_verify")
TPL_REMINDER = os.environ.get("WHATSAPP_TEMPLATE_REMINDER", "jobpilot_reminder")


async def wa_creds():
    """Read WhatsApp credentials at call time, so keys added from the dashboard take effect.

    They are resolved from the admin-managed secret store first and the environment second; a
    module-level read would freeze the boot-time environment and ignore anything set later.
    """
    stored = await integration_secrets()
    return {k: await integration_value(name, stored) for k, name in
            (("token", "WHATSAPP_TOKEN"), ("phone_id", "WHATSAPP_PHONE_ID"),
             ("verify", "WHATSAPP_VERIFY_TOKEN"), ("app_secret", "WHATSAPP_APP_SECRET"))}


async def wa_configured():
    c = await wa_creds()
    return bool(c["token"] and c["phone_id"])


def norm_phone(p):
    return re.sub(r"\D", "", p or "")


async def wa_send_template(to, template, params, lang="en"):
    creds = await wa_creds()
    if not (creds["token"] and creds["phone_id"]):
        return False
    body = {"messaging_product": "whatsapp", "to": norm_phone(to), "type": "template",
            "template": {"name": template, "language": {"code": "ar" if lang == "ar" else "en"},
                         "components": [{"type": "body", "parameters": [{"type": "text", "text": str(p)[:900]} for p in params]}]}}
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"https://graph.facebook.com/v21.0/{creds['phone_id']}/messages",
                             headers={"Authorization": f"Bearer {creds['token']}"}, json=body)
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"WhatsApp send failed: {e}")
        return False
