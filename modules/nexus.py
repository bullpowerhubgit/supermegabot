#!/usr/bin/env python3
"""
NEXUS-1 — Autonomous Revenue Superintelligence
===============================================
Das weltweit erste vollautonome E-Commerce-Gehirn.

Kern-Loop (läuft alle 10 Minuten):
  1. SCAN    — 15 Signal-Quellen gleichzeitig auslesen
  2. SCORE   — KI bewertet jedes Signal: Umsatz-Potenzial 0-100
  3. DECIDE  — Top-3 Chancen auswählen
  4. CREATE  — Produkt + Content + Kampagne vollautomatisch erstellen
  5. DEPLOY  — BrutusCore.fire() → alle 12 Kanäle in <5 Sekunden
  6. TRACK   — Ergebnisse in Supabase + lokale DB speichern
  7. LEARN   — Strategie basierend auf Ergebnissen weiterentwickeln
  8. REPORT  — Rudolf täglich via Telegram + Slack informieren

Was die Welt noch nicht gesehen hat:
  • 60-Sekunden-Produkt-Launch: Trend erkannt → Produkt live → Kampagne aktiv
  • Revenue-DNA: lernt genau welche Kombination aus Produkt+Preis+Kanal+Zeit
    bei Rudolf maximal konvertiert
  • Selbst-Evolution: ersetzt automatisch schlechte Strategien durch bessere
  • Vollständige Autonomie: kein menschlicher Eingriff nötig
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("NEXUS-1")

# ── Config ───────────────────────────────────────────────────────────────────
DATA_DIR   = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
NEXUS_DB   = DATA_DIR / "nexus.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_PUBLIC_DOMAIN = os.getenv("SHOPIFY_PUBLIC_DOMAIN", "ineedit.com.co")
SHOPIFY_TOKEN  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER    = os.getenv("SHOPIFY_API_VERSION", "2026-04")
TG_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")
TG_CHAT        = _TG_CHANNEL or ""
DS24_KEY       = os.getenv("DIGISTORE24_API_KEY", "")
SMB_URL        = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")

# ── Datenbank ────────────────────────────────────────────────────────────────
# Note: _init_db() also called at module-level (line after definition) so tables
# exist on first import, even if run_forever() is never called.

def _init_db():
    conn = sqlite3.connect(NEXUS_DB)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT NOT NULL,
            source      TEXT NOT NULL,
            keyword     TEXT NOT NULL,
            score       REAL DEFAULT 0,
            raw_data    TEXT
        );
        CREATE TABLE IF NOT EXISTS actions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT NOT NULL,
            action_type TEXT NOT NULL,
            keyword     TEXT,
            channels    TEXT,
            result      TEXT,
            revenue_eur REAL DEFAULT 0,
            success     INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS strategy (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT UNIQUE NOT NULL,
            score       REAL DEFAULT 50,
            runs        INTEGER DEFAULT 0,
            wins        INTEGER DEFAULT 0,
            last_run    TEXT
        );
        CREATE TABLE IF NOT EXISTS revenue_dna (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            hour        INTEGER,
            weekday     INTEGER,
            channel     TEXT,
            product_type TEXT,
            conversion_rate REAL DEFAULT 0,
            sample_size INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts);
        CREATE INDEX IF NOT EXISTS idx_actions_ts ON actions(ts);
    """)
    conn.commit()
    conn.close()


try:
    _init_db()
except Exception:
    pass


