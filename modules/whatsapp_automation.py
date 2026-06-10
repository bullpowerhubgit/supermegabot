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

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime, timezone, date
from typing import Dict, List, Optional

log = logging.getLogger("WhatsAppAutomation")

_WA_BASE = "https://graph.facebook.com/v19.0"

# E.164 phone number validation: optional leading +, 7-15 digits
_PHONE_E164_RE = re.compile(r"^\+?[1-9]\d{6,14}$")

# WhatsApp Cloud API: 1000 messages/second burst; use 0.002s min sleep between sends.
# For broadcast safety we use a more conservative 0.1s (100 msg/s effective).
_BROADCAST_DELAY_S = 0.1

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

def _app_secret() -> str:
    return os.getenv("WHATSAPP_APP_SECRET", "")

def _is_configured() -> bool:
    return bool(_token() and _phone_id())


# ── Phone number validation ───────────────────────────────────────────────────

def _normalize_phone(raw: str) -> Optional[str]:
    """
    Normalise to E.164 format (digits only, no leading +).
    Returns None if the number is structurally invalid.
    Examples: '+49 151 12345678' -> '4915112345678'
              '0049 151 ...'     -> '4915112345678'
    """
    if not raw:
        return None
    # Remove formatting characters
    cleaned = re.sub(r"[\s\-\(\)]", "", raw)
    # Handle 00XX international prefix
    if cleaned.startswith("00"):
        cleaned = cleaned[2:]
    # Strip leading +
    cleaned = cleaned.lstrip("+")
    # Must be digits only after cleaning
    if not cleaned.isdigit():
        return None
    if not _PHONE_E164_RE.match(cleaned):
        return None
    return cleaned


# ── Webhook signature verification ───────────────────────────────────────────

