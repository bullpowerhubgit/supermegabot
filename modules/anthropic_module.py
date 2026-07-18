#!/usr/bin/env python3
"""
Anthropic API – Automatisierungs-Modul (SuperMegaBot)
=====================================================

Alle AI-Calls laufen über modules.ai_client (Fallback-Kette):
  OpenClaw/Ollama → Groq → DeepSeek → OpenRouter → Gemini
  → Anthropic → OpenAI → Perplexity

Kompatibilität mit altem API bleibt erhalten (ask, async_ask, Chat, extract, …).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import AsyncIterator, Iterator

from modules.ai_client import (
    ai_complete,
    ai_complete_sync,
    ai_complete_chat,
    ai_complete_chat_sync,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Modelle (Referenz — ai_client wählt den Provider autonom)
# ---------------------------------------------------------------------------
MODEL      = "claude-sonnet-5"           # stark + schnell
FAST_MODEL = "claude-haiku-4-5-20251001" # günstig, für Massen-Tasks

# Kosten-Tabelle (USD per 1M Tokens) — für Referenz / Logging
_COST: dict[str, tuple[float, float]] = {
    "claude-sonnet-5":           (3.00,  15.00),
    "claude-haiku-4-5-20251001": (0.25,   1.25),
    "claude-opus-4-8":           (15.00, 75.00),
}

_DEFAULT_SYSTEM = "Du bist ein präziser Assistent. Antworte knapp."


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def is_configured() -> bool:
    """True wenn mindestens ein AI-Provider mit API-Key konfiguriert ist."""
    from modules.ai_client import _groq, _deepseek, _openrouter, _anthropic, _openai, _gemini
    return any([_groq(), _deepseek(), _openrouter(), _anthropic(), _openai(), _gemini()])


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Kostenschätzung (nur Referenzwert — ai_client verwaltet Budget selbst)."""
    inp, out = _COST.get(model, (3.0, 15.0))
    return (input_tokens * inp + output_tokens * out) / 1_000_000


# ---------------------------------------------------------------------------
# 1. Basis: Frage stellen (sync + async)
# ---------------------------------------------------------------------------
def ask(
    prompt: str,
    system: str = "",
    model: str = MODEL,
    max_tokens: int = 2000,
) -> str:
    """Stellt eine Frage — der `model`-Parameter wird als Hint übergeben,
    ai_client wählt den günstigsten verfügbaren Provider."""
    return ai_complete_sync(
        prompt=prompt,
        system=system or _DEFAULT_SYSTEM,
        max_tokens=max_tokens,
    )


async def async_ask(
    prompt: str,
    system: str = "",
    model: str = MODEL,
    max_tokens: int = 2000,
) -> str:
    return await ai_complete(
        prompt=prompt,
        system=system or _DEFAULT_SYSTEM,
        max_tokens=max_tokens,
    )


# ---------------------------------------------------------------------------
# 2. Streaming (simuliert — ai_client unterstützt kein Echtzeit-Streaming)
# ---------------------------------------------------------------------------
def stream(
    prompt: str,
    system: str = "",
    model: str = MODEL,
    max_tokens: int = 2000,
) -> Iterator[str]:
    """Gibt den vollständigen Text als einzelnen Chunk zurück.
    Echtes Token-Streaming ist über ai_client nicht verfügbar."""
    result = ai_complete_sync(
        prompt=prompt,
        system=system or "Du bist ein präziser Assistent.",
        max_tokens=max_tokens,
    )
    if result:
        yield result


async def async_stream(
    prompt: str,
    system: str = "",
    model: str = MODEL,
    max_tokens: int = 2000,
) -> AsyncIterator[str]:
    """Async-Generator — gibt vollständigen Text als einzelnen Chunk zurück."""
    result = await ai_complete(
        prompt=prompt,
        system=system or "Du bist ein präziser Assistent.",
        max_tokens=max_tokens,
    )
    if result:
        yield result


