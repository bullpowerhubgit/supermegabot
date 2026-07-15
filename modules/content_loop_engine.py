"""
Content Loop Engine — Vollautonomer kostenloser Traffic-Kanal
=============================================================
1 SEO-Artikel generieren (Smart Home / Gadgets Nische)
→ Shopify Blog publizieren
→ IndexNow (Google/Bing Schnell-Indexierung)
→ Telegram + LinkedIn + Dev.to verteilen

Läuft alle 8h = ~90 Artikel/Monat = wachsender Gratis-Traffic
"""

import asyncio
import aiohttp
import logging
import os
import json
import random
import re
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ContentLoopEngine")

SHOP_DOMAIN    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOKEN     = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
API_VER        = os.getenv("SHOPIFY_API_VERSION", "2026-04")
TG_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT        = os.getenv("TELEGRAM_CHAT_ID", "")
LINKEDIN_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_URN   = os.getenv("LINKEDIN_PERSON_URN", "")
DEVTO_KEY      = os.getenv("DEVTO_API_KEY", "")

STORE_URL   = f"https://{SHOP_DOMAIN}" if SHOP_DOMAIN else "https://ineedit.com.co"
INDEXNOW_KEY = "smarthome2026indexnow"   # frei wählbar, muss im Shop als Datei liegen (optional)

STATE_FILE = Path(__file__).parent.parent / "data" / "content_loop_published.json"

