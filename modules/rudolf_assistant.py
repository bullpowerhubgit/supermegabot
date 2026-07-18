"""
Rudolf's persönliche KI-Rechte-Hand — automatischer Provider-Fallback.
Nutzt ai_client.py: Groq (gratis) → DeepSeek → OpenRouter → Anthropic.
Kein Anthropic-Guthaben nötig solange Groq/OpenRouter verfügbar.

Import:
    from modules.rudolf_assistant import ask, ask_sync, clear_history
"""

import os
import logging
import asyncio
from collections import deque

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Du bist Rudolfs persönliche Rechte Hand — direkter KI-Assistent von Rudolf Sarkany.

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

# Conversation memory: session_id → deque(messages, maxlen=20)
_HISTORY: dict = {}


def _history(session_id: str) -> deque:
    if session_id not in _HISTORY:
        _HISTORY[session_id] = deque(maxlen=20)
    return _HISTORY[session_id]


async def ask(message: str, session_id: str = "default", context: str = "") -> str:
    """Async-Anfrage mit Session-Memory. Nutzt automatisch besten verfügbaren Provider."""
    from modules.ai_client import ai_complete_chat

    hist = _history(session_id)
    hist.append({"role": "user", "content": message})

    system = SYSTEM_PROMPT
    if context:
        system += f"\n\nAKTUELLER SYSTEM-KONTEXT:\n{context}"

    try:
        answer = await ai_complete_chat(list(hist), system=system, max_tokens=2048)
        if not answer:
            answer = "⚠️ Alle AI-Provider gerade nicht erreichbar — bitte kurz warten."
        hist.append({"role": "assistant", "content": answer})
        return answer
    except Exception as e:
        log.error("Rudolf-Assistent Fehler: %s", e)
        return f"❌ Assistent nicht verfügbar: {e}"


def ask_sync(message: str, session_id: str = "default", context: str = "") -> str:
    """Synchroner Wrapper für ask()."""
    from modules.ai_client import ai_complete_chat_sync

    hist = _history(session_id)
    hist.append({"role": "user", "content": message})

    system = SYSTEM_PROMPT
    if context:
        system += f"\n\nAKTUELLER SYSTEM-KONTEXT:\n{context}"

    try:
        answer = ai_complete_chat_sync(list(hist), system=system, max_tokens=2048)
        if not answer:
            answer = "⚠️ Alle AI-Provider gerade nicht erreichbar — bitte kurz warten."
        hist.append({"role": "assistant", "content": answer})
        return answer
    except Exception as e:
        log.error("Rudolf-Assistent sync Fehler: %s", e)
        return f"❌ Assistent nicht verfügbar: {e}"


def clear_history(session_id: str = "default"):
    """Unterhaltungs-Verlauf einer Session löschen."""
    _HISTORY.pop(session_id, None)


def quick(prompt: str) -> str:
    """Einmalige Frage ohne Session-Memory (für Webhooks, Analysen etc.)."""
    try:
        from modules.ai_client import ai_complete_sync
        return ai_complete_sync(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=512) or ""
    except Exception as e:
        log.warning("Rudolf-Assistent quick() Fehler: %s", e)
        return ""
