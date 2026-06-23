#!/usr/bin/env python3
"""Digistore24 automation — orders, products, sales sync"""
import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

log = logging.getLogger("Digistore24")

DS24_BASE = "https://www.digistore24.com/api/call"
DS24_KEY  = os.getenv("DIGISTORE24_API_KEY", "1581233-eOOUB4qRJJybjVb9z4q5tO68wtEQmt9h9l8t3s1N")
DS24_FORMAT = "JSON"

# DS24 API v1.2: use X-DS-API-KEY header (URL-based key auth deprecated)
DS24_HEADERS = {"X-DS-API-KEY": DS24_KEY} if DS24_KEY else {}


def _url(action: str) -> str:
    return f"{DS24_BASE}/{action}/{DS24_FORMAT}/"


def is_configured() -> bool:
    return bool(DS24_KEY)


async def get_orders(page=1, per_page=50):
    """Fetch orders from Digistore24. Returns list of order dicts."""
    if not DS24_KEY:
        log.warning("DIGISTORE24_API_KEY not set — returning empty (set key to enable)")
        return []

    if not HAS_AIOHTTP:
        log.error("aiohttp not installed")
        return []

    url = _url("listTransactions")
    now = datetime.now()
    params = {
        "page_no": page,
        "page_size": per_page,
        "from": (now - timedelta(days=365)).strftime("%Y-%m-%d"),
        "to": now.strftime("%Y-%m-%d"),
    }
    headers = {"X-DS-API-KEY": DS24_KEY}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json(content_type=None)
        if data.get("result") == "success":
            raw = data.get("data", {})
            return raw.get("transaction_list", [])
        log.warning("DS24 get_orders: result=%s msg=%s", data.get("result"), data.get("message",""))
        return []
    except Exception as exc:
        log.error("DS24 get_orders error: %s", exc)
        return []


async def get_products():
    """Fetch products from Digistore24. Returns list of product dicts."""
    if not DS24_KEY:
        log.warning("DIGISTORE24_API_KEY not set — returning empty")
        return []

    if not HAS_AIOHTTP:
        log.error("aiohttp not installed")
        return []

    url = _url("listProducts")
    headers = {"X-DS-API-KEY": DS24_KEY}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json(content_type=None)
        if data.get("result") == "success":
            raw = data.get("data", {})
            products = raw.get("products", raw.get("product_list", []))
            return products
        log.warning("DS24 get_products: result=%s", data.get("result"))
        return []
    except Exception as exc:
        log.error("DS24 get_products error: %s", exc)
        return []


async def get_sales_stats():
    """Return daily/weekly/monthly sales totals computed from orders."""
    orders = await get_orders(page=1, per_page=200)
    now = datetime.now()
    day_start   = now - timedelta(days=1)
    week_start  = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    quarter_start = now - timedelta(days=90)
    totals = {
        "today": 0.0, "week": 0.0, "month": 0.0, "quarter": 0.0, "total": 0.0,
        "orders_today": 0, "orders_week": 0, "orders_month": 0, "orders_quarter": 0, "orders_total": 0,
    }

    for order in orders:
        raw_date = order.get("transaction_pay_date") or order.get("created_at") or order.get("transaction_created_at") or ""
        try:
            if raw_date:
                order_dt = datetime.strptime(raw_date[:10], "%Y-%m-%d")
            else:
                continue
        except ValueError:
            continue

        amount = 0.0
        for field in ("amount", "transaction_amount", "earned_amount", "total", "price"):
            try:
                amount = float(order.get(field, 0) or 0)
                if amount:
                    break
            except (ValueError, TypeError):
                pass

        totals["total"] += amount
        totals["orders_total"] += 1
        if order_dt >= quarter_start:
            totals["quarter"] += amount
            totals["orders_quarter"] += 1
        if order_dt >= month_start:
            totals["month"] += amount
            totals["orders_month"] += 1
        if order_dt >= week_start:
            totals["week"] += amount
            totals["orders_week"] += 1
        if order_dt >= day_start:
            totals["today"] += amount
            totals["orders_today"] += 1

    for k in ("today", "week", "month", "quarter", "total"):
        totals[k] = round(totals[k], 2)
    return totals


async def ping():
    """Test the DS24 API key. Returns True if connected, False otherwise."""
    if not DS24_KEY:
        return False
    if not HAS_AIOHTTP:
        return False
    try:
        url = _url("listProducts")
        headers = {"X-DS-API-KEY": DS24_KEY}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json(content_type=None)
        return data.get("result") == "success"
    except Exception as exc:
        log.error("DS24 ping error: %s", exc)
        return False


async def setup_ipn(product_id: str = "576000") -> dict:
    """Return info about IPN setup — user must set this URL in DS24 manually."""
    ipn_url = "https://dudirudibot-mega-production.up.railway.app/api/digistore24/ipn"
    return {
        "ipn_url": ipn_url,
        "product_id": product_id,
        "instructions": (
            f"In Digistore24 → Vendor → Products → {product_id} → "
            f"Integration → IPN URL setzen auf: {ipn_url}"
        ),
    }


async def run_with_brutus_traffic() -> dict:
    """Run DS24 stats then fire BRUTUS traffic for Digistore24."""
    result = {}
    try:
        result["stats"] = await get_sales_stats()
    except Exception as e:
        result["stats_error"] = str(e)
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        result["brutus"] = await run_brutus_swarm(
            keywords=["Digistore24 Affiliate 2026", "digitale Produkte verkaufen online", "AI Income Machine AIITEC"],
            max_keywords=3,
        )
    except Exception as e:
        result["brutus_error"] = str(e)
    return result