# 80 Smart Home / Gadgets Keywords — passend zu den 13.404 Produkten
SMART_HOME_TOPICS = [
    "Beste Smart Home Gadgets 2026 — Vergleich und Tipps",
    "Solar Powerstation Test — welche lohnt sich wirklich",
    "Smarte Steckdosen im Test — Energie sparen leicht gemacht",
    "Balkonkraftwerk kaufen — Alles was du wissen musst",
    "WiFi Überwachungskamera außen — die besten Modelle",
    "Smart Home Starter Set — für Einsteiger erklärt",
    "Portable Powerstation für Camping — Vergleich 2026",
    "Smarte LED Strips — Wohnzimmer perfekt beleuchten",
    "Solar Generator Off-Grid — selbst Strom erzeugen",
    "Smart Thermostat sparen — Heizkosten senken automatisch",
    "Roboterstaubsauger Test 2026 — die besten unter 300 Euro",
    "Smarte Türklingel mit Kamera — Video-Türsprechanlage",
    "Air Purifier Luftreiniger Smart — saubere Luft zuhause",
    "Smart Watch Gesundheit — welche Features wirklich nützen",
    "E-Bike Kaufberatung 2026 — worauf du achten musst",
    "Smart Speaker Vergleich — Echo, Google, Apple im Test",
    "Smarter Kühlschrank lohnt sich das — ehrlicher Test",
    "Powercenter Solarspeicher für zu Hause — Ratgeber",
    "Smarte Lichtschalter nachrüsten — ohne Elektriker",
    "WiFi Mesh System — ganzes Haus mit Internet versorgen",
    "Smart Lock Türschloss Test — sicher und bequem",
    "Wärmepumpe Smart Home Integration — so geht's",
    "Smart Garden Bewässerung automatisch — Tipps 2026",
    "4K Dashcam Test — beste Modelle für dein Auto",
    "Tragbare Klimaanlage Smart — für Büro und Schlafzimmer",
    "Smarte Waage Körperanalyse — die besten Modelle",
    "Smart Home Zentrale einrichten — Alexa vs Google vs Apple",
    "Kabelloser Lautsprecher wasserdicht Test 2026",
    "Solar Ladegerät Powerbank — unterwegs nie mehr leer",
    "Smarte Jalousien nachrüsten — Sonnenschutz automatisch",
    "Induktionsladegerät Multi — alle Geräte gleichzeitig laden",
    "Smart Home Sicherheit — Alarmanlagen im Vergleich",
    "Projektor Mini Smart — Heimkino für kleines Budget",
    "Smarter Saugroboter mit Wischfunktion Test 2026",
    "Powerstation 1000W Test — für Notfall und Camping",
    "Smarte Steckdosenleiste mit Energiemessung",
    "Noise Cancelling Kopfhörer Test — die besten 2026",
    "Home Office Gadgets — produktiver arbeiten von zuhause",
    "Smart TV nachrüsten mit Fire TV oder Chromecast",
    "Überwachungskamera innen — Baby und Haustier im Blick",
    "Smarte Alarmanlage ohne Abo — einmalig kaufen",
    "Solarpanel 400W kaufen — was steckt dahinter",
    "Smart Home mit Alexa einrichten — Schritt für Schritt",
    "Fitness Tracker Test 2026 — Schrittzähler und mehr",
    "Smart Plug mit Energiemessung — Stromfresser finden",
    "Automatische Bewässerung Garten — Smarte Systeme Test",
    "Elektrischer Luftentfeuchter Smart — Schimmel vermeiden",
    "Smart Radiator Heizungsthermostat — Energie sparen",
    "Videokonferenz Webcam 4K Test — für Home Office",
    "Smarte Steckdosen Outdoor — wasserdicht und timer",
    "Bluetooth Tracker Geldbörse Schlüssel — AirTag Alternative",
    "Smart Home auf Mieterwohnung — was geht ohne Umbau",
    "Powerstation 500Wh im Test — reicht das für Camping",
    "Smarte Badezimmer Gadgets — Duschkopf bis Spiegel",
    "NAS Heimserver einrichten — eigene Cloud zuhause",
    "Gaming Stuhl Ergonomie Smart 2026 — Testbericht",
    "Smarter Küchenwecker mit Display — das beste Modell",
    "Hochdruckreiniger Smart — Terrasse und Auto reinigen",
    "Smart Home Energie Dashboard — Verbrauch im Blick",
    "LED Panel Smart Arbeitslicht — perfektes Heimstudio",
    "Wetterstationen Smart — Innen und Außen überwachen",
    "Solar Balkonkraftwerk Erfahrungen — lohnt es sich 2026",
    "Smarte Mülltonnen Erinnerung — Gadget oder Gimmick",
    "Sprachassistent Auto nachrüsten — CarPlay Android Auto",
    "Smart Home Protokolle erklärt — Zigbee Matter Thread",
    "Smarte Aquarium Steuerung — Automatisch Licht Pumpe Heizung",
    "Elektroauto Ladekabel Wallbox — Ratgeber 2026",
    "Smarte Whiteboards digitaler Stift — kreativ und produktiv",
    "Drohne kaufen — beste Modelle unter 500 Euro 2026",
    "Smart Baby Monitor Test — mehr als ein Babyphone",
    "Kabellose Sicherheitskamera Akku — ohne WLAN Pflicht",
    "Powerstation Solaranlage Bundle — alles aus einer Hand",
    "Smarte Küche Gadgets — Thermomix Alternative günstig",
    "Smart Home Einbruchschutz — die besten Systeme",
    "4K Action Kamera Test — GoPro Alternative 2026",
    "Smarte Wäschetrockner Wäscherei — Energie optimieren",
    "E-Roller E-Scooter kaufen — rechtlich und technisch erklärt",
    "Heizstrahler Smart — Terrasse effizient heizen",
    "Smarte Kühlbox Auto 12V — für Urlaub und Camping",
    "Smart Home Rollläden Motor — automatisch steuern",
]


def _load_published() -> set:
    try:
        return set(json.loads(STATE_FILE.read_text()))
    except Exception:
        return set()


def _save_published(items: set) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(list(items)))


def _html_to_plain(html: str) -> str:
    """Strip HTML for plain-text previews."""
    return re.sub(r"<[^>]+>", " ", html).strip()[:500]


async def _get_or_create_blog(session: aiohttp.ClientSession) -> str | None:
    base = f"https://{SHOP_DOMAIN}/admin/api/{API_VER}"
    hdrs = {"X-Shopify-Access-Token": SHOP_TOKEN, "Content-Type": "application/json"}

    async with session.get(f"{base}/blogs.json", headers=hdrs,
                           timeout=aiohttp.ClientTimeout(total=15)) as r:
        if r.status == 200:
            blogs = (await r.json()).get("blogs", [])
            if blogs:
                return str(blogs[0]["id"])

    async with session.post(f"{base}/blogs.json", headers=hdrs,
                            json={"blog": {"title": "Smart Home & Gadgets Blog", "commentable": "no"}},
                            timeout=aiohttp.ClientTimeout(total=15)) as r:
        if r.status == 201:
            return str((await r.json())["blog"]["id"])
    return None


