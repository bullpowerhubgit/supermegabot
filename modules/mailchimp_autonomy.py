#!/usr/bin/env python3
"""
Mailchimp Autonomy — Campaign creation, weekly digest, product blasts.
API: https://us7.api.mailchimp.com/3.0/
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("MailchimpAutonomy")

API_KEY = os.getenv("MAILCHIMP_API_KEY", "")
LIST_ID = os.getenv("MAILCHIMP_LIST_ID", "606e45a6b0")
SERVER = os.getenv("MAILCHIMP_SERVER_PREFIX", os.getenv("MAILCHIMP_SERVER", "us7"))
BASE = f"https://{SERVER}.api.mailchimp.com/3.0"
FROM_EMAIL = os.getenv("FROM_EMAIL", "aiitecbuuss@gmail.com")
FROM_NAME = os.getenv("MAILCHIMP_FROM_NAME", "DragonApp")

# DragonApp Mailchimp (dragonadnp@gmail.com) — separate account us18
DRAGON_API_KEY = os.getenv("MAILCHIMP_DRAGON_API_KEY", "")
DRAGON_LIST_ID = os.getenv("MAILCHIMP_DRAGON_LIST_ID", "0e84a22a44")
DRAGON_SERVER  = os.getenv("MAILCHIMP_DRAGON_SERVER", "us18")
DRAGON_BASE    = f"https://{DRAGON_SERVER}.api.mailchimp.com/3.0"
DRAGON_FROM    = os.getenv("MAILCHIMP_DRAGON_EMAIL", "dragonadnp@gmail.com")

SHOP = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER = os.getenv("SHOPIFY_API_VERSION", "2024-10")


def _auth() -> dict:
    creds = base64.b64encode(f"anystring:{API_KEY}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}


async def _mc_get(path: str) -> dict:
    if not API_KEY:
        return {}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{BASE}{path}", headers=_auth(),
                         timeout=aiohttp.ClientTimeout(total=15)) as r:
            return await r.json() if r.status < 400 else {"error": await r.text()}


async def _mc_post(path: str, data: dict) -> dict:
    if not API_KEY:
        return {"error": "no MAILCHIMP_API_KEY"}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{BASE}{path}", headers=_auth(), json=data,
                          timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status == 204:
                return {"ok": True, "status": 204}
            return await r.json() if r.status < 400 else {"error": await r.text()}


async def _mc_put(path: str, data: dict) -> dict:
    if not API_KEY:
        return {}
    async with aiohttp.ClientSession() as s:
        async with s.put(f"{BASE}{path}", headers=_auth(), json=data,
                         timeout=aiohttp.ClientTimeout(total=20)) as r:
            return await r.json()


async def _ai(prompt: str, max_tokens: int = 600) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def get_list_stats() -> dict:
    """GET list stats."""
    data = await _mc_get(f"/lists/{LIST_ID}")
    stats = data.get("stats", {})
    return {
        "ok": bool(data.get("id")),
        "member_count": stats.get("member_count", 0),
        "open_rate": stats.get("open_rate", 0),
        "click_rate": stats.get("click_rate", 0),
        "campaign_count": stats.get("campaign_count", 0),
    }


_mc_campaign_dates: list = []

async def create_campaign(subject: str, html_body: str, from_name: str = FROM_NAME) -> dict:
    """Create + fill + send a Mailchimp campaign."""
    if not API_KEY:
        return {"ok": False, "error": "no MAILCHIMP_API_KEY"}
    if os.getenv("MAILCHIMP_AUTOMATION_ENABLED", "true").lower() in ("false", "0", "off"):
        return {"ok": False, "error": "Mailchimp automation disabled"}
    # Rate limit: max 1 campaign per day
    max_per_day = int(os.getenv("MAILCHIMP_MAX_CAMPAIGNS_PER_DAY", "1"))
    today = datetime.now(timezone.utc).date().isoformat()
    today_count = sum(1 for d in _mc_campaign_dates if d == today)
    if today_count >= max_per_day:
        return {"ok": False, "error": f"Daily limit reached ({max_per_day}/day) — skipped"}
    _mc_campaign_dates.append(today)
    try:
        # 1. Create campaign
        campaign_data = {
            "type": "regular",
            "recipients": {"list_id": LIST_ID},
            "settings": {
                "subject_line": subject[:150],
                "title": f"Campaign {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "from_name": from_name,
                "reply_to": FROM_EMAIL,
            },
        }
        camp = await _mc_post("/campaigns", campaign_data)
        cid = camp.get("id")
        if not cid:
            return {"ok": False, "error": camp.get("error", "campaign creation failed")}

        # 2. Set content
        await _mc_put(f"/campaigns/{cid}/content", {"html": html_body})

        # 3. Send
        send_result = await _mc_post(f"/campaigns/{cid}/actions/send", {})
        success = "status" not in send_result or send_result.get("status") != 400

        log.info("Mailchimp campaign sent: %s (id=%s)", subject[:60], cid)
        return {"ok": success, "campaign_id": cid, "subject": subject}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def send_product_campaign(products: list) -> dict:
    """AI email for given products → send campaign."""
    if not products:
        return {"ok": False, "error": "no products"}
    try:
        product_list = "\n".join(
            f"- {p.get('title', p.get('name', 'Product'))}: €{p.get('price', p.get('amount', ''))}"
            for p in products[:5]
        )
        shop_url = f"https://{SHOP}" if SHOP else "https://autopilot-store-suite-fmbka.myshopify.com"
        prompt = f"""Schreibe einen HTML-Newsletter (Mailchimp-kompatibel) auf Deutsch für diese Produkte:

{product_list}

Shop: {shop_url}

Format: professionell, responsive HTML mit:
- Headline h1
- Kurze Einleitung
- Produktliste mit Preisen
- CTA Button "Jetzt kaufen"
Nur HTML body content, kein <!DOCTYPE html>."""
        html = await _ai(prompt, max_tokens=800)
        if not html:
            html = f"<h1>Neue Produkte!</h1><p>Entdecke unsere neuesten Angebote im Shop.</p><a href='{shop_url}'>Jetzt kaufen</a>"

        subject = f"Neue Produkte bei BullPowerHub — {datetime.now().strftime('%d.%m.%Y')}"
        return await create_campaign(subject, html)
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _get_shopify_stats() -> dict:
    """Quick Shopify stats for digest."""
    if not SHOP or not SHOPIFY_TOKEN:
        return {}
    try:
        headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOP}/admin/api/{SHOPIFY_VER}/orders.json",
                headers=headers,
                params={"limit": 50, "status": "any", "financial_status": "paid"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
        orders = data.get("orders", [])
        total = sum(float(o.get("total_price", 0)) for o in orders)
        return {"orders": len(orders), "revenue": round(total, 2)}
    except Exception:
        return {}


async def send_weekly_digest() -> dict:
    """Shopify stats + DS24 revenue → AI email → send to list."""
    try:
        shopify = await _get_shopify_stats()
        shop_url = f"https://{SHOP}" if SHOP else "https://autopilot-store-suite-fmbka.myshopify.com"

        prompt = f"""Schreibe einen wöchentlichen HTML-Newsletter-Digest auf Deutsch für BullPowerHub:

Shopify: {shopify.get('orders', 0)} Bestellungen, €{shopify.get('revenue', 0):.2f} Umsatz (letzte 50 Bestellungen)
Shop: {shop_url}

