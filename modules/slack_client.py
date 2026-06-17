"""
Slack integration for SuperMegaBot.
Supports:
  - Incoming Webhooks (SLACK_WEBHOOK_URL) — simplest, no bot token needed
  - Bot API (SLACK_BOT_TOKEN = xoxb-...) — for channel posting + more
Falls back to Telegram if no Slack is configured.
Events are persisted to Supabase hermes_events table.
"""
import logging
import os
import time
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_DEFAULT_CHANNEL = os.getenv("SLACK_DEFAULT_CHANNEL", "#general")
SLACK_API_BASE = "https://slack.com/api"

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")

_SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Accept-Profile": "public",
    "Content-Profile": "public",
    "Prefer": "return=minimal",
}


async def _post_webhook(text: str, blocks: Optional[list] = None) -> bool:
    if not SLACK_WEBHOOK_URL:
        return False
    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SLACK_WEBHOOK_URL, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as r:
                ok = r.status == 200
                if not ok:
                    logger.warning("Slack webhook returned %s", r.status)
                return ok
    except Exception as exc:
        logger.error("Slack webhook error: %s", exc)
        return False


async def _post_bot_api(text: str, channel: str, blocks: Optional[list] = None) -> bool:
    token = SLACK_BOT_TOKEN
    if not token or not token.startswith("xoxb-"):
        return False
    payload = {"channel": channel, "text": text}
    if blocks:
        payload["blocks"] = blocks
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{SLACK_API_BASE}/chat.postMessage",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                data = await r.json()
                if not data.get("ok"):
                    logger.warning("Slack API error: %s", data.get("error"))
                return bool(data.get("ok"))
    except Exception as exc:
        logger.error("Slack API error: %s", exc)
        return False


async def _tg_fallback(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                return r.status == 200
    except Exception:
        return False


async def _persist_event(service: str, event_type: str, message: str,
                          channel: str, metadata: dict,
                          slack_ok: bool, tg_ok: bool) -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    row = {
        "service": service,
        "event_type": event_type,
        "channel": channel,
        "message": message,
        "metadata": metadata or {},
        "notified_slack": slack_ok,
        "notified_telegram": tg_ok,
    }
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"{SUPABASE_URL}/rest/v1/hermes_events",
                json=row,
                headers=_SB_HEADERS,
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception as exc:
        logger.debug("hermes_events persist failed: %s", exc)


async def push_event(
    service: str,
    event_type: str,
    message: str,
    channel: str = "general",
    metadata: Optional[dict] = None,
) -> bool:
    """
    Push event to Supabase hermes_events + notify Slack (falls back to Telegram).
    Always returns without raising.
    """
    slack_ok = False
    tg_ok = False
    try:
        ch = f"#{channel}" if not channel.startswith("#") else channel
        slack_ok = await _post_webhook(message)
        if not slack_ok:
            slack_ok = await _post_bot_api(message, ch)
        if not slack_ok:
            tg_ok = await _tg_fallback(message)
    except Exception as exc:
        logger.error("push_event delivery error: %s", exc)
    try:
        await _persist_event(service, event_type, message, channel,
                             metadata or {}, slack_ok, tg_ok)
    except Exception as exc:
        logger.debug("push_event persist error: %s", exc)
    return slack_ok or tg_ok


async def notify(
    text: str,
    channel: Optional[str] = None,
    blocks: Optional[list] = None,
    emoji: str = "robot_face",
) -> bool:
    ch = channel or SLACK_DEFAULT_CHANNEL
    prefixed = f":{emoji}: {text}"
    sent = await _post_webhook(prefixed, blocks)
    if sent:
        return True
    sent = await _post_bot_api(prefixed, ch, blocks)
    if sent:
        return True
    logger.info("[Slack] No delivery method configured. Message: %s", text)
    return False


async def notify_revenue(amount_eur: float, source: str, detail: str = "") -> bool:
    text = f"*Neue Einnahme!* €{amount_eur:.2f} via {source}"
    if detail:
        text += f"\n{detail}"
    return await notify(text, emoji="money_with_wings")


async def notify_error(service: str, error: str) -> bool:
    return await notify(f"*Fehler in {service}*: {error}", emoji="red_circle")


async def notify_deploy(service: str, url: str, status: str = "live") -> bool:
    return await notify(
        f"*Deploy {status.upper()}* — {service}\n{url}", emoji="rocket"
    )


async def verify_credentials() -> dict:
    result = {"webhook": False, "bot_api": False, "method": None}

    if SLACK_WEBHOOK_URL:
        ok = await _post_webhook(":white_check_mark: SuperMegaBot Slack-Verbindung OK")
        result["webhook"] = ok
        if ok:
            result["method"] = "webhook"

    if SLACK_BOT_TOKEN and SLACK_BOT_TOKEN.startswith("xoxb-"):
        ok = await _post_bot_api(
            ":white_check_mark: SuperMegaBot Bot-API OK",
            SLACK_DEFAULT_CHANNEL,
        )
        result["bot_api"] = ok
        if ok and not result["method"]:
            result["method"] = "bot_api"

    if not result["method"]:
        result["error"] = (
            "Kein funktionierender Slack-Kanal. "
            "Setze SLACK_WEBHOOK_URL oder SLACK_BOT_TOKEN=xoxb-..."
        )

    return result
