"""
WhatsApp Business Cloud API Automation
=======================================
Handles Meta WhatsApp webhook verification, message receiving,
sending text messages, and broadcasting to subscriber lists.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("WhatsAppAutomation")

WA_PHONE_ID    = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WA_TOKEN       = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WA_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "bullpower_wa_verify_2026")
WA_VERSION     = os.getenv("WA_API_VERSION", "v21.0")
WA_BASE        = f"https://graph.facebook.com/{WA_VERSION}"

# Internal dashboard URL for routing incoming messages to the CommandRouter
DASHBOARD_BASE_URL = os.getenv("DASHBOARD_BASE_URL", "http://localhost:8888")

DATA_DIR       = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
STATS_FILE     = DATA_DIR / "whatsapp_stats.json"

_stats = {"sent": 0, "received": 0, "failed": 0, "subscribers": 0}


def _load_stats() -> dict:
    try:
        return json.loads(STATS_FILE.read_text())
    except Exception:
        return {"sent": 0, "received": 0, "failed": 0, "subscribers": 0}


def _save_stats(s: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(json.dumps(s, indent=2))


async def verify_webhook(token: str, challenge: str) -> str | None:
    """Meta webhook verification — return challenge if token matches."""
    if token == WA_VERIFY_TOKEN:
        log.info("WhatsApp webhook verified")
        return challenge
    log.warning("WhatsApp webhook: invalid verify token '%s'", token)
    return None


async def _route_to_command_router(sender: str, text: str) -> None:
    """Forward an incoming WhatsApp text to the internal CommandRouter for auto-reply."""
    try:
        import aiohttp as _aiohttp
        payload = {
            "command": text.strip(),
            "source": "whatsapp",
            "sender": sender,
        }
        async with _aiohttp.ClientSession() as session:
            async with session.post(
                f"{DASHBOARD_BASE_URL}/api/bot/execute",
                json=payload,
                timeout=_aiohttp.ClientTimeout(total=10),
            ) as resp:
                result = await resp.json(content_type=None)
                reply = result.get("result") or result.get("response") or result.get("message")
                if reply:
                    await send_message(sender, str(reply))
                    log.info("WA auto-reply sent to %s", sender)
                else:
                    log.debug("WA CommandRouter returned no reply text for sender=%s", sender)
    except Exception as exc:
        log.warning("WA _route_to_command_router error (sender=%s): %s", sender, exc)


async def process_webhook(data: dict) -> None:
    """Handle incoming WhatsApp messages and delivery/read status updates."""
    stats = _load_stats()
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # ── Incoming messages ──────────────────────────────────────────
                for msg in value.get("messages", []):
                    stats["received"] += 1
                    sender = msg.get("from", "")
                    msg_type = msg.get("type", "")
                    log.info("WA incoming: from=%s type=%s", sender, msg_type)

                    # Route text messages to CommandRouter for auto-reply
                    if msg_type == "text" and sender:
                        text_body = (msg.get("text") or {}).get("body", "").strip()
                        if text_body:
                            import asyncio
                            asyncio.ensure_future(_route_to_command_router(sender, text_body))

                # ── Delivery / read receipts (statuses) ───────────────────────
                for status in value.get("statuses", []):
                    msg_id = status.get("id", "")
                    status_val = status.get("status", "")
                    recipient = status.get("recipient_id", "")
                    log.info(
                        "WA status update: msg_id=%s status=%s recipient=%s",
                        msg_id, status_val, recipient,
                    )
                    # Optionally track delivered/read per message in stats
                    if status_val in ("delivered", "read"):
                        stats.setdefault(f"status_{status_val}", 0)
                        stats[f"status_{status_val}"] += 1

        _save_stats(stats)
    except Exception as e:
        log.warning("WhatsApp process_webhook error: %s", e)


async def send_message(to: str, message: str) -> bool:
    """Send a WhatsApp text message via Cloud API."""
    if not WA_PHONE_ID or not WA_TOKEN:
        log.warning("WhatsApp not configured — missing WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_ACCESS_TOKEN")
        return False
    try:
        import aiohttp
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to.lstrip("+"),
            "type": "text",
            "text": {"preview_url": False, "body": message[:4096]},
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{WA_BASE}/{WA_PHONE_ID}/messages",
                headers={"Authorization": f"Bearer {WA_TOKEN}",
                         "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
                ok = "messages" in data
                stats = _load_stats()
                if ok:
                    stats["sent"] += 1
                    log.info("WA sent → %s", to)
                else:
                    stats["failed"] += 1
                    log.warning("WA send failed → %s: %s", to, data)
                _save_stats(stats)
                return ok
    except Exception as e:
        log.warning("WhatsApp send_message error: %s", e)
        stats = _load_stats()
        stats["failed"] += 1
        _save_stats(stats)
        return False


async def broadcast_to_subscribers(message: str, numbers: list[str]) -> dict:
    """Broadcast a message to multiple WhatsApp numbers."""
    sent = 0
    failed = 0
    for number in numbers:
        ok = await send_message(number, message)
        if ok:
            sent += 1
        else:
            failed += 1
    return {
        "total": len(numbers),
        "sent": sent,
        "failed": failed,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def send_via_twilio_whatsapp(to: str, message: str) -> bool:
    """Fallback: send WhatsApp message via Twilio (Sandbox or approved number)."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_wa     = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")  # Twilio sandbox default
    if not account_sid or not auth_token:
        return False
    to_wa = f"whatsapp:{to}" if not to.startswith("whatsapp:") else to
    try:
        import aiohttp
        import base64
        creds = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
                headers={"Authorization": f"Basic {creds}"},
                data={"From": from_wa, "To": to_wa, "Body": message[:1600]},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        ok = d.get("status") not in ("failed", "undelivered") and "sid" in d
        log.info("Twilio WA → %s: %s", to, d.get("status", "?"))
        return ok
    except Exception as e:
        log.warning("Twilio WhatsApp error: %s", e)
        return False


async def get_whatsapp_stats() -> dict:
    stats = _load_stats()
    return {
        "configured": bool(WA_PHONE_ID and WA_TOKEN),
        "twilio_fallback": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        "phone_number_id": WA_PHONE_ID or "not set",
        "messages_sent": stats.get("sent", 0),
        "messages_received": stats.get("received", 0),
        "messages_failed": stats.get("failed", 0),
        "verify_token_set": bool(WA_VERIFY_TOKEN),
    }


async def send_whatsapp_blast(message: str) -> dict:
    """Broadcast via Meta WhatsApp Cloud API; Twilio fallback if unconfigured."""
    numbers_raw = os.getenv("WHATSAPP_TO_NUMBERS", os.getenv("WHATSAPP_DEFAULT_TO",
                             os.getenv("TWILIO_VERIFIED_TO", "")))
    numbers = [n.strip() for n in numbers_raw.split(",") if n.strip()]
    if not numbers:
        log.warning("send_whatsapp_blast: no recipients configured")
        return {"ok": False, "error": "no recipients in WHATSAPP_TO_NUMBERS or TWILIO_VERIFIED_TO", "sent": 0}

    if WA_PHONE_ID and WA_TOKEN:
        result = await broadcast_to_subscribers(message, numbers)
    else:
        # Twilio WhatsApp fallback
        sent = 0
        for num in numbers:
            if await send_via_twilio_whatsapp(num, message):
                sent += 1
        result = {"total": len(numbers), "sent": sent, "failed": len(numbers) - sent,
                  "via": "twilio", "ts": datetime.now(timezone.utc).isoformat()}

    result["ok"] = result.get("sent", 0) > 0
    return result
