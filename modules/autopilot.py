#!/usr/bin/env python3
"""
AutoPilot System - Multi-Agent AI Orchestration
CEO Agent, Shopify Agent, Marketing Agent, Coding Agent etc.
100% local via Ollama + optional OpenAI/Claude fallback
"""

import asyncio
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("AutoPilot")

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "autopilot.db"
OLLAMA_BASE   = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEEPSEEK_KEY  = os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROQ_KEY      = os.getenv("GROQ_API_KEY", "")

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


# ---------------------------------------------------------------------------
# Agent Definitions
# ---------------------------------------------------------------------------

AGENTS = {
    "ceo": {
        "name": "CEO Agent",
        "emoji": "👑",
        "role": "Strategischer Entscheider und Koordinator",
        "system": "Du bist der CEO eines AI-Automatisierungs-Startups. Deine Aufgabe ist Strategie, Priorisierung und Delegation. Sei präzise, entscheidungsfreudig und zukunftsorientiert. Antworte auf Deutsch.",
        "color": "#ffd700",
    },
    "shopify": {
        "name": "Shopify Agent",
        "emoji": "🛒",
        "role": "E-Commerce Automation & Store-Optimierung",
        "system": "Du bist ein Shopify-Experte mit Fokus auf Produkte, SEO, Conversion-Optimierung und Store-Automation. Du kennst GraphQL, Shopify APIs und E-Commerce-Strategien. Antworte auf Deutsch.",
        "color": "#96f7d2",
    },
    "marketing": {
        "name": "Marketing Agent",
        "emoji": "📣",
        "role": "Content, Ads, Social Media & Growth",
        "system": "Du bist ein Performance-Marketing-Experte. Erstelle Ads, Content, Social Media Posts und Wachstumsstrategien. Fokus auf ROI und Konversionen. Antworte auf Deutsch.",
        "color": "#ff6b6b",
    },
    "coding": {
        "name": "Coding Agent",
        "emoji": "💻",
        "role": "Code-Entwicklung, Debugging & Architektur",
        "system": "Du bist ein Senior Full-Stack-Entwickler. Schreibe sauberen, effizienten Code in Python, JavaScript, TypeScript, Node.js. Analysiere Fehler und erstelle Lösungen. Antworte auf Deutsch.",
        "color": "#6c63ff",
    },
    "research": {
        "name": "Research Agent",
        "emoji": "🔬",
        "role": "Marktanalyse, Trends & Wettbewerber",
        "system": "Du bist ein Marktanalyst. Recherchiere Trends, analysiere Wettbewerber und identifiziere Chancen. Liefere präzise Daten und Handlungsempfehlungen. Antworte auf Deutsch.",
        "color": "#4facfe",
    },
    "finance": {
        "name": "Finance Agent",
        "emoji": "💰",
        "role": "Crypto, Trading, Finanzen & Steuern",
        "system": "Du bist ein Finanzexperte für Krypto-Trading, Arbitrage, Steuern und Finanzplanung. Analysiere Märkte und erstelle Finanzstrategien. Antworte auf Deutsch.",
        "color": "#43d98c",
    },
    "automation": {
        "name": "Automation Agent",
        "emoji": "⚙️",
        "role": "Workflow-Automation & System-Integration",
        "system": "Du bist ein Automation-Experte. Baue Workflows, verbinde APIs, automatisiere Prozesse und erstelle Self-Healing-Systeme. Antworte auf Deutsch.",
        "color": "#f093fb",
    },
    "security": {
        "name": "Security Agent",
        "emoji": "🛡️",
        "role": "Sicherheit, API-Keys & System-Schutz",
        "system": "Du bist ein Security-Experte. Prüfe Systeme auf Schwachstellen, sichere APIs und implementiere Best Practices. Antworte auf Deutsch.",
        "color": "#ff4757",
    },
}


