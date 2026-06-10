#!/usr/bin/env python3
"""
TikTok Shop Integration — Produkt-Sync, Bestellungen, Analytics, Promotions.

Env vars:
  TIKTOK_APP_KEY          — TikTok Developer App Key
  TIKTOK_APP_SECRET       — TikTok Developer App Secret
  TIKTOK_ACCESS_TOKEN     — Shop access token (short-lived)
  TIKTOK_REFRESH_TOKEN    — Token used to obtain a new access token
  TIKTOK_TOKEN_EXPIRES_AT — Unix timestamp when access token expires
  TIKTOK_SHOP_ID          — TikTok Shop ID
  SHOPIFY_SHOP_DOMAIN / SHOPIFY_ADMIN_API_TOKEN / SHOPIFY_API_VERSION — Shopify source
"""
from __future__ import annotations

import asyncio
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
_TOKEN_REFRESH_URL = "https://auth.tiktok-shops.com/api/v2/token/refresh"

# TikTok requires at least one image per product listing
_TIKTOK_MIN_IMAGES = 1

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

def _refresh_token() -> str:
    return os.getenv("TIKTOK_REFRESH_TOKEN", "")

def _token_expires_at() -> int:
    try:
        return int(os.getenv("TIKTOK_TOKEN_EXPIRES_AT", "0"))
    except (TypeError, ValueError):
        return 0

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


# ── Token refresh ─────────────────────────────────────────────────────────────

async def _refresh_access_token() -> bool:
    """
    Refreshes the TikTok access token using the refresh token.
    Updates TIKTOK_ACCESS_TOKEN and TIKTOK_TOKEN_EXPIRES_AT in the process env.
    Returns True on success, False on failure.
    Note: In production, write new token values to .env or a secrets store.
    """
    refresh = _refresh_token()
    if not refresh:
        log.warning("TikTok token refresh: TIKTOK_REFRESH_TOKEN not set")
        return False
    if not HAS_AIOHTTP:
        return False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(
                _TOKEN_REFRESH_URL,
                params={
                    "app_key": _app_key(),
                    "app_secret": _app_secret(),
                    "refresh_token": refresh,
                    "grant_type": "refresh_token",
                },
            ) as resp:
                data = await resp.json(content_type=None)
                if data.get("code") != 0:
                    log.error(
                        "TikTok token refresh failed: %s — %s",
                        data.get("code"), data.get("message"),
                    )
                    return False
                token_data = data.get("data", {})
                new_token   = token_data.get("access_token", "")
                expires_in  = int(token_data.get("access_token_expire_in", 0))
                new_refresh = token_data.get("refresh_token", refresh)
                if not new_token:
                    log.error("TikTok token refresh: empty access_token in response")
                    return False
                # Update process environment (in-memory for this run)
                os.environ["TIKTOK_ACCESS_TOKEN"] = new_token
                os.environ["TIKTOK_TOKEN_EXPIRES_AT"] = str(int(time.time()) + expires_in)
                if new_refresh:
                    os.environ["TIKTOK_REFRESH_TOKEN"] = new_refresh
                log.info(
                    "TikTok access token refreshed, expires in %ss", expires_in
                )
                return True
    except Exception as exc:
        log.error("TikTok token refresh error: %s", exc)
        return False


async def _ensure_valid_token() -> bool:
    """
    Check if the access token is about to expire (within 5 min) and refresh proactively.
    Returns False if token is missing or refresh fails.
    """
    if not _access_token():
        log.error("TIKTOK_ACCESS_TOKEN not set")
        return False
    expires_at = _token_expires_at()
    if expires_at > 0:
        time_left = expires_at - int(time.time())
        if time_left < 300:  # Less than 5 minutes left
            log.info("TikTok access token expires in %ss — refreshing", time_left)
            return await _refresh_access_token()
    return True


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


