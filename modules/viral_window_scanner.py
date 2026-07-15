#!/usr/bin/env python3
"""
Viral Window Scanner — Echtzeit-Marktlücken-Detektor
======================================================
Kombiniert 5 Signalquellen → AI-Score → Telegram-Alert → Shopify-Import

Subscriptions (Stripe):
  Alert Only  €29/mo  — VIRAL_PRICE_ALERT  env var
  Pro         €79/mo  — VIRAL_PRICE_PRO    env var
  Agency      €199/mo — VIRAL_PRICE_AGENCY env var

Signalquellen (kein API-Key nötig):
  1. Google Trends RSS (DE)
  2. Amazon Movers & Shakers (scraping)
  3. AliExpress Top-Produkte (scraping)
  4. Reddit r/Entrepreneur + r/ecommerce (public JSON)
  5. TikTok Nischen-Rotation (kuratiert)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

log = logging.getLogger("ViralWindowScanner")

# ── Config ────────────────────────────────────────────────────────────────────

_BASE_DIR  = Path(__file__).parent.parent
_DATA_DIR  = _BASE_DIR / "data"
_DATA_DIR.mkdir(exist_ok=True)
_DB_PATH   = _DATA_DIR / "viral_scanner.db"

STRIPE_BASE = "https://api.stripe.com/v1"
TG_API      = "https://api.telegram.org"

def _stripe_key()  -> str: return os.getenv("STRIPE_SECRET_KEY", "")
def _tg_token()    -> str: return os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
def _tg_chat()     -> str: return os.getenv("TELEGRAM_CHAT_ID", "")
def _shopify_dom() -> str: return os.getenv("SHOPIFY_SHOP_DOMAIN", "")

# Stripe Price IDs für die 3 Tiers (werden bei Setup angelegt)
def _price_alert()  -> str: return os.getenv("VIRAL_PRICE_ALERT", "")
def _price_pro()    -> str: return os.getenv("VIRAL_PRICE_PRO", "")
def _price_agency() -> str: return os.getenv("VIRAL_PRICE_AGENCY", "")

WINDOW_HOURS = 48  # Durchschnittliches Trend-Fenster
MIN_SCORE_SHOPIFY_IMPORT = 72  # Ab diesem Score: Auto-Import in Shopify
MIN_SCORE_ALERT = 55  # Ab diesem Score: Telegram-Alert

# ── Datenbank ─────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS viral_signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword     TEXT NOT NULL,
            source      TEXT NOT NULL,
            raw_data    TEXT,
            score       REAL DEFAULT 0,
            saturation  INTEGER DEFAULT -1,
            ek_eur      REAL DEFAULT 0,
            vk_eur      REAL DEFAULT 0,
            margin_pct  REAL DEFAULT 0,
            fb_ad_json  TEXT,
            first_seen  INTEGER,
            last_seen   INTEGER,
            alerted     INTEGER DEFAULT 0,
            imported    INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS viral_subscribers (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            email        TEXT UNIQUE NOT NULL,
            telegram_id  TEXT,
            tier         TEXT DEFAULT 'alert',
            stripe_sub   TEXT,
            stripe_cus   TEXT,
            active       INTEGER DEFAULT 1,
            created_at   INTEGER
        );

        CREATE TABLE IF NOT EXISTS viral_alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword     TEXT NOT NULL,
            score       REAL,
            sources     TEXT,
            window_h    INTEGER DEFAULT 48,
            supplier    TEXT,
            margin_pct  REAL,
            shopify_id  TEXT,
            message     TEXT,
            sent_at     INTEGER
        );

        CREATE TABLE IF NOT EXISTS viral_stripe_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id   TEXT UNIQUE,
            event_type TEXT,
            payload    TEXT,
            processed  INTEGER DEFAULT 0,
            created_at INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_viral_keyword ON viral_signals(keyword);
        CREATE INDEX IF NOT EXISTS idx_viral_score   ON viral_signals(score DESC);
        """)
        # Spalten-Migration für ältere DB-Versionen
        for col, coltype in [
            ("saturation", "INTEGER DEFAULT -1"),
            ("ek_eur",     "REAL DEFAULT 0"),
            ("vk_eur",     "REAL DEFAULT 0"),
            ("margin_pct", "REAL DEFAULT 0"),
            ("fb_ad_json", "TEXT"),
            ("sources",    "TEXT"),
        ]:
            try:
                c.execute(f"ALTER TABLE viral_signals ADD COLUMN {col} {coltype}")
            except Exception:
                pass


# ── HTTP Helper ───────────────────────────────────────────────────────────────

def _session(timeout: int = 20) -> aiohttp.ClientSession:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    }
    return aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout),
        headers=headers,
        connector=aiohttp.TCPConnector(ssl=False)
    )


async def _tg_send(text: str, chat_id: str = "") -> bool:
    token = _tg_token()
    chat  = chat_id or _tg_chat()
    if not token or not chat:
        return False
    try:
        async with _session(8) as s:
            r = await s.post(
                f"{TG_API}/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": True}
            )
            return r.status == 200
    except Exception as e:
        log.debug("TG send error: %s", e)
        return False


async def _stripe(method: str, path: str, data: dict = None) -> dict:
    key = _stripe_key()
    if not key:
        return {"error": "STRIPE_SECRET_KEY not set"}
    headers = {"Authorization": f"Bearer {key}"}
    url = f"{STRIPE_BASE}/{path}"
    try:
        async with _session(30) as s:
            if method == "GET":
                async with s.get(url, headers=headers, params=data) as r:
                    return await r.json()
            else:
                async with s.post(url, headers=headers, data=data) as r:
                    return await r.json()
    except Exception as e:
        return {"error": str(e)}


# ── Signal Source 1: Google Trends RSS ───────────────────────────────────────

async def fetch_google_trends() -> List[Dict]:
    results = []
    urls = [
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=DE",
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=AT",
    ]
    for url in urls:
        try:
            async with _session(15) as s:
                async with s.get(url) as r:
                    if r.status != 200:
                        continue
                    text = await r.text()
                    titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", text)
                    traffic = re.findall(r"<ht:approx_traffic>(.*?)</ht:approx_traffic>", text)
                    for i, title in enumerate(titles[:20]):
                        if len(title) < 3:
                            continue
                        t_num = 0
                        if i < len(traffic):
                            t_str = traffic[i].replace("+", "").replace(",", "").replace(".", "")
                            try:
                                t_num = int(t_str.replace("K", "000").replace("M", "000000"))
                            except ValueError:
                                pass
                        results.append({
                            "keyword": title.strip(),
                            "source": "google_trends",
                            "traffic": t_num,
                            "raw": text[:200]
                        })
        except Exception as e:
            log.debug("Google Trends error: %s", e)
    return results


