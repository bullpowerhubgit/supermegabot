"""
Shopify Blog Auto-Publisher
============================
Erstellt automatisch einen Blog (falls nicht vorhanden) und publiziert
SEO-Artikel für den ineedit.com.co Smart Home & Gadgets-Shop.
Themen: Smart Home, AI-Gadgets, Solar, E-Mobilität, moderne Technologie.
"""
import os
import json
import logging
import asyncio
import random
from datetime import datetime
from pathlib import Path

import aiohttp
from modules.ai_client import ai_complete

log = logging.getLogger("ShopifyBlogAuto")

SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOKEN  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")

DATA_DIR   = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
STATE_FILE = DATA_DIR / "shopify_blog_published.json"

STORE_URL = "https://ineedit.com.co"

BLOG_TOPICS = [
    "Smart Home Geräte 2026 — die besten Gadgets im Vergleich",
    "Balkonkraftwerk kaufen — Komplettset Solar mit Speicher",
    "Smart Plug WLAN Steckdose — Energie sparen mit App-Steuerung",
    "AI-Gadgets Haushalt 2026 — intelligente Helfer im Test",
    "Robot Staubsauger kaufen — Vergleich Saugroboter 2026",
    "Smarte Glühbirnen & LED-Strips — Alexa und Google Home kompatibel",
    "Powerstation Solar kaufen — Off-Grid Energieversorgung 2026",
    "Smart Lock Türschloss kaufen — Keyless Entry im Test",
    "Smartwatch kaufen 2026 — Fitness Tracker im Vergleich",
    "E-Bike kaufen 2026 — bestes Pedelec unter 2000 Euro",
    "Solar Gartenbeleuchtung kaufen — kabellos & wartungsfrei",
    "Smart Thermostat kaufen — Heizkosten sparen mit KI",
    "Überwachungskamera WLAN kaufen — Smart Home Sicherheit",
    "Gaming Headset kaufen 2026 — bestes kabelloses Headset",
    "Wireless Earbuds kaufen — ANC Kopfhörer im Vergleich",
    "4K Beamer kaufen Heimkino — beste Projektoren 2026",
    "E-Scooter kaufen 2026 — straßenzugelassen & langlebig",
    "Portable Solar Panel kaufen — Powerbank Solar Test",
    "Smart Speaker kaufen — Alexa Echo vs Google Nest 2026",
    "Dashcam kaufen 2026 — beste Auto-Kamera im Test",
    "Drohne kaufen 2026 — beste Kameradrohne für Einsteiger",
    "3D-Drucker kaufen 2026 — bester Einsteiger-Drucker",
    "Smart Home Zentrale kaufen — Hub für alle Geräte",
    "Luftreiniger kaufen 2026 — bester HEPA-Filter Test",
    "Induktionsladegerät kaufen — wireless charging Tipp",
    "Smart Mirror kaufen — intelligenter Spiegel mit Display",
    "Mini PC kaufen 2026 — kompakter Büro-Computer Test",
    "VR Brille kaufen 2026 — beste Virtual Reality Headsets",
    "Fitness Tracker kaufen — Schrittzähler & Pulsuhren 2026",
    "Solar Ladegerät kaufen — bestes USB Solar-Panel Test",
    "Smart Kühlschrank kaufen — vernetzter Kühlschrank 2026",
    "Elektrische Zahnbürste kaufen — beste Schallzahnbürste",
    "Smart TV kaufen 2026 — bestes QLED oder OLED unter 1000€",
    "Heimautomation einrichten — Smart Home Anfänger-Guide",
    "E-Auto Zubehör kaufen — Wallbox & Kabel-Sets 2026",
    "KI-gestützte Geräte Haushalt — ChatGPT im Alltag nutzen",
    "Balkonkraftwerk Speicher nachrüsten — Erweiterung 2026",
    "Robot Mähroboter kaufen — bester Rasenmähroboter Test",
    "Smarte Jalousien Rolladen kaufen — App-gesteuert 2026",
    "NAS Netzwerkspeicher kaufen — bestes Heimnetzwerk 2026",
    "Gaming Chair kaufen 2026 — ergonomischer Bürostuhl Test",
    "Portable Monitor kaufen — bester USB-C Monitor 2026",
    "Smart Waage kaufen — WLAN Körperanalyse-Waage Test",
    "Küchenroboter kaufen 2026 — smarte Küchenhelfer Test",
    "Zigbee Hub kaufen — smarte Geräte ohne Cloud verbinden",
    "Solar Powerstation kaufen — Camping & Outdoor Energie",
    "Smart Bedroom Gadgets — Schlafzimmer automatisieren 2026",
    "Wärmebildkamera kaufen — Wärmepumpe & Hausdämmung prüfen",
    "Action Cam kaufen 2026 — bestes GoPro Alternative Test",
    "Bluetooth Lautsprecher kaufen — wasserdicht & outdoor 2026",
]


def _load_published() -> set:
    try:
        return set(json.loads(STATE_FILE.read_text()))
    except Exception:
        return set()


def _save_published(slugs: set) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(list(slugs)))


