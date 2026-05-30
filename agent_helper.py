#!/usr/bin/env python3
"""
🆘 Agent Helper - Hilft anderen Agenten mit Guardian API
"""

import sys
import os
import json
from pathlib import Path
_eternal_dir = os.environ.get("ETERNAL_BOT_DIR", str(Path.home() / "rudibot-eternal"))
if _eternal_dir not in sys.path:
    sys.path.insert(0, _eternal_dir)

from guardian_client import GuardianClient

def help_agent(agent_name: str, action: str, **kwargs):
    """
    Hilft einem anderen Agenten mit Guardian API
    
    Args:
        agent_name: Name des Agenten der Hilfe braucht
        action: Was soll gemacht werden
        **kwargs: Zusätzliche Parameter
    
    Returns:
        dict: Ergebnis der Aktion
    """
    client = GuardianClient()
    
    actions = {
        'check_health': lambda: client.health(),
        'check_status': lambda: client.status(),
        'restart_service': lambda: client.restart_service(kwargs.get('service', 'rudibot_main')),
        'heal_service': lambda: client.heal_service(kwargs.get('service', 'rudibot_main')),
        'send_notification': lambda: client.notify(
            kwargs.get('message', f'Hilfe von {agent_name}'),
            priority=kwargs.get('priority', 'normal')
        ),
        'get_brain': lambda: client.brain_summary(),
        'list_agents': lambda: client.list_agents(),
        'create_backup': lambda: client.create_backup(),
        'register_agent': lambda: client.register_agent(
            agent_id=kwargs.get('agent_id', agent_name),
            agent_type=kwargs.get('agent_type', 'helper'),
            endpoint=kwargs.get('endpoint', '')
        ),
    }
    
    if action not in actions:
        return {'error': f'Unbekannte Aktion: {action}', 'available': list(actions.keys())}
    
    try:
        result = actions[action]()
        print(f"✅ {agent_name}: {action} erfolgreich")
        return result
    except Exception as e:
        error_msg = f"❌ {agent_name}: {action} fehlgeschlagen - {e}"
        print(error_msg)
        return {'error': str(e), 'action': action}

def show_help():
    """Zeigt alle verfügbaren Aktionen"""
    print("""
🤖 AGENT HELPER - Verfügbare Aktionen
═══════════════════════════════════════════════════════════════

1. check_health      - Prüfe Guardian Health
2. check_status      - Zeige vollen System Status
3. restart_service   - Restarte einen Service
4. heal_service      - Heile einen Service
5. send_notification - Sende Notification
6. get_brain         - Hole Brain Summary
7. list_agents       - Liste alle registrierten Agenten
8. create_backup     - Erstelle Backup
9. register_agent    - Registriere neuen Agenten

Verwendung:
    python3 agent_helper.py <agent_name> <aktion> [args]

Beispiele:
    # Health Check
    python3 agent_helper.py supermegabot check_health
    
    # Service restart
    python3 agent_helper.py telegram-bot restart_service --service rudibot_main
    
    # Notification senden
    python3 agent_helper.py rudibot send_notification --message "Hallo!"
    
    # Agent registrieren
    python3 agent_helper.py mein-agent register_agent --type monitoring

═══════════════════════════════════════════════════════════════
""")

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        show_help()
        sys.exit(0)
    
    if len(sys.argv) < 3:
        print("❌ Fehler: Benötige agent_name und action")
        print("Usage: python3 agent_helper.py <agent> <action>")
        sys.exit(1)
    
    agent_name = sys.argv[1]
    action = sys.argv[2]
    
    # Parse kwargs (einfache --key value Form)
    kwargs = {}
    i = 3
    while i < len(sys.argv):
        if sys.argv[i].startswith('--') and i + 1 < len(sys.argv):
            key = sys.argv[i][2:]
            value = sys.argv[i + 1]
            kwargs[key] = value
            i += 2
        else:
            i += 1
    
    result = help_agent(agent_name, action, **kwargs)
    print(json.dumps(result, indent=2, default=str))
