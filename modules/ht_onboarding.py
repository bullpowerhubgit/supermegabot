"""
High-Ticket Onboarding System
================================
Verwaltet den White-Glove Onboarding-Prozess für neue HT-Kunden:
- Onboarding-Checkliste mit Steps
- Automatische Telegram-Updates
- Account-Verbindungs-Status
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("ht_onboarding")

ONBOARDING_STEPS = [
    {"id": "shopify",    "title": "Shopify-Account verbinden",    "required": True,  "eta_min": 5},
    {"id": "stripe",     "title": "Stripe-Account verbinden",     "required": True,  "eta_min": 3},
    {"id": "telegram",   "title": "Telegram-Bot einrichten",      "required": True,  "eta_min": 2},
    {"id": "linkedin",   "title": "LinkedIn-Account verbinden",   "required": False, "eta_min": 5},
    {"id": "pinterest",  "title": "Pinterest-Account verbinden",  "required": False, "eta_min": 5},
    {"id": "instagram",  "title": "Instagram-Account verbinden",  "required": False, "eta_min": 5},
    {"id": "klaviyo",    "title": "Klaviyo-Account verbinden",    "required": False, "eta_min": 3},
    {"id": "ai_calibration", "title": "KI auf Business kalibrieren", "required": True, "eta_min": 60},
    {"id": "first_sync", "title": "Erster Produktsync",           "required": True,  "eta_min": 15},
    {"id": "go_live",    "title": "Autopilot aktivieren",         "required": True,  "eta_min": 1},
]


async def get_onboarding_status(client_email: str) -> dict:
    """Gibt den aktuellen Onboarding-Status für einen Client zurück."""
    steps_status = []
    completed = 0

    for step in ONBOARDING_STEPS:
        done = await _check_step_done(step["id"], client_email)
        steps_status.append({
            **step,
            "done": done,
            "status": "✅ Erledigt" if done else ("⏳ Offen" if step["required"] else "○ Optional"),
        })
        if done:
            completed += 1

    pct = round(completed / len(ONBOARDING_STEPS) * 100)
    return {
        "email": client_email,
        "progress_pct": pct,
        "completed_steps": completed,
        "total_steps": len(ONBOARDING_STEPS),
        "steps": steps_status,
        "ready_for_autopilot": pct >= 70,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def _check_step_done(step_id: str, email: str) -> bool:
    try:
        if step_id == "shopify":
            return bool(os.getenv("SHOPIFY_ADMIN_API_TOKEN") and os.getenv("SHOPIFY_SHOP_DOMAIN"))
        if step_id == "stripe":
            return bool(os.getenv("STRIPE_SECRET_KEY", "").startswith("sk_live_51Tg1U"))
        if step_id == "telegram":
            return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))
        if step_id == "klaviyo":
            return bool(os.getenv("KLAVIYO_API_KEY"))
        if step_id == "linkedin":
            return bool(os.getenv("LINKEDIN_ACCESS_TOKEN") or os.getenv("LINKEDIN_URN"))
        if step_id == "pinterest":
            tok = os.getenv("PINTEREST_ACCESS_TOKEN", "")
            return bool(tok and not tok.startswith("pina_AMAR"))
        if step_id == "instagram":
            return bool(os.getenv("INSTAGRAM_TOKEN_AIITEC") or os.getenv("FACEBOOK_PAGE_TOKEN"))
        if step_id == "ai_calibration":
            return bool(os.getenv("ANTHROPIC_API_KEY"))
        if step_id in ("first_sync", "go_live"):
            return bool(os.getenv("SHOPIFY_ADMIN_API_TOKEN"))
    except Exception:
        pass
    return False


async def send_onboarding_telegram(client_name: str, client_email: str, plan: str) -> bool:
    """Sendet Onboarding-Begrüßung per Telegram."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False

    status = await get_onboarding_status(client_email)
    completed = status["completed_steps"]
    total = status["total_steps"]

    msg = (
        f"🎉 <b>Neuer HT-Kunde: {client_name}</b>\n\n"
        f"📦 Plan: <b>{plan}</b>\n"
        f"📧 E-Mail: <code>{client_email}</code>\n\n"
        f"📋 Onboarding-Status: {completed}/{total} Steps\n"
    )
    for s in status["steps"][:5]:
        icon = "✅" if s["done"] else "○"
        msg += f"  {icon} {s['title']}\n"
    msg += "\n<i>→ Onboarding-Call innerhalb 48h planen!</i>"

    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as sess:
            r = await sess.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            )
            return r.status == 200
    except Exception as e:
        log.error("Telegram onboarding failed: %s", e)
        return False


async def get_onboarding_dashboard() -> dict:
    """Aggregierter Onboarding-Status für das Dashboard."""
    status = await get_onboarding_status("system")
    return {
        "system_onboarding_pct": status["progress_pct"],
        "steps_complete": status["completed_steps"],
        "steps_total": status["total_steps"],
        "ready": status["ready_for_autopilot"],
        "steps": [
            {"id": s["id"], "title": s["title"], "done": s["done"], "required": s["required"]}
            for s in status["steps"]
        ],
    }
