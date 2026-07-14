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
        # Groq zuerst (schnellstes free model)
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
