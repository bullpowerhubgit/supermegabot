#!/usr/bin/env python3
"""
Agent Communication Protocols für SuperMegaBot
Ermöglicht strukturierte Kommunikation zwischen verschiedenen Agenten
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
import aiohttp
import uuid

# Import Collaboration Framework
from agent_collaboration_framework import hub, register_agent, report_issue, share_solution
from debug_tools import debugger, diagnose_and_fix_agent

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(DATA_DIR / "communication.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("AgentCommunication")

class MessageType(Enum):
    """Verschiedene Nachrichtentypen"""
    REQUEST_HELP = "request_help"
    OFFER_HELP = "offer_help"
    SHARE_SOLUTION = "share_solution"
    STATUS_UPDATE = "status_update"
    HEARTBEAT = "heartbeat"
    TASK_DELEGATION = "task_delegation"
    TASK_RESULT = "task_result"
    ERROR_REPORT = "error_report"
    SYSTEM_ALERT = "system_alert"
    COLLABORATION_REQUEST = "collaboration_request"

class Priority(Enum):
    """Nachrichten-Prioritäten"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class AgentMessage:
    """Struktur für Agenten-Nachrichten"""
    id: str
    sender: str
    recipient: Optional[str]  # None für Broadcast
    message_type: MessageType
    priority: Priority
    subject: str
    content: str
    timestamp: datetime
    reply_to: Optional[str] = None
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = None
    requires_ack: bool = True
    acknowledged: bool = False
    ack_timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.expires_at is None:
            # Standard: 1 Stunde Gültigkeit
            self.expires_at = self.timestamp + timedelta(hours=1)

