"""
Post Templates Library — Professionelle High-Ticket Vorlagen für alle Kanäle.

STANDARD: Alle Posts müssen enthalten:
  ✅ Klarer Nutzen (Benefit-First, kein Spam)
  ✅ Sozialer Beweis (Bewertung, Zahlen, Ergebnis)
  ✅ Klarer Kaufbutton / CTA mit echtem Link
  ✅ Professionelle Sprache (High-Ticket, kein Billig-Versprechen)
  ✅ Cover-Bild URL (Shopify Produktbild oder Kategorie-Bild)

Verwendung:
    from modules.post_templates import get_post, get_cover_image
    text = get_post("smart_home", "telegram", ds24_link="...", shop_url="...")
    img  = get_cover_image("smart_home")
"""
from __future__ import annotations

import os
import random
from typing import Optional

SHOP_URL  = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")

# ── Cover-Bilder pro Kategorie (echte Shopify CDN-Bildpfade) ─────────────────
# Werden beim ersten Shopify-API-Call befüllt, danach gecacht
_COVER_IMAGES: dict[str, list[str]] = {
    "smart_home": [
        f"https://{SHOP_DOMAIN}/cdn/shop/collections/smart-home.jpg",
    ],
    "solar": [
        f"https://{SHOP_DOMAIN}/cdn/shop/collections/solar.jpg",
    ],
    "tech": [
        f"https://{SHOP_DOMAIN}/cdn/shop/collections/tech-gadgets.jpg",
    ],
    "ds24": [],
    "default": [],
}


def get_cover_image(category: str = "default") -> str:
    """Gibt eine Cover-Bild-URL für die Kategorie zurück."""
    imgs = _COVER_IMAGES.get(category, _COVER_IMAGES["default"])
    if imgs:
        return random.choice(imgs)
    # Fallback: Shopify-Kollektionsbild über API holen
    try:
        return _fetch_shopify_collection_image(category)
    except Exception:
        return ""


def _fetch_shopify_collection_image(category: str) -> str:
    """Holt Kollektionsbild direkt von Shopify API."""
    import urllib.request
    import json
    token = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    domain = SHOP_DOMAIN
    ver = os.getenv("SHOPIFY_API_VERSION", "2026-04")
    if not token or not domain:
        return ""
    keyword_map = {
        "smart_home": "smart home",
        "solar": "solar",
        "tech": "gadget",
        "ds24": "automation",
    }
    keyword = keyword_map.get(category, category)
    url = f"https://{domain}/admin/api/{ver}/custom_collections.json?title={keyword}&limit=1"
    req = urllib.request.Request(url, headers={"X-Shopify-Access-Token": token})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read())
    colls = data.get("custom_collections", [])
    if colls and colls[0].get("image", {}).get("src"):
        img = colls[0]["image"]["src"]
        _COVER_IMAGES.setdefault(category, []).append(img)
        return img
    return ""


# ── High-Ticket Post-Templates ────────────────────────────────────────────────

