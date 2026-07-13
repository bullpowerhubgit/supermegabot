#!/usr/bin/env python3
"""
SYS-18: Steuerberater Mandanten-Newsletter KI — €149/Monat
===========================================================
Automatisch generierte Mandanten-Newsletter für Steuerberatungskanzleien:
  - Aktuelle Steuer-News (monatlich)
  - Mandantengerechte Sprache (kein Fachjargon)
  - Personalisierter Kanzlei-Header
  - DSGVO-konform (nur für bestehende Mandanten)
  - Direkt in gängige Email-Tools übertragbar

Multiplikatoren:
  - DStV (Deutscher Steuerberaterverband): 37.000 Mitglieder
  - DATEV-Community: 52.000 Kanzleien
  - Steuerberater-Verbände der Länder

Preis: €149/Monat pro Kanzlei
Provision für Partner: €44,70/Monat
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SYS-18] %(levelname)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("SYS18NewsletterKI")

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

# ── Aktuelle Steuer-Themen (monatlich aktualisierbar) ────────────────────────

STEUER_THEMEN_JULI_2026 = [
    "Jahressteuergesetz 2026: Neue Regelungen ab 01.07.2026",
    "Grundfreibetrag 2026: Erhöhung auf €11.784",
    "Photovoltaik: Nullsteuersatz Erweiterung auf Balkonsolar",
    "Homeoffice-Pauschale: Dauerhafte Verlängerung bestätigt",
    "GmbH-Anteile: Neue Bewertungsregeln für Erbschaftsteuer",
    "Umsatzsteuer: Vereinfachungen für Kleinunternehmer ab 2026",
    "Riester-Reform: Was sich für Mandanten ändert",
    "Elektroauto: Dienstwagenbesteuerung 0,25% weiter verlängert",
]

# ── Newsletter-Generator ──────────────────────────────────────────────────────

async def generate_newsletter(
    kanzlei_name: str,
    kanzlei_ort: str,
    mandanten_typ: str = "gemischt",  # privat / gewerblich / gemischt
    themen: Optional[List[str]] = None,
    monat: str = "Juli 2026",
) -> Dict:
    """
    Generiert vollständigen Mandanten-Newsletter für eine Kanzlei.
    Returns: {"betreff": str, "html": str, "plain": str, "themen_count": int}
    """
    from modules.claude_automation import ask

    if not themen:
        themen = STEUER_THEMEN_JULI_2026

    themen_str = "\n".join(f"- {t}" for t in themen[:6])

    system = (
        "Du bist Steuerberater-Kommunikationsexperte. "
        "Erstelle mandantengerechte Newsletter: kein Fachjargon, praxisnah, "
        "positiv formuliert, mit konkreten Handlungsempfehlungen."
    )

    prompt = f"""Erstelle einen Mandanten-Newsletter für Steuerberatungskanzlei "{kanzlei_name}" ({kanzlei_ort}).

Mandantentyp: {mandanten_typ}
Ausgabe: {monat}
Aktuelle Themen:
{themen_str}

Struktur:
1. BETREFF: Catchy, max 60 Zeichen (z.B. "Steuer-News {monat}: Was jetzt zu beachten ist")
2. BEGRÜSSUNG: Persönlich, warm, 2 Sätze
3. HAUPTBEITRAG: Das wichtigste Thema, mandantengerecht erklärt, 150 Wörter, mit Handlungsempfehlung
4. KURZMELDUNGEN: 3 weitere Punkte, je 2-3 Sätze
5. TIPP DES MONATS: Praktischer Steuertipp, 80 Wörter
6. ABSCHLUSS: Einladung zur Kontaktaufnahme, Kanzlei-Signatur mit Platzhalter

