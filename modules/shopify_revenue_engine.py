#!/usr/bin/env python3
"""
Shopify Revenue Autopilot Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Automatisiert alles was direkt Umsatz generiert:
  • Revenue Analytics (heute/7T/30T)
  • Abandoned Cart Recovery → Klaviyo
  • Flash Sale Creator (1-Klick Rabatt)
  • Bulk Price Engine (%, Marge, fix)
  • Top/Slow Product Analyzer
  • AI SEO-Beschreibungen (Claude bulk)
  • Low Inventory Alerts
  • Auto-Publish Drafts
  • Upsell-Empfehlungen
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("RevenueEngine")

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

# ── Config helpers ─────────────────────────────────────────────────────────────

def _domain() -> str:
    d = os.getenv("SHOPIFY_SHOP_DOMAIN", "").strip().rstrip("/")
    if not d:
        # fallback: extract from SHOPIFY_STORE_URL
        url = os.getenv("SHOPIFY_STORE_URL", "").strip()
        d = url.replace("https://", "").replace("http://", "").rstrip("/")
    return d

def _token() -> str:
    return (os.getenv("SHOPIFY_ADMIN_API_TOKEN") or
            os.getenv("SHOPIFY_ACCESS_TOKEN") or
            os.getenv("SHOPIFY_AUTOMATION_TOKEN") or "").strip()

def _version() -> str:
    return os.getenv("SHOPIFY_API_VERSION", "2024-10")

def _base() -> str:
    return f"https://{_domain()}/admin/api/{_version()}"

def _headers() -> Dict[str, str]:
    return {
        "X-Shopify-Access-Token": _token(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def _session(timeout: int = 30) -> "aiohttp.ClientSession":
    return aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout),
        headers=_headers(),
    )


# ── Low-level REST helpers ─────────────────────────────────────────────────────

async def _get(path: str, params: Optional[Dict] = None) -> Dict:
    url = f"{_base()}{path}"
    async with _session() as s:
        async with s.get(url, params=params) as r:
            if r.status >= 400:
                text = await r.text()
                raise RuntimeError(f"GET {path} → {r.status}: {text[:300]}")
            return await r.json()


async def _post(path: str, body: Dict) -> Dict:
    url = f"{_base()}{path}"
    async with _session() as s:
        async with s.post(url, json=body) as r:
            if r.status >= 400:
                text = await r.text()
                raise RuntimeError(f"POST {path} → {r.status}: {text[:300]}")
            return await r.json()


async def _put(path: str, body: Dict) -> Dict:
    url = f"{_base()}{path}"
    async with _session() as s:
        async with s.put(url, json=body) as r:
            if r.status >= 400:
                text = await r.text()
                raise RuntimeError(f"PUT {path} → {r.status}: {text[:300]}")
            return await r.json()


async def _delete(path: str) -> bool:
    url = f"{_base()}{path}"
    async with _session() as s:
        async with s.delete(url) as r:
            return r.status < 400


# ── 1. Revenue Analytics ───────────────────────────────────────────────────────

async def get_revenue_summary() -> Dict[str, Any]:
    """Echtzeit-Umsatz: heute, gestern, 7 Tage, 30 Tage, offene Bestellungen."""
    now = datetime.now(timezone.utc)

    async def _fetch_orders(since: datetime, status: str = "any") -> List[Dict]:
        params = {
            "status": status,
            "created_at_min": since.isoformat(),
            "limit": 250,
            "fields": "id,total_price,financial_status,fulfillment_status,created_at,line_items",
        }
        data = await _get("/orders.json", params)
        return data.get("orders", [])

    periods = {
        "today":   now - timedelta(hours=now.hour, minutes=now.minute),
        "yesterday": now - timedelta(days=1),
        "7d":      now - timedelta(days=7),
        "30d":     now - timedelta(days=30),
    }

    tasks = {k: _fetch_orders(v) for k, v in periods.items()}
    results = {}
    for k, coro in tasks.items():
        try:
            results[k] = await coro
        except Exception as e:
            results[k] = []
            log.warning("Revenue fetch %s failed: %s", k, e)

    def _summarize(orders: List[Dict]) -> Dict:
        paid = [o for o in orders if o.get("financial_status") in ("paid", "partially_paid")]
        revenue = sum(float(o.get("total_price", 0)) for o in paid)
        return {
            "revenue": round(revenue, 2),
            "orders": len(paid),
            "aov": round(revenue / len(paid), 2) if paid else 0,
        }

    # Pending / unfulfilled orders
    try:
        pending_data = await _fetch_orders(now - timedelta(days=90), status="open")
        unfulfilled = [o for o in pending_data if o.get("fulfillment_status") != "fulfilled"]
    except Exception:
        unfulfilled = []

    return {
        "today":     _summarize(results["today"]),
        "yesterday": _summarize(results["yesterday"]),
        "7d":        _summarize(results["7d"]),
        "30d":       _summarize(results["30d"]),
        "pending_orders": len(unfulfilled),
        "pending_revenue": round(sum(float(o.get("total_price", 0)) for o in unfulfilled), 2),
        "timestamp": now.isoformat(),
    }


# ── 2. Abandoned Cart Recovery ─────────────────────────────────────────────────

async def get_abandoned_carts(hours: int = 24) -> List[Dict]:
    """Alle Checkouts die nicht abgeschlossen wurden (letzte N Stunden)."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        data = await _get("/checkouts.json", {"created_at_min": since, "limit": 250})
        checkouts = data.get("checkouts", [])
        result = []
        for c in checkouts:
            email = c.get("email", "")
            total = c.get("total_price", "0")
            items = c.get("line_items", [])
            result.append({
                "id": c.get("id"),
                "token": c.get("token"),
                "email": email,
                "total": float(total),
                "items": len(items),
                "product_titles": [i.get("title", "") for i in items[:3]],
                "created_at": c.get("created_at"),
                "abandoned_checkout_url": c.get("abandoned_checkout_url", ""),
            })
        return sorted(result, key=lambda x: x["total"], reverse=True)
    except Exception as e:
        log.error("Abandoned carts error: %s", e)
        return []


