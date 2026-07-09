#!/usr/bin/env python3
"""
MegaAgentOrchestrator — Multi-Plattform Koordinator
=====================================================
Koordiniert ALLE Plattform-Agenten gleichzeitig:
Klaviyo · Twilio · Mailchimp · AliExpress · eBay · Amazon
Fiverr · Upwork · TikTok · Reddit · Discord · YouTube

Jeder Agent läuft autonom — der Orchestrator teilt Trending-Topics,
koordiniert Content-Verteilung und sammelt Ergebnisse.
"""
import asyncio
import logging
import os
import json
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("MegaAgentOrchestrator")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY     = os.getenv("OPENAI_API_KEY", "")


# ── AI Helper ──────────────────────────────────────────────────────────────────

async def _ai(prompt: str, max_tokens: int = 400) -> str:
    try:
        import aiohttp
        if ANTHROPIC_KEY:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                             "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": max_tokens,
                          "messages": [{"role": "user", "content": prompt}]},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    d = await r.json(content_type=None)
                    return d.get("content", [{}])[0].get("text", "").strip()
    except Exception as e:
        log.warning("AI error: %s", e)
    return ""


async def _tg(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram error: %s", e)


# ── Trending Topics Generator ──────────────────────────────────────────────────

async def get_trending_topics() -> list[str]:
    prompt = (
        "Gib mir 5 aktuell trendende E-Commerce/Online-Business Themen auf Deutsch. "
        "Kurz und prägnant, ein Thema pro Zeile, keine Nummerierung."
    )
    text = await _ai(prompt)
    topics = [t.strip() for t in text.split("\n") if t.strip()][:5]
    if not topics:
        topics = [
            "KI-Tools für Online-Shops",
            "Dropshipping 2026 Trends",
            "Passive Einnahmen online",
            "Digitale Produkte verkaufen",
            "Affiliate Marketing Geheimtipps",
        ]
    return topics


# ── Platform Agents ────────────────────────────────────────────────────────────

async def agent_klaviyo(topics: list[str]) -> dict:
    """Klaviyo Agent — Email-Kampagne an Subscriber."""
    result = {"platform": "Klaviyo", "ok": False, "action": ""}
    try:
        from modules.klaviyo_autonomy import run_autonomy_cycle
        r = await asyncio.wait_for(run_autonomy_cycle(), timeout=30)
        result["ok"] = True
        result["action"] = f"Campaign sent — {r.get('campaigns_created', 0)} campaigns"
    except Exception as e:
        result["error"] = str(e)[:80]
        log.warning("Klaviyo agent error: %s", e)
    return result


async def agent_mailchimp(topics: list[str]) -> dict:
    """Mailchimp Agent — Newsletter-Kampagne."""
    result = {"platform": "Mailchimp", "ok": False, "action": ""}
    try:
        from modules.mailchimp_autonomy import run_autonomy_cycle
        r = await asyncio.wait_for(run_autonomy_cycle(), timeout=30)
        result["ok"] = True
        result["action"] = f"Newsletter: {r.get('campaigns_created', 0)} campaigns"
    except Exception as e:
        result["error"] = str(e)[:80]
        log.warning("Mailchimp agent error: %s", e)
    return result


async def agent_twilio(topics: list[str]) -> dict:
    """Twilio Agent — SMS-Broadcast an Opt-in Liste."""
    result = {"platform": "Twilio", "ok": False, "action": ""}
    try:
        from modules.twilio_sms_blast import run_sms_blast
        topic = topics[0] if topics else "Neue Angebote"
        r = await asyncio.wait_for(run_sms_blast(topic), timeout=20)
        result["ok"] = r.get("ok", False)
        result["action"] = f"SMS sent: {r.get('sent', 0)}"
    except Exception as e:
        result["error"] = str(e)[:80]
        log.warning("Twilio agent error: %s", e)
    return result


async def agent_aliexpress(topics: list[str]) -> dict:
    """AliExpress Agent — Trending Produkte importieren."""
    result = {"platform": "AliExpress", "ok": False, "action": ""}
    try:
        from modules.aliexpress_autonomy import run_autonomy_cycle
        r = await asyncio.wait_for(run_autonomy_cycle(), timeout=45)
        result["ok"] = True
        result["action"] = f"Imported: {r.get('imported', 0)} products"
    except Exception as e:
        result["error"] = str(e)[:80]
        log.warning("AliExpress agent error: %s", e)
    return result


async def agent_ebay(topics: list[str]) -> dict:
    """eBay Agent — Affiliate Links + Traffic Blast."""
    result = {"platform": "eBay", "ok": False, "action": ""}
    try:
        from modules.ebay_autonomy import run_autonomy_cycle
        r = await asyncio.wait_for(run_autonomy_cycle(), timeout=30)
        result["ok"] = True
        result["action"] = f"eBay blast: {r.get('posted', 0)} posts"
    except Exception as e:
        result["error"] = str(e)[:80]
        log.warning("eBay agent error: %s", e)
    return result


async def agent_amazon(topics: list[str]) -> dict:
    """Amazon Agent — Affiliate Produkte pushen."""
    result = {"platform": "Amazon", "ok": False, "action": ""}
    try:
        from modules.amazon_autonomy import run_autonomy_cycle
        r = await asyncio.wait_for(run_autonomy_cycle(), timeout=30)
        result["ok"] = True
        result["action"] = f"Amazon blast: {r.get('blasted', 0)} products"
    except Exception as e:
        result["error"] = str(e)[:80]
        log.warning("Amazon agent error: %s", e)
    return result


async def agent_fiverr(topics: list[str]) -> dict:
    """Fiverr Agent — Gigs promoten + Orders checken."""
    result = {"platform": "Fiverr", "ok": False, "action": ""}
    try:
        from modules.fiverr_sync import sync_fiverr
        r = await asyncio.wait_for(sync_fiverr(), timeout=20)
        result["ok"] = True
        result["action"] = f"Fiverr sync: {r.get('gigs', 0)} gigs active"
    except Exception as e:
        result["error"] = str(e)[:80]
        log.warning("Fiverr agent error: %s", e)
    return result


async def agent_upwork(topics: list[str]) -> dict:
    """Upwork Agent — Job-Proposals automatisch senden."""
    result = {"platform": "Upwork", "ok": False, "action": ""}
    try:
        from modules.upwork_autonomy import run_autonomy_cycle
        r = await asyncio.wait_for(run_autonomy_cycle(), timeout=30)
        result["ok"] = r.get("ok", True)
        result["action"] = f"Proposals: {r.get('proposals_sent', 0)} gesendet"
    except Exception as e:
        result["error"] = str(e)[:80]
        log.warning("Upwork agent error: %s", e)
    return result


async def agent_tiktok(topics: list[str]) -> dict:
    """TikTok Agent — Content + Shop Sync."""
    result = {"platform": "TikTok", "ok": False, "action": ""}
    try:
        from modules.tiktok_autonomy import run_tiktok_cycle
        r = await asyncio.wait_for(run_tiktok_cycle(), timeout=30)
        result["ok"] = True
        result["action"] = f"TikTok: {r.get('posts', 0)} posts, {r.get('products_synced', 0)} products"
    except Exception as e:
        result["error"] = str(e)[:80]
        log.warning("TikTok agent error: %s", e)
    return result


async def agent_reddit(topics: list[str]) -> dict:
    """Reddit Agent — Posts in relevante Subreddits."""
    result = {"platform": "Reddit", "ok": False, "action": ""}
    try:
        from modules.reddit_autoposter import auto_post_all
        topic = topics[0] if topics else "Online Business"
        r = await asyncio.wait_for(auto_post_all(topic), timeout=30)
        result["ok"] = r.get("ok", True)
        result["action"] = f"Reddit: {r.get('posted', 0)} posts"
    except Exception as e:
        result["error"] = str(e)[:80]
        log.warning("Reddit agent error: %s", e)
    return result


async def agent_discord(topics: list[str]) -> dict:
    """Discord Agent — Community Posts + Promo."""
    result = {"platform": "Discord", "ok": False, "action": ""}
    try:
        from modules.discord_automation import post_promo
        topic = topics[0] if topics else "Online Business Tipps"
        r = await asyncio.wait_for(post_promo(topic), timeout=20)
        result["ok"] = r.get("ok", False)
        result["action"] = f"Discord: {r.get('via', 'webhook')} post"
    except Exception as e:
        result["error"] = str(e)[:80]
        log.warning("Discord agent error: %s", e)
    return result


async def agent_youtube(topics: list[str]) -> dict:
    """YouTube Agent — Community Posts + SEO Content."""
    result = {"platform": "YouTube", "ok": False, "action": ""}
    try:
        from modules.youtube_autonomy import run_autonomy_cycle
        r = await asyncio.wait_for(run_autonomy_cycle(), timeout=30)
        result["ok"] = True
        result["action"] = f"YouTube: {r.get('posts', 0)} community posts"
    except Exception as e:
        result["error"] = str(e)[:80]
        log.warning("YouTube agent error: %s", e)
    return result


# ── Master Orchestrator ────────────────────────────────────────────────────────

AGENTS = [
    agent_klaviyo,
    agent_mailchimp,
    agent_twilio,
    agent_aliexpress,
    agent_ebay,
    agent_amazon,
    agent_fiverr,
    agent_upwork,
    agent_tiktok,
    agent_reddit,
    agent_discord,
    agent_youtube,
]


async def run_all_agents(topics: list[str] | None = None) -> dict:
    """Alle 12 Agenten gleichzeitig ausführen."""
    if not topics:
        topics = await get_trending_topics()

    log.info("MegaAgentOrchestrator: Starte %d Agenten parallel | Topics: %s",
             len(AGENTS), topics[:2])

    tasks = [agent(topics) for agent in AGENTS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    ok_count = 0
    fail_count = 0
    report_lines = []

    for r in results:
        if isinstance(r, Exception):
            fail_count += 1
            report_lines.append(f"❌ ERROR: {str(r)[:60]}")
        elif r.get("ok"):
            ok_count += 1
            report_lines.append(f"✅ {r['platform']}: {r.get('action', 'ok')}")
        else:
            fail_count += 1
            report_lines.append(f"⚠️ {r['platform']}: {r.get('error', 'failed')}")

    summary = {
        "ok": ok_count > 0,
        "agents_ok": ok_count,
        "agents_failed": fail_count,
        "total_agents": len(AGENTS),
        "topics": topics,
        "results": results if not isinstance(results, Exception) else [],
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    msg = (
        f"🤖 <b>MegaAgentOrchestrator</b>\n"
        f"✅ {ok_count}/{len(AGENTS)} Agenten erfolgreich\n\n"
        + "\n".join(report_lines[:12])
        + f"\n\n🕒 {datetime.now().strftime('%H:%M:%S')}"
    )
    await _tg(msg)

    return summary


async def get_orchestrator_status() -> dict:
    """Status aller Platform-Agenten ohne Ausführung."""
    import aiohttp
    platform_status = {}

    checks = {
        "Klaviyo":    "https://supermegabot-production.up.railway.app/api/klaviyo/status",
        "Mailchimp":  "https://supermegabot-production.up.railway.app/api/email/status",
        "Twilio":     "https://supermegabot-production.up.railway.app/api/twilio/status",
        "AliExpress": "https://supermegabot-production.up.railway.app/api/aliexpress/status",
        "eBay":       "https://supermegabot-production.up.railway.app/api/ebay/status",
        "Amazon":     "https://supermegabot-production.up.railway.app/api/amazon/status",
        "Fiverr":     "https://supermegabot-production.up.railway.app/api/fiverr/status",
        "TikTok":     "https://supermegabot-production.up.railway.app/api/tiktok/status",
        "YouTube":    "https://supermegabot-production.up.railway.app/api/youtube/status",
        "Discord":    "https://supermegabot-production.up.railway.app/api/discord/status",
    }

    async def _check(name: str, url: str) -> tuple[str, bool]:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    d = await r.json(content_type=None)
                    return name, bool(d.get("ok") or d.get("configured") or d.get("connected"))
        except Exception:
            return name, False

    tasks = [_check(n, u) for n, u in checks.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for item in results:
        if isinstance(item, tuple):
            name, status = item
            platform_status[name] = status

    ok_count = sum(1 for v in platform_status.values() if v)
    return {
        "ok": True,
        "platforms": platform_status,
        "active": ok_count,
        "total": len(platform_status),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def scheduled_orchestrator_run() -> str:
    """Scheduler-Task: Alle Agenten koordiniert starten."""
    try:
        topics = await get_trending_topics()
        result = await run_all_agents(topics)
        return (
            f"MegaAgentOrchestrator: {result['agents_ok']}/{result['total_agents']} OK | "
            f"Topics: {', '.join(topics[:2])}"
        )
    except Exception as e:
        log.error("Orchestrator error: %s", e)
        return f"Orchestrator error: {e}"
