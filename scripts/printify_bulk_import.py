#!/usr/bin/env python3
"""
Printify → Shopify Bulk Import
Erstellt ECHTE Print-on-Demand Produkte für alle 1.592 Blueprints
"""
import os, json, time, logging, base64, struct, zlib, sys
import requests
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("printify_bulk")

TOKEN    = os.getenv("PRINTIFY_API_TOKEN", os.getenv("PRINTIFY_API_KEY", ""))
SHOP_ID  = os.getenv("PRINTIFY_SHOP_ID", "27975583")
BASE_URL = "https://api.printify.com/v1"
HEADERS  = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Produkt-Preise nach Kategorie
PRICES = {
    "tshirt":    {"price": 2999, "compare": 3999},
    "hoodie":    {"price": 5499, "compare": 6999},
    "mug":       {"price": 1999, "compare": 2699},
    "poster":    {"price": 2499, "compare": 3299},
    "phonecase": {"price": 1999, "compare": 2599},
    "totebag":   {"price": 1699, "compare": 2299},
    "bag":       {"price": 4999, "compare": 6499},
    "hat":       {"price": 2499, "compare": 3299},
    "home":      {"price": 3499, "compare": 4499},
    "sticker":   {"price":  899, "compare": 1299},
    "notebook":  {"price": 1999, "compare": 2699},
    "other":     {"price": 2999, "compare": 3999},
}

# Design-Farben für Abwechslung
DESIGN_COLORS = [
    (26, 26, 26, 255),    # Schwarz
    (255, 255, 255, 255), # Weiß
    (41, 98, 255, 255),   # Blau
    (220, 53, 69, 255),   # Rot
    (40, 167, 69, 255),   # Grün
    (255, 193, 7, 255),   # Gelb/Gold
    (111, 66, 193, 255),  # Lila
    (253, 126, 20, 255),  # Orange
    (32, 201, 151, 255),  # Türkis
    (108, 117, 125, 255), # Grau
]

DESCRIPTION_TEMPLATES = {
    "tshirt": """<h2>👕 {title}</h2>
<p>Premium Unisex T-Shirt von <strong>I Need It!</strong> — Hochwertiger Baumwolldruck für jeden Anlass.</p>
<h3>✅ Produktmerkmale</h3>
<ul>
<li>🌿 100% gekämmte Baumwolle (ringgesponnen)</li>
<li>👕 Klassischer Schnitt — für Männer & Frauen</li>
<li>🎨 Direktdruck (DTG) — lebendige, langlebige Farben</li>
<li>🧺 Maschinenwaschbar bis 40°C</li>
<li>📦 Lieferung innerhalb 5-10 Werktage (DE/AT/CH)</li>
</ul>
<p><strong>Größen:</strong> XS bis 5XL</p>""",

    "hoodie": """<h2>🧥 {title}</h2>
<p>Premium Hoodie von <strong>I Need It!</strong> — Warm, weich und stilvoll.</p>
<h3>✅ Produktmerkmale</h3>
<ul>
<li>🌿 80% Baumwolle, 20% Polyester</li>
<li>🧥 Känguru-Tasche + verstellbare Kapuze</li>
<li>🎨 Direktdruck — farbbrilant & langlebig</li>
<li>🧺 Maschinenwaschbar</li>
<li>📦 5-10 Werktage Lieferzeit</li>
</ul>""",

    "mug": """<h2>☕ {title}</h2>
<p>Hochwertige Keramiktasse 11oz von <strong>I Need It!</strong> — Perfekt als Geschenk oder für jeden Tag.</p>
<h3>✅ Eigenschaften</h3>
<ul>
<li>☕ 330ml Fassungsvermögen</li>
<li>🍽️ Spülmaschinenfest & mikrowellentauglich</li>
<li>🎨 Sublimationsdruck — Farben verblassen nicht</li>
<li>🎁 Perfektes Geschenk für Geburtstag, Weihnachten</li>
</ul>""",

    "poster": """<h2>🖼️ {title}</h2>
<p>Hochwertiger Kunstdruck von <strong>I Need It!</strong> — Einzigartiges Wandbild für dein Zuhause.</p>
<h3>✅ Eigenschaften</h3>
<ul>
<li>📐 Verfügbar in: A4, A3, A2, 30×40cm, 50×70cm</li>
<li>🖨️ 210gsm Premium-Satinglanzpapier</li>
<li>🎨 Lebendige Farben — UV-beständig</li>
<li>🖼️ Rahmenlos geliefert — für alle Standardrahmen geeignet</li>
</ul>""",

    "totebag": """<h2>👜 {title}</h2>
<p>Nachhaltiger Stoffbeutel von <strong>I Need It!</strong> — Stilvoll & umweltfreundlich.</p>
<h3>✅ Eigenschaften</h3>
<ul>
<li>♻️ 100% Baumwolle — nachhaltig produziert</li>
<li>💪 Tragkraft bis 10kg</li>
<li>🎨 Siebdruck — langlebige Farben</li>
<li>📐 Ca. 38×42cm Größe</li>
</ul>""",

    "other": """<h2>🌟 {title}</h2>
<p>Einzigartiges Premium-Produkt von <strong>I Need It!</strong> — Für alle, die etwas Besonderes suchen.</p>
<h3>✅ Warum bei uns kaufen?</h3>
<ul>
<li>✅ Geprüfte Produktqualität</li>
<li>✅ Print-on-Demand — auf Bestellung produziert</li>
<li>✅ 30 Tage Rückgaberecht</li>
<li>✅ Kundensupport auf Deutsch</li>
</ul>""",
}


