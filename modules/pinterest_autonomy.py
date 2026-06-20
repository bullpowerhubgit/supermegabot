#!/usr/bin/env python3
"""
Pinterest Autonomy — Shopify-Produkte → Pinterest Pins, virale Pin-Texte, Traffic.
Mit Token: echte Pinterest API v5. Ohne: KI Pin-Content + Kanal-Promotion.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random

import aiohttp

log = logging.getLogger("PinterestAutonomy")

PINTEREST_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", "")
PINTEREST_BOARD = os.getenv("PINTEREST_BOARD_ID", "")
SHOP = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER   = os.getenv("SHOPIFY_API_VERSION", "2024-10")
SHOP_URL      = os.getenv("SHOPIFY_SHOP_URL", "https://autopilot-store-suite-fmbka.myshopify.com")

PINTEREST_BASE = "https://api.pinterest.com/v5"

PIN_NICHES = [
    "home decor ideas", "fitness motivation", "smart gadgets 2026",
    "kitchen must-haves", "budget fashion finds", "desk setup goals",
    "beauty essentials", "travel accessories", "pet products",
    "self improvement tips",
]

PIN_TEMPLATES = [
    "✨ {title} — Save this for later!",
    "💡 The {title} everyone is talking about",
    "🛍️ {title} — Found the best deal!",
    "⭐ Why you NEED {title} in your life",
    "🔥 {title} — Under €{price}!",
]


async def _ai(prompt: str, max_tokens: int = 300) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _get_shopify_products(limit: int = 20) -> list:
    if not SHOP or not SHOPIFY_TOKEN:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOP}/admin/api/{SHOPIFY_VER}/products.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                params={"limit": limit, "status": "active"},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                data = await r.json()
        return data.get("products", [])
    except Exception:
        return []


async def create_pin(title: str, desc: str, image_url: str, link: str) -> dict:
    """Erstellt einen Pinterest Pin via API v5."""
    if not PINTEREST_TOKEN:
        return {"ok": False, "error": "no PINTEREST_ACCESS_TOKEN",
                "note": "Set PINTEREST_ACCESS_TOKEN in Railway"}
    try:
        payload = {
            "board_id": PINTEREST_BOARD,
            "title": title[:100],
            "description": desc[:500],
            "link": link,
            "media_source": {"source_type": "image_url", "url": image_url} if image_url else None,
        }
        if not payload["media_source"]:
            del payload["media_source"]

        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{PINTEREST_BASE}/pins",
                headers={"Authorization": f"Bearer {PINTEREST_TOKEN}",
                         "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                data = await r.json()

        if "id" in data:
            return {"ok": True, "pin_id": data["id"], "title": title[:50]}
        return {"ok": False, "error": str(data)[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def auto_pin_products(limit: int = 5) -> dict:
    """Alle Shopify-Produkte → Pinterest Pins (mit Token) oder Promo (ohne)."""
    products = await _get_shopify_products(limit)
    pinned = 0
    pin_content = []

    for product in products[:limit]:
        try:
            title = product.get("title", "")[:60]
            image = (product.get("images") or [{}])[0].get("src", "")
            handle = product.get("handle", "")
            link = f"{SHOP_URL}/products/{handle}" if handle else SHOP_URL
            price = (product.get("variants") or [{}])[0].get("price", "29.99")

            # KI: Pin-Beschreibung
            desc = await generate_pin_description(title, price)

            if PINTEREST_TOKEN and PINTEREST_BOARD:
                result = await create_pin(title, desc, image, link)
                if result.get("ok"):
                    pinned += 1
            else:
                pin_content.append({"title": title, "desc": desc, "link": link})

            await asyncio.sleep(1)
        except Exception as e:
            log.debug("Pin error for %s: %s", product.get("title","")[:30], e)

    # Ohne Token: via BrutusCore promoten
    if pin_content:
        try:
            from modules.brutus_core import fire
            preview = pin_content[0]
            await fire(
                f"Pinterest Pin: {preview['title']}",
                f"📌 {preview['desc']}\n\n👉 {preview['link']}",
                link=preview["link"],
                channels=["telegram", "slack"]
            )
        except Exception:
            pass

    return {"ok": True, "mode": "api" if PINTEREST_TOKEN else "promo_only",
            "pinned": pinned, "products_processed": len(products),
            "pin_content_generated": len(pin_content)}


async def generate_pin_description(title: str, price: str = "") -> str:
    """KI schreibt viral-optimierte Pinterest Pin-Beschreibung."""
    template = random.choice(PIN_TEMPLATES).format(title=title, price=price or "25")
    prompt = f"""Write a viral Pinterest pin description for: "{title}" {'priced at €'+price if price else ''}
Style: inspiring, benefit-focused, 2-3 sentences
Include: save/pin CTA, relevant emojis, shop link hint
End with: Shop now → {SHOP_URL}
Max 80 words, English."""
    desc = await _ai(prompt, 120)
    return desc or f"{template}\n\nShop now → {SHOP_URL}"


async def generate_pin_descriptions(count: int = 5) -> dict:
    """Generiert Pin-Beschreibungen für verschiedene Produkt-Nischen."""
    descriptions = []
    niches = random.sample(PIN_NICHES, min(count, len(PIN_NICHES)))
    for niche in niches:
        desc = await generate_pin_description(niche)
        descriptions.append({"niche": niche, "description": desc})
        await asyncio.sleep(0.5)
    return {"ok": True, "count": len(descriptions), "descriptions": descriptions}


async def run_pinterest_cycle() -> dict:
    """Scheduler-Einstiegspunkt."""
    pins = await auto_pin_products(limit=5)
    descs = await generate_pin_descriptions(count=3)
    return {"ok": True, "pinned": pins.get("pinned", 0),
            "descriptions": descs.get("count", 0)}
