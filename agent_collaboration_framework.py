#!/usr/bin/env python3
"""
Agent Collaboration Framework - Helft anderen Agenten zusammenzuarbeiten und Issues zu fixen
Zentralisiert die Kommunikation zwischen verschiedenen Agenten und provides debugging tools
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import aiohttp
from dataclasses import dataclass

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(DATA_DIR / "collaboration.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("AgentCollaboration")

@dataclass
class AgentStatus:
    """Status eines einzelnen Agents"""
    name: str
    status: str  # "running", "stopped", "error", "idle"
    last_heartbeat: datetime
    capabilities: List[str]
    current_task: Optional[str] = None
    error_count: int = 0
    success_count: int = 0

@dataclass
class Issue:
    """Issue/Problem das gelöst werden muss"""
    id: str
    title: str
    description: str
    severity: str  # "low", "medium", "high", "critical"
    agent_assigned: Optional[str] = None
    status: str = "open"  # "open", "in_progress", "resolved", "failed"
    created_at: datetime = None
    resolved_at: Optional[datetime] = None
    solution: Optional[str] = None
    tags: List[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.tags is None:
            self.tags = []

class AgentRegistry:
    """Registry aller aktiven Agenten"""
    def __init__(self):
        self.agents: Dict[str, AgentStatus] = {}
        self.registry_file = DATA_DIR / "agent_registry.json"
        self._load_registry()

    def _load_registry(self):
        """Lade Registry von Disk"""
        try:
            if self.registry_file.exists():
                data = json.loads(self.registry_file.read_text())
                for name, agent_data in data.items():
                    self.agents[name] = AgentStatus(
                        name=agent_data["name"],
                        status=agent_data["status"],
                        last_heartbeat=datetime.fromisoformat(agent_data["last_heartbeat"]),
                        capabilities=agent_data["capabilities"],
                        current_task=agent_data.get("current_task"),
                        error_count=agent_data.get("error_count", 0),
                        success_count=agent_data.get("success_count", 0)
                    )
        except Exception as e:
            log.error(f"Fehler beim Laden der Registry: {e}")

    def _save_registry(self):
        """Speichere Registry auf Disk"""
        try:
            data = {}
            for name, agent in self.agents.items():
                data[name] = {
                    "name": agent.name,
                    "status": agent.status,
                    "last_heartbeat": agent.last_heartbeat.isoformat(),
                    "capabilities": agent.capabilities,
                    "current_task": agent.current_task,
                    "error_count": agent.error_count,
                    "success_count": agent.success_count
                }
            self.registry_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.error(f"Fehler beim Speichern der Registry: {e}")

    def register_agent(self, name: str, capabilities: List[str]) -> bool:
        """Registriere neuen Agent"""
        agent = AgentStatus(
            name=name,
            status="running",
            last_heartbeat=datetime.now(),
            capabilities=capabilities
        )
        self.agents[name] = agent
        self._save_registry()
        log.info(f"Agent '{name}' registriert mit Capabilities: {capabilities}")
        return True

    def update_heartbeat(self, name: str, status: str = None, current_task: str = None):
        """Update heartbeat und Status eines Agents"""
        if name in self.agents:
            self.agents[name].last_heartbeat = datetime.now()
            if status:
                self.agents[name].status = status
            if current_task:
                self.agents[name].current_task = current_task
            self._save_registry()

    def get_agents_by_capability(self, capability: str) -> List[AgentStatus]:
        """Finde Agenten mit bestimmter Capability"""
        return [agent for agent in self.agents.values() 
                if capability in agent.capabilities and agent.status == "running"]

    def get_best_agent_for_task(self, task_type: str) -> Optional[AgentStatus]:
        """Finde besten Agent für bestimmte Task"""
        candidates = self.get_agents_by_capability(task_type)
        if not candidates:
            return None
        # Wähle Agent mit höchster Success Rate
        return max(candidates, key=lambda a: a.success_count / (a.success_count + a.error_count + 1))

    def record_success(self, agent_name: str):
        """Record erfolgreiche Operation"""
        if agent_name in self.agents:
            self.agents[agent_name].success_count += 1
            self._save_registry()

    def record_error(self, agent_name: str):
        """Record fehlgeschlagene Operation"""
        if agent_name in self.agents:
            self.agents[agent_name].error_count += 1
            self._save_registry()

class IssueTracker:
    """Issue Tracking System"""
    def __init__(self):
        self.issues: Dict[str, Issue] = {}
        self.issues_file = DATA_DIR / "issues.json"
        self._load_issues()

    def _load_issues(self):
        """Lade Issues von Disk"""
        try:
            if self.issues_file.exists():
                data = json.loads(self.issues_file.read_text())
                for issue_id, issue_data in data.items():
                    self.issues[issue_id] = Issue(
                        id=issue_data["id"],
                        title=issue_data["title"],
                        description=issue_data["description"],
                        severity=issue_data["severity"],
                        agent_assigned=issue_data.get("agent_assigned"),
                        status=issue_data.get("status", "open"),
                        created_at=datetime.fromisoformat(issue_data["created_at"]),
                        resolved_at=datetime.fromisoformat(issue_data["resolved_at"]) if issue_data.get("resolved_at") else None,
                        solution=issue_data.get("solution"),
                        tags=issue_data.get("tags", [])
                    )
        except Exception as e:
            log.error(f"Fehler beim Laden der Issues: {e}")

    def _save_issues(self):
        """Speichere Issues auf Disk"""
        try:
            data = {}
            for issue_id, issue in self.issues.items():
                data[issue_id] = {
                    "id": issue.id,
                    "title": issue.title,
                    "description": issue.description,
                    "severity": issue.severity,
                    "agent_assigned": issue.agent_assigned,
                    "status": issue.status,
                    "created_at": issue.created_at.isoformat(),
                    "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
                    "solution": issue.solution,
                    "tags": issue.tags
                }
            self.issues_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.error(f"Fehler beim Speichern der Issues: {e}")

    def create_issue(self, title: str, description: str, severity: str = "medium", tags: List[str] = None) -> str:
        """Erstelle neues Issue"""
        issue_id = f"ISSUE_{int(time.time())}_{len(self.issues)}"
        issue = Issue(
            id=issue_id,
            title=title,
            description=description,
            severity=severity,
            tags=tags or []
        )
        self.issues[issue_id] = issue
        self._save_issues()
        log.info(f"Neues Issue erstellt: {issue_id} - {title}")
        return issue_id

    def assign_issue(self, issue_id: str, agent_name: str) -> bool:
        """Weise Issue einem Agent zu"""
        if issue_id in self.issues:
            self.issues[issue_id].agent_assigned = agent_name
            self.issues[issue_id].status = "in_progress"
            self._save_issues()
            log.info(f"Issue {issue_id} zugewiesen an Agent {agent_name}")
            return True
        return False

    def resolve_issue(self, issue_id: str, solution: str) -> bool:
        """Löse Issue"""
        if issue_id in self.issues:
            self.issues[issue_id].status = "resolved"
            self.issues[issue_id].resolved_at = datetime.now()
            self.issues[issue_id].solution = solution
            self._save_issues()
            log.info(f"Issue {issue_id} gelöst: {solution[:100]}")
            return True
        return False

    def get_open_issues(self, severity: str = None) -> List[Issue]:
        """Hole offene Issues"""
        issues = [issue for issue in self.issues.values() if issue.status in ["open", "in_progress"]]
        if severity:
            issues = [issue for issue in issues if issue.severity == severity]
        return sorted(issues, key=lambda i: (i.severity, i.created_at), reverse=True)

class CollaborationHub:
    """Zentrale Hub für Agenten-Kollaboration"""
    def __init__(self):
        self.registry = AgentRegistry()
        self.issue_tracker = IssueTracker()
        self.communication_log: List[Dict] = []
        self.log_file = DATA_DIR / "communication_log.json"

    async def register_agent(self, name: str, capabilities: List[str]) -> bool:
        """Registriere neuen Agent"""
        return self.registry.register_agent(name, capabilities)

    async def report_issue(self, title: str, description: str, severity: str = "medium", 
                          reporter: str = "system", tags: List[str] = None) -> str:
        """Reporte neues Issue"""
        issue_id = self.issue_tracker.create_issue(title, description, severity, tags)
        
        # Versuche automatisch zuzuweisen
        best_agent = self._find_best_agent_for_issue(title, description)
        if best_agent:
            self.issue_tracker.assign_issue(issue_id, best_agent.name)
            await self._notify_agent(best_agent.name, f"Neues Issue zugewiesen: {title}")
        
        self._log_communication("issue_reported", reporter, {"issue_id": issue_id, "title": title})
        return issue_id

    def _find_best_agent_for_issue(self, title: str, description: str) -> Optional[AgentStatus]:
        """Finde besten Agent für Issue basierend auf Titel und Beschreibung"""
        # Einfache Keyword-basierte Zuweisung
        keywords = {
            "trading": ["trading", "arbitrage", "preise", "krypto"],
            "system": ["system", "prozess", "cpu", "ram", "speicher"],
            "browser": ["browser", "web", "seite", "öffnen"],
            "mac": ["mac", "screenshot", "bildschirm", "datei"],
            "shopify": ["shopify", "produkt", "gmc", "ads"],
            "api": ["api", "endpoint", "request"],
            "ai": ["ki", "chat", "ollama", "lernen"]
        }
        
        text = (title + " " + description).lower()
        
        for capability, kw_list in keywords.items():
            if any(kw in text for kw in kw_list):
                agent = self.registry.get_best_agent_for_task(capability)
                if agent:
                    return agent
        
        return None

    async def request_help(self, agent_name: str, problem: str, context: Dict = None) -> Optional[str]:
        """Agent fragt um Hilfe"""
        # Finde passende Agenten basierend auf Problem
        best_agent = self._find_best_agent_for_issue("Help Request", problem)
        
        if best_agent and best_agent.name != agent_name:
            # Erstelle Issue für das Problem
            issue_id = await self.report_issue(
                f"Hilfe benötigt von {agent_name}",
                problem,
                severity="medium",
                reporter=agent_name,
                tags=["help_request"]
            )
            
            await self._notify_agent(best_agent.name, f"Hilfe-Anfrage von {agent_name}: {problem}")
            self._log_communication("help_request", agent_name, {"problem": problem, "assigned_to": best_agent.name})
            return issue_id
        
        return None

    async def share_solution(self, agent_name: str, issue_id: str, solution: str) -> bool:
        """Agent teilt Lösung für Issue"""
        # Update Issue
        success = self.issue_tracker.resolve_issue(issue_id, solution)
        
        if success:
            # Belohne Agent
            self.registry.record_success(agent_name)
            
            # Informiere andere Agenten über die Lösung
            await self._broadcast_solution(agent_name, issue_id, solution)
            self._log_communication("solution_shared", agent_name, {"issue_id": issue_id, "solution": solution[:200]})
        
        return success

    async def _notify_agent(self, agent_name: str, message: str):
        """Sende Nachricht an Agent (implementiert von einzelnen Agenten)"""
        log.info(f"Notification an {agent_name}: {message}")
        # In einer realen Implementierung würde hier eine Kommunikationsmethode aufgerufen

    async def _broadcast_solution(self, solver: str, issue_id: str, solution: str):
        """Broadcaste Lösung an alle Agenten"""
        issue = self.issue_tracker.issues.get(issue_id)
        if issue:
            message = f"✅ Lösung von {solver} für '{issue.title}': {solution[:200]}..."
            log.info(f"Broadcast: {message}")

    def _log_communication(self, action: str, agent: str, data: Dict):
        """Logge Kommunikation"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "agent": agent,
            "data": data
        }
        self.communication_log.append(entry)
        
        # Speichere Log (begrenzte Größe)
        if len(self.communication_log) > 1000:
            self.communication_log = self.communication_log[-1000:]
        
        try:
            with open(self.log_file, "w") as f:
                json.dump(self.communication_log, f, indent=2)
        except Exception as e:
            log.error(f"Fehler beim Speichern des Kommunikations-Logs: {e}")

    def get_dashboard_status(self) -> Dict:
        """Erstelle Dashboard Status"""
        agents_status = {}
        for name, agent in self.registry.agents.items():
            agents_status[name] = {
                "status": agent.status,
                "capabilities": agent.capabilities,
                "success_rate": agent.success_count / (agent.success_count + agent.error_count + 1),
                "current_task": agent.current_task,
                "last_heartbeat": agent.last_heartbeat.isoformat()
            }
        
        open_issues = len(self.issue_tracker.get_open_issues())
        critical_issues = len(self.issue_tracker.get_open_issues("critical"))
        
        return {
            "agents": agents_status,
            "issues": {
                "open": open_issues,
                "critical": critical_issues,
                "total": len(self.issue_tracker.issues)
            },
            "collaboration_stats": {
                "total_communications": len(self.communication_log),
                "recent_solutions": len([c for c in self.communication_log[-50:] if c["action"] == "solution_shared"])
            }
        }

