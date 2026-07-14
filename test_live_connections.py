#!/usr/bin/env python3
"""
SuperMegaBot — Live Connection Test (v3)
=========================================
Testet alle APIs live mit korrekten Env-Variablen-Namen.
Gibt NIEMALS Secrets oder Token-Werte aus.

Usage:
  python3 test_live_connections.py           # alle Tests
  python3 test_live_connections.py shopify   # nur Shopify
  python3 test_live_connections.py --json    # JSON-Output für Scripts
"""
import os
import sys
import json
import time
import traceback
from pathlib import Path
from datetime import datetime

# ── .env laden (immer aus supermegabot/.env) ───────────────────────────────────
_ENV = Path(__file__).parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(_ENV, override=True)
except ImportError:
    if _ENV.exists():
        for line in _ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

try:
    import requests
except ImportError:
    print("❌ pip install requests")
    sys.exit(1)

RESULTS: dict = {}
TIMEOUT = 12
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; X = "\033[0m"

def _e(*keys) -> str:
    for k in keys:
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""

def _mask(v: str) -> str:
    if not v or len(v) < 5:
        return "***"
    return v[:4] + "…" + v[-3:]

def section(t): print(f"\n{B}{'─'*52}{X}\n  {t}\n{'─'*52}")
def ok(n, m=""): print(f"  {G}✅{X} {n:<22} {m}"); RESULTS[n] = {"ok": True, "msg": m}
def fail(n, m=""): print(f"  {R}❌{X} {n:<22} {R}{m}{X}"); RESULTS[n] = {"ok": False, "msg": m}
def warn(n, m=""): print(f"  {Y}⚠️ {X} {n:<22} {Y}{m}{X}"); RESULTS[n] = {"ok": None, "msg": m}

def _get(url, headers=None):
    t0 = time.monotonic()
    try:
        r = requests.get(url, headers=headers or {}, timeout=TIMEOUT)
        return r.status_code, r.json() if "json" in r.headers.get("content-type","") else {}, int((time.monotonic()-t0)*1000)
    except Exception as e:
        return 0, {}, 0

def _post(url, headers=None, payload=None):
    t0 = time.monotonic()
    try:
        r = requests.post(url, headers={**headers, "Content-Type": "application/json"} if headers else {"Content-Type":"application/json"},
                          json=payload, timeout=TIMEOUT)
        return r.status_code, r.json() if "json" in r.headers.get("content-type","") else {}, int((time.monotonic()-t0)*1000)
    except Exception as e:
        return 0, {}, 0


# ══════════════════════════════════════════════════════════
def test_telegram():
    section("1. TELEGRAM")
    tok = _e("TELEGRAM_BOT_TOKEN")
    chat = _e("TELEGRAM_CHAT_ID")
    if not tok: fail("Bot Token", "TELEGRAM_BOT_TOKEN fehlt"); return
    c, d, ms = _get(f"https://api.telegram.org/bot{tok}/getMe")
    if c == 200 and d.get("ok"):
        bot = d.get("result", {})
        ok("Bot", f"@{bot.get('username')} — {ms}ms")
    else:
        fail("Bot Token", f"HTTP {c} — {d.get('description','')}")
    if not chat: warn("Chat ID", "TELEGRAM_CHAT_ID fehlt")
    else: ok("Chat ID", _mask(chat))


def test_anthropic():
    section("2. ANTHROPIC (Claude)")
    key = _e("ANTHROPIC_API_KEY")
    if not key: fail("API Key", "ANTHROPIC_API_KEY fehlt"); return
    ok("Key vorhanden", _mask(key))
    c, d, ms = _post("https://api.anthropic.com/v1/messages",
                     {"x-api-key": key, "anthropic-version": "2023-06-01"},
                     {"model": "claude-haiku-4-5-20251001", "max_tokens": 5,
                      "messages": [{"role": "user", "content": "Hi"}]})
    if c == 200 and "content" in d:
        ok("Claude haiku-4-5", f"{ms}ms")
    elif c == 529:
        warn("Claude", "529 — Überlastet / keine Credits")
    elif c == 401:
        fail("Claude", "401 — Key ungültig")
    else:
        fail("Claude", f"HTTP {c}")


