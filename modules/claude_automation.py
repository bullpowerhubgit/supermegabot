"""
Anthropic API – Automatisierungs-Modul (SuperMegaBot)
=====================================================

Setup:
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."      # Key von console.anthropic.com

Import ist immer sicher — der Client wird lazy erzeugt. Fehlt der Key,
schlägt erst der erste Funktionsaufruf fehl (RuntimeError), nicht der Import.

Nutzung:
    from modules.claude_automation import ask, extract, classify, is_configured
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
FAST_MODEL = os.getenv("ANTHROPIC_FAST_MODEL", "claude-haiku-4-5-20251001")

_CLIENT: Optional[Any] = None


def is_configured() -> bool:
    """Für Dashboard-Health-Check — kein API-Call, kein Client."""
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    return bool(key) and not key.startswith("your_")


def _client():
    """Lazy Singleton. Erzeugt den Client erst beim ersten Aufruf."""
    global _CLIENT
    if _CLIENT is None:
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY ist nicht gesetzt. "
                "Key auf console.anthropic.com erzeugen und als Umgebungsvariable setzen."
            )
        from anthropic import Anthropic
        logger.debug("Anthropic-Client initialisiert (model=%s)", MODEL)
        _CLIENT = Anthropic(api_key=key)
    return _CLIENT


def ping() -> Tuple[bool, str]:
    """Health-Check: Key gültig? Credits vorhanden?"""
    if not is_configured():
        return False, "ANTHROPIC_API_KEY nicht gesetzt"
    try:
        _client().messages.create(
            model=FAST_MODEL,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        return True, "Verbunden"
    except Exception as exc:
        msg = str(exc)
        if "credit balance is too low" in msg.lower():
            return True, "Key OK — Credits aufladen (console.anthropic.com)"
        if "401" in msg or "authentication" in msg.lower():
            return False, "Key ungültig"
        logger.warning("Anthropic ping fehlgeschlagen: %s", msg[:120])
        return False, msg[:120]


def ask(prompt: str, system: str = "", model: str = MODEL, max_tokens: int = 2000) -> str:
    logger.debug("ask(): model=%s prompt_len=%d", model, len(prompt))
    resp = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system or "Du bist ein präziser Assistent. Antworte knapp.",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


async def ask_async(prompt: str, system: str = "", max_tokens: int = 2000) -> str:
    """Wie ask(), mit Fallback auf ai_client wenn Anthropic-Credits leer."""
    try:
        return ask(prompt, system=system, max_tokens=max_tokens)
    except Exception as exc:
        if "credit balance is too low" not in str(exc).lower():
            raise
        logger.info("Anthropic-Credits leer — Fallback auf ai_client")
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, system=system, max_tokens=max_tokens)


def extract(text: str, schema: dict) -> dict:
    logger.debug("extract(): felder=%s", list(schema))
    resp = _client().messages.create(
        model=MODEL,
        max_tokens=2000,
        tools=[{
            "name": "ergebnis",
            "description": "Gib die extrahierten Daten zurück.",
            "input_schema": {"type": "object", "properties": schema, "required": list(schema)},
        }],
        tool_choice={"type": "tool", "name": "ergebnis"},
        messages=[{"role": "user", "content": f"Extrahiere die Daten aus diesem Text:\n\n{text}"}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return block.input
    return {}


def classify(text: str, categories: List[str]) -> str:
    prompt = (
        f"Ordne den folgenden Text genau EINER Kategorie zu.\n"
        f"Kategorien: {', '.join(categories)}\n"
        f"Antworte NUR mit dem Kategorienamen.\n\n{text}"
    )
    ergebnis = ask(prompt, model=FAST_MODEL, max_tokens=20).strip()
    logger.debug("classify(): -> %s", ergebnis)
    return ergebnis


def read_pdf(path: str, frage: str) -> str:
    logger.info("read_pdf(): %s", path)
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
    logger.info("read_image(): %s", path)
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


def batch_ordner(ordner: str, muster: str, aufgabe: str, ausgabe: str = "ergebnisse.json") -> List[Dict]:
    dateien = sorted(Path(ordner).glob(muster))
    logger.info("batch_ordner(): %d Datei(en) in %s", len(dateien), ordner)

    ergebnisse: List[Dict] = []
    for i, datei in enumerate(dateien, 1):
        logger.info("[%d/%d] %s", i, len(dateien), datei.name)
        try:
            inhalt = datei.read_text(encoding="utf-8", errors="ignore")
            ergebnisse.append({"datei": datei.name, "ergebnis": ask(f"{aufgabe}\n\n{inhalt}")})
        except Exception:
            logger.exception("Fehler bei %s — wird übersprungen", datei.name)

    Path(ausgabe).write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=2))
    logger.info("Fertig: %d Ergebnis(se) → %s", len(ergebnisse), ausgabe)
    return ergebnisse