"""
Anthropic/Claude Automation-Toolkit — SuperMegaBot
Fragen, Extrahieren, Klassifizieren, PDF/Bild, Batch.
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

_CLIENT: Any = None


def is_configured() -> bool:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    return bool(key) and not key.startswith("your_")


def _client():
    global _CLIENT
    if _CLIENT is None:
        from anthropic import Anthropic
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY nicht gesetzt")
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
        return False, msg[:120]


def ask(prompt: str, system: str = "", model: str = MODEL, max_tokens: int = 2000) -> str:
    resp = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system or "Du bist ein präziser Assistent. Antworte knapp.",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


async def ask_async(prompt: str, system: str = "", max_tokens: int = 2000) -> str:
    """Mit Fallback auf ai_client wenn Anthropic-Credits leer."""
    try:
        return ask(prompt, system=system, max_tokens=max_tokens)
    except Exception as exc:
        if "credit balance is too low" not in str(exc).lower():
            raise
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, system=system, max_tokens=max_tokens)


def extract(text: str, schema: dict) -> dict:
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
    return ask(prompt, model=FAST_MODEL, max_tokens=20).strip()


def read_pdf(path: str, frage: str) -> str:
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
    ergebnisse: List[Dict] = []
    for datei in sorted(Path(ordner).glob(muster)):
        logger.info("batch: %s", datei.name)
        try:
            inhalt = datei.read_text(encoding="utf-8", errors="ignore")
            ergebnisse.append({"datei": datei.name, "ergebnis": ask(f"{aufgabe}\n\n{inhalt}")})
        except Exception as exc:
            ergebnisse.append({"datei": datei.name, "error": str(exc)[:200]})
    Path(ausgabe).write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=2))
    return ergebnisse