#!/usr/bin/env python3
"""
BullPower MEGA Command Center — Revenue Tracker
===============================================
Aggregates real-time revenue across Stripe, Digistore24, Shopify, Klaviyo.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

log = logging.getLogger("RevenueTracker")

_DATA = Path(__file__).parent.parent / "data"
SNAPSHOT_FILE = _DATA / "revenue_snapshot.json"

_LAST_ALERT: dict[str, float] = {}


def _e(key: str, default: str = "") -> str:
    return os.getenv(key, default) or default


def _today_midnight_ts() -> int:
    d = date.today()
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


async def _get_json(session: aiohttp.ClientSession, url: str, headers: dict | None = None,
                    params: dict | None = None, auth: tuple | None = None,
                    timeout: int = 15) -> tuple[int, Any]:
    try:
        kwargs: dict = {"headers": headers or {}, "params": params or {},
                        "timeout": aiohttp.ClientTimeout(total=timeout)}
        if auth:
            kwargs["auth"] = aiohttp.BasicAuth(*auth)
        async with session.get(url, **kwargs) as r:
            try:
                body = await r.json(content_type=None)
            except Exception:
                body = {}
            return r.status, body
    except Exception as exc:
        return 0, {"error": str(exc)}


# ── Stripe ────────────────────────────────────────────────────────────────────
async def _stripe_revenue(session: aiohttp.ClientSession) -> dict:
    key = _e("STRIPE_SECRET_KEY")
    if not key:
        return {"today": 0.0, "total": 0.0, "count": 0, "error": "no key"}

    today_ts = _today_midnight_ts()
    today_total = 0.0
    all_total = 0.0
    count = 0

    # Fetch recent charges (last 50)
    status, body = await _get_json(
        session, "https://api.stripe.com/v1/balance/transactions",
        params={"limit": "100", "type": "charge"},
        auth=(key, ""),
    )
    if status != 200:
        return {"today": 0.0, "total": 0.0, "count": 0, "error": str(body)[:80]}

    for txn in body.get("data", []):
        amount_eur = txn.get("amount", 0) / 100.0
        all_total += amount_eur
        count += 1
        if txn.get("created", 0) >= today_ts:
            today_total += amount_eur

    return {"today": round(today_total, 2), "total": round(all_total, 2), "count": count}


# ── Digistore24 ───────────────────────────────────────────────────────────────
async def _ds24_revenue(session: aiohttp.ClientSession) -> dict:
    ds_key = _e("DIGISTORE24_API_KEY")
    if not ds_key:
        return {"total": 0.0, "count": 0, "error": "no key"}

    status, body = await _get_json(
        session,
        "https://www.digistore24.com/api/call/listTransactions/JSON/",
        headers={"X-DS-API-KEY": ds_key},
    )
    if status != 200:
        return {"total": 0.0, "count": 0, "error": str(body)[:80]}

    transactions = body.get("data", {}).get("transactions", []) if isinstance(body, dict) else []
    total = 0.0
    for t in transactions:
        try:
            total += float(t.get("earnings_gross", t.get("price_gross", 0)) or 0)
        except (ValueError, TypeError):
            pass
    return {"total": round(total, 2), "count": len(transactions)}


# ── Shopify ───────────────────────────────────────────────────────────────────
async def _shopify_revenue(session: aiohttp.ClientSession) -> dict:
    domain = _e("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")
    token = _e("SHOPIFY_ADMIN_API_TOKEN") or _e("SHOPIFY_ACCESS_TOKEN")
    if not token:
        return {"today": 0.0, "count": 0, "last_order": None, "error": "no token"}

    today_str = date.today().isoformat() + "T00:00:00Z"
    status, body = await _get_json(
        session,
        f"https://{domain}/admin/api/2026-04/orders.json",
        headers={"X-Shopify-Access-Token": token},
        params={"status": "any", "limit": "50", "created_at_min": today_str},
    )
    if status != 200:
        return {"today": 0.0, "count": 0, "last_order": None, "error": str(body)[:80]}

    orders = body.get("orders", [])
    today_total = 0.0
    last_order = None
    for order in orders:
        try:
            today_total += float(order.get("total_price", 0) or 0)
        except (ValueError, TypeError):
            pass
        if last_order is None:
            last_order = {
                "id": order.get("id"),
                "total": order.get("total_price"),
                "created_at": order.get("created_at"),
                "email": order.get("email", ""),
            }
    return {"today": round(today_total, 2), "count": len(orders), "last_order": last_order}


# ── Klaviyo (email events as revenue proxy) ───────────────────────────────────
async def _klaviyo_events(session: aiohttp.ClientSession) -> dict:
    key = _e("KLAVIYO_API_KEY_AIITEC") or _e("KLAVIYO_API_KEY")
    if not key:
        return {"placed_orders": 0, "error": "no key"}

    status, body = await _get_json(
        session,
        "https://a.klaviyo.com/api/metrics/",
        headers={"Authorization": f"Klaviyo-API-Key {key}", "revision": "2024-02-15"},
        params={"filter": 'equals(name,"Placed Order")'},
    )
    if status != 200:
        return {"placed_orders": 0, "error": str(body)[:80]}

    metrics = body.get("data", [])
    return {"placed_orders": len(metrics)}


# ── Telegram Alert ────────────────────────────────────────────────────────────
async def _tg(msg: str) -> None:
    token = _e("TELEGRAM_BOT_TOKEN")
    chat = _e("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as exc:
        log.warning("TG alert failed: %s", exc)


# ── Main aggregator ───────────────────────────────────────────────────────────
async def get_all_revenue() -> dict:
    """Aggregate revenue from all streams."""
    async with aiohttp.ClientSession() as session:
        stripe, ds24, shopify, klaviyo = await asyncio.gather(
            _stripe_revenue(session),
            _ds24_revenue(session),
            _shopify_revenue(session),
            _klaviyo_events(session),
            return_exceptions=True,
        )

    def _safe(x: Any, default: dict) -> dict:
        return x if isinstance(x, dict) else {**default, "error": str(x)}

    stripe = _safe(stripe, {"today": 0.0, "total": 0.0, "count": 0})
    ds24 = _safe(ds24, {"total": 0.0, "count": 0})
    shopify = _safe(shopify, {"today": 0.0, "count": 0, "last_order": None})
    klaviyo = _safe(klaviyo, {"placed_orders": 0})

    stripe_today = stripe.get("today", 0.0)
    shopify_today = shopify.get("today", 0.0)
    total_today = round(stripe_today + shopify_today, 2)
    total_all = round(stripe.get("total", 0.0) + ds24.get("total", 0.0), 2)

    result = {
        "stripe_today": stripe_today,
        "stripe_total": stripe.get("total", 0.0),
        "stripe_count": stripe.get("count", 0),
        "ds24_total": ds24.get("total", 0.0),
        "ds24_count": ds24.get("count", 0),
        "shopify_today": shopify_today,
        "shopify_order_count": shopify.get("count", 0),
        "klaviyo_placed_orders": klaviyo.get("placed_orders", 0),
        "total_today": total_today,
        "total_all_time": total_all,
        "last_order": shopify.get("last_order"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "_sources": {"stripe": stripe, "ds24": ds24, "shopify": shopify, "klaviyo": klaviyo},
    }

    _DATA.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_FILE.write_text(json.dumps(result, indent=2))

    # Alerts
    now = time.monotonic()
    last_celebrate = _LAST_ALERT.get("celebrate", 0)
    last_warn = _LAST_ALERT.get("warn", 0)

    if total_today > 0 and (now - last_celebrate) > 3600:
        _LAST_ALERT["celebrate"] = now
        asyncio.create_task(_tg(
            f"💰 *Revenue Today: €{total_today:.2f}*\n"
            f"Stripe: €{stripe_today:.2f} | Shopify: €{shopify_today:.2f}\n"
            f"DS24 total: €{ds24.get('total', 0):.2f}"
        ))
    elif total_today == 0 and (now - last_warn) > 86400:
        _LAST_ALERT["warn"] = now
        asyncio.create_task(_tg(
            "⚠️ *0 € Umsatz in 24h!*\nShopify + Stripe zeigen keine neuen Zahlungen. "
            "Bitte prüfen!"
        ))

    log.info("Revenue snapshot: today=€%.2f all=€%.2f", total_today, total_all)
    return result


async def get_roas(ad_spend: float) -> dict:
    """Calculate ROAS from current revenue vs given ad spend."""
    rev = await get_all_revenue()
    today_rev = rev.get("total_today", 0.0)
    if ad_spend > 0:
        roas = round(today_rev / ad_spend, 2)
    else:
        roas = 0.0
    result = {
        "roas": roas,
        "revenue_today": today_rev,
        "ad_spend": ad_spend,
        "profitable": roas >= 2.0,
        "recommendation": (
            "✅ Profitable — scale ads" if roas >= 3.0 else
            "⚠️ Break-even — hold" if roas >= 1.0 else
            "❌ Unprofitable — pause ads"
        ),
    }
    return result


def get_cached_snapshot() -> dict:
    """Return last saved snapshot without API calls."""
    if SNAPSHOT_FILE.exists():
        try:
            return json.loads(SNAPSHOT_FILE.read_text())
        except Exception:
            pass
    return {
        "stripe_today": 0.0, "stripe_total": 0.0, "ds24_total": 0.0,
        "shopify_today": 0.0, "total_today": 0.0, "total_all_time": 0.0,
        "last_order": None, "timestamp": None,
    }
