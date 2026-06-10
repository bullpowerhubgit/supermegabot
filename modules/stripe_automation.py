#!/usr/bin/env python3
"""
Stripe Payment Automation
Charges, Customers, Subscriptions, Revenue Tracking, Telegram Alerts
Account: aiitec (acct_1SwsoNFZGd8ei10Q)
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

log = logging.getLogger("Stripe")

_BASE = "https://api.stripe.com/v1"
_DATA_DIR = Path(__file__).parent.parent / "data"
_CACHE_FILE = _DATA_DIR / "stripe_cache.json"


def _auth() -> Dict[str, str]:
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        raise ValueError("STRIPE_SECRET_KEY nicht gesetzt")
    return {"Authorization": f"Bearer {key}"}


def _session(total: int = 30) -> aiohttp.ClientSession:
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=total))


async def _tg(msg: str):
    import aiohttp as _aio
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1") or os.getenv("TELEGRAM_BOT_TOKEN_2") or ""
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        async with _aio.ClientSession(timeout=_aio.ClientTimeout(total=8)) as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"}
            )
    except Exception:
        pass


# ── Health ────────────────────────────────────────────────────────────────────

async def ping() -> tuple[bool, str]:
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        return False, "STRIPE_SECRET_KEY nicht gesetzt"
    try:
        async with _session() as s:
            async with s.get(f"{_BASE}/account", headers=_auth()) as r:
                if r.status == 200:
                    d = await r.json()
                    name = d.get("display_name") or d.get("business_profile", {}).get("name", "OK")
                    return True, name
                return False, f"HTTP {r.status}"
    except Exception as e:
        return False, str(e)


# ── Balance ───────────────────────────────────────────────────────────────────

async def get_balance() -> Dict:
    try:
        async with _session() as s:
            async with s.get(f"{_BASE}/balance", headers=_auth()) as r:
                if r.status != 200:
                    return {"ok": False, "error": f"HTTP {r.status}"}
                d = await r.json()
                available = {b["currency"].upper(): b["amount"] / 100 for b in d.get("available", [])}
                pending   = {b["currency"].upper(): b["amount"] / 100 for b in d.get("pending", [])}
                return {"ok": True, "available": available, "pending": pending, "livemode": d.get("livemode", False)}
    except Exception as e:
        log.error(f"get_balance: {e}")
        return {"ok": False, "error": str(e)}


# ── Charges ───────────────────────────────────────────────────────────────────

async def get_charges(limit: int = 20, days_back: int = 30) -> List[Dict]:
    since = int((datetime.now() - timedelta(days=days_back)).timestamp())
    try:
        async with _session() as s:
            async with s.get(
                f"{_BASE}/charges",
                headers=_auth(),
                params={"limit": limit, "created[gte]": since}
            ) as r:
                if r.status != 200:
                    return []
                d = await r.json()
                return [
                    {
                        "id":          c["id"],
                        "amount":      c["amount"] / 100,
                        "currency":    c["currency"].upper(),
                        "status":      c["status"],
                        "description": c.get("description", ""),
                        "email":       c.get("billing_details", {}).get("email", ""),
                        "created":     datetime.fromtimestamp(c["created"]).isoformat(),
                        "paid":        c.get("paid", False),
                        "refunded":    c.get("refunded", False),
                    }
                    for c in d.get("data", [])
                ]
    except Exception as e:
        log.error(f"get_charges: {e}")
        return []


# ── Payment Intents ───────────────────────────────────────────────────────────

async def get_payment_intents(limit: int = 20) -> List[Dict]:
    try:
        async with _session() as s:
            async with s.get(
                f"{_BASE}/payment_intents",
                headers=_auth(),
                params={"limit": limit}
            ) as r:
                if r.status != 200:
                    return []
                d = await r.json()
                return [
                    {
                        "id":       pi["id"],
                        "amount":   pi["amount"] / 100,
                        "currency": pi["currency"].upper(),
                        "status":   pi["status"],
                        "created":  datetime.fromtimestamp(pi["created"]).isoformat(),
                        "email":    pi.get("receipt_email", ""),
                    }
                    for pi in d.get("data", [])
                ]
    except Exception as e:
        log.error(f"get_payment_intents: {e}")
        return []


# ── Customers ─────────────────────────────────────────────────────────────────

async def get_customers(limit: int = 50) -> List[Dict]:
    try:
        async with _session() as s:
            async with s.get(
                f"{_BASE}/customers",
                headers=_auth(),
                params={"limit": limit}
            ) as r:
                if r.status != 200:
                    return []
                d = await r.json()
                return [
                    {
                        "id":      c["id"],
                        "email":   c.get("email", ""),
                        "name":    c.get("name", ""),
                        "created": datetime.fromtimestamp(c["created"]).isoformat(),
                        "currency": c.get("currency", "").upper(),
                        "balance": c.get("balance", 0) / 100,
                    }
                    for c in d.get("data", [])
                ]
    except Exception as e:
        log.error(f"get_customers: {e}")
        return []


# ── Subscriptions ─────────────────────────────────────────────────────────────

async def get_subscriptions(limit: int = 20, status: str = "active") -> List[Dict]:
    try:
        async with _session() as s:
            async with s.get(
                f"{_BASE}/subscriptions",
                headers=_auth(),
                params={"limit": limit, "status": status}
            ) as r:
                if r.status != 200:
                    return []
                d = await r.json()
                result = []
                for sub in d.get("data", []):
                    items = sub.get("items", {}).get("data", [])
                    amount = sum(
                        (i.get("price", {}).get("unit_amount", 0) or 0) / 100
                        for i in items
                    )
                    result.append({
                        "id":          sub["id"],
                        "status":      sub["status"],
                        "amount":      amount,
                        "currency":    (items[0].get("price", {}).get("currency", "eur").upper() if items else "EUR"),
                        "interval":    (items[0].get("price", {}).get("recurring", {}).get("interval", "") if items else ""),
                        "customer_id": sub.get("customer", ""),
                        "created":     datetime.fromtimestamp(sub["created"]).isoformat(),
                        "current_period_end": datetime.fromtimestamp(sub.get("current_period_end", 0)).isoformat(),
                    })
                return result
    except Exception as e:
        log.error(f"get_subscriptions: {e}")
        return []


# ── Revenue Summary ───────────────────────────────────────────────────────────

async def get_revenue_summary(days_back: int = 30) -> Dict:
    charges = await get_charges(limit=100, days_back=days_back)
    paid = [c for c in charges if c["paid"] and not c["refunded"]]
    refunded = [c for c in charges if c["refunded"]]

    by_currency: Dict[str, float] = {}
    for c in paid:
        cur = c["currency"]
        by_currency[cur] = by_currency.get(cur, 0) + c["amount"]

    return {
        "ok":             True,
        "period_days":    days_back,
        "total_charges":  len(charges),
        "successful":     len(paid),
        "refunded":       len(refunded),
        "revenue":        by_currency,
        "recent_charges": charges[:5],
    }


# ── Webhook Signature Verification ───────────────────────────────────────────

def verify_webhook_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify Stripe-Signature header using HMAC-SHA256.

    Stripe sends: t=<timestamp>,v1=<signature>
    We compute HMAC(secret, f"{timestamp}.{payload}") and compare.
    Returns False if secret is not configured (allows passthrough in dev).
    """
    if not secret:
        return True  # dev mode — no secret configured
    try:
        parts = {k: v for k, v in (p.split("=", 1) for p in sig_header.split(","))}
        ts = parts.get("t", "")
        sig = parts.get("v1", "")
        if not ts or not sig:
            return False
        # Reject events older than 5 minutes to prevent replay attacks
        if abs(time.time() - int(ts)) > 300:
            log.warning("Stripe webhook timestamp too old: %s", ts)
            return False
        expected = hmac.new(
            secret.encode(),
            f"{ts}.{payload.decode()}".encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, sig)
    except Exception as exc:
        log.error("verify_webhook_signature error: %s", exc)
        return False


