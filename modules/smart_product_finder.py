"""
Smart Product Finder — Vollautomatische Produktrecherche & Import-Pipeline

Funktionsweise:
1. RESEARCH: Sucht trending Smart/Tech-Produkte auf mehreren Quellen
2. QUALITY GATE: KI-Validierung — nur echte, gefragte Produkte passieren
3. DEDUP: Prüft ob Produkt schon im Shop
4. IMPORT: Erstellt Shopify-Produkt mit echten Daten (kein Fake)

Quellen:
- AliExpress: Trending + Bestseller in Smart Home / Tech
- Amazon.de: Bestseller-Listen der relevanten Kategorien
- Idealo.de: Preistrend & Beliebtheit
- Reddit r/smarthome, r/gadgets: Community-Empfehlungen
- Google Trends (via scraping): Suchvolumen-Peaks
"""
import asyncio
import logging
import os
import re
import json
import hashlib
from typing import Optional
from urllib.parse import quote_plus, urljoin

import aiohttp
from dotenv import load_dotenv
from modules.ai_client import ai_complete
from modules.product_gatekeeper import validate_product

load_dotenv()
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SHOP        = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TOKEN       = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
API_VER     = os.getenv("SHOPIFY_API_VERSION", "2024-04")
HEADERS     = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}
TIMEOUT     = aiohttp.ClientTimeout(total=30, connect=10)

# Nischen-Regeln — ALLES muss smart/modern/tech sein
ALLOWED_NICHES = [
    "Smart Home", "Solar", "Powerstation", "E-Mobility", "Saugroboter",
    "Smart Lighting", "Smart Security", "Grow Light", "3D Drucker",
    "Laser Engraver", "Drone", "Audio", "Gaming", "Wearable", "Smartwatch",
    "Home Office Tech", "Auto Tech", "Pet Tech", "Camping Tech", "Fitness Tech",
    "Werkzeug Profi", "EV Charging", "Netzwerk Tech", "Tablets", "Smartphones",
]

# Preisrahmen EK → VK (Faktor 2.2x)
MIN_EK_EUR = 8.0
MAX_EK_EUR = 300.0

# Amazon.de Bestseller-Kategorien (URL-Pfade)
AMAZON_CATEGORIES = [
    "Beleuchtung/zgbs/lighting",
    "Smart-Home/zgbs/amazon-devices",
    "Heimkino-HiFi-Fernseher/zgbs/ce-de",
    "Computer-Zubehoer/zgbs/computers",
    "Garten/zgbs/garden",
    "Sport-Freizeit/zgbs/sports",
    "Baumarkt/zgbs/diy",
    "Elektronik/zgbs/electronics",
]

# AliExpress Trending-Kategorien
ALIEXPRESS_CATEGORIES = [
    "smart home", "solar panel portable", "robot vacuum", "led strip rgb wifi",
    "powerstation portable", "grow light led", "3d printer", "smart plug wifi",
    "laser engraver", "dashcam wifi", "e-bike", "smartwatch fitness",
    "bluetooth speaker waterproof", "security camera wifi", "drone mini",
]

# Reddit-Subreddits für Trend-Signale
REDDIT_SUBS = [
    "smarthome", "gadgets", "homeautomation", "solar",
    "PrintedCircuitBoard", "3Dprinting", "ebikes",
]

# Blacklist-Keywords → sofort ablehnen
BLACKLIST = [
    "article", "news", "blog", "tutorial", "guide", "review", "forum",
    "reddit", "hackernews", "hn ", "verlag", "buch", "kochbuch", "roman",
    "windel", "babytuch", "wischtuch", "serviette", "taschentuch",
    "notizbuch", "kalender", "planner", "ringordner", "flipchart",
    "frühstücksbrett", "schneidebrett", "holzbrett", "servierbrett",
    "pfannenwender", "kochutensilien set", "besteck", "messer set",
    "bettwäsche", "kissenbezug", "handtuch", "badetuch",
    "babybadewanne", "lauflernhilfe", "trinklerntasse",
    "kugelschreiber", "stift ", "füller", "marker",
]


def _ok() -> bool:
    return bool(SHOP and TOKEN)


