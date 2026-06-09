#!/usr/bin/env python3
"""Webhook Handler — Real-time event processing for Shopify, Printify, Digistore24"""
import hashlib
import hmac
import json
import logging
import os
from typing import Awaitable, Callable, Dict, List

log = logging.getLogger("Webhooks")

# ---------------------------------------------------------------------------
# Core handler class
# ---------------------------------------------------------------------------

class WebhookHandler:
    """
    Register async callbacks for webhook events and dispatch them when
    incoming payloads are received from Shopify, Printify, or Digistore24.
    """

    def __init__(self):
        self._shopify_secret: str = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
        self._handlers: Dict[str, List[Callable]] = {}

    # ── Handler registry ────────────────────────────────────────────────────

    def on(self, event: str, fn: Callable[..., Awaitable]) -> None:
        """Register an async handler for *event*."""
        self._handlers.setdefault(event, []).append(fn)

    async def emit(self, event: str, data: Dict) -> None:
        """
        Call every handler registered for *event* in order.
        Exceptions in individual handlers are logged but do not abort others.
        """
        handlers = self._handlers.get(event, [])
        if not handlers:
            log.debug("No handlers registered for event: %s", event)
            return
        for fn in handlers:
            try:
                await fn(data)
            except Exception as exc:
                log.error("Handler error for event '%s': %s", event, exc)

    # ── Platform-specific processors ────────────────────────────────────────

    async def process_shopify(self, headers: Dict, body: bytes) -> bool:
        """
        Verify HMAC-SHA256 signature and dispatch the Shopify event.

        Headers expected:
          X-Shopify-Hmac-Sha256  — base64-encoded HMAC
          X-Shopify-Topic        — e.g. "orders/create"

        Returns True if signature valid and event dispatched, False otherwise.
        """
        import base64

        if self._shopify_secret:
            signature_header = headers.get(
                "X-Shopify-Hmac-Sha256",
                headers.get("x-shopify-hmac-sha256", "")
            )
            if not signature_header:
                log.warning("Shopify webhook: missing HMAC header")
                return False

            expected_mac = hmac.new(
                self._shopify_secret.encode("utf-8"),
                body,
                hashlib.sha256,
            ).digest()
            try:
                provided_mac = base64.b64decode(signature_header)
            except Exception:
                log.warning("Shopify webhook: invalid base64 in HMAC header")
                return False

            if not hmac.compare_digest(expected_mac, provided_mac):
                log.warning("Shopify webhook: HMAC verification failed")
                return False

        topic = headers.get(
            "X-Shopify-Topic",
            headers.get("x-shopify-topic", "unknown/unknown")
        )
        # Normalise "orders/create" → "shopify/orders/create"
        event = f"shopify/{topic}" if not topic.startswith("shopify/") else topic

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            log.error("Shopify webhook: could not parse body JSON: %s", exc)
            return False

        log.info("Shopify webhook received: %s", event)
        await self.emit(event, data)
        return True

    async def process_printify(self, body: Dict) -> bool:
        """
        Parse a Printify webhook payload and dispatch the matching event.

        Expected keys: type (e.g. "order:fulfilled"), data {}

        Returns True if event recognised and dispatched.
        """
        raw_type = body.get("type", "")
        if not raw_type:
            log.warning("Printify webhook: missing 'type' field")
            return False

        # Map Printify types to internal events
        event_map = {
            "order:fulfilled":  "printify/order/fulfilled",
            "order:cancelled":  "printify/order/cancelled",
            "order:created":    "printify/order/created",
            "order:shipment":   "printify/order/shipment",
            "product:created":  "printify/product/created",
            "product:updated":  "printify/product/updated",
        }
        event = event_map.get(raw_type, f"printify/{raw_type.replace(':', '/')}")
        data  = body.get("data", body)

        log.info("Printify webhook received: %s", event)
        await self.emit(event, data)
        return True

    async def process_digistore(self, body: Dict) -> bool:
        """
        Parse a Digistore24 IPN / webhook payload and dispatch the event.

        Expected keys: event (e.g. "order_completed"), order_id, ...

        Returns True if event recognised and dispatched.
        """
        raw_event = body.get("event", body.get("action", ""))
        if not raw_event:
            log.warning("Digistore webhook: missing 'event' field")
            return False

        event_map = {
            "order_completed":     "digistore/order/created",
            "order_refunded":      "digistore/order/refunded",
            "order_chargeback":    "digistore/order/chargeback",
            "subscription_new":    "digistore/subscription/created",
            "subscription_cancel": "digistore/subscription/cancelled",
            "affiliate_sale":      "digistore/affiliate/sale",
        }
        event = event_map.get(raw_event, f"digistore/{raw_event}")

        log.info("Digistore24 webhook received: %s", event)
        await self.emit(event, body)
        return True