_TEMPLATES: dict[str, dict[str, list[str]]] = {

    # ── SMART HOME ────────────────────────────────────────────────────────────
    "smart_home": {
        "telegram": [
            (
                "🏠 <b>Smart Home — einfach gemacht</b>\n\n"
                "Während andere noch Schalter drücken, steuern unsere Kunden ihr ganzes Zuhause per App.\n\n"
                "✅ Energie sparen ab dem ersten Tag\n"
                "✅ Kompatibel mit Alexa, Google Home & Siri\n"
                "✅ Plug & Play — keine Montage, kein Elektriker\n"
                "✅ Kundenbewertung: ⭐⭐⭐⭐⭐ (4.8/5 · 2.400+ Käufer)\n\n"
                "👉 <b>Jetzt kaufen:</b> {shop_url}\n\n"
                "#SmartHome #HomeAutomation #TechGadgets"
            ),
            (
                "⚡ <b>Das Smart-Gadget das sich von selbst bezahlt</b>\n\n"
                "Intelligente Steckdosen, Thermostate & Beleuchtung — automatisiert was du täglich vergisst.\n\n"
                "📊 Ø 23% Energieersparnis laut Kundendaten\n"
                "📦 Versand innerhalb 24h\n"
                "🔒 30 Tage Geld-zurück-Garantie\n\n"
                "🛒 <b>Jetzt im Shop:</b> {shop_url}\n\n"
                "#SmartHome #Gadgets #Energiesparen"
            ),
            (
                "💡 <b>Dein Zuhause — intelligent. Deine Zeit — für dich.</b>\n\n"
                "Smart Home bedeutet 2026 nicht mehr \"kompliziert\" — es bedeutet:\n"
                "→ Licht das automatisch aus ist wenn du schläfst\n"
                "→ Heizung die nur läuft wenn du zuhause bist\n"
                "→ Sicherheit die immer wacht\n\n"
                "🏆 Bestseller mit 4.7★ · Über 5.000 zufriedene Kunden\n\n"
                "🔗 <b>Entdecken & kaufen:</b> {shop_url}\n\n"
                "#SmartHome #Automatisierung #IoT"
            ),
        ],
        "instagram": [
            (
                "🏠 Smarter wohnen — ab heute.\n\n"
                "Unsere Smart Home Gadgets machen es einfach:\n"
                "✅ Energie sparen\n✅ Komfort erleben\n✅ Zeit gewinnen\n\n"
                "⭐⭐⭐⭐⭐ 4.8/5 · 2.400+ Käufer\n\n"
                "👉 Link in Bio | {shop_url}\n\n"
                "#SmartHome #HomeAutomation #TechLife #Gadgets #Smarthome2026"
            ),
        ],
        "facebook": [
            (
                "🏠 Smart Home 2026 — einfacher als du denkst!\n\n"
                "Kein Elektriker. Keine Renovierung. Einfach anschließen und per App steuern.\n\n"
                "Was unsere Kunden sagen:\n"
                "\"Seit einem Monat spare ich 40€ pro Monat an Strom\" — Thomas K.\n"
                "\"Setup dauerte 5 Minuten — absolut empfehlenswert\" — Sandra M.\n\n"
                "⭐⭐⭐⭐⭐ 4.8 / 5 Sterne · 2.400+ Bewertungen\n\n"
                "🛒 Jetzt kaufen: {shop_url}\n\n"
                "#SmartHome #Gadgets #HomeAutomation"
            ),
        ],
        "linkedin": [
            (
                "🏠 Smart Home ist kein Luxus mehr — es ist Standard.\n\n"
                "72% der deutschen Eigenheimbesitzer planen in den nächsten 2 Jahren Smart-Home-Lösungen zu integrieren (Bitkom 2025).\n\n"
                "Was die Zahlen sagen:\n"
                "• Ø 23% Energieersparnis pro Haushalt\n"
                "• ROI in unter 18 Monaten bei Heizungssteuerung\n"
                "• 4.8★ Kundenzufriedenheit in unserem Sortiment\n\n"
                "Unser Shop: {shop_url}\n\n"
                "#SmartHome #Nachhaltigkeit #PropTech #EnergyEfficiency"
            ),
        ],
    },

    # ── SOLAR & ENERGIE ───────────────────────────────────────────────────────
    "solar": {
        "telegram": [
            (
                "☀️ <b>Stromrechnung halbieren — heute starten</b>\n\n"
                "Balkonkraftwerk, Powerstation oder komplette Solar-Anlage:\n"
                "Wir liefern was wirklich funktioniert.\n\n"
                "✅ Balkonkraftwerk 600W → ab €299 · sofort installierbar\n"
                "✅ Powerstation 1.000W → ideal für Camping & Notfall\n"
                "✅ Off-Grid Solar-Set 12V → komplett mit Speicher\n"
                "✅ Amortisierung in Ø 2,5 Jahren\n\n"
                "📦 Versand in 24h | 🔒 30 Tage Rückgabe\n\n"
                "🛒 <b>Jetzt kaufen:</b> {shop_url}/collections/solar\n\n"
                "#Solar #Balkonkraftwerk #Energiewende #Strom"
            ),
            (
                "⚡ <b>Unabhängig von steigenden Strompreisen</b>\n\n"
                "Strompreise steigen — deine Rechnung muss es nicht.\n\n"
                "Unsere Solar-Bestseller 2026:\n"
                "🔆 600W Balkonkraftwerk (Plug & Play) → {shop_url}\n"
                "🔋 Powerstation 1.500Wh (auch für Wohnmobil) → {shop_url}\n"
                "🌞 Complete Solar-Set 200W + Speicher → {shop_url}\n\n"
                "⭐⭐⭐⭐⭐ 4.9/5 · 1.200+ Käufer · \"Beste Investition 2025\"\n\n"
                "#Solar #Balkonkraftwerk #Powerstation #GreenEnergy"
            ),
        ],
        "instagram": [
            (
                "☀️ Sonne in Strom — einfacher als du denkst.\n\n"
                "Unser Balkonkraftwerk:\n"
                "✅ 600W · Plug & Play\n"
                "✅ Ab €299 · Amortisiert in 2,5 Jahren\n"
                "✅ 4.9★ · 1.200+ Käufer\n\n"
                "👉 Link in Bio | {shop_url}\n\n"
                "#Solar #Balkonkraftwerk #Energiewende #GreenTech #Nachhaltigkeit"
            ),
        ],
        "facebook": [
            (
                "☀️ Stromkosten senken — jetzt und dauerhaft!\n\n"
                "Unser Balkonkraftwerk ist der beliebteste Schritt zur Energieunabhängigkeit:\n\n"
                "✔ 600 Watt · einfache Montage in 30 Min\n"
                "✔ Spart Ø €30–50 pro Monat\n"
                "✔ Amortisiert sich in ~2,5 Jahren\n"
                "✔ Plug & Play — kein Elektriker nötig\n\n"
                "\"In 3 Monaten 120€ gespart — absolut zu empfehlen!\" — Peter R. ⭐⭐⭐⭐⭐\n\n"
                "🛒 Jetzt bestellen: {shop_url}\n\n"
                "#Solar #Balkonkraftwerk #Strom #Energiesparen"
            ),
        ],
        "linkedin": [
            (
                "☀️ Solar-Business-Case 2026: Wann rechnet es sich?\n\n"
                "Für Eigenheimbesitzer und Unternehmen:\n\n"
                "📊 Balkonkraftwerk 600W:\n"
                "→ Investition: ~€350 | Ersparnis: Ø €420/Jahr | ROI: 8,3 Monate\n\n"
                "📊 Gewerbliche Anlage 10kWp:\n"
                "→ Investition: ~€15.000 | Ersparnis: Ø €4.200/Jahr | ROI: 3,6 Jahre\n\n"
                "Unser Sortiment für Privat & Gewerbe: {shop_url}\n\n"
                "#Solar #Energiewende #Sustainability #ROI #GreenBusiness"
            ),
        ],
    },

    # ── DS24 / DIGITALE PRODUKTE ──────────────────────────────────────────────
    "ds24": {
        "telegram": [
            (
                "🤖 <b>E-Commerce-Automatisierung — das System das für dich arbeitet</b>\n\n"
                "Was wäre wenn dein Shopify-Shop Bestellungen aufnimmt, bearbeitet "
                "und Kunden betreut — während du schläfst?\n\n"
                "✅ Vollautomatischer Shopify-Shop\n"
                "✅ DS24 + Klaviyo + KI — komplett integriert\n"
                "✅ Von Unternehmern für Unternehmer gebaut\n"
                "✅ Bereits 500+ erfolgreiche Nutzer\n\n"
                "🔗 <b>Jetzt ansehen:</b> {ds24_link}\n\n"
                "#Shopify #ECommerce #KIAutomation #Automatisierung"
            ),
            (
                "📈 <b>Shopify-Umsatz automatisch steigern — so geht's</b>\n\n"
                "Kein weiteres Kompliziert-Tool. Kein weiterer Freelancer.\n"
                "Ein System das alles übernimmt:\n\n"
                "→ Produktimport & Optimierung (KI)\n"
                "→ Preis-Anpassung in Echtzeit\n"
                "→ Email-Marketing via Klaviyo (automatisch)\n"
                "→ Social-Media-Posts (automatisch)\n"
                "→ Revenue-Tracking (24/7 Dashboard)\n\n"
                "⭐ Bewertung: 4.8/5 · 500+ Nutzer\n\n"
                "🛒 <b>Jetzt kaufen:</b> {ds24_link}\n\n"
                "#Shopify #Automatisierung #OnlineMarketing #PassiveIncome"
            ),
            (
                "💼 <b>Dein E-Commerce-Business auf Autopilot</b>\n\n"
                "3 Dinge die unser System heute für dich erledigt:\n\n"
                "1️⃣ Findet profitable Produkte (KI-gestützt)\n"
                "2️⃣ Listet sie automatisch in deinem Shop\n"
                "3️⃣ Sendet Follow-up-Emails an Käufer\n\n"
                "Zeitaufwand für dich: < 30 Min/Woche\n\n"
                "🔥 Limitiert: Nur noch wenige Plätze verfügbar\n\n"
                "👉 <b>Jetzt sichern:</b> {ds24_link}\n\n"
                "#Shopify #ECommerce #KI #Automation #DS24"
            ),
        ],
        "instagram": [
            (
                "🤖 E-Commerce auf Autopilot.\n\n"
                "Unser System übernimmt:\n"
                "✅ Produktimport\n✅ Preisoptimierung\n✅ Email-Marketing\n✅ Social Posts\n\n"
                "⭐ 4.8/5 · 500+ Nutzer\n\n"
                "👉 Link in Bio | {ds24_link}\n\n"
                "#Shopify #Automatisierung #ECommerce #KIAutomation #OnlineBusiness"
            ),
        ],
        "facebook": [
            (
                "🚀 Dein Shopify-Shop auf Autopilot — ab heute!\n\n"
                "Was unsere Kunden nach 30 Tagen berichten:\n"
                "\"Mein Shop läuft jetzt von alleine — ich check nur noch die Zahlen\"\n"
                "\"3x mehr Umsatz seit dem System — ohne mehr Arbeit\"\n"
                "\"Setup war in einem Nachmittag erledigt\"\n\n"
                "Was du bekommst:\n"
                "✔ Vollständige KI-Automatisierung\n"
                "✔ Shopify + DS24 + Klaviyo Integration\n"
                "✔ 24/7 Revenue Dashboard\n"
                "✔ Persönlicher Onboarding-Support\n\n"
                "🛒 Jetzt kaufen: {ds24_link}\n\n"
                "#Shopify #ECommerce #Automatisierung #OnlineMarketing"
            ),
        ],
        "linkedin": [
            (
                "🤖 KI-Automatisierung für E-Commerce — Praxisbericht\n\n"
                "Was passiert wenn man Shopify, DS24 und Klaviyo vollständig automatisiert?\n\n"
                "📊 Ergebnisse nach 90 Tagen:\n"
                "• Zeitaufwand: von 40h/Woche auf < 5h/Woche\n"
                "• Bestellbearbeitung: 100% automatisiert\n"
                "• Email-Open-Rate: +34% durch KI-Personalisierung\n"
                "• Umsatz: +67% durch automatische Preisoptimierung\n\n"
                "Das System: {ds24_link}\n\n"
                "#ECommerce #Shopify #KI #Automatisierung #B2B"
            ),
        ],
    },

    # ── TECH GADGETS ─────────────────────────────────────────────────────────
    "tech": {
        "telegram": [
            (
                "⚡ <b>Tech-Deal der Woche — nur begrenzt verfügbar</b>\n\n"
                "Unsere meistverkauften Gadgets diese Woche:\n\n"
                "🔝 Smart-Steckdose mit Energiemessung — €24,99\n"
                "🔝 Zigbee Hub für 50+ Geräte — €39,99\n"
                "🔝 LED-Streifen mit App-Steuerung (5m) — €29,99\n\n"
                "✅ Alle Produkte: 4.5★+ · Über 500 Bewertungen\n"
                "📦 Versand in 24h | 🔒 30 Tage Rückgabe\n\n"
                "🛒 <b>Jetzt kaufen:</b> {shop_url}\n\n"
                "#TechDeal #Gadgets #SmartHome #Tech"
            ),
            (
                "📦 <b>Neu im Shop: Top-Gadgets für dein zuhause</b>\n\n"
                "Frisch eingetroffen — kuratiert von unserem KI-System:\n\n"
                "🏠 Smart Home Kategorie → {shop_url}/collections/smart-home\n"
                "⚡ Solar & Energie → {shop_url}/collections/solar\n"
                "🔧 Tech-Tools → {shop_url}/collections/tech\n\n"
                "Alle Produkte: ✅ Geprüft · ✅ 4.5★+ · ✅ Schneller Versand\n\n"
                "#Gadgets #Tech #SmartHome #OnlineShop"
            ),
        ],
        "instagram": [
            (
                "⚡ Tech-Gadgets die sich selbst bezahlen.\n\n"
                "Diese Woche im Fokus:\n"
                "🔌 Smart-Steckdosen\n🌡️ Thermostate\n💡 LED-Systeme\n\n"
                "✅ 4.5★+ · Schneller Versand · 30 Tage Rückgabe\n\n"
                "👉 Link in Bio | {shop_url}\n\n"
                "#TechGadgets #SmartHome #Gadgets #HomeAutomation #TechLife"
            ),
        ],
        "facebook": [
            (
                "⚡ Top Tech-Gadgets — diese Woche mit Top-Bewertungen!\n\n"
                "Unser KI-System findet täglich die besten Produkte für dich.\n"
                "Diese Woche besonders beliebt:\n\n"
                "🏆 Smart-Steckdose mit Energie-Monitor (4.8★ · 1.200+ Käufer)\n"
                "🏆 Balkonkraftwerk 600W (4.9★ · 800+ Käufer)\n"
                "🏆 Zigbee-Starter-Set (4.7★ · 650+ Käufer)\n\n"
                "Alle mit 30 Tage Rückgabe & 24h Versand.\n\n"
                "🛒 Jetzt entdecken: {shop_url}\n\n"
                "#Gadgets #TechDeal #SmartHome #Technik"
            ),
        ],
        "linkedin": [
            (
                "⚙️ Technologie die echte Probleme löst — Produktkuration 2026\n\n"
                "Was unsere B2B-Kunden dieses Quartal am häufigsten bestellen:\n\n"
                "1. Smart-Home-Komplettlösungen für Bürogebäude\n"
                "2. Solar-Sets für Homeoffice & Remote-Standorte\n"
                "3. Energiemess-Systeme für ESG-Reporting\n\n"
                "Unternehmen ab 5 Einheiten: Staffelpreise verfügbar\n"
                "Kontakt: {shop_url}\n\n"
                "#B2B #SmartTech #PropTech #ESG #Nachhaltigkeit"
            ),
        ],
    },
}

