#!/usr/bin/env python3
"""
Trading Bot mit Collaboration Framework Integration
Erweitert den bestehenden Trading Bot um Agenten-Kollaboration
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

# Import Collaboration Framework
try:
    from agent_communication import start_agent_communication
    from agent_collaboration_framework import share_solution
    from debug_tools import diagnose_and_fix_agent
    COLLABORATION_AVAILABLE = True
except ImportError:
    COLLABORATION_AVAILABLE = False

# Import bestehenden Trading Bot
try:
    from modules.trading_bot import TradingBot
    TRADING_BOT_AVAILABLE = True
except ImportError:
    TRADING_BOT_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("TradingBotCollab")

class TradingBotAgent:
    """Trading Bot mit Agenten-Kollaboration"""
    
    def __init__(self):
        self.name = "trading_bot"
        self.protocol = None
        self.capabilities = ["trading", "arbitrage", "price_analysis", "market_monitoring"]
        self.base_bot = None
        self.is_running = False
        
        if TRADING_BOT_AVAILABLE:
            self.base_bot = TradingBot()
    
    async def start(self):
        """Starte den Trading Bot Agent"""
        if not COLLABORATION_AVAILABLE:
            log.warning("Collaboration Framework nicht verfügbar")
            return
        
        try:
            # Registriere Agenten
            self.protocol = await start_agent_communication(self.name, self.capabilities)
            
            # Starte Heartbeat
            asyncio.create_task(self.heartbeat_loop())
            
            # Starte Trading Loop
            asyncio.create_task(self.trading_loop())
            
            self.is_running = True
            log.info(f"✅ {self.name} Agent gestartet")
            
        except Exception as e:
            log.error(f"❌ Start von {self.name} fehlgeschlagen: {e}")
    
    async def stop(self):
        """Stoppe den Trading Bot Agent"""
        self.is_running = False
        if self.protocol:
            # Sende letzten Status
            await self.protocol.send_heartbeat("stopped", "agent stopped")
        log.info(f"{self.name} Agent gestoppt")
    
    async def heartbeat_loop(self):
        """Sende regelmäßige Heartbeats"""
        while self.is_running:
            try:
                status = "running" if self.is_healthy() else "error"
                task = f"monitoring {len(self.get_active_pairs())} pairs"
                await self.protocol.send_heartbeat(status, task)
                await asyncio.sleep(30)
            except Exception as e:
                log.error(f"Heartbeat Fehler: {e}")
                await asyncio.sleep(60)
    
    async def trading_loop(self):
        """Haupt Trading Loop mit Kollaboration"""
        while self.is_running:
            try:
                # Trading Logic
                opportunities = await self.scan_opportunities()
                
                if not opportunities:
                    # Frage andere Agenten um Hilfe
                    await self.request_market_help()
                else:
                    # Führe Trades aus
                    results = await self.execute_trades(opportunities)
                    
                    # Teile Erfolge
                    for result in results:
                        if result.get("success"):
                            await self.share_trading_success(result)
                
                await asyncio.sleep(60)  # Alle 60 Sekunden prüfen
                
            except Exception as e:
                await self.handle_trading_error(e)
                await asyncio.sleep(120)  # Bei Fehler länger warten
    
    async def scan_opportunities(self) -> List[Dict]:
        """Scanne nach Trading-Opportunities"""
        if not self.base_bot:
            return []
        
        try:
            opportunities = await self.base_bot.scan_quick()
            log.info(f"🔍 {len(opportunities)} Opportunities gefunden")
            return opportunities
        except Exception as e:
            log.error(f"Opportunity Scan Fehler: {e}")
            return []
    
    async def execute_trades(self, opportunities: List[Dict]) -> List[Dict]:
        """Führe Trades aus mit Fehlerbehandlung"""
        results = []
        
        for opp in opportunities[:5]:  # Max 5 Trades
            try:
                result = await self.execute_single_trade(opp)
                results.append(result)
            except Exception as e:
                results.append({
                    "opportunity": opp,
                    "success": False,
                    "error": str(e)
                })
        
        return results
    
    async def execute_single_trade(self, opportunity: Dict) -> Dict:
        """Führe einzelnen Trade aus"""
        try:
            # Hier würde die eigentliche Trading-Logik stehen
            # Für Demo simulieren wir einen Trade
            
            profit_pct = opportunity.get('profit_pct', 0)
            success = profit_pct > 0.5  # Simuliere Erfolg bei >0.5% Profit
            
            return {
                "opportunity": opportunity,
                "success": success,
                "profit_pct": profit_pct,
                "timestamp": datetime.now().isoformat(),
                "details": f"Trade {opportunity.get('pair', 'unknown')}: {'Erfolg' if success else 'Fehlschlag'}"
            }
        except Exception as e:
            return {
                "opportunity": opportunity,
                "success": False,
                "error": str(e)
            }
    
    async def request_market_help(self):
        """Frage um Hilfe bei fehlenden Opportunities"""
        if not self.protocol:
            return
        
        try:
            await self.protocol.request_help(
                "Keine Trading-Opportunities gefunden",
                {
                    "strategy": "arbitrage",
                    "markets": self.get_active_pairs(),
                    "scan_time": datetime.now().isoformat()
                }
            )
            log.info("🆘 Hilfe-Anfrage für Opportunities gesendet")
        except Exception as e:
            log.error(f"Hilfe-Anfrage Fehler: {e}")
    
    async def share_trading_success(self, result: Dict):
        """Teile erfolgreichen Trade mit anderen Agenten"""
        if not self.protocol or not result.get("success"):
            return
        
        try:
            opp = result["opportunity"]
            await self.protocol.share_solution(
                f"Trade ausgeführt: {opp.get('pair', 'unknown')}",
                f"Profit: {result.get('profit_pct', 0):.2f}% - {result.get('details', '')}",
                f"trade_{opp.get('pair', 'unknown').replace('/', '_')}_{int(datetime.now().timestamp())}"
            )
            log.info(f"✅ Trade-Erfolg geteilt: {opp.get('pair')}")
        except Exception as e:
            log.error(f"Trade-Erfolg Teilen Fehler: {e}")
    
    async def handle_trading_error(self, error: Exception):
        """Behandle Trading-Fehler mit Auto-Diagnose"""
        if not COLLABORATION_AVAILABLE:
            return
        
        try:
            # Reporte Fehler
            if self.protocol:
                await self.protocol.report_error(
                    f"Trading Loop Fehler: {str(error)}",
                    {
                        "error_type": type(error).__name__,
                        "active_pairs": len(self.get_active_pairs()),
                        "last_scan": datetime.now().isoformat()
                    }
                )
            
            # Auto-Diagnose anfordern
            diagnosis = await diagnose_and_fix_agent(
                self.name,
                f"Trading Loop Exception: {str(error)}",
                {
                    "error_type": type(error).__name__,
                    "context": "trading_loop"
                }
            )
            
            log.info(f"🔍 Diagnose für Trading Fehler: {diagnosis.get('issue_id')}")
            
        except Exception as e:
            log.error(f"Fehlerbehandlung fehlgeschlagen: {e}")
    
    def is_healthy(self) -> bool:
        """Prüfe ob Bot gesund ist"""
        if not self.base_bot:
            return False
        
        try:
            # Einfache Health-Check
            return self.is_running
        except:
            return False
    
    def get_active_pairs(self) -> List[str]:
        """Hole aktive Trading-Pairs"""
        # Simuliere aktive Pairs
        return ["BTC/USDT", "ETH/USDT", "BNB/USDT", "ADA/USDT", "DOT/USDT"]

# Global Instance
trading_agent = TradingBotAgent()

# Exportierte Funktionen für Integration
async def start_trading_agent():
    """Starte Trading Bot Agent"""
    return await trading_agent.start()

async def stop_trading_agent():
    """Stoppe Trading Bot Agent"""
    return await trading_agent.stop()

def get_trading_agent_status() -> Dict:
    """Hole Status des Trading Bot Agent"""
    return {
        "name": trading_agent.name,
        "running": trading_agent.is_running,
        "healthy": trading_agent.is_healthy(),
        "capabilities": trading_agent.capabilities,
        "active_pairs": trading_agent.get_active_pairs()
    }

if __name__ == "__main__":
    # Test
    async def test_trading_agent():
        await start_trading_agent()
        
        # Laufe für 2 Minuten zum Testen
        await asyncio.sleep(120)
        
        await stop_trading_agent()
        print("Test abgeschlossen")
    
    asyncio.run(test_trading_agent())
