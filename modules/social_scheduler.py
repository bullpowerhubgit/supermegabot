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

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")   # marketing → public channel only
TELEGRAM_ALERT   = os.getenv("TELEGRAM_CHAT_ID", "")       # system alerts → private chat
TELEGRAM_CHAT    = TELEGRAM_CHANNEL or TELEGRAM_ALERT or "" # fall back to private chat if no channel
TWITTER_WEBHOOK = os.getenv("TWITTER_WEBHOOK_URL", os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("RAILWAY_STATIC_URL", "http://localhost:8888")).rstrip("/") + "/api/twitter/post")
TWITTER_SECRET  = os.getenv("TWITTER_WEBHOOK_SECRET", "bullpower2026")
FB_PAGE_ID      = os.getenv("FACEBOOK_PAGE_ID", "1016738738178786")  # AiiteC
FB_PAGE_TOKEN   = os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC", os.getenv("FACEBOOK_PAGE_TOKEN", ""))
GRAPH_API_VERSION = "v21.0"

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
        "text": "🔥 Shopify auf Autopilot: KI findet Bestseller, optimiert Preise, postet überall.\n\nKein manueller Aufwand mehr. Ab €49/Monat:\n👉 https://ineedit.com.co\n\n#ShopifyAutomation #KI #Ecommerce",
        "telegram_extra": "\n\n<b>Jetzt testen →</b> https://ineedit.com.co",
    },
    {
        "text": "💰 +187% Umsatz in 90 Tagen — vollautomatisch.\n\nKI-Automatisierung macht's möglich:\n✅ Produkte finden\n✅ Emails senden\n✅ Social Media posten\n\nhttps://ineedit.com.co #AIITEC",
        "telegram_extra": "",
    },
    {
        "text": "⚡ Shopify CRO auf Autopilot: +47% Conversion Rate durch KI-gesteuerte A/B-Tests & Page Speed.\n\nAlles automatisch — kein Aufwand.\n👉 https://ineedit.com.co\n\n#Shopify #CRO #Ecommerce",
        "telegram_extra": "",
    },
    {
        "text": "📊 Warum 90% der Shopify-Stores nie profitabel werden:\n\n❌ Manuell Produkte suchen\n❌ Keine Email-Automation\n❌ Kein A/B-Testing\n\n✅ Lösung: https://ineedit.com.co\n\n#Shopify #OnlineShop",
        "telegram_extra": "",
    },
    {
        "text": "🤖 KI im E-Commerce 2026:\n\n→ Produktrecherche: 2h → 2min\n→ Produktbeschreibungen: 20min → sofort\n→ Social Media: täglich → automatisch\n→ Umsatz: +187%\n\nhttps://ineedit.com.co #AI #KI",
        "telegram_extra": "",
    },
    {
        "text": "⭐⭐⭐⭐⭐ Kundenstimme:\n\n\"In 6 Wochen meinen Shopify-Umsatz verdoppelt. Die KI findet Produkte die ich nie gefunden hätte.\"\n— Markus K., München\n\n🔗 https://ineedit.com.co",
        "telegram_extra": "\n\n<i>Starte auch du heute.</i>",
    },
    {
        "text": "📈 Zahlen die für sich sprechen:\n\n• 187% mehr Umsatz (Ø 90 Tage)\n• +47% Conversion Rate\n• 40h/Woche gespart\n• 9 Social-Kanäle gleichzeitig\n\nhttps://ineedit.com.co\n#ShopifyAutomation",
        "telegram_extra": "",
    },
    {
        "text": "⏰ Während du manuell Produkte suchst, laufen automatisierte Stores auf Hochtouren.\n\nDer Unterschied: Ein Tool. Ab €49/Monat.\n\nhttps://ineedit.com.co\n#Shopify #Automation",
        "telegram_extra": "",
    },
    {
        "text": "💡 Shopify Tipp: Abandoned Cart Emails generieren 15-20% des Umsatzes zurück.\n\nAber 78% der Shops haben keine automatischen Cart-Recovery-Emails.\n\nFix in 5 Min: https://ineedit.com.co\n#Shopify #EmailMarketing",
        "telegram_extra": "",
    },
    {
        "text": "🎯 3 Dinge die sofort deinen Shopify-Umsatz erhöhen:\n\n1. Abandoned Cart Email (automatisch)\n2. Post-Purchase Upsell (KI-gesteuert)\n3. Social Proof auf Produktseiten\n\nAlles automatisch: https://ineedit.com.co",
        "telegram_extra": "",
    },
    # Gumroad — LIVE, sofort kaufbar
    {
        "text": "🚀 SuperMegaBot — Shopify auf KI-Autopilot\n\n✅ 10.500+ Produkte auto-importiert\n✅ Bestseller in Echtzeit\n✅ 9 Social-Kanäle automatisch\n✅ Revenue-Tracking vollautomatisch\n\n💶 €97 einmalig — kein Abo\n\n👉 https://www.checkout-ds24.com/product/668035\n\n#Shopify #KI #Automation",
        "telegram_extra": "",
    },
    {
        "text": "💰 40h/Woche Shopify → 0h manuell.\n\nSuperMegaBot übernimmt alles:\n→ Produktrecherche: 2h → 2min\n→ Beschreibungen: sofort\n→ Social Media: automatisch\n→ Emails: vollautomatisch\n\n€97 einmalig — läuft alleine.\n\n🔗 https://www.checkout-ds24.com/product/668035\n\n#ShopifyAutomation",
        "telegram_extra": "",
    },
    {
        "text": "⚡ SuperMegaBot — der einzige Shopify-Bot den du brauchst.\n\n🤖 KI-gesteuerte Produktauswahl\n📊 Live Revenue-Dashboard\n📱 Facebook + Instagram + TikTok automatisch\n📧 Email-Sequenzen vollautomatisch\n\nEinmalig €97 (kein Abo!)\n\n👉 Jetzt sichern: https://www.checkout-ds24.com/product/668035",
        "telegram_extra": "",
    },
    {
        "text": "🎯 Stell dir vor: Morgen früh wachst du auf und dein Shopify-Shop hat über Nacht Bestellungen bekommen — automatisch.\n\nDas ist SuperMegaBot.\n\n💶 Einmalig €97 — kein monatliches Abo.\n\n👉 https://www.checkout-ds24.com/product/668035\n\n#Shopify #AutomatischGeldVerdienen #KI2026",
        "telegram_extra": "",
    },
]


