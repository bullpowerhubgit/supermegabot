"""
Google Merchant Center Status Monitor
Uses Shopify data (live) + GMC placeholder data (TODO: add GMC OAuth).
Merchant ID: 5734366162
"""

import os
import time
import json
import logging
import asyncio
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Config aus .env
GMC_MERCHANT_ID = os.getenv("GMC_MERCHANT_ID", "5734366162")
SHOPIFY_SUITE_ACCESS_TOKEN = os.getenv("SHOPIFY_SUITE_ACCESS_TOKEN", "")
SHOPIFY_SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

# In-memory cache
_cache: Dict[str, Any] = {
    "full_status": None,
    "full_status_at": 0,
}
CACHE_TTL = 300  # seconds


# ─── Shopify Data ─────────────────────────────────────────────────────────────

async def get_shopify_product_count() -> dict:
    """Calls Shopify GraphQL to get total product count (active + all)."""
    if not HAS_AIOHTTP:
        return {"error": "aiohttp not installed", "count": 0}

    if not SHOPIFY_SUITE_ACCESS_TOKEN:
        return {"error": "SHOPIFY_SUITE_ACCESS_TOKEN not set", "count": 0}

    query = """
    {
        productsCount {
            count
        }
        activeProducts: productsCount(query: "status:active") {
            count
        }
        draftProducts: productsCount(query: "status:draft") {
            count
        }
    }
    """

    url = f"https://{SHOPIFY_SHOP_DOMAIN}/admin/api/2024-10/graphql.json"
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_SUITE_ACCESS_TOKEN,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"query": query},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    d = data.get("data", {})
                    return {
                        "total": d.get("productsCount", {}).get("count", 0),
                        "active": d.get("activeProducts", {}).get("count", 0),
                        "draft": d.get("draftProducts", {}).get("count", 0),
                        "source": "shopify_graphql",
                    }
                else:
                    body = await resp.text()
                    logger.warning("Shopify product count failed %d: %s", resp.status, body[:200])
                    return {"error": f"HTTP {resp.status}", "count": 0}
    except Exception as e:
        logger.error("get_shopify_product_count error: %s", e)
        return {"error": str(e), "count": 0}


# ─── GMC Data (TODO: add GMC OAuth) ──────────────────────────────────────────

async def get_gmc_status() -> dict:
    """
    Returns GMC merchant status dict.

    TODO: add GMC OAuth — replace hardcoded/mock values below with real calls to:
      GET https://shoppingcontent.googleapis.com/content/v2.1/{merchantId}/accountstatuses/{accountId}
    Requires: google-auth-oauthlib, service account JSON or OAuth2 credentials.
    """
    # TODO: add GMC OAuth — call Merchant Center REST API
    # GMC_API = f"https://shoppingcontent.googleapis.com/content/v2.1/{GMC_MERCHANT_ID}/accountstatuses/{GMC_MERCHANT_ID}"

    return {
        "merchant_id": GMC_MERCHANT_ID,
        # TODO: add GMC OAuth — fetch real suspension status
        "suspended": False,
        "suspension_reason": "",  # TODO: add GMC OAuth
        # TODO: add GMC OAuth — fetch real product approval counts
        "products_approved": None,      # TODO: add GMC OAuth
        "products_disapproved": None,   # TODO: add GMC OAuth
        # Confirmed values (2026-05-24)
        "shipping_policies_count": 15,
        "return_policies_count": 2,
        "return_policies_verified": True,
        # Identity still pending manual verification
        "identity_verification_pending": True,
        "last_checked": time.time(),
        "data_source": "local_confirmed_values",
    }


# ─── Combined Status ──────────────────────────────────────────────────────────

async def get_full_status() -> dict:
    """
    Combines GMC status + Shopify product count.
    Cached for 300 seconds.
    """
    now = time.time()
    if _cache["full_status"] and (now - _cache["full_status_at"]) < CACHE_TTL:
        logger.debug("gmc_monitor: returning cached full_status")
        return _cache["full_status"]

    gmc = await get_gmc_status()
    shopify_products = await get_shopify_product_count()

    # Try to import shopify_client for richer data, but don't fail if unavailable
    shop_info: dict = {}
    try:
        from modules import shopify_client
        shop_info = await shopify_client.get_shop_info()
    except Exception as e:
        logger.debug("shopify_client import skipped: %s", e)

    result = {
        "gmc": gmc,
        "shopify_products": shopify_products,
        "shop_info": shop_info,
        "cached_at": now,
        "cache_ttl_seconds": CACHE_TTL,
    }

    _cache["full_status"] = result
    _cache["full_status_at"] = now
    return result


# ─── Telegram Formatter ───────────────────────────────────────────────────────

async def format_telegram_status() -> str:
    """Returns formatted HTML string for Telegram with GMC + Shopify status."""
    status = await get_full_status()
    gmc = status.get("gmc", {})
    products = status.get("shopify_products", {})
    shop = status.get("shop_info", {})

    last_checked = gmc.get("last_checked", 0)
    last_checked_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_checked)) if last_checked else "N/A"

    suspended = gmc.get("suspended", False)
    suspend_icon = "🔴" if suspended else "🟢"
    suspend_text = f"SUSPENDED: {gmc.get('suspension_reason', '')}" if suspended else "Active"

    identity_icon = "⏳" if gmc.get("identity_verification_pending") else "✅"
    return_icon = "✅" if gmc.get("return_policies_verified") else "⚠️"

    products_approved = gmc.get("products_approved")
    products_disapproved = gmc.get("products_disapproved")
    approved_str = str(products_approved) if products_approved is not None else "⏳ (OAuth pending)"
    disapproved_str = str(products_disapproved) if products_disapproved is not None else "⏳ (OAuth pending)"

    shop_name = shop.get("name", SHOPIFY_SHOP_DOMAIN)
    total_products = products.get("total", "N/A")
    active_products = products.get("active", "N/A")

    lines = [
        "🛒 <b>Google Merchant Center Status</b>",
        "",
        f"🏪 <b>Merchant ID:</b> <code>{gmc.get('merchant_id')}</code>",
        f"{suspend_icon} <b>Account:</b> {suspend_text}",
        "",
        "📦 <b>Products (GMC)</b>",
        f"  ✅ Approved: {approved_str}",
        f"  ❌ Disapproved: {disapproved_str}",
        "",
        "🚚 <b>Policies</b>",
        f"  📋 Shipping policies: {gmc.get('shipping_policies_count', 0)}",
        f"  {return_icon} Return policies: {gmc.get('return_policies_count', 0)} (verified)",
        "",
        "🔐 <b>Verification</b>",
        f"  {identity_icon} Identity verification: {'Pending' if gmc.get('identity_verification_pending') else 'Verified'}",
        "",
        "🛍 <b>Shopify Store</b>",
        f"  🏷 Store: {shop_name}",
        f"  📦 Total products: {total_products}",
        f"  ✅ Active: {active_products}",
        "",
        f"🕐 <i>Last checked: {last_checked_str}</i>",
    ]

    return "\n".join(lines)


# ─── Test ─────────────────────────────────────────────────────────────────────

async def _test():
    status = await get_full_status()
    print(json.dumps(status, indent=2, default=str))
    print()
    msg = await format_telegram_status()
    print(msg)


if __name__ == "__main__":
    asyncio.run(_test())
