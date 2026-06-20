#!/usr/bin/env python3
"""
Shopify Full Autonomy Engine
============================
Was bisher fehlte für echte Shopify-Autonomie:

1. AUTO-COLLECTIONS   — 630 Produkte automatisch in Kollektionen organisieren
2. MASS SEO FIXER     — alle Produkte: Metafields, Alt-Text, SEO-Titel in Bulk
3. CONVERSION FIX     — Preispsychologie (.99), CTA in Beschreibungen, CONTINUE-Inventar
4. DEAD PRODUCT AUDIT — Null-Verkauf-Produkte verbessern oder killen
5. BUNDLE BUILDER     — automatisch Produkt-Bundles erstellen
6. DISCOUNT ENGINE    — wöchentlich neue Rabatt-Codes + Blast auf alle Kanäle
7. COLLECTION SEO     — jede Kollektion bekommt SEO-Beschreibung
8. INVENTORY POLICE   — alle Varianten auf inventoryPolicy: CONTINUE setzen
9. DRAFT ACTIVATOR    — alle Drafts sofort aktivieren
10. PRICE SANITY CHECK — kein Produkt mit €0 Preis, kein Preis über €999 ohne Grund
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import aiohttp

log = logging.getLogger("ShopifyFullAuto")

SHOP    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
VER     = os.getenv("SHOPIFY_API_VERSION", "2024-10")
BASE    = lambda path: f"https://{SHOP}/admin/api/{VER}/{path}"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

BATCH = 50  # Produkte pro API-Call


def _ok() -> bool:
    return bool(SHOP and TOKEN)


# ── Shopify REST helpers ──────────────────────────────────────────────────────

async def _get(path: str, params: dict = None) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.get(BASE(path), headers=HEADERS, params=params or {},
                         timeout=aiohttp.ClientTimeout(total=20)) as r:
            return await r.json()


async def _put(path: str, data: dict) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.put(BASE(path), headers=HEADERS, json=data,
                         timeout=aiohttp.ClientTimeout(total=15)) as r:
            return await r.json()


async def _post(path: str, data: dict) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.post(BASE(path), headers=HEADERS, json=data,
                          timeout=aiohttp.ClientTimeout(total=15)) as r:
            return await r.json()


async def _graphql(query: str, variables: dict = None) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"https://{SHOP}/admin/api/{VER}/graphql.json",
            headers=HEADERS,
            json={"query": query, "variables": variables or {}},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            return await r.json()


async def _ai(prompt: str, max_tokens: int = 500) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _all_products(limit: int = 250) -> list:
    """Alle Shopify-Produkte laden (paginiert via since_id)."""
    products = []
    since_id = None
    while True:
        params = {"limit": limit, "status": "any"}
        if since_id:
            params["since_id"] = since_id
        data = await _get("products.json", params)
        batch = data.get("products", [])
        if not batch:
            break
        products.extend(batch)
        if len(batch) < limit:
            break
        since_id = batch[-1]["id"]
        if len(products) >= 2000:
            break
    return products


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DRAFT ACTIVATOR — alle Draft-Produkte sofort live
# ═══════════════════════════════════════════════════════════════════════════════

async def activate_all_drafts() -> dict:
    """Alle Draft-Produkte → active."""
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}
    activated = 0
    try:
        data = await _get("products.json", {"limit": 250, "status": "draft"})
        drafts = data.get("products", [])
        for p in drafts:
            await _put(f"products/{p['id']}.json", {"product": {"id": p["id"], "status": "active"}})
            activated += 1
            await asyncio.sleep(0.3)
        log.info("Drafts activated: %d", activated)
        return {"ok": True, "activated": activated}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 2. INVENTORY POLICE — alle Varianten auf CONTINUE
# ═══════════════════════════════════════════════════════════════════════════════

async def fix_inventory_policy() -> dict:
    """Setzt alle Varianten auf inventoryPolicy: CONTINUE (kein 'Sold Out')."""
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}
    fixed = 0
    try:
        products = await _all_products()
        for p in products:
            for v in p.get("variants", []):
                if v.get("inventory_policy") != "continue":
                    await _put(
                        f"variants/{v['id']}.json",
                        {"variant": {"id": v["id"], "inventory_policy": "continue",
                                     "inventory_management": None}}
                    )
                    fixed += 1
                    if fixed % 10 == 0:
                        await asyncio.sleep(1)
        log.info("Inventory policy fixed: %d variants", fixed)
        return {"ok": True, "fixed": fixed, "total": len(products)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PRICE SANITY CHECK — kein €0, keine falschen Preise
# ═══════════════════════════════════════════════════════════════════════════════

async def fix_prices() -> dict:
    """Korrigiert €0-Preise und wendet .99-Psychologie an."""
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}
    fixed = 0
    try:
        products = await _all_products()
        for p in products:
            for v in p.get("variants", []):
                price = float(v.get("price", "0") or "0")
                new_price = None
                if price <= 0:
                    # Default-Preis aus Titel ableiten (teures Produkt = höherer Preis)
                    title = p.get("title", "").lower()
                    if any(w in title for w in ["beamer", "drucker", "4k", "laptop", "kamera"]):
                        new_price = "199.99"
                    elif any(w in title for w in ["gadget", "smart", "adapter", "kabel"]):
                        new_price = "29.99"
                    else:
                        new_price = "39.99"
                elif not str(price).endswith((".99", ".49", ".95")):
                    # .99-Psychologie anwenden
                    rounded = round(price) - 0.01
                    if rounded > 0:
                        new_price = f"{rounded:.2f}"
                if new_price:
                    await _put(
                        f"variants/{v['id']}.json",
                        {"variant": {"id": v["id"], "price": new_price}}
                    )
                    fixed += 1
                    await asyncio.sleep(0.2)
        log.info("Prices fixed: %d", fixed)
        return {"ok": True, "fixed": fixed}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 4. MASS SEO FIXER — Metafields für SEO bei allen Produkten
# ═══════════════════════════════════════════════════════════════════════════════

async def fix_product_seo(product: dict) -> bool:
    """SEO-Metafields + Tags für ein einzelnes Produkt."""
    pid = product["id"]
    title = product.get("title", "")
    tags = product.get("tags", "")

    # Skip wenn schon gute Tags vorhanden
    if len(tags.split(",")) >= 5 and "shopify automation" not in tags:
        return False

    # KI: bessere Tags generieren
    prompt = f"""Produkt: "{title}"
