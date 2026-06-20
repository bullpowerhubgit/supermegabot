#!/usr/bin/env python3
"""
Klaviyo Autonomy — Campaigns, event tracking, weekly newsletter, flow triggers.
API: https://a.klaviyo.com/api/ (revision: 2024-02-15)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import aiohttp

log = logging.getLogger("KlaviyoAutonomy")

API_KEY = os.getenv("KLAVIYO_API_KEY", "pk_VaCYq3_242945f7521ac82039ed5dbf7ff8e6cf1c")
LIST_ID = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
BASE = "https://a.klaviyo.com/api"
REVISION = "2024-02-15"

SHOP = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER = os.getenv("SHOPIFY_API_VERSION", "2024-10")


def _headers() -> dict:
    return {
        "Authorization": f"Klaviyo-API-Key {API_KEY}",
        "revision": REVISION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _kv_get(path: str) -> dict:
    if not API_KEY:
        return {}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{BASE}{path}", headers=_headers(),
                         timeout=aiohttp.ClientTimeout(total=15)) as r:
            return await r.json() if r.status < 400 else {"error": await r.text()}


async def _kv_post(path: str, data: dict) -> dict:
    if not API_KEY:
        return {"error": "no KLAVIYO_API_KEY"}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{BASE}{path}", headers=_headers(), json=data,
                          timeout=aiohttp.ClientTimeout(total=20)) as r:
            return await r.json() if r.status < 400 else {"error": await r.text()}


async def _ai(prompt: str, max_tokens: int = 600) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def get_list_profiles() -> dict:
    """GET /lists/{list_id}/relationships/profiles/"""
    try:
        data = await _kv_get(f"/lists/{LIST_ID}/relationships/profiles/")
        profiles = data.get("data", [])
        return {"ok": True, "count": len(profiles)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def track_event(email: str, event_name: str, properties: dict) -> dict:
    """POST /events/ — track custom event for a profile."""
    if not API_KEY:
        return {"ok": False, "error": "no KLAVIYO_API_KEY"}
    try:
        payload = {
            "data": {
                "type": "event",
                "attributes": {
                    "properties": properties,
                    "time": datetime.now(timezone.utc).isoformat(),
                    "value": properties.get("value", 0),
                    "metric": {
                        "data": {
                            "type": "metric",
                            "attributes": {"name": event_name},
                        }
                    },
                    "profile": {
                        "data": {
                            "type": "profile",
                            "attributes": {"email": email},
                        }
                    },
                },
            }
        }
        result = await _kv_post("/events/", payload)
        success = "errors" not in result
        return {"ok": success, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def create_campaign(name: str, subject: str, html_content: str) -> dict:
    """Create a Klaviyo email campaign."""
    if not API_KEY:
        return {"ok": False, "error": "no KLAVIYO_API_KEY"}
    try:
        # Step 1: Create campaign
        campaign_payload = {
            "data": {
                "type": "campaign",
                "attributes": {
                    "name": name[:100],
                    "audiences": {
                        "included": [{"type": "list", "id": LIST_ID}],
                    },
                    "send_strategy": {
                        "method": "immediate",
                    },
                },
            }
        }
        campaign = await _kv_post("/campaigns/", campaign_payload)
        cid = campaign.get("data", {}).get("id")
        if not cid:
            return {"ok": False, "error": campaign.get("error", "campaign creation failed")}

        # Step 2: Create message (template)
        msg_payload = {
            "data": {
                "type": "campaign-message",
                "attributes": {
                    "channel": "email",
                    "content": {
                        "subject": subject[:150],
                        "preview_text": name[:100],
                        "from_email": os.getenv("FROM_EMAIL", "hello@ineedit.com.co"),
                        "from_label": "BullPowerHub",
                        "body": html_content,
                    },
                },
                "relationships": {
                    "campaign": {"data": {"type": "campaign", "id": cid}},
                },
            }
        }
        await _kv_post("/campaign-messages/", msg_payload)

        # Step 3: Schedule/send
        send_payload = {
            "data": {
                "type": "campaign-send-job",
                "attributes": {},
                "relationships": {
                    "campaign": {"data": {"type": "campaign", "id": cid}},
                },
            }
        }
        await _kv_post("/campaign-send-jobs/", send_payload)

        log.info("Klaviyo campaign sent: %s (id=%s)", name[:60], cid)
        return {"ok": True, "campaign_id": cid, "name": name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def send_product_blast(products: list) -> dict:
    """AI email for products → create_campaign → send."""
    if not products:
        return {"ok": False, "error": "no products"}
    try:
        shop_url = f"https://{SHOP}" if SHOP else "https://ineedit.com.co"
        product_list = "\n".join(
            f"- {p.get('title', 'Product')}"
            for p in products[:5]
        )
        prompt = f"""Schreibe einen kurzen deutschen E-Mail-Kampagnen-Text (HTML) für Klaviyo:
Produkte:
{product_list}
Shop: {shop_url}

Format: kurze HTML-Mail mit Headline, 2 Sätze Einleitung, Produktliste, CTA-Button.
Kein DOCTYPE, nur body content."""
        html = await _ai(prompt, max_tokens=600)
        if not html:
            html = f"<h2>Neue Produkte!</h2><p>Jetzt im Shop:</p><a href='{shop_url}' style='background:#e63946;color:#fff;padding:12px 24px;text-decoration:none;border-radius:4px'>Zum Shop</a>"

        name = f"Product Blast {datetime.now().strftime('%Y-%m-%d')}"
        subject = f"Neue Highlights — {datetime.now().strftime('%d.%m.%Y')}"
        return await create_campaign(name, subject, html)
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def trigger_flow_event(event: str, properties: dict = None) -> dict:
    """Fire a Klaviyo metric event to trigger flows."""
    return await track_event(
        email=os.getenv("FROM_EMAIL", "hello@ineedit.com.co"),
        event_name=event,
        properties=properties or {"source": "supermegabot"},
    )


async def _get_recent_shopify_products(limit: int = 5) -> list:
    if not SHOP or not SHOPIFY_TOKEN:
        return []
    try:
        headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOP}/admin/api/{SHOPIFY_VER}/products.json",
                headers=headers,
                params={"limit": limit, "status": "active"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
        return data.get("products", [])
    except Exception:
        return []


async def send_weekly_newsletter() -> dict:
    """Fetch Shopify trending products → AI content → Klaviyo campaign."""
    try:
        products = await _get_recent_shopify_products(5)
        result = await send_product_blast(products)

        if result.get("ok"):
            await trigger_flow_event("Weekly Newsletter Sent", {
                "product_count": len(products),
                "date": datetime.now().strftime("%Y-%m-%d"),
            })
            try:
                from modules.brutus_core import fire
                await fire("Klaviyo Newsletter gesendet",
                           f"{len(products)} Produkte featured",
                           channels=["telegram", "slack"])
            except Exception:
                pass
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def run_klaviyo_cycle() -> dict:
    """Scheduler entry point."""
    newsletter = await send_weekly_newsletter()
    return {"ok": True, "newsletter": newsletter}
