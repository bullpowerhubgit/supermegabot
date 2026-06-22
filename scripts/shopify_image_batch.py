#!/usr/bin/env python3
"""
Shopify Product Image Batch Uploader
Adds royalty-free Unsplash images to products missing images.
Uses keyword matching against product titles to pick relevant images.
"""
import asyncio, os, logging, sys, time
from pathlib import Path

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import aiohttp

log = logging.getLogger("ImageBatch")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
VER     = os.getenv("SHOPIFY_API_VERSION", "2024-10")
BASE    = f"https://{DOMAIN}/admin/api/{VER}"
DELAY   = 0.7  # stay under Shopify Basic 2 req/sec limit

# Category keyword → royalty-free Unsplash image URLs (multiple per category for variety)
CATEGORY_IMAGES = {
    # Smart Home / IoT
    "smarthome|smart home|steckdose|wlan|wifi|iot|schalter|sensor|hub|zigbee|alexa|home assistant": [
        "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1585771724684-38269d6639fd?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1613274554329-70f997dae503?w=800&auto=format&fit=crop",
    ],
    # Fitness / Sport
    "fitness|sport|yoga|pilates|hantel|widerstand|training|workout|gym": [
        "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1583454110551-21f2fa2afe61?w=800&auto=format&fit=crop",
    ],
    # Garden / Garten
    "garten|garden|pflanz|balkon|kräuter|saatgut|bewässer|outdoor gemüse|botanisch": [
        "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1585320806297-9794b3e4aaae?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1523348837708-15d4a09cfac2?w=800&auto=format&fit=crop",
    ],
    # Outdoor / Camping
    "outdoor|camping|trekking|wandern|zelt|rucksack|abenteuer|survival": [
        "https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1571863533956-01c88e79957e?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1533240332313-0db49b459ad6?w=800&auto=format&fit=crop",
    ],
    # Electronics / Tech
    "beamer|projektor|laptop|computer|monitor|drucker|3d|elektronik|gadget|tech": [
        "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1488590528505-98d2b5aba04b?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=800&auto=format&fit=crop",
    ],
    # Headphones / Audio
    "kopfhörer|ohrhörer|lautsprecher|audio|musik|sound|bluetooth|headphone": [
        "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1583394838336-acd977736f90?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1484704849700-f032a568e944?w=800&auto=format&fit=crop",
    ],
    # Smartwatch / Fitness Tracker
    "smartwatch|fitnessuhr|uhr|tracker|wearable|watch": [
        "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1546868871-7041f2a55e12?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?w=800&auto=format&fit=crop",
    ],
    # Kitchen / Küche
    "küche|kaffee|blender|mixer|kochgeschirr|pfanne|kochen|küchen": [
        "https://images.unsplash.com/photo-1556910103-1c02745aae4d?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1484659832748-c28e2fcb38a5?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1585515320310-259814833e62?w=800&auto=format&fit=crop",
    ],
    # LED / Lighting / Decor
    "led|lampe|beleuchtung|licht|sunset|projektor lamp|nachtlicht|stehlampe": [
        "https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1558618047-3e29e8ae2168?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1565814636199-ae8133055c1c?w=800&auto=format&fit=crop",
    ],
    # Auto / Car
    "auto|kfz|fahrzeug|car|pkw|fahren|reise gadget": [
        "https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1502877338535-766e1452684a?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1583121274602-3e2820c69888?w=800&auto=format&fit=crop",
    ],
    # Solar / Energy
    "solar|energie|strom|photovoltaik|balkonkraftwerk|nachhalt": [
        "https://images.unsplash.com/photo-1509391366360-2e959784a276?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1466611653911-95081537e5b7?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1548430395-ec39eaf2aa1a?w=800&auto=format&fit=crop",
    ],
    # Gaming
    "gaming|spiel|gamer|controller|game": [
        "https://images.unsplash.com/photo-1538481199705-c710c4e965fc?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=800&auto=format&fit=crop",
    ],
    # Organizer / Storage
    "organizer|aufbewahrung|ordnung|box|behälter|schreibtisch": [
        "https://images.unsplash.com/photo-1558618047-f91a7f8ea1e9?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1556909190-eccf4a8bf97a?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1505409628601-edc9af17fda6?w=800&auto=format&fit=crop",
    ],
    # AI / Digital / App
    "ki|ai|digital|app|software|lern|schreib|assistent|kurs|e-book": [
        "https://images.unsplash.com/photo-1677442135703-1787eea5ce01?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?w=800&auto=format&fit=crop",
    ],
    # Personalisiert / Jewelry
    "personalis|schmuck|gravur|individu|maßgefertigt|geschenk": [
        "https://images.unsplash.com/photo-1515562141207-7a88fb7ce338?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1551892374-ecf8754cf8b0?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1599707367072-cd6ada2bc375?w=800&auto=format&fit=crop",
    ],
    # Travel / Reise
    "reise|travel|koffer|gepäck|urlaub|backpack": [
        "https://images.unsplash.com/photo-1500835556837-99ac94a94552?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1488085061387-422e29b40080?w=800&auto=format&fit=crop",
    ],
    # Security / Camera
    "kamera|überwachung|security|türklingel|sicherheit|alarm|bewegung": [
        "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1557597774-9d273605dfa9?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1555680202-c86f0e12f086?w=800&auto=format&fit=crop",
    ],
    # Massage / Wellbeing
    "massage|nacken|rücken|entspann|wellness|therapie|körper": [
        "https://images.unsplash.com/photo-1544161515-4ab6ce6db874?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1600334129128-685c5582fd35?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1540555700478-4be289fbecef?w=800&auto=format&fit=crop",
    ],
    # Trinkflasche / Bottles
    "trinkflasche|flasche|bottle|thermos|becher|wasser": [
        "https://images.unsplash.com/photo-1602143407151-7111542de6e8?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1523362628745-0c100150b504?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1575377427642-087cf684ad61?w=800&auto=format&fit=crop",
    ],
    # Baby / Kids
    "baby|kind|kinder|spielzeug|schule|lernen|bildung": [
        "https://images.unsplash.com/photo-1537591075571-59d42b1432a3?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1596464716127-f2a82984de30?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1581091226033-d5c48150dbaa?w=800&auto=format&fit=crop",
    ],
}

