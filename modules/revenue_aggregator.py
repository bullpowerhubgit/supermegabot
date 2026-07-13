#!/usr/bin/env python3
"""Revenue Aggregator — Umsatz aus allen Plattformen zusammenführen"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

log = logging.getLogger("RevenueAggregator")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

# EUR conversion rates (approximate, updated manually or via API in production)
_RATES_TO_EUR: Dict[str, float] = {
    "EUR": 1.0,
    "USD": 0.92,
    "GBP": 1.17,
    "CHF": 1.02,
    "CAD": 0.68,
    "AUD": 0.60,
}


def _to_eur(amount: float, currency: str) -> float:
    rate = _RATES_TO_EUR.get(currency.upper(), 1.0)
    return round(amount * rate, 2)


# ---------------------------------------------------------------------------
# Per-platform revenue fetchers
# ---------------------------------------------------------------------------

async def _fetch_shopify() -> Dict:
    """Fetch today's revenue from Shopify via existing shopify_client."""
    try:
        from modules.shopify_client import get_analytics_summary  # type: ignore
        summary = await get_analytics_summary()
        revenue  = float(summary.get("revenue", 0.0))
        orders   = int(summary.get("orders_paid", 0))
        currency = summary.get("currency", "EUR")
        return {"revenue": revenue, "orders": orders, "currency": currency, "ok": True}
    except Exception as exc:
        log.warning("Shopify revenue fetch failed: %s", exc)
        return {"revenue": 0.0, "orders": 0, "currency": "EUR", "ok": False, "error": str(exc)}


async def _fetch_gumroad() -> Dict:
    """Fetch sales total from Gumroad API."""
    token = os.getenv("GUMROAD_ACCESS_TOKEN", "")
    if not token:
        return {"revenue": 0.0, "orders": 0, "currency": "USD", "ok": False,
                "error": "GUMROAD_ACCESS_TOKEN not set"}
    if not HAS_AIOHTTP:
        return {"revenue": 0.0, "orders": 0, "currency": "USD", "ok": False,
                "error": "aiohttp not installed"}
    try:
        url = "https://api.gumroad.com/v2/sales"
        params = {"access_token": token, "page": 1, "per_page": 100}
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json(content_type=None)
        if not data or not data.get("success"):
            msg = data.get("message", "Unknown error") if data else "Empty response"
            return {"revenue": 0.0, "orders": 0, "currency": "USD", "ok": False,
                    "error": msg}
        sales = data.get("sales", [])
        total   = sum(float(s.get("price", 0)) / 100 for s in sales)  # Gumroad: cents
        return {"revenue": round(total, 2), "orders": len(sales), "currency": "USD", "ok": True}
    except Exception as exc:
        log.warning("Gumroad revenue fetch failed: %s", exc)
        return {"revenue": 0.0, "orders": 0, "currency": "USD", "ok": False, "error": str(exc)}


async def _fetch_etsy() -> Dict:
    """Fetch transaction totals from Etsy."""
    try:
        from modules.ecommerce_connectors import EtsyConnector  # type: ignore
        etsy   = EtsyConnector()
        # EtsyConnector.get_listings gives products; we use get_receipts if available
        # Fallback: sum up listing prices as a proxy
        if not etsy.api_key:
            return {"revenue": 0.0, "orders": 0, "currency": "EUR", "ok": False,
                    "error": "ETSY_API_KEY not set"}
        # Try fetching receipts (paid orders)
        shop_id = etsy.shop_id
        if not shop_id:
            return {"revenue": 0.0, "orders": 0, "currency": "EUR", "ok": False,
                    "error": "ETSY_SHOP_ID not set"}
        data = await etsy._get(
            f"/application/shops/{shop_id}/receipts",
            params={"limit": 100, "was_paid": "true"},
        )
        receipts = data.get("results", [])
        total    = sum(float(r.get("grandtotal", {}).get("amount", 0)) / 100
                       for r in receipts)
        currency = (receipts[0].get("grandtotal", {}).get("currency_code", "USD")
                    if receipts else "USD")
        return {"revenue": round(total, 2), "orders": len(receipts),
                "currency": currency, "ok": True}
    except Exception as exc:
        log.warning("Etsy revenue fetch failed: %s", exc)
        return {"revenue": 0.0, "orders": 0, "currency": "USD", "ok": False, "error": str(exc)}


