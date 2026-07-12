#!/usr/bin/env python3
"""
Printify Autonomy — POD product creation, Shopify publishing, BrutusCore blast.
API: https://developers.printify.com/
"""
from __future__ import annotations

import asyncio
import logging
import os
import random

import aiohttp

log = logging.getLogger("PrintifyAutonomy")

TOKEN = os.getenv("PRINTIFY_API_TOKEN", "")
SHOP_ID = os.getenv("PRINTIFY_SHOP_ID", "27975583")
BASE = "https://api.printify.com/v1"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
AUTH = lambda: {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": _UA}

SHOP = os.getenv("SHOPIFY_SHOP_DOMAIN", "")

# Blueprint 6 = Unisex Staple T-Shirt (Bella+Canvas 3001), widely available
DEFAULT_BLUEPRINT = 6
DEFAULT_PROVIDER = 99  # Monster Digital — fallback to first available


async def _ai(prompt: str, max_tokens: int = 400) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _get(path: str) -> dict:
    if not TOKEN:
        return {}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.get(f"{BASE}{path}", headers=AUTH(),
                         timeout=aiohttp.ClientTimeout(total=20)) as r:
            return await r.json() if r.status < 400 else {"error": await r.text()}


async def _post(path: str, data: dict) -> dict:
    if not TOKEN:
        return {"error": "no PRINTIFY_API_TOKEN"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.post(f"{BASE}{path}", headers=AUTH(), json=data,
                          timeout=aiohttp.ClientTimeout(total=30)) as r:
            return await r.json() if r.status < 400 else {"error": await r.text()}


async def get_catalog_blueprints() -> list:
    """GET /v1/catalog/blueprints.json"""
    try:
        data = await _get("/catalog/blueprints.json")
        return data if isinstance(data, list) else data.get("data", [])
    except Exception as e:
        log.warning("Printify blueprints error: %s", e)
        return []


async def get_print_providers(blueprint_id: int) -> list:
    """GET /v1/catalog/blueprints/{id}/print_providers.json"""
    try:
        data = await _get(f"/catalog/blueprints/{blueprint_id}/print_providers.json")
        return data if isinstance(data, list) else []
    except Exception as e:
        log.warning("Printify providers error: %s", e)
        return []


async def _get_first_provider(blueprint_id: int) -> int:
    """Return first available print provider ID."""
    providers = await get_print_providers(blueprint_id)
    if providers:
        return providers[0].get("id", DEFAULT_PROVIDER)
    return DEFAULT_PROVIDER


async def _get_variants(blueprint_id: int, provider_id: int) -> list:
    """Get available variants for a blueprint+provider combo."""
    try:
        data = await _get(f"/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/variants.json")
        variants = data if isinstance(data, list) else data.get("variants", [])
        # Return first 4 variants (S, M, L, XL typically)
        enabled = []
        for v in variants[:4]:
            enabled.append({
                "id": v["id"],
                "price": 2999,  # €29.99 in cents
                "is_enabled": True,
            })
        return enabled
    except Exception as e:
        log.warning("Printify variants error: %s", e)
        return []


async def _upload_image_url(url: str, filename: str = "design.jpg") -> str:
    """Upload image by URL to Printify media library, returns image ID."""
    try:
        result = await _post("/uploads/images.json", {
            "file_name": filename,
            "url": url,
        })
        img_id = result.get("id", "")
        if img_id:
            log.debug("Printify image uploaded: %s", img_id)
        return img_id
    except Exception as e:
        log.debug("Printify image upload error: %s", e)
        return ""


async def create_pod_product(title: str, description: str,
                              blueprint_id: int = DEFAULT_BLUEPRINT,
                              provider_id: int = DEFAULT_PROVIDER) -> dict:
    """Create a POD product in Printify shop."""
    if not TOKEN:
        return {"ok": False, "error": "no PRINTIFY_API_TOKEN"}
    if not SHOP_ID:
        return {"ok": False, "error": "no PRINTIFY_SHOP_ID"}

    # Get real provider
    provider_id = await _get_first_provider(blueprint_id)
    variants = await _get_variants(blueprint_id, provider_id)
    if not variants:
        variants = [{"id": 18110, "price": 2999, "is_enabled": True}]

    # Upload design image (LoremFlickr — kein Key nötig)
    safe_title = title.replace(" ", ",")[:40]
    img_url = f"https://loremflickr.com/800/800/{safe_title}"
    image_id = await _upload_image_url(img_url, f"{title[:30].replace(' ','_')}.jpg")

    print_areas_images = []
    if image_id:
        print_areas_images = [{"id": image_id, "x": 0.5, "y": 0.5, "scale": 1, "angle": 0}]
    else:
        # Printify public test image ID (always valid)
        print_areas_images = [{"id": "5e16b7b78b3abd4e490a45c6", "x": 0.5, "y": 0.5, "scale": 1, "angle": 0}]

    payload = {
        "title": title[:100],
        "description": description[:2000],
        "blueprint_id": blueprint_id,
        "print_provider_id": provider_id,
        "variants": variants,
        "print_areas": [
            {
                "variant_ids": [v["id"] for v in variants],
                "placeholders": [
                    {"position": "front", "images": print_areas_images}
                ],
            }
        ],
    }

    try:
        result = await _post(f"/shops/{SHOP_ID}/products.json", payload)
        pid = result.get("id")
        if pid:
            log.info("Printify product created: %s (id=%s)", title[:60], pid)
            return {"ok": True, "product_id": pid, "title": title}
        err = result.get("error", str(result)[:200])
        log.warning("Printify create failed: %s", err)
        return {"ok": False, "error": err}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def publish_to_shopify(printify_product_id: str) -> dict:
    """Publish Printify product to Shopify."""
    if not TOKEN or not SHOP_ID:
        return {"ok": False, "error": "no credentials"}
    try:
        payload = {
            "title": True,
            "description": True,
            "images": True,
            "variants": True,
            "tags": True,
            "keyFeatures": True,
            "shipping_template": True,
        }
        result = await _post(f"/shops/{SHOP_ID}/products/{printify_product_id}/publish.json", payload)
        success = result.get("status") == "succeeded" or not result.get("error")
        log.info("Printify publish %s: %s", printify_product_id, "OK" if success else result.get("error"))
        return {"ok": success, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def auto_create_trending_pod(count: int = 3) -> dict:
    """AI generates POD design concepts → Printify → Shopify → BrutusCore."""
    if not TOKEN:
        return {"ok": False, "error": "no PRINTIFY_API_TOKEN", "created": 0}

    prompt = f"""Erstelle {count} kreative T-Shirt Design-Konzepte für einen deutschen Online-Shop.
Jedes Konzept: catchy Slogan auf Deutsch oder Englisch, für Zielgruppe 25-45 Jahre.
Themen: Motivation, Humor, Gadgets, Outdoor, Erfolg.

Antworte mit JSON-Array:
[
  {{"title": "Produkt-Titel (max 60 Zeichen)", "description": "Kurze Produktbeschreibung 2 Sätze", "slogan": "Der eigentliche Aufdruck-Text"}},
  ...
]"""
    raw = await _ai(prompt, max_tokens=400)
    concepts = []
    try:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start != -1:
            import json
            concepts = json.loads(raw[start:end])
    except Exception as _e:
        log.debug("suppressed: %s", _e)

    if not concepts:
        concepts = [
            {"title": "Hustle Hard T-Shirt", "description": "Motivations-Shirt für Unternehmer.", "slogan": "HUSTLE HARDER"},
            {"title": "Smart Work T-Shirt", "description": "Für digitale Nomaden.", "slogan": "WORK SMART"},
            {"title": "Rise & Grind T-Shirt", "description": "Für ambitionierte Menschen.", "slogan": "RISE & GRIND"},
        ]

    created = 0
    for concept in concepts[:count]:
        desc = f"<p>{concept.get('description', '')}</p><p><strong>Aufdruck: {concept.get('slogan', '')}</strong></p>"
        result = await create_pod_product(
            title=concept.get("title", "Custom T-Shirt"),
            description=desc,
        )
        if result.get("ok"):
            pid = result["product_id"]
            await publish_to_shopify(str(pid))
            created += 1
            try:
                from modules.brutus_core import fire
                shop_url = f"https://{SHOP}" if SHOP else os.getenv("SHOPIFY_SHOP_URL", "https://autopilot-store-suite-fmbka.myshopify.com")
                await fire(
                    f"Neues POD Produkt: {concept.get('title', 'T-Shirt')}",
                    f"{concept.get('description', '')} Jetzt im Shop erhältlich!",
                    link=shop_url,
                    channels=["telegram", "slack", "shopify_blog"],
                )
            except Exception as be:
                log.debug("Brutus fire: %s", be)
        await asyncio.sleep(3)

    result = {"ok": True, "created": created, "total": len(concepts)}
    try:
        from modules.brutus_clone import BrutusClone
        bc = BrutusClone("printify_autonomy")
        asyncio.create_task(bc.fire(
            "Printify Produkte erstellt",
            f"{created} neue POD-Produkte erstellt und zu Shopify publiziert",
            f"https://autopilot-store-suite-fmbka.myshopify.com"
        ))
    except Exception as _e:
        log.debug("suppressed: %s", _e)
    return result


async def run_printify_cycle() -> dict:
    """Scheduler entry point."""
    return await auto_create_trending_pod(count=2)