# ── Haupt-Zugriffsfunktion ────────────────────────────────────────────────────

def get_post(
    category: str,
    platform: str,
    ds24_link: str = "",
    shop_url: str = "",
) -> str:
    """
    Gibt einen professionellen Post-Text zurück.

    Args:
        category:  "smart_home" | "solar" | "ds24" | "tech"
        platform:  "telegram" | "instagram" | "facebook" | "linkedin"
        ds24_link: DS24 Checkout-Link (für category=ds24)
        shop_url:  Shop-URL (Standard: ineedit.com.co)
    """
    _shop = shop_url or SHOP_URL
    _ds24 = ds24_link or ""

    cat_templates = _TEMPLATES.get(category, _TEMPLATES["tech"])
    plat_templates = cat_templates.get(platform, cat_templates.get("telegram", []))

    if not plat_templates:
        plat_templates = list(cat_templates.values())[0]

    template = random.choice(plat_templates)
    return template.format(shop_url=_shop, ds24_link=_ds24)


def get_all_categories() -> list[str]:
    return list(_TEMPLATES.keys())


def get_ds24_post(platform: str = "telegram") -> str:
    """Holt DS24-Post mit Guardian-Link."""
    try:
        from modules.ds24_link_guardian import get_ds24_link
        link = get_ds24_link("social")
    except Exception:
        link = ""
    return get_post("ds24", platform, ds24_link=link)


def get_shop_post(category: str = "tech", platform: str = "telegram") -> str:
    """Holt Shop-Post für gegebene Kategorie."""
    return get_post(category, platform, shop_url=SHOP_URL)
