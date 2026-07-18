"""
Rudolf's persönliche KI-Rechte-Hand — Claude als zentraler Assistent.
Eingebunden in: Dashboard, Telegram, Mac-Terminal, Shopify, Stripe, alle Railway-Services.

Import:
    from modules.rudolf_assistant import ask, ask_sync, clear_history
"""

import os
import logging
import asyncio
from collections import deque

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Du bist Rudolfs persönliche Rechte Hand — Claude, direkter KI-Assistent von Rudolf Sarkany.

KONTEXT:
- Owner: Rudolf Sarkany (bullpowersrtkennels@gmail.com, @bullpowerhubgit)
- Haupt-Business: SuperMegaBot SaaS + Shopify ineedit.com.co (Smart Home/Solar/Tech, 13.000+ Produkte)
- Infrastruktur: 9 Railway-Services + 6 Netlify-Sites live
- Zahlungen: Stripe acct_1Tg1U0RJECiV6vSm (bullpowersrtkennels)
- Social: Instagram @aaiitecc, YouTube @AIITECrs, Telegram @DudiRudibot
- DS24: Konto 1581233-... (aiitec-Konto) — 415 Produkte aktiv
- Shopify: autopilot-store-suite-fmbka.myshopify.com / ineedit.com.co

DEINE ROLLE:
- Strategische Beratung: E-Commerce, SaaS, Marketing, Monetarisierung
- Code schreiben, debuggen, deployen
- Business-Entscheidungen: Empfehlung + sofortige Umsetzung
- Probleme SOFORT lösen, nicht endlos analysieren
- Kontext aus vorherigen Nachrichten verwenden

REGELN:
- Antworte IMMER auf Deutsch
- Kein Smalltalk, kein Drumherum — Rudolf braucht Ergebnisse
- Bei Code: fertigen Code sofort liefern
- Bei Problemen: Lösung zuerst, kurze Erklärung danach
- Kurz und präzise — maximal was nötig ist"""

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
FAST_MODEL = "claude-haiku-4-5-20251001"

# Conversation memory: session_id → deque(messages, maxlen=20)
_HISTORY: dict = {}
_MAX_HISTORY = 20


def _client():
    try:
        from modules.anthropic_compat import Anthropic
    except ImportError:
        from anthropic import Anthropic
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY nicht gesetzt")
    return Anthropic(api_key=key)


def _history(session_id: str) -> deque:
    if session_id not in _HISTORY:
        _HISTORY[session_id] = deque(maxlen=_MAX_HISTORY)
    return _HISTORY[session_id]


def ask_sync(message: str, session_id: str = "default", context: str = "") -> str:
    """Synchrone Anfrage an Rudolf's Assistenten mit Gesprächs-Memory."""
    try:
        hist = _history(session_id)
        hist.append({"role": "user", "content": message})

        system = SYSTEM_PROMPT
        if context:
            system += f"\n\nAKTUELLER SYSTEM-KONTEXT:\n{context}"

        response = _client().messages.create(
            model=MODEL,
            max_tokens=2048,
            system=system,
            messages=list(hist),
        )
        answer = response.content[0].text if response.content else "Keine Antwort."
        hist.append({"role": "assistant", "content": answer})
        return answer

    except Exception as e:
        log.error("Rudolf-Assistent Fehler: %s", e)
        err = str(e).lower()
        if "credit" in err or "402" in err or "balance" in err or "529" in err:
            return "⚠️ Anthropic Credits leer — bitte console.anthropic.com → Billing → Credits aufladen!"
        if "api_key" in err or "401" in err:
            return "❌ Anthropic API-Key fehlt oder ungültig."
        return f"❌ Assistent nicht verfügbar: {e}"


async def ask(message: str, session_id: str = "default", context: str = "") -> str:
    """Async-Wrapper für ask_sync."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, ask_sync, message, session_id, context)


def clear_history(session_id: str = "default"):
    """Unterhaltungs-Verlauf einer Session löschen."""
    _HISTORY.pop(session_id, None)


def quick(prompt: str) -> str:
    """Einmalige Frage ohne Session-Memory (für Webhooks, Analysen etc.)."""
    try:
        response = _client().messages.create(
            model=FAST_MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text if response.content else ""
    except Exception as e:
        log.warning("Rudolf-Assistent quick() Fehler: %s", e)
        return ""
