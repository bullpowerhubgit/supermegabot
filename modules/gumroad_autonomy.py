#!/usr/bin/env python3
"""
Gumroad Autonomy — Digitale Produkte erstellen, listen, auf allen Kanälen bewerben.
Mit Token: echte Gumroad API. Ohne: KI-generierte Produkt-Pages + Promotion.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random

import aiohttp

log = logging.getLogger("GumroadAutonomy")

GUMROAD_TOKEN = os.getenv("GUMROAD_ACCESS_TOKEN", "")
SHOP_URL      = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
GUMROAD_BASE  = "https://api.gumroad.com/v2"

DIGITAL_PRODUCTS = [
    {"name": "Shopify Automation Masterpack", "price": 2700, "desc": "50+ Automatisierungs-Templates für Shopify-Shops. Sofort einsetzbar.", "url": f"{SHOP_URL}/collections/digital"},
    {"name": "ChatGPT Prompt Pack — 200 Business Prompts", "price": 1700, "desc": "200 getestete ChatGPT-Prompts für Marketing, Sales, Content Creation.", "url": f"{SHOP_URL}/collections/digital"},
    {"name": "E-Commerce SEO Checkliste 2026", "price": 700, "desc": "87-Punkte SEO-Checkliste für Shopify und WooCommerce Shops.", "url": f"{SHOP_URL}/collections/digital"},
    {"name": "Affiliate Marketing Blueprint", "price": 1200, "desc": "Kompletter Guide von 0 auf €1000/Monat mit Affiliate Marketing.", "url": f"{SHOP_URL}/collections/digital"},
    {"name": "TikTok Content Kalender 2026", "price": 900, "desc": "365 TikTok-Ideen, Scripts und Hashtag-Strategien. Fertig zum Posten.", "url": f"{SHOP_URL}/collections/digital"},
    {"name": "Dropshipping Lieferanten-Liste DACH", "price": 1500, "desc": "200+ geprüfte Dropshipping-Lieferanten für den deutschsprachigen Markt.", "url": f"{SHOP_URL}/collections/digital"},
    {"name": "Email Funnel Template Pack", "price": 1900, "desc": "30 konvertierende Email-Sequenzen für Klaviyo und Mailchimp.", "url": f"{SHOP_URL}/collections/digital"},
]


async def _ai(prompt: str, max_tokens: int = 300) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def create_digital_product(name: str, desc: str, price: int, url: str = "") -> dict:
    """Erstellt ein Gumroad-Produkt (mit Token) oder loggt es (ohne)."""
    if not GUMROAD_TOKEN:
        log.info("Gumroad product ready (no token): %s — $%.2f", name, price / 100)
        return {"ok": True, "mode": "no_token", "name": name,
                "price_cents": price, "note": "Set GUMROAD_ACCESS_TOKEN in Railway"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{GUMROAD_BASE}/products",
                data={
                    "name": name, "description": desc,
                    "price": price, "url": url or SHOP_URL,
                    "published": True,
                },
                headers={"Authorization": f"Bearer {GUMROAD_TOKEN}"},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                data = await r.json()
        if data.get("success"):
            product = data.get("product", {})
            log.info("Gumroad product created: %s", product.get("id"))
            return {"ok": True, "mode": "api", "product_id": product.get("id"),
                    "url": product.get("short_url", ""), "name": name}
        return {"ok": False, "error": data.get("message", "unknown")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def list_products() -> dict:
    """Listet alle Gumroad-Produkte."""
    if not GUMROAD_TOKEN:
        return {"ok": True, "products": DIGITAL_PRODUCTS, "mode": "local_catalog",
                "count": len(DIGITAL_PRODUCTS)}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{GUMROAD_BASE}/products",
                headers={"Authorization": f"Bearer {GUMROAD_TOKEN}"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                data = await r.json()
        products = data.get("products", [])
        return {"ok": True, "products": products, "count": len(products), "mode": "api"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def blast_gumroad_links(count: int = 3) -> dict:
    """Bewirbt Gumroad/Digitale Produkte auf allen Kanälen."""
    products_data = await list_products()
    products = products_data.get("products", [])[:count]
    if not products:
        products = random.sample(DIGITAL_PRODUCTS, min(count, len(DIGITAL_PRODUCTS)))

    blasted = 0
    for product in products:
        try:
            name = product.get("name", "Digital Product")
            price_cents = product.get("price_cents", product.get("price", 1700))
            price_str = f"€{price_cents/100:.2f}" if price_cents else ""
            link = product.get("short_url", product.get("url", SHOP_URL))
            desc = product.get("description", product.get("desc", ""))[:100]

            prompt = f"""Kurzer Promotions-Post (Deutsch, 3 Sätze + Link):
Produkt: "{name}" {price_str}
Beschreibung: {desc}
Link: {link}
Emojis OK. Urgency erzeugen."""
            post = await _ai(prompt, 100)
            if not post:
                post = f"🎯 {name} {price_str}\n{desc}\n👉 {link}"

            from modules.brutus_core import fire
            await fire(name[:60], post, link=link,
                       channels=["telegram", "slack", "discord", "linkedin", "mailchimp"])
            blasted += 1
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("Gumroad blast error: %s", e)

    return {"ok": True, "blasted": blasted, "total": len(products)}


async def auto_create_all_products() -> dict:
    """Erstellt alle definierten digitalen Produkte auf Gumroad."""
    created = 0
    for product in DIGITAL_PRODUCTS:
        result = await create_digital_product(
            name=product["name"],
            desc=product["desc"],
            price=product["price"],
            url=product.get("url", SHOP_URL),
        )
        if result.get("ok"):
            created += 1
        await asyncio.sleep(1)
    return {"ok": True, "created": created, "total": len(DIGITAL_PRODUCTS)}


async def run_gumroad_cycle() -> dict:
    """Scheduler-Einstiegspunkt."""
    blast = await blast_gumroad_links(count=2)
    return {"ok": True, "blasted": blast.get("blasted", 0)}
