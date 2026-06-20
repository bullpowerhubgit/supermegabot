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

API_KEY = os.getenv("MAILCHIMP_API_KEY", "1d35dd606aad1a9f1bbd10d2dd2e2ea7-us7")
LIST_ID = os.getenv("MAILCHIMP_LIST_ID", "606e45a6b0")
SERVER = os.getenv("MAILCHIMP_SERVER_PREFIX", os.getenv("MAILCHIMP_SERVER", "us7"))
BASE = f"https://{SERVER}.api.mailchimp.com/3.0"
FROM_EMAIL = os.getenv("FROM_EMAIL", "hello@ineedit.com.co")
FROM_NAME = "BullPowerHub"

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


async def create_campaign(subject: str, html_body: str, from_name: str = FROM_NAME) -> dict:
    """Create + fill + send a Mailchimp campaign."""
    if not API_KEY:
        return {"ok": False, "error": "no MAILCHIMP_API_KEY"}
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
            except Exception:
                pass
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
    return {"ok": True, "digest": digest}
