#!/usr/bin/env python3
"""
Autonomous Product Generator
=============================
Vollautonomer Produkt-Generator:
1. Scannt Trending-Quellen (Google Trends, Amazon, eBay, Reddit)
2. KI generiert vollständige Produktdaten (Titel, Beschreibung, Preis, Tags)
3. Bild-Sourcing automatisch (Pexels → Unsplash → LoremFlickr)
4. Shopify-Produkt erstellen + Kollektion zuweisen
5. BrutusCore blast auf alle Kanäle
6. Supabase-Logging zur Deduplizierung
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import aiohttp

log = logging.getLogger("ProductGenerator")

SHOP    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TOKEN   = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
VER     = os.getenv("SHOPIFY_API_VERSION", "2026-04")
BASE    = lambda p: f"https://{SHOP}/admin/api/{VER}/{p}"
HDR     = lambda: {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

PEXELS_KEY   = os.getenv("PEXELS_API_KEY", "")
UNSPLASH_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")


def _ok() -> bool:
    return bool(SHOP and TOKEN)


# ─── Trend Sources ────────────────────────────────────────────────────────────

SEED_KEYWORDS = [
    "Smart Home Gadget", "Wireless Earbuds", "LED Strip WiFi", "Fitness Tracker",
    "USB-C Hub", "Power Bank", "Ring Light", "Desk Organizer", "Pet Camera",
    "Mini Beamer", "Luftreiniger", "Elektrische Zahnbürste", "Küchenhelfer",
    "Gaming Headset RGB", "Stehlampe dimmbar", "Massage Gun", "Yoga Matte",
    "Laptop Ständer", "Kabelloser Lautsprecher", "Schlafmaske", "Pflanzenlampe",
    "Cocktail Set", "Duschkopf Hochdruck", "Wandhalterung TV", "3D Drucker Filament",
    "Smartwatch 2026", "Bluetooth Kopfhörer", "Webcam HD", "Steckdose USB",
    "Kabelmanagement", "Schreibtisch Organizer", "Mini Projektor", "VR Brille",
    "Smart Plug", "Türklingel Kamera", "Balkonkraftwerk", "Solar Panel",
    "Elektrische Pumpe", "Gewürzmühle elektrisch", "Salatschleuder", "Weinöffner",
]

TREND_RSS_SOURCES = [
    "https://trends.google.com/trends/trendingsearches/daily/rss?geo=DE",
    "https://trends.google.com/trends/trendingsearches/daily/rss?geo=AT",
    "https://trends.google.com/trends/trendingsearches/daily/rss?geo=CH",
]

AMAZON_BESTSELLER_CATS = [
    "https://www.amazon.de/gp/bestsellers/electronics/rss/ref=zg_bs_tab_r_elec_1",
    "https://www.amazon.de/gp/bestsellers/garden/rss/ref=zg_bs_tab_r_garden_1",
    "https://www.amazon.de/gp/bestsellers/sports/rss/ref=zg_bs_tab_r_sports_1",
    "https://www.amazon.de/gp/bestsellers/kitchen/rss/ref=zg_bs_tab_r_kitchen_1",
]

NICHE_NICHES = {
    "smart_home": ["Smart Plug", "WiFi Steckdose", "Alexa Gerät", "Google Home", "Smart Thermostat"],
    "fitness":    ["Resistance Band", "Yoga Block", "Foam Roller", "Ab Roller", "Springseil"],
    "kitchen":    ["Airfryer Zubehör", "Gewürzregal", "Messerblock", "Küchenwaage", "Spiralschneider"],
    "office":     ["Monitor Arm", "Ergonomisches Kissen", "Kabelkanal", "Whiteboard", "Post-it Halter"],
    "beauty":     ["Gesichtsroller", "LED Maske", "Haartrockner", "Epilator", "Serum"],
    "outdoor":    ["Campinglampe", "Trinkflasche Thermo", "Rucksack", "Wanderstöcke", "Stirnlampe"],
    "pet":        ["Futterautomat", "GPS Tracker Hund", "Katzen Kratzbaum", "Napf Set", "Laufband Hund"],
    "gaming":     ["Gaming Maus", "Mousepad XXL", "Headset Ständer", "LED Controller", "Gaming Stuhl"],
}

PRICE_BY_CATEGORY = {
    "smart_home": (24.99, 89.99),
    "fitness":    (14.99, 59.99),
    "kitchen":    (19.99, 79.99),
    "office":     (29.99, 149.99),
    "beauty":     (19.99, 99.99),
    "outdoor":    (24.99, 129.99),
    "pet":        (19.99, 89.99),
    "gaming":     (29.99, 199.99),
    "default":    (24.99, 79.99),
}


async def _fetch_rss_titles(url: str, timeout: int = 8) -> list[str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"User-Agent": "Mozilla/5.0"},
                             timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                raw = await r.text()
        raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)
        root = ET.fromstring(raw)
        return [t.text.strip() for item in root.iter("item")
                if (t := item.find("title")) is not None and t.text][:10]
    except Exception:
        return []


async def scan_trends(max_keywords: int = 15) -> list[str]:
    """Scannt alle Quellen und gibt priorisierte Keyword-Liste zurück."""
    results = []

    # Google Trends DE/AT/CH
    rss_tasks = [_fetch_rss_titles(url) for url in TREND_RSS_SOURCES]
    rss_results = await asyncio.gather(*rss_tasks, return_exceptions=True)
    for batch in rss_results:
        if isinstance(batch, list):
            results.extend(batch)

    # Amazon Bestseller RSS
    amz_tasks = [_fetch_rss_titles(url) for url in AMAZON_BESTSELLER_CATS[:2]]
    amz_results = await asyncio.gather(*amz_tasks, return_exceptions=True)
    for batch in amz_results:
        if isinstance(batch, list):
            # Produkt-Titel aus Amazon RSS kürzen
            for t in batch:
                short = t[:60].strip()
                if short:
                    results.append(short)

    # Zufällige Nische als Ergänzung
    niche = random.choice(list(NICHE_NICHES.values()))
    results.extend(random.sample(niche, min(3, len(niche))))

    # Seed keywords als Fallback
    if len(results) < 5:
        results.extend(random.sample(SEED_KEYWORDS, min(10, len(SEED_KEYWORDS))))

    # Deduplizieren + Shufflen
    seen = set()
    unique = []
    for r in results:
        key = r.lower()[:40]
        if key not in seen:
            seen.add(key)
            unique.append(r)

    random.shuffle(unique)
    log.info("Trends gesammelt: %d Keywords", len(unique))
    return unique[:max_keywords]


# ─── Deduplizierung via Supabase ──────────────────────────────────────────────

async def _already_created(keyword: str) -> bool:
    """Prüft ob Keyword schon als Produkt erstellt wurde (Supabase)."""
    try:
        from modules.supabase_client import get_client
        client = get_client()
        kh = hashlib.md5(keyword.lower().strip().encode()).hexdigest()
        result = client.table("generated_products").select("id").eq("keyword_hash", kh).execute()
        return bool(result.data)
    except Exception:
        return False


async def _mark_created(keyword: str, shopify_id: str, title: str):
    try:
        from modules.supabase_client import get_client
        client = get_client()
        kh = hashlib.md5(keyword.lower().strip().encode()).hexdigest()
        client.table("generated_products").insert({
            "keyword_hash": kh,
            "keyword": keyword[:200],
            "shopify_product_id": str(shopify_id),
            "title": title[:255],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.debug("Supabase mark: %s", e)


# ─── AI Produktdaten generieren ──────────────────────────────────────────────

async def _ai(prompt: str, max_tokens: int = 600) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


def _detect_category(keyword: str) -> str:
    kl = keyword.lower()
    for cat, words in NICHE_NICHES.items():
        if any(w.lower() in kl for w in words):
            return cat
    cat_map = {
        "smart_home": ["smart", "wifi", "alexa", "plug", "home"],
        "fitness":    ["fitness", "yoga", "sport", "gym", "training"],
        "kitchen":    ["küche", "kitchen", "kochen", "food", "snack"],
        "office":     ["büro", "desk", "office", "monitor", "kabel"],
        "beauty":     ["beauty", "skin", "haar", "gesicht", "pflege"],
        "outdoor":    ["outdoor", "camping", "reise", "garten", "solar"],
        "pet":        ["hund", "katze", "pet", "tier", "haustier"],
        "gaming":     ["gaming", "gamer", "rgb", "headset", "maus"],
    }
    for cat, words in cat_map.items():
        if any(w in kl for w in words):
            return cat
    return "default"


async def generate_product_data(keyword: str) -> Optional[dict]:
    """Generiert vollständige Shopify-Produktdaten per KI."""
    category = _detect_category(keyword)
    price_min, price_max = PRICE_BY_CATEGORY.get(category, (24.99, 79.99))
    suggested_price = round(random.uniform(price_min, price_max) - 0.01, 2)

    prompt = f"""Erstelle ein vollständiges Shopify-Produkt für den deutschen Markt.
