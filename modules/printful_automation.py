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


REDIRECT_URL = "https://supermegabot-production.up.railway.app/api/printful/callback"


def _token() -> str:
    return os.getenv("PRINTFUL_API_KEY", "")


def _client_id() -> str:
    return os.getenv("PRINTFUL_CLIENT_ID", "")


def _client_secret() -> str:
    return os.getenv("PRINTFUL_CLIENT_SECRET", "")


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
    stores = await get_stores()
    if not stores:
        return []
    try:
        data = await _get(f"/sync/products?limit={limit}")
        return data.get("result", [])
    except Exception:
        return []


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
        stores = await get_stores()
        if not stores:
            return {
                "total_orders": 0, "today_orders": 0,
                "pending": 0, "fulfilled": 0, "sync_products": 0,
                "notice": "No store connected — link Shopify at printful.com/dashboard/stores",
            }
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


async def get_products(limit: int = 100) -> List[Dict]:
    """List all synced Printful products."""
    try:
        return await get_sync_products(limit=limit)
    except Exception as e:
        log.warning("get_products error: %s", e)
        return []


async def create_product(name: str, description: str = "", product_type: str = "T-Shirt") -> Dict:
    """Auto-create a Printful product using Claude Haiku to generate description if not provided."""
    # Auto-generate description via Claude Haiku if missing
    if not description:
        try:
            import aiohttp
            anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
            if anthropic_key:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01",
                                 "Content-Type": "application/json"},
                        json={"model": "claude-haiku-4-5-20251001", "max_tokens": 200,
                              "messages": [{"role": "user",
                                            "content": f"Write a short 2-sentence product description for a print-on-demand {product_type} called '{name}'. Keep it catchy and e-commerce ready."}]}
                    ) as r:
                        d = await r.json(content_type=None)
                description = d.get("content", [{}])[0].get("text", f"Premium quality {product_type} — {name}.")
        except Exception:
            description = f"Premium quality {product_type} — {name}. Perfect for print-on-demand."

    payload = {
        "sync_product": {"name": name, "description": description},
        "sync_variants": [],
    }
    try:
        result = await _post("/sync/products", payload)
        product_id = result.get("result", {}).get("id")
        log.info("Printful product created: %s (ID: %s)", name, product_id)
        await _tg(f"🖨️ <b>Printful Produkt erstellt:</b> {name} (ID: {product_id})")
        return {"ok": True, "product_id": product_id, "name": name, "description": description}
    except Exception as e:
        log.warning("create_product error: %s", e)
        return {"ok": False, "error": str(e)}


async def run_with_brutus_traffic() -> Dict:
    """Get Printful stats then fire BRUTUS for print-on-demand keywords."""
    stats = await get_stats()
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        brutus_result = await run_brutus_swarm(
            keywords=["Print on Demand 2026", "Custom T-Shirt Shop", "Printful Shopify"],
            max_keywords=3
        )
        return {
            "stats": stats,
            "brutus": brutus_result,
            "ok": True,
        }
    except ImportError:
        log.warning("brutus_traffic_engine not available")
        return {"stats": stats, "brutus": None, "ok": True, "note": "BRUTUS not available"}
    except Exception as e:
        log.warning("run_with_brutus_traffic error: %s", e)
        return {"stats": stats, "brutus_error": str(e), "ok": False}


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


# ── OAuth2 Flow ───────────────────────────────────────────────────────────────

def get_oauth_url(state: str = "supermegabot") -> str:
    """Build Printful OAuth authorization URL."""
    from urllib.parse import urlencode
    params = urlencode({
        "client_id": _client_id(),
        "redirect_url": REDIRECT_URL,
        "state": state,
    })
    return f"https://www.printful.com/oauth/authorize?{params}"


async def exchange_oauth_code(code: str) -> Dict:
    """Exchange authorization code for access token, save to Railway."""
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://www.printful.com/oauth/token",
            json={
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "code": code,
                "redirect_url": REDIRECT_URL,
            },
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            data = await r.json(content_type=None)

    token = data.get("access_token", "")
    if not token:
        log.error("Printful OAuth token exchange failed: %s", data)
        return {"ok": False, "error": str(data)}

    _set_railway("PRINTFUL_API_KEY", token)
    log.info("Printful OAuth token saved — store connection active")
    await _tg("🖨️ <b>Printful verbunden!</b> OAuth Token gespeichert. Store-Sync startet automatisch.")
    return {"ok": True, "token_saved": True}