# ── Signal Source 2: Amazon Movers & Shakers ─────────────────────────────────

AMAZON_MOVERS_CATEGORIES = [
    "electronics", "sporting-goods", "home-garden",
    "health-personal-care", "beauty", "kitchen"
]

async def fetch_amazon_movers() -> List[Dict]:
    results = []
    # Amazon DE Movers & Shakers — öffentliche Seite
    for cat in AMAZON_MOVERS_CATEGORIES[:3]:
        url = f"https://www.amazon.de/gp/movers-and-shakers/{cat}/"
        try:
            async with _session(20) as s:
                async with s.get(url) as r:
                    if r.status != 200:
                        continue
                    html = await r.text()
                    # Extrahiere Produkttitel aus Amazon HTML
                    titles = re.findall(
                        r'class="zg-bdg-text">.*?<.*?aria-label="(.*?)"',
                        html, re.DOTALL
                    )
                    # Fallback: span mit aria-label
                    if not titles:
                        titles = re.findall(
                            r'aria-label="([^"]{10,100})"',
                            html
                        )[:15]
                    # Rang-Steigerungen (positive = trending)
                    ranks = re.findall(r"\+(\d+)", html)
                    for i, title in enumerate(titles[:10]):
                        clean = re.sub(r"\s+", " ", title).strip()
                        if len(clean) < 5:
                            continue
                        rank_gain = int(ranks[i]) if i < len(ranks) else 0
                        results.append({
                            "keyword": clean[:120],
                            "source": "amazon_movers",
                            "category": cat,
                            "rank_gain": rank_gain,
                            "raw": ""
                        })
        except Exception as e:
            log.debug("Amazon Movers error (%s): %s", cat, e)
        await asyncio.sleep(1.5)
    return results


# ── Signal Source 3: AliExpress Trending ─────────────────────────────────────

ALIEXPRESS_CATEGORIES = [
    "consumer-electronics", "sports-entertainment",
    "home-garden", "beauty-health"
]

async def fetch_aliexpress_trending() -> List[Dict]:
    results = []
    for cat in ALIEXPRESS_CATEGORIES[:2]:
        url = f"https://bestselling.aliexpress.com/en/{cat}"
        try:
            async with _session(20) as s:
                async with s.get(url) as r:
                    if r.status != 200:
                        continue
                    html = await r.text()
                    # Produktnamen aus AliExpress
                    titles = re.findall(r'"title"\s*:\s*"([^"]{10,150})"', html)
                    prices = re.findall(r'"salePrice"\s*:\s*"([^"]+)"', html)
                    orders = re.findall(r'"totalOrders"\s*:\s*(\d+)', html)
                    for i, title in enumerate(titles[:10]):
                        price_raw = prices[i] if i < len(prices) else "0"
                        try:
                            price = float(re.sub(r"[^0-9.]", "", price_raw))
                        except ValueError:
                            price = 0.0
                        order_count = int(orders[i]) if i < len(orders) else 0
                        results.append({
                            "keyword": title.strip()[:120],
                            "source": "aliexpress",
                            "category": cat,
                            "price_eur": round(price * 0.93, 2),
                            "order_count": order_count,
                            "raw": ""
                        })
        except Exception as e:
            log.debug("AliExpress error (%s): %s", cat, e)
        await asyncio.sleep(1)
    return results


# ── Signal Source 4: Reddit via RSS + Pullpush.io (kein Auth nötig) ──────────

REDDIT_SUBS = ["gadgets", "smarthome", "ecommerce", "Entrepreneur"]

async def _reddit_rss(sub: str, session) -> List[Dict]:
    """Public RSS feed — kein Auth, kein Rate-Limit-Problem."""
    url = f"https://old.reddit.com/r/{sub}/.rss"
    results = []
    try:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
            if r.status != 200:
                return []
            text = await r.text()
        import re
        titles = re.findall(r"<title><!\[CDATA\[(.+?)\]\]></title>", text)
        for title in titles[1:]:  # skip feed title
            title = title.strip()
            if len(title) < 10 or title.lower() in ("hot", sub.lower()):
                continue
            results.append({
                "keyword": title[:120],
                "source": "reddit_rss",
                "subreddit": sub,
                "upvotes": 0,
                "ratio": 0,
                "raw": ""
            })
    except Exception as e:
        log.debug("Reddit RSS (%s): %s", sub, e)
    return results


async def _reddit_pullpush(sub: str, session) -> List[Dict]:
    """Pullpush.io — kostenloses Reddit-Archiv, kein Auth."""
    url = (f"https://api.pullpush.io/reddit/search/submission/"
           f"?subreddit={sub}&size=15&sort=score&order=desc")
    results = []
    try:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
            if r.status != 200:
                return []
            data = await r.json()
        for post in data.get("data", []):
            title = post.get("title", "")
            score = post.get("score", 0)
            if not title or score < 20:
                continue
            results.append({
                "keyword": title[:120],
                "source": "pullpush",
                "subreddit": sub,
                "upvotes": score,
                "ratio": 0,
                "raw": ""
            })
    except Exception as e:
        log.debug("Pullpush (%s): %s", sub, e)
    return results


async def fetch_reddit_signals() -> List[Dict]:
    results = []
    async with _session(15) as s:
        for sub in REDDIT_SUBS:
            # Pullpush.io als Primary (zuverlässig, kein Auth)
            pp = await _reddit_pullpush(sub, s)
            if pp:
                results.extend(pp)
            else:
                # Fallback: old.reddit.com RSS
                rss = await _reddit_rss(sub, s)
                results.extend(rss)
            await asyncio.sleep(0.5)
    return results


# ── Signal Source 5: TikTok Nischen ──────────────────────────────────────────