# ---------------------------------------------------------------------------
# 3. Multi-Turn Konversation
# ---------------------------------------------------------------------------
class Chat:
    """Einfache Konversation mit Verlauf. chat = Chat(); chat.send('Hallo')"""

    def __init__(self, system: str = "", model: str = MODEL, max_tokens: int = 2000):
        self.system     = system or "Du bist ein präziser Assistent."
        self.model      = model
        self.max_tokens = max_tokens
        self.history: list[dict] = []
        self.total_cost = 0.0  # Kosten-Tracking über ai_client nicht verfügbar

    def send(self, message: str) -> str:
        self.history.append({"role": "user", "content": message})
        text = ai_complete_chat_sync(
            messages=self.history,
            system=self.system,
            max_tokens=self.max_tokens,
        )
        self.history.append({"role": "assistant", "content": text})
        return text

    async def async_send(self, message: str) -> str:
        self.history.append({"role": "user", "content": message})
        text = await ai_complete_chat(
            messages=self.history,
            system=self.system,
            max_tokens=self.max_tokens,
        )
        self.history.append({"role": "assistant", "content": text})
        return text

    def reset(self):
        self.history.clear()
        self.total_cost = 0.0


# ---------------------------------------------------------------------------
# 4. Strukturierte Extraktion (JSON-Prompt statt Tool Use)
# ---------------------------------------------------------------------------
def extract(text: str, schema: dict) -> dict:
    """Extrahiert strukturierte Daten per JSON-Prompt (kein Anthropic Tool Use nötig)."""
    schema_desc = json.dumps(schema, ensure_ascii=False, indent=2)
    prompt = (
        f"Extrahiere die Daten aus dem folgenden Text und gib sie als valides JSON-Objekt zurück.\n"
        f"Schema (Feldnamen und Typen):\n{schema_desc}\n"
        f"Antworte NUR mit dem JSON-Objekt, ohne weitere Erklärungen.\n\n"
        f"Text:\n{text}"
    )
    result = ai_complete_sync(
        prompt=prompt,
        system="Du bist ein JSON-Extraktor. Antworte ausschließlich mit validem JSON.",
        max_tokens=2000,
    )
    try:
        m = re.search(r'\{.*\}', result, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return {}


async def async_extract(text: str, schema: dict) -> dict:
    schema_desc = json.dumps(schema, ensure_ascii=False, indent=2)
    prompt = (
        f"Extrahiere die Daten aus dem folgenden Text und gib sie als valides JSON-Objekt zurück.\n"
        f"Schema (Feldnamen und Typen):\n{schema_desc}\n"
        f"Antworte NUR mit dem JSON-Objekt, ohne weitere Erklärungen.\n\n"
        f"Text:\n{text}"
    )
    result = await ai_complete(
        prompt=prompt,
        system="Du bist ein JSON-Extraktor. Antworte ausschließlich mit validem JSON.",
        max_tokens=2000,
    )
    try:
        m = re.search(r'\{.*\}', result, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------------------
# 5. Klassifizieren
# ---------------------------------------------------------------------------
def classify(text: str, categories: list[str]) -> str:
    prompt = (
        f"Ordne den folgenden Text genau EINER Kategorie zu.\n"
        f"Kategorien: {', '.join(categories)}\n"
        f"Antworte NUR mit dem Kategorienamen.\n\n{text}"
    )
    return ask(prompt, max_tokens=20).strip()


async def async_classify(text: str, categories: list[str]) -> str:
    prompt = (
        f"Ordne den folgenden Text genau EINER Kategorie zu.\n"
        f"Kategorien: {', '.join(categories)}\n"
        f"Antworte NUR mit dem Kategorienamen.\n\n{text}"
    )
    return (await async_ask(prompt, max_tokens=20)).strip()


# ---------------------------------------------------------------------------
# 6. PDF / Bild analysieren
# ---------------------------------------------------------------------------
def read_pdf(path: str, frage: str) -> str:
    """PDF analysieren — versucht zuerst Text-Extraktion via pdfplumber."""
    text_content = ""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            text_content = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ImportError:
        text_content = f"[PDF: {Path(path).name} — pdfplumber nicht installiert, Text-Extraktion nicht möglich]"
    except Exception as e:
        text_content = f"[PDF konnte nicht gelesen werden: {e}]"

    return ai_complete_sync(
        prompt=f"{frage}\n\nDokumentinhalt:\n{text_content}",
        system="Du bist ein präziser Dokumenten-Analyst.",
        max_tokens=4000,
    )


def read_image(path: str, frage: str) -> str:
    """Bild-Frage an ai_client — multimodale Bild-Übertragung nicht verfügbar.
    Gibt Text-Antwort auf die Frage zurück."""
    log.warning(
        "read_image('%s'): Multimodale Bildanalyse nicht über ai_client verfügbar — "
        "nur Text-Antwort auf die Frage wird zurückgegeben.",
        Path(path).name,
    )
    return ai_complete_sync(
        prompt=(
            f"Frage zu Bild '{Path(path).name}': {frage}\n"
            f"Hinweis: Das Bild konnte nicht übertragen werden. Beantworte die Frage soweit möglich."
        ),
        system="Du bist ein präziser Assistent.",
        max_tokens=2000,
    )


# ---------------------------------------------------------------------------
# 7. Batch: Ordner abarbeiten (sync + paralleles async)
# ---------------------------------------------------------------------------
def batch_ordner(
    ordner: str,
    muster: str,
    aufgabe: str,
    ausgabe: str = "ergebnisse.json",
) -> list[dict]:
    dateien    = sorted(Path(ordner).glob(muster))
    ergebnisse = []
    for i, datei in enumerate(dateien, 1):
        log.info("[%d/%d] %s", i, len(dateien), datei.name)
        try:
            inhalt = datei.read_text(encoding="utf-8", errors="ignore")
            ergebnisse.append({"datei": datei.name, "ergebnis": ask(f"{aufgabe}\n\n{inhalt}")})
        except Exception:
            log.exception("Fehler bei %s – übersprungen", datei.name)
    Path(ausgabe).write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=2))
    log.info("Fertig: %d Ergebnis(se) → %s", len(ergebnisse), ausgabe)
    return ergebnisse


