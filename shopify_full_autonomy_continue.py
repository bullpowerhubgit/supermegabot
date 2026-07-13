#!/usr/bin/env python3
"""
Shopify Full Autonomy — Continue Run
=====================================
Repariert alle Kaufblocker und ergänzt fehlende Inhalte.

Tasks (vollautomatisch, ohne KI-API):
  1. Inventory Policy Fix: alle "deny + qty=0" Varianten → "continue" (Dropshipping-Standard)
  2. SEO/Description Fill: alle Produkte ohne body_html → template-basierte Beschreibung
  3. CTA-Tags: fehlende "verfügbar" + "kauf-jetzt" Tags ergänzen
  4. Preischeck: Produkte mit Preis < 1 EUR flaggen + korrigieren
  5. Telegram-Bericht am Ende

Starten:
  python3 shopify_full_autonomy_continue.py
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SHOPIFY-AUTO] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ShopifyAuto")

# ── Config ────────────────────────────────────────────────────────────────────

for line in (Path(__file__).parent / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
API_VER = os.getenv("SHOPIFY_API_VERSION", "2024-10")
BASE    = f"https://{DOMAIN}/admin/api/{API_VER}"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}
TG_TKN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

# Rate limiting: Shopify REST = 2 req/s burst up to 40
SLEEP_BETWEEN = 0.55   # safe margin
SLEEP_429     = 8.0
MAX_RETRIES   = 5

# ── HTTP Helpers ──────────────────────────────────────────────────────────────

def _request(method: str, url: str, body: Optional[Dict] = None) -> Tuple[Dict, str]:
    data = json.dumps(body).encode() if body else None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
            resp = urllib.request.urlopen(req, timeout=25)
            link = resp.getheader("Link", "")
            return json.loads(resp.read()), link
        except urllib.error.HTTPError as e:
            if e.code == 429:
                log.warning("429 Rate Limit — warte %.1fs", SLEEP_429)
                time.sleep(SLEEP_429 * (attempt + 1))
                continue
            if e.code in (500, 503):
                time.sleep(3 * (attempt + 1))
                continue
            body_txt = e.read().decode(errors="ignore")[:200]
            log.error("HTTP %d: %s — %s", e.code, url[-60:], body_txt)
            return {}, ""
        except Exception as e:
            log.error("Fehler: %s", e)
            time.sleep(2 * (attempt + 1))
    return {}, ""


def shopify_get(path: str) -> Tuple[Dict, str]:
    url = path if path.startswith("http") else f"{BASE}{path}"
    d, link = _request("GET", url)
    time.sleep(SLEEP_BETWEEN)
    return d, link


def shopify_put(path: str, body: Dict) -> Dict:
    url = f"{BASE}{path}"
    d, _ = _request("PUT", url, body)
    time.sleep(SLEEP_BETWEEN)
    return d


def shopify_post(path: str, body: Dict) -> Dict:
    url = f"{BASE}{path}"
    d, _ = _request("POST", url, body)
    time.sleep(SLEEP_BETWEEN)
    return d


def tg(text: str):
    try:
        data = json.dumps({"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TKN}/sendMessage",
            data=data, headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=6)
    except Exception:
        pass


# ── Description Templates ─────────────────────────────────────────────────────

CATEGORY_MAP = {
    "solar":       ("Solaranlage & Energiespeicher",  "Solarmodul", "Energiespeicher", "Off-Grid"),
    "batterie":    ("Powerstation & Akku",            "Lithium-Akku", "Powerstation", "USV"),
    "wlan":        ("Smart-Home WLAN",                "WLAN-Modul", "App-steuerbar", "Alexa"),
    "schalter":    ("Smarter Schalter",               "Smarter Schalter", "App-steuerbar", "ZigBee"),
    "kamera":      ("Überwachungskamera",             "Full-HD Kamera", "Nachtsicht", "Bewegungserkennung"),
    "sensor":      ("Smart-Sensor",                   "Sensor", "Echtzeit-Alert", "App-Benachrichtigung"),
    "beleuchtung": ("Smart-Beleuchtung",              "LED", "Dimmbar", "RGB Farben"),
    "licht":       ("Smarte Beleuchtung",             "LED", "Warm/Kalt-Weiß", "Sprachsteuerung"),
    "steckdose":   ("Smarte Steckdose",               "Energiemessung", "Timer", "Remote-Control"),
    "thermostat":  ("Smarter Thermostat",             "Präzisionsregelung", "Energiesparmodus", "Wochenprogramm"),
    "heizung":     ("Heizungssteuerung",              "Thermostat", "Zeitplan", "Sprachsteuerung"),
    "roboter":     ("Saugroboter & Automatisierung",  "Auto-Navigation", "Selbstentleerung", "App-Steuerung"),
    "saug":        ("Saugroboter",                    "Laser-Navigation", "HEPA-Filter", "Automatisch"),
    "drohne":      ("Drohne & Kamera-UAV",            "GPS-Stabilisierung", "4K-Kamera", "Follow-Me"),
    "e-bike":      ("E-Bike & E-Mobilität",           "Elektromotor", "Reichweite bis 80km", "Lithium-Akku"),
    "fahrrad":     ("Fahrrad & E-Bike",               "Aluminium-Rahmen", "Shimano", "Hydraulische Bremsen"),
    "akku":        ("Akku & Batterie",                "Lithium-Ion", "Schnellladen", "Schutzschaltung"),
    "lautsprecher":("Smart-Speaker & Audio",          "HD-Audio", "Bluetooth 5.0", "Sprachsteuerung"),
    "display":     ("Smart-Display",                  "Touch-Display", "HD-Auflösung", "App-Integration"),
    "uhr":         ("Smartwatch & Fitness",           "Herzfrequenz", "GPS", "7 Tage Akku"),
    "watch":       ("Smartwatch",                     "Gesundheitsmonitoring", "Wasserdicht", "AMOLED"),
    "lock":        ("Smart-Lock & Sicherheit",        "Fingerprint", "App-Zugang", "Automatische Sperre"),
    "türschloss":  ("Smarter Türschloss",             "Fingerabdrucksensor", "Zahlencode", "NFC"),
    "kühlschrank": ("Smart-Kühlschrank",              "NoFrost", "Energieeffizienz A++", "Smart-Steuerung"),
    "waschmaschine":("Waschmaschine",                 "Inverter-Motor", "Energieklasse A", "15 Programme"),
    "luftreiniger":("Luftreiniger",                   "HEPA H13 Filter", "Pollen & Allergene", "Leise 25dB"),
    "klimaanlage": ("Klimaanlage",                    "Inverter", "WLAN-fähig", "Heizen & Kühlen"),
    "projektor":   ("Projektor",                      "Full-HD", "LED", "Heimkino"),
    "gaming":      ("Gaming",                         "Low Latency", "Hohe Auflösung", "RGB"),
    "keyboard":    ("Tastatur & Peripherie",          "Mechanisch", "RGB-Beleuchtung", "Anti-Ghosting"),
    "maus":        ("Gaming-Maus",                    "Hochpräzisions-Sensor", "Ergonomisch", "RGB"),
}

GENERIC_FEATURES = [
    "Hochwertige Materialien für maximale Langlebigkeit",
    "Einfache Einrichtung in wenigen Minuten",
    "Energieeffizient und umweltfreundlich",
    "Kompatibel mit gängigen Smart-Home-Systemen",
]

def _build_description(title: str, product_type: str = "", tags: str = "") -> str:
    text_lower = (title + " " + product_type + " " + tags).lower()
    cat_name   = "Smart Home Produkt"
    features   = GENERIC_FEATURES.copy()

    for key, (cname, f1, f2, f3) in CATEGORY_MAP.items():
        if key in text_lower:
            cat_name  = cname
            features  = [f1, f2, f3] + GENERIC_FEATURES[:2]
            break

    title_safe = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    feat_html  = "\n".join(f"<li>✅ {f}</li>" for f in features[:4])

    return (
        f"<p><strong>{title_safe}</strong> — {cat_name} für Ihr modernes Zuhause. "
        f"Überzeugende Technik, einfache Bedienung und zuverlässige Qualität "
        f"machen dieses Produkt zur perfekten Wahl für alle, die ihr Leben smarter gestalten möchten.</p>"
        f"<p><strong>Ihre Vorteile:</strong></p>"
        f"<ul>{feat_html}</ul>"
        f"<p>📦 <strong>Kostenloser Versand ab €55</strong> | "
        f"🔄 30 Tage Rückgabe | 🔒 SSL-gesicherter Kauf | ⭐ Geprüfte Qualität</p>"
    )


# ── Main Tasks ────────────────────────────────────────────────────────────────

def fix_inventory_policies() -> int:
    """Alle Varianten mit inventory_policy='deny' und qty<=0 auf 'continue' setzen."""
    log.info("Task 1: Inventory Policy Fix startet...")
    fixed = 0
    page  = 0

    url = f"{BASE}/products.json?limit=250&status=active&fields=id,title,variants"
    while url:
        data, link = shopify_get(url)
        products   = data.get("products", [])
        if not products:
            break

        for prod in products:
            for variant in prod.get("variants", []):
                pol = variant.get("inventory_policy", "continue")
                qty = int(variant.get("inventory_quantity") or 0)
                mgmt = variant.get("inventory_management")

                needs_fix = (pol == "deny" and qty <= 0) or (mgmt == "shopify" and qty <= 0)
                if needs_fix:
                    result = shopify_put(
                        f"/variants/{variant['id']}.json",
                        {"variant": {"id": variant["id"], "inventory_policy": "continue"}}
                    )
                    if result.get("variant"):
                        fixed += 1
                        if fixed % 50 == 0:
                            log.info("  Inventory Fix: %d korrigiert...", fixed)

        # Next page from Link header
        m = re.search(r'<([^>]+)>; rel="next"', link)
        url = m.group(1) if m else None
        page += 1
        if page % 10 == 0:
            log.info("Seite %d — %d Fixes bisher", page, fixed)

    log.info("Task 1 abgeschlossen: %d Varianten auf 'continue' gesetzt", fixed)
    return fixed


def fill_descriptions() -> int:
    """Produkte ohne Beschreibung mit template-basiertem HTML befüllen."""
    log.info("Task 2: Description Fill startet...")
    filled = 0

    url = f"{BASE}/products.json?limit=250&status=active&fields=id,title,body_html,product_type,tags"
    while url:
        data, link = shopify_get(url)
        products   = data.get("products", [])
        if not products:
            break

        for prod in products:
            if (prod.get("body_html") or "").strip():
                continue

            desc = _build_description(
                prod.get("title", "Produkt"),
                prod.get("product_type", ""),
                prod.get("tags", ""),
            )
            result = shopify_put(
                f"/products/{prod['id']}.json",
                {"product": {"id": prod["id"], "body_html": desc}}
            )
            if result.get("product"):
                filled += 1
                if filled % 25 == 0:
                    log.info("  Descriptions: %d ergänzt...", filled)

        m = re.search(r'<([^>]+)>; rel="next"', link)
        url = m.group(1) if m else None

    log.info("Task 2 abgeschlossen: %d Beschreibungen ergänzt", filled)
    return filled


def fix_prices() -> int:
    """Produkte mit Preis < €1 identifizieren und auf €9.99 setzen."""
    log.info("Task 3: Preisfix startet...")
    fixed = 0

    url = f"{BASE}/products.json?limit=250&status=active&fields=id,title,variants"
    while url:
        data, link = shopify_get(url)
        products   = data.get("products", [])
        if not products:
            break

        for prod in products:
            for v in prod.get("variants", []):
                price = float(v.get("price") or "0")
                if price < 1.0:
                    shopify_put(
                        f"/variants/{v['id']}.json",
                        {"variant": {"id": v["id"], "price": "9.99"}}
                    )
                    fixed += 1
                    log.info("Preis korrigiert: %s → €9.99", prod.get("title", "?")[:40])

        m = re.search(r'<([^>]+)>; rel="next"', link)
        url = m.group(1) if m else None

    log.info("Task 3 abgeschlossen: %d Preise korrigiert", fixed)
    return fixed


def add_cta_tags() -> int:
    """Produkten ohne 'newarrivals'-Tag CTA-Tags hinzufügen."""
    log.info("Task 4: CTA Tags startet...")
    tagged = 0

    url = f"{BASE}/products.json?limit=250&status=active&fields=id,title,tags"
    while url:
        data, link = shopify_get(url)
        products   = data.get("products", [])
        if not products:
            break

        for prod in products:
            existing = set(t.strip() for t in (prod.get("tags") or "").split(",") if t.strip())
            new_tags = set()
            if "cta-jetzt-kaufen" not in existing:
                new_tags.add("cta-jetzt-kaufen")
            if "verfuegbar" not in existing:
                new_tags.add("verfuegbar")

            if new_tags:
                all_tags = ", ".join(sorted(existing | new_tags))
                result = shopify_put(
                    f"/products/{prod['id']}.json",
                    {"product": {"id": prod["id"], "tags": all_tags}}
                )
                if result.get("product"):
                    tagged += 1

        m = re.search(r'<([^>]+)>; rel="next"', link)
        url = m.group(1) if m else None
        if tagged > 500:   # Cap: first 500 für diesen Run
            break

    log.info("Task 4 abgeschlossen: %d Tags ergänzt", tagged)
    return tagged


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    start = time.time()
    log.info("=" * 55)
    log.info("SHOPIFY FULL AUTONOMY CONTINUE — %s", datetime.now().strftime("%d.%m.%Y %H:%M"))
    log.info("=" * 55)

    tg(
        "🛍️ <b>Shopify Full Autonomy — CONTINUE</b>\n"
        f"Start: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        "4 Tasks werden ausgeführt...\n"
        "Inventar Fix · Beschreibungen · Preise · CTA-Tags"
    )

    results = {}

    # Task 1: Inventory Policy Fix (höchste Priorität — blockiert Käufe!)
    try:
        results["inv_fixed"] = fix_inventory_policies()
    except Exception as e:
        log.error("Task 1 Fehler: %s", e)
        results["inv_fixed"] = 0

    # Task 2: Description Fill
    try:
        results["desc_filled"] = fill_descriptions()
    except Exception as e:
        log.error("Task 2 Fehler: %s", e)
        results["desc_filled"] = 0

    # Task 3: Price Fix
    try:
        results["price_fixed"] = fix_prices()
    except Exception as e:
        log.error("Task 3 Fehler: %s", e)
        results["price_fixed"] = 0

    # Task 4: CTA Tags
    try:
        results["tags_added"] = add_cta_tags()
    except Exception as e:
        log.error("Task 4 Fehler: %s", e)
        results["tags_added"] = 0

    elapsed = int(time.time() - start)
    m, s    = divmod(elapsed, 60)

    summary = (
        f"✅ <b>Shopify Full Autonomy — ABGESCHLOSSEN</b>\n\n"
        f"⏱ Laufzeit: {m}m {s}s\n\n"
        f"📊 <b>Ergebnisse:</b>\n"
        f"  🔧 Inventory Fixes:      {results['inv_fixed']:>5}\n"
        f"  📝 Beschreibungen:       {results['desc_filled']:>5}\n"
        f"  💶 Preise korrigiert:    {results['price_fixed']:>5}\n"
        f"  🏷️ CTA-Tags gesetzt:     {results['tags_added']:>5}\n\n"
        f"🔗 Shop: ineedit.com.co"
    )

    log.info("\n" + summary.replace("<b>", "").replace("</b>", ""))
    tg(summary)
    log.info("FERTIG.")
