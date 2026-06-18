#!/usr/bin/env python3
"""
Telegram Master Dashboard — steuert alle Railway-Dienste vom Bot aus.
Befehle: /dashboard, /alle_dienste, /revenue, /seo_push, /agent_status, /deploy_status
"""
import asyncio
import json
import os
import urllib.request
import urllib.parse
from typing import Optional

TELEGRAM_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_BOT_TOKEN_1")
    or os.getenv("TELEGRAM_BOT_TOKEN_2")
    or ""
)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── All deployed Railway services ────────────────────────────────────────────
RAILWAY_SERVICES = [
    {"name": "🤖 SuperMegaBot",           "url": "https://dudirudibot-mega-production.up.railway.app",                    "health": "/health"},
    {"name": "🛍️ Shopify Acq. Engine",    "url": "https://shopify-acquisition-engine-production.up.railway.app",          "health": "/health"},
    {"name": "💰 iComeAuto SaaS",          "url": "https://icomeauto-saas-production.up.railway.app",                      "health": "/api/health"},
    {"name": "📈 SEO Turbo Tools",         "url": "https://seo-turbo-tools-production.up.railway.app",                     "health": "/health"},
    {"name": "📡 SEO Traffic Engine",      "url": "https://seo-traffic-engine-production.up.railway.app",                  "health": "/health"},
    {"name": "✈️ Telegram Automation",    "url": "https://telegram-automation-bot-production.up.railway.app",             "health": "/api/health"},
    {"name": "🎨 CreatorAI Ultra",         "url": "https://creatorai-ultra-production.up.railway.app",                     "health": "/health"},
    {"name": "📦 Digistore24 Suite",       "url": "https://digistore24-automation-production.up.railway.app",              "health": "/health"},
    {"name": "🧠 Cognitive Symphony",      "url": "https://cognitive-symphony-production.up.railway.app",                  "health": "/health"},
    {"name": "💰 Revenue Hub",             "url": "https://revenue-hub-notifications-production.up.railway.app",           "health": "/health"},
    {"name": "📢 AdPoster Engine",         "url": "https://adposter-engine-production.up.railway.app",                     "health": "/health"},
    {"name": "🧾 Steuercockpit",           "url": "https://steuercockpit-production-44c9.up.railway.app",                  "health": "/api/health"},
    {"name": "🏪 Shopify Automaton Suite", "url": "https://shopify-automaton-suite-production-e405.up.railway.app",        "health": "/api/health"},
    {"name": "📘 Meta Social Engine",      "url": "https://meta-social-engine-production.up.railway.app",                  "health": "/health"},
    {"name": "💼 Freelance Gig Engine",    "url": "https://freelance-gig-engine-production.up.railway.app",               "health": "/health"},
    {"name": "🖼️ Visual Content Engine",  "url": "https://visual-content-engine-production.up.railway.app",               "health": "/health"},
    {"name": "📊 Analytics Marketing",     "url": "https://analytics-marketing-pro-production.up.railway.app",             "health": "/health"},
    {"name": "🛒 Shopify KI Suite",        "url": "https://shopify-ki-suite-production.up.railway.app",                   "health": "/health"},
    {"name": "📣 Social Traffic Engine",   "url": "https://social-traffic-engine-production.up.railway.app",              "health": "/health"},
]

SEO_ENGINE_URL = os.getenv("SEO_TRAFFIC_ENGINE_URL", "https://seo-traffic-engine-production.up.railway.app")


def _http_get(url: str, timeout: int = 5) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SuperMegaBot/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


async def check_service_health(service: dict) -> tuple[str, bool]:
    """Returns (name, is_healthy)."""
    loop = asyncio.get_event_loop()
    url = service["url"] + service["health"]
    result = await loop.run_in_executor(None, lambda: _http_get(url, timeout=5))
    ok = result is not None and (
        result.get("status") in ("ok", "healthy", "running")
        or result.get("ok") is True
        or "version" in result
    )
    return service["name"], ok


async def cmd_dashboard(text: str = "", session_id: str = "") -> str:
    """Check health of all Railway services and return a formatted dashboard."""
    tasks = [check_service_health(s) for s in RAILWAY_SERVICES]
    results = await asyncio.gather(*tasks)

    online = [(n, ok) for n, ok in results if ok]
    offline = [(n, ok) for n, ok in results if not ok]

    lines = [
        "🖥️ <b>MASTER DASHBOARD — Alle Dienste</b>",
        f"✅ Online: <b>{len(online)}</b>  ❌ Offline: <b>{len(offline)}</b>",
        "",
        "<b>🟢 Online:</b>",
    ]
    for name, _ in online:
        lines.append(f"  • {name}")

    if offline:
        lines.append("")
        lines.append("<b>🔴 Offline / Fehler:</b>")
        for name, _ in offline:
            lines.append(f"  • {name}")

    lines.append("")
    lines.append("🔄 Befehle: /alle_dienste /revenue /seo_push /agent_status")
    return "\n".join(lines)


