#!/usr/bin/env python3
"""
Non-EU VAT/OSS Automation — SuperMegaBot Nische 3
Für Nicht-EU-Verkäufer (UK, US, CH, CN, etc.):
- Kein €10.000-Schwellenwert — sofort OSS-Pflicht ab erster EU-Bestellung
- Automatische MwSt-Berechnung für alle 27 EU-Länder
- OSS-Meldungs-Generierung (Quartalsbericht)
- Stripe Tax Integration
- Preis: €49–99/Monat

Rechtsgrundlage: EU-Mehrwertsteuerrichtlinie 2021/2085, §3a ff. UStG
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
log = logging.getLogger("NonEuVatOss")

TG_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT    = os.getenv("TELEGRAM_CHAT_ID", "")
STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STATE_FILE = Path(__file__).parent.parent / "data" / "vat_oss_state.json"

# ── EU-27 MwSt-Sätze (Standard-Satz, gültig 2026) ──────────────────────
EU_VAT_RATES = {
    "AT": {"name": "Österreich",      "standard": 20.0, "reduced": 10.0, "super_reduced": 5.0,  "zero": False},
    "BE": {"name": "Belgien",         "standard": 21.0, "reduced": 6.0,  "super_reduced": None, "zero": False},
    "BG": {"name": "Bulgarien",       "standard": 20.0, "reduced": 9.0,  "super_reduced": None, "zero": False},
    "CY": {"name": "Zypern",          "standard": 19.0, "reduced": 9.0,  "super_reduced": None, "zero": False},
    "CZ": {"name": "Tschechien",      "standard": 21.0, "reduced": 12.0, "super_reduced": None, "zero": False},
    "DE": {"name": "Deutschland",     "standard": 19.0, "reduced": 7.0,  "super_reduced": None, "zero": False},
    "DK": {"name": "Dänemark",        "standard": 25.0, "reduced": None, "super_reduced": None, "zero": False},
    "EE": {"name": "Estland",         "standard": 22.0, "reduced": 9.0,  "super_reduced": None, "zero": False},
    "ES": {"name": "Spanien",         "standard": 21.0, "reduced": 10.0, "super_reduced": 4.0,  "zero": False},
    "FI": {"name": "Finnland",        "standard": 25.5, "reduced": 14.0, "super_reduced": 10.0, "zero": False},
    "FR": {"name": "Frankreich",      "standard": 20.0, "reduced": 10.0, "super_reduced": 5.5,  "zero": False},
    "GR": {"name": "Griechenland",    "standard": 24.0, "reduced": 13.0, "super_reduced": 6.0,  "zero": False},
    "HR": {"name": "Kroatien",        "standard": 25.0, "reduced": 13.0, "super_reduced": 5.0,  "zero": False},
    "HU": {"name": "Ungarn",          "standard": 27.0, "reduced": 18.0, "super_reduced": 5.0,  "zero": False},
    "IE": {"name": "Irland",          "standard": 23.0, "reduced": 13.5, "super_reduced": None, "zero": True},
    "IT": {"name": "Italien",         "standard": 22.0, "reduced": 10.0, "super_reduced": 5.0,  "zero": True},
    "LT": {"name": "Litauen",         "standard": 21.0, "reduced": 9.0,  "super_reduced": 5.0,  "zero": False},
    "LU": {"name": "Luxemburg",       "standard": 17.0, "reduced": 8.0,  "super_reduced": 3.0,  "zero": False},
    "LV": {"name": "Lettland",        "standard": 21.0, "reduced": 12.0, "super_reduced": 5.0,  "zero": False},
    "MT": {"name": "Malta",           "standard": 18.0, "reduced": 7.0,  "super_reduced": 5.0,  "zero": True},
    "NL": {"name": "Niederlande",     "standard": 21.0, "reduced": 9.0,  "super_reduced": None, "zero": False},
    "PL": {"name": "Polen",           "standard": 23.0, "reduced": 8.0,  "super_reduced": 5.0,  "zero": False},
    "PT": {"name": "Portugal",        "standard": 23.0, "reduced": 13.0, "super_reduced": 6.0,  "zero": False},
    "RO": {"name": "Rumänien",        "standard": 19.0, "reduced": 9.0,  "super_reduced": 5.0,  "zero": False},
    "SE": {"name": "Schweden",        "standard": 25.0, "reduced": 12.0, "super_reduced": 6.0,  "zero": False},
    "SI": {"name": "Slowenien",       "standard": 22.0, "reduced": 9.5,  "super_reduced": 5.0,  "zero": False},
    "SK": {"name": "Slowakei",        "standard": 23.0, "reduced": 10.0, "super_reduced": None, "zero": False},
}

# Produkttypen → MwSt-Kategorie
VAT_CATEGORIES = {
    "digital":     "standard",    # Digitale Güter immer Standard-MwSt
    "physical":    "reduced",     # Physische Waren oft reduziert möglich
    "food":        "super_reduced",
    "books":       "reduced",
    "services":    "standard",
    "software":    "standard",
    "clothing":    "standard",
    "electronics": "standard",
}

# OSS-Registrierungsland (Rudolf: Deutschland)
OSS_REGISTRATION_COUNTRY = "DE"
OSS_REGISTRATION_NUMBER  = os.getenv("OSS_REGISTRATION_NUMBER", "DE_OSS_NICHT_GESETZT")


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "clients": [],
        "transactions": [],
        "quarterly_reports": {},
        "last_cycle": 0,
        "stats": {"total_vat_calculated": 0.0, "total_transactions": 0},
    }


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


def calculate_vat(
    net_amount_eur: float,
    customer_country: str,
    product_type: str = "digital",
    is_b2b: bool = False,
) -> dict:
    """
    Berechnet MwSt für eine EU-Bestellung.

    Args:
        net_amount_eur: Netto-Betrag in EUR
        customer_country: ISO-2 Ländercode (z.B. "DE", "FR")
        product_type: Produktkategorie (digital/physical/food/books/services)
        is_b2b: B2B-Verkauf (Reverse Charge — keine MwSt)

    Returns: Vollständige MwSt-Berechnung
    """
    country_upper = customer_country.upper()

    if country_upper not in EU_VAT_RATES:
        return {
            "ok":             False,
            "error":          f"Land {customer_country} nicht in EU-27",
            "vat_applicable": False,
        }

    country_data = EU_VAT_RATES[country_upper]

    if is_b2b:
        return {
            "ok":             True,
            "country":        country_upper,
            "country_name":   country_data["name"],
            "vat_applicable": False,
            "vat_rate":       0.0,
            "vat_amount":     0.0,
            "gross_amount":   net_amount_eur,
            "net_amount":     net_amount_eur,
            "mechanism":      "Reverse Charge (B2B) — keine MwSt fällig",
            "oss_relevant":   False,
        }

    vat_category = VAT_CATEGORIES.get(product_type, "standard")
    vat_rate = country_data.get(vat_category) or country_data["standard"]

    vat_amount   = round(net_amount_eur * vat_rate / 100, 2)
    gross_amount = round(net_amount_eur + vat_amount, 2)

    return {
        "ok":             True,
        "country":        country_upper,
        "country_name":   country_data["name"],
        "vat_applicable": True,
        "vat_rate":       vat_rate,
        "vat_category":   vat_category,
        "vat_amount":     vat_amount,
        "gross_amount":   gross_amount,
        "net_amount":     net_amount_eur,
        "mechanism":      f"OSS — gemeldet über {OSS_REGISTRATION_COUNTRY}",
        "oss_relevant":   True,
        "legal_basis":    "EU MWST-Richtlinie 2021/2085",
    }


def calculate_vat_batch(orders: list[dict]) -> list[dict]:
    """
    Batch-MwSt-Berechnung für mehrere Bestellungen.

    Args:
        orders: [{"amount": float, "country": str, "type": str, "b2b": bool, "id": str}]

    Returns: Bestellungen mit MwSt-Details angereichert
    """
    results = []
    for order in orders:
        vat = calculate_vat(
            net_amount_eur  = order.get("amount", 0),
            customer_country= order.get("country", "DE"),
            product_type    = order.get("type", "digital"),
            is_b2b          = order.get("b2b", False),
        )
        results.append({**order, "vat": vat})
    return results


def generate_oss_quarterly_report(
    transactions: list[dict],
    quarter: str,
    year: int,
) -> dict:
    """
    Generiert OSS-Quartalsbericht für die Steuerbehörde.

    Args:
        transactions: [{country, net_amount, vat_amount, vat_rate, date}]
        quarter: "Q1", "Q2", "Q3", "Q4"
        year: 2026

    Returns: Strukturierter OSS-Bericht
    """
    by_country: dict[str, dict] = {}

    for tx in transactions:
        country = tx.get("country", "XX").upper()
        if country not in EU_VAT_RATES:
            continue

        if country not in by_country:
            by_country[country] = {
                "country":       country,
                "country_name":  EU_VAT_RATES[country]["name"],
                "net_total":     0.0,
                "vat_total":     0.0,
                "transaction_count": 0,
                "vat_rate":      EU_VAT_RATES[country]["standard"],
            }

        by_country[country]["net_total"]         += tx.get("net_amount", 0)
        by_country[country]["vat_total"]          += tx.get("vat_amount", 0)
        by_country[country]["transaction_count"]  += 1

    total_vat = sum(c["vat_total"] for c in by_country.values())
    total_net = sum(c["net_total"] for c in by_country.values())

    # Runden
    for c in by_country.values():
        c["net_total"] = round(c["net_total"], 2)
        c["vat_total"] = round(c["vat_total"], 2)

    return {
        "report_type":           "OSS-Quartalsbericht (EU VAT One-Stop-Shop)",
        "generated_at":          datetime.now(timezone.utc).isoformat(),
        "period":                f"{quarter} {year}",
        "registration_country":  OSS_REGISTRATION_COUNTRY,
        "oss_registration_no":   OSS_REGISTRATION_NUMBER,
        "currency":              "EUR",
        "total_net_eur":         round(total_net, 2),
        "total_vat_eur":         round(total_vat, 2),
        "total_gross_eur":       round(total_net + total_vat, 2),
        "by_country":            list(by_country.values()),
        "countries_active":      len(by_country),
        "total_transactions":    len(transactions),
        "submission_deadline":   _get_submission_deadline(quarter, year),
        "legal_basis":           "EU MWST-Richtlinie 2021/2085",
        "filing_portal":         "https://www.bzst.de/DE/Unternehmen/Umsatzsteuer/One-Stop-Shop/one-stop-shop.html",
    }


def _get_submission_deadline(quarter: str, year: int) -> str:
    deadlines = {
        "Q1": f"{year}-04-30",
        "Q2": f"{year}-07-31",
        "Q3": f"{year}-10-31",
        "Q4": f"{year+1}-01-31",
    }
    return deadlines.get(quarter, f"{year}-12-31")


def check_oss_obligation(
    seller_country: str,
    eu_revenue_eur: float,
    has_oss_registration: bool = False,
) -> dict:
    """
    Prüft OSS-Pflicht für Nicht-EU-Verkäufer.
    Nicht-EU-Verkäufer: KEIN €10k-Schwellenwert — sofort pflichtig!
    """
    is_eu_seller = seller_country.upper() in EU_VAT_RATES
    eu_threshold = 10000.0 if is_eu_seller else 0.0  # Nicht-EU: immer €0

    oss_required = not has_oss_registration and (
        eu_revenue_eur > eu_threshold or not is_eu_seller
    )

    urgency = "SOFORT" if (not is_eu_seller and not has_oss_registration) else "PRÜFEN"

    return {
        "seller_country":        seller_country,
        "is_eu_seller":          is_eu_seller,
        "eu_revenue_eur":        eu_revenue_eur,
        "threshold_eur":         eu_threshold,
        "oss_required":          oss_required,
        "has_oss_registration":  has_oss_registration,
        "urgency":               urgency,
        "action": (
            "OSS-Registrierung beim Bundeszentralamt für Steuern (BZST) SOFORT beantragen!"
            if oss_required else
            "OSS-Registrierung vorhanden — quartalsweise Meldung erforderlich"
        ),
        "registration_url":      "https://www.bzst.de/DE/Unternehmen/Umsatzsteuer/One-Stop-Shop",
        "fine_risk":             "bis €50.000 + Nachzahlung aller MwSt-Beträge + Zinsen 5% p.a.",
        "legal_basis":           "EU MWST-Richtlinie 2021/2085 Art. 369a–369x",
    }


async def get_stripe_tax_settings() -> dict:
    """Prüft Stripe Tax Einstellungen für automatische MwSt."""
    if not STRIPE_KEY:
        return {"ok": False, "error": "STRIPE_SECRET_KEY nicht gesetzt"}

    try:
        auth = aiohttp.BasicAuth(STRIPE_KEY, "")
        async with aiohttp.ClientSession(auth=auth) as session:
            async with session.get(
                "https://api.stripe.com/v1/tax/settings",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return {
                        "ok":           True,
                        "stripe_tax":   data,
                        "tax_enabled":  data.get("status") == "active",
                    }
                return {"ok": False, "status": r.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def run_vat_oss_cycle() -> dict:
    """Scheduler-Einstieg: OSS-Status prüfen und Report senden."""
    state = _load_state()
    total_vat = state.get("stats", {}).get("total_vat_calculated", 0)
    transactions = state.get("stats", {}).get("total_transactions", 0)

    msg = (
        f"🧾 *Non-EU VAT/OSS System — Cycle Report*\n"
        f"Transaktionen verarbeitet: {transactions}\n"
        f"MwSt berechnet: €{total_vat:.2f}\n"
        f"OSS-Land: {OSS_REGISTRATION_COUNTRY}\n"
        f"EU-Länder abgedeckt: 27\n"
        f"System: ✅ Online"
    )
    await _tg(msg)

    state["last_cycle"] = int(time.time())
    _save_state(state)

    return {
        "ok":          True,
        "transactions": transactions,
        "total_vat":   total_vat,
        "eu_countries": len(EU_VAT_RATES),
    }


async def get_status() -> dict:
    state = _load_state()
    return {
        "eu_countries":          len(EU_VAT_RATES),
        "oss_registration":      OSS_REGISTRATION_COUNTRY,
        "price_range":           "€49–99/Monat",
        "total_transactions":    state.get("stats", {}).get("total_transactions", 0),
        "total_vat_eur":         state.get("stats", {}).get("total_vat_calculated", 0),
        "stripe_tax_available":  bool(STRIPE_KEY),
        "legal_basis":           "EU MWST-Richtlinie 2021/2085",
    }
