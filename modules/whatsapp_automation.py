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
WA_VERSION     = "v18.0"
WA_BASE        = f"https://graph.facebook.com/{WA_VERSION}"

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


async def process_webhook(data: dict) -> None:
    """Handle incoming WhatsApp messages (status updates, texts)."""
    stats = _load_stats()
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    stats["received"] += 1
                    log.info(
                        "WA incoming: from=%s type=%s",
                        msg.get("from"), msg.get("type"),
                    )
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


async def get_whatsapp_stats() -> dict:
    stats = _load_stats()
    return {
        "configured": bool(WA_PHONE_ID and WA_TOKEN),
        "phone_number_id": WA_PHONE_ID or "not set",
        "messages_sent": stats.get("sent", 0),
        "messages_received": stats.get("received", 0),
        "messages_failed": stats.get("failed", 0),
        "verify_token_set": bool(WA_VERIFY_TOKEN),
    }


async def send_whatsapp_blast(message: str) -> dict:
    """Broadcast a message to all configured WhatsApp recipients (WHATSAPP_TO_NUMBERS env, comma-separated)."""
    numbers_raw = os.getenv("WHATSAPP_TO_NUMBERS", os.getenv("WHATSAPP_DEFAULT_TO", ""))
    numbers = [n.strip() for n in numbers_raw.split(",") if n.strip()]
    if not numbers:
        log.warning("send_whatsapp_blast: no WHATSAPP_TO_NUMBERS configured")
        return {"ok": False, "error": "WHATSAPP_TO_NUMBERS not set", "sent": 0}
    result = await broadcast_to_subscribers(message, numbers)
    result["ok"] = result.get("sent", 0) > 0
    return result
