#!/usr/bin/env python3
"""
Fiverr Autonomy — Gig-Promotion, Content-Generierung, Portfolio-Blast.
Mit API-Key: echte Fiverr-Stats. Ohne: KI-Content + BrutusCore-Promotion.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random

import aiohttp

log = logging.getLogger("FiverrAutonomy")

FIVERR_KEY  = os.getenv("FIVERR_API_KEY", "")
FIVERR_USER = os.getenv("FIVERR_USERNAME", "bullpowerhub")
SHOP_URL    = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")

FIVERR_PROFILE = f"https://www.fiverr.com/{FIVERR_USER}"

GIG_CATEGORIES = [
    {"title": "I will build you a complete Shopify dropshipping store",
     "price": 150, "delivery": 3,
     "tags": ["shopify", "dropshipping", "ecommerce", "store setup"]},
    {"title": "I will create an AI-powered automation system for your business",
     "price": 200, "delivery": 5,
     "tags": ["automation", "ai", "python", "chatgpt", "workflow"]},
    {"title": "I will set up your complete email marketing funnel",
     "price": 100, "delivery": 2,
     "tags": ["email marketing", "klaviyo", "mailchimp", "funnel", "automation"]},
    {"title": "I will build a Telegram bot for your business",
     "price": 120, "delivery": 3,
     "tags": ["telegram", "bot", "python", "automation", "business"]},
    {"title": "I will create and optimize your Google Ads campaign",
     "price": 80, "delivery": 2,
     "tags": ["google ads", "ppc", "advertising", "marketing", "roi"]},
    {"title": "I will build your print-on-demand business with Printify",
     "price": 90, "delivery": 2,
     "tags": ["printify", "print on demand", "pod", "shopify", "passive income"]},
    {"title": "I will set up complete Amazon affiliate marketing system",
     "price": 130, "delivery": 3,
     "tags": ["amazon", "affiliate", "marketing", "passive income", "monetization"]},
]


async def _ai(prompt: str, max_tokens: int = 400) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def generate_gig_content(category: str = "") -> dict:
    """KI schreibt optimierte Fiverr-Gig-Beschreibungen."""
    gig = random.choice(GIG_CATEGORIES)
    prompt = f"""Schreibe eine überzeugende Fiverr-Gig-Beschreibung auf Englisch:
Titel: "{gig['title']}"
Preis: ${gig['price']}
Lieferzeit: {gig['delivery']} Tage

Format:
- Opening Hook (1 Satz, Attention-grabbing)
- Was du bekommst (3-4 Bullet Points mit ✅)
- Warum ich (2 Sätze Expertise)
- Call-to-Action

Max 150 Wörter. Professionell aber menschlich."""
    content = await _ai(prompt, 250)
    if not content:
        content = f"✅ Professional {gig['title']} — Fast delivery, quality guaranteed!\n\nOrder now for just ${gig['price']}."
    return {"ok": True, "gig": gig, "description": content}


async def promote_gigs(count: int = 3) -> dict:
    """Bewirbt Fiverr-Gigs auf allen verfügbaren Kanälen via BrutusCore."""
    promoted = 0
    gigs_to_promote = random.sample(GIG_CATEGORIES, min(count, len(GIG_CATEGORIES)))

    for gig in gigs_to_promote:
        try:
            prompt = f"""Kurzer Promotion-Post (Deutsch, 3 Sätze + Link) für:
Fiverr Gig: "{gig['title']}" — ab ${gig['price']}
Fiverr Profil: {FIVERR_PROFILE}
Schluss mit dem Link. Emojis OK."""
            post = await _ai(prompt, 120)
            if not post:
                post = f"💼 Neu auf Fiverr: {gig['title']}\nAb ${gig['price']} | {gig['delivery']} Tage Lieferzeit.\n👉 {FIVERR_PROFILE}"

            from modules.brutus_core import fire
            await fire(
                f"Fiverr Gig: {gig['title'][:50]}",
                post,
                link=FIVERR_PROFILE,
                channels=["telegram", "slack", "linkedin", "discord"],
            )
            promoted += 1
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("Fiverr promote error: %s", e)

    return {"ok": True, "promoted": promoted, "profile": FIVERR_PROFILE}


async def get_fiverr_status() -> dict:
    """Status des Fiverr-Moduls."""
    has_key = bool(FIVERR_KEY)
    return {
        "ok": True,
        "configured": has_key,
        "username": FIVERR_USER,
        "profile_url": FIVERR_PROFILE,
        "gigs_ready": len(GIG_CATEGORIES),
        "mode": "api" if has_key else "promotion_only",
        "note": "Set FIVERR_API_KEY in Railway for full API access" if not has_key else "API ready",
    }


async def run_fiverr_cycle() -> dict:
    """Scheduler-Einstiegspunkt."""
    promo = await promote_gigs(count=2)
    content = await generate_gig_content()
    return {"ok": True, "promoted": promo.get("promoted", 0),
            "gig_content_generated": content.get("ok")}