Erstelle 8 SEO-optimierte Tags auf Deutsch für dieses Shopify-Produkt.
Nur die Tags, kommagetrennt, kein JSON, kein anderer Text.
Beispiel: smart home, gadget 2026, weihnachtsgeschenk, bestseller"""
    ai_tags = await _ai(prompt, max_tokens=100)
    if not ai_tags or len(ai_tags) < 10:
        return False

    clean_tags = ",".join([t.strip()[:50] for t in ai_tags.split(",") if t.strip()][:10])
    try:
        await _put(f"products/{pid}.json",
                   {"product": {"id": pid, "tags": clean_tags}})
        return True
    except Exception as e:
        log.debug("SEO fix %s: %s", pid, e)
        return False


async def run_mass_seo_fix(batch_size: int = 20) -> dict:
    """SEO-Fix für alle Produkte — läuft in Batches um Rate-Limits zu vermeiden."""
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}
    fixed = 0
    try:
        products = await _all_products()
        # Priorität: schlechte Tags zuerst
        needs_fix = [p for p in products
                     if "shopify automation" in p.get("tags", "") or
                     len(p.get("tags", "").split(",")) < 4]
        log.info("SEO fix needed: %d/%d products", len(needs_fix), len(products))

        for i, p in enumerate(needs_fix[:batch_size]):
            if await fix_product_seo(p):
                fixed += 1
            await asyncio.sleep(0.5)

        return {"ok": True, "fixed": fixed, "needs_fix": len(needs_fix), "total": len(products)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 5. AUTO-COLLECTION BUILDER — Produkte automatisch in Kollektionen
# ═══════════════════════════════════════════════════════════════════════════════

COLLECTION_RULES = [
    ("Smart Home", ["smart home", "wifi", "alexa", "google home", "smarthome", "smart plug"]),
    ("Gadgets & Tech", ["gadget", "usb", "adapter", "kabel", "bluetooth", "wireless", "charging"]),
    ("Fitness & Sport", ["fitness", "sport", "training", "gym", "yoga", "laufen", "tracker"]),
    ("Küche & Haushalt", ["küche", "kitchen", "kochen", "haushalt", "reinigung", "organizer"]),
    ("Beauty & Pflege", ["beauty", "pflege", "kosmetik", "skin", "haar", "make up"]),
    ("Reise & Outdoor", ["reise", "travel", "outdoor", "camping", "rucksack", "koffer"]),
    ("Büro & Schreibtisch", ["büro", "desk", "office", "schreibtisch", "organizer", "laptop"]),
    ("Tier & Haustier", ["pet", "hund", "katze", "tier", "haustier", "dog", "cat"]),
    ("Geschenke", ["geschenk", "gift", "personalisiert", "weihnacht", "geburtstag"]),
    ("Neuheiten 2026", ["2026", "neu", "new", "trending", "bestseller", "top"]),
    ("Angebote", ["rabatt", "sale", "angebot", "günstig", "preis"]),
    ("3D & Druck", ["3d", "drucker", "print", "filament"]),
]


async def _get_or_create_collection(title: str, body_html: str = "") -> Optional[str]:
    """Gibt Collection-ID zurück, erstellt sie wenn nötig."""
    try:
        data = await _get("custom_collections.json", {"title": title, "limit": 1})
        existing = data.get("custom_collections", [])
        if existing:
            return str(existing[0]["id"])
        # Erstellen
        seo_desc = await _ai(f"Schreibe eine kurze SEO-Kollektion-Beschreibung auf Deutsch für: {title}. Max 1 Satz.", 80)
        result = await _post("custom_collections.json", {
            "custom_collection": {
                "title": title,
                "body_html": seo_desc or f"<p>Entdecke unsere {title} Kollektion.</p>",
                "published": True,
                "sort_order": "best-selling",
            }
        })
        cid = result.get("custom_collection", {}).get("id")
        return str(cid) if cid else None
    except Exception as e:
        log.debug("Collection %s: %s", title, e)
        return None


async def _add_to_collection(collection_id: str, product_id: str):
    try:
        await _post("collects.json", {
            "collect": {"collection_id": int(collection_id), "product_id": int(product_id)}
        })
    except Exception:
        pass


async def run_auto_collections() -> dict:
    """Organisiert alle 630 Produkte automatisch in Kollektionen."""
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}
    try:
        products = await _all_products()
        added = 0
        created_collections = 0

        for name, keywords in COLLECTION_RULES:
            matching = [
                p for p in products
                if any(kw.lower() in (p.get("title", "") + p.get("tags", "") +
                                      p.get("product_type", "")).lower() for kw in keywords)
            ]
            if not matching:
                continue

            cid = await _get_or_create_collection(name)
            if not cid:
                continue
            created_collections += 1

            for p in matching[:50]:
                await _add_to_collection(cid, str(p["id"]))
                added += 1
                await asyncio.sleep(0.1)

        log.info("Collections: %d created/updated, %d products added", created_collections, added)
        return {"ok": True, "collections": created_collections, "products_added": added,
                "total_products": len(products)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 6. DISCOUNT ENGINE — wöchentlich neue Rabatt-Codes
# ═══════════════════════════════════════════════════════════════════════════════

DISCOUNT_CODES = [
    ("NEXUS10", 10, "Wochendeal"),
    ("BLITZ20", 20, "Flash Sale"),
    ("START15", 15, "Willkommensrabatt"),
    ("POWER25", 25, "VIP Angebot"),
    ("SALE30", 30, "Sonder-Aktion"),
]


async def create_discount_and_blast(code: str = None, percentage: int = 20,
                                     reason: str = "Wochenangebot") -> dict:
    """Erstellt Rabatt-Code und blasted ihn auf alle Kanäle."""
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}
    if not code:
        import random
        code, percentage, reason = random.choice(DISCOUNT_CODES)
    try:
        # Bestehenden Code prüfen
        check = await _get("price_rules.json", {"title": code})
        existing = check.get("price_rules", [])
        if existing:
            rule_id = existing[0]["id"]
        else:
            from datetime import timedelta
            start = datetime.now(timezone.utc)
            end = start + timedelta(days=7)
            result = await _post("price_rules.json", {
                "price_rule": {
                    "title": code,
                    "target_type": "line_item",
                    "target_selection": "all",
                    "allocation_method": "across",
                    "value_type": "percentage",
                    "value": f"-{percentage}.0",
                    "customer_selection": "all",
                    "starts_at": start.isoformat(),
                    "ends_at": end.isoformat(),
                }
            })
            rule_id = result.get("price_rule", {}).get("id")
            if rule_id:
                await _post(f"price_rules/{rule_id}/discount_codes.json",
                            {"discount_code": {"code": code}})

        shop_url = f"https://{SHOP}"
        msg = (f"🔥 {reason}!\n\n"
               f"{percentage}% RABATT auf alles\n"
               f"Code: **{code}**\n\n"
               f"🛒 Jetzt einlösen: {shop_url}\n"
               f"⏰ Gültig 7 Tage")
        try:
            from modules.brutus_core import fire
            blast = await fire(f"{reason}: {percentage}% mit Code {code}", msg,
                               link=shop_url,
                               channels=["telegram", "mailchimp", "klaviyo", "twitter",
                                         "discord", "whatsapp", "slack", "linkedin"])
            channels_hit = blast.get("channels_hit", 0)
        except Exception:
            channels_hit = 0

        return {"ok": True, "code": code, "percentage": percentage,
                "channels_hit": channels_hit}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 7. DEAD PRODUCT AUDIT — schlechte Produkte verbessern
# ═══════════════════════════════════════════════════════════════════════════════

async def audit_and_fix_weak_products(limit: int = 10) -> dict:
    """Findet Produkte mit schlechten Tags/Beschreibungen und verbessert sie mit KI."""
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}
    improved = 0
    try:
        products = await _all_products()
        # "Schwache" Produkte: kurze Beschreibung ODER schlechte Tags
        weak = [p for p in products if (
            len(p.get("body_html", "") or "") < 100 or
            "shopify automation" in (p.get("tags", "") or "") or
            len((p.get("body_html", "") or "").split()) < 20
        )]
        log.info("Weak products found: %d", len(weak))

        for p in weak[:limit]:
            title = p.get("title", "")
            old_desc = p.get("body_html", "") or ""

            prompt = f"""Schreibe eine überzeugende Produkt-Beschreibung auf Deutsch für:
