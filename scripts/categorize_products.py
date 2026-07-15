"""
Vollständige Kategorisierung aller aktiven iNeedit-Produkte:
- Weist product_type anhand Titelanalyse zu
- Setzt passende Tags für Smart Collections
- Überspringt bereits korrekt kategorisierte
"""
import asyncio
import logging
import os
import re
from dotenv import load_dotenv
import aiohttp

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

SHOP    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
API_VER = os.getenv("SHOPIFY_API_VERSION", "2024-04")
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}
TIMEOUT = aiohttp.ClientTimeout(total=60, connect=15)

# Kategorisierungs-Matrix: (type, [tags], [title_keywords])
CATEGORIES = [
    ("Powerstation", ["powerstation", "solar", "energie"],
     ["powerstation", "power station", "portable power", "lifepo", "lithium station"]),
    ("Solar", ["solar", "balkonkraftwerk", "energie"],
     ["solar panel", "balkonkraftwerk", "balkon solar", "solarmodul", "photovoltaik",
      "solar generator", "solar charger", "solarzelle"]),
    ("E-Bike", ["e-bike", "e-mobility"],
     ["e-bike", "ebike", "elektrofahrrad", "electric bike", "pedelec"]),
    ("E-Scooter", ["e-scooter", "e-mobility"],
     ["e-scooter", "elektroroller", "electric scooter", "kick scooter"]),
    ("Saugroboter", ["saugroboter", "roboter", "smart-home"],
     ["saugroboter", "robot vacuum", "roborock", "deebot", "dreame", "narwal",
      "proscenic", "irobot", "roomba", "staubsauger roboter"]),
    ("Smart Security", ["security", "überwachung", "smart-home"],
     ["überwachungskamera", "security camera", "dashcam", "dash cam", "kamera wifi",
      "ip kamera", "cctv", "alarm system", "doorbell camera", "türklingel kamera",
      "tpms", "reifendruck"]),
    ("Smart Lighting", ["led", "beleuchtung", "smart-home"],
     ["led strip", "led lichtband", "rgb led", "smart light", "smart lamp",
      "philips hue", "govee", "led lampe", "smart bulb", "leuchtmittel"]),
    ("Smart Plug", ["smart-home", "steckdose"],
     ["smart plug", "smart steckdose", "zwischenstecker", "wifi steckdose",
      "tuya smart", "wlan steckdose", "steckdose smart", "smart power strip"]),
    ("Smart Display", ["smart-home", "display"],
     ["smart display", "echo show", "tablet display", "smart screen", "magic mirror"]),
    ("Smart Thermostat", ["smart-home", "heizung"],
     ["thermostat", "heizungsregler", "raumthermostat", "heizkörper", "smart heizung"]),
    ("Grow Light", ["grow", "indoor-growing", "led"],
     ["grow light", "grow led", "pflanzenlampe", "vollspektrum", "quantum board",
      "grow lamp", "pflanzenlicht", "indoor grow"]),
    ("Grow Tent", ["grow", "indoor-growing"],
     ["grow tent", "grow zelt", "growbox", "anbauzelt", "kulturzelt"]),
    ("3D Drucker", ["3d-druck", "maker"],
     ["3d drucker", "3d-drucker", "3d printer", "fdm drucker", "resin drucker",
      "bambu", "bambulab", "creality", "ender-3", "prusa", "filament drucker"]),
    ("Laser Engraver", ["laser-engraver", "maker"],
     ["laser engraver", "lasergravur", "laser graveur", "laser cutter",
      "lasergraviermaschine", "cnc laser", "xtools", "sculpfun"]),
    ("Drone", ["drohne", "kamera"],
     ["drohne", "drone", "dji", "mini drohne", "fpv drohne", "quadcopter"]),
    ("Kamera", ["kamera", "fotografie"],
     ["action cam", "action camera", "gopro", "insta360", "360 kamera",
      "webcam", "usb kamera", "streaming kamera"]),
    ("Audio", ["audio", "sound"],
     ["lautsprecher", "speaker", "bluetooth speaker", "kopfhörer", "headphone",
      "earbuds", "earphone", "hifi", "hi-fi", "soundbar", "subwoofer", "amp"]),
    ("Gaming", ["gaming"],
     ["gamepad", "controller", "gaming maus", "gaming tastatur", "gaming headset",
      "gaming chair", "rgb gaming", "ps5", "xbox", "nintendo"]),
    ("Werkzeug", ["werkzeug", "diy"],
     ["akkuschrauber", "bohrmaschine", "säge", "schleifer", "schweißgerät",
      "lötkolben", "multimeter", "oszilloskop", "zange", "ratsche", "flex ",
      "winkelschleifer", "kreissäge", "oberfräse", "stichsäge"]),
    ("Auto", ["auto", "fahrzeugtechnik"],
     ["dashcam", "carplay", "android auto", "obd", "head unit", "car dvr",
      "autokamera", "car radio", "car charger", "kfz", "auto adapter"]),
    ("Home Office", ["home-office", "elektronik"],
     ["monitor", "laptop stand", "ergonomic", "desk lamp", "schreibtischlampe",
      "monitor arm", "standing desk", "stehpult", "bürostuhl", "webcam", "docking"]),
    ("Smart Home", ["smart-home"],
     ["smart home", "zigbee", "z-wave", "matter", "home assistant", "alexa",
      "google home", "tuya", "homekit", "aqara", "sonos"]),
    ("Pet Tech", ["haustier", "pet"],
     ["futterautomat", "pet feeder", "katzenkratzbaum", "hundebett",
      "wasserspender hund", "hundespielzeug", "katzenspielzeug", "pet camera",
      "gps tracker hund", "haustier", "hundehalsband"]),
    ("Camping", ["camping", "outdoor"],
     ["camping", "trekking", "survival", "outdoor lampe", "campingkocher",
      "zelt", "schlafsack", "camping solar", "powerbank outdoor"]),
    ("Fitness", ["fitness", "sport"],
     ["laufband", "hometrainer", "fahrradergometer", "crosstrainer", "gewichte",
      "widerstandsband", "yoga", "fitness band", "smartwatch sport"]),
    ("Smartwatch", ["smartwatch", "wearable"],
     ["smartwatch", "smart watch", "fitness tracker", "garmin", "fitbit",
      "huawei watch", "samsung watch", "apple watch", "wear os"]),
    ("Smart Gadget", ["gadget", "elektronik"],  # fallback
     []),
]

