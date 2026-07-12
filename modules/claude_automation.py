"""
Anthropic/Claude Automation-Toolkit — SuperMegaBot
Basis-Funktionen: Fragen, Extrahieren, Klassifizieren, PDF/Bild analysieren, Batch.
"""

import os
import json
import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-5"
FAST_MODEL = "claude-haiku-4-5-20251001"


def _client():
    from anthropic import Anthropic
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY nicht gesetzt")
    return Anthropic(api_key=key)


def ask(prompt: str, system: str = "", model: str = MODEL, max_tokens: int = 2000) -> str:
    """Einfache Text-Anfrage an Claude."""
    c = _client()
    resp = c.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system or "Du bist ein präziser Assistent. Antworte knapp.",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def extract(text: str, schema: dict) -> dict:
    """Strukturierte Daten aus Text extrahieren — garantiert JSON zurück."""
    c = _client()
    resp = c.messages.create(
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
    return resp.content[0].input


def classify(text: str, categories: list) -> str:
    """Text einer Kategorie zuordnen (Haiku — schnell & billig)."""
    prompt = (
        f"Ordne den folgenden Text genau EINER Kategorie zu.\n"
        f"Kategorien: {', '.join(categories)}\n"
        f"Antworte NUR mit dem Kategorienamen.\n\n{text}"
    )
    return ask(prompt, model=FAST_MODEL, max_tokens=20).strip()


def read_pdf(path: str, frage: str) -> str:
    """PDF analysieren und Frage beantworten."""
    c = _client()
    data = base64.b64encode(Path(path).read_bytes()).decode()
    resp = c.messages.create(
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
    """Bild analysieren und Frage beantworten."""
    c = _client()
    data = base64.b64encode(Path(path).read_bytes()).decode()
    suffix = Path(path).suffix.lower().replace(".", "").replace("jpg", "jpeg")
    resp = c.messages.create(
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


def batch_ordner(ordner: str, muster: str, aufgabe: str, ausgabe: str = "ergebnisse.json") -> list:
    """Ganzen Ordner mit Claude abarbeiten."""
    ergebnisse = []
    for datei in sorted(Path(ordner).glob(muster)):
        logger.info("claude_automation batch: %s", datei.name)
        inhalt = datei.read_text(encoding="utf-8", errors="ignore")
        ergebnisse.append({"datei": datei.name, "ergebnis": ask(f"{aufgabe}\n\n{inhalt}")})
    Path(ausgabe).write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=2))
    logger.info("claude_automation batch done: %d Dateien → %s", len(ergebnisse), ausgabe)
    return ergebnisse


def is_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", ""))