# ---------------------------------------------------------------------------
# Module-level singleton + default handlers
# ---------------------------------------------------------------------------

_handler = WebhookHandler()


def _send_telegram(text: str) -> None:
    """Fire-and-forget Telegram notification (sync-safe)."""
    import urllib.request
    token   = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1") or os.getenv("TELEGRAM_BOT_TOKEN_2") or ""
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not (token and chat_id):
        log.debug("Telegram not configured — skipping notification")
        return
    try:
        payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=8)
    except Exception as exc:
        log.warning("Telegram notification failed: %s", exc)


async def _add_mailchimp_tag(email: str, tag: str) -> None:
    """Add a tag to a Mailchimp subscriber."""
    try:
        from modules.mailchimp_automation import add_subscriber_tag  # type: ignore
        await add_subscriber_tag(email, tag)
    except Exception as exc:
        log.warning("Mailchimp tag add failed (%s): %s", tag, exc)


# ── Default Shopify order handler ───────────────────────────────────────────

async def _on_shopify_order_telegram(data: Dict) -> None:
    """Send Telegram notification for new Shopify order."""
    order_id = data.get("name", data.get("id", "?"))
    total    = data.get("total_price", "0.00")
    currency = data.get("currency", "EUR")
    customer = data.get("customer", {})
    email    = customer.get("email", "") if isinstance(customer, dict) else ""
    name     = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip() if isinstance(customer, dict) else ""
    msg = (
        f"🛒 <b>Neue Shopify Bestellung!</b>\n"
        f"Bestellung: {order_id}\n"
        f"Betrag: {total} {currency}\n"
        f"Kunde: {name or email or 'Unbekannt'}"
    )
    _send_telegram(msg)


_handler.on("shopify/orders/create", _on_shopify_order_telegram)


async def _on_shopify_order_mailchimp(data: Dict) -> None:
    """Tag the customer in Mailchimp when a new Shopify order arrives."""
    customer = data.get("customer", {})
    email = customer.get("email", "") if isinstance(customer, dict) else ""
    if email:
        await _add_mailchimp_tag(email, "shopify-customer")


_handler.on("shopify/orders/create", _on_shopify_order_mailchimp)


# ── Default Printify fulfilled handler ──────────────────────────────────────

async def _on_printify_fulfilled(data: Dict) -> None:
    """Notify Telegram when a Printify order has been fulfilled/shipped."""
    order_id  = data.get("external_id", data.get("id", "?"))
    tracking  = data.get("carrier", "Tracking verfügbar in Bestellübersicht")
    msg = (
        f"📦 <b>Bestellung versandt!</b>\n"
        f"Printify Order: {order_id}\n"
        f"Versand via: {tracking}"
    )
    _send_telegram(msg)


_handler.on("printify/order/fulfilled", _on_printify_fulfilled)


# ── Default Digistore order handler ─────────────────────────────────────────

async def _on_digistore_order(data: Dict) -> None:
    """Telegram notification + Mailchimp welcome tag for new Digistore24 sale."""
    order_id = data.get("order_id", data.get("id", "?"))
    product  = data.get("product_name", data.get("product_title", "Produkt"))
    amount   = data.get("amount", data.get("total", "?"))
    currency = data.get("currency", "EUR")
    email    = data.get("buyer_email", data.get("email", ""))

    # Telegram
    msg = (
        f"💰 <b>Neuer Digistore24 Verkauf!</b>\n"
        f"Order: {order_id}\n"
        f"Produkt: {product}\n"
        f"Betrag: {amount} {currency}\n"
        f"Käufer: {email or 'Unbekannt'}"
    )
    _send_telegram(msg)

    # Mailchimp welcome tag
    if email:
        await _add_mailchimp_tag(email, "digistore-customer")


_handler.on("digistore/order/created", _on_digistore_order)
