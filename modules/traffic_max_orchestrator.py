#!/usr/bin/env python3
"""
Traffic Max Orchestrator — Maximaler organischer Traffic + Revenue
==================================================================
Startet alle Traffic-Engines parallel und stellt sicher dass immer eine
AI-API verfügbar ist (8-Provider Fallback: Ollama→Groq→DeepSeek→OpenRouter→Gemini→Anthropic→OpenAI→Perplexity).

Features:
  • Parallel-Start aller Traffic-Module (SEO, Social, Email, IndexNow)
  • APIHunt Watchdog — wechselt automatisch auf nächsten Provider
  • IndexNow Bulk-Submit für alle neuen Shopify-Produkte
  • Google Merchant Center Feed-Refresh (Free Shopping Traffic)
  • Email Revenue Guardian — verhindert gebrochene Emails
  • Umsatz-Dashboard per Telegram
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("TrafficMax")

_ROOT = Path(__file__).parent.parent
TG_TOKEN = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = lambda: os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_DOMAIN  = lambda: os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = lambda: os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_VERSION = lambda: os.getenv("SHOPIFY_API_VERSION", "2026-04")
INDEXNOW_KEY    = os.getenv("INDEXNOW_KEY", "bullpower2026indexnow")

# 8 AI Provider Fallback Chain
_AI_PROVIDERS = [
    {"name": "Ollama",      "env": "OLLAMA_HOST",         "base": "http://localhost:11434"},
    {"name": "Groq",        "env": "GROQ_API_KEY",        "base": "https://api.groq.com"},
    {"name": "DeepSeek",    "env": "DEEPSEEK_API_KEY",    "base": "https://api.deepseek.com"},
    {"name": "OpenRouter",  "env": "OPENROUTER_API_KEY",  "base": "https://openrouter.ai/api/v1"},
    {"name": "Gemini",      "env": "GEMINI_API_KEY",      "base": "https://generativelanguage.googleapis.com"},
    {"name": "Anthropic",   "env": "ANTHROPIC_API_KEY",   "base": "https://api.anthropic.com"},
    {"name": "OpenAI",      "env": "OPENAI_API_KEY",      "base": "https://api.openai.com"},
    {"name": "Perplexity",  "env": "PERPLEXITY_API_KEY",  "base": "https://api.perplexity.ai"},
]


async def _tg(msg: str) -> None:
    tok = TG_TOKEN()
    chat = TG_CHAT()
    if not tok or not chat:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


async def check_api_providers() -> dict:
    """Check all 8 AI providers and return status + active provider."""
    import aiohttp
    results = {}
    active = None

    for p in _AI_PROVIDERS:
        key = os.getenv(p["env"], "")
        if not key and p["name"] != "Ollama":
            results[p["name"]] = "NO_KEY"
            continue

        # Simple availability check
        try:
            async with aiohttp.ClientSession() as s:
                if p["name"] == "Ollama":
                    async with s.get(f"{p['base']}/api/tags", timeout=aiohttp.ClientTimeout(total=3)) as r:
                        results[p["name"]] = "✅" if r.status == 200 else f"HTTP {r.status}"
                elif p["name"] == "Groq":
                    async with s.get("https://api.groq.com/openai/v1/models",
                                     headers={"Authorization": f"Bearer {key}"},
                                     timeout=aiohttp.ClientTimeout(total=5)) as r:
                        results[p["name"]] = "✅" if r.status == 200 else f"HTTP {r.status}"
                elif p["name"] == "Anthropic":
                    async with s.get("https://api.anthropic.com/v1/models",
                                     headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                                     timeout=aiohttp.ClientTimeout(total=5)) as r:
                        results[p["name"]] = "✅" if r.status == 200 else f"HTTP {r.status}"
                else:
                    results[p["name"]] = "✅ (key present)"
                    if not active:
                        active = p["name"]
                    continue
                if not active and results[p["name"]] == "✅":
                    active = p["name"]
        except Exception as e:
            results[p["name"]] = f"❌ {type(e).__name__}"

    return {"providers": results, "active": active}


async def bulk_indexnow_submit(max_urls: int = 1000) -> dict:
    """Submit all Shopify product URLs to IndexNow (Bing+Yandex+others) for instant indexing."""
    import aiohttp
    domain = SHOPIFY_DOMAIN()
    token = SHOPIFY_TOKEN()
    ver = SHOPIFY_VERSION()
    if not domain or not token:
        return {"ok": False, "error": "Shopify not configured"}

    # Collect all product handles via pagination
    urls = []
    since_id = 0
    while len(urls) < max_urls:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://{domain}/admin/api/{ver}/products.json",
                    headers={"X-Shopify-Access-Token": token},
                    params={"limit": 250, "since_id": since_id, "fields": "id,handle", "status": "active"},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    data = await r.json(content_type=None)
            products = data.get("products", [])
            if not products:
                break
            for p in products:
                urls.append(f"https://{domain}/products/{p['handle']}")
            since_id = products[-1]["id"]
            await asyncio.sleep(0.5)  # respect rate limit
        except Exception as e:
            log.error("IndexNow fetch error: %s", e)
            break

    if not urls:
        return {"ok": False, "error": "No product URLs found"}

    # Submit to IndexNow endpoints
    endpoints = [
        "https://api.indexnow.org/indexnow",
        "https://www.bing.com/indexnow",
        "https://yandex.com/indexnow",
    ]

    submitted = 0
    # IndexNow accepts max 10k URLs per batch
    for i in range(0, len(urls), 500):
        batch = urls[i:i+500]
        payload = {
            "host": domain,
            "key": INDEXNOW_KEY,
            "keyLocation": f"https://{domain}/{INDEXNOW_KEY}.txt",
            "urlList": batch,
        }
        for ep in endpoints:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(ep, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
                        if r.status in (200, 202):
                            submitted += len(batch)
                            log.info("IndexNow %s: submitted %d URLs", ep, len(batch))
                        break  # one successful endpoint is enough per batch
            except Exception:
                continue
        await asyncio.sleep(1)

    return {"ok": True, "urls_found": len(urls), "submitted": submitted}


async def google_merchant_feed_ping() -> dict:
    """Trigger Google Merchant Center feed re-fetch via Content API (free Shopping traffic)."""
    # Without GMC API key, ping Google's cache refresher via the sitemap
    import aiohttp
    domain = SHOPIFY_DOMAIN()
    if not domain:
        return {"ok": False, "error": "Shopify not configured"}

    sitemap_url = f"https://{domain}/sitemap.xml"
    google_ping = f"https://www.google.com/ping?sitemap={sitemap_url}"
    bing_ping = f"https://www.bing.com/ping?sitemap={sitemap_url}"

    results = {}
    for name, url in [("Google", google_ping), ("Bing", bing_ping)]:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    results[name] = f"HTTP {r.status}"
        except Exception as e:
            results[name] = f"Error: {e}"

    return {"ok": True, "pings": results, "sitemap": sitemap_url}


async def email_revenue_guardian() -> dict:
    """Ensure email systems are healthy — check Mailchimp, Klaviyo, SMTP, fix broken sequences."""
    results = {}
    import aiohttp

    # 1. Mailchimp ping
    mc_key = os.getenv("MAILCHIMP_API_KEY", "")
    mc_server = os.getenv("MAILCHIMP_SERVER", "us5")
    if mc_key:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://{mc_server}.api.mailchimp.com/3.0/ping",
                    headers={"Authorization": f"apikey {mc_key}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    results["mailchimp"] = "✅" if r.status == 200 else f"❌ HTTP {r.status}"
        except Exception as e:
            results["mailchimp"] = f"❌ {e}"
    else:
        results["mailchimp"] = "NO_KEY"

    # 2. Klaviyo ping
    kv_key = os.getenv("KLAVIYO_API_KEY", "")
    if kv_key:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://a.klaviyo.com/api/accounts/",
                    headers={"Authorization": f"Klaviyo-API-Key {kv_key}", "revision": "2024-02-15"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    results["klaviyo"] = "✅" if r.status == 200 else f"❌ HTTP {r.status}"
        except Exception as e:
            results["klaviyo"] = f"❌ {e}"
    else:
        results["klaviyo"] = "NO_KEY"

    # 3. Trigger email sequence processing for any stuck emails
    try:
        from modules.email_sequence_engine import process_due_emails
        seq_result = await process_due_emails()
        results["sequences"] = f"✅ {seq_result.get('sent', 0)} gesendet"
    except Exception as e:
        results["sequences"] = f"⚠️ {e}"

    return {"ok": True, "systems": results}


async def run_traffic_max_cycle() -> dict:
    """
    Master parallel run: alle Traffic-Engines gleichzeitig starten.
    Gibt Gesamtstatus + Umsatz-Bericht zurück.
    """
    start = time.time()
    log.info("TrafficMax: Starting parallel cycle")

    # 1. API provider health check (always first)
    api_status = await check_api_providers()
    active_provider = api_status.get("active", "unknown")

    # 2. Parallel run: IndexNow + Google ping + email guardian
    results = await asyncio.gather(
        bulk_indexnow_submit(max_urls=500),
        google_merchant_feed_ping(),
        email_revenue_guardian(),
        return_exceptions=True,
    )

    indexnow_r = results[0] if not isinstance(results[0], Exception) else {"ok": False, "error": str(results[0])}
    gmc_r      = results[1] if not isinstance(results[1], Exception) else {"ok": False, "error": str(results[1])}
    email_r    = results[2] if not isinstance(results[2], Exception) else {"ok": False, "error": str(results[2])}

    elapsed = round(time.time() - start, 1)

    # 3. Telegram report
    providers_ok = sum(1 for v in api_status["providers"].values() if v.startswith("✅"))
    providers_total = len(api_status["providers"])
    email_systems = email_r.get("systems", {})
    email_ok = sum(1 for v in email_systems.values() if "✅" in str(v))

    report = (
        f"🚀 <b>Traffic Max Orchestrator</b>\n"
        f"⏱ {elapsed}s | {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n\n"
        f"🤖 <b>AI APIs:</b> {providers_ok}/{providers_total} OK | Aktiv: {active_provider}\n"
        f"🔍 <b>IndexNow:</b> {indexnow_r.get('submitted',0)}/{indexnow_r.get('urls_found',0)} URLs eingereicht\n"
        f"📊 <b>Sitemap-Pings:</b> Google+Bing {'✅' if gmc_r.get('ok') else '❌'}\n"
        f"📧 <b>Email-Systeme:</b> {email_ok}/3 OK\n"
    )

    if providers_ok < 2:
        report += f"\n⚠️ <b>WARNUNG: Nur {providers_ok} AI-Provider verfügbar!</b>"
        await _tg(report)
    else:
        await _tg(report)

    return {
        "ok": True,
        "elapsed": elapsed,
        "api_providers": api_status,
        "indexnow": indexnow_r,
        "gmc": gmc_r,
        "email": email_r,
    }


async def api_hunt_watchdog() -> dict:
    """
    Prüft ob genug AI-Provider verfügbar sind.
    Falls < 2 aktiv → Telegram-Alert + versucht neue Free APIs zu entdecken.
    """
    status = await check_api_providers()
    active_count = sum(1 for v in status["providers"].values() if "✅" in str(v))

    if active_count < 2:
        await _tg(
            f"⚠️ <b>APIHunt Watchdog Alert!</b>\n"
            f"Nur {active_count} AI-Provider aktiv!\n"
            f"Details: {json.dumps(status['providers'], ensure_ascii=False)[:300]}"
        )
        # Trigger free API discovery
        try:
            from modules.free_api_hunter import hunt_all_free_apis
            await hunt_all_free_apis()
        except Exception as e:
            log.warning("Free API hunt failed: %s", e)

    return {"ok": True, "active_providers": active_count, "status": status}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
    asyncio.run(run_traffic_max_cycle())
