"""
ShopifyImageManager — automatischer Bild-Validator & Korrektor für ineedit.com.co
Scannt alle Produkte, erkennt falsche/fehlende Bilder, ersetzt sie automatisch.
"""
import asyncio
import logging
import os
import re
import aiohttp
from typing import Optional

log = logging.getLogger(__name__)

SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP_URL", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# Bild-Muster die IMMER falsch sind (Keyword in URL-Pfad)
_BAD_IMAGE_PATTERNS = [
    "black-friday",
    "blackfriday",
    "sale-banner",
    "voucher",
    "coupon",
    "discount-banner",
    "gift-box",
    "gift_box",
    "christmas",
    "halloween",
    "thanksgiving",
    "holiday-sale",
    "seasonal",
    "promo-banner",
    "pexels-photo-5632399",  # Das konkrete falsche Bild (Black Friday)
    "pexels-photo-1303098",
    "placeholder",
    "no-image",
    "noimage",
    "coming-soon",
    "dummy",
]

# Produkttyp → Pexels Suchbegriffe
_TYPE_TO_KEYWORDS = {
    "lamp": "smart LED lamp home",
    "lampe": "smart LED lamp home",
    "thermostat": "smart thermostat home",
    "solar": "solar panel energy home",
    "powerstation": "portable power station battery",
    "powerbank": "power bank charger portable",
    "speaker": "bluetooth speaker wireless",
    "lautsprecher": "bluetooth speaker wireless",
    "robot": "robot vacuum cleaner smart home",
    "staubsauger": "robot vacuum cleaner",
    "kamera": "security camera smart home",
    "camera": "security camera surveillance",
    "lock": "smart door lock keyless",
    "schloss": "smart door lock",
    "bulb": "smart LED bulb color",
    "glühbirne": "smart LED bulb",
    "sensor": "smart home sensor motion",
    "plug": "smart plug outlet wifi",
    "steckdose": "smart plug wifi",
    "display": "smart display touch screen",
    "monitor": "computer monitor screen",
    "watch": "smart watch fitness",
    "uhr": "smart watch fitness tracker",
    "headphone": "wireless headphone earbuds",
    "kopfhörer": "wireless headphone earbuds",
    "drone": "drone quadcopter aerial",
    "drohne": "drone quadcopter",
    "e-bike": "electric bike bicycle",
    "ebike": "electric bike bicycle",
    "scooter": "electric scooter",
    "keyboard": "keyboard computer peripherals",
    "tastatur": "keyboard wireless",
    "mouse": "computer mouse wireless",
    "maus": "computer mouse",
    "charger": "wireless charger phone",
    "ladegerät": "wireless charger phone",
    "hub": "smart home hub controller",
    "gateway": "smart home gateway",
    "default": "smart home technology gadget",
}


def _is_bad_image(url: str) -> bool:
    """Prüft ob eine Bild-URL offensichtlich falsch/generisch ist."""
    url_lower = url.lower()
    for pattern in _BAD_IMAGE_PATTERNS:
        if pattern in url_lower:
            return True
    # Sehr kurze URLs oder Placeholder
    if not url or len(url) < 20:
        return True
    return False


def _get_search_keyword(title: str, product_type: str) -> str:
    """Leitet Pexels-Suchbegriff aus Produkt-Titel/Typ ab."""
    combined = (title + " " + (product_type or "")).lower()
    for key, kw in _TYPE_TO_KEYWORDS.items():
        if key in combined:
            return kw
    return _TYPE_TO_KEYWORDS["default"]


async def _fetch_pexels_image(keyword: str, session: aiohttp.ClientSession) -> Optional[str]:
    """Sucht ein passendes Bild auf Pexels und gibt die URL zurück."""
    if not PEXELS_API_KEY:
        # Fallback: bekannte gute Smart-Home Pexels IDs
        fallback_ids = {
            "smart": "6913319",
            "solar": "9875440",
            "power": "7856856",
            "speaker": "4790271",
            "robot": "6180133",
            "camera": "3861457",
            "watch": "437037",
            "drone": "1087180",
            "default": "6913319",
        }
        kw_lower = keyword.lower()
        for k, pid in fallback_ids.items():
            if k in kw_lower:
                return f"https://images.pexels.com/photos/{pid}/pexels-photo-{pid}.jpeg"
        return f"https://images.pexels.com/photos/6913319/pexels-photo-6913319.jpeg"

    try:
        async with session.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": keyword, "per_page": 3, "orientation": "square"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                photos = data.get("photos", [])
                if photos:
                    return photos[0]["src"]["medium"]
    except Exception as e:
        log.debug("Pexels API error: %s", e)
    return None


