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
from typing import Any, Callable, Dict, List, Optional

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

# Guardian Integration
GUARDIAN_AVAILABLE = False
_ETERNAL_DIR = os.getenv("ETERNAL_BOT_DIR", str(Path.home() / "rudibot-eternal"))
try:
    sys.path.insert(0, _ETERNAL_DIR)
    from guardian_integration import guardian
    GUARDIAN_AVAILABLE = True
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "megabot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("MegaOrchestrator")

# Guardian Status melden
if GUARDIAN_AVAILABLE:
    log.info("✅ Guardian Integration loaded")
else:
    log.warning("⚠️ Guardian Integration not available")

OLLAMA_BASE = os.getenv("OLLAMA_HOST", "http://localhost:11434")
# @DudiRudibot — SuperMegaBot Admin Bot (alle 110 Commands)
TELEGRAM_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_BOT_TOKEN_1")
    or os.getenv("TELEGRAM_BOT_TOKEN_2")
    or ""
)
# @RudiCludiBot — Kunden-Bot (Subscriptions, Support)
TELEGRAM_TOKEN_CUSTOMER = os.getenv("TELEGRAM_BOT_TOKEN_2", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


# ---------------------------------------------------------------------------
# Memory System (SQLite - 100% local)
# ---------------------------------------------------------------------------

class MemorySystem:
    """Persistent SQLite-backed memory for conversations, facts, repairs, and task history."""

    def __init__(self) -> None:
        """Initialize the memory database at the configured data directory."""
        self.db_path = DATA_DIR / "memory.db"
        self._init_db()

    def _init_db(self) -> None:
        """Create all required tables if they do not already exist."""
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

    def save_message(self, session_id: str, role: str, content: str, context: str = "") -> None:
        """Persist a single conversation turn for the given session."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO conversations (session_id,role,content,timestamp,context) VALUES (?,?,?,?,?)",
            (session_id, role, content, datetime.now().isoformat(), context),
        )
        conn.commit()
        conn.close()

    def get_history(self, session_id: str, limit: int = 20) -> List[Dict[str, str]]:
        """Return the most recent conversation turns for a session, oldest first."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT role,content,timestamp FROM conversations WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        conn.close()
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]

    def clear_history(self, session_id: str) -> int:
        """Delete all persisted conversation turns for a session and return the deleted row count."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("DELETE FROM conversations WHERE session_id=?", (session_id,))
        conn.commit()
        deleted = cur.rowcount
        conn.close()
        return deleted

    def learn_fact(self, category: str, key: str, value: str, confidence: float = 1.0) -> None:
        """Upsert a named fact so the bot can recall it across sessions."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO learned_facts (category,key,value,confidence,updated_at) VALUES (?,?,?,?,?)",
            (category, key, value, confidence, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

    def get_fact(self, key: str) -> Optional[str]:
        """Retrieve a previously learned fact by key, or None if unknown."""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT value FROM learned_facts WHERE key=?", (key,)).fetchone()
        conn.close()
        return row[0] if row else None

    def save_repair(self, error_pattern: str, solution: str, success: bool) -> None:
        """Record whether an auto-repair solution worked so future errors can reuse it."""
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
        """Return the most-used successful repair solution for a matching error pattern."""
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
        "fast":     os.getenv("OLLAMA_FAST_MODEL",     "llama3.2:latest"),
        "smart":    os.getenv("OLLAMA_SMART_MODEL",    "gemma2:latest"),
        "code":     os.getenv("OLLAMA_CODE_MODEL",     "codellama:latest"),
        "analysis": os.getenv("OLLAMA_ANALYSIS_MODEL", "mistral:latest"),
    }

    def __init__(self) -> None:
        """Set up the Ollama base URL and initialize the available-model cache."""
        self.base: str = OLLAMA_BASE
        self.available_models: List[str] = []

    async def check_health(self) -> bool:
        """Probe the Ollama server and populate the available-model list on success."""
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
        """Select the best locally-available model for the given task tier."""
        for key, model in self.MODELS.items():
            for m in self.available_models:
                if model.split(":")[0] in m:
                    if key == task:
                        return m
        # fallback: first available
        return self.available_models[0] if self.available_models else "llama3.2:latest"

    async def chat(self, messages: List[Dict[str, str]], task: str = "smart", stream: bool = False) -> str:
        """Send a multi-turn chat to Ollama and return the assistant reply as a string."""
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
        """Send a single-turn completion prompt and return the generated text."""
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
    """Diagnoses runtime errors via AI and attempts automatic package-level repairs."""

    def __init__(self, memory: MemorySystem, ai: OllamaClient) -> None:
        """Wire up the memory store and AI client used for diagnosis and repair logging."""
        self.memory = memory
        self.ai = ai
        self.repair_attempts: Dict[str, int] = {}
        self.MAX_ATTEMPTS: int = 10

    async def heal(
        self,
        error: Exception,
        context: str,
        retry_fn: Optional[Callable[[], Any]] = None,
    ) -> Dict[str, Any]:
        """Attempt to repair an error automatically, optionally retrying the original call."""
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

        result: Dict[str, Any] = {"success": False, "solution": solution, "attempts": attempts}

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

    # Erlaubte Package-Manager und ihre Executables
    _REPAIR_MANAGERS = {
        "pip":    [sys.executable, "-m", "pip", "install"],
        "pip3":   [sys.executable, "-m", "pip", "install"],
        "brew":   ["brew", "install"],
        "npm":    ["npm", "install"],
    }

    def _parse_repair_actions(self, solution: str) -> List[List[str]]:
        """Gibt validierte Befehle als Listen zurück (kein shell=True)."""
        actions = []
        import re
        pkg_re = re.compile(r'^[a-zA-Z0-9_\-\.\[\]>=<!\s]+$')
        for raw in solution.strip().split("\n"):
            raw = raw.strip()
            parts = raw.split()
            if len(parts) < 3:
                continue
            manager = parts[0]
            if parts[1] != "install":
                continue
            packages = parts[2:]
            # Paket-Namen validieren (nur sichere Zeichen)
            if not all(pkg_re.match(p) for p in packages):
                continue
            base = self._REPAIR_MANAGERS.get(manager)
            if base:
                actions.append(base + packages)
        return actions

    async def _execute_repair_action(self, action: List[str]) -> bool:
        import subprocess
        try:
            result = subprocess.run(
                action, shell=False, capture_output=True, text=True, timeout=120
            )
            return result.returncode == 0
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Command Router
# ---------------------------------------------------------------------------

