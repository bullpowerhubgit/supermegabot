#!/usr/bin/env python3
"""
Start Script für das komplette Agent Collaboration System
Startet alle Komponenten und registriert die Agenten
"""

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.mega_orchestrator import MegaOrchestrator
from modules.trading_bot_collab import start_trading_agent, stop_trading_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "data" / "collaboration_system.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("CollaborationSystem")

class CollaborationSystemManager:
    """Manager für das komplette Collaboration System"""
    
    def __init__(self):
        self.orchestrator = None
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        log.info(f"Signal {signum} empfangen - starte Shutdown...")
        self.shutdown_event.set()
    
    async def start(self):
        """Starte das komplette System"""
        log.info("🚀 Starte SuperMegaBot Collaboration System...")
        
        try:
            # 1. Starte Mega Orchestrator
            self.orchestrator = MegaOrchestrator()
            
            # 2. Starte Trading Bot Agent
            await start_trading_agent()
            
            # 3. Starte Orchestrator
            await self.orchestrator.start()
            
            self.is_running = True
            log.info("✅ SuperMegaBot Collaboration System läuft")
            
            # Zeile System-Status
            await self.show_system_status()
            
            # Warte auf Shutdown
            await self.shutdown_event.wait()
            
        except Exception as e:
            log.error(f"❌ Start fehlgeschlagen: {e}")
            raise
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Fahre das System herunter"""
        if not self.is_running:
            return
        
        log.info("🛑 Fahre SuperMegaBot Collaboration System herunter...")
        
        try:
            # Stoppe Trading Bot Agent
            await stop_trading_agent()
            
            # Orchestrator wird automatisch durch Event gestoppt
            if self.orchestrator:
                self.orchestrator.running = False
            
            self.is_running = False
            log.info("✅ System heruntergefahren")
            
        except Exception as e:
            log.error(f"❌ Shutdown Fehler: {e}")
    
    async def show_system_status(self):
        """Zeige System-Status"""
        try:
            # Import Collaboration Framework
            from agent_collaboration_framework import get_dashboard_status
            from agent_communication import get_communication_stats
            from debug_tools import get_system_health
            
            print("\n" + "="*60)
            print("🤖 SUPERMEGABOT COLLABORATION SYSTEM STATUS")
            print("="*60)
            
            # System Health
            health = get_system_health()
            print(f"\n💚 System Health Score: {health.get('score', 0)}/100")
            print(f"   CPU: {health.get('cpu', 0)}%")
            print(f"   Memory: {health.get('memory', {}).get('percent', 0)}%")
            print(f"   Disk: {health.get('disk', {}).get('percent', 0)}%")
            
            # Agent Status
            dashboard = get_dashboard_status()
            agents = dashboard.get('agents', {})
            print(f"\n🤖 Aktive Agenten: {len(agents)}")
            for name, info in agents.items():
                status_emoji = "✅" if info.get('status') == 'running' else "❌"
                success_rate = info.get('success_rate', 0)
                print(f"   {status_emoji} {name}: {info.get('status', '?')} (Success Rate: {success_rate:.1%})")
            
            # Issues
            issues = dashboard.get('issues', {})
            print(f"\n📋 Offene Issues: {issues.get('open', 0)}")
            if issues.get('critical', 0) > 0:
                print(f"   ⚠️  Kritische Issues: {issues.get('critical', 0)}")
            
            # Communication Stats
            comm_stats = await get_communication_stats()
            total_messages = comm_stats.get('total_messages', 0)
            active_protocols = comm_stats.get('active_protocols', 0)
            print(f"\n📡 Kommunikation: {total_messages} Nachrichten, {active_protocols} aktive Protokolle")
            
            print("\n" + "="*60)
            print("System bereit für Agenten-Kollaboration!")
            print("Verfügbare Befehle:")
            print("  /agent_status     - Status aller Agenten")
            print("  /agent_help <p>  - Hilfe anfordern")
            print("  /agent_debug <a> - Debug Report für Agent")
            print("  /system_health    - System Health Check")
            print("  /collab_stats     - Kollaborations-Statistiken")
            print("  /agent_dashboard  - Vollständiges Dashboard")
            print("="*60)
            
        except Exception as e:
            log.error(f"Fehler bei Status-Anzeige: {e}")

async def main():
    """Main Funktion"""
    manager = CollaborationSystemManager()
    
    try:
        await manager.start()
    except KeyboardInterrupt:
        log.info("Keyboard Interrupt empfangen")
    except Exception as e:
        log.error(f"Unerwarteter Fehler: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Stelle sicher dass data Verzeichnis existiert
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)
    
    # Starte das System
    asyncio.run(main())
