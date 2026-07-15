#!/usr/bin/env python3
"""
Klaviyo Client — Stub-Modul
Leichtgewichtiger Client-Stub; echte API-Aufrufe via klaviyo_automation.py.
Verhindert ImportError bei track_event-Aufrufen in server.py.
"""

import logging
import os

log = logging.getLogger(__name__)


async def track_event(event: str, email: str, properties: dict = None):
    """Stub: Event an Klaviyo senden.
    Verwendet KLAVIYO_API_KEY aus .env wenn gesetzt, sonst no-op.
    """
    api_key = os.getenv("KLAVIYO_API_KEY", "")
    if not api_key:
        log.debug("klaviyo_client.track_event: kein KLAVIYO_API_KEY — übersprungen")
        return {"ok": False, "error": "KLAVIYO_API_KEY nicht konfiguriert"}
    try:
        import aiohttp
        payload = {
            "data": {
                "type": "event",
                "attributes": {
                    "metric": {"data": {"type": "metric", "attributes": {"name": event}}},
                    "profile": {"data": {"type": "profile", "attributes": {"email": email}}},
                    "properties": properties or {},
                },
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://a.klaviyo.com/api/events/",
                headers={
                    "Authorization": f"Klaviyo-API-Key {api_key}",
                    "revision": "2024-02-15",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status in (200, 202):
                    return {"ok": True, "event": event, "email": email}
                text = await r.text()
                return {"ok": False, "status": r.status, "body": text[:200]}
    except Exception as e:
        log.warning("klaviyo_client.track_event Fehler: %s", e)
        return {"ok": False, "error": str(e)}
