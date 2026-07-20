"""
Price Comparison Feed Generator — Idealo, PriceRunner, Kelkoo
Generates product feeds for free listings on German price comparison sites.

Feeds are cached in data/ for 4 hours. No fake/demo data: empty Shopify
response produces empty feeds and a warning.
"""

import asyncio
import csv
import io
import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

CACHE_TTL_SECONDS = 4 * 3600  # 4 hours
DATA_DIR = Path(__file__).parent.parent / "data"

HANDLER_NAME = "ineedit.com.co"
SHIPPING_COST = "0,00 EUR"
DELIVERY_TIME = "2-4 Werktage"
STORE_BASE_URL = "https://ineedit.com.co"

FEED_FILES = {
    "idealo": DATA_DIR / "idealo_feed.csv",
    "pricerunner": DATA_DIR / "pricerunner_feed.xml",
    "kelkoo": DATA_DIR / "kelkoo_feed.csv",
}


# ─── Shopify helpers ──────────────────────────────────────────────────────────

def _shopify_env() -> tuple[str, str, str]:
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "").strip().rstrip("/")
    token = (
        os.getenv("SHOPIFY_ADMIN_API_TOKEN")
        or os.getenv("SHOPIFY_SUITE_ACCESS_TOKEN")
        or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    )
    version = os.getenv("SHOPIFY_API_VERSION", "2026-04")
    return domain, token, version


def _product_url(handle: str) -> str:
    return f"{STORE_BASE_URL}/products/{handle}"


def _normalize_price(price_str: Optional[str]) -> str:
    """Convert Shopify price string (e.g. '29.99') to feed format '29.99'."""
    if not price_str:
        return "0.00"
    try:
        return f"{float(price_str):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _clean_text(text: Optional[str], max_len: int = 0) -> str:
    """Strip HTML tags and truncate."""
    if not text:
        return ""
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_len and len(text) > max_len:
        text = text[:max_len - 3] + "..."
    return text


def _map_product(raw: dict) -> dict:
    """Flatten a Shopify REST product dict to our internal schema."""
    variants = raw.get("variants") or []
    first_variant = variants[0] if variants else {}

    images = raw.get("images") or []
    image_url = ""
    if images:
        image_url = images[0].get("src", "")

    price = first_variant.get("price") or raw.get("variants", [{}])[0].get("price", "0.00") if variants else "0.00"
    compare_at = first_variant.get("compare_at_price") or ""

    vendor = raw.get("vendor", "")
    product_type = raw.get("product_type", "")
    handle = raw.get("handle", str(raw.get("id", "")))

    return {
        "id": str(raw.get("id", "")),
        "title": raw.get("title", ""),
        "price": _normalize_price(price),
        "compare_at_price": _normalize_price(compare_at) if compare_at else "",
        "url": _product_url(handle),
        "image": image_url,
        "brand": vendor,
        "description": _clean_text(raw.get("body_html", ""), max_len=500),
        "category": product_type,
    }


# ─── Shopify product fetch ────────────────────────────────────────────────────

