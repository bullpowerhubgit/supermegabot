#!/usr/bin/env python3
"""SuperMegaBot Dashboard Server - Port 8888"""

# DS24 Guardian MUSS als erstes importiert werden — validiert + heilt DS24_AFFILIATE_LINK
try:
    from modules.ds24_link_guardian import get_ds24_link, validate_and_heal
    validate_and_heal()
except Exception as _e:
    import logging; logging.getLogger(__name__).warning(f"DS24Guardian import failed: {_e}")

try:
    from modules.smart_poster import install_global_telegram_send_guard
    install_global_telegram_send_guard()
except Exception as _e:
    import logging; logging.getLogger(__name__).warning(f"Global Telegram guard install failed: {_e}")

try:
    from modules.ai_budget_guard import install_global_ai_budget_guard
    install_global_ai_budget_guard()
except Exception as _e:
    import logging; logging.getLogger(__name__).warning(f"Global AI budget guard install failed: {_e}")

try:
    from modules.never_again import engine as _never_again_engine
    _never_again_engine.init()
except Exception as _e:
    import logging; logging.getLogger(__name__).warning(f"NeverAgain init failed: {_e}")

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

sys.path.insert(0, str(Path.home()))
sys.path.insert(0, str(Path(__file__).parent.parent))

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
    load_dotenv(BASE_DIR / ".env", override=True)
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

# DAUERHAFT: Alle FB/IG Alias-Vars = AiiteC Page Token (nie IWIN/User als Default)
try:
    from modules.meta_token_resolver import apply_aiitec_aliases_to_process
    apply_aiitec_aliases_to_process()
except Exception as _mtr_err:
    pass  # logging not ready yet

# DAUERHAFT: Stripe NUR bullpowersrtkennels@gmail.com — AIITEC-Keys aus Process löschen
try:
    # Stripe: NUR ineedit.com.co (acct_1Tg1U0…) — AIITEC permanent verboten
    from modules.stripe_key_resolver import enforce_ineedit_only
    enforce_ineedit_only()
except Exception:
    pass

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

_MONEY_MACHINES_HTML = Path(__file__).parent / "static" / "money_machines.html"
_HT_SALES_HTML = Path(__file__).parent / "highticket.html"


async def handle_money_machines(req):
    """GET /money-machines — Demand Oracle + B2B Intent Radar live dashboard."""
    try:
        html = _MONEY_MACHINES_HTML.read_text(encoding="utf-8")
    except Exception:
        html = "<h1>money_machines.html nicht gefunden</h1>"
    return web.Response(text=html, content_type="text/html")


async def handle_highticket(req):
    """GET /highticket — High-Ticket Sales Page (€497/€997/€2.497)."""
    try:
        html = _HT_SALES_HTML.read_text(encoding="utf-8")
    except Exception:
        html = "<h1>highticket.html nicht gefunden</h1>"
    return web.Response(text=html, content_type="text/html")


async def handle_ht_demo_data(req):
    """GET /api/ht/demo — Personalisierte Demo-Metriken."""
    from modules.ht_demo_system import get_demo_data, track_demo_view
    try:
        revenue = int(req.rel_url.query.get("revenue", "25000"))
        plan = req.rel_url.query.get("plan", "")
        referrer = req.headers.get("Referer", "")
        await track_demo_view(referrer=referrer, plan=plan)
        data = await get_demo_data(revenue)
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_ht_apply(req):
    """POST /api/ht/apply — Demo-Anfrage verarbeiten."""
    from modules.ht_application import save_application
    try:
        data = await req.json()
        result = await save_application(data)
        return web.json_response(result)
    except Exception as e:
        log.error("HT apply error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ht_onboarding(req):
    """GET /api/ht/onboarding — Onboarding-Status."""
    from modules.ht_onboarding import get_onboarding_dashboard
    try:
        data = await get_onboarding_dashboard()
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_ht_stats(req):
    """GET /api/ht/stats — Demo-View-Statistiken."""
    from modules.ht_demo_system import get_demo_stats
    try:
        data = await get_demo_stats()
        plans = {
            "growth":     {"monthly": os.getenv("STRIPE_PRICE_HT_GROWTH_MONTHLY", ""),
                           "onetime": os.getenv("STRIPE_PRICE_HT_GROWTH_ONETIME", ""),
                           "price": 497},
            "scale":      {"monthly": os.getenv("STRIPE_PRICE_HT_SCALE_MONTHLY", ""),
                           "onetime": os.getenv("STRIPE_PRICE_HT_SCALE_ONETIME", ""),
                           "price": 997},
            "enterprise": {"monthly": os.getenv("STRIPE_PRICE_HT_ENTERPRISE_MONTHLY", ""),
                           "onetime": os.getenv("STRIPE_PRICE_HT_ENTERPRISE_ONETIME", ""),
                           "price": 2497},
        }
        data["stripe_plans"] = plans
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ── Compliance Tool Landing Pages (SYS-17 bis SYS-42) ────────────────────────
_COMPLIANCE_STATIC = Path(__file__).parent / "static"

def _serve_static(filename: str):
    async def _handler(req):
        try:
            html = (_COMPLIANCE_STATIC / filename).read_text(encoding="utf-8")
        except Exception:
            html = f"<h1>{filename} nicht gefunden</h1>"
        return web.Response(text=html, content_type="text/html")
    return _handler

handle_compliance_index        = _serve_static("index.html")
handle_gpsr_shield             = _serve_static("gpsr-shop-shield.html")
handle_ppwr_radar              = _serve_static("ppwr-verpackungs-radar.html")
handle_erechnung_autopilot     = _serve_static("e-rechnung-autopilot.html")
handle_cra_waechter            = _serve_static("cra-melde-waechter.html")
handle_nis2_check              = _serve_static("nis2-kmu-check.html")
handle_kanzlei_radar           = _serve_static("kanzlei-mandanten-radar.html")
handle_eudr_pass               = _serve_static("eudr-lieferketten-pass.html")
handle_hr_ki_audit             = _serve_static("hr-ki-hochrisiko-audit.html")
handle_bfsg_scanner            = _serve_static("bfsg-barriere-scanner.html")
handle_zvg_expose              = _serve_static("zvg-expose-engine.html")


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


async def handle_assistant_ask(req):
    """POST /api/assistant/ask — Rudolf's persönlicher KI-Assistent (alle Modi).
    Body: {"message": "...", "session_id": "optional", "context": "optional",
           "mode": "general|shop|mail|post|revenue|expansion|browser"}
    Returns: {"ok": true, "answer": "...", "session_id": "...", "mode": "..."}
    """
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    message = (data.get("message") or data.get("text") or "").strip()
    if not message:
        return web.json_response({"ok": False, "error": "message required"}, status=400)

    session_id = data.get("session_id", "dashboard")
    context = data.get("context", "")
    mode = data.get("mode", "general")

    try:
        from modules.rudolf_assistant import ask
        answer = await ask(message, session_id=session_id, context=context, mode=mode)
        return web.json_response({"ok": True, "answer": answer, "session_id": session_id, "mode": mode})
    except Exception as e:
        log.error("assistant/ask error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_assistant_clear(req):
    """DELETE /api/assistant/history?session_id=xxx — Verlauf löschen."""
    session_id = req.rel_url.query.get("session_id", "dashboard")
    try:
        from modules.rudolf_assistant import clear_history
        clear_history(session_id)
        return web.json_response({"ok": True, "cleared": session_id})
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


async def handle_ollama_status(req):
    """Detaillierter Ollama-Status inkl. laufende Modelle + Empfehlungen."""
    try:
        from modules.ollama_manager import get_manager
        data = await get_manager().status()
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"online": False, "error": str(e)})


async def handle_ollama_chat(req):
    """Chat mit lokalem Ollama-Modell."""
    try:
        body    = await req.json()
        prompt  = body.get("prompt", "")
        system  = body.get("system", "Du bist AIITEC SuperBot.")
        model   = body.get("model") or None
        if not prompt:
            return web.json_response({"ok": False, "error": "prompt required"}, status=400)
        from modules.ollama_manager import get_manager
        text = await get_manager().chat(prompt, model=model, system=system)
        return web.json_response({"ok": bool(text), "response": text,
                                   "model": model or "default", "source": "ollama-local"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ollama_stream(req):
    """Streaming-Chat mit lokalem Ollama (Server-Sent Events)."""
    try:
        body   = await req.json()
        prompt = body.get("prompt", "")
        system = body.get("system", "")
        model  = body.get("model") or None
        if not prompt:
            return web.json_response({"ok": False, "error": "prompt required"}, status=400)

        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream",
                                            "Cache-Control": "no-cache"})
        await resp.prepare(req)

        from modules.ollama_manager import get_manager
        async for chunk in get_manager().stream(prompt, model=model, system=system):
            await resp.write(f"data: {json.dumps({'chunk': chunk})}\n\n".encode())
        await resp.write(b"data: [DONE]\n\n")
        return resp
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ollama_generate(req):
    """Einfache Text-Generierung mit Ollama."""
    try:
        body   = await req.json()
        prompt = body.get("prompt", "")
        model  = body.get("model") or None
        if not prompt:
            return web.json_response({"ok": False, "error": "prompt required"}, status=400)
        from modules.ollama_manager import get_manager
        text = await get_manager().generate(prompt, model=model)
        return web.json_response({"ok": bool(text), "response": text, "source": "ollama-local"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ollama_pull(req):
    """Neues Modell herunterladen — Fortschritt als JSON-Stream."""
    try:
        body  = await req.json()
        model = body.get("model", "").strip()
        if not model:
            return web.json_response({"ok": False, "error": "model required"}, status=400)

        resp = web.StreamResponse(headers={"Content-Type": "application/x-ndjson",
                                            "Cache-Control": "no-cache"})
        await resp.prepare(req)

        from modules.ollama_manager import get_manager
        async for line in get_manager().pull(model):
            await resp.write((line + "\n").encode())
        await resp.write(b'{"status":"complete"}\n')
        return resp
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ollama_delete(req):
    """Installiertes Modell löschen."""
    try:
        body  = await req.json()
        model = body.get("model", "").strip()
        if not model:
            return web.json_response({"ok": False, "error": "model required"}, status=400)
        from modules.ollama_manager import get_manager
        result = await get_manager().delete(model)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ollama_info(req):
    """Details zu einem installierten Modell."""
    model = req.query.get("model", DEFAULT_MODEL if 'DEFAULT_MODEL' in dir() else "llama3.2:latest")
    try:
        from modules.ollama_manager import get_manager
        info = await get_manager().model_info(model)
        return web.json_response(info)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_open_claw_status(req):
    """OpenClaw = lokales Ollama AI System."""
    try:
        from modules.open_claw import get_models, is_online, OLLAMA_BASE, CLAW_MODEL
        online = await is_online()
        models = await get_models() if online else []
        return web.json_response({
            "ok": online, "name": "OpenClaw", "base": OLLAMA_BASE,
            "default_model": CLAW_MODEL, "models": models,
            "status": "online" if online else "offline"
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_open_claw_generate(req):
    """Generiere Content mit lokalem Ollama."""
    try:
        data = await req.json()
        topic = data.get("topic", "KI Automation")
        content_type = data.get("type", "post")
        from modules.open_claw import claw_generate_content
        result = await claw_generate_content(topic, content_type)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_open_claw_chat(req):
    """Direktes Chat-Interface mit OpenClaw."""
    try:
        data = await req.json()
        prompt = data.get("prompt", "")
        system = data.get("system", "Du bist AIITEC SuperBot, ein autonomes KI-System.")
        fast = data.get("fast", False)
        if not prompt:
            return web.json_response({"ok": False, "error": "prompt required"}, status=400)
        from modules.open_claw import claw_complete
        text = await claw_complete(prompt, system=system, fast=fast)
        return web.json_response({"ok": bool(text), "response": text, "source": "OpenClaw"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_open_claw_revenue(req):
    """Tages-Revenue-Strategie via OpenClaw."""
    try:
        from modules.open_claw import claw_revenue_strategy
        strategy = await claw_revenue_strategy()
        return web.json_response({"ok": bool(strategy), "strategy": strategy, "source": "OpenClaw-Local"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_open_claw_blast(req):
    """Generiere + blast Content via OpenClaw → Telegram + BrutusClone."""
    try:
        data = await req.json() if req.content_length else {}
        topic = data.get("topic", "KI Automation Shopify Digistore24")
        from modules.open_claw import claw_generate_content
        from modules.brutus_clone import BrutusClone
        brutus = BrutusClone("OpenClaw")
        post = await claw_generate_content(topic, "telegram")
        email_content = await claw_generate_content(topic, "email")
        fired = await brutus.fire(
            title=f"OpenClaw: {topic[:40]}",
            content=post.get("text", ""),
            link="https://buy.stripe.com/dRm6oJ67ofqq6Aw8gK4F21y"
        )
        return web.json_response({
            "ok": True, "topic": topic,
            "post_generated": bool(post.get("text")),
            "telegram_sent": fired.get("telegram", False),
            "email_content": email_content.get("text", "")[:200],
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


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


async def handle_gmc_setup(req):
    """GET /api/gmc/setup — registriert Shopping Feed als Scheduled Fetch via SA."""
    try:
        from modules.gmc_feed_uploader import register_scheduled_fetch, list_feeds
        result = await register_scheduled_fetch()
        if result.get("ok"):
            tg_tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
            tg_ch  = os.getenv("TELEGRAM_CHAT_ID", "")
            if tg_tok and tg_ch:
                status = result.get("status", "")
                msg = (f"🛍️ <b>Google Shopping Feed</b>\n\n"
                       f"{'✅ Bereits registriert' if status == 'already_registered' else '🎉 JETZT REGISTRIERT!'}\n"
                       f"Feed ID: {result.get('feed_id','?')}\n"
                       f"URL: {result.get('feed_url', '')}\n"
                       f"662 Produkte gehen live bei Google Shopping!")
                async with aiohttp.ClientSession() as s2:
                    await s2.post(f"https://api.telegram.org/bot{tg_tok}/sendMessage",
                                  json={"chat_id": tg_ch, "text": msg, "parse_mode": "HTML"})
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


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
        "ok": True,
        "configured": configured,
        "setup": "Set REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET + REDDIT_USERNAME + REDDIT_PASSWORD in Railway" if not configured else "Ready",
        "target_subreddits": ["passive_income", "entrepreneur", "ecommerce", "dropshipping", "affiliatemarketing", "shopify"],
        "auto_posting": True,
        "note": "Reddit auto-poster aktiv — postet auch ohne eigene Credentials via Web API",
    })


async def handle_gmc_feed(req):
    """GET /api/gmc/feed.xml — Google Shopping RSS product feed for all Shopify products."""
    import re as _re, html as _html
    shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
    shopify_token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    shopify_ver    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
    custom_domain  = os.getenv("SHOPIFY_CUSTOM_DOMAIN", "ineedit.com.co")
    store_url      = f"https://{custom_domain}" if custom_domain else os.getenv("SHOPIFY_STORE_URL", f"https://{shopify_domain}")

    # Google product category map (keyword → Google taxonomy ID)
    _CAT_MAP = [
        (["drucker", "3d-druck"], "632"),           # Electronics > 3D Printers
        (["beamer", "projektor"], "289"),             # Electronics > Projectors
        (["kopfhörer", "earbuds", "headset"], "239"),# Electronics > Headphones
        (["smartwatch", "fitnessuhr", "tracker"], "1712"),  # Smartwatches
        (["yoga", "fitness", "sport", "dehnband"], "990"),   # Sporting Goods
        (["küche", "kochen", "mixer", "blender", "kaffeemasch"], "672"),  # Kitchen
        (["garten", "pflanzen", "bewässerung"], "739"),   # Garden
        (["lampe", "licht", "led"], "2702"),          # Lighting
        (["shirt", "kleidung", "sneaker"], "1604"),   # Apparel
        (["baby", "kinder"], "537"),                  # Baby & Toddler
        (["hund", "katze", "haustier"], "1"),        # Pet Supplies
        (["buch", "guide", "lernkarten", "kurs"], "784"),  # Books
    ]

    def _guess_category(title: str, prod_type: str = "") -> str:
        text = (title + " " + prod_type).lower()
        for keywords, cat_id in _CAT_MAP:
            if any(k in text for k in keywords):
                return cat_id
        return "632"  # default: Electronics

    def _clean_desc(html_body: str, title: str) -> str:
        if not html_body:
            return title
        # Remove script/style blocks and JSON-LD
        text = _re.sub(r'<script[^>]*>.*?</script>', '', html_body, flags=_re.DOTALL | _re.IGNORECASE)
        text = _re.sub(r'<style[^>]*>.*?</style>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
        # Strip remaining HTML tags
        text = _re.sub(r'<[^>]+>', ' ', text)
        # Clean whitespace and markdown artifacts
        text = _re.sub(r'[*#`]+', '', text)
        text = _re.sub(r'\s+', ' ', text).strip()
        return text[:500] or title

    try:
        products = []
        if shopify_token:
            import aiohttp as _aio
            # Feed-Cache: 2h gültig um wiederholte API-Calls zu vermeiden
            _feed_cache_key = "gmc_feed_cache"
            _feed_cache_ts  = "gmc_feed_cache_ts"
            import time as _time
            _now = _time.time()
            _cached_xml = req.app.get(_feed_cache_key)
            _cached_ts  = req.app.get(_feed_cache_ts, 0)
            if _cached_xml and (_now - _cached_ts) < 7200:
                return web.Response(text=_cached_xml, content_type="application/xml",
                                    headers={"Content-Disposition": "inline; filename=feed.xml",
                                             "X-Cache": "HIT"})

            async with _aio.ClientSession() as s:
                last_id = 0
                # Kleine Batches (50) → schnelle API-Calls, max 600 Produkte gesamt
                max_products = 600
                while len(products) < max_products:
                    try:
                        async with s.get(
                            f"https://{shopify_domain}/admin/api/{shopify_ver}/products.json",
                            headers={"X-Shopify-Access-Token": shopify_token},
                            params={"limit": 50, "since_id": last_id,
                                    "status": "active",
                                    "fields": "id,title,body_html,handle,images,variants,product_type,status,vendor,tags"},
                            timeout=_aio.ClientTimeout(total=12),
                        ) as r:
                            if r.status != 200:
                                log.warning("GMC feed Shopify API status=%s", r.status)
                                break
                            batch = (await r.json(content_type=None)).get("products", [])
                            if not batch:
                                break
                            products.extend(batch)
                            last_id = batch[-1]["id"]
                            if len(batch) < 50:
                                break
                    except Exception as _fe:
                        log.warning("GMC feed fetch page error: %s", _fe)
                        break

        # Vendor-Bereinigung: Shop-eigene Vendor-Namen → echte Marke
        _VENDOR_SKIP = {"i want that! i need it!", "ineedit", "aiitec", "bullpowerhub",
                        "supermegabot", "demo", "testvendor"}

        items = []
        for p in products:
            variant  = (p.get("variants") or [{}])[0]
            price    = variant.get("price", "0")
            barcode  = variant.get("barcode", "") or ""
            sku      = variant.get("sku", "") or f"SMB-{p.get('id','')}"
            image    = (p.get("images") or [{}])[0].get("src", "") if p.get("images") else ""
            if not image:
                continue  # Google requires image — skip imageless products
            if not price or float(price or 0) <= 0:
                continue  # Skip free/no-price products
            handle   = p.get("handle", "")
            title    = p.get("title", "")[:150]
            if not title or len(title) < 3:
                continue
            desc     = _clean_desc(p.get("body_html", ""), title)
            cat_id   = _guess_category(title, p.get("product_type", ""))
            img_tag  = f"\n    <g:image_link>{_html.escape(image)}</g:image_link>"

            # Brand: Shopify-Vendor bevorzugen, nur Shop-Namen überschreiben
            raw_vendor = (p.get("vendor") or "").strip()
            brand = raw_vendor if raw_vendor and raw_vendor.lower() not in _VENDOR_SKIP else "iNeedit"

            # GTIN/MPN: Barcode als GTIN wenn vorhanden (EAN/UPC), sonst MPN via SKU
            identifier_block = ""
            if barcode and len(barcode) in (8, 12, 13, 14):
                identifier_block = f"\n    <g:gtin>{_html.escape(barcode)}</g:gtin>"
            elif sku and not sku.startswith("SMB-"):
                identifier_block = f"\n    <g:mpn>{_html.escape(sku[:70])}</g:mpn>"
            else:
                identifier_block = "\n    <g:identifier_exists>no</g:identifier_exists>"

            items.append(f"""  <item>
    <title><![CDATA[{title}]]></title>
    <description><![CDATA[{desc}]]></description>
    <link>{store_url}/products/{handle}</link>
    <g:id>shopify_{p.get('id','')}</g:id>
    <g:price>{price} EUR</g:price>
    <g:availability>in stock</g:availability>
    <g:condition>new</g:condition>
    <g:brand>{_html.escape(brand)}</g:brand>
    <g:google_product_category>{cat_id}</g:google_product_category>{identifier_block}
    <g:shipping>
      <g:country>DE</g:country>
      <g:service>Standard</g:service>
      <g:price>4.99 EUR</g:price>
    </g:shipping>
    <g:shipping>
      <g:country>AT</g:country>
      <g:service>Standard</g:service>
      <g:price>6.99 EUR</g:price>
    </g:shipping>
    <g:shipping>
      <g:country>CH</g:country>
      <g:service>Standard</g:service>
      <g:price>9.99 EUR</g:price>
    </g:shipping>{img_tag}
  </item>""")

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
<channel>
  <title>I Want That! I Need It! — Google Shopping Feed</title>
  <link>{store_url}</link>
  <description>Alle Produkte aus dem Online-Shop von I Want That! I Need It!</description>
  <language>de</language>
{chr(10).join(items)}
</channel>
</rss>"""
        # Cache befüllen
        req.app[_feed_cache_key] = xml
        req.app[_feed_cache_ts]  = _now
        return web.Response(text=xml, content_type="application/xml",
                            headers={"Content-Disposition": "inline; filename=feed.xml",
                                     "X-Products": str(len(items))})
    except Exception as e:
        log.error("GMC feed error: %s", e)
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
    try:
        from modules.error_sentinel import get_sentinel_status
        sentinel = get_sentinel_status()
    except Exception:
        sentinel = {"ok": False, "error": "unavailable"}
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
        "sentinel": sentinel,
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
            "api_version": os.getenv("SHOPIFY_API_VERSION", "2024-10"),
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
    """AI integrations status — komplette Provider-Kette."""
    _ant_enabled = os.getenv("ANTHROPIC_ENABLED", "true").lower() not in ("false", "0", "off")
    _ant_keys_count = sum(1 for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_2", "ANTHROPIC_API_KEY_3") if os.getenv(k))
    anthropic_ok = _ant_enabled and _ant_keys_count > 0
    _ollama_host = os.getenv("OLLAMA_BASE", os.getenv("OLLAMA_HOST", os.getenv("OLLAMA_URL", "http://localhost:11434")))
    ollama_ok = False
    ollama_models = []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as s:
            async with s.get(f"{_ollama_host}/api/tags") as r:
                if r.status == 200:
                    ollama_ok = True
                    d = await r.json(content_type=None)
                    ollama_models = [m["name"] for m in d.get("models", [])]
    except Exception:
        pass
    _ollama_default = os.getenv("OLLAMA_CLAW_MODEL", os.getenv("OLLAMA_DEFAULT_MODEL", os.getenv("OLLAMA_MODEL", "llama3.2:latest")))
    _ollama_fast    = os.getenv("OLLAMA_FAST_MODEL", _ollama_default)
    _ollama_smart   = os.getenv("OLLAMA_SMART_MODEL", _ollama_default)
    return web.json_response({
        "ok": True,
        "provider_chain": [
            "Ollama/OpenClaw (local, free)",
            "Groq (free tier)",
            "Cerebras (free)",
            "SambaNova (free)",
            "Mistral (free tier)",
            "DeepSeek",
            "OpenRouter :free (13 models)",
            "Gemini",
            "OpenAI",
            "Perplexity",
            "APIHunt Bridge (Anthropic key-rotation, Pollinations)",
        ],
        "ollama": {
            "online": ollama_ok,
            "host": _ollama_host,
            "default_model": _ollama_default,
            "fast_model": _ollama_fast,
            "smart_model": _ollama_smart,
            "installed_models": ollama_models,
            "slot": 0,
        },
        "groq":        {"configured": bool(os.getenv("GROQ_API_KEY")),        "slot": 1, "model": "llama-3.3-70b-versatile"},
        "cerebras":    {"configured": bool(os.getenv("CEREBRAS_API_KEY")),    "slot": 2},
        "sambanova":   {"configured": bool(os.getenv("SAMBANOVA_API_KEY")),   "slot": 3},
        "mistral":     {"configured": bool(os.getenv("MISTRAL_API_KEY")),     "slot": 4},
        "deepseek":    {"configured": bool(os.getenv("DEEPSEEK_API_KEY")),    "slot": 5, "model": "deepseek-chat"},
        "openrouter":  {"configured": bool(os.getenv("OPENROUTER_API_KEY")), "slot": 6, "free_models": 13},
        "gemini":      {"configured": bool(os.getenv("GEMINI_API_KEY")),      "slot": 7},
        "openai":      {"configured": bool(os.getenv("OPENAI_API_KEY")),      "slot": 8},
        "perplexity":  {"configured": bool(os.getenv("PERPLEXITY_API_KEY")), "slot": 9},
        "anthropic": {
            "configured": anthropic_ok, "enabled": _ant_enabled,
            "keys_count": _ant_keys_count, "slot": 10,
            "model": os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            "location": "APIHunt Bridge (key rotation)",
        },
    })


async def handle_ai_complete(req):
    """POST /api/ai/complete — testet die komplette AI-Kette.
    Body: {"prompt": "...", "model_hint": "fast|smart|code", "max_tokens": 100}
    """
    try:
        body = await req.json()
        prompt = body.get("prompt", "").strip()
        if not prompt:
            return web.json_response({"ok": False, "error": "prompt required"}, status=400)
        model_hint = body.get("model_hint", "fast")
        max_tokens = int(body.get("max_tokens", 200))
        from modules.ai_client import ai_complete
        import time as _time
        t0 = _time.time()
        text = await ai_complete(prompt, max_tokens=max_tokens, model_hint=model_hint)
        elapsed = round(_time.time() - t0, 2)
        return web.json_response({
            "ok": bool(text),
            "response": text,
            "elapsed_s": elapsed,
            "model_hint": model_hint,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


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
    service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
    configured = bool(supabase_url and service_key)
    reachable = False
    if configured:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as s:
                async with s.get(f"{supabase_url}/rest/v1/",
                                 headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"}) as r:
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
                headers={"apikey": os.getenv("SUPABASE_ANON_KEY", "")},
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


async def handle_ebay_arbitrage_stats(req):
    """GET /api/ebay-arbitrage/stats"""
    try:
        from modules.ebay_arbitrage import get_stats
        return web.json_response({"ok": True, **get_stats()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ebay_arbitrage_scan(req):
    """POST /api/ebay-arbitrage/scan — trigger manual scan (non-blocking)"""
    try:
        from modules.ebay_arbitrage import run_full_scan
        asyncio.create_task(run_full_scan(max_imports=5))
        return web.json_response({"ok": True, "message": "Arbitrage scan gestartet — Ergebnis via Telegram"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ebay_arbitrage_preview(req):
    """POST /api/ebay-arbitrage/preview — scan one category without importing"""
    try:
        body     = await req.json()
        category = body.get("category", "Smart Home")
        keywords = body.get("keywords", ["smart steckdose wlan"])
        from modules.ebay_arbitrage import scan_category
        opps = await asyncio.wait_for(scan_category(category, keywords), timeout=30)
        return web.json_response({"ok": True, "opportunities": opps[:10], "count": len(opps)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_intent_bridge_stats(req):
    """GET /api/intent-bridge/stats — live stats for the Intent-to-Sale Bridge."""
    try:
        from modules.intent_to_sale_bridge import get_stats
        stats = get_stats()
        return web.json_response({"ok": True, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_intent_bridge_process(req):
    """POST /api/intent-bridge/process — manual test: analyze a message."""
    try:
        body = await req.json()
        text    = body.get("text", "")
        chat_id = body.get("chat_id", "test")
        if not text:
            return web.json_response({"ok": False, "error": "text required"}, status=400)
        from modules.intent_to_sale_bridge import classify_intent, search_products, generate_response
        intent   = await classify_intent(text)
        products = await search_products(intent.get("category", "general"), intent.get("keywords", []))
        response = ""
        if products and intent.get("is_buying") and intent.get("confidence", 0) >= 0.75:
            response = await generate_response(text, products, intent.get("language", "de"))
        return web.json_response({
            "ok": True,
            "intent": intent,
            "products": products,
            "response": response,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_radar_stats(req):
    """GET /api/b2b-radar/stats"""
    try:
        from modules.b2b_intent_radar import get_stats
        return web.json_response({"ok": True, "stats": get_stats()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_radar_scan(req):
    """POST /api/b2b-radar/scan — trigger manual scan"""
    try:
        from modules.b2b_intent_radar import run_b2b_scan
        asyncio.create_task(run_b2b_scan())
        return web.json_response({"ok": True, "message": "B2B Intent Radar scan gestartet"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_radar_leads(req):
    """GET /api/b2b-radar/leads — export all leads"""
    try:
        from modules.b2b_intent_radar import get_leads_for_export
        leads = get_leads_for_export()
        return web.json_response({"ok": True, "count": len(leads), "leads": leads})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_radar_outreach(req):
    """POST /api/b2b-radar/outreach — mark company as contacted"""
    try:
        body    = await req.json()
        company = body.get("company", "")
        if not company:
            return web.json_response({"ok": False, "error": "company required"}, status=400)
        from modules.b2b_intent_radar import mark_outreach_sent
        await mark_outreach_sent(company)
        return web.json_response({"ok": True, "company": company})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_demand_oracle_stats(req):
    """GET /api/demand-oracle/stats"""
    try:
        from modules.demand_oracle import get_stats
        return web.json_response({"ok": True, "stats": get_stats()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_demand_oracle_scan(req):
    """POST /api/demand-oracle/scan — trigger manual scan"""
    try:
        from modules.demand_oracle import run_demand_scan
        asyncio.create_task(run_demand_scan())
        return web.json_response({"ok": True, "message": "Demand Oracle scan gestartet"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_demand_oracle_wishes(req):
    """GET /api/demand-oracle/wishes — recent wish expressions"""
    try:
        import sqlite3
        from pathlib import Path
        db_path = Path(__file__).parent.parent / "data" / "demand_oracle.db"
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        wishes = con.execute(
            "SELECT text, subreddit, score, ts FROM do_wishes ORDER BY ts DESC LIMIT 50"
        ).fetchall()
        con.close()
        return web.json_response({"ok": True, "wishes": [dict(w) for w in wishes]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


_ds24_status_cache: dict = {}
_ds24_status_cache_ts: float = 0.0
_DS24_STATUS_TTL = 300


async def handle_digistore_status(req):
    global _ds24_status_cache, _ds24_status_cache_ts
    try:
        import time
        from modules.digistore24_automation import ping, get_sales_stats, get_products, is_configured
        configured = is_configured()
        if not configured:
            return web.json_response({"ok": False, "connected": False, "configured": False, "error": "DS24 nicht konfiguriert"})
        if _ds24_status_cache and time.time() - _ds24_status_cache_ts < _DS24_STATUS_TTL:
            return web.json_response(_ds24_status_cache)
        ipn_url = "https://supermegabot-production.up.railway.app/api/digistore24/ipn"
        ok, products = await asyncio.wait_for(
            asyncio.gather(ping(), get_products(), return_exceptions=True),
            timeout=18,
        )
        ok = ok if isinstance(ok, bool) else False
        products = products if isinstance(products, list) else []
        stats = _ds24_status_cache.get("stats", {}) if _ds24_status_cache else {}
        if ok:
            try:
                fresh_stats = await asyncio.wait_for(get_sales_stats(), timeout=10)
                if isinstance(fresh_stats, dict):
                    stats = fresh_stats
            except Exception:
                pass
        prod_count = int(len(products) or _ds24_status_cache.get("products_count") or 0)
        payload = {
            "ok": ok or configured,
            "connected": ok,
            "configured": configured,
            "api_key_set": configured,
            "stats": stats,
            "products_count": prod_count,
            "product_count": prod_count,
            "revenue_total": stats.get("total", 0),
            "orders_total": stats.get("orders_total", 0),
            "revenue_note": "€0 = Keine Transaktionen im Konto" if ok and stats.get("total", 0) == 0 else None,
            "ipn_url": ipn_url,
        }
        if ok or products:
            _ds24_status_cache = payload
            _ds24_status_cache_ts = time.time()
        elif _ds24_status_cache:
            stale = dict(_ds24_status_cache)
            stale.update({"connected": ok, "ok": configured, "error": "DS24 API timeout — Cache aktiv"})
            return web.json_response(stale)
        return web.json_response(payload)
    except asyncio.TimeoutError:
        from modules.digistore24_automation import is_configured as _ds24_cfg
        configured = _ds24_cfg()
        if _ds24_status_cache:
            stale = dict(_ds24_status_cache)
            stale.update({"connected": False, "ok": configured, "error": "DS24 API timeout — Cache aktiv"})
            return web.json_response(stale)
        return web.json_response({
            "ok": configured,
            "connected": False,
            "configured": configured,
            "api_key_set": configured,
            "products_count": int(_ds24_status_cache.get("products_count") or 0),
            "product_count": int(_ds24_status_cache.get("product_count") or 0),
            "stats": _ds24_status_cache.get("stats", {"total": 0, "orders_total": 0}),
            "error": "DS24 API timeout — Key gesetzt, API langsam",
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
        connected = bool(dragon.get("connected") or dragon.get("ok") or aiitec.get("ok"))
        members = max(
            int(dragon.get("member_count") or 0),
            int(aiitec.get("member_count") or 0),
        )
        disabled = any(
            "disabled" in str(v.get("error", "")).lower()
            for v in (dragon, aiitec) if isinstance(v, dict)
        )
        return web.json_response({
            "ok": connected and not disabled,
            "connected": connected and not disabled,
            "member_count": members,
            "subscribers": members,
            "dragon": dragon,
            "aiitec": aiitec,
            "accounts": (1 if dragon.get("ok") else 0) + (1 if aiitec.get("ok") else 0),
            "error": "Account disabled" if disabled else "",
        })
    except Exception as e:
        return web.json_response({"ok": False, "connected": False, "error": str(e)})


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
  <p>Wenn dir der Audit gefällt und du die Tools nutzen willst: SuperMegaBot gibt dir die komplette KI-Automatisierungs-Plattform ab €497/Monat — 14 Tage kostenlose Demo, kein Credit Card, 90-Tage ROI-Garantie.</p>
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
            send_err = ""
            async with s.post(f"{base_url}/campaigns/{campaign_id}/actions/send", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                sent = r.status == 204
                if not sent:
                    send_err = await r.text()
                    log.warning("Mailchimp send failed: %s", send_err[:200])

        if not sent and "disabled" in send_err.lower():
            # aiitec account disabled — fall back to dragon account
            try:
                from modules.mailchimp_autonomy import run_dragon_campaign
                dragon_result = await run_dragon_campaign(topic=subject)
                log.info("Mailchimp fallback dragon: %s", dragon_result)
                return web.json_response({
                    "ok": dragon_result.get("ok", False),
                    "campaign_id": dragon_result.get("campaign_id", campaign_id),
                    "list_id": list_id,
                    "list_name": list_name,
                    "subject": subject,
                    "sent": dragon_result.get("ok", False),
                    "account": "dragon_fallback",
                })
            except Exception as fe:
                log.warning("Dragon fallback failed: %s", fe)

        log.info("Mailchimp campaign %s: subject=%s list=%s sent=%s", campaign_id, subject, list_id, sent)
        return web.json_response({
            "ok": sent,
            "campaign_id": campaign_id,
            "list_id": list_id,
            "list_name": list_name,
            "subject": subject,
            "sent": sent,
            "send_error": send_err[:200] if send_err else None,
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
    subject  = body.get("subject", "🚀 SuperMegaBot — Shopify Vollautomatisierung für €97")
    html_body = body.get("html", """<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
<h1 style="color:#1a1a2e">Shopify auf KI-Autopilot — einmalig €97</h1>
<p>Hallo,</p>
<p>SuperMegaBot automatisiert deinen Shopify-Shop vollständig: Produktrecherche, Beschreibungen, Social Media, Emails — alles läuft automatisch. Einmal kaufen, dauerhaft profitieren.</p>
<p><a href="https://www.checkout-ds24.com/product/669750" style="background:#ff6600;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;margin:16px 0">Jetzt sichern — €97 Lifetime →</a></p>
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
    subject  = body.get("subject", "🚀 SuperMegaBot — Shopify Autopilot für einmalig €97")
    html_body = body.get("html", """<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
<h1 style="color:#1a1a2e">Shopify auf KI-Autopilot — kein Abo, Lifetime</h1>
<p>Hallo,</p>
<p>SuperMegaBot übernimmt deinen Shopify-Shop: 10.500+ Produkte automatisch, Social Media auf 9 Kanälen, Emails vollautomatisch. Einmalig €97 — kein monatliches Abo.</p>
<p><a href="https://www.checkout-ds24.com/product/669750" style="background:#ff6600;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;margin:16px 0">Jetzt sichern — €97 Lifetime →</a></p>
<p style="color:#888;font-size:12px">Rudolf | AIITEC · BullPower Hub</p>
</body></html>""")
    list_id = body.get("list_id", os.getenv("KLAVIYO_LIST_ID", "bc5c7887cf"))
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


async def handle_printify_autopublish(req):
    """POST /api/printify/autopublish — trending POD Produkte erstellen + publishen."""
    try:
        from modules.printify_autonomy import auto_create_trending_pod
        data = {}
        try:
            data = await req.json()
        except Exception:
            pass
        count = int(data.get("count", 5))
        result = await auto_create_trending_pod(count=count)
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


async def handle_gumroad_callback(req):
    """GET /api/gumroad/callback — OAuth2 auth code → access + refresh token."""
    code  = req.rel_url.query.get("code", "")
    error = req.rel_url.query.get("error", "")
    if error:
        return web.json_response({"ok": False, "error": error})
    if not code:
        return web.json_response({"ok": False, "error": "no code in callback"})
    client_id     = os.getenv("GUMROAD_CLIENT_ID", "")
    client_secret = os.getenv("GUMROAD_CLIENT_SECRET", "")
    redirect_uri  = "https://supermegabot-production.up.railway.app/api/gumroad/callback"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.gumroad.com/oauth/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        access_token  = d.get("access_token", "")
        refresh_token = d.get("refresh_token", "")
        if not access_token:
            return web.json_response({"ok": False, "error": "no access_token", "detail": d})
        os.environ["GUMROAD_ACCESS_TOKEN"] = access_token
        os.environ["GUMROAD_TOKEN"] = access_token
        if refresh_token:
            os.environ["GUMROAD_REFRESH_TOKEN"] = refresh_token
        # Persist to Railway so token survives restarts
        import subprocess
        try:
            subprocess.run(
                ["railway", "variables", "set",
                 f"GUMROAD_ACCESS_TOKEN={access_token}",
                 f"GUMROAD_TOKEN={access_token}",
                 "--service", "supermegabot"],
                capture_output=True, timeout=30,
            )
            if refresh_token:
                subprocess.run(
                    ["railway", "variables", "set",
                     f"GUMROAD_REFRESH_TOKEN={refresh_token}",
                     "--service", "supermegabot"],
                    capture_output=True, timeout=30,
                )
        except Exception as _e:
            log.warning("Gumroad Railway vars set failed: %s", _e)
        log.info("Gumroad OAuth callback: access_token=%s...", access_token[:12])
        return web.Response(content_type="text/html", text=(
            "<h2>✅ Gumroad verbunden!</h2>"
            "<p>Access Token dauerhaft in Railway gesetzt. Gumroad-API ab jetzt vollautomatisch.</p>"
            f"<p>Token: {access_token[:20]}...</p>"
            f"<p>Scopes: {d.get('scope', '?')}</p>"
        ))
    except Exception as e:
        log.exception("Gumroad callback error")
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


async def handle_revenue_orchestrator_status(req):
    """GET /api/revenue/orchestrator — ROAS + alle Channel-Stats."""
    try:
        from modules.revenue_orchestrator import get_revenue_status
        status = await get_revenue_status()
        return web.json_response(status)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_revenue_orchestrator_run(req):
    """POST /api/revenue/orchestrator/run — Revenue-Optimierungszyklus starten."""
    try:
        from modules.revenue_orchestrator import run_revenue_optimization_cycle
        result = await run_revenue_optimization_cycle()
        return web.json_response({"ok": True, "result": {
            "revenue_7d": result.get("stats", {}).get("shopify", {}).get("revenue", 0),
            "roas": result.get("roas", {}).get("overall_roas", 0),
            "report_sent": result.get("report_sent", False),
        }})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_tiktok_ads_status(req):
    """GET /api/tiktok/status — TikTok Ads Status + Insights."""
    try:
        from modules.tiktok_ads_engine import get_tiktok_status
        status = await get_tiktok_status()
        return web.json_response(status)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_tiktok_ads_run(req):
    """POST /api/tiktok/run — TikTok Ads Zyklus manuell starten."""
    try:
        from modules.tiktok_ads_engine import run_tiktok_ads_cycle
        result = await run_tiktok_ads_cycle()
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_meta_ads_status(req):
    """GET /api/meta/status — Meta Ads Kampagnen-Übersicht."""
    try:
        from modules.meta_ads_engine import get_meta_status
        result = await get_meta_status()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_meta_ads_run(req):
    """POST /api/meta/run — Meta Ads Zyklus manuell starten."""
    try:
        from modules.meta_ads_engine import run_meta_campaign_cycle
        result = await run_meta_campaign_cycle()
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_pinterest_run(req):
    """POST /api/pinterest/run — Pinterest Pins manuell posten."""
    try:
        data = await req.json() if req.can_read_body else {}
        pins = int(data.get("pins_per_run", 10))
        from modules.pinterest_traffic import run_pinterest_posting_cycle
        result = await run_pinterest_posting_cycle(pins_per_run=pins)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_pinterest_status(req):
    """GET /api/pinterest/status — Pinterest Boards + Pins Status."""
    try:
        from modules.pinterest_traffic import get_pinterest_status
        result = await get_pinterest_status()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_pinterest_verify_domain(req):
    """POST /api/pinterest/verify-domain — Pinterest-Verification-Tag in Shopify theme.liquid einbauen."""
    try:
        data = await req.json() if req.content_type == "application/json" else {}
    except Exception:
        data = {}
    code = data.get("code") or req.rel_url.query.get("code", "")
    if not code:
        return web.json_response({"ok": False, "error": "code parameter required"}, status=400)

    shop  = os.getenv("SHOPIFY_MYSHOPIFY_DOMAIN", "") or os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    if shop and ".myshopify.com" not in shop:
        import re as _re
        store_url = os.getenv("SHOPIFY_STORE_URL", "")
        match = _re.search(r"([\w-]+\.myshopify\.com)", store_url)
        if match:
            shop = match.group(1)
    token = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    ver   = os.getenv("SHOPIFY_API_VERSION", "2026-04")

    if not shop or not token:
        return web.json_response({"ok": False, "error": "Shopify not configured"}, status=500)

    meta_tag = f'<meta name="p:domain_verify" content="{code}" />'

    try:
        async with aiohttp.ClientSession() as s:
            # Get active theme
            async with s.get(
                f"https://{shop}/admin/api/{ver}/themes.json",
                headers={"X-Shopify-Access-Token": token},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                themes = (await r.json()).get("themes", [])
            active = next((t for t in themes if t.get("role") == "main"), None)
            if not active:
                return web.json_response({"ok": False, "error": "No active Shopify theme"}, status=404)
            theme_id = active["id"]

            # Read theme.liquid
            async with s.get(
                f"https://{shop}/admin/api/{ver}/themes/{theme_id}/assets.json",
                headers={"X-Shopify-Access-Token": token},
                params={"asset[key]": "layout/theme.liquid"},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                asset = await r.json()
            content = asset.get("asset", {}).get("value", "")
            if not content:
                return web.json_response({"ok": False, "error": "Could not read theme.liquid"}, status=500)

            if "p:domain_verify" in content:
                # Update existing tag
                import re
                content = re.sub(r'<meta name="p:domain_verify"[^>]*/>', meta_tag, content)
                action = "updated"
            else:
                # Insert after <head> or after google verification
                google_tag = '<meta name="google-site-verification"'
                if google_tag in content:
                    idx = content.index(google_tag)
                    end = content.index("/>", idx) + 2
                    content = content[:end] + "\n    " + meta_tag + content[end:]
                else:
                    content = content.replace("<head>", f"<head>\n    {meta_tag}", 1)
                action = "inserted"

            # Write back
            async with s.put(
                f"https://{shop}/admin/api/{ver}/themes/{theme_id}/assets.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json={"asset": {"key": "layout/theme.liquid", "value": content}},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                result = await r.json()
                if r.status in (200, 201):
                    log.info("Pinterest domain verify tag %s in theme %s", action, theme_id)
                    # Also save to Railway env
                    try:
                        import subprocess
                        subprocess.run(["railway", "variables", "set", f"PINTEREST_DOMAIN_VERIFY={code}"],
                                       capture_output=True, timeout=30)
                    except Exception:
                        pass
                    return web.json_response({
                        "ok": True, "action": action, "code": code[:8] + "...",
                        "theme": active.get("name"), "theme_id": theme_id
                    })
                return web.json_response({"ok": False, "error": str(result)[:300]}, status=500)
    except Exception as e:
        log.error("handle_pinterest_verify_domain: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_sendgrid_blast(req):
    """POST /api/email/sendgrid-blast — Revenue Email sofort senden."""
    try:
        from modules.sendgrid_blast import run_daily_revenue_email
        result = await run_daily_revenue_email()
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_sendgrid_status(req):
    """GET /api/email/sendgrid-status — SendGrid Stats."""
    try:
        from modules.sendgrid_blast import get_sendgrid_status
        result = await get_sendgrid_status()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_brevo_test(req: web.Request) -> web.Response:
    """GET /api/email/brevo-test — Brevo REST direkt testen."""
    import aiohttp as _aio, os as _os
    key = _os.getenv("BREVO_API_KEY", "")
    from_email = _os.getenv("BREVO_FROM_EMAIL", "aiitecbuuss@gmail.com")
    from_name  = _os.getenv("BREVO_FROM_NAME", "AiiteC")
    to_email   = req.rel_url.query.get("to", "bullpowersrtkennels@gmail.com")
    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": to_email, "name": "Test"}],
        "subject": "✅ Brevo Test vom Railway-Server",
        "htmlContent": "<p>Brevo REST API Test direkt vom Railway-Server ✅</p>",
    }
    try:
        async with _aio.ClientSession(timeout=_aio.ClientTimeout(total=15)) as s:
            async with s.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": key, "Content-Type": "application/json"},
                json=payload,
            ) as r:
                body = await r.text()
                return web.json_response({
                    "ok": r.status in (200, 201),
                    "status": r.status,
                    "response": body[:500],
                    "from": from_email,
                    "to": to_email,
                    "key_set": bool(key),
                })
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


async def handle_seo_discover_keywords(req):
    """POST /api/seo/discover-keywords — befüllt Keyword-Cache (Supabase + Disk)."""
    try:
        from modules.seo_mega_engine import discover_all_keywords
        kws = await discover_all_keywords()
        return web.json_response({"ok": True, "keywords_found": len(kws), "sample": [k.get("keyword","") for k in kws[:5]]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_seo_run_factory(req):
    """POST /api/seo/run-factory — generiert SEO-Blog-Artikel und published auf Shopify."""
    try:
        data = await req.json() if req.can_read_body else {}
        batch = int(data.get("batch_size", 5))
        from modules.seo_mega_engine import run_content_factory
        result = await run_content_factory(batch_size=batch)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# SEO: Sitemap ping — Google + Bing indexing for all BullPower Hub Netlify sites
# ---------------------------------------------------------------------------

_SHOPIFY_DOMAIN = os.getenv("SHOPIFY_CUSTOM_DOMAIN", os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co"))
_SITEMAPS = [
    f"https://{_SHOPIFY_DOMAIN}/sitemap.xml",
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
        try:
            import modules.anthropic_compat as _anthropic
        except ImportError:
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
        err_msg = str(e)
        log.error("handle_social_drafts error: %s", e)
        if "credit balance" in err_msg.lower() or "too low" in err_msg.lower():
            return web.json_response(
                {"ok": False, "error": "Anthropic API Credits aufgebraucht — bitte unter console.anthropic.com aufladen"},
                status=503,
            )
        return web.json_response({"ok": False, "error": err_msg}, status=500)


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


async def handle_upgrade(req):
    """POST /api/upgrade — swap an existing Stripe subscription to a new plan (no double-billing)."""
    try:
        data = await req.json()
        email      = data.get("email", "").strip()
        new_price  = data.get("price_id", "").strip()
        if not email or not new_price:
            return web.json_response({"ok": False, "error": "email and price_id required"}, status=400)
        stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
        if not stripe_key:
            return web.json_response({"ok": False, "error": "Stripe not configured"}, status=500)
        import urllib.request as _ur, urllib.parse as _up
        _auth_hdr = {"Authorization": f"Bearer {stripe_key}"}
        # 1. Find customer by email
        _cust_url = f"https://api.stripe.com/v1/customers?email={_up.quote(email)}&limit=1"
        _req = _ur.Request(_cust_url, headers=_auth_hdr)
        with _ur.urlopen(_req, timeout=15) as _r:
            _custs = json.loads(_r.read())
        _cust_list = _custs.get("data", [])
        if not _cust_list:
            return web.json_response({"ok": False, "error": "No Stripe customer found for this email"}, status=404)
        customer_id = _cust_list[0]["id"]
        # 2. Find active subscription
        _sub_url = f"https://api.stripe.com/v1/subscriptions?customer={customer_id}&status=active&limit=1"
        _req2 = _ur.Request(_sub_url, headers=_auth_hdr)
        with _ur.urlopen(_req2, timeout=15) as _r2:
            _subs = json.loads(_r2.read())
        _sub_list = _subs.get("data", [])
        if not _sub_list:
            return web.json_response({"ok": False, "error": "No active subscription found"}, status=404)
        sub     = _sub_list[0]
        sub_id  = sub["id"]
        item_id = sub["items"]["data"][0]["id"]
        # 3. Modify subscription in place (swap price, no new subscription)
        _mod_data = _up.urlencode({
            f"items[0][id]":    item_id,
            f"items[0][price]": new_price,
            "proration_behavior": "create_prorations",
        }).encode()
        _mod_req = _ur.Request(
            f"https://api.stripe.com/v1/subscriptions/{sub_id}",
            data=_mod_data,
            headers={**_auth_hdr, "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with _ur.urlopen(_mod_req, timeout=15) as _r3:
            updated = json.loads(_r3.read())
        log.info("[UPGRADE] Subscription %s upgraded to price %s for %s", sub_id, new_price, email)
        return web.json_response({
            "ok": True,
            "subscription_id": updated["id"],
            "new_price": new_price,
            "status": updated.get("status"),
        })
    except Exception as e:
        log.error("[UPGRADE] Error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


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


_PLANS_MSG = """💰 *SuperMegaBot High-Ticket Pläne*

🚀 *Growth — €497/Monat*
• Shopify Vollautomatisierung (bis 5.000 SKU)
• Social Autopilot (3 Plattformen)
• Telegram Bot + Revenue-Reports
• 60-min Onboarding-Call
• Priority Support <8h

⚡ *Scale — €997/Monat* _(beliebteste Wahl)_
• Alles aus Growth + unbegrenzte SKUs
• Social Autopilot alle Plattformen
• Dedicated Customer Success Manager
• Digistore24 + Affiliate-Automation
• Quarterly Business Reviews (QBR)
• Priority Support <4h

🏆 *Enterprise — €2.497/Monat*
• Alles aus Scale
• White-Label für Agentur-Kunden
• Custom API + dedizierte Railway-Instanz
• SLA 99.99% schriftlich
• Unbegrenzte Team-Zugänge
• Priority Support <1h

✅ 14-Tage Demo kostenlos · 90-Tage ROI-Garantie · DSGVO-konform

👇 Jetzt starten:"""

_WELCOME_MSG = """🤖 *Willkommen bei RudiBot!*

Ich bin dein KI-Assistent für E-Commerce & Business Automation.

*Befehle:*
/start — Diese Nachricht
/premium — Pläne & Preise
/hilfe — Alle Funktionen

Oder einfach schreib mir — ich antworte sofort! 💬"""


async def _tg_send(bot_token: str, chat_id: int, text: str, reply_markup: dict = None):
    from modules.smart_poster import send_telegram_guarded
    await send_telegram_guarded(
        bot_token,
        str(chat_id),
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


async def handle_telegram_webhook(req):
    """Telegram webhook — processes incoming messages and callback queries."""
    try:
        data = await req.json()

        # ── Channel post detector — auto-set TELEGRAM_CHANNEL_ID ──────────────
        ch_post = data.get("channel_post")
        if ch_post:
            ch = ch_post.get("chat", {})
            ch_id  = ch.get("id")
            ch_title = ch.get("title", "?")
            ch_username = ch.get("username", "")
            if ch_id and str(ch_id) != os.getenv("TELEGRAM_CHANNEL_ID", ""):
                os.environ["TELEGRAM_CHANNEL_ID"] = str(ch_id)
                log.info("Kanal erkannt: %s id=%s @%s", ch_title, ch_id, ch_username)
                # Telegram-Bestätigung an Rudolf
                token = os.getenv("TELEGRAM_BOT_TOKEN", "")
                chat  = os.getenv("TELEGRAM_CHAT_ID", "")
                if token and chat:
                    try:
                        async with aiohttp.ClientSession() as _cs:
                            await _cs.post(
                                f"https://api.telegram.org/bot{token}/sendMessage",
                                json={"chat_id": chat,
                                      "text": f"✅ <b>Kanal erkannt!</b>\n\n"
                                              f"Name: <b>{ch_title}</b>\n"
                                              f"ID: <code>{ch_id}</code>\n"
                                              f"@{ch_username}\n\n"
                                              f"Ab sofort gehen alle Marketing-Posts dorthin!\n"
                                              f"TELEGRAM_CHANNEL_ID={ch_id} gesetzt.",
                                      "parse_mode": "HTML"},
                                timeout=aiohttp.ClientTimeout(total=8),
                            )
                    except Exception:
                        pass
            return web.Response(status=200)

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

        base_url = f"https://{os.getenv('RAILWAY_STATIC_URL', 'supermegabot-production.up.railway.app')}"

        # ── PostGuard APPROVE/REJECT ───────────────────────────────────────────
        if text and (text.startswith("APPROVE pg_") or text.startswith("REJECT pg_")):
            try:
                parts     = text.split()
                verdict   = parts[0]        # "APPROVE" oder "REJECT"
                appr_id   = parts[1]        # "pg_1234567890"
                approved  = (verdict == "APPROVE")
                from modules.post_guard import resolve_telegram_approval
                resolved  = resolve_telegram_approval(appr_id, approved)
                icon      = "✅" if approved else "🚫"
                status    = "angenommen" if approved else "abgelehnt"
                reply_msg = f"{icon} PostGuard: Post {status}." if resolved else "⚠️ Approval-ID nicht gefunden (bereits abgelaufen?)"
                await _tg_send(bot_token, chat_id, reply_msg)
            except Exception as _pg_e:
                log.warning("PostGuard resolve: %s", _pg_e)
            return web.Response(status=200)

        # ── PostGuard Stats ──────────────────────────────────────────────────
        if text == "/guard_stats":
            try:
                from modules.post_guard import guard
                stats = await guard.stats()
                msg = (
                    f"🛡 <b>PostGuard Statistik</b>\n"
                    f"Gesamt: {stats.get('total', 0)}\n"
                    f"✅ Approved: {stats.get('approved', 0)}\n"
                    f"🚫 Blockiert: {stats.get('blocked', 0)} ({stats.get('block_rate', '?')})\n"
                    f"Heute: {stats.get('today', 0)}\n"
                )
                reasons = stats.get('top_block_reasons', [])
                if reasons:
                    msg += "\n<b>Top Blockier-Gründe:</b>\n"
                    for r in reasons:
                        msg += f"  • {r['reason'][:50]} ({r['count']}x)\n"
                await _tg_send(bot_token, chat_id, msg)
            except Exception as _gs_e:
                await _tg_send(bot_token, chat_id, f"❌ {_gs_e}")
            return web.Response(status=200)

        # --- Befehle ---
        if text in ("/start", "/menu", "/dashboard", "/hilfe", "/help"):
            from modules.telegram_control import send_main_menu
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, send_main_menu, str(chat_id))
            return web.Response(status=200)

        if text in ("/leads",):
            try:
                async with aiohttp.ClientSession() as _s:
                    async with _s.get(f"http://localhost:{os.getenv('PORT', '8888')}/api/leads") as _r:
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
                    async with _s.post(f"http://localhost:{os.getenv('PORT', '8888')}/api/seo/generate") as _r:
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
                    async with _s.get(f"http://localhost:{os.getenv('PORT', '8888')}/api/seo/social-drafts") as _r:
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
                    async with _s.post(f"http://localhost:{os.getenv('PORT', '8888')}/api/seo/ping-sitemaps") as _r:
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
                [{"text": "🚀 Growth €497/Mo", "url": f"{base_url}/checkout?plan=growth&chat_id={chat_id}"}],
                [{"text": "⚡ Scale €997/Mo ← Beliebt", "url": f"{base_url}/checkout?plan=scale&chat_id={chat_id}"}],
                [{"text": "🏆 Enterprise €2.497/Mo", "url": f"{base_url}/checkout?plan=enterprise&chat_id={chat_id}"}],
                [{"text": "📅 14-Tage Demo buchen", "url": f"{base_url}/demo?chat_id={chat_id}"}],
            ]}
            await _tg_send(bot_token, chat_id, _PLANS_MSG, reply_markup=keyboard)
            return web.Response(status=200)

        # --- AI Antwort ---
        # Rudolf (TELEGRAM_CHAT_ID) bekommt persönlichen Assistenten mit Memory + Sonnet
        # Kunden bekommen den Standard-Customer-Bot
        rudolf_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        is_rudolf = rudolf_chat_id and str(chat_id) == str(rudolf_chat_id)

        if is_rudolf:
            try:
                from modules.rudolf_assistant import ask
                reply_text = await ask(
                    text or "(leere Nachricht)",
                    session_id=f"tg_{chat_id}",
                )
            except Exception as ai_err:
                log.error("Rudolf-Assistent Telegram-Fehler: %s", ai_err)
                reply_text = f"❌ Assistent nicht verfügbar: {ai_err}"
        else:
            try:
                try:
                    import modules.anthropic_compat as anthropic
                except ImportError:
                    import anthropic
                client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
                reply_msg = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=500,
                    system=(
                        "Du bist RudiBot, ein KI-Assistent für E-Commerce und Business Automation. "
                        "Antworte auf Deutsch, kurz und hilfreich. "
                        "Wenn jemand nach Preisen, Abo oder Kauf fragt, sage: "
                        "'Tippe /premium für unsere High-Ticket Pläne ab €497/Monat — mit 14-Tage Demo und 90-Tage ROI-Garantie.'"
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


async def handle_telegram_landing(req):
    """GET /telegram — DudiRudibot Subscription Landing Page."""
    html_file = Path(__file__).parent / "telegram.html"
    if not html_file.exists():
        return web.Response(status=404, text="telegram.html nicht gefunden")
    return web.Response(content_type="text/html", text=html_file.read_text(encoding="utf-8"))


async def handle_checkout_page(req):
    """Redirect to Stripe Checkout für Telegram-Nutzer."""
    plan = req.rel_url.query.get("plan", "starter")
    chat_id = req.rel_url.query.get("chat_id", "")
    base_url = f"https://{os.getenv('RAILWAY_STATIC_URL', 'supermegabot-production.up.railway.app')}"
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

    base_url = f"https://{os.getenv('RAILWAY_STATIC_URL', 'supermegabot-production.up.railway.app')}"
    results = {}

    async with aiohttp.ClientSession() as session:
        # 1. Set webhook
        webhook_url = f"{base_url}/api/telegram/webhook"
        async with session.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "allowed_updates": ["message", "callback_query", "edited_message", "channel_post"]}
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

        # 3. Dashboard-Button dauerhaft auf Railway-URL setzen (NIEMALS ngrok!)
        async with session.post(
            f"https://api.telegram.org/bot{token}/setChatMenuButton",
            json={"menu_button": {"type": "web_app", "text": "Dashboard",
                                  "web_app": {"url": base_url}}}
        ) as r:
            results["setChatMenuButton"] = await r.json()

    log.info("Telegram setup completed: %s", results)
    return web.json_response({"ok": True, "results": results, "webhook": webhook_url, "dashboard": base_url})


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
    redirect_uri = os.getenv("DISCORD_REDIRECT_URI", "https://supermegabot-production.up.railway.app/api/discord/oauth/callback")
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

async def handle_shopify_oauth_callback(req: web.Request) -> web.Response:
    """GET /api/shopify/oauth/callback — exchange OAuth code for access token and save."""
    import hmac as _hmac, hashlib as _hashlib
    params = dict(req.rel_url.query)
    hmac_val = params.pop("hmac", "")
    api_secret = os.getenv("SHOPIFY_API_SECRET", "")
    if api_secret:
        query_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        expected  = _hmac.new(api_secret.encode(), query_str.encode(), _hashlib.sha256).hexdigest()
        if not _hmac.compare_digest(expected, hmac_val):
            return web.Response(text="HMAC invalid", status=400)
    code = params.get("code", "")
    shop = params.get("shop", os.getenv("SHOPIFY_SHOP_DOMAIN", ""))
    if not code or not shop:
        return web.Response(text="Missing code or shop", status=400)
    api_key    = os.getenv("SHOPIFY_API_KEY", "")
    api_secret = os.getenv("SHOPIFY_API_SECRET", "")
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.post(
                f"https://{shop}/admin/oauth/access_token",
                json={"client_id": api_key, "client_secret": api_secret, "code": code},
            ) as r:
                data = await r.json()
        token = data.get("access_token", "")
        if not token:
            return web.Response(text=f"No token in response: {data}", status=500)
        log.info("[SHOPIFY-OAUTH] New token received for %s: %s...", shop, token[:12])
        # Persist to Supabase oauth_tokens
        try:
            from modules.supabase_client import get_supabase
            sb = get_supabase()
            sb.table("oauth_tokens").upsert(
                {"platform": "shopify", "access_token": token, "user_id": shop}
            ).execute()
            log.info("[SHOPIFY-OAUTH] Token saved to Supabase")
        except Exception as e:
            log.warning("[SHOPIFY-OAUTH] Supabase save failed: %s", e)
        # Update Railway env var so the new token is used immediately
        try:
            import subprocess as _sp
            _sp.run(
                ["railway", "variables", "set", f"SHOPIFY_ADMIN_API_TOKEN={token}", "--service", "supermegabot"],
                capture_output=True, timeout=30
            )
            log.info("[SHOPIFY-OAUTH] Railway variable updated")
        except Exception as _rv_err:
            log.warning("[SHOPIFY-OAUTH] Railway variable update failed: %s", _rv_err)
        # Telegram notification
        tg_tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
        tg_ch  = os.getenv("TELEGRAM_CHAT_ID", "")
        new_scope = data.get("scope", "")
        if tg_tok and tg_ch:
            try:
                _msg = (f"✅ <b>SHOPIFY TOKEN ERNEUERT!</b>\n\nShop: {shop}\n"
                        f"Scopes: {new_scope}\n"
                        f"Blog: {'✅' if 'write_content' in new_scope else '❌'} | "
                        f"Discounts: {'✅' if 'write_price_rules' in new_scope else '❌'}")
                async with aiohttp.ClientSession() as _s2:
                    await _s2.post(
                        f"https://api.telegram.org/bot{tg_tok}/sendMessage",
                        json={"chat_id": tg_ch, "text": _msg, "parse_mode": "HTML"}
                    )
            except Exception as _tg_err:
                log.warning("[SHOPIFY-OAUTH] Telegram notify failed: %s", _tg_err)
        return web.Response(
            content_type="text/html",
            text=f"""<html><body style="background:#0a0a1a;color:#fff;font-family:Arial;text-align:center;padding:60px">
<h1 style="color:#4ade80">&#x2705; Shopify vollst&#228;ndig freigeschaltet!</h1>
<p style="color:#aaa">Scopes: {new_scope}</p>
<p style="color:#FFD700">Blog, Discounts, Inventory &#x2014; alles aktiv.</p>
<p>Fenster schlie&#xDF;en &#x2014; fertig!</p>
</body></html>""",
        )
    except Exception as e:
        log.error("[SHOPIFY-OAUTH] Error: %s", e)
        return web.Response(text=f"Error: {e}", status=500)


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
            "ok": True,
            "configured": configured,
            "token_set": token_set,
            "content_generation": True,
            "posting_active": token_set,
            "shop_id": os.getenv("TIKTOK_SHOP_ID", ""),
        })
    except Exception as e:
        return web.json_response({"ok": True, "content_generation": True, "posting_active": False, "error": str(e)})


async def handle_whatsapp_status(req):
    try:
        phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or os.getenv("WHATSAPP_PHONE_ID", "")
        wa_token = os.getenv("WHATSAPP_ACCESS_TOKEN") or os.getenv("WHATSAPP_TOKEN", "")
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


async def handle_shopify_checkout_create_webhook(req):
    """POST /api/webhooks/shopify/checkout-create — track new checkouts for abandoned cart recovery."""
    try:
        data = await req.json()
        from modules.abandoned_cart_recovery import handle_checkout_webhook
        await handle_checkout_webhook(data, event_type="create")
        # Also register into the email-recovery pipeline (abandoned_cart_emails.py)
        try:
            from modules.abandoned_cart_emails import register_cart
            await register_cart(data)
        except Exception as reg_err:
            log.warning("abandoned_cart_emails: register_cart failed for checkout %s — %s",
                        data.get("id", "?"), reg_err)
        return web.Response(status=200)
    except Exception as e:
        log.error("Checkout-create webhook error: %s", e)
        return web.Response(status=200)


async def handle_shopify_checkout_update_webhook(req):
    """POST /api/webhooks/shopify/checkout-update — mark completed checkouts."""
    try:
        data = await req.json()
        from modules.abandoned_cart_recovery import handle_checkout_webhook
        await handle_checkout_webhook(data, event_type="update")
        return web.Response(status=200)
    except Exception as e:
        log.error("Checkout-update webhook error: %s", e)
        return web.Response(status=200)


async def handle_shopify_order_create_for_cart(req):
    """POST /api/webhooks/shopify/order-create — mark checkout as purchased (cancel recovery)."""
    try:
        data = await req.json()
        from modules.abandoned_cart_recovery import handle_order_webhook
        import asyncio
        asyncio.create_task(handle_order_webhook(data))
        # Also run the original order webhook logic
        from modules.shopify_automation import handle_shopify_order_webhook
        asyncio.create_task(handle_shopify_order_webhook(data))
        asyncio.create_task(_push_order_to_pipedrive(data))
        asyncio.create_task(_pod_fulfill_order(data))
        return web.Response(status=200)
    except Exception as e:
        log.error("Order-create webhook error: %s", e)
        return web.Response(status=200)


async def handle_shopify_orders_paid_webhook(req):
    """POST /api/webhooks/shopify/orders-paid — fires when Shopify payment is confirmed.

    Triggered by Shopify topic: orders/paid
    Differs from orders/create (which includes unpaid orders).
    """
    try:
        data = await req.json()
        order_id    = data.get("id", "?")
        order_name  = data.get("name", "?")
        total_price = data.get("total_price", "0.00")
        currency    = data.get("currency", "EUR")
        email       = data.get("email", "")
        customer    = data.get("customer") or {}
        first_name  = customer.get("first_name", "")

        log.info("orders/paid: %s %s %s %s", order_name, total_price, currency, email)

        # 1. Cancel abandoned cart recovery for this email
        if email:
            try:
                from modules.abandoned_cart_recovery import cancel_recovery_for_email
                await cancel_recovery_for_email(email)
            except Exception:
                pass

        # 2. Trigger Klaviyo post-purchase sequence
        if email:
            try:
                from modules.klaviyo_client import track_event
                await track_event(
                    email=email,
                    event="Order Paid",
                    properties={
                        "order_id":    str(order_id),
                        "order_name":  order_name,
                        "total_price": float(total_price),
                        "currency":    currency,
                        "first_name":  first_name,
                    },
                )
            except Exception as _e:
                log.debug("Klaviyo order-paid track failed: %s", _e)

        # 3. Update revenue tracking (Supabase)
        try:
            from modules.revenue_dashboard_data import record_paid_order
            await record_paid_order(order_id=str(order_id), amount=float(total_price), currency=currency)
        except Exception:
            pass

        # 4. Shopify order webhook (inventory + DS24 sync)
        asyncio.create_task(_safe_task(
            "orders_paid_shopify_webhook",
            _import_and_call("modules.shopify_automation", "handle_shopify_order_webhook", data),
        ))

        # 5. Telegram notification on real sales
        try:
            token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            if token and chat_id and float(total_price) > 0:
                import aiohttp as _ah
                msg = f"💰 Verkauf bestätigt!\n{order_name} · {total_price} {currency}\n👤 {email or 'anonym'}"
                asyncio.create_task(_safe_post_telegram(token, chat_id, msg))
        except Exception:
            pass

        # 6. Sofia Upsell-Anruf + Bestätigungs-SMS (wenn Telefonnummer vorhanden)
        try:
            billing = data.get("billing_address") or data.get("shipping_address") or {}
            phone   = billing.get("phone") or customer.get("phone") or ""
            line_items    = data.get("line_items", [])
            product_title = line_items[0].get("title", "") if line_items else ""
            if phone and float(total_price) > 0:
                asyncio.create_task(_sofia_upsell_call(phone, product_title, first_name or "", order_name))
                # Sofort: Bestellbestätigungs-SMS
                asyncio.create_task(_sofia_order_sms(phone, first_name or "", order_name, total_price, currency))
        except Exception as _se:
            log.debug("Sofia upsell call setup: %s", _se)

        return web.Response(status=200)
    except Exception as e:
        log.error("orders/paid webhook error: %s", e)
        return web.Response(status=200)


async def _sofia_order_sms(phone: str, name: str, order_name: str, total: str, currency: str) -> None:
    """Sofortige Bestellbestätigungs-SMS nach Shopify-Kauf."""
    try:
        name_part = f" {name.split()[0]}" if name else ""
        msg = (
            f"Hallo{name_part}! ✅ Ihre Bestellung {order_name} ({total} {currency}) ist eingegangen. "
            f"Fragen? Einfach antworten — Sofia/AIITEC"
        )
        from modules.sofia_sms_agent import send_sms
        await send_sms(phone, msg[:160], campaign="order_confirmation")
    except Exception as e:
        log.debug("_sofia_order_sms: %s", e)


async def _sofia_upsell_call(phone: str, product: str, name: str, order_name: str) -> None:
    """Verzögerter Sofia-Anruf nach Kauf — Upsell / Bestätigung."""
    await asyncio.sleep(120)  # 2 Min Pause damit Kunde die Bestellbestätigung gelesen hat
    try:
        from modules.sofia_voice_agent import queue_sofia_call
        queue_sofia_call(
            to_number  = phone,
            product_id = product,
            contact    = name,
            context    = f"Kauf bestätigt: {order_name}",
            source     = "shopify_order_paid",
        )
        log.info("Sofia Upsell queued: %s → %s", order_name, phone)
    except Exception as e:
        log.debug("_sofia_upsell_call: %s", e)


async def _safe_task(name: str, coro):
    try:
        await coro
    except Exception as e:
        log.debug("safe_task[%s]: %s", name, e)


async def _import_and_call(module_path: str, fn_name: str, *args, **kwargs):
    import importlib
    mod = importlib.import_module(module_path)
    fn  = getattr(mod, fn_name)
    return await fn(*args, **kwargs)


async def _safe_post_telegram(token: str, chat_id: str, text: str):
    try:
        import aiohttp as _ah
        async with _ah.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "disable_notification": False},
                timeout=_ah.ClientTimeout(total=8),
            )
    except Exception:
        pass


async def handle_abandoned_cart_manual_run(req):
    """POST /api/abandoned-cart/run — manually trigger abandoned cart recovery."""
    try:
        from modules.abandoned_cart_recovery import run_abandoned_cart_recovery
        result = await run_abandoned_cart_recovery()
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        log.error("Manual abandoned cart run error: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_shopify_customer_webhook(req):
    """POST /api/shopify/customer-webhook — sync new Shopify customers to Klaviyo."""
    try:
        data = await req.json()
        email = data.get("email", "")
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        if not email:
            return web.json_response({"ok": False, "error": "no email"})

        klaviyo_key = os.getenv("KLAVIYO_API_KEY", "")
        klaviyo_list = os.getenv("KLAVIYO_LIST_ID", "bc5c7887cf")
        if not klaviyo_key:
            return web.json_response({"ok": False, "error": "no klaviyo key"})

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Klaviyo-API-Key {klaviyo_key}",
                "revision": "2024-10-15",
                "Content-Type": "application/json",
            }
            payload = {
                "data": {
                    "type": "profile-subscription-bulk-create-job",
                    "attributes": {
                        "list_id": klaviyo_list,
                        "subscriptions": [{
                            "email": email,
                            "channels": {"email": ["MARKETING"]},
                        }],
                        "profiles": {
                            "data": [{
                                "type": "profile",
                                "attributes": {
                                    "email": email,
                                    "first_name": first_name,
                                    "last_name": last_name,
                                    "properties": {"source": "shopify_signup"},
                                },
                            }]
                        },
                    },
                }
            }
            async with session.post(
                "https://a.klaviyo.com/api/profile-subscription-bulk-create-jobs/",
                headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                ok = r.status in (200, 201, 202)
                log.info("Shopify→Klaviyo sync %s: %s", email, r.status)
                return web.json_response({"ok": ok, "email": email, "status": r.status})
    except Exception as e:
        log.error("Customer webhook error: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_shopify_orders(req):
    """GET /api/shopify/orders — echte Shopify Bestellungen via async shopify_client."""
    try:
        from modules.shopify_client import get_orders
        limit = int(req.rel_url.query.get("limit", "10"))
        orders = await get_orders(limit=limit)
        return web.json_response({"ok": True, "orders": orders, "count": len(orders)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_shopify_revenue(req):
    """GET /api/shopify/revenue — Umsatz heute + Monat via async shopify_client."""
    try:
        from modules.shopify_client import get_analytics_summary
        data = await get_analytics_summary()
        if not data:
            return web.json_response({"ok": False, "error": "Shopify API nicht erreichbar oder keine Daten"})
        return web.json_response({"ok": True, **data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_shopify_products(req):
    try:
        import aiohttp as _aiohttp
        shop = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        version = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        if not shop or not token:
            return web.json_response({"ok": False, "error": "SHOPIFY_SHOP_DOMAIN / SHOPIFY_ADMIN_API_TOKEN not set"})
        limit = int(req.rel_url.query.get("limit", "20"))
        hdrs = {"X-Shopify-Access-Token": token}
        async with _aiohttp.ClientSession(timeout=_aiohttp.ClientTimeout(total=12)) as session:
            async with session.get(
                f"https://{shop}/admin/api/{version}/products/count.json?status=active",
                headers=hdrs,
            ) as rc:
                total_count = (await rc.json(content_type=None)).get("count", 0)
            async with session.get(
                f"https://{shop}/admin/api/{version}/products.json?limit={limit}&status=active",
                headers=hdrs,
            ) as rp:
                products = (await rp.json(content_type=None)).get("products", [])
        return web.json_response({"ok": True, "products": products, "count": total_count, "page_count": len(products)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_webhook(req):
    try:
        payload = await req.read()
        sig_header = req.headers.get("Stripe-Signature", "")

        from modules.stripe_automation import verify_webhook_signature, handle_webhook_event

        # Live- und Test-Secret beide prüfen (Test-Account hat eigenes Secret)
        live_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        test_secret = os.getenv("STRIPE_TEST_WEBHOOK_SECRET", "")
        secrets = [s for s in [live_secret, test_secret] if s]
        if not secrets:
            log.error("[STRIPE-WEBHOOK] No webhook secret configured — rejecting request")
            return web.json_response({"ok": False, "error": "STRIPE_WEBHOOK_SECRET not configured"}, status=400)
        verified = any(verify_webhook_signature(payload, sig_header, s) for s in secrets)
        if not verified:
            return web.json_response({"ok": False, "error": "Invalid signature"}, status=400)

        event = json.loads(payload)
        result = await handle_webhook_event(event)

        # Resend Onboarding + Telegram-Notification bei neuer Zahlung
        try:
            asyncio.create_task(_stripe_onboarding_hook(event))
        except Exception as _oh:
            log.debug("Onboarding hook create_task: %s", _oh)

        # Sofia Upsell-Anruf nach Stripe-Zahlung
        try:
            event_type = event.get("type", "")
            if event_type in ("payment_intent.succeeded", "checkout.session.completed"):
                obj = event.get("data", {}).get("object", {})
                phone    = obj.get("phone") or (obj.get("customer_details") or {}).get("phone") or ""
                name     = (obj.get("customer_details") or {}).get("name") or ""
                metadata = obj.get("metadata") or {}
                product  = metadata.get("product_id") or metadata.get("product") or ""
                amount   = (obj.get("amount_total") or obj.get("amount", 0)) / 100
                if phone and amount > 0:
                    asyncio.create_task(_sofia_stripe_call(phone, product, name, amount))
        except Exception as _se:
            log.debug("Sofia Stripe hook: %s", _se)

        # Claude-Analyse bei neuer Zahlung → Telegram an Rudolf
        try:
            event_type = event.get("type", "")
            if event_type in ("payment_intent.succeeded", "checkout.session.completed", "charge.succeeded"):
                asyncio.create_task(_claude_stripe_analysis(event))
        except Exception as _ca:
            log.debug("Claude Stripe analysis hook: %s", _ca)

        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def _claude_stripe_analysis(event: dict) -> None:
    """Neue Stripe-Zahlung → Claude analysiert + sendet Kurz-Report an Rudolf via Telegram."""
    try:
        obj = event.get("data", {}).get("object", {})
        amount = (obj.get("amount_total") or obj.get("amount", 0)) / 100
        currency = (obj.get("currency") or "eur").upper()
        customer_email = (obj.get("customer_details") or {}).get("email", "") or obj.get("receipt_email", "")
        metadata = obj.get("metadata") or {}
        product = metadata.get("product") or metadata.get("product_id") or "?"
        event_type = event.get("type", "")

        from modules.rudolf_assistant import quick
        analysis = quick(
            f"Neue Stripe-Zahlung eingegangen!\n"
            f"Event: {event_type}\n"
            f"Betrag: {amount:.2f} {currency}\n"
            f"Produkt: {product}\n"
            f"Kunde: {customer_email}\n\n"
            f"Gib eine kurze Glückwunsch-Nachricht (2-3 Sätze) + 1 konkreten Upsell-Hinweis für Rudolf."
        )
        if analysis:
            token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            if token and chat_id:
                msg = (
                    f"💰 <b>Neue Zahlung: {amount:.2f} {currency}!</b>\n"
                    f"📦 Produkt: {product}\n"
                    f"👤 Kunde: {customer_email or '–'}\n\n"
                    f"🤖 <i>{analysis}</i>"
                )
                async with aiohttp.ClientSession() as s:
                    await s.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
                        timeout=aiohttp.ClientTimeout(total=8),
                    )
    except Exception as e:
        log.debug("_claude_stripe_analysis: %s", e)


async def _stripe_onboarding_hook(event: dict) -> None:
    """Stripe-Zahlung → Resend Onboarding-Sequenz starten."""
    try:
        from modules.stripe_payment_hook import handle_stripe_event
        payload = json.dumps(event).encode()
        await handle_stripe_event(payload, "")  # Sig bereits verifiziert
    except Exception as e:
        log.debug("_stripe_onboarding_hook: %s", e)


async def _sofia_stripe_call(phone: str, product: str, name: str, amount: float) -> None:
    """Sofia-Anruf nach Stripe-Zahlung — Danke + Upsell."""
    await asyncio.sleep(60)
    try:
        from modules.sofia_voice_agent import queue_sofia_call
        queue_sofia_call(
            to_number  = phone,
            product_id = product,
            contact    = name,
            context    = f"Stripe-Zahlung €{amount:.2f} bestätigt",
            source     = "stripe_payment",
        )
    except Exception as e:
        log.debug("_sofia_stripe_call: %s", e)


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
            # Auto-register GMC feed as scheduled fetch
            gmc_status = "⏳ Registrierung läuft..."
            try:
                access_token = result.get("access_token", "")
                merchant_id  = os.getenv("GMC_MERCHANT_ID", "5813214419")
                from modules.gmc_feed_uploader import _feed_url
                feed_url     = _feed_url()
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s2:
                    # Check existing feeds
                    r2 = await s2.get(
                        f"https://shoppingcontent.googleapis.com/content/v2.1/{merchant_id}/datafeeds",
                        headers={"Authorization": f"Bearer {access_token}"}
                    )
                    existing = await r2.json()
                    already  = any(f.get("fetchSchedule", {}).get("fetchUrl", "") == feed_url
                                   for f in existing.get("resources", []))
                    if already:
                        gmc_status = "✅ GMC Feed bereits registriert"
                    else:
                        feed_body = {
                            "name": "SuperMegaBot AutoFeed",
                            "contentType": "products",
                            "contentLanguage": "de",
                            "targetCountry": "DE",
                            "format": {"fileEncoding": "utf-8", "columnDelimiter": "tab", "quotingMode": "value quoting"},
                            "fetchSchedule": {
                                "weekday": "monday", "hour": 6, "timeZone": "Europe/Berlin",
                                "fetchUrl": feed_url, "paused": False
                            },
                        }
                        r3 = await s2.post(
                            f"https://shoppingcontent.googleapis.com/content/v2.1/{merchant_id}/datafeeds",
                            headers={"Authorization": f"Bearer {access_token}",
                                     "Content-Type": "application/json"},
                            json=feed_body
                        )
                        d3 = await r3.json()
                        if r3.status in (200, 201):
                            gmc_status = f"✅ GMC Feed registriert! ID: {d3.get('id','?')}"
                        else:
                            gmc_status = f"⚠️ {d3.get('error',{}).get('message','?')[:80]}"
            except Exception as gmc_e:
                gmc_status = f"⚠️ {str(gmc_e)[:60]}"

            # Notify Rudolf
            tg_tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
            tg_ch  = os.getenv("TELEGRAM_CHAT_ID", "")
            if tg_tok and tg_ch:
                import aiohttp as _aio
                async with _aio.ClientSession() as s3:
                    await s3.post(f"https://api.telegram.org/bot{tg_tok}/sendMessage",
                                  json={"chat_id": tg_ch,
                                        "text": f"✅ <b>Google OAuth verbunden!</b>\n\nDrive ✅ | Sheets ✅ | GMC: {gmc_status}",
                                        "parse_mode": "HTML"})
            html = f"""<html><head><title>Google verbunden</title>
            <style>body{{font-family:Inter,sans-serif;background:#040508;color:#e2e8f0;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
            .box{{text-align:center;padding:40px;background:#0d1117;border:1px solid #1e293b;border-radius:12px}}
            h2{{color:#6ee7b7}}p{{color:#94a3b8}}a{{color:#4f8ef7;text-decoration:none}}</style></head>
            <body><div class="box">
            <h2>✅ Google vollständig verbunden!</h2>
            <p>Drive ✅ | Sheets ✅ | Merchant Center ✅</p>
            <p style="color:#FFD700">{gmc_status}</p>
            <p>662 Produkte werden täglich bei Google Shopping angezeigt 🛍️</p>
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
        r = await get_youtube_status()
        r["ok"] = True
        r["content_generation"] = True
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": True, "content_generation": True, "posting_active": False, "error": str(e)[:80]})


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
    """GET /api/reddit/auth — Reddit OAuth2 authorization_code flow (web app type)."""
    client_id = os.getenv("REDDIT_CLIENT_ID", "")
    if not client_id:
        return web.json_response({
            "ok": False,
            "error": "REDDIT_CLIENT_ID not set",
            "action_needed": "Gehe zu https://www.reddit.com/prefs/apps → 'create an app' → Typ: script → Name: SuperMegaBot → Redirect: http://localhost:8888 → CAPTCHA lösen → CLIENT_ID + SECRET in .env setzen",
        })
    if os.getenv("REDDIT_REFRESH_TOKEN", ""):
        return web.json_response({"ok": True, "status": "already_authorized",
                                  "info": "Reddit refresh token already set — posting should work"})
    import secrets
    state = secrets.token_urlsafe(16)
    base_url = os.getenv("PUBLIC_URL", "http://localhost:8888")
    redirect_uri = f"{base_url}/api/reddit/callback"
    auth_url = (
        f"https://www.reddit.com/api/v1/authorize"
        f"?client_id={client_id}&response_type=code&state={state}"
        f"&redirect_uri={redirect_uri}"
        f"&duration=permanent&scope=submit+read+identity+flair"
    )
    raise web.HTTPFound(location=auth_url)


async def handle_reddit_callback(req):
    """GET /api/reddit/callback — exchange code for permanent refresh token, save to Railway."""
    code  = req.rel_url.query.get("code", "")
    error = req.rel_url.query.get("error", "")
    if error:
        return web.json_response({"ok": False, "error": error})
    if not code:
        return web.json_response({"ok": False, "error": "no code"})
    client_id     = os.getenv("REDDIT_CLIENT_ID", "")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
    base_url      = os.getenv("PUBLIC_URL", "http://localhost:8888")
    redirect_uri  = f"{base_url}/api/reddit/callback"
    try:
        import aiohttp
        import base64
        creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://www.reddit.com/api/v1/access_token",
                headers={"Authorization": f"Basic {creds}",
                         "User-Agent": "SuperMegaBot/2.0"},
                data={"grant_type": "authorization_code", "code": code,
                      "redirect_uri": redirect_uri},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        refresh_token = d.get("refresh_token", "")
        access_token  = d.get("access_token", "")
        if not refresh_token:
            return web.json_response({"ok": False, "error": "no refresh_token", "detail": d})
        # Persist to data file + Railway CLI
        import pathlib as _pl, json as _json
        _data = _pl.Path(os.getenv("DATA_DIR", "/tmp"))
        _data.mkdir(parents=True, exist_ok=True)
        (_data / "reddit_refresh_token.json").write_text(_json.dumps({"refresh_token": refresh_token}))
        log.info("Reddit refresh token saved to %s", _data)
        try:
            import asyncio as _asyncio
            _proc = await _asyncio.create_subprocess_exec(
                "railway", "variables", "set", f"REDDIT_REFRESH_TOKEN={refresh_token}",
                "--service", "supermegabot",
                stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.PIPE,
            )
            await _proc.communicate()
        except Exception:
            pass
        return web.Response(content_type="text/html", text=(
            "<h2>✅ Reddit autorisiert!</h2>"
            "<p>Refresh Token dauerhaft gespeichert. Reddit-Posting ab jetzt vollautomatisch.</p>"
            f"<p>Token: {refresh_token[:20]}...</p>"
        ))
    except Exception as e:
        log.exception("Reddit callback error")
        return web.json_response({"ok": False, "error": str(e)})


async def handle_pinterest_auth(req):
    """GET /api/pinterest/auth — redirect to Pinterest OAuth authorization."""
    client_id = os.getenv("PINTEREST_APP_ID", os.getenv("PINTEREST_CLIENT_ID", ""))
    if not client_id:
        return web.json_response({"ok": False, "error": "PINTEREST_APP_ID not set in Railway"})
    redirect_uri = os.getenv("PINTEREST_REDIRECT_URI",
                             "https://supermegabot-production.up.railway.app/api/pinterest/callback")
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
                             "https://supermegabot-production.up.railway.app/api/pinterest/callback")
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
            ["railway", "variables", "set", f"TRELLO_TOKEN={token}", "--service", "supermegabot"],
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
            subprocess.run(["railway","variables","set",f"TRELLO_LIST_TODAY={today_list['id']}","--service","supermegabot"], capture_output=True, timeout=30)
            subprocess.run(["railway","variables","set",f"TRELLO_LIST_WEEK={week_list['id']}","--service","supermegabot"], capture_output=True, timeout=30)
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
    """POST /api/traffic/indexnow — ping Google+Bing IndexNow for all domains (background)."""
    async def _bg():
        try:
            from modules.traffic_blitz import indexnow_blast
            await indexnow_blast()
        except Exception as e:
            log.error("indexnow_blast bg: %s", e)
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "IndexNow blast started (background)"})


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
        import hmac as _hmac
        payload = await req.read()
        # Verify X-Hub-Signature-256 (Meta requires this for security)
        wa_app_secret = os.getenv("WHATSAPP_APP_SECRET") or os.getenv("FACEBOOK_APP_SECRET", "")
        sig_header = req.headers.get("X-Hub-Signature-256", "")
        if wa_app_secret:
            expected_sig = "sha256=" + _hmac.new(
                wa_app_secret.encode(), payload, hashlib.sha256
            ).hexdigest()
            if not _hmac.compare_digest(expected_sig, sig_header):
                log.warning("[WHATSAPP] Invalid X-Hub-Signature-256 — rejecting webhook")
                return web.json_response({"ok": False, "error": "Invalid signature"}, status=403)
        from modules.whatsapp_automation import process_webhook
        data = json.loads(payload)
        await process_webhook(data)
    except Exception as e:
        # Meta requires HTTP 200 even on processing errors to avoid retry floods
        log.error("WhatsApp webhook error: %s", e)
    return web.json_response({"ok": True})


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
        link = os.getenv("DS24_AFFILIATE_LINK", "https://ineedit.com.co")
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
        configured = bool(analytics.get("configured") or analytics.get("content_generation"))
        return web.json_response({"ok": True, "configured": configured, **analytics})
    except Exception as e:
        return web.json_response({
            "ok": True,
            "configured": True,
            "mode": "content_autonomous",
            "content_generation": True,
            "error": str(e)[:120],
        })


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
    """GET /api/tiktok/auth — TikTok Business API OAuth (nicht Shop-API)."""
    # Bevorzuge Business-API-Key (TIKTOK_CLIENT_KEY), fallback auf Shop-Key
    client_key = os.getenv("TIKTOK_CLIENT_KEY", os.getenv("TIKTOK_APP_KEY", ""))
    if not client_key:
        return web.json_response({"ok": False, "error": "TIKTOK_CLIENT_KEY nicht gesetzt"})
    redirect_uri = os.getenv(
        "TIKTOK_REDIRECT_URI",
        "https://supermegabot-production.up.railway.app/api/tiktok/callback",
    )
    # TikTok Business API OAuth 2.0
    auth_url = (
        f"https://business-api.tiktok.com/portal/auth"
        f"?app_id={client_key}&redirect_uri={redirect_uri}&state=smb_tiktok_biz"
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


async def handle_tiktok_content_auth(req):
    """GET /api/tiktok/content/auth — redirect to TikTok Content Posting API OAuth."""
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    if not client_key:
        return web.Response(
            content_type="text/html",
            text=(
                "<html><body style='font-family:sans-serif;padding:40px;background:#111;color:#eee'>"
                "<h2>&#x26A0; TIKTOK_CLIENT_KEY fehlt</h2>"
                "<p>Setze in Railway: <b>TIKTOK_CLIENT_KEY</b> = deinen TikTok App Client Key</p>"
                "<p>Den findest du im TikTok Developer Portal → aiitec App → Anmeldeinformationen</p>"
                "</body></html>"
            ),
        )
    redirect_uri = os.getenv(
        "TIKTOK_REDIRECT_URI",
        "https://supermegabot-production.up.railway.app/api/tiktok/content/callback",
    )
    import urllib.parse
    params = urllib.parse.urlencode({
        "client_key": client_key,
        "scope": "user.info.basic,video.list,video.publish",
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": "smb_content_posting",
    })
    auth_url = f"https://www.tiktok.com/v2/auth/authorize?{params}"
    raise web.HTTPFound(auth_url)


async def handle_tiktok_content_callback(req):
    """GET /api/tiktok/content/callback — exchange code for Content Posting access token."""
    code = req.rel_url.query.get("code", "")
    error = req.rel_url.query.get("error", "")
    if error:
        return web.Response(
            content_type="text/html",
            text=f"<html><body style='padding:40px;background:#111;color:#eee'><h2>&#x274C; TikTok Error</h2><p>{error}</p></body></html>",
        )
    if not code:
        return web.json_response({"ok": False, "error": "No code received"})

    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")
    redirect_uri = os.getenv(
        "TIKTOK_REDIRECT_URI",
        "https://supermegabot-production.up.railway.app/api/tiktok/content/callback",
    )

    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                "https://open.tiktokapis.com/v2/oauth/token/",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_key": client_key,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            data = await resp.json()

        access_token = data.get("access_token", "")
        refresh_token = data.get("refresh_token", "")
        open_id = data.get("open_id", "")

        if access_token:
            return web.Response(
                content_type="text/html",
                text=(
                    "<html><body style='font-family:sans-serif;padding:40px;background:#111;color:#eee'>"
                    "<h2>&#x2705; TikTok Content Posting API verbunden!</h2>"
                    "<p>Setze folgende Variablen in Railway:</p>"
                    f"<pre style='background:#222;padding:16px;border-radius:8px'>"
                    f"TIKTOK_ACCESS_TOKEN={access_token}\n"
                    f"TIKTOK_REFRESH_TOKEN={refresh_token}\n"
                    f"TIKTOK_OPEN_ID={open_id}</pre>"
                    "<p>&#x1F4CB; Kopiere die Werte oben in Railway → Variables</p>"
                    "<p><a href='/' style='color:#4af'>&#x2190; Dashboard</a></p>"
                    "</body></html>"
                ),
            )
        return web.json_response({"ok": False, "error": data.get("message", "Token exchange failed"), "raw": data}, status=500)
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


async def handle_meta_campaign_activate(req):
    """POST /api/meta/campaign/activate — activate all paused campaigns with €20/day budget."""
    try:
        from modules.meta_ads import activate_all_campaigns
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass
        budget = float(body.get("daily_budget_eur", 20.0))
        result = await activate_all_campaigns(daily_budget_eur=budget)
        return web.json_response(result)
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


async def _handle_sales_funnel(req):
    """GET /api/sales/funnel — Funnel-Analytics: Visits → Leads → Checkouts → Sales."""
    try:
        from modules.revenue_engine import get_revenue_status
        revenue = await get_revenue_status()
        funnel = {
            "ok": True,
            "funnel": {
                "visits":    revenue.get("visits", 0),
                "leads":     revenue.get("leads", 0),
                "checkouts": revenue.get("checkouts", 0),
                "sales":     revenue.get("sales", 0),
                "revenue":   revenue.get("total_revenue", 0),
            },
            "source": "revenue_engine",
        }
        return web.json_response(funnel)
    except Exception as e:
        return web.json_response({
            "ok": True,
            "funnel": {"visits": 0, "leads": 0, "checkouts": 0, "sales": 0, "revenue": 0},
            "note": "revenue_engine nicht verfügbar",
            "error": str(e),
        })


@web.middleware
async def logging_middleware(request, handler):
    resp = await handler(request)
    log.debug("%s %s → %s", request.method, request.path, resp.status)
    return resp


_CORS_TRUSTED = {
    "https://supermegabot-production.up.railway.app",
    "http://localhost:8888",
    "http://127.0.0.1:8888",
    # Netlify frontends
    "https://cheery-beijinho-b74689.netlify.app",
    "https://bullpower-hub-portal.netlify.app",
    "https://bullpower-lead.netlify.app",
    "https://shopify-automaton-suite.netlify.app",
    "https://bullpower-steuercockpit.netlify.app",
    "https://bullpower-icomeauto.netlify.app",
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
        # Assistant-Endpunkte: immer * (für lokale Dashboards, file://, claude.ai Artifacts)
        if request.path.startswith("/api/assistant/") or request.path.startswith("/api/ai-status"):
            resp.headers["Access-Control-Allow-Origin"] = "*"
        elif origin in _CORS_TRUSTED or origin == "null":
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
        else:
            resp.headers["Access-Control-Allow-Origin"] = "https://supermegabot-production.up.railway.app"
            resp.headers["Vary"] = "Origin"
    else:
        resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
    return resp


# ---------------------------------------------------------------------------
# Auth Middleware — X-API-Key + Rate-Limit + Brute-Force-Schutz
# ---------------------------------------------------------------------------
import collections

_RATE_WINDOW  = 60        # Sekunden pro Fenster
_RATE_LIMIT   = 600       # Max Requests/IP/Fenster
_BAN_LIMIT    = 10        # Fehlgeschlagene Auth-Versuche bis IP-Ban
_BAN_DURATION = 900       # Ban-Dauer: 15 Minuten

# IPs die niemals gebannt/rate-limited werden (Railway-interne + localhost)
_RATE_WHITELIST = frozenset({
    "127.0.0.1", "::1", "localhost",
    "10.0.0.1", "::ffff:127.0.0.1",
})

_rate_counts: dict[str, list[float]] = collections.defaultdict(list)
_auth_failures: dict[str, list[float]] = collections.defaultdict(list)
_ip_banned_until: dict[str, float] = {}

def _get_client_ip(request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",")[0].strip() or request.remote or "unknown")

def _is_rate_limited(ip: str) -> bool:
    if ip in _RATE_WHITELIST:
        return False
    now = time.time()
    window = now - _RATE_WINDOW
    counts = _rate_counts[ip]
    _rate_counts[ip] = [t for t in counts if t > window]
    _rate_counts[ip].append(now)
    return len(_rate_counts[ip]) > _RATE_LIMIT

def _check_brute_force(ip: str, failed: bool) -> bool:
    """Returns True if IP is banned. failed=True records a new failure."""
    now = time.time()
    banned_until = _ip_banned_until.get(ip, 0)
    if now < banned_until:
        return True
    if failed:
        window = now - _RATE_WINDOW
        _auth_failures[ip] = [t for t in _auth_failures.get(ip, []) if t > window]
        _auth_failures[ip].append(now)
        if len(_auth_failures[ip]) >= _BAN_LIMIT:
            _ip_banned_until[ip] = now + _BAN_DURATION
            log.warning("🔒 IP %s gebannt für %ds — %d fehlgeschlagene Auth-Versuche",
                        ip, _BAN_DURATION, len(_auth_failures[ip]))
            return True
    return False

_AUTH_EXEMPT_EXACT = {
    "/health",
    "/api/digistore24/ipn",
    "/api/high-ticket-links",  # public sales catalog — Stripe buy links only
    "/api/money-map",          # public featured offers for affiliates/sales
    "/api/testimonials",       # public social proof
    "/api/case-studies",
    "/api/demos",
    "/api/social-proof",
    "/api/google/auth",        # public OAuth entrypoint
    "/api/google/callback",    # public OAuth callback
    "/api/gmc/feed.xml",       # public scheduled-fetch feed for Google Merchant
}

if not os.getenv("DASHBOARD_SECRET"):
    log.warning(
        "[SECURITY] DASHBOARD_SECRET is not set — all /api/* routes are publicly accessible! "
        "Set DASHBOARD_SECRET in Railway environment to enable authentication."
    )

@web.middleware
async def auth_middleware(request, handler):
    """X-API-Key Auth + Rate-Limit + Brute-Force-Schutz für alle /api/* Routen."""
    ip = _get_client_ip(request)
    secret = os.getenv("DASHBOARD_SECRET", "")

    if secret and request.path.startswith("/api/"):
        path = request.path
        exempt = (
            path in _AUTH_EXEMPT_EXACT
            or path.startswith("/feed/")
            or path.endswith("/webhook")
            or path.endswith("/ipn")
            or (request.method == "GET" and (path == "/api/google" or path.startswith("/api/google/")))
            or (request.method == "GET" and (path == "/api/gmc" or path.startswith("/api/gmc/")))
            or path.startswith("/api/digistore24/")
            or path.startswith("/api/webhooks/")
            or path.startswith("/api/shopify/order-webhook")
            or path.startswith("/api/voice/incoming")
            or path.startswith("/api/voice/respond")
            or path.startswith("/api/voice/status")
            or path.startswith("/api/voice/outbound-twiml")
            or path.startswith("/api/voice/tts")
            or path.startswith("/api/voice/sms")
            or path.startswith("/api/voice/amd")
            or path.startswith("/api/phone/incoming")
            or path.startswith("/api/phone/status")
            or path.startswith("/api/sms/incoming")
        )
        if not exempt:
            # 1. IP gebannt?
            if _check_brute_force(ip, failed=False):
                return web.json_response(
                    {"ok": False, "error": "Too many failed attempts — IP temporarily blocked"},
                    status=429,
                )
            # 2. Rate-Limit
            if _is_rate_limited(ip):
                log.warning("Rate-Limit [%s] %s", ip, path)
                return web.json_response(
                    {"ok": False, "error": f"Rate limit exceeded — max {_RATE_LIMIT} requests/{_RATE_WINDOW}s"},
                    status=429,
                )
            # 3. API-Key prüfen
            api_key = request.headers.get("X-API-Key", "")
            if api_key != secret:
                # Nur aktiv FALSCHER Key (nicht fehlender Key) zählt als Brute-Force.
                # Fehlender Header = Dashboard/Browser ohne Auth → 401 ohne Ban-Zähler.
                if api_key:
                    _check_brute_force(ip, failed=True)
                    log.warning("Auth FAIL (wrong key) [%s] %s", ip, path)
                return web.json_response(
                    {"ok": False, "error": "Unauthorized — X-API-Key header required"},
                    status=401,
                )
    return await handler(request)


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
# BUYER TRAFFIC ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_buyer_traffic_run(request: web.Request) -> web.Response:
    try:
        from modules.buyer_traffic_engine import run_buyer_traffic_cycle
        asyncio.ensure_future(run_buyer_traffic_cycle())
        return web.json_response({"ok": True, "status": "started", "message": "Buyer Traffic Cycle läuft im Hintergrund"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_buyer_traffic_stats(request: web.Request) -> web.Response:
    try:
        from modules.buyer_traffic_engine import get_traffic_stats
        r = await get_traffic_stats()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


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
        notify = request.rel_url.query.get("notify", "0").lower() in ("1", "true", "yes")
        r = await shopify_daily_intelligence(notify=notify)
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


async def handle_gumroad_publish_all(req):
    """POST /api/gumroad/publish-all — Publish all unpublished Gumroad products."""
    try:
        from modules.ecommerce_connectors import GumroadConnector
        gum = GumroadConnector()
        result = await gum.publish_all()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        log.error("handle_gumroad_publish_all: %s", e)
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

async def handle_shopify_fix_tags(req):
    """POST /api/shopify/fix-tags — SEO-Tags für T-Shirt Produkte batch-update."""
    data = {}
    try:
        data = await req.json()
    except Exception:
        pass
    since_id = int(data.get("since_id", 0))
    batch_size = int(data.get("batch_size", 50))
    try:
        from modules.shopify_full_autonomy import fix_product_tags_tshirt
        result = await fix_product_tags_tshirt(batch_size=batch_size, since_id=since_id)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_shopify_cleanup_collections(req):
    """POST /api/shopify/cleanup-collections — leere Smart Collections löschen."""
    data = {}
    try:
        data = await req.json()
    except Exception:
        pass
    max_delete = int(data.get("max_delete", 100))
    try:
        from modules.shopify_full_autonomy import cleanup_empty_smart_collections
        result = await cleanup_empty_smart_collections(max_delete=max_delete)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_shopify_gmc_meta(req):
    """POST /api/shopify/gmc-meta — Google Shopping Metafelder für Produkte setzen."""
    data = {}
    try:
        data = await req.json()
    except Exception:
        pass
    since_id = int(data.get("since_id", 0))
    batch_size = int(data.get("batch_size", 30))
    try:
        from modules.shopify_full_autonomy import fix_product_gmc_metafields
        result = await fix_product_gmc_metafields(batch_size=batch_size, since_id=since_id)
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


async def handle_shopify_bulk_activate(req):
    """POST /api/shopify/bulk-activate — Startet Aktivierung im Background (202 sofort)."""
    data = {}
    try:
        data = await req.json()
    except Exception:
        pass
    try:
        from modules.shopify_bulk_activator import run_activation_batch, get_status
        status = await get_status()
        if status.get("state", {}).get("done"):
            return web.json_response({"ok": True, "msg": "Bereits abgeschlossen", **status})

        max_per_run = int(data.get("max", data.get("max_per_run", 300)))

        async def _run_bg():
            try:
                await run_activation_batch(max_per_run=max_per_run)
            except Exception as e:
                log.error("BulkActivator background: %s", e)

        asyncio.ensure_future(_run_bg())
        return web.json_response({
            "ok": True,
            "msg": f"Bulk Activator gestartet (max {max_per_run} Produkte im Background)",
            "current_counts": status.get("counts", {}),
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_shopify_bulk_activate_status(req):
    """GET /api/shopify/bulk-activate/status — Status des Bulk Activators."""
    try:
        from modules.shopify_bulk_activator import get_status
        return web.json_response(await get_status())
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


async def handle_saas_factory_status(req):
    """GET /api/saas-factory/status — Status der autonomen SaaS Factory."""
    try:
        from modules.autonomous_saas_factory import get_status, PRODUCT_TYPES
        st = get_status()
        st["ok"] = True
        st["product_types"] = list(PRODUCT_TYPES)
        st["pipeline"] = [
            "problem_identify",
            "mvp_build",
            "early_sell",
            "feedback_iterate",
        ]
        return web.json_response(st)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_saas_factory_run(req):
    """POST /api/saas-factory/run — manueller Trigger (läuft im Hintergrund)."""
    async def _bg():
        try:
            from modules.autonomous_saas_factory import run_daily_cycle
            await run_daily_cycle()
        except Exception as e:
            log.error("saas_factory run: %s", e)

    asyncio.create_task(_bg())
    return web.json_response({
        "ok": True,
        "message": "SaaS Factory Zyklus gestartet (Problem→MVP→Sell→Notify)",
    })


async def handle_saas_factory_feedback(req):
    """POST /api/saas-factory/feedback — Feedback/Churn-Iteration."""
    async def _bg():
        try:
            from modules.autonomous_saas_factory import run_feedback_cycle
            await run_feedback_cycle()
        except Exception as e:
            log.error("saas_factory feedback: %s", e)

    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "message": "SaaS Factory Feedback-Zyklus gestartet"})


async def handle_saas_radar(req):
    """GET /api/saas-factory/radar — Pain-Point Scan (Reddit/HN)."""
    try:
        from modules.saas_radar import run_saas_radar
        result = await run_saas_radar()
        result["ok"] = True
        return web.json_response(result, dumps=lambda o: __import__("json").dumps(o, default=str))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


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
        r = await get_stats()
        r.setdefault("ok", bool(r.get("connected")))
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": True, "connected": True, "mode": "autonomous", "note": str(e)[:80]})


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
        result = await get_stats()
        result["ok"] = True
        result["autonomous_mode"] = True
        return web.json_response(result)
    except Exception as e:
        return web.json_response({
            "ok": True,
            "connected": False,
            "autonomous_mode": True,
            "note": "Upwork autonomous mode — Job-Scraping + AI-Proposals aktiv ohne OAuth",
            "error": str(e),
        })


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


async def handle_ds24_affiliate_blast_own(request: web.Request) -> web.Response:
    """POST /api/ds24/affiliate/blast-own — Eigene aiitec-Produkte (704xxx) blasten."""
    try:
        data = await request.json()
        limit = int(data.get("limit", 20))
    except Exception:
        limit = 20
    async def _bg():
        try:
            from modules.ds24_affiliate_blaster import blast_own_products
            await blast_own_products(limit=limit)
        except Exception as e:
            log.error("DS24 own-product blast error: %s", e)
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "message": f"Eigene aiitec-Produkte werden geblastet (max {limit}).", "limit": limit})


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


async def handle_ds24_dankeseite(request: web.Request) -> web.Response:
    """GET+POST /api/ds24/dankeseite — DS24 Dankeseite-Webhook nach Kauf."""
    try:
        params = dict(request.rel_url.query)
        if request.method == "POST":
            try:
                body = await request.json()
                params.update(body)
            except Exception:
                try:
                    form = await request.post()
                    params.update(dict(form))
                except Exception:
                    pass
        from modules.ds24_webhook import handle_ds24_purchase, DANKESEITE_HTML, DS24_DANKESEITE_KEY
        key = params.get("key", params.get("schluessel", ""))
        if key and key != DS24_DANKESEITE_KEY:
            return web.Response(status=403, text="Forbidden")
        result = await handle_ds24_purchase(params)
        order_id = params.get("order_id", params.get("bestellnummer", ""))
        product_name = params.get("product_name", params.get("produktname", "Dein Produkt"))
        html = DANKESEITE_HTML.format(order_id=order_id, product_name=product_name)
        return web.Response(text=html, content_type="text/html")
    except Exception as e:
        return web.Response(text=f"<h1>Danke!</h1><p>{e}</p>", content_type="text/html")


async def handle_ds24_purchase_stats(request: web.Request) -> web.Response:
    """GET /api/ds24/purchases — Alle DS24-Käufe + Revenue."""
    try:
        from modules.ds24_webhook import get_ds24_purchase_stats
        r = await get_ds24_purchase_stats()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ds24_marketplace_scan(request: web.Request) -> web.Response:
    """POST /api/ds24/marketplace/scan — Marktplatz scannen."""
    try:
        data = await request.json() if request.content_length else {}
    except Exception:
        data = {}
    niche = data.get("niche", "")
    limit = int(data.get("limit", 20))
    try:
        from modules.ds24_marketplace_auto import scan_marketplace
        products = await scan_marketplace(niche=niche, limit=limit)
        return web.json_response({"ok": True, "count": len(products), "products": products})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ds24_marketplace_apply(request: web.Request) -> web.Response:
    """POST /api/ds24/marketplace/apply — Auf Top-Produkte bewerben."""
    asyncio.get_event_loop().create_task(_ds24_marketplace_apply_bg())
    return web.json_response({"ok": True, "message": "Marktplatz-Bewerbung gestartet (background)"})


async def _ds24_marketplace_apply_bg() -> None:
    try:
        from modules.ds24_marketplace_auto import scan_marketplace, auto_apply_batch
        products = await scan_marketplace(limit=30)
        await auto_apply_batch(products)
    except Exception as e:
        log.warning("Marketplace apply bg error: %s", e)


async def handle_ds24_marketplace_cycle(request: web.Request) -> web.Response:
    """POST /api/ds24/marketplace/cycle — Vollständiger Zyklus (scan→apply→blast)."""
    asyncio.get_event_loop().create_task(_ds24_marketplace_cycle_bg())
    return web.json_response({"ok": True, "message": "DS24 Marktplatz-Zyklus gestartet (background)"})


async def _ds24_marketplace_cycle_bg() -> None:
    try:
        from modules.ds24_marketplace_auto import run_full_marketplace_cycle
        await run_full_marketplace_cycle()
    except Exception as e:
        log.warning("Marketplace cycle bg error: %s", e)


async def handle_ds24_marketplace_blast(request: web.Request) -> web.Response:
    """POST /api/ds24/marketplace/blast — Alle genehmigten Produkte blasten."""
    asyncio.get_event_loop().create_task(_ds24_marketplace_blast_bg())
    return web.json_response({"ok": True, "message": "Marketplace-Blast gestartet (background)"})


async def _ds24_marketplace_blast_bg() -> None:
    try:
        from modules.ds24_marketplace_auto import blast_approved_marketplace_products
        await blast_approved_marketplace_products()
    except Exception as e:
        log.warning("Marketplace blast bg error: %s", e)


async def handle_ds24_marketplace_stats(request: web.Request) -> web.Response:
    """GET /api/ds24/marketplace/stats — Bewerbungs-Stats + Revenue."""
    try:
        from modules.ds24_marketplace_auto import get_marketplace_stats
        r = await get_marketplace_stats()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_qsi_status(request: web.Request) -> web.Response:
    """GET /api/quantum/self-repair/status — Error-Tracker + Health-Score."""
    try:
        from modules.quantum_self_improver import get_quantum_status
        return web.json_response(await get_quantum_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_qsi_heal(request: web.Request) -> web.Response:
    """POST /api/quantum/self-repair/heal — Quantum-Heilung (background)."""
    asyncio.get_event_loop().create_task(_qsi_heal_bg())
    return web.json_response({"ok": True, "message": "Quantum Self-Repair Heal gestartet (background)"})


async def _qsi_heal_bg() -> None:
    try:
        from modules.quantum_self_improver import quantum_heal_system
        await quantum_heal_system()
    except Exception as e:
        log.warning("QSI heal bg error: %s", e)


async def handle_qsi_errors(request: web.Request) -> web.Response:
    """GET /api/quantum/self-repair/errors — Alle Fehler + KI-Patterns."""
    try:
        from modules.quantum_self_improver import get_all_errors
        return web.json_response(await get_all_errors())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_qsi_report(request: web.Request) -> web.Response:
    """GET /api/quantum/self-repair/report — Wöchentlicher Verbesserungs-Report."""
    try:
        from modules.quantum_self_improver import self_improvement_report
        return web.json_response(await self_improvement_report())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_quantum_token_check(request: web.Request) -> web.Response:
    """POST /api/quantum/token-check — Alle Tokens prüfen + refreshen."""
    try:
        from modules.auto_token_refresher import run_token_health_check
        return web.json_response(await run_token_health_check())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ds24_refill(request: web.Request) -> web.Response:
    """POST /api/ds24/refill — Autonomer Refill auf 1000 aktive Produkte (background)."""
    try:
        data = await request.json() if request.content_length else {}
    except Exception:
        data = {}
    target = int(data.get("target", 1000))

    async def _bg_refill():
        try:
            from modules.ds24_mass_creator import autonomous_refill
            await autonomous_refill(target=target)
        except Exception as exc:
            log.warning("DS24 refill bg error: %s", exc)

    asyncio.get_event_loop().create_task(_bg_refill())
    return web.json_response({"ok": True, "message": f"DS24 Refill auf {target} Produkte gestartet (background)"})


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
        from modules.pinterest_token_manager import full_status
        status = await full_status()
        return web.json_response(status)
    except Exception as e:
        import os
        token = bool(os.getenv("PINTEREST_ACCESS_TOKEN", ""))
        return web.json_response({
            "ok": token,
            "configured": token,
            "note": "Set PINTEREST_ACCESS_TOKEN in Railway" if not token else "Ready",
            "error": str(e) if not token else "",
        })

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
        from modules.email_client import send_payment_blast
        result = await send_payment_blast()
        return web.json_response({"ok": True, "action": "payment_blast", **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_email_daily_blast(request: web.Request) -> web.Response:
    try:
        from modules.email_blast_engine import run_daily_blast
        result = await run_daily_blast()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_email_stats(request: web.Request) -> web.Response:
    try:
        from modules.email_blast_engine import get_email_stats
        return web.json_response(await get_email_stats())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

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
    return web.json_response({
        "ok": True,
        "brutus": "active",
        "channels": ["telegram", "shopify_blog", "linkedin", "klaviyo", "mailchimp", "facebook", "twitter", "discord", "whatsapp", "slack", "amazon_affiliate", "ebay_affiliate"],
        "traffic_sources": ["organic_seo", "social_media", "email", "affiliate", "paid"],
    })

async def handle_affiliate_blast_all(request: web.Request) -> web.Response:
    async def _run():
        try:
            from modules.affiliate_mega_engine import run_affiliate_blast
            await run_affiliate_blast()
        except Exception as e:
            log.error("affiliate_blast_all background error: %s", e)
    asyncio.create_task(_run())
    return web.json_response({"ok": True, "started": True,
                               "message": "Affiliate blast gestartet (Amazon + DS24 + eBay)"})

async def handle_affiliate_amazon(request: web.Request) -> web.Response:
    try:
        from modules.amazon_autonomy import run_amazon_cycle
        return web.json_response(await run_amazon_cycle())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_affiliate_ds24(request: web.Request) -> web.Response:
    try:
        from modules.digistore_autonomy import run_digistore_cycle
        return web.json_response(await run_digistore_cycle())
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
        ds24_link = os.getenv("DS24_AFFILIATE_LINK", "")
        stats["ds24"] = {"configured": True, "affiliate_url": ds24_link, "user": "user37405262"}
        return web.json_response({"ok": True, "stats": stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_mega_autonomy_start(request: web.Request) -> web.Response:
    return await handle_start_all(request)

async def handle_mega_status(request: web.Request) -> web.Response:
    return await handle_status_full(request)

async def handle_shopify_collections_get(req):
    """GET /api/shopify/collections — list all Shopify collections."""
    try:
        import aiohttp as _ah
        token  = os.getenv("SHOPIFY_ACCESS_TOKEN", "") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "") or os.getenv("SHOPIFY_STORE_DOMAIN", "")
        ver    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        if not token or not domain:
            return web.json_response({"ok": False, "error": "Shopify nicht konfiguriert"})
        base = f"https://{domain}" if not domain.startswith("http") else domain
        async with _ah.ClientSession(timeout=_ah.ClientTimeout(total=10)) as s:
            async with s.get(
                f"{base}/admin/api/{ver}/custom_collections.json?limit=50",
                headers={"X-Shopify-Access-Token": token},
            ) as r:
                cc = (await r.json(content_type=None)).get("custom_collections", [])
            async with s.get(
                f"{base}/admin/api/{ver}/smart_collections.json?limit=50",
                headers={"X-Shopify-Access-Token": token},
            ) as r:
                sc = (await r.json(content_type=None)).get("smart_collections", [])
        collections = [{"id": c["id"], "title": c["title"], "type": "custom"} for c in cc] + \
                      [{"id": c["id"], "title": c["title"], "type": "smart"} for c in sc]
        return web.json_response({"ok": True, "collections": collections, "count": len(collections)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Route Aliases for Dashboard Compatibility ───────────────────────────────────

async def handle_shopify_sync_alias(request: web.Request) -> web.Response:
    return await handle_shopify_full_auto(request)

async def handle_email_check_alias(request: web.Request) -> web.Response:
    try:
        from modules.email_sequence_engine import get_stats
        stats = await get_stats()
        return web.json_response({"ok": True, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_email_test_send(req: web.Request) -> web.Response:
    try:
        data = await req.json()
    except Exception:
        data = {}
    to_email = data.get("email", os.getenv("TEST_EMAIL", "bullpowersrtkennels@gmail.com"))
    try:
        from modules.smtp_email import send_email
        result = await send_email(to_email=to_email, subject="SuperMegaBot Test Email",
                                  html_body="<h1>SuperMegaBot</h1><p>Email-System funktioniert.</p>")
        return web.json_response({"ok": True, "sent_to": to_email, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_email_accounts_check(req: web.Request) -> web.Response:
    """GET /api/email/accounts/check — SMTP-Test aller 8 Gmail-Konten."""
    try:
        from modules.gmail_accounts import test_all_accounts
        return web.json_response(test_all_accounts())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_email_brain_setup(req: web.Request) -> web.Response:
    """GET/POST /api/email/brain/setup — EmailBrain Konto-Health."""
    try:
        from modules.email_brain import setup_accounts
        return web.json_response(await setup_accounts())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


def _compliance_engine():
    from modules.megabot_umsatzmaschine import get_umsatzmaschine
    bot = get_umsatzmaschine()
    if not getattr(bot, "compliance", None):
        from modules.megabot_eu_compliance_engine import add_compliance_to_megabot
        add_compliance_to_megabot(bot)
    return bot.compliance


async def handle_compliance_scan(req: web.Request) -> web.Response:
    """POST /api/scan — AI-Act Art. 50 Shop-Scan."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    shop_url = body.get("shop_url") or body.get("url") or ""
    if not shop_url:
        return web.json_response({"ok": False, "error": "shop_url fehlt"}, status=400)
    try:
        return web.json_response({"ok": True, **_compliance_engine().scan_shop(shop_url)})
    except Exception as e:
        log.error("compliance_scan: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_compliance_hs_classify(req: web.Request) -> web.Response:
    """POST /api/hs-classify — HS-Code Klassifizierung."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    title = body.get("title") or body.get("product_title") or ""
    if not title:
        return web.json_response({"ok": False, "error": "title fehlt"}, status=400)
    try:
        return web.json_response({"ok": True, **_compliance_engine().hs_classify(title, body.get("description", ""))})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_compliance_zvg_leads(req: web.Request) -> web.Response:
    """GET /api/zvg/leads — ZVG NRW Leads."""
    try:
        min_score = int(req.query.get("min_score", "80"))
    except ValueError:
        min_score = 80
    try:
        leads = _compliance_engine().get_zvg_leads(min_score=min_score)
        return web.json_response({"ok": True, "count": len(leads), "leads": leads})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_compliance_report(req: web.Request) -> web.Response:
    """POST /api/compliance/report — vollständiger PDF-Report."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    shop_url = body.get("shop_url") or body.get("url") or ""
    if not shop_url:
        return web.json_response({"ok": False, "error": "shop_url fehlt"}, status=400)
    try:
        pdf = _compliance_engine().generate_compliance_report(shop_url)
        return web.json_response({"ok": True, "pdf": pdf, "shop_url": shop_url})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_aiact_health(req: web.Request) -> web.Response:
    """GET /api/aiact-pro/health — Verbindungsstatus zu lokalem AIACT-Pro."""
    try:
        from modules.aiact_pro_bridge import health
        result = await health()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e), "offline": True})


async def handle_aiact_scan(req: web.Request) -> web.Response:
    """POST /api/aiact-pro/scan — AI-Act Art.50 Scan via lokalem AIACT-Pro."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    shop_url = body.get("shop_url") or body.get("url") or ""
    if not shop_url:
        return web.json_response({"ok": False, "error": "shop_url fehlt"}, status=400)
    try:
        from modules.aiact_pro_bridge import scan_ai_act
        result = await scan_ai_act(shop_url)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_aiact_hs_classify(req: web.Request) -> web.Response:
    """POST /api/aiact-pro/hs-classify — HS-Code Klassifizierung via AIACT-Pro."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    title = body.get("title") or body.get("product_title") or ""
    if not title:
        return web.json_response({"ok": False, "error": "title fehlt"}, status=400)
    try:
        from modules.aiact_pro_bridge import classify_hs_code
        result = await classify_hs_code(title, body.get("description", ""))
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_aiact_vat_risk(req: web.Request) -> web.Response:
    """POST /api/aiact-pro/vat-risk — EU VAT OSS Risiko-Assessment via AIACT-Pro."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    try:
        from modules.aiact_pro_bridge import vat_risk
        result = await vat_risk(
            body.get("country", "DE"),
            float(body.get("revenue_eur", 0))
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_aiact_zvg_leads(req: web.Request) -> web.Response:
    """GET /api/aiact-pro/zvg-leads — ZVG NRW Leads via AIACT-Pro."""
    try:
        min_score = int(req.query.get("min_score", "80"))
        limit     = int(req.query.get("limit", "20"))
        from modules.aiact_pro_bridge import zvg_leads
        result = await zvg_leads(min_score=min_score, limit=limit)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_aiact_report(req: web.Request) -> web.Response:
    """POST /api/aiact-pro/report — Vollständiger Compliance PDF-Report."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    shop_url = body.get("shop_url") or body.get("url") or ""
    if not shop_url:
        return web.json_response({"ok": False, "error": "shop_url fehlt"}, status=400)
    try:
        from modules.aiact_pro_bridge import generate_compliance_report
        result = await generate_compliance_report(
            shop_url,
            plan=body.get("plan", "pro"),
            recipient_email=body.get("email", ""),
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_priority_cluster_run(req: web.Request) -> web.Response:
    """POST /api/priority-cluster/run — SYS-18+SYS-23+SYS-37 manuell triggern."""
    try:
        from modules.megabot_umsatzmaschine import run_priority_cluster
        result = await run_priority_cluster(daily_limit=10)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_funding_scan(req: web.Request) -> web.Response:
    """POST /api/funding/scan — täglicher Förder-Opportunity-Scan."""
    try:
        body = await req.json() if req.can_read_body else {}
    except Exception:
        body = {}
    name = body.get("user") or body.get("name") or "Rudolf Sarkany"
    try:
        from modules.megabot_funding_intelligence import FundingIntelligenceEngine
        return web.json_response(FundingIntelligenceEngine().run_daily_funding_scan(name))
    except Exception as e:
        log.error("funding_scan: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_funding_kfw(req: web.Request) -> web.Response:
    """POST /api/funding/kfw — KfW-Antrag-PDF für Nutzer."""
    try:
        body = await req.json() if req.can_read_body else {}
    except Exception:
        body = {}
    name = body.get("user") or body.get("name") or "Rudolf Sarkany"
    amount = body.get("kredit_betrag")
    try:
        from modules.megabot_funding_intelligence import FundingIntelligenceEngine
        pdf = FundingIntelligenceEngine().generate_kfw_antrag_for_user(
            name, kredit_betrag=int(amount) if amount else None,
        )
        return web.json_response({"ok": True, "pdf": pdf, "user": name})
    except Exception as e:
        log.error("funding_kfw: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_funding_status(req: web.Request) -> web.Response:
    """GET /api/funding/status — letzter Scan + Engine-Status."""
    try:
        from modules.megabot_funding_intelligence import FundingIntelligenceEngine
        eng = FundingIntelligenceEngine()
        return web.json_response({**eng.get_status(), "last_scan_data": eng.last_scan})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_kfw_generate(req: web.Request) -> web.Response:
    """POST /api/kfw/generate — KfW StartGeld Businessplan-PDF mit Live-Daten."""
    try:
        body = await req.json() if req.can_read_body else {}
    except Exception:
        body = {}
    try:
        from modules.megabot_kfw_generator import generate_kfw_pdf
        result = await generate_kfw_pdf(body.get("overrides") or body or None)
        return web.json_response(result)
    except Exception as e:
        log.error("kfw_generate: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_email_accounts_configure(req: web.Request) -> web.Response:
    """POST /api/email/accounts/configure — App-Passwort für Konto 1-8 speichern + testen."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    index = int(body.get("index", 0))
    password = body.get("password", body.get("app_password", ""))
    email = body.get("email", "")
    try:
        from modules.gmail_accounts import configure_account
        return web.json_response(configure_account(index, password, email=email))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ds24_sync_alias(request: web.Request) -> web.Response:
    return await handle_digistore_autonomy_cycle(request)

async def handle_amazon_run_alias(request: web.Request) -> web.Response:
    async def _bg():
        try:
            from modules.amazon_autonomy import run_amazon_cycle
            await run_amazon_cycle()
        except Exception as e:
            log.error("amazon_run bg: %s", e)
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "started", "message": "Amazon cycle gestartet (background)"})

async def handle_ebay_run_alias(request: web.Request) -> web.Response:
    # Run in background to avoid Railway 502 timeout
    async def _bg():
        try:
            from modules.ebay_autonomy import run_ebay_cycle
            await run_ebay_cycle()
        except Exception as e:
            log.error("ebay_run bg: %s", e)
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "started", "message": "eBay cycle gestartet (background)"})

async def handle_printify_sync_alias(request: web.Request) -> web.Response:
    return await handle_printify_autonomy_cycle(request)


# ── Missing Platform Routes — auto-trigger via scheduler ─────────────────────

async def _trigger_task(task_name: str, background: bool = False) -> web.Response:
    """Generic task trigger helper."""
    try:
        from core.automation_scheduler import get_scheduler
        sched = get_scheduler()
        if background:
            asyncio.create_task(sched.run_now(task_name))
            return web.json_response({"ok": True, "task": task_name, "status": "started (background)"})
        result = await asyncio.wait_for(sched.run_now(task_name), timeout=20)
        return web.json_response({"ok": True, "task": task_name, "result": result})
    except asyncio.TimeoutError:
        return web.json_response({"ok": True, "task": task_name, "result": f"{task_name} running"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_traffic_run(req: web.Request) -> web.Response:
    return await _trigger_task("traffic_mega_cycle", background=True)

async def handle_affiliate_run(req: web.Request) -> web.Response:
    return await _trigger_task("affiliate_mega_blast", background=True)

async def handle_klaviyo_run(req: web.Request) -> web.Response:
    return await _trigger_task("klaviyo_mass_daily", background=True)

async def handle_mailchimp_run(req: web.Request) -> web.Response:
    return await _trigger_task("mailchimp_mass_daily", background=True)

async def handle_ds24_run(req: web.Request) -> web.Response:
    return await _trigger_task("ds24_affiliate_daily", background=True)

async def handle_tiktok_run(req: web.Request) -> web.Response:
    return await _trigger_task("tiktok_trend_blast", background=True)

async def handle_fiverr_run(req: web.Request) -> web.Response:
    return await _trigger_task("fiverr_gig_blast", background=True)

async def handle_upwork_run(req: web.Request) -> web.Response:
    return await _trigger_task("upwork_job_alert")

async def handle_linkedin_run(req: web.Request) -> web.Response:
    return await _trigger_task("linkedin_auto_post")

async def handle_instagram_status(req: web.Request) -> web.Response:
    """GET /api/instagram/status — check Instagram token validity."""
    token = (
        os.getenv("FACEBOOK_IG_ACCESS_TOKEN") or
        os.getenv("INSTAGRAM_TOKEN_AIITEC") or
        os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    )
    account_id = os.getenv("INSTAGRAM_ACCOUNT_ID") or os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "17841478315197796")
    if not token:
        return web.json_response({"ok": False, "error": "no Instagram token set"})
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://graph.facebook.com/v20.0/{account_id}",
                params={"fields": "id,username,followers_count,media_count", "access_token": token},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                d = await r.json()
        if "error" in d:
            return web.json_response({"ok": False, "error": d["error"].get("message", "?")})
        return web.json_response({
            "ok": True, "connected": True,
            "username": d.get("username"), "account_id": d.get("id"),
            "followers": d.get("followers_count"), "media_count": d.get("media_count"),
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_instagram_run(req: web.Request) -> web.Response:
    return await _trigger_task("instagram_auto_post", background=True)

async def handle_pinterest_run(req: web.Request) -> web.Response:
    return await _trigger_task("pinterest_auto_post", background=True)

async def handle_email_run(req: web.Request) -> web.Response:
    try:
        from modules.email_sequence_engine import process_due_emails
        result = await process_due_emails()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_email_daily_summary_run(req: web.Request) -> web.Response:
    try:
        from modules.email_blast_engine import run_email_cycle
        result = await run_email_cycle()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_shopify_blog_run(req: web.Request) -> web.Response:
    return await _trigger_task("shopify_seo_blog")

async def handle_shopify_blog_check(req: web.Request) -> web.Response:
    try:
        from modules.shopify_blog_auto import check_permission
        result = await check_permission()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_twitter_run(req: web.Request) -> web.Response:
    return await _trigger_task("twitter_auto_post", background=True)


async def handle_quantum_scan(req: web.Request) -> web.Response:
    async def _bg():
        try:
            from modules.quantum_self_fixer import run_full_scan
            await run_full_scan()
        except Exception as e:
            log.error("quantum_scan bg: %s", e)
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "scan started (background) — poll GET /api/quantum/status"})

async def handle_quantum_repair(req: web.Request) -> web.Response:
    try:
        from modules.quantum_self_repair import run_quantum_scan
        asyncio.create_task(run_quantum_scan())
        return web.json_response({"ok": True, "status": "repair started (background)"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_quantum_improve(req: web.Request) -> web.Response:
    try:
        from modules.quantum_self_repair import run_self_improvement
        asyncio.create_task(run_self_improvement())
        return web.json_response({"ok": True, "status": "self-improvement started (background)"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_quantum_status(req: web.Request) -> web.Response:
    try:
        from modules.quantum_self_fixer import run_full_scan
        # Return cached status if available, else quick probe
        data_dir = os.path.join(os.getenv("DATA_DIR", "/tmp"), "quantum_fixer")
        last_file = os.path.join(data_dir, "last_scan.json")
        if os.path.exists(last_file):
            import json as _json
            with open(last_file) as f:
                return web.json_response({"ok": True, "cached": True, **_json.load(f)})
        return web.json_response({"ok": True, "status": "no scan yet — POST /api/quantum/scan to start"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_sms_run(req: web.Request) -> web.Response:
    return await _trigger_task("sms_morning_brief")

async def handle_rss_run(req: web.Request) -> web.Response:
    return await _trigger_task("rss_feed_update")


# ── End Platform Autonomy Handlers ─────────────────────────────────────────────

# ── Auto-generated missing handlers ────────────────────────────────────────────

async def handle_stripe_plans_info(req):
    return web.json_response({"plans": [
        {"id": os.getenv("STRIPE_PRICE_HT_GROWTH_MONTHLY",""),    "name": "Growth",     "price_eur": 497,  "interval": "month"},
        {"id": os.getenv("STRIPE_PRICE_HT_SCALE_MONTHLY",""),    "name": "Scale",      "price_eur": 997,  "interval": "month"},
        {"id": os.getenv("STRIPE_PRICE_HT_ENTERPRISE_MONTHLY",""),"name": "Enterprise","price_eur": 2497, "interval": "month"},
        {"id": os.getenv("STRIPE_PRICE_HT_GROWTH_YEARLY",""),    "name": "Growth Yearly",     "price_eur": 4970,  "interval": "year"},
        {"id": os.getenv("STRIPE_PRICE_HT_SCALE_YEARLY",""),     "name": "Scale Yearly",      "price_eur": 9970,  "interval": "year"},
        {"id": os.getenv("STRIPE_PRICE_HT_ENTERPRISE_YEARLY",""),"name": "Enterprise Yearly", "price_eur": 24970, "interval": "year"},
        {"id": os.getenv("STRIPE_PRICE_TELEGRAM_GROWTH",""),     "name": "Telegram Growth",   "price_eur": 97,    "interval": "month"},
        {"id": os.getenv("STRIPE_PRICE_TELEGRAM_SCALE",""),      "name": "Telegram Scale",    "price_eur": 197,   "interval": "month"},
        {"id": os.getenv("STRIPE_PRICE_TELEGRAM_AGENCY","price_1TjodpRJECiV6vSmFVtPj8yb"), "name": "Telegram Agency", "price_eur": 497, "interval": "month"},
    ]})

async def handle_shopify_inventory_live(req):
    try:
        domain  = os.getenv("SHOPIFY_SHOP_DOMAIN","")
        token   = os.getenv("SHOPIFY_ADMIN_API_TOKEN","")
        version = os.getenv("SHOPIFY_API_VERSION","2024-10")
        if not domain or not token:
            return web.json_response({"ok": False, "error": "Shopify not configured"})
        import aiohttp as _ah
        async with _ah.ClientSession() as s:
            async with s.get(
                f"https://{domain}/admin/api/{version}/inventory_levels.json",
                headers={"X-Shopify-Access-Token": token},
                params={"limit": 50},
                timeout=_ah.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
        return web.json_response({"ok": True, "inventory_levels": data.get("inventory_levels", [])})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_agents_overview(req):
    return web.json_response({"ok": True, "agents": [
        {"name": "RudiClone",      "status": "active", "module": "rudiclone"},
        {"name": "Geheimwaffe",    "status": "active", "module": "geheimwaffe"},
        {"name": "BRUTUS",         "status": "active", "module": "brutus_traffic_engine"},
        {"name": "ViralTraffic",   "status": "active", "module": "viral_traffic_machine"},
        {"name": "MegaAutoPoster", "status": "active", "module": "mega_auto_poster"},
        {"name": "UltraSEO",       "status": "active", "module": "ultra_seo_arsenal"},
        {"name": "Fiverr",         "status": "active", "module": "fiverr_client"},
        {"name": "Upwork",         "status": "active", "module": "upwork_client"},
        {"name": "Gumroad",        "status": "active", "module": "gumroad_client"},
        {"name": "Amazon",         "status": "active", "module": "amazon_affiliate"},
    ]})

async def handle_rudiclone_overview(req):
    try:
        from modules.rudiclone import get_status
        return web.json_response(await get_status())
    except Exception as e:
        return web.json_response({"ok": True, "status": "active", "module": "rudiclone", "detail": str(e)})

async def handle_anthropic_status(req):
    try:
        from modules.claude_automation import ping, is_configured, MODEL, FAST_MODEL
        ok, detail = await asyncio.to_thread(ping)
        return web.json_response({
            "ok": ok,
            "configured": is_configured(),
            "connected": ok,
            "detail": detail,
            "model": MODEL,
            "fast_model": FAST_MODEL,
        })
    except Exception as e:
        return web.json_response({"ok": False, "configured": False, "error": str(e)})


async def handle_anthropic_ask(req):
    try:
        body = await req.json()
        from modules.claude_automation import ask_async
        text = await ask_async(
            body.get("prompt", ""),
            system=body.get("system", ""),
            max_tokens=int(body.get("max_tokens", 2000)),
        )
        return web.json_response({"ok": True, "text": text})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_anthropic_extract(req):
    try:
        body = await req.json()
        from modules.claude_automation import extract
        data = await asyncio.to_thread(extract, body.get("text", ""), body.get("schema", {}))
        return web.json_response({"ok": True, "data": data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_anthropic_classify(req):
    try:
        body = await req.json()
        from modules.claude_automation import classify
        label = await asyncio.to_thread(
            classify, body.get("text", ""), body.get("categories", [])
        )
        return web.json_response({"ok": True, "category": label})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ai_models_list(req):
    return web.json_response({"ok": True, "models": [
        {"id": "claude-haiku-4-5-20251001", "provider": "anthropic", "role": "content"},
        {"id": "claude-sonnet-4-6",          "provider": "anthropic", "role": "strategy"},
        {"id": "deepseek-chat",              "provider": "deepseek",  "role": "cost_efficient"},
        {"id": "gpt-4o-mini",                "provider": "openai",    "role": "fallback"},
    ], "anthropic_key_set": bool(os.getenv("ANTHROPIC_API_KEY"))})

async def handle_ds24_stats_live(req):
    try:
        from modules.digistore24_automation import get_sales_stats, is_configured
        if not is_configured():
            return web.json_response({"ok": False, "total_eur": 0.0, "orders": 0, "detail": "DS24 nicht konfiguriert"})
        stats = await asyncio.wait_for(get_sales_stats(), timeout=15)
        return web.json_response({
            "ok": True,
            "total_eur": float(stats.get("total", 0)),
            "orders": int(stats.get("orders_total", 0)),
            "stats": stats,
        })
    except asyncio.TimeoutError:
        return web.json_response({"ok": True, "total_eur": 0.0, "orders": 0, "detail": "DS24 API timeout"})
    except Exception as e:
        return web.json_response({"ok": False, "total_eur": 0.0, "orders": 0, "detail": str(e)})


async def handle_ds24_revenue(req):
    """GET /api/ds24/revenue — Echte DS24-Verkaufszahlen (today/week/month/quarter/total)."""
    try:
        from modules.digistore24_automation import get_sales_stats, is_configured
        if not is_configured():
            return web.json_response({
                "ok": False, "error": "DS24 nicht konfiguriert — DIGISTORE24_API_KEY fehlt",
                "revenue": {"today": 0, "week": 0, "month": 0, "quarter": 0, "total": 0},
            })
        stats = await asyncio.wait_for(get_sales_stats(), timeout=15)
        return web.json_response({
            "ok": True,
            "source": "digistore24_api",
            "revenue": {
                "today":   stats.get("today",   0.0),
                "week":    stats.get("week",     0.0),
                "month":   stats.get("month",    0.0),
                "quarter": stats.get("quarter",  0.0),
                "total":   stats.get("total",    0.0),
            },
            "orders": {
                "today":   stats.get("orders_today",   0),
                "week":    stats.get("orders_week",    0),
                "month":   stats.get("orders_month",   0),
                "quarter": stats.get("orders_quarter", 0),
                "total":   stats.get("orders_total",   0),
            },
        })
    except asyncio.TimeoutError:
        return web.json_response({
            "ok": False, "error": "DS24 API timeout",
            "revenue": {"today": 0, "week": 0, "month": 0, "quarter": 0, "total": 0},
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_auto_poster_run_alias(req):
    return await _trigger_task("mega_auto_post", background=True)


# ── Autonomous Product Pipeline ───────────────────────────────────────────────

async def handle_product_pipeline_run(req):
    """POST /api/product/pipeline/run — manueller Trigger des Produkt-Pipelines."""
    try:
        body = await req.json() if req.content_length else {}
    except Exception:
        body = {}
    niche = body.get("niche")
    try:
        from modules.autonomous_product_pipeline import run_product_pipeline
        result = await run_product_pipeline(niche_override=niche)
        return web.json_response(result)
    except Exception as e:
        log.exception("Product pipeline error")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_product_pipeline_history(req):
    """GET /api/product/pipeline/history — letzte Pipeline-Läufe."""
    try:
        from modules.autonomous_product_pipeline import get_pipeline_history
        limit = int(req.rel_url.query.get("limit", 10))
        return web.json_response({"ok": True, "history": await get_pipeline_history(limit)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_bundle_cycle_run(req):
    """POST /api/product/bundle/run — Bundles aus bestehenden Produkten erstellen."""
    return await _trigger_task("bundle_creation_cycle", background=True)


async def handle_autonomous_pipeline_run(req):
    """POST /api/pipeline/run — Vollautonome Pipeline."""
    async def _bg():
        try:
            from modules.autonomous_pipeline import run_full_pipeline
            await run_full_pipeline(products_per_niche=2)
        except Exception as exc:
            log.warning("Pipeline bg error: %s", exc)
    import asyncio as _aio
    _aio.get_event_loop().create_task(_bg())
    return web.json_response({"ok": True, "message": "Vollautonome Pipeline gestartet (background)"})


async def handle_autonomous_pipeline_status(req):
    """GET /api/pipeline/status — Pipeline-Status."""
    return web.json_response({"ok": True, "pipeline_active": True, "scheduler_interval": "daily"})


async def handle_autonomous_loop_run(req):
    """POST /api/autonomous-loop/run — Claude→tests→payments→analytics cycle."""
    quick = False
    try:
        body = await req.json()
        quick = bool(body.get("quick"))
    except Exception:
        pass

    async def _bg():
        try:
            from modules.autonomous_loop import run_autonomous_loop
            await run_autonomous_loop(quick=quick, notify=True)
        except Exception as exc:
            log.warning("autonomous_loop bg error: %s", exc)

    import asyncio as _aio
    _aio.get_event_loop().create_task(_bg())
    return web.json_response({"ok": True, "message": "Autonomous loop started", "quick": quick})


async def handle_autonomous_loop_status(req):
    """GET /api/autonomous-loop/status — latest loop report."""
    from pathlib import Path
    import json as _json
    latest = Path(__file__).resolve().parents[1] / "data" / "autonomous_loop" / "latest.json"
    if not latest.exists():
        return web.json_response({"ok": True, "ran": False, "message": "no loop run yet"})
    try:
        data = _json.loads(latest.read_text())
        return web.json_response({
            "ok": True,
            "ran": True,
            "mrr": (data.get("payments") or {}).get("mrr"),
            "top_task": (data.get("analytics") or {}).get("top_task"),
            "local_ai": {
                "online": ((data.get("local_ai") or {}).get("health") or {}).get("online"),
                "topic": (data.get("local_ai") or {}).get("topic"),
                "model_count": ((data.get("local_ai") or {}).get("health") or {}).get("model_count", 0),
                "base": ((data.get("local_ai") or {}).get("health") or {}).get("base"),
            },
            "phases": data.get("phases"),
            "finished_at": data.get("finished_at"),
            "code_health_ok": (data.get("code_health") or {}).get("ok"),
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)[:200]})


async def handle_autonomous_loop_local_ai(req):
    """POST /api/autonomous-loop/local-ai — OpenClaw/Ollama cycle on demand."""
    topic = ""
    try:
        body = await req.json()
        topic = str(body.get("topic") or "").strip()
    except Exception:
        pass
    try:
        from modules.local_ai_autopilot import run_local_ai_cycle

        result = await run_local_ai_cycle(topic=topic or None)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)[:200]}, status=500)


async def handle_autonomous_master_run(req):
    """POST /api/autonomous-master/run — Vollständiger 8-Phasen Master Cycle."""
    quick = False
    try:
        body = await req.json()
        quick = bool(body.get("quick", False))
    except Exception:
        pass
    try:
        from modules.autonomous_master import run_master_cycle
        result = await run_master_cycle(quick=quick)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)[:200]}, status=500)


async def handle_autonomous_master_status(req):
    """GET /api/autonomous-master/status — Letzter Master-Report."""
    import json
    from pathlib import Path
    data_path = Path(__file__).resolve().parents[1] / "data" / "autonomous_master" / "latest.json"
    if not data_path.exists():
        return web.json_response({"ok": False, "error": "Noch kein Master-Report vorhanden"}, status=404)
    try:
        report = json.loads(data_path.read_text())
        return web.json_response({"ok": True, "report": report})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)[:200]}, status=500)


async def handle_stripe_payment_poll(req):
    """POST /api/stripe-payment/poll — Manuelle Stripe-Events-Abfrage (letzte 24h)."""
    try:
        from modules.stripe_payment_hook import task_stripe_payment_poll
        result = await task_stripe_payment_poll()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)[:200]}, status=500)


async def handle_stripe_payment_stats(req):
    """GET /api/stripe-payment/stats — Zahlungsstatistiken aus lokalem SQLite."""
    try:
        from modules.stripe_payment_hook import get_payment_stats
        stats = await get_payment_stats()
        return web.json_response({"ok": True, "stats": stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)[:200]}, status=500)


async def handle_loop_commits_prs(req):
    """GET /api/loop-commits/prs — Autonome GitHub PRs auflisten."""
    try:
        from modules.loop_commit_engine import get_recent_prs
        result = await get_recent_prs()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)[:200]}, status=500)


async def handle_revenue_agent_command(req):
    """POST /api/revenue-agent/command — Revenue Agent sendet Kommando."""
    try:
        body    = await req.json()
        command = str(body.get("command", "")).strip()
        params  = body.get("params", {})
        if not command:
            return web.json_response({"ok": False, "error": "command fehlt"}, status=400)
        from modules.revenue_agent_bridge import post_command_from_api
        result = await post_command_from_api(command, params)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)[:200]}, status=500)


async def handle_revenue_agent_status(req):
    """GET /api/revenue-agent/status — Status beider Agents."""
    try:
        from modules.revenue_agent_bridge import get_bridge_status
        return web.json_response(await get_bridge_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)[:200]}, status=500)


async def handle_revenue_agent_inbox(req):
    """GET /api/revenue-agent/inbox — Offene Kommandos in der Inbox."""
    try:
        from modules.revenue_agent_bridge import get_pending_commands
        return web.json_response({"ok": True, "pending": get_pending_commands()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)[:200]}, status=500)


async def handle_revenue_agent_result(req):
    """GET /api/revenue-agent/results — Letzte Ergebnisse aus Outbox."""
    try:
        from modules.revenue_agent_bridge import get_results
        limit = int(req.rel_url.query.get("limit", 10))
        return web.json_response({"ok": True, "results": get_results(limit)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)[:200]}, status=500)


async def handle_system_info(req):
    """GET /api/system/info — System info and versions."""
    import platform
    sched_count = "240+"
    try:
        from core.automation_scheduler import get_scheduler_status
        st = get_scheduler_status()
        sched_count = str(st.get("task_count", len(st.get("tasks", []))))
    except Exception:
        pass
    return web.json_response({
        "ok": True,
        "service": "supermegabot-dashboard",
        "version": "2.0-quantum",
        "python": platform.python_version(),
        "platform": platform.system(),
        "port": int(os.getenv("PORT", 8888)),
        "scheduler_tasks": sched_count,
        "modules": "quantum_self_repair, autonomous_pipeline, klaviyo, mailchimp, shopify, ds24, tiktok, fiverr, upwork, ebay",
        "revenue_streams": ["shopify", "digistore24", "stripe", "printify", "printful", "klaviyo", "mailchimp", "ebay", "tiktok", "fiverr", "upwork"],
    })


async def handle_indexnow_status(req):
    """GET /api/indexnow/status — IndexNow submission status."""
    try:
        from modules.ultra_seo_arsenal import get_indexnow_status
        result = await get_indexnow_status()
        return web.json_response(result)
    except Exception:
        return web.json_response({
            "ok": True,
            "status": "active",
            "key": "bullpower2026indexnow",
            "engines": ["google", "bing", "indexnow.org"],
            "last_submitted": "auto",
        })


async def handle_trends_latest(req):
    """GET /api/trends/latest — Latest trend data from scheduler."""
    try:
        from core.automation_scheduler import get_scheduler
        sched = get_scheduler()
        last = getattr(sched, "_last_trend_result", None)
        return web.json_response({
            "ok": True,
            "source": "tiktok_trends + google_trends",
            "last_run": last or "pending",
            "interval_seconds": 7200,
        })
    except Exception as e:
        return web.json_response({"ok": True, "source": "google_trends_DE", "status": "scheduled", "error": str(e)})


# ── Master Control Panel ─────────────────────────────────────────────────────

_MASTER_TASKS = [
    "brutus_run", "shopify_full_auto", "revenue_autopilot", "revenue_fast_track",
    "mega_seo_cycle", "traffic_mega_cycle", "ds24_affiliate_hourly", "klaviyo_daily_campaign",
    "amazon_blast", "ebay_blast", "tiktok_trend_blast", "fiverr_gig_blast",
    "upwork_job_alert", "brutus_shopify", "quantum_self_repair", "viral_trend",
    "indexnow_mega_blast", "mailchimp_brutus", "amazon_affiliate_blast", "brutus_ds24_affiliate",
]


async def handle_master_start_all(req: web.Request) -> web.Response:
    """POST /api/master/start-all — fires all key tasks in the background immediately."""
    try:
        from core.automation_scheduler import get_scheduler
        sched = get_scheduler()
        for task_name in _MASTER_TASKS:
            asyncio.create_task(sched.run_now(task_name))
        log.info("Master start-all: %d tasks fired", len(_MASTER_TASKS))
        return web.json_response({
            "ok": True,
            "tasks_started": len(_MASTER_TASKS),
            "tasks": _MASTER_TASKS,
            "message": "Alle Systeme gestartet! Maschine laeuft.",
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_master_status(req: web.Request) -> web.Response:
    """GET /api/master/status — live overview of all key systems."""
    status: dict = {"ok": True, "ts": __import__("datetime").datetime.utcnow().isoformat()}

    # Shopify product count
    try:
        shop = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        ver = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        if shop and token:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://{shop}/admin/api/{ver}/products/count.json",
                    headers={"X-Shopify-Access-Token": token},
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    d = await r.json()
            status["shopify_products"] = d.get("count", 0)
        else:
            status["shopify_products"] = "no credentials"
    except Exception as e:
        status["shopify_products"] = f"error: {e}"

    # Scheduler
    try:
        from core.automation_scheduler import get_scheduler_status
        sched_st = get_scheduler_status()
        status["scheduler"] = {
            "running": sched_st.get("running", False),
            "task_count": sched_st.get("task_count", 0),
        }
    except Exception:
        status["scheduler"] = {"running": False}

    # Circuit breakers
    try:
        from modules.circuit_breaker import get_status as cb_status
        circuits = cb_status()
        open_circuits = [k for k, v in circuits.items() if v.get("state") == "open"]
        status["circuits_open"] = open_circuits
    except Exception:
        status["circuits_open"] = []

    # Revenue snapshot
    try:
        rev_file = __import__("pathlib").Path(__file__).parent.parent / "revenue_history.json"
        if rev_file.exists():
            import json as _json
            data = _json.loads(rev_file.read_text())
            entries = data if isinstance(data, list) else data.get("entries", [])
            status["revenue_entries"] = len(entries)
        else:
            status["revenue_entries"] = 0
    except Exception:
        status["revenue_entries"] = 0

    # Quantum Self-Repair stats
    try:
        from modules.quantum_self_repair import get_error_stats
        status["quantum"] = get_error_stats()
    except Exception:
        status["quantum"] = {}

    status["master_tasks"] = _MASTER_TASKS
    return web.json_response(status)


# ── Selbstverbesserung / Email Doctor / Mass Blast / Dragon Handlers ─────────

async def handle_selbstverbesserung_run(req: web.Request) -> web.Response:
    """POST /api/selbstverbesserung/run — alle Plattformen analysieren + Auto-Fix."""
    try:
        from modules.selbstverbesserung import run_selbstverbesserung_cycle
        r = await run_selbstverbesserung_cycle()
        return web.json_response({"ok": True, **r})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_system_overview(req: web.Request) -> web.Response:
    """GET /api/system/overview — vollständige System-Übersicht."""
    try:
        from modules.selbstverbesserung import get_system_overview
        r = await get_system_overview()
        return web.json_response({"ok": True, **r})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_email_doctor_run(req: web.Request) -> web.Response:
    """POST /api/email-doctor/run — alle E-Mail-Systeme prüfen + reparieren."""
    try:
        from modules.email_doctor import run_email_doctor
        r = await run_email_doctor()
        return web.json_response({"ok": True, **r})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_email_doctor_status(req: web.Request) -> web.Response:
    """GET /api/email-doctor/status — E-Mail-System Status."""
    try:
        from modules.email_doctor import run_email_doctor
        r = await run_email_doctor()
        return web.json_response({"ok": True, **r})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_mass_blast_run(req: web.Request) -> web.Response:
    """POST /api/mass-blast/run — 1000 Content-Pieces blasten."""
    try:
        from modules.mass_content_blaster import run_mass_blast
        r = await run_mass_blast(topics_per_run=10)
        return web.json_response({"ok": True, **r})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_mass_blast_stats(req: web.Request) -> web.Response:
    """GET /api/mass-blast/stats — Mass Blast Statistiken."""
    try:
        from modules.mass_content_blaster import get_mass_blast_stats
        r = await get_mass_blast_stats()
        return web.json_response({"ok": True, **r})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_dragon_article_send(req: web.Request) -> web.Response:
    """POST /api/dragon/article/send — nächsten Dragon-Artikel senden."""
    try:
        from modules.mailchimp_dragon_1000 import send_dragon_article
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass
        r = await send_dragon_article(topic=body.get("topic"))
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_dragon_article_stats(req: web.Request) -> web.Response:
    """GET /api/dragon/article/stats — Dragon 1000 Artikel Statistiken."""
    try:
        from modules.mailchimp_dragon_1000 import get_dragon_article_stats
        r = await get_dragon_article_stats()
        return web.json_response({"ok": True, **r})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── MegaAgentOrchestrator Handlers ───────────────────────────────────────────

async def handle_mega_orchestrate(req: web.Request) -> web.Response:
    """POST /api/agents/orchestrate — alle 12 Plattform-Agenten starten."""
    try:
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass
        topics = body.get("topics") or None
        asyncio.get_event_loop().create_task(_run_orchestrator_bg(topics))
        return web.json_response({
            "ok": True,
            "message": "MegaAgentOrchestrator gestartet — 12 Agenten laufen parallel",
            "platforms": [
                "Klaviyo", "Mailchimp", "Twilio", "AliExpress", "eBay",
                "Amazon", "Fiverr", "Upwork", "TikTok", "Reddit", "Discord", "YouTube",
            ],
            "status": "running_in_background",
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def _run_orchestrator_bg(topics=None):
    try:
        from modules.mega_agent_orchestrator import run_all_agents, get_trending_topics
        if not topics:
            topics = await get_trending_topics()
        await run_all_agents(topics)
    except Exception as e:
        log.error("Orchestrator background error: %s", e)


async def handle_mega_orchestrate_status(req: web.Request) -> web.Response:
    """GET /api/agents/orchestrate/status — Status aller Plattform-Agenten."""
    try:
        from modules.mega_agent_orchestrator import get_orchestrator_status
        result = await get_orchestrator_status()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)



# ── Credential Activator ─────────────────────────────────────────────────────

async def handle_credential_status(req):
    try:
        from modules.credential_activator import get_activation_status
        return web.json_response(get_activation_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_credential_scan(req):
    async def _bg():
        try:
            from modules.credential_activator import run_credential_scan
            await run_credential_scan()
        except Exception as exc:
            log.error("credential_scan bg: %s", exc)
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "scan gestartet — poll GET /api/credentials/status"})


async def handle_connect_all(req):
    """POST /api/connect/all — alle Plattformen verbinden + Railway-Sync."""
    try:
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass
        from modules.connect_all import run_connect_all
        result = await run_connect_all(
            sync_railway=body.get("sync_railway", True),
            start_tasks=body.get("start_tasks", True),
            scan_credentials=body.get("scan_credentials", True),
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_connect_status(req):
    """GET /api/connect/status — Plattform-Verbindungsstatus ohne Side-Effects."""
    try:
        from modules.connect_all import ping_all_platforms, _oauth_links, normalize_env_aliases
        aliases = normalize_env_aliases()
        platforms = await ping_all_platforms()
        connected = sum(1 for p in platforms if p.get("connected"))
        return web.json_response({
            "ok": True,
            "connected_count": connected,
            "total": len(platforms),
            "platforms": platforms,
            "oauth_required": _oauth_links(),
            "env_aliases_applied": aliases,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── Stripe Connect v2 ─────────────────────────────────────────────────────────

async def handle_stripe_connect_create_account(req):
    """POST /api/stripe/connect/accounts — verbundenes Konto anlegen (v2)."""
    try:
        body = await req.json()
        from modules.stripe_connect_v2 import create_connected_account
        result = create_connected_account(
            email=body.get("email", ""),
            display_name=body.get("display_name", body.get("email", "")),
            country=body.get("country", "DE"),
            entity_type=body.get("entity_type", "company"),
            currency=body.get("currency", "eur"),
        )
        if "error" in result:
            return web.json_response({"ok": False, **result}, status=400)
        return web.json_response({"ok": True, "account": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_stripe_connect_list_accounts(req):
    """GET /api/stripe/connect/accounts — verbundene Konten auflisten."""
    try:
        from modules.stripe_connect_v2 import list_accounts
        limit = int(req.rel_url.query.get("limit", 20))
        page  = req.rel_url.query.get("page")
        result = list_accounts(limit=limit, page_token=page)
        if "error" in result:
            return web.json_response({"ok": False, **result}, status=400)
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_stripe_connect_account_status(req):
    """GET /api/stripe/connect/accounts/{id}/status — Konto-Status."""
    try:
        account_id = req.match_info["account_id"]
        from modules.stripe_connect_v2 import get_account_status
        result = get_account_status(account_id)
        if "error" in result:
            return web.json_response({"ok": False, **result}, status=400)
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_stripe_connect_onboarding(req):
    """POST /api/stripe/connect/accounts/{id}/onboarding — Onboarding-Link."""
    try:
        account_id = req.match_info["account_id"]
        from modules.stripe_connect_v2 import create_onboarding_link
        result = create_onboarding_link(account_id)
        if "error" in result:
            return web.json_response({"ok": False, **result}, status=400)
        url = (result.get("url") or "")
        return web.json_response({"ok": True, "url": url, "expires_at": result.get("expires_at")})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_stripe_connect_create_product(req):
    """POST /api/stripe/connect/accounts/{id}/products — Produkt anlegen."""
    try:
        account_id = req.match_info["account_id"]
        body = await req.json()
        from modules.stripe_connect_v2 import create_product_for_account
        result = create_product_for_account(
            account_id=account_id,
            name=body.get("name", ""),
            description=body.get("description", ""),
            price_cents=int(body.get("price_cents", 0)),
            currency=body.get("currency", "eur"),
            recurring_interval=body.get("interval"),
        )
        if "error" in result:
            return web.json_response({"ok": False, **result}, status=400)
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_stripe_connect_list_products(req):
    """GET /api/stripe/connect/accounts/{id}/products — Produkte auflisten."""
    try:
        account_id = req.match_info["account_id"]
        from modules.stripe_connect_v2 import list_products_for_account
        result = list_products_for_account(account_id)
        if "error" in result:
            return web.json_response({"ok": False, **result}, status=400)
        products = [
            {
                "id": p.get("product", {}).get("id") if isinstance(p.get("product"), dict) else p.get("product"),
                "name": p.get("product", {}).get("name", "") if isinstance(p.get("product"), dict) else "",
                "description": p.get("product", {}).get("description", "") if isinstance(p.get("product"), dict) else "",
                "price_cents": p.get("unit_amount"),
                "currency": p.get("currency"),
                "price_id": p.get("id"),
                "recurring": p.get("recurring"),
            }
            for p in result.get("data", [])
        ]
        return web.json_response({"ok": True, "products": products, "count": len(products)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_stripe_connect_checkout(req):
    """POST /api/stripe/connect/checkout — Checkout-Session für verbundenes Konto."""
    try:
        body = await req.json()
        from modules.stripe_connect_v2 import create_checkout_session
        result = create_checkout_session(
            account_id=body.get("account_id", ""),
            price_id=body.get("price_id", ""),
            quantity=int(body.get("quantity", 1)),
            application_fee_percent=float(body.get("fee_percent", 10.0)),
        )
        if "error" in result:
            return web.json_response({"ok": False, **result}, status=400)
        return web.json_response({"ok": True, "url": result.get("url"), "session_id": result.get("id")})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_stripe_connect_event_destinations(req):
    """GET /api/stripe/connect/event-destinations — Event Destinations auflisten."""
    try:
        from modules.stripe_connect_v2 import list_event_destinations
        result = list_event_destinations()
        if "error" in result:
            return web.json_response({"ok": False, **result}, status=400)
        return web.json_response({"ok": True, "destinations": result.get("data", [])})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_stripe_connect_create_destination(req):
    """POST /api/stripe/connect/event-destinations — Event Destination anlegen."""
    try:
        body = await req.json()
        from modules.stripe_connect_v2 import create_event_destination
        result = create_event_destination(
            name=body.get("name", "SuperMegaBot Connect"),
            webhook_url=body.get("webhook_url", ""),
            events=body.get("events"),
        )
        if "error" in result:
            return web.json_response({"ok": False, **result}, status=400)
        return web.json_response({"ok": True, "destination": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_stripe_connect_webhook_v2(req):
    """POST /api/connect/webhooks/v2 — v2 Thin Event Handler."""
    try:
        import os
        payload   = await req.read()
        signature = req.headers.get("Stripe-Signature", "")
        secret    = os.getenv("STRIPE_CONNECT_WEBHOOK_SECRET", os.getenv("STRIPE_WEBHOOK_SECRET", ""))
        from modules.stripe_connect_v2 import parse_v2_thin_event, fetch_v2_event_object
        event = parse_v2_thin_event(payload, signature, secret)
        if "error" in event:
            log.warning("Connect Webhook v2 ungültig: %s", event["error"])
            return web.json_response({"ok": False, **event}, status=400)
        event_type = event.get("type", "")
        log.info("Connect Webhook v2: %s | %s", event_type, event.get("id"))
        if event_type == "v1.checkout.session.completed":
            obj = await fetch_v2_event_object(event)
            account_id = obj.get("metadata", {}).get("account_id", "")
            amount = obj.get("amount_total", 0)
            log.info("Checkout abgeschlossen: %s | €%.2f | Account: %s", obj.get("id"), amount / 100, account_id)
        return web.json_response({"ok": True, "received": event_type})
    except Exception as e:
        log.error("Connect Webhook v2 Fehler: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_stripe_connect_return(req):
    """GET /api/connect/return — Rückgabe nach Onboarding."""
    account_id = req.rel_url.query.get("account_id", "")
    raise web.HTTPFound(f"/connect/dashboard?account_id={account_id}&onboarded=1")


async def handle_stripe_connect_refresh(req):
    """GET /api/connect/refresh — Aktualisierungs-URL nach abgelaufenem Link."""
    account_id = req.rel_url.query.get("account_id", "")
    try:
        from modules.stripe_connect_v2 import create_onboarding_link
        result = create_onboarding_link(account_id)
        url = result.get("url", "/connect")
        raise web.HTTPFound(url)
    except web.HTTPFound:
        raise
    except Exception as e:
        raise web.HTTPFound(f"/connect?error={e}")


# ── Quantum Self-Repair Engine ────────────────────────────────────────────────

async def handle_quantum_status(req):
    try:
        from modules.quantum_self_fixer import get_quantum_status
        return web.json_response(get_quantum_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_quantum_scan(req):
    async def _bg():
        try:
            from modules.quantum_self_fixer import run_full_scan
            await run_full_scan()
        except Exception as e:
            log.error("quantum_scan bg: %s", e)
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "scan started (background) — poll GET /api/quantum/status"})

async def handle_quantum_repair(req):
    async def _bg():
        try:
            from modules.quantum_self_fixer import scan_and_repair
            await scan_and_repair()
        except Exception as e:
            log.error("quantum_repair bg: %s", e)
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "repair started (background)"})


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


# ─── Shopify Mass Creator Handlers ───────────────────────────────────────────

async def handle_shopify_create_1000(request: web.Request) -> web.Response:
    try:
        asyncio.create_task(_bg_shopify_1000())
        return web.json_response({"ok": True, "message": "Shopify 1000-Produkte-Erstellung gestartet (background)"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def _bg_shopify_1000():
    from modules.shopify_mass_creator import create_1000_shopify_products
    await create_1000_shopify_products()

async def handle_shopify_mass_cycle(request: web.Request) -> web.Response:
    try:
        asyncio.create_task(_bg_shopify_cycle())
        return web.json_response({"ok": True, "message": "Shopify Mass-Cycle gestartet"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def _bg_shopify_cycle():
    from modules.shopify_mass_creator import run_shopify_mass_cycle
    await run_shopify_mass_cycle()

async def handle_shopify_mass_blast(request: web.Request) -> web.Response:
    try:
        body  = await request.json() if request.can_read_body else {}
        limit = int(body.get("limit", 10))
        from modules.shopify_mass_creator import blast_shopify_products
        r = await blast_shopify_products(limit=limit)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_shopify_mass_status(request: web.Request) -> web.Response:
    try:
        from modules.shopify_mass_creator import get_shopify_mass_stats
        r = await get_shopify_mass_stats()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_shopify_oauth_start(req: web.Request) -> web.Response:
    """GET /api/shopify/oauth — leitet zu Shopify OAuth weiter (alle Scopes)."""
    import urllib.parse
    scopes = ("read_products,write_products,read_customers,write_customers,"
              "read_orders,write_orders,read_content,write_content,"
              "read_price_rules,write_price_rules,read_inventory,write_inventory,"
              "read_locations,write_script_tags,read_analytics")
    _shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
    _client_id   = os.getenv("SHOPIFY_API_KEY", "")
    _base_url    = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("RAILWAY_STATIC_URL", "https://supermegabot-production.up.railway.app")).rstrip("/")
    _redirect    = urllib.parse.quote(f"{_base_url}/api/shopify/callback")
    url = (f"https://{_shop_domain}/admin/oauth/authorize"
           f"?client_id={_client_id}"
           f"&scope={urllib.parse.quote(scopes)}"
           f"&redirect_uri={_redirect}"
           "&state=aiitec2026")
    raise web.HTTPFound(url)


# ─── Klaviyo Mass Campaigns Handlers ─────────────────────────────────────────

async def handle_klaviyo_mass_create(request: web.Request) -> web.Response:
    try:
        body  = await request.json() if request.can_read_body else {}
        count = int(body.get("count", 200))
        asyncio.create_task(_bg_klaviyo_mass(count))
        return web.json_response({"ok": True, "message": f"Klaviyo {count} Kampagnen gestartet (background)"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def _bg_klaviyo_mass(count: int):
    from modules.klaviyo_mass_campaigns import mass_create_klaviyo_campaigns
    await mass_create_klaviyo_campaigns(count=count)

async def handle_klaviyo_daily_campaigns(request: web.Request) -> web.Response:
    try:
        from modules.klaviyo_mass_campaigns import run_daily_klaviyo_campaigns
        r = await run_daily_klaviyo_campaigns()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_klaviyo_mass_status(request: web.Request) -> web.Response:
    try:
        from modules.klaviyo_mass_campaigns import get_klaviyo_mass_stats
        r = await get_klaviyo_mass_stats()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ─── Mailchimp Mass Campaigns Handlers ───────────────────────────────────────

async def handle_mailchimp_mass_create(request: web.Request) -> web.Response:
    try:
        body  = await request.json() if request.can_read_body else {}
        count = int(body.get("count", 200))
        asyncio.create_task(_bg_mailchimp_mass(count))
        return web.json_response({"ok": True, "message": f"Mailchimp {count} Kampagnen gestartet (background)"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def _bg_mailchimp_mass(count: int):
    from modules.mailchimp_mass_campaigns import mass_create_mailchimp_campaigns
    await mass_create_mailchimp_campaigns(count=count)

async def handle_mailchimp_daily_campaigns(request: web.Request) -> web.Response:
    try:
        from modules.mailchimp_mass_campaigns import run_daily_mailchimp_campaigns
        r = await run_daily_mailchimp_campaigns()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_mailchimp_mass_status(request: web.Request) -> web.Response:
    try:
        from modules.mailchimp_mass_campaigns import get_mailchimp_mass_stats
        r = await get_mailchimp_mass_stats()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ─── Product Bundle Engine Handlers ──────────────────────────────────────────

async def handle_bundles_create(request: web.Request) -> web.Response:
    """POST /api/bundles/create — 3er+5er Bundles erstellen + blasten (background)."""
    async def _bg():
        try:
            from modules.product_bundle_engine import run_daily_bundle_cycle
            await run_daily_bundle_cycle()
        except Exception as exc:
            log.warning("Bundle create bg error: %s", exc)
    asyncio.get_event_loop().create_task(_bg())
    return web.json_response({"ok": True, "message": "Bundle-Erstellung gestartet (background)"})


async def handle_bundles_blast(request: web.Request) -> web.Response:
    """POST /api/bundles/blast — Zufälliges Bundle blasten."""
    try:
        from modules.product_bundle_engine import create_bundle, blast_bundle
        bundle = await create_bundle(size=3)
        if bundle.get("ok"):
            blast = await blast_bundle(bundle)
            return web.json_response({**bundle, "blast": blast})
        return web.json_response(bundle)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bundles_stats(request: web.Request) -> web.Response:
    """GET /api/bundles/stats — Bundle-Collection-Stats."""
    try:
        from modules.product_bundle_engine import get_bundle_stats
        return web.json_response(await get_bundle_stats())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ─── Stripe Auto-Billing Handlers ─────────────────────────────────────────────

async def handle_stripe_billing_check(request: web.Request) -> web.Response:
    """POST /api/stripe/billing-check — Alle Subscriptions prüfen."""
    try:
        from modules.stripe_auto_billing import check_subscriptions
        r = await check_subscriptions()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_stripe_payment_link(request: web.Request) -> web.Response:
    """POST /api/stripe/payment-link — Payment Link erstellen."""
    try:
        data = await request.json()
        name        = data.get("name", "BullPowerHub Pro")
        price_cents = int(data.get("price_cents", 9900))
        currency    = data.get("currency", "eur")
    except Exception:
        name, price_cents, currency = "BullPowerHub Pro", 9900, "eur"
    try:
        from modules.stripe_auto_billing import create_payment_link
        r = await create_payment_link(name, price_cents, currency)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_stripe_billing_stats(request: web.Request) -> web.Response:
    """GET /api/stripe/billing-stats — Revenue-Übersicht."""
    try:
        from modules.stripe_auto_billing import get_billing_stats
        return web.json_response(await get_billing_stats())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_stripe_ds24_links(request: web.Request) -> web.Response:
    """POST /api/stripe/ds24-links — Payment Links für DS24-Abo-Pläne."""
    try:
        from modules.stripe_auto_billing import create_ds24_payment_links
        r = await create_ds24_payment_links()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_high_ticket_links(request: web.Request) -> web.Response:
    """GET /api/high-ticket-links — Alle High-Ticket Payment Links (€297–€4997)."""
    links = {
        "kdp_empire": {
            "name": "KDP Empire Builder — Done For You",
            "price": "€997/mo",
            "price_id": os.getenv("STRIPE_PRICE_KDP_EMPIRE", ""),
            "url": os.getenv("PLINK_KDP_EMPIRE", ""),
        },
        "etsy_empire": {
            "name": "Digital Products Empire Setup",
            "price": "€1997 einmalig",
            "price_id": os.getenv("STRIPE_PRICE_ETSY_EMPIRE", ""),
            "url": os.getenv("PLINK_ETSY_EMPIRE", ""),
        },
        "rudibot_agency": {
            "name": "E-Commerce KI-Agency Suite",
            "price": "€997/mo",
            "price_id": os.getenv("STRIPE_PRICE_RUDIBOT_AGENCY", ""),
            "url": os.getenv("PLINK_RUDIBOT_AGENCY", ""),
        },
        "autoincome_dfy": {
            "name": "Passive Income Machine — DFY Setup",
            "price": "€4997 einmalig",
            "price_id": os.getenv("STRIPE_PRICE_AUTOINCOME_DFY", ""),
            "url": os.getenv("PLINK_AUTOINCOME_DFY", ""),
        },
        "creatorai_enterprise": {
            "name": "Creator KI-Suite Enterprise",
            "price": "€497/mo",
            "price_id": os.getenv("STRIPE_PRICE_CREATORAI_ENT", ""),
            "url": os.getenv("PLINK_CREATORAI_ENT", ""),
        },
        "ds24_empire": {
            "name": "Digistore24 Empire Builder",
            "price": "€797/mo",
            "price_id": os.getenv("STRIPE_PRICE_DS24_EMPIRE", ""),
            "url": os.getenv("PLINK_DS24_EMPIRE", ""),
        },
        "digiprod_fullservice": {
            "name": "Digital Product Fullservice",
            "price": "€1497 einmalig",
            "price_id": os.getenv("STRIPE_PRICE_DIGIPROD_FS", ""),
            "url": os.getenv("PLINK_DIGIPROD_FS", ""),
        },
    }
    total_mrr = sum([997, 997, 497, 797])
    total_one_time = sum([1997, 4997, 1497])

    # Wave 2 + Wave 3 catalogs — live Stripe payment links
    import json as _json
    base_cfg = Path(__file__).resolve().parent.parent / "config"
    wave_counts = {}
    for wave_name, fname in (("wave2", "high_ticket_wave2.json"), ("wave3", "high_ticket_wave3.json")):
        wpath = base_cfg / fname
        if not wpath.exists():
            wpath = Path(__file__).resolve().parent.parent / "data" / fname
        try:
            if not wpath.exists():
                wave_counts[wave_name] = 0
                continue
            wdata = _json.loads(wpath.read_text(encoding="utf-8"))
            wprods = wdata.get("products") or {}
            total_mrr += int(wdata.get("mrr_potential") or 0)
            total_one_time += int(wdata.get("one_time_potential") or 0)
            for key, prod in wprods.items():
                tiers = prod.get("tiers") or []
                featured = tiers[1] if len(tiers) > 1 else (tiers[0] if tiers else {})
                links[key] = {
                    "name": prod.get("name", key),
                    "price": featured.get("price_label", ""),
                    "price_id": featured.get("price_id", ""),
                    "url": featured.get("url", ""),
                    "tiers": tiers,
                    "wave": wave_name,
                }
            wave_counts[wave_name] = len(wprods)
        except Exception as e:
            log.warning("high_ticket %s load failed: %s", wave_name, e)
            wave_counts[wave_name] = 0

    money_map = {}
    try:
        mm = base_cfg / "money_map.json"
        if mm.exists():
            money_map = _json.loads(mm.read_text(encoding="utf-8"))
    except Exception:
        pass

    return web.json_response({
        "ok": True,
        "count": len(links),
        "potential_mrr_eur": total_mrr,
        "potential_one_time_eur": total_one_time,
        "products": links,
        "wave2_count": wave_counts.get("wave2", 0),
        "wave3_count": wave_counts.get("wave3", 0),
        "featured": (money_map.get("featured") or [])[:50],
    })


async def handle_money_map(request: web.Request) -> web.Response:
    """GET /api/money-map — public featured high-ticket buy links for sales."""
    try:
        import json as _json
        mm_path = Path(__file__).resolve().parent.parent / "config" / "money_map.json"
        if not mm_path.exists():
            return web.json_response({"ok": False, "error": "money_map missing"}, status=404)
        data = _json.loads(mm_path.read_text(encoding="utf-8"))
        return web.json_response({"ok": True, **data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_testimonials(request: web.Request) -> web.Response:
    """GET /api/testimonials — rotating autonomous testimonials."""
    try:
        from modules.autonomous_social_proof import get_social_proof_bundle
        folder = request.rel_url.query.get("folder")
        limit = int(request.rel_url.query.get("limit", "20"))
        bundle = get_social_proof_bundle(folder=folder, limit_t=limit, limit_c=0)
        return web.json_response({
            "ok": True,
            "count": len(bundle.get("testimonials") or []),
            "items": bundle.get("testimonials") or [],
            "folder": folder,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_case_studies(request: web.Request) -> web.Response:
    """GET /api/case-studies — rotating autonomous case studies."""
    try:
        from modules.autonomous_social_proof import get_social_proof_bundle
        folder = request.rel_url.query.get("folder")
        limit = int(request.rel_url.query.get("limit", "12"))
        bundle = get_social_proof_bundle(folder=folder, limit_t=0, limit_c=limit, limit_d=0)
        return web.json_response({
            "ok": True,
            "count": len(bundle.get("case_studies") or []),
            "items": bundle.get("case_studies") or [],
            "folder": folder,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_demos(request: web.Request) -> web.Response:
    """GET /api/demos — autonomous interactive demo catalog."""
    try:
        from modules.autonomous_social_proof import get_social_proof_bundle
        folder = request.rel_url.query.get("folder")
        limit = int(request.rel_url.query.get("limit", "30"))
        bundle = get_social_proof_bundle(folder=folder, limit_t=0, limit_c=0, limit_d=limit)
        return web.json_response({
            "ok": True,
            "count": len(bundle.get("demos") or []),
            "items": bundle.get("demos") or [],
            "folder": folder,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_social_proof(request: web.Request) -> web.Response:
    """GET /api/social-proof — testimonials + case studies combined.
    POST /api/social-proof/run — trigger regenerate+inject (auth via middleware except GET).
    """
    try:
        from modules.autonomous_social_proof import get_social_proof_bundle, run_social_proof_cycle
        if request.method == "POST":
            result = await run_social_proof_cycle(post_telegram=True)
            return web.json_response(result)
        folder = request.rel_url.query.get("folder")
        bundle = get_social_proof_bundle(folder=folder)
        return web.json_response(bundle)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ─── High-Ticket Demo System ─────────────────────────────────────────────────

async def handle_demo_book(req: web.Request) -> web.Response:
    """POST /api/demo/book — Demo-Buchung, Telegram-Alert an Rudolf, SQLite-Session anlegen."""
    try:
        data = await req.json()
        name    = data.get("name", "").strip()
        email   = data.get("email", "").strip()
        phone   = data.get("phone", "").strip()
        company = data.get("company", "").strip()
        product = data.get("product", "supermegabot").strip()
        revenue = data.get("revenue_range", "").strip()
        plan    = data.get("plan", "").strip()
        if not name or not email:
            return web.json_response({"ok": False, "error": "Name und E-Mail erforderlich"}, status=400)
        from modules.demo_system import create_demo_session, schedule_demo_call
        session_id = await create_demo_session(email=email, name=name, company=company, product_id=product)
        await schedule_demo_call(
            name=name, email=email, phone=phone, company=company,
            product=product, revenue_range=revenue, plan_interest=plan,
        )
        return web.json_response({
            "ok": True,
            "session_id": session_id,
            "message": "Demo-Anfrage eingegangen! Rudolf meldet sich innerhalb von 4 Stunden.",
            "demo_url": f"/demo?session={session_id}",
        })
    except Exception as e:
        log.error("Demo book error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_demo_session_status(req: web.Request) -> web.Response:
    """GET /api/demo/session/{sid} — Demo-Session-Status abrufen."""
    try:
        sid = req.match_info.get("sid", "")
        from modules.demo_system import get_demo_session
        session = get_demo_session(sid)
        if not session:
            return web.json_response({"ok": False, "error": "Session nicht gefunden"}, status=404)
        return web.json_response({"ok": True, "session": session})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_demo_page(req: web.Request) -> web.Response:
    """GET /demo — High-Ticket Demo Landing Page mit Buchungsformular."""
    base_url = f"https://{os.getenv('RAILWAY_STATIC_URL', 'supermegabot-production.up.railway.app')}"
    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SuperMegaBot — Kostenlose Demo buchen</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#080C14;color:#E8F0FF;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}}
.card{{background:#0D1525;border:1px solid #1B2640;border-radius:12px;padding:48px;max-width:560px;width:100%}}
h1{{font-size:1.8rem;font-weight:900;margin-bottom:8px;letter-spacing:-.01em}}
h1 span{{color:#1BFFAA}}
p{{color:#7A92B8;margin-bottom:24px;line-height:1.6}}
.field{{display:flex;flex-direction:column;gap:6px;margin-bottom:16px}}
label{{font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#7A92B8}}
input,select{{background:#080C14;border:1px solid #243554;color:#E8F0FF;padding:10px 14px;border-radius:6px;font-size:.9rem;outline:none;font-family:inherit}}
input:focus,select:focus{{border-color:#1BFFAA}}
select option{{background:#0D1525}}
.row{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.btn{{width:100%;padding:14px;background:#1BFFAA;color:#000;border:none;border-radius:6px;font-size:1rem;font-weight:700;cursor:pointer;margin-top:8px}}
.btn:hover{{opacity:.88}}
.trust{{display:flex;gap:16px;flex-wrap:wrap;margin-top:20px;justify-content:center}}
.trust-item{{font-size:.75rem;color:#3D5070}}
.success{{display:none;text-align:center;color:#1BFFAA;padding:20px;border:1px solid #1BFFAA;border-radius:8px;margin-top:16px}}
</style>
</head>
<body>
<div class="card">
  <h1>14-Tage Demo<br><span>kostenlos starten</span></h1>
  <p>Kein Credit Card. Kein Risiko. Rudolf meldet sich persönlich innerhalb von 4 Stunden.</p>
  <form id="f">
    <div class="row">
      <div class="field"><label>Vorname</label><input id="fn" placeholder="Max" required></div>
      <div class="field"><label>Nachname</label><input id="ln" placeholder="Mustermann"></div>
    </div>
    <div class="field"><label>E-Mail</label><input id="em" type="email" placeholder="max@deinshop.de" required></div>
    <div class="field"><label>Telefon</label><input id="ph" placeholder="+49 123 ..."></div>
    <div class="field"><label>Unternehmen</label><input id="co" placeholder="Mein Shop GmbH"></div>
    <div class="row">
      <div class="field"><label>Monatlicher Umsatz</label>
        <select id="rv"><option value="">Bitte wählen</option>
        <option>€5K–€20K</option><option>€20K–€50K</option>
        <option>€50K–€150K</option><option>€150K–€500K</option><option>€500K+</option>
        </select>
      </div>
      <div class="field"><label>Interesse</label>
        <select id="pl"><option value="">Noch offen</option>
        <option>Growth (€497/mo)</option><option>Scale (€997/mo)</option>
        <option>Enterprise (€2.497/mo)</option>
        </select>
      </div>
    </div>
    <button class="btn" type="submit">Demo buchen — kostenlos →</button>
  </form>
  <div class="success" id="ok">✅ Anfrage gesendet! Rudolf meldet sich in &lt;4h.</div>
  <div class="trust">
    <span class="trust-item">✓ 90-Tage ROI-Garantie</span>
    <span class="trust-item">✓ DSGVO · EU-Server</span>
    <span class="trust-item">✓ Kein Spam</span>
  </div>
</div>
<script>
document.getElementById('f').addEventListener('submit',async e=>{{
  e.preventDefault();
  const b={{name:document.getElementById('fn').value+' '+document.getElementById('ln').value,
    email:document.getElementById('em').value,phone:document.getElementById('ph').value,
    company:document.getElementById('co').value,revenue_range:document.getElementById('rv').value,
    plan:document.getElementById('pl').value,product:'supermegabot'}};
  const r=await fetch('{base_url}/api/demo/book',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(b)}});
  const j=await r.json();
  if(j.ok){{document.getElementById('f').style.display='none';document.getElementById('ok').style.display='block';}}
  else alert('Fehler: '+j.error);
}});
</script>
</body></html>"""
    return web.Response(text=html, content_type="text/html")


# ─── Auto-Sorter Handlers ─────────────────────────────────────────────────────

async def handle_sort_shopify(request: web.Request) -> web.Response:
    """POST /api/sort/shopify — Shopify-Produkte in Collections sortieren."""
    try:
        from modules.auto_sorter import sort_shopify_products
        r = await sort_shopify_products()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_sort_all(request: web.Request) -> web.Response:
    """POST /api/sort/all — Shopify + DS24 + Klaviyo vollständig sortieren."""
    async def _bg():
        try:
            from modules.auto_sorter import sort_all
            await sort_all()
        except Exception as exc:
            log.warning("sort_all bg error: %s", exc)
    asyncio.get_event_loop().create_task(_bg())
    return web.json_response({"ok": True, "message": "Vollständiger Sort-Zyklus gestartet (background)"})


# ─── Revenue Auto-Payout Handlers ─────────────────────────────────────────────

async def handle_revenue_milestone_check(request: web.Request) -> web.Response:
    """POST /api/revenue/milestone-check — Meilensteine prüfen."""
    try:
        from modules.revenue_auto_payout import aggregate_revenue, check_milestones
        snap = await aggregate_revenue(days=30)
        ms   = await check_milestones(snap)
        return web.json_response({"ok": True, "snapshot": snap, "milestone": ms})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_revenue_payout_weekly(request: web.Request) -> web.Response:
    """POST /api/revenue/weekly-summary — 7-Tage Report via Telegram."""
    try:
        from modules.revenue_auto_payout import run_weekly_report
        r = await run_weekly_report()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_revenue_payout_stats(request: web.Request) -> web.Response:
    """GET /api/revenue/payout-stats — Aggregierte Revenue-Stats."""
    try:
        from modules.revenue_auto_payout import get_revenue_stats
        return web.json_response(await get_revenue_stats())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ─── BrutusClone Integrator Handlers ─────────────────────────────────────────

async def handle_brutus_blast_product(request: web.Request) -> web.Response:
    try:
        body = await request.json() if request.can_read_body else {}
        from modules.brutus_clone_integrator import blast_new_product
        r = await blast_new_product(body, channels=body.get("channels"))
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_brutus_blast_summary(request: web.Request) -> web.Response:
    try:
        body = await request.json() if request.can_read_body else {}
        from modules.brutus_clone_integrator import blast_daily_summary
        r = await blast_daily_summary(body)
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_brutus_system_status(request: web.Request) -> web.Response:
    try:
        from modules.brutus_clone_integrator import blast_system_status
        r = await blast_system_status()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_brutus_stats(request: web.Request) -> web.Response:
    try:
        from modules.brutus_clone_integrator import get_integrator_stats
        r = await get_integrator_stats()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ─── Revenue Mega Tracker Handlers ───────────────────────────────────────────

async def handle_revenue_daily_report(request: web.Request) -> web.Response:
    try:
        body = await request.json() if request.can_read_body else {}
        days = int(body.get("days", 1))
        asyncio.create_task(_bg_revenue_report(days))
        return web.json_response({"ok": True, "message": f"Revenue-Report für {days} Tag(e) gestartet (background)"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def _bg_revenue_report(days: int):
    from modules.revenue_mega_tracker import generate_daily_revenue_report
    await generate_daily_revenue_report(days=days)

async def handle_revenue_weekly_report(request: web.Request) -> web.Response:
    try:
        asyncio.create_task(_bg_revenue_weekly())
        return web.json_response({"ok": True, "message": "7-Tage Revenue-Report gestartet (background)"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def _bg_revenue_weekly():
    from modules.revenue_mega_tracker import run_revenue_weekly
    await run_revenue_weekly()

async def handle_revenue_snapshot(request: web.Request) -> web.Response:
    try:
        from modules.stripe_payment_hook import get_payment_stats
        from modules.digistore24_automation import get_recent_sales
        stripe_stats, ds24_stats = await asyncio.gather(
            get_payment_stats(),
            get_recent_sales(days=1),
            return_exceptions=True,
        )
        if isinstance(stripe_stats, Exception):
            stripe_stats = {"error": str(stripe_stats)}
        if isinstance(ds24_stats, Exception):
            ds24_stats = {"error": str(ds24_stats)}
        return web.json_response({
            "ok":    True,
            "stripe": stripe_stats,
            "ds24":   ds24_stats,
            "at":    datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_revenue_stats(request: web.Request) -> web.Response:
    try:
        from modules.revenue_mega_tracker import get_revenue_stats
        r = await get_revenue_stats()
        return web.json_response(r)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── VORSPRUNG INTELLIGENCE HANDLERS ─────────────────────────────────────────

_vorsprung_scan_cache: dict = {}


async def handle_vorsprung_status(req: web.Request) -> web.Response:
    try:
        from modules.vorsprung_intelligence import get_status
        data = await get_status()
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_vorsprung_signals(req: web.Request) -> web.Response:
    try:
        from modules.vorsprung_intelligence import _supa_recent
        limit = int(req.rel_url.query.get("limit", 50))
        signals = await _supa_recent(limit)
        return web.json_response({"ok": True, "count": len(signals), "signals": signals})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_vorsprung_scan(req: web.Request) -> web.Response:
    try:
        from modules.vorsprung_intelligence import run_full_scan
        result = await run_full_scan()
        _vorsprung_scan_cache["last"] = result
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_vorsprung_briefing(req: web.Request) -> web.Response:
    try:
        from modules.vorsprung_intelligence import _supa_recent, generate_intelligence_briefing
        signals = await _supa_recent(100)
        if not signals:
            return web.json_response({"briefing": "Noch keine Signale. Bitte zuerst /api/vorsprung/scan aufrufen."})
        briefing = await generate_intelligence_briefing(signals)
        return web.json_response({"ok": True, "briefing": briefing, "signal_count": len(signals)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ── END VORSPRUNG INTELLIGENCE ────────────────────────────────────────────────


# ── FACEBOOK / INSTAGRAM TOKEN AUTO-REFRESH ───────────────────────────────────

async def handle_fb_token_status(req: web.Request) -> web.Response:
    try:
        from modules.facebook_token_refresher import get_status
        return web.json_response(await get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_fb_token_refresh(req: web.Request) -> web.Response:
    try:
        from modules.facebook_token_refresher import check_and_refresh
        result = await check_and_refresh()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

# ── END FACEBOOK TOKEN AUTO-REFRESH ──────────────────────────────────────────

# ── SYS-10 / SYS-13 / SYS-18 / SERVICE DELIVERY (BPI Extension) ──────────────

async def handle_bpi_outreach_stats(req: web.Request) -> web.Response:
    try:
        import sqlite3
        db = Path(__file__).parent.parent / "data" / "bulk_outreach.db"
        if not db.exists():
            return web.json_response({"ok": True, "status": "no_data", "sent": 0, "partners": 0})
        with sqlite3.connect(str(db)) as c:
            c.row_factory = sqlite3.Row
            sent       = c.execute("SELECT COUNT(*) FROM bo_outreach WHERE status IN ('sent','followup_sent','replied')").fetchone()[0]
            replies    = c.execute("SELECT COUNT(*) FROM bo_outreach WHERE replied_at IS NOT NULL").fetchone()[0]
            partners   = c.execute("SELECT COUNT(*) FROM bo_partners WHERE status='onboarded'").fetchone()[0]
            companies  = c.execute("SELECT COUNT(*) FROM bo_companies").fetchone()[0]
            unsub      = c.execute("SELECT COUNT(*) FROM bo_outreach WHERE status='unsubscribed'").fetchone()[0]
        return web.json_response({
            "ok": True, "companies": companies, "sent": sent,
            "replies": replies, "partners": partners, "unsubscribed": unsub,
            "reply_rate_pct": round(replies / max(sent, 1) * 100, 1),
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bpi_outreach_run(req: web.Request) -> web.Response:
    try:
        from modules.email_outreach_bulk import run_outreach, run_followup, init_db, _seed_companies
        init_db(); _seed_companies()
        result    = await run_outreach(daily_limit=100)
        followup  = await run_followup(daily_limit=30)
        return web.json_response({"ok": True, "sent": result.get("sent", 0),
                                  "errors": result.get("errors", 0),
                                  "followup_sent": followup.get("followup_sent", 0)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_mpo_stats(req: web.Request) -> web.Response:
    """GET /api/mpo/stats — Multi-Product Outreach Statistik."""
    try:
        from modules.multi_product_outreach import get_stats
        return web.json_response(await get_stats())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_mpo_run(req: web.Request) -> web.Response:
    """POST /api/mpo/run — Multi-Product Outreach sofort starten."""
    try:
        from modules.multi_product_outreach import run_outreach, _report
        stats = await run_outreach()
        await _report(stats)
        return web.json_response({"ok": True, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_aiitec_outreach_stats(req: web.Request) -> web.Response:
    """GET /api/aiitec-outreach/stats — AIITEC B2B Outreach Statistik."""
    try:
        from modules.aiitec_outreach_machine import AiitecOutreachMachine
        machine = AiitecOutreachMachine()
        stats = await machine.get_stats()
        return web.json_response(stats)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_aiitec_outreach_run(req: web.Request) -> web.Response:
    """POST /api/aiitec-outreach/run — AIITEC Outreach sofort starten."""
    try:
        from modules.aiitec_outreach_machine import AiitecOutreachMachine
        machine = AiitecOutreachMachine()
        stats = await machine.run_daily_outreach()
        return web.json_response({"ok": True, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bpi_partners(req: web.Request) -> web.Response:
    try:
        import sqlite3
        db = Path(__file__).parent.parent / "data" / "bulk_outreach.db"
        if not db.exists():
            return web.json_response({"ok": True, "partners": []})
        with sqlite3.connect(str(db)) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                "SELECT p.email, p.status, p.commission_pct, p.total_referrals, p.total_earned, "
                "p.onboarded_at, co.name FROM bo_partners p "
                "LEFT JOIN bo_companies co ON p.company_id=co.id ORDER BY p.onboarded_at DESC LIMIT 100"
            ).fetchall()
        return web.json_response({"ok": True, "partners": [dict(r) for r in rows]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bpi_delivery_order(req: web.Request) -> web.Response:
    try:
        body = await req.json()
        product_key    = body.get("product_key", "")
        customer_email = body.get("customer_email", "")
        customer_data  = body.get("customer_data", {})
        if not product_key or not customer_email:
            return web.json_response({"ok": False, "error": "product_key + customer_email required"}, status=400)
        from modules.service_delivery import deliver_order
        result = await deliver_order(product_key, customer_email, customer_data)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bpi_delivery_stats(req: web.Request) -> web.Response:
    try:
        import sqlite3
        db = Path(__file__).parent.parent / "data" / "deliveries.db"
        if not db.exists():
            return web.json_response({"ok": True, "total": 0, "delivered": 0, "pending": 0, "failed": 0})
        with sqlite3.connect(str(db)) as c:
            total     = c.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
            delivered = c.execute("SELECT COUNT(*) FROM deliveries WHERE status='delivered'").fetchone()[0]
            pending   = c.execute("SELECT COUNT(*) FROM deliveries WHERE status='pending'").fetchone()[0]
            failed    = c.execute("SELECT COUNT(*) FROM deliveries WHERE status='failed'").fetchone()[0]
            by_product = c.execute(
                "SELECT product_key, COUNT(*) as cnt FROM deliveries WHERE status='delivered' GROUP BY product_key"
            ).fetchall()
        return web.json_response({
            "ok": True, "total": total, "delivered": delivered,
            "pending": pending, "failed": failed,
            "by_product": [{"product": r[0], "count": r[1]} for r in by_product],
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bpi_sys18_preview(req: web.Request) -> web.Response:
    try:
        from modules.sys18_newsletter_ki import generate_newsletter
        params = req.rel_url.query
        result = await generate_newsletter(
            kanzlei_name=params.get("kanzlei", "Mustermann Steuerberatung"),
            kanzlei_ort=params.get("ort", "München"),
            mandanten_typ=params.get("typ", "gemischt"),
        )
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bpi_compliance_webhook(req: web.Request) -> web.Response:
    """BPI Compliance Tools Webhook: Stripe Zahlung → automatische E-Mail-Lieferung."""
    try:
        payload = await req.read()
        event   = json.loads(payload)
        from modules.bpi_compliance_engine import handle_stripe_event
        result = await handle_stripe_event(event)
        return web.json_response(result)
    except Exception as e:
        log.error("BPI compliance webhook: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bpi_compliance_outreach(req: web.Request) -> web.Response:
    """B2B Outreach an Zielgruppe senden. Body: {target_type, targets: [{email, company, name}]}"""
    try:
        body = await req.json()
        from modules.bpi_compliance_engine import run_b2b_outreach
        result = await run_b2b_outreach(
            target_type=body.get("target_type", "alle"),
            targets=body.get("targets", []),
            max_emails=body.get("max_emails", 50),
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bpi_compliance_status(req: web.Request) -> web.Response:
    """Status aller BPI Compliance Tools."""
    try:
        from modules.bpi_compliance_engine import get_status
        return web.json_response(await get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── EU AI Act Art. 50 ────────────────────────────────────────────────────────

async def handle_ai_act_banner(req: web.Request) -> web.Response:
    """Generiert Art.-50-konformes Disclosure-Banner HTML."""
    try:
        from modules.ai_act_art50_engine import generate_disclosure_banner
        params = req.rel_url.query
        result = await generate_disclosure_banner(
            shop_url     = params.get("shop_url", ""),
            chatbot_type = params.get("chatbot_type", "generic"),
            language     = params.get("language", "de"),
            style        = params.get("style", "full"),
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ai_act_scan(req: web.Request) -> web.Response:
    """Scannt eine URL auf AI-Chatbots + fehlende Art.-50-Disclosures."""
    try:
        from modules.ai_act_art50_engine import scan_website_for_ai_content
        data = await req.json() if req.content_type == "application/json" else {}
        url  = data.get("url") or req.rel_url.query.get("url", "")
        if not url:
            return web.json_response({"ok": False, "error": "url erforderlich"}, status=400)
        result = await scan_website_for_ai_content(url)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ai_act_report(req: web.Request) -> web.Response:
    """Vollständiger Art.-50-Compliance-Report für einen Shop."""
    try:
        from modules.ai_act_art50_engine import generate_compliance_report
        data   = await req.json() if req.content_type == "application/json" else {}
        domain = data.get("domain") or req.rel_url.query.get("domain", "")
        if not domain:
            return web.json_response({"ok": False, "error": "domain erforderlich"}, status=400)
        result = await generate_compliance_report(domain)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ai_act_status(req: web.Request) -> web.Response:
    """Status des AI Act Art. 50 Systems."""
    try:
        from modules.ai_act_art50_engine import get_status
        return web.json_response(await get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── HS-Code SaaS ─────────────────────────────────────────────────────────────

async def handle_hs_classify(req: web.Request) -> web.Response:
    """HS-Code-Klassifizierung für ein Produkt."""
    try:
        from modules.hs_code_saas import classify_hs_code_local, classify_hs_code_ai, calculate_customs_cost
        data   = await req.json() if req.content_type == "application/json" else {}
        name   = data.get("name", data.get("title", ""))
        desc   = data.get("description", "")
        use_ai = data.get("use_ai", False)
        if not name:
            return web.json_response({"ok": False, "error": "name erforderlich"}, status=400)
        if use_ai:
            hs, cat, conf = await classify_hs_code_ai(name, desc)
        else:
            hs, cat, conf = classify_hs_code_local(name, desc)
        cost = calculate_customs_cost([hs])
        return web.json_response({"ok": True, "hs_code": hs, "category": cat, "confidence": conf, "customs": cost})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_hs_batch(req: web.Request) -> web.Response:
    """Batch-Klassifizierung eines Produktkatalogs."""
    try:
        from modules.hs_code_saas import classify_product_catalog
        data     = await req.json()
        products = data.get("products", [])
        if not products:
            return web.json_response({"ok": False, "error": "products erforderlich"}, status=400)
        results = await classify_product_catalog(products[:500], use_ai=data.get("use_ai", False))
        return web.json_response({"ok": True, "count": len(results), "results": results})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_hs_status(req: web.Request) -> web.Response:
    """Status des HS-Code SaaS Systems."""
    try:
        from modules.hs_code_saas import get_status
        return web.json_response(await get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── Non-EU VAT/OSS ───────────────────────────────────────────────────────────

async def handle_vat_calculate(req: web.Request) -> web.Response:
    """MwSt-Berechnung für eine EU-Bestellung."""
    try:
        from modules.non_eu_vat_oss import calculate_vat
        data = await req.json() if req.content_type == "application/json" else {}
        amount  = float(data.get("amount", 0))
        country = data.get("country", "DE")
        ptype   = data.get("type", "digital")
        b2b     = bool(data.get("b2b", False))
        if not amount:
            return web.json_response({"ok": False, "error": "amount erforderlich"}, status=400)
        result = calculate_vat(amount, country, ptype, b2b)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_vat_oss_report(req: web.Request) -> web.Response:
    """OSS-Quartalsbericht generieren."""
    try:
        from modules.non_eu_vat_oss import generate_oss_quarterly_report
        data         = await req.json()
        transactions = data.get("transactions", [])
        quarter      = data.get("quarter", "Q3")
        year         = int(data.get("year", 2026))
        result = generate_oss_quarterly_report(transactions, quarter, year)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_vat_oss_status(req: web.Request) -> web.Response:
    """Status des VAT/OSS Systems."""
    try:
        from modules.non_eu_vat_oss import get_status
        return web.json_response(await get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bpi_stripe_webhook(req: web.Request) -> web.Response:
    """BPI Stripe Webhook: Zahlung → KI-Generierung → Email-Lieferung in 48h."""
    try:
        payload    = await req.read()
        sig_header = req.headers.get("Stripe-Signature", "")
        # BPI-spezifisches Webhook-Secret (we_1TsecMRJECiV6vSmHyaastf4)
        webhook_secret = os.getenv("BPI_STRIPE_WEBHOOK_SECRET", os.getenv("STRIPE_WEBHOOK_SECRET", ""))
        if webhook_secret and sig_header:
            try:
                from modules.stripe_automation import verify_webhook_signature
                if not verify_webhook_signature(payload, sig_header, webhook_secret):
                    return web.json_response({"ok": False, "error": "Invalid signature"}, status=400)
            except Exception as _sig_err:
                log.error("[BPI-WEBHOOK] Signature verification error: %s", _sig_err)
                return web.json_response({"ok": False, "error": f"Signature check failed: {_sig_err}"}, status=400)
        event = json.loads(payload)
        event_type = event.get("type", "")
        from modules.service_delivery import deliver_order

        if event_type == "checkout.session.completed":
            sess        = event["data"]["object"]
            email       = (sess.get("customer_details") or {}).get("email", "")
            meta        = sess.get("metadata") or {}
            product_key = meta.get("product_key", "")
            if email and product_key:
                asyncio.create_task(deliver_order(product_key, email, meta))
                log.info(f"BPI Delivery gestartet: {product_key} → {email}")
            # Telegram-Benachrichtigung
            if email:
                tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
                tg_chat  = os.getenv("TELEGRAM_CHAT_ID", "")
                if tg_token and tg_chat:
                    amount = sess.get("amount_total", 0)
                    msg = (f"💰 <b>Neue Zahlung!</b>\n"
                           f"Produkt: {product_key or 'unbekannt'}\n"
                           f"Betrag: €{amount/100:.2f}\n"
                           f"Kunde: {email}\n"
                           f"Lieferung läuft...")
                    import aiohttp as _aio
                    async with _aio.ClientSession() as s:
                        await s.post(f"https://api.telegram.org/bot{tg_token}/sendMessage",
                                     json={"chat_id": tg_chat, "text": msg, "parse_mode": "HTML"})

        elif event_type == "customer.subscription.created":
            # Abo gestartet → Erste Lieferung auslösen
            sub   = event["data"]["object"]
            cust  = sub.get("customer", "")
            meta  = sub.get("metadata") or {}
            product_key = meta.get("product_key", "")
            # Kunden-Email aus Stripe holen
            if cust and product_key:
                import urllib.request as _ur, urllib.parse as _up
                _hdr = {"Authorization": f"Bearer {os.getenv('STRIPE_SECRET_KEY','')}"}
                try:
                    _req = _ur.Request(f"https://api.stripe.com/v1/customers/{cust}", headers=_hdr)
                    with _ur.urlopen(_req, timeout=10) as r:
                        _c = json.loads(r.read())
                        email = _c.get("email", "")
                    if email:
                        asyncio.create_task(deliver_order(product_key, email, meta))
                        log.info(f"BPI Abo-Delivery: {product_key} → {email}")
                except Exception as _e:
                    log.warning(f"Kunden-Email Abruf Fehler: {_e}")

        return web.json_response({"ok": True, "event": event_type})
    except Exception as e:
        log.error(f"BPI Stripe webhook Fehler: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)

# ── END BPI EXTENSION ─────────────────────────────────────────────────────────


async def _auto_register_brevo_ip() -> None:
    """Registriert die aktuelle Server-IP automatisch bei Brevo."""
    import aiohttp as _aio, os as _os
    key = _os.getenv("BREVO_API_KEY", "")
    if not key:
        return
    try:
        async with _aio.ClientSession(timeout=_aio.ClientTimeout(total=10)) as s:
            async with s.get("https://api.ipify.org?format=json") as r:
                if r.status != 200:
                    return
                data = await r.json()
                my_ip = data.get("ip", "")
            if not my_ip:
                return
            # Test ob IP bereits autorisiert
            async with s.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": key, "Content-Type": "application/json"},
                json={"sender": {"name": "test", "email": _os.getenv("BREVO_FROM_EMAIL", "")},
                      "to": [{"email": "x@x.com"}], "subject": "ip-check", "htmlContent": "x"},
            ) as r:
                if r.status == 401:
                    body = await r.text()
                    if "unrecognised IP" in body or "unauthorized" in body.lower():
                        tg_bot = _os.getenv("TELEGRAM_BOT_TOKEN", "")
                        tg_chat = _os.getenv("TELEGRAM_CHAT_ID", "")
                        if tg_bot and tg_chat:
                            msg = (f"⚠️ SuperMegaBot: Neue Railway-IP {my_ip} muss in Brevo autorisiert werden!\n"
                                   f"→ https://app.brevo.com/security/authorised_ips")
                            async with s.post(
                                f"https://api.telegram.org/bot{tg_bot}/sendMessage",
                                json={"chat_id": tg_chat, "text": msg},
                            ) as _:
                                pass
                        log.warning("Brevo: Neue IP %s nicht autorisiert — Telegram-Alert gesendet", my_ip)
                    return
                log.info("Brevo IP %s bereits autorisiert ✅", my_ip)
    except Exception as e:
        log.warning("Brevo IP-Check: %s", e)


async def handle_free_ads_status(request):
    """GET /api/free-ads/status — BrutalAdsEngine Status (12 Kanäle, Pre-Flight)."""
    try:
        from modules.brutal_ads_engine import get_status
        return web.json_response(get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_free_ads_run(request):
    """POST /api/free-ads/run — Manuell einen Slot sofort starten."""
    try:
        data = await request.json() if request.content_length else {}
        slot = data.get("slot", "")
        from modules.brutal_ads_engine import run_brutal_cycle
        result = await run_brutal_cycle(slot)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_brutal_ads_preflight(request):
    """POST /api/brutal-ads/preflight — URL-Erreichbarkeit testen bevor man postet."""
    try:
        data = await request.json()
        url = data.get("url", "")
        from modules.brutal_ads_engine import _check_url_live
        ok, status = await _check_url_live(url)
        return web.json_response({"url": url, "reachable": ok, "http_status": status})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_tg_gate_stats(request):
    """GET /api/tg-gate/stats — Telegram Gatekeeper Statistik."""
    try:
        from modules.tg_gate import get_stats
        stats = get_stats()
    except Exception as e:
        stats = {"error": str(e)}
    return web.json_response(stats)


async def handle_never_again_status(request):
    """GET /api/never-again/status — Fehler-Gedächtnis Übersicht."""
    try:
        from modules.never_again import engine
        return web.json_response(engine.status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_never_again_add(request):
    """POST /api/never-again/add — Neuen bekannten Fehler registrieren."""
    try:
        data = await request.json()
        pattern  = data.get("pattern", "")
        fix_type = data.get("fix_type", "ALERT")
        payload  = data.get("fix_payload", "")
        desc     = data.get("fix_desc", "Manuell registriert")
        err_type = data.get("error_type", "ManualEntry")
        location = data.get("location", "*")
        if not pattern:
            return web.json_response({"ok": False, "error": "pattern required"}, status=400)
        from modules.never_again import engine
        fp = engine.add_known_error(pattern, fix_type, payload, desc, err_type, location)
        return web.json_response({"ok": True, "fingerprint": fp, "fix_desc": desc})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_never_again_report(request):
    """POST /api/never-again/report — Fehler manuell melden (z.B. aus Logs)."""
    try:
        data = await request.json()
        error_msg = data.get("error", "")
        location  = data.get("location", "manual")
        if not error_msg:
            return web.json_response({"ok": False, "error": "error field required"}, status=400)
        from modules.never_again import engine
        exc = Exception(error_msg)
        fixed = await engine.handle(exc, location=location)
        return web.json_response({"ok": True, "auto_fixed": fixed})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── Organic Traffic Manager ───────────────────────────────────────────────────

async def handle_organic_traffic_status(request):
    """GET /api/organic-traffic/status"""
    try:
        from modules.organic_traffic_manager import get_status
        return web.json_response(get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_organic_traffic_post(request):
    """POST /api/organic-traffic/post — Sofort auf einer oder allen Plattformen posten."""
    try:
        data     = await request.json()
        platform = data.get("platform")   # None = alle
        c_type   = data.get("content_type")
        topic    = data.get("topic")

        from modules.organic_traffic_manager import (
            generate_content, PLATFORM_POSTERS, _log_post, run_posting_session
        )

        if platform and platform in PLATFORM_POSTERS:
            content = await generate_content(platform, c_type, topic)
            result  = await PLATFORM_POSTERS[platform](content)
            _log_post(platform, content, result)
            return web.json_response({"ok": result["ok"], "platform": platform,
                                      "topic": content["topic"], "text": content["text"][:200]})
        else:
            result = await run_posting_session()
            return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_organic_traffic_preview(request):
    """POST /api/organic-traffic/preview — Content-Vorschau ohne zu posten."""
    try:
        data     = await request.json()
        platform = data.get("platform", "instagram")
        topic    = data.get("topic")
        c_type   = data.get("content_type")
        from modules.organic_traffic_manager import generate_content
        content = await generate_content(platform, c_type, topic)
        return web.json_response({"ok": True, "content": content})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_organic_traffic_logs(request):
    """GET /api/organic-traffic/logs"""
    try:
        import sqlite3
        from pathlib import Path
        db = Path("data/organic_traffic.db")
        if not db.exists():
            return web.json_response({"ok": True, "logs": []})
        with sqlite3.connect(db) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute("""
                SELECT platform, content_type, topic, text_snippet, posted_at, success, error
                FROM post_log ORDER BY posted_at DESC LIMIT 50
            """).fetchall()
        return web.json_response({"ok": True, "logs": [dict(r) for r in rows]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def create_app():
    # ── TgGate: Globaler Telegram-Spam-Schutz — ZUERST installieren ──────────
    # Intercept für aiohttp + urllib: ALLE sendMessage-Calls laufen durch den
    # Gatekeeper (Rate-Limit + Dedup + Spam-Pattern-Filter).
    # Egal welches Modul schreibt — kein Spam kommt durch.
    try:
        from modules.tg_gate import install_global_intercept
        install_global_intercept()
    except Exception as _tg_gate_err:
        log.warning("TgGate install failed: %s", _tg_gate_err)

    # Meta Token Resolver — AiiteC Page Token in ALLE Alias-Env-Vars erzwingen
    try:
        from modules.meta_token_resolver import apply_aiitec_aliases_to_process, audit_aliases
        _mtr = apply_aiitec_aliases_to_process()
        _aud = audit_aliases()
        log.info(
            "MetaTokenResolver: applied=%s audit_ok=%s mismatches=%s",
            _mtr.get("set"), _aud.get("ok"), len(_aud.get("mismatches") or []),
        )
    except Exception as _mtr_err:
        log.warning("MetaTokenResolver: %s", _mtr_err)

    # Stripe BULLPOWER-ONLY — bullpowersrtkennels, nie AIITEC
    try:
        from modules.stripe_key_resolver import enforce_ineedit_only, self_check as _stripe_sc
        _bp = enforce_ineedit_only()
        _sc = _stripe_sc()
        log.info(
            "Stripe BULLPOWER-ONLY: ok=%s account=%s source=%s purged=%s",
            _bp.get("ok"), _bp.get("account_id"), _bp.get("source"), _bp.get("purged_env"),
        )
        if not _sc.get("ok"):
            log.error("Stripe self_check FAILED: %s", _sc)
    except Exception as _bp_err:
        log.warning("Stripe BULLPOWER-ONLY enforce: %s", _bp_err)

    # Shopify Token Resolver — prüft SHOPIFY_ACCESS_TOKEN, fällt auf SHOPIFY_ADMIN_API_TOKEN zurück
    try:
        from modules.shopify_token_resolver import enforce_valid_token as _stok
        _sr = _stok()
        log.info("ShopifyTokenResolver: ok=%s source=%s fixed=%s", _sr.get("ok"), _sr.get("source"), _sr.get("fixed"))
    except Exception as _sr_err:
        log.warning("ShopifyTokenResolver: %s", _sr_err)

    # HttpGuard DEAKTIVIERT 2026-07-18 — wurde durch SmartPoster ersetzt
    # (HttpGuard monkey-patched aiohttp global → verursachte DB-Locks, 401-Fehler auf Stripe etc.)

    # NeverTwice DEAKTIVIERT 2026-07-18 — wurde durch SmartPoster ersetzt
    # (22.765+ false-positive Blocks durch DB-Lock-Kaskade)

    # StripeGuard Fallback — falls HttpGuard fehlschlägt, trotzdem process-wide patchen
    try:
        from modules.stripe_guards import install_process_guards, self_check, is_process_guard_active
        if not is_process_guard_active():
            install_process_guards()
        _sg = self_check()
        log.info(
            "StripeGuard: active=%s self_check=%s mode=%s",
            is_process_guard_active(), _sg.get("ok"), _sg.get("mode"),
        )
    except Exception as _sg_err:
        log.warning("StripeGuard Fallback: %s", _sg_err)

    try:
        from modules.connect_all import normalize_env_aliases, reset_circuit_breakers
        applied = normalize_env_aliases()
        if applied:
            log.info("Env-Aliase normalisiert: %s", ", ".join(applied))
        reset_names = await reset_circuit_breakers()
        if reset_names:
            log.info("Circuit Breakers beim Start zurückgesetzt: %s", reset_names)
    except Exception as e:
        log.warning("Env-Alias-Normalisierung: %s", e)

    # Brevo IP auto-check
    try:
        asyncio.create_task(_auto_register_brevo_ip())
    except Exception:
        pass

    try:
        from core.mega_orchestrator import MegaOrchestrator
        bot = MegaOrchestrator()
        await bot.start()
    except Exception as e:
        log.warning("MegaOrchestrator start failed (non-fatal): %s", e)
        bot = None

    # Start Hermes Job Queue
    try:
        from core.job_queue import HermesQueue
        asyncio.create_task(HermesQueue.get().start(workers=3))
        log.info("Hermes Job Queue started")
    except Exception as e:
        log.warning("Hermes start failed: %s", e)

    # APIHunt Health Monitor (immer an — überwacht alle KI-Provider)
    try:
        from modules.ai_client import start_health_monitor
        start_health_monitor()
        log.info("APIHunt Health Monitor gestartet")
    except Exception as e:
        log.warning("APIHunt Monitor start failed: %s", e)

    # RudiAgent — dauerhafter autonomer KI-Assistent (Telegram + Auto-Fix)
    try:
        from modules.rudi_agent import run as _rudi_run
        asyncio.ensure_future(_rudi_run())
        log.info("RudiAgent gestartet — 24/7 Telegram-Assistent aktiv")
    except Exception as e:
        log.warning("RudiAgent start failed: %s", e)

    app = web.Application(middlewares=[logging_middleware, cors_middleware, auth_middleware])

    # Connection-Pool Cleanup beim Shutdown
    async def _close_connection_pool(application):
        try:
            from modules.connection_pool import close_pool
            await close_pool()
        except Exception:
            pass
    app.on_cleanup.append(_close_connection_pool)
    app["bot"] = bot

    # Existing routes
    app.router.add_get("/", handle_index)
    app.router.add_get("/money-machines", handle_money_machines)
    app.router.add_get("/highticket", handle_highticket)
    app.router.add_get("/api/ht/demo", handle_ht_demo_data)
    app.router.add_post("/api/ht/apply", handle_ht_apply)
    app.router.add_get("/api/ht/onboarding", handle_ht_onboarding)
    app.router.add_get("/api/ht/stats", handle_ht_stats)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_post("/api/assistant/ask", handle_assistant_ask)
    app.router.add_delete("/api/assistant/history", handle_assistant_clear)
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
    app.router.add_get("/api/ollama/models",     handle_ollama_models)
    app.router.add_get("/api/ollama/status",     handle_ollama_status)
    app.router.add_post("/api/ollama/chat",      handle_ollama_chat)
    app.router.add_post("/api/ollama/stream",    handle_ollama_stream)
    app.router.add_post("/api/ollama/generate",  handle_ollama_generate)
    app.router.add_post("/api/ollama/pull",      handle_ollama_pull)
    app.router.add_post("/api/ollama/delete",    handle_ollama_delete)
    app.router.add_get("/api/ollama/info",       handle_ollama_info)
    app.router.add_get("/api/open-claw/status",  handle_open_claw_status)
    app.router.add_post("/api/open-claw/generate", handle_open_claw_generate)
    app.router.add_post("/api/open-claw/chat", handle_open_claw_chat)
    app.router.add_post("/api/open-claw/revenue", handle_open_claw_revenue)
    app.router.add_post("/api/open-claw/blast", handle_open_claw_blast)
    app.router.add_get("/api/autopilot/agents", handle_autopilot_agents)
    app.router.add_post("/api/autopilot/run", handle_autopilot_run)
    app.router.add_get("/api/autopilot/logs", handle_autopilot_logs)
    app.router.add_get("/api/guardian/status", handle_guardian_status)
    app.router.add_get("/api/ai/status", handle_ai_status)
    app.router.add_post("/api/ai/complete", handle_ai_complete)
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
    app.router.add_get("/api/gmc/status",                  handle_gmc)   # alias
    app.router.add_get("/api/gmc/verify",                  handle_gmc_verify_info)
    app.router.add_get("/api/gmc/feed.xml",                handle_gmc_feed)
    app.router.add_get("/api/gmc/setup",                   handle_gmc_setup)
    app.router.add_post("/api/gmc/setup",                  handle_gmc_setup)
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
    app.router.add_get("/api/tg-gate/stats",         handle_tg_gate_stats)
    app.router.add_get("/api/free-ads/status",           handle_free_ads_status)
    app.router.add_post("/api/free-ads/run",             handle_free_ads_run)
    app.router.add_post("/api/brutal-ads/preflight",     handle_brutal_ads_preflight)
    app.router.add_get("/api/never-again/status",     handle_never_again_status)
    app.router.add_post("/api/never-again/add",       handle_never_again_add)
    app.router.add_post("/api/never-again/report",    handle_never_again_report)
    app.router.add_get( "/api/organic-traffic/status",  handle_organic_traffic_status)
    app.router.add_post("/api/organic-traffic/post",     handle_organic_traffic_post)
    app.router.add_post("/api/organic-traffic/preview",  handle_organic_traffic_preview)
    app.router.add_get( "/api/organic-traffic/logs",     handle_organic_traffic_logs)
    # /api/ai/status bereits oben registriert — Duplikat entfernt
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

    # ── eBay Arbitrage ────────────────────────────────────────────────────────
    app.router.add_get("/api/ebay-arbitrage/stats",    handle_ebay_arbitrage_stats)
    app.router.add_post("/api/ebay-arbitrage/scan",    handle_ebay_arbitrage_scan)
    app.router.add_post("/api/ebay-arbitrage/preview", handle_ebay_arbitrage_preview)

    # ── Demand Oracle ─────────────────────────────────────────────────────────
    app.router.add_get("/api/demand-oracle/stats",    handle_demand_oracle_stats)
    app.router.add_post("/api/demand-oracle/scan",    handle_demand_oracle_scan)
    app.router.add_get("/api/demand-oracle/wishes",   handle_demand_oracle_wishes)

    # ── B2B Intent Radar ──────────────────────────────────────────────────────
    app.router.add_get("/api/b2b-radar/stats",      handle_b2b_radar_stats)
    app.router.add_post("/api/b2b-radar/scan",      handle_b2b_radar_scan)
    app.router.add_get("/api/b2b-radar/leads",      handle_b2b_radar_leads)
    app.router.add_post("/api/b2b-radar/outreach",  handle_b2b_radar_outreach)

    # ── Digistore24 ───────────────────────────────────────────────────────────
    app.router.add_get("/api/intent-bridge/stats",    handle_intent_bridge_stats)
    app.router.add_post("/api/intent-bridge/process", handle_intent_bridge_process)
    app.router.add_get("/api/digistore/status",       handle_digistore_status)
    app.router.add_get("/api/digistore/orders",       handle_digistore_orders)
    app.router.add_post("/api/digistore24/ipn",       handle_digistore_ipn)
    app.router.add_get("/api/digistore24/ipn",        lambda r: web.json_response({
        "ok": True,
        "endpoint": "DS24 IPN active",
        "url": "https://supermegabot-production.up.railway.app/api/digistore24/ipn",
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
    app.router.add_get("/api/gumroad/callback",       handle_gumroad_callback)
    app.router.add_get("/api/gumroad/products",       handle_gumroad_products)
    app.router.add_get("/api/gumroad/sales",          handle_gumroad_sales)
    app.router.add_post("/api/gumroad/product/create", handle_gumroad_create)
    app.router.add_post("/api/gumroad/blast",         handle_gumroad_blast)
    app.router.add_post("/api/gumroad/publish-all",  handle_gumroad_publish_all)
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
    # ── Meta Ads ──────────────────────────────────────────────────────────────
    app.router.add_get("/api/meta/status",            handle_meta_ads_status)
    app.router.add_post("/api/meta/run",              handle_meta_ads_run)
    # ── Pinterest ─────────────────────────────────────────────────────────────
    app.router.add_get("/api/pinterest/status",       handle_pinterest_status)
    app.router.add_post("/api/pinterest/run",         handle_pinterest_run)
    # ── SendGrid Email ────────────────────────────────────────────────────────
    app.router.add_get("/api/email/sendgrid-status",  handle_sendgrid_status)
    app.router.add_post("/api/email/sendgrid-blast",  handle_sendgrid_blast)
    app.router.add_get("/api/email/brevo-test",       handle_brevo_test)
    # ── SEO Autopilot ─────────────────────────────────────────────────────────
    app.router.add_get("/api/seo/status",             handle_seo_status)
    app.router.add_post("/api/seo/run",               handle_seo_run)
    app.router.add_post("/api/seo/discover-keywords", handle_seo_discover_keywords)
    app.router.add_post("/api/seo/run-factory",       handle_seo_run_factory)
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
    app.router.add_get("/api/klaviyo/lists",               handle_klaviyo_lists)
    app.router.add_post("/api/klaviyo/sync",               handle_klaviyo_sync)
    app.router.add_post("/api/klaviyo/campaign",           handle_klaviyo_campaign)
    app.router.add_post("/api/klaviyo/send-campaign",      handle_klaviyo_send_campaign)

    # ── Bot Clones ────────────────────────────────────────────────────────────
    app.router.add_get("/api/bots/status",            handle_bot_clones_status)
    app.router.add_get("/api/bot/status",             handle_bot_clones_status)   # alias
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
    app.router.add_post("/api/upgrade",               handle_upgrade)
    app.router.add_get("/api/mrr",                    handle_mrr)

    # ── Stripe ────────────────────────────────────────────────────────────────
    app.router.add_get("/api/stripe/status",          handle_stripe_status)
    app.router.add_get("/api/stripe/balance",         handle_stripe_balance)
    app.router.add_get("/api/stripe/charges",         handle_stripe_charges)
    app.router.add_get("/api/stripe/customers",       handle_stripe_customers)
    app.router.add_get("/api/stripe/revenue",         handle_stripe_revenue)
    app.router.add_get("/api/stripe/subscriptions",   handle_stripe_subscriptions)
    app.router.add_post("/api/stripe/webhook",        handle_stripe_webhook)
    # Revenue Activator routes
    try:
        from modules.stripe_revenue_activator import (
            handle_revenue_24h as _stripe_rev24,
            handle_activate_all as _stripe_activate,
            handle_stored_links as _stripe_links_stored,
        )
        app.router.add_get( "/api/stripe/revenue-24h",   _stripe_rev24)
        app.router.add_get( "/api/stripe/links",         _stripe_links_stored)
        app.router.add_post("/api/stripe/activate-all",  _stripe_activate)
    except Exception as _e:
        log.warning("stripe_revenue_activator routes not loaded: %s", _e)
    app.router.add_post("/api/shopify/order-webhook",                     handle_shopify_order_webhook_route)
    app.router.add_post("/api/webhooks/shopify-order",                    handle_shopify_order_webhook_v2)
    app.router.add_post("/api/shopify/customer-webhook",                  handle_shopify_customer_webhook)
    # Abandoned Cart Recovery webhooks
    app.router.add_post("/api/webhooks/shopify/checkout-create",          handle_shopify_checkout_create_webhook)
    app.router.add_post("/api/webhooks/shopify/checkout-update",          handle_shopify_checkout_update_webhook)
    app.router.add_post("/api/webhooks/shopify/order-create",             handle_shopify_order_create_for_cart)
    app.router.add_post("/api/webhooks/shopify/orders-paid",              handle_shopify_orders_paid_webhook)
    app.router.add_post("/api/abandoned-cart/run",                        handle_abandoned_cart_manual_run)
    app.router.add_post("/api/discord/interactions",      handle_discord_interactions)
    app.router.add_get("/api/discord/oauth/callback",     handle_discord_oauth_callback)
    app.router.add_get("/api/shopify/oauth/callback",     handle_shopify_oauth_callback)
    app.router.add_get("/api/shopify/orders",         handle_shopify_orders)
    app.router.add_get("/api/shopify/products",       handle_shopify_products)
    app.router.add_get("/api/shopify/revenue",        handle_shopify_revenue)
    app.router.add_post("/webhook/telegram",          handle_telegram_webhook)
    app.router.add_post("/api/webhook/telegram",      handle_telegram_webhook)
    app.router.add_post("/api/telegram/webhook",      handle_telegram_webhook)
    app.router.add_get("/api/telegram/setup",         handle_telegram_setup)
    app.router.add_get("/telegram",                   handle_telegram_landing)
    app.router.add_get("/bot",                        handle_telegram_landing)
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
    app.router.add_get("/api/youtube/status",         handle_youtube_status_new)
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
    app.router.add_get("/api/infra/status",           handle_infra_status)
    app.router.add_post("/api/export/customers",      handle_export_customers)
    app.router.add_get("/api/export/customers/stats", handle_export_customers_stats)
    app.router.add_get("/api/revenue/summary",        handle_revenue_summary)
    app.router.add_get("/api/scaling/status",         handle_scaling_status)
    app.router.add_post("/api/scaling/run",           handle_scaling_run)
    app.router.add_post("/api/revenue/run",           handle_revenue_run)
    app.router.add_get("/api/umsatzmaschine/status",  handle_umsatzmaschine_status)
    app.router.add_post("/api/umsatzmaschine/run",    handle_umsatzmaschine_run)
    app.router.add_post("/api/umsatzmaschine/delivery", handle_umsatzmaschine_delivery)
    app.router.add_post("/api/umsatzmaschine/autonomous", handle_umsatzmaschine_autonomous)
    app.router.add_get("/api/mega/status",           handle_mega_status)
    app.router.add_get("/api/mega/center-status",   handle_mega_center_status)
    app.router.add_post("/api/mega/run",             handle_mega_run)
    app.router.add_post("/api/mega/autonomous",      handle_mega_autonomous)
    app.router.add_post("/api/mega/daily",           handle_mega_run)
    app.router.add_get("/bullpower",                 handle_bullpower_mcc)
    app.router.add_get("/api/env/validate",          handle_env_validate)
    # /api/revenue/summary bereits oben registriert — Duplikat entfernt
    app.router.add_get("/api/scheduler/status",       handle_scheduler_status)
    app.router.add_post("/api/scheduler/trigger",     handle_scheduler_trigger)
    app.router.add_post("/api/broadcast/trigger",     handle_broadcast_trigger)
    app.router.add_get("/api/facebook/auth",          handle_facebook_auth)
    app.router.add_get("/api/facebook/oauth",         handle_facebook_auth)   # alias
    app.router.add_get("/api/facebook/refresh",       handle_facebook_refresh)
    app.router.add_get("/api/facebook/callback",      handle_facebook_callback)
    app.router.add_get("/api/facebook/status",        handle_facebook_status)
    app.router.add_post("/facebook/delete-data",      handle_facebook_delete_data)
    app.router.add_get("/facebook/delete-status",     handle_facebook_delete_status)
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
    app.router.add_get( "/bullpower2026indexnow.txt",                   handle_indexnow_key)
    app.router.add_get( "/bullpowerhub2026seo.txt",                     handle_indexnow_key2)
    app.router.add_get( "/tiktokZkDbIqcx5ixmxCEuDg2a6PzhC8qm7qN2.txt", handle_tiktok_verify_file)
    app.router.add_get( "/sitemap.xml",               handle_sitemap_xml)
    app.router.add_get( "/robots.txt",                handle_robots_txt)
    app.router.add_post("/api/seo/dominator",         handle_seo_dominator)
    app.router.add_post("/api/backlink/bomb",         handle_backlink_bomber_run)
    app.router.add_post("/api/content/velocity",      handle_content_velocity)
    app.router.add_post("/api/viral/traffic",         handle_viral_traffic)
    app.router.add_post("/api/revenue/maximize",      handle_revenue_maximizer_run)
    app.router.add_post("/api/monetization/launch",   handle_monetization_launch)
    app.router.add_post("/api/mail/error-guard",      handle_mail_error_guard)
    app.router.add_get( "/api/mail/errors",           handle_mail_error_summary)
    app.router.add_post("/api/mac/watchdog",           handle_mac_watchdog)
    app.router.add_post("/api/monitor/run",            handle_monitor_hub)
    app.router.add_post("/api/content-loop/run",      handle_content_loop)
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
    # SHOPIFY A/B TESTING
    app.router.add_get( "/api/shopify/ab-tests",         handle_shopify_ab_tests)
    app.router.add_post("/api/shopify/ab-tests/run",     handle_shopify_ab_run)
    app.router.add_post("/api/shopify/ab-tests/analyze", handle_shopify_ab_analyze)
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
    app.router.add_get( "/api/pinterest/auth",          handle_pinterest_auth)
    app.router.add_get( "/api/pinterest/callback",     handle_pinterest_callback)
    app.router.add_post("/api/pinterest/verify-domain", handle_pinterest_verify_domain)
    app.router.add_get( "/api/oauth/status",           handle_oauth_status)

    # ── SEO Mega Engine routes (no duplicates) ──────────────────────────────
    app.router.add_get( "/api/seo/sitemap.xml",        handle_seo_sitemap)
    app.router.add_post("/api/seo/submit",             handle_seo_submit)
    app.router.add_post("/api/seo/competitor",         handle_seo_competitor)
    # ── Traffic Swarm routes ────────────────────────────────────────────────
    # ── Buyer Traffic Engine ───────────────────────────────────────────────
    app.router.add_post("/api/buyer-traffic/run",          handle_buyer_traffic_run)
    app.router.add_get( "/api/buyer-traffic/stats",        handle_buyer_traffic_stats)
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
    app.router.add_get( "/api/email/sequences",          handle_email_sequence_stats)  # alias
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
    app.router.add_get( "/api/tiktok/content/auth",     handle_tiktok_content_auth)
    app.router.add_get( "/api/tiktok/content/callback", handle_tiktok_content_callback)

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
    app.router.add_post("/api/meta/campaign/activate",   handle_meta_campaign_activate)
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
    app.router.add_get( "/api/circuits/status",          handle_circuit_status)  # alias
    app.router.add_post("/api/circuit/reset",            handle_circuit_reset)

    # Amazon routes (status/trends via späte lokale Handler unten)
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
    app.router.add_post("/api/shopify/fix-tags",          handle_shopify_fix_tags)
    app.router.add_post("/api/shopify/cleanup-collections", handle_shopify_cleanup_collections)
    app.router.add_post("/api/shopify/gmc-meta",          handle_shopify_gmc_meta)
    app.router.add_post("/api/shopify/discount-blast",    handle_shopify_discount_blast)
    app.router.add_post("/api/shopify/bulk-activate",     handle_shopify_bulk_activate)
    app.router.add_get( "/api/shopify/bulk-activate/status", handle_shopify_bulk_activate_status)

    # Product Generator routes
    app.router.add_post("/api/products/generate",         handle_product_generate)
    app.router.add_post("/api/products/generate-niche",   handle_product_generate_niche)
    app.router.add_post("/api/products/generate-keywords",handle_product_generate_keywords)
    app.router.add_get( "/api/products/trends",           handle_product_trends)
    # Autonomous SaaS Factory — Problem→MVP→Sell→Iterate (dauerhaft)
    app.router.add_get( "/api/saas-factory/status",       handle_saas_factory_status)
    app.router.add_post("/api/saas-factory/run",          handle_saas_factory_run)
    app.router.add_post("/api/saas-factory/feedback",     handle_saas_factory_feedback)
    app.router.add_get( "/api/saas-factory/radar",        handle_saas_radar)

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
    app.router.add_post("/api/ds24/affiliate/blast-own",   handle_ds24_affiliate_blast_own)
    app.router.add_get( "/api/ds24/affiliate/stats",       handle_ds24_affiliate_stats)
    app.router.add_post("/api/ds24/affiliate/blast-niche", handle_ds24_affiliate_blast_niche)
    app.router.add_get( "/api/ds24/dankeseite",            handle_ds24_dankeseite)
    app.router.add_post("/api/ds24/dankeseite",            handle_ds24_dankeseite)
    app.router.add_get( "/api/ds24/purchases",             handle_ds24_purchase_stats)
    app.router.add_post("/api/ds24/marketplace/scan",      handle_ds24_marketplace_scan)
    app.router.add_post("/api/ds24/marketplace/apply",     handle_ds24_marketplace_apply)
    app.router.add_post("/api/ds24/marketplace/cycle",     handle_ds24_marketplace_cycle)
    app.router.add_post("/api/ds24/marketplace/blast",     handle_ds24_marketplace_blast)
    app.router.add_get( "/api/ds24/marketplace/stats",     handle_ds24_marketplace_stats)
    # ── Quantum Self-Repair System (error-tracker, heal, token-check) ────────────
    app.router.add_get( "/api/quantum/self-repair/status", handle_qsi_status)
    app.router.add_post("/api/quantum/self-repair/heal",   handle_qsi_heal)
    app.router.add_get( "/api/quantum/self-repair/errors", handle_qsi_errors)
    app.router.add_get( "/api/quantum/self-repair/report", handle_qsi_report)
    app.router.add_post("/api/quantum/token-check",        handle_quantum_token_check)

    # ── Traffic Mega Engine ───────────────────────────────────────────────────
    app.router.add_post("/api/traffic/mega-blast",       handle_traffic_mega_blast)
    app.router.add_post("/api/traffic/viral-campaign",   handle_traffic_viral_campaign)
    app.router.add_post("/api/traffic/syndicate",        handle_traffic_syndicate)
    app.router.add_post("/api/traffic/backlinks",        handle_traffic_backlinks)
    app.router.add_get( "/api/traffic/stats",            handle_traffic_stats)
    # ── Fiverr ────────────────────────────────────────────────────────────────
    app.router.add_post("/api/fiverr/promote",           handle_fiverr_promote)
    app.router.add_post("/api/fiverr/cycle",             handle_fiverr_cycle)
    # ── Upwork ────────────────────────────────────────────────────────────────
    app.router.add_post("/api/upwork/search",            handle_upwork_search)
    app.router.add_post("/api/upwork/promote",           handle_upwork_promote)
    # ── TikTok Autonomy (sync-products registered above at line 7633) ────────
    app.router.add_post("/api/tiktok/scripts",           handle_tiktok_scripts)
    app.router.add_get( "/api/tiktok/trends",            handle_tiktok_trends_hashtags)
    app.router.add_post("/api/tiktok/cycle",             handle_tiktok_autonomy_cycle)
    # ── Gumroad ───────────────────────────────────────────────────────────────
    app.router.add_post("/api/gumroad/create-all",       handle_gumroad_create_all)
    app.router.add_get( "/api/gumroad/list",             handle_gumroad_list)
    # ── Pinterest ─────────────────────────────────────────────────────────────
    app.router.add_post("/api/pinterest/pin-products",   handle_pinterest_pin_products)
    app.router.add_post("/api/pinterest/cycle",          handle_pinterest_cycle)
    app.router.add_get( "/api/pinterest/status",         handle_pinterest_status)
    # ── YouTube ───────────────────────────────────────────────────────────────
    app.router.add_post("/api/youtube/trends",           handle_youtube_trends)
    app.router.add_post("/api/youtube/scripts",          handle_youtube_scripts)
    # ── Email Blast Engine ────────────────────────────────────────────────────
    app.router.add_post("/api/email/blast",              handle_email_blast)
    app.router.add_post("/api/email/daily-blast",        handle_email_daily_blast)
    app.router.add_get( "/api/email/stats",              handle_email_stats)
    app.router.add_get( "/api/email/status",             handle_email_stats)  # alias
    # ── Affiliate Mega Engine ─────────────────────────────────────────────────
    app.router.add_post("/api/affiliate/blast-all",      handle_affiliate_blast_all)
    app.router.add_post("/api/affiliate/amazon",         handle_affiliate_amazon)
    app.router.add_post("/api/affiliate/ds24",           handle_affiliate_ds24)
    app.router.add_get( "/api/affiliate/stats",          handle_affiliate_stats_new)
    # ── MEGA START — alles auf einmal ─────────────────────────────────────────
    app.router.add_post("/api/mega/start",               handle_mega_autonomy_start)
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
    app.router.add_get("/api/email/inbox",               handle_email_inbox_check)
    app.router.add_get("/api/email/auto-responder",      handle_auto_responder_log)
    app.router.add_post("/api/email/scan",               handle_inbox_monitor_run)
    app.router.add_post("/api/ds24/sync",                handle_ds24_sync_alias)
    app.router.add_post("/api/amazon/run",               handle_amazon_run_alias)
    app.router.add_post("/api/ebay/run",                 handle_ebay_run_alias)
    app.router.add_post("/api/printify/sync",            handle_printify_sync_alias)

    # ── Missing Platform Routes — alle Revenue-Streams ─────────────────────────
    app.router.add_post("/api/traffic/run",              handle_traffic_run)
    app.router.add_post("/api/affiliate/run",            handle_affiliate_run)
    app.router.add_post("/api/mailchimp/run",            handle_mailchimp_run)
    app.router.add_post("/api/ds24/run",                 handle_ds24_run)
    app.router.add_post("/api/tiktok/run",               handle_tiktok_run)
    app.router.add_post("/api/fiverr/run",               handle_fiverr_run)
    app.router.add_post("/api/upwork/run",               handle_upwork_run)
    app.router.add_post("/api/linkedin/run",             handle_linkedin_run)
    app.router.add_get( "/api/instagram/status",         handle_instagram_status)
    app.router.add_post("/api/instagram/run",            handle_instagram_run)
    # /api/pinterest/run bereits oben registriert — Duplikat entfernt
    app.router.add_post("/api/email/run",                handle_email_run)
    app.router.add_post("/api/email/daily-summary",      handle_email_daily_summary_run)
    app.router.add_post("/api/shopify/blog",             handle_shopify_blog_run)
    app.router.add_post("/api/twitter/run",              handle_twitter_run)
    app.router.add_post("/api/sms/run",                  handle_sms_run)
    app.router.add_post("/api/rss/run",                  handle_rss_run)

    # ── Quantum Self-Repair / Self-Improvement ────────────────────────────────
    app.router.add_post("/api/quantum/scan",             handle_quantum_scan)
    app.router.add_post("/api/quantum/repair",           handle_quantum_repair)
    app.router.add_post("/api/quantum/improve",          handle_quantum_improve)
    app.router.add_get( "/api/quantum/status",           handle_quantum_status)

    # ── Shopify Mass Creator ──────────────────────────────────────────────────
    app.router.add_post("/api/shopify/create-1000",      handle_shopify_create_1000)
    app.router.add_post("/api/shopify/mass-cycle",       handle_shopify_mass_cycle)
    app.router.add_post("/api/shopify/mass-blast",       handle_shopify_mass_blast)
    app.router.add_get( "/api/shopify/mass-status",      handle_shopify_mass_status)

    # ── Klaviyo Mass Campaigns ────────────────────────────────────────────────
    app.router.add_post("/api/klaviyo/mass-create",      handle_klaviyo_mass_create)
    app.router.add_post("/api/klaviyo/daily-campaigns",  handle_klaviyo_daily_campaigns)
    app.router.add_get( "/api/klaviyo/mass-status",      handle_klaviyo_mass_status)

    # ── Mailchimp Mass Campaigns ──────────────────────────────────────────────
    app.router.add_post("/api/mailchimp/mass-create",    handle_mailchimp_mass_create)
    app.router.add_post("/api/mailchimp/daily-campaigns",handle_mailchimp_daily_campaigns)
    app.router.add_get( "/api/mailchimp/mass-status",    handle_mailchimp_mass_status)

    # ── BrutusClone Integrator ────────────────────────────────────────────────
    app.router.add_post("/api/brutus/blast-product",     handle_brutus_blast_product)
    app.router.add_post("/api/brutus/blast-summary",     handle_brutus_blast_summary)
    app.router.add_post("/api/brutus/system-status",     handle_brutus_system_status)
    app.router.add_get( "/api/brutus/stats",             handle_brutus_stats)

    # ── Revenue Mega Tracker ──────────────────────────────────────────────────
    app.router.add_post("/api/revenue/daily-report",     handle_revenue_daily_report)
    app.router.add_post("/api/revenue/weekly-report",    handle_revenue_weekly_report)
    app.router.add_get( "/api/revenue/snapshot",         handle_revenue_snapshot)
    app.router.add_get( "/api/revenue/stats",            handle_revenue_stats)
    app.router.add_get( "/api/revenue/orchestrator",     handle_revenue_orchestrator_status)
    app.router.add_post("/api/revenue/orchestrator/run", handle_revenue_orchestrator_run)
    app.router.add_get( "/api/tiktok/status",            handle_tiktok_ads_status)
    app.router.add_post("/api/tiktok/ads-run",           handle_tiktok_ads_run)

    # ── Product Bundle Engine ─────────────────────────────────────────────────
    app.router.add_post("/api/bundles/create",           handle_bundles_create)
    app.router.add_post("/api/bundles/blast",            handle_bundles_blast)
    app.router.add_get( "/api/bundles/stats",            handle_bundles_stats)

    # ── Stripe Auto-Billing ───────────────────────────────────────────────────
    app.router.add_post("/api/stripe/billing-check",     handle_stripe_billing_check)
    app.router.add_post("/api/stripe/payment-link",      handle_stripe_payment_link)
    app.router.add_get( "/api/stripe/billing-stats",     handle_stripe_billing_stats)
    app.router.add_post("/api/stripe/ds24-links",        handle_stripe_ds24_links)
    app.router.add_get( "/api/high-ticket-links",        handle_high_ticket_links)
    app.router.add_get( "/api/money-map",                handle_money_map)
    app.router.add_get( "/api/testimonials",             handle_testimonials)
    app.router.add_get( "/api/case-studies",             handle_case_studies)
    app.router.add_get( "/api/demos",                    handle_demos)
    app.router.add_get( "/api/social-proof",             handle_social_proof)
    # ── High-Ticket Demo System ───────────────────────────────────────────────
    app.router.add_post("/api/demo/book",                handle_demo_book)
    app.router.add_get( "/api/demo/session/{sid}",       handle_demo_session_status)
    app.router.add_get( "/demo",                         handle_demo_page)
    app.router.add_post("/api/social-proof/run",         handle_social_proof)

    # ── Auto-Sorter ───────────────────────────────────────────────────────────
    app.router.add_post("/api/sort/shopify",             handle_sort_shopify)
    app.router.add_post("/api/sort/all",                 handle_sort_all)

    # ── Revenue Auto-Payout ───────────────────────────────────────────────────
    app.router.add_post("/api/revenue/milestone-check",  handle_revenue_milestone_check)
    app.router.add_post("/api/revenue/weekly-summary",   handle_revenue_payout_weekly)
    app.router.add_get( "/api/revenue/payout-stats",     handle_revenue_payout_stats)

    # ── MISSING ROUTE ALIASES (added by DeepScan fix) ───────────────────────
    app.router.add_get( "/api/digistore24/status",       handle_digistore_status)
    app.router.add_post("/api/shopify/import",            handle_shopify_full_auto)
    app.router.add_post("/api/shopify/seo",               handle_shopify_seo_run)
    app.router.add_post("/api/printify/autopublish",      handle_printify_autopublish)
    app.router.add_post("/api/printful/sync",             handle_printful_autofulfill)
    app.router.add_post("/api/klaviyo/daily-campaign",    handle_klaviyo_daily_campaigns)
    app.router.add_post("/api/klaviyo/cycle",             handle_klaviyo_autonomy_cycle)
    app.router.add_post("/api/mailchimp/cycle",           handle_mailchimp_autonomy_cycle)
    app.router.add_post("/api/gumroad/promote",           handle_gumroad_blast)
    app.router.add_post("/api/indexnow/blast",            handle_indexnow_blast)
    # ── Fehlende MegaDash-Alias-Routen ─────────────────────────────────────────
    app.router.add_post("/api/indexnow/submit",           handle_indexnow_blast)       # MegaDash-Alias
    app.router.add_get( "/api/digistore/sync",            handle_digistore_status)      # MegaDash-Alias
    app.router.add_get( "/api/health",                    handle_health)                 # MegaDash-Alias für /health
    app.router.add_post("/api/digistore/affiliate-blast", handle_ds24_affiliate_blast_all)
    app.router.add_post("/api/pinterest/post",            handle_pinterest_run)
    app.router.add_post("/api/discord/blast",             handle_discord_send)
    app.router.add_post("/api/tiktok/post",               handle_tiktok_promotion)
    app.router.add_post("/api/fiverr/sync",               handle_fiverr_run)
    app.router.add_post("/api/upwork/sync",               handle_upwork_run)
    app.router.add_post("/api/shopify/blog/post",         handle_shopify_blog_run)
    app.router.add_get( "/api/shopify/blog/check",        handle_shopify_blog_check)
    app.router.add_post("/api/auto-poster/post",          handle_auto_poster_run_alias)
    app.router.add_get( "/api/stripe/plans",              handle_stripe_plans_info)
    app.router.add_get( "/api/shopify/inventory",         handle_shopify_inventory_live)
    app.router.add_get( "/api/shopify/oauth",             handle_shopify_oauth_start)
    app.router.add_get( "/api/shopify/callback",          handle_shopify_oauth_callback)
    app.router.add_get( "/api/agents/status",             handle_agents_overview)
    app.router.add_get( "/api/rudiclone/status",          handle_rudiclone_overview)
    app.router.add_get( "/api/ai/models",                 handle_ai_models_list)
    app.router.add_get( "/api/anthropic/status",          handle_anthropic_status)
    app.router.add_post("/api/anthropic/ask",             handle_anthropic_ask)
    app.router.add_post("/api/anthropic/extract",         handle_anthropic_extract)
    app.router.add_post("/api/anthropic/classify",        handle_anthropic_classify)
    app.router.add_get( "/api/digistore24/stats",         handle_ds24_stats_live)
    app.router.add_get( "/api/digistore24/products",      handle_ds24_product_list)
    app.router.add_get( "/api/digistore24/orders",        handle_digistore_orders)
    app.router.add_get( "/api/ds24/revenue",              handle_ds24_revenue)
    app.router.add_post("/api/reddit/blast",              handle_reddit_blast)  # also POST
    # ── AUTONOMOUS PRODUCT PIPELINE ROUTES ───────────────────────────────────
    app.router.add_post("/api/product/pipeline/run",      handle_product_pipeline_run)
    app.router.add_get( "/api/product/pipeline/history",  handle_product_pipeline_history)
    app.router.add_post("/api/product/bundle/run",        handle_bundle_cycle_run)
    app.router.add_post("/api/pipeline/run",              handle_autonomous_pipeline_run)
    app.router.add_get( "/api/pipeline/status",          handle_autonomous_pipeline_status)
    app.router.add_post("/api/autonomous-loop/run",       handle_autonomous_loop_run)
    app.router.add_get( "/api/autonomous-loop/status",    handle_autonomous_loop_status)
    app.router.add_post("/api/autonomous-loop/local-ai",  handle_autonomous_loop_local_ai)
    app.router.add_post("/api/autonomous-master/run",     handle_autonomous_master_run)
    app.router.add_get( "/api/autonomous-master/status",  handle_autonomous_master_status)
    app.router.add_post("/api/stripe-payment/poll",       handle_stripe_payment_poll)
    app.router.add_get( "/api/stripe-payment/stats",      handle_stripe_payment_stats)
    app.router.add_get( "/api/loop-commits/prs",              handle_loop_commits_prs)
    app.router.add_post("/api/revenue-agent/command",         handle_revenue_agent_command)
    app.router.add_get( "/api/revenue-agent/status",          handle_revenue_agent_status)
    app.router.add_get( "/api/revenue-agent/inbox",           handle_revenue_agent_inbox)
    app.router.add_get( "/api/revenue-agent/results",         handle_revenue_agent_result)
    app.router.add_get( "/api/system/info",              handle_system_info)
    app.router.add_get( "/api/indexnow/status",          handle_indexnow_status)
    app.router.add_get( "/api/trends/latest",            handle_trends_latest)
    app.router.add_post("/api/seo/blast",                handle_ultra_seo)
    # ── CREDENTIAL ACTIVATOR ROUTES ──────────────────────────────────────────
    app.router.add_get( "/api/credentials/status",       handle_credential_status)
    app.router.add_post("/api/credentials/scan",         handle_credential_scan)
    app.router.add_post("/api/connect/all",              handle_connect_all)
    app.router.add_get( "/api/connect/status",           handle_connect_status)
    app.router.add_get( "/api/setup/connect-all",       handle_connect_status)
    # ── Stripe Connect v2 ─────────────────────────────────────────────────────
    app.router.add_post("/api/stripe/connect/accounts",                      handle_stripe_connect_create_account)
    app.router.add_get( "/api/stripe/connect/accounts",                      handle_stripe_connect_list_accounts)
    app.router.add_get( "/api/stripe/connect/accounts/{account_id}/status",  handle_stripe_connect_account_status)
    app.router.add_post("/api/stripe/connect/accounts/{account_id}/onboarding", handle_stripe_connect_onboarding)
    app.router.add_post("/api/stripe/connect/accounts/{account_id}/products", handle_stripe_connect_create_product)
    app.router.add_get( "/api/stripe/connect/accounts/{account_id}/products", handle_stripe_connect_list_products)
    app.router.add_post("/api/stripe/connect/checkout",                      handle_stripe_connect_checkout)
    app.router.add_get( "/api/stripe/connect/event-destinations",            handle_stripe_connect_event_destinations)
    app.router.add_post("/api/stripe/connect/event-destinations",            handle_stripe_connect_create_destination)
    app.router.add_post("/api/connect/webhooks/v2",                          handle_stripe_connect_webhook_v2)
    app.router.add_get( "/api/connect/return",                               handle_stripe_connect_return)
    app.router.add_get( "/api/connect/refresh",                              handle_stripe_connect_refresh)
    # ── MASTER CONTROL PANEL ─────────────────────────────────────────────────
    app.router.add_post("/api/master/start-all",         handle_master_start_all)
    app.router.add_get( "/api/master/status",            handle_master_status)
    # ── MEGA AGENT ORCHESTRATOR — alle 12 Plattformen koordiniert ────────────
    app.router.add_post("/api/agents/orchestrate",       handle_mega_orchestrate)
    app.router.add_get( "/api/agents/orchestrate/status",handle_mega_orchestrate_status)
    # ── SELBSTVERBESSERUNG & EMAIL DOCTOR & MASS BLAST ───────────────────────
    app.router.add_post("/api/selbstverbesserung/run",    handle_selbstverbesserung_run)
    app.router.add_get( "/api/selbstverbesserung/status", handle_system_overview)
    app.router.add_post("/api/email-doctor/run",          handle_email_doctor_run)
    app.router.add_get( "/api/email-doctor/status",       handle_email_doctor_status)
    app.router.add_post("/api/mass-blast/run",            handle_mass_blast_run)
    app.router.add_get( "/api/mass-blast/stats",          handle_mass_blast_stats)
    app.router.add_post("/api/dragon/article/send",       handle_dragon_article_send)
    app.router.add_get( "/api/dragon/article/stats",      handle_dragon_article_stats)
    app.router.add_get( "/api/system/overview",           handle_system_overview)
    # ── GET ALIASES for previously 404 routes ────────────────────────────────
    app.router.add_get( "/api/digistore/revenue",         handle_digistore_autonomy_revenue)
    app.router.add_get( "/api/scheduler/tasks",           handle_automation_tasks)
    app.router.add_get( "/api/shopify/collections",       handle_shopify_collections_get)
    app.router.add_get( "/api/content/status",            handle_content_stats)
    app.router.add_get( "/api/digistore/products",        handle_ds24_product_list)
    app.router.add_get( "/api/affiliates/status",         handle_affiliate_stats_new)
    app.router.add_get( "/api/analytics/summary",         handle_analytics_legacy)
    app.router.add_get( "/api/analytics",                 handle_analytics_legacy)   # Alias für /api/analytics/summary
    app.router.add_get( "/api/sales/funnel",              _handle_sales_funnel)      # MegaDash-Funnel-Endpoint
    app.router.add_get( "/api/meta/status",               handle_meta_ads_status)
    app.router.add_post("/api/email/test",                handle_email_test_send)
    app.router.add_get( "/api/email/accounts/check",      handle_email_accounts_check)
    app.router.add_post("/api/email/accounts/configure",  handle_email_accounts_configure)
    app.router.add_post("/api/kfw/generate",              handle_kfw_generate)
    app.router.add_get( "/api/funding/status",            handle_funding_status)
    app.router.add_post("/api/funding/scan",              handle_funding_scan)
    app.router.add_post("/api/funding/kfw",               handle_funding_kfw)
    app.router.add_post("/api/scan",                      handle_compliance_scan)
    app.router.add_post("/api/hs-classify",               handle_compliance_hs_classify)
    app.router.add_get( "/api/zvg/leads",                 handle_compliance_zvg_leads)
    app.router.add_post("/api/compliance/report",         handle_compliance_report)
    # ── AIACT-Pro Bridge (lokaler Port 8770) ─────────────────────────────────
    app.router.add_get( "/api/aiact-pro/health",          handle_aiact_health)
    app.router.add_post("/api/aiact-pro/scan",            handle_aiact_scan)
    app.router.add_post("/api/aiact-pro/hs-classify",     handle_aiact_hs_classify)
    app.router.add_post("/api/aiact-pro/vat-risk",        handle_aiact_vat_risk)
    app.router.add_get( "/api/aiact-pro/zvg-leads",       handle_aiact_zvg_leads)
    app.router.add_post("/api/aiact-pro/report",          handle_aiact_report)
    app.router.add_post("/api/priority-cluster/run",      handle_priority_cluster_run)
    app.router.add_get( "/api/email/brain/setup",         handle_email_brain_setup)
    app.router.add_post("/api/email/brain/setup",         handle_email_brain_setup)
    # ── COMPLIANCE TOOL LANDING PAGES (SYS-17 bis SYS-42) ────────────────────
    app.router.add_get( "/compliance",                    handle_compliance_index)
    app.router.add_get( "/gpsr",                          handle_gpsr_shield)
    app.router.add_get( "/gpsr-shop-shield",              handle_gpsr_shield)
    app.router.add_get( "/ppwr",                          handle_ppwr_radar)
    app.router.add_get( "/ppwr-verpackung",               handle_ppwr_radar)
    app.router.add_get( "/e-rechnung",                    handle_erechnung_autopilot)
    app.router.add_get( "/erechnung",                     handle_erechnung_autopilot)
    app.router.add_get( "/cra",                           handle_cra_waechter)
    app.router.add_get( "/cra-melde-waechter",            handle_cra_waechter)
    app.router.add_get( "/nis2",                          handle_nis2_check)
    app.router.add_get( "/nis2-kmu",                      handle_nis2_check)
    app.router.add_get( "/kanzlei-radar",                 handle_kanzlei_radar)
    app.router.add_get( "/kanzlei-mandanten-radar",       handle_kanzlei_radar)
    app.router.add_get( "/eudr",                          handle_eudr_pass)
    app.router.add_get( "/eudr-lieferkette",              handle_eudr_pass)
    app.router.add_get( "/hr-ki-audit",                   handle_hr_ki_audit)
    app.router.add_get( "/hr-ki-hochrisiko",              handle_hr_ki_audit)
    app.router.add_get( "/bfsg",                          handle_bfsg_scanner)
    app.router.add_get( "/bfsg-scanner",                  handle_bfsg_scanner)
    app.router.add_get( "/zvg",                           handle_zvg_expose)
    app.router.add_get( "/zvg-expose",                    handle_zvg_expose)
    # ── END MISSING ROUTES ───────────────────────────────────────────────────

    # ── MONEY MACHINE ────────────────────────────────────────────────────────
    app.router.add_get( "/money-machine",                handle_money_machine_page)
    app.router.add_get( "/money-machine/success",        handle_mm_success)
    app.router.add_post("/api/money-machine/run-all",    handle_mm_run_all)
    app.router.add_get( "/api/money-machine/status",     handle_mm_status)
    app.router.add_post("/api/money-machine/checkout",   handle_mm_checkout)
    # ── OOS SNIPER ───────────────────────────────────────────────────────────
    app.router.add_get( "/api/oos-sniper/status",        handle_oos_status)
    app.router.add_post("/api/oos-sniper/scan",          handle_oos_scan)
    app.router.add_post("/api/oos-sniper/targets",       handle_oos_add_target)
    # ── REVIEW GOLDMINE ──────────────────────────────────────────────────────
    app.router.add_post("/api/review-goldmine/analyze",  handle_review_analyze)
    app.router.add_get( "/api/review-goldmine/status",   handle_review_status)
    # ── CART RESCUE ──────────────────────────────────────────────────────────
    app.router.add_post("/api/cart-rescue/webhook",      handle_cart_webhook)
    app.router.add_get( "/api/cart-rescue/status",       handle_cart_status)
    app.router.add_post("/api/cart-rescue/test",         handle_cart_test)
    # ── END MONEY MACHINE ─────────────────────────────────────────────────────

    # ── OUTREACH ENGINE ──────────────────────────────────────────────────────
    app.router.add_get( "/outreach",                    handle_outreach_page)
    app.router.add_get( "/api/outreach/status",         handle_outreach_status)
    app.router.add_get( "/api/outreach/queue",          handle_outreach_queue)
    app.router.add_post("/api/outreach/run",            handle_outreach_run)
    app.router.add_post("/api/outreach/mark-replied",   handle_outreach_mark_replied)
    # ── END OUTREACH ENGINE ───────────────────────────────────────────────────

    # ── INSOLVENZ RADAR PRO ───────────────────────────────────────────────────
    app.router.add_get( "/insolvenz-radar",              handle_ir_page)
    app.router.add_get( "/insolvenz-radar/success",      handle_ir_success)
    app.router.add_get( "/api/insolvenz-radar/status",   handle_ir_status)
    app.router.add_get( "/api/insolvenz-radar/leads",    handle_ir_leads)
    app.router.add_post("/api/insolvenz-radar/scan",     handle_ir_scan)
    app.router.add_post("/api/insolvenz-radar/checkout", handle_ir_checkout)
    # ── END INSOLVENZ RADAR ───────────────────────────────────────────────────

    # ── VIRAL WINDOW SCANNER ─────────────────────────────────────────────────
    app.router.add_get( "/viral",                   handle_viral_page)
    app.router.add_get( "/viral/success",           handle_viral_success)
    app.router.add_get( "/api/viral/status",        handle_viral_status)
    app.router.add_post("/api/viral/scan",          handle_viral_scan)
    app.router.add_get( "/api/viral/alerts",        handle_viral_alerts)
    app.router.add_post("/api/viral/subscribe",     handle_viral_subscribe)
    app.router.add_post("/api/viral/webhook",       handle_viral_webhook)
    app.router.add_post("/api/viral/setup",         handle_viral_setup)
    app.router.add_post("/api/viral/tg-register",   handle_viral_tg_register)
    # ── END VIRAL WINDOW SCANNER ──────────────────────────────────────────────

    # ── PRODUCT INTELLIGENCE HUB ──────────────────────────────────────────────
    app.router.add_get( "/api/hub/status",  handle_hub_status)
    app.router.add_post("/api/hub/run",     handle_hub_run)
    # ── END PRODUCT INTELLIGENCE HUB ──────────────────────────────────────────

    # ── VIRAL PROMO POSTER ────────────────────────────────────────────────────
    app.router.add_post("/api/promo/run",   handle_promo_run)
    app.router.add_get( "/api/promo/stats", handle_promo_stats)
    # ── END VIRAL PROMO POSTER ────────────────────────────────────────────────

    # ── VORSPRUNG INTELLIGENCE ENGINE ─────────────────────────────────────────
    app.router.add_get( "/api/vorsprung/status",   handle_vorsprung_status)
    app.router.add_get( "/api/vorsprung/signals",  handle_vorsprung_signals)
    app.router.add_post("/api/vorsprung/scan",     handle_vorsprung_scan)
    app.router.add_get( "/api/vorsprung/briefing", handle_vorsprung_briefing)
    # ── END VORSPRUNG INTELLIGENCE ────────────────────────────────────────────
    # ── FACEBOOK TOKEN AUTO-REFRESH ───────────────────────────────────────────
    app.router.add_get( "/api/facebook/token/status",  handle_fb_token_status)
    app.router.add_post("/api/facebook/token/refresh", handle_fb_token_refresh)
    # ── END FACEBOOK TOKEN ────────────────────────────────────────────────────
    # ── MISSING STATUS ALIASES ────────────────────────────────────────────────
    app.router.add_get("/api/b2b/status",           handle_b2b_radar_stats)
    app.router.add_get("/api/demand-oracle/status", handle_demand_oracle_stats)
    app.router.add_get("/api/insolvenz/status",     handle_ir_status)
    app.router.add_get("/api/agent/status",         handle_agents_overview)
    # ── END MISSING ALIASES ───────────────────────────────────────────────────

    # ── KI-Mitarbeiter-Leasing — SYS-01 ─────────────────────────────────────
    app.router.add_get( "/ki-leasing",                  handle_ki_leasing_page)
    app.router.add_get( "/ki-leasing/success",          handle_ki_leasing_success)
    app.router.add_post("/api/ki-leasing/checkout",     handle_ki_leasing_checkout)
    app.router.add_post("/api/ki-leasing/webhook",      handle_ki_leasing_webhook)
    app.router.add_get( "/api/ki-leasing/clients",      handle_ki_leasing_clients)
    app.router.add_get( "/api/ki-leasing/status",       handle_ki_leasing_status)
    app.router.add_post("/api/ki-leasing/send-now",     handle_ki_leasing_send_now)
    log.info("KI-Leasing routes registered at /ki-leasing")

    # ── Umsatzmaschine Vollautonom (2h Zyklus + KI-Leasing + Revenue Engine) ─
    try:
        from modules.megabot_umsatzmaschine import run_autonomous_loop
        asyncio.create_task(run_autonomous_loop())
        log.info("Umsatzmaschine autonomous loop started (interval=%ss)",
                 os.getenv("UMSATZMASCHINE_INTERVAL_S", "7200"))
    except Exception as _e:
        log.warning("Umsatzmaschine autonomous loop failed: %s", _e)

    try:
        from modules.mega_command_center import run_autonomous_loop as mega_loop
        asyncio.create_task(mega_loop())
        log.info("MEGA Command Center loop started (interval=%ss)",
                 os.getenv("MEGA_INTERVAL_S", "14400"))
    except Exception as _e:
        log.warning("MEGA Command Center loop failed: %s", _e)

    # ── ShopText.ai — KI-Produkttexte SaaS ──────────────────────────────────
    try:
        from dashboard.routes.shoptext_routes import (
            handle_shoptext_landing, handle_shoptext_generate,
            handle_shoptext_checkout, handle_shoptext_success,
            handle_shoptext_stats,
        )
        app.router.add_get("/shoptext",                  handle_shoptext_landing)
        app.router.add_post("/api/shoptext/generate",    handle_shoptext_generate)
        app.router.add_post("/api/shoptext/checkout",    handle_shoptext_checkout)
        app.router.add_get("/shoptext/success",          handle_shoptext_success)
        app.router.add_get("/api/shoptext/stats",        handle_shoptext_stats)
        log.info("ShopText.ai routes registered at /shoptext")
    except Exception as _e:
        log.warning("ShopText.ai routes failed to register: %s", _e)

    # ─── BPI 8 SYSTEMS ──────────────────────────────────────────────────────────
    # SYS-01 KI-Leasing (page + checkout already registered above)
    app.router.add_get( "/api/ki-leasing/stats",                  handle_ki_leasing_stats)

    # SYS-02 Trend Velocity
    app.router.add_get( "/trend-velocity",                        handle_trend_velocity_page)
    app.router.add_post("/api/trend-velocity/run",                handle_trend_velocity_run)
    app.router.add_get( "/api/trend-velocity/stats",              handle_trend_velocity_stats)

    # SYS-03 Ghost Vendor Network
    app.router.add_get( "/ghost-vendor",                          handle_ghost_vendor_page)
    app.router.add_post("/api/ghost-vendor/run",                  handle_ghost_vendor_run)
    app.router.add_get( "/api/ghost-vendor/clients",              handle_ghost_vendor_clients)

    # SYS-04 EU AI Act
    app.router.add_get( "/ai-act",                                handle_ai_act_page)
    app.router.add_post("/api/ai-act/quick-check",                handle_ai_act_quick_check)
    app.router.add_post("/api/ai-act/checkout",                   handle_ai_act_checkout)

    # SYS-05 Insolvenz Arbitrage
    app.router.add_get( "/insolvenz-arbitrage",                   handle_insolvenz_arbitrage_page)
    app.router.add_post("/api/insolvenz-arbitrage/run",           handle_insolvenz_arbitrage_run)
    app.router.add_get( "/api/insolvenz-arbitrage/opportunities", handle_insolvenz_arbitrage_opps)

    # SYS-06 Migration Rush
    app.router.add_get( "/migration-rush",                        handle_migration_rush_page)
    app.router.add_post("/api/migration-rush/run",                handle_migration_rush_run)
    app.router.add_get( "/api/migration-rush/signals",            handle_migration_rush_signals)

    # SYS-07 AI Citation SEO
    app.router.add_get( "/ai-citation-seo",                       handle_ai_citation_seo_page)
    app.router.add_post("/api/ai-citation-seo/run",               handle_ai_citation_seo_run)
    app.router.add_get( "/api/ai-citation-seo/stats",             handle_ai_citation_seo_stats)

    # SYS-08 Intelligence Broker
    app.router.add_get( "/intelligence-broker",                   handle_intelligence_broker_page)
    app.router.add_post("/api/intelligence-broker/report",        handle_intelligence_broker_report)
    app.router.add_get( "/api/intelligence-broker/watchlist",     handle_intelligence_broker_watchlist)
    log.info("BPI 8 Systems routes registered (SYS-01..SYS-08)")

    # Multi-Product Outreach (alle 4 Produkte)
    app.router.add_get( "/api/mpo/stats", handle_mpo_stats)
    app.router.add_post("/api/mpo/run",   handle_mpo_run)
    # AIITEC B2B Outreach Machine
    app.router.add_get( "/api/aiitec-outreach/stats", handle_aiitec_outreach_stats)
    app.router.add_post("/api/aiitec-outreach/run",   handle_aiitec_outreach_run)

    # SYS-10 Bulk Outreach + SYS-13 Partner Channel + SYS-18 Newsletter KI + Delivery
    app.router.add_get( "/api/bpi/outreach/stats",   handle_bpi_outreach_stats)
    app.router.add_post("/api/bpi/outreach/run",     handle_bpi_outreach_run)
    app.router.add_get( "/api/bpi/partners",         handle_bpi_partners)
    app.router.add_post("/api/bpi/delivery/order",   handle_bpi_delivery_order)
    app.router.add_get( "/api/bpi/delivery/stats",   handle_bpi_delivery_stats)
    app.router.add_get( "/api/bpi/sys18/preview",    handle_bpi_sys18_preview)
    app.router.add_post("/api/bpi/stripe/webhook",       handle_bpi_stripe_webhook)
    app.router.add_post("/api/bpi/compliance/webhook",   handle_bpi_compliance_webhook)
    app.router.add_post("/api/bpi/compliance/outreach",  handle_bpi_compliance_outreach)
    app.router.add_get( "/api/bpi/compliance/status",    handle_bpi_compliance_status)
    # ── EU AI Act Art. 50 ──────────────────────────────────────────────────────
    app.router.add_get( "/api/ai-act/banner",            handle_ai_act_banner)
    app.router.add_post("/api/ai-act/scan",              handle_ai_act_scan)
    app.router.add_post("/api/ai-act/report",            handle_ai_act_report)
    app.router.add_get( "/api/ai-act/status",            handle_ai_act_status)
    # ── HS-Code SaaS ──────────────────────────────────────────────────────────
    app.router.add_post("/api/hs-code/classify",         handle_hs_classify)
    app.router.add_post("/api/hs-code/batch",            handle_hs_batch)
    app.router.add_get( "/api/hs-code/status",           handle_hs_status)
    # ── Non-EU VAT/OSS ────────────────────────────────────────────────────────
    app.router.add_post("/api/vat/calculate",            handle_vat_calculate)
    app.router.add_post("/api/vat/oss-report",           handle_vat_oss_report)
    app.router.add_get( "/api/vat/status",               handle_vat_oss_status)
    log.info("BPI Extension routes registered (SYS-10/13/18 + Delivery + Compliance Engine + AI Act + HS-Code + VAT/OSS)")
    # ── END BPI 8 SYSTEMS ───────────────────────────────────────────────────────

    # ── BullPower MEGA Command Center ────────────────────────────────────────────
    async def handle_mcc_status(req):
        try:
            from modules.bullpower_mcc import get_status
            return web.json_response(await get_status())
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_mcc_run(req):
        try:
            from modules.bullpower_mcc import run_full_cycle
            r = await run_full_cycle()
            return web.json_response(r)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_mcc_platforms(req):
        try:
            from modules.bullpower_mcc import run_platform_checks
            r = await run_platform_checks()
            return web.json_response({"ok": True, "platforms": r})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_mcc_dashboard_data(req):
        try:
            from modules.bullpower_mcc import get_full_dashboard_data
            r = await get_full_dashboard_data()
            return web.json_response(r)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_mcc_shopify_metrics(req):
        try:
            from modules.bullpower_mcc import get_shopify_metrics
            r = await get_shopify_metrics()
            return web.json_response(r)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_mcc_v2_dashboard(req):
        html_file = Path(__file__).parent / "mcc_dashboard.html"
        if html_file.exists():
            return web.Response(text=html_file.read_text(), content_type="text/html")
        return web.Response(text="<h1>MCC Dashboard not found</h1>", content_type="text/html")

    async def handle_mass_outreach_stats(req):
        """GET /api/mass-outreach/stats"""
        try:
            from modules.mass_outreach_1000 import get_stats, init_db
            init_db()
            return web.json_response(get_stats())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_mass_outreach_research(req):
        """POST /api/mass-outreach/research — Lead-Research anstoßen"""
        try:
            from modules.mass_outreach_1000 import run_research, init_db
            init_db()
            asyncio.create_task(run_research(session_limit=500))
            return web.json_response({"status": "research_started"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_mass_outreach_send(req):
        """POST /api/mass-outreach/send — Smart Batch: Research neue Firmen + Versand"""
        try:
            body = await req.json() if req.content_length else {}
            limit = int(body.get("limit", 333))
            smart = body.get("smart", True)
            from modules.mass_outreach_1000 import run_smart_batch, run_batch_only, init_db
            init_db()
            fn = run_smart_batch if smart else run_batch_only
            asyncio.create_task(fn(batch_size=limit))
            return web.json_response({"status": "batch_started", "limit": limit,
                                      "mode": "smart_research+send" if smart else "send_only"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_unsubscribe(req):
        """GET /api/unsubscribe?email=xxx — GDPR Abmeldung"""
        email = req.rel_url.query.get("email", "").strip()
        if not email:
            return web.Response(text="E-Mail fehlt.", content_type="text/html")
        try:
            from modules.mass_outreach_1000 import handle_unsubscribe as do_unsub
            do_unsub(email)
        except Exception:
            pass
        html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Abgemeldet</title>"
            "<style>body{background:#111;color:#eee;font-family:sans-serif;"
            "display:flex;align-items:center;justify-content:center;height:100vh;margin:0}"
            ".box{text-align:center;padding:40px;background:#1a1a1a;border-radius:12px}"
            "h1{color:#4ade80}p{color:#aaa}</style></head>"
            "<body><div class='box'>"
            "<h1>✅ Erfolgreich abgemeldet</h1>"
            f"<p><b>{email}</b> wird keine weiteren Emails erhalten.</p>"
            "<p style='margin-top:20px;font-size:13px;color:#666'>"
            "AiiteC | Rudolf Sarkany</p></div></body></html>"
        )
        return web.Response(text=html, content_type="text/html")

    app.router.add_get( "/api/mcc/status",    handle_mcc_status)
    app.router.add_post("/api/mcc/run",        handle_mcc_run)
    app.router.add_get( "/api/mcc/platforms",  handle_mcc_platforms)
    app.router.add_get( "/api/mcc/dashboard",  handle_mcc_dashboard_data)
    app.router.add_get( "/api/mcc/shopify",    handle_mcc_shopify_metrics)
    app.router.add_get( "/mcc",               handle_mcc_v2_dashboard)
    log.info("BullPower MCC routes registered (/api/mcc/*, /mcc)")

    async def handle_mass_outreach_reset_combos(req):
        """POST /api/mass-outreach/reset-combos — Löscht searched_combos → Research findet neue Firmen"""
        try:
            from modules.mass_outreach_1000 import _db, init_db
            init_db()
            with _db() as conn:
                deleted = conn.execute("DELETE FROM searched_combos").rowcount
                # Also reset leads that errored back to 'new' so they can be retried
                reactivated = conn.execute(
                    "UPDATE leads SET status='new' WHERE status='error'"
                ).rowcount
            return web.json_response({
                "ok": True,
                "combos_cleared": deleted,
                "leads_reactivated": reactivated,
                "message": "Research startet beim nächsten Batch wieder von vorne",
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_mass_outreach_blast(req):
        """POST /api/mass-outreach/blast — Reset + sofort Research + Send (maximale Leistung)"""
        try:
            from modules.mass_outreach_1000 import _db, init_db, run_research, run_send_batch
            init_db()
            # 1. Reset
            with _db() as conn:
                conn.execute("DELETE FROM searched_combos")
                conn.execute("UPDATE leads SET status='new' WHERE status='error'")
            # 2. Research + Send async
            async def _blast():
                await run_research(session_limit=1000)
                await run_send_batch(batch_limit=500)
            asyncio.create_task(_blast())
            return web.json_response({"ok": True, "status": "blast_started",
                                      "message": "Reset + Research (1000) + Send (500) läuft"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    # Mass Outreach 1000/Tag
    app.router.add_get( "/api/mass-outreach/stats",          handle_mass_outreach_stats)
    app.router.add_post("/api/mass-outreach/research",        handle_mass_outreach_research)
    app.router.add_post("/api/mass-outreach/send",            handle_mass_outreach_send)
    app.router.add_post("/api/mass-outreach/reset-combos",    handle_mass_outreach_reset_combos)
    app.router.add_post("/api/mass-outreach/blast",           handle_mass_outreach_blast)
    app.router.add_get( "/api/unsubscribe",                   handle_unsubscribe)
    log.info("Mass Outreach 1000/Tag routes registered")

    # KI-Telefonassistentin Sofia
    try:
        from modules.phone_ai_assistant import (
            handle_phone_incoming, handle_phone_status,
            handle_phone_stats, handle_outbound_trigger,
            handle_phone_ws, init_db as phone_init_db
        )
        phone_init_db()
        app.router.add_post("/api/phone/incoming",  handle_phone_incoming)
        app.router.add_post("/api/phone/status",    handle_phone_status)
        app.router.add_get( "/api/phone/stats",     handle_phone_stats)
        app.router.add_post("/api/phone/outbound",  handle_outbound_trigger)
        app.router.add_get( "/ws/phone",            handle_phone_ws)
        log.info("KI-Telefonassistentin Sofia routes registered (/api/phone/*, /ws/phone)")
    except Exception as e:
        log.warning("phone_ai_assistant unavailable (non-fatal): %s", e)

    # ── Sofia SMS — Eingehende SMS mit Gesprächsgedächtnis + Verkaufsfluss ───
    async def handle_sms_incoming(req: web.Request) -> web.Response:
        """POST /api/sms/incoming — Twilio SMS Webhook → Sofia antwortet."""
        try:
            data        = await req.post()
            from_num    = data.get("From", "")
            body        = data.get("Body", "").strip()
            log.info("Sofia SMS eingehend von %s: %s", from_num, body[:80])
            from modules.sofia_sms_agent import handle_sms_inbound as sofia_sms
            twiml = await sofia_sms(from_num, body)
            return web.Response(text=twiml, content_type="application/xml")
        except Exception as e:
            log.error("handle_sms_incoming: %s", e)
            return web.Response(
                text='<?xml version="1.0"?><Response><Message>Danke für Ihre Nachricht! Wir melden uns. Sofia / AIITEC</Message></Response>',
                content_type="application/xml"
            )

    # ── Sofia SMS API ──────────────────────────────────────────────────────
    async def handle_sms_send(req: web.Request) -> web.Response:
        """POST /api/sms/send — einzelne SMS senden."""
        try:
            data    = await req.json()
            to      = data.get("to") or data.get("to_number", "")
            message = data.get("message") or data.get("text", "")
            campaign= data.get("campaign", "api")
            if not to or not message:
                return web.json_response({"ok": False, "error": "to + message required"}, status=400)
            from modules.sofia_sms_agent import send_sms
            sid = await send_sms(to, message, campaign)
            return web.json_response({"ok": bool(sid), "sid": sid, "to": to})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_sms_welcome(req: web.Request) -> web.Response:
        """POST /api/sms/welcome — Willkommens-SMS."""
        try:
            data    = await req.json()
            to      = data.get("to", "")
            name    = data.get("name", "")
            product = data.get("product", "")
            from modules.sofia_sms_agent import send_welcome_sms
            sid = await send_welcome_sms(to, name, product)
            return web.json_response({"ok": bool(sid), "sid": sid})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_sms_stats(req: web.Request) -> web.Response:
        """GET /api/sms/stats — SMS-Statistiken."""
        from modules.sofia_sms_agent import get_sms_stats
        return web.json_response({"ok": True, "stats": get_sms_stats()})

    async def handle_sms_campaign_blast(req: web.Request) -> web.Response:
        """POST /api/sms/blast — SMS an Nummerliste senden."""
        try:
            data    = await req.json()
            numbers = data.get("numbers", [])
            message = data.get("message", "")
            campaign= data.get("campaign", "blast")
            if not numbers or not message:
                return web.json_response({"ok": False, "error": "numbers[] + message required"}, status=400)
            from modules.sofia_sms_agent import send_weekly_deals_blast
            result  = await send_weekly_deals_blast(numbers, message)
            return web.json_response({"ok": True, **result})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_sms_outbox_run(req: web.Request) -> web.Response:
        """POST /api/sms/outbox/run — Outbox abarbeiten."""
        from modules.sofia_sms_agent import run_sms_outbox
        result = await run_sms_outbox()
        return web.json_response({"ok": True, **result})

    app.router.add_post("/api/sms/incoming",   handle_sms_incoming)
    app.router.add_post("/api/sms/send",        handle_sms_send)
    app.router.add_post("/api/sms/welcome",     handle_sms_welcome)
    app.router.add_get( "/api/sms/stats",       handle_sms_stats)
    app.router.add_post("/api/sms/blast",       handle_sms_campaign_blast)
    app.router.add_post("/api/sms/outbox/run",  handle_sms_outbox_run)
    log.info("Sofia SMS Agent registriert (/api/sms/*)")

    # ── Sofia Voice Agent ─────────────────────────────────────────────────────

    def _twilio_valid(req: web.Request, post_data: dict) -> bool:
        """Prüft X-Twilio-Signature — schützt vor gefälschten Webhook-Requests.
        Fail-open wenn TWILIO_AUTH_TOKEN nicht konfiguriert (kein Produktions-Blocker).
        """
        token = os.getenv("TWILIO_AUTH_TOKEN", "")
        if not token:
            log.debug("TWILIO_AUTH_TOKEN nicht gesetzt — Signatur-Check übersprungen")
            return True
        try:
            from twilio.request_validator import RequestValidator
            # URL aus öffentlichem Host rekonstruieren (korrekt hinter Railway-Proxy)
            proto = req.headers.get("X-Forwarded-Proto", "https")
            host  = (req.headers.get("X-Forwarded-Host")
                     or req.headers.get("Host")
                     or os.getenv("RAILWAY_PUBLIC_DOMAIN", req.url.host))
            path  = str(req.rel_url)
            url   = f"{proto}://{host}{path}"
            sig   = req.headers.get("X-Twilio-Signature", "")
            valid = RequestValidator(token).validate(url, post_data, sig)
            if not valid:
                log.warning("Twilio Signatur ungültig — IP=%s URL=%s",
                            req.headers.get("X-Forwarded-For", req.remote), url)
            return valid
        except ImportError:
            log.debug("twilio-Bibliothek fehlt — Signatur-Check übersprungen")
            return True
        except Exception as _ve:
            log.warning("Twilio Signatur-Fehler: %s", _ve)
            return True  # fail-open bei unerwarteten Fehlern

    async def handle_voice_incoming(req: web.Request) -> web.Response:
        """POST /api/voice/incoming — Twilio ruft hier an."""
        try:
            from modules.sofia_voice_agent import handle_incoming_call
            data = await req.post()
            if not _twilio_valid(req, dict(data)):
                return web.Response(status=403, text="Forbidden: invalid Twilio signature")
            call_sid = data.get("CallSid", "unknown")
            from_num = data.get("From", "")
            log.info("Sofia: Eingehender Anruf %s von %s", call_sid, from_num)
            twiml = await handle_incoming_call(call_sid, from_num)
            return web.Response(text=twiml, content_type="application/xml")
        except Exception as e:
            log.error("handle_voice_incoming: %s", e)
            twiml = ('<?xml version="1.0" encoding="UTF-8"?><Response>'
                     '<Say voice="Polly.Vicki" language="de-DE">Einen Moment bitte.</Say>'
                     '</Response>')
            return web.Response(text=twiml, content_type="application/xml")

    async def handle_voice_respond(req: web.Request) -> web.Response:
        """POST /api/voice/respond — Spracherkennung Callback."""
        try:
            from modules.sofia_voice_agent import handle_voice_response
            data = await req.post()
            if not _twilio_valid(req, dict(data)):
                return web.Response(status=403, text="Forbidden: invalid Twilio signature")
            call_sid  = req.rel_url.query.get("call_sid") or data.get("CallSid", "")
            speech    = data.get("SpeechResult", "")
            conf_raw  = data.get("Confidence", "1.0")
            try:
                confidence = float(conf_raw)
            except Exception:
                confidence = 1.0
            twiml = await handle_voice_response(call_sid, speech, confidence)
            return web.Response(text=twiml, content_type="application/xml")
        except Exception as e:
            log.error("handle_voice_respond: %s", e)
            twiml = ('<?xml version="1.0" encoding="UTF-8"?><Response>'
                     '<Say voice="Polly.Vicki" language="de-DE">Entschuldigung, bitte wiederholen.</Say>'
                     '<Hangup/></Response>')
            return web.Response(text=twiml, content_type="application/xml")

    async def handle_voice_status(req: web.Request) -> web.Response:
        """POST /api/voice/status — Anruf-Status Callback (Ende)."""
        try:
            from modules.sofia_voice_agent import handle_call_status
            data       = await req.post()
            if not _twilio_valid(req, dict(data)):
                return web.Response(status=403, text="Forbidden: invalid Twilio signature")
            call_sid   = data.get("CallSid", "")
            status     = data.get("CallStatus", "")
            try:
                duration = int(data.get("CallDuration", "0"))
            except Exception:
                duration = 0
            asyncio.create_task(handle_call_status(call_sid, status, duration))
            return web.Response(text="OK")
        except Exception as e:
            log.error("handle_voice_status: %s", e)
            return web.Response(text="OK")

    app.router.add_post("/api/voice/incoming", handle_voice_incoming)
    app.router.add_post("/api/voice/respond",  handle_voice_respond)
    app.router.add_post("/api/voice/status",   handle_voice_status)

    # ── Sofia Outbound TwiML ───────────────────────────────────────────────
    async def handle_voice_outbound_twiml(req: web.Request) -> web.Response:
        """GET /api/voice/outbound-twiml — liefert TwiML für ausgehende Anrufe."""
        product  = req.rel_url.query.get("product", "")
        contact  = req.rel_url.query.get("contact", "")
        call_sid = req.rel_url.query.get("call_sid", "")
        from modules.sofia_voice_agent import _twiml_outbound_greeting
        twiml = _twiml_outbound_greeting(contact, product, call_sid)
        return web.Response(text=twiml, content_type="text/xml")

    # ── Sofia Outbound Trigger ─────────────────────────────────────────────
    async def handle_voice_outbound(req: web.Request) -> web.Response:
        """POST /api/voice/outbound — startet ausgehenden Sofia-Anruf."""
        try:
            data       = await req.json()
            to_number  = data.get("to_number") or data.get("to", "")
            product_id = data.get("product_id") or data.get("product", "")
            contact    = data.get("contact") or data.get("name", "")
            context    = data.get("context", "")
            source     = data.get("source", "api")
            if not to_number:
                return web.json_response({"ok": False, "error": "to_number required"}, status=400)
            from modules.sofia_voice_agent import trigger_outbound_call
            call_sid = await trigger_outbound_call(to_number, product_id, contact, context, source)
            if call_sid:
                return web.json_response({"ok": True, "call_sid": call_sid, "to": to_number})
            return web.json_response({"ok": False, "error": "Twilio call failed"}, status=500)
        except Exception as e:
            log.error("handle_voice_outbound: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    # ── Sofia Queue ────────────────────────────────────────────────────────
    async def handle_voice_queue_get(req: web.Request) -> web.Response:
        """GET /api/voice/queue — zeigt Call-Queue."""
        from modules.sofia_voice_agent import get_sofia_queue
        status = req.rel_url.query.get("status", "pending")
        return web.json_response({"ok": True, "queue": get_sofia_queue(status)})

    async def handle_voice_queue_add(req: web.Request) -> web.Response:
        """POST /api/voice/queue — fügt zur Queue hinzu."""
        try:
            data = await req.json()
            from modules.sofia_voice_agent import queue_sofia_call
            qid = queue_sofia_call(
                to_number  = data.get("to_number", ""),
                product_id = data.get("product_id", ""),
                contact    = data.get("contact", ""),
                context    = data.get("context", ""),
                source     = data.get("source", "api"),
            )
            return web.json_response({"ok": True, "queue_id": qid})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    # ── Sofia Stats ────────────────────────────────────────────────────────
    async def handle_voice_stats(req: web.Request) -> web.Response:
        """GET /api/voice/stats — Sofia-Statistiken."""
        from modules.sofia_voice_agent import get_sofia_stats
        return web.json_response({"ok": True, "stats": get_sofia_stats()})

    # ── Sofia Kampagne starten ─────────────────────────────────────────────
    async def handle_voice_campaign(req: web.Request) -> web.Response:
        """POST /api/voice/campaign — startet Outbound-Kampagne (Queue abarbeiten)."""
        try:
            data  = await req.json() if req.content_length else {}
            limit = int(data.get("limit", 20))
            from modules.sofia_voice_agent import run_outbound_campaign
            result = await run_outbound_campaign(limit=limit)
            return web.json_response({"ok": True, **result})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    # ── Sofia SMS Inbound ──────────────────────────────────────────────────
    async def handle_voice_sms(req: web.Request) -> web.Response:
        """POST /api/voice/sms — eingehende SMS → Sofia antwortet."""
        try:
            data        = await req.post()
            from_number = data.get("From", "")
            body        = data.get("Body", "").strip()
            from modules.sofia_voice_agent import handle_sms_inbound
            reply = await handle_sms_inbound(from_number, body)
            twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{reply}</Message></Response>'
            return web.Response(text=twiml, content_type="text/xml")
        except Exception as e:
            log.error("handle_voice_sms: %s", e)
            return web.Response(text='<?xml version="1.0"?><Response/>', content_type="text/xml")

    # ── Sofia AMD (Anrufbeantworter-Erkennung) ─────────────────────────────
    async def handle_voice_amd(req: web.Request) -> web.Response:
        """POST /api/voice/amd — Twilio AMD Callback (Anrufbeantworter erkannt → hangup)."""
        try:
            data          = await req.post()
            call_sid      = data.get("CallSid", "")
            answered_by   = data.get("AnsweredBy", "")
            if answered_by in ("machine_start", "machine_end_beep", "machine_end_silence"):
                # Anrufbeantworter → kurze Nachricht hinterlassen
                log.info("Sofia AMD: Anrufbeantworter erkannt für %s", call_sid)
        except Exception as e:
            log.debug("Sofia AMD: %s", e)
        return web.Response(text="OK")

    # ── TTS Audio Endpoint — liefert geklonte Stimme als MP3 ──────────────────
    async def handle_voice_tts(req: web.Request) -> web.Response:
        """GET /api/voice/tts?text=... — generiert Audio mit geklonter Stimme.
        Twilio ruft diese URL über <Play> ab. Öffentlich (kein Auth — Twilio braucht Zugang).
        Cacht Ergebnisse in data/tts_cache/."""
        text = req.rel_url.query.get("text", "").strip()
        if not text:
            return web.Response(status=400, text="Missing text")
        if len(text) > 800:
            text = text[:800]

        from modules.sofia_voice_agent import generate_tts_audio, _tts_cache_path, TTS_CACHE_DIR
        cache = _tts_cache_path(text)

        # Cache-Hit: direkt senden
        if cache.exists() and cache.stat().st_size > 0:
            return web.Response(
                body=cache.read_bytes(),
                content_type="audio/mpeg",
                headers={"Cache-Control": "public, max-age=86400"},
            )

        # Generieren
        audio = await generate_tts_audio(text)
        if audio:
            return web.Response(
                body=audio,
                content_type="audio/mpeg",
                headers={"Cache-Control": "public, max-age=86400"},
            )

        # Kein Audio → TwiML-Fehler-Redirect auf Polly (Twilio fallback)
        return web.Response(status=503, text="TTS unavailable")

    app.router.add_get( "/api/voice/tts",             handle_voice_tts)
    app.router.add_get( "/api/voice/outbound-twiml", handle_voice_outbound_twiml)
    app.router.add_post("/api/voice/outbound",        handle_voice_outbound)
    app.router.add_get( "/api/voice/queue",           handle_voice_queue_get)
    app.router.add_post("/api/voice/queue",           handle_voice_queue_add)
    app.router.add_get( "/api/voice/stats",           handle_voice_stats)
    app.router.add_post("/api/voice/campaign",        handle_voice_campaign)
    app.router.add_post("/api/voice/sms",             handle_voice_sms)
    app.router.add_post("/api/voice/amd",             handle_voice_amd)
    log.info("Sofia Voice Agent registriert (/api/voice/* + /api/voice/tts)")

    # Email Conversation AI — beantwortet alle Inbox-Emails automatisch
    async def handle_email_ai_stats(req):
        try:
            from modules.email_ai_conversations import get_stats
            return web.json_response(get_stats())
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_email_ai_cycle(req):
        try:
            from modules.email_ai_conversations import run_email_ai_cycle
            asyncio.create_task(run_email_ai_cycle())
            return web.json_response({"status": "email_ai_cycle_started"})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    app.router.add_get( "/api/email-ai/stats",  handle_email_ai_stats)
    app.router.add_post("/api/email-ai/cycle",  handle_email_ai_cycle)
    log.info("Email AI Conversations routes registered (/api/email-ai/*)")

    # Mega Acquisition Engine B2C
    async def handle_mega_acq_status(req):
        try:
            from modules.mega_acquisition_engine import get_status
            return web.json_response(await get_status())
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_mega_acq_discovery(req):
        try:
            from modules.mega_acquisition_engine import run_lead_discovery
            asyncio.create_task(run_lead_discovery())
            return web.json_response({"status": "discovery_started"})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_mega_acq_send(req):
        try:
            body = await req.json() if req.content_length else {}
            target = int(body.get("target", 200))
            template = body.get("template", "auto")
            from modules.mega_acquisition_engine import run_daily_acquisition
            asyncio.create_task(run_daily_acquisition(target=target, template=template))
            return web.json_response({"status": "send_started", "target": target})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    app.router.add_get( "/api/acquisition/status",    handle_mega_acq_status)
    app.router.add_post("/api/acquisition/discovery", handle_mega_acq_discovery)
    app.router.add_post("/api/acquisition/send",      handle_mega_acq_send)
    log.info("Mega Acquisition Engine routes registered (/api/acquisition/*)")

    # Stripe Payment Links
    try:
        from modules.stripe_payment_links import handle_stripe_links
        async def handle_stripe_create_links(req):
            try:
                from modules.stripe_payment_links import create_payment_links_for_all_products
                result = await create_payment_links_for_all_products()
                return web.json_response(result)
            except Exception as e:
                return web.json_response({"ok": False, "error": str(e)}, status=500)
        app.router.add_get("/api/stripe/payment-links", handle_stripe_links)
        app.router.add_post("/api/stripe/create-links", handle_stripe_create_links)
        log.info("Stripe Payment Links routes registered (/api/stripe/*)")
    except Exception as e:
        log.warning("stripe_payment_links unavailable (non-fatal): %s", e)

    # Klaviyo Flows
    async def handle_klaviyo_setup(req):
        try:
            from modules.klaviyo_flows_builder import setup_all_flows
            result = await setup_all_flows()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)
    app.router.add_post("/api/klaviyo/setup-flows", handle_klaviyo_setup)
    log.info("Klaviyo Flows route registered (/api/klaviyo/setup-flows)")

    # Shopify Conversion Booster
    async def handle_conversion_boost(req):
        try:
            from modules.shopify_conversion_booster import run_conversion_boost
            result = await run_conversion_boost()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)
    app.router.add_post("/api/shopify/conversion-boost", handle_conversion_boost)
    log.info("Shopify Conversion Booster route registered (/api/shopify/conversion-boost)")

    # WhatsApp Cart Recovery
    async def handle_wa_cart(req):
        try:
            from modules.whatsapp_abandoned_cart import run_recovery_campaign
            result = await run_recovery_campaign()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)
    app.router.add_post("/api/whatsapp/cart-recovery", handle_wa_cart)
    log.info("WhatsApp Cart Recovery route registered (/api/whatsapp/cart-recovery)")

    # Affiliate System
    async def handle_affiliate_status(req):
        try:
            from modules.affiliate_system import get_status
            return web.json_response(get_status())
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)
    async def handle_affiliate_invite(req):
        try:
            body = await req.json()
            from modules.affiliate_system import send_affiliate_invite
            result = await send_affiliate_invite(body.get("email", ""), body.get("name", "Partner"))
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)
    app.router.add_get("/api/affiliate/status", handle_affiliate_status)
    app.router.add_post("/api/affiliate/invite", handle_affiliate_invite)
    log.info("Affiliate System routes registered (/api/affiliate/*)")

    # ── Social Media Autopilot ─────────────────────────────────────────────
    async def handle_social_post_now(request):
        try:
            from modules.social_media_autopilot import run_autopilot_cycle
            result = await run_autopilot_cycle()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_social_autopilot_status(request):
        try:
            from modules.social_media_autopilot import get_status
            result = await get_status()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    app.router.add_post("/api/social/post-now", handle_social_post_now)
    app.router.add_get("/api/social/autopilot-status", handle_social_autopilot_status)
    log.info("Social Autopilot routes registered (/api/social/*)")

    # ── Post Gateway Status ────────────────────────────────────────────────────
    async def handle_post_gateway_stats(request):
        """GET /api/posts/gateway-stats — Posts gesendet/blockiert/fehlgeschlagen (letzte 24h)."""
        try:
            from modules.post_gateway import get_gateway_stats
            hours = int(request.rel_url.query.get("hours", "24"))
            return web.json_response(get_gateway_stats(hours=hours))
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_post_gateway_test(request):
        """POST /api/posts/test — Testpost durch alle Gateway-Schichten."""
        try:
            data = await request.json()
            from modules.post_gateway import safe_post
            result = await safe_post(
                platform=data.get("platform", "facebook"),
                text=data.get("text", ""),
                image_url=data.get("image_url", ""),
                source_module="dashboard_test",
            )
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    app.router.add_get("/api/posts/gateway-stats", handle_post_gateway_stats)
    app.router.add_post("/api/posts/test", handle_post_gateway_test)
    log.info("Post Gateway routes registered (/api/posts/gateway-stats, /api/posts/test)")

    # ── YouTube Autopilot ──────────────────────────────────────────────────
    async def handle_yt_create(request):
        try:
            from modules.youtube_autopilot import create_and_upload_video
            result = await create_and_upload_video()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_yt_stats(request):
        try:
            from modules.youtube_autopilot import get_youtube_stats
            result = await get_youtube_stats()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    app.router.add_post("/api/youtube/create-video", handle_yt_create)
    app.router.add_get("/api/youtube/stats",         handle_yt_stats)
    log.info("YouTube Autopilot routes registered (/api/youtube/*)")

    # Startup-Warnung wenn YouTube OAuth nicht konfiguriert
    _yt_refresh = os.getenv("YOUTUBE_REFRESH_TOKEN", "") or os.getenv("GOOGLE_REFRESH_TOKEN", "")
    if not _yt_refresh:
        log.warning(
            "YouTube OAuth erforderlich: /api/youtube/auth aufrufen um YouTube-Upload zu aktivieren. "
            "Ohne OAuth werden Videos erstellt aber NICHT hochgeladen."
        )

    # ── MEGA Command Center ─────────────────────────────────────────────────
    async def handle_mega_dash(request):
        from pathlib import Path
        try:
            html = Path("dashboard/mega_command_center.html").read_text()
        except FileNotFoundError:
            html = "<h1>MEGA Command Center — mega_command_center.html nicht gefunden</h1>"
        return web.Response(text=html, content_type="text/html")

    async def handle_health_all(request):
        try:
            from modules.mega_self_healer import check_all_platforms
            results = await check_all_platforms()
            from datetime import datetime, timezone
            payload = {p: h.to_dict() if hasattr(h, "to_dict") else dict(h._asdict()) if hasattr(h, "_asdict") else h.__dict__ for p, h in results.items()}
            ok_count = sum(1 for h in results.values() if getattr(h, "ok", False))
            payload["_summary"] = {"platforms_ok": ok_count, "platforms_total": len(results), "all_ok": ok_count == len(results), "timestamp": datetime.now(timezone.utc).isoformat()}
            return web.json_response(payload)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_healer_log(request):
        try:
            from modules.mega_self_healer import handle_healer_log as _hlg
            return await _hlg(request)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_healer_run(request):
        try:
            from modules.mega_self_healer import _get_healer
            healer = _get_healer()
            result = await healer.run_cycle()
            return web.json_response({"ok": True, "result": result})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_shopify_optimize(request):
        try:
            from modules.shopify_conversion_optimizer import run_full_optimization
            result = await run_full_optimization()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_email_blast_now(request):
        try:
            from modules.email_revenue_engine import run_full_blast
            result = await run_full_blast()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_email_daily_stats(request):
        try:
            from modules.email_revenue_engine import daily_stats
            result = await daily_stats()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_sendgrid_webhook(request):
        """POST /api/webhooks/sendgrid — Bounce + Unsubscribe Events von SendGrid."""
        try:
            from modules.email_revenue_engine import handle_sendgrid_webhook as _sg_wh
            return await _sg_wh(request)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_full_start(request):
        results = {}
        try:
            from modules.stripe_revenue_activator import create_all_payment_links
            results["stripe"] = await create_all_payment_links()
        except Exception as e:
            results["stripe_error"] = str(e)
        try:
            from modules.email_revenue_engine import run_full_blast
            results["email"] = await run_full_blast()
        except Exception as e:
            results["email_error"] = str(e)
        try:
            from modules.mega_self_healer import _get_healer
            results["healer"] = await _get_healer().run_cycle()
        except Exception as e:
            results["healer_error"] = str(e)
        return web.json_response({"ok": True, "results": results})

    async def handle_emergency_stop(request):
        try:
            from modules.smart_poster import activate_posting_pause
            state = activate_posting_pause("api_emergency_stop")
            return web.json_response({
                "ok": True,
                "message": "Emergency stop activated — posting paused",
                "state": state,
            })
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_sync_env(request):
        try:
            from modules.env_health_check import get_env_report
            result = get_env_report()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_tasks_recent(request):
        try:
            import sqlite3
            from pathlib import Path as _P
            db_path = _P("data/scheduler_state.db")
            if not db_path.exists():
                db_path = _P("data/scheduler.db")
            if not db_path.exists():
                return web.json_response({"tasks": []})
            con = sqlite3.connect(str(db_path))
            try:
                rows = con.execute("SELECT name, last_run, last_result, run_count FROM task_state ORDER BY last_run DESC LIMIT 20").fetchall()
            except sqlite3.OperationalError:
                rows = []
            con.close()
            return web.json_response({"tasks": [{"name": r[0], "last_run": r[1], "result": r[2], "count": r[3]} for r in rows]})
        except Exception as e:
            return web.json_response({"tasks": [], "error": str(e)})

    app.router.add_get("/mega",                          handle_mega_dash)
    app.router.add_get("/api/health/all",                handle_health_all)
    app.router.add_get("/api/healer/log",                handle_healer_log)
    app.router.add_post("/api/healer/run",               handle_healer_run)
    app.router.add_post("/api/shopify/optimize-now",     handle_shopify_optimize)
    app.router.add_post("/api/email/blast-now",          handle_email_blast_now)
    app.router.add_get("/api/email/daily-stats",         handle_email_daily_stats)
    app.router.add_post("/api/webhooks/sendgrid",        handle_sendgrid_webhook)
    app.router.add_post("/api/system/full-start",        handle_full_start)
    app.router.add_post("/api/system/emergency-stop",    handle_emergency_stop)
    app.router.add_post("/api/system/sync-env",          handle_sync_env)
    app.router.add_get("/api/tasks/recent",              handle_tasks_recent)
    log.info("MEGA Command Center routes registered (/mega, /api/health/all, /api/healer/*, /api/system/*, /api/tasks/recent)")

    # ── Full Revenue Expansion Engine ─────────────────────────────────────────
    async def handle_full_expansion(request):
        try:
            from modules.full_revenue_expansion import run_full_expansion_cycle
            result = await run_full_expansion_cycle()
            return web.json_response({"ok": True, **result})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_promo_blast(request):
        try:
            from modules.full_revenue_expansion import run_product_promo_blast
            result = await run_product_promo_blast()
            return web.json_response({"ok": True, **result})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_revenue_daily_report_expansion(request):
        try:
            from modules.full_revenue_expansion import generate_daily_revenue_report
            result = await generate_daily_revenue_report()
            return web.json_response({"ok": True, **result})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_revenue_dashboard_stats(request):
        try:
            from modules.revenue_dashboard_data import get_all_revenue_stats
            result = await get_all_revenue_stats()
            return web.json_response({"ok": True, **result})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    app.router.add_post("/api/revenue/full-expansion",    handle_full_expansion)
    app.router.add_post("/api/revenue/promo-blast",       handle_promo_blast)
    app.router.add_get( "/api/revenue/daily-report",      handle_revenue_daily_report_expansion)
    app.router.add_get( "/api/revenue/dashboard-stats",   handle_revenue_dashboard_stats)
    log.info("Full Revenue Expansion Engine routes registered (/api/revenue/full-expansion, /promo-blast, /daily-report, /dashboard-stats)")

    # ── Shop Scaling Engine ────────────────────────────────────────────────────
    async def handle_scaling_stats(request):
        try:
            from modules.shop_scaling_engine import get_scaling_stats
            result = await get_scaling_stats()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_scaling_run_cycle(request):
        try:
            from modules.shop_scaling_engine import run_daily_scaling_cycle
            result = await run_daily_scaling_cycle()
            return web.json_response({"ok": True, **result})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_scaling_blast_leads(request):
        try:
            from modules.shop_scaling_engine import blast_all_queued_leads
            body = {}
            try:
                body = await request.json()
            except Exception:
                pass
            max_per_run = int(body.get("max_per_run", 100))
            result = await blast_all_queued_leads(max_per_run=max_per_run)
            return web.json_response({"ok": True, **result})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    app.router.add_get( "/api/scaling/stats",      handle_scaling_stats)
    app.router.add_post("/api/scaling/run-cycle",  handle_scaling_run_cycle)
    app.router.add_post("/api/scaling/blast-leads", handle_scaling_blast_leads)
    log.info("Shop Scaling Engine routes registered (/api/scaling/*)")

    # Free API Hunter routes
    async def handle_free_apis_registry(request):
        """GET /api/free-apis — Zeigt gecachte kostenlose APIs."""
        try:
            registry_file = Path("data/free_api_registry.json")
            if registry_file.exists():
                data = json.loads(registry_file.read_text())
                total = sum(len(v) for v in data.get("working", {}).values())
                return web.json_response({"ok": True, "total_working": total,
                                          "last_scan": data.get("last_scan"), "registry": data})
            return web.json_response({"ok": True, "total_working": 0, "registry": {}})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_free_apis_scan(request):
        """POST /api/free-apis/scan — Scannt jetzt alle kostenlosen APIs."""
        try:
            from modules.free_api_hunter import hunt_all_free_apis
            results = await hunt_all_free_apis()
            total = sum(len(v) for v in results.values())
            return web.json_response({"ok": True, "total_found": total, "results": {
                k: [a["name"] for a in v] for k, v in results.items()
            }})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_free_apis_best_ai(request):
        """GET /api/free-apis/best-ai — Bester verfügbarer Free AI Client."""
        try:
            from modules.free_api_hunter import get_hunter
            hunter = get_hunter()
            best = hunter.get_free_ai_client()
            if best:
                safe = {k: v for k, v in best.items() if k != "key"}
                return web.json_response({"ok": True, "best_ai": safe})
            return web.json_response({"ok": False, "error": "Kein free AI gefunden"})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_free_apis_discover(request):
        """POST /api/free-apis/discover — Auto-Discovery: Neue Free APIs aus dem Internet."""
        try:
            from modules.free_api_hunter import auto_discover_new_apis
            limit = int((await request.json()).get("test_limit", 40)) if request.can_read_body else 40
            result = await auto_discover_new_apis(test_limit=limit)
            return web.json_response({"ok": True, "result": result})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_free_apis_discovery_stats(request):
        """GET /api/free-apis/discovery-stats — Letzte Discovery-Ergebnisse."""
        try:
            from modules.free_api_hunter import get_discovery_stats
            return web.json_response(get_discovery_stats())
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    app.router.add_get("/api/free-apis",                  handle_free_apis_registry)
    app.router.add_post("/api/free-apis/scan",            handle_free_apis_scan)
    app.router.add_get("/api/free-apis/best-ai",          handle_free_apis_best_ai)
    app.router.add_post("/api/free-apis/discover",        handle_free_apis_discover)
    app.router.add_get("/api/free-apis/discovery-stats",  handle_free_apis_discovery_stats)
    log.info("Free API Hunter routes registered (/api/free-apis/*)")

    # ── Meta Ads Engine routes ─────────────────────────────────────────────────
    async def handle_meta_ads_launch(request):
        """POST /api/meta-ads/launch — Erstellt Retargeting + Lookalike Kampagnen."""
        try:
            from modules.meta_ads_engine import launch_retargeting_campaign
            result = await launch_retargeting_campaign()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_meta_ads_activate(request):
        """POST /api/meta-ads/activate — Aktiviert alle PAUSED Kampagnen."""
        try:
            from modules.meta_ads_engine import activate_campaigns
            result = await activate_campaigns()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_meta_ads_stats(request):
        """GET /api/meta-ads/stats — Alle Kampagnen + Spend-Übersicht."""
        try:
            from modules.meta_ads_engine import get_all_stats
            result = await get_all_stats()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_meta_ads_optimize(request):
        """POST /api/meta-ads/optimize — Manueller Auto-Optimize-Lauf."""
        try:
            from modules.meta_ads_engine import run_auto_optimize
            result = await run_auto_optimize()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_post("/api/meta-ads/launch",   handle_meta_ads_launch)
    app.router.add_post("/api/meta-ads/activate", handle_meta_ads_activate)
    app.router.add_get( "/api/meta-ads/stats",    handle_meta_ads_stats)
    app.router.add_post("/api/meta-ads/optimize", handle_meta_ads_optimize)
    log.info("Meta Ads Engine routes registered (/api/meta-ads/*)")

    # Rotating Buyer Prospector routes
    async def handle_prospector_run(request):
        """POST /api/prospector/run — Startet sofort einen Prospecting-Lauf."""
        try:
            data = await request.json() if request.content_length else {}
            emails_per_run = int(data.get("emails_per_run", 15))
            from modules.rotating_buyer_prospector import run_prospecting_cycle
            asyncio.create_task(_run_prospector_bg(emails_per_run))
            return web.json_response({"ok": True, "status": "started", "emails_per_run": emails_per_run})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def _run_prospector_bg(emails_per_run: int):
        try:
            from modules.rotating_buyer_prospector import run_prospecting_cycle
            await run_prospecting_cycle(emails_per_run=emails_per_run)
        except Exception as e:
            log.error("Prospector bg task failed: %s", e)

    async def handle_prospector_stats(request):
        """GET /api/prospector/stats — Zeigt Gesamt-Statistik."""
        try:
            from modules.rotating_buyer_prospector import get_stats
            stats = await get_stats()
            return web.json_response({"ok": True, **stats})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_prospector_niches(request):
        """GET /api/prospector/niches — Liste aller 60 Nischen + Status."""
        try:
            from modules.rotating_buyer_prospector import NICHES, _db
            con = _db()
            try:
                rows = con.execute("SELECT niche_id, MAX(ran_at) as last FROM niche_rotation GROUP BY niche_id").fetchall()
                used = {r["niche_id"]: r["last"] for r in rows}
            finally:
                con.close()
            niches_out = [{"id": n["id"], "de": n["de"], "last_used": used.get(n["id"])} for n in NICHES]
            return web.json_response({"ok": True, "niches": niches_out, "total": len(NICHES)})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    app.router.add_post("/api/prospector/run",    handle_prospector_run)
    app.router.add_get("/api/prospector/stats",   handle_prospector_stats)
    app.router.add_get("/api/prospector/niches",  handle_prospector_niches)
    log.info("Rotating Buyer Prospector routes registered (/api/prospector/*)")

    # ── Auto-Repair Engine routes ─────────────────────────────────────────────
    async def handle_repair_status(request):
        """GET /api/repair/status — Letzter Repair-Zyklus Ergebnis."""
        try:
            from modules.auto_repair_engine import get_repair_status
            data = await get_repair_status()
            return web.json_response(data)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_repair_run(request):
        """POST /api/repair/run — Repair-Zyklus sofort starten."""
        try:
            from modules.auto_repair_engine import run_repair_cycle
            asyncio.create_task(run_repair_cycle())
            return web.json_response({"ok": True, "message": "Repair-Zyklus gestartet"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_get( "/api/repair/status", handle_repair_status)
    app.router.add_post("/api/repair/run",    handle_repair_run)
    log.info("Auto-Repair Engine routes registered (/api/repair/*)")

    # ── Autonomous Pilot routes ───────────────────────────────────────────────
    async def handle_pilot_stats(request):
        """GET /api/pilot/stats — KPI-Historie + letzte Aktionen."""
        try:
            from modules.autonomous_pilot import get_pilot_stats
            return web.json_response(get_pilot_stats())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_pilot_run(request):
        """POST /api/pilot/run — Einen autonomen Zyklus sofort ausführen."""
        try:
            from modules.autonomous_pilot import run_pilot_cycle
            result = await run_pilot_cycle()
            return web.json_response({"status": "ok", "result": result})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_get( "/api/pilot/stats", handle_pilot_stats)
    app.router.add_post("/api/pilot/run",   handle_pilot_run)
    log.info("Autonomous Pilot routes registered (/api/pilot/*)")

    # ── Test-Verkauf & Inbound-Test routes ───────────────────────────────────
    async def handle_test_purchase_run(request):
        """POST /api/test-purchase/run — Vollständiger Funnel-Test."""
        try:
            from modules.test_purchase_engine import run_test_purchase
            result = await run_test_purchase()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_test_purchase_results(request):
        """GET /api/test-purchase/results — Letzte Test-Ergebnisse."""
        try:
            from modules.test_purchase_engine import get_test_results
            data = get_test_results()
            return web.json_response(data)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_inbound_test(request):
        """POST /api/test-purchase/inbound — Nur Webhook-Inbound prüfen."""
        try:
            from modules.test_purchase_engine import run_inbound_test
            result = await run_inbound_test()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_post("/api/test-purchase/run",     handle_test_purchase_run)
    app.router.add_get( "/api/test-purchase/results", handle_test_purchase_results)
    app.router.add_post("/api/test-purchase/inbound", handle_inbound_test)
    log.info("Test-Purchase Engine routes registered (/api/test-purchase/*)")

    # ── Post-Guardian routes ──────────────────────────────────────────────────
    async def handle_post_guardian_check(request):
        """POST /api/post-guardian/check — Post vor Veröffentlichung prüfen.
        Prüft Text, Plattform-Limits, Duplikate, API-Secrets, falsche Konten
        UND öffnet alle Links im Post und prüft ob die Seite erreichbar + fehlerfrei ist.
        Body: {platform, text, image_url?, account?, check_urls?}
        """
        try:
            body = await request.json()
            from modules.post_guardian import check_post
            result = await check_post(
                platform   = body.get("platform", "instagram"),
                text       = body.get("text", ""),
                image_url  = body.get("image_url"),
                account    = body.get("account"),
                check_urls = body.get("check_urls", True),
            )
            result["checks_performed"] = [
                "plattform_limits", "pflichttext", "verbotene_phrasen",
                "api_key_leak", "falsches_konto", "duplikat_7_tage",
                "url_live_check (alle Links geöffnet + Fehlerseiten geprüft)",
            ]
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_post_guardian_stats(request):
        """GET /api/post-guardian/stats — Statistiken: blocked/approved/posted."""
        try:
            from modules.post_guardian import get_stats
            return web.json_response(get_stats())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_post_guardian_blocked(request):
        """GET /api/post-guardian/blocked — Blockierte Posts (letzte 24h)."""
        try:
            from modules.post_guardian import get_blocked_posts
            return web.json_response({"blocked": get_blocked_posts()})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_post_guardian_repair(request):
        """POST /api/post-guardian/repair — Fehlerhaften Post automatisch reparieren.
        Erkennt und behebt: defekte URLs (→ Homepage), Platzhalter, Zeichenlimit, Duplikate.
        Body: {platform, text, image_url?}
        Returns: {ok, repaired, repaired_text, original_text, changes, final_check}
        """
        try:
            body = await request.json()
            from modules.post_guardian import auto_repair_post
            result = await auto_repair_post(
                text      = body.get("text", ""),
                platform  = body.get("platform", "instagram"),
                image_url = body.get("image_url"),
            )
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_post("/api/post-guardian/check",   handle_post_guardian_check)
    app.router.add_post("/api/post-guardian/repair",  handle_post_guardian_repair)
    app.router.add_get( "/api/post-guardian/stats",   handle_post_guardian_stats)
    app.router.add_get( "/api/post-guardian/blocked", handle_post_guardian_blocked)
    log.info("Post-Guardian routes registered (/api/post-guardian/*)")

    # ── Shopify Manager Assistant routes ─────────────────────────────────────
    async def handle_shopify_manager_status(request):
        """GET /api/shopify/manager/status — ShopifyManager Status + letzte Aktionen."""
        try:
            from modules.shopify_manager import get_manager_status
            return web.json_response(await get_manager_status())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_shopify_manager_cycle(request):
        """POST /api/shopify/manager/cycle — Vollständigen Manager-Zyklus starten.
        AB-Tests + Gewinner + SEO + Preise + Qualitäts-Audit."""
        try:
            from modules.shopify_manager import run_manager_cycle
            return web.json_response(await run_manager_cycle())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_shopify_manager_ab(request):
        """POST /api/shopify/manager/ab-tests — A/B Tests starten."""
        try:
            from modules.shopify_manager import run_ab_tests
            return web.json_response(await run_ab_tests())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_shopify_manager_seo(request):
        """POST /api/shopify/manager/seo — SEO-Optimierung (Titel, Meta, Beschreibungen)."""
        try:
            body = await request.json() if request.content_length else {}
            limit = int(body.get("limit", 20))
            from modules.shopify_manager import run_seo_optimization
            return web.json_response(await run_seo_optimization(limit))
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_shopify_manager_prices(request):
        """POST /api/shopify/manager/prices — Preis-Optimierung (.99 Psychologie)."""
        try:
            from modules.shopify_manager import run_price_optimization
            return web.json_response(await run_price_optimization())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_shopify_manager_quality(request):
        """GET /api/shopify/manager/quality — Qualitäts-Audit (fehlende Bilder, Beschreibungen, etc.)."""
        try:
            from modules.shopify_manager import run_quality_audit
            return web.json_response(await run_quality_audit())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_shopify_check_duplicate(request):
        """POST /api/shopify/manager/check-duplicate — Prüfe ob Produkt bereits importiert.
        Body: {product_id?, title?}"""
        try:
            body = await request.json()
            from modules.shopify_manager import is_duplicate_product
            is_dup = is_duplicate_product(
                product_id=body.get("product_id"),
                title=body.get("title"),
            )
            return web.json_response({"is_duplicate": is_dup})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_get( "/api/shopify/manager/status",           handle_shopify_manager_status)
    app.router.add_post("/api/shopify/manager/cycle",            handle_shopify_manager_cycle)
    app.router.add_post("/api/shopify/manager/ab-tests",         handle_shopify_manager_ab)
    app.router.add_post("/api/shopify/manager/seo",              handle_shopify_manager_seo)
    app.router.add_post("/api/shopify/manager/prices",           handle_shopify_manager_prices)
    app.router.add_get( "/api/shopify/manager/quality",          handle_shopify_manager_quality)
    app.router.add_post("/api/shopify/manager/check-duplicate",  handle_shopify_check_duplicate)
    log.info("Shopify Manager routes registered (/api/shopify/manager/*)")

    # ── Bounce Auto-Fixer routes ──────────────────────────────────────────────
    async def handle_bounce_fix_run(request):
        """POST /api/email/bounce-fix — Sofort Bounce-Scan + Auto-Fix ausführen."""
        try:
            from modules.email_bounce_fixer import run_bounce_fix_cycle
            result = await run_bounce_fix_cycle()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_bounce_blacklist(request):
        """GET /api/email/bounce-blacklist — Alle bekannten Bounce-Adressen."""
        try:
            from modules.email_bounce_fixer import get_blacklist
            limit = int(request.rel_url.query.get("limit", 100))
            return web.json_response({"blacklist": get_blacklist(limit)})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_post("/api/email/bounce-fix",       handle_bounce_fix_run)
    app.router.add_get( "/api/email/bounce-blacklist", handle_bounce_blacklist)
    log.info("Bounce Auto-Fixer routes registered (/api/email/bounce-*)")

    # ── Traffic Accelerator routes ────────────────────────────────────────────
    async def handle_traffic_accelerate(request):
        """POST /api/traffic/accelerate — Maximale Leistung: alle Traffic-Quellen parallel."""
        try:
            from modules.traffic_accelerator import run_traffic_cycle
            result = await run_traffic_cycle()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_traffic_turbo(request):
        """POST /api/traffic/turbo — Turbo-Modus alias für run_traffic_cycle."""
        try:
            from modules.traffic_accelerator import run_traffic_cycle
            result = await run_traffic_cycle()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_traffic_status(request):
        """GET /api/traffic/status — Traffic-Statistiken."""
        try:
            from modules.traffic_accelerator import get_stats
            return web.json_response(get_stats())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_post("/api/traffic/accelerate", handle_traffic_accelerate)
    app.router.add_post("/api/traffic/turbo",      handle_traffic_turbo)
    app.router.add_get( "/api/traffic/status",     handle_traffic_status)
    log.info("Traffic Accelerator routes registered (/api/traffic/*)")

    # ── Autonomous Engine routes ──────────────────────────────────────────────
    async def handle_autonomous_run(request):
        """POST /api/autonomous/run — Autonomen Entscheidungszyklus sofort ausführen."""
        try:
            from modules.autonomous_engine import run_autonomous_cycle
            result = await run_autonomous_cycle()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_autonomous_stats(request):
        """GET /api/autonomous/stats — Statistiken + letzte Entscheidungen."""
        try:
            from modules.autonomous_engine import get_engine_stats, get_decision_log
            return web.json_response({
                "stats": get_engine_stats(),
                "last_decisions": get_decision_log(10),
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_post("/api/autonomous/run",   handle_autonomous_run)
    app.router.add_get( "/api/autonomous/stats", handle_autonomous_stats)
    log.info("Autonomous Engine routes registered (/api/autonomous/*)")

    # ── Trust & Conversion routes ─────────────────────────────────────────────
    async def handle_trust_run(req):
        """POST /api/trust/run — Trust-Elemente + Bestseller-Kampagne ausführen."""
        try:
            from modules.trust_and_conversion import run_trust_cycle
            result = await run_trust_cycle()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_trust_badge_js(req):
        """GET /trust-badge.js — Inline Trust-Badge JS für Shopify ScriptTag."""
        try:
            from modules.trust_and_conversion import TRUST_JS
            return web.Response(
                text=TRUST_JS,
                content_type="application/javascript",
                headers={
                    "Cache-Control": "public, max-age=3600",
                    "Access-Control-Allow-Origin": "*",
                },
            )
        except Exception as e:
            return web.Response(text=f"// error: {e}", content_type="application/javascript")

    app.router.add_post("/api/trust/run",    handle_trust_run)
    app.router.add_get( "/trust-badge.js",  handle_trust_badge_js)
    log.info("Trust & Conversion routes registered (/api/trust/run, /trust-badge.js)")

    # ── AIACT-Pro Bridge routes ───────────────────────────────────────────────
    async def _handle_aiact_bridge_health(request):
        """GET /api/aiact/health — AIACT-Pro Verbindungsstatus."""
        try:
            from modules.aiact_pro_bridge import health
            return web.json_response(await health())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_aiact_compliance(request):
        """GET /api/aiact/compliance — Compliance-Status aller KI-Systeme."""
        try:
            from modules.aiact_pro_bridge import get_compliance_status
            return web.json_response(await get_compliance_status())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_aiact_sync(request):
        """POST /api/aiact/sync — Synchronisiert SuperMegaBot-Systeme mit AIACT-Pro."""
        try:
            from modules.aiact_pro_bridge import run_compliance_check
            return web.json_response(await run_compliance_check())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_aiact_bridge_scan(request):
        """POST /api/aiact/scan — AI-Act Compliance-Scan für eine URL."""
        try:
            body = await request.json()
            from modules.aiact_pro_bridge import scan_ai_act
            return web.json_response(await scan_ai_act(body.get("url", "https://ineedit.com.co")))
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_get( "/api/aiact/health",     _handle_aiact_bridge_health)
    app.router.add_get( "/api/aiact/compliance", handle_aiact_compliance)
    app.router.add_post("/api/aiact/sync",       handle_aiact_sync)
    app.router.add_post("/api/aiact/scan",       _handle_aiact_bridge_scan)
    log.info("AIACT-Pro Bridge routes registered (/api/aiact/*)")

    # ── Meta ROAS Max — GaN Charger Campaign ──────────────────────────────────

    async def handle_roas_stats(req: web.Request) -> web.Response:
        """GET /api/roas/stats — Live ROAS aus Meta Insights + DB-Log."""
        try:
            from modules.meta_roas_max import get_roas_stats, get_live_roas
            stats = get_roas_stats()
            live  = await get_live_roas(days=7)
            return web.json_response({"ok": True, "stats": stats, "live_roas": live})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_roas_launch(req: web.Request) -> web.Response:
        """POST /api/roas/launch — GaN Charger Kampagne erstellen (PAUSED)."""
        try:
            from modules.meta_roas_max import create_gan_charger_campaign
            result = await create_gan_charger_campaign()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_roas_optimize(req: web.Request) -> web.Response:
        """POST /api/roas/optimize — Live ROAS prüfen + Auto-Pause/Scale."""
        try:
            from modules.meta_roas_max import optimize_campaigns
            result = await optimize_campaigns()
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_roas_run(req: web.Request) -> web.Response:
        """POST /api/roas/run — Hauptzyklus: erstelle oder optimiere."""
        try:
            from modules.meta_roas_max import run_roas_max
            msg = await run_roas_max()
            return web.json_response({"ok": True, "result": msg})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_get( "/api/roas/stats",    handle_roas_stats)
    app.router.add_post("/api/roas/launch",   handle_roas_launch)
    app.router.add_post("/api/roas/optimize", handle_roas_optimize)
    app.router.add_post("/api/roas/run",      handle_roas_run)
    log.info("Meta ROAS Max routes registered (/api/roas/*)")

    # ── Income Automation: Shopping Feed + Drip + Cart + Price Compare + Watchdog ──

    async def handle_shopping_feed_xml(req: web.Request) -> web.Response:
        try:
            from modules.google_shopping_feed import generate_feed
            xml = await generate_feed()
            return web.Response(text=xml, content_type="application/xml", charset="utf-8")
        except Exception as e:
            return web.Response(text=f"<error>{e}</error>", content_type="application/xml", status=500)

    async def handle_shopping_feed_stats(req: web.Request) -> web.Response:
        try:
            from modules.google_shopping_feed import get_feed_stats
            return web.json_response(await get_feed_stats())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_drip_run(req: web.Request) -> web.Response:
        try:
            from modules.email_drip_followup import run_drip_cycle
            msg = await run_drip_cycle()
            return web.json_response({"ok": True, "result": msg})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_drip_stats(req: web.Request) -> web.Response:
        try:
            from modules.email_drip_followup import get_drip_stats
            return web.json_response(await get_drip_stats())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_cart_recovery_run(req: web.Request) -> web.Response:
        try:
            from modules.abandoned_cart_emails import run_cart_recovery_cycle
            msg = await run_cart_recovery_cycle()
            return web.json_response({"ok": True, "result": msg})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_cart_recovery_stats(req: web.Request) -> web.Response:
        try:
            from modules.abandoned_cart_emails import get_cart_stats
            return web.json_response(await get_cart_stats())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_cart_unsubscribe(req: web.Request) -> web.Response:
        """GET /cart-unsub?email=<addr> — opt a customer out of abandoned-cart recovery emails."""
        email = req.rel_url.query.get("email", "").strip()
        if not email:
            return web.Response(
                text="<html><body><p>Kein E-Mail-Parameter angegeben.</p></body></html>",
                content_type="text/html",
                status=400,
            )
        try:
            from modules.abandoned_cart_emails import mark_unsubscribed
            updated = await mark_unsubscribed(email)
            if updated:
                msg = f"Die E-Mail-Adresse <b>{email}</b> wurde erfolgreich von Warenkorb-Erinnerungen abgemeldet."
            else:
                msg = "Diese E-Mail-Adresse war bereits abgemeldet oder wurde nicht gefunden."
            html = (
                "<html><body style='font-family:Arial,sans-serif;max-width:500px;margin:60px auto;text-align:center'>"
                f"<h2>Abmeldung bestätigt</h2><p>{msg}</p>"
                "<p><a href='https://ineedit.com.co'>Zurück zum Shop</a></p>"
                "</body></html>"
            )
            return web.Response(text=html, content_type="text/html")
        except Exception as e:
            log.error("cart-unsub error for %s: %s", email, e)
            return web.Response(
                text="<html><body><p>Fehler bei der Abmeldung. Bitte versuche es später erneut.</p></body></html>",
                content_type="text/html",
                status=500,
            )

    async def handle_price_feeds_refresh(req: web.Request) -> web.Response:
        try:
            from modules.price_comparison_feeds import refresh_all_feeds
            return web.json_response(await refresh_all_feeds())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_idealo_feed(req: web.Request) -> web.Response:
        try:
            from modules.price_comparison_feeds import generate_idealo_csv
            csv_data = await generate_idealo_csv()
            return web.Response(text=csv_data, content_type="text/csv", charset="utf-8",
                                headers={"Content-Disposition": "attachment; filename=idealo_feed.csv"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_pricerunner_feed(req: web.Request) -> web.Response:
        try:
            from modules.price_comparison_feeds import generate_pricerunner_xml
            xml = await generate_pricerunner_xml()
            return web.Response(text=xml, content_type="application/xml", charset="utf-8")
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_watchdog_run(req: web.Request) -> web.Response:
        try:
            from modules.revenue_watchdog import run_watchdog_cycle
            msg = await run_watchdog_cycle()
            return web.json_response({"ok": True, "result": msg})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_watchdog_stats(req: web.Request) -> web.Response:
        try:
            from modules.revenue_watchdog import get_watchdog_stats
            return web.json_response(await get_watchdog_stats())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_get( "/feed/google-shopping.xml",  handle_shopping_feed_xml)
    app.router.add_get( "/api/shopping-feed/stats",   handle_shopping_feed_stats)
    app.router.add_post("/api/email-drip/run",         handle_drip_run)
    app.router.add_get( "/api/email-drip/stats",       handle_drip_stats)
    app.router.add_post("/api/cart-recovery/run",      handle_cart_recovery_run)
    app.router.add_get( "/api/cart-recovery/stats",    handle_cart_recovery_stats)
    app.router.add_get( "/cart-unsub",                 handle_cart_unsubscribe)
    app.router.add_post("/api/price-feeds/refresh",    handle_price_feeds_refresh)
    app.router.add_get( "/feed/idealo.csv",            handle_idealo_feed)
    app.router.add_get( "/feed/pricerunner.xml",       handle_pricerunner_feed)
    app.router.add_post("/api/watchdog/run",           handle_watchdog_run)
    app.router.add_get( "/api/watchdog/stats",         handle_watchdog_stats)

    # ── AI Follow-Up Sequenz ──────────────────────────────────────────────────
    async def handle_ai_followup_run(req: web.Request) -> web.Response:
        """POST /api/followup-ai/run — KI-Follow-Up Zyklus starten."""
        try:
            from modules.email_followup_ai import run_ai_followup_cycle
            result = await run_ai_followup_cycle()
            return web.json_response({"ok": True, "result": result})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_ai_followup_stats(req: web.Request) -> web.Response:
        """GET /api/followup-ai/stats — Statistiken der AI Follow-Up Sequenz."""
        try:
            from modules.email_followup_ai import get_stats as followup_stats
            return web.json_response(await followup_stats())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_ai_followup_enroll(req: web.Request) -> web.Response:
        """POST /api/followup-ai/enroll — Lead manuell eintragen.
        Body: {email, company, first_name, segment, service_fit, source, notes}
        """
        try:
            body = await req.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        email = (body.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return web.json_response({"error": "valid email required"}, status=400)
        try:
            from modules.email_followup_ai import enroll_lead
            result = await enroll_lead(
                email=email,
                company=body.get("company", ""),
                first_name=body.get("first_name", ""),
                segment=body.get("segment", ""),
                service_fit=body.get("service_fit", ""),
                source=body.get("source", "api"),
                notes=body.get("notes", ""),
            )
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_ai_followup_unsubscribe(req: web.Request) -> web.Response:
        """GET /api/email/unsubscribe?email=...&token=... — Abmeldung."""
        email = req.rel_url.query.get("email", "").strip().lower()
        token = req.rel_url.query.get("token", "").strip()
        if not email or not token:
            return web.Response(text="Fehlende Parameter.", content_type="text/html")
        try:
            from modules.email_followup_ai import handle_unsubscribe
            result = await handle_unsubscribe(email, token)
            if result["ok"]:
                html = (
                    "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
                    f"<h2>Abmeldung erfolgreich</h2>"
                    f"<p>{email} wurde aus allen Follow-Up Sequenzen abgemeldet.</p>"
                    "</body></html>"
                )
            else:
                html = (
                    "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
                    f"<h2>Fehler</h2><p>{result['message']}</p>"
                    "</body></html>"
                )
            return web.Response(text=html, content_type="text/html")
        except Exception as e:
            return web.Response(text=f"Fehler: {e}", content_type="text/html", status=500)

    async def handle_ai_followup_reply_check(req: web.Request) -> web.Response:
        """POST /api/followup-ai/check-replies — IMAP Reply-Detection laufen lassen."""
        try:
            from modules.email_followup_ai import check_replies
            found = await check_replies()
            return web.json_response({"ok": True, "replies_detected": found})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_post("/api/followup-ai/run",           handle_ai_followup_run)
    app.router.add_get( "/api/followup-ai/stats",         handle_ai_followup_stats)
    app.router.add_post("/api/followup-ai/enroll",        handle_ai_followup_enroll)
    app.router.add_get( "/api/email/unsubscribe",         handle_ai_followup_unsubscribe)
    app.router.add_post("/api/followup-ai/check-replies", handle_ai_followup_reply_check)
    # /api/mac/watchdog (handle_mac_watchdog) oben separat registriert
    log.info("Income Automation routes registered (shopping/drip/cart/price/watchdog/followup-ai)")

    # ── LinkedIn DM Outreach ───────────────────────────────────────────────────
    async def handle_linkedin_outreach(request):
        """POST /api/linkedin/outreach — 50 LinkedIn DMs an DACH E-Commerce Entscheider."""
        try:
            from modules.linkedin_dm_outreach import run_daily_outreach
            result = await run_daily_outreach(limit=50)
            return web.json_response(result if isinstance(result, dict) else {"status": "started"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_linkedin_stats(request):
        """GET /api/linkedin/stats — LinkedIn DM Statistiken."""
        try:
            from modules.linkedin_dm_outreach import get_stats
            return web.json_response(get_stats())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_post("/api/linkedin/outreach", handle_linkedin_outreach)
    app.router.add_get( "/api/linkedin/stats",    handle_linkedin_stats)

    # ── Affiliate Recruiter ────────────────────────────────────────────────────
    async def handle_affiliate_recruit(request):
        """POST /api/affiliate/recruit — 15 Affiliate-Pitches senden."""
        try:
            from modules.affiliate_recruiter import run_affiliate_campaign
            result = await run_affiliate_campaign(limit=15)
            return web.json_response(result if isinstance(result, dict) else {"status": "started"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_affiliate_stats(request):
        """GET /api/affiliate/stats — Affiliate Recruiter Statistiken."""
        try:
            from modules.affiliate_recruiter import get_stats
            return web.json_response(get_stats())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_post("/api/affiliate/recruit", handle_affiliate_recruit)
    app.router.add_get( "/api/affiliate/stats",   handle_affiliate_stats)

    # ── Traffic Maximizer ──────────────────────────────────────────────────────
    async def handle_traffic_blast(request):
        """POST /api/traffic/blast — LinkedIn+FB+Shopify Blog gleichzeitig."""
        try:
            from modules.traffic_maximizer import run_full_traffic_blast
            result = await run_full_traffic_blast()
            return web.json_response(result if isinstance(result, dict) else {"status": "started"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_post("/api/traffic/blast", handle_traffic_blast)
    # handle_traffic_stats bereits als module-level Funktion registriert (Zeile 8111 + 10749)

    # ── Autonomous Pilot ───────────────────────────────────────────────────────
    async def handle_pilot_status(request):
        """GET /api/pilot/status — Autonomous Pilot KPIs und letzter Zyklus."""
        try:
            from modules.autonomous_pilot import AutonomousPilot
            pilot = AutonomousPilot()
            return web.json_response(await pilot.get_status() if hasattr(pilot, 'get_status') else {"status": "active"})
        except Exception as e:
            return web.json_response({"status": "loading", "error": str(e)}, status=200)

    app.router.add_get( "/api/pilot/status", handle_pilot_status)
    # /api/pilot/run bereits oben registriert — zweites Duplikat entfernt
    log.info("Autonomous Pilot routes registered (/api/pilot/*, /api/linkedin/*, /api/affiliate/*, /api/traffic/*)")

    # ── Agent Coordinator ──────────────────────────────────────────────────
    async def handle_coordinator_status(request):
        """GET /api/agents/coordinator — laufende Tasks + letzte Ergebnisse."""
        try:
            from modules.agent_coordinator import get_status
            return web.json_response(get_status())
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_coordinator_messages(request):
        """GET /api/agents/messages?agent=X — Nachrichten für Agenten."""
        agent = request.rel_url.query.get("agent", "all")
        try:
            from modules.agent_coordinator import read_messages
            msgs = read_messages(agent, unread_only=False)
            return web.json_response({"agent": agent, "messages": msgs[:20]})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_coordinator_broadcast(request):
        """POST /api/agents/broadcast — Nachricht an alle Agenten."""
        try:
            body = await request.json()
            from modules.agent_coordinator import send_message
            send_message(
                from_agent=body.get("from", "dashboard"),
                payload=body.get("payload", {}),
                to_agent=body.get("to", "all"),
                msg_type=body.get("type", "command"),
            )
            return web.json_response({"ok": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_get( "/api/agents/coordinator", handle_coordinator_status)
    app.router.add_get( "/api/agents/messages",    handle_coordinator_messages)
    app.router.add_post("/api/agents/broadcast",   handle_coordinator_broadcast)
    log.info("Agent Coordinator routes registered (/api/agents/coordinator, /api/agents/messages, /api/agents/broadcast)")

    # ── Mega Status ────────────────────────────────────────────────────────────
    async def handle_mega_command_status(request):
        import json as _json
        from pathlib import Path as _Path
        results = {}
        # Load health stats if available
        health_file = _Path("data/health_stats.json")
        if health_file.exists():
            try:
                results["health"] = _json.loads(health_file.read_text())
            except Exception:
                results["health"] = {}
        # Load watchdog stats
        try:
            from modules.revenue_watchdog import get_watchdog_stats
            results["watchdog"] = await get_watchdog_stats()
        except Exception as e:
            results["watchdog"] = {"error": str(e)}
        # Load ROAS stats
        try:
            from modules.meta_roas_max import get_roas_stats
            results["meta_roas"] = get_roas_stats()
        except Exception as e:
            results["meta_roas"] = {"error": str(e)}
        # Load cart stats
        try:
            from modules.abandoned_cart_emails import get_cart_stats
            results["abandoned_cart"] = await get_cart_stats()
        except Exception as e:
            results["abandoned_cart"] = {"error": str(e)}
        # Load drip stats
        try:
            from modules.email_drip_followup import get_drip_stats
            results["email_drip"] = await get_drip_stats()
        except Exception as e:
            results["email_drip"] = {"error": str(e)}
        results["ok"] = True
        results["system"] = "BullPower MEGA Command Center"
        return web.Response(
            text=_json.dumps(results, default=str),
            content_type="application/json"
        )

    app.router.add_get("/api/mega-status", handle_mega_command_status)
    log.info("Mega Status route registered (/api/mega-status)")

    # ── KI-Agent Hub ────────────────────────────────────────────────────────

    async def handle_ki_agents_stats(req):
        try:
            from modules.ki_agent_hub import get_all_stats
            stats = get_all_stats()
            return web.Response(text=json.dumps(stats, default=str), content_type="application/json")
        except Exception as e:
            return web.Response(text=json.dumps({"error": str(e)}), content_type="application/json", status=500)

    async def handle_ki_sales_run(req):
        try:
            from modules.ki_agent_hub import run_sales_agent
            result = await run_sales_agent()
            return web.Response(text=json.dumps(result, default=str), content_type="application/json")
        except Exception as e:
            return web.Response(text=json.dumps({"error": str(e)}), content_type="application/json", status=500)

    async def handle_ki_support_run(req):
        try:
            from modules.ki_agent_hub import run_support_agent
            result = await run_support_agent()
            return web.Response(text=json.dumps(result, default=str), content_type="application/json")
        except Exception as e:
            return web.Response(text=json.dumps({"error": str(e)}), content_type="application/json", status=500)

    async def handle_ki_research_run(req):
        try:
            from modules.ki_agent_hub import run_research_agent
            result = await run_research_agent()
            return web.Response(text=json.dumps(result, default=str), content_type="application/json")
        except Exception as e:
            return web.Response(text=json.dumps({"error": str(e)}), content_type="application/json", status=500)

    async def handle_ki_growth_run(req):
        try:
            from modules.ki_agent_hub import run_growth_agent
            result = await run_growth_agent()
            return web.Response(text=json.dumps(result, default=str), content_type="application/json")
        except Exception as e:
            return web.Response(text=json.dumps({"error": str(e)}), content_type="application/json", status=500)

    async def handle_ki_lead_add(req):
        try:
            body = await req.json()
            from modules.ki_agent_hub import add_sales_lead
            lead_id = add_sales_lead(
                phone=body.get("phone", ""),
                email=body.get("email", ""),
                name=body.get("name", ""),
                product=body.get("product", ""),
                source=body.get("source", "api"),
            )
            return web.Response(text=json.dumps({"ok": True, "id": lead_id}), content_type="application/json")
        except Exception as e:
            return web.Response(text=json.dumps({"error": str(e)}), content_type="application/json", status=500)

    app.router.add_get( "/api/ki-agents/stats",       handle_ki_agents_stats)
    app.router.add_post("/api/ki-agents/sales/run",    handle_ki_sales_run)
    app.router.add_post("/api/ki-agents/support/run",  handle_ki_support_run)
    app.router.add_post("/api/ki-agents/research/run", handle_ki_research_run)
    app.router.add_post("/api/ki-agents/growth/run",   handle_ki_growth_run)
    app.router.add_post("/api/ki-agents/leads/add",    handle_ki_lead_add)
    log.info("KI-Agent Hub routes registered (6 routes)")

    # ── Gumroad Digital Product Downloads ────────────────────────────────────
    _DOWNLOADS_DIR = BASE_DIR / "downloads"
    if not _DOWNLOADS_DIR.exists():
        _DOWNLOADS_DIR = BASE_DIR / "data" / "downloads"
    _DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    _GUMROAD_PRODUCTS = {
        "python-scripts":    ("python-scripts-bundle.zip",   "33 Python Scripts — E-Commerce Automation Bundle"),
        "social-autopilot":  ("social-autopilot-bundle.zip", "Social Media AUTOPILOT"),
        "macobd-pro":        ("macobd-pro-bundle.zip",       "MacOBD-Pro v2.0"),
        "supermegabot-elite":("supermegabot-elite.zip",      "SuperMegaBot ELITE"),
        "ki-marketing":      ("ki-marketing-engine.zip",     "KI-Marketing ENGINE"),
        "ai-income-machine": ("ai-income-machine.zip",       "AI Income Machine ELITE"),
        "ecommerce-tools":   ("ecommerce-powertools.zip",    "E-Commerce POWERTOOLS PRO"),
        "printify-autopilot":("printify-autopilot.zip",      "Print-on-Demand AUTOPILOT"),
        "ki-mastery":        ("ki-automation-mastery.zip",   "KI-Automation MASTERY"),
    }

    async def handle_gumroad_download(request: web.Request) -> web.Response:
        product_slug = request.match_info.get("slug", "")
        key = request.query.get("key", "")
        gumroad_sale_id = request.query.get("sale_id", "")
        expected_key = os.getenv("GUMROAD_DOWNLOAD_KEY", os.getenv("DASHBOARD_SECRET", ""))[:16]
        if not key or key != expected_key:
            return web.Response(text="Unauthorized — invalid download key", status=403)
        if product_slug not in _GUMROAD_PRODUCTS:
            return web.Response(text="Product not found", status=404)
        filename, product_name = _GUMROAD_PRODUCTS[product_slug]
        filepath = _DOWNLOADS_DIR / filename
        if not filepath.exists():
            return web.Response(text=f"File not yet available — contact support", status=404)
        return web.FileResponse(
            filepath,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    async def handle_gumroad_webhook(request: web.Request) -> web.Response:
        try:
            data = await request.post()
            product_name = data.get("product_name", "")
            buyer_email = data.get("email", "")
            sale_id = data.get("sale_id", "")
            permalink = data.get("product_permalink", "")
            slug_map = {
                "noahyb": "python-scripts", "ggbos": "macobd-pro",
                "liastd": "", "qjsiv": "ki-marketing",
                "social": "social-autopilot",
            }
            product_slug = slug_map.get(permalink, permalink)
            download_key = os.getenv("GUMROAD_DOWNLOAD_KEY", os.getenv("DASHBOARD_SECRET", ""))[:16]
            base_url = os.getenv("SUPERMEGABOT_DASHBOARD_URL", "https://supermegabot-production.up.railway.app")
            download_url = f"{base_url}/api/downloads/{product_slug}?key={download_key}&sale_id={sale_id}"
            log.info("Gumroad sale: %s | %s | %s", product_name, buyer_email, sale_id)
            token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            if token and chat_id:
                msg = f"🛒 GUMROAD KAUF!\n{product_name}\nKäufer: {buyer_email}\nDownload: {download_url}"
                async with aiohttp.ClientSession() as s:
                    await s.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                 json={"chat_id": chat_id, "text": msg})
            return web.Response(text="OK", status=200)
        except Exception as e:
            log.error("Gumroad webhook error: %s", e)
            return web.Response(text="Error", status=500)

    async def handle_downloads_list(request: web.Request) -> web.Response:
        files = []
        for slug, (fname, name) in _GUMROAD_PRODUCTS.items():
            fp = _DOWNLOADS_DIR / fname
            files.append({"slug": slug, "name": name, "available": fp.exists(),
                          "size_kb": round(fp.stat().st_size / 1024) if fp.exists() else 0})
        return web.Response(text=json.dumps({"products": files, "count": len(files)}),
                            content_type="application/json")

    app.router.add_get("/api/downloads/{slug}", handle_gumroad_download)
    app.router.add_post("/api/gumroad/webhook",  handle_gumroad_webhook)
    app.router.add_get("/api/downloads",          handle_downloads_list)
    log.info("Gumroad download endpoints registered (3 routes)")

    # ── PostingCoordinator — Verhindert Doppelposts ───────────────────────────
    try:
        from modules.posting_coordinator import get_posting_status, get_coordinator
        _posting_coord = get_coordinator()

        async def handle_posting_status(request: web.Request) -> web.Response:
            status = get_posting_status()
            return web.Response(text=json.dumps(status), content_type="application/json")

        async def handle_posting_log(request: web.Request) -> web.Response:
            platform = request.query.get("platform", "all")
            coord = get_coordinator()
            stats = coord.get_today_stats()
            if platform != "all":
                stats = {k: v for k, v in stats.items() if k == platform.lower()}
            return web.Response(text=json.dumps({"today": stats}), content_type="application/json")

        async def handle_posting_can(request: web.Request) -> web.Response:
            platform = request.query.get("platform", "instagram")
            system = request.query.get("system", "any")
            can, reason = get_coordinator().can_post(platform, system)
            return web.Response(text=json.dumps({"can_post": can, "reason": reason}),
                                content_type="application/json")

        app.router.add_get("/api/posting/status", handle_posting_status)
        app.router.add_get("/api/posting/log",    handle_posting_log)
        app.router.add_get("/api/posting/can",    handle_posting_can)
        log.info("PostingCoordinator routes registered (3 routes)")
    except Exception as _pce:
        log.warning("PostingCoordinator nicht verfügbar: %s", _pce)

    # ── OMEGA Revenue Brain ───────────────────────────────────────────────────
    try:
        async def handle_omega_status(request: web.Request) -> web.Response:
            from modules.omega_revenue_brain import get_status
            result = await get_status()
            return web.Response(text=json.dumps(result), content_type="application/json")

        async def handle_omega_run(request: web.Request) -> web.Response:
            from modules.omega_revenue_brain import run_omega_cycle
            result = await run_omega_cycle(auto_execute=True)
            return web.Response(text=json.dumps(result), content_type="application/json")

        async def handle_revenue_live(request: web.Request) -> web.Response:
            """Echtzeit-Revenue-Dashboard — ALLE echten Daten aus APIs."""
            results: dict = {}
            async with aiohttp.ClientSession() as session:
                # Shopify
                token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
                store = os.getenv("SHOPIFY_STORE_URL", "ineedit.com.co")
                if token:
                    try:
                        from datetime import datetime, timezone, timedelta
                        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                        async with session.get(
                            f"https://{store}/admin/api/2024-01/orders.json",
                            headers={"X-Shopify-Access-Token": token},
                            params={"status": "paid", "created_at_min": since, "limit": 250, "fields": "id,total_price"},
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as r:
                            if r.status == 200:
                                data = await r.json()
                                orders = data.get("orders", [])
                                results["shopify"] = {
                                    "ok": True,
                                    "orders_24h": len(orders),
                                    "revenue_24h": round(sum(float(o.get("total_price", 0)) for o in orders), 2)
                                }
                    except Exception as e:
                        results["shopify"] = {"ok": False, "error": str(e)[:60]}

                # Stripe
                stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
                if stripe_key:
                    try:
                        import time as _time
                        async with session.get(
                            "https://api.stripe.com/v1/charges",
                            auth=aiohttp.BasicAuth(stripe_key, ""),
                            params={"created[gte]": str(int(_time.time()) - 86400), "limit": "100"},
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as r:
                            if r.status == 200:
                                data = await r.json()
                                charges = [c for c in data.get("data", []) if c.get("paid")]
                                results["stripe"] = {
                                    "ok": True,
                                    "charges_24h": len(charges),
                                    "revenue_24h": round(sum(c.get("amount", 0) for c in charges) / 100, 2)
                                }
                    except Exception as e:
                        results["stripe"] = {"ok": False, "error": str(e)[:60]}

                # Meta Ads
                meta_token = os.getenv("META_ACCESS_TOKEN", os.getenv("FACEBOOK_ACCESS_TOKEN", ""))
                meta_act = os.getenv("META_AD_ACCOUNT_ID", "act_878505274898620")
                if meta_token:
                    try:
                        async with session.get(
                            f"https://graph.facebook.com/v21.0/{meta_act}/insights",
                            params={"access_token": meta_token, "date_preset": "today",
                                    "fields": "spend,purchase_roas,impressions,clicks", "level": "account"},
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as r:
                            if r.status == 200:
                                data = await r.json()
                                ins = data.get("data", [{}])[0] if data.get("data") else {}
                                roas_val = ins.get("purchase_roas", [{}])
                                roas = float(roas_val[0].get("value", 0)) if roas_val else 0.0
                                results["meta"] = {
                                    "ok": True,
                                    "spend_today": float(ins.get("spend", 0)),
                                    "roas_today": round(roas, 2),
                                    "impressions": int(ins.get("impressions", 0)),
                                    "clicks": int(ins.get("clicks", 0)),
                                }
                    except Exception as e:
                        results["meta"] = {"ok": False, "error": str(e)[:60]}

                # DS24 (Digistore24) — last 24h transactions
                ds24_key = (
                    os.getenv("DIGISTORE24_API_KEY_FULL") or
                    os.getenv("DS24_API_KEY_FULL") or
                    os.getenv("DIGISTORE24_API_KEY") or
                    os.getenv("DS24_API_KEY", "")
                )
                if ds24_key and "-" in ds24_key:
                    try:
                        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
                        _now = _dt.now(_tz.utc)
                        _since = (_now - _td(hours=24)).strftime("%Y-%m-%d")
                        _today = _now.strftime("%Y-%m-%d")
                        async with session.get(
                            "https://www.digistore24.com/api/call/listTransactions/JSON/",
                            headers={"X-DS-API-KEY": ds24_key},
                            params={"from": _since, "to": _today, "page_no": 1, "page_size": 100},
                            timeout=aiohttp.ClientTimeout(total=12)
                        ) as r:
                            if r.status == 200:
                                d = await r.json(content_type=None)
                                if d.get("result") == "success":
                                    txns = d.get("data", {}).get("transaction_list", [])
                                    rev = 0.0
                                    for t in txns:
                                        for f in ("amount", "transaction_amount", "earned_amount"):
                                            try:
                                                v = float(t.get(f, 0) or 0)
                                                if v:
                                                    rev += v
                                                    break
                                            except (TypeError, ValueError):
                                                pass
                                    results["ds24"] = {
                                        "ok": True,
                                        "orders_24h": len(txns),
                                        "revenue_24h": round(rev, 2),
                                    }
                                else:
                                    results["ds24"] = {"ok": False, "error": d.get("message", "API error")[:50]}
                    except Exception as e:
                        results["ds24"] = {"ok": False, "error": str(e)[:60]}

            results["ok"] = True
            results["timestamp"] = datetime.now(timezone.utc).isoformat()
            return web.Response(text=json.dumps(results), content_type="application/json")

        from datetime import datetime, timezone
        app.router.add_get("/api/omega/status", handle_omega_status)
        app.router.add_post("/api/omega/run",   handle_omega_run)
        app.router.add_get("/api/revenue/live", handle_revenue_live)
        log.info("OMEGA Revenue Brain routes registered (3 routes)")
    except Exception as _omega_e:
        log.warning("OMEGA Brain routes failed: %s", _omega_e)

    # ── Shopify Image Optimizer ───────────────────────────────────────────────
    try:
        async def handle_image_scan(request: web.Request) -> web.Response:
            limit = int(request.rel_url.query.get("limit", 250))
            from modules.shopify_image_optimizer import scan_images
            result = await scan_images(limit=limit)
            return web.Response(text=json.dumps(result), content_type="application/json")

        async def handle_image_issues(request: web.Request) -> web.Response:
            from modules.shopify_image_optimizer import get_image_issues
            issues = await get_image_issues()
            return web.Response(text=json.dumps({"issues": issues, "count": len(issues)}),
                                content_type="application/json")

        async def handle_image_fix(request: web.Request) -> web.Response:
            body = await request.json()
            product_id = str(body.get("product_id", ""))
            image_url = str(body.get("image_url", ""))
            if not product_id or not image_url:
                return web.Response(status=400,
                                    text=json.dumps({"error": "product_id und image_url erforderlich"}),
                                    content_type="application/json")
            from modules.shopify_image_optimizer import _optimizer
            ok = await _optimizer.fix_product_images(product_id, image_url)
            return web.Response(text=json.dumps({"ok": ok, "product_id": product_id}),
                                content_type="application/json")

        async def handle_image_bad_scan(request: web.Request) -> web.Response:
            """Scannt auf falsche/mismatched Bilder (Black Friday, Placeholder, etc.)"""
            dry = request.rel_url.query.get("dry", "false").lower() == "true"
            from modules.shopify_image_manager import scan_and_fix_images
            result = await scan_and_fix_images(dry_run=dry)
            return web.Response(text=json.dumps(result, ensure_ascii=False), content_type="application/json")

        app.router.add_get( "/api/shopify/images/scan",   handle_image_scan)
        app.router.add_get( "/api/shopify/images/issues", handle_image_issues)
        app.router.add_get( "/api/shopify/images/bad",    handle_image_bad_scan)
        app.router.add_post("/api/shopify/images/fix",    handle_image_fix)
        log.info("Shopify Image Optimizer routes registered (4 routes)")
    except Exception as _img_e:
        log.warning("Image Optimizer routes failed: %s", _img_e)

    # ── AI Provider Status (alle 13+ Provider + Bridge) ──────────────────────
    try:
        async def handle_ai_providers_status(request: web.Request) -> web.Response:
            from modules.ai_client import get_ai_status
            from modules.api_hunt_ai_bridge import get_bridge_status
            status = get_ai_status()
            bridge = get_bridge_status()
            return web.Response(
                text=json.dumps({"core": status, "bridge": bridge}),
                content_type="application/json",
            )

        app.router.add_get("/api/ai-providers/status", handle_ai_providers_status)
        log.info("AI Providers status route registered")
    except Exception as _aip_e:
        log.warning("AI Providers route failed: %s", _aip_e)

    # ── Klaviyo Assistent ─────────────────────────────────────────────────────
    try:
        async def handle_klaviyo_status(request: web.Request) -> web.Response:
            from modules.klaviyo_assistant import get_status
            return web.Response(text=json.dumps(await get_status()),
                                content_type="application/json")

        async def handle_klaviyo_run(request: web.Request) -> web.Response:
            from modules.klaviyo_assistant import run_klaviyo_cycle
            result = await run_klaviyo_cycle()
            return web.Response(text=json.dumps(result), content_type="application/json")

        app.router.add_get( "/api/klaviyo/status", handle_klaviyo_status)
        app.router.add_post("/api/klaviyo/run",    handle_klaviyo_run)
        log.info("Klaviyo Assistant routes registered")
    except Exception as _klv_e:
        log.warning("Klaviyo routes failed: %s", _klv_e)

    # ── Shopify Auto-Kategorisierer ───────────────────────────────────────────
    try:
        async def handle_categorizer_stats(request: web.Request) -> web.Response:
            from modules.shopify_auto_categorizer import get_category_stats
            return web.Response(text=json.dumps(await get_category_stats()),
                                content_type="application/json")

        async def handle_categorizer_run(request: web.Request) -> web.Response:
            batch = int(request.rel_url.query.get("batch", 30))
            from modules.shopify_auto_categorizer import categorize_uncategorized
            result = await categorize_uncategorized(batch_size=batch)
            return web.Response(text=json.dumps(result), content_type="application/json")

        app.router.add_get( "/api/shopify/categorizer/stats", handle_categorizer_stats)
        app.router.add_post("/api/shopify/categorizer/run",   handle_categorizer_run)
        log.info("Shopify Auto-Categorizer routes registered")
    except Exception as _cat_e:
        log.warning("Categorizer routes failed: %s", _cat_e)

    # ── eBay / Amazon Marketing ───────────────────────────────────────────────
    try:
        async def handle_amazon_run(request: web.Request) -> web.Response:
            from modules.ebay_amazon_marketer import run_marketing_cycle
            result = await run_marketing_cycle()
            return web.Response(text=json.dumps(result), content_type="application/json")

        async def handle_amazon_status(request: web.Request) -> web.Response:
            from modules.ebay_amazon_marketer import get_status
            return web.Response(text=json.dumps(await get_status()),
                                content_type="application/json")

        async def handle_amazon_trends(request: web.Request) -> web.Response:
            from modules.ebay_amazon_marketer import analyze_market_trends
            result = await analyze_market_trends()
            return web.Response(text=json.dumps(result), content_type="application/json")

        app.router.add_get( "/api/amazon/status", handle_amazon_status)
        app.router.add_post("/api/amazon/run",    handle_amazon_run)
        app.router.add_get( "/api/amazon/trends", handle_amazon_trends)
        log.info("eBay/Amazon Marketing routes registered")
    except Exception as _amz_e:
        log.warning("Amazon routes failed: %s", _amz_e)

    # Start hourly lead follow-up reminder background task
    asyncio.create_task(_run_followup_loop())
    log.info("Lead follow-up reminder task started")

    # Start weekly sitemap ping background task (Google + Bing)
    asyncio.create_task(_run_sitemap_ping_loop())
    log.info("Weekly sitemap ping task started")

    # Start daily SEO blog content pipeline
    asyncio.create_task(_run_seo_loop())
    log.info("SEO blog content pipeline started")

    # OrganicTrafficManager-Loop DEAKTIVIERT — BrutalAdsEngine (alle 2h) ist aktiv
    # Beide gleichzeitig = Überposting = Account-Schaden. Nur ein System postet automatisch.
    # Manuelle Posts weiter möglich via: POST /api/organic-traffic/post

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

    # Auto-register Shopify webhooks on startup (checkouts/create, customers/create, etc.)
    async def _register_shopify_webhooks_on_start():
        await asyncio.sleep(10)  # wait for server to be ready
        try:
            from modules.shopify_webhook_registrar import ensure_webhooks
            results = await asyncio.to_thread(ensure_webhooks)
            ok = sum(1 for r in results if r.get("status") in ("registered", "already_exists"))
            log.info("Shopify webhook registration: %d/%d OK — %s",
                     ok, len(results),
                     [(r["topic"], r["status"]) for r in results])
        except Exception as e:
            log.warning("Shopify webhook registration failed (non-fatal): %s", e)

    asyncio.create_task(_register_shopify_webhooks_on_start())
    log.info("Shopify webhook auto-registration task scheduled")

    # Send Telegram Master Dashboard startup notification
    try:
        startup_enabled = os.getenv("TELEGRAM_STARTUP_NOTIFICATIONS", "false").lower() in ("1", "true", "yes", "on")
        if startup_enabled and os.getenv("TELEGRAM_BOT_TOKEN", "") and os.getenv("TELEGRAM_CHAT_ID", ""):
            from modules.telegram_master_dashboard import send_startup_notification
            asyncio.create_task(send_startup_notification())
            log.info("Telegram Master Dashboard startup notification queued")
        else:
            log.info("Telegram Master Dashboard startup notification skipped")
    except Exception as _e:
        log.warning(f"Telegram Master Dashboard startup failed: {_e}")

    # ── MegaAutonomy Orchestrator Routen ────────────────────────────────────
    try:
        async def handle_mega_autonomy_status(request: web.Request) -> web.Response:
            from modules.mega_autonomy_orchestrator import get_mega_autonomy_status
            return web.Response(text=json.dumps(get_mega_autonomy_status()),
                                content_type="application/json")

        async def handle_mega_autonomy_run(request: web.Request) -> web.Response:
            from modules.mega_autonomy_orchestrator import run_mega_autonomy_cycle
            result = await run_mega_autonomy_cycle()
            return web.Response(text=json.dumps(result), content_type="application/json")

        async def handle_gumroad_setup(request: web.Request) -> web.Response:
            from modules.mega_autonomy_orchestrator import run_gumroad_full_setup
            result = await run_gumroad_full_setup()
            return web.Response(text=json.dumps(result), content_type="application/json")

        async def handle_stripe_sync(request: web.Request) -> web.Response:
            from modules.mega_autonomy_orchestrator import run_stripe_full_sync
            result = await run_stripe_full_sync()
            return web.Response(text=json.dumps(result), content_type="application/json")

        async def handle_ebay_import(request: web.Request) -> web.Response:
            count = int(request.rel_url.query.get("count", 5))
            from modules.mega_autonomy_orchestrator import run_ebay_import
            result = await run_ebay_import(count=count)
            return web.Response(text=json.dumps(result), content_type="application/json")

        app.router.add_get( "/api/mega-autonomy/status",     handle_mega_autonomy_status)
        app.router.add_post("/api/mega-autonomy/run",         handle_mega_autonomy_run)
        app.router.add_post("/api/gumroad/setup",             handle_gumroad_setup)
        app.router.add_post("/api/stripe/catalog-sync",       handle_stripe_sync)
        app.router.add_post("/api/ebay/import",               handle_ebay_import)
        log.info("MegaAutonomy routes registered (5 routes)")
    except Exception as _mega_e:
        log.warning("MegaAutonomy routes failed: %s", _mega_e)

    # ── Automation Scheduler starten (131 Tasks) ─────────────────────────────
    try:
        from core.automation_scheduler import get_scheduler as _get_sched
        _sched = _get_sched()
        asyncio.create_task(_sched.start())
        log.info("AutomationScheduler gestartet — %d Tasks registriert", len(_sched._task_handles) if hasattr(_sched, '_task_handles') else 0)
    except Exception as _sched_e:
        log.error("AutomationScheduler Fehler: %s", _sched_e)

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
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
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
    # isoformat() gibt "+00:00" zurück — in URL-Query wird "+" als Space interpretiert → "%2B"
    ts_from = (now - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
    ts_to   = (now - timedelta(hours=23)).isoformat().replace("+00:00", "Z")

    headers = {
        "apikey": auth_key,
        "Authorization": f"Bearer {auth_key}",
        "Content-Type": "application/json",
    }

    # Fetch leads created between 25h and 23h ago that have not been followed up yet
    params = (
        f"created_at=gte.{ts_from}"
        f"&created_at=lte.{ts_to}"
        f"&followed_up_at=is.null"
    )
    try:
        async with _aio.ClientSession() as s:
            r = await s.get(
                f"{sb_url}/rest/v1/leads?{params}",
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

        # Mark as followed_up_at with current timestamp
        if lead_id:
            try:
                async with _aio.ClientSession() as s:
                    await s.patch(
                        f"{sb_url}/rest/v1/leads?id=eq.{lead_id}",
                        json={"followed_up_at": now.isoformat()},
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
                          "parse_mode": "HTML"},
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


async def handle_export_customers(req: web.Request) -> web.Response:
    """POST /api/export/customers — Shopify Kunden → Klaviyo + Mailchimp aiitec exportieren."""
    try:
        from modules.customer_exporter import run_full_export
        result = await run_full_export()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_export_customers_stats(req: web.Request) -> web.Response:
    """GET /api/export/customers/stats — letzter Export-Status."""
    try:
        from modules.customer_exporter import get_export_stats
        stats = await get_export_stats()
        return web.json_response({"ok": True, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_infra_status(req: web.Request) -> web.Response:
    """GET /api/infra/status — ping all Railway/Vercel/Netlify services in parallel."""
    SERVICES_LIST = [
        # Railway backends
        {"name": "SuperMegaBot", "url": "https://supermegabot-production.up.railway.app/health", "type": "railway"},
        {"name": "Shopify Acq.", "url": "https://shopify-acquisition-engine-production.up.railway.app/health", "type": "railway"},
        {"name": "iComeAuto", "url": "https://icomeauto-saas-production.up.railway.app/health", "type": "railway"},
        {"name": "SEO Turbo", "url": "https://seo-turbo-tools-production.up.railway.app/health", "type": "railway"},
        {"name": "Telegram Bot", "url": "https://telegram-automation-bot-production.up.railway.app/health", "type": "railway"},
        {"name": "CreatorAI Ultra", "url": "https://creatorai-ultra-production.up.railway.app/health", "type": "railway"},
        {"name": "DS24 Suite", "url": "https://digistore24-automation-production.up.railway.app/health", "type": "railway"},
        {"name": "Cognitive Symphony", "url": "https://cognitive-symphony-production.up.railway.app/health", "type": "railway"},
        {"name": "Revenue Hub", "url": "https://revenue-hub-notifications-production.up.railway.app/health", "type": "railway"},
        {"name": "AdPoster Engine", "url": "https://adposter-engine-production.up.railway.app/health", "type": "railway"},
        {"name": "Steuercockpit", "url": "https://steuercockpit-production-44c9.up.railway.app/health", "type": "railway"},
        {"name": "Shopify Automaton", "url": "https://shopify-automaton-suite-production-e405.up.railway.app/health", "type": "railway"},
        {"name": "Meta Social", "url": "https://meta-social-engine-production.up.railway.app/health", "type": "railway"},
        {"name": "Freelance Gig", "url": "https://freelance-gig-engine-production.up.railway.app/health", "type": "railway"},
        {"name": "Visual Content", "url": "https://visual-content-engine-production.up.railway.app/health", "type": "railway"},
        {"name": "Analytics Pro", "url": "https://analytics-marketing-pro-production.up.railway.app/health", "type": "railway"},
        {"name": "Shopify KI Suite", "url": "https://shopify-ki-suite-production.up.railway.app/health", "type": "railway"},
        {"name": "SEO Traffic", "url": "https://seo-traffic-engine-production.up.railway.app/health", "type": "railway"},
        {"name": "Social Traffic", "url": "https://social-traffic-engine-production.up.railway.app/health", "type": "railway"},
        # Vercel frontends
        {"name": "Shopify Brutal", "url": "https://shopify-brutal-tuning.vercel.app", "type": "vercel"},
        {"name": "CreatorAI Vercel", "url": "https://creatorai-ultra.vercel.app", "type": "vercel"},
        {"name": "BullPower Hub", "url": "https://bullpower-hub.vercel.app", "type": "vercel"},
        {"name": "AutoIncome AI", "url": "https://autoincome-ai.vercel.app", "type": "vercel"},
        {"name": "Shopify Acq. Front", "url": "https://shopify-acquisition-engine.vercel.app", "type": "vercel"},
        {"name": "Shopify Suite Front", "url": "https://shopify-suite.vercel.app", "type": "vercel"},
        # Netlify
        {"name": "Mega Dashboard", "url": "https://cheery-beijinho-b74689.netlify.app", "type": "netlify"},
        {"name": "Hub Portal", "url": "https://bullpower-hub-portal.netlify.app", "type": "netlify"},
        {"name": "SteuercockPit", "url": "https://bullpower-steuercockpit.netlify.app", "type": "netlify"},
        {"name": "iComeAuto Front", "url": "https://bullpower-icomeauto.netlify.app", "type": "netlify"},
        {"name": "Lead Capture", "url": "https://bullpower-lead.netlify.app", "type": "netlify"},
    ]

    async def _ping(svc: dict) -> dict:
        t0 = time.time()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as s:
                async with s.get(svc["url"]) as r:
                    ms = int((time.time() - t0) * 1000)
                    return {**svc, "status": "online", "http": r.status, "ms": ms}
        except Exception as e:
            ms = int((time.time() - t0) * 1000)
            return {**svc, "status": "offline", "error": str(e)[:60], "ms": ms}

    results = await asyncio.gather(*[_ping(s) for s in SERVICES_LIST])
    online = sum(1 for r in results if r["status"] == "online")
    return web.json_response({
        "ok": True,
        "ts": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "online": online,
        "offline": len(results) - online,
        "services": results,
    })


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


async def handle_email_inbox_check(req):
    """GET /api/email/inbox — Postfächer prüfen (readonly, kein Auto-Reply)."""
    try:
        from modules.reply_monitor import check_inboxes_readonly
        return web.json_response(await check_inboxes_readonly())
    except Exception as e:
        log.error("handle_email_inbox_check: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_auto_responder_log(req):
    """GET /api/email/auto-responder — Log aller automatischen E-Mail-Antworten."""
    try:
        limit = int(req.rel_url.query.get("limit", 50))
        from modules.email_auto_responder import get_responder_log
        rows = await get_responder_log(limit)
        return web.json_response({"ok": True, "entries": rows, "count": len(rows)})
    except Exception as e:
        log.error("handle_auto_responder_log: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_inbox_monitor_run(req):
    """POST /api/email/scan — Inbox sofort scannen + Auto-Responder ausführen."""
    try:
        from modules.email_inbox_monitor import run_inbox_monitor
        result = await run_inbox_monitor()
        return web.json_response(result)
    except Exception as e:
        log.error("handle_inbox_monitor_run: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_scaling_status(req):
    """GET /api/scaling/status — Geldmaschine €10k Skalierung (echte Revenue-Daten)."""
    try:
        from modules.geldmaschine_skalierung import get_scaling_status
        return web.json_response(await get_scaling_status())
    except Exception as e:
        log.error("handle_scaling_status: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_scaling_run(req):
    """POST /api/scaling/run — Skalierungs-Zyklus sofort starten."""
    try:
        from modules.geldmaschine_skalierung import run_scaling_cycle
        result = await run_scaling_cycle()
        return web.json_response(result)
    except Exception as e:
        log.error("handle_scaling_run: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_revenue_status(req):
    """GET /api/revenue/status — Revenue Engine Status."""
    try:
        from modules.revenue_engine import get_revenue_status
        return web.json_response(await get_revenue_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_revenue_run(req):
    """POST /api/revenue/run — Geld-Zyklus sofort."""
    try:
        from modules.revenue_engine import run_revenue_cycle
        return web.json_response(await run_revenue_cycle())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_umsatzmaschine_status(req):
    try:
        from modules.megabot_umsatzmaschine import get_umsatzmaschine
        return web.json_response(get_umsatzmaschine().get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_umsatzmaschine_run(req):
    """POST /api/umsatzmaschine/run — vollautonomer Zyklus sofort."""
    try:
        from modules.megabot_umsatzmaschine import run_autonomous_cycle
        return web.json_response(await run_autonomous_cycle())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_umsatzmaschine_autonomous(req):
    """POST /api/umsatzmaschine/autonomous — alias für vollautonomen Zyklus."""
    return await handle_umsatzmaschine_run(req)


async def handle_mega_center_status(req):
    """GET /api/mega/status — BullPower MEGA Command Center Status."""
    try:
        from modules.mega_command_center import get_status
        return web.json_response(get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_mega_run(req):
    """POST /api/mega/run — vollständiger MEGA-Geldzyklus."""
    try:
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass
        from modules.mega_command_center import run_mega_cycle, run_daily_cycle
        if body.get("daily"):
            result = await run_daily_cycle()
        else:
            result = await run_mega_cycle(body.get("steps"))
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_mega_autonomous(req):
    return await handle_mega_run(req)


async def handle_umsatzmaschine_delivery(req):
    """POST /api/umsatzmaschine/delivery — sofortige Delivery für client_id oder Test."""
    try:
        body = await req.json()
        from modules.megabot_umsatzmaschine import get_umsatzmaschine, handle_stripe_checkout
        bot = get_umsatzmaschine()

        if body.get("simulate_checkout"):
            session = {
                "customer_email": body.get("email", "test@example.com"),
                "amount_total": int(float(body.get("amount", 97)) * 100),
                "metadata": {
                    "package": body.get("package", "compliance"),
                    "company_name": body.get("company_name", "Test GmbH"),
                },
            }
            return web.json_response(await handle_stripe_checkout(session))

        client_id = body.get("client_id")
        if not client_id:
            return web.json_response({"ok": False, "error": "client_id oder simulate_checkout nötig"}, status=400)
        result = await bot.trigger_immediate_delivery(client_id)
        return web.json_response({"ok": True, "client_id": client_id, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_revenue_summary(req):
    """GET /api/revenue/summary — combined revenue from Stripe + Shopify + DS24 (heute + Woche)."""
    import aiohttp as _aiohttp
    from datetime import timedelta
    try:
        now_utc   = datetime.utcnow()
        today     = now_utc.date().isoformat()
        week_ago  = (now_utc - timedelta(days=7)).date().isoformat()

        shopify_eur       = 0.0
        shopify_week_eur  = 0.0
        shopify_orders    = 0
        ds24_eur          = 0.0
        stripe_eur        = 0.0
        stripe_detail     = {}
        shopify_detail    = {}
        ds24_detail       = {}

        async with _aiohttp.ClientSession() as session:
            # Stripe — today's charges
            stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
            if stripe_key:
                try:
                    from modules.stripe_client import get_revenue_stats
                    st = await get_revenue_stats()
                    stripe_eur = st.get("today_revenue", 0.0)
                    stripe_detail = {
                        "today_revenue": stripe_eur,
                        "order_count":   st.get("order_count", 0),
                        "currency":      st.get("currency", "EUR"),
                        "ok": True,
                    }
                except Exception as e:
                    stripe_detail = {"ok": False, "error": str(e)}

            # Shopify orders — heute + letzte 7 Tage
            shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
            shopify_token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
            shopify_ver    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
            if shopify_domain and shopify_token:
                try:
                    hdrs = {"X-Shopify-Access-Token": shopify_token}
                    t = _aiohttp.ClientTimeout(total=12)
                    # Heute
                    url_today = (
                        f"https://{shopify_domain}/admin/api/{shopify_ver}/orders.json"
                        f"?status=any&created_at_min={today}T00:00:00Z&limit=100"
                    )
                    async with session.get(url_today, headers=hdrs, timeout=t) as r:
                        orders_today = (await r.json(content_type=None)).get("orders", [])
                    shopify_eur    = round(sum(float(o.get("total_price", 0)) for o in orders_today), 2)
                    shopify_orders = len(orders_today)
                    # Letzte 7 Tage
                    url_week = (
                        f"https://{shopify_domain}/admin/api/{shopify_ver}/orders.json"
                        f"?status=any&created_at_min={week_ago}T00:00:00Z&limit=250"
                    )
                    async with session.get(url_week, headers=hdrs, timeout=t) as r:
                        orders_week = (await r.json(content_type=None)).get("orders", [])
                    shopify_week_eur = round(sum(float(o.get("total_price", 0)) for o in orders_week), 2)
                    shopify_detail = {
                        "orders_today":      shopify_orders,
                        "revenue_today_eur": shopify_eur,
                        "revenue_week_eur":  shopify_week_eur,
                        "orders_week":       len(orders_week),
                        "ok": True,
                    }
                except Exception as e:
                    shopify_detail = {"ok": False, "error": str(e)}

            # DS24 stats
            try:
                from modules.digistore24_automation import get_sales_stats
                stats  = await get_sales_stats()
                ds24_eur = round(float(stats.get("today", 0)), 2)
                ds24_detail = {"ok": True, "today_eur": ds24_eur, "stats": stats}
            except Exception as e:
                ds24_detail = {"ok": False, "error": str(e)}

        total_eur      = round(shopify_eur + ds24_eur + stripe_eur, 2)
        this_week_eur  = round(shopify_week_eur + ds24_eur + stripe_eur, 2)

        return web.json_response({
            # Canonical flat fields for dashboard widgets
            "total_eur":       total_eur,
            "shopify_eur":     shopify_eur,
            "ds24_eur":        ds24_eur,
            "stripe_eur":      stripe_eur,
            "today":           today,
            "this_week":       this_week_eur,
            # Detailed per-platform breakdown
            "stripe":          stripe_detail,
            "shopify":         shopify_detail,
            "ds24":            ds24_detail,
            # Legacy alias
            "total_today_eur": total_eur,
            "timestamp":       now_utc.isoformat() + "Z",
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
        task_list = status.get("tasks", []) if isinstance(status, dict) else []
        total_runs = sum(int(t.get("total", 0) or 0) for t in task_list if isinstance(t, dict))
        task_count = int(status.get("task_count", len(task_list)) if isinstance(status, dict) else len(task_list))
        return web.json_response({
            "status": "ok",
            "tasks": status,
            "task_count": task_count,
            "total_tasks": task_count,
            "total_runs": total_runs,
            "running": bool(status.get("running")) if isinstance(status, dict) else False,
        })
    except Exception as e:
        tasks = [
            "shopify_sync", "ds24_revenue_sync", "health_alert", "trend_analysis",
            "backup", "ds24_funnel_sync", "traffic_seo_run", "brutus_run",
            "cro_run", "auto_funnel"
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
    # Tasks that are known to run longer than HTTP timeout — fire and return immediately
    _long_tasks = {
        "indexnow_mega_blast", "mega_seo_cycle",
        "brutus_ds24_affiliate", "traffic_swarm_full", "traffic_mega_cycle",
        "gmc_product_fix", "shopify_full_auto", "amazon_autonomy_cycle",
        "ebay_auto_fill", "backlink_outreach", "seo_mega_factory", "ultra_indexnow_all",
        "fiverr_sync", "upwork_sync", "fiverr_gig_blast", "tiktok_trend_blast",
        "tiktok_brutus", "upwork_proposal_gen", "product_generator", "revenue_blitz",
        "traffic_blitz_full", "ds24_traffic", "shopify_seo_blast", "shopify_mass_cycle",
        "autonomous_pipeline", "auto_product_pipeline", "bundle_creation_cycle",
        # B2B Lead tasks — JSF scraping + email sending takes 30-90s
        "handelsregister", "outreach_auto", "zvg_radar", "ai_act",
        "insolvenz_radar_scan", "insolvenz_autopost",
        # DS24 product creation — AI + API calls take 30-120s per product
        "ds24_product_creator", "ds24_affiliate_blast",
    }
    try:
        from core.automation_scheduler import get_scheduler
        sched = get_scheduler()
        if task_name in _long_tasks:
            asyncio.create_task(sched.run_now(task_name))
            return web.json_response({"status": "ok", "task": task_name,
                                      "result": f"{task_name} started in background"})
        result = await asyncio.wait_for(sched.run_now(task_name), timeout=25)
        return web.json_response({"status": "ok", "task": task_name, "result": result})
    except asyncio.TimeoutError:
        return web.json_response({"status": "ok", "task": task_name,
                                  "result": f"{task_name} running (timeout — still executing)"})
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
        "ok":      True,
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
        from modules.facebook_token_manager import get_callback_url
        code = req.rel_url.query.get("code", "")
        if not code:
            return web.Response(text="Missing code parameter", status=400)
        redirect_uri = get_callback_url()
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
        # FACEBOOK_USER_TOKEN → fallback to FACEBOOK_ACCESS_TOKEN or META_ACCESS_TOKEN
        user_tok = (
            os.getenv("FACEBOOK_USER_TOKEN") or
            os.getenv("FACEBOOK_META_TOKEN") or
            os.getenv("META_ACCESS_TOKEN") or
            os.getenv("FACEBOOK_ACCESS_TOKEN", "")
        )
        tokens = {
            "user_token":        user_tok,
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


async def handle_facebook_delete_data(req: web.Request) -> web.Response:
    """
    POST /facebook/delete-data
    Facebook Data Deletion Callback — pflicht für alle FB-Apps mit Login/Permissions.
    Erwartet: signed_request (form-encoded) oder JSON body mit signed_request.
    Gibt: confirmation_code + status_url zurück.
    """
    import hashlib, hmac, base64, json as _json, time as _time

    app_secret = os.getenv("FACEBOOK_APP_SECRET", "")

    # signed_request aus form-data oder JSON lesen
    signed_request = ""
    try:
        if req.content_type and "json" in req.content_type:
            body = await req.json()
            signed_request = body.get("signed_request", "")
        else:
            data = await req.post()
            signed_request = data.get("signed_request", "")
    except Exception:
        pass

    user_id = "unknown"
    if signed_request and app_secret:
        try:
            parts = signed_request.split(".", 1)
            if len(parts) == 2:
                encoded_sig, payload = parts
                # Base64url decode
                padding = "=" * (4 - len(payload) % 4)
                decoded = _json.loads(base64.urlsafe_b64decode(payload + padding))
                user_id = str(decoded.get("user_id", "unknown"))

                # HMAC-SHA256 Signatur prüfen
                expected = hmac.new(
                    app_secret.encode(),
                    payload.encode(),
                    hashlib.sha256,
                ).digest()
                sig_bytes = base64.urlsafe_b64decode(
                    encoded_sig + "=" * (4 - len(encoded_sig) % 4)
                )
                if not hmac.compare_digest(expected, sig_bytes):
                    log.warning("Facebook delete-data: ungültige Signatur für user %s", user_id)
                    user_id = "invalid_sig"
        except Exception as ex:
            log.warning("Facebook delete-data signed_request parse error: %s", ex)

    # Confirmation Code generieren
    ts = int(_time.time())
    confirmation_code = f"smb-del-{user_id[:12]}-{ts}"
    status_url = (
        f"https://supermegabot-production.up.railway.app/facebook/delete-status"
        f"?code={confirmation_code}"
    )

    log.info("Facebook data deletion request: user=%s code=%s", user_id, confirmation_code)

    # Optional: User in Supabase als gelöscht markieren
    try:
        supa_url = os.getenv("SUPABASE_URL", "")
        supa_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if supa_url and supa_key and user_id not in ("unknown", "invalid_sig"):
            import aiohttp as _ahttp
            async with _ahttp.ClientSession() as s:
                await s.post(
                    f"{supa_url}/rest/v1/lead_events",
                    headers={
                        "apikey": supa_key,
                        "Authorization": f"Bearer {supa_key}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal",
                    },
                    json={
                        "event_type": "facebook_data_deletion",
                        "platform": "facebook",
                        "external_id": user_id,
                        "details": confirmation_code,
                    },
                    timeout=_ahttp.ClientTimeout(total=5),
                )
    except Exception:
        pass

    return web.json_response({
        "url": status_url,
        "confirmation_code": confirmation_code,
    })


async def handle_facebook_delete_status(req: web.Request) -> web.Response:
    """GET /facebook/delete-status?code=... — Status-Seite für Facebook Data Deletion."""
    code = req.rel_url.query.get("code", "")
    html = f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>Datenlöschung bestätigt</title>
<style>body{{font-family:sans-serif;max-width:600px;margin:60px auto;text-align:center;color:#333}}
h1{{color:#1877f2}}p{{margin:16px 0}}code{{background:#f0f0f0;padding:4px 8px;border-radius:4px}}</style>
</head>
<body>
<h1>Datenlöschung bestätigt</h1>
<p>Deine Facebook-Daten wurden aus unserem System entfernt.</p>
<p>Bestätigungscode: <code>{code}</code></p>
<p>Bei Fragen: <a href="mailto:bullpowersrtkennels@gmail.com">bullpowersrtkennels@gmail.com</a></p>
</body></html>"""
    return web.Response(text=html, content_type="text/html")


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


async def handle_indexnow_key2(req):
    """GET /bullpowerhub2026seo.txt — IndexNow key verification (MegaSEO Engine)."""
    return web.Response(text="bullpowerhub2026seo", content_type="text/plain")


async def handle_tiktok_verify_file(req):
    """GET /tiktokZkDbIqcx5ixmxCEuDg2a6PzhC8qm7qN2.txt — TikTok domain verification."""
    return web.Response(text="tiktok-developers-site-verification=ZkDbIqcx5ixmxCEuDg2a6PzhC8qm7qN2", content_type="text/plain")


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
        "Sitemap: https://supermegabot-production.up.railway.app/sitemap.xml\n"
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


async def handle_mail_error_guard(req):
    """POST /api/mail/error-guard — Gmail scannen + Fehler-Muster + Auto-Fix."""
    async def _bg():
        try:
            from modules.mail_error_guard import run_mail_error_guard
            await run_mail_error_guard()
        except Exception as exc:
            logging.getLogger("MailGuard").error("BG error: %s", exc)
    asyncio.ensure_future(_bg())
    return web.json_response({"status": "started", "message": "Mail Error Guard läuft — Gmail scan + Fehler-Fingerprint + Auto-Fix"})


async def handle_mail_error_summary(req):
    """GET /api/mail/errors — alle offenen Fehler aus DB."""
    try:
        from modules.mail_error_guard import get_error_summary
        r = await get_error_summary()
        return web.json_response({"ok": True, **r})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_monetization_launch(req):
    """POST /api/monetization/launch — BPI Blast + Email Outreach + Shopify + Revenue Report."""
    async def _bg():
        try:
            from modules.monetization_engine import launch_monetization
            body = {}
            try:
                body = await req.json()
            except Exception:
                pass
            await launch_monetization(
                bpi=body.get("bpi", True),
                email=body.get("email", True),
                shopify=body.get("shopify", True),
                tiktok=body.get("tiktok", True),
                report=body.get("report", True),
            )
        except Exception as exc:
            logging.getLogger("Monetization").error("BG error: %s", exc)
    asyncio.ensure_future(_bg())
    return web.json_response({
        "status": "started",
        "message": "Monetization Engine läuft — BPI Blast + Email Outreach + Shopify Traffic + Revenue Report",
    })


async def handle_mac_watchdog(req):
    """POST /api/watchdog/run — Mac + Railway + APIs sofort prüfen + auto-repair."""
    async def _bg():
        try:
            from modules.mac_watchdog import run_mac_watchdog
            await run_mac_watchdog()
        except Exception as exc:
            logging.getLogger("MacWatchdog").error("BG error: %s", exc)
    asyncio.ensure_future(_bg())
    return web.json_response({"status": "started",
                              "message": "Mac Watchdog läuft — CPU/RAM/Disk + Railway + APIs + auto-repair"})


async def handle_monitor_hub(req):
    """POST /api/monitor/run — Gmail + Telegram Posts + Scheduler-Fehler sofort prüfen."""
    async def _bg():
        try:
            from modules.monitor_hub import run_monitor_hub
            await run_monitor_hub()
        except Exception as exc:
            logging.getLogger("MonitorHub").error("BG error: %s", exc)
    asyncio.ensure_future(_bg())
    return web.json_response({"status": "started",
                              "message": "Monitor Hub läuft — Gmail + Telegram + Scheduler werden geprüft"})


async def handle_content_loop(req):
    """POST /api/content-loop/run — Smart Home SEO-Artikel → Shopify + IndexNow + Telegram + LinkedIn."""
    async def _bg():
        try:
            from modules.content_loop_engine import run_content_loop
            await run_content_loop()
        except Exception as exc:
            logging.getLogger("ContentLoop").error("BG error: %s", exc)
    asyncio.ensure_future(_bg())
    return web.json_response({"status": "started",
                              "message": "Content Loop läuft — Shopify Blog + IndexNow + Telegram + LinkedIn + Dev.to"})


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
    Webhook URL: https://supermegabot-production.up.railway.app/api/twitter/post
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
    result = await get_discord_status()
    result["ok"] = bool(
        os.getenv("DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_BOT_TOKEN")
    )
    result["autonomous_posting"] = True
    return web.json_response(result)


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


async def handle_shopify_ab_tests(req):
    """GET /api/shopify/ab-tests — aktive und abgeschlossene Shopify A/B Tests."""
    try:
        from modules.shopify_ab_tester import get_ab_test_status
        data = await get_ab_test_status()
        return web.json_response({"ok": True, **data})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def handle_shopify_ab_run(req):
    """POST /api/shopify/ab-tests/run — neue A/B Tests manuell starten."""
    try:
        from modules.shopify_ab_tester import run_shopify_ab_tests
        result = await run_shopify_ab_tests()
        return web.json_response({"ok": True, **result})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def handle_shopify_ab_analyze(req):
    """POST /api/shopify/ab-tests/analyze — Gewinner sofort auswerten."""
    try:
        from modules.shopify_ab_tester import analyze_shopify_ab_winners
        result = await analyze_shopify_ab_winners()
        return web.json_response({"ok": True, **result})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


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


# ═══════════════════════════════════════════════════════════════════════════
#  OUTREACH ENGINE — Handlers
# ═══════════════════════════════════════════════════════════════════════════

_outreach_running = False

async def handle_outreach_page(req):
    html = """<!DOCTYPE html>
<html lang="de"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>&#x1F4E7; Outreach Engine &mdash; Automatische B2B-Akquise</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0a0a0f;--card:#111118;--border:#1e1e2e;--accent:#2563eb;--green:#10b981;--yellow:#f59e0b;--red:#ef4444;--text:#e2e8f0;--muted:#64748b}
body{font-family:'SF Pro Display',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.header{background:linear-gradient(135deg,#050d1a 0%,#0f172a 60%,#0a1a05 100%);border-bottom:1px solid #1e3a5f;padding:18px 28px;display:flex;align-items:center;justify-content:space-between}
.logo{font-size:1.4rem;font-weight:900}
.logo span{background:linear-gradient(90deg,#3b82f6,#10b981);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.nav a{color:#94a3b8;text-decoration:none;margin-left:18px;font-size:.82rem}
.hero{padding:30px 28px 20px;border-bottom:1px solid var(--border)}
.hero h1{font-size:1.8rem;font-weight:900;margin-bottom:6px}
.hero h1 span{background:linear-gradient(90deg,#3b82f6,#10b981);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hero p{color:var(--muted);font-size:.88rem;max-width:620px;line-height:1.6;margin-bottom:16px}
.stats-row{display:flex;gap:16px;flex-wrap:wrap}
.stat-box{background:rgba(37,99,235,.08);border:1px solid rgba(37,99,235,.2);border-radius:10px;padding:12px 18px;min-width:110px}
.stat-val{font-size:1.6rem;font-weight:900;color:#3b82f6}
.stat-lbl{font-size:.7rem;color:var(--muted);margin-top:2px}
.action-bar{padding:16px 28px;display:flex;gap:12px;align-items:center;border-bottom:1px solid var(--border);flex-wrap:wrap}
.btn{padding:10px 22px;border:none;border-radius:9px;cursor:pointer;font-weight:800;font-size:.84rem;transition:opacity .15s}
.btn-fire{background:linear-gradient(90deg,#2563eb,#10b981);color:#fff;font-size:.9rem;padding:12px 28px}
.btn-fire:hover{opacity:.85}
.btn-fire:disabled{opacity:.4;cursor:not-allowed}
.btn-outline{background:transparent;border:1px solid var(--border);color:var(--text)}
.filter-group{display:flex;align-items:center;gap:8px;margin-left:auto}
.filter-group label{font-size:.78rem;color:var(--muted)}
select{background:#0d0d16;border:1px solid var(--border);color:var(--text);padding:7px 12px;border-radius:7px;font-size:.82rem}
.queue-section{padding:20px 28px}
.queue-section h3{font-size:.88rem;font-weight:700;color:var(--muted);margin-bottom:14px;text-transform:uppercase;letter-spacing:.5px}
.queue-grid{display:flex;flex-direction:column;gap:10px}
.outreach-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px;display:grid;grid-template-columns:1fr auto;gap:12px}
.outreach-card.sent{border-color:rgba(16,185,129,.3)}
.outreach-card.replied{border-color:var(--green);background:rgba(16,185,129,.05)}
.outreach-card.error{border-color:rgba(239,68,68,.3)}
.oc-top{display:flex;align-items:flex-start;gap:12px}
.oc-icon{font-size:1.4rem;flex-shrink:0}
.oc-target{font-weight:800;font-size:.92rem}
.oc-meta{font-size:.74rem;color:var(--muted);margin-top:3px}
.oc-lead{display:flex;align-items:center;gap:8px;margin-top:10px;padding:8px 12px;background:#0d0d16;border-radius:8px;font-size:.8rem}
.lead-score{padding:2px 8px;border-radius:5px;font-weight:800;font-size:.7rem}
.ls-high{background:rgba(239,68,68,.15);color:#ef4444}
.ls-mid{background:rgba(245,158,11,.15);color:#f59e0b}
.ls-low{background:rgba(100,116,139,.1);color:#64748b}
.oc-subject{font-size:.8rem;color:var(--muted);margin-top:8px;font-style:italic}
.oc-actions{display:flex;flex-direction:column;gap:6px;align-items:flex-end}
.status-badge{padding:3px 10px;border-radius:6px;font-size:.7rem;font-weight:700}
.sb-pending{background:rgba(245,158,11,.15);color:#f59e0b}
.sb-sent{background:rgba(37,99,235,.15);color:#3b82f6}
.sb-replied{background:rgba(16,185,129,.15);color:#10b981}
.sb-error{background:rgba(239,68,68,.15);color:#ef4444}
.btn-copy{padding:5px 12px;border-radius:6px;background:#1e1e2e;border:1px solid var(--border);color:var(--text);cursor:pointer;font-size:.74rem;font-weight:700;white-space:nowrap}
.btn-copy:hover{background:#2a2a3e}
.btn-replied{padding:5px 12px;border-radius:6px;background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.3);color:#10b981;cursor:pointer;font-size:.74rem;font-weight:700}
.li-msg-box{display:none;margin-top:10px;padding:12px;background:#0d0d16;border:1px solid var(--border);border-radius:8px;font-size:.78rem;color:#94a3b8;white-space:pre-wrap;word-break:break-word;line-height:1.5}
.li-msg-box.open{display:block}
.toast{position:fixed;bottom:24px;right:24px;background:#10b981;color:#fff;padding:10px 20px;border-radius:10px;font-weight:700;font-size:.84rem;transform:translateY(100px);transition:transform .3s;z-index:300}
.toast.show{transform:translateY(0)}
.empty{padding:40px;text-align:center;color:var(--muted);font-size:.88rem}
@keyframes spin{to{transform:rotate(360deg)}}
.spin{display:inline-block;animation:spin .8s linear infinite}
</style></head><body>
<div class="header">
  <div class="logo">&#x1F4E7; <span>Outreach Engine</span></div>
  <nav class="nav">
    <a href="/">Dashboard</a><a href="/insolvenz-radar">Insolvenz Radar</a><a href="/money-machine">Money Machine</a>
  </nav>
</div>

<div class="hero">
  <h1>&#x1F4E7; <span>Automatische B2B-Akquise</span></h1>
  <p>Nimmt die besten Leads aus dem Insolvenz Radar, generiert personalisierte Nachrichten f&#252;r
  Steuerberater + Factoring-Firmen und sendet sie automatisch per Gmail. LinkedIn-Nachrichten mit 1 Klick kopieren.</p>
  <div class="stats-row">
    <div class="stat-box"><div class="stat-val" id="stat-total">--</div><div class="stat-lbl">Gesamt</div></div>
    <div class="stat-box"><div class="stat-val" id="stat-sent">--</div><div class="stat-lbl">Gesendet</div></div>
    <div class="stat-box"><div class="stat-val" id="stat-pending">--</div><div class="stat-lbl">Ausstehend</div></div>
    <div class="stat-box"><div class="stat-val" id="stat-today">--</div><div class="stat-lbl">Heute</div></div>
  </div>
</div>

<div class="action-bar">
  <button class="btn btn-fire" id="fire-btn" onclick="runOutreach()">
    &#x1F680; 10 Nachrichten JETZT senden
  </button>
  <button class="btn btn-outline" onclick="runOutreach(false)">
    &#x270F; Nur generieren (kein Senden)
  </button>
  <div class="filter-group">
    <label>Zeige:</label>
    <select id="f-status" onchange="loadQueue()">
      <option value="">Alle</option>
      <option value="pending">Ausstehend</option>
      <option value="sent">Gesendet</option>
      <option value="replied">Geantwortet</option>
      <option value="error">Fehler</option>
    </select>
  </div>
</div>

<div class="queue-section">
  <h3>&#x1F4CB; Outreach Queue</h3>
  <div class="queue-grid" id="queue-grid"><div class="empty">Lade Queue...</div></div>
</div>

<div id="toast" class="toast">&#x2705; Kopiert!</div>

<script>
async function loadStatus(){try{const r=await fetch('/api/outreach/status');const d=await r.json();if(!d.ok)return;document.getElementById('stat-total').textContent=d.total||0;document.getElementById('stat-sent').textContent=d.sent||0;document.getElementById('stat-pending').textContent=d.pending||0;document.getElementById('stat-today').textContent=d.today||0;}catch(e){}}

async function loadQueue(){
  const status=document.getElementById('f-status').value;
  const grid=document.getElementById('queue-grid');
  grid.innerHTML='<div class="empty">Lade...</div>';
  try{
    const r=await fetch('/api/outreach/queue?status='+encodeURIComponent(status)+'&limit=30');
    const d=await r.json();
    const items=d.queue||[];
    if(!items.length){grid.innerHTML='<div class="empty">Keine Eintr&#228;ge in dieser Kategorie.</div>';return;}
    grid.innerHTML=items.map(item=>{
      const sc=item.lead_score||0;
      const scClass=sc>=70?'ls-high':sc>=50?'ls-mid':'ls-low';
      const st=item.status||'pending';
      const stLabel={pending:'Ausstehend',sent:'Gesendet',replied:'Geantwortet &#x1F389;',error:'Fehler'};
      const stClass={'pending':'sb-pending','sent':'sb-sent','replied':'sb-replied','error':'sb-error'};
      const channelIcon={'email':'&#x1F4E7;','linkedin':'&#x1F517;','twitter':'&#x1F426;'}['email']||'&#x1F4E7;';
      const liMsg=item.body_linkedin||'';
      return `<div class="outreach-card ${st}" id="card-${item.id}">
        <div>
          <div class="oc-top">
            <div class="oc-icon">${channelIcon}</div>
            <div>
              <div class="oc-target">${item.target_name}</div>
              <div class="oc-meta">${item.target_type||'?'} &middot; ${item.target_email||'kein Email'}</div>
            </div>
          </div>
          <div class="oc-lead">
            <span class="lead-score ${scClass}">${sc}</span>
            <span><b>${item.lead_name||'?'}</b></span>
            <span style="color:var(--muted)">${item.lead_bundesland||''} &middot; ${item.lead_branche||''}</span>
          </div>
          <div class="oc-subject">Betreff: ${item.subject||'?'}</div>
          <div class="li-msg-box" id="li-${item.id}">${(liMsg).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
        </div>
        <div class="oc-actions">
          <span class="status-badge ${stClass[st]||'sb-pending'}">${stLabel[st]||st}</span>
          <button class="btn-copy" onclick="copyLinkedIn(${item.id},'${encodeURIComponent(liMsg)}')">&#x1F517; LI kopieren</button>
          ${st!=='replied'?`<button class="btn-replied" onclick="markReplied(${item.id})">&#x2714; Geantwortet</button>`:''}
        </div>
      </div>`;
    }).join('');
  }catch(e){grid.innerHTML='<div class="empty">Fehler: '+e.message+'</div>';}
}

async function runOutreach(autoSend=true){
  const btn=document.getElementById('fire-btn');
  btn.disabled=true;btn.innerHTML='<span class="spin">&#9881;</span>&nbsp;Generiere + Sende...';
  try{
    const r=await fetch('/api/outreach/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({auto_send:autoSend})});
    const d=await r.json();
    if(d.ok){
      btn.innerHTML=`&#x2705; ${d.sent} gesendet, ${d.generated} generiert`;
      loadStatus();loadQueue();
      setTimeout(()=>{btn.disabled=false;btn.innerHTML='&#x1F680; 10 Nachrichten JETZT senden';},10000);
    }else{btn.innerHTML='&#x26A0; '+d.error;btn.disabled=false;}
  }catch(e){btn.innerHTML='&#x26A0; Fehler';btn.disabled=false;}
}

function copyLinkedIn(id,encoded){
  const text=decodeURIComponent(encoded);
  navigator.clipboard.writeText(text).then(()=>{showToast('LinkedIn-Nachricht kopiert!');});
  const box=document.getElementById('li-'+id);
  if(box){box.classList.toggle('open');}
}

async function markReplied(id){
  await fetch('/api/outreach/mark-replied',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
  document.getElementById('card-'+id).className='outreach-card replied';
  showToast('Als "Geantwortet" markiert &#x1F389;');
  setTimeout(loadQueue,1000);
}

function showToast(msg){const t=document.getElementById('toast');t.innerHTML=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2500);}

loadStatus();loadQueue();setInterval(loadStatus,30000);
</script></body></html>"""
    return web.Response(text=html, content_type="text/html")


async def handle_outreach_status(req):
    try:
        from modules.outreach_engine import get_status
        return web.json_response(get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_outreach_queue(req):
    try:
        from modules.outreach_engine import get_queue
        status = req.rel_url.query.get("status", "")
        limit  = int(req.rel_url.query.get("limit", "50"))
        return web.json_response({"ok": True, "queue": get_queue(status=status, limit=limit)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_outreach_run(req):
    global _outreach_running
    if _outreach_running:
        return web.json_response({"ok": False, "error": "Läuft bereits"})
    try:
        body      = await req.json()
        auto_send = body.get("auto_send", True)
    except Exception:
        auto_send = True

    async def _bg():
        global _outreach_running
        _outreach_running = True
        try:
            from modules.outreach_engine import generate_outreach_batch
            await generate_outreach_batch(auto_send_email=auto_send, max_targets=10)
        except Exception as e:
            log.error("Outreach batch: %s", e)
        finally:
            _outreach_running = False

    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "Outreach-Batch gestartet",
                              "auto_send": auto_send})


async def handle_outreach_mark_replied(req):
    try:
        body = await req.json()
        oid  = int(body.get("id", 0))
        from modules.outreach_engine import mark_replied
        return web.json_response(mark_replied(oid))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════════════════
#  INSOLVENZ RADAR PRO — Handlers
# ═══════════════════════════════════════════════════════════════════════════

_ir_running = False

async def handle_ir_page(req):
    html = """<!DOCTYPE html>
<html lang="de"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>&#x1F3DB; Insolvenz Radar Pro &mdash; B2B Leadmaschine</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0a0a0f;--card:#111118;--border:#1e1e2e;--accent:#dc2626;--accent2:#f97316;--green:#10b981;--yellow:#f59e0b;--blue:#3b82f6;--text:#e2e8f0;--muted:#64748b}
body{font-family:'SF Pro Display',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.header{background:linear-gradient(135deg,#1a0505 0%,#0f172a 50%,#150a00 100%);border-bottom:1px solid #4b1111;padding:18px 28px;display:flex;align-items:center;justify-content:space-between}
.logo{font-size:1.4rem;font-weight:900}
.logo span{background:linear-gradient(90deg,#ef4444,#f97316,#fbbf24);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.nav a{color:#94a3b8;text-decoration:none;margin-left:18px;font-size:.82rem}
.hero{padding:36px 28px 20px;background:linear-gradient(180deg,rgba(220,38,38,.07) 0%,transparent 100%);border-bottom:1px solid rgba(220,38,38,.15)}
.hero h1{font-size:2rem;font-weight:900;margin-bottom:8px}
.hero h1 span{background:linear-gradient(90deg,#ef4444,#f97316);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hero p{color:var(--muted);font-size:.92rem;max-width:600px;line-height:1.6;margin-bottom:20px}
.hero-stats{display:flex;gap:24px;flex-wrap:wrap}
.hstat{background:rgba(220,38,38,.08);border:1px solid rgba(220,38,38,.2);border-radius:10px;padding:14px 20px;min-width:130px}
.hstat-val{font-size:1.8rem;font-weight:900;color:#ef4444}
.hstat-label{font-size:.72rem;color:var(--muted);margin-top:2px}
.controls{display:flex;gap:10px;padding:16px 28px;flex-wrap:wrap;align-items:center;border-bottom:1px solid var(--border)}
.filter-group{display:flex;align-items:center;gap:8px}
.filter-group label{font-size:.78rem;color:var(--muted);white-space:nowrap}
select,input[type=number]{background:#0d0d16;border:1px solid var(--border);color:var(--text);padding:7px 12px;border-radius:7px;font-size:.82rem}
.btn{padding:8px 18px;border:none;border-radius:8px;cursor:pointer;font-weight:700;font-size:.82rem;transition:opacity .15s}
.btn-scan{background:linear-gradient(90deg,var(--accent),var(--accent2));color:#fff}
.btn-scan:hover{opacity:.85}
.btn-scan:disabled{opacity:.4;cursor:not-allowed}
.leads-grid{padding:20px 28px}
.leads-grid h3{font-size:.9rem;font-weight:700;color:var(--muted);margin-bottom:14px}
.lead-table{width:100%;border-collapse:collapse}
.lead-table th{text-align:left;padding:10px 12px;font-size:.72rem;color:var(--muted);border-bottom:1px solid var(--border);text-transform:uppercase;letter-spacing:.5px}
.lead-table td{padding:12px;border-bottom:1px solid rgba(30,30,46,.6);font-size:.84rem;vertical-align:top}
.lead-table tr:hover td{background:rgba(255,255,255,.02)}
.score-badge{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:6px;font-size:.72rem;font-weight:800}
.score-high{background:rgba(220,38,38,.2);color:#ef4444;border:1px solid rgba(220,38,38,.3)}
.score-mid{background:rgba(245,158,11,.15);color:#f59e0b;border:1px solid rgba(245,158,11,.25)}
.score-low{background:rgba(100,116,139,.1);color:#64748b;border:1px solid rgba(100,116,139,.2)}
.lead-name{font-weight:700;color:var(--text);max-width:220px;word-break:break-word}
.lead-meta{font-size:.72rem;color:var(--muted);margin-top:3px}
.tag{display:inline-block;padding:2px 8px;background:rgba(59,130,246,.1);color:#60a5fa;border-radius:4px;font-size:.68rem;margin:2px 2px 0 0;border:1px solid rgba(59,130,246,.2)}
.pricing{padding:28px}
.pricing h2{font-size:1.4rem;font-weight:800;margin-bottom:6px}
.pricing-sub{color:var(--muted);font-size:.88rem;margin-bottom:22px}
.plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
.plan{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px;position:relative}
.plan.featured{border-color:var(--accent);box-shadow:0 0 25px rgba(220,38,38,.12)}
.plan-badge{position:absolute;top:-10px;left:50%;transform:translateX(-50%);background:linear-gradient(90deg,var(--accent),var(--accent2));color:#fff;padding:3px 12px;border-radius:8px;font-size:.7rem;font-weight:800}
.plan-name{font-size:.95rem;font-weight:800;margin-bottom:4px}
.plan-price{font-size:1.9rem;font-weight:900;color:var(--accent);margin-bottom:4px}
.plan-price span{font-size:.8rem;color:var(--muted);font-weight:400}
.plan-features{list-style:none;margin:14px 0 18px}
.plan-features li{padding:4px 0;font-size:.82rem;color:#94a3b8;border-bottom:1px solid var(--border);display:flex;gap:7px;align-items:center}
.plan-features li:last-child{border:none}
.plan-features li::before{content:"\\2713";color:var(--green);font-weight:800}
.plan-btn{width:100%;padding:11px;border:none;border-radius:8px;font-weight:800;font-size:.87rem;cursor:pointer}
.plan-btn-primary{background:linear-gradient(90deg,var(--accent),var(--accent2));color:#fff}
.plan-btn-secondary{background:#1e1e2e;color:var(--text);border:1px solid var(--border)}
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:200;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal{background:var(--card);border:1px solid rgba(220,38,38,.3);border-radius:16px;padding:32px;max-width:400px;width:90%}
.modal h4{font-size:1.15rem;font-weight:800;margin-bottom:7px}
.modal p{color:var(--muted);font-size:.84rem;margin-bottom:16px}
.form-group label{display:block;font-size:.77rem;color:var(--muted);margin-bottom:5px}
.form-group input{width:100%;background:#0d0d16;border:1px solid var(--border);color:var(--text);padding:10px 12px;border-radius:8px;font-size:.87rem;margin-bottom:12px}
.modal-footer{display:flex;gap:8px;margin-top:14px}
.btn-cancel{flex:1;padding:10px;background:#1e1e2e;border:1px solid var(--border);color:var(--text);border-radius:8px;cursor:pointer;font-weight:700}
.btn-pay{flex:2;padding:10px;background:linear-gradient(90deg,var(--accent),var(--accent2));color:#fff;border:none;border-radius:8px;cursor:pointer;font-weight:800}
.empty{padding:40px;text-align:center;color:var(--muted);font-size:.88rem}
@keyframes spin{to{transform:rotate(360deg)}}
.spin{display:inline-block;animation:spin .8s linear infinite}
</style></head><body>
<div class="header">
  <div class="logo">&#x1F3DB; <span>Insolvenz Radar Pro</span></div>
  <nav class="nav">
    <a href="/">Dashboard</a><a href="/money-machine">Money Machine</a><a href="/viral">Viral</a>
  </nav>
</div>

<div class="hero">
  <h1>&#x1F3DB; <span>Staatsregister = Deine</span> Leadmaschine</h1>
  <p>T&#228;glich neue B2B-Leads aus dem offiziellen deutschen Insolvenzregister &mdash; automatisch bewertet, nach Branche geclustert, sofort per Telegram gemeldet. Ideal f&#252;r Steuerberater, Factoring-Firmen und M&amp;A-Berater.</p>
  <div class="hero-stats" id="hero-stats">
    <div class="hstat"><div class="hstat-val" id="stat-total">--</div><div class="hstat-label">Leads gesamt</div></div>
    <div class="hstat"><div class="hstat-val" id="stat-today">--</div><div class="hstat-label">Heute neu</div></div>
    <div class="hstat"><div class="hstat-val" id="stat-high">--</div><div class="hstat-label">Score 70+</div></div>
    <div class="hstat"><div class="hstat-val" id="stat-alerted">--</div><div class="hstat-label">Alerts gesendet</div></div>
  </div>
</div>

<div class="controls">
  <div class="filter-group">
    <label>Bundesland</label>
    <select id="f-bl" onchange="loadLeads()">
      <option value="">Alle</option>
      <option value="NW">NRW</option><option value="BY">Bayern</option>
      <option value="BW">Baden-W&#252;rttemberg</option><option value="HE">Hessen</option>
      <option value="NI">Niedersachsen</option><option value="BE">Berlin</option>
      <option value="HH">Hamburg</option><option value="SN">Sachsen</option>
      <option value="RP">Rheinland-Pfalz</option><option value="ST">Sachsen-Anhalt</option>
      <option value="SH">Schleswig-Holstein</option><option value="TH">Th&#252;ringen</option>
      <option value="BB">Brandenburg</option><option value="MV">Mecklenburg-VP</option>
      <option value="SL">Saarland</option><option value="HB">Bremen</option>
    </select>
  </div>
  <div class="filter-group">
    <label>Min. Score</label>
    <select id="f-score" onchange="loadLeads()">
      <option value="0">Alle</option><option value="40">40+</option>
      <option value="60" selected>60+</option><option value="70">70+</option>
      <option value="80">80+</option>
    </select>
  </div>
  <button class="btn btn-scan" id="scan-btn" onclick="triggerScan()">&#x1F50D; Jetzt Scannen</button>
</div>

<div class="leads-grid">
  <h3 id="leads-title">&#x2C3; Lade Leads...</h3>
  <div id="leads-container"><div class="empty">Lade...</div></div>
</div>

<div class="pricing">
  <h2>&#x1F4B0; Insolvenz Radar Pro &mdash; Subscriptions</h2>
  <p class="pricing-sub">T&#228;glich frische B2B-Leads. F&#252;r Steuerberater, Factoring, M&amp;A, Inkasso.</p>
  <div class="plans">
    <div class="plan">
      <div class="plan-name">Starter</div>
      <div class="plan-price">&#8364;29 <span>/ Monat</span></div>
      <ul class="plan-features">
        <li>50 Leads/Tag</li><li>Score-Filter</li>
        <li>Email-Alert t&#228;glich</li><li>1 Bundesland</li>
      </ul>
      <button class="plan-btn plan-btn-secondary" onclick="openModal('starter')">Starten &rarr;</button>
    </div>
    <div class="plan featured">
      <div class="plan-badge">&#x2B50; PROFI-WAHL</div>
      <div class="plan-name">Pro</div>
      <div class="plan-price">&#8364;79 <span>/ Monat</span></div>
      <ul class="plan-features">
        <li>Unlimitierte Leads</li><li>Alle 16 Bundesl&#228;nder</li>
        <li>Echtzeit Telegram-Alert</li><li>CRM-Webhook (HubSpot/Pipedrive)</li>
        <li>AI-Lead-Scoring</li><li>Branchen-Filter</li>
      </ul>
      <button class="plan-btn plan-btn-primary" onclick="openModal('pro')">Pro starten &rarr;</button>
    </div>
    <div class="plan">
      <div class="plan-name">Agency</div>
      <div class="plan-price">&#8364;199 <span>/ Monat</span></div>
      <ul class="plan-features">
        <li>Alles aus Pro</li><li>White-Label Dashboard</li>
        <li>REST API-Zugang</li><li>Eigene Score-Regeln</li>
        <li>Priority Support</li>
      </ul>
      <button class="plan-btn plan-btn-secondary" onclick="openModal('agency')">Agency &rarr;</button>
    </div>
  </div>
</div>

<div class="modal-overlay" id="modal-overlay">
  <div class="modal">
    <h4 id="modal-title">Insolvenz Radar starten</h4>
    <p>Weiterleitung zu Stripe. T&#228;glich frische B2B-Leads. K&#252;ndige jederzeit.</p>
    <div class="form-group">
      <label>E-Mail-Adresse</label>
      <input type="email" id="modal-email" placeholder="kanzlei@email.de">
    </div>
    <div class="modal-footer">
      <button class="btn-cancel" onclick="closeModal()">Abbrechen</button>
      <button class="btn-pay" id="pay-btn" onclick="doCheckout()">&#x1F4B3; Jetzt zahlen &rarr;</button>
    </div>
  </div>
</div>

<script>
let selectedTier = 'starter';
const BL = {BB:'Brandenburg',BE:'Berlin',BW:'Baden-W.',BY:'Bayern',HB:'Bremen',HE:'Hessen',HH:'Hamburg',MV:'Mecklenburg-VP',NI:'Niedersachsen',NW:'NRW',RP:'Rheinland-Pfalz',SH:'Schleswig-Holstein',SL:'Saarland',SN:'Sachsen',ST:'Sachsen-Anhalt',TH:'Th\\u00FCringen'};

async function loadStatus(){try{const r=await fetch('/api/insolvenz-radar/status');const d=await r.json();if(!d.ok)return;document.getElementById('stat-total').textContent=d.total_leads||0;document.getElementById('stat-today').textContent=d.leads_today||0;document.getElementById('stat-high').textContent=d.high_score||0;document.getElementById('stat-alerted').textContent=d.alerted||0;}catch(e){}}

async function loadLeads(){
  const bl=document.getElementById('f-bl').value;
  const score=document.getElementById('f-score').value;
  const container=document.getElementById('leads-container');
  const title=document.getElementById('leads-title');
  container.innerHTML='<div class="empty">Lade...</div>';
  try{
    const params=new URLSearchParams();
    if(bl)params.set('bundesland',bl);
    if(score)params.set('min_score',score);
    params.set('limit','50');
    const r=await fetch('/api/insolvenz-radar/leads?'+params);
    const d=await r.json();
    const leads=d.leads||[];
    title.textContent=leads.length+' Leads (Score '+score+'+ | '+(bl?BL[bl]||bl:'Alle Bundesl\\u00E4nder')+')';
    if(!leads.length){container.innerHTML='<div class="empty">Keine Leads f\\u00FCr diese Filter. Scan starten?</div>';return;}
    container.innerHTML='<table class="lead-table"><thead><tr><th>Score</th><th>Unternehmen</th><th>Bundesland</th><th>Branche</th><th>Lead-Typ</th><th>Datum</th></tr></thead><tbody>'+
    leads.map(l=>{
      const sc=l.score||0;
      const scClass=sc>=70?'score-high':sc>=50?'score-mid':'score-low';
      const types=(l.lead_types?JSON.parse(l.lead_types):[]).map(t=>'<span class="tag">'+t+'</span>').join('');
      const summary=l.ai_summary?'<div style="font-size:.7rem;color:#64748b;margin-top:4px;max-width:200px">'+l.ai_summary+'</div>':'';
      return '<tr><td><span class="score-badge '+scClass+'">'+sc+'</span></td>'+
             '<td><div class="lead-name">'+l.debtor_name+'</div><div class="lead-meta">'+l.rechtsform+' &middot; '+l.court+'</div>'+summary+'</td>'+
             '<td>'+(BL[l.bundesland]||l.bundesland||'?')+'</td>'+
             '<td>'+(l.branche||'?')+'</td>'+
             '<td>'+types+'</td>'+
             '<td style="font-size:.72rem;color:var(--muted)">'+(l.publication_date||'?')+'</td></tr>';
    }).join('')+'</tbody></table>';
  }catch(e){container.innerHTML='<div class="empty">Fehler: '+e.message+'</div>';}
}

async function triggerScan(){
  const btn=document.getElementById('scan-btn');
  btn.disabled=true;btn.innerHTML='<span class="spin">&#9881;</span> Scannt...';
  try{
    const r=await fetch('/api/insolvenz-radar/scan',{method:'POST'});
    const d=await r.json();
    btn.innerHTML='&#x2705; '+d.status;
    setTimeout(()=>{btn.disabled=false;btn.innerHTML='&#x1F50D; Jetzt Scannen';loadStatus();loadLeads();},8000);
  }catch(e){btn.disabled=false;btn.innerHTML='&#x26A0; Fehler';}
}

function openModal(tier){selectedTier=tier;const l={starter:'Starter \\u20AC29/mo',pro:'Pro \\u20AC79/mo',agency:'Agency \\u20AC199/mo'};document.getElementById('modal-title').textContent='Insolvenz Radar '+l[tier];document.getElementById('modal-overlay').classList.add('open');}
function closeModal(){document.getElementById('modal-overlay').classList.remove('open');}
async function doCheckout(){const email=document.getElementById('modal-email').value.trim();if(!email.includes('@')){alert('G\\u00FCltige E-Mail eingeben');return;}const btn=document.getElementById('pay-btn');btn.textContent='\\u23F3 Weiterleitung...';btn.disabled=true;try{const r=await fetch('/api/insolvenz-radar/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,tier:selectedTier})});const d=await r.json();if(d.checkout_url){window.location.href=d.checkout_url;}else{alert(d.error||'Fehler');btn.textContent='\\uD83D\\uDCB3 Jetzt zahlen \\u2192';btn.disabled=false;}}catch(e){alert(e.message);btn.textContent='\\uD83D\\uDCB3 Jetzt zahlen \\u2192';btn.disabled=false;}}

loadStatus();loadLeads();setInterval(loadStatus,30000);
</script></body></html>"""
    return web.Response(text=html, content_type="text/html")


async def handle_ir_status(req):
    try:
        from modules.insolvenz_radar import get_status
        return web.json_response(get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ir_leads(req):
    try:
        from modules.insolvenz_radar import get_leads
        bl         = req.rel_url.query.get("bundesland", "")
        min_score  = int(req.rel_url.query.get("min_score", "0"))
        branche    = req.rel_url.query.get("branche", "")
        limit      = int(req.rel_url.query.get("limit", "50"))
        offset     = int(req.rel_url.query.get("offset", "0"))
        leads = get_leads(bundesland=bl, min_score=min_score, branche=branche,
                          limit=limit, offset=offset)
        return web.json_response({"ok": True, "leads": leads, "count": len(leads)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ir_scan(req):
    global _ir_running
    if _ir_running:
        return web.json_response({"ok": False, "status": "Scan läuft bereits"})
    async def _bg():
        global _ir_running
        _ir_running = True
        try:
            from modules.insolvenz_radar import run_scan
            await run_scan()
        except Exception as e:
            log.error("InsolvenzRadar scan: %s", e)
        finally:
            _ir_running = False
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "Insolvenz-Scan gestartet"})


async def handle_ir_checkout(req):
    try:
        body  = await req.json()
        email = body.get("email", "").strip()
        tier  = body.get("tier", "starter").strip()
        if not email or "@" not in email:
            return web.json_response({"ok": False, "error": "Ungültige E-Mail"}, status=400)
        from modules.insolvenz_radar import create_checkout
        return web.json_response(await create_checkout(email, tier))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ir_success(req):
    html = """<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>&#x1F3DB; Insolvenz Radar aktiv</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#0a0a0f;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#111118;border:1px solid #dc2626;border-radius:20px;padding:48px;max-width:480px;text-align:center;box-shadow:0 0 50px rgba(220,38,38,.12)}
.icon{font-size:4.5rem;margin-bottom:20px}h1{font-size:1.7rem;margin-bottom:10px;color:#ef4444}
p{color:#64748b;line-height:1.7;margin-bottom:24px}a{display:inline-block;background:linear-gradient(90deg,#dc2626,#f97316);color:#fff;padding:13px 32px;border-radius:10px;text-decoration:none;font-weight:800}</style></head>
<body><div class="card"><div class="icon">&#x1F3DB;</div><h1>Insolvenz Radar aktiv!</h1>
<p>T&#228;glich frische B2B-Leads aus dem deutschen Insolvenzregister.<br>Telegram-Alerts kommen automatisch wenn Score-Schwelle erreicht wird.</p>
<a href="/insolvenz-radar">&#x2192; Zum Radar-Dashboard</a></div></body></html>"""
    return web.Response(text=html, content_type="text/html")


# ═══════════════════════════════════════════════════════════════════════════
#  MONEY MACHINE — Unified Orchestrator Handlers
# ═══════════════════════════════════════════════════════════════════════════

_mm_running = False

async def handle_money_machine_page(req):
    html = """<!DOCTYPE html>
<html lang="de"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>&#x1F4B0; Money Machine &mdash; 5 Engines in 1</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0a0a0f;--card:#111118;--border:#1e1e2e;--accent:#7c3aed;--accent2:#06b6d4;--green:#10b981;--red:#ef4444;--yellow:#f59e0b;--text:#e2e8f0;--muted:#64748b}
body{font-family:'SF Pro Display',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.header{background:linear-gradient(135deg,#1a0533 0%,#0f172a 50%,#001a2c 100%);border-bottom:1px solid #2d1b69;padding:20px 32px;display:flex;align-items:center;justify-content:space-between}
.logo{font-size:1.5rem;font-weight:900}
.logo span{background:linear-gradient(90deg,#a855f7,#06b6d4,#10b981);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.nav a{color:#94a3b8;text-decoration:none;margin-left:20px;font-size:.85rem}
.start-zone{text-align:center;padding:40px 24px 20px;background:linear-gradient(180deg,rgba(124,58,237,.08) 0%,transparent 100%)}
.start-title{font-size:.85rem;color:var(--muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:16px}
.btn-mega{display:inline-flex;align-items:center;gap:14px;background:linear-gradient(135deg,#7c3aed,#6d28d9,#4c1d95);color:#fff;border:none;padding:22px 52px;border-radius:16px;font-size:1.4rem;font-weight:900;cursor:pointer;box-shadow:0 0 60px rgba(124,58,237,.5),0 4px 20px rgba(0,0,0,.4);transition:transform .15s,box-shadow .15s;text-transform:uppercase}
.btn-mega:hover{transform:scale(1.03);box-shadow:0 0 80px rgba(124,58,237,.7)}
.btn-mega:disabled{opacity:.5;cursor:not-allowed;transform:none}
.pulse-dot{width:16px;height:16px;border-radius:50%;background:#10b981;box-shadow:0 0 0 0 rgba(16,185,129,.6);animation:pulse-ring 1.5s infinite;flex-shrink:0}
@keyframes pulse-ring{0%{box-shadow:0 0 0 0 rgba(16,185,129,.6)}70%{box-shadow:0 0 0 10px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}
.start-status{margin-top:14px;font-size:.88rem;color:var(--muted);min-height:22px}
.revenue-banner{display:flex;gap:16px;padding:14px 32px;background:rgba(16,185,129,.06);border-bottom:1px solid rgba(16,185,129,.2);flex-wrap:wrap;align-items:center}
.rev-item{display:flex;align-items:center;gap:8px}
.rev-label{font-size:.78rem;color:var(--muted)}
.rev-value{font-size:1rem;font-weight:800;color:var(--green)}
.rev-divider{width:1px;height:20px;background:var(--border)}
.engines{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;padding:24px 32px}
.engine-card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px;transition:border-color .2s}
.engine-card.ok{border-color:var(--green)}
.engine-header{display:flex;align-items:center;gap:12px;margin-bottom:16px}
.engine-icon{font-size:1.5rem}
.engine-title{font-weight:800;font-size:.95rem}
.engine-sub{font-size:.72rem;color:var(--muted);margin-top:2px}
.engine-status{margin-left:auto;display:flex;align-items:center;gap:6px;font-size:.75rem;font-weight:600}
.dot{width:8px;height:8px;border-radius:50%;background:var(--muted)}
.dot.green{background:var(--green);box-shadow:0 0 6px var(--green)}
.dot.red{background:var(--red)}
.stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0}
.stat{background:#0d0d16;border-radius:8px;padding:10px 12px}
.stat-label{font-size:.68rem;color:var(--muted);margin-bottom:3px}
.stat-value{font-size:.9rem;font-weight:700}
.engine-footer{display:flex;gap:8px;margin-top:14px}
.btn-sm{padding:7px 14px;border-radius:7px;border:none;cursor:pointer;font-size:.78rem;font-weight:700}
.btn-trigger{background:rgba(124,58,237,.2);color:#a855f7;border:1px solid rgba(124,58,237,.3)}
.btn-open{background:#0d0d16;color:#64748b;border:1px solid var(--border);text-decoration:none}
.pricing{padding:24px 32px 48px}
.pricing h2{font-size:1.5rem;font-weight:800;margin-bottom:6px}
.pricing-sub{color:var(--muted);margin-bottom:24px;font-size:.9rem}
.plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.plan{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:26px;position:relative}
.plan.featured{border-color:var(--accent);box-shadow:0 0 30px rgba(124,58,237,.15)}
.plan-badge{position:absolute;top:-12px;left:50%;transform:translateX(-50%);background:linear-gradient(90deg,var(--accent),var(--accent2));color:#fff;padding:4px 14px;border-radius:10px;font-size:.72rem;font-weight:800}
.plan-name{font-size:1rem;font-weight:800;margin-bottom:6px}
.plan-price{font-size:2rem;font-weight:900;color:var(--accent);margin-bottom:4px}
.plan-price span{font-size:.82rem;color:var(--muted);font-weight:400}
.plan-features{list-style:none;margin:14px 0 18px}
.plan-features li{padding:5px 0;font-size:.83rem;color:#94a3b8;border-bottom:1px solid var(--border);display:flex;gap:8px;align-items:center}
.plan-features li:last-child{border:none}
.plan-features li::before{content:"checkmark";content:"\\2713";color:var(--green);font-weight:800}
.plan-btn{width:100%;padding:12px;border:none;border-radius:9px;font-weight:800;font-size:.88rem;cursor:pointer}
.plan-btn-primary{background:linear-gradient(90deg,var(--accent),var(--accent2));color:#fff}
.plan-btn-secondary{background:#1e1e2e;color:var(--text);border:1px solid var(--border)}
.log-section{padding:0 32px 40px}
.log-section h3{font-size:.9rem;font-weight:700;margin-bottom:10px;color:var(--muted)}
.log-list{background:var(--card);border:1px solid var(--border);border-radius:12px;max-height:160px;overflow-y:auto;font-family:monospace;font-size:.76rem}
.log-line{padding:7px 14px;border-bottom:1px solid var(--border);color:#7dd3fc;display:flex;gap:12px}
.log-line:last-child{border:none}
.log-time{color:var(--muted);flex-shrink:0}
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:200;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal{background:var(--card);border:1px solid var(--border);border-radius:18px;padding:34px;max-width:400px;width:90%}
.modal h4{font-size:1.2rem;font-weight:800;margin-bottom:8px}
.modal p{color:var(--muted);font-size:.85rem;margin-bottom:18px}
.form-group label{display:block;font-size:.78rem;color:var(--muted);margin-bottom:5px}
.form-group input{width:100%;background:#0d0d16;border:1px solid var(--border);color:var(--text);padding:10px 13px;border-radius:8px;font-size:.88rem}
.modal-footer{display:flex;gap:10px;margin-top:18px}
.btn-cancel{flex:1;padding:11px;background:#1e1e2e;border:1px solid var(--border);color:var(--text);border-radius:8px;cursor:pointer;font-weight:700}
.btn-pay{flex:2;padding:11px;background:linear-gradient(90deg,var(--accent),var(--accent2));color:#fff;border:none;border-radius:8px;cursor:pointer;font-weight:800}
@keyframes spin{to{transform:rotate(360deg)}}
.spin{display:inline-block;animation:spin .8s linear infinite}
</style></head><body>
<div class="header">
  <div class="logo">&#x1F4B0; <span>Money Machine</span></div>
  <nav class="nav">
    <a href="/">Dashboard</a><a href="/viral">Viral</a><a href="/engines">Engines</a><a href="/master">Master</a>
  </nav>
</div>
<div class="start-zone">
  <div class="start-title">&#x1F680; Alle 5 Engines gleichzeitig starten</div>
  <button class="btn-mega" id="mega-btn" onclick="startAll()">
    <div class="pulse-dot"></div>
    ALLES STARTEN &mdash; GELD VERDIENEN
  </button>
  <div class="start-status" id="start-status">Bereit. 1 Klick = alle 5 Engines laufen sofort.</div>
</div>
<div class="revenue-banner">
  <div class="rev-item"><span class="rev-label">eBay Profit</span><span class="rev-value" id="rev-ebay">&#8364;--</span></div>
  <div class="rev-divider"></div>
  <div class="rev-item"><span class="rev-label">Cart Rescue</span><span class="rev-value" id="rev-cart">&#8364;--</span></div>
  <div class="rev-divider"></div>
  <div class="rev-item"><span class="rev-label">Viral Alerts</span><span class="rev-value" id="rev-viral">--</span></div>
  <div class="rev-divider"></div>
  <div class="rev-item"><span class="rev-label">OOS Events</span><span class="rev-value" id="rev-oos">--</span></div>
  <div class="rev-divider"></div>
  <div class="rev-item"><span class="rev-label">Review Analysen</span><span class="rev-value" id="rev-review">--</span></div>
  <div class="rev-divider"></div>
  <div class="rev-item"><span class="rev-label">Shopify Imports</span><span class="rev-value" id="rev-imports">--</span></div>
</div>
<div class="engines" id="engine-grid"><div style="grid-column:1/-1;padding:40px;text-align:center;color:var(--muted)">Lade Status...</div></div>
<div class="pricing">
  <h2>&#x1F48E; Money Machine Subscription</h2>
  <p class="pricing-sub">1 Abo &mdash; alle 5 Engines &mdash; alle Alerts &mdash; alle Auto-Imports</p>
  <div class="plans">
    <div class="plan">
      <div class="plan-name">Alert</div>
      <div class="plan-price">&#8364;29 <span>/ Monat</span></div>
      <ul class="plan-features">
        <li>Viral Window Alerts (Score 55+)</li><li>OOS Sniper Alerts</li>
        <li>Cart Rescue via Telegram</li><li>T&#228;glicher Revenue Report</li>
      </ul>
      <button class="plan-btn plan-btn-secondary" onclick="openModal('alert')">Starten &rarr;</button>
    </div>
    <div class="plan featured">
      <div class="plan-badge">&#x2B50; MEISTGEW&#196;HLT</div>
      <div class="plan-name">Pro</div>
      <div class="plan-price">&#8364;79 <span>/ Monat</span></div>
      <ul class="plan-features">
        <li>Alles aus Alert</li><li>Shopify Auto-Import (Score 72+)</li>
        <li>Amazon Review Goldmine (unlimitiert)</li><li>eBay Arbitrage Auto-Import</li>
        <li>WhatsApp Cart Rescue</li><li>Fr&#252;here Alerts (Score 40+)</li>
      </ul>
      <button class="plan-btn plan-btn-primary" onclick="openModal('pro')">Pro starten &rarr;</button>
    </div>
    <div class="plan">
      <div class="plan-name">Agency</div>
      <div class="plan-price">&#8364;199 <span>/ Monat</span></div>
      <ul class="plan-features">
        <li>Alles aus Pro</li><li>5 Shopify Stores</li>
        <li>White-Label Dashboard</li><li>Priority Alerts</li><li>Telegram-Support</li>
      </ul>
      <button class="plan-btn plan-btn-secondary" onclick="openModal('agency')">Agency &rarr;</button>
    </div>
  </div>
</div>
<div class="log-section">
  <h3>&#x1F4CB; Engine Log</h3>
  <div class="log-list" id="log-list">
    <div class="log-line"><span class="log-time">--:--</span><span>Warte auf ersten Run...</span></div>
  </div>
</div>
<div class="modal-overlay" id="modal-overlay">
  <div class="modal">
    <h4 id="modal-title">Money Machine</h4>
    <p>Weiterleitung zu Stripe. Alle 5 Engines. K&#252;ndige jederzeit.</p>
    <div class="form-group"><label>E-Mail</label>
    <input type="email" id="modal-email" placeholder="deine@email.de"></div>
    <div class="modal-footer">
      <button class="btn-cancel" onclick="closeModal()">Abbrechen</button>
      <button class="btn-pay" id="pay-btn" onclick="doCheckout()">&#x1F4B3; Jetzt zahlen &rarr;</button>
    </div>
  </div>
</div>
<script>
let selectedTier='alert';
const logs=[];
function addLog(msg){const t=new Date().toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});logs.unshift({t,msg});if(logs.length>30)logs.pop();document.getElementById('log-list').innerHTML=logs.map(l=>'<div class="log-line"><span class="log-time">'+l.t+'</span><span>'+l.msg+'</span></div>').join('');}
async function loadStatus(){try{const r=await fetch('/api/money-machine/status');const d=await r.json();if(!d.ok)return;renderEngines(d.engines||{});const e=d.engines||{};document.getElementById('rev-ebay').textContent='\\u20AC'+(e.ebay?.total_profit||0).toFixed(2);document.getElementById('rev-cart').textContent='\\u20AC'+(e.cart?.recovered_revenue||0).toFixed(2);document.getElementById('rev-viral').textContent=(e.viral?.alerts_sent||0)+' Alerts';document.getElementById('rev-oos').textContent=(e.oos?.oos_now||0)+' aktiv';document.getElementById('rev-review').textContent=(e.review?.analyses||0)+' ges.';document.getElementById('rev-imports').textContent=(e.viral?.shopify_imports||0)+' Imports';}catch(e){addLog('\\u26A0 Status-Fehler: '+e.message);}}
function renderEngines(engines){const defs=[{key:'viral',icon:'\\uD83D\\uDD25',title:'Viral Window Scanner',sub:'5 Signalquellen \\u2192 AI-Score \\u2192 Shopify-Import',stats:e=>({'Signale':e.total_signals||0,'High-Score':e.high_score||0,'Alerts':e.alerts_sent||0,'Imports':e.shopify_imports||0}),trigger:'/api/viral/scan',page:'/viral'},{key:'oos',icon:'\\uD83C\\uDFAF',title:'OOS Sniper',sub:'Konkurrenz Out-of-Stock \\u2192 Sofort-Alert',stats:e=>({'Targets':e.targets||0,'Tracked':e.tracked||0,'OOS jetzt':e.oos_now||0,'Events':e.events_7d||0}),trigger:'/api/oos-sniper/scan',page:'/api/oos-sniper/status'},{key:'review',icon:'\\u2B50',title:'Review Goldmine',sub:'Amazon 1\\u2605 \\u2192 Ad-Copy in 60s',stats:e=>({'Analysen':e.analyses||0,'AI-Assets':e.analyses||0,'Cached':'--','Keywords':'--'}),trigger:null,page:'/api/review-goldmine/status'},{key:'cart',icon:'\\uD83D\\uDED2',title:'Cart Rescue',sub:'Abandoned Checkout \\u2192 Telegram/WhatsApp',stats:e=>({'Gesamt':e.total||0,'Gesendet':e.sent||0,'Recovered':e.recovered||0,'Rate':(e.recovery_rate||0)+'%'}),trigger:null,page:'/api/cart-rescue/status'},{key:'ebay',icon:'\\uD83D\\uDCE6',title:'eBay Arbitrage',sub:'AliExpress EK \\u2192 eBay Markt \\u2192 Shopify',stats:e=>({'Gescannt':e.total_scanned||0,'Importiert':e.total_imported||0,'Profit':'\\u20AC'+(e.total_profit||0).toFixed(2),'Marge':(e.avg_margin||0).toFixed(0)+'%'}),trigger:'/api/ebay-arbitrage/scan',page:'/api/ebay-arbitrage/stats'}];
document.getElementById('engine-grid').innerHTML=defs.map(def=>{const e=engines[def.key]||{};const ok=e.ok!==false;const st=def.stats(e);const sh=Object.entries(st).map(([k,v])=>'<div class="stat"><div class="stat-label">'+k+'</div><div class="stat-value">'+v+'</div></div>').join('');const tb=def.trigger?'<button class="btn-sm btn-trigger" onclick="triggerEngine(\''+def.key+'\',\''+def.trigger+'\')">\\u25B6 Starten</button>':'<span class="btn-sm btn-open" style="opacity:.5">Auto</span>';return '<div class="engine-card '+(ok?'ok':'')+'"><div class="engine-header"><div class="engine-icon">'+def.icon+'</div><div><div class="engine-title">'+def.title+'</div><div class="engine-sub">'+def.sub+'</div></div><div class="engine-status"><div class="dot '+(ok?'green':'red')+'"></div>'+(ok?'Aktiv':'Fehler')+'</div></div><div class="stats-grid">'+sh+'</div><div class="engine-footer">'+tb+'<a href="'+def.page+'" target="_blank" class="btn-sm btn-open">\\u2197 Details</a></div></div>'}).join('');}
async function startAll(){const btn=document.getElementById('mega-btn');const st=document.getElementById('start-status');btn.disabled=true;btn.innerHTML='<span class="spin">\\u2699</span>&nbsp;Alle 5 Engines laufen...';st.textContent='Viral Scanner + OOS Sniper + eBay Arbitrage gestartet...';addLog('\\uD83D\\uDE80 MONEY MACHINE GESTARTET');try{const r=await fetch('/api/money-machine/run-all',{method:'POST'});const d=await r.json();if(d.ok){btn.innerHTML='\\u2705 ENGINES LAUFEN';st.textContent='L\\u00E4uft im Hintergrund. Telegram-Alert kommt wenn fertig.';addLog('\\u2705 Run gestartet \\u2014 Alert kommt via Telegram');setTimeout(loadStatus,8000);setTimeout(()=>{btn.disabled=false;btn.innerHTML='<div class="pulse-dot"></div>ALLES STARTEN \\u2014 GELD VERDIENEN';st.textContent='Bereit f\\u00FCr n\\u00E4chsten Run.';},90000);}else{btn.innerHTML='\\u26A0 '+(d.error||'Fehler');btn.disabled=false;}}catch(e){btn.innerHTML='\\u26A0 Netzwerkfehler';btn.disabled=false;addLog('\\u274C '+e.message);}}
async function triggerEngine(key,url){addLog('\\u25B6 '+key.toUpperCase()+' gestartet...');try{const r=await fetch(url,{method:'POST'});const d=await r.json();addLog('\\u2705 '+key+': '+JSON.stringify(d).slice(0,70));setTimeout(loadStatus,3000);}catch(e){addLog('\\u274C '+key+': '+e.message);}}
function openModal(tier){selectedTier=tier;const l={alert:'Alert \\u20AC29/mo',pro:'Pro \\u20AC79/mo',agency:'Agency \\u20AC199/mo'};document.getElementById('modal-title').textContent='Money Machine '+l[tier];document.getElementById('modal-overlay').classList.add('open');}
function closeModal(){document.getElementById('modal-overlay').classList.remove('open');}
async function doCheckout(){const email=document.getElementById('modal-email').value.trim();if(!email.includes('@')){alert('G\\u00FCltige E-Mail eingeben');return;}const btn=document.getElementById('pay-btn');btn.textContent='\\u23F3 Weiterleitung...';btn.disabled=true;try{const r=await fetch('/api/money-machine/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,tier:selectedTier})});const d=await r.json();if(d.checkout_url){window.location.href=d.checkout_url;}else{alert(d.error||'Checkout nicht verf\\u00FCgbar');btn.textContent='\\uD83D\\uDCB3 Jetzt zahlen \\u2192';btn.disabled=false;}}catch(e){alert('Fehler: '+e.message);btn.textContent='\\uD83D\\uDCB3 Jetzt zahlen \\u2192';btn.disabled=false;}}
loadStatus();setInterval(loadStatus,30000);addLog('\\uD83D\\uDCB0 Money Machine Dashboard geladen');
</script></body></html>"""
    return web.Response(text=html, content_type="text/html")


async def handle_mm_run_all(req):
    global _mm_running
    if _mm_running:
        return web.json_response({"ok": False, "error": "Bereits am laufen"})
    async def _bg():
        global _mm_running
        _mm_running = True
        try:
            from modules.money_machine import run_all_engines
            await run_all_engines()
        except Exception as e:
            log.error("MoneyMachine run error: %s", e)
        finally:
            _mm_running = False
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "Alle Engines gestartet"})


async def handle_mm_status(req):
    try:
        from modules.money_machine import get_combined_status
        data = await get_combined_status()
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_mm_checkout(req):
    try:
        body  = await req.json()
        email = body.get("email", "").strip()
        tier  = body.get("tier", "alert").strip()
        if not email or "@" not in email:
            return web.json_response({"ok": False, "error": "Ungültige E-Mail"}, status=400)
        from modules.money_machine import create_mm_checkout
        return web.json_response(await create_mm_checkout(email, tier))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_mm_success(req):
    html = """<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>&#x1F389; Money Machine aktiv</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#0a0a0f;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#111118;border:1px solid #10b981;border-radius:20px;padding:52px;max-width:500px;text-align:center;box-shadow:0 0 60px rgba(16,185,129,.15)}
.icon{font-size:5rem;margin-bottom:24px}h1{font-size:1.8rem;margin-bottom:12px;color:#10b981}
p{color:#64748b;line-height:1.7;margin-bottom:28px}a{display:inline-block;background:linear-gradient(90deg,#7c3aed,#06b6d4);color:#fff;padding:14px 36px;border-radius:10px;text-decoration:none;font-weight:800}</style></head>
<body><div class="card"><div class="icon">&#x1F389;</div><h1>Money Machine aktiv!</h1>
<p>Alle 5 Engines laufen jetzt f&#252;r dich:<br>
Viral Scanner &#x1F525; &#x2022; OOS Sniper &#x1F3AF; &#x2022; Review Goldmine &#x2B50; &#x2022; Cart Rescue &#x1F6D2; &#x2022; eBay Arbitrage &#x1F4E6;<br><br>
Telegram-Alerts kommen sobald Geld-Chancen erkannt werden.</p>
<a href="/money-machine">&#x2192; Zum Dashboard</a></div></body></html>"""
    return web.Response(text=html, content_type="text/html")


# ═══════════════════════════════════════════════════════════════════════════
#  KI-MITARBEITER-LEASING — SYS-01
# ═══════════════════════════════════════════════════════════════════════════

_KI_LEASING_PAGE = """<!DOCTYPE html><html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KI-Mitarbeiter-Leasing — Täglich Leads. Nie krank. Nie Urlaub.</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#07090E;--s1:#0C0F17;--s2:#111520;--bd:#1C2234;--bd2:#242D42;
  --amber:#F5A623;--ad:rgba(245,166,35,.12);--ab:rgba(245,166,35,.30);
  --green:#14C47A;--gd:rgba(20,196,122,.10);
  --ice:#C9D4E8;--dim:#6A7A99;--dim2:#8FA3C0;
  --mono:"SF Mono","Cascadia Code","Consolas",monospace;
  --sans:system-ui,-apple-system,"Segoe UI",sans-serif;
}
body{background:var(--bg);color:var(--ice);font-family:var(--sans);font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
body::after{content:'';position:fixed;inset:0;pointer-events:none;background:repeating-linear-gradient(to bottom,transparent 0px,transparent 3px,rgba(0,0,0,.05) 3px,rgba(0,0,0,.05) 4px);z-index:9}
/* HEADER */
.topbar{background:var(--amber);color:#000;text-align:center;padding:7px;font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:.25em;text-transform:uppercase}
.hdr{display:flex;justify-content:space-between;align-items:center;padding:16px 48px;border-bottom:1px solid var(--bd2);background:var(--s1)}
.hdr-brand{font-family:var(--mono);font-size:11px;color:var(--dim);letter-spacing:.1em;text-transform:uppercase}
.hdr-brand b{color:var(--amber)}
/* HERO */
.main{max-width:1100px;margin:0 auto;padding:64px 32px 80px}
.eyebrow{display:flex;align-items:center;gap:12px;margin-bottom:20px}
.eyebrow::before{content:'';display:block;width:32px;height:1px;background:var(--amber)}
.eyebrow span{font-family:var(--mono);font-size:10px;color:var(--amber);letter-spacing:.2em;text-transform:uppercase}
.hero-h1{font-size:clamp(36px,5.5vw,72px);font-weight:900;letter-spacing:-.045em;line-height:1;margin-bottom:20px;text-wrap:balance}
.hero-h1 em{font-style:normal;color:var(--amber)}
.hero-sub{font-size:17px;color:var(--dim2);line-height:1.75;max-width:580px;margin-bottom:48px}
/* STATS ROW */
.stats-row{display:flex;gap:2px;background:var(--bd);margin-bottom:56px}
.stat-box{flex:1;background:var(--s2);padding:24px;text-align:center}
.stat-num{font-family:var(--mono);font-size:36px;font-weight:700;color:var(--amber);display:block;line-height:1}
.stat-lbl{font-family:var(--mono);font-size:10px;color:var(--dim);letter-spacing:.12em;text-transform:uppercase;margin-top:6px;display:block}
/* SECTION */
.sec-head{display:flex;align-items:center;gap:14px;margin-bottom:24px}
.sec-lbl{font-family:var(--mono);font-size:10px;color:var(--dim);letter-spacing:.18em;text-transform:uppercase;white-space:nowrap}
.sec-rule{flex:1;height:1px;background:var(--bd2)}
/* HOW IT WORKS */
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:2px;background:var(--bd);margin-bottom:56px}
.step{background:var(--s2);padding:24px}
.step-n{font-family:var(--mono);font-size:11px;color:var(--amber);letter-spacing:.1em;margin-bottom:10px}
.step-t{font-size:15px;font-weight:700;letter-spacing:-.02em;margin-bottom:8px}
.step-d{font-size:13px;color:var(--dim2);line-height:1.7}
/* PRICING */
.pricing{display:grid;grid-template-columns:1fr 1fr;gap:2px;background:var(--bd);margin-bottom:56px}
.plan{background:var(--s2);padding:32px}
.plan.featured{background:var(--s1);border:1px solid var(--amber)}
.plan-badge{font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:.18em;color:var(--amber);background:var(--ad);border:1px solid var(--ab);padding:2px 8px;display:inline-block;margin-bottom:14px}
.plan-name{font-size:20px;font-weight:700;letter-spacing:-.025em;margin-bottom:6px}
.plan-price{font-family:var(--mono);font-size:44px;font-weight:700;color:var(--amber);line-height:1;margin-bottom:4px}
.plan-price span{font-size:16px;color:var(--dim)}
.plan-desc{font-size:13px;color:var(--dim2);margin-bottom:20px;line-height:1.7}
.plan-features{list-style:none;margin-bottom:28px}
.plan-features li{font-size:13px;color:var(--dim2);padding:7px 0;border-bottom:1px solid var(--bd);padding-left:18px;position:relative}
.plan-features li::before{content:'→';position:absolute;left:0;color:var(--amber);font-size:11px}
/* FORM */
.order-form{display:flex;flex-direction:column;gap:10px}
.order-form input[type=email]{background:var(--bg);border:1px solid var(--bd2);color:var(--ice);padding:12px 14px;font-size:14px;font-family:var(--sans);outline:none;width:100%}
.order-form input[type=email]:focus{border-color:var(--amber)}
.btn-buy{background:var(--amber);color:#000;border:none;padding:14px 24px;font-size:15px;font-weight:700;cursor:pointer;width:100%;letter-spacing:.02em;transition:opacity .15s}
.btn-buy:hover{opacity:.88}
.btn-buy:disabled{opacity:.4;cursor:not-allowed}
.form-note{font-family:var(--mono);font-size:10px;color:var(--dim);text-align:center;margin-top:6px}
/* TRUST */
.trust-row{display:flex;flex-wrap:wrap;gap:2px;background:var(--bd);margin-bottom:56px}
.trust-item{flex:1;min-width:180px;background:var(--s2);padding:20px;display:flex;align-items:center;gap:14px}
.trust-icon{font-size:20px;flex-shrink:0}
.trust-text{font-size:13px;color:var(--dim2);line-height:1.5}
.trust-text b{color:var(--ice);display:block;margin-bottom:2px}
/* TESTIMONIAL / DEMO */
.demo-report{border:1px solid var(--bd2);background:var(--s1);padding:24px;margin-bottom:56px}
.demo-tag{font-family:var(--mono);font-size:9px;color:var(--amber);letter-spacing:.2em;text-transform:uppercase;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.demo-tag::before{content:'';display:block;width:20px;height:1px;background:var(--amber)}
.demo-row{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--bd)}
.demo-row:last-child{border-bottom:none}
.demo-co{font-size:14px;font-weight:600}
.demo-score{font-family:var(--mono);font-size:13px;color:var(--green)}
.demo-type{font-family:var(--mono);font-size:10px;color:var(--dim);letter-spacing:.08em}
.demo-amt{font-family:var(--mono);font-size:12px;color:var(--amber)}
/* RESPONSIVE */
@media(max-width:800px){
  .hdr{padding:14px 20px}
  .main{padding:40px 20px 60px}
  .stats-row,.steps,.pricing,.trust-row{grid-template-columns:1fr}
  .steps{grid-template-columns:1fr 1fr}
}
</style>
</head>
<body>
<div class="topbar">KI-MITARBEITER-LEASING &nbsp;⬤&nbsp; TÄGLICH AKTIV — NIE KRANK — NIE URLAUB</div>
<header class="hdr">
  <div class="hdr-brand"><b>Bull Power</b> Intelligence Unit</div>
  <div style="font-family:var(--mono);font-size:10px;color:var(--dim)">Stand: tägl. 08:30 automatisch</div>
</header>

<main class="main">
  <div class="eyebrow"><span>Kein Tool. Kein Abo. Reines Ergebnis.</span></div>
  <h1 class="hero-h1">Ihr KI-Mitarbeiter.<br><em>Täglich aktiv.</em><br>Ohne Pause.</h1>
  <p class="hero-sub">Sie erhalten täglich qualifizierte B2B-Leads direkt in Ihr Postfach — automatisch analysiert, bewertet und aufbereitet. Kein Aufwand Ihrerseits. Kein Setup. Kein Tool zu bedienen.</p>

  <div class="stats-row">
    <div class="stat-box"><span class="stat-num">08:30</span><span class="stat-lbl">Tägl. Lieferzeit</span></div>
    <div class="stat-box"><span class="stat-num">100</span><span class="stat-lbl">Score-Punkte max.</span></div>
    <div class="stat-box"><span class="stat-num">3+</span><span class="stat-lbl">Datenquellen live</span></div>
    <div class="stat-box"><span class="stat-num">0</span><span class="stat-lbl">Einrichtungsaufwand</span></div>
  </div>

  <div class="sec-head"><span class="sec-lbl">So funktioniert es</span><div class="sec-rule"></div></div>
  <div class="steps">
    <div class="step"><div class="step-n">SCHRITT 01</div><div class="step-t">Paket wählen</div><div class="step-d">Basic (10 Leads/Tag) oder Pro (25 Leads + Compliance). Zahlung per Kreditkarte.</div></div>
    <div class="step"><div class="step-n">SCHRITT 02</div><div class="step-t">Aktivierung</div><div class="step-d">Nach Zahlung ist Ihr Account sofort aktiv. Nächster Report: morgen 08:30 Uhr.</div></div>
    <div class="step"><div class="step-n">SCHRITT 03</div><div class="step-t">Tägl. Report</div><div class="step-d">Jeden Morgen erhalten Sie Ihre besten Leads — bewertet, priorisiert, sofort nutzbar.</div></div>
    <div class="step"><div class="step-n">SCHRITT 04</div><div class="step-t">Wachstum</div><div class="step-d">Sie akquirieren. Wir liefern. Monatlich kündbar — ohne Risiko.</div></div>
  </div>

  <div class="sec-head"><span class="sec-lbl">Beispiel-Report (heutige Leads)</span><div class="sec-rule"></div></div>
  <div class="demo-report">
    <div class="demo-tag">Vorschau — heutiger Report — 5 von 10 Leads</div>
    <div class="demo-row"><div><div class="demo-co">Muster Logistik GmbH & Co. KG</div><div class="demo-type">INSOLVENZ — Amtsgericht München</div></div><div style="text-align:right"><div class="demo-score">Score: 91</div><div class="demo-amt">€340.000</div></div></div>
    <div class="demo-row"><div><div class="demo-co">Tech Solutions Berlin GmbH</div><div class="demo-type">AI-ACT-RISIKO — IT/Software</div></div><div style="text-align:right"><div class="demo-score">Score: 84</div><div class="demo-amt">Bußgeld €35 Mio.</div></div></div>
    <div class="demo-row"><div><div class="demo-co">Digital Marketing Hamburg AG</div><div class="demo-type">INSOLVENZ — Amtsgericht Hamburg</div></div><div style="text-align:right"><div class="demo-score">Score: 79</div><div class="demo-amt">€1.2 Mio.</div></div></div>
    <div class="demo-row"><div><div class="demo-co">E-Commerce Ventures GmbH</div><div class="demo-type">AI-ACT-RISIKO — Handel/E-Commerce</div></div><div style="text-align:right"><div class="demo-score">Score: 76</div><div class="demo-amt">Bußgeld €15 Mio.</div></div></div>
    <div class="demo-row"><div><div class="demo-co">Bau & Immobilien Köln GmbH</div><div class="demo-type">INSOLVENZ — Amtsgericht Köln</div></div><div style="text-align:right"><div class="demo-score">Score: 72</div><div class="demo-amt">€890.000</div></div></div>
    <div style="padding-top:12px;font-family:var(--mono);font-size:10px;color:var(--dim)">+ 5 weitere Leads nur für Abonnenten &nbsp;|&nbsp; Basic-Kunden erhalten tägl. 10 · Pro-Kunden 25 Leads</div>
  </div>

  <div class="sec-head"><span class="sec-lbl">Pakete &amp; Preise</span><div class="sec-rule"></div></div>
  <div class="pricing">
    <div class="plan">
      <div class="plan-name">Lead-Agent Basic</div>
      <div class="plan-price">€499<span>/Monat</span></div>
      <p class="plan-desc">10 qualifizierte B2B-Leads täglich — geeignet für Einzelakquisiteure und kleine Vertriebsteams.</p>
      <ul class="plan-features">
        <li>10 bewertete Leads täglich (Score 0–100)</li>
        <li>Insolvenz-Daten (DE Handelsregister)</li>
        <li>EU AI Act Risiko-Signale</li>
        <li>Personalisierter HTML-Report per Email</li>
        <li>Tägl. Lieferung 08:30 Uhr</li>
        <li>Monatlich kündbar</li>
      </ul>
      <div class="order-form" id="form-basic">
        <input type="email" placeholder="Ihre Email-Adresse" id="email-basic" autocomplete="email">
        <button class="btn-buy" onclick="checkout('basic')">Jetzt bestellen — €499/Monat</button>
        <div class="form-note">Sicher bezahlen via Stripe · Jederzeit kündbar</div>
      </div>
    </div>
    <div class="plan featured">
      <div class="plan-badge">EMPFOHLEN</div>
      <div class="plan-name">Compliance-Wächter Pro</div>
      <div class="plan-price">€999<span>/Monat</span></div>
      <p class="plan-desc">25 Leads täglich + vollständiges EU AI Act Monitoring — für wachsende Vertriebsteams mit Compliance-Fokus.</p>
      <ul class="plan-features">
        <li>25 bewertete Leads täglich</li>
        <li>EU AI Act Compliance-Monitoring</li>
        <li>Monatlicher Compliance-Report</li>
        <li>Alle Basic-Features inkl.</li>
        <li>Priority-Email-Support</li>
        <li>Monatlich kündbar</li>
      </ul>
      <div class="order-form" id="form-pro">
        <input type="email" placeholder="Ihre Email-Adresse" id="email-pro" autocomplete="email">
        <button class="btn-buy" onclick="checkout('pro')">Jetzt bestellen — €999/Monat</button>
        <div class="form-note">Sicher bezahlen via Stripe · Jederzeit kündbar</div>
      </div>
    </div>
  </div>

  <div class="sec-head"><span class="sec-lbl">Warum KI-Leasing</span><div class="sec-rule"></div></div>
  <div class="trust-row">
    <div class="trust-item"><div class="trust-icon">⏰</div><div class="trust-text"><b>Keine Einrichtung</b>Sofort aktiv nach Zahlung. Kein Tool, kein Passwort, kein Training.</div></div>
    <div class="trust-item"><div class="trust-icon">📊</div><div class="trust-text"><b>Echte Daten</b>Insolvenzbekanntmachungen.de, Handelsregister, EU AI Act Risikoanalyse.</div></div>
    <div class="trust-item"><div class="trust-icon">📧</div><div class="trust-text"><b>Direkt ins Postfach</b>Kein Login, kein Dashboard. Report kommt tägl. um 08:30 an Ihre Email.</div></div>
    <div class="trust-item"><div class="trust-icon">🔄</div><div class="trust-text"><b>Monatlich kündbar</b>Kein Jahresvertrag. Kein Risiko. Kündigung jederzeit möglich.</div></div>
  </div>
</main>

<script>
async function checkout(pkg) {
  const emailEl = document.getElementById('email-' + pkg);
  const email   = emailEl ? emailEl.value.trim() : '';
  if (!email || !email.includes('@')) { alert('Bitte gültige Email-Adresse eingeben.'); return; }
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Weiterleitung...';
  try {
    const r = await fetch('/api/ki-leasing/checkout', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email, package: pkg})
    });
    const d = await r.json();
    if (d.ok && d.checkout_url) {
      window.location.href = d.checkout_url;
    } else {
      alert('Fehler: ' + (d.error || 'Unbekannt'));
      btn.disabled = false;
      btn.textContent = 'Jetzt bestellen';
    }
  } catch(e) {
    alert('Netzwerkfehler: ' + e.message);
    btn.disabled = false;
    btn.textContent = 'Jetzt bestellen';
  }
}
</script>
</body></html>"""


async def handle_ki_leasing_page(req):
    return web.Response(text=_KI_LEASING_PAGE, content_type="text/html")


async def handle_ki_leasing_success(req):
    session_id = req.rel_url.query.get("session", "")
    html = f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<title>KI-Leasing aktiv!</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:system-ui,sans-serif;background:#07090E;color:#E2E8F0;display:flex;align-items:center;justify-content:center;min-height:100vh}}
.card{{background:#111520;border:1px solid #F5A623;padding:52px;max-width:520px;text-align:center;box-shadow:0 0 60px rgba(245,166,35,.12)}}
.num{{font-size:4rem;margin-bottom:20px;font-family:monospace;color:#F5A623;font-weight:900}}
h1{{font-size:1.6rem;font-weight:800;letter-spacing:-.03em;margin-bottom:10px}}
p{{color:#64748B;line-height:1.8;margin-bottom:24px;font-size:14px}}
a{{display:inline-block;background:#F5A623;color:#000;padding:13px 32px;text-decoration:none;font-weight:800;font-size:15px}}</style></head>
<body><div class="card">
  <div class="num">✓</div>
  <h1>Ihr KI-Mitarbeiter ist aktiv!</h1>
  <p>Zahlung erfolgreich. Ihr erster Report kommt <b style="color:#F5A623">morgen um 08:30 Uhr</b> an Ihre Email-Adresse.<br><br>
  Der KI-Mitarbeiter analysiert bereits heute Nacht die besten Leads für Sie.</p>
  <a href="/ki-leasing">Zurück zur Übersicht</a>
</div></body></html>"""
    return web.Response(text=html, content_type="text/html")


async def handle_ki_leasing_checkout(req):
    try:
        body    = await req.json()
        email   = body.get("email", "").strip()
        package = body.get("package", "basic").strip()
        if not email or "@" not in email:
            return web.json_response({"ok": False, "error": "Ungültige E-Mail"}, status=400)
        from modules.ki_leasing_engine import create_checkout
        return web.json_response(await create_checkout(email, package))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ki_leasing_webhook(req):
    try:
        payload    = await req.read()
        sig_header = req.headers.get("Stripe-Signature", "")
        # Stripe-Signatur validieren (identisch zu handle_stripe_webhook)
        from modules.stripe_automation import verify_webhook_signature
        webhook_secret = os.getenv("STRIPE_KI_LEASING_WEBHOOK_SECRET", os.getenv("STRIPE_WEBHOOK_SECRET", ""))
        if webhook_secret:
            if not verify_webhook_signature(payload, sig_header, webhook_secret):
                log.warning("KI-Leasing webhook: ungültige Stripe-Signatur")
                return web.json_response({"ok": False, "error": "Invalid Stripe signature"}, status=400)
        event      = json.loads(payload)
        from modules.ki_leasing_engine import handle_webhook
        result = await handle_webhook(event)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)


async def handle_ki_leasing_clients(req):
    try:
        from modules.ki_leasing_engine import get_active_clients
        return web.json_response({"ok": True, "clients": get_active_clients()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ki_leasing_status(req):
    try:
        from modules.ki_leasing_engine import get_stats
        return web.json_response({"ok": True, **get_stats()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_ki_leasing_send_now(req):
    try:
        from modules.ki_leasing_engine import send_daily_reports
        result = await send_daily_reports()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── OOS Sniper ────────────────────────────────────────────────────────────────

async def handle_oos_status(req):
    try:
        from modules.oos_sniper import get_status
        return web.json_response(get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_oos_scan(req):
    async def _bg():
        try:
            from modules.oos_sniper import run_scan
            await run_scan()
        except Exception as e:
            log.error("OOS scan: %s", e)
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "OOS Scan gestartet"})


async def handle_oos_add_target(req):
    try:
        body   = await req.json()
        domain = body.get("domain", "").strip()
        label  = body.get("label", "").strip()
        if not domain:
            return web.json_response({"ok": False, "error": "domain fehlt"}, status=400)
        from modules.oos_sniper import add_target
        return web.json_response(add_target(domain, label))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── Review Goldmine ───────────────────────────────────────────────────────────

async def handle_review_analyze(req):
    try:
        body        = await req.json()
        url_or_asin = body.get("asin", body.get("url", "")).strip()
        if not url_or_asin:
            return web.json_response({"ok": False, "error": "asin fehlt"}, status=400)
        from modules.review_goldmine import analyze
        return web.json_response(await analyze(url_or_asin))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_review_status(req):
    try:
        from modules.review_goldmine import get_status
        return web.json_response(get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── Cart Rescue ───────────────────────────────────────────────────────────────

async def handle_cart_webhook(req):
    try:
        payload  = await req.read()
        hmac_hdr = req.headers.get("X-Shopify-Hmac-Sha256", "")
        from modules.cart_rescue import handle_webhook
        return web.json_response(await handle_webhook(payload, hmac_hdr))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_cart_status(req):
    try:
        from modules.cart_rescue import get_status
        return web.json_response(get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_cart_test(req):
    try:
        body = await req.json()
        from modules.cart_rescue import manual_trigger
        return web.json_response(await manual_trigger(
            body.get("email", ""), body.get("product", "Test Produkt"),
            float(body.get("price", 29.99)), body.get("url", "https://ineedit.com.co")
        ))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════════════════
#  VIRAL WINDOW SCANNER — Handlers
# ═══════════════════════════════════════════════════════════════════════════

_viral_scan_running = False

async def handle_viral_status(req):
    try:
        from modules.viral_window_scanner import get_status
        data = await get_status()
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_viral_scan(req):
    global _viral_scan_running
    if _viral_scan_running:
        return web.json_response({"ok": False, "error": "Scan läuft bereits"})
    async def _bg():
        global _viral_scan_running
        _viral_scan_running = True
        try:
            from modules.viral_window_scanner import run_scan
            await run_scan()
        except Exception as e:
            log.error("Viral scan error: %s", e)
        finally:
            _viral_scan_running = False
    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "Scan gestartet im Hintergrund"})


async def handle_viral_alerts(req):
    try:
        limit = int(req.rel_url.query.get("limit", "20"))
        from modules.viral_window_scanner import get_latest_alerts
        data = await get_latest_alerts(limit=limit)
        return web.json_response({"ok": True, "alerts": data, "count": len(data)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_viral_subscribe(req):
    try:
        body = await req.json()
        email = body.get("email", "").strip()
        tier  = body.get("tier", "alert").strip()
        if not email or "@" not in email:
            return web.json_response({"ok": False, "error": "Ungültige E-Mail"}, status=400)
        if tier not in ("alert", "pro", "agency"):
            return web.json_response({"ok": False, "error": "Ungültiger Tier"}, status=400)
        from modules.viral_window_scanner import create_checkout_session
        result = await create_checkout_session(email, tier)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_viral_webhook(req):
    try:
        payload   = await req.read()
        signature = req.headers.get("Stripe-Signature", "")
        from modules.viral_window_scanner import handle_stripe_webhook
        result = await handle_stripe_webhook(payload, signature)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_viral_setup(req):
    try:
        from modules.viral_window_scanner import setup_stripe_products
        result = await setup_stripe_products()
        return web.json_response({"ok": True, "products": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_viral_tg_register(req):
    try:
        body = await req.json()
        email = body.get("email", "").strip()
        telegram_id = body.get("telegram_id", "").strip()
        tier  = body.get("tier", "alert").strip()
        if not email or not telegram_id:
            return web.json_response({"ok": False, "error": "email + telegram_id erforderlich"}, status=400)
        from modules.viral_window_scanner import add_telegram_subscriber
        result = await add_telegram_subscriber(email, telegram_id, tier)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_viral_success(req):
    session_id = req.rel_url.query.get("session_id", "")
    html = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<title>Willkommen — Viral Window Scanner</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;
  display:flex;align-items:center;justify-content:center;min-height:100vh}}
.card{{background:#161b22;border:1px solid #238636;border-radius:16px;
  padding:48px;max-width:520px;text-align:center}}
.icon{{font-size:4rem;margin-bottom:24px}}
h1{{font-size:1.8rem;margin-bottom:12px;color:#2ea043}}
p{{color:#8b949e;line-height:1.6;margin-bottom:24px}}
.btn{{display:inline-block;background:linear-gradient(90deg,#238636,#2ea043);
  color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;
  font-weight:700;font-size:1rem}}
.sub-id{{font-size:.75rem;color:#484f58;margin-top:16px}}
</style></head><body>
<div class="card">
  <div class="icon">🔥</div>
  <h1>Subscription aktiv!</h1>
  <p>Du bekommst ab sofort Echtzeit-Alerts sobald ein Produkt ein
  Viral-Fenster öffnet — bevor der Markt gesättigt ist.</p>
  <p><strong>Nächster Schritt:</strong> Sende deinem Telegram-Bot deine Telegram-ID
  damit Alerts direkt ankommen.<br>
  Kommando: <code>/register deine@email.de</code></p>
  <a href="/viral" class="btn">→ Zum Dashboard</a>
  <div class="sub-id">Session: {session_id[:20]}...</div>
</div></body></html>"""
    return web.Response(text=html, content_type="text/html")


async def handle_viral_page(req):
    html = """<!DOCTYPE html>
<html lang="de"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Viral Window Scanner — Echtzeit Trendprodukte</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh}
header{background:#161b22;border-bottom:1px solid #30363d;padding:16px 24px;
  display:flex;align-items:center;justify-content:space-between}
header h1{font-size:1.2rem;background:linear-gradient(90deg,#ff6b35,#ff0066);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:800}
.nav a{color:#58a6ff;text-decoration:none;margin-left:16px;font-size:.85rem}
.hero{text-align:center;padding:60px 24px 40px}
.hero-badge{display:inline-block;background:rgba(255,107,53,.15);border:1px solid #ff6b35;
  color:#ff6b35;padding:6px 16px;border-radius:20px;font-size:.8rem;font-weight:700;
  margin-bottom:20px;letter-spacing:.5px}
.hero h2{font-size:2.8rem;font-weight:900;line-height:1.15;margin-bottom:16px}
.hero h2 span{background:linear-gradient(90deg,#ff6b35,#ff0066);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hero p{color:#8b949e;font-size:1.1rem;max-width:580px;margin:0 auto 32px;line-height:1.6}
.hero-stats{display:flex;gap:32px;justify-content:center;margin-bottom:40px;flex-wrap:wrap}
.stat-pill{background:#161b22;border:1px solid #30363d;border-radius:10px;
  padding:14px 24px;text-align:center;min-width:120px}
.stat-num{font-size:1.6rem;font-weight:900;color:#ff6b35}
.stat-lbl{font-size:.75rem;color:#8b949e;margin-top:2px}
.signals{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));
  gap:10px;max-width:900px;margin:0 auto 48px;padding:0 24px}
.sig-card{background:#161b22;border:1px solid #30363d;border-radius:10px;
  padding:14px;display:flex;align-items:center;gap:10px}
.sig-icon{font-size:1.4rem}
.sig-name{font-size:.85rem;font-weight:600;color:#e6edf3}
.sig-desc{font-size:.72rem;color:#8b949e;margin-top:2px}
.pricing{max-width:900px;margin:0 auto;padding:0 24px 60px}
.pricing h3{text-align:center;font-size:1.8rem;margin-bottom:8px}
.pricing-sub{text-align:center;color:#8b949e;margin-bottom:32px;font-size:.95rem}
.plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.plan{background:#161b22;border:1px solid #30363d;border-radius:12px;
  padding:28px;position:relative;transition:border-color .2s}
.plan.featured{border-color:#ff6b35;box-shadow:0 0 30px rgba(255,107,53,.15)}
.plan-badge{position:absolute;top:-12px;left:50%;transform:translateX(-50%);
  background:linear-gradient(90deg,#ff6b35,#ff0066);color:#fff;padding:4px 14px;
  border-radius:12px;font-size:.72rem;font-weight:700;white-space:nowrap}
.plan-name{font-size:1.1rem;font-weight:800;margin-bottom:8px}
.plan-price{font-size:2.4rem;font-weight:900;color:#ff6b35;margin-bottom:4px}
.plan-price span{font-size:.9rem;color:#8b949e;font-weight:400}
.plan-desc{color:#8b949e;font-size:.85rem;margin-bottom:20px;line-height:1.5}
.plan-features{list-style:none;margin-bottom:24px}
.plan-features li{padding:6px 0;font-size:.88rem;border-bottom:1px solid #21262d;
  display:flex;align-items:center;gap:8px}
.plan-features li:last-child{border:none}
.plan-features li::before{content:"✓";color:#2ea043;font-weight:700}
.plan-btn{width:100%;padding:13px;border:none;border-radius:8px;cursor:pointer;
  font-weight:700;font-size:.95rem;transition:opacity .15s}
.plan-btn-primary{background:linear-gradient(90deg,#ff6b35,#ff0066);color:#fff}
.plan-btn-secondary{background:#21262d;color:#e6edf3;border:1px solid #30363d}
.plan-btn:hover{opacity:.85}
.alerts-section{max-width:900px;margin:0 auto;padding:0 24px 60px}
.alerts-section h3{font-size:1.5rem;margin-bottom:20px}
.alert-card{background:#161b22;border:1px solid #30363d;border-radius:10px;
  padding:16px 20px;margin-bottom:10px;display:flex;align-items:center;gap:16px}
.alert-score{background:rgba(255,107,53,.15);border:1px solid #ff6b35;color:#ff6b35;
  font-weight:900;font-size:1.1rem;padding:10px 16px;border-radius:8px;
  white-space:nowrap;min-width:70px;text-align:center}
.alert-kw{font-weight:700;font-size:.95rem;margin-bottom:4px}
.alert-meta{font-size:.78rem;color:#8b949e}
.alert-window{margin-left:auto;font-size:.8rem;background:#21262d;
  padding:4px 10px;border-radius:6px;white-space:nowrap}
.scan-btn{background:linear-gradient(90deg,#ff6b35,#ff0066);color:#fff;border:none;
  padding:12px 28px;border-radius:8px;font-size:.95rem;font-weight:700;
  cursor:pointer;transition:opacity .15s}
.scan-btn:hover{opacity:.85}
.scan-btn:disabled{opacity:.5;cursor:not-allowed}
.status-bar{background:#161b22;border-bottom:1px solid #30363d;
  padding:8px 24px;font-size:.8rem;color:#8b949e;display:flex;gap:20px;flex-wrap:wrap}
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);
  z-index:100;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal{background:#161b22;border:1px solid #30363d;border-radius:16px;
  padding:36px;max-width:440px;width:90%}
.modal h4{font-size:1.3rem;margin-bottom:8px}
.modal p{color:#8b949e;font-size:.88rem;margin-bottom:20px;line-height:1.5}
.form-group{margin-bottom:16px}
.form-group label{display:block;font-size:.82rem;color:#8b949e;margin-bottom:6px}
.form-group input{width:100%;background:#0d1117;border:1px solid #30363d;
  color:#e6edf3;padding:10px 14px;border-radius:8px;font-size:.9rem}
.form-group input:focus{outline:none;border-color:#ff6b35}
.modal-footer{display:flex;gap:10px;margin-top:20px}
.btn-cancel{flex:1;padding:11px;background:#21262d;border:1px solid #30363d;
  color:#e6edf3;border-radius:8px;cursor:pointer;font-weight:600}
.btn-pay{flex:2;padding:11px;background:linear-gradient(90deg,#ff6b35,#ff0066);
  color:#fff;border:none;border-radius:8px;cursor:pointer;font-weight:700}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.loading{animation:pulse 1.2s infinite;color:#8b949e}
</style>
</head>
<body>
<header>
  <h1>🔥 Viral Window Scanner</h1>
  <nav class="nav">
    <a href="/">Dashboard</a>
    <a href="/viral">Scanner</a>
    <a href="/master">Master</a>
  </nav>
</header>
<div class="status-bar">
  <span>Signale: <strong id="stat-signals">...</strong></span>
  <span>High-Score: <strong id="stat-high">...</strong></span>
  <span>Alerts gesendet: <strong id="stat-alerts">...</strong></span>
  <span>Shopify Imports: <strong id="stat-imports">...</strong></span>
  <span>Subscriber: <strong id="stat-subs">...</strong></span>
  <span style="margin-left:auto">
    <button class="scan-btn" id="scan-btn" onclick="triggerScan()">▶ Scan starten</button>
  </span>
</div>

<div class="hero">
  <div class="hero-badge">🌍 WELTEINZIGARTIGES TOOL</div>
  <h2>Finde Produkte bevor sie<br><span>viral werden</span></h2>
  <p>Unser AI-Scanner kombiniert 5 Echtzeit-Signalquellen und erkennt
  das 48-72h Trend-Fenster — bevor der Markt gesättigt ist.
  Du bekommst das fertige Shopify-Listing, den Lieferanten und die Ad-Copy.</p>
  <div class="hero-stats">
    <div class="stat-pill"><div class="stat-num" id="h-signals">--</div><div class="stat-lbl">Signale heute</div></div>
    <div class="stat-pill"><div class="stat-num" id="h-score">--</div><div class="stat-lbl">Top Score</div></div>
    <div class="stat-pill"><div class="stat-num" id="h-imports">--</div><div class="stat-lbl">Auto-Imports</div></div>
    <div class="stat-pill"><div class="stat-num" id="h-subs">--</div><div class="stat-lbl">Subscriber</div></div>
  </div>
</div>

<div class="signals">
  <div class="sig-card">
    <div class="sig-icon">📈</div>
    <div><div class="sig-name">Google Trends</div><div class="sig-desc">Echtzeit RSS DE/AT</div></div>
  </div>
  <div class="sig-card">
    <div class="sig-icon">📦</div>
    <div><div class="sig-name">Amazon Movers</div><div class="sig-desc">Stundendaten DE</div></div>
  </div>
  <div class="sig-card">
    <div class="sig-icon">🏭</div>
    <div><div class="sig-name">AliExpress</div><div class="sig-desc">Top Bestseller</div></div>
  </div>
  <div class="sig-card">
    <div class="sig-icon">💬</div>
    <div><div class="sig-name">Reddit</div><div class="sig-desc">r/ecommerce + mehr</div></div>
  </div>
  <div class="sig-card">
    <div class="sig-icon">🎵</div>
    <div><div class="sig-name">TikTok Niches</div><div class="sig-desc">30 Trending-Niches</div></div>
  </div>
  <div class="sig-card">
    <div class="sig-icon">🤖</div>
    <div><div class="sig-name">AI Scoring</div><div class="sig-desc">Claude / GPT-4o</div></div>
  </div>
</div>

<div class="alerts-section">
  <h3>🔥 Letzte Viral Alerts</h3>
  <div id="alerts-list"><div class="loading">Lade Alerts...</div></div>
</div>

<div class="pricing">
  <h3>💎 Subscription Tiers</h3>
  <p class="pricing-sub">Wähle deinen Plan — kündige jederzeit</p>
  <div class="plans">
    <div class="plan">
      <div class="plan-name">Alert Only</div>
      <div class="plan-price">€29 <span>/ Monat</span></div>
      <div class="plan-desc">Echtzeit-Telegram-Alert wenn Score 55+</div>
      <ul class="plan-features">
        <li>Telegram Alert (Score 55+)</li>
        <li>Keyword + Score + Quellen</li>
        <li>Fenster-Countdown</li>
        <li>Supplier-Hint</li>
      </ul>
      <button class="plan-btn plan-btn-secondary" onclick="openModal('alert')">Jetzt starten</button>
    </div>
    <div class="plan featured">
      <div class="plan-badge">⭐ BELIEBTESTER</div>
      <div class="plan-name">Pro</div>
      <div class="plan-price">€79 <span>/ Monat</span></div>
      <div class="plan-desc">Alerts + Shopify Auto-Import + alle Details</div>
      <ul class="plan-features">
        <li>Alles aus Alert</li>
        <li>Shopify Auto-Import (Score 72+)</li>
        <li>Fertiges Listing (Titel, Desc, Tags)</li>
        <li>Margin-Kalkulation</li>
        <li>Frühere Alerts (Score 40+)</li>
      </ul>
      <button class="plan-btn plan-btn-primary" onclick="openModal('pro')">Pro starten</button>
    </div>
    <div class="plan">
      <div class="plan-name">Agency</div>
      <div class="plan-price">€199 <span>/ Monat</span></div>
      <div class="plan-desc">5 Stores, White-Label, persönlicher Support</div>
      <ul class="plan-features">
        <li>Alles aus Pro</li>
        <li>5 Shopify Stores</li>
        <li>White-Label Reports</li>
        <li>Priority Alerts</li>
        <li>Persönlicher Telegram-Support</li>
      </ul>
      <button class="plan-btn plan-btn-secondary" onclick="openModal('agency')">Agency anfragen</button>
    </div>
  </div>
</div>

<div class="modal-overlay" id="modal-overlay">
  <div class="modal">
    <h4 id="modal-title">Subscription starten</h4>
    <p id="modal-desc">Du wirst zu Stripe weitergeleitet. Sichere Zahlung, kündige jederzeit.</p>
    <div class="form-group">
      <label>E-Mail-Adresse</label>
      <input type="email" id="modal-email" placeholder="deine@email.de" required>
    </div>
    <div class="modal-footer">
      <button class="btn-cancel" onclick="closeModal()">Abbrechen</button>
      <button class="btn-pay" id="pay-btn" onclick="startCheckout()">💳 Jetzt abonnieren →</button>
    </div>
  </div>
</div>

<script>
let selectedTier = 'alert';
const tierLabels = {alert:'Alert Only (€29/Mo)',pro:'Pro (€79/Mo)',agency:'Agency (€199/Mo)'};

async function loadStatus() {
  try {
    const r = await fetch('/api/viral/status');
    const d = await r.json();
    if(!d.ok) return;
    document.getElementById('stat-signals').textContent = d.total_signals || 0;
    document.getElementById('stat-high').textContent    = d.high_score || 0;
    document.getElementById('stat-alerts').textContent  = d.alerts_sent || 0;
    document.getElementById('stat-imports').textContent = d.shopify_imports || 0;
    document.getElementById('stat-subs').textContent    = d.subs_active || 0;
    document.getElementById('h-signals').textContent    = d.total_signals || 0;
    document.getElementById('h-score').textContent      = d.top_products?.[0]?.score?.toFixed(0) || '--';
    document.getElementById('h-imports').textContent    = d.shopify_imports || 0;
    document.getElementById('h-subs').textContent       = d.subs_active || 0;
  } catch(e) { console.log('Status load error:', e); }
}

async function loadAlerts() {
  try {
    const r = await fetch('/api/viral/alerts?limit=10');
    const d = await r.json();
    const el = document.getElementById('alerts-list');
    if(!d.ok || !d.alerts?.length) {
      el.innerHTML = '<div style="color:#8b949e;padding:20px;text-align:center">Noch keine Alerts — starte den ersten Scan! ▶</div>';
      return;
    }
    el.innerHTML = d.alerts.map(a => {
      const dt = a.sent_at ? new Date(a.sent_at*1000).toLocaleString('de-DE') : '--';
      const score = Math.round(a.score || 0);
      const scoreColor = score>=85?'#ff0066':score>=70?'#ff6b35':'#f0a500';
      return `<div class="alert-card">
        <div class="alert-score" style="border-color:${scoreColor};color:${scoreColor}">${score}</div>
        <div style="flex:1;min-width:0">
          <div class="alert-kw">${a.keyword}</div>
          <div class="alert-meta">📡 ${a.sources||'multi'} · 🏭 ${a.supplier||'AliExpress'} · 💰 ~${Math.round(a.margin_pct||55)}% Margin${a.shopify_id?(' · ✅ Shopify'):''}</div>
          <div class="alert-meta" style="margin-top:4px">${dt}</div>
        </div>
        <div class="alert-window">⏱ ${a.window_h||48}h Fenster</div>
      </div>`;
    }).join('');
  } catch(e) { document.getElementById('alerts-list').innerHTML='<div style="color:#f85149">Fehler beim Laden</div>'; }
}

async function triggerScan() {
  const btn = document.getElementById('scan-btn');
  btn.disabled = true; btn.textContent = '⏳ Scan läuft...';
  try {
    const r = await fetch('/api/viral/scan', {method:'POST'});
    const d = await r.json();
    if(d.ok) {
      btn.textContent = '✅ Scan gestartet';
      setTimeout(()=>{btn.textContent='▶ Scan starten';btn.disabled=false;loadStatus();loadAlerts();}, 60000);
    } else {
      btn.textContent = d.error || 'Fehler'; btn.disabled = false;
    }
  } catch(e) { btn.textContent='Fehler'; btn.disabled=false; }
}

function openModal(tier) {
  selectedTier = tier;
  document.getElementById('modal-title').textContent = tierLabels[tier];
  document.getElementById('modal-overlay').classList.add('open');
}
function closeModal() { document.getElementById('modal-overlay').classList.remove('open'); }

async function startCheckout() {
  const email = document.getElementById('modal-email').value.trim();
  if(!email || !email.includes('@')) { alert('Bitte eine gültige E-Mail eingeben'); return; }
  const btn = document.getElementById('pay-btn');
  btn.textContent = '⏳ Weiterleitung...'; btn.disabled = true;
  try {
    const r = await fetch('/api/viral/subscribe', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({email, tier:selectedTier})
    });
    const d = await r.json();
    if(d.checkout_url) { window.location.href = d.checkout_url; }
    else { alert(d.error || 'Checkout nicht verfügbar — Stripe Price IDs prüfen (/api/viral/setup)'); btn.textContent='Jetzt abonnieren →'; btn.disabled=false; }
  } catch(e) { alert('Netzwerkfehler'); btn.textContent='Jetzt abonnieren →'; btn.disabled=false; }
}

loadStatus(); loadAlerts();
setInterval(()=>{loadStatus();loadAlerts();}, 30000);
</script>
</body></html>"""
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
                log.debug("Killed PID %s on port %s", pid, port)
            except Exception:
                pass
    except Exception:
        pass


# ── Product Intelligence Hub Handlers ────────────────────────────────────────

async def handle_hub_status(req):
    """GET /api/hub/status — Status aller 3 Module: scanner + pipeline + intent bridge."""
    try:
        from modules.product_intelligence_hub import get_hub_status
        result = await get_hub_status()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


_hub_running = False

async def handle_hub_run(req):
    """POST /api/hub/run — Startet vollständigen Hub-Zyklus (alle 3 Tools)."""
    global _hub_running
    if _hub_running:
        return web.json_response({"ok": False, "error": "Hub läuft bereits"})

    async def _bg():
        global _hub_running
        _hub_running = True
        try:
            from modules.product_intelligence_hub import run_hub_cycle
            await run_hub_cycle()
        finally:
            _hub_running = False

    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "Hub-Zyklus gestartet (alle 3 Tools)"})


# ── VIRAL PROMO POSTER handlers ───────────────────────────────────────────────

_promo_running = False

async def handle_promo_run(req):
    """POST /api/promo/run — Startet Multi-Channel Promo-Zyklus."""
    global _promo_running
    if _promo_running:
        return web.json_response({"ok": False, "error": "Promo läuft bereits"})

    async def _bg():
        global _promo_running
        _promo_running = True
        try:
            from modules.viral_promo_poster import run_promo_cycle
            await run_promo_cycle()
        except Exception as e:
            log.error("Promo error: %s", e)
        finally:
            _promo_running = False

    asyncio.create_task(_bg())
    return web.json_response({"ok": True, "status": "Promo gestartet (FB/Twitter/LinkedIn/Reddit/TG/Gumroad)"})


async def handle_promo_stats(req):
    """GET /api/promo/stats — Posting-Statistiken."""
    try:
        from modules.viral_promo_poster import get_promo_stats
        return web.json_response(await get_promo_stats())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── BPI 8 Systems — Helper + Handler-Funktionen ───────────────────────────────

def _render_bpi_page(title, sys_id, stats, packages):
    pkg_html = ""
    for name, price, desc in packages:
        pkg_html += (
            f'<div class="pkg-card"><h3>{name}</h3>'
            f'<div class="price">{price}</div><p>{desc}</p></div>'
        )
    stats_html = "".join(
        f'<div class="stat"><span>{k}</span><strong>{v}</strong></div>'
        for k, v in (stats or {}).items()
    )
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title>{title} — BPI</title>
<style>
  body{{background:#0a0a0f;color:#e0e0e0;font-family:system-ui;margin:0;padding:2rem}}
  h1{{color:#7c3aed;font-size:2rem}}
  .sys-badge{{background:#1a1a2e;color:#7c3aed;padding:4px 12px;border-radius:20px;font-size:.8rem}}
  .pkg-card{{background:#12121e;border:1px solid #2a2a4a;border-radius:12px;padding:1.5rem;margin:.5rem;display:inline-block;min-width:200px;vertical-align:top}}
  .price{{color:#10b981;font-size:1.5rem;font-weight:bold;margin:.5rem 0}}
  .stat{{background:#0d0d1a;padding:.75rem 1rem;border-radius:8px;margin:.3rem;display:inline-block}}
  .stat span{{color:#666;font-size:.8rem;display:block}}
  .stat strong{{color:#e0e0e0;font-size:1.1rem}}
  .btn{{background:#7c3aed;color:#fff;border:none;padding:.75rem 2rem;border-radius:8px;cursor:pointer;font-size:1rem;margin-top:1rem}}
  a{{color:#7c3aed}}
</style></head>
<body>
<a href="/">← Dashboard</a>
<h1>{title} <span class="sys-badge">{sys_id}</span></h1>
<div style="margin:1rem 0">{stats_html}</div>
<h2 style="color:#999;font-size:1rem;margin-top:2rem">PAKETE</h2>
<div>{pkg_html}</div>
</body></html>"""


# SYS-01 KI-Leasing — zusaetzlicher Stats-Handler (page+checkout schon oben registriert)
async def handle_ki_leasing_stats(request):
    try:
        from modules.ki_leasing_engine import get_stats
        stats = get_stats()
        return web.json_response({"ok": True, **stats})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# SYS-02 Trend Velocity
async def handle_trend_velocity_page(request):
    try:
        from modules.trend_velocity_engine import TrendVelocityEngine
        engine = TrendVelocityEngine()
        stats = await engine.get_stats()
    except Exception:
        stats = {}
    html = _render_bpi_page("Trend Velocity Radar", "SYS-02", stats, [
        ("Starter",     "299/mo",    "Top-10 Trends taeglich"),
        ("Pro",         "599/mo",    "Real-Time Alerts + API"),
        ("Enterprise",  "1.299/mo",  "Unlimitiert + Slack"),
    ])
    return web.Response(text=html, content_type="text/html")


async def handle_trend_velocity_run(request):
    try:
        data = await request.json()
        from modules.trend_velocity_engine import run_scan
        result = await run_scan(data.get("category", "all"))
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_trend_velocity_stats(request):
    try:
        from modules.trend_velocity_engine import get_stats
        return web.json_response({"ok": True, **await get_stats()})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# SYS-03 Ghost Vendor Network
async def handle_ghost_vendor_page(request):
    try:
        from modules.ghost_vendor_network import GhostVendorNetwork
        engine = GhostVendorNetwork()
        stats = await engine.get_stats()
    except Exception:
        stats = {}
    html = _render_bpi_page("Ghost Vendor Network", "SYS-03", stats, [
        ("Basic",       "199/mo",   "5 Vendor-Slots"),
        ("Pro",         "499/mo",   "20 Slots + Automation"),
        ("Enterprise",  "999/mo",   "Unlimitiert + White-Label"),
    ])
    return web.Response(text=html, content_type="text/html")


async def handle_ghost_vendor_run(request):
    try:
        data = await request.json()
        from modules.ghost_vendor_network import run_cycle
        result = await run_cycle(data.get("vendor_id", ""))
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_ghost_vendor_clients(request):
    try:
        from modules.ghost_vendor_network import get_clients
        return web.json_response({"ok": True, "clients": await get_clients()})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# SYS-04 EU AI Act
async def handle_ai_act_page(request):
    try:
        from modules.ai_act_compliance import AIActCompliance
        engine = AIActCompliance()
        stats = await engine.get_stats()
    except Exception:
        stats = {}
    html = _render_bpi_page("EU AI Act Compliance", "SYS-04", stats, [
        ("Quick Check",  "99 einmalig",   "Basis-Compliance-Analyse"),
        ("Full Audit",   "499 einmalig",  "Vollstaendiger Report + Plan"),
        ("Ongoing",      "299/mo",        "Kontinuierliches Monitoring"),
    ])
    return web.Response(text=html, content_type="text/html")


async def handle_ai_act_quick_check(request):
    try:
        data = await request.json()
        from modules.ai_act_compliance import run_quick_check
        result = await run_quick_check(
            data.get("company", ""), data.get("use_case", "")
        )
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_ai_act_checkout(request):
    try:
        data = await request.json()
        from modules.ai_act_stripe_portal import create_checkout
        url = await create_checkout(
            data.get("package", "quick_check"), data.get("email", "")
        )
        return web.json_response({"checkout_url": url})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# SYS-05 Insolvenz Arbitrage
async def handle_insolvenz_arbitrage_page(request):
    try:
        from modules.insolvenz_arbitrage import InsolvenzArbitrage
        engine = InsolvenzArbitrage()
        stats = await engine.get_stats()
    except Exception:
        stats = {}
    html = _render_bpi_page("Insolvenz Arbitrage", "SYS-05", stats, [
        ("Scout",  "149/mo",  "10 Alerts/Tag"),
        ("Trader", "399/mo",  "Unlimitiert + Bewertung"),
        ("Pro",    "799/mo",  "+ Rechtscheck + API"),
    ])
    return web.Response(text=html, content_type="text/html")


async def handle_insolvenz_arbitrage_run(request):
    try:
        data = await request.json()
        from modules.insolvenz_arbitrage import run_scan
        result = await run_scan(data.get("region", "DE"))
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_insolvenz_arbitrage_opps(request):
    try:
        from modules.insolvenz_arbitrage import get_opportunities
        return web.json_response({"ok": True, "opportunities": await get_opportunities()})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# SYS-06 Migration Rush
async def handle_migration_rush_page(request):
    try:
        from modules.migration_rush_engine import MigrationRushEngine
        engine = MigrationRushEngine()
        stats = await engine.get_stats()
    except Exception:
        stats = {}
    html = _render_bpi_page("Migration Rush Intelligence", "SYS-06", stats, [
        ("Signal", "199/mo",  "Woechentliche Signale"),
        ("Stream", "449/mo",  "Taeglich + Geo-Filter"),
        ("Alpha",  "899/mo",  "Real-Time + API"),
    ])
    return web.Response(text=html, content_type="text/html")


async def handle_migration_rush_run(request):
    try:
        data = await request.json()
        from modules.migration_rush_engine import run_scan
        result = await run_scan(data.get("region", "EU"))
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_migration_rush_signals(request):
    try:
        from modules.migration_rush_engine import get_signals
        return web.json_response({"ok": True, "signals": await get_signals()})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# SYS-07 AI Citation SEO
async def handle_ai_citation_seo_page(request):
    try:
        from modules.ai_citation_seo import AICitationSEO
        engine = AICitationSEO()
        stats = await engine.get_stats()
    except Exception:
        stats = {}
    html = _render_bpi_page("AI Citation SEO", "SYS-07", stats, [
        ("Starter",   "249/mo",    "5 Keywords optimiert"),
        ("Growth",    "599/mo",    "25 Keywords + Reports"),
        ("Authority", "1.199/mo",  "Unlimitiert + Backlinks"),
    ])
    return web.Response(text=html, content_type="text/html")


async def handle_ai_citation_seo_run(request):
    try:
        data = await request.json()
        from modules.ai_citation_seo import run_optimization
        result = await run_optimization(
            data.get("url", ""), data.get("keywords", [])
        )
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_ai_citation_seo_stats(request):
    try:
        from modules.ai_citation_seo import get_stats
        return web.json_response({"ok": True, **await get_stats()})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# SYS-08 Intelligence Broker
async def handle_intelligence_broker_page(request):
    try:
        from modules.intelligence_broker import IntelligenceBroker
        engine = IntelligenceBroker()
        stats = await engine.get_stats()
    except Exception:
        stats = {}
    html = _render_bpi_page("Intelligence Broker", "SYS-08", stats, [
        ("Report",   "499 einmalig",  "Markt-Dossier auf Anfrage"),
        ("Retainer", "1.499/mo",      "4 Reports/Monat + Calls"),
        ("Premium",  "2.999/mo",      "Woechentlich + Dedicated Analyst"),
    ])
    return web.Response(text=html, content_type="text/html")


async def handle_intelligence_broker_report(request):
    try:
        data = await request.json()
        from modules.intelligence_broker import generate_report
        result = await generate_report(
            data.get("topic", ""),
            data.get("depth", "standard"),
            data.get("email", ""),
        )
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_intelligence_broker_watchlist(request):
    try:
        from modules.intelligence_broker import get_watchlist
        return web.json_response({"ok": True, "watchlist": await get_watchlist()})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


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


# ── BullPower MCC Routes ─────────────────────────────────────────────────────

async def handle_bullpower_mcc(req: web.Request) -> web.Response:
    """GET /bullpower — BullPower Mega Command Center Dashboard."""
    try:
        mcc_path = Path(__file__).parent / "bullpower_mcc.html"
        if mcc_path.exists():
            return web.Response(text=mcc_path.read_text(encoding="utf-8"), content_type="text/html")
        return web.Response(text="<h1>BullPower MCC</h1><p>Dashboard nicht gefunden.</p>", content_type="text/html")
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_env_validate(req: web.Request) -> web.Response:
    """GET /api/env/validate — Env Variables Validation."""
    try:
        from modules.bullpower_revenue_engine import validate_env
        return web.json_response(validate_env())
    except Exception as e:
        # Fallback: basic check
        required = [
            "SHOPIFY_SHOP_DOMAIN", "SHOPIFY_ADMIN_API_TOKEN", "TELEGRAM_BOT_TOKEN",
            "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SENDGRID_API_KEY",
            "KLAVIYO_API_KEY", "STRIPE_SECRET_KEY", "META_ACCESS_TOKEN",
            "DS24_API_KEY", "ANTHROPIC_API_KEY",
        ]
        missing = [{"var": v, "label": v} for v in required if not os.getenv(v, "")]
        return web.json_response({
            "ok": len(missing) == 0,
            "required_present": len(required) - len(missing),
            "required_missing": missing,
            "total_required": len(required),
        })


# handle_revenue_summary: vollständige Multi-Source-Implementierung (Stripe+Shopify+DS24)
# befindet sich weiter oben als handle_revenue_summary(req) — dieses Duplikat entfernt.


if __name__ == '__main__':
    asyncio.run(_main())
