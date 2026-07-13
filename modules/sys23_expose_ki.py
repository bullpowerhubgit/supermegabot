#!/usr/bin/env python3
"""
SYS-23: Unternehmensverkauf-Exposé KI — €499 einmalig
=======================================================
Vollständige M&A-Unterlagen für Unternehmensverkäufe:
  - Executive Summary (Käufer-seitig)
  - Unternehmensprofil (Stärken, Alleinstellungsmerkmale)
  - Finanz-Narrative (nicht Zahlen, sondern Story)
  - Wachstumspotenzial-Darstellung
  - Käufer-Ansprache (strategische vs. Finanz-Investoren)
  - Teaser-Dokument (anonym für erste Kontakte)

Multiplikatoren:
  - M&A-Berater (8.000 in DE, Provision: €149,70)
  - Steuerberater Nachfolge (DStV, GmbH-Beratung)
  - IHK Unternehmensnachfolge-Börse (18k jährlich)
  - Unternehmensberater (Restrukturierung, Exit-Planung)

Preis: €499 einmalig (günstigster M&A-Baustein am Markt)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SYS-23] %(levelname)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("SYS23ExposKI")

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


async def generate_expose(firma_data: dict) -> Dict:
    """
    Generiert komplettes Unternehmensverkauf-Exposé.

    firma_data keys:
      firma_name, branche, ort, gruendungsjahr, mitarbeiter,
      umsatz_ca, ebitda_ca, hauptprodukt, alleinstellungsmerkmal,
      verkaufsgrund, wunsch_kaeuferprofil
    """
    from modules.claude_automation import ask

    name     = firma_data.get("firma_name", "Muster GmbH")
    branche  = firma_data.get("branche", "Dienstleistungen")
    ort      = firma_data.get("ort", "Deutschland")
    gegr     = firma_data.get("gruendungsjahr", "2010")
    ma       = firma_data.get("mitarbeiter", "15")
    umsatz   = firma_data.get("umsatz_ca", "€2-3 Mio.")
    ebitda   = firma_data.get("ebitda_ca", "15%")
    produkt  = firma_data.get("hauptprodukt", "Kernprodukt/-service")
    usp      = firma_data.get("alleinstellungsmerkmal", "Marktstellung")
    grund    = firma_data.get("verkaufsgrund", "Nachfolge")
    kaeuf    = firma_data.get("wunsch_kaeuferprofil", "Strategischer Käufer aus der Branche")

    system = (
        "Du bist erfahrener M&A-Berater und Autor von Unternehmens-Exposés. "
        "Schreibe professionell, investoren-orientiert, faktenbasiert. "
        "Betone Wachstumspotenzial und Käufervorteile, nicht nur Ist-Zustand. "
        "Vermeide Marketing-Sprache — schreibe wie ein Investment Memorandum."
    )

    prompt = f"""Erstelle ein vollständiges Unternehmensverkauf-Exposé für:

Unternehmen: {name}
Branche: {branche} | Standort: {ort} | Gegründet: {gegr}
Mitarbeiter: {ma} | Umsatz (ca.): {umsatz} | EBITDA-Marge (ca.): {ebitda}
Kernprodukt/-service: {produkt}
Alleinstellungsmerkmal: {usp}
Verkaufsgrund: {grund}
Wunsch-Käuferprofil: {kaeuf}

Erstelle folgende Dokumente:

## 1. ANONYMER TEASER (1 Seite — für erste Kontaktaufnahme ohne Namensnennung)
Kurzbeschreibung, Finanzkennzahlen anonymisiert, Investmentthese, Kontakt-CTA.

## 2. EXECUTIVE SUMMARY (2 Seiten)
Unternehmensportrait, Marktposition, Finanzhighlights, Wachstumspotenzial,
Transaktionsstruktur, nächste Schritte.

## 3. UNTERNEHMENSPROFIL
Geschichte und Entwicklung, Produkte/Dienstleistungen, Kundenbasis,
Wettbewerbsvorteile, Team/Management.

## 4. WACHSTUMSPOTENZIAL-NARRATIVE
3 konkrete Wachstumsoptionen die ein Käufer heben kann (die der aktuelle
Eigentümer aus Zeit-/Kapazitätsgründen nicht ausgeschöpft hat).

## 5. KÄUFER-ANSPRACHE
Vorlage für initiale Kontakt-Email an potenzielle Käufer.
"""

    content = await asyncio.to_thread(ask, prompt, system=system, max_tokens=3000)

    return {
        "firma": name,
        "branche": branche,
        "content": content,
        "dokumente": ["Teaser", "Executive Summary", "Unternehmensprofil",
                      "Wachstumspotenzial", "Käufer-Ansprache"],
    }


async def handle_new_order(customer_email: str, firma_data: dict) -> dict:
    """Nach Stripe-Zahlung: Exposé generieren + liefern."""
    log.info(f"SYS-23 Bestellung: {customer_email} — {firma_data.get('firma_name', '?')}")
    expose = await generate_expose(firma_data)
    from modules.service_delivery import _send_delivery_email
    ok = _send_delivery_email(customer_email, "Unternehmensverkauf-Exposé KI", expose["content"])
    return {"ok": ok, "firma": expose["firma"], "dokumente": expose["dokumente"]}


if __name__ == "__main__":
    async def _test():
        result = await generate_expose({
            "firma_name": "Muster Maschinenbau GmbH",
            "branche": "Sondermaschinenbau",
            "ort": "Stuttgart",
            "gruendungsjahr": "1998",
            "mitarbeiter": "28",
            "umsatz_ca": "€4,2 Mio.",
            "ebitda_ca": "18%",
            "hauptprodukt": "Automatisierungsanlagen für Automotive",
            "alleinstellungsmerkmal": "Einziger Anbieter von Inline-Prüfsystemen für E-Motor-Wicklungen in DE",
            "verkaufsgrund": "Altersbedingte Nachfolge, kein Nachfolger in der Familie",
            "wunsch_kaeuferprofil": "Strategischer Käufer aus Automotive-Zulieferer oder Private Equity",
        })
        print(result["content"][:1000])
    asyncio.run(_test())
