#!/usr/bin/env python3
"""
test_all_apis.py — Testet ALLE konfigurierten APIs und zeigt Status
Ausführen: python3 ~/supermegabot/scripts/test_all_apis.py
"""

import asyncio
import os
import sys
import time
from pathlib import Path

HOME = Path.home()
MEGA_DIR = HOME / "supermegabot"
sys.path.insert(0, str(MEGA_DIR))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(MEGA_DIR / ".env")
except ImportError:
    env_file = MEGA_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
GRAY   = "\033[90m"
BOLD   = "\033[1m"
NC     = "\033[0m"

results = []


async def test(name: str, coro):
    t0 = time.monotonic()
    try:
        ok, info = await asyncio.wait_for(coro, timeout=12)
        ms = int((time.monotonic() - t0) * 1000)
        results.append((name, ok, info, ms))
        status = f"{GREEN}✅ OK{NC}" if ok else f"{YELLOW}⚠️  Kein Key{NC}"
        print(f"  {status:<30} {GRAY}{name}{NC}: {info[:70]}")
    except asyncio.TimeoutError:
        ms = int((time.monotonic() - t0) * 1000)
        results.append((name, False, "Timeout", ms))
        print(f"  {RED}⏱️ Timeout{NC}            {GRAY}{name}{NC}")
    except Exception as e:
        ms = int((time.monotonic() - t0) * 1000)
        results.append((name, False, str(e)[:80], ms))
        print(f"  {RED}❌ Fehler{NC}             {GRAY}{name}{NC}: {str(e)[:60]}")


# ── Test functions ───────────────────────────────────────────────────────────

async def test_shopify():
    token  = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    if not token or not domain:
        return False, "SHOPIFY_ACCESS_TOKEN / SHOPIFY_SHOP_DOMAIN fehlt"
    import aiohttp
    base = f"https://{domain}" if not domain.startswith("http") else domain
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{base}/admin/api/2024-10/shop.json",
                         headers={"X-Shopify-Access-Token": token}) as r:
            if r.status == 200:
                d = await r.json()
                return True, f"Shop: {d['shop']['name']} ({d['shop']['domain']})"
            return False, f"HTTP {r.status}"

async def test_ollama():
    import aiohttp
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{host}/api/tags") as r:
            if r.status == 200:
                d = await r.json()
                models = [m["name"] for m in d.get("models", [])]
                return True, f"{len(models)} Modelle: {', '.join(models[:3])}"
            return False, f"HTTP {r.status}"

async def test_deepseek():
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        return False, "DEEPSEEK_API_KEY fehlt"
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.get("https://api.deepseek.com/v1/models",
                         headers={"Authorization": f"Bearer {key}"}) as r:
            if r.status == 200:
                return True, "DeepSeek API erreichbar"
            return False, f"HTTP {r.status}"

async def test_anthropic():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return False, "ANTHROPIC_API_KEY fehlt"
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.post("https://api.anthropic.com/v1/messages",
                         headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                  "content-type": "application/json"},
                         json={"model": "claude-haiku-4-5-20251001", "max_tokens": 10,
                               "messages": [{"role": "user", "content": "hi"}]}) as r:
            if r.status == 200:
                return True, "Claude API OK"
            return False, f"HTTP {r.status}"

async def test_perplexity():
    key = os.getenv("PERPLEXITY_API_KEY", "")
    if not key:
        return False, "PERPLEXITY_API_KEY fehlt"
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.post("https://api.perplexity.ai/chat/completions",
                         headers={"Authorization": f"Bearer {key}"},
                         json={"model": "sonar", "messages": [{"role": "user", "content": "hi"}],
                               "max_tokens": 5}) as r:
            if r.status == 200:
                return True, "Perplexity API OK"
            return False, f"HTTP {r.status}"

async def test_supabase():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return False, "SUPABASE_URL / SUPABASE_ANON_KEY fehlt"
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{url}/rest/v1/",
                         headers={"apikey": key, "Authorization": f"Bearer {key}"}) as r:
            return r.status < 400, f"Supabase {'OK' if r.status < 400 else f'HTTP {r.status}'}"

async def test_telegram():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return False, "TELEGRAM_BOT_TOKEN fehlt"
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.telegram.org/bot{token}/getMe") as r:
            if r.status == 200:
                d = await r.json()
                name = d.get("result", {}).get("username", "?")
                return True, f"Bot: @{name}"
            return False, f"HTTP {r.status}"

