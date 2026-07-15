"""
WhatsApp Token Manager — validate, alert, auto-update.

Flow:
1. Check WHATSAPP_TOKEN every 6 hours via scheduler
2. If invalid/expired → Telegram alert with regeneration link
3. POST /api/whatsapp/token with new token → auto-sets Railway var
4. GET  /api/whatsapp/token/status → health check
"""
import os
import logging
import subprocess
import aiohttp
from datetime import datetime

log = logging.getLogger(__name__)

WA_TOKEN      = os.getenv("WHATSAPP_TOKEN", "")
WA_PHONE_ID   = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "1029511316922873")
WA_APP_ID     = os.getenv("WHATSAPP_APP_ID", "1994952984446870")
TG_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT       = os.getenv("TELEGRAM_CHAT_ID", "")
RAILWAY_SVC   = os.getenv("RAILWAY_SERVICE_NAME", "aiitec-saas")
_GRAPH        = "https://graph.facebook.com/v21.0"

_BIZ_URL = (
    "https://business.facebook.com/settings/system-users?"
    "business_id=1328977765197849"
)


async def _tg(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram send failed: %s", e)


async def check_wa_token(token: str | None = None) -> dict:
    """Validate WhatsApp token via Graph API debug_token."""
    t = token or WA_TOKEN
    if not t:
        return {"valid": False, "reason": "no token configured"}

    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{_GRAPH}/{WA_PHONE_ID}",
                params={"access_token": t, "fields": "id,display_phone_number,verified_name"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json(content_type=None)

        if "error" in d:
            err = d["error"]
            return {
                "valid": False,
                "reason": err.get("message", "unknown"),
                "code": err.get("code", 0),
            }

        return {
            "valid": True,
            "phone": d.get("display_phone_number"),
            "name": d.get("verified_name"),
        }
    except Exception as e:
        return {"valid": False, "reason": str(e)}


def _set_railway_var(key: str, value: str) -> bool:
    try:
        r = subprocess.run(
            ["railway", "variables", "set", f"{key}={value}",
             "--service", RAILWAY_SVC],
            capture_output=True, timeout=30,
        )
        return r.returncode == 0
    except Exception as e:
        log.warning("Railway var set failed %s: %s", key, e)
        return False


async def alert_token_expired(reason: str = "") -> None:
    """Send Telegram alert with step-by-step token renewal instructions."""
    await _tg(
        "🚨 <b>WhatsApp Token ABGELAUFEN</b>\n\n"
        f"Grund: {reason or 'Ungültiger Token'}\n\n"
        "<b>Neuen Token generieren (3 Schritte):</b>\n\n"
        "1️⃣ Öffne: <a href=\"https://business.facebook.com/settings/system-users?business_id=1328977765197849\">Meta Business → System Users</a>\n\n"
        "2️⃣ Klicke auf <b>\"Conversions API System User\"</b> → <b>\"Generate new token\"</b>\n"
        "   App: <b>AIITEC WA App (1994952984446870)</b>\n"
        "   Permissions: <b>whatsapp_business_messaging, whatsapp_business_management</b>\n\n"
        "3️⃣ Token an Bot schicken:\n"
        "   /wa_token EAAA...dein_neuer_token\n\n"
        "Oder per POST: https://aiitec-saas-production.up.railway.app/api/whatsapp/token"
    )


async def process_new_token(new_token: str) -> dict:
    """Validate and deploy new WhatsApp token."""
    check = await check_wa_token(new_token)

    if not check.get("valid"):
        return {"ok": False, "error": check.get("reason", "Token ungültig")}

    # Setze in Railway
    ok_rw = _set_railway_var("WHATSAPP_TOKEN", new_token)

    await _tg(
        f"✅ <b>WhatsApp Token erneuert!</b>\n"
        f"Nummer: {check.get('phone', '?')}\n"
        f"Name: {check.get('name', '?')}\n"
        f"Railway: {'✅ gesetzt' if ok_rw else '⚠️ manuell setzen'}\n"
        f"Datum: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

    return {
        "ok": True,
        "phone": check.get("phone"),
        "name": check.get("name"),
        "railway_set": ok_rw,
    }


async def run_token_health_check() -> dict:
    """Scheduled job — check token, alert if invalid."""
    check = await check_wa_token()

    if not check.get("valid"):
        log.warning("WA Token ungültig: %s", check.get("reason"))
        await alert_token_expired(check.get("reason", ""))
        return {"healthy": False, **check}

    log.info("WA Token OK — %s (%s)", check.get("phone"), check.get("name"))
    return {"healthy": True, **check}
