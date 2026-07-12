#!/usr/bin/env python3
"""
Anthropic API – Automatisierungs-Starterkit (CLI)
=================================================

Setup (einmalig):
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."

Nutzung:
    python claude_automation.py
"""
import json
import logging

from modules.claude_automation import (
    MODEL,
    FAST_MODEL,
    ask,
    batch_ordner,
    classify,
    extract,
    is_configured,
    ping,
    read_image,
    read_pdf,
)

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not is_configured():
        logger.error("ANTHROPIC_API_KEY fehlt — export ANTHROPIC_API_KEY=sk-ant-...")
        raise SystemExit(1)

    ok, detail = ping()
    logger.info("Ping: %s — %s", "OK" if ok else "FAIL", detail)
    if not ok:
        raise SystemExit(1)

    # (a) Einfache Frage
    logger.info(ask("Schreibe eine kurze, freundliche Terminbestätigung per E-Mail."))

    # (b) Strukturiert extrahieren
    mail = """
    Hallo, ich hätte Interesse an einem Welpen. Mein Name ist Anna Weber,
    erreichbar unter anna.weber@example.com oder 0176 1234567.
    Ich suche einen Rüden, gerne im Herbst.
    """
    daten = extract(mail, {
        "name":      {"type": "string"},
        "email":     {"type": "string"},
        "telefon":   {"type": "string"},
        "anliegen":  {"type": "string"},
        "dringlich": {"type": "boolean"},
    })
    logger.info(json.dumps(daten, ensure_ascii=False, indent=2))

    # (c) Klassifizieren
    logger.info(classify(mail, ["Anfrage", "Beschwerde", "Rechnung", "Spam"]))

    # (d) PDF auswerten
    # logger.info(read_pdf("rechnung.pdf", "Nenne Rechnungsnummer, Datum und Gesamtbetrag."))

    # (e) Ordner abarbeiten
    # batch_ordner("./mails", "*.txt", "Fasse in einem Satz zusammen und nenne die nächste Aktion.")