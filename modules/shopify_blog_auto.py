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

log = logging.getLogger("ShopifyBlogAuto")

SHOP_DOMAIN   = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOKEN    = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
API_VERSION   = os.getenv("SHOPIFY_API_VERSION", "2026-04")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_KEY    = os.getenv("GEMINI_API_KEY", "")

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

    if ANTHROPIC_KEY:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                             "Content-Type": "application/json"},
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 900,
                        "messages": [{"role": "user", "content":
                            f"Schreibe einen deutschen SEO-Blogartikel (600 Wörter) über '{keyword}'. "
                            f"Format: HTML mit h2/h3/p/ul Tags. Keine Markdown-Syntax. "
                            f"Natürlicher Ton, praktische Tipps, am Ende ein CTA zu {STORE_URL}. "
                            f"Nur HTML-Body-Inhalt, kein head/body-Tag."
                        }]
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        body = data["content"][0]["text"].strip()
                        return {"title": title, "body_html": body, "tags": keyword, "slug": slug}
        except Exception as e:
            log.warning("Claude API Fehler: %s", e)

    if GEMINI_KEY:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}",
                    json={"contents": [{"parts": [{"text":
                        f"Schreibe einen deutschen SEO-Blogartikel (600 Wörter) über '{keyword}'. "
                        f"Format: HTML mit h2/h3/p/ul Tags. Keine Markdown-Syntax. "
                        f"Natürlicher Ton, praktische Tipps, am Ende CTA zu {STORE_URL}. "
                        f"Nur HTML-Body-Inhalt."
                    }]}]},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        body = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        return {"title": title, "body_html": body, "tags": keyword, "slug": slug}
        except Exception as e:
            log.warning("Gemini API Fehler: %s", e)

    # Fallback template
    body = f"""<h2>{keyword} — Was du wissen musst</h2>
<p>T-Shirts sind mehr als nur Kleidung — sie sind ein Statement. In diesem Artikel zeigen wir dir alles über <strong>{keyword}</strong> und wie du das perfekte Stück für dich oder als Geschenk findest.</p>
<h2>Warum ist das Thema {keyword.split()[0]} T-Shirt so beliebt?</h2>
<p>Individuell gestaltete T-Shirts liegen voll im Trend. Sie ermöglichen es, Persönlichkeit auszudrücken, ohne ein Wort sagen zu müssen. Besonders personalisierte Designs mit Sprüchen oder Motiven kommen super an.</p>
<h2>So findest du das richtige T-Shirt</h2>
<ul>
<li>Achte auf hochwertige Baumwolle (mindestens 180g/m²)</li>
<li>Wähle einen Spruch der wirklich zu dir oder der beschenkten Person passt</li>
<li>Größentabelle beachten — Schnitte variieren stark</li>
<li>Waschbeständigkeit des Drucks prüfen</li>
</ul>
<h2>Jetzt stöbern</h2>
<p>Schau dir unsere riesige Auswahl an — von motivierenden Sprüchen bis hin zu witzigen Designs ist für jeden Geschmack etwas dabei.</p>
<p><a href="{STORE_URL}" target="_blank" rel="noopener"><strong>→ Jetzt T-Shirts entdecken bei I Need It!</strong></a></p>"""

    return {"title": title, "body_html": body, "tags": keyword, "slug": slug}


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