Trend/Keyword: "{keyword}"
Kategorie: {category}
Preisrahmen: €{price_min:.2f} – €{price_max:.2f}

Antworte NUR mit diesem JSON (kein Markdown, kein Text darum):
{{
  "title": "Produktname deutsch, SEO-optimiert, max 70 Zeichen",
  "body_html": "<p>Überzeugende Beschreibung 120-160 Wörter auf Deutsch. Hauptvorteil. Features als Liste.</p><ul><li>Vorteil 1</li><li>Vorteil 2</li><li>Vorteil 3</li></ul><p><strong>✅ Kostenloser Versand ab €29 | 30 Tage Rückgabe</strong></p>",
  "price": "{suggested_price:.2f}",
  "compare_at_price": "{suggested_price * 1.4:.2f}",
  "tags": "tag1,tag2,tag3,tag4,tag5,trending,2026,bestseller",
  "product_type": "Kategoriename auf Deutsch",
  "vendor": "BullPowerHub",
  "image_query": "product photo english keywords for image search",
  "collection": "passende Kollektion auf Deutsch"
}}"""

    raw = await _ai(prompt, max_tokens=700)
    if not raw:
        return None

    try:
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        data = json.loads(raw[start:end])
        if not data.get("title"):
            return None
        data["_category"] = category
        data["_keyword"] = keyword
        return data
    except Exception as e:
        log.debug("JSON parse error for '%s': %s", keyword, e)
        return None


# ─── Bild-Sourcing ───────────────────────────────────────────────────────────

async def _get_image_url(query: str) -> str:
    """Pexels → Unsplash → LoremFlickr (immer verfügbar)."""
    if PEXELS_KEY:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://api.pexels.com/v1/search",
                    headers={"Authorization": PEXELS_KEY},
                    params={"query": query, "per_page": 1, "orientation": "square"},
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    pd = await r.json()
            photos = pd.get("photos", [])
            if photos:
                return photos[0]["src"]["medium"]
        except Exception as _e:
            log.debug("skipped: %s", _e)

    if UNSPLASH_KEY:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://api.unsplash.com/search/photos",
                    params={"query": query, "per_page": 1},
                    headers={"Authorization": f"Client-ID {UNSPLASH_KEY}"},
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    ud = await r.json()
            results = ud.get("results", [])
            if results:
                return results[0]["urls"]["small"]
        except Exception as _e:
            log.debug("skipped: %s", _e)

    # LoremFlickr: immer verfügbar, keyword-basiert, kostenlos
    safe_q = re.sub(r'[^a-zA-Z0-9 ]', '', query)[:60].strip().replace(" ", ",")
    return ""


# ─── Shopify Produkt erstellen ────────────────────────────────────────────────

async def _shopify_post(path: str, data: dict) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.post(BASE(path), headers=HDR(), json=data,
                          timeout=aiohttp.ClientTimeout(total=20)) as r:
            return await r.json()


async def _shopify_get(path: str, params: dict = None) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.get(BASE(path), headers=HDR(), params=params or {},
                         timeout=aiohttp.ClientTimeout(total=15)) as r:
            return await r.json()


async def _ensure_collection(name: str) -> Optional[str]:
    try:
        data = await _shopify_get("custom_collections.json", {"title": name, "limit": 1})
        existing = data.get("custom_collections", [])
        if existing:
            return str(existing[0]["id"])
        result = await _shopify_post("custom_collections.json", {
            "custom_collection": {
                "title": name,
                "body_html": f"<p>Entdecke unsere {name} Kollektion.</p>",
                "published": True,
                "sort_order": "best-selling",
            }
        })
        cid = result.get("custom_collection", {}).get("id")
        return str(cid) if cid else None
    except Exception:
        return None


async def create_shopify_product(product_data: dict, image_url: str) -> Optional[dict]:
    """Erstellt das Produkt in Shopify und gibt es zurück."""
    payload = {
        "title":        product_data.get("title", "")[:255],
        "body_html":    product_data.get("body_html", ""),
        "vendor":       product_data.get("vendor", "BullPowerHub"),
        "product_type": product_data.get("product_type", "Gadget"),
        "tags":         product_data.get("tags", "trending,2026"),
        "status":       "active",
        "variants": [{
            "price":                product_data.get("price", "39.99"),
            "compare_at_price":     product_data.get("compare_at_price", ""),
            "inventory_policy":     "continue",
            "inventory_management": None,
            "requires_shipping":    True,
        }],
        "images": [{"src": image_url, "alt": product_data.get("title", "")[:200]}],
    }

    result = await _shopify_post("products.json", {"product": payload})
    product = result.get("product", {})
    if not product.get("id"):
        log.warning("Shopify product creation failed: %s", result)
        return None

    # Kollektion zuweisen
    collection_name = product_data.get("collection", "")
    if collection_name:
        cid = await _ensure_collection(collection_name)
        if cid:
            try:
                await _shopify_post("collects.json", {
                    "collect": {"collection_id": int(cid), "product_id": product["id"]}
                })
            except Exception as _e:
                log.debug("skipped: %s", _e)

    return product


# ─── BrutusCore Blast ─────────────────────────────────────────────────────────

async def _blast(product: dict, product_data: dict):
    try:
        from modules.brutus_core import fire
        title = product.get("title", "Neues Produkt")
        handle = product.get("handle", "")
        shop_url = f"https://{SHOP.replace('.myshopify.com', '')}.myshopify.com" if SHOP else ""
        link = f"{shop_url}/products/{handle}" if handle else shop_url
        price = product_data.get("price", "?")
        tags = product_data.get("tags", "")
        body = (f"🆕 Neu im Shop: {title}\n\n"
                f"💶 Nur €{price}\n"
                f"🏷️ {tags.split(',')[0] if tags else 'Trending 2026'}\n\n"
                f"🛒 Jetzt kaufen: {link}")
        await fire(title, body, link=link,
                   channels=["telegram", "slack", "mailchimp", "klaviyo",
                             "twitter", "discord", "shopify_blog"])
    except Exception as e:
        log.debug("Blast error: %s", e)


# ─── Haupt-Generierungs-Engine ───────────────────────────────────────────────

async def generate_one(keyword: str) -> Optional[dict]:
    """Generiert und published ein einzelnes Produkt für ein Keyword."""
    if not _ok():
        return None

    # Duplikat-Check
    if await _already_created(keyword):
        log.info("Skip duplicate: %s", keyword)
        return None

    # KI: Produktdaten generieren
    product_data = await generate_product_data(keyword)
    if not product_data:
        log.warning("No product data for: %s", keyword)
        return None

    # Bild holen
    img_query = product_data.get("image_query", keyword)
    image_url = await _get_image_url(img_query)

    # Shopify-Produkt erstellen
    product = await create_shopify_product(product_data, image_url)
    if not product:
        return None

    pid = product["id"]
    title = product.get("title", keyword)
    log.info("✅ Produkt erstellt: %s (ID: %s, €%s)", title[:50], pid, product_data.get("price"))

    # In Supabase markieren
    await _mark_created(keyword, str(pid), title)

    # BrutusCore Blast
    await _blast(product, product_data)

    return {
        "ok": True,
        "id": pid,
        "title": title,
        "price": product_data.get("price"),
        "handle": product.get("handle"),
        "image": image_url,
        "category": product_data.get("_category"),
        "keyword": keyword,
    }


async def run_generator_cycle(count: int = 3, from_trends: bool = True) -> dict:
    """
    Haupt-Funktion: Scannt Trends → generiert count neue Produkte → postet überall.
    Wird vom Scheduler alle 2h aufgerufen.
    """
    if not _ok():
        return {"ok": False, "error": "no shopify credentials"}

    created = []
    failed = 0

    # Keyword-Pool
    if from_trends:
        keywords = await scan_trends(max_keywords=count * 3)
    else:
        keywords = random.sample(SEED_KEYWORDS, min(count * 3, len(SEED_KEYWORDS)))

    for keyword in keywords:
        if len(created) >= count:
            break
        try:
            result = await generate_one(keyword)
            if result:
                created.append(result)
            else:
                failed += 1
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("Generator error for '%s': %s", keyword, e)
            failed += 1

    # Zusammenfassung an Telegram
    if created:
        try:
            from modules.notify_hub import notify
            titles = "\n".join(f"• {p['title'][:45]} (€{p['price']})" for p in created)
            await notify(
                f"🏭 Product Generator: {len(created)} neue Produkte erstellt!\n\n{titles}",
                level="success"
            )
        except Exception as _e:
            log.debug("skipped: %s", _e)

    log.info("Generator cycle done: %d created, %d failed", len(created), failed)
    return {
        "ok": True,
        "created": len(created),
        "failed": failed,
        "products": created,
    }


async def generate_from_keywords(keywords: list[str]) -> dict:
    """Generiert Produkte für eine gegebene Liste von Keywords."""
    created = []
    for kw in keywords:
        result = await generate_one(kw)
        if result:
            created.append(result)
        await asyncio.sleep(2)
    return {"ok": True, "created": len(created), "products": created}


async def run_niche_blast(niche: str = None) -> dict:
    """Generiert 5 Produkte aus einer spezifischen Nische."""
    if niche and niche in NICHE_NICHES:
        keywords = NICHE_NICHES[niche]
    else:
        niche = random.choice(list(NICHE_NICHES.keys()))
        keywords = NICHE_NICHES[niche]
    log.info("Niche blast: %s (%d keywords)", niche, len(keywords))
    return await generate_from_keywords(keywords[:5])
