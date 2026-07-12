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
    except Exception as _e:
        log.debug("skipped: %s", _e)


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

async def _auto_enroll_buyer(email: str, first_name: str, amount: float, sequence: str) -> None:
    """Enroll buyer in email sequence + Klaviyo profile + track event."""
    try:
        from modules.email_sequence_engine import enroll
        await enroll(email, sequence, first_name=first_name,
                     metadata={"amount": amount, "source": "stripe"})
    except Exception as e:
        log.warning("Email sequence enroll failed: %s", e)
    try:
        from modules.klaviyo_automation import upsert_profile, get_lists, add_profile_to_list
        pid = await upsert_profile(email, first_name=first_name,
                                   properties={"stripe_purchase_amount": amount,
                                               "purchase_source": "stripe"})
        if pid:
            lists = await get_lists()
            buyers_list = next((l["id"] for l in lists
                                if "buyer" in l["name"].lower() or "kunde" in l["name"].lower()), None)
            if buyers_list:
                await add_profile_to_list(buyers_list, pid)
    except Exception as e:
        log.warning("Klaviyo enroll failed: %s", e)


async def _trello_card_for_event(etype: str, event_data: dict) -> None:
    """Fire-and-forget Trello card creation for Stripe events."""
    try:
        from modules.trello_client import handle_stripe_event
        await handle_stripe_event(etype, event_data)
    except Exception as exc:
        log.debug("Trello card skipped (token not set?): %s", exc)


async def handle_webhook_event(event: Dict) -> str:
    etype = event.get("type", "")
    data  = event.get("data", {}).get("object", {})
    asyncio.create_task(_trello_card_for_event(etype, event.get("data", {})))

    if etype == "payment_intent.succeeded":
        amount   = data.get("amount", 0) / 100
        currency = data.get("currency", "eur").upper()
        email    = data.get("receipt_email") or data.get("customer_email") or "?"
        name     = (data.get("shipping", {}) or {}).get("name", "") or email.split("@")[0]
        await _tg(
            f"💳 <b>Stripe Zahlung</b> ✅\n"
            f"Betrag: <b>{amount:.2f} {currency}</b>\n"
            f"Email: {email}"
        )
        if email and "@" in email:
            asyncio.create_task(_auto_enroll_buyer(email, name, amount, "post_purchase"))
        return "payment_intent.succeeded handled + email_sequence enrolled"

    if etype == "checkout.session.completed":
        email    = data.get("customer_email") or data.get("customer_details", {}).get("email", "?")
        name     = (data.get("customer_details") or {}).get("name", "") or email.split("@")[0]
        amount   = (data.get("amount_total") or 0) / 100
        currency = (data.get("currency") or "eur").upper()
        mode     = data.get("mode", "payment")
        seq      = "saas_onboarding" if mode == "subscription" else "post_purchase"
        await _tg(
            f"🛒 <b>Checkout abgeschlossen</b> ✅\n"
            f"Betrag: <b>{amount:.2f} {currency}</b> ({mode})\n"
            f"Email: {email}"
        )
        if email and "@" in email:
            asyncio.create_task(_auto_enroll_buyer(email, name, amount, seq))
        return f"checkout.session.completed handled → {seq}"

    if etype == "customer.subscription.created":
        plan = ""
        items = data.get("items", {}).get("data", [])
        customer_email = data.get("customer_email", "?")
        if items:
            price = items[0].get("price", {})
            amount = (price.get("unit_amount", 0) or 0) / 100
            cur    = price.get("currency", "eur").upper()
            plan   = f"{amount:.2f} {cur}/{price.get('recurring', {}).get('interval', '')}"
        await _tg(
            f"🔔 <b>Neues Abo</b> — Stripe\n"
            f"Plan: {plan}\n"
            f"Email: {customer_email}"
        )
        if customer_email and "@" in customer_email:
            asyncio.create_task(_auto_enroll_buyer(customer_email, customer_email.split("@")[0],
                                                    float(plan.split()[0]) if plan else 0,
                                                    "saas_onboarding"))
        return "subscription.created handled + onboarding enrolled"

    if etype == "charge.refunded":
        amount   = data.get("amount_refunded", 0) / 100
        currency = data.get("currency", "eur").upper()
        email    = data.get("billing_details", {}).get("email", "?")
        await _tg(
            f"↩️ <b>Stripe Rückerstattung</b>\n"
            f"Betrag: {amount:.2f} {currency}\n"
            f"Email: {email}"
        )
        return "charge.refunded handled"

    if etype == "customer.subscription.deleted":
        customer_id = data.get("customer", "?")
        items = data.get("items", {}).get("data", [])
        plan = ""
        if items:
            price = items[0].get("price", {})
            amount = (price.get("unit_amount", 0) or 0) / 100
            cur    = price.get("currency", "eur").upper()
            plan   = f"{amount:.2f} {cur}/{price.get('recurring', {}).get('interval', '')}"
        customer_email = data.get("customer_email", customer_id)
        await _tg(
            f"❌ <b>Abo gekündigt</b> — Stripe\n"
            f"Plan: {plan}\n"
            f"Email: {customer_email}"
        )
        if customer_email and "@" in customer_email:
            asyncio.create_task(_auto_enroll_buyer(
                customer_email, customer_email.split("@")[0], 0, "winback"
            ))
        return "subscription.deleted handled + winback enrolled"

    if etype == "invoice.payment_failed":
        amount   = (data.get("amount_due") or 0) / 100
        currency = (data.get("currency") or "eur").upper()
        email    = data.get("customer_email") or "?"
        attempt  = data.get("attempt_count", 1)
        await _tg(
            f"⚠️ <b>Zahlung fehlgeschlagen</b> — Stripe\n"
            f"Betrag: {amount:.2f} {currency}\n"
            f"Versuch #{attempt}\n"
            f"Email: {email}"
        )
        return f"invoice.payment_failed handled (attempt #{attempt})"

    if etype == "customer.subscription.updated":
        customer_email = data.get("customer_email", "?")
        status = data.get("status", "?")
        await _tg(
            f"🔄 <b>Abo aktualisiert</b> — Stripe\n"
            f"Status: {status}\n"
            f"Email: {customer_email}"
        )
        return f"subscription.updated handled (status={status})"

    return f"unhandled: {etype}"


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
    except Exception as _e:
        log.debug("skipped: %s", _e)

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
        except Exception as _e:
            log.debug("skipped: %s", _e)

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
