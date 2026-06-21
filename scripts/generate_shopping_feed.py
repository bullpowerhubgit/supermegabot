#!/usr/bin/env python3
"""
Google Shopping Feed Generator — RSS/XML feed für Google Merchant Center.
Generiert products.xml aus allen aktiven Shopify-Produkten.
Upload in GMC: Merchant Center → Feeds → Neuen Feed erstellen → URL oder Datei.
"""
import asyncio, os, json, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import aiohttp

DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
VER     = os.getenv("SHOPIFY_API_VERSION", "2024-10")
STORE_URL = f"https://ineedit.com.co"
OUT_FILE  = Path(__file__).parent.parent / "data" / "google_shopping_feed.xml"
BATCH     = 250
DELAY     = 0.6

GOOGLE_CATEGORIES = {
    "beamer": "Electronics > Video > Projectors",
    "drucker": "Electronics > Print, Copy, Scan & Fax > Printers",
    "kopfhörer": "Electronics > Audio > Headphones",
    "lautsprecher": "Electronics > Audio > Speakers",
    "kamera": "Cameras & Optics > Cameras",
    "uhr": "Apparel & Accessories > Jewelry > Watches",
    "watch": "Apparel & Accessories > Jewelry > Watches",
    "handy": "Electronics > Communications > Telephony > Mobile Phones",
    "solar": "Hardware > Electrical Equipment & Supplies > Power Supplies > Solar Energy",
    "fitness": "Sporting Goods > Exercise & Fitness",
    "küche": "Kitchen & Dining > Kitchen Appliances",
    "garten": "Home & Garden > Lawn & Garden",
    "laptop": "Electronics > Computers > Laptops",
    "tablet": "Electronics > Computers > Tablets",
    "spielzeug": "Toys & Games",
    "baby": "Baby & Toddler > Baby Transport & Safety",
    "fahrrad": "Sporting Goods > Outdoor Recreation > Cycling",
}


def _guess_category(title: str) -> str:
    t = title.lower()
    for kw, cat in GOOGLE_CATEGORIES.items():
        if kw in t:
            return cat
    return "Home & Garden"


async def fetch_all_products() -> list:
    products = []
    url = f"https://{DOMAIN}/admin/api/{VER}/products.json?limit={BATCH}&status=active&fields=id,title,body_html,images,variants,vendor,product_type,handle,tags"
    headers = {"X-Shopify-Access-Token": TOKEN}
    page = 1
    async with aiohttp.ClientSession() as s:
        while url:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as r:
                data = await r.json(content_type=None)
                batch = data.get("products", [])
                products.extend(batch)
                print(f"  Seite {page}: {len(batch)} Produkte (gesamt: {len(products)})")
                link = r.headers.get("Link", "")
                url = None
                for part in link.split(","):
                    if 'rel="next"' in part:
                        url = part.strip().split(";")[0].strip().strip("<>")
                page += 1
            await asyncio.sleep(DELAY)
    return products


def build_feed(products: list) -> ET.Element:
    rss = ET.Element("rss", {
        "version": "2.0",
        "xmlns:g": "http://base.google.com/ns/1.0",
    })
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "ineedit.com.co — KI Shop"
    ET.SubElement(channel, "link").text = STORE_URL
    ET.SubElement(channel, "description").text = "Smarte Produkte günstig kaufen"

    skipped = 0
    for p in products:
        variants = p.get("variants", [])
        if not variants:
            skipped += 1
            continue
        images = p.get("images", [])
        if not images:
            skipped += 1
            continue

        variant = variants[0]
        price = variant.get("price", "0")
        img_url = images[0].get("src", "")
        if not img_url:
            skipped += 1
            continue

        title = p.get("title", "").strip()
        handle = p.get("handle", "")
        body = p.get("body_html", "") or ""
        # Strip HTML tags for description
        import re
        description = re.sub(r"<[^>]+>", "", body).strip()
        if not description:
            description = title
        if len(description) > 5000:
            description = description[:4997] + "..."

        pid = str(p.get("id", ""))
        sku = variant.get("sku") or f"SMB-{pid[-8:]}"
        category = _guess_category(title)

        item = ET.SubElement(channel, "item")
        g = "http://base.google.com/ns/1.0"
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = f"{STORE_URL}/products/{handle}"
        ET.SubElement(item, "description").text = description[:800]
        ET.SubElement(item, f"{{{g}}}id").text = sku
        ET.SubElement(item, f"{{{g}}}condition").text = "new"
        ET.SubElement(item, f"{{{g}}}price").text = f"{price} EUR"
        ET.SubElement(item, f"{{{g}}}availability").text = "in stock"
        ET.SubElement(item, f"{{{g}}}image_link").text = img_url
        ET.SubElement(item, f"{{{g}}}brand").text = p.get("vendor") or "ineedit"
        ET.SubElement(item, f"{{{g}}}identifier_exists").text = "no"
        ET.SubElement(item, f"{{{g}}}google_product_category").text = category
        if p.get("product_type"):
            ET.SubElement(item, f"{{{g}}}product_type").text = p["product_type"]

        # Additional images
        for img in images[1:4]:
            src = img.get("src", "")
            if src:
                ET.SubElement(item, f"{{{g}}}additional_image_link").text = src

    print(f"  Übersprungen (kein Bild/Variante): {skipped}")
    return rss


async def main():
    if not DOMAIN or not TOKEN:
        print("ERROR: Shopify-Credentials fehlen!")
        return

    print(f"Google Shopping Feed Generator")
    print(f"Store: {DOMAIN}")
    print(f"Output: {OUT_FILE}")
    print()
    print("Lade Produkte...")
    products = await fetch_all_products()
    print(f"\n{len(products)} Produkte geladen. Erstelle Feed...")

    tree = build_feed(products)
    OUT_FILE.parent.mkdir(exist_ok=True)

    # Pretty print
    ET.indent(tree)
    xml_str = ET.tostring(tree, encoding="unicode", xml_declaration=False)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_str)

    size_kb = OUT_FILE.stat().st_size // 1024
    print(f"\n✅ Feed erstellt: {OUT_FILE}")
    print(f"   Größe: {size_kb} KB")
    print()
    print("NÄCHSTE SCHRITTE:")
    print("1. Öffne: https://merchants.google.com (Merchant ID: 5813214419)")
    print("2. Produkte → Feeds → + Neuen Feed erstellen")
    print("3. Sprache: Deutsch, Land: Deutschland")
    print("4. Datei hochladen: google_shopping_feed.xml")
    print("5. Produkte erscheinen in 1-3 Tagen bei Google Shopping")


if __name__ == "__main__":
    asyncio.run(main())
