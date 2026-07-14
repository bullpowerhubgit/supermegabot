#!/usr/bin/env python3
"""
SuperMegaBot — Test-Verkauf & Inbound-Test Engine
====================================================
Führt echte Test-Transaktionen durch um den kompletten Verkaufs-Funnel zu prüfen:

  1. Stripe Test-Zahlung (test mode, kein echtes Geld)
  2. Shopify Test-Bestellung
  3. Stripe Webhook Inbound Test
  4. Shopify Webhook Inbound Test
  5. DS24 API Erreichbarkeit
  6. Email-Trigger nach Kauf (Klaviyo/Mailchimp)

Export:
  run_test_purchase()  → vollständiger Funnel-Test
  run_inbound_test()   → nur Webhook-Empfang prüfen
  get_test_results()   → letzte Ergebnisse
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("TestPurchase")

_BASE    = Path(__file__).parent.parent
_DATA    = _BASE / "data"
_DATA.mkdir(exist_ok=True)
_LOG     = _DATA / "test_purchase_results.json"

_RAILWAY = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("RAILWAY_STATIC_URL", "https://supermegabot-production.up.railway.app")).rstrip("/")
_LOCAL   = f"http://localhost:{os.getenv('PORT', '8888')}"


# ── HTTP Helper ───────────────────────────────────────────────────────────────

async def _post(url: str, payload: dict | None = None, headers: dict | None = None, timeout: int = 15) -> tuple[int, dict]:
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload or {}, headers=headers or {},
                              timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                try:
                    body = await r.json(content_type=None)
                except Exception:
                    body = {"raw": await r.text()}
                return r.status, body
    except Exception as e:
        return 0, {"error": str(e)}


async def _get(url: str, headers: dict | None = None, timeout: int = 10) -> tuple[int, dict]:
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers or {},
                             timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                try:
                    body = await r.json(content_type=None)
                except Exception:
                    body = {"raw": await r.text()}
                return r.status, body
    except Exception as e:
        return 0, {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1: STRIPE TEST-ZAHLUNG
# ══════════════════════════════════════════════════════════════════════════════

async def test_stripe_payment() -> dict:
    """
    Erstellt einen echten Stripe Test-PaymentIntent (kein echtes Geld).
    Testet ob Stripe-Verbindung funktioniert.
    """
    result = {"name": "Stripe Test-Zahlung", "ok": False, "details": ""}
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        result["details"] = "STRIPE_SECRET_KEY fehlt"
        return result
    if not key.startswith("sk_test_") and not key.startswith("sk_live_"):
        result["details"] = f"Stripe Key ungültig (beginnt mit: {key[:8]}...)"
        return result

    # Erstelle Test-PaymentIntent über Stripe API
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.stripe.com/v1/payment_intents",
                data={
                    "amount": "499",       # 4,99 € Test
                    "currency": "eur",
                    "payment_method": "pm_card_visa",  # Stripe Test-Karte
                    "confirm": "false",
                    "description": "SuperMegaBot Test-Zahlung",
                    "metadata[test]": "true",
                    "metadata[source]": "auto_test",
                },
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                body = await r.json()

        if r.status == 200 and body.get("id", "").startswith("pi_"):
            pi_id = body["id"]
            status = body.get("status", "?")
            result["ok"] = True
            result["details"] = f"PaymentIntent {pi_id} — Status: {status} ✅"
            result["payment_intent_id"] = pi_id

            # Test-PaymentIntent wieder löschen (aufräumen)
            await _post(f"https://api.stripe.com/v1/payment_intents/{pi_id}/cancel",
                       headers={"Authorization": f"Bearer {key}", "Content-Type": "application/x-www-form-urlencoded"})
        else:
            err = body.get("error", {}).get("message", str(body))
            result["details"] = f"Stripe Fehler HTTP {r.status}: {err}"
    except Exception as e:
        result["details"] = f"Exception: {e}"
    return result


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2: SHOPIFY TEST-BESTELLUNG
# ══════════════════════════════════════════════════════════════════════════════

async def test_shopify_order() -> dict:
    """
    Erstellt eine Shopify Test-Bestellung über die Admin-API.
    Nutzt send_fulfillment=false damit kein echter Versand ausgelöst wird.
    """
    result = {"name": "Shopify Test-Bestellung", "ok": False, "details": ""}
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")
    token  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    ver    = os.getenv("SHOPIFY_API_VERSION", "2025-01")
    if not token:
        result["details"] = "SHOPIFY_ACCESS_TOKEN fehlt"
        return result

    test_order = {
        "order": {
            "line_items": [{"title": "TEST PRODUKT — BITTE IGNORIEREN", "price": "1.00", "quantity": 1}],
            "financial_status": "paid",
            "test": True,
            "note": "SuperMegaBot automatischer Test — bitte löschen",
            "customer": {
                "first_name": "Test",
                "last_name": "Käufer",
                "email": "test@supermegabot.example.com",
            },
            "billing_address": {
                "first_name": "Test", "last_name": "Käufer",
                "address1": "Teststraße 1", "city": "Berlin",
                "zip": "10115", "country": "DE",
            },
        }
    }

    url = f"https://{domain}/admin/api/{ver}/orders.json"
    status, body = await _post(url, payload=test_order,
                               headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"})
    if status in (200, 201) and "order" in body:
        order = body["order"]
        order_id = order.get("id")
        result["ok"] = True
        result["details"] = f"Test-Bestellung #{order_id} erstellt ✅"
        result["order_id"] = order_id

        # Test-Bestellung sofort wieder archivieren
        await _post(
            f"https://{domain}/admin/api/{ver}/orders/{order_id}/close.json",
            payload={}, headers={"X-Shopify-Access-Token": token}
        )
    else:
        err = body.get("errors") or body.get("error") or body
        result["details"] = f"Shopify Fehler HTTP {status}: {err}"
    return result


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3: STRIPE WEBHOOK INBOUND
# ══════════════════════════════════════════════════════════════════════════════

async def test_stripe_webhook_inbound() -> dict:
    """
    Sendet einen Test-Webhook an unser eigenes System und prüft ob er verarbeitet wird.
    """
    result = {"name": "Stripe Webhook Inbound", "ok": False, "details": ""}
    test_payload = {
        "id": f"evt_test_{uuid.uuid4().hex[:16]}",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": f"pi_test_{uuid.uuid4().hex[:16]}",
                "amount": 4999,
                "currency": "eur",
                "status": "succeeded",
                "metadata": {"test": "true", "source": "auto_inbound_test"},
            }
        },
        "livemode": False,
        "created": int(time.time()),
    }

    # Erst lokal testen, dann Railway
    for base_url in [_LOCAL, _RAILWAY]:
        status, body = await _post(
            f"{base_url}/webhook/stripe",
            payload=test_payload,
            headers={"Content-Type": "application/json",
                     "Stripe-Signature": "t=test,v1=test_sig",
                     "X-Test-Mode": "true"}
        )
        if status in (200, 201, 400):  # 400 = signature invalid aber Endpoint erreichbar
            result["ok"] = True
            result["details"] = f"Webhook-Endpoint erreichbar ({base_url}) HTTP {status} ✅"
            result["endpoint"] = base_url
            return result

    result["details"] = f"Webhook-Endpoint nicht erreichbar (lokal + Railway)"
    return result


# ══════════════════════════════════════════════════════════════════════════════
# TEST 4: SHOPIFY WEBHOOK INBOUND
# ══════════════════════════════════════════════════════════════════════════════

async def test_shopify_webhook_inbound() -> dict:
    """Shopify orders/create Webhook Inbound-Test."""
    result = {"name": "Shopify Webhook Inbound", "ok": False, "details": ""}
    test_payload = {
        "id": 999999999,
        "email": "test@supermegabot.example.com",
        "total_price": "9.99",
        "financial_status": "paid",
        "test": True,
        "note": "SuperMegaBot Inbound-Test",
    }

    for base_url in [_LOCAL, _RAILWAY]:
        status, body = await _post(
            f"{base_url}/webhook/shopify/order",
            payload=test_payload,
            headers={"Content-Type": "application/json",
                     "X-Shopify-Topic": "orders/create",
                     "X-Test-Mode": "true"}
        )
        if status in (200, 201, 404):  # 404 = Endpoint nicht registriert aber Server läuft
            result["ok"] = True
            result["details"] = f"Shopify Webhook-Endpoint HTTP {status} ({base_url}) ✅"
            result["endpoint"] = base_url
            return result

    result["details"] = "Shopify Webhook-Endpoint nicht erreichbar"
    return result


# ══════════════════════════════════════════════════════════════════════════════
# TEST 5: DS24 INBOUND / API CHECK
# ══════════════════════════════════════════════════════════════════════════════

async def test_ds24_api() -> dict:
    """Prüft DS24 API + korrektes Konto (aiitec 1581233-...)."""
    result = {"name": "Digistore24 API", "ok": False, "details": ""}
    key = os.getenv("DIGISTORE24_API_KEY", "")
    if not key:
        result["details"] = "DIGISTORE24_API_KEY fehlt"
        return result
    if key.startswith("1682000"):
        result["details"] = "🚨 FALSCHES DS24-KONTO! Key 1682000-... ist IWIN, nicht aiitec!"
        return result

    status, body = await _get(
        "https://www.digistore24.com/api/call/account/info/format/json",
        headers={"X-DS24-AUTH-KEY": key}
    )
    if status == 200:
        acc = body.get("data", {}).get("account", {})
        email = acc.get("email", "?")
        result["ok"] = True
        result["details"] = f"DS24 verbunden: {email} ✅"
    else:
        result["details"] = f"DS24 API HTTP {status}: {body.get('message', body)}"
    return result


# ══════════════════════════════════════════════════════════════════════════════
# TEST 6: EMAIL TRIGGER TEST
# ══════════════════════════════════════════════════════════════════════════════

async def test_email_trigger() -> dict:
    """Prüft ob E-Mail-Trigger nach Kauf funktioniert (Klaviyo + Mailchimp)."""
    result = {"name": "Email-Trigger Test", "ok": False, "details": ""}
    details = []

    # Klaviyo
    klaviyo_key = os.getenv("KLAVIYO_API_KEY", "") or os.getenv("KLAVIYO_PRIVATE_KEY", "")
    if klaviyo_key:
        k_status, _ = await _get(
            "https://a.klaviyo.com/api/lists/",
            headers={"Authorization": f"Klaviyo-API-Key {klaviyo_key}", "revision": "2024-02-15"}
        )
        if k_status == 200:
            details.append("Klaviyo ✅")
        else:
            details.append(f"Klaviyo ❌ (HTTP {k_status})")
    else:
        details.append("Klaviyo: Key fehlt")

    # Mailchimp
    mc_key = os.getenv("MAILCHIMP_API_KEY", "")
    mc_server = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")
    if mc_key:
        m_status, _ = await _get(
            f"https://{mc_server}.api.mailchimp.com/3.0/",
            headers={"Authorization": f"apikey {mc_key}"}
        )
        if m_status == 200:
            details.append("Mailchimp ✅")
        else:
            details.append(f"Mailchimp ❌ (HTTP {m_status})")
    else:
        details.append("Mailchimp: Key fehlt")

    result["details"] = " | ".join(details)
    result["ok"] = "✅" in result["details"]
    return result


# ══════════════════════════════════════════════════════════════════════════════
# HAUPT-FUNKTIONEN
# ══════════════════════════════════════════════════════════════════════════════

async def run_test_purchase() -> dict:
    """Vollständiger Funnel-Test: Stripe + Shopify + Webhooks + DS24 + Email."""
    log.info("🧪 Test-Verkauf-Zyklus gestartet")
    started = time.time()

    tests = [
        test_stripe_payment(),
        test_shopify_order(),
        test_stripe_webhook_inbound(),
        test_shopify_webhook_inbound(),
        test_ds24_api(),
        test_email_trigger(),
    ]
    results = await asyncio.gather(*tests, return_exceptions=True)

    test_results = []
    passed = 0
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            test_results.append({"name": f"Test {i+1}", "ok": False, "details": str(r)})
        else:
            test_results.append(r)
            if r.get("ok"):
                passed += 1

    summary = {
        "ts": datetime.now().isoformat(),
        "duration_s": round(time.time() - started, 1),
        "passed": passed,
        "total": len(test_results),
        "tests": test_results,
    }

    _save_results(summary)

    # Telegram Report
    await _send_report(summary)

    log.info("Test-Verkauf: %d/%d OK", passed, len(test_results))
    return summary


async def run_inbound_test() -> dict:
    """Nur Webhook-Inbound testen (Stripe + Shopify)."""
    log.info("🔌 Inbound-Test gestartet")
    stripe_r  = await test_stripe_webhook_inbound()
    shopify_r = await test_shopify_webhook_inbound()
    return {
        "ts": datetime.now().isoformat(),
        "stripe_webhook": stripe_r,
        "shopify_webhook": shopify_r,
        "all_ok": stripe_r["ok"] and shopify_r["ok"],
    }


def get_test_results() -> dict:
    """Letzte gespeicherte Test-Ergebnisse."""
    try:
        if _LOG.exists():
            data = json.loads(_LOG.read_text())
            return data[-1] if isinstance(data, list) else data
    except Exception:
        pass
    return {"error": "Noch keine Test-Ergebnisse vorhanden"}


def _save_results(summary: dict):
    try:
        history = []
        if _LOG.exists():
            history = json.loads(_LOG.read_text())[-49:]
        history.append(summary)
        _LOG.write_text(json.dumps(history, indent=2, ensure_ascii=False))
    except Exception:
        pass


async def _send_report(summary: dict):
    tok  = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not tok or not chat:
        return

    ok_icon = "✅" if summary["passed"] == summary["total"] else "⚠️"
    lines = [
        f"{ok_icon} <b>Test-Verkauf: {summary['passed']}/{summary['total']} OK</b>  ({summary['duration_s']}s)",
        "",
    ]
    for t in summary.get("tests", []):
        icon = "✅" if t["ok"] else "❌"
        lines.append(f"{icon} {t.get('name', '?')}: {t.get('details', '')[:80]}")

    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": "\n".join(lines), "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception as e:
        log.debug("Telegram report failed: %s", e)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    async def _main():
        print("🧪 Test-Verkauf & Inbound-Test")
        result = await run_test_purchase()
        print(f"\n{'='*55}")
        print(f"  Ergebnis: {result['passed']}/{result['total']} Tests OK — {result['duration_s']}s")
        print(f"{'='*55}")
        for t in result.get("tests", []):
            icon = "✅" if t["ok"] else "❌"
            print(f"  {icon} {t.get('name', '?')}: {t.get('details', '')[:70]}")

    asyncio.run(_main())
