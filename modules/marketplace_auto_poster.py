#!/usr/bin/env python3
"""
Marketplace Auto Poster — eBay + Amazon + AliExpress Streetwear Automation
Fetches latest Printify products → posts with marketplace cross-links to Telegram/social
Also runs autonomous eBay/Amazon affiliate deal blasts for streetwear
"""
import asyncio
import logging
import os
import random
from typing import Dict, List

import aiohttp

log = logging.getLogger("MarketplacePoster")

SHOP_DOMAIN   = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
TG_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT       = os.getenv("TELEGRAM_CHAT_ID", "")
EBAY_APP_ID   = os.getenv("EBAY_CLIENT_ID", "IRV7wFsqtKC76676391G2237LhVpgNCRZ1")
AMZN_TAG      = os.getenv("AMAZON_ASSOCIATE_TAG", "bullpowerhub-21")
DS24_AFFIL    = os.getenv("DS24_AFFILIATE_ID", "user37405262")
STORE_URL     = f"https://{SHOP_DOMAIN}" if SHOP_DOMAIN else ""

STREETWEAR_KW = [
    "streetwear t-shirt", "urban hoodie", "graphic tee men streetwear",
    "cyberpunk shirt", "hip hop tee", "skate t-shirt", "grunge hoodie",
    "neon streetwear", "wolf graphic shirt", "dragon urban tee",
    "oversized streetwear hoodie", "eagle street shirt",
]


# ── Telegram sender ───────────────────────────────────────────────────────────

async def _tg(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": text,
                      "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json(content_type=None)
        return d.get("ok", False)
    except Exception as e:
        log.warning("TG error: %s", e)
        return False


# ── Shopify: get latest Printify products ─────────────────────────────────────

async def _get_printify_products(limit: int = 5) -> List[Dict]:
    if not SHOP_DOMAIN or not SHOPIFY_TOKEN:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOP_DOMAIN}/admin/api/2024-10/products.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                params={"limit": limit * 2, "status": "active",
                        "vendor": "Printify",
                        "fields": "id,title,handle,images,variants"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
        products = [p for p in data.get("products", []) if p.get("images")]
        return products[:limit]
    except Exception as e:
        log.error("Shopify fetch: %s", e)
        return []


# ── eBay affiliate search links ───────────────────────────────────────────────

def _ebay_link(keyword: str) -> str:
    import urllib.parse
    kw = urllib.parse.quote(keyword)
    return f"https://www.ebay.de/sch/i.html?_nkw={kw}&_sop=12"


async def _ebay_search(keyword: str, count: int = 3) -> List[Dict]:
    """eBay Finding API for streetwear keyword."""
    items = []
    try:
        params = {
            "OPERATION-NAME": "findItemsByKeywords",
            "SERVICE-VERSION": "1.0.0",
            "SECURITY-APPNAME": EBAY_APP_ID,
            "RESPONSE-DATA-FORMAT": "JSON",
            "REST-PAYLOAD": "",
            "keywords": keyword,
            "paginationInput.entriesPerPage": str(count),
            "itemFilter(0).name": "ListingType",
            "itemFilter(0).value": "FixedPrice",
            "sortOrder": "BestMatch",
            "GLOBAL-ID": "EBAY-DE",
        }
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://svcs.ebay.com/services/search/FindingService/v1",
                params=params,
                timeout=aiohttp.ClientTimeout(total=12),
            ) as r:
                data = await r.json()
        found = (data.get("findItemsByKeywordsResponse", [{}])[0]
                     .get("searchResult", [{}])[0]
                     .get("item", []))
        for item in found[:count]:
            title = item.get("title", [""])[0]
            url   = item.get("viewItemURL", [""])[0]
            price = item.get("sellingStatus", [{}])[0].get("currentPrice", [{}])[0].get("__value__", "")
            items.append({"title": title[:80], "url": url, "price": price})
    except Exception as e:
        log.debug("eBay search '%s' error: %s", keyword, e)
    return items


# ── Amazon affiliate links ────────────────────────────────────────────────────

def _amazon_link(keyword: str) -> str:
    import urllib.parse
    kw = urllib.parse.quote(keyword)
    return f"https://www.amazon.de/s?k={kw}&tag={AMZN_TAG}"


# ── AliExpress affiliate links ────────────────────────────────────────────────

def _ali_link(keyword: str) -> str:
    import urllib.parse
    kw = urllib.parse.quote(keyword)
    return f"https://www.aliexpress.com/wholesale?SearchText={kw}&sortType=total_tranQty_desc"


# ── Main: post Printify products with marketplace cross-links ─────────────────

