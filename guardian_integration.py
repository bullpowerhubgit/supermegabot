#!/usr/bin/env python3
"""
🤖 SuperMegaBot + Guardian Integration

Lazy-loads the GuardianClient so importing this module never crashes the
dashboard / orchestrator when GUARDIAN_API_SECRET isn't set.
"""

import sys
import os
from pathlib import Path

# Portable: try project-local first, then the rudibot-eternal sibling repo,
# overridable via $ETERNAL_BOT_DIR.
_HERE = Path(__file__).resolve().parent
for _cand in (
    _HERE,
    Path(os.environ.get("ETERNAL_BOT_DIR", "")) if os.environ.get("ETERNAL_BOT_DIR") else None,
    Path.home() / "rudibot-eternal",
):
    if _cand and (_cand / "guardian_client.py").exists():
        sys.path.insert(0, str(_cand))
        break

from guardian_client import GuardianClient


class SuperMegaBotGuardian:
    """SuperMegaBot mit Guardian Überwachung (Client wird lazy initialisiert)."""

    def __init__(self):
        self._client = None
        self.project_name = "supermegabot"

    @property
    def client(self) -> GuardianClient:
        """Create the GuardianClient on first use so missing env vars don't
        crash module import."""
        if self._client is None:
            self._client = GuardianClient()
        return self._client
        
    def startup(self):
        """Start melden"""
        self.client.notify(f"🚀 {self.project_name} startet...")
        
        # Als Agent registrieren
        self.client.register_agent(
            agent_id=f"proj-{self.project_name}",
            agent_type="service",
            endpoint=f"http://localhost:{os.getenv('PORT', '3200')}"
        )
        
        # Guardian Status prüfen
        health = self.client.health()
        if health['status'] != 'healthy':
            self.client.notify("⚠️ Guardian meldet Probleme!", priority="high")
            # Auto-heal
            self.client.heal_service('rudibot_main')
    
    def on_error(self, error_msg: str):
        """Fehler an Guardian melden"""
        self.client.notify(
            f"🔴 {self.project_name} Fehler: {error_msg[:200]}",
            priority="high"
        )
    
    def shutdown(self):
        """Stop melden"""
        self.client.notify(f"🛑 {self.project_name} wird gestoppt")

# Singleton für einfachen Zugriff
guardian = SuperMegaBotGuardian()

if __name__ == '__main__':
    guardian.startup()
    print("✅ SuperMegaBot mit Guardian verbunden!")
