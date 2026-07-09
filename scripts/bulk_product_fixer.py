#!/usr/bin/env python3
"""
Bulk Product Fixer — ineedit.com.co
- Archiviert Fake/Digital-Produkte (KI-Apps, Nonsense-Namen, digitale Software)
- Setzt echte Marktpreise für physische Produkte
- Aktiviert alle echten Produkte
- Ändert Vendor von "Auto-Import" zu "iNeedit"
"""
import os, json, asyncio, aiohttp, logging, time
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
TOKEN  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
API_VER = os.getenv("SHOPIFY_API_VERSION", "2024-10")
GQL_URL = f"https://{DOMAIN}/admin/api/{API_VER}/graphql.json"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

# Schlüsselwörter die auf FAKE/DIGITAL hinweisen → archivieren
FAKE_KEYWORDS = [
    "ki-gestützt", "ki-gestütz", "ki-tutor", "ki-lernstift", "lernstift",
    "autopilot", "auto-pilot", "autopilotshoppe", "nachhilfe-app", "matheapp",
    "matheassistent", "schreibassistent für deutsche", "aufsatzkorrektur",
    "übungsaufgaben-generator", "lernbegleiter", "content-ersteller",
    "text- und bildgenerator", "grafik- und design-assistent", "vokabeltrainer",
    "quiz-generator", "lernplattform", "interaktives übungsbuch",
    "digitale produkte", "online-kursinhalt", "digitaler", "digitale",
    "aurasynch smartarmband", "kinetikflow", "chronosense", "adaptigrip",
    "aquaflow precision spritz", "lumigrow sensor-stick", "ecoguard sonic shield",
    "autopilotshoppe", "mathematik-lernen mit autopilot",
    "automatisierter content", "intelligenter schreibassistent für visuelle",
    "amazon bestseller massagepistole modell x",  # fake amazon produkt
    "mensjournal", "allhometool", "energysage",  # scraped article names, not products
    "apple watch ultra outdoor pro",  # doesn't exist
    "smart hydroponic garden kit xl",  # vague
    "autopilot-garten",
    "lumitorch stirnlampe 'glowpath'", "apexgear multitool 'trailmaster'",
    "consumer betterment", "hybrid resistance home gym",
    "aurasync", "kineticflow", "chronosense", "adaptigrip tracker sleeve",
]

# Preistabelle nach Kategorie/Keyword
PRICE_MAP = [
    # Electronics / Smart Home (KEIN Billigware)
    (["massagepistole", "massage gun", "massager"],                     149.99),
    (["garmin", "forerunner", "vivoactive"],                            229.99),
    (["polar grit", "suunto", "coros apex", "coros pace"],             249.99),
    (["therabody", "theragun", "hyperice", "hypervolt"],                179.99),
    (["apple watch"],                                                    399.99),
    (["4k beamer", "mini-beamer", "projektor", "beamer"],               139.99),
    (["balkonkraftwerk", "zendure", "solar speicher"],                  349.99),
    (["rasenmähroboter", "mähroboter"],                                 299.99),
    (["smart thermostat", "intelligenter thermostat"],                    89.99),
    (["video-türklingel", "türklingel", "doorbell"],                     79.99),
    (["überwachungskamera", "kamera", "ip-kamera", "webcam"],            69.99),
    (["fitness tracker", "smartwatch", "smart watch", "fitness band"],   79.99),
    (["smart steckdose", "steckdosenleiste", "smart plug", "steckdose"],  44.99),
    (["kabellose ladestation", "ladestation", "powerbank", "ladegerät"],  54.99),
    (["magsafe"],                                                         59.99),
    (["bluetooth lautsprecher", "speaker", "lautsprecher"],              89.99),
    (["ohrhörer", "earbuds", "kopfhörer", "earphone"],                   69.99),
    (["led strip", "lichtband", "led-streifen", "lumiflex", "chromasync"], 39.99),
    (["led lampe", "glühbirne", "birne", "led-lampe"],                   34.99),
    (["aroma-diffusor", "luftbefeuchter", "diffusor"],                   44.99),
    (["fleischthermometer", "thermometer", "thermometer"],               34.99),
    (["milchaufschäumer", "kaffeemaschine", "milch"],                    44.99),
    (["seifenspender", "soap", "spender"],                               34.99),
    (["mixer", "smoothie", "mixer"],                                     49.99),
    (["laptop ständer", "laptopständer", "ständer"],                     49.99),
    (["widerstandsband", "fitness band", "trainingsband", "theraband", "spri",
       "fitsimp", "wod", "proflex", "flexifit", "powerband", "aeroflow"],  34.99),
    (["yoga matte", "yogamatte", "fitnessmatte"],                        44.99),
    (["hanteln", "mini-hanteln", "gewicht"],                             59.99),
    (["klimmzugstange", "klimmzug"],                                     49.99),
    (["push-up", "liegestütze", "stepper"],                              39.99),
    (["sprungseil"],                                                      29.99),
    (["ergonomic", "ergonomisch", "büro ergon"],                         59.99),
    # Garten
    (["bewässerung", "bewässerungsanlage", "bewässerungsset",
       "bewässerungssystem", "gartensprenger", "sprenger"],              59.99),
    (["gartengeräte", "gartenschaufel", "gartenschere", "gartenset"],    44.99),
    (["gartenhandschuhe", "handschuhe garten"],                          24.99),
    (["anzuchttöpfe", "saatgut", "samen"],                               19.99),
    (["hydroponik", "hydroponic", "pflanzensensor", "smart garden"],     89.99),
    (["vogelträn", "vogel"],                                             24.99),
    (["gartenetikett"],                                                  12.99),
    # Outdoor / Reise
    (["camping", "outdoor set", "trekking set"],                         89.99),
    (["rucksack", "backpack"],                                            69.99),
    (["wasserfilter", "filter"],                                          49.99),
    (["kochset", "outdoor-kochset"],                                     69.99),
    (["isomatte", "schlafsack"],                                         49.99),
    (["stirnlampe", "taschenlampe"],                                     29.99),
    (["multitool"],                                                       44.99),
    (["reise", "travel", "reiseset"],                                    59.99),
    (["trinkflasche", "thermoskanne"],                                   34.99),
    (["picknickkorb", "picknick"],                                        54.99),
    (["lunchbox"],                                                        29.99),
    # Gaming / Auto
    (["gaming"],                                                         79.99),
    (["auto-zubehör", "auto zubehör", "fahrzeug"],                       59.99),
    # Organsizer / Haushalt
    (["organizer", "aufbewahrung"],                                      39.99),
    (["küchen-gadget", "küchenhelfer"],                                  44.99),
    # Sensoren / Smart Home
    (["sensor", "rauchmelder", "bewegungsmelder", "fensterkontakt",
       "türkontakt", "tür & fenster", "wasserdetektor"],                 34.99),
    (["smart home hub", "zigbee", "zwave"],                              69.99),
    (["co2-sensor", "luftqualität"],                                      49.99),
    # Default
    (["default"],                                                         49.99),
]

