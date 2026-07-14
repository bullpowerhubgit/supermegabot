#!/usr/bin/env python3
"""
SuperMegaBot — Self-Healing System (Portabel, Linux+macOS)
Überwacht Services, repariert automatisch, lernt aus Fehlern.
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

BASE_DIR  = Path(__file__).parent.parent
DATA_DIR  = BASE_DIR / "data"
HEAL_LOG  = DATA_DIR / "heal_history.json"
KNOWN_FIXES  = DATA_DIR / "known_fixes.json"
IMPROVE_LOG  = DATA_DIR / "improvements.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(DATA_DIR / "selfheal.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("SelfHealer")

_HOME = Path.home()


def _ext(env_var: str, default_rel: str) -> str:
    return os.getenv(env_var, str(_HOME / default_rel))


# ── Services überwachen ──────────────────────────────────────────────────────
WATCHED_SERVICES: Dict[str, Dict] = {
    "supermegabot_dashboard": {
        "type": "http",
        "url": f"http://localhost:{os.getenv('DASHBOARD_PORT','8888')}/health",
        "restart_cmd": [sys.executable, str(BASE_DIR / "dashboard" / "server.py")],
        "log": "/tmp/supermegabot.log",
        "critical": True,
    },
    "ollama": {
        "type": "http",
        "url": "http://localhost:11434/api/tags",
        "restart_cmd": ["ollama", "serve"],
        "log": "/tmp/ollama.log",
        "critical": True,
    },
    "rudibot_army": {
        "type": "process",
        "name": "army_commander.py",
        "restart_cmd": [sys.executable, str(BASE_DIR / "rudibot-army" / "army_commander.py")],
        "log": "/tmp/rudibot-army.log",
        "critical": False,
    },
}

# Optionaler externer Telegram-Bot
_TELEGRAM_BOT_DIR = _ext("TELEGRAM_BOT_DIR", "telegram-automation-bot")
if Path(_TELEGRAM_BOT_DIR).exists():
    WATCHED_SERVICES["telegram_bot"] = {
        "type": "http",
        "url": "http://localhost:3200/health",
        "restart_cmd": ["node", "server.js"],
        "cwd": _TELEGRAM_BOT_DIR,
        "log": "/tmp/telegram-bot.log",
        "critical": False,
    }


def _free_ram():
    """Plattform-sicheres RAM freigeben."""
    try:
        subprocess.run(["sync"], timeout=5)
    except Exception:
        pass


def _detect_high_ram() -> bool:
    if not HAS_PSUTIL:
        return False
    return psutil.virtual_memory().percent > 90


def _detect_high_cpu() -> bool:
    if not HAS_PSUTIL:
        return False
    return psutil.cpu_percent(interval=1) > 95


def _detect_disk_full() -> bool:
    if not HAS_PSUTIL:
        return False
    return psutil.disk_usage("/").percent > 90


def _detect_zombies() -> bool:
    if not HAS_PSUTIL:
        return False
    return sum(1 for p in psutil.process_iter(["status"])
               if p.info.get("status") == "zombie") > 5


AUTO_FIXES = {
    "disk_full": {
        "detect": _detect_disk_full,
        "fix_fn": lambda: subprocess.run(
            ["find", "/tmp", "-name", "*.log", "-mtime", "+3", "-delete"],
            timeout=20
        ),
        "description": "Festplatte voll → alte /tmp Logs bereinigt",
    },
    "high_cpu": {
        "detect": _detect_high_cpu,
        "fix_fn": lambda: subprocess.run(
            ["sh", "-c", "ps aux --sort=-%cpu | head -6 >> /tmp/high_cpu_report.txt"],
            timeout=10
        ),
        "description": "CPU überlastet (>95%) → Top-Prozesse in /tmp/high_cpu_report.txt geloggt",
    },
    "high_ram": {
        "detect": _detect_high_ram,
        "fix_fn": _free_ram,
        "description": "RAM überlastet → sync ausgeführt",
    },
    "zombie_processes": {
        "detect": _detect_zombies,
        "fix_fn": lambda: subprocess.run(
            ["sh", "-c", "kill -s SIGCHLD $(ps -A -ostat,ppid | awk '/[Zz]/{print $2}' | sort -u) 2>/dev/null || true"],
            timeout=10
        ),
        "description": "Zombie-Prozesse erkannt → SIGCHLD an Eltern-Prozesse gesendet",
    },
}


class SelfHealer:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.heal_history: List[Dict] = self._load_json(HEAL_LOG, [])
        self.known_fixes: Dict = self._load_json(KNOWN_FIXES, {})
        self.improvements: List[Dict] = self._load_json(IMPROVE_LOG, [])
        log.info("🔧 SelfHealer initialisiert")

    def _load_json(self, path: Path, default):
        try:
            if path.exists():
                return json.loads(path.read_text())
        except Exception:
            pass
        return default

    def _save_json(self, path: Path, data):
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        except Exception:
            pass

    def _record_fix(self, service: str, problem: str, fix: str, success: bool):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "service": service,
            "problem": problem,
            "fix_applied": fix,
            "success": success,
        }
        self.heal_history.append(entry)
        self.heal_history = self.heal_history[-1000:]
        self._save_json(HEAL_LOG, self.heal_history)

        if success:
            key = hashlib.md5(f"{service}:{problem}".encode()).hexdigest()[:8]
            prev = self.known_fixes.get(key, {})
            self.known_fixes[key] = {
                "service": service, "problem": problem, "fix": fix,
                "success_count": prev.get("success_count", 0) + 1,
                "last_fixed": datetime.now().isoformat(),
            }
            self._save_json(KNOWN_FIXES, self.known_fixes)

    async def _check_http(self, url: str, timeout: int = 5) -> bool:
        if not HAS_AIOHTTP:
            try:
                import urllib.request
                req = urllib.request.urlopen(url, timeout=timeout)
                return req.getcode() < 500
            except Exception:
                return False
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as s:
                async with s.get(url) as r:
                    return r.status < 500
        except Exception:
            return False

    def _check_process(self, name: str) -> bool:
        if not HAS_PSUTIL:
            try:
                r = subprocess.run(
                    ["pgrep", "-f", name], capture_output=True, text=True
                )
                return r.returncode == 0 and bool(r.stdout.strip())
            except Exception:
                return False
        return any(
            name in " ".join(p.info.get("cmdline") or [])
            for p in psutil.process_iter(["cmdline"])
        )

    async def check_service(self, name: str, svc: Dict) -> bool:
        if svc["type"] == "http":
            return await self._check_http(svc["url"])
        elif svc["type"] == "process":
            return self._check_process(svc["name"])
        return True

    async def heal_service(self, name: str, svc: Dict) -> bool:
        log.warning(f"⚠️  {name} ausgefallen — starte Reparatur...")
        cmd = svc.get("restart_cmd", [])
        if not cmd:
            return False
        try:
            log_path = svc.get("log", "/tmp/selfheal.log")
            cwd = svc.get("cwd", str(BASE_DIR))
            with open(log_path, "a") as lf:
                subprocess.Popen(cmd, stdout=lf, stderr=lf,
                                 start_new_session=True, cwd=cwd)
            await asyncio.sleep(4)
            ok = await self.check_service(name, svc)
            self._record_fix(name, "service_down", str(cmd), ok)
            if ok:
                log.info(f"✅ {name} repariert")
            else:
                log.error(f"❌ {name} nicht reparierbar")
            return ok
        except Exception as e:
            self._record_fix(name, "service_down", str(e), False)
            return False

    async def run_auto_fixes(self) -> List[str]:
        applied = []
        for fix_name, fix_def in AUTO_FIXES.items():
            try:
                if fix_def["detect"]():
                    log.warning(f"🔴 Problem: {fix_name}")
                    fix_def["fix_fn"]()
                    applied.append(fix_def["description"])
                    self._record_fix("system", fix_name, fix_name, True)
            except Exception as e:
                log.error(f"Fix {fix_name} Fehler: {e}")
        return applied

    async def scan_logs_for_errors(self) -> List[Dict]:
        errors = []
        log_files = [
            "/tmp/supermegabot.log",
            "/tmp/rudibot-army.log",
            "/tmp/ollama.log",
            "/tmp/telegram-bot.log",
            str(DATA_DIR / "selfheal.log"),
        ]
        patterns = {
            "EADDRINUSE":         "port_conflict",
            "ECONNREFUSED":       "connection_refused",
            "SyntaxError":        "syntax_error",
            "Cannot find module": "missing_module",
            "Out of memory":      "oom",
            "ModuleNotFoundError":"missing_python_module",
            "ConnectionResetError": "connection_reset",
        }
        for lf in log_files:
            try:
                p = Path(lf)
                if not p.exists():
                    continue
                content = p.read_text(errors="ignore")[-5000:]
                for pattern, error_type in patterns.items():
                    if pattern in content:
                        errors.append({"file": lf, "error": error_type, "pattern": pattern})
            except Exception:
                pass
        return errors

    def get_status_summary(self) -> Dict:
        recent_fixes = [h for h in self.heal_history[-50:] if h.get("success")]
        return {
            "total_fixes": len(self.heal_history),
            "recent_fixes": len(recent_fixes),
            "known_problems": len(self.known_fixes),
            "last_fix": self.heal_history[-1] if self.heal_history else None,
        }

    async def daily_improvement(self):
        if not self.heal_history:
            return
        week_ago = datetime.now() - timedelta(days=7)
        recent = [
            h for h in self.heal_history
            if datetime.fromisoformat(h["timestamp"]) > week_ago
        ]
        from collections import Counter
        top = Counter(f"{h['service']}:{h['problem']}" for h in recent).most_common(5)
        entry = {
            "date": datetime.now().isoformat(),
            "week_fixes": len(recent),
            "top_problems": top,
        }
        self.improvements.append(entry)
        self._save_json(IMPROVE_LOG, self.improvements)
        log.info(f"📈 Tages-Analyse: {len(recent)} Fixes. Top: {top[:2]}")

    async def run_forever(self, interval: int = 60):
        log.info(f"🚀 SelfHealer gestartet — prüft alle {interval}s")
        last_daily = datetime.now().date()
        check_count = 0
        while True:
            try:
                check_count += 1
                for svc_name, svc in WATCHED_SERVICES.items():
                    ok = await self.check_service(svc_name, svc)
                    if not ok:
                        await self.heal_service(svc_name, svc)
                fixes = await self.run_auto_fixes()
                if fixes:
                    log.info(f"🔧 Fixes: {fixes}")
                errors = await self.scan_logs_for_errors()
                if errors:
                    log.warning(f"⚠️  Log-Fehler: {[e['error'] for e in errors]}")
                today = datetime.now().date()
                if today > last_daily:
                    await self.daily_improvement()
                    last_daily = today
            except Exception as e:
                log.error(f"❌ SelfHealer Fehler: {e}")
            await asyncio.sleep(interval)


async def main():
    healer = SelfHealer()
    await healer.run_forever(interval=60)


if __name__ == "__main__":
    asyncio.run(main())
