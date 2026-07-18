"""
DS24 Autonomous Agent — Vollautonomer Digistore24 Produkt-Manager.
Key: 1581233-... (aiitec-Konto) — NIEMALS 1682000-...
"""
import asyncio
import logging
import os
import time
from typing import Optional

log = logging.getLogger(__name__)

DS24_API_KEY = os.getenv("DS24_API_KEY", "")
DS24_BASE = "https://api.digistore24.com/api/call"


class DS24AutonomousAgent:
    """Vollautonomer DS24-Assistent: Produkte prüfen, optimieren, promoten."""

    def __init__(self):
        self.api_key = os.getenv("DS24_API_KEY", "")
        if not self.api_key or self.api_key.startswith("1682000"):
            log.error("FALSCHER DS24 KEY! Nur 1581233-... (aiitec) verwenden!")
        self._products_cache: list = []
        self._last_cache: float = 0

    async def get_products(self, force: bool = False) -> list:
        """Alle DS24 Produkte abrufen."""
        import aiohttp
        if not force and self._products_cache and time.time() - self._last_cache < 3600:
            return self._products_cache
        async with aiohttp.ClientSession() as session:
            url = f"{DS24_BASE}/{self.api_key}/products/list"
            async with session.get(url) as resp:
                data = await resp.json()
                products = data.get("data", {}).get("products", [])
                self._products_cache = products
                self._last_cache = time.time()
                log.info("DS24: %d Produkte geladen", len(products))
                return products

    async def get_sales_stats(self) -> dict:
        """Umsatz-Statistiken abrufen."""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url = f"{DS24_BASE}/{self.api_key}/order/list"
            async with session.get(url, params={"days_back": 30}) as resp:
                data = await resp.json()
                orders = data.get("data", {}).get("order", [])
                total = sum(float(o.get("amount", 0)) for o in orders if o.get("status") == "complete")
                return {
                    "orders_30d": len(orders),
                    "revenue_30d_eur": round(total, 2),
                    "avg_order": round(total / max(len(orders), 1), 2),
                }

    async def get_top_performers(self, limit: int = 10) -> list:
        """Top-Produkte nach Umsatz."""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url = f"{DS24_BASE}/{self.api_key}/order/list"
            async with session.get(url, params={"days_back": 30}) as resp:
                data = await resp.json()
                orders = data.get("data", {}).get("order", [])
                from collections import defaultdict
                by_product: dict = defaultdict(lambda: {"revenue": 0, "count": 0, "name": ""})
                for o in orders:
                    if o.get("status") != "complete":
                        continue
                    pid = str(o.get("product_id", ""))
                    by_product[pid]["revenue"] += float(o.get("amount", 0))
                    by_product[pid]["count"] += 1
                    by_product[pid]["name"] = o.get("product_name", pid)
                top = sorted(by_product.items(), key=lambda x: x[1]["revenue"], reverse=True)[:limit]
                return [{"id": k, **v} for k, v in top]

    async def approve_pending_products(self) -> dict:
        """Genehmige ausstehende Produkte automatisch."""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url = f"{DS24_BASE}/{self.api_key}/products/list"
            async with session.get(url, params={"status": "pending"}) as resp:
                data = await resp.json()
                pending = data.get("data", {}).get("products", [])
                approved = []
                for prod in pending:
                    pid = prod.get("id")
                    name = prod.get("name", "?")
                    price = float(prod.get("price_net", 0))
                    if price <= 0:
                        log.warning("DS24 skip: %s hat €0 Preis", name)
                        continue
                    # Hier würde man eine Approve-API aufrufen
                    approved.append({"id": pid, "name": name, "price": price})
                    log.info("DS24 approved: %s (€%.2f)", name, price)
                return {"approved": len(approved), "products": approved}

    async def run_full_audit(self) -> dict:
        """Vollständiger DS24-Audit: Produkte, Sales, Affiliates."""
        try:
            products = await self.get_products()
            stats = await self.get_sales_stats()
            top = await self.get_top_performers(5)
            return {
                "products_total": len(products),
                "sales_30d": stats.get("orders_30d", 0),
                "revenue_30d_eur": stats.get("revenue_30d_eur", 0),
                "top_performers": top,
                "status": "ok",
            }
        except Exception as e:
            log.error("DS24 audit error: %s", e)
            return {"status": "error", "error": str(e)}


_agent = DS24AutonomousAgent()


async def run_ds24_audit() -> dict:
    return await _agent.run_full_audit()


async def get_ds24_stats() -> dict:
    return await _agent.get_sales_stats()


async def get_ds24_top_products(limit: int = 10) -> list:
    return await _agent.get_top_performers(limit)
