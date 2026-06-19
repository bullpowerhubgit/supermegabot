#!/usr/bin/env python3
"""Printful — vollautonome Print-on-Demand Pipeline: Produkte, Bestellungen, Fulfillment, Shopify-Sync."""

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("Printful")

_BASE = "https://api.printful.com"
_DATA = Path(__file__).parent.parent / "data"
_DATA.mkdir(exist_ok=True)
_STORE_CACHE = _DATA / "printful_store.json"

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")


def _token() -> str:
    return os.getenv("PRINTFUL_API_KEY", "")


def _store_id() -> str:
    return os.getenv("PRINTFUL_STORE_ID", "")


def _headers() -> Dict:
    h = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}
    sid = _store_id()
    if sid:
        h["X-PF-Store-Id"] = sid
    return h


def _set_railway(key: str, value: str) -> None:
    try:
        subprocess.run(
            ["railway", "variables", "set", f"{key}={value}", "--service", "dudirudibot-mega"],
            capture_output=True, timeout=30
        )
    except Exception:
        pass


async def _tg(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


async def _get(path: str) -> Dict:
    import aiohttp
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        async with s.get(f"{_BASE}{path}", headers=_headers()) as r:
            if r.status == 401:
                raise ValueError("PRINTFUL_API_KEY ungültig (401) — Key von printful.com → Settings → API")
            r.raise_for_status()
            return await r.json()


async def _post(path: str, data: Dict) -> Dict:
    import aiohttp
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        async with s.post(f"{_BASE}{path}", headers=_headers(), json=data) as r:
            r.raise_for_status()
            return await r.json()


async def ping() -> bool:
    if not _token():
        return False
    try:
        await _get("/stores")
        return True
    except Exception:
        return False


async def get_stores() -> List[Dict]:
    data = await _get("/stores")
    return data.get("result", [])


async def auto_detect_store() -> str:
    """Detect store ID — from env, cache, or API."""
    sid = _store_id()
    if sid:
        return sid
    if _STORE_CACHE.exists():
        try:
            return str(json.loads(_STORE_CACHE.read_text())["store_id"])
        except Exception:
            pass
    stores = await get_stores()
    if not stores:
        raise ValueError("Kein Printful-Store gefunden")
    sid = str(stores[0]["id"])
    name = stores[0].get("name", "?")
    _STORE_CACHE.write_text(json.dumps({"store_id": sid, "name": name, "ts": datetime.now().isoformat()}))
    _set_railway("PRINTFUL_STORE_ID", sid)
    log.info("Printful Store auto-detected: %s (%s)", name, sid)
    await _tg(f"🖨️ <b>Printful Store gefunden:</b> {name} (ID: <code>{sid}</code>)")
    return sid


async def get_sync_products(limit: int = 100) -> List[Dict]:
    """Get all products synced with Shopify."""
    data = await _get(f"/sync/products?limit={limit}")
    return data.get("result", [])


async def get_orders(status: str = "", limit: int = 100) -> List[Dict]:
    path = f"/orders?limit={limit}"
    if status:
        path += f"&status={status}"
    data = await _get(path)
    return data.get("result", [])


async def get_pending_orders() -> List[Dict]:
    return await get_orders(status="pending")


async def confirm_order(order_id: int) -> Dict:
    """Confirm a draft order — sends it to production."""
    return await _post(f"/orders/{order_id}/confirm", {})


async def auto_fulfill_pending() -> Dict:
    """Confirm all pending/draft Printful orders → production."""
    pending = await get_pending_orders()
    confirmed, failed = [], []
    for order in pending:
        oid = order.get("id")
        try:
            await confirm_order(oid)
            confirmed.append(oid)
            log.info("Printful order %s confirmed → production", oid)
        except Exception as e:
            failed.append({"id": oid, "error": str(e)})
            log.warning("Printful order %s failed: %s", oid, e)

    if confirmed:
        await _tg(
            f"🖨️ <b>Printful Auto-Fulfill</b>\n"
            f"✅ {len(confirmed)} Bestellungen bestätigt\n"
            f"❌ {len(failed)} Fehler"
        )
    return {"confirmed": confirmed, "failed": failed, "total_pending": len(pending)}


async def create_order_from_shopify(shopify_order: Dict) -> Dict:
    """Create Printful order from Shopify order data."""
    order_number = shopify_order.get("order_number", "?")
    shipping = shopify_order.get("shipping_address", {})
    line_items = shopify_order.get("line_items", [])

    # Map Shopify line items to Printful format
    pf_items = []
    for item in line_items:
        pf_items.append({
            "sync_variant_id": item.get("variant_id"),
            "quantity": item.get("quantity", 1),
        })

    if not pf_items:
        return {"ok": False, "reason": "no items"}

    payload = {
        "external_id": f"shopify_{shopify_order.get('id')}",
        "shipping": "STANDARD",
        "recipient": {
            "name":       f"{shipping.get('first_name','')} {shipping.get('last_name','')}".strip(),
            "email":      shopify_order.get("email", ""),
            "phone":      shipping.get("phone", ""),
            "address1":   shipping.get("address1", ""),
            "address2":   shipping.get("address2", ""),
            "city":       shipping.get("city", ""),
            "state_code": shipping.get("province_code", ""),
            "country_code": shipping.get("country_code", "DE"),
            "zip":        shipping.get("zip", ""),
        },
        "items": pf_items,
    }
    try:
        result = await _post("/orders", payload)
        order_id = result.get("result", {}).get("id")
        # Auto-confirm immediately
        if order_id:
            await confirm_order(order_id)
        await _tg(f"🖨️ Shopify #{order_number} → Printful Produktion ✅ (Order ID: {order_id})")
        return {"ok": True, "printful_order_id": order_id}
    except Exception as e:
        log.warning("Printful order creation failed: %s", e)
        return {"ok": False, "error": str(e)}


async def get_stats() -> Dict:
    try:
        orders = await get_orders(limit=100)
        today = datetime.now().strftime("%Y-%m-%d")
        products = await get_sync_products()
        return {
            "total_orders":  len(orders),
            "today_orders":  len([o for o in orders if (o.get("created", "") or "").startswith(today)]),
            "pending":       len([o for o in orders if o.get("status") in ("pending", "draft")]),
            "fulfilled":     len([o for o in orders if o.get("status") == "fulfilled"]),
            "sync_products": len(products),
        }
    except Exception as e:
        return {"error": str(e)}


async def sync_catalog_to_shopify() -> Dict:
    """Ensure all Printful products are properly synced to Shopify."""
    products = await get_sync_products()
    synced = [p for p in products if p.get("synced", 0) > 0]
    unsynced = [p for p in products if p.get("synced", 0) == 0]

    if unsynced:
        await _tg(
            f"⚠️ <b>Printful Sync-Problem:</b>\n"
            f"{len(unsynced)} Produkte nicht mit Shopify verknüpft:\n"
            + "\n".join(f"• {p.get('name', p.get('id'))}" for p in unsynced[:5])
            + "\nprintful.com → Stores → Sync needed"
        )
    return {"synced": len(synced), "unsynced": len(unsynced), "total": len(products)}
