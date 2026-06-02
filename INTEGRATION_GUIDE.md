# Agent Collaboration Framework - Integration Guide

## Überblick

Dieses Framework ermöglicht es verschiedenen SuperMegaBot Agenten, zusammenzuarbeiten, Probleme zu lösen und sich gegenseitig zu helfen. Es besteht aus drei Hauptkomponenten:

1. **Collaboration Framework** (`agent_collaboration_framework.py`) - Zentrale Registry und Issue Tracking
2. **Debug Tools** (`debug_tools.py`) - Automatische Diagnose und Fehlerbehebung  
3. **Communication Protocols** (`agent_communication.py`) - Nachrichten-System zwischen Agenten

## Schnellstart für Agent-Entwickler

### 1. Agent registrieren

```python
from agent_communication import start_agent_communication
from debug_tools import diagnose_and_fix_agent

# Registriere deinen Agent mit seinen Fähigkeiten
protocol = await start_agent_communication(
    "mein_agent", 
    ["trading", "analysis", "automation"]
)
```

### 2. Kommunikation implementieren

```python
# Sende Heartbeat (regelmäßig aufrufen)
await protocol.send_heartbeat("running", "analysiere marktdaten")

# Frage um Hilfe bei Problemen
await protocol.request_help(
    "Trading API nicht erreichbar",
    {"endpoint": "https://api.binance.com", "error": "timeout"}
)

# Teile Lösungen mit anderen
await protocol.share_solution(
    "API Timeout Problem",
    "Timeout von 5s auf 30s erhöht, connection pooling aktiviert"
)

# Reporte Fehler automatisch
await protocol.report_error(
    "Datenbank-Verbindung fehlgeschlagen",
    {"database": "trading_db", "query": "SELECT * FROM trades"}
)
```

### 3. Auto-Diagnose nutzen

```python
# Bei Fehlern automatisch diagnostizieren lassen
try:
    # Dein Code hier
    result = await trading_api.get_prices()
except Exception as e:
    diagnosis = await diagnose_and_fix_agent(
        "mein_agent",
        str(e),
        {"error_type": type(e).__name__, "context": "price_fetch"}
    )
    print(f"Diagnose: {diagnosis}")
```

## Integration mit bestehenden SuperMegaBot Modulen

### Mega Orchestrator Integration

Füge diese Befehle zum `CommandRouter` in `mega_orchestrator.py` hinzu:

```python
# In der _register_routes Methode:
self.routes.update({
    "/agent_status": self._cmd_agent_status,
    "/agent_help": self._cmd_agent_help,
    "/agent_debug": self._cmd_agent_debug,
    "/collab_stats": self._cmd_collab_stats,
})

async def _cmd_agent_status(self, text, session_id) -> str:
    """Status aller Agenten anzeigen"""
    from agent_collaboration_framework import get_dashboard_status
    status = get_dashboard_status()
    return json.dumps(status, indent=2, ensure_ascii=False)

async def _cmd_agent_help(self, text, session_id) -> str:
    """Hilfe für Agenten anfordern"""
    problem = text.replace("/agent_help", "").strip()
    if not problem:
        return "Usage: /agent_help <problem beschreibung>"
    
    from agent_communication import comm_manager
    # Sende Hilfe-Anfrage an alle Agenten
    for protocol in comm_manager.protocols.values():
        await protocol.request_help(problem)
    
    return f"Hilfe-Anfrage gesendet: {problem}"

async def _cmd_agent_debug(self, text, session_id) -> str:
    """Debug-Report für spezifischen Agent"""
    agent = text.replace("/agent_debug", "").strip()
    if not agent:
        return "Usage: /agent_debug <agent_name>"
    
    from debug_tools import get_agent_debug_report
    report = await get_agent_debug_report(agent)
    return json.dumps(report, indent=2, ensure_ascii=False)

async def _cmd_collab_stats(self, text, session_id) -> str:
    """Kollaborations-Statistiken"""
    from agent_communication import get_communication_stats
    stats = await get_communication_stats()
    return json.dumps(stats, indent=2, ensure_ascii=False)
```

### Self-Healing Integration

Erweitere den `SelfHealingEngine` in `self_healer.py`:

```python
# Am Anfang der Datei importieren:
from agent_collaboration_framework import report_issue, share_solution
from agent_communication import comm_manager

# In der heal_service Methode hinzufügen:
async def heal_service(self, svc_name: str, svc: Dict) -> bool:
    log.warning(f"⚠️  {svc_name} ausgefallen — starte Reparatur...")
    
    # Reporte Issue an Collaboration Hub
    issue_id = await report_issue(
        f"Service {svc_name} ausgefallen",
        f"Service {svc_name} reagiert nicht. Restart-Command: {svc['restart_cmd']}",
        "high",
        "self_healer",
        ["service_failure", svc_name]
    )
    
    try:
        subprocess.run(svc['restart_cmd'], shell=True, timeout=15)
        await asyncio.sleep(3)
        ok = await self.check_service(svc_name, svc)
        
        if ok:
            # Teile erfolgreiche Lösung
            await share_solution("self_healer", issue_id, f"Service erfolgreich restartet")
            log.info(f"✅ {svc_name} repariert")
        else:
            # Frage um Hilfe von anderen Agenten
            for protocol in comm_manager.protocols.values():
                await protocol.request_help(
                    f"Konnte {svc_name} nicht restarten",
                    {"service": svc_name, "command": svc['restart_cmd']}
                )
        
        return ok
    except Exception as e:
        await share_solution("self_healer", issue_id, f"Restart fehlgeschlagen: {e}")
        return False
```

## Best Practices

### 1. Regelmäßige Heartbeats

```python
# In deinem Agent regelmäßig aufrufen (alle 30-60 Sekunden)
async def heartbeat_loop():
    while True:
        await protocol.send_heartbeat(
            "running" if is_healthy else "error",
            current_task
        )
        await asyncio.sleep(30)
```

### 2. Strukturierte Fehlerbehandlung

```python
class MyAgent:
    async def safe_execute(self, operation: str, context: Dict = None):
        try:
            # Operation ausführen
            result = await self._execute_operation(operation)
            
            # Erfolg recorden
            hub.registry.record_success(self.name)
            return result
            
        except Exception as e:
            # Fehler reporten
            await protocol.report_error(
                f"Fehler bei {operation}",
                {"error": str(e), "context": context or {}}
            )
            
            # Auto-Diagnose anfordern
            diagnosis = await diagnose_and_fix_agent(
                self.name,
                f"{operation}: {str(e)}",
                context
            )
            
            # Entweder Lösung anwenden oder weiter propagieren
            if diagnosis.get("fix_applied", {}).get("success"):
                # Retry mit Fix
                return await self._execute_operation(operation)
            else:
                raise e
```

### 3. Fähigkeiten deklarieren

Registriere deinen Agent mit präzisen Fähigkeiten:

```python
CAPABILITIES = {
    "trading_bot": ["trading", "arbitrage", "market_analysis"],
    "system_monitor": ["system", "monitoring", "health_check"],
    "api_manager": ["api", "endpoint_management", "testing"],
    "debugger": ["debugging", "error_analysis", "auto_fix"],
    "shopify_agent": ["shopify", "products", "gmc", "ads"]
}
```

### 4. Lösungen teilen

Wenn dein Agent ein Problem löst, teile die Lösung:

```python
async def solve_problem(self, problem_id: str, solution: str):
    # Teile mit Collaboration Hub
    await share_solution(self.name, problem_id, solution)
    
    # Teile mit anderen Agenten via Communication
    await protocol.share_solution(
        f"{problem_id}: {solution[:50]}",
        solution,
        problem_id
    )
    
    # Record Erfolg
    hub.registry.record_success(self.name)
```

## Monitoring und Dashboard

### System Health Dashboard

```python
# Erstelle einfaches Dashboard
async def show_dashboard():
    from agent_collaboration_framework import get_dashboard_status
    from agent_communication import get_communication_stats
    from debug_tools import get_system_health
    
    dashboard = {
        "timestamp": datetime.now().isoformat(),
        "system_health": get_system_health(),
        "agents": get_dashboard_status(),
        "communication": await get_communication_stats()
    }
    
    print(json.dumps(dashboard, indent=2, ensure_ascii=False))
```

### Troubleshooting

1. **Agent antwortet nicht**: Prüfe Heartbeat in `get_dashboard_status()`
2. **Nachrichten nicht zugestellt**: Überprüfe `get_communication_stats()`
3. **Issues bleiben ungelöst**: Prüfe `get_agent_debug_report()` für betroffenen Agent
4. **System instabil**: Prüfe `get_system_health()` Score

## Beispiel: Trading Bot Integration