async def cmd_alle_dienste(text: str = "", session_id: str = "") -> str:
    """Return a list of all services with their direct URLs."""
    lines = ["🗺️ <b>ALLE DIENSTE — Railway + Netlify</b>", ""]
    lines.append("<b>🚀 Railway Backends:</b>")
    for s in RAILWAY_SERVICES:
        lines.append(f"• {s['name']}: {s['url']}")

    lines += [
        "",
        "<b>🌐 Netlify Frontends:</b>",
        "• Mega Dashboard: https://cheery-beijinho-b74689.netlify.app",
        "• Shopify Suite: https://visionary-quokka-002bdb.netlify.app",
        "• CreatorStudio Pro: https://venerable-lebkuchen-52bc6d.netlify.app",
        "• Digistore24 Suite: https://melodic-chimera-3b3e92.netlify.app",
        "• Cognitive Symphony: https://deluxe-valkyrie-1302a6.netlify.app",
        "• Monetization Hub: https://hilarious-horse-833910.netlify.app",
        "",
        "💡 /dashboard für Health-Check aller Dienste",
    ]
    return "\n".join(lines)


async def cmd_seo_push(text: str = "", session_id: str = "") -> str:
    """Push a keyword to the SEO traffic engine."""
    parts = text.strip().split(None, 1)
    keyword = parts[1].strip() if len(parts) > 1 else "shopify automation"
    loop = asyncio.get_event_loop()

    def _push():
        try:
            payload = json.dumps({"keyword": keyword, "url": SEO_ENGINE_URL}).encode()
            req = urllib.request.Request(
                f"{SEO_ENGINE_URL}/api/ingest",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                return json.loads(r.read())
        except Exception as e:
            return {"error": str(e)}

    result = await loop.run_in_executor(None, _push)
    if "error" in result:
        return f"❌ SEO Push fehlgeschlagen: {result['error']}"
    return f"✅ SEO Push erfolgreich!\n🔑 Keyword: <b>{keyword}</b>\n📡 Engine: {SEO_ENGINE_URL}"


async def cmd_agent_status(text: str = "", session_id: str = "") -> str:
    """Show status of all autonomous background agents."""
    lines = [
        "🤖 <b>AGENTEN-STATUS — Alle autonomen Prozesse</b>",
        "",
        "<b>⏰ Automatische Intervalle:</b>",
        "• AdPoster: KI-Ads alle 6h → Telegram",
        "• Revenue Hub: Stripe Webhooks → Telegram (sofort)",
        "• SuperMegaBot: Shopify sync 30min | DS24 1h | Health 2h | Trends 6h | Backup täglich",
        "• SEO Traffic Engine: Artikel alle 6h + Sitemap-Ping + Twitter alle 4h",
        "• Social Traffic Engine: Reddit/LinkedIn/HN alle 8h → Telegram",
        "• Meta Social Engine: Facebook + Instagram alle 4h (⚠️ Token erneuern!)",
        "• Visual Content Engine: TikTok + Pinterest + Discord alle 5h → Telegram",
        "• Freelance Engine: Fiverr Gig + Upwork Proposals alle 12h → Telegram",
        "",
        "<b>⚠️ Manuelle Aktionen nötig:</b>",
        "1. Facebook Token abgelaufen → developers.facebook.com erneuern",
        "2. Discord Bot nicht im Server → Einladen nötig",
        "3. Pinterest Board-ID fehlt → railway variables set PINTEREST_BOARD_ID=<id>",
        "4. Instagram Account-ID fehlt → business.facebook.com",
        "",
        "💡 /dashboard für Live-Health | /seo_push <keyword> für SEO",
    ]
    return "\n".join(lines)


async def cmd_revenue(text: str = "", session_id: str = "") -> str:
    """Fetch revenue summary from iComeAuto and Revenue Hub."""
    loop = asyncio.get_event_loop()

    def _fetch_icome():
        return _http_get("https://icomeauto-saas-production.up.railway.app/api/revenue/summary", timeout=8)

    def _fetch_hub():
        return _http_get("https://revenue-hub-notifications-production.up.railway.app/health", timeout=8)

    icome, hub = await asyncio.gather(
        loop.run_in_executor(None, _fetch_icome),
        loop.run_in_executor(None, _fetch_hub),
    )

    lines = ["💰 <b>REVENUE ÜBERSICHT</b>", ""]

    if icome and isinstance(icome, dict):
        mrr = icome.get("mrr", icome.get("monthly_recurring_revenue", "?"))
        active = icome.get("active_subscriptions", icome.get("activeSubs", "?"))
        total = icome.get("total_revenue", icome.get("monthRevenue", "?"))
        lines += [
            "<b>📊 iComeAuto SaaS:</b>",
            f"  💵 MRR: <b>€{mrr}</b>",
            f"  👥 Aktive Subs: <b>{active}</b>",
            f"  📅 Monat: <b>€{total}</b>",
        ]
    else:
        lines.append("⚠️ iComeAuto Revenue-API nicht erreichbar")

    lines += [
        "",
        f"Revenue Hub: {'✅ Online' if hub else '❌ Offline'}",
        "",
        "💡 Mehr Details: /alle_dienste | /dashboard",
    ]
    return "\n".join(lines)


async def cmd_deploy_status(text: str = "", session_id: str = "") -> str:
    """Quick health check of the 5 most critical services."""
    critical = RAILWAY_SERVICES[:5]
    tasks = [check_service_health(s) for s in critical]
    results = await asyncio.gather(*tasks)

    lines = ["🚀 <b>DEPLOY STATUS — Kritische Dienste</b>", ""]
    for name, ok in results:
        icon = "✅" if ok else "❌"
        lines.append(f"{icon} {name}")

    lines += [
        "",
        "💡 /dashboard für alle Dienste | /seo_push <keyword>",
    ]
    return "\n".join(lines)