async def trigger_cart_recovery_email(checkout_token: str) -> Dict:
    """Shopify sendet Recovery-Email an Checkout-Inhaber."""
    try:
        data = await _post(
            f"/checkouts/{checkout_token}/send_invoice.json",
            {"checkout": {"custom_message": "Du hast etwas vergessen! 🛒 Jetzt bestellen und 10% sparen."}}
        )
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def recover_all_carts(hours: int = 24) -> Dict:
    """Alle offenen Carts automatisch per E-Mail ansprechen."""
    carts = await get_abandoned_carts(hours)
    carts_with_email = [c for c in carts if c.get("email")]
    results = []
    for cart in carts_with_email[:50]:  # max 50 auf einmal
        r = await trigger_cart_recovery_email(cart["token"])
        r["email"] = cart["email"]
        r["total"] = cart["total"]
        results.append(r)
        await asyncio.sleep(0.3)  # rate limit

    ok = sum(1 for r in results if r.get("ok"))
    return {
        "total_abandoned": len(carts),
        "with_email": len(carts_with_email),
        "emails_sent": ok,
        "failed": len(results) - ok,
        "potential_revenue": round(sum(c["total"] for c in carts_with_email[:50]), 2),
        "results": results,
    }


# ── 3. Flash Sale Creator ──────────────────────────────────────────────────────