async def async_batch_ordner(
    ordner: str,
    muster: str,
    aufgabe: str,
    ausgabe: str = "ergebnisse.json",
    concurrency: int = 5,
) -> list[dict]:
    """Paralleles Batch-Processing — bis zu `concurrency` Dateien gleichzeitig."""
    dateien    = sorted(Path(ordner).glob(muster))
    sem        = asyncio.Semaphore(concurrency)
    ergebnisse = []

    async def _process(datei: Path) -> dict:
        async with sem:
            inhalt = datei.read_text(encoding="utf-8", errors="ignore")
            result = await async_ask(f"{aufgabe}\n\n{inhalt}")
            return {"datei": datei.name, "ergebnis": result}

    tasks = [asyncio.create_task(_process(d)) for d in dateien]
    for i, t in enumerate(asyncio.as_completed(tasks), 1):
        try:
            res = await t
            ergebnisse.append(res)
            log.info("[%d/%d] %s", i, len(dateien), res["datei"])
        except Exception as e:
            log.warning("Batch-Fehler: %s", e)

    Path(ausgabe).write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=2))
    log.info("Fertig: %d Ergebnis(se) → %s", len(ergebnisse), ausgabe)
    return ergebnisse


# ---------------------------------------------------------------------------
# BEISPIELE
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not is_configured():
        log.error("Kein AI-Provider konfiguriert (GROQ_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY, …)")
        raise SystemExit(1)

    # (a) Einfache Frage
    antwort = ask("Schreibe eine kurze, freundliche Terminbestätigung per E-Mail.")
    log.info(antwort)

    # (b) Multi-Turn Chat
    # c = Chat(system="Du bist ein Buchhalter.")
    # print(c.send("Was ist doppelte Buchführung?"))
    # print(c.send("Nenn mir ein konkretes Beispiel."))

    # (c) Strukturiert extrahieren
    mail = "Hallo, ich bin Anna Weber, anna@example.com, 0176-1234567. Interesse an einem Rüden, gerne im Herbst."
    daten = extract(mail, {
        "name":      {"type": "string"},
        "email":     {"type": "string"},
        "telefon":   {"type": "string"},
        "anliegen":  {"type": "string"},
        "dringlich": {"type": "boolean"},
    })
    log.info(json.dumps(daten, ensure_ascii=False, indent=2))

    # (d) Klassifizieren
    log.info(classify(mail, ["Anfrage", "Beschwerde", "Rechnung", "Spam"]))

    # (e) Streaming
    # for chunk in stream("Schreibe 5 E-Commerce Tipps"):
    #     print(chunk, end="", flush=True)

    # (f) Async-Batch parallel
    # asyncio.run(async_batch_ordner("./mails", "*.txt", "Fasse zusammen + nächste Aktion."))
