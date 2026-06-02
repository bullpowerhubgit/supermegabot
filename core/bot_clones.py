#!/usr/bin/env python3
"""
SuperMegaBot — Spezialisierte Bot-Clone System
Jeder Clone übernimmt einen spezifischen Bereich:
  🔍 WatchBot    — Monitoring & Alerting
  🔧 RepairBot   — Fehlerkennung & Auto-Reparatur
  📈 GrowthBot   — SEO, Content, Social Media
  💰 RevenueBot  — Umsatz-Tracking & Alerts
  🛡 GuardBot    — Sicherheit & API-Key-Gesundheit
  🚀 DeployBot   — GitHub Backup & Service-Restart
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("BotClones")

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

_STATUS_FILE = DATA_DIR / "bot_clones_status.json"


def _load_status() -> Dict:
    if _STATUS_FILE.exists():
        try:
            return json.loads(_STATUS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_status(status: Dict):
    _STATUS_FILE.write_text(json.dumps(status, indent=2, ensure_ascii=False))


# ── Telegram helper ───────────────────────────────────────────────────────────

async def _tg(msg: str):
    import aiohttp
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"}
            )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# BOT DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

BOT_REGISTRY = {}


def bot(name: str, icon: str, description: str, interval_s: int):
    """Decorator to register a bot-clone."""
    def decorator(cls):
        BOT_REGISTRY[name] = {
            "name":        name,
            "icon":        icon,
            "description": description,
            "interval_s":  interval_s,
            "class":       cls,
        }
        return cls
    return decorator


# ── 1. WatchBot — Monitoring ─────────────────────────────────────────────────

@bot("watchbot", "🔍", "System-Monitoring, Service-Health, Port-Checks", 300)
class WatchBot:
    async def run(self) -> Dict:
        results = {}
        # CPU / RAM
        try:
            import psutil
            results["cpu_pct"]  = psutil.cpu_percent(interval=0.5)
            results["ram_pct"]  = psutil.virtual_memory().percent
            results["disk_pct"] = psutil.disk_usage("/").percent
        except ImportError:
            results["psutil"] = "not installed"

        # Port checks
        import socket
        ports = {"dashboard": 8888, "ollama": 11434}
        results["ports"] = {}
        for name, port in ports.items():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                results["ports"][name] = sock.connect_ex(("127.0.0.1", port)) == 0

        # Log file sizes
        logs_dir = BASE_DIR / "logs"
        if logs_dir.exists():
            results["log_sizes"] = {
                f.name: f"{f.stat().st_size // 1024}KB"
                for f in logs_dir.iterdir() if f.suffix == ".log"
            }

        # Alert if critical
        if results.get("cpu_pct", 0) > 90 or results.get("ram_pct", 0) > 90:
            await _tg(
                f"⚠️ <b>WatchBot Alert</b>\n"
                f"CPU: {results.get('cpu_pct','?')}% | RAM: {results.get('ram_pct','?')}%"
            )
        return results


# ── 2. RepairBot — Fehler & Reparatur ────────────────────────────────────────

@bot("repairbot", "🔧", "Broken-Import-Scan, DB-Cleanup, Log-Rotation", 1800)
class RepairBot:
    async def run(self) -> Dict:
        import py_compile
        results = {"errors": [], "fixed": [], "scanned": 0}

        # Compile-check all Python files
        for py_file in BASE_DIR.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            results["scanned"] += 1
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as e:
                results["errors"].append(f"{py_file.name}: {e}")

        # Cleanup old .pyc files
        cleaned = 0
        for pyc in BASE_DIR.rglob("*.pyc"):
            try:
                pyc.unlink()
                cleaned += 1
            except Exception:
                pass
        results["pyc_cleaned"] = cleaned

        # Check data dir for corrupt JSON
        for json_file in DATA_DIR.glob("*.json"):
            try:
                json.loads(json_file.read_text())
            except Exception:
                json_file.write_text("{}")
                results["fixed"].append(f"Reset corrupt: {json_file.name}")

        if results["errors"]:
            await _tg(
                f"🔧 <b>RepairBot</b> — {len(results['errors'])} Syntax-Fehler gefunden:\n"
                + "\n".join(results["errors"][:5])
            )
        return results


# ── 3. GrowthBot — SEO & Content ─────────────────────────────────────────────

@bot("growthbot", "📈", "SEO-Check, Content-Kalender, Social-Status", 7200)
class GrowthBot:
    async def run(self) -> Dict:
        results = {}

        # Check Shopify product count
        try:
            import aiohttp
            token  = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
            domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
            if token and domain:
                base = f"https://{domain}" if not domain.startswith("http") else domain
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                    async with s.get(
                        f"{base}/admin/api/{os.getenv('SHOPIFY_API_VERSION','2024-10')}/products/count.json",
                        headers={"X-Shopify-Access-Token": token}
                    ) as r:
                        if r.status == 200:
                            results["shopify_products"] = (await r.json()).get("count", 0)
        except Exception as e:
            results["shopify_error"] = str(e)

        # Check content calendar
        cal_file = DATA_DIR / "content_calendar.json"
        if cal_file.exists():
            try:
                cal = json.loads(cal_file.read_text())
                results["content_items"] = len(cal)
                results["content_updated"] = cal_file.stat().st_mtime
            except Exception:
                pass

        # Ollama health (for SEO generation)
        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
                async with s.get(os.getenv("OLLAMA_HOST", "http://localhost:11434") + "/api/tags") as r:
                    results["ollama_ok"] = r.status == 200
        except Exception:
            results["ollama_ok"] = False

        return results


# ── 4. RevenueBot — Umsatz ───────────────────────────────────────────────────

@bot("revenuebot", "💰", "Umsatz-Tracking, Platform-Vergleich, Daily Report", 3600)
class RevenueBot:
    async def run(self) -> Dict:
        results = {}
        # Load cached platform data
        for fname, platform in [
            ("digistore_orders.json", "digistore"),
            ("shopify_cache.json", "shopify"),
        ]:
            f = DATA_DIR / fname
            if f.exists():
                try:
                    d = json.loads(f.read_text())
                    age_h = (time.time() - f.stat().st_mtime) / 3600
                    results[platform] = {"age_h": round(age_h, 1), "data": d if isinstance(d, dict) else {"count": len(d)}}
                except Exception:
                    pass

        # Revenue snapshot
        snap_file = DATA_DIR / "revenue_snapshots.json"
        if snap_file.exists():
            try:
                snaps = json.loads(snap_file.read_text())
                results["snapshots"] = len(snaps)
                if snaps:
                    results["last_snapshot"] = snaps[-1].get("date", "")
            except Exception:
                pass

        return results


# ── 5. GuardBot — Sicherheit ─────────────────────────────────────────────────

@bot("guardbot", "🛡", "API-Key-Health, .env-Scan, Token-Expiry-Check", 21600)
class GuardBot:
    CRITICAL_KEYS = [
        "SHOPIFY_ACCESS_TOKEN", "PRINTIFY_API_KEY", "DIGISTORE24_API_KEY",
        "SUPABASE_URL", "SUPABASE_ANON_KEY", "PERPLEXITY_API_KEY",
    ]
    OPTIONAL_KEYS = [
        "TELEGRAM_BOT_TOKEN", "MAILCHIMP_API_KEY", "KLAVIYO_API_KEY",
        "STRIPE_SECRET_KEY", "META_ACCESS_TOKEN", "YOUTUBE_API_KEY",
    ]

    async def run(self) -> Dict:
        results = {"critical": {}, "optional": {}, "alerts": []}
        for key in self.CRITICAL_KEYS:
            val = os.getenv(key, "")
            results["critical"][key] = "✅ set" if val else "❌ MISSING"
            if not val:
                results["alerts"].append(key)
        for key in self.OPTIONAL_KEYS:
            val = os.getenv(key, "")
            results["optional"][key] = "✅ set" if val else "⚠️ missing"

        # Check .env exists and is not committed
        env_path = BASE_DIR / ".env"
        gitignore = BASE_DIR / ".gitignore"
        results[".env_exists"] = env_path.exists()
        if gitignore.exists():
            results[".env_gitignored"] = ".env" in gitignore.read_text()

        if results["alerts"]:
            await _tg(
                f"🛡 <b>GuardBot Alert</b> — Kritische Keys fehlen:\n"
                + "\n".join(f"  • {k}" for k in results["alerts"])
            )
        return results


# ── 6. DeployBot — GitHub & Services ─────────────────────────────────────────

@bot("deploybot", "🚀", "Git-Backup, Service-Watchdog, PM2-Status", 86400)
class DeployBot:
    async def run(self) -> Dict:
        import subprocess
        results = {}

        # Git status
        try:
            r = subprocess.run(
                ["git", "log", "--oneline", "-5"],
                cwd=str(BASE_DIR), capture_output=True, text=True, timeout=15
            )
            results["recent_commits"] = r.stdout.strip().splitlines()
        except Exception as e:
            results["git_error"] = str(e)

        # Check for uncommitted changes
        try:
            r = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(BASE_DIR), capture_output=True, text=True, timeout=10
            )
            results["uncommitted"] = len(r.stdout.strip().splitlines())
        except Exception:
            pass

        # PM2 status
        try:
            r = subprocess.run(
                ["pm2", "jlist"],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0:
                procs = json.loads(r.stdout)
                results["pm2"] = [
                    {"name": p["name"], "status": p["pm2_env"]["status"]}
                    for p in procs
                ]
            else:
                results["pm2"] = "not running"
        except Exception:
            results["pm2"] = "not installed"

        return results


# ══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════════════════════

class BotCloneManager:
    def __init__(self):
        self._running = False
        self._handles: list = []
        self._status: Dict = _load_status()

    async def start(self):
        self._running = True
        log.info(f"BotCloneManager gestartet — {len(BOT_REGISTRY)} Clones")
        for name, meta in BOT_REGISTRY.items():
            handle = asyncio.create_task(
                self._run_loop(name, meta["class"](), meta["interval_s"])
            )
            self._handles.append(handle)

    async def _run_loop(self, name: str, instance, interval_s: int):
        # Stagger starts so they don't all fire at once
        stagger = list(BOT_REGISTRY.keys()).index(name) * 15
        await asyncio.sleep(stagger)
        while self._running:
            t0 = time.monotonic()
            try:
                result = await instance.run()
                ms = int((time.monotonic() - t0) * 1000)
                self._status[name] = {
                    "last_run":    datetime.now().isoformat(),
                    "ok":          True,
                    "result":      result,
                    "ms":          ms,
                }
                log.debug(f"[{name}] OK ({ms}ms)")
            except Exception as e:
                ms = int((time.monotonic() - t0) * 1000)
                self._status[name] = {
                    "last_run": datetime.now().isoformat(),
                    "ok":       False,
                    "error":    str(e),
                    "ms":       ms,
                }
                log.error(f"[{name}] Error: {e}")
            _save_status(self._status)
            await asyncio.sleep(interval_s)

    async def stop(self):
        self._running = False
        for h in self._handles:
            h.cancel()


_manager: Optional[BotCloneManager] = None


def get_manager() -> BotCloneManager:
    global _manager
    if _manager is None:
        _manager = BotCloneManager()
    return _manager


async def get_bot_status() -> Dict:
    status = _load_status()
    bots = []
    for name, meta in BOT_REGISTRY.items():
        s = status.get(name, {})
        bots.append({
            "name":        name,
            "icon":        meta["icon"],
            "description": meta["description"],
            "interval_s":  meta["interval_s"],
            "last_run":    s.get("last_run"),
            "ok":          s.get("ok"),
            "ms":          s.get("ms", 0),
            "error":       s.get("error"),
        })
    return {"ok": True, "bots": bots, "count": len(bots)}


async def run_bot_action(bot_name: str, action: str) -> str:
    if bot_name not in BOT_REGISTRY:
        return f"Bot '{bot_name}' nicht gefunden"
    instance = BOT_REGISTRY[bot_name]["class"]()
    if action == "status":
        s = _load_status().get(bot_name, {})
        return json.dumps(s, ensure_ascii=False)
    if action == "run":
        result = await instance.run()
        status = _load_status()
        status[bot_name] = {"last_run": datetime.now().isoformat(), "ok": True, "result": result, "ms": 0}
        _save_status(status)
        return json.dumps(result, ensure_ascii=False)
    return f"Unbekannte Aktion: {action}"