# Global Hub Instance
hub = CollaborationHub()

# Helper Functions für andere Module
async def register_agent(name: str, capabilities: List[str]) -> bool:
    """Registriere Agent im Collaboration Hub"""
    return await hub.register_agent(name, capabilities)

async def report_issue(title: str, description: str, severity: str = "medium", 
                      reporter: str = "system", tags: List[str] = None) -> str:
    """Reporte Issue an den Hub"""
    return await hub.report_issue(title, description, severity, reporter, tags)

async def request_help(agent_name: str, problem: str, context: Dict = None) -> Optional[str]:
    """Frage um Hilfe von anderen Agenten"""
    return await hub.request_help(agent_name, problem, context)

async def share_solution(agent_name: str, issue_id: str, solution: str) -> bool:
    """Teile Lösung mit anderen Agenten"""
    return await hub.share_solution(agent_name, issue_id, solution)

def get_dashboard_status() -> Dict:
    """Hole Dashboard Status"""
    return hub.get_dashboard_status()

if __name__ == "__main__":
    # Test
    async def test():
        # Registriere Test-Agenten
        await register_agent("test_trader", ["trading", "arbitrage"])
        await register_agent("test_system", ["system", "monitoring"])
        
        # Reporte Issue
        issue_id = await report_issue(
            "Trading Bot nicht erreichbar",
            "Der Trading Bot antwortet nicht auf API-Anfragen",
            severity="high",
            reporter="monitor",
            tags=["trading", "api"]
        )
        
        print(f"Issue erstellt: {issue_id}")
        print("Dashboard Status:", json.dumps(get_dashboard_status(), indent=2))
    
    asyncio.run(test())
