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
DS24_KEY  = os.getenv("DIGISTORE24_API_KEY", "")
DS24_FORMAT = "json"


def _url(action: str) -> str:
    return f"{DS24_BASE}/{DS24_KEY}/{action}/{DS24_FORMAT}"


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

    url = _url("listOrdersForVendor")
    params = {"page": page, "items_per_page": per_page}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json(content_type=None)
        if data.get("result") == "success":
            raw = data.get("data", {})
            # DS24 nests orders under data.order_list or data.orders
            orders = raw.get("order_list", raw.get("orders", raw if isinstance(raw, list) else []))
            return orders
        log.warning("DS24 get_orders: result=%s", data.get("result"))
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

    url = _url("listProductsForVendor")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json(content_type=None)
        if data.get("result") == "success":
            raw = data.get("data", {})
            products = raw.get("product_list", raw.get("products", raw if isinstance(raw, list) else []))
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

    totals = {"today": 0.0, "week": 0.0, "month": 0.0,
              "orders_today": 0, "orders_week": 0, "orders_month": 0}

    for order in orders:
        # Try to parse date from various DS24 field names
        raw_date = order.get("date") or order.get("order_date") or order.get("created_at") or ""
        try:
            if raw_date:
                order_dt = datetime.strptime(raw_date[:10], "%Y-%m-%d")
            else:
                continue
        except ValueError:
            continue

        amount = 0.0
        for field in ("amount", "total", "gross_revenue", "price"):
            try:
                amount = float(order.get(field, 0) or 0)
                if amount:
                    break
            except (ValueError, TypeError):
                pass

        if order_dt >= month_start:
            totals["month"] += amount
            totals["orders_month"] += 1
        if order_dt >= week_start:
            totals["week"] += amount
            totals["orders_week"] += 1
        if order_dt >= day_start:
            totals["today"] += amount
            totals["orders_today"] += 1

    totals["today"]  = round(totals["today"], 2)
    totals["week"]   = round(totals["week"], 2)
    totals["month"]  = round(totals["month"], 2)
    return totals


async def ping():
    """Test the DS24 API key. Returns True if connected, False otherwise."""
    if not DS24_KEY:
        return False
    if not HAS_AIOHTTP:
        return False
    try:
        url = _url("listProductsForVendor")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json(content_type=None)
        return data.get("result") == "success"
    except Exception as exc:
        log.error("DS24 ping error: %s", exc)
        return False
