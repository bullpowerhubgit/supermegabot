"""AgentLearner — Selbstlern-Mixin für Army Agenten"""
import json, time, os
from pathlib import Path

BRAIN_DIR = Path(__file__).parent / "brain"
BRAIN_DIR.mkdir(exist_ok=True)


class AgentLearner:
    """Jeder Agent hat ein kleines Gehirn: merkt sich Patterns, lernt dazu."""

    def __init__(self, agent_id: str):
        self.id = agent_id
        self.brain_file = BRAIN_DIR / f"{agent_id}_brain.json"
        self.data = self._load()
        self._ensure_defaults()

    def _load(self) -> dict:
        try:
            if self.brain_file.exists():
                return json.loads(self.brain_file.read_text())
        except Exception:
            pass
        return {}

    def _save(self):
        try:
            self.brain_file.write_text(json.dumps(self.data, indent=2, default=str))
        except Exception:
            pass

    def _ensure_defaults(self):
        defaults = {
            "cycles": 0,
            "patterns": {},
            "registers": {},
            "history": [],
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for k, v in defaults.items():
            self.data.setdefault(k, v)

    def register(self, key: str, fn_or_value, description: str = ""):
        """Registriert einen Wert oder eine Funktion für Monitoring."""
        self.data["registers"][key] = {
            "description": description,
            "last_value": None,
            "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def log_cycle(self, status: str, message: str, metrics: dict = None):
        """Speichert einen Zyklus + lernt Patterns."""
        self.data["cycles"] += 1
        entry = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
            "message": message,
            "metrics": metrics or {},
        }
        self.data["history"].append(entry)
        self.data["history"] = self.data["history"][-500:]  # max 500 Einträge

        # Pattern-Learning: gleicher Fehler wiederholt?
        if status in ("error", "warning"):
            pattern_key = f"{status}:{message[:60]}"
            self.data["patterns"][pattern_key] = self.data["patterns"].get(pattern_key, 0) + 1

        self._save()

    def get_insights(self) -> list:
        """Gibt gelernte Insights zurück (häufige Patterns)."""
        insights = []
        for pattern, count in self.data.get("patterns", {}).items():
            if count >= 3:
                insights.append(f"🔁 {pattern} ({count}x)")
        return insights

    def summary(self) -> dict:
        return {
            "agent": self.id,
            "cycles": self.data["cycles"],
            "insights": self.get_insights(),
            "registers": list(self.data["registers"].keys()),
        }
