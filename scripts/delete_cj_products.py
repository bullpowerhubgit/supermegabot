"""
Permanently DELETE all remaining active CJ Dropshipping products.
Run after archive_cj_products.py completes to catch errors and stragglers.
"""
import asyncio
import logging
import os
import sys

import aiohttp
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

SHOP = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
API_VER = os.getenv("SHOPIFY_API_VERSION", "2024-04")
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}
TIMEOUT = aiohttp.ClientTimeout(total=60, connect=15)


async def fetch_remaining_cj_ids(session: aiohttp.ClientSession) -> list[str]:
    """Find all still-active CJ Dropshipping products (archival failures + stragglers)."""
    base = f"https://{SHOP}/admin/api/{API_VER}/products.json"
    ids: list[str] = []
    page_info: str | None = None
    page = 0

    while True:
        page += 1
        if page_info:
            params = {"limit": 250, "page_info": page_info}
        else:
            params = {
                "limit": 250,
                "status": "active",
                "vendor": "CJ Dropshipping",
                "fields": "id,title,vendor,status",
            }

        async with session.get(base, headers=HEADERS, params=params, timeout=TIMEOUT) as resp:
            if resp.status == 429:
                await asyncio.sleep(float(resp.headers.get("Retry-After", "2")))
                continue
            if resp.status != 200:
                log.error("Shopify error %s", resp.status)
                break
            data = await resp.json()
            products = data.get("products", [])
            if not products:
                break
            batch = [str(p["id"]) for p in products]
            ids.extend(batch)
            log.info("Scan page %d: %d active CJ products found (total %d)", page, len(batch), len(ids))
            import re
            link = resp.headers.get("Link", "")
            page_info = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    m = re.search(r"page_info=([^&>]+)", part)
                    if m:
                        page_info = m.group(1)
            if not page_info:
                break

    return ids


async def delete_products(session: aiohttp.ClientSession, ids: list[str]) -> tuple[int, int]:
    ok = err = 0
    for i, pid in enumerate(ids, 1):
        url = f"https://{SHOP}/admin/api/{API_VER}/products/{pid}.json"
        try:
            async with session.delete(url, headers=HEADERS, timeout=TIMEOUT) as resp:
                if resp.status == 429:
                    await asyncio.sleep(float(resp.headers.get("Retry-After", "2")))
                    async with session.delete(url, headers=HEADERS, timeout=TIMEOUT) as r2:
                        if r2.status == 200:
                            ok += 1
                        else:
                            err += 1
                elif resp.status == 200:
                    ok += 1
                    if i % 25 == 0:
                        log.info("Deleted %d/%d (%.0f%%)", i, len(ids), i / len(ids) * 100)
                else:
                    log.warning("Delete failed %s: HTTP %s", pid, resp.status)
                    err += 1
        except aiohttp.ClientError as e:
            log.error("Error deleting %s: %s", pid, e)
            err += 1
        await asyncio.sleep(0.12)
    return ok, err


async def main() -> None:
    if not SHOP or not TOKEN:
        log.error("Missing SHOPIFY credentials")
        sys.exit(1)

    log.info("=== CJ Dropshipping DELETION ===")
    log.info("Shop: %s", SHOP)

    async with aiohttp.ClientSession() as session:
        ids = await fetch_remaining_cj_ids(session)

    if not ids:
        log.info("No active CJ Dropshipping products remaining — all clean!")
        return

    log.info("Deleting %d remaining active CJ Dropshipping products...", len(ids))
    async with aiohttp.ClientSession() as session:
        ok, err = await delete_products(session, ids)

    log.info("=== DONE ===")
    log.info("Deleted: %d", ok)
    log.info("Errors:  %d", err)


if __name__ == "__main__":
    asyncio.run(main())