async def post_printify_with_marketplace_links(count: int = 3) -> Dict:
    """Fetch newest Printify shirts → Telegram post mit eBay+Amazon+AliExpress Links."""
    products = await _get_printify_products(limit=count)
    if not products:
        return {"ok": False, "error": "no Printify products", "posted": 0}

    posted = 0
    for p in products:
        title   = p.get("title", "New Design")[:60]
        handle  = p.get("handle", "")
        img     = p.get("images", [{}])[0].get("src", "")
        variants = p.get("variants", [{}])
        price   = variants[0].get("price", "29.99") if variants else "29.99"
        shop_url = f"{STORE_URL}/products/{handle}"

        kw = random.choice(STREETWEAR_KW)
        ebay_url  = _ebay_link(kw)
        amzn_url  = _amazon_link(kw)
        ali_url   = _ali_link(kw)

        msg = (
            f"🔥 <b>{title}</b>\n"
            f"💶 Nur €{price} — Premium Print-on-Demand\n\n"
            f"👕 <a href='{shop_url}'>Jetzt kaufen (Shop)</a>\n\n"
            f"🔍 Ähnliche Styles:\n"
            f"  • <a href='{ebay_url}'>eBay Streetwear</a>\n"
            f"  • <a href='{amzn_url}'>Amazon Mode</a>\n"
            f"  • <a href='{ali_url}'>AliExpress Urban</a>"
        )

        ok = await _tg(msg)
        if ok:
            posted += 1
        await asyncio.sleep(3)

    return {"ok": posted > 0, "posted": posted, "total": len(products)}


# ── eBay deal blast (streetwear only) ─────────────────────────────────────────

async def run_ebay_streetwear_blast(count: int = 3) -> Dict:
    """Suche eBay nach Streetwear → Telegram Deal-Posts."""
    kw = random.choice(STREETWEAR_KW)
    items = await _ebay_search(kw, count=count)

    if not items:
        # Fallback mit Affiliate-Suchlink
        url = _ebay_link(kw)
        msg = (
            f"👕 <b>eBay Streetwear Deal</b>\n"
            f"Trending: <b>{kw.title()}</b>\n\n"
            f"🔗 <a href='{url}'>Jetzt auf eBay suchen</a>\n"
            f"🏪 <a href='{STORE_URL}'>Unser Shop: AIITEC Streetwear</a>"
        )
        ok = await _tg(msg)
        return {"ok": ok, "blasted": 1 if ok else 0, "source": "fallback"}

    blasted = 0
    for item in items[:2]:
        url  = item["url"]
        name = item["title"]
        price_str = f"€{item['price']}" if item.get("price") else ""
        msg = (
            f"🛒 <b>eBay Streetwear</b>\n"
            f"{name}\n"
            f"{price_str}\n\n"
            f"🔗 <a href='{url}'>eBay Deal ansehen</a>\n"
            f"🏪 Eigene Designs: <a href='{STORE_URL}'>AIITEC Store</a>"
        )
        ok = await _tg(msg)
        if ok:
            blasted += 1
        await asyncio.sleep(3)

    return {"ok": blasted > 0, "blasted": blasted, "keyword": kw}


# ── Amazon affiliate blast (streetwear only) ──────────────────────────────────

async def run_amazon_streetwear_blast() -> Dict:
    """Amazon Affiliate Streetwear Post → Telegram."""
    kw  = random.choice(STREETWEAR_KW)
    url = _amazon_link(kw)

    MSGS = [
        f"🛍️ <b>Amazon Streetwear Finds</b>\nTrending jetzt: <b>{kw.title()}</b>\n\n🔗 <a href='{url}'>Amazon Fashion entdecken →</a>\n🏪 Premium Print: <a href='{STORE_URL}'>AIITEC Store</a>",
        f"📦 <b>Amazon Mode Deals</b>\n{kw.title()} — Prime-Lieferung!\n\n👉 <a href='{url}'>Jetzt auf Amazon</a>\n✨ Exklusiv bei uns: <a href='{STORE_URL}'>AIITEC Streetwear</a>",
        f"⚡ <b>Amazon Streetwear</b>\n{kw.title()} — Bestseller 2026\n\n🔗 <a href='{url}'>Amazon Deal</a> | 🏪 <a href='{STORE_URL}'>Unser Shop</a>",
    ]
    msg = random.choice(MSGS)
    ok  = await _tg(msg)
    return {"ok": ok, "keyword": kw}


# ── AliExpress streetwear import + announce ───────────────────────────────────

async def run_aliexpress_streetwear_announce() -> Dict:
    """Post AliExpress streetwear search + link to own shop."""
    kw  = random.choice(STREETWEAR_KW)
    url = _ali_link(kw)

    msg = (
        f"🌏 <b>AliExpress Streetwear</b>\n"
        f"Trending: <b>{kw.title()}</b>\n\n"
        f"🔗 <a href='{url}'>AliExpress entdecken</a>\n"
        f"✅ Premium Alternative: <a href='{STORE_URL}'>AIITEC Streetwear Store</a>\n"
        f"(Print-on-Demand — Bella+Canvas Qualität)"
    )
    ok = await _tg(msg)
    return {"ok": ok, "keyword": kw}


# ── Full marketplace cycle ─────────────────────────────────────────────────────

async def run_full_marketplace_cycle() -> Dict:
    """Scheduler entry: rotiert durch alle Marketplace-Posts."""
    ACTIONS = [
        ("printify_cross", post_printify_with_marketplace_links),
        ("ebay_blast",     run_ebay_streetwear_blast),
        ("amazon_blast",   run_amazon_streetwear_blast),
        ("ali_announce",   run_aliexpress_streetwear_announce),
    ]
    name, fn = random.choice(ACTIONS)
    try:
        result = await fn()
        return {"ok": result.get("ok"), "action": name, "detail": result}
    except Exception as e:
        log.error("Marketplace cycle '%s' error: %s", name, e)
        return {"ok": False, "action": name, "error": str(e)}
