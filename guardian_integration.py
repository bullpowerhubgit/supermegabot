#!/usr/bin/env python3
"""SuperMegaBot + Guardian Integration (optional — graceful when not available)"""

import os
import sys
from pathlib import Path

_eternal_dir = os.environ.get("ETERNAL_BOT_DIR", str(Path.home() / "rudibot-eternal"))
if _eternal_dir not in sys.path:
    sys.path.insert(0, _eternal_dir)

from guardian_client import GuardianClient


class SuperMegaBotGuardian:
    """SuperMegaBot mit Guardian Überwachung. Guardian ist optional — kein Crash wenn nicht konfiguriert."""

    def __init__(self):
        try:
            self.client = GuardianClient()
        except Exception:
            self.client = None
        self.project_name = "supermegabot"

    def _ok(self) -> bool:
        return self.client is not None

    def startup(self):
        if not self._ok():
            return
        try:
            self.client.notify(f"🚀 {self.project_name} startet...")
            self.client.register_agent(
                agent_id=f"proj-{self.project_name}",
                agent_type="service",
                endpoint=f"http://localhost:{os.getenv('DASHBOARD_PORT', '8888')}"
            )
            health = self.client.health()
            if health.get("status") != "healthy":
                self.client.notify("⚠️ Guardian meldet Probleme!", priority="high")
        except Exception:
            pass

    def notify(self, msg: str, priority: str = "normal"):
        if not self._ok():
            return
        try:
            self.client.notify(msg, priority=priority)
        except Exception:
            pass

    def register_agent(self, **kwargs):
        if not self._ok():
            return
        try:
            self.client.register_agent(**kwargs)
        except Exception:
            pass

    def status(self):
        if not self._ok():
            return {"services": []}
        try:
            return self.client.status()
        except Exception:
            return {"services": []}

    def heal_service(self, name: str):
        if not self._ok():
            return
        try:
            self.client.heal_service(name)
        except Exception:
            pass

    def on_error(self, error_msg: str):
        self.notify(f"🔴 {self.project_name} Fehler: {error_msg[:200]}", priority="high")

    def shutdown(self):
        self.notify(f"🛑 {self.project_name} wird gestoppt")


# Singleton
guardian = SuperMegaBotGuardian()

if __name__ == "__main__":
    guardian.startup()
    print("✅ SuperMegaBot mit Guardian verbunden!" if guardian._ok() else "⚠️ Guardian nicht konfiguriert (GUARDIAN_API_SECRET fehlt)")
