#!/usr/bin/env python3
"""
Shopify Tag Optimizer — Fügt echte Kategorie-Tags zu Produkten hinzu.
Smart Collections brauchen relevante Tags, damit Produkte automatisch zugeordnet werden.
Läuft über alle Produkte, analysiert Title + Body und fügt Keywords als Tags hinzu.
"""
from __future__ import annotations
import requests, os, re, time, sys
from pathlib import Path

env = Path(__file__).parent.parent / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

SHOP    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}
BASE    = f"https://{SHOP}/admin/api/{VERSION}"
DELAY   = 0.55  # stay under Basic 2 req/sec limit

# Keyword → Tag mappings (German and English)
# Each entry: (keyword_phrases, tags_to_add)
# Keyword phrases are matched as substrings ONLY if they appear as whole words or compound fragments.
# Long specific phrases are safe; short ambiguous words (auto, kind, etc.) use word-boundary matching.
KEYWORD_TAGS: list[tuple[list[str], list[str]]] = [
    # Smart Home
    (["smart home", "alexa kompatibel", "zigbee", "z-wave", "smarte steckdose",
      "smarter schalter", "smarte beleuchtung", "wlan steckdose",
      "thermostat steuer", "sicherheitskamera", "türklingel kamera", "smarten"],
     ["smart-home", "tech", "gadget"]),
    # Audio
    (["kopfhörer", "headphone", "earphone", "ohrhörer", "lautsprecher", "soundbar",
      "bluetooth speaker", "subwoofer", "noise cancelling", "mikrofon"],
     ["audio", "tech", "gadget"]),
    # Kamera & Foto
    (["kamera", "dashcam", "webcam", "action cam", "gopro", "objektiv",
      "stativ", "foto zubehör", "gimbal", "videokamera"],
     ["kamera", "foto-video", "tech"]),
    # Smartphone & Tablet
    (["smartphone", "iphone", "samsung galaxy", "android zubehör", "tablet",
      "ipad", "handyhülle", "panzerglas", "schutzglas für"],
     ["smartphone", "mobile", "tech"]),
    # Laptop & PC
    (["laptop", "notebook", "macbook", "gaming pc", "tastatur", "mausmatte",
      "monitor halterung", "usb-c hub", "dockingstation", "schreibtisch organizer pc"],
     ["laptop-pc", "tech", "home-office"]),
    # Laden & Energie
    (["ladekabel", "powerbank", "ladestation", "wireless charging", "induktives laden",
      "solar panel", "solarladegerät", "akkupack", "multi-charger"],
     ["laden-energie", "tech", "gadget"]),
    # Fitness & Sport
    (["fitness", "yoga", "workout", "hanteln", "laufband", "fahrrad trainer",
      "crossfit", "pilates", "dehnband", "fitnesstracker", "sportgerät",
      "trainingsgerät", "fitnessband", "sportmatte"],
     ["fitness", "sport", "gesundheit"]),
    # Gesundheit
    (["massagegerät", "massage gun", "physiotherapie", "nacken masseur",
      "rücken schmerz", "entspannungsbad", "schlafmaske", "meditation kissen",
      "health tracker", "blutdruck", "pulsoximeter", "wellness"],
     ["gesundheit", "wellness"]),
    # Küche
    (["küche", "küchenmaschine", "airfryer", "luftfritteuse", "kaffeemaschine",
      "espressomaschine", "wasserkocher", "toaster", "entsafter", "kochmesser",
      "pfanne", "kochtopf", "backen zubehör", "schneidebrett"],
     ["küche", "haushalt"]),
    # Garten & Outdoor
    (["garten", "bewässerung", "rasenmäher", "gartenwerkzeug", "outdoor camping",
      "wandern zubehör", "zelt", "schlafsack", "grillzubehör", "balkon pflanzen",
      "pflanzentopf", "unkraut", "terrasse"],
     ["garten", "outdoor"]),
    # Auto & Reise
    (["auto zubehör", "kfz", "fahrzeug", "reisekoffer", "trolley",
      "reiserucksack", "navi halterung", "dashcam auto", "autopflege",
      "car holder", "reiseadapter", "kompressionsbeutel"],
     ["auto-reise", "reise"]),
    # Haustier
    (["hundehalsband", "hundeleine", "hundebett", "katzenspielzeug", "katzenklo",
      "tiernahrung", "aquarium", "hundefutter", "katzenfutter", "haustier"],
     ["haustier", "tier"]),
    # Baby & Kinder
    (["babyphone", "kinderwagen", "kindersicherheit", "lernspielzeug", "kinderbett",
      "babyausstattung", "spielzeug für kinder", "kinderrucksack", "schulranzen"],
     ["baby-kinder", "spielzeug"]),
    # Mode & Beauty
    (["schmuckset", "armband silber", "halskette", "ohrringe", "herrenuhr",
      "damenuhr", "sonnenbrillen", "kosmetik", "make up", "parfum",
      "haarpflege", "beauty set", "nagelpflege"],
     ["mode", "beauty"]),
    # Büro & Schreibtisch
    (["büro organisator", "schreibtischlampe", "monitor arm", "ergonomischer stuhl",
      "stehpult", "laptop ständer", "druckerkartusche", "papierschneider",
      "büroklammern", "notizbuch premium", "planer 2026"],
     ["büro", "home-office"]),
    # Beleuchtung
    (["led streifen", "led strip", "rgb licht", "nachtlicht", "tischlampe led",
      "stehlampe", "lichterkette", "smart beleuchtung", "ambient light"],
     ["beleuchtung", "smart-home"]),
    # Reinigung
    (["staubsauger", "akkusauger", "roboter sauger", "wischmopp", "dampfreiniger",
      "hochdruckreiniger", "fensterreiniger", "reinigungsset"],
     ["reinigung", "haushalt"]),
    # Werkzeug & DIY
    (["akkuschrauber", "bohrmaschine", "säge", "werkzeugkoffer", "heimwerker",
      "montageset", "dübel", "malerrolle", "tapezieren", "fugenmasse"],
     ["werkzeug", "diy"]),
    # Sicherheit
    (["alarmanlage", "bewegungsmelder", "türschloss smart", "sicherheitskamera outdoor",
      "tresör", "schloss elektronisch", "videoüberwachung"],
     ["sicherheit", "smart-home"]),
    # Gaming
    (["gaming headset", "gaming maus", "gaming tastatur", "controller ps5",
      "xbox controller", "nintendo switch", "gaming stuhl", "gaming monitor"],
     ["gaming", "tech"]),
    # Drohne & RC
    (["drohne", "drone", "quadcopter", "fpv brille", "ferngesteuert"],
     ["drohne", "tech", "gadget"]),
    # 3D Druck
    (["3d-drucker", "3d drucker", "filament pla", "resin drucker", "fdm drucker"],
     ["3d-druck", "tech"]),
    # Projektor
    (["beamer", "projektor", "mini beamer", "heimkino projektor", "led projektor"],
     ["projektor", "heimkino", "tech"]),
]