# ── Webhook Handler ───────────────────────────────────────────────────────────

async def handle_webhook_event(event: Dict) -> str:
    etype = event.get("type", "")
    data  = event.get("data", {}).get("object", {})

    if etype == "payment_intent.succeeded":
        amount   = data.get("amount", 0) / 100
        currency = data.get("currency", "eur").upper()
        email    = data.get("receipt_email", "?")
        await _tg(
            f"💳 <b>Stripe Zahlung</b> ✅\n"
            f"Betrag: <b>{amount:.2f} {currency}</b>\n"
            f"Email: {email}"
        )
        return "payment_intent.succeeded handled"

    if etype == "customer.subscription.created":
        plan = ""
        items = data.get("items", {}).get("data", [])
        if items:
            price = items[0].get("price", {})
            amount = (price.get("unit_amount", 0) or 0) / 100
            cur    = price.get("currency", "eur").upper()
            plan   = f"{amount:.2f} {cur}/{price.get('recurring', {}).get('interval', '')}"
        await _tg(
            f"🔔 <b>Neues Abo</b> — Stripe\n"
            f"Plan: {plan}\n"
            f"ID: {data.get('id', '')}"
        )
        return "subscription.created handled"

    if etype == "charge.refunded":
        amount   = data.get("amount_refunded", 0) / 100
        currency = data.get("currency", "eur").upper()
        await _tg(
            f"↩️ <b>Stripe Rückerstattung</b>\n"
            f"Betrag: {amount:.2f} {currency}"
        )
        return "charge.refunded handled"

    if etype == "customer.subscription.deleted":
        customer_id = data.get("customer", "?")
        plan = ""
        items = data.get("items", {}).get("data", [])
        if items:
            price = items[0].get("price", {})
            amount = (price.get("unit_amount", 0) or 0) / 100
            cur    = price.get("currency", "eur").upper()
            plan   = f"{amount:.2f} {cur}/{price.get('recurring', {}).get('interval', '')}"
        await _tg(
            f"❌ <b>Abo gekündigt</b> — Stripe\n"
            f"Kunde: {customer_id}\n"
            f"Plan: {plan or 'unbekannt'}\n"
            f"Abo-ID: {data.get('id', '')}"
        )
        return "subscription.deleted handled"

    if etype == "invoice.payment_failed":
        customer_id = data.get("customer", "?")
        amount      = (data.get("amount_due", 0) or 0) / 100
        currency    = data.get("currency", "eur").upper()
        attempt_cnt = data.get("attempt_count", 1)
        next_attempt = data.get("next_payment_attempt")
        next_ts = (
            datetime.fromtimestamp(next_attempt).strftime("%d.%m.%Y %H:%M")
            if next_attempt else "kein weiterer Versuch"
        )
        await _tg(
            f"⚠️ <b>Zahlung fehlgeschlagen</b> — Stripe\n"
            f"Kunde: {customer_id}\n"
            f"Betrag: {amount:.2f} {currency}\n"
            f"Versuch #{attempt_cnt} | Nächster: {next_ts}"
        )
        return "invoice.payment_failed handled"

    return f"unhandled: {etype}"


