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

    async def _cloud_fallback(self, prompt: str) -> str:
        """Use ai_client fallback chain (Anthropic→OpenAI→Groq→Gemini→OpenRouter) when Ollama is offline."""
        try:
            from modules.ai_client import ai_complete
            result = await ai_complete(prompt, max_tokens=1200)
            return result
        except Exception as e:
            log.debug("Cloud AI fallback failed: %s", e)
            return ""

    async def chat(self, messages: List[Dict[str, str]], task: str = "smart", stream: bool = False) -> str:
        """Send a multi-turn chat to Ollama; falls back to cloud AI chain when Ollama is offline."""
        model = self._pick_model(task)
        payload = {"model": model, "messages": messages, "stream": False}
        prompt_fallback = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
        ) + "\nassistant:"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(f"{self.base}/api/chat", json=payload) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("message", {}).get("content", "")
        except Exception:
            pass
        # Ollama offline — use cloud AI fallback chain
        result = await self._cloud_fallback(prompt_fallback)
        if result:
            return result
        return "KI momentan nicht verfügbar. Bitte später erneut versuchen."

    async def generate(self, prompt: str, task: str = "fast") -> str:
        """Send a single-turn completion; falls back to cloud AI chain when Ollama is offline."""
        model = self._pick_model(task)
        payload = {"model": model, "prompt": prompt, "stream": False}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(f"{self.base}/api/generate", json=payload) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("response", "")
        except Exception:
            pass
        # Ollama offline — use cloud AI fallback chain
        result = await self._cloud_fallback(prompt)
        return result if result else ""


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
            # NEXUS-1 Autonomous Revenue Superintelligence
            "/nexus": self._cmd_nexus,
            "nexus": self._cmd_nexus,
            "/nexus_run": self._cmd_nexus_run,
            "nexus run": self._cmd_nexus_run,
            "/nexus_blast": self._cmd_nexus_blast,
            "nexus blast": self._cmd_nexus_blast,
            "/nexus_signals": self._cmd_nexus_signals,
            "/nexus_actions": self._cmd_nexus_actions,
            "/nexus_evolve": self._cmd_nexus_evolve,
            "/nexus_report": self._cmd_nexus_report,
            "/nexus_dna": self._cmd_nexus_dna,
            # Product Generator
            "/generate": self._cmd_generate,
            "generate": self._cmd_generate,
            "/generiere": self._cmd_generate,
            "generiere": self._cmd_generate,
            "/niche": self._cmd_generate_niche,
            "niche": self._cmd_generate_niche,
            "/produkt": self._cmd_generate,
            "produkt erstellen": self._cmd_generate,
            # DS24 Product Creator
            "/ds24": self._cmd_ds24_create,
            "/ds24_create": self._cmd_ds24_create,
            "ds24 produkt": self._cmd_ds24_create,
            "digistore produkt anlegen": self._cmd_ds24_create,
            "/ds24_auto": self._cmd_ds24_auto,
            "ds24 auto": self._cmd_ds24_auto,
            "/ds24_fix": self._cmd_ds24_fix,
            "ds24 fix 669750": self._cmd_ds24_fix,
            "/ds24_1000": self._cmd_ds24_1000,
            "ds24 1000": self._cmd_ds24_1000,
            "1000 produkte": self._cmd_ds24_1000,
            "/ds24_status": self._cmd_ds24_status,
            "ds24 status": self._cmd_ds24_status,
            "/ds24_revenue": self._cmd_ds24_revenue,
            "ds24 umsatz": self._cmd_ds24_revenue,
            "/ds24_refill": self._cmd_ds24_refill,
            "ds24 refill": self._cmd_ds24_refill,
            "/ds24_blast": self._cmd_ds24_seo_blast,
            "ds24 blast": self._cmd_ds24_seo_blast,
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
            "/agenten_status": self._cmd_agent_status,
            "/deploy_status": self._cmd_deploy_status,
            "/revenue": self._cmd_revenue,
            "dashboard": self._cmd_master_dashboard,
            "alle dienste": self._cmd_alle_dienste,
            # ── Selbstverbesserung & Email Doctor & Dragon 1000 & Mass Blast ─
            "/export_kunden": self._cmd_export_kunden,
            "kunden exportieren": self._cmd_export_kunden,
            "export kunden": self._cmd_export_kunden,
            "/selbstverbesserung": self._cmd_selbstverbesserung,
            "selbstverbesserung": self._cmd_selbstverbesserung,
            "/selbst": self._cmd_selbstverbesserung,
            "/email_doctor": self._cmd_email_doctor,
            "email doctor": self._cmd_email_doctor,
            "/dragon_artikel": self._cmd_dragon_artikel,
            "dragon artikel": self._cmd_dragon_artikel,
            "/mass_blast": self._cmd_mass_blast,
            "mass blast": self._cmd_mass_blast,
            "1000 sachen": self._cmd_mass_blast,
            "/system_overview": self._cmd_system_overview,
            "system overview": self._cmd_system_overview,
            "überblick": self._cmd_system_overview,
            "/repair": self._cmd_quantum_repair,
            "reparatur": self._cmd_quantum_repair,
            "selbst reparatur": self._cmd_quantum_repair,
            "/linkedin": self._cmd_linkedin_post,
            "/instagram": self._cmd_instagram_post,
            "/pinterest": self._cmd_pinterest_post,
            "/shopify_stats": self._cmd_shopify_stats,
            "/shopify_products": self._cmd_shopify_products,
            "shopify stats": self._cmd_shopify_stats,
            "/scheduler_status": self._cmd_scheduler_status_info,
            "/scheduler": self._cmd_scheduler_status_info,
            "scheduler status": self._cmd_scheduler_status_info,
            "/health_check": self._cmd_status,
            "/trend_analyse": self._cmd_trend_analyse,
            "trend analyse": self._cmd_trend_analyse,
            "/printify": self._cmd_printify_status,
            "/printful": self._cmd_printful_status,
            "/gumroad": self._cmd_gumroad_status,
            "/paypal": self._cmd_paypal_status,
            "/klaviyo_blast": self._cmd_klaviyo_blast,
            "/ebay_blast": self._cmd_ebay_blast,
            "/amazon_blast": self._cmd_amazon_blast,
            "/twilio_blast": self._cmd_twilio_blast,
            # ── KI-Direkt ────────────────────────────────────────────────────
            "/ai": self._cmd_ai,
            "ai frage": self._cmd_ai,
            "ki frage": self._cmd_ai,
            # ── Leads ────────────────────────────────────────────────────────
            "/leads": self._cmd_leads,
            "leads": self._cmd_leads,
            "/lead_status": self._cmd_leads,
            # ── Broadcast ────────────────────────────────────────────────────
            "/broadcast": self._cmd_broadcast,
            "broadcast": self._cmd_broadcast,
            "/nachricht": self._cmd_broadcast,
            # ── Shopify Alias ────────────────────────────────────────────────
            "/shopify": self._cmd_shopify_stats,
            "shopify": self._cmd_shopify_stats,
        }

    async def route(self, text: str, session_id: str) -> str:
        """Dispatch the input text to the matching command handler or AI chat fallback."""
        text_lower = text.lower().strip()
        # Normalize: strip leading slash so "/status" matches route "status"
        text_norm = text_lower.lstrip("/")

        # Match longest routes first so "/ds24_revenue" isn't hijacked by "/ds24"
        for key, handler in sorted(self.routes.items(), key=lambda x: len(x[0]), reverse=True):
            key_norm = key.lstrip("/")
            if text_norm.startswith(key_norm) or text_lower.startswith(key):
                return await handler(text, session_id)

        # AI chat fallback (cloud AI chain when Ollama offline)
        return await self._cmd_ai_chat(text, session_id)

    # ── Premium / Paywall Gate ────────────────────────────────────────────────

    def _is_premium(self, session_id: str) -> bool:
        """
        Check whether the caller has an active paid subscription.

        Priority:
          1. PREMIUM_SESSION_IDS env var — comma-separated list of always-premium
             session IDs (e.g. the owner's own Telegram chat: "telegram_5088771245").
          2. PREMIUM_TELEGRAM_CHAT_IDS env var — Telegram chat IDs of paying customers.
          3. Falls back to checking Supabase `clients` table if SUPABASE_URL is set.

        Returns True if premium, False otherwise.
        """
        # 1. Hard-coded admin/owner sessions (always premium)
        admin_sessions = {s.strip() for s in os.getenv("PREMIUM_SESSION_IDS", "").split(",") if s.strip()}
        # Always grant premium to the owner's own chat
        owner_chat = os.getenv("TELEGRAM_CHAT_ID", "")
        if owner_chat:
            admin_sessions.add(f"telegram_{owner_chat}")
            admin_sessions.add(f"tg-{owner_chat}")
        if session_id in admin_sessions:
            return True

        # 2. Env-var list of paying customer Telegram IDs
        premium_chats = {c.strip() for c in os.getenv("PREMIUM_TELEGRAM_CHAT_IDS", "").split(",") if c.strip()}
        tg_id = session_id.replace("telegram_", "").replace("tg-", "")
        if tg_id in premium_chats:
            return True

        # 3. Supabase clients table (non-blocking sync check via thread)
        try:
            import concurrent.futures
            supabase_url = os.getenv("SUPABASE_URL", "")
            if not supabase_url:
                return False

            def _check_db():
                try:
                    from modules.supabase_client import get_supabase_client
                    client = get_supabase_client()
                    rows = (
                        client.table("clients")
                        .select("id,status")
                        .eq("telegram_id", tg_id)
                        .eq("status", "active")
                        .limit(1)
                        .execute()
                    )
                    return bool(rows.data)
                except Exception:
                    return False

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(_check_db).result(timeout=3)
        except Exception:
            return False

    def _require_premium(self, session_id: str) -> Optional[str]:
        """Return an error string if the session is NOT premium, else None."""
        if not self._is_premium(session_id):
            return (
                "🔒 <b>Premium-Funktion</b>\n\n"
                "Diese Funktion erfordert ein aktives Abonnement.\n\n"
                "Tippe /plans um die Preise zu sehen.\n"
                "Tippe /subscribe um jetzt zu starten (14 Tage gratis)."
            )
        return None

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
        """Report current CPU, RAM, disk usage, and AI availability."""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            ollama_ok = await self.bot.ai.check_health()
            ai_status = "Ollama ✅" if ollama_ok else "Cloud-AI ✅"
            return (
                f"🖥 System Status:\n"
                f"CPU: {cpu}%\n"
                f"RAM: {mem.percent:.0f}% ({mem.used//1024//1024}MB/{mem.total//1024//1024}MB)\n"
                f"Disk: {disk.percent}% ({disk.free//1024//1024//1024}GB frei)\n"
                f"KI: {ai_status}"
            )
        except ImportError:
            return "psutil nicht installiert"
        except Exception as e:
            return f"Status Fehler: {e}"

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
            os.getenv("SUPERMEGABOT_DASHBOARD_URL", "https://supermegabot-production.up.railway.app")
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
        """Agent Team ausführen. [PREMIUM Enterprise]"""
        gate = self._require_premium(session_id)
        if gate:
            return gate
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
        return """SuperMegaBot Befehle (v2):
  ⚠️  PAYWALL: /plans und /subscribe für Premium-Zugang.
      Ohne Abo: Basis-Commands. Premium: alle KI/Shopify/DS24-Commands.

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

  Kosten: 95% lokal (Ollama), 5% externe APIs

  🤖 NEXUS-1 (Autonome Revenue-Superintelligenz):
    /nexus              - NEXUS Status + Strategie-Scores
    /nexus_run          - Sofort-Zyklus starten
    /nexus_signals      - Letzte erkannte Trends
    /nexus_actions      - Letzte Aktionen + Performance
    /nexus_evolve       - Self-Evolution jetzt
    /nexus_report       - Tages-Report senden
    /nexus_dna          - Revenue-DNA anzeigen
    /nexus_blast <msg>  - Broadcast an alle Kanäle + Agenten

  🤖 KI & KOMMUNIKATION:
    /ai <frage>         - Direkte KI-Anfrage (Ollama → Cloud Fallback)
    /leads              - Lead-Übersicht aus Supabase (letzte 10)
    /broadcast <msg>    - Broadcast-Nachricht an alle Telegram-Chats
    /shopify            - Shopify Store Stats (Alias für /shopify_stats)"""

    async def _cmd_nexus(self, text: str, session_id: str) -> str:
        """NEXUS-1 Status via Telegram."""
        import aiohttp
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{smb_url}/api/nexus/status",
                                 timeout=aiohttp.ClientTimeout(total=10)) as r:
                    data = await r.json()
            scores = data.get("strategy_scores", {})
            top3 = sorted(scores.items(), key=lambda x: x[1].get("score", 0), reverse=True)[:3]
            top3_str = "\n".join([f"  • {a}: {v.get('score',0):.0f}% ({v.get('wins',0)}/{v.get('runs',0)} wins)"
                                  for a, v in top3])
            last = data.get("last_signal") or {}
            return (
                f"🤖 NEXUS-1 ONLINE\n"
                f"{'━'*30}\n"
                f"⚡ Heute: {data.get('today_actions', 0)} Aktionen\n"
                f"📊 Gesamt: {data.get('total_actions', 0)} Aktionen\n"
                f"📡 Bester Kanal jetzt: {data.get('best_channel_now', '?')}\n"
                f"🔍 Letztes Signal: {last.get('keyword', '?')[:40]}\n"
                f"   (Quelle: {last.get('source', '?')}, Score: {last.get('score', 0):.0f})\n\n"
                f"🏆 Top-Strategien:\n{top3_str}"
            )
        except Exception as e:
            return f"NEXUS Status Fehler: {e}"

    async def _cmd_nexus_run(self, text: str, session_id: str) -> str:
        """Startet sofort einen NEXUS-Zyklus. [PREMIUM]"""
        gate = self._require_premium(session_id)
        if gate:
            return gate
        import aiohttp
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{smb_url}/api/nexus/run",
                                  timeout=aiohttp.ClientTimeout(total=5)) as r:
                    await r.json()
            return "⚡ NEXUS-Zyklus gestartet!\nScan → Score → Decide → Create → Deploy → Track → Learn\nErgebnis kommt in ~30 Sekunden."
        except Exception as e:
            return f"NEXUS run Fehler: {e}"

    async def _cmd_nexus_blast(self, text: str, session_id: str) -> str:
        """Broadcast an alle Kanäle + Agenten."""
        import aiohttp
        msg = text.replace("/nexus_blast", "").strip() or "NEXUS: Alle Systeme aktiv!"
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{smb_url}/api/nexus/broadcast",
                                  json={"message": msg},
                                  timeout=aiohttp.ClientTimeout(total=30)) as r:
                    data = await r.json()
            return (f"📢 Broadcast gesendet!\n"
                    f"BrutusCore: {data.get('brutus_channels', 0)} Kanäle\n"
                    f"Hermes: {'✅' if data.get('hermes_ok') else '❌'}\n"
                    f"Slack: {'✅' if data.get('slack_ok') else '❌'}")
        except Exception as e:
            return f"Broadcast Fehler: {e}"

    # ── NEXUS Sub-Commands (real handlers) ────────────────────────────────────

    async def _cmd_nexus_signals(self, text: str, session_id: str) -> str:
        """NEXUS — letzte erkannte Trend-Signale."""
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{smb_url}/api/nexus/signals",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    data = await r.json()
            signals = data.get("signals", data.get("data", []))
            if not signals:
                return "📡 NEXUS: Keine Signale vorhanden (noch kein Scan-Zyklus gelaufen)."
            lines = [f"📡 <b>NEXUS Signale — letzte {min(len(signals),5)}:</b>\n"]
            for sig in signals[:5]:
                kw    = str(sig.get("keyword", sig.get("trend", "?")))[:40]
                score = sig.get("score", sig.get("strength", 0))
                src   = sig.get("source", sig.get("channel", "?"))
                lines.append(f"• {kw} (Score: {score:.0f}) — {src}")
            return "\n".join(lines)
        except Exception as e:
            return f"NEXUS Signale Fehler: {e}"

    async def _cmd_nexus_actions(self, text: str, session_id: str) -> str:
        """NEXUS — letzte Aktionen + Performance."""
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{smb_url}/api/nexus/actions",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    data = await r.json()
            actions = data.get("actions", data.get("data", []))
            if not actions:
                return "⚡ NEXUS: Keine Aktionen protokolliert."
            lines = [f"⚡ <b>NEXUS Aktionen — letzte {min(len(actions),5)}:</b>\n"]
            for act in actions[:5]:
                atype  = act.get("type", act.get("action", "?"))
                result = str(act.get("result", act.get("status", "?")))[:50]
                ts     = str(act.get("timestamp", act.get("created_at", "")))[:16]
                lines.append(f"• {atype}: {result} ({ts})")
            return "\n".join(lines)
        except Exception as e:
            return f"NEXUS Aktionen Fehler: {e}"

    async def _cmd_nexus_evolve(self, text: str, session_id: str) -> str:
        """NEXUS — Self-Evolution-Zyklus jetzt starten."""
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{smb_url}/api/nexus/evolve",
                    json={},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    data = await r.json()
            adjusted   = data.get("adjusted", data.get("strategies_adjusted", 0))
            dna_ok     = data.get("dna_updated", data.get("ok", False))
            best       = data.get("best_strategy", data.get("winner", "?"))
            return (
                f"🧬 <b>NEXUS Evolution abgeschlossen!</b>\n"
                f"Strategien angepasst: {adjusted}\n"
                f"DNA aktualisiert: {'✅' if dna_ok else '⚠️'}\n"
                f"Beste Strategie jetzt: {best}"
            )
        except Exception as e:
            return f"NEXUS Evolve Fehler: {e}"

    async def _cmd_nexus_report(self, text: str, session_id: str) -> str:
        """NEXUS — Tages-Report generieren und senden."""
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{smb_url}/api/nexus/report",
                    json={},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as r:
                    data = await r.json()
            today_actions = data.get("today_actions", data.get("actions_today", 0))
            revenue_impact = data.get("revenue_impact", data.get("revenue", 0))
            top_strategy   = data.get("top_strategy", data.get("best_strategy", "?"))
            return (
                f"📋 <b>NEXUS Tages-Report</b>\n"
                f"📅 {datetime.utcnow().strftime('%Y-%m-%d')}\n\n"
                f"⚡ Aktionen heute: {today_actions}\n"
                f"💶 Revenue-Impact: €{float(revenue_impact):.2f}\n"
                f"🏆 Top-Strategie: {top_strategy}\n\n"
                f"Vollständiger Report per Telegram gesendet."
            )
        except Exception as e:
            return f"NEXUS Report Fehler: {e}"

    async def _cmd_nexus_dna(self, text: str, session_id: str) -> str:
        """NEXUS — Revenue-DNA anzeigen."""
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{smb_url}/api/nexus/dna",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    data = await r.json()
            dna = data.get("dna", data.get("data", {}))
            if not dna:
                return "🧬 NEXUS: Keine DNA-Daten vorhanden (noch kein Evolution-Zyklus)."
            lines = ["🧬 <b>NEXUS Revenue-DNA:</b>\n"]
            for k, v in list(dna.items())[:8]:
                v_str = f"{float(v):.3f}" if isinstance(v, (int, float)) else str(v)[:30]
                lines.append(f"• {k}: {v_str}")
            return "\n".join(lines)
        except Exception as e:
            return f"NEXUS DNA Fehler: {e}"

    # ── New Core Commands ─────────────────────────────────────────────────────

    async def _cmd_ai(self, text: str, session_id: str) -> str:
        """Direkte KI-Anfrage via ai_complete() — Vollautomatische Provider-Kette."""
        prompt = text.strip()
        # Strip command prefix
        for prefix in ("/ai", "ai frage", "ki frage"):
            if prompt.lower().startswith(prefix):
                prompt = prompt[len(prefix):].strip()
                break
        if not prompt:
            return (
                "🤖 <b>KI-Direktanfrage</b>\n\n"
                "Usage: <code>/ai Deine Frage hier</code>\n\n"
                "Beispiele:\n"
                "• /ai Was sind die Top-Trends im E-Commerce 2026?\n"
                "• /ai Schreibe einen Facebook-Post über Smart Home\n"
                "• /ai Optimiere diesen Produkttitel: ..."
            )
        try:
            from modules.ai_client import ai_complete
            result = await ai_complete(
                prompt,
                system=(
                    "Du bist SuperMegaBot, ein autonomer KI-Assistent für E-Commerce-Automatisierung. "
                    "Antworte immer auf Deutsch. Sei präzise, praktisch und handlungsorientiert."
                ),
                max_tokens=1200,
            )
            if not result or result.startswith("KI momentan"):
                # Fallback via Ollama chat
                result = await self.bot.ai.chat(
                    [{"role": "user", "content": prompt}],
                    task="smart",
                )
            return f"🤖 <b>KI-Antwort:</b>\n\n{result}" if result else "❌ KI momentan nicht verfügbar."
        except Exception as e:
            return f"KI Fehler: {e}"

    async def _cmd_leads(self, text: str, session_id: str) -> str:
        """Lead-Übersicht aus Supabase (lead_events Tabelle)."""
        try:
            from modules.supabase_client import get_supabase_client
            client = get_supabase_client()
            result = (
                client.table("lead_events")
                .select("id,email,source,channel,created_at,revenue")
                .order("created_at", desc=True)
                .limit(10)
                .execute()
            )
            rows = result.data or []
            if not rows:
                return (
                    "📋 <b>Leads</b>\n\n"
                    "Keine Leads in Supabase (lead_events leer).\n"
                    "Leads werden automatisch erfasst sobald der erste Kauf stattfindet."
                )
            total_revenue = sum(float(r.get("revenue", 0) or 0) for r in rows)
            lines = [f"📋 <b>Letzte {len(rows)} Leads</b> (€{total_revenue:.2f} gesamt)\n"]
            for r in rows:
                email  = r.get("email", "?")[:30]
                source = r.get("source", r.get("channel", "?"))
                ts     = str(r.get("created_at", ""))[:10]
                rev    = r.get("revenue")
                rev_str = f" | €{float(rev):.2f}" if rev else ""
                lines.append(f"• {email} ({source}{rev_str}) — {ts}")
            return "\n".join(lines)
        except ImportError:
            return "❌ Supabase Client nicht verfügbar (SUPABASE_URL fehlt?)"
        except Exception as e:
            return f"Leads Fehler: {e}"

    async def _cmd_broadcast(self, text: str, session_id: str) -> str:
        """Broadcast-Nachricht an alle konfigurierten Telegram-Chats senden."""
        # Strip command prefix
        msg = text.strip()
        for prefix in ("/broadcast", "/nachricht", "broadcast"):
            if msg.lower().startswith(prefix):
                msg = msg[len(prefix):].strip()
                break
        if not msg:
            return (
                "📢 <b>Broadcast</b>\n\n"
                "Usage: <code>/broadcast Deine Nachricht</code>\n\n"
                "Die Nachricht wird an den konfigurierten Telegram-Chat gesendet.\n"
                "Für mehrere Empfänger TELEGRAM_BROADCAST_CHATS in .env setzen (kommagetrennt)."
            )
        # Collect target chat IDs
        broadcast_chats_env = os.getenv("TELEGRAM_BROADCAST_CHATS", "")
        chat_ids: List[str] = [c.strip() for c in broadcast_chats_env.split(",") if c.strip()]
        if TELEGRAM_CHAT_ID and TELEGRAM_CHAT_ID not in chat_ids:
            chat_ids.insert(0, TELEGRAM_CHAT_ID)
        if not chat_ids:
            return "❌ Keine Broadcast-Empfänger konfiguriert (TELEGRAM_CHAT_ID fehlt)."
        formatted = f"📢 <b>Broadcast</b>\n\n{msg}"
        sent = 0
        failed = 0
        for cid in chat_ids:
            try:
                await send_telegram(formatted, chat_id=cid)
                sent += 1
            except Exception:
                failed += 1
        return (
            f"✅ Broadcast gesendet!\n"
            f"📨 Empfänger: {sent} erfolgreich"
            + (f", {failed} fehlgeschlagen" if failed else "")
            + f"\n📝 Nachricht: {msg[:80]}{'...' if len(msg) > 80 else ''}"
        )

    async def _cmd_generate(self, text: str, session_id: str) -> str:
        """Startet den Product Generator via Telegram."""
        import aiohttp, re as _re
        # Optionale Anzahl aus Text extrahieren
        nums = _re.findall(r'\d+', text)
        count = min(int(nums[0]), 10) if nums else 3
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{smb_url}/api/products/generate",
                                  json={"count": count},
                                  timeout=aiohttp.ClientTimeout(total=10)) as r:
                    data = await r.json()
            return (f"🏭 Product Generator gestartet!\n"
                    f"Erstelle {count} neue Produkte aus aktuellen Trends.\n"
                    f"Ergebnis + Benachrichtigung kommt in ~2 Min.\n\n"
                    f"Parallel wird auf Telegram + Slack + Mailchimp + Klaviyo gepostet.")
        except Exception as e:
            return f"Generator Fehler: {e}"

    async def _cmd_generate_niche(self, text: str, session_id: str) -> str:
        """Generiert 5 Produkte aus einer Nische via Telegram."""
        import aiohttp
        # Nische aus Text extrahieren
        known = ["smart_home","fitness","kitchen","office","beauty","outdoor","pet","gaming"]
        niche = None
        for n in known:
            if n in text.lower().replace(" ", "_"):
                niche = n
                break
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{smb_url}/api/products/generate-niche",
                                  json={"niche": niche},
                                  timeout=aiohttp.ClientTimeout(total=10)) as r:
                    data = await r.json()
            niche_name = niche or "zufällig"
            return (f"🎯 Nichen-Generator gestartet: {niche_name}\n"
                    f"Erstelle 5 Produkte aus dieser Nische.\n"
                    f"Verfügbare Nischen: {', '.join(known)}")
        except Exception as e:
            return f"Niche Generator Fehler: {e}"

    async def _cmd_ds24_create(self, text: str, session_id: str) -> str:
        """Legt ein neues DS24-Produkt an. Usage: /ds24 Konzept €97."""
        import aiohttp, re
        # Preis aus Text extrahieren
        m = re.search(r"€?\s*(\d+(?:[.,]\d+)?)", text)
        price = m.group(1).replace(",", ".") if m else "97.00"
        # Konzept = Text ohne Preis/Befehlswörter
        concept = re.sub(r"(/ds24[_\w]*|ds24|digistore|produkt|anlegen|€?\s*\d+[.,]?\d*)", "", text, flags=re.I).strip()
        if not concept or len(concept) < 5:
            concept = "KI-gestütztes E-Commerce Automatisierungs-System 2026"
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{smb_url}/api/ds24/product/create",
                                  json={"concept": concept, "price": price},
                                  timeout=aiohttp.ClientTimeout(total=60)) as r:
                    data = await r.json()
            if data.get("ok"):
                return (f"✅ DS24-Produkt erstellt!\n"
                        f"📦 {data.get('name','')}\n"
                        f"💶 €{data.get('price','')}\n"
                        f"🆔 ID: {data.get('product_id','')}\n"
                        f"🛒 Checkout: {data.get('checkout_link','')}\n"
                        f"🔗 Affiliate: {data.get('affiliate_link','')}")
            return f"DS24 Fehler: {data.get('error','unbekannt')}"
        except Exception as e:
            return f"DS24 Create Fehler: {e}"

    async def _cmd_ds24_auto(self, text: str, session_id: str) -> str:
        """Erstellt 2 DS24-Produkte vollautomatisch aus Templates."""
        import aiohttp
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{smb_url}/api/ds24/product/auto",
                                  json={"count": 2},
                                  timeout=aiohttp.ClientTimeout(total=120)) as r:
                    data = await r.json()
            created = data.get("created", 0)
            products = data.get("products", [])
            lines = [f"🎯 DS24 Auto-Create: {created} Produkte erstellt!\n"]
            for p in products[:3]:
                lines.append(f"• {p.get('name','')[:45]} (€{p.get('price','')}, {p.get('commission','')})")
            return "\n".join(lines)
        except Exception as e:
            return f"DS24 Auto Fehler: {e}"

    async def _cmd_ds24_fix(self, text: str, session_id: str) -> str:
        """Repariert DS24-Produkt 669750 (Zahlungsplan + Aktivierung)."""
        import aiohttp
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{smb_url}/api/ds24/fix/669750",
                                  timeout=aiohttp.ClientTimeout(total=30)) as r:
                    data = await r.json()
            if data.get("ok"):
                return (f"✅ DS24 Produkt 669750 repariert!\n"
                        f"Plan-ID: {data.get('payment_plan_added','')}\n"
                        f"🛒 {data.get('checkout_link','')}")
            return f"Fix 669750 Fehler: {data}"
        except Exception as e:
            return f"DS24 Fix Fehler: {e}"

    async def _cmd_ds24_1000(self, text: str, session_id: str) -> str:
        """Startet die Massenanlage von 1000 DS24-Produkten mit SEO. [PREMIUM]"""
        gate = self._require_premium(session_id)
        if gate:
            return gate
        import aiohttp
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{smb_url}/api/ds24/create-1000",
                                  timeout=aiohttp.ClientTimeout(total=15)) as r:
                    data = await r.json()
            if data.get("ok"):
                return ("🚀 DS24 Massenanleger gestartet!\n\n"
                        "📦 Ziel: 1000 Produkte mit SEO\n"
                        "👷 5 parallele Worker\n"
                        "⏱️ ca. 60-90 Minuten\n\n"
                        "Telegram-Updates alle 100 Produkte.")
            return f"DS24 1000 Fehler: {data.get('error','?')}"
        except Exception as e:
            return f"DS24 1000 Fehler: {e}"

    async def _cmd_shopify_stats(self, text: str, session_id: str) -> str:
        """Shopify Store Statistiken ohne AI."""
        import aiohttp
        shop = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        ver = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        if not shop or not token:
            return "Shopify nicht konfiguriert (SHOPIFY_SHOP_DOMAIN fehlt)"
        headers = {"X-Shopify-Access-Token": token}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://{shop}/admin/api/{ver}/products/count.json", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    prod_count = (await r.json()).get("count", 0)
                async with s.get(f"https://{shop}/admin/api/{ver}/orders/count.json?status=any", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    order_count = (await r.json()).get("count", 0)
                async with s.get(f"https://{shop}/admin/api/{ver}/customers/count.json", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    cust_count = (await r.json()).get("count", 0)
            return (f"🛒 <b>Shopify Stats</b>\n"
                    f"📦 Produkte: {prod_count}\n"
                    f"📋 Bestellungen: {order_count}\n"
                    f"👥 Kunden: {cust_count}\n"
                    f"🌐 Shop: {shop}")
        except Exception as e:
            return f"Shopify Stats Fehler: {e}"

    async def _cmd_shopify_products(self, text: str, session_id: str) -> str:
        """Zeigt letzte 5 Shopify-Produkte."""
        import aiohttp
        shop = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        ver = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        if not shop or not token:
            return "Shopify nicht konfiguriert"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://{shop}/admin/api/{ver}/products.json?limit=5&fields=title,status,variants",
                    headers={"X-Shopify-Access-Token": token},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    products = (await r.json()).get("products", [])
            lines = [f"🛍 <b>Letzte Shopify-Produkte</b>"]
            for p in products:
                price = p.get("variants", [{}])[0].get("price", "?")
                lines.append(f"• {p['title'][:50]} — €{price}")
            return "\n".join(lines)
        except Exception as e:
            return f"Shopify Produkte Fehler: {e}"

    async def _cmd_scheduler_status_info(self, text: str, session_id: str) -> str:
        """Zeigt Scheduler-Status ohne AI."""
        import aiohttp
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{smb_url}/api/automation/status", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    data = await r.json()
            st = data.get("status", {})
            tasks = st.get("tasks", [])
            running = st.get("running", False)
            total_tasks = st.get("task_count", len(tasks))
            ok_tasks = sum(1 for t in tasks if isinstance(t, dict) and t.get("ok", 0) == t.get("total", 0) and t.get("total", 0) > 0)
            last_runs = []
            for t in sorted(tasks, key=lambda x: x.get("last_run","") if isinstance(x,dict) else "", reverse=True)[:3]:
                if isinstance(t, dict):
                    last_runs.append(f"• {t.get('name','?')}: {t.get('last_run','')[:16]}")
            return (f"⚙️ <b>Scheduler Status</b>\n"
                    f"{'✅ Läuft' if running else '❌ Gestoppt'}\n"
                    f"📊 {total_tasks} Tasks total\n"
                    f"✅ {ok_tasks} fehlerfrei\n"
                    f"\n<b>Zuletzt ausgeführt:</b>\n" + "\n".join(last_runs))
        except Exception as e:
            return f"Scheduler Fehler: {e}"

    async def _cmd_trend_analyse(self, text: str, session_id: str) -> str:
        """Trend-Analyse via AI."""
        prompt = "Analysiere 3 aktuelle E-Commerce Trends für den deutschen Markt 2026. Kurz und konkret."
        result = await self.bot.ai.chat([{"role": "user", "content": prompt}], task="fast")
        return f"📈 <b>Trend-Analyse</b>\n{result}" if result and not result.startswith("KI momentan") else "📈 Trend-Analyse: KI momentan nicht verfügbar"

    async def _cmd_ds24_revenue(self, text: str, session_id: str) -> str:
        """Zeigt DS24 Umsatz und Bestellungen."""
        try:
            from modules.ds24_product_creator import DS24_KEY, DS24_BASE
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{DS24_BASE}/getOrderList",
                    headers={"x-ds-api-key": DS24_KEY, "Content-Type": "application/json"},
                    json={"data": {"date_range": "today"}},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    data = await r.json()
            if data.get("result") == "success":
                orders = data.get("data", {}).get("orders", []) or []
                total = sum(float(o.get("amount", 0)) for o in orders)
                return (f"💶 DS24 Umsatz heute:\n"
                        f"€{total:.2f} | {len(orders)} Bestellungen\n"
                        f"📦 Produkte: 417 aktiv")
            return f"DS24 Umsatz: €0.00 (0 Bestellungen heute)"
        except Exception as e:
            return f"DS24 Umsatz Fehler: {e}"

    async def _cmd_ds24_status(self, text: str, session_id: str) -> str:
        """Zeigt DS24 Produkt-Statistiken."""
        import aiohttp
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{smb_url}/api/ds24/status",
                                 timeout=aiohttp.ClientTimeout(total=15)) as r:
                    data = await r.json()
            if data.get("ok"):
                cats = data.get("by_category", {})
                cat_str = "\n".join(f"  • {k}: {v}" for k, v in list(cats.items())[:5])
                return (f"📊 DS24 Status:\n\n"
                        f"📦 Gesamt: {data.get('total', 0)} Produkte\n"
                        f"✅ Aktiv: {data.get('active', 0)}\n\n"
                        f"Top Kategorien:\n{cat_str}")
            return f"DS24 Status Fehler: {data.get('error','?')}"
        except Exception as e:
            return f"DS24 Status Fehler: {e}"

    async def _cmd_ds24_refill(self, text: str, session_id: str) -> str:
        """Füllt DS24-Produkte auf 1000 auf."""
        import aiohttp
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{smb_url}/api/ds24/refill",
                                  json={"target": 1000},
                                  timeout=aiohttp.ClientTimeout(total=30)) as r:
                    data = await r.json()
            if data.get("ok"):
                return (f"🔄 DS24 Refill läuft!\n\n"
                        f"✅ Erstellt: {data.get('created', 0)}\n"
                        f"📦 Aktiv: {data.get('total_active', 0)}/1000")
            return f"DS24 Refill Fehler: {data.get('error','?')}"
        except Exception as e:
            return f"DS24 Refill Fehler: {e}"

    async def _cmd_ds24_seo_blast(self, text: str, session_id: str) -> str:
        """Blastet Top-DS24-Produkte auf allen Kanälen."""
        import aiohttp
        try:
            smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{smb_url}/api/ds24/seo-blast",
                                  json={"count": 10},
                                  timeout=aiohttp.ClientTimeout(total=60)) as r:
                    data = await r.json()
            if data.get("ok"):
                return f"🔥 DS24 SEO Blast: {data.get('blasted', 0)} Produkte geblasten!"
            return f"DS24 Blast Fehler: {data.get('error','?')}"
        except Exception as e:
            return f"DS24 Blast Fehler: {e}"

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

    async def _cmd_export_kunden(self, text: str, session_id: str) -> str:
        """Shopify-Kunden → Klaviyo aiitec + Mailchimp exportieren."""
        try:
            from modules.customer_exporter import run_full_export
            r = await run_full_export()
            kl = r.get("klaviyo", {})
            mc = r.get("mailchimp", {})
            return (
                f"🔄 <b>Kunden Export abgeschlossen!</b>\n\n"
                f"👥 Shopify: {r.get('total_customers',0)} Kunden\n"
                f"📧 Mit Email: {r.get('emails_found',0)}\n"
                f"🛒 Käufer: {r.get('buyers',0)}\n\n"
                f"📊 Klaviyo: {kl.get('synced',0)} importiert\n"
                f"📮 Mailchimp: {mc.get('subscribed',0)} abonniert\n"
                f"📋 Details per Telegram gesendet"
            )
        except Exception as e:
            return f"Export Fehler: {e}"

    async def _cmd_selbstverbesserung(self, text: str, session_id: str) -> str:
        """Alle Plattformen analysieren + Auto-Fix."""
        try:
            from modules.selbstverbesserung import run_selbstverbesserung_cycle
            r = await run_selbstverbesserung_cycle()
            return (f"🔧 Selbstverbesserung:\n"
                    f"✅ OK: {r.get('ok_count',0)}/{r.get('platforms_checked',0)}\n"
                    f"❌ Issues: {r.get('issues_found',0)}\n"
                    f"🛠️ Fixes: {r.get('fixes_applied',0)}")
        except Exception as e:
            return f"Selbstverbesserung Fehler: {e}"

    async def _cmd_email_doctor(self, text: str, session_id: str) -> str:
        """E-Mail Health Check aller Systeme."""
        try:
            from modules.email_doctor import run_email_doctor
            r = await run_email_doctor()
            return (f"💊 Email Doctor:\n"
                    f"Klaviyo: {r.get('klaviyo','?')}\n"
                    f"Mailchimp: {r.get('mailchimp','?')}\n"
                    f"Dragon: {r.get('dragon','?')}\n"
                    f"SendGrid: {r.get('sendgrid','?')}\n"
                    f"Twilio: {r.get('twilio','?')}\n"
                    f"Issues: {r.get('issues',0)} | Fixes: {r.get('fixes',0)}")
        except Exception as e:
            return f"Email Doctor Fehler: {e}"

    async def _cmd_dragon_artikel(self, text: str, session_id: str) -> str:
        """Nächsten Dragon Mailchimp Artikel senden."""
        try:
            from modules.mailchimp_dragon_1000 import run_dragon_article_cycle, get_dragon_article_stats
            r = await run_dragon_article_cycle()
            stats = await get_dragon_article_stats()
            if r.get("ok"):
                return (f"📧 Dragon Artikel gesendet:\n"
                        f"📝 Thema: {r.get('topic','?')}\n"
                        f"📊 Fortschritt: {stats.get('total_sent',0)}/1000\n"
                        f"⏳ Verbleibend: {stats.get('remaining',0)} Themen")
            return f"Dragon Artikel Fehler: {r.get('error','?')}"
        except Exception as e:
            return f"Dragon Artikel Fehler: {e}"

    async def _cmd_mass_blast(self, text: str, session_id: str) -> str:
        """1000 Content-Pieces über alle Kanäle blasten."""
        try:
            from modules.mass_content_blaster import run_mass_blast, get_mass_blast_stats
            r = await run_mass_blast(topics_per_run=5)
            stats = await get_mass_blast_stats()
            return (f"🚀 Mass Blast:\n"
                    f"Posts gesamt: {r.get('total_posted',0)}\n"
                    f"Plattformen: {r.get('platforms_hit',0)}\n"
                    f"Themen: {r.get('topics_used',0)}\n"
                    f"Fortschritt: {stats.get('progress','0/1000')}")
        except Exception as e:
            return f"Mass Blast Fehler: {e}"

    async def _cmd_system_overview(self, text: str, session_id: str) -> str:
        """Kompletter System-Überblick aller Plattformen."""
        try:
            from modules.selbstverbesserung import get_system_overview
            r = await get_system_overview()
            platforms = r.get("platforms", [])
            ok = [p for p in platforms if "✅" in p.get("status", "")]
            err = [p for p in platforms if "❌" in p.get("status", "")]
            lines = [f"🌐 System Overview: {r.get('summary','?')}"]
            if ok:
                lines.append("✅ " + " | ".join(p["platform"] for p in ok[:10]))
            if err:
                lines.append("❌ " + " | ".join(p["platform"] for p in err[:10]))
            return "\n".join(lines)
        except Exception as e:
            return f"System Overview Fehler: {e}"

    async def _cmd_quantum_repair(self, text: str, session_id: str) -> str:
        """Quantum Self-Repair durchführen."""
        try:
            from modules.quantum_self_repair import run_quantum_scan
            r = await run_quantum_scan()
            return (f"🔧 Quantum Repair:\n"
                    f"Wiederkehrend: {r.get('recurring_errors',0)}\n"
                    f"Fixes: {r.get('fix_count',0)}\n"
                    f"Fehler gesamt: {r.get('error_stats',{}).get('total_occurrences',0)}")
        except Exception as e:
            return f"Quantum Repair Fehler: {e}"

    async def _cmd_linkedin_post(self, text: str, session_id: str) -> str:
        """LinkedIn Post veröffentlichen."""
        try:
            from core.automation_scheduler import task_linkedin_auto_post
            return await task_linkedin_auto_post()
        except Exception as e:
            return f"LinkedIn Fehler: {e}"

    async def _cmd_instagram_post(self, text: str, session_id: str) -> str:
        """Instagram Post veröffentlichen."""
        try:
            from core.automation_scheduler import task_instagram_auto_post
            return await task_instagram_auto_post()
        except Exception as e:
            return f"Instagram Fehler: {e}"

    async def _cmd_pinterest_post(self, text: str, session_id: str) -> str:
        """Pinterest Pin veröffentlichen."""
        try:
            from core.automation_scheduler import task_pinterest_auto_post
            return await task_pinterest_auto_post()
        except Exception as e:
            return f"Pinterest Fehler: {e}"

    async def _cmd_printify_status(self, text: str, session_id: str) -> str:
        """Printify Status."""
        try:
            from modules.printify_automation import ping, get_shops
            ok = await ping()
            if ok:
                shops = await get_shops()
                return f"Printify: ✅ Verbunden | {len(shops)} Shop(s)"
            return "Printify: ❌ Nicht verbunden (PRINTIFY_API_TOKEN fehlt oder ungültig)"
        except Exception as e:
            return f"Printify Fehler: {e}"

    async def _cmd_printful_status(self, text: str, session_id: str) -> str:
        """Printful Status."""
        try:
            from modules.printful_automation import ping
            result = await ping()
            if isinstance(result, tuple):
                ok, info = result
            else:
                ok, info = bool(result), str(result)
            return f"Printful: {'✅ ' + str(info) if ok else '❌ ' + str(info)}"
        except Exception as e:
            return f"Printful Fehler: {e}"

    async def _cmd_gumroad_status(self, text: str, session_id: str) -> str:
        """Gumroad Status."""
        try:
            from modules.ecommerce_connectors import GumroadConnector
            g = GumroadConnector()
            r = await g.ping()
            return f"Gumroad: {'✅ ' + str(r) if r.get('connected') else '❌ ' + r.get('error','?')}"
        except Exception as e:
            return f"Gumroad: 🔗 {os.getenv('DS24_AFFILIATE_LINK','https://www.checkout-ds24.com/product/668035')}"

    async def _cmd_paypal_status(self, text: str, session_id: str) -> str:
        """PayPal Status."""
        try:
            from modules.paypal_client import get_status
            r = await get_status()
            return f"PayPal: {r}"
        except Exception as e:
            return f"PayPal: Sandbox ✅ | Live Keys → developer.paypal.com → RudiBot → LIVE Tab"

    async def _cmd_klaviyo_blast(self, text: str, session_id: str) -> str:
        """Klaviyo Campaign senden."""
        try:
            from core.automation_scheduler import task_klaviyo_daily_campaign
            return await task_klaviyo_daily_campaign()
        except Exception as e:
            return f"Klaviyo Fehler: {e}"

    async def _cmd_ebay_blast(self, text: str, session_id: str) -> str:
        """eBay Blast durchführen."""
        try:
            from core.automation_scheduler import task_ebay_blast
            return await task_ebay_blast()
        except Exception as e:
            return f"eBay Fehler: {e}"

    async def _cmd_amazon_blast(self, text: str, session_id: str) -> str:
        """Amazon Blast durchführen."""
        try:
            from core.automation_scheduler import task_amazon_blast
            return await task_amazon_blast()
        except Exception as e:
            return f"Amazon Fehler: {e}"

    async def _cmd_twilio_blast(self, text: str, session_id: str) -> str:
        """Twilio SMS senden."""
        try:
            from core.automation_scheduler import task_twilio_morning_brief
            return await task_twilio_morning_brief()
        except Exception as e:
            return f"Twilio Fehler: {e}"


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
                except Exception:
                    pass

            repair = await self.healer.heal(e, f"processing command: {text[:100]}")
            if repair["success"]:
                return await self.router.route(text, session_id)
            return f"Fehler (wird repariert): {type(e).__name__}: {str(e)[:100]}"

    async def _health_loop(self) -> None:
        """Periodically verify Ollama is reachable and restart it if it has gone offline."""
        import shutil
        # On Railway/cloud: ollama is not available — skip silently
        if not shutil.which("ollama"):
            log.info("Ollama not available (cloud deployment) — health loop disabled")
            return
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
