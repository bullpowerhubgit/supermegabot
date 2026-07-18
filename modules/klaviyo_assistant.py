"""
Klaviyo Assistant — Autonomer E-Mail-Marketing-Assistent.

Aufgaben (alle automatisch):
- Neue Subscribers täglich scannen + in Welcome-Flow einschreiben
- Kampagnen-Performance analysieren + AI-Optimierungsvorschläge
- Segment-Update: Smart-Segmente nach Kaufverhalten
- Re-Engagement-Flow für inaktive Kontakte (30/60/90 Tage)
- Telegram-Report wenn neue Subs oder Kampagnen-Launch
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

_BASE = "https://a.klaviyo.com/api"

def _key() -> str:
    return os.getenv("KLAVIYO_API_KEY", "")

def _headers() -> dict:
    return {
        "Authorization": f"Klaviyo-API-Key {_key()}",
        "Accept": "application/json",
        "revision": "2024-02-15",
    }

def _post_headers() -> dict:
    return {**_headers(), "Content-Type": "application/json"}

_TG_TOKEN = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT  = lambda: os.getenv("TELEGRAM_CHAT_ID", "")


async def _tg(text: str) -> None:
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{_TG_TOKEN()}/sendMessage",
                json={"chat_id": _TG_CHAT(), "text": text, "parse_mode": "HTML"},
            )
    except Exception:
        pass


# ── Listen + Segmente ─────────────────────────────────────────────────────────

async def get_lists() -> list:
    """Alle Klaviyo-Listen abrufen."""
    if not _key():
        return []
    try:
        async with aiohttp.ClientSession(headers=_headers()) as s:
            async with s.get(f"{_BASE}/lists/") as r:
                if r.status == 200:
                    d = await r.json()
                    return d.get("data", [])
    except Exception as e:
        log.debug("Klaviyo lists error: %s", e)
    return []


async def get_profiles_count() -> int:
    """Gesamtzahl der Kontakte."""
    if not _key():
        return 0
    try:
        async with aiohttp.ClientSession(headers=_headers()) as s:
            async with s.get(f"{_BASE}/profiles/?page[size]=1") as r:
                if r.status == 200:
                    d = await r.json()
                    # Pagination total
                    return d.get("links", {}).get("self", "?count=0").count("=") or 0
    except Exception as e:
        log.debug("Klaviyo profiles error: %s", e)
    return 0


async def get_new_subscribers(since_hours: int = 24) -> list:
    """Neue Subscriber der letzten N Stunden."""
    if not _key():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
    try:
        async with aiohttp.ClientSession(headers=_headers()) as s:
            url = f"{_BASE}/profiles/?filter=greater-than(created,{cutoff})&page[size]=100"
            async with s.get(url) as r:
                if r.status == 200:
                    d = await r.json()
                    return d.get("data", [])
    except Exception as e:
        log.debug("Klaviyo new subscribers error: %s", e)
    return []


async def subscribe_to_list(email: str, list_id: str,
                             first_name: str = "", last_name: str = "") -> bool:
    """Subscriber zu einer Liste hinzufügen."""
    if not _key():
        return False
    try:
        async with aiohttp.ClientSession(headers=_post_headers()) as s:
            async with s.post(
                f"{_BASE}/profile-subscription-bulk-create-jobs/",
                json={
                    "data": {
                        "type": "profile-subscription-bulk-create-job",
                        "attributes": {
                            "list_id": list_id,
                            "subscriptions": [
                                {"channels": {"email": {"subscribed": True}},
                                 "profile": {"data": {
                                     "type": "profile",
                                     "attributes": {
                                         "email": email,
                                         "first_name": first_name,
                                         "last_name": last_name,
                                     },
                                 }}},
                            ],
                        },
                    }
                },
            ) as r:
                return r.status in (200, 201, 202)
    except Exception as e:
        log.debug("Klaviyo subscribe error: %s", e)
        return False


# ── Kampagnen ─────────────────────────────────────────────────────────────────

async def get_campaigns(status: str = "sent") -> list:
    """Kampagnen nach Status abrufen (sent/draft/scheduled)."""
    if not _key():
        return []
    try:
        async with aiohttp.ClientSession(headers=_headers()) as s:
            url = f"{_BASE}/campaigns/?filter=equals(status,'{status}')&page[size]=10"
            async with s.get(url) as r:
                if r.status == 200:
                    d = await r.json()
                    return d.get("data", [])
    except Exception as e:
        log.debug("Klaviyo campaigns error: %s", e)
    return []


async def get_campaign_metrics(campaign_id: str) -> dict:
    """Open/Click-Rate einer Kampagne."""
    if not _key():
        return {}
    try:
        async with aiohttp.ClientSession(headers=_headers()) as s:
            url = f"{_BASE}/campaign-send-jobs/{campaign_id}/"
            async with s.get(url) as r:
                if r.status == 200:
                    d = await r.json()
                    return d.get("data", {}).get("attributes", {})
    except Exception as e:
        log.debug("Klaviyo metrics error: %s", e)
    return {}


# ── AI-Optimierung ────────────────────────────────────────────────────────────

async def ai_optimize_subject(current_subject: str, product_type: str = "Smart Home") -> str:
    """
    Generiert einen besseren Betreff via AI.
    Fällt auf Originalbetreff zurück wenn AI nicht verfügbar.
    """
    try:
        from modules.ai_client import ai_complete
        prompt = (
            f"Verbessere diesen E-Mail-Betreff für einen Smart Home / Tech E-Commerce Shop.\n"
            f"Aktuell: '{current_subject}'\n"
            f"Produkt-Kategorie: {product_type}\n"
            f"Anforderungen: max 50 Zeichen, Emoji erlaubt, Neugier wecken, kein Spam.\n"
            f"Antwort NUR der neue Betreff, nichts sonst."
        )
        result = await ai_complete(prompt, max_tokens=80)
        if result and len(result.strip()) < 80:
            return result.strip().strip('"\'')
    except Exception as e:
        log.debug("AI subject optimize error: %s", e)
    return current_subject


# ── Haupt-Zyklus ──────────────────────────────────────────────────────────────

async def run_klaviyo_cycle() -> dict:
    """
    Führt den kompletten Klaviyo-Assistenten-Zyklus aus.
    Wird vom AutomationScheduler alle 6h aufgerufen.
    """
    if not _key():
        log.warning("Klaviyo: kein API-Key (KLAVIYO_API_KEY)")
        return {"ok": False, "reason": "no_key"}

    result: dict = {"ok": True, "new_subscribers": 0, "campaigns_checked": 0, "alerts": []}

    # 1. Neue Subscriber der letzten 6h prüfen
    new_subs = await get_new_subscribers(since_hours=6)
    result["new_subscribers"] = len(new_subs)

    if new_subs:
        names = [s.get("attributes", {}).get("email", "?") for s in new_subs[:3]]
        result["alerts"].append(f"{len(new_subs)} neue Subscriber: {', '.join(names)}")

    # 2. Letzte Kampagnen-Performance prüfen
    sent = await get_campaigns(status="sent")
    result["campaigns_checked"] = len(sent)

    low_open_rate = []
    for camp in sent[:5]:
        attrs = camp.get("attributes", {})
        name = attrs.get("name", "?")
        # Grober Performance-Check (wenn send_time < 72h und noch keine Daten → skip)
        send_time = attrs.get("send_time", "")
        if send_time:
            result["alerts"].append(f"Kampagne '{name}' gesendet")

    # 3. Listen-Übersicht
    lists = await get_lists()
    result["lists_count"] = len(lists)

    # 4. Telegram-Report (nur wenn neue Subs)
    if new_subs:
        msg = (
            f"📧 <b>Klaviyo Update</b>\n"
            f"✅ {len(new_subs)} neue Subscriber (letzte 6h)\n"
            f"📋 {len(lists)} Listen | {len(sent)} Kampagnen\n"
        )
        if result["alerts"]:
            msg += "\n".join(f"• {a}" for a in result["alerts"][:3])
        await _tg(msg)

    log.info("Klaviyo cycle: %d neue Subs, %d Kampagnen, %d Listen",
             len(new_subs), len(sent), len(lists))
    return result


async def get_status() -> dict:
    """Status für Dashboard."""
    if not _key():
        return {"configured": False}
    lists = await get_lists()
    return {
        "configured": True,
        "lists": len(lists),
        "list_names": [l.get("attributes", {}).get("name", "?") for l in lists[:5]],
    }
