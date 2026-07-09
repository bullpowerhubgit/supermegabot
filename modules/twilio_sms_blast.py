#!/usr/bin/env python3
"""
Twilio SMS Blast — vollautonome SMS Marketing Engine via Twilio REST API.
Kein SDK nötig — direkt aiohttp.
"""
import logging
import os
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("TwilioSMS")

ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN", "")
FROM_NUMBER  = os.getenv("TWILIO_FROM_NUMBER", "+18663835801")
TO_NUMBER    = os.getenv("TWILIO_VERIFIED_TO", "+4917622890860")

_TWILIO_URL  = f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}/Messages.json"

STORE_URL    = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
PROD_URL     = "https://supermegabot-production.up.railway.app"


async def _send_sms(body: str, to: str = None) -> dict:
    """Send SMS via Twilio REST API using HTTP Basic auth."""
    if not ACCOUNT_SID or not AUTH_TOKEN:
        return {"ok": False, "error": "TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN not set"}
    recipient = to or TO_NUMBER
    if not recipient or not FROM_NUMBER:
        return {"ok": False, "error": "TWILIO_FROM_NUMBER or TWILIO_VERIFIED_TO not set"}

    body_truncated = body[:1600]
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                _TWILIO_URL,
                auth=aiohttp.BasicAuth(ACCOUNT_SID, AUTH_TOKEN),
                data={"From": FROM_NUMBER, "To": recipient, "Body": body_truncated},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
        if data.get("sid"):
            log.info("SMS sent: %s → %s (SID: %s)", FROM_NUMBER, recipient, data["sid"])
            return {"ok": True, "sid": data["sid"], "to": recipient}
        err = data.get("message", str(data.get("code", "unknown error")))
        log.warning("SMS failed: %s", err)
        return {"ok": False, "error": err}
    except Exception as e:
        log.error("Twilio SMS error: %s", e)
        return {"ok": False, "error": str(e)}


async def run_sms_revenue_alert(message: str) -> dict:
    """Send an SMS revenue alert to Rudolf."""
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
    text = f"[BullPower Bot] {today}\n{message}"
    return await _send_sms(text)


async def run_sms_morning_brief() -> dict:
    """Daily morning SMS with system status and revenue summary."""
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    # Try to get live revenue from Railway
    revenue_line = ""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(f"{PROD_URL}/api/revenue/summary") as r:
                d = await r.json(content_type=None)
            today_rev = d.get("today", {}).get("total", d.get("total_today", 0))
            revenue_line = f"Heute: €{today_rev:.2f}" if today_rev else ""
    except Exception:
        pass

    text = (
        f"[SuperMegaBot] Guten Morgen! {today}\n"
        f"System: ✅ Online\n"
        f"{revenue_line}\n"
        f"Shop: {STORE_URL}\n"
        f"Alle Tasks laufen autonom."
    ).strip()
    return await _send_sms(text)


async def run_sms_promo_blast(promo_text: str = None) -> dict:
    """Send a promotional SMS."""
    if not promo_text:
        promo_text = (
            f"🔥 DEAL ALERT von autopilot-store-suite-fmbka.myshopify.com!\n"
            f"Heute: Top-Produkte zu besten Preisen.\n"
            f"Schau jetzt rein: {STORE_URL}"
        )
    return await _send_sms(promo_text)
