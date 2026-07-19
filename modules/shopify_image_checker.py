"""
ShopifyImageChecker — Automatischer Bild-Qualitätsprüfer und Reparatur-Manager.

Aufgaben:
1. Scan alle Produkte auf fehlerhafte/mismatched Bilder
2. Erkennt: falsches Bild, kein Bild, Black Friday/Sale-Fotos, Geschenke, Gutscheine
3. Auto-Reparatur: Pexels-Suche nach passendem Bild + Shopify-Update
4. Scheduler-Task: läuft täglich und repariert automatisch
"""
import asyncio
import logging
import os
import re
import time
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

SHOPIFY_DOMAIN = os.getenv("SHOPIFY_MYSHOPIFY_DOMAIN", "")
if not SHOPIFY_DOMAIN:
    _raw = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    SHOPIFY_DOMAIN = re.sub(r"^https?://", "", _raw).rstrip("/")

SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

_API = f"https://{SHOPIFY_DOMAIN}/admin/api/2024-01"

# Bilder die GARANTIERT falsch sind — egal welches Produkt
_BAD_IMAGE_MARKERS = [
    "black friday", "blackfriday", "sale", "gift", "geschenk",
    "ribbon", "bow", "gutschein", "voucher", "coupon",
    "pexels-photo-5632399",  # Das konkrete falsche Bild von vorhin
]

# Schlüsselwörter im Produkttitel → erwartete Pexels-Suchbegriffe
_TITLE_TO_SEARCH = [
    (["lampe", "lamp", "licht", "light", "birne", "bulb", "led"], "smart LED lamp wifi"),
    (["thermostat", "heizung", "heater", "wärme"], "smart thermostat home"),
    (["kamera", "camera", "überwachung", "security"], "smart home security camera"),
    (["steckdose", "plug", "socket", "outlet"], "smart plug wifi"),
    (["lautsprecher", "speaker", "echo", "alexa"], "smart speaker home assistant"),
    (["sensor", "detektor", "detector", "alarm"], "smart home sensor"),
    (["roboter", "robot", "sauger", "vacuum"], "robot vacuum cleaner smart"),
    (["solar", "panel", "powerstation", "akku"], "solar panel power station"),
    (["display", "bildschirm", "monitor", "tablet"], "smart display home hub"),
    (["schalter", "switch", "dimmer"], "smart home light switch"),
    (["lock", "schloss", "türschloss"], "smart door lock"),
    (["drohne", "drone"], "drone quadcopter"),
    (["uhr", "watch", "smartwatch"], "smartwatch fitness tracker"),
    (["hub", "gateway", "bridge", "zentrale"], "smart home hub gateway"),
    (["luftreiniger", "air purifier", "humidifier", "luftbefeuchter"], "air purifier smart home"),
    (["kühlschrank", "fridge", "refrigerator"], "smart refrigerator"),
    (["waschmaschine", "washing"], "washing machine smart"),
]


def _image_is_bad(image_url: str, product_title: str) -> tuple[bool, str]:
    """Gibt (True, Grund) zurück wenn das Bild offensichtlich falsch ist."""
    url_lower = image_url.lower()
    title_lower = product_title.lower()

    # Bekannte schlechte Bilder
    for marker in _BAD_IMAGE_MARKERS:
        if marker in url_lower:
            return True, f"URL enthält '{marker}'"

    # Pexels-Foto-ID Kreuzprüfung: bestimmte IDs sind bekannte Stock-Fotos ohne Produktbezug
    # z.B. 5632399 = Black Friday Geschenk
    bad_pexels_ids = {"5632399", "1029243", "5632369"}
    m = re.search(r"pexels-photo-(\d+)", url_lower)
    if m and m.group(1) in bad_pexels_ids:
        return True, f"Bekanntes falsches Pexels-Foto ({m.group(1)})"

    return False, ""


def _find_search_query(product_title: str, product_type: str = "") -> str:
    """Findet den besten Pexels-Suchbegriff basierend auf Produkttitel."""
    text = (product_title + " " + product_type).lower()
    for keywords, query in _TITLE_TO_SEARCH:
        if any(kw in text for kw in keywords):
            return query
    # Fallback: ersten 3 Wörter des Titels
    words = product_title.split()[:3]
    return " ".join(words) + " product"


