#!/usr/bin/env python3
"""
Review Goldmine — Amazon 1-Stern-Analyse → Fertige Werbung
===========================================================
Input:  Amazon-URL oder ASIN
Output in 60s:
  - Top 10 Schmerzpunkte aus 1-Stern-Reviews
  - Shopify-Beschreibung die genau das löst
  - Facebook Ad Copy (Headline + Primary Text + CTA)
  - Google Ads Headline (3 Varianten)
  - SEO-Keywords (10 Stück)
  - Email-Betreffzeilen (3 Stück)
"""
from __future__ import annotations

import asyncio
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

log = logging.getLogger("ReviewGoldmine")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "review_goldmine.db"

def _anthropic() -> str: return os.getenv("ANTHROPIC_API_KEY", "")
def _openai()    -> str: return os.getenv("OPENAI_API_KEY", "")


# ── DB ────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS goldmine_analyses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            asin        TEXT NOT NULL,
            product_url TEXT,
            product_title TEXT,
            pain_points TEXT,
            ad_copy     TEXT,
            seo_kw      TEXT,
            created_at  INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_gm_asin ON goldmine_analyses(asin);
        """)


# ── Amazon Scraper ────────────────────────────────────────────────────────────

def _extract_asin(url_or_asin: str) -> str:
    url_or_asin = url_or_asin.strip()
    # Direkte ASIN (10 Zeichen alphanumerisch)
    if re.match(r"^[A-Z0-9]{10}$", url_or_asin):
        return url_or_asin
    # Aus URL extrahieren
    m = re.search(r"/(?:dp|product|gp/product)/([A-Z0-9]{10})", url_or_asin)
    return m.group(1) if m else ""


async def _fetch_amazon_page(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=25),
            headers=headers,
            connector=aiohttp.TCPConnector(ssl=False)
        ) as s:
            async with s.get(url) as r:
                if r.status == 200:
                    return await r.text()
    except Exception as e:
        log.debug("Amazon fetch error: %s", e)
    return ""


async def scrape_reviews(asin: str, star_filter: str = "one_star") -> Dict:
    """Scrapt Amazon-Reviews (1-Stern) für eine ASIN."""
    # Amazon DE Reviews URL
    base_url = f"https://www.amazon.de/product-reviews/{asin}"
    params   = f"?filterByStar={star_filter}&reviewerType=all_reviews&sortBy=recent&pageNumber=1"
    url      = base_url + params

    html = await _fetch_amazon_page(url)
    if not html:
        # Fallback: Amazon.com
        url  = f"https://www.amazon.com/product-reviews/{asin}" + params
        html = await _fetch_amazon_page(url)

    result = {"asin": asin, "reviews": [], "product_title": ""}

    if not html:
        return result

    # Produkttitel extrahieren
    title_m = re.search(r'<span[^>]*id="productTitle"[^>]*>(.*?)</span>', html, re.DOTALL)
    if title_m:
        result["product_title"] = re.sub(r"\s+", " ", title_m.group(1)).strip()

    # Reviews aus HTML extrahieren
    # Pattern 1: data-hook="review-body"
    review_bodies = re.findall(
        r'data-hook="review-body"[^>]*>.*?<span[^>]*>(.*?)</span>',
        html, re.DOTALL
    )
    # Pattern 2: span mit review text
    if not review_bodies:
        review_bodies = re.findall(
            r'class="[^"]*review-text[^"]*"[^>]*>.*?<span[^>]*>(.*?)</span>',
            html, re.DOTALL
        )

    for body in review_bodies[:25]:
        clean = re.sub(r"<[^>]+>", "", body)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) > 20:
            result["reviews"].append(clean[:500])

    # Review-Titles für zusätzliche Insights
    titles = re.findall(r'data-hook="review-title"[^>]*>.*?<span[^>]*>(.*?)</span>', html, re.DOTALL)
    for t in titles[:10]:
        clean = re.sub(r"<[^>]+>", "", t).strip()
        if clean and len(clean) > 5:
            result["reviews"].append(f"[Titel] {clean}")

    return result


# ── AI Analyse ────────────────────────────────────────────────────────────────

async def analyze_with_ai(asin: str, reviews: List[str], product_title: str) -> Dict:
    if not reviews:
        reviews = [
            "Qualität entspricht nicht dem Preis",
            "Hält nicht was es verspricht",
            "Kundenservice antwortet nicht",
            "Beschreibung irreführend",
            "Lieferung dauerte viel zu lange"
        ]

    review_text = "\n".join(f"- {r}" for r in reviews[:20])

    prompt = f"""Du bist ein E-Commerce-Marketing-Experte. Analysiere diese 1-Stern-Reviews für "{product_title}" (ASIN: {asin}):