TIKTOK_PRODUCT_NICHES = [
    "LED Schreibtischlampe", "Mini Kühlschrank", "Massage Pistole",
    "Luftbefeuchter", "Kabelloser Lautsprecher", "Fitness Widerstandsband",
    "Rucksack Anti-Diebstahl", "Haarserum Keratin", "Smart Home Gadget",
    "Solar Powerstation", "E-Bike Zubehör", "Webcam HD günstig",
    "Mikrofon Podcast", "Standing Desk", "Ring Light Studio",
    "Nail Art Set", "Skincare Jade Roller", "Coffee Grinder Electric",
    "Wireless Earbuds", "Smartwatch Fitness Tracker",
    "Portable Blender", "Car Phone Holder Magnetic",
    "Desk Cable Management", "Ergonomic Chair Cushion",
    "UV Sanitizer Box", "Pet Grooming Glove", "Kitchen Scale Digital",
    "Posture Corrector", "Laptop Stand Adjustable", "Bamboo Cutting Board Set"
]

def fetch_tiktok_niches() -> List[Dict]:
    import random
    selected = random.sample(TIKTOK_PRODUCT_NICHES, min(12, len(TIKTOK_PRODUCT_NICHES)))
    return [
        {"keyword": kw, "source": "tiktok_niche", "raw": ""} for kw in selected
    ]


# ── AI Scoring ────────────────────────────────────────────────────────────────

async def score_with_ai(keywords_with_sources: List[Dict]) -> List[Dict]:
    if not keywords_with_sources:
        return _heuristic_score(keywords_with_sources)

    # Top 20 für AI-Bewertung vorbereiten
    kw_list = "\n".join(
        f"- {d['keyword']} [Quellen: {d.get('sources', d.get('source','?'))}]"
        for d in keywords_with_sources[:20]
    )

    prompt = f"""Du bist ein E-Commerce-Experte für Dropshipping und Trendprodukte.
Bewerte diese Produkt-Keywords nach Marktpotenzial für einen deutschen Online-Shop (0-100):

{kw_list}

Kriterien:
- Ist es ein physisches Produkt das man kaufen/verkaufen kann? (30 Pkte)
- Ist es gerade viral / trending? (25 Pkte)
- Gibt es eine klare Zielgruppe? (20 Pkte)
- Margin möglich (EK €5-50, VK 2-4x)? (15 Pkte)
- Nicht gesättigt in DE? (10 Pkte)

Antworte NUR als JSON-Array:
[{{"keyword": "...", "score": 75, "margin_pct": 65, "supplier_hint": "AliExpress Electronics", "window_h": 48, "reason": "kurze Begründung"}}]
"""

    from modules.ai_client import ai_complete
    try:
        raw = await ai_complete(prompt, system="", max_tokens=2000)
        scored = _parse_ai_scores(raw, keywords_with_sources)
        if scored:
            return scored
    except Exception as e:
        log.warning("AI scoring error: %s", e)

    return _heuristic_score(keywords_with_sources)


def _parse_ai_scores(raw: str, fallback: List[Dict]) -> List[Dict]:
    try:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []
        data = json.loads(match.group())
        result = []
        for item in data:
            if "keyword" in item and "score" in item:
                result.append({
                    "keyword":       item["keyword"],
                    "score":         float(item.get("score", 0)),
                    "margin_pct":    float(item.get("margin_pct", 50)),
                    "supplier_hint": item.get("supplier_hint", "AliExpress"),
                    "window_h":      int(item.get("window_h", WINDOW_HOURS)),
                    "reason":        item.get("reason", ""),
                    "sources":       next(
                        (d.get("sources", d.get("source", "multi"))
                         for d in fallback if d["keyword"] == item["keyword"]),
                        "multi"
                    )
                })
        return result
    except Exception as e:
        log.debug("AI score parse error: %s", e)
        return []


def _heuristic_score(items: List[Dict]) -> List[Dict]:
    result = []
    for d in items:
        kw = d["keyword"]
        score = 40.0
        # Physisches Produkt? Schlüsselwörter
        product_words = ["set", "kit", "pro", "mini", "smart", "wireless",
                         "portable", "electric", "adjustable", "ergonomic",
                         "solar", "led", "usb", "bluetooth", "lcd"]
        if any(w in kw.lower() for w in product_words):
            score += 20
        # Mehrere Quellen = mehr Gewicht
        sources = d.get("sources", d.get("source", ""))
        if isinstance(sources, list):
            score += min(len(sources) * 8, 24)
        # Amazon Movers: hoher Rang-Gewinn
        if d.get("rank_gain", 0) > 50:
            score += 15
        # Reddit: viele Upvotes
        if d.get("upvotes", 0) > 500:
            score += 10
        # AliExpress: viele Bestellungen
        if d.get("order_count", 0) > 1000:
            score += 12
        score = min(score, 100)
        result.append({
            "keyword":       kw,
            "score":         round(score, 1),
            "margin_pct":    55.0,
            "supplier_hint": "AliExpress",
            "window_h":      WINDOW_HOURS,
            "reason":        "Heuristik-Score",
            "sources":       sources if isinstance(sources, str) else ",".join(sources)
        })
    return result


# ── Signal Source 6: Shopify-Sättigungs-Check ────────────────────────────────

async def fetch_shopify_saturation(keywords: List[str]) -> Dict[str, int]:
    """Schätzt Shopify-Sättigung via DuckDuckGo HTML-Suche (kein API-Key nötig)."""
    saturation: Dict[str, int] = {}
    for kw in keywords[:15]:
        query = f"site:myshopify.com {kw}"
        url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        try:
            async with _session(12) as s:
                async with s.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
                    if r.status != 200:
                        saturation[kw] = -1
                        continue
                    html = await r.text()
                    # Anzahl Ergebnisse aus DDG-HTML auslesen
                    count_match = re.search(
                        r'(\d[\d,\.]+)\s+(?:Ergebnisse|results)', html, re.IGNORECASE
                    )
                    if count_match:
                        raw = count_match.group(1).replace(",", "").replace(".", "")
                        saturation[kw] = int(raw)
                    else:
                        # Zähle sichtbare .result Einträge als Mindestschätzung
                        hits = len(re.findall(r'class="result"', html))
                        saturation[kw] = hits * 10
        except Exception as e:
            log.debug("Saturation check error (%s): %s", kw, e)
            saturation[kw] = -1
        await asyncio.sleep(0.8)
    return saturation