async def _shopify_gql(query: str, variables: dict, session: aiohttp.ClientSession) -> dict:
    """Führt einen Shopify GraphQL-Call durch."""
    if not SHOPIFY_SHOP or not SHOPIFY_TOKEN:
        return {}
    url = f"https://{SHOPIFY_SHOP}/admin/api/2024-01/graphql.json"
    try:
        async with session.post(
            url,
            headers={
                "X-Shopify-Access-Token": SHOPIFY_TOKEN,
                "Content-Type": "application/json",
            },
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        log.error("Shopify GQL error: %s", e)
    return {}


async def _get_all_products_with_images(session: aiohttp.ClientSession) -> list:
    """Lädt alle aktiven Produkte mit ihren Bild-URLs."""
    products = []
    cursor = None
    query = """
    query getProducts($cursor: String) {
      products(first: 50, after: $cursor, query: "status:active") {
        edges {
          node {
            id
            title
            productType
            media(first: 5) {
              edges {
                node {
                  id
                  ... on MediaImage {
                    image { url altText }
                  }
                }
              }
            }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
    """
    while True:
        data = await _shopify_gql(query, {"cursor": cursor}, session)
        page = data.get("data", {}).get("products", {})
        edges = page.get("edges", [])
        for edge in edges:
            node = edge["node"]
            media = []
            for m in node.get("media", {}).get("edges", []):
                mn = m["node"]
                img = mn.get("image")
                if img:
                    media.append({"media_id": mn["id"], "url": img.get("url", "")})
            products.append({
                "id": node["id"],
                "title": node["title"],
                "product_type": node.get("productType", ""),
                "images": media,
            })
        page_info = page.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    return products


async def _remove_and_add_image(
    product_id: str,
    remove_media_id: str,
    new_image_url: str,
    alt_text: str,
    session: aiohttp.ClientSession,
) -> bool:
    """Entfernt ein falsches Bild und fügt das korrekte hinzu."""
    mutation = """
    mutation productUpdateMedia($productId: ID!, $deleteIds: [ID!]!, $media: [CreateMediaInput!]!) {
      productDeleteMedia(productId: $productId, mediaIds: $deleteIds) {
        deletedMediaIds
        product { id }
        userErrors { field message }
      }
      productCreateMedia(productId: $productId, media: $media) {
        media { id }
        product { id }
        userErrors { field message }
      }
    }
    """
    variables = {
        "productId": product_id,
        "deleteIds": [remove_media_id],
        "media": [{"originalSource": new_image_url, "alt": alt_text, "mediaContentType": "IMAGE"}],
    }
    result = await _shopify_gql(mutation, variables, session)
    errors = (
        result.get("data", {}).get("productDeleteMedia", {}).get("userErrors", [])
        + result.get("data", {}).get("productCreateMedia", {}).get("userErrors", [])
    )
    if errors:
        log.warning("Image update errors for %s: %s", product_id, errors)
        return False
    return True


async def scan_and_fix_images(dry_run: bool = False) -> dict:
    """
    Hauptfunktion: Scannt alle Produkte, erkennt falsche Bilder, repariert sie.
    dry_run=True → nur Report, kein Schreiben.
    """
    report = {"scanned": 0, "bad_found": 0, "fixed": 0, "errors": 0, "details": []}

    async with aiohttp.ClientSession() as session:
        log.info("ImageManager: Lade alle Produkte...")
        products = await _get_all_products_with_images(session)
        report["scanned"] = len(products)
        log.info("ImageManager: %d Produkte geladen", len(products))

        for product in products:
            pid = product["id"]
            title = product["title"]
            ptype = product["product_type"]
            images = product["images"]

            if not images:
                # Kein Bild vorhanden
                report["bad_found"] += 1
                keyword = _get_search_keyword(title, ptype)
                new_url = await _fetch_pexels_image(keyword, session) if not dry_run else None
                report["details"].append({
                    "product_id": pid, "title": title,
                    "issue": "no_image", "fixed": False, "new_url": new_url,
                })
                continue

            for img in images:
                url = img["url"]
                media_id = img["media_id"]

                if not _is_bad_image(url):
                    continue

                report["bad_found"] += 1
                log.warning("Falsches Bild gefunden: %s → %s", title, url)

                if dry_run:
                    report["details"].append({
                        "product_id": pid, "title": title,
                        "issue": "bad_image", "bad_url": url, "fixed": False,
                    })
                    continue

                # Ersatzbild suchen
                keyword = _get_search_keyword(title, ptype)
                new_url = await _fetch_pexels_image(keyword, session)

                if not new_url:
                    log.error("Kein Ersatzbild für: %s", title)
                    report["errors"] += 1
                    continue

                alt_text = f"{title} Smart Home"
                success = await _remove_and_add_image(pid, media_id, new_url, alt_text, session)
                if success:
                    report["fixed"] += 1
                    log.info("Bild repariert: %s → %s", title, new_url)
                    report["details"].append({
                        "product_id": pid, "title": title,
                        "issue": "bad_image", "bad_url": url,
                        "new_url": new_url, "fixed": True,
                    })
                else:
                    report["errors"] += 1

    return report


async def fix_single_product(product_id: str, new_image_url: str, alt_text: str = "") -> dict:
    """Repariert ein einzelnes Produkt schnell (z.B. nach manuellem Hinweis)."""
    async with aiohttp.ClientSession() as session:
        products = await _get_all_products_with_images(session)
        for p in products:
            if p["id"] == product_id and p["images"]:
                media_id = p["images"][0]["media_id"]
                title = p["title"]
                alt = alt_text or f"{title} Smart Home"
                ok = await _remove_and_add_image(product_id, media_id, new_image_url, alt, session)
                return {"ok": ok, "product_id": product_id, "new_url": new_image_url}
    return {"ok": False, "error": "Produkt nicht gefunden"}


# Scheduler-Task-Wrapper
async def task_image_scan():
    """Täglicher Scan aller Produkt-Bilder — wird vom Scheduler aufgerufen."""
    try:
        result = await scan_and_fix_images(dry_run=False)
        msg = (
            f"🖼 Image-Scan abgeschlossen:\n"
            f"• Geprüft: {result['scanned']}\n"
            f"• Fehlerhafte Bilder: {result['bad_found']}\n"
            f"• Repariert: {result['fixed']}\n"
            f"• Fehler: {result['errors']}"
        )
        if result["bad_found"] > 0:
            log.warning(msg)
        else:
            log.info(msg)
        return result
    except Exception as e:
        log.error("ImageManager task error: %s", e)
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(scan_and_fix_images(dry_run=True))
