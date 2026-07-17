#!/usr/bin/env python3
"""
Monetization Engine — Vollautomatische Umsatz-Maschine
=======================================================
Koordiniert alle Revenue-Streams:
  1. BPI Services auf allen Social-Kanälen (12 Produkte × 6 Kanäle)
  2. B2B Email-Outreach (100 Kalt-Emails/Tag an Multiplikatoren)
  3. Shopify Traffic-Blast (TikTok + Social + BRUTUS)
  4. DS24 Affiliate-Promotion
  5. Revenue-Report via Telegram

Scheduler: täglich 08:00 + 14:00 + 20:00
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any

import aiohttp

log = logging.getLogger("MonetizationEngine")

_TG_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
_PUBLIC_DOMAIN = (os.getenv("SHOPIFY_PUBLIC_DOMAIN") or "ineedit.com.co").strip().removeprefix("https://").removeprefix("http://").strip("/")
_SHOP_URL  = os.getenv("SHOPIFY_SHOP_URL", f"https://{_PUBLIC_DOMAIN}")
_STRIPE_SK = os.getenv("STRIPE_SECRET_KEY", "")

# ── BPI Service Katalog ────────────────────────────────────────────────────────

BPI_SERVICES = [
    {
        "key":     "shopify_texts",
        "name":    "Shopify KI-Texte",
        "emoji":   "🛒",
        "price":   "€79 einmalig",
        "target":  "Online-Shop-Besitzer",
        "value":   "50 professionelle Produktbeschreibungen in 48h — SEO-optimiert, kaufsteigernd",
        "stripe":  "https://buy.stripe.com/fZu00lgM2a660c8eF84F33B",
        "channels": ["telegram", "twitter", "linkedin", "discord"],
    },
    {
        "key":     "stellenanzeigen",
        "name":    "Stellenanzeigen KI",
        "emoji":   "💼",
        "price":   "€99 einmalig",
        "target":  "HR-Abteilungen, Personalvermittler",
        "value":   "10 überzeugende Stellenanzeigen in 48h — mehr Bewerbungen, weniger Aufwand",
        "stripe":  "https://buy.stripe.com/3cIcN7cvMfqqcYU40u4F33C",
        "channels": ["telegram", "linkedin", "twitter"],
    },
    {
        "key":     "gastro_texte",
        "name":    "Hotel & Gastro Texte",
        "emoji":   "🍽️",
        "price":   "€149 einmalig",
        "target":  "Hotels, Restaurants, Cafés",
        "value":   "Website + Zimmer + Menü + Bewertungsantworten — alles KI-generiert in 48h",
        "stripe":  "https://buy.stripe.com/dRm5kF0N4cee7EAaoS4F33D",
        "channels": ["telegram", "instagram", "linkedin"],
    },
    {
        "key":     "kfz_texte",
        "name":    "Kfz-Händler Texte",
        "emoji":   "🚗",
        "price":   "€99 einmalig",
        "target":  "Kfz-Händler, Autoverkäufer",
        "value":   "50 Fahrzeugtexte in 48h — mehr Klicks, mehr Probefahrten, mehr Verkäufe",
        "stripe":  "https://buy.stripe.com/4gMfZj7bs5PQ7EA2Wq4F33E",
        "channels": ["telegram", "twitter", "linkedin"],
    },
    {
        "key":     "handwerker_angebote",
        "name":    "Handwerker Angebots-KI",
        "emoji":   "🔧",
        "price":   "€79 einmalig",
        "target":  "Handwerker, Installateure, Bauunternehmer",
        "value":   "30 professionelle Angebotsschreiben — gewinnen Sie mehr Aufträge ohne Schreibstress",
        "stripe":  "https://buy.stripe.com/00w6oJanE5PQgb68gK4F33F",
        "channels": ["telegram", "linkedin", "twitter"],
    },
    {
        "key":     "makler_ki",
        "name":    "Makler Angebots-KI",
        "emoji":   "🏠",
        "price":   "€129 einmalig",
        "target":  "Immobilienmakler, Versicherungsmakler",
        "value":   "20 personalisierte Anschreiben + Exposé-Texte in 48h — mehr Abschlüsse",
        "stripe":  "https://buy.stripe.com/bJe5kF2VcguuaQM0Oi4F33G",
        "channels": ["telegram", "linkedin"],
    },
    {
        "key":     "rechtstexte",
        "name":    "Rechtstexte KI",
        "emoji":   "⚖️",
        "price":   "€49 einmalig",
        "target":  "Online-Shops, Startups, Selbstständige",
        "value":   "Impressum + AGB + Datenschutz — rechtssicher, DSGVO-konform, sofort einsatzbereit",
        "stripe":  "https://buy.stripe.com/5kQdRb9jA5PQ9MI1Sm4F33H",
        "channels": ["telegram", "twitter", "linkedin", "discord"],
    },
    {
        "key":     "mna_expose",
        "name":    "Unternehmensverkauf-Exposé",
        "emoji":   "📊",
        "price":   "€499 einmalig",
        "target":  "Unternehmer, M&A-Berater, Investoren",
        "value":   "5 professionelle M&A-Dokumente in 48h — Executive Summary, Teaser, IM und mehr",
        "stripe":  "https://buy.stripe.com/4gMfZjgM27XYcYU1Sm4F33I",
        "channels": ["telegram", "linkedin"],
    },
    {
        "key":     "fitness_content",
        "name":    "Fitness Content KI",
        "emoji":   "💪",
        "price":   "€69/Monat",
        "target":  "Fitnessstudios, Personal Trainer, Coaches",
        "value":   "30 Social Posts + Newsletter pro Monat — vollautomatisch, immer aktuell",
        "stripe":  "https://buy.stripe.com/7sY9AVbrIguuaQM2Wq4F33J",
        "channels": ["telegram", "instagram", "twitter"],
    },
    {
        "key":     "social_kalender",
        "name":    "Social Kalender KI",
        "emoji":   "📅",
        "price":   "€69/Monat",
        "target":  "KMU, Agenturen, Selbstständige",
        "value":   "30 fertige Social-Posts + 2 Newsletter/Monat — nie wieder leere Kanäle",
        "stripe":  "https://buy.stripe.com/5kQ7sN9jA4LMe2YaoS4F33K",
        "channels": ["telegram", "linkedin", "twitter", "discord"],
    },
    {
        "key":     "steuerberater_newsletter",
        "name":    "Steuerberater Newsletter KI",
        "emoji":   "📧",
        "price":   "€149/Monat",
        "target":  "Steuerberaterkanzleien",
        "value":   "100 personalisierte Mandanten-Newsletter/Monat — vollautomatisch, DSGVO-konform",
        "stripe":  "https://buy.stripe.com/dRm6oJgM23HIe2YgNg4F33L",
        "channels": ["telegram", "linkedin"],
    },
    {
        "key":     "mieterbrief_ki",
        "name":    "Mieterbrief KI",
        "emoji":   "🏢",
        "price":   "€249/Monat",
        "target":  "Hausverwaltungen, Wohnungsbaugesellschaften",
        "value":   "Unbegrenzte Mieterbriefe, Kündigungen, Nebenkostenabrechnungen — automatisch",
        "stripe":  "https://buy.stripe.com/6oUeVf8fw5PQ5wsfJc4F33M",
        "channels": ["telegram", "linkedin"],
    },
]

# ── Amazon Affiliate Produkte ──────────────────────────────────────────────────

AMAZON_TAG = "bullpowerhub-21"

AMAZON_PRODUCTS = [
    {
        "key":      "ai_income_machine",
        "name":     "AI Income Machine – 90-Day Blueprint",
        "emoji":    "🤖",
        "category": "KI & E-Commerce Automation",
        "hook":     "Ein 90-Tage-Plan fuer KI-gestuetzte Angebote, Content und skalierbare Prozesse",
        "target":   "Online-Unternehmer, Freelancer und Teams mit Fokus auf Automation",
        "bullets": [
            "Schritt-fuer-Schritt Blueprint: 90 Tage, Tag fuer Tag",
            "KI-Tools fuer Content, Angebote und operative Ablaeufe",
            "Saubere Automations-Setups statt Hype-Versprechen",
            "Direkt umsetzbar fuer kleine Teams und Solo-Operatoren",
        ],
        "link":     f"https://www.amazon.de/s?k=AI+Income+Machine+90-Day+Blueprint&tag={AMAZON_TAG}",
        "channels": ["telegram", "twitter", "linkedin", "tiktok", "discord"],
    },
]

# ── Helpers ────────────────────────────────────────────────────────────────────

async def _tg(msg: str) -> None:
    if not _TG_TOKEN or not _TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
                json={"chat_id": _TG_CHAT, "text": msg[:4096], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.debug("Telegram skip: %s", e)


async def _brutus(title: str, body: str, link: str, channels: list) -> dict:
    try:
        from modules.brutus_core import fire
        return await fire(title, body, link=link, channels=channels)
    except Exception as e:
        log.debug("BRUTUS skip: %s", e)
        return {}


async def _stripe_revenue() -> dict:
    if not _STRIPE_SK:
        return {}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.stripe.com/v1/balance",
                auth=aiohttp.BasicAuth(_STRIPE_SK, ""),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                bal = await r.json()
            async with s.get(
                "https://api.stripe.com/v1/charges",
                auth=aiohttp.BasicAuth(_STRIPE_SK, ""),
                params={"limit": 10, "created[gte]": int(
                    (datetime.now(timezone.utc).timestamp()) - 86400 * 7
                )},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                charges = await r.json()
        available = sum(
            b.get("amount", 0) for b in bal.get("available", [])
            if b.get("currency", "eur") == "eur"
        ) / 100
        week_revenue = sum(
            c.get("amount", 0) for c in charges.get("data", [])
            if c.get("paid") and not c.get("refunded")
        ) / 100
        return {"available_eur": available, "week_revenue_eur": week_revenue}
    except Exception as e:
        log.debug("Stripe revenue skip: %s", e)
        return {}


# ── Core Actions ───────────────────────────────────────────────────────────────

async def blast_bpi_service(svc: dict, slot: int = 0) -> dict:
    """Postet einen BPI Service auf allen konfigurierten Kanälen."""
    name    = svc["name"]
    emoji   = svc["emoji"]
    price   = svc["price"]
    target  = svc["target"]
    value   = svc["value"]
    stripe  = svc["stripe"]
    channels = svc.get("channels", ["telegram"])

    # Varianten für Abwechslung (kein Copy-Paste-Spam)
    intros = [
        f"Neu für {target}:",
        f"Problem gelöst für {target}:",
        f"Jetzt verfügbar — {name}:",
        f"{target} aufgepasst:",
        f"Spare Stunden pro Woche —",
    ]
    intro = intros[slot % len(intros)]

    body = (
        f"{emoji} <b>{name} — {price}</b>\n\n"
        f"{intro}\n{value}\n\n"
        f"✅ Lieferung in 48h\n"
        f"✅ Kein Abo-Zwang (außer Monatsprodukte)\n"
        f"✅ 100% KI-generiert, sofort einsatzbereit\n\n"
        f"👉 Jetzt bestellen: {stripe}"
    )

    result = await _brutus(f"{emoji} {name}", body, stripe, channels)
    log.info("BPI blast: %s → channels=%s", name, channels)
    return {"service": name, "channels_hit": result.get("channels_hit", 0)}


async def run_bpi_daily_blast(limit: int = 4) -> dict:
    """Postet täglich bis zu `limit` BPI Services (rotierend, keine Wiederholung)."""
    hour  = datetime.now(timezone.utc).hour
    slot  = hour // 6  # 0–3 → 4 Rotations/Tag
    start = (slot * limit) % len(BPI_SERVICES)
    batch = (BPI_SERVICES + BPI_SERVICES)[start:start + limit]

    tasks   = [blast_bpi_service(svc, slot + i) for i, svc in enumerate(batch)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    hits    = sum(r.get("channels_hit", 0) for r in results if isinstance(r, dict))
    return {
        "ok": True,
        "services_posted": len(batch),
        "channels_hit": hits,
        "services": [s["name"] for s in batch],
    }


async def blast_amazon_product(prod: dict, variant: int = 0) -> dict:
    """Postet ein Amazon-Affiliate-Produkt auf allen Kanälen."""
    name     = prod["name"]
    emoji    = prod["emoji"]
    hook     = prod["hook"]
    bullets  = prod["bullets"]
    link     = prod["link"]
    channels = prod.get("channels", ["telegram", "twitter"])

    bullet_str = "\n".join(f"✅ {b}" for b in bullets)

    # 3 Textvarianten — verhindert Shadow-Ban durch identische Posts
    variants = [
        (
            f"{emoji} <b>{name}</b>\n\n"
            f"{hook}\n\n"
            f"{bullet_str}\n\n"
            f"👉 Auf Amazon: {link}"
        ),
        (
            f"📚 Buchtipp: <b>{name}</b>\n\n"
            f"Warum lesen?\n{bullet_str}\n\n"
            f"💰 Amazon Bestseller → {link}"
        ),
        (
            f"🔥 {hook}\n\n"
            f"<b>{name}</b>\n{bullet_str}\n\n"
            f"➡️ Jetzt auf Amazon: {link}"
        ),
    ]

    body   = variants[variant % len(variants)]
    result = await _brutus(f"{emoji} {name}", body, link, channels)
    log.info("Amazon affiliate blast: %s → channels=%s", name, channels)
    return {
        "ok": True,
        "product": name,
        "link": link,
        "channels_hit": result.get("channels_hit", 0),
    }


async def run_amazon_affiliate_blast() -> dict:
    """Blast alle Amazon Affiliate Produkte auf allen Kanälen."""
    hour    = datetime.now(timezone.utc).hour
    results = []
    for i, prod in enumerate(AMAZON_PRODUCTS):
        r = await blast_amazon_product(prod, variant=hour + i)
        results.append(r)
        if i < len(AMAZON_PRODUCTS) - 1:
            await asyncio.sleep(2)
    hits = sum(r.get("channels_hit", 0) for r in results)
    return {
        "ok": True,
        "products_blasted": len(results),
        "channels_hit": hits,
        "products": [r["product"] for r in results],
    }


async def run_email_outreach(daily_limit: int = 100) -> dict:
    """Startet SYS-10 Bulk-Outreach: 100 Kalt-Emails an Multiplikatoren."""
    try:
        from modules.email_outreach_bulk import run_outreach
        result = await run_outreach(daily_limit=daily_limit)
        sent   = result.get("sent", 0)
        log.info("Email outreach: %d Emails versendet", sent)
        return {"ok": True, "emails_sent": sent, **result}
    except Exception as e:
        log.warning("Email outreach Fehler: %s", e)
        return {"ok": False, "error": str(e)}


async def run_shopify_traffic_blast() -> dict:
    """Shopify Shop auf allen Kanälen promoten."""
    niches = ["Smart Home Gadgets", "Solar & Energie", "Shopify Automation", "Smarte Sicherheit"]
    niche  = random.choice(niches)

    msg = (
        f"🛒 <b>Online Shop — Top {niche} 2026</b>\n\n"
        f"13.400+ Produkte — versandkostenfrei ab €29\n"
        f"Täglich neue Arrivals aus EU-Lagern\n\n"
        f"🔥 Jetzt stöbern: {_SHOP_URL}"
    )
    result = await _brutus(
        f"Shop: {niche}",
        msg,
        _SHOP_URL,
        ["telegram", "twitter", "discord"],
    )
    return {"ok": True, "niche": niche, "channels_hit": result.get("channels_hit", 0)}


async def run_tiktok_content_blast() -> dict:
    """TikTok Content für Shopify + BPI auf allen Kanälen."""
    try:
        from modules.tiktok_autonomy import run_tiktok_cycle
        r = await run_tiktok_cycle()
        return {"ok": True, "tiktok": r}
    except Exception as e:
        log.debug("TikTok blast: %s", e)
        return {"ok": False, "error": str(e)}


async def run_revenue_report() -> dict:
    """Holt aktuellen Revenue von Stripe + Shopify + DS24, sendet Telegram-Report."""
    stripe_data = await _stripe_revenue()

    # DS24 Revenue
    ds24_revenue = 0.0
    try:
        from modules.digistore24_client import get_revenue_summary
        ds = await get_revenue_summary()
        ds24_revenue = float(ds.get("total_revenue", 0) or 0)
    except Exception:
        pass

    # Shopify Revenue (letzte 7 Tage)
    shopify_revenue = 0.0
    try:
        shop   = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        token  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        ver    = os.getenv("SHOPIFY_API_VERSION", "2026-04")
        if shop and token:
            from datetime import timedelta
            since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://{shop}/admin/api/{ver}/orders.json",
                    headers={"X-Shopify-Access-Token": token},
                    params={"status": "paid", "created_at_min": since,
                            "fields": "total_price", "limit": 250},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    data = await r.json(content_type=None)
            shopify_revenue = sum(float(o.get("total_price", 0) or 0)
                                  for o in data.get("orders", []))
    except Exception:
        pass

    stripe_week    = stripe_data.get("week_revenue_eur", 0)
    stripe_balance = stripe_data.get("available_eur", 0)
    total_week     = round(stripe_week + ds24_revenue + shopify_revenue, 2)

    report = (
        f"💰 <b>Revenue Report — {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC</b>\n\n"
        f"📦 Shopify 7T: <b>€{shopify_revenue:.2f}</b>\n"
        f"💳 Stripe 7T: <b>€{stripe_week:.2f}</b>\n"
        f"🏪 DS24: <b>€{ds24_revenue:.2f}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 Gesamt 7T: <b>€{total_week:.2f}</b>\n"
        f"🏦 Stripe Balance: €{stripe_balance:.2f}\n\n"
        f"🚀 Monetization Engine läuft — BPI Services aktiv"
    )
    await _tg(report)

    return {
        "ok": True,
        "week_revenue_eur": total_week,
        "stripe_week": stripe_week,
        "stripe_balance": stripe_balance,
        "ds24": ds24_revenue,
        "shopify_7d": shopify_revenue,
    }


# ── Master Launch ──────────────────────────────────────────────────────────────

async def launch_monetization(
    *,
    bpi: bool = True,
    email: bool = True,
    shopify: bool = True,
    tiktok: bool = True,
    report: bool = True,
) -> dict:
    """
    Haupt-Einstiegspunkt: startet alle Revenue-Engines parallel.
    Wird vom Scheduler 3× täglich aufgerufen.
    """
    ts = datetime.now(timezone.utc).isoformat()
    log.info("Monetization launch — %s", ts)

    await _tg(
        f"🚀 <b>Monetization Engine startet</b>\n"
        f"Zeit: {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
        f"BPI Blast: {'✅' if bpi else '—'} | Email: {'✅' if email else '—'} | "
        f"Shopify: {'✅' if shopify else '—'} | TikTok: {'✅' if tiktok else '—'}"
    )

    tasks: dict[str, Any] = {}

    async def _run(key: str, coro):
        try:
            tasks[key] = await coro
        except Exception as e:
            tasks[key] = {"ok": False, "error": str(e)[:120]}

    coros = []
    if bpi:
        coros.append(_run("bpi", run_bpi_daily_blast(limit=4)))
    if shopify:
        coros.append(_run("shopify", run_shopify_traffic_blast()))
    if tiktok:
        coros.append(_run("tiktok", run_tiktok_content_blast()))
    # Amazon Affiliate immer mitlaufen lassen
    coros.append(_run("amazon", run_amazon_affiliate_blast()))

    # Parallel: BPI + Shopify + TikTok + Amazon
    await asyncio.gather(*coros)

    # Sequential: Email (rate-limited) + Revenue Report
    if email:
        await _run("email", run_email_outreach(daily_limit=100))
    if report:
        await _run("revenue", run_revenue_report())

    bpi_r     = tasks.get("bpi", {})
    email_r   = tasks.get("email", {})
    shopify_r = tasks.get("shopify", {})
    amazon_r  = tasks.get("amazon", {})

    summary = (
        f"✅ <b>Monetization Launch abgeschlossen</b>\n\n"
        f"📣 BPI Services gepostet: {bpi_r.get('services_posted', 0)}\n"
        f"🤖 Amazon Affiliate: {amazon_r.get('products_blasted', 0)} Produkte → {amazon_r.get('channels_hit', 0)} Kanäle\n"
        f"📧 Emails versendet: {email_r.get('emails_sent', 0)}\n"
        f"🛒 Shopify Blast: {'OK' if shopify_r.get('ok') else 'skip'}\n"
        f"💰 7T Revenue: €{tasks.get('revenue', {}).get('week_revenue_eur', 0):.2f}"
    )
    await _tg(summary)

    return {
        "ok": True,
        "timestamp": ts,
        "results": tasks,
    }


async def run_monetization_cycle() -> dict:
    """Scheduler-Einstiegspunkt (task_monetization_launch)."""
    return await launch_monetization()
