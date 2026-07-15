"""
Archive all CJ Dropshipping products from the Shopify store.
These are the mass-imported 0-inventory fake/junk products.
Run: python3 scripts/archive_cj_products.py
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

JUNK_VENDORS = {"CJ Dropshipping", "cj dropshipping"}


async def fetch_cj_product_ids(session: aiohttp.ClientSession) -> list[str]:
    """Paginate through all active CJ Dropshipping products and return their IDs."""
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
                "fields": "id,vendor,status",
            }

        try:
            async with session.get(base, headers=HEADERS, params=params, timeout=TIMEOUT) as resp:
                if resp.status == 429:
                    retry = float(resp.headers.get("Retry-After", "2"))
                    log.warning("Rate limit — sleeping %.1fs", retry)
                    await asyncio.sleep(retry)
                    continue
                if resp.status != 200:
                    log.error("Shopify error %s: %s", resp.status, await resp.text())
                    break
                data = await resp.json()
                products = data.get("products", [])
                if not products:
                    break

                batch_ids = [str(p["id"]) for p in products]
                ids.extend(batch_ids)
                log.info("Page %d: found %d CJ products (total %d)", page, len(batch_ids), len(ids))

                link = resp.headers.get("Link", "")
                page_info = _parse_next(link)
                if not page_info:
                    break

        except aiohttp.ClientError as e:
            log.error("Network error: %s", e)
            break

    return ids


def _parse_next(link: str) -> str | None:
    import re
    for part in link.split(","):
        if 'rel="next"' in part:
            m = re.search(r"page_info=([^&>]+)", part)
            if m:
                return m.group(1)
    return None


async def archive_products(session: aiohttp.ClientSession, product_ids: list[str]) -> tuple[int, int]:
    """Archive a list of products by ID. Returns (success_count, error_count)."""
    ok = 0
    err = 0
    for pid in product_ids:
        url = f"https://{SHOP}/admin/api/{API_VER}/products/{pid}.json"
        payload = {"product": {"id": pid, "status": "archived"}}
        try:
            async with session.put(url, headers=HEADERS, json=payload, timeout=TIMEOUT) as resp:
                if resp.status == 429:
                    retry = float(resp.headers.get("Retry-After", "2"))
                    await asyncio.sleep(retry)
                    # retry once
                    async with session.put(url, headers=HEADERS, json=payload, timeout=TIMEOUT) as r2:
                        if r2.status == 200:
                            ok += 1
                        else:
                            err += 1
                elif resp.status == 200:
                    ok += 1
                else:
                    log.warning("Failed to archive %s: HTTP %s", pid, resp.status)
                    err += 1
        except aiohttp.ClientError as e:
            log.error("Network error archiving %s: %s", pid, e)
            err += 1
        # Small delay to avoid hammering the API
        await asyncio.sleep(0.1)
    return ok, err


async def main() -> None:
    if not SHOP or not TOKEN:
        log.error("SHOPIFY_SHOP_DOMAIN or SHOPIFY_ADMIN_API_TOKEN not set")
        sys.exit(1)

    log.info("=== CJ Dropshipping Cleanup ===")
    log.info("Shop: %s", SHOP)

    async with aiohttp.ClientSession() as session:
        # Step 1: collect all CJ product IDs
        log.info("Scanning for CJ Dropshipping products...")
        ids = await fetch_cj_product_ids(session)
        log.info("Found %d CJ Dropshipping products to archive", len(ids))

        if not ids:
            log.info("No CJ Dropshipping products found — store is already clean!")
            return

        # Step 2: archive in parallel chunks (5 concurrent to avoid rate limits)
        CHUNK = 5
        total_ok = 0
        total_err = 0

        for i in range(0, len(ids), CHUNK):
            chunk = ids[i : i + CHUNK]
            ok, err = await archive_products(session, chunk)
            total_ok += ok
            total_err += err
            done = i + len(chunk)
            pct = done / len(ids) * 100
            log.info("Progress: %d/%d (%.0f%%) — archived %d, errors %d",
                     done, len(ids), pct, total_ok, total_err)

    log.info("=== DONE ===")
    log.info("Total archived: %d", total_ok)
    log.info("Total errors:   %d", total_err)
    log.info("Remaining active CJ products: %d (check Shopify)", total_err)


if __name__ == "__main__":
    asyncio.run(main())
