"""EU VAT OSS Engine — Nicht-EU-Verkäufer ohne Schwellenwert (seit 1. Juli 2021)"""
import logging
from datetime import datetime, timezone

log = logging.getLogger("VATOSSEngine")

# MwSt-Sätze aller EU-Länder (Standardsatz)
EU_VAT_RATES = {
    "AT": {"name": "Österreich", "standard": 20, "reduced": 10},
    "BE": {"name": "Belgien", "standard": 21, "reduced": 6},
    "BG": {"name": "Bulgarien", "standard": 20, "reduced": 9},
    "CY": {"name": "Zypern", "standard": 19, "reduced": 5},
    "CZ": {"name": "Tschechien", "standard": 21, "reduced": 12},
    "DE": {"name": "Deutschland", "standard": 19, "reduced": 7},
    "DK": {"name": "Dänemark", "standard": 25, "reduced": 0},
    "EE": {"name": "Estland", "standard": 22, "reduced": 9},
    "ES": {"name": "Spanien", "standard": 21, "reduced": 10},
    "FI": {"name": "Finnland", "standard": 25.5, "reduced": 14},
    "FR": {"name": "Frankreich", "standard": 20, "reduced": 5.5},
    "GR": {"name": "Griechenland", "standard": 24, "reduced": 13},
    "HR": {"name": "Kroatien", "standard": 25, "reduced": 13},
    "HU": {"name": "Ungarn", "standard": 27, "reduced": 5},
    "IE": {"name": "Irland", "standard": 23, "reduced": 13.5},
    "IT": {"name": "Italien", "standard": 22, "reduced": 10},
    "LT": {"name": "Litauen", "standard": 21, "reduced": 9},
    "LU": {"name": "Luxemburg", "standard": 17, "reduced": 8},
    "LV": {"name": "Lettland", "standard": 21, "reduced": 12},
    "MT": {"name": "Malta", "standard": 18, "reduced": 5},
    "NL": {"name": "Niederlande", "standard": 21, "reduced": 9},
    "PL": {"name": "Polen", "standard": 23, "reduced": 8},
    "PT": {"name": "Portugal", "standard": 23, "reduced": 13},
    "RO": {"name": "Rumänien", "standard": 19, "reduced": 9},
    "SE": {"name": "Schweden", "standard": 25, "reduced": 12},
    "SI": {"name": "Slowenien", "standard": 22, "reduced": 9.5},
    "SK": {"name": "Slowakei", "standard": 20, "reduced": 10},
}

OSS_REGISTRATION_STEPS = [
    {"step": 1, "title": "Identifikation der Steuerpflicht", "desc": "Prüfen ob B2C-Umsätze in EU anfallen (Schwellenwert für Nicht-EU = €0)"},
    {"step": 2, "title": "OSS-Registrierung", "desc": "Nicht-Unions-OSS: Registrierung in EINEM EU-Mitgliedsstaat (z.B. Deutschland: BZSt Online-Portal)"},
    {"step": 3, "title": "USt-IdNr beantragen", "desc": "EU-USt-IdNr für OSS-Zwecke (kostenlos beim zuständigen Finanzamt/Bundeszentralamt für Steuern)"},
    {"step": 4, "title": "Umsatzerfassung einrichten", "desc": "Alle EU-B2C-Umsätze nach Zielland getrennt erfassen (Shopify/Stripe Revenue by Country)"},
    {"step": 5, "title": "Quartalsvoranmeldung", "desc": "OSS-Voranmeldung quartalsweise: 30. April, 31. Juli, 31. Oktober, 31. Januar"},
    {"step": 6, "title": "MwSt-Zahlung", "desc": "Zahlung im Registrierungsland, das OSS-Portal verteilt an alle Zielländer"},
]


def calculate_vat_liability(sales_by_country: dict) -> dict:
    """Berechnet MwSt-Schuld nach Zielland."""
    total_vat = 0.0
    breakdown = []
    for country_code, net_revenue in sales_by_country.items():
        if country_code in EU_VAT_RATES:
            rate = EU_VAT_RATES[country_code]["standard"]
            vat_amount = net_revenue * (rate / 100)
            total_vat += vat_amount
            breakdown.append({
                "country": country_code,
                "country_name": EU_VAT_RATES[country_code]["name"],
                "net_revenue_eur": net_revenue,
                "vat_rate_pct": rate,
                "vat_due_eur": round(vat_amount, 2),
            })
    return {
        "total_vat_due_eur": round(total_vat, 2),
        "breakdown": sorted(breakdown, key=lambda x: x["vat_due_eur"], reverse=True),
        "report_generated": datetime.now(timezone.utc).isoformat(),
        "legal_basis": "MwSt-RL 2006/112/EG Art. 59c — Nicht-EU-Verkäufer: Schwellenwert €0",
        "oss_filing_deadlines": ["30.04", "31.07", "31.10", "31.01"],
    }


def generate_quarterly_prefill(q: int, year: int, sales_by_country: dict) -> dict:
    """Vorbefüllung der OSS-Quartalsvoranmeldung."""
    q_map = {1: ("Jan–Mrz", "30.04"), 2: ("Apr–Jun", "31.07"), 3: ("Jul–Sep", "31.10"), 4: ("Okt–Dez", "31.01")}
    period_name, deadline = q_map.get(q, ("?", "?"))
    liability = calculate_vat_liability(sales_by_country)
    return {
        "quarter": f"Q{q}/{year}",
        "period": period_name,
        "filing_deadline": deadline,
        "scheme": "Nicht-Unions-OSS",
        "vat_liability": liability,
        "prefill_ready": True,
        "note": "Diese Voranmeldung wurde automatisch vorbefüllt. Bitte vor Einreichung prüfen.",
    }


def assess_non_eu_seller_risk(country_of_origin: str, annual_eu_revenue: float) -> dict:
    """Risikoanalyse für Nicht-EU-Verkäufer."""
    is_eu = country_of_origin.upper() in EU_VAT_RATES
    risk = "LOW" if is_eu else "CRITICAL"
    estimated_vat_exposure = annual_eu_revenue * 0.20  # ~20% durchschnittlich
    return {
        "seller_country": country_of_origin,
        "is_eu_seller": is_eu,
        "eu_vat_threshold": "€10.000/Jahr (nur EU-Ansässige)" if is_eu else "€0 — KEIN Schwellenwert!",
        "risk_level": risk,
        "annual_eu_revenue_eur": annual_eu_revenue,
        "estimated_vat_exposure_eur": round(estimated_vat_exposure, 2),
        "penalty_risk": "Nachzahlung + Zinsen + ggf. Strafzuschlag bis 10%" if not is_eu else "Standard",
        "action_required": "Sofortige OSS-Registrierung!" if not is_eu else "Jährliche Überprüfung ausreichend",
        "legal_basis": "MwSt-RL 2006/112/EG Art. 59c Abs. 1",
    }