# ---------------------------------------------------------------------------
# Memory for agents
# ---------------------------------------------------------------------------

class AgentMemory:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS agent_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT,
                task TEXT,
                result TEXT,
                timestamp TEXT
            );
            CREATE TABLE IF NOT EXISTS agent_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT,
                key TEXT,
                value TEXT,
                updated_at TEXT,
                UNIQUE(agent, key)
            );
            CREATE TABLE IF NOT EXISTS autopilot_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT,
                assigned_to TEXT,
                status TEXT DEFAULT 'pending',
                result TEXT,
                created_at TEXT,
                completed_at TEXT
            );
        """)
        conn.commit()
        conn.close()

    def log(self, agent: str, task: str, result: str):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO agent_logs (agent,task,result,timestamp) VALUES (?,?,?,?)",
                     (agent, task[:500], result[:2000], datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def remember(self, agent: str, key: str, value: str):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR REPLACE INTO agent_memory (agent,key,value,updated_at) VALUES (?,?,?,?)",
                     (agent, key, value, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def recall(self, agent: str, key: str) -> Optional[str]:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT value FROM agent_memory WHERE agent=? AND key=?", (agent, key)).fetchone()
        conn.close()
        return row[0] if row else None

    def get_logs(self, agent: str = None, limit: int = 20) -> List[Dict]:
        conn = sqlite3.connect(DB_PATH)
        if agent:
            rows = conn.execute("SELECT agent,task,result,timestamp FROM agent_logs WHERE agent=? ORDER BY id DESC LIMIT ?",
                                (agent, limit)).fetchall()
        else:
            rows = conn.execute("SELECT agent,task,result,timestamp FROM agent_logs ORDER BY id DESC LIMIT ?",
                                (limit,)).fetchall()
        conn.close()
        return [{"agent": r[0], "task": r[1], "result": r[2], "timestamp": r[3]} for r in rows]

    def create_task(self, task: str, assigned_to: str) -> int:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("INSERT INTO autopilot_tasks (task,assigned_to,status,created_at) VALUES (?,?,?,?)",
                           (task, assigned_to, "pending", datetime.now().isoformat()))
        task_id = cur.lastrowid
        conn.commit()
        conn.close()
        return task_id

    def complete_task(self, task_id: int, result: str):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE autopilot_tasks SET status='completed', result=?, completed_at=? WHERE id=?",
                     (result[:2000], datetime.now().isoformat(), task_id))
        conn.commit()
        conn.close()

    def get_tasks(self, limit: int = 20) -> List[Dict]:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT id,task,assigned_to,status,result,created_at FROM autopilot_tasks ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()
        conn.close()
        return [{"id": r[0], "task": r[1], "agent": r[2], "status": r[3], "result": r[4], "created_at": r[5]} for r in rows]


# ---------------------------------------------------------------------------
# AI Provider — Anthropic → DeepSeek → Groq → Ollama (lokal)
# ---------------------------------------------------------------------------

async def ai_complete(system: str, prompt: str, model_hint: str = "fast") -> str:
    """Delegates to central ai_client fallback chain (Anthropic→OpenAI→Gemini→OpenRouter→Perplexity)."""
    try:
        from modules.ai_client import ai_complete as _central
        return await _central(prompt, system=system)
    except Exception as e:
        log.warning("ai_complete failed: %s", e)
    return "Kein AI-Provider verfügbar"


# ---------------------------------------------------------------------------
# Individual Agents
# ---------------------------------------------------------------------------

class Agent:
    def __init__(self, agent_id: str, memory: AgentMemory):
        self.id = agent_id
        self.config = AGENTS[agent_id]
        self.memory = memory

    async def run(self, task: str) -> str:
        task_id = self.memory.create_task(task, self.id)
        result = await ai_complete(
            system=self.config["system"],
            prompt=task,
            model_hint="smart"
        )
        self.memory.log(self.id, task, result)
        self.memory.complete_task(task_id, result)
        return result

    @property
    def name(self):
        return f"{self.config['emoji']} {self.config['name']}"


# ---------------------------------------------------------------------------
# AutoPilot Orchestrator
# ---------------------------------------------------------------------------

class AutoPilot:
    def __init__(self):
        self.memory = AgentMemory()
        self.agents = {aid: Agent(aid, self.memory) for aid in AGENTS}
        self.running = False

    def _route_task(self, task: str) -> str:
        """Determine best agent for task"""
        task_lower = task.lower()
        if any(w in task_lower for w in ["shopify", "produkt", "shop", "bestellung", "order"]):
            return "shopify"
        if any(w in task_lower for w in ["code", "bug", "programm", "script", "fix", "entwickl"]):
            return "coding"
        if any(w in task_lower for w in ["marketing", "ads", "social", "content", "instagram", "tiktok"]):
            return "marketing"
        if any(w in task_lower for w in ["trading", "arbitrage", "krypto", "bitcoin", "finanzen", "steuer"]):
            return "finance"
        if any(w in task_lower for w in ["analysiere", "recherche", "trend", "markt", "wettbewerb"]):
            return "research"
        if any(w in task_lower for w in ["automatisier", "workflow", "integration", "api verbind"]):
            return "automation"
        if any(w in task_lower for w in ["sicherheit", "security", "key", "passwort", "verschlüssel"]):
            return "security"
        if any(w in task_lower for w in ["strategie", "plan", "entscheid", "priorisier", "ziel"]):
            return "ceo"
        return "ceo"  # default

    async def run_task(self, task: str, agent_id: str = None) -> Dict:
        if not agent_id:
            agent_id = self._route_task(task)

        agent = self.agents[agent_id]
        log.info(f"[AutoPilot] {agent.name} ← {task[:60]}")
        start = time.time()
        result = await agent.run(task)
        ms = int((time.time() - start) * 1000)
        return {
            "agent": agent_id,
            "agent_name": agent.name,
            "task": task,
            "result": result,
            "duration_ms": ms,
            "timestamp": datetime.now().isoformat(),
        }

    async def run_autopilot_mode(self, goal: str) -> List[Dict]:
        """Full autopilot - CEO breaks goal into tasks, delegates to agents"""
        ceo = self.agents["ceo"]

        # CEO creates plan
        plan_prompt = f"""Ziel: {goal}

