#!/usr/bin/env python3
"""Twilio SMS module — send SMS via API Key auth"""
import os
import logging
import aiohttp

log = logging.getLogger("TwilioSMS")

ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN", "")
FROM_NUMBER  = os.getenv("TWILIO_FROM_NUMBER", "")

BASE_URL = f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}/Messages.json"


def is_configured() -> bool:
    return bool(ACCOUNT_SID and AUTH_TOKEN)


async def send_sms(to: str, body: str, from_number: str = None) -> dict:
    """Send SMS. Returns dict with sid and status, or error key on failure."""
    if not is_configured():
        log.warning("Twilio not configured — set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN")
        return {"error": "not_configured"}

    sender = from_number or FROM_NUMBER
    if not sender:
        return {"error": "no_from_number — set TWILIO_FROM_NUMBER in .env"}

    auth = aiohttp.BasicAuth(ACCOUNT_SID, AUTH_TOKEN)
    data = {"To": to, "From": sender, "Body": body}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(BASE_URL, data=data, auth=auth,
                                    timeout=aiohttp.ClientTimeout(total=15)) as resp:
                result = await resp.json(content_type=None)
        if resp.status == 201:
            log.info("SMS sent to %s — SID: %s", to, result.get("sid"))
            return {"sid": result.get("sid"), "status": result.get("status")}
        log.error("Twilio error %s: %s", resp.status, result.get("message"))
        return {"error": result.get("message"), "code": result.get("code")}
    except Exception as exc:
        log.error("Twilio send_sms exception: %s", exc)
        return {"error": str(exc)}


async def get_account_info() -> dict:
    """Fetch account info to verify credentials."""
    if not is_configured():
        return {"error": "not_configured"}

    url = f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}.json"
    auth = aiohttp.BasicAuth(ACCOUNT_SID, AUTH_TOKEN)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, auth=auth,
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json(content_type=None)
        if resp.status == 200:
            return {"status": data.get("status"), "friendly_name": data.get("friendly_name")}
        return {"error": data.get("message")}
    except Exception as exc:
        return {"error": str(exc)}