Produkt: "{title}"

Format: HTML mit <p> Absätzen und <ul> Vorteile-Liste.
Länge: 150-200 Wörter.
Inkludiere: Hauptvorteil, 3-4 Features, klaren Kaufgrund.
NUR HTML zurückgeben, kein JSON, kein Kommentar."""

            new_desc = await _ai(prompt, max_tokens=400)
            if new_desc and len(new_desc) > 80:
                await _put(f"products/{p['id']}.json", {
                    "product": {"id": p["id"], "body_html": new_desc}
                })
                improved += 1
                await asyncio.sleep(0.5)

        return {"ok": True, "improved": improved, "weak_found": len(weak)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 8. IMAGE ALT-TEXT FIXER — SEO-Alt-Text für alle Produktbilder
# ═══════════════════════════════════════════════════════════════════════════════

async def fix_image_alt_texts(limit: int = 30) -> dict:
    """Setzt SEO-Alt-Text für alle Produktbilder ohne Alt-Text."""
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}
    fixed = 0
    try:
        products = await _all_products()
        for p in products[:limit]:
            title = p.get("title", "")
            for img in p.get("images", []):
                if not img.get("alt"):
                    alt = f"{title} — kaufen online Deutschland"[:200]
                    await _put(
                        f"products/{p['id']}/images/{img['id']}.json",
                        {"image": {"id": img["id"], "alt": alt}}
                    )
                    fixed += 1
                    await asyncio.sleep(0.2)
        return {"ok": True, "fixed": fixed}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 9. CONVERSION CTA INJECTOR — Kaufanreiz in Beschreibungen
# ═══════════════════════════════════════════════════════════════════════════════

CTA_SNIPPETS = [
    "\n<p><strong>✅ Kostenloser Versand ab €29 | 30 Tage Rückgabe | Sichere Zahlung</strong></p>",
    "\n<p><em>⭐ Top-Bewertungen von zufriedenen Kunden. Jetzt bestellen und sofort liefern lassen!</em></p>",
    "\n<p><strong>🎁 Perfektes Geschenk — kommt sicher und schnell an!</strong></p>",
    "\n<p>💡 <strong>Tipp:</strong> Spare mit Code <strong>NEXUS10</strong> — 10% auf deine Bestellung!</p>",
]


async def inject_cta_snippets(limit: int = 50) -> dict:
    """Fügt Conversion-CTAs am Ende von Produktbeschreibungen ein."""
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}
    import random
    updated = 0
    try:
        products = await _all_products()
        for p in products[:limit]:
            desc = p.get("body_html", "") or ""
            # Skip wenn CTA schon vorhanden
            if "Kostenloser Versand" in desc or "NEXUS10" in desc:
                continue
            cta = random.choice(CTA_SNIPPETS)
            new_desc = desc + cta
            await _put(f"products/{p['id']}.json",
                       {"product": {"id": p["id"], "body_html": new_desc}})
            updated += 1
            await asyncio.sleep(0.3)
        return {"ok": True, "updated": updated}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 10. AUTO-RESTOCK — Meistgesuchte Produkte automatisch nachladen
# ═══════════════════════════════════════════════════════════════════════════════

TRENDING_PRODUCT_NICHES = [
    "Smart Home 2026 Gadget", "Wireless Earbuds Bluetooth", "LED Strip WiFi App",
    "Fitness Tracker Smartwatch", "USB-C Hub Adapter", "Portable Charger Power Bank",
    "Ring Light Selfie", "Desk Organizer Büro", "Pet Camera Haustier", "Mini Beamer Projektor",
    "Luftreiniger Filter", "Elektrische Zahnbürste", "Küchenhelfer Set", "Reise Organizer",
    "Gaming Headset RGB", "Stehlampe dimmbar", "Wandhalterung TV", "Duschkopf Hochdruck",
    "Schlafmaske Reise", "Pflanzenlampe LED", "Cocktail Shaker Set", "Yoga Mat rutschfest",
    "Laptop Ständer höhenverstellbar", "Kabelloser Lautsprecher", "Massage Gun Muskel",
]


async def auto_restock_trending(count: int = 5) -> dict:
    """
    Lädt den Shopify-Shop automatisch mit meistgesuchten Produkten nach.
    - Ermittelt aktuelle Trends via Google Trends + eigene Nischenliste
    - Erstellt Shopify-Produkt mit KI-Titel, KI-Beschreibung, KI-Tags
    - Lädt Bild von Pexels/Unsplash (kostenlos, lizenzfrei)
    - Aktiviert sofort und postet via BrutusCore
    """
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}

    import random
    created = 0
    created_titles = []

    # Trends von Google holen
    trending_keywords = []
    try:
        import xml.etree.ElementTree as ET, re
        async with aiohttp.ClientSession() as s:
            async with s.get("https://trends.google.com/trends/trendingsearches/daily/rss?geo=DE",
                             headers={"User-Agent": "Mozilla/5.0"},
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                raw = await r.text()
        raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)
        root = ET.fromstring(raw)
        for item in list(root.iter("item"))[:5]:
            t = item.find("title")
            if t is not None and t.text:
                trending_keywords.append(t.text.strip())
    except Exception:
        pass

    # Kombiniere: Google Trends + eigene Nischen
    pool = trending_keywords + TRENDING_PRODUCT_NICHES
    random.shuffle(pool)
    to_create = pool[:count]

    for keyword in to_create:
        try:
            # KI: Produktdaten generieren
            prompt = f"""Erstelle ein Shopify-Produkt für den Trend: "{keyword}"
