"""
GMC Product Fixer — Sets Google Shopping compliance metafields for all Shopify products.
- identifier_exists: false  (for products without GTIN/barcode)
- condition: new
- Generates SKUs for variants without SKU
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os

import aiohttp

log = logging.getLogger("GMCProductFixer")

SHOP = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
VER = os.getenv("SHOPIFY_API_VERSION", "2024-10")


def _headers() -> dict:
    return {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}


def generate_sku(product_id: str, variant_id: str) -> str:
    h = hashlib.md5(f"{product_id}{variant_id}".encode()).hexdigest().upper()
    return f"SMB-{h[:6]}"


async def add_product_metafield(product_id: str, namespace: str, key: str,
                                 value: str, value_type: str = "string") -> dict:
    if not SHOP or not TOKEN:
        return {"error": "no shopify credentials"}
    url = f"https://{SHOP}/admin/api/{VER}/products/{product_id}/metafields.json"
    payload = {"metafield": {"namespace": namespace, "key": key,
                              "value": value, "type": value_type}}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.post(url, headers=_headers(), json=payload) as r:
            data = await r.json()
            return data.get("metafield", data)


async def update_variant_sku(product_id: str, variant_id: str, sku: str) -> dict:
    if not SHOP or not TOKEN:
        return {"error": "no shopify credentials"}
    url = f"https://{SHOP}/admin/api/{VER}/products/{product_id}/variants/{variant_id}.json"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.put(url, headers=_headers(),
                         json={"variant": {"id": int(variant_id), "sku": sku}}) as r:
            data = await r.json()
            return data.get("variant", data)


async def fix_product_gmc_compliance(product: dict) -> bool:
    pid = str(product.get("id", ""))
    try:
        # Set identifier_exists: false (no GTIN)
        await add_product_metafield(pid, "google", "identifier_exists", "false")
        await asyncio.sleep(0.1)
        # Set condition: new
        await add_product_metafield(pid, "google", "condition", "new")

        # Generate SKUs for variants without one
        for v in product.get("variants", []):
            if not v.get("sku"):
                sku = generate_sku(pid, str(v["id"]))
                await update_variant_sku(pid, str(v["id"]), sku)
                await asyncio.sleep(0.1)

        log.info("GMC fixed product %s (%s)", pid, product.get("title", "")[:40])
        return True
    except Exception as e:
        log.error("GMC fix error product %s: %s", pid, e)
        return False


async def bulk_fix_all_products(limit: int = 250) -> dict:
    if not SHOP or not TOKEN:
        return {"error": "no shopify credentials", "fixed": 0, "errors": 0, "total": 0}

    fixed = errors = total = 0
    page_info = None

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        while True:
            params = {"limit": limit, "fields": "id,title,variants"}
            if page_info:
                params = {"limit": limit, "fields": "id,title,variants",
                          "page_info": page_info}
            async with s.get(
                f"https://{SHOP}/admin/api/{VER}/products.json",
                headers=_headers(), params=params
            ) as r:
                data = await r.json()
                products = data.get("products", [])
                # Check for next page in Link header
                link_header = r.headers.get("Link", "")
                next_page = None
                if 'rel="next"' in link_header:
                    for part in link_header.split(","):
                        if 'rel="next"' in part:
                            import re
                            m = re.search(r'page_info=([^&>]+)', part)
                            if m:
                                next_page = m.group(1)

            total += len(products)
            # Only fix products missing barcode
            needs_fix = [p for p in products
                         if any(not v.get("barcode") for v in p.get("variants", []))]

            for product in needs_fix:
                ok = await fix_product_gmc_compliance(product)
                if ok:
                    fixed += 1
                else:
                    errors += 1
                await asyncio.sleep(0.5)

            if not next_page:
                break
            page_info = next_page

    log.info("GMC bulk fix complete: %d fixed, %d errors, %d total", fixed, errors, total)
    return {"fixed": fixed, "errors": errors, "total": total}


async def run_gmc_fixer_cycle() -> dict:
    result = await bulk_fix_all_products()
    return result