class MessageQueue:
    """Message Queue für Agenten-Kommunikation"""
    def __init__(self):
        self.messages: Dict[str, AgentMessage] = {}
        self.agent_queues: Dict[str, List[str]] = {}  # agent_name -> message_ids
        self.queue_file = DATA_DIR / "message_queue.json"
        self.max_queue_size = 1000
        self._load_queue()

    def _load_queue(self):
        """Lade Queue von Disk"""
        try:
            if self.queue_file.exists():
                data = json.loads(self.queue_file.read_text())
                for msg_id, msg_data in data.get("messages", {}).items():
                    self.messages[msg_id] = AgentMessage(
                        id=msg_data["id"],
                        sender=msg_data["sender"],
                        recipient=msg_data.get("recipient"),
                        message_type=MessageType(msg_data["message_type"]),
                        priority=Priority(msg_data["priority"]),
                        subject=msg_data["subject"],
                        content=msg_data["content"],
                        timestamp=datetime.fromisoformat(msg_data["timestamp"]),
                        reply_to=msg_data.get("reply_to"),
                        expires_at=datetime.fromisoformat(msg_data["expires_at"]) if msg_data.get("expires_at") else None,
                        metadata=msg_data.get("metadata", {}),
                        requires_ack=msg_data.get("requires_ack", True),
                        acknowledged=msg_data.get("acknowledged", False),
                        ack_timestamp=datetime.fromisoformat(msg_data["ack_timestamp"]) if msg_data.get("ack_timestamp") else None
                    )
                self.agent_queues = data.get("agent_queues", {})
        except Exception as e:
            log.error(f"Fehler beim Laden der Message Queue: {e}")

    def _save_queue(self):
        """Speichere Queue auf Disk"""
        try:
            data = {
                "messages": {
                    msg_id: {
                        "id": msg.id,
                        "sender": msg.sender,
                        "recipient": msg.recipient,
                        "message_type": msg.message_type.value,
                        "priority": msg.priority.value,
                        "subject": msg.subject,
                        "content": msg.content,
                        "timestamp": msg.timestamp.isoformat(),
                        "reply_to": msg.reply_to,
                        "expires_at": msg.expires_at.isoformat() if msg.expires_at else None,
                        "metadata": msg.metadata,
                        "requires_ack": msg.requires_ack,
                        "acknowledged": msg.acknowledged,
                        "ack_timestamp": msg.ack_timestamp.isoformat() if msg.ack_timestamp else None
                    }
                    for msg_id, msg in self.messages.items()
                },
                "agent_queues": self.agent_queues
            }
            self.queue_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.error(f"Fehler beim Speichern der Message Queue: {e}")

    def add_message(self, message: AgentMessage) -> bool:
        """Füge Nachricht zur Queue hinzu"""
        # Prüfe Queue-Größe
        if len(self.messages) >= self.max_queue_size:
            self._cleanup_old_messages()
        
        self.messages[message.id] = message
        
        # Füge zu Empfänger-Queue hinzu
        if message.recipient:
            if message.recipient not in self.agent_queues:
                self.agent_queues[message.recipient] = []
            self.agent_queues[message.recipient].append(message.id)
        else:
            # Broadcast an alle Agenten
            for agent_name in hub.registry.agents.keys():
                if agent_name != message.sender:  # Nicht an sich selbst senden
                    if agent_name not in self.agent_queues:
                        self.agent_queues[agent_name] = []
                    self.agent_queues[agent_name].append(message.id)
        
        self._save_queue()
        log.info(f"Nachricht {message.id} von {message.sender} an {message.recipient or 'all'}")
        return True

    def get_messages_for_agent(self, agent_name: str, unack_only: bool = True) -> List[AgentMessage]:
        """Hole Nachrichten für einen Agenten"""
        message_ids = self.agent_queues.get(agent_name, [])
        messages = []
        
        for msg_id in message_ids[:]:  # Kopie für sichere Iteration
            if msg_id in self.messages:
                msg = self.messages[msg_id]
                
                # Prüfe ob Nachricht abgelaufen ist
                if datetime.now() > msg.expires_at:
                    self._remove_message(msg_id)
                    continue
                
                # Prüfe ob nur unbestätigte Nachrichten gewünscht sind
                if unack_only and msg.acknowledged:
                    continue
                
                messages.append(msg)
        
        # Sortiere nach Priorität und Zeitstempel
        priority_order = {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3}
        messages.sort(key=lambda m: (priority_order[m.priority], m.timestamp))
        
        return messages

    def acknowledge_message(self, message_id: str, agent_name: str) -> bool:
        """Bestätige Nachricht"""
        if message_id in self.messages:
            message = self.messages[message_id]
            if message.recipient == agent_name or message.recipient is None:
                message.acknowledged = True
                message.ack_timestamp = datetime.now()
                self._save_queue()
                log.info(f"Nachricht {message_id} von {agent_name} bestätigt")
                return True
        return False

    def _remove_message(self, message_id: str):
        """Entferne Nachricht aus Queue"""
        if message_id in self.messages:
            del self.messages[message_id]
            # Entferne aus allen Agent-Queues
            for agent_queue in self.agent_queues.values():
                if message_id in agent_queue:
                    agent_queue.remove(message_id)

    def _cleanup_old_messages(self):
        """Räume alte Nachrichten auf"""
        now = datetime.now()
        expired_messages = [msg_id for msg_id, msg in self.messages.items() if now > msg.expires_at]
        for msg_id in expired_messages:
            self._remove_message(msg_id)
        
        # Wenn immer noch zu viele, entferne die ältesten
        if len(self.messages) >= self.max_queue_size:
            sorted_messages = sorted(self.messages.items(), key=lambda x: x[1].timestamp)
            to_remove = sorted_messages[:len(self.messages) - self.max_queue_size + 100]
            for msg_id, _ in to_remove:
                self._remove_message(msg_id)