async def _generate_article(session: aiohttp.ClientSession, topic: str) -> dict | None:
    """AI-generierter SEO-Artikel (Smart Home Nische, Deutsch, HTML)."""
    from modules.ai_client import ai_complete

    prompt = (
        f"Schreibe einen professionellen deutschen SEO-Blogartikel über: '{topic}'\n\n"
        f"Anforderungen:\n"
        f"- 700-900 Wörter\n"
        f"- HTML-Format (h2, h3, p, ul, strong — kein Markdown)\n"
        f"- Keyword '{topic}' natürlich 3-4× einbauen\n"
        f"- Praktische Kauftipps und ehrliche Einschätzungen\n"
        f"- Am Ende CTA: 'Alle Produkte findest du in unserem Shop unter {STORE_URL}'\n"
        f"- Kein <html>/<head>/<body> Wrapper — nur Body-Inhalt\n"
        f"- Keine Fake-Bewertungen, keine erfundenen Modellnamen"
    )

    body = await ai_complete(prompt, max_tokens=1200)
    if body:
        title = f"{topic} — Ratgeber {datetime.now().year}"
        tags = "Smart Home,Gadgets,Technik,Ratgeber"
        return {"title": title, "body_html": body.strip(), "tags": tags}
    log.error("AI-Artikel-Generierung fehlgeschlagen")
    return None


