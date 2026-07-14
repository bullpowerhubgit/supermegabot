#!/usr/bin/env python3
"""
Free API Hunt Daemon — Automatischer Entdecker kostenloser APIs
===============================================================
Durchsucht kontinuierlich öffentliche API-Verzeichnisse, testet Endpoints,
speichert funktionierende APIs in Supabase (discovered_apis) und meldet
Neufunde per Telegram.

Quellen:
  - public-apis.io (GitHub Liste: 1400+ APIs)
  - apilist.fun
  - rapidapi.com (kostenlose Tiers)
  - GitHub awesome-public-datasets

Starten:
  python3 modules/free_api_hunt_daemon.py           # Daemon (alle 6h)
  python3 modules/free_api_hunt_daemon.py --hunt    # Einmalig
  python3 modules/free_api_hunt_daemon.py --list    # Gespeicherte APIs zeigen
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [API-HUNT] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("FreeAPIHunt")

_BASE = Path(__file__).parent.parent

def _load_env():
    ef = _BASE / ".env"
    if ef.exists():
        for line in ef.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

_TG_TOKEN = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT  = lambda: os.getenv("TELEGRAM_CHAT_ID", "")
_SB_URL   = lambda: os.getenv("SUPABASE_URL", "")
_SB_KEY   = lambda: os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY", ""))

HUNT_INTERVAL = 6 * 3600  # alle 6 Stunden

# ── Bekannte kostenlose API-Kategorien für SuperMegaBot-Nutzung ───────────────

TARGET_CATEGORIES = {
    "business":     ["company", "business", "corporate", "finance", "commerce"],
    "email":        ["email", "mail", "smtp", "validation"],
    "ai":           ["ai", "machine learning", "nlp", "language", "openai", "groq"],
    "ecommerce":    ["shopify", "amazon", "ebay", "product", "price", "shopping"],
    "social":       ["social", "facebook", "instagram", "twitter", "linkedin"],
    "data":         ["data", "statistics", "government", "public", "open data"],
    "communication":["telegram", "whatsapp", "sms", "push", "notification"],
    "analytics":    ["analytics", "tracking", "seo", "marketing"],
}

# ── Statische Liste bekannter kostenloser APIs (sofort nutzbar) ───────────────

KNOWN_FREE_APIS = [
    # B2B / Business
    {"name": "OpenCorporates", "url": "https://api.opencorporates.com/v0.4/companies/search?q=test&per_page=5",
     "category": "business", "auth": False, "docs": "https://api.opencorporates.com/documentation"},
    {"name": "Handelsregister DE", "url": "https://www.handelsregister.de/rp_web/search.do",
     "category": "business", "auth": False, "docs": "https://www.handelsregister.de"},
    {"name": "GLEIF LEI", "url": "https://api.gleif.org/api/v1/lei-records?filter[fulltext]=siemens&page[size]=5",
     "category": "business", "auth": False, "docs": "https://api.gleif.org"},
    {"name": "Wikidata", "url": "https://www.wikidata.org/w/api.php?action=wbsearchentities&search=siemens&language=de&format=json",
     "category": "business", "auth": False, "docs": "https://www.wikidata.org/wiki/Wikidata:Data_access"},
    # Email Validierung
    {"name": "Disify Email Check", "url": "https://api.disify.com/api/email/test@test.com",
     "category": "email", "auth": False, "docs": "https://www.disify.com/"},
    {"name": "Abstract Email Validation", "url": "https://emailvalidation.abstractapi.com/v1/?api_key=FREE&email=test@test.com",
     "category": "email", "auth": True, "docs": "https://app.abstractapi.com/api/email-validation"},
    {"name": "ZeroBounce (free tier)", "url": "https://api.zerobounce.net/v2/getapiusage?api_key=FREE",
     "category": "email", "auth": True, "docs": "https://www.zerobounce.net/docs/"},
    # AI / LLM
    {"name": "Groq (free)", "url": "https://api.groq.com/openai/v1/models",
     "category": "ai", "auth": True, "docs": "https://console.groq.com/docs/openai"},
    {"name": "OpenRouter (free models)", "url": "https://openrouter.ai/api/v1/models",
     "category": "ai", "auth": False, "docs": "https://openrouter.ai/docs"},
    {"name": "Hugging Face Inference", "url": "https://api-inference.huggingface.co/models/gpt2",
     "category": "ai", "auth": True, "docs": "https://huggingface.co/docs/api-inference"},
    # News / Content
    {"name": "NewsAPI (free 100/day)", "url": "https://newsapi.org/v2/top-headlines?country=de&apiKey=FREE",
     "category": "analytics", "auth": True, "docs": "https://newsapi.org/docs"},
    {"name": "GNews (free 100/day)", "url": "https://gnews.io/api/v4/search?q=KI&lang=de&token=FREE",
     "category": "analytics", "auth": True, "docs": "https://gnews.io/docs"},
    {"name": "RSS (no auth)", "url": "https://feeds.reuters.com/reuters/businessNews",
     "category": "data", "auth": False, "docs": "RSS Feeds"},
    # E-Commerce
    {"name": "Open Food Facts", "url": "https://world.openfoodfacts.org/api/v0/product/3017620422003.json",
     "category": "ecommerce", "auth": False, "docs": "https://world.openfoodfacts.org/data"},
    {"name": "Barcode Lookup (upcitemdb)", "url": "https://api.upcitemdb.com/prod/trial/lookup?upc=012345678905",
     "category": "ecommerce", "auth": False, "docs": "https://www.upcitemdb.com/api/explorer#!/lookup/get_trial_lookup"},
    {"name": "Exchangerate (free)", "url": "https://api.exchangerate-api.com/v4/latest/EUR",
     "category": "data", "auth": False, "docs": "https://www.exchangerate-api.com/docs/free"},
    # Communication
    {"name": "Telegram Bot API", "url": "https://api.telegram.org/botTEST/getMe",
     "category": "communication", "auth": True, "docs": "https://core.telegram.org/bots/api"},
    # Location / Data
    {"name": "ip-api.com (free)", "url": "http://ip-api.com/json/8.8.8.8",
     "category": "data", "auth": False, "docs": "https://ip-api.com/docs"},
    {"name": "RestCountries", "url": "https://restcountries.com/v3.1/name/germany",
     "category": "data", "auth": False, "docs": "https://restcountries.com/"},
    {"name": "Clearbit Logo API", "url": "https://logo.clearbit.com/siemens.com",
     "category": "business", "auth": False, "docs": "https://clearbit.com/docs#logo-api"},
    # GitHub
    {"name": "GitHub REST API", "url": "https://api.github.com/repos/public-apis/public-apis",
     "category": "data", "auth": False, "docs": "https://docs.github.com/en/rest"},
    # Social Media Tools
    {"name": "Linkpreview (free tier)", "url": "https://api.linkpreview.net/?q=https://siemens.com&key=FREE",
     "category": "social", "auth": True, "docs": "https://my.linkpreview.net/"},
    # SEO / Analytics
    {"name": "PageSpeed Insights", "url": "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=https://siemens.com&strategy=mobile",
     "category": "analytics", "auth": False, "docs": "https://developers.google.com/speed/docs/insights/v5/get-started"},
    # Amazon Product API alternative
    {"name": "Rainforest API (trial)", "url": "https://api.rainforestapi.com/request?api_key=FREE&type=product&asin=B07X6C9RMF&amazon_domain=amazon.de",
     "category": "ecommerce", "auth": True, "docs": "https://www.rainforestapi.com/docs"},
]

# ── Supabase ──────────────────────────────────────────────────────────────────

async def _sb(method: str, path: str, body=None, params=None):
    url = _SB_URL().rstrip("/") + path
    headers = {
        "apikey": _SB_KEY(),
        "Authorization": f"Bearer {_SB_KEY()}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    async with aiohttp.ClientSession() as s:
        fn = getattr(s, method.lower())
        kw: dict = {"headers": headers}
        if body:   kw["json"] = body
        if params: kw["params"] = params
        async with fn(url, **kw) as r:
            text = await r.text()
            if r.status >= 400:
                return None
            try:
                return json.loads(text)
            except Exception:
                return text

async def _ensure_table():
    """Erstellt discovered_apis Tabelle falls nicht vorhanden."""
    sql = """
    CREATE TABLE IF NOT EXISTS discovered_apis (
        id          BIGSERIAL PRIMARY KEY,
        name        TEXT NOT NULL UNIQUE,
        url         TEXT,
        category    TEXT,
        auth        BOOLEAN DEFAULT FALSE,
        docs        TEXT,
        score       INTEGER DEFAULT 0,
        status      TEXT DEFAULT 'unknown',
        last_tested TIMESTAMPTZ,
        last_ok     TIMESTAMPTZ,
        notes       TEXT,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """
    # Via RPC falls verfügbar
    await _sb("POST", "/rest/v1/rpc/exec_sql", {"sql": sql})

# ── API Test ──────────────────────────────────────────────────────────────────

async def _test_api(api: dict, timeout: float = 8.0) -> dict:
    """Testet ob API erreichbar und antwortet korrekt."""
    url = api["url"]
    result = {**api, "status": "error", "score": 0, "notes": "",
              "last_tested": datetime.now(timezone.utc).isoformat()}

    # Platzhalter-Keys überspringen
    if "FREE" in url or "TEST" in url:
        result["status"] = "needs_key"
        result["notes"] = "Benötigt API-Key"
        result["score"] = 30 if not api.get("auth") else 20
        return result

    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
                headers={"User-Agent": "SuperMegaBot/3.0 API-Discovery"},
            ) as r:
                status = r.status
                ct = r.headers.get("content-type", "")

                if status == 200:
                    result["status"] = "active"
                    result["last_ok"] = datetime.now(timezone.utc).isoformat()
                    # Score basierend auf Auth-Anforderung und Response
                    score = 80
                    if not api.get("auth"):
                        score += 20  # Kein Key nötig = wertvoller
                    if "json" in ct:
                        score += 10
                    result["score"] = min(score, 100)
                    result["notes"] = f"HTTP 200 | Content-Type: {ct[:50]}"
                elif status == 401:
                    result["status"] = "needs_key"
                    result["score"] = 50
                    result["notes"] = "API aktiv aber Auth erforderlich"
                elif status == 429:
                    result["status"] = "rate_limited"
                    result["score"] = 60
                    result["notes"] = "Rate-Limited (API ist aktiv)"
                else:
                    result["status"] = "error"
                    result["score"] = 10
                    result["notes"] = f"HTTP {status}"

    except asyncio.TimeoutError:
        result["notes"] = "Timeout"
    except Exception as e:
        result["notes"] = str(e)[:100]

    return result

async def _save_api(api_result: dict) -> bool:
    """Speichert API-Ergebnis in Supabase (api-Schema, upsert on name)."""
    row = {
        "name":        api_result["name"],
        "url":         api_result["url"],
        "category":    api_result.get("category", ""),
        "auth":        api_result.get("auth", False),
        "docs":        api_result.get("docs", ""),
        "score":       api_result.get("score", 0),
        "status":      api_result.get("status", "unknown"),
        "last_tested": api_result.get("last_tested"),
        "last_ok":     api_result.get("last_ok"),
        "notes":       api_result.get("notes", ""),
    }
    url = _SB_URL().rstrip("/") + "/rest/v1/discovered_apis"
    headers = {
        "apikey":        _SB_KEY(),
        "Authorization": f"Bearer {_SB_KEY()}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=merge-duplicates,return=representation",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=row, headers=headers,
                              params={"on_conflict": "name"}) as r:
                return r.status in (200, 201)
    except Exception as e:
        log.debug("Save-Fehler: %s", e)
        return False

# ── GitHub public-apis Liste ──────────────────────────────────────────────────

async def _fetch_public_apis_github() -> List[dict]:
    """Lädt die öffentliche API-Liste von public-apis/public-apis auf GitHub."""
    discovered = []
    try:
        raw_url = "https://raw.githubusercontent.com/public-apis/public-apis/master/apis.json"
        async with aiohttp.ClientSession() as s:
            async with s.get(raw_url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    return []
                data = await r.json()

        count = 0
        for category, entries in data.items():
            # Nur für SuperMegaBot relevante Kategorien
            cat_lower = category.lower()
            relevant = any(
                kw in cat_lower
                for kw in ["business", "finance", "email", "ai", "machine", "commerce",
                           "news", "social", "data", "open", "job", "government"]
            )
            if not relevant:
                continue

            for entry in entries:
                if not entry.get("Link"):
                    continue
                # Kategorisieren
                smb_cat = "data"
                for our_cat, keywords in TARGET_CATEGORIES.items():
                    if any(k in (entry.get("Description") or "").lower() or
                           k in category.lower()
                           for k in keywords):
                        smb_cat = our_cat
                        break

                discovered.append({
                    "name": entry.get("API", "Unknown"),
                    "url": entry.get("Link", ""),
                    "category": smb_cat,
                    "auth": entry.get("Auth", "").lower() not in ("no", "", "false"),
                    "docs": entry.get("Link", ""),
                    "notes": entry.get("Description", "")[:200],
                })
                count += 1
                if count >= 50:  # Maximal 50 pro Lauf
                    break
            if count >= 50:
                break

        log.info("[HUNT] %d APIs von GitHub public-apis geladen", len(discovered))
    except Exception as e:
        log.warning("[HUNT] GitHub-Fetch-Fehler: %s", e)
    return discovered

# ── Haupt-Hunt ────────────────────────────────────────────────────────────────

async def _tg(text: str):
    token = _TG_TOKEN()
    chat  = _TG_CHAT()
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram: %s", e)

async def hunt(report: bool = True) -> dict:
    """Durchsucht alle Quellen, testet APIs, speichert Ergebnisse."""
    log.info("[HUNT] === Free API Hunt gestartet ===")
    stats = {"tested": 0, "active": 0, "new": 0, "needs_key": 0}

    all_apis = list(KNOWN_FREE_APIS)

    # Erweitere mit GitHub public-apis
    github_apis = await _fetch_public_apis_github()
    all_apis.extend(github_apis)

    # Deduplizieren nach Name
    seen_names: set = set()
    unique_apis = []
    for api in all_apis:
        if api["name"] not in seen_names:
            seen_names.add(api["name"])
            unique_apis.append(api)

    log.info("[HUNT] %d APIs zu testen …", len(unique_apis))
    new_finds: List[str] = []

    # Parallel testen (max 10 gleichzeitig)
    semaphore = asyncio.Semaphore(10)

    async def test_and_save(api: dict):
        async with semaphore:
            result = await _test_api(api)
            stats["tested"] += 1
            if result["status"] == "active":
                stats["active"] += 1
                log.info("  ✅ [%s] %s — Score %d", result["category"], result["name"], result["score"])
            elif result["status"] in ("needs_key", "rate_limited"):
                stats["needs_key"] += 1
                log.debug("  🔑 %s — %s", result["name"], result["status"])
            saved = await _save_api(result)
            if saved and result["status"] == "active" and result["score"] >= 70:
                new_finds.append(f"✅ {result['name']} ({result['category']}) — Score {result['score']}")
                stats["new"] += 1

    tasks = [test_and_save(api) for api in unique_apis]
    await asyncio.gather(*tasks, return_exceptions=True)

    log.info("[HUNT] Fertig: %d getestet, %d aktiv, %d neu gespeichert",
             stats["tested"], stats["active"], stats["new"])

    if report and new_finds:
        msg = (
            f"🔍 *Free API Hunt — Neue APIs gefunden!*\n\n"
            f"Getestet: {stats['tested']} | Aktiv: {stats['active']}\n\n"
            + "\n".join(new_finds[:10])
        )
        await _tg(msg)

    return stats

async def list_apis() -> None:
    """Zeigt alle gespeicherten APIs aus Supabase."""
    data = await _sb("GET", "/rest/v1/discovered_apis",
                     params={"order": "score.desc", "limit": "50"})
    if not data:
        print("Keine APIs gespeichert (oder Tabelle fehlt)")
        return
    print(f"\n=== Gespeicherte APIs ({len(data)}) ===")
    for api in data:
        icon = "✅" if api["status"] == "active" else ("🔑" if api["status"] == "needs_key" else "❌")
        print(f"  {icon} [{api['score']:3d}] {api['name']:<35} [{api['category']}]")
        if api.get("notes"):
            print(f"       {api['notes'][:60]}")
    print()

async def daemon():
    log.info("Free API Hunt Daemon gestartet — alle %dh", HUNT_INTERVAL // 3600)
    await _tg(f"🔍 *Free API Hunt Daemon* gestartet\nSucht alle {HUNT_INTERVAL//3600}h nach neuen kostenlosen APIs")
    while True:
        try:
            await hunt()
        except Exception as e:
            log.error("Hunt-Fehler: %s", e)
        await asyncio.sleep(HUNT_INTERVAL)

async def main():
    args = sys.argv[1:]
    if "--hunt" in args:
        stats = await hunt()
        print(json.dumps(stats, indent=2))
    elif "--list" in args:
        await list_apis()
    else:
        await daemon()

if __name__ == "__main__":
    asyncio.run(main())