async def fetch_shopify_products(limit: int = 500) -> list[dict]:
    """
    Fetch products from Shopify Admin REST API with cursor pagination.

    Uses env vars: SHOPIFY_SHOP_DOMAIN, SHOPIFY_ADMIN_API_TOKEN,
    SHOPIFY_API_VERSION.

    Returns list of normalised product dicts. Returns [] on error (with warning).
    """
    try:
        import aiohttp
    except ImportError:
        logger.error("aiohttp not installed — cannot fetch Shopify products")
        return []

    domain, token, version = _shopify_env()
    if not domain or not token:
        logger.warning(
            "SHOPIFY_SHOP_DOMAIN or SHOPIFY_ADMIN_API_TOKEN not set — "
            "returning empty product list"
        )
        return []

    base_url = f"https://{domain}/admin/api/{version}/products.json"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }

    products: list[dict] = []
    page_info: Optional[str] = None
    page_size = min(limit, 250)  # Shopify max per page is 250

    logger.info("Fetching Shopify products (limit=%d, page_size=%d) …", limit, page_size)

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            while True:
                remaining = limit - len(products)
                if remaining <= 0:
                    break

                if page_info:
                    # Shopify: status cannot be passed when page_info is present
                    params: dict = {
                        "limit": min(page_size, remaining),
                        "page_info": page_info,
                    }
                else:
                    params = {
                        "limit": min(page_size, remaining),
                        "fields": "id,title,handle,body_html,vendor,product_type,variants,images",
                        "status": "active",
                    }

                async with session.get(base_url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error(
                            "Shopify API error %s: %s", resp.status, body[:200]
                        )
                        break

                    data = await resp.json()
                    batch = data.get("products", [])
                    if not batch:
                        break

                    for raw in batch:
                        products.append(_map_product(raw))

                    logger.debug("Fetched page: %d products (total so far: %d)", len(batch), len(products))

                    # Parse Link header for cursor pagination
                    link_header = resp.headers.get("Link", "")
                    next_page_info = _parse_next_page_info(link_header)
                    if not next_page_info or len(products) >= limit:
                        break
                    page_info = next_page_info

    except asyncio.TimeoutError:
        logger.error("Timeout fetching Shopify products after %d fetched", len(products))
    except Exception as exc:
        logger.error("Unexpected error fetching Shopify products: %s", exc, exc_info=True)

    if not products:
        logger.warning("Shopify returned 0 products — feeds will be empty")

    logger.info("Fetched %d products from Shopify", len(products))
    return products


def _parse_next_page_info(link_header: str) -> Optional[str]:
    """Extract page_info token for the 'next' rel from a Shopify Link header."""
    if not link_header:
        return None
    import re
    # Example: <https://…?page_info=abc>; rel="next"
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part:
            match = re.search(r'page_info=([^&>]+)', part)
            if match:
                return match.group(1)
    return None


# ─── Cache helpers ─────────────────────────────────────────────────────────────

def _is_cache_valid(path: Path) -> bool:
    """Return True if file exists and is younger than CACHE_TTL_SECONDS."""
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < CACHE_TTL_SECONDS


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# ─── Idealo CSV ───────────────────────────────────────────────────────────────

# Idealo DE merchant feed columns (standard CSV format)
IDEALO_COLUMNS = [
    "EAN",
    "Artikel-ID",
    "Bezeichnung",
    "Preis",
    "Händler-ID",
    "Händlername",
    "Beschreibung",
    "Bild-URL",
    "Deeplink",
    "Kategorie",
    "Lieferzeit",
    "Versandkosten",
]


async def generate_idealo_csv(products: Optional[list[dict]] = None) -> str:
    """
    Generate Idealo DE product feed as CSV string.

    Fetches products if not supplied. Returns empty CSV (headers only) when
    Shopify returns no products.
    """
    if products is None:
        products = await fetch_shopify_products()

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=IDEALO_COLUMNS,
        delimiter=";",
        quoting=csv.QUOTE_ALL,
        lineterminator="\n",
    )
    writer.writeheader()

    if not products:
        logger.warning("generate_idealo_csv: no products — writing headers only")
        return output.getvalue()

    for p in products:
        price_str = p["price"].replace(".", ",") + " EUR"  # German decimal format
        writer.writerow({
            "EAN": "",
            "Artikel-ID": f"shopify-{p['id']}",
            "Bezeichnung": p["title"],
            "Preis": price_str,
            "Händler-ID": "",
            "Händlername": HANDLER_NAME,
            "Beschreibung": p["description"],
            "Bild-URL": p["image"],
            "Deeplink": p["url"],
            "Kategorie": p["category"],
            "Lieferzeit": DELIVERY_TIME,
            "Versandkosten": SHIPPING_COST,
        })

    csv_str = output.getvalue()
    logger.info("Idealo CSV generated: %d rows", len(products))
    return csv_str


# ─── PriceRunner XML ──────────────────────────────────────────────────────────

async def generate_pricerunner_xml(products: Optional[list[dict]] = None) -> str:
    """
    Generate PriceRunner product feed as XML string.

    Schema: <products><product> with child elements per product.
    """
    if products is None:
        products = await fetch_shopify_products()

    if not products:
        logger.warning("generate_pricerunner_xml: no products — writing empty feed")

    root = ET.Element("products")
    root.set("generated_at", datetime.now(timezone.utc).isoformat())

    for p in products:
        prod_el = ET.SubElement(root, "product")

        def _sub(tag: str, text: str) -> ET.Element:
            el = ET.SubElement(prod_el, tag)
            el.text = text
            return el

        _sub("id", f"shopify-{p['id']}")
        _sub("name", p["title"])

        price_el = ET.SubElement(prod_el, "price")
        price_el.set("currency", "EUR")
        price_el.text = p["price"]

        _sub("url", p["url"])
        _sub("image-url", p["image"])
        _sub("description", p["description"])
        _sub("brand", p["brand"])
        _sub("category", p["category"])
        _sub("delivery-time", DELIVERY_TIME)
        _sub("shipping-cost", SHIPPING_COST)

    # Pretty-print
    _indent_xml(root)
    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    xml_str = buf.getvalue().decode("utf-8")

    logger.info("PriceRunner XML generated: %d products", len(products))
    return xml_str


def _indent_xml(elem: ET.Element, level: int = 0) -> None:
    """Add pretty-print indentation in place (Python < 3.9 compat fallback)."""
    indent = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
        for child in elem:
            _indent_xml(child, level + 1)
        # Last child tail
        if not child.tail or not child.tail.strip():  # noqa: F821
            child.tail = indent
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = indent


# ─── Kelkoo / Twenga CSV ─────────────────────────────────────────────────────

KELKOO_COLUMNS = [
    "offer-id",
    "title",
    "product-url",
    "image-url",
    "price",
    "description",
    "category",
    "brand",
    "delivery-cost",
    "delivery-time",
]