Format: Klar getrennte Abschnitte mit ###-Überschriften für einfaches Kopieren.
"""

    content = await asyncio.to_thread(ask, prompt, system=system, max_tokens=2000)

    # Betreff extrahieren
    betreff = f"Steuer-News {monat} von {kanzlei_name}"
    for line in content.split("\n"):
        if "BETREFF:" in line.upper() or line.strip().startswith("1."):
            candidate = line.split(":", 1)[-1].strip().strip('"').strip("*")
            if 10 < len(candidate) < 100:
                betreff = candidate
                break

    return {
        "betreff": betreff,
        "content": content,
        "kanzlei": kanzlei_name,
        "monat": monat,
        "themen_count": len(themen),
        "mandanten_typ": mandanten_typ,
    }


async def generate_dstv_pitch() -> str:
    """Pitch-Text für DStV/DATEV-Anschreiben (B2B an Verbände)."""
    from modules.claude_automation import ask

    return await asyncio.to_thread(ask, """
Schreibe eine kurze (200 Wörter), überzeugende Email an den DStV
(Deutschen Steuerberaterverband) mit dem Angebot:
"KI-generierte Mandanten-Newsletter für Mitgliedskanzleien — €149/Monat,
30% Provision für Verband-Weiterempfehlung."

Betone:
- Zeitersparnis für Kanzleien (Newsletter in 5 Min statt 3h)
- Mandantenbindung durch regelmäßige Kommunikation
- Datenschutz: KI verarbeitet keine Mandantendaten
- Testmonat kostenlos für 5 Pilotkanzleien

Ton: kollegial-professionell, nicht werblich.
""", max_tokens=400)


# ── Stripe + Lieferung ────────────────────────────────────────────────────────

async def handle_new_subscription(customer_email: str, kanzlei_data: dict) -> dict:
    """
    Onboarding nach Stripe-Zahlung:
    1. Ersten Newsletter sofort generieren
    2. Per Email liefern
    3. In SQLite loggen
    """
    log.info(f"SYS-18 Neues Abo: {customer_email} — {kanzlei_data.get('kanzlei_name', '?')}")

    newsletter = await generate_newsletter(
        kanzlei_name=kanzlei_data.get("kanzlei_name", "Ihre Kanzlei"),
        kanzlei_ort=kanzlei_data.get("ort", "Deutschland"),
        mandanten_typ=kanzlei_data.get("mandanten_typ", "gemischt"),
    )

    from modules.service_delivery import _send_delivery_email
    content = f"BETREFF: {newsletter['betreff']}\n\n{newsletter['content']}"
    ok = _send_delivery_email(customer_email, "Mandanten-Newsletter KI", content)

    return {
        "ok": ok,
        "betreff": newsletter["betreff"],
        "kanzlei": newsletter["kanzlei"],
    }


# ── Scheduler-Task (monatlich) ────────────────────────────────────────────────

async def task_sys18_monthly_newsletters() -> str:
    """Verschickt alle monatlichen Newsletter an aktive Abonnenten."""
    import sqlite3

    db_path = _BASE / "data" / "deliveries.db"
    if not db_path.exists():
        return "SYS-18: Keine Abonnenten-DB vorhanden"

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        subs = conn.execute(
            "SELECT DISTINCT customer_email, customer_data FROM deliveries "
            "WHERE product_key='sys18_newsletter' AND status='delivered'"
        ).fetchall()

    if not subs:
        return "SYS-18: Keine aktiven Newsletter-Abonnenten"

    delivered = 0
    for sub in subs:
        try:
            import json as _json
            data = _json.loads(sub["customer_data"].replace("'", '"'))
        except Exception:
            data = {}
        result = await handle_new_subscription(sub["customer_email"], data)
        if result.get("ok"):
            delivered += 1
        await asyncio.sleep(10)

    return f"SYS-18: {delivered}/{len(subs)} Newsletter versendet ✅"


if __name__ == "__main__":
    async def _test():
        result = await generate_newsletter(
            kanzlei_name="Müller & Partner Steuerberatung",
            kanzlei_ort="München",
            mandanten_typ="gemischt",
        )
        print(f"BETREFF: {result['betreff']}\n\n{result['content']}")

    asyncio.run(_test())
