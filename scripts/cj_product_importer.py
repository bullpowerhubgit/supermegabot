#!/usr/bin/env python3
"""
CJ Dropshipping → Shopify Importer
Importiert echte Produkte aus dem CJ Dropshipping Katalog direkt in Shopify.

Setup:
  1. CJ API Token holen: https://developers.cjdropshipping.com/
     - Login mit aiitecbuuss@gmail.com
     - My Account → API Token → Generate Token
  2. Token in .env eintragen: CJ_ACCESS_TOKEN=xxx
  3. Dieses Script ausführen: python3 scripts/cj_product_importer.py

Kategorien: Solar, Smart Home, Fitness, Elektronik, Gadgets
"""
import os, json, asyncio, aiohttp, logging, time, re
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

CJ_TOKEN   = os.getenv("CJ_ACCESS_TOKEN", "")
CJ_EMAIL   = os.getenv("CJ_EMAIL", "aiitecbuuss@gmail.com")
CJ_PASSWORD = os.getenv("CJ_PASSWORD", "")

SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_API_VER = os.getenv("SHOPIFY_API_VERSION", "2024-10")
SHOPIFY_GQL_URL = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_API_VER}/graphql.json"
SHOPIFY_HEADERS = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

CJ_BASE = "https://developers.cjdropshipping.com/api2.0/v1"

# Kategorien die wir importieren wollen
IMPORT_CATEGORIES = [
    "Solar & Energy",
    "Smart Home",
    "Electronics",
    "Fitness & Sports",
    "Health & Beauty",
    "Outdoor & Camping",
    "Kitchen Gadgets",
    "Car Accessories",
    "Phone Accessories",
    "LED Lighting",
]

# Preisaufschlag: Einkaufspreis × Multiplikator
PRICE_MULTIPLIER = 2.8  # ~180% Aufschlag

# Preiskorrektur nach Kategorie
CATEGORY_PRICE_OVERRIDE = {
    "solar": 149.99,
    "smart home hub": 89.99,
    "gaming": 79.99,
}

BLACKLIST_WORDS = ["sexy", "adult", "porn", "xxx", "weapon", "gun", "knife", "drug"]

async def get_cj_token(session: aiohttp.ClientSession) -> str:
    """CJ API Token über Email/Passwort holen"""
    if CJ_TOKEN:
        return CJ_TOKEN
    if not CJ_PASSWORD:
        raise ValueError("CJ_PASSWORD oder CJ_ACCESS_TOKEN muss in .env gesetzt sein!")
    r = await session.post(
        f"{CJ_BASE}/authentication/getAccessToken",
        json={"email": CJ_EMAIL, "password": CJ_PASSWORD}
    )
    data = await r.json()
    if data.get("result"):
        token = data["data"]["accessToken"]
        log.info(f"CJ Token erhalten: {token[:20]}...")
        return token
    raise ValueError(f"CJ Login fehlgeschlagen: {data.get('message', data)}")

async def get_cj_products(session: aiohttp.ClientSession, token: str,
                           category_id: str = None, page: int = 1, page_size: int = 100) -> dict:
    """Produkte aus CJ Katalog holen"""
    params = {
        "pageNum": page,
        "pageSize": page_size,
    }
    if category_id:
        params["categoryId"] = category_id

    r = await session.get(
        f"{CJ_BASE}/product/list",
        headers={"CJ-Access-Token": token},
        params=params
    )
    return await r.json()

async def get_cj_categories(session: aiohttp.ClientSession, token: str) -> list:
    """Alle CJ Kategorien abrufen"""
    r = await session.get(
        f"{CJ_BASE}/product/getCategory",
        headers={"CJ-Access-Token": token}
    )
    data = await r.json()
    return data.get("data", [])

async def search_cj_products(session: aiohttp.ClientSession, token: str,
                              keyword: str, page: int = 1) -> dict:
    """CJ Produkte nach Keyword suchen"""
    r = await session.get(
        f"{CJ_BASE}/product/list",
        headers={"CJ-Access-Token": token},
        params={
            "productNameEn": keyword,
            "pageNum": page,
            "pageSize": 50,
            "sort": "SUPPLIER_RATING",  # Nach Bewertung sortieren
        }
    )
    return await r.json()

def calculate_price(cost: float, shipping: float = 0) -> float:
    """Verkaufspreis aus Einkaufspreis berechnen"""
    total_cost = cost + shipping
    price = total_cost * PRICE_MULTIPLIER
    # Auf .99 runden
    rounded = round(price * 2) / 2  # Auf 0.5 runden
    if rounded < 19.99:
        return 19.99
    # Schöne Preise: 24.99, 29.99, 34.99, etc.
    if rounded % 1 == 0:
        return rounded - 0.01
    return round(rounded - 0.01, 2) if rounded % 1 == 0.5 else rounded

