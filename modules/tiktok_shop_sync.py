#!/usr/bin/env python3
"""
TikTok Shop Integration — Produkt-Sync, Bestellungen, Analytics, Promotions.

Env vars:
  TIKTOK_APP_KEY       — TikTok Developer App Key
  TIKTOK_APP_SECRET    — TikTok Developer App Secret
  TIKTOK_ACCESS_TOKEN  — Shop access token
  TIKTOK_SHOP_ID       — TikTok Shop ID
  SHOPIFY_SHOP_DOMAIN / SHOPIFY_ADMIN_API_TOKEN / SHOPIFY_API_VERSION — Shopify source
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger("TikTokShopSync")

_TIKTOK_BASE = "https://open-api.tiktokglobalshop.com"

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


# ── Config helpers ────────────────────────────────────────────────────────────

def _app_key() -> str:
    return os.getenv("TIKTOK_APP_KEY", "")

def _app_secret() -> str:
    return os.getenv("TIKTOK_APP_SECRET", "")

def _access_token() -> str:
    return os.getenv("TIKTOK_ACCESS_TOKEN", "")

def _shop_id() -> str:
    return os.getenv("TIKTOK_SHOP_ID", "")

def _shopify_domain() -> str:
    return os.getenv("SHOPIFY_SHOP_DOMAIN", "")

def _shopify_token() -> str:
    return os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")

def _shopify_version() -> str:
    return os.getenv("SHOPIFY_API_VERSION", "2024-10")

def _is_configured() -> bool:
    return bool(_app_key() and _access_token() and _shop_id())


# ── TikTok request signing ────────────────────────────────────────────────────

def _sign_request(path: str, params: Dict[str, str], body: str = "") -> str:
    """
    TikTok Shop API v2 HMAC-SHA256 signature.
    Concat: app_secret + path + sorted(params as key+value) + body
    """
    secret = _app_secret()
    if not secret:
        return ""
    # Sort params by key, exclude sign and access_token
    exclude = {"sign", "access_token"}
    sorted_params = sorted((k, v) for k, v in params.items() if k not in exclude)
    param_str = "".join(f"{k}{v}" for k, v in sorted_params)
    base = f"{secret}{path}{param_str}{body}"
    return hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()


async def _tiktok_get(path: str, extra_params: Optional[Dict] = None) -> Dict:
    """Authenticated GET to TikTok Shop API."""
    if not HAS_AIOHTTP:
        return {"error": "aiohttp not installed"}
    if not _is_configured():
        return {"error": "TikTok Shop not configured (TIKTOK_APP_KEY, TIKTOK_ACCESS_TOKEN, TIKTOK_SHOP_ID)"}
    ts = str(int(time.time()))
    params: Dict[str, str] = {
        "app_key": _app_key(),
        "shop_id": _shop_id(),
        "timestamp": ts,
        "version": "202309",
    }
    if extra_params:
        params.update({k: str(v) for k, v in extra_params.items()})
    params["sign"] = _sign_request(path, params)
    url = f"{_TIKTOK_BASE}{path}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(
                url,
                headers={
                    "x-tts-access-token": _access_token(),
                    "Content-Type": "application/json",
                },
                params=params,
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200:
                    log.warning("TikTok GET %s %s: %s", resp.status, path, data)
                return data
    except Exception as exc:
        log.error("TikTok GET error %s: %s", path, exc)
        return {"error": str(exc)}


async def _tiktok_post(path: str, body: Dict, extra_params: Optional[Dict] = None) -> Dict:
    """Authenticated POST to TikTok Shop API."""
    if not HAS_AIOHTTP:
        return {"error": "aiohttp not installed"}
    if not _is_configured():
        return {"error": "TikTok Shop not configured"}
    ts = str(int(time.time()))
    params: Dict[str, str] = {
        "app_key": _app_key(),
        "shop_id": _shop_id(),
        "timestamp": ts,
        "version": "202309",
    }
    if extra_params:
        params.update({k: str(v) for k, v in extra_params.items()})
    body_str = json.dumps(body)
    params["sign"] = _sign_request(path, params, body_str)
    url = f"{_TIKTOK_BASE}{path}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                url,
                headers={
                    "x-tts-access-token": _access_token(),
                    "Content-Type": "application/json",
                },
                params=params,
                data=body_str,
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status not in (200, 201):
                    log.warning("TikTok POST %s %s: %s", resp.status, path, data)
                return data
    except Exception as exc:
        log.error("TikTok POST error %s: %s", path, exc)
        return {"error": str(exc)}


# ── Shopify helpers ───────────────────────────────────────────────────────────

async def _shopify_get(endpoint: str) -> Dict:
    domain = _shopify_domain()
    token  = _shopify_token()
    if not domain or not token:
        return {"error": "Shopify not configured"}
    if not HAS_AIOHTTP:
        return {"error": "aiohttp not installed"}
    base = f"https://{domain}" if not domain.startswith("http") else domain
    url  = f"{base}/admin/api/{_shopify_version()}/{endpoint}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(
                url, headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
            ) as resp:
                return await resp.json(content_type=None)
    except Exception as exc:
        return {"error": str(exc)}


async def _shopify_post(endpoint: str, data: Dict) -> Dict:
    domain = _shopify_domain()
    token  = _shopify_token()
    if not domain or not token:
        return {"error": "Shopify not configured"}
    if not HAS_AIOHTTP:
        return {"error": "aiohttp not installed"}
    base = f"https://{domain}" if not domain.startswith("http") else domain
    url  = f"{base}/admin/api/{_shopify_version()}/{endpoint}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                url,
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json=data,
            ) as resp:
                return await resp.json(content_type=None)
    except Exception as exc:
        return {"error": str(exc)}


# ── Public API ────────────────────────────────────────────────────────────────

async def get_shop_info() -> Dict:
    """TikTok Shop Info und Status."""
    result = await _tiktok_get("/shop/202309/shops")
    if "error" in result:
        return {"configured": False, "error": result["error"]}
    shops = result.get("data", {}).get("shops") or []
    if shops:
        shop = shops[0]
        return {
            "configured": True,
            "shop_id": shop.get("id") or _shop_id(),
            "shop_name": shop.get("name", ""),
            "region": shop.get("region", ""),
            "status": shop.get("status", "active"),
        }
    return {
        "configured": _is_configured(),
        "shop_id": _shop_id(),
        "shop_name": "Unknown",
        "status": "configured" if _is_configured() else "not_configured",
    }


async def sync_products_to_tiktok(limit: int = 50) -> Dict:
    """
    Synct Shopify-Produkte zu TikTok Shop:
    1. Holt Shopify-Produkte
    2. Prüft ob bereits auf TikTok vorhanden
    3. Erstellt/Updated Listings
    Returns: {"synced": 12, "created": 3, "updated": 9, "failed": 0}
    """
    synced = 0
    created = 0
    updated = 0
    failed = 0
    errors: List[str] = []

    # Fetch Shopify products
    sh_result = await _shopify_get(f"products.json?limit={limit}&status=active")
    if "error" in sh_result:
        return {"synced": 0, "created": 0, "updated": 0, "failed": 0,
                "error": f"Shopify error: {sh_result['error']}"}
    shopify_products = sh_result.get("products", [])
    if not shopify_products:
        return {"synced": 0, "created": 0, "updated": 0, "failed": 0,
                "error": "No active Shopify products found"}

    # Fetch existing TikTok listings
    tt_result = await _tiktok_get("/product/202309/products/search", {"page_size": "100"})
    existing_tiktok: Dict[str, str] = {}  # external_id -> tiktok_product_id
    if "data" in tt_result:
        for item in (tt_result.get("data", {}).get("products") or []):
            ext_id = item.get("skus", [{}])[0].get("external_sku_id", "")
            if ext_id:
                existing_tiktok[ext_id] = item.get("id", "")

    for product in shopify_products[:limit]:
        product_id = str(product.get("id", ""))
        title  = product.get("title", "")
        desc   = product.get("body_html", "")
        images = [img.get("src", "") for img in (product.get("images") or [])[:9] if img.get("src")]
        variants = product.get("variants") or []
        if not variants:
            failed += 1
            continue

        # Build TikTok product payload
        skus = []
        for variant in variants[:50]:
            sku: Dict[str, Any] = {
                "external_sku_id": str(variant.get("id", "")),
                "seller_sku": variant.get("sku") or str(variant.get("id", "")),
                "price": {
                    "currency": "USD",
                    "amount": str(variant.get("price", "0")),
                },
                "inventory": [
                    {
                        "quantity": int(variant.get("inventory_quantity") or 0),
                        "warehouse_id": "",  # filled by TikTok
                    }
                ],
            }
            skus.append(sku)

        tt_payload: Dict[str, Any] = {
            "product_name": title[:255],
            "description": (desc or title)[:5000],
            "category_id": "",  # Would need category mapping in production
            "brand_id": "",
            "images": [{"url": img} for img in images],
            "skus": skus,
        }

        try:
            if product_id in existing_tiktok:
                # Update existing
                tt_id = existing_tiktok[product_id]
                result = await _tiktok_post(
                    f"/product/202309/products/{tt_id}", tt_payload
                )
                if result.get("code") == 0:
                    updated += 1
                    synced += 1
                else:
                    failed += 1
                    errors.append(f"{title[:30]}: {result.get('message','?')}")
            else:
                # Create new
                result = await _tiktok_post("/product/202309/products", tt_payload)
                if result.get("code") == 0:
                    created += 1
                    synced += 1
                else:
                    failed += 1
                    errors.append(f"{title[:30]}: {result.get('message','?')}")
        except Exception as exc:
            failed += 1
            errors.append(f"{title[:30]}: {exc}")

    log.info("TikTok product sync: %s synced (%s created, %s updated, %s failed)",
             synced, created, updated, failed)
    return {
        "synced": synced,
        "created": created,
        "updated": updated,
        "failed": failed,
        "errors": errors[:5],
    }


async def get_tiktok_orders(days: int = 7) -> List[Dict]:
    """Holt TikTok Shop Bestellungen der letzten X Tage."""
    since_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    until_ts = int(datetime.now(timezone.utc).timestamp())
    result = await _tiktok_get(
        "/order/202309/orders/search",
        {
            "create_time_ge": str(since_ts),
            "create_time_lt": str(until_ts),
            "page_size": "50",
            "sort_type": "2",      # desc by create time
        },
    )
    if "error" in result:
        log.warning("get_tiktok_orders error: %s", result["error"])
        return []
    orders = result.get("data", {}).get("orders") or []
    normalized = []
    for o in orders:
        normalized.append({
            "id": o.get("id") or o.get("order_id"),
            "status": o.get("status"),
            "total_amount": o.get("payment", {}).get("total_amount"),
            "currency": o.get("payment", {}).get("currency", "USD"),
            "buyer_uid": o.get("buyer_uid"),
            "created_at": o.get("create_time"),
            "items": [
                {
                    "product_name": item.get("product_name"),
                    "quantity": item.get("quantity"),
                    "sku_id": item.get("sku_id"),
                }
                for item in (o.get("line_items") or [])
            ],
        })
    return normalized


async def sync_tiktok_orders_to_shopify() -> Dict:
    """
    Importiert TikTok-Bestellungen als Shopify-Bestellungen.
    Returns: {"imported": 3, "skipped": 1, "failed": 0}
    """
    imported = 0
    skipped = 0
    failed = 0

    tt_orders = await get_tiktok_orders(days=1)
    if not tt_orders:
        return {"imported": 0, "skipped": 0, "failed": 0, "message": "No TikTok orders found"}

    for order in tt_orders:
        try:
            order_id = str(order.get("id", ""))
            # Check if already imported (by searching Shopify notes)
            existing = await _shopify_get(
                f"orders.json?note=tiktok_order:{order_id}&status=any&limit=1"
            )
            if existing.get("orders"):
                skipped += 1
                continue

            # Create Shopify order
            line_items = [
                {"title": item.get("product_name", "TikTok Product"),
                 "quantity": item.get("quantity", 1),
                 "price": "0.00"}  # price would be mapped from TikTok SKU in production
                for item in (order.get("items") or [])
            ]
            if not line_items:
                skipped += 1
                continue

            sh_order = {
                "order": {
                    "financial_status": "paid",
                    "fulfillment_status": None,
                    "note": f"tiktok_order:{order_id}",
                    "tags": "tiktok_shop",
                    "line_items": line_items,
                    "total_price": str(order.get("total_amount") or "0"),
                    "currency": order.get("currency", "USD"),
                }
            }
            result = await _shopify_post("orders.json", sh_order)
            if result.get("order"):
                imported += 1
            else:
                failed += 1
                log.warning("sync_tiktok_orders_to_shopify: create failed: %s", result)
        except Exception as exc:
            failed += 1
            log.error("sync_tiktok_orders_to_shopify order %s: %s", order.get("id"), exc)

    return {"imported": imported, "skipped": skipped, "failed": failed}


async def get_tiktok_analytics() -> Dict:
    """
    TikTok Shop Analytics — GMV, Bestellungen, Top-Produkte, Conversion.
    """
    today = datetime.now(timezone.utc)
    today_start = int(today.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    seven_days_ago = int((today - timedelta(days=7)).timestamp())
    now_ts = int(today.timestamp())

    # Orders today
    orders_today_result = await _tiktok_get(
        "/order/202309/orders/search",
        {"create_time_ge": str(today_start), "create_time_lt": str(now_ts), "page_size": "50"},
    )
    orders_today = orders_today_result.get("data", {}).get("orders") or []
    gmv_today = sum(
        float(o.get("payment", {}).get("total_amount") or 0)
        for o in orders_today
    )

    # Orders 7 days
    orders_7d_result = await _tiktok_get(
        "/order/202309/orders/search",
        {"create_time_ge": str(seven_days_ago), "create_time_lt": str(now_ts), "page_size": "100"},
    )
    orders_7d = orders_7d_result.get("data", {}).get("orders") or []
    gmv_7d = sum(
        float(o.get("payment", {}).get("total_amount") or 0)
        for o in orders_7d
    )

    # Top products from 7d orders
    product_revenue: Dict[str, float] = {}
    for o in orders_7d:
        for item in (o.get("line_items") or []):
            name = item.get("product_name", "?")
            amount = float(item.get("item_price") or 0) * int(item.get("quantity") or 1)
            product_revenue[name] = product_revenue.get(name, 0) + amount
    top_products = sorted(
        [{"name": k, "revenue": round(v, 2)} for k, v in product_revenue.items()],
        key=lambda x: x["revenue"],
        reverse=True,
    )[:5]

    # Conversion rate (orders / product views — approximated from analytics endpoint)
    conversion_rate = 0.0
    analytics_result = await _tiktok_get(
        "/analytics/202309/shop/metrics",
        {"start_date": (today - timedelta(days=7)).strftime("%Y-%m-%d"),
         "end_date": today.strftime("%Y-%m-%d"),
         "metrics": "page_views,order_count"},
    )
    metrics = analytics_result.get("data", {}).get("metrics") or {}
    views = float(metrics.get("page_views") or 0)
    orders_count = float(metrics.get("order_count") or len(orders_7d))
    if views > 0:
        conversion_rate = round(orders_count / views * 100, 2)

    return {
        "gmv_today": round(gmv_today, 2),
        "gmv_7d": round(gmv_7d, 2),
        "orders_today": len(orders_today),
        "orders_7d": len(orders_7d),
        "top_products": top_products,
        "conversion_rate": conversion_rate,
        "currency": "USD",
    }


async def create_tiktok_promotion(
    product_id: str, discount_pct: int, duration_hours: int
) -> Dict:
    """Erstellt eine TikTok-exklusive Promotion für ein Produkt."""
    if not product_id:
        return {"error": "product_id is required"}
    if not (1 <= discount_pct <= 90):
        return {"error": "discount_pct must be between 1 and 90"}
    if duration_hours < 1:
        return {"error": "duration_hours must be >= 1"}

    now = datetime.now(timezone.utc)
    start_ts = int(now.timestamp())
    end_ts   = int((now + timedelta(hours=duration_hours)).timestamp())

    payload = {
        "product_id": product_id,
        "discount": {
            "discount_type": 1,       # Percentage off
            "discount_value": discount_pct,
        },
        "activity_start_time": start_ts,
        "activity_end_time": end_ts,
        "activity_type": 2,           # Flash sale
    }
    result = await _tiktok_post("/promotion/202309/activity", payload)
    if result.get("code") == 0:
        promo_id = result.get("data", {}).get("activity_id", "")
        log.info("TikTok promotion created: %s (%s%% off %s)", promo_id, discount_pct, product_id)
        return {
            "success": True,
            "promotion_id": promo_id,
            "product_id": product_id,
            "discount_pct": discount_pct,
            "duration_hours": duration_hours,
            "start": now.isoformat(),
            "end": (now + timedelta(hours=duration_hours)).isoformat(),
        }
    return {
        "success": False,
        "error": result.get("message", "Unknown error"),
        "code": result.get("code"),
    }


async def get_combined_revenue() -> Dict:
    """
    Kombinierter Revenue: Shopify + TikTok + Digistore24.
    Returns unified summary dict.
    """
    results: Dict[str, Any] = {}

    # TikTok
    try:
        tt_analytics = await get_tiktok_analytics()
        results["tiktok"] = {
            "gmv_today": tt_analytics.get("gmv_today", 0.0),
            "gmv_7d": tt_analytics.get("gmv_7d", 0.0),
            "orders_today": tt_analytics.get("orders_today", 0),
            "currency": tt_analytics.get("currency", "USD"),
            "ok": True,
        }
    except Exception as exc:
        results["tiktok"] = {"gmv_today": 0.0, "gmv_7d": 0.0, "orders_today": 0, "ok": False,
                             "error": str(exc)}

    # Shopify
    try:
        from modules.shopify_client import get_analytics_summary  # type: ignore
        sh = await get_analytics_summary()
        results["shopify"] = {
            "revenue_today": float(sh.get("revenue", 0)),
            "orders_today": int(sh.get("orders_paid", 0)),
            "currency": sh.get("currency", "EUR"),
            "ok": True,
        }
    except Exception as exc:
        log.debug("Shopify revenue: %s", exc)
        results["shopify"] = {"revenue_today": 0.0, "orders_today": 0, "ok": False,
                              "error": str(exc)}

    # Digistore24
    try:
        from modules.digistore24_automation import get_sales_stats  # type: ignore
        ds = await get_sales_stats()
        results["digistore24"] = {
            "revenue_today": float(ds.get("today_revenue", ds.get("total_revenue", 0))),
            "orders_today": int(ds.get("today_orders", ds.get("total_orders", 0))),
            "currency": "EUR",
            "ok": True,
        }
    except Exception as exc:
        log.debug("Digistore24 revenue: %s", exc)
        results["digistore24"] = {"revenue_today": 0.0, "orders_today": 0, "ok": False,
                                  "error": str(exc)}

    # Totals
    total_orders = (
        results["tiktok"].get("orders_today", 0)
        + results["shopify"].get("orders_today", 0)
        + results["digistore24"].get("orders_today", 0)
    )
    total_revenue_eur = (
        results["shopify"].get("revenue_today", 0.0)
        + results["digistore24"].get("revenue_today", 0.0)
        + results["tiktok"].get("gmv_today", 0.0) * 0.92  # USD → EUR approx
    )

    return {
        "platforms": results,
        "total_orders_today": total_orders,
        "total_revenue_eur_today": round(total_revenue_eur, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
