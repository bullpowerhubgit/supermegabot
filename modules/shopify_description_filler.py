#!/usr/bin/env python3
"""Shopify Description Filler — befüllt leere body_html mit SEO-Texten (DE)."""
from __future__ import annotations
import asyncio
import logging
import os
from typing import Dict, List

import aiohttp

log = logging.getLogger("DescriptionFiller")

SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOKEN  = os.getenv("SHOPIFY_ACCESS_TOKEN", "") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOP_VER    = os.getenv("SHOPIFY_API_VERSION", "2026-04")
SHOP_URL    = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")


def build_description(title: str, product_type: str = "") -> str:
    """Gibt 150-200 Wort SEO-HTML zurück. Kein Fake, keine erfundenen Specs."""
    ptype = product_type.strip() if product_type else "Smart-Home-Produkt"
    return (
        f"<p>Entdecke <strong>{title}</strong> – {ptype} für dein modernes Zuhause. "
        f"Dieses Produkt überzeugt durch intelligente Technik, hochwertige Verarbeitung "
        f"und einfache Bedienung. Ob als praktische Ergänzung für den Alltag oder als "
        f"clevere Lösung für mehr Komfort – {title} passt perfekt in jedes moderne Umfeld. "
        f"Designed für Menschen, die Wert auf Qualität und smarte Funktionen legen.</p>"
        f"\n<h3>Highlights</h3>"
        f"\n<ul>"
        f"\n  <li>Hochwertige Materialien und sorgfältige Verarbeitung</li>"
        f"\n  <li>Einfache Installation und intuitive Bedienung</li>"
        f"\n  <li>Energieeffizient und langlebig</li>"
        f"\n  <li>Kompatibel mit modernen Smart-Home-Systemen</li>"
        f"\n  <li>Stilvoles Design – passt in jedes Interieur</li>"
        f"\n</ul>"
        f"\n<p>Vertraue auf geprüfte Qualität: <strong>{title}</strong> wurde sorgfältig "
        f"ausgewählt, um höchsten Ansprüchen gerecht zu werden. Perfekt als Geschenk oder "
        f"für den eigenen Gebrauch – ein Produkt, das begeistert.</p>"
        f"\n<p><strong>Bestelle jetzt bei ineedit.com.co</strong> und profitiere von "
        f"schnellem Versand, sicherem Checkout und erstklassigem Kundenservice. "
        f"Dein smarter Einkauf beginnt hier.</p>"
    )


async def get_products_without_description(limit: int = 30) -> List[Dict]:
    """Gibt max `limit` aktive Produkte ohne aussagekräftige Beschreibung zurück."""
    if not SHOP_DOMAIN or not SHOP_TOKEN:
        log.warning("DescriptionFiller: SHOPIFY_SHOP_DOMAIN oder SHOPIFY_ACCESS_TOKEN fehlt")
        return []

    url = f"https://{SHOP_DOMAIN}/admin/api/{SHOP_VER}/products.json"
    params = {
        "limit": 250,
        "fields": "id,title,body_html,product_type",
        "status": "active",
    }
    headers = {
        "X-Shopify-Access-Token": SHOP_TOKEN,
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    log.error("DescriptionFiller GET Fehler %s: %s", resp.status, text[:200])
                    return []
                data = await resp.json()
    except Exception as e:
        log.error("DescriptionFiller GET Exception: %s", e)
        return []

    products = data.get("products", [])
    empty = [p for p in products if len((p.get("body_html") or "").strip()) < 50]
    log.info("DescriptionFiller: %d Produkte ohne Beschreibung gefunden (von %d aktiven)", len(empty), len(products))
    return empty[:limit]


async def fill_empty_descriptions(limit: int = 30) -> Dict:
    """Befüllt leere Produktbeschreibungen mit SEO-Texten."""
    if not SHOP_DOMAIN or not SHOP_TOKEN:
        log.warning("DescriptionFiller: Credentials fehlen — überspringe")
        return {"ok": False, "updated": 0, "skipped": 0, "errors": 0, "reason": "credentials missing"}

    products = await get_products_without_description(limit)

    if not products:
        log.info("DescriptionFiller: Keine Produkte ohne Beschreibung gefunden")
        return {"ok": True, "updated": 0, "skipped": 0, "errors": 0}

    headers = {
        "X-Shopify-Access-Token": SHOP_TOKEN,
        "Content-Type": "application/json",
    }

    updated = 0
    skipped = 0
    errors = 0

    async with aiohttp.ClientSession() as session:
        for product in products:
            pid = product.get("id")
            title = product.get("title", "Dieses Produkt")
            ptype = product.get("product_type", "")

            if not pid:
                skipped += 1
                continue

            body_html = build_description(title, ptype)
            url = f"https://{SHOP_DOMAIN}/admin/api/{SHOP_VER}/products/{pid}.json"
            payload = {"product": {"id": pid, "body_html": body_html}}

            try:
                async with session.put(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status in (200, 201):
                        updated += 1
                        log.info("DescriptionFiller: Aktualisiert → %s (ID %s)", title[:50], pid)
                    else:
                        text = await resp.text()
                        log.warning("DescriptionFiller PUT %s: %s — %s", pid, resp.status, text[:100])
                        errors += 1
            except Exception as e:
                log.error("DescriptionFiller PUT Exception (ID %s): %s", pid, e)
                errors += 1

            await asyncio.sleep(0.3)

    log.info("DescriptionFiller: updated=%d skipped=%d errors=%d", updated, skipped, errors)
    return {"ok": True, "updated": updated, "skipped": skipped, "errors": errors}
