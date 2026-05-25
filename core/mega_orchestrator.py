#!/usr/bin/env python3
"""
SuperMegaBot - Indestructible AI Orchestrator
95% local processing via Ollama | Self-healing | Never breaks
"""

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import sqlite3

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed; env vars must be set externally

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "megabot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("MegaOrchestrator")

OLLAMA_BASE = os.getenv("OLLAMA_HOST", "http://localhost:11434")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


# ---------------------------------------------------------------------------
# Memory System (SQLite - 100% local)
# ---------------------------------------------------------------------------

class MemorySystem:
    def __init__(self):
        self.db_path = DATA_DIR / "memory.db"
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                timestamp TEXT,
                context TEXT
            );
            CREATE TABLE IF NOT EXISTS learned_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                key TEXT UNIQUE,
                value TEXT,
                confidence REAL DEFAULT 1.0,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS repair_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_pattern TEXT,
                solution TEXT,
                success INTEGER,
                attempts INTEGER DEFAULT 1,
                last_used TEXT
            );
            CREATE TABLE IF NOT EXISTS task_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT,
                result TEXT,
                duration_ms INTEGER,
                timestamp TEXT
            );
        """)
        conn.commit()
        conn.close()

    def save_message(self, session_id: str, role: str, content: str, context: str = ""):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO conversations (session_id,role,content,timestamp,context) VALUES (?,?,?,?,?)",
            (session_id, role, content, datetime.now().isoformat(), context),
        )
        conn.commit()
        conn.close()

    def get_history(self, session_id: str, limit: int = 20) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT role,content,timestamp FROM conversations WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        conn.close()
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]

    def learn_fact(self, category: str, key: str, value: str, confidence: float = 1.0):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO learned_facts (category,key,value,confidence,updated_at) VALUES (?,?,?,?,?)",
            (category, key, value, confidence, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

    def get_fact(self, key: str) -> Optional[str]:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT value FROM learned_facts WHERE key=?", (key,)).fetchone()
        conn.close()
        return row[0] if row else None

    def save_repair(self, error_pattern: str, solution: str, success: bool):
        conn = sqlite3.connect(self.db_path)
        existing = conn.execute(
            "SELECT id, attempts FROM repair_history WHERE error_pattern=? AND solution=?",
            (error_pattern, solution),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE repair_history SET success=?,attempts=?,last_used=? WHERE id=?",
                (int(success), existing[1] + 1, datetime.now().isoformat(), existing[0]),
            )
        else:
            conn.execute(
                "INSERT INTO repair_history (error_pattern,solution,success,last_used) VALUES (?,?,?,?)",
                (error_pattern, solution, int(success), datetime.now().isoformat()),
            )
        conn.commit()
        conn.close()

    def get_best_repair(self, error_pattern: str) -> Optional[str]:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT solution FROM repair_history WHERE error_pattern LIKE ? AND success=1 ORDER BY attempts DESC LIMIT 1",
            (f"%{error_pattern[:50]}%",),
        ).fetchone()
        conn.close()
        return row[0] if row else None


# ---------------------------------------------------------------------------
# Ollama Client (local AI - zero cost)
# ---------------------------------------------------------------------------

class OllamaClient:
    MODELS = {
        "fast": "llama3.2:latest",
        "smart": "llama3.2:latest",
        "code": "codellama:latest",
        "analysis": "mistral:latest",
    }

    def __init__(self):
        self.base = OLLAMA_BASE
        self.available_models: List[str] = []

    async def check_health(self) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
                async with s.get(f"{self.base}/api/tags") as r:
                    if r.status == 200:
                        data = await r.json()
                        self.available_models = [m["name"] for m in data.get("models", [])]
                        return True
        except Exception:
            pass
        return False

    def _pick_model(self, task: str) -> str:
        for key, model in self.MODELS.items():
            for m in self.available_models:
                if model.split(":")[0] in m:
                    if key == task:
                        return m
        # fallback: first available
        return self.available_models[0] if self.available_models else "llama3.2:latest"

    async def chat(self, messages: List[Dict], task: str = "smart", stream: bool = False) -> str:
        model = self._pick_model(task)
        payload = {"model": model, "messages": messages, "stream": False}
        prompt_fallback = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
        ) + "\nassistant:"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
                async with s.post(f"{self.base}/api/chat", json=payload) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("message", {}).get("content", "")
                    # Fallback: try generate endpoint before returning a hard error.
                    alt = await self.generate(prompt_fallback, task="fast")
                    if alt and not alt.startswith("Error:") and not alt.startswith("Offline:"):
                        return alt
                    detail = await r.text()
                    return f"Ollama temporär nicht verfügbar (HTTP {r.status}): {detail[:160]}"
        except Exception as e:
            alt = await self.generate(prompt_fallback, task="fast")
            if alt and not alt.startswith("Error:") and not alt.startswith("Offline:"):
                return alt
            return f"Ollama unavailable: {e}"

    async def generate(self, prompt: str, task: str = "fast") -> str:
        model = self._pick_model(task)
        payload = {"model": model, "prompt": prompt, "stream": False}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
                async with s.post(f"{self.base}/api/generate", json=payload) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("response", "")
                    return f"Error: {r.status}"
        except Exception as e:
            return f"Offline: {e}"


# ---------------------------------------------------------------------------
# Self-Healing Engine
# ---------------------------------------------------------------------------

class SelfHealingEngine:
    def __init__(self, memory: MemorySystem, ai: OllamaClient):
        self.memory = memory
        self.ai = ai
        self.repair_attempts: Dict[str, int] = {}
        self.MAX_ATTEMPTS = 10

    async def heal(self, error: Exception, context: str, retry_fn=None) -> Dict:
        error_key = type(error).__name__ + str(error)[:80]
        attempts = self.repair_attempts.get(error_key, 0) + 1
        self.repair_attempts[error_key] = attempts

        log.warning(f"[HEAL] Attempt {attempts}/{self.MAX_ATTEMPTS} for: {error_key[:60]}")

        # Check known solutions first
        known = self.memory.get_best_repair(error_key)
        if known:
            log.info(f"[HEAL] Using known solution: {known[:80]}")
            solution = known
        else:
            # Ask Ollama to diagnose
            prompt = f"""System error in context: {context}
