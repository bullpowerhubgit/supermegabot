#!/usr/bin/env python3
"""
Live Connection Test — SuperMegaBot
Liest alle Credentials aus .env / Umgebungsvariablen.
Gibt NIEMALS Secrets oder Token-Werte aus.
"""
import os
import sys
import json
import time
import traceback
from pathlib import Path

# ── .env laden ────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=True)
except ImportError:
    pass  # python-dotenv optional — export vars manually if needed

try:
    import requests
except ImportError:
    print("FEHLER: 'requests' nicht installiert. Führe aus: pip install requests")
    sys.exit(1)

RESULTS = {}
TIMEOUT = 10

def _mask(value: str) -> str:
    """Zeigt nur die ersten 4 Zeichen, rest maskiert."""
    if not value or len(value) < 5:
        return "***"
    return value[:4] + "***" + value[-2:]

def _env(key: str):
    return os.environ.get(key)

def _check_env(*keys) -> tuple[bool, list[str]]:
    missing = [k for k in keys if not _env(k)]
    return len(missing) == 0, missing

def section(title: str):
    print(f"\n{'═'*55}")
    print(f"  {title}")
    print('═'*55)

def ok(msg): print(f"  ✅ {msg}")
def fail(msg): print(f"  ❌ {msg}")
def warn(msg): print(f"  ⚠️  {msg}")
def info(msg): print(f"  ℹ️  {msg}")

# ══════════════════════════════════════════════════════════
# 1. SHOPIFY
# ══════════════════════════════════════════════════════════
def test_shopify():
    section("SHOPIFY")
    required = ["SHOPIFY_STORE_URL", "SHOPIFY_ACCESS_TOKEN"]
    ready, missing = _check_env(*required)
    if not ready:
        fail(f"Fehlende Variablen: {missing}")
        RESULTS["shopify"] = {"status": "SKIP", "missing": missing}
        return

    store_url = _env("SHOPIFY_STORE_URL").rstrip("/")
    token = _env("SHOPIFY_ACCESS_TOKEN")
    info(f"Store: {store_url}")
    info(f"Token: {_mask(token)}")

    try:
        url = f"{store_url}/admin/api/2024-01/shop.json"
        r = requests.get(url, headers={"X-Shopify-Access-Token": token}, timeout=TIMEOUT)
        if r.status_code == 200:
            shop = r.json().get("shop", {})
            ok(f"Verbunden — Shop: {shop.get('name')} | Domain: {shop.get('domain')}")
            ok(f"Plan: {shop.get('plan_name')} | Currency: {shop.get('currency')}")
            RESULTS["shopify"] = {"status": "OK", "shop": shop.get("name")}
        elif r.status_code == 401:
            fail("401 Unauthorized — Token ungültig oder abgelaufen")
            RESULTS["shopify"] = {"status": "FAIL", "error": "401"}
        elif r.status_code == 403:
            fail("403 Forbidden — Token hat nicht die nötigen Scopes")
            info("Benötigte Scopes: read_orders, write_products, read_customers")
            RESULTS["shopify"] = {"status": "FAIL", "error": "403"}
        else:
            fail(f"HTTP {r.status_code}")
            RESULTS["shopify"] = {"status": "FAIL", "error": str(r.status_code)}
    except requests.exceptions.ConnectionError:
        fail("Verbindung fehlgeschlagen — Store-URL prüfen")
        RESULTS["shopify"] = {"status": "FAIL", "error": "connection_error"}
    except Exception as e:
        fail(f"Unerwarteter Fehler: {type(e).__name__}")
        RESULTS["shopify"] = {"status": "FAIL", "error": type(e).__name__}

