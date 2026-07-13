#!/usr/bin/env python3
"""
Shopify Daily Healer — autonomer Scheduler-Task
================================================
Läuft täglich via AutomationScheduler.
Kein manueller Start nötig — vollständig autonom.

Heilt:
  1. Inventory Policy: "deny + qty≤0" → "continue" (Dropshipping-Pflicht)
  2. Fehlende Beschreibungen → template-basiertes SEO-HTML
  3. Preis < €1 → €9.99 (kaufblockiert)
  4. Fehlende product_type → aus Tags ableiten
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import urllib.request
from typing import Dict, Optional, Tuple

log = logging.getLogger("ShopifyHealer")

# ── API Config ─────────────────────────────────────────────────────────────────

def _creds() -> Tuple[str, str, str]:
    domain  = os.getenv("SHOPIFY_SHOP_DOMAIN",       "autopilot-store-suite-fmbka.myshopify.com")
    token   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    version = os.getenv("SHOPIFY_API_VERSION",        "2026-04")
    return domain, token, version


SLEEP_OK  = 0.55
SLEEP_429 = 8.0
MAX_RETRY = 4

# ── Category Templates ─────────────────────────────────────────────────────────

_CAT = {
    "solar":       ("Solar & Energie",          ["Solarmodul",       "Energiespeicher",    "Off-Grid System",   "Wirkungsgrad >20%"]),
    "powerstation":("Powerstation & Akku",      ["Lithium-Ion Akku", "2000W Leistung",     "Schnellladen",      "Notstrom Ready"]),
    "batterie":    ("Akku & Batterie",           ["Hohe Kapazität",   "Zyklenfest",         "BMS-Schutz",        "12V/24V kompatibel"]),
    "wlan":        ("WLAN Smart Home",           ["WLAN 2.4/5 GHz",  "App-steuerbar",      "Alexa/Google",      "Automatisierung"]),
    "schalter":    ("Smarter Schalter",          ["1-10 Schalter",    "ZigBee/WLAN",        "Kein Neutral nötig","Touch-Bedienung"]),
    "kamera":      ("Überwachungskamera",        ["2K Full HD",       "Nachtsicht 10m",     "Bewegungsalarm",    "Wetterfest IP66"]),
    "sensor":      ("Smart-Sensor",              ["Echtzeit-Messung", "App-Benachrichtigung","Batteriebetrieb",  "ZigBee/BLE"]),
    "licht":       ("Smart-Beleuchtung",         ["16 Mio. Farben",   "Dimmbar 1-100%",     "Warm/Kalt 2700-6500K","Sprachsteuerung"]),
    "beleuchtung": ("LED Beleuchtung",           ["A++ Effizienz",    "50.000h Lebensdauer","Flackerfrei",       "Instant-On"]),
    "steckdose":   ("Smarte Steckdose",          ["Energiemessung",   "2300W max.",         "Timer & Zeitplan",  "Überlastschutz"]),
    "thermostat":  ("Smart-Thermostat",          ["0.5°C Genauigkeit","Wochenprogramm",     "Energiesparmodus",  "WLAN-Steuerung"]),
    "heizung":     ("Heizungssteuerung",         ["Thermostat",       "PID-Regelung",       "Google Home",       "Offenes Fenster Erkennung"]),
    "roboter":     ("Saugroboter",               ["3D-Lidar-Navigation","Selbstentleerung", "HEPA H13",          "3500 Pa Saugkraft"]),
    "drohne":      ("Drohne & UAV",              ["GPS-Stabilisierung","4K 30fps",          "Windresistenz 8m/s","Return-to-Home"]),
    "e-bike":      ("E-Bike & E-Mobilität",      ["250W Motor",       "36V 10Ah Akku",      "80km Reichweite",   "Shimano 7-Gang"]),
    "akku":        ("Portable Powerbank",        ["20.000 mAh",       "65W PD Schnellladen","USB-C/A Dual",      "LED-Anzeige"]),
    "lautsprecher":("Smart-Speaker",             ["360° Sound",       "Bluetooth 5.3",      "Sprachassistent",   "8h Akku"]),
    "uhr":         ("Smartwatch",                ["AMOLED 1.43\"",    "7 Tage Akku",        "Herzfrequenz/SpO2", "IP68 Wasserdicht"]),
    "lock":        ("Smart-Lock",                ["Fingerprint 0.3s", "Zahlencode",         "App-Zugang",        "NFC-Karte"]),
    "luftreiniger":("Luftreiniger",              ["HEPA H13",         "Aktivkohlefilter",    "25 dB leise",       "500m³/h Luftmenge"]),
    "projektor":   ("Heimkino Projektor",        ["1080p Full HD",    "4000 Ansi Lumen",    "Keystone ±45°",     "HDMI/USB"]),
    "gaming":      ("Gaming Hardware",           ["RGB Beleuchtung",  "Hochpräzisions-Sensor","Makro-Tasten",    "Anti-Ghosting"]),
}

_GENERIC = ["Smart-Technologie", "Energieeffizient", "Einfache App-Steuerung", "Geprüfte Qualität"]


def _build_desc(title: str, ptype: str = "", tags: str = "") -> str:
    haystack = (title + " " + ptype + " " + tags).lower()
    cat_name = "Smart Home Produkt"
    features = _GENERIC

    for kw, (cname, feats) in _CAT.items():
        if kw in haystack:
            cat_name = cname
            features = feats
            break

    t = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    fl = "\n".join(f"<li>✅ {f}</li>" for f in features)

    return (
        f"<p><strong>{t}</strong> — {cat_name} für das moderne Zuhause. "
        f"Durchdachte Technik, unkomplizierte Bedienung und überzeugender Mehrwert "
        f"— die ideale Wahl für smarte Käufer.</p>"
        f"<ul>{fl}</ul>"
        f"<p>📦 <strong>Kostenloser Versand ab €55</strong> · "
        f"🔄 30 Tage Rückgabe · 🔒 SSL-gesicherter Kauf</p>"
    )


# ── HTTP ────────────────────────────────────────────────────────────────────────

def _http(method: str, url: str, body: Optional[Dict], token: str) -> Tuple[dict, str]:
    data = json.dumps(body).encode() if body else None
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    for attempt in range(MAX_RETRY):
        try:
            req  = urllib.request.Request(url, data=data, headers=headers, method=method)
            resp = urllib.request.urlopen(req, timeout=25)
            link = resp.getheader("Link", "")
            return json.loads(resp.read()), link
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(SLEEP_429 * (attempt + 1))
                continue
            if e.code in (500, 503):
                time.sleep(3 * (attempt + 1))
                continue
            return {}, ""
        except Exception:
            time.sleep(2 * (attempt + 1))
    return {}, ""


# ── Heal Tasks ─────────────────────────────────────────────────────────────────

async def _fix_inventory(base: str, token: str) -> int:
    """Setzt inventory_policy auf 'continue' für alle deny+qty≤0 Varianten."""
    fixed = 0
    url   = f"{base}/products.json?limit=250&status=active&fields=id,variants"
    while url:
        data, link = await asyncio.get_event_loop().run_in_executor(
            None, lambda u=url: _http("GET", u, None, token)
        )
        for prod in data.get("products", []):
            for v in prod.get("variants", []):
                qty = int(v.get("inventory_quantity") or 0)
                pol = v.get("inventory_policy", "continue")
                if pol == "deny" and qty <= 0:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda vid=v["id"]: _http(
                            "PUT",
                            f"{base}/variants/{vid}.json",
                            {"variant": {"id": vid, "inventory_policy": "continue"}},
                            token
                        )
                    )
                    fixed += 1
                    await asyncio.sleep(SLEEP_OK)

        m   = re.search(r'<([^>]+)>; rel="next"', link)
        url = m.group(1) if m else None
        await asyncio.sleep(SLEEP_OK)

    return fixed


async def _fill_descriptions(base: str, token: str) -> int:
    """Ergänzt leere body_html mit kategorie-spezifischem SEO-Template."""
    filled = 0
    url    = f"{base}/products.json?limit=250&status=active&fields=id,title,body_html,product_type,tags"
    while url:
        data, link = await asyncio.get_event_loop().run_in_executor(
            None, lambda u=url: _http("GET", u, None, token)
        )
        for prod in data.get("products", []):
            if (prod.get("body_html") or "").strip():
                continue
            desc = _build_desc(
                prod.get("title", "Produkt"),
                prod.get("product_type", ""),
                prod.get("tags", ""),
            )
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda pid=prod["id"], d=desc: _http(
                    "PUT",
                    f"{base}/products/{pid}.json",
                    {"product": {"id": pid, "body_html": d}},
                    token
                )
            )
            filled += 1
            await asyncio.sleep(SLEEP_OK)

        m   = re.search(r'<([^>]+)>; rel="next"', link)
        url = m.group(1) if m else None
        await asyncio.sleep(SLEEP_OK)

    return filled


async def _fix_prices(base: str, token: str) -> int:
    """Korrigiert Varianten mit Preis < €1.00."""
    fixed = 0
    url   = f"{base}/products.json?limit=250&status=active&fields=id,variants"
    while url:
        data, link = await asyncio.get_event_loop().run_in_executor(
            None, lambda u=url: _http("GET", u, None, token)
        )
        for prod in data.get("products", []):
            for v in prod.get("variants", []):
                if float(v.get("price") or "0") < 1.0:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda vid=v["id"]: _http(
                            "PUT",
                            f"{base}/variants/{vid}.json",
                            {"variant": {"id": vid, "price": "9.99"}},
                            token
                        )
                    )
                    fixed += 1
                    await asyncio.sleep(SLEEP_OK)

        m   = re.search(r'<([^>]+)>; rel="next"', link)
        url = m.group(1) if m else None
        await asyncio.sleep(SLEEP_OK)

    return fixed


async def _set_product_types(base: str, token: str) -> int:
    """Leitet product_type aus Tags/Titel ab wenn leer."""
    TYPE_MAP = {
        "solar": "Solar Energy",   "powerstation": "Power Station", "batterie": "Battery",
        "kamera": "Camera",        "sensor": "Smart Sensor",        "schalter": "Smart Switch",
        "licht": "Smart Lighting", "steckdose": "Smart Plug",       "thermostat": "Thermostat",
        "roboter": "Robot Vacuum", "drohne": "Drone",               "e-bike": "E-Bike",
        "lautsprecher": "Speaker", "uhr": "Smartwatch",             "lock": "Smart Lock",
        "luftreiniger": "Air Purifier", "projektor": "Projector",   "gaming": "Gaming",
    }
    updated = 0
    url = f"{base}/products.json?limit=250&status=active&fields=id,title,product_type,tags"
    while url:
        data, link = await asyncio.get_event_loop().run_in_executor(
            None, lambda u=url: _http("GET", u, None, token)
        )
        for prod in data.get("products", []):
            if (prod.get("product_type") or "").strip():
                continue
            haystack = (prod.get("title", "") + " " + prod.get("tags", "")).lower()
            ptype = None
            for kw, tp in TYPE_MAP.items():
                if kw in haystack:
                    ptype = tp
                    break
            if ptype:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda pid=prod["id"], pt=ptype: _http(
                        "PUT",
                        f"{base}/products/{pid}.json",
                        {"product": {"id": pid, "product_type": pt}},
                        token
                    )
                )
                updated += 1
                await asyncio.sleep(SLEEP_OK)

        m   = re.search(r'<([^>]+)>; rel="next"', link)
        url = m.group(1) if m else None
        await asyncio.sleep(SLEEP_OK)

    return updated


# ── Public Entry Point ─────────────────────────────────────────────────────────

async def run_daily_heal() -> str:
    """
    Vollautonomer täglicher Shopify-Heal-Zyklus.
    Wird vom AutomationScheduler gerufen — kein manueller Start nötig.
    """
    domain, token, version = _creds()
    base = f"https://{domain}/admin/api/{version}"
    log.info("Shopify Daily Healer startet — %s", domain)

    inv   = await _fix_inventory(base, token)
    desc  = await _fill_descriptions(base, token)
    price = await _fix_prices(base, token)
    ptype = await _set_product_types(base, token)

    summary = (
        f"Inventory-Fixes={inv} | "
        f"Beschreibungen={desc} | "
        f"Preise={price} | "
        f"ProductType={ptype}"
    )
    log.info("Shopify Daily Healer fertig: %s", summary)
    return summary
