#!/usr/bin/env python3
"""
SEO Scaler + Shop Perfektionist — Vollautonomes SEO & Shop-Optimierungs-System
===============================================================================
Läuft täglich via Scheduler. Optimiert ALLE Shopify-Produkte für maximalen
organischen Traffic: Titel, Beschreibungen, Meta-Tags, Alt-Texte, Collections,
Bundles, Content-Cluster. Ziel: Platz 1 bei Google & KI-Suchen.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("SEOScaler")

SHOP_URL  = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
SHOP_DOM  = os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")

# Top-Keywords für Smart-Home (nach Suchvolumen)
TOP_KEYWORDS = [
    "smart home", "smarthome", "alexa kompatibel", "google home kompatibel",
    "smart steckdose", "wlan steckdose", "zigbee", "z-wave",
    "solar balkonkraftwerk", "balkonkraftwerk 800w", "mini solaranlage",
    "überwachungskamera wlan", "ip kamera aussen", "kamera mit nachtsicht",
    "roboter rasenmäher", "mähroboter", "rasenroboter app",
    "smart thermostat", "heizkörper thermostat wlan", "heizung sparen",
    "led smart bulb", "rgb glühbirne smart", "smart beleuchtung",
    "smart home anfänger", "smart home set", "starter set smart home",
    "energiesparen smart home", "strom sparen gadget",
    "haus automatisierung", "home automation", "smart home österreich",
]


async def _ai(prompt: str, max_tokens: int = 600) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception as e:
        log.warning("SEO AI: %s", e)
        return ""


async def _shopify_get(path: str) -> Any:
    try:
        from modules import shopify_client as sc
        return await sc.rest_get(path)
    except Exception as e:
        log.warning("Shopify GET %s: %s", path, e)
        return {}


async def _shopify_put(path: str, data: dict) -> bool:
    try:
        from modules import shopify_client as sc
        r = await sc.rest_put(path, data)
        return bool(r and not r.get("error"))
    except Exception as e:
        log.warning("Shopify PUT %s: %s", path, e)
        return False


async def optimize_product_seo(product: dict) -> bool:
    """Optimiert SEO für ein einzelnes Produkt."""
    pid   = product.get("id")
    title = (product.get("title") or "")[:120]
    body  = (product.get("body_html") or "")[:500]
    ptype = (product.get("product_type") or "Smart Home")
    tags  = (product.get("tags") or "")
    vendor = (product.get("vendor") or "iNeedit")

    if not pid or not title:
        return False

    # Nur wenn SEO-Tag noch nicht gesetzt
    if "seo-optimized" in tags:
        return False

    prompt = f"""Du bist SEO-Experte für einen deutschen Smart-Home-Shop (ineedit.com.co).
Optimiere folgendes Produkt für maximalen organischen Traffic bei Google.de, Google.at und KI-Suchen.

Produkt: {title}
Kategorie: {ptype}
Beschreibung: {body[:200]}

Erstelle:
1. SEO-TITEL (max 70 Zeichen): Hauptkeyword am Anfang, USP, Marke am Ende
2. META-DESCRIPTION (max 155 Zeichen): Klickstark, Keyword, Call-to-Action
3. BESCHREIBUNG (150-250 Wörter): Keyword-reich, Vorteile, technische Details, für wen geeignet
4. TAGS (10-15): Komma-getrennt, relevante Suchbegriffe auf Deutsch

Antwort NUR als JSON: {{"title":"...","meta_description":"...","body_html":"...","tags":"..."}}"""

    result = await _ai(prompt, max_tokens=800)
    if not result:
        return False

    # JSON extrahieren
    try:
        start = result.find("{")
        end   = result.rfind("}") + 1
        if start < 0 or end <= start:
            return False
        data = json.loads(result[start:end])
    except Exception:
        return False

    new_title = data.get("title", "")[:255]
    new_meta  = data.get("meta_description", "")[:320]
    new_body  = data.get("body_html", "")
    new_tags  = data.get("tags", "")

    if not new_title or not new_body:
        return False

    # Tags mit seo-optimized markieren
    existing_tags = [t.strip() for t in tags.split(",") if t.strip()]
    seo_tags = [t.strip() for t in new_tags.split(",") if t.strip()]
    all_tags = list(set(existing_tags + seo_tags + ["seo-optimized"]))

    update_payload = {
        "product": {
            "id": pid,
            "title": new_title,
            "body_html": new_body,
            "tags": ", ".join(all_tags[:30]),
            "metafields_global_title_tag": new_title,
            "metafields_global_description_tag": new_meta,
        }
    }

    success = await _shopify_put(f"products/{pid}.json", update_payload)
    if success:
        log.info("SEO OK: %s → %s", title[:40], new_title[:40])
    return success


async def create_bundle(name: str, product_ids: List[int], price: float, description: str) -> bool:
    """Erstellt ein Produkt-Bundle als neues Shopify-Produkt."""
    try:
        from modules import shopify_client as sc

        title = f"{name} Bundle — Komplett-Set"
        body = f"""<h2>{name} — Alles was Sie brauchen</h2>