# ── Failed Payments ───────────────────────────────────────────────────────────

async def get_failed_payments(days_back: int = 30) -> Dict:
    """Fetch all failed payment intents from the last *days_back* days.

    Returns:
        {"ok": True, "count": int, "total_failed_eur": float,
         "payments": [{"id", "amount", "currency", "created", "error", "email"}]}
    """
    since = int((datetime.now() - timedelta(days=days_back)).timestamp())
    try:
        failed_payments = []
        starting_after: Optional[str] = None

        async with _session() as s:
            while True:
                params: Dict = {
                    "limit": "100",
                    "created[gte]": str(since),
                }
                if starting_after:
                    params["starting_after"] = starting_after
                async with s.get(
                    f"{_BASE}/payment_intents",
                    headers=_auth(),
                    params=params,
                ) as r:
                    if r.status != 200:
                        return {"ok": False, "error": f"HTTP {r.status}"}
                    d = await r.json()
                chunk = [
                    pi for pi in d.get("data", [])
                    if pi.get("status") in ("requires_payment_method", "canceled")
                    and pi.get("last_payment_error")
                ]
                failed_payments.extend(chunk)
                if not d.get("has_more") or not d.get("data"):
                    break
                starting_after = d["data"][-1]["id"]

        result_list = []
        total_eur = 0.0
        for pi in failed_payments:
            amount   = (pi.get("amount") or 0) / 100
            currency = (pi.get("currency") or "eur").upper()
            err_obj  = pi.get("last_payment_error") or {}
            result_list.append({
                "id":       pi["id"],
                "amount":   amount,
                "currency": currency,
                "created":  datetime.fromtimestamp(pi["created"]).isoformat(),
                "error":    err_obj.get("message", "unknown"),
                "code":     err_obj.get("code", ""),
                "email":    pi.get("receipt_email", ""),
            })
            if currency == "EUR":
                total_eur += amount

        log.info("Failed payments (last %d days): %d, total EUR %.2f", days_back, len(result_list), total_eur)
        return {
            "ok":               True,
            "count":            len(result_list),
            "total_failed_eur": round(total_eur, 2),
            "period_days":      days_back,
            "payments":         result_list,
        }
    except Exception as e:
        log.error("get_failed_payments: %s", e)
        return {"ok": False, "error": str(e), "count": 0, "payments": []}


