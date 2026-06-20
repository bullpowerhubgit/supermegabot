#!/usr/bin/env python3
"""
Product Bundle Engine — vollautomatische Bundles auf Shopify.
Täglich: scannt Produkte → erstellt 3er/5er Bundles → Collection → Discount-Code → BrutusCore-Blast.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("ProductBundleEngine")

SHOP        = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOK = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER = os.getenv("SHOPIFY_API_VERSION", "2024-10")
SHOP_URL    = os.getenv("SHOPIFY_SHOP_URL", "")

BUNDLE_DISCOUNT = 20  # Prozent

BUNDLE_THEMES = [
    ("KI Starter Pack", "ki artificial-intelligence ai"),
    ("Business Booster Bundle", "business ecommerce shopify"),
    ("Marketing Mega-Set", "marketing seo social-media"),
    ("Digital Creator Bundle", "digital content creator"),
    ("Produktivitäts-Bundle", "produktivitat workflow automation"),
    ("E-Commerce Pro Bundle", "ecommerce dropshipping product"),
    ("KI Tools Komplettpaket", "ki tool software automation"),
    ("Online Business Starter", "online business geld verdienen"),
]


async def _shopify_get(path: str) -> dict:
    if not SHOP or not SHOPIFY_TOK:
        return {}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOP}/admin/api/{SHOPIFY_VER}{path}",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOK},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return await r.json() if r.status < 400 else {}
    except Exception:
        return {}


async def _shopify_post(path: str, data: dict) -> dict:
    if not SHOP or not SHOPIFY_TOK:
        return {}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://{SHOP}/admin/api/{SHOPIFY_VER}{path}",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOK,
                         "Content-Type": "application/json"},
                json=data,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return await r.json() if r.status < 400 else {}
    except Exception:
        return {}


async def _ai(prompt: str, max_tokens: int = 200) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _get_shopify_products(limit: int = 50) -> list:
    data = await _shopify_get(f"/products.json?limit={limit}&status=active")
    return data.get("products", [])


async def _create_collection(title: str, body: str, product_ids: list) -> str:
    """Erstellt eine Custom-Collection auf Shopify."""
    result = await _shopify_post("/custom_collections.json", {
        "custom_collection": {
            "title": title,
            "body_html": body,
            "published": True,
        }
    })
    cid = result.get("custom_collection", {}).get("id")
    if not cid:
        return ""

    # Produkte zur Collection hinzufügen
    for pid in product_ids:
        await _shopify_post("/collects.json", {
            "collect": {"collection_id": cid, "product_id": pid}
        })
    return str(cid)


async def _create_discount_code(title: str, pct: int) -> str:
    """Erstellt einen prozentualen Discount-Code auf Shopify."""
    code = title.upper().replace(" ", "")[:8] + str(random.randint(10, 99))
    result = await _shopify_post("/price_rules.json", {
        "price_rule": {
            "title": title,
            "target_type": "line_item",
            "target_selection": "all",
            "allocation_method": "across",
            "value_type": "percentage",
            "value": f"-{pct}.0",
            "customer_selection": "all",
            "starts_at": datetime.now(timezone.utc).isoformat(),
        }
    })
    rule_id = result.get("price_rule", {}).get("id")
    if not rule_id:
        return code

    await _shopify_post(f"/price_rules/{rule_id}/discount_codes.json", {
        "discount_code": {"code": code}
    })
    return code


async def create_bundle(size: int = 3) -> dict:
    """Erstellt ein Bundle aus zufälligen Shopify-Produkten."""
    products = await _get_shopify_products(50)
    if len(products) < size:
        return {"ok": False, "error": f"Zu wenige Produkte: {len(products)} < {size}"}

    selected = random.sample(products, size)
    theme_name, _keywords = random.choice(BUNDLE_THEMES)
    bundle_title = f"{theme_name} ({size}er Bundle)"

    product_names = ", ".join(p.get("title", "")[:20] for p in selected)
    body = await _ai(
        f"Schreibe eine kurze deutsche Beschreibung (2 Sätze) für ein Bundle namens '{bundle_title}'. "
        f"Enthält: {product_names}. Betone den Spareffekt und den Mehrwert.",
        max_tokens=80,
    ) or f"Das {bundle_title} kombiniert {size} Top-Produkte zu einem unschlagbaren Preis."

    product_ids = [p["id"] for p in selected]
    cid = await _create_collection(bundle_title, body, product_ids)
    code = await _create_discount_code(bundle_title, BUNDLE_DISCOUNT)

    shop_base = SHOP_URL or f"https://{SHOP}"
    collection_url = f"{shop_base}/collections/{cid}" if cid else shop_base

    log.info("Bundle erstellt: %s (collection=%s, code=%s)", bundle_title, cid, code)
    return {
        "ok": True,
        "bundle_title": bundle_title,
        "products": len(selected),
        "collection_id": cid,
        "discount_code": code,
        "discount_pct": BUNDLE_DISCOUNT,
        "url": collection_url,
    }


async def blast_bundle(bundle: dict) -> dict:
    """Blasted ein Bundle auf alle Kanäle."""
    title = bundle.get("bundle_title", "Bundle")
    code  = bundle.get("discount_code", "")
    pct   = bundle.get("discount_pct", BUNDLE_DISCOUNT)
    url   = bundle.get("url", "")
    products = bundle.get("products", 0)

    content = await _ai(
        f"Kurzer überzeugender Werbepost (3 Sätze, deutsch) für das Bundle '{title}'. "
        f"{products} Produkte, {pct}% Rabatt mit Code {code}. Link: {url}",
        max_tokens=100,
    ) or (
        f"Spare jetzt {pct}% auf unser {title}!\n"
        f"{products} Top-Produkte zum Sonderpreis.\n"
        f"Code: {code} — Jetzt sichern: {url}"
    )

    try:
        from modules.brutus_core import fire
        await fire(
            title,
            content,
            link=url,
            channels=["telegram", "slack", "discord", "mailchimp", "klaviyo", "shopify_blog"],
        )
        return {"ok": True, "blasted": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def run_daily_bundle_cycle() -> dict:
    """Täglich: 2 Bundles (3er + 5er) erstellen und blasten."""
    results = []
    for size in [3, 5]:
        b = await create_bundle(size=size)
        if b.get("ok"):
            blast = await blast_bundle(b)
            b["blast_ok"] = blast.get("ok")
        results.append(b)
        await asyncio.sleep(2)

    ok_count = sum(1 for r in results if r.get("ok"))
    return {"ok": ok_count > 0, "bundles_created": ok_count, "results": results}


async def get_bundle_stats() -> dict:
    """Anzahl Collections auf Shopify als Proxy für Bundles."""
    data = await _shopify_get("/custom_collections.json?limit=250")
    cols = data.get("custom_collections", [])
    bundles = [c for c in cols if "Bundle" in c.get("title", "")]
    return {
        "ok": True,
        "total_collections": len(cols),
        "bundle_collections": len(bundles),
        "recent_bundles": [
            {"id": b["id"], "title": b["title"]} for b in bundles[-5:]
        ],
    }


async def run_bundle_cycle() -> dict:
    """Scheduler-Einstiegspunkt."""
    return await run_daily_bundle_cycle()
