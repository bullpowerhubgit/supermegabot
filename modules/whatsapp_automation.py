#!/usr/bin/env python3
"""
WhatsApp Business Cloud API (Meta) — Nachrichten senden, empfangen,
Bestellbenachrichtigungen und tägliche Revenue-Alerts.

Env vars:
  WHATSAPP_TOKEN        — Meta permanent access token
  WHATSAPP_PHONE_ID     — Phone number ID from Meta Business
  WHATSAPP_VERIFY_TOKEN — Webhook verification token (you choose)
  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID — Fallback notifications
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, date
from typing import Dict, List, Optional

log = logging.getLogger("WhatsAppAutomation")

_WA_BASE = "https://graph.facebook.com/v19.0"

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


# ── Config helpers ────────────────────────────────────────────────────────────

def _token() -> str:
    return os.getenv("WHATSAPP_TOKEN", "")

def _phone_id() -> str:
    return os.getenv("WHATSAPP_PHONE_ID", "")

def _verify_token() -> str:
    return os.getenv("WHATSAPP_VERIFY_TOKEN", "supermegabot_verify")

def _is_configured() -> bool:
    return bool(_token() and _phone_id())


# ── Internal HTTP helper ──────────────────────────────────────────────────────

async def _wa_post(endpoint: str, payload: Dict) -> Dict:
    """POST to WhatsApp Cloud API. Returns parsed JSON response."""
    if not HAS_AIOHTTP:
        return {"error": "aiohttp not installed"}
    if not _is_configured():
        return {"error": "WHATSAPP_TOKEN / WHATSAPP_PHONE_ID not configured"}
    url = f"{_WA_BASE}/{_phone_id()}/{endpoint}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                url,
                headers={
                    "Authorization": f"Bearer {_token()}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status not in (200, 201):
                    log.warning("WhatsApp API %s %s: %s", resp.status, endpoint, data)
                return data
    except Exception as exc:
        log.error("WhatsApp POST error: %s", exc)
        return {"error": str(exc)}


# ── In-memory stats counter (reset on restart) ────────────────────────────────

_stats: Dict[str, int] = {
    "sent_today": 0,
    "received_today": 0,
    "sent_month": 0,
    "received_month": 0,
}
_stats_date = str(date.today())


def _bump_sent() -> None:
    global _stats_date
    today = str(date.today())
    if today != _stats_date:
        _stats["sent_today"] = 0
        _stats["received_today"] = 0
        _stats_date = today
    _stats["sent_today"] += 1
    _stats["sent_month"] += 1


def _bump_received() -> None:
    global _stats_date
    today = str(date.today())
    if today != _stats_date:
        _stats["sent_today"] = 0
        _stats["received_today"] = 0
        _stats_date = today
    _stats["received_today"] += 1
    _stats["received_month"] += 1


# ── Claude AI helper for auto-replies ────────────────────────────────────────

async def _claude_reply(user_message: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or not HAS_AIOHTTP:
        return "Entschuldigung, KI-Antworten sind gerade nicht verfügbar."
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 256,
                    "system": (
                        "Du bist der SuperMegaBot Assistent für WhatsApp. "
                        "Antworte kurz und hilfreich auf Deutsch. "
                        "Du hilfst bei Shopify-Shop Fragen, Bestellungen und Revenue-Tracking."
                    ),
                    "messages": [{"role": "user", "content": user_message}],
                },
            ) as resp:
                if resp.status != 200:
                    return "Entschuldigung, ich konnte Ihre Anfrage nicht verarbeiten."
                data = await resp.json()
                return data["content"][0]["text"]
    except Exception as exc:
        log.error("Claude reply error: %s", exc)
        return "Entschuldigung, ein Fehler ist aufgetreten."


# ── Public API ────────────────────────────────────────────────────────────────

async def send_message(to_number: str, message: str) -> bool:
    """Sendet eine WhatsApp-Textnachricht."""
    if not to_number or not message:
        return False
    # Normalize number: remove spaces/dashes, ensure it starts with country code
    number = to_number.replace(" ", "").replace("-", "").lstrip("+")
    result = await _wa_post(
        "messages",
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": number,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        },
    )
    if "error" in result:
        log.warning("send_message to %s failed: %s", number, result["error"])
        return False
    _bump_sent()
    log.info("WhatsApp message sent to %s", number)
    return True


async def send_template_message(
    to_number: str, template_name: str, params: List[str]
) -> bool:
    """Sendet eine vorgenehmigte WhatsApp Template-Nachricht."""
    if not to_number or not template_name:
        return False
    number = to_number.replace(" ", "").replace("-", "").lstrip("+")
    components = []
    if params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": p} for p in params],
        })
    result = await _wa_post(
        "messages",
        {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "de"},
                "components": components,
            },
        },
    )
    if "error" in result:
        log.warning("send_template_message to %s failed: %s", number, result["error"])
        return False
    _bump_sent()
    return True


async def send_order_notification(order: Dict) -> bool:
    """
    Neue Shopify-Bestellung -> WhatsApp an Betreiber.
    Nachricht: 'Neue Bestellung #1234 — €49.99 von Max M.'
    """
    owner_number = os.getenv("WHATSAPP_OWNER_NUMBER", "")
    if not owner_number:
        log.warning("WHATSAPP_OWNER_NUMBER not set, skipping order notification")
        return False
    order_num = order.get("order_number") or order.get("name") or order.get("id", "?")
    total     = order.get("total_price", "?")
    currency  = order.get("currency", "EUR")
    billing   = order.get("billing_address") or order.get("customer") or {}
    first     = billing.get("first_name", "Kunde")
    last_i    = (billing.get("last_name") or "")[:1]
    customer  = f"{first} {last_i}.".strip()
    msg = f"Neue Bestellung #{order_num} — {total} {currency} von {customer}"
    return await send_message(owner_number, msg)


async def send_revenue_alert(daily_revenue: float, target: float) -> bool:
    """
    Tages-Umsatz-Alert wenn > target oder < 50% von target.
    """
    owner_number = os.getenv("WHATSAPP_OWNER_NUMBER", "")
    if not owner_number:
        return False
    today = datetime.now().strftime("%d.%m.%Y")
    if daily_revenue > target:
        msg = (
            f"Ziel erreicht! Tagesumsatz: €{daily_revenue:.2f} "
            f"(Ziel: €{target:.2f}) — {today}"
        )
    elif daily_revenue < target * 0.5:
        msg = (
            f"Umsatz unter 50% des Ziels! Heute: €{daily_revenue:.2f} "
            f"(Ziel: €{target:.2f}) — {today}"
        )
    else:
        # Within range — no alert needed
        return True
    return await send_message(owner_number, msg)


async def handle_incoming_message(data: Dict) -> str:
    """
    Verarbeitet eingehende WhatsApp-Nachrichten und gibt eine Antwort zurück.
    Kommandos: 'umsatz', 'bestellungen', 'hilfe' — sonst Claude AI.
    """
    _bump_received()
    text = str(data.get("text", {}).get("body", "")).strip().lower()
    from_number = data.get("from", "")

    if text in ("umsatz", "revenue", "einnahmen"):
        try:
            from modules.revenue_aggregator import get_daily_report  # type: ignore
            report = await get_daily_report()
            reply = f"Revenue-Übersicht:\n{report}"
        except Exception as exc:
            reply = f"Revenue-Daten nicht verfügbar: {exc}"

    elif text in ("bestellungen", "orders", "bestellung"):
        try:
            import os as _os
            import aiohttp as _ah
            token  = _os.getenv("SHOPIFY_ACCESS_TOKEN", "")
            domain = _os.getenv("SHOPIFY_SHOP_DOMAIN", "")
            if token and domain:
                base = f"https://{domain}" if not domain.startswith("http") else domain
                async with _ah.ClientSession(timeout=_ah.ClientTimeout(total=10)) as s:
                    async with s.get(
                        f"{base}/admin/api/{_os.getenv('SHOPIFY_API_VERSION','2024-10')}/orders.json?limit=5&status=any",
                        headers={"X-Shopify-Access-Token": token},
                    ) as resp:
                        od = await resp.json()
                orders = od.get("orders", [])
                if orders:
                    lines = [f"Letzte {len(orders)} Bestellungen:"]
                    for o in orders:
                        lines.append(
                            f"#{o.get('order_number','?')} — "
                            f"{o.get('total_price','?')} {o.get('currency','EUR')} — "
                            f"{o.get('financial_status','?')}"
                        )
                    reply = "\n".join(lines)
                else:
                    reply = "Keine Bestellungen gefunden."
            else:
                reply = "Shopify nicht konfiguriert."
        except Exception as exc:
            reply = f"Fehler beim Laden der Bestellungen: {exc}"

    elif text in ("hilfe", "help", "commands", "?"):
        reply = (
            "SuperMegaBot WhatsApp Commands:\n"
            "umsatz — Tages-Revenue-Übersicht\n"
            "bestellungen — Letzte 5 Bestellungen\n"
            "hilfe — Diese Liste\n"
            "Alle anderen Nachrichten werden von KI beantwortet."
        )
    else:
        reply = await _claude_reply(data.get("text", {}).get("body", text))

    # Send reply back to sender
    if from_number and reply:
        await send_message(from_number, reply)
    return reply


async def verify_webhook(token: str, challenge: str) -> str:
    """WhatsApp Webhook Verification (GET request from Meta)."""
    if token == _verify_token():
        return challenge
    return ""


async def process_webhook(data: Dict) -> None:
    """
    Verarbeitet eingehende WhatsApp Webhook Events.
    Supports: messages, message status updates.
    """
    try:
        entry = (data.get("entry") or [{}])[0]
        changes = entry.get("changes") or []
        for change in changes:
            value = change.get("value", {})
            # Incoming messages
            for msg in value.get("messages") or []:
                if msg.get("type") == "text":
                    await handle_incoming_message(msg)
                else:
                    log.info("Received non-text WhatsApp message type: %s", msg.get("type"))
            # Status updates (delivered, read, failed)
            for status in value.get("statuses") or []:
                log.info(
                    "WhatsApp message %s status: %s",
                    status.get("id"), status.get("status")
                )
    except Exception as exc:
        log.error("process_webhook error: %s", exc)


async def get_whatsapp_stats() -> Dict:
    """Returns message stats for today and this month."""
    return {
        "configured": _is_configured(),
        "phone_id": _phone_id() or None,
        "sent_today": _stats["sent_today"],
        "received_today": _stats["received_today"],
        "sent_month": _stats["sent_month"],
        "received_month": _stats["received_month"],
        "stats_date": _stats_date,
    }


async def broadcast_to_subscribers(
    message: str, subscriber_numbers: List[str]
) -> Dict:
    """
    Sendet eine Broadcast-Nachricht an alle angegebenen WhatsApp-Nummern.
    Returns: {"sent": 5, "failed": 1, "total": 6}
    """
    if not message or not subscriber_numbers:
        return {"sent": 0, "failed": 0, "total": 0}
    sent = 0
    failed = 0
    for number in subscriber_numbers:
        ok = await send_message(number, message)
        if ok:
            sent += 1
        else:
            failed += 1
        # Brief pause to respect Meta rate limits
        import asyncio
        await asyncio.sleep(0.5)
    log.info("Broadcast complete: %s/%s sent", sent, len(subscriber_numbers))
    return {"sent": sent, "failed": failed, "total": len(subscriber_numbers)}
