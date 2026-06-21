#!/usr/bin/env python3
"""
Shopify SEO Batch Optimizer — kein AI nötig, läuft sofort.
Setzt meta_title + meta_description auf alle Produkte ohne SEO-Tags.
"""
import asyncio, os, json, logging, sys, time
from pathlib import Path

# Load .env manually
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import aiohttp

log = logging.getLogger("SEOBatch")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DOMAIN   = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TOKEN    = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
VER      = os.getenv("SHOPIFY_API_VERSION", "2024-10")
BASE     = f"https://{DOMAIN}/admin/api/{VER}"
BATCH    = 250     # products per page
CONCUR   = 1       # sequential — Shopify Basic allows 2 req/sec
DELAY    = 0.6     # seconds between API calls (stay under 2 req/sec)

SUFFIX_MAP = {
    "beamer": "Heimkino Beamer",
    "drucker": "3D Drucker",
    "kopfhörer": "Bluetooth Kopfhörer",
    "lautsprecher": "Bluetooth Lautsprecher",
    "kamera": "Action Kamera",
    "uhr": "Smartwatch",
    "watch": "Smartwatch",
    "handy": "Smartphone Zubehör",
    "solar": "Solar Energie",
    "fitness": "Fitness Geräte",
    "küche": "Küchengeräte",
    "garten": "Gartengeräte",
}

def _make_seo(title: str) -> tuple[str, str]:
    """Generate meta_title + meta_description from product title."""
    clean = title.strip()
    # SEO Title: max 70 chars
    suffix = "kaufen"
    for kw, label in SUFFIX_MAP.items():
        if kw.lower() in clean.lower():
            suffix = f"günstig kaufen"
            break
    meta_title = f"{clean} | Jetzt günstig kaufen"
    if len(meta_title) > 70:
        meta_title = clean[:57] + " kaufen"
    # Meta description: 150-160 chars
    meta_desc = (
        f"{clean} ✓ Günstige Preise ✓ Schnelle Lieferung ✓ "
        f"Top-Qualität. Jetzt im Shop bestellen und sparen!"
    )
    if len(meta_desc) > 160:
        meta_desc = meta_desc[:157] + "..."
    return meta_title, meta_desc


async def get_all_products(session: aiohttp.ClientSession) -> list:
    """Fetch all products via REST pagination."""
    products = []
    url = f"{BASE}/products.json?limit={BATCH}&fields=id,title,metafields_global_title_tag&published_status=any"
    page = 1
    while url:
        async with session.get(url, headers={"X-Shopify-Access-Token": TOKEN}) as r:
            if r.status != 200:
                log.error("Fetch page %d failed: HTTP %s", page, r.status)
                break
            data = await r.json(content_type=None)
            batch = data.get("products", [])
            products.extend(batch)
            log.info("Page %d: fetched %d products (total so far: %d)", page, len(batch), len(products))
            # Pagination via Link header
            link_hdr = r.headers.get("Link", "")
            next_url = None
            for part in link_hdr.split(","):
                if 'rel="next"' in part:
                    next_url = part.strip().split(";")[0].strip().strip("<>")
                    break
            url = next_url
            page += 1
            await asyncio.sleep(DELAY)
    return products


async def update_product_seo(session: aiohttp.ClientSession, product_id: int, title: str, sem: asyncio.Semaphore) -> bool:
    """Update a single product's SEO meta title + description."""
    meta_title, meta_desc = _make_seo(title)
    payload = {
        "product": {
            "id": product_id,
            "metafields_global_title_tag": meta_title,
            "metafields_global_description_tag": meta_desc,
        }
    }
    async with sem:
        try:
            async with session.put(
                f"{BASE}/products/{product_id}.json",
                json=payload,
                headers={"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"},
            ) as r:
                if r.status == 200:
                    return True
                body = await r.text()
                log.warning("Update %d failed HTTP %s: %s", product_id, r.status, body[:120])
                return False
        except Exception as e:
            log.error("Update %d exception: %s", product_id, e)
            return False
        finally:
            await asyncio.sleep(DELAY)


async def main():
    if not DOMAIN or not TOKEN:
        print("ERROR: SHOPIFY_SHOP_DOMAIN oder SHOPIFY_ADMIN_API_TOKEN fehlt!")
        sys.exit(1)

    log.info("Shopify SEO Batch Optimizer gestartet")
    log.info("Store: %s", DOMAIN)

    async with aiohttp.ClientSession() as session:
        # 1. Fetch all products
        log.info("Lade alle Produkte...")
        products = await get_all_products(session)
        log.info("Gesamt: %d Produkte geladen", len(products))

        # 2. Filter: only those without meta_title
        to_update = [
            p for p in products
            if not p.get("metafields_global_title_tag")
        ]
        log.info("%d Produkte ohne SEO-Meta-Title → werden optimiert", len(to_update))

        if not to_update:
            log.info("Alle Produkte haben bereits SEO-Tags. Fertig!")
            return

        # 3. Batch update with concurrency limit
        sem = asyncio.Semaphore(CONCUR)
        done = 0
        errors = 0

        tasks = [
            update_product_seo(session, int(p["id"]), p["title"], sem)
            for p in to_update
        ]

        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            ok = await coro
            if ok:
                done += 1
            else:
                errors += 1
            if i % 50 == 0 or i == len(tasks):
                log.info("Fortschritt: %d/%d ✅ %d Fehler", i, len(tasks), errors)

    log.info("=" * 50)
    log.info("FERTIG: %d Produkte SEO-optimiert, %d Fehler", done, errors)
    log.info("Google kann jetzt alle Produkte besser finden!")


if __name__ == "__main__":
    asyncio.run(main())