JUNK_TAGS = {"shopify automation", "shopify product import", "e-commerce automatisierung"}

# All category tags managed by this script — used to cleanly replace on re-run
MANAGED_TAGS: set[str] = {
    tag for _, tags in KEYWORD_TAGS for tag in tags
}


def classify_product(title: str, body: str) -> set[str]:
    text = (title + " " + body).lower()
    new_tags: set[str] = set()
    for keywords, tags in KEYWORD_TAGS:
        if any(kw in text for kw in keywords):
            new_tags.update(tags)
    return new_tags


def clean_tags(raw: str) -> set[str]:
    """Return tags, stripping junk tags AND managed category tags (so we re-apply cleanly)."""
    all_strip = JUNK_TAGS | MANAGED_TAGS
    return {t.strip() for t in raw.split(",") if t.strip() and t.strip().lower() not in all_strip}


def get_products(limit: int = 0) -> list[dict]:
    products = []
    url = f"{BASE}/products.json?limit=250&status=active&fields=id,title,tags,body_html"
    while url:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        batch = r.json().get("products", [])
        products.extend(batch)
        print(f"  Geladen: {len(products)}", end="\r", flush=True)

        link = r.headers.get("Link", "")
        url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.strip().split(";")[0].strip().strip("<>")
        time.sleep(DELAY)
        if limit and len(products) >= limit:
            products = products[:limit]
            break
    return products


def update_product_tags(product_id: int, new_tags_str: str) -> bool:
    r = requests.put(
        f"{BASE}/products/{product_id}.json",
        headers=HEADERS,
        json={"product": {"id": product_id, "tags": new_tags_str}},
        timeout=30,
    )
    return r.status_code == 200


def main():
    limit = 0
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])

    print(f"Shopify Tag Optimizer")
    print(f"Shop: {SHOP}")
    if limit:
        print(f"Limit: {limit} Produkte")
    print()
    print("Lade Produkte...")
    products = get_products(limit)
    print(f"\n{len(products)} Produkte geladen.\n")

    updated = 0
    skipped = 0
    errors = 0

    for i, p in enumerate(products):
        pid = p["id"]
        title = p.get("title", "")
        body = re.sub(r"<[^>]+>", "", p.get("body_html") or "")
        raw_tags = p.get("tags", "")

        # clean_tags strips both junk AND managed tags → fresh slate
        base_tags = clean_tags(raw_tags)
        new_category_tags = classify_product(title, body)

        combined = base_tags | new_category_tags

        # Rebuild what current state would be without junk/managed (to compare)
        old_managed = {t.strip().lower() for t in raw_tags.split(",") if t.strip().lower() in MANAGED_TAGS}
        if old_managed == new_category_tags and not ({t.strip().lower() for t in raw_tags.split(",") if t.strip()} & JUNK_TAGS):
            skipped += 1
            continue

        final_tags_str = ", ".join(sorted(combined))

        if update_product_tags(pid, final_tags_str):
            updated += 1
            if updated % 10 == 0 or i < 5:
                added = new_category_tags - old_managed
                print(f"[{updated}] {title[:55]}: +{len(added)} tags → {', '.join(sorted(added)[:4])}")
        else:
            errors += 1

        time.sleep(DELAY)

        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(products)} — updated={updated} skipped={skipped} errors={errors}")

    print()
    print(f"✅ FERTIG!")
    print(f"   Aktualisiert: {updated}")
    print(f"   Übersprungen: {skipped}")
    print(f"   Fehler: {errors}")
    print(f"   Smart Collections werden jetzt automatisch befüllt!")


if __name__ == "__main__":
    main()
