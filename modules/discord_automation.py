#!/usr/bin/env python3
"""
Discord Automation — SuperMegaBot
==================================
Postet automatisch auf Discord via Webhook + BRUTUS Integration.

Setup: Gehe in deinen Discord-Server → Kanal → Einstellungen → Integrationen
→ Webhooks → Webhook erstellen → URL kopieren → in .env als DISCORD_WEBHOOK_URL setzen.
"""
import asyncio
import logging
import os
import aiohttp
from datetime import datetime, timezone

log = logging.getLogger("DiscordAuto")

DISCORD_WEBHOOK  = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_BOT_TOK  = os.getenv("DISCORD_BOT_TOKEN", "")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT    = os.getenv("TELEGRAM_CHAT_ID", "")
DS24_LINK        = "https://www.digistore24.com/redir/669750/user37405262/"
PERPLEXITY_KEY   = os.getenv("PERPLEXITY_API_KEY", "")
ANTHROPIC_KEY    = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY       = os.getenv("OPENAI_API_KEY", "")


async def _ai(prompt: str) -> str:
    """AI with full fallback chain via central ai_complete."""
    try:
        from modules.ai_client import ai_complete
        result = await ai_complete(prompt, max_tokens=350)
        if result:
            return result
    except Exception:
        pass
    return "🚀 E-Commerce Automation auf Autopilot — DS24 Affiliate + Shopify + AI!"


async def post_webhook(content: str, embeds: list = None) -> bool:
    """Post to Discord channel via webhook."""
    if not DISCORD_WEBHOOK:
        log.warning("DISCORD_WEBHOOK_URL not set — skip")
        return False
    payload = {"content": content[:2000]}
    if embeds:
        payload["embeds"] = embeds
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                DISCORD_WEBHOOK,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status in (200, 204):
                    return True
                log.error("Discord webhook %s: %s", r.status, await r.text())
                return False
    except Exception as e:
        log.error("Discord webhook error: %s", e)
        return False


async def post_rich_embed(title: str, description: str, url: str = "", color: int = 0xe63946) -> bool:
    """Post a rich embed card to Discord."""
    embed = {
        "title": title[:256],
        "description": description[:4096],
        "color": color,
        "url": url or DS24_LINK,
        "footer": {"text": "SuperMegaBot Automation • " + datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")},
    }
    return await post_webhook("", embeds=[embed])


async def run_discord_promo() -> dict:
    """Generate and post a DS24 promo to Discord."""
    if not DISCORD_WEBHOOK:
        return {"ok": False, "error": "DISCORD_WEBHOOK_URL not configured. Add webhook URL to .env"}

    prompt = (
        "Schreibe einen kurzen Discord-Beitrag (max 300 Zeichen) auf Deutsch über "
        "E-Commerce Automation und passive Einnahmen. Direkt, motivierend, emoji. "
        "Kein Link einfügen — das wird separat hinzugefügt."
    )
    body = await _ai(prompt)

    msg = f"🚀 **E-Commerce Automation**\n\n{body}\n\n👉 {DS24_LINK}"
    ok = await post_webhook(msg)

    if not ok:
        ok = await post_rich_embed(
            title="🚀 E-Commerce Automation auf Autopilot",
            description=body,
            url=DS24_LINK,
        )

    return {"ok": ok, "chars": len(body), "ts": datetime.now(timezone.utc).isoformat()}


async def run_discord_revenue_report(orders: int = 0, revenue: float = 0.0) -> dict:
    """Post a revenue report embed to Discord."""
    if not DISCORD_WEBHOOK:
        return {"ok": False, "error": "DISCORD_WEBHOOK_URL not set"}

    embed = {
        "title": f"💰 Revenue Update — {datetime.now(timezone.utc).strftime('%d.%m.%Y')}",
        "color": 0x2ecc71,
        "fields": [
            {"name": "💼 Orders", "value": str(orders), "inline": True},
            {"name": "💶 Revenue", "value": f"€{revenue:.2f}", "inline": True},
            {"name": "🤖 Automationen", "value": "149 aktiv", "inline": True},
            {"name": "🔥 DS24 Affiliate", "value": DS24_LINK, "inline": False},
        ],
        "footer": {"text": "SuperMegaBot • Railway Production"},
    }
    ok = await post_webhook("", embeds=[embed])
    return {"ok": ok}


async def run_discord_brutus_blast(topic: str = "E-Commerce Automation") -> dict:
    """Use Discord as a BRUTUS channel — post content about topic with affiliate."""
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        r = await run_brutus_swarm(niche=topic, affiliate_url=DS24_LINK)
        return {"brutus": r, "discord_ok": False, "note": "BRUTUS ran — Discord needs webhook URL"}
    except Exception as e:
        promo = await run_discord_promo()
        return {"brutus_error": str(e), "discord_ok": promo.get("ok")}


def get_invite_url() -> str:
    """Generate bot invite URL for Rudolf to add bot to server."""
    client_id = os.getenv("DISCORD_CLIENT_ID", "1515460691664965672")
    perms = 2048 + 16384  # Send Messages + Read Messages
    return (
        f"https://discord.com/api/oauth2/authorize?"
        f"client_id={client_id}&permissions={perms}&scope=bot"
    )