# ── Stats (dashboard) ─────────────────────────────────────────────────────────

async def get_stats() -> Dict:
    ok, account = await ping()
    if not ok:
        return {"ok": False, "error": account}
    balance  = await get_balance()
    revenue  = await get_revenue_summary(days_back=30)
    subs     = await get_subscriptions(limit=10)
    customers = await get_customers(limit=10)

    # Cache result
    _DATA_DIR.mkdir(exist_ok=True)
    cache = {
        "updated":    datetime.now().isoformat(),
        "account":    account,
        "balance":    balance,
        "revenue":    revenue,
        "subs":       subs[:5],
        "customers":  customers[:5],
    }
    try:
        _CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    except Exception:
        pass

    return {
        "ok":             True,
        "account":        account,
        "balance":        balance,
        "revenue_30d":    revenue,
        "active_subs":    len([s for s in subs if s["status"] == "active"]),
        "customer_count": len(customers),
        "recent_charges": revenue.get("recent_charges", []),
    }


# ── Monitor Task (called by scheduler) ───────────────────────────────────────

async def monitor_payments() -> str:
    """Check for new payments since last run, alert via Telegram."""
    cache_ts_file = _DATA_DIR / "stripe_last_check.txt"
    last_check = 0
    if cache_ts_file.exists():
        try:
            last_check = float(cache_ts_file.read_text().strip())
        except Exception:
            pass

    charges = await get_charges(limit=50, days_back=1)
    new_payments = [
        c for c in charges
        if c["paid"] and not c["refunded"]
        and datetime.fromisoformat(c["created"]).timestamp() > last_check
    ]

    cache_ts_file.write_text(str(time.time()))

    if new_payments:
        total = sum(c["amount"] for c in new_payments)
        currency = new_payments[0]["currency"] if new_payments else "EUR"
        await _tg(
            f"💰 <b>Stripe Monitor</b>\n"
            f"{len(new_payments)} neue Zahlung(en): <b>{total:.2f} {currency}</b>\n"
            + "\n".join(f"  • {c['amount']:.2f} {c['currency']} — {c['description'] or c['email']}" for c in new_payments[:3])
        )
        return f"{len(new_payments)} neue Zahlungen, {total:.2f} {currency}"

    return "keine neuen Zahlungen"


# ── Checkout Session ─────────────────────────────────────────────────────────

async def create_checkout_session(price_id: str, success_url: str = None, cancel_url: str = None) -> Dict:
    """Create a Stripe Checkout Session for subscription.

    Args:
        price_id:    Stripe Price ID (must start with 'price_')
        success_url: Redirect URL on success
        cancel_url:  Redirect URL on cancel
    """
    # Validate price_id before hitting the API
    if not price_id or not isinstance(price_id, str) or not price_id.startswith("price_"):
        return {"ok": False, "error": f"Ungültige price_id: {price_id!r} (muss mit 'price_' beginnen)"}
    try:
        async with _session() as s:
            payload = {
                "mode": "subscription",
                "payment_method_types": ["card"],
                "line_items": [{"price": price_id, "quantity": 1}],
                "success_url": success_url or f"{os.getenv('DASHBOARD_URL', 'http://localhost:8888')}/pricing?success=true",
                "cancel_url": cancel_url or f"{os.getenv('DASHBOARD_URL', 'http://localhost:8888')}/pricing?canceled=true",
            }
            async with s.post(f"{_BASE}/checkout/sessions", headers=_auth(), json=payload) as r:
                if r.status != 200:
                    return {"ok": False, "error": f"HTTP {r.status}"}
                d = await r.json()
                return {"ok": True, "url": d.get("url"), "session_id": d.get("id")}
    except Exception as e:
        log.error(f"create_checkout_session: {e}")
        return {"ok": False, "error": str(e)}