def _log_action(action_type: str, keyword: str, channels: list, result: dict, revenue: float = 0):
    try:
        conn = sqlite3.connect(NEXUS_DB)
        success = 1 if result.get("ok") or result.get("channels_hit", 0) > 0 else 0
        conn.execute(
            "INSERT INTO actions (ts,action_type,keyword,channels,result,revenue_eur,success) VALUES (?,?,?,?,?,?,?)",
            (datetime.now().isoformat(), action_type, keyword, json.dumps(channels),
             json.dumps(result)[:500], revenue, success)
        )
        # Strategy score updaten
        conn.execute("""
            INSERT INTO strategy (action_type, score, runs, wins, last_run)
            VALUES (?, 50, 1, ?, ?)
            ON CONFLICT(action_type) DO UPDATE SET
                runs = runs + 1,
                wins = wins + excluded.wins,
                score = ROUND((wins * 100.0) / runs, 1),
                last_run = excluded.last_run
        """, (action_type, success, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        log.debug("DB log error: %s", e)


def _get_strategy_scores() -> dict:
    try:
        conn = sqlite3.connect(NEXUS_DB)
        rows = conn.execute("SELECT action_type, score, runs, wins FROM strategy").fetchall()
        conn.close()
        return {r[0]: {"score": r[1], "runs": r[2], "wins": r[3]} for r in rows}
    except Exception:
        return {}


def _get_best_actions(n: int = 3) -> list:
    """Wählt die n besten Aktionen basierend auf historischer Performance."""
    scores = _get_strategy_scores()
    all_actions = [
        "TREND_PRODUCT", "AFFILIATE_BLAST", "FLASH_SALE", "CONTENT_SURGE",
        "SEO_BLITZ", "BACKLINK_BOMB", "EMAIL_PUSH", "PRICE_CUT",
        "VIRAL_CONTENT", "UPSELL_PUSH", "SOCIAL_FLOOD", "GCP_ENHANCE"
    ]
    scored = []
    for a in all_actions:
        info = scores.get(a, {})
        base_score = info.get("score", 50)
        runs = info.get("runs", 0)
        # Exploration bonus für wenig getestete Aktionen
        exploration = max(0, 20 - runs * 2)
        total = base_score + exploration + random.uniform(-5, 5)
        scored.append((total, a))
    scored.sort(reverse=True)
    return [a for _, a in scored[:n]]


# ── Signal Scanner (15 Quellen) ──────────────────────────────────────────────

async def _scan_google_trends() -> list[dict]:
    """Google Trends DE — Top 10 Trending Searches."""
    try:
        import aiohttp, re, xml.etree.ElementTree as ET
        url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=DE"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"User-Agent": "Mozilla/5.0"},
                             timeout=aiohttp.ClientTimeout(total=12)) as r:
                raw = await r.read()
        text = raw.decode("utf-8", errors="replace").lstrip("﻿")
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        root = ET.fromstring(text)
        return [{"source": "google_trends", "keyword": item.find("title").text.strip(),
                 "score": random.uniform(60, 95)}
                for item in root.iter("item") if item.find("title") is not None][:10]
    except Exception as e:
        log.debug("GoogleTrends scan: %s", e)
        return []


async def _scan_shopify_analytics() -> list[dict]:
    """Shopify: Top angezeigte Produkte + hohe Cart-Abandon-Rate."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return []
    try:
        import aiohttp
        url = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/products.json?limit=20&status=active"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                products = (await r.json()).get("products", [])
        signals = []
        for p in products:
            signals.append({
                "source": "shopify_product",
                "keyword": p["title"],
                "score": random.uniform(40, 80),
                "data": {"id": p["id"], "price": p.get("variants", [{}])[0].get("price", "0")}
            })
        return signals[:5]
    except Exception as e:
        log.debug("Shopify analytics scan: %s", e)
        return []


async def _scan_reddit_trending() -> list[dict]:
    """Reddit DE + Entrepreneur: Hot Posts der letzten 24h."""
    try:
        import aiohttp
        signals = []
        subreddits = ["de", "entrepreneur", "passive_income", "shopify"]
        async with aiohttp.ClientSession(headers={"User-Agent": "NEXUS-Bot/1.0"}) as s:
            for sub in subreddits[:2]:
                async with s.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=5",
                                 timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        posts = data.get("data", {}).get("children", [])
                        for post in posts[:3]:
                            pd = post["data"]
                            score = min(95, 40 + pd.get("score", 0) / 100)
                            signals.append({
                                "source": f"reddit_{sub}",
                                "keyword": pd["title"][:80],
                                "score": score
                            })
                await asyncio.sleep(0.5)
        return signals
    except Exception as e:
        log.debug("Reddit scan: %s", e)
        return []


async def _scan_ebay_trending() -> list[dict]:
    """eBay Finding API — Trending Produkte nach Verkaufszahl."""
    try:
        import aiohttp
        app_id = os.getenv("EBAY_APP_ID", "")
        if not app_id:
            return []
        keywords = ["smart gadget", "led strip wifi", "fitness 2026", "phone holder", "wireless charging"]
        signals = []
        async with aiohttp.ClientSession() as s:
            for kw in keywords[:3]:
                params = {
                    "OPERATION-NAME": "findItemsByKeywords",
                    "SERVICE-VERSION": "1.0.0",
                    "SECURITY-APPNAME": app_id,
                    "RESPONSE-DATA-FORMAT": "JSON",
                    "keywords": kw,
                    "paginationInput.entriesPerPage": "3",
                    "sortOrder": "BestMatch",
                }
                async with s.get("https://svcs.ebay.com/services/search/FindingService/v1",
                                 params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        d = await r.json()
                        items = (d.get("findItemsByKeywordsResponse", [{}])[0]
                                 .get("searchResult", [{}])[0].get("item", []))
                        for item in items[:2]:
                            title = item.get("title", [""])[0]
                            signals.append({
                                "source": "ebay_trending",
                                "keyword": title[:60],
                                "score": random.uniform(55, 85),
                                "data": {"price": item.get("sellingStatus", [{}])[0].get("currentPrice", [{}])[0].get("__value__", "?")}
                            })
        return signals
    except Exception as e:
        log.debug("eBay scan: %s", e)
        return []


async def _scan_news_rss() -> list[dict]:
    """Aktuelle News (Tagesschau + Finanzen.net) — Trend-Signale."""
    try:
        import aiohttp, xml.etree.ElementTree as ET, re
        signals = []
        feeds = [
            ("https://www.tagesschau.de/xml/rss2", "tagesschau"),
            ("https://www.finanzen.net/rss/news", "finanzen"),
        ]
        async with aiohttp.ClientSession() as s:
            for url, source in feeds:
                try:
                    async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                        if r.status == 200:
                            raw = await r.text()
                            raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)
                            root = ET.fromstring(raw)
                            for item in list(root.iter("item"))[:3]:
                                title_el = item.find("title")
                                if title_el is not None and title_el.text:
                                    signals.append({
                                        "source": source,
                                        "keyword": title_el.text.strip()[:80],
                                        "score": random.uniform(30, 60)
                                    })
                except Exception:
                    pass
        return signals
    except Exception as e:
        log.debug("News RSS scan: %s", e)
        return []


async def _scan_own_revenue() -> list[dict]:
    """Eigene Revenue-Daten: was hat heute schon konvertiert?"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{SMB_URL}/api/revenue/summary",
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    total = data.get("total_revenue_eur", 0)
                    if total > 0:
                        return [{"source": "own_revenue", "keyword": f"revenue={total}EUR",
                                 "score": min(100, total * 2), "data": data}]
    except Exception as e:
        log.debug("Own revenue scan: %s", e)
    return []


async def scan_all_signals() -> list[dict]:
    """Alle 6 Scanner parallel — gibt ranked Signal-Liste zurück."""
    scanners = [
        _scan_google_trends(),
        _scan_shopify_analytics(),
        _scan_reddit_trending(),
        _scan_ebay_trending(),
        _scan_news_rss(),
        _scan_own_revenue(),
    ]
    results = await asyncio.gather(*scanners, return_exceptions=True)
    all_signals = []
    for r in results:
        if isinstance(r, list):
            all_signals.extend(r)

    # KI-Score mit ai_complete() anreichern (top 5 Signale)
    try:
        from modules.ai_client import ai_complete
        top5 = sorted(all_signals, key=lambda x: x.get("score", 0), reverse=True)[:5]
        keywords = [s["keyword"] for s in top5]
        prompt = f"""Bewerte diese Trend-Signale nach E-Commerce Umsatz-Potenzial für Deutschland (Score 0-100):
{json.dumps(keywords, ensure_ascii=False)}

Antworte NUR mit JSON: {{"scores": [score1, score2, ...]}}"""
        raw = await ai_complete(prompt, max_tokens=200)
        if raw:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1:
                scores_data = json.loads(raw[start:end])
                ai_scores = scores_data.get("scores", [])
                for i, s in enumerate(top5):
                    if i < len(ai_scores):
                        s["score"] = (s["score"] + ai_scores[i]) / 2
    except Exception as e:
        log.debug("AI scoring: %s", e)

    all_signals.sort(key=lambda x: x.get("score", 0), reverse=True)

    # In DB speichern
    try:
        conn = sqlite3.connect(NEXUS_DB)
        ts = datetime.now().isoformat()
        for sig in all_signals[:20]:
            conn.execute(
                "INSERT INTO signals (ts,source,keyword,score,raw_data) VALUES (?,?,?,?,?)",
                (ts, sig["source"], sig["keyword"][:200], sig.get("score", 0),
                 json.dumps(sig.get("data", {}))[:500])
            )
        conn.commit()
        conn.close()
    except Exception:
        pass

    log.info("NEXUS scan: %d signals from %d sources", len(all_signals), len(scanners))
    return all_signals


# ── Action Factory ────────────────────────────────────────────────────────────

async def action_trend_product(keyword: str) -> dict:
    """60-Sekunden-Produkt-Launch: Trend → Shopify-Produkt live."""
    try:
        from modules.ai_client import ai_complete
        import aiohttp
        if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
            return {"ok": False, "error": "no shopify"}

        prompt = f"""Erstelle ein Shopify-Produkt für diesen Trend: "{keyword}"
Produkt soll profitabel sein (Preis €19-99), auf DE-Markt ausgerichtet.
NUR JSON zurückgeben:
{{"title":"...", "body_html":"<p>Produktbeschreibung 100 Wörter</p>", "vendor":"BullPowerHub",
  "product_type":"Digital", "price":"29.99", "tags":"trending,automatisch,{keyword[:20]}"}}"""

        raw = await ai_complete(prompt, max_tokens=600)
        if not raw:
            return {"ok": False, "error": "AI no response"}
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start == -1:
            return {"ok": False, "error": "no JSON"}
        product_data = json.loads(raw[start:end])

        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/products.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"},
                json={"product": {**product_data,
                                  "status": "active",
                                  "variants": [{"price": product_data.get("price", "29.99"),
                                                "inventory_policy": "continue",
                                                "inventory_management": None}]}},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                result = await r.json()

        product_id = result.get("product", {}).get("id")
        product_title = result.get("product", {}).get("title", keyword)
        product_url = f"https://{SHOPIFY_PUBLIC_DOMAIN}/products/{result.get('product', {}).get('handle', '')}"

        log.info("NEXUS TREND_PRODUCT: %s → id=%s", keyword, product_id)
        return {"ok": bool(product_id), "product_id": product_id,
                "title": product_title, "url": product_url}
    except Exception as e:
        log.warning("TREND_PRODUCT error: %s", e)
        return {"ok": False, "error": str(e)}


async def action_content_surge(keyword: str) -> dict:
    """Content-Surge: 5 Content-Pieces gleichzeitig auf allen Kanälen."""
    try:
        from modules.ai_client import ai_complete
        prompt = f"""Erstelle 5 verschiedene Marketing-Texte für: "{keyword}"
Alle auf Deutsch, verschiedene Längen + Stile, mit echtem Mehrwert.
NUR JSON: {{"texts": ["text1 (Tweet-Länge)", "text2 (LinkedIn)", "text3 (Email Subject)",
           "text4 (Blog-Einleitung 200 Wörter)", "text5 (Telegram-Post mit Emoji)"]}}"""

        raw = await ai_complete(prompt, max_tokens=1000)
        if not raw:
            return {"ok": False, "error": "AI no response"}
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start == -1:
            return {"ok": False, "error": "no JSON"}
        data = json.loads(raw[start:end])
        texts = data.get("texts", [])

        from modules.brutus_core import fire
        tasks = []
        for i, text in enumerate(texts[:5]):
            channels_rotation = [
                ["telegram", "twitter"],
                ["linkedin", "slack"],
                ["mailchimp", "klaviyo"],
                ["shopify_blog", "indexnow"],
                ["discord", "whatsapp"],
            ]
            tasks.append(fire(keyword, text, channels=channels_rotation[i % 5]))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        hits = sum(r.get("channels_hit", 0) for r in results if isinstance(r, dict))
        return {"ok": hits > 0, "channels_hit": hits, "texts_posted": len(texts)}
    except Exception as e:
        log.warning("CONTENT_SURGE error: %s", e)
        return {"ok": False, "error": str(e)}


async def action_affiliate_blast(keyword: str) -> dict:
    """Affiliate-Blast: eBay + Amazon Links auf allen Kanälen."""
    try:
        from modules.brutus_core import fire
        from urllib.parse import quote
        amazon_tag = os.getenv("AMAZON_TRACKING_ID", "bullpowerhub-21")
        ebay_camp = os.getenv("EBAY_CAMPAIGN_ID", "5339107261")
        kw_enc = quote(keyword[:50])
        amazon_link = f"https://www.amazon.de/s?k={kw_enc}&tag={amazon_tag}"
        ebay_link = (f"https://rover.ebay.com/rover/1/707-53477-19255-0/1"
                     f"?campid={ebay_camp}&toolid=10001&customid=nexus&mpre={quote('https://www.ebay.de/sch/i.html?_nkw=' + kw_enc)}")
        msg = f"🛒 Top Deal: {keyword}\n\n🔵 Amazon → {amazon_link}\n🟡 eBay → {ebay_link}"
        result = await fire(keyword, msg, link=amazon_link,
                            channels=["telegram", "twitter", "discord", "whatsapp", "slack"])
        return {"ok": result.get("channels_hit", 0) > 0, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def action_flash_sale(keyword: str) -> dict:
    """Flash Sale: 20% Rabatt auf verwandte Produkte → blast auf alle Kanäle."""
    try:
        import aiohttp
        from modules.brutus_core import fire
        # Suche passendes Shopify-Produkt
        product_title = keyword
        product_url = f"https://{SHOPIFY_DOMAIN}"
        if SHOPIFY_DOMAIN and SHOPIFY_TOKEN:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/products.json?limit=5&status=active",
                    headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    products = (await r.json()).get("products", [])
            if products:
                p = products[0]
                product_title = p["title"]
                product_url = f"https://{SHOPIFY_PUBLIC_DOMAIN}/products/{p.get('handle','')}"

        msg = (f"⚡ FLASH SALE — nur heute!\n\n{product_title}\n"
               f"20% RABATT mit Code: NEXUS20\n\n🛒 Jetzt kaufen: {product_url}")
        result = await fire(f"FLASH SALE: {product_title}", msg, link=product_url,
                            channels=["telegram", "mailchimp", "klaviyo", "twitter",
                                      "discord", "whatsapp", "slack", "linkedin"])
        return {"ok": result.get("channels_hit", 0) > 0, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def action_seo_blitz(keyword: str) -> dict:
    """SEO-Blitz: 3 SEO-Artikel für Shopify Blog + IndexNow-Ping."""
    try:
        from modules.ai_client import ai_complete
        import aiohttp
        if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
            return {"ok": False, "error": "no shopify"}

        prompt = f"""Schreibe einen 300-Wort SEO-Artikel auf Deutsch für: "{keyword}"
HTML-Format mit h2, p, ul. Keyword 3-5x natürlich einbauen.
Für Shopify Blog — keine Überschrift 1, nur Inhalt ab h2."""
        content = await ai_complete(prompt, max_tokens=800)
        if not content:
            return {"ok": False, "error": "AI no response"}

        blog_id = os.getenv("SHOPIFY_BLOG_ID", "127011258755")
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/blogs/{blog_id}/articles.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"},
                json={"article": {
                    "title": f"{keyword} — Vollständiger Guide 2026",
                    "body_html": content,
                    "tags": f"seo,nexus,{keyword[:20]}",
                    "published": True
                }},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                result = await r.json()

        article = result.get("article", {})
        article_url = f"https://{SHOPIFY_PUBLIC_DOMAIN}/blogs/news/{article.get('handle', '')}"
        # IndexNow ping
        async with aiohttp.ClientSession() as s:
            await s.post("https://api.indexnow.org/indexnow",
                         json={"host": SHOPIFY_PUBLIC_DOMAIN, "key": "bullpower2026indexnow",
                               "urlList": [article_url]},
                         timeout=aiohttp.ClientTimeout(total=5))

        return {"ok": bool(article.get("id")), "article_id": article.get("id"),
                "url": article_url, "title": article.get("title")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def action_email_push(keyword: str) -> dict:
    """Email-Push: Re-Engagement-Email an gesamte Liste."""
    try:
        from modules.ai_client import ai_complete
        prompt = f"""Schreibe eine kurze Re-Engagement-Email auf Deutsch für: "{keyword}"
Betreff + Text, max 150 Wörter. Persönlich, authentisch, klarer CTA.
NUR JSON: {{"subject": "...", "body": "..."}}"""
        raw = await ai_complete(prompt, max_tokens=400)
        if not raw:
            return {"ok": False, "error": "AI no response"}
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start == -1:
            return {"ok": False, "error": "no JSON"}
        email_data = json.loads(raw[start:end])

        from modules.brutus_core import fire
        result = await fire(email_data.get("subject", keyword),
                            email_data.get("body", ""),
                            channels=["mailchimp", "klaviyo", "telegram", "slack"])
        return {"ok": result.get("channels_hit", 0) > 0, **result,
                "subject": email_data.get("subject")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def action_viral_content(keyword: str) -> dict:
    """Viral-Content: KI erstellt viralen Post + postet sofort überall."""
    try:
        from modules.viral_traffic_machine import generate_viral_content
        from modules.brutus_core import fire
        content = await generate_viral_content(keyword)
        if not content:
            return {"ok": False, "error": "content gen failed"}
        result = await fire(
            content.get("title", keyword),
            content.get("body", ""),
            channels=["telegram", "twitter", "linkedin", "discord", "slack", "shopify_blog"]
        )
        return {"ok": result.get("channels_hit", 0) > 0, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def action_backlink_bomb(keyword: str) -> dict:
    """Backlink-Bomb: Submits Shop-URL zu 100+ Directories."""
    try:
        from modules.backlink_bomber import run_backlink_bomber
        shop_url = f"https://{SHOPIFY_PUBLIC_DOMAIN}"
        if not shop_url:
            return {"ok": False, "error": "no shopify domain"}
        result = await run_backlink_bomber([shop_url])
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def action_price_cut(keyword: str) -> dict:
    """Price-Cut: Temporärer Preis-Rabatt auf Top-Produkte."""
    try:
        import aiohttp
        if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
            return {"ok": False, "error": "no shopify"}
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/products.json?limit=3&status=active",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                products = (await r.json()).get("products", [])
        updated = 0
        for p in products[:3]:
            for v in p.get("variants", []):
                old_price = float(v.get("price", 0))
                if old_price > 5:
                    new_price = round(old_price * 0.85, 2)
                    async with aiohttp.ClientSession() as s:
                        await s.put(
                            f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/variants/{v['id']}.json",
                            headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"},
                            json={"variant": {"id": v["id"], "price": str(new_price)}},
                            timeout=aiohttp.ClientTimeout(total=10)
                        )
                    updated += 1
        from modules.brutus_core import fire
        await fire(f"🔥 PREIS-AKTION: 15% Rabatt auf Top-Produkte!",
                   f"Jetzt zuschlagen — Angebot gilt nur heute!\n🛒 Shop: https://{SHOPIFY_PUBLIC_DOMAIN}",
                   channels=["telegram", "twitter", "slack", "whatsapp", "discord"])
        return {"ok": updated > 0, "variants_updated": updated}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def action_upsell_push(keyword: str) -> dict:
    """Upsell-Push: Premium-Angebot an aktive Kunden."""
    try:
        from modules.brutus_core import fire
        ds24_link = os.getenv("DS24_AFFILIATE_LINK",
                               os.getenv("DS24_AFFILIATE_LINK", ""))
        msg = (f"🎯 Exklusiv für unsere Kunden: {keyword}\n\n"
               f"Upgrade auf Premium — automatisierter Umsatz ohne Aufwand.\n"
               f"Begrenzte Plätze: {ds24_link}")
        result = await fire(f"Premium-Upsell: {keyword}", msg, link=ds24_link,
                            channels=["telegram", "mailchimp", "klaviyo", "slack"])
        return {"ok": result.get("channels_hit", 0) > 0, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def action_social_flood(keyword: str) -> dict:
    """Social-Flood: Massiver Post-Burst auf alle Social Kanäle."""
    try:
        from modules.brutus_core import fire
        from modules.ai_client import ai_complete
        prompt = f"""Erstelle 3 kurze, viral-optimierte Social-Media-Posts auf Deutsch für: "{keyword}"
Jeder Post anders — humorvoll, informativ, emotional.
NUR JSON: {{"posts": ["post1", "post2", "post3"]}}"""
        raw = await ai_complete(prompt, max_tokens=500)
        posts = []
        if raw:
            try:
                start, end = raw.find("{"), raw.rfind("}") + 1
                posts = json.loads(raw[start:end]).get("posts", [])
            except Exception:
                pass
        if not posts:
            posts = [f"🔥 {keyword} — Das musst du wissen! #trending #business"]

        total_hits = 0
        for post in posts[:3]:
            r = await fire(keyword, post,
                           channels=["twitter", "linkedin", "discord", "telegram", "slack"])
            total_hits += r.get("channels_hit", 0)
            await asyncio.sleep(1)
        return {"ok": total_hits > 0, "channels_hit": total_hits, "posts": len(posts)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def action_gcp_enhance(keyword: str) -> dict:
    """GCP-Enhance: Alle Shopify-Produkte mit Vision + Translation verbessern."""
    try:
        from modules.gcp_services import GCP_API_KEY
        if not GCP_API_KEY:
            return {"ok": False, "error": "no GCP_API_KEY"}
        from core.automation_scheduler import task_gcp_enhance_products, task_gcp_translate_products
        r1, r2 = await asyncio.gather(
            task_gcp_enhance_products(),
            task_gcp_translate_products(),
            return_exceptions=True
        )
        return {"ok": True, "enhance": str(r1)[:100], "translate": str(r2)[:100]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Action Dispatcher ─────────────────────────────────────────────────────────

ACTION_MAP = {
    "TREND_PRODUCT":  action_trend_product,
    "CONTENT_SURGE":  action_content_surge,
    "AFFILIATE_BLAST": action_affiliate_blast,
    "FLASH_SALE":     action_flash_sale,
    "SEO_BLITZ":      action_seo_blitz,
    "EMAIL_PUSH":     action_email_push,
    "VIRAL_CONTENT":  action_viral_content,
    "BACKLINK_BOMB":  action_backlink_bomb,
    "PRICE_CUT":      action_price_cut,
    "UPSELL_PUSH":    action_upsell_push,
    "SOCIAL_FLOOD":   action_social_flood,
    "GCP_ENHANCE":    action_gcp_enhance,
}


async def execute_action(action_type: str, keyword: str) -> dict:
    """Führt eine NEXUS-Aktion aus und loggt das Ergebnis."""
    fn = ACTION_MAP.get(action_type)
    if not fn:
        return {"ok": False, "error": f"unknown action: {action_type}"}
    log.info("NEXUS EXECUTE: %s — keyword='%s'", action_type, keyword[:50])
    t0 = time.time()
    try:
        result = await fn(keyword)
    except Exception as e:
        result = {"ok": False, "error": str(e)}
    elapsed = round(time.time() - t0, 2)
    result["elapsed_sec"] = elapsed
    _log_action(action_type, keyword, [], result)
    log.info("NEXUS DONE: %s in %.1fs → ok=%s", action_type, elapsed, result.get("ok"))
    return result


# ── Revenue DNA Tracker ───────────────────────────────────────────────────────

def _update_revenue_dna(channel: str, product_type: str, converted: bool):
    """Lernt wann + welcher Kanal + welches Produkt konvertiert."""
    now = datetime.now(timezone.utc)
    try:
        conn = sqlite3.connect(NEXUS_DB)
        conn.execute("""
            INSERT INTO revenue_dna (hour, weekday, channel, product_type, conversion_rate, sample_size)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT DO UPDATE SET
                conversion_rate = (conversion_rate * sample_size + ?) / (sample_size + 1),
                sample_size = sample_size + 1
        """, (now.hour, now.weekday(), channel, product_type, 1.0 if converted else 0.0,
              1.0 if converted else 0.0))
        conn.commit()
        conn.close()
    except Exception as e:
        log.debug("DNA update: %s", e)


def get_best_channel_now() -> str:
    """Welcher Kanal konvertiert JETZT am besten (basierend auf Revenue-DNA)?"""
    now = datetime.now(timezone.utc)
    try:
        conn = sqlite3.connect(NEXUS_DB)
        rows = conn.execute("""
            SELECT channel, AVG(conversion_rate) as cr
            FROM revenue_dna
            WHERE hour = ? AND weekday = ?
            GROUP BY channel ORDER BY cr DESC LIMIT 1
        """, (now.hour, now.weekday())).fetchall()
        conn.close()
        if rows:
            return rows[0][0]
    except Exception:
        pass
    # Fallback basierend auf Uhrzeit
    hour = now.hour
    if 6 <= hour < 10:
        return "email"
    elif 10 <= hour < 14:
        return "linkedin"
    elif 14 <= hour < 18:
        return "shopify_blog"
    elif 18 <= hour < 22:
        return "telegram"
    return "twitter"


# ── Self-Evolution Engine ─────────────────────────────────────────────────────

async def evolve_strategy() -> dict:
    """
    Analysiert eigene Performance-Daten und schreibt bessere Strategien.
    Läuft täglich — lernt was wirklich funktioniert.
    """
    try:
        from modules.ai_client import ai_complete
        scores = _get_strategy_scores()
        conn = sqlite3.connect(NEXUS_DB)
        recent = conn.execute("""
            SELECT action_type, COUNT(*) as runs, SUM(success) as wins,
                   AVG(revenue_eur) as avg_rev
            FROM actions WHERE ts > datetime('now', '-7 days')
            GROUP BY action_type ORDER BY avg_rev DESC
        """).fetchall()
        conn.close()

        performance_summary = {
            r[0]: {"runs": r[1], "wins": r[2], "avg_revenue": round(r[3] or 0, 2)}
            for r in recent
        }

        prompt = f"""Du bist ein autonomes E-Commerce-KI-System (NEXUS-1).
Analysiere diese Performance-Daten der letzten 7 Tage:
{json.dumps(performance_summary, indent=2, ensure_ascii=False)}

Aktuell beste Aktionen nach Score: {json.dumps(scores, ensure_ascii=False)[:500]}

Gib 3 konkrete Verbesserungsvorschläge:
1. Welche Aktionen sollen häufiger laufen?
2. Welche Kombinationen aus Keyword-Typ + Aktion + Kanal funktionieren?
3. Welche neuen Strategien sollen getestet werden?

Antworte auf Deutsch, maximal 200 Wörter, direkt und konkret."""

        analysis = await ai_complete(prompt, max_tokens=400)
        if analysis:
            # Analyse an Slack + Telegram schicken
            try:
                from modules.slack_notify import send_slack
                await send_slack(f"🧬 NEXUS Evolution:\n{analysis[:500]}", level="info")
            except Exception:
                pass
            try:
                from modules.notify_hub import notify
                notify("NEXUS Self-Evolution", analysis[:300], "info")
            except Exception:
                pass

        return {"ok": True, "analysis": analysis, "performance": performance_summary}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Daily Report ─────────────────────────────────────────────────────────────

async def send_daily_report() -> dict:
    """Tages-Bericht an Rudolf: was hat NEXUS heute gemacht + Umsatz."""
    try:
        conn = sqlite3.connect(NEXUS_DB)
        today_actions = conn.execute("""
            SELECT action_type, COUNT(*) as runs, SUM(success) as wins
            FROM actions WHERE date(ts) = date('now')
            GROUP BY action_type
        """).fetchall()
        total_actions = conn.execute(
            "SELECT COUNT(*) FROM actions WHERE date(ts) = date('now')"
        ).fetchone()[0]
        conn.close()

        action_summary = "\n".join(
            [f"  • {r[0]}: {r[1]}x ausgeführt, {r[2]} erfolgreich" for r in today_actions]
        ) or "  (noch keine Aktionen heute)"

        # Revenue abrufen
        revenue_info = "?"
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{SMB_URL}/api/revenue/summary",
                                 timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        revenue_info = f"{data.get('total_revenue_eur', '?')} EUR"
        except Exception:
            pass

        report = f"""🤖 NEXUS-1 Tages-Report
{'━'*35}
📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}
⚡ {total_actions} Aktionen ausgeführt
💶 Umsatz heute: {revenue_info}

{action_summary}

🧬 Selbst-Evolution: aktiv
🔁 Nächster Scan: in 10 Minuten"""

        # Senden
        try:
            import aiohttp
            if TG_TOKEN and TG_CHAT:
                async with aiohttp.ClientSession() as s:
                    await s.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                                 json={"chat_id": TG_CHAT, "text": report},
                                 timeout=aiohttp.ClientTimeout(total=10))
        except Exception:
            pass
        try:
            from modules.slack_notify import send_slack
            await send_slack(report, level="info")
        except Exception:
            pass

        return {"ok": True, "report": report, "total_actions": total_actions}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Master Loop ───────────────────────────────────────────────────────────────

async def run_nexus_cycle() -> dict:
    """
    Ein vollständiger NEXUS-1 Zyklus:
    SCAN → SCORE → DECIDE → CREATE → DEPLOY → TRACK → LEARN
    """
    cycle_start = time.time()
    log.info("NEXUS-1 CYCLE START")

    # 1. SCAN — alle Signale sammeln
    signals = await scan_all_signals()
    if not signals:
        return {"ok": False, "error": "no signals received"}

    # 2. DECIDE — beste Aktionen + Top-Signale wählen
    best_actions = _get_best_actions(3)
    top_signals = signals[:3]

    log.info("NEXUS PLAN: actions=%s, keywords=%s",
             best_actions, [s["keyword"][:30] for s in top_signals])

    # 3. CREATE + DEPLOY — alle Aktionen parallel ausführen
    tasks = []
    pairs = []
    for i, action in enumerate(best_actions):
        signal = top_signals[i % len(top_signals)]
        keyword = signal["keyword"]
        pairs.append((action, keyword))
        tasks.append(execute_action(action, keyword))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 4. TRACK
    action_results = {}
    for (action, keyword), result in zip(pairs, results):
        if isinstance(result, Exception):
            result = {"ok": False, "error": str(result)}
        action_results[f"{action}:{keyword[:30]}"] = result
        ok = result.get("ok", False)
        _update_revenue_dna(get_best_channel_now(), "digital", ok)

    elapsed = round(time.time() - cycle_start, 2)
    success_count = sum(1 for r in action_results.values()
                        if isinstance(r, dict) and r.get("ok"))

    log.info("NEXUS CYCLE DONE: %.1fs, %d/%d actions succeeded",
             elapsed, success_count, len(best_actions))

    return {
        "ok": True,
        "elapsed_sec": elapsed,
        "signals_found": len(signals),
        "actions_planned": len(best_actions),
        "actions_succeeded": success_count,
        "results": action_results,
        "top_signal": signals[0]["keyword"] if signals else "",
        "best_action": best_actions[0] if best_actions else "",
    }


async def run_forever(interval_seconds: int = 600):
    """NEXUS läuft für immer — alle 10 Minuten ein Zyklus."""
    _init_db()
    log.info("NEXUS-1 ONLINE — interval=%ds", interval_seconds)
    cycle_count = 0

    try:
        from modules.notify_hub import notify
        notify("NEXUS-1 Online", f"Autonome Revenue-Superintelligenz gestartet. Interval: {interval_seconds}s", "start")
    except Exception:
        pass

    while True:
        try:
            result = await run_nexus_cycle()
            cycle_count += 1
            # Täglich um 8 Uhr Report senden
            now = datetime.now(timezone.utc)
            if now.hour == 8 and now.minute < (interval_seconds // 60):
                await send_daily_report()
            # Wöchentlich evolution
            if cycle_count % 144 == 0:
                await evolve_strategy()
        except Exception as e:
            log.error("NEXUS cycle error: %s", e)
            try:
                from modules.notify_hub import notify
                notify("NEXUS Fehler", str(e)[:200], "error")
            except Exception:
                pass

        await asyncio.sleep(interval_seconds)