DAILY_POST_LIMIT = int(os.getenv("DAILY_POST_LIMIT", "3"))


def _next_template_index() -> int:
    import json
    try:
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
            return (state.get("last_index", -1) + 1) % len(CONTENT_TEMPLATES)
    except Exception as _e:
        log.debug("skipped: %s", _e)
    return 0


def _today_post_count() -> int:
    import json
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
            if state.get("last_post_date") == today:
                return state.get("posts_today", 0)
    except Exception as _e:
        log.debug("skipped: %s", _e)
    return 0


def _save_state(index: int, results: dict) -> None:
    import json
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        existing = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    except Exception:
        existing = {}
    posts_today = existing.get("posts_today", 0) + 1 if existing.get("last_post_date") == today else 1
    state = {
        "last_index": index,
        "last_run": datetime.now(timezone.utc).isoformat(),
        "last_results": results,
        "last_post_date": today,
        "posts_today": posts_today,
    }
    STATE_FILE.write_text(json.dumps(state, indent=2))


async def _validate_urls(text: str) -> str:
    """Prüft alle URLs im Text, ersetzt kaputte durch ineedit.com.co."""
    try:
        from modules.telegram_safe import validate_and_fix_text
        async with aiohttp.ClientSession() as s:
            fixed = await validate_and_fix_text(s, text)
            return fixed if fixed is not None else text
    except Exception:
        return text


async def post_to_telegram(text: str, extra_html: str = "") -> dict:
    """Sendet Nachricht an Telegram Channel/Chat mit URL-Validierung."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return {"ok": False, "error": "Telegram credentials fehlen"}

    try:
        from modules.telegram_safe import tg_send_safe
        full_text = f"📢 SuperMegaBot Update\n\n{text}{extra_html}"
        ok = await tg_send_safe(full_text, chat_id=TELEGRAM_CHAT)
        if ok:
            log.info("telegram: gesendet via telegram_safe")
            return {"ok": True, "platform": "telegram"}
        return {"ok": False, "error": "send failed"}
    except Exception as e:
        log.error("telegram exception: %s", e)
        return {"ok": False, "error": str(e)}


async def post_to_facebook(text: str) -> dict:
    """Postet auf AiiteC Facebook Page (1016738738178786) mit URL-Validierung + Post-Wächter."""
    try:
        from modules.post_watchdog import validate_post, record_sent, record_blocked
        ok, issues = await validate_post(text, platform="facebook")
        if not ok:
            log.warning("PostWatchdog [facebook] — BLOCKIERT: %s", "; ".join(issues))
            record_blocked(text, "facebook", issues)
            return {"ok": False, "blocked": True, "reasons": issues}
        record_sent(text, "facebook")
    except Exception:
        pass
    if not FB_PAGE_TOKEN:
        return {"ok": False, "error": "FACEBOOK_PAGE_TOKEN_AIITEC fehlt"}
    # Rate gate: max 1 Facebook post per 3 hours — verhindert Spam-Sperre
    try:
        from modules.brutus_core import _rate_gate
        if not _rate_gate("facebook", 10800):
            return {"ok": False, "error": "rate_limited — next post in >3h"}
    except Exception:
        pass

    dead_url = await _check_urls_in_text(text)
    if dead_url:
        log.error("post_to_facebook: URL_DEAD=%s — Post abgebrochen", dead_url)
        return {"ok": False, "error": f"URL_DEAD: {dead_url}"}
    text = await _validate_urls(text)

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{FB_PAGE_ID}/feed"
    payload = {"message": text, "access_token": FB_PAGE_TOKEN}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if "id" in data:
                    log.info("facebook: post live (id=%s)", data["id"])
                    return {"ok": True, "platform": "facebook", "post_id": data["id"]}
                else:
                    log.error("facebook error: %s", data)
                    return {"ok": False, "error": data.get("error", {}).get("message", str(data))}
    except Exception as e:
        log.error("facebook exception: %s", e)
        return {"ok": False, "error": str(e)}


async def post_to_twitter(text: str) -> dict:
    """Versucht Tweet über internen Webhook mit URL-Validierung + Post-Wächter."""
    try:
        from modules.post_watchdog import validate_post, record_sent, record_blocked
        ok, issues = await validate_post(text, platform="twitter")
        if not ok:
            log.warning("PostWatchdog [twitter] — BLOCKIERT: %s", "; ".join(issues))
            record_blocked(text, "twitter", issues)
            return {"ok": False, "blocked": True, "reasons": issues}
        record_sent(text, "twitter")
    except Exception:
        pass
    dead_url = await _check_urls_in_text(text)
    if dead_url:
        log.error("post_to_twitter: URL_DEAD=%s — Post abgebrochen", dead_url)
        return {"ok": False, "error": f"URL_DEAD: {dead_url}"}
    text = await _validate_urls(text)
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


async def _check_urls_in_text(text: str) -> str | None:
    """Prüft alle https:// URLs im Text. Gibt erste tote URL zurück oder None."""
    import re as _re
    urls = _re.findall(r'https://[^\s\'"\\>)\]]+', text)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            for url in urls:
                url = url.rstrip('.,;)')
                try:
                    async with s.get(url, allow_redirects=True) as r:
                        if r.status >= 400:
                            log.warning("URL_DEAD %s → %s", url, r.status)
                            return url
                except Exception:
                    log.warning("URL_UNREACHABLE %s", url)
                    return url
    except Exception as _e:
        log.debug("skipped: %s", _e)
    return None