# Fallback generic product image
FALLBACK_IMAGE = "https://images.unsplash.com/photo-1491553895911-0055eca6402d?w=800&auto=format&fit=crop"

import random
import re as _re


def pick_image(title: str, used: set = None) -> str:
    """Pick the most relevant image URL for a product title."""
    title_low = title.lower()
    for pattern, urls in CATEGORY_IMAGES.items():
        keywords = pattern.split("|")
        if any(kw in title_low for kw in keywords):
            # Avoid reusing same URLs too often
            available = [u for u in urls if u not in (used or set())]
            if available:
                return random.choice(available)
            return random.choice(urls)
    return FALLBACK_IMAGE


async def get_all_products_without_images(session: aiohttp.ClientSession) -> list:
    """Fetch all active products that have no images."""
    products = []
    last_id = 0
    while True:
        params = {
            "limit": 250,
            "since_id": last_id,
            "status": "active",
            "fields": "id,title,images",
        }
        async with session.get(f"{BASE}/products.json", params=params,
                               headers={"X-Shopify-Access-Token": TOKEN}) as r:
            batch = (await r.json()).get("products", [])
        if not batch:
            break
        no_img = [p for p in batch if not p.get("images")]
        products.extend(no_img)
        last_id = batch[-1]["id"]
        if len(batch) < 250:
            break
        await asyncio.sleep(DELAY)
    return products


async def add_image(session: aiohttp.ClientSession, product_id: int, title: str, img_url: str) -> bool:
    """Add an image to a Shopify product."""
    payload = {"image": {"src": img_url, "alt": title[:255]}}
    async with session.post(
        f"{BASE}/products/{product_id}/images.json",
        headers={"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"},
        json=payload,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as r:
        if r.status in (200, 201):
            return True
        body = await r.text()
        log.warning("Image upload failed for %d: %s — %s", product_id, r.status, body[:100])
        return False


async def main():
    limit = None
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])
        elif arg == "--limit" and sys.argv.index(arg) + 1 < len(sys.argv):
            limit = int(sys.argv[sys.argv.index(arg) + 1])

    log.info("Shopify Image Batch Uploader gestartet")
    log.info("Store: %s", DOMAIN)

    async with aiohttp.ClientSession() as session:
        log.info("Lade Produkte ohne Bilder...")
        products = await get_all_products_without_images(session)
        log.info("%d Produkte ohne Bild gefunden", len(products))

        if limit:
            products = products[:limit]
            log.info("Begrenze auf %d Produkte", limit)

        if not products:
            log.info("Alle Produkte haben Bilder. Fertig!")
            return

        done = 0
        errors = 0
        used_urls: set = set()

        for i, p in enumerate(products, 1):
            title = p.get("title", "Produkt")
            pid = p["id"]
            img_url = pick_image(title, used_urls)

            ok = await add_image(session, pid, title, img_url)
            if ok:
                done += 1
                used_urls.add(img_url)
                if len(used_urls) > 50:
                    used_urls.clear()  # reset to allow reuse
                if i % 25 == 0:
                    log.info("Fortschritt: %d/%d ✅ %d Fehler", i, len(products), errors)
            else:
                errors += 1
                if i % 25 == 0:
                    log.info("Fortschritt: %d/%d ✅ %d Fehler", i, len(products), errors)

            await asyncio.sleep(DELAY)

        log.info("✅ Fertig: %d/%d Bilder hinzugefügt, %d Fehler", done, len(products), errors)


if __name__ == "__main__":
    asyncio.run(main())