async def _fetch_digistore() -> Dict:
    """Fetch orders total from Digistore24 via REST API."""
    api_key = (os.getenv("DIGISTORE24_API_KEY") or os.getenv("DIGISTORE24_API_KEY_FULL") or "")
    if not api_key:
        return {"revenue": 0.0, "orders": 0, "currency": "EUR",
                "ok": False, "status": "not_configured",
                "error": "DIGISTORE24_API_KEY not set"}
    try:
        from datetime import date
        today = date.today().isoformat()
        async with aiohttp.ClientSession() as s:
            url = "https://www.digistore24.com/api/call/listTransactions/JSON/"
            async with s.get(url, headers={"X-DS24-API-KEY": api_key},
                             params={"date_from": today, "date_to": today},
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                d = await r.json(content_type=None)
        if d.get("result") != "success":
            return {"revenue": 0.0, "orders": 0, "currency": "EUR",
                    "ok": False, "error": d.get("message", "DS24 API error")[:80]}
        data = d.get("data", {})
        transactions = data.get("transactions", [])
        if isinstance(transactions, dict):
            transactions = list(transactions.values())
        total = sum(float(t.get("amount", 0)) for t in transactions)
        currency = transactions[0].get("currency", "EUR") if transactions else "EUR"
        return {"revenue": round(total, 2), "orders": len(transactions),
                "currency": currency, "ok": True}
    except Exception as exc:
        log.warning("Digistore24 revenue fetch failed: %s", exc)
        return {"revenue": 0.0, "orders": 0, "currency": "EUR", "ok": False, "error": str(exc)[:80]}


async def _fetch_paypal() -> Dict:
    """Fetch PayPal balance/status."""
    try:
        from modules.paypal_client import get_paypal_status, PAYPAL_API_USERNAME
        if not PAYPAL_API_USERNAME:
            return {"revenue": 0.0, "orders": 0, "currency": "EUR", "ok": False, "error": "PAYPAL credentials not set"}
        status = await get_paypal_status()
        return {"revenue": 0.0, "orders": 0, "currency": "EUR", "ok": status.get("connected", False),
                "email": status.get("email", ""), "env": status.get("env", "")}
    except Exception as exc:
        log.warning("PayPal fetch failed: %s", exc)
        return {"revenue": 0.0, "orders": 0, "currency": "EUR", "ok": False, "error": str(exc)}


async def _fetch_printify() -> Dict:
    """Fetch fulfilled orders total from Printify."""
    token = os.getenv("PRINTIFY_API_TOKEN", "")
    shop_id = os.getenv("PRINTIFY_SHOP_ID", "")
    if not token:
        return {"revenue": 0.0, "orders": 0, "currency": "USD", "ok": False,
                "error": "PRINTIFY_API_TOKEN not set"}
    if not HAS_AIOHTTP:
        return {"revenue": 0.0, "orders": 0, "currency": "USD", "ok": False,
                "error": "aiohttp not installed"}
    try:
        _pf_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": _pf_ua}
        timeout = aiohttp.ClientTimeout(total=20)
        if not shop_id:
            # Auto-discover first shop
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("https://api.printify.com/v1/shops.json",
                                       headers=headers) as resp:
                    shops = await resp.json(content_type=None)
            shop_id = str(shops[0]["id"]) if shops else ""
        if not shop_id:
            return {"revenue": 0.0, "orders": 0, "currency": "USD", "ok": False,
                    "error": "No Printify shop found"}

        url = f"https://api.printify.com/v1/shops/{shop_id}/orders.json"
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers,
                                   params={"limit": 100, "status": "fulfilled"}) as resp:
                data = await resp.json(content_type=None)
        orders_list = data.get("data", [])
        total = sum(
            float(o.get("total_price", 0)) / 100 for o in orders_list  # Printify: cents
        )
        return {"revenue": round(total, 2), "orders": len(orders_list),
                "currency": "USD", "ok": True}
    except Exception as exc:
        log.warning("Printify revenue fetch failed: %s", exc)
        return {"revenue": 0.0, "orders": 0, "currency": "USD", "ok": False, "error": str(exc)}