def classify_product(title: str, current_type: str) -> tuple[str, list[str]]:
    """Klassifiziert ein Produkt anhand seines Titels."""
    t = title.lower()
    for ptype, tags, keywords in CATEGORIES:
        for kw in keywords:
            if kw in t:
                return ptype, tags
    # Keep current type if already specific
    if current_type and current_type not in ("Smart Gadget", "Electronics & Gadgets", ""):
        return current_type, []
    return "Smart Gadget", ["gadget", "elektronik"]


async def get_all_active_products(session: aiohttp.ClientSession) -> list[dict]:
    base = f"https://{SHOP}/admin/api/{API_VER}/products.json"
    all_products = []
    page_info = None
    page = 0
    while True:
        params = {"limit": 250, "status": "active", "vendor": "iNeedit",
                  "fields": "id,title,product_type,tags"}
        if page_info:
            params = {"limit": 250, "page_info": page_info, "fields": "id,title,product_type,tags"}
        async with session.get(base, headers=HEADERS, params=params, timeout=TIMEOUT) as r:
            data = await r.json()
            products = data.get("products", [])
            all_products.extend(products)
            page += 1
            log.info("Seite %d geladen: %d Produkte (gesamt %d)", page, len(products), len(all_products))
            link = r.headers.get("Link", "")
            if 'rel="next"' not in link:
                break
            import re as _re
            m = _re.search(r'page_info=([^&>]+).*?rel="next"', link)
            if not m:
                break
            page_info = m.group(1)
    return all_products


async def update_product(session: aiohttp.ClientSession, pid: int,
                         new_type: str, add_tags: list[str]) -> bool:
    url = f"https://{SHOP}/admin/api/{API_VER}/products/{pid}.json"
    payload = {"product": {"id": pid, "product_type": new_type}}
    if add_tags:
        payload["product"]["tags"] = ", ".join(add_tags)
    for attempt in range(3):
        async with session.put(url, headers=HEADERS, json=payload, timeout=TIMEOUT) as r:
            if r.status == 429:
                await asyncio.sleep(3)
                continue
            return r.status == 200
    return False


async def main():
    log.info("=== PRODUCT KATEGORISIERUNG START ===")
    connector = aiohttp.TCPConnector(limit=10, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        products = await get_all_active_products(session)
        log.info("Gesamt geladen: %d aktive iNeedit-Produkte", len(products))

        to_update = []
        already_ok = 0
        for p in products:
            new_type, new_tags = classify_product(p["title"], p.get("product_type", ""))
            current_tags = [t.strip() for t in p.get("tags", "").split(",") if t.strip()]
            missing_tags = [t for t in new_tags if t not in current_tags]
            if new_type != p.get("product_type", "") or missing_tags:
                all_tags = list(set(current_tags + missing_tags))
                to_update.append((p["id"], p["title"][:60], new_type, all_tags))
            else:
                already_ok += 1

        log.info("Bereits OK: %d | Zu updaten: %d", already_ok, len(to_update))

        updated = 0
        errors = 0
        CHUNK = 5
        for i in range(0, len(to_update), CHUNK):
            chunk = to_update[i:i+CHUNK]
            results = await asyncio.gather(
                *[update_product(session, pid, ptype, tags)
                  for pid, title, ptype, tags in chunk],
                return_exceptions=True
            )
            for j, (pid, title, ptype, tags) in enumerate(chunk):
                if results[j] is True:
                    updated += 1
                else:
                    errors += 1
            if (i // CHUNK) % 10 == 0:
                log.info("Progress: %d/%d (errors: %d)", i + CHUNK, len(to_update), errors)
            await asyncio.sleep(0.3)

        log.info("=== DONE: %d aktualisiert | %d Fehler ===", updated, errors)


if __name__ == "__main__":
    asyncio.run(main())
