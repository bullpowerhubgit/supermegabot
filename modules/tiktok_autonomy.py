#!/usr/bin/env python3
"""
TikTok Autonomy — TikTok Shop Sync, Video Scripts, Trending Hashtags.
Mit Token: Shopify → TikTok Shop. Ohne: KI Video-Scripts + Hashtag-Strategie via Telegram.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random

import aiohttp

log = logging.getLogger("TikTokAutonomy")

TIKTOK_KEY    = os.getenv("TIKTOK_APP_KEY", "")
TIKTOK_SECRET = os.getenv("TIKTOK_APP_SECRET", "")
TIKTOK_TOKEN  = os.getenv("TIKTOK_ACCESS_TOKEN", "")
TIKTOK_SHOP   = os.getenv("TIKTOK_SHOP_ID", "")
SHOP = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER   = os.getenv("SHOPIFY_API_VERSION", "2026-04")
SHOP_URL      = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
DS24_LINK     = os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/668035")

TRENDING_HASHTAGS_DE = [
    "#GeldVerdienen", "#PassivesEinkommen", "#OnlineMarketing", "#Dropshipping",
    "#ShopifyTipps", "#ECommerce", "#KIBusiness", "#AffiliateMarketing",
    "#DigitaleProdukte", "#FreelancerLeben", "#SideHustle", "#BusinessTipps",
    "#OnlineShop", "#WorkFromHome", "#FinanzielleFreiheit",
]

TIKTOK_NICHES = [
    "smart home gadgets", "fitness equipment", "kitchen tools",
    "desk accessories", "beauty tools", "outdoor gear",
    "pet accessories", "gaming peripherals", "passive income",
    "dropshipping tips",
]

VIDEO_FORMATS = [
    "Hook + Problem + Solution + CTA",
    "3 Secrets nobody tells you about {topic}",
    "Watch me make €{amount} with {topic} in {time}",
    "POV: You just discovered {topic}",
    "{number} {topic} hacks that actually work",
]


async def _ai(prompt: str, max_tokens: int = 500) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _tg_notify(text: str) -> None:
    """Direkte Telegram-Nachricht ohne BRUTUS-Abhängigkeit."""
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not tg_token or not tg_chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                json={"chat_id": tg_chat, "text": text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as exc:
        log.debug("_tg_notify error: %s", exc)


async def get_shopify_products(limit: int = 10) -> list:
    """Holt Shopify-Produkte für TikTok Sync."""
    if not SHOP or not SHOPIFY_TOKEN:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOP}/admin/api/{SHOPIFY_VER}/products.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                params={"limit": limit, "status": "active"},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                data = await r.json()
        return data.get("products", [])
    except Exception:
        return []


async def sync_products_to_tiktok() -> dict:
    """Shopify-Produkte → TikTok Shop (mit Token) oder Telegram-Report (ohne)."""
    products = await get_shopify_products(20)

    if TIKTOK_TOKEN and TIKTOK_SHOP:
        synced = 0
        for product in products[:10]:
            try:
                variant = (product.get("variants") or [{}])[0]
                price = variant.get("price", "29.99")
                image = (product.get("images") or [{}])[0].get("src", "")

                payload = {
                    "products": [{
                        "title": product.get("title", "")[:255],
                        "description": product.get("body_html", "")[:1000],
                        "price": {"amount": str(price), "currency": "EUR"},
                        "main_images": [{"url": image}] if image else [],
                    }]
                }
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        f"https://open-api.tiktok-shops.com/api/v1/products",
                        headers={"x-tts-access-token": TIKTOK_TOKEN,
                                 "Content-Type": "application/json"},
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as r:
                        if r.status < 300:
                            synced += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                log.debug("TikTok sync error: %s", e)
        return {"ok": True, "mode": "api", "synced": synced, "total": len(products)}

    # Ohne Token: Produkt-Promo via Telegram
    if products:
        titles = [p.get("title", "")[:40] for p in products[:5]]
        msg = f"📦 TikTok Shop Ready: {len(products)} Produkte warten\n" + "\n".join(f"• {t}" for t in titles)
        msg += f"\n\n🔗 Shop: {SHOP_URL}"
        try:
            from modules.brutus_core import fire
            await fire("TikTok Shop Produkte", msg, link=SHOP_URL, channels=["telegram"])
        except Exception as _e:
            log.debug("skipped: %s", _e)
    return {"ok": True, "mode": "promo_only", "products_ready": len(products),
            "note": "Set TIKTOK_ACCESS_TOKEN in Railway for TikTok Shop API"}


async def generate_video_scripts(niche: str = "", count: int = 3) -> dict:
    """KI generiert TikTok Video-Scripts für eine Nische."""
    target_niche = niche or random.choice(TIKTOK_NICHES)
    scripts = []

    for i in range(count):
        fmt = random.choice(VIDEO_FORMATS)
        prompt = f"""Schreibe ein TikTok Video-Script (60 Sekunden, Deutsch) zum Thema "{target_niche}".
Format: {fmt.format(topic=target_niche, amount=random.randint(100,500), time="24h", number=random.randint(3,7))}

Struktur:
🎬 HOOK (0-3 Sek): [Aufmerksamkeit sofort]
📖 CONTENT (3-50 Sek): [Wert liefern]
🎯 CTA (50-60 Sek): [Folgen + Link in Bio: {SHOP_URL}]

