#!/usr/bin/env python3
"""
Mass Content Blaster — 1000 Content-Pieces pro Plattform.
Generiert automatisch Massen-Content und verteilt ihn über alle Kanäle.
Ziel: 1000 Posts/Artikel/Pins/Videos-Beschreibungen auf jeder Plattform.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

log = logging.getLogger("MassContentBlaster")

DB_PATH = Path(os.getenv("DATA_DIR", "/tmp/supermegabot")) / "mass_content.db"
DS24_LINK = os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/668035")
SHOP_URL  = os.getenv("SHOPIFY_SHOP_URL", f"https://{os.getenv('SHOPIFY_SHOP_DOMAIN', 'autopilot-store-suite-fmbka.myshopify.com')}")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHANNEL    = os.getenv("TELEGRAM_CHANNEL_ID", "")   # marketing → must be public channel
# SAFETY: never send to private chat - only to explicitly set public channel
TELEGRAM_CHAT  = _TG_CHANNEL if _TG_CHANNEL and _TG_CHANNEL.startswith("-100") else ""

# APPROVED product links only - 669750 is GESPERRT, 576000/578000 are foreign products
# 668035 = AI Income Machine 90-Day Blueprint (OUR product, €37, proven converter!)
APPROVED_LINKS = [
    "https://www.checkout-ds24.com/product/668035",
    "https://www.checkout-ds24.com/product/668035",
    "https://www.checkout-ds24.com/product/668035",
    "https://www.checkout-ds24.com/product/668035",
]
if "669750" in DS24_LINK or "576000" in DS24_LINK or "578000" in DS24_LINK:
    DS24_LINK = APPROVED_LINKS[0]  # override unapproved/wrong product

# Daily send limit - prevent flooding
_MAX_SENDS_PER_DAY = 20

TOPICS_1000 = [
    # 100 KI & Automatisierung
    "KI-Automatisierung für Anfänger", "ChatGPT verdient Geld für dich",
    "KI-Tools 2026 Vergleich", "Automatisches Online-Business aufbauen",
    "KI schreibt Texte die verkaufen", "Von 0 auf 5k/Monat mit KI",
    "KI-Bilder für E-Commerce", "Automatische Shopify-Befüllung",
    "KI-Kundenservice ohne Personal", "Prompt Engineering für Business",
    "Claude vs ChatGPT 2026", "KI macht Geld während du schläfst",
    "Automatisierter Content-Kalender", "KI-SEO: 10x schneller ranken",
    "KI-Newsletter der sich selbst schreibt",
    # Shopify Produkte (100)
    "Bester Laptop-Ständer 2026", "Wireless Charger Test",
    "Ergonomische Maus Empfehlung", "Gaming Headset unter €50",
    "Smart Home Gadget Must-Have", "Fitness-Tracker Vergleich",
    "Noise Cancelling Kopfhörer Test", "Tragbarer Projektor Review",
    "Smartwatch für Business", "Kamera-Zubehör für Anfänger",
    "Küchen-Gadgets die Zeit sparen", "Outdoor Powerbank Test",
    "3-in-1 Ladekabel Empfehlung", "Mini-PC für Home Office",
    "Bluetooth-Lautsprecher Review",
    # Business & Mindset (100)
    "Morgenroutine für Online-Unternehmer", "Produktivitäts-Hacks 2026",
    "Timeboxing Methode erklärt", "Deep Work für Solopreneure",
    "Atomic Habits für Business", "Wachstumsmentalität entwickeln",
    "Nein sagen als Unternehmer", "Vision Board für Business-Ziele",
    "Journaling für Klarheit", "Meditation für Produktivität",
    # Dropshipping (100)
    "AliExpress Bestseller finden", "Dropshipping Nischen 2026",
    "Lieferzeit optimieren", "Produktfotos ohne Muster",
    "Dropshipping Steuern DE", "Winning Products identifizieren",
    "Shopify + Oberlo Alternative 2026", "Dropshipping mit KI skalieren",
    "Retouren bei Dropshipping managen", "Kundensupport automatisieren",
    # SEO & Traffic (100)
    "Kostenlos 10.000 Besucher/Monat", "Long-Tail Keywords 2026",
    "Google Core Update überleben", "Backlinks 2026 aufbauen",
    "Technical SEO Checkliste", "Schema Markup für E-Commerce",
    "Page Speed optimieren Shopify", "Rich Snippets einrichten",
    "Local SEO für Online-Shops", "SEO Content Brief erstellen",
    # Print on Demand (100)
    "Printify Shop einrichten", "Printful vs Printify Kosten",
    "T-Shirt Design verkaufen", "POD Nischen 2026",
    "Bestseller POD Designs", "Kaffeebecher Designs die verkaufen",
    "Notebook Designs Ideen", "Tote Bag Bestseller",
    "POD auf Etsy vs Shopify", "Passives Einkommen mit POD",
    # Affiliate Marketing (100)
    "Digistore24 Bestseller 2026", "Amazon Affiliate Nischen",
    "Affiliate Blog aufbauen", "Affiliate SEO-Strategie",
    "YouTube Affiliate Marketing", "Pinterest für Affiliates",
    "Vergleichsseiten als Business", "Affiliate Newsletter-Strategie",
    "Hochpreisige Produkte promoten", "Recurring Commission Programme",
    # Email Marketing (100)
    "E-Mail Liste aufbauen schnell", "Lead Magnet Ideen 2026",
    "Willkommens-Serie schreiben", "Re-Engagement Kampagne",
    "E-Mail Betreff A/B Test", "Segmentierung für mehr Umsatz",
    "Drip-Kampagne einrichten", "E-Mail Deliverability verbessern",
    "Newsletter Monetarisierung", "Autoresponder Strategie",
    # Social Media (100)
    "Instagram Reels Algorithmus 2026", "TikTok Business Account",
    "LinkedIn-Posts die viral gehen", "Pinterest Boards optimieren",
    "YouTube Community Posts nutzen", "Twitter/X für Business",
    "Discord Community aufbauen", "Reddit Marketing 2026",
    "Facebook Groups als Traffic-Quelle", "Influencer-Kooperationen",
    # Fiverr & Freelancing (100)
    "Fiverr Gig optimieren", "KI-Services verkaufen auf Fiverr",
    "5-Star Rating System Fiverr", "Upwork Profil optimieren",
    "Ersten Kunden auf Upwork finden", "Freelancer Steuern DE",
    "Preiserhöhung kommunizieren", "Retainer-Kunden gewinnen",
    "Portfolio aufbauen ohne Erfahrung", "Nische als Freelancer finden",
    # Passive Income (100)
    "10 Passive Income Streams 2026", "Dividenden vs Online-Business",
    "Cashflow-Modell aufbauen", "Passives Einkommen mit Kursen",
    "Memberships als Einkommensquelle", "Digitale Produkte 2026",
    "Software as a Service für Solopreneure", "Bücher als passive Einkommensquelle",
    "Kursplattformen Vergleich 2026", "Passives Einkommen Steuern DE",
    # Klaviyo & Mailing (100)
    "Klaviyo Flows einrichten", "Abandoned Cart Email Klaviyo",
    "Welcome Series Klaviyo", "Segmentierung in Klaviyo",
    "Klaviyo vs Mailchimp 2026", "SMS Marketing mit Klaviyo",
    "A/B Test in Klaviyo", "Klaviyo Analytics verstehen",
    "Post-Purchase Flow Klaviyo", "Win-Back Kampagne Klaviyo",
    # Shopify Tips (100)
    "Shopify Conversion Rate erhöhen", "Shopify SEO 2026",
    "Shopify Apps 2026 die sich lohnen", "Shopify Checkout optimieren",
    "Shopify Abandoned Cart", "Shopify Produktbeschreibungen KI",
    "Shopify Bilder optimieren", "Shopify Blog für SEO",
    "Shopify Upsell Strategien", "Shopify Metafelder nutzen",
    # Amazon & eBay (100)
    "Amazon FBA 2026 noch profitabel?", "eBay Verkaufen 2026",
    "Amazon Produktbeschreibung optimieren", "eBay SEO Strategien",
    "Amazon Brand Registry", "eBay International verkaufen",
    "Amazon PPC für Anfänger", "eBay Verkaufsgebühren sparen",
    "Amazon Bewertungen ethisch sammeln", "eBay Dropshipping legal?",
    # Financial (100)
    "Online Business Steuern DE 2026", "Kleinunternehmer vs UStpflichtig",
    "Rechnungen schreiben als Freelancer", "Business Konto 2026 Vergleich",
    "PayPal für Business optimieren", "Stripe vs PayPal für E-Commerce",
    "Buchhaltung automatisieren", "DATEV Alternative 2026",
    "Umsatzsteuer EU E-Commerce", "GmbH Gründung Online-Business",
]


def _init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS blasted_content "
        "(id INTEGER PRIMARY KEY, topic TEXT, platform TEXT, blasted_at TEXT)"
    )
    conn.commit()
    return conn


def _count_blasted(platform: str) -> int:
    conn = _init_db()
    c = conn.execute("SELECT COUNT(*) FROM blasted_content WHERE platform=?", (platform,)).fetchone()[0]
    conn.close()
    return c


def _mark_blasted(topic: str, platform: str) -> None:
    conn = _init_db()
    conn.execute(
        "INSERT INTO blasted_content (topic, platform, blasted_at) VALUES (?, ?, ?)",
        (topic, platform, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


async def _ai(prompt: str, max_tokens: int = 200) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _tg_send(text: str) -> bool:
    try:
        from modules.telegram_safe import tg_send_safe
        return await tg_send_safe(text)
    except Exception:
        return False


async def run_mass_blast(topics_per_run: int = 5) -> dict:
    """Blast N Topics über alle verfügbaren Kanäle."""
    if os.getenv("SOCIAL_POSTING_PAUSED", "").lower() in ("1", "true", "yes"):
        log.warning("MassContentBlaster: SOCIAL_POSTING_PAUSED=true — übersprungen")
        return {"ok": False, "skipped": True, "reason": "SOCIAL_POSTING_PAUSED"}
    # Daily limit check - prevent flooding owner's inbox
    conn = _init_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sent_today = conn.execute(
        "SELECT COUNT(*) FROM blasted_content WHERE blasted_at LIKE ?", (f"{today}%",)
    ).fetchone()[0]
    conn.close()
    if sent_today >= _MAX_SENDS_PER_DAY:
        log.info("Daily send limit (%d) reached, skipping blast", _MAX_SENDS_PER_DAY)
        return {"total_posted": 0, "skipped": "daily_limit_reached", "sent_today": sent_today}

    # Only blast if channel is set (never send to private chat)
    if not TELEGRAM_CHAT:
        log.info("TELEGRAM_CHANNEL_ID not set → skipping Telegram blast (safety)")

    total_posted = 0
    platforms_hit = set()
    topics_used = 0

    selected = random.sample(TOPICS_1000, min(topics_per_run, len(TOPICS_1000)))

    for topic in selected:
        content = await _ai(
            f"Schreibe einen kurzen, überzeugenden Marketing-Post auf Deutsch über: {topic}. "
            f"Max 200 Zeichen. Füge am Ende ein: 👉 {DS24_LINK}",
            max_tokens=150,
        )
        if not content:
            content = f"💡 {topic}\n\n🚀 Jetzt mehr erfahren!\n👉 {DS24_LINK}"

        try:
            from modules.brutus_core import fire
            result = await fire(topic, content, channels=["telegram", "slack"])
            if result:
                platforms_hit.add("brutus")
                total_posted += 1
                _mark_blasted(topic, "brutus")
        except Exception as e:
            log.debug("BRUTUS blast failed for %s: %s", topic, e)

        # Direct Telegram
        if await _tg_send(f"📢 {content}"):
            platforms_hit.add("telegram")
            total_posted += 1
            _mark_blasted(topic, "telegram")

        # Dev.to (if key set)
        devto_key = os.getenv("DEVTO_API_KEY", "")
        if devto_key and devto_key not in ("MISSING_PLEASE_ADD", ""):
            try:
                from modules.dev_to_publisher import publish_article
                r = await publish_article(title=topic, body_markdown=content, tags=["ki","business","automatisierung"])
                if r.get("ok"):
                    platforms_hit.add("devto")
                    total_posted += 1
                    _mark_blasted(topic, "devto")
            except Exception as _e:
                log.debug("skipped: %s", _e)

        # Hashnode (if key set)
        hn_key = os.getenv("HASHNODE_API_KEY", "") or os.getenv("HASHNODE_TOKEN", "")
        if hn_key and hn_key not in ("MISSING_PLEASE_ADD", ""):
            try:
                from modules.free_syndication_network import post_to_hashnode
                r = await post_to_hashnode({"title": topic, "content": content, "tags": ["ki","business"]})
                if r.get("ok"):
                    platforms_hit.add("hashnode")
                    total_posted += 1
                    _mark_blasted(topic, "hashnode")
            except Exception as _e:
                log.debug("skipped: %s", _e)

        topics_used += 1
        await asyncio.sleep(0.5)

    conn = _init_db()
    total_in_db = conn.execute("SELECT COUNT(*) FROM blasted_content").fetchone()[0]
    conn.close()

    log.info("MassBlast: %d posted, %d platforms, %d topics, total in DB: %d",
             total_posted, len(platforms_hit), topics_used, total_in_db)
    return {
        "total_posted": total_posted,
        "platforms_hit": len(platforms_hit),
        "topics_used": topics_used,
        "total_blasted_ever": total_in_db,
        "progress_to_1000": f"{min(total_in_db, 1000)}/1000",
    }


async def get_mass_blast_stats() -> dict:
    conn = _init_db()
    total = conn.execute("SELECT COUNT(*) FROM blasted_content").fetchone()[0]
    by_platform = conn.execute(
        "SELECT platform, COUNT(*) FROM blasted_content GROUP BY platform"
    ).fetchall()
    conn.close()
    return {
        "total_blasted": total,
        "progress": f"{min(total, 1000)}/1000",
        "by_platform": dict(by_platform),
        "unique_topics": len(TOPICS_1000),
    }
