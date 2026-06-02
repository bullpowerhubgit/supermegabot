#!/usr/bin/env python3
"""
🤖 Template für Windsurf/VS Code Agenten
Kopieren und anpassen für jedes Projekt

Benötigt: pip install requests
"""

import sys
import json
import time
from pathlib import Path

# Guardian Client importieren (immer verfügbar)
import os
_eternal_dir = os.environ.get("ETERNAL_BOT_DIR", str(Path.home() / "rudibot-eternal"))
if _eternal_dir not in sys.path:
    sys.path.insert(0, _eternal_dir)
from guardian_client import GuardianClient

# ═══════════════════════════════════════════════════════════════════════
# DEINE AGENT-KONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

AGENT_ID = "supermegabot-main-agent"
AGENT_TYPE = "analyzer"  # monitoring, healer, notifier, analyzer

# ═══════════════════════════════════════════════════════════════════════
# AGENT-LOGIK
# ═══════════════════════════════════════════════════════════════════════

def main():
    """Hauptfunktion deines Agenten"""
    
    try:
        client = GuardianClient()
    except ValueError as e:
        print(f"❌ Guardian Client Fehler: {e}")
        return
    
    print(f"🤖 {AGENT_ID} startet...")
    print(f"   Typ: {AGENT_TYPE}")
    print(f"   Projekt: {Path.cwd().name}")
    
    # 1. Bei Guardian registrieren
    try:
        result = client.register_agent(AGENT_ID, AGENT_TYPE)
        if result.get('registered'):
            print(f"   ✅ Registriert")
        else:
            print(f"   ℹ️  {result}")
    except Exception as e:
        print(f"   ⚠️  Registrierung: {e}")
    
    # 2. Status abfragen
    try:
        status = client.status()
        print(f"\n📊 Guardian Status: {status.get('overall_health', 'unknown')}")
        print(f"   Services: {len(status.get('services', []))}")
    except Exception as e:
        print(f"   ❌ Status: {e}")
    
    # 3. DEINE LOGIK HIER EINFÜGEN
    print(f"\n🔍 {AGENT_TYPE} Logic:")
    
    if AGENT_TYPE == "monitoring":
        # Beispiel: Überwache Projektspezifische Dinge
        print("   • Überwache Projekt-Health...")
        
    elif AGENT_TYPE == "analyzer":
        # Beispiel: Analysiere Code/Logs
        print("   • Analysiere aktuelle Änderungen...")
        
    elif AGENT_TYPE == "healer":
        # Beispiel: Auto-Repair für Projekt
        print("   • Prüfe auf bekannte Probleme...")
        
    elif AGENT_TYPE == "notifier":
        # Beispiel: Sende Projekt-Benachrichtigungen
        print("   • Bereite Notifications vor...")
    
    # 4. Beispiel-Notification
    try:
        result = client.notify(
            f"🚀 {AGENT_ID} ({AGENT_TYPE}) ist online im Projekt {Path.cwd().name}",
            priority="normal"
        )
        print(f"\n📨 Notification gesendet: {result.get('sent', False)}")
    except Exception as e:
        print(f"   ⚠️  Notification: {e}")
    
    print(f"\n✨ {AGENT_ID} beendet.")

# ═══════════════════════════════════════════════════════════════════════
# START
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    main()
