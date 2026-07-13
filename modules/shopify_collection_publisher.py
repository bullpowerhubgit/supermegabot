"""
Shopify Collection Publisher — Publiziert alle unpublizierten Smart Collections
Läuft alle 6h; stellt sicher dass neu erstellte Collections sofort live sind.
"""
import asyncio
import logging
import os

import aiohttp

log = logging.getLogger("CollectionPublisher")

SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOKEN  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")


def _base() -> str:
    return f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}"


def _hdrs() -> dict:
    return {"X-Shopify-Access-Token": SHOP_TOKEN, "Content-Type": "application/json"}


async def publish_all_smart_collections() -> dict:
    """Fetched alle Smart Collections und publiziert unpublizierte."""
    if not SHOP_DOMAIN or not SHOP_TOKEN:
        return {"ok": False, "error": "Shopify credentials fehlen"}

    async with aiohttp.ClientSession() as s:
        all_sc = []
        page_info = None
        import re

        while True:
            params = {"limit": 250}
            if page_info:
                params["page_info"] = page_info
            try:
                async with s.get(f"{_base()}/smart_collections.json", headers=_hdrs(),
                                 params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status == 429:
                        await asyncio.sleep(15)
                        continue
                    if r.status != 200:
                        return {"ok": False, "error": f"HTTP {r.status}"}
                    sc = (await r.json()).get("smart_collections", [])
                    all_sc.extend(sc)
                    link = r.headers.get("Link", "")
                    if 'rel="next"' in link:
                        m = re.search(r'page_info=([^>&"]+).*?rel="next"', link)
                        page_info = m.group(1) if m else None
                    else:
                        break
            except Exception as e:
                log.warning("fetch smart_collections: %s", e)
                break
            await asyncio.sleep(1)

        unpublished = [c for c in all_sc if not c.get("published_at")]
        published_count = 0
        errors = 0

        for c in unpublished:
            cid = c["id"]
            try:
                async with s.put(
                    f"{_base()}/smart_collections/{cid}.json", headers=_hdrs(),
                    json={"smart_collection": {"id": cid, "published": True}},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r2:
                    if r2.status in (200, 201):
                        published_count += 1
                        log.info("Published: %s", c.get("title", cid))
                    elif r2.status == 429:
                        await asyncio.sleep(10)
                        errors += 1
                    else:
                        errors += 1
                        log.warning("Publish failed %s: HTTP %s", c.get("title"), r2.status)
            except Exception as e:
                log.warning("publish %s: %s", cid, e)
                errors += 1
            await asyncio.sleep(0.7)

    return {
        "ok": True,
        "total_smart_collections": len(all_sc),
        "newly_published": published_count,
        "already_published": len(all_sc) - len(unpublished),
        "errors": errors,
    }


async def get_status() -> dict:
    return {"ok": True, "module": "Shopify Collection Publisher"}
