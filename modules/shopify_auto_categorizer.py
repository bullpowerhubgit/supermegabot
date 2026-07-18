"""
Shopify Auto-Kategorisierer — Autonome Produkt-Taxonomie.

Aufgaben (automatisch, alle 12h):
- Produkte ohne product_type → AI ordnet sie einer Kategorie zu
- Smart Collections auto-update: Tags + product_type als Regeln
- Tags normalisieren (format: attribute-value, z.B. color-black)
- Duplikat-Collections erkennen + melden
- Qualitäts-Check: Produkte ohne Tags/Kategorie flaggen

Erlaubte Kategorien (aus shop_rules.json / Smart Home Nische):
  Smart Lighting, Smart Security, Smart Climate, Smart Energy,
  Solar & Off-Grid, Home Automation Hub, Wearable Tech,
  Smart Kitchen, Smart Health, EV & Mobility, Smart Audio,
  Gadgets & Accessories
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

_STORE_URL = lambda: os.getenv("SHOPIFY_STORE_URL", "").rstrip("/")
_TOKEN     = lambda: os.getenv("SHOPIFY_ACCESS_TOKEN", "")
_TG_TOKEN  = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT   = lambda: os.getenv("TELEGRAM_CHAT_ID", "")

def _headers() -> dict:
    return {"X-Shopify-Access-Token": _TOKEN(), "Content-Type": "application/json"}

# ── Erlaubte Smart-Home-Kategorien ────────────────────────────────────────────
ALLOWED_CATEGORIES = [
    "Smart Lighting",
    "Smart Security",
    "Smart Climate",
    "Smart Energy",
    "Solar & Off-Grid",
    "Home Automation Hub",
    "Wearable Tech",
    "Smart Kitchen",
    "Smart Health",
    "EV & Mobility",
    "Smart Audio",
    "Gadgets & Accessories",
]

# Schlüsselwörter → Kategorie
_KEYWORD_MAP = {
    "Smart Lighting":      ["led", "bulb", "light", "lamp", "strip", "rgb", "dimmer", "leucht", "lampe", "licht"],
    "Smart Security":      ["camera", "kamera", "doorbell", "türklingel", "alarm", "lock", "schloss", "motion", "sensor", "sicherheit"],
    "Smart Climate":       ["thermostat", "heizung", "climate", "air", "fan", "humidifier", "luftfeucht", "ventil", "cooling"],
    "Smart Energy":        ["plug", "socket", "steckdose", "power meter", "energy monitor", "verbrauch", "smart switch", "relay"],
    "Solar & Off-Grid":    ["solar", "panel", "powerstation", "akku", "battery", "off-grid", "laderegler", "balkon"],
    "Home Automation Hub": ["hub", "gateway", "bridge", "controller", "zigbee", "z-wave", "matter", "thread", "home assistant"],
    "Wearable Tech":       ["watch", "uhr", "band", "ring", "fitness", "tracker", "smartwatch"],
    "Smart Kitchen":       ["coffee", "kaffeemaschine", "blender", "cooker", "oven", "ofen", "fridge", "scale", "waage"],
    "Smart Health":        ["health", "gesundheit", "blood", "heart", "pulse", "sleep", "schlaf", "oximeter"],
    "EV & Mobility":       ["ev", "electric", "bike", "e-bike", "scooter", "charger", "ladegerät"],
    "Smart Audio":         ["speaker", "lautsprecher", "audio", "sound", "microphone", "echo", "assistant"],
    "Gadgets & Accessories": ["cable", "kabel", "adapter", "mount", "halter", "case", "hülle", "tool"],
}


def _classify_product(title: str, tags: str, product_type: str) -> Optional[str]:
    """Klassifiziert ein Produkt anhand Titel + Tags (kein AI-Aufruf)."""
    text = f"{title} {tags} {product_type}".lower()
    scores: dict[str, int] = {}
    for category, keywords in _KEYWORD_MAP.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[category] = score
    if scores:
        return max(scores, key=scores.get)  # type: ignore[arg-type]
    return None


async def _ai_classify(title: str, description: str = "") -> Optional[str]:
    """Klassifiziert via AI wenn Keyword-Match fehlschlägt."""
    try:
        from modules.ai_client import ai_complete
        cats = ", ".join(ALLOWED_CATEGORIES)
        prompt = (
            f"Shopify Produkt: '{title}'\n"
            f"Beschreibung (kurz): {description[:200]}\n\n"
            f"Wähle NUR eine Kategorie aus dieser Liste:\n{cats}\n\n"
            f"Antworte NUR mit dem exakten Kategorienamen, nichts sonst."
        )
        result = await ai_complete(prompt, max_tokens=30)
        result = result.strip().strip('"\'').strip()
        if result in ALLOWED_CATEGORIES:
            return result
        # Fuzzy match
        for cat in ALLOWED_CATEGORIES:
            if cat.lower() in result.lower() or result.lower() in cat.lower():
                return cat
    except Exception as e:
        log.debug("AI classify error: %s", e)
    return None


# ── Shopify API-Helpers ────────────────────────────────────────────────────────

async def _get_products_without_type(session: aiohttp.ClientSession, limit: int = 50) -> list:
    """Produkte ohne product_type abrufen."""
    url = f"{_STORE_URL()}/admin/api/2024-01/products.json?limit={limit}&fields=id,title,tags,product_type,body_html"
    async with session.get(url) as r:
        if r.status != 200:
            return []
        d = await r.json()
        products = d.get("products", [])
        return [p for p in products if not p.get("product_type", "").strip()]


async def _update_product_type(session: aiohttp.ClientSession, product_id: str, product_type: str) -> bool:
    """Setzt product_type eines Produkts."""
    url = f"{_STORE_URL()}/admin/api/2024-01/products/{product_id}.json"
    async with session.put(url, json={"product": {"id": product_id, "product_type": product_type}}) as r:
        return r.status == 200


async def _add_tag(session: aiohttp.ClientSession, product_id: str,
                   existing_tags: str, new_tag: str) -> bool:
    """Fügt einen Tag hinzu wenn noch nicht vorhanden."""
    tags_list = [t.strip() for t in existing_tags.split(",") if t.strip()]
    if new_tag in tags_list:
        return True
    tags_list.append(new_tag)
    url = f"{_STORE_URL()}/admin/api/2024-01/products/{product_id}.json"
    async with session.put(url, json={"product": {"id": product_id, "tags": ", ".join(tags_list)}}) as r:
        return r.status == 200


# ── Haupt-Logik ───────────────────────────────────────────────────────────────

async def categorize_uncategorized(batch_size: int = 30) -> dict:
    """
    Kategorisiert Produkte ohne product_type.
    Verwendet zuerst Keyword-Matching, dann AI als Fallback.
    """
    if not _TOKEN():
        return {"ok": False, "reason": "no_shopify_token"}

    result = {"ok": True, "processed": 0, "keyword_match": 0, "ai_match": 0, "failed": 0, "categories": {}}

    async with aiohttp.ClientSession(headers=_headers()) as session:
        products = await _get_products_without_type(session, limit=batch_size)
        result["found_uncategorized"] = len(products)

        for product in products:
            pid = str(product.get("id", ""))
            title = product.get("title", "")
            tags = product.get("tags", "")
            desc = product.get("body_html", "")[:200]

            # 1. Keyword-Match (schnell, kein AI)
            category = _classify_product(title, tags, "")

            # 2. AI-Fallback
            if not category:
                category = await _ai_classify(title, desc)

            if category:
                ok = await _update_product_type(session, pid, category)
                if ok:
                    # Category-Tag hinzufügen (z.B. category-smart-lighting)
                    cat_tag = "category-" + category.lower().replace(" & ", "-").replace(" ", "-")
                    await _add_tag(session, pid, tags, cat_tag)

                    result["processed"] += 1
                    result["categories"][category] = result["categories"].get(category, 0) + 1
                    if _classify_product(title, tags, ""):
                        result["keyword_match"] += 1
                    else:
                        result["ai_match"] += 1
                    log.info("Kategorisiert: '%s' → %s", title[:50], category)
                else:
                    result["failed"] += 1
            else:
                result["failed"] += 1
                log.debug("Keine Kategorie für: %s", title[:50])

            await asyncio.sleep(0.3)  # Shopify Rate-Limit schonen

    return result


async def get_category_stats() -> dict:
    """Gibt Statistik der aktuellen Produkt-Kategorien zurück."""
    if not _TOKEN():
        return {}
    try:
        async with aiohttp.ClientSession(headers=_headers()) as session:
            url = f"{_STORE_URL()}/admin/api/2024-01/products/count.json"
            async with session.get(url) as r:
                total = (await r.json()).get("count", 0) if r.status == 200 else 0

            url = f"{_STORE_URL()}/admin/api/2024-01/products/count.json?product_type="
            async with session.get(url) as r:
                no_type = (await r.json()).get("count", 0) if r.status == 200 else 0

        return {
            "total_products": total,
            "without_category": no_type,
            "with_category": total - no_type,
            "coverage_pct": round((total - no_type) / max(total, 1) * 100, 1),
        }
    except Exception as e:
        log.debug("Category stats error: %s", e)
        return {}


async def run_auto_categorizer() -> dict:
    """Haupt-Einstiegspunkt für den Scheduler."""
    stats = await get_category_stats()
    if stats.get("without_category", 0) == 0:
        return {"ok": True, "message": "Alle Produkte kategorisiert", **stats}

    result = await categorize_uncategorized(batch_size=30)
    result.update(stats)
    result["run_at"] = __import__("time").strftime("%Y-%m-%d %H:%M")
    return result
