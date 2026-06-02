#!/usr/bin/env python3
"""
Automated Issue Fixer Agent - Hilft anderen Agenten offene Issues zu fixen
Überwacht, analysiert und koordiniert die Lösung von Issues im Collaboration Framework
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

# Import Collaboration Framework
from agent_collaboration_framework import hub, report_issue, share_solution, get_dashboard_status
from agent_communication import start_agent_communication
from debug_tools import diagnose_and_fix_agent, get_system_health, IssueAnalyzer, AutoFixer

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(DATA_DIR / "issue_fixer.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("IssueFixerAgent")

class IssueFixerAgent:
    """Automatischer Agent für Issue-Behebung"""
    
    def __init__(self):
        self.name = "issue_fixer"
        self.protocol = None
        self.capabilities = ["issue_fixing", "debugging", "auto_repair", "coordination"]
        self.is_running = False
        self.issue_analyzer = IssueAnalyzer()
        self.autofixer = AutoFixer()
        self.fix_history: List[Dict] = []
        self.fix_history_file = DATA_DIR / "issue_fixer_history.json"
        self._load_fix_history()
    
    def _load_fix_history(self):
        """Lade Fix-Historie"""
        try:
            if self.fix_history_file.exists():
                self.fix_history = json.loads(self.fix_history_file.read_text())
        except Exception as e:
            log.error(f"Fehler beim Laden der Fix-Historie: {e}")
    
    def _save_fix_history(self):
        """Speichere Fix-Historie"""
        try:
            self.fix_history_file.write_text(json.dumps(self.fix_history, indent=2))
        except Exception as e:
            log.error(f"Fehler beim Speichern der Fix-Historie: {e}")
    
    async def start(self):
        """Starte den Issue Fixer Agent"""
        try:
            # Registriere Agenten
            self.protocol = await start_agent_communication(self.name, self.capabilities)
            
            # Starte Main Loop
            asyncio.create_task(self.main_loop())
            
            # Starte Heartbeat
            asyncio.create_task(self.heartbeat_loop())
            
            self.is_running = True
            log.info(f"✅ {self.name} Agent gestartet")
            
        except Exception as e:
            log.error(f"❌ Start von {self.name} fehlgeschlagen: {e}")
    
    async def stop(self):
        """Stoppe den Issue Fixer Agent"""
        self.is_running = False
        if self.protocol:
            await self.protocol.send_heartbeat("stopped", "agent stopped")
        log.info(f"{self.name} Agent gestoppt")
    
    async def heartbeat_loop(self):
        """Sende regelmäßige Heartbeats"""
        while self.is_running:
            try:
                status = "running" if self.is_running else "stopped"
                task = f"monitoring {len(self.get_open_issues())} issues"
                await self.protocol.send_heartbeat(status, task)
                await asyncio.sleep(30)
            except Exception as e:
                log.error(f"Heartbeat Fehler: {e}")
                await asyncio.sleep(60)
    
    async def main_loop(self):
        """Haupt Loop für Issue-Überwachung und -Behebung"""
        while self.is_running:
            try:
                # 1. Hole offene Issues
                open_issues = self.get_open_issues()
                
                if open_issues:
                    log.info(f"📋 {len(open_issues)} offene Issues gefunden")
                    
                    # 2. Priorisiere Issues
                    prioritized_issues = self.prioritize_issues(open_issues)
                    
                    # 3. Bearbeite Issues
                    for issue in prioritized_issues:
                        if not self.is_running:
                            break
                        
                        await self.process_issue(issue)
                
                # Warte vor nächster Runde
                await asyncio.sleep(60)  # Alle 60 Sekunden prüfen
                
            except Exception as e:
                log.error(f"Fehler im Main Loop: {e}")
                await asyncio.sleep(120)
    
    def get_open_issues(self) -> List:
        """Hole offene Issues aus dem Collaboration Hub"""
        try:
            return hub.issue_tracker.get_open_issues()
        except Exception as e:
            log.error(f"Fehler beim Holen der Issues: {e}")
            return []
    
    def prioritize_issues(self, issues: List) -> List:
        """Priorisiere Issues basierend auf Severity und Alter"""
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        
        def sort_key(issue):
            severity_score = severity_order.get(issue.severity, 4)
            age_hours = (datetime.now() - issue.created_at).total_seconds() / 3600
            return (severity_score, -age_hours)  # Höhere Priorität für kritische und alte Issues
        
        return sorted(issues, key=sort_key)
    
    async def process_issue(self, issue):
        """Verarbeite ein einzelnes Issue"""
        log.info(f"🔧 Bearbeite Issue: {issue.id} - {issue.title}")
        
        try:
            # 1. Analysiere Issue
            analysis = self.issue_analyzer.analyze_issue(
                issue.title, 
                issue.description,
                []
            )
            
            log.info(f"📊 Analyse: {analysis['recommended_action']}")
            
            # 2. Prüfe ob Auto-Fix verfügbar
            if analysis.get("auto_fix_available"):
                log.info(f"🤖 Auto-Fix verfügbar: {analysis['auto_fix_available']}")
                
                # 3. Wende Auto-Fix an
                fix_result = await self.apply_auto_fix(issue, analysis)
                
                if fix_result.get("success"):
                    # 4. Issue als gelöst markieren
                    await self.resolve_issue(issue, fix_result)
                else:
                    # 5. Frage um Hilfe von anderen Agenten
                    await self.request_agent_help(issue, analysis)
            else:
                # Kein Auto-Fix verfügbar - frage um Hilfe
                await self.request_agent_help(issue, analysis)
            
        except Exception as e:
            log.error(f"Fehler bei der Bearbeitung von Issue {issue.id}: {e}")
            await self.report_fix_failure(issue, str(e))
    
    async def apply_auto_fix(self, issue, analysis: Dict) -> Dict:
        """Wende automatischen Fix an"""
        try:
            pattern = analysis["detected_patterns"][0]["pattern"]
            auto_fix = analysis["auto_fix_available"]
            
            log.info(f"🔧 Wende Auto-Fix an: {pattern}")
            
            # Extrahiere Kontext aus Issue
            context = self._extract_context_from_issue(issue)
            
            # Wende Fix an
            fix_result = await self.autofixer.apply_auto_fix(
                issue.id,
                pattern,
                auto_fix,
                context
            )
            
            # Speichere in Historie
            self._record_fix_attempt(issue, pattern, fix_result)
            
            return fix_result
            
        except Exception as e:
            log.error(f"Auto-Fix Fehler: {e}")
            return {"success": False, "error": str(e)}
    
    def _extract_context_from_issue(self, issue) -> Dict:
        """Extrahiere Kontext aus Issue"""
        context = {
            "issue_id": issue.id,
            "title": issue.title,
            "description": issue.description,
            "severity": issue.severity,
            "tags": issue.tags
        }
        
        # Extrahiere spezifische Informationen aus Beschreibung
        desc = issue.description.lower()
        
        if "port" in desc:
            # Extrahiere Port-Nummer
            import re
            port_match = re.search(r'port\s*(\d+)', desc)
            if port_match:
                context["port"] = port_match.group(1)
        
        if "service" in desc:
            # Extrahiere Service-Name
            import re
            service_match = re.search(r'service\s*[:\s]*(\w+)', desc)
            if service_match:
                context["service"] = service_match.group(1)
        
        return context
    
    async def resolve_issue(self, issue, fix_result: Dict):
        """Markiere Issue als gelöst"""
        try:
            solution = f"Auto-fix erfolgreich: {fix_result.get('command', 'unknown')}"
            
            # Update Issue Tracker
            success = hub.issue_tracker.resolve_issue(issue.id, solution)
            
            if success:
                # Teile Lösung mit anderen Agenten
                await share_solution(self.name, issue.id, solution)
                
                # Belohne Agent
                hub.registry.record_success(self.name)
                
                log.info(f"✅ Issue {issue.id} gelöst")
                
                # Teile Erfolg via Communication
                if self.protocol:
                    await self.protocol.share_solution(
                        f"Issue gelöst: {issue.title}",
                        solution,
                        issue.id
                    )
        except Exception as e:
            log.error(f"Fehler beim Lösen von Issue {issue.id}: {e}")
    
    async def request_agent_help(self, issue, analysis: Dict):
        """Frage andere Agenten um Hilfe"""
        try:
            # Finde besten Agent für dieses Issue
            best_agent = self._find_best_agent_for_issue(issue, analysis)
            
            if best_agent:
                log.info(f"🆘 Frage {best_agent.name} um Hilfe für Issue {issue.id}")
                
                # Weise Issue zu
                hub.issue_tracker.assign_issue(issue.id, best_agent.name)
                
                # Sende Hilfe-Anfrage
                if self.protocol:
                    await self.protocol.request_help(
                        f"Issue {issue.id}: {issue.title}",
                        {
                            "issue_id": issue.id,
                            "analysis": analysis,
                            "description": issue.description
                        }
                    )
                
                # Update Issue Status
                issue.status = "in_progress"
                issue.agent_assigned = best_agent.name
                
            else:
                log.warning(f"⚠️ Kein passender Agent für Issue {issue.id}")
                
                # Erstelle Escalation Issue
                await report_issue(
                    f"Escalation: {issue.title}",
                    f"Kein passender Agent gefunden. Manual intervention required.\n\nOriginal: {issue.description}",
                    "high",
                    self.name,
                    ["escalation", "manual_intervention"]
                )
                
        except Exception as e:
            log.error(f"Fehler bei Hilfe-Anfrage: {e}")
    
    def _find_best_agent_for_issue(self, issue, analysis: Dict) -> Optional:
        """Finde besten Agent für Issue"""
        try:
            # Extrahiere Keywords aus Issue
            text = (issue.title + " " + issue.description).lower()
            
            # Mapping von Keywords zu Capabilities
            capability_mapping = {
                "trading": ["trading", "arbitrage", "market"],
                "system": ["system", "monitoring", "health"],
                "shopify": ["shopify", "products", "gmc"],
                "api": ["api", "endpoint", "request"],
                "browser": ["browser", "web", "automation"],
                "mac": ["mac", "screenshot", "control"],
                "ai": ["ai", "ollama", "chat", "learning"]
            }
            
            # Finde passende Capability
            matched_capability = None
            for capability, keywords in capability_mapping.items():
                if any(keyword in text for keyword in keywords):
                    matched_capability = capability
                    break
            
            if matched_capability:
                # Hole besten Agent für diese Capability
                return hub.registry.get_best_agent_for_task(matched_capability)
            
            # Fallback: Agent mit höchster Success Rate
            all_agents = list(hub.registry.agents.values())
            if all_agents:
                return max(all_agents, key=lambda a: a.success_count / (a.success_count + a.error_count + 1))
            
            return None
            
        except Exception as e:
            log.error(f"Fehler beim Finden des besten Agents: {e}")
            return None
    
    async def report_fix_failure(self, issue, error: str):
        """Reporte fehlgeschlagenen Fix"""
        try:
            # Erstelle Issue für den Fehler
            await report_issue(
                f"Fix fehlgeschlagen: {issue.title}",
                f"Konnte Issue {issue.id} nicht automatisch beheben.\n\nFehler: {error}",
                "medium",
                self.name,
                ["fix_failure", issue.id]
            )
            
            # Record in Historie
            self._record_fix_attempt(issue, "manual_intervention", {"success": False, "error": error})
            
        except Exception as e:
            log.error(f"Fehler beim Reporten des Fix-Fehlers: {e}")
    
    def _record_fix_attempt(self, issue, pattern: str, result: Dict):
        """Record Fix-Versuch in Historie"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "issue_id": issue.id,
            "issue_title": issue.title,
            "pattern": pattern,
            "success": result.get("success", False),
            "command": result.get("command"),
            "error": result.get("error")
        }
        
        self.fix_history.append(entry)
        
        # Begrenze Historie
        if len(self.fix_history) > 1000:
            self.fix_history = self.fix_history[-1000:]
        
        self._save_fix_history()
    
    async def get_fix_statistics(self) -> Dict:
        """Hole Fix-Statistiken"""
        total_attempts = len(self.fix_history)
        successful_fixes = sum(1 for entry in self.fix_history if entry.get("success"))
        
        # Pattern-basierte Statistiken
        pattern_stats = {}
        for entry in self.fix_history:
            pattern = entry.get("pattern", "unknown")
            if pattern not in pattern_stats:
                pattern_stats[pattern] = {"total": 0, "success": 0}
            pattern_stats[pattern]["total"] += 1
            if entry.get("success"):
                pattern_stats[pattern]["success"] += 1
        
        return {
            "total_attempts": total_attempts,
            "successful_fixes": successful_fixes,
            "success_rate": successful_fixes / total_attempts if total_attempts > 0 else 0,
            "pattern_stats": pattern_stats,
            "recent_fixes": self.fix_history[-10:] if self.fix_history else []
        }

# Global Instance
issue_fixer = IssueFixerAgent()

# Exportierte Funktionen
async def start_issue_fixer():
    """Starte Issue Fixer Agent"""
    return await issue_fixer.start()

async def stop_issue_fixer():
    """Stoppe Issue Fixer Agent"""
    return await issue_fixer.stop()

async def get_fixer_status() -> Dict:
    """Hole Status des Issue Fixer"""
    return {
        "name": issue_fixer.name,
        "running": issue_fixer.is_running,
        "capabilities": issue_fixer.capabilities,
        "open_issues": len(issue_fixer.get_open_issues()),
        "statistics": await issue_fixer.get_fix_statistics()
    }

if __name__ == "__main__":
    # Test
    async def test_issue_fixer():
        await start_issue_fixer()
        
        # Laufe für 5 Minuten zum Testen
        await asyncio.sleep(300)
        
        stats = await get_fixer_status()
        print("Issue Fixer Status:", json.dumps(stats, indent=2))
        
        await stop_issue_fixer()
        print("Test abgeschlossen")
    
    asyncio.run(test_issue_fixer())
