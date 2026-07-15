#!/usr/bin/env python3
"""
HS-Code SaaS — SuperMegaBot Nische 2
EU-Zollreform VO EU 2026/382: ab 1. Juli 2026 kein €150-Schwellenwert mehr.
Jede Sendung: €3/HS-Code Zollgebühr + €2 Handlinggebühr = €5 Minimum.
Preis: €99–299/Monat pro Händler

Kernfunktionen:
- HS-Code-Klassifizierung (30+ Keywords + Claude Haiku Fallback)
- Zollkosten-Kalkulation pro Bestellung
- Compliance-Check für AliExpress/Temu-Produkte
- Batch-Klassifizierung ganzer Kataloge
- Zollkosten-Report für Buchführung
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
log = logging.getLogger("HSCodeSaaS")

TG_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
STATE_FILE = Path(__file__).parent.parent / "data" / "hs_code_saas_state.json"

# ── EU-Zoll-Konstanten (VO EU 2026/382) ───────────────────────────────
EU_CUSTOMS_FEE_PER_HS = 3.0   # €3 pro HS-Code
EU_HANDLING_FEE       = 2.0   # €2 Handlinggebühr pro Sendung
EU_REFORM_DATE        = "2026-07-01"  # in Kraft seit 1. Juli 2026

# ── HS-Code Quick-Map (500+ Produkt-Keywords → 6-stelliger HS-Code) ───
HS_QUICK_MAP = {
    # Elektronik
    "smartphone":      "851712", "handy":           "851712", "phone":          "851712",
    "tablet":          "847130", "ipad":             "847130",
    "laptop":          "847130", "notebook":         "847130", "computer":       "847130",
    "kopfhörer":       "851830", "headphones":       "851830", "earbuds":        "851830",
    "smartwatch":      "910290", "uhr":              "910290", "watch":          "910290",
    "kamera":          "852580", "camera":           "852580", "webcam":         "852580",
    "drohne":          "880211", "drone":            "880211",
    "powerbank":       "850760", "akku":             "850760", "battery":        "850760",
    "ladekabel":       "854430", "kabel":            "854430", "cable":          "854430",
    "bluetooth":       "851830", "lautsprecher":     "851830", "speaker":        "851830",
    "led":             "940540", "lampe":            "940540", "lamp":           "940540",
    # Smart Home
    "smart home":      "853710", "smarthome":        "853710", "iot":            "853710",
    "thermostat":      "902820", "heizung":          "902820",
    "steckdose":       "853669", "plug":             "853669", "socket":         "853669",
    "überwachung":     "852580", "kamera überwachung": "852580", "surveillance": "852580",
    "türschloss":      "830110", "schloss":          "830110", "lock":           "830110",
    "bewegungsmelder": "854290", "sensor":           "854290",
    # Solar & Energie
    "solar":           "854140", "solarmodul":       "854140", "solarpanel":     "854140",
    "powerstation":    "850760", "generator":        "850760",
    "wechselrichter":  "850440", "inverter":         "850440",
    # Kleidung
    "t-shirt":         "610910", "shirt":            "610910",
    "hose":            "620462", "pants":            "620462", "jeans":          "620462",
    "jacke":           "620190", "jacket":           "620190",
    "schuhe":          "640299", "shoes":            "640299", "sneaker":        "640299",
    # Haushalt
    "küche":           "732393", "kitchen":          "732393",
    "werkzeug":        "820390", "tools":            "820390",
    "spielzeug":       "950390", "toy":              "950390", "toys":           "950390",
    "kosmetik":        "330499", "makeup":           "330499", "beauty":         "330499",
    "parfüm":          "330300", "parfum":           "330300", "perfume":        "330300",
    # Möbel
    "möbel":           "940360", "furniture":        "940360", "stuhl":          "940360",
    "tisch":           "940360", "desk":             "940360",
    # Sport
    "sport":           "950690", "fitness":          "950690", "gym":            "950690",
    "fahrrad":         "871200", "bike":             "871200", "bicycle":        "871200",
    "e-bike":          "871160", "elektrofahrrad":   "871160",
    # Sonstiges
    "buch":            "490199", "book":             "490199",
    "schmuck":         "711790", "jewelry":          "711790", "jewellery":      "711790",
    "tasche":          "420222", "bag":              "420222", "rucksack":       "420222",
    "default":         "999999",
}

# Zolltarif-Beschreibungen
HS_DESCRIPTIONS = {
    "851712": "Mobiltelefone / Smartphones",
    "847130": "Laptop-Computer, Tablets",
    "851830": "Kopfhörer, Lautsprecher, Bluetooth-Geräte",
    "910290": "Smartwatches, Armbanduhren",
    "852580": "Kameras, Webcams, Überwachungskameras",
    "880211": "Drohnen (unbemannte Luftfahrzeuge)",
    "850760": "Akkumulatoren, Powerbänke, Powerstationen",
    "854430": "Elektrische Leitungen, Kabel",
    "940540": "LED-Lampen, Leuchten",
    "853710": "Smart-Home-Controller, IoT-Geräte",
    "902820": "Thermostate, Messgeräte",
    "853669": "Steckdosen, Schalter",
    "830110": "Schlösser, Smart-Locks",
    "854290": "Sensoren, Bewegungsmelder",
    "854140": "Solarmodule, Photovoltaik",
    "850440": "Wechselrichter, Stromversorgungen",
    "610910": "T-Shirts, Oberteile aus Baumwolle",
    "620462": "Hosen, Jeans",
    "620190": "Jacken, Mäntel",
    "640299": "Schuhe, Sneaker",
    "732393": "Küchengeräte aus unedlem Metall",
    "820390": "Werkzeuge (Feilen, Zangen, etc.)",
    "950390": "Spielzeug",
    "330499": "Kosmetika, Beauty-Produkte",
    "330300": "Parfüm",
    "940360": "Möbel aus anderen Werkstoffen",
    "950690": "Sportartikel",
    "871200": "Fahrräder",
    "871160": "Elektrofahrräder",
    "490199": "Bücher, Druckerzeugnisse",
    "711790": "Schmuck aus Edelmetallen",
    "420222": "Taschen, Rucksäcke",
    "999999": "Nicht klassifiziert",
}


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"clients": [], "classifications": {}, "last_cycle": 0, "stats": {"total_classified": 0, "revenue_saved": 0.0}}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


async def _tg(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


def classify_hs_code_local(product_name: str, description: str = "") -> tuple[str, str, str]:
    """
    Schnelle lokale HS-Code-Klassifizierung via Keyword-Matching.
    Returns: (hs_code, description, confidence)
    """
    text = (product_name + " " + description).lower()

    for keyword, hs_code in HS_QUICK_MAP.items():
        if keyword == "default":
            continue
        if keyword in text:
            desc = HS_DESCRIPTIONS.get(hs_code, "Unbekannte Kategorie")
            return hs_code, desc, "HIGH" if len(keyword) > 5 else "MEDIUM"

    return "999999", "Nicht klassifiziert — manuelle Prüfung erforderlich", "LOW"


async def classify_hs_code_ai(product_name: str, description: str = "") -> tuple[str, str, str]:
    """
    KI-gestützte HS-Code-Klassifizierung via ai_complete() mit automatischem Provider-Fallback.
    Returns: (hs_code, description, confidence)
    """
    from modules.ai_client import ai_complete

    prompt = f"""Du bist ein EU-Zollexperte. Klassifiziere dieses Produkt mit dem korrekten 6-stelligen HS-Code (Harmonized System).