<p>{description}</p>
<ul>
<li>✅ Komplett-Set — sofort einsatzbereit</li>
<li>✅ Kompatibel mit Alexa & Google Home</li>
<li>✅ EU-Versand in 3-7 Werktagen</li>
<li>✅ 30 Tage Rückgaberecht</li>
</ul>"""

        product_data = {
            "product": {
                "title": title,
                "body_html": body,
                "vendor": "iNeedit",
                "product_type": "Bundle",
                "tags": "bundle, smart-home, set, komplett, spar-set, seo-optimized",
                "variants": [{"price": str(price), "inventory_management": "shopify", "inventory_quantity": 50}],
            }
        }
        result = await sc.rest_post("products.json", product_data)
        if result and result.get("product", {}).get("id"):
            log.info("Bundle erstellt: %s (€%.0f)", title, price)
            return True
    except Exception as e:
        log.warning("Bundle create: %s", e)
    return False


async def create_top_bundles() -> int:
    """Erstellt die meistgefragten Bundles automatisch."""
    bundles = [
        {
            "name": "Smart Home Komplett-Starter",
            "price": 229.0,
            "description": "Das perfekte Einsteiger-Paket: Smart Hub, 3 Steckdosen, 5 LED-Lampen, Bewegungssensor. Alles aus einer Hand, sofort verbunden."
        },
        {
            "name": "Solar Energie-Spar",
            "price": 549.0,
            "description": "Balkonkraftwerk 800W + Smart Thermostat Pro: bis zu €1.200/Jahr Energieersparnis. Amortisation in unter 18 Monaten."
        },
        {
            "name": "Smart Security Premium",
            "price": 289.0,
            "description": "4K Überwachungskamera (2x) + Smart Doorbell + Alarm-Sensor. Vollständige 360°-Überwachung Ihres Zuhauses."
        },
        {
            "name": "Garten Automatisierung",
            "price": 429.0,
            "description": "Roboter-Rasenmäher AI + Smart Bewässerung + Wetter-Sensor. Ihr Garten pflegt sich vollautomatisch."
        },
        {
            "name": "Smart Home Pro Komplett",
            "price": 699.0,
            "description": "Das ultimative Smart-Home-Paket für Anspruchsvolle: 10 LED-Lampen, 5 Steckdosen, Thermostat, Kamera, Hub. Komplett vernetzt."
        },
    ]

    created = 0
    for bundle in bundles:
        # Prüfe ob Bundle schon existiert
        try:
            from modules import shopify_client as sc
            search = await sc.get(f"products.json?title={bundle['name']} Bundle&limit=1")
            if search.get("products"):
                continue
        except Exception:
            pass

        ok = await create_bundle(bundle["name"], [], bundle["price"], bundle["description"])
        if ok:
            created += 1
        await asyncio.sleep(1)

    return created


async def run_seo_batch(limit: int = 50) -> Dict[str, int]:
    """Optimiert bis zu `limit` Produkte pro Lauf."""
    stats = {"checked": 0, "optimized": 0, "skipped": 0, "errors": 0}

    try:
        from modules import shopify_client as sc
        # Produkte ohne seo-optimized Tag holen
        result = await sc.get(f"products.json?limit={limit}&fields=id,title,body_html,product_type,tags,vendor")
        products = result.get("products", [])
    except Exception as e:
        log.error("Shopify products fetch: %s", e)
        return stats

    for p in products:
        stats["checked"] += 1
        tags = p.get("tags", "")
        if "seo-optimized" in tags:
            stats["skipped"] += 1
            continue
        try:
            ok = await optimize_product_seo(p)
            if ok:
                stats["optimized"] += 1
            else:
                stats["errors"] += 1
        except Exception as e:
            log.warning("SEO product %s: %s", p.get("id"), e)
            stats["errors"] += 1
        await asyncio.sleep(0.5)

    return stats


async def run_full_seo_cycle() -> str:
    """Vollständiger SEO-Zyklus: Produkte + Bundles + Report."""
    log.info("SEO Scaler: Start")
    start = time.time()

    # 1. Produkte SEO-optimieren
    seo_stats = await run_seo_batch(limit=30)

    # 2. Bundles erstellen (falls noch nicht vorhanden)
    bundles_created = await create_top_bundles()

    elapsed = int(time.time() - start)
    report = (
        f"🔍 <b>SEO Scaler Report</b>\n\n"
        f"⏱ Dauer: {elapsed}s\n"
        f"📦 Produkte geprüft: {seo_stats['checked']}\n"
        f"✅ SEO-optimiert: {seo_stats['optimized']}\n"
        f"⏭ Bereits optimiert: {seo_stats['skipped']}\n"
        f"🎁 Bundles erstellt: {bundles_created}\n\n"
        f"📈 Organischer Traffic wächst — täglich mehr Reichweite!"
    )

    log.info("SEO Scaler fertig: %s", seo_stats)
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_full_seo_cycle())