async def create_flash_sale(
    discount_pct: int = 20,
    title: str = "",
    duration_hours: int = 24,
    collection_id: Optional[str] = None,
    min_purchase: float = 0,
) -> Dict:
    """Erstellt einen Discount-Code für eine zeitbegrenzte Flash-Sale-Aktion."""
    if not title:
        title = f"FLASH{discount_pct}"

    starts_at = datetime.now(timezone.utc).isoformat()
    ends_at = (datetime.now(timezone.utc) + timedelta(hours=duration_hours)).isoformat()

    body: Dict[str, Any] = {
        "price_rule": {
            "title": title,
            "target_type": "line_item",
            "target_selection": "all" if not collection_id else "entitled",
            "allocation_method": "across",
            "value_type": "percentage",
            "value": f"-{discount_pct}.0",
            "customer_selection": "all",
            "starts_at": starts_at,
            "ends_at": ends_at,
            "usage_limit": None,
        }
    }

    if min_purchase > 0:
        body["price_rule"]["prerequisite_subtotal_range"] = {"greater_than_or_equal_to": str(min_purchase)}

    if collection_id:
        body["price_rule"]["entitled_collection_ids"] = [int(collection_id)]

    try:
        rule_data = await _post("/price_rules.json", body)
        rule_id = rule_data["price_rule"]["id"]

        code_data = await _post(
            f"/price_rules/{rule_id}/discount_codes.json",
            {"discount_code": {"code": title}}
        )
        return {
            "ok": True,
            "code": code_data["discount_code"]["code"],
            "discount_pct": discount_pct,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "price_rule_id": rule_id,
            "discount_code_id": code_data["discount_code"]["id"],
            "share_message": f"🔥 FLASH SALE! {discount_pct}% Rabatt mit Code: {title} — nur {duration_hours}h!"
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── 4. Bulk Price Engine ───────────────────────────────────────────────────────

async def get_all_products_with_prices() -> List[Dict]:
    """Alle Produkte mit Preisen und Varianten laden."""
    products = []
    page_info = None
    while True:
        params: Dict[str, Any] = {
            "limit": 250,
            "fields": "id,title,status,variants,vendor,product_type",
        }
        if page_info:
            params["page_info"] = page_info

        data = await _get("/products.json", params)
        batch = data.get("products", [])
        products.extend(batch)

        link = data.get("link", "")
        if 'rel="next"' not in link:
            break
        # Extract page_info from Link header (simplified)
        import re
        m = re.search(r'page_info=([^&>]+).*?rel="next"', link)
        if not m:
            break
        page_info = m.group(1)

    result = []
    for p in products:
        variants = p.get("variants", [])
        prices = [float(v.get("price", 0)) for v in variants if v.get("price")]
        result.append({
            "id": p["id"],
            "title": p["title"],
            "status": p.get("status", "active"),
            "vendor": p.get("vendor", ""),
            "product_type": p.get("product_type", ""),
            "min_price": min(prices) if prices else 0,
            "max_price": max(prices) if prices else 0,
            "variant_count": len(variants),
            "variants": [{"id": v["id"], "price": v.get("price", "0"), "sku": v.get("sku", "")} for v in variants],
        })
    return result


async def bulk_price_update(
    product_ids: Optional[List[int]] = None,
    method: str = "percent",  # "percent" | "fixed_add" | "fixed_set" | "margin"
    value: float = 10.0,      # % increase, fixed add, absolute price, or margin %
    min_price: float = 0,
    max_price: float = 99999,
) -> Dict:
    """
    Preise für mehrere Produkte auf einmal anpassen.
    method=percent: +10% auf alle Preise
    method=fixed_add: +5€ auf alle Preise
    method=fixed_set: Alle Preise auf exakt value setzen
    method=margin: Preis so setzen dass Marge = value% (braucht Einkaufspreis)
    """
    products = await get_all_products_with_prices()
    if product_ids:
        products = [p for p in products if p["id"] in product_ids]

    updated = 0
    errors = 0
    changes = []

    for product in products:
        for variant in product["variants"]:
            old_price = float(variant["price"])
            if old_price < min_price or old_price > max_price:
                continue

            if method == "percent":
                new_price = old_price * (1 + value / 100)
            elif method == "fixed_add":
                new_price = old_price + value
            elif method == "fixed_set":
                new_price = value
            else:
                continue

            new_price = max(0.01, round(new_price, 2))

            if abs(new_price - old_price) < 0.01:
                continue

            try:
                await _put(
                    f"/variants/{variant['id']}.json",
                    {"variant": {"id": variant["id"], "price": str(new_price)}}
                )
                changes.append({
                    "product": product["title"],
                    "old": old_price,
                    "new": new_price,
                    "diff": round(new_price - old_price, 2),
                })
                updated += 1
                await asyncio.sleep(0.1)
            except Exception as e:
                log.error("Price update failed for variant %s: %s", variant["id"], e)
                errors += 1

    return {
        "ok": True,
        "updated_variants": updated,
        "errors": errors,
        "products_processed": len(products),
        "method": method,
        "value": value,
        "changes": changes[:20],  # first 20 for display
    }


# ── 5. Product Performance Analyzer ───────────────────────────────────────────

async def get_product_performance(days: int = 30) -> Dict:
    """Analysiert welche Produkte sich gut verkaufen und welche nicht."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    try:
        orders_data = await _get("/orders.json", {
            "status": "any",
            "financial_status": "paid",
            "created_at_min": since,
            "limit": 250,
            "fields": "id,line_items,total_price,created_at",
        })
        orders = orders_data.get("orders", [])
    except Exception as e:
        return {"error": str(e)}

    product_stats: Dict[str, Dict] = {}

    for order in orders:
        for item in order.get("line_items", []):
            pid = str(item.get("product_id", "unknown"))
            title = item.get("title", "Unbekannt")
            qty = int(item.get("quantity", 1))
            revenue = float(item.get("price", 0)) * qty

            if pid not in product_stats:
                product_stats[pid] = {
                    "product_id": pid,
                    "title": title,
                    "units_sold": 0,
                    "revenue": 0.0,
                    "orders": 0,
                }
            product_stats[pid]["units_sold"] += qty
            product_stats[pid]["revenue"] += revenue
            product_stats[pid]["orders"] += 1

    sorted_products = sorted(product_stats.values(), key=lambda x: x["revenue"], reverse=True)

    # Products with zero sales
    all_products = await get_all_products_with_prices()
    sold_ids = set(product_stats.keys())
    zero_sellers = [
        p for p in all_products
        if str(p["id"]) not in sold_ids and p["status"] == "active"
    ]

    return {
        "period_days": days,
        "total_orders": len(orders),
        "total_revenue": round(sum(p["revenue"] for p in product_stats.values()), 2),
        "top_sellers": [
            {**p, "revenue": round(p["revenue"], 2)}
            for p in sorted_products[:10]
        ],
        "slow_sellers": [
            {**p, "revenue": round(p["revenue"], 2)}
            for p in sorted_products[-5:] if p["revenue"] > 0
        ],
        "zero_sellers": [
            {"id": p["id"], "title": p["title"], "price": p["min_price"]}
            for p in zero_sellers[:20]
        ],
        "zero_seller_count": len(zero_sellers),
    }


# ── 6. AI SEO Beschreibungen (Claude bulk) ─────────────────────────────────────

async def generate_ai_descriptions_bulk(
    product_ids: Optional[List[int]] = None,
    limit: int = 10,
    language: str = "de",
) -> Dict:
    """Generiert SEO-optimierte Produktbeschreibungen mit Claude für mehrere Produkte."""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        return {"error": "ANTHROPIC_API_KEY nicht gesetzt"}

    products = await get_all_products_with_prices()
    if product_ids:
        products = [p for p in products if p["id"] in product_ids]
    products = products[:limit]

    results = []

    async def _claude_describe(product: Dict) -> Dict:
        lang_instruction = "auf Deutsch" if language == "de" else "in English"
        prompt = (
            f"Schreibe eine SEO-optimierte Produktbeschreibung {lang_instruction} für:\n"
            f"Produkt: {product['title']}\n"
            f"Kategorie: {product.get('product_type', 'unbekannt')}\n"
            f"Marke: {product.get('vendor', 'unbekannt')}\n"
            f"Preis: ab {product['min_price']}€\n\n"
            "Die Beschreibung soll:\n"
            "• 150-200 Wörter sein\n"
            "• 3-5 relevante Keywords enthalten\n"
            "• Vorteile und Nutzen betonen\n"
            "• Mit einem Call-to-Action enden\n"
            "• Als einfaches HTML (p, ul, li Tags) formatiert sein\n\n"
            "Antworte NUR mit dem HTML-Text, keine Erklärungen."
        )

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": anthropic_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}],
        }

        try:
            async with _session(60) as s:
                async with s.post(url, json=body, headers=headers) as r:
                    if r.status != 200:
                        return {"product_id": product["id"], "ok": False, "error": await r.text()}
                    data = await r.json()
                    description = data["content"][0]["text"].strip()

            # Apply to Shopify product
            await _put(
                f"/products/{product['id']}.json",
                {"product": {"id": product["id"], "body_html": description}}
            )
            return {
                "product_id": product["id"],
                "title": product["title"],
                "ok": True,
                "description_preview": description[:100] + "...",
            }
        except Exception as e:
            return {"product_id": product["id"], "ok": False, "error": str(e)}

    tasks = [_claude_describe(p) for p in products]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    ok = sum(1 for r in results if isinstance(r, dict) and r.get("ok"))
    return {
        "processed": len(results),
        "updated": ok,
        "failed": len(results) - ok,
        "results": list(results),
    }


# ── 7. Low Inventory Alerts ────────────────────────────────────────────────────

async def get_low_inventory(threshold: int = 5) -> List[Dict]:
    """Produkte mit geringem Lagerbestand."""
    try:
        data = await _get("/variants.json", {
            "limit": 250,
            "fields": "id,title,product_id,inventory_quantity,sku,price",
        })
        variants = data.get("variants", [])
        low = [
            {
                "variant_id": v["id"],
                "product_id": v["product_id"],
                "sku": v.get("sku", ""),
                "title": v.get("title", ""),
                "inventory": v.get("inventory_quantity", 0),
                "price": float(v.get("price", 0)),
            }
            for v in variants
            if isinstance(v.get("inventory_quantity"), int) and v["inventory_quantity"] <= threshold
        ]
        return sorted(low, key=lambda x: x["inventory"])
    except Exception as e:
        log.error("Low inventory check failed: %s", e)
        return []


# ── 8. Auto-Publish Drafts ─────────────────────────────────────────────────────

async def auto_publish_drafts() -> Dict:
    """Alle Draft-Produkte auf 'active' setzen und veröffentlichen."""
    try:
        data = await _get("/products.json", {"status": "draft", "limit": 250, "fields": "id,title"})
        drafts = data.get("products", [])
    except Exception as e:
        return {"error": str(e)}

    published = []
    errors = []

    for product in drafts:
        try:
            await _put(
                f"/products/{product['id']}.json",
                {"product": {"id": product["id"], "status": "active", "published": True}}
            )
            published.append({"id": product["id"], "title": product["title"]})
            await asyncio.sleep(0.15)
        except Exception as e:
            errors.append({"id": product["id"], "title": product["title"], "error": str(e)})

    return {
        "ok": True,
        "total_drafts": len(drafts),
        "published": len(published),
        "errors": len(errors),
        "published_products": published,
        "error_details": errors,
    }


# ── 9. Smart Upsell Recommendations ───────────────────────────────────────────

async def get_upsell_pairs(limit: int = 10) -> List[Dict]:
    """Analysiert Bestellungen und findet häufig zusammen gekaufte Produkte."""
    since = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    try:
        data = await _get("/orders.json", {
            "status": "any",
            "financial_status": "paid",
            "created_at_min": since,
            "limit": 250,
            "fields": "id,line_items",
        })
        orders = data.get("orders", [])
    except Exception:
        return []

    from collections import defaultdict, Counter
    pair_counts: Counter = Counter()
    product_names: Dict[str, str] = {}

    for order in orders:
        items = order.get("line_items", [])
        for item in items:
            pid = str(item.get("product_id", ""))
            product_names[pid] = item.get("title", "Unbekannt")

        ids = [str(i.get("product_id", "")) for i in items if i.get("product_id")]
        ids = list(set(ids))
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pair = tuple(sorted([ids[i], ids[j]]))
                pair_counts[pair] += 1

    results = []
    for (a, b), count in pair_counts.most_common(limit):
        if count >= 2:
            results.append({
                "product_a": product_names.get(a, a),
                "product_b": product_names.get(b, b),
                "bought_together": count,
                "recommendation": f"Kunden die '{product_names.get(a, a)}' kaufen, kaufen oft auch '{product_names.get(b, b)}'",
            })
    return results


# ── 10. Complete Dashboard Data (single call) ─────────────────────────────────

async def get_full_dashboard() -> Dict:
    """Alle Dashboard-Daten in einem einzigen Aufruf (parallel)."""
    revenue_task   = asyncio.create_task(get_revenue_summary())
    carts_task     = asyncio.create_task(get_abandoned_carts(24))
    inventory_task = asyncio.create_task(get_low_inventory(5))

    revenue, carts, inventory = await asyncio.gather(
        revenue_task, carts_task, inventory_task,
        return_exceptions=True
    )

    return {
        "revenue": revenue if not isinstance(revenue, Exception) else {"error": str(revenue)},
        "abandoned_carts": carts if not isinstance(carts, Exception) else [],
        "abandoned_cart_count": len(carts) if isinstance(carts, list) else 0,
        "low_inventory": inventory if not isinstance(inventory, Exception) else [],
        "low_inventory_count": len(inventory) if isinstance(inventory, list) else 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