# ── Margin-Rechner ────────────────────────────────────────────────────────────

def calculate_margin(ek_eur: float, vk_eur: float, shipping_eur: float = 3.5) -> Dict:
    """Berechnet Nettomargin inkl. Versand und Shopify-Gebühren (2%)."""
    if ek_eur <= 0 or vk_eur <= 0:
        return {"margin_eur": 0, "margin_pct": 0, "roi_pct": 0}
    shopify_fee = vk_eur * 0.02
    cost_total  = ek_eur + shipping_eur + shopify_fee
    margin_eur  = vk_eur - cost_total
    margin_pct  = (margin_eur / vk_eur * 100) if vk_eur > 0 else 0
    roi_pct     = (margin_eur / cost_total * 100) if cost_total > 0 else 0
    return {
        "ek_eur":      round(ek_eur, 2),
        "vk_eur":      round(vk_eur, 2),
        "shipping_eur": round(shipping_eur, 2),
        "shopify_fee":  round(shopify_fee, 2),
        "margin_eur":   round(margin_eur, 2),
        "margin_pct":   round(margin_pct, 1),
        "roi_pct":      round(roi_pct, 1),
    }


# ── Facebook Ad Copy Generator ────────────────────────────────────────────────

async def generate_fb_ad_copy(item: Dict) -> Dict[str, str]:
    """Generiert 3 Facebook-Ad-Varianten (Hook / Body / CTA) via Claude/OpenAI."""
    kw     = item["keyword"]
    score  = item["score"]
    margin = item.get("margin_pct", 55)
    reason = item.get("reason", "")

    prompt = f"""Du bist ein Facebook-Ads-Experte für deutschsprachige E-Commerce-Shops.
Erstelle 3 verschiedene Facebook-Ad-Varianten für dieses Trending-Produkt:

Produkt: {kw}
Trend-Score: {score}/100
Warum trending: {reason}
Margin: ~{margin:.0f}%

Format (NUR JSON, kein Text drumrum):
{{
  "ad_a": {{
    "hook": "Erste Zeile die stoppt (max 10 Wörter)",
    "body": "2-3 Sätze Produktvorteile + Social Proof",
    "cta": "Call-to-Action Button Text"
  }},
  "ad_b": {{
    "hook": "Andere Emotion/Winkel",
    "body": "Problem → Lösung Stil",
    "cta": "CTA"
  }},
  "ad_c": {{
    "hook": "FOMO/Urgency Winkel",
    "body": "Limitiert/Trending Stil",
    "cta": "CTA"
  }},
  "hashtags": "#tag1 #tag2 #tag3 #tag4 #tag5"
}}"""

    empty = {
        "ad_a": {"hook": f"🔥 {kw} — jetzt trending!", "body": reason, "cta": "Jetzt kaufen"},
        "ad_b": {"hook": f"Alle kaufen gerade: {kw}", "body": f"Score {score}/100 • Margin ~{margin:.0f}%", "cta": "Zum Shop"},
        "ad_c": {"hook": "Trend-Fenster schließt sich!", "body": f"{kw} — limitiertes Angebot", "cta": "Sichern"},
        "hashtags": "#trending #dropshipping #onlineshop #trendprodukt #viral"
    }

    from modules.ai_client import ai_complete
    try:
        raw_text = await ai_complete(prompt, system="", max_tokens=800)
        if raw_text:
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if match:
                return json.loads(match.group())
    except Exception as e:
        log.debug("FB Ad Copy error: %s", e)

    return empty


# ── Signal-Aggregator ─────────────────────────────────────────────────────────

async def aggregate_signals() -> List[Dict]:
    log.info("Starte Signal-Aggregation von 6 Quellen...")
    tasks = [
        fetch_google_trends(),
        fetch_amazon_movers(),
        fetch_aliexpress_trending(),
        fetch_reddit_signals(),
    ]
    results_raw = await asyncio.gather(*tasks, return_exceptions=True)

    # TikTok ist synchron
    tiktok = fetch_tiktok_niches()

    all_signals: List[Dict] = []
    for r in results_raw:
        if isinstance(r, list):
            all_signals.extend(r)
    all_signals.extend(tiktok)

    # Deduplizieren: gleiches Keyword aus mehreren Quellen zusammenführen
    merged: Dict[str, Dict] = {}
    for sig in all_signals:
        kw_key = sig["keyword"].lower()[:80]
        if kw_key not in merged:
            merged[kw_key] = {**sig, "sources": [sig["source"]], "saturation": -1}
        else:
            if sig["source"] not in merged[kw_key]["sources"]:
                merged[kw_key]["sources"].append(sig["source"])
            # Aggregiere numerische Felder — KEIN Duplikat, nur summieren
            for field in ["traffic", "rank_gain", "upvotes", "order_count"]:
                if field in sig:
                    merged[kw_key][field] = merged[kw_key].get(field, 0) + sig.get(field, 0)

    # Signal 6: Shopify-Sättigung — wird direkt in merged eingetragen (kein neuer Eintrag)
    if merged:
        kw_list = [v["keyword"] for v in list(merged.values())[:15]]
        saturation_map = await fetch_shopify_saturation(kw_list)
        for kw_key, entry in merged.items():
            kw = entry["keyword"]
            entry["saturation"] = saturation_map.get(kw, saturation_map.get(kw.lower(), -1))

    log.info("Aggregiert: %d eindeutige Keywords aus %d Signalen",
             len(merged), len(all_signals))
    return list(merged.values())


# ── Haupt-Scan ────────────────────────────────────────────────────────────────

