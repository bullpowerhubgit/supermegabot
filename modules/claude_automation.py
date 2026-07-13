"""
Anthropic API – Automatisierungs-Modul (SuperMegaBot)
=====================================================

Setup:
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."      # Key von console.anthropic.com

Import ist immer sicher – der Client wird lazy erzeugt. Fehlt der Key,
schlägt erst der erste Funktionsaufruf fehl (RuntimeError), nicht der Import.
"""

import os
import json
import base64
import logging
from pathlib import Path
from typing import Optional

from anthropic import Anthropic

log = logging.getLogger(__name__)

MODEL = "claude-sonnet-5"                    # schnell + stark; Alternative: "claude-opus-4-8"
FAST_MODEL = "claude-haiku-4-5-20251001"     # billig, für Massen-Tasks

_CLIENT: Optional[Anthropic] = None


# ---------------------------------------------------------------------------
# Client / Health-Check
# ---------------------------------------------------------------------------
def is_configured() -> bool:
    """True, wenn ein API-Key gesetzt ist. Für den Dashboard-Health-Check."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _client() -> Anthropic:
    """Lazy Singleton. Erzeugt den Client erst beim ersten Aufruf."""
    global _CLIENT
    if _CLIENT is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY ist nicht gesetzt. "
                "Key auf console.anthropic.com erzeugen und als Umgebungsvariable setzen."
            )
        log.debug("Anthropic-Client wird initialisiert (Modell: %s)", MODEL)
        _CLIENT = Anthropic(api_key=key)
    return _CLIENT


# ---------------------------------------------------------------------------
# 1. Basis: eine Frage stellen
# ---------------------------------------------------------------------------
def ask(prompt: str, system: str = "", model: str = MODEL, max_tokens: int = 2000) -> str:
    log.debug("ask(): model=%s, prompt_len=%d", model, len(prompt))
    resp = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system or "Du bist ein präziser Assistent. Antworte knapp.",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


# ---------------------------------------------------------------------------
# 2. Strukturierte Daten extrahieren (garantiertes JSON)
#    -> Rechnungen, E-Mails, Formulare, Produktdaten ...
# ---------------------------------------------------------------------------
def extract(text: str, schema: dict) -> dict:
    log.debug("extract(): felder=%s", list(schema))
    resp = _client().messages.create(
        model=MODEL,
        max_tokens=2000,
        tools=[{
            "name": "ergebnis",
            "description": "Gib die extrahierten Daten zurück.",
            "input_schema": {"type": "object", "properties": schema, "required": list(schema)},
        }],
        tool_choice={"type": "tool", "name": "ergebnis"},   # erzwingt strukturierte Ausgabe
        messages=[{"role": "user", "content": f"Extrahiere die Daten aus diesem Text:\n\n{text}"}],
    )
    return resp.content[0].input


# ---------------------------------------------------------------------------
# 3. Klassifizieren (Massen-Task -> billiges Modell)
# ---------------------------------------------------------------------------
def classify(text: str, categories: list[str]) -> str:
    prompt = (
        f"Ordne den folgenden Text genau EINER Kategorie zu.\n"
        f"Kategorien: {', '.join(categories)}\n"
        f"Antworte NUR mit dem Kategorienamen.\n\n{text}"
    )
    ergebnis = ask(prompt, model=FAST_MODEL, max_tokens=20).strip()
    log.debug("classify(): -> %s", ergebnis)
    return ergebnis


# ---------------------------------------------------------------------------
# 4. PDF / Bild analysieren
# ---------------------------------------------------------------------------
def read_pdf(path: str, frage: str) -> str:
    log.info("read_pdf(): %s", path)
    data = base64.b64encode(Path(path).read_bytes()).decode()
    resp = _client().messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf", "data": data}},
                {"type": "text", "text": frage},
            ],
        }],
    )
    return resp.content[0].text


def read_image(path: str, frage: str) -> str:
    log.info("read_image(): %s", path)
    data = base64.b64encode(Path(path).read_bytes()).decode()
    suffix = Path(path).suffix.lower().lstrip(".").replace("jpg", "jpeg")
    resp = _client().messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": f"image/{suffix}", "data": data}},
                {"type": "text", "text": frage},
            ],
        }],
    )
    return resp.content[0].text


# ---------------------------------------------------------------------------
# 5. Batch: ganzen Ordner abarbeiten
# ---------------------------------------------------------------------------
def batch_ordner(ordner: str, muster: str, aufgabe: str, ausgabe: str = "ergebnisse.json") -> list[dict]:
    dateien = sorted(Path(ordner).glob(muster))
    log.info("batch_ordner(): %d Datei(en) in %s", len(dateien), ordner)

    ergebnisse = []
    for i, datei in enumerate(dateien, 1):
        log.info("[%d/%d] %s", i, len(dateien), datei.name)
        try:
            inhalt = datei.read_text(encoding="utf-8", errors="ignore")
            ergebnisse.append({"datei": datei.name, "ergebnis": ask(f"{aufgabe}\n\n{inhalt}")})
        except Exception:
            log.exception("Fehler bei %s – wird übersprungen", datei.name)

    Path(ausgabe).write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=2))
    log.info("Fertig: %d Ergebnis(se) -> %s", len(ergebnisse), ausgabe)
    return ergebnisse


# ---------------------------------------------------------------------------
# BEISPIELE
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not is_configured():
        log.error("ANTHROPIC_API_KEY fehlt – bitte setzen.")
        raise SystemExit(1)

    # (a) Einfache Frage
    log.info(ask("Schreibe eine kurze, freundliche Terminbestätigung per E-Mail."))

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
    log.info(json.dumps(daten, ensure_ascii=False, indent=2))

    # (c) Klassifizieren
    log.info(classify(mail, ["Anfrage", "Beschwerde", "Rechnung", "Spam"]))

    # (d) PDF auswerten
    # log.info(read_pdf("rechnung.pdf", "Nenne Rechnungsnummer, Datum und Gesamtbetrag."))

    # (e) Ordner abarbeiten
    # batch_ordner("./mails", "*.txt", "Fasse in einem Satz zusammen und nenne die nächste Aktion.")
