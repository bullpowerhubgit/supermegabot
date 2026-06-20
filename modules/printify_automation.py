#!/usr/bin/env python3
"""Printify — vollautonome Print-on-Demand Pipeline: Shops, Produkte, Bestellungen, Fulfillment, Shopify-Sync."""

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("Printify")

_BASE = "https://api.printify.com/v1"
_DATA = Path(__file__).parent.parent / "data"
_DATA.mkdir(exist_ok=True)
_SHOP_CACHE = _DATA / "printify_shop.json"

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")


def _token() -> str:
    return os.getenv("PRINTIFY_API_KEY", "")


def _headers() -> Dict:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


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
                raise ValueError("PRINTIFY_API_KEY ungültig (401) — neuen Key von printify.com holen")
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
        await _get("/shops.json")
        return True
    except Exception:
        return False


async def get_shops() -> List[Dict]:
    data = await _get("/shops.json")
    return data if isinstance(data, list) else []


async def _shop_id() -> str:
    """Auto-detect shop ID — from env, then Railway, then cache, then API."""
    sid = os.getenv("PRINTIFY_SHOP_ID", "")
    if sid:
        return sid
    if _SHOP_CACHE.exists():
        try:
            cached = json.loads(_SHOP_CACHE.read_text())
            return str(cached["shop_id"])
        except Exception:
            pass
    shops = await get_shops()
    if not shops:
        raise ValueError("Kein Printify-Shop gefunden")
    sid = str(shops[0]["id"])
    _SHOP_CACHE.write_text(json.dumps({"shop_id": sid, "title": shops[0].get("title", "?"), "ts": datetime.now().isoformat()}))
    _set_railway("PRINTIFY_SHOP_ID", sid)
    log.info("Printify Shop-ID auto-detected: %s", sid)
    return sid


async def get_products(limit: int = 50) -> List[Dict]:
    shop = await _shop_id()
    data = await _get(f"/shops/{shop}/products.json?limit={limit}")
    return data.get("data", [])


async def get_orders(page: int = 1, limit: int = 50) -> List[Dict]:
    shop = await _shop_id()
    data = await _get(f"/shops/{shop}/orders.json?page={page}&limit={limit}")
    return data.get("data", [])


async def get_pending_orders() -> List[Dict]:
    orders = await get_orders(limit=50)
    return [o for o in orders if o.get("status") in ("pending", "on-hold")]


async def submit_order(order_id: str) -> Dict:
    shop = await _shop_id()
    return await _post(f"/shops/{shop}/orders/{order_id}/send_to_production.json", {})


async def auto_fulfill_pending() -> Dict:
    """Find all pending orders and submit them to Printify production."""
    pending = await get_pending_orders()
    submitted, failed = [], []
    for order in pending:
        oid = order.get("id")
        try:
            await submit_order(oid)
            submitted.append(oid)
            log.info("Printify order %s → production", oid)
        except Exception as e:
            failed.append({"id": oid, "error": str(e)})
            log.warning("Printify order %s failed: %s", oid, e)

    if submitted:
        await _tg(
            f"🖨️ <b>Printify Auto-Fulfill</b>\n"
            f"✅ {len(submitted)} Bestellungen an Produktion gesendet\n"
            f"❌ {len(failed)} Fehler\n"
            f"IDs: {', '.join(str(x) for x in submitted[:5])}"
        )
    return {"submitted": submitted, "failed": failed, "total_pending": len(pending)}


async def publish_product_to_shopify(product_id: str) -> Dict:
    """Publish a Printify product to the connected Shopify store."""
    shop = await _shop_id()
    return await _post(
        f"/shops/{shop}/products/{product_id}/publish.json",
        {"title": True, "description": True, "images": True,
         "variants": True, "tags": True, "keyFeatures": True, "shipping_template": True}
    )


async def sync_all_products_to_shopify() -> Dict:
    """Push all unpublished Printify products to Shopify."""
    products = await get_products(limit=50)
    published, failed, already = [], [], 0
    for p in products:
        if p.get("external", {}).get("id"):
            already += 1
            continue
        try:
            await publish_product_to_shopify(p["id"])
            published.append(p.get("title", p["id"]))
        except Exception as e:
            failed.append({"id": p["id"], "error": str(e)})

    if published:
        await _tg(
            f"🛍️ <b>Printify→Shopify Sync</b>\n"
            f"✅ {len(published)} Produkte neu veröffentlicht\n"
            f"Already live: {already} | Fehler: {len(failed)}\n"
            f"Neu: {', '.join(published[:5])}"
        )
        # BrutusCore: neue Printify Produkte auf allen Kanälen promoten
        try:
            from modules.brutus_core import fire as brutus_fire
            for name in published[:2]:
                await brutus_fire(
                    title=f"🖨️ Neu im Shop: {name}",
                    body=f"Frisch verfügbar: {name} — personalisiert, auf Bestellung gedruckt, direkt an dich geliefert.",
                    link=f"https://ineedit.com.co",
                    niche="print on demand geschenke",
                    tags=["printify", "neu", "print-on-demand"]
                )
        except Exception:
            pass
    return {"published": len(published), "already_live": already, "failed": len(failed)}


async def get_stats() -> Dict:
    orders = await get_orders(limit=50)
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "total_orders":   len(orders),
        "today_orders":   len([o for o in orders if (o.get("created_at") or "").startswith(today)]),
        "pending":        len([o for o in orders if o.get("status") in ("pending", "on-hold")]),
        "fulfilled":      len([o for o in orders if o.get("status") == "fulfilled"]),
        "products":       len(await get_products()),
    }


async def handle_shopify_order(shopify_order: Dict) -> Dict:
    """Called when Shopify webhook fires — submit matching Printify order."""
    shop = await _shop_id()
    line_items = shopify_order.get("line_items", [])
    shipping = shopify_order.get("shipping_address", {})
    order_number = shopify_order.get("order_number", "?")

    printify_line_items = []
    for item in line_items:
        variant_id = item.get("variant_id")
        if variant_id:
            printify_line_items.append({
                "product_id": str(item.get("product_id", "")),
                "variant_id": str(variant_id),
                "quantity": item.get("quantity", 1),
            })

    if not printify_line_items:
        return {"ok": False, "reason": "no printify items"}

    payload = {
        "external_id": str(shopify_order.get("id")),
        "label": f"Shopify #{order_number}",
        "line_items": printify_line_items,
        "shipping_method": 1,
        "address_to": {
            "first_name": shipping.get("first_name", ""),
            "last_name":  shipping.get("last_name", ""),
            "email":      shopify_order.get("email", ""),
            "phone":      shipping.get("phone", ""),
            "country":    shipping.get("country_code", "DE"),
            "region":     shipping.get("province_code", ""),
            "address1":   shipping.get("address1", ""),
            "address2":   shipping.get("address2", ""),
            "city":       shipping.get("city", ""),
            "zip":        shipping.get("zip", ""),
        },
        "send_shipping_notification": True,
    }
    try:
        result = await _post(f"/shops/{shop}/orders.json", payload)
        await _tg(f"🖨️ Shopify #{order_number} → Printify Produktion gesendet ✅")
        return {"ok": True, "printify_order_id": result.get("id")}
    except Exception as e:
        return {"ok": False, "error": str(e)}
