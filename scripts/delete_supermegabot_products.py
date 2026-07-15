"""
Lösche alle aktiven SuperMegaBot Fake-Produkte (vendor=SuperMegaBot).
"""
import asyncio
import logging
import os
import re
import aiohttp
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

SHOP    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
API_VER = os.getenv("SHOPIFY_API_VERSION", "2024-04")
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}
TIMEOUT = aiohttp.ClientTimeout(total=60, connect=15)


async def fetch_ids(session: aiohttp.ClientSession) -> list[str]:
    base = f"https://{SHOP}/admin/api/{API_VER}/products.json"
    ids: list[str] = []
    page_info = None
    page = 0
    while True:
        if page_info:
            params = {"limit": 250, "page_info": page_info}
        else:
            params = {"limit": 250, "vendor": "SuperMegaBot", "status": "active",
                      "fields": "id,title"}
        async with session.get(base, headers=HEADERS, params=params, timeout=TIMEOUT) as r:
            data = await r.json()
            products = data.get("products", [])
            ids.extend(str(p["id"]) for p in products)
            page += 1
            log.info("Seite %d: %d SuperMegaBot-Produkte (gesamt %d)", page, len(products), len(ids))
            link = r.headers.get("Link", "")
            if 'rel="next"' not in link:
                break
            m = re.search(r'page_info=([^&>]+).*?rel="next"', link)
            if not m:
                break
            page_info = m.group(1)
    return ids


async def delete_one(session: aiohttp.ClientSession, pid: str) -> bool:
    url = f"https://{SHOP}/admin/api/{API_VER}/products/{pid}.json"
    for _ in range(3):
        async with session.delete(url, headers=HEADERS, timeout=TIMEOUT) as r:
            if r.status == 429:
                await asyncio.sleep(float(r.headers.get("Retry-After", "2")))
                continue
            return r.status in (200, 204)
    return False


async def main():
    log.info("=== SuperMegaBot FAKE-PRODUKTE LÖSCHUNG ===")
    conn = aiohttp.TCPConnector(limit=5, ssl=False)
    async with aiohttp.ClientSession(connector=conn) as session:
        ids = await fetch_ids(session)
        log.info("Gesamt gefunden: %d SuperMegaBot-Produkte", len(ids))
        ok = errors = 0
        CHUNK = 5
        for i in range(0, len(ids), CHUNK):
            chunk = ids[i:i+CHUNK]
            results = await asyncio.gather(
                *[delete_one(session, pid) for pid in chunk],
                return_exceptions=True
            )
            for r in results:
                if r is True:
                    ok += 1
                else:
                    errors += 1
            await asyncio.sleep(0.15)
            if (i // CHUNK) % 20 == 0:
                log.info("Progress: %d/%d gelöscht (errors: %d)", ok, len(ids), errors)
        log.info("=== DONE: %d gelöscht | %d Fehler ===", ok, errors)


if __name__ == "__main__":
    asyncio.run(main())
