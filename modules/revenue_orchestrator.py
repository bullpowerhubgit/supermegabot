"""
Revenue Orchestrator — central autonomous revenue coordinator for ineedit.com.co.
Aggregates all channels (Shopify, Meta Ads, TikTok, Pinterest, Email, SEO),
calculates ROAS, reallocates budgets to top performers, sends daily Telegram report.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import aiohttp

log = logging.getLogger("RevenueOrchestrator")

SHOP          = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOK      = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOP_VER      = os.getenv("SHOPIFY_API_VERSION", "2026-04")
KLAVIYO_KEY   = os.getenv("KLAVIYO_API_KEY", "")
META_TOKEN    = os.getenv("META_ACCESS_TOKEN", "")
META_ACCOUNT  = os.getenv("META_AD_ACCOUNT_ID_INEEDIT") or os.getenv("META_AD_ACCOUNT_ID", "")
TK_TOKEN      = os.getenv("TIKTOK_ACCESS_TOKEN", "")
TK_ADV        = os.getenv("TIKTOK_ADVERTISER_ID", "")
TG_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT       = os.getenv("TELEGRAM_CHAT_ID", "")
SHOP_URL      = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")


async def _tg(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg[:4096]},
            )
    except Exception:
        pass


async def _get_shopify_revenue_7d() -> dict:
    """Shopify orders total revenue last 7 days."""
    if not SHOP or not SHOP_TOK:
        return {"revenue": 0.0, "orders": 0}
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(
                f"https://{SHOP}/admin/api/{SHOP_VER}/orders.json",
                headers={"X-Shopify-Access-Token": SHOP_TOK},
                params={"created_at_min": since, "status": "any", "limit": 250,
                        "fields": "total_price,financial_status"},
            ) as r:
                if r.status == 200:
                    orders = (await r.json()).get("orders", [])
                    paid = [o for o in orders if o.get("financial_status") in ("paid", "partially_paid")]
                    revenue = sum(float(o.get("total_price", 0)) for o in paid)
                    return {"revenue": round(revenue, 2), "orders": len(paid)}
    except Exception as e:
        log.warning("Shopify revenue: %s", e)
    return {"revenue": 0.0, "orders": 0}


async def _get_meta_spend_7d() -> dict:
    """Meta Ads spend last 7 days."""
    if not META_TOKEN or not META_ACCOUNT:
        return {"spend": 0.0, "clicks": 0, "impressions": 0}
    account_id = META_ACCOUNT if META_ACCOUNT.startswith("act_") else f"act_{META_ACCOUNT}"
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(
                f"https://graph.facebook.com/v21.0/{account_id}/insights",
                params={
                    "access_token": META_TOKEN,
                    "fields": "spend,clicks,impressions",
                    "time_range": f'{{"since":"{start}","until":"{end}"}}',
                    "level": "account",
                },
            ) as r:
                data = await r.json()
        row = (data.get("data") or [{}])[0]
        return {
            "spend": round(float(row.get("spend", 0)), 2),
            "clicks": int(row.get("clicks", 0)),
            "impressions": int(row.get("impressions", 0)),
        }
    except Exception as e:
        log.warning("Meta spend: %s", e)
    return {"spend": 0.0, "clicks": 0, "impressions": 0}


async def _get_tiktok_spend_7d() -> dict:
    """TikTok Ads spend last 7 days."""
    if not TK_TOKEN or not TK_ADV:
        return {"spend": 0.0, "clicks": 0}
    try:
        from modules.tiktok_ads_engine import get_insights
        r = await get_insights(days=7)
        return {"spend": r.get("total_spend", 0.0), "clicks": r.get("total_clicks", 0)}
    except Exception as e:
        log.warning("TikTok spend: %s", e)
    return {"spend": 0.0, "clicks": 0}


async def _get_klaviyo_sent_today() -> int:
    """Klaviyo emails sent today (campaigns)."""
    if not KLAVIYO_KEY:
        return 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(
                "https://a.klaviyo.com/api/campaigns/",
                headers={"Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
                         "revision": "2024-10-15"},
                params={"filter": f"equals(status,'sent'),greater-or-equal(updated_at,{today}T00:00:00Z)"},
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return len(data.get("data", []))
    except Exception as e:
        log.debug("Klaviyo campaigns: %s", e)
    return 0


async def _get_seo_articles_today() -> int:
    """SEO articles published to Shopify blog today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        from modules.seo_mega_engine import _supa_get
        rows = await _supa_get("seo_content", f"select=id&created_at=gte.{today}&limit=100")
        return len(rows)
    except Exception:
        return 0