def _verify_webhook_signature(payload_bytes: bytes, x_hub_signature_256: str) -> bool:
    """
    Verify Meta webhook payload using HMAC-SHA256.
    Header format: 'sha256=<hex_digest>'
    Requires WHATSAPP_APP_SECRET env var.
    """
    secret = _app_secret()
    if not secret:
        # If secret not configured, log warning but allow (non-strict mode)
        log.warning(
            "WHATSAPP_APP_SECRET not set — webhook signature not verified. "
            "Set this env var in production."
        )
        return True
    if not x_hub_signature_256 or not x_hub_signature_256.startswith("sha256="):
        log.warning("Missing or malformed X-Hub-Signature-256 header")
        return False
    expected = hmac.new(
        secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()
    received = x_hub_signature_256[len("sha256="):]
    return hmac.compare_digest(expected, received)


# ── Internal HTTP helper ──────────────────────────────────────────────────────

async def _wa_post(endpoint: str, payload: Dict, retries: int = 3) -> Dict:
    """POST to WhatsApp Cloud API with retry on 429/500/503."""
    if not HAS_AIOHTTP:
        return {"error": "aiohttp not installed"}
    if not _is_configured():
        return {"error": "WHATSAPP_TOKEN / WHATSAPP_PHONE_ID not configured"}
    url = f"{_WA_BASE}/{_phone_id()}/{endpoint}"
    backoff = 1.0
    for attempt in range(1, retries + 1):
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
                    if resp.status in (429, 500, 503):
                        log.warning(
                            "WhatsApp API %s %s (attempt %s/%s), retrying in %.0fs",
                            resp.status, endpoint, attempt, retries, backoff,
                        )
                        if attempt < retries:
                            await asyncio.sleep(backoff)
                            backoff *= 2
                            continue
                    if resp.status not in (200, 201):
                        log.warning("WhatsApp API %s %s: %s", resp.status, endpoint, data)
                    return data
        except aiohttp.ClientError as exc:
            log.warning("WhatsApp POST network error (attempt %s/%s): %s", attempt, retries, exc)
            if attempt < retries:
                await asyncio.sleep(backoff)
                backoff *= 2
        except Exception as exc:
            log.error("WhatsApp POST unexpected error: %s", exc)
            return {"error": str(exc)}
    return {"error": f"WhatsApp API unreachable after {retries} attempts"}


# ── Supabase stats persistence ────────────────────────────────────────────────

def _supa_optional():
    """Return supabase client or None (never raises)."""
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client  # type: ignore
        return create_client(url, key)
    except Exception:
        return None


async def _persist_stats(stats_snapshot: Dict) -> None:
    """Save WhatsApp stats to Supabase for persistence across restarts."""
    client = _supa_optional()
    if not client:
        return
    try:
        today = str(date.today())
        client.table("whatsapp_stats").upsert(
            {"date": today, **stats_snapshot},
            on_conflict="date",
        ).execute()
    except Exception as exc:
        log.debug("_persist_stats: %s", exc)


async def _load_stats() -> Dict:
    """Load today's WhatsApp stats from Supabase (for recovery after restart)."""
    client = _supa_optional()
    if not client:
        return {}
    try:
        today = str(date.today())
        result = client.table("whatsapp_stats").select("*").eq("date", today).execute()
        if result.data:
            return result.data[0]
    except Exception as exc:
        log.debug("_load_stats: %s", exc)
    return {}


# ── In-memory stats counter ────────────────────────────────────────────────────

_stats: Dict[str, int] = {
    "sent_today": 0,
    "received_today": 0,
    "sent_month": 0,
    "received_month": 0,
}
_stats_date = str(date.today())
_stats_initialized = False


async def _ensure_stats_loaded() -> None:
    """Lazy-load persisted stats on first use."""
    global _stats_initialized, _stats, _stats_date
    if _stats_initialized:
        return
    _stats_initialized = True
    persisted = await _load_stats()
    if persisted:
        _stats["sent_today"]     = int(persisted.get("sent_today", 0))
        _stats["received_today"] = int(persisted.get("received_today", 0))
        _stats["sent_month"]     = int(persisted.get("sent_month", 0))
        _stats["received_month"] = int(persisted.get("received_month", 0))
        log.info("WhatsApp stats restored from Supabase: %s", _stats)


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
                    log.warning("Claude reply API %s", resp.status)
                    return "Entschuldigung, ich konnte Ihre Anfrage nicht verarbeiten."
                data = await resp.json()
                return data["content"][0]["text"]
    except aiohttp.ClientError as exc:
        log.warning("Claude reply network error: %s", exc)
        return "Entschuldigung, ein Netzwerkfehler ist aufgetreten."
    except Exception as exc:
        log.error("Claude reply error: %s", exc)
        return "Entschuldigung, ein Fehler ist aufgetreten."


# ── Public API ────────────────────────────────────────────────────────────────

async def send_message(to_number: str, message: str) -> bool:
    """Sendet eine WhatsApp-Textnachricht. Validiert Telefonnummer (E.164)."""
    if not to_number or not message:
        return False
    if not message.strip():
        log.warning("send_message: empty message body")
        return False

    number = _normalize_phone(to_number)
    if number is None:
        log.warning(
            "send_message: invalid phone number '%s' — must be E.164 format (e.g. +4915112345678)",
            to_number,
        )
        return False

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
    log.info("WhatsApp message sent to %s (%d chars)", number, len(message))
    return True


async def send_template_message(
    to_number: str, template_name: str, params: List[str]
) -> bool:
    """Sendet eine vorgenehmigte WhatsApp Template-Nachricht."""
    if not to_number or not template_name:
        return False
    number = _normalize_phone(to_number)
    if number is None:
        log.warning("send_template_message: invalid phone number '%s'", to_number)
        return False
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
    log.info("WhatsApp template '%s' sent to %s", template_name, number)
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
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
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

    Unterstützte Nachrichtentypen:
    - text:  Kommandos (umsatz, bestellungen, hilfe) oder Claude AI
    - image/sticker/audio/video/document: freundliche Rückmeldung
    Kommandos: 'umsatz', 'bestellungen', 'hilfe' — sonst Claude AI.
    """
    await _ensure_stats_loaded()
    _bump_received()

    msg_type = data.get("type", "text")
    from_number = data.get("from", "")

    # Handle non-text message types gracefully
    if msg_type != "text":
        log.info(
            "Received non-text WhatsApp message type '%s' from %s", msg_type, from_number
        )
        type_hints = {
            "image": "Ihr Bild",
            "sticker": "Ihren Sticker",
            "audio": "Ihre Sprachnachricht",
            "video": "Ihr Video",
            "document": "Ihr Dokument",
        }
        label = type_hints.get(msg_type, f"'{msg_type}'-Nachricht")
        reply = (
            f"Ich habe {label} erhalten, kann aber nur Text verarbeiten. "
            "Bitte schreiben Sie Ihre Anfrage als Text. "
            "Tippen Sie 'hilfe' für verfügbare Kommandos."
        )
        if from_number:
            await send_message(from_number, reply)
        return reply

    text = str(data.get("text", {}).get("body", "")).strip()
    text_lower = text.lower()

    if text_lower in ("umsatz", "revenue", "einnahmen"):
        try:
            from modules.revenue_aggregator import get_daily_report  # type: ignore
            report = await get_daily_report()
            reply = f"Revenue-Übersicht:\n{report}"
        except Exception as exc:
            log.warning("handle_incoming_message: revenue fetch error: %s", exc)
            reply = f"Revenue-Daten nicht verfügbar: {exc}"

    elif text_lower in ("bestellungen", "orders", "bestellung"):
        try:
            shopify_token  = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
            shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
            if shopify_token and shopify_domain and HAS_AIOHTTP:
                base = (
                    f"https://{shopify_domain}"
                    if not shopify_domain.startswith("http")
                    else shopify_domain
                )
                api_version = os.getenv("SHOPIFY_API_VERSION", "2024-10")
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as s:
                    async with s.get(
                        f"{base}/admin/api/{api_version}/orders.json?limit=5&status=any",
                        headers={"X-Shopify-Access-Token": shopify_token},
                    ) as resp:
                        od = await resp.json(content_type=None)
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
        except aiohttp.ClientError as exc:
            log.warning("handle_incoming_message: Shopify network error: %s", exc)
            reply = "Shopify-Verbindung fehlgeschlagen."
        except Exception as exc:
            log.warning("handle_incoming_message: orders fetch error: %s", exc)
            reply = f"Fehler beim Laden der Bestellungen: {exc}"

    elif text_lower in ("hilfe", "help", "commands", "?"):
        reply = (
            "SuperMegaBot WhatsApp Commands:\n"
            "umsatz — Tages-Revenue-Übersicht\n"
            "bestellungen — Letzte 5 Bestellungen\n"
            "hilfe — Diese Liste\n"
            "Alle anderen Nachrichten werden von KI beantwortet."
        )
    elif not text:
        reply = "Ich habe eine leere Nachricht erhalten. Bitte senden Sie Text oder tippen Sie 'hilfe'."
    else:
        reply = await _claude_reply(text)

    # Send reply back to sender
    if from_number and reply:
        await send_message(from_number, reply)
    return reply


async def verify_webhook(token: str, challenge: str) -> str:
    """WhatsApp Webhook Verification (GET request from Meta)."""
    if token == _verify_token():
        log.info("WhatsApp webhook verification successful")
        return challenge
    log.warning("WhatsApp webhook verification failed — token mismatch")
    return ""


async def process_webhook(
    data: Dict,
    raw_body: Optional[bytes] = None,
    signature_header: Optional[str] = None,
) -> None:
    """
    Verarbeitet eingehende WhatsApp Webhook Events.
    Supports: messages, message status updates.

    Args:
        data:             Parsed JSON body (dict)
        raw_body:         Raw request bytes for signature verification
        signature_header: Value of X-Hub-Signature-256 header
    """
    # Signature verification
    if raw_body is not None and signature_header is not None:
        if not _verify_webhook_signature(raw_body, signature_header):
            log.warning("process_webhook: signature verification FAILED — request rejected")
            return
    elif raw_body is not None or signature_header is not None:
        # One provided but not the other — warn but don't block
        log.warning(
            "process_webhook: partial signature info (raw_body=%s, sig=%s) — skipping verification",
            raw_body is not None, signature_header is not None,
        )

    try:
        entry = (data.get("entry") or [{}])[0]
        changes = entry.get("changes") or []
        for change in changes:
            value = change.get("value", {})
            # Incoming messages
            for msg in value.get("messages") or []:
                await handle_incoming_message(msg)
            # Status updates (delivered, read, failed)
            for status in value.get("statuses") or []:
                log.info(
                    "WhatsApp message %s status: %s (recipient: %s)",
                    status.get("id"), status.get("status"), status.get("recipient_id"),
                )
    except Exception as exc:
        log.error("process_webhook error: %s", exc)


async def get_whatsapp_stats() -> Dict:
    """Returns message stats for today and this month. Restores from Supabase if restarted."""
    await _ensure_stats_loaded()
    return {
        "configured": _is_configured(),
        "phone_id": _phone_id() or None,
        "sent_today": _stats["sent_today"],
        "received_today": _stats["received_today"],
        "sent_month": _stats["sent_month"],
        "received_month": _stats["received_month"],
        "stats_date": _stats_date,
        "persisted": _supa_optional() is not None,
    }


async def broadcast_to_subscribers(
    message: str, subscriber_numbers: List[str]
) -> Dict:
    """
    Sendet eine Broadcast-Nachricht an alle angegebenen WhatsApp-Nummern.
    Respektiert WhatsApp Rate-Limit (1000 msg/s burst; wir nutzen 100 msg/s für Sicherheit).
    Ungültige Nummern werden übersprungen und geloggt.
    Returns: {"sent": 5, "failed": 1, "skipped_invalid": 1, "total": 7}
    """
    if not message or not subscriber_numbers:
        return {"sent": 0, "failed": 0, "skipped_invalid": 0, "total": 0}

    sent = 0
    failed = 0
    skipped_invalid = 0

    log.info("broadcast_to_subscribers: sending to %s numbers", len(subscriber_numbers))

    for number in subscriber_numbers:
        # Validate phone before attempting send
        normalized = _normalize_phone(number)
        if normalized is None:
            log.warning("broadcast_to_subscribers: invalid number '%s' — skipping", number)
            skipped_invalid += 1
            continue

        ok = await send_message(number, message)
        if ok:
            sent += 1
        else:
            failed += 1

        # Respect Meta rate limits: ~100 msg/s (conservative)
        await asyncio.sleep(_BROADCAST_DELAY_S)

    log.info(
        "Broadcast complete: %s sent, %s failed, %s skipped (invalid) / %s total",
        sent, failed, skipped_invalid, len(subscriber_numbers),
    )
    # Persist updated stats after large broadcast
    await _persist_stats({
        "sent_today": _stats["sent_today"],
        "received_today": _stats["received_today"],
        "sent_month": _stats["sent_month"],
        "received_month": _stats["received_month"],
    })
    return {
        "sent": sent,
        "failed": failed,
        "skipped_invalid": skipped_invalid,
        "total": len(subscriber_numbers),
    }