async def post_daily_content(force_template_index: int = None) -> dict:
    """Hauptfunktion: postet auf Twitter, fällt auf Telegram zurück."""
    if os.getenv("SOCIAL_POSTING_PAUSED", "").lower() in ("1", "true", "yes"):
        log.warning("social_scheduler: SOCIAL_POSTING_PAUSED=true — übersprungen")
        return {"ok": False, "skipped": True, "reason": "SOCIAL_POSTING_PAUSED"}
    today_count = _today_post_count()
    if today_count >= DAILY_POST_LIMIT:
        log.info("social_scheduler: Tageslimit %d/%d erreicht — übersprungen", today_count, DAILY_POST_LIMIT)
        return {"ok": False, "skipped": True, "reason": f"DAILY_LIMIT_{today_count}/{DAILY_POST_LIMIT}"}
    idx = force_template_index if force_template_index is not None else _next_template_index()
    template = CONTENT_TEMPLATES[idx]
    text = template["text"]
    extra = template.get("telegram_extra", "")

    results = {"index": idx, "twitter": None, "telegram": None, "facebook": None, "timestamp": datetime.now(timezone.utc).isoformat()}

    # Facebook — immer posten (AiiteC page, 1.322 Follower)
    fb_result = await post_to_facebook(text)
    results["facebook"] = fb_result

    twitter_result = await post_to_twitter(text)
    results["twitter"] = twitter_result

    if not twitter_result["ok"]:
        log.info("Twitter nicht verfügbar — Fallback auf Telegram")
        telegram_result = await post_to_telegram(text, extra)
        results["telegram"] = telegram_result
        channels_used = ["telegram" if telegram_result["ok"] else None, "facebook" if fb_result["ok"] else None]
        results["channel_used"] = "+".join(c for c in channels_used if c) or "none"
    else:
        results["channel_used"] = "twitter" + ("+facebook" if fb_result["ok"] else "")

    _save_state(idx, results)
    await _brutus_fire(text[:300])
    await _slack_notify(f"SocialScheduler posted: channel={results.get('channel_used')} idx={idx}")
    return results


async def post_to_all_channels(text: str) -> dict:
    """Postet gleichzeitig auf Twitter, Telegram UND Facebook."""
    twitter_task = asyncio.create_task(post_to_twitter(text))
    telegram_task = asyncio.create_task(post_to_telegram(text))
    facebook_task = asyncio.create_task(post_to_facebook(text))
    twitter_result, telegram_result, facebook_result = await asyncio.gather(
        twitter_task, telegram_task, facebook_task, return_exceptions=True
    )

    return {
        "twitter": twitter_result if not isinstance(twitter_result, Exception) else {"ok": False, "error": str(twitter_result)},
        "telegram": telegram_result if not isinstance(telegram_result, Exception) else {"ok": False, "error": str(telegram_result)},
        "facebook": facebook_result if not isinstance(facebook_result, Exception) else {"ok": False, "error": str(facebook_result)},
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