Error: {type(error).__name__}: {str(error)[:200]}
Traceback: {traceback.format_exc()[-500:]}

Provide a SHORT repair solution (1-3 steps, Python code if needed):"""
            solution = await self.ai.generate(prompt, task="code")
            log.info(f"[HEAL] AI solution: {solution[:120]}")

        result = {"success": False, "solution": solution, "attempts": attempts}

        # Execute repair steps automatically
        repair_actions = self._parse_repair_actions(solution)
        for action in repair_actions:
            try:
                success = await self._execute_repair_action(action)
                if success:
                    result["success"] = True
                    self.memory.save_repair(error_key, solution, True)
                    log.info(f"[HEAL] Repair successful after {attempts} attempts")
                    break
            except Exception as inner_e:
                log.error(f"[HEAL] Repair action failed: {inner_e}")

        if not result["success"]:
            self.memory.save_repair(error_key, solution, False)

        # If retry function provided and repair was successful, retry
        if result["success"] and retry_fn and attempts < self.MAX_ATTEMPTS:
            try:
                retry_result = await retry_fn()
                result["retry_result"] = retry_result
            except Exception as retry_err:
                result["retry_error"] = str(retry_err)

        return result

    def _parse_repair_actions(self, solution: str) -> List[str]:
        actions = []
        lines = solution.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("pip install") or line.startswith("pip3 install"):
                actions.append(line)
            elif line.startswith("brew install"):
                actions.append(line)
            elif line.startswith("npm install"):
                actions.append(line)
        return actions

    async def _execute_repair_action(self, action: str) -> bool:
        import subprocess
        try:
            result = subprocess.run(
                action, shell=True, capture_output=True, text=True, timeout=120
            )
            return result.returncode == 0
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Command Router
# ---------------------------------------------------------------------------

class CommandRouter:
    def __init__(self, orchestrator: "MegaOrchestrator"):
        self.bot = orchestrator
        self.routes: Dict[str, Any] = {}
        self._register_routes()

    def _register_routes(self):
        self.routes = {
            # Mac control
            "screenshot": self._cmd_screenshot,
            "screenshot machen": self._cmd_screenshot,
            "bildschirm": self._cmd_screenshot,
            # System
            "status": self._cmd_status,
            "system status": self._cmd_status,
            "prozesse": self._cmd_processes,
            "speicher": self._cmd_disk,
            # Trading
            "arbitrage": self._cmd_arbitrage,
            "preise": self._cmd_prices,
            "trading": self._cmd_arbitrage,
            # Browser
            "öffne browser": self._cmd_open_browser,
            "browser": self._cmd_open_browser,
            # Finance
            "finanzen": self._cmd_finances,
            "abos": self._cmd_subscriptions,
            # Help
            "hilfe": self._cmd_help,
            "help": self._cmd_help,
            "/help": self._cmd_help,
            "/start": self._cmd_start,
            # GMC / Google Merchant Center
            "/gmc_status": self._cmd_gmc_status,
            "/produkte": self._cmd_produkte,
            "/ads": self._cmd_ads,
            # API Builder
            "/api_liste": self._cmd_api,
            "/api_list": self._cmd_api,
            "/api_test": self._cmd_api,
            "/api_test_alle": self._cmd_api,
            "/api_info": self._cmd_api,
            "/api_neu": self._cmd_api,
            "/api_ersetze": self._cmd_api,
            "/api_regeln": self._cmd_api,
            "/api_hilfe": self._cmd_api,
            "/api_help": self._cmd_api,
            "api liste": self._cmd_api,
            "api test": self._cmd_api,
            "api hilfe": self._cmd_api,
            # ── MEGA HUB ────────────────────────────────────────────────────
            "/hub": self._cmd_hub,
            "/hub_status": self._cmd_hub,
            "/prozesse": self._cmd_hub,
            "/procs": self._cmd_hub,
            "hub": self._cmd_hub,
            "alles": self._cmd_hub,
            "alle systeme": self._cmd_hub,
            # PM2
            "/pm2": self._cmd_hub,
            "/pm2_status": self._cmd_hub,
            "/pm2_restart": self._cmd_hub,
            "/pm2_start": self._cmd_hub,
            "/pm2_stop": self._cmd_hub,
            "/pm2_logs": self._cmd_hub,
            "/pm2_save": self._cmd_hub,
            # Geheimwaffe
            "/waffe": self._cmd_hub,
            "/geheimwaffe": self._cmd_hub,
            "/waffe_run": self._cmd_hub,
            "/waffe_produkte": self._cmd_hub,
            "/waffe_content": self._cmd_hub,
            "/waffe_analytics": self._cmd_hub,
            "/waffe_seo": self._cmd_hub,
            "/shopify_analytics": self._cmd_hub,
            "/seo": self._cmd_hub,
            # Autopilot Agents
            "/autopilot": self._cmd_hub,
            "/autopilot_run": self._cmd_hub,
            "/autopilot_logs": self._cmd_hub,
            "/agenten": self._cmd_hub,
            "/agent": self._cmd_hub,
            # RudiBot Army
            "/army": self._cmd_hub,
            "/army_status": self._cmd_hub,
            "/army_start": self._cmd_hub,
            "/army_stop": self._cmd_hub,
            "/army_events": self._cmd_hub,
            "army": self._cmd_hub,
            # ImmortalBot
            "/immortal": self._cmd_hub,
            "/immortal_status": self._cmd_hub,
            "/immortal_start": self._cmd_hub,
            "/immortal_stop": self._cmd_hub,
            "/immortal_brain": self._cmd_hub,
            "/brain": self._cmd_hub,
            # Password-Sync
            "/pw": self._cmd_hub,
            "/pw_status": self._cmd_hub,
            "/pw_stats": self._cmd_hub,
            "/passwortsync": self._cmd_hub,
            # Self-Learner (eigene Routen — NICHT Hub)
            "/learner": self._cmd_learner,
            "/learner_status": self._cmd_learner,
            "/skills": self._cmd_learner,
            "/kann_ich": self._cmd_learner,
            "/lerne": self._cmd_learner,
            "/lerne_api": self._cmd_learner,
            "/api_finde": self._cmd_learner,
            "/skill_del": self._cmd_learner,
            "/micro": self._cmd_micro,
            "/micro_status": self._cmd_micro,
            "/micro_ping": self._cmd_micro,
            "/army_micro": self._cmd_micro,
            # Hub Hilfe
            "/hub_hilfe": self._cmd_hub,
            "/hub_help": self._cmd_hub,
            "hub hilfe": self._cmd_hub,
        }

    async def route(self, text: str, session_id: str) -> str:
        text_lower = text.lower().strip()

        # Direct route match
        for key, handler in self.routes.items():
            if text_lower.startswith(key):
                return await handler(text, session_id)

        # AI chat fallback (local Ollama)
        return await self._cmd_ai_chat(text, session_id)

    async def _cmd_screenshot(self, text, session_id) -> str:
        try:
            from modules.mac_controller import MacController
            mac = MacController()
            path = await mac.take_screenshot()
            return f"Screenshot gespeichert: {path}"
        except Exception as e:
            return f"Screenshot fehlgeschlagen: {e}"

    async def _cmd_status(self, text, session_id) -> str:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return (
                f"System Status:\n"
                f"CPU: {cpu}%\n"
                f"RAM: {mem.percent}% ({mem.used//1024//1024//1024}GB/{mem.total//1024//1024//1024}GB)\n"
                f"Disk: {disk.percent}% ({disk.free//1024//1024//1024}GB frei)\n"
                f"Ollama: {'Online' if await self.bot.ai.check_health() else 'Offline'}"
            )
        except ImportError:
            return "psutil nicht installiert. Führe: pip install psutil"

    async def _cmd_processes(self, text, session_id) -> str:
        try:
            import psutil
            procs = []
            for p in sorted(psutil.process_iter(["pid", "name", "cpu_percent"]), key=lambda x: x.info["cpu_percent"] or 0, reverse=True)[:10]:
                procs.append(f"PID {p.info['pid']}: {p.info['name']} ({p.info['cpu_percent']}%)")
            return "Top Prozesse:\n" + "\n".join(procs)
        except Exception as e:
            return f"Fehler: {e}"

    async def _cmd_disk(self, text, session_id) -> str:
        try:
            import psutil
            result = []
            for part in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    result.append(f"{part.mountpoint}: {usage.percent}% ({usage.free//1024//1024//1024}GB frei)")
                except PermissionError:
                    pass
            return "\n".join(result)
        except Exception as e:
            return f"Fehler: {e}"

    async def _cmd_arbitrage(self, text, session_id) -> str:
        try:
            from modules.trading_bot import TradingBot
            bot = TradingBot()
            opps = await bot.scan_quick()
            if not opps:
                return "Keine Arbitrage-Möglichkeiten gefunden (< 0.5% Profit)"
            lines = [f"Arbitrage Scan ({len(opps)} Treffer):"]
            for o in opps[:5]:
                lines.append(f"  {o['pair']}: {o['exchange_buy']} → {o['exchange_sell']} = {o['profit_pct']:.2f}%")
            return "\n".join(lines)
        except Exception as e:
            return f"Trading Bot Fehler: {e}"

    async def _cmd_prices(self, text, session_id) -> str:
        try:
            from modules.trading_bot import TradingBot
            bot = TradingBot()
            prices = await bot.get_quick_prices()
            lines = ["Aktuelle Preise:"]
            for pair, data in list(prices.items())[:6]:
                lines.append(f"  {pair}: ${data.get('avg', 0):,.2f}")
            return "\n".join(lines)
        except Exception as e:
            return f"Preis-Fehler: {e}"

    async def _cmd_open_browser(self, text, session_id) -> str:
        url = text.replace("öffne browser", "").replace("browser", "").strip()
        if not url:
            url = "https://google.com"
        try:
            import subprocess
            subprocess.Popen(["open", "-a", "Safari", url])
            return f"Browser geöffnet: {url}"
        except Exception as e:
            return f"Fehler: {e}"

    async def _cmd_finances(self, text, session_id) -> str:
        return (
            "Finanz-Funktionen verfügbar:\n"
            "• 'abos' - Abonnements anzeigen/kündigen\n"
            "• 'arbitrage' - Krypto-Arbitrage scannen\n"
            "• 'preise' - Aktuelle Krypto-Preise\n"
            "Tippe einen Befehl für Details."
        )

    async def _cmd_subscriptions(self, text, session_id) -> str:
        try:
            from modules.mac_controller import MacController
            mac = MacController()
            return await mac.list_subscriptions()
        except Exception as e:
            return f"Abo-Check Fehler: {e}"

    async def _cmd_ai_chat(self, text, session_id) -> str:
        history = self.bot.memory.get_history(session_id, limit=10)
        messages = [
            {
                "role": "system",
                "content": (
                    "Du bist SuperMegaBot, ein superintelligenter KI-Assistent für Mac. "
                    "Du hast Zugriff auf: Mac-Steuerung, Browser, Trading, Shopify, Telegram. "
                    "Antworte auf Deutsch. Sei präzise und hilfreich."
                ),
            }
        ]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": text})

        response = await self.bot.ai.chat(messages, task="smart")

        self.bot.memory.save_message(session_id, "user", text)
        self.bot.memory.save_message(session_id, "assistant", response)

        return response

    async def _cmd_gmc_status(self, text, session_id) -> str:
        try:
            from modules.gmc_monitor import format_telegram_status
            return await format_telegram_status()
        except Exception as e:
            return f"GMC Status Fehler: {e}"

    async def _cmd_produkte(self, text, session_id) -> str:
        try:
            from modules.gmc_monitor import get_shopify_product_count
            products = await get_shopify_product_count()
            total = products.get("total", products.get("count", "?"))
            active = products.get("active", "?")
            draft = products.get("draft", "?")
            return (
                f"Produkte:\n"
                f"  Gesamt: {total}\n"
                f"  Aktiv: {active}\n"
                f"  Entwurf: {draft}"
            )
        except Exception as e:
            return f"Produkte Fehler: {e}"

    async def _cmd_ads(self, text, session_id) -> str:
        try:
            from modules.campaign_manager import get_campaigns, format_telegram_ads
            campaigns = await get_campaigns()
            return format_telegram_ads(campaigns)
        except Exception as e:
            return f"Ads Fehler: {e}"

    async def _cmd_api(self, text: str, session_id: str) -> str:
        try:
            from modules.api_builder import get_manager
            mgr = get_manager()
            return await mgr.dispatch(text)
        except Exception as e:
            return f"API Builder Fehler: {e}"

    async def _cmd_hub(self, text: str, session_id: str) -> str:
        try:
            from modules.mega_hub import get_hub
            hub = get_hub()
            return await hub.dispatch(text)
        except Exception as e:
            return f"Hub Fehler: {e}"

    async def _cmd_learner(self, text: str, session_id: str) -> str:
        try:
            import sys, os
            sys.path.insert(0, os.path.expanduser("~"))
            # Tokens laden
            from pathlib import Path
            env_file = Path("/Users/rudolfsarkany/Library/Mobile Documents/com~apple~CloudDocs/Documents/GitHub/telegram-automation-bot/.env")
            if env_file.exists():
                for line in env_file.read_text(errors="ignore").splitlines():
                    if "=" in line and not line.strip().startswith("#"):
                        k, _, v = line.partition("=")
                        if not os.environ.get(k.strip()):
                            os.environ[k.strip()] = v.strip()
            from self_learner_core import SelfLearner
            if not hasattr(self, "_learner"):
                self._learner = SelfLearner("supermegabot", telegram_notify=True)
                self._learner.load_learned_skills()
            # Befehl extrahieren: "/learner" → "/status", direkter Befehl weiterleiten
            cmd = text.strip()
            if cmd in ("/learner", "/learner_status"):
                cmd = "/status"
            return self._learner.handle_command(cmd)
        except Exception as e:
            return f"Learner Fehler: {e}"

    async def _cmd_micro(self, text: str, session_id: str) -> str:
        try:
            import json, os
            from pathlib import Path
            state_file = Path(os.path.expanduser("~/rudibot-army/shared/army_state.json"))
            state = json.loads(state_file.read_text(errors="ignore")) if state_file.exists() else {}
            agents = state.get("agents", {})
            micro_ids = ["micro_ping", "micro_revenue", "micro_backup", "micro_clean", "micro_ai"]
            lines = ["🤖 <b>Micro Bots Status:</b>\n"]
            icons = {"micro_ping":"🏓","micro_revenue":"💸","micro_backup":"💾","micro_clean":"🧹","micro_ai":"🤖"}
            for mid in micro_ids:
                info = agents.get(mid, {})
                s = info.get("status", "?")
                si = {"ok":"✅","warning":"⚠️","error":"❌"}.get(s, "❓")
                msg = info.get("message", "Keine Daten")[:50]
                lines.append(f"{icons.get(mid,'•')} {mid}: {si} {msg}")
            return "\n".join(lines)
        except Exception as e:
            return f"Micro Status Fehler: {e}"

    async def _cmd_help(self, text, session_id) -> str:
        return """SuperMegaBot Befehle:

  System:
    status          - CPU/RAM/Disk anzeigen
    prozesse        - Top Prozesse
    speicher        - Disk Nutzung
    screenshot      - Screenshot machen

  Trading:
    arbitrage       - Krypto-Arbitrage scannen
    preise          - Aktuelle Preise

  Browser & Mac:
    browser <url>   - Browser öffnen
    abos            - Abonnements verwalten

  KI-Chat:
    Alles andere → Ollama KI (100% lokal, kostenlos)

  GMC & Ads:
    /gmc_status     - Google Merchant Center Status
    /produkte       - Shopify Produktanzahl
    /ads            - Google Ads Kampagnen

  API Builder:
    /api_liste        - alle konfigurierten APIs
    /api_test <name>  - API live testen
    /api_test_alle    - alle APIs auf einmal testen
    /api_info <name>  - Details & Env-Keys
    /api_neu <id> <url> <auth> [key]  - neuen Client generieren
    /api_ersetze <datei> <alt> <neu>  - API in Modul tauschen
    /api_regeln       - Ersetzungsregeln anzeigen

  🏠 MEGA HUB (alles steuern):
    /hub              - Komplett-Status aller Systeme
    /pm2              - PM2 Prozesse
    /pm2_restart <name> /pm2_start <name> /pm2_stop <name>
    /pm2_logs <name>  - Logs eines Prozesses
    /waffe_run <nische> - Geheimwaffe Full-Automation
    /waffe_produkte   - Winning Products finden
    /waffe_content <produkt> - Content generieren
    /waffe_analytics  - Shopify Analytics
    /autopilot        - KI-Agenten anzeigen
    /agent <id> <aufgabe> - Agenten beauftragen
    /army             - RudiBot Army Status
    /army_start       - Army starten
    /immortal         - EternalImmortalBot Status
    /immortal_brain   - Brain-Statistiken
    /pw               - Password-Sync Status
    /learner          - Self-Learner Status
    /hub_hilfe        - alle Hub-Befehle

  🧠 SELF-LEARNER (Skills anlernen):
    /skills           - alle gelernten Skills
    /kann_ich         - Selbstanalyse aller Fähigkeiten
    /lerne <beschr>   - neuen Skill anlernen
    /lerne_api <beschr> - API-Integration hinzufügen
    /api_finde <aufg> - beste freie API finden
    /skill_del <name> - Skill löschen

  🤖 MICRO BOTS:
    /micro            - Status aller 5 Micro Bots
    /micro_status     - Ping, Revenue, Backup, Clean, AI

  Kosten: 95% lokal (Ollama), 5% externe APIs"""

    async def _cmd_start(self, text, session_id) -> str:
        return (
            "SuperMegaBot gestartet!\n"
            "Ich bin dein lokaler KI-Assistent.\n"
            "Tippe 'hilfe' für alle Befehle.\n\n"
            "Aktive Module:\n"
            "✓ Ollama KI (lokal)\n"
            "✓ Mac Controller\n"
            "✓ Browser Automation\n"
            "✓ Trading Bot\n"
            "✓ Self-Healing\n"
            "✓ Persistentes Gedächtnis"
        )


# ---------------------------------------------------------------------------
# Telegram Sender
# ---------------------------------------------------------------------------

async def send_telegram(text: str, chat_id: str = None, token: str = None):
    token = token or TELEGRAM_TOKEN
    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(url, json=payload)
    except Exception as e:
        log.error(f"Telegram send error: {e}")


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

class MegaOrchestrator:
    def __init__(self):
        self.memory = MemorySystem()
        self.ai = OllamaClient()
        self.healer = SelfHealingEngine(self.memory, self.ai)
        self.router = CommandRouter(self)
        self.running = True
        log.info("MegaOrchestrator initialized")

    async def start(self):
        log.info("Starting SuperMegaBot...")

        # Check Ollama
        ollama_ok = await self.ai.check_health()
        if ollama_ok:
            log.info(f"Ollama OK - Models: {self.ai.available_models}")
        else:
            log.warning("Ollama offline - will retry in background")

        # Start health monitor
        asyncio.create_task(self._health_loop())
        # Start Telegram polling
        asyncio.create_task(self._telegram_polling_loop())

        log.info("SuperMegaBot is RUNNING")
        await send_telegram("SuperMegaBot gestartet! Tippe /help")

    async def process(self, text: str, session_id: str = "default") -> str:
        start = time.time()
        try:
            result = await self.router.route(text, session_id)
            ms = int((time.time() - start) * 1000)
            conn = sqlite3.connect(DATA_DIR / "memory.db")
            conn.execute(
                "INSERT INTO task_history (task,result,duration_ms,timestamp) VALUES (?,?,?,?)",
                (text[:200], result[:500], ms, datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
            return result
        except Exception as e:
            log.error(f"Process error: {e}")
            repair = await self.healer.heal(e, f"processing command: {text[:100]}")
            if repair["success"]:
                return await self.router.route(text, session_id)
            return f"Fehler (wird repariert): {type(e).__name__}: {str(e)[:100]}"

    async def _health_loop(self):
        while self.running:
            try:
                await asyncio.sleep(60)
                ollama_ok = await self.ai.check_health()
                if not ollama_ok:
                    log.warning("Ollama down - attempting restart")
                    import subprocess
                    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                log.error(f"Health loop error: {e}")

    async def _telegram_polling_loop(self):
        if not TELEGRAM_TOKEN:
            log.warning("No Telegram token - polling disabled")
            return

        # Webhook löschen (verhindert Konflikt mit Polling)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                del_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook"
                async with s.post(del_url, json={"drop_pending_updates": False}) as r:
                    result = await r.json()
                    if result.get("ok"):
                        log.info("Telegram webhook gelöscht - Polling aktiv")
                    else:
                        log.warning(f"Webhook delete: {result}")
        except Exception as e:
            log.warning(f"Webhook delete fehlgeschlagen: {type(e).__name__}: {e}")

        offset = 0
        retry_wait = 5
        log.info("Telegram polling gestartet")
        while self.running:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
                params = {"offset": offset, "timeout": 30, "limit": 10, "allowed_updates": ["message"]}
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35)) as s:
                    async with s.get(url, params=params) as r:
                        if r.status == 200:
                            data = await r.json()
                            if not data.get("ok"):
                                log.error(f"Telegram API Fehler: {data.get('description','?')} (code={data.get('error_code')})")
                                # Code 409 = Konflikt mit anderem Client (OpenClaw nutzt denselben Token)
                                if data.get("error_code") == 409:
                                    log.warning("KONFLIKT: OpenClaw nutzt denselben Telegram-Token! SuperMegaBot-Polling pausiert (60s).")
                                    await asyncio.sleep(60)
                                    continue
                                await asyncio.sleep(retry_wait)
                                continue
                            retry_wait = 5  # Reset bei Erfolg
                            for update in data.get("result", []):
                                offset = update["update_id"] + 1
                                asyncio.create_task(self._handle_telegram_update(update))
                        elif r.status == 409:
                            body = await r.text()
                            log.warning(f"Token-Konflikt (409): {body[:200]} — pausiere 60s")
                            await asyncio.sleep(60)
                        else:
                            body = await r.text()
                            log.error(f"Telegram HTTP {r.status}: {body[:200]}")
                            await asyncio.sleep(retry_wait)
            except aiohttp.ClientConnectorError as e:
                log.error(f"Telegram Netzwerkfehler: {e} — Kein Internet?")
                await asyncio.sleep(30)
            except asyncio.TimeoutError:
                log.warning("Telegram Timeout — normaler Long-Poll-Ablauf, weiter...")
            except Exception as e:
                log.error(f"Telegram poll Fehler: {type(e).__name__}: {e}")
                await asyncio.sleep(retry_wait)

    async def _handle_telegram_update(self, update: Dict):
        try:
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id", ""))
            user = msg.get("from", {}).get("username", "unknown")

            if not text or not chat_id:
                return

            session_id = f"telegram_{chat_id}"
            log.info(f"Telegram [{user}]: {text[:60]}")

            response = await self.process(text, session_id)
            await send_telegram(response, chat_id=chat_id)
        except Exception as e:
            log.error(f"Telegram handler error: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    bot = MegaOrchestrator()
    await bot.start()

    # Interactive mode if no Telegram token
    if not TELEGRAM_TOKEN:
        print("\nSuperMegaBot Interactive Mode (Ctrl+C to quit)")
        print("Type your command:\n")
        while True:
            try:
                text = input("> ").strip()
                if text:
                    result = await bot.process(text)
                    print(f"\n{result}\n")
            except (KeyboardInterrupt, EOFError):
                print("\nBot stopped.")
                break
    else:
        # Keep alive
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
