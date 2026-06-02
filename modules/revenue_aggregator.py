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
        if not data.get("success"):
            return {"revenue": 0.0, "orders": 0, "currency": "USD", "ok": False,
                    "error": data.get("message", "Unknown error")}
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
    """Fetch orders total from Digistore24."""
    from modules.digistore24_automation import is_configured as ds24_configured, get_orders  # type: ignore
    if not ds24_configured():
        return {"revenue": 0.0, "orders": 0, "currency": "EUR",
                "ok": False, "status": "not_configured",
                "error": "DIGISTORE24_API_KEY not set"}
    try:
        orders_list = await get_orders(page=1, per_page=100)
        total   = sum(float(o.get("amount", 0)) for o in orders_list)
        currency = (orders_list[0].get("currency", "EUR") if orders_list else "EUR")
        return {"revenue": round(total, 2), "orders": len(orders_list),
                "currency": currency, "ok": True}
    except Exception as exc:
        log.warning("Digistore24 revenue fetch failed: %s", exc)
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
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
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
    results = await asyncio.gather(
        _fetch_shopify(),
        _fetch_gumroad(),
        _fetch_etsy(),
        _fetch_digistore(),
        _fetch_printify(),
        return_exceptions=False,
    )
    platforms = {
        "shopify":   results[0],
        "gumroad":   results[1],
        "etsy":      results[2],
        "digistore": results[3],
        "printify":  results[4],
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
    """
    report = await get_platform_revenue()
    platforms = report["platforms"]
    total_eur  = report["total_eur"]
    timestamp  = report["timestamp"][:10]  # YYYY-MM-DD

    lines: List[str] = [
        f"📊 <b>Tages-Report {timestamp}</b>",
        "",
    ]

    platform_emojis = {
        "shopify":   "🛒",
        "gumroad":   "💾",
        "etsy":      "🎨",
        "digistore": "🎓",
        "printify":  "👕",
    }

    best_platform = ""
    best_revenue  = -1.0

    for name, data in platforms.items():
        emoji    = platform_emojis.get(name, "💼")
        currency = data.get("currency", "EUR")
        revenue  = data.get("revenue", 0.0)
        orders   = data.get("orders", 0)
        ok       = data.get("ok", False)

        if ok:
            eur_equiv = _to_eur(revenue, currency)
            lines.append(
                f"{emoji} <b>{name.capitalize()}</b>: "
                f"{revenue:.2f} {currency} ({orders} Bestellungen)"
            )
            if eur_equiv > best_revenue:
                best_revenue  = eur_equiv
                best_platform = name
        else:
            if data.get("status") == "not_configured":
                lines.append(f"{emoji} <b>{name.capitalize()}</b>: ⚙️ nicht konfiguriert")
            else:
                error = data.get("error", "Nicht verfügbar")
                lines.append(f"{emoji} <b>{name.capitalize()}</b>: ⚠️ {error}")

    lines += [
        "",
        f"💶 <b>Gesamt: {total_eur:.2f} EUR</b>",
    ]
    if best_platform:
        lines.append(f"🏆 Beste Plattform: <b>{best_platform.capitalize()}</b>")

    total_orders = sum(v.get("orders", 0) for v in platforms.values() if v.get("ok"))
    lines.append(f"📦 Bestellungen gesamt: {total_orders}")

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
