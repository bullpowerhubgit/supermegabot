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

def _load_tokens():
    """Lädt Telegram-Tokens aus .env falls nicht als Umgebungsvariable gesetzt."""
    try:
        sys.path.insert(0, str(ARMY_DIR / "shared"))
        from bus import get_env
        for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "AUTHORIZED_USER_ID"):
            if not os.environ.get(key):
                val = get_env(key)
                if val:
                    os.environ[key] = val
        if not os.environ.get("TELEGRAM_CHAT_ID"):
            v = os.environ.get("AUTHORIZED_USER_ID", "")
            if v:
                os.environ["TELEGRAM_CHAT_ID"] = v
    except Exception:
        pass

try:
    _load_tokens()
    sys.path.insert(0, os.path.expanduser("~"))
    from self_learner_core import SelfLearner as _SelfLearner
    _LEARNER_AVAILABLE = True
except Exception:
    _SelfLearner = None
    _LEARNER_AVAILABLE = False


class _DummyLearner:
    """Fallback wenn SelfLearner nicht verfügbar — Agent läuft trotzdem."""
    def register(self, *a, **k): pass
    def handle(self, *a, **k): return "Learner nicht verfügbar"
    def log_cycle(self, *a, **k): pass
    def skills_summary(self): return "Learner nicht verfügbar"
    def self_analysis(self): return "Learner nicht verfügbar"


class AgentLearner:
    """Crashsicherer Wrapper um SelfLearner für Army-Agenten."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._cycle = 0
        self._learner = None
        try:
            if _LEARNER_AVAILABLE:
                # telegram_notify=False bei Init — kein Spam bei jedem Start
                self._learner = _SelfLearner(f"army_{agent_id}", telegram_notify=False)
                self._learner.load_learned_skills()
                # Telegram erst nach erstem erfolgreichem Zyklus aktivieren
                self._learner.telegram_notify = bool(
                    os.environ.get("TELEGRAM_BOT_TOKEN") and
                    os.environ.get("TELEGRAM_CHAT_ID")
                )
        except Exception as e:
            self._learner = None

    def _get(self):
        return self._learner if self._learner else _DummyLearner()

    def register(self, name: str, handler, desc: str = ""):
        try:
            self._get().register(name, handler, desc)
        except Exception:
            pass

    def handle(self, command: str) -> str:
        try:
            return self._get().handle(command)
        except Exception as e:
            return f"Fehler: {e}"

    def log_cycle(self, status: str, msg: str, data: dict = None):
        """Jeden Agent-Zyklus tracken; täglich Zusammenfassung senden."""
        self._cycle += 1
        try:
            if self._learner:
                self._learner._log("INFO", f"[{self.agent_id}] {status}: {msg}")
            # Alle 720 Zyklen (~24h bei 120s sleep) → Telegram-Zusammenfassung
            if self._cycle % 720 == 0 and self._learner:
                n = len(self._learner.skills) if self._learner else 0
                self._learner.send_telegram(
                    f"📊 *{self.agent_id} Tages-Report*\n"
                    f"Status: {status}\n{msg}\nSkills: {n}"
                )
        except Exception:
            pass

    def skills_summary(self) -> str:
        try:
            return self._get().skills_summary()
        except Exception:
            return "Learner nicht verfügbar"

    def self_analysis(self) -> str:
        try:
            return self._get().self_analysis()
        except Exception:
            return "Learner nicht verfügbar"
