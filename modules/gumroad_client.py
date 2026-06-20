#!/usr/bin/env python3
"""Gumroad integration — product listing, sales tracking, BRUTUS traffic.

Thin wrapper around ecommerce_connectors.GumroadConnector with added
brutus-blast support. Set GUMROAD_ACCESS_TOKEN in .env to enable.
Register at: https://app.gumroad.com/api
"""
import os
import logging

log = logging.getLogger("Gumroad")

GUMROAD_TOKEN = os.getenv("GUMROAD_ACCESS_TOKEN", "")


async def get_products() -> list:
    """Return all Gumroad products for the authenticated seller."""
    from modules.ecommerce_connectors import GumroadConnector
    gum = GumroadConnector()
    try:
        return await gum.get_products()
    except Exception as exc:
        log.warning("Gumroad get_products error: %s", exc)
        return []


async def get_stats() -> dict:
    """Return connection status and product count."""
    from modules.ecommerce_connectors import GumroadConnector
    gum = GumroadConnector()
    try:
        ping_result = await gum.ping()
        products = await gum.get_products() if ping_result.get("connected") else []
        return {
            "ok": ping_result.get("connected", False),
            "product_count": len(products),
            "configured": bool(GUMROAD_TOKEN),
            **{k: v for k, v in ping_result.items() if k != "connected"},
        }
    except Exception as exc:
        log.warning("Gumroad get_stats error: %s", exc)
        return {"ok": False, "configured": bool(GUMROAD_TOKEN), "error": str(exc)}


async def run_with_brutus_traffic() -> dict:
    """Get Gumroad stats then fire BRUTUS traffic swarm for digital products."""
    result: dict = {}
    try:
        result["stats"] = await get_stats()
    except Exception as exc:
        result["stats_error"] = str(exc)
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        result["brutus"] = await run_brutus_swarm(
            keywords=[
                "Gumroad Digital Products 2026",
                "Passive Income Digital Downloads",
                "KI Produkte kaufen online",
            ],
            max_keywords=3,
        )
    except Exception as exc:
        result["brutus_error"] = str(exc)
    return result