async def test_social(name: str):
    from modules.social_connectors import CONNECTORS
    cls = CONNECTORS.get(name)
    if not cls:
        return False, "Connector nicht gefunden"
    ok, info = await cls().ping()
    return ok, info

async def test_mailchimp():
    from modules.mailchimp_automation import ping
    ok, info = await ping()
    return ok, info or "Mailchimp ping fehlgeschlagen"

async def test_digistore():
    from modules.digistore24_automation import ping
    ok = await ping()
    return ok, "DS24 API erreichbar" if ok else "DIGISTORE24_API_KEY fehlt"

async def test_printify():
    from modules.printify_automation import ping
    ok = await ping()
    return ok, "Printify API erreichbar" if ok else "PRINTIFY_API_KEY fehlt"

async def test_etsy():
    from modules.ecommerce_connectors import EtsyConnector
    return await EtsyConnector().ping()

async def test_gumroad():
    from modules.ecommerce_connectors import GumroadConnector
    return await GumroadConnector().ping()

async def test_github():
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        return False, "GITHUB_TOKEN fehlt"
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.get("https://api.github.com/user",
                         headers={"Authorization": f"Bearer {token}"}) as r:
            if r.status == 200:
                d = await r.json()
                return True, f"GitHub: {d.get('login', '?')}"
            return False, f"HTTP {r.status}"

async def test_railway():
    import aiohttp
    url = os.getenv("SHOPIFY_SUITE_URL", "https://shopify-suite-v2-production.up.railway.app")
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{url}/health") as r:
            return r.status < 400, f"Railway HTTP {r.status}"


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    print(f"\n{BOLD}{'═'*55}{NC}")
    print(f"{BOLD}  SuperMegaBot — API Test Suite{NC}")
    print(f"{BOLD}{'═'*55}{NC}\n")

    sections = [
        ("🛍️  E-Commerce", [
            ("Shopify",      test_shopify()),
            ("Digistore24",  test_digistore()),
            ("Etsy",         test_etsy()),
            ("Gumroad",      test_gumroad()),
            ("Printify",     test_printify()),
            ("Mailchimp",    test_mailchimp()),
        ]),
        ("🤖  AI Provider", [
            ("Ollama (lokal)", test_ollama()),
            ("Anthropic",     test_anthropic()),
            ("DeepSeek",      test_deepseek()),
            ("Perplexity",    test_perplexity()),
        ]),
        ("📱  Social Media", [
            ("TikTok",     test_social("tiktok")),
            ("Pinterest",  test_social("pinterest")),
            ("Meta/IG",    test_social("meta")),
            ("Reddit",     test_social("reddit")),
            ("YouTube",    test_social("youtube")),
            ("Twitter/X",  test_social("twitter")),
            ("Discord",    test_social("discord")),
        ]),
        ("☁️  Infrastructure", [
            ("Telegram Bot", test_telegram()),
            ("Supabase",     test_supabase()),
            ("GitHub",       test_github()),
            ("Railway",      test_railway()),
        ]),
    ]

    for section_name, tests in sections:
        print(f"\n{BLUE}{section_name}{NC}")
        await asyncio.gather(*(test(name, coro) for name, coro in tests))

    # ── Zusammenfassung ──────────────────────────────────────────
    ok_count  = sum(1 for _, ok, _, _ in results if ok)
    fail_count = len(results) - ok_count

    print(f"\n{BOLD}{'═'*55}{NC}")
    print(f"{BOLD}  Ergebnis: {GREEN}{ok_count} OK{NC}{BOLD} | {RED}{fail_count} fehlen{NC}")
    print(f"{BOLD}{'═'*55}{NC}")

    if fail_count:
        print(f"\n{YELLOW}Fehlende Keys in ~/supermegabot/.env eintragen.{NC}")
        print(f"Anleitung in ~/.env: Kommentar (#) entfernen und Key eintragen.\n")

    # Speichere Ergebnis als JSON für Dashboard
    import json
    out = Path(MEGA_DIR) / "data" / "api_test_results.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps([
        {"name": n, "ok": ok, "info": info, "ms": ms}
        for n, ok, info, ms in results
    ], indent=2))
    print(f"  Gespeichert: {out}\n")


if __name__ == "__main__":
    asyncio.run(main())