def clean_description(desc: str) -> str:
    """Beschreibung bereinigen und auf Deutsch übersetzen (Platzhalter)"""
    if not desc:
        return ""
    # Entferne HTML-Tags außer grundlegende
    clean = re.sub(r'<(?!/?(?:p|ul|li|strong|em|h[1-6]|br))[^>]+>', '', desc)
    return clean[:2000]

def is_valid_product(product: dict) -> bool:
    """Prüft ob Produkt für den Shop geeignet ist"""
    title = (product.get("productNameEn") or "").lower()
    if any(bw in title for bw in BLACKLIST_WORDS):
        return False
    # Muss Bild haben
    if not product.get("productImage"):
        return False
    # Muss Preis haben
    if not product.get("sellPrice") and not product.get("variants"):
        return False
    return True

async def create_shopify_product(session: aiohttp.ClientSession, cj_product: dict) -> bool:
    """Produkt in Shopify erstellen"""
    title = cj_product.get("productNameEn", "")
    if not title:
        return False

    cost = float(cj_product.get("sellPrice") or 0)
    price = calculate_price(cost)

    images = []
    main_img = cj_product.get("productImage")
    if main_img:
        images.append({"src": main_img, "altText": title})

    # Varianten-Bilder
    for variant in cj_product.get("variants", []):
        img = variant.get("variantImage")
        if img and img not in [i["src"] for i in images]:
            images.append({"src": img, "altText": f"{title} - {variant.get('variantName','')}"})

    desc = clean_description(cj_product.get("description", ""))
    if not desc:
        desc = f"<p>{title}</p>"

    mutation = """
    mutation createProduct($input: ProductInput!, $media: [CreateMediaInput!]) {
      productCreate(input: $input, media: $media) {
        product {
          id
          title
          status
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "input": {
            "title": title,
            "descriptionHtml": desc,
            "vendor": "iNeedit",
            "status": "ACTIVE",
            "tags": ["dropship", "cj-dropshipping"],
            "variants": [{"price": str(price), "inventoryQuantities": {"locationId": "gid://shopify/Location/120414110083", "availableQuantity": 99}}],
        },
        "media": [{"originalSource": img["src"], "mediaContentType": "IMAGE"} for img in images[:5]],
    }

    async with session.post(
        SHOPIFY_GQL_URL,
        headers=SHOPIFY_HEADERS,
        json={"query": mutation, "variables": variables}
    ) as r:
        data = await r.json()
        errors = data.get("data", {}).get("productCreate", {}).get("userErrors", [])
        if errors:
            log.warning(f"Shopify Fehler für '{title}': {errors}")
            return False
        product_id = data.get("data", {}).get("productCreate", {}).get("product", {}).get("id")
        if product_id:
            log.info(f"✅ {title} → €{price}")
            return True
        return False

SEARCH_KEYWORDS = [
    "solar panel portable", "solar charger", "solar power bank",
    "smart home security", "wifi smart plug", "led strip wifi",
    "bluetooth speaker waterproof", "wireless earbuds",
    "fitness tracker smartwatch", "massage gun",
    "portable projector mini", "ring light selfie",
    "car phone holder wireless", "car dash cam",
    "kitchen gadget silicone", "air fryer accessories",
    "camping lantern led", "outdoor survival kit",
    "posture corrector", "resistance bands set",
    "magnetic charging cable", "usb hub type c",
    "smart water bottle", "infrared thermometer",
    "electric wine opener", "coffee frother",
    "robot vacuum accessories", "air purifier",
    "security camera wireless", "video doorbell",
    "smart lock fingerprint", "motion sensor light",
]

async def main():
    imported = 0
    errors = 0
    target = 500  # Pro Lauf 500 neue Produkte

    async with aiohttp.ClientSession() as session:
        log.info("CJ Dropshipping Login...")
        try:
            token = await get_cj_token(session)
        except Exception as e:
            log.error(f"Login fehlgeschlagen: {e}")
            log.error("\nBITTE in .env eintragen:")
            log.error("CJ_ACCESS_TOKEN=dein-token-von-developers.cjdropshipping.com")
            log.error("ODER:")
            log.error("CJ_PASSWORD=dein-passwort-für-aiitecbuuss@gmail.com")
            return

        log.info(f"Starte Import von {target} Produkten...")

        for keyword in SEARCH_KEYWORDS:
            if imported >= target:
                break

            log.info(f"Suche: '{keyword}'")
            for page in range(1, 4):
                if imported >= target:
                    break

                result = await search_cj_products(session, token, keyword, page)
                products = result.get("data", {}).get("list", [])

                if not products:
                    break

                for product in products:
                    if imported >= target:
                        break
                    if not is_valid_product(product):
                        continue

                    success = await create_shopify_product(session, product)
                    if success:
                        imported += 1
                    else:
                        errors += 1

                    await asyncio.sleep(0.3)  # Rate limit

                log.info(f"  Seite {page}: {imported}/{target} importiert")

    log.info(f"\n=== FERTIG ===")
    log.info(f"✅ Importiert: {imported}")
    log.info(f"❌ Fehler: {errors}")

if __name__ == "__main__":
    asyncio.run(main())
