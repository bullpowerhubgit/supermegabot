#!/usr/bin/env python3
"""Alias: leitet weiter zu modules.digistore24_automation."""
import logging

_log = logging.getLogger(__name__)

try:
    from modules.digistore24_automation import (
        get_orders,
        get_products,
        get_sales_stats,
        ping,
        is_configured,
        setup_ipn,
        run_with_brutus_traffic,
    )
    _log.debug("digistore: digistore24_automation geladen")
except ImportError as _e:
    _log.warning("digistore: digistore24_automation nicht verfügbar (%s)", _e)
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
    async def setup_ipn(product_id: str = "") -> dict:
        return {}
    async def run_with_brutus_traffic() -> dict:
        return {}

try:
    from modules.digistore_autonomy import (
        run_digistore_cycle,
        send_revenue_report,
        blast_best_products,
        get_recent_transactions,
        create_affiliate_links,
    )
    _log.debug("digistore: digistore_autonomy geladen")
except ImportError as _e:
    _log.warning("digistore: digistore_autonomy nicht verfügbar (%s)", _e)
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
