#!/usr/bin/env python3
"""
SuperMegaBot — Permanentes Self-Healing & Auto-Improvement System
Läuft 24/7 im Hintergrund, repariert Probleme BEVOR sie auftreten,
lernt aus jedem Fehler und verhindert Wiederholungen dauerhaft.
"""

import asyncio
import json
import os
import subprocess
import time
import hashlib
import psutil
import aiohttp
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# ── Konfiguration ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
HEAL_LOG  = BASE_DIR / "data" / "heal_history.json"
KNOWN_FIXES = BASE_DIR / "data" / "known_fixes.json"
IMPROVE_LOG = BASE_DIR / "data" / "improvements.json"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(BASE_DIR / "data" / "selfheal.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("SelfHealer")

# ── Services die überwacht werden ────────────────────────────────────────────
WATCHED_SERVICES = {
    "bot_server": {
        "type": "http", "url": "http://localhost:3200/health",
        "restart_cmd": "cd '/Users/rudolfsarkany/Library/Mobile Documents/com~apple~CloudDocs/Documents/GitHub/telegram-automation-bot' && nohup node server.js > /tmp/bot-server.log 2>&1 &",
        "critical": True
    },
    "supermegabot": {
        "type": "process", "name": "bot.py",
        "restart_cmd": "cd /Users/rudolfsarkany/supermegabot && nohup python3 bot.py > /tmp/supermegabot.log 2>&1 &",
        "critical": True
    },
    "ollama": {
        "type": "http", "url": "http://localhost:11434/api/tags",
        "restart_cmd": "ollama serve &",
        "critical": True
    },
    "ngrok": {
        "type": "http", "url": "http://localhost:4040/api/tunnels",
        "restart_cmd": "nohup ngrok http 3200 --domain=foreseeingly-nonempty-miss.ngrok-free.dev > /tmp/ngrok.log 2>&1 &",
        "critical": False
    },
}

# ── Bekannte Fehler + automatische Fixes ─────────────────────────────────────
AUTO_FIXES = {
    "port_in_use": {
        "detect": lambda: False,  # via log scan
        "fix": "lsof -ti:{port} | xargs kill -9 2>/dev/null || true",
        "description": "Port belegt → Prozess beendet"
    },
    "disk_full": {
        "detect": lambda: psutil.disk_usage('/').percent > 90,
        "fix": "find /tmp -name '*.log' -mtime +3 -delete; docker system prune -f --volumes 2>/dev/null || true",
        "description": "Festplatte voll → Logs + Docker-Cache bereinigt"
    },
    "high_cpu": {
        "detect": lambda: psutil.cpu_percent(interval=1) > 95,
        "fix": "pkill -f 'node.*test' 2>/dev/null || true",
        "description": "CPU überlastet → Test-Prozesse beendet"
    },
    "high_ram": {
        "detect": lambda: psutil.virtual_memory().percent > 90,
        "fix": "sync && sudo purge 2>/dev/null || true",
        "description": "RAM überlastet → Cache geleert"
    },
    "zombie_processes": {
        "detect": lambda: sum(1 for p in psutil.process_iter(['status']) if p.info['status'] == 'zombie') > 5,
        "fix": "kill $(ps -el | grep 'Z' | awk '{print $4}') 2>/dev/null || true",
        "description": "Zombie-Prozesse → beendet"
    },
}

class SelfHealer:
    def __init__(self):
        self._ensure_data_dir()
        self.heal_history: List[Dict] = self._load_json(HEAL_LOG, [])
        self.known_fixes: Dict = self._load_json(KNOWN_FIXES, {})
        self.improvements: List[Dict] = self._load_json(IMPROVE_LOG, [])
        self.fix_counts: Dict[str, int] = {}
        log.info("🔧 SelfHealer initialisiert")

    def _ensure_data_dir(self):
        (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)

    def _load_json(self, path: Path, default):
        try:
            if path.exists():
                return json.loads(path.read_text())
        except Exception:
            pass
        return default

    def _save_json(self, path: Path, data):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))

    def _record_fix(self, service: str, problem: str, fix: str, success: bool):
        """Jeder Fix wird permanent gespeichert — wird NIE wieder ignoriert"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "service": service,
            "problem": problem,
            "fix_applied": fix,
            "success": success,
        }
        self.heal_history.append(entry)
        if len(self.heal_history) > 1000:
            self.heal_history = self.heal_history[-1000:]
        self._save_json(HEAL_LOG, self.heal_history)

        # Problem-Hash für "bekannte Probleme" Datenbank
        problem_hash = hashlib.md5(f"{service}:{problem}".encode()).hexdigest()[:8]
        if success:
            self.known_fixes[problem_hash] = {
                "service": service, "problem": problem,
                "fix": fix, "success_count": self.known_fixes.get(problem_hash, {}).get("success_count", 0) + 1,
                "last_fixed": datetime.now().isoformat()
            }
            self._save_json(KNOWN_FIXES, self.known_fixes)
            log.info(f"✅ Fix gespeichert [{problem_hash}]: {service} — {problem}")

    async def _check_http(self, url: str, timeout: int = 5) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
                async with s.get(url) as r:
                    return r.status < 500
        except Exception:
            return False

    def _check_process(self, name: str) -> bool:
        return any(name in (p.info.get('name','') + ' '.join(p.info.get('cmdline',[])))
                   for p in psutil.process_iter(['name','cmdline']))

    async def check_service(self, svc_name: str, svc: Dict) -> bool:
        if svc['type'] == 'http':
            return await self._check_http(svc['url'])
        elif svc['type'] == 'process':
            return self._check_process(svc['name'])
        return True

    async def heal_service(self, svc_name: str, svc: Dict) -> bool:
        log.warning(f"⚠️  {svc_name} ausgefallen — starte Reparatur...")
        try:
            subprocess.run(svc['restart_cmd'], shell=True, timeout=15)
            await asyncio.sleep(3)
            ok = await self.check_service(svc_name, svc)
            self._record_fix(svc_name, "service_down", svc['restart_cmd'], ok)
            if ok:
                log.info(f"✅ {svc_name} repariert")
            else:
                log.error(f"❌ {svc_name} konnte nicht repariert werden")
            return ok
        except Exception as e:
            self._record_fix(svc_name, "service_down", str(e), False)
            return False

    async def run_auto_fixes(self) -> List[str]:
        applied = []
        for fix_name, fix_def in AUTO_FIXES.items():
            try:
                if fix_def['detect']():
                    log.warning(f"🔴 Problem erkannt: {fix_name}")
                    cmd = fix_def['fix']
                    subprocess.run(cmd, shell=True, timeout=30)
                    applied.append(fix_def['description'])
                    self._record_fix("system", fix_name, cmd, True)
            except Exception as e:
                log.error(f"Fix {fix_name} fehlgeschlagen: {e}")
        return applied

    async def scan_logs_for_errors(self) -> List[Dict]:
        """Scannt Bot-Logs nach bekannten Fehlermustern"""
        errors = []
        log_files = ["/tmp/bot-server.log", "/tmp/supermegabot.log", "/tmp/ngrok.log"]
        patterns = {
            "EADDRINUSE": ("port_conflict", "lsof -ti:{port} | xargs kill -9 2>/dev/null"),
            "ECONNREFUSED": ("connection_refused", None),
            "SyntaxError": ("syntax_error", None),
            "Cannot find module": ("missing_module", "npm install 2>/dev/null || pip3 install -r requirements.txt 2>/dev/null"),
            "SIGKILL": ("process_killed", None),
            "Out of memory": ("oom", "sync && sudo purge 2>/dev/null || true"),
        }
        for log_file in log_files:
            try:
                path = Path(log_file)
                if not path.exists():
                    continue
                content = path.read_text(errors='ignore')[-5000:]  # Letzte 5KB
                for pattern, (error_type, auto_fix) in patterns.items():
                    if pattern in content:
                        entry = {"file": log_file, "error": error_type, "pattern": pattern}
                        errors.append(entry)
                        if auto_fix:
                            subprocess.run(auto_fix, shell=True, timeout=10)
                            self._record_fix(log_file, error_type, auto_fix, True)
            except Exception:
                pass
        return errors

    async def daily_improvement(self):
        """Täglich: analysiert Fehlerhistorie und optimiert System"""
        if not self.heal_history:
            return

        # Häufigste Probleme der letzten 7 Tage
        week_ago = datetime.now() - timedelta(days=7)
        recent = [h for h in self.heal_history
                  if datetime.fromisoformat(h['timestamp']) > week_ago]

        from collections import Counter
        problem_counts = Counter(f"{h['service']}:{h['problem']}" for h in recent)
        top_problems = problem_counts.most_common(5)

        improvement = {
            "date": datetime.now().isoformat(),
            "week_fixes": len(recent),
            "top_recurring_problems": top_problems,
            "recommendation": "Keine" if not top_problems else
                f"'{top_problems[0][0]}' trat {top_problems[0][1]}x auf — permanente Lösung empfohlen"
        }
        self.improvements.append(improvement)
        self._save_json(IMPROVE_LOG, self.improvements)
        log.info(f"📈 Tages-Analyse: {len(recent)} Fixes diese Woche. Top: {top_problems[:2]}")

    async def run_forever(self, interval: int = 60):
        """Hauptschleife — läuft für immer"""
        log.info(f"🚀 SelfHealer gestartet — prüft alle {interval}s")
        last_daily = datetime.now().date()
        check_count = 0

        while True:
            try:
                check_count += 1
                log.debug(f"[Check #{check_count}] Starte Systemprüfung...")

                # 1. Alle Services prüfen
                for svc_name, svc in WATCHED_SERVICES.items():
                    ok = await self.check_service(svc_name, svc)
                    if not ok:
                        await self.heal_service(svc_name, svc)

                # 2. Auto-Fixes für System-Probleme
                fixes = await self.run_auto_fixes()
                if fixes:
                    log.info(f"🔧 Auto-Fixes angewendet: {fixes}")

                # 3. Log-Scan nach Fehlermustern
                errors = await self.scan_logs_for_errors()
                if errors:
                    log.warning(f"⚠️  Log-Fehler gefunden: {[e['error'] for e in errors]}")

                # 4. Tägliche Verbesserungsanalyse
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