async def _pexels_search(query: str) -> Optional[str]:
    """Sucht ein passendes Bild auf Pexels und gibt die URL zurück."""
    if not PEXELS_API_KEY:
        log.warning("PEXELS_API_KEY nicht gesetzt — kein automatischer Bild-Ersatz")
        return None

    url = "https://api.pexels.com/v1/search"
    params = {"query": query, "per_page": 5, "orientation": "square"}
    headers = {"Authorization": PEXELS_API_KEY}

    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, headers=headers,
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    log.warning("Pexels API %d für '%s'", r.status, query)
                    return None
                data = await r.json()
                photos = data.get("photos", [])
                if not photos:
                    return None
                # Nimm das erste Foto in medium-Qualität
                src = photos[0].get("src", {})
                return src.get("large") or src.get("medium") or src.get("original")
    except Exception as e:
        log.warning("Pexels-Suche fehlgeschlagen: %s", e)
        return None


async def _get_product_media(product_id: str) -> list[dict]:
    """Lädt alle Medien eines Produkts via GraphQL."""
    query = """
    query($id: ID!) {
      product(id: $id) {
        media(first: 10) {
          edges {
            node {
              id
              ... on MediaImage {
                image { url }
              }
            }
          }
        }
      }
    }
    """
    url = f"{_API}/graphql.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={"query": query, "variables": {"id": product_id}},
                              headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json()
                edges = (data.get("data", {}).get("product", {})
                         .get("media", {}).get("edges", []))
                return [
                    {
                        "id": e["node"]["id"],
                        "url": e["node"].get("image", {}).get("url", ""),
                    }
                    for e in edges
                ]
    except Exception as e:
        log.warning("Medien-Abruf fehlgeschlagen für %s: %s", product_id, e)
        return []


async def _replace_product_image(product_id: str, remove_media_ids: list[str],
                                 new_image_url: str, alt_text: str) -> bool:
    """Ersetzt Produktbild via GraphQL productUpdateMedia + productCreateMedia."""
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
    url = f"{_API}/graphql.json"

    # Schritt 1: Altes Bild entfernen
    if remove_media_ids:
        del_mutation = """
        mutation($productId: ID!, $mediaIds: [ID!]!) {
          productDeleteMedia(productId: $productId, mediaIds: $mediaIds) {
            deletedMediaIds
            userErrors { field message }
          }
        }
        """
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json={
                    "query": del_mutation,
                    "variables": {"productId": product_id, "mediaIds": remove_media_ids}
                }, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    result = await r.json()
                    errors = (result.get("data", {})
                              .get("productDeleteMedia", {})
                              .get("userErrors", []))
                    if errors:
                        log.warning("Bild-Löschen Fehler: %s", errors)
        except Exception as e:
            log.warning("Bild-Löschen Exception: %s", e)

        await asyncio.sleep(0.5)

    # Schritt 2: Neues Bild hinzufügen
    add_mutation = """
    mutation($productId: ID!, $media: [CreateMediaInput!]!) {
      productCreateMedia(productId: $productId, media: $media) {
        media { id }
        userErrors { field message }
      }
    }
    """
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={
                "query": add_mutation,
                "variables": {
                    "productId": product_id,
                    "media": [{"originalSource": new_image_url, "alt": alt_text,
                               "mediaContentType": "IMAGE"}]
                }
            }, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                result = await r.json()
                errors = (result.get("data", {})
                          .get("productCreateMedia", {})
                          .get("userErrors", []))
                if errors:
                    log.warning("Bild-Hinzufügen Fehler: %s", errors)
                    return False
                return True
    except Exception as e:
        log.warning("Bild-Hinzufügen Exception: %s", e)
        return False


async def check_and_repair_product_images(product: dict) -> dict:
    """
    Prüft ein Produkt auf fehlerhafte Bilder und repariert sie automatisch.

    product: dict mit keys: id, title, product_type, images (list of {url, id})
    Returns: {"ok": bool, "repaired": bool, "reason": str}
    """
    pid = product.get("id", "")
    title = product.get("title", "")
    ptype = product.get("product_type", "")
    images = product.get("images", [])

    if not images:
        return {"ok": False, "repaired": False, "reason": "Kein Bild vorhanden"}

    bad_media_ids = []
    bad_reasons = []

    for img in images:
        url = img.get("url", "")
        mid = img.get("id", "")
        is_bad, reason = _image_is_bad(url, title)
        if is_bad:
            bad_media_ids.append(mid)
            bad_reasons.append(f"{reason} [{url[:60]}]")

    if not bad_media_ids:
        return {"ok": True, "repaired": False, "reason": "Bilder OK"}

    log.warning("IMAGE-CHECKER: %s — %d fehlerhafte Bilder: %s",
                title, len(bad_media_ids), "; ".join(bad_reasons))

    # Suche passendes Ersatzbild
    search_query = _find_search_query(title, ptype)
    new_url = await _pexels_search(search_query)

    if not new_url:
        log.warning("Kein Ersatzbild gefunden für '%s' (query: %s)", title, search_query)
        return {"ok": False, "repaired": False,
                "reason": f"Falsches Bild erkannt, kein Ersatz: {bad_reasons[0]}"}

    # Nur die schlechten Bilder ersetzen, gute behalten
    ok = await _replace_product_image(pid, bad_media_ids, new_url,
                                      alt_text=f"{title} Smart Home")

    if ok:
        log.info("IMAGE-CHECKER REPARIERT: %s → %s", title, new_url[:60])
        return {"ok": True, "repaired": True,
                "reason": f"Repariert: {bad_reasons[0]} → {search_query}",
                "new_image": new_url}
    else:
        return {"ok": False, "repaired": False,
                "reason": f"Reparatur fehlgeschlagen für: {bad_reasons[0]}"}


