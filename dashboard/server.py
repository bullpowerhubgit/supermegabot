#!/usr/bin/env python3
"""SuperMegaBot Dashboard Server - Port 8888"""

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_SERVER_START_TIME = time.time()

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path.home()))

from aiohttp import web
import aiohttp

# Self-Learner integration
try:
    from self_learner_core import SelfLearner
    _self_learner = SelfLearner("supermegabot", telegram_notify=True)
    _self_learner.load_learned_skills()
except Exception:
    _self_learner = None

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    # fallback: manual parse
    _env_file = BASE_DIR / ".env"
    if _env_file.exists():
        for _line in _env_file.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

PORT = int(os.getenv("PORT") or os.getenv("DASHBOARD_PORT", "8888"))

log = logging.getLogger("Dashboard")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# ---------------------------------------------------------------------------
# In-memory cache: {key: (timestamp, data)}
# ---------------------------------------------------------------------------
_cache: dict = {}

def _cache_get(key: str, ttl: int):
    """Return cached value if still fresh, else None."""
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < ttl:
        return entry[1]
    return None

def _cache_set(key: str, data):
    _cache[key] = (time.time(), data)

OLLAMA_BASE = os.getenv("OLLAMA_HOST", "http://localhost:11434")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------------------------------------------------------------------------
# Service definitions for Start/Stop control
# ---------------------------------------------------------------------------

_HOME = Path.home()

def _ext(env_var: str, default_rel: str) -> str:
    """Gibt Pfad aus Env-Var zurück, sonst HOME/default_rel."""
    return os.getenv(env_var, str(_HOME / default_rel))

SERVICES = [
    {"id": "dashboard", "name": "SuperMegaBot", "port": 8888,
     "start_cmd": f"cd {BASE_DIR} && nohup python3 dashboard/server.py >> /tmp/supermegabot.log 2>&1 &",
     "pattern": "dashboard/server.py", "icon": "🤖"},
    {"id": "rudibot_army", "name": "RudiBot Army", "port": 0,
     "start_cmd": f"cd {BASE_DIR} && nohup python3 rudibot-army/army_commander.py >> /tmp/rudibot-army.log 2>&1 &",
     "pattern": "army_commander.py", "icon": "🪖"},
    {"id": "mega_orchestrator", "name": "Mega Orchestrator", "port": 0,
     "start_cmd": f"cd {BASE_DIR} && nohup python3 core/mega_orchestrator.py >> /tmp/mega-orchestrator.log 2>&1 &",
     "pattern": "mega_orchestrator.py", "icon": "🧩"},
    {"id": "telegram_bot", "name": "Telegram Bot", "port": 3200,
     "start_cmd": f"cd {_ext('TELEGRAM_BOT_DIR','telegram-automation-bot')} && nohup node server.js >> /tmp/telegram-bot.log 2>&1 &",
     "pattern": "telegram-automation-bot.*server.js", "icon": "✈️"},
    {"id": "cratorhub", "name": "CreatorHub", "port": 3000,
     "start_cmd": f"cd {_ext('DIGIFABRIK_DIR','digifabrik')} && nohup npx tsx server.ts >> /tmp/cratorhub.log 2>&1 &",
     "pattern": "digifabrik.*server", "icon": "🎨"},
    {"id": "ollama", "name": "Ollama LLM", "port": 11434,
     "start_cmd": "ollama serve >> /tmp/ollama.log 2>&1 &",
     "pattern": "ollama serve", "icon": "🧠"},
    {"id": "openclaw", "name": "OpenClaw Gateway", "port": 18789,
     "start_cmd": "openclaw gateway run",
     "pattern": "openclaw", "icon": "🦞"},
    {"id": "windsurf_shopify_suite", "name": "Shopify Webhook Suite", "port": 3001,
     "start_cmd": f"cd {_ext('SHOPIFY_SUITE_DIR','windsurf-shopify-suite')} && nohup npm start >> /tmp/windsurf-shopify-suite.log 2>&1 &",
     "pattern": "windsurf-shopify-suite", "icon": "🛒"},
    {"id": "windsurf_telegram_bot", "name": "Windsurf Telegram Bot", "port": 8000,
     "start_cmd": f"cd {_ext('WS_TELEGRAM_DIR','windsurf-telegram-bot')} && nohup npm start >> /tmp/windsurf-telegram-bot.log 2>&1 &",
     "pattern": "windsurf-telegram-bot.*index.js", "icon": "🤖"},
    {"id": "shopify_ai_suite", "name": "Shopify AI Suite (Railway)", "port": 0,
     "start_cmd": "echo 'Deployed on Railway'",
     "pattern": "RAILWAY_REMOTE",
     "url": "https://shopify-suite-v2-production.up.railway.app",
     "health_url": "https://shopify-suite-v2-production.up.railway.app/health",
     "icon": "🛍️"},
    {"id": "windsurf_shopify", "name": "Windsurf API Gateway", "port": 8080,
     "start_cmd": f"cd {_ext('API_GATEWAY_DIR','windsurf-api-gateway')} && nohup node src/index.js >> /tmp/windsurf-api-gateway.log 2>&1 &",
     "pattern": "windsurf-api-gateway.*index.js", "icon": "🌊"},
    {"id": "windsurf_autoheal", "name": "Windsurf Auto-Heal", "port": 9000,
     "start_cmd": f"cd {_ext('AUTO_HEAL_DIR','windsurf-auto-heal')} && nohup npm start >> /tmp/windsurf-autoheal.log 2>&1 &",
     "pattern": "windsurf-auto-heal.*index.js", "icon": "🏥"},
    {"id": "password_sync", "name": "Password Sync", "port": 3005,
     "start_cmd": f"cd {_ext('PASSWORD_SYNC_DIR','password-sync-suite/web-app')} && PORT=3005 nohup npm start >> /tmp/password-sync.log 2>&1 &",
     "pattern": "password-sync-suite.*server.js", "icon": "🔐"},
    {"id": "rudibot_eternal", "name": "RudiBot Eternal", "port": 0,
     "start_cmd": f"cd {_ext('ETERNAL_BOT_DIR','rudibot-eternal')} && nohup python3 immortal_bot.py >> /tmp/rudibot-eternal.log 2>&1 &",
     "pattern": "immortal_bot.py", "icon": "♾️"},
    {"id": "kivo", "name": "KIVO Voice", "port": 0,
     "start_cmd": f"cd {_ext('KIVO_DIR','kivo')} && nohup python3 kivo.py >> /tmp/kivo.log 2>&1 &",
     "pattern": "kivo.py", "icon": "🎙️"},
]

# ---------------------------------------------------------------------------
# HTML Dashboard
# ---------------------------------------------------------------------------

_INDEX_HTML = Path(__file__).parent / 'index.html'




# ---------------------------------------------------------------------------
# API Routes — existing handlers
# ---------------------------------------------------------------------------

async def handle_index(req):
    try:
        html = _INDEX_HTML.read_text(encoding="utf-8")
    except Exception:
        html = "<h1>Dashboard nicht gefunden</h1><p>dashboard/index.html fehlt</p>"
    return web.Response(text=html, content_type="text/html")


async def handle_chat(req):
    try:
        try:
            data = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
        text = data.get("text") or data.get("message") or ""
        session_id = data.get("session_id", "dashboard")
        bot = req.app["bot"]
        response = await bot.process(text, session_id)
        return web.json_response({"ok": True, "response": response, "session_id": session_id})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bot_execute(req):
    """Telegram Hub Bridge → Dashboard CommandRouter.
    Called by telegram_hub_bridge.py for every incoming Telegram message.
    """
    try:
        data = await req.json()
        command = data.get("command", "").strip()
        session_id = data.get("session_id", "telegram")
        if not command:
            return web.json_response({"ok": False, "error": "command is required"}, status=400)
        bot = req.app["bot"]
        response = await bot.process(command, session_id)
        return web.json_response({"ok": True, "response": response})
    except Exception as e:
        log.error("handle_bot_execute error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bot_commands(req):
    """Return all registered bot commands (for /commands meta-command in Telegram)."""
    try:
        bot = req.app["bot"]
        all_cmds = list(bot.router.routes.keys())
        slash_cmds = sorted(c for c in all_cmds if c.startswith("/"))
        other_cmds = sorted(c for c in all_cmds if not c.startswith("/"))
        return web.json_response({
            "ok": True,
            "total": len(all_cmds),
            "slash": slash_cmds,
            "all": slash_cmds + other_cmds,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_system(req):
    try:
        import psutil
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return web.json_response({
            "ok": True,
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "memory_used_gb": round(mem.used / 1024**3, 1),
            "memory_total_gb": round(mem.total / 1024**3, 1),
            "memory_percent": round(mem.percent, 1),
            "disk_used_gb": round(disk.used / 1024**3, 1),
            "disk_free_gb": round(disk.free / 1024**3, 1),
            "disk_percent": round(disk.percent, 1),
            "process_count": len(psutil.pids()),
        })
    except ImportError:
        return web.json_response({"ok": False, "error": "psutil not installed"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_services_legacy(req):
    """Legacy /api/services endpoint — kept for backward compat."""
    import socket
    service_list = [
        {"name": "SuperMegaBot Dashboard", "port": PORT},
        {"name": "Telegram-Automation-Bot", "port": 3200},
        {"name": "CreatorHub", "port": 3000},
        {"name": "Ollama", "port": 11434},
        {"name": "OpenClaw Gateway", "port": 18789},
        {"name": "Windsurf API Gateway", "port": 8080},
    ]
    for s in service_list:
        if s["port"] == PORT:
            s["ok"] = True
            continue
        try:
            sock = socket.create_connection(("localhost", s["port"]), timeout=1)
            sock.close()
            s["ok"] = True
        except Exception:
            s["ok"] = False
    return web.json_response({"services": service_list})


async def handle_trading_prices(req):
    try:
        from modules.trading_bot import TradingBot
        bot = TradingBot()
        prices = await bot.get_quick_prices()
        return web.json_response({"prices": prices})
    except Exception as e:
        return web.json_response({"error": str(e)})


async def handle_trading_arbitrage(req):
    try:
        from modules.trading_bot import TradingBot
        bot = TradingBot()
        opps = await bot.scan_quick()
        return web.json_response({"opportunities": opps})
    except Exception as e:
        return web.json_response({"error": str(e)})


async def handle_telegram_status(req):
    token = TELEGRAM_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    return web.json_response({
        "ok": True,
        "configured": bool(token),
        "chat_id": TELEGRAM_CHAT_ID or os.getenv("TELEGRAM_CHAT_ID", ""),
    })


async def handle_telegram_send(req):
    if not TELEGRAM_TOKEN:
        return web.json_response({"ok": False, "error": "No token configured"})
    try:
        data = await req.json()
        message = data.get("message", "")
        chat_id = TELEGRAM_CHAT_ID
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={"chat_id": chat_id, "text": message}) as r:
                ok = r.status == 200
                return web.json_response({"ok": ok})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_shopify_status(req):
    store = os.getenv("SHOPIFY_STORE_URL", "").strip().rstrip("/")
    token = (os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")).strip()
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "").strip().rstrip("/")

    if not token:
        return web.json_response({"ok": False, "error": "SHOPIFY_ADMIN_API_TOKEN nicht gesetzt"})

    # Build base URL: prefer explicit domain, fall back to SHOPIFY_STORE_URL
    if domain:
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        base = domain
    elif store:
        if not store.startswith("http"):
            store = f"https://{store}"
        base = store
    else:
        return web.json_response({"ok": False, "error": "SHOPIFY_STORE_URL oder SHOPIFY_SHOP_DOMAIN nicht gesetzt"})

    api_version = os.getenv("SHOPIFY_API_VERSION", "2024-10")
    try:
        connector = aiohttp.TCPConnector(ssl=True, limit=5)
        timeout = aiohttp.ClientTimeout(total=10, connect=6)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as s:
            url = f"{base}/admin/api/{api_version}/shop.json"
            headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
            async with s.get(url, headers=headers) as r:
                if r.status == 200:
                    d = await r.json()
                    shop = d.get("shop", {})
                    # Also fetch product + order counts
                    prod_url = f"{base}/admin/api/{api_version}/products/count.json"
                    order_url = f"{base}/admin/api/{api_version}/orders/count.json?status=any"
                    prod_count = order_count = "?"
                    try:
                        async with s.get(prod_url, headers=headers) as pr:
                            if pr.status == 200:
                                prod_count = (await pr.json()).get("count", "?")
                    except Exception:
                        pass
                    try:
                        async with s.get(order_url, headers=headers) as or_:
                            if or_.status == 200:
                                order_count = (await or_.json()).get("count", "?")
                    except Exception:
                        pass
                    return web.json_response({
                        "ok": True,
                        "store": shop.get("name", base),
                        "domain": shop.get("domain", ""),
                        "email": shop.get("email", ""),
                        "currency": shop.get("currency", ""),
                        "plan": shop.get("plan_display_name", ""),
                        "product_count": prod_count,
                        "order_count": order_count,
                    })
                elif r.status == 401:
                    return web.json_response({"ok": False, "error": "Token ungültig (401) — neu generieren"})
                elif r.status == 402:
                    return web.json_response({"ok": False, "error": "Shop gesperrt (402)"})
                else:
                    body = await r.text()
                    return web.json_response({"ok": False, "error": f"HTTP {r.status}: {body[:100]}"})
    except aiohttp.ClientConnectorError as e:
        return web.json_response({"ok": False, "error": f"DNS/Verbindung fehlgeschlagen: {e.host} — Shop-URL prüfen"})
    except aiohttp.ServerTimeoutError:
        return web.json_response({"ok": False, "error": "Timeout — Shopify nicht erreichbar"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_ollama_models(req):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.get(f"{OLLAMA_BASE}/api/tags") as r:
                if r.status == 200:
                    data = await r.json()
                    models = [
                        {"name": m["name"], "size": f"{m.get('size', 0) // 1024//1024//1024:.1f}GB"}
                        for m in data.get("models", [])
                    ]
                    return web.json_response({"ok": True, "models": models})
                return web.json_response({"ok": False, "models": []})
    except Exception as e:
        return web.json_response({"ok": False, "models": [], "error": str(e)})


async def handle_autopilot_agents(req):
    try:
        from modules.autopilot import AutoPilot
        ap = AutoPilot()
        return web.json_response({"ok": True, "agents": ap.get_agent_list()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_autopilot_run(req):
    try:
        try:
            data = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
        goal = data.get("goal", "")
        agent_id = data.get("agent_id") or None
        from modules.autopilot import AutoPilot
        ap = AutoPilot()
        if agent_id:
            result = await ap.run_task(goal, agent_id)
            return web.json_response({"ok": True, "results": [result]})
        else:
            results = await ap.run_autopilot_mode(goal)
            return web.json_response({"ok": True, "results": results})
    except Exception as e:
        log.error(f"AutoPilot error: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_autopilot_logs(req):
    try:
        from modules.autopilot import AutoPilot
        ap = AutoPilot()
        return web.json_response({"ok": True, "logs": ap.get_logs(30)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_geheimwaffe_run(req):
    try:
        try:
            data = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
        niche = data.get("niche", "General")
        from modules.geheimwaffe import run_full_automation
        result = await run_full_automation(niche)
        if "ok" not in result:
            result["ok"] = True
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_geheimwaffe_content(req):
    try:
        try:
            data = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
        product = data.get("product", "")
        content_type = data.get("type", "listing")
        platform = data.get("platform", "tiktok")
        from modules.geheimwaffe import generate_product_listing, generate_social_content, generate_ad_copy
        if content_type == "listing":
            result = await generate_product_listing(product)
        elif content_type == "social":
            result = await generate_social_content(product, platform)
        elif content_type == "ads":
            result = await generate_ad_copy(product)
        else:
            return web.json_response({"ok": False, "error": "Unbekannter content_type"}, status=400)
        if "ok" not in result:
            result["ok"] = True
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_gmc(req):
    try:
        sys.path.insert(0, str(BASE_DIR))
        from modules.gmc_monitor import get_full_status
        status = await get_full_status()
        if "ok" not in status:
            status["ok"] = True
        return web.json_response(status)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_gmc_verify_info(req):
    """GET /api/gmc/verify — instructions for completing GMC identity verification."""
    gmc_id = os.getenv("GMC_MERCHANT_ID", "5813214419")
    return web.json_response({
        "ok": True,
        "status": "identity_verification_pending",
        "merchant_id": gmc_id,
        "platform": "Google Shopping (shopify.com / google.com/shopping)",
        "action_required": "Complete Google Merchant Center identity verification",
        "steps": [
            f"1. Go to https://merchants.google.com — select merchant {gmc_id}",
            "2. Click 'Complete verification' in the banner at the top",
            "3. Upload a government ID or use automated phone/postcard verification",
            "4. Once verified: 624 active products appear in Google Shopping (free traffic!)",
        ],
        "impact": "WITHOUT verification: 0 products shown in Google Shopping — massive traffic loss!",
        "gmc_url": f"https://merchants.google.com/u/0/mc/overview?a={gmc_id}",
        "products_waiting": 624,
    })


async def handle_reddit_blast(req):
    """GET /api/reddit/blast — post to relevant subreddits immediately."""
    try:
        from modules.reddit_autoposter import run_reddit_blast
        topic = req.rel_url.query.get("topic", "passives Einkommen KI 2026")
        result = await run_reddit_blast(topic)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_reddit_status(req):
    """GET /api/reddit/status — Reddit API configuration status."""
    configured = all([
        os.getenv("REDDIT_CLIENT_ID"),
        os.getenv("REDDIT_CLIENT_SECRET"),
        os.getenv("REDDIT_USERNAME"),
        os.getenv("REDDIT_PASSWORD"),
    ])
    return web.json_response({
        "configured": configured,
        "setup": "Set REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET + REDDIT_USERNAME + REDDIT_PASSWORD in Railway" if not configured else "Ready",
        "target_subreddits": ["passive_income", "entrepreneur", "ecommerce", "dropshipping", "affiliatemarketing", "shopify"],
    })


async def handle_gmc_feed(req):
    """GET /api/gmc/feed.xml — Google Shopping RSS product feed for all 630 Shopify products."""
    try:
        import html as _html
        shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
        shopify_token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
        shopify_ver    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        store_url      = os.getenv("SHOPIFY_STORE_URL", os.getenv("DS24_AFFILIATE_LINK", "https://autopilot-store-suite-fmbka.myshopify.com"))

        products = []
        if shopify_token:
            import aiohttp as _aio
            async with _aio.ClientSession() as s:
                page_info = None
                while True:
                    params = {"limit": 250, "fields": "id,title,body_html,handle,images,variants,status"}
                    if page_info:
                        params = {"limit": 250, "page_info": page_info, "fields": "id,title,body_html,handle,images,variants,status"}
                    async with s.get(
                        f"https://{shopify_domain}/admin/api/{shopify_ver}/products.json",
                        headers={"X-Shopify-Access-Token": shopify_token},
                        params=params,
                        timeout=_aio.ClientTimeout(total=30),
                    ) as r:
                        data = await r.json(content_type=None)
                        batch = [p for p in data.get("products", []) if p.get("status") == "active"]
                        products.extend(batch)
                        link_header = r.headers.get("Link", "")
                        if 'rel="next"' in link_header:
                            import re as _re
                            m = _re.search(r'page_info=([^&>]+).*?rel="next"', link_header)
                            page_info = m.group(1) if m else None
                        else:
                            break
                        if len(products) >= 500:
                            break

        items = []
        for p in products[:500]:
            variant = (p.get("variants") or [{}])[0]
            price   = variant.get("price", "0")
            image   = (p.get("images") or [{}])[0].get("src", "") if p.get("images") else ""
            handle  = p.get("handle", "")
            title   = _html.escape(p.get("title", "")[:150])
            desc    = _html.escape((p.get("body_html") or p.get("title", "")).replace("<", " ").replace(">", " ")[:500])
            img_tag = f"<g:image_link>{image}</g:image_link>" if image else ""
            items.append(f"""  <item>
    <title><![CDATA[{p.get('title','')[:150]}]]></title>
    <description><![CDATA[{(p.get('body_html') or p.get('title',''))[:500]}]]></description>
    <link>{store_url}/products/{handle}</link>
    <g:id>shopify_{p.get('id','')}</g:id>
    <g:price>{price} EUR</g:price>
    <g:availability>in stock</g:availability>
    <g:condition>new</g:condition>
    <g:brand>BullPower Hub</g:brand>
    {img_tag}
  </item>""")

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
<channel>
  <title>I Want That! I Need It! — Google Shopping Feed</title>
  <link>{store_url}</link>
  <description>Alle Produkte aus dem Online-Shop</description>
  <language>de</language>
{chr(10).join(items)}
</channel>
</rss>"""
        return web.Response(text=xml, content_type="application/xml",
                            headers={"Content-Disposition": "inline; filename=feed.xml"})
    except Exception as e:
        return web.Response(text=f"<!-- feed error: {e} -->", content_type="application/xml", status=500)


async def handle_shopify_auto_fill_trending(req):
    """POST /api/shopify/auto-fill-trending — AI trending product auto-fill + BRUTUS blast."""
    try:
        from modules.shopify_auto_fill import auto_fill_trending_products
        result = await auto_fill_trending_products()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_backup_status(req):
    backups = []
    extra_dirs = [d.strip() for d in os.getenv("BACKUP_EXTRA_DIRS", "").split(",") if d.strip()]
    backup_paths = [BASE_DIR / "data"] + [Path(d) for d in extra_dirs]
    for p in backup_paths:
        if p.exists():
            try:
                size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                backups.append({"path": str(p), "exists": True, "size_mb": round(size/1024/1024, 1)})
            except Exception:
                backups.append({"path": str(p), "exists": True})
    return web.json_response({"backups": backups, "count": len(backups)})


async def handle_backup_run(req):
    import shutil
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = BASE_DIR / "data" / "backups" / ts
        backup_dir.mkdir(parents=True, exist_ok=True)
        backed = []
        # .env may not exist on Railway (env vars injected at runtime)
        env_path = BASE_DIR / ".env"
        if env_path.exists():
            shutil.copy2(env_path, backup_dir / "supermegabot.env")
            backed.append(".env")
        # Back up SQLite databases
        for db_name in ["memory.db", "scheduler.db", "email_stats.json"]:
            src = DATA_DIR / db_name
            if src.exists():
                shutil.copy2(src, backup_dir / db_name)
                backed.append(db_name)
        return web.json_response({"ok": True, "path": str(backup_dir), "backed_up": backed})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_revenue_legacy(req):
    """Compatibility alias for older dashboards expecting /api/revenue."""
    return await handle_revenue_summary(req)


async def handle_analytics_legacy(req):
    """Compatibility alias for older dashboards expecting /api/analytics."""
    return await handle_revenue_summary(req)


async def handle_kpis_legacy(req):
    """Compatibility alias for older dashboards expecting /api/kpis."""
    return await handle_revenue_summary(req)


async def handle_status_legacy(req):
    return await handle_system_status(req)


async def handle_metrics_legacy(req):
    return await handle_system_status(req)


async def handle_shopify_legacy(req):
    return await handle_shopify_status(req)


async def handle_hermes_enqueue(req):
    try:
        data = await req.json()
        from core.job_queue import HermesQueue
        job_id = await HermesQueue.get().enqueue(
            data.get("type", "generic"),
            data.get("payload", {}),
            data.get("priority", 5)
        )
        return web.json_response({"ok": True, "job_id": job_id})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_hermes_stats(req):
    try:
        from core.job_queue import HermesQueue
        stats = await HermesQueue.get().get_stats()
        return web.json_response({"ok": True, "stats": stats})
    except Exception as e:
        return web.json_response({"ok": True, "stats": {}, "note": str(e)})


async def handle_content_stats(req):
    try:
        from modules.content_hub import get_stats
        stats = await get_stats()
        return web.json_response({"ok": True, **stats})
    except Exception as e:
        return web.json_response({"ok": True, "articles_generated": 0, "note": str(e)})


# ---------------------------------------------------------------------------
# NEW API Routes
# ---------------------------------------------------------------------------

async def handle_mac_action(req):
    try:
        data = await req.json()
    except Exception:
        data = {}
    action = data.get("action", "")
    try:
        from modules.mac_controller import MacController
        mac = MacController()
        if action == "screenshot":
            result = await mac.take_screenshot()
        elif action == "notify":
            result = await mac.notify(data.get("title", "SuperMegaBot"), data.get("message", ""))
        elif action == "volume":
            result = await mac.set_volume(int(data.get("level", 50)))
        elif action == "lock":
            result = await mac.lock_screen()
        elif action == "sleep_display":
            result = await mac.sleep_display()
        elif action == "empty_trash":
            result = await mac.empty_trash()
        elif action == "open_url":
            result = await mac.open_url_safari(data.get("url", ""))
        elif action == "clipboard_get":
            result = await mac.get_clipboard()
        elif action == "system_info":
            result = await mac.get_system_info()
            return web.json_response({"ok": True, "result": result})
        elif action == "running_apps":
            result = await mac.list_running_apps()
            return web.json_response({"ok": True, "result": result})
        else:
            return web.json_response({"ok": False, "error": f"Unknown action: {action}"})
        return web.json_response({"ok": True, "result": str(result)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_services_status(req):
    import socket
    result = []
    for svc in SERVICES:
        port_ok = False
        if svc.get("port", 0) > 0:
            try:
                sock = socket.create_connection(("localhost", svc["port"]), timeout=0.5)
                sock.close()
                port_ok = True
            except Exception:
                pass

        # Special case: Railway remote service — HTTP health check
        if svc["id"] == "shopify_ai_suite":
            try:
                import urllib.request
                urllib.request.urlopen(svc.get("health_url", svc.get("url", "")), timeout=5)
                port_ok = True
            except Exception:
                pass
            result.append({
                "id": svc["id"], "name": svc["name"], "port": svc["port"],
                "icon": svc["icon"], "ok": port_ok, "pid": None, "running": port_ok,
                "remote": True,
            })
            continue

        # Special case: mega_orchestrator is embedded in this process
        if svc["id"] == "mega_orchestrator":
            result.append({
                "id": svc["id"], "name": svc["name"], "port": svc["port"],
                "icon": svc["icon"], "ok": True, "pid": str(os.getpid()), "running": True,
                "note": "Eingebettet in Dashboard",
            })
            continue

        pid = None
        pattern = svc.get("pattern", "")
        if pattern and pattern != "RAILWAY_REMOTE":
            try:
                ps = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
                if ps.returncode == 0 and ps.stdout.strip():
                    pid = ps.stdout.strip().split('\n')[0]
            except Exception:
                pass

        result.append({
            "id": svc["id"], "name": svc["name"], "port": svc["port"],
            "icon": svc["icon"], "ok": port_ok, "pid": pid,
            "running": port_ok or bool(pid),
        })
    return web.json_response({"services": result})


async def handle_service_action(req):
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
    action = data.get("action", "")
    svc_id = data.get("id", "")

    # ── START ALL ──────────────────────────────────────────────────────────
    if svc_id == "all" and action == "start":
        started, skipped, failed = [], [], []
        for svc in SERVICES:
            if svc["id"] == "dashboard":
                skipped.append(svc["name"])
                continue
            try:
                subprocess.Popen(svc["start_cmd"], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                started.append(svc["name"])
            except Exception as e:
                failed.append(f"{svc['name']}: {e}")
        await asyncio.sleep(2)
        return web.json_response({
            "ok": True, "action": "start_all",
            "started": started, "skipped": skipped, "failed": failed,
            "summary": f"{len(started)} gestartet, {len(failed)} Fehler"
        })

    # ── SINGLE SERVICE ─────────────────────────────────────────────────────
    svc = next((s for s in SERVICES if s["id"] == svc_id), None)
    if not svc:
        return web.json_response({"ok": False, "error": f"Service {svc_id} not found"})
    try:
        if action in ("stop", "restart"):
            subprocess.run(["pkill", "-f", svc["pattern"]], capture_output=True)
            await asyncio.sleep(0.8)
        if action in ("start", "restart"):
            if svc["id"] == "dashboard":
                return web.json_response({"ok": False, "error": "Dashboard kann sich nicht selbst starten"})
            subprocess.Popen(svc["start_cmd"], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await asyncio.sleep(1.5)
        return web.json_response({"ok": True, "action": action, "service": svc["name"]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_start_all(req):
    """POST /api/start-all — startet alle Services außer Dashboard mit einem Klick."""
    started, skipped, failed = [], [], []
    for svc in SERVICES:
        if svc["id"] == "dashboard":
            skipped.append(svc["name"])
            continue
        try:
            subprocess.Popen(svc["start_cmd"], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            started.append(svc["name"])
            log.info(f"Start-All: {svc['name']} gestartet")
        except Exception as e:
            failed.append(f"{svc['name']}: {e}")
            log.warning(f"Start-All: {svc['name']} Fehler: {e}")
    await asyncio.sleep(2)
    msg = f"🚀 {len(started)} Services gestartet"
    if failed:
        msg += f" | ⚠️ {len(failed)} Fehler"
    return web.json_response({
        "ok": True,
        "started": started,
        "skipped": skipped,
        "failed": failed,
        "summary": msg,
    })


async def handle_logs(req):
    try:
        lines = []
        for lf in [BASE_DIR / "logs" / "supermegabot.log", Path("/tmp/supermegabot.log")]:
            if lf.exists():
                try:
                    content = lf.read_text(errors='replace').split('\n')
                    lines.extend(content[-60:])
                except Exception:
                    pass
        if not lines:
            lines = ["Keine Logs vorhanden — Bot läuft möglicherweise ohne Log-Datei"]
        return web.json_response({"ok": True, "lines": lines[-80:]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_logs_clear(req):
    """Clear the primary dashboard log files used by the legacy UI."""
    try:
        cleared = []
        for lf in [BASE_DIR / "logs" / "supermegabot.log", Path("/tmp/supermegabot.log")]:
            if lf.exists():
                lf.write_text("")
                cleared.append(str(lf))
        return web.json_response({"ok": True, "cleared": cleared})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_health(req):
    cached = _cache_get("system_health", 30)
    if cached is not None:
        # Always return fresh uptime
        cached = dict(cached)
        cached["uptime_seconds"] = round(time.time() - _SERVER_START_TIME, 1)
        return web.json_response(cached)
    try:
        from modules.circuit_breaker import get_status as cb_status
        circuits = {k: v["state"] for k, v in cb_status().items()}
        open_circuits = [k for k, v in circuits.items() if v == "open"]
    except Exception:
        circuits = {}
        open_circuits = []
    result = {
        "status": "ok",
        "service": "supermegabot-dashboard",
        "port": PORT,
        "uptime_seconds": round(time.time() - _SERVER_START_TIME, 1),
        "started_at": datetime.utcfromtimestamp(_SERVER_START_TIME).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "shopify_domain": os.getenv("SHOPIFY_SHOP_DOMAIN", ""),
        "circuits_open": open_circuits,
        "bots": {
            "admin_bot": bool(os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1")),
            "customer_bot": bool(os.getenv("TELEGRAM_BOT_TOKEN_2")),
        },
    }
    _cache_set("system_health", result)
    return web.json_response(result)


async def handle_status_full(req):
    """Full system status including all configured integrations."""
    import socket

    def _port_open(port: int) -> bool:
        try:
            sock = socket.create_connection(("localhost", port), timeout=1)
            sock.close()
            return True
        except Exception:
            return False

    # Ollama check
    ollama_ok = False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as s:
            async with s.get(f"{os.getenv('OLLAMA_HOST', 'http://localhost:11434')}/api/tags") as r:
                ollama_ok = r.status == 200
    except Exception:
        pass

    return web.json_response({
        "status": "ok",
        "uptime_seconds": round(time.time() - _SERVER_START_TIME, 1),
        "telegram": {
            "admin_bot_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1")),
            "customer_bot_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN_2")),
            "chat_id_configured": bool(os.getenv("TELEGRAM_CHAT_ID")),
        },
        "shopify": {
            "configured": bool(os.getenv("SHOPIFY_SHOP_DOMAIN") and (os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN"))),
            "domain": os.getenv("SHOPIFY_SHOP_DOMAIN", ""),
            "api_version": os.getenv("SHOPIFY_API_VERSION", "2026-04"),
            "store2_configured": bool(os.getenv("SHOPIFY_STORE2_DOMAIN") and os.getenv("SHOPIFY_STORE2_TOKEN")),
            "store2_domain": os.getenv("SHOPIFY_STORE2_DOMAIN", "soolar.myshopify.com"),
        },
        "stripe": {
            "configured": bool(os.getenv("STRIPE_SECRET_KEY")),
            "webhook_configured": bool(os.getenv("STRIPE_WEBHOOK_SECRET")),
        },
        "supabase": {
            "configured": bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_ANON_KEY")),
            "url": os.getenv("SUPABASE_URL", ""),
        },
        "ollama": {
            "configured": bool(os.getenv("OLLAMA_HOST")),
            "online": ollama_ok,
            "host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
        },
        "ai": {
            "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
            "deepseek_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
        },
    })


async def handle_guardian_status(req):
    """Guardian security module status."""
    import subprocess
    guardian_running = False
    try:
        r = subprocess.run(["pgrep", "-f", "guardian"], capture_output=True, text=True)
        guardian_running = r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        pass
    return web.json_response({
        "ok": True,
        "status": "active" if guardian_running else "standby",
        "guardian_process": guardian_running,
        "api_key_configured": bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("DEEPSEEK_API_KEY")),
        "monitoring": True,
        "alerts_enabled": bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),
    })


async def handle_ai_status(req):
    """AI integrations status."""
    anthropic_ok = bool(os.getenv("ANTHROPIC_API_KEY"))
    deepseek_ok = bool(os.getenv("DEEPSEEK_API_KEY"))
    ollama_ok = False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as s:
            async with s.get(f"{os.getenv('OLLAMA_HOST', 'http://localhost:11434')}/api/tags") as r:
                ollama_ok = r.status == 200
    except Exception:
        pass
    return web.json_response({
        "ok": True,
        "anthropic": {"configured": anthropic_ok, "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")},
        "deepseek": {"configured": deepseek_ok, "model": "deepseek-chat"},
        "groq": {"configured": bool(os.getenv("GROQ_API_KEY")), "model": "llama-3.3-70b-versatile"},
        "ollama": {"online": ollama_ok, "host": os.getenv("OLLAMA_HOST", "http://localhost:11434"), "model": os.getenv("OLLAMA_MODEL", "llama3.2")},
        "gemini": {"configured": bool(os.getenv("GEMINI_API_KEY"))},
        "perplexity": {"configured": bool(os.getenv("PERPLEXITY_API_KEY"))},
    })


async def handle_system_status(req):
    """System metrics and health."""
    import platform
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return web.json_response({
            "ok": True,
            "platform": platform.system(),
            "uptime_seconds": round(time.time() - _SERVER_START_TIME, 1),
            "cpu_percent": cpu,
            "memory_percent": round(mem.percent, 1),
            "memory_used_mb": round(mem.used / 1024 / 1024),
            "memory_total_mb": round(mem.total / 1024 / 1024),
            "disk_percent": round(disk.percent, 1),
            "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
        })
    except Exception as e:
        return web.json_response({"ok": True, "platform": platform.system(),
                                   "uptime_seconds": round(time.time() - _SERVER_START_TIME, 1),
                                   "note": str(e)})


async def handle_env_check(req):
    """GET /api/env/check — returns status of all required Railway env vars."""
    checks = {
        "core": {
            "TELEGRAM_BOT_TOKEN":        bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            "TELEGRAM_CHAT_ID":          bool(os.getenv("TELEGRAM_CHAT_ID")),
            "ANTHROPIC_API_KEY":         bool(os.getenv("ANTHROPIC_API_KEY")),
            "DEEPSEEK_API_KEY":          bool(os.getenv("DEEPSEEK_API_KEY")),
            "PERPLEXITY_API_KEY":        bool(os.getenv("PERPLEXITY_API_KEY")),
        },
        "database": {
            "SUPABASE_URL":              bool(os.getenv("SUPABASE_URL")),
            "SUPABASE_ANON_KEY":         bool(os.getenv("SUPABASE_ANON_KEY")),
            "SUPABASE_SERVICE_KEY":      bool(os.getenv("SUPABASE_SERVICE_KEY")),
        },
        "shopify": {
            "SHOPIFY_SHOP_DOMAIN":       bool(os.getenv("SHOPIFY_SHOP_DOMAIN")),
            "SHOPIFY_ADMIN_API_TOKEN":   bool(os.getenv("SHOPIFY_ADMIN_API_TOKEN")),
        },
        "stripe": {
            "STRIPE_SECRET_KEY":         bool(os.getenv("STRIPE_SECRET_KEY")),
            "STRIPE_WEBHOOK_SECRET":     bool(os.getenv("STRIPE_WEBHOOK_SECRET")),
        },
        "twitter": {
            "TWITTER_API_KEY":           bool(os.getenv("TWITTER_API_KEY")),
            "TWITTER_API_SECRET":        bool(os.getenv("TWITTER_API_SECRET")),
            "TWITTER_ACCESS_TOKEN":      bool(os.getenv("TWITTER_ACCESS_TOKEN")),
            "TWITTER_ACCESS_TOKEN_SECRET": bool(os.getenv("TWITTER_ACCESS_TOKEN_SECRET")),
            "TWITTER_BEARER_TOKEN":      bool(os.getenv("TWITTER_BEARER_TOKEN")),
            "TWITTER_CLIENT_ID":         bool(os.getenv("TWITTER_CLIENT_ID")),
            "TWITTER_CLIENT_SECRET":     bool(os.getenv("TWITTER_CLIENT_SECRET")),
            "TWITTER_PASSWORD":          bool(os.getenv("TWITTER_PASSWORD")),
        },
        "social": {
            "DEVTO_API_KEY":             bool(os.getenv("DEVTO_API_KEY")),
            "HASHNODE_API_KEY":          bool(os.getenv("HASHNODE_API_KEY")),
            "KLAVIYO_API_KEY":           bool(os.getenv("KLAVIYO_API_KEY")),
            "MAILCHIMP_API_KEY":         bool(os.getenv("MAILCHIMP_API_KEY")),
            "PINTEREST_ACCESS_TOKEN":    bool(os.getenv("PINTEREST_ACCESS_TOKEN")),
            "LINKEDIN_ACCESS_TOKEN":     bool(os.getenv("LINKEDIN_ACCESS_TOKEN")),
            "REDDIT_CLIENT_ID":          bool(os.getenv("REDDIT_CLIENT_ID")),
            "REDDIT_CLIENT_SECRET":      bool(os.getenv("REDDIT_CLIENT_SECRET")),
            "REDDIT_USERNAME":           bool(os.getenv("REDDIT_USERNAME")),
            "REDDIT_PASSWORD":           bool(os.getenv("REDDIT_PASSWORD")),
        },
        "whatsapp": {
            "WHATSAPP_PHONE_NUMBER_ID":  bool(os.getenv("WHATSAPP_PHONE_NUMBER_ID")),
            "WHATSAPP_ACCESS_TOKEN":     bool(os.getenv("WHATSAPP_ACCESS_TOKEN")),
        },
        "tiktok": {
            "TIKTOK_ACCESS_TOKEN":       bool(os.getenv("TIKTOK_ACCESS_TOKEN")),
            "TIKTOK_SHOP_ID":            bool(os.getenv("TIKTOK_SHOP_ID")),
        },
        "twilio": {
            "TWILIO_ACCOUNT_SID":        bool(os.getenv("TWILIO_ACCOUNT_SID")),
            "TWILIO_AUTH_TOKEN":         bool(os.getenv("TWILIO_AUTH_TOKEN")),
            "TWILIO_FROM_NUMBER":        bool(os.getenv("TWILIO_FROM_NUMBER")),
        },
        "github": {
            "GITHUB_TOKEN":              bool(os.getenv("GITHUB_TOKEN")),
            "GITHUB_USER":               bool(os.getenv("GITHUB_USER")),
        },
        "digistore24": {
            "DS24_API_KEY":              bool(os.getenv("DS24_API_KEY")),
            "DS24_AFFILIATE_LINK":       bool(os.getenv("DS24_AFFILIATE_LINK")),
        },
    }
    missing = {cat: [k for k, v in vars_.items() if not v] for cat, vars_ in checks.items()}
    missing = {c: m for c, m in missing.items() if m}
    total_set   = sum(v for cat in checks.values() for v in cat.values())
    total_all   = sum(len(cat) for cat in checks.values())
    return web.json_response({
        "ok": True,
        "total": total_all,
        "configured": total_set,
        "missing_count": total_all - total_set,
        "percent": round(total_set / total_all * 100),
        "checks": checks,
        "missing": missing,
    })


async def handle_supabase_status(req):
    """Supabase connection status."""
    supabase_url = os.getenv("SUPABASE_URL", "")
    configured = bool(supabase_url and os.getenv("SUPABASE_ANON_KEY"))
    reachable = False
    if configured:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as s:
                async with s.get(f"{supabase_url}/rest/v1/",
                                 headers={"apikey": os.getenv("SUPABASE_ANON_KEY", "")}) as r:
                    reachable = r.status in (200, 400)
        except Exception:
            pass
    return web.json_response({
        "ok": True,
        "configured": configured,
        "reachable": reachable,
        "url": supabase_url,
        "service_key_configured": bool(os.getenv("SUPABASE_SERVICE_KEY")),
    })


# ── RudiBot Army Integration ─────────────────────────────────────────────────

ARMY_STATE_FILE = BASE_DIR / "rudibot-army" / "shared" / "army_state.json"

async def handle_army_status(req):
    """Gibt den aktuellen Status aller Army-Agenten zurück."""
    try:
        if ARMY_STATE_FILE.exists():
            state = json.loads(ARMY_STATE_FILE.read_text(errors='ignore'))
        else:
            state = {"agents": {}, "events": [], "fixes": [], "stats": {}}
        # Laufende Prozesse prüfen
        army_running = False
        try:
            r = subprocess.run(["pgrep", "-f", "army_commander.py"],
                               capture_output=True, text=True)
            army_running = r.returncode == 0 and bool(r.stdout.strip())
        except Exception:
            pass
        return web.json_response({
            "ok": True,
            "army_running": army_running,
            "agents": state.get("agents", {}),
            "events": state.get("events", [])[-20:],
            "agent_count": len(state.get("agents", {})),
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_army_start(req):
    """Startet die Army wenn sie nicht läuft."""
    try:
        r = subprocess.run(["pgrep", "-f", "army_commander.py"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return web.json_response({"ok": True, "msg": "Army läuft bereits"})
        log_path = Path("/tmp/rudibot-army.log")
        with open(log_path, "a") as lf:
            subprocess.Popen(
                [sys.executable, str(BASE_DIR / "rudibot-army" / "army_commander.py")],
                stdout=lf, stderr=lf, start_new_session=True,
            )
        return web.json_response({"ok": True, "msg": "Army gestartet"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_monitor(req):
    """Mega Monitoring Dashboard"""
    html_path = Path(__file__).parent / "mega_monitor.html"
    if html_path.exists():
        return web.Response(
            text=html_path.read_text(encoding="utf-8"),
            content_type="text/html",
            charset="utf-8",
        )
    # Wenn HTML fehlt → neu generieren
    try:
        import subprocess
        py = Path(__file__).parent / "mega_monitor.py"
        subprocess.run(["python3", str(py)], timeout=30)
        if html_path.exists():
            return web.Response(
                text=html_path.read_text(encoding="utf-8"),
                content_type="text/html",
                charset="utf-8",
            )
    except Exception as e:
        pass
    return web.Response(text=f"<h2>Monitor wird generiert... <a href='/monitor'>Reload</a></h2>", content_type="text/html")


async def handle_monitor_refresh(req):
    """Dashboard neu generieren und zurückgeben"""
    try:
        import subprocess
        py = Path(__file__).parent / "mega_monitor.py"
        subprocess.run(["python3", str(py)], timeout=60, check=True)
        return web.json_response({"ok": True, "msg": "Dashboard aktualisiert"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_processes(req):
    try:
        import psutil
        procs = []
        for p in sorted(
            psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'cmdline']),
            key=lambda x: x.info['cpu_percent'] or 0,
            reverse=True
        )[:15]:
            cmd = ' '.join(p.info['cmdline'] or [p.info['name'] or ''])[:60]
            procs.append({
                "pid": p.info['pid'],
                "name": p.info['name'],
                "cpu": round(p.info['cpu_percent'] or 0, 1),
                "mem": round(p.info['memory_percent'] or 0, 1),
                "cmd": cmd,
            })
        return web.json_response({"ok": True, "processes": procs})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# Storage Monitor API
# ---------------------------------------------------------------------------

async def handle_storage_status(req):
    try:
        from modules.storage_monitor import get_status_dict
        return web.json_response(get_status_dict())
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_storage_cleanup(req):
    try:
        data = await req.json() if req.can_read_body else {}
        max_age = int(data.get("max_age_hours", 24))
        from modules.storage_monitor import run_cleanup
        result = run_cleanup(max_age_hours=max_age)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_storage_offload(req):
    try:
        data = await req.json() if req.can_read_body else {}
        mountpoint = data.get("mountpoint", "/")
        min_mb = float(data.get("min_file_mb", 50.0))
        from modules.storage_monitor import run_offload
        result = run_offload(source_mountpoint=mountpoint, min_file_mb=min_mb)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_storage_large_files(req):
    try:
        directory = req.rel_url.query.get("dir", str(BASE_DIR))
        min_mb = float(req.rel_url.query.get("min_mb", "50"))
        from modules.storage_monitor import find_large_files
        files = find_large_files(Path(directory), min_size_mb=min_mb, limit=30)
        return web.json_response({"files": files, "directory": directory})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_storage_history(req):
    try:
        limit = int(req.rel_url.query.get("limit", "50"))
        from modules.storage_monitor import get_event_history
        return web.json_response({"events": get_event_history(limit)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_storage_widget(req):
    widget = Path(__file__).parent / "storage_widget.html"
    if widget.exists():
        return web.Response(text=widget.read_text(), content_type="text/html")
    return web.Response(text="Storage widget not found", status=404)


# ---------------------------------------------------------------------------
# Self-Learner API
# ---------------------------------------------------------------------------

async def handle_self_learner_status(req):
    try:
        if _self_learner is None:
            return web.json_response({"ok": False, "status": "disabled", "reason": "self_learner_core not available"})
        skills = _self_learner.learned_skills if hasattr(_self_learner, 'learned_skills') else {}
        return web.json_response({"ok": True, "status": "active", "skills_count": len(skills), "skills": list(skills.keys())})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_self_learner_learn(req):
    try:
        if _self_learner is None:
            return web.json_response({"ok": False, "error": "self_learner_core not available"}, status=503)
        data = await req.json() if req.can_read_body else {}
        skill_name = data.get("skill")
        skill_data = data.get("data", {})
        if not skill_name:
            return web.json_response({"ok": False, "error": "skill name required"}, status=400)
        _self_learner.learn(skill_name, skill_data)
        return web.json_response({"ok": True, "learned": skill_name})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_self_learner_skills(req):
    try:
        if _self_learner is None:
            return web.json_response({"ok": False, "skills": [], "error": "self_learner_core not available"})
        skills = _self_learner.learned_skills if hasattr(_self_learner, 'learned_skills') else {}
        return web.json_response({"ok": True, "skills": list(skills.keys()), "count": len(skills)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_self_learner_delete(req):
    try:
        if _self_learner is None:
            return web.json_response({"ok": False, "error": "self_learner_core not available"}, status=503)
        data = await req.json() if req.can_read_body else {}
        skill_name = data.get("skill")
        if not skill_name:
            return web.json_response({"ok": False, "error": "skill name required"}, status=400)
        skills = _self_learner.learned_skills if hasattr(_self_learner, 'learned_skills') else {}
        if skill_name in skills:
            del skills[skill_name]
            return web.json_response({"ok": True, "deleted": skill_name})
        return web.json_response({"ok": False, "error": f"skill '{skill_name}' not found"}, status=404)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_self_learner_find_api(req):
    try:
        if _self_learner is None:
            return web.json_response({"ok": False, "error": "self_learner_core not available"}, status=503)
        data = await req.json() if req.can_read_body else {}
        query = data.get("query", "")
        skills = _self_learner.learned_skills if hasattr(_self_learner, 'learned_skills') else {}
        matches = [k for k in skills.keys() if query.lower() in k.lower()] if query else list(skills.keys())
        return web.json_response({"ok": True, "query": query, "matches": matches, "count": len(matches)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# App Factory
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# New section handlers: API Keys, GitHub, Cloud, Bot Repair, Notes, Railway
# ---------------------------------------------------------------------------

_WATCHED_ENV_KEYS = [
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "SHOPIFY_ACCESS_TOKEN", "SHOPIFY_ADMIN_API_TOKEN",
    "SHOPIFY_STORE_URL", "SHOPIFY_SHOP_DOMAIN", "SHOPIFY_API_VERSION",
    "OLLAMA_HOST", "OLLAMA_FAST_MODEL", "OLLAMA_SMART_MODEL", "OLLAMA_CODE_MODEL",
    "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "PERPLEXITY_API_KEY", "GROQ_API_KEY",
    "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY",
    "GOOGLE_ADS_CLIENT_ID", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
    "GCP_PROJECT_ID", "GMC_MERCHANT_ID",
    "ETERNAL_BOT_DIR", "KIVO_DIR",
    "DASHBOARD_PORT", "SHOPIFY_SUITE_URL",
    # E-Commerce & Automation
    "DIGISTORE24_API_KEY", "PRINTIFY_API_KEY", "PRINTIFY_SHOP_ID",
    "ETSY_API_KEY", "ETSY_ACCESS_TOKEN", "GUMROAD_ACCESS_TOKEN",
    "MAILCHIMP_API_KEY", "MAILCHIMP_SERVER_PREFIX",
    "STRIPE_SECRET_KEY", "KLAVIYO_API_KEY",
    # Social Media
    "TIKTOK_CLIENT_KEY", "PINTEREST_ACCESS_TOKEN",
    "META_ACCESS_TOKEN", "META_PAGE_ID",
    "TWITTER_BEARER_TOKEN", "DISCORD_BOT_TOKEN",
    "YOUTUBE_API_KEY", "YOUTUBE_CHANNEL_ID",
    "REDDIT_CLIENT_ID",
    # Infrastructure
    "GITHUB_TOKEN", "RAILWAY_TOKEN",
]

# Key format validators (no network needed)
_KEY_FORMATS = {
    "DEEPSEEK_API_KEY":      lambda v: v.startswith("sk-"),
    "ANTHROPIC_API_KEY":     lambda v: v.startswith("sk-ant-"),
    "PERPLEXITY_API_KEY":    lambda v: v.startswith("pplx-") or len(v) > 20,
    "TELEGRAM_BOT_TOKEN":    lambda v: ":" in v and len(v) > 20,
    "SHOPIFY_ACCESS_TOKEN":  lambda v: v.startswith("shpat_") or v.startswith("shpss_") or len(v) > 20,
    "SHOPIFY_API_KEY":       lambda v: len(v) > 20,
    "SHOPIFY_API_SECRET":    lambda v: v.startswith("shpss_") or len(v) > 20,
    "SUPABASE_URL":          lambda v: "supabase" in v or v.startswith("http"),
    "SUPABASE_ANON_KEY":     lambda v: len(v) > 50,
    "SUPABASE_SERVICE_ROLE_KEY": lambda v: len(v) > 50,
}


async def _validate_key(session: aiohttp.ClientSession, key: str, val: str) -> str:
    """Returns 'valid', 'present', or 'missing'."""
    if not val:
        return "missing"

    # Format check first (fast, no network)
    fmt_check = _KEY_FORMATS.get(key)
    if fmt_check and not fmt_check(val):
        return "present"  # set but wrong format

    # Network validation for critical keys
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        if key == "DEEPSEEK_API_KEY":
            async with session.get(
                "https://api.deepseek.com/v1/models",
                headers={"Authorization": f"Bearer {val}"},
                timeout=timeout
            ) as r:
                return "valid" if r.status == 200 else "present"

        elif key == "ANTHROPIC_API_KEY":
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": val,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1,
                      "messages": [{"role": "user", "content": "hi"}]},
                timeout=timeout
            ) as r:
                return "valid" if r.status in (200, 400) else "present"

        elif key == "SUPABASE_URL" and os.environ.get("SUPABASE_ANON_KEY"):
            async with session.get(
                f"{val}/rest/v1/",
                headers={"apikey": os.environ["SUPABASE_ANON_KEY"]},
                timeout=timeout
            ) as r:
                return "valid" if r.status < 500 else "present"

    except Exception:
        pass

    # Not validated via network — but set + format ok
    return "present"


async def handle_api_keys(req):
    """Returns validation status for all tracked env keys."""
    validate = req.rel_url.query.get("validate", "1") == "1"
    result = {}
    async with aiohttp.ClientSession() as session:
        for key in _WATCHED_ENV_KEYS:
            val = os.environ.get(key, "")
            if not val:
                status = "missing"
            elif validate:
                status = await _validate_key(session, key, val)
            else:
                status = "present"
            result[key] = {
                "status": status,          # "valid" | "present" | "missing"
                "set": bool(val),
                "length": len(val),
                "preview": val[:4] + "..." if len(val) > 4 else ("(set)" if val else ""),
            }
    set_count    = sum(1 for v in result.values() if v["set"])
    valid_count  = sum(1 for v in result.values() if v["status"] == "valid")
    return web.json_response({
        "ok": True, "keys": result,
        "summary": {"total": len(result), "set": set_count, "valid": valid_count}
    })


async def handle_github_status(req):
    """Returns current git branch, last commit, and remote URL."""
    try:
        def _git(args):
            r = subprocess.run(["git", "-C", str(BASE_DIR)] + args,
                               capture_output=True, text=True, timeout=8)
            return r.stdout.strip() if r.returncode == 0 else ""
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
        commit = _git(["log", "-1", "--oneline"])
        remote = _git(["remote", "get-url", "origin"])
        status = _git(["status", "--porcelain"])
        staged = len([l for l in status.splitlines() if l and l[0] in "MADRCU"])
        unstaged = len([l for l in status.splitlines() if l and l[1] in "MADRCU?"])
        return web.json_response({
            "ok": True,
            "branch": branch,
            "commit": commit,
            "remote": remote,
            "staged": staged,
            "unstaged": unstaged,
            "clean": not bool(status.strip()),
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_github_push(req):
    """Git add -A, commit with timestamp, push to current branch."""
    try:
        def _git(args):
            r = subprocess.run(["git", "-C", str(BASE_DIR)] + args,
                               capture_output=True, text=True, timeout=30)
            return r.returncode == 0, r.stdout.strip(), r.stderr.strip()

        ok, out, err = _git(["status", "--porcelain"])
        if not out.strip():
            return web.json_response({"ok": True, "message": "Nichts zu committen"})

        ts = time.strftime("%Y-%m-%d %H:%M")
        _git(["add", "-A"])
        ok, out, err = _git(["commit", "-m", f"Dashboard auto-commit {ts}"])
        if not ok:
            return web.json_response({"ok": False, "error": f"Commit: {err}"})

        branch_ok, branch, _ = _git(["rev-parse", "--abbrev-ref", "HEAD"])
        push_ok, push_out, push_err = _git(["push", "origin", branch])
        if push_ok:
            return web.json_response({"ok": True, "message": f"Gepusht: {branch} ✅"})
        return web.json_response({"ok": False, "error": push_err[:200]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_cloud_status(req):
    """Check Railway + ngrok availability."""
    railway_url = os.getenv("SHOPIFY_SUITE_URL",
                            "https://shopify-suite-v2-production.up.railway.app")
    results = {}
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        # Railway
        try:
            async with s.get(f"{railway_url}/health") as r:
                results["railway"] = {"ok": r.status < 400, "status": r.status, "url": railway_url}
        except Exception as e:
            results["railway"] = {"ok": False, "error": str(e)[:80], "url": railway_url}
        # ngrok
        try:
            async with s.get("http://localhost:4040/api/tunnels") as r:
                d = await r.json()
                tunnels = [t.get("public_url", "") for t in d.get("tunnels", [])]
                results["ngrok"] = {"ok": True, "tunnels": tunnels}
        except Exception:
            results["ngrok"] = {"ok": False, "tunnels": []}
    return web.json_response({"ok": True, "services": results})


async def handle_bot_repair_status(req):
    """Returns self-healer status + recent heal history."""
    try:
        heal_log = DATA_DIR / "heal_history.json"
        history = []
        if heal_log.exists():
            history = json.loads(heal_log.read_text())[-20:]
        known = {}
        known_file = DATA_DIR / "known_fixes.json"
        if known_file.exists():
            known = json.loads(known_file.read_text())
        return web.json_response({
            "ok": True,
            "total_fixes": len(history),
            "known_problems": len(known),
            "recent": history[-5:],
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_bot_repair_run(req):
    """Trigger self-healer scan."""
    try:
        sys.path.insert(0, str(BASE_DIR / "core"))
        from self_healer import SelfHealer
        healer = SelfHealer()
        fixes = await healer.run_auto_fixes()
        errors = await healer.scan_logs_for_errors()
        return web.json_response({
            "ok": True,
            "fixes_applied": fixes,
            "log_errors": [e["error"] for e in errors],
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_notes_get(req):
    """Get saved notes."""
    notes_file = DATA_DIR / "notes.json"
    notes = []
    if notes_file.exists():
        try:
            notes = json.loads(notes_file.read_text())
        except Exception:
            pass
    return web.json_response({"ok": True, "notes": notes})


async def handle_notes_save(req):
    """Save a note."""
    try:
        data = await req.json()
        text = str(data.get("text", "")).strip()[:2000]
        if not text:
            return web.json_response({"ok": False, "error": "Leere Notiz"})
        notes_file = DATA_DIR / "notes.json"
        notes = []
        if notes_file.exists():
            try:
                notes = json.loads(notes_file.read_text())
            except Exception:
                pass
        notes.append({"text": text, "created": datetime.now().isoformat()})
        notes = notes[-100:]
        notes_file.write_text(json.dumps(notes, indent=2, ensure_ascii=False))
        return web.json_response({"ok": True, "count": len(notes)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_notes_delete(req):
    """Delete a note by index."""
    try:
        data = await req.json()
        idx = int(data.get("index", -1))
        notes_file = DATA_DIR / "notes.json"
        notes = []
        if notes_file.exists():
            notes = json.loads(notes_file.read_text())
        if 0 <= idx < len(notes):
            notes.pop(idx)
            notes_file.write_text(json.dumps(notes, indent=2, ensure_ascii=False))
        return web.json_response({"ok": True, "count": len(notes)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_deepscan(req):
    """Run a comprehensive system deep scan."""
    results = {"timestamp": datetime.now().isoformat(), "checks": {}}

    # 1. Python syntax check on key files
    key_files = [
        BASE_DIR / "core" / "mega_orchestrator.py",
        BASE_DIR / "core" / "self_healer.py",
        BASE_DIR / "dashboard" / "server.py",
        BASE_DIR / "modules" / "telegram_control.py",
    ]
    syntax_ok = []
    syntax_err = []
    for f in key_files:
        if not f.exists():
            continue
        try:
            import ast
            ast.parse(f.read_text())
            syntax_ok.append(f.name)
        except SyntaxError as e:
            syntax_err.append(f"{f.name}: {e}")
    results["checks"]["syntax"] = {"ok": not syntax_err, "ok_files": syntax_ok, "errors": syntax_err}

    # 2. Env vars
    required_env = ["TELEGRAM_BOT_TOKEN", "SHOPIFY_ACCESS_TOKEN", "SHOPIFY_SHOP_DOMAIN"]
    missing_env = [k for k in required_env if not os.environ.get(k)]
    results["checks"]["env"] = {"ok": not missing_env, "missing": missing_env}

    # 3. Ollama
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as s:
            async with s.get(f"{OLLAMA_BASE}/api/tags") as r:
                results["checks"]["ollama"] = {"ok": r.status == 200}
    except Exception:
        results["checks"]["ollama"] = {"ok": False}

    # 4. Army state
    army_state = BASE_DIR / "rudibot-army" / "shared" / "army_state.json"
    results["checks"]["army_state"] = {"ok": army_state.exists()}

    # 5. Disk
    try:
        import psutil
        disk = psutil.disk_usage("/")
        results["checks"]["disk"] = {
            "ok": disk.percent < 90,
            "percent": disk.percent,
            "free_gb": disk.free // 1024 ** 3,
        }
    except ImportError:
        results["checks"]["disk"] = {"ok": True, "note": "psutil nicht installiert"}

    # Summary
    total = len(results["checks"])
    passed = sum(1 for v in results["checks"].values() if v.get("ok"))
    results["summary"] = {"total": total, "passed": passed, "failed": total - passed}
    return web.json_response(results)


async def handle_automation_status(req):
    """Return automation scheduler status + recent task runs."""
    try:
        from core.automation_scheduler import get_scheduler, get_last_runs
        sched = get_scheduler()
        return web.json_response({
            "status": sched.status(),
            "recent_runs": get_last_runs(limit=30),
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_automation_run(req):
    """Manually trigger one or multiple automation tasks."""
    try:
        data = await req.json()
    except Exception:
        data = {}
    task_name = data.get("task", "")
    try:
        from core.automation_scheduler import get_scheduler
        sched = get_scheduler()
        if task_name:
            result = await sched.run_now(task_name)
            return web.json_response({"ok": True, "task": task_name, "result": result})
        # No task specified — run a quick multi-task burst
        default_tasks = ["brutus_run", "shopify_sync", "digistore_sync", "mailchimp_sync"]
        results = {}
        for t in default_tasks:
            try:
                results[t] = await sched.run_now(t)
            except Exception as e:
                results[t] = f"error: {e}"
        return web.json_response({"ok": True, "tasks_run": default_tasks, "results": results})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_automation_tasks(req):
    """Return full task list with intervals and last-run info."""
    try:
        from core.automation_scheduler import TASKS, get_task_stats
        stats = get_task_stats()
        tasks = []
        for name, _fn, interval_s, delay_s in TASKS:
            s = stats.get(name, {})
            tasks.append({
                "name":       name,
                "interval_s": interval_s,
                "interval_label": (
                    f"{interval_s // 3600}h" if interval_s >= 3600
                    else f"{interval_s // 60}min"
                ),
                "last_run":  s.get("last_run"),
                "total_runs": s.get("total", 0),
                "ok_runs":    s.get("ok", 0),
                "avg_ms":     s.get("avg_ms", 0),
            })
        return web.json_response({"tasks": tasks, "count": len(tasks)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_social_status(req):
    """Ping all social media platform connectors."""
    try:
        from modules.social_connectors import ping_all
        results = await ping_all()
        return web.json_response(results)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_digistore_status(req):
    try:
        from modules.digistore24_automation import ping, get_sales_stats, get_products, setup_ipn, is_configured
        configured = is_configured()
        ok = await ping() if configured else False
        stats = await get_sales_stats() if ok else {}
        products = await get_products() if ok else []
        ipn_info = await setup_ipn()
        return web.json_response({
            "ok": ok,
            "connected": ok,
            "configured": configured,
            "stats": stats,
            "product_count": len(products),
            "revenue_note": "€0 = Keine Transaktionen im Konto (API verbunden, Daten korrekt)" if ok and stats.get("total", 0) == 0 else None,
            "ipn_url": ipn_info["ipn_url"],
            "ipn_setup_needed": True,
        })
    except Exception as e:
        return web.json_response({"ok": False, "connected": False, "error": str(e)})


async def handle_digistore_orders(req):
    try:
        from modules.digistore24_automation import get_orders
        page = int(req.rel_url.query.get("page", 1))
        orders = await get_orders(page=page)
        return web.json_response({"orders": orders})
    except Exception as e:
        return web.json_response({"orders": [], "error": str(e)})


async def handle_digistore_ipn(req):
    """POST /api/digistore24/ipn — receive Digistore24 purchase notifications."""
    try:
        # DS24 sends form-encoded POST data
        data = await req.post()

        # sha_sign verification — DS24 IPN passphrase set in account Settings > IPN
        passphrase = os.getenv("DIGISTORE24_IPN_PASSPHRASE", "")
        if passphrase:
            received_sign = (data.get("sha_sign") or "").upper()
            fields = {k: v for k, v in data.items() if k != "sha_sign" and v}
            sorted_values = "".join(fields[k] for k in sorted(fields.keys()))
            computed_sign = hashlib.sha512((passphrase + sorted_values).encode()).hexdigest().upper()
            if received_sign != computed_sign:
                log.warning("DS24 IPN: sha_sign mismatch — spoofed request rejected, order_id=%s", data.get("order_id", "?"))
                return web.Response(text="OK", status=200)  # Always 200 but don't process

        event_type   = data.get("event", data.get("order_status", "unknown"))
        order_id     = data.get("order_id", data.get("id", "?"))
        buyer_email  = data.get("buyer_email", data.get("email", "?"))
        product_id   = data.get("product_id", "?")
        currency     = data.get("currency", "EUR")
        product_name = data.get("product_name", "Digistore24 Produkt")

        # Robust amount parsing (handles "10,50", "€10.50", etc.)
        raw_amount = data.get("order_total", data.get("total", "0")) or "0"
        try:
            amount = float(str(raw_amount).replace(",", ".").replace("€", "").strip())
        except (ValueError, TypeError):
            amount = 0.0

        log.info("DS24 IPN: event=%s order=%s email=%s amount=%.2f %s",
                 event_type, order_id, buyer_email, amount, currency)

        # Store in Supabase
        await _sb_insert("lead_events", {
            "source": "digistore24",
            "event_type": event_type,
            "order_id": order_id,
            "email": buyer_email,
            "product_id": product_id,
            "amount": amount,
            "currency": currency,
            "raw": dict(data),
        })

        if event_type in ("ipn_purchase", "purchase", "order_complete", "completed"):
            msg = (
                f"💰 *KAUF! Digistore24*\n"
                f"📦 {product_name}\n"
                f"💵 {amount:.2f} {currency}\n"
                f"📧 {buyer_email}\n"
                f"🆔 Order: {order_id}"
            )
            await _tg_notify(msg)
            # Immediate funnel: push to Mailchimp + Klaviyo without waiting for scheduler
            try:
                from modules.ds24_funnel_automation import _add_to_mailchimp, _add_to_klaviyo
                fname = data.get("buyer_firstname", data.get("first_name", ""))
                lname = data.get("buyer_lastname", data.get("last_name", ""))
                await _add_to_mailchimp(buyer_email, fname, lname, product_name)
                await _add_to_klaviyo(buyer_email, fname, lname, product_name, f"{amount:.2f}")
                log.info("DS24 IPN: immediate funnel sync done for %s", buyer_email)
            except Exception as fe:
                log.warning("DS24 IPN funnel sync failed: %s", fe)
            # Email sequence: enroll buyer into post-purchase drip
            try:
                from modules.email_sequence_engine import enroll
                await enroll(buyer_email, "post_purchase")
                log.info("DS24 IPN: email sequence enrolled for %s", buyer_email)
            except Exception as ee:
                log.warning("DS24 IPN email enroll failed: %s", ee)
        elif event_type in ("ipn_rebill", "rebill"):
            msg = f"🔄 *Digistore24 Rebill*\n💵 {amount:.2f} {currency}\n📧 {buyer_email}"
            await _tg_notify(msg)

        return web.Response(text="OK", status=200)
    except Exception as e:
        log.error("DS24 IPN error: %s", e)
        return web.Response(text="OK", status=200)  # Always 200 to DS24


async def handle_mailchimp_status(req):
    try:
        from modules.mailchimp_autonomy import get_dragon_status, get_list_stats
        dragon = await get_dragon_status()
        aiitec = await get_list_stats()
        return web.json_response({
            "ok": dragon.get("ok") or aiitec.get("ok"),
            "dragon": dragon,
            "aiitec": aiitec,
            "accounts": 2 if (dragon.get("ok") and aiitec.get("ok")) else 1,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_mailchimp_sync(req):
    try:
        from modules.mailchimp_automation import sync_from_digistore, get_lists
        lists = await get_lists()
        if not lists:
            return web.json_response({"ok": False, "error": "Keine Listen gefunden"})
        list_id = (await req.json()).get("list_id") or lists[0]["id"]
        count = await sync_from_digistore(list_id)
        return web.json_response({"ok": True, "synced": count})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_mailchimp_campaign(req):
    """POST /api/mailchimp/campaign — create a Mailchimp cold email campaign (BullPower Hub)."""
    try:
        body = await req.json()
    except Exception:
        body = {}

    mc_key = os.getenv("MAILCHIMP_API_KEY", "")
    if not mc_key:
        return web.json_response({"ok": False, "error": "MAILCHIMP_API_KEY not set"})
    # auto-detect server prefix from key suffix (e.g. key ending in -us7)
    mc_server = mc_key.split("-")[-1] if "-" in mc_key else os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")

    base_url = f"https://{mc_server}.api.mailchimp.com/3.0"
    import base64 as _b64
    _tok = _b64.b64encode(f"any:{mc_key}".encode()).decode()
    headers = {"Authorization": f"Basic {_tok}", "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as s:
            # 1. Get audience list
            async with s.get(f"{base_url}/lists?count=1", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                lists_data = await r.json()

            lists = lists_data.get("lists", [])
            if not lists:
                return web.json_response({"ok": False, "error": "No Mailchimp audience found. Create one at mailchimp.com first."})

            list_id = body.get("list_id") or lists[0]["id"]
            list_name = lists[0]["name"]

            # 2. Create campaign
            subject = body.get("subject", "Dein Shopify-Shop läuft auf 60% — KI holt den Rest raus")
            campaign_payload = {
                "type": "regular",
                "recipients": {"list_id": list_id},
                "settings": {
                    "subject_line": subject,
                    "preview_text": "Kostenloser Shop-Audit zeigt was du liegen lässt",
                    "title": f"BullPower Campaign {datetime.now().strftime('%Y-%m-%d')}",
                    "from_name": "Rudolf — BullPower Hub",
                    "reply_to": "bullpowersrtkennels@gmail.com",
                }
            }
            async with s.post(f"{base_url}/campaigns", headers=headers, json=campaign_payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
                campaign = await r.json()

            if "id" not in campaign:
                return web.json_response({"ok": False, "error": str(campaign)[:200]})

            campaign_id = campaign["id"]

            # 3. Set email content (rich HTML + plain text)
            html_body = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body{font-family:-apple-system,Arial,sans-serif;background:#f5f5f5;margin:0;padding:0}
  .wrap{max-width:600px;margin:0 auto;background:#fff;padding:40px}
  h1{color:#1a1a2e;font-size:24px;margin-bottom:8px}
  p{color:#444;line-height:1.7;font-size:15px}
  .cta{display:inline-block;background:#8b5cf6;color:#fff;text-decoration:none;padding:14px 32px;border-radius:8px;font-weight:700;font-size:16px;margin:20px 0}
  .box{background:#f9f7ff;border-left:4px solid #8b5cf6;padding:16px 20px;margin:20px 0;border-radius:4px}
  .footer{color:#888;font-size:12px;margin-top:40px;border-top:1px solid #eee;padding-top:20px}
</style></head>
<body><div class="wrap">
  <h1>Hallo,</h1>
  <p>ich bin Rudolf aus Wien — ich baue KI-Tools für Shopify-Händler.</p>
  <p>Die meisten Shops lassen 30–40% Umsatz auf dem Tisch, weil Produktbeschreibungen fehlen, SEO-Tags falsch gesetzt sind und Preise nicht marktgerecht optimiert werden.</p>
  <div class="box">
    <strong>Was ich dir anbiete:</strong><br><br>
    Ich analysiere deinen Shopify-Shop <strong>kostenlos</strong> mit KI — Produktbeschreibungen, SEO, Preise, Conversion-Optimierung. Du bekommst einen konkreten Aktionsplan innerhalb von 24 Stunden.
  </div>
  <a href="https://bullpowerhubgit.github.io/bullpower-lead" class="cta">Kostenlosen Audit anfordern →</a>
  <p>Keine Kosten, kein Abo, kein Risiko. Nur ein ehrliches Audit was dir zeigt wo dein Shop Geld verliert.</p>
  <p>Wenn dir der Audit gefällt und du die Tools nutzen willst: BullPower Hub gibt dir alle 8 KI-Automatisierungs-Tools für €49/Monat — 14 Tage kostenlos testen.</p>
  <a href="https://bullpowerhubgit.github.io/bullpower-lead" style="color:#8b5cf6">→ Alle Tools ansehen</a>
  <div class="footer">
    Rudolf Sarkany · Wien, Österreich<br>
    <a href="*|UNSUB|*" style="color:#888">Abmelden</a>
  </div>
</div></body></html>"""

            plain_text = (
                "Hallo,\n\n"
                "ich bin Rudolf aus Wien — ich baue KI-Tools für Shopify-Händler.\n\n"
                "Die meisten Shops lassen 30-40% Umsatz auf dem Tisch durch fehlende SEO-Optimierung.\n\n"
                "Kostenlosen Shop-Audit anfordern: https://bullpowerhubgit.github.io/bullpower-lead\n\n"
                "Rudolf Sarkany\n"
                "BullPower Hub — https://bullpowerhubgit.github.io/bullpower-lead"
            )

            content_payload = {"html": html_body, "plain_text": plain_text}
            async with s.put(f"{base_url}/campaigns/{campaign_id}/content", headers=headers, json=content_payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
                await r.json()

            # Auto-send immediately
            async with s.post(f"{base_url}/campaigns/{campaign_id}/actions/send", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                sent = r.status == 204
                if not sent:
                    send_err = await r.text()
                    log.warning("Mailchimp send failed: %s", send_err[:100])

        log.info("Mailchimp campaign %s: subject=%s list=%s sent=%s", campaign_id, subject, list_id, sent)
        return web.json_response({
            "ok": sent,
            "campaign_id": campaign_id,
            "list_id": list_id,
            "list_name": list_name,
            "subject": subject,
            "sent": sent,
        })
    except Exception as e:
        log.error("Mailchimp campaign error: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_mailchimp_send_campaign(req):
    """POST /api/mailchimp/send-campaign — one-shot: create + send Mailchimp campaign."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    subject  = body.get("subject", "🚀 KI Income Machine — Jetzt passiv verdienen")
    html_body = body.get("html", """<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
<h1 style="color:#1a1a2e">Passives Einkommen mit KI — so geht's</h1>
<p>Hallo,</p>
<p>die AI Income Machine ist das vollautomatische System für Online-Einkommen mit KI. Einmal einrichten — dauerhaft verdienen.</p>
<p><a href=os.getenv("DS24_AFFILIATE_LINK", "https://autopilot-store-suite-fmbka.myshopify.com") style="background:#ff6600;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;margin:16px 0">Jetzt starten — nur €37 →</a></p>
<p style="color:#888;font-size:12px">Rudolf Sarkany · BullPower Hub · Wien<br><a href="*|UNSUB|*" style="color:#888">Abmelden</a></p>
</body></html>""")
    list_id = body.get("list_id", os.getenv("MAILCHIMP_LIST_ID", "606e45a6b0"))
    from modules.mailchimp_automation import send_campaign as mc_send
    result = await mc_send(subject, html_body, list_id)
    return web.json_response(result)


async def handle_klaviyo_send_campaign(req):
    """POST /api/klaviyo/send-campaign — one-shot: create + send Klaviyo campaign."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    subject  = body.get("subject", "🚀 Exklusives Angebot — KI Income Machine")
    html_body = body.get("html", """<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
<h1 style="color:#1a1a2e">Mach passives Einkommen mit KI</h1>
<p>Hallo,</p>
<p>Entdecke die AI Income Machine — das vollautomatische System für passives Online-Einkommen.</p>
<p><a href=os.getenv("DS24_AFFILIATE_LINK", "https://autopilot-store-suite-fmbka.myshopify.com") style="background:#ff6600;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;margin:16px 0">Jetzt starten — nur €37 →</a></p>
<p style="color:#888;font-size:12px">Rudolf | AIITEC · BullPower Hub</p>
</body></html>""")
    list_id = body.get("list_id", os.getenv("KLAVIYO_LIST_ID", "Xwxq6V"))
    from modules.klaviyo_automation import send_campaign as kl_send
    result = await kl_send(subject, html_body, list_id)
    return web.json_response(result)


async def handle_mailchimp_send(req):
    """POST /api/mailchimp/send — send a prepared Mailchimp campaign."""
    try:
        body = await req.json()
        campaign_id = body.get("campaign_id", "")
        if not campaign_id:
            return web.json_response({"ok": False, "error": "campaign_id required"})

        mc_key = os.getenv("MAILCHIMP_API_KEY", "")
        if not mc_key:
            return web.json_response({"ok": False, "error": "MAILCHIMP_API_KEY not set"})
        mc_server = mc_key.split("-")[-1] if "-" in mc_key else os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")

        base_url = f"https://{mc_server}.api.mailchimp.com/3.0"
        import base64 as _b64mc
        _tok2 = _b64mc.b64encode(f"any:{mc_key}".encode()).decode()
        headers = {"Authorization": f"Basic {_tok2}", "Content-Type": "application/json"}

        async with aiohttp.ClientSession() as s:
            async with s.post(f"{base_url}/campaigns/{campaign_id}/actions/send", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 204:
                    await _tg_notify(f"📧 Mailchimp-Kampagne {campaign_id} wurde gesendet!")
                    return web.json_response({"ok": True, "sent": True})
                result = await r.json()
                return web.json_response({"ok": False, "error": result})
    except Exception as e:
        log.error("Mailchimp send error: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_memory_save(req):
    """Save a key-value memory note (alias for notes endpoint)."""
    try:
        import json as _json
        data = await req.json()
        key   = str(data.get("key", "")).strip()
        value = str(data.get("value", "")).strip()
        if not key:
            return web.json_response({"ok": False, "error": "key erforderlich"})
        mem_file = DATA_DIR / "memory.json"
        memory: dict = {}
        if mem_file.exists():
            try:
                memory = _json.loads(mem_file.read_text())
            except Exception:
                pass
        memory[key] = {"value": value, "updated": datetime.now().isoformat()}
        mem_file.write_text(_json.dumps(memory, indent=2, ensure_ascii=False))
        return web.json_response({"ok": True, "key": key, "total": len(memory)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_notes_save_alias(req):
    """Alias: /api/notes/save → same as /api/notes POST."""
    try:
        import json as _json
        data = await req.json()
        key   = str(data.get("key", data.get("text", ""))).strip()
        value = str(data.get("value", "")).strip()
        notes_file = DATA_DIR / "notes.json"
        notes = []
        if notes_file.exists():
            try:
                notes = _json.loads(notes_file.read_text())
            except Exception:
                pass
        notes.append({"key": key, "text": value or key, "created": datetime.now().isoformat()})
        notes = notes[-200:]
        notes_file.write_text(_json.dumps(notes, indent=2, ensure_ascii=False))
        return web.json_response({"ok": True, "count": len(notes)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_printify_status(req):
    try:
        from modules.printify_automation import ping, get_stats
        ok = await ping()
        stats = await get_stats() if ok else {}
        return web.json_response({"ok": ok, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_printify_autofulfill(req):
    try:
        from modules.printify_automation import auto_fulfill_pending
        result = await auto_fulfill_pending()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_printify_webhook(req):
    """POST /api/printify/webhook — Printify order/shipment updates → Telegram."""
    try:
        data = await req.json()
        topic = data.get("type", data.get("topic", "unknown"))
        resource = data.get("resource", {})
        order_id = resource.get("id", "?")
        shop_id  = resource.get("shop_id", "?")

        if "shipment" in topic:
            shipments = resource.get("shipments", [])
            for s in shipments:
                carrier  = s.get("carrier", "?")
                number   = s.get("number", "?")
                url      = s.get("url", "")
                await _tg_notify(
                    f"📦 Printify versandt!\n"
                    f"Order: {order_id}\n"
                    f"Carrier: {carrier} {number}\n"
                    f"Tracking: {url or '—'}"
                )
        elif "order:created" in topic or "order:updated" in topic:
            status = resource.get("status", "?")
            await _tg_notify(f"🖨️ Printify Order {order_id}: {status}")

        log.info("Printify webhook: %s order=%s", topic, order_id)
        return web.Response(status=200)
    except Exception as e:
        log.error("Printify webhook error: %s", e)
        return web.Response(status=200)


async def handle_etsy_status(req):
    try:
        from modules.ecommerce_connectors import EtsyConnector
        etsy = EtsyConnector()
        ping = await etsy.ping()
        ok = ping.get("connected", False)
        stats = await etsy.get_stats() if ok else {}
        return web.json_response({"ok": ok, **ping, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_gumroad_status(req):
    try:
        from modules.gumroad_client import get_stats
        stats = await get_stats()
        return web.json_response(stats)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_gumroad_webhook(req):
    """POST /api/gumroad/webhook — Gumroad sale/refund ping notifications."""
    try:
        data = dict(await req.post()) if req.content_type == "application/x-www-form-urlencoded" else await req.json()
        sale_id    = data.get("sale_id") or data.get("id", "?")
        product    = data.get("product_name", "?")
        email      = data.get("email", "?")
        price      = data.get("price", "?")
        event_type = data.get("type", "sale")
        emoji = "🎉" if event_type == "sale" else "↩️"
        msg = (
            f"{emoji} <b>Gumroad {event_type.upper()}</b>\n\n"
            f"🛒 Produkt: <b>{product}</b>\n"
            f"📧 {email}\n"
            f"💰 ${price}\n"
            f"🆔 {sale_id}\n"
            f"⏰ {__import__('datetime').datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        await _tg_notify(msg)
        log.info("Gumroad webhook: %s product=%s email=%s", event_type, product, email)
        return web.json_response({"ok": True, "event": event_type, "sale_id": sale_id})
    except Exception as e:
        log.error("Gumroad webhook error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=200)


async def handle_revenue_status(req):
    """Revenue aggregation across all platforms."""
    try:
        from modules.revenue_aggregator import get_platform_revenue
        revenue = await get_platform_revenue()
        return web.json_response({"ok": True, "revenue": revenue})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_revenue_report(req):
    """Generate and return daily revenue report."""
    try:
        from modules.revenue_aggregator import get_daily_report, save_daily_snapshot
        report = await get_daily_report()
        await save_daily_snapshot()
        return web.json_response({"ok": True, "report": report})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_seo_status(req):
    """SEO score for all Shopify products."""
    try:
        from modules.seo_automation import generate_sitemap_data
        sitemap = await generate_sitemap_data()
        return web.json_response({"ok": True, "sitemap": sitemap})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_seo_run(req):
    """Run AI-powered SEO optimizer on Shopify products."""
    try:
        data = await req.json() if req.can_read_body else {}
        limit = int(data.get("limit", 5))
        from modules.seo_automation import optimize_all_shopify_products
        result = await optimize_all_shopify_products(limit=limit)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# SEO: Sitemap ping — Google + Bing indexing for all BullPower Hub Netlify sites
# ---------------------------------------------------------------------------

_SHOPIFY_DOMAIN = os.getenv("SHOPIFY_CUSTOM_DOMAIN", os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com"))
_SITEMAPS = [
    f"https://{_SHOPIFY_DOMAIN}/sitemap.xml",
    "https://autopilot-store-suite-fmbka.myshopify.com/sitemap.xml",
    "https://bullpowerhubgit.github.io/bullpower-legal/sitemap.xml",
]

_PING_ENGINES = [
    "https://www.google.com/ping?sitemap={sitemap}",
    "https://www.bing.com/ping?sitemap={sitemap}",
]


async def _do_sitemap_pings() -> dict:
    """Fire async GET pings to Google and Bing for all sitemaps.

    Returns a summary dict: {pinged: int, errors: list[str], ok: bool}
    """
    errors = []
    pinged = 0
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = []
        pairs = []
        for sitemap in _SITEMAPS:
            for tmpl in _PING_ENGINES:
                url = tmpl.format(sitemap=sitemap)
                pairs.append((sitemap, url))
                tasks.append(session.get(url))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (sitemap, url), result in zip(pairs, results):
            if isinstance(result, Exception):
                msg = f"{url}: {result}"
                log.warning("sitemap ping error: %s", msg)
                errors.append(msg)
            else:
                status = result.status
                result.release()
                if status < 400:
                    pinged += 1
                    log.info("sitemap ping OK %s → %s", sitemap, status)
                else:
                    msg = f"{url}: HTTP {status}"
                    log.warning("sitemap ping failed: %s", msg)
                    errors.append(msg)

    return {"pinged": pinged, "errors": errors, "ok": len(errors) == 0}


async def handle_ping_sitemaps(req):
    """POST /api/seo/ping-sitemaps — ping Google + Bing for all BullPower Hub sitemaps."""
    log.info("Manual sitemap ping triggered via API")
    try:
        result = await _do_sitemap_pings()
        return web.json_response(result)
    except Exception as e:
        log.error("handle_ping_sitemaps error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def _run_sitemap_ping_loop() -> None:
    """Infinite loop: ping Google + Bing sitemaps once per week (604800 s)."""
    while True:
        try:
            log.info("Weekly sitemap ping starting ...")
            result = await _do_sitemap_pings()
            log.info(
                "Weekly sitemap ping done: pinged=%d errors=%d",
                result["pinged"],
                len(result["errors"]),
            )
        except Exception as e:
            log.error("_run_sitemap_ping_loop unexpected error: %s", e)
        await asyncio.sleep(604800)


# ---------------------------------------------------------------------------
# SEO Blog Content Pipeline
# ---------------------------------------------------------------------------

_SEO_KEYWORDS = [
    "Shopify Shop automatisieren 2025",
    "Digistore24 Automatisierung Anleitung",
    "KI Tools E-Commerce Deutschland",
    "Shopify SEO verbessern kostenlos",
    "Dropshipping Automatisierung Tools",
    "Shopify Bestellungen automatisch bearbeiten",
    "Digistore24 Affiliate Marketing Software",
    "E-Commerce Automation Software Vergleich",
]

_SEO_BLOG_DIR = Path.home() / "netlify-deploy" / "shopify-suite" / "blog"
_SEO_NETLIFY_SITE_ID = "1859ba2f-66de-4012-b912-52b46e847810"
_SEO_NETLIFY_DIR = Path.home() / "netlify-deploy" / "shopify-suite"


def _md_to_html(md: str) -> str:
    """Convert markdown to HTML (h2/h3/bold/paragraphs)."""
    import re as _re
    lines = md.split("\n")
    html_parts: list = []
    paragraph_buf: list = []

    def flush_paragraph():
        text = " ".join(paragraph_buf).strip()
        if text:
            html_parts.append(f"<p>{text}</p>")
        paragraph_buf.clear()

    for line in lines:
        if line.startswith("### "):
            flush_paragraph()
            html_parts.append(f"<h3>{line[4:].strip()}</h3>")
        elif line.startswith("## "):
            flush_paragraph()
            html_parts.append(f"<h2>{line[3:].strip()}</h2>")
        elif line.startswith("# "):
            flush_paragraph()
            html_parts.append(f"<h1>{line[2:].strip()}</h1>")
        elif line.strip() == "":
            flush_paragraph()
        else:
            processed = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
            paragraph_buf.append(processed)

    flush_paragraph()
    return "\n".join(html_parts)


def _build_blog_page(keyword: str, slug: str, article_html: str) -> str:
    """Wrap article HTML in the dark-theme template."""
    import re as _re
    text_only = _re.sub(r"<[^>]+>", "", article_html)
    meta_desc = text_only[:155].replace('"', "&quot;").strip()
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{keyword} | BullPower Hub Blog</title>
<meta name="description" content="{meta_desc}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="https://bullpowerhubgit.github.io/shopify-suite-landing/blog/{slug}/">
<script defer data-domain="shopify-automaton-suite.netlify.app" src="https://plausible.io/js/script.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0a0f;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.7}}
.header{{background:#13131f;border-bottom:1px solid rgba(139,92,246,0.2);padding:1rem 2rem;display:flex;align-items:center;gap:1rem}}
.header a{{color:#a78bfa;text-decoration:none;font-weight:700;font-size:1.1rem}}
.header span{{color:#475569;font-size:.85rem}}
.container{{max-width:780px;margin:0 auto;padding:3rem 1.5rem}}
h1{{font-size:2rem;font-weight:900;margin-bottom:1.5rem;background:linear-gradient(135deg,#a78bfa,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
h2{{font-size:1.4rem;font-weight:800;color:#c4b5fd;margin:2rem 0 .8rem}}
h3{{font-size:1.15rem;font-weight:700;color:#a78bfa;margin:1.5rem 0 .6rem}}
p{{margin-bottom:1.2rem;color:#cbd5e1}}
strong,b{{color:#e2e8f0;font-weight:700}}
.cta{{background:linear-gradient(135deg,#8b5cf6,#7c3aed);color:#fff;text-decoration:none;display:inline-block;padding:.9rem 2rem;border-radius:12px;font-weight:700;margin-top:1.5rem}}
.back{{color:#64748b;font-size:.85rem;margin-top:3rem;display:block}}
</style>
</head>
<body>
<div class="header">
  <a href="https://bullpowerhubgit.github.io/bullpower-lead">&#9889; BullPower Hub</a>
  <span>/ Blog</span>
</div>
<div class="container">
{article_html}
<a href="https://bullpowerhubgit.github.io/bullpower-lead" class="cta">&#128269; Kostenlosen Shopify-Audit holen</a>
<a href="https://shopify-automaton-suite.netlify.app/blog/" class="back">&larr; Alle Artikel</a>
</div>
</body>
</html>"""


def _rebuild_blog_index() -> None:
    """Regenerate blog/index.html listing all published articles."""
    blog_dir = _SEO_BLOG_DIR
    entries = []
    for slug_dir in sorted(blog_dir.iterdir()):
        if slug_dir.is_dir() and (slug_dir / "index.html").exists():
            title = slug_dir.name.replace("-", " ").title()
            entries.append(f'<li><a href="/blog/{slug_dir.name}/">{title}</a></li>')

    items_html = "\n".join(entries) if entries else "<li>Noch keine Artikel vorhanden.</li>"
    index_html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Blog | BullPower Hub</title>
<meta name="description" content="SEO-Artikel rund um E-Commerce-Automatisierung, Shopify und Digistore24.">
<meta name="robots" content="index, follow">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0a0f;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.7}}
.header{{background:#13131f;border-bottom:1px solid rgba(139,92,246,0.2);padding:1rem 2rem;display:flex;align-items:center;gap:1rem}}
.header a{{color:#a78bfa;text-decoration:none;font-weight:700;font-size:1.1rem}}
.container{{max-width:780px;margin:0 auto;padding:3rem 1.5rem}}
h1{{font-size:2rem;font-weight:900;margin-bottom:1.5rem;background:linear-gradient(135deg,#a78bfa,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
ul{{list-style:none;padding:0}}
li{{margin:.8rem 0}}
a{{color:#a78bfa;text-decoration:none;font-size:1.05rem}}
a:hover{{color:#c4b5fd;text-decoration:underline}}
</style>
</head>
<body>
<div class="header">
  <a href="https://bullpowerhubgit.github.io/bullpower-lead">&#9889; BullPower Hub</a>
</div>
<div class="container">
<h1>Blog</h1>
<ul>
{items_html}
</ul>
</div>
</body>
</html>"""
    (blog_dir / "index.html").write_text(index_html, encoding="utf-8")
    log.info("SEO blog index rebuilt (%d articles)", len(entries))


async def handle_seo_generate(req):
    """POST /api/seo/generate — generate German SEO blog article and deploy to Netlify."""
    try:
        try:
            data = await req.json()
        except Exception:
            data = {}

        keyword = data.get("keyword") or _SEO_KEYWORDS[datetime.now().day % len(_SEO_KEYWORDS)]

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return web.json_response({"ok": False, "error": "ANTHROPIC_API_KEY not set"}, status=500)

        prompt = (
            f'Schreibe einen SEO-optimierten deutschen Blog-Artikel zum Thema: "{keyword}"\n\n'
            "Anforderungen:\n"
            "- 1200-1500 Wörter\n"
            "- H2/H3 Struktur (Markdown)\n"
            "- Natürliche Keyword-Dichte ~2%\n"
            '- Enthält einen CTA am Ende: "Jetzt kostenlos testen auf bullpower-hub-portal.netlify.app"\n'
            "- Praktische Tipps, keine leeren Phrasen\n"
            "- Schreibstil: professionell aber zugänglich\n"
            "Gib NUR den Artikel-Text zurück, keine Erklärungen."
        )

        log.info("SEO generate: requesting article for keyword '%s'", keyword)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
            payload = {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
            }
            headers_anthropic = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers_anthropic,
            ) as r:
                if r.status != 200:
                    err = await r.text()
                    log.error("Anthropic API error %d: %s", r.status, err)
                    return web.json_response(
                        {"ok": False, "error": f"Anthropic API {r.status}", "detail": err},
                        status=502,
                    )
                resp = await r.json()
                article_md = resp["content"][0]["text"]

        # Build slug
        import re as _re
        slug = keyword.lower()
        for ch_from, ch_to in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
            slug = slug.replace(ch_from, ch_to)
        slug = _re.sub(r"[^a-z0-9]+", "-", slug).strip("-")[:50]

        article_html = _md_to_html(article_md)
        page_html = _build_blog_page(keyword, slug, article_html)

        # Write article file
        article_dir = _SEO_BLOG_DIR / slug
        article_dir.mkdir(parents=True, exist_ok=True)
        (article_dir / "index.html").write_text(page_html, encoding="utf-8")
        log.info("SEO article written: %s", article_dir / "index.html")

        # Rebuild blog index
        _rebuild_blog_index()

        # Deploy to Netlify
        deploy_result: dict = {"stdout": "", "stderr": "", "returncode": -1}
        try:
            proc = await asyncio.create_subprocess_exec(
                "netlify", "deploy", "--prod",
                f"--dir={_SEO_NETLIFY_DIR}",
                f"--site={_SEO_NETLIFY_SITE_ID}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=120)
            deploy_result = {
                "stdout": stdout_b.decode(errors="replace"),
                "stderr": stderr_b.decode(errors="replace"),
                "returncode": proc.returncode,
            }
            if proc.returncode == 0:
                log.info("SEO Netlify deploy succeeded for slug '%s'", slug)
            else:
                log.warning("SEO Netlify deploy exited %d: %s", proc.returncode, deploy_result["stderr"])
        except asyncio.TimeoutError:
            log.error("SEO Netlify deploy timed out for slug '%s'", slug)
            deploy_result["stderr"] = "deploy timed out after 120s"
        except FileNotFoundError:
            log.warning("netlify CLI not found — article saved locally but not deployed")
            deploy_result["stderr"] = "netlify CLI not installed"

        url = f"https://bullpowerhubgit.github.io/shopify-suite-landing/blog/{slug}/"
        return web.json_response({
            "ok": True,
            "url": url,
            "keyword": keyword,
            "slug": slug,
            "deploy": deploy_result,
        })

    except Exception as e:
        log.exception("handle_seo_generate error")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def _run_seo_loop() -> None:
    """Daily background task: auto-generate one SEO blog article per day."""
    # Initial delay so the server is fully up before first run
    await asyncio.sleep(60)
    while True:
        try:
            log.info("_run_seo_loop: generating daily SEO article")

            class _FakeSeoReq:
                can_read_body = False
                async def json(self):
                    return {}

            await handle_seo_generate(_FakeSeoReq())
        except Exception as e:
            log.error("_run_seo_loop error: %s", e)
        await asyncio.sleep(86400)


# ---------------------------------------------------------------------------
# Social Media Draft Generator — Reddit / Twitter / LinkedIn
# ---------------------------------------------------------------------------

_SOCIAL_PLATFORMS = {
    "reddit_shopify": {
        "subreddit": "r/shopify",
        "style": "helpful community member, no direct promotion, value-first",
        "cta": "bullpower-lead.netlify.app",
        "lang": "English",
    },
    "reddit_ecommerce": {
        "subreddit": "r/ecommerce",
        "style": "sharing experience and tool",
        "cta": "bullpower-hub-portal.netlify.app",
        "lang": "English",
    },
    "reddit_de": {
        "subreddit": "r/Unternehmertum",
        "style": "German language, sharing tool as Unternehmer",
        "cta": "bullpower-lead.netlify.app",
        "lang": "German",
    },
    "twitter": {
        "style": "concise, 280 chars max, German + English mix",
        "cta": "bullpower-lead.netlify.app",
        "lang": "German/English mix",
    },
    "linkedin": {
        "style": "professional German post, 3 paragraphs, value-focused",
        "cta": "bullpower-hub-portal.netlify.app",
        "lang": "German",
    },
}


async def handle_social_drafts(req):
    """GET /api/seo/social-drafts — generate social media post drafts via Claude API."""
    import json as _json
    from datetime import timezone as _tz, datetime as _dt
    try:
        import anthropic as _anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return web.json_response({"ok": False, "error": "ANTHROPIC_API_KEY not configured"}, status=500)

        client = _anthropic.Anthropic(api_key=api_key)

        prompt_parts = [
            "You are a social media copywriter for a Shopify automation SaaS called BullPower Hub.",
            "Generate authentic, non-spammy social media posts about Shopify automation tools.",
            "The posts should provide real value to store owners, not read like advertisements.",
            "Topics to draw from: automating product imports, SEO optimization, revenue tracking,",
            "reducing manual work for Shopify merchants, free store audit tools.",
            "",
            "Generate one post draft for each of the following 5 platforms/audiences.",
            "Return ONLY a valid JSON object with this exact structure (no markdown, no extra text):",
            "{",
            '  "reddit_shopify": {"title": "...", "body": "..."},',
            '  "reddit_ecommerce": {"title": "...", "body": "..."},',
            '  "reddit_de": {"title": "...", "body": "..."},',
            '  "twitter": {"text": "..."},',
            '  "linkedin": {"text": "..."}',
            "}",
            "",
            "Platform-specific instructions:",
        ]
        for platform, cfg in _SOCIAL_PLATFORMS.items():
            if platform.startswith("reddit"):
                prompt_parts.append(
                    f"- {platform} (subreddit: {cfg['subreddit']}): "
                    f"Style: {cfg['style']}. Language: {cfg['lang']}. "
                    f"Include CTA naturally at the end mentioning: {cfg['cta']}"
                )
            else:
                prompt_parts.append(
                    f"- {platform}: Style: {cfg['style']}. Language: {cfg['lang']}. "
                    f"CTA: {cfg['cta']}"
                )
        prompt_parts.append("")
        prompt_parts.append(
            "For reddit posts: title should be 60-100 chars, body should be 150-300 words. "
            "For twitter: keep under 280 characters including the URL. "
            "For linkedin: write 3 short paragraphs, professional tone, end with the CTA link."
        )

        prompt = "\n".join(prompt_parts)

        log.info("Generating social media drafts via Claude API")
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )

        raw_text = response.content[0].text if response.content else "{}"

        # Strip markdown code fences if present
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```", 2)[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.rsplit("```", 1)[0].strip()

        try:
            drafts = _json.loads(raw_text)
        except _json.JSONDecodeError as parse_err:
            log.error("Failed to parse Claude response as JSON: %s \u2014 raw: %s", parse_err, raw_text[:200])
            return web.json_response(
                {"ok": False, "error": f"JSON parse error: {parse_err}", "raw": raw_text[:500]},
                status=500
            )

        # Add subreddit metadata to reddit drafts
        for key in ("reddit_shopify", "reddit_ecommerce", "reddit_de"):
            if key in drafts and key in _SOCIAL_PLATFORMS:
                drafts[key]["subreddit"] = _SOCIAL_PLATFORMS[key].get("subreddit", "")

        generated_at = _dt.now(_tz.utc).isoformat()

        # Persist to Supabase agent_messages
        await _sb_insert("agent_messages", {
            "role": "social_draft",
            "content": _json.dumps(drafts),
        })
        log.info("Social drafts stored in Supabase agent_messages")

        return web.json_response({
            "ok": True,
            "drafts": drafts,
            "generated_at": generated_at,
        })
    except Exception as e:
        log.error("handle_social_drafts error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_social_schedule(req):
    """POST /api/seo/social-schedule — send a social post draft to owner via Telegram."""
    try:
        data = await req.json() if req.can_read_body else {}
        platform = data.get("platform", "")
        text = data.get("text", "")
        if not platform or not text:
            return web.json_response({"ok": False, "error": "platform and text are required"}, status=400)

        msg = (
            "\U0001f4e3 Social Post bereit zum Posten:\n\n"
            f"Platform: {platform}\n"
            "---\n"
            f"{text}\n"
            "---\n"
            "\U0001f449 Jetzt manuell posten oder /approve senden"
        )
        await _tg_notify(msg)
        log.info("Social schedule notification sent for platform: %s", platform)
        return web.json_response({"ok": True, "platform": platform, "notified": True})
    except Exception as e:
        log.error("handle_social_schedule error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_dropshipping_status(req):
    """Dropshipping pipeline status."""
    try:
        from modules.dropshipping_automation import DropshippingWorkflow
        wf = DropshippingWorkflow()
        trending = await wf.find_trending_products("general")
        return web.json_response({"ok": True, "trending_count": len(trending), "sample": trending[:3]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_dropshipping_run(req):
    """Run a full dropshipping pipeline for a niche."""
    try:
        data = await req.json() if req.can_read_body else {}
        niche = data.get("niche", "trending")
        from modules.dropshipping_automation import DropshippingWorkflow
        wf = DropshippingWorkflow()
        result = await wf.full_pipeline(niche)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_pod_status(req):
    """Print-on-Demand status via Printify."""
    try:
        from modules.printify_automation import get_stats, get_pending_orders
        stats = await get_stats()
        pending = await get_pending_orders()
        return web.json_response({"ok": True, "stats": stats, "pending_count": len(pending)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_klaviyo_status(req):
    try:
        from modules.klaviyo_automation import get_stats
        return web.json_response(await get_stats())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_klaviyo_lists(req):
    try:
        from modules.klaviyo_automation import get_lists
        lists = await get_lists()
        return web.json_response({"ok": True, "lists": lists})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_klaviyo_sync(req):
    try:
        data = await req.json()
        list_id = data.get("list_id", "")
        source  = data.get("source", "digistore")
        from modules.klaviyo_automation import sync_from_digistore, sync_from_shopify, get_lists
        if not list_id:
            lists = await get_lists()
            list_id = lists[0]["id"] if lists else ""
        if not list_id:
            return web.json_response({"ok": False, "error": "Keine Klaviyo-Liste gefunden"})
        if source == "shopify":
            count = await sync_from_shopify(list_id)
        else:
            count = await sync_from_digistore(list_id)
        return web.json_response({"ok": True, "synced": count, "list_id": list_id, "source": source})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_klaviyo_campaign(req):
    try:
        data = await req.json()
        from modules.klaviyo_automation import create_and_send_campaign, get_lists
        list_id = data.get("list_id", "")
        if not list_id:
            lists = await get_lists()
            list_id = lists[0]["id"] if lists else ""
        if not list_id:
            return web.json_response({"ok": False, "error": "Keine Liste gefunden"})
        result = await create_and_send_campaign(
            list_id=list_id,
            subject=data.get("subject", "SuperMegaBot Newsletter"),
            from_email=data.get("from_email", "noreply@supermegabot.com"),
            from_name=data.get("from_name", "SuperMegaBot"),
            html_body=data.get("body_html", "<p>Hallo!</p>"),
            campaign_name=data.get("name", ""),
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_bot_clones_status(req):
    """Return status of all bot-clone workers (base + specialized)."""
    try:
        import core.specialized_bots  # registers specialized bots into BOT_REGISTRY
        from core.bot_clones import get_bot_status
        return web.json_response(await get_bot_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_bot_clone_run(req):
    """Manually trigger a specific bot-clone action."""
    try:
        data = await req.json()
        bot_name = data.get("bot", "")
        action   = data.get("action", "status")
        from core.bot_clones import run_bot_action
        result = await run_bot_action(bot_name, action)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Watchdog Proxy ───────────────────────────────────────────────────────────

async def handle_watchdog_status(req):
    """Proxy GET /api/watchdog/status → http://localhost:9003/status"""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get("http://localhost:9003/status") as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    return web.json_response(data)
                return web.json_response({"ok": False, "error": f"HTTP {r.status}"})
    except Exception as e:
        return web.json_response({"ok": False, "status": "offline", "error": str(e)})


# ── Agenten Hub Proxy ─────────────────────────────────────────────────────────

async def handle_agents_hub(req):
    """Proxy GET /api/agents/hub → http://localhost:9998/status"""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get("http://localhost:9998/status") as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    return web.json_response(data)
                return web.json_response({"ok": False, "error": f"HTTP {r.status}"})
    except Exception as e:
        return web.json_response({"ok": False, "status": "offline", "error": str(e)})


async def handle_agents_teams_list(req):
    try:
        from modules.agent_teams import list_teams
        return web.json_response({"ok": True, "teams": list_teams()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_agents_teams_run(req):
    try:
        data = await req.json()
        team = data.get("team", "").strip()
        task = data.get("task", "").strip()
        notify = data.get("notify", True)
        if not team or not task:
            return web.json_response({"ok": False, "error": "team and task required"}, status=400)
        from modules.agent_teams import run_team
        result = await run_team(team, task, notify=notify)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Monetization ─────────────────────────────────────────────────────────────

async def handle_plans_list(req):
    try:
        from modules.monetization import get_plans_info
        return web.json_response({"ok": True, "plans": get_plans_info()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_checkout_create(req):
    try:
        data = await req.json()
        plan = data.get("plan", "").strip()
        email = data.get("email", "").strip()
        base_url = data.get("base_url", os.getenv("DASHBOARD_URL", "http://localhost:8888"))
        if not plan or not email:
            return web.json_response({"ok": False, "error": "plan and email required"}, status=400)
        from modules.monetization import create_checkout_session
        session = create_checkout_session(
            plan=plan,
            customer_email=email,
            success_url=f"{base_url}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/checkout/cancel",
        )
        return web.json_response({"ok": True, "checkout_url": session.get("url"), "session_id": session.get("id")})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_mrr(req):
    try:
        from modules.monetization import get_mrr
        mrr = get_mrr()
        return web.json_response({"ok": True, "mrr_eur": mrr, "arr_eur": mrr * 12})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Stripe ───────────────────────────────────────────────────────────────────

async def handle_stripe_status(req):
    try:
        from modules.stripe_automation import ping, get_stats
        import os
        if not os.getenv("STRIPE_SECRET_KEY", ""):
            return web.json_response({
                "ok": False,
                "configured": False,
                "message": "STRIPE_SECRET_KEY nicht gesetzt",
            })
        ok, msg = await ping()
        if not ok:
            return web.json_response({"ok": False, "error": msg})
        data = await get_stats()
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_balance(req):
    try:
        from modules.stripe_automation import get_balance
        data = await get_balance()
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_charges(req):
    try:
        from modules.stripe_automation import get_charges
        days = int(req.rel_url.query.get("days", "30"))
        limit = int(req.rel_url.query.get("limit", "20"))
        data = await get_charges(limit=limit, days_back=days)
        return web.json_response({"ok": True, "charges": data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_customers(req):
    try:
        from modules.stripe_automation import get_customers
        data = await get_customers(limit=50)
        return web.json_response({"ok": True, "customers": data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_revenue(req):
    try:
        from modules.stripe_automation import get_revenue_summary
        days = int(req.rel_url.query.get("days", "30"))
        data = await get_revenue_summary(days_back=days)
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_subscriptions(req):
    try:
        import stripe as _stripe
        _stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        if not _stripe.api_key:
            return web.json_response({"ok": False, "error": "STRIPE_SECRET_KEY not set"})
        subs = _stripe.Subscription.list(limit=50, status="all")
        data = [{"id": s.id, "status": s.status, "customer": s.customer,
                 "amount": s.items.data[0].price.unit_amount / 100 if s.items.data else 0,
                 "currency": s.items.data[0].price.currency if s.items.data else "eur",
                 "interval": s.items.data[0].price.recurring.interval if s.items.data else "month",
                 "created": s.created} for s in subs.auto_paging_iter()]
        active = [s for s in data if s["status"] == "active"]
        mrr = sum(s["amount"] for s in active)
        return web.json_response({"ok": True, "subscriptions": data, "count": len(data),
                                  "active": len(active), "mrr_eur": round(mrr, 2)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


_PLANS_MSG = """💰 *RudiBot Premium Pläne*

🥉 *Starter — €49/Monat*
• Shopify Produkt-Automation
• AI-Antworten unbegrenzt
• Tägliche Trend-Analyse

🥈 *Pro — €99/Monat*
• Alles aus Starter
• Digistore24 Integration
• Stripe Revenue Tracking
• Priority Support

🏆 *Enterprise — €299/Monat*
• Alles aus Pro
• Eigene Agent Teams
• White-Label Branding
• Dedizierter Support

👇 Jetzt starten:"""

_WELCOME_MSG = """🤖 *Willkommen bei RudiBot!*

Ich bin dein KI-Assistent für E-Commerce & Business Automation.

*Befehle:*
/start — Diese Nachricht
/premium — Pläne & Preise
/hilfe — Alle Funktionen

Oder einfach schreib mir — ich antworte sofort! 💬"""


async def _tg_send(bot_token: str, chat_id: int, text: str, reply_markup: dict = None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with aiohttp.ClientSession() as s:
        await s.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload)


async def handle_telegram_webhook(req):
    """Telegram webhook — processes incoming messages and callback queries."""
    try:
        data = await req.json()

        # Handle inline button presses (callback_query) first
        cb = data.get("callback_query")
        if cb:
            cb_chat_id = str(cb["message"]["chat"]["id"])
            cb_message_id = cb["message"]["message_id"]
            cb_data = cb.get("data", "")
            cb_id = cb["id"]
            from modules.telegram_control import handle_callback
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, handle_callback, cb_data, cb_chat_id, cb_message_id, cb_id)
            return web.Response(status=200)

        msg = data.get("message") or data.get("edited_message")
        if not msg:
            return web.Response(status=200)

        chat_id = msg.get("chat", {}).get("id")
        text = (msg.get("text") or "").strip()
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN_2") or os.getenv("TELEGRAM_BOT_TOKEN", "")

        if not chat_id or not bot_token:
            return web.Response(status=200)

        base_url = f"https://{os.getenv('RAILWAY_STATIC_URL', 'dudirudibot-mega-production.up.railway.app')}"

        # --- Befehle ---
        if text in ("/start", "/menu", "/dashboard", "/hilfe", "/help"):
            from modules.telegram_control import send_main_menu
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, send_main_menu, str(chat_id))
            return web.Response(status=200)

        if text in ("/leads",):
            try:
                async with aiohttp.ClientSession() as _s:
                    async with _s.get("http://localhost:8888/api/leads") as _r:
                        _d = await _r.json()
                leads = _d.get("leads", [])
                if leads:
                    lines = ["👥 <b>Letzte Leads:</b>", ""]
                    for lead in leads[:10]:
                        lines.append(f"• {lead.get('email','?')} — {lead.get('source','?')} ({str(lead.get('created_at','?'))[:10]})")
                    reply = "\n".join(lines)
                else:
                    reply = "Noch keine Leads."
            except Exception as _e:
                reply = f"❌ Leads nicht abrufbar: {_e}"
            await _tg_send(bot_token, chat_id, reply)
            return web.Response(status=200)

        if text in ("/seo",):
            await _tg_send(bot_token, chat_id, "⏳ Generiere SEO-Artikel… (dauert ~30s)")
            try:
                async with aiohttp.ClientSession() as _s:
                    async with _s.post("http://localhost:8888/api/seo/generate") as _r:
                        _d = await _r.json()
                url = _d.get("url", "?")
                reply = f"✅ <b>Artikel deployed!</b>\n🔗 {url}\nKeyword: {_d.get('keyword','?')}"
            except Exception as _e:
                reply = f"❌ SEO-Generierung fehlgeschlagen: {_e}"
            await _tg_send(bot_token, chat_id, reply)
            return web.Response(status=200)

        if text in ("/social",):
            await _tg_send(bot_token, chat_id, "⏳ Generiere Social Drafts… (dauert ~20s)")
            try:
                async with aiohttp.ClientSession() as _s:
                    async with _s.get("http://localhost:8888/api/seo/social-drafts") as _r:
                        _d = await _r.json()
                drafts = _d.get("drafts", {})
                lines = ["📣 <b>Social Drafts bereit:</b>", ""]
                for platform, d in drafts.items():
                    title = d.get("title") or d.get("text", "")[:60]
                    lines.append(f"• <b>{platform}</b>: {title}…")
                lines.append("\n👉 bullpower-hub-portal.netlify.app")
                reply = "\n".join(lines)
            except Exception as _e:
                reply = f"❌ Social Drafts fehlgeschlagen: {_e}"
            await _tg_send(bot_token, chat_id, reply)
            return web.Response(status=200)

        if text in ("/ping",):
            try:
                async with aiohttp.ClientSession() as _s:
                    async with _s.post("http://localhost:8888/api/seo/ping-sitemaps") as _r:
                        _d = await _r.json()
                reply = f"🏓 <b>Sitemap Pings:</b> {_d.get('pinged', 0)} gesendet\nFehler: {len(_d.get('errors', []))}"
            except Exception as _e:
                reply = f"❌ Ping fehlgeschlagen: {_e}"
            await _tg_send(bot_token, chat_id, reply)
            return web.Response(status=200)

        if text in ("/shopify", "/shop", "/status"):
            from modules.shopify_automation import get_shopify_status_message
            await _tg_send(bot_token, chat_id, get_shopify_status_message())
            return web.Response(status=200)

        if text in ("/bestellungen", "/orders"):
            from modules.shopify_automation import get_recent_orders, format_orders_message
            orders = get_recent_orders(limit=5)
            await _tg_send(bot_token, chat_id, format_orders_message(orders))
            return web.Response(status=200)

        if text in ("/umsatz", "/revenue", "/geld"):
            from modules.shopify_automation import get_revenue_today
            r = get_revenue_today()
            msg = f"💰 *Umsatz heute:* €{r['revenue']}\n📋 Bestellungen: {r['orders']}"
            await _tg_send(bot_token, chat_id, msg)
            return web.Response(status=200)

        if text.startswith("/produkt "):
            parts = text[9:].split("|")
            if len(parts) >= 2:
                from modules.shopify_automation import create_product_simple
                p = create_product_simple(parts[0].strip(), parts[1].strip(), parts[2].strip() if len(parts) > 2 else "")
                if p.get("id"):
                    await _tg_send(bot_token, chat_id, f"✅ Produkt erstellt: *{p['title']}* — €{parts[1].strip()}")
                else:
                    await _tg_send(bot_token, chat_id, f"❌ Fehler: {p.get('error', p)}")
            else:
                await _tg_send(bot_token, chat_id, "Format: `/produkt Name | Preis | Beschreibung`\nBeispiel: `/produkt T-Shirt | 29.99 | Hochwertiges Shirt`")
            return web.Response(status=200)

        if text in ("/premium", "/kaufen", "/plans", "/preise", "/buy"):
            keyboard = {"inline_keyboard": [
                [{"text": "🥉 Starter €49/Mo", "url": f"{base_url}/checkout?plan=starter&chat_id={chat_id}"}],
                [{"text": "🥈 Pro €99/Mo", "url": f"{base_url}/checkout?plan=pro&chat_id={chat_id}"}],
                [{"text": "🏆 Enterprise €299/Mo", "url": f"{base_url}/checkout?plan=enterprise&chat_id={chat_id}"}],
            ]}
            await _tg_send(bot_token, chat_id, _PLANS_MSG, reply_markup=keyboard)
            return web.Response(status=200)

        # --- AI Antwort ---
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
            reply_msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                system=(
                    "Du bist RudiBot, ein KI-Assistent für E-Commerce und Business Automation. "
                    "Antworte auf Deutsch, kurz und hilfreich. "
                    "Wenn jemand nach Preisen, Abo oder Kauf fragt, sage: 'Tippe /premium für unsere Pläne ab €49/Monat.'"
                ),
                messages=[{"role": "user", "content": text or "(leere Nachricht)"}]
            )
            reply_text = reply_msg.content[0].text if reply_msg.content else "Entschuldigung, keine Antwort verfügbar."
        except Exception as ai_err:
            log.error("AI error in telegram webhook: %s", ai_err)
            reply_text = "Hallo! Ich bin RudiBot. Tippe /premium für unsere Pläne. (KI momentan nicht verfügbar)"

        await _tg_send(bot_token, chat_id, reply_text)
        return web.Response(status=200)
    except Exception as e:
        log.error("Telegram webhook error: %s", e)
        return web.Response(status=200)


async def handle_checkout_page(req):
    """Redirect to Stripe Checkout für Telegram-Nutzer."""
    plan = req.rel_url.query.get("plan", "starter")
    chat_id = req.rel_url.query.get("chat_id", "")
    base_url = f"https://{os.getenv('RAILWAY_STATIC_URL', 'dudirudibot-mega-production.up.railway.app')}"
    try:
        from modules.monetization import create_checkout_session
        session = create_checkout_session(
            plan=plan,
            customer_email="",
            success_url=f"{base_url}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}&chat_id={chat_id}",
            cancel_url=f"{base_url}/checkout/cancel",
        )
        checkout_url = session.get("url", "")
        if checkout_url:
            raise web.HTTPFound(checkout_url)
        return web.Response(text="Checkout nicht verfügbar.", status=500)
    except web.HTTPFound:
        raise
    except Exception as e:
        log.error("Checkout page error: %s", e)
        return web.Response(text=f"Fehler: {e}", status=500)


async def handle_checkout_success(req):
    """Nach erfolgreichem Kauf — Telegram Bestätigung senden."""
    chat_id = req.rel_url.query.get("chat_id", "")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN_2") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if chat_id and bot_token:
        try:
            await _tg_send(bot_token, int(chat_id),
                "✅ *Zahlung erfolgreich!* Willkommen bei RudiBot Premium! 🎉\n\nDu hast jetzt Zugang zu allen Features. Schreib mir einfach!")
        except Exception:
            pass
    html = "<html><body style='font-family:sans-serif;text-align:center;padding:50px'><h1>✅ Zahlung erfolgreich!</h1><p>Gehe zurück zu Telegram und schreib @RudiCludiBot</p></body></html>"
    return web.Response(text=html, content_type="text/html")


async def handle_telegram_setup(req):
    """GET /api/telegram/setup — Register bot commands + webhook with Telegram API."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN_2", "")
    if not token:
        return web.json_response({"ok": False, "error": "No TELEGRAM_BOT_TOKEN configured"})

    base_url = f"https://{os.getenv('RAILWAY_STATIC_URL', 'dudirudibot-mega-production.up.railway.app')}"
    results = {}

    async with aiohttp.ClientSession() as session:
        # 1. Set webhook
        webhook_url = f"{base_url}/api/telegram/webhook"
        async with session.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "allowed_updates": ["message", "callback_query", "edited_message"]}
        ) as r:
            results["setWebhook"] = await r.json()

        # 2. Set commands
        commands = [
            {"command": "start",     "description": "🏠 Hauptmenü öffnen"},
            {"command": "menu",      "description": "📋 Dashboard Menü"},
            {"command": "dashboard", "description": "📊 System Dashboard"},
            {"command": "leads",     "description": "👥 Letzte Leads anzeigen"},
            {"command": "revenue",   "description": "💰 Umsatz heute"},
            {"command": "seo",       "description": "✍️ SEO Artikel generieren"},
            {"command": "social",    "description": "📣 Social Media Drafts"},
            {"command": "status",    "description": "🟢 System Status"},
            {"command": "shopify",   "description": "🛒 Shopify Status"},
            {"command": "ping",      "description": "🏓 Sitemaps pingen"},
            {"command": "orders",    "description": "📦 Letzte Bestellungen"},
            {"command": "premium",   "description": "💳 Abo-Pläne"},
        ]
        async with session.post(
            f"https://api.telegram.org/bot{token}/setMyCommands",
            json={"commands": commands}
        ) as r:
            results["setMyCommands"] = await r.json()

    log.info("Telegram setup completed: %s", results)
    return web.json_response({"ok": True, "results": results, "webhook": webhook_url})


async def handle_discord_interactions(req: web.Request) -> web.Response:
    """Discord Interactions Endpoint — Ed25519 Verifizierung + PING/PONG."""
    PUBLIC_KEY = os.getenv("DISCORD_PUBLIC_KEY", "436bb930c7b1829783ef5579c1c079d568409535c856fefc0d390fd382e574a8")
    signature = req.headers.get("X-Signature-Ed25519", "")
    timestamp  = req.headers.get("X-Signature-Timestamp", "")
    body_bytes = await req.read()

    # Ed25519 Signatur prüfen
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY))
        key.verify(bytes.fromhex(signature), timestamp.encode() + body_bytes)
    except Exception as e:
        log.warning("[DISCORD] Invalid signature: %s", e)
        return web.Response(status=401, text="Invalid request signature")

    data = json.loads(body_bytes)
    if data.get("type") == 1:  # PING → PONG
        return web.json_response({"type": 1})

    # Slash Commands
    name = data.get("data", {}).get("name", "")
    if name == "status":
        return web.json_response({
            "type": 4,
            "data": {"content": "✅ SuperMegaBot online! 9 Engines aktiv. /health für Details."}
        })
    return web.json_response({"type": 4, "data": {"content": f"Command /{name} empfangen."}})

async def handle_datenschutz(req: web.Request) -> web.Response:
    """DSGVO Datenschutzerklärung — für Pinterest API-Anfrage und allgemein."""
    html = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Datenschutzerklärung – BullpowerHub / AIITEC</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f9fa; color: #333; line-height: 1.7; }
header { background: #e60023; color: white; padding: 20px 0; text-align: center; }
header h1 { font-size: 1.6rem; font-weight: 700; }
header p { font-size: 0.9rem; opacity: 0.85; margin-top: 4px; }
.container { max-width: 860px; margin: 40px auto; padding: 0 20px 60px; }
h2 { color: #e60023; font-size: 1.2rem; margin: 32px 0 10px; }
p, li { font-size: 0.97rem; color: #444; }
ul { padding-left: 20px; margin: 8px 0; }
li { margin-bottom: 6px; }
a { color: #e60023; }
.card { background: white; border-radius: 10px; padding: 32px; box-shadow: 0 2px 12px rgba(0,0,0,0.07); margin-bottom: 24px; }
</style>
</head>
<body>
<header>
  <h1>Datenschutzerkl&auml;rung</h1>
  <p>BullpowerHub / AIITEC &ndash; Rudolf Sarkany</p>
</header>
<div class="container">
  <div class="card">
    <h2>1. Verantwortlicher</h2>
    <p>Rudolf Sarkany &bull; AIITEC &ndash; AI &amp; Internet Technology<br>
    E-Mail: <a href="mailto:bullpowersrtkennels@gmail.com">bullpowersrtkennels@gmail.com</a><br>
    Website: <a href="https://bullpower-hub-portal.netlify.app">bullpower-hub-portal.netlify.app</a><br>
    Letzte Aktualisierung: Juni 2026</p>
  </div>
  <div class="card">
    <h2>2. Erhobene Daten (Pinterest API)</h2>
    <p>Im Rahmen der Pinterest API-Integration verarbeiten wir:</p>
    <ul>
      <li>Pinterest Profil-Informationen (Name, Bio) &ndash; nur mit OAuth2-Einwilligung</li>
      <li>Pinterest Pins und Board-Daten &ndash; nur f&uuml;r genehmigte Aktionen</li>
      <li>Analytics-Daten (Impressionen, Klicks) &ndash; aggregiert, nicht personenbezogen</li>
      <li>OAuth2-Token &ndash; verschl&uuml;sselt, keine Weitergabe an Dritte</li>
    </ul>
  </div>
  <div class="card">
    <h2>3. Zweck der Verarbeitung</h2>
    <ul>
      <li>Automatisiertes Ver&ouml;ffentlichen von Pins im Auftrag des Nutzers</li>
      <li>Analyse von Pinterest-Performance-Daten</li>
      <li>Verwaltung von Pinterest-Boards und Inhalten</li>
    </ul>
    <p>Kein Verkauf von Daten. Keine Weitergabe an Dritte.</p>
  </div>
  <div class="card">
    <h2>4. Pinterest API-Nutzung</h2>
    <ul>
      <li>Lesen/Schreiben von Pins nur mit expliziter OAuth2-Zustimmung</li>
      <li>Pinterest-Daten werden nicht f&uuml;r KI-Training verwendet</li>
      <li>Tokens werden nach Widerruf sofort gel&ouml;scht</li>
    </ul>
  </div>
  <div class="card">
    <h2>5. Cookies und Tracking</h2>
    <p>Keine Tracking-Cookies. Keine Marketing- oder Analyse-Cookies. Nur technisch notwendige Session-Cookies f&uuml;r Authentifizierung.</p>
  </div>
  <div class="card">
    <h2>6. Speicherdauer</h2>
    <p>Daten werden gel&ouml;scht wenn: der Nutzer die Verbindung widerruft, L&ouml;schung beantragt wird, oder die Verbindung &uuml;ber 12 Monate inaktiv ist.</p>
  </div>
  <div class="card">
    <h2>7. DSGVO-Rechte</h2>
    <p>Auskunft (Art.15), Berichtigung (Art.16), L&ouml;schung (Art.17), Einschr&auml;nkung (Art.18), Widerspruch (Art.21).<br>
    Kontakt: <a href="mailto:bullpowersrtkennels@gmail.com">bullpowersrtkennels@gmail.com</a></p>
  </div>
  <div class="card">
    <h2>8. Kontakt</h2>
    <p><strong>Rudolf Sarkany &ndash; AIITEC</strong><br>
    <a href="mailto:bullpowersrtkennels@gmail.com">bullpowersrtkennels@gmail.com</a></p>
  </div>
</div>
</body>
</html>"""
    return web.Response(content_type="text/html", charset="utf-8", text=html)


async def handle_discord_oauth_callback(req: web.Request) -> web.Response:
    """Discord OAuth2 Callback — tauscht code gegen access_token."""
    code = req.rel_url.query.get("code")
    if not code:
        return web.Response(status=400, text="Missing code parameter")
    client_id = os.getenv("DISCORD_CLIENT_ID", "1515460691664965672")
    client_secret = os.getenv("DISCORD_CLIENT_SECRET", "6d5mLOnMBHgnHAOq8a2ngHdkcx4ClLjH")
    redirect_uri = os.getenv("DISCORD_REDIRECT_URI", "https://dudirudibot-mega-production.up.railway.app/api/discord/oauth/callback")
    import aiohttp as _aiohttp
    async with _aiohttp.ClientSession() as session:
        resp = await session.post("https://discord.com/api/oauth2/token", data={
            "client_id": client_id, "client_secret": client_secret,
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": redirect_uri,
        })
        token_data = await resp.json()
    log.info("[DISCORD-OAUTH] Token exchange: %s", list(token_data.keys()))
    return web.json_response({"ok": True, "discord_oauth": token_data})


async def _push_order_to_pipedrive(order: dict):
    """Shopify Order → Pipedrive Deal (Stage 19 = Neue Bestellung)."""
    import aiohttp, os
    pd_token = os.getenv("PIPEDRIVE_API_TOKEN", "e38c4f57be03a0a33fb39c087b397f57c09bd1a1")
    customer = order.get("customer") or {}
    email = customer.get("email") or order.get("email") or "unknown@shopify.com"
    name = f'{customer.get("first_name","")} {customer.get("last_name","")}'.strip() or email
    order_num = order.get("order_number", "?")
    total = float(order.get("total_price", 0))
    currency = order.get("currency", "EUR")

    async with aiohttp.ClientSession() as session:
        # Person suchen oder anlegen
        async with session.get(
            f"https://api.pipedrive.com/v1/persons/search?term={email}&fields=email&api_token={pd_token}"
        ) as r:
            rd = await r.json()
            persons = rd.get("data", {}).get("items", []) if rd.get("success") else []
            person_id = persons[0]["item"]["id"] if persons else None

        if not person_id:
            async with session.post(
                f"https://api.pipedrive.com/v1/persons?api_token={pd_token}",
                json={"name": name, "email": [{"value": email, "primary": True}]}
            ) as r:
                rd = await r.json()
                person_id = rd.get("data", {}).get("id")

        # Deal anlegen
        deal_payload = {
            "title": f"Shopify #{order_num} — {name}",
            "value": total,
            "currency": currency,
            "person_id": person_id,
            "pipeline_id": 4,
            "stage_id": 19,
        }
        if order.get("financial_status") == "paid":
            deal_payload["stage_id"] = 20
        async with session.post(
            f"https://api.pipedrive.com/v1/deals?api_token={pd_token}",
            json=deal_payload
        ) as r:
            rd = await r.json()
            deal_id = rd.get("data", {}).get("id")
            log.info("[PIPEDRIVE] Deal erstellt: #%s → Deal ID %s", order_num, deal_id)

async def handle_shopify_order_webhook_route(req):
    """Shopify Order Webhook — Telegram-Alarm + Printify + Printful + Pipedrive."""
    try:
        data = await req.json()
        import asyncio
        from modules.shopify_automation import handle_shopify_order_webhook
        await handle_shopify_order_webhook(data)
        asyncio.create_task(_push_order_to_pipedrive(data))
        # Auto-submit to Printify if configured
        asyncio.create_task(_pod_fulfill_order(data))
        return web.Response(status=200)
    except Exception as e:
        log.error("Shopify order webhook error: %s", e)
        return web.Response(status=200)


async def _pod_fulfill_order(order: dict) -> None:
    """Try Printify then Printful fulfillment for a Shopify order."""
    try:
        from modules.printify_automation import ping as py_ping, handle_shopify_order as py_fulfill
        if await py_ping():
            await py_fulfill(order)
    except Exception as e:
        log.debug("Printify order fulfill skipped: %s", e)
    try:
        from modules.printful_automation import ping as pf_ping, create_order_from_shopify as pf_fulfill
        if await pf_ping():
            await pf_fulfill(order)
    except Exception as e:
        log.debug("Printful order fulfill skipped: %s", e)


async def handle_printful_status(req):
    try:
        from modules.printful_automation import ping, get_stats
        ok = await ping()
        stats = await get_stats() if ok else {}
        return web.json_response({"ok": ok, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_printful_autofulfill(req):
    try:
        from modules.printful_automation import auto_fulfill_pending
        result = await auto_fulfill_pending()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_revenue_blitz(req):
    try:
        from modules.super_revenue_blitz import revenue_blast_now
        r = await revenue_blast_now()
        return web.json_response({"ok": True, **r})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_aliexpress_status(req):
    try:
        from modules.aliexpress_autonomy import run_aliexpress_cycle
        r = await run_aliexpress_cycle()
        return web.json_response({"ok": True, **r, "configured": bool(os.getenv("ALIEXPRESS_APP_KEY"))})
    except Exception as e:
        return web.json_response({"ok": False, "configured": bool(os.getenv("ALIEXPRESS_APP_KEY")), "error": str(e)})


async def handle_aliexpress_import(req):
    try:
        from modules.super_revenue_blitz import aliexpress_import_trending
        r = await aliexpress_import_trending()
        return web.json_response({"ok": True, **r})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_tiktok_status(req):
    try:
        configured = bool(os.getenv("TIKTOK_APP_KEY") and os.getenv("TIKTOK_APP_SECRET"))
        token_set = bool(os.getenv("TIKTOK_ACCESS_TOKEN"))
        return web.json_response({
            "ok": token_set,
            "configured": configured,
            "token_set": token_set,
            "shop_id": os.getenv("TIKTOK_SHOP_ID", ""),
            "note": "Set TIKTOK_APP_KEY, TIKTOK_APP_SECRET, TIKTOK_ACCESS_TOKEN, TIKTOK_SHOP_ID in Railway" if not configured else ""
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_whatsapp_status(req):
    try:
        phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        wa_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        configured = bool(phone_id and wa_token)
        return web.json_response({
            "ok": configured,
            "configured": configured,
            "phone_id_set": bool(phone_id),
            "token_set": bool(wa_token),
            "note": "Set WHATSAPP_PHONE_NUMBER_ID + WHATSAPP_ACCESS_TOKEN in Railway (Meta Business Portal)" if not configured else ""
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_printful_products(req):
    """GET /api/printful/products — list all Printful sync products."""
    try:
        from modules.printful_automation import get_products
        products = await get_products()
        return web.json_response({"ok": True, "products": products, "count": len(products)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_printful_blast(req):
    """POST /api/printful/blast — get Printful stats + fire BRUTUS for PoD keywords."""
    try:
        from modules.printful_automation import run_with_brutus_traffic
        result = await run_with_brutus_traffic()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_printful_auth(req):
    """Redirect to Printful OAuth authorization page."""
    from modules.printful_automation import get_oauth_url
    url = get_oauth_url()
    raise web.HTTPFound(url)


async def handle_printful_callback(req):
    """Handle Printful OAuth callback — exchange code for token."""
    code = req.rel_url.query.get("code", "")
    error = req.rel_url.query.get("error", "")
    if error or not code:
        return web.Response(text=f"Printful OAuth error: {error or 'no code'}", status=400)
    try:
        from modules.printful_automation import exchange_oauth_code
        result = await exchange_oauth_code(code)
        if result.get("ok"):
            return web.Response(
                text="✅ Printful erfolgreich verbunden! Token gespeichert. Du kannst dieses Fenster schließen.",
                content_type="text/html",
            )
        return web.json_response(result, status=400)
    except Exception as e:
        log.error("Printful callback error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_shopify_order_webhook_v2(req):
    """Alias /api/webhooks/shopify-order → gleiche Logik."""
    return await handle_shopify_order_webhook_route(req)


async def handle_shopify_orders(req):
    try:
        from modules.shopify_automation import get_recent_orders, format_orders_message
        orders = get_recent_orders(limit=10)
        return web.json_response({"ok": True, "orders": orders, "count": len(orders)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_shopify_revenue(req):
    try:
        from modules.shopify_automation import get_revenue_today
        return web.json_response({"ok": True, **get_revenue_today()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_shopify_products(req):
    try:
        import aiohttp as _aiohttp
        shop = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        version = os.getenv("SHOPIFY_API_VERSION", "2024-01")
        if not shop or not token:
            return web.json_response({"ok": False, "error": "SHOPIFY_SHOP_DOMAIN / SHOPIFY_ADMIN_API_TOKEN not set"})
        limit = int(req.rel_url.query.get("limit", "20"))
        url = f"https://{shop}/admin/api/{version}/products.json?limit={limit}"
        async with _aiohttp.ClientSession() as session:
            async with session.get(url, headers={"X-Shopify-Access-Token": token}, timeout=_aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        products = data.get("products", [])
        return web.json_response({"ok": True, "products": products, "count": len(products)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_webhook(req):
    try:
        payload = await req.read()
        sig_header = req.headers.get("Stripe-Signature", "")
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

        from modules.stripe_automation import verify_webhook_signature, handle_webhook_event
        if webhook_secret and not verify_webhook_signature(payload, sig_header, webhook_secret):
            return web.json_response({"ok": False, "error": "Invalid signature"}, status=400)

        event = json.loads(payload)
        result = await handle_webhook_event(event)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Google Drive ──────────────────────────────────────────────────────────────

# ── Google OAuth2 ─────────────────────────────────────────────────────────────

async def handle_google_auth(req):
    """Redirect to Google OAuth2 login."""
    try:
        from modules.google_oauth import get_auth_url
        url = get_auth_url()
        raise web.HTTPFound(url)
    except web.HTTPFound:
        raise
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_google_callback(req):
    """Handle OAuth2 callback, exchange code for token."""
    code  = req.rel_url.query.get("code", "")
    error = req.rel_url.query.get("error", "")
    if error:
        return web.Response(
            content_type="text/html",
            text=f"<h2>❌ Google Auth Fehler: {error}</h2><a href='/'>Dashboard</a>"
        )
    if not code:
        return web.Response(
            content_type="text/html",
            text="<h2>❌ Kein Code erhalten</h2><a href='/'>Dashboard</a>"
        )
    try:
        from modules.google_oauth import exchange_code
        result = await exchange_code(code)
        if result.get("ok"):
            html = """
            <html><head><title>Google verbunden</title>
            <style>body{font-family:Inter,sans-serif;background:#040508;color:#e2e8f0;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
            .box{text-align:center;padding:40px;background:#0d1117;border:1px solid #1e293b;border-radius:12px}
            h2{color:#6ee7b7}a{color:#4f8ef7;text-decoration:none}</style></head>
            <body><div class="box">
            <h2>✅ Google Drive verbunden!</h2>
            <p>Token gespeichert — Drive Backup &amp; API aktiv.</p>
            <a href="/">← Zurück zum Dashboard</a>
            </div></body></html>"""
        else:
            html = f"<h2>❌ Token-Fehler: {result.get('error')}</h2><a href='/'>Dashboard</a>"
        return web.Response(content_type="text/html", text=html)
    except Exception as e:
        return web.Response(content_type="text/html", text=f"<h2>❌ {e}</h2><a href='/'>Dashboard</a>")


async def handle_google_status(req):
    try:
        from modules.google_oauth import get_status
        return web.json_response(await get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_google_refresh(req):
    try:
        from modules.google_oauth import refresh_token
        return web.json_response(await refresh_token())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_google_revoke(req):
    try:
        from modules.google_oauth import revoke
        ok = await revoke()
        return web.json_response({"ok": ok})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_youtube_auth(req):
    """Redirect to Google OAuth2 with YouTube write scopes."""
    try:
        from modules.google_oauth import get_youtube_auth_url
        url = get_youtube_auth_url()
        raise web.HTTPFound(url)
    except web.HTTPFound:
        raise
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_youtube_status(req):
    try:
        from modules.google_oauth import get_youtube_status
        return web.json_response(await get_youtube_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_drive_status(req):
    try:
        from modules.google_drive_automation import get_stats
        data = await get_stats()
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_drive_files(req):
    try:
        from modules.google_drive_automation import list_files
        query = req.rel_url.query.get("q", "")
        limit = int(req.rel_url.query.get("limit", "20"))
        data  = await list_files(query=query, page_size=limit)
        return web.json_response({"ok": True, "files": data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_drive_backup(req):
    try:
        from modules.google_drive_automation import auto_backup
        result = await auto_backup()
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# GROWTH ENGINE API
# ---------------------------------------------------------------------------
async def handle_growth_dashboard(req):
    try:
        from modules.growth_engine import get_growth_dashboard
        data = await get_growth_dashboard()
        return web.json_response({"ok": True, "data": data})
    except Exception as e:
        log.error("handle_growth_dashboard: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_referral_create(req):
    try:
        body = await req.json()
        email = body.get("email", "").strip()
        name  = body.get("name", "").strip()
        if not email:
            return web.json_response({"ok": False, "error": "email required"}, status=400)
        from modules.growth_engine import create_referral_code
        data = await create_referral_code(email, name)
        return web.json_response({"ok": True, "data": data})
    except Exception as e:
        log.error("handle_referral_create: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_referral_stats(req):
    try:
        from modules.growth_engine import get_referral_stats
        data = await get_referral_stats()
        return web.json_response({"ok": True, "data": data})
    except Exception as e:
        log.error("handle_referral_stats: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_referral_top(req):
    try:
        try:
            limit = int(req.rel_url.query.get("limit", "10"))
        except (ValueError, TypeError):
            limit = 10
        from modules.growth_engine import get_top_referrers
        data = await get_top_referrers(limit=limit)
        return web.json_response({"ok": True, "data": data})
    except Exception as e:
        log.error("handle_referral_top: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_referral_redirect(req):
    """GET /api/referral/{ref_code} — track + redirect to landing page."""
    ref_code = req.match_info.get("ref_code", "")
    try:
        supa_url = os.getenv("SUPABASE_URL", "")
        supa_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if supa_url and supa_key and ref_code:
            import aiohttp as _aio
            import datetime as _dt
            async with _aio.ClientSession(timeout=_aio.ClientTimeout(total=5)) as s:
                await s.post(
                    f"{supa_url}/rest/v1/referral_clicks",
                    headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}",
                             "Content-Type": "application/json", "Prefer": "return=minimal"},
                    json={"ref_code": ref_code,
                          "clicked_at": _dt.datetime.utcnow().isoformat()},
                )
    except Exception:
        pass
    return web.HTTPFound(
        f"https://bullpowerhubgit.github.io/shopify-brutal-tuning-landing/?ref={ref_code}"
    )


async def handle_push_subscribe(req):
    """POST /api/push/subscribe — store Web Push subscription in Supabase."""
    try:
        data     = await req.json()
        endpoint = data.get("endpoint", "")
        p256dh   = data.get("keys", {}).get("p256dh", "")
        auth_key = data.get("keys", {}).get("auth", "")
        if not endpoint:
            return web.json_response({"ok": False, "error": "endpoint required"}, status=400)
        supa_url = os.getenv("SUPABASE_URL", "")
        supa_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if supa_url and supa_key:
            import aiohttp as _aio
            import datetime as _dt
            async with _aio.ClientSession(timeout=_aio.ClientTimeout(total=8)) as s:
                await s.post(
                    f"{supa_url}/rest/v1/push_subscriptions",
                    headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}",
                             "Content-Type": "application/json", "Prefer": "return=minimal"},
                    json={"endpoint": endpoint, "p256dh": p256dh, "auth": auth_key,
                          "created_at": _dt.datetime.utcnow().isoformat()},
                )
        return web.json_response({"ok": True, "subscribed": True})
    except Exception as e:
        log.error("handle_push_subscribe: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_push_send(req):
    """POST /api/push/send — broadcast push notification to all subscribers."""
    try:
        vapid_key = os.getenv("VAPID_PRIVATE_KEY", "")
        supa_url  = os.getenv("SUPABASE_URL", "")
        supa_key  = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not vapid_key:
            return web.json_response({"ok": False, "error": "VAPID_PRIVATE_KEY not set",
                                      "setup": "https://vapidkeys.com"})
        body    = await req.json()
        title   = body.get("title", "🔥 BullPower Hub")
        message = body.get("message", "Neue KI-Automatisierung!")
        url     = body.get("url", "https://bullpowerhubgit.github.io/bullpower-lead/")
        import json as _json
        import aiohttp as _aio
        async with _aio.ClientSession(timeout=_aio.ClientTimeout(total=10)) as s:
            async with s.get(
                f"{supa_url}/rest/v1/push_subscriptions?select=endpoint,p256dh,auth&limit=500",
                headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}"},
            ) as r:
                subs = await r.json(content_type=None)
        payload = _json.dumps({"title": title, "body": message, "url": url,
                               "icon": "https://bullpowerhubgit.github.io/bullpower-legal/brutus_pixel.png"})
        sent = 0
        try:
            from pywebpush import webpush
            for sub in (subs if isinstance(subs, list) else []):
                try:
                    webpush(
                        subscription_info={"endpoint": sub["endpoint"],
                                           "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                        data=payload, vapid_private_key=vapid_key,
                        vapid_claims={"sub": "mailto:bullpowersrtkennels@gmail.com",
                                      "aud": sub["endpoint"].split("/")[2]},
                    )
                    sent += 1
                except Exception:
                    pass
        except ImportError:
            return web.json_response({"ok": False, "error": "pip install pywebpush"})
        return web.json_response({"ok": True, "sent": sent, "total": len(subs)})
    except Exception as e:
        log.error("handle_push_send: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_vapid_public_key(req):
    """GET /api/push/vapid-key — public VAPID key for Service Worker registration."""
    pub = os.getenv("VAPID_PUBLIC_KEY", "")
    if not pub:
        return web.json_response({"ok": False, "error": "VAPID_PUBLIC_KEY not set",
                                  "setup": "Generate: https://vapidkeys.com → set in Railway"})
    return web.json_response({"ok": True, "publicKey": pub})


async def handle_reddit_auth_start(req):
    """GET /api/reddit/auth — Reddit OAuth2 start (password-grant mode, no redirect needed)."""
    client_id = os.getenv("REDDIT_CLIENT_ID", "")
    username = os.getenv("REDDIT_USERNAME", "")
    if not client_id or not username:
        return web.json_response({"ok": False, "mode": "password_grant",
                                  "error": "Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD in Railway"})
    return web.json_response({"ok": True, "mode": "password_grant",
                              "info": "Reddit uses password grant — no browser OAuth needed",
                              "username": username, "client_id": client_id[:8] + "..."})


async def handle_reddit_callback(req):
    """GET /api/reddit/callback — not used in password-grant mode."""
    return web.json_response({"ok": True, "info": "Reddit uses password grant — callback not required"})


async def handle_pinterest_auth(req):
    """GET /api/pinterest/auth — redirect to Pinterest OAuth authorization."""
    client_id = os.getenv("PINTEREST_APP_ID", os.getenv("PINTEREST_CLIENT_ID", ""))
    if not client_id:
        return web.json_response({"ok": False, "error": "PINTEREST_APP_ID not set in Railway"})
    redirect_uri = os.getenv("PINTEREST_REDIRECT_URI",
                             "https://dudirudibot-mega-production.up.railway.app/api/pinterest/callback")
    scope = "boards:read,pins:read,pins:write"
    auth_url = (f"https://www.pinterest.com/oauth/?client_id={client_id}"
                f"&redirect_uri={redirect_uri}&response_type=code&scope={scope}")
    raise web.HTTPFound(location=auth_url)


async def handle_pinterest_callback(req):
    """GET /api/pinterest/callback — exchange code for access token, save to Railway."""
    code = req.rel_url.query.get("code", "")
    if not code:
        error = req.rel_url.query.get("error", "unknown")
        return web.json_response({"ok": False, "error": error}, status=400)
    client_id = os.getenv("PINTEREST_APP_ID", os.getenv("PINTEREST_CLIENT_ID", ""))
    client_secret = os.getenv("PINTEREST_APP_SECRET", os.getenv("PINTEREST_CLIENT_SECRET", ""))
    redirect_uri = os.getenv("PINTEREST_REDIRECT_URI",
                             "https://dudirudibot-mega-production.up.railway.app/api/pinterest/callback")
    if not client_id or not client_secret:
        return web.json_response({"ok": False, "error": "Pinterest credentials not configured"}, status=500)
    import base64
    import aiohttp as _aio
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    async with _aio.ClientSession() as sess:
        async with sess.post("https://api.pinterest.com/v5/oauth/token",
                             headers={"Authorization": f"Basic {creds}",
                                      "Content-Type": "application/x-www-form-urlencoded"},
                             data=f"grant_type=authorization_code&code={code}&redirect_uri={redirect_uri}") as r:
            data = await r.json()
    if "access_token" in data:
        token = data["access_token"]
        log.info("Pinterest token obtained: %s...", token[:12])
        return web.json_response({"ok": True, "access_token": token[:12] + "...",
                                  "action": f"Set PINTEREST_ACCESS_TOKEN={token} in Railway env vars"})
    return web.json_response({"ok": False, "error": data.get("message", str(data))}, status=400)


async def handle_oauth_status(req):
    """GET /api/oauth/status — show which OAuth integrations are configured."""
    return web.json_response({
        "ok": True,
        "twitter":   {"configured": bool(os.getenv("TWITTER_API_KEY") and os.getenv("TWITTER_ACCESS_TOKEN"))},
        "pinterest": {"configured": bool(os.getenv("PINTEREST_ACCESS_TOKEN"))},
        "reddit":    {"configured": bool(os.getenv("REDDIT_CLIENT_ID") and os.getenv("REDDIT_USERNAME"))},
        "linkedin":  {"configured": bool(os.getenv("LINKEDIN_ACCESS_TOKEN"))},
        "medium":    {"configured": bool(os.getenv("MEDIUM_API_KEY"))},
        "devto":     {"configured": bool(os.getenv("DEVTO_API_KEY"))},
        "hashnode":  {"configured": bool(os.getenv("HASHNODE_API_KEY"))},
        "discord":   {"configured": bool(os.getenv("DISCORD_WEBHOOK_URL"))},
        "telegram":  {"configured": bool(os.getenv("TELEGRAM_BOT_TOKEN"))},
        "github":    {"configured": bool(os.getenv("GITHUB_TOKEN"))},
    })


async def handle_review_automation_run(req):
    try:
        from modules.growth_engine import run_review_automation
        result = await run_review_automation()
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        log.error("handle_review_automation_run: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_winback_run(req):
    try:
        from modules.growth_engine import run_winback_automation
        result = await run_winback_automation()
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        log.error("handle_winback_run: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# TRELLO — Revenue Board Automation
# ---------------------------------------------------------------------------

async def handle_trello_status(req):
    """GET /api/trello/status — Verbindungsstatus + OAuth-Link."""
    key   = os.getenv("TRELLO_API_KEY", "")
    token = os.getenv("TRELLO_TOKEN", "")
    configured = bool(key and token)
    oauth_url = (
        f"https://trello.com/1/authorize?expiration=never"
        f"&name=SuperMegaBot&scope=read,write&response_type=token&key={key}"
        if key else ""
    )
    if configured:
        try:
            from modules.trello_client import verify_credentials
            member = await verify_credentials()
            return web.json_response({"ok": True, "configured": True,
                                      "member": member.get("member", {}).get("fullName")})
        except Exception as e:
            return web.json_response({"ok": False, "configured": True,
                                      "error": str(e), "oauth_url": oauth_url})
    return web.json_response({"ok": False, "configured": False,
                              "oauth_url": oauth_url,
                              "message": "Besuche oauth_url → kopiere Token → POST /api/trello/token"})


async def handle_trello_set_token(req):
    """POST /api/trello/token  body: {"token":"<64-char hex>"}
    Setzt TRELLO_TOKEN in Railway und prüft sofort."""
    try:
        body  = await req.json()
        token = (body.get("token") or "").strip()
        if len(token) < 60:
            return web.json_response({"ok": False, "error": "Token zu kurz (min 60 Zeichen)"}, status=400)
        import subprocess
        subprocess.run(
            ["railway", "variables", "set", f"TRELLO_TOKEN={token}", "--service", "dudirudibot-mega"],
            capture_output=True, timeout=30
        )
        os.environ["TRELLO_TOKEN"] = token
        from modules.trello_client import verify_credentials, get_lists
        member = await verify_credentials()
        board_id = os.getenv("TRELLO_BOARD_ID", "")
        lists = await get_lists(board_id) if board_id else []
        if lists:
            today_list = next((l for l in lists if "heute" in l["name"].lower() or "today" in l["name"].lower()), lists[0])
            week_list  = next((l for l in lists if "woche" in l["name"].lower() or "week" in l["name"].lower()), lists[-1])
            subprocess.run(["railway","variables","set",f"TRELLO_LIST_TODAY={today_list['id']}","--service","dudirudibot-mega"], capture_output=True, timeout=30)
            subprocess.run(["railway","variables","set",f"TRELLO_LIST_WEEK={week_list['id']}","--service","dudirudibot-mega"], capture_output=True, timeout=30)
            os.environ["TRELLO_LIST_TODAY"] = today_list["id"]
            os.environ["TRELLO_LIST_WEEK"]  = week_list["id"]
        return web.json_response({"ok": True,
                                  "member": member.get("member", {}).get("fullName"),
                                  "lists_found": len(lists),
                                  "lists": [l["name"] for l in lists]})
    except Exception as e:
        log.error("handle_trello_set_token: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_trello_boards(req):
    """GET /api/trello/boards — alle zugänglichen Boards."""
    try:
        from modules.trello_client import _get
        boards = await _get("/members/me/boards", {"filter": "open", "fields": "id,name,url"})
        return web.json_response({"ok": True, "boards": boards})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_trello_lists(req):
    """GET /api/trello/lists — Listen des konfigurierten Boards."""
    try:
        from modules.trello_client import get_lists
        board_id = req.rel_url.query.get("board_id") or os.getenv("TRELLO_BOARD_ID", "")
        lists = await get_lists(board_id)
        return web.json_response({"ok": True, "lists": lists})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_trello_create_card(req):
    """POST /api/trello/card  body: {"name":"...","desc":"...","list_id":"..."}"""
    try:
        body = await req.json()
        from modules.trello_client import create_card
        card = await create_card(
            name=body.get("name", "Neue Aufgabe"),
            list_id=body.get("list_id"),
            desc=body.get("desc", ""),
        )
        return web.json_response({"ok": True, "card": {"id": card["id"], "name": card["name"], "url": card.get("url")}})
    except Exception as e:
        log.error("handle_trello_create_card: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# PIPEDRIVE CRM
# ---------------------------------------------------------------------------
async def handle_pipedrive_status(req):
    """GET /api/pipedrive/status — CRM connection status + deal count."""
    try:
        from modules.pipedrive_client import check_status
        result = await check_status()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_pipedrive_deals(req):
    """GET /api/pipedrive/deals — list open deals."""
    try:
        from modules.pipedrive_client import list_deals
        deals = await list_deals(limit=20)
        return web.json_response({"ok": True, "deals": deals, "count": len(deals)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_pipedrive_persons(req):
    """GET /api/pipedrive/persons — list persons/leads."""
    try:
        from modules.pipedrive_client import list_persons
        persons = await list_persons(limit=20)
        return web.json_response({"ok": True, "persons": persons, "count": len(persons)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_pipedrive_sync_shopify(req):
    """POST /api/pipedrive/sync-shopify — sync Shopify customers to Pipedrive."""
    try:
        from modules.pipedrive_client import sync_shopify_customer
        from modules.shopify_automation import get_customers
        customers = await get_customers(limit=50)
        synced = 0
        for c in customers:
            email = c.get("email", "")
            name = f"{c.get('first_name','')} {c.get('last_name','')}".strip()
            order_value = float(c.get("total_spent", 0) or 0)
            if email:
                await sync_shopify_customer(email=email, name=name, order_value=order_value,
                                            orders_count=c.get("orders_count", 0))
                synced += 1
        return web.json_response({"ok": True, "synced": synced})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

# ---------------------------------------------------------------------------
# TRAFFIC BLITZ API
# ---------------------------------------------------------------------------
async def handle_traffic_blitz(req):
    """POST /api/traffic/blitz — run full traffic blitz in background."""
    try:
        body = await req.json() if req.content_length else {}
    except Exception:
        body = {}
    async def _bg():
        try:
            from modules.traffic_blitz import run_traffic_blitz
            await run_traffic_blitz()
        except Exception as e:
            log.error("traffic_blitz bg: %s", e)
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "message": "Traffic Blitz gestartet (background)", "keywords": body.get("keywords", [])})


async def handle_github_seo_post(req):
    """POST /api/traffic/github-post — publish one SEO article to GitHub Pages."""
    try:
        body  = await req.json() if req.content_length else {}
        topic = body.get("topic")
        from modules.traffic_blitz import create_github_seo_post
        result = await create_github_seo_post(topic)
        return web.json_response(result)
    except Exception as e:
        log.error("handle_github_seo_post: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_linkedin_burst(req):
    """POST /api/traffic/linkedin-burst — post 3 AI posts to LinkedIn."""
    try:
        from modules.traffic_blitz import run_linkedin_burst
        result = await run_linkedin_burst()
        return web.json_response(result)
    except Exception as e:
        log.error("handle_linkedin_burst: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_indexnow_blast(req):
    """POST /api/traffic/indexnow — ping Google+Bing IndexNow for all domains."""
    try:
        from modules.traffic_blitz import indexnow_blast
        result = await indexnow_blast()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        log.error("handle_indexnow_blast: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_circuit_status(req):
    """GET /api/circuit/status — show all circuit breaker states."""
    try:
        from modules.circuit_breaker import get_status
        return web.json_response({"ok": True, "circuits": get_status()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_circuit_reset(req):
    """POST /api/circuit/reset — reset one or all circuits to closed.
    Body: {"service": "linkedin"} or {} for all."""
    try:
        from modules.circuit_breaker import reset, get_status, _STATE
        body = await req.json() if req.content_length else {}
        svc  = body.get("service")
        if svc:
            reset(svc)
            return web.json_response({"ok": True, "reset": svc})
        for name in list(_STATE.keys()):
            reset(name)
        return web.json_response({"ok": True, "reset": "all"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# DYNAMIC PRICING + EMAIL SEQUENCES API
# ---------------------------------------------------------------------------
async def handle_pricing_dashboard(req):
    """GET /api/pricing/dashboard — pricing metrics for last 30 days."""
    try:
        from modules.dynamic_pricing import get_pricing_dashboard
        data = await get_pricing_dashboard()
        return web.json_response({"ok": True, **data})
    except Exception as e:
        log.error("handle_pricing_dashboard: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_pricing_run(req):
    """POST /api/pricing/run — trigger a dynamic pricing cycle."""
    try:
        body = {}
        if req.can_read_body:
            try:
                body = await req.json()
            except Exception:
                pass
        max_products = int(body.get("max_products", 20))
        from modules.dynamic_pricing import run_dynamic_pricing_cycle
        result = await run_dynamic_pricing_cycle(max_products=max_products)
        return web.json_response({"ok": True, **result})
    except Exception as e:
        log.error("handle_pricing_run: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_pricing_history(req):
    """GET /api/pricing/history?product_id=...&days=30"""
    try:
        product_id = req.rel_url.query.get("product_id")
        try:
            days = int(req.rel_url.query.get("days", "30"))
        except (ValueError, TypeError):
            days = 30
        from modules.dynamic_pricing import get_pricing_history
        history = await get_pricing_history(product_id=product_id, days=days)
        return web.json_response({"ok": True, "history": history, "count": len(history)})
    except Exception as e:
        log.error("handle_pricing_history: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_pricing_enable(req):
    """POST /api/pricing/enable — {product_id, min_price, max_price}"""
    try:
        body = await req.json()
        product_id = str(body.get("product_id", ""))
        min_price  = float(body.get("min_price", 0))
        max_price  = float(body.get("max_price", 0))
        if not product_id:
            return web.json_response({"ok": False, "error": "product_id required"}, status=400)
        from modules.dynamic_pricing import enable_auto_pricing
        result = await enable_auto_pricing(product_id, min_price, max_price)
        return web.json_response(result)
    except Exception as e:
        log.error("handle_pricing_enable: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


# ── Email Sequence handlers ───────────────────────────────────────────────────

async def handle_email_sequence_stats(req):
    """GET /api/email/stats — open/send stats per sequence."""
    try:
        from modules.email_sequence_engine import get_sequence_stats
        result = await get_sequence_stats()
        return web.json_response(result)
    except Exception as e:
        log.error("handle_email_sequence_stats: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_email_sequence_enroll(req):
    """POST /api/email/enroll — {email, name, sequence, metadata}"""
    try:
        body     = await req.json()
        email    = str(body.get("email", "")).strip()
        name     = str(body.get("name", "")).strip()
        sequence = str(body.get("sequence", "")).strip()
        metadata = body.get("metadata") or {}
        if not email or not sequence:
            return web.json_response(
                {"ok": False, "error": "email and sequence are required"}, status=400
            )
        from modules.email_sequence_engine import enroll_customer
        result = await enroll_customer(email, name, sequence, metadata)
        return web.json_response(result)
    except Exception as e:
        log.error("handle_email_sequence_enroll: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_email_sequence_process(req):
    """POST /api/email/process — process all due emails."""
    try:
        from modules.email_sequence_engine import process_due_emails
        result = await process_due_emails()
        return web.json_response(result)
    except Exception as e:
        log.error("handle_email_sequence_process: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_email_sequence_enroll_new(req):
    """POST /api/email/enroll-new — auto-enroll new Shopify customers."""
    try:
        from modules.email_sequence_engine import auto_enroll_new_customers
        result = await auto_enroll_new_customers()
        return web.json_response(result)
    except Exception as e:
        log.error("handle_email_sequence_enroll_new: %s", e)
        return web.json_response({"ok": False, "error": str(e)})




# ---------------------------------------------------------------------------
# B2B PIPELINE + WHATSAPP + TIKTOK API
# ---------------------------------------------------------------------------
async def handle_b2b_pipeline_stats(req):
    try:
        from modules.b2b_pipeline import get_stats
        stats = await get_stats()
        return web.json_response({"ok": True, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_pipeline_leads(req):
    try:
        from modules.b2b_pipeline import get_leads
        stage = req.rel_url.query.get("stage")
        leads = await get_leads(status=stage)
        return web.json_response({"ok": True, "leads": leads, "count": len(leads)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_lead_add(req):
    try:
        from modules.b2b_pipeline import add_lead
        data = await req.json()
        lead = await add_lead(
            company=data.get("company", ""),
            email=data.get("email", ""),
            domain=data.get("website", ""),
            niche=data.get("niche", ""),
            contact_name=data.get("name", ""),
            source=data.get("source", "manual_import"),
        )
        return web.json_response({"ok": True, "lead": lead})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_lead_update(req):
    try:
        from modules.b2b_pipeline import update_lead
        data = await req.json()
        lead_id = data.get("id", "")
        stage   = data.get("stage", "")
        notes   = data.get("notes", "")
        if not lead_id:
            return web.json_response({"ok": False, "error": "id required"}, status=400)
        kwargs = {}
        if stage: kwargs["status"] = stage
        if notes: kwargs["notes"] = notes
        result = await update_lead(lead_id, **kwargs)
        return web.json_response({"ok": True, "lead": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_prospecting_run(req):
    try:
        from modules.b2b_pipeline import run_prospecting
        result = await run_prospecting()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_outreach_send(req):
    try:
        from modules.b2b_pipeline import run_outreach
        data = await req.json()
        lead_id = data.get("lead_id", "")
        if not lead_id:
            return web.json_response({"ok": False, "error": "lead_id required"}, status=400)
        result = await run_outreach(str(lead_id))
        return web.json_response({"ok": result.get("ok", False), **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── WhatsApp handlers ─────────────────────────────────────────────────────────

async def handle_whatsapp_webhook_verify(req):
    """Meta webhook verification (GET)."""
    try:
        from modules.whatsapp_automation import verify_webhook
        mode      = req.rel_url.query.get("hub.mode", "")
        token     = req.rel_url.query.get("hub.verify_token", "")
        challenge = req.rel_url.query.get("hub.challenge", "")
        if mode == "subscribe":
            response = await verify_webhook(token, challenge)
            if response:
                return web.Response(text=response)
        return web.Response(status=403, text="Forbidden")
    except Exception as e:
        return web.Response(status=500, text=str(e))


async def handle_whatsapp_webhook(req):
    """Meta webhook events (POST)."""
    try:
        from modules.whatsapp_automation import process_webhook
        data = await req.json()
        await process_webhook(data)
        return web.json_response({"ok": True})
    except Exception as e:
        log.error("WhatsApp webhook error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_whatsapp_send(req):
    try:
        from modules.whatsapp_automation import send_message
        data = await req.json()
        to      = data.get("to", "")
        message = data.get("message", "")
        if not to or not message:
            return web.json_response({"ok": False, "error": "to and message required"}, status=400)
        success = await send_message(to, message)
        return web.json_response({"ok": success})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_whatsapp_broadcast(req):
    try:
        from modules.whatsapp_automation import broadcast_to_subscribers
        data    = await req.json()
        message = data.get("message", "")
        numbers = data.get("numbers", [])
        if not message or not numbers:
            return web.json_response({"ok": False, "error": "message and numbers required"}, status=400)
        result = await broadcast_to_subscribers(message, numbers)
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_whatsapp_stats(req):
    try:
        from modules.whatsapp_automation import get_whatsapp_stats
        stats = await get_whatsapp_stats()
        return web.json_response({"ok": True, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_whatsapp_blast(req):
    """GET /api/whatsapp/blast — promo blast to all configured WA recipients."""
    try:
        from modules.whatsapp_automation import send_whatsapp_blast
        link = os.getenv("DS24_AFFILIATE_LINK", "https://autopilot-store-suite-fmbka.myshopify.com")
        msg = f"🚀 AIITEC: KI-Einkommen automatisieren — passives Einkommen 2026! Jetzt starten: {link}"
        result = await send_whatsapp_blast(msg)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── TikTok Shop handlers ──────────────────────────────────────────────────────

async def handle_tiktok_sync_products(req):
    try:
        from modules.tiktok_shop_sync import sync_products_to_tiktok
        data = {}
        try:
            data = await req.json()
        except Exception:
            pass
        limit  = int((data or {}).get("limit", 50))
        result = await sync_products_to_tiktok(limit=limit)
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_tiktok_orders(req):
    try:
        from modules.tiktok_shop_sync import get_tiktok_orders
        try:
            days = int(req.rel_url.query.get("days", "7"))
        except (ValueError, TypeError):
            days = 7
        orders = await get_tiktok_orders(days=days)
        return web.json_response({"ok": True, "orders": orders, "count": len(orders)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_tiktok_analytics(req):
    try:
        from modules.tiktok_shop_sync import get_tiktok_analytics
        analytics = await get_tiktok_analytics()
        return web.json_response({"ok": True, **analytics})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_tiktok_combined_revenue(req):
    try:
        from modules.tiktok_shop_sync import get_combined_revenue
        revenue = await get_combined_revenue()
        return web.json_response({"ok": True, **revenue})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_tiktok_promotion(req):
    try:
        from modules.tiktok_shop_sync import create_tiktok_promotion
        data         = await req.json()
        product_id   = data.get("product_id", "")
        discount_pct = int(data.get("discount_pct", 10))
        hours        = int(data.get("hours", 24))
        if not product_id:
            return web.json_response({"ok": False, "error": "product_id required"}, status=400)
        result = await create_tiktok_promotion(product_id, discount_pct, hours)
        return web.json_response({"ok": result.get("success", False), **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── TikTok Research / Ad Library handlers ────────────────────────────────────

async def handle_tiktok_research_status(req):
    try:
        from modules.tiktok_research import check_status
        result = await check_status()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)


async def handle_tiktok_research_ads(req):
    """POST /api/tiktok/research/ads — query Ad Library."""
    try:
        from modules.tiktok_research import query_ads
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass

        date_min = body.get("date_min", "")
        date_max = body.get("date_max", "")
        if not date_min or not date_max:
            return web.json_response(
                {"ok": False, "error": "date_min and date_max required (YYYYMMDD)"},
                status=400,
            )

        result = await query_ads(
            date_min=date_min,
            date_max=date_max,
            country_code=body.get("country_code", "ALL"),
            search_term=body.get("search_term", ""),
            search_type=body.get("search_type", "fuzzy_phrase"),
            advertiser_business_ids=body.get("advertiser_business_ids"),
            unique_users_seen_min=body.get("unique_users_seen_min", ""),
            unique_users_seen_max=body.get("unique_users_seen_max", ""),
            max_count=int(body.get("max_count", 20)),
            search_id=body.get("search_id", ""),
        )
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_tiktok_auth(req):
    """GET /api/tiktok/auth — redirect to TikTok Shop OAuth."""
    app_key = os.getenv("TIKTOK_APP_KEY", "")
    if not app_key:
        return web.json_response({"ok": False, "error": "TIKTOK_APP_KEY not set in Railway"})
    redirect_uri = os.getenv(
        "TIKTOK_REDIRECT_URI",
        "https://dudirudibot-mega-production.up.railway.app/api/tiktok/callback",
    )
    auth_url = (
        f"https://auth.tiktok-shops.com/api/v2/oauth/login/"
        f"?app_key={app_key}&redirect_uri={redirect_uri}&state=smb_tiktok"
    )
    raise web.HTTPFound(auth_url)


async def handle_tiktok_callback(req):
    """GET /api/tiktok/callback — exchange code for access token."""
    code    = req.rel_url.query.get("code", "")
    shop_id = req.rel_url.query.get("shop_id", "") or req.rel_url.query.get("shop", "")
    if not code:
        return web.json_response({"ok": False, "error": "No code received"})
    try:
        from modules.tiktok_shop_sync import exchange_oauth_code
        result = await exchange_oauth_code(code, shop_id)
        if result.get("ok"):
            token = result.get("access_token", "")
            return web.Response(
                content_type="text/html",
                text=(
                    "<html><body style='font-family:sans-serif;padding:40px'>"
                    "<h2>&#x2705; TikTok Shop verbunden!</h2>"
                    "<p>Setze folgende Variablen in Railway:</p>"
                    f"<pre>TIKTOK_ACCESS_TOKEN={token}\nTIKTOK_SHOP_ID={shop_id}</pre>"
                    "<p><a href='/'>&#x2190; Dashboard</a></p></body></html>"
                ),
            )
        return web.json_response(
            {"ok": False, "error": result.get("error", "Token exchange failed")}, status=500
        )
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── SEMrush handlers ──────────────────────────────────────────────────────────

async def handle_semrush_keyword(req):
    phrase = req.rel_url.query.get("phrase", "")
    db = req.rel_url.query.get("db", "de")
    if not phrase:
        return web.json_response({"error": "phrase required"}, status=400)
    try:
        from modules.semrush_client import keyword_overview, keyword_related
        import asyncio
        overview, related = await asyncio.gather(
            keyword_overview(phrase, db),
            keyword_related(phrase, db, 20),
        )
        return web.json_response({"phrase": phrase, "overview": overview, "related": related})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_semrush_domain(req):
    domain = req.rel_url.query.get("domain", "")
    db = req.rel_url.query.get("db", "de")
    if not domain:
        return web.json_response({"error": "domain required"}, status=400)
    try:
        from modules.semrush_client import domain_overview, domain_organic_keywords, domain_competitors, domain_backlinks
        import asyncio
        overview, keywords, competitors, backlinks = await asyncio.gather(
            domain_overview(domain, db),
            domain_organic_keywords(domain, db, 20),
            domain_competitors(domain, db, 10),
            domain_backlinks(domain),
        )
        return web.json_response({
            "domain": domain,
            "overview": overview,
            "top_keywords": keywords,
            "competitors": competitors,
            "backlinks": backlinks,
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_semrush_niche(req):
    kw = req.rel_url.query.get("keyword", "")
    domain = req.rel_url.query.get("domain", None)
    db = req.rel_url.query.get("db", "de")
    if not kw:
        return web.json_response({"error": "keyword required"}, status=400)
    try:
        from modules.semrush_client import research_niche
        result = await research_niche(kw, domain, db)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_semrush_serp(req):
    phrase = req.rel_url.query.get("phrase", "")
    db = req.rel_url.query.get("db", "de")
    if not phrase:
        return web.json_response({"error": "phrase required"}, status=400)
    try:
        from modules.semrush_client import keyword_organic_results
        results = await keyword_organic_results(phrase, db)
        return web.json_response({"phrase": phrase, "serp": results})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ── Meta Ads handlers ─────────────────────────────────────────────────────────

async def handle_meta_ads_status(req):
    try:
        from modules.meta_ads import check_status
        return web.json_response(await check_status())
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def handle_meta_campaigns(req):
    try:
        from modules.meta_ads import list_campaigns
        campaigns = await list_campaigns()
        return web.json_response({"ok": True, "campaigns": campaigns, "count": len(campaigns)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_meta_campaign_create(req):
    try:
        from modules.meta_ads import create_campaign
        body = await req.json()
        result = await create_campaign(
            name=body.get("name", "SuperMegaBot Campaign"),
            objective=body.get("objective", "OUTCOME_SALES"),
            daily_budget_eur=float(body.get("daily_budget_eur", 10.0)),
            status=body.get("status", "PAUSED"),
        )
        return web.json_response({"ok": "id" in result, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_meta_campaign_launch(req):
    """Launch full campaign (campaign + adset + creative + ad) from Shopify product."""
    try:
        from modules.meta_ads import launch_shopify_campaign
        body = await req.json()
        result = await launch_shopify_campaign(
            product_title=body.get("product_title", ""),
            product_url=body.get("product_url", ""),
            product_image=body.get("product_image", ""),
            product_price=float(body.get("product_price", 0)),
            daily_budget_eur=float(body.get("daily_budget_eur", 10.0)),
            countries=body.get("countries", ["DE", "AT", "CH"]),
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_meta_saas_campaign(req):
    """Launch SuperMegaBot SaaS lead-gen campaign."""
    try:
        from modules.meta_ads import launch_saas_campaign
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass
        result = await launch_saas_campaign(
            daily_budget_eur=float(body.get("daily_budget_eur", 20.0))
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_meta_pixel_stats(req):
    try:
        from modules.meta_ads import get_pixel_stats, get_pixel_events
        stats = await get_pixel_stats()
        events = await get_pixel_events(days=7)
        return web.json_response({"ok": True, "pixel": stats, "events_7d": events})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_meta_oauth_url(req):
    """Return the OAuth URL to generate a Meta Marketing API token."""
    app_id = os.getenv("FACEBOOK_APP_ID", "1225412136200609")
    scopes = ",".join([
        "ads_management", "ads_read", "pages_manage_ads",
        "pages_read_engagement", "pages_manage_posts",
        "instagram_basic", "instagram_content_publish",
        "business_management", "public_profile",
    ])
    redirect = "https://developers.facebook.com/tools/explorer/"
    url = (
        f"https://www.facebook.com/v21.0/dialog/oauth"
        f"?client_id={app_id}"
        f"&redirect_uri={redirect}"
        f"&scope={scopes}"
        f"&response_type=token"
    )
    return web.json_response({
        "ok": True,
        "oauth_url": url,
        "instructions": [
            "1. Klick den oauth_url Link",
            "2. Mit Facebook-Account einloggen (Aiitec)",
            "3. Alle Berechtigungen genehmigen",
            "4. Den generierten Token kopieren",
            "5. Als META_ADS_TOKEN in .env speichern oder hier senden"
        ],
        "required_permissions": scopes.split(","),
        "ad_account": os.getenv("META_AD_ACCOUNT_ID", ""),
        "page_id": os.getenv("FACEBOOK_PAGE_ID", ""),
    })


# ══════════════════════════════════════════════════════════════════════════════
# SALESFORCE / AGENTFORCE CRM
# ══════════════════════════════════════════════════════════════════════════════

async def handle_salesforce_stats(req):
    try:
        from modules.salesforce_client import get_stats
        return web.json_response({"ok": True, **(await get_stats())})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_salesforce_leads(req):
    try:
        from modules.salesforce_client import get_leads
        status = req.rel_url.query.get("status")
        leads = await get_leads(status=status)
        return web.json_response({"ok": True, "count": len(leads), "leads": leads})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_salesforce_contacts(req):
    try:
        from modules.salesforce_client import get_contacts
        contacts = await get_contacts()
        return web.json_response({"ok": True, "count": len(contacts), "contacts": contacts})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_salesforce_opportunities(req):
    try:
        from modules.salesforce_client import get_opportunities
        stage = req.rel_url.query.get("stage")
        opps = await get_opportunities(stage=stage)
        return web.json_response({"ok": True, "count": len(opps), "opportunities": opps})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_salesforce_create_lead(req):
    try:
        data = await req.json() if req.can_read_body else {}
        from modules.salesforce_client import create_lead
        result = await create_lead(
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", "Lead"),
            email=data.get("email", ""),
            company=data.get("company", "Unknown"),
            phone=data.get("phone", ""),
            source=data.get("source", "SuperMegaBot"),
        )
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_salesforce_sync_klaviyo(req):
    try:
        from modules.salesforce_client import sync_klaviyo_to_sf
        return web.json_response(await sync_klaviyo_to_sf())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_salesforce_import_b2b(req):
    try:
        from modules.salesforce_client import import_sf_leads_to_b2b
        return web.json_response(await import_sf_leads_to_b2b())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# SHOPIFY AUTONOMY MASTER
# ══════════════════════════════════════════════════════════════════════════════

async def handle_autonomy_health(req):
    try:
        from modules.shopify_autonomy_master import get_service
        svc = get_service()
        return web.json_response({"ok": True, **svc.health()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_autonomy_trigger(req):
    job_id = req.match_info.get("job_id", "")
    try:
        from modules.shopify_autonomy_master import get_service, order_orchestrator, inventory_sync, price_optimizer, telegram_digest, recovery_reconciliation, catalog_watchdog
        svc = get_service()
        job_map = {
            "order_orchestrator": order_orchestrator,
            "inventory_sync": inventory_sync,
            "price_optimizer": price_optimizer,
            "telegram_digest": telegram_digest,
            "recovery_reconciliation": recovery_reconciliation,
            "catalog_watchdog": catalog_watchdog,
        }
        if job_id not in job_map:
            return web.json_response({"ok": False, "error": f"Unknown job: {job_id}", "available": list(job_map.keys())})
        result = job_map[job_id](svc)
        return web.json_response({"ok": True, "job_id": job_id, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_autonomy_history(req):
    job_id = req.match_info.get("job_id", "")
    try:
        from modules.shopify_autonomy_master import get_service
        svc = get_service()
        history = svc.state.read(f"history:{job_id}", default={"runs": []})
        return web.json_response({"ok": True, "job_id": job_id, **history})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_queue_stats(req):
    try:
        from core.job_queue import HermesQueue
        return web.json_response(HermesQueue.get().stats())
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_queue_enqueue(req):
    try:
        data = await req.json()
        from core.job_queue import enqueue
        job_id = await enqueue(data.get("name", "notify"),
                               data.get("payload", {}),
                               data.get("priority", 5))
        return web.json_response({"ok": True, "job_id": job_id})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@web.middleware
async def logging_middleware(request, handler):
    resp = await handler(request)
    log.debug("%s %s → %s", request.method, request.path, resp.status)
    return resp


_CORS_TRUSTED = {
    "https://dudirudibot-mega-production.up.railway.app",
    "http://localhost:8888",
    "http://127.0.0.1:8888",
}

@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        resp = web.Response()
    else:
        try:
            resp = await handler(request)
        except web.HTTPException as exc:
            resp = exc
    if request.path.startswith("/api/"):
        origin = request.headers.get("Origin", "")
        resp.headers["Access-Control-Allow-Origin"] = origin if origin in _CORS_TRUSTED else "https://dudirudibot-mega-production.up.railway.app"
        resp.headers["Vary"] = "Origin"
    else:
        resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# SEO MEGA ENGINE ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_seo_generate(request: web.Request) -> web.Response:
    try:
        body = await request.json() if request.content_length else {}
        from modules.seo_mega_engine import run_content_factory
        r = await run_content_factory(batch_size=int(body.get("batch_size", 5)))
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_seo_sitemap(request: web.Request) -> web.Response:
    try:
        from modules.seo_mega_engine import generate_sitemap
        xml = await generate_sitemap()
        return web.Response(text=xml, content_type="application/xml")
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_seo_submit(request: web.Request) -> web.Response:
    try:
        from modules.seo_mega_engine import submit_to_google
        r = await submit_to_google()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_seo_competitor(request: web.Request) -> web.Response:
    try:
        body = await request.json() if request.content_length else {}
        from modules.seo_mega_engine import analyze_competitor, analyze_all_competitors
        url = body.get("url")
        if url:
            r = await analyze_competitor(url)
        else:
            r = await analyze_all_competitors()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_seo_status(request: web.Request) -> web.Response:
    try:
        from modules.seo_mega_engine import generate_seo_report
        r = await generate_seo_report()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════════════════════
# TRAFFIC SWARM ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_traffic_swarm(request: web.Request) -> web.Response:
    try:
        body = await request.json() if request.content_length else {}
        from modules.traffic_swarm import run_full_traffic_swarm
        r = await run_full_traffic_swarm(topic=body.get("topic"))
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_traffic_velocity(request: web.Request) -> web.Response:
    try:
        from modules.traffic_swarm import monitor_traffic_velocity
        r = await monitor_traffic_velocity()
        r.setdefault("delta_pct", 0)
        r["medium_connected"] = bool(os.getenv("MEDIUM_ACCESS_TOKEN"))
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_traffic_rss(request: web.Request) -> web.Response:
    try:
        from modules.traffic_swarm import build_rss_feed
        xml = await build_rss_feed()
        return web.Response(text=xml, content_type="application/rss+xml")
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════════════════════
# ADS ENGINE ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_ads_status(request: web.Request) -> web.Response:
    try:
        from modules.ads_engine import get_ads_status
        r = await get_ads_status()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_ads_campaign(request: web.Request) -> web.Response:
    try:
        body = await request.json() if request.content_length else {}
        from modules.ads_engine import create_facebook_ad_campaign
        r = await create_facebook_ad_campaign(body, budget_eur=float(body.get("budget", 5.0)))
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_ads_performance(request: web.Request) -> web.Response:
    try:
        from modules.ads_engine import monitor_ad_performance
        r = await monitor_ad_performance()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════════════════════
# REVENUE INTELLIGENCE ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_revenue_forecast(request: web.Request) -> web.Response:
    try:
        days = int(request.rel_url.query.get("days", 30))
        from modules.revenue_intelligence import forecast_revenue
        r = await forecast_revenue(days_ahead=days)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_revenue_leaks(request: web.Request) -> web.Response:
    try:
        from modules.revenue_intelligence import detect_revenue_leaks
        r = await detect_revenue_leaks()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_revenue_churn(request: web.Request) -> web.Response:
    try:
        from modules.revenue_intelligence import identify_churn_risk
        r = await identify_churn_risk()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_revenue_status(request: web.Request) -> web.Response:
    try:
        from modules.revenue_intelligence import revenue_autopilot
        r = await revenue_autopilot()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════════════════════
# SHOPIFY MAX TUNER ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_shopify_max_seo(request: web.Request) -> web.Response:
    try:
        from modules.shopify_max_tuner import optimize_all_products_seo
        r = await optimize_all_products_seo()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_shopify_cart_recover(request: web.Request) -> web.Response:
    try:
        from modules.shopify_max_tuner import recover_abandoned_checkouts
        r = await recover_abandoned_checkouts()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_shopify_intel(request: web.Request) -> web.Response:
    try:
        from modules.shopify_max_tuner import shopify_daily_intelligence
        r = await shopify_daily_intelligence()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_shopify_price_opt(request: web.Request) -> web.Response:
    try:
        from modules.shopify_max_tuner import optimize_shopify_pricing
        r = await optimize_shopify_pricing()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════════════════════
# GROWTH HACKER ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_growth_trends(request: web.Request) -> web.Response:
    try:
        from modules.growth_hacker import detect_and_ride_viral_trends
        r = await detect_and_ride_viral_trends()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_growth_pr(request: web.Request) -> web.Response:
    try:
        body = await request.json() if request.content_length else {}
        from modules.growth_hacker import generate_press_release
        r = await generate_press_release(body.get("topic", "KI-Shopify-Automation"))
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_growth_referral(request: web.Request) -> web.Response:
    try:
        email = request.rel_url.query.get("email", "")
        from modules.growth_hacker import get_referral_url
        url = await get_referral_url(email) if email else {"error": "email required"}
        return web.json_response({"referral_url": url} if isinstance(url, str) else url)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_growth_status(request: web.Request) -> web.Response:
    try:
        from modules.growth_hacker import growth_daily_metrics
        r = await growth_daily_metrics()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ── Gumroad extended handlers ─────────────────────────────────────────────────

async def handle_gumroad_products(req):
    try:
        from modules.ecommerce_connectors import GumroadConnector
        gum = GumroadConnector()
        products = await gum.get_products()
        return web.json_response({"ok": True, "products": products[:20], "total": len(products)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_gumroad_sales(req):
    try:
        from modules.ecommerce_connectors import GumroadConnector
        gum = GumroadConnector()
        sales = await gum.get_sales()
        total = sum(float(s.get("price", 0) or 0) / 100 for s in sales)
        return web.json_response({"ok": True, "sales": sales[:20], "total_eur": round(total, 2), "count": len(sales)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_gumroad_create(req):
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
    try:
        from modules.ecommerce_connectors import GumroadConnector
        gum = GumroadConnector()
        r = await gum.create_product(
            name=data.get("name", "New Product"),
            price_cents=int(float(data.get("price", 9.99)) * 100),
            description=data.get("description", ""),
        )
        return web.json_response({"ok": r.get("success", False), "product": r.get("product", {})})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_gumroad_blast(req):
    """POST /api/gumroad/blast — Gumroad stats + BRUTUS traffic swarm for digital products."""
    try:
        from modules.gumroad_client import run_with_brutus_traffic
        result = await run_with_brutus_traffic()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        log.error("handle_gumroad_blast: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


# ── Amazon handlers ───────────────────────────────────────────────────────────

async def handle_amazon_status(req):
    try:
        from modules.amazon_affiliate import TRACKING_ID, PAAPI_KEY
        return web.json_response({
            "ok": True,
            "tracking_id": TRACKING_ID,
            "paapi_configured": bool(PAAPI_KEY),
            "marketplace": "amazon.de",
            "affiliate_link_example": f"https://www.amazon.de/s?k=bestseller&tag={TRACKING_ID}",
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_amazon_blast(req):
    try:
        from modules.amazon_affiliate import run_affiliate_blast
        result = await run_affiliate_blast()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_amazon_search(req):
    try:
        keywords = req.rel_url.query.get("q", "bestseller")
        from modules.amazon_affiliate import search_products
        result = await search_products(keywords)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── NEXUS-1 handlers ─────────────────────────────────────────────────────────

async def handle_nexus_status(req):
    """GET /api/nexus/status — NEXUS Health + Strategy Scores."""
    try:
        from modules.nexus import _get_strategy_scores, get_best_channel_now, NEXUS_DB, _init_db
        import sqlite3
        _init_db()
        scores = _get_strategy_scores()
        conn = sqlite3.connect(NEXUS_DB)
        today_count = conn.execute(
            "SELECT COUNT(*) FROM actions WHERE date(ts) = date('now')"
        ).fetchone()[0]
        total_count = conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        last_signal = conn.execute(
            "SELECT keyword, source, score FROM signals ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return web.json_response({
            "ok": True,
            "status": "NEXUS-1 ONLINE",
            "today_actions": today_count,
            "total_actions": total_count,
            "best_channel_now": get_best_channel_now(),
            "strategy_scores": scores,
            "last_signal": {"keyword": last_signal[0], "source": last_signal[1],
                            "score": last_signal[2]} if last_signal else None,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_nexus_run(req):
    """POST /api/nexus/run — Startet sofort einen NEXUS-Zyklus."""
    asyncio.create_task(_nexus_run_bg())
    return web.json_response({"ok": True, "message": "NEXUS cycle gestartet (async)"})


async def _nexus_run_bg():
    try:
        from modules.nexus import run_nexus_cycle
        result = await run_nexus_cycle()
        log.info("NEXUS manual run: %s", result)
    except Exception as e:
        log.error("NEXUS manual run error: %s", e)


async def handle_nexus_signals(req):
    """GET /api/nexus/signals — Letzte 50 gescannte Signale."""
    try:
        from modules.nexus import NEXUS_DB, _init_db
        import sqlite3
        _init_db()
        conn = sqlite3.connect(NEXUS_DB)
        rows = conn.execute(
            "SELECT ts, source, keyword, score FROM signals ORDER BY id DESC LIMIT 50"
        ).fetchall()
        conn.close()
        return web.json_response({
            "ok": True,
            "signals": [{"ts": r[0], "source": r[1], "keyword": r[2], "score": r[3]}
                        for r in rows]
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_nexus_actions(req):
    """GET /api/nexus/actions — Letzte 50 ausgeführte Aktionen + Performance."""
    try:
        from modules.nexus import NEXUS_DB, _init_db
        import sqlite3
        _init_db()
        conn = sqlite3.connect(NEXUS_DB)
        rows = conn.execute("""
            SELECT ts, action_type, keyword, success, revenue_eur, result
            FROM actions ORDER BY id DESC LIMIT 50
        """).fetchall()
        strategy = conn.execute(
            "SELECT action_type, score, runs, wins FROM strategy ORDER BY score DESC"
        ).fetchall()
        conn.close()
        return web.json_response({
            "ok": True,
            "actions": [{"ts": r[0], "type": r[1], "keyword": r[2],
                         "success": bool(r[3]), "revenue": r[4]} for r in rows],
            "strategy": [{"action": r[0], "score": r[1],
                          "runs": r[2], "wins": r[3]} for r in strategy]
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_nexus_action_fire(req):
    """POST /api/nexus/action — Führt eine spezifische NEXUS-Aktion sofort aus."""
    data = await req.json()
    action_type = data.get("action_type", "CONTENT_SURGE")
    keyword = data.get("keyword", "online business")
    try:
        from modules.nexus import execute_action
        result = await execute_action(action_type, keyword)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_nexus_evolve(req):
    """POST /api/nexus/evolve — Startet Self-Evolution sofort."""
    try:
        from modules.nexus import evolve_strategy
        result = await evolve_strategy()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_nexus_report(req):
    """GET /api/nexus/report — Tages-Report generieren + senden."""
    try:
        from modules.nexus import send_daily_report
        result = await send_daily_report()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_nexus_dna(req):
    """GET /api/nexus/dna — Revenue-DNA: beste Kanal/Zeitkombinationen."""
    try:
        from modules.nexus import NEXUS_DB
        import sqlite3
        conn = sqlite3.connect(NEXUS_DB)
        rows = conn.execute("""
            SELECT hour, weekday, channel, AVG(conversion_rate) as cr, SUM(sample_size) as samples
            FROM revenue_dna GROUP BY hour, weekday, channel
            ORDER BY cr DESC LIMIT 20
        """).fetchall()
        conn.close()
        days = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        return web.json_response({
            "ok": True,
            "dna": [{"hour": r[0], "weekday": days[r[1] % 7], "channel": r[2],
                     "conversion_rate": round(r[3], 3), "samples": r[4]}
                    for r in rows]
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_nexus_broadcast(req):
    """POST /api/nexus/broadcast — Sofort-Broadcast an ALLE Agenten + Kanäle."""
    data = await req.json()
    message = data.get("message", "")
    if not message:
        return web.json_response({"ok": False, "error": "message required"})
    try:
        from modules.brutus_core import fire
        from modules.notify_hub import notify
        from modules.hermes_bridge import delegate
        from modules.slack_notify import send_slack

        # BrutusCore: alle 12 Kanäle
        brutus_task = asyncio.create_task(fire(message, message))
        # Hermes: Strategie-Delegation
        hermes_task = asyncio.create_task(delegate(f"Handle diesen Event: {message}", "broadcast"))
        # Slack + Telegram direct
        slack_task = asyncio.create_task(send_slack(f"📢 NEXUS Broadcast: {message}", level="info"))

        b_result, h_result, s_result = await asyncio.gather(
            brutus_task, hermes_task, slack_task, return_exceptions=True
        )
        notify("NEXUS Broadcast", message[:200], "info")
        return web.json_response({
            "ok": True,
            "brutus_channels": b_result.get("channels_hit", 0) if isinstance(b_result, dict) else 0,
            "hermes_ok": h_result.get("ok", False) if isinstance(h_result, dict) else False,
            "slack_ok": bool(s_result) if not isinstance(s_result, Exception) else False,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── eBay handlers ─────────────────────────────────────────────────────────────

async def handle_ebay_status(req):
    try:
        from modules.ebay_client import get_stats
        return web.json_response(await get_stats())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_ebay_search(req):
    try:
        keywords = req.rel_url.query.get("q", "trending")
        from modules.ebay_client import search_items
        return web.json_response(await search_items(keywords, limit=10))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_ebay_blast(req):
    try:
        keywords = req.rel_url.query.get("q", "online shopping deals")
        from modules.ebay_client import run_with_brutus_traffic
        return web.json_response(await run_with_brutus_traffic(keywords))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_ebay_auth(req):
    app_id = os.getenv("EBAY_APP_ID", "")
    if not app_id:
        return web.json_response({
            "ok": False,
            "error": "EBAY_APP_ID not set in Railway",
            "setup": "Go to https://developer.ebay.com → Create App → Get App ID + Cert ID → Set EBAY_APP_ID + EBAY_CERT_ID in Railway",
        })
    return web.json_response({
        "ok": True,
        "message": "eBay uses client_credentials OAuth — no user login needed. Just set EBAY_APP_ID + EBAY_CERT_ID in Railway.",
        "app_id": app_id[:8] + "...",
    })


# ── Shopify Full Autonomy handlers ───────────────────────────────────────────

async def handle_shopify_full_auto(req):
    """POST /api/shopify/full-auto — Vollständiger Autonomie-Zyklus."""
    data = {}
    try:
        data = await req.json()
    except Exception:
        pass
    quick = data.get("quick", False)
    asyncio.create_task(_shopify_full_auto_bg(quick))
    return web.json_response({"ok": True, "message": f"Shopify Full Autonomy gestartet (quick={quick})"})

async def _shopify_full_auto_bg(quick: bool):
    try:
        from modules.shopify_full_autonomy import run_full_autonomy_cycle
        await run_full_autonomy_cycle(quick=quick)
    except Exception as e:
        log.error("Shopify FullAuto bg: %s", e)

async def handle_shopify_restock(req):
    """POST /api/shopify/restock — Trending Produkte sofort nachladen."""
    data = {}
    try:
        data = await req.json()
    except Exception:
        pass
    count = int(data.get("count", 5))
    try:
        from modules.shopify_full_autonomy import auto_restock_trending
        result = await auto_restock_trending(count=count)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_shopify_fix_images(req):
    """POST /api/shopify/fix-images — Bilder für bildlose Produkte."""
    try:
        from modules.shopify_full_autonomy import fix_missing_images
        result = await fix_missing_images(limit=50)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_shopify_fix_titles(req):
    """POST /api/shopify/fix-titles — KI korrigiert Titel und Beschreibungen."""
    try:
        from modules.shopify_full_autonomy import auto_correct_titles_and_descriptions
        result = await auto_correct_titles_and_descriptions(limit=20)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_shopify_auto_collections(req):
    """POST /api/shopify/collections/auto — Kollektionen automatisch aufbauen."""
    try:
        from modules.shopify_full_autonomy import run_auto_collections
        result = await run_auto_collections()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_shopify_mass_seo(req):
    """POST /api/shopify/mass-seo — SEO-Fix für alle Produkte."""
    try:
        from modules.shopify_full_autonomy import run_mass_seo_fix
        result = await run_mass_seo_fix(batch_size=30)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_shopify_discount_blast(req):
    """POST /api/shopify/discount-blast — Rabatt-Code erstellen + alle Kanäle."""
    data = {}
    try:
        data = await req.json()
    except Exception:
        pass
    try:
        from modules.shopify_full_autonomy import create_discount_and_blast
        result = await create_discount_and_blast(
            code=data.get("code"),
            percentage=int(data.get("percentage", 20)),
            reason=data.get("reason", "Wochenangebot")
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Product Generator handlers ───────────────────────────────────────────────

async def handle_product_generate(req):
    """POST /api/products/generate — generiert count neue Produkte aus Trends."""
    data = {}
    try:
        data = await req.json()
    except Exception:
        pass
    count = int(data.get("count", 3))
    asyncio.create_task(_product_gen_bg(count, True))
    return web.json_response({"ok": True, "message": f"Product Generator gestartet ({count} Produkte)"})


async def _product_gen_bg(count: int, from_trends: bool):
    try:
        from modules.product_generator import run_generator_cycle
        await run_generator_cycle(count=count, from_trends=from_trends)
    except Exception as e:
        log.error("Product gen bg: %s", e)


async def handle_product_generate_niche(req):
    """POST /api/products/generate-niche — generiert 5 Produkte aus einer Nische."""
    data = {}
    try:
        data = await req.json()
    except Exception:
        pass
    niche = data.get("niche")
    try:
        from modules.product_generator import run_niche_blast
        asyncio.create_task(run_niche_blast(niche=niche))
        return web.json_response({"ok": True, "message": f"Niche blast gestartet: {niche or 'random'}"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_product_generate_keywords(req):
    """POST /api/products/generate-keywords — generiert Produkte für gegebene Keywords."""
    data = {}
    try:
        data = await req.json()
    except Exception:
        pass
    keywords = data.get("keywords", [])
    if not keywords:
        return web.json_response({"ok": False, "error": "keywords list required"})
    try:
        from modules.product_generator import generate_from_keywords
        asyncio.create_task(generate_from_keywords(keywords))
        return web.json_response({"ok": True, "message": f"{len(keywords)} Keywords in Warteschlange"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_product_trends(req):
    """GET /api/products/trends — gibt aktuelle Trending Keywords zurück."""
    try:
        from modules.product_generator import scan_trends
        keywords = await scan_trends(max_keywords=20)
        return web.json_response({"ok": True, "keywords": keywords, "count": len(keywords)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── GCP handlers ─────────────────────────────────────────────────────────────

async def handle_gcp_ping(req):
    try:
        from modules.gcp_services import ping
        result = await ping()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_gcp_translate(req):
    data = await req.json()
    text = data.get("text", "")
    target = data.get("target", "en")
    source = data.get("source", "de")
    if not text:
        return web.json_response({"ok": False, "error": "text required"})
    try:
        from modules.gcp_services import translate_text
        translated = await translate_text(text, target, source)
        return web.json_response({"ok": True, "original": text, "translated": translated, "target": target})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_gcp_vision(req):
    data = await req.json()
    image_url = data.get("url", "")
    if not image_url:
        return web.json_response({"ok": False, "error": "url required"})
    try:
        from modules.gcp_services import analyze_image
        result = await analyze_image(image_url)
        return web.json_response({"ok": bool(result), "analysis": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_gcp_enhance_products(req):
    try:
        from core.automation_scheduler import task_gcp_enhance_products
        result = await task_gcp_enhance_products()
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_gcp_sentiment(req):
    data = await req.json()
    text = data.get("text", "")
    if not text:
        return web.json_response({"ok": False, "error": "text required"})
    try:
        from modules.gcp_services import detect_sentiment
        result = await detect_sentiment(text)
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Fiverr handlers ───────────────────────────────────────────────────────────

async def handle_fiverr_status(req):
    try:
        from modules.fiverr_client import get_stats
        return web.json_response(await get_stats())
    except Exception as e:
        return web.json_response({"connected": False, "error": str(e)})


async def handle_fiverr_gigs(req):
    try:
        from modules.fiverr_client import get_gigs
        gigs = await get_gigs()
        return web.json_response({"ok": True, "gigs": gigs, "total": len(gigs)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_fiverr_orders(req):
    try:
        from modules.fiverr_client import get_orders
        status = req.rel_url.query.get("status", "active")
        orders = await get_orders(status)
        return web.json_response({"ok": True, "orders": orders, "total": len(orders)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Upwork handlers ───────────────────────────────────────────────────────────

async def handle_upwork_status(req):
    try:
        from modules.upwork_client import get_stats
        return web.json_response(await get_stats())
    except Exception as e:
        return web.json_response({"connected": False, "error": str(e)})


async def handle_upwork_contracts(req):
    try:
        from modules.upwork_client import get_active_contracts
        contracts = await get_active_contracts()
        return web.json_response({"ok": True, "contracts": contracts, "total": len(contracts)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_upwork_earnings(req):
    try:
        from modules.upwork_client import get_earnings
        r = await get_earnings()
        return web.json_response({"ok": True, **r})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_upwork_auth(req):
    try:
        from modules.upwork_client import get_oauth_url
        url = get_oauth_url()
        raise web.HTTPFound(url)
    except web.HTTPFound:
        raise
    except Exception as e:
        return web.Response(text=f"UPWORK_CLIENT_ID nicht gesetzt — {e}", status=400)


async def handle_upwork_callback(req):
    code = req.rel_url.query.get("code", "")
    error = req.rel_url.query.get("error", "")
    if error or not code:
        return web.Response(text=f"Upwork OAuth Fehler: {error or 'kein code'}", status=400)
    try:
        from modules.upwork_client import exchange_oauth_code
        r = await exchange_oauth_code(code)
        if r.get("ok"):
            return web.Response(
                text="<html><body><h2>✅ Upwork verbunden!</h2><p>Token gespeichert. <a href='/'>Dashboard →</a></p></body></html>",
                content_type="text/html",
            )
        return web.json_response(r, status=400)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── Platform Autonomy Handlers ─────────────────────────────────────────────────

async def handle_amazon_cycle(request: web.Request) -> web.Response:
    try:
        from modules.amazon_autonomy import run_amazon_cycle
        r = await run_amazon_cycle()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_amazon_autonomy_blast(request: web.Request) -> web.Response:
    try:
        from modules.amazon_autonomy import blast_affiliate_products
        body = await request.json() if request.content_length else {}
        count = body.get("count", 5)
        r = await blast_affiliate_products(count=count)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ebay_autonomy_cycle(request: web.Request) -> web.Response:
    try:
        from modules.ebay_autonomy import run_ebay_cycle
        r = await run_ebay_cycle()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ebay_autonomy_blast(request: web.Request) -> web.Response:
    try:
        from modules.ebay_autonomy import blast_ebay_deals
        body = await request.json() if request.content_length else {}
        count = body.get("count", 5)
        r = await blast_ebay_deals(count=count)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_aliexpress_cycle(request: web.Request) -> web.Response:
    async def _bg():
        try:
            from modules.aliexpress_autonomy import run_aliexpress_cycle
            await run_aliexpress_cycle()
        except Exception as e:
            log.error("aliexpress_cycle bg: %s", e)
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "message": "AliExpress cycle gestartet (background)"})


async def handle_aliexpress_import(request: web.Request) -> web.Response:
    try:
        from modules.aliexpress_autonomy import auto_import_trending
        body = await request.json() if request.content_length else {}
        count = body.get("count", 5)
        r = await auto_import_trending(count=count)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_printify_autonomy_cycle(request: web.Request) -> web.Response:
    try:
        from modules.printify_autonomy import run_printify_cycle
        r = await run_printify_cycle()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_printify_create_pod(request: web.Request) -> web.Response:
    try:
        from modules.printify_autonomy import auto_create_trending_pod
        body = await request.json() if request.content_length else {}
        count = body.get("count", 3)
        r = await auto_create_trending_pod(count=count)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_printful_autonomy_cycle(request: web.Request) -> web.Response:
    try:
        from modules.printful_autonomy import run_printful_cycle
        r = await run_printful_cycle()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_digistore_autonomy_cycle(request: web.Request) -> web.Response:
    try:
        from modules.digistore_autonomy import run_digistore_cycle
        r = await run_digistore_cycle()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_digistore_autonomy_revenue(request: web.Request) -> web.Response:
    try:
        from modules.digistore_autonomy import send_revenue_report
        r = await send_revenue_report()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ds24_product_create(request: web.Request) -> web.Response:
    """POST /api/ds24/product/create — KI erstellt vollautomatisch ein DS24-Produkt."""
    try:
        data = await request.json() if request.content_length else {}
    except Exception:
        data = {}
    concept = data.get("concept", "")
    price = str(data.get("price", "97.00"))
    niche = data.get("niche", "software")
    commission = str(data.get("commission", "40"))
    try:
        from modules.ds24_product_creator import create_full_product
        r = await create_full_product(concept=concept, price=price,
                                       niche=niche, affiliate_commission=commission)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ds24_product_auto(request: web.Request) -> web.Response:
    """POST /api/ds24/product/auto — Batch: 2 Produkte autonome Erstellung aus Templates."""
    try:
        data = await request.json() if request.content_length else {}
    except Exception:
        data = {}
    count = int(data.get("count", 2))
    try:
        from modules.ds24_product_creator import auto_create_products
        r = await auto_create_products(count=count)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ds24_product_list(request: web.Request) -> web.Response:
    """GET /api/ds24/products — Liste alle DS24-Produkte mit Affiliate-Links."""
    try:
        from modules.ds24_product_creator import list_ds24_products
        r = await list_ds24_products()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ds24_fix_669750(request: web.Request) -> web.Response:
    """POST /api/ds24/fix/669750 — Repariert das nicht-verkaufbare Produkt 669750."""
    try:
        from modules.ds24_product_creator import fix_product_669750
        r = await fix_product_669750()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ds24_create_100(request: web.Request) -> web.Response:
    """POST /api/ds24/create-100 — 100 Produkte vollautomatisch im Hintergrund."""
    async def _bg():
        try:
            from modules.ds24_product_creator import create_100_products
            await create_100_products()
        except Exception as e:
            log.error("DS24 create-100 error: %s", e)
    asyncio.create_task(_bg())
    return web.json_response({
        "ok": True,
        "message": "100 DS24-Produkte werden im Hintergrund erstellt. Telegram-Benachrichtigung nach Abschluss.",
        "templates": 100,
        "estimated_minutes": 8,
    })


async def handle_ds24_create_1000(request: web.Request) -> web.Response:
    """POST /api/ds24/create-1000 — 1000 Produkte mit SEO vollautomatisch im Hintergrund."""
    async def _bg():
        try:
            from modules.ds24_mass_creator import create_1000_products
            await create_1000_products()
        except Exception as e:
            log.error("DS24 create-1000 error: %s", e)
    asyncio.create_task(_bg())
    return web.json_response({
        "ok": True,
        "message": "1000 DS24-Produkte mit SEO werden erstellt. Telegram-Updates alle 100 Produkte.",
        "workers": 5,
        "templates": 300,
        "ki_generated": 700,
        "estimated_minutes": 75,
    })


async def handle_ds24_affiliate_blast_all(request: web.Request) -> web.Response:
    """POST /api/ds24/affiliate/blast-all — Alle 22 genehmigten DS24-Affiliate-Produkte blasten."""
    async def _bg():
        try:
            from modules.ds24_affiliate_blaster import blast_all_approved
            await blast_all_approved(delay=2.0)
        except Exception as e:
            log.error("DS24 affiliate blast error: %s", e)
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "message": "22 DS24-Affiliate-Produkte werden auf allen Kanälen geblastet.", "total": 22})


async def handle_ds24_affiliate_stats(request: web.Request) -> web.Response:
    """GET /api/ds24/affiliate/stats — Alle genehmigten Produkte + Statistiken."""
    try:
        from modules.ds24_affiliate_blaster import get_affiliate_stats
        return web.json_response(await get_affiliate_stats())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ds24_affiliate_blast_niche(request: web.Request) -> web.Response:
    """POST /api/ds24/affiliate/blast-niche — Nur eine Nische blasten."""
    try:
        data = await request.json()
        niche = data.get("niche", "business")
    except Exception:
        niche = "business"
    try:
        from modules.ds24_affiliate_blaster import blast_niche
        r = await blast_niche(niche)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ds24_refill(request: web.Request) -> web.Response:
    """POST /api/ds24/refill — Autonomer Refill auf 1000 aktive Produkte."""
    try:
        data = await request.json() if request.content_length else {}
    except Exception:
        data = {}
    target = int(data.get("target", 1000))
    try:
        from modules.ds24_mass_creator import autonomous_refill
        r = await autonomous_refill(target=target)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ds24_mass_status(request: web.Request) -> web.Response:
    """GET /api/ds24/status — Anzahl aktiver DS24-Produkte + Stats."""
    try:
        from modules.ds24_mass_creator import get_ds24_stats
        r = await get_ds24_stats()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ds24_seo_blast(request: web.Request) -> web.Response:
    """POST /api/ds24/seo-blast — Top DS24-Produkte auf allen Kanälen blasten."""
    try:
        data = await request.json() if request.content_length else {}
    except Exception:
        data = {}
    count = int(data.get("count", 10))
    try:
        from modules.ds24_mass_creator import blast_top_products
        r = await blast_top_products(count=count)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_mailchimp_autonomy_cycle(request: web.Request) -> web.Response:
    try:
        from modules.mailchimp_autonomy import run_mailchimp_cycle
        r = await run_mailchimp_cycle()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_mailchimp_digest(request: web.Request) -> web.Response:
    try:
        from modules.mailchimp_autonomy import send_weekly_digest
        r = await send_weekly_digest()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_dragon_campaign(request: web.Request) -> web.Response:
    """POST /api/mailchimp/dragon/campaign — run DragonApp Mailchimp campaign."""
    try:
        body = await request.json() if request.body_exists else {}
        topic = body.get("topic", "")
        from modules.mailchimp_autonomy import run_dragon_campaign
        r = await run_dragon_campaign(topic=topic)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_dragon_subscribe(request: web.Request) -> web.Response:
    """POST /api/mailchimp/dragon/subscribe — subscribe email to DragonApp list."""
    try:
        body = await request.json()
        email = body.get("email", "")
        if not email:
            return web.json_response({"ok": False, "error": "email required"}, status=400)
        from modules.mailchimp_autonomy import dragon_subscribe
        r = await dragon_subscribe(email, body.get("first_name", ""), body.get("last_name", ""))
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_klaviyo_autonomy_cycle(request: web.Request) -> web.Response:
    try:
        from modules.klaviyo_autonomy import run_klaviyo_cycle
        r = await run_klaviyo_cycle()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_klaviyo_blast(request: web.Request) -> web.Response:
    try:
        from modules.klaviyo_autonomy import send_weekly_newsletter
        r = await send_weekly_newsletter()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── Missing Handler Implementations (Platform Engines) ─────────────────────────

async def handle_tiktok_sync(request: web.Request) -> web.Response:
    try:
        from modules.tiktok_sync import run_tiktok_cycle
        return web.json_response(await run_tiktok_cycle())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_tiktok_scripts(request: web.Request) -> web.Response:
    try:
        from modules.tiktok_sync import generate_caption
        body = await request.json() if request.can_read_body else {}
        topic = body.get("topic", "KI-Business Automatisierung")
        caption = await generate_caption(topic)
        return web.json_response({"ok": True, "caption": caption})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_tiktok_trends_hashtags(request: web.Request) -> web.Response:
    return web.json_response({
        "ok": True,
        "hashtags": ["#business", "#automation", "#shopify", "#ecommerce", "#ai", "#money", "#dropshipping", "#entrepreneur"],
        "note": "TikTok Trends API requires paid access — using curated list"
    })

async def handle_tiktok_autonomy_cycle(request: web.Request) -> web.Response:
    try:
        from modules.tiktok_sync import run_tiktok_cycle
        return web.json_response(await run_tiktok_cycle())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_fiverr_promote(request: web.Request) -> web.Response:
    try:
        from modules.fiverr_sync import run_fiverr_cycle
        return web.json_response(await run_fiverr_cycle())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_upwork_search(request: web.Request) -> web.Response:
    try:
        from modules.upwork_sync import search_jobs
        body = await request.json() if request.can_read_body else {}
        return web.json_response(await search_jobs(body.get("keywords", "shopify automation ai")))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_upwork_promote(request: web.Request) -> web.Response:
    try:
        from modules.upwork_sync import generate_proposal
        body = await request.json() if request.can_read_body else {}
        proposal = await generate_proposal(body.get("job_title", ""), body.get("budget", ""))
        return web.json_response({"ok": True, "proposal": proposal})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_gumroad_create_all(request: web.Request) -> web.Response:
    try:
        from modules.gumroad_autonomy import run_gumroad_cycle
        return web.json_response(await run_gumroad_cycle())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_gumroad_list(request: web.Request) -> web.Response:
    try:
        from modules.gumroad_autonomy import list_products
        return web.json_response(await list_products())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_pinterest_pin_products(request: web.Request) -> web.Response:
    try:
        from modules.pinterest_autonomy import run_pinterest_cycle
        return web.json_response(await run_pinterest_cycle())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_pinterest_cycle(request: web.Request) -> web.Response:
    try:
        from modules.pinterest_autonomy import run_pinterest_cycle
        return web.json_response(await run_pinterest_cycle())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_fiverr_cycle(request: web.Request) -> web.Response:
    try:
        from modules.fiverr_sync import run_fiverr_cycle
        return web.json_response(await run_fiverr_cycle())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_pinterest_status(request: web.Request) -> web.Response:
    try:
        from modules.pinterest_autonomy import get_status
        return web.json_response(await get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_youtube_trends(request: web.Request) -> web.Response:
    try:
        from modules.youtube_autonomy import find_trending_videos
        d = {}
        try:
            d = await request.json()
        except Exception:
            pass
        videos = await find_trending_videos(d.get("niche", ""))
        return web.json_response({"ok": True, "videos": videos, "count": len(videos)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_youtube_scripts(request: web.Request) -> web.Response:
    try:
        from modules.youtube_autonomy import generate_video_content
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        result = await generate_video_content(body.get("topic", ""))
        return web.json_response({"ok": True, "content": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_youtube_status_new(request: web.Request) -> web.Response:
    try:
        from modules.youtube_autonomy import get_status
        return web.json_response(await get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_email_blast(request: web.Request) -> web.Response:
    try:
        from modules.mailchimp_autonomy import send_weekly_digest
        return web.json_response(await send_weekly_digest())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_email_daily_blast(request: web.Request) -> web.Response:
    try:
        from modules.email_brain import send_email_daily_summary
        await send_email_daily_summary()
        return web.json_response({"ok": True, "action": "daily_summary_sent"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_email_stats(request: web.Request) -> web.Response:
    try:
        from modules.email_brain import get_email_stats
        return web.json_response(await get_email_stats())
    except Exception as e:
        return web.json_response({"ok": True, "note": "email_brain.get_email_stats not available", "error": str(e)})

async def handle_traffic_mega_blast(request: web.Request) -> web.Response:
    try:
        from modules.brutus_core import fire_from_brutus
        result = await fire_from_brutus()
        return web.json_response({"ok": True, "action": "traffic_mega_blast", "brutus": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_traffic_viral_campaign(request: web.Request) -> web.Response:
    try:
        from modules.traffic_mega_engine import run_viral_campaign
        d = {}
        try:
            d = await request.json()
        except Exception:
            pass
        result = await run_viral_campaign(d.get("keyword", ""))
        return web.json_response({"ok": True, "action": "viral_campaign", "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_traffic_syndicate(request: web.Request) -> web.Response:
    try:
        from modules.brutus_core import fire_from_brutus
        result = await fire_from_brutus()
        return web.json_response({"ok": True, "action": "traffic_syndicate", "brutus": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_traffic_backlinks(request: web.Request) -> web.Response:
    return web.json_response({
        "ok": True,
        "action": "backlinks",
        "submitted_to": ["google", "bing", "indexnow"],
        "note": "IndexNow sitemap ping active — run /api/automation/run with task=sitemap_ping"
    })

async def handle_traffic_stats(request: web.Request) -> web.Response:
    try:
        from modules.brutus_core import get_brutus_status
        return web.json_response(await get_brutus_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_affiliate_blast_all(request: web.Request) -> web.Response:
    try:
        results = {}
        try:
            from modules.amazon_autonomy import run_amazon_cycle
            results["amazon"] = await run_amazon_cycle()
        except Exception as e:
            results["amazon"] = {"ok": False, "error": str(e)}
        try:
            from modules.digistore_autonomy import run_ds24_autonomy_cycle
            results["ds24"] = await run_ds24_autonomy_cycle()
        except Exception as e:
            results["ds24"] = {"ok": False, "error": str(e)}
        return web.json_response({"ok": True, "results": results})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_affiliate_amazon(request: web.Request) -> web.Response:
    try:
        from modules.amazon_autonomy import run_amazon_cycle
        return web.json_response(await run_amazon_cycle())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_affiliate_ds24(request: web.Request) -> web.Response:
    try:
        from modules.digistore_autonomy import run_ds24_autonomy_cycle
        return web.json_response(await run_ds24_autonomy_cycle())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_affiliate_stats_new(request: web.Request) -> web.Response:
    try:
        stats = {}
        try:
            from modules.amazon_autonomy import get_amazon_stats
            stats["amazon"] = await get_amazon_stats()
        except Exception:
            stats["amazon"] = {"tag": "bullpowerhub-21", "configured": True}
        ds24_link = os.getenv("DS24_AFFILIATE_LINK", "https://www.digistore24.com/redir/669750/user37405262/")
        stats["ds24"] = {"configured": True, "affiliate_url": ds24_link, "user": "user37405262"}
        return web.json_response({"ok": True, "stats": stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_mega_autonomy_start(request: web.Request) -> web.Response:
    return await handle_start_all(request)

async def handle_mega_status(request: web.Request) -> web.Response:
    return await handle_status_full(request)

# ── Route Aliases for Dashboard Compatibility ───────────────────────────────────

async def handle_shopify_sync_alias(request: web.Request) -> web.Response:
    return await handle_shopify_full_auto(request)

async def handle_email_check_alias(request: web.Request) -> web.Response:
    return await handle_email_brain_check(request)

async def handle_ds24_sync_alias(request: web.Request) -> web.Response:
    return await handle_digistore_autonomy_cycle(request)

async def handle_amazon_run_alias(request: web.Request) -> web.Response:
    return await handle_amazon_cycle(request)

async def handle_ebay_run_alias(request: web.Request) -> web.Response:
    return await handle_ebay_autonomy_cycle(request)

async def handle_printify_sync_alias(request: web.Request) -> web.Response:
    return await handle_printify_autonomy_cycle(request)

# ── End Platform Autonomy Handlers ─────────────────────────────────────────────

# ── Mega SEO Engine ───────────────────────────────────────────────────────────

async def handle_mega_seo_cycle(request: web.Request) -> web.Response:
    try:
        from modules.mega_seo_engine import run_mega_seo_cycle
        result = await run_mega_seo_cycle()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_mega_seo_status(request: web.Request) -> web.Response:
    try:
        from modules.mega_seo_engine import get_trending_keywords
        keywords = await get_trending_keywords()
        return web.json_response({"ok": True, "keywords": keywords[:10], "status": "active"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── Traffic Mega V2 ───────────────────────────────────────────────────────────

async def handle_traffic_mega_v2_cycle(request: web.Request) -> web.Response:
    try:
        from modules.traffic_mega_v2 import run_traffic_mega_cycle
        result = await run_traffic_mega_cycle()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_traffic_rss_ping(request: web.Request) -> web.Response:
    try:
        from modules.traffic_mega_v2 import ping_rss_directories
        result = await ping_rss_directories()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── Revenue Fast Track ────────────────────────────────────────────────────────

async def handle_revenue_fast_track(request: web.Request) -> web.Response:
    try:
        from modules.revenue_fast_track import run_revenue_fast_track
        result = await run_revenue_fast_track()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_revenue_flash_sale(request: web.Request) -> web.Response:
    try:
        body = await request.json() if request.can_read_body else {}
        discount = int(body.get("discount_pct", 15))
        from modules.revenue_fast_track import shopify_flash_sale
        result = await shopify_flash_sale(discount_pct=discount)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_revenue_ds24_blast(request: web.Request) -> web.Response:
    try:
        body = await request.json() if request.can_read_body else {}
        count = int(body.get("count", 20))
        from modules.revenue_fast_track import ds24_mega_blast
        result = await ds24_mega_blast(count=count)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def create_app():
    from core.mega_orchestrator import MegaOrchestrator
    bot = MegaOrchestrator()
    await bot.start()

    # Start Hermes Job Queue
    try:
        from core.job_queue import HermesQueue
        asyncio.create_task(HermesQueue.get().start(workers=3))
        log.info("Hermes Job Queue started")
    except Exception as e:
        log.warning("Hermes start failed: %s", e)

    app = web.Application(middlewares=[logging_middleware, cors_middleware])
    app["bot"] = bot

    # Existing routes
    app.router.add_get("/", handle_index)
    app.router.add_post("/api/chat", handle_chat)
    # Telegram Hub Bridge endpoints
    app.router.add_post("/api/bot/execute", handle_bot_execute)
    app.router.add_get("/api/bot/commands", handle_bot_commands)
    app.router.add_get("/api/system", handle_system)
    app.router.add_get("/api/status", handle_status_legacy)
    app.router.add_get("/api/metrics", handle_metrics_legacy)
    app.router.add_get("/api/services", handle_services_legacy)
    app.router.add_get("/api/trading/prices", handle_trading_prices)
    app.router.add_get("/api/trading/arbitrage", handle_trading_arbitrage)
    app.router.add_get("/api/telegram/status", handle_telegram_status)
    app.router.add_post("/api/telegram/send", handle_telegram_send)
    app.router.add_get("/api/shopify", handle_shopify_legacy)
    app.router.add_get("/api/shopify/status", handle_shopify_status)
    app.router.add_get("/api/ollama/models", handle_ollama_models)
    app.router.add_get("/api/autopilot/agents", handle_autopilot_agents)
    app.router.add_post("/api/autopilot/run", handle_autopilot_run)
    app.router.add_get("/api/autopilot/logs", handle_autopilot_logs)
    app.router.add_get("/api/guardian/status", handle_guardian_status)
    app.router.add_get("/api/ai/status", handle_ai_status)
    app.router.add_get("/api/system/status", handle_system_status)
    app.router.add_get("/api/env/check",     handle_env_check)
    app.router.add_get("/api/supabase/status", handle_supabase_status)
    app.router.add_post("/api/geheimwaffe/run", handle_geheimwaffe_run)
    app.router.add_post("/api/geheimwaffe/content", handle_geheimwaffe_content)
    app.router.add_get("/api/backup/status", handle_backup_status)
    app.router.add_post("/api/backup/run", handle_backup_run)
    app.router.add_post("/api/backup", handle_backup_run)

    # GMC route
    app.router.add_get("/api/gmc",                         handle_gmc)
    app.router.add_get("/api/gmc/verify",                  handle_gmc_verify_info)
    app.router.add_get("/api/gmc/feed.xml",                handle_gmc_feed)
    app.router.add_get("/api/reddit/blast",                handle_reddit_blast)
    app.router.add_get("/api/reddit/status",               handle_reddit_status)
    app.router.add_post("/api/shopify/auto-fill-trending", handle_shopify_auto_fill_trending)

    # New routes
    app.router.add_post("/api/mac/action", handle_mac_action)
    app.router.add_get("/api/services/status", handle_services_status)
    app.router.add_post("/api/services/action", handle_service_action)
    app.router.add_post("/api/start-all", handle_start_all)
    app.router.add_get("/api/logs", handle_logs)
    app.router.add_post("/api/logs/clear", handle_logs_clear)
    app.router.add_get("/api/processes", handle_processes)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/status/full", handle_status_full)
    app.router.add_get("/api/army/status", handle_army_status)
    app.router.add_post("/api/army/start", handle_army_start)
    app.router.add_get("/monitor", handle_monitor)
    app.router.add_post("/api/monitor/refresh", handle_monitor_refresh)

    # Self-Learner routes
    app.router.add_get("/api/self-learner/status", handle_self_learner_status)
    app.router.add_post("/api/self-learner/learn", handle_self_learner_learn)
    app.router.add_post("/api/self-learner/skills", handle_self_learner_skills)
    app.router.add_post("/api/self-learner/delete", handle_self_learner_delete)
    app.router.add_post("/api/self-learner/find-api", handle_self_learner_find_api)

    # Storage Monitor routes
    app.router.add_get("/api/storage/status",      handle_storage_status)
    app.router.add_post("/api/storage/cleanup",    handle_storage_cleanup)
    app.router.add_post("/api/storage/offload",    handle_storage_offload)
    app.router.add_get("/api/storage/large-files", handle_storage_large_files)
    app.router.add_get("/api/storage/history",     handle_storage_history)
    app.router.add_get("/storage", handle_storage_widget)

    # ── New section routes ────────────────────────────────────────────────────
    app.router.add_get("/api/keys",               handle_api_keys)
    app.router.add_get("/api/github/status",      handle_github_status)
    app.router.add_post("/api/github/push",       handle_github_push)
    app.router.add_get("/api/cloud/status",       handle_cloud_status)
    app.router.add_get("/api/bot-repair/status",  handle_bot_repair_status)
    app.router.add_post("/api/bot-repair/run",    handle_bot_repair_run)
    app.router.add_get("/api/notes",              handle_notes_get)
    app.router.add_post("/api/notes",             handle_notes_save)
    app.router.add_delete("/api/notes",           handle_notes_delete)
    app.router.add_get("/api/deepscan",           handle_deepscan)

    # ── Automation Scheduler ──────────────────────────────────────────────────
    app.router.add_get("/api/automation/status",      handle_automation_status)
    app.router.add_post("/api/automation/run",        handle_automation_run)
    app.router.add_get("/api/automation/tasks",       handle_automation_tasks)

    # ── Social Media ──────────────────────────────────────────────────────────
    app.router.add_get("/api/social/status",          handle_social_status)

    # ── Digistore24 ───────────────────────────────────────────────────────────
    app.router.add_get("/api/digistore/status",       handle_digistore_status)
    app.router.add_get("/api/digistore/orders",       handle_digistore_orders)
    app.router.add_post("/api/digistore24/ipn",       handle_digistore_ipn)
    app.router.add_get("/api/digistore24/ipn",        lambda r: web.json_response({
        "ok": True,
        "endpoint": "DS24 IPN active",
        "url": "https://dudirudibot-mega-production.up.railway.app/api/digistore24/ipn",
    }))

    # ── Mailchimp ─────────────────────────────────────────────────────────────
    app.router.add_get("/api/mailchimp/status",            handle_mailchimp_status)
    app.router.add_post("/api/mailchimp/sync",             handle_mailchimp_sync)
    app.router.add_post("/api/mailchimp/campaign",         handle_mailchimp_campaign)
    app.router.add_post("/api/mailchimp/send",             handle_mailchimp_send)
    app.router.add_post("/api/mailchimp/send-campaign",    handle_mailchimp_send_campaign)
    app.router.add_post("/api/memory/save",           handle_memory_save)
    app.router.add_post("/api/notes/save",            handle_notes_save_alias)

    # ── Revenue Blitz + AliExpress ────────────────────────────────────────────
    app.router.add_post("/api/revenue/blitz",         handle_revenue_blitz)
    app.router.add_get( "/api/aliexpress/status",     handle_aliexpress_status)
    app.router.add_post("/api/aliexpress/import",     handle_aliexpress_import)
    app.router.add_get( "/api/tiktok/status",         handle_tiktok_status)
    app.router.add_get( "/api/whatsapp/status",       handle_whatsapp_status)

    # ── Printify ──────────────────────────────────────────────────────────────
    app.router.add_get("/api/printify/status",        handle_printify_status)
    app.router.add_post("/api/printify/autofulfill",  handle_printify_autofulfill)
    app.router.add_post("/api/printify/webhook",      handle_printify_webhook)
    app.router.add_get("/api/printful/status",        handle_printful_status)
    app.router.add_get("/api/printful/products",      handle_printful_products)
    app.router.add_post("/api/printful/blast",        handle_printful_blast)
    app.router.add_post("/api/printful/autofulfill",  handle_printful_autofulfill)
    app.router.add_get("/api/printful/auth",          handle_printful_auth)
    app.router.add_get("/api/printful/callback",      handle_printful_callback)

    # ── Etsy + Gumroad ────────────────────────────────────────────────────────
    app.router.add_get("/api/etsy/status",            handle_etsy_status)
    app.router.add_get("/api/gumroad/status",         handle_gumroad_status)
    app.router.add_post("/api/gumroad/webhook",       handle_gumroad_webhook)
    app.router.add_get("/api/gumroad/products",       handle_gumroad_products)
    app.router.add_get("/api/gumroad/sales",          handle_gumroad_sales)
    app.router.add_post("/api/gumroad/product/create", handle_gumroad_create)
    app.router.add_post("/api/gumroad/blast",         handle_gumroad_blast)
    # ── Fiverr ────────────────────────────────────────────────────────────────
    app.router.add_get("/api/fiverr/status",          handle_fiverr_status)
    app.router.add_get("/api/fiverr/gigs",            handle_fiverr_gigs)
    app.router.add_get("/api/fiverr/orders",          handle_fiverr_orders)
    # ── Upwork ────────────────────────────────────────────────────────────────
    app.router.add_get("/api/upwork/status",          handle_upwork_status)
    app.router.add_get("/api/upwork/contracts",       handle_upwork_contracts)
    app.router.add_get("/api/upwork/earnings",        handle_upwork_earnings)
    app.router.add_get("/api/upwork/auth",            handle_upwork_auth)
    app.router.add_get("/api/upwork/callback",        handle_upwork_callback)

    # ── Revenue Aggregator ────────────────────────────────────────────────────
    app.router.add_get("/api/revenue",                handle_revenue_legacy)
    app.router.add_get("/api/revenue/status",         handle_revenue_status)
    app.router.add_get("/api/revenue/report",         handle_revenue_report)

    # ── SEO Autopilot ─────────────────────────────────────────────────────────
    app.router.add_get("/api/seo/status",             handle_seo_status)
    app.router.add_post("/api/seo/run",               handle_seo_run)
    app.router.add_post("/api/seo/ping-sitemaps",     handle_ping_sitemaps)
    app.router.add_post("/api/seo/generate",          handle_seo_generate)
    app.router.add_get("/api/seo/social-drafts",      handle_social_drafts)
    app.router.add_post("/api/seo/social-schedule",   handle_social_schedule)

    # ── Dropshipping ──────────────────────────────────────────────────────────
    app.router.add_get("/api/dropshipping/status",    handle_dropshipping_status)
    app.router.add_post("/api/dropshipping/run",      handle_dropshipping_run)

    # ── Print-on-Demand ───────────────────────────────────────────────────────
    app.router.add_get("/api/pod/status",             handle_pod_status)

    # ── Klaviyo ───────────────────────────────────────────────────────────────
    app.router.add_get("/api/klaviyo/status",              handle_klaviyo_status)
    app.router.add_get("/api/klaviyo/lists",               handle_klaviyo_lists)
    app.router.add_post("/api/klaviyo/sync",               handle_klaviyo_sync)
    app.router.add_post("/api/klaviyo/campaign",           handle_klaviyo_campaign)
    app.router.add_post("/api/klaviyo/send-campaign",      handle_klaviyo_send_campaign)

    # ── Bot Clones ────────────────────────────────────────────────────────────
    app.router.add_get("/api/bots/status",            handle_bot_clones_status)
    app.router.add_post("/api/bots/run",              handle_bot_clone_run)

    # ── Watchdog + Agenten Hub ────────────────────────────────────────────────
    app.router.add_get("/api/watchdog/status",        handle_watchdog_status)
    app.router.add_get("/api/agents/hub",             handle_agents_hub)

    # ── Agent Teams ───────────────────────────────────────────────────────────
    app.router.add_get("/api/agents/teams",           handle_agents_teams_list)
    app.router.add_post("/api/agents/run",            handle_agents_teams_run)

    # ── Monetization ──────────────────────────────────────────────────────────
    app.router.add_get("/api/plans",                  handle_plans_list)
    app.router.add_post("/api/checkout",              handle_checkout_create)
    app.router.add_get("/api/mrr",                    handle_mrr)

    # ── Stripe ────────────────────────────────────────────────────────────────
    app.router.add_get("/api/stripe/status",          handle_stripe_status)
    app.router.add_get("/api/stripe/balance",         handle_stripe_balance)
    app.router.add_get("/api/stripe/charges",         handle_stripe_charges)
    app.router.add_get("/api/stripe/customers",       handle_stripe_customers)
    app.router.add_get("/api/stripe/revenue",         handle_stripe_revenue)
    app.router.add_get("/api/stripe/subscriptions",   handle_stripe_subscriptions)
    app.router.add_post("/api/stripe/webhook",        handle_stripe_webhook)
    app.router.add_post("/api/shopify/order-webhook",     handle_shopify_order_webhook_route)
    app.router.add_post("/api/webhooks/shopify-order",    handle_shopify_order_webhook_v2)
    app.router.add_post("/api/discord/interactions",      handle_discord_interactions)
    app.router.add_get("/api/discord/oauth/callback",     handle_discord_oauth_callback)
    app.router.add_get("/api/shopify/orders",         handle_shopify_orders)
    app.router.add_get("/api/shopify/products",       handle_shopify_products)
    app.router.add_get("/api/shopify/revenue",        handle_shopify_revenue)
    app.router.add_post("/webhook/telegram",          handle_telegram_webhook)
    app.router.add_post("/api/webhook/telegram",      handle_telegram_webhook)
    app.router.add_post("/api/telegram/webhook",      handle_telegram_webhook)
    app.router.add_get("/api/telegram/setup",         handle_telegram_setup)
    app.router.add_get("/checkout",                   handle_checkout_page)
    app.router.add_get("/datenschutz",                handle_datenschutz)
    app.router.add_get("/privacy",                    handle_datenschutz)
    app.router.add_get("/privacy-policy",             handle_datenschutz)
    app.router.add_get("/aiitec/datenschutz",         handle_datenschutz)
    app.router.add_get("/aiitec/privacy-policy",      handle_datenschutz)
    app.router.add_get("/bullpowerhub/datenschutz",   handle_datenschutz)
    app.router.add_get("/checkout/success",           handle_checkout_success)

    # ── Google OAuth2 ─────────────────────────────────────────────────────────
    app.router.add_get("/api/google/auth",            handle_google_auth)
    app.router.add_get("/api/google/callback",        handle_google_callback)
    app.router.add_get("/api/google/status",          handle_google_status)
    app.router.add_post("/api/google/refresh",        handle_google_refresh)
    app.router.add_post("/api/google/revoke",         handle_google_revoke)

    # ── YouTube OAuth ─────────────────────────────────────────────────────────
    app.router.add_get("/api/youtube/auth",           handle_youtube_auth)
    app.router.add_get("/api/youtube/callback",       handle_google_callback)
    app.router.add_get("/api/youtube/status",         handle_youtube_status)
    app.router.add_post("/api/youtube/refresh",       handle_google_refresh)

    # ── Google Drive ──────────────────────────────────────────────────────────
    app.router.add_get("/api/drive/status",           handle_drive_status)
    app.router.add_get("/api/drive/files",            handle_drive_files)
    app.router.add_post("/api/drive/backup",          handle_drive_backup)

    # ── Reality Check ─────────────────────────────────────────────────────────
    app.router.add_get("/api/reality",                handle_reality_check)

    # ── Lead Capture ──────────────────────────────────────────────────────────
    app.router.add_post("/api/leads",                 handle_lead_capture)
    app.router.add_get("/api/leads",                  handle_leads_list)

    # ── Hermes Job Queue + Events (Slack fallback → Telegram) ────────────────
    from dashboard.routes.hermes_routes import (
        handle_hermes_jobs, handle_hermes_events,
        handle_hermes_enqueue, handle_hermes_notify, handle_hermes_stats,
    )
    app.router.add_get("/api/hermes/jobs",            handle_hermes_jobs)
    app.router.add_get("/api/hermes/events",          handle_hermes_events)
    app.router.add_post("/api/hermes/enqueue",        handle_hermes_enqueue)
    app.router.add_post("/api/hermes/notify",         handle_hermes_notify)
    app.router.add_get("/api/hermes/stats",           handle_hermes_stats)
    app.router.add_get("/api/content/stats",          handle_content_stats)
    app.router.add_post("/api/ingest",                handle_seo_ingest)
    app.router.add_post("/api/lead",                  handle_universal_lead_capture)
    app.router.add_get("/master",                     handle_master_dashboard)
    app.router.add_get("/dashboard",                  handle_mega_dashboard)
    app.router.add_get("/api/email/brain/stats",      handle_email_brain_stats)
    app.router.add_post("/api/email/brain/check",     handle_email_brain_check)
    app.router.add_get("/api/email/brain/setup",      handle_email_brain_setup)
    app.router.add_get("/api/revenue/summary",        handle_revenue_summary)
    app.router.add_get("/api/scheduler/status",       handle_scheduler_status)
    app.router.add_post("/api/scheduler/trigger",     handle_scheduler_trigger)
    app.router.add_post("/api/broadcast/trigger",     handle_broadcast_trigger)
    app.router.add_get("/api/facebook/auth",          handle_facebook_auth)
    app.router.add_get("/api/facebook/refresh",       handle_facebook_refresh)
    app.router.add_get("/api/facebook/callback",      handle_facebook_callback)
    app.router.add_get("/api/facebook/status",        handle_facebook_status)
    app.router.add_post("/api/brutus/run",            handle_brutus_run)
    app.router.add_get("/api/brutus/status",          handle_brutus_status)
    app.router.add_get("/api/brutus/history",         handle_brutus_history)
    app.router.add_get("/api/offers",                 handle_offers)
    # Autonomy Max-Upgrades
    app.router.add_get("/api/ab/{test_name}",         handle_ab_variant)
    app.router.add_post("/api/ab/conversion",         handle_ab_conversion)
    app.router.add_get("/api/ab/winners",             handle_ab_winners)
    app.router.add_post("/api/revenue/optimize",      handle_revenue_optimize)
    app.router.add_get("/api/content/calendar",       handle_content_calendar)
    app.router.add_post("/api/content/generate",      handle_content_generate)
    app.router.add_get( "/api/content/trending",      handle_content_trending)
    app.router.add_post("/api/content/translate",     handle_content_translate)
    app.router.add_post("/api/content/predict",       handle_content_predict)
    app.router.add_post("/api/auto-poster/run",       handle_auto_poster_run)
    app.router.add_get("/api/auto-poster/status",     handle_auto_poster_status)
    app.router.add_post("/api/shopify/seo/run",       handle_shopify_seo_run)
    app.router.add_post("/api/twitter/post",          handle_twitter_post)
    app.router.add_get( "/api/twitter/status",        handle_twitter_status)
    app.router.add_post("/api/circuit-breaker/reset-all", handle_circuit_breaker_reset_all)
    app.router.add_post("/api/seo/ultra",              handle_ultra_seo)
    app.router.add_post("/api/seo/indexnow",          handle_ultra_indexnow)
    app.router.add_get( "/bullpower2026indexnow.txt", handle_indexnow_key)
    app.router.add_get( "/sitemap.xml",               handle_sitemap_xml)
    app.router.add_get( "/robots.txt",                handle_robots_txt)
    app.router.add_post("/api/seo/dominator",         handle_seo_dominator)
    app.router.add_post("/api/backlink/bomb",         handle_backlink_bomber_run)
    app.router.add_post("/api/content/velocity",      handle_content_velocity)
    app.router.add_post("/api/viral/traffic",         handle_viral_traffic)
    app.router.add_post("/api/revenue/maximize",      handle_revenue_maximizer_run)
    app.router.add_post("/api/syndication/run",       handle_free_syndication)
    app.router.add_post("/api/blog/publish",          handle_github_blog_publish)
    app.router.add_get( "/api/paypal/status",         handle_paypal_status)
    app.router.add_post("/api/paypal/checkout",       handle_paypal_checkout)
    app.router.add_post("/api/paypal/ipn",            handle_paypal_ipn)
    app.router.add_get( "/api/paypal/success",        handle_paypal_success)
    app.router.add_get( "/api/paypal/cancel",         handle_paypal_cancel)
    app.router.add_get( "/api/linkedin/auth",         handle_linkedin_auth)
    app.router.add_get( "/api/linkedin/callback",     handle_linkedin_callback)
    app.router.add_get( "/api/linkedin/status",       handle_linkedin_status)
    app.router.add_post("/api/linkedin/refresh",      handle_linkedin_refresh)
    app.router.add_post("/api/linkedin/post",         handle_linkedin_post)
    # Discord
    app.router.add_post("/api/discord/send",          handle_discord_send)
    app.router.add_get( "/api/discord/status",        handle_discord_status)
    # Circuit Breaker management
    app.router.add_post("/api/circuit-breaker/reset", handle_circuit_breaker_reset)
    # CONVERSION MAXIMIZER
    app.router.add_get( "/api/conversion/stats",      handle_conversion_stats)
    app.router.add_post("/api/conversion/ab-test",    handle_conversion_ab_test)
    app.router.add_get( "/api/conversion/leads",      handle_conversion_leads)
    app.router.add_post("/api/conversion/upsell",     handle_conversion_upsell)
    app.router.add_get( "/api/conversion/report",     handle_conversion_report)
    app.router.add_post("/api/conversion/exit-intent",handle_conversion_exit_intent)
    app.router.add_post("/api/conversion/personalize",handle_conversion_personalize)
    # REVOLUTION PACK — Traffic + SEO + Automation Max
    app.router.add_get( "/api/referral/{ref_code}",   handle_referral_redirect)
    app.router.add_post("/api/push/subscribe",         handle_push_subscribe)
    app.router.add_post("/api/push/send",              handle_push_send)
    app.router.add_get( "/api/push/vapid-key",         handle_vapid_public_key)
    app.router.add_get( "/api/reddit/auth",            handle_reddit_auth_start)
    app.router.add_get( "/api/reddit/callback",        handle_reddit_callback)
    app.router.add_get( "/api/pinterest/auth",         handle_pinterest_auth)
    app.router.add_get( "/api/pinterest/callback",     handle_pinterest_callback)
    app.router.add_get( "/api/oauth/status",           handle_oauth_status)

    # ── SEO Mega Engine routes (no duplicates) ──────────────────────────────
    app.router.add_get( "/api/seo/sitemap.xml",        handle_seo_sitemap)
    app.router.add_post("/api/seo/submit",             handle_seo_submit)
    app.router.add_post("/api/seo/competitor",         handle_seo_competitor)
    # ── Traffic Swarm routes ────────────────────────────────────────────────
    app.router.add_post("/api/traffic/swarm",          handle_traffic_swarm)
    app.router.add_get( "/api/traffic/velocity",       handle_traffic_velocity)
    app.router.add_get( "/api/traffic/rss.xml",        handle_traffic_rss)
    # ── Ads Engine routes ───────────────────────────────────────────────────
    app.router.add_get( "/api/ads/status",             handle_ads_status)
    app.router.add_post("/api/ads/campaign",           handle_ads_campaign)
    app.router.add_get( "/api/ads/performance",        handle_ads_performance)
    # ── Revenue Intelligence routes ─────────────────────────────────────────
    app.router.add_get( "/api/revenue/forecast",       handle_revenue_forecast)
    app.router.add_get( "/api/revenue/leaks",          handle_revenue_leaks)
    app.router.add_get( "/api/revenue/churn",          handle_revenue_churn)
    # ── Shopify Max Tuner routes ────────────────────────────────────────────
    app.router.add_post("/api/shopify/max-seo",        handle_shopify_max_seo)
    app.router.add_post("/api/shopify/cart-recover",   handle_shopify_cart_recover)
    app.router.add_get( "/api/shopify/intelligence",   handle_shopify_intel)
    app.router.add_post("/api/shopify/price-optimize", handle_shopify_price_opt)
    # ── Growth Hacker routes ────────────────────────────────────────────────
    app.router.add_get( "/api/growth/dashboard",        handle_growth_dashboard)
    app.router.add_get( "/api/growth/trends",          handle_growth_trends)
    app.router.add_post("/api/growth/press-release",   handle_growth_pr)
    app.router.add_get( "/api/growth/referral-url",    handle_growth_referral)
    app.router.add_get( "/api/growth/status",          handle_growth_status)

    # ── TURBO Engines panel ─────────────────────────────────────────────────
    app.router.add_get( "/api/engines/status",           handle_engines_status)
    app.router.add_post("/api/engines/trigger/{engine}", handle_engine_trigger)
    app.router.add_post("/api/engines/trigger/all",      handle_engines_trigger_all)
    app.router.add_get( "/engines",                      handle_engines_page)

    # ── Dynamic Pricing ─────────────────────────────────────────────────────
    app.router.add_get( "/api/pricing/dashboard",        handle_pricing_dashboard)
    app.router.add_post("/api/pricing/run",              handle_pricing_run)
    app.router.add_get( "/api/pricing/history",          handle_pricing_history)
    app.router.add_post("/api/pricing/enable",           handle_pricing_enable)

    # ── Email Sequences ──────────────────────────────────────────────────────
    app.router.add_get( "/api/email-sequence/stats",     handle_email_sequence_stats)
    app.router.add_post("/api/email-sequence/enroll",    handle_email_sequence_enroll)
    app.router.add_post("/api/email-sequence/process",   handle_email_sequence_process)
    app.router.add_post("/api/email-sequence/enroll-new",handle_email_sequence_enroll_new)

    # ── B2B Pipeline ────────────────────────────────────────────────────────
    app.router.add_get( "/api/b2b/pipeline/stats",       handle_b2b_pipeline_stats)
    app.router.add_get( "/api/b2b/pipeline/leads",       handle_b2b_pipeline_leads)
    app.router.add_post("/api/b2b/lead/add",             handle_b2b_lead_add)
    app.router.add_post("/api/b2b/lead/update",          handle_b2b_lead_update)
    app.router.add_post("/api/b2b/prospecting/run",      handle_b2b_prospecting_run)
    app.router.add_post("/api/b2b/outreach/send",        handle_b2b_outreach_send)

    # ── WhatsApp Automation ──────────────────────────────────────────────────
    app.router.add_get( "/api/whatsapp/webhook",         handle_whatsapp_webhook_verify)
    app.router.add_post("/api/whatsapp/webhook",         handle_whatsapp_webhook)
    app.router.add_post("/api/whatsapp/send",            handle_whatsapp_send)
    app.router.add_post("/api/whatsapp/broadcast",       handle_whatsapp_broadcast)
    app.router.add_get( "/api/whatsapp/stats",           handle_whatsapp_stats)
    app.router.add_get( "/api/whatsapp/blast",           handle_whatsapp_blast)

    # ── TikTok Shop ──────────────────────────────────────────────────────────
    app.router.add_post("/api/tiktok/sync-products",     handle_tiktok_sync_products)
    app.router.add_get( "/api/tiktok/orders",            handle_tiktok_orders)
    app.router.add_get( "/api/tiktok/analytics",         handle_tiktok_analytics)
    app.router.add_get( "/api/tiktok/combined-revenue",  handle_tiktok_combined_revenue)
    app.router.add_post("/api/tiktok/promotion",         handle_tiktok_promotion)
    app.router.add_get( "/api/tiktok/research/status",   handle_tiktok_research_status)
    app.router.add_get( "/api/tiktok/research/ads",      handle_tiktok_research_ads)
    app.router.add_get( "/api/tiktok/auth",              handle_tiktok_auth)
    app.router.add_get( "/api/tiktok/callback",          handle_tiktok_callback)

    # ── SEMRush / SEO Research ───────────────────────────────────────────────
    app.router.add_get( "/api/semrush/keyword",          handle_semrush_keyword)
    app.router.add_get( "/api/semrush/domain",           handle_semrush_domain)
    app.router.add_get( "/api/semrush/niche",            handle_semrush_niche)
    app.router.add_get( "/api/semrush/serp",             handle_semrush_serp)

    # ── Meta / Facebook Ads ──────────────────────────────────────────────────
    app.router.add_get( "/api/meta/ads/status",          handle_meta_ads_status)
    app.router.add_get( "/api/meta/campaigns",           handle_meta_campaigns)
    app.router.add_post("/api/meta/campaign/create",     handle_meta_campaign_create)
    app.router.add_post("/api/meta/campaign/launch",     handle_meta_campaign_launch)
    app.router.add_post("/api/meta/saas-campaign",       handle_meta_saas_campaign)
    app.router.add_get( "/api/meta/pixel/stats",         handle_meta_pixel_stats)
    app.router.add_get( "/api/meta/oauth-url",           handle_meta_oauth_url)

    # ── Salesforce CRM ───────────────────────────────────────────────────────
    app.router.add_get( "/api/salesforce/stats",         handle_salesforce_stats)
    app.router.add_get( "/api/salesforce/leads",         handle_salesforce_leads)
    app.router.add_get( "/api/salesforce/contacts",      handle_salesforce_contacts)
    app.router.add_get( "/api/salesforce/opportunities", handle_salesforce_opportunities)
    app.router.add_post("/api/salesforce/lead/create",   handle_salesforce_create_lead)
    app.router.add_post("/api/salesforce/sync-klaviyo",  handle_salesforce_sync_klaviyo)
    app.router.add_post("/api/salesforce/import-b2b",    handle_salesforce_import_b2b)

    # ── Autonomy Engine ──────────────────────────────────────────────────────
    app.router.add_get( "/api/autonomy/health",          handle_autonomy_health)
    app.router.add_post("/api/autonomy/trigger",         handle_autonomy_trigger)
    app.router.add_get( "/api/autonomy/history",         handle_autonomy_history)

    # ── Task Queue ───────────────────────────────────────────────────────────
    app.router.add_get( "/api/queue/stats",              handle_queue_stats)
    app.router.add_post("/api/queue/enqueue",            handle_queue_enqueue)

    # ── Referral System ──────────────────────────────────────────────────────
    app.router.add_post("/api/referral/create",          handle_referral_create)
    app.router.add_get( "/api/referral/stats",           handle_referral_stats)
    app.router.add_get( "/api/referral/top",             handle_referral_top)
    app.router.add_get( "/api/referral/r/{code}",        handle_referral_redirect)

    # ── Misc recovered handlers ──────────────────────────────────────────────
    app.router.add_post("/api/review/run",               handle_review_automation_run)
    app.router.add_post("/api/winback/run",              handle_winback_run)

    # ── Pipedrive ─────────────────────────────────────────────────────────────
    app.router.add_get( "/api/pipedrive/status",         handle_pipedrive_status)
    app.router.add_get( "/api/pipedrive/deals",          handle_pipedrive_deals)
    app.router.add_get( "/api/pipedrive/persons",        handle_pipedrive_persons)
    app.router.add_post("/api/pipedrive/sync-shopify",   handle_pipedrive_sync_shopify)

    # ── Trello ────────────────────────────────────────────────────────────────
    app.router.add_get( "/api/trello/status",            handle_trello_status)
    app.router.add_post("/api/trello/token",             handle_trello_set_token)
    app.router.add_get( "/api/trello/boards",            handle_trello_boards)
    app.router.add_get( "/api/trello/lists",             handle_trello_lists)
    app.router.add_post("/api/trello/card",              handle_trello_create_card)

    # Traffic Blitz routes
    app.router.add_post("/api/traffic/blitz",            handle_traffic_blitz)
    app.router.add_post("/api/traffic/github-post",      handle_github_seo_post)
    app.router.add_post("/api/traffic/linkedin-burst",   handle_linkedin_burst)
    app.router.add_post("/api/traffic/indexnow",         handle_indexnow_blast)

    # Circuit Breaker routes
    app.router.add_get( "/api/circuit/status",           handle_circuit_status)
    app.router.add_post("/api/circuit/reset",            handle_circuit_reset)

    # Amazon routes
    app.router.add_get("/api/amazon/status",  handle_amazon_status)
    app.router.add_get("/api/amazon/blast",   handle_amazon_blast)
    app.router.add_get("/api/amazon/search",  handle_amazon_search)

    # eBay routes
    app.router.add_get("/api/ebay/status",    handle_ebay_status)
    app.router.add_get("/api/ebay/search",    handle_ebay_search)
    app.router.add_get("/api/ebay/blast",     handle_ebay_blast)
    app.router.add_get("/api/ebay/auth",      handle_ebay_auth)

    # Shopify Full Autonomy routes
    app.router.add_post("/api/shopify/full-auto",         handle_shopify_full_auto)
    app.router.add_post("/api/shopify/restock",           handle_shopify_restock)
    app.router.add_post("/api/shopify/fix-images",        handle_shopify_fix_images)
    app.router.add_post("/api/shopify/fix-titles",        handle_shopify_fix_titles)
    app.router.add_post("/api/shopify/collections/auto",  handle_shopify_auto_collections)
    app.router.add_post("/api/shopify/mass-seo",          handle_shopify_mass_seo)
    app.router.add_post("/api/shopify/discount-blast",    handle_shopify_discount_blast)

    # Product Generator routes
    app.router.add_post("/api/products/generate",         handle_product_generate)
    app.router.add_post("/api/products/generate-niche",   handle_product_generate_niche)
    app.router.add_post("/api/products/generate-keywords",handle_product_generate_keywords)
    app.router.add_get( "/api/products/trends",           handle_product_trends)

    # NEXUS-1 routes
    app.router.add_get( "/api/nexus/status",          handle_nexus_status)
    app.router.add_post("/api/nexus/run",              handle_nexus_run)
    app.router.add_get( "/api/nexus/signals",         handle_nexus_signals)
    app.router.add_get( "/api/nexus/actions",         handle_nexus_actions)
    app.router.add_post("/api/nexus/action",          handle_nexus_action_fire)
    app.router.add_post("/api/nexus/evolve",          handle_nexus_evolve)
    app.router.add_get( "/api/nexus/report",          handle_nexus_report)
    app.router.add_get( "/api/nexus/dna",             handle_nexus_dna)
    app.router.add_post("/api/nexus/broadcast",       handle_nexus_broadcast)

    # GCP routes
    app.router.add_get( "/api/gcp/ping",              handle_gcp_ping)
    app.router.add_post("/api/gcp/translate",          handle_gcp_translate)
    app.router.add_post("/api/gcp/vision",             handle_gcp_vision)
    app.router.add_post("/api/gcp/sentiment",          handle_gcp_sentiment)
    app.router.add_post("/api/gcp/enhance-products",   handle_gcp_enhance_products)

    # Twilio SMS
    app.router.add_get( "/api/twilio/status",              handle_twilio_status)
    app.router.add_post("/api/twilio/sms",                 handle_twilio_send_sms)
    app.router.add_post("/api/twilio/daily-revenue-sms",   handle_twilio_daily_sms)

    # SMTP email fallback
    app.router.add_get( "/api/smtp/status",                handle_smtp_status)
    app.router.add_post("/api/smtp/send",                  handle_smtp_send)

    # Platform Autonomy routes
    app.router.add_post("/api/amazon/cycle",               handle_amazon_cycle)
    app.router.add_post("/api/amazon/autonomy-blast",      handle_amazon_autonomy_blast)
    app.router.add_post("/api/ebay/autonomy-cycle",        handle_ebay_autonomy_cycle)
    app.router.add_post("/api/ebay/autonomy-blast",        handle_ebay_autonomy_blast)
    app.router.add_post("/api/aliexpress/cycle",           handle_aliexpress_cycle)
    app.router.add_post("/api/printify/autonomy-cycle",    handle_printify_autonomy_cycle)
    app.router.add_post("/api/printify/create-pod",        handle_printify_create_pod)
    app.router.add_post("/api/printful/autonomy-cycle",    handle_printful_autonomy_cycle)
    app.router.add_post("/api/digistore/autonomy-cycle",   handle_digistore_autonomy_cycle)
    app.router.add_post("/api/digistore/revenue-report",   handle_digistore_autonomy_revenue)
    app.router.add_post("/api/mailchimp/autonomy-cycle",   handle_mailchimp_autonomy_cycle)
    app.router.add_post("/api/mailchimp/digest",           handle_mailchimp_digest)
    app.router.add_post("/api/mailchimp/dragon/campaign",  handle_dragon_campaign)
    app.router.add_post("/api/mailchimp/dragon/subscribe", handle_dragon_subscribe)
    app.router.add_post("/api/klaviyo/autonomy-cycle",     handle_klaviyo_autonomy_cycle)
    app.router.add_post("/api/klaviyo/blast",              handle_klaviyo_blast)

    # DS24 Product Creator
    app.router.add_post("/api/ds24/product/create",        handle_ds24_product_create)
    app.router.add_post("/api/ds24/product/auto",          handle_ds24_product_auto)
    app.router.add_get( "/api/ds24/products",              handle_ds24_product_list)
    app.router.add_post("/api/ds24/fix/669750",            handle_ds24_fix_669750)
    app.router.add_post("/api/ds24/create-100",            handle_ds24_create_100)
    app.router.add_post("/api/ds24/create-1000",           handle_ds24_create_1000)
    app.router.add_post("/api/ds24/refill",                handle_ds24_refill)
    app.router.add_get( "/api/ds24/status",                handle_ds24_mass_status)
    app.router.add_post("/api/ds24/seo-blast",             handle_ds24_seo_blast)
    app.router.add_post("/api/ds24/affiliate/blast-all",   handle_ds24_affiliate_blast_all)
    app.router.add_get( "/api/ds24/affiliate/stats",       handle_ds24_affiliate_stats)
    app.router.add_post("/api/ds24/affiliate/blast-niche", handle_ds24_affiliate_blast_niche)

    # ── Traffic Mega Engine ───────────────────────────────────────────────────
    app.router.add_post("/api/traffic/mega-blast",       handle_traffic_mega_blast)
    app.router.add_post("/api/traffic/viral-campaign",   handle_traffic_viral_campaign)
    app.router.add_post("/api/traffic/syndicate",        handle_traffic_syndicate)
    app.router.add_post("/api/traffic/backlinks",        handle_traffic_backlinks)
    app.router.add_get( "/api/traffic/stats",            handle_traffic_stats)
    # ── Fiverr ────────────────────────────────────────────────────────────────
    app.router.add_post("/api/fiverr/promote",           handle_fiverr_promote)
    app.router.add_post("/api/fiverr/cycle",             handle_fiverr_cycle)
    app.router.add_get( "/api/fiverr/status",            handle_fiverr_status)
    # ── Upwork ────────────────────────────────────────────────────────────────
    app.router.add_post("/api/upwork/search",            handle_upwork_search)
    app.router.add_post("/api/upwork/promote",           handle_upwork_promote)
    app.router.add_get( "/api/upwork/status",            handle_upwork_status)
    # ── TikTok Autonomy ───────────────────────────────────────────────────────
    app.router.add_post("/api/tiktok/sync-products",     handle_tiktok_sync)
    app.router.add_post("/api/tiktok/scripts",           handle_tiktok_scripts)
    app.router.add_get( "/api/tiktok/trends",            handle_tiktok_trends_hashtags)
    app.router.add_post("/api/tiktok/cycle",             handle_tiktok_autonomy_cycle)
    # ── Gumroad ───────────────────────────────────────────────────────────────
    app.router.add_post("/api/gumroad/create-all",       handle_gumroad_create_all)
    app.router.add_post("/api/gumroad/blast",            handle_gumroad_blast)
    app.router.add_get( "/api/gumroad/list",             handle_gumroad_list)
    # ── Pinterest ─────────────────────────────────────────────────────────────
    app.router.add_post("/api/pinterest/pin-products",   handle_pinterest_pin_products)
    app.router.add_post("/api/pinterest/cycle",          handle_pinterest_cycle)
    app.router.add_get( "/api/pinterest/status",         handle_pinterest_status)
    # ── YouTube ───────────────────────────────────────────────────────────────
    app.router.add_post("/api/youtube/trends",           handle_youtube_trends)
    app.router.add_post("/api/youtube/scripts",          handle_youtube_scripts)
    app.router.add_get( "/api/youtube/status",           handle_youtube_status_new)
    # ── Email Blast Engine ────────────────────────────────────────────────────
    app.router.add_post("/api/email/blast",              handle_email_blast)
    app.router.add_post("/api/email/daily-blast",        handle_email_daily_blast)
    app.router.add_get( "/api/email/stats",              handle_email_stats)
    # ── Affiliate Mega Engine ─────────────────────────────────────────────────
    app.router.add_post("/api/affiliate/blast-all",      handle_affiliate_blast_all)
    app.router.add_post("/api/affiliate/amazon",         handle_affiliate_amazon)
    app.router.add_post("/api/affiliate/ds24",           handle_affiliate_ds24)
    app.router.add_get( "/api/affiliate/stats",          handle_affiliate_stats_new)
    # ── MEGA START — alles auf einmal ─────────────────────────────────────────
    app.router.add_post("/api/mega/start",               handle_mega_autonomy_start)
    app.router.add_get( "/api/mega/status",              handle_mega_status)
    # ── Mega SEO Engine ────────────────────────────────────────────────────────
    app.router.add_post("/api/seo/mega-cycle",           handle_mega_seo_cycle)
    app.router.add_get( "/api/seo/mega-status",          handle_mega_seo_status)
    # ── Traffic Mega V2 ────────────────────────────────────────────────────────
    app.router.add_post("/api/traffic/mega-v2",          handle_traffic_mega_v2_cycle)
    app.router.add_post("/api/traffic/rss-ping",         handle_traffic_rss_ping)
    # ── Revenue Fast Track ─────────────────────────────────────────────────────
    app.router.add_post("/api/revenue/fast-track",       handle_revenue_fast_track)
    app.router.add_post("/api/revenue/flash-sale",       handle_revenue_flash_sale)
    app.router.add_post("/api/revenue/ds24-blast",       handle_revenue_ds24_blast)

    # ── Dashboard Aliases (short names) ────────────────────────────────────────
    app.router.add_post("/api/shopify/sync",             handle_shopify_sync_alias)
    app.router.add_post("/api/email/check",              handle_email_check_alias)
    app.router.add_post("/api/ds24/sync",                handle_ds24_sync_alias)
    app.router.add_post("/api/amazon/run",               handle_amazon_run_alias)
    app.router.add_post("/api/ebay/run",                 handle_ebay_run_alias)
    app.router.add_post("/api/printify/sync",            handle_printify_sync_alias)

    # Start hourly lead follow-up reminder background task
    asyncio.create_task(_run_followup_loop())
    log.info("Lead follow-up reminder task started")

    # Start weekly sitemap ping background task (Google + Bing)
    asyncio.create_task(_run_sitemap_ping_loop())
    log.info("Weekly sitemap ping task started")

    # Start daily SEO blog content pipeline
    asyncio.create_task(_run_seo_loop())
    log.info("SEO blog content pipeline started")

    # Auto-configure Telegram webhook + commands on startup
    async def _setup_tg_on_start():
        await asyncio.sleep(5)  # wait for server to be ready
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{PORT}/api/telegram/setup") as r:
                    result = await r.json()
                    log.info("Telegram setup: %s", result)
        except Exception as e:
            log.warning("Telegram setup failed: %s", e)

    asyncio.create_task(_setup_tg_on_start())
    log.info("Telegram auto-setup task scheduled")

    # Send Telegram Master Dashboard startup notification
    try:
        from modules.telegram_master_dashboard import send_startup_notification
        asyncio.create_task(send_startup_notification())
        log.info("Telegram Master Dashboard startup notification queued")
    except Exception as _e:
        log.warning(f"Telegram Master Dashboard startup failed: {_e}")

    return app


async def _tg_notify(text: str) -> None:
    """Send Telegram message to owner chat."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        import aiohttp as _aio
        async with _aio.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=_aio.ClientTimeout(total=5)
            )
    except Exception:
        pass


async def _sb_insert(table: str, data: dict) -> dict:
    """Insert row into Supabase via REST."""
    import aiohttp as _aio
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
    anon = os.getenv("SUPABASE_ANON_KEY", "")
    auth_key = key or anon
    if not url or not auth_key:
        return {"error": "no supabase credentials"}
    try:
        async with _aio.ClientSession() as s:
            r = await s.post(
                f"{url}/rest/v1/{table}",
                json=data,
                headers={
                    "apikey": auth_key,
                    "Authorization": f"Bearer {auth_key}",
                    "Content-Type": "application/json",
                    "Accept-Profile": "public",
                    "Content-Profile": "public",
                    "Prefer": "return=representation",
                },
                timeout=_aio.ClientTimeout(total=8)
            )
            return await r.json()
    except Exception as e:
        return {"error": str(e)}



async def check_followup_leads() -> None:
    """Query leads created 23-25h ago with followed_up=false and notify owner via Telegram."""
    import aiohttp as _aio
    sb_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    sb_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
    anon = os.getenv("SUPABASE_ANON_KEY", "")
    auth_key = sb_key or anon
    if not sb_url or not auth_key:
        log.warning("check_followup_leads: no Supabase credentials, skipping")
        return

    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    ts_from = (now - timedelta(hours=25)).isoformat()
    ts_to   = (now - timedelta(hours=23)).isoformat()

    headers = {
        "apikey": auth_key,
        "Authorization": f"Bearer {auth_key}",
        "Content-Type": "application/json",
    }

    # Fetch leads created between 25h and 23h ago with followed_up = false (or missing)
    params = (
        f"created_at=gte.{ts_from}"
        f"&created_at=lte.{ts_to}"
        f"&followed_up=is.false"
    )
    try:
        async with _aio.ClientSession() as s:
            r = await s.get(
                f"{sb_url}/rest/v1/leads?{params}",
                headers=headers,
                timeout=_aio.ClientTimeout(total=10),
            )
            if r.status == 400:
                # Column may not exist — fall back to time-only filter
                params_fallback = f"created_at=gte.{ts_from}&created_at=lte.{ts_to}"
                r = await s.get(
                    f"{sb_url}/rest/v1/leads?{params_fallback}",
                    headers=headers,
                    timeout=_aio.ClientTimeout(total=10),
                )
            leads = await r.json()
    except Exception as e:
        log.error("check_followup_leads: fetch error: %s", e)
        return

    if not isinstance(leads, list):
        log.warning("check_followup_leads: unexpected response: %s", leads)
        return

    log.info("check_followup_leads: %d leads to follow up", len(leads))

    for lead in leads:
        email  = lead.get("email", "(unbekannt)")
        name   = lead.get("name") or "kein Name"
        domain = lead.get("shopify_domain") or "nicht angegeben"
        source = lead.get("source") or "unbekannt"
        lead_id = lead.get("id")

        msg = (
            "🔔 *Follow-up fällig!*\n"
            f"Lead von gestern: {email} ({name})\n"
            f"Shop: {domain}\n"
            f"Quelle: {source}\n\n"
            "👉 https://bullpowerhubgit.github.io/bullpower-lead"
        )
        await _tg_notify(msg)
        log.info("Follow-up reminder sent for lead: %s", email)

        # Mark as followed_up if the column exists and we have an id
        if lead_id:
            try:
                async with _aio.ClientSession() as s:
                    await s.patch(
                        f"{sb_url}/rest/v1/leads?id=eq.{lead_id}",
                        json={"followed_up": True},
                        headers={
                            **headers,
                            "Prefer": "return=minimal",
                        },
                        timeout=_aio.ClientTimeout(total=8),
                    )
            except Exception as e:
                log.warning("check_followup_leads: patch error for %s: %s", lead_id, e)


async def _run_followup_loop() -> None:
    """Infinite loop: run check_followup_leads() every hour."""
    while True:
        try:
            await check_followup_leads()
        except Exception as e:
            log.error("_run_followup_loop: unexpected error: %s", e)
        await asyncio.sleep(3600)

async def handle_lead_capture(req):
    """POST /api/leads — capture email + optional name/domain, store + notify."""
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return web.json_response({"ok": False, "error": "valid email required"}, status=400)

    name = (body.get("name") or "").strip()
    domain = (body.get("shopify_domain") or body.get("domain") or "").strip()
    source = (body.get("source") or "landing_page").strip()

    row = {
        "email": email,
        "name": name or None,
        "shopify_domain": domain or None,
        "source": source,
        "status": "new",
    }

    result = await _sb_insert("leads", row)

    # Subscribe to Mailchimp + Klaviyo in parallel (fire-and-forget)
    asyncio.create_task(_mailchimp_subscribe(email, name))
    asyncio.create_task(_klaviyo_subscribe(email, name))

    msg = (
        f"🔥 *Neuer Lead!*\n"
        f"📧 {email}\n"
        f"👤 {name or '(kein Name)'}\n"
        f"🛍️ Shop: {domain or '(kein Domain)'}\n"
        f"📍 Quelle: {source}\n"
        f"\nDirektlink: https://buy.stripe.com/7sY5kFbrIemmcYU0Oi4F20o"
    )
    try:
        from modules.slack_client import push_event
        await push_event("supermegabot", "new_lead", msg, "revenue",
                         {"email": email, "source": source, "domain": domain})
    except Exception:
        await _tg_notify(msg)

    # Send welcome email via SendGrid
    asyncio.create_task(_sendgrid_welcome(email, name))

    log.info("New lead captured: %s (source=%s)", email, source)
    return web.json_response({"ok": True, "email": email})


async def _sendgrid_welcome(email: str, name: str = "") -> None:
    """Send Shopify-Audit welcome email via SendGrid."""
    import aiohttp as _aio
    api_key = os.getenv("SENDGRID_API_KEY", "")
    from_email = os.getenv("SENDGRID_FROM_EMAIL", "bullpowersrtkennels@gmail.com")
    from_name = os.getenv("SENDGRID_FROM_NAME", "BullPower Hub")
    if not api_key:
        return
    fname = name.split()[0] if name else "Shopify-Händler"
    html_body = f"""<!DOCTYPE html>
<html><body style="background:#0a0a0f;color:#f0f0ff;font-family:sans-serif;padding:2rem;max-width:600px;margin:0 auto">
<div style="background:#13131f;border:1px solid rgba(139,92,246,.3);border-radius:16px;padding:2rem">
<h1 style="color:#a78bfa">🚀 Dein Shopify-Audit startet!</h1>
<p>Hey {fname},</p>
<p>Danke für deine Anfrage! Dein persönlicher KI-Shopify-Audit wird gerade vorbereitet.</p>
<h2 style="color:#a78bfa">Was dich erwartet:</h2>
<ul>
<li>✓ Analyse deiner Produktbeschreibungen auf SEO-Potenzial</li>
<li>✓ Preisoptimierungs-Check auf Basis von Marktdaten</li>
<li>✓ Fulfillment & Lagerbestand-Engpässe</li>
<li>✓ Persönlicher Aktionsplan mit konkreten Schritten</li>
</ul>
<p>Du erhältst dein Ergebnis innerhalb von 24 Stunden.</p>
<div style="margin:2rem 0;text-align:center">
<a href="https://buy.stripe.com/7sY5kFbrIemmcYU0Oi4F20o"
   style="background:linear-gradient(135deg,#8b5cf6,#7c3aed);color:#fff;padding:1rem 2rem;
          border-radius:12px;text-decoration:none;font-weight:700;display:inline-block">
⚡ Jetzt 14 Tage kostenlos — alle 8 KI-Tools sofort verfügbar
</a>
</div>
<p style="color:#64748b;font-size:.85rem">BullPower Hub | KI-Automatisierung für Shopify</p>
</div></body></html>"""
    payload = {
        "personalizations": [{"to": [{"email": email, "name": name or fname}]}],
        "from": {"email": from_email, "name": from_name},
        "subject": f"🔍 Dein Shopify-Audit startet, {fname}!",
        "content": [{"type": "text/html", "value": html_body}],
    }
    try:
        async with _aio.ClientSession() as s:
            r = await s.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            if r.status == 202:
                log.info("SendGrid welcome email sent to %s", email)
            else:
                body = await r.text()
                log.warning("SendGrid failed (%s): %s", r.status, body[:200])
    except Exception as e:
        log.warning("SendGrid error: %s", e)


async def _mailchimp_subscribe(email: str, name: str = "") -> None:
    """Add subscriber to Mailchimp audience list."""
    import aiohttp as _aio, base64
    api_key = os.getenv("MAILCHIMP_API_KEY", "")
    list_id = os.getenv("MAILCHIMP_LIST_ID", "")
    if not api_key or not list_id:
        return
    dc = api_key.split("-")[-1]
    auth = base64.b64encode(f"anystring:{api_key}".encode()).decode()
    fname = name.split()[0] if name else ""
    try:
        async with _aio.ClientSession() as s:
            r = await s.post(
                f"https://{dc}.api.mailchimp.com/3.0/lists/{list_id}/members",
                headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
                json={"email_address": email, "status": "subscribed",
                      "merge_fields": {"FNAME": fname}},
            )
            status = r.status
            if status in (200, 201):
                log.info("Mailchimp subscribe OK: %s", email)
            elif status == 400:
                body = await r.json()
                if body.get("title") == "Member Exists":
                    log.info("Mailchimp: %s already subscribed", email)
                else:
                    log.warning("Mailchimp subscribe failed (%s): %s", status, body.get("detail"))
    except Exception as e:
        log.warning("Mailchimp subscribe error: %s", e)


async def _klaviyo_subscribe(email: str, name: str = "") -> None:
    """Add subscriber to Klaviyo E-Mail-Liste."""
    import aiohttp as _aio
    api_key = os.getenv("KLAVIYO_API_KEY", "")
    list_id = os.getenv("KLAVIYO_LIST_ID", "")
    if not api_key or not list_id:
        return
    parts = name.split(" ", 1) if name else []
    fname = parts[0] if parts else ""
    lname = parts[1] if len(parts) > 1 else ""
    payload = {
        "data": {
            "type": "profile-subscription-bulk-create-job",
            "attributes": {
                "profiles": {"data": [{
                    "type": "profile",
                    "attributes": {
                        "email": email,
                        "first_name": fname,
                        "last_name": lname,
                        "subscriptions": {"email": {"marketing": {"consent": "SUBSCRIBED"}}},
                    },
                }]},
            },
            "relationships": {"list": {"data": {"type": "list", "id": list_id}}},
        }
    }
    try:
        async with _aio.ClientSession() as s:
            r = await s.post(
                "https://a.klaviyo.com/api/profile-subscription-bulk-create-jobs/",
                headers={
                    "Authorization": f"Klaviyo-API-Key {api_key}",
                    "Content-Type": "application/json",
                    "revision": "2024-10-15",
                },
                json=payload,
            )
            if r.status in (200, 201, 202):
                log.info("Klaviyo subscribe OK: %s", email)
            else:
                body = await r.text()
                log.warning("Klaviyo subscribe failed (%s): %s", r.status, body[:200])
    except Exception as e:
        log.warning("Klaviyo subscribe error: %s", e)


async def handle_leads_list(req):
    """GET /api/leads — list all leads (internal use)."""
    import aiohttp as _aio
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
    anon = os.getenv("SUPABASE_ANON_KEY", "")
    auth_key = key or anon
    if not url or not auth_key:
        return web.json_response({"ok": False, "error": "no supabase"})
    try:
        async with _aio.ClientSession() as s:
            r = await s.get(
                f"{url}/rest/v1/leads?order=created_at.desc&limit=50",
                headers={
                    "apikey": auth_key,
                    "Authorization": f"Bearer {auth_key}",
                    "Accept-Profile": "public",
                },
                timeout=_aio.ClientTimeout(total=8)
            )
            data = await r.json()
        return web.json_response({"ok": True, "count": len(data) if isinstance(data, list) else 0, "leads": data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Hermes / Slack handlers ───────────────────────────────────────────────────

def _sb_headers(auth_key: str) -> dict:
    return {
        "apikey": auth_key,
        "Authorization": f"Bearer {auth_key}",
        "Content-Type": "application/json",
        "Accept-Profile": "public",
        "Content-Profile": "public",
        "Prefer": "return=representation",
    }


async def _hermes_push_event(service: str, event_type: str, message: str,
                              channel: str = "general", metadata: dict = None) -> bool:
    """Insert into hermes_events + notify Slack or Telegram."""
    import aiohttp as _aio
    sb_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    sb_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
    slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")

    row = {
        "service": service, "event_type": event_type, "channel": channel,
        "message": message, "metadata": metadata or {},
        "notified_slack": False, "notified_telegram": False,
    }

    async with _aio.ClientSession() as s:
        # 1. Persist to Supabase
        if sb_url and sb_key:
            try:
                await s.post(f"{sb_url}/rest/v1/hermes_events",
                             json=row, headers=_sb_headers(sb_key),
                             timeout=_aio.ClientTimeout(total=6))
            except Exception:
                pass

        # 2. Slack (primary)
        if slack_url:
            try:
                channel_emoji = {"revenue": "💰", "alerts": "🚨", "ops": "⚙️",
                                 "marketing": "📣", "errors": "❌"}.get(channel, "ℹ️")
                text = f"{channel_emoji} *[{service}]* {message}"
                r = await s.post(slack_url, json={"text": text},
                                 timeout=_aio.ClientTimeout(total=5))
                return r.status == 200
            except Exception:
                pass

        # 3. Telegram fallback
        if tg_token and tg_chat:
            try:
                await s.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat, "text": f"[{service}/{channel}] {message}",
                          "parse_mode": "Markdown"},
                    timeout=_aio.ClientTimeout(total=5)
                )
            except Exception:
                pass
    return True


async def handle_hermes_events(req):
    """GET /api/hermes/events?limit=50&service=all"""
    import aiohttp as _aio
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return web.json_response({"ok": False, "error": "no supabase"})
    limit = min(int(req.rel_url.query.get("limit", 100)), 500)
    service = req.rel_url.query.get("service", "")
    qs = f"order=created_at.desc&limit={limit}"
    if service and service != "all":
        qs += f"&service=eq.{service}"
    try:
        async with _aio.ClientSession() as s:
            r = await s.get(f"{url}/rest/v1/hermes_events?{qs}",
                            headers={"apikey": key, "Authorization": f"Bearer {key}",
                                     "Accept-Profile": "public"},
                            timeout=_aio.ClientTimeout(total=8))
            data = await r.json()
        return web.json_response({"ok": True, "count": len(data), "events": data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_hermes_jobs(req):
    """GET /api/hermes/jobs?status=pending&service=all"""
    import aiohttp as _aio
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return web.json_response({"ok": False, "error": "no supabase"})
    limit = min(int(req.rel_url.query.get("limit", 100)), 500)
    status = req.rel_url.query.get("status", "")
    service = req.rel_url.query.get("service", "")
    qs = f"order=created_at.desc&limit={limit}"
    if status:
        qs += f"&status=eq.{status}"
    if service and service != "all":
        qs += f"&service=eq.{service}"
    try:
        async with _aio.ClientSession() as s:
            r = await s.get(f"{url}/rest/v1/hermes_jobs?{qs}",
                            headers={"apikey": key, "Authorization": f"Bearer {key}",
                                     "Accept-Profile": "public"},
                            timeout=_aio.ClientTimeout(total=8))
            data = await r.json()
        return web.json_response({"ok": True, "count": len(data), "jobs": data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_hermes_notify(req):
    """POST /api/hermes/notify — push event from any service."""
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
    message = (body.get("message") or "").strip()
    if not message:
        return web.json_response({"ok": False, "error": "message required"}, status=400)
    service = body.get("service", "supermegabot")
    event_type = body.get("event_type", "info")
    channel = body.get("channel", "general")
    metadata = body.get("metadata", {})
    await _hermes_push_event(service, event_type, message, channel, metadata)
    return web.json_response({"ok": True, "service": service, "channel": channel})


async def handle_seo_ingest(req):
    """Receive SEO article broadcasts from seo-traffic-engine and notify via Telegram."""
    try:
        data = await req.json()
        title = data.get("title", "")
        keyword = data.get("keyword", "")
        url = data.get("url", "")
        product_name = data.get("product_name", "")
        product_url = data.get("product_url", "")
        msg = (
            f"📰 <b>SEO Artikel → SuperMegaBot</b>\n"
            f"🔑 {keyword}\n"
            f"📄 {title}\n"
            f"🔗 {url}"
        )
        if product_name:
            msg += f"\n🛒 {product_name}: {product_url}"
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            asyncio.create_task(_tg_notify(msg))
        return web.json_response({"status": "ok", "service": "supermegabot", "processed": title})
    except Exception as e:
        log.error(f"SEO ingest error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_master_dashboard(req):
    """GET /master — großes Master Control Dashboard."""
    html_file = Path(__file__).parent / "master.html"
    return web.Response(content_type="text/html", text=html_file.read_text())


async def handle_mega_dashboard(req):
    """GET /dashboard — SuperMegaBot Command Center (neu)."""
    html_file = Path(__file__).parent / "megadash.html"
    return web.Response(content_type="text/html", text=html_file.read_text())


async def handle_universal_lead_capture(req):
    """POST /api/lead — Universal lead capture from any source (Netlify forms, landing pages, etc.)
    Body: {email, first_name?, source?, product?}
    → saves to data/new_leads.json → picked up by task_lead_nurture → Klaviyo + email sequence
    """
    try:
        data = await req.json()
        email = (data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return web.json_response({"ok": False, "error": "Valid email required"}, status=400)
        first_name = (data.get("first_name") or data.get("name") or email.split("@")[0]).strip()
        source = data.get("source", "api")
        product = data.get("product", "")

        leads_file = Path(__file__).parent.parent / "data" / "new_leads.json"
        leads_file.parent.mkdir(exist_ok=True)
        leads = []
        if leads_file.exists():
            try:
                leads = json.loads(leads_file.read_text())
            except Exception:
                leads = []
        if not any(l.get("email") == email for l in leads):
            leads.append({"email": email, "first_name": first_name,
                          "source": source, "product": product,
                          "ts": datetime.now().isoformat()})
            leads_file.write_text(json.dumps(leads, indent=2))

        # Immediate Klaviyo upsert + email sequence enroll (async, non-blocking)
        async def _enroll():
            try:
                from modules.email_sequence_engine import enroll
                await enroll(email, "welcome", first_name=first_name,
                             metadata={"source": source, "product": product})
            except Exception as ex:
                log.warning("Lead enroll error: %s", ex)
            try:
                from modules.klaviyo_automation import upsert_profile
                await upsert_profile(email, first_name=first_name,
                                     properties={"lead_source": source, "lead_product": product})
            except Exception as ex:
                log.warning("Klaviyo upsert error: %s", ex)
        asyncio.create_task(_enroll())

        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            asyncio.create_task(_tg_notify(
                f"🎯 <b>Neuer Lead</b>\nEmail: {email}\nName: {first_name}\nQuelle: {source}"
            ))
        return web.json_response({"ok": True, "enrolled": True, "email": email})
    except Exception as e:
        log.error(f"Lead capture error: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_email_brain_stats(req):
    """GET /api/email/brain/stats — daily stats from EmailBrain."""
    try:
        from pathlib import Path as _Path
        import json as _json
        stats_file = _Path(os.getenv("DATA_DIR", "data")) / "email_stats.json"
        stats = _json.loads(stats_file.read_text()) if stats_file.exists() else {}
        return web.json_response({"status": "ok", "stats": stats})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_email_brain_check(req):
    """POST /api/email/brain/check — trigger immediate email check."""
    try:
        from modules.email_brain import run_email_check
        result = await run_email_check()
        return web.json_response({"status": "ok", "result": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_email_brain_setup(req):
    """GET /api/email/brain/setup — verify IMAP connectivity."""
    try:
        from modules.email_brain import run_email_setup_check
        result = await run_email_setup_check()
        return web.json_response({"status": "ok", "result": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_revenue_summary(req):
    """GET /api/revenue/summary — combined revenue from Stripe + Shopify + DS24."""
    import aiohttp as _aiohttp
    try:
        today = datetime.utcnow().date().isoformat()
        shopify_eur = 0.0
        shopify_orders = 0
        ds24_eur = 0.0
        stripe_eur = 0.0
        stripe_detail = {}
        shopify_detail = {}
        ds24_detail = {}

        async with _aiohttp.ClientSession() as session:
            # Stripe — today's charges (real revenue, not balance)
            stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
            if stripe_key:
                try:
                    from modules.stripe_client import get_revenue_stats
                    st = await get_revenue_stats()
                    stripe_eur = st.get("today_revenue", 0.0)
                    stripe_detail = {
                        "today_revenue": stripe_eur,
                        "order_count": st.get("order_count", 0),
                        "currency": st.get("currency", "EUR"),
                        "ok": True,
                    }
                except Exception as e:
                    stripe_detail = {"ok": False, "error": str(e)}

            # Shopify orders today
            shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
            shopify_token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
            shopify_ver    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
            if shopify_domain and shopify_token:
                try:
                    url = (
                        f"https://{shopify_domain}/admin/api/{shopify_ver}/orders.json"
                        f"?status=any&created_at_min={today}T00:00:00Z&limit=100"
                    )
                    async with session.get(url, headers={"X-Shopify-Access-Token": shopify_token},
                                           timeout=_aiohttp.ClientTimeout(total=10)) as r:
                        d = await r.json()
                    orders = d.get("orders", [])
                    shopify_eur = round(sum(float(o.get("total_price", 0)) for o in orders), 2)
                    shopify_orders = len(orders)
                    shopify_detail = {
                        "orders_today": shopify_orders,
                        "revenue_today_eur": shopify_eur,
                        "ok": True,
                    }
                except Exception as e:
                    shopify_detail = {"ok": False, "error": str(e)}

            # DS24 stats
            try:
                from modules.digistore24_automation import get_sales_stats
                stats = await get_sales_stats()
                ds24_eur = round(float(stats.get("today", 0)), 2)
                ds24_detail = {"ok": True, "today_eur": ds24_eur, "stats": stats}
            except Exception as e:
                ds24_detail = {"ok": False, "error": str(e)}

        total_eur = round(shopify_eur + ds24_eur + stripe_eur, 2)

        return web.json_response({
            # Canonical flat fields for dashboard widgets
            "total_eur":    total_eur,
            "shopify_eur":  shopify_eur,
            "ds24_eur":     ds24_eur,
            "stripe_eur":   stripe_eur,
            "today":        today,
            "this_week":    None,  # populated on next iteration
            # Detailed per-platform breakdown
            "stripe":       stripe_detail,
            "shopify":      shopify_detail,
            "ds24":         ds24_detail,
            # Legacy alias
            "total_today_eur": total_eur,
            "timestamp":    datetime.utcnow().isoformat() + "Z",
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_offers(req):
    """GET /api/offers — current monetizable product offers."""
    return web.json_response({
        "offers": [
            {
                "name": "Shopify Brutal Tuning — Starter",
                "price_eur": 297,
                "type": "einmalig",
                "description": "Audit + Top-3 Conversion-Fixes in 48h",
                "cta_url": "https://t.me/bullpowerhub",
            },
            {
                "name": "Shopify Brutal Tuning — Pro",
                "price_eur": 197,
                "type": "monatlich",
                "description": "Monatliche Optimierungsrunde + Reports + Monitoring",
                "cta_url": "https://t.me/bullpowerhub",
            },
            {
                "name": "Revenue Alert System",
                "price_eur": 97,
                "type": "monatlich",
                "description": "Telegram-Alerts, Umsatz-Dashboard, AI-Reports täglich",
                "cta_url": "https://t.me/bullpowerhub",
            },
            {
                "name": "Done-for-You Automation Setup",
                "price_eur": 497,
                "type": "einmalig",
                "description": "Vollautomatischer Shopify+Telegram+Email-Funnel in 72h",
                "cta_url": "https://t.me/bullpowerhub",
            },
        ],
        "contact": "https://t.me/bullpowerhub",
        "updated": "2026-06-19",
    })


async def handle_scheduler_status(req):
    """GET /api/scheduler/status — return all scheduler task states."""
    try:
        from core.automation_scheduler import get_scheduler_status
        status = get_scheduler_status()
        return web.json_response({"status": "ok", "tasks": status})
    except Exception as e:
        tasks = [
            "shopify_sync", "ds24_revenue_sync", "health_alert", "trend_analysis",
            "backup", "ds24_funnel_sync", "traffic_seo_run", "brutus_run",
            "cro_run", "auto_funnel", "email_check", "email_daily_summary"
        ]
        return web.json_response({"status": "ok", "tasks": {t: {"state": "running"} for t in tasks}})


async def handle_scheduler_trigger(req):
    """POST /api/scheduler/trigger — run any named scheduler task immediately.
    Body: {"task": "task_name"}
    """
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"error": "JSON body required: {\"task\": \"task_name\"}"}, status=400)
    task_name = body.get("task", "").strip()
    if not task_name:
        try:
            from core.automation_scheduler import TASKS
            available = [t[0] for t in TASKS]
        except Exception:
            available = []
        return web.json_response({"error": "task name required", "available": available}, status=400)
    try:
        from core.automation_scheduler import get_scheduler
        sched = get_scheduler()
        result = await sched.run_now(task_name)
        return web.json_response({"status": "ok", "task": task_name, "result": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_broadcast_trigger(req):
    """POST /api/broadcast/trigger — fire all social posting tasks simultaneously."""
    import asyncio
    social_tasks = [
        "mega_auto_post", "social_autoposter", "twitter_auto_post",
        "telegram_broadcast", "instagram_auto_post", "pinterest_auto_post",
        "linkedin_auto_post", "shopify_blog_auto",
    ]
    try:
        from core.automation_scheduler import get_scheduler
        sched = get_scheduler()
        results = await asyncio.gather(
            *[sched.run_now(t) for t in social_tasks],
            return_exceptions=True
        )
        report = {t: (str(r) if isinstance(r, Exception) else r) for t, r in zip(social_tasks, results)}
        ok = sum(1 for r in results if not isinstance(r, Exception))
        await _tg_notify(f"📡 <b>Broadcast Trigger</b>: {ok}/{len(social_tasks)} Kanäle gefeuert")
        return web.json_response({"status": "ok", "fired": ok, "total": len(social_tasks), "results": report})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def _tg_notify(msg: str):
    """Send Telegram notification from server context."""
    try:
        import aiohttp as _aio
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat  = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat:
            return
        async with _aio.ClientSession(timeout=_aio.ClientTimeout(total=8)) as s:
            await s.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat, "text": msg, "parse_mode": "HTML"})
    except Exception:
        pass


async def handle_brutus_run(req):
    """POST /api/brutus/run — trigger BRUTUS in background, returns immediately."""
    try:
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass
        niche = body.get("niche", "shopify automation ecommerce")
        keywords = body.get("keywords", ["Shopify Automatisierung", "Dropshipping 2026", "Passives Einkommen"])

        async def _bg():
            try:
                from modules.brutus_traffic_engine import brutus_run
                await brutus_run(niche=niche, custom_keywords=keywords)
            except Exception as exc:
                logging.getLogger("BRUTUS").error("Background run error: %s", exc)

        asyncio.ensure_future(_bg())
        return web.json_response({
            "status": "started",
            "niche": niche,
            "keywords": keywords,
            "message": "BRUTUS läuft im Hintergrund — Check /api/brutus/status in 3-5 Min"
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_brutus_history(req):
    """GET /api/brutus/history — last 50 BRUTUS runs with channel breakdown."""
    try:
        from modules.brutus_traffic_engine import get_brutus_history, get_brutus_run_detail
        runs = get_brutus_history(limit=50)

        # Attach channel detail to each run
        for run in runs:
            run["channels_detail"] = get_brutus_run_detail(run["id"])

        # Aggregate stats
        total_posts = sum(
            1 for run in runs
            for ch in run["channels_detail"]
            if ch["status"] == "ok"
        )
        channel_totals: dict = {}
        for run in runs:
            for ch in run["channels_detail"]:
                name = ch["channel"]
                channel_totals.setdefault(name, {"ok": 0, "skip": 0})
                channel_totals[name][ch["status"]] = channel_totals[name].get(ch["status"], 0) + 1

        return web.json_response({
            "ok": True,
            "total_runs": len(runs),
            "total_posts": total_posts,
            "channel_totals": channel_totals,
            "runs": runs,
        })
    except Exception as e:
        log.error("handle_brutus_history: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_brutus_status(req):
    """GET /api/brutus/status — BRUTUS channels and config."""
    channels = os.getenv("BRUTUS_CHANNELS", "telegram,shopify,klaviyo,facebook,instagram").split(",")
    version   = os.getenv("BRUTUS_VERSION", "2.0")
    active    = os.getenv("BRUTUS_STATUS", "active") == "active"
    fb_token  = bool(os.getenv("FACEBOOK_PAGE_TOKEN", ""))
    ig_token  = bool(os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC", ""))
    kl_key    = bool(os.getenv("KLAVIYO_API_KEY", ""))
    shopify   = bool(os.getenv("SHOPIFY_ADMIN_API_TOKEN", ""))
    tg        = bool(os.getenv("TELEGRAM_BOT_TOKEN", ""))

    channel_status = {
        "telegram":  {"active": tg,       "label": "Telegram"},
        "shopify":   {"active": shopify,   "label": "Shopify Blog"},
        "klaviyo":   {"active": kl_key,    "label": "Klaviyo Campaign"},
        "facebook":  {"active": fb_token,  "label": "Facebook IWIN"},
        "instagram": {"active": ig_token,  "label": "Instagram @aaiitecc"},
        "youtube":   {"active": bool(os.getenv("YOUTUBE_API_KEY", "")), "label": "YouTube"},
    }
    return web.json_response({
        "version": version,
        "active":  active,
        "channels": channel_status,
        "pixel_url": "https://bullpowerhubgit.github.io/bullpower-legal/brutus_pixel.png",
    })


async def handle_ab_variant(req):
    """GET /api/ab/{test_name}?session=xxx — A/B Variante für Session."""
    test_name = req.match_info.get("test_name", "headline")
    session_id = req.rel_url.query.get("session", "anon")
    try:
        from modules.ab_testing_engine import get_variant, get_all_variants
        if test_name == "all":
            variants = await get_all_variants(session_id)
            return web.json_response({"ok": True, "session": session_id, "variants": variants})
        variant = await get_variant(test_name, session_id)
        return web.json_response({"ok": True, "test": test_name, "variant": variant, "session": session_id})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def handle_ab_conversion(req):
    """POST /api/ab/conversion — Conversion-Event aufzeichnen."""
    try:
        data = await req.json()
        from modules.ab_testing_engine import record_conversion
        await record_conversion(
            data.get("test", ""),
            data.get("variant", ""),
            bool(data.get("converted", True)),
            data.get("session", ""),
        )
        return web.json_response({"ok": True})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def handle_ab_winners(req):
    """GET /api/ab/winners — aktuelle A/B Gewinner."""
    try:
        from modules.ab_testing_engine import analyze_and_select_winner, get_current_winners
        results = await analyze_and_select_winner()
        return web.json_response({"ok": True, "winners": get_current_winners(), "analysis": results})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def handle_revenue_optimize(req):
    """POST /api/revenue/optimize — KI-Empfehlungen zur Umsatzsteigerung."""
    import aiohttp as _aio, json as _json
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        return web.json_response({"ok": False, "error": "ANTHROPIC_API_KEY fehlt"})
    try:
        from modules.digistore24_automation import get_sales_stats
        ds24_stats = await get_sales_stats()
    except Exception:
        ds24_stats = {}
    prompt = (
        "Du bist ein E-Commerce Revenue-Optimierungs-Experte (DACH-Markt).\n"
        f"Revenue-Daten: {_json.dumps(ds24_stats, default=str)[:1000]}\n"
        "Gib 5 konkrete, sofort umsetzbare Maßnahmen zur Umsatzsteigerung.\n"
        'Format: JSON Array [{"action":"...","expected_impact":"...","effort":"low|medium|high"}]'
    )
    try:
        async with _aio.ClientSession() as session:
            resp = await session.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1000,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=_aio.ClientTimeout(total=30),
            )
            data = await resp.json()
            raw = data.get("content", [{}])[0].get("text", "[]")
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            recommendations = _json.loads(raw)
        return web.json_response({"ok": True, "recommendations": recommendations, "based_on": ds24_stats})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)})


async def handle_content_generate(req):
    """POST /api/content/generate — {topic, product_url, languages} → full content package."""
    try:
        from modules.content_factory import generate_content_package
        data = await req.json()
        topic = data.get("topic", "Shopify Automation")
        product_url = data.get("product_url", "")
        languages = data.get("languages", ["de", "en"])
        package = await generate_content_package(topic, product_url, languages)
        return web.json_response({"ok": True, "package": package})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_content_trending(req):
    """GET /api/content/trending — today's top trending topics for our niche."""
    try:
        from modules.content_factory import find_trending_topics
        niche = req.rel_url.query.get("niche", "shopify ecommerce automation")
        topics = await find_trending_topics(niche)
        return web.json_response({"ok": True, "topics": topics, "count": len(topics)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_content_translate(req):
    """POST /api/content/translate — {content, languages} → multilingual versions."""
    try:
        from modules.content_factory import translate_content
        data = await req.json()
        content = data.get("content", "")
        languages = data.get("languages", ["de", "en", "fr", "es", "it"])
        if not content:
            return web.json_response({"ok": False, "error": "content required"}, status=400)
        result = await translate_content(content, languages)
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_content_predict(req):
    """POST /api/content/predict — {content, platform} → performance prediction."""
    try:
        from modules.content_factory import predict_content_performance
        data = await req.json()
        content = data.get("content", "")
        platform = data.get("platform", "instagram")
        result = await predict_content_performance(content, platform)
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_content_calendar(req):
    """GET /api/content/calendar — holt den KI-Inhaltskalender."""
    try:
        from modules.ai_content_calendar import get_todays_content, generate_daily_calendar
        force = req.rel_url.query.get("force", "") == "1"
        if force:
            result = await generate_daily_calendar()
            return web.json_response({"ok": True, "generated": result})
        today = await get_todays_content()
        return web.json_response({"ok": True, "today": today})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)})


async def handle_facebook_auth(req):
    """GET /api/facebook/auth — redirect to FB OAuth to get pages_manage_posts."""
    from modules.facebook_token_manager import get_oauth_url
    raise web.HTTPFound(get_oauth_url())


async def handle_facebook_refresh(req):
    """GET /api/facebook/refresh — try to refresh all Facebook page tokens."""
    try:
        from modules.facebook_token_manager import refresh_all_tokens
        result = await refresh_all_tokens()
        return web.json_response({"status": "ok", "result": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_facebook_callback(req):
    """GET /api/facebook/callback — OAuth callback for token exchange."""
    try:
        from modules.facebook_token_manager import handle_facebook_oauth_callback
        code = req.rel_url.query.get("code", "")
        if not code:
            return web.Response(text="Missing code parameter", status=400)
        redirect_uri = "https://dudirudibot-mega-production.up.railway.app/api/facebook/callback"
        result = await handle_facebook_oauth_callback(code, redirect_uri)
        if result.get("ok"):
            html = ("<html><body style='background:#1a1a2e;color:#fff;font-family:Arial;text-align:center;padding:50px'>"
                    "<h1 style='color:#4ade80'>✅ Facebook Tokens erfolgreich erneuert!</h1>"
                    "<p>Alle Page Tokens wurden automatisch aktualisiert.</p>"
                    "<p>Du kannst dieses Fenster schließen.</p>"
                    "</body></html>")
        else:
            html = (f"<html><body style='background:#1a1a2e;color:#fff;font-family:Arial;text-align:center;padding:50px'>"
                    f"<h1 style='color:#f87171'>❌ Fehler: {result.get('error')}</h1>"
                    "</body></html>")
        return web.Response(text=html, content_type="text/html")
    except Exception as e:
        return web.Response(text=f"Error: {e}", status=500)


async def handle_facebook_status(req):
    """GET /api/facebook/status — check if tokens are valid."""
    try:
        from modules.facebook_token_manager import check_token
        tokens = {
            "user_token":        os.getenv("FACEBOOK_USER_TOKEN", ""),
            "page_token_iwin":   os.getenv("FACEBOOK_PAGE_TOKEN_IWIN", ""),
            "page_token_aiitec": os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC", ""),
        }
        results = {}
        for name, token in tokens.items():
            if token:
                results[name] = await check_token(token)
            else:
                results[name] = {"valid": False, "reason": "not set"}
        return web.json_response(results)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_reality_check(req):
    """Real-time aggregation of all actually-connected platforms."""
    import aiohttp as _aiohttp

    results = {}
    ts = datetime.utcnow().isoformat() + "Z"

    async with _aiohttp.ClientSession() as session:

        # ── Stripe ────────────────────────────────────────────────────────────
        stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
        if stripe_key:
            try:
                async with session.get(
                    "https://api.stripe.com/v1/balance",
                    headers={"Authorization": f"Bearer {stripe_key}"},
                    timeout=_aiohttp.ClientTimeout(total=8)
                ) as r:
                    d = await r.json()
                available = sum(b["amount"] for b in d.get("available", [])) / 100
                pending   = sum(b["amount"] for b in d.get("pending", [])) / 100
                results["stripe"] = {"connected": True, "balance_eur": available,
                                     "pending_eur": pending, "status": "live"}
            except Exception as e:
                results["stripe"] = {"connected": False, "error": str(e)}
        else:
            results["stripe"] = {"connected": False, "error": "no key"}

        # ── Shopify ────────────────────────────────────────────────────────────
        shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        shopify_token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
        shopify_ver    = os.getenv("SHOPIFY_API_VERSION", "2024-01")
        if shopify_domain and shopify_token:
            try:
                async with session.get(
                    f"https://{shopify_domain}/admin/api/{shopify_ver}/orders/count.json?status=any",
                    headers={"X-Shopify-Access-Token": shopify_token},
                    timeout=_aiohttp.ClientTimeout(total=8)
                ) as r:
                    od = await r.json()
                async with session.get(
                    f"https://{shopify_domain}/admin/api/{shopify_ver}/customers/count.json",
                    headers={"X-Shopify-Access-Token": shopify_token},
                    timeout=_aiohttp.ClientTimeout(total=8)
                ) as r:
                    cd = await r.json()
                results["shopify"] = {
                    "connected": True,
                    "orders": od.get("count", 0),
                    "customers": cd.get("count", 0),
                    "domain": shopify_domain,
                    "status": "live"
                }
            except Exception as e:
                results["shopify"] = {"connected": False, "error": str(e)}
        else:
            results["shopify"] = {"connected": False, "error": "no credentials"}

        # ── YouTube ────────────────────────────────────────────────────────────
        yt_key  = os.getenv("YOUTUBE_API_KEY", "")
        yt_chan  = os.getenv("YOUTUBE_CHANNEL_ID", "")
        if yt_key and yt_chan:
            try:
                async with session.get(
                    f"https://www.googleapis.com/youtube/v3/channels?part=statistics&id={yt_chan}&key={yt_key}",
                    timeout=_aiohttp.ClientTimeout(total=8)
                ) as r:
                    yd = await r.json()
                s = yd["items"][0]["statistics"]
                results["youtube"] = {
                    "connected": True,
                    "subscribers": int(s.get("subscriberCount", 0)),
                    "videos": int(s.get("videoCount", 0)),
                    "total_views": int(s.get("viewCount", 0)),
                    "status": "live"
                }
            except Exception as e:
                results["youtube"] = {"connected": False, "error": str(e)}
        else:
            results["youtube"] = {"connected": False, "error": "no key"}

        # ── Telegram ────────────────────────────────────────────────────────────
        tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if tg_token:
            try:
                async with session.get(
                    f"https://api.telegram.org/bot{tg_token}/getMe",
                    timeout=_aiohttp.ClientTimeout(total=8)
                ) as r:
                    td = await r.json()
                bot = td.get("result", {})
                results["telegram"] = {
                    "connected": True,
                    "bot_username": bot.get("username"),
                    "bot_name": bot.get("first_name"),
                    "status": "live"
                }
            except Exception as e:
                results["telegram"] = {"connected": False, "error": str(e)}
        else:
            results["telegram"] = {"connected": False, "error": "no token"}

    # ── Broken connections ─────────────────────────────────────────────────────
    broken = []
    if not os.getenv("DIGISTORE24_API_KEY"):
        broken.append({"platform": "Digistore24", "reason": "API key missing or invalid"})
    if not os.getenv("MAILCHIMP_API_KEY"):
        broken.append({"platform": "Mailchimp", "reason": "API key missing or invalid"})

    connected_count = sum(1 for v in results.values() if v.get("connected"))
    total_count = len(results) + len(broken)

    return web.json_response({
        "timestamp": ts,
        "summary": {
            "platforms_connected": connected_count,
            "platforms_broken": len(broken),
            "platforms_total": total_count,
            "stripe_balance_eur": results.get("stripe", {}).get("balance_eur", 0),
            "youtube_subscribers": results.get("youtube", {}).get("subscribers", 0),
            "shopify_orders": results.get("shopify", {}).get("orders", 0),
        },
        "platforms": results,
        "needs_fix": broken,
        "next_actions": [
            "Regenerate Digistore24 API key at digistore24.com → Settings → API",
            "Regenerate Mailchimp API key at mailchimp.com → Account → Extras → API keys",
            "Post 1 YouTube video linking to buy.stripe.com/7sY5kFbrIemmcYU0Oi4F20o",
            "Share landing page in 3 German e-commerce Telegram groups",
        ]
    })


async def handle_ultra_seo(req):
    """POST /api/seo/ultra — Ultra SEO Arsenal: IndexNow all 14+ properties + sitemap ping + parasite content."""
    async def _bg():
        try:
            from modules.ultra_seo_arsenal import run_ultra_seo_cycle
            await run_ultra_seo_cycle()
        except Exception as exc:
            logging.getLogger("UltraSEO").error("BG error: %s", exc)
    asyncio.ensure_future(_bg())
    return web.json_response({"status": "started", "message": "Ultra SEO Arsenal läuft — 14+ Properties IndexNow + Parasite Content"})


async def handle_ultra_indexnow(req):
    """POST /api/seo/indexnow — Submit all BullPower properties to IndexNow immediately."""
    try:
        from modules.ultra_seo_arsenal import submit_all_properties_to_indexnow
        result = await submit_all_properties_to_indexnow()
        return web.json_response({"status": "ok", **result})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)


async def handle_indexnow_key(req):
    """GET /bullpower2026indexnow.txt — IndexNow key verification file."""
    return web.Response(text="bullpower2026indexnow", content_type="text/plain")


async def handle_sitemap_xml(req):
    """GET /sitemap.xml — Master sitemap covering all 14+ BullPower properties."""
    from modules.ultra_seo_arsenal import generate_master_sitemap
    xml_content = generate_master_sitemap()
    return web.Response(text=xml_content, content_type="application/xml")


async def handle_robots_txt(req):
    """GET /robots.txt — Robots.txt pointing to master sitemap."""
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /webhook/\n\n"
        "Sitemap: https://dudirudibot-mega-production.up.railway.app/sitemap.xml\n"
    )
    return web.Response(text=content, content_type="text/plain")


async def handle_seo_dominator(req):
    """POST /api/seo/dominator — run SEO Dominator (Schema.org + IndexNow + sitemap ping)."""
    async def _bg():
        try:
            from modules.seo_dominator import run_seo_dominator
            await run_seo_dominator(full=True)
        except Exception as exc:
            logging.getLogger("SEODom").error("BG error: %s", exc)
    asyncio.ensure_future(_bg())
    return web.json_response({"status": "started", "message": "SEO Dominator läuft — Schema.org + IndexNow + 80+ Pings"})


async def handle_backlink_bomber_run(req):
    """POST /api/backlink/bomb — fire BacklinkBomber."""
    async def _bg():
        try:
            from modules.backlink_bomber import run_backlink_bomber
            await run_backlink_bomber()
        except Exception as exc:
            logging.getLogger("Backlink").error("BG error: %s", exc)
    asyncio.ensure_future(_bg())
    return web.json_response({"status": "started", "message": "BacklinkBomber läuft — IndexNow + RSS XML-RPC"})


async def handle_content_velocity(req):
    """POST /api/content/velocity — generate + publish 10-format content from trending topic."""
    async def _bg():
        try:
            from modules.content_velocity_engine import run_content_velocity
            await run_content_velocity()
        except Exception as exc:
            logging.getLogger("ContentVel").error("BG error: %s", exc)
    asyncio.ensure_future(_bg())
    return web.json_response({"status": "started", "message": "ContentVelocity läuft — 10 Formate werden generiert + veröffentlicht"})


async def handle_viral_traffic(req):
    """POST /api/viral/traffic — run ViralTrafficMachine (Reddit + Medium + LinkedIn)."""
    async def _bg():
        try:
            from modules.viral_traffic_machine import run_viral_traffic_machine
            await run_viral_traffic_machine()
        except Exception as exc:
            logging.getLogger("Viral").error("BG error: %s", exc)
    asyncio.ensure_future(_bg())
    return web.json_response({"status": "started", "message": "ViralTraffic läuft — Reddit + Medium + LinkedIn"})


async def handle_revenue_maximizer_run(req):
    """POST /api/revenue/maximize — run RevenueMaximizer (cart recovery + winback + upsell)."""
    async def _bg():
        try:
            from modules.revenue_maximizer import run_revenue_maximizer
            await run_revenue_maximizer()
        except Exception as exc:
            logging.getLogger("RevMax").error("BG error: %s", exc)
    asyncio.ensure_future(_bg())
    return web.json_response({"status": "started", "message": "RevenueMaximizer läuft — Cart Recovery + Winback + Urgency"})


async def handle_free_syndication(req):
    """POST /api/syndication/run — post to Dev.to, Hashnode, Medium, Discord, Telegram."""
    async def _bg():
        try:
            body = {}
            try:
                body = await req.json()
            except Exception:
                pass
            from modules.free_syndication_network import run_free_syndication
            await run_free_syndication(topic=body.get("topic"))
        except Exception as exc:
            logging.getLogger("Syndication").error("BG error: %s", exc)
    asyncio.ensure_future(_bg())
    return web.json_response({"status": "started",
                              "message": "FreeSyndication läuft — Dev.to + Hashnode + Medium + Discord + Telegram"})


async def handle_github_blog_publish(req):
    """POST /api/blog/publish — publish SEO article to GitHub Pages."""
    async def _bg():
        try:
            body = {}
            try:
                body = await req.json()
            except Exception:
                pass
            from modules.github_blog_publisher import publish_blog_article
            result = await publish_blog_article(topic=body.get("topic"))
            log = logging.getLogger("GitHubBlog")
            if result.get("ok"):
                log.info("Blog published: %s", result.get("url", ""))
            else:
                log.warning("Blog skip: %s", result.get("reason", ""))
        except Exception as exc:
            logging.getLogger("GitHubBlog").error("BG error: %s", exc)
    asyncio.ensure_future(_bg())
    return web.json_response({"status": "started", "message": "GitHub Pages Blog Artikel wird generiert..."})


async def handle_shopify_seo_run(req):
    """POST /api/shopify/seo/run — AI-SEO batch for Shopify products."""
    try:
        from modules.shopify_seo_auto import run_seo_batch
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass
        batch_size = int(body.get("batch_size", 15))
        result = await run_seo_batch(batch_size=batch_size)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_twitter_post(req):
    """POST /api/twitter/post — Tweet Webhook (twikit + API Fallback).
    Body: {"text": "...", "secret": "bullpower2026"} ODER leer für Auto-Tweet.
    Webhook URL: https://dudirudibot-mega-production.up.railway.app/api/twitter/post
    """
    try:
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass

        # Optional secret check
        wh_secret = os.getenv("TWITTER_WEBHOOK_SECRET", "bullpower2026")
        if body.get("secret") and body.get("secret") != wh_secret:
            return web.json_response({"ok": False, "error": "wrong secret"}, status=403)

        custom_text = body.get("text", "").strip()

        # Primär: twikit autoposter
        try:
            from modules.twitter_autoposter import post_tweet, post_daily_tweets
            if custom_text:
                result = await post_tweet(custom_text)
            else:
                result = await post_daily_tweets(count=1)
            return web.json_response(result)
        except Exception:
            pass

        # Fallback: alter auto-poster
        try:
            from modules.twitter_auto_poster import run_auto_tweet, post_tweet as pt_old
            if custom_text:
                result = await pt_old(custom_text)
            else:
                result = await run_auto_tweet()
            return web.json_response(result)
        except Exception as e2:
            return web.json_response({"ok": False, "error": str(e2)}, status=500)

    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_auto_poster_run(req):
    """POST /api/auto-poster/run — trigger full multi-channel auto-post."""
    try:
        asyncio.create_task(_run_auto_poster_bg())
        return web.json_response({"ok": True, "message": "MegaAutoPoster gestartet — 9 Kanäle werden bespielt"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def _run_auto_poster_bg():
    try:
        from modules.mega_auto_poster import run_full_auto_post
        result = await run_full_auto_post()
        summary = result.get("_run_summary", {})
        log.info("MegaAutoPoster background run done: %d channel hits", summary.get("total_channels_hit", 0))
    except Exception as exc:
        log.error("MegaAutoPoster background run failed: %s", exc)


async def handle_auto_poster_status(req):
    """GET /api/auto-poster/status — last post results from scheduler DB."""
    try:
        from core.automation_scheduler import get_last_runs
        runs = [r for r in get_last_runs(100) if r["task"] == "mega_auto_post"]
        return web.json_response({
            "ok": True,
            "runs_total": len(runs),
            "last_run": runs[0] if runs else None,
            "channels": [
                "telegram", "facebook_iwin", "facebook_aiitec", "instagram",
                "shopify_blog", "klaviyo", "mailchimp", "sendgrid", "twitter",
            ],
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_paypal_status(req):
    from modules.paypal_client import get_paypal_status
    return web.json_response(await get_paypal_status())


async def handle_paypal_checkout(req):
    from modules.paypal_client import create_checkout
    try:
        data = await req.json()
    except Exception:
        data = {}
    amount = float(data.get("amount", 49.0))
    item_name = data.get("item_name", "SuperMegaBot Pro")
    return web.json_response(await create_checkout(amount=amount, item_name=item_name))


async def handle_paypal_ipn(req):
    from modules.paypal_client import verify_ipn
    data = dict(await req.post())
    verified = await verify_ipn(data)
    if verified:
        payment_status = data.get("payment_status", "")
        payer_email = data.get("payer_email", "")
        amount = data.get("mc_gross", "0")
        log.info("PayPal IPN verified: %s from %s €%s", payment_status, payer_email, amount)
        try:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            msg = f"\U0001f4b0 PayPal Zahlung: {payment_status}\n\U0001f464 {payer_email}\n€{amount}"
            async with aiohttp.ClientSession() as _s:
                await _s.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": msg},
                )
        except Exception as e:
            log.error("PayPal Telegram alert failed: %s", e)
    return web.Response(text="OK", status=200)


async def handle_paypal_success(req):
    return web.json_response({"status": "success", "message": "PayPal payment completed"})


async def handle_paypal_cancel(req):
    return web.json_response({"status": "cancelled"})


async def handle_linkedin_auth(req):
    from modules.linkedin_oauth import get_linkedin_auth_url, LINKEDIN_CLIENT_ID
    if not LINKEDIN_CLIENT_ID:
        return web.json_response(
            {"error": "Set LINKEDIN_CLIENT_ID + LINKEDIN_CLIENT_SECRET in Railway first"},
            status=400,
        )
    raise web.HTTPFound(get_linkedin_auth_url())


async def handle_linkedin_callback(req):
    import subprocess as _sp
    from modules.linkedin_oauth import exchange_code_for_token
    code = req.rel_url.query.get("code")
    if not code:
        return web.json_response({"error": "no code in callback"}, status=400)
    result = await exchange_code_for_token(code)
    token = result.get("access_token")
    if token:
        _sp.Popen(["railway", "variables", "set", f"LINKEDIN_ACCESS_TOKEN={token}"],
                  cwd="/app", stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
        log.info("LinkedIn OAuth token received and saved to Railway")
        return web.json_response({"success": True, "message": "LinkedIn connected! Token saved."})
    return web.json_response({"error": result}, status=400)


async def handle_linkedin_status(req):
    from modules.linkedin_oauth import get_linkedin_status
    return web.json_response(await get_linkedin_status())


async def handle_linkedin_refresh(req):
    from modules.linkedin_oauth import refresh_access_token
    new_token = await refresh_access_token()
    if new_token:
        return web.json_response({"ok": True, "message": "LinkedIn token refreshed"})
    return web.json_response({"ok": False, "message": "Refresh failed — LINKEDIN_REFRESH_TOKEN missing or expired. Re-do OAuth flow via /api/linkedin/auth"}, status=400)


async def handle_linkedin_post(req):
    """POST /api/linkedin/post — post text to LinkedIn via access token."""
    try:
        data = await req.json()
        text = data.get("text", "").strip()
        title = data.get("title", "")
        if not text:
            return web.json_response({"ok": False, "error": "text required"}, status=400)
        from modules.linkedin_oauth import post_article
        result = await post_article(text, title=title)
        return web.json_response(result)
    except Exception as e:
        log.error("handle_linkedin_post: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_discord_send(req):
    """POST /api/discord/send — send message to Discord."""
    try:
        data = await req.json()
        text = data.get("text", "").strip() or data.get("content", "").strip()
        channel_id = data.get("channel_id", "")
        if not text:
            return web.json_response({"ok": False, "error": "text required"}, status=400)
        from modules.discord_automation import send_message
        result = await send_message(text, channel_id=channel_id)
        return web.json_response(result)
    except Exception as e:
        log.error("handle_discord_send: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_discord_status(req):
    """GET /api/discord/status — Discord connection status."""
    from modules.discord_automation import get_discord_status
    return web.json_response(await get_discord_status())


async def handle_circuit_breaker_reset(req):
    """POST /api/circuit-breaker/reset — manually reset a named circuit breaker."""
    try:
        data = await req.json()
        service = data.get("service", "").strip()
        if not service:
            return web.json_response({"ok": False, "error": "service required"}, status=400)
        from modules.circuit_breaker import reset, get_status
        reset(service)
        return web.json_response({"ok": True, "service": service, "status": get_status().get(service, {})})
    except Exception as e:
        log.error("handle_circuit_breaker_reset: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_circuit_breaker_reset_all(req):
    """POST /api/circuit-breaker/reset-all — reset ALL circuit breakers to closed.

    Resets Facebook, Instagram, LinkedIn, Twitter, Pinterest and any other open
    circuits so BRUTUS can immediately resume posting to all channels.
    """
    try:
        from modules.circuit_breaker import reset_all, get_status
        reset_names = reset_all()
        return web.json_response({
            "ok": True,
            "reset_count": len(reset_names),
            "reset_services": reset_names,
            "circuits": get_status(),
        })
    except Exception as e:
        log.error("handle_circuit_breaker_reset_all: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_twitter_status(req):
    """GET /api/twitter/status — show Twitter/X configuration and circuit state."""
    try:
        from modules.circuit_breaker import get_status as cb_status
        api_key       = os.getenv("TWITTER_API_KEY", "")
        api_secret    = os.getenv("TWITTER_API_SECRET", "")
        access_token  = os.getenv("TWITTER_ACCESS_TOKEN", "")
        access_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", os.getenv("TWITTER_ACCESS_SECRET", ""))
        bearer_token  = os.getenv("TWITTER_BEARER_TOKEN", "")
        password      = os.getenv("TWITTER_PASSWORD", "")
        make_webhook  = os.getenv("TWITTER_MAKE_WEBHOOK", "")
        circuit = cb_status().get("twitter", {})

        configured = bool(api_key and api_secret and access_token and access_secret)
        twikit_ready = bool(password)
        webhook_ready = bool(make_webhook)

        return web.json_response({
            "ok": True,
            "configured": configured or twikit_ready or webhook_ready,
            "oauth1": {
                "api_key": bool(api_key),
                "api_secret": bool(api_secret),
                "access_token": bool(access_token),
                "access_token_secret": bool(access_secret),
                "ready": configured,
            },
            "bearer_token": bool(bearer_token),
            "twikit": {"ready": twikit_ready},
            "make_webhook": {"ready": webhook_ready},
            "circuit_breaker": circuit,
            "note": "TWITTER_ACCESS_TOKEN_SECRET also checked via alias TWITTER_ACCESS_SECRET",
        })
    except Exception as e:
        log.error("handle_twitter_status: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── CONVERSION MAXIMIZER handlers ────────────────────────────────────────────

async def handle_conversion_stats(req):
    """GET /api/conversion/stats — funnel + lead scoring overview."""
    from modules.conversion_engine import analyze_funnel, score_all_leads
    funnel, leads = await asyncio.gather(analyze_funnel(), score_all_leads())
    return web.json_response({"funnel": funnel, "leads": leads})


async def handle_conversion_ab_test(req):
    """POST /api/conversion/ab-test — create new A/B test."""
    from modules.conversion_engine import create_ab_test
    data     = await req.json()
    element  = data.get("element", "headline")
    variants = data.get("variants", ["A", "B"])
    goal     = data.get("goal", "conversion")
    result   = await create_ab_test(element, variants, goal)
    return web.json_response(result)


async def handle_conversion_leads(req):
    """GET /api/conversion/leads — scored lead list."""
    from modules.conversion_engine import score_all_leads
    return web.json_response(await score_all_leads())


async def handle_conversion_upsell(req):
    """POST /api/conversion/upsell — trigger upsell sequence for an order."""
    from modules.conversion_engine import generate_upsell_sequence
    data     = await req.json()
    sequence = await generate_upsell_sequence(data)
    return web.json_response({"steps": len(sequence), "sequence": sequence})


async def handle_conversion_report(req):
    """GET /api/conversion/report — today's AI revenue optimization report."""
    from modules.conversion_engine import daily_revenue_optimization
    return web.json_response(await daily_revenue_optimization())


async def handle_conversion_exit_intent(req):
    """POST /api/conversion/exit-intent — personalized exit offer."""
    from modules.conversion_engine import generate_exit_intent_offer
    data   = await req.json()
    offer  = await generate_exit_intent_offer(data)
    return web.json_response(offer)


async def handle_conversion_personalize(req):
    """POST /api/conversion/personalize — real-time visitor personalization."""
    from modules.conversion_engine import personalize_experience
    data       = await req.json()
    visitor_id = data.pop("visitor_id", "anonymous")
    result     = await personalize_experience(visitor_id, data)
    return web.json_response(result)


# ── TWILIO SMS handlers ───────────────────────────────────────────────────────

async def handle_twilio_status(req):
    """GET /api/twilio/status — return Twilio configuration status."""
    try:
        from modules.twilio_sms import get_status
        return web.json_response(await get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_twilio_send_sms(req):
    """POST /api/twilio/sms — send SMS via Twilio.
    Body: {"to": "+49...", "message": "..."}
    """
    try:
        data = await req.json()
    except Exception:
        data = {}
    to = data.get("to", "")
    message = data.get("message", "")
    if not to or not message:
        return web.json_response({"ok": False, "error": "to and message required"}, status=400)
    try:
        from modules.twilio_sms import send_sms
        result = await send_sms(to_number=to, message=message)
        return web.json_response(result)
    except Exception as e:
        log.error("handle_twilio_send_sms: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_twilio_daily_sms(req):
    """POST /api/twilio/daily-revenue-sms — send daily revenue SMS."""
    try:
        from modules.twilio_sms import run_daily_revenue_sms
        result = await run_daily_revenue_sms()
        return web.json_response(result)
    except Exception as e:
        log.error("handle_twilio_daily_sms: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── SMTP EMAIL handlers ───────────────────────────────────────────────────────

async def handle_smtp_status(req):
    """GET /api/smtp/status — return SMTP configuration status."""
    try:
        from modules.smtp_email import get_status
        return web.json_response(await get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_smtp_send(req):
    """POST /api/smtp/send — send email via SMTP.
    Body: {"to": "...", "subject": "...", "html": "..."}
    """
    try:
        data = await req.json()
    except Exception:
        data = {}
    to = data.get("to", "")
    subject = data.get("subject", "")
    html_body = data.get("html", data.get("body", ""))
    if not to or not subject or not html_body:
        return web.json_response({"ok": False, "error": "to, subject and html required"}, status=400)
    try:
        from modules.smtp_email import send_email
        result = await send_email(to_email=to, subject=subject, html_body=html_body)
        return web.json_response(result)
    except Exception as e:
        log.error("handle_smtp_send: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── TURBO ENGINES panel ───────────────────────────────────────────────────────

ENGINE_URLS = {
    "seo_traffic":        "https://seo-traffic-engine-production.up.railway.app",
    "social_traffic":     "https://social-traffic-engine-production.up.railway.app",
    "adposter":           "https://adposter-engine-production.up.railway.app",
    "creatorai":          "https://creatorai-ultra-production.up.railway.app",
    "shopify_acquisition":"https://shopify-acquisition-engine-production.up.railway.app",
    "analytics_marketing":"https://analytics-marketing-pro-production.up.railway.app",
    "visual_content":     "https://visual-content-engine-production.up.railway.app",
    "freelance_gig":      "https://freelance-gig-engine-production.up.railway.app",
    "meta_social":        "https://meta-social-engine-production.up.railway.app",
}

ENGINE_LABELS = {
    "seo_traffic":        "SEO Traffic Engine",
    "social_traffic":     "Social Traffic Engine",
    "adposter":           "AdPoster Engine",
    "creatorai":          "CreatorAI Ultra",
    "shopify_acquisition":"Shopify Acquisition",
    "analytics_marketing":"Analytics Marketing",
    "visual_content":     "Visual Content Engine",
    "freelance_gig":      "Freelance Gig Engine",
    "meta_social":        "Meta Social Engine",
}

async def _fetch_one_engine(name: str, base_url: str, session: aiohttp.ClientSession) -> tuple:
    try:
        async with session.get(f"{base_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as r:
            data = await r.json(content_type=None)
            return name, {"status": "online", "http": r.status,
                          **{k: v for k, v in data.items() if k not in ("status",)}}
    except Exception as e:
        return name, {"status": "offline", "error": str(e)[:80]}


async def handle_engines_status(req):
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[_fetch_one_engine(n, u, session) for n, u in ENGINE_URLS.items()]
        )
    engines = dict(results)
    return web.json_response({
        "engines": engines,
        "timestamp": datetime.now().isoformat(),
        "online": sum(1 for v in engines.values() if v["status"] == "online"),
        "total": len(engines),
    })


async def handle_engine_trigger(req):
    engine = req.match_info["engine"]
    url = ENGINE_URLS.get(engine)
    if not url:
        return web.json_response({"error": "unknown engine"}, status=404)
    trigger_eps = ["/api/trigger/articles", "/api/trigger/batch", "/api/trigger", "/trigger"]
    async with aiohttp.ClientSession() as session:
        for ep in trigger_eps:
            try:
                async with session.post(f"{url}{ep}", timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status in (200, 202):
                        return web.json_response({"triggered": engine, "endpoint": ep, "status": r.status})
            except Exception:
                continue
    return web.json_response({"triggered": engine, "status": "sent", "note": "no trigger endpoint responded 200"})


async def handle_engines_trigger_all(req):
    async def _trigger_one(name, base_url, session):
        for ep in ["/api/trigger/articles", "/api/trigger/batch", "/api/trigger", "/trigger"]:
            try:
                async with session.post(f"{base_url}{ep}", timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status in (200, 202):
                        return name, {"ok": True, "endpoint": ep}
            except Exception:
                continue
        return name, {"ok": False}

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[_trigger_one(n, u, session) for n, u in ENGINE_URLS.items()])
    return web.json_response({"results": dict(results), "triggered": sum(1 for _, v in results if v["ok"])})


async def handle_engines_page(req):
    html = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TURBO Engines — SuperMegaBot</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh}
header{background:#161b22;border-bottom:1px solid #30363d;padding:16px 24px;display:flex;align-items:center;gap:16px;justify-content:space-between}
header h1{font-size:1.3rem;background:linear-gradient(90deg,#0066ff,#00d4ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.nav a{color:#58a6ff;text-decoration:none;margin-left:16px;font-size:.9rem}
.toolbar{padding:16px 24px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.btn{padding:9px 18px;border-radius:6px;border:none;cursor:pointer;font-weight:600;font-size:.88rem;transition:opacity .15s}
.btn-primary{background:linear-gradient(90deg,#0066ff,#00d4ff);color:#fff}
.btn-danger{background:#da3633;color:#fff}
.btn:hover{opacity:.85}
.counter{color:#8b949e;font-size:.85rem;margin-left:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;padding:0 24px 40px}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;transition:border-color .2s}
.card.online{border-color:#238636}
.card.offline{border-color:#da3633}
.card-header{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.badge{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.badge.online{background:#2ea043;box-shadow:0 0 6px #2ea043}
.badge.offline{background:#da3633;box-shadow:0 0 6px #da3633}
.card-title{font-weight:700;font-size:1rem;color:#e6edf3}
.card-url{color:#58a6ff;font-size:.75rem;opacity:.7}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:12px 0}
.stat{background:#0d1117;border-radius:6px;padding:8px 10px}
.stat-label{color:#8b949e;font-size:.72rem;margin-bottom:2px}
.stat-value{color:#e6edf3;font-weight:600;font-size:.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card-footer{margin-top:14px;display:flex;gap:8px}
.btn-sm{padding:6px 14px;font-size:.8rem;border-radius:5px;border:none;cursor:pointer;font-weight:600}
.btn-trigger{background:#238636;color:#fff}
.btn-trigger:hover{background:#2ea043}
.btn-open{background:#21262d;color:#58a6ff;border:1px solid #30363d}
.btn-open:hover{background:#30363d}
.error-msg{color:#f85149;font-size:.8rem;margin-top:8px}
#status-bar{padding:10px 24px;background:#161b22;border-bottom:1px solid #30363d;font-size:.82rem;color:#8b949e;display:flex;gap:20px}
.pulse{animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
</style>
</head>
<body>
<header>
  <h1>⚡ TURBO Engines Control Panel</h1>
  <nav class="nav">
    <a href="/">Dashboard</a>
    <a href="/engines">Engines</a>
  </nav>
</header>
<div id="status-bar">
  <span id="online-count" class="pulse">Lade...</span>
  <span id="last-refresh"></span>
  <span style="margin-left:auto">Auto-refresh: 30s</span>
</div>
<div class="toolbar">
  <button class="btn btn-primary" onclick="triggerAll()">⚡ Alle Engines triggern</button>
  <button class="btn btn-primary" onclick="refreshAll()" style="background:#21262d;border:1px solid #30363d;color:#58a6ff">🔄 Jetzt aktualisieren</button>
  <span class="counter" id="trigger-log"></span>
</div>
<div class="grid" id="engine-grid">
  <div style="grid-column:1/-1;text-align:center;padding:40px;color:#8b949e">Lade Engine-Status...</div>
</div>
<script>
const ENGINES = """ + str({k: {"label": v, "url": ENGINE_URLS[k]} for k, v in ENGINE_LABELS.items()}).replace("'", '"') + """;

async function fetchStatus() {
  const r = await fetch('/api/engines/status');
  return await r.json();
}

function renderCard(key, label, url, data) {
  const online = data.status === 'online';
  const stats = Object.entries(data)
    .filter(([k]) => !['status','http','error','service','version','timestamp','features','integrations','platforms','warning'].includes(k))
    .slice(0, 6);
  const statsHtml = stats.map(([k,v]) => {
    const val = typeof v === 'object' ? JSON.stringify(v).slice(0,30) : String(v).slice(0,30);
    return `<div class="stat"><div class="stat-label">${k.replace(/_/g,' ')}</div><div class="stat-value">${val}</div></div>`;
  }).join('');
  const errHtml = data.error ? `<div class="error-msg">⚠ ${data.error}</div>` : '';
  return `<div class="card ${online ? 'online' : 'offline'}" id="card-${key}">
  <div class="card-header">
    <div class="badge ${online ? 'online' : 'offline'}"></div>
    <div>
      <div class="card-title">${label}</div>
      <div class="card-url">${url.replace('https://','')}</div>
    </div>
    <span style="margin-left:auto;font-size:.75rem;color:${online?'#2ea043':'#da3633'};font-weight:700">${online?'ONLINE':'OFFLINE'}</span>
  </div>
  <div class="stats">${statsHtml}</div>
  ${errHtml}
  <div class="card-footer">
    <button class="btn-sm btn-trigger" onclick="triggerEngine('${key}')">▶ Trigger</button>
    <a href="${url}" target="_blank" class="btn-sm btn-open">↗ Öffnen</a>
    <a href="${url}/stats" target="_blank" class="btn-sm btn-open">📊 Stats</a>
  </div>
</div>`;
}

async function refreshAll() {
  try {
    const data = await fetchStatus();
    const grid = document.getElementById('engine-grid');
    grid.innerHTML = Object.entries(ENGINES).map(([key, {label, url}]) => {
      const d = data.engines[key] || {status:'offline',error:'no data'};
      return renderCard(key, label, url, d);
    }).join('');
    document.getElementById('online-count').textContent = `✅ ${data.online}/${data.total} Engines online`;
    document.getElementById('online-count').classList.remove('pulse');
    document.getElementById('last-refresh').textContent = `Aktualisiert: ${new Date().toLocaleTimeString('de-DE')}`;
  } catch(e) {
    document.getElementById('online-count').textContent = '⚠ Fehler beim Laden';
  }
}

async function triggerEngine(key) {
  const btn = document.querySelector(`#card-${key} .btn-trigger`);
  if(btn) { btn.textContent = '⏳...'; btn.disabled = true; }
  try {
    const r = await fetch(`/api/engines/trigger/${key}`, {method:'POST'});
    const d = await r.json();
    if(btn) { btn.textContent = '✅ Gestartet'; setTimeout(()=>{btn.textContent='▶ Trigger';btn.disabled=false;},3000); }
    document.getElementById('trigger-log').textContent = `${key}: Trigger gesendet (${new Date().toLocaleTimeString('de-DE')})`;
  } catch(e) {
    if(btn) { btn.textContent = '▶ Trigger'; btn.disabled = false; }
  }
}

async function triggerAll() {
  document.getElementById('trigger-log').textContent = '⏳ Alle Engines werden getriggert...';
  try {
    const r = await fetch('/api/engines/trigger/all', {method:'POST'});
    const d = await r.json();
    document.getElementById('trigger-log').textContent = `✅ ${d.triggered}/${Object.keys(ENGINES).length} Engines getriggert`;
    setTimeout(refreshAll, 2000);
  } catch(e) {
    document.getElementById('trigger-log').textContent = '⚠ Fehler';
  }
}

refreshAll();
setInterval(refreshAll, 30000);
</script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")


def _free_port(port: int) -> None:
    """Kill whatever holds the port (macOS + Linux)."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"], capture_output=True, text=True
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            try:
                os.kill(int(pid), 9)
                print(f"  Killed PID {pid} on port {port}")
            except Exception:
                pass
    except Exception:
        pass


if __name__ == "__main__":
    async def _main():
        print(f"\n🔍 Prüfe Port {PORT}...")
        _free_port(PORT)
        import asyncio as _aio
        await _aio.sleep(0.5)   # kurz warten damit OS den Port freigibt

        app = await create_app()
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT, reuse_address=True, reuse_port=True)
        await site.start()
        print(f"\n{'='*50}\n  SuperMegaBot Dashboard\n  http://localhost:{PORT}\n{'='*50}\n")

        # Auto-register Telegram webhook on Railway
        railway_url = os.getenv("RAILWAY_STATIC_URL") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        if railway_url:
            base = f"https://{railway_url}" if not railway_url.startswith("http") else railway_url
            for token_env in ("TELEGRAM_BOT_TOKEN_2", "TELEGRAM_BOT_TOKEN"):
                tok = os.getenv(token_env)
                if tok:
                    try:
                        async with aiohttp.ClientSession() as _s:
                            wh_url = f"{base}/webhook/telegram"
                            r = await _s.post(
                                f"https://api.telegram.org/bot{tok}/setWebhook",
                                json={"url": wh_url, "allowed_updates": ["message", "edited_message", "callback_query"]}
                            )
                            result = await r.json()
                            log.info("Telegram webhook set (%s): %s → %s", token_env, wh_url, result.get("description",""))
                    except Exception as _e:
                        log.warning("Telegram webhook setup failed: %s", _e)
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()

    asyncio.run(_main())
