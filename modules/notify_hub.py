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


def send_telegram(text: str) -> bool:
    """Sync alias for _tg_send."""
    return _tg_send(text)


async def async_send_telegram(text: str) -> bool:
    """Async-safe wrapper — runs sync send_telegram in executor to avoid 'bool can't be awaited'."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _tg_send, text)


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
    # Slack — immer versuchen (Webhook oder Bot Token)
    slack_wh = os.getenv("SLACK_WEBHOOK_URL", "")
    slack_tok = os.getenv("SLACK_BOT_TOKEN", SLACK_BOT)
    slack_ch  = os.getenv("SLACK_DEFAULT_CHANNEL", "#ops")
    if slack_wh or slack_tok:
        try:
            slack_text = f"{icon} *{title}*"
            if body:
                slack_text += f"\n{body}"
            import urllib.request as _ur
            req_data = json.dumps({"text": slack_text[:4000]}).encode()
            if slack_wh:
                req = _ur.Request(slack_wh, data=req_data, headers={"Content-Type": "application/json"})
                with _ur.urlopen(req, timeout=6) as r:
                    results.append(r.status == 200)
            elif slack_tok:
                req = _ur.Request(
                    "https://slack.com/api/chat.postMessage",
                    data=json.dumps({"channel": slack_ch, "text": slack_text}).encode(),
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {slack_tok}"}
                )
                with _ur.urlopen(req, timeout=6) as r:
                    d = json.loads(r.read())
                    results.append(d.get("ok", False))
        except Exception as _se:
            log.debug("Slack notify failed: %s", _se)

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

async def send_daily_revenue_report(
    shopify_eur: float = 0.0,
    shopify_orders: int = 0,
    ds24_eur: float = 0.0,
    ds24_sales: int = 0,
    stripe_eur: float = 0.0,
    gumroad_eur: float = 0.0,
    date_str: str | None = None,
) -> bool:
    """
    Build and send the daily revenue report to Telegram.
    Fetches real data from revenue_aggregator if no values provided.
    Format matches the canonical report template.
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    # If no data provided, try to fetch from revenue_aggregator
    if shopify_eur == 0 and ds24_eur == 0 and stripe_eur == 0:
        try:
            from modules.revenue_aggregator import get_platform_revenue
            data = await get_platform_revenue()
            platforms = data.get("platforms", {})

            sh = platforms.get("shopify", {})
            shopify_eur = sh.get("revenue", 0.0)
            shopify_orders = sh.get("orders", 0)

            ds = platforms.get("digistore", {})
            ds24_eur = ds.get("revenue", 0.0)
            ds24_sales = ds.get("orders", 0)

            # Stripe via stripe_client
            try:
                from modules.stripe_client import get_revenue_stats
                st = await get_revenue_stats()
                stripe_eur = st.get("today_revenue", 0.0)
            except Exception:
                try:
                    from modules.stripe_client import get_revenue_summary
                    import asyncio as _asyncio
                    loop = _asyncio.get_event_loop()
                    st = await loop.run_in_executor(None, get_revenue_summary)
                    stripe_eur = st.get("today_revenue", 0.0)
                except Exception as _e:
                    log.debug("skipped: %s", _e)

            gm = platforms.get("gumroad", {})
            from modules.revenue_aggregator import _to_eur as _rev_to_eur
            gumroad_eur = _rev_to_eur(gm.get("revenue", 0.0), gm.get("currency", "USD")) if gm.get("ok") else 0.0
        except Exception as exc:
            log.warning("Revenue fetch for daily report failed: %s", exc)

    total_eur = shopify_eur + ds24_eur + stripe_eur + gumroad_eur

    msg = (
        f"📊 <b>Revenue Report {date_str}</b>\n"
        "\n"
        f"🛒 <b>Shopify</b>: €{shopify_eur:.2f} ({shopify_orders} Bestellungen)\n"
        f"💾 <b>DS24</b>: €{ds24_eur:.2f} ({ds24_sales} Verkäufe)\n"
        f"💳 <b>Stripe</b>: €{stripe_eur:.2f}\n"
        f"📦 <b>Gesamt</b>: €{total_eur:.2f}\n"
        "\n"
        "🤖 System aktiv | BRUTUS läuft"
    )
    return await async_send_telegram(msg)


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
