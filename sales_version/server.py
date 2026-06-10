#!/usr/bin/env python3
"""
AutoPilot CreatorHub AI — Sales Version
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Eigenständiger, passwortgeschützter Server.
Keine Demo-Daten. Nur echte API-Verbindungen.
Port: 9000 (konfigurierbar via PORT env)
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("SalesServer")

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    for _f in [ROOT_DIR / ".env", BASE_DIR / ".env"]:
        if _f.exists():
            for _line in _f.read_text().splitlines():
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _, _v = _line.partition("=")
                    os.environ.setdefault(_k.strip(), _v.strip())

PORT = int(os.getenv("SALES_PORT", os.getenv("PORT", "9000")))
# Password hash (SHA-256 of the password). Default: "autopilot2024"
DEFAULT_PASS = "autopilot2024"
_PASS_HASH = os.getenv(
    "SALES_PASSWORD_HASH",
    hashlib.sha256(os.getenv("SALES_PASSWORD", DEFAULT_PASS).encode()).hexdigest()
)

# Session store: token → expiry
_sessions: dict = {}
SESSION_TTL = 86400  # 24h

from aiohttp import web


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _make_session() -> str:
    token = secrets.token_hex(32)
    _sessions[token] = time.time() + SESSION_TTL
    return token


def _check_session(req: web.Request) -> bool:
    token = req.cookies.get("session") or req.headers.get("X-Session-Token", "")
    if not token:
        return False
    expiry = _sessions.get(token, 0)
    if time.time() > expiry:
        _sessions.pop(token, None)
        return False
    return True


def _require_auth(handler):
    async def wrapper(req):
        if not _check_session(req):
            if req.path.startswith("/api/"):
                return web.json_response({"error": "Nicht autorisiert"}, status=401)
            raise web.HTTPFound("/login")
        return await handler(req)
    return wrapper


# ── Login page ─────────────────────────────────────────────────────────────────

_LOGIN_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AutoPilot CreatorHub AI — Login</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#040608;color:#e8f4fd;min-height:100vh;display:flex;align-items:center;justify-content:center}
body::before{content:'';position:fixed;inset:0;background:radial-gradient(ellipse 80% 50% at 50% -20%,#003322,transparent);pointer-events:none}
.box{background:#0a0d12;border:1px solid #1a2030;border-radius:16px;padding:48px 40px;width:380px;position:relative;z-index:1}
.logo{font-size:1.4rem;font-weight:800;background:linear-gradient(135deg,#00ff9d,#00d4ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;text-align:center;margin-bottom:8px}
.sub{color:#4a6080;font-size:.82rem;text-align:center;margin-bottom:36px}
label{display:block;font-size:.75rem;color:#4a6080;margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px}
input[type=password]{width:100%;background:#0d1520;border:1px solid #1a2030;border-radius:8px;color:#e8f4fd;padding:12px 16px;font-size:1rem;outline:none;transition:.2s;margin-bottom:20px}
input[type=password]:focus{border-color:#00ff9d;box-shadow:0 0 0 2px #00ff9d15}
button{width:100%;padding:13px;background:#00ff9d;color:#000;font-weight:800;font-size:1rem;border:none;border-radius:8px;cursor:pointer;transition:.2s}
button:hover{box-shadow:0 0 20px #00ff9d33}
.err{color:#ff3355;font-size:.82rem;text-align:center;margin-top:12px;display:none}
.err.show{display:block}
.badge{display:inline-block;padding:3px 10px;background:#00ff9d11;border:1px solid #00ff9d33;color:#00ff9d;border-radius:20px;font-size:.7rem;font-weight:700;margin-bottom:24px}
.center{text-align:center}
</style>
</head>
<body>
<div class="box">
  <div class="logo">⚡ AutoPilot CreatorHub AI</div>
  <div class="sub">Shopify Automation · 10 AI-Agenten · Revenue Autopilot</div>
  <div class="center"><span class="badge">🔒 GESICHERT</span></div>
  <form id="form">
    <label>Passwort</label>
    <input type="password" id="pw" placeholder="Passwort eingeben…" autofocus>
    <button type="submit">Einloggen ⚡</button>
    <div class="err" id="err">Falsches Passwort</div>
  </form>
</div>
<script>
document.getElementById('form').onsubmit=async e=>{
  e.preventDefault();
  const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('pw').value})});
  const d=await r.json();
  if(d.ok)window.location='/';
  else{document.getElementById('err').classList.add('show');}
};
</script>
</body>
</html>"""