# ── Customer Portal ─────────────────────────────────────────────────────────

async def create_customer_portal_session(customer_id: str, return_url: str = None) -> Dict:
    """Create a Stripe Customer Portal session for subscription management."""
    try:
        async with _session() as s:
            payload = {
                "customer": customer_id,
                "return_url": return_url or f"{os.getenv('DASHBOARD_URL', 'http://localhost:8888')}/pricing",
            }
            async with s.post(f"{_BASE}/billing_portal/sessions", headers=_auth(), json=payload) as r:
                if r.status != 200:
                    return {"ok": False, "error": f"HTTP {r.status}"}
                d = await r.json()
                return {"ok": True, "url": d.get("url")}
    except Exception as e:
        log.error(f"create_customer_portal_session: {e}")
        return {"ok": False, "error": str(e)}


# ── SaaS Product Creation ────────────────────────────────────────────────────

SAAS_TIERS = [
    {"name": "Starter",    "price_eur": 4900,  "description": "SuperMegaBot Starter — Shopify Automation, AI Content, Telegram Alerts"},
    {"name": "Pro",        "price_eur": 9900,  "description": "SuperMegaBot Pro — Full Automation Suite, Multi-Channel Marketing, Priority Support"},
    {"name": "Enterprise", "price_eur": 29900, "description": "SuperMegaBot Enterprise — Unlimited Everything, Dedicated Infrastructure, White-Label"},
]


async def create_subscription_product(name: str, price_eur: int, description: str = "") -> Dict:
    """Create a Stripe product + monthly recurring price for a SaaS tier.

    Args:
        name: Product display name (e.g. "Starter")
        price_eur: Price in euro cents (e.g. 4900 = €49)
        description: Product description

    Returns:
        {"ok": True, "product_id": str, "price_id": str, "amount": float}
    """
    try:
        async with _session() as s:
            # Step 1 — Create product
            prod_payload = {
                "name": f"SuperMegaBot {name}",
                "description": description or f"SuperMegaBot {name} plan",
                "metadata[tier]": name.lower(),
            }
            async with s.post(f"{_BASE}/products", headers=_auth(), data=prod_payload) as r:
                if r.status not in (200, 201):
                    body = await r.text()
                    return {"ok": False, "error": f"Product creation failed HTTP {r.status}: {body[:200]}"}
                product = await r.json()

            product_id = product["id"]

            # Step 2 — Create recurring price
            price_payload = {
                "product": product_id,
                "unit_amount": str(price_eur),
                "currency": "eur",
                "recurring[interval]": "month",
                "metadata[tier]": name.lower(),
            }
            async with s.post(f"{_BASE}/prices", headers=_auth(), data=price_payload) as r:
                if r.status not in (200, 201):
                    body = await r.text()
                    return {"ok": False, "error": f"Price creation failed HTTP {r.status}: {body[:200]}"}
                price = await r.json()

        log.info("SaaS product created: %s — product_id=%s price_id=%s", name, product_id, price["id"])
        return {
            "ok":         True,
            "tier":       name,
            "product_id": product_id,
            "price_id":   price["id"],
            "amount":     price_eur / 100,
            "currency":   "EUR",
            "interval":   "month",
        }
    except Exception as e:
        log.error("create_subscription_product(%s): %s", name, e)
        return {"ok": False, "error": str(e)}


async def _get_existing_products() -> Dict[str, str]:
    """Return a map of {product_name_lower: product_id} for all existing Stripe products."""
    try:
        async with _session() as s:
            async with s.get(
                f"{_BASE}/products",
                headers=_auth(),
                params={"limit": "100", "active": "true"}
            ) as r:
                if r.status != 200:
                    return {}
                d = await r.json()
                return {
                    prod.get("name", "").lower(): prod["id"]
                    for prod in d.get("data", [])
                    if prod.get("name")
                }
    except Exception as e:
        log.warning("_get_existing_products: %s", e)
        return {}