Erstelle einen Aktionsplan mit 3-5 konkreten Schritten.
Für jeden Schritt: welcher Agent (shopify/marketing/coding/research/finance/automation), was genau zu tun ist.
Format: JSON Liste: [{{"agent": "...", "task": "..."}}]
Nur JSON, kein anderer Text."""

        plan_text = await ai_complete(ceo.config["system"], plan_prompt, "smart")

        # Parse plan
        tasks = []
        try:
            import re
            json_match = re.search(r'\[.*\]', plan_text, re.DOTALL)
            if json_match:
                tasks = json.loads(json_match.group())
        except Exception:
            tasks = [{"agent": "ceo", "task": goal}]

        results = []
        for step in tasks[:5]:
            agent_id = step.get("agent", "ceo")
            task_text = step.get("task", goal)
            if agent_id not in self.agents:
                agent_id = "ceo"
            result = await self.run_task(task_text, agent_id)
            results.append(result)
            await asyncio.sleep(0.1)

        return results

    def get_logs(self, limit: int = 30) -> List[Dict]:
        return self.memory.get_logs(limit=limit)

    def get_tasks(self, limit: int = 20) -> List[Dict]:
        return self.memory.get_tasks(limit=limit)

    def get_agent_list(self) -> List[Dict]:
        return [
            {
                "id": aid,
                "name": cfg["name"],
                "emoji": cfg["emoji"],
                "role": cfg["role"],
                "color": cfg["color"],
            }
            for aid, cfg in AGENTS.items()
        ]
