#!/usr/bin/env python3
"""
Marketplace Auto Poster — eBay + Amazon + AliExpress Smart Home/Gadgets Automation
Zwei getrennte Kanäle:
  1. Eigener Shop: Printify Streetwear Produkte → Telegram
  2. Marktplätze: Smart Home / Smart Garden / AI Gadgets → Telegram Deal-Posts
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
STORE_URL     = f"https://{SHOP_DOMAIN}" if SHOP_DOMAIN else ""

# Smart Home / Smart Garden / AI Gadgets — NUR für eBay/Amazon/AliExpress
SMART_HOME_KW = [
    "smart home steckdose wlan", "wifi smart plug energiemessen",
    "smart garden bewässerung", "zigbee gateway smart home",
    "led streifen wifi alexa", "tuya smart schalter",
    "smart thermostat heizung", "wlan zeitschaltuhr",
    "ki smart speaker", "home assistant hub",
    "smart home starter set", "smart home sensor bewegungsmelder",
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


# ── Shopify: get latest Printify products (streetwear) ────────────────────────

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


# ── Own shop: post Printify streetwear to Telegram ────────────────────────────

async def post_own_shop_streetwear(count: int = 3) -> Dict:
    """Neueste Printify Streetwear Designs → Telegram (nur eigener Shop, keine Fremd-Links)."""
    products = await _get_printify_products(limit=count)
    if not products:
        return {"ok": False, "error": "no Printify products", "posted": 0}

    posted = 0
    for p in products:
        title    = p.get("title", "New Design")[:60]
        handle   = p.get("handle", "")
        variants = p.get("variants", [{}])
        price    = variants[0].get("price", "29.99") if variants else "29.99"
        shop_url = f"{STORE_URL}/products/{handle}"

        msg = (
            f"🔥 <b>{title}</b>\n"
            f"💶 Nur €{price} — Premium Print-on-Demand\n\n"
            f"👕 <a href='{shop_url}'>Jetzt kaufen → AIITEC Store</a>"
        )
        ok = await _tg(msg)
        if ok:
            posted += 1
        await asyncio.sleep(3)

    return {"ok": posted > 0, "posted": posted, "total": len(products)}


# ── eBay affiliate link builder ───────────────────────────────────────────────

def _ebay_link(keyword: str) -> str:
    import urllib.parse
    kw = urllib.parse.quote(keyword)
    return f"https://www.ebay.de/sch/i.html?_nkw={kw}&_sop=12"


async def _ebay_search(keyword: str, count: int = 3) -> List[Dict]:
    """eBay Finding API für Smart Home Keywords."""
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


# ── Amazon affiliate link builder ─────────────────────────────────────────────

def _amazon_link(keyword: str) -> str:
    import urllib.parse
    kw = urllib.parse.quote(keyword)
    return f"https://www.amazon.de/s?k={kw}&tag={AMZN_TAG}"


# ── AliExpress link builder ───────────────────────────────────────────────────

def _ali_link(keyword: str) -> str:
    import urllib.parse
    kw = urllib.parse.quote(keyword)
    return f"https://www.aliexpress.com/wholesale?SearchText={kw}&sortType=total_tranQty_desc"


# ── eBay Smart Home deal blast ────────────────────────────────────────────────

async def run_ebay_smarthome_blast(count: int = 3) -> Dict:
    """eBay Smart Home Deals → Telegram."""
    kw    = random.choice(SMART_HOME_KW)
    items = await _ebay_search(kw, count=count)

    if not items:
        url = _ebay_link(kw)
        msg = (
            f"🏠 <b>eBay Smart Home Deal</b>\n"
            f"Trending: <b>{kw.title()}</b>\n\n"
            f"🔗 <a href='{url}'>Jetzt auf eBay suchen</a>"
        )
        ok = await _tg(msg)
        return {"ok": ok, "blasted": 1 if ok else 0, "source": "fallback"}

    blasted = 0
    for item in items[:2]:
        price_str = f"€{item['price']}" if item.get("price") else ""
        msg = (
            f"🛒 <b>eBay Smart Home</b>\n"
            f"{item['title']}\n"
            f"{price_str}\n\n"
            f"🔗 <a href='{item['url']}'>eBay Deal ansehen</a>"
        )
        ok = await _tg(msg)
        if ok:
            blasted += 1
        await asyncio.sleep(3)

    return {"ok": blasted > 0, "blasted": blasted, "keyword": kw}


# ── Amazon Smart Home affiliate blast ────────────────────────────────────────

async def run_amazon_smarthome_blast() -> Dict:
    """Amazon Smart Home Affiliate Post → Telegram."""
    kw  = random.choice(SMART_HOME_KW)
    url = _amazon_link(kw)

    MSGS = [
        f"🛍️ <b>Amazon Smart Home</b>\nTrending: <b>{kw.title()}</b>\n\n🔗 <a href='{url}'>Amazon Deals entdecken →</a>",
        f"📦 <b>Amazon Smart Home Deals</b>\n{kw.title()} — Prime-Lieferung!\n\n👉 <a href='{url}'>Jetzt auf Amazon</a>",
        f"⚡ <b>Amazon Smart Home 2026</b>\n{kw.title()} — Bestseller\n\n🔗 <a href='{url}'>Amazon Deal ansehen</a>",
    ]
    ok = await _tg(random.choice(MSGS))
    return {"ok": ok, "keyword": kw}


# ── AliExpress Smart Home announce ───────────────────────────────────────────

async def run_aliexpress_smarthome_announce() -> Dict:
    """AliExpress Smart Home Deals → Telegram."""
    kw  = random.choice(SMART_HOME_KW)
    url = _ali_link(kw)

    msg = (
        f"🌏 <b>AliExpress Smart Home</b>\n"
        f"Trending: <b>{kw.title()}</b>\n\n"
        f"🔗 <a href='{url}'>AliExpress Deals entdecken</a>"
    )
    ok = await _tg(msg)
    return {"ok": ok, "keyword": kw}


# ── Full marketplace cycle ─────────────────────────────────────────────────────

async def run_full_marketplace_cycle() -> Dict:
    """Scheduler entry: rotiert zwischen eigenem Shop (Streetwear) und Marktplatz-Deals (Smart Home)."""
    ACTIONS = [
        ("own_shop_streetwear", post_own_shop_streetwear),
        ("ebay_smarthome",      run_ebay_smarthome_blast),
        ("amazon_smarthome",    run_amazon_smarthome_blast),
        ("ali_smarthome",       run_aliexpress_smarthome_announce),
    ]
    name, fn = random.choice(ACTIONS)
    try:
        result = await fn()
        return {"ok": result.get("ok"), "action": name, "detail": result}
    except Exception as e:
        log.error("Marketplace cycle '%s' error: %s", name, e)
        return {"ok": False, "action": name, "error": str(e)}
