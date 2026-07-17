#!/usr/bin/env python3
"""
Stripe Payment Hook — Zahlung erkannt → Resend Onboarding sofort starten.

Trigger:
  checkout.session.completed
  customer.subscription.created
  invoice.payment_succeeded (Abo-Verlängerung)

Aktion:
  1. Email + Name aus Stripe-Event extrahieren
  2. Resend Onboarding-Sequenz starten (D0/D1/D3/D7)
  3. Telegram-Notification an Rudolf
  4. SQLite-Log in data/stripe_payments.db

Verwendung (aiohttp Webhook-Handler):
  from modules.stripe_payment_hook import handle_stripe_event
  await handle_stripe_event(payload_bytes, sig_header)

Scheduled check (Polling-Fallback wenn kein Webhook):
  from modules.stripe_payment_hook import task_stripe_payment_poll
  await task_stripe_payment_poll()
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

log = logging.getLogger("StripePaymentHook")

_BASE    = Path(__file__).resolve().parents[1]
_DB_PATH = _BASE / "data" / "stripe_payments.db"


# ── Credentials ──────────────────────────────────────────────────────────────

def _stripe_key() -> str:
    v = os.getenv("STRIPE_SECRET_KEY", "")
    if v.startswith("sk_live_51Tg1U") or v.startswith("sk_test_"):
        return v
    raise RuntimeError("STRIPE_SECRET_KEY is not the ineedit.com.co key — aborting")

def _webhook_secret() -> str:
    return os.getenv("STRIPE_WEBHOOK_SECRET", "")

def _tg_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")

def _tg_chat() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


# ── SQLite ────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id           TEXT PRIMARY KEY,
            email        TEXT,
            name         TEXT,
            amount_eur   REAL,
            event_type   TEXT,
            onboarded    INTEGER DEFAULT 0,
            received_at  INTEGER DEFAULT (strftime('%s','now'))
        )
    """)
    conn.commit()
    return conn


def _already_processed(payment_id: str) -> bool:
    with _db() as c:
        row = c.execute("SELECT id FROM payments WHERE id=?", (payment_id,)).fetchone()
        return row is not None


def _record_payment(payment_id: str, email: str, name: str, amount_eur: float, event_type: str) -> None:
    with _db() as c:
        c.execute(
            "INSERT OR IGNORE INTO payments(id,email,name,amount_eur,event_type) VALUES(?,?,?,?,?)",
            (payment_id, email, name, amount_eur, event_type),
        )


def _mark_onboarded(payment_id: str) -> None:
    with _db() as c:
        c.execute("UPDATE payments SET onboarded=1 WHERE id=?", (payment_id,))


# ── Stripe Webhook Verify ─────────────────────────────────────────────────────

def verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    try:
        parts = {k: v for k, v in (p.split("=", 1) for p in sig_header.split(",") if "=" in p)}
        timestamp = parts.get("t", "")
        signatures = [v for k, v in parts.items() if k == "v1"]
        signed = f"{timestamp}.".encode() + payload
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, s) for s in signatures)
    except Exception:
        return False


# ── Event-Verarbeitung ────────────────────────────────────────────────────────

async def _trigger_onboarding(email: str, name: str, amount_eur: float, payment_id: str) -> bool:
    """Startet die Resend-Onboarding-Sequenz für den neuen Kunden."""
    try:
        from modules.email_onboarding_autopilot import send_onboarding_sequence
        result = await send_onboarding_sequence(email=email, name=name or "Kunde")
        if result.get("ok"):
            _mark_onboarded(payment_id)
            log.info("✅ Onboarding gestartet: %s", email)
            return True
        log.warning("Onboarding fehlgeschlagen: %s — %s", email, result)
        return False
    except Exception as e:
        log.error("Onboarding-Fehler: %s", e)
        return False