async def generate_kelkoo_csv(products: Optional[list[dict]] = None) -> str:
    """
    Generate Kelkoo/Twenga product feed as CSV string.

    Returns empty CSV (headers only) when Shopify returns no products.
    """
    if products is None:
        products = await fetch_shopify_products()

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=KELKOO_COLUMNS,
        delimiter=",",
        quoting=csv.QUOTE_ALL,
        lineterminator="\n",
    )
    writer.writeheader()

    if not products:
        logger.warning("generate_kelkoo_csv: no products — writing headers only")
        return output.getvalue()

    for p in products:
        writer.writerow({
            "offer-id": f"shopify-{p['id']}",
            "title": p["title"],
            "product-url": p["url"],
            "image-url": p["image"],
            "price": f"{p['price']} EUR",
            "description": p["description"],
            "category": p["category"],
            "brand": p["brand"],
            "delivery-cost": "0.00 EUR",
            "delivery-time": DELIVERY_TIME,
        })

    csv_str = output.getvalue()
    logger.info("Kelkoo CSV generated: %d rows", len(products))
    return csv_str


# ─── Refresh all feeds ────────────────────────────────────────────────────────

async def refresh_all_feeds() -> dict:
    """
    Fetch products once and regenerate all three feeds, writing them to disk.

    Returns:
        {
            "idealo": <product_count>,
            "pricerunner": <product_count>,
            "kelkoo": <product_count>,
            "generated_at": "<ISO timestamp>",
        }
    """
    _ensure_data_dir()

    logger.info("refresh_all_feeds: fetching Shopify products …")
    products = await fetch_shopify_products()
    count = len(products)

    # Generate all three feeds concurrently (products already in memory)
    idealo_csv, pricerunner_xml, kelkoo_csv = await asyncio.gather(
        generate_idealo_csv(products),
        generate_pricerunner_xml(products),
        generate_kelkoo_csv(products),
    )

    FEED_FILES["idealo"].write_text(idealo_csv, encoding="utf-8")
    FEED_FILES["pricerunner"].write_text(pricerunner_xml, encoding="utf-8")
    FEED_FILES["kelkoo"].write_text(kelkoo_csv, encoding="utf-8")

    generated_at = datetime.now(timezone.utc).isoformat()

    logger.info(
        "refresh_all_feeds done — idealo=%d pricerunner=%d kelkoo=%d at %s",
        count, count, count, generated_at,
    )

    return {
        "idealo": count,
        "pricerunner": count,
        "kelkoo": count,
        "generated_at": generated_at,
    }


# ─── Feed stats ───────────────────────────────────────────────────────────────

async def get_feed_stats() -> dict:
    """
    Return file sizes, estimated product counts, and last_updated for each feed.

    Product count is estimated from line count (CSV) or <product> tags (XML).
    """
    stats: dict = {}

    for feed_name, path in FEED_FILES.items():
        if not path.exists():
            stats[feed_name] = {
                "exists": False,
                "file_size_bytes": 0,
                "product_count": 0,
                "last_updated": None,
                "cache_valid": False,
            }
            continue

        file_size = path.stat().st_size
        mtime = path.stat().st_mtime
        last_updated = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        cache_valid = _is_cache_valid(path)

        # Estimate product count
        content = path.read_text(encoding="utf-8", errors="replace")
        if feed_name == "pricerunner":
            product_count = content.count("<product>")
        else:
            # CSV: count data rows (total lines minus header line)
            lines = [l for l in content.splitlines() if l.strip()]
            product_count = max(0, len(lines) - 1)

        stats[feed_name] = {
            "exists": True,
            "file_size_bytes": file_size,
            "product_count": product_count,
            "last_updated": last_updated,
            "cache_valid": cache_valid,
        }

    return stats


# ─── Cached feed accessors (used by dashboard routes) ────────────────────────

async def get_or_refresh_idealo() -> str:
    """Return cached Idealo CSV or regenerate if stale."""
    path = FEED_FILES["idealo"]
    if _is_cache_valid(path):
        return path.read_text(encoding="utf-8")
    _ensure_data_dir()
    csv_str = await generate_idealo_csv()
    path.write_text(csv_str, encoding="utf-8")
    return csv_str


async def get_or_refresh_pricerunner() -> str:
    """Return cached PriceRunner XML or regenerate if stale."""
    path = FEED_FILES["pricerunner"]
    if _is_cache_valid(path):
        return path.read_text(encoding="utf-8")
    _ensure_data_dir()
    xml_str = await generate_pricerunner_xml()
    path.write_text(xml_str, encoding="utf-8")
    return xml_str


async def get_or_refresh_kelkoo() -> str:
    """Return cached Kelkoo CSV or regenerate if stale."""
    path = FEED_FILES["kelkoo"]
    if _is_cache_valid(path):
        return path.read_text(encoding="utf-8")
    _ensure_data_dir()
    csv_str = await generate_kelkoo_csv()
    path.write_text(csv_str, encoding="utf-8")
    return csv_str


# ─── CLI entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _main() -> None:
        cmd = sys.argv[1] if len(sys.argv) > 1 else "refresh"
        if cmd == "refresh":
            result = await refresh_all_feeds()
            print("Feeds generated:", result)
        elif cmd == "stats":
            stats = await get_feed_stats()
            import json
            print(json.dumps(stats, indent=2))
        else:
            print(f"Unknown command: {cmd}. Use 'refresh' or 'stats'.")

    asyncio.run(_main())
