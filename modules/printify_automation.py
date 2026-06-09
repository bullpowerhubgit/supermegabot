#!/usr/bin/env python3
"""Printify automation — orders, products, fulfillment, Shopify sync"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("Printify")

_BASE    = "https://api.printify.com/v1"
_TOKEN   = os.getenv("PRINTIFY_API_KEY", "")
_SHOP_ID = os.getenv("PRINTIFY_SHOP_ID", "")
_DATA    = Path(__file__).parent.parent / "data"


def _headers() -> Dict:
    return {"Authorization": f"Bearer {_TOKEN}", "Content-Type": "application/json"}


async def _get(path: str) -> Dict:
    import aiohttp
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.get(f"{_BASE}{path}", headers=_headers()) as r:
            if r.status == 401:
                raise ValueError("Printify API Key ungültig (401)")
            r.raise_for_status()
            return await r.json()


async def _post(path: str, data: Dict) -> Dict:
    import aiohttp
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.post(f"{_BASE}{path}", headers=_headers(), json=data) as r:
            r.raise_for_status()
            return await r.json()


async def ping() -> bool:
    if not _TOKEN:
        return False
    try:
        await _get("/shops.json")
        return True
    except Exception:
        return False


async def get_shops() -> List[Dict]:
    data = await _get("/shops.json")
    return data if isinstance(data, list) else []


async def _shop() -> str:
    """Return configured shop ID or auto-detect first shop."""
    if _SHOP_ID:
        return _SHOP_ID
    shops = await get_shops()
    if shops:
        return str(shops[0]["id"])
    raise ValueError("Kein Printify-Shop gefunden")


async def get_products(limit: int = 20) -> List[Dict]:
    shop = await _shop()
    data = await _get(f"/shops/{shop}/products.json?limit={limit}")
    return data.get("data", [])


async def get_orders(page: int = 1, limit: int = 20) -> List[Dict]:
    shop = await _shop()
    data = await _get(f"/shops/{shop}/orders.json?page={page}&limit={limit}")
    return data.get("data", [])


async def get_pending_orders() -> List[Dict]:
    orders = await get_orders(limit=50)
    return [o for o in orders if o.get("status") in ("pending", "on-hold")]


async def submit_order(order_id: str) -> Dict:
    """Submit a pending order to Printify for fulfillment."""
    shop = await _shop()
    return await _post(f"/shops/{shop}/orders/{order_id}/send_to_production.json", {})


async def auto_fulfill_pending() -> Dict:
    """Find all pending orders and submit them for production."""
    pending = await get_pending_orders()
    submitted = []
    failed = []
    for order in pending:
        oid = order.get("id")
        try:
            await submit_order(oid)
            submitted.append(oid)
        except Exception as e:
            failed.append({"id": oid, "error": str(e)})
    return {"submitted": submitted, "failed": failed, "total_pending": len(pending)}


async def get_stats() -> Dict:
    """Revenue + order counts for dashboard."""
    orders = await get_orders(limit=50)
    today = datetime.now().strftime("%Y-%m-%d")
    today_orders  = [o for o in orders if (o.get("created_at") or "").startswith(today)]
    pending_count = len([o for o in orders if o.get("status") in ("pending", "on-hold")])
    fulfilled     = len([o for o in orders if o.get("status") == "fulfilled"])
    return {
        "total_orders":   len(orders),
        "today_orders":   len(today_orders),
        "pending":        pending_count,
        "fulfilled":      fulfilled,
        "sample_orders":  orders[:5],
    }


async def publish_product_to_shopify(product_id: str) -> Dict:
    """Publish an existing Printify product to the connected Shopify store."""
    shop = await _shop()
    return await _post(
        f"/shops/{shop}/products/{product_id}/publish.json",
        {"title": True, "description": True, "images": True,
         "variants": True, "tags": True, "keyFeatures": True, "shipping_template": True}
    )
