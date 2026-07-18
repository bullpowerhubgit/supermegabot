"""
eBay / Amazon Autonomes Marketing — Smart Home & Gadgets.

Aufgaben (automatisch, alle 12h):
- Top-Produkte aus dem Shopify-Shop auf eBay-Kleinanzeigen beschreiben
- Amazon-Affiliate-Links für passende Produkte generieren (ASIN-Suche)
- Preistrend-Analyse: Was läuft auf Amazon/eBay? → Import-Kandidaten für Shop
- Keyword-Trends aus Amazon Best-Sellers (no-auth RSS)
- Telegram-Report: Top-3 Chancen des Tages

WICHTIG — Nischen-Regel (niemals mischen!):
  eBay/Amazon: NUR Smart Home / Gadgets / Solar
  Streetwear: NUR Printify (niemals eBay/Amazon für Streetwear!)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

_TG_TOKEN = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT  = lambda: os.getenv("TELEGRAM_CHAT_ID", "")
_SHOPIFY_URL   = lambda: os.getenv("SHOPIFY_STORE_URL", "").rstrip("/")
_SHOPIFY_TOKEN = lambda: os.getenv("SHOPIFY_ACCESS_TOKEN", "")
_AMZN_PARTNER  = lambda: os.getenv("AMAZON_ASSOCIATE_TAG", os.getenv("AMAZON_PARTNER_TAG", ""))

# Amazon DE Best-Sellers RSS (kein Key nötig)
_AMZN_RSS_URLS = [
    "https://www.amazon.de/gp/rss/bestsellers/amazon-devices/ref=zg_bs_amazon-devices_rsslink",
    "https://www.amazon.de/gp/rss/bestsellers/ce-de/ref=zg_bs_ce-de_rsslink",
    "https://www.amazon.de/gp/rss/bestsellers/computers/ref=zg_bs_computers_rsslink",
]

# eBay DE Trending (öffentliches RSS)
_EBAY_TRENDING_URL = "https://www.ebay.de/sch/i.html?_nkw=smart+home&_sop=12&_rss=1"


async def _tg(text: str) -> None:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{_TG_TOKEN()}/sendMessage",
                json={"chat_id": _TG_CHAT(), "text": text, "parse_mode": "HTML"},
            )
    except Exception:
        pass


# ── Amazon Best-Sellers (RSS, kein Key) ────────────────────────────────────────

async def get_amazon_bestsellers(category_url: str) -> list[dict]:
    """Liest Amazon Best-Sellers-RSS aus."""
    items = []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; SuperMegaBot/1.0)"}
            async with s.get(category_url, headers=headers) as r:
                if r.status != 200:
                    return []
                xml_text = await r.text()

        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for item in root.findall(".//item")[:10]:
            title_el = item.find("title")
            link_el  = item.find("link")
            desc_el  = item.find("description")
            title = title_el.text if title_el is not None else ""
            link  = link_el.text  if link_el  is not None else ""
            desc  = desc_el.text  if desc_el  is not None else ""

            # Preis aus Beschreibung extrahieren
            price_match = re.search(r"(\d+[.,]\d{2})\s*€", desc or "")
            price = price_match.group(1) if price_match else ""

            if title:
                items.append({
                    "title": title.strip()[:100],
                    "link": link.strip(),
                    "price": price,
                    "source": "amazon_de",
                })
    except ET.ParseError:
        log.debug("Amazon RSS parse error (kein gültiges XML)")
    except Exception as e:
        log.debug("Amazon RSS error: %s", e)
    return items


# ── Shop-Produkte für Marketing auswählen ────────────────────────────────────

async def get_top_shop_products(limit: int = 10) -> list[dict]:
    """Holt Top-Produkte aus dem Shopify-Shop (nach Preis absteigend)."""
    if not _SHOPIFY_TOKEN():
        return []
    try:
        async with aiohttp.ClientSession(
            headers={"X-Shopify-Access-Token": _SHOPIFY_TOKEN(), "Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as s:
            url = (
                f"{_SHOPIFY_URL()}/admin/api/2024-01/products.json"
                f"?limit={limit}&status=active&fields=id,title,variants,product_type,tags,images"
            )
            async with s.get(url) as r:
                if r.status != 200:
                    return []
                d = await r.json()
                products = []
                for p in d.get("products", []):
                    variants = p.get("variants", [{}])
                    price = float(variants[0].get("price", 0)) if variants else 0
                    img_url = ""
                    if p.get("images"):
                        img_url = p["images"][0].get("src", "")
                    products.append({
                        "id": str(p.get("id", "")),
                        "title": p.get("title", ""),
                        "price": price,
                        "product_type": p.get("product_type", ""),
                        "tags": p.get("tags", ""),
                        "image": img_url,
                    })
                # Nach Preis sortieren (teuerste zuerst — höhere Marge)
                products.sort(key=lambda x: x["price"], reverse=True)
                return products
    except Exception as e:
        log.debug("Shopify top products error: %s", e)
    return []


# ── Amazon Affiliate-Link generieren ─────────────────────────────────────────

def build_amazon_affiliate_link(search_term: str) -> str:
    """Baut einen Amazon-Affiliate-Suchlink (kein API-Key nötig für einfache Suche)."""
    tag = _AMZN_PARTNER()
    import urllib.parse
    encoded = urllib.parse.quote_plus(search_term)
    base = f"https://www.amazon.de/s?k={encoded}"
    if tag:
        base += f"&tag={tag}"
    return base


# ── AI Produktbeschreibung für Listings ───────────────────────────────────────

async def ai_generate_listing(product_title: str, product_type: str, price: float) -> str:
    """Generiert eine Marketing-Beschreibung für eBay/Amazon-Listings."""
    try:
        from modules.ai_client import ai_complete
        prompt = (
            f"Schreibe eine kurze, überzeugende Produktbeschreibung für:\n"
            f"Produkt: {product_title}\n"
            f"Kategorie: {product_type or 'Smart Home'}\n"
            f"Preis: EUR {price:.2f}\n\n"
            f"Anforderungen: 3-4 Sätze, Vorteile betonen, kaufmotivierend, auf Deutsch.\n"
            f"Keine Überschrift, direkt mit dem Text beginnen."
        )
        return await ai_complete(prompt, max_tokens=150)
    except Exception as e:
        log.debug("AI listing error: %s", e)
        return f"{product_title} — Jetzt zum Bestpreis bei ineedit.com.co"


# ── Trend-Analyse ─────────────────────────────────────────────────────────────

async def analyze_market_trends() -> dict:
    """
    Analysiert Amazon-Trends und vergleicht mit Shop-Sortiment.
    Gibt Import-Kandidaten zurück.
    """
    all_amzn = []
    for url in _AMZN_RSS_URLS:
        items = await get_amazon_bestsellers(url)
        all_amzn.extend(items)
        await asyncio.sleep(1)  # Kein Spam gegen Amazon

    # Top-Produktnamen extrahieren
    trending_titles = [item["title"] for item in all_amzn[:20]]

    # Mit Shop-Produkten abgleichen (Keyword-Overlap)
    shop_products = await get_top_shop_products(limit=50)
    shop_titles = {p["title"].lower() for p in shop_products}

    gaps = []  # Amazon-Trends die noch nicht im Shop sind
    for amzn in all_amzn[:20]:
        amzn_lower = amzn["title"].lower()
        # Einfacher Overlap-Check
        already_in_shop = any(
            any(word in amzn_lower for word in shop_t.split() if len(word) > 4)
            for shop_t in shop_titles
        )
        if not already_in_shop:
            gaps.append(amzn)

    return {
        "amazon_trending": trending_titles[:10],
        "shop_gap_count": len(gaps),
        "top_import_candidates": gaps[:5],
    }


# ── Haupt-Zyklus ──────────────────────────────────────────────────────────────

async def run_marketing_cycle() -> dict:
    """
    Kompletter eBay/Amazon Marketing-Zyklus.
    Wird vom Scheduler alle 12h aufgerufen.
    """
    result: dict = {
        "ok": True,
        "top_products": 0,
        "amazon_trending": [],
        "import_candidates": 0,
        "affiliate_links": [],
        "alerts": [],
    }

    # 1. Top-Produkte aus Shop holen
    products = await get_top_shop_products(limit=5)
    result["top_products"] = len(products)

    # 2. Affiliate-Links für Top-Produkte generieren
    for p in products[:3]:
        link = build_amazon_affiliate_link(p["title"])
        result["affiliate_links"].append({
            "title": p["title"],
            "shop_price": p["price"],
            "amazon_search": link,
        })

    # 3. Amazon-Trends analysieren
    trends = await analyze_market_trends()
    result["amazon_trending"] = trends.get("amazon_trending", [])[:5]
    result["import_candidates"] = trends.get("shop_gap_count", 0)
    candidates = trends.get("top_import_candidates", [])

    # 4. AI-Optimierungsvorschlag für bestes Produkt
    if products:
        best = products[0]
        listing_text = await ai_generate_listing(
            best["title"], best.get("product_type", ""), best["price"]
        )
        result["best_product_listing"] = {
            "title": best["title"],
            "price": best["price"],
            "listing": listing_text,
            "amazon_link": build_amazon_affiliate_link(best["title"]),
        }

    # 5. Telegram-Report (nur wenn interessante Daten)
    if candidates or products:
        msg_lines = ["📊 <b>eBay/Amazon Marketing Update</b>"]
        if products:
            msg_lines.append(f"🏆 Top-Produkt: {products[0]['title'][:50]} — EUR {products[0]['price']:.2f}")
        if candidates:
            msg_lines.append(f"🔍 {len(candidates)} Import-Kandidaten auf Amazon trending")
            for c in candidates[:2]:
                msg_lines.append(f"  • {c['title'][:60]}")
        if result.get("affiliate_links"):
            msg_lines.append(f"🔗 {len(result['affiliate_links'])} Affiliate-Links generiert")
        await _tg("\n".join(msg_lines))

    log.info("eBay/Amazon Marketing: %d Produkte, %d Amazon-Trends, %d Kandidaten",
             len(products), len(result["amazon_trending"]), result["import_candidates"])
    return result


async def get_status() -> dict:
    """Status für Dashboard."""
    return {
        "configured": True,
        "amazon_associate_tag": bool(_AMZN_PARTNER()),
        "shopify_connected": bool(_SHOPIFY_TOKEN()),
    }
