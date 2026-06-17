"""
Central Slack notification module for SuperMegaBot.
Uses SLACK_WEBHOOK_URL (preferred) or falls back to SLACK_MCP_TOKEN via Web API.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from typing import Optional

log = logging.getLogger("slack_notify")

LEVEL_COLORS = {
    "info":    "#36a64f",
    "warning": "#ffcc00",
    "error":   "#cc0000",
    "revenue": "#00cc66",
    "ops":     "#0099ff",
}

LEVEL_EMOJI = {
    "info":    "ℹ️",
    "warning": "⚠️",
    "error":   "🔴",
    "revenue": "💰",
    "ops":     "⚙️",
}

DEFAULT_CHANNEL = os.getenv("SLACK_DEFAULT_CHANNEL", "#general")


def _get_webhook_url() -> str:
    url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    return url if url.startswith("https://hooks.slack.com/") else ""


def _get_bot_token() -> str:
    # xoxb- tokens for chat.postMessage; xoxe-1- (MCP/OAuth) also work
    for key in ("SLACK_BOT_TOKEN_XOXB", "SLACK_BOT_TOKEN"):
        t = os.getenv(key, "").strip()
        if t.startswith("xoxb-"):
            return t
    # Fall back to MCP token (xoxe-1- OAuth token) — works for chat.postMessage
    mcp = os.getenv("SLACK_MCP_TOKEN", "").strip()
    if mcp.startswith("xoxe-"):
        return mcp
    return ""


async def send_slack(
    message: str,
    channel: Optional[str] = None,
    emoji: str = "",
    level: str = "info",
) -> bool:
    """
    Send a Slack notification. Returns True on success.
    Tries webhook URL first, then Bot/OAuth token.
    """
    ch = channel or DEFAULT_CHANNEL
    color = LEVEL_COLORS.get(level, "#36a64f")
    icon = emoji or LEVEL_EMOJI.get(level, "")
    text = f"{icon} {message}".strip()

    webhook_url = _get_webhook_url()
    bot_token = _get_bot_token()

    if not webhook_url and not bot_token:
        log.warning("Slack: no SLACK_WEBHOOK_URL or bot token configured — message dropped")
        return False

    payload_webhook = {
        "channel": ch,
        "attachments": [{
            "color": color,
            "text": text,
            "footer": "SuperMegaBot",
            "ts": int(time.time()),
        }],
    }

    payload_api = {
        "channel": ch,
        "attachments": [{
            "color": color,
            "text": text,
            "footer": "SuperMegaBot",
            "ts": int(time.time()),
        }],
    }

    try:
        import aiohttp
    except ImportError:
        log.error("aiohttp not installed — cannot send Slack message")
        return False

    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as session:
                if webhook_url:
                    async with session.post(
                        webhook_url,
                        json=payload_webhook,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        if r.status == 200:
                            return True
                        body = await r.text()
                        log.warning("Slack webhook attempt %d: HTTP %s — %s", attempt + 1, r.status, body[:100])

                elif bot_token:
                    headers = {
                        "Authorization": f"Bearer {bot_token}",
                        "Content-Type": "application/json",
                    }
                    async with session.post(
                        "https://slack.com/api/chat.postMessage",
                        json=payload_api,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        data = await r.json()
                        if data.get("ok"):
                            return True
                        log.warning("Slack API attempt %d: %s", attempt + 1, data.get("error", "unknown"))

        except Exception as exc:
            log.warning("Slack send attempt %d failed: %s", attempt + 1, exc)

        if attempt < 2:
            await asyncio.sleep(2 ** attempt)

    return False


def send_slack_sync(message: str, channel: Optional[str] = None, level: str = "info") -> bool:
    """Synchronous wrapper for non-async contexts."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # In async context — schedule as task
            asyncio.ensure_future(send_slack(message, channel, level=level))
            return True
        return loop.run_until_complete(send_slack(message, channel, level=level))
    except Exception as exc:
        log.error("send_slack_sync error: %s", exc)
        return False


# Convenience shortcuts
async def slack_error(msg: str, channel: str = "#errors") -> bool:
    return await send_slack(msg, channel=channel, level="error")

async def slack_revenue(msg: str, channel: str = "#revenue") -> bool:
    return await send_slack(msg, channel=channel, level="revenue")

async def slack_ops(msg: str, channel: str = "#ops") -> bool:
    return await send_slack(msg, channel=channel, level="ops")
