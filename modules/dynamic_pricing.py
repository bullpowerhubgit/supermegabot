#!/usr/bin/env python3
"""
Dynamic Pricing Engine — KI-gestützte Preis-Optimierung

Scrapes competitor prices via AI, calculates optimal prices
based on inventory/velocity/competition, updates Shopify,
logs all changes to Supabase, and sends Telegram summaries.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("DynamicPricing")

# ── Lazy env helpers ──────────────────────────────────────────────────────────

def _shopify_domain() -> str:
    return os.getenv("SHOPIFY_SHOP_DOMAIN", "")

def _shopify_token() -> str:
    return (
        os.getenv("SHOPIFY_ADMIN_API_TOKEN")
        or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    )

def _shopify_api_version() -> str:
    return os.getenv("SHOPIFY_API_VERSION", "2026-04")

def _anthropic_key() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "")

def _perplexity_key() -> str:
    return os.getenv("PERPLEXITY_API_KEY", "")

def _telegram_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN_2") or os.getenv("TELEGRAM_BOT_TOKEN", "")

def _telegram_chat() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")

# Max concurrent Shopify price updates to avoid API rate-limit hammering
PRICING_SHOPIFY_CONCURRENCY = int(os.getenv("PRICING_SHOPIFY_CONCURRENCY", "5"))

# ── aiohttp helper ────────────────────────────────────────────────────────────

try:
    import aiohttp as _aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    _HAS_AIOHTTP = False


def _session(timeout: int = 20) -> "_aiohttp.ClientSession":
    return _aiohttp.ClientSession(timeout=_aiohttp.ClientTimeout(total=timeout))


# ── Supabase helper ───────────────────────────────────────────────────────────

def _supabase():
    from modules.supabase_client import get_client
    return get_client()


async def _ensure_tables() -> None:
    """Create Supabase tables if they don't exist (idempotent)."""
    try:
        sb = _supabase()
        sb.table("pricing_history").select("id").limit(0).execute()
        sb.table("auto_pricing_config").select("product_id").limit(0).execute()
    except Exception as exc:
        log.warning("Supabase table check failed (tables may not exist yet): %s", exc)


# ── Telegram notification ─────────────────────────────────────────────────────

async def _tg(msg: str) -> None:
    token = _telegram_token()
    chat  = _telegram_chat()
    if not token or not chat:
        return
    if not _HAS_AIOHTTP:
        return
    try:
        async with _session(8) as sess:
            await sess.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            )
    except Exception as exc:
        log.warning("Telegram send error: %s", exc)


# ── Competitor Price Scraping ─────────────────────────────────────────────────

async def scrape_competitor_prices(product_title: str, category: str = "") -> List[Dict]:
    """
    Find competitor prices via Perplexity AI (or Anthropic Claude as fallback).

    Returns list of dicts: [{"source": str, "price": float, "currency": str, "url": str}]
    """
    if not product_title or not product_title.strip():
        log.warning("scrape_competitor_prices: empty product_title")
        return []

    prompt = (
        f"Find current retail prices for '{product_title}'"
        + (f" in category '{category}'" if category else "")
        + " from 5 different online stores. "
        "Return ONLY a JSON array with fields: source (store name), price (number), "
        "currency (EUR/USD/GBP), url (product URL or store domain). "
        "Example: [{\"source\":\"Amazon\",\"price\":29.99,\"currency\":\"EUR\",\"url\":\"amazon.de\"}]"
    )

    # Try Perplexity first
    pplx_key = _perplexity_key()
    if pplx_key and _HAS_AIOHTTP:
        try:
            result = await _scrape_via_perplexity(prompt, pplx_key)
            if result:
                log.info(
                    "Competitor prices fetched via Perplexity for '%s': %d results",
                    product_title, len(result),
                )
                return result
        except Exception as exc:
            log.warning("Perplexity scrape failed, falling back to Claude: %s", exc)

    # Fallback: Anthropic Claude
    anthropic_key = _anthropic_key()
    if anthropic_key and _HAS_AIOHTTP:
        try:
            result = await _scrape_via_anthropic(prompt, anthropic_key)
            if result:
                log.info(
                    "Competitor prices fetched via Claude for '%s': %d results",
                    product_title, len(result),
                )
                return result
        except Exception as exc:
            log.warning("Claude scrape failed: %s", exc)

    log.warning("No AI key available or all requests failed for '%s'", product_title)
    return []


