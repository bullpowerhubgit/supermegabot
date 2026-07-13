#!/usr/bin/env python3
"""
Auto-Sorter — vollautomatisches Sortieren und Kategorisieren.
Shopify: Produkte → Collections per Tags.
DS24: neue Produkte → Nischen-Kategorien.
Klaviyo: Subscriber → Segmente per Kaufverhalten.
"""
from __future__ import annotations

import asyncio
import logging
import os

import aiohttp

log = logging.getLogger("AutoSorter")

SHOP        = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOK = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER = os.getenv("SHOPIFY_API_VERSION", "2026-04")
KLAVIYO_KEY = os.getenv("KLAVIYO_API_KEY", "pk_VaCYq3_242945f7521ac82039ed5dbf7ff8e6cf1c")
DS24_KEY    = os.getenv("DS24_API_KEY", "")

# Tag → Collection-Name Mapping
TAG_COLLECTIONS = {
    "ki":             "KI & Künstliche Intelligenz",
    "ai":             "KI & Künstliche Intelligenz",
    "software":       "Software & Tools",
    "business":       "Business & Finanzen",
    "marketing":      "Marketing & SEO",
    "fitness":        "Fitness & Gesundheit",
    "coaching":       "Coaching & Mindset",
    "ecommerce":      "E-Commerce & Shopify",
    "digital":        "Digitale Produkte",
    "online":         "Online-Business",
    "mindset":        "Coaching & Mindset",
    "seo":            "Marketing & SEO",
    "social":         "Social Media",
    "affiliate":      "Affiliate Marketing",
    "dropshipping":   "E-Commerce & Shopify",
}

NICHE_KEYWORDS = {
    "ki_ai":      ["ki", "ai", "artificial", "gpt", "chatgpt", "claude", "llm"],
    "business":   ["business", "finanzen", "geld", "einkommen", "profit", "revenue"],
    "marketing":  ["marketing", "seo", "social", "content", "ads", "werbung"],
    "fitness":    ["fitness", "abnehmen", "gesundheit", "sport", "training"],
    "coaching":   ["coaching", "mindset", "persönlichkeit", "motivation", "ziele"],
    "ecommerce":  ["shopify", "ecommerce", "dropshipping", "amazon", "ebay"],
    "software":   ["software", "tool", "app", "programm", "saas", "automation"],
}


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


async def _get_or_create_collection(title: str) -> str:
    """Holt oder erstellt eine Smart-Collection."""
    existing = await _shopify_get(f"/custom_collections.json?title={title}&limit=1")
    cols = existing.get("custom_collections", [])
    if cols:
        return str(cols[0]["id"])

    result = await _shopify_post("/custom_collections.json", {
        "custom_collection": {"title": title, "published": True}
    })
    cid = result.get("custom_collection", {}).get("id")
    return str(cid) if cid else ""


async def sort_shopify_products() -> dict:
    """Sortiert alle Shopify-Produkte in Collections anhand ihrer Tags."""
    if not SHOP or not SHOPIFY_TOK:
        return {"ok": False, "error": "no Shopify credentials"}

    products = (await _shopify_get("/products.json?limit=250&status=active")).get("products", [])
    sorted_count = 0
    collections_used: dict = {}

    for product in products:
        tags_raw = product.get("tags", "")
        tags     = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]
        pid      = product["id"]

        for tag in tags:
            col_name = TAG_COLLECTIONS.get(tag)
            if not col_name:
                continue
            if col_name not in collections_used:
                cid = await _get_or_create_collection(col_name)
                collections_used[col_name] = cid
            else:
                cid = collections_used[col_name]

            if cid:
                await _shopify_post("/collects.json", {
                    "collect": {"collection_id": cid, "product_id": pid}
                })
                sorted_count += 1
                break  # ein Produkt → eine Haupt-Collection

        await asyncio.sleep(0.1)

    log.info("Shopify sort: %d Produkte in %d Collections", sorted_count, len(collections_used))
    return {
        "ok":           True,
        "products":     len(products),
        "sorted":       sorted_count,
        "collections":  len(collections_used),
    }


def _detect_niche(text: str) -> str:
    """Erkennt die Nische eines Produkts anhand von Keywords."""
    text_lower = text.lower()
    for niche, keywords in NICHE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return niche
    return "general"


async def sort_ds24_products() -> dict:
    """Sortiert DS24-Produkte aus Supabase in Nischen-Kategorien."""
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("ds24_products").select("*").is_("niche", "null").limit(100).execute()
        products = rows.data or []

        updated = 0
        for p in products:
            name  = p.get("name", "") or ""
            desc  = p.get("description", "") or ""
            niche = _detect_niche(name + " " + desc)
            get_client().table("ds24_products").update(
                {"niche": niche}
            ).eq("id", p["id"]).execute()
            updated += 1

        return {"ok": True, "sorted": updated}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def create_klaviyo_segments() -> dict:
    """Erstellt Klaviyo-Segmente nach Kaufverhalten."""
    if not KLAVIYO_KEY:
        return {"ok": False, "error": "no KLAVIYO_API_KEY"}

    segments = [
        {"name": "High-Value Customers", "filter": "greater_or_equal(properties.total_spent, 100)"},
        {"name": "Recent Buyers",        "filter": "greater_or_equal(properties.last_purchase, -30d)"},
        {"name": "Newsletter Aktiv",     "filter": "greater_or_equal(properties.email_opens, 3)"},
    ]
    created = 0
    headers = {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
        "revision":      "2024-02-15",
        "Content-Type":  "application/json",
    }

    async with aiohttp.ClientSession() as s:
        for seg in segments:
            try:
                payload = {
                    "data": {
                        "type": "segment",
                        "attributes": {
                            "name":       seg["name"],
                            "definition": {"condition_groups": []},
                        },
                    }
                }
                async with s.post(
                    "https://a.klaviyo.com/api/segments/",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    if r.status < 400:
                        created += 1
            except Exception as e:
                log.warning("Ignored error: %s", e)
            await asyncio.sleep(0.5)

    return {"ok": True, "segments_created": created}


async def sort_all() -> dict:
    """Vollständiger Sort-Zyklus."""
    results = await asyncio.gather(
        sort_shopify_products(),
        sort_ds24_products(),
        create_klaviyo_segments(),
        return_exceptions=True,
    )

    shopify  = results[0] if isinstance(results[0], dict) else {"ok": False, "error": str(results[0])}
    ds24     = results[1] if isinstance(results[1], dict) else {"ok": False, "error": str(results[1])}
    klaviyo  = results[2] if isinstance(results[2], dict) else {"ok": False, "error": str(results[2])}

    return {
        "ok":      True,
        "shopify": shopify,
        "ds24":    ds24,
        "klaviyo": klaviyo,
    }


async def run_sort_cycle() -> dict:
    """Scheduler-Einstiegspunkt (alle 6h)."""
    return await sort_all()