def get_price(title: str) -> float:
    title_lower = title.lower()
    for keywords, price in PRICE_MAP:
        if keywords == ["default"]:
            return price
        for kw in keywords:
            if kw in title_lower:
                return price
    return 49.99

def is_fake(title: str) -> bool:
    title_lower = title.lower()
    for kw in FAKE_KEYWORDS:
        if kw in title_lower:
            return True
    return False

async def gql(session: aiohttp.ClientSession, query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    async with session.post(GQL_URL, headers=HEADERS, json=payload) as r:
        return await r.json()

GET_PRODUCTS = """
query getProducts($cursor: String) {
  products(first: 50, after: $cursor, query: "status:draft") {
    edges {
      node {
        id
        title
        vendor
        variants(first: 1) {
          edges {
            node {
              id
              price
            }
          }
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""

ARCHIVE_PRODUCT = """
mutation archiveProduct($id: ID!) {
  productUpdate(input: { id: $id, status: ARCHIVED }) {
    product { id status }
    userErrors { field message }
  }
}
"""

ACTIVATE_PRODUCT = """
mutation activateProduct($id: ID!, $vendor: String!, $desc: String!) {
  productUpdate(input: { id: $id, status: ACTIVE, vendor: $vendor, descriptionHtml: $desc }) {
    product { id status }
    userErrors { field message }
  }
}
"""

UPDATE_PRICE = """
mutation updatePrice($productId: ID!, $variantId: ID!, $price: String!) {
  productVariantsBulkUpdate(productId: $productId, variants: [{ id: $variantId, price: $price }]) {
    productVariants { price }
    userErrors { field message }
  }
}
"""

async def process_batch(session: aiohttp.ClientSession, products: list, stats: dict):
    for p in products:
        pid = p["id"]
        title = p["title"]
        variant = p["variants"]["edges"][0]["node"] if p["variants"]["edges"] else None

        if is_fake(title):
            log.info(f"ARCHIVIERE (Fake): {title}")
            res = await gql(session, ARCHIVE_PRODUCT, {"id": pid})
            if res.get("data", {}).get("productUpdate", {}).get("userErrors"):
                log.warning(f"  Fehler: {res['data']['productUpdate']['userErrors']}")
            stats["archived"] += 1
        else:
            price = get_price(title)
            log.info(f"AKTIVIERE: {title} → €{price}")
            # Activate + update description
            res = await gql(session, ACTIVATE_PRODUCT, {
                "id": pid,
                "vendor": "iNeedit",
                "desc": f"<p>{title}</p>"
            })
            err = res.get("data", {}).get("productUpdate", {}).get("userErrors", [])
            if err:
                log.warning(f"  Aktivierung Fehler: {err}")
            # Update price
            if variant:
                vid = variant["id"]
                pres = await gql(session, UPDATE_PRICE, {
                    "productId": pid,
                    "variantId": vid,
                    "price": str(price)
                })
                perr = pres.get("data", {}).get("productVariantsBulkUpdate", {}).get("userErrors", [])
                if perr:
                    log.warning(f"  Preis Fehler: {perr}")
            stats["activated"] += 1

        await asyncio.sleep(0.1)  # Rate limit: 10 req/s

async def main():
    stats = {"activated": 0, "archived": 0, "total": 0}
    cursor = None
    page = 0

    async with aiohttp.ClientSession() as session:
        while True:
            page += 1
            log.info(f"=== Seite {page} | Aktiviert: {stats['activated']} | Archiviert: {stats['archived']} ===")

            result = await gql(session, GET_PRODUCTS, {"cursor": cursor})
            data = result.get("data", {}).get("products", {})
            edges = data.get("edges", [])

            if not edges:
                log.info("Keine weiteren Produkte.")
                break

            products = [e["node"] for e in edges]
            stats["total"] += len(products)

            await process_batch(session, products, stats)

            page_info = data.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

    log.info(f"\n=== FERTIG ===")
    log.info(f"Total: {stats['total']} | Aktiviert: {stats['activated']} | Archiviert: {stats['archived']}")

if __name__ == "__main__":
    asyncio.run(main())
