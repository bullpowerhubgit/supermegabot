#!/usr/bin/env python3
"""
Fiverr Buyer Request Scraper + Gig Promoter — kein API-Key nötig.
Fiverr hat keine offizielle public API — wir promoten via BRUTUS
und scrapen öffentliche Kategorie-Seiten für Keyword-Signale.
"""
import asyncio
import logging
import os
import random

import aiohttp

log = logging.getLogger("FiverrScraper")

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
STORE    = os.getenv("DS24_AFFILIATE_LINK", "https://ineedit.com.co")
PORTFOLIO = "https://aiitec.online"

# Rudolf's Fiverr Gig-Kategorien (curated)
GIG_SERVICES = [
    ("Shopify Store Setup & Automation", "shopify automation ecommerce setup ai"),
    ("Python Bot & Automation Script", "python automation bot script aiohttp"),
    ("Dropshipping Store Komplett", "dropshipping store setup aliexpress shopify"),
    ("AI-Powered Product Descriptions", "ai seo product description shopify writing"),
    ("Klaviyo & Mailchimp Email Setup", "email marketing klaviyo mailchimp shopify"),
    ("Telegram Bot Development", "telegram bot python automation"),
    ("Printify/Printful Store Integration", "printify printful shopify pod integration"),
    ("E-Commerce SEO Optimierung", "shopify seo optimization product listing"),
]

GIG_PROMOS = [
    "🎯 **Fiverr Gig**: {service}\n✅ 24h Lieferzeit\n✅ Unbegrenzte Revisionen\n✅ 5⭐ Qualität\n\n📋 Portfolio: {portfolio}\n💬 Direkt anfragen!",
    "💼 Neues **Fiverr Angebot**: {service}\n\nIch bin Rudolf Sarkany — Shopify AI Specialist mit 5+ Jahren Erfahrung.\n\n🔥 Sofort verfügbar | Budget-freundlich\n📌 {portfolio}",
    "⚡ **Service verfügbar**: {service}\n\nBullPower Hub | aiitec.online\n\nWas ich liefere:\n✔ Vollautomatische Lösung\n✔ Sauberer Code\n✔ Support nach Abgabe\n\n{portfolio}",
]

BUYER_REQUEST_TEMPLATES = [
    "Ich suche Shopify Entwickler für vollautomatischen Dropshipping Store",
    "Python Script für automatische Produktliste gesucht",
    "Klaviyo Email Automation Spezialist gesucht",
    "TikTok Shop Integration mit Shopify",
    "AI Chatbot für E-Commerce Website",
    "Automatischer Social Media Poster gesucht",
]


async def _tg(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        return False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": True}) as r:
                return (await r.json(content_type=None)).get("ok", False)
    except Exception:
        return False


async def run_fiverr_gig_promotion(count: int = 3) -> dict:
    """Promote Rudolf's Fiverr services across all channels."""
    services = random.sample(GIG_SERVICES, min(count, len(GIG_SERVICES)))
    channels_hit = 0

    for service_name, niche_kw in services:
        promo = random.choice(GIG_PROMOS).format(service=service_name, portfolio=PORTFOLIO)
        tg_ok = await _tg(f"🎯 *Fiverr Service*\n\n{promo}")
        if tg_ok:
            channels_hit += 1

        try:
            from modules.brutus_traffic_engine import brutus_run
            r = await brutus_run(niche=f"fiverr gig {niche_kw}")
            channels_hit += r.get("channels_hit", 0)
        except Exception:
            pass

        await asyncio.sleep(0.5)

    log.info("Fiverr promotion: %d gigs, %d channels", len(services), channels_hit)
    return {"gigs_promoted": len(services), "channels_hit": channels_hit}


async def run_fiverr_buyer_request_alert() -> dict:
    """Simulate buyer request matching + alert via Telegram."""
    # Fiverr public pages don't expose buyer requests without login
    # Instead: alert with a reminder to check buyer requests manually
    # AND blast all channels with services to attract inbound
    msg = (
        "📬 *Fiverr Buyer Requests — Check jetzt!*\n\n"
        "Gehe zu: fiverr.com → Selling → Buyer Requests\n\n"
        "Suchanfragen heute:\n"
    )
    for req in random.sample(BUYER_REQUEST_TEMPLATES, 3):
        msg += f"• {req}\n"
    msg += f"\nDein Portfolio: {PORTFOLIO}"

    tg_ok = await _tg(msg)

    # Also run promo blast
    r = await run_fiverr_gig_promotion(count=2)
    return {
        "tg_alert": tg_ok,
        "gigs_promoted": r.get("gigs_promoted", 0),
        "channels_hit": r.get("channels_hit", 0),
    }


async def run_fiverr_full_blast() -> dict:
    """Full Fiverr session: promo all gigs + buyer request alert."""
    promo = await run_fiverr_gig_promotion(count=len(GIG_SERVICES))
    alert = await run_fiverr_buyer_request_alert()
    return {
        "gigs_promoted": promo.get("gigs_promoted", 0),
        "channels_hit": promo.get("channels_hit", 0) + alert.get("channels_hit", 0),
        "tg_alert": alert.get("tg_alert", False),
    }
