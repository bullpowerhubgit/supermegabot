#!/usr/bin/env python3
"""Gumroad Funnel — Upsell-Links, Download-Tracking, Checkout-Optimierung."""
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger("GumroadFunnel")

GUMROAD_BASE = "https://api.gumroad.com/v2"

# Funnel-Preispunkte (in Cent)
_ENTRY_PRICE_CENTS = 9700   # €97
_MID_PRICE_CENTS   = 19700  # €197
_HIGH_PRICE_CENTS  = 49700  # €497


def _token() -> str:
    return os.getenv("GUMROAD_ACCESS_TOKEN", "")


async def get_sales_today() -> dict:
    """Gumroad API: GET /v2/sales — heutiger Umsatz.

    Gibt {"sales": n, "revenue_eur": x} zurück.
    """
    token = _token()
    if not token:
        log.warning("GUMROAD_ACCESS_TOKEN nicht gesetzt")
        return {"sales": 0, "revenue_eur": 0.0, "error": "token_missing"}

    today = datetime.now().strftime("%Y-%m-%d")
    try:
        import aiohttp
        import json as _json
        headers = {"Authorization": f"Bearer {token}"}
        params  = {"after": today}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(f"{GUMROAD_BASE}/sales",
                             headers=headers, params=params) as r:
                body = await r.text()
                if r.status >= 400:
                    log.warning("Gumroad sales HTTP %s: %s", r.status, body[:200])
                    return {"sales": 0, "revenue_eur": 0.0, "error": f"http_{r.status}"}
                data = _json.loads(body)

        if not data.get("success"):
            return {"sales": 0, "revenue_eur": 0.0,
                    "error": data.get("message", "unknown")}

        sales_list = data.get("sales", [])
        revenue    = 0.0
        for sale in sales_list:
            try:
                price_cents = int(sale.get("price", 0) or 0)
                revenue    += price_cents / 100.0
            except (ValueError, TypeError):
                pass

        return {"sales": len(sales_list), "revenue_eur": round(revenue, 2)}
    except Exception as exc:
        log.error("Gumroad get_sales_today error: %s", exc)
        return {"sales": 0, "revenue_eur": 0.0, "error": str(exc)}


async def build_funnel_links() -> dict:
    """Erstellt Upsell-Link-Struktur nach Preisstufe.

    Returns:
        {
            "entry_url": ...,  # €97 Produkt
            "mid_url":   ...,  # €197 Produkt
            "high_url":  ...,  # €497 Produkt
        }
    """
    shop  = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
    token = _token()

    if not token:
        return {
            "entry_url":       f"{shop}/collections/digital?tier=entry",
            "mid_url":         f"{shop}/collections/digital?tier=mid",
            "high_url":        f"{shop}/collections/digital?tier=high",
            "entry_price_eur": _ENTRY_PRICE_CENTS / 100,
            "mid_price_eur":   _MID_PRICE_CENTS / 100,
            "high_price_eur":  _HIGH_PRICE_CENTS / 100,
            "mode":            "shopify_fallback",
        }

    try:
        import aiohttp
        import json as _json
        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(f"{GUMROAD_BASE}/products", headers=headers) as r:
                data = _json.loads(await r.text())

        published = [
            p for p in data.get("products", [])
            if p.get("published") and p.get("short_url")
        ]

        def _closest(target_cents: int) -> str:
            if not published:
                return ""
            best = min(published,
                       key=lambda p: abs(int(p.get("price", 0) or 0) - target_cents))
            return best.get("short_url", "")

        return {
            "entry_url": _closest(_ENTRY_PRICE_CENTS) or f"{shop}/collections/digital?tier=entry",
            "mid_url":   _closest(_MID_PRICE_CENTS)   or f"{shop}/collections/digital?tier=mid",
            "high_url":  _closest(_HIGH_PRICE_CENTS)  or f"{shop}/collections/digital?tier=high",
            "entry_price_eur": _ENTRY_PRICE_CENTS / 100,
            "mid_price_eur":   _MID_PRICE_CENTS / 100,
            "high_price_eur":  _HIGH_PRICE_CENTS / 100,
            "mode":            "gumroad_api",
            "product_count":   len(published),
        }
    except Exception as exc:
        log.error("Gumroad build_funnel_links error: %s", exc)
        return {
            "entry_url":       f"{shop}/collections/digital?tier=entry",
            "mid_url":         f"{shop}/collections/digital?tier=mid",
            "high_url":        f"{shop}/collections/digital?tier=high",
            "entry_price_eur": _ENTRY_PRICE_CENTS / 100,
            "mid_price_eur":   _MID_PRICE_CENTS / 100,
            "high_price_eur":  _HIGH_PRICE_CENTS / 100,
            "error":           str(exc),
            "mode":            "error_fallback",
        }


async def run_gumroad_report() -> dict:
    """Tages-Report: Sales + Funnel-Links."""
    sales  = await get_sales_today()
    links  = await build_funnel_links()
    report = {
        "today":     sales,
        "funnel":    links,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    log.info(
        "Gumroad Report: %s Verkäufe, %.2f EUR",
        sales.get("sales", 0),
        sales.get("revenue_eur", 0.0),
    )
    return report
