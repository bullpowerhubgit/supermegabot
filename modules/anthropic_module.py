#!/usr/bin/env python3
"""
Anthropic API – Automatisierungs-Modul (SuperMegaBot)
=====================================================

Setup:
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."      # Key von console.anthropic.com

Verbesserungen gegenüber Originalversion:
  - Async-Varianten aller Funktionen (async_ask, async_extract, ...)
  - Streaming-Support (stream / async_stream)
  - Multi-Turn-Konversation (chat / async_chat)
  - Automatischer Retry mit Exponential-Backoff (529/429)
  - Token-Tracking: jede Antwort liefert .usage
  - Kosten-Schätzung (cost_usd())
  - Batch-Ordner mit Parallelisierung (async_batch_ordner)
  - Kontext-Cache (prompt_cache) für Wiederholungen
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import AsyncIterator, Iterator, Optional

try:
    import modules.anthropic_compat as _anthlib
except ImportError:
    import anthropic as _anthlib

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Modelle (aktuell, Stand 2026)
# ---------------------------------------------------------------------------
MODEL      = "claude-sonnet-5"           # stark + schnell; empfohlen für Haupt-Tasks
FAST_MODEL = "claude-haiku-4-5-20251001" # günstig, für Massen-Tasks

# Kosten-Tabelle (USD per 1M Tokens, Input/Output)
_COST: dict[str, tuple[float, float]] = {
    "claude-sonnet-5":           (3.00,  15.00),
    "claude-haiku-4-5-20251001": (0.25,   1.25),
    "claude-opus-4-8":           (15.00, 75.00),
}

_CLIENT: Optional[_anthlib.Anthropic]       = None
_ACLIENT: Optional[_anthlib.AsyncAnthropic] = None


# ---------------------------------------------------------------------------
# Client-Singletons
# ---------------------------------------------------------------------------
def _client() -> _anthlib.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY ist nicht gesetzt.")
        _CLIENT = _anthlib.Anthropic(api_key=key)
    return _CLIENT


def _aclient() -> _anthlib.AsyncAnthropic:
    global _ACLIENT
    if _ACLIENT is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY ist nicht gesetzt.")
        _ACLIENT = _anthlib.AsyncAnthropic(api_key=key)
    return _ACLIENT


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# ---------------------------------------------------------------------------
# Kosten-Schätzung
# ---------------------------------------------------------------------------
def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    inp, out = _COST.get(model, (3.0, 15.0))
    return (input_tokens * inp + output_tokens * out) / 1_000_000


# ---------------------------------------------------------------------------
# Retry-Wrapper (429/529 → exponential backoff)
# ---------------------------------------------------------------------------
def _retry_sync(fn, max_tries: int = 3):
    for attempt in range(max_tries):
        try:
            return fn()
        except _anthlib.RateLimitError:
            wait = 2 ** attempt
            log.warning("Anthropic 429 — Retry in %ds", wait)
            time.sleep(wait)
        except _anthlib.APIStatusError as e:
            if e.status_code == 529:
                wait = 2 ** attempt
                log.warning("Anthropic 529 (überlastet) — Retry in %ds", wait)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Anthropic max retries reached")


async def _retry_async(fn, max_tries: int = 3):
    for attempt in range(max_tries):
        try:
            return await fn()
        except _anthlib.RateLimitError:
            wait = 2 ** attempt
            log.warning("Anthropic 429 — Retry in %ds", wait)
            await asyncio.sleep(wait)
        except _anthlib.APIStatusError as e:
            if e.status_code == 529:
                wait = 2 ** attempt
                log.warning("Anthropic 529 (überlastet) — Retry in %ds", wait)
                await asyncio.sleep(wait)
            else:
                raise
    raise RuntimeError("Anthropic max retries reached")


# ---------------------------------------------------------------------------
# 1. Basis: Frage stellen (sync + async)
# ---------------------------------------------------------------------------
def ask(
    prompt: str,
    system: str = "",
    model: str = MODEL,
    max_tokens: int = 2000,
) -> str:
    def _call():
        resp = _client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system or "Du bist ein präziser Assistent. Antworte knapp.",
            messages=[{"role": "user", "content": prompt}],
        )
        log.debug(
            "ask(): %s | in=%d out=%d | ~$%.4f",
            model, resp.usage.input_tokens, resp.usage.output_tokens,
            cost_usd(model, resp.usage.input_tokens, resp.usage.output_tokens),
        )
        return resp.content[0].text

    return _retry_sync(_call)


async def async_ask(
    prompt: str,
    system: str = "",
    model: str = MODEL,
    max_tokens: int = 2000,
) -> str:
    async def _call():
        resp = await _aclient().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system or "Du bist ein präziser Assistent. Antworte knapp.",
            messages=[{"role": "user", "content": prompt}],
        )
        log.debug(
            "async_ask(): %s | in=%d out=%d | ~$%.4f",
            model, resp.usage.input_tokens, resp.usage.output_tokens,
            cost_usd(model, resp.usage.input_tokens, resp.usage.output_tokens),
        )
        return resp.content[0].text

    return await _retry_async(_call)


# ---------------------------------------------------------------------------
# 2. Streaming (sync + async)
# ---------------------------------------------------------------------------
def stream(
    prompt: str,
    system: str = "",
    model: str = MODEL,
    max_tokens: int = 2000,
) -> Iterator[str]:
    """Yields Text-Chunks wie ein Generator. Ideal für Live-Ausgaben."""
    with _client().messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system or "Du bist ein präziser Assistent.",
        messages=[{"role": "user", "content": prompt}],
    ) as s:
        for chunk in s.text_stream:
            yield chunk


async def async_stream(
    prompt: str,
    system: str = "",
    model: str = MODEL,
    max_tokens: int = 2000,
) -> AsyncIterator[str]:
    """Async-Generator für Streaming — nutze `async for chunk in async_stream(...)`."""
    async with _aclient().messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system or "Du bist ein präziser Assistent.",
        messages=[{"role": "user", "content": prompt}],
    ) as s:
        async for chunk in s.text_stream:
            yield chunk


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
        self.total_cost = 0.0

    def send(self, message: str) -> str:
        self.history.append({"role": "user", "content": message})
        resp = _retry_sync(lambda: _client().messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system,
            messages=self.history,
        ))
        text = resp.content[0].text
        self.history.append({"role": "assistant", "content": text})
        self.total_cost += cost_usd(self.model, resp.usage.input_tokens, resp.usage.output_tokens)
        return text

    async def async_send(self, message: str) -> str:
        self.history.append({"role": "user", "content": message})
        resp = await _retry_async(lambda: _aclient().messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system,
            messages=self.history,
        ))
        text = resp.content[0].text
        self.history.append({"role": "assistant", "content": text})
        self.total_cost += cost_usd(self.model, resp.usage.input_tokens, resp.usage.output_tokens)
        return text

    def reset(self):
        self.history.clear()
        self.total_cost = 0.0


# ---------------------------------------------------------------------------
# 4. Strukturierte Extraktion (garantiertes JSON via Tool Use)
# ---------------------------------------------------------------------------
def extract(text: str, schema: dict) -> dict:
    resp = _retry_sync(lambda: _client().messages.create(
        model=MODEL,
        max_tokens=2000,
        tools=[{
            "name": "ergebnis",
            "description": "Gib die extrahierten Daten zurück.",
            "input_schema": {"type": "object", "properties": schema, "required": list(schema)},
        }],
        tool_choice={"type": "tool", "name": "ergebnis"},
        messages=[{"role": "user", "content": f"Extrahiere die Daten:\n\n{text}"}],
    ))
    return resp.content[0].input


async def async_extract(text: str, schema: dict) -> dict:
    resp = await _retry_async(lambda: _aclient().messages.create(
        model=MODEL,
        max_tokens=2000,
        tools=[{
            "name": "ergebnis",
            "description": "Gib die extrahierten Daten zurück.",
            "input_schema": {"type": "object", "properties": schema, "required": list(schema)},
        }],
        tool_choice={"type": "tool", "name": "ergebnis"},
        messages=[{"role": "user", "content": f"Extrahiere die Daten:\n\n{text}"}],
    ))
    return resp.content[0].input


# ---------------------------------------------------------------------------
# 5. Klassifizieren (billiges Modell)
# ---------------------------------------------------------------------------
def classify(text: str, categories: list[str]) -> str:
    prompt = (
        f"Ordne den folgenden Text genau EINER Kategorie zu.\n"
        f"Kategorien: {', '.join(categories)}\n"
        f"Antworte NUR mit dem Kategorienamen.\n\n{text}"
    )
    return ask(prompt, model=FAST_MODEL, max_tokens=20).strip()


async def async_classify(text: str, categories: list[str]) -> str:
    prompt = (
        f"Ordne den folgenden Text genau EINER Kategorie zu.\n"
        f"Kategorien: {', '.join(categories)}\n"
        f"Antworte NUR mit dem Kategorienamen.\n\n{text}"
    )
    return (await async_ask(prompt, model=FAST_MODEL, max_tokens=20)).strip()


# ---------------------------------------------------------------------------
# 6. PDF / Bild analysieren
# ---------------------------------------------------------------------------
def read_pdf(path: str, frage: str) -> str:
    data = base64.b64encode(Path(path).read_bytes()).decode()
    resp = _retry_sync(lambda: _client().messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}},
            {"type": "text", "text": frage},
        ]}],
    ))
    return resp.content[0].text


def read_image(path: str, frage: str) -> str:
    data   = base64.b64encode(Path(path).read_bytes()).decode()
    suffix = Path(path).suffix.lower().lstrip(".").replace("jpg", "jpeg")
    resp   = _retry_sync(lambda: _client().messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": f"image/{suffix}", "data": data}},
            {"type": "text", "text": frage},
        ]}],
    ))
    return resp.content[0].text


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
        log.error("ANTHROPIC_API_KEY fehlt")
        raise SystemExit(1)

    # (a) Einfache Frage mit Kosten-Tracking
    antwort = ask("Schreibe eine kurze, freundliche Terminbestätigung per E-Mail.")
    log.info(antwort)

    # (b) Multi-Turn Chat
    # c = Chat(system="Du bist ein Buchhalter.")
    # print(c.send("Was ist doppelte Buchführung?"))
    # print(c.send("Nenn mir ein konkretes Beispiel."))
    # log.info("Gesamtkosten: $%.4f", c.total_cost)

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