Format: Professioneller HTML-Newsletter mit:
- "Wöchentlicher Rückblick" Headline
- Highlights der Woche
- Shop-CTA "Jetzt kaufen"
- Motivierender Abschluss
Nur HTML body content."""
        html = await _ai(prompt, max_tokens=700)
        if not html:
            html = f"<h1>Wöchentlicher Rückblick</h1><p>Diese Woche: {shopify.get('orders',0)} Bestellungen!</p><a href='{shop_url}'>Jetzt kaufen</a>"

        subject = f"Wochenbericht BullPowerHub — {datetime.now().strftime('%d.%m.%Y')}"
        result = await create_campaign(subject, html)

        if result.get("ok"):
            try:
                from modules.brutus_core import fire
                await fire("Mailchimp Weekly Digest gesendet",
                           f"{shopify.get('orders',0)} Orders diese Woche",
                           channels=["telegram", "slack"])
            except Exception as _e:
                log.debug("skipped: %s", _e)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def auto_welcome_sequence() -> dict:
    """Check if welcome automation exists, log status."""
    try:
        data = await _mc_get("/automations")
        automations = data.get("automations", [])
        welcome = [a for a in automations if "welcome" in a.get("settings", {}).get("title", "").lower()]
        return {"ok": True, "welcome_automations": len(welcome),
                "total_automations": len(automations)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def run_mailchimp_cycle() -> dict:
    """Scheduler entry point: weekly digest."""
    digest = await send_weekly_digest()
    dragon = await run_dragon_campaign()
    return {"ok": True, "digest": digest, "dragon": dragon}


# ─── DragonApp Mailchimp (dragonadnp@gmail.com / us18) ───────────────────────

def _dragon_auth() -> dict:
    creds = base64.b64encode(f"anystring:{DRAGON_API_KEY}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}


async def _dragon_get(path: str) -> dict:
    if not DRAGON_API_KEY:
        return {}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{DRAGON_BASE}{path}", headers=_dragon_auth(),
                         timeout=aiohttp.ClientTimeout(total=15)) as r:
            return await r.json() if r.status < 400 else {"error": await r.text()}


async def _dragon_post(path: str, data: dict) -> dict:
    if not DRAGON_API_KEY:
        return {"error": "no MAILCHIMP_DRAGON_API_KEY"}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{DRAGON_BASE}{path}", headers=_dragon_auth(), json=data,
                          timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status == 204:
                return {"ok": True, "status": 204}
            return await r.json() if r.status < 400 else {"error": await r.text()}


async def _dragon_put(path: str, data: dict) -> dict:
    if not DRAGON_API_KEY:
        return {}
    async with aiohttp.ClientSession() as s:
        async with s.put(f"{DRAGON_BASE}{path}", headers=_dragon_auth(), json=data,
                         timeout=aiohttp.ClientTimeout(total=20)) as r:
            return await r.json()


async def get_dragon_status() -> dict:
    """Status of DragonApp Mailchimp account."""
    try:
        data = await _dragon_get(f"/lists/{DRAGON_LIST_ID}")
        if "id" not in data:
            return {"ok": False, "connected": False, "error": data.get("error", "no list")}
        stats = data.get("stats", {})
        return {
            "ok": True,
            "connected": True,
            "account": "dragonadnp@gmail.com",
            "list_id": DRAGON_LIST_ID,
            "list_name": data.get("name"),
            "member_count": stats.get("member_count", 0),
            "open_rate": stats.get("open_rate", 0),
            "campaign_count": stats.get("campaign_count", 0),
        }
    except Exception as e:
        return {"ok": False, "connected": False, "error": str(e)}


async def dragon_subscribe(email: str, first_name: str = "", last_name: str = "") -> dict:
    """Subscribe email to DragonApp Mailchimp list."""
    try:
        data = {
            "email_address": email,
            "status": "subscribed",
            "merge_fields": {"FNAME": first_name, "LNAME": last_name},
        }
        result = await _dragon_put(f"/lists/{DRAGON_LIST_ID}/members/{email}", data)
        return {"ok": bool(result.get("id")), "email": email, "account": "dragon"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def run_dragon_campaign(topic: str = "") -> dict:
    """Create + send campaign via DragonApp Mailchimp."""
    if not DRAGON_API_KEY:
        return {"ok": False, "error": "MAILCHIMP_DRAGON_API_KEY not set"}
    if os.getenv("MAILCHIMP_AUTOMATION_ENABLED", "true").lower() in ("false", "0", "off"):
        return {"ok": False, "error": "Mailchimp automation disabled — TOS violation fix pending"}
    try:
        ds24 = os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/668035")
        shop = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
        shop_url = f"https://{shop}"
        subject_topic = topic or "KI-Business Automatisierung 2026"

        html = await _ai(
            f"Schreibe einen professionellen HTML-Newsletter auf Deutsch über: {subject_topic}. "
            f"Shop: {shop_url}. Affiliate: {ds24}. Responsives HTML, kein DOCTYPE.",
            max_tokens=600,
        )
        if not html:
            html = (
                f"<h1>{subject_topic}</h1>"
                f"<p>Entdecke die neuesten KI-Tools für dein Business.</p>"
                f"<p><a href='{ds24}'>Jetzt starten →</a></p>"
                f"<p>Shop: <a href='{shop_url}'>{shop_url}</a></p>"
            )

        subject = f"{subject_topic} — {datetime.now().strftime('%d.%m.%Y')}"
        campaign_data = {
            "type": "regular",
            "recipients": {"list_id": DRAGON_LIST_ID},
            "settings": {
                "subject_line": subject[:150],
                "title": f"Dragon Campaign {datetime.now().strftime('%Y-%m-%d')}",
                "from_name": "DragonApp",
                "reply_to": DRAGON_FROM,
            },
        }
        camp = await _dragon_post("/campaigns", campaign_data)
        cid = camp.get("id")
        if not cid:
            return {"ok": False, "error": camp.get("error", "campaign creation failed"), "account": "dragon"}

        await _dragon_put(f"/campaigns/{cid}/content", {"html": html})
        send_result = await _dragon_post(f"/campaigns/{cid}/actions/send", {})
        success = "status" not in send_result or send_result.get("status") != 400
        log.info("Dragon Mailchimp campaign sent: %s (id=%s)", subject[:60], cid)
        return {"ok": success, "campaign_id": cid, "subject": subject, "account": "dragon"}
    except Exception as e:
        return {"ok": False, "error": str(e), "account": "dragon"}