# ══════════════════════════════════════════════════════════
# 2. STRIPE
# ══════════════════════════════════════════════════════════
def test_stripe():
    section("STRIPE")
    ready, missing = _check_env("STRIPE_SECRET_KEY")
    if not ready:
        fail(f"Fehlende Variablen: {missing}")
        RESULTS["stripe"] = {"status": "SKIP", "missing": missing}
        return

    key = _env("STRIPE_SECRET_KEY")
    info(f"Key: {_mask(key)} | Typ: {'TEST' if key.startswith('sk_test') else 'LIVE'}")

    if key.startswith("sk_test"):
        warn("TEST-Modus aktiv — kein echter Geldfluss möglich")

    try:
        r = requests.get(
            "https://api.stripe.com/v1/balance",
            auth=(key, ""),
            timeout=TIMEOUT
        )
        if r.status_code == 200:
            data = r.json()
            available = data.get("available", [])
            for bal in available:
                amount = bal["amount"] / 100
                ok(f"Balance {bal['currency'].upper()}: {amount:.2f}")
            RESULTS["stripe"] = {"status": "OK", "balance_count": len(available)}
        elif r.status_code == 401:
            fail("401 — Stripe Key ungültig")
            RESULTS["stripe"] = {"status": "FAIL", "error": "401"}
        else:
            fail(f"HTTP {r.status_code}")
            RESULTS["stripe"] = {"status": "FAIL", "error": str(r.status_code)}
    except Exception as e:
        fail(f"Fehler: {type(e).__name__}")
        RESULTS["stripe"] = {"status": "FAIL", "error": type(e).__name__}

# ══════════════════════════════════════════════════════════
# 3. TELEGRAM BOT
# ══════════════════════════════════════════════════════════
def test_telegram():
    section("TELEGRAM BOT")
    ready, missing = _check_env("TELEGRAM_BOT_TOKEN")
    if not ready:
        fail(f"Fehlende Variablen: {missing}")
        RESULTS["telegram"] = {"status": "SKIP", "missing": missing}
        return

    token = _env("TELEGRAM_BOT_TOKEN")
    info(f"Token: {_mask(token)}")

    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=TIMEOUT
        )
        data = r.json()
        if data.get("ok"):
            bot = data["result"]
            ok(f"Bot aktiv: @{bot.get('username')} | Name: {bot.get('first_name')}")
            ok(f"Can join groups: {bot.get('can_join_groups')} | Inline: {bot.get('supports_inline_queries')}")
            RESULTS["telegram"] = {"status": "OK", "username": bot.get("username")}

            # Webhook-Status prüfen
            wh = requests.get(
                f"https://api.telegram.org/bot{token}/getWebhookInfo",
                timeout=TIMEOUT
            ).json()
            wh_url = wh.get("result", {}).get("url", "")
            if wh_url:
                # Nie die volle URL ausgeben — könnte Token-Fragment enthalten
                info("Webhook gesetzt: [URL vorhanden, nicht angezeigt]")
            else:
                warn("Kein Webhook gesetzt — Bot läuft im Polling-Modus")
        else:
            fail(f"API Fehler: {data.get('description')}")
            RESULTS["telegram"] = {"status": "FAIL", "error": data.get("description")}
    except Exception as e:
        fail(f"Fehler: {type(e).__name__}")
        RESULTS["telegram"] = {"status": "FAIL", "error": type(e).__name__}