async def _fetch_stripe() -> Dict:
    """Fetch today's revenue from Stripe Charges via stripe_client."""
    try:
        from modules.stripe_client import get_revenue_stats
        stats = await get_revenue_stats()
        return {
            "revenue": stats.get("today_revenue", 0.0),
            "orders": stats.get("order_count", 0),
            "currency": stats.get("currency", "EUR"),
            "ok": "error" not in stats,
            "error": stats.get("error", ""),
        }
    except Exception as exc:
        log.warning("Stripe revenue fetch failed: %s", exc)
        return {"revenue": 0.0, "orders": 0, "currency": "EUR", "ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_platform_revenue() -> Dict:
    """
    Fetch revenue from all platforms concurrently.

    Returns:
        {
          "platforms": {
            "shopify":   {"revenue": 0.0, "orders": 0, "currency": "EUR", "ok": True},
            "gumroad":   {"revenue": 0.0, "orders": 0, "currency": "USD", "ok": False, "error": "..."},
            "etsy":      {...},
            "digistore": {...},
            "printify":  {...},
          },
          "total_eur": 0.0,
          "period": "today",
          "timestamp": "2026-05-29T...",
        }
    """
    _err = lambda e: {"revenue": 0.0, "orders": 0, "currency": "EUR", "ok": False, "error": str(e)[:80]}
    results = await asyncio.gather(
        _fetch_shopify(),
        _fetch_gumroad(),
        _fetch_etsy(),
        _fetch_digistore(),
        _fetch_printify(),
        _fetch_paypal(),
        _fetch_stripe(),
        return_exceptions=True,
    )
    platforms = {
        "shopify":   results[0] if not isinstance(results[0], Exception) else _err(results[0]),
        "gumroad":   results[1] if not isinstance(results[1], Exception) else _err(results[1]),
        "etsy":      results[2] if not isinstance(results[2], Exception) else _err(results[2]),
        "digistore": results[3] if not isinstance(results[3], Exception) else _err(results[3]),
        "printify":  results[4] if not isinstance(results[4], Exception) else _err(results[4]),
        "paypal":    results[5] if not isinstance(results[5], Exception) else _err(results[5]),
        "stripe":    results[6] if not isinstance(results[6], Exception) else _err(results[6]),
    }
    total_eur = sum(
        _to_eur(v["revenue"], v["currency"])
        for v in platforms.values()
        if v.get("ok") and v.get("revenue", 0) > 0
    )
    return {
        "platforms": platforms,
        "total_eur": round(total_eur, 2),
        "period":    "today",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


async def get_daily_report() -> str:
    """
    Build and return a Telegram-ready text report with revenue from all platforms.
    Uses the canonical format: Shopify / DS24 / Stripe / Gesamt.
    """
    report = await get_platform_revenue()
    platforms = report["platforms"]
    timestamp  = report["timestamp"][:10]  # YYYY-MM-DD

    sh  = platforms.get("shopify",   {})
    ds  = platforms.get("digistore", {})
    st  = platforms.get("stripe",    {})
    gm  = platforms.get("gumroad",   {})

    shopify_eur    = _to_eur(sh.get("revenue", 0.0), sh.get("currency", "EUR")) if sh.get("ok") else 0.0
    shopify_orders = sh.get("orders", 0)
    ds24_eur       = _to_eur(ds.get("revenue", 0.0), ds.get("currency", "EUR")) if ds.get("ok") else 0.0
    ds24_sales     = ds.get("orders", 0)
    stripe_eur     = _to_eur(st.get("revenue", 0.0), st.get("currency", "EUR")) if st.get("ok") else 0.0
    gumroad_eur    = _to_eur(gm.get("revenue", 0.0), gm.get("currency", "USD")) if gm.get("ok") else 0.0
    total_eur      = round(shopify_eur + ds24_eur + stripe_eur + gumroad_eur, 2)

    lines: List[str] = [
        f"📊 <b>Revenue Report {timestamp}</b>",
        "",
        f"🛒 <b>Shopify</b>: €{shopify_eur:.2f} ({shopify_orders} Bestellungen)",
        f"💾 <b>DS24</b>: €{ds24_eur:.2f} ({ds24_sales} Verkäufe)",
        f"💳 <b>Stripe</b>: €{stripe_eur:.2f}",
        f"📦 <b>Gesamt</b>: €{total_eur:.2f}",
        "",
        "🤖 System aktiv | BRUTUS läuft",
    ]

    # Append secondary platforms if they have revenue
    extras = []
    if gumroad_eur > 0:
        extras.append(f"💾 Gumroad: €{gumroad_eur:.2f}")
    etsy = platforms.get("etsy", {})
    if etsy.get("ok") and etsy.get("revenue", 0) > 0:
        etsy_eur = _to_eur(etsy["revenue"], etsy.get("currency", "USD"))
        extras.append(f"🎨 Etsy: €{etsy_eur:.2f}")
    if extras:
        lines.insert(-1, "")
        lines[-1:-1] = extras

    return "\n".join(lines)


async def save_daily_snapshot() -> None:
    """Append today's revenue snapshot to data/revenue_history.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    history_path = DATA_DIR / "revenue_history.json"

    # Load existing history
    history: List[Dict] = []
    if history_path.exists():
        try:
            with open(history_path, "r", encoding="utf-8") as fh:
                history = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not read revenue_history.json (%s) — starting fresh", exc)
            history = []

    snapshot = await get_platform_revenue()
    history.append(snapshot)

    try:
        with open(history_path, "w", encoding="utf-8") as fh:
            json.dump(history, fh, indent=2, ensure_ascii=False, default=str)
        log.info("Revenue snapshot saved to %s (%d entries)", history_path, len(history))
    except OSError as exc:
        log.error("Could not save revenue snapshot: %s", exc)
