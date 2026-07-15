#!/usr/bin/env python3
"""
SuperMegaBot — Free API Hunter
================================
Sucht und nutzt automatisch kostenlose API-Alternativen.
Fällt auf Free-Tier um wenn bezahlte APIs nicht verfügbar sind.
Cached gefundene free APIs in data/free_api_registry.json.

Export: get_free_api(service), hunt_all_free_apis(), FreeAPIHunter
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DATA = Path(__file__).parent.parent / "data"
_DATA.mkdir(exist_ok=True)
_REGISTRY_FILE = _DATA / "free_api_registry.json"

# ── Known Free API Registry ────────────────────────────────────────────────────
# Immer aktuell gehaltene Liste kostenloser APIs nach Kategorie
FREE_API_CATALOG: dict[str, list[dict]] = {

    "ai_text": [
        {
            "name": "Ollama (lokal — kostenlos, kein Rate-Limit)",
            "url": "http://localhost:11434/api/chat",
            "env_key": "OLLAMA_FAST_MODEL",
            "model": "llama3.2:latest",
            "free_limit": "unbegrenzt (lokal)",
            "auth_header": "",
            "auth_prefix": "",
            "test_endpoint": "http://localhost:11434/api/tags",
            "local": True,
        },
        {
            "name": "Groq (llama-3.1-8b)",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "env_key": "GROQ_API_KEY",
            "model": "llama-3.1-8b-instant",
            "free_limit": "14400 req/day",
            "auth_header": "Authorization",
            "auth_prefix": "Bearer ",
            "test_endpoint": "https://api.groq.com/openai/v1/models",
        },
        {
            "name": "Groq (gemma2-9b)",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "env_key": "GROQ_API_KEY",
            "model": "gemma2-9b-it",
            "free_limit": "14400 req/day",
            "auth_header": "Authorization",
            "auth_prefix": "Bearer ",
            "test_endpoint": "https://api.groq.com/openai/v1/models",
        },
        {
            "name": "Gemini Flash 2.0 (free)",
            "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            "env_key": "GEMINI_API_KEY",
            "model": "gemini-2.0-flash",
            "free_limit": "1500 req/day",
            "auth_mode": "query_param",
            "auth_param": "key",
            "test_endpoint": "https://generativelanguage.googleapis.com/v1beta/models",
        },
        {
            "name": "OpenRouter (gemma-4-26b free)",
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "env_key": "OPENROUTER_API_KEY",
            "model": "google/gemma-4-26b-a4b-it:free",
            "free_limit": "unlimited (rate limited)",
            "auth_header": "Authorization",
            "auth_prefix": "Bearer ",
            "test_endpoint": "https://openrouter.ai/api/v1/models",
        },
        {
            "name": "OpenRouter (deepseek-v3 free)",
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "env_key": "OPENROUTER_API_KEY",
            "model": "deepseek/deepseek-chat-v3-0324:free",
            "free_limit": "unlimited (rate limited)",
            "auth_header": "Authorization",
            "auth_prefix": "Bearer ",
            "test_endpoint": "https://openrouter.ai/api/v1/models",
        },
        {
            "name": "Ollama (lokal)",
            "url": "http://localhost:11434/api/generate",
            "env_key": None,
            "model": "llama3.2",
            "free_limit": "∞ lokal",
            "auth_header": None,
            "test_endpoint": "http://localhost:11434/api/tags",
        },
    ],

    "ai_image": [
        {
            "name": "Pollinations.ai (komplett free)",
            "url": "https://image.pollinations.ai/prompt/{prompt}",
            "env_key": None,
            "free_limit": "∞ free",
            "auth_header": None,
            "test_endpoint": "https://image.pollinations.ai/prompt/test?nologo=true&width=64&height=64",
            "usage": "GET https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true",
        },
        {
            "name": "StabilityAI (free credits)",
            "url": "https://api.stability.ai/v2beta/stable-image/generate/core",
            "env_key": "STABILITY_API_KEY",
            "free_limit": "25 Credits/Monat gratis",
            "auth_header": "Authorization",
            "auth_prefix": "Bearer ",
            "test_endpoint": "https://api.stability.ai/v1/user/account",
        },
        {
            "name": "Unsplash (free photos)",
            "url": "https://api.unsplash.com/search/photos",
            "env_key": "UNSPLASH_ACCESS_KEY",
            "free_limit": "50 req/hour",
            "auth_header": "Authorization",
            "auth_prefix": "Client-ID ",
            "test_endpoint": "https://api.unsplash.com/photos",
        },
    ],

    "email_lookup": [
        {
            "name": "Hunter.io (free 25/mo)",
            "url": "https://api.hunter.io/v2/email-finder",
            "env_key": "HUNTER_API_KEY",
            "free_limit": "25 Suchen/Monat",
            "test_endpoint": "https://api.hunter.io/v2/account",
            "auth_mode": "query_param",
            "auth_param": "api_key",
        },
        {
            "name": "Apollo.io (free tier)",
            "url": "https://api.apollo.io/api/v1/people/match",
            "env_key": "APOLLO_API_KEY",
            "free_limit": "50 Credits/Monat",
            "auth_header": "X-Api-Key",
            "test_endpoint": "https://api.apollo.io/api/v1/auth/health",
        },
        {
            "name": "Abstract Email Validation (free)",
            "url": "https://emailvalidation.abstractapi.com/v1/",
            "env_key": "ABSTRACT_API_KEY",
            "free_limit": "100 req/Monat",
            "auth_mode": "query_param",
            "auth_param": "api_key",
            "test_endpoint": "https://emailvalidation.abstractapi.com/v1/",
        },
    ],

    "web_search": [
        {
            "name": "DuckDuckGo Instant Answer (free, kein Key)",
            "url": "https://api.duckduckgo.com/",
            "env_key": None,
            "free_limit": "∞ free",
            "auth_header": None,
            "test_endpoint": "https://api.duckduckgo.com/?q=test&format=json",
            "usage": "GET https://api.duckduckgo.com/?q={query}&format=json&no_html=1",
        },
        {
            "name": "Brave Search (free 2000/mo)",
            "url": "https://api.search.brave.com/res/v1/web/search",
            "env_key": "BRAVE_SEARCH_API_KEY",
            "free_limit": "2000 Abfragen/Monat",
            "auth_header": "X-Subscription-Token",
            "auth_prefix": "",
            "test_endpoint": "https://api.search.brave.com/res/v1/web/search?q=test",
        },
        {
            "name": "SerpAPI (free 100/mo)",
            "url": "https://serpapi.com/search",
            "env_key": "SERPAPI_KEY",
            "free_limit": "100 Suchen/Monat",
            "auth_mode": "query_param",
            "auth_param": "api_key",
            "test_endpoint": "https://serpapi.com/account",
        },
    ],

    "product_data": [
        {
            "name": "Open Food Facts (free, kein Key)",
            "url": "https://world.openfoodfacts.org/api/v2/search",
            "env_key": None,
            "free_limit": "∞ free",
            "auth_header": None,
            "test_endpoint": "https://world.openfoodfacts.org/api/v2/search?fields=id&page_size=1",
        },
        {
            "name": "Barcode Lookup (free 10/day)",
            "url": "https://api.barcodelookup.com/v3/products",
            "env_key": "BARCODE_LOOKUP_KEY",
            "free_limit": "10 req/Tag",
            "auth_mode": "query_param",
            "auth_param": "key",
            "test_endpoint": "https://api.barcodelookup.com/v3/products?barcode=012345678905",
        },
        {
            "name": "UPC Item DB (free, kein Key)",
            "url": "https://api.upcitemdb.com/prod/trial/lookup",
            "env_key": None,
            "free_limit": "100 req/Tag",
            "auth_header": None,
            "test_endpoint": "https://api.upcitemdb.com/prod/trial/lookup?upc=4006381333931",
            "usage": "GET https://api.upcitemdb.com/prod/trial/lookup?upc={upc}",
        },
    ],

    "currency": [
        {
            "name": "Open Exchange Rates (free 1000/mo)",
            "url": "https://openexchangerates.org/api/latest.json",
            "env_key": "OPEN_EXCHANGE_RATES_KEY",
            "free_limit": "1000 req/Monat",
            "auth_mode": "query_param",
            "auth_param": "app_id",
            "test_endpoint": "https://openexchangerates.org/api/currencies.json",
        },
        {
            "name": "Frankfurter (free, kein Key)",
            "url": "https://api.frankfurter.app/latest",
            "env_key": None,
            "free_limit": "∞ free",
            "auth_header": None,
            "test_endpoint": "https://api.frankfurter.app/latest?from=EUR&to=USD",
            "usage": "GET https://api.frankfurter.app/latest?from=EUR&to=USD",
        },
        {
            "name": "ExchangeRate-API (free 1500/mo)",
            "url": "https://v6.exchangerate-api.com/v6/{key}/latest/EUR",
            "env_key": "EXCHANGERATE_API_KEY",
            "free_limit": "1500 req/Monat",
            "test_endpoint": "https://v6.exchangerate-api.com/v6/{key}/latest/EUR",
        },
    ],

    "seo_analytics": [
        {
            "name": "Google PageSpeed (free, kein Key)",
            "url": "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
            "env_key": None,
            "free_limit": "∞ free (mit Key höher)",
            "auth_header": None,
            "test_endpoint": "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=https://google.com&strategy=mobile",
            "usage": "GET ?url={target_url}&strategy=mobile",
        },
        {
            "name": "BuiltWith (free basic)",
            "url": "https://api.builtwith.com/free1/api.json",
            "env_key": "BUILTWITH_API_KEY",
            "free_limit": "free basic tier",
            "auth_mode": "query_param",
            "auth_param": "KEY",
            "test_endpoint": "https://api.builtwith.com/free1/api.json?KEY={key}&LOOKUP=google.com",
        },
    ],

    "social_data": [
        {
            "name": "Reddit API (free, OAuth)",
            "url": "https://oauth.reddit.com/r/{subreddit}/hot",
            "env_key": "REDDIT_CLIENT_ID",
            "free_limit": "60 req/min",
            "auth_header": "Authorization",
            "auth_prefix": "Bearer ",
            "test_endpoint": "https://www.reddit.com/r/entrepreneur/hot.json?limit=5",
        },
        {
            "name": "RSS → JSON (free, kein Key)",
            "url": "https://api.rss2json.com/v1/api.json",
            "env_key": None,
            "free_limit": "10000 req/Tag",
            "auth_header": None,
            "test_endpoint": "https://api.rss2json.com/v1/api.json?rss_url=https://feeds.bbci.co.uk/news/rss.xml",
            "usage": "GET ?rss_url={feed_url}",
        },
    ],

    "ecommerce_data": [
        {
            "name": "Rainforest API (free trial)",
            "url": "https://api.rainforestapi.com/request",
            "env_key": "RAINFOREST_API_KEY",
            "free_limit": "100 Credits Trial",
            "auth_mode": "query_param",
            "auth_param": "api_key",
            "test_endpoint": "https://api.rainforestapi.com/request?api_key={key}&type=search&amazon_domain=amazon.de&search_term=smart+home",
        },
        {
            "name": "Preisjäger (free scraping)",
            "url": "https://www.preisjager.at/api/search",
            "env_key": None,
            "free_limit": "free public",
            "auth_header": None,
        },
    ],

    # B2B-spezifisch: Company-Enrichment + News (für AIITEC Outreach)
    "b2b_company": [
        {
            "name": "OpenCorporates (kein Key, 50k/mo)",
            "url": "https://api.opencorporates.com/v0.4/companies/search",
            "env_key": None,
            "free_limit": "50.000 req/Monat ohne Key",
            "auth_header": None,
            "test_endpoint": "https://api.opencorporates.com/v0.4/companies/search?q=Allianz&jurisdiction_code=de&format=json",
            "usage": "GET ?q={company_name}&jurisdiction_code=de&format=json",
        },
        {
            "name": "Clearbit Enrichment (50/mo free)",
            "url": "https://company.clearbit.com/v2/companies/find",
            "env_key": "CLEARBIT_API_KEY",
            "free_limit": "50 req/Monat",
            "auth_header": "Authorization",
            "auth_prefix": "Bearer ",
            "test_endpoint": "https://company.clearbit.com/v2/companies/find?domain=stripe.com",
        },
        {
            "name": "Disify Email Validation (kein Key)",
            "url": "https://www.disify.com/api/email/",
            "env_key": None,
            "free_limit": "∞ kostenlos",
            "auth_header": None,
            "test_endpoint": "https://www.disify.com/api/email/test@gmail.com",
            "usage": "GET https://www.disify.com/api/email/{email}",
        },
        {
            "name": "Abstract Email Validation (100/mo)",
            "url": "https://emailvalidation.abstractapi.com/v1/",
            "env_key": "ABSTRACT_API_KEY",
            "free_limit": "100 req/Monat",
            "auth_mode": "query_param",
            "auth_param": "api_key",
            "test_endpoint": "https://emailvalidation.abstractapi.com/v1/?api_key={key}&email=test@gmail.com",
        },
    ],

    "b2b_news": [
        {
            "name": "NewsAPI (100/Tag free)",
            "url": "https://newsapi.org/v2/everything",
            "env_key": "NEWSAPI_KEY",
            "free_limit": "100 Anfragen/Tag",
            "auth_mode": "query_param",
            "auth_param": "apiKey",
            "test_endpoint": "https://newsapi.org/v2/top-headlines?country=de&apiKey={key}&pageSize=1",
        },
        {
            "name": "GNews (100/Tag free)",
            "url": "https://gnews.io/api/v4/search",
            "env_key": "GNEWS_API_KEY",
            "free_limit": "100 Anfragen/Tag",
            "auth_mode": "query_param",
            "auth_param": "token",
            "test_endpoint": "https://gnews.io/api/v4/top-headlines?lang=de&max=1&token={key}",
        },
        {
            "name": "Currents API (600/Tag free)",
            "url": "https://api.currentsapi.services/v1/search",
            "env_key": "CURRENTS_API_KEY",
            "free_limit": "600 Anfragen/Tag",
            "auth_mode": "query_param",
            "auth_param": "apiKey",
            "test_endpoint": "https://api.currentsapi.services/v1/latest-news?language=de&apiKey={key}&page_size=1",
        },
    ],
}


class FreeAPIHunter:
    """Sucht und testet kostenlose API-Alternativen automatisch."""

    def __init__(self):
        self.registry: dict = self._load_registry()
        self.session = None

    def _load_registry(self) -> dict:
        if _REGISTRY_FILE.exists():
            try:
                return json.loads(_REGISTRY_FILE.read_text())
            except Exception:
                pass
        return {"last_scan": None, "working": {}, "broken": {}}

    def _save_registry(self):
        try:
            _REGISTRY_FILE.write_text(json.dumps(self.registry, indent=2, ensure_ascii=False))
        except Exception as e:
            log.debug("Registry save failed: %s", e)

    def get_best_free(self, service: str) -> dict | None:
        """Gibt die beste funktionierende kostenlose API für einen Service zurück."""
        working = self.registry.get("working", {}).get(service, [])
        if working:
            return working[0]
        # Fallback: aus Katalog ohne Test
        catalog = FREE_API_CATALOG.get(service, [])
        for api in catalog:
            if not api.get("env_key") or os.getenv(api["env_key"]):
                return api
        return None

    async def test_api(self, api: dict) -> bool:
        """Testet ob eine API erreichbar und authentifiziert ist."""
        test_url = api.get("test_endpoint")
        if not test_url:
            return False

        key = None
        if api.get("env_key"):
            key = os.getenv(api["env_key"], "")
            if not key:
                return False
            test_url = test_url.replace("{key}", key)

        try:
            import aiohttp
            headers = {}
            params = {}

            if key and api.get("auth_header"):
                prefix = api.get("auth_prefix", "")
                headers[api["auth_header"]] = f"{prefix}{key}"
            elif key and api.get("auth_mode") == "query_param":
                params[api["auth_param"]] = key

            async with aiohttp.ClientSession() as sess:
                async with sess.get(
                    test_url, headers=headers, params=params,
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    return r.status in (200, 201, 202)
        except Exception as e:
            log.debug("API test failed for %s: %s", api.get("name"), e)
            return False

    async def scan_category(self, category: str) -> list[dict]:
        """Scannt alle APIs einer Kategorie und gibt funktionierende zurück."""
        catalog = FREE_API_CATALOG.get(category, [])
        if not catalog:
            return []

        working = []
        for api in catalog:
            ok = await self.test_api(api)
            if ok:
                working.append({**api, "tested_at": datetime.now().isoformat(), "ok": True})
                log.info("✅ Free API: %s — %s", category, api["name"])
            else:
                log.debug("❌ Free API: %s — %s (nicht verfügbar)", category, api["name"])

        return working

    async def hunt_all_free_apis(self) -> dict:
        """Scannt alle Kategorien und speichert funktionierende APIs."""
        log.info("🔍 Free API Hunter — scanne alle Kategorien...")
        results = {}

        for category in FREE_API_CATALOG:
            working = await self.scan_category(category)
            results[category] = working
            log.info("  %s: %d/%d APIs funktionieren",
                     category, len(working), len(FREE_API_CATALOG[category]))

        self.registry["working"] = results
        self.registry["last_scan"] = datetime.now().isoformat()
        self.registry["total_working"] = sum(len(v) for v in results.values())
        self._save_registry()

        return results

    def get_free_ai_client(self) -> dict | None:
        """Gibt den besten verfügbaren kostenlosen AI-Client zurück."""
        # Ollama zuerst (lokal, kostenlos, kein Rate-Limit)
        import urllib.request
        try:
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
            model = os.getenv("OLLAMA_FAST_MODEL", "llama3.2:latest")
            return {
                "name": "Ollama",
                "url": "http://localhost:11434/api/chat",
                "key": "local",
                "model": model,
                "headers": {"Content-Type": "application/json"},
                "local": True,
            }
        except Exception:
            pass

        # Groq (schnellstes free cloud model)
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            return {
                "name": "Groq",
                "url": "https://api.groq.com/openai/v1/chat/completions",
                "key": groq_key,
                "model": "llama-3.1-8b-instant",
                "headers": {"Authorization": f"Bearer {groq_key}"},
            }

        # Gemini (free tier)
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            return {
                "name": "Gemini Flash",
                "url": f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}",
                "key": gemini_key,
                "model": "gemini-2.0-flash",
                "headers": {"Content-Type": "application/json"},
            }

        # OpenRouter free models
        or_key = os.getenv("OPENROUTER_API_KEY")
        if or_key:
            return {
                "name": "OpenRouter/DeepSeek",
                "url": "https://openrouter.ai/api/v1/chat/completions",
                "key": or_key,
                "model": "deepseek/deepseek-chat-v3-0324:free",
                "headers": {"Authorization": f"Bearer {or_key}"},
            }

        # Ollama lokal
        return {
            "name": "Ollama (lokal)",
            "url": "http://localhost:11434/api/generate",
            "key": None,
            "model": "llama3.2",
            "headers": {},
        }

    @staticmethod
    def get_free_image_url(prompt: str, width: int = 1024, height: int = 1024) -> str:
        """Gibt URL für kostenloses KI-Bild zurück (Pollinations)."""
        import urllib.parse
        encoded = urllib.parse.quote(prompt)
        return f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true&enhance=true"

    @staticmethod
    def get_free_currency_rate(from_cur: str = "EUR", to_cur: str = "USD") -> float | None:
        """Holt aktuellen Wechselkurs (Frankfurter — komplett free)."""
        try:
            import urllib.request
            url = f"https://api.frankfurter.app/latest?from={from_cur}&to={to_cur}"
            with urllib.request.urlopen(url, timeout=5) as r:
                data = json.loads(r.read())
                return data.get("rates", {}).get(to_cur)
        except Exception as e:
            log.debug("Currency rate fetch failed: %s", e)
            return None

    @staticmethod
    def duckduckgo_search(query: str, max_results: int = 5) -> list[dict]:
        """DuckDuckGo Instant Answer API — komplett free, kein Key."""
        try:
            import urllib.request
            import urllib.parse
            encoded = urllib.parse.quote(query)
            url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
            with urllib.request.urlopen(url, timeout=8) as r:
                data = json.loads(r.read())
                results = []
                for topic in data.get("RelatedTopics", [])[:max_results]:
                    if isinstance(topic, dict) and topic.get("FirstURL"):
                        results.append({
                            "title": topic.get("Text", "")[:100],
                            "url": topic.get("FirstURL"),
                        })
                return results
        except Exception as e:
            log.debug("DuckDuckGo search failed: %s", e)
            return []


# ── Convenience functions ──────────────────────────────────────────────────────
_hunter: FreeAPIHunter | None = None

def get_hunter() -> FreeAPIHunter:
    global _hunter
    if _hunter is None:
        _hunter = FreeAPIHunter()
    return _hunter


def get_free_api(service: str) -> dict | None:
    """Gibt beste free API für service zurück (ai_text, ai_image, web_search, etc.)"""
    return get_hunter().get_best_free(service)


async def run_roas_cycle():
    """Alias falls vom Scheduler aufgerufen."""
    return await hunt_all_free_apis()


async def hunt_all_free_apis() -> dict:
    """Hauptfunktion: Alle free APIs scannen und cachen."""
    hunter = get_hunter()
    results = await hunter.hunt_all_free_apis()

    total = sum(len(v) for v in results.values())
    log.info("✅ Free API Hunter: %d funktionierende APIs in %d Kategorien", total, len(results))

    # Telegram-Bericht
    try:
        tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        tg_chat  = os.getenv("TELEGRAM_CHAT_ID", "")
        if tg_token and tg_chat:
            import aiohttp
            lines = [f"🔍 <b>Free API Hunter — Scan abgeschlossen</b>"]
            for cat, apis in results.items():
                if apis:
                    names = ", ".join(a["name"] for a in apis[:2])
                    lines.append(f"✅ {cat}: {len(apis)} ({names})")
            lines.append(f"\n<b>Total: {total} kostenlose APIs verfügbar</b>")
            msg = "\n".join(lines)
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat, "text": msg, "parse_mode": "HTML"},
                    timeout=aiohttp.ClientTimeout(total=8),
                )
    except Exception as e:
        log.debug("Telegram notify failed: %s", e)

    return results


# ── FreeAPIToolkit — direkt nutzbar für AIITEC Outreach ───────────────────────

class FreeAPIToolkit:
    """
    Einheitliche Schnittstelle für die besten Free APIs.
    Nutzung:
        async with FreeAPIToolkit() as kit:
            text  = await kit.ai_complete("Schreib eine Email...")
            email = await kit.find_email("allianz.de")
            news  = await kit.get_company_news("Allianz")
            co    = await kit.enrich_company("Allianz SE", "allianz.de")
    """

    def __init__(self):
        self._session = None

    async def __aenter__(self):
        import aiohttp
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15)
        )
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()

    async def ai_complete(self, prompt: str, system: str = "", max_tokens: int = 800) -> str:
        """Groq (free) → OpenRouter → Gemini → leer."""
        import aiohttp
        key = os.getenv("GROQ_API_KEY", "")
        if key:
            try:
                msgs = []
                if system:
                    msgs.append({"role": "system", "content": system})
                msgs.append({"role": "user", "content": prompt})
                async with self._session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": "llama-3.1-70b-versatile", "messages": msgs,
                          "max_tokens": max_tokens},
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        return d["choices"][0]["message"]["content"].strip()
            except Exception:
                pass
        # OpenRouter fallback
        or_key = os.getenv("OPENROUTER_API_KEY", "")
        if or_key:
            try:
                msgs = []
                if system:
                    msgs.append({"role": "system", "content": system})
                msgs.append({"role": "user", "content": prompt})
                async with self._session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json",
                             "HTTP-Referer": "https://supermegabot-production.up.railway.app"},
                    json={"model": "google/gemma-4-26b-a4b-it:free", "messages": msgs,
                          "max_tokens": max_tokens},
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        return d["choices"][0]["message"]["content"].strip()
            except Exception:
                pass
        return ""

    async def find_email(self, domain: str, department: str = "") -> str:
        """Hunter.io — findet echte Kontakt-Emails per Domain (25/Monat free)."""
        key = os.getenv("HUNTER_API_KEY", "")
        if not key:
            return ""
        try:
            params = {"domain": domain, "api_key": key}
            if department:
                params["department"] = department
            async with self._session.get(
                "https://api.hunter.io/v2/domain-search", params=params
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    emails = d.get("data", {}).get("emails", [])
                    if emails:
                        best = max(emails, key=lambda e: e.get("confidence", 0))
                        return best.get("value", "")
        except Exception as e:
            log.debug("Hunter Fehler: %s", e)
        return ""

    async def validate_email(self, email_addr: str) -> bool:
        """Disify — Email-Validierung ohne Key (∞ free)."""
        try:
            async with self._session.get(
                f"https://www.disify.com/api/email/{email_addr}"
            ) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    return bool(d.get("format")) and not d.get("disposable", True)
        except Exception:
            pass
        return True

    async def get_company_news(self, company: str, max_results: int = 3) -> list:
        """NewsAPI → GNews → [] — aktuelle News für Email-Personalisierung."""
        news_key = os.getenv("NEWSAPI_KEY", os.getenv("NEWS_API_KEY", ""))
        if news_key:
            try:
                async with self._session.get(
                    "https://newsapi.org/v2/everything",
                    params={"q": company, "language": "de", "pageSize": max_results,
                            "sortBy": "publishedAt", "apiKey": news_key}
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        titles = [a.get("title", "") for a in d.get("articles", [])]
                        if titles:
                            return titles
            except Exception:
                pass
        gnews_key = os.getenv("GNEWS_API_KEY", "")
        if gnews_key:
            try:
                async with self._session.get(
                    "https://gnews.io/api/v4/search",
                    params={"q": company, "lang": "de", "max": max_results, "token": gnews_key}
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        return [a.get("title", "") for a in d.get("articles", [])]
            except Exception:
                pass
        return []

    async def enrich_company(self, name: str, domain: str = "") -> dict:
        """OpenCorporates — Handelsregister-Daten ohne Key (50k/Monat free)."""
        result = {"name": name, "domain": domain}
        try:
            async with self._session.get(
                "https://api.opencorporates.com/v0.4/companies/search",
                params={"q": name, "jurisdiction_code": "de", "format": "json"},
                headers={"User-Agent": "SuperMegaBot/1.0"},
            ) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    companies = d.get("results", {}).get("companies", [])
                    if companies:
                        c = companies[0].get("company", {})
                        result.update({
                            "registered_address": c.get("registered_address_in_full", ""),
                            "company_number": c.get("company_number", ""),
                            "incorporation_date": c.get("incorporation_date", ""),
                            "company_type": c.get("company_type", ""),
                            "status": c.get("current_status", ""),
                        })
        except Exception as e:
            log.debug("OpenCorporates Fehler: %s", e)
        return result


# ── Auto-Discovery Engine ──────────────────────────────────────────────────────
# Findet automatisch NEUE kostenlose APIs aus öffentlichen Quellen

_DISCOVERED_FILE = _DATA / "free_api_discovered.json"

# Kategorie-Mapping: API-Kategorie aus publicapis.org → unsere Kategorien
_CATEGORY_MAP = {
    "Artificial Intelligence": "ai_text",
    "Machine Learning": "ai_text",
    "Science & Math": "ai_text",
    "Business": "b2b_company",
    "Finance": "currency",
    "Currency Exchange": "currency",
    "Email": "email_lookup",
    "Data Validation": "email_lookup",
    "News": "b2b_news",
    "Social": "social_data",
    "Search": "web_search",
    "Shopping": "ecommerce_data",
    "eCommerce": "ecommerce_data",
    "SEO": "seo_analytics",
    "Analytics": "seo_analytics",
    "Photography": "ai_image",
    "Art & Design": "ai_image",
}


async def _discover_from_public_apis_io(session) -> list[dict]:
    """Holt alle no-auth, HTTPS, CORS-freien APIs von publicapis.org."""
    discovered = []
    try:
        async with session.get(
            "https://api.publicapis.org/entries",
            params={"https": "true", "cors": "yes", "auth": ""},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status == 200:
                data = await r.json(content_type=None)
                for entry in data.get("entries", []):
                    cat = _CATEGORY_MAP.get(entry.get("Category", ""), "")
                    if not cat:
                        continue
                    link = entry.get("Link", "")
                    if not link or not link.startswith("https://"):
                        continue
                    discovered.append({
                        "name": entry.get("API", "Unknown") + " (auto-discovered)",
                        "url": link,
                        "env_key": None,
                        "free_limit": "public (no auth)",
                        "auth_header": None,
                        "test_endpoint": link,
                        "description": entry.get("Description", "")[:120],
                        "category": cat,
                        "source": "publicapis.org",
                    })
    except Exception as e:
        log.debug("publicapis.org fetch error: %s", e)
    return discovered


async def _discover_from_github_awesome(session) -> list[dict]:
    """Parst das awesome-public-apis README auf GitHub für no-auth Endpoints."""
    discovered = []
    sources = [
        ("https://raw.githubusercontent.com/public-apis/public-apis/master/README.md",
         "public-apis/public-apis"),
    ]
    url_pat = __import__("re").compile(r'\[([^\]]+)\]\((https://[^\)]+)\)')
    auth_pat = __import__("re").compile(r'\|\s*`?No`?\s*\|', __import__("re").IGNORECASE)
    try:
        for raw_url, source_name in sources:
            async with session.get(raw_url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    continue
                text = await r.text()
                lines = text.splitlines()
                for i, line in enumerate(lines):
                    if "|" not in line:
                        continue
                    if not auth_pat.search(line):
                        continue
                    m = url_pat.search(line)
                    if not m:
                        continue
                    api_name, api_url = m.group(1), m.group(2)
                    if not api_url.startswith("https://"):
                        continue
                    # Bestimme Kategorie aus vorangehender Überschrift
                    cat = "web_search"
                    for j in range(max(0, i - 30), i):
                        hl = lines[j]
                        if hl.startswith("## "):
                            heading = hl.lstrip("# ").strip()
                            cat = _CATEGORY_MAP.get(heading, "web_search")
                            break
                    discovered.append({
                        "name": f"{api_name} (auto-discovered)",
                        "url": api_url,
                        "env_key": None,
                        "free_limit": "no-auth public",
                        "auth_header": None,
                        "test_endpoint": api_url,
                        "category": cat,
                        "source": source_name,
                    })
                    if len(discovered) >= 150:
                        break
    except Exception as e:
        log.debug("GitHub awesome parse error: %s", e)
    return discovered


async def auto_discover_new_apis(test_limit: int = 40) -> dict:
    """
    Automatische API-Entdeckung aus dem Internet.
    Findet neue kostenlose APIs, testet sie, speichert funktionierende.
    """
    import aiohttp as _aiohttp
    log.info("🌐 Auto-Discovery: Suche nach neuen Free APIs...")

    async with _aiohttp.ClientSession(
        headers={"User-Agent": "SuperMegaBot-FreeAPIHunter/1.0"},
    ) as session:
        # Quellen parallel abrufen
        results = await asyncio.gather(
            _discover_from_public_apis_io(session),
            _discover_from_github_awesome(session),
            return_exceptions=True,
        )

    all_found: list[dict] = []
    for r in results:
        if isinstance(r, list):
            all_found.extend(r)

    # Dedupliziere nach URL
    seen_urls: set[str] = set()
    unique = []
    for api in all_found:
        u = api.get("url", "")
        if u and u not in seen_urls:
            seen_urls.add(u)
            unique.append(api)

    # Vergleiche mit bekanntem Katalog — nur wirklich neue aufnehmen
    existing_urls: set[str] = set()
    for cat_apis in FREE_API_CATALOG.values():
        for a in cat_apis:
            if a.get("url"):
                existing_urls.add(a["url"])
    novel = [a for a in unique if a["url"] not in existing_urls]

    log.info("Discovery: %d gesamt, %d einzigartig, %d neu (noch nicht im Katalog)",
             len(all_found), len(unique), len(novel))

    # Teste max `test_limit` neue APIs
    hunter = get_hunter()
    tested_ok: list[dict] = []
    tested_fail: list[dict] = []
    import aiohttp as _aiohttp2
    async with _aiohttp2.ClientSession() as sess:
        for api in novel[:test_limit]:
            try:
                async with sess.get(
                    api["test_endpoint"],
                    timeout=_aiohttp2.ClientTimeout(total=6),
                    headers={"User-Agent": "SuperMegaBot/1.0"},
                    allow_redirects=True,
                ) as r:
                    ok = r.status in (200, 201, 202, 204)
                    entry = {**api, "http_status": r.status, "tested_at": datetime.now().isoformat()}
                    if ok:
                        tested_ok.append(entry)
                    else:
                        tested_fail.append(entry)
            except Exception as e:
                tested_fail.append({**api, "error": str(e)[:80], "tested_at": datetime.now().isoformat()})

    # Speichern
    discovered_data = {
        "last_discovery": datetime.now().isoformat(),
        "total_found": len(all_found),
        "total_unique": len(unique),
        "total_novel": len(novel),
        "total_tested": len(tested_ok) + len(tested_fail),
        "working": tested_ok,
        "broken": tested_fail[:20],
    }
    try:
        _DISCOVERED_FILE.write_text(
            json.dumps(discovered_data, indent=2, ensure_ascii=False)
        )
    except Exception as e:
        log.debug("Save discovered failed: %s", e)

    # Telegram-Meldung
    try:
        tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
        if tg_token and tg_chat and tested_ok:
            import aiohttp as _aiohttp3
            lines = [
                f"<b>🌐 Auto-Discovery: {len(tested_ok)} neue Free APIs gefunden!</b>",
                f"Quellen: publicapis.org + GitHub awesome-lists",
                f"Getestet: {len(tested_ok) + len(tested_fail)}, OK: {len(tested_ok)}",
            ]
            for a in tested_ok[:5]:
                lines.append(f"✅ {a['name'][:50]}")
            if len(tested_ok) > 5:
                lines.append(f"… und {len(tested_ok) - 5} weitere")
            async with _aiohttp3.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat, "text": "\n".join(lines), "parse_mode": "HTML"},
                    timeout=_aiohttp3.ClientTimeout(total=8),
                )
    except Exception:
        pass

    log.info("Auto-Discovery: %d neue funktionierende APIs gefunden", len(tested_ok))
    return discovered_data


def get_discovery_stats() -> dict:
    """Liest gespeicherte Discovery-Ergebnisse."""
    try:
        if _DISCOVERED_FILE.exists():
            data = json.loads(_DISCOVERED_FILE.read_text())
            return {
                "ok": True,
                "last_discovery": data.get("last_discovery"),
                "total_novel": data.get("total_novel", 0),
                "working_count": len(data.get("working", [])),
                "working": data.get("working", [])[:10],
            }
    except Exception:
        pass
    return {"ok": False, "last_discovery": None, "working_count": 0, "working": []}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    print("🔍 Suche nach kostenlosen APIs...")
    results = asyncio.run(hunt_all_free_apis())
    print(f"\n{'═'*55}")
    print(f"  Ergebnis: {sum(len(v) for v in results.values())} funktionierende Free APIs")
    print(f"{'═'*55}")
    for cat, apis in results.items():
        print(f"\n  {cat}:")
        for api in apis:
            print(f"    ✅ {api['name']} ({api.get('free_limit','')})")
    print()
    # Zeige beste AI-Option
    hunter = get_hunter()
    best_ai = hunter.get_free_ai_client()
    if best_ai:
        print(f"  🤖 Bester Free AI: {best_ai['name']} / {best_ai['model']}")
    # Zeige Wechselkurs
    rate = FreeAPIHunter.get_free_currency_rate("EUR", "USD")
    if rate:
        print(f"  💶 EUR/USD: {rate}")
    # DuckDuckGo test
    results2 = FreeAPIHunter.duckduckgo_search("smart home gadgets 2026", 3)
    print(f"  🔍 DDG Suche: {len(results2)} Ergebnisse")
