#!/usr/bin/env python3
"""
Amazon Autonomy — Associates affiliate blast + trending product content.
No paid PA-API needed: scrapes Amazon.de bestseller RSS + category pages.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import xml.etree.ElementTree as ET

import aiohttp

log = logging.getLogger("AmazonAutonomy")

ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "bullpowerhub-21")
SHOP = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER = os.getenv("SHOPIFY_API_VERSION", "2024-10")

AMAZON_BESTSELLER_FEEDS = [
    "https://www.amazon.de/gp/rss/bestsellers/electronics",
    "https://www.amazon.de/gp/rss/bestsellers/kitchen",
    "https://www.amazon.de/gp/rss/bestsellers/sports",
    "https://www.amazon.de/gp/rss/bestsellers/home",
    "https://www.amazon.de/gp/rss/bestsellers/toys",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "de-DE,de;q=0.9",
}


async def _ai(prompt: str, max_tokens: int = 400) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def get_trending_products(keywords: list = None) -> list:
    """Scrape Amazon.de bestseller RSS feeds for trending products."""
    products = []
    feed_url = random.choice(AMAZON_BESTSELLER_FEEDS)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(feed_url, headers=HEADERS,
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                raw = await r.text()
        raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)
        root = ET.fromstring(raw)
        ns = {"dc": "http://purl.org/dc/elements/1.1/"}
        for item in list(root.iter("item"))[:10]:
            title_el = item.find("title")
            link_el = item.find("link")
            if title_el is None or link_el is None:
                continue
            title = (title_el.text or "").strip()
            raw_link = (link_el.text or "").strip()
            # Extract ASIN from URL
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', raw_link)
            asin = asin_match.group(1) if asin_match else ""
            affiliate_url = (
                f"https://www.amazon.de/dp/{asin}?tag={ASSOCIATE_TAG}"
                if asin else raw_link + f"?tag={ASSOCIATE_TAG}"
            )
            products.append({
                "asin": asin,
                "title": title[:120],
                "url": affiliate_url,
                "image": "",
                "price": "",
            })
    except Exception as e:
        log.warning("Amazon RSS fetch error: %s", e)

    # Fallback: seed keywords als Affiliate-Suchanfragen (RSS oft geblockt)
    if not products:
        fallback_keywords = keywords or [
            "Smart Home Gadget 2026", "Wireless Earbuds Bluetooth", "USB-C Hub Multiport",
            "LED Strip WiFi App", "Fitness Tracker Smartwatch", "Power Bank 20000mAh",
            "Ring Light Selfie", "Mini Beamer Portable", "Laptop Ständer Ergonomisch",
            "Massage Gun Tiefengewebe",
        ]
        for kw in random.sample(fallback_keywords, min(5, len(fallback_keywords))):
            products.append({
                "asin": "",
                "title": kw,
                "url": f"https://www.amazon.de/s?k={kw.replace(' ', '+')}&tag={ASSOCIATE_TAG}",
                "image": "",
                "price": "Top-Angebot",
            })
    return products


async def create_affiliate_content(product: dict) -> str:
    """AI-generated review/recommendation for a product."""
    prompt = f"""Schreibe einen kurzen, überzeugenden deutschen Affiliate-Text (3-4 Sätze) für:
Produkt: "{product['title']}"
Amazon-Link: {product['url']}

Format: direkt loslegen, kein "Hier ist", kein "Natürlich".
Endet mit: "Jetzt auf Amazon kaufen ➜ {product['url']}"
Keine Preisangaben die erfunden sind."""
    return await _ai(prompt, max_tokens=200)


async def blast_affiliate_products(count: int = 5) -> dict:
    """Fetch trending → AI content → BrutusCore blast on all channels."""
    products = await get_trending_products()
    if not products:
        return {"ok": False, "error": "no products fetched", "blasted": 0}

    blasted = 0
    random.shuffle(products)
    for p in products[:count]:
        try:
            content = await create_affiliate_content(p)
            if not content or len(content) < 20:
                content = f"Jetzt zugreifen: {p['title']} ➜ {p['url']}"

            from modules.brutus_core import fire
            await fire(
                p["title"],
                content,
                link=p["url"],
                channels=["telegram", "slack", "linkedin", "discord", "shopify_blog"],
            )
            blasted += 1
            log.info("Amazon blast: %s", p["title"][:60])
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("Amazon blast error: %s", e)

    return {"ok": True, "blasted": blasted, "total_fetched": len(products)}


async def run_amazon_cycle() -> dict:
    """Scheduler entry point."""
    return await blast_affiliate_products(count=3)
