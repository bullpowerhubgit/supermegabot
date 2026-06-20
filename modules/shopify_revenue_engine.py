"""Shopify Revenue Engine — Flash sales, cart recovery, pricing, upsells, AI descriptions."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("ShopifyRevenueEngine")
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
_FLASH_BACKUP = DATA_DIR / "flash_sale_backup.json"


# ── Shopify helpers ──────────────────────────────────────────────────────────

async def _products(limit: int = 250) -> list[dict]:
    try:
        from modules.shopify_client import get_products
        return await get_products(limit=limit, status="any")
    except Exception as e:
        log.warning("shopify products fetch failed: %s", e)
        return []


async def _orders(limit: int = 250) -> list[dict]:
    try:
        from modules.shopify_client import get_orders
        return await get_orders(limit=limit, status="any")
    except Exception as e:
        log.warning("shopify orders fetch failed: %s", e)
        return []


async def _rest_get(endpoint: str) -> dict:
    try:
        from modules.shopify_client import rest_get
        return await rest_get(endpoint)
    except Exception as e:
        log.warning("shopify rest_get %s failed: %s", endpoint, e)
        return {}


async def _graphql(query: str, variables: dict | None = None) -> dict:
    try:
        from modules.shopify_client import graphql
        return await graphql(query, variables)
    except Exception as e:
        log.warning("shopify graphql failed: %s", e)
        return {}


async def _update_variant_price(variant_id: str | int, price: str) -> bool:
    """Update a variant price via REST."""
    import aiohttp
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    version = os.getenv("SHOPIFY_API_VERSION", "2024-01")
    if not domain or not token:
        return False
    url = f"https://{domain}/admin/api/{version}/variants/{variant_id}.json"
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as s:
        async with s.put(url, json={"variant": {"id": variant_id, "price": price}}, headers=headers) as r:
            return r.status in (200, 201)


# ── Revenue Summary ───────────────────────────────────────────────────────────

async def get_revenue_summary() -> dict:
    try:
        from modules.shopify_client import get_analytics_summary
        summary = await get_analytics_summary()
        return {
            "today": summary.get("today_revenue", 0),
            "last_7_days": summary.get("week_revenue", 0),
            "last_30_days": summary.get("month_revenue", 0),
            "total_orders": summary.get("total_orders", 0),
            "open_orders": summary.get("open_orders", 0),
            "currency": summary.get("currency", "EUR"),
            "source": "shopify",
        }
    except Exception as e:
        log.warning("revenue summary error: %s", e)
        return {"today": 0, "last_7_days": 0, "last_30_days": 0, "total_orders": 0, "error": str(e)}


async def get_full_dashboard() -> dict:
    """Combined: revenue + carts + inventory."""
    revenue = await get_revenue_summary()
    carts = await get_abandoned_carts(24)
    inventory = await get_low_inventory(5)
    products = await get_product_performance(30)
    return {
        "revenue": revenue,
        "abandoned_carts": {"count": len(carts), "items": carts[:5]},
        "low_inventory": {"count": len(inventory), "items": inventory[:10]},
        "performance": products,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Abandoned Carts ───────────────────────────────────────────────────────────

async def get_abandoned_carts(hours: int = 24) -> list[dict]:
    data = await _rest_get(f"checkouts.json?limit=50&status=open")
    checkouts = data.get("checkouts", [])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = []
    for c in checkouts:
        updated = c.get("updated_at", "")
        try:
            dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            if dt < cutoff:
                result.append({
                    "token": c.get("token"),
                    "email": c.get("email"),
                    "total": c.get("total_price"),
                    "currency": c.get("currency"),
                    "updated_at": updated,
                    "recovery_url": c.get("abandoned_checkout_url"),
                })
        except Exception:
            pass
    return result


async def recover_all_carts(hours: int = 24) -> dict:
    """Send Klaviyo recovery events for all open carts."""
    carts = await get_abandoned_carts(hours)
    sent = 0
    kv_key = os.getenv("KLAVIYO_API_KEY", "")
    if kv_key and carts:
        import aiohttp
        headers = {"Authorization": f"Klaviyo-API-Key {kv_key}", "revision": "2024-10-15",
                   "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as s:
            for cart in carts:
                if not cart.get("email"):
                    continue
                event = {"data": {"type": "event", "attributes": {
                    "metric": {"data": {"type": "metric", "attributes": {"name": "Abandoned Cart"}}},
                    "profile": {"data": {"type": "profile", "attributes": {"email": cart["email"]}}},
                    "properties": {"cart_total": cart.get("total"), "recovery_url": cart.get("recovery_url")},
                    "time": datetime.now(timezone.utc).isoformat(),
                }}}
                async with s.post("https://a.klaviyo.com/api/events/", json=event, headers=headers) as r:
                    if r.status in (200, 201, 202):
                        sent += 1
    return {"carts_found": len(carts), "recovery_sent": sent, "method": "klaviyo_event"}


# ── Flash Sale ────────────────────────────────────────────────────────────────

async def create_flash_sale(
    discount_pct: int = 20,
    title: str = "",
    duration_hours: int = 24,
    collection_id: str | None = None,
    min_purchase: float = 0,
    product_ids: list | None = None,
) -> dict:
    products = await _products(250)
    backup: list[dict] = []
    updated = 0
    for p in products:
        if product_ids and str(p.get("id")) not in [str(x) for x in product_ids]:
            continue
        for v in p.get("variants", []):
            orig_price = v.get("price", "0")
            try:
                new_price = round(float(orig_price) * (1 - discount_pct / 100), 2)
            except (ValueError, TypeError):
                continue
            backup.append({"variant_id": v["id"], "original_price": orig_price})
            ok = await _update_variant_price(v["id"], str(new_price))
            if ok:
                updated += 1
    DATA_DIR.mkdir(exist_ok=True)
    _FLASH_BACKUP.write_text(json.dumps({"discount_pct": discount_pct, "variants": backup,
                                         "expires_at": (datetime.now(timezone.utc) + timedelta(hours=duration_hours)).isoformat()},
                                        indent=2))
    return {
        "ok": True,
        "title": title or f"Flash Sale -{discount_pct}%",
        "discount_pct": discount_pct,
        "variants_updated": updated,
        "duration_hours": duration_hours,
        "restore_via": "POST /api/revenue/flash-sale/restore",
    }


async def restore_flash_sale() -> dict:
    if not _FLASH_BACKUP.exists():
        return {"ok": False, "error": "No flash sale backup found"}
    backup = json.loads(_FLASH_BACKUP.read_text())
    restored = 0
    for item in backup.get("variants", []):
        ok = await _update_variant_price(item["variant_id"], item["original_price"])
        if ok:
            restored += 1
    _FLASH_BACKUP.unlink(missing_ok=True)
    return {"ok": True, "variants_restored": restored}


# ── Bulk Price Update ─────────────────────────────────────────────────────────

async def bulk_price_update(
    product_ids: list | None = None,
    method: str = "percent",
    value: float = 10,
    min_price: float = 0,
    max_price: float = 99999,
) -> dict:
    products = await _products(250)
    updated = 0
    for p in products:
        if product_ids and str(p.get("id")) not in [str(x) for x in product_ids]:
            continue
        for v in p.get("variants", []):
            try:
                orig = float(v.get("price", 0))
            except (ValueError, TypeError):
                continue
            if method == "percent":
                new_p = orig * (1 + value / 100)
            elif method == "fixed":
                new_p = orig + value
            else:
                new_p = value
            new_p = max(min_price, min(max_price, round(new_p, 2)))
            ok = await _update_variant_price(v["id"], str(new_p))
            if ok:
                updated += 1
    return {"ok": True, "method": method, "value": value, "variants_updated": updated}


# ── Product Performance ───────────────────────────────────────────────────────

async def get_product_performance(days: int = 30) -> dict:
    orders = await _orders(250)
    products = await _products(250)
    product_map = {str(p["id"]): p.get("title", "?") for p in products}
    sales_count: dict[str, int] = {}
    for o in orders:
        for li in o.get("line_items", []):
            pid = str(li.get("product_id", ""))
            sales_count[pid] = sales_count.get(pid, 0) + li.get("quantity", 1)
    if not sales_count:
        return {"top_sellers": [], "slow_movers": [], "zero_sellers": [], "total_products": len(products)}
    sorted_by_sales = sorted(sales_count.items(), key=lambda x: x[1], reverse=True)
    top = [{"product_id": pid, "title": product_map.get(pid, pid), "units_sold": cnt}
           for pid, cnt in sorted_by_sales[:10]]
    slow = [{"product_id": pid, "title": product_map.get(pid, pid), "units_sold": cnt}
            for pid, cnt in sorted_by_sales[-5:] if cnt < 3]
    all_product_ids = {str(p["id"]) for p in products}
    sold_ids = set(sales_count.keys())
    zero_ids = all_product_ids - sold_ids
    zero = [{"product_id": pid, "title": product_map.get(pid, pid)} for pid in list(zero_ids)[:10]]
    return {"top_sellers": top, "slow_movers": slow, "zero_sellers": zero,
            "total_products": len(products), "period_days": days}


# ── All Products With Prices ──────────────────────────────────────────────────

async def get_all_products_with_prices() -> list[dict]:
    products = await _products(250)
    result = []
    for p in products:
        variants = p.get("variants", [])
        prices = [v.get("price") for v in variants if v.get("price")]
        result.append({
            "id": p.get("id"),
            "title": p.get("title"),
            "status": p.get("status"),
            "vendor": p.get("vendor"),
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "variants": len(variants),
        })
    return result


# ── AI Descriptions ───────────────────────────────────────────────────────────

async def generate_ai_descriptions_bulk(
    product_ids: list | None = None,
    limit: int = 5,
    language: str = "de",
) -> dict:
    products = await _products(250)
    if product_ids:
        products = [p for p in products if str(p.get("id")) in [str(x) for x in product_ids]]
    products = products[:limit]

    import aiohttp
    updated = 0
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    version = os.getenv("SHOPIFY_API_VERSION", "2024-01")
    lang_hint = "Deutsch" if language == "de" else "English"

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    perplexity_key = os.getenv("PERPLEXITY_API_KEY", "")
    if not anthropic_key and not openai_key and not perplexity_key:
        return {"ok": False, "error": "Kein AI Key verfügbar", "updated": 0}

    async def _ai_describe(title: str) -> str:
        prompt = (f"Schreibe eine kurze, SEO-optimierte Produktbeschreibung auf {lang_hint} "
                  f"für dieses Shopify-Produkt: '{title}'. Max 150 Wörter, ansprechend und kaufmotivierend.")
        try:
            from modules.ai_client import ai_complete
            return await ai_complete(prompt, max_tokens=300)
        except Exception:
            return ""

    for p in products:
        title = p.get("title", "")
        try:
            description = await _ai_describe(title)
            if description and domain and token:
                url = f"https://{domain}/admin/api/{version}/products/{p['id']}.json"
                sh_headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
                async with aiohttp.ClientSession() as s:
                    async with s.put(url, json={"product": {"id": p["id"], "body_html": description}},
                                     headers=sh_headers) as r2:
                        if r2.status in (200, 201):
                            updated += 1
        except Exception as e:
            log.warning("AI description for %s failed: %s", title, e)

    return {"ok": True, "products_updated": updated, "total_requested": len(products), "language": language}


# ── Low Inventory ─────────────────────────────────────────────────────────────

async def get_low_inventory(threshold: int = 5) -> list[dict]:
    products = await _products(250)
    low = []
    for p in products:
        for v in p.get("variants", []):
            qty = v.get("inventory_quantity")
            if qty is not None and int(qty) <= threshold:
                low.append({
                    "product_id": p.get("id"),
                    "product_title": p.get("title"),
                    "variant_id": v.get("id"),
                    "variant_title": v.get("title"),
                    "inventory_quantity": qty,
                    "price": v.get("price"),
                })
    return sorted(low, key=lambda x: x["inventory_quantity"])


# ── Auto Publish Drafts ───────────────────────────────────────────────────────

async def auto_publish_drafts() -> dict:
    products = await _products(250)
    drafts = [p for p in products if p.get("status") == "draft"]
    published = 0
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    version = os.getenv("SHOPIFY_API_VERSION", "2024-01")
    if domain and token:
        import aiohttp
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as s:
            for p in drafts:
                url = f"https://{domain}/admin/api/{version}/products/{p['id']}.json"
                async with s.put(url, json={"product": {"id": p["id"], "status": "active"}},
                                 headers=headers) as r:
                    if r.status in (200, 201):
                        published += 1
    return {"ok": True, "drafts_found": len(drafts), "published": published}


# ── Upsell Pairs ─────────────────────────────────────────────────────────────

async def get_upsell_pairs(limit: int = 10) -> list[dict]:
    """Products frequently bought together (co-occurrence in orders)."""
    orders = await _orders(250)
    co_buys: dict[str, int] = {}
    for o in orders:
        items = o.get("line_items", [])
        pids = [str(li.get("product_id")) for li in items if li.get("product_id")]
        for i, a in enumerate(pids):
            for b in pids[i + 1:]:
                key = "-".join(sorted([a, b]))
                co_buys[key] = co_buys.get(key, 0) + 1
    sorted_pairs = sorted(co_buys.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"product_pair": pair, "co_purchases": count} for pair, count in sorted_pairs]
