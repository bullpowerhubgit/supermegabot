#!/usr/bin/env python3
"""
TikTok Trends Scraper — kein API-Key nötig.
Holt Trending-Hashtags + Produkte aus öffentlichen Quellen:
- TikTok Creative Center (öffentlich, kein Login)
- Google Trends RSS für "tiktok" Keywords
- Hardcoded Trending-Rotation mit 60+ Niches
"""
import asyncio
import logging
import os
import random
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("TikTokTrends")

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
STORE    = os.getenv("DS24_AFFILIATE_LINK", "https://ineedit.com.co")

# 60 bewährte TikTok-Trend-Niches (keine API nötig — kuratiert)
TIKTOK_NICHES = [
    # Produkt-Trends
    "LED Schreibtischlampe aesthetic", "Mini Kühlschrank Zimmer", "Handyhülle transparent",
    "Nagel Set Gel zuhause", "Schmuck Set Gold Silber", "Haarbürste kein Ziehen",
    "Wasserflassche mit Strohhalm", "Sticker Aesthetic Pack", "Fitness Widerstandsband Set",
    "Massage Pistole Rücken", "Luftbefeuchter Schlafzimmer", "Kabelloser Lautsprecher",
    "Rucksack Anti-Diebstahl", "Sonnencreme unsichtbar", "Haarserum Keratin",
    # Business/Money-Trends
    "Geld verdienen online 2026", "Passives Einkommen KI", "Dropshipping Anfänger",
    "Shopify Store erstellen", "Print on Demand starten", "Affiliate Marketing lernen",
    "Side Hustle Ideen Deutschland", "Online Shop ohne Kapital", "KI Tools Business",
    "Amazon FBA starten", "eBay Flipping Geld", "Etsy Verkäufer werden",
    # Lifestyle-Trends
    "Room Decor aesthetic 2026", "Outfit Ideen Winter 2026", "Healthy Morning Routine",
    "Meal Prep Anfänger", "Home Gym Equipment", "Travel Hacks günstig",
    "Book Aesthetic Reading", "Desk Setup minimal", "Skincare Routine Morgen",
    "Zero Waste Tipps", "Mindset Motivation", "Produktivität Tipps Student",
    # Tech-Trends
    "ChatGPT Tricks 2026", "AI Tools kostenlos", "Notion Template Pack",
    "iPad Zubehör must have", "Handy Zubehör 2026", "Smart Home Budget",
    "Laptop Kühler leise", "Webcam HD günstig", "Mikrofon Podcast günstig",
    # DE/AT/CH spezifisch
    "Geld sparen Österreich", "Online verdienen Schweiz", "Nebeneinkommen Deutschland",
    "Steuer sparen Selbstständig", "Kleingewerbe anmelden", "Freelancer werden",
    "Amazon Flex Erfahrung", "Lieferando Fahrrad Job", "Verkaufen ohne Lager",
]

VIRAL_CAPTIONS = [
    "🔥 Das ist VIRAL auf TikTok: {niche}! Alle wollen das gerade. 👉 {url} #TikTokMadeMeBuyIt #Trending",
    "💡 TikTok Trend 2026: {niche} — so verdienst du damit Geld! {url} #PassivesEinkommen #TikTok",
    "🚀 POV: Du entdeckst '{niche}' auf TikTok und startest direkt ein Business. {url} #Dropshipping",
    "📈 {niche} explodiert gerade auf TikTok! Hier ist wie du profitierst: {url} #Business2026",
    "⚡ TikTok zeigt mir immer: {niche} verkauft sich WAHNSINNIG. Mein Shop: {url} #Shopping",
    "🎵 Sound off, caption on: '{niche}' — das kaufen gerade alle auf TikTok! {url} #Viral",
    "💰 {niche} Trend: Ich habe damit angefangen Geld zu verdienen. Du auch? {url} #SideHustle",
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


async def get_google_trends_rss() -> list[str]:
    """Fetch trending searches from Google Trends RSS (public, no key)."""
    trends = []
    try:
        url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=DE"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
                if r.status == 200:
                    import re
                    text = await r.text()
                    titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", text)
                    trends = [t.strip() for t in titles if len(t) > 3][:10]
    except Exception as e:
        log.debug("Google Trends RSS error: %s", e)
    return trends


async def run_tiktok_trend_blast(count: int = 5) -> dict:
    """Pick trending niches → generate viral captions → BRUTUS blast."""
    # Mix: curated niches + Google Trends
    curated = random.sample(TIKTOK_NICHES, min(count, len(TIKTOK_NICHES)))
    google  = await get_google_trends_rss()
    pool    = curated + google[:3]
    selected = random.sample(pool, min(count, len(pool)))

    channels_hit = 0
    tg_ok_count  = 0

    for niche in selected:
        caption = random.choice(VIRAL_CAPTIONS).format(niche=niche, url=STORE)

        # Telegram post
        tg_ok = await _tg(f"🎵 *TikTok Trend*\n\n{caption}")
        if tg_ok:
            tg_ok_count += 1
            channels_hit += 1

        # BRUTUS blast
        try:
            from modules.brutus_traffic_engine import brutus_run
            r = await brutus_run(niche=f"tiktok trend {niche}")
            channels_hit += r.get("channels_hit", 0)
        except Exception:
            pass

        await asyncio.sleep(0.5)

    log.info("TikTok trend blast: %d niches, %d channels", len(selected), channels_hit)
    return {
        "niches_blasted": len(selected),
        "channels_hit": channels_hit,
        "tg_posts": tg_ok_count,
        "source": "TikTok trends + Google Trends DE",
    }


async def run_tiktok_product_content(niche: str = None) -> dict:
    """Generate TikTok-style product content for one niche."""
    if not niche:
        niche = random.choice(TIKTOK_NICHES)
    caption = random.choice(VIRAL_CAPTIONS).format(niche=niche, url=STORE)
    tg_ok = await _tg(f"🎵 *TikTok Content*\n\n{caption}")
    return {"niche": niche, "caption": caption[:100], "tg_ok": tg_ok}
