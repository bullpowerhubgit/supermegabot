"""Shopify Price Optimizer — analysiert und optimiert Produktpreise."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("ShopifyPriceOptimizer")

# ── Config ────────────────────────────────────────────────────────────────────

SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOKEN  = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")


def _credentials_ok() -> bool:
    return bool(SHOP_DOMAIN and SHOP_TOKEN)


# ── GraphQL helper ────────────────────────────────────────────────────────────

async def _graphql(query: str, variables: dict | None = None) -> dict:
    """Ruft Shopify GraphQL via zentralen shopify_client auf."""
    try:
        from modules.shopify_client import graphql as _gql
        return await _gql(query, variables)
    except Exception as e:
        log.warning("shopify_client.graphql Fehler: %s", e)
        return {"errors": str(e)}


# ── 1. get_price_distribution ─────────────────────────────────────────────────

async def get_price_distribution() -> dict:
    """
    Holt alle aktiven Produktpreise via GraphQL-Paginierung.
    Gibt {"min": x, "max": y, "avg": z, "under_10": n, "over_500": n,
          "total": n, "buckets": {...}} zurück.
    """
    if not _credentials_ok():
        return {"ok": False, "error": "Shopify-Zugangsdaten fehlen"}

    query = """
    query GetPrices($first: Int!, $after: String) {
        products(first: $first, after: $after, query: "status:active") {
            pageInfo { hasNextPage endCursor }
            edges {
                node {
                    id
                    priceRangeV2 {
                        minVariantPrice { amount currencyCode }
                        maxVariantPrice { amount currencyCode }
                    }
                }
            }
        }
    }
    """

    prices: list[float] = []
    cursor: str | None = None
    page = 0

    while page < 50:  # Sicherheits-Limit (50 × 250 = 12.500 Produkte)
        page += 1
        variables: dict[str, Any] = {"first": 250}
        if cursor:
            variables["after"] = cursor

        r = await _graphql(query, variables)
        products_data = r.get("data", {}).get("products", {})
        edges = products_data.get("edges", [])

        for edge in edges:
            node = edge.get("node", {})
            price_range = node.get("priceRangeV2", {})
            min_price = price_range.get("minVariantPrice", {}).get("amount")
            if min_price is not None:
                try:
                    prices.append(float(min_price))
                except (ValueError, TypeError):
                    pass

        page_info = products_data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    if not prices:
        return {
            "ok": True,
            "total": 0,
            "min": 0, "max": 0, "avg": 0,
            "under_10": 0, "over_500": 0,
            "buckets": {},
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    prices.sort()
    total = len(prices)
    price_sum = sum(prices)

    # Buckets
    under_10  = sum(1 for p in prices if p < 10)
    ten_to_20 = sum(1 for p in prices if 10 <= p < 20)
    twenty_50 = sum(1 for p in prices if 20 <= p < 50)
    fifty_100 = sum(1 for p in prices if 50 <= p < 100)
    hun_500   = sum(1 for p in prices if 100 <= p < 500)
    over_500  = sum(1 for p in prices if p >= 500)

    return {
        "ok": True,
        "total": total,
        "min": round(prices[0], 2),
        "max": round(prices[-1], 2),
        "avg": round(price_sum / total, 2),
        "median": round(prices[total // 2], 2),
        "under_10": under_10,
        "over_500": over_500,
        "buckets": {
            "0-9.99":     under_10,
            "10-19.99":   ten_to_20,
            "20-49.99":   twenty_50,
            "50-99.99":   fifty_100,
            "100-499.99": hun_500,
            "500+":       over_500,
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ── 2. find_underpriced ───────────────────────────────────────────────────────

async def find_underpriced(min_margin_eur: float = 5.0) -> list:
    """
    Gibt Produkte unter €10 zurück — wahrscheinlich keine Marge.
    Threshold = min_margin_eur (default €5 → unter €10 ist riskant bei üblichen EK ~€3-8).
    """
    if not _credentials_ok():
        log.warning("find_underpriced: Shopify-Zugangsdaten fehlen")
        return []

    threshold = min_margin_eur * 2  # einfache Faustregel: VK < 2× min_margin → unterpreisig
    if threshold < 10:
        threshold = 10.0  # Mindest-Threshold €10

    query = """
    query FindUnderpriced($first: Int!, $after: String) {
        products(first: $first, after: $after, query: "status:active") {
            pageInfo { hasNextPage endCursor }
            edges {
                node {
                    id title vendor productType
                    priceRangeV2 {
                        minVariantPrice { amount currencyCode }
                    }
                    variants(first: 1) {
                        edges { node { id price compareAtPrice } }
                    }
                }
            }
        }
    }
    """

    underpriced: list[dict] = []
    cursor: str | None = None
    page = 0

    while page < 50:
        page += 1
        variables: dict[str, Any] = {"first": 250}
        if cursor:
            variables["after"] = cursor

        r = await _graphql(query, variables)
        products_data = r.get("data", {}).get("products", {})
        edges = products_data.get("edges", [])

        for edge in edges:
            node = edge.get("node", {})
            price_range = node.get("priceRangeV2", {})
            min_price_str = price_range.get("minVariantPrice", {}).get("amount")
            try:
                price = float(min_price_str) if min_price_str else 0.0
            except (ValueError, TypeError):
                continue

            if price < threshold:
                variant_edges = node.get("variants", {}).get("edges", [])
                variant = variant_edges[0]["node"] if variant_edges else {}
                underpriced.append({
                    "id":           node.get("id"),
                    "title":        node.get("title"),
                    "vendor":       node.get("vendor"),
                    "product_type": node.get("productType"),
                    "price":        price,
                    "variant_id":   variant.get("id"),
                    "compare_at_price": variant.get("compareAtPrice"),
                })

        page_info = products_data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    log.info("find_underpriced: %d Produkte unter €%.2f gefunden", len(underpriced), threshold)
    return underpriced


# ── 3. suggest_prices ────────────────────────────────────────────────────────

def _round_to_99(price: float) -> float:
    """Rundet auf psychologische .99-Preise."""
    if price < 10:
        return 12.99
    if price < 20:
        return 24.99
    if price < 50:
        # Nächste volle 5 → .99
        import math
        next_5 = math.ceil(price / 5) * 5
        return float(next_5) - 0.01
    if price < 100:
        import math
        next_10 = math.ceil(price / 10) * 10
        return float(next_10) - 0.01
    # > €100 → nächste 25er Marke
    import math
    next_25 = math.ceil(price / 25) * 25
    return float(next_25) - 0.01


async def suggest_prices(products: list) -> list:
    """
    Für jede Produkt-Liste: wenn Preis < €10 → schlage €12.99 vor,
    wenn < €20 → €24.99, wenn < €50 → runde auf x.99.
    Gibt Liste mit {id, title, current_price, suggested_price, change_eur} zurück.
    KEINE automatischen Änderungen — nur Vorschläge!
    """
    suggestions: list[dict] = []

    for product in products:
        current = float(product.get("price", 0) or 0)
        if current <= 0:
            continue

        suggested = _round_to_99(current)
        change = round(suggested - current, 2)

        if change <= 0:
            continue  # kein Aufschlag nötig

        suggestions.append({
            "id":              product.get("id"),
            "title":           product.get("title"),
            "vendor":          product.get("vendor"),
            "current_price":   current,
            "suggested_price": suggested,
            "change_eur":      change,
            "change_pct":      round(change / current * 100, 1) if current else 0,
        })

    # Sortieren nach größtem absoluten Aufschlag zuerst
    suggestions.sort(key=lambda x: x["change_eur"], reverse=True)
    log.info("suggest_prices: %d Preisvorschläge", len(suggestions))
    return suggestions


# ── 4. run_price_check ────────────────────────────────────────────────────────

async def run_price_check() -> dict:
    """
    Haupt-Report: Distribution + Underpriced + Empfehlungen.
    KEINE automatischen Änderungen — nur Analyse!
    """
    if not _credentials_ok():
        return {"ok": False, "error": "Shopify-Zugangsdaten fehlen"}

    log.info("PriceCheck: starte Preisanalyse ...")

    # 1. Distribution
    distribution = await get_price_distribution()

    # 2. Unterpreisige Produkte
    underpriced = await find_underpriced(min_margin_eur=5.0)

    # 3. Preisvorschläge
    suggestions = await suggest_prices(underpriced)

    # 4. Zusammenfassung
    total = distribution.get("total", 0)
    under10 = distribution.get("under_10", 0)
    over500 = distribution.get("over_500", 0)

    summary_lines = [
        f"Preisanalyse abgeschlossen: {total} aktive Produkte",
        f"Durchschnittspreis: €{distribution.get('avg', 0)}",
        f"Preisrange: €{distribution.get('min', 0)} – €{distribution.get('max', 0)}",
        f"Unter €10: {under10} Produkte ({round(under10/total*100,1) if total else 0}%)",
        f"Über €500: {over500} Produkte",
        f"Preisvorschläge: {len(suggestions)} Produkte könnten optimiert werden",
    ]
    summary = "\n".join(summary_lines)

    log.info("PriceCheck fertig: %s Vorschläge", len(suggestions))

    return {
        "ok":           True,
        "summary":      summary,
        "distribution": distribution,
        "underpriced_count": len(underpriced),
        "suggestions_count": len(suggestions),
        "top_suggestions":   suggestions[:20],  # Top 20 im Report
        "all_underpriced":   underpriced,
        "checked_at":        datetime.now(timezone.utc).isoformat(),
        "note":              "KEINE Preise wurden geaendert — nur Analyse. Preisaenderungen erfordern explizite Freigabe.",
    }