async def _get_or_create_blog(session: aiohttp.ClientSession) -> str | None:
    base = f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}"
    headers = {"X-Shopify-Access-Token": SHOP_TOKEN, "Content-Type": "application/json"}

    # Check existing blogs
    async with session.get(f"{base}/blogs.json", headers=headers,
                           timeout=aiohttp.ClientTimeout(total=15)) as r:
        if r.status == 200:
            blogs = (await r.json()).get("blogs", [])
            if blogs:
                return str(blogs[0]["id"])

    # Create blog
    async with session.post(f"{base}/blogs.json", headers=headers,
                            json={"blog": {"title": "Smart Home & Tech Blog", "commentable": "no"}},
                            timeout=aiohttp.ClientTimeout(total=15)) as r:
        if r.status == 201:
            blog = (await r.json()).get("blog", {})
            blog_id = str(blog.get("id", ""))
            log.info("Blog erstellt: ID=%s", blog_id)
            return blog_id
        error = await r.text()
        log.error("Blog erstellen fehlgeschlagen: %s %s", r.status, error)
        return None


async def _generate_article(keyword: str) -> dict:
    title = f"{keyword} — Tipps & Trends 2026"
    slug = keyword.lower().replace(" ", "-").replace("ä","ae").replace("ö","oe").replace("ü","ue")[:60]

    try:
        prompt = (
            f"Schreibe einen deutschen SEO-Blogartikel (600 Wörter) über '{keyword}'. "
            f"Format: HTML mit h2/h3/p/ul Tags. Keine Markdown-Syntax. "
            f"Natürlicher Ton, praktische Tipps, am Ende ein CTA zu {STORE_URL}. "
            f"Nur HTML-Body-Inhalt, kein head/body-Tag."
        )
        body = await ai_complete(prompt, max_tokens=900)
        if body:
            return {"title": title, "body_html": body.strip(), "tags": keyword, "slug": slug}
    except Exception as e:
        log.warning("ai_complete Fehler: %s", e)

    # AI-Fehler: Artikel NICHT mit falschem Nischen-Content publizieren
    log.warning("ai_complete lieferte keinen Inhalt für '%s' — Artikel wird übersprungen.", keyword)
    return None


async def publish_one_article() -> dict:
    if not SHOP_DOMAIN or not SHOP_TOKEN:
        return {"ok": False, "reason": "SHOPIFY_SHOP_DOMAIN oder SHOPIFY_ADMIN_API_TOKEN fehlt"}

    published = _load_published()
    remaining = [t for t in BLOG_TOPICS if t not in published]
    if not remaining:
        # Reset cycle
        published = set()
        remaining = list(BLOG_TOPICS)

    keyword = remaining[0]

    async with aiohttp.ClientSession() as session:
        blog_id = await _get_or_create_blog(session)
        if not blog_id:
            return {"ok": False, "reason": "Blog konnte nicht erstellt/gefunden werden — write_content Scope fehlt?"}

        article = await _generate_article(keyword)
        if article is None:
            # AI-Fehler: Thema überspringen, beim nächsten Lauf wird nächstes Thema gewählt
            published.add(keyword)
            _save_published(published)
            return {"ok": False, "reason": f"KI-Inhalt konnte nicht generiert werden für: {keyword}"}
        base = f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}"
        headers = {"X-Shopify-Access-Token": SHOP_TOKEN, "Content-Type": "application/json"}

        async with session.post(
            f"{base}/blogs/{blog_id}/articles.json",
            headers=headers,
            json={"article": {
                "title": article["title"],
                "body_html": article["body_html"],
                "tags": article["tags"],
                "published": True,
                "metafields": [
                    {"key": "description_tag", "value": f"Alles über {keyword} — Tipps, Trends und Geschenkideen 2026.", "type": "single_line_text_field", "namespace": "global"},
                ]
            }},
            timeout=aiohttp.ClientTimeout(total=20)
        ) as r:
            if r.status == 201:
                art = (await r.json()).get("article", {})
                published.add(keyword)
                _save_published(published)
                log.info("Artikel publiziert: %s (ID %s)", art.get("title"), art.get("id"))
                return {"ok": True, "title": art.get("title"), "id": art.get("id"), "keyword": keyword}
            error = await r.text()
            log.error("Artikel-Post fehlgeschlagen: %s — %s", r.status, error[:200])
            return {"ok": False, "status": r.status, "error": error[:200], "keyword": keyword}


async def check_permission() -> dict:
    """Prüft ob write_content Scope vorhanden ist."""
    if not SHOP_DOMAIN or not SHOP_TOKEN:
        return {"ok": False, "reason": "Kein Token konfiguriert"}
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}/blogs.json",
            headers={"X-Shopify-Access-Token": SHOP_TOKEN, "Content-Type": "application/json"},
            json={"blog": {"title": "_permission_test_"}},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status == 201:
                # Delete test blog immediately
                blog_id = (await r.json()).get("blog", {}).get("id")
                if blog_id:
                    await s.delete(
                        f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}/blogs/{blog_id}.json",
                        headers={"X-Shopify-Access-Token": SHOP_TOKEN}
                    )
                return {"ok": True}
            text = await r.text()
            return {"ok": False, "status": r.status, "error": text[:200]}
