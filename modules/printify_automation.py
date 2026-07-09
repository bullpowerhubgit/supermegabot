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
    # dragonadnp@gmail.com token (expires 2027-06-19) — fallback if PRINTIFY_API_KEY not set
    _DRAGON_TOKEN = (
        "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiIzN2Q0YmQzMDM1ZmUxMWU5YTgwM2FiN2VlYjNjY2M5NyIsImp0"
        "aSI6ImUxZTNlMzU4ODE1YzkwYjE5OGNlNjk0ZDliMjk4Njk2YTVhOTljMmIyNDhlM2Q0N2I5Y2Y2ZTBiZjI2ODVhYjE0MjIyMTA"
        "1ODFiMDk4MWY4IiwiaWF0IjoxNzgxODY4ODI5Ljk0OTEzMywibmJmIjoxNzgxODY4ODI5Ljk0OTEzNSwiZXhwIjoxODEzNDA0OD"
        "I5Ljk0MjY5NCwic3ViIjoiMjc2NTA5MjYiLCJzY29wZXMiOlsic2hvcHMubWFuYWdlIiwic2hvcHMucmVhZCIsImNhdGFsb2cucm"
        "VhZCIsIm9yZGVycy5yZWFkIiwib3JkZXJzLndyaXRlIiwicHJvZHVjdHMucmVhZCIsInByb2R1Y3RzLndyaXRlIiwid2ViaG9va3"
        "MucmVhZCIsIndlYmhvb2tzLndyaXRlIiwidXBsb2Fkcy5yZWFkIiwidXBsb2Fkcy53cml0ZSIsInByaW50X3Byb3ZpZGVycy5yZW"
        "FkIiwidXNlci5pbmZvIl19.Q2sE05qdiBSrb67mZcIf0MoxXIhdmrebxRH-GUBOraGK_DzDQveN25cQKn0Em7Tja8wmGAOx6jOm3"
        "A44vSmSOGlBHYJSQHmpeDluPWbmhFb2IUKH4oKYZJsk4tGDfzDiLZQPfoYwQFpkEoyUDjg0gaSlKUQvPv6fgtiGSb5XHHWjJdgt"
        "XRdgh36sY6wLyq9B3xM6Kvika8Xb4NYEBujZsJjNRFbvHP6tycdS4T_DKmn0Ej3H2f-m0YTr2Eo_t37WDhx8qHjG1Xdwbuo5ab"
        "GRB8r2A_qyomRWQIjx-SI5Fig8yhmTlQiP6yxy3FkMHujsrixODlSokOqra0_HiJEaUiRAaF5iOOOOHjup-4N452w7dLZ8A6JkT"
        "0p0LEPJPFVNrlPGXBXUUty-9KxEmWFP7CE711i2BhVzqIuXm26BzeGO4YS0_rApMIY3uW0Y8d7H6tcjA2gAuk9OFTBguIbEHnb4"
        "LCZUd8unXuzKsskhjgffDayEQCZrSO8aLn7goGHOkpVJ2SUPNOX-AAkMNyDwGAtG0P6sN53yziWqFUaINe9b_0uu11rk0FRpw3k"
        "5m7IDG75Ileln_bWIX8Ei03p-vv7mKnPzCOjHTkBqmbNI9fgkyxj-xZnmRj67csQ8_S-EVBGNOlmDsYLCwbpMnXiiEwW7Y7zsra"
        "zsrilFLyiwKeQ"
    )
    return os.getenv("PRINTIFY_API_KEY", os.getenv("PRINTIFY_API_TOKEN", _DRAGON_TOKEN))


_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"


def _headers() -> Dict:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "User-Agent": _UA,
    }


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
        # BRUTUS: neue Printify Produkte auf allen Kanälen promoten
        try:
            from modules.brutus_traffic_engine import run_brutus_swarm
            await run_brutus_swarm(
                keywords=[f"Print on Demand {published[0]}", "Custom Merchandise 2026"],
                max_keywords=2
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


async def run_with_brutus_traffic() -> Dict:
    """Get Printify stats then fire BRUTUS for POD keywords."""
    stats = await get_stats()
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        brutus = await run_brutus_swarm(
            keywords=["Print on Demand Shop 2026", "Custom Mug Design", "Personalisierte Geschenke"],
            max_keywords=3
        )
        return {"stats": stats, "brutus": brutus, "ok": True}
    except Exception as e:
        return {"stats": stats, "brutus_error": str(e), "ok": False}


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
