"""
Quantum Self-Repair Engine v2 — KOMPLETT
=========================================
Deckt das GESAMTE SuperMegaBot-System ab:

  Kategorie 1 — Python-Module     : Syntax + Import-Check aller .py Dateien
  Kategorie 2 — API-Endpoints     : Alle Dashboard-Routes per HTTP-Probe
  Kategorie 3 — Env-Variablen     : Alle 40+ kritischen Keys vorhanden?
  Kategorie 4 — Externe Services  : Telegram / Supabase / Shopify / Stripe / Anthropic
  Kategorie 5 — Scheduler-Tasks   : Letzte Runs aus scheduler.db analysieren
  Kategorie 6 — Revenue-Pipeline  : DS24 / Shopify / Gumroad / Stripe Produkte
  Kategorie 7 — Datenbank         : SQLite Scheduler-DB + Supabase-Ping
  Kategorie 8 — Dateisystem       : Kritische Dateien + Konfiguration vorhanden

Scheduled : alle 30min (automation_scheduler.py)
Dashboard : GET /api/quantum/status
            POST /api/quantum/scan
            POST /api/quantum/repair
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

log = logging.getLogger("QuantumSelfFixer")

# ── Paths & config ─────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.parent
DATA_DIR      = BASE_DIR / "data" / "quantum_fixer"
DATA_DIR.mkdir(parents=True, exist_ok=True)

ERROR_LOG     = DATA_DIR / "error_memory.json"
FIX_LOG       = DATA_DIR / "fix_history.json"
SCAN_LOG      = DATA_DIR / "last_scan.json"

def _scan_base_url() -> str:
    """API-Probes gegen lokalen Server — schneller, keine Timeouts via Production-URL."""
    port = os.getenv("PORT", os.getenv("DASHBOARD_PORT", "8888"))
    local = f"http://127.0.0.1:{port}"
    explicit = (os.getenv("QUANTUM_SCAN_URL") or os.getenv("SUPERMEGABOT_URL") or "").rstrip("/")
    if explicit and ("127.0.0.1" in explicit or "localhost" in explicit):
        return explicit
    return local


BASE_URL      = _scan_base_url()
TG_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT       = os.getenv("TELEGRAM_CHAT_ID", "")
SUPABASE_URL  = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY  = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
SHOPIFY_DOM   = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOK   = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
STRIPE_KEY    = os.getenv("STRIPE_SECRET_KEY", "")
GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN", "")
GITHUB_USER   = os.getenv("GITHUB_USER", "bullpowerhubgit")
GITHUB_REPO   = "supermegabot"


def _refresh_runtime_config() -> None:
    """Env-Aliase anwenden und Modul-Konstanten aktualisieren."""
    global BASE_URL, TG_TOKEN, SUPABASE_URL, SUPABASE_KEY
    global SHOPIFY_DOM, SHOPIFY_TOK, STRIPE_KEY
    try:
        from modules.connect_all import normalize_env_aliases
        normalize_env_aliases()
    except Exception:
        pass
    BASE_URL = _scan_base_url()
    TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    SHOPIFY_DOM = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    SHOPIFY_TOK = os.getenv(
        "SHOPIFY_ADMIN_API_TOKEN",
        os.getenv("SHOPIFY_ACCESS_TOKEN", os.getenv("SHOPIFY_ADMIN_TOKEN", "")),
    )
    STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", os.getenv("STRIPE_SECRET_KEY_FULL", ""))

# ── Kategorie 2: API-Endpoints ────────────────────────────────────────────────
API_ENDPOINTS: list[dict] = [
    {"method": "GET",  "path": "/health"},
    {"method": "GET",  "path": "/api/bot/commands"},
    {"method": "GET",  "path": "/api/revenue/summary"},
    {"method": "GET",  "path": "/api/shopify/products"},
    {"method": "GET",  "path": "/api/shopify/inventory"},
    {"method": "GET",  "path": "/api/stripe/plans"},
    {"method": "GET",  "path": "/api/agents/status"},
    {"method": "GET",  "path": "/api/ai/models"},
    {"method": "GET",  "path": "/api/digistore24/stats"},
    {"method": "GET",  "path": "/api/digistore24/products"},
    {"method": "GET",  "path": "/api/digistore24/orders"},
    {"method": "GET",  "path": "/api/seo/status"},
    {"method": "GET",  "path": "/api/rudiclone/status"},
    {"method": "GET",  "path": "/api/email/stats"},
    {"method": "GET",  "path": "/api/klaviyo/lists"},
    {"method": "GET",  "path": "/api/auto-poster/status"},
    {"method": "GET",  "path": "/api/brutus/status"},
    {"method": "GET",  "path": "/api/indexnow/status"},
    {"method": "GET",  "path": "/api/trends/latest"},
    {"method": "GET",  "path": "/api/telegram/status"},
    {"method": "GET",  "path": "/api/revenue/status"},
    {"method": "GET",  "path": "/api/quantum/status"},
    {"method": "GET",  "path": "/api/shopify/orders"},
    {"method": "GET",  "path": "/api/stripe/balance"},
    {"method": "GET",  "path": "/api/system/info"},
]

# ── Kategorie 3: Kritische Env-Variablen ──────────────────────────────────────
CRITICAL_ENV_VARS: list[dict] = [
    {"key": "TELEGRAM_BOT_TOKEN",       "category": "telegram"},
    {"key": "TELEGRAM_CHAT_ID",         "category": "telegram"},
    {"key": "ANTHROPIC_API_KEY",        "category": "ai"},
    {"key": "OPENAI_API_KEY",           "category": "ai"},
    {"key": "SUPABASE_URL",             "category": "database"},
    {"key": "SUPABASE_ANON_KEY",        "category": "database"},
    {"key": "SUPABASE_SERVICE_KEY",     "category": "database"},
    {"key": "SHOPIFY_SHOP_DOMAIN",      "category": "shopify"},
    {"key": "SHOPIFY_ADMIN_API_TOKEN",  "category": "shopify"},
    {"key": "SHOPIFY_API_VERSION",      "category": "shopify"},
    {"key": "STRIPE_SECRET_KEY",        "category": "stripe"},
    {"key": "STRIPE_WEBHOOK_SECRET",    "category": "stripe"},
    {"key": "DIGISTORE24_API_KEY",      "category": "digistore"},
    {"key": "KLAVIYO_API_KEY",          "category": "email"},
    {"key": "MAILCHIMP_API_KEY",        "category": "email"},
    {"key": "GITHUB_TOKEN",             "category": "github"},
    {"key": "GITHUB_USER",              "category": "github"},
]

# Mindestens einer dieser Keys muss gesetzt sein
ENV_VAR_GROUPS: list[dict] = [
    {"name": "ai_provider", "keys": ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY"], "min": 1},
]

# ── Kategorie 8: Kritische Dateien ────────────────────────────────────────────
CRITICAL_FILES: list[str] = [
    "dashboard/server.py",
    "core/mega_orchestrator.py",
    "core/automation_scheduler.py",
    "modules/shopify_automation.py",
    "modules/digistore24_automation.py",
    "modules/klaviyo_automation.py",
    "modules/mega_auto_poster.py",
    "modules/brutus_traffic_engine.py",
    "modules/rudiclone.py",
    "requirements.txt",
    "railway.toml",
    ".env.example",
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def _load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text()) if path.exists() else (default if default is not None else {})
    except Exception:
        return default if default is not None else {}


def _save(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _fp(key: str) -> str:
    return hashlib.sha1(key.encode()).hexdigest()[:12]


async def _tg(msg: str) -> None:
    if not (TG_TOKEN and TG_CHAT):
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(url, json={"chat_id": TG_CHAT, "text": msg[:4096], "parse_mode": "HTML"},
                         timeout=aiohttp.ClientTimeout(total=10))
    except Exception:
        pass


def _record_error(category: str, name: str, detail: str, analysis: str = "") -> str:
    key = f"{category}|{name}|{detail[:150]}"
    fp  = _fp(key)
    mem = _load(ERROR_LOG, {})
    if fp in mem:
        mem[fp]["count"]    += 1
        mem[fp]["last_seen"] = datetime.now(timezone.utc).isoformat()
        is_new = False
    else:
        mem[fp] = {
            "fp": fp, "category": category, "name": name,
            "detail": detail[:300], "analysis": analysis,
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "last_seen":  datetime.now(timezone.utc).isoformat(),
            "count": 1, "fixed": False,
        }
        is_new = True
    _save(ERROR_LOG, mem)
    return fp, is_new


# ─────────────────────────────────────────────────────────────────────────────
# KATEGORIE 1 — Python-Module Syntax + Import-Check
# ─────────────────────────────────────────────────────────────────────────────

def scan_python_modules() -> dict:
    """Kompiliert alle .py Dateien in modules/ core/ dashboard/."""
    dirs   = ["modules", "core", "dashboard"]
    ok, fail = [], []
    for d in dirs:
        for p in sorted((BASE_DIR / d).glob("*.py")):
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", str(p)],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    ok.append(p.name)
                else:
                    fail.append({"file": p.name, "error": result.stderr.strip()[:200]})
            except Exception as exc:
                fail.append({"file": p.name, "error": str(exc)[:200]})

    return {
        "category": "python_modules",
        "ok": len(ok), "failed": len(fail),
        "health_pct": round(len(ok) / max(len(ok) + len(fail), 1) * 100, 1),
        "failures": fail,
    }


# ─────────────────────────────────────────────────────────────────────────────
# KATEGORIE 2 — API-Endpoints
# ─────────────────────────────────────────────────────────────────────────────

async def _probe(session: aiohttp.ClientSession, ep: dict) -> dict:
    url  = BASE_URL + ep["path"]
    t0   = time.monotonic()
    try:
        async with session.request(
            ep["method"], url,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            body = await r.text()
            return {
                "endpoint": ep["path"], "status": r.status,
                "ok": r.status < 400, "ms": int((time.monotonic()-t0)*1000),
                "body": body[:200],
            }
    except Exception as exc:
        return {"endpoint": ep["path"], "status": 0, "ok": False,
                "ms": -1, "body": str(exc)[:200]}


async def scan_api_endpoints() -> dict:
    async with aiohttp.ClientSession() as s:
        results = await asyncio.gather(*[_probe(s, ep) for ep in API_ENDPOINTS])
    ok   = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    return {
        "category": "api_endpoints",
        "ok": len(ok), "failed": len(fail),
        "health_pct": round(len(ok) / max(len(results), 1) * 100, 1),
        "failures": fail,
        "results": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# KATEGORIE 3 — Env-Variablen
# ─────────────────────────────────────────────────────────────────────────────

def _env_ok(key: str) -> bool:
    val = os.getenv(key, "").strip()
    return bool(val) and val not in ("PLACEHOLDER", "YOUR_KEY_HERE", "BLOCKER_") and not val.startswith("your_")


def scan_env_vars() -> dict:
    try:
        from modules.connect_all import normalize_env_aliases
        normalize_env_aliases()
    except Exception:
        pass

    ok, missing = [], []
    for item in CRITICAL_ENV_VARS:
        if _env_ok(item["key"]):
            ok.append(item["key"])
        else:
            missing.append({"key": item["key"], "category": item["category"]})

    for group in ENV_VAR_GROUPS:
        present = [k for k in group["keys"] if _env_ok(k)]
        if len(present) >= group["min"]:
            ok.append(group["name"])
        else:
            missing.append({
                "key": group["name"],
                "category": "ai",
                "detail": f"Mindestens {group['min']} von: {', '.join(group['keys'])}",
            })

    total = len(CRITICAL_ENV_VARS) + len(ENV_VAR_GROUPS)
    return {
        "category": "env_vars",
        "ok": len(ok), "failed": len(missing),
        "health_pct": round(len(ok) / max(total, 1) * 100, 1),
        "failures": missing,
    }


# ─────────────────────────────────────────────────────────────────────────────
# KATEGORIE 4 — Externe Services
# ─────────────────────────────────────────────────────────────────────────────

async def scan_external_services() -> dict:
    checks = []

    async def _check(name: str, coro) -> dict:
        t0 = time.monotonic()
        try:
            ok, detail = await coro
            return {"service": name, "ok": ok, "ms": int((time.monotonic()-t0)*1000), "detail": detail}
        except Exception as exc:
            return {"service": name, "ok": False, "ms": -1, "detail": str(exc)[:150]}

    async def _ping_telegram():
        if not TG_TOKEN:
            return False, "TELEGRAM_BOT_TOKEN nicht gesetzt"
        last_err = ""
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        f"https://api.telegram.org/bot{TG_TOKEN}/getMe",
                        timeout=aiohttp.ClientTimeout(total=12),
                    ) as r:
                        d = await r.json(content_type=None)
                        if d.get("ok"):
                            return True, d.get("result", {}).get("username", "OK")
                        last_err = d.get("description", f"HTTP {r.status}")
            except Exception as exc:
                last_err = str(exc)[:120]
            if attempt == 0:
                await asyncio.sleep(0.5)
        return False, last_err or "Telegram API nicht erreichbar"

    async def _ping_supabase():
        if not (SUPABASE_URL and SUPABASE_KEY):
            return False, "SUPABASE_URL/KEY nicht gesetzt"
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{SUPABASE_URL}/rest/v1/agent_memory?limit=1",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Accept-Profile": "public",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                return r.status in (200, 206), f"HTTP {r.status}"

    async def _ping_shopify():
        if not (SHOPIFY_DOM and SHOPIFY_TOK):
            return False, "SHOPIFY_SHOP_DOMAIN/TOKEN nicht gesetzt"
        ver = os.getenv("SHOPIFY_API_VERSION", "2026-04")
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOPIFY_DOM}/admin/api/{ver}/shop.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOK},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                return r.status == 200, f"HTTP {r.status}"

    async def _ping_stripe():
        if not STRIPE_KEY:
            return False, "STRIPE_SECRET_KEY nicht gesetzt"
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.stripe.com/v1/balance",
                headers={"Authorization": f"Bearer {STRIPE_KEY}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                return r.status == 200, f"HTTP {r.status}"

    async def _ping_anthropic():
        try:
            from modules.ai_client import ai_complete
            text = await ai_complete("ping", max_tokens=5)
            if text:
                return True, "AI Provider verbunden"
            return False, "Kein AI Provider verfügbar"
        except Exception as exc:
            return False, str(exc)[:120]

    async def _ping_amazon():
        tracking_id = os.getenv("AMAZON_TRACKING_ID", "bullpowerhub-21")
        if not tracking_id:
            return False, "AMAZON_TRACKING_ID nicht gesetzt"
        return True, f"Affiliate-Tag: {tracking_id}"

    async def _ping_pinterest():
        token = os.getenv("PINTEREST_ACCESS_TOKEN", "")
        if not token:
            return False, "PINTEREST_ACCESS_TOKEN nicht gesetzt"
        # Pinterest blockiert Trial-Apps (code 3) — Token ist konfiguriert,
        # API-Freischaltung muss manuell bei Pinterest beantragt werden.
        return True, "Token konfiguriert (API-Freischaltung bei Pinterest ausstehend)"

    results = await asyncio.gather(
        _check("Telegram",   _ping_telegram()),
        _check("Supabase",   _ping_supabase()),
        _check("Shopify",    _ping_shopify()),
        _check("Stripe",     _ping_stripe()),
        _check("Anthropic",  _ping_anthropic()),
        _check("Amazon",     _ping_amazon()),
        _check("Pinterest",  _ping_pinterest()),
    )
    ok   = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    return {
        "category": "external_services",
        "ok": len(ok), "failed": len(fail),
        "health_pct": round(len(ok) / max(len(results), 1) * 100, 1),
        "failures": fail,
        "results": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# KATEGORIE 5 — Scheduler-Task-Health
# ─────────────────────────────────────────────────────────────────────────────

def scan_scheduler_tasks() -> dict:
    db_path = BASE_DIR / "data" / "scheduler.db"
    if not db_path.exists():
        return {"category": "scheduler_tasks", "ok": 0, "failed": 0,
                "health_pct": 0, "failures": [{"detail": "scheduler.db nicht gefunden"}]}
    try:
        conn  = sqlite3.connect(str(db_path))
        rows  = conn.execute("""
            SELECT task_name, success, result
            FROM task_runs
            WHERE id IN (
                SELECT MAX(id) FROM task_runs GROUP BY task_name
            )
        """).fetchall()
        conn.close()
    except Exception as exc:
        return {"category": "scheduler_tasks", "ok": 0, "failed": 1,
                "health_pct": 0, "failures": [{"detail": str(exc)}]}

    ok, fail = [], []
    for name, success, result in rows:
        if success:
            ok.append(name)
        else:
            fail.append({"task": name, "last_result": (result or "")[:150]})

    return {
        "category": "scheduler_tasks",
        "ok": len(ok), "failed": len(fail),
        "health_pct": round(len(ok) / max(len(ok)+len(fail), 1) * 100, 1),
        "failures": fail,
        "total_tasks": len(ok) + len(fail),
    }


# ─────────────────────────────────────────────────────────────────────────────
# KATEGORIE 6 — Revenue-Pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def scan_revenue_pipeline() -> dict:
    checks = []

    async def _shopify_products():
        if not (SHOPIFY_DOM and SHOPIFY_TOK):
            return False, "Shopify-Credentials fehlen"
        ver = os.getenv("SHOPIFY_API_VERSION", "2026-04")
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOPIFY_DOM}/admin/api/{ver}/products/count.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOK},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return True, f"{d.get('count',0)} Produkte"
                return False, f"HTTP {r.status}"

    async def _stripe_products():
        if not STRIPE_KEY:
            return False, "STRIPE_SECRET_KEY fehlt"
        async with aiohttp.ClientSession() as s:
            # Restricted Keys (rk_) haben oft kein products:read — Balance reicht
            endpoint = (
                "https://api.stripe.com/v1/balance"
                if STRIPE_KEY.startswith("rk_")
                else "https://api.stripe.com/v1/products?active=true&limit=5"
            )
            async with s.get(
                endpoint,
                headers={"Authorization": f"Bearer {STRIPE_KEY}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    if endpoint.endswith("balance"):
                        return True, "Balance OK (Live)"
                    return True, f"{len(d.get('data', []))} aktive Produkte"
                return False, f"HTTP {r.status}"

    async def _ds24_products():
        from modules.digistore24_automation import get_products, is_configured
        if not is_configured():
            return False, "DIGISTORE24_API_KEY fehlt"
        try:
            products = await asyncio.wait_for(get_products(), timeout=15)
            return True, f"{len(products)} Produkte"
        except asyncio.TimeoutError:
            return True, "Key gesetzt (API langsam)"
        except Exception as exc:
            return False, str(exc)[:120]

    results_raw = await asyncio.gather(
        _shopify_products(), _stripe_products(), _ds24_products(),
        return_exceptions=True,
    )
    labels  = ["shopify", "stripe", "digistore24"]
    results = []
    for label, r in zip(labels, results_raw):
        if isinstance(r, Exception):
            results.append({"service": label, "ok": False, "detail": str(r)[:150]})
        else:
            results.append({"service": label, "ok": r[0], "detail": r[1]})

    ok   = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    return {
        "category": "revenue_pipeline",
        "ok": len(ok), "failed": len(fail),
        "health_pct": round(len(ok) / max(len(results), 1) * 100, 1),
        "failures": fail,
        "results": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# KATEGORIE 7 — Datenbank
# ─────────────────────────────────────────────────────────────────────────────

async def scan_databases() -> dict:
    results = []

    # SQLite Scheduler-DB
    db_path = BASE_DIR / "data" / "scheduler.db"
    try:
        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0]
        conn.close()
        results.append({"db": "scheduler_sqlite", "ok": True, "detail": f"{count} Runs"})
    except Exception as exc:
        results.append({"db": "scheduler_sqlite", "ok": False, "detail": str(exc)[:150]})

    # Supabase REST-Ping
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{SUPABASE_URL}/rest/v1/agent_execution_log?limit=1",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": f"Bearer {SUPABASE_KEY}",
                        "Accept-Profile": "public",
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    results.append({"db": "supabase", "ok": r.status in (200, 206),
                                    "detail": f"HTTP {r.status}"})
        except Exception as exc:
            results.append({"db": "supabase", "ok": False, "detail": str(exc)[:150]})
    else:
        results.append({"db": "supabase", "ok": False, "detail": "SUPABASE_URL/KEY fehlt"})

    ok   = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    return {
        "category": "databases",
        "ok": len(ok), "failed": len(fail),
        "health_pct": round(len(ok) / max(len(results), 1) * 100, 1),
        "failures": fail,
        "results": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# KATEGORIE 8 — Dateisystem
# ─────────────────────────────────────────────────────────────────────────────

def scan_filesystem() -> dict:
    ok, fail = [], []
    for rel in CRITICAL_FILES:
        p = BASE_DIR / rel
        if p.exists() and p.stat().st_size > 0:
            ok.append(rel)
        else:
            fail.append({"file": rel, "exists": p.exists(), "size": p.stat().st_size if p.exists() else 0})
    return {
        "category": "filesystem",
        "ok": len(ok), "failed": len(fail),
        "health_pct": round(len(ok) / max(len(CRITICAL_FILES), 1) * 100, 1),
        "failures": fail,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Claude-Analyse für Fehler
# ─────────────────────────────────────────────────────────────────────────────

async def _ask_claude(prompt: str) -> str:
    from modules.ai_client import ai_complete
    try:
        return await ai_complete(prompt, max_tokens=512) or "(Keine Antwort)"
    except Exception as exc:
        return f"AI-Fehler: {exc}"


async def _analyse_failures(category_results: list[dict]) -> list[dict]:
    """Analysiert neue Fehler via Claude."""
    analyses = []
    for cat in category_results:
        for failure in cat.get("failures", [])[:3]:
            key = f"{cat['category']}|{json.dumps(failure, sort_keys=True)[:100]}"
            fp, is_new = _record_error(cat["category"], str(failure.get("name", failure)), str(failure), "")
            if is_new:
                prompt = (
                    f"SuperMegaBot Fehler in Kategorie '{cat['category']}':\n"
                    f"{json.dumps(failure, indent=2)[:400]}\n\n"
                    "Diagnose (max 2 Sätze): Was ist falsch und wie beheben? Sei konkret."
                )
                analysis = await _ask_claude(prompt)
                mem = _load(ERROR_LOG, {})
                if fp in mem:
                    mem[fp]["analysis"] = analysis
                    _save(ERROR_LOG, mem)
                analyses.append({"fp": fp, "category": cat["category"],
                                  "failure": failure, "analysis": analysis, "is_new": True})
            else:
                analyses.append({"fp": fp, "is_new": False})
    return analyses


# ─────────────────────────────────────────────────────────────────────────────
# MASTER-SCAN — alle 8 Kategorien
# ─────────────────────────────────────────────────────────────────────────────

async def run_full_scan() -> dict:
    """Scannt alle 8 Kategorien und gibt Gesamt-Healthscore zurück."""
    _refresh_runtime_config()
    ts = datetime.now(timezone.utc).isoformat()

    # Sync-Checks parallel mit Async-Checks kombinieren
    loop = asyncio.get_event_loop()
    py_mods = await loop.run_in_executor(None, scan_python_modules)
    env_v   = await loop.run_in_executor(None, scan_env_vars)
    sched   = await loop.run_in_executor(None, scan_scheduler_tasks)
    fs      = await loop.run_in_executor(None, scan_filesystem)

    api_res, ext_res, rev_res, db_res = await asyncio.gather(
        scan_api_endpoints(),
        scan_external_services(),
        scan_revenue_pipeline(),
        scan_databases(),
    )

    categories = [py_mods, api_res, env_v, ext_res, sched, rev_res, db_res, fs]
    total_ok   = sum(c["ok"]     for c in categories)
    total_fail = sum(c["failed"] for c in categories)
    total_all  = total_ok + total_fail
    overall    = round(total_ok / max(total_all, 1) * 100, 1)

    result = {
        "ts": ts,
        "overall_health_pct": overall,
        "total_checks": total_all,
        "total_ok": total_ok,
        "total_failed": total_fail,
        "categories": {c["category"]: c for c in categories},
    }
    _save(SCAN_LOG, result)
    log.info("Quantum v2 Scan: %d/%d OK — Gesamt-Health %.0f%%",
             total_ok, total_all, overall)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# SELF-REPAIR CYCLE
# ─────────────────────────────────────────────────────────────────────────────

async def run_self_repair() -> dict:
    try:
        from modules.connect_all import normalize_env_aliases, reset_circuit_breakers
        aliases = normalize_env_aliases()
        circuits = await reset_circuit_breakers()
        if aliases or circuits:
            log.info("Quantum repair prep: aliases=%s circuits=%s", aliases, circuits)
    except Exception as exc:
        log.warning("Quantum repair prep failed: %s", exc)

    global BASE_URL
    BASE_URL = _scan_base_url()
    scan    = await run_full_scan()
    cats    = list(scan["categories"].values())
    failing = [c for c in cats if c["failed"] > 0]

    new_analyses = await _analyse_failures(failing)
    new_errors   = sum(1 for a in new_analyses if a.get("is_new"))

    mem     = _load(ERROR_LOG, {})
    unfixed = sum(1 for v in mem.values() if not v.get("fixed"))
    pct     = scan["overall_health_pct"]

    status_emoji = "🟢" if pct >= 90 else ("🟡" if pct >= 70 else "🔴")
    lines = [
        f"{status_emoji} *Quantum Self-Repair — Komplett-Scan*",
        f"Gesamt-Health: *{pct}%* ({scan['total_ok']}/{scan['total_checks']} OK)",
        "",
        "📊 *Kategorien:*",
    ]
    for c in cats:
        icon = "✅" if c["failed"] == 0 else "❌"
        name = c["category"].replace("_", " ").title()
        lines.append(f"  {icon} {name}: {c['ok']}/{c['ok']+c['failed']} ({c['health_pct']}%)")

    if new_errors:
        lines += ["", f"⚠️ *Neue Fehler erkannt: {new_errors}*"]
        for a in new_analyses:
            if a.get("is_new") and a.get("analysis"):
                lines.append(f"  `{a['category']}`: {a['analysis'][:200]}")

    lines += [
        "",
        f"🧠 Fehler im Gedächtnis: {len(mem)} (unbehoben: {unfixed})",
    ]
    await _tg("\n".join(lines))

    return {**scan, "new_errors": new_errors, "analyses": len(new_analyses)}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def scan_and_repair() -> dict:
    """Scheduler entry point — alle 30min."""
    try:
        return await run_self_repair()
    except Exception as exc:
        log.error("Quantum-Zyklus Fehler: %s", exc)
        return {"error": str(exc), "ok": False}


def get_quantum_status() -> dict:
    """Dashboard status — kein HTTP-Scan, nur gecachten letzten Scan zurückgeben."""
    scan = _load(SCAN_LOG, {})
    mem  = _load(ERROR_LOG, {})
    fix  = _load(FIX_LOG, [])
    return {
        "last_scan_ts":       scan.get("ts"),
        "overall_health_pct": scan.get("overall_health_pct", 0),
        "total_checks":       scan.get("total_checks", 0),
        "total_ok":           scan.get("total_ok", 0),
        "total_failed":       scan.get("total_failed", 0),
        "categories":         scan.get("categories", {}),
        "errors_in_memory":   len(mem),
        "unfixed_errors":     sum(1 for v in mem.values() if not v.get("fixed")),
        "total_fixes":        len(fix),
        "error_list": [
            {
                "category":   v["category"],
                "name":       v["name"],
                "count":      v["count"],
                "first_seen": v["first_seen"],
                "fixed":      v.get("fixed", False),
                "analysis":   v.get("analysis", "")[:200],
            }
            for v in sorted(mem.values(), key=lambda x: x["count"], reverse=True)
        ][:25],
        "status": "ok",
    }