def make_png(w: int = 200, h: int = 200, color=(26, 26, 26, 255)) -> bytes:
    """Erstellt ein einfaches PNG mit einer Farbe"""
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', c)

    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    raw = b''
    for _ in range(h):
        raw += b'\x00'
        for _ in range(w):
            raw += bytes(color[:3])
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')
    return png


def upload_image(color_idx: int = 0) -> Optional[str]:
    color = DESIGN_COLORS[color_idx % len(DESIGN_COLORS)]
    img = make_png(400, 400, color)
    b64 = base64.b64encode(img).decode()
    r = requests.post(f"{BASE_URL}/uploads/images.json",
        headers=HEADERS,
        json={"file_name": f"ineedit_design_{color_idx}.png", "contents": b64},
        timeout=30)
    if r.status_code == 200:
        img_id = r.json().get("id")
        log.info("Bild hochgeladen: %s (Farbe %d)", img_id, color_idx)
        return img_id
    log.error("Bild-Upload fehlgeschlagen: %s", r.text[:200])
    return None


def categorize_blueprint(title: str) -> str:
    tl = title.lower()
    if any(x in tl for x in ['t-shirt', 'tee', 'tshirt']) and 'women' not in tl and 'kid' not in tl:
        return "tshirt"
    if any(x in tl for x in ['hoodie', 'sweatshirt', 'pullover']):
        return "hoodie"
    if 'mug' in tl or 'cup' in tl or 'tasse' in tl:
        return "mug"
    if any(x in tl for x in ['poster', 'print', 'canvas', 'tapestry', 'art']):
        return "poster"
    if any(x in tl for x in ['phone case', 'phone cover', 'handyhülle']):
        return "phonecase"
    if any(x in tl for x in ['tote bag', 'shopping bag', 'stoffbeutel']):
        return "totebag"
    if any(x in tl for x in ['backpack', 'duffel', 'bag']) and 'tote' not in tl:
        return "bag"
    if any(x in tl for x in ['hat', 'cap', 'beanie', 'bucket']):
        return "hat"
    if any(x in tl for x in ['pillow', 'cushion', 'blanket', 'towel']):
        return "home"
    if any(x in tl for x in ['sticker', 'decal', 'label']):
        return "sticker"
    if any(x in tl for x in ['journal', 'notebook', 'book', 'notepad']):
        return "notebook"
    return "other"


def make_de_title(original: str, category: str) -> str:
    """Erstellt einen deutschen Produkttitel"""
    prefixes = {
        "tshirt": "I Need It! T-Shirt",
        "hoodie": "I Need It! Premium Hoodie",
        "mug": "I Need It! Tasse",
        "poster": "I Need It! Kunstdruck",
        "phonecase": "I Need It! Handyhülle",
        "totebag": "I Need It! Stoffbeutel",
        "bag": "I Need It! Premium Tasche",
        "hat": "I Need It! Cap",
        "home": "I Need It! Wohndekoration",
        "sticker": "I Need It! Aufkleber",
        "notebook": "I Need It! Notizbuch",
        "other": "I Need It! Produkt",
    }
    style_names = [
        "Urban", "Classic", "Vintage", "Premium", "Modern", "Minimal",
        "Bold", "Street", "Casual", "Elegant", "Dynamic", "Creative"
    ]
    prefix = prefixes.get(category, "I Need It!")
    # Use original title stripped for style hints
    clean = original.replace("Unisex", "").replace("Men's", "").replace("Women's", "").strip()
    style = style_names[hash(original) % len(style_names)]
    return f"{prefix} — {style} Design"