async def _publish_shopify(session: aiohttp.ClientSession,
                           blog_id: str, article: dict) -> dict | None:
    """Artikel auf Shopify Blog veröffentlichen."""
    url = f"https://{SHOP_DOMAIN}/admin/api/{API_VER}/blogs/{blog_id}/articles.json"
    hdrs = {"X-Shopify-Access-Token": SHOP_TOKEN, "Content-Type": "application/json"}
    payload = {
        "article": {
            "title": article["title"],
            "body_html": article["body_html"],
            "tags": article["tags"],
            "published": True,
            "metafields": [{
                "key": "description_tag",
                "value": _html_to_plain(article["body_html"])[:160],
                "type": "single_line_text_field",
                "namespace": "global"
            }]
        }
    }
    async with session.post(url, headers=hdrs, json=payload,
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
        if r.status == 201:
            data = (await r.json()).get("article", {})
            handle = data.get("handle", "")
            return {
                "id": data.get("id"),
                "url": f"{STORE_URL}/blogs/news/{handle}",
                "handle": handle
            }
        err = await r.text()
        log.error("Shopify Blog Fehler %s: %s", r.status, err[:200])
    return None


async def _submit_indexnow(session: aiohttp.ClientSession, article_url: str) -> bool:
    """IndexNow — Google/Bing indexieren den Artikel innerhalb von Stunden."""
    host = SHOP_DOMAIN.split("/")[0] if SHOP_DOMAIN else ""
    payload = {
        "host": host,
        "key": INDEXNOW_KEY,
        "urlList": [article_url]
    }
    for endpoint in [
        "https://api.indexnow.org/indexnow",
        "https://www.bing.com/indexnow",
    ]:
        try:
            async with session.post(endpoint, json=payload,
                                    timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status in (200, 202):
                    log.info("IndexNow %s: %s → %s", endpoint.split("/")[2], r.status, article_url)
        except Exception as e:
            log.debug("IndexNow %s Fehler: %s", endpoint, e)
    return True


async def _post_telegram(session: aiohttp.ClientSession,
                          title: str, article_url: str) -> bool:
    """Artikel-Ankündigung auf Telegram — via Post Gateway."""
    text = (
        f"📱 <b>Neuer Artikel:</b>\n"
        f"<i>{title}</i>\n\n"
        f"🔗 {article_url}\n\n"
        f"#SmartHome #Gadgets #Technik"
    )
    from modules.post_gateway import safe_post
    result = await safe_post("telegram", text, source_module="content_loop_engine")
    return result.get("ok", False)


async def _post_linkedin(session: aiohttp.ClientSession,
                          title: str, article_url: str, summary: str) -> bool:
    """Artikel als LinkedIn Post — via Post Gateway (5-Schicht-Prüfung)."""
    text = f"🔍 {title}\n\n{summary[:300]}...\n\n👉 {article_url}\n\n#SmartHome #Gadgets #Technologie"
    from modules.post_gateway import safe_post
    result = await safe_post("linkedin", text, source_module="content_loop_engine")
    return result.get("ok", False)


async def _post_devto(session: aiohttp.ClientSession,
                       title: str, body_html: str, topic: str) -> str | None:
    """Artikel auf Dev.to publizieren (kostenloser zusätzlicher Kanal)."""
    if not DEVTO_KEY:
        return None
    clean = _html_to_plain(body_html)
    payload = {
        "article": {
            "title": title,
            "body_markdown": clean[:5000],
            "tags": ["smarthome", "gadgets", "technik"],
            "published": True,
            "description": clean[:160],
        }
    }
    async with session.post(
        "https://dev.to/api/articles",
        headers={"api-key": DEVTO_KEY, "Content-Type": "application/json"},
        json=payload,
        timeout=aiohttp.ClientTimeout(total=20)
    ) as r:
        if r.status == 201:
            data = await r.json()
            url = data.get("url", "")
            log.info("Dev.to: Artikel publiziert → %s", url)
            return url
    return None


async def run_content_loop() -> dict:
    """
    Hauptfunktion: 1 SEO-Artikel generieren und auf alle Kanäle verteilen.
    Aufruf: alle 8h via Scheduler = ~90 Artikel/Monat.
    """
    if os.getenv("SOCIAL_POSTING_PAUSED", "").lower() in ("1", "true", "yes"):
        log.info("ContentLoopEngine pausiert (SOCIAL_POSTING_PAUSED gesetzt)")
        return {"topic": "", "shopify_url": None, "channels": [], "errors": ["posting_paused"], "ok": False}

    result = {
        "topic": "",
        "shopify_url": None,
        "channels": [],
        "errors": [],
        "ok": False
    }

    if not SHOP_DOMAIN or not SHOP_TOKEN:
        result["errors"].append("Shopify Credentials fehlen")
        return result

    # Thema wählen (noch nicht veröffentlicht)
    published = _load_published()
    remaining = [t for t in SMART_HOME_TOPICS if t not in published]
    if not remaining:
        published = set()
        remaining = list(SMART_HOME_TOPICS)

    topic = remaining[0]
    result["topic"] = topic
    log.info("Content Loop startet: %s", topic)

    async with aiohttp.ClientSession() as session:

        # 1. Blog holen/erstellen
        blog_id = await _get_or_create_blog(session)
        if not blog_id:
            result["errors"].append("Shopify Blog nicht erreichbar (write_content Scope?)")
            return result

        # 2. Artikel generieren
        article = await _generate_article(session, topic)
        if not article:
            result["errors"].append("Artikel-Generierung fehlgeschlagen (Anthropic?)")
            return result

        # 3. Auf Shopify publizieren
        published_art = await _publish_shopify(session, blog_id, article)
        if not published_art:
            result["errors"].append("Shopify-Veröffentlichung fehlgeschlagen")
            return result

        article_url = published_art["url"]
        result["shopify_url"] = article_url
        result["channels"].append("shopify_blog")
        log.info("Shopify Blog: %s", article_url)

        # Thema als veröffentlicht markieren
        published.add(topic)
        _save_published(published)

        # 4. IndexNow — Google & Bing informieren
        await _submit_indexnow(session, article_url)
        result["channels"].append("indexnow_google_bing")

        # 5. Telegram
        summary = _html_to_plain(article["body_html"])
        tg_ok = await _post_telegram(session, article["title"], article_url)
        if tg_ok:
            result["channels"].append("telegram")

        # 6. LinkedIn
        li_ok = await _post_linkedin(session, article["title"], article_url, summary)
        if li_ok:
            result["channels"].append("linkedin")

        # 7. Dev.to
        devto_url = await _post_devto(session, article["title"], article["body_html"], topic)
        if devto_url:
            result["channels"].append("devto")

    result["ok"] = True
    active = ", ".join(result["channels"])
    log.info("Content Loop fertig — Kanäle: %s", active)
    return result