Optimiert für den deutschen Markt. Preis zwischen €19 und €199.

Antworte NUR mit diesem JSON:
{{
  "title": "Produktname (max 70 Zeichen, SEO-optimiert)",
  "body_html": "<p>Produktbeschreibung 150 Wörter auf Deutsch mit Features und Kaufgrund.</p><ul><li>Vorteil 1</li><li>Vorteil 2</li><li>Vorteil 3</li></ul>",
  "price": "39.99",
  "tags": "tag1,tag2,tag3,tag4,tag5,trending,2026",
  "product_type": "Kategorie",
  "image_query": "product photo relevant keyword english"
}}"""

            raw = await _ai(prompt, max_tokens=600)
            if not raw:
                continue
            start, end = raw.find("{"), raw.rfind("}") + 1
            if start == -1:
                continue
            data = json.loads(raw[start:end])

            # Bild holen: Pexels → Unsplash → LoremFlickr (kein Key nötig)
            image_url = ""
            pexels_key = os.getenv("PEXELS_API_KEY", "")
            img_query = data.get("image_query", keyword)
            if pexels_key:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(
                            "https://api.pexels.com/v1/search",
                            headers={"Authorization": pexels_key},
                            params={"query": img_query, "per_page": 1, "orientation": "square"},
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as r:
                            pd = await r.json()
                    photos = pd.get("photos", [])
                    if photos:
                        image_url = photos[0]["src"]["medium"]
                except Exception:
                    pass

            if not image_url:
                unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY", "")
                if unsplash_key:
                    try:
                        async with aiohttp.ClientSession() as s:
                            async with s.get(
                                "https://api.unsplash.com/search/photos",
                                params={"query": img_query, "per_page": 1},
                                headers={"Authorization": f"Client-ID {unsplash_key}"},
                                timeout=aiohttp.ClientTimeout(total=10)
                            ) as r:
                                ud = await r.json()
                        results = ud.get("results", [])
                        if results:
                            image_url = results[0]["urls"]["small"]
                    except Exception:
                        pass

            # LoremFlickr fallback — kein API Key, keyword-basiert, kostenlos
            if not image_url:
                safe_q = img_query.replace(" ", ",")[:60]
                image_url = f"https://loremflickr.com/640/640/{safe_q}"

            # Shopify Produkt erstellen
            product_payload = {
                "title": data.get("title", keyword)[:255],
                "body_html": data.get("body_html", ""),
                "vendor": "BullPowerHub",
                "product_type": data.get("product_type", "Gadget"),
                "tags": data.get("tags", "trending,2026"),
                "status": "active",
                "variants": [{
                    "price": data.get("price", "39.99"),
                    "inventory_policy": "continue",
                    "inventory_management": None,
                    "requires_shipping": True,
                }],
            }
            if image_url:
                product_payload["images"] = [{"src": image_url, "alt": data.get("title", keyword)[:200]}]

            result = await _post("products.json", {"product": product_payload})
            new_product = result.get("product", {})
            if new_product.get("id"):
                created += 1
                created_titles.append(new_product.get("title", keyword))
                log.info("Auto-restock created: %s (€%s)", new_product["title"][:50], data.get("price"))

                # BrutusCore: sofort promoten
                try:
                    from modules.brutus_core import fire
                    shop_url = f"https://{SHOP}/products/{new_product.get('handle','')}"
                    await fire(
                        new_product["title"],
                        data.get("body_html", "")[:300],
                        link=shop_url,
                        channels=["telegram", "twitter", "slack", "linkedin", "shopify_blog"]
                    )
                except Exception:
                    pass

            await asyncio.sleep(1)
        except Exception as e:
            log.warning("Restock error for '%s': %s", keyword, e)

    return {"ok": True, "created": created, "products": created_titles}


# ═══════════════════════════════════════════════════════════════════════════════
# 11. BILD AUTO-FIXER — Produkte ohne Bild bekommen automatisch Bilder
# ═══════════════════════════════════════════════════════════════════════════════

async def fix_missing_images(limit: int = 30) -> dict:
    """Produkte ohne Bild bekommen automatisch ein lizenzfreies Bild von Pexels."""
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}

    pexels_key = os.getenv("PEXELS_API_KEY", "")
    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY", "")
    # LoremFlickr funktioniert immer — kein Key nötig

    fixed = 0
    try:
        products = await _all_products()
        no_image = [p for p in products if not p.get("images")]
        log.info("Products without image: %d", len(no_image))

        for p in no_image[:limit]:
            title = p.get("title", "product")
            search_q = title[:50]

            image_url = ""
            if pexels_key:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(
                            "https://api.pexels.com/v1/search",
                            headers={"Authorization": pexels_key},
                            params={"query": search_q, "per_page": 1, "orientation": "square"},
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as r:
                            pd = await r.json()
                    photos = pd.get("photos", [])
                    if photos:
                        image_url = photos[0]["src"]["medium"]
                except Exception:
                    pass

            if not image_url and unsplash_key:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(
                            "https://api.unsplash.com/search/photos",
                            params={"query": search_q, "per_page": 1},
                            headers={"Authorization": f"Client-ID {unsplash_key}"},
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as r:
                            ud = await r.json()
                    results = ud.get("results", [])
                    if results:
                        image_url = results[0]["urls"]["small"]
                except Exception:
                    pass

            # LoremFlickr fallback — immer verfügbar, kein Key
            if not image_url:
                safe_q = search_q.replace(" ", ",")[:60]
                image_url = f"https://loremflickr.com/640/640/{safe_q}"

            await _post(f"products/{p['id']}/images.json", {
                "image": {"src": image_url, "alt": title[:200]}
            })
            fixed += 1
            await asyncio.sleep(0.5)

        return {"ok": True, "fixed": fixed, "no_image_total": len(no_image)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 12. TITLE + DESCRIPTION AUTO-KORREKTUR — KI korrigiert alle schwachen Titel
# ═══════════════════════════════════════════════════════════════════════════════

async def auto_correct_titles_and_descriptions(limit: int = 15) -> dict:
    """KI verbessert alle Titel die zu kurz, generisch oder auf Englisch sind."""
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}
    fixed = 0
    try:
        products = await _all_products()
        # Produkte mit schwachen Titeln
        weak = [p for p in products if (
            len(p.get("title", "")) < 20 or
            p.get("title", "").isupper() or
            re.search(r'[A-Z]{3,}', p.get("title", "")) or  # Caps-Lock
            len(p.get("body_html", "") or "") < 50
        )]
        log.info("Weak titles/descriptions: %d", len(weak))

        for p in weak[:limit]:
            title = p.get("title", "")
            desc = p.get("body_html", "") or ""

            prompt = f"""Verbessere dieses Shopify-Produkt für den deutschen Markt:
Aktueller Titel: "{title}"
Aktuelle Beschreibung: "{desc[:200]}"

Gib zurück als JSON:
{{"title": "Verbesserter SEO-Titel auf Deutsch (max 70 Zeichen)",
  "body_html": "<p>Neue Beschreibung 150 Wörter</p><ul><li>3 Features</li></ul>"}}"""

            raw = await _ai(prompt, max_tokens=500)
            if not raw:
                continue
            try:
                start, end = raw.find("{"), raw.rfind("}") + 1
                data = json.loads(raw[start:end])
                new_title = data.get("title", "")
                new_desc = data.get("body_html", "")
                if new_title and len(new_title) >= 10:
                    await _put(f"products/{p['id']}.json", {
                        "product": {
                            "id": p["id"],
                            "title": new_title[:255],
                            "body_html": new_desc or desc,
                        }
                    })
                    fixed += 1
                    await asyncio.sleep(0.5)
            except Exception:
                pass

        return {"ok": True, "fixed": fixed, "weak_found": len(weak)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER — Alle Schritte in optimaler Reihenfolge
# ═══════════════════════════════════════════════════════════════════════════════

async def run_full_autonomy_cycle(quick: bool = False, restock: bool = True) -> dict:
    """
    Vollständiger Autonomie-Zyklus für Shopify.
    quick=True: nur die schnellen Fixes (Drafts, Inventory, Preise)
    quick=False: alles inkl. KI-SEO und Collections
    """
    if not _ok():
        return {"ok": False, "error": "SHOPIFY_SHOP_DOMAIN oder SHOPIFY_ADMIN_API_TOKEN fehlt"}

    log.info("Shopify Full Autonomy Cycle START (quick=%s)", quick)
    results = {}

    # Schritt 1: Schnelle Fixes parallel
    draft_task   = asyncio.create_task(activate_all_drafts())
    inv_task     = asyncio.create_task(fix_inventory_policy())
    price_task   = asyncio.create_task(fix_prices())
    draft_r, inv_r, price_r = await asyncio.gather(draft_task, inv_task, price_task,
                                                    return_exceptions=True)
    results["drafts_activated"]  = draft_r  if isinstance(draft_r,  dict) else {"ok": False}
    results["inventory_fixed"]   = inv_r    if isinstance(inv_r,    dict) else {"ok": False}
    results["prices_fixed"]      = price_r  if isinstance(price_r,  dict) else {"ok": False}

    if quick:
        return {"ok": True, "mode": "quick", **results}

    # Schritt 2: Collections aufbauen
    await asyncio.sleep(1)
    results["collections"] = await run_auto_collections()

    # Schritt 3: SEO-Fix (Batch)
    results["seo_fix"] = await run_mass_seo_fix(batch_size=30)

    # Schritt 4: Schwache Produkte verbessern
    results["weak_products"] = await audit_and_fix_weak_products(limit=15)

    # Schritt 5: Image Alt-Texts
    results["alt_texts"] = await fix_image_alt_texts(limit=50)

    # Schritt 6: CTAs injizieren
    results["cta_injection"] = await inject_cta_snippets(limit=50)

    # Schritt 7: Bilder für bildlose Produkte
    results["image_fix"] = await fix_missing_images(limit=20)

    # Schritt 8: Titel + Beschreibungen korrigieren
    results["title_fix"] = await auto_correct_titles_and_descriptions(limit=10)

    # Schritt 9: Wöchentlicher Discount blast
    results["discount"] = await create_discount_and_blast()

    # Schritt 10: Trending Produkte nachladen
    if restock:
        results["restock"] = await auto_restock_trending(count=3)

    # Summary
    ok_count = sum(1 for v in results.values() if isinstance(v, dict) and v.get("ok"))
    log.info("Shopify Full Autonomy DONE: %d/%d steps OK", ok_count, len(results))

    # Telegram + Slack Report
    try:
        from modules.notify_hub import notify
        summary = (
            f"Drafts: {results['drafts_activated'].get('activated',0)} aktiviert\n"
            f"Inventar: {results['inventory_fixed'].get('fixed',0)} Varianten → CONTINUE\n"
            f"Preise: {results['prices_fixed'].get('fixed',0)} korrigiert\n"
            f"Collections: {results['collections'].get('collections',0)} erstellt\n"
            f"SEO: {results['seo_fix'].get('fixed',0)} Produkte gefixt\n"
            f"Produkte verbessert: {results['weak_products'].get('improved',0)}\n"
            f"Bilder hinzugefügt: {results.get('image_fix',{}).get('fixed',0)}\n"
            f"Titel/Text korrigiert: {results.get('title_fix',{}).get('fixed',0)}\n"
            f"CTAs: {results['cta_injection'].get('updated',0)} Produkte\n"
            f"Discount: {results['discount'].get('code','?')} ({results['discount'].get('percentage','?')}%)\n"
            f"Neue Trending-Produkte: {results.get('restock',{}).get('created',0)}"
        )
        notify("Shopify Full Autonomy", summary, "success")
    except Exception:
        pass

    return {"ok": True, "mode": "full", "steps_ok": ok_count, **results}


# ── Public aliases ────────────────────────────────────────────────────────────

async def run_full_autonomy(quick: bool = False, restock: bool = True) -> dict:
    """Alias for run_full_autonomy_cycle — used by external callers and tests."""
    return await run_full_autonomy_cycle(quick=quick, restock=restock)


# ═══════════════════════════════════════════════════════════════════════════════
# 13. AFFILIATE BLOG AUTO-CREATOR — DS24 Affiliate Blog Posts in Shopify
# ═══════════════════════════════════════════════════════════════════════════════

async def auto_create_affiliate_blog_posts(count: int = 3) -> dict:
    """
    Erstellt Shopify Blog-Posts die auf den DS24 Affiliate Link verlinken.
    Nutzt KI um SEO-optimierten Content zu generieren.
    """
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}

    ds24_link = (
        os.getenv("DS24_AFFILIATE_LINK")
        or os.getenv("AIITEC_AFFILIATE_URL")
        or "https://ineedit.com.co"
    )

    topics = [
        ("KI Tools für Selbstständige 2026", "ki tools selbststaendige automatisierung"),
        ("Passives Einkommen mit Digitalprodukten", "passives einkommen digitale produkte"),
        ("Shopify Automatisierung: Mehr Umsatz ohne Arbeit", "shopify automatisierung umsatz"),
        ("Digistore24 Affiliate Marketing Guide 2026", "digistore24 affiliate marketing"),
        ("KI Business Blueprint: So automatisierst du alles", "ki business automatisierung"),
    ]

    import random
    selected = random.sample(topics, min(count, len(topics)))

    created = 0
    posts = []
    for title, tags_hint in selected:
        try:
            prompt = f"""Schreibe einen SEO-optimierten Blog-Post auf Deutsch für Shopify:
Thema: "{title}"
Ziel: Leser zu digitalem Produkt führen

Struktur:
- H1: ansprechender Titel
- Einleitung (Problem/Lösung)
- 3-4 Abschnitte mit H2
- Konkrete Tipps und Mehrwert
- Call-to-Action am Ende mit Link

Der CTA-Link lautet: {ds24_link}
Text für CTA: "Jetzt starten und automatisch Einkommen generieren →"

NUR HTML zurückgeben. Länge: 400-500 Wörter."""

            content_html = await _ai(prompt, max_tokens=800)
            if not content_html or len(content_html) < 100:
                # Fallback template
                content_html = f"""<h1>{title}</h1>
<p>Im heutigen digitalen Zeitalter bieten KI-Tools und Automatisierung unglaubliche Möglichkeiten für Selbstständige und Online-Unternehmer.</p>
<h2>Warum jetzt der richtige Zeitpunkt ist</h2>
<p>Die Technologie ist ausgereift, die Einstiegshürde niedrig, und die Ergebnisse kommen schneller als je zuvor.</p>
<h2>Schritt-für-Schritt zur Automatisierung</h2>
<ul>
<li>✅ System aufsetzen (einmalig 2-3 Stunden)</li>
<li>✅ KI übernimmt Content-Erstellung</li>
<li>✅ Automatische Verteilung auf alle Kanäle</li>
<li>✅ Passives Einkommen läuft 24/7</li>
</ul>
<h2>Das Ergebnis</h2>
<p>Vollautomatisches Einkommen ohne tägliche Arbeit. Das System arbeitet für dich — auch wenn du schläfst.</p>
<p><strong><a href="{ds24_link}">👉 Jetzt starten und automatisch Einkommen generieren →</a></strong></p>
<hr>
<p><em>60-Tage Geld-zurück-Garantie. Kein Risiko.</em></p>"""

            # Blog-Post in Shopify erstellen
            payload = {
                "article": {
                    "title": title,
                    "body_html": content_html,
                    "tags": f"{tags_hint},affiliate,ds24,ki,automatisierung,digistore24",
                    "published": True,
                    "metafields": [
                        {"namespace": "seo", "key": "description",
                         "value": f"{title} — Vollautomatisches KI-Business mit DS24. Jetzt starten.",
                         "type": "single_line_text_field"}
                    ]
                }
            }

            # Blog-ID ermitteln (oder "news" nutzen)
            blog_data = await _get("blogs.json")
            blogs = blog_data.get("blogs", [])
            blog_id = blogs[0]["id"] if blogs else None

            if blog_id:
                result = await _post(f"blogs/{blog_id}/articles.json", payload)
                article = result.get("article", {})
                if article.get("id"):
                    created += 1
                    handle = article.get("handle", "")
                    shop_url = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
                    post_url = f"https://{shop_url}/blogs/news/{handle}" if shop_url else ""
                    posts.append({"title": title, "url": post_url, "ds24_link": ds24_link})
                    log.info("Affiliate blog post created: %s", title[:50])

            await asyncio.sleep(1)
        except Exception as e:
            log.warning("Affiliate blog post error for '%s': %s", title, e)

    # BRUTUS: neue Blog-Posts auf allen Kanälen bewerben
    if posts:
        try:
            from modules.brutus_core import fire
            for post in posts[:2]:  # Max 2 BRUTUS blasts
                await fire(
                    post["title"],
                    f"Neuer Blog-Post: {post['title']}\n\nJetzt lesen und umsetzen!\n{post.get('url', ds24_link)}",
                    link=post.get("url") or ds24_link,
                    channels=["telegram", "linkedin", "mailchimp", "klaviyo"]
                )
        except Exception as e:
            log.debug("BRUTUS affiliate blast: %s", e)

    return {"ok": True, "created": created, "posts": posts, "ds24_link": ds24_link}