# ══════════════════════════════════════════════════════════
# 4. SUPABASE
# ══════════════════════════════════════════════════════════
def test_supabase():
    section("SUPABASE")
    required = ["SUPABASE_URL", "SUPABASE_KEY"]
    # Auch SUPABASE_ANON_KEY akzeptieren
    if not _env("SUPABASE_KEY") and _env("SUPABASE_ANON_KEY"):
        os.environ["SUPABASE_KEY"] = _env("SUPABASE_ANON_KEY")
    if not _env("SUPABASE_KEY") and _env("NEXT_PUBLIC_SUPABASE_ANON_KEY"):
        os.environ["SUPABASE_KEY"] = _env("NEXT_PUBLIC_SUPABASE_ANON_KEY")

    ready, missing = _check_env(*required)
    if not ready:
        fail(f"Fehlende Variablen: {missing}")
        info("Akzeptiert auch: SUPABASE_ANON_KEY oder NEXT_PUBLIC_SUPABASE_ANON_KEY")
        RESULTS["supabase"] = {"status": "SKIP", "missing": missing}
        return

    url = _env("SUPABASE_URL").rstrip("/")
    key = _env("SUPABASE_KEY")
    info(f"URL: {url}")
    info(f"Key: {_mask(key)}")

    try:
        # REST Health-Check
        r = requests.get(
            f"{url}/rest/v1/",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=TIMEOUT
        )
        if r.status_code in (200, 404):  # 404 = no table, but auth works
            ok("REST API erreichbar")
            RESULTS["supabase"] = {"status": "OK"}

            # Auth Health
            auth_r = requests.get(
                f"{url}/auth/v1/settings",
                headers={"apikey": key},
                timeout=TIMEOUT
            )
            if auth_r.status_code == 200:
                ok("Auth API erreichbar")
            else:
                warn(f"Auth API: HTTP {auth_r.status_code}")
        elif r.status_code == 401:
            fail("401 — Supabase Key ungültig")
            RESULTS["supabase"] = {"status": "FAIL", "error": "401"}
        else:
            fail(f"HTTP {r.status_code}")
            RESULTS["supabase"] = {"status": "FAIL", "error": str(r.status_code)}
    except Exception as e:
        fail(f"Fehler: {type(e).__name__}")
        RESULTS["supabase"] = {"status": "FAIL", "error": type(e).__name__}

# ══════════════════════════════════════════════════════════
# 5. ANTHROPIC API
# ══════════════════════════════════════════════════════════
def test_anthropic():
    section("ANTHROPIC API")
    ready, missing = _check_env("ANTHROPIC_API_KEY")
    if not ready:
        fail(f"Fehlende Variablen: {missing}")
        RESULTS["anthropic"] = {"status": "SKIP", "missing": missing}
        return

    key = _env("ANTHROPIC_API_KEY")
    model = _env("ANTHROPIC_MODEL") or "claude-sonnet-4-20250514"
    info(f"Key: {_mask(key)}")
    info(f"Model: {model}")

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model=model,
            max_tokens=5,
            messages=[{"role": "user", "content": "hi"}]
        )
        ok(f"Anthropic API OK - Modell: {model}")
        RESULTS["anthropic"] = {"status": "OK", "model": model}
    except ImportError:
        fail("'anthropic' Python-Paket nicht installiert")
        info("Installieren mit: pip install anthropic")
        RESULTS["anthropic"] = {"status": "FAIL", "error": "anthropic_not_installed"}
    except anthropic.NotFoundError:
        fail(f"404 - Modell '{model}' nicht gefunden (deprecated)")
        info("Aktuelles Modell in .env setzen: ANTHROPIC_MODEL=...")
        RESULTS["anthropic"] = {"status": "FAIL", "error": "model_not_found"}
    except anthropic.AuthenticationError:
        fail("401 - API Key ungültig")
        RESULTS["anthropic"] = {"status": "FAIL", "error": "401"}
    except Exception as e:
        fail(f"Fehler: {type(e).__name__}")
        RESULTS["anthropic"] = {"status": "FAIL", "error": type(e).__name__}

