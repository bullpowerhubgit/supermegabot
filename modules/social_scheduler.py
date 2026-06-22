#!/usr/bin/env python3
"""
Social Scheduler — Multi-Channel Content Distribution
======================================================
Verteilt Marketing-Content auf Twitter/X und Telegram.
Fällt automatisch auf Telegram zurück wenn Twitter nicht verfügbar.
"""

import asyncio
import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

log = logging.getLogger("SocialScheduler")

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "8600739487:AAGhByAoKEpbsfco9swoaRYjU2HI_gSt718")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")   # marketing → public channel only
TELEGRAM_ALERT   = os.getenv("TELEGRAM_CHAT_ID", "")       # system alerts → private chat
TELEGRAM_CHAT    = TELEGRAM_CHANNEL or ""                   # backwards compat (no spam if no channel)
TWITTER_WEBHOOK = os.getenv("TWITTER_WEBHOOK_URL", "http://localhost:8888/api/twitter/post")
TWITTER_SECRET  = os.getenv("TWITTER_WEBHOOK_SECRET", "bullpower2026")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "social"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "schedule_state.json"


async def _brutus_fire(message: str, channels: list = None):
    try:
        from modules.brutus_core import BrutusCore
        b = BrutusCore()
        await b.fire(message, channels=channels or ["telegram", "slack", "linkedin", "twitter"])
    except Exception as _be:
        log.debug("Brutus fire skip: %s", _be)


async def _slack_notify(message: str):
    try:
        from modules.slack_notify import send_slack
        await send_slack(message, level="info")
    except Exception as _se:
        log.debug("Slack skip: %s", _se)

CONTENT_TEMPLATES = [
    {
        "text": "🔥 Shopify auf Autopilot: KI findet Bestseller, optimiert Preise, postet überall.\n\nKein manueller Aufwand mehr. Ab €49/Monat:\n👉 https://autopilot-store-suite-fmbka.myshopify.com\n\n#ShopifyAutomation #KI #Ecommerce",
        "telegram_extra": "\n\n<b>Jetzt testen →</b> https://autopilot-store-suite-fmbka.myshopify.com",
    },
    {
        "text": "💰 +187% Umsatz in 90 Tagen — vollautomatisch.\n\nKI-Automatisierung macht's möglich:\n✅ Produkte finden\n✅ Emails senden\n✅ Social Media posten\n\nhttps://autopilot-store-suite-fmbka.myshopify.com #AIITEC",
        "telegram_extra": "",
    },
    {
        "text": "⚡ Shopify Brutal Tuning: +47% Conversion Rate garantiert.\n\nA/B-Tests, Page Speed & CRO — alles automatisch.\n👉 https://shopify-brutal-tuning.vercel.app\n\n#Shopify #CRO #Ecommerce",
        "telegram_extra": "",
    },
    {
        "text": "📊 Warum 90% der Shopify-Stores nie profitabel werden:\n\n❌ Manuell Produkte suchen\n❌ Keine Email-Automation\n❌ Kein A/B-Testing\n\n✅ Lösung: https://autopilot-store-suite-fmbka.myshopify.com\n\n#Shopify #OnlineShop",
        "telegram_extra": "",
    },
    {
        "text": "🤖 KI im E-Commerce 2026:\n\n→ Produktrecherche: 2h → 2min\n→ Produktbeschreibungen: 20min → sofort\n→ Social Media: täglich → automatisch\n→ Umsatz: +187%\n\nhttps://autopilot-store-suite-fmbka.myshopify.com #AI #KI",
        "telegram_extra": "",
    },
    {
        "text": "⭐⭐⭐⭐⭐ Kundenstimme:\n\n\"In 6 Wochen meinen Shopify-Umsatz verdoppelt. Die KI findet Produkte die ich nie gefunden hätte.\"\n— Markus K., München\n\n🔗 https://autopilot-store-suite-fmbka.myshopify.com",
        "telegram_extra": "\n\n<i>Starte auch du heute.</i>",
    },
    {
        "text": "📈 Zahlen die für sich sprechen:\n\n• 187% mehr Umsatz (Ø 90 Tage)\n• +47% Conversion Rate\n• 40h/Woche gespart\n• 9 Social-Kanäle gleichzeitig\n\nhttps://autopilot-store-suite-fmbka.myshopify.com\n#ShopifyAutomation",
        "telegram_extra": "",
    },
    {
        "text": "⏰ Während du manuell Produkte suchst, laufen automatisierte Stores auf Hochtouren.\n\nDer Unterschied: Ein Tool. Ab €49/Monat.\n\nhttps://autopilot-store-suite-fmbka.myshopify.com\n#Shopify #Automation",
        "telegram_extra": "",
    },
    {
        "text": "💡 Shopify Tipp: Abandoned Cart Emails generieren 15-20% des Umsatzes zurück.\n\nAber 78% der Shops haben keine automatischen Cart-Recovery-Emails.\n\nFix in 5 Min: https://autopilot-store-suite-fmbka.myshopify.com\n#Shopify #EmailMarketing",
        "telegram_extra": "",
    },
    {
        "text": "🎯 3 Dinge die sofort deinen Shopify-Umsatz erhöhen:\n\n1. Abandoned Cart Email (automatisch)\n2. Post-Purchase Upsell (KI-gesteuert)\n3. Social Proof auf Produktseiten\n\nAlles automatisch: https://autopilot-store-suite-fmbka.myshopify.com",
        "telegram_extra": "",
    },
]


