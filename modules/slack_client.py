"""
Slack integration for SuperMegaBot.
Supports:
  - Incoming Webhooks (SLACK_WEBHOOK_URL) — simplest, no bot token needed
  - Bot API (SLACK_BOT_TOKEN = xoxb-...) — for channel posting + more
  - rudibot-1 Socket Mode is separate; wire via RUDIBOT_API_URL if needed
"""
import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")  # must be xoxb-
SLACK_DEFAULT_CHANNEL = os.getenv("SLACK_DEFAULT_CHANNEL", "#general")
SLACK_API_BASE = "https://slack.com/api"


async def _post_webhook(text: str, blocks: Optional[list] = None) -> bool:
    if not SLACK_WEBHOOK_URL:
        return False
    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SLACK_WEBHOOK_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
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
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json()
                if not data.get("ok"):
                    logger.warning("Slack API error: %s", data.get("error"))
                return bool(data.get("ok"))
    except Exception as exc:
        logger.error("Slack API error: %s", exc)
        return False


async def notify(
    text: str,
    channel: Optional[str] = None,
    blocks: Optional[list] = None,
    emoji: str = "robot_face",
) -> bool:
    """
    Send a notification to Slack. Tries webhook first, then bot API.
    Returns True if delivered successfully.
    """
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
            "Setze SLACK_WEBHOOK_URL (einfachste Option) oder "
            "SLACK_BOT_TOKEN=xoxb-... + SLACK_DEFAULT_CHANNEL=#kanal"
        )

    return result