def test_openai():
    section("3. OPENAI")
    key = _e("OPENAI_API_KEY")
    if not key: fail("API Key", "OPENAI_API_KEY fehlt"); return
    ok("Key vorhanden", _mask(key))
    c, d, ms = _post("https://api.openai.com/v1/chat/completions",
                     {"Authorization": f"Bearer {key}"},
                     {"model": "gpt-4o-mini", "max_tokens": 5,
                      "messages": [{"role": "user", "content": "Hi"}]})
    if c == 200 and "choices" in d:
        ok("GPT-4o-mini", f"{ms}ms")
    elif c == 401:
        fail("OpenAI", "401 — Key ungültig")
    elif c == 429:
        warn("OpenAI", "429 — Rate Limit / keine Credits")
    else:
        fail("OpenAI", f"HTTP {c}")


def test_groq():
    section("4. GROQ (Free AI Fallback)")
    key = _e("GROQ_API_KEY")
    if not key: warn("Groq", "GROQ_API_KEY nicht gesetzt"); return
    c, d, ms = _post("https://api.groq.com/openai/v1/chat/completions",
                     {"Authorization": f"Bearer {key}"},
                     {"model": "llama-3.1-8b-instant", "max_tokens": 5,
                      "messages": [{"role": "user", "content": "Hi"}]})
    if c == 200:
        ok("Groq llama-3.1-8b", f"{ms}ms")
    elif c == 401:
        fail("Groq", "401 — Key ungültig oder abgelaufen")
    else:
        fail("Groq", f"HTTP {c}")


def test_gemini():
    section("5. GEMINI (Free AI Fallback)")
    key = _e("GEMINI_API_KEY", "GCP_API_KEY", "GOOGLE_AI_API_KEY")
    if not key: warn("Gemini", "GEMINI_API_KEY nicht gesetzt"); return
    c, d, ms = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
        {},
        {"contents": [{"parts": [{"text": "Hi"}]}]}
    )
    if c == 200 and "candidates" in d:
        ok("gemini-2.0-flash", f"{ms}ms")
    elif c == 429:
        warn("Gemini", "429 — Quota erreicht (tägl. Reset)")
    else:
        fail("Gemini", f"HTTP {c}")


def test_openrouter():
    section("6. OPENROUTER")
    key = _e("OPENROUTER_API_KEY")
    if not key: warn("OpenRouter", "OPENROUTER_API_KEY nicht gesetzt"); return
    c, d, ms = _post("https://openrouter.ai/api/v1/chat/completions",
                     {"Authorization": f"Bearer {key}",
                      "HTTP-Referer": "https://supermegabot-production.up.railway.app"},
                     {"model": "google/gemma-4-26b-a4b-it:free", "max_tokens": 5,
                      "messages": [{"role": "user", "content": "Hi"}]})
    if c == 200 and "choices" in d:
        ok("gemma-4-26b:free", f"{ms}ms")
    elif c == 402:
        warn("OpenRouter", "402 — Guthaben leer")
    else:
        fail("OpenRouter", f"HTTP {c}")


def test_shopify():
    section("7. SHOPIFY")
    # Korrekte Variablen-Namen — mehrere Aliase unterstützt
    domain = _e("SHOPIFY_SHOP_DOMAIN", "SHOPIFY_STORE_URL", "SHOPIFY_DOMAIN")
    token  = _e("SHOPIFY_ACCESS_TOKEN", "SHOPIFY_ADMIN_API_TOKEN", "SHOPIFY_ADMIN_TOKEN")
    if not domain: fail("Domain", "SHOPIFY_SHOP_DOMAIN fehlt"); return
    if not token:  fail("Token",  "SHOPIFY_ACCESS_TOKEN fehlt"); return
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    ver = _e("SHOPIFY_API_VERSION") or "2025-01"
    ok("Domain", domain.replace("https://",""))
    ok("Token",  _mask(token))
    c, d, ms = _get(f"{domain}/admin/api/{ver}/shop.json",
                    {"X-Shopify-Access-Token": token})
    if c == 200 and "shop" in d:
        shop = d["shop"]
        ok("Shop", f"{shop.get('name')} | {shop.get('domain')}")
        ok("Plan",  f"{shop.get('plan_name')} | {shop.get('currency')}")
        # Produktanzahl
        c2, d2, _ = _get(f"{domain}/admin/api/{ver}/products/count.json",
                         {"X-Shopify-Access-Token": token})
        if c2 == 200:
            ok("Produkte", f"{d2.get('count','?')} aktiv")
    elif c == 401:
        fail("Shopify", "401 — Token ungültig/abgelaufen")
    else:
        fail("Shopify", f"HTTP {c}")


