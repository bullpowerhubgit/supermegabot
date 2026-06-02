#!/usr/bin/env python3
"""
Debugging & Issue Fixing Tools für SuperMegaBot Agenten
Integriert mit dem Collaboration Framework und existing Self-Healing System
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import psutil
import aiohttp

# Import Collaboration Framework
from agent_collaboration_framework import hub, report_issue, request_help, share_solution

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(DATA_DIR / "debug_tools.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("DebugTools")

class SystemDiagnostics:
    """System-Diagnostik Tools"""
    
    @staticmethod
    def get_system_health() -> Dict[str, Any]:
        """Umfassende System-Health Check"""
        health = {
            "timestamp": datetime.now().isoformat(),
            "cpu": psutil.cpu_percent(interval=1),
            "memory": psutil.virtual_memory()._asdict(),
            "disk": psutil.disk_usage('/')._asdict(),
            "processes": len(list(psutil.process_iter())),
            "load_average": os.getloadavg() if hasattr(os, 'getloadavg') else None,
            "uptime": datetime.now().timestamp() - psutil.boot_time()
        }
        
        # Check kritische Services
        health["services"] = SystemDiagnostics._check_critical_services()
        
        # Overall Health Score (0-100)
        health["score"] = SystemDiagnostics._calculate_health_score(health)
        
        return health
    
    @staticmethod
    def _check_critical_services() -> Dict[str, bool]:
        """Check Status kritischer Services"""
        services = {
            "ollama": SystemDiagnostics._check_http_service("http://localhost:11434/api/tags"),
            "supermegabot": SystemDiagnostics._check_process("bot.py"),
            "telegram_bot": SystemDiagnostics._check_process("server.js"),
            "ngrok": SystemDiagnostics._check_http_service("http://localhost:4040/api/tunnels")
        }
        return services
    
    @staticmethod
    def _check_http_service(url: str, timeout: int = 5) -> bool:
        """Check HTTP Service"""
        try:
            import aiohttp
            async def check():
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                    async with session.get(url) as response:
                        return response.status < 500
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(check())
            loop.close()
            return result
        except Exception:
            return False
    
    @staticmethod
    def _check_process(name: str) -> bool:
        """Check ob Prozess läuft"""
        return any(name.lower() in (p.info.get('name', '') + ' '.join(p.info.get('cmdline', []))).lower()
                  for p in psutil.process_iter(['name', 'cmdline']))
    
    @staticmethod
    def _calculate_health_score(health: Dict) -> int:
        """Berechne overall Health Score"""
        score = 100
        
        # CPU Usage (0-30 Punkte)
        cpu_usage = health.get("cpu", 0)
        if cpu_usage > 80:
            score -= 30
        elif cpu_usage > 60:
            score -= 20
        elif cpu_usage > 40:
            score -= 10
        
        # Memory Usage (0-25 Punkte)
        mem_percent = health.get("memory", {}).get("percent", 0)
        if mem_percent > 90:
            score -= 25
        elif mem_percent > 80:
            score -= 15
        elif mem_percent > 70:
            score -= 5
        
        # Disk Usage (0-20 Punkte)
        disk_percent = health.get("disk", {}).get("percent", 0)
        if disk_percent > 95:
            score -= 20
        elif disk_percent > 90:
            score -= 10
        elif disk_percent > 80:
            score -= 5
        
        # Services (0-25 Punkte)
        services = health.get("services", {})
        failed_services = sum(1 for status in services.values() if not status)
        score -= failed_services * 5
        
        return max(0, min(100, score))

class IssueAnalyzer:
    """Analyziert Issues und schlägt Lösungen vor"""
    
    def __init__(self):
        self.patterns_file = DATA_DIR / "issue_patterns.json"
        self.patterns = self._load_patterns()
    
    def _load_patterns(self) -> Dict:
        """Lade bekannte Issue-Patterns"""
        default_patterns = {
            "port_conflict": {
                "keywords": ["port", "bind", "address already in use", "eaddrinuse"],
                "detection": "log_analysis",
                "solution": "Finde und beende Prozess auf dem Port",
                "auto_fix": "lsof -ti:{port} | xargs kill -9"
            },
            "memory_leak": {
                "keywords": ["memory", "out of memory", "oom", "cannot allocate"],
                "detection": "system_monitoring",
                "solution": "Neustart des betroffenen Service",
                "auto_fix": "systemctl restart {service} || kill -9 {pid}"
            },
            "connection_failed": {
                "keywords": ["connection", "refused", "timeout", "unreachable"],
                "detection": "network_check",
                "solution": "Prüfe Netzwerkverbindung und Service Status",
                "auto_fix": "curl -I {url} || systemctl restart network"
            },
            "permission_denied": {
                "keywords": ["permission", "denied", "access", "forbidden"],
                "detection": "file_check",
                "solution": "Prüfe und korrigiere Berechtigungen",
                "auto_fix": "chmod {permissions} {file} || chown {user}:{group} {file}"
            },
            "module_missing": {
                "keywords": ["module", "import", "cannot find", "no module"],
                "detection": "dependency_check",
                "solution": "Installiere fehlende Abhängigkeiten",
                "auto_fix": "pip install {module} || npm install {package}"
            }
        }
        
        try:
            if self.patterns_file.exists():
                return json.loads(self.patterns_file.read_text())
        except Exception:
            pass
        
        return default_patterns
    
    def analyze_issue(self, title: str, description: str, logs: List[str] = None) -> Dict[str, Any]:
        """Analysiere Issue und erkenne Pattern"""
        text = (title + " " + description + " " + " ".join(logs or [])).lower()
        
        detected_patterns = []
        for pattern_name, pattern_data in self.patterns.items():
            keyword_matches = sum(1 for keyword in pattern_data["keywords"] if keyword in text)
            if keyword_matches > 0:
                detected_patterns.append({
                    "pattern": pattern_name,
                    "confidence": keyword_matches / len(pattern_data["keywords"]),
                    "matches": keyword_matches,
                    "solution": pattern_data["solution"],
                    "auto_fix": pattern_data.get("auto_fix")
                })
        
        # Sortiere nach Confidence
        detected_patterns.sort(key=lambda x: x["confidence"], reverse=True)
        
        return {
            "detected_patterns": detected_patterns,
            "recommended_action": detected_patterns[0]["solution"] if detected_patterns else "Manual investigation required",
            "auto_fix_available": detected_patterns[0]["auto_fix"] if detected_patterns else None,
            "severity": self._estimate_severity(text, detected_patterns)
        }
    
    def _estimate_severity(self, text: str, patterns: List[Dict]) -> str:
        """Schätze Severity des Issues"""
        critical_keywords = ["critical", "crash", "fatal", "emergency", "down", "failed"]
        high_keywords = ["error", "warning", "timeout", "refused"]
        
        if any(keyword in text for keyword in critical_keywords):
            return "critical"
        elif any(keyword in text for keyword in high_keywords) or any(p["confidence"] > 0.7 for p in patterns):
            return "high"
        elif patterns:
            return "medium"
        else:
            return "low"

class AutoFixer:
    """Automatische Issue-Behebung"""
    
    def __init__(self):
        self.fix_history_file = DATA_DIR / "fix_history.json"
        self.fix_history = self._load_fix_history()
    
    def _load_fix_history(self) -> List[Dict]:
        """Lade Fix-Historie"""
        try:
            if self.fix_history_file.exists():
                return json.loads(self.fix_history_file.read_text())
        except Exception:
            pass
        return []
    
    def _save_fix_history(self):
        """Speichere Fix-Historie"""
        try:
            self.fix_history_file.write_text(json.dumps(self.fix_history, indent=2))
        except Exception as e:
            log.error(f"Fehler beim Speichern der Fix-Historie: {e}")
    
    async def apply_auto_fix(self, issue_id: str, pattern: str, auto_fix: str, context: Dict = None) -> Dict[str, Any]:
        """Wende automatischen Fix an"""
        log.info(f"Versuche Auto-Fix für Issue {issue_id}: {pattern}")
        
        # Ersetze Platzhalter im Fix-Command
        fix_command = self._substitute_placeholders(auto_fix, context or {})
        
        result = {
            "issue_id": issue_id,
            "pattern": pattern,
            "command": fix_command,
            "success": False,
            "output": "",
            "error": "",
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # Führe Fix aus
            process = await asyncio.create_subprocess_shell(
                fix_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=30
            )
            
            stdout, stderr = await process.communicate()
            result["output"] = stdout.decode('utf-8', errors='ignore')
            result["error"] = stderr.decode('utf-8', errors='ignore')
            result["success"] = process.returncode == 0
            
            if result["success"]:
                log.info(f"✅ Auto-Fix erfolgreich: {pattern}")
                await share_solution("auto_fixer", issue_id, f"Automatisch behoben: {fix_command}")
            else:
                log.warning(f"❌ Auto-Fix fehlgeschlagen: {pattern} - {result['error']}")
            
        except asyncio.TimeoutError:
            result["error"] = "Command timeout"
            log.error(f"Auto-Fix timeout: {fix_command}")
        except Exception as e:
            result["error"] = str(e)
            log.error(f"Auto-Fix Exception: {e}")
        
        # Speichere in Historie
        self.fix_history.append(result)
        self._save_fix_history()
        
        return result
    
    def _substitute_placeholders(self, command: str, context: Dict) -> str:
        """Ersetze Platzhalter im Fix-Command"""
        substitutions = {
            "{port}": context.get("port", "3000"),
            "{service}": context.get("service", "supermegabot"),
            "{pid}": context.get("pid", ""),
            "{file}": context.get("file", ""),
            "{permissions}": context.get("permissions", "755"),
            "{user}": context.get("user", "rudolfsarkany"),
            "{group}": context.get("group", "staff"),
            "{module}": context.get("module", ""),
            "{package}": context.get("package", ""),
            "{url}": context.get("url", "http://localhost:3000")
        }
        
        result = command
        for placeholder, value in substitutions.items():
            result = result.replace(placeholder, str(value))
        
        return result

class CollaborationDebugger:
    """Integrierter Debugger für Agenten-Kollaboration"""
    
    def __init__(self):
        self.diagnostics = SystemDiagnostics()
        self.analyzer = IssueAnalyzer()
        self.autofixer = AutoFixer()
    
    async def diagnose_and_fix(self, agent_name: str, problem: str, context: Dict = None) -> Dict[str, Any]:
        """Vollständige Diagnose und Fix-Versuch"""
        log.info(f"Starte Diagnose für Agent {agent_name}: {problem}")
        
        # 1. System-Health Check
        system_health = self.diagnostics.get_system_health()
        
        # 2. Issue-Analyse
        analysis = self.analyzer.analyze_issue(problem, problem, [context.get("logs", "")] if context else [])
        
        # 3. Erstelle Issue im Collaboration Hub
        issue_id = await report_issue(
            f"Problem bei {agent_name}: {problem}",
            f"System Health: {system_health['score']}%\n\nAnalyse: {analysis['recommended_action']}",
            severity=analysis["severity"],
            reporter="debugger",
            tags=["auto_diagnosed", agent_name]
        )
        
        result = {
            "issue_id": issue_id,
            "agent": agent_name,
            "problem": problem,
            "system_health": system_health,
            "analysis": analysis,
            "fix_applied": None
        }
        
        # 4. Auto-Fix versuchen
        if analysis["auto_fix_available"]:
            fix_result = await self.autofixer.apply_auto_fix(
                issue_id, 
                analysis["detected_patterns"][0]["pattern"],
                analysis["auto_fix_available"],
                context
            )
            result["fix_applied"] = fix_result
            
            if fix_result["success"]:
                await share_solution("collaboration_debugger", issue_id, f"Auto-fix erfolgreich: {fix_result['command']}")
        
        # 5. Falls Auto-Fix fehlschlägt, frage um Hilfe
        if not result.get("fix_applied", {}).get("success"):
            help_request = await request_help(
                "collaboration_debugger",
                f"Benötige Hilfe bei: {agent_name} - {problem}",
                {"issue_id": issue_id, "analysis": analysis}
            )
            result["help_requested"] = help_request
        
        log.info(f"Diagnose abgeschlossen für {agent_name}: {issue_id}")
        return result
    
    async def get_agent_debug_report(self, agent_name: str) -> Dict[str, Any]:
        """Erstelle detaillierten Debug-Report für einen Agent"""
        # System Status
        system_health = self.diagnostics.get_system_health()
        
        # Agent-spezifische Probleme
        agent_issues = [issue for issue in hub.issue_tracker.get_open_issues() 
                       if agent_name in issue.tags or agent_name in issue.title]
        
        # Fix-Historie für diesen Agent
        agent_fixes = [fix for fix in self.autofixer.fix_history 
                      if agent_name in str(fix.get("context", {}))]
        
        return {
            "agent": agent_name,
            "timestamp": datetime.now().isoformat(),
            "system_health": system_health,
            "open_issues": len(agent_issues),
            "issues": [
                {
                    "id": issue.id,
                    "title": issue.title,
                    "severity": issue.severity,
                    "status": issue.status,
                    "created": issue.created_at.isoformat()
                }
                for issue in agent_issues[:5]  # Letzte 5 Issues
            ],
            "fix_history": len(agent_fixes),
            "recent_fixes": agent_fixes[-5:],  # Letzte 5 Fixes
            "recommendations": self._generate_recommendations(agent_name, system_health, agent_issues)
        }
    
    def _generate_recommendations(self, agent_name: str, system_health: Dict, issues: List) -> List[str]:
        """Generiere Empfehlungen für den Agent"""
        recommendations = []
        
        # System-basierte Empfehlungen
        if system_health["score"] < 70:
            recommendations.append("System-Health ist niedrig - prüfe CPU/RAM/Disk Nutzung")
        
        if system_health["cpu"] > 80:
            recommendations.append("Hohe CPU-Auslastung - prüfe auf Endlosschleifen")
        
        if system_health["memory"]["percent"] > 85:
            recommendations.append("Hohe Memory-Nutzung - prüfe auf Memory Leaks")
        
        # Issue-basierte Empfehlungen
        critical_issues = [i for i in issues if i.severity == "critical"]
        if critical_issues:
            recommendations.append(f"{len(critical_issues)} kritische Issues benötigen sofortige Aufmerksamkeit")
        
        # Service-spezifische Empfehlungen
        failed_services = [service for service, status in system_health["services"].items() if not status]
        if failed_services:
            recommendations.append(f"Services nicht verfügbar: {', '.join(failed_services)}")
        
        return recommendations

# Global Instance
debugger = CollaborationDebugger()

# Exportierte Funktionen für andere Module
async def diagnose_and_fix_agent(agent_name: str, problem: str, context: Dict = None) -> Dict[str, Any]:
    """Diagnose und fixe Probleme eines Agenten"""
    return await debugger.diagnose_and_fix(agent_name, problem, context)

async def get_agent_debug_report(agent_name: str) -> Dict[str, Any]:
    """Hole Debug-Report für einen Agenten"""
    return await debugger.get_agent_debug_report(agent_name)

def get_system_health() -> Dict[str, Any]:
    """Hole System-Health Status"""
    return SystemDiagnostics.get_system_health()

if __name__ == "__main__":
    # Test
    async def test_debug():
        # System Health Check
        health = get_system_health()
        print("System Health:", json.dumps(health, indent=2, default=str))
        
        # Simuliere Problem
        result = await diagnose_and_fix_agent(
            "test_agent",
            "Service reagiert nicht auf Port 3000",
            {"port": "3000", "logs": "EADDRINUSE: address already in use"}
        )
        print("Diagnose Result:", json.dumps(result, indent=2, default=str))
    
    asyncio.run(test_debug())