Hashtags: {' '.join(random.sample(TRENDING_HASHTAGS_DE, 5))}
Trennzeichen: ---"""
        script = await _ai(prompt, 350)
        if not script:
            script = f"Hook: Wusstest du das? {target_niche} kann dir €{random.randint(100,1000)}/Monat bringen!\nContent: Hier sind meine Top-Tipps...\nCTA: Folge mir für mehr! Link in Bio: {SHOP_URL}"
        scripts.append({"niche": target_niche, "format": fmt[:40], "script": script})
        await asyncio.sleep(1)

    # Scripts einzeln an Telegram senden (direkter Fallback ohne BRUTUS)
    header = (
        f"📱 *Neue TikTok Scripts bereit: {target_niche}*\n"
        f"Nische: `{target_niche}` | Anzahl: {len(scripts)}\n\n"
        f"Bitte manuell auf TikTok @aaiitecc posten:"
    )
    await _tg_notify(header)
    for idx, sc in enumerate(scripts, 1):
        msg = (
            f"*Script {idx}/{len(scripts)} — {sc['format'][:40]}*\n\n"
            f"{sc['script'][:1000]}"
        )
        await _tg_notify(msg)
        await asyncio.sleep(0.5)

    # Zusätzlich via BRUTUS (optionaler Kanal-Blast)
    try:
        from modules.brutus_core import fire
        await fire(
            f"TikTok Script: {target_niche}",
            scripts[0]["script"][:500] if scripts else "",
            link=SHOP_URL, channels=["telegram"]
        )
    except Exception as _e:
        log.debug("brutus blast skipped: %s", _e)

    return {"ok": True, "niche": target_niche, "scripts_generated": len(scripts), "scripts": scripts}


async def get_trending_hashtags(niche: str = "") -> dict:
    """Gibt trending TikTok Hashtags zurück."""
    target = niche or random.choice(TIKTOK_NICHES)
    niche_hashtags = {
        "smart home": ["#SmartHome", "#Alexa", "#SmartLiving", "#IoT", "#HomeAutomation"],
        "fitness": ["#Fitness", "#WorkoutMotivation", "#HomeWorkout", "#GymLife", "#FitTok"],
        "dropshipping": ["#Dropshipping", "#ECommerce", "#OnlineBusiness", "#Shopify", "#SideHustle"],
        "passive income": ["#PassiveIncome", "#FinancialFreedom", "#MakeMoneyOnline", "#Investing"],
    }
    hashtags = TRENDING_HASHTAGS_DE + niche_hashtags.get(target.lower(), [])
    selected = random.sample(hashtags, min(10, len(hashtags)))

    return {"ok": True, "niche": target, "hashtags": selected,
            "count": len(selected), "tip": f"Use in TikTok captions for {target} content"}


async def run_tiktok_cycle() -> dict:
    """Scheduler-Einstiegspunkt."""
    sync = await sync_products_to_tiktok()
    scripts = await generate_video_scripts(count=2)
    return {"ok": True, "sync": sync, "scripts": scripts.get("scripts_generated", 0)}


async def run_tiktok_autonomy(count: int = 3) -> dict:
    """
    Vollautonome TikTok-Promotion ohne Access-Token.
    Erstellt Video-Scripts aus Templates + blasted auf 6 Kanäle via BRUTUS.
    """
    niches = random.sample(TIKTOK_NICHES, min(count, len(TIKTOK_NICHES)))
    videos_scripted = 0
    channels_hit = 0

    _SCRIPT_TEMPLATES = [
        lambda n, ht: (
            f"🎵 Hook: Wusstest du das? {n} kann dir €{random.randint(200,1500)}/Monat bringen!\n\n"
            f"📖 Content: Mit dem richtigen System läuft alles automatisch. Kein Lager, kein Stress.\n\n"
            f"🎯 CTA: Folge mir! Shop: {SHOP_URL} | Digitales System: {DS24_LINK}\n\n"
            f"{ht}"
        ),
        lambda n, ht: (
            f"🔥 POV: Du entdeckst gerade die beste Business-Idee 2026 — {n}!\n\n"
            f"Schritt 1: System aufsetzen (einmalig 2h)\n"
            f"Schritt 2: KI übernimmt alles\n"
            f"Schritt 3: Geld verdienen während du schläfst\n\n"
            f"✅ Shop: {SHOP_URL} | Komplettes System (Digistore24): {DS24_LINK}\n{ht}"
        ),
        lambda n, ht: (
            f"💰 {random.randint(3,7)} {n} Hacks die wirklich funktionieren:\n\n"
            f"#1 Automatisierung — spare 20h/Woche\n"
            f"#2 KI-Content — 100 Posts/Tag ohne Arbeit\n"
            f"#3 Passives Einkommen — 24/7 aktiv\n\n"
            f"🔗 Shop: {SHOP_URL} | Kurs & System: {DS24_LINK}\n{ht}"
        ),
    ]

    for niche in niches:
        hashtags = random.sample(TRENDING_HASHTAGS_DE, 5)
        niche_ht = {
            "smart home gadgets": ["#SmartHome", "#Gadgets2026"],
            "fitness equipment": ["#Fitness", "#FitTok"],
            "passive income": ["#PassiveIncome", "#FinancialFreedom"],
            "dropshipping tips": ["#Dropshipping", "#Shopify"],
        }.get(niche, [])
        all_ht = " ".join(hashtags + niche_ht)

        script_fn = random.choice(_SCRIPT_TEMPLATES)
        script = script_fn(niche, all_ht)

        try:
            from modules.brutus_core import fire
            result = await fire(
                f"TikTok: {niche[:40]}",
                script,
                link=SHOP_URL,
                channels=["telegram", "mailchimp", "klaviyo", "twitter", "linkedin", "discord"],
            )
            channels_hit += result.get("channels_hit", 1)
            videos_scripted += 1
        except Exception as e:
            log.warning("run_tiktok_autonomy blast: %s", e)
        await asyncio.sleep(1)

    return {
        "ok": True,
        "videos_scripted": videos_scripted,
        "channels_hit": channels_hit,
        "niches": niches,
        "mode": "brutus_promotion",
    }