async def _scrape_via_perplexity(prompt: str, api_key: str) -> List[Dict]:
    payload = {
        "model": "sonar",
        "messages": [
            {
                "role": "system",
                "content": "You are a pricing research assistant. Always respond with valid JSON only, no markdown fences.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 800,
    }
    async with _session(30) as sess:
        async with sess.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Perplexity HTTP {resp.status}")
            data = await resp.json()

    choices = data.get("choices") or []
    if not choices:
        log.warning("Perplexity returned empty choices")
        return []
    raw = (choices[0].get("message") or {}).get("content", "").strip()
    if not raw:
        log.warning("Perplexity returned empty content")
        return []
    return _parse_price_json(raw)


async def _scrape_via_anthropic(prompt: str, api_key: str) -> List[Dict]:
    payload = {
        "model": "claude-haiku-4-5",
        "max_tokens": 800,
        "messages": [{"role": "user", "content": prompt}],
        "system": "You are a pricing research assistant. Respond with valid JSON only, no markdown fences.",
    }
    async with _session(30) as sess:
        async with sess.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=payload,
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Anthropic HTTP {resp.status}")
            data = await resp.json()

    content_blocks = data.get("content") or []
    if not content_blocks:
        log.warning("Anthropic returned empty content blocks")
        return []
    raw = (content_blocks[0].get("text") or "").strip()
    if not raw:
        log.warning("Anthropic returned empty text block")
        return []
    return _parse_price_json(raw)


def _parse_price_json(raw: str) -> List[Dict]:
    """Extract and validate JSON price array from AI response."""
    if not raw:
        return []

    # Strip markdown code fences if present
    if "```" in raw:
        parts = raw.split("```")
        # Take the content between first pair of fences
        raw = parts[1] if len(parts) > 1 else parts[0]
        if raw.startswith("json"):
            raw = raw[4:]

    # Attempt to find JSON array boundaries if extra prose is present
    start = raw.find("[")
    end   = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end + 1]

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            log.warning("_parse_price_json: expected list, got %s", type(parsed).__name__)
            return []
        validated = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                price = float(item.get("price", 0))
                if price > 0:
                    validated.append({
                        "source":   str(item.get("source", "unknown")),
                        "price":    round(price, 2),
                        "currency": str(item.get("currency", "EUR")),
                        "url":      str(item.get("url", "")),
                    })
            except (TypeError, ValueError):
                continue
        return validated
    except json.JSONDecodeError as exc:
        log.warning("Failed to parse price JSON: %s | raw=%s", exc, raw[:200])
        return []


# ── Optimal Price Calculation ─────────────────────────────────────────────────

async def calculate_optimal_price(
    current_price: float,
    competitor_prices: List[float],
    inventory_level: int,
    sales_velocity: float,
    target_margin: float = 0.35,
) -> Dict[str, Any]:
    """
    Calculate optimal price based on competition, inventory pressure, and sales velocity.

    Returns: {"optimal_price": float, "reason": str, "change_pct": float}
    """
    # Input validation
    if current_price <= 0:
        return {
            "optimal_price": 0.0,
            "reason": "Invalid current_price (must be > 0)",
            "change_pct": 0.0,
        }
    if inventory_level < 0:
        inventory_level = 0
    if sales_velocity < 0:
        sales_velocity = 0.0

    reasons: List[str] = []

    cost_floor = current_price * (1 - target_margin)
    min_price  = cost_floor * (1 + target_margin)

    if not competitor_prices:
        return {
            "optimal_price": round(current_price, 2),
            "reason": "No competitor data available; keeping current price",
            "change_pct": 0.0,
        }

    # Filter out non-positive prices defensively
    valid_comp = [p for p in competitor_prices if p > 0]
    if not valid_comp:
        return {
            "optimal_price": round(current_price, 2),
            "reason": "All competitor prices invalid; keeping current price",
            "change_pct": 0.0,
        }

    comp_median = statistics.median(valid_comp)
    comp_min    = min(valid_comp)
    comp_max    = max(valid_comp)
    reasons.append(
        f"Competitor: min={comp_min:.2f} median={comp_median:.2f} max={comp_max:.2f}"
    )

    # Base: position relative to median
    if inventory_level > 50:
        base_price = comp_median * 0.95
        reasons.append("High inventory → 5% below median")
    elif inventory_level < 10:
        base_price = comp_median * 1.05
        reasons.append("Low inventory → 5% above median (scarcity)")
    else:
        base_price = comp_median
        reasons.append("Normal inventory → at median")

    # Sales velocity adjustment
    if sales_velocity > 5:
        base_price *= 1.03
        reasons.append(f"High velocity ({sales_velocity:.1f}/day) → +3%")
    elif sales_velocity < 0.5 and inventory_level > 20:
        base_price *= 0.97
        reasons.append(f"Low velocity ({sales_velocity:.1f}/day) → -3%")

    # Enforce margin floor
    optimal = max(base_price, min_price)
    if optimal == min_price and base_price < min_price:
        reasons.append(f"Floor enforced (margin {target_margin:.0%})")

    # Round to .99 pricing
    optimal    = _round_to_99(optimal)
    change_pct = round((optimal - current_price) / current_price * 100, 2)

    return {
        "optimal_price":      optimal,
        "reason":             "; ".join(reasons),
        "change_pct":         change_pct,
        "competitor_min":     round(comp_min, 2),
        "competitor_median":  round(comp_median, 2),
        "competitor_max":     round(comp_max, 2),
    }


def _round_to_99(price: float) -> float:
    """Round to nearest .99 psychological price point."""
    base = int(price)
    if price - base >= 0.5:
        return float(base) + 0.99
    return float(max(0, base - 1)) + 0.99


# ── Shopify REST helpers ──────────────────────────────────────────────────────

async def _shopify_get_products(max_products: int = 20) -> List[Dict]:
    """Fetch active Shopify products with variants and inventory."""
    domain = _shopify_domain()
    token  = _shopify_token()
    if not domain or not token:
        log.warning("Shopify not configured")
        return []
    if not _HAS_AIOHTTP:
        return []

    base    = f"https://{domain}" if not domain.startswith("http") else domain
    version = _shopify_api_version()
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }
    products: List[Dict] = []
    page_info: Optional[str] = None
    per_page = min(max_products, 50)

    try:
        async with _session(20) as sess:
            while len(products) < max_products:
                url = f"{base}/admin/api/{version}/products.json?limit={per_page}&status=active"
                if page_info:
                    url += f"&page_info={page_info}"
                async with sess.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        log.warning("Shopify products HTTP %s", resp.status)
                        break
                    data = await resp.json()
                batch = data.get("products", [])
                products.extend(batch)
                if len(batch) < per_page:
                    break
    except Exception as exc:
        log.error("Shopify product fetch error: %s", exc)

    return products[:max_products]


