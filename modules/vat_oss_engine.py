#!/usr/bin/env python3
"""
VAT OSS Engine — Non-EU → EU VAT One-Stop-Shop Compliance
==========================================================
Automatisierte Mehrwertsteuer-Compliance für Nicht-EU-Verkäufer:
- Echtzeit-MwSt-Berechnung für alle EU-27 Länder
- OSS-Quartalsbericht-Generierung
- €10.000-Schwellenwert-Überwachung für Kleinunternehmer
- Stripe-Integration für automatische Tax-Erfassung

Rechtsgrundlage: EU-Mehrwertsteuerrichtlinie 2021/2085 (OSS-Regime)
Preis: €79/Monat (Stripe Price ID: VAT_OSS_PRICE_ID)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

log = logging.getLogger("VatOssEngine")

# ── Env ──────────────────────────────────────────────────────────────────────
TG_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT        = os.getenv("TELEGRAM_CHAT_ID", "")
STRIPE_KEY     = os.getenv("STRIPE_SECRET_KEY", "")
VAT_OSS_PRICE  = os.getenv("VAT_OSS_PRICE_ID", "")
NETLIFY_URL    = os.getenv("BPI_NETLIFY_URL", "https://extraordinary-daffodil-239faa.netlify.app")
LANDING_URL    = f"{NETLIFY_URL}/vat-oss"

# ── EU VAT Rates (Stand 2026) ──────────────────────────────────────────────
# Standard rate + Digital services rate per country
# "digital" = rate applied to electronically supplied services
EU_VAT_RATES: dict[str, dict[str, Any]] = {
    "DE": {"name": "Deutschland",     "standard": 19.0, "reduced": 7.0,   "digital": 19.0},
    "AT": {"name": "Österreich",      "standard": 20.0, "reduced": 10.0,  "digital": 20.0},
    "FR": {"name": "Frankreich",      "standard": 20.0, "reduced": 10.0,  "digital": 20.0},
    "NL": {"name": "Niederlande",     "standard": 21.0, "reduced": 9.0,   "digital": 21.0},
    "IT": {"name": "Italien",         "standard": 22.0, "reduced": 10.0,  "digital": 22.0},
    "ES": {"name": "Spanien",         "standard": 21.0, "reduced": 10.0,  "digital": 21.0},
    "PL": {"name": "Polen",           "standard": 23.0, "reduced": 8.0,   "digital": 23.0},
    "BE": {"name": "Belgien",         "standard": 21.0, "reduced": 6.0,   "digital": 21.0},
    "SE": {"name": "Schweden",        "standard": 25.0, "reduced": 12.0,  "digital": 25.0},
    "DK": {"name": "Dänemark",        "standard": 25.0, "reduced": None,  "digital": 25.0},
    # Weitere EU-Länder (vollständige EU-27 Abdeckung)
    "BG": {"name": "Bulgarien",       "standard": 20.0, "reduced": 9.0,   "digital": 20.0},
    "CY": {"name": "Zypern",          "standard": 19.0, "reduced": 9.0,   "digital": 19.0},
    "CZ": {"name": "Tschechien",      "standard": 21.0, "reduced": 12.0,  "digital": 21.0},
    "EE": {"name": "Estland",         "standard": 22.0, "reduced": 9.0,   "digital": 22.0},
    "FI": {"name": "Finnland",        "standard": 25.5, "reduced": 14.0,  "digital": 25.5},
    "GR": {"name": "Griechenland",    "standard": 24.0, "reduced": 13.0,  "digital": 24.0},
    "HR": {"name": "Kroatien",        "standard": 25.0, "reduced": 13.0,  "digital": 25.0},
    "HU": {"name": "Ungarn",          "standard": 27.0, "reduced": 18.0,  "digital": 27.0},
    "IE": {"name": "Irland",          "standard": 23.0, "reduced": 13.5,  "digital": 23.0},
    "LT": {"name": "Litauen",         "standard": 21.0, "reduced": 9.0,   "digital": 21.0},
    "LU": {"name": "Luxemburg",       "standard": 17.0, "reduced": 8.0,   "digital": 17.0},
    "LV": {"name": "Lettland",        "standard": 21.0, "reduced": 12.0,  "digital": 21.0},
    "MT": {"name": "Malta",           "standard": 18.0, "reduced": 7.0,   "digital": 18.0},
    "PT": {"name": "Portugal",        "standard": 23.0, "reduced": 13.0,  "digital": 23.0},
    "RO": {"name": "Rumänien",        "standard": 19.0, "reduced": 9.0,   "digital": 19.0},
    "SI": {"name": "Slowenien",       "standard": 22.0, "reduced": 9.5,   "digital": 22.0},
    "SK": {"name": "Slowakei",        "standard": 23.0, "reduced": 10.0,  "digital": 23.0},
}

# ── OSS Schwellenwert für Kleinunternehmer ─────────────────────────────────
OSS_THRESHOLD_EUR = 10_000.0  # €10.000 Jahresumsatz in der gesamten EU


# ── Core Functions ─────────────────────────────────────────────────────────

def calculate_vat(
    country_code: str,
    amount_eur: float,
    product_type: str = "standard",
) -> dict:
    """
    Berechne MwSt für ein EU-Land.

    Args:
        country_code: ISO-3166-1 Alpha-2 (z.B. "DE", "FR")
        amount_eur:   Netto-Betrag in EUR
        product_type: "standard", "digital", "reduced", "zero"

    Returns:
        {country_code, country_name, rate, amount_net, amount_vat, amount_gross, product_type}
    """
    country_code = country_code.upper()
    rates = EU_VAT_RATES.get(country_code)
    if not rates:
        log.warning("Unbekanntes EU-Land: %s — Kein MwSt-Satz verfügbar", country_code)
        return {
            "country_code":   country_code,
            "country_name":   "Unbekannt",
            "rate":           0.0,
            "amount_net":     round(amount_eur, 2),
            "amount_vat":     0.0,
            "amount_gross":   round(amount_eur, 2),
            "product_type":   product_type,
            "error":          f"Kein Satz für {country_code}",
        }

    if product_type == "digital":
        rate = rates.get("digital", rates["standard"])
    elif product_type == "reduced":
        rate = rates.get("reduced") or rates["standard"]
    elif product_type == "zero":
        rate = 0.0
    else:
        rate = rates["standard"]

    amount_vat   = round(amount_eur * rate / 100, 2)
    amount_gross = round(amount_eur + amount_vat, 2)

    return {
        "country_code":   country_code,
        "country_name":   rates["name"],
        "rate":           rate,
        "amount_net":     round(amount_eur, 2),
        "amount_vat":     amount_vat,
        "amount_gross":   amount_gross,
        "product_type":   product_type,
    }


def generate_oss_report(transactions: list[dict], quarter: str) -> dict:
    """
    OSS-Quartalsbericht generieren.

    Args:
        transactions: Liste von Dicts mit {country_code, amount_eur, product_type}
        quarter:      Z.B. "2026-Q1"

    Returns:
        {quarter, totals_by_country, grand_total_net, grand_total_vat,
         grand_total_gross, transaction_count, generated_at}
    """
    totals: dict[str, dict] = {}
    grand_net   = 0.0
    grand_vat   = 0.0
    grand_gross = 0.0

    for tx in transactions:
        cc   = tx.get("country_code", "").upper()
        amt  = float(tx.get("amount_eur", 0.0))
        ptype = tx.get("product_type", "standard")

        if not cc or amt <= 0:
            continue

        calc = calculate_vat(cc, amt, ptype)
        if cc not in totals:
            totals[cc] = {
                "country_name":  calc.get("country_name", cc),
                "rate":          calc.get("rate", 0.0),
                "total_net":     0.0,
                "total_vat":     0.0,
                "total_gross":   0.0,
                "tx_count":      0,
            }

        totals[cc]["total_net"]   += calc["amount_net"]
        totals[cc]["total_vat"]   += calc["amount_vat"]
        totals[cc]["total_gross"] += calc["amount_gross"]
        totals[cc]["tx_count"]    += 1
        grand_net   += calc["amount_net"]
        grand_vat   += calc["amount_vat"]
        grand_gross += calc["amount_gross"]

    # Round totals
    for cc in totals:
        totals[cc]["total_net"]   = round(totals[cc]["total_net"],   2)
        totals[cc]["total_vat"]   = round(totals[cc]["total_vat"],   2)
        totals[cc]["total_gross"] = round(totals[cc]["total_gross"], 2)

    return {
        "quarter":            quarter,
        "totals_by_country":  totals,
        "grand_total_net":    round(grand_net,   2),
        "grand_total_vat":    round(grand_vat,   2),
        "grand_total_gross":  round(grand_gross, 2),
        "transaction_count":  len(transactions),
        "generated_at":       datetime.now(timezone.utc).isoformat(),
    }


def check_oss_threshold(annual_eur: float) -> dict:
    """
    Prüfe OSS-Registrierungspflicht (€10.000-Schwellenwert für EU-Kleinunternehmer).

    Wichtig: Für Nicht-EU-Verkäufer gilt kein Schwellenwert — sie sind ab der
    ersten EU-Bestellung OSS-pflichtig. Diese Funktion gilt nur für EU-ansässige
    Kleinunternehmer.

    Args:
        annual_eur: Jährlicher grenzüberschreitender EU-Umsatz in EUR

    Returns:
        {annual_eur, threshold, threshold_pct, exceeded, oss_required, message}
    """
    exceeded     = annual_eur >= OSS_THRESHOLD_EUR
    threshold_pct = min((annual_eur / OSS_THRESHOLD_EUR) * 100, 100.0)

    if exceeded:
        msg = (
            f"⚠️ OSS-Pflicht! Jahresumsatz €{annual_eur:,.2f} überschreitet "
            f"den €{OSS_THRESHOLD_EUR:,.0f}-Schwellenwert. "
            "OSS-Registrierung in einem EU-Land erforderlich."
        )
    elif threshold_pct >= 80:
        msg = (
            f"⚡ Achtung: {threshold_pct:.0f}% des OSS-Schwellenwerts erreicht "
            f"(€{annual_eur:,.2f} von €{OSS_THRESHOLD_EUR:,.0f}). "
            "OSS-Registrierung bald erforderlich."
        )
    else:
        msg = (
            f"✅ Unterhalb des OSS-Schwellenwerts: €{annual_eur:,.2f} "
            f"({threshold_pct:.0f}% von €{OSS_THRESHOLD_EUR:,.0f})."
        )

    return {
        "annual_eur":    round(annual_eur, 2),
        "threshold":     OSS_THRESHOLD_EUR,
        "threshold_pct": round(threshold_pct, 1),
        "exceeded":      exceeded,
        "oss_required":  exceeded,
        "message":       msg,
    }


async def _get_stripe_eu_revenue() -> float:
    """Lese Stripe-Umsätze der letzten 365 Tage für EU-Länder."""
    if not STRIPE_KEY:
        log.debug("STRIPE_SECRET_KEY nicht gesetzt — Stripe-Revenue-Check übersprungen")
        return 0.0

    eu_codes = set(EU_VAT_RATES.keys())
    total    = 0.0
    cutoff   = int(datetime.now(timezone.utc).timestamp()) - 365 * 86400

    try:
        headers = {"Authorization": f"Bearer {STRIPE_KEY}"}
        params  = {
            "limit":         "100",
            "created[gte]":  str(cutoff),
            "status":        "paid",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.stripe.com/v1/payment_intents",
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for pi in data.get("data", []):
                        cc = (pi.get("shipping", {}) or {}).get("address", {}).get("country", "")
                        if cc.upper() in eu_codes:
                            total += pi.get("amount", 0) / 100.0
                else:
                    log.warning("Stripe API: HTTP %s", resp.status)
    except Exception as exc:
        log.warning("Stripe EU Revenue Check: %s", exc)

    return round(total, 2)


async def _send_tg(msg: str) -> None:
    """Sende Telegram-Benachrichtigung."""
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        async with aiohttp.ClientSession() as session:
            await session.post(
                url,
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as exc:
        log.debug("TG Send: %s", exc)


async def run_vat_oss_cycle() -> dict:
    """
    Haupt-Zyklus: Stripe EU-Umsatz abrufen → Schwellenwert prüfen →
    Telegram-Alert bei Überschreitung.

    Returns:
        {status, annual_eur, threshold_pct, exceeded, oss_required, landing_url, price_id}
    """
    log.info("VAT OSS Engine — Zyklus startet")

    annual_eur = await _get_stripe_eu_revenue()
    threshold  = check_oss_threshold(annual_eur)

    result = {
        "status":        "ok",
        "annual_eur":    annual_eur,
        "threshold_pct": threshold["threshold_pct"],
        "exceeded":      threshold["exceeded"],
        "oss_required":  threshold["oss_required"],
        "landing_url":   LANDING_URL,
        "price_id":      VAT_OSS_PRICE,
    }

    # Telegram-Benachrichtigung bei kritischen Schwellen
    if threshold["exceeded"]:
        await _send_tg(
            "🚨 <b>VAT OSS — OSS-Pflicht erreicht!</b>\n"
            f"{threshold['message']}\n"
            f"💰 EU-Jahresumsatz: €{annual_eur:,.2f}\n"
            f"🔗 <a href='{LANDING_URL}'>VAT OSS Tool (€79/Monat)</a>"
        )
        result["status"] = "threshold_exceeded"
        log.warning("OSS-Schwellenwert überschritten: €%.2f", annual_eur)
    elif threshold["threshold_pct"] >= 80:
        await _send_tg(
            "⚡ <b>VAT OSS — Schwellenwert fast erreicht</b>\n"
            f"{threshold['message']}\n"
            f"🔗 <a href='{LANDING_URL}'>Jetzt vorbereiten (€79/Monat)</a>"
        )
        result["status"] = "threshold_warning"
        log.info("OSS-Schwellenwert Warnung: %.1f%%", threshold["threshold_pct"])
    else:
        log.info("OSS-Status: OK (%.1f%% des Schwellenwerts)", threshold["threshold_pct"])

    return result
