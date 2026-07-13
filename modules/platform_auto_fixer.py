#!/usr/bin/env python3
"""
Platform Auto-Fixer — prüft und korrigiert automatisch alle Plattform-Einstellungen.
Läuft als Scheduler-Task alle 12h oder on-demand via /api/platform/fix
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')
log = logging.getLogger("PlatformAutoFixer")

STATE = Path(__file__).parent.parent / 'data' / 'platform_fix_state.json'

# ── Credentials ──────────────────────────────────────────────────────────────
FB_TOKEN    = os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC") or os.getenv("META_ACCESS_TOKEN", "")
FB_PAGE_ID  = os.getenv("FACEBOOK_PAGE_ID", "1016738738178786")
IG_ID       = os.getenv("INSTAGRAM_ACCOUNT_ID", "17841478315197796")
SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
SHOP_TOKEN  = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOP_VER    = os.getenv("SHOPIFY_API_VERSION", "2026-04")
STRIPE_KEY  = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WH   = os.getenv("STRIPE_WEBHOOK_SECRET", "")
TG_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT     = os.getenv("TELEGRAM_CHAT_ID", "")
KLAVIYO_KEY = os.getenv("KLAVIYO_API_KEY_AIITEC") or os.getenv("KLAVIYO_API_KEY", "")
SUPA_URL    = os.getenv("SUPABASE_URL", "")
SUPA_KEY    = os.getenv("SUPABASE_ANON_KEY", "")
RAILWAY_URL = "https://supermegabot-production.up.railway.app"

_FIX_LOG: list[dict] = []


def _log_fix(platform: str, check: str, status: str, action: str = "", detail: str = ""):
    entry = {
        "platform": platform, "check": check, "status": status,
        "action": action, "detail": detail[:200], "ts": datetime.now().isoformat()
    }
    _FIX_LOG.append(entry)
    icon = "✅" if status == "ok" else ("🔧" if status == "fixed" else "❌")
    log.info("%s [%s] %s: %s", icon, platform, check, action or detail)


# ── Shopify Checks ───────────────────────────────────────────────────────────
async def check_shopify(s: aiohttp.ClientSession) -> list[dict]:
    results = []
    base = f"https://{SHOP_DOMAIN}/admin/api/{SHOP_VER}"
    hdrs = {"X-Shopify-Access-Token": SHOP_TOKEN, "Content-Type": "application/json"}

    # 1. Shop erreichbar
    try:
        async with s.get(f"{base}/shop.json", headers=hdrs, timeout=aiohttp.ClientTimeout(total=10)) as r:
            d = await r.json()
        if "shop" in d:
            _log_fix("Shopify", "shop_access", "ok", "API erreichbar")
            shop_name = d["shop"].get("name", "?")
            results.append({"check": "shop_access", "ok": True, "detail": shop_name})
        else:
            _log_fix("Shopify", "shop_access", "error", detail=str(d)[:100])
            results.append({"check": "shop_access", "ok": False})
    except Exception as e:
        _log_fix("Shopify", "shop_access", "error", detail=str(e))
        results.append({"check": "shop_access", "ok": False})

    # 2. Aktive Produkte zählen
    try:
        async with s.get(f"{base}/products/count.json?status=active", headers=hdrs,
                         timeout=aiohttp.ClientTimeout(total=10)) as r:
            d = await r.json()
        count = d.get("count", 0)
        ok = count > 0
        _log_fix("Shopify", "active_products", "ok" if ok else "warn",
                 detail=f"{count} aktive Produkte")
        results.append({"check": "active_products", "ok": ok, "count": count})
    except Exception as e:
        results.append({"check": "active_products", "ok": False, "error": str(e)})

    # 3. Webhooks prüfen (Stripe-Checkout)
    try:
        async with s.get(f"{base}/webhooks.json", headers=hdrs,
                         timeout=aiohttp.ClientTimeout(total=10)) as r:
            d = await r.json()
        hooks = d.get("webhooks", [])
        topics = [h["topic"] for h in hooks]
        required = ["orders/create", "orders/paid", "app/uninstalled"]
        missing = [t for t in required if t not in topics]
        if missing:
            # Auto-fix: fehlende Webhooks registrieren
            for topic in missing:
                payload = {"webhook": {
                    "topic": topic,
                    "address": f"{RAILWAY_URL}/webhooks/shopify",
                    "format": "json"
                }}
                async with s.post(f"{base}/webhooks.json", json=payload, headers=hdrs,
                                  timeout=aiohttp.ClientTimeout(total=10)) as rr:
                    if rr.status in (200, 201):
                        _log_fix("Shopify", "webhook", "fixed", f"Webhook registriert: {topic}")
                    else:
                        _log_fix("Shopify", "webhook", "error", f"Konnte {topic} nicht registrieren")
        else:
            _log_fix("Shopify", "webhooks", "ok", f"{len(hooks)} Webhooks OK")
        results.append({"check": "webhooks", "ok": True, "count": len(hooks), "missing_fixed": missing})
    except Exception as e:
        results.append({"check": "webhooks", "ok": False, "error": str(e)})

    return results


# ── Stripe Checks ─────────────────────────────────────────────────────────────
async def check_stripe(s: aiohttp.ClientSession) -> list[dict]:
    results = []
    if not STRIPE_KEY:
        return [{"check": "stripe_key", "ok": False, "error": "kein Key"}]

    # 1. Balance abrufen
    try:
        async with s.get("https://api.stripe.com/v1/balance",
                         headers={"Authorization": f"Bearer {STRIPE_KEY}"},
                         timeout=aiohttp.ClientTimeout(total=10)) as r:
            d = await r.json()
        if "available" in d:
            eur = next((x["amount"] for x in d["available"] if x["currency"] == "eur"), 0)
            _log_fix("Stripe", "balance", "ok", f"Balance: €{eur/100:.2f}")
            results.append({"check": "balance", "ok": True, "eur_cents": eur})
        else:
            _log_fix("Stripe", "balance", "error", detail=str(d)[:80])
            results.append({"check": "balance", "ok": False})
    except Exception as e:
        results.append({"check": "balance", "ok": False, "error": str(e)})

    # 2. Webhook-Endpoints prüfen
    try:
        async with s.get("https://api.stripe.com/v1/webhook_endpoints?limit=10",
                         headers={"Authorization": f"Bearer {STRIPE_KEY}"},
                         timeout=aiohttp.ClientTimeout(total=10)) as r:
            d = await r.json()
        endpoints = d.get("data", [])
        railway_hook = next((e for e in endpoints if RAILWAY_URL in e.get("url", "")), None)
        if not railway_hook:
            # Auto-fix: Webhook erstellen
            payload = {
                "url": f"{RAILWAY_URL}/webhooks/stripe",
                "enabled_events[]": [
                    "checkout.session.completed",
                    "customer.subscription.created",
                    "payment_intent.succeeded",
                    "invoice.payment_succeeded",
                ]
            }
            async with s.post("https://api.stripe.com/v1/webhook_endpoints",
                              data=payload,
                              headers={"Authorization": f"Bearer {STRIPE_KEY}"},
                              timeout=aiohttp.ClientTimeout(total=10)) as rr:
                rd = await rr.json()
                if "id" in rd:
                    _log_fix("Stripe", "webhook", "fixed",
                             f"Webhook erstellt: {rd['id']} → Secret: {rd.get('secret','?')[:20]}")
                    results.append({"check": "webhook", "ok": True, "fixed": True, "id": rd["id"]})
                else:
                    _log_fix("Stripe", "webhook", "error", detail=str(rd)[:80])
                    results.append({"check": "webhook", "ok": False})
        else:
            status = railway_hook.get("status", "?")
            _log_fix("Stripe", "webhook", "ok", f"Webhook aktiv: {status}")
            results.append({"check": "webhook", "ok": True, "status": status})
    except Exception as e:
        results.append({"check": "webhook", "ok": False, "error": str(e)})

    return results


# ── Meta/Facebook Checks ─────────────────────────────────────────────────────
async def check_meta(s: aiohttp.ClientSession) -> list[dict]:
    results = []
    if not FB_TOKEN:
        return [{"check": "fb_token", "ok": False, "error": "kein Token"}]
    graph = "https://graph.facebook.com/v19.0"

    # 1. Page-Token gültig
    try:
        async with s.get(f"{graph}/{FB_PAGE_ID}",
                         params={"fields": "name,fan_count,access_token", "access_token": FB_TOKEN},
                         timeout=aiohttp.ClientTimeout(total=10)) as r:
            d = await r.json()
        if "name" in d:
            _log_fix("Meta", "page_token", "ok", f"{d['name']} — {d.get('fan_count',0)} Fans")
            results.append({"check": "page_token", "ok": True, "fans": d.get("fan_count", 0)})
        else:
            _log_fix("Meta", "page_token", "error", detail=d.get("error", {}).get("message", "?")[:80])
            results.append({"check": "page_token", "ok": False})
    except Exception as e:
        results.append({"check": "page_token", "ok": False, "error": str(e)})

    # 2. Instagram Account
    try:
        async with s.get(f"{graph}/{IG_ID}",
                         params={"fields": "username,followers_count,media_count", "access_token": FB_TOKEN},
                         timeout=aiohttp.ClientTimeout(total=10)) as r:
            d = await r.json()
        if "username" in d:
            _log_fix("Meta", "instagram", "ok",
                     f"@{d['username']} — {d.get('followers_count',0)} Follower, {d.get('media_count',0)} Posts")
            results.append({"check": "instagram", "ok": True,
                            "followers": d.get("followers_count", 0), "posts": d.get("media_count", 0)})
        else:
            _log_fix("Meta", "instagram", "error", detail=str(d)[:80])
            results.append({"check": "instagram", "ok": False})
    except Exception as e:
        results.append({"check": "instagram", "ok": False, "error": str(e)})

    # 3. Pixel prüfen (nur ob konfiguriert)
    pixel_id = os.getenv("FACEBOOK_PIXEL_ID", "")
    if pixel_id:
        _log_fix("Meta", "pixel", "ok", f"Pixel {pixel_id} konfiguriert")
        results.append({"check": "pixel", "ok": True, "pixel_id": pixel_id})

    return results


# ── Telegram Check ────────────────────────────────────────────────────────────
async def check_telegram(s: aiohttp.ClientSession) -> list[dict]:
    results = []
    if not TG_TOKEN:
        return [{"check": "bot_token", "ok": False, "error": "kein Token"}]
    try:
        async with s.get(f"https://api.telegram.org/bot{TG_TOKEN}/getMe",
                         timeout=aiohttp.ClientTimeout(total=10)) as r:
            d = await r.json()
        if d.get("ok") and "result" in d:
            bot = d["result"]
            _log_fix("Telegram", "bot", "ok", f"@{bot['username']} — {bot.get('first_name','?')}")
            results.append({"check": "bot", "ok": True, "username": bot["username"]})
        else:
            _log_fix("Telegram", "bot", "error", detail=str(d)[:80])
            results.append({"check": "bot", "ok": False})
    except Exception as e:
        results.append({"check": "bot", "ok": False, "error": str(e)})
    return results


# ── Supabase Check ────────────────────────────────────────────────────────────
async def check_supabase(s: aiohttp.ClientSession) -> list[dict]:
    results = []
    if not SUPA_URL or not SUPA_KEY:
        return [{"check": "supabase", "ok": False, "error": "URL oder Key fehlt"}]
    try:
        svc_key = os.getenv("SUPABASE_SERVICE_KEY", SUPA_KEY)
        async with s.get(f"{SUPA_URL}/rest/v1/scraped_products?limit=1",
                         headers={"apikey": svc_key, "Authorization": f"Bearer {svc_key}"},
                         timeout=aiohttp.ClientTimeout(total=10)) as r:
            ok = r.status in (200, 206)
            body = await r.text()
            _log_fix("Supabase", "rest_api", "ok" if ok else "error",
                     f"HTTP {r.status}" + ("" if ok else f": {body[:60]}"))
            results.append({"check": "rest_api", "ok": ok, "status": r.status})
    except Exception as e:
        results.append({"check": "rest_api", "ok": False, "error": str(e)})
    return results


# ── Railway Health ────────────────────────────────────────────────────────────
async def check_railway(s: aiohttp.ClientSession) -> list[dict]:
    results = []
    try:
        async with s.get(f"{RAILWAY_URL}/health", timeout=aiohttp.ClientTimeout(total=15)) as r:
            d = await r.json()
            ok = d.get("status") == "ok"
            _log_fix("Railway", "health", "ok" if ok else "error", f"HTTP {r.status}: {d}")
            results.append({"check": "health", "ok": ok, "response": d})
    except Exception as e:
        _log_fix("Railway", "health", "error", detail=str(e))
        results.append({"check": "health", "ok": False, "error": str(e)})
    return results


# ── Email / Klaviyo Check ──────────────────────────────────────────────────────
async def check_klaviyo(s: aiohttp.ClientSession) -> list[dict]:
    results = []
    if not KLAVIYO_KEY:
        return [{"check": "klaviyo", "ok": False, "error": "kein Key"}]
    try:
        async with s.get("https://a.klaviyo.com/api/accounts/",
                         headers={"Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
                                  "revision": "2024-02-15"},
                         timeout=aiohttp.ClientTimeout(total=10)) as r:
            d = await r.json()
            ok = r.status == 200 and "data" in d
            _log_fix("Klaviyo", "api_key", "ok" if ok else "error",
                     f"HTTP {r.status}" if not ok else "API OK")
            results.append({"check": "api_key", "ok": ok, "status": r.status})
    except Exception as e:
        results.append({"check": "api_key", "ok": False, "error": str(e)})
    return results


# ── Telegram Report ───────────────────────────────────────────────────────────
async def _send_tg(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


def _save_state(data: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, indent=2, default=str))


# ── Main: run_all_fixes ───────────────────────────────────────────────────────
async def run_all_fixes() -> dict:
    """Vollständiger Platform-Check + Auto-Fix-Zyklus."""
    _FIX_LOG.clear()
    started = datetime.now().isoformat()
    all_results: dict[str, list] = {}

    async with aiohttp.ClientSession() as s:
        checks = await asyncio.gather(
            check_shopify(s),
            check_stripe(s),
            check_meta(s),
            check_telegram(s),
            check_supabase(s),
            check_railway(s),
            check_klaviyo(s),
            return_exceptions=True,
        )

    platforms = ["shopify", "stripe", "meta", "telegram", "supabase", "railway", "klaviyo"]
    for name, result in zip(platforms, checks):
        if isinstance(result, Exception):
            all_results[name] = [{"check": "exception", "ok": False, "error": str(result)}]
        else:
            all_results[name] = result

    # Summary
    total_checks = sum(len(v) for v in all_results.values())
    ok_checks = sum(1 for v in all_results.values() for c in v if c.get("ok"))
    failed = [(p, c) for p, v in all_results.items() for c in v if not c.get("ok")]

    summary = {
        "started": started,
        "completed": datetime.now().isoformat(),
        "total_checks": total_checks,
        "ok": ok_checks,
        "failed": len(failed),
        "platforms": all_results,
        "fix_log": _FIX_LOG,
    }
    _save_state(summary)

    # TG Report
    icon = "✅" if len(failed) == 0 else ("⚠️" if len(failed) < 3 else "🚨")
    msg = (f"{icon} *Platform-Check* — {ok_checks}/{total_checks} OK\n"
           f"Stand: {datetime.now().strftime('%H:%M %d.%m.%Y')}\n\n")
    for p, results_list in all_results.items():
        p_ok = all(c.get("ok") for c in results_list)
        msg += f"{'✅' if p_ok else '❌'} *{p.title()}*\n"
    if failed:
        msg += "\n🔴 Fehler:\n"
        for p, c in failed[:5]:
            msg += f"• {p}/{c['check']}: {c.get('error', c.get('detail', '?'))[:50]}\n"

    await _send_tg(msg)
    log.info("Platform-Check: %d/%d OK, %d Fehler", ok_checks, total_checks, len(failed))
    return summary


def get_status() -> Optional[dict]:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_all_fixes())
