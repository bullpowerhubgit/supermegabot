#!/usr/bin/env python3
"""
🧠 Learner Mixin — Self-Learning für jeden Army-Agent in 2 Zeilen
Usage:
    from learner_mixin import AgentLearner
    learner = AgentLearner("optimizer")
    learner.log_cycle(status="ok", msg="CPU:12%")
"""
import os, sys
from pathlib import Path

ARMY_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ARMY_DIR / "shared"))

def _load_tokens():
    """Lädt Telegram-Tokens aus .env falls nicht als Umgebungsvariable gesetzt."""
    from bus import get_env
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "AUTHORIZED_USER_ID"):
        if not os.environ.get(key):
            val = get_env(key)
            if val:
                os.environ[key] = val
    # TELEGRAM_CHAT_ID fallback auf AUTHORIZED_USER_ID
    if not os.environ.get("TELEGRAM_CHAT_ID"):
        v = os.environ.get("AUTHORIZED_USER_ID", "")
        if v:
            os.environ["TELEGRAM_CHAT_ID"] = v

_load_tokens()

# Jetzt erst SelfLearner importieren — Tokens sind gesetzt
sys.path.insert(0, os.path.expanduser("~"))
from self_learner_core import SelfLearner


class AgentLearner:
    """Dünner Wrapper um SelfLearner speziell für Army-Agenten."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._learner = SelfLearner(f"army_{agent_id}", telegram_notify=True)
        self._learner.load_learned_skills()
        self._cycle = 0

    # ── Skills registrieren ──────────────────────────────────────────────────

    def register(self, name: str, handler, desc: str = ""):
        """Skill beim Learner registrieren."""
        self._learner.register_skill(name, handler, desc=desc, source="built-in")

    def handle(self, command: str) -> str:
        """Befehl an Learner übergeben."""
        return self._learner.handle_command(command)

    # ── Zyklus-Logging ───────────────────────────────────────────────────────

    def log_cycle(self, status: str, msg: str, data: dict = None):
        """Jeden Agent-Zyklus tracken; täglich Zusammenfassung senden."""
        self._cycle += 1
        self._learner._log("INFO", f"[{self.agent_id}] {status}: {msg}")
        # Alle 720 Zyklen (~24h bei 120s sleep) → Telegram-Zusammenfassung
        if self._cycle % 720 == 0:
            self._learner.send_telegram(
                f"📊 *{self.agent_id} Tages-Report*\n"
                f"Status: {status}\n"
                f"{msg}\n"
                f"Skills: {len(self._learner.skills)}"
            )

    # ── Skill-Status ─────────────────────────────────────────────────────────

    def skills_summary(self) -> str:
        return self._learner.handle_command("/skills")

    def self_analysis(self) -> str:
        return self._learner.handle_command("/kann_ich")
