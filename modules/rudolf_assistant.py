"""
Rudolf's persönliche KI-Rechte-Hand — läuft über APIHunt-Fallback-Kette.
Kette: Groq (gratis) → DeepSeek → OpenRouter (gratis) → Gemini → Anthropic → OpenAI → ...

Modi: general (default), shop, mail, post, revenue, expansion, browser

Import:
    from modules.rudolf_assistant import ask, ask_sync, clear_history
"""

import asyncio
import logging
import os
from collections import deque

log = logging.getLogger(__name__)

_BASE = """Du bist Rudolfs persönliche Rechte Hand — KI-Assistent von Rudolf Sarkany.

KONTEXT:
- Owner: Rudolf Sarkany (bullpowersrtkennels@gmail.com, @bullpowerhubgit)
- Business: SuperMegaBot SaaS + Shopify ineedit.com.co (Smart Home/Solar/Tech, 13k+ Produkte)
- Infrastruktur: 9 Railway-Services + 6 Netlify-Sites live
- Stripe: acct_1Tg1U0RJECiV6vSm (bullpowersrtkennels)
- Social: Instagram @aaiitecc, YouTube @AIITECrs, Telegram @DudiRudibot
- DS24: Konto 1581233-... (aiitec), Shopify: ineedit.com.co

REGELN:
- Antworte IMMER auf Deutsch
- Kein Smalltalk — Rudolf braucht Ergebnisse
- Kurz und präzise, fertigen Code sofort liefern"""

SYSTEM_PROMPT = _BASE + """

ROLLE: Allgemeiner Assistent + Business-Stratege
Aufgaben: Code, Debugging, Deployment, Business-Entscheidungen, Problemlösung."""

_SPECIALIST_PROMPTS = {
    "shop": _BASE + """

ROLLE: SHOP-MANAGER (Shopify ineedit.com.co)
Aufgaben: Produkte anlegen/bearbeiten, Preise optimieren, Collections, SEO, Bestellungen.
Nische: Smart Home / Solar / Tech — NUR 4.5★+, EK €8-300+.
API: SHOPIFY_ACCESS_TOKEN + SHOPIFY_STORE_URL aus .env.
Reagiere auf: Bestellprobleme, Lagerstand, Preis-Optimierung, Trending-Produkte.""",

    "mail": _BASE + """

ROLLE: MAIL-ASSISTENT (bullpowersrtkennels@gmail.com)
Aufgaben: Antworten schreiben, Templates, Leads qualifizieren, Kundensupport, Newsletter.
Ton: Professionell, freundlich. Deutsch bevorzugt, Englisch wenn Kunde Englisch schreibt.""",

    "post": _BASE + """

ROLLE: POST-ASSISTENT / SOCIAL MEDIA
Plattformen: Instagram @aaiitecc, YouTube @AIITECrs, TikTok, Pinterest.
Aufgaben: Caption, Hashtags, Content-Plan, Posting-Zeiten, Trend-Recherche.
Stil: Smart Home/Solar/Tech, Zielgruppe 25-45, tech-affin.
Format: Hook → Wert → CTA. Instagram max 2200 Zeichen. 20-30 Hashtags.""",

    "revenue": _BASE + """

ROLLE: MONETARISIERUNGS-MANAGER
Einnahmen: Shopify ineedit.com.co, DS24 (1581233-...), Stripe (acct_1Tg1U0), Gumroad.
Aufgaben: Umsatz analysieren, neue Produkte, Preisstrategien, Upsells, Cross-Sells, Affiliate.
DRINGEND: Meta Ads Budget setzen! (ROAS=0 wegen €0 Budget). Klaviyo E-Mail-Flows optimieren.""",

    "expansion": _BASE + """

ROLLE: EXPANSION-MANAGER
Aufgabe: Neues Business entwickeln, Märkte analysieren, Skalierungsstrategien.
Fokus: E-Commerce Expansion (EU/US), neue SaaS-Produkte, B2B-Partnerschaften, Reseller.
Output: Konkrete Aktionsschritte — kein Blabla.""",

    "browser": _BASE + """

ROLLE: BROWSER-ASSISTENT / RECHERCHE
Aufgabe: Web-Recherche, Produkt-Research, Trend-Analyse, Konkurrenz-Monitoring.
Output: Strukturierte Zusammenfassung + konkrete Empfehlungen.""",
}

_MAX_HISTORY = 20
_HISTORY: dict = {}


def _history(session_id: str) -> deque:
    if session_id not in _HISTORY:
        _HISTORY[session_id] = deque(maxlen=_MAX_HISTORY)
    return _HISTORY[session_id]


def _get_system(mode: str, context: str = "") -> str:
    system = _SPECIALIST_PROMPTS.get(mode, SYSTEM_PROMPT)
    if context:
        system += f"\n\nAKTUELLER KONTEXT:\n{context}"
    return system


async def ask(message: str, session_id: str = "default", context: str = "", mode: str = "general") -> str:
    """Async-Anfrage mit Session-Memory. Nutzt automatisch besten verfügbaren Provider."""
    from modules.ai_client import ai_complete_chat

    hist = _history(session_id)
    hist.append({"role": "user", "content": message})

    try:
        answer = await ai_complete_chat(list(hist), system=_get_system(mode, context), max_tokens=2048)
        if not answer:
            answer = "⚠️ Alle AI-Provider gerade nicht erreichbar — bitte kurz warten."
        hist.append({"role": "assistant", "content": answer})
        return answer
    except Exception as e:
        log.error("Rudolf-Assistent Fehler: %s", e)
        return f"❌ Assistent nicht verfügbar: {e}"


def ask_sync(message: str, session_id: str = "default", context: str = "", mode: str = "general") -> str:
    """Synchroner Wrapper für ask()."""
    from modules.ai_client import ai_complete_chat_sync

    hist = _history(session_id)
    hist.append({"role": "user", "content": message})

    try:
        answer = ai_complete_chat_sync(list(hist), system=_get_system(mode, context), max_tokens=2048)
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


def quick(prompt: str, mode: str = "general") -> str:
    """Einmalige Frage ohne Session-Memory (für Webhooks, Analysen etc.)."""
    try:
        from modules.ai_client import ai_complete_sync
        system = _SPECIALIST_PROMPTS.get(mode, SYSTEM_PROMPT)
        return ai_complete_sync(prompt=prompt, system=system, max_tokens=512) or ""
    except Exception as e:
        log.warning("Rudolf-Assistent quick() Fehler: %s", e)
        return ""
