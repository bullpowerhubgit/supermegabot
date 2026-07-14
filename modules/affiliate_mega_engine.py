#!/usr/bin/env python3
"""
Affiliate Mega Engine — Alle Affiliate-Netzwerke in einem: Amazon, DS24, eBay, Gumroad.
KI schreibt konvertierenden Content. BrutusCore blast auf alle Kanäle.
Click-Tracking via Supabase.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("AffiliateMegaEngine")

AMAZON_TAG    = os.getenv("AMAZON_ASSOCIATE_TAG", "bullpowerhub-21")
DS24_LINK     = os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/668035")
AFFILIATE_ID  = os.getenv("DS24_AFFILIATE_ID", "user37405262")
EBAY_CAMPAIGN = os.getenv("EBAY_CAMPAIGN_ID", "")
EBAY_AFFILIATE = os.getenv("EBAY_AFFILIATE_ID", "")
SHOP_URL      = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")

AMAZON_KEYWORDS = [
    "smart home starter kit", "wireless earbuds 2026", "usb c hub laptop",
    "ring light streaming", "laptop stand ergonomic", "fitness tracker waterproof",
    "coffee maker programmable", "led strip lights wifi", "power bank 20000mah",
    "bluetooth speaker portable", "standing desk converter", "webcam 1080p",
    "mechanical keyboard gaming", "monitor arm single", "noise cancelling headphones",
]

AFFILIATE_NETWORKS = {
    "amazon": f"https://www.amazon.de/s?k={{keyword}}&tag={AMAZON_TAG}",
    "ebay": "https://www.ebay.de/sch/i.html?_nkw={keyword}",
    "ds24": DS24_LINK,
    "shopify": SHOP_URL,
}


async def _ai(prompt: str, max_tokens: int = 300) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _track_click(network: str, keyword: str, link: str):
    """Click-Tracking via Supabase."""
    try:
        from modules.supabase_client import get_client
        get_client().table("affiliate_clicks").insert({
            "network": network,
            "keyword": keyword[:100],
            "link": link[:500],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.warning("Ignored error: %s", e)


async def generate_affiliate_content(product: str, network: str, link: str) -> str:
    """KI schreibt Affiliate-Post für spezifisches Netzwerk."""
    network_styles = {
        "amazon": "Deal-focused, kurz, Preis erwähnen, 'Amazon-Deal' Label",
        "ds24": "Informationsprodukt, Nutzen betonen, Provision erwähnen wenn Affiliate",
        "ebay": "Schnäppchen-Stil, Vergleich, 'Bestseller auf eBay'",
        "shopify": "Lifestyle, Produktvorteile, eigener Shop",
    }
    style = network_styles.get(network, "professionell, nutzenorientiert")
    prompt = f"""Kurzer Deutsch-Post (3 Sätze + Link) für {network.upper()} Affiliate:
Produkt/Thema: "{product}"
Stil: {style}
Link: {link}
Endet mit dem Link. Emojis OK. Dringlichkeit erzeugen."""
    content = await _ai(prompt, 120)
    return content or f"🛒 {product} — Jetzt günstig!\n👉 {link}"


async def blast_amazon_affiliates(keywords: list = None, count: int = 3) -> dict:
    """Amazon Affiliate Links für Top-Produkte → alle Kanäle."""
    kws = keywords or random.sample(AMAZON_KEYWORDS, min(count, len(AMAZON_KEYWORDS)))
    blasted = 0
    for kw in kws[:count]:
        try:
            link = AFFILIATE_NETWORKS["amazon"].format(keyword=kw.replace(" ", "+"))
            content = await generate_affiliate_content(kw, "amazon", link)
            from modules.brutus_core import fire
            await fire(
                f"Amazon Deal: {kw[:50]}",
                content, link=link,
                channels=["telegram", "slack", "discord", "twitter", "shopify_blog"],
            )
            await _track_click("amazon", kw, link)
            blasted += 1
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("Amazon blast error: %s", e)
    return {"ok": True, "network": "amazon", "blasted": blasted, "tag": AMAZON_TAG}


async def blast_ds24_affiliates(count: int = 3) -> dict:
    """DS24-Produkte mit Affiliate-Links blasten."""
    blasted = 0
    try:
        # Versuche echte DS24-Produkte zu laden
        products = []
        try:
            from modules.ds24_product_creator import list_ds24_products
            result = await list_ds24_products()
            products = result.get("products", [])[:count]
        except Exception as e:
            log.warning("Ignored error: %s", e)

        if not products:
            # Fallback: DS24-Affiliate-Link direkt
            from modules.brutus_core import fire
            content = await generate_affiliate_content(
                "Digistore24 Digitale Produkte — bis 50% Provision", "ds24", DS24_LINK
            )
            await fire("DS24 Affiliate Programm", content, link=DS24_LINK,
                       channels=["telegram", "slack", "linkedin", "discord"])
            await _track_click("ds24", "general", DS24_LINK)
            return {"ok": True, "network": "ds24", "blasted": 1, "mode": "general_link"}

        for p in products[:count]:
            try:
                link = p.get("affiliate_link", DS24_LINK)
                name = p.get("name", "DS24 Produkt")
                content = await generate_affiliate_content(name, "ds24", link)
                from modules.brutus_core import fire
                await fire(
                    f"DS24: {name[:50]}",
                    content, link=link,
                    channels=["telegram", "slack", "mailchimp", "klaviyo", "linkedin"],
                )
                await _track_click("ds24", name, link)
                blasted += 1
                await asyncio.sleep(2)
            except Exception as e:
                log.warning("DS24 blast error: %s", e)

    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "network": "ds24", "blasted": blasted}


async def blast_ebay_affiliates(count: int = 3) -> dict:
    """eBay Deals mit EPN-Links blasten."""
    keywords = random.sample(AMAZON_KEYWORDS, min(count, len(AMAZON_KEYWORDS)))
    blasted = 0
    for kw in keywords:
        try:
            base_link = AFFILIATE_NETWORKS["ebay"].format(keyword=kw.replace(" ", "+"))
            # eBay EPN Link wenn Campaign ID vorhanden
            link = f"https://rover.ebay.com/rover/1/{EBAY_CAMPAIGN}/1?mpre={base_link}" if EBAY_CAMPAIGN else base_link
            content = await generate_affiliate_content(kw, "ebay", link)
            from modules.brutus_core import fire
            await fire(
                f"eBay Deal: {kw[:50]}", content, link=link,
                channels=["telegram", "slack", "discord"],
            )
            await _track_click("ebay", kw, link)
            blasted += 1
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("eBay blast error: %s", e)
    return {"ok": True, "network": "ebay", "blasted": blasted}


async def run_affiliate_blast() -> dict:
    """ALLE Netzwerke gleichzeitig blasten."""
    results = await asyncio.gather(
        blast_amazon_affiliates(count=2),
        blast_ds24_affiliates(count=2),
        blast_ebay_affiliates(count=2),
        return_exceptions=True,
    )
    total_blasted = sum(
        r.get("blasted", 0) for r in results if isinstance(r, dict)
    )
    return {
        "ok": True,
        "total_blasted": total_blasted,
        "amazon": results[0] if isinstance(results[0], dict) else {"error": str(results[0])},
        "ds24": results[1] if isinstance(results[1], dict) else {"error": str(results[1])},
        "ebay": results[2] if isinstance(results[2], dict) else {"error": str(results[2])},
    }


async def get_affiliate_stats() -> dict:
    """Statistiken + Status aller Affiliate-Netzwerke."""
    clicks = 0
    try:
        from modules.supabase_client import get_client
        result = get_client().table("affiliate_clicks").select("id", count="exact").execute()
        clicks = result.count or 0
    except Exception as e:
        log.warning("Ignored error: %s", e)

    return {
        "ok": True,
        "networks": {
            "amazon": {"configured": True, "tag": AMAZON_TAG, "keywords": len(AMAZON_KEYWORDS)},
            "ds24": {"configured": True, "affiliate_id": AFFILIATE_ID},
            "ebay": {"configured": bool(EBAY_CAMPAIGN), "campaign": EBAY_CAMPAIGN or "set EBAY_CAMPAIGN_ID"},
            "gumroad": {"configured": False, "note": "via gumroad_autonomy.py"},
        },
        "total_clicks_tracked": clicks,
        "shop_url": SHOP_URL,
    }


async def run_affiliate_cycle() -> dict:
    """Scheduler-Einstiegspunkt."""
    return await run_affiliate_blast()
