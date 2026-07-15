#!/usr/bin/env python3
"""
Printful Autonomy — Catalog sync, product creation, BrutusCore blast.
API v2: https://api.printful.com/v2
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random

import aiohttp

log = logging.getLogger("PrintfulAutonomy")

TOKEN = os.getenv("PRINTFUL_API_KEY", "gd3ZDHx6QkyaoDB7Vr95Wsey3CKZv1tGtOIBfbkh")
BASE_V2 = "https://api.printful.com/v2"
BASE_V1 = "https://api.printful.com"
AUTH = lambda: {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                "X-PF-API-Key": TOKEN}

SHOP = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER = os.getenv("SHOPIFY_API_VERSION", "2026-04")
SHOPIFY_HEADERS = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}


async def _ai(prompt: str, max_tokens: int = 400) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _get_v1(path: str) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{BASE_V1}{path}", headers=AUTH(),
                         timeout=aiohttp.ClientTimeout(total=20)) as r:
            return await r.json() if r.status < 400 else {}


async def _get_v2(path: str) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{BASE_V2}{path}", headers=AUTH(),
                         timeout=aiohttp.ClientTimeout(total=20)) as r:
            return await r.json() if r.status < 400 else {}


async def get_products() -> list:
    """GET Printful catalog products (v1 /products is more reliable than v2)."""
    if not TOKEN:
        return []
    try:
        data = await _get_v1("/products")
        items = data.get("result", [])
        log.info("Printful catalog: %d products", len(items))
        return items
    except Exception as e:
        log.warning("Printful get_products error: %s", e)
        return []


async def create_product(title: str, description: str) -> dict:
    """Create a Printful sync product (requires store connected)."""
    if not TOKEN:
        return {"ok": False, "error": "no PRINTFUL_API_KEY"}
    try:
        # Get first available product from catalog for a t-shirt
        catalog = await get_products()
        tshirt = next((p for p in catalog if "t-shirt" in p.get("model", "").lower()
                       or "T-Shirt" in p.get("model", "")), None)
        if not tshirt:
            return {"ok": False, "error": "no t-shirt in Printful catalog"}

        # v1 sync product creation
        payload = {
            "sync_product": {
                "name": title[:100],
                "thumbnail": "",
            },
            "sync_variants": [
                {
                    "retail_price": "29.99",
                    "variant_id": tshirt.get("id", 4011),
                    "files": [
                        {"type": "front", "url": "https://picsum.photos/800/800?grayscale"}
                    ],
                }
            ],
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{BASE_V1}/store/products", headers=AUTH(), json=payload,
                              timeout=aiohttp.ClientTimeout(total=20)) as r:
                result = await r.json()
        pid = result.get("result", {}).get("id")
        if pid:
            log.info("Printful product created: %s (id=%s)", title[:60], pid)
            return {"ok": True, "product_id": pid, "title": title}
        return {"ok": False, "error": result.get("error", {}).get("message", "unknown")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def sync_catalog() -> dict:
    """Pull Printful catalog, highlight top items."""
    products = await get_products()
    if not products:
        return {"ok": False, "error": "no Printful catalog items", "count": 0}

    top = random.sample(products, min(5, len(products)))
    titles = [p.get("model", "Product") for p in top]
    log.info("Printful catalog sync: top items: %s", titles[:3])
    return {"ok": True, "count": len(products), "top_items": titles}


async def auto_blast_printful_deals() -> dict:
    """Get Printful catalog items → AI content → BrutusCore blast."""
    products = await get_products()
    if not products:
        return {"ok": False, "error": "no Printful products", "blasted": 0}

    blasted = 0
    for p in random.sample(products, min(3, len(products))):
        try:
            model = p.get("model", "Custom Product")
            brand = p.get("brand", "")
            prompt = f"""Kurzer deutscher Marketing-Text (2-3 Sätze) für Print-on-Demand Produkt:
Produkt: {brand} {model}
Qualitäts-POD aus unserem Shop. Personalisierbar. Schnelle Lieferung DE/AT/CH."""
            content = await _ai(prompt, max_tokens=150)
            if not content:
                content = f"Premium {brand} {model} — individuell bedruckt, schnelle Lieferung!"

            from modules.brutus_core import fire
            shop_url = f"https://{SHOP}" if SHOP else os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/669750")
            await fire(
                f"POD Highlight: {brand} {model}",
                content,
                link=shop_url,
                channels=["telegram", "slack", "linkedin"],
            )
            blasted += 1
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("Printful blast error: %s", e)

    return {"ok": True, "blasted": blasted}


async def run_printful_cycle() -> dict:
    """Scheduler entry point."""
    sync = await sync_catalog()
    blast = await auto_blast_printful_deals()
    return {"ok": True, "sync": sync, "blast": blast}