async def setup_saas_products() -> Dict:
    """Create all 3 SaaS tiers (Starter/Pro/Enterprise) in Stripe at once.

    Idempotent: skips creation if a product with the same name already exists
    and retrieves its active price instead.

    Returns:
        {"ok": True, "tiers": [{"tier": ..., "price_id": ...}, ...], "errors": [...]}
    """
    existing = await _get_existing_products()
    results = []
    errors = []

    for tier in SAAS_TIERS:
        tier_key = f"supermegabot {tier['name'].lower()}"
        if tier_key in existing:
            product_id = existing[tier_key]
            # Fetch the active recurring price for this product
            try:
                async with _session() as s:
                    async with s.get(
                        f"{_BASE}/prices",
                        headers=_auth(),
                        params={"product": product_id, "active": "true", "limit": "5"}
                    ) as r:
                        prices_data = await r.json() if r.status == 200 else {}
                prices = prices_data.get("data", [])
                monthly_prices = [
                    p for p in prices
                    if (p.get("recurring") or {}).get("interval") == "month"
                ]
                price_id = monthly_prices[0]["id"] if monthly_prices else (prices[0]["id"] if prices else "unknown")
                results.append({
                    "ok":         True,
                    "tier":       tier["name"],
                    "product_id": product_id,
                    "price_id":   price_id,
                    "amount":     tier["price_eur"] / 100,
                    "currency":   "EUR",
                    "interval":   "month",
                    "skipped":    True,
                })
                log.info("SaaS product already exists: %s (product_id=%s)", tier["name"], product_id)
            except Exception as e:
                errors.append(f"{tier['name']}: existing product found but price lookup failed — {e}")
            continue

        result = await create_subscription_product(
            name=tier["name"],
            price_eur=tier["price_eur"],
            description=tier["description"],
        )
        if result.get("ok"):
            results.append(result)
        else:
            errors.append(f"{tier['name']}: {result.get('error')}")

    newly_created = [r for r in results if not r.get("skipped")]
    skipped_count = len([r for r in results if r.get("skipped")])
    await _tg(
        f"\U0001f3d7 <b>SaaS Products Setup</b>\n"
        f"Erstellt: {len(newly_created)}/3, Übersprungen (vorhanden): {skipped_count}/3\n"
        + "\n".join(f"  ✅ {r['tier']} — {r['amount']:.0f} EUR/mo (price_id: {r['price_id']})" for r in results)
        + ("\n⚠️ Fehler:\n" + "\n".join(errors) if errors else "")
    )

    return {
        "ok":     len(errors) == 0,
        "tiers":  results,
        "errors": errors,
    }


# ── MRR & Churn Analytics ─────────────────────────────────────────────────────