def _product_hash(title: str) -> str:
    return hashlib.md5(title.lower().strip().encode()).hexdigest()[:12]


def _is_blacklisted(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in BLACKLIST)


# ── Shopify: Duplikat-Check ───────────────────────────────────────────────────
async def _exists_in_shop(session: aiohttp.ClientSession, title: str) -> bool:
    """Prüft ob ein Produkt mit ähnlichem Titel schon existiert."""
    words = title.split()[:4]
    q = " ".join(words)
    url = f"https://{SHOP}/admin/api/{API_VER}/products.json"
    try:
        async with session.get(url, headers=HEADERS,
                               params={"title": q, "limit": 5, "fields": "id,title"},
                               timeout=TIMEOUT) as r:
            data = await r.json()
            products = data.get("products", [])
            t_lower = title.lower()
            for p in products:
                if t_lower in p.get("title", "").lower() or p.get("title", "").lower() in t_lower:
                    return True
    except Exception:
        pass
    return False


# ── KI-Qualitäts-Gate ────────────────────────────────────────────────────────
async def _ai_validate(candidate: dict) -> Optional[dict]:
    """
    KI bewertet das Kandidat-Produkt via ai_complete (multi-provider fallback):
    - Passt es in unsere Smart/Modern Nische?
    - Ist es ein echtes Produkt (kein Artikel/Fake)?
    - Welche Kategorie?
    - Deutschen Titel + SEO-Beschreibung generieren
    Returns None wenn abgelehnt.
    """
    title    = candidate.get("title", "")
    price    = candidate.get("price_eur", 0)
    source   = candidate.get("source", "")
    category = candidate.get("category", "")

    prompt = f"""Du bist Qualitätsprüfer für einen deutschen Smart-Tech Online Shop (Nische: Smart Home, Solar, Camping-Tech, moderne Elektronik).

Beurteilung dieses Produktkandidaten:
Titel: {title}
Kategorie: {category}
Preis (EK): {price}€
Quelle: {source}

Regeln:
- ABLEHNEN wenn: Zeitungsartikel, Blog-Post, Alltagsartikel ohne Technik (Holzbrettchen, Notizbuch, Babyzubehör), Kleidung, Lebensmittel, Bürobedarf
- ABLEHNEN wenn Preis < 5€ oder > 400€ EK
- ANNEHMEN wenn: Smart Home, Solar, Licht-Tech, Roboter, E-Mobility, Profi-Werkzeug, Camping-Tech, Audio, Gaming

Wenn ANGENOMMEN: Erstelle einen deutschen SEO-Titel (max 80 Zeichen) und eine deutsche Beschreibung (150-200 Wörter, Vorteile + Anwendung + Keywords).
Wähle die beste Kategorie aus: {', '.join(ALLOWED_NICHES)}

Antworte NUR mit diesem JSON (kein Markdown):
{{"ok": true/false, "reason": "...", "de_title": "...", "de_desc": "...", "niche": "..."}}"""

    try:
        text = await ai_complete(prompt, system="", max_tokens=600)
        if not text:
            if _is_blacklisted(title):
                return None
            return candidate
        # Strip markdown if present
        text = re.sub(r"^```json\s*|```$", "", text.strip(), flags=re.MULTILINE).strip()
        result = json.loads(text)
        if not result.get("ok"):
            log.debug("KI abgelehnt: %s — %s", title[:40], result.get("reason", ""))
            return None
        return {
            **candidate,
            "title": result.get("de_title", title),
            "description": result.get("de_desc", ""),
            "niche": result.get("niche", category),
        }
    except Exception as e:
        log.debug("KI-Validierung Fehler: %s", e)
        # Fallback: Keyword-Check
        if _is_blacklisted(title):
            return None
        return candidate