class CommandRouter:
    """Maps incoming command strings to their handler coroutines and dispatches them."""

    def __init__(self, orchestrator: "MegaOrchestrator") -> None:
        """Register all command routes using the given orchestrator as context."""
        self.bot = orchestrator
        self.routes: Dict[str, Callable[..., Any]] = {}
        self._register_routes()

    def _register_routes(self) -> None:
        """Build the full command-to-handler mapping covering all 110+ bot commands."""
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
            # ── Control Panel ────────────────────────────────────────────────
            "/menu": self._cmd_menu,
            "/steuerung": self._cmd_menu,
            "/control": self._cmd_menu,
            # Guardian / Eternal
            "/guardian": self._cmd_guardian,
            "/guardian_status": self._cmd_guardian,
            "/guardian_health": self._cmd_guardian,
            "/guardian_services": self._cmd_guardian,
            "/guardian_agents": self._cmd_guardian,
            "/guardian_brain": self._cmd_guardian,
            "/guardian_heal": self._cmd_guardian,
            "/guardian_backup": self._cmd_guardian,
            "/guardian_restore": self._cmd_guardian,
            "/guardian_backups": self._cmd_guardian,
            "/eternal": self._cmd_guardian,
            "/eternal_status": self._cmd_guardian,
            "guardian": self._cmd_guardian,
            "eternal": self._cmd_guardian,
            # Hub Hilfe
            "/hub_hilfe": self._cmd_hub,
            "/hub_help": self._cmd_hub,
            "hub hilfe": self._cmd_hub,
            # ── Monetization ─────────────────────────────────────────────────
            "/plans": self._cmd_plans,
            "/subscribe": self._cmd_subscribe,
            "/team_run": self._cmd_team_run,
            "/mrr": self._cmd_mrr,
            # ── Master Dashboard ──────────────────────────────────────────────
            "/dashboard": self._cmd_master_dashboard,
            "/alle_dienste": self._cmd_alle_dienste,
            "/alle dienste": self._cmd_alle_dienste,
            "/seo_push": self._cmd_seo_push,
            "/agent_status": self._cmd_agent_status,
            "/agenten": self._cmd_agent_status,
            "/deploy_status": self._cmd_deploy_status,
            "/revenue": self._cmd_revenue,
            "dashboard": self._cmd_master_dashboard,
            "alle dienste": self._cmd_alle_dienste,
        }

    async def route(self, text: str, session_id: str) -> str:
        """Dispatch the input text to the matching command handler or AI chat fallback."""
        text_lower = text.lower().strip()

        # Direct route match
        for key, handler in self.routes.items():
            if text_lower.startswith(key):
                return await handler(text, session_id)

        # AI chat fallback (local Ollama)
        return await self._cmd_ai_chat(text, session_id)

    async def _cmd_screenshot(self, text: str, session_id: str) -> str:
        """Take a Mac screenshot and return the saved file path."""
        try:
            from modules.mac_controller import MacController
            mac = MacController()
            path = await mac.take_screenshot()
            return f"Screenshot gespeichert: {path}"
        except Exception as e:
            return f"Screenshot fehlgeschlagen: {e}"

    async def _cmd_status(self, text: str, session_id: str) -> str:
        """Report current CPU, RAM, disk usage, and Ollama availability."""
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

    async def _cmd_processes(self, text: str, session_id: str) -> str:
        """List the top 10 processes sorted by CPU usage."""
        try:
            import psutil
            procs = []
            for p in sorted(psutil.process_iter(["pid", "name", "cpu_percent"]), key=lambda x: x.info["cpu_percent"] or 0, reverse=True)[:10]:
                procs.append(f"PID {p.info['pid']}: {p.info['name']} ({p.info['cpu_percent']}%)")
            return "Top Prozesse:\n" + "\n".join(procs)
        except Exception as e:
            return f"Fehler: {e}"

    async def _cmd_disk(self, text: str, session_id: str) -> str:
        """Show disk usage for every mounted partition."""
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

    async def _cmd_arbitrage(self, text: str, session_id: str) -> str:
        """Scan exchanges for crypto arbitrage opportunities above 0.5% profit."""
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

    async def _cmd_prices(self, text: str, session_id: str) -> str:
        """Fetch and display current average prices for the top 6 crypto pairs."""
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

    async def _cmd_open_browser(self, text: str, session_id: str) -> str:
        """Open Safari with the URL extracted from the command text."""
        url = text.replace("öffne browser", "").replace("browser", "").strip()
        if not url:
            url = "https://google.com"
        try:
            import subprocess
            subprocess.Popen(["open", "-a", "Safari", url])
            return f"Browser geöffnet: {url}"
        except Exception as e:
            return f"Fehler: {e}"

    async def _cmd_finances(self, text: str, session_id: str) -> str:
        """List available finance-related sub-commands."""
        return (
            "Finanz-Funktionen verfügbar:\n"
            "• 'abos' - Abonnements anzeigen/kündigen\n"
            "• 'arbitrage' - Krypto-Arbitrage scannen\n"
            "• 'preise' - Aktuelle Krypto-Preise\n"
            "Tippe einen Befehl für Details."
        )

    async def _cmd_subscriptions(self, text: str, session_id: str) -> str:
        """Delegate subscription listing to the Mac controller module."""
        try:
            from modules.mac_controller import MacController
            mac = MacController()
            return await mac.list_subscriptions()
        except Exception as e:
            return f"Abo-Check Fehler: {e}"

    async def _cmd_ai_chat(self, text: str, session_id: str) -> str:
        """Forward unrecognized input to Ollama with conversation history as context."""
        history = self.bot.memory.get_history(session_id, limit=10)
        messages: List[Dict[str, str]] = [
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

    async def _cmd_gmc_status(self, text: str, session_id: str) -> str:
        """Return a formatted Google Merchant Center status summary."""
        try:
            from modules.gmc_monitor import format_telegram_status
            return await format_telegram_status()
        except Exception as e:
            return f"GMC Status Fehler: {e}"

    async def _cmd_produkte(self, text: str, session_id: str) -> str:
        """Show total, active, and draft Shopify product counts."""
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

    async def _cmd_ads(self, text: str, session_id: str) -> str:
        """Fetch and format active Google Ads campaign data."""
        try:
            from modules.campaign_manager import get_campaigns, format_telegram_ads
            campaigns = await get_campaigns()
            return format_telegram_ads(campaigns)
        except Exception as e:
            return f"Ads Fehler: {e}"

    async def _cmd_api(self, text: str, session_id: str) -> str:
        """Delegate API-builder commands to the api_builder module dispatcher."""
        try:
            from modules.api_builder import get_manager
            mgr = get_manager()
            return await mgr.dispatch(text)
        except Exception as e:
            return f"API Builder Fehler: {e}"

    async def _cmd_hub(self, text: str, session_id: str) -> str:
        """Delegate hub commands (PM2, Geheimwaffe, Army, ImmortalBot, etc.) to mega_hub."""
        try:
            from modules.mega_hub import get_hub
            hub = get_hub()
            return await hub.dispatch(text)
        except Exception as e:
            return f"Hub Fehler: {e}"

    async def _cmd_learner(self, text: str, session_id: str) -> str:
        """Route self-learner skill commands to the learner bridge module."""
        try:
            from self_learner_bridge import get_learner
            learner = get_learner()
            cmd = text.strip()
            if cmd in ("/learner", "/learner_status"):
                cmd = "/status"
            return learner.handle_command(cmd)
        except Exception as e:
            return f"Learner Fehler: {e}"

    async def _cmd_micro(self, text: str, session_id: str) -> str:
        """Read the shared army state file and report the status of all 5 micro bots."""
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

    async def _cmd_menu(self, text: str, session_id: str) -> str:
        return (
            "🤖 <b>Control Panel</b>\n\n"
            "Tippe /menu um das interaktive Steuerungsmenü mit Buttons zu öffnen.\n\n"
            "📊 Status · 🪖 Army · 🔧 Services · 🩺 Repair · 📋 Logs · ⚡ Actions"
        )
    async def _cmd_guardian(self, text: str, session_id: str) -> str:
        """Guardian/Eternal API Commands"""
        try:
            if not self.bot.guardian:
                return "⚠️ Guardian API nicht verfügbar. API läuft auf Port 3201?"

            cmd = text.strip().lower()

            # Health check
            if any(x in cmd for x in ["health", "status", "guardian", "eternal"]):
                health = self.bot.guardian.health()
                status_icon = "🟢" if health.get('status') == 'healthy' else "🔴"
                return f"{status_icon} Guardian Health: {health.get('status', 'unknown')}\n🕐 {health.get('timestamp', 'N/A')[:19]}"

            # Services
            if "services" in cmd or "service" in cmd:
                status = self.bot.guardian.status()
                services = status.get('services', [])
                lines = ["📋 Guardian Services:\n"]
                for svc in services:
                    icon = "🟢" if svc['healthy'] else "🔴"
                    crit = " [CRITICAL]" if svc.get('critical') else ""
                    lines.append(f"{icon} {svc['name']} (Port {svc['port']}){crit}")
                lines.append(f"\nOverall: {status.get('overall_health', 'unknown')}")
                return "\n".join(lines)

            # Agents
            if "agents" in cmd or "agent" in cmd:
                agents = self.bot.guardian.list_agents()
                if not agents:
                    return "🤖 Keine Agenten registriert"
                lines = [f"🤖 Registrierte Agenten ({len(agents)}):\n"]
                for agent in agents[:10]:  # Max 10
                    last = agent.get('last_seen', 'never')[:16] if agent.get('last_seen') else 'never'
                    lines.append(f"• {agent['agent_id'][:25]} ({agent['type']}) - {last}")
                return "\n".join(lines)

            # Brain
            if "brain" in cmd:
                brain = self.bot.guardian.brain_summary()
                return (
                    f"🧠 Guardian Brain:\n"
                    f"  Patterns: {brain.get('patterns_learned', 0)}\n"
                    f"  Repairs: {brain.get('total_repairs', 0)}\n"
                    f"  Permanently resolved: {brain.get('permanently_resolved', 0)}"
                )

            # Heal service
            if "heal" in cmd:
                # Extract service name if provided
                parts = text.split()
                service_name = "rudibot_main"
                for i, p in enumerate(parts):
                    if p in ["heal", "heilen"] and i + 1 < len(parts):
                        service_name = parts[i + 1]
                        break
                result = self.bot.guardian.heal_service(service_name)
                if result.get('healed'):
                    return f"✅ Service {service_name} wurde geheilt"
                return f"⚠️ Heilen von {service_name} fehlgeschlagen oder nicht nötig"

            # Backup
            if "backup" in cmd:
                result = self.bot.guardian.create_backup()
                if result.get('results'):
                    return f"✅ Backup erstellt: {len(result['results'])} Projekte"
                return f"⚠️ Backup fehlgeschlagen: {result.get('error', 'unknown')}"

            # Restore
            if "restore" in cmd:
                # Extract project name and optional date
                parts = text.split()
                project = None
                date = None
                for i, p in enumerate(parts):
                    if p in ["restore", "wiederherstellen"]:
                        if i + 1 < len(parts):
                            project = parts[i + 1]
                        if i + 2 < len(parts):
                            date = parts[i + 2]
                        break
                if not project:
                    return "⚠️ Usage: /guardian_restore <project> [YYYY-MM-DD]\nBeispiel: /guardian_restore supermegabot"
                result = self.bot.guardian.restore_project(project, date)
                if result.get('success'):
                    return f"✅ {project} von {result.get('from', 'backup')} wiederhergestellt"
                return f"⚠️ Restore fehlgeschlagen: {result.get('error', 'unknown')}"

            # List backups
            if "backups" in cmd:
                backups = self.bot.guardian.list_backups()
                if backups:
                    lines = [f"💾 Verfügbare Backups ({len(backups)}):"]
                    for b in backups[:10]:
                        lines.append(f"  • {b}")
                    return "\n".join(lines)
                return "⚠️ Keine Backups gefunden"

            # Default: show all info
            return (
                "🤖 Guardian Commands:\n"
                "  /guardian_health - Health Status\n"
                "  /guardian_services - Alle Services\n"
                "  /guardian_agents - Registrierte Agenten\n"
                "  /guardian_brain - Brain Stats\n"
                "  /guardian_heal [service] - Service heilen\n"
                "  /guardian_backup - Backup erstellen\n"
                "  /guardian_restore <projekt> [datum] - Restore\n"
                "  /guardian_backups - Liste Backups"
            )
        except Exception as e:
            return f"Guardian Fehler: {e}"

    async def _cmd_plans(self, text: str, session_id: str) -> str:
        """Zeigt verfügbare Abo-Pläne"""
        return (
            "📦 SuperMegaBot Abo-Pläne:\n\n"
            "🟢 Starter  — €49/Monat\n"
            "   • Shopify Sync, Telegram Bot, AI Chat\n\n"
            "🔵 Pro      — €99/Monat\n"
            "   • Alles in Starter + Multi-Store, SEO Autopilot\n\n"
            "🟣 Enterprise — €299/Monat\n"
            "   • Alles in Pro + Agent Teams, dedizierter Support\n\n"
            "Zum Abonnieren: /subscribe"
        )

    async def _cmd_subscribe(self, text: str, session_id: str) -> str:
        """Create live Stripe checkout sessions for all subscription plans."""
        import stripe as _stripe
        dashboard_url = os.getenv(
            "DASHBOARD_URL",
            os.getenv("SUPERMEGABOT_DASHBOARD_URL", "https://dudirudibot-mega-production.up.railway.app")
        )
        sk = os.getenv("STRIPE_SECRET_KEY", "")
        price_starter = os.getenv("STRIPE_PRICE_STARTER", "")
        price_pro = os.getenv("STRIPE_PRICE_PRO", "")
        price_enterprise = os.getenv("STRIPE_PRICE_ENTERPRISE", "")

        lines = ["🛒 Abonnement abschließen — Live Stripe Checkout:\n"]
        for label, amount, price_id in [
            ("Starter", "€49/mo", price_starter),
            ("Pro", "€99/mo", price_pro),
            ("Enterprise", "€299/mo", price_enterprise),
        ]:
            url = None
            if price_id and sk:
                try:
                    client = _stripe.StripeClient(sk)
                    sess = client.checkout.sessions.create(params={
                        "mode": "subscription",
                        "line_items": [{"price": price_id, "quantity": 1}],
                        "success_url": f"{dashboard_url}/pricing?success=true",
                        "cancel_url": f"{dashboard_url}/pricing?canceled=true",
                        "allow_promotion_codes": True,
                    })
                    url = sess.url
                except Exception as e:
                    logging.error(f"Checkout error {label}: {e}")
            if url:
                lines.append(f"• {label} ({amount}): {url}")
            else:
                lines.append(f"• {label} ({amount}): {'Preis-ID fehlt' if not price_id else 'Checkout-Fehler'}")

        lines.append("\n✅ Zahlung via Stripe • Sofort aktiv")
        return "\n".join(lines)

    async def _cmd_team_run(self, text: str, session_id: str) -> str:
        """Agent Team ausführen"""
        try:
            dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{dashboard_url}/api/agents/run",
                    json={"team": "default", "triggered_by": session_id},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as r:
                    data = await r.json()
                    if r.status == 200:
                        return f"✅ Agent Team gestartet: {data.get('message', 'OK')}"
                    return f"⚠️ Agent Team Fehler: {data.get('error', r.status)}"
        except Exception as e:
            return f"❌ /team_run Fehler: {e}"

    async def _cmd_mrr(self, text: str, session_id: str) -> str:
        """MRR (Monthly Recurring Revenue) anzeigen"""
        try:
            dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{dashboard_url}/api/mrr",
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    data = await r.json()
                    mrr = data.get("mrr", 0)
                    currency = data.get("currency", "EUR")
                    active = data.get("active_subscriptions", "N/A")
                    return (
                        f"💰 MRR: {mrr} {currency}\n"
                        f"📊 Aktive Abos: {active}\n"
                        f"📅 Stand: {datetime.utcnow().strftime('%Y-%m-%d')}"
                    )
        except Exception as e:
            return f"❌ /mrr Fehler: {e}"

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

  🛡️ GUARDIAN (RudiBot Eternal):
    /guardian         - Guardian Status
    /guardian_health  - Health Check
    /guardian_services - Alle Services
    /guardian_agents  - Registrierte Agenten
    /guardian_brain   - Brain Statistiken
    /guardian_heal [svc] - Service heilen
    /guardian_backup  - Backup erstellen
    /guardian_restore <proj> [datum] - Restore
    /guardian_backups - Liste alle Backups

  🖥️ MASTER DASHBOARD (alle 19 Dienste):
    /dashboard          - Health-Check aller Railway-Dienste
    /alle_dienste       - Liste aller Services + URLs
    /revenue            - Revenue-Übersicht
    /seo_push <keyword> - Keyword an SEO Engine pushen
    /agent_status       - Alle autonomen Agenten
    /deploy_status      - Kritische Dienste prüfen

  Kosten: 95% lokal (Ollama), 5% externe APIs"""

    async def _cmd_start(self, text: str, session_id: str) -> str:
        """Send the welcome message listing all active modules."""
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
            "✓ Persistentes Gedächtnis\n"
            "✓ Guardian API (RudiBot Eternal)\n"
            "✓ Master Dashboard (alle 19 Dienste)"
        )

    # ── Master Dashboard Commands ─────────────────────────────────────────────

    async def _cmd_master_dashboard(self, text: str, session_id: str) -> str:
        """Health-Check aller Railway-Dienste."""
        from modules.telegram_master_dashboard import cmd_dashboard
        return await cmd_dashboard(text, session_id)

    async def _cmd_alle_dienste(self, text: str, session_id: str) -> str:
        """Liste aller Dienste mit URLs."""
        from modules.telegram_master_dashboard import cmd_alle_dienste
        return await cmd_alle_dienste(text, session_id)

    async def _cmd_seo_push(self, text: str, session_id: str) -> str:
        """Keyword an SEO Traffic Engine pushen."""
        from modules.telegram_master_dashboard import cmd_seo_push
        return await cmd_seo_push(text, session_id)

    async def _cmd_agent_status(self, text: str, session_id: str) -> str:
        """Status aller autonomen Agenten."""
        from modules.telegram_master_dashboard import cmd_agent_status
        return await cmd_agent_status(text, session_id)

    async def _cmd_revenue(self, text: str, session_id: str) -> str:
        """Revenue-Übersicht von allen Diensten."""
        from modules.telegram_master_dashboard import cmd_revenue
        return await cmd_revenue(text, session_id)

    async def _cmd_deploy_status(self, text: str, session_id: str) -> str:
        """Schneller Health-Check der kritischsten Dienste."""
        from modules.telegram_master_dashboard import cmd_deploy_status
        return await cmd_deploy_status(text, session_id)


# ---------------------------------------------------------------------------
# Telegram Sender
# ---------------------------------------------------------------------------

async def send_telegram(
    text: str,
    chat_id: Optional[str] = None,
    token: Optional[str] = None,
) -> None:
    """Send a Telegram HTML message, silently dropping errors to avoid cascading failures."""
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
    """Top-level controller that wires together memory, AI, healing, routing, and Telegram."""

    def __init__(self) -> None:
        """Instantiate all sub-systems and attempt to connect to the Guardian API."""
        self.memory = MemorySystem()
        self.ai = OllamaClient()
        self.healer = SelfHealingEngine(self.memory, self.ai)
        self.router = CommandRouter(self)
        self.running = True

        # Guardian Integration
        self.guardian = None
        self._init_guardian()

        log.info("MegaOrchestrator initialized")

    def _init_guardian(self):
        """Initialize Guardian API client"""
        try:
            sys.path.insert(0, _ETERNAL_DIR)
            from guardian_client import GuardianClient
            self.guardian = GuardianClient()
            log.info("Guardian API client initialized")
        except Exception as e:
            log.warning(f"Guardian client not available: {e}")
            self.guardian = None

    async def start(self):
        log.info("Starting SuperMegaBot...")

        # Check Ollama
        ollama_ok = await self.ai.check_health()
        if ollama_ok:
            log.info(f"Ollama OK - Models: {self.ai.available_models}")
        else:
            log.warning("Ollama offline - will retry in background")

        # Register with Guardian
        if self.guardian:
            try:
                self.guardian.register_agent(
                    agent_id="supermegabot-core",
                    agent_type="orchestrator",
                    endpoint=f"http://localhost:{os.getenv('DASHBOARD_PORT', '8888')}"
                )
                self.guardian.notify("🚀 SuperMegaBot Orchestrator gestartet!")
                log.info("Registered with Guardian API")
            except Exception as e:
                log.warning(f"Guardian registration failed: {e}")

        # Start health monitor
        asyncio.create_task(self._health_loop())
        # Telegram polling DEAKTIVIERT — telegram-automation-bot (Node.js) übernimmt
        # asyncio.create_task(self._telegram_polling_loop())
        # Start Guardian monitor
        asyncio.create_task(self._guardian_monitor_loop())
        # Start automation scheduler
        try:
            from core.automation_scheduler import get_scheduler
            sched = get_scheduler()
            await sched.start()
            log.info(f"AutoScheduler gestartet ({len(sched._task_handles)} Tasks)")
        except Exception as e:
            log.warning(f"AutoScheduler nicht gestartet: {e}")

        # Start specialized bot-clones
        try:
            from core.bot_clones import get_manager
            clone_mgr = get_manager()
            await clone_mgr.start()
            log.info("BotClone-Manager gestartet (6 spezialisierte Clones)")
        except Exception as e:
            log.warning(f"BotClone-Manager nicht gestartet: {e}")

        # Start RudiCludiBot (Kunden-Bot @RudiCludiBot)
        try:
            if TELEGRAM_TOKEN_CUSTOMER:
                from modules.rudicludi_bot import run as rudicludi_run
                asyncio.create_task(rudicludi_run())
                log.info("RudiCludiBot (@RudiCludiBot) gestartet")
        except Exception as e:
            log.warning(f"RudiCludiBot nicht gestartet: {e}")

        log.info("SuperMegaBot is RUNNING")
        await send_telegram("🚀 SuperMegaBot + @RudiCludiBot gestartet! Tippe /help")

    async def process(self, text: str, session_id: str = "default") -> str:
        """Route a command, persist timing data, and trigger self-healing on failure."""
        start = time.time()
        try:
            result = await self.router.route(text, session_id)
            ms = int((time.time() - start) * 1000)
            conn = sqlite3.connect(DATA_DIR / "memory.db")
            conn.execute(
                "INSERT INTO task_history (task,result,duration_ms,timestamp) VALUES (?,?,?,?)",
                (text[:2000], result[:4000], ms, datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
            return result
        except Exception as e:
            log.error(f"Process error: {e}")

            # Notify Guardian about error
            if self.guardian:
                try:
                    self.guardian.notify(
                        f"🔴 SuperMegaBot Fehler: {type(e).__name__}: {str(e)[:150]}",
                        priority="high"
                    )
                except:
                    pass

            repair = await self.healer.heal(e, f"processing command: {text[:100]}")
            if repair["success"]:
                return await self.router.route(text, session_id)
            return f"Fehler (wird repariert): {type(e).__name__}: {str(e)[:100]}"

    async def _health_loop(self) -> None:
        """Periodically verify Ollama is reachable and restart it if it has gone offline."""
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

    async def _guardian_monitor_loop(self):
        """Monitor Guardian API health and services"""
        while self.running:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes

                if not self.guardian:
                    continue

                # Check Guardian health
                health = self.guardian.health()
                if health.get('status') != 'healthy':
                    log.warning(f"Guardian not healthy: {health}")
                    continue

                # Check all services
                status = self.guardian.status()
                services = status.get('services', [])

                for svc in services:
                    if not svc['healthy'] and svc.get('critical', False):
                        log.error(f"Critical service down: {svc['name']}")
                        # Auto-heal critical services
                        self.guardian.heal_service(svc['name'])
                        self.guardian.notify(
                            f"🔴 Auto-heal triggered for {svc['name']}",
                            priority="high"
                        )

                log.info(f"Guardian monitor: {len([s for s in services if s['healthy']])}/{len(services)} services healthy")

            except Exception as e:
                log.error(f"Guardian monitor error: {e}")

    async def _telegram_polling_loop(self):
        if not TELEGRAM_TOKEN:
            log.warning("No Telegram token - polling disabled")
            return

        # PID-Lock: verhindert doppeltes Polling bei mehrfachem Start
        lock_path = DATA_DIR / "telegram_polling.pid"
        my_pid = os.getpid()
        if lock_path.exists():
            try:
                old_pid = int(lock_path.read_text().strip())
                import signal
                os.kill(old_pid, 0)  # prüft ob Prozess noch läuft
                if old_pid != my_pid:
                    log.warning(f"Telegram-Polling läuft bereits in PID {old_pid} — überspringe")
                    return
            except (ValueError, ProcessLookupError, PermissionError):
                pass  # alter PID tot → Lock überschreiben
        lock_path.write_text(str(my_pid))

        try:
            await self._do_telegram_polling()
        finally:
            try:
                lock_path.unlink(missing_ok=True)
            except Exception:
                pass

    async def _do_telegram_polling(self):
        # Webhook löschen (verhindert Konflikt mit Polling)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                del_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook"
                async with s.post(del_url, json={"drop_pending_updates": True}) as r:
                    result = await r.json()
                    if result.get("ok"):
                        log.info("Telegram webhook gelöscht - Polling aktiv")
                    else:
                        log.warning(f"Webhook delete: {result}")
        except Exception as e:
            log.warning(f"Webhook delete fehlgeschlagen: {type(e).__name__}: {e}")

        offset = 0
        retry_wait = 5
        conflict_wait = 15
        log.info("Telegram polling gestartet")
        while self.running:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
                params = {"offset": offset, "timeout": 30, "limit": 10, "allowed_updates": ["message", "callback_query"]}
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
                            retry_wait = 5       # Reset bei Erfolg
                            conflict_wait = 15   # Reset nach erfolgreichem Poll
                            for update in data.get("result", []):
                                offset = update["update_id"] + 1
                                asyncio.create_task(self._handle_telegram_update(update))
                        elif r.status == 401:
                            # Ungültiger Token — kein Retry-Spam, einmalig loggen dann stoppen
                            log.error(
                                "Telegram 401 Unauthorized — TELEGRAM_BOT_TOKEN ungültig oder abgelaufen. "
                                "Bitte Token über @BotFather erneuern und .env aktualisieren. "
                                "Polling wird deaktiviert."
                            )
                            return  # Loop beenden, kein weiterer Spam
                        elif r.status == 409:
                            body = await r.text()
                            log.warning(f"Token-Konflikt (409): {body[:100]} — pausiere {conflict_wait}s")
                            await asyncio.sleep(conflict_wait)
                            conflict_wait = min(conflict_wait * 2, 300)
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

    async def _handle_telegram_update(self, update: Dict[str, Any]) -> None:
        """Process a single Telegram update: route callback queries or text messages."""
        try:
            # ── Inline-Keyboard Button-Klick ──────────────────────────────
            cq = update.get("callback_query")
            if cq:
                try:
                    from modules.telegram_control import handle_callback
                    chat_id   = str(cq.get("message", {}).get("chat", {}).get("id", ""))
                    if TELEGRAM_CHAT_ID and chat_id != str(TELEGRAM_CHAT_ID):
                        log.warning(f"Callback von unautorisiertem Chat {chat_id} ignoriert")
                        return
                    message_id = cq.get("message", {}).get("message_id", 0)
                    cq_id     = cq.get("id", "")
                    data      = cq.get("data", "")
                    log.info(f"Callback: {data}")
                    await asyncio.get_event_loop().run_in_executor(
                        None, handle_callback, data, chat_id, message_id, cq_id
                    )
                except Exception as e:
                    log.error(f"Callback handler error: {e}")
                return

            # ── Normale Textnachricht ─────────────────────────────────────
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id", ""))
            user = msg.get("from", {}).get("username", "unknown")

            if not text or not chat_id:
                return

            if TELEGRAM_CHAT_ID and chat_id != str(TELEGRAM_CHAT_ID):
                log.warning(f"Nachricht von unautorisiertem Chat {chat_id} ignoriert")
                return

            session_id = f"telegram_{chat_id}"
            log.info(f"Telegram [{user}]: {text[:60]}")

            # /menu — zeigt Inline-Keyboard Control Panel
            if text.strip().lower() in ("/menu", "/steuerung", "/control"):
                try:
                    from modules.telegram_control import send_main_menu
                    await asyncio.get_event_loop().run_in_executor(
                        None, send_main_menu, chat_id
                    )
                except Exception as e:
                    await send_telegram(f"Menü-Fehler: {e}", chat_id=chat_id)
                return

            response = await self.process(text, session_id)
            await send_telegram(response, chat_id=chat_id)
        except Exception as e:
            log.error(f"Telegram handler error: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    """Bootstrap the orchestrator and either start interactive mode or keep-alive loop."""
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