async def _notify_telegram(email: str, name: str, amount_eur: float, event_type: str) -> None:
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return
    emoji = "🔄" if "subscription" in event_type else "💰"
    msg = (
        f"{emoji} <b>Neue Zahlung — ineedit.com.co</b>\n"
        f"💶 Betrag: <b>€{amount_eur:.2f}</b>\n"
        f"👤 Kunde: {name or '(kein Name)'} &lt;{email}&gt;\n"
        f"📋 Typ: {event_type}\n"
        f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram Fehler: %s", e)


async def _process_event(event: dict) -> dict[str, Any]:
    """Verarbeitet ein Stripe-Event — gibt Ergebnis zurück."""
    event_type = event.get("type", "")
    obj        = event.get("data", {}).get("object", {})
    event_id   = event.get("id", f"evt_{int(time.time())}")

    email      = ""
    name       = ""
    amount_eur = 0.0

    if event_type == "checkout.session.completed":
        email      = obj.get("customer_details", {}).get("email") or obj.get("customer_email", "")
        name       = (obj.get("customer_details") or {}).get("name", "")
        amount_eur = (obj.get("amount_total") or 0) / 100.0

    elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
        cid = obj.get("customer", "")
        if cid:
            try:
                key = _stripe_key()
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        f"https://api.stripe.com/v1/customers/{cid}",
                        headers={"Authorization": f"Bearer {key}"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        cdata  = await r.json()
                        email  = cdata.get("email", "")
                        name   = cdata.get("name", "")
            except Exception as e:
                log.warning("Kunde nicht abrufbar: %s", e)
        items      = (obj.get("items") or {}).get("data") or []
        for item in items:
            price = item.get("price") or {}
            if price.get("unit_amount"):
                amount_eur += price["unit_amount"] / 100.0

    elif event_type == "invoice.payment_succeeded":
        email      = obj.get("customer_email", "")
        name       = obj.get("customer_name", "")
        amount_eur = (obj.get("amount_paid") or 0) / 100.0

    else:
        return {"ok": True, "skipped": True, "event_type": event_type}

    if not email:
        return {"ok": False, "error": "Keine Email im Event"}

    if _already_processed(event_id):
        return {"ok": True, "skipped": True, "reason": "already_processed", "id": event_id}

    _record_payment(event_id, email, name, amount_eur, event_type)

    # Onboarding + Telegram parallel
    onboarded, _ = await asyncio.gather(
        _trigger_onboarding(email, name, amount_eur, event_id),
        _notify_telegram(email, name, amount_eur, event_type),
        return_exceptions=True,
    )

    return {
        "ok": True,
        "event_id": event_id,
        "event_type": event_type,
        "email": email,
        "amount_eur": amount_eur,
        "onboarding_started": bool(onboarded),
    }


# ── Öffentliche API ───────────────────────────────────────────────────────────

async def handle_stripe_event(payload: bytes, sig_header: str) -> dict[str, Any]:
    """aiohttp-Handler für POST /webhooks/stripe."""
    secret = _webhook_secret()
    if secret and not verify_stripe_signature(payload, sig_header, secret):
        return {"ok": False, "error": "Invalid signature"}
    try:
        event = json.loads(payload)
    except Exception as e:
        return {"ok": False, "error": f"JSON parse error: {e}"}
    return await _process_event(event)


async def task_stripe_payment_poll() -> dict[str, Any]:
    """Polling-Fallback: prüft letzte 24h Stripe-Events (kein Webhook nötig)."""
    processed = 0
    errors    = 0
    try:
        key = _stripe_key()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    since = int(time.time()) - 86400  # letzte 24h
    url   = (
        f"https://api.stripe.com/v1/events"
        f"?types[]=checkout.session.completed"
        f"&types[]=customer.subscription.created"
        f"&types[]=invoice.payment_succeeded"
        f"&created[gte]={since}&limit=50"
    )
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url,
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data   = await r.json()
                events = data.get("data") or []
        for event in events:
            result = await _process_event(event)
            if result.get("ok") and not result.get("skipped"):
                processed += 1
            elif not result.get("ok"):
                errors += 1
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

    return {
        "ok": True,
        "events_checked": len(events) if "events" in dir() else 0,
        "processed": processed,
        "errors": errors,
        "at": datetime.now(timezone.utc).isoformat(),
    }


async def get_payment_stats() -> dict[str, Any]:
    """Übersicht über verarbeitete Zahlungen."""
    with _db() as c:
        total     = c.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
        onboarded = c.execute("SELECT COUNT(*) FROM payments WHERE onboarded=1").fetchone()[0]
        revenue   = c.execute("SELECT COALESCE(SUM(amount_eur),0) FROM payments").fetchone()[0]
        recent    = c.execute(
            "SELECT email, amount_eur, event_type, received_at FROM payments ORDER BY received_at DESC LIMIT 5"
        ).fetchall()
    return {
        "total_payments": total,
        "onboarding_triggered": onboarded,
        "total_revenue_eur": round(revenue, 2),
        "recent": [dict(r) for r in recent],
    }
