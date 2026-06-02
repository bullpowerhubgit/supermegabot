#!/usr/bin/env python3
"""
Agent Data Bridge - Daten-Sharing zwischen allen Agenten
============================================================
Ermöglicht:
- Zentralisierte Datenspeicherung
- Echtzeit-Daten-Sharing
- Agent-zu-Agent Kommunikation
- Daten-Synchronisation
- API-Endpunkte für alle Agenten
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
BRIDGE_DB = DATA_DIR / "agent_bridge.db"
SHARED_DATA_FILE = DATA_DIR / "shared_agent_data.json"


class AgentDataBridge:
    """Zentrale Datenbrücke für alle Agenten"""

    def __init__(self):
        self.data_dir = DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.shared_data_file = SHARED_DATA_FILE
        self.subscribers: Dict[str, List[callable]] = {}
        self._init_storage()

    def _init_storage(self):
        """Initialisiert Storage"""
        if not self.shared_data_file.exists():
            self._save_shared_data({
                "created_at": datetime.now().isoformat(),
                "agents": {},
                "messages": [],
                "events": [],
                "commands": [],
                "status": "active"
            })

    def _load_shared_data(self) -> Dict:
        try:
            with open(self.shared_data_file, 'r') as f:
                return json.load(f)
        except Exception:
            return {"agents": {}, "messages": [], "events": [], "commands": []}

    def _save_shared_data(self, data: Dict):
        try:
            with open(self.shared_data_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Speichern fehlgeschlagen: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    # AGENT REGISTRATION
    # ═══════════════════════════════════════════════════════════════════════════

    def register_agent(self, agent_id: str, agent_data: Dict[str, Any]) -> Dict:
        """Registriert einen Agenten"""
        data = self._load_shared_data()
        if "agents" not in data:
            data["agents"] = {}

        data["agents"][agent_id] = {
            "registered_at": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "status": "online",
            "data": agent_data,
            "capabilities": agent_data.get("capabilities", []),
            "metrics": agent_data.get("metrics", {})
        }

        self._save_shared_data(data)
        logger.info(f"🤖 Agent registriert: {agent_id}")
        return {"success": True, "agent_id": agent_id}

    def update_agent(self, agent_id: str, update_data: Dict[str, Any]) -> Dict:
        """Aktualisiert Agenten-Daten"""
        data = self._load_shared_data()
        if agent_id not in data.get("agents", {}):
            return {"success": False, "error": "Agent nicht gefunden"}

        data["agents"][agent_id]["last_seen"] = datetime.now().isoformat()
        data["agents"][agent_id]["data"].update(update_data)
        if "metrics" in update_data:
            data["agents"][agent_id]["metrics"].update(update_data["metrics"])

        self._save_shared_data(data)
        return {"success": True}

    def unregister_agent(self, agent_id: str) -> Dict:
        """Entfernt Agenten-Registrierung"""
        data = self._load_shared_data()
        if agent_id in data.get("agents", {}):
            data["agents"][agent_id]["status"] = "offline"
            data["agents"][agent_id]["last_seen"] = datetime.now().isoformat()
            self._save_shared_data(data)
        return {"success": True}

    def get_agent(self, agent_id: str) -> Optional[Dict]:
        """Gibt Agenten-Daten zurück"""
        data = self._load_shared_data()
        return data.get("agents", {}).get(agent_id)

    def get_all_agents(self) -> Dict[str, Dict]:
        """Gibt alle registrierten Agenten zurück"""
        data = self._load_shared_data()
        return data.get("agents", {})

    # ═══════════════════════════════════════════════════════════════════════════
    # DATA SHARING
    # ═══════════════════════════════════════════════════════════════════════════

    def share_data(self, agent_id: str, key: str, value: Any, scope: str = "all") -> Dict:
        """Teilt Daten mit anderen Agenten"""
        data = self._load_shared_data()
        if "shared" not in data:
            data["shared"] = {}

        entry = {
            "agent_id": agent_id,
            "key": key,
            "value": value,
            "scope": scope,  # "all", "specific:<agent_id>", "group:<group>"
            "timestamp": datetime.now().isoformat()
        }

        if key not in data["shared"]:
            data["shared"][key] = []
        data["shared"][key].append(entry)

        # Max 50 Einträge pro Key
        data["shared"][key] = data["shared"][key][-50:]

        self._save_shared_data(data)

        # Notify subscribers
        self._notify_subscribers(agent_id, key, value)

        return {"success": True, "shared": True}

    def get_shared_data(self, key: str = None, agent_id: str = None, since: str = None) -> Dict:
        """Holt geteilte Daten"""
        data = self._load_shared_data()
        shared = data.get("shared", {})

        if key:
            entries = shared.get(key, [])
            if agent_id:
                entries = [e for e in entries if e["agent_id"] == agent_id]
            if since:
                entries = [e for e in entries if e["timestamp"] >= since]
            return {"key": key, "entries": entries}

        return {"keys": list(shared.keys()), "data": shared}

    # ═══════════════════════════════════════════════════════════════════════════
    # MESSAGING
    # ═══════════════════════════════════════════════════════════════════════════

    def send_message(self, from_agent: str, to_agent: str, message_type: str, content: Dict) -> Dict:
        """Sendet Nachricht zwischen Agenten"""
        data = self._load_shared_data()
        if "messages" not in data:
            data["messages"] = []

        msg = {
            "id": f"msg_{int(time.time() * 1000)}",
            "from": from_agent,
            "to": to_agent,  # "all" für Broadcast
            "type": message_type,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "read": False
        }

        data["messages"].append(msg)
        data["messages"] = data["messages"][-200:]  # Max 200 Nachrichten

        self._save_shared_data(data)
        return {"success": True, "message_id": msg["id"]}

    def get_messages(self, agent_id: str = None, message_type: str = None, unread_only: bool = False) -> List[Dict]:
        """Holt Nachrichten für Agenten"""
        data = self._load_shared_data()
        messages = data.get("messages", [])

        if agent_id:
            messages = [m for m in messages if m["to"] in [agent_id, "all"] or m["from"] == agent_id]
        if message_type:
            messages = [m for m in messages if m["type"] == message_type]
        if unread_only:
            messages = [m for m in messages if not m.get("read", False)]

        return messages[-50:]

    def mark_read(self, message_id: str) -> Dict:
        """Markiert Nachricht als gelesen"""
        data = self._load_shared_data()
        for msg in data.get("messages", []):
            if msg["id"] == message_id:
                msg["read"] = True
                break
        self._save_shared_data(data)
        return {"success": True}

    # ═══════════════════════════════════════════════════════════════════════════
    # COMMANDS
    # ═══════════════════════════════════════════════════════════════════════════

    def execute_command(self, from_agent: str, target_agent: str, command: str, params: Dict = None) -> Dict:
        """Führt Befehl auf anderem Agenten aus"""
        data = self._load_shared_data()
        if "commands" not in data:
            data["commands"] = []

        cmd = {
            "id": f"cmd_{int(time.time() * 1000)}",
            "from": from_agent,
            "target": target_agent,
            "command": command,
            "params": params or {},
            "status": "pending",
            "timestamp": datetime.now().isoformat(),
            "result": None
        }

        data["commands"].append(cmd)
        data["commands"] = data["commands"][-100:]

        self._save_shared_data(data)
        return {"success": True, "command_id": cmd["id"], "status": "pending"}

    def get_commands(self, target_agent: str = None, status: str = None) -> List[Dict]:
        """Holt Befehle"""
        data = self._load_shared_data()
        commands = data.get("commands", [])

        if target_agent:
            commands = [c for c in commands if c["target"] == target_agent]
        if status:
            commands = [c for c in commands if c["status"] == status]

        return commands

    def update_command_status(self, command_id: str, status: str, result: Dict = None) -> Dict:
        """Aktualisiert Befehls-Status"""
        data = self._load_shared_data()
        for cmd in data.get("commands", []):
            if cmd["id"] == command_id:
                cmd["status"] = status
                cmd["result"] = result
                cmd["completed_at"] = datetime.now().isoformat()
                break
        self._save_shared_data(data)
        return {"success": True}

    # ═══════════════════════════════════════════════════════════════════════════
    # EVENTS
    # ═══════════════════════════════════════════════════════════════════════════

    def publish_event(self, agent_id: str, event_type: str, event_data: Dict) -> Dict:
        """Veröffentlicht Event"""
        data = self._load_shared_data()
        if "events" not in data:
            data["events"] = []

        event = {
            "id": f"evt_{int(time.time() * 1000)}",
            "agent_id": agent_id,
            "type": event_type,
            "data": event_data,
            "timestamp": datetime.now().isoformat()
        }

        data["events"].append(event)
        data["events"] = data["events"][-100:]

        self._save_shared_data(data)
        return {"success": True, "event_id": event["id"]}

    def get_events(self, event_type: str = None, agent_id: str = None, limit: int = 50) -> List[Dict]:
        """Holt Events"""
        data = self._load_shared_data()
        events = data.get("events", [])

        if event_type:
            events = [e for e in events if e["type"] == event_type]
        if agent_id:
            events = [e for e in events if e["agent_id"] == agent_id]

        return events[-limit:]

    # ═══════════════════════════════════════════════════════════════════════════
    # SUBSCRIPTIONS
    # ═══════════════════════════════════════════════════════════════════════════

    def subscribe(self, agent_id: str, callback: callable):
        """Abonniert Daten-Updates"""
        if agent_id not in self.subscribers:
            self.subscribers[agent_id] = []
        self.subscribers[agent_id].append(callback)

    def unsubscribe(self, agent_id: str, callback: callable):
        """Beendet Abonnement"""
        if agent_id in self.subscribers:
            self.subscribers[agent_id] = [c for c in self.subscribers[agent_id] if c != callback]

    def _notify_subscribers(self, agent_id: str, key: str, value: Any):
        """Benachrichtigt Abonnenten"""
        for sub_agent, callbacks in self.subscribers.items():
            if sub_agent != agent_id:  # Nicht sich selbst benachrichtigen
                for callback in callbacks:
                    try:
                        callback(agent_id, key, value)
                    except Exception:
                        pass

    # ═══════════════════════════════════════════════════════════════════════════
    # SYSTEM STATUS
    # ═══════════════════════════════════════════════════════════════════════════

    def get_system_status(self) -> Dict:
        """Gibt Gesamt-System-Status zurück"""
        data = self._load_shared_data()
        agents = data.get("agents", {})

        online_agents = [a for a in agents.values() if a.get("status") == "online"]
        offline_agents = [a for a in agents.values() if a.get("status") != "online"]

        return {
            "timestamp": datetime.now().isoformat(),
            "total_agents": len(agents),
            "online_agents": len(online_agents),
            "offline_agents": len(offline_agents),
            "agent_list": list(agents.keys()),
            "active_messages": len([m for m in data.get("messages", []) if not m.get("read", False)]),
            "pending_commands": len([c for c in data.get("commands", []) if c.get("status") == "pending"]),
            "recent_events": len(data.get("events", []))
        }

    def get_dashboard_data(self) -> Dict:
        """Gibt Dashboard-Daten zurück"""
        status = self.get_system_status()
        agents = self.get_all_agents()

        return {
            "status": status,
            "agents": {
                agent_id: {
                    "status": agent_data.get("status", "unknown"),
                    "last_seen": agent_data.get("last_seen"),
                    "capabilities": agent_data.get("capabilities", []),
                    "metrics": agent_data.get("metrics", {})
                }
                for agent_id, agent_data in agents.items()
            },
            "recent_messages": self.get_messages()[-10:],
            "recent_events": self.get_events()[-10:],
            "pending_commands": self.get_commands(status="pending")
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_bridge = None

def get_data_bridge() -> AgentDataBridge:
    global _bridge
    if _bridge is None:
        _bridge = AgentDataBridge()
    return _bridge


# ═══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS (für Integration mit Dashboard Server)
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_api_request(path: str, method: str, data: Dict = None) -> Dict:
    """Verarbeitet API-Anfragen für die Data Bridge"""
    bridge = get_data_bridge()
    data = data or {}

    if path == "/agents" and method == "GET":
        return {"success": True, "agents": bridge.get_all_agents()}

    elif path == "/agents/register" and method == "POST":
        return bridge.register_agent(data.get("agent_id"), data.get("data", {}))

    elif path == "/agents/update" and method == "POST":
        return bridge.update_agent(data.get("agent_id"), data.get("data", {}))

    elif path == "/messages" and method == "GET":
        return {"success": True, "messages": bridge.get_messages(
            data.get("agent_id"), data.get("type"), data.get("unread_only", False)
        )}

    elif path == "/messages/send" and method == "POST":
        return bridge.send_message(
            data.get("from"), data.get("to"), data.get("type", "general"), data.get("content", {})
        )

    elif path == "/commands" and method == "GET":
        return {"success": True, "commands": bridge.get_commands(
            data.get("target_agent"), data.get("status")
        )}

    elif path == "/commands/execute" and method == "POST":
        return bridge.execute_command(
            data.get("from"), data.get("target"), data.get("command"), data.get("params", {})
        )

    elif path == "/status" and method == "GET":
        return {"success": True, "status": bridge.get_system_status()}

    elif path == "/dashboard" and method == "GET":
        return {"success": True, "data": bridge.get_dashboard_data()}

    elif path == "/share" and method == "POST":
        return bridge.share_data(
            data.get("agent_id"), data.get("key"), data.get("value"), data.get("scope", "all")
        )

    elif path == "/share/data" and method == "GET":
        return bridge.get_shared_data(
            data.get("key"), data.get("agent_id"), data.get("since")
        )

    elif path == "/events" and method == "GET":
        return {"success": True, "events": bridge.get_events(
            data.get("type"), data.get("agent_id"), data.get("limit", 50)
        )}

    elif path == "/events/publish" and method == "POST":
        return bridge.publish_event(data.get("agent_id"), data.get("event_type"), data.get("data", {}))

    return {"success": False, "error": "Unknown endpoint"}


if __name__ == "__main__":
    async def test():
        bridge = get_data_bridge()
        print("🌉 Agent Data Bridge Test")
        print("=" * 50)

        # Agent registrieren
        print("\n1. Registriere Agenten...")
        r = bridge.register_agent("mac_optimizer", {
            "capabilities": ["cleanup", "security", "performance"],
            "metrics": {"health_score": 95}
        })
        print(f"   Ergebnis: {r}")

        # Daten teilen
        print("\n2. Teile Daten...")
        r = bridge.share_data("mac_optimizer", "disk_usage", {"percent": 72})
        print(f"   Ergebnis: {r}")

        # Nachricht senden
        print("\n3. Sende Nachricht...")
        r = bridge.send_message("mac_optimizer", "all", "status_update", {"health": "good"})
        print(f"   Ergebnis: {r}")

        # Status abrufen
        print("\n4. System Status...")
        status = bridge.get_system_status()
        print(f"   Agenten: {status['total_agents']}, Online: {status['online_agents']}")

        # Dashboard
        print("\n5. Dashboard Daten...")
        dash = bridge.get_dashboard_data()
        print(f"   Daten verfügbar: {list(dash.keys())}")

        print("\n✅ Test abgeschlossen")

    asyncio.run(test())
