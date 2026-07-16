"""
Conversion Pixel Engine — Meta CAPI Purchase/Lead Events
=========================================================
Feuert Server-Side Events an Meta Conversion API (kein Browser nötig)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("ConversionPixel")

_TOKEN    = os.getenv("META_ADS_TOKEN", os.getenv("META_ACCESS_TOKEN", ""))
_PIXEL_ID = os.getenv("FACEBOOK_PIXEL_ID", "4215456142051261")
_API      = "https://graph.facebook.com/v21.0"


def _hash(value: str) -> str:
    return hashlib.sha256(value.lower().strip().encode()).hexdigest()


async def _send_event(event_name: str, data: dict, test_event_code: Optional[str] = None) -> dict:
    if not _TOKEN:
        log.warning("META_ADS_TOKEN nicht gesetzt")
        return {"error": "no token"}
    payload: dict = {
        "data": [{
            "event_name": event_name,
            "event_time": int(time.time()),
            "action_source": "website",
            **data
        }],
        "access_token": _TOKEN,
    }
    if test_event_code:
        payload["test_event_code"] = test_event_code
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{_API}/{_PIXEL_ID}/events",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                result = await r.json()
                if "error" in result:
                    log.warning("CAPI %s Fehler: %s", event_name, result["error"].get("message"))
                else:
                    log.info("CAPI %s gesendet ✓ (events_received=%s)", event_name,
                             result.get("events_received", "?"))
                return result
    except Exception as e:
        log.warning("CAPI send_event: %s", e)
        return {"error": str(e)}


async def fire_purchase_event(value_eur: float, email: str = "", order_id: str = "") -> dict:
    """Sendet Purchase-Event an Meta CAPI — wenn Stripe-Zahlung eingeht."""
    user_data: dict = {"client_ip_address": "127.0.0.1", "client_user_agent": "SuperMegaBot"}
    if email:
        user_data["em"] = [_hash(email)]
    custom_data: dict = {
        "currency": "EUR",
        "value": value_eur,
        "content_type": "product",
        "content_ids": ["smb_subscription"],
    }
    if order_id:
        custom_data["order_id"] = order_id
    return await _send_event("Purchase", {
        "user_data": user_data,
        "custom_data": custom_data,
    })


async def fire_lead_event(email: str, source: str = "website") -> dict:
    """Sendet Lead-Event — wenn jemand seine Email eingibt."""
    user_data: dict = {"client_ip_address": "127.0.0.1", "client_user_agent": "SuperMegaBot"}
    if email:
        user_data["em"] = [_hash(email)]
    return await _send_event("Lead", {
        "user_data": user_data,
        "custom_data": {"content_name": source},
    })


async def fire_view_content_event(url: str = "", content_name: str = "") -> dict:
    """Sendet ViewContent-Event — für Retargeting."""
    return await _send_event("ViewContent", {
        "user_data": {"client_ip_address": "127.0.0.1", "client_user_agent": "SuperMegaBot"},
        "custom_data": {
            "content_name": content_name or "SuperMegaBot Landing",
            "content_type": "product",
        },
        "event_source_url": url or "https://ineedit.com.co",
    })


async def run_daily_pixel_report() -> dict:
    """Pixel-Statistiken der letzten 7 Tage."""
    if not _TOKEN:
        return {"error": "no token"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{_API}/{_PIXEL_ID}",
                params={
                    "fields": "name,creation_time,last_fired_time,is_unavailable",
                    "access_token": _TOKEN
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                data = await r.json()
                return {
                    "pixel_id": _PIXEL_ID,
                    "name": data.get("name", "?"),
                    "last_fired": data.get("last_fired_time", "?"),
                    "active": not data.get("is_unavailable", False),
                }
    except Exception as e:
        return {"error": str(e)}