async def _tiktok_get(
    path: str,
    extra_params: Optional[Dict] = None,
    retries: int = 3,
) -> Dict:
    """Authenticated GET to TikTok Shop API with token refresh and retry."""
    if not HAS_AIOHTTP:
        return {"error": "aiohttp not installed"}
    if not _is_configured():
        return {"error": "TikTok Shop not configured (TIKTOK_APP_KEY, TIKTOK_ACCESS_TOKEN, TIKTOK_SHOP_ID)"}

    await _ensure_valid_token()

    backoff = 1.0
    for attempt in range(1, retries + 1):
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
                    if resp.status in (429, 500, 503):
                        log.warning(
                            "TikTok GET %s %s (attempt %s/%s), retrying in %.0fs",
                            resp.status, path, attempt, retries, backoff,
                        )
                        if attempt < retries:
                            await asyncio.sleep(backoff)
                            backoff *= 2
                            continue
                    if resp.status != 200:
                        log.warning("TikTok GET %s %s: %s", resp.status, path, data)
                    return data
        except aiohttp.ClientError as exc:
            log.warning("TikTok GET network error %s (attempt %s/%s): %s", path, attempt, retries, exc)
            if attempt < retries:
                await asyncio.sleep(backoff)
                backoff *= 2
        except Exception as exc:
            log.error("TikTok GET unexpected error %s: %s", path, exc)
            return {"error": str(exc)}
    return {"error": f"TikTok GET {path} unreachable after {retries} attempts"}


async def _tiktok_post(
    path: str,
    body: Dict,
    extra_params: Optional[Dict] = None,
    retries: int = 3,
) -> Dict:
    """Authenticated POST to TikTok Shop API with token refresh and retry."""
    if not HAS_AIOHTTP:
        return {"error": "aiohttp not installed"}
    if not _is_configured():
        return {"error": "TikTok Shop not configured"}

    await _ensure_valid_token()

    backoff = 1.0
    for attempt in range(1, retries + 1):
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
                    if resp.status in (429, 500, 503):
                        log.warning(
                            "TikTok POST %s %s (attempt %s/%s), retrying in %.0fs",
                            resp.status, path, attempt, retries, backoff,
                        )
                        if attempt < retries:
                            await asyncio.sleep(backoff)
                            backoff *= 2
                            continue
                    if resp.status not in (200, 201):
                        log.warning("TikTok POST %s %s: %s", resp.status, path, data)
                    return data
        except aiohttp.ClientError as exc:
            log.warning("TikTok POST network error %s (attempt %s/%s): %s", path, attempt, retries, exc)
            if attempt < retries:
                await asyncio.sleep(backoff)
                backoff *= 2
        except Exception as exc:
            log.error("TikTok POST unexpected error %s: %s", path, exc)
            return {"error": str(exc)}
    return {"error": f"TikTok POST {path} unreachable after {retries} attempts"}


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
    except aiohttp.ClientError as exc:
        return {"error": f"Shopify network error: {exc}"}
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
    except aiohttp.ClientError as exc:
        return {"error": f"Shopify network error: {exc}"}
    except Exception as exc:
        return {"error": str(exc)}


# ── Pagination helper ─────────────────────────────────────────────────────────

