#!/usr/bin/env python3
"""
SYS-37: Wohnungswirtschaft Mieterbrief KI — €249/Monat
=======================================================
Monatlich unbegrenzte KI-Mieterbriefe für Wohnungsgesellschaften:
  - Modernisierungsankündigungen (§555 BGB-konform)
  - Betriebskosten-Abrechnungsbegleitschreiben
  - Wartungsankündigungen (Heizung, Aufzug, Brandschutz)
  - Informationsschreiben (Hausordnung, Änderungen)
  - Mahn- und Erinnerungsschreiben (ton-kalibriert)
  - Willkommensbriefe für neue Mieter
  - Kündigung Bestätigung + Rückgabe-Checklisten

Multiplikatoren:
  - GdW (Bundesverband: 3.000 Mitglieder, 6 Mio. Wohnungen)
  - vdw Niedersachsen, BWB Bayern, VNW Hamburg
  - Domus AG, Nemetschek (Wohnungswirtschaftssoftware)
  - Hausverwaltungs-Verbände (VDIV: 3.000 Mitglieder)

Preis: €249/Monat (Einzelbrief-Kosten: 0 — unbegrenzte Nutzung)
Provision für Partner: €74,70/Monat recurring
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SYS-37] %(levelname)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("SYS37MieterbriefKI")

_BASE = Path(__file__).parent.parent


def _load_env():
    ef = _BASE / ".env"
    if ef.exists():
        for line in ef.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


BRIEF_TYPEN = {
    "modernisierung":    "Modernisierungsankündigung (§555b BGB)",
    "betriebskosten":    "Betriebskosten-Abrechnungsbegleitschreiben",
    "wartung_heizung":   "Wartungsankündigung Heizung",
    "wartung_aufzug":    "Wartungsankündigung Aufzug/Fahrstuhl",
    "wartung_brandschutz":"Brandschutzprüfung-Ankündigung",
    "hausordnung":       "Hausordnung Aktualisierung",
    "willkommen":        "Willkommensschreiben neuer Mieter",
    "mahnung_freundl":   "Freundliche Zahlungserinnerung",
    "mahnung_formal":    "Formelle Mahnung (2. Stufe)",
    "kuendigung_eingang":"Kündigung Eingangsbestätigung + Rückgabe-Checkliste",
    "energieausweis":    "Energieausweis Information",
    "mieterhöhung":      "Mieterhöhungsverlangen (§558 BGB-konform)",
}


async def generate_mieterbrief(
    brief_typ: str,
    gesellschaft: str,
    objekt_adresse: str,
    zusatz: str = "",
    termin: str = "",
) -> Dict:
    """
    Generiert rechtssicheren Mieterbrief.

    Args:
        brief_typ: Key aus BRIEF_TYPEN
        gesellschaft: Name der Wohnungsgesellschaft
        objekt_adresse: Straße + Hausnr. des betroffenen Objekts
        zusatz: Zusätzliche Infos (z.B. Maßnahmen, Beträge)
        termin: Datum des Termins/Maßnahme
    """
    from modules.claude_automation import ask

    typ_name = BRIEF_TYPEN.get(brief_typ, brief_typ)

    system = (
        "Du bist Rechtsanwalt mit Schwerpunkt Mietrecht und Kommunikationsexperte "
        "für Wohnungsgesellschaften. Schreibe rechtssicher, klar, mieterfreundlich. "
        "Vermeide Fachjargon. Briefe müssen gesetzliche Anforderungen erfüllen "
        "(BGB-Konformität bei Ankündigungen) und dabei verständlich bleiben."
    )

    prompt = f"""Erstelle einen {typ_name} für:

Wohnungsgesellschaft: {gesellschaft}
Objekt: {objekt_adresse}
{f'Termin/Datum: {termin}' if termin else ''}
{f'Zusätzliche Informationen: {zusatz}' if zusatz else ''}

Anforderungen:
1. Formeller Briefkopf (Platzhalter für Mieter-Adresse)
2. Korrekte Anrede "Sehr geehrte Damen und Herren,"
3. Haupttext: klar, verständlich, alle Pflichtangaben
4. Rechtliche Grundlage (wo gesetzlich vorgeschrieben)
5. Kontaktmöglichkeit für Rückfragen
6. Freundlicher Abschluss
7. Unterschriftsblock mit Platzhaltern

Gesetzliche Besonderheiten für {typ_name} beachten!
Format: Vollständiger Brief, sofort verwendbar.
"""

    content = await asyncio.to_thread(ask, prompt, system=system, max_tokens=1500)
    return {
        "typ": typ_name,
        "gesellschaft": gesellschaft,
        "objekt": objekt_adresse,
        "brief": content,
    }


async def generate_brief_paket(gesellschaft: str, objekt: str) -> str:
    """Generiert 5 häufigste Brief-Typen auf einmal (für Erstlieferung bei Neukunden)."""
    standard_typen = ["willkommen", "wartung_heizung", "mahnung_freundl",
                      "modernisierung", "betriebskosten"]
    ergebnisse = []
    for typ in standard_typen:
        result = await generate_mieterbrief(typ, gesellschaft, objekt)
        ergebnisse.append(f"{'='*60}\n{result['typ'].upper()}\n{'='*60}\n\n{result['brief']}")
        await asyncio.sleep(2)
    return "\n\n".join(ergebnisse)


async def handle_new_subscription(customer_email: str, gesellschaft_data: dict) -> dict:
    """Nach Stripe-Zahlung: Starter-Paket (5 Briefe) sofort liefern."""
    log.info(f"SYS-37 Neues Abo: {customer_email} — {gesellschaft_data.get('gesellschaft', '?')}")
    gesellschaft = gesellschaft_data.get("gesellschaft", "Ihre Wohnungsgesellschaft")
    objekt = gesellschaft_data.get("muster_objekt", "Musterstraße 1, 12345 Musterstadt")
    paket = await generate_brief_paket(gesellschaft, objekt)
    from modules.service_delivery import _send_delivery_email
    header = f"STARTER-PAKET: 5 Mieterbrief-Vorlagen für {gesellschaft}\n\n"
    ok = _send_delivery_email(customer_email, "Wohnungswirtschaft Mieterbrief KI", header + paket)
    return {"ok": ok, "gesellschaft": gesellschaft, "briefe": 5}


async def task_sys37_monthly_reports() -> str:
    """Placeholder: Monatliche Nutzungsreports an Abonnenten."""
    return "SYS-37: Monatliche Reports — noch keine aktiven Abonnenten"


if __name__ == "__main__":
    async def _test():
        result = await generate_mieterbrief(
            brief_typ="modernisierung",
            gesellschaft="Städtische Wohnungsbau GmbH München",
            objekt_adresse="Beispielstraße 12-14, 80331 München",
            zusatz="Einbau neuer Wärmedämmung Außenfassade, Erneuerung Fenster EG-3.OG",
            termin="15. September 2026",
        )
        print(result["brief"])
    asyncio.run(_test())
