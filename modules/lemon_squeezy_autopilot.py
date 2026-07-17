#!/usr/bin/env python3
"""
Lemon Squeezy Autopilot — shop products, variants, checkout links without manual UI.

Requires:
  LEMON_SQUEEZY_API_KEY (or LEMON_API_KEY)
  LEMON_SQUEEZY_STORE_ID (or LEMON_STORE_ID)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

log = logging.getLogger("LemonSqueezyAutopilot")

API = "https://api.lemonsqueezy.com/v1"
API_KEY = (
    os.getenv("LEMON_SQUEEZY_API_KEY")
    or os.getenv("LEMON_API_KEY")
    or ""
)
STORE_ID = (
    os.getenv("LEMON_SQUEEZY_STORE_ID")
    or os.getenv("LEMON_STORE_ID")
    or ""
)

# Default SuperMegaBot catalog (EUR cents)
DEFAULT_CATALOG = [
    {
        "name": "SuperMegaBot Starter",
        "description": "E-commerce automation starter — Shopify, bots, autopost.",
        "price_cents": 4900,
        "slug": "supermegabot-starter",
    },
    {
        "name": "SuperMegaBot Pro",
        "description": "Full automation suite — multi-shop, AI agents, priority support.",
        "price_cents": 9900,
        "slug": "supermegabot-pro",
    },
    {
        "name": "SuperMegaBot Enterprise",
        "description": "Agency / multi-client automation + white-label options.",
        "price_cents": 29900,
        "slug": "supermegabot-enterprise",
    },
]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }


def configured() -> bool:
    return bool(API_KEY and STORE_ID)


async def _request(method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
    if not configured():
        return {"ok": False, "skipped": True, "reason": "LEMON_SQUEEZY_API_KEY/STORE_ID missing"}
    url = f"{API}{path}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.request(
                method,
                url,
                headers=_headers(),
                data=json.dumps(payload) if payload else None,
            ) as r:
                text = await r.text()
                try:
                    data = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    data = {"raw": text[:300]}
                return {"ok": r.status < 400, "status": r.status, "data": data}
    except Exception as e:
        log.warning("Lemon request failed %s %s: %s", method, path, e)
        return {"ok": False, "error": str(e)[:200]}


async def list_products() -> dict[str, Any]:
    res = await _request("GET", f"/products?filter[store_id]={STORE_ID}")
    if not res.get("ok"):
        return res
    items = (res.get("data") or {}).get("data") or []
    products = []
    for it in items:
        attrs = it.get("attributes") or {}
        products.append({
            "id": it.get("id"),
            "name": attrs.get("name"),
            "status": attrs.get("status"),
            "buy_now_url": attrs.get("buy_now_url") or attrs.get("url"),
            "price": attrs.get("price"),
        })
    return {"ok": True, "count": len(products), "products": products}


async def ensure_catalog(catalog: list[dict] | None = None) -> dict[str, Any]:
    """Create missing products from catalog; skip names that already exist."""
    catalog = catalog or DEFAULT_CATALOG
    existing = await list_products()
    if existing.get("skipped"):
        return existing
    if not existing.get("ok"):
        return existing

    names = {p.get("name", "").lower() for p in existing.get("products") or []}
    created = []
    skipped = []
    errors = []

    for item in catalog:
        name = item["name"]
        if name.lower() in names:
            skipped.append(name)
            continue
        payload = {
            "data": {
                "type": "products",
                "attributes": {
                    "name": name[:150],
                    "description": (item.get("description") or "")[:2000],
                    "status": "published",
                    "price": int(item.get("price_cents") or 1000),
                },
                "relationships": {
                    "store": {"data": {"type": "stores", "id": str(STORE_ID)}}
                },
            }
        }
        res = await _request("POST", "/products", payload)
        if res.get("ok"):
            data = (res.get("data") or {}).get("data") or {}
            attrs = data.get("attributes") or {}
            created.append({
                "name": name,
                "id": data.get("id"),
                "buy_now_url": attrs.get("buy_now_url") or attrs.get("url"),
            })
        else:
            errors.append({"name": name, "error": str(res)[:200]})

    return {
        "ok": True,
        "created": created,
        "skipped_existing": skipped,
        "errors": errors,
        "existing_count": existing.get("count", 0),
        "at": datetime.now(timezone.utc).isoformat(),
    }


async def list_orders(page_size: int = 10) -> dict[str, Any]:
    res = await _request("GET", f"/orders?page[size]={page_size}&filter[store_id]={STORE_ID}")
    if not res.get("ok"):
        return res
    items = (res.get("data") or {}).get("data") or []
    orders = []
    for it in items:
        attrs = it.get("attributes") or {}
        orders.append({
            "id": it.get("id"),
            "status": attrs.get("status"),
            "total": attrs.get("total"),
            "user_email": attrs.get("user_email"),
            "created_at": attrs.get("created_at"),
        })
    return {"ok": True, "count": len(orders), "orders": orders}


async def run_lemon_cycle() -> dict[str, Any]:
    """Daily/periodic autopilot: ensure catalog + snapshot orders."""
    if not configured():
        return {
            "ok": False,
            "skipped": True,
            "reason": "Set LEMON_SQUEEZY_API_KEY + LEMON_SQUEEZY_STORE_ID",
        }
    catalog = await ensure_catalog()
    orders = await list_orders()
    return {
        "ok": True,
        "catalog": catalog,
        "orders": orders,
        "at": datetime.now(timezone.utc).isoformat(),
    }
