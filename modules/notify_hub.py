#!/usr/bin/env python3
"""
NotifyHub — Zentrale Benachrichtigungs-Schicht für alle SuperMegaBot-Projekte.

Primär: Telegram (Rudiclone-Bot, Chat 5088771245) — immer verfügbar.
Sekundär: Slack (xapp-1- Bot Token) — für Team-Workspace marketing-m9r3843.
Tertiär:  Discord Webhook (wenn konfiguriert).

Alle anderen Module importieren NUR diesen Hub.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.request
from datetime import datetime
from typing import Optional

log = logging.getLogger("NotifyHub")

# ── Credentials aus .env ──────────────────────────────────────────────────────
TG_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "8600739487:AAGhByAoKEpbsfco9swoaRYjU2HI_gSt718")
TG_CHAT    = os.getenv("TELEGRAM_CHAT_ID", "5088771245")
SLACK_BOT  = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHAN  = os.getenv("SLACK_DEFAULT_CHANNEL", "C0000000000")  # wird per API aufgelöst
DISCORD_WH = os.getenv("DISCORD_WEBHOOK_URL", "")

# ── Emoji-Präfixe nach Event-Typ ─────────────────────────────────────────────
_ICONS = {
    "revenue": "💰", "error": "🔴", "deploy": "🚀", "alert": "⚠️",
    "health": "💚", "order": "🛒", "payment": "💳", "info": "ℹ️",
    "start": "▶️", "stop": "⏹️", "success": "✅", "warn": "🟡",
}


def _icon(event_type: str) -> str:
    return _ICONS.get(event_type.lower(), "📢")


# ── Sync HTTP-Helfer (kein aiohttp nötig) ────────────────────────────────────

def _http_post(url: str, data: dict, headers: dict | None = None) -> bool:
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body,
                                     headers={**(headers or {}), "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status == 200
    except Exception as e:
        log.warning("HTTP POST %s failed: %s", url, e)
        return False


def _tg_send(text: str) -> bool:
    if not TG_TOKEN:
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    return _http_post(url, {"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"})


def _discord_send(title: str, body: str, color: int = 0x00ff88) -> bool:
    if not DISCORD_WH:
        return False
    payload = {"embeds": [{"title": title, "description": body,
                            "color": color, "timestamp": datetime.utcnow().isoformat()}]}
    return _http_post(DISCORD_WH, payload)


# ── Public API ────────────────────────────────────────────────────────────────

def notify(title: str, body: str = "", event_type: str = "info") -> bool:
    """
    Sende Benachrichtigung an alle konfigurierten Channels.
    Gibt True zurück wenn mindestens ein Channel erfolgreich war.
    """
    icon = _icon(event_type)
    tg_msg = f"{icon} <b>{title}</b>"
    if body:
        tg_msg += f"\n{body}"

    results = []
    results.append(_tg_send(tg_msg))
    if DISCORD_WH:
        color = {"error": 0xff0000, "revenue": 0x00ff88, "warn": 0xffaa00}.get(event_type, 0x5865f2)
        results.append(_discord_send(f"{icon} {title}", body, color))

    success = any(results)
    if not success:
        log.error("NotifyHub: Alle Channels fehlgeschlagen — %s: %s", title, body)
    return success


def notify_revenue(amount: float, currency: str, product: str, source: str = "") -> bool:
    title = f"Neue Zahlung: {amount:.2f} {currency}"
    body = f"Produkt: {product}"
    if source:
        body += f"\nQuelle: {source}"
    return notify(title, body, "revenue")


def notify_error(service: str, error: str, detail: str = "") -> bool:
    title = f"Fehler in {service}"
    body = error
    if detail:
        body += f"\n{detail[:300]}"
    return notify(title, body, "error")


def notify_deploy(service: str, status: str = "deployed", url: str = "") -> bool:
    title = f"Deploy: {service} — {status}"
    body = url if url else ""
    return notify(title, body, "deploy")


def notify_health(service: str, status: str, detail: str = "") -> bool:
    etype = "health" if "ok" in status.lower() else "warn"
    return notify(f"Health: {service} — {status}", detail, etype)


async def notify_async(title: str, body: str = "", event_type: str = "info") -> bool:
    """Async-Wrapper für aiohttp-Kontexte."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, notify, title, body, event_type)


async def notify_revenue_async(amount: float, currency: str, product: str, source: str = "") -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, notify_revenue, amount, currency, product, source)


# ── Stripe Webhook-Integration ────────────────────────────────────────────────

def handle_stripe_payment_event(event: dict) -> None:
    """Wird von handle_stripe_webhook aufgerufen — sofort Telegram-Alert."""
    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    if etype == "checkout.session.completed":
        amt = (obj.get("amount_total") or 0) / 100
        currency = (obj.get("currency") or "eur").upper()
        customer = obj.get("customer_email") or obj.get("customer_details", {}).get("email", "?")
        product_name = (obj.get("metadata") or {}).get("product", "Checkout")
        notify_revenue(amt, currency, product_name, f"Stripe Checkout — {customer}")

    elif etype == "invoice.payment_succeeded":
        amt = (obj.get("amount_paid") or 0) / 100
        currency = (obj.get("currency") or "eur").upper()
        customer = obj.get("customer_email", "?")
        notify_revenue(amt, currency, "Subscription", f"Stripe Invoice — {customer}")

    elif etype in ("payment_intent.payment_failed", "invoice.payment_failed"):
        customer = obj.get("customer_email") or "?"
        notify_error("Stripe", f"Zahlung fehlgeschlagen — {customer}",
                     obj.get("last_payment_error", {}).get("message", ""))


# ── Slack Integration (via slack_notify module) ───────────────────────────────

async def send_slack_alert(message: str, level: str = "info") -> bool:
    """
    Send a Slack notification using the central slack_notify module.
    level: info | warning | error | revenue | ops
    """
    try:
        from modules.slack_notify import send_slack
        return await send_slack(message, level=level)
    except Exception as exc:
        import logging
        logging.getLogger("notify_hub").warning("Slack alert failed: %s", exc)
        return False
