"""
TikTok Shop Sync
================
Syncs Shopify products to TikTok Shop, fetches orders, analytics,
combined revenue, and creates flash promotions.
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("TikTokShopSync")

TIKTOK_APP_KEY    = os.getenv("TIKTOK_APP_KEY", "")
TIKTOK_APP_SECRET = os.getenv("TIKTOK_APP_SECRET", "")
TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")
TIKTOK_SHOP_ID    = os.getenv("TIKTOK_SHOP_ID", "")
SHOPIFY_DOMAIN    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN     = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_VERSION   = os.getenv("SHOPIFY_API_VERSION", "2024-01")

DATA_DIR          = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
SYNC_STATE_FILE   = DATA_DIR / "tiktok_sync_state.json"

TT_BASE = "https://open-api.tiktok.com/api/v1"


def _load_sync_state() -> dict:
    try:
        return json.loads(SYNC_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_sync_state(s: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SYNC_STATE_FILE.write_text(json.dumps(s, indent=2))


def _tt_headers() -> dict:
    return {
        "Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "x-tts-access-token": TIKTOK_ACCESS_TOKEN,
    }


def _configured() -> bool:
    return bool(TIKTOK_ACCESS_TOKEN and TIKTOK_SHOP_ID)


async def _shopify_products(limit: int = 50) -> list:
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return []
    try:
        import aiohttp
        url = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/products.json"
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url,
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                params={"limit": limit, "status": "active",
                        "fields": "id,title,body_html,images,variants"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        return data.get("products", [])
    except Exception as e:
        log.warning("Shopify products fetch error: %s", e)
        return []


async def sync_products_to_tiktok(limit: int = 50) -> dict:
    """Push Shopify products to TikTok Shop product catalog."""
    if not _configured():
        return {
            "ok": False,
            "error": "TikTok not configured — set TIKTOK_ACCESS_TOKEN and TIKTOK_SHOP_ID in Railway",
            "synced": 0,
        }

    products = await _shopify_products(limit)
    if not products:
        return {"ok": False, "error": "No Shopify products found", "synced": 0}

    state   = _load_sync_state()
    synced  = 0
    skipped = 0

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            for p in products:
                pid  = str(p["id"])
                variant = (p.get("variants") or [{}])[0]
                image   = (p.get("images") or [{}])[0].get("src", "")
                price   = float(variant.get("price", 0) or 0)
                sku     = variant.get("sku", "") or pid

                if state.get(pid, {}).get("synced") and not state.get(pid, {}).get("needs_update"):
                    skipped += 1
                    continue

                payload = {
                    "product_name": p.get("title", "")[:255],
                    "description": (p.get("body_html") or "")[:5000],
                    "skus": [{
                        "seller_sku": sku[:50],
                        "price": {"amount": str(int(price * 100)), "currency": "EUR"},
                        "quantity_value": int(variant.get("inventory_quantity", 0) or 0),
                    }],
                    "images": [{"img_url": image}] if image else [],
                }

                async with session.post(
                    f"{TT_BASE}/products",
                    headers=_tt_headers(),
                    params={"shop_id": TIKTOK_SHOP_ID},
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    resp = await r.json(content_type=None)
                    if resp.get("code") == 0 or r.status in (200, 201):
                        state[pid] = {
                            "synced": True,
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "tiktok_id": resp.get("data", {}).get("product_id", ""),
                        }
                        synced += 1
                        log.info("TikTok synced: %s", p.get("title", pid))
                    else:
                        log.warning("TikTok sync failed for %s: %s", pid, resp)
    except Exception as e:
        log.error("TikTok sync error: %s", e)
        return {"ok": False, "error": str(e), "synced": synced}

    _save_sync_state(state)
    return {
        "ok": True,
        "synced": synced,
        "skipped": skipped,
        "total_shopify": len(products),
    }


async def get_tiktok_orders(days: int = 7) -> list:
    """Fetch TikTok Shop orders from the last N days."""
    if not _configured():
        return []
    try:
        import aiohttp
        start_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        end_ts   = int(datetime.now(timezone.utc).timestamp())

        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{TT_BASE}/orders/search",
                headers=_tt_headers(),
                params={"shop_id": TIKTOK_SHOP_ID},
                json={
                    "create_time_ge": start_ts,
                    "create_time_lt": end_ts,
                    "page_size": 100,
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        orders = data.get("data", {}).get("orders", [])
        log.info("TikTok orders fetched: %d (last %d days)", len(orders), days)
        return orders
    except Exception as e:
        log.warning("TikTok orders error: %s", e)
        return []


async def get_tiktok_analytics() -> dict:
    """Return TikTok Shop performance analytics."""
    if not _configured():
        return {
            "configured": False,
            "error": "TIKTOK_ACCESS_TOKEN and TIKTOK_SHOP_ID required",
        }
    try:
        orders = await get_tiktok_orders(days=30)
        revenue = sum(
            float(o.get("total_amount", 0) or 0)
            for o in orders
            if o.get("status") not in ("CANCELLED", "REFUNDED")
        )
        return {
            "configured": True,
            "shop_id": TIKTOK_SHOP_ID,
            "orders_30d": len(orders),
            "revenue_30d_eur": round(revenue / 100, 2),
            "avg_order_value": round(revenue / max(len(orders), 1) / 100, 2),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        log.warning("TikTok analytics error: %s", e)
        return {"configured": True, "error": str(e)}


async def get_combined_revenue() -> dict:
    """Combined revenue from TikTok Shop + Shopify."""
    tt_analytics = await get_tiktok_analytics()
    tt_revenue   = tt_analytics.get("revenue_30d_eur", 0)

    shopify_revenue = 0.0
    try:
        import aiohttp
        if SHOPIFY_DOMAIN and SHOPIFY_TOKEN:
            start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            url   = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/orders.json"
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    url,
                    headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                    params={"status": "paid", "created_at_min": start, "fields": "total_price", "limit": 250},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    data = await r.json(content_type=None)
            for o in data.get("orders", []):
                try:
                    shopify_revenue += float(o.get("total_price", 0) or 0)
                except Exception:
                    pass
    except Exception as e:
        log.warning("Shopify revenue fetch error: %s", e)

    total = round(tt_revenue + shopify_revenue, 2)
    return {
        "tiktok_revenue_30d": tt_revenue,
        "shopify_revenue_30d": round(shopify_revenue, 2),
        "combined_revenue_30d": total,
        "currency": "EUR",
        "period": "30d",
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def create_tiktok_promotion(product_id: str, discount_pct: int = 10, hours: int = 24) -> dict:
    """Create a flash promotion on TikTok Shop for a product."""
    if not _configured():
        return {"success": False, "error": "TikTok not configured"}
    if not 1 <= discount_pct <= 90:
        return {"success": False, "error": "discount_pct must be 1–90"}

    try:
        import aiohttp
        now      = datetime.now(timezone.utc)
        end_time = now + timedelta(hours=hours)
        payload  = {
            "product_id": product_id,
            "discount_percentage": discount_pct,
            "begin_time": int(now.timestamp()),
            "end_time": int(end_time.timestamp()),
            "promotion_name": f"Flash Sale -{discount_pct}% ({hours}h)",
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{TT_BASE}/promotions",
                headers=_tt_headers(),
                params={"shop_id": TIKTOK_SHOP_ID},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
        success = data.get("code") == 0
        return {
            "success": success,
            "product_id": product_id,
            "discount_pct": discount_pct,
            "hours": hours,
            "ends_at": end_time.isoformat(),
            "promotion_id": data.get("data", {}).get("promotion_id", ""),
            "raw": data if not success else {},
        }
    except Exception as e:
        log.warning("TikTok promotion error: %s", e)
        return {"success": False, "error": str(e)}


async def exchange_oauth_code(code: str, shop_id: str = "") -> dict:
    """Exchange TikTok Shop OAuth auth_code for access token."""
    app_key    = TIKTOK_APP_KEY
    app_secret = TIKTOK_APP_SECRET
    if not app_key or not app_secret:
        return {"ok": False, "error": "TIKTOK_APP_KEY and TIKTOK_APP_SECRET required"}
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://auth.tiktok-shops.com/api/v2/token/get",
                params={
                    "app_key":    app_key,
                    "app_secret": app_secret,
                    "auth_code":  code,
                    "grant_type": "authorized_code",
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        if data.get("code") == 0:
            token = data.get("data", {}).get("access_token", "")
            log.info("TikTok OAuth success, token: %s...", token[:8])
            return {"ok": True, "access_token": token, "raw": data.get("data", {})}
        return {"ok": False, "error": str(data.get("message", data))}
    except Exception as e:
        log.warning("TikTok OAuth exchange error: %s", e)
        return {"ok": False, "error": str(e)}


async def run_with_brutus_traffic() -> dict:
    """Sync products to TikTok Shop and launch BRUTUS traffic blast."""
    sync_result = await sync_products_to_tiktok()
    try:
        from modules.brutus_traffic_engine import brutus_blast_for_tool
        keywords = [
            "TikTok Shop Produkte", "Online Shop TikTok", "TikTok eCommerce",
            "Produkte TikTok kaufen", "TikTok Dropshipping", "TikTok viral Produkte",
        ]
        blast_result = await brutus_blast_for_tool("TikTok Shop", "https://www.tiktok.com/", keywords)
    except Exception as e:
        blast_result = {"error": str(e)}
    return {"sync": sync_result, "brutus": blast_result}