async def scan_and_repair_all(limit: int = 50, send_telegram: bool = True) -> dict:
    """
    Scannt alle Produkte auf fehlerhafte Bilder und repariert sie automatisch.
    Läuft als täglicher Scheduler-Task.
    """
    if not SHOPIFY_TOKEN or not SHOPIFY_DOMAIN:
        log.error("Shopify-Credentials fehlen — Image-Checker abgebrochen")
        return {"ok": False, "checked": 0, "repaired": 0}

    log.info("IMAGE-CHECKER: Starte Scan von bis zu %d Produkten...", limit)

    query = """
    query($first: Int!, $after: String) {
      products(first: $first, after: $after, query: "status:active") {
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
                    image { url }
                  }
                }
              }
            }
          }
          cursor
        }
        pageInfo { hasNextPage endCursor }
      }
    }
    """

    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
    api_url = f"{_API}/graphql.json"

    checked = 0
    repaired = 0
    errors = 0
    repaired_products = []
    cursor = None

    while checked < limit:
        batch = min(50, limit - checked)
        variables = {"first": batch}
        if cursor:
            variables["after"] = cursor

        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(api_url, json={"query": query, "variables": variables},
                                  headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    data = await r.json()
        except Exception as e:
            log.error("GraphQL-Fehler beim Image-Scan: %s", e)
            break

        edges = (data.get("data", {}).get("products", {}).get("edges", []))
        page_info = (data.get("data", {}).get("products", {}).get("pageInfo", {}))

        for edge in edges:
            node = edge["node"]
            images = [
                {"id": m["node"]["id"], "url": m["node"].get("image", {}).get("url", "")}
                for m in node.get("media", {}).get("edges", [])
                if "image" in m["node"]
            ]

            result = await check_and_repair_product_images({
                "id": node["id"],
                "title": node["title"],
                "product_type": node.get("productType", ""),
                "images": images,
            })

            checked += 1
            if result.get("repaired"):
                repaired += 1
                repaired_products.append({
                    "title": node["title"],
                    "reason": result.get("reason", ""),
                })
            elif not result.get("ok") and "Kein Bild" in result.get("reason", ""):
                errors += 1

            await asyncio.sleep(0.3)  # Rate-Limit schonen

        if not page_info.get("hasNextPage") or not edges:
            break
        cursor = page_info.get("endCursor")

    summary = {
        "ok": True,
        "checked": checked,
        "repaired": repaired,
        "errors": errors,
        "repaired_products": repaired_products,
    }

    log.info("IMAGE-CHECKER FERTIG: %d geprüft, %d repariert, %d Fehler",
             checked, repaired, errors)

    if send_telegram and repaired > 0:
        _notify_telegram(checked, repaired, repaired_products)

    return summary


def _notify_telegram(checked: int, repaired: int, products: list[dict]):
    """Sendet Telegram-Benachrichtigung über reparierte Bilder."""
    try:
        import asyncio as _asyncio
        from modules.telegram_notifier import send_alert

        lines = [f"🖼️ *Image-Checker Bericht*"]
        lines.append(f"✅ {checked} geprüft | 🔧 {repaired} repariert")
        for p in products[:5]:
            lines.append(f"• {p['title'][:40]}...")
        if len(products) > 5:
            lines.append(f"... und {len(products) - 5} weitere")

        _asyncio.create_task(send_alert("\n".join(lines)))
    except Exception as e:
        log.debug("Telegram-Notify fehlgeschlagen: %s", e)


# Direkter Scheduler-Einstiegspunkt
async def run():
    """Wird vom automation_scheduler.py täglich aufgerufen."""
    return await scan_and_repair_all(limit=200, send_telegram=True)