# ── Research: Amazon.de Bestseller ───────────────────────────────────────────
async def _research_amazon(session: aiohttp.ClientSession, category_path: str) -> list[dict]:
    """Scrapt Amazon.de Bestseller-Liste für eine Kategorie."""
    url = f"https://www.amazon.de/gp/bestsellers/{category_path}"
    results = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "de-DE,de;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        }
        async with session.get(url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=12)) as r:
            if r.status != 200:
                return []
            html = await r.text(errors="ignore")

        # Extrahiere Produkttitel und Preise
        titles = re.findall(r'<span[^>]*class="[^"]*p13n-sc-truncate[^"]*"[^>]*>([^<]{10,120})</span>', html)
        prices_raw = re.findall(r'<span[^>]*class="[^"]*p13n-sc-price[^"]*"[^>]*>([^<]+)</span>', html)

        prices = []
        for p in prices_raw:
            m = re.search(r'[\d]+[,.][\d]+', p.replace(".", "").replace(",", "."))
            if m:
                try:
                    prices.append(float(m.group().replace(",", ".")))
                except Exception:
                    prices.append(0.0)
            else:
                prices.append(0.0)

        cat_name = category_path.split("/")[0]
        for i, title in enumerate(titles[:20]):
            title = title.strip()
            if len(title) < 10 or _is_blacklisted(title):
                continue
            price_vk = prices[i] if i < len(prices) else 0.0
            price_ek = round(price_vk / 2.2, 2) if price_vk > 0 else 0.0
            if price_ek < MIN_EK_EUR or price_ek > MAX_EK_EUR:
                continue
            results.append({
                "title": title,
                "price_eur": price_ek,
                "price_vk": price_vk,
                "source": "amazon_bestseller",
                "category": cat_name,
            })
        log.info("Amazon %s: %d Kandidaten", cat_name, len(results))
    except Exception as e:
        log.debug("Amazon scrape Fehler (%s): %s", category_path, e)
    return results


