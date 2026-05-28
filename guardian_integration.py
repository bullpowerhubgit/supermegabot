#!/usr/bin/env python3
"""
🤖 SuperMegaBot + Guardian Integration
"""

import sys
import os
sys.path.insert(0, '/Users/rudolfsarkany/rudibot-eternal')

from guardian_client import GuardianClient

class SuperMegaBotGuardian:
    """SuperMegaBot mit Guardian Überwachung"""
    
    def __init__(self):
        self.client = GuardianClient()
        self.project_name = "supermegabot"
        
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
