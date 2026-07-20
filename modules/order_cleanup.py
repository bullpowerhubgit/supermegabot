#!/usr/bin/env python3
"""
Order Cleanup — archiviert alle Test-Bestellungen (Test Käufer, €1)
Bereinigt Analytics ohne echte Orders zu berühren.
"""
from __future__ import annotations
import asyncio, logging, os, re
from typing import Dict

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

log = logging.getLogger("OrderCleanup")


def _myshopify() -> str:
    d = os.getenv("SHOPIFY_MYSHOPIFY_DOMAIN", "")
    if d:
        return d
    url = os.getenv("SHOPIFY_STORE_URL", "")
    m = re.search(r"([\w-]+\.myshopify\.com)", url)
    return m.group(1) if m else ""


DOMAIN  = _myshopify()
TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-04")


async def archive_test_orders(session: aiohttp.ClientSession) -> Dict:
    """Archiviert alle Test-Bestellungen (customer.first_name == 'Test')."""
    if not DOMAIN or not TOKEN:
        return {"error": "credentials missing"}

    base    = f"https://{DOMAIN}/admin/api/{VERSION}"
    headers = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=20)

    archived = 0
    skipped  = 0
    real     = 0
    since_id = 0

    while True:
        async with session.get(
            f"{base}/orders.json?status=any&limit=250&since_id={since_id}"
            "&fields=id,order_number,customer,total_price,closed_at",
            headers=headers, timeout=timeout,
        ) as r:
            orders = (await r.json(content_type=None)).get("orders", [])

        if not orders:
            break

        for o in orders:
            fname = (o.get("customer") or {}).get("first_name", "")
            price = float(o.get("total_price", 0) or 0)
            closed = o.get("closed_at")

            is_test = (fname == "Test" and price <= 1.0)

            if is_test and not closed:
                try:
                    async with session.post(
                        f"{base}/orders/{o['id']}/close.json",
                        headers=headers,
                        json={},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r2:
                        await r2.read()
                    archived += 1
                    await asyncio.sleep(0.25)
                except Exception as e:
                    log.debug("close order %s: %s", o["id"], e)
            elif is_test and closed:
                skipped += 1
            else:
                real += 1

        since_id = orders[-1]["id"]
        if len(orders) < 250:
            break
        await asyncio.sleep(0.5)

    return {"archived": archived, "already_closed": skipped, "real_orders": real}


async def run_order_cleanup() -> Dict:
    if not HAS_AIOHTTP:
        return {"error": "aiohttp not installed"}
    async with aiohttp.ClientSession() as session:
        result = await archive_test_orders(session)
    log.info("OrderCleanup: %s", result)
    return result


if __name__ == "__main__":
    import asyncio, logging
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(run_order_cleanup()))