async def run_scan() -> Dict:
    init_db()
    now = int(time.time())
    log.info("=== Viral Window Scan gestartet ===")

    # 1. Signale sammeln
    signals = await aggregate_signals()
    if not signals:
        return {"ok": False, "error": "Keine Signale erhalten"}

    # 2. AI-Scoring
    scored = await score_with_ai(signals)
    if not scored:
        return {"ok": False, "error": "AI-Scoring fehlgeschlagen"}

    # 3. In DB speichern + Top-Produkte finden
    high_score_items = []
    with _db() as conn:
        # Spalten nachrüsten falls DB aus älterer Version
        for col, coltype in [
            ("saturation", "INTEGER DEFAULT -1"),
            ("ek_eur", "REAL DEFAULT 0"),
            ("vk_eur", "REAL DEFAULT 0"),
            ("margin_pct", "REAL DEFAULT 0"),
            ("fb_ad_json", "TEXT"),
            ("sources", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE viral_signals ADD COLUMN {col} {coltype}")
            except Exception:
                pass  # Spalte existiert bereits

        for item in scored:
            kw       = item["keyword"]
            sc       = item["score"]
            sat      = item.get("saturation", -1)
            srcs     = item.get("sources", "")
            if isinstance(srcs, list):
                srcs = ",".join(srcs)

            # Margin aus AI-Score ableiten (EK Schätzung: score/100 * 40 + 5 EUR)
            ek_est  = round(5 + (sc / 100) * 35, 2)
            vk_est  = round(ek_est * (2.5 + item.get("margin_pct", 55) / 100), 2)
            mg      = calculate_margin(ek_est, vk_est)

            existing = conn.execute(
                "SELECT id, score, alerted, imported, fb_ad_json FROM viral_signals WHERE keyword=?",
                (kw,)
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE viral_signals
                       SET score=?, last_seen=?, source=?, saturation=?,
                           ek_eur=?, vk_eur=?, margin_pct=?
                       WHERE keyword=?""",
                    (sc, now, srcs, sat, mg["ek_eur"], mg["vk_eur"], mg["margin_pct"], kw)
                )
            else:
                conn.execute(
                    """INSERT INTO viral_signals
                       (keyword, source, score, saturation, ek_eur, vk_eur, margin_pct,
                        first_seen, last_seen)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (kw, srcs, sc, sat, mg["ek_eur"], mg["vk_eur"], mg["margin_pct"], now, now)
                )

            if sc >= MIN_SCORE_ALERT:
                alerted      = existing["alerted"]    if existing else 0
                imported     = existing["imported"]   if existing else 0
                fb_ad_cached = existing["fb_ad_json"] if existing else None
                high_score_items.append({
                    **item,
                    "alerted":       alerted,
                    "imported":      imported,
                    "margin_data":   mg,
                    "saturation":    sat,
                    "fb_ad_cached":  fb_ad_cached,
                })

    # 4a. Bestehende unimportierte High-Score Signale aus DB nachladen
    with _db() as conn:
        pending = conn.execute(
            """SELECT keyword, score, source AS sources, saturation, ek_eur, vk_eur,
                      margin_pct, fb_ad_json, alerted, imported
               FROM viral_signals
               WHERE score >= ? AND imported = 0
               ORDER BY score DESC LIMIT 20""",
            (MIN_SCORE_SHOPIFY_IMPORT,)
        ).fetchall()
        existing_kws = {i["keyword"] for i in high_score_items}
        for row in pending:
            if row["keyword"] not in existing_kws:
                high_score_items.append({
                    "keyword":      row["keyword"],
                    "score":        row["score"],
                    "sources":      row["sources"],
                    "saturation":   row["saturation"] or -1,
                    "alerted":      row["alerted"],
                    "imported":     row["imported"],
                    "margin_data":  {"ek_eur": row["ek_eur"], "vk_eur": row["vk_eur"],
                                     "margin_pct": row["margin_pct"], "margin_eur": 0, "roi_pct": 0},
                    "supplier_hint": "AliExpress",
                    "reason":       "Bestehendes High-Score Signal — jetzt importiert",
                    "window_h":     WINDOW_HOURS,
                    "fb_ad_cached": row["fb_ad_json"],
                })

    # 4b. FB Ad Copy + Alerts + Shopify-Import (pro Produkt EINMALIG generieren)
    imported_count = 0
    alerted_count  = 0
    for item in sorted(high_score_items, key=lambda x: x["score"], reverse=True)[:10]:
        kw = item["keyword"]
        sc = item["score"]

        # FB Ad Copy nur generieren wenn noch nicht vorhanden
        fb_ad = None
        if not item.get("fb_ad_cached"):
            fb_ad = await generate_fb_ad_copy(item)
            with _db() as conn:
                conn.execute(
                    "UPDATE viral_signals SET fb_ad_json=? WHERE keyword=?",
                    (json.dumps(fb_ad), kw)
                )
        else:
            try:
                fb_ad = json.loads(item["fb_ad_cached"])
            except Exception:
                fb_ad = None

        item["fb_ad"] = fb_ad

        # Shopify-Import wenn Score hoch genug und noch nicht importiert
        shopify_id = None
        if sc >= MIN_SCORE_SHOPIFY_IMPORT and not item.get("imported"):
            shopify_id = await _shopify_import(item)
            if shopify_id:
                with _db() as conn:
                    conn.execute(
                        "UPDATE viral_signals SET imported=1 WHERE keyword=?", (kw,)
                    )
                imported_count += 1

        # Telegram-Alert nur 1x pro Keyword
        if not item.get("alerted"):
            await _send_alert(item, shopify_id)
            with _db() as conn:
                conn.execute(
                    "UPDATE viral_signals SET alerted=1 WHERE keyword=?", (kw,)
                )
            alerted_count += 1

    summary = {
        "ok": True,
        "signals_total":    len(signals),
        "signals_scored":   len(scored),
        "high_score":       len(high_score_items),
        "alerts_sent":      alerted_count,
        "shopify_imported": imported_count,
        "top_products":     [
            {"keyword": i["keyword"], "score": i["score"]}
            for i in sorted(high_score_items, key=lambda x: x["score"], reverse=True)[:5]
        ],
        "scanned_at": datetime.now(timezone.utc).isoformat()
    }
    log.info("Scan abgeschlossen: %s", summary)
    return summary


# ── Shopify Auto-Import ───────────────────────────────────────────────────────

_NEWS_SIGNALS = [
    "year later", "years later", "owners say", "owners said", "says study",
    "according to", "report says", "collecting dust", "collect dust",
    "have been", "you've probably", "you probably", "without realizing",
    "running trains", "running hospitals", "running printers", "expert says",
    "regret buying", "decades-old", "still running", "tastenkürzel",
    "umschalttaste", "ein-/ausblenden", "ein/ausblenden", "keyboard shortcut",
    "shortcut", "people say", "they say", "study says", "scientists say",
]

def _is_valid_product(keyword: str) -> bool:
    """Gibt True zurück wenn keyword ein echtes Produkt-Name ist (kein News-Artikel)."""
    if not keyword or len(keyword) > 80:
        return False
    if "|" in keyword:
        return False
    kw_lower = keyword.lower()
    if any(sig in kw_lower for sig in _NEWS_SIGNALS):
        return False
    # Zu viele Wörter = wahrscheinlich ein Satz / Headline
    if len(keyword.split()) > 7:
        return False
    # Anführungszeichen am Anfang deutet auf Zitat/Headline hin
    if keyword.startswith('"') or keyword.startswith("'"):
        return False
    return True


def _clean_product_title(raw: str) -> str:
    """Bereinigt News-Artikel-Titel zu echten Produkt-Titeln."""
    # Alles nach | entfernen (Artikel-Subheadlines wie "Apple Vision Pro | It's collecting dust")
    title = raw.split("|")[0].strip()
    # Anführungszeichen entfernen
    title = title.strip('"\'')
    # Mehrfache Leerzeichen normalisieren
    title = " ".join(title.split())
    # Zu lange Titel kürzen (echte Produktnamen sind kurz)
    if len(title) > 80:
        # Versuche am letzten Wort innerhalb 80 Zeichen zu kürzen
        title = title[:80].rsplit(" ", 1)[0]
    # News-typische Muster erkennen und ablehnen → Fallback auf kw[:60]
    news_signals = ["years later", "year later", "running trains", "running hospitals",
                    "have been", "owners say", "you've probably", "you probably",
                    "without realizing", "collect dust", "collecting dust",
                    "says study", "report says", "according to", "expert says"]
    if any(sig in title.lower() for sig in news_signals):
        # Das ist eindeutig kein Produktname → rohen Keyword als Stichwort nehmen
        # Nehme erstes relevantes Substantiv aus dem keyword
        words = [w for w in raw.split() if len(w) > 3 and w[0].isupper()]
        if words:
            title = " ".join(words[:4])
        else:
            title = raw[:60]
    return title.strip() or raw[:60]


async def _shopify_import(item: Dict) -> Optional[str]:
    token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    version = os.getenv("SHOPIFY_API_VERSION", "2026-04")
    if not token or not domain:
        log.warning("Shopify credentials fehlen")
        return None

    kw     = item["keyword"]
    score  = item["score"]
    window = item.get("window_h", WINDOW_HOURS)
    reason = item.get("reason", "")

    mg = item.get("margin_data", {})
    margin_html = ""
    if mg and mg.get("ek_eur", 0) > 0:
        margin_html = (
            f"<p>💵 <strong>Margin:</strong> "
            f"EK ~€{mg['ek_eur']} | VK ~€{mg['vk_eur']} | "
            f"Gewinn ~€{mg.get('margin_eur',0)} ({mg['margin_pct']}%) | ROI {mg.get('roi_pct',0)}%</p>"
        )

    sat = item.get("saturation", -1)
    sat_html = ""
    if sat >= 0:
        level = "NIEDRIG 🟢" if sat < 50 else ("MITTEL 🟡" if sat < 500 else "HOCH 🔴")
        sat_html = f"<p>🏪 Shopify-Sättigung: {level} (~{sat} Stores)</p>"

    fb_ad = item.get("fb_ad", {})
    fb_html = ""
    if fb_ad and fb_ad.get("ad_a"):
        ad_a = fb_ad["ad_a"]
        fb_html = (f"<h3>📢 Facebook Ad</h3>"
                   f"<p><strong>Hook:</strong> {ad_a.get('hook','')}</p>"
                   f"<p>{ad_a.get('body','')}</p>"
                   f"<p><em>CTA: {ad_a.get('cta','Jetzt kaufen')}</em></p>")

    body = (f"<h2>🔥 Trending — AI-Score {score}/100</h2>"
            f"<p>Trend-Fenster: ~{window}h | {reason}</p>"
            f"{margin_html}{sat_html}"
            f"<p>Supplier: {item.get('supplier_hint','AliExpress')}</p>"
            f"<h3>Warum jetzt?</h3>"
            f"<p>{kw} ist in mehreren Quellen gleichzeitig sichtbar.</p>"
            f"{fb_html}")

    tags = ["viral-window", "trending-2026", f"score-{int(score)}",
            item.get("supplier_hint", "aliexpress").lower().replace(" ", "-")]
    if sat >= 0 and sat < 50:
        tags.append("low-competition")

    vk = mg.get("vk_eur", 0) if mg else 0
    if vk <= 0:
        vk = round(29.99 + (score / 100) * 50, 2)

    product_title = _clean_product_title(kw)

    payload = {
        "product": {
            "title": product_title,
            "body_html": body,
            "vendor": "Viral Window Scanner",
            "product_type": "Trending Product",
            "status": "active",
            "tags": ",".join(tags),
            "variants": [{"price": str(vk), "inventory_management": "shopify",
                          "inventory_quantity": 10}]
        }
    }
    try:
        async with _session(30) as s:
            async with s.post(
                f"https://{domain}/admin/api/{version}/products.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json=payload
            ) as r:
                data = await r.json()
                product_id = str(data.get("product", {}).get("id", ""))
                if product_id:
                    log.info("Shopify Import OK: %s → %s", kw, product_id)
                    return product_id
                log.warning("Shopify Import Fehler: %s", data.get("errors", data))
    except Exception as e:
        log.warning("Shopify Import Exception: %s", e)
    return None


# ── Telegram Alert ────────────────────────────────────────────────────────────

async def _send_alert(item: Dict, shopify_id: Optional[str] = None):
    kw     = item["keyword"]
    score  = item["score"]
    margin = item.get("margin_pct", 55)
    window = item.get("window_h", WINDOW_HOURS)
    srcs   = item.get("sources", "multi")
    if isinstance(srcs, list):
        srcs = ", ".join(srcs)
    reason = item.get("reason", "")
    supplier = item.get("supplier_hint", "AliExpress")

    # Score-Emoji
    emoji = "🔥🔥🔥" if score >= 85 else ("🔥🔥" if score >= 70 else "🔥")
    urgency = "JETZT SOFORT" if score >= 85 else ("HEUTE noch" if score >= 70 else "Diese Woche")

    shopify_line = ""
    if shopify_id:
        domain = _shopify_dom()
        if domain:
            shopify_line = f"\n🛍️ <b>Auto-Import:</b> <a href='https://{domain}/admin/products/{shopify_id}'>Shopify ✅</a>"

    # Margin-Daten aus item holen
    mg = item.get("margin_data", {})
    margin_line = ""
    if mg and mg.get("ek_eur", 0) > 0:
        margin_line = (
            f"\n💵 EK: ~€{mg['ek_eur']} → VK: ~€{mg['vk_eur']} "
            f"→ Gewinn: €{mg['margin_eur']} ({mg['margin_pct']}%)"
        )

    # Sättigungs-Info
    sat = item.get("saturation", -1)
    sat_line = ""
    if sat >= 0:
        if sat < 50:
            sat_line = f"\n🟢 Sättigung: NIEDRIG (~{sat} Shops)"
        elif sat < 500:
            sat_line = f"\n🟡 Sättigung: MITTEL (~{sat} Shops)"
        else:
            sat_line = f"\n🔴 Sättigung: HOCH (~{sat} Shops)"

    msg = f"""{emoji} <b>VIRAL WINDOW ALERT</b> {emoji}

🎯 <b>{kw}</b>
📊 <b>Score: {score}/100</b> — {urgency} handeln!
⏱️ Trend-Fenster: ~{window}h noch offen{margin_line}{sat_line}
📡 Signale: {srcs}
🏭 Supplier: {supplier}
{shopify_line}

<i>{reason}</i>

━━━━━━━━━━━━━━━━━━
🤖 Viral Window Scanner by AiiteC
💎 Pro-Tier für Auto-Import: /subscribe"""

    # An Rudolf's Chat senden
    await _tg_send(msg)

    # Pro/Agency Subscriber bekommen zusätzlich FB Ad Copy
    fb_ad = item.get("fb_ad")
    fb_msg = None
    if fb_ad:
        ad_a = fb_ad.get("ad_a", {})
        fb_msg = (
            f"📢 <b>FB Ad Copy für: {kw}</b>\n\n"
            f"<b>Ad A (Hook):</b> {ad_a.get('hook','')}\n"
            f"{ad_a.get('body','')}\n"
            f"🔘 <i>{ad_a.get('cta','')}</i>\n\n"
            f"{fb_ad.get('hashtags','')}"
        )

    # An alle aktiven Subscriber senden (tier-basiert)
    await _notify_subscribers(msg, fb_msg=fb_msg, min_tier_score=score)

    # In DB loggen
    with _db() as conn:
        conn.execute(
            """INSERT INTO viral_alerts
               (keyword, score, sources, window_h, supplier, margin_pct, shopify_id, message, sent_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (kw, score, srcs, window, supplier, margin, shopify_id, msg, int(time.time()))
        )


async def _notify_subscribers(msg: str, fb_msg: str = None, min_tier_score: float = 0):
    with _db() as conn:
        subs = conn.execute(
            "SELECT telegram_id, tier FROM viral_subscribers WHERE active=1 AND telegram_id != ''"
        ).fetchall()

    for sub in subs:
        tid  = sub["telegram_id"]
        tier = sub["tier"]
        # Alert-Only bekommt ab Score 55, Pro ab 40, Agency immer
        if tier == "alert" and min_tier_score < MIN_SCORE_ALERT:
            continue
        if not tid:
            continue
        await _tg_send(msg, chat_id=tid)
        # Pro + Agency bekommen zusätzlich FB Ad Copy
        if fb_msg and tier in ("pro", "agency"):
            await asyncio.sleep(0.2)
            await _tg_send(fb_msg, chat_id=tid)
        await asyncio.sleep(0.05)


# ── Stripe Subscription Setup ─────────────────────────────────────────────────

async def setup_stripe_products() -> Dict:
    """Erstellt Stripe Produkte + Prices falls noch nicht vorhanden."""
    results = {}
    products_to_create = [
        {
            "env_var": "VIRAL_PRICE_ALERT",
            "name":    "Viral Window Alert",
            "desc":    "Echtzeit-Alerts wenn Produkte viral gehen (Score 55+)",
            "amount":  2900,
            "tier":    "alert"
        },
        {
            "env_var": "VIRAL_PRICE_PRO",
            "name":    "Viral Window Pro",
            "desc":    "Alerts + Shopify Auto-Import + Lieferanten-Details (Score 40+)",
            "amount":  7900,
            "tier":    "pro"
        },
        {
            "env_var": "VIRAL_PRICE_AGENCY",
            "name":    "Viral Window Agency",
            "desc":    "5 Stores, White-Label, Priority Alerts, persönlicher Support",
            "amount":  19900,
            "tier":    "agency"
        }
    ]

    for p in products_to_create:
        existing_price = os.getenv(p["env_var"], "")
        if existing_price:
            results[p["tier"]] = {"price_id": existing_price, "status": "already_set"}
            continue

        # Produkt anlegen
        prod = await _stripe("POST", "products", {
            "name":        p["name"],
            "description": p["desc"],
            "metadata[tier]": p["tier"]
        })
        prod_id = prod.get("id", "")
        if not prod_id:
            results[p["tier"]] = {"error": prod.get("error", "unknown")}
            continue

        # Recurring Price anlegen
        price = await _stripe("POST", "prices", {
            "product":              prod_id,
            "unit_amount":          str(p["amount"]),
            "currency":             "eur",
            "recurring[interval]":  "month",
            "nickname":             p["name"]
        })
        price_id = price.get("id", "")
        results[p["tier"]] = {
            "product_id": prod_id,
            "price_id":   price_id,
            "env_var":    p["env_var"],
            "amount_eur": p["amount"] / 100
        }
        log.info("Stripe Price erstellt: %s = %s", p["env_var"], price_id)

    return results


async def create_checkout_session(email: str, tier: str = "alert") -> Dict:
    """Erstellt Stripe Checkout für Viral Window Subscription."""
    price_map = {
        "alert":  _price_alert(),
        "pro":    _price_pro(),
        "agency": _price_agency()
    }
    price_id = price_map.get(tier, _price_alert())
    if not price_id:
        return {"error": f"VIRAL_PRICE_{tier.upper()} nicht gesetzt — zuerst /api/viral/setup aufrufen"}

    dashboard_url = os.getenv("DASHBOARD_URL", "https://supermegabot-production.up.railway.app")
    session = await _stripe("POST", "checkout/sessions", {
        "payment_method_types[]":       "card",
        "mode":                          "subscription",
        "line_items[0][price]":          price_id,
        "line_items[0][quantity]":       "1",
        "customer_email":                email,
        "success_url":                   f"{dashboard_url}/viral/success?session={{CHECKOUT_SESSION_ID}}",
        "cancel_url":                    f"{dashboard_url}/viral",
        "metadata[tier]":                tier,
        "metadata[service]":             "viral_window_scanner"
    })
    return {
        "ok":          "id" in session,
        "checkout_url": session.get("url", ""),
        "session_id":   session.get("id", ""),
        "tier":         tier,
        "error":        session.get("error", {}).get("message", "") if "error" in session else ""
    }


async def handle_stripe_webhook(payload: bytes, signature: str) -> Dict:
    """Verarbeitet Stripe Webhook Events für Subscriptions."""
    import hmac
    import hashlib

    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if secret:
        try:
            parts  = {p.split("=")[0]: p.split("=")[1] for p in signature.split(",")}
            ts     = parts.get("t", "0")
            sig_v1 = parts.get("v1", "")
            expected = hmac.new(
                secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, sig_v1):
                return {"ok": False, "error": "Invalid signature"}
        except Exception:
            pass

    try:
        event = json.loads(payload)
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}

    event_id   = event.get("id", "")
    event_type = event.get("type", "")

    # Deduplizierung
    with _db() as conn:
        existing = conn.execute(
            "SELECT id FROM viral_stripe_events WHERE event_id=?", (event_id,)
        ).fetchone()
        if existing:
            return {"ok": True, "status": "already_processed"}
        conn.execute(
            "INSERT INTO viral_stripe_events (event_id, event_type, payload, created_at) VALUES (?,?,?,?)",
            (event_id, event_type, json.dumps(event), int(time.time()))
        )

    obj = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        customer = obj.get("customer", "")
        email    = obj.get("customer_email", "") or obj.get("customer_details", {}).get("email", "")
        sub_id   = obj.get("subscription", "")
        tier     = obj.get("metadata", {}).get("tier", "alert")

        if email:
            with _db() as conn:
                existing_sub = conn.execute(
                    "SELECT id FROM viral_subscribers WHERE email=?", (email,)
                ).fetchone()
                if existing_sub:
                    conn.execute(
                        "UPDATE viral_subscribers SET tier=?, stripe_sub=?, stripe_cus=?, active=1 WHERE email=?",
                        (tier, sub_id, customer, email)
                    )
                else:
                    conn.execute(
                        """INSERT INTO viral_subscribers
                           (email, tier, stripe_sub, stripe_cus, active, created_at)
                           VALUES (?,?,?,?,1,?)""",
                        (email, tier, sub_id, customer, int(time.time()))
                    )

            await _tg_send(
                f"💰 Neuer Viral-Window Subscriber!\n"
                f"📧 {email}\n💎 Tier: {tier.upper()}\n"
                f"💳 Sub: {sub_id}"
            )
            log.info("Neuer Subscriber: %s (%s)", email, tier)

    elif event_type in ("customer.subscription.deleted", "customer.subscription.updated"):
        sub_id = obj.get("id", "")
        status = obj.get("status", "")
        if sub_id:
            active = 1 if status == "active" else 0
            with _db() as conn:
                conn.execute(
                    "UPDATE viral_subscribers SET active=? WHERE stripe_sub=?",
                    (active, sub_id)
                )

    with _db() as conn:
        conn.execute(
            "UPDATE viral_stripe_events SET processed=1 WHERE event_id=?", (event_id,)
        )

    return {"ok": True, "event_type": event_type}


# ── Public API ────────────────────────────────────────────────────────────────

async def get_status() -> Dict:
    init_db()
    with _db() as conn:
        total_signals = conn.execute("SELECT COUNT(*) FROM viral_signals").fetchone()[0]
        high_score    = conn.execute(
            "SELECT COUNT(*) FROM viral_signals WHERE score >= ?", (MIN_SCORE_ALERT,)
        ).fetchone()[0]
        alerts_sent   = conn.execute("SELECT COUNT(*) FROM viral_alerts").fetchone()[0]
        subs_active   = conn.execute(
            "SELECT COUNT(*) FROM viral_subscribers WHERE active=1"
        ).fetchone()[0]
        imported      = conn.execute(
            "SELECT COUNT(*) FROM viral_signals WHERE imported=1"
        ).fetchone()[0]
        top5_raw = conn.execute(
            "SELECT keyword, score, sources FROM viral_signals ORDER BY score DESC LIMIT 30"
        ).fetchall()
        top5 = [r for r in top5_raw if _is_valid_product(r["keyword"])][:5]
        last_alert = conn.execute(
            "SELECT keyword, score, sent_at FROM viral_alerts ORDER BY sent_at DESC LIMIT 1"
        ).fetchone()

    return {
        "ok":             True,
        "total_signals":  total_signals,
        "high_score":     high_score,
        "alerts_sent":    alerts_sent,
        "subs_active":    subs_active,
        "shopify_imports": imported,
        "stripe_setup": {
            "alert":  bool(_price_alert()),
            "pro":    bool(_price_pro()),
            "agency": bool(_price_agency())
        },
        "top_products": [
            {"keyword": r["keyword"], "score": r["score"], "sources": r["sources"]}
            for r in top5
        ],
        "last_alert": {
            "keyword": last_alert["keyword"],
            "score":   last_alert["score"],
            "sent_at": last_alert["sent_at"]
        } if last_alert else None
    }


async def get_latest_alerts(limit: int = 20) -> List[Dict]:
    init_db()
    with _db() as conn:
        rows = conn.execute(
            """SELECT keyword, score, sources, window_h, supplier, margin_pct,
                      shopify_id, sent_at
               FROM viral_alerts ORDER BY sent_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


async def add_telegram_subscriber(email: str, telegram_id: str, tier: str = "alert") -> Dict:
    init_db()
    with _db() as conn:
        try:
            conn.execute(
                """INSERT OR REPLACE INTO viral_subscribers
                   (email, telegram_id, tier, active, created_at)
                   VALUES (?,?,?,1,?)""",
                (email, telegram_id, tier, int(time.time()))
            )
            return {"ok": True, "email": email, "tier": tier}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# Modul-Init
init_db()
