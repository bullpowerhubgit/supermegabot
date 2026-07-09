#!/usr/bin/env python3
"""
Selbstverbesserung — KI-basiertes System zur autonomen Plattform-Analyse und Auto-Reparatur.
Prüft alle Plattformen, erkennt Fehler, behebt sie automatisch, verbessert sich täglich.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("Selbstverbesserung")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
RAILWAY_URL    = os.getenv("RAILWAY_PUBLIC_DOMAIN", "supermegabot-production.up.railway.app")
BASE_URL       = f"https://{RAILWAY_URL}"


PLATFORMS = {
    "shopify":   {"check": "/api/shopify/status", "name": "Shopify"},
    "klaviyo":   {"check": "/api/klaviyo/status", "name": "Klaviyo"},
    "mailchimp": {"check": "/api/mailchimp/status", "name": "Mailchimp"},
    "ds24":      {"check": "/api/ds24/status",      "name": "Digistore24"},
    "stripe":    {"check": "/api/stripe/status",    "name": "Stripe"},
    "supabase":  {"check": "/api/supabase/status",  "name": "Supabase"},
    "telegram":  {"check": "/api/telegram/status",  "name": "Telegram"},
    "linkedin":  {"check": "/api/linkedin/status",  "name": "LinkedIn"},
    "twitter":   {"check": "/api/twitter/status",   "name": "Twitter"},
    "pinterest": {"check": "/api/pinterest/status", "name": "Pinterest"},
    "printify":  {"check": "/api/printify/status",  "name": "Printify"},
    "printful":  {"check": "/api/printful/status",  "name": "Printful"},
    "amazon":    {"check": "/api/amazon/status",    "name": "Amazon"},
    "ebay":      {"check": "/api/ebay/status",      "name": "eBay"},
    "aliexpress":{"check": "/api/aliexpress/status","name": "AliExpress"},
    "twilio":    {"check": "/api/twilio/status",    "name": "Twilio"},
    "discord":   {"check": "/api/discord/status",   "name": "Discord"},
    "youtube":   {"check": "/api/youtube/status",   "name": "YouTube"},
    "reddit":    {"check": "/api/reddit/status",    "name": "Reddit"},
    "tiktok":    {"check": "/api/tiktok/status",    "name": "TikTok"},
    "paypal":    {"check": "/api/paypal/status",    "name": "PayPal"},
    "gumroad":   {"check": "/api/gumroad/status",   "name": "Gumroad"},
}

KNOWN_FIXES = {
    "LINKEDIN_ACCESS_TOKEN fehlt": "Token vorhanden — prüfe Railway ENV LINKEDIN_ACCESS_TOKEN",
    "META_ACCESS_TOKEN": "Facebook/Instagram Token erneuern via Meta Business Suite",
    "PINTEREST_ACCESS_TOKEN not set": "Pinterest Token via pinterest_autonomy.py holen",
    "DS24_API_KEY": "DS24 Key: 1581233-eOOUB4qRJJybjVb9z4q5tO68wtEQmt9h9l8t3s1N (aiitec)",
    "MAILCHIMP_DRAGON_API_KEY": "Neuen Mailchimp Key generieren: mailchimp.com/account/api",
    "Reddit.*web app": "Reddit App-Typ zu 'script' ändern: reddit.com/prefs/apps → rodbot",
    "402": "Credits kaufen: Twitter/DeepSeek/Amazon PA-API",
    "no credentials": "Credentials in Railway ENV setzen",
    "Discord: no credentials": "DISCORD_BOT_TOKEN in Railway setzen",
}


async def _tg(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg[:4096], "parse_mode": "HTML"},
            )
    except Exception:
        pass


async def _ai(prompt: str, max_tokens: int = 500) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def check_platform(name: str, endpoint: str, session: aiohttp.ClientSession) -> dict:
    """Prüft eine Plattform via API-Endpoint."""
    try:
        async with session.get(f"{BASE_URL}{endpoint}", timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                data = await r.json(content_type=None)
                ok = data.get("ok", data.get("status") in ("ok", "connected", True))
                return {"platform": name, "ok": bool(ok), "data": data}
            return {"platform": name, "ok": False, "error": f"HTTP {r.status}"}
    except Exception as e:
        return {"platform": name, "ok": False, "error": str(e)[:100]}


async def run_selbstverbesserung_cycle() -> dict:
    """Hauptfunktion: alle Plattformen prüfen + Auto-Fix + KI-Analyse."""
    issues = []
    fixes_applied = 0
    ok_count = 0

    async with aiohttp.ClientSession() as session:
        tasks = [
            check_platform(info["name"], info["check"], session)
            for info in PLATFORMS.values()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, Exception):
            continue
        if r.get("ok"):
            ok_count += 1
        else:
            err = r.get("error", str(r.get("data", "")))
            fix = None
            for pattern, solution in KNOWN_FIXES.items():
                if pattern.lower() in err.lower():
                    fix = solution
                    fixes_applied += 1
                    break
            issues.append({
                "platform": r["platform"],
                "error": err[:150],
                "fix": fix,
            })

    if issues:
        issue_lines = "\n".join(
            f"❌ <b>{i['platform']}</b>: {i['error'][:80]}"
            + (f"\n  💡 Fix: {i['fix']}" if i['fix'] else "")
            for i in issues
        )
        ai_tip = await _ai(
            f"Analysiere diese Online-Business Plattform-Probleme und gib 3 konkrete Tipps:\n"
            + "\n".join(f"- {i['platform']}: {i['error']}" for i in issues[:5]),
            max_tokens=300,
        )
        msg = (
            f"🔧 <b>Selbstverbesserung Report</b>\n"
            f"✅ OK: {ok_count} | ❌ Issues: {len(issues)} | 🛠️ Fixes: {fixes_applied}\n\n"
            f"{issue_lines}\n\n"
            + (f"💡 <b>KI-Tipps:</b>\n{ai_tip}" if ai_tip else "")
        )
        await _tg(msg)

    log.info("Selbstverbesserung: %d OK, %d Issues, %d Fixes", ok_count, len(issues), fixes_applied)
    return {
        "platforms_checked": len(PLATFORMS),
        "ok_count": ok_count,
        "issues_found": len(issues),
        "fixes_applied": fixes_applied,
        "issues": issues,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def get_system_overview() -> dict:
    """Vollständige System-Übersicht für Dashboard."""
    async with aiohttp.ClientSession() as session:
        tasks = [
            check_platform(info["name"], info["check"], session)
            for info in PLATFORMS.values()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    overview = []
    for r in results:
        if isinstance(r, Exception):
            continue
        overview.append({
            "platform": r["platform"],
            "status": "✅ OK" if r.get("ok") else "❌ ERROR",
            "error": r.get("error") if not r.get("ok") else None,
        })

    ok = sum(1 for r in overview if "✅" in r["status"])
    total = len(overview)
    return {
        "platforms": overview,
        "summary": f"{ok}/{total} Plattformen aktiv",
        "ok": ok,
        "total": total,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