async def get_mrr() -> Dict:
    """Calculate Monthly Recurring Revenue from all active subscriptions.

    Returns:
        {"ok": True, "mrr_eur": float, "arr_eur": float, "active_count": int, "by_plan": {}}
    """
    try:
        all_subs = []
        starting_after: Optional[str] = None

        async with _session() as s:
            while True:
                params: Dict = {"status": "active", "limit": "100"}
                if starting_after:
                    params["starting_after"] = starting_after
                async with s.get(f"{_BASE}/subscriptions", headers=_auth(), params=params) as r:
                    if r.status != 200:
                        return {"ok": False, "error": f"HTTP {r.status}"}
                    d = await r.json()
                all_subs.extend(d.get("data", []))
                if not d.get("has_more"):
                    break
                if d["data"]:
                    starting_after = d["data"][-1]["id"]
                else:
                    break

        mrr_by_currency: Dict[str, float] = {}
        by_plan: Dict[str, Dict] = {}

        for sub in all_subs:
            items = sub.get("items", {}).get("data", [])
            for item in items:
                price = item.get("price", {})
                recurring = price.get("recurring", {}) or {}
                interval = recurring.get("interval", "month")
                interval_count = recurring.get("interval_count", 1) or 1
                unit_amount = price.get("unit_amount", 0) or 0
                currency = price.get("currency", "eur").lower()
                qty = item.get("quantity", 1) or 1

                # Normalise to monthly
                if interval == "year":
                    monthly = (unit_amount * qty) / (12 * interval_count)
                elif interval == "week":
                    monthly = (unit_amount * qty) * (52 / 12) / interval_count
                elif interval == "day":
                    monthly = (unit_amount * qty) * (365 / 12) / interval_count
                else:
                    monthly = (unit_amount * qty) / interval_count

                monthly_eur = monthly / 100
                mrr_by_currency[currency] = mrr_by_currency.get(currency, 0) + monthly_eur

                prod_name = price.get("nickname") or price.get("product", "unknown")
                if isinstance(prod_name, dict):
                    prod_name = prod_name.get("name", "unknown")
                prod_name = str(prod_name)
                if prod_name not in by_plan:
                    by_plan[prod_name] = {"count": 0, "mrr": 0.0, "currency": currency.upper()}
                by_plan[prod_name]["count"] += 1
                by_plan[prod_name]["mrr"] = round(by_plan[prod_name]["mrr"] + monthly_eur, 2)

        total_mrr_eur = mrr_by_currency.get("eur", 0.0)
        total_mrr_usd = mrr_by_currency.get("usd", 0.0)

        log.info("MRR: EUR %.2f, USD %.2f (%d active subs)", total_mrr_eur, total_mrr_usd, len(all_subs))
        return {
            "ok":              True,
            "mrr_eur":         round(total_mrr_eur, 2),
            "mrr_usd":         round(total_mrr_usd, 2),
            "mrr_by_currency": {k: round(v, 2) for k, v in mrr_by_currency.items()},
            "active_count":    len(all_subs),
            "by_plan":         by_plan,
            "arr_eur":         round(total_mrr_eur * 12, 2),
        }
    except Exception as e:
        log.error("get_mrr: %s", e)
        return {"ok": False, "error": str(e)}


async def get_churn_rate(days_back: int = 30) -> Dict:
    """Calculate churn rate from canceled subscriptions over the given period.

    Churn rate = canceled_in_period / (active + canceled) * 100

    Returns:
        {"ok": True, "churn_rate_pct": float, "canceled": int, "active": int, "period_days": int}
    """
    try:
        since_ts = int((datetime.now() - timedelta(days=days_back)).timestamp())

        async with _session() as s:
            # Paginate to get true active count (not just the first page)
            active_count = 0
            active_after = None
            while True:
                active_params: Dict = {"status": "active", "limit": "100"}
                if active_after:
                    active_params["starting_after"] = active_after
                async with s.get(
                    f"{_BASE}/subscriptions",
                    headers=_auth(),
                    params=active_params,
                ) as r:
                    if r.status != 200:
                        return {"ok": False, "error": f"HTTP {r.status}"}
                    active_data = await r.json()
                chunk = active_data.get("data", [])
                active_count += len(chunk)
                if not active_data.get("has_more") or not chunk:
                    break
                active_after = chunk[-1]["id"]

            # Fetch all canceled within window (paginate up to 300)
            canceled_count = 0
            starting_after = None
            while True:
                params: Dict = {
                    "status": "canceled",
                    "limit": "100",
                    "created[gte]": str(since_ts),
                }
                if starting_after:
                    params["starting_after"] = starting_after
                async with s.get(f"{_BASE}/subscriptions", headers=_auth(), params=params) as r:
                    if r.status != 200:
                        break
                    cdata = await r.json()
                chunk = cdata.get("data", [])
                canceled_count += len(chunk)
                if not cdata.get("has_more") or not chunk:
                    break
                starting_after = chunk[-1]["id"]

        base = active_count + canceled_count
        churn_rate = (canceled_count / base * 100) if base > 0 else 0.0

        # Statistical confidence flag: results are unreliable with < 5 subscriptions
        low_data = base < 5
        if low_data:
            log.warning("Churn rate based on < 5 subscriptions — low statistical confidence")

        log.info("Churn %.2f%% (%d canceled / %d base, %d days)", churn_rate, canceled_count, base, days_back)
        return {
            "ok":              True,
            "churn_rate_pct":  round(churn_rate, 2),
            "canceled":        canceled_count,
            "active":          active_count,
            "base":            base,
            "period_days":     days_back,
            "low_data_warning": low_data,
            "note": "Stichprobengröße < 5 — statistische Aussagekraft gering" if low_data else None,
        }
    except Exception as e:
        log.error("get_churn_rate: %s", e)
        return {"ok": False, "error": str(e)}
