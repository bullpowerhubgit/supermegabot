#!/usr/bin/env python3
"""
Alibaba/1688 Autonomy — Trending products via AliExpress Open Platform API.
Alibaba and AliExpress share the same product catalog via the same API credentials.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import time
from urllib.parse import urlencode

import aiohttp

log = logging.getLogger("AlibabaAutonomy")

APP_KEY    = os.getenv("ALIEXPRESS_APP_KEY", "536860")
APP_SECRET = os.getenv("ALIEXPRESS_APP_SECRET", "mmKF9pO8NZrEzdjpl6j0lXFoHhv213uN")
SHOPIFY    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER   = os.getenv("SHOPIFY_API_VERSION", "2024-10")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

ALIBABA_NICHES = [
    "smart home gadgets",
    "fitness equipment",
    "pet accessories",
    "kitchen tools",
    "phone accessories",
    "outdoor survival",
    "beauty tools",
    "office organizers",
    "baby products",
    "car accessories",
]


def _sign(params: dict, secret: str) -> str:
    sorted_params = sorted(params.items())
    sign_string = secret + "".join(f"{k}{v}" for k, v in sorted_params) + secret
    return hashlib.md5(sign_string.encode("utf-8")).hexdigest().upper()


async def _ai(prompt: str, max_tokens: int = 400) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def search_alibaba_products(keyword: str, count: int = 10) -> list:
    """Search trending dropship products via AliExpress API (same catalog as Alibaba)."""
    params = {
        "method": "aliexpress.affiliate.product.query",
        "app_key": APP_KEY,
        "timestamp": str(int(time.time() * 1000)),
        "format": "json",
        "v": "2.0",
        "sign_method": "md5",
        "fields": "product_id,product_title,product_main_image_url,target_sale_price,sale_price,evaluate_rate,volume",
        "keywords": keyword,
        "page_no": "1",
        "page_size": str(count),
        "sort": "SALES_DESC",
        "target_currency": "EUR",
        "target_language": "DE",
        "ship_to_country": "DE",
    }
    params["sign"] = _sign(params, APP_SECRET)

    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api-sg.aliexpress.com/sync",
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)

        resp = data.get("aliexpress_affiliate_product_query_response", {})
        resp_result = resp.get("resp_result", {})
        result = resp_result.get("result", {})
        products = result.get("products", {}).get("product", [])
        log.info("Alibaba search '%s': %d products", keyword, len(products))
        return products
    except Exception as e:
        log.warning("Alibaba search error: %s", e)
        return []


async def _enhance_with_ai(product: dict) -> dict:
    """AI-enhance product title and description for German market."""
    title = product.get("product_title", "")[:100]
    prompt = (
        f"Erstelle einen deutschen Shopify-Produkttitel (max 80 Zeichen) und eine "
        f"Beschreibung (150 Wörter, SEO-optimiert) für: '{title}'. "
        f"Format:\nTITEL: ...\nBESCHREIBUNG: ..."
    )
    ai_text = await _ai(prompt, 300)
    if "TITEL:" in ai_text and "BESCHREIBUNG:" in ai_text:
        parts = ai_text.split("BESCHREIBUNG:")
        de_title = parts[0].replace("TITEL:", "").strip()[:80]
        de_desc = parts[1].strip()
    else:
        de_title = title
        de_desc = f"Top-Produkt: {title}. Schnelle Lieferung nach Deutschland. Hochwertige Qualität."
    return {**product, "de_title": de_title, "de_desc": de_desc}


async def import_to_shopify(product: dict) -> dict:
    """Import one Alibaba product into Shopify."""
    if not SHOPIFY or not SHOPIFY_TOKEN:
        return {"ok": False, "error": "no shopify credentials"}

    enhanced = await _enhance_with_ai(product)
    title = enhanced.get("de_title") or enhanced.get("product_title", "Produkt")[:80]
    desc = enhanced.get("de_desc", "")
    price = enhanced.get("target_sale_price") or enhanced.get("sale_price", "9.99")
    try:
        price_val = float(str(price).replace(",", "."))
        sell_price = round(price_val * 2.5, 2)
    except Exception:
        sell_price = 19.99
    image_url = enhanced.get("product_main_image_url", "")

    body = {
        "product": {
            "title": title,
            "body_html": f"<p>{desc}</p>",
            "vendor": "Alibaba Import",
            "product_type": "Dropship",
            "tags": "alibaba,dropship,trending,auto-import",
            "status": "active",
            "variants": [{"price": str(sell_price), "inventory_management": None}],
        }
    }
    if image_url:
        body["product"]["images"] = [{"src": image_url}]

    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
    url = f"https://{SHOPIFY}/admin/api/{SHOPIFY_VER}/products.json"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=20)) as r:
                d = await r.json(content_type=None)
        pid = d.get("product", {}).get("id")
        return {"ok": bool(pid), "product_id": pid, "title": title, "price": sell_price}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _notify(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


async def run_alibaba_cycle(count_per_niche: int = 2) -> dict:
    """Full autonomous Alibaba cycle: scan niches → import top products → notify."""
    import random
    niches = random.sample(ALIBABA_NICHES, min(3, len(ALIBABA_NICHES)))
    imported = 0
    published = 0
    errors = []

    for niche in niches:
        products = await search_alibaba_products(niche, count=count_per_niche + 2)
        top = products[:count_per_niche]
        for p in top:
            result = await import_to_shopify(p)
            imported += 1
            if result.get("ok"):
                published += 1
                log.info("Alibaba → Shopify: %s @ €%.2f", result.get("title"), result.get("price", 0))
            else:
                errors.append(result.get("error", "unknown"))
            await asyncio.sleep(1)

    summary = f"🏭 <b>Alibaba Auto-Import</b>\n✅ {published}/{imported} Produkte importiert\n📦 Niches: {', '.join(niches)}"
    if errors:
        summary += f"\n⚠️ {len(errors)} Fehler"
    await _notify(summary)

    # BrutusClone blast — traffic für alle importierten Produkte
    if published > 0:
        try:
            from modules.brutus_core import fire
            shop_url = f"https://{SHOPIFY}" if SHOPIFY else "https://autopilot-store-suite-fmbka.myshopify.com"
            await fire(
                f"🏭 {published} neue Alibaba-Produkte im Shop!",
                f"Trending Dropship-Produkte aus {', '.join(niches)} — jetzt verfügbar. "
                f"Günstiger Direktimport, schnelle Lieferung nach DE/AT/CH.",
                link=shop_url,
                channels=["telegram", "slack", "shopify_blog"],
            )
        except Exception as be:
            log.debug("BrutusClone fire: %s", be)

        # Self-improvement log
        try:
            from modules.quantum_self_fixer import log_error
            # Log success as a positive signal (not an error)
            pass
        except Exception:
            pass

    log.info("Alibaba cycle done: %d/%d imported", published, imported)
    return {"imported": imported, "published": published, "niches": niches, "errors": errors}