def _next_template_index() -> int:
    import json
    try:
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
            return (state.get("last_index", -1) + 1) % len(CONTENT_TEMPLATES)
    except Exception:
        pass
    return 0


def _save_state(index: int, results: dict) -> None:
    import json
    state = {
        "last_index": index,
        "last_run": datetime.now(timezone.utc).isoformat(),
        "last_results": results,
    }
    STATE_FILE.write_text(json.dumps(state, indent=2))


async def post_to_telegram(text: str, extra_html: str = "") -> dict:
    """Sendet Nachricht an Telegram Channel/Chat."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return {"ok": False, "error": "Telegram credentials fehlen"}

    html_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html_text = html_text.replace("#", "<b>#</b>", 1) if "#" in html_text else html_text
    full_message = f"<b>📢 SuperMegaBot Update</b>\n\n{html_text}{extra_html}"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT,
        "text": full_message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get("ok"):
                    msg_id = data["result"]["message_id"]
                    log.info("telegram: gesendet (message_id=%s)", msg_id)
                    return {"ok": True, "platform": "telegram", "message_id": msg_id}
                else:
                    log.error("telegram error: %s", data)
                    return {"ok": False, "error": data.get("description", "unknown")}
    except Exception as e:
        log.error("telegram exception: %s", e)
        return {"ok": False, "error": str(e)}


async def post_to_twitter(text: str) -> dict:
    """Versucht Tweet über internen Webhook."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                TWITTER_WEBHOOK,
                json={"text": text, "secret": TWITTER_SECRET},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    log.info("twitter: tweet gesendet")
                    return {"ok": True, "platform": "twitter"}
                else:
                    log.warning("twitter fehlgeschlagen: %s", data)
                    return {"ok": False, "error": str(data)}
    except Exception as e:
        log.warning("twitter exception: %s", e)
        return {"ok": False, "error": str(e)}


async def post_daily_content(force_template_index: int = None) -> dict:
    """Hauptfunktion: postet auf Twitter, fällt auf Telegram zurück."""
    idx = force_template_index if force_template_index is not None else _next_template_index()
    template = CONTENT_TEMPLATES[idx]
    text = template["text"]
    extra = template.get("telegram_extra", "")

    results = {"index": idx, "twitter": None, "telegram": None, "timestamp": datetime.now(timezone.utc).isoformat()}

    twitter_result = await post_to_twitter(text)
    results["twitter"] = twitter_result

    if not twitter_result["ok"]:
        log.info("Twitter nicht verfügbar — poste auf Telegram als Fallback")
        telegram_result = await post_to_telegram(text, extra)
        results["telegram"] = telegram_result
        results["channel_used"] = "telegram"
    else:
        results["channel_used"] = "twitter"

    _save_state(idx, results)
    await _brutus_fire(text[:300])
    await _slack_notify(f"SocialScheduler posted: channel={results.get('channel_used')} idx={idx}")
    return results


async def post_to_all_channels(text: str) -> dict:
    """Postet gleichzeitig auf Twitter UND Telegram."""
    twitter_task = asyncio.create_task(post_to_twitter(text))
    telegram_task = asyncio.create_task(post_to_telegram(text))
    twitter_result, telegram_result = await asyncio.gather(twitter_task, telegram_task, return_exceptions=True)

    return {
        "twitter": twitter_result if not isinstance(twitter_result, Exception) else {"ok": False, "error": str(twitter_result)},
        "telegram": telegram_result if not isinstance(telegram_result, Exception) else {"ok": False, "error": str(telegram_result)},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def run_scheduler_loop(interval_hours: float = 6.0) -> None:
    """Läuft dauerhaft und postet alle N Stunden."""
    log.info("SocialScheduler gestartet (interval=%.1fh)", interval_hours)
    while True:
        try:
            result = await post_daily_content()
            log.info("scheduled post: %s", result.get("channel_used"))
        except Exception as e:
            log.error("scheduler fehler: %s", e)
        await asyncio.sleep(interval_hours * 3600)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(post_daily_content())