async def _tiktok_get_all_pages(
    path: str,
    base_params: Dict,
    data_key: str = "orders",
    page_size: int = 50,
    max_pages: int = 20,
) -> List[Dict]:
    """
    Fetches all pages from a paginated TikTok API endpoint.
    Uses cursor-based pagination (next_page_token).
    """
    all_items: List[Dict] = []
    params = {**base_params, "page_size": str(page_size)}
    page_token: Optional[str] = None

    for page_num in range(1, max_pages + 1):
        if page_token:
            params["page_token"] = page_token

        result = await _tiktok_get(path, params)
        if "error" in result:
            log.warning("_tiktok_get_all_pages: error on page %s: %s", page_num, result["error"])
            break

        data_obj = result.get("data", {})
        items = data_obj.get(data_key) or []
        all_items.extend(items)
        log.debug("_tiktok_get_all_pages: page %s fetched %s items", page_num, len(items))

        # Check for next page
        page_token = data_obj.get("next_page_token") or data_obj.get("page_token")
        total = data_obj.get("total_count") or data_obj.get("total")
        if not page_token or not items or len(all_items) >= (total or len(all_items)):
            break

    return all_items


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
    - Produkte ohne Bilder werden übersprungen (TikTok-Pflichtfeld)
    - Verwendet TikTok product_id für Idempotenz beim Update
    Returns: {"synced": 12, "created": 3, "updated": 9, "failed": 0, "skipped_no_image": 2}
    """
    synced = 0
    created = 0
    updated = 0
    failed = 0
    skipped_no_image = 0
    errors: List[str] = []

    # Fetch Shopify products
    sh_result = await _shopify_get(f"products.json?limit={limit}&status=active")
    if "error" in sh_result:
        return {
            "synced": 0, "created": 0, "updated": 0, "failed": 0,
            "skipped_no_image": 0,
            "error": f"Shopify error: {sh_result['error']}",
        }
    shopify_products = sh_result.get("products", [])
    if not shopify_products:
        return {
            "synced": 0, "created": 0, "updated": 0, "failed": 0,
            "skipped_no_image": 0,
            "error": "No active Shopify products found",
        }

    # Fetch existing TikTok listings for idempotent sync
    tt_result = await _tiktok_get("/product/202309/products/search", {"page_size": "100"})
    existing_tiktok: Dict[str, str] = {}  # shopify_product_id -> tiktok_product_id
    if "data" in tt_result:
        for item in (tt_result.get("data", {}).get("products") or []):
            # Map via external_product_id stored in the first SKU
            ext_id = str(item.get("external_product_id") or "")
            if not ext_id:
                # Fallback: first SKU's external_sku_id prefix (product id)
                skus = item.get("skus") or []
                if skus:
                    ext_id = str(skus[0].get("external_product_id") or "")
            if ext_id:
                existing_tiktok[ext_id] = item.get("id", "")

    for product in shopify_products[:limit]:
        product_id = str(product.get("id", ""))
        title    = product.get("title", "")
        desc     = product.get("body_html", "")
        images   = [
            img.get("src", "")
            for img in (product.get("images") or [])[:9]
            if img.get("src")
        ]
        variants = product.get("variants") or []

        # Skip products with no images (TikTok requires at least one)
        if len(images) < _TIKTOK_MIN_IMAGES:
            log.warning(
                "sync_products_to_tiktok: skipping '%s' (id=%s) — no images",
                title[:50], product_id,
            )
            skipped_no_image += 1
            continue

        if not variants:
            log.warning("sync_products_to_tiktok: skipping '%s' — no variants", title[:50])
            failed += 1
            continue

        # Build TikTok product payload
        skus = []
        for variant in variants[:50]:
            sku: Dict[str, Any] = {
                "external_sku_id": str(variant.get("id", "")),
                "external_product_id": product_id,
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
            "external_product_id": product_id,
            "product_name": title[:255],
            "description": (desc or title)[:5000],
            "category_id": "",  # Would need category mapping in production
            "brand_id": "",
            "images": [{"url": img} for img in images],
            "skus": skus,
        }

        try:
            if product_id in existing_tiktok:
                # Update existing — idempotent by TikTok product ID
                tt_id = existing_tiktok[product_id]
                result = await _tiktok_post(
                    f"/product/202309/products/{tt_id}", tt_payload
                )
                if result.get("code") == 0:
                    updated += 1
                    synced += 1
                    log.debug("TikTok product updated: '%s' (tt_id=%s)", title[:40], tt_id)
                else:
                    failed += 1
                    errors.append(f"{title[:30]}: {result.get('message','?')}")
            else:
                # Create new
                result = await _tiktok_post("/product/202309/products", tt_payload)
                if result.get("code") == 0:
                    created += 1
                    synced += 1
                    log.debug("TikTok product created: '%s'", title[:40])
                else:
                    failed += 1
                    errors.append(f"{title[:30]}: {result.get('message','?')}")
        except Exception as exc:
            failed += 1
            errors.append(f"{title[:30]}: {exc}")

    log.info(
        "TikTok product sync: %s synced (%s created, %s updated, %s failed, %s no_image)",
        synced, created, updated, failed, skipped_no_image,
    )
    return {
        "synced": synced,
        "created": created,
        "updated": updated,
        "failed": failed,
        "skipped_no_image": skipped_no_image,
        "errors": errors[:5],
    }


async def get_tiktok_orders(days: int = 7) -> List[Dict]:
    """
    Holt TikTok Shop Bestellungen der letzten X Tage.
    Unterstützt Pagination über alle Seiten (>50 Bestellungen).
    """
    since_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    until_ts = int(datetime.now(timezone.utc).timestamp())

    orders = await _tiktok_get_all_pages(
        "/order/202309/orders/search",
        base_params={
            "create_time_ge": str(since_ts),
            "create_time_lt": str(until_ts),
            "sort_type": "2",  # desc by create time
        },
        data_key="orders",
        page_size=50,
        max_pages=40,
    )

    if not orders:
        return []

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
    log.info("get_tiktok_orders: fetched %s orders for last %s days", len(normalized), days)
    return normalized


async def sync_tiktok_orders_to_shopify() -> Dict:
    """
    Importiert TikTok-Bestellungen als Shopify-Bestellungen.
    Idempotent: prüft vor dem Erstellen ob Bestellung (note=tiktok_order:<id>) bereits existiert.
    Returns: {"imported": 3, "skipped": 1, "failed": 0}
    """
    imported = 0
    skipped  = 0
    failed   = 0

    tt_orders = await get_tiktok_orders(days=1)
    if not tt_orders:
        return {"imported": 0, "skipped": 0, "failed": 0, "message": "No TikTok orders found"}

    for order in tt_orders:
        try:
            order_id = str(order.get("id", ""))
            if not order_id:
                log.warning("sync_tiktok_orders_to_shopify: order with no id — skipping")
                skipped += 1
                continue

            # Idempotency check: search Shopify for existing import by note tag
            existing = await _shopify_get(
                f"orders.json?note=tiktok_order:{order_id}&status=any&limit=1"
            )
            if existing.get("orders"):
                log.debug(
                    "sync_tiktok_orders_to_shopify: order %s already imported — skipping",
                    order_id,
                )
                skipped += 1
                continue

            # Build line items
            line_items = [
                {
                    "title": item.get("product_name") or "TikTok Product",
                    "quantity": max(1, int(item.get("quantity") or 1)),
                    "price": "0.00",  # price mapped from TikTok SKU in production
                }
                for item in (order.get("items") or [])
            ]
            if not line_items:
                log.warning(
                    "sync_tiktok_orders_to_shopify: order %s has no line items — skipping",
                    order_id,
                )
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
                log.info(
                    "sync_tiktok_orders_to_shopify: imported TikTok order %s as Shopify order %s",
                    order_id, result["order"].get("id"),
                )
            else:
                failed += 1
                log.warning(
                    "sync_tiktok_orders_to_shopify: create failed for order %s: %s",
                    order_id, result,
                )
        except Exception as exc:
            failed += 1
            log.error("sync_tiktok_orders_to_shopify order %s: %s", order.get("id"), exc)

    log.info(
        "TikTok->Shopify sync: %s imported, %s skipped, %s failed",
        imported, skipped, failed,
    )
    return {"imported": imported, "skipped": skipped, "failed": failed}


async def get_tiktok_analytics() -> Dict:
    """
    TikTok Shop Analytics — GMV, Bestellungen, Top-Produkte, Conversion.
    """
    today = datetime.now(timezone.utc)
    today_start   = int(today.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    seven_days_ago = int((today - timedelta(days=7)).timestamp())
    now_ts         = int(today.timestamp())

    # Orders today — full pagination
    orders_today = await _tiktok_get_all_pages(
        "/order/202309/orders/search",
        base_params={"create_time_ge": str(today_start), "create_time_lt": str(now_ts)},
        data_key="orders",
        page_size=50,
    )
    gmv_today = sum(
        float(o.get("payment", {}).get("total_amount") or 0)
        for o in orders_today
    )

    # Orders 7 days — full pagination
    orders_7d = await _tiktok_get_all_pages(
        "/order/202309/orders/search",
        base_params={"create_time_ge": str(seven_days_ago), "create_time_lt": str(now_ts)},
        data_key="orders",
        page_size=50,
        max_pages=40,
    )
    gmv_7d = sum(
        float(o.get("payment", {}).get("total_amount") or 0)
        for o in orders_7d
    )

    # Top products from 7d orders
    product_revenue: Dict[str, float] = {}
    for o in orders_7d:
        for item in (o.get("line_items") or []):
            name   = item.get("product_name") or "?"
            amount = float(item.get("item_price") or 0) * int(item.get("quantity") or 1)
            product_revenue[name] = product_revenue.get(name, 0) + amount
    top_products = sorted(
        [{"name": k, "revenue": round(v, 2)} for k, v in product_revenue.items()],
        key=lambda x: x["revenue"],
        reverse=True,
    )[:5]

    # Conversion rate from analytics endpoint
    conversion_rate = 0.0
    analytics_result = await _tiktok_get(
        "/analytics/202309/shop/metrics",
        {
            "start_date": (today - timedelta(days=7)).strftime("%Y-%m-%d"),
            "end_date": today.strftime("%Y-%m-%d"),
            "metrics": "page_views,order_count",
        },
    )
    metrics = analytics_result.get("data", {}).get("metrics") or {}
    views        = float(metrics.get("page_views") or 0)
    orders_count = float(metrics.get("order_count") or len(orders_7d))
    if views > 0:
        conversion_rate = round(orders_count / views * 100, 2)

    log.info(
        "TikTok analytics: GMV today=%.2f, 7d=%.2f, orders today=%s/7d=%s",
        gmv_today, gmv_7d, len(orders_today), len(orders_7d),
    )
    return {
        "gmv_today": round(gmv_today, 2),
        "gmv_7d": round(gmv_7d, 2),
        "orders_today": len(orders_today),
        "orders_7d": len(orders_7d),
        "top_products": top_products,
        "conversion_rate": conversion_rate,
        "currency": "USD",
    }


async def get_active_promotions(product_id: str) -> List[Dict]:
    """
    Holt aktive Promotions für ein Produkt.
    Wird vor create_tiktok_promotion aufgerufen um Überschneidungen zu verhindern.
    """
    result = await _tiktok_get(
        "/promotion/202309/activities",
        {"product_id": product_id, "status": "ongoing", "page_size": "20"},
    )
    if "error" in result:
        log.warning("get_active_promotions error for product %s: %s", product_id, result["error"])
        return []
    return result.get("data", {}).get("activities") or []


async def create_tiktok_promotion(
    product_id: str, discount_pct: int, duration_hours: int
) -> Dict:
    """
    Erstellt eine TikTok-exklusive Promotion für ein Produkt.
    Prüft vorher auf überschneidende aktive Promotions auf demselben Produkt.
    """
    if not product_id or not product_id.strip():
        return {"error": "product_id is required"}
    if not (1 <= discount_pct <= 90):
        return {"error": "discount_pct must be between 1 and 90"}
    if duration_hours < 1:
        return {"error": "duration_hours must be >= 1"}

    # Check for overlapping active promotions
    active = await get_active_promotions(product_id)
    if active:
        active_ids = [a.get("activity_id") for a in active]
        log.warning(
            "create_tiktok_promotion: product %s already has %s active promotion(s): %s — "
            "cancel them first to avoid overlap",
            product_id, len(active), active_ids,
        )
        return {
            "error": (
                f"Product {product_id} already has {len(active)} active promotion(s). "
                "Cancel existing promotions before creating a new one."
            ),
            "active_promotion_ids": active_ids,
        }

    now      = datetime.now(timezone.utc)
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
        log.info(
            "TikTok promotion created: id=%s (%s%% off product %s for %sh)",
            promo_id, discount_pct, product_id, duration_hours,
        )
        return {
            "success": True,
            "promotion_id": promo_id,
            "product_id": product_id,
            "discount_pct": discount_pct,
            "duration_hours": duration_hours,
            "start": now.isoformat(),
            "end": (now + timedelta(hours=duration_hours)).isoformat(),
        }
    log.warning(
        "TikTok promotion creation failed: code=%s message=%s",
        result.get("code"), result.get("message"),
    )
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
        log.warning("get_combined_revenue: TikTok error: %s", exc)
        results["tiktok"] = {
            "gmv_today": 0.0, "gmv_7d": 0.0, "orders_today": 0, "ok": False,
            "error": str(exc),
        }

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
        results["shopify"] = {
            "revenue_today": 0.0, "orders_today": 0, "ok": False, "error": str(exc),
        }

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
        results["digistore24"] = {
            "revenue_today": 0.0, "orders_today": 0, "ok": False, "error": str(exc),
        }

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

    log.info(
        "Combined revenue: €%.2f today, %s orders across %s platforms",
        total_revenue_eur, total_orders, sum(1 for v in results.values() if v.get("ok")),
    )
    return {
        "platforms": results,
        "total_orders_today": total_orders,
        "total_revenue_eur_today": round(total_revenue_eur, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