class CommunicationProtocol:
    """Kommunikations-Protokoll für Agenten"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.message_queue = MessageQueue()
        self.message_handlers: Dict[MessageType, Callable] = {}
        self.is_running = False
        self.processing_task = None
        
        # Registriere Standard-Handler
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """Registriere Standard-Message-Handler"""
        self.message_handlers[MessageType.HEARTBEAT] = self._handle_heartbeat
        self.message_handlers[MessageType.REQUEST_HELP] = self._handle_help_request
        self.message_handlers[MessageType.OFFER_HELP] = self._handle_help_offer
        self.message_handlers[MessageType.SHARE_SOLUTION] = self._handle_solution_share
        self.message_handlers[MessageType.STATUS_UPDATE] = self._handle_status_update
        self.message_handlers[MessageType.ERROR_REPORT] = self._handle_error_report
        self.message_handlers[MessageType.SYSTEM_ALERT] = self._handle_system_alert
    
    async def start_communication(self):
        """Starte Kommunikation"""
        if not self.is_running:
            self.is_running = True
            self.processing_task = asyncio.create_task(self._process_messages())
            log.info(f"Kommunikation für {self.agent_name} gestartet")
    
    async def stop_communication(self):
        """Stoppe Kommunikation"""
        self.is_running = False
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        log.info(f"Kommunikation für {self.agent_name} gestoppt")
    
    async def _process_messages(self):
        """Verarbeite eingehende Nachrichten"""
        while self.is_running:
            try:
                messages = self.message_queue.get_messages_for_agent(self.agent_name)
                
                for message in messages:
                    await self._handle_message(message)
                    
                    # Bestätige Nachricht
                    if message.requires_ack:
                        self.message_queue.acknowledge_message(message.id, self.agent_name)
                
                await asyncio.sleep(1)  # Alle 1 Sekunde prüfen
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Fehler bei der Nachrichtenverarbeitung: {e}")
                await asyncio.sleep(5)
    
    async def _handle_message(self, message: AgentMessage):
        """Verarbeite einzelne Nachricht"""
        try:
            handler = self.message_handlers.get(message.message_type)
            if handler:
                await handler(message)
            else:
                log.warning(f"Kein Handler für Nachrichtentyp: {message.message_type}")
        except Exception as e:
            log.error(f"Fehler bei der Verarbeitung von Nachricht {message.id}: {e}")
    
    async def send_message(self, recipient: Optional[str], message_type: MessageType, 
                          subject: str, content: str, priority: Priority = Priority.MEDIUM,
                          reply_to: Optional[str] = None, metadata: Dict = None) -> str:
        """Sende Nachricht"""
        message = AgentMessage(
            id=str(uuid.uuid4()),
            sender=self.agent_name,
            recipient=recipient,
            message_type=message_type,
            priority=priority,
            subject=subject,
            content=content,
            timestamp=datetime.now(),
            reply_to=reply_to,
            metadata=metadata or {}
        )
        
        self.message_queue.add_message(message)
        return message.id
    
    async def broadcast_message(self, message_type: MessageType, subject: str, 
                              content: str, priority: Priority = Priority.MEDIUM) -> str:
        """Sende Broadcast-Nachricht an alle Agenten"""
        return await self.send_message(None, message_type, subject, content, priority)
    
    async def request_help(self, problem: str, context: Dict = None, priority: Priority = Priority.HIGH) -> str:
        """Frage um Hilfe"""
        return await self.send_message(
            None,  # Broadcast
            MessageType.REQUEST_HELP,
            f"Hilfe benötigt: {problem[:50]}",
            json.dumps({"problem": problem, "context": context or {}}, indent=2),
            priority
        )
    
    async def offer_help(self, to_agent: str, problem: str, solution: str) -> str:
        """Biete Hilfe an"""
        return await self.send_message(
            to_agent,
            MessageType.OFFER_HELP,
            f"Lösungsvorschlag für: {problem[:50]}",
            json.dumps({"problem": problem, "solution": solution}, indent=2),
            Priority.MEDIUM
        )
    
    async def share_solution(self, problem: str, solution: str, issue_id: str = None) -> str:
        """Teile Lösung mit anderen Agenten"""
        metadata = {"issue_id": issue_id} if issue_id else {}
        return await self.broadcast_message(
            MessageType.SHARE_SOLUTION,
            f"Lösung gefunden: {problem[:50]}",
            json.dumps({"problem": problem, "solution": solution}, indent=2),
            Priority.MEDIUM,
            metadata=metadata
        )
    
    async def report_error(self, error: str, context: Dict = None, priority: Priority = Priority.HIGH) -> str:
        """Reporte Fehler"""
        return await self.broadcast_message(
            MessageType.ERROR_REPORT,
            f"Fehler in {self.agent_name}",
            json.dumps({"error": error, "context": context or {}}, indent=2),
            priority
        )
    
    async def send_heartbeat(self, status: str = "running", current_task: str = None) -> str:
        """Sende Heartbeat"""
        return await self.broadcast_message(
            MessageType.HEARTBEAT,
            f"Heartbeat von {self.agent_name}",
            json.dumps({"status": status, "current_task": current_task}, indent=2),
            Priority.LOW
        )
    
    async def send_status_update(self, status: Dict) -> str:
        """Sende Status-Update"""
        return await self.broadcast_message(
            MessageType.STATUS_UPDATE,
            f"Status-Update von {self.agent_name}",
            json.dumps(status, indent=2),
            Priority.LOW
        )
    
    # Default Handler
    async def _handle_heartbeat(self, message: AgentMessage):
        """Verarbeite Heartbeat"""
        try:
            data = json.loads(message.content)
            log.debug(f"Heartbeat von {message.sender}: {data.get('status')}")
            
            # Update Agent Registry
            hub.registry.update_heartbeat(
                message.sender, 
                data.get("status"), 
                data.get("current_task")
            )
        except Exception as e:
            log.error(f"Fehler bei Heartbeat-Verarbeitung: {e}")
    
    async def _handle_help_request(self, message: AgentMessage):
        """Verarbeite Hilfe-Anfrage"""
        try:
            data = json.loads(message.content)
            problem = data.get("problem", "")
            context = data.get("context", {})
            
            log.info(f"Hilfe-Anfrage von {message.sender}: {problem}")
            
            # Prüfe ob ich helfen kann
            if self._can_help(problem):
                solution = await self._generate_solution(problem, context)
                await self.offer_help(message.sender, problem, solution)
        except Exception as e:
            log.error(f"Fehler bei Hilfe-Anfrage: {e}")
    
    async def _handle_help_offer(self, message: AgentMessage):
        """Verarbeite Hilfe-Angebot"""
        try:
            data = json.loads(message.content)
            problem = data.get("problem", "")
            solution = data.get("solution", "")
            
            log.info(f"Hilfe-Angebot von {message.sender} für: {problem}")
            
            # Hier könnte die Lösung angewendet werden
            # Für jetzt: Log und teile mit Collaboration Hub
            issue_id = await report_issue(
                f"Hilfe erhalten von {message.sender}",
                f"Problem: {problem}\nLösung: {solution}",
                "low",
                self.agent_name,
                ["help_received"]
            )
        except Exception as e:
            log.error(f"Fehler bei Hilfe-Angebot: {e}")
    
    async def _handle_solution_share(self, message: AgentMessage):
        """Verarbeite geteilte Lösung"""
        try:
            data = json.loads(message.content)
            problem = data.get("problem", "")
            solution = data.get("solution", "")
            issue_id = message.metadata.get("issue_id")
            
            log.info(f"Lösung geteilt von {message.sender}: {problem}")
            
            # Speichere Lösung im Collaboration Hub
            if issue_id:
                await share_solution(message.sender, issue_id, solution)
        except Exception as e:
            log.error(f"Fehler bei Lösungs-Teilung: {e}")
    
    async def _handle_status_update(self, message: AgentMessage):
        """Verarbeite Status-Update"""
        try:
            status = json.loads(message.content)
            log.debug(f"Status-Update von {message.sender}: {status}")
        except Exception as e:
            log.error(f"Fehler bei Status-Update: {e}")
    
    async def _handle_error_report(self, message: AgentMessage):
        """Verarbeite Fehler-Report"""
        try:
            data = json.loads(message.content)
            error = data.get("error", "")
            context = data.get("context", {})
            
            log.warning(f"Fehler-Report von {message.sender}: {error}")
            
            # Erstelle Issue und versuche Auto-Fix
            issue_id = await report_issue(
                f"Fehler in {message.sender}",
                error,
                "high",
                message.sender,
                ["error_report"]
            )
            
            # Versuche automatische Diagnose
            await diagnose_and_fix_agent(message.sender, error, context)
        except Exception as e:
            log.error(f"Fehler bei Fehler-Report: {e}")
    
    async def _handle_system_alert(self, message: AgentMessage):
        """Verarbeite System-Alert"""
        try:
            alert_data = json.loads(message.content)
            log.warning(f"System-Alert von {message.sender}: {alert_data}")
            
            # System-Alerts haben hohe Priorität
            # Hier könnten Notfall-Maßnahmen eingeleitet werden
        except Exception as e:
            log.error(f"Fehler bei System-Alert: {e}")
    
    def _can_help(self, problem: str) -> bool:
        """Prüfe ob dieser Agent bei einem Problem helfen kann"""
        # Einfache Implementierung - kann von Subklassen überschrieben werden
        return False
    
    async def _generate_solution(self, problem: str, context: Dict) -> str:
        """Generiere Lösung für Problem"""
        # Einfache Implementierung - kann von Subklassen überschrieben werden
        return f"Standard-Lösungsvorschlag für: {problem}"

class AgentCommunicationManager:
    """Manager für alle Agenten-Kommunikationen"""
    
    def __init__(self):
        self.protocols: Dict[str, CommunicationProtocol] = {}
        self.cleanup_task = None
        self.is_running = False
    
    async def register_agent_protocol(self, agent_name: str, capabilities: List[str]) -> CommunicationProtocol:
        """Registriere Agenten-Protokoll"""
        # Registriere Agent im Hub
        await register_agent(agent_name, capabilities)
        
        # Erstelle Kommunikations-Protokoll
        protocol = CommunicationProtocol(agent_name)
        self.protocols[agent_name] = protocol
        
        # Starte Kommunikation
        await protocol.start_communication()
        
        log.info(f"Agenten-Protokoll für {agent_name} registriert")
        return protocol
    
    async def unregister_agent(self, agent_name: str):
        """Entferne Agenten-Protokoll"""
        if agent_name in self.protocols:
            await self.protocols[agent_name].stop_communication()
            del self.protocols[agent_name]
            log.info(f"Agenten-Protokoll für {agent_name} entfernt")
    
    async def get_communication_stats(self) -> Dict:
        """Hole Kommunikations-Statistiken"""
        queue = MessageQueue()
        
        total_messages = len(queue.messages)
        unack_messages = sum(1 for msg in queue.messages.values() if not msg.acknowledged)
        
        agent_stats = {}
        for agent_name, protocol in self.protocols.items():
            agent_messages = queue.get_messages_for_agent(agent_name, unack_only=False)
            agent_stats[agent_name] = {
                "total_messages": len(agent_messages),
                "unack_messages": len([m for m in agent_messages if not m.acknowledged]),
                "protocol_running": protocol.is_running
            }
        
        return {
            "total_messages": total_messages,
            "unacknowledged_messages": unack_messages,
            "active_protocols": len(self.protocols),
            "agent_stats": agent_stats
        }
    
    async def start_cleanup_task(self):
        """Starte Cleanup-Task"""
        if not self.is_running:
            self.is_running = True
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def stop_cleanup_task(self):
        """Stoppe Cleanup-Task"""
        self.is_running = False
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def _cleanup_loop(self):
        """Cleanup-Loop für alte Nachrichten"""
        while self.is_running:
            try:
                queue = MessageQueue()
                queue._cleanup_old_messages()
                await asyncio.sleep(300)  # Alle 5 Minuten aufräumen
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Fehler bei Cleanup: {e}")
                await asyncio.sleep(60)

# Global Manager
comm_manager = AgentCommunicationManager()

# Exportierte Funktionen
async def start_agent_communication(agent_name: str, capabilities: List[str]) -> CommunicationProtocol:
    """Starte Kommunikation für einen Agenten"""
    return await comm_manager.register_agent_protocol(agent_name, capabilities)

async def stop_agent_communication(agent_name: str):
    """Stoppe Kommunikation für einen Agenten"""
    await comm_manager.unregister_agent(agent_name)

async def get_communication_stats() -> Dict:
    """Hole Kommunikations-Statistiken"""
    return await comm_manager.get_communication_stats()

if __name__ == "__main__":
    # Test
    async def test_communication():
        # Starte Cleanup
        await comm_manager.start_cleanup_task()
        
        # Registriere Test-Agenten
        protocol1 = await start_agent_communication("test_agent1", ["trading", "analysis"])
        protocol2 = await start_agent_communication("test_agent2", ["system", "debugging"])
        
        # Sende Test-Nachrichten
        await protocol1.send_heartbeat("running", "analyzing markets")
        await protocol2.request_help("Trading Bot reagiert nicht", {"port": "3000"})
        
        # Warte auf Verarbeitung
        await asyncio.sleep(3)
        
        # Stats
        stats = await get_communication_stats()
        print("Kommunikations-Stats:", json.dumps(stats, indent=2))
        
        # Cleanup
        await stop_agent_communication("test_agent1")
        await stop_agent_communication("test_agent2")
        await comm_manager.stop_cleanup_task()
    
    asyncio.run(test_communication())
