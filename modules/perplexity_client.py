#!/usr/bin/env python3
"""
Perplexity AI Client — Web-Research für Revenue-Tasks
======================================================
Nutzt Perplexity Sonar (Online-Search) um aktuelle Markt-Infos zu holen.

NUR Revenue-Module dürfen diesen Client nutzen (ai_budget_guard).

Use cases:
  - Aktuelle Produktpreise für Flash Deals recherchieren
  - Trending Topics für DS24 Affiliate Posts
  - AIITEC: aktuelle EU AI Act News für B2B Outreach
  - Konkurrenpreise prüfen
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

import aiohttp

log = logging.getLogger("PerplexityClient")

PPLX_KEY   = lambda: os.getenv("PERPLEXITY_API_KEY", "")
PPLX_URL   = "https://api.perplexity.ai/chat/completions"
PPLX_MODEL = "sonar"            # Online-Search Modell — aktuell + günstig
PPLX_MODEL_PRO = "sonar-pro"    # Teureres Modell für komplexe Recherche

try:
    from modules.ai_budget_guard import is_allowed_pplx, record_usage_pplx
    _GUARD = True
except ImportError:
    _GUARD = False
    def is_allowed_pplx(caller=""): return (True, caller)
    def record_usage_pplx(caller=""): pass


async def search(query: str, caller: str = "", pro: bool = False,
                 max_tokens: int = 512) -> Optional[str]:
    """
    Führt eine Perplexity Online-Search durch.
    Nur für Revenue-Module erlaubt (Budget Guard).

    Returns: Antwort-Text oder None bei Fehler/Block
    """
    if _GUARD:
        allowed, reason = is_allowed_pplx(caller)
        if not allowed:
            log.warning("Perplexity BLOCKED: %s", reason)
            return None

    key = PPLX_KEY()
    if not key:
        # Fallback: ai_client nutzt Groq/DeepSeek/OpenRouter gratis
        try:
            from modules.ai_client import ai_complete
            log.info("Perplexity: kein Key — Fallback auf ai_client für: %s", query[:60])
            return await ai_complete(
                prompt=query,
                system="Antworte knapp und präzise auf Deutsch. Nur Fakten.",
                max_tokens=max_tokens,
            )
        except Exception as fe:
            log.warning("Perplexity Fallback fehlgeschlagen: %s", fe)
            return None

    model = PPLX_MODEL_PRO if pro else PPLX_MODEL
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                PPLX_URL,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system",
                         "content": "Antworte knapp und präzise auf Deutsch. Nur Fakten."},
                        {"role": "user", "content": query},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                    "return_citations": True,
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                if r.status != 200:
                    body = await r.text()
                    log.warning("Perplexity %d: %s", r.status, body[:100])
                    return None
                d = await r.json()
                text = d["choices"][0]["message"]["content"]
                record_usage_pplx(caller or "perplexity_client")
                return text
    except Exception as e:
        log.warning("Perplexity Exception: %s", e)
        return None


async def research_trending_products(category: str = "smart home tech") -> str:
    """Findet trending Produkte für Shopify Flash Deals."""
    result = await search(
        f"Was sind aktuell die meistgekauften und trending {category} Produkte "
        f"auf Amazon.de und AliExpress? Nenne 5 konkrete Produktnamen mit Preisen.",
        caller="smart_product_finder",
        max_tokens=300,
    )
    return result or ""


async def research_aiact_news() -> str:
    """Aktuelle EU AI Act News für AIITEC B2B Outreach."""
    result = await search(
        "Was sind die neuesten Entwicklungen zum EU AI Act 2026? "
        "Welche Branchen sind besonders betroffen? Kurze Zusammenfassung.",
        caller="compliance_outreach_all",
        max_tokens=250,
    )
    return result or ""


async def research_ds24_trending(niche: str = "online business") -> str:
    """Trending Topics für DS24 Affiliate Posts."""
    result = await search(
        f"Was sind aktuell die heißesten Trends im Bereich '{niche}' "
        f"für digitale Produkte und Online-Kurse in Deutschland?",
        caller="ds24_affiliate_blaster",
        max_tokens=200,
    )
    return result or ""


async def get_competitor_prices(product_name: str) -> str:
    """Preisvergleich für Shopify Produkte."""
    result = await search(
        f"Was kostet '{product_name}' aktuell bei Amazon.de, MediaMarkt und Idealo? "
        f"Nenne nur den günstigsten und teuersten Preis.",
        caller="revenue_engine",
        max_tokens=100,
    )
    return result or ""


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    query = " ".join(sys.argv[1:]) or "Aktuelle EU AI Act News 2026"
    result = asyncio.run(search(query, caller="revenue_engine"))
    print(result or "Keine Antwort")
