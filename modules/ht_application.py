"""
High-Ticket Application System
================================
Verarbeitet Demo-Anfragen von der High-Ticket Landing Page:
- Speichert Lead in Supabase (lead_events)
- Sendet Telegram-Alert an Rudolf
- Sendet Bestätigungs-E-Mail via Klaviyo
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger("ht_application")

_TIERS = {
    "Growth": {"price_monthly": 497, "price_onetime": 3997},
    "Scale": {"price_monthly": 997, "price_onetime": 7997},
    "Enterprise": {"price_monthly": 2497, "price_onetime": 14997},
}


async def save_application(data: dict) -> dict:
    """
    Verarbeitet eine High-Ticket Demo-Anfrage.
    data: {name, email, shop_url, revenue, plan, problem, source}
    """
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    plan = data.get("plan", "Scale")
    revenue = data.get("revenue", "")
    shop_url = data.get("shop_url", "")
    problem = data.get("problem", "")
    source = data.get("source", "highticket_landing_page")

    if not name or not email:
        return {"ok": False, "error": "name und email erforderlich"}

    lead_score = _calc_lead_score(revenue, plan, shop_url)
    tier_info = _TIERS.get(plan, _TIERS["Scale"])
    ts = datetime.now(timezone.utc).isoformat()

    tasks = [
        _save_supabase(name, email, shop_url, plan, revenue, problem, lead_score, source, ts),
        _notify_telegram(name, email, plan, revenue, shop_url, problem, lead_score, tier_info),
        _klaviyo_confirm(name, email, plan),
    ]

    import asyncio
    results = await asyncio.gather(*tasks, return_exceptions=True)

    supabase_ok = not isinstance(results[0], Exception)
    telegram_ok = not isinstance(results[1], Exception)

    log.info(
        "HT Application: %s <%s> Plan=%s Score=%d Supabase=%s Telegram=%s",
        name, email, plan, lead_score, supabase_ok, telegram_ok,
    )

    return {
        "ok": True,
        "lead_score": lead_score,
        "plan": plan,
        "supabase_saved": supabase_ok,
        "telegram_notified": telegram_ok,
    }


def _calc_lead_score(revenue: str, plan: str, shop_url: str) -> int:
    score = 50
    rev_scores = {
        "Über €150.000": 40, "€50.000 – €150.000": 30,
        "€15.000 – €50.000": 20, "€5.000 – €15.000": 10,
        "Unter €5.000": 0,
    }
    score += rev_scores.get(revenue, 5)
    plan_scores = {"Enterprise": 8, "Scale": 5, "Growth": 2}
    score += plan_scores.get(plan, 0)
    if shop_url and shop_url.startswith("http"):
        score += 2
    return min(score, 100)


async def _save_supabase(name, email, shop_url, plan, revenue, problem, lead_score, source, ts):
    import aiohttp
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        log.warning("Supabase nicht konfiguriert — Lead nicht gespeichert")
        return

    payload = {
        "event_type": "ht_demo_application",
        "email": email,
        "metadata": json.dumps({
            "name": name, "plan": plan, "revenue": revenue,
            "shop_url": shop_url, "problem": problem,
            "lead_score": lead_score, "source": source, "ts": ts,
        }),
    }

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        async with s.post(
            f"{url}/rest/v1/lead_events",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json=payload,
        ) as r:
            if r.status not in (200, 201):
                body = await r.text()
                log.error("Supabase insert failed %s: %s", r.status, body[:200])


async def _notify_telegram(name, email, plan, revenue, shop_url, problem, lead_score, tier_info):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return

    score_emoji = "🔥" if lead_score >= 80 else "⭐" if lead_score >= 60 else "👤"
    msg = (
        f"{score_emoji} <b>NEUER HIGH-TICKET LEAD!</b>\n\n"
        f"👤 <b>{name}</b> (<code>{email}</code>)\n"
        f"📦 Plan: <b>{plan}</b> → €{tier_info['price_monthly']}/Monat\n"
        f"💰 Shop-Umsatz: {revenue}\n"
        f"🏪 Shop: {shop_url or '—'}\n"
        f"🎯 Lead-Score: <b>{lead_score}/100</b>\n"
    )
    if problem:
        msg += f"\n💬 Problem: <i>{problem[:200]}</i>\n"
    msg += f"\n<i>→ Innerhalb 2 Werktagen kontaktieren!</i>"

    import aiohttp
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        await s.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
        )


async def _klaviyo_confirm(name, email, plan):
    key = os.getenv("KLAVIYO_API_KEY", "")
    if not key:
        return

    import aiohttp
    payload = {
        "data": {
            "type": "profile",
            "attributes": {
                "email": email,
                "first_name": name.split()[0] if name else name,
                "properties": {"ht_plan_interest": plan, "ht_demo_requested": True},
            },
        }
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        async with s.post(
            "https://a.klaviyo.com/api/profiles/",
            headers={
                "Authorization": f"Klaviyo-API-Key {key}",
                "revision": "2024-10-15",
                "Content-Type": "application/json",
            },
            json=payload,
        ) as r:
            if r.status not in (200, 201, 409):
                log.warning("Klaviyo profile failed: %s", r.status)