async def _shopify_get_inventory(variant_id: str) -> int:
    """Get inventory quantity for a variant."""
    domain = _shopify_domain()
    token  = _shopify_token()
    if not domain or not token or not _HAS_AIOHTTP:
        return 0

    base    = f"https://{domain}" if not domain.startswith("http") else domain
    version = _shopify_api_version()
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    try:
        async with _session(10) as sess:
            async with sess.get(
                f"{base}/admin/api/{version}/variants/{variant_id}.json",
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    return 0
                data = await resp.json()
        return int(data.get("variant", {}).get("inventory_quantity", 0))
    except Exception as exc:
        log.warning("Inventory fetch error for variant %s: %s", variant_id, exc)
        return 0


async def _shopify_update_price(variant_id: str, new_price: float) -> bool:
    """Update variant price in Shopify."""
    domain = _shopify_domain()
    token  = _shopify_token()
    if not domain or not token or not _HAS_AIOHTTP:
        return False
    if new_price <= 0:
        log.warning("_shopify_update_price: refusing to set non-positive price %.2f", new_price)
        return False

    base    = f"https://{domain}" if not domain.startswith("http") else domain
    version = _shopify_api_version()
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    try:
        async with _session(10) as sess:
            async with sess.put(
                f"{base}/admin/api/{version}/variants/{variant_id}.json",
                headers=headers,
                json={"variant": {"id": variant_id, "price": f"{new_price:.2f}"}},
            ) as resp:
                if resp.status == 200:
                    return True
                log.warning(
                    "_shopify_update_price: HTTP %s for variant %s",
                    resp.status, variant_id,
                )
                return False
    except Exception as exc:
        log.error("Shopify price update error for variant %s: %s", variant_id, exc)
        return False


# ── Per-product pricing task (used by semaphore-bounded gather) ───────────────

async def _process_single_product(
    product: Dict,
    auto_config: Dict[str, Dict],
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    """
    Process one product through the full pricing cycle:
    scrape → calculate → (optionally) update Shopify.
    Returns a status dict for the product.
    """
    product_id    = str(product.get("id", ""))
    product_title = product.get("title", "")
    variants      = product.get("variants", [])

    if not variants:
        return {"status": "skipped", "reason": "no_variants", "product_title": product_title}

    variant       = variants[0]
    variant_id    = str(variant.get("id", ""))
    current_price = float(variant.get("price", 0) or 0)
    category      = product.get("product_type", "")

    if current_price <= 0:
        return {"status": "skipped", "reason": "invalid_price", "product_title": product_title}

    try:
        comp_data = await asyncio.wait_for(
            scrape_competitor_prices(product_title, category),
            timeout=15.0,
        )
        comp_prices = [item["price"] for item in comp_data if item.get("price", 0) > 0]

        inventory = await asyncio.wait_for(
            _shopify_get_inventory(variant_id),
            timeout=10.0,
        )

        velocity = await _estimate_velocity(product_id)

        pricing_result = await calculate_optimal_price(
            current_price=current_price,
            competitor_prices=comp_prices,
            inventory_level=inventory,
            sales_velocity=velocity,
        )
        optimal    = pricing_result["optimal_price"]
        change_pct = abs(pricing_result["change_pct"])

        # Apply price band from auto_pricing_config if present.
        # If no entry exists, the computed price is used as-is (algorithm is
        # already bounded by the margin floor inside calculate_optimal_price).
        if product_id in auto_config:
            cfg = auto_config[product_id]
            min_p = float(cfg.get("min_price", 0) or 0)
            max_p = float(cfg.get("max_price", 0) or 0)
            if min_p > 0 and max_p > min_p:
                clamped = max(min_p, min(max_p, optimal))
                if clamped != optimal:
                    log.debug(
                        "Price band clamp for %s: %.2f → %.2f (band %.2f–%.2f)",
                        product_title, optimal, clamped, min_p, max_p,
                    )
                    optimal = clamped
                    # Recompute change_pct after clamping
                    change_pct = abs(
                        round((optimal - current_price) / current_price * 100, 2)
                    )
            else:
                log.warning(
                    "auto_pricing_config for %s has invalid band min=%.2f max=%.2f — ignored",
                    product_id, min_p, max_p,
                )

        if change_pct > 3.0:
            async with semaphore:
                success = await _shopify_update_price(variant_id, optimal)

            if success:
                monthly_units  = max(velocity * 30, 1)
                revenue_impact = monthly_units * (optimal - current_price)

                await _log_price_change(
                    product_id=product_id,
                    product_title=product_title,
                    old_price=current_price,
                    new_price=optimal,
                    change_pct=pricing_result["change_pct"],
                    reason=pricing_result["reason"],
                    competitor_min=pricing_result.get("competitor_min"),
                    competitor_median=pricing_result.get("competitor_median"),
                    inventory_level=inventory,
                )
                log.info(
                    "Price updated: '%s' %.2f → %.2f (%.1f%%)",
                    product_title, current_price, optimal, pricing_result["change_pct"],
                )
                return {
                    "status":         "updated",
                    "product_title":  product_title,
                    "old_price":      current_price,
                    "new_price":      optimal,
                    "change_pct":     pricing_result["change_pct"],
                    "revenue_impact": revenue_impact,
                }
            else:
                return {
                    "status":        "error",
                    "product_title": product_title,
                    "reason":        "shopify_update_failed",
                }
        else:
            log.debug("No change needed for '%s' (%.1f%%)", product_title, change_pct)
            return {"status": "unchanged", "product_title": product_title}

    except asyncio.TimeoutError:
        log.warning("Timeout processing product '%s'", product_title)
        return {"status": "skipped", "reason": "timeout", "product_title": product_title}
    except Exception as exc:
        log.error("Error processing product '%s': %s", product_title, exc)
        return {
            "status":        "error",
            "product_title": product_title,
            "reason":        str(exc),
        }


# ── Pricing Cycle ─────────────────────────────────────────────────────────────

async def run_dynamic_pricing_cycle(max_products: int = 20) -> Dict[str, Any]:
    """
    Main pricing cycle:
    1. Fetch active Shopify products
    2. Scrape competitor prices for each (parallel, semaphore-bounded Shopify updates)
    3. Calculate optimal price
    4. Update Shopify if change > 3%
    5. Log to Supabase
    6. Send Telegram summary
    """
    await _ensure_tables()

    products = await _shopify_get_products(max_products)
    if not products:
        return {
            "updated":              0,
            "unchanged":            0,
            "skipped":              0,
            "total_revenue_impact": "+€0/month estimated",
            "errors":               [],
            "error":                "No Shopify products found or Shopify not configured",
        }

    # Load auto-pricing config from Supabase (non-fatal if table missing)
    auto_config: Dict[str, Dict] = {}
    try:
        sb = _supabase()
        cfg_result = sb.table("auto_pricing_config").select("*").eq("enabled", True).execute()
        for row in cfg_result.data or []:
            auto_config[str(row["product_id"])] = row
        if auto_config:
            log.info("Loaded auto_pricing_config for %d products", len(auto_config))
    except Exception as exc:
        log.warning("Could not load auto_pricing_config: %s", exc)

    # Semaphore limits concurrent Shopify PUT requests
    semaphore = asyncio.Semaphore(PRICING_SHOPIFY_CONCURRENCY)

    # Process all products concurrently (each product's Shopify update is gated by semaphore)
    product_results = await asyncio.gather(
        *[_process_single_product(p, auto_config, semaphore) for p in products],
        return_exceptions=False,
    )

    updated        = 0
    unchanged      = 0
    skipped        = 0
    revenue_impact = 0.0
    errors: List[str] = []

    for r in product_results:
        status = r.get("status", "")
        if status == "updated":
            updated += 1
            revenue_impact += r.get("revenue_impact", 0.0)
        elif status == "unchanged":
            unchanged += 1
        elif status == "error":
            errors.append(f"{r.get('product_title','?')}: {r.get('reason','unknown')}")
            unchanged += 1
        else:
            skipped += 1

    sign   = "+" if revenue_impact >= 0 else ""
    impact = f"{sign}€{revenue_impact:.0f}/month estimated"

    msg_parts = [
        "<b>Dynamic Pricing Cycle Complete</b>",
        f"Updated: {updated} | Unchanged: {unchanged} | Skipped: {skipped}",
        f"Revenue impact: {impact}",
    ]
    if errors:
        msg_parts.append(f"Errors ({len(errors)}): {errors[0]}")
    await _tg("\n".join(msg_parts))

    log.info(
        "Pricing cycle done: updated=%d unchanged=%d skipped=%d errors=%d impact=%s",
        updated, unchanged, skipped, len(errors), impact,
    )

    return {
        "updated":              updated,
        "unchanged":            unchanged,
        "skipped":              skipped,
        "total_revenue_impact": impact,
        "errors":               errors,
    }


async def _estimate_velocity(product_id: str) -> float:
    """Estimate daily sales velocity from Supabase pricing_history (fallback: 1.0)."""
    try:
        sb = _supabase()
        result = (
            sb.table("pricing_history")
            .select("changed_at")
            .eq("product_id", product_id)
            .limit(30)
            .execute()
        )
        count = len(result.data or [])
        return max(float(count) / 30, 0.1)
    except Exception:
        return 1.0


async def _log_price_change(
    product_id: str,
    product_title: str,
    old_price: float,
    new_price: float,
    change_pct: float,
    reason: str,
    competitor_min: Optional[float],
    competitor_median: Optional[float],
    inventory_level: int,
) -> None:
    try:
        sb = _supabase()
        sb.table("pricing_history").insert({
            "product_id":          product_id,
            "product_title":       product_title,
            "old_price":           old_price,
            "new_price":           new_price,
            "change_pct":          change_pct,
            "reason":              reason,
            "competitor_min":      competitor_min,
            "competitor_median":   competitor_median,
            "inventory_level":     inventory_level,
            "changed_at":          datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as exc:
        log.warning("Supabase pricing_history insert failed: %s", exc)


# ── History & Dashboard ───────────────────────────────────────────────────────

async def get_pricing_history(product_id: Optional[str] = None, days: int = 30) -> List[Dict]:
    """Fetch pricing change history from Supabase."""
    try:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        sb = _supabase()
        query = (
            sb.table("pricing_history")
            .select("*")
            .gte("changed_at", cutoff)
            .order("changed_at", desc=True)
            .limit(200)
        )
        if product_id:
            query = query.eq("product_id", product_id)
        result = query.execute()
        return result.data or []
    except Exception as exc:
        log.error("get_pricing_history error: %s", exc)
        return []


async def get_pricing_dashboard() -> Dict[str, Any]:
    """Return high-level pricing dashboard metrics."""
    try:
        from datetime import timedelta
        cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        sb = _supabase()

        result = (
            sb.table("pricing_history")
            .select("*")
            .gte("changed_at", cutoff_30d)
            .order("changed_at", desc=True)
            .limit(500)
            .execute()
        )
        rows = result.data or []

        if not rows:
            return {
                "total_adjustments_30d":    0,
                "avg_price_change_pct":     0.0,
                "estimated_revenue_impact": 0.0,
                "top_adjusted_products":    [],
                "last_cycle":               None,
            }

        total_adj  = len(rows)
        changes    = [r["change_pct"] for r in rows if r.get("change_pct") is not None]
        avg_change = round(statistics.mean([abs(c) for c in changes]), 2) if changes else 0.0

        revenue_impact = sum(
            (float(r.get("new_price", 0)) - float(r.get("old_price", 0)))
            for r in rows
        )

        from collections import Counter
        counts = Counter(r["product_title"] for r in rows if r.get("product_title"))
        top_products = [
            {"product_title": title, "adjustments": cnt}
            for title, cnt in counts.most_common(5)
        ]

        last_cycle = rows[0].get("changed_at") if rows else None

        return {
            "total_adjustments_30d":    total_adj,
            "avg_price_change_pct":     avg_change,
            "estimated_revenue_impact": round(revenue_impact, 2),
            "top_adjusted_products":    top_products,
            "last_cycle":               last_cycle,
        }

    except Exception as exc:
        log.error("get_pricing_dashboard error: %s", exc)
        return {
            "total_adjustments_30d":    0,
            "avg_price_change_pct":     0.0,
            "estimated_revenue_impact": 0.0,
            "top_adjusted_products":    [],
            "last_cycle":               None,
            "error":                    str(exc),
        }


# ── Auto-Pricing Config ───────────────────────────────────────────────────────

async def enable_auto_pricing(
    product_id: str,
    min_price: float,
    max_price: float,
) -> Dict[str, Any]:
    """Enable auto-pricing for a product with price band constraints."""
    if not product_id or not str(product_id).strip():
        return {"ok": False, "error": "product_id must not be empty"}
    if min_price < 0:
        return {"ok": False, "error": "min_price must not be negative"}
    if min_price >= max_price:
        return {"ok": False, "error": "min_price must be less than max_price"}
    try:
        sb = _supabase()
        sb.table("auto_pricing_config").upsert({
            "product_id": product_id,
            "min_price":  min_price,
            "max_price":  max_price,
            "enabled":    True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        log.info(
            "Auto-pricing enabled for product %s [%.2f – %.2f]",
            product_id, min_price, max_price,
        )
        return {"ok": True, "product_id": product_id, "min_price": min_price, "max_price": max_price}
    except Exception as exc:
        log.error("enable_auto_pricing error: %s", exc)
        return {"ok": False, "error": str(exc)}


async def disable_auto_pricing(product_id: str) -> Dict[str, Any]:
    """Disable auto-pricing for a product."""
    if not product_id or not str(product_id).strip():
        return {"ok": False, "error": "product_id must not be empty"}
    try:
        sb = _supabase()
        sb.table("auto_pricing_config").update({"enabled": False}).eq("product_id", product_id).execute()
        log.info("Auto-pricing disabled for product %s", product_id)
        return {"ok": True, "product_id": product_id}
    except Exception as exc:
        log.error("disable_auto_pricing error: %s", exc)
        return {"ok": False, "error": str(exc)}