def test_stripe():
    section("8. STRIPE")
    key = _e("STRIPE_SECRET_KEY", "STRIPE_API_KEY", "STRIPE_SECRET")
    if not key: fail("Secret Key", "STRIPE_SECRET_KEY fehlt"); return
    ok("Key", _mask(key))
    c, d, ms = _get("https://api.stripe.com/v1/account",
                    {"Authorization": f"Bearer {key}"})
    if c == 200:
        ok("Account", f"{d.get('business_profile',{}).get('name',d.get('id',''))}")
        # Balance
        c2, d2, _ = _get("https://api.stripe.com/v1/balance",
                         {"Authorization": f"Bearer {key}"})
        if c2 == 200:
            avail = d2.get("available", [])
            bal = ", ".join(f"{a['amount']/100:.2f} {a['currency'].upper()}" for a in avail)
            ok("Balance", bal or "€0")
    elif c == 401:
        fail("Stripe", "401 — Key ungültig")
    else:
        fail("Stripe", f"HTTP {c}")


def test_supabase():
    section("9. SUPABASE")
    url  = _e("SUPABASE_URL")
    anon = _e("SUPABASE_ANON_KEY")
    svc  = _e("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY")
    if not url:  fail("URL",      "SUPABASE_URL fehlt"); return
    if not anon: fail("Anon Key", "SUPABASE_ANON_KEY fehlt"); return
    ok("URL", url[:40] + "…")
    # Test mit Service Key gegen echte Tabelle (anon key hat keine Schema-Introspection)
    test_key = svc if svc else anon
    c, d, ms = _get(f"{url}/rest/v1/agent_memory?limit=1",
                    {"apikey": test_key, "Authorization": f"Bearer {test_key}"})
    if c == 200:
        ok("REST API", f"{ms}ms | agent_memory erreichbar")
    elif c == 401:
        # Anon key hat keine Berechtigung — Supabase selbst antwortet aber
        warn("REST API", f"401 — Service Key nötig für RLS-geschützte Tabellen")
    elif c in (400, 404):
        ok("REST API", f"{ms}ms (Tabelle leer oder nicht gefunden)")
    else:
        fail("REST API", f"HTTP {c}")
    if svc:
        ok("Service Key", _mask(svc) + " ✓")
    else:
        warn("Service Key", "SUPABASE_SERVICE_KEY fehlt (Backend-Writes nötig)")


def test_klaviyo():
    section("10. KLAVIYO")
    key = _e("KLAVIYO_API_KEY", "KLAVIYO_API_KEY_AIITEC")
    if not key: fail("API Key", "KLAVIYO_API_KEY fehlt"); return
    ok("Key", _mask(key))
    c, d, ms = _get("https://a.klaviyo.com/api/profiles/",
                    {"Authorization": f"Klaviyo-API-Key {key}", "revision": "2024-10-15"})
    if c == 200:
        ok("Klaviyo", f"{ms}ms | {d.get('meta',{}).get('total',0)} Profile")
    elif c == 401:
        fail("Klaviyo", "401 — Key ungültig")
    elif c == 429:
        warn("Klaviyo", "429 — Rate Limit")
    else:
        fail("Klaviyo", f"HTTP {c}")


def test_mailchimp():
    section("11. MAILCHIMP")
    key = _e("MAILCHIMP_API_KEY")
    dc  = _e("MAILCHIMP_SERVER_PREFIX")
    if not key: fail("API Key", "MAILCHIMP_API_KEY fehlt"); return
    if not dc:
        dc = key.split("-")[-1] if "-" in key else "us7"
    c, d, ms = _get(f"https://{dc}.api.mailchimp.com/3.0/lists",
                    {"Authorization": f"Bearer {key}"})
    if c == 200:
        ok("Mailchimp", f"{len(d.get('lists',[]))} Listen")
    elif c == 401:
        fail("Mailchimp", "401 — Key ungültig oder falsches DC")
    else:
        fail("Mailchimp", f"HTTP {c}")


def test_printify():
    section("12. PRINTIFY")
    key = _e("PRINTIFY_API_KEY")
    if not key: fail("API Key", "PRINTIFY_API_KEY fehlt"); return
    c, d, ms = _get("https://api.printify.com/v1/shops.json",
                    {"Authorization": f"Bearer {key}"})
    if c == 200:
        shops = d if isinstance(d, list) else d.get("data", [])
        ok("Printify", f"{len(shops)} Shops")
    elif c == 401:
        fail("Printify", "401 — Key ungültig")
    else:
        fail("Printify", f"HTTP {c}")