# ── Research: AliExpress Trending ────────────────────────────────────────────
async def _research_aliexpress(session: aiohttp.ClientSession, keyword: str) -> list[dict]:
    """Scrapt AliExpress Suchergebnisse für ein Keyword."""
    url = f"https://www.aliexpress.com/wholesale?SearchText={quote_plus(keyword)}&SortType=total_tranpro_desc"
    results = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        }
        async with session.get(url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return []
            html = await r.text(errors="ignore")

        # JSON-Daten aus dem Script-Tag extrahieren
        data_matches = re.findall(r'"title"\s*:\s*"([^"]{15,120})".*?"salePrice"\s*:\s*\{[^}]*"value"\s*:\s*"([\d.]+)"', html)
        if not data_matches:
            # Fallback: direkte Titelextraktion
            titles = re.findall(r'"title":"([^"]{15,120})"', html)
            data_matches = [(t, "0") for t in titles[:15]]

        for title, price_str in data_matches[:15]:
            title = title.strip().replace("\\u0026", "&").replace("\\n", " ")
            if _is_blacklisted(title):
                continue
            try:
                price_usd = float(price_str)
                price_ek = round(price_usd * 0.92, 2)  # USD→EUR
            except Exception:
                price_ek = 0.0
            if price_ek < MIN_EK_EUR or (price_ek > MAX_EK_EUR and price_ek > 0):
                continue
            results.append({
                "title": title,
                "price_eur": price_ek,
                "price_vk": round(price_ek * 2.2, 2),
                "source": "aliexpress_trending",
                "category": keyword,
            })
        log.info("AliExpress '%s': %d Kandidaten", keyword, len(results))
    except Exception as e:
        log.debug("AliExpress scrape Fehler (%s): %s", keyword, e)
    return results


# ── Research: Reddit Trending ─────────────────────────────────────────────────
async def _research_reddit(session: aiohttp.ClientSession, sub: str) -> list[dict]:
    """Analysiert Reddit-Posts für Produkt-Mentions via JSON API."""
    url = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
    results = []
    try:
        headers = {"User-Agent": "SmartProductFinder/1.0"}
        async with session.get(url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return []
            data = await r.json()

        posts = data.get("data", {}).get("children", [])
        for post in posts:
            pd = post.get("data", {})
            title = pd.get("title", "")
            score = pd.get("score", 0)
            # Nur hochgepunktete Posts
            if score < 50 or _is_blacklisted(title):
                continue
            # Produktnamen aus Titeln extrahieren
            # Filter: muss nach Produkt klingen (Großbuchstaben Modell-Name)
            product_patterns = re.findall(r'[A-Z][a-zA-Z0-9]+ (?:[A-Z0-9]+\s?){1,3}(?:Pro|Ultra|Max|Mini|Plus|Gen\d|V\d)', title)
            for prod in product_patterns:
                if len(prod) > 5:
                    results.append({
                        "title": prod.strip(),
                        "price_eur": 0.0,
                        "price_vk": 0.0,
                        "source": f"reddit_r_{sub}",
                        "category": sub,
                        "reddit_score": score,
                    })
        log.info("Reddit r/%s: %d Produkt-Mentions", sub, len(results))
    except Exception as e:
        log.debug("Reddit scrape Fehler (%s): %s", sub, e)
    return results


# ── Shopify: Produkt erstellen ────────────────────────────────────────────────
async def _create_shopify_product(session: aiohttp.ClientSession, product: dict) -> bool:
    """Erstellt ein validiertes Produkt in Shopify."""
    title       = product.get("title", "")
    description = product.get("description", f"<p>{title} — hochwertige Qualität für anspruchsvolle Kunden.</p>")
    niche       = product.get("niche", product.get("category", "Smart Gadget"))
    price_vk    = product.get("price_vk", 0.0)
    price_ek    = product.get("price_eur", 0.0)

    if price_vk <= 0:
        price_vk = round(price_ek * 2.2, 2) if price_ek > 0 else 29.99
    if price_vk < 9.99:
        price_vk = 9.99

    # Gatekeeper-Check — verhindert Fake/Junk-Produkte unabhaengig vom KI-Gate
    ok_gate, reason = validate_product(
        title=title,
        vendor="iNeedit",
        product_type=niche,
        price=price_ek,
    )
    if not ok_gate:
        log.warning("Gatekeeper blockiert Produkt: %s — %s", title[:60], reason)
        return False

    # Tags aus Nische ableiten
    niche_tags = {
        "Smart Home": ["smart-home", "smart", "alexa", "wifi"],
        "Solar": ["solar", "energie", "powerstation"],
        "Powerstation": ["powerstation", "solar", "energie"],
        "E-Mobility": ["e-bike", "e-mobility", "elektrisch"],
        "Saugroboter": ["saugroboter", "smart-home", "roboter"],
        "Smart Lighting": ["led", "beleuchtung", "smart-home"],
        "Gaming": ["gaming", "elektronik"],
        "Audio": ["audio", "bluetooth", "sound"],
        "Grow Light": ["grow", "indoor-growing", "led"],
        "3D Drucker": ["3d-druck", "maker"],
        "Laser Engraver": ["laser-engraver", "maker"],
        "Drone": ["drohne", "kamera"],
        "Wearable": ["smartwatch", "wearable"],
        "Smartwatch": ["smartwatch", "wearable"],
        "Home Office Tech": ["home-office", "elektronik"],
        "Auto Tech": ["auto", "fahrzeugtechnik"],
        "Pet Tech": ["haustier", "smart"],
        "Camping Tech": ["camping", "outdoor"],
        "Fitness Tech": ["fitness", "sport"],
        "Werkzeug Profi": ["werkzeug", "diy"],
        "EV Charging": ["ev-charging", "elektro"],
        "Netzwerk Tech": ["netzwerk", "wlan"],
        "Tablets": ["tablet", "elektronik"],
        "Smartphones": ["smartphone", "elektronik"],
        "Smart Security": ["security", "überwachung", "smart-home"],
    }
    tags = niche_tags.get(niche, ["gadget", "elektronik"])
    tags.append("ineedit")
    tags.append("smart-tech-2026")

    payload = {
        "product": {
            "title": title,
            "body_html": description,
            "vendor": "iNeedit",
            "product_type": niche,
            "tags": ", ".join(tags),
            "status": "active",
            "variants": [{
                "price": f"{price_vk:.2f}",
                "compare_at_price": f"{price_vk * 1.3:.2f}",
                "inventory_quantity": 50,
                "inventory_management": "shopify",
                "fulfillment_service": "manual",
                "requires_shipping": True,
            }],
        }
    }
    url = f"https://{SHOP}/admin/api/{API_VER}/products.json"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with session.post(url, headers=HEADERS, json=payload, timeout=TIMEOUT) as r:
                if r.status == 429:
                    retry_after = int(r.headers.get("Retry-After", 10))
                    log.warning(
                        "Shopify 429 — warte %ds (Versuch %d/%d): %s",
                        retry_after, attempt + 1, max_retries, title[:60],
                    )
                    await asyncio.sleep(retry_after)
                    continue
                return r.status in (200, 201)
        except Exception as e:
            log.debug("Shopify create Fehler: %s", e)
            return False
    log.warning("Shopify create nach %d Versuchen fehlgeschlagen: %s", max_retries, title[:60])
    return False


# ── Haupt-Pipeline ────────────────────────────────────────────────────────────
async def run_smart_product_cycle(
    max_amazon_cats: int = 4,
    max_aliexpress_cats: int = 6,
    max_reddit_subs: int = 3,
    max_imports: int = 20,
) -> dict:
    """
    Vollautomatischer Zyklus:
    1. Research auf 3 Quellen
    2. KI-Qualitäts-Gate für jeden Kandidaten
    3. Duplikat-Check gegen vorhandene Shop-Produkte
    4. Import der validierten Produkte
    """
    if not _ok():
        return {"ok": False, "error": "Shopify-Credentials fehlen"}

    connector = aiohttp.TCPConnector(limit=10, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Phase 1: Research parallel
        log.info("Smart Product Finder: Research-Phase startet")
        import random
        amazon_cats = random.sample(AMAZON_CATEGORIES, min(max_amazon_cats, len(AMAZON_CATEGORIES)))
        ali_cats    = random.sample(ALIEXPRESS_CATEGORIES, min(max_aliexpress_cats, len(ALIEXPRESS_CATEGORIES)))
        reddit_subs = random.sample(REDDIT_SUBS, min(max_reddit_subs, len(REDDIT_SUBS)))

        research_tasks = (
            [_research_amazon(session, c) for c in amazon_cats] +
            [_research_aliexpress(session, c) for c in ali_cats] +
            [_research_reddit(session, s) for s in reddit_subs]
        )
        results = await asyncio.gather(*research_tasks, return_exceptions=True)

        candidates = []
        for r in results:
            if isinstance(r, list):
                candidates.extend(r)
        log.info("Research: %d Rohdaten-Kandidaten", len(candidates))

        # Blacklist-Vorfilter (schnell, kein API-Call)
        candidates = [c for c in candidates if not _is_blacklisted(c.get("title", ""))]
        log.info("Nach Blacklist-Filter: %d Kandidaten", len(candidates))

        # Shuffle für Vielfalt
        random.shuffle(candidates)

        # Phase 2: KI-Validierung + Duplikat-Check
        validated = []
        seen_hashes = set()
        for candidate in candidates:
            if len(validated) >= max_imports:
                break
            h = _product_hash(candidate.get("title", ""))
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            # Duplikat-Check im Shop
            if await _exists_in_shop(session, candidate["title"]):
                log.debug("Duplikat übersprungen: %s", candidate["title"][:50])
                continue

            # KI-Qualitäts-Gate
            result = await _ai_validate(candidate)
            if result:
                validated.append(result)
                log.info("✅ Validiert: %s (%.2f€ VK)", result["title"][:60], result.get("price_vk", 0))
            await asyncio.sleep(0.1)

        log.info("KI-Gate: %d/%d Kandidaten bestanden", len(validated), len(candidates))

        # Phase 3: Import
        imported = 0
        errors = 0
        for product in validated[:max_imports]:
            ok = await _create_shopify_product(session, product)
            if ok:
                imported += 1
                log.info("Importiert: %s", product["title"][:60])
            else:
                errors += 1
            await asyncio.sleep(0.5)

        log.info("Import fertig: %d neue Produkte | %d Fehler", imported, errors)
        return {
            "ok": True,
            "researched": len(candidates),
            "validated": len(validated),
            "imported": imported,
            "errors": errors,
        }