```python
class TradingBotAgent:
    def __init__(self):
        self.name = "trading_bot"
        self.protocol = None
        self.capabilities = ["trading", "arbitrage", "price_analysis"]
    
    async def start(self):
        # Registriere Agent
        self.protocol = await start_agent_communication(self.name, self.capabilities)
        
        # Starte Heartbeat
        asyncio.create_task(self.heartbeat_loop())
        
        # Starte Trading Loop
        asyncio.create_task(self.trading_loop())
    
    async def heartbeat_loop(self):
        while True:
            status = "running" if self.is_healthy() else "error"
            task = f"analyzing {len(self.active_pairs)} pairs"
            await self.protocol.send_heartbeat(status, task)
            await asyncio.sleep(30)
    
    async def trading_loop(self):
        while True:
            try:
                # Trading Logic
                opportunities = await self.scan_opportunities()
                
                if not opportunities:
                    # Frage andere Agenten nach Hilfe
                    await self.protocol.request_help(
                        "Keine Trading-Opportunities gefunden",
                        {"strategy": "arbitrage", "markets": self.active_markets}
                    )
                
                # Execute trades
                for opp in opportunities:
                    await self.execute_trade(opp)
                    
            except Exception as e:
                # Auto-Diagnose
                diagnosis = await diagnose_and_fix_agent(
                    self.name,
                    f"Trading Loop Fehler: {str(e)}",
                    {"error_type": type(e).__name__, "opportunities": len(opportunities) if 'opportunities' in locals() else 0}
                )
                
                if not diagnosis.get("fix_applied", {}).get("success"):
                    await self.protocol.report_error(
                        f"Trading Loop fehlgeschlagen: {str(e)}",
                        {"diagnosis": diagnosis}
                    )
            
            await asyncio.sleep(60)
    
    async def execute_trade(self, opportunity):
        try:
            # Trade ausführen
            result = await self._perform_trade(opportunity)
            
            # Erfolg teilen
            await self.protocol.share_solution(
                f"Trade ausgeführt: {opportunity['pair']}",
                f"Profit: {opportunity['expected_profit']}%",
                f"trade_{opportunity['id']}"
            )
            
        except Exception as e:
            await self.protocol.report_error(
                f"Trade fehlgeschlagen: {opportunity['pair']}",
                {"error": str(e), "opportunity": opportunity}
            )
```

## Fehlerbehebung

### Häufige Probleme

1. **Import Error**: Stelle sicher dass alle Module im selben Verzeichnis sind
2. **AsyncIO Context**: Nutze `asyncio.run()` für Test-Code
3. **Permission Issues**: Prüfe Dateirechte für `data/` Verzeichnis
4. **Port Conflicts**: Ändere Ports in Konfiguration

### Debug Mode

Aktiviere Debug Logging:

```python
import logging
logging.getLogger("AgentCollaboration").setLevel(logging.DEBUG)
logging.getLogger("DebugTools").setLevel(logging.DEBUG)
logging.getLogger("AgentCommunication").setLevel(logging.DEBUG)
```

## API Referenz

### Collaboration Framework

- `register_agent(name, capabilities)` - Agent registrieren
- `report_issue(title, description, severity)` - Issue erstellen
- `request_help(agent_name, problem)` - Um Hilfe bitten
- `share_solution(agent_name, issue_id, solution)` - Lösung teilen
- `get_dashboard_status()` - Dashboard Status

### Debug Tools

- `diagnose_and_fix_agent(agent_name, problem)` - Auto-Diagnose
- `get_agent_debug_report(agent_name)` - Debug Report
- `get_system_health()` - System Health

### Communication

- `start_agent_communication(name, capabilities)` - Kommunikation starten
- `protocol.send_message(recipient, type, subject, content)` - Nachricht senden
- `protocol.request_help(problem)` - Hilfe anfordern
- `protocol.share_solution(problem, solution)` - Lösung teilen
- `protocol.report_error(error)` - Fehler reporten

---

## Nächste Schritte

1. **Teste die Integration**: Nutze die Test-Code in den einzelnen Modulen
2. **Implementiere in deinen Agenten**: Füge die Kommunikation zu bestehenden Agenten hinzu
3. **Monitor das System**: Nutze die Dashboard-Funktionen zur Überwachung
4. **Erweitere die Fähigkeiten**: Füge neue Capabilities und Handler hinzu

Bei Fragen oder Problemen nutze die eingebaute Hilfe:

```python
from agent_collaboration_framework import hub
help_issue = await hub.report_issue(
    "Integration Frage",
    "Wie integriere ich X mit Y?",
    "low",
    "developer"
)
```
