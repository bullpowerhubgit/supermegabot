#!/usr/bin/env python3
"""
Revenue Fast Track — Shopify flash sales, Gumroad blast, DS24 mega blast (20 promo texts),
Amazon product blast, mini sales pages, multi-channel revenue spike.
Fully autonomous: runs without manual intervention.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

log = logging.getLogger("RevenueFastTrack")

SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
SHOP_URL = f"https://{SHOP_DOMAIN}"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER = os.getenv("SHOPIFY_API_VERSION", "2024-10")
DS24_URL = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
DS24_USER = os.getenv("DS24_USER_ID", "user37405262")
GUMROAD_TOKEN = os.getenv("GUMROAD_ACCESS_TOKEN", "")
AMAZON_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "bullpowerhub-21")
STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", "")

DS24_PROMO_TEXTS = [
    f"🔥 HEUTE GRATIS: Lerne wie du mit KI täglich €200+ verdienst → {DS24_URL}",
    f"💰 Passiveinkommen 2026: Die Methode die wirklich funktioniert → {DS24_URL}",
    f"⚡ JETZT STARTEN: Dein automatisiertes Business in 24h → {DS24_URL}",
    f"🚀 E-Commerce Automation: Shopify + KI + DS24 = Cashflow → {DS24_URL}",
    f"💼 Digitale Produkte verkaufen ohne Aufwand: Schritt-für-Schritt → {DS24_URL}",
    f"🎯 Affiliate Marketing 2026: Verdiene an fremden Produkten → {DS24_URL}",
    f"📈 KI Business Blueprint: Von €0 zu €5000/Monat → {DS24_URL}",
    f"🛒 Dropshipping mit KI: Welches Produkt wird der nächste Hit? → {DS24_URL}",
    f"💡 Print on Demand Geheimnis: Dein Shop läuft 24/7 → {DS24_URL}",
    f"🔑 Freiheit durch Online-Business: So geht's wirklich → {DS24_URL}",
    f"⭐ TOP-KURS 2026: €37 einmalig, lebenslange Einnahmen → {DS24_URL}",
    f"💎 Premium KI-Tools für deinen Shop: Alles inklusive → {DS24_URL}",
    f"📊 Täglich neue Kunden ohne Werbung: SEO-Automatisierung → {DS24_URL}",
    f"🌟 Erfolg mit digitalem Business: 500+ zufriedene Kunden → {DS24_URL}",
    f"🎪 FLASH DEAL: KI Income Machine für nur €37 → {DS24_URL}",
    f"💸 Amazon Affiliate + DS24 Combo = Maximaler Gewinn → {DS24_URL}",
    f"🏆 Bewährt: 3000+ Stunden KI-Research → 1 Kurs → {DS24_URL}",
    f"🔮 Zukunft ist automatisiert: Baue deinen AI-Bot heute → {DS24_URL}",
    f"📱 Mobile Business: Verwalte alles vom Handy → {DS24_URL}",
    f"🌍 Globaler Markt: Verkaufe in 30+ Länder gleichzeitig → {DS24_URL}",
]

AMAZON_HOT_PRODUCTS = [
    ("KI Business Automatisierung Bundle", "B09XJ2Y1MF"),
    ("Dropshipping Starter Kit 2026", "B08N5WRWNW"),
    ("Shopify Master Course", "B07VGQX5SK"),
    ("Print on Demand Guide", "B0BVWQ5X1N"),
    ("Affiliate Marketing Masterclass", "B08K2MXHQZ"),
    ("E-Commerce Tools 2026", "B0CK5WPXND"),
    ("Passive Income Blueprint", "B09R4XJLHG"),
]

FLASH_SALE_TOPICS = [
    "Weekend Flash Sale", "Montags-Deal", "Mittwochs-Angebot",
    "Freitags-Special", "KI-Business Deal", "48h Promo",
]


async def _ai(prompt: str, max_tokens: int = 500) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _tg(msg: str) -> None:
    try:
        from modules.telegram_hub_bridge import send_telegram_message
        await send_telegram_message(msg[:3500])
    except Exception:
        pass


async def shopify_flash_sale(discount_pct: int = 15) -> dict[str, Any]:
    if not SHOPIFY_TOKEN:
        return {"ok": False, "error": "no SHOPIFY_ADMIN_API_TOKEN"}
    try:
        headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
        sale_name = random.choice(FLASH_SALE_TOPICS)

        payload = {
            "price_rule": {
                "title": f"{sale_name} -{discount_pct}%",
                "target_type": "line_item",
                "target_selection": "all",
                "allocation_method": "across",
                "value_type": "percentage",
                "value": f"-{discount_pct}.0",
                "customer_selection": "all",
                "starts_at": datetime.now(timezone.utc).isoformat(),
                "ends_at": expires_at,
                "usage_limit": 200,
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://{SHOP_DOMAIN}/admin/api/{SHOPIFY_VER}/price_rules.json",
                json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                rule = data.get("price_rule", {})
                rule_id = rule.get("id")

                if not rule_id:
                    return {"ok": False, "error": data.get("errors", "price rule failed")}

                # Create discount code
                async with s.post(
                    f"https://{SHOP_DOMAIN}/admin/api/{SHOPIFY_VER}/price_rules/{rule_id}/discount_codes.json",
                    json={"discount_code": {"code": f"FLASH{discount_pct}NOW"}},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r2:
                    code_data = await r2.json()
                    code = code_data.get("discount_code", {}).get("code", f"FLASH{discount_pct}NOW")

        msg = (
            f"⚡ *Flash Sale aktiv: -{discount_pct}% auf ALLES!*\n"
            f"🎟️ Code: `{code}`\n"
            f"⏰ Gültig 48 Stunden\n"
            f"🛒 Shop: {SHOP_URL}"
        )
        await _tg(msg)
        log.info("Shopify flash sale created: %s, code=%s", sale_name, code)
        return {"ok": True, "rule_id": rule_id, "code": code, "discount": discount_pct, "expires": expires_at}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def gumroad_blast() -> dict[str, Any]:
    if not GUMROAD_TOKEN:
        return {"ok": False, "error": "no GUMROAD_ACCESS_TOKEN — set at gumroad.com/settings/advanced"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.gumroad.com/v2/products",
                params={"access_token": GUMROAD_TOKEN},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                products = data.get("products", [])

        if not products:
            return {"ok": False, "error": "no Gumroad products found"}

        blasted = []
        for product in products[:5]:
            name = product.get("name", "Produkt")
            url = product.get("short_url", product.get("url", ""))
            price = product.get("formatted_price", "")

            promo = random.choice(DS24_PROMO_TEXTS[:10])
            msg = (
                f"💎 *Gumroad: {name}* {price}\n"
                f"{promo}\n"
                f"🔗 {url}"
            )
            await _tg(msg)

            try:
                from modules.brutus_core import fire
                await fire(f"Gumroad: {name}", f"{name} {price} — {url}", channels=["telegram", "linkedin"])
            except Exception:
                pass

            blasted.append({"name": name, "url": url, "price": price})

        log.info("Gumroad blast: %d products", len(blasted))
        return {"ok": True, "blasted": len(blasted), "products": blasted}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def ds24_mega_blast(count: int = 20) -> dict[str, Any]:
    texts = DS24_PROMO_TEXTS[:count]
    sent = 0
    for i, text in enumerate(texts):
        try:
            if i > 0 and i % 5 == 0:
                await asyncio.sleep(2)

            await _tg(text)

            if i % 4 == 0:
                try:
                    from modules.brutus_core import fire
                    await fire(
                        "DS24 Affiliate Promo",
                        text,
                        channels=["telegram", "linkedin"] if i % 8 == 0 else ["telegram"],
                    )
                except Exception:
                    pass
            sent += 1
        except Exception as e:
            log.warning("DS24 blast text %d failed: %s", i, e)

    log.info("DS24 mega blast: %d/%d texts sent", sent, count)
    return {"ok": sent > 0, "sent": sent, "total": count}


async def amazon_product_blast() -> dict[str, Any]:
    blasted = []
    for name, asin in AMAZON_HOT_PRODUCTS[:5]:
        url = f"https://www.amazon.de/dp/{asin}?tag={AMAZON_TAG}"
        promo = random.choice(DS24_PROMO_TEXTS[10:])

        msg = (
            f"🛒 *Amazon Empfehlung: {name}*\n"
            f"{promo}\n"
            f"📦 Produkt: {url}"
        )
        await _tg(msg)
        blasted.append({"name": name, "asin": asin, "url": url})

    log.info("Amazon blast: %d products", len(blasted))
    return {"ok": True, "blasted": len(blasted), "products": blasted}


async def stripe_revenue_pulse() -> dict[str, Any]:
    if not STRIPE_KEY:
        return {"ok": False, "error": "no STRIPE_SECRET_KEY"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.stripe.com/v1/balance",
                auth=aiohttp.BasicAuth(STRIPE_KEY, ""),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json()
                available = data.get("available", [{}])
                pending = data.get("pending", [{}])
                avail_amount = sum(b.get("amount", 0) for b in available) / 100
                pend_amount = sum(b.get("amount", 0) for b in pending) / 100

        if avail_amount > 0 or pend_amount > 0:
            await _tg(
                f"💳 *Stripe Balance*\n"
                f"✅ Verfügbar: €{avail_amount:.2f}\n"
                f"⏳ Ausstehend: €{pend_amount:.2f}"
            )

        return {"ok": True, "available": avail_amount, "pending": pend_amount}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def run_revenue_fast_track() -> dict[str, Any]:
    if os.getenv("SOCIAL_POSTING_PAUSED", "").lower() in ("1", "true", "yes"):
        log.warning("RevenueFastTrack: SOCIAL_POSTING_PAUSED=true — übersprungen")
        return {"ok": False, "skipped": True, "reason": "SOCIAL_POSTING_PAUSED"}
    start = time.time()
    log.info("RevenueFastTrack cycle starting")

    flash_sale, gumroad, ds24_blast, amazon, stripe = await asyncio.gather(
        shopify_flash_sale(discount_pct=random.choice([10, 15, 20])),
        gumroad_blast(),
        ds24_mega_blast(count=20),
        amazon_product_blast(),
        stripe_revenue_pulse(),
        return_exceptions=True,
    )

    def _safe(r: Any) -> dict:
        return r if isinstance(r, dict) else {"ok": False, "error": str(r)}

    results = {
        "flash_sale": _safe(flash_sale),
        "gumroad": _safe(gumroad),
        "ds24_blast": _safe(ds24_blast),
        "amazon": _safe(amazon),
        "stripe": _safe(stripe),
    }

    elapsed = round(time.time() - start, 1)
    ok_count = sum(1 for v in results.values() if v.get("ok"))

    summary = (
        f"💰 *Revenue Fast Track fertig* ({elapsed}s)\n"
        f"✅ Systeme aktiv: {ok_count}/5\n"
        f"⚡ Flash Sale: {'✅ ' + str(results['flash_sale'].get('code','')) if results['flash_sale'].get('ok') else '❌'}\n"
        f"🎁 Gumroad: {'✅ ' + str(results['gumroad'].get('blasted',0)) + ' Produkte' if results['gumroad'].get('ok') else '❌'}\n"
        f"🚀 DS24: {'✅ ' + str(results['ds24_blast'].get('sent',0)) + ' Promos' if results['ds24_blast'].get('ok') else '❌'}\n"
        f"🛒 Amazon: {'✅ ' + str(results['amazon'].get('blasted',0)) + ' Produkte' if results['amazon'].get('ok') else '❌'}\n"
        f"💳 Stripe: {'✅ €' + str(results['stripe'].get('available',0)) if results['stripe'].get('ok') else '❌'}"
    )
    await _tg(summary)
    log.info("RevenueFastTrack done: %d/5 OK, elapsed=%.1fs", ok_count, elapsed)

    return {
        "ok": ok_count > 0,
        "channels_ok": ok_count,
        "results": results,
        "elapsed": elapsed,
    }
