"""
Google Shopping Feed Generator for ineedit.com.co
Generates a valid Google Merchant Center RSS 2.0 XML feed
from Shopify products and caches it for 6 hours.
"""

import asyncio
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom

import aiohttp

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CACHE_PATH = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data")) / "google_shopping_feed.xml"
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours
MAX_PRODUCTS = 250            # feed cap
PAGE_SIZE = 50                # Shopify pagination limit per request

PRODUCT_TYPE_MAP: dict[str, str] = {
    "Smart Home": "Connected Home Devices",
    "smart home": "Connected Home Devices",
    "Gadgets": "Electronics",
    "gadgets": "Electronics",
    "Electronics": "Electronics > Consumer Electronics",
    "Solar": "Outdoor Recreation > Camping & Hiking > Camping Lights & Lanterns",
    "Power Station": "Electronics > Power",
    "E-Bike": "Sporting Goods > Cycling > Electric Bikes",
    "Home & Garden": "Home & Garden",
    "Tools": "Hardware > Tools",
    "Fitness": "Sporting Goods > Exercise & Fitness",
}
DEFAULT_CATEGORY = "Electronics > Consumer Electronics"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_html(html: str) -> str:
    """Remove HTML tags, JSON-LD blocks, promo suffixes and normalise whitespace."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    # Remove JSON-LD blocks Shopify appends to body_html
    text = re.sub(r'\{"\s*@context".*', "", text, flags=re.DOTALL)
    # Remove promotional suffixes (emoji-led promo lines)
    text = re.sub(r"[\U00010000-\U0010ffff🎁💡🛍️✅👉🔥⚡]+.*$", "", text, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:5000]


def _map_category(product_type: str) -> str:
    if not product_type:
        return DEFAULT_CATEGORY
    for key, value in PRODUCT_TYPE_MAP.items():
        if key.lower() in product_type.lower():
            return value
    return DEFAULT_CATEGORY


def _cache_is_valid() -> bool:
    if not CACHE_PATH.exists():
        return False
    age = time.time() - CACHE_PATH.stat().st_mtime
    return age < CACHE_TTL_SECONDS


# ---------------------------------------------------------------------------
# Shopify fetcher
# ---------------------------------------------------------------------------

async def _fetch_shopify_products(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch up to MAX_PRODUCTS published products from the Shopify Admin API."""
    shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")
    token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    api_version = os.getenv("SHOPIFY_API_VERSION", "2024-01")

    if not token:
        log.error("SHOPIFY_ADMIN_API_TOKEN is not set — cannot fetch products")
        return []

    base_url = f"https://{shop_domain}/admin/api/{api_version}/products.json"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }

    products: list[dict] = []
    params = {
        "limit": PAGE_SIZE,
        "published_status": "published",
        "fields": "id,title,body_html,vendor,product_type,handle,variants,images,tags",
        "status": "active",
    }
    page_info: str | None = None
    fetched = 0

    while fetched < MAX_PRODUCTS:
        call_params = dict(params)
        if page_info:
            call_params = {"limit": PAGE_SIZE, "page_info": page_info}

        try:
            async with session.get(base_url, headers=headers, params=call_params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 429:
                    retry_after = float(resp.headers.get("Retry-After", "2"))
                    log.warning("Shopify rate-limit hit — sleeping %.1fs", retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                if resp.status != 200:
                    body = await resp.text()
                    log.error("Shopify API error %s: %s", resp.status, body[:200])
                    break

                data = await resp.json()
                page_products = data.get("products", [])

                if not page_products:
                    break

                products.extend(page_products)
                fetched += len(page_products)
                log.debug("Fetched %d products so far", fetched)

                # Parse Link header for cursor-based pagination
                link_header = resp.headers.get("Link", "")
                next_page_info = _parse_next_page_info(link_header)
                if not next_page_info or fetched >= MAX_PRODUCTS:
                    break
                page_info = next_page_info

        except aiohttp.ClientError as exc:
            log.error("Network error fetching Shopify products: %s", exc)
            break

    return products[:MAX_PRODUCTS]


def _parse_next_page_info(link_header: str) -> str | None:
    """Extract page_info for the 'next' rel from a Shopify Link header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part:
            match = re.search(r'page_info=([^&>]+)', part)
            if match:
                return match.group(1)
    return None


# ---------------------------------------------------------------------------
# XML builder
# ---------------------------------------------------------------------------

def _build_xml(products: list[dict], shop_domain: str) -> str:
    """Build a Google Merchant Center RSS 2.0 XML string from product list."""
    rss = ET.Element("rss", {
        "version": "2.0",
        "xmlns:g": "http://base.google.com/ns/1.0",
    })
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "ineedit.com.co — Smart Products"
    ET.SubElement(channel, "link").text = f"https://{shop_domain}"
    ET.SubElement(channel, "description").text = (
        "Google Shopping product feed for ineedit.com.co"
    )

    item_count = 0
    for product in products:
        product_id = product.get("id")
        title = (product.get("title") or "").strip()
        handle = product.get("handle", "")
        vendor = (product.get("vendor") or "").strip()
        product_type = (product.get("product_type") or "").strip()
        body_html = product.get("body_html") or ""
        images = product.get("images") or []
        variants = product.get("variants") or []

        if not variants:
            continue

        description = _strip_html(body_html) or title
        image_link = images[0]["src"] if images and images[0].get("src") else ""
        product_url = f"https://{shop_domain}/products/{handle}"
        category = _map_category(product_type)

        # Skip products without image — GMC requires g:image_link
        if not image_link:
            log.debug("Skipping product %s (no image)", product_id)
            continue

        for variant in variants:
            variant_id = variant.get("id")
            price = variant.get("price")
            if not price:
                continue

            try:
                price_float = float(price)
            except (TypeError, ValueError):
                continue

            # Skip zero-price variants
            if price_float <= 0:
                continue

            item = ET.SubElement(channel, "item")

            _g(item, "id", f"shopify-{product_id}-{variant_id}")
            _g(item, "title", title[:150])
            _g(item, "description", description)
            ET.SubElement(item, "link").text = product_url
            if image_link:
                _g(item, "image_link", image_link)
            _g(item, "price", f"{price_float:.2f} EUR")
            _g(item, "availability", "in stock")
            _g(item, "condition", "new")
            _g(item, "content_language", "de")
            _g(item, "target_country", "DE")
            if vendor:
                _g(item, "brand", vendor)
            _g(item, "google_product_category", category)
            _g(item, "identifier_exists", "no")

            item_count += 1

    log.info("Built Google Shopping feed with %d items from %d products", item_count, len(products))

    # Pretty-print
    raw = ET.tostring(rss, encoding="unicode", xml_declaration=False)
    try:
        pretty = minidom.parseString(f'<?xml version="1.0" encoding="UTF-8"?>{raw}')
        return pretty.toprettyxml(indent="  ", encoding=None)
    except Exception:
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{raw}'


def _g(parent: ET.Element, tag: str, text: str) -> ET.Element:
    """Add a g:-namespaced child element."""
    el = ET.SubElement(parent, f"g:{tag}")
    el.text = text
    return el


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_feed() -> str:
    """
    Generate (or return cached) Google Shopping RSS 2.0 XML feed.

    Returns:
        str — valid XML string.
    """
    if _cache_is_valid():
        log.info("Returning cached Google Shopping feed from %s", CACHE_PATH)
        return CACHE_PATH.read_text(encoding="utf-8")

    # Use custom storefront domain for product URLs (not internal myshopify domain)
    storefront_domain = os.getenv("SHOPIFY_STOREFRONT_DOMAIN", "ineedit.com.co")

    async with aiohttp.ClientSession() as session:
        products = await _fetch_shopify_products(session)

    if not products:
        log.warning("Shopify returned 0 products — returning empty feed (no fake data)")
        xml_str = _build_xml([], storefront_domain)
    else:
        log.info("Generating Google Shopping feed for %d products", len(products))
        xml_str = _build_xml(products, storefront_domain)

    # Persist cache
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(xml_str, encoding="utf-8")
        log.info("Cached Google Shopping feed to %s (%d bytes)", CACHE_PATH, len(xml_str))
    except OSError as exc:
        log.error("Could not write feed cache: %s", exc)

    return xml_str


async def get_feed_stats() -> dict:
    """
    Return metadata about the cached feed.

    Returns:
        dict with keys:
            products_in_feed  (int)
            last_generated    (str ISO-8601 or None)
            file_size_kb      (float)
            top_categories    (list[str])
    """
    stats: dict = {
        "products_in_feed": 0,
        "last_generated": None,
        "file_size_kb": 0.0,
        "top_categories": [],
    }

    if not CACHE_PATH.exists():
        return stats

    mtime = CACHE_PATH.stat().st_mtime
    stats["last_generated"] = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    stats["file_size_kb"] = round(CACHE_PATH.stat().st_size / 1024, 2)

    try:
        content = CACHE_PATH.read_text(encoding="utf-8")
        stats["products_in_feed"] = content.count("<item>")

        # Extract top categories
        cats = re.findall(r"<g:google_product_category>([^<]+)</g:google_product_category>", content)
        from collections import Counter
        counter = Counter(cats)
        stats["top_categories"] = [cat for cat, _ in counter.most_common(5)]
    except OSError as exc:
        log.error("Could not read feed cache for stats: %s", exc)

    return stats


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    async def _main() -> None:
        xml = await generate_feed()
        print(xml[:800])
        print("...")
        stats = await get_feed_stats()
        print("\nFeed stats:", stats)

    asyncio.run(_main())
