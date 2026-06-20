#!/usr/bin/env python3
"""Twilio SMS module — send SMS via Twilio REST API"""
import os
import logging
import aiohttp
from datetime import datetime

log = logging.getLogger("TwilioSMS")

ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN", "")
# Support both TWILIO_PHONE_NUMBER and legacy TWILIO_FROM_NUMBER
FROM_NUMBER  = os.getenv("TWILIO_PHONE_NUMBER", os.getenv("TWILIO_FROM_NUMBER", ""))
TO_NUMBER    = os.getenv("TWILIO_TO_NUMBER", "")


def _base_url() -> str:
    sid = os.getenv("TWILIO_ACCOUNT_SID", ACCOUNT_SID)
    return f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


def is_configured() -> bool:
    return bool(ACCOUNT_SID and AUTH_TOKEN)


async def send_sms(to_number: str, message: str, from_number: str = None) -> dict:
    """Send SMS via Twilio REST API.

    Args:
        to_number:   Recipient phone number (E.164 format, e.g. +4912345678)
        message:     SMS body text
        from_number: Override sender; defaults to TWILIO_PHONE_NUMBER env var

    Returns dict with sid/status on success, or error key on failure.
    Gracefully skips if phone numbers are not configured.
    """
    sid = os.getenv("TWILIO_ACCOUNT_SID", ACCOUNT_SID)
    token = os.getenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    sender = from_number or os.getenv("TWILIO_PHONE_NUMBER", os.getenv("TWILIO_FROM_NUMBER", FROM_NUMBER))

    if not sid or not token:
        log.warning("Twilio not configured — set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN")
        return {"ok": False, "error": "not_configured"}

    if not sender:
        log.warning("No sender number — set TWILIO_PHONE_NUMBER in .env")
        return {"ok": False, "error": "no_from_number — set TWILIO_PHONE_NUMBER in .env"}

    if not to_number:
        log.warning("No recipient number provided and TWILIO_TO_NUMBER not set")
        return {"ok": False, "error": "no_to_number — provide to_number or set TWILIO_TO_NUMBER"}

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    auth = aiohttp.BasicAuth(sid, token)
    payload = {"To": to_number, "From": sender, "Body": message}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload, auth=auth,
                                    timeout=aiohttp.ClientTimeout(total=15)) as resp:
                result = await resp.json(content_type=None)
        if resp.status == 201:
            log.info("SMS sent to %s — SID: %s", to_number, result.get("sid"))
            return {"ok": True, "sid": result.get("sid"), "status": result.get("status")}
        log.error("Twilio error %s: %s", resp.status, result.get("message"))
        return {"ok": False, "error": result.get("message"), "code": result.get("code")}
    except Exception as exc:
        log.error("Twilio send_sms exception: %s", exc)
        return {"ok": False, "error": str(exc)}


async def run_daily_revenue_sms() -> dict:
    """Send daily revenue summary via SMS.

    Uses TWILIO_TO_NUMBER as recipient. Gracefully skips if phone numbers
    are not configured. Pulls revenue data from Supabase/internal APIs where
    available, otherwise sends a simple status ping.
    """
    to = os.getenv("TWILIO_TO_NUMBER", TO_NUMBER)
    if not to:
        log.info("run_daily_revenue_sms: TWILIO_TO_NUMBER not set — skipping")
        return {"ok": False, "skipped": True, "reason": "TWILIO_TO_NUMBER not configured"}

    if not is_configured():
        log.info("run_daily_revenue_sms: Twilio credentials not set — skipping")
        return {"ok": False, "skipped": True, "reason": "Twilio credentials not configured"}

    # Try to fetch revenue data
    revenue_text = ""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("http://localhost:8888/api/revenue/summary",
                             timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    data = await r.json()
                    ds24 = data.get("ds24", {}).get("stats", {})
                    stripe = data.get("stripe", {})
                    shopify = data.get("shopify", {})
                    ds24_total = ds24.get("total", 0)
                    stripe_mrr = stripe.get("mrr_eur", 0)
                    shop_rev = shopify.get("revenue_today_eur", 0)
                    total = float(ds24_total or 0) + float(stripe_mrr or 0) + float(shop_rev or 0)
                    revenue_text = (
                        f"DS24: €{ds24_total} | Stripe MRR: €{stripe_mrr} | "
                        f"Shopify: €{shop_rev} | TOTAL: €{total:.0f}"
                    )
    except Exception as e:
        log.warning("Could not fetch revenue data: %s", e)

    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    if revenue_text:
        body = f"[SuperMegaBot] Tages-Revenue {now}\n{revenue_text}"
    else:
        body = f"[SuperMegaBot] Daily Status {now}\nSystem laeuft. Keine Revenue-Daten verfuegbar."

    result = await send_sms(to, body)
    log.info("Daily revenue SMS: %s", result)
    return result


async def get_status() -> dict:
    """Return Twilio configuration status."""
    sid = os.getenv("TWILIO_ACCOUNT_SID", ACCOUNT_SID)
    token = os.getenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    phone = os.getenv("TWILIO_PHONE_NUMBER", os.getenv("TWILIO_FROM_NUMBER", FROM_NUMBER))
    to = os.getenv("TWILIO_TO_NUMBER", TO_NUMBER)
    configured = bool(sid and token)
    return {
        "ok": configured,
        "configured": configured,
        "has_from_number": bool(phone),
        "has_to_number": bool(to),
        "account_sid_set": bool(sid),
        "auth_token_set": bool(token),
    }


async def get_account_info() -> dict:
    """Fetch account info to verify credentials."""
    sid = os.getenv("TWILIO_ACCOUNT_SID", ACCOUNT_SID)
    token = os.getenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    if not sid or not token:
        return {"error": "not_configured"}

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json"
    auth = aiohttp.BasicAuth(sid, token)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, auth=auth,
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json(content_type=None)
        if resp.status == 200:
            return {"ok": True, "status": data.get("status"), "friendly_name": data.get("friendly_name")}
        return {"ok": False, "error": data.get("message")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
