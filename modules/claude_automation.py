"""
AI Automatisierungs-Modul (SuperMegaBot)
=========================================

Alle KI-Calls laufen über modules.ai_client.ai_complete() mit automatischem Fallback:
OpenClaw/Ollama → Groq → DeepSeek → OpenRouter → Gemini → Anthropic → OpenAI → Perplexity

Setup:
    Mindestens einen Provider-Key setzen (GROQ_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY …)
    Import ist immer sicher. Fehlt jeder Key, schlägt erst der erste Aufruf fehl.
"""

import asyncio
import os
import json
import base64
import logging
from pathlib import Path
from typing import Optional

from modules.ai_client import ai_complete, ai_complete_sync

try:
    from modules.ai_budget_guard import is_allowed, record_usage, record_blocked
    _GUARD_AVAILABLE = True
except ImportError:
    _GUARD_AVAILABLE = False
    def is_allowed(caller=""): return (True, caller)
    def record_usage(i, o, caller=""): pass
    def record_blocked(): pass

log = logging.getLogger(__name__)

MODEL      = "claude-sonnet-5"               # Hinweis-Konstante; ai_client wählt Provider
FAST_MODEL = "claude-haiku-4-5-20251001"     # Hinweis-Konstante für Massen-Tasks


# ---------------------------------------------------------------------------
# Client / Health-Check
# ---------------------------------------------------------------------------
def is_configured() -> bool:
    """True, wenn mindestens ein AI-Provider-Key gesetzt ist."""
    return bool(
        os.getenv("GROQ_API_KEY") or
        os.getenv("OPENROUTER_API_KEY") or
        os.getenv("ANTHROPIC_API_KEY") or
        os.getenv("OPENAI_API_KEY") or
        os.getenv("DEEPSEEK_API_KEY") or
        os.getenv("GEMINI_API_KEY")
    )


def is_available() -> bool:
    return is_configured()


