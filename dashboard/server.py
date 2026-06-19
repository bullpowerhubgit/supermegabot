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
        shutil.copy2(BASE_DIR / ".env", backup_dir / "supermegabot.env")
        shutil.copy2(DATA_DIR / "memory.db", backup_dir / "memory.db")
        return web.json_response({"ok": True, "path": str(backup_dir)})
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
    result = {
        "status": "ok",
        "service": "supermegabot-dashboard",
        "port": PORT,
        "uptime_seconds": round(time.time() - _SERVER_START_TIME, 1),
        "started_at": datetime.utcfromtimestamp(_SERVER_START_TIME).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "shopify_domain": os.getenv("SHOPIFY_SHOP_DOMAIN", ""),
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
            "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
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
        "api_key_configured": bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")),
        "monitoring": True,
        "alerts_enabled": bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),
    })


async def handle_ai_status(req):
    """AI integrations status."""
    anthropic_ok = bool(os.getenv("ANTHROPIC_API_KEY"))
    openai_ok = bool(os.getenv("OPENAI_API_KEY"))
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
        "openai": {"configured": openai_ok, "model": os.getenv("OPENAI_MODEL", "gpt-4o")},
        "ollama": {"online": ollama_ok, "host": os.getenv("OLLAMA_HOST", "http://localhost:11434"), "model": os.getenv("OLLAMA_MODEL", "llama3.2")},
        "gemini": {"configured": bool(os.getenv("GEMINI_API_KEY"))},
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
            "OPENAI_API_KEY":            bool(os.getenv("OPENAI_API_KEY")),
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
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "PERPLEXITY_API_KEY",
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
    "OPENAI_API_KEY":        lambda v: v.startswith("sk-"),
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
        if key == "OPENAI_API_KEY":
            async with session.get(
                "https://api.openai.com/v1/models",
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
    """Manually trigger a specific automation task."""
    try:
        data = await req.json()
        task_name = data.get("task", "")
        from core.automation_scheduler import get_scheduler
        sched = get_scheduler()
        result = await sched.run_now(task_name)
        return web.json_response({"ok": True, "result": result})
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
        from modules.digistore24_automation import ping, get_sales_stats, get_products, setup_ipn
        ok = await ping()
        stats = await get_sales_stats() if ok else {}
        products = await get_products() if ok else []
        ipn_info = await setup_ipn()
        return web.json_response({
            "ok": ok,
            "stats": stats,
            "product_count": len(products),
            "ipn_url": ipn_info["ipn_url"],
            "ipn_setup_needed": True,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


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
        from modules.mailchimp_automation import ping, get_lists
        ok, account = await ping()
        lists = await get_lists() if ok else []
        return web.json_response({"ok": ok, "account": account, "lists": lists})
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
    mc_server = os.getenv("MAILCHIMP_SERVER_PREFIX", "us1")
    if not mc_key:
        return web.json_response({"ok": False, "error": "MAILCHIMP_API_KEY not set"})
    # auto-detect server prefix from key suffix (e.g. key ending in -us17)
    if "-" in mc_key:
        mc_server = mc_key.split("-")[-1]

    base_url = f"https://{mc_server}.api.mailchimp.com/3.0"
    headers = {"Authorization": f"Bearer {mc_key}", "Content-Type": "application/json"}

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

        log.info("Mailchimp campaign created: %s subject=%s list=%s", campaign_id, subject, list_id)
        return web.json_response({
            "ok": True,
            "campaign_id": campaign_id,
            "list_id": list_id,
            "list_name": list_name,
            "subject": subject,
            "status": campaign.get("status"),
            "note": "Campaign created. POST to /api/mailchimp/send with campaign_id to send.",
        })
    except Exception as e:
        log.error("Mailchimp campaign error: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_mailchimp_send(req):
    """POST /api/mailchimp/send — send a prepared Mailchimp campaign."""
    try:
        body = await req.json()
        campaign_id = body.get("campaign_id", "")
        if not campaign_id:
            return web.json_response({"ok": False, "error": "campaign_id required"})

        mc_key = os.getenv("MAILCHIMP_API_KEY", "")
        mc_server = os.getenv("MAILCHIMP_SERVER_PREFIX", "us1")
        if not mc_key:
            return web.json_response({"ok": False, "error": "MAILCHIMP_API_KEY not set"})
        if "-" in mc_key:
            mc_server = mc_key.split("-")[-1]

        base_url = f"https://{mc_server}.api.mailchimp.com/3.0"
        headers = {"Authorization": f"Bearer {mc_key}", "Content-Type": "application/json"}

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


async def handle_etsy_status(req):
    try:
        from modules.ecommerce_connectors import EtsyConnector
        etsy = EtsyConnector()
        ok, info = await etsy.ping()
        stats = await etsy.get_stats() if ok else {}
        return web.json_response({"ok": ok, "info": info, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_gumroad_status(req):
    try:
        from modules.ecommerce_connectors import GumroadConnector
        gum = GumroadConnector()
        ok, info = await gum.ping()
        stats = await gum.get_stats() if ok else {}
        return web.json_response({"ok": ok, "info": info, **stats})
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

_SITEMAPS = [
    "https://bullpowerhubgit.github.io/bullpower-lead/sitemap.xml",
    "https://bullpowerhubgit.github.io/shopify-suite-landing/sitemap.xml",
    "https://cognitive-symphony-ds24.netlify.app/sitemap.xml",
    "https://creatorstudio-pro.netlify.app/sitemap.xml",
    "https://digistore24-automation-suite.netlify.app/sitemap.xml",
    "https://bullpowerhubgit.github.io/bullpower-lead/sitemap.xml",
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


async def handle_shopify_order_webhook_route(req):
    """Shopify Order Webhook — sendet Telegram-Alarm bei neuer Bestellung."""
    try:
        data = await req.json()
        from modules.shopify_automation import handle_shopify_order_webhook
        await handle_shopify_order_webhook(data)
        return web.Response(status=200)
    except Exception as e:
        log.error("Shopify order webhook error: %s", e)
        return web.Response(status=200)


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
        from modules.b2b_pipeline import get_pipeline_stats
        stats = await get_pipeline_stats()
        return web.json_response({"ok": True, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_pipeline_leads(req):
    try:
        from modules.b2b_pipeline import get_pipeline_leads
        stage = req.rel_url.query.get("stage")
        try:
            limit = int(req.rel_url.query.get("limit", "50"))
        except (ValueError, TypeError):
            limit = 50
        leads = await get_pipeline_leads(stage=stage, limit=limit)
        return web.json_response({"ok": True, "leads": leads, "count": len(leads)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_lead_add(req):
    try:
        from modules.b2b_pipeline import add_lead
        data = await req.json()
        lead = await add_lead(
            email=data.get("email", ""),
            name=data.get("name", ""),
            company=data.get("company", ""),
            website=data.get("website", ""),
            niche=data.get("niche", ""),
            source=data.get("source", "manual_import"),
            score=int(data.get("score", 0)),
            notes=data.get("notes", ""),
        )
        return web.json_response({"ok": True, "lead": lead})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_lead_update(req):
    try:
        from modules.b2b_pipeline import update_lead_stage
        data = await req.json()
        lead_id = int(data.get("id", 0))
        stage   = data.get("stage", "")
        notes   = data.get("notes", "")
        if not lead_id or not stage:
            return web.json_response({"ok": False, "error": "id and stage required"}, status=400)
        result = await update_lead_stage(lead_id, stage, notes)
        return web.json_response({"ok": True, "lead": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_prospecting_run(req):
    try:
        from modules.b2b_pipeline import run_daily_prospecting
        data = {}
        try:
            data = await req.json()
        except Exception:
            pass
        result = await run_daily_prospecting()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_outreach_send(req):
    try:
        from modules.b2b_pipeline import send_outreach_email
        data = await req.json()
        lead_id = int(data.get("lead_id", 0))
        if not lead_id:
            return web.json_response({"ok": False, "error": "lead_id required"}, status=400)
        success = await send_outreach_email(lead_id)
        return web.json_response({"ok": success})
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
    app.router.add_get("/api/gmc", handle_gmc)

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
    app.router.add_get("/api/mailchimp/status",       handle_mailchimp_status)
    app.router.add_post("/api/mailchimp/sync",        handle_mailchimp_sync)
    app.router.add_post("/api/mailchimp/campaign",    handle_mailchimp_campaign)
    app.router.add_post("/api/mailchimp/send",        handle_mailchimp_send)
    app.router.add_post("/api/memory/save",           handle_memory_save)
    app.router.add_post("/api/notes/save",            handle_notes_save_alias)

    # ── Printify ──────────────────────────────────────────────────────────────
    app.router.add_get("/api/printify/status",        handle_printify_status)
    app.router.add_post("/api/printify/autofulfill",  handle_printify_autofulfill)

    # ── Etsy + Gumroad ────────────────────────────────────────────────────────
    app.router.add_get("/api/etsy/status",            handle_etsy_status)
    app.router.add_get("/api/gumroad/status",         handle_gumroad_status)
    app.router.add_post("/api/gumroad/webhook",       handle_gumroad_webhook)

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
    app.router.add_get("/api/klaviyo/status",         handle_klaviyo_status)
    app.router.add_get("/api/klaviyo/lists",          handle_klaviyo_lists)
    app.router.add_post("/api/klaviyo/sync",          handle_klaviyo_sync)
    app.router.add_post("/api/klaviyo/campaign",      handle_klaviyo_campaign)

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
    app.router.add_post("/api/shopify/order-webhook", handle_shopify_order_webhook_route)
    app.router.add_get("/api/shopify/orders",         handle_shopify_orders)
    app.router.add_get("/api/shopify/products",       handle_shopify_products)
    app.router.add_get("/api/shopify/revenue",        handle_shopify_revenue)
    app.router.add_post("/webhook/telegram",          handle_telegram_webhook)
    app.router.add_post("/api/webhook/telegram",      handle_telegram_webhook)
    app.router.add_post("/api/telegram/webhook",      handle_telegram_webhook)
    app.router.add_get("/api/telegram/setup",         handle_telegram_setup)
    app.router.add_get("/checkout",                   handle_checkout_page)
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
    app.router.add_get("/api/facebook/refresh",       handle_facebook_refresh)
    app.router.add_get("/api/facebook/callback",      handle_facebook_callback)
    app.router.add_get("/api/facebook/status",        handle_facebook_status)
    app.router.add_post("/api/brutus/run",            handle_brutus_run)
    app.router.add_get("/api/brutus/status",          handle_brutus_status)
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

    # ── TikTok Shop ──────────────────────────────────────────────────────────
    app.router.add_post("/api/tiktok/sync-products",     handle_tiktok_sync_products)
    app.router.add_get( "/api/tiktok/orders",            handle_tiktok_orders)
    app.router.add_get( "/api/tiktok/analytics",         handle_tiktok_analytics)
    app.router.add_get( "/api/tiktok/combined-revenue",  handle_tiktok_combined_revenue)
    app.router.add_post("/api/tiktok/promotion",         handle_tiktok_promotion)
    app.router.add_get( "/api/tiktok/research/status",   handle_tiktok_research_status)
    app.router.add_get( "/api/tiktok/research/ads",      handle_tiktok_research_ads)

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
                async with session.get("http://localhost:8888/api/telegram/setup") as r:
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
        results = {"stripe": {}, "shopify": {}, "ds24": {}, "total_today_eur": 0.0}
        today = datetime.utcnow().date().isoformat()

        async with _aiohttp.ClientSession() as session:
            # Stripe balance
            stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
            if stripe_key:
                try:
                    async with session.get(
                        "https://api.stripe.com/v1/balance",
                        headers={"Authorization": f"Bearer {stripe_key}"},
                        timeout=_aiohttp.ClientTimeout(total=8)
                    ) as r:
                        d = await r.json()
                    avail = sum(b["amount"] for b in d.get("available", [])) / 100
                    pend  = sum(b["amount"] for b in d.get("pending", []))   / 100
                    results["stripe"] = {"available_eur": avail, "pending_eur": pend, "ok": True}
                    results["total_today_eur"] += avail
                except Exception as e:
                    results["stripe"] = {"ok": False, "error": str(e)}

            # Shopify orders today
            shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
            shopify_token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
            shopify_ver    = os.getenv("SHOPIFY_API_VERSION", "2024-01")
            if shopify_domain and shopify_token:
                try:
                    url = f"https://{shopify_domain}/admin/api/{shopify_ver}/orders.json?status=any&created_at_min={today}T00:00:00Z&limit=50"
                    async with session.get(url, headers={"X-Shopify-Access-Token": shopify_token},
                                           timeout=_aiohttp.ClientTimeout(total=8)) as r:
                        d = await r.json()
                    orders = d.get("orders", [])
                    revenue = sum(float(o.get("total_price", 0)) for o in orders)
                    results["shopify"] = {"orders_today": len(orders), "revenue_today_eur": revenue, "ok": True}
                    results["total_today_eur"] += revenue
                except Exception as e:
                    results["shopify"] = {"ok": False, "error": str(e)}

            # DS24 stats
            try:
                from modules.digistore24_automation import get_sales_stats
                stats = await get_sales_stats()
                results["ds24"] = {"ok": True, "stats": stats}
                results["total_today_eur"] += float(stats.get("today", 0))
            except Exception as e:
                results["ds24"] = {"ok": False, "error": str(e)}

        results["timestamp"] = datetime.utcnow().isoformat() + "Z"
        return web.json_response(results)
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
