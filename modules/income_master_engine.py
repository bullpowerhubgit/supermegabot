"""
Income Master Engine — Zentrales Einkommens-Kontrollzentrum
===========================================================
Koordiniert alle Revenue-Streams, misst Echtzeit-Umsatz,
sendet tägliche Reports und aktiviert alle Einkommensquellen.

Scheduler: alle 30min run_income_cycle()
Täglich 20:00: send_telegram_revenue_report()
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

log = logging.getLogger("IncomeMaster")

# ── Credentials ───────────────────────────────────────────────────────────────
STRIPE_KEY      = os.getenv("STRIPE_SECRET_KEY", "")
DS24_KEY        = os.getenv("DS24_API_KEY", "")
SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
KLAVIYO_KEY     = os.getenv("KLAVIYO_API_KEY", "")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
TELEGRAM_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
META_TOKEN      = os.getenv("META_ADS_TOKEN", "")
META_ACCOUNT    = os.getenv("META_AD_ACCOUNT_ID", "act_878505274898620")

_last_total: float = 0.0  # für Telegram-Alert bei neuen Sales
_report_sent_date: str = ""


async def _tg(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text[:4096], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram error: %s", e)


# ── Revenue Pull ──────────────────────────────────────────────────────────────

async def _stripe_today() -> float:
    if not STRIPE_KEY:
        return 0.0
    today_ts = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.stripe.com/v1/payment_intents",
                params={"limit": 100, "created[gte]": str(today_ts)},
                headers={"Authorization": f"Bearer {STRIPE_KEY}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                return sum(
                    p["amount"] / 100
                    for p in data.get("data", [])
                    if p.get("status") == "succeeded" and p.get("currency", "").upper() == "EUR"
                )
    except Exception as e:
        log.warning("Stripe check error: %s", e)
        return 0.0


async def _ds24_today() -> float:
    if not DS24_KEY:
        return 0.0
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://www.digistore24.com/api/v1/{DS24_KEY}/json/listSalesOfPeriod/today",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                items = data.get("data", {}).get("sales", [])
                return sum(float(item.get("earnings_net", 0)) for item in items)
    except Exception as e:
        log.warning("DS24 check error: %s", e)
        return 0.0


async def _shopify_today() -> dict:
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {"revenue": 0.0, "orders": 0}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/2024-01/orders.json",
                params={"status": "any", "created_at_min": today, "limit": 250},
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                orders = data.get("orders", [])
                revenue = sum(float(o.get("total_price", 0)) for o in orders if o.get("financial_status") in ("paid", "partially_paid"))
                return {"revenue": revenue, "orders": len(orders)}
    except Exception as e:
        log.warning("Shopify check error: %s", e)
        return {"revenue": 0.0, "orders": 0}


async def _klaviyo_subscribers() -> int:
    if not KLAVIYO_KEY:
        return 0
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://a.klaviyo.com/api/lists/",
                headers={"Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}", "revision": "2024-02-15"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json()
                return sum(l.get("attributes", {}).get("profile_count", 0) for l in data.get("data", []))
    except Exception as e:
        log.warning("Klaviyo check error: %s", e)
        return 0


async def _meta_spend_today() -> float:
    if not META_TOKEN:
        return 0.0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://graph.facebook.com/v20.0/{META_ACCOUNT}/insights",
                params={
                    "fields": "spend",
                    "time_range": json.dumps({"since": today, "until": today}),
                    "access_token": META_TOKEN,
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json()
                rows = data.get("data", [])
                return sum(float(row.get("spend", 0)) for row in rows)
    except Exception as e:
        log.warning("Meta spend check error: %s", e)
        return 0.0


# ── Public API ────────────────────────────────────────────────────────────────

async def get_live_revenue() -> dict:
    """Echtzeit-Umsatz aller Kanäle."""
    stripe, ds24, shopify_data, subs, meta_spend = await asyncio.gather(
        _stripe_today(),
        _ds24_today(),
        _shopify_today(),
        _klaviyo_subscribers(),
        _meta_spend_today(),
        return_exceptions=True,
    )
    stripe = stripe if isinstance(stripe, float) else 0.0
    ds24   = ds24   if isinstance(ds24,   float) else 0.0
    shopify_data = shopify_data if isinstance(shopify_data, dict) else {"revenue": 0.0, "orders": 0}
    subs   = subs   if isinstance(subs,   int)   else 0
    meta_spend = meta_spend if isinstance(meta_spend, float) else 0.0

    total = stripe + ds24 + shopify_data["revenue"]
    return {
        "stripe":           stripe,
        "ds24":             ds24,
        "shopify":          shopify_data["revenue"],
        "shopify_orders":   shopify_data["orders"],
        "total_eur":        total,
        "klaviyo_subs":     subs,
        "meta_spend_eur":   meta_spend,
        "roas":             round(total / meta_spend, 2) if meta_spend > 0 else 0.0,
        "ts":               datetime.now(timezone.utc).isoformat(),
    }


async def run_income_cycle() -> dict:
    """Hauptzyklus — alle 30min. Koordiniert alle Einkommensquellen."""
    global _last_total

    revenue = await get_live_revenue()
    total = revenue["total_eur"]

    # Telegram-Alert nur bei neuem Sale
    if total > _last_total and total > 0:
        diff = total - _last_total
        await _tg(
            f"💰 NEUER SALE! +{diff:.2f}€\n"
            f"Stripe: {revenue['stripe']:.2f}€ | DS24: {revenue['ds24']:.2f}€ | Shopify: {revenue['shopify']:.2f}€\n"
            f"Gesamt heute: {total:.2f}€ | ROAS: {revenue['roas']}x | "
            f"Subscribers: {revenue['klaviyo_subs']}"
        )
    _last_total = total

    log.info(
        "Income Cycle: €%.2f heute (Stripe=%.2f DS24=%.2f Shop=%.2f) | Meta Spend: €%.2f | Subs: %d",
        total, revenue["stripe"], revenue["ds24"], revenue["shopify"],
        revenue["meta_spend_eur"], revenue["klaviyo_subs"],
    )
    return revenue


async def activate_all_revenue_streams() -> dict:
    """Aktiviert SOFORT alle Revenue-Streams — einmalig aufrufen."""
    from modules.agent_coordinator import run as coord_run

    results = {}

    async def _safe(name: str, coro):
        try:
            results[name] = await coro
        except Exception as e:
            results[name] = f"error: {e}"
            log.warning("%s error: %s", name, e)

    tasks = []

    async with coord_run("ds24_blast", "income_master", ttl=3600) as ctx:
        if not ctx.already_running:
            try:
                from modules.ds24_income_blaster import run_affiliate_blast_now
                tasks.append(_safe("ds24_blast", run_affiliate_blast_now()))
            except ImportError:
                results["ds24_blast"] = "module not yet available"

    async with coord_run("traffic_blast", "income_master", ttl=900) as ctx:
        if not ctx.already_running:
            try:
                from modules.traffic_maximizer import run_full_traffic_blast
                tasks.append(_safe("traffic_blast", run_full_traffic_blast()))
            except ImportError:
                results["traffic_blast"] = "module not yet available"

    async with coord_run("roas_cycle", "income_master", ttl=3600) as ctx:
        if not ctx.already_running:
            try:
                from modules.roas_optimizer import run_roas_cycle
                tasks.append(_safe("roas", run_roas_cycle()))
            except ImportError:
                results["roas"] = "module not yet available"

    try:
        from modules.sales_funnel_closer import process_email_queue
        tasks.append(_safe("email_queue", process_email_queue()))
    except ImportError:
        results["email_queue"] = "module not yet available"

    if tasks:
        await asyncio.gather(*tasks)

    await _tg(
        "🚀 Alle Revenue-Streams aktiviert!\n" +
        "\n".join(f"  {'✅' if 'error' not in str(v) else '⚠️'} {k}: {v}" for k, v in results.items())
    )
    return results


async def send_telegram_revenue_report() -> None:
    """Täglicher Revenue-Report — täglich um 20:00 aufrufen."""
    global _report_sent_date
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _report_sent_date == today:
        return
    _report_sent_date = today

    revenue = await get_live_revenue()
    text = (
        f"📊 <b>Tages-Report {today}</b>\n\n"
        f"💳 Stripe:   <b>{revenue['stripe']:.2f}€</b>\n"
        f"🛒 DS24:     <b>{revenue['ds24']:.2f}€</b>\n"
        f"🏪 Shopify:  <b>{revenue['shopify']:.2f}€</b> ({revenue['shopify_orders']} Orders)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 GESAMT:   <b>{revenue['total_eur']:.2f}€</b>\n\n"
        f"📈 Meta Ads Spend: {revenue['meta_spend_eur']:.2f}€ | ROAS: {revenue['roas']}x\n"
        f"📧 Klaviyo Subs:   {revenue['klaviyo_subs']}"
    )
    await _tg(text)
    log.info("Tages-Report gesendet: %.2f€ gesamt", revenue["total_eur"])
