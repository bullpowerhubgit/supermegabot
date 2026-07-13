#!/usr/bin/env python3
"""Alias: Kurzform für modules.digistore — leitet weiter zu digistore24_automation."""
import logging

_log = logging.getLogger(__name__)

try:
    from modules.digistore import *  # noqa: F401, F403
    from modules.digistore import (
        get_orders,
        get_products,
        get_sales_stats,
        ping,
        is_configured,
        run_digistore_cycle,
        send_revenue_report,
        blast_best_products,
        get_recent_transactions,
        create_affiliate_links,
    )
    _log.debug("ds: digistore alias geladen")
except ImportError as _e:
    _log.warning("ds: digistore nicht verfügbar (%s)", _e)
    async def get_orders(page: int = 1, per_page: int = 50) -> list:
        return []
    async def get_products() -> list:
        return []
    async def get_sales_stats() -> dict:
        return {}
    async def ping() -> dict:
        return {"status": "nicht verfügbar"}
    def is_configured() -> bool:
        return False
    async def run_digistore_cycle() -> dict:
        return {"status": "nicht verfügbar"}
    async def send_revenue_report() -> dict:
        return {}
    async def blast_best_products(count: int = 3) -> dict:
        return {}
    async def get_recent_transactions(days: int = 7) -> list:
        return []
    def create_affiliate_links(product_ids: list) -> list:
        return []