# ---------------------------------------------------------------------------
# 1. Basis: eine Frage stellen (NUR Revenue-Module erlaubt)
# ---------------------------------------------------------------------------
def ask(prompt: str, system: str = "", model: str = MODEL, max_tokens: int = 1000,
        fallback: str = "", caller: str = "") -> str:
    allowed, reason = is_allowed(caller)
    if not allowed:
        log.warning("AI BLOCKED: %s", reason)
        record_blocked()
        if fallback:
            return fallback
        raise PermissionError(f"AI Budget Guard: {reason}")

    log.debug("ask(): caller=%s", reason)
    try:
        text = ai_complete_sync(
            prompt=prompt,
            system=system or "Du bist ein präziser Assistent. Antworte knapp.",
            max_tokens=max_tokens,
        )
        # Approximative Usage-Erfassung (1 Token ≈ 4 Zeichen)
        approx_in  = max(1, len(prompt) // 4)
        approx_out = max(1, len(text) // 4)
        record_usage(approx_in, approx_out, reason)
        return text
    except PermissionError:
        raise
    except Exception as e:
        log.warning("ai_complete ask() Fehler (%s)", type(e).__name__)
        if fallback:
            return fallback
        raise


# ---------------------------------------------------------------------------
# 2. Strukturierte Daten extrahieren (garantiertes JSON)
#    -> Rechnungen, E-Mails, Formulare, Produktdaten ...
# ---------------------------------------------------------------------------
def extract(text: str, schema: dict) -> dict:
    log.debug("extract(): felder=%s", list(schema))
    field_desc = json.dumps(schema, ensure_ascii=False, indent=2)
    prompt = (
        f"Extrahiere die Daten aus dem folgenden Text und gib sie als JSON-Objekt zurück.\n"
        f"Erwartete Felder (JSON Schema):\n{field_desc}\n\n"
        f"Antworte NUR mit dem JSON-Objekt — kein zusätzlicher Text, keine Erklärung.\n\n"
        f"Text:\n{text}"
    )
    raw = ai_complete_sync(
        prompt=prompt,
        system="Du bist ein Datenextraktor. Antworte ausschließlich mit validem JSON.",
        max_tokens=2000,
    )
    raw = raw.strip()
    # Markdown-Code-Block entfernen, falls das Modell einen erzeugt hat
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) >= 2:
            inner = parts[1]
            if inner.startswith("json"):
                inner = inner[4:]
            raw = inner.strip()
    return json.loads(raw)


# ---------------------------------------------------------------------------
# 3. Klassifizieren (Massen-Task -> billiges Modell)
# ---------------------------------------------------------------------------
def classify(text: str, categories: list[str]) -> str:
    prompt = (
        f"Ordne den folgenden Text genau EINER Kategorie zu.\n"
        f"Kategorien: {', '.join(categories)}\n"
        f"Antworte NUR mit dem Kategorienamen.\n\n{text}"
    )
    ergebnis = ask(prompt, max_tokens=20).strip()
    log.debug("classify(): -> %s", ergebnis)
    return ergebnis


# ---------------------------------------------------------------------------
# 4. PDF / Bild analysieren
# ---------------------------------------------------------------------------
def read_pdf(path: str, frage: str) -> str:
    """
    PDF auswerten. Extrahiert Text via pdfminer oder pypdf, dann ai_complete.
    Kein direkter Anthropic-Call — läuft durch den vollständigen Fallback-Stack.
    """
    log.info("read_pdf(): %s", path)
    pdf_text = _extract_pdf_text(path)
    if not pdf_text:
        raise RuntimeError(f"PDF-Text konnte nicht extrahiert werden: {path}")
    prompt = f"{frage}\n\nDokument-Inhalt:\n{pdf_text[:12000]}"
    return ai_complete_sync(
        prompt=prompt,
        system="Du analysierst PDF-Dokumente. Antworte präzise und strukturiert.",
        max_tokens=4000,
    )


def _extract_pdf_text(path: str) -> str:
    """Text aus PDF extrahieren (pdfminer → pypdf)."""
    try:
        from pdfminer.high_level import extract_text
        return extract_text(path) or ""
    except ImportError:
        pass
    except Exception as e:
        log.debug("pdfminer Fehler: %s", e)

    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        pass
    except Exception as e:
        log.debug("pypdf Fehler: %s", e)

    return ""


def read_image(path: str, frage: str) -> str:
    """
    Bild analysieren. Versucht zuerst OpenRouter Vision-Modell (Gemini Flash),
    dann Text-Fallback via ai_complete.
    """
    log.info("read_image(): %s", path)
    data      = base64.b64encode(Path(path).read_bytes()).decode()
    suffix    = Path(path).suffix.lower().lstrip(".").replace("jpg", "jpeg")
    media_type = f"image/{suffix}"

    # OpenRouter Vision-Modell (unterstützt multimodale Eingaben)
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    if openrouter_key:
        result = _try_openrouter_vision(data, media_type, frage, openrouter_key)
        if result:
            return result

    # Text-Fallback: ai_complete ohne Bilddaten
    log.warning("read_image(): Kein Vision-Provider verfügbar — Text-Fallback für %s", path)
    return ai_complete_sync(
        prompt=(
            f"Ich habe ein Bild vom Typ '{suffix}' (Dateiname: {Path(path).name}). "
            f"Bitte beantworte folgende Frage so gut wie möglich: {frage}\n"
            f"Hinweis: Das Bild selbst steht nicht zur Verfügung."
        ),
        system="Du bist ein Bildanalyst.",
        max_tokens=2000,
    )


def _try_openrouter_vision(data: str, media_type: str, frage: str, key: str) -> str:
    """Versucht OpenRouter mit Vision-Modell (Gemini Flash)."""
    import aiohttp

    async def _call() -> str:
        payload = {
            "model": "google/gemini-2.0-flash-001",
            "max_tokens": 2000,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}},
                    {"type": "text", "text": frage},
                ],
            }],
        }
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://supermegabot-production.up.railway.app",
                    },
                    json=payload,
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        return d.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            log.debug("OpenRouter Vision Fehler: %s", e)
        return ""

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _call())
                return future.result(timeout=35)
        else:
            return loop.run_until_complete(_call())
    except Exception as e:
        log.debug("_try_openrouter_vision error: %s", e)
        return ""


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
        log.error("Kein AI-Provider konfiguriert — bitte GROQ_API_KEY, OPENROUTER_API_KEY oder ANTHROPIC_API_KEY setzen.")
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
