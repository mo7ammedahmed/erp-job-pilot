import os
import re
import httpx
from core import logger

WA_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
WA_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "")
WA_VERIFY = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
WA_APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "")
TPL_VERIFY = os.environ.get("WHATSAPP_TEMPLATE_VERIFY", "jobpilot_verify")
TPL_REMINDER = os.environ.get("WHATSAPP_TEMPLATE_REMINDER", "jobpilot_reminder")


def wa_configured():
    return bool(WA_TOKEN and WA_PHONE_ID)


def norm_phone(p):
    return re.sub(r"\D", "", p or "")


async def wa_send_template(to, template, params, lang="en"):
    if not wa_configured():
        return False
    body = {"messaging_product": "whatsapp", "to": norm_phone(to), "type": "template",
            "template": {"name": template, "language": {"code": "ar" if lang == "ar" else "en"},
                         "components": [{"type": "body", "parameters": [{"type": "text", "text": str(p)[:900]} for p in params]}]}}
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages", headers={"Authorization": f"Bearer {WA_TOKEN}"}, json=body)
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"WhatsApp send failed: {e}")
        return False