REVIEWS:
{review_text}

Erstelle SOFORT einsetzbare Marketing-Assets. Antworte als JSON:
{{
  "pain_points": ["Schmerzpunkt 1", "Schmerzpunkt 2", ..., "Schmerzpunkt 10"],
  "shopify_description": "200-300 Wörter Produktbeschreibung die GENAU diese Probleme löst. Mit <h3>, <ul>, <p> Tags. Deutsche Sprache. Conversion-optimiert.",
  "fb_headline": "Kurze Facebook Ad Headline (max 40 Zeichen) die Schmerz anspricht",
  "fb_primary": "Facebook Primary Text (max 150 Zeichen) mit Lösung + Urgency",
  "fb_cta": "Call-to-Action Text (max 20 Zeichen)",
  "google_headlines": ["Google Headline 1 (max 30 Zeichen)", "Google Headline 2 (max 30 Zeichen)", "Google Headline 3 (max 30 Zeichen)"],
  "seo_keywords": ["keyword1", "keyword2", ..., "keyword10"],
  "email_subjects": ["Email Betreff 1", "Email Betreff 2", "Email Betreff 3"],
  "unique_selling_point": "1 Satz: Was macht dein Produkt besser als dieses?"
}}"""

    if _anthropic():
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                connector=aiohttp.TCPConnector(ssl=False)
            ) as s:
                async with s.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": _anthropic(), "anthropic-version": "2023-06-01",
                             "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1500,
                          "messages": [{"role": "user", "content": prompt}]}
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        text = d.get("content", [{}])[0].get("text", "")
                        m = re.search(r"\{.*\}", text, re.DOTALL)
                        if m:
                            return json.loads(m.group())
        except Exception as e:
            log.warning("AI analyze error: %s", e)

    if _openai():
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                connector=aiohttp.TCPConnector(ssl=False)
            ) as s:
                async with s.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_openai()}",
                             "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini",
                          "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": 1500}
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        text = d["choices"][0]["message"]["content"]
                        m = re.search(r"\{.*\}", text, re.DOTALL)
                        if m:
                            return json.loads(m.group())
        except Exception as e:
            log.warning("OpenAI error: %s", e)

    # Fallback ohne AI
    return {
        "pain_points": [
            "Qualität schlechter als beschrieben",
            "Lieferung dauert zu lange",
            "Kundenservice reagiert nicht",
            "Preis-Leistung stimmt nicht",
            "Verarbeitung minderwertig"
        ],
        "shopify_description": f"<h3>Das Beste am Markt — ohne die typischen Probleme</h3><p>Wir haben die Reviews analysiert und ein überlegenes Produkt entwickelt.</p>",
        "fb_headline": f"Endlich: {(product_title.split() or ['Produkt'])[0]} der funktioniert",
        "fb_primary": "Kein billigen Ausreden mehr. Qualität die hält was sie verspricht. Jetzt bestellen →",
        "fb_cta": "Jetzt kaufen",
        "google_headlines": [f"{(product_title.split() or ['Produkt'])[0]} kaufen", "Beste Qualität", "Sofort lieferbar"],
        "seo_keywords": [product_title.lower(), f"{product_title.lower()} kaufen", "beste alternative"],
        "email_subjects": [f"⚠️ Vorsicht beim Kauf von {(product_title.split() or ['diesem Produkt'])[0]}", f"Das bessere {(product_title.split() or ['Produkt'])[0]}", "Warum Kunden wechseln"],
        "unique_selling_point": f"Im Gegensatz zum Konkurrenten bieten wir garantierte Qualität mit 30-Tage-Rückgabe."
    }


# ── Haupt-API ─────────────────────────────────────────────────────────────────

async def analyze(url_or_asin: str) -> Dict:
    """Vollständige Analyse: Amazon URL/ASIN → fertige Marketing-Assets."""
    init_db()
    asin = _extract_asin(url_or_asin)
    if not asin:
        return {"ok": False, "error": "Ungültige Amazon URL oder ASIN (10 Zeichen, Großbuchstaben + Zahlen)"}

    # Cache: letzte Analyse für diese ASIN (max 24h alt)
    with _db() as conn:
        cached = conn.execute(
            "SELECT * FROM goldmine_analyses WHERE asin=? AND created_at > ? ORDER BY created_at DESC LIMIT 1",
            (asin, int(time.time()) - 86400)
        ).fetchone()
        if cached:
            return {
                "ok":            True,
                "asin":          asin,
                "cached":        True,
                "product_title": cached["product_title"],
                "pain_points":   json.loads(cached["pain_points"] or "[]"),
                "ad_copy":       json.loads(cached["ad_copy"] or "{}"),
                "seo_keywords":  json.loads(cached["seo_kw"] or "[]"),
            }

    # Reviews scrapen
    log.info("Scraping Amazon reviews for ASIN: %s", asin)
    scraped = await scrape_reviews(asin, "one_star")
    product_title = scraped.get("product_title", f"Produkt {asin}")
    reviews       = scraped.get("reviews", [])

    # AI-Analyse
    log.info("Analysiere %d Reviews mit AI...", len(reviews))
    analysis = await analyze_with_ai(asin, reviews, product_title)

    # In DB cachen
    with _db() as conn:
        conn.execute(
            """INSERT INTO goldmine_analyses
               (asin, product_url, product_title, pain_points, ad_copy, seo_kw, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                asin,
                f"https://www.amazon.de/dp/{asin}",
                product_title,
                json.dumps(analysis.get("pain_points", []), ensure_ascii=False),
                json.dumps({k: v for k, v in analysis.items() if k != "pain_points"}, ensure_ascii=False),
                json.dumps(analysis.get("seo_keywords", []), ensure_ascii=False),
                int(time.time())
            )
        )

    return {
        "ok":              True,
        "asin":            asin,
        "cached":          False,
        "product_title":   product_title,
        "reviews_scraped": len(reviews),
        "pain_points":     analysis.get("pain_points", []),
        "shopify_description": analysis.get("shopify_description", ""),
        "facebook_ad": {
            "headline":  analysis.get("fb_headline", ""),
            "primary":   analysis.get("fb_primary", ""),
            "cta":       analysis.get("fb_cta", "Jetzt kaufen"),
        },
        "google_headlines": analysis.get("google_headlines", []),
        "seo_keywords":    analysis.get("seo_keywords", []),
        "email_subjects":  analysis.get("email_subjects", []),
        "usp":             analysis.get("unique_selling_point", ""),
        "amazon_url":      f"https://www.amazon.de/dp/{asin}",
    }


def get_status() -> Dict:
    init_db()
    with _db() as conn:
        total    = conn.execute("SELECT COUNT(*) FROM goldmine_analyses").fetchone()[0]
        recent   = conn.execute(
            "SELECT asin, product_title, created_at FROM goldmine_analyses ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
    return {
        "ok":        True,
        "analyses":  total,
        "recent":    [dict(r) for r in recent]
    }


init_db()
