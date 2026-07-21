#!/usr/bin/env python3
"""
Revenue Mega Tracker — Alle Einnahmequellen in einem Dashboard
==============================================================
Verfolgt alle Revenue-Streams:
- Shopify (Bestellungen via API)
- Digistore24 (Transaktionen via API)
- Stripe (Charges via API)
- Affiliate (DS24 Affiliate Links)
- Klaviyo / Mailchimp (Campaign Revenue Attribution)
- Supabase (historische Daten)

Täglicher Telegram-Bericht + Meilenstein-Alerts via BrutusCore.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp

log = logging.getLogger("RevenueMegaTracker")

# Credentials
SHOPIFY_SHOP    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER     = os.getenv("SHOPIFY_API_VERSION", "2026-04")
DS24_KEY        = os.getenv("DIGISTORE24_API_KEY", "")
DS24_BASE       = "https://www.digistore24.com/api/call"
STRIPE_KEY      = os.getenv("STRIPE_SECRET_KEY", "")
TELEGRAM_ID     = os.getenv("TELEGRAM_CHAT_ID", "")
SHOP_URL        = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")

# Meilenstein-Schwellen in EUR (jedes Mal wenn überschritten → Blast)
MILESTONES_EUR  = [100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]


async def _notify(msg: str):
    try:
        from modules.notify_hub import notify
        notify(msg)  # sync function — no await, no 'level' kwarg
    except Exception as _e:
        log.debug("skipped: %s", _e)


async def _fire(title: str, content: str) -> dict:
    try:
        from modules.brutus_core import fire
        return await fire(title, content, channels=["telegram", "slack", "discord"])
    except Exception as e:
        await _notify(f"{title}\n{content}")
        return {"ok": True, "fallback": True}


# ─── Shopify Revenue ──────────────────────────────────────────────────────────

async def get_shopify_revenue(days: int = 1) -> dict:
    """Holt Shopify-Umsatz der letzten N Tage."""
    if not SHOPIFY_SHOP or not SHOPIFY_TOKEN:
        return {"ok": False, "error": "no Shopify credentials", "total": 0.0, "orders": 0}
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
        url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_VER}/orders.json"
        params = {
            "status": "any",
            "financial_status": "paid",
            "created_at_min": since,
            "limit": 250,
        }
        total_revenue = 0.0
        order_count   = 0
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, params=params,
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                data = await r.json()
        orders = data.get("orders", [])
        for order in orders:
            total_revenue += float(order.get("total_price", 0) or 0)
            order_count   += 1
        return {"ok": True, "total": total_revenue, "orders": order_count,
                "currency": "EUR", "days": days, "source": "shopify"}
    except Exception as e:
        return {"ok": False, "error": str(e), "total": 0.0, "orders": 0, "source": "shopify"}


# ─── DS24 Revenue ─────────────────────────────────────────────────────────────

async def get_ds24_revenue(days: int = 1) -> dict:
    """Holt Digistore24-Umsatz der letzten N Tage."""
    if not DS24_KEY:
        return {"ok": False, "error": "no DS24 key", "total": 0.0, "source": "ds24"}
    try:
        headers = {"x-ds-api-key": DS24_KEY, "Content-Type": "application/json"}
        since   = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        url     = f"{DS24_BASE}/listTransactions"
        params  = {"date_from": since}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, params=params,
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                data = await r.json()
        txns = data.get("data", {}).get("transactions", []) if isinstance(data.get("data"), dict) else []
        if not txns and isinstance(data.get("data"), list):
            txns = data["data"]
        total = sum(float(t.get("amount", 0) or 0) for t in txns)
        return {"ok": True, "total": total, "transactions": len(txns),
                "currency": "EUR", "days": days, "source": "ds24"}
    except Exception as e:
        return {"ok": False, "error": str(e), "total": 0.0, "transactions": 0, "source": "ds24"}


# ─── Stripe Revenue ───────────────────────────────────────────────────────────

async def get_stripe_revenue(days: int = 1) -> dict:
    """Holt Stripe-Umsatz der letzten N Tage."""
    if not STRIPE_KEY:
        return {"ok": False, "error": "no Stripe key", "total": 0.0, "source": "stripe"}
    try:
        since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        headers = {"Authorization": f"Bearer {STRIPE_KEY}"}
        url     = "https://api.stripe.com/v1/charges"
        params  = {"created[gte]": since, "limit": 100}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, params=params,
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                data = await r.json()
        charges = data.get("data", [])
        total   = sum(c.get("amount", 0) / 100.0
                      for c in charges if c.get("paid") and not c.get("refunded"))
        return {"ok": True, "total": total, "charges": len(charges),
                "currency": "EUR", "days": days, "source": "stripe"}
    except Exception as e:
        return {"ok": False, "error": str(e), "total": 0.0, "source": "stripe"}


# ─── Affiliate Revenue (via DS24) ─────────────────────────────────────────────

async def get_affiliate_revenue(days: int = 1) -> dict:
    """Holt Affiliate-Provisionen der letzten N Tage."""
    if not DS24_KEY:
        return {"ok": False, "error": "no DS24 key", "total": 0.0, "source": "affiliate"}
    try:
        headers = {"x-ds-api-key": DS24_KEY, "Content-Type": "application/json"}
        since   = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        url     = f"{DS24_BASE}/getAffiliateEarnings"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, params={"date_from": since},
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json()
        total = float(data.get("data", {}).get("total_earnings", 0) or 0)
        return {"ok": True, "total": total, "currency": "EUR", "days": days, "source": "affiliate"}
    except Exception as e:
        return {"ok": False, "error": str(e), "total": 0.0, "source": "affiliate"}


# ─── Supabase Revenue-Log ─────────────────────────────────────────────────────

async def save_revenue_snapshot(snapshot: dict) -> None:
    """Speichert Revenue-Snapshot in Supabase."""
    try:
        from modules.supabase_client import get_client
        get_client().table("revenue_snapshots").insert({
            "date": snapshot.get("date"),
            "shopify_total":   snapshot.get("shopify", {}).get("total", 0),
            "ds24_total":      snapshot.get("ds24", {}).get("total", 0),
            "stripe_total":    snapshot.get("stripe", {}).get("total", 0),
            "affiliate_total": snapshot.get("affiliate", {}).get("total", 0),
            "grand_total":     snapshot.get("grand_total", 0),
            "created_at":      datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.warning("save_revenue_snapshot error: %s", e)


async def get_revenue_history(days: int = 30) -> list[dict]:
    """Holt historische Revenue-Daten aus Supabase."""
    try:
        from modules.supabase_client import get_client
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = get_client().table("revenue_snapshots")\
            .select("*")\
            .gte("created_at", since)\
            .order("created_at", desc=True)\
            .limit(100)\
            .execute()
        return rows.data or []
    except Exception:
        return []


# ─── Meilenstein-Checker ──────────────────────────────────────────────────────

async def check_milestones(today_total: float, prev_milestone_key: str = "revenue_last_milestone") -> None:
    """Prüft ob Meilenstein erreicht und feuert Blast."""
    try:
        from modules.supabase_client import get_client
        # Letzten gespeicherten Meilenstein aus Supabase holen
        r = get_client().table("agent_memory")\
            .select("value")\
            .eq("key", prev_milestone_key)\
            .limit(1)\
            .execute()
        last_milestone = float((r.data or [{}])[0].get("value", 0))
    except Exception:
        last_milestone = 0.0

    for ms in MILESTONES_EUR:
        if today_total >= ms > last_milestone:
            await _fire(
                f"🏆 €{ms:,.0f} Meilenstein erreicht!",
                f"💰 Gesamt-Umsatz heute: €{today_total:,.2f}\n"
                f"🎯 Meilenstein €{ms:,.0f} wurde überschritten!\n"
                f"📈 Weiter so! Nächstes Ziel: €{next((m for m in MILESTONES_EUR if m > ms), ms * 2):,.0f}"
            )
            try:
                from modules.supabase_client import get_client
                get_client().table("agent_memory").upsert(
                    {"key": prev_milestone_key, "value": str(ms)},
                    on_conflict="key"
                ).execute()
            except Exception as _e:
                log.debug("skipped: %s", _e)
            break


# ─── Tägtlicher Revenue Report ────────────────────────────────────────────────

async def generate_daily_revenue_report(days: int = 1) -> dict:
    """Holt alle Revenue-Quellen, konsolidiert und sendet Telegram-Report."""
    log.info("Generating daily revenue report (last %d day(s))...", days)

    # Alle Quellen parallel abfragen
    results = await asyncio.gather(
        get_shopify_revenue(days),
        get_ds24_revenue(days),
        get_stripe_revenue(days),
        get_affiliate_revenue(days),
        return_exceptions=True,
    )
    shopify   = results[0] if not isinstance(results[0], Exception) else {"total": 0.0, "ok": False}
    ds24      = results[1] if not isinstance(results[1], Exception) else {"total": 0.0, "ok": False}
    stripe    = results[2] if not isinstance(results[2], Exception) else {"total": 0.0, "ok": False}
    affiliate = results[3] if not isinstance(results[3], Exception) else {"total": 0.0, "ok": False}

    grand_total = (
        shopify.get("total", 0) + ds24.get("total", 0)
        + stripe.get("total", 0) + affiliate.get("total", 0)
    )

    period  = "Heute" if days == 1 else f"Letzte {days} Tage"
    date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M") + " UTC"

    report = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "period": period,
        "shopify": shopify,
        "ds24": ds24,
        "stripe": stripe,
        "affiliate": affiliate,
        "grand_total": grand_total,
        "timestamp": date_str,
    }

    # Supabase Snapshot
    await save_revenue_snapshot(report)

    # Meilenstein-Check
    await check_milestones(grand_total)

    # Telegram-Report
    msg_lines = [
        f"💰 *Revenue Report — {period}*",
        f"📅 {date_str}\n",
        f"🛍️ Shopify:    €{shopify.get('total', 0):>9,.2f}",
        f"📦 DS24:       €{ds24.get('total', 0):>9,.2f}",
        f"💳 Stripe:     €{stripe.get('total', 0):>9,.2f}",
        f"🔗 Affiliate:  €{affiliate.get('total', 0):>9,.2f}",
        f"{'─'*30}",
        f"💎 GESAMT:     €{grand_total:>9,.2f}",
    ]

    # Fehler-Hinweise
    errors = []
    for src, data in [("Shopify", shopify), ("DS24", ds24), ("Stripe", stripe), ("Affiliate", affiliate)]:
        if not data.get("ok"):
            errors.append(f"⚠️ {src}: {data.get('error', 'error')[:40]}")
    if errors:
        msg_lines.append("\n" + "\n".join(errors))

    msg = "\n".join(msg_lines)
    await _fire(f"💰 Revenue {period}: €{grand_total:,.2f}", msg)

    log.info("Revenue report done: Grand Total = €%.2f", grand_total)
    return report


# ─── Live Revenue Monitor ─────────────────────────────────────────────────────

async def get_current_revenue_snapshot() -> dict:
    """Schneller Snapshot aller Revenue-Quellen für Dashboard."""
    r7 = await asyncio.gather(
        get_shopify_revenue(7),
        get_ds24_revenue(7),
        get_stripe_revenue(7),
        get_affiliate_revenue(7),
        return_exceptions=True,
    )
    shopify7   = r7[0] if not isinstance(r7[0], Exception) else {"total": 0.0}
    ds24_7     = r7[1] if not isinstance(r7[1], Exception) else {"total": 0.0}
    stripe7    = r7[2] if not isinstance(r7[2], Exception) else {"total": 0.0}
    affiliate7 = r7[3] if not isinstance(r7[3], Exception) else {"total": 0.0}

    total_7d = (shopify7.get("total", 0) + ds24_7.get("total", 0)
                + stripe7.get("total", 0) + affiliate7.get("total", 0))

    history = await get_revenue_history(30)

    return {
        "ok": True,
        "last_7_days": {
            "shopify":   shopify7.get("total", 0),
            "ds24":      ds24_7.get("total", 0),
            "stripe":    stripe7.get("total", 0),
            "affiliate": affiliate7.get("total", 0),
            "total":     total_7d,
        },
        "history_30d": history[:30],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Scheduler Entry Points ───────────────────────────────────────────────────

async def run_revenue_tracker_cycle() -> dict:
    """Täglich: Revenue-Report generieren + senden."""
    report = await generate_daily_revenue_report(days=1)
    return {"ok": True, "grand_total": report.get("grand_total", 0),
            "report_date": report.get("date")}


async def run_revenue_weekly() -> dict:
    """Wöchentlich: 7-Tage Revenue Report."""
    report = await generate_daily_revenue_report(days=7)
    return {"ok": True, "grand_total_7d": report.get("grand_total", 0)}


async def get_revenue_stats() -> dict:
    """Status-Endpoint für Dashboard."""
    return await get_current_revenue_snapshot()
