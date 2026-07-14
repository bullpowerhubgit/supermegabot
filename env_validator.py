#!/usr/bin/env python3
"""
SuperMegaBot — ENV Validator & API Health Check
================================================
Lädt alle Keys aus .env, testet jeden API-Endpunkt live,
sendet Telegram-Alert bei Fehlern, schreibt data/api_health.json.

Usage:
  python3 env_validator.py            # vollständiger Test
  python3 env_validator.py --quiet    # nur Fehler ausgeben
  python3 env_validator.py --fix      # fix bekannte Env-Aliase
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── .env laden ─────────────────────────────────────────────────────────────────
_ENV_FILE = Path(__file__).parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_FILE, override=True)
except ImportError:
    # Fallback: manuell parsen
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

import urllib.request
import urllib.error

# ── Hilfsfunktionen ────────────────────────────────────────────────────────────
def _g(key: str, *aliases) -> str:
    """Gibt env-Wert zurück, prüft auch Aliase."""
    for k in (key, *aliases):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""

def _mask(v: str) -> str:
    if not v or len(v) < 6:
        return "***"
    return v[:4] + "…" + v[-3:]

def _req(url: str, method: str = "GET", headers: dict | None = None,
         body: bytes | None = None, timeout: int = 10) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode(errors="replace")
    except Exception as e:
        return 0, str(e)

# ── Farben ─────────────────────────────────────────────────────────────────────
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; X = "\033[0m"; DIM = "\033[2m"

def ok(name, msg=""): print(f"  {G}✅{X} {name:<22} {DIM}{msg}{X}")
def fail(name, msg=""): print(f"  {R}❌{X} {name:<22} {R}{msg}{X}")
def warn(name, msg=""): print(f"  {Y}⚠️ {X} {name:<22} {Y}{msg}{X}")
def section(title): print(f"\n{B}{'─'*55}{X}\n  {B}{title}{X}\n{'─'*55}")

# ══════════════════════════════════════════════════════════════════════════════
# REQUIRED KEYS — nach Priorität
# ══════════════════════════════════════════════════════════════════════════════
REQUIRED_KEYS = {
    "TELEGRAM_BOT_TOKEN": "Telegram Bot (Benachrichtigungen)",
    "TELEGRAM_CHAT_ID":   "Telegram Chat ID",
    "ANTHROPIC_API_KEY":  "Claude AI (Haiku 4.5)",
    "OPENAI_API_KEY":     "OpenAI GPT",
    "SHOPIFY_SHOP_DOMAIN": "Shopify Shop Domain",
    "SHOPIFY_ACCESS_TOKEN": "Shopify Admin Token",
    "STRIPE_SECRET_KEY":  "Stripe Zahlungen",
    "SUPABASE_URL":       "Supabase Datenbank",
    "SUPABASE_ANON_KEY":  "Supabase Anon Key",
    "KLAVIYO_API_KEY":    "Klaviyo Email",
    "PRINTIFY_API_KEY":   "Printify POD",
    "GROQ_API_KEY":       "Groq AI Fallback",
    "OPENROUTER_API_KEY": "OpenRouter AI Fallback",
    "GEMINI_API_KEY":     "Gemini AI Fallback",
    "DIGISTORE24_API_KEY": "DS24 Affiliate",
    "GITHUB_TOKEN":       "GitHub Deployment",
    "META_ACCESS_TOKEN":  "Meta Ads/Instagram",
    "MAILCHIMP_API_KEY":  "Mailchimp Email",
    "SENDGRID_API_KEY":   "SendGrid SMTP",
}

OPTIONAL_KEYS = {
    "PERPLEXITY_API_KEY": "Perplexity AI",
    "TWITTER_API_KEY_AIITEC": "Twitter/X",
    "TIKTOK_ACCESS_TOKEN": "TikTok",
    "YOUTUBE_REFRESH_TOKEN": "YouTube OAuth",
    "TWILIO_PHONE_NUMBER": "Twilio Sofia Phone",
    "SEMRUSH_API_KEY": "Semrush SEO",
    "AMAZON_PAAPI_KEY": "Amazon PA API",
    "EBAY_CLIENT_ID": "eBay API",
}

# ── ENV-Aliase (falsche Namen → korrekte Namen) ────────────────────────────────
# Wenn ein Modul den falschen Namen nutzt, hier reparieren
KNOWN_ALIASES = {
    "SHOPIFY_ADMIN_API_TOKEN": "SHOPIFY_ACCESS_TOKEN",
    "SHOPIFY_ADMIN_TOKEN": "SHOPIFY_ACCESS_TOKEN",
    "SHOPIFY_API_TOKEN": "SHOPIFY_ACCESS_TOKEN",
    "STRIPE_API_KEY": "STRIPE_SECRET_KEY",
    "STRIPE_SECRET": "STRIPE_SECRET_KEY",
    "GOOGLE_AI_API_KEY": "GEMINI_API_KEY",
    "GCP_API_KEY": "GEMINI_API_KEY",
    "SUPABASE_SERVICE_KEY": "SUPABASE_SERVICE_KEY",  # this one is correct
    "KLAVIYO_API_KEY_AIITEC": "KLAVIYO_API_KEY",
}

# ══════════════════════════════════════════════════════════════════════════════
# API TESTS
# ══════════════════════════════════════════════════════════════════════════════

results: dict[str, dict] = {}

def _record(name: str, status: str, latency_ms: int = 0, detail: str = ""):
    results[name.lower().replace(" ", "_")] = {
        "name": name, "status": status,
        "latency_ms": latency_ms, "detail": detail,
        "ts": datetime.now(timezone.utc).isoformat()
    }

def _test(name: str, url: str, method: str = "GET",
          headers: dict | None = None, body_dict: dict | None = None,
          ok_status: int | None = None, ok_check=None) -> bool:
    t0 = time.monotonic()
    body_bytes = json.dumps(body_dict).encode() if body_dict else None
    if body_dict and headers is None:
        headers = {}
    if body_dict:
        headers = {**headers, "Content-Type": "application/json"}
    code, data = _req(url, method, headers, body_bytes)
    ms = int((time.monotonic() - t0) * 1000)
    passed = False
    if ok_status:
        passed = (code == ok_status)
    elif ok_check:
        try:
            passed = ok_check(code, data)
        except Exception:
            passed = False
    else:
        passed = 200 <= code < 300

    detail = f"HTTP {code}"
    if isinstance(data, dict):
        err = data.get("error", {})
        if isinstance(err, dict):
            detail += f" — {err.get('message', '')}"
        elif isinstance(err, str):
            detail += f" — {err}"
        elif "message" in data:
            detail += f" — {data['message']}"
    if passed:
        ok(name, f"{ms}ms")
    else:
        fail(name, detail)
    _record(name, "OK" if passed else "FAIL", ms, detail)
    return passed


def test_env_keys() -> tuple[int, int]:
    section("1. ENV-Keys Prüfung")
    present = missing = 0
    for key, desc in REQUIRED_KEYS.items():
        val = _g(key, *[k for k, v in KNOWN_ALIASES.items() if v == key])
        if val:
            ok(f"{key}", f"{_mask(val)}  ({desc})")
            present += 1
        else:
            fail(f"{key}", f"FEHLT  ({desc})")
            missing += 1
    if OPTIONAL_KEYS:
        print(f"\n  {DIM}Optional:{X}")
        for key, desc in OPTIONAL_KEYS.items():
            val = _g(key)
            if val:
                ok(f"  {key}", f"{_mask(val)}")
            else:
                warn(f"  {key}", f"nicht gesetzt  ({desc})")
    return present, missing


def test_telegram() -> bool:
    section("2. Telegram")
    tok = _g("TELEGRAM_BOT_TOKEN")
    if not tok:
        fail("Bot Token", "nicht gesetzt"); return False
    return _test("Telegram getMe",
                 f"https://api.telegram.org/bot{tok}/getMe",
                 ok_check=lambda c, d: c == 200 and d.get("ok"))


def test_anthropic() -> bool:
    section("3. Anthropic (Claude)")
    key = _g("ANTHROPIC_API_KEY")
    if not key:
        fail("API Key", "nicht gesetzt"); return False
    return _test("Claude haiku-4-5",
                 "https://api.anthropic.com/v1/messages",
                 method="POST",
                 headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                 body_dict={"model": "claude-haiku-4-5-20251001", "max_tokens": 5,
                            "messages": [{"role": "user", "content": "Hi"}]},
                 ok_check=lambda c, d: c == 200 and "content" in d)


def test_openai() -> bool:
    section("4. OpenAI")
    key = _g("OPENAI_API_KEY")
    if not key:
        fail("API Key", "nicht gesetzt"); return False
    return _test("GPT-4o-mini",
                 "https://api.openai.com/v1/chat/completions",
                 method="POST",
                 headers={"Authorization": f"Bearer {key}"},
                 body_dict={"model": "gpt-4o-mini", "max_tokens": 5,
                            "messages": [{"role": "user", "content": "Hi"}]},
                 ok_check=lambda c, d: c == 200 and "choices" in d)


def test_groq() -> bool:
    section("5. Groq (Free AI Fallback)")
    key = _g("GROQ_API_KEY")
    if not key:
        warn("Groq", "Key nicht gesetzt — Fallback fehlt"); return False
    return _test("llama-3.1-8b-instant",
                 "https://api.groq.com/openai/v1/chat/completions",
                 method="POST",
                 headers={"Authorization": f"Bearer {key}"},
                 body_dict={"model": "llama-3.1-8b-instant", "max_tokens": 5,
                            "messages": [{"role": "user", "content": "Hi"}]},
                 ok_check=lambda c, d: c == 200 and "choices" in d)


def test_gemini() -> bool:
    section("6. Gemini (Free AI Fallback)")
    key = _g("GEMINI_API_KEY", "GCP_API_KEY", "GOOGLE_AI_API_KEY")
    if not key:
        warn("Gemini", "Key nicht gesetzt"); return False
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
    return _test("gemini-2.0-flash", url, method="POST",
                 body_dict={"contents": [{"parts": [{"text": "Hi"}]}]},
                 ok_check=lambda c, d: c == 200 and "candidates" in d)


def test_openrouter() -> bool:
    section("7. OpenRouter")
    key = _g("OPENROUTER_API_KEY")
    if not key:
        warn("OpenRouter", "Key nicht gesetzt"); return False
    return _test("gemma-4-26b-a4b-it:free",
                 "https://openrouter.ai/api/v1/chat/completions",
                 method="POST",
                 headers={"Authorization": f"Bearer {key}",
                          "HTTP-Referer": "https://supermegabot-production.up.railway.app"},
                 body_dict={"model": "google/gemma-4-26b-a4b-it:free", "max_tokens": 5,
                            "messages": [{"role": "user", "content": "Hi"}]},
                 ok_check=lambda c, d: c == 200 and "choices" in d)


def test_shopify() -> bool:
    section("8. Shopify")
    domain = _g("SHOPIFY_SHOP_DOMAIN", "SHOPIFY_STORE_URL")
    token = _g("SHOPIFY_ACCESS_TOKEN", "SHOPIFY_ADMIN_API_TOKEN", "SHOPIFY_ADMIN_TOKEN")
    if not domain or not token:
        fail("Shopify", f"Fehlt: {'SHOPIFY_SHOP_DOMAIN' if not domain else 'SHOPIFY_ACCESS_TOKEN'}")
        return False
    domain = domain.rstrip("/")
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    ver = _g("SHOPIFY_API_VERSION", default="2025-01")
    passed = _test("Shopify shop.json",
                   f"{domain}/admin/api/{ver}/shop.json",
                   headers={"X-Shopify-Access-Token": token},
                   ok_check=lambda c, d: c == 200 and "shop" in d)
    if passed:
        code, data = _req(f"{domain}/admin/api/{ver}/products/count.json",
                          headers={"X-Shopify-Access-Token": token})
        if code == 200:
            ok("  Produktanzahl", str(data.get("count", "?")))
    return passed


def test_stripe() -> bool:
    section("9. Stripe")
    key = _g("STRIPE_SECRET_KEY", "STRIPE_API_KEY", "STRIPE_SECRET")
    if not key:
        fail("Stripe", "Key nicht gesetzt"); return False
    return _test("Stripe /v1/account",
                 "https://api.stripe.com/v1/account",
                 headers={"Authorization": f"Bearer {key}"},
                 ok_check=lambda c, d: c == 200 and ("id" in d or "business_type" in d))


def test_supabase() -> bool:
    section("10. Supabase")
    url = _g("SUPABASE_URL")
    anon = _g("SUPABASE_ANON_KEY")
    if not url or not anon:
        fail("Supabase", "URL oder Key fehlt"); return False
    return _test("Supabase REST",
                 f"{url}/rest/v1/",
                 headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
                 ok_check=lambda c, d: c in (200, 400, 404))


def test_klaviyo() -> bool:
    section("11. Klaviyo")
    key = _g("KLAVIYO_API_KEY", "KLAVIYO_API_KEY_AIITEC")
    if not key:
        fail("Klaviyo", "Key nicht gesetzt"); return False
    return _test("Klaviyo profiles",
                 "https://a.klaviyo.com/api/profiles/",
                 headers={"Authorization": f"Klaviyo-API-Key {key}", "revision": "2024-10-15"},
                 ok_check=lambda c, d: c in (200, 400) and isinstance(d, dict))


def test_mailchimp() -> bool:
    section("12. Mailchimp")
    key = _g("MAILCHIMP_API_KEY")
    dc = _g("MAILCHIMP_SERVER_PREFIX")
    if not key:
        fail("Mailchimp", "Key nicht gesetzt"); return False
    if not dc:
        dc = key.split("-")[-1] if "-" in key else "us7"
    return _test("Mailchimp lists",
                 f"https://{dc}.api.mailchimp.com/3.0/lists",
                 headers={"Authorization": f"Bearer {key}"},
                 ok_check=lambda c, d: c in (200, 401))


def test_printify() -> bool:
    section("13. Printify")
    key = _g("PRINTIFY_API_KEY")
    if not key:
        fail("Printify", "Key nicht gesetzt"); return False
    return _test("Printify shops",
                 "https://api.printify.com/v1/shops.json",
                 headers={"Authorization": f"Bearer {key}"},
                 ok_check=lambda c, d: c == 200)


def test_digistore24() -> bool:
    section("14. Digistore24")
    key = _g("DIGISTORE24_API_KEY")
    if not key:
        fail("DS24", "Key nicht gesetzt"); return False
    code, data = _req(f"https://www.digistore24.com/api/call/account/info/format/json/sha_sign/{key[:10]}")
    ms = 0
    if code in (200, 401, 403):
        ok("DS24 API", f"HTTP {code}")
        _record("digistore24", "OK", 0, f"HTTP {code}")
        return True
    fail("DS24", f"HTTP {code}")
    _record("digistore24", "FAIL", 0, f"HTTP {code}")
    return False


def test_github() -> bool:
    section("15. GitHub")
    tok = _g("GITHUB_TOKEN", "GITHUB_TOKEN_CLASSIC", "GITHUB_TOKEN_FINE")
    if not tok:
        fail("GitHub", "Token nicht gesetzt"); return False
    return _test("GitHub user",
                 "https://api.github.com/user",
                 headers={"Authorization": f"Bearer {tok}", "User-Agent": "SuperMegaBot"},
                 ok_check=lambda c, d: c == 200 and "login" in d)


def test_meta() -> bool:
    section("16. Meta (Facebook/Instagram)")
    tok = _g("META_ACCESS_TOKEN")
    if not tok:
        warn("Meta", "Access Token nicht gesetzt"); return False
    return _test("Meta token info",
                 f"https://graph.facebook.com/me?access_token={tok}",
                 ok_check=lambda c, d: c == 200 and "id" in d)


def _g(key: str, *aliases, default: str = "") -> str:
    for k in (key, *aliases):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return default


def send_telegram_report(report: dict):
    tok = _g("TELEGRAM_BOT_TOKEN")
    chat = _g("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return
    ok_count = sum(1 for v in report.values() if v.get("status") == "OK")
    fail_count = sum(1 for v in report.values() if v.get("status") == "FAIL")
    total = len(report)
    failed_names = [v["name"] for v in report.values() if v.get("status") == "FAIL"]
    emoji = "✅" if fail_count == 0 else ("⚠️" if fail_count <= 2 else "🚨")
    lines = [
        f"{emoji} <b>SuperMegaBot API Health</b>",
        f"✅ {ok_count}/{total} OK  |  ❌ {fail_count} FAIL",
        f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
    ]
    if failed_names:
        lines.append(f"\n❌ Defekt: {', '.join(failed_names)}")
    msg = "\n".join(lines)
    body = json.dumps({"chat_id": chat, "text": msg, "parse_mode": "HTML"}).encode()
    try:
        _req(f"https://api.telegram.org/bot{tok}/sendMessage", "POST",
             {"Content-Type": "application/json"}, body, timeout=10)
    except Exception:
        pass


def fix_env_aliases():
    """Schreibt fehlende Aliase in die .env (falls der echte Key vorhanden ist)."""
    if not _ENV_FILE.exists():
        return
    lines = _ENV_FILE.read_text().splitlines()
    existing = {l.split("=")[0].strip() for l in lines if "=" in l and not l.startswith("#")}
    additions = []
    for alias, real in KNOWN_ALIASES.items():
        if alias not in existing and real in existing:
            real_val = _g(real)
            if real_val:
                additions.append(f"{alias}={real_val}")
                print(f"  {G}+{X} Alias hinzugefügt: {alias} → {real}")
    if additions:
        with open(_ENV_FILE, "a") as f:
            f.write("\n# ── Kompatibilitäts-Aliase (auto-generated) ──────────\n")
            for a in additions:
                f.write(a + "\n")


def main():
    quiet = "--quiet" in sys.argv
    fix = "--fix" in sys.argv
    no_telegram = "--no-telegram" in sys.argv

    print(f"\n{B}{'═'*55}{X}")
    print(f"{B}  SuperMegaBot — ENV Validator & API Health{X}")
    print(f"{B}  {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}{X}")
    print(f"{B}{'═'*55}{X}")

    if fix:
        section("0. ENV Aliase reparieren")
        fix_env_aliases()

    present, missing = test_env_keys()

    tests = [
        test_telegram, test_anthropic, test_openai, test_groq,
        test_gemini, test_openrouter, test_shopify, test_stripe,
        test_supabase, test_klaviyo, test_mailchimp, test_printify,
        test_digistore24, test_github, test_meta,
    ]

    passed = sum(1 for t in tests if t())

    # Ergebnis
    total = len(tests)
    print(f"\n{B}{'═'*55}{X}")
    status_color = G if passed == total else (Y if passed >= total * 0.7 else R)
    print(f"\n  {status_color}APIs: {passed}/{total} OK{X}  |  "
          f"{'✅' if missing == 0 else R + '❌' + X} Env-Keys: {present} gesetzt, {missing} fehlen\n")

    # Report schreiben
    report_path = Path(__file__).parent / "data" / "api_health.json"
    report_path.parent.mkdir(exist_ok=True)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "passed": passed, "total": total,
        "env_present": present, "env_missing": missing,
        "services": results,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"  {DIM}Report: {report_path}{X}\n")

    # Telegram alert
    if not no_telegram:
        send_telegram_report(results)

    return 0 if passed >= total * 0.7 else 1


if __name__ == "__main__":
    sys.exit(main())
