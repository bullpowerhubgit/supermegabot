#!/usr/bin/env python3
"""
eBay Autonomy — Finding API search + deal blast via BrutusCore.
Uses eBay Finding API (free, no OAuth for search).
"""
from __future__ import annotations

import asyncio
import logging
import os
import random

import aiohttp

log = logging.getLogger("eBayAutonomy")

EBAY_APP_ID   = os.getenv("EBAY_CLIENT_ID", "IRV7wFsqtKC76676391G2237LhVpgNCRZ1")
ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "bullpowerhub-21")
FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"

SHOP = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER = os.getenv("SHOPIFY_API_VERSION", "2024-10")
SHOPIFY_HEADERS = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

DEFAULT_KEYWORDS = [
    "streetwear t-shirt", "urban hoodie", "graphic tee men", "oversized shirt streetwear",
    "cyberpunk t-shirt", "hip hop tee", "skate shirt", "grunge hoodie",
    "neon streetwear", "urban fashion tee", "wolf shirt design", "dragon graphic tee",
]


async def _ai(prompt: str, max_tokens: int = 300) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def search_trending_ebay(keywords: list = None, count: int = 5) -> list:
    """eBay Finding API — hot items search."""
    keywords = keywords or DEFAULT_KEYWORDS
    kw = random.choice(keywords)
    items = []
    try:
        params = {
            "OPERATION-NAME": "findItemsByKeywords",
            "SERVICE-VERSION": "1.0.0",
            "SECURITY-APPNAME": EBAY_APP_ID,
            "RESPONSE-DATA-FORMAT": "JSON",
            "REST-PAYLOAD": "",
            "keywords": kw,
            "paginationInput.entriesPerPage": str(count),
            "itemFilter(0).name": "ListingType",
            "itemFilter(0).value": "FixedPrice",
            "itemFilter(1).name": "Condition",
            "itemFilter(1).value": "New",
            "sortOrder": "BestMatch",
            "outputSelector": "PictureURLSuperSize",
            "GLOBAL-ID": "EBAY-DE",
        }
        async with aiohttp.ClientSession() as s:
            async with s.get(FINDING_URL, params=params,
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json()
        search_result = (
            data.get("findItemsByKeywordsResponse", [{}])[0]
               .get("searchResult", [{}])[0]
               .get("item", [])
        )
        for item in search_result[:count]:
            title = item.get("title", [""])[0]
            url = item.get("viewItemURL", [""])[0]
            price_info = item.get("sellingStatus", [{}])[0].get("currentPrice", [{}])[0]
            price = price_info.get("__value__", "")
            currency = price_info.get("@currencyId", "EUR")
            image = item.get("pictureURLSuperSize", item.get("galleryURL", [""]))[0] if item.get("pictureURLSuperSize") or item.get("galleryURL") else ""
            items.append({
                "title": title[:120],
                "url": url,
                "price": f"{price} {currency}",
                "image": image,
                "keyword": kw,
            })
    except Exception as e:
        log.warning("eBay Finding API error: %s", e)

    # Fallback: manuell kuratierte eBay-Deals (immer verfügbar)
    if not items:
        fallback = [
            {"title": "Smart Home Steckdose WiFi", "url": f"https://www.ebay.de/sch/i.html?_nkw=smart+home+steckdose&tag={ASSOCIATE_TAG}", "price": "ca. €15-25 EUR", "image": "", "keyword": kw},
            {"title": "Bluetooth Kopfhörer In-Ear", "url": f"https://www.ebay.de/sch/i.html?_nkw=bluetooth+kopfhörer&tag={ASSOCIATE_TAG}", "price": "ca. €20-50 EUR", "image": "", "keyword": kw},
            {"title": "USB-C Hub Multiport Adapter", "url": f"https://www.ebay.de/sch/i.html?_nkw=usb+c+hub&tag={ASSOCIATE_TAG}", "price": "ca. €25-45 EUR", "image": "", "keyword": kw},
            {"title": "LED Strip WiFi Alexa", "url": f"https://www.ebay.de/sch/i.html?_nkw=led+strip+wifi&tag={ASSOCIATE_TAG}", "price": "ca. €10-20 EUR", "image": "", "keyword": kw},
            {"title": "Fitness Tracker Smartwatch 2026", "url": f"https://www.ebay.de/sch/i.html?_nkw=fitness+tracker&tag={ASSOCIATE_TAG}", "price": "ca. €30-80 EUR", "image": "", "keyword": kw},
        ]
        items = random.sample(fallback, min(count, len(fallback)))
    return items


async def blast_ebay_deals(count: int = 5) -> dict:
    """Find eBay items → AI content → BrutusCore blast."""
    items = await search_trending_ebay(count=count)
    if not items:
        return {"ok": False, "error": "no eBay items found", "blasted": 0}

    blasted = 0
    for item in items:
        try:
            prompt = f"""Kurzer Deutsch-Deal-Text (2-3 Sätze) für eBay-Angebot:
Produkt: "{item['title']}"
Preis: {item['price']}
Link: {item['url']}
Keine erfundenen Preise. Endet mit dem Link."""
            content = await _ai(prompt, max_tokens=150)
            if not content:
                content = f"Top-Deal: {item['title']} — {item['price']}\n{item['url']}"

            from modules.brutus_core import fire
            await fire(
                f"eBay Deal: {item['title'][:60]}",
                content,
                link=item["url"],
                channels=["telegram", "slack", "discord"],
            )
            blasted += 1
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("eBay blast error for '%s': %s", item.get("title", "")[:40], e)

    return {"ok": True, "blasted": blasted, "items_found": len(items)}


async def sync_shopify_to_ebay(limit: int = 10) -> dict:
    """Pull Shopify products and log them (eBay Trading API requires full OAuth setup)."""
    if not SHOP or not SHOPIFY_TOKEN:
        return {"ok": False, "error": "no Shopify credentials"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOP}/admin/api/{SHOPIFY_VER}/products.json",
                headers=SHOPIFY_HEADERS,
                params={"limit": limit, "status": "active"},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                data = await r.json()
        products = data.get("products", [])
        log.info("Shopify→eBay sync: %d products ready for listing", len(products))
        return {"ok": True, "products_ready": len(products),
                "note": "eBay Trading API OAuth required for actual listing — synced to log"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def run_ebay_cycle() -> dict:
    """Scheduler entry point."""
    blast = await blast_ebay_deals(count=3)
    sync = await sync_shopify_to_ebay(limit=5)
    return {"ok": True, "blast": blast, "sync": sync}