# ══════════════════════════════════════════════════════════
# 6. GUARDIAN API (lokal)
# ══════════════════════════════════════════════════════════
def test_guardian():
    section("GUARDIAN API (lokal)")
    guardian_url = _env("GUARDIAN_URL") or "http://localhost:3201"
    info(f"URL: {guardian_url}")

    try:
        r = requests.get(f"{guardian_url}/api/v1/health", timeout=5)
        if r.status_code == 200:
            ok("Guardian läuft")
            RESULTS["guardian"] = {"status": "OK"}
        else:
            warn(f"HTTP {r.status_code} — Guardian läuft, aber Health-Check fehlgeschlagen")
            RESULTS["guardian"] = {"status": "WARN", "code": r.status_code}
    except requests.exceptions.ConnectionError:
        warn("Nicht erreichbar — Guardian läuft nicht (Port 3201)")
        info("Starten mit: pm2 start ecosystem.config.js --only guardian")
        RESULTS["guardian"] = {"status": "OFFLINE"}
    except Exception as e:
        fail(f"Fehler: {type(e).__name__}")
        RESULTS["guardian"] = {"status": "FAIL", "error": type(e).__name__}

# ══════════════════════════════════════════════════════════
# 6. DASHBOARD (lokal)
# ══════════════════════════════════════════════════════════
def test_dashboard():
    section("DASHBOARD (lokal)")
    dash_url = "http://localhost:8888"
    info(f"URL: {dash_url}")

    try:
        r = requests.get(f"{dash_url}/api/health", timeout=5)
        if r.status_code == 200:
            ok(f"Dashboard läuft: {r.json()}")
            RESULTS["dashboard"] = {"status": "OK"}
        else:
            warn(f"HTTP {r.status_code}")
            RESULTS["dashboard"] = {"status": "WARN"}
    except requests.exceptions.ConnectionError:
        warn("Nicht erreichbar — Dashboard läuft nicht (Port 8888)")
        info("Starten mit: python3 dashboard/server.py")
        RESULTS["dashboard"] = {"status": "OFFLINE"}
    except Exception as e:
        fail(f"Fehler: {type(e).__name__}")
        RESULTS["dashboard"] = {"status": "FAIL", "error": type(e).__name__}

# ══════════════════════════════════════════════════════════
# ZUSAMMENFASSUNG
# ══════════════════════════════════════════════════════════
def summary():
    section("ZUSAMMENFASSUNG")
    status_icons = {"OK": "✅", "FAIL": "❌", "SKIP": "⏭️ ", "WARN": "⚠️ ", "OFFLINE": "🔴"}
    for service, result in RESULTS.items():
        icon = status_icons.get(result["status"], "❓")
        extra = ""
        if result["status"] == "SKIP":
            extra = f" → fehlende Vars: {result.get('missing', [])}"
        elif result["status"] == "FAIL":
            extra = f" → {result.get('error', '')}"
        elif result["status"] == "OK" and "shop" in result:
            extra = f" → {result['shop']}"
        elif result["status"] == "OK" and "username" in result:
            extra = f" → @{result['username']}"
        elif result["status"] == "OK" and "model" in result:
            extra = f" → {result['model']}"
        print(f"  {icon} {service.upper():<15} {result['status']}{extra}")

    failed = [k for k, v in RESULTS.items() if v["status"] == "FAIL"]
    skipped = [k for k, v in RESULTS.items() if v["status"] == "SKIP"]

    print()
    if failed:
        print(f"  ❌ Fehlgeschlagen: {failed}")
        print("  → Diese Logs bitte zurücksenden.")
    if skipped:
        print(f"  ⏭️  Übersprungen (Keys fehlen): {skipped}")
    if not failed and not skipped:
        print("  🎉 Alle Tests bestanden — System produktionsbereit!")

    # JSON-Output für Rücksendung
    print(f"\n{'─'*55}")
    print("  KOPIERE DIESEN BLOCK UND SENDE IHN ZURÜCK:")
    print('─'*55)
    safe_results = {k: v for k, v in RESULTS.items()}
    print(json.dumps(safe_results, indent=2))


if __name__ == "__main__":
    print("\n🔍 SuperMegaBot — Live Connection Test")
    print(f"   {time.strftime('%Y-%m-%d %H:%M:%S')}")

    test_shopify()
    test_stripe()
    test_telegram()
    test_supabase()
    test_anthropic()
    test_guardian()
    test_dashboard()
    summary()
