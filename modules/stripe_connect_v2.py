#!/usr/bin/env python3
"""
Stripe Connect v2 — vollständige Integration
============================================
Implementiert alle drei Bereiche:

1. Accounts v2   — verbundene Konten anlegen, onboarden, verwalten
2. Event Destinations (v2 Thin Events) — Webhook-Targets registrieren
3. Checkout      — Checkout-Sessions für verbundene Konten erstellen

API-Besonderheiten v2:
- Content-Type: application/json (nicht form-encoded)
- Stripe-Version: 2026-06-24.preview Header erforderlich
- Paginierung via next_page_url / previous_page_url
- Thin Events (nur Objekt-ID, kein Snapshot)
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from typing import Any, Optional

log = logging.getLogger("StripeConnectV2")

_SK  = lambda: os.getenv("STRIPE_SECRET_KEY", "")
_WHS = lambda: os.getenv("STRIPE_WEBHOOK_SECRET", "")
_DOMAIN = lambda: os.getenv("RAILWAY_PUBLIC_DOMAIN", "supermegabot-production.up.railway.app")

_V2_VERSION = "2026-06-24.preview"
_V1_BASE    = "https://api.stripe.com/v1"
_V2_BASE    = "https://api.stripe.com/v2"


# ── HTTP Helpers ──────────────────────────────────────────────────────────────

def _headers_v1() -> dict:
    return {
        "Authorization": f"Bearer {_SK()}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _headers_v2() -> dict:
    return {
        "Authorization": f"Bearer {_SK()}",
        "Content-Type": "application/json",
        "Stripe-Version": _V2_VERSION,
    }


def _req(method: str, url: str, data=None, headers: dict = None, timeout: int = 20) -> dict:
    """Führt HTTP-Request durch, gibt JSON-Dict zurück."""
    if headers is None:
        headers = _headers_v1()
    body = None
    if data is not None:
        if headers.get("Content-Type") == "application/json":
            body = json.dumps(data).encode()
        else:
            body = urllib.parse.urlencode(data, doseq=True).encode()
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        log.error("Stripe %s %s → %d: %s", method, url, e.code, err)
        return {"error": err}


def _v2(method: str, path: str, data=None) -> dict:
    return _req(method, f"{_V2_BASE}/{path}", data, _headers_v2())


def _v1(method: str, path: str, data=None) -> dict:
    return _req(method, f"{_V1_BASE}/{path}", data, _headers_v1())


def _v1_for_account(method: str, path: str, account_id: str, data=None) -> dict:
    h = _headers_v1()
    h["Stripe-Account"] = account_id
    return _req(method, f"{_V1_BASE}/{path}", data, h)


# ── 1. ACCOUNTS V2 ───────────────────────────────────────────────────────────

def create_connected_account(
    email: str,
    display_name: str,
    country: str = "DE",
    entity_type: str = "company",
    currency: str = "eur",
) -> dict:
    """Erstellt ein verbundenes Konto mit der Accounts v2 API."""
    return _v2("POST", "core/accounts", {
        "contact_email": email,
        "display_name": display_name,
        "dashboard": "full",
        "identity": {
            "country": country.lower(),
            "entity_type": entity_type,
        },
        "configuration": {
            "merchant": {
                "capabilities": {
                    "card_payments": {"requested": True},
                }
            }
        },
        "defaults": {
            "currency": currency,
            "responsibilities": {
                "fees_collector": "stripe",
                "losses_collector": "stripe",
            },
            "locales": ["de-DE"],
        },
        "include": ["configuration.merchant", "identity", "requirements"],
    })


def get_account(account_id: str) -> dict:
    """Ruft ein verbundenes Konto ab (v2)."""
    return _v2("GET", f"core/accounts/{account_id}?include[]=requirements&include[]=configuration.merchant")


def list_accounts(limit: int = 20, page_token: str = None) -> dict:
    """Listet alle verbundenen Konten auf (v2 Paginierung)."""
    params = f"limit={limit}"
    if page_token:
        params += f"&page={page_token}"
    return _v2("GET", f"core/accounts?{params}")


def get_account_status(account_id: str) -> dict:
    """Gibt vereinfachten Status eines verbundenen Kontos zurück."""
    r = _v2("GET", f"core/accounts/{account_id}?include[]=requirements&include[]=configuration.merchant")
    if "error" in r:
        return r
    merchant = (r.get("configuration") or {}).get("merchant") or {}
    capabilities = merchant.get("capabilities") or {}
    card = capabilities.get("card_payments") or {}
    payouts = (capabilities.get("stripe_balance") or {}).get("payouts") or {}
    reqs = r.get("requirements") or {}
    return {
        "id": r.get("id"),
        "display_name": r.get("display_name"),
        "contact_email": r.get("contact_email"),
        "charges_enabled": card.get("status") == "active",
        "payouts_enabled": payouts.get("status") == "active",
        "details_submitted": (reqs.get("summary") or {}).get("minimum_deadline") is None,
        "requirements": reqs.get("entries", []),
    }


# ── 2. ONBOARDING (Account Links v2) ─────────────────────────────────────────

def create_onboarding_link(account_id: str) -> dict:
    """Erstellt Onboarding-Link für verbundenes Konto (v2)."""
    domain = _DOMAIN()
    return _v2("POST", "core/account_links", {
        "account": account_id,
        "use_case": {
            "type": "account_onboarding",
            "account_onboarding": {
                "configurations": ["merchant"],
                "refresh_url": f"https://{domain}/api/connect/refresh?account_id={account_id}",
                "return_url": f"https://{domain}/api/connect/return?account_id={account_id}",
            },
        },
    })


# ── 3. PRODUKTE FÜR VERBUNDENE KONTEN (v1 on behalf of) ─────────────────────

def create_product_for_account(
    account_id: str,
    name: str,
    description: str,
    price_cents: int,
    currency: str = "eur",
    recurring_interval: str = None,
) -> dict:
    """Erstellt Produkt + Preis im Namen eines verbundenen Kontos."""
    product = _v1_for_account("POST", "products", account_id, {
        "name": name,
        "description": description[:500],
    })
    if "error" in product:
        return product
    price_data = {
        "product": product["id"],
        "unit_amount": str(price_cents),
        "currency": currency,
    }
    if recurring_interval:
        price_data["recurring[interval]"] = recurring_interval
    price = _v1_for_account("POST", "prices", account_id, price_data)
    if "error" in price:
        return price
    return {"product": product, "price": price}


def list_products_for_account(account_id: str) -> dict:
    """Listet alle Produkte eines verbundenen Kontos."""
    return _v1_for_account("GET", "prices?expand[]=data.product&active=true&limit=100", account_id)


# ── 4. CHECKOUT FÜR VERBUNDENE KONTEN ────────────────────────────────────────

def create_checkout_session(
    account_id: str,
    price_id: str,
    quantity: int = 1,
    application_fee_percent: float = 10.0,
) -> dict:
    """Erstellt Checkout-Session für verbundenes Konto mit Plattform-Fee."""
    domain = _DOMAIN()
    # Preis-Typ ermitteln (recurring → subscription, sonst payment)
    price = _v1_for_account("GET", f"prices/{price_id}", account_id)
    mode = "subscription" if price.get("recurring") else "payment"

    data = {
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": str(quantity),
        "mode": mode,
        "success_url": f"https://{domain}/connect/done?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"https://{domain}/connect",
    }
    if mode == "payment":
        fee = int(price.get("unit_amount", 0) * application_fee_percent / 100)
        if fee > 0:
            data["payment_intent_data[application_fee_amount]"] = str(fee)
    else:
        data[f"subscription_data[application_fee_percent]"] = str(application_fee_percent)

    h = _headers_v1()
    h["Stripe-Account"] = account_id
    return _req("POST", f"{_V1_BASE}/checkout/sessions", data, h)


# ── 5. EVENT DESTINATIONS (v2 Thin Events) ───────────────────────────────────

def list_event_destinations() -> dict:
    """Listet alle Event Destinations (v2)."""
    return _v2("GET", "core/event_destinations")


def create_event_destination(
    name: str,
    webhook_url: str,
    events: list[str] = None,
) -> dict:
    """Erstellt eine Event Destination für v2 Thin Events."""
    if events is None:
        events = [
            "v1.payment_intent.succeeded",
            "v1.payment_intent.payment_failed",
            "v1.checkout.session.completed",
            "v2.core.account_link.completed",
        ]
    return _v2("POST", "core/event_destinations", {
        "name": name,
        "type": "webhook_endpoint",
        "webhook_endpoint": {
            "url": webhook_url,
        },
        "enabled_events": events,
        "include": ["webhook_endpoint.signing_secret"],
    })


def delete_event_destination(destination_id: str) -> dict:
    return _v2("DELETE", f"core/event_destinations/{destination_id}")


# ── 6. WEBHOOK HANDLER (v2 Thin Events) ──────────────────────────────────────

def parse_v2_thin_event(payload: bytes, signature: str, secret: str) -> dict:
    """
    Verifiziert und parst ein v2 Thin Event.
    v2 Thin Events haben KEINE vollständige Objektkopie — nur die ID.
    """
    import hmac, hashlib
    # Stripe v2 Signatur-Verifizierung
    try:
        parts = {k: v for p in signature.split(",") for k, v in [p.split("=", 1)]}
        ts = parts.get("t", "")
        sig = parts.get("v1", "")
        signed = f"{ts}.{payload.decode()}"
        expected = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise ValueError("Ungültige Signatur")
        age = abs(time.time() - int(ts))
        if age > 300:
            raise ValueError(f"Event zu alt: {age}s")
    except (KeyError, ValueError) as e:
        return {"error": str(e)}
    return json.loads(payload)


async def fetch_v2_event_object(event: dict) -> dict:
    """
    Ruft das vollständige Objekt eines Thin Events ab.
    Bei v2 Events: event.related_object.id → API-Call für vollständige Daten.
    """
    related = event.get("related_object") or {}
    obj_id = related.get("id", "")
    obj_type = related.get("type", "")

    if obj_type.startswith("account"):
        return get_account(obj_id)
    if obj_type.startswith("payment_intent"):
        return _v1("GET", f"payment_intents/{obj_id}")
    if obj_type.startswith("checkout.session"):
        return _v1("GET", f"checkout/sessions/{obj_id}")
    return {"id": obj_id, "type": obj_type}


# ── 7. SELBST-REGISTRIERUNG EVENT DESTINATION ────────────────────────────────

def ensure_event_destination() -> dict:
    """
    Stellt sicher dass eine Event Destination für diesen Server registriert ist.
    Wird einmalig beim Server-Start aufgerufen.
    """
    domain = _DOMAIN()
    webhook_url = f"https://{domain}/api/connect/webhooks/v2"

    existing = list_event_destinations()
    if "error" not in existing:
        for dest in (existing.get("data") or []):
            wh = dest.get("webhook_endpoint") or {}
            if wh.get("url") == webhook_url:
                log.info("Event Destination bereits aktiv: %s", dest.get("id"))
                return dest

    result = create_event_destination(
        name="SuperMegaBot Connect v2 Events",
        webhook_url=webhook_url,
    )
    if "error" not in result:
        secret = (result.get("webhook_endpoint") or {}).get("signing_secret")
        if secret:
            log.info("Event Destination erstellt: %s | Secret: %s...", result.get("id"), secret[:10])
        else:
            log.info("Event Destination erstellt: %s", result.get("id"))
    else:
        log.warning("Event Destination Fehler: %s", result.get("error"))
    return result
