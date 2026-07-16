#!/usr/bin/env python3
"""
OpenAI Client — Budget-geschützt, nur für Revenue-Tasks
=========================================================
gpt-4o-mini: billigstes GPT-4-Level Modell ($0.15/1M input, $0.60/1M output)

Nur Revenue-Module dürfen diesen Client nutzen (ai_budget_guard).
Tageslimit: $8.00 (env: OPENAI_DAILY_USD_LIMIT)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp

log = logging.getLogger("OpenAIClient")

OAI_KEY   = lambda: os.getenv("OPENAI_API_KEY", "")
OAI_URL   = "https://api.openai.com/v1/chat/completions"
OAI_MODEL = "gpt-4o-mini"   # billig + stark für Revenue-Tasks

try:
    from modules.ai_budget_guard import is_allowed_oai, record_usage_oai
    _GUARD = True
except ImportError:
    _GUARD = False
    def is_allowed_oai(caller=""): return (True, caller)
    def record_usage_oai(i, o, caller=""): pass


async def ask(prompt: str, system: str = "", caller: str = "",
              max_tokens: int = 800, model: str = OAI_MODEL,
              fallback: str = "") -> Optional[str]:
    """
    OpenAI Chat Completion — Budget-geschützt.
    Nur für Revenue-Module. Gibt None zurück wenn geblockt.
    """
    if _GUARD:
        allowed, reason = is_allowed_oai(caller)
        if not allowed:
            log.warning("OpenAI BLOCKED: %s", reason)
            return fallback or None

    key = OAI_KEY()
    if not key:
        log.warning("OPENAI_API_KEY nicht gesetzt")
        return fallback or None

    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                OAI_URL,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={"model": model, "messages": messages,
                      "max_tokens": max_tokens, "temperature": 0.7},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                if r.status == 429:
                    log.warning("OpenAI 429 — Quota leer oder Rate Limit")
                    return fallback or None
                if r.status != 200:
                    body = await r.text()
                    log.warning("OpenAI %d: %s", r.status, body[:100])
                    return fallback or None
                d = await r.json()
                text = d["choices"][0]["message"]["content"]
                usage = d.get("usage", {})
                record_usage_oai(
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    caller or "openai_client",
                )
                return text
    except Exception as e:
        log.warning("OpenAI Exception: %s", e)
        return fallback or None


async def generate_product_description(title: str, price: float,
                                       caller: str = "revenue_engine") -> str:
    """Kurze Produkt-Beschreibung für Shopify Flash Deal Posts."""
    result = await ask(
        f"Schreib einen kurzen, verkaufsstarken deutschen Werbetext (max 2 Sätze) "
        f"für das Produkt: '{title}' zum Preis €{price:.2f}. "
        f"Fokus: Nutzen + Dringlichkeit. Keine Emojis.",
        caller=caller,
        max_tokens=100,
    )
    return result or f"Top Deal: {title} für nur €{price:.2f}!"


async def generate_ds24_teaser(product_name: str, niche: str,
                               caller: str = "ds24_affiliate_blaster") -> str:
    """Teaser-Text für DS24 Affiliate Posts."""
    result = await ask(
        f"Schreib einen Teaser-Satz (max 15 Wörter) für '{product_name}' "
        f"im Bereich {niche}. Auf Deutsch, verkaufsstark, mit Emoji am Anfang.",
        caller=caller,
        max_tokens=60,
    )
    return result or f"🚀 {product_name} — jetzt entdecken!"


async def generate_b2b_subject(company: str, topic: str = "EU AI Act",
                               caller: str = "compliance_outreach_all") -> str:
    """Personalisierte Email-Betreffzeile für B2B Outreach."""
    result = await ask(
        f"Schreib eine Email-Betreffzeile (max 8 Wörter) für {company} "
        f"zum Thema {topic}. Professionell, kein Spam, auf Deutsch.",
        caller=caller,
        max_tokens=30,
    )
    return result or f"{company}: {topic} — Handlungsbedarf bis August 2026"


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    prompt = " ".join(sys.argv[1:]) or "Hallo!"
    result = asyncio.run(ask(prompt, caller="revenue_engine"))
    print(result or "Keine Antwort (Quota leer oder geblockt)")