def test_github():
    section("13. GITHUB")
    tok = _e("GITHUB_TOKEN", "GITHUB_TOKEN_CLASSIC", "GITHUB_TOKEN_FINE")
    if not tok: fail("Token", "GITHUB_TOKEN fehlt"); return
    c, d, ms = _get("https://api.github.com/user",
                    {"Authorization": f"Bearer {tok}", "User-Agent": "SuperMegaBot"})
    if c == 200:
        ok("GitHub", f"@{d.get('login')} | {ms}ms")
    elif c == 401:
        fail("GitHub", "401 — Token ungültig oder abgelaufen")
    else:
        fail("GitHub", f"HTTP {c}")


def test_meta():
    section("14. META (Facebook/Instagram)")
    tok = _e("META_ACCESS_TOKEN", "FB_ACCESS_TOKEN")
    pid = _e("META_PAGE_ID", "FB_PAGE_ID")
    if not tok: warn("Access Token", "META_ACCESS_TOKEN fehlt"); return
    c, d, ms = _get(f"https://graph.facebook.com/me?access_token={tok}")
    if c == 200 and "id" in d:
        ok("Meta", f"id={d.get('id')} | {ms}ms")
    elif c == 190:
        fail("Meta", "Token abgelaufen — neu generieren!")
    else:
        fail("Meta", f"HTTP {c}")


def test_digistore24():
    section("15. DIGISTORE24")
    key = _e("DIGISTORE24_API_KEY")
    if not key: fail("API Key", "DIGISTORE24_API_KEY fehlt"); return
    ok("Key", _mask(key) + f" ({key[:7]}...)")
    # DS24 API ist komplexer — einfacher Ping
    c, d, ms = _get(f"https://www.digistore24.com/api/call/account/info/format/json",
                    {"X-DS24-AUTH-KEY": key})
    if c in (200, 401, 403):
        if c == 200:
            ok("DS24 API", f"verbunden | {ms}ms")
        else:
            warn("DS24 API", f"HTTP {c} — Key möglicherweise falsch (Konto: aiitec 1581233-...)")
    else:
        fail("DS24 API", f"HTTP {c}")


# ══════════════════════════════════════════════════════════
ALL_TESTS = {
    "telegram": test_telegram, "anthropic": test_anthropic,
    "openai": test_openai, "groq": test_groq, "gemini": test_gemini,
    "openrouter": test_openrouter, "shopify": test_shopify,
    "stripe": test_stripe, "supabase": test_supabase,
    "klaviyo": test_klaviyo, "mailchimp": test_mailchimp,
    "printify": test_printify, "github": test_github,
    "meta": test_meta, "digistore24": test_digistore24,
}


def main():
    json_out = "--json" in sys.argv
    filter_args = [a for a in sys.argv[1:] if not a.startswith("-")]
    tests = {k: v for k, v in ALL_TESTS.items()
             if not filter_args or k in filter_args}

    if not json_out:
        print(f"\n{B}{'═'*52}{X}")
        print(f"{B}  SuperMegaBot Live Connection Test{X}")
        print(f"{B}  {datetime.now().strftime('%d.%m.%Y %H:%M')}{X}")
        print(f"{B}{'═'*52}{X}")

    for name, fn in tests.items():
        try:
            fn()
        except Exception as e:
            fail(name, f"Exception: {e}")

    ok_count  = sum(1 for v in RESULTS.values() if v.get("ok") is True)
    warn_count = sum(1 for v in RESULTS.values() if v.get("ok") is None)
    fail_count = sum(1 for v in RESULTS.values() if v.get("ok") is False)
    total = len(RESULTS)

    if json_out:
        print(json.dumps({"ok": ok_count, "warn": warn_count, "fail": fail_count,
                          "total": total, "results": RESULTS}, indent=2))
        return

    print(f"\n{B}{'═'*52}{X}")
    print(f"  {G}✅ {ok_count}{X}  {Y}⚠️  {warn_count}{X}  {R}❌ {fail_count}{X}  von {total} Tests")
    if fail_count > 0:
        failed = [n for n, v in RESULTS.items() if v.get("ok") is False]
        print(f"\n  {R}Defekt: {', '.join(failed)}{X}")
    print(f"{B}{'═'*52}{X}\n")

    # Report schreiben
    rp = Path(__file__).parent / "data" / "last_test_results.json"
    rp.parent.mkdir(exist_ok=True)
    rp.write_text(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "ok": ok_count, "warn": warn_count, "fail": fail_count,
        "results": RESULTS
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