def get_first_provider_variants(bp_id: int) -> tuple:
    """Returns (provider_id, variant_ids, placeholder_positions)"""
    r = requests.get(f"{BASE_URL}/catalog/blueprints/{bp_id}/print_providers.json",
        headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return None, [], []
    providers = r.json()
    if not providers:
        return None, [], []

    prov_id = providers[0]["id"]
    r2 = requests.get(f"{BASE_URL}/catalog/blueprints/{bp_id}/print_providers/{prov_id}/variants.json",
        headers=HEADERS, timeout=15)
    if r2.status_code != 200:
        return prov_id, [], []

    data = r2.json()
    variants = data.get("variants", [])
    if not variants:
        return prov_id, [], []

    # Get enabled variants (max 10 to keep it simple)
    var_ids = [v["id"] for v in variants[:10]]
    # Get placeholder positions from first variant
    positions = [p["position"] for p in variants[0].get("placeholders", [])]
    return prov_id, var_ids, positions


def create_printify_product(bp_id: int, bp_title: str, image_id: str, color_idx: int) -> Optional[str]:
    """Erstellt ein Produkt in Printify"""
    category = categorize_blueprint(bp_title)
    pricing  = PRICES.get(category, PRICES["other"])
    title    = make_de_title(bp_title, category)
    desc_tpl = DESCRIPTION_TEMPLATES.get(category, DESCRIPTION_TEMPLATES["other"])
    desc     = desc_tpl.replace("{title}", title)
    tags     = ["ineedit", category, "I Need It", "premium", "print-on-demand"]

    prov_id, var_ids, positions = get_first_provider_variants(bp_id)
    if not prov_id or not var_ids:
        log.warning("Blueprint %d: Keine Provider/Varianten", bp_id)
        return None

    if not positions:
        positions = ["front"]

    variants = [{"id": v, "price": pricing["price"],
                 "compare_at_price": pricing["compare"], "is_enabled": True}
                for v in var_ids]

    placeholders = [{"position": pos,
                     "images": [{"id": image_id, "x": 0.5, "y": 0.5, "scale": 1.0, "angle": 0}]}
                    for pos in positions]

    product = {
        "title": title,
        "description": desc,
        "blueprint_id": bp_id,
        "print_provider_id": prov_id,
        "variants": variants,
        "print_areas": [{"variant_ids": var_ids, "placeholders": placeholders}],
        "tags": tags,
    }

    r = requests.post(f"{BASE_URL}/shops/{SHOP_ID}/products.json",
        headers=HEADERS, json=product, timeout=30)
    if r.status_code == 200:
        prod_id = r.json().get("id")
        return prod_id
    log.error("Produkt-Erstellung Blueprint %d fehlgeschlagen: %s", bp_id, r.text[:200])
    return None


def publish_product(prod_id: str) -> bool:
    """Veröffentlicht ein Printify-Produkt auf Shopify"""
    r = requests.post(f"{BASE_URL}/shops/{SHOP_ID}/products/{prod_id}/publish.json",
        headers=HEADERS,
        json={"title": True, "description": True, "images": True,
              "variants": True, "tags": True, "vendor": True, "collections": False},
        timeout=30)
    return r.status_code == 200


def run_bulk_import(blueprints: list, start_idx: int = 0, max_count: int = 500):
    log.info("🚀 Printify Bulk Import: %d Blueprints verarbeiten (ab Index %d)", min(max_count, len(blueprints) - start_idx), start_idx)

    # Upload 10 verschiedene Farbbilder
    log.info("📤 Bilder hochladen...")
    image_ids = []
    for i in range(min(10, len(DESIGN_COLORS))):
        img_id = upload_image(i)
        if img_id:
            image_ids.append(img_id)
        time.sleep(0.5)

    if not image_ids:
        log.error("Keine Bilder konnten hochgeladen werden!")
        return 0

    log.info("✅ %d Design-Bilder bereit", len(image_ids))

    created = 0
    failed  = 0
    skipped = 0

    progress_file = "/tmp/printify_progress.json"
    try:
        with open(progress_file) as f:
            done_ids = set(json.load(f))
    except Exception:
        done_ids = set()

    for idx, bp in enumerate(blueprints[start_idx:start_idx + max_count], start=start_idx):
        bp_id    = bp["id"]
        bp_title = bp["title"]

        if bp_id in done_ids:
            skipped += 1
            continue

        image_id = image_ids[created % len(image_ids)]
        log.info("[%d/%d] Blueprint %d: %s", idx + 1, len(blueprints), bp_id, bp_title[:50])

        prod_id = create_printify_product(bp_id, bp_title, image_id, created)
        if prod_id:
            time.sleep(0.5)
            ok = publish_product(prod_id)
            if ok:
                created += 1
                done_ids.add(bp_id)
                with open(progress_file, "w") as f:
                    json.dump(list(done_ids), f)
                log.info("  ✅ Veröffentlicht (%d gesamt)", created)
            else:
                log.warning("  ⚠️ Erstellt aber nicht veröffentlicht: %s", prod_id)
                failed += 1
        else:
            failed += 1

        time.sleep(1.0)  # Rate limiting

    log.info("✅ Fertig: %d erstellt, %d fehlgeschlagen, %d übersprungen", created, failed, skipped)
    return created


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()

    with open("/tmp/printify_blueprints.json") as f:
        blueprints = json.load(f)

    log.info("Gesamt Blueprints: %d", len(blueprints))
    run_bulk_import(blueprints, start_idx=args.start, max_count=args.count)
