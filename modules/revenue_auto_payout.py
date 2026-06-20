#!/usr/bin/env python3
"""
Revenue Auto-Payout & Reporting — vollautomatisch.
Täglich: aggregiert Revenue (Shopify+Stripe+DS24+Affiliate) → Supabase.
Meilensteine: Telegram-Alert + BrutusCore-Blast.
Wöchentlich: Report als Telegram-Nachricht.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import aiohttp

log = logging.getLogger("RevenueAutoPayout")

STRIPE_KEY     = os.getenv("STRIPE_SECRET_KEY", "")
SHOP           = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOK    = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
DS24_KEY       = os.getenv("DS24_API_KEY", "1682000-T8KjTRJXCO1IgXOU5I7am6p6a0AZuqV2BGswDECY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

MILESTONES = [100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]


async def _telegram(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


async def _fetch_shopify_revenue(days: int = 30) -> float:
    if not SHOP or not SHOPIFY_TOK:
        return 0.0
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOP}/admin/api/{SHOPIFY_VER}/orders.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOK},
                params={"status": "any", "financial_status": "paid",
                        "created_at_min": since, "limit": "250"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
        orders = data.get("orders", [])
        return sum(float(o.get("total_price", 0)) for o in orders)
    except Exception:
        return 0.0


async def _fetch_stripe_revenue(days: int = 30) -> float:
    if not STRIPE_KEY:
        return 0.0
    try:
        since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.stripe.com/v1/charges",
                headers={"Authorization": f"Bearer {STRIPE_KEY}"},
                params={"limit": "100", "created[gte]": str(since)},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
        charges = data.get("data", [])
        return sum(c.get("amount", 0) for c in charges if c.get("paid")) / 100
    except Exception:
        return 0.0


async def _fetch_ds24_revenue() -> float:
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("ds24_purchases").select("price").execute()
        return sum(float(r.get("price", 0) or 0) for r in (rows.data or []))
    except Exception:
        return 0.0


async def _fetch_affiliate_revenue() -> float:
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("affiliate_clicks").select("commission_earned").execute()
        return sum(float(r.get("commission_earned", 0) or 0) for r in (rows.data or []))
    except Exception:
        return 0.0


async def _get_last_milestone(total: float) -> float:
    """Höchster erreichter Meilenstein."""
    reached = [m for m in MILESTONES if m <= total]
    return reached[-1] if reached else 0.0


async def _load_prev_milestone() -> float:
    try:
        from modules.supabase_client import get_client
        row = get_client().table("agent_memory").select("value").eq(
            "key", "revenue_last_milestone").execute()
        if row.data:
            return float(row.data[0].get("value", 0))
    except Exception:
        pass
    return 0.0


async def _save_milestone(milestone: float) -> None:
    try:
        from modules.supabase_client import get_client
        get_client().table("agent_memory").upsert({
            "key":        "revenue_last_milestone",
            "value":      str(milestone),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception:
        pass


async def aggregate_revenue(days: int = 7) -> dict:
    """Alle Revenue-Quellen aggregieren."""
    shopify, stripe_rev, ds24, affiliate = await asyncio.gather(
        _fetch_shopify_revenue(days),
        _fetch_stripe_revenue(days),
        _fetch_ds24_revenue(),
        _fetch_affiliate_revenue(),
        return_exceptions=True,
    )
    shopify   = shopify   if isinstance(shopify, float)   else 0.0
    stripe_rev= stripe_rev if isinstance(stripe_rev, float) else 0.0
    ds24      = ds24      if isinstance(ds24, float)      else 0.0
    affiliate = affiliate if isinstance(affiliate, float) else 0.0

    total = shopify + stripe_rev + ds24 + affiliate

    snapshot = {
        "date":       datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "shopify":    round(shopify, 2),
        "stripe":     round(stripe_rev, 2),
        "ds24":       round(ds24, 2),
        "affiliate":  round(affiliate, 2),
        "total":      round(total, 2),
        "period_days": days,
    }

    try:
        from modules.supabase_client import get_client
        get_client().table("revenue_snapshots").insert(snapshot).execute()
    except Exception:
        pass

    return snapshot


async def check_milestones(snapshot: dict) -> dict:
    """Prüft ob neue Revenue-Meilensteine erreicht wurden."""
    total           = snapshot.get("total", 0)
    current_ms      = await _get_last_milestone(total)
    prev_ms         = await _load_prev_milestone()

    if current_ms > prev_ms and current_ms > 0:
        await _save_milestone(current_ms)
        msg = (
            f"🏆 <b>MEILENSTEIN ERREICHT!</b>\n"
            f"€{current_ms:,.0f} Gesamtumsatz!\n"
            f"Shopify: €{snapshot.get('shopify',0):.2f}\n"
            f"Stripe: €{snapshot.get('stripe',0):.2f}\n"
            f"DS24: €{snapshot.get('ds24',0):.2f}\n"
            f"Affiliate: €{snapshot.get('affiliate',0):.2f}"
        )
        await _telegram(msg)
        try:
            from modules.brutus_core import fire
            await fire(
                f"🏆 Meilenstein: €{current_ms:,.0f} Umsatz!",
                f"Gesamtumsatz: €{total:.2f} — Meilenstein €{current_ms:,.0f} erreicht!",
                channels=["telegram", "slack", "discord"],
            )
        except Exception:
            pass
        return {"milestone_reached": current_ms, "prev": prev_ms}

    return {"milestone_reached": None, "current": total}


async def run_daily_revenue_report() -> dict:
    """Täglich: aggregieren + Meilenstein-Check."""
    snapshot = await aggregate_revenue(days=1)
    milestone = await check_milestones(snapshot)

    await _telegram(
        f"📊 <b>Tages-Revenue-Report</b>\n"
        f"Shopify: €{snapshot['shopify']:.2f}\n"
        f"Stripe: €{snapshot['stripe']:.2f}\n"
        f"DS24: €{snapshot['ds24']:.2f}\n"
        f"Affiliate: €{snapshot['affiliate']:.2f}\n"
        f"<b>Gesamt: €{snapshot['total']:.2f}</b>"
    )

    return {"ok": True, "snapshot": snapshot, "milestone": milestone}


async def run_weekly_report() -> dict:
    """Wöchentlich: 7-Tage Zusammenfassung."""
    snapshot = await aggregate_revenue(days=7)

    try:
        from modules.supabase_client import get_client
        rows = get_client().table("revenue_snapshots").select("*").order(
            "date", desc=True).limit(7).execute()
        history = rows.data or []
    except Exception:
        history = []

    days_line = "\n".join(
        f"{r.get('date','')}: €{r.get('total',0):.2f}"
        for r in history[:7]
    )

    await _telegram(
        f"📈 <b>7-Tage Revenue-Report</b>\n"
        f"Gesamt: €{snapshot['total']:.2f}\n"
        f"Ø pro Tag: €{snapshot['total']/7:.2f}\n\n"
        f"Tagesdetails:\n{days_line}"
    )

    return {"ok": True, "snapshot": snapshot, "days": len(history)}


async def get_revenue_stats() -> dict:
    """Live-Stats für Dashboard."""
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("revenue_snapshots").select("*").order(
            "date", desc=True).limit(30).execute()
        history = rows.data or []
    except Exception:
        history = []

    total_all = sum(float(r.get("total", 0)) for r in history)
    return {
        "ok":          True,
        "total_30d":   round(total_all, 2),
        "days_tracked": len(history),
        "last_7_days": history[:7],
        "next_milestone": next(
            (m for m in MILESTONES if m > total_all), None
        ),
    }


async def run_revenue_cycle() -> dict:
    """Scheduler-Einstiegspunkt (täglich)."""
    return await run_daily_revenue_report()


async def run_weekly_cycle() -> dict:
    """Scheduler-Einstiegspunkt (wöchentlich)."""
    return await run_weekly_report()