# ── Setup page ─────────────────────────────────────────────────────────────────

_SETUP_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Setup — AutoPilot CreatorHub</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#040608;color:#e8f4fd;padding:40px 20px}
body::before{content:'';position:fixed;inset:0;background:radial-gradient(ellipse 80% 50% at 50% -20%,#003322,transparent);pointer-events:none}
.container{max-width:680px;margin:0 auto;position:relative;z-index:1}
h1{font-size:1.6rem;font-weight:800;background:linear-gradient(135deg,#00ff9d,#00d4ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:8px}
.sub{color:#4a6080;font-size:.9rem;margin-bottom:32px}
.card{background:#0a0d12;border:1px solid #1a2030;border-radius:12px;padding:24px;margin-bottom:16px}
.card h2{font-size:.9rem;font-weight:700;margin-bottom:4px;color:#e8f4fd}
.card p{font-size:.8rem;color:#4a6080;margin-bottom:16px}
label{display:block;font-size:.75rem;color:#4a6080;margin-bottom:4px;margin-top:10px}
input{width:100%;background:#0d1520;border:1px solid #1a2030;border-radius:6px;color:#e8f4fd;padding:9px 12px;font-size:.88rem;outline:none}
input:focus{border-color:#00ff9d}
.hint{font-size:.72rem;color:#4a6080;margin-top:4px}
.hint a{color:#00d4ff}
button{padding:12px 24px;background:#00ff9d;color:#000;font-weight:800;border:none;border-radius:8px;cursor:pointer;font-size:.9rem;margin-top:20px}
button:hover{box-shadow:0 0 16px #00ff9d33}
.status{padding:10px 14px;border-radius:8px;font-size:.82rem;margin-top:16px;display:none}
.status.ok{background:#00ff9d15;color:#00ff9d;border:1px solid #00ff9d33;display:block}
.status.err{background:#ff335515;color:#ff3355;border:1px solid #ff335533;display:block}
.step{display:inline-block;width:24px;height:24px;background:#00ff9d;color:#000;border-radius:50%;font-weight:800;font-size:.8rem;text-align:center;line-height:24px;margin-right:8px}
</style>
</head>
<body>
<div class="container">
  <h1>⚡ Setup — AutoPilot CreatorHub AI</h1>
  <div class="sub">Trage deine echten API-Schlüssel ein. Keine Demo-Daten — nur echte Verbindungen.</div>

  <div class="card">
    <h2><span class="step">1</span>Shopify Admin API Token <span style="color:#ff3355;font-weight:700">← WICHTIGSTE</span></h2>
    <p>Shopify Admin → Einstellungen → Apps → Apps entwickeln → App erstellen → Scopes: read_orders, write_products, read_products, write_price_rules, write_discounts → Installieren → Admin-API-Zugriffstoken kopieren</p>
    <label>Shopify Shop Domain (z.B. mein-shop.myshopify.com)</label>
    <input id="shop-domain" placeholder="mein-shop.myshopify.com">
    <label>Admin API Zugriffstoken (beginnt mit shpat_)</label>
    <input id="shop-token" placeholder="shpat_xxxxxxxxxxxxxxxx" type="password">
  </div>

  <div class="card">
    <h2><span class="step">2</span>Claude / Anthropic API Key</h2>
    <p>console.anthropic.com → API Keys → Create Key</p>
    <label>Anthropic API Key</label>
    <input id="anthropic-key" placeholder="sk-ant-xxxxxxxx" type="password">
  </div>

  <div class="card">
    <h2><span class="step">3</span>Stripe (optional, für Zahlungen)</h2>
    <label>Stripe Secret Key</label>
    <input id="stripe-key" placeholder="sk_live_xxxxxxxx" type="password">
  </div>

  <div class="card">
    <h2><span class="step">4</span>Telegram Bot (optional, für Alerts)</h2>
    <p>@BotFather → /newbot → Token kopieren. Chat-ID: @userinfobot</p>
    <label>Telegram Bot Token</label>
    <input id="tg-token" placeholder="123456:AABBccDD..." type="password">
    <label>Telegram Chat ID</label>
    <input id="tg-chat" placeholder="-100123456789">
  </div>

  <button onclick="saveConfig()">💾 Konfiguration speichern & testen</button>
  <div class="status" id="status"></div>
</div>

<script>
async function saveConfig(){
  const config={
    SHOPIFY_SHOP_DOMAIN: document.getElementById('shop-domain').value.trim(),
    SHOPIFY_ADMIN_API_TOKEN: document.getElementById('shop-token').value.trim(),
    ANTHROPIC_API_KEY: document.getElementById('anthropic-key').value.trim(),
    STRIPE_SECRET_KEY: document.getElementById('stripe-key').value.trim(),
    TELEGRAM_BOT_TOKEN: document.getElementById('tg-token').value.trim(),
    TELEGRAM_CHAT_ID: document.getElementById('tg-chat').value.trim(),
  };
  const r=await fetch('/api/setup/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});
  const d=await r.json();
  const el=document.getElementById('status');
  if(d.ok){
    el.className='status ok';
    el.innerHTML='✅ Gespeichert! <a href="/" style="color:#00ff9d">→ Zum Dashboard</a>';
  }else{
    el.className='status err';
    el.textContent='Fehler: '+d.error;
  }
}
</script>
</body>
</html>"""


# ── API handlers ───────────────────────────────────────────────────────────────

async def handle_login_page(req):
    return web.Response(text=_LOGIN_HTML, content_type="text/html")


async def handle_login_post(req):
    try:
        data = await req.json()
        pw = data.get("password", "")
        pw_hash = hashlib.sha256(pw.encode()).hexdigest()
        if hmac.compare_digest(pw_hash, _PASS_HASH):
            token = _make_session()
            resp = web.json_response({"ok": True})
            resp.set_cookie("session", token, max_age=SESSION_TTL, httponly=True, samesite="Lax")
            return resp
        return web.json_response({"ok": False, "error": "Falsches Passwort"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_logout(req):
    token = req.cookies.get("session", "")
    _sessions.pop(token, None)
    resp = web.HTTPFound("/login")
    resp.del_cookie("session")
    return resp


async def handle_setup(req):
    return web.Response(text=_SETUP_HTML, content_type="text/html")


async def handle_setup_save(req):
    """Speichert Konfiguration in .env und testet Verbindungen."""
    try:
        data = await req.json()
        env_path = ROOT_DIR / ".env"
        # Read existing .env
        existing = {}
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    existing[k.strip()] = v.strip()

        # Update with new values
        for key, val in data.items():
            if val:
                existing[key] = val
                os.environ[key] = val

        # Write back
        lines = [f"{k}={v}" for k, v in existing.items()]
        env_path.write_text("\n".join(lines) + "\n")

        # Test Shopify connection
        import aiohttp as aiohttp_lib
        domain = data.get("SHOPIFY_SHOP_DOMAIN", "").strip()
        token = data.get("SHOPIFY_ADMIN_API_TOKEN", "").strip()
        if domain and token:
            url = f"https://{domain}/admin/api/2024-10/shop.json"
            async with aiohttp_lib.ClientSession() as s:
                async with s.get(url, headers={"X-Shopify-Access-Token": token}, timeout=aiohttp_lib.ClientTimeout(total=10)) as r:
                    body = await r.json()
                    if r.status != 200 or "errors" in body:
                        return web.json_response({"ok": False, "error": f"Shopify Token ungültig: {body}"})

        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


@_require_auth
async def handle_health(req):
    import sys
    sys.path.insert(0, str(ROOT_DIR))
    from modules.real_data_guard import get_system_health
    health = get_system_health()
    return web.json_response({
        "status": "ok" if health["ready"] else "degraded",
        "services": health["services"],
        "score": f"{health['score']}/{health['max_score']}",
        "ready": health["ready"],
        "missing": health["missing"],
    })


@_require_auth
async def handle_dashboard(req):
    """Leitet zur Autopilot-Hauptseite."""
    autopilot_html = ROOT_DIR / "dashboard" / "autopilot.html"
    if autopilot_html.exists():
        html = autopilot_html.read_text(encoding="utf-8")
        # Inject base URL for API calls
        html = html.replace("const API='';", "const API='http://localhost:8888';", 1)
        return web.Response(text=html, content_type="text/html")
    raise web.HTTPFound("http://localhost:8888/autopilot")


@_require_auth
async def handle_revenue_proxy(req):
    """Proxied Revenue-Daten vom Hauptserver."""
    import aiohttp as aiohttp_lib
    path = req.match_info.get("path", "")
    try:
        async with aiohttp_lib.ClientSession() as s:
            async with s.request(
                req.method,
                f"http://localhost:8888/api/revenue/{path}",
                headers={"Content-Type": "application/json"},
                json=await req.json() if req.can_read_body and req.method == "POST" else None,
                timeout=aiohttp_lib.ClientTimeout(total=60),
            ) as r:
                body = await r.json()
                return web.json_response(body)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


@_require_auth
async def handle_agents_proxy(req):
    """Proxied Agent-Calls vom Hauptserver."""
    import aiohttp as aiohttp_lib
    try:
        data = await req.json() if req.can_read_body else {}
        async with aiohttp_lib.ClientSession() as s:
            async with s.post(
                "http://localhost:8888/api/creatorhub/run",
                json=data,
                timeout=aiohttp_lib.ClientTimeout(total=60),
            ) as r:
                return web.json_response(await r.json())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


@_require_auth
async def handle_index(req):
    """Zeigt vollständiges Dashboard oder Setup-Wizard wenn nicht konfiguriert."""
    import sys
    sys.path.insert(0, str(ROOT_DIR))
    from modules.real_data_guard import get_system_health
    health = get_system_health()

    if not health["ready"]:
        # Redirect to setup if not configured
        raise web.HTTPFound("/setup")

    # Serve the main dashboard HTML with the password-protected wrapper
    autopilot_html = ROOT_DIR / "dashboard" / "autopilot.html"
    if autopilot_html.exists():
        html = autopilot_html.read_text(encoding="utf-8")
        # Add logout button to header
        html = html.replace(
            '<div class="mode-badge">🤖 AUTOPILOT MODE</div>',
            '<div class="mode-badge">🤖 AUTOPILOT MODE</div>'
            '<a href="/logout" style="padding:4px 12px;border-radius:20px;font-size:.72rem;font-weight:700;'
            'background:#ff335511;color:#ff3355;border:1px solid #ff335533;text-decoration:none;margin-left:8px">Abmelden</a>',
            1
        )
        return web.Response(text=html, content_type="text/html")

    return web.json_response({"error": "Dashboard nicht gefunden"}, status=404)


# ── App factory ────────────────────────────────────────────────────────────────

def create_app() -> web.Application:
    app = web.Application()

    # Public routes
    app.router.add_get("/login",           handle_login_page)
    app.router.add_post("/api/login",      handle_login_post)
    app.router.add_get("/logout",          handle_logout)
    app.router.add_get("/setup",           handle_setup)
    app.router.add_post("/api/setup/save", handle_setup_save)

    # Protected routes
    app.router.add_get("/",                handle_index)
    app.router.add_get("/health",          handle_health)
    app.router.add_get("/api/agents/run",  handle_agents_proxy)
    app.router.add_post("/api/agents/run", handle_agents_proxy)
    app.router.add_get(r"/api/revenue/{path:.*}", handle_revenue_proxy)
    app.router.add_post(r"/api/revenue/{path:.*}", handle_revenue_proxy)

    return app


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT_DIR))
    log.info("AutoPilot CreatorHub — Sales Version startet auf Port %d", PORT)
    log.info("Dashboard: http://localhost:%d", PORT)
    web.run_app(create_app(), host="0.0.0.0", port=PORT, print=None)