async def _get_pinterest_pins_today() -> int:
    """Pinterest pins created today (from local counter if available)."""
    try:
        import json
        from pathlib import Path
        p = Path("/app/data/pinterest_pins_today.json")
        if p.exists():
            d = json.loads(p.read_text())
            if d.get("date") == datetime.now(timezone.utc).strftime("%Y-%m-%d"):
                return d.get("count", 0)
    except Exception:
        pass
    return 0


async def get_all_revenue_stats() -> dict:
    """Gather stats from all revenue channels concurrently."""
    shopify, meta, tiktok, klaviyo_sent, seo_articles, pins = await asyncio.gather(
        _get_shopify_revenue_7d(),
        _get_meta_spend_7d(),
        _get_tiktok_spend_7d(),
        _get_klaviyo_sent_today(),
        _get_seo_articles_today(),
        _get_pinterest_pins_today(),
        return_exceptions=True,
    )

    def _safe(v, default):
        return v if not isinstance(v, Exception) else default

    shopify = _safe(shopify, {"revenue": 0.0, "orders": 0})
    meta = _safe(meta, {"spend": 0.0, "clicks": 0, "impressions": 0})
    tiktok = _safe(tiktok, {"spend": 0.0, "clicks": 0})
    klaviyo_sent = _safe(klaviyo_sent, 0)
    seo_articles = _safe(seo_articles, 0)
    pins = _safe(pins, 0)

    return {
        "shopify": shopify,
        "meta_ads": meta,
        "tiktok_ads": tiktok,
        "emails_sent_today": klaviyo_sent,
        "seo_articles_today": seo_articles,
        "pinterest_pins_today": pins,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def calculate_roas(stats: dict) -> dict:
    """Calculate ROAS per channel."""
    revenue = stats.get("shopify", {}).get("revenue", 0.0)
    meta_spend = stats.get("meta_ads", {}).get("spend", 0.0)
    tiktok_spend = stats.get("tiktok_ads", {}).get("spend", 0.0)
    total_spend = meta_spend + tiktok_spend

    return {
        "total_revenue_7d": revenue,
        "total_ad_spend_7d": total_spend,
        "overall_roas": round(revenue / max(total_spend, 0.01), 2),
        "meta_roas": round(revenue / max(meta_spend, 0.01), 2) if meta_spend > 0 else None,
        "tiktok_roas": round(revenue / max(tiktok_spend, 0.01), 2) if tiktok_spend > 0 else None,
    }


async def optimize_budget_allocation(total_budget: float = 50.0, stats: dict | None = None) -> dict:
    """
    Allocate total_budget across Meta and TikTok based on ROAS.
    Returns recommended daily spend per channel.
    """
    if stats is None:
        stats = await get_all_revenue_stats()
    roas = calculate_roas(stats)

    meta_roas = roas.get("meta_roas") or 1.0
    tiktok_roas = roas.get("tiktok_roas") or 1.0

    total_roas = meta_roas + tiktok_roas
    meta_share = meta_roas / total_roas
    tiktok_share = tiktok_roas / total_roas

    allocation = {
        "total_budget": total_budget,
        "meta_daily": round(total_budget * meta_share, 2),
        "tiktok_daily": round(total_budget * tiktok_share, 2),
        "meta_roas": meta_roas,
        "tiktok_roas": tiktok_roas,
        "recommendation": "meta" if meta_roas >= tiktok_roas else "tiktok",
    }
    log.info("Budget allocation: Meta €%s | TikTok €%s", allocation["meta_daily"], allocation["tiktok_daily"])
    return allocation


async def run_daily_revenue_report(stats: dict | None = None) -> dict:
    """Send comprehensive revenue Telegram report."""
    if stats is None:
        stats = await get_all_revenue_stats()
    roas = calculate_roas(stats)
    allocation = await optimize_budget_allocation(stats=stats)

    datum = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    revenue = stats["shopify"].get("revenue", 0)
    orders = stats["shopify"].get("orders", 0)
    meta_spend = stats["meta_ads"].get("spend", 0)
    meta_clicks = stats["meta_ads"].get("clicks", 0)
    tiktok_spend = stats["tiktok_ads"].get("spend", 0)
    emails = stats.get("emails_sent_today", 0)
    pins = stats.get("pinterest_pins_today", 0)
    articles = stats.get("seo_articles_today", 0)
    overall_roas = roas.get("overall_roas", 0)
    best_channel = allocation.get("recommendation", "meta").title()

    msg = (
        f"💰 REVENUE REPORT — {datum}\n\n"
        f"📦 Shop Umsatz (7 Tage): €{revenue:.2f} ({orders} Bestellungen)\n"
        f"📊 ROAS: {overall_roas}x\n"
        f"📧 Emails gesendet: {emails}\n"
        f"📌 Pinterest Pins: {pins}\n"
        f"🎯 Meta Ads: €{meta_spend:.2f} ausgegeben ({meta_clicks} Klicks)\n"
        f"📱 TikTok Ads: €{tiktok_spend:.2f}\n"
        f"📝 SEO Artikel heute: {articles}\n"
        f"🔥 Beste Channel: {best_channel}\n\n"
        f"💡 Empfehlung: Meta €{allocation['meta_daily']}/Tag | TikTok €{allocation['tiktok_daily']}/Tag\n"
        f"🌐 {SHOP_URL}"
    )
    await _tg(msg)
    log.info("Revenue report sent: €%s revenue, ROAS=%sx", revenue, overall_roas)
    return {"ok": True, "report_sent": True, "stats": stats, "roas": roas}


async def run_revenue_optimization_cycle() -> dict:
    """
    Master orchestrator:
    1. Gather all stats
    2. Calculate ROAS
    3. Reallocate budgets
    4. Send daily report
    5. Log underperformers
    """
    stats = await get_all_revenue_stats()
    roas = calculate_roas(stats)
    allocation = await optimize_budget_allocation(total_budget=50.0, stats=stats)

    # Log underperformers
    if roas.get("overall_roas", 0) < 1.5:
        log.warning("Low ROAS detected: %.2f — consider pausing underperformers", roas.get("overall_roas", 0))

    report = await run_daily_revenue_report(stats=stats)

    return {
        "ok": True,
        "stats": stats,
        "roas": roas,
        "allocation": allocation,
        "report_sent": report.get("report_sent", False),
    }


async def get_revenue_status() -> dict:
    """Quick status dict for API endpoint."""
    stats = await get_all_revenue_stats()
    roas = calculate_roas(stats)
    return {
        "ok": True,
        "revenue_7d": stats["shopify"].get("revenue", 0),
        "orders_7d": stats["shopify"].get("orders", 0),
        "overall_roas": roas.get("overall_roas", 0),
        "meta_spend_7d": stats["meta_ads"].get("spend", 0),
        "tiktok_spend_7d": stats["tiktok_ads"].get("spend", 0),
        "emails_today": stats.get("emails_sent_today", 0),
        "articles_today": stats.get("seo_articles_today", 0),
    }