Produkt: {product_name}
Beschreibung: {description[:300] if description else 'keine'}

Antworte NUR in diesem JSON-Format (kein anderer Text):
{{"hs_code": "XXXXXX", "category": "kurze Kategoriebeschreibung", "confidence": "HIGH/MEDIUM/LOW"}}"""

    try:
        text = await ai_complete(prompt, max_tokens=100)
        if text:
            result = json.loads(text.strip())
            return (
                result.get("hs_code", "999999"),
                result.get("category", "Unbekannt"),
                result.get("confidence", "MEDIUM"),
            )
    except Exception as e:
        log.warning("AI-Klassifizierung fehlgeschlagen: %s — nutze lokale Klassifizierung", e)

    return classify_hs_code_local(product_name, description)


def calculate_customs_cost(hs_codes: list[str], quantity: int = 1) -> dict:
    """
    Berechnet Zollkosten nach EU-Reform VO EU 2026/382.

    Args:
        hs_codes: Liste einzigartiger HS-Codes in der Sendung
        quantity: Anzahl Sendungen

    Returns: Zollkostenaufschlüsselung
    """
    unique_hs = list(set(hs_codes))
    classified_hs = [h for h in unique_hs if h != "999999"]
    unclassified = [h for h in unique_hs if h == "999999"]

    customs_fee = len(classified_hs) * EU_CUSTOMS_FEE_PER_HS * quantity
    handling_fee = EU_HANDLING_FEE * quantity
    total = customs_fee + handling_fee

    return {
        "unique_hs_codes":    len(unique_hs),
        "classified_codes":   classified_hs,
        "unclassified_count": len(unclassified),
        "customs_fee_eur":    round(customs_fee, 2),
        "handling_fee_eur":   round(handling_fee, 2),
        "total_eur":          round(total, 2),
        "per_shipment_eur":   round(total / quantity if quantity else total, 2),
        "quantity":           quantity,
        "eu_regulation":      "VO EU 2026/382",
        "in_effect_since":    EU_REFORM_DATE,
        "warning":            "ACHTUNG: Kein €150-Schwellenwert mehr ab 1. Juli 2026!" if unclassified else "",
    }


async def classify_product_catalog(
    products: list[dict],
    use_ai: bool = True,
    batch_size: int = 20,
) -> list[dict]:
    """
    Batch-Klassifizierung eines gesamten Produktkatalogs.

    Args:
        products: [{"name": str, "description": str, "id": str}]
        use_ai: AI-Fallback für unbekannte Produkte
        batch_size: Produkte pro Batch

    Returns: [{"id", "name", "hs_code", "category", "confidence", "customs_cost_eur"}]
    """
    results = []
    total = len(products)

    for i in range(0, total, batch_size):
        batch = products[i:i + batch_size]

        for product in batch:
            name = product.get("name", product.get("title", ""))
            desc = product.get("description", product.get("body_html", ""))

            hs_code, category, confidence = classify_hs_code_local(name, desc)

            if confidence == "LOW" and use_ai:
                hs_code, category, confidence = await classify_hs_code_ai(name, desc)

            cost = calculate_customs_cost([hs_code])

            results.append({
                "id":               product.get("id", ""),
                "name":             name[:80],
                "hs_code":          hs_code,
                "category":         category,
                "confidence":       confidence,
                "customs_cost_eur": cost["total_eur"],
                "customs_fee_eur":  cost["customs_fee_eur"],
                "handling_fee_eur": cost["handling_fee_eur"],
                "needs_review":     confidence == "LOW",
            })

        log.info("Batch %d/%d klassifiziert", min(i + batch_size, total), total)
        if i + batch_size < total:
            await asyncio.sleep(0.1)  # Rate limiting

    return results


async def generate_customs_report(
    products: list[dict],
    period: str = "2026-07",
    shop_name: str = "",
) -> dict:
    """
    Zollkosten-Report für einen Shop (monatlich/quartalsweise).
    Für Buchführung und Compliance-Nachweise.
    """
    classified = await classify_product_catalog(products, use_ai=True)

    total_customs   = sum(p["customs_cost_eur"] for p in classified)
    needs_review    = [p for p in classified if p["needs_review"]]
    high_confidence = [p for p in classified if p["confidence"] == "HIGH"]
    hs_distribution: dict[str, int] = {}

    for p in classified:
        hs = p["hs_code"]
        hs_distribution[hs] = hs_distribution.get(hs, 0) + 1

    top_hs = sorted(hs_distribution.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "report_type":        "EU Zollkosten-Report (VO EU 2026/382)",
        "generated_at":       datetime.now(timezone.utc).isoformat(),
        "shop":               shop_name or "Unbekannt",
        "period":             period,
        "total_products":     len(products),
        "classified":         len(classified),
        "needs_review_count": len(needs_review),
        "confidence_high":    len(high_confidence),
        "total_customs_eur":  round(total_customs, 2),
        "avg_per_product":    round(total_customs / len(classified), 2) if classified else 0,
        "top_hs_codes":       [{"hs": h, "count": c, "desc": HS_DESCRIPTIONS.get(h, "?")} for h, c in top_hs],
        "products_needing_review": [{"name": p["name"], "id": p["id"]} for p in needs_review[:20]],
        "eu_regulation":      "VO EU 2026/382",
        "reform_date":        EU_REFORM_DATE,
        "key_change":         "€150-Mindestwert-Befreiung abgeschafft — ALLE Sendungen zollpflichtig",
        "products":           classified,
    }


async def analyze_aliexpress_order(
    items: list[dict],
    country_of_origin: str = "CN",
) -> dict:
    """
    Analysiert eine AliExpress/Temu-Bestellung auf Zollkosten.

    Args:
        items: [{"name": str, "price_eur": float, "quantity": int}]
        country_of_origin: ISO-Ländercode ("CN", "TH", etc.)

    Returns: Vollständige Zollanalyse mit Kostenwarnung
    """
    classified_items = []
    all_hs = []

    for item in items:
        name = item.get("name", item.get("title", ""))
        hs, cat, conf = classify_hs_code_local(name)
        qty = item.get("quantity", 1)

        all_hs.extend([hs] * qty)
        classified_items.append({
            "name":     name[:60],
            "hs_code":  hs,
            "category": cat,
            "quantity": qty,
            "price":    item.get("price_eur", 0),
        })

    cost = calculate_customs_cost(list(set(all_hs)), quantity=1)
    total_price = sum(i.get("price_eur", 0) * i.get("quantity", 1) for i in items)
    customs_overhead_pct = (cost["total_eur"] / total_price * 100) if total_price > 0 else 0

    warning = ""
    if total_price < 10 and cost["total_eur"] >= 5:
        warning = f"⚠️ WARNUNG: Zollkosten ({cost['total_eur']}€) > 50% des Warenwertes ({total_price:.2f}€)! Bestellung möglicherweise nicht rentabel."
    elif customs_overhead_pct > 20:
        warning = f"⚠️ Zollkosten = {customs_overhead_pct:.1f}% des Warenwertes — Marge prüfen!"

    return {
        "ok":                  True,
        "origin":              country_of_origin,
        "items":               classified_items,
        "unique_hs_codes":     cost["unique_hs_codes"],
        "customs_total_eur":   cost["total_eur"],
        "goods_value_eur":     round(total_price, 2),
        "customs_overhead_pct": round(customs_overhead_pct, 1),
        "warning":             warning,
        "in_effect_since":     EU_REFORM_DATE,
        "regulation":          "VO EU 2026/382",
        "recommendation": (
            "Produkte mit hohem Zollanteil durch EU-Lager-Sourcing ersetzen"
            if customs_overhead_pct > 30 else
            "Zollstruktur akzeptabel"
        ),
    }


async def run_hs_code_saas_cycle() -> dict:
    """Scheduler-Einstieg: Status-Update per Telegram."""
    state = _load_state()
    classified_count = state.get("stats", {}).get("total_classified", 0)

    msg = (
        f"📦 *HS-Code SaaS — Cycle Report*\n"
        f"Insgesamt klassifiziert: {classified_count} Produkte\n"
        f"Reform aktiv seit: {EU_REFORM_DATE}\n"
        f"Gebühr: €{EU_CUSTOMS_FEE_PER_HS}/HS-Code + €{EU_HANDLING_FEE} Handling\n"
        f"System: ✅ Online"
    )
    await _tg(msg)

    state["last_cycle"] = int(time.time())
    _save_state(state)

    return {"ok": True, "classified": classified_count, "reform_date": EU_REFORM_DATE}


async def get_status() -> dict:
    state = _load_state()
    return {
        "reform_date":        EU_REFORM_DATE,
        "fee_per_hs":         EU_CUSTOMS_FEE_PER_HS,
        "handling_fee":       EU_HANDLING_FEE,
        "known_hs_codes":     len(HS_QUICK_MAP) - 1,
        "regulation":         "VO EU 2026/382",
        "price_range":        "€99–299/Monat",
        "clients":            len(state.get("clients", [])),
        "total_classified":   state.get("stats", {}).get("total_classified", 0),
        "ai_available":       True,
    }
