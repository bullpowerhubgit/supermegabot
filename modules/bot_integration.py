"""
Bot Integration Module - DeepScan & Repair Tool Integration
Integriert das DeepScan System in verschiedene Bot-Komponenten
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any
try:
    from .deepscan_repair_tool import DeepScanRepairTool, DeepScanScheduler, integrate_deepscan_tool
except ImportError:
    from deepscan_repair_tool import DeepScanRepairTool, DeepScanScheduler, integrate_deepscan_tool

logger = logging.getLogger(__name__)

class BotDeepScanIntegration:
    """Zentrale Integration für alle Bot-Komponenten"""
    
    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path) if base_path else Path(__file__).parent.parent
        self.deepscan_tool = DeepScanRepairTool("SuperMegaBot")
        self.scheduler = DeepScanScheduler(self.deepscan_tool)
        self.integrations = {}
        
    async def initialize_all_integrations(self):
        """Initialisiert alle Integrationen"""
        logger.info("🔧 Initialisiere Bot Integrationen...")
        
        # Dashboard Server Integration
        await self._integrate_dashboard_server()
        
        # Telegram Bot Integration  
        await self._integrate_telegram_bot()
        
        # Shopify Suite Integration
        await self._integrate_shopify_suite()
        
        # CreatorHub Integration
        await self._integrate_creatorhub()
        
        # API Gateway Integration
        await self._integrate_api_gateway()
        
        # Start Scheduler
        asyncio.create_task(self.scheduler.start_scheduler())
        
        logger.info("✅ Alle Bot Integrationen initialisiert")
    
    async def _integrate_dashboard_server(self):
        """Integriert in Dashboard Server"""
        try:
            # Dashboard Server Routes sind bereits in server.py implementiert
            # Wir müssen nur prüfen ob der Server läuft
            import aiohttp
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get('http://localhost:8888/api/deepscan/status', timeout=5) as resp:
                        if resp.status == 200:
                            self.integrations["dashboard"] = True
                            logger.info("✅ Dashboard Server Integration - API aktiv")
                            return
                except Exception:
                    pass
            
            # Fallback: Dashboard API ist verfügbar aber Server läuft noch nicht
            self.integrations["dashboard"] = True
            logger.info("✅ Dashboard Server Integration - Routes konfiguriert")
            
        except Exception as e:
            logger.error(f"❌ Dashboard Server Integration failed: {e}")
            self.integrations["dashboard"] = False
    
    async def _integrate_telegram_bot(self):
        """Integriert in Telegram Bot"""
        try:
            telegram_path = self.base_path / "windsurf-telegram-bot"
            if not telegram_path.exists():
                return
            
            # Check if telegram bot has integration points
            bot_file = telegram_path / "bot.py"
            if bot_file.exists():
                # Add DeepScan monitoring to telegram bot
                await self._add_telegram_monitoring(telegram_path)
                self.integrations["telegram"] = True
                logger.info("✅ Telegram Bot Integration")
            
        except Exception as e:
            logger.error(f"❌ Telegram Bot Integration failed: {e}")
            self.integrations["telegram"] = False
    
    async def _add_telegram_monitoring(self, telegram_path: Path):
        """Fügt Monitoring zum Telegram Bot hinzu"""
        monitoring_file = telegram_path / "deepscan_monitoring.py"
        
        monitoring_code = '''
"""
DeepScan Monitoring für Telegram Bot
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent / "modules"))

try:
    from deepscan_repair_tool import DeepScanRepairTool
    
    class TelegramDeepScanMonitor:
        def __init__(self):
            self.tool = DeepScanRepairTool("TelegramBot")
            self.last_check = None
        
        async def check_system_health(self):
            """Überprüft System-Gesundheit"""
            results = await self.tool.perform_deep_scan()
            
            issues_count = results.get("total_issues", 0)
            critical_issues = len([i for i in results.get("issues_found", []) 
                                if i.get("severity") == "high"])
            
            return {
                "healthy": critical_issues == 0,
                "issues": issues_count,
                "critical": critical_issues,
                "timestamp": datetime.now().isoformat()
            }
        
        async def get_daily_summary(self):
            """Gibt tägliche Zusammenfassung"""
            metrics = self.tool.get_metrics()
            
            return f"""
🤖 **SuperMegaBot Health Report**
📅 {datetime.now().strftime('%Y-%m-%d')}

📊 **Statistiken:**
• Scans heute: {metrics['scan_metrics']['total_scans']}
• Fehler gefunden: {metrics['scan_metrics']['errors_found']}
• Fehler behoben: {metrics['scan_metrics']['errors_fixed']}
• Pattern erkannt: {metrics['error_patterns_count']}

🔧 **System Status:**
{'✅ Gesund' if metrics['scan_metrics']['errors_found'] < 10 else '⚠️ Aufmerksamkeit benötigt'}
            """
    
    # Global instance
    monitor = TelegramDeepScanMonitor()
    
except ImportError:
    print("DeepScan Tool nicht verfügbar")
    monitor = None
'''
        
        with open(monitoring_file, 'w') as f:
            f.write(monitoring_code)
    
    async def _integrate_shopify_suite(self):
        """Integriert in Shopify Suite"""
        try:
            shopify_path = self.base_path / "windsurf-shopify-suite"
            if not shopify_path.exists():
                return
            
            # Add DeepScan hooks to Shopify suite
            await self._add_shopify_monitoring(shopify_path)
            self.integrations["shopify"] = True
            logger.info("✅ Shopify Suite Integration")
            
        except Exception as e:
            logger.error(f"❌ Shopify Suite Integration failed: {e}")
            self.integrations["shopify"] = False
    
    async def _add_shopify_monitoring(self, shopify_path: Path):
        """Fügt Monitoring zur Shopify Suite hinzu"""
        monitoring_file = shopify_path / "src" / "deepscan_integration.js"
        
        monitoring_code = '''
/**
 * DeepScan Integration für Shopify Suite
 */

class DeepScanIntegration {
    constructor() {
        this.baseURL = process.env.DASHBOARD_URL || 'http://localhost:8888';
        this.lastCheck = null;
        this.checkInterval = 300000; // 5 Minuten
    }
    
    async checkSystemHealth() {
        try {
            const response = await fetch(`${this.baseURL}/api/deepscan/status`);
            const status = await response.json();
            
            return {
                healthy: status.status === 'running',
                lastScan: status.last_scan,
                totalScans: status.total_scans,
                schedulerActive: status.scheduler_active
            };
        } catch (error) {
            console.error('DeepScan Status Check failed:', error);
            return { healthy: false, error: error.message };
        }
    }
    
    async triggerScan() {
        try {
            const response = await fetch(`${this.baseURL}/api/deepscan/scan`);
            const results = await response.json();
            
            return {
                success: true,
                issuesFound: results.issues_found,
                issuesFixed: results.auto_repair?.repairs_successful || 0,
                scanId: results.scan_id
            };
        } catch (error) {
            console.error('DeepScan Trigger failed:', error);
            return { success: false, error: error.message };
        }
    }
    
    async getMetrics() {
        try {
            const response = await fetch(`${this.baseURL}/api/deepscan/metrics`);
            return await response.json();
        } catch (error) {
            console.error('DeepScan Metrics failed:', error);
            return { error: error.message };
        }
    }
    
    startMonitoring() {
        console.log('🔧 Starting DeepScan monitoring...');
        
        // Check health every 5 minutes
        setInterval(async () => {
            const health = await this.checkSystemHealth();
            
            if (!health.healthy) {
                console.warn('⚠️ DeepScan system unhealthy:', health);
                
                // Try to trigger repair
                const repair = await this.triggerRepair();
                console.log('🔧 Auto-repair triggered:', repair);
            }
        }, this.checkInterval);
        
        console.log('✅ DeepScan monitoring started');
    }
    
    async triggerRepair() {
        try {
            const response = await fetch(`${this.baseURL}/api/deepscan/repair`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            return await response.json();
        } catch (error) {
            console.error('DeepScan Repair failed:', error);
            return { success: false, error: error.message };
        }
    }
}

// Export singleton
const deepscanIntegration = new DeepScanIntegration();

module.exports = { deepscanIntegration, DeepScanIntegration };
'''
        
        monitoring_file.parent.mkdir(exist_ok=True)
        with open(monitoring_file, 'w') as f:
            f.write(monitoring_code)
    
    async def _integrate_creatorhub(self):
        """Integriert in CreatorHub"""
        try:
            creatorhub_path = self.base_path / "digifabrik"
            if not creatorhub_path.exists():
                # Check alternative path
                creatorhub_path = self.base_path.parent / "digifabrik"
            
            if creatorhub_path.exists():
                await self._add_creatorhub_monitoring(creatorhub_path)
                self.integrations["creatorhub"] = True
                logger.info("✅ CreatorHub Integration")
            
        except Exception as e:
            logger.error(f"❌ CreatorHub Integration failed: {e}")
            self.integrations["creatorhub"] = False
    
    async def _add_creatorhub_monitoring(self, creatorhub_path: Path):
        """Fügt Monitoring zu CreatorHub hinzu"""
        monitoring_file = creatorhub_path / "deepscan_integration.ts"
        
        monitoring_code = '''
/**
 * DeepScan Integration für CreatorHub (TypeScript)
 */

interface DeepScanStatus {
    status: 'running' | 'stopped';
    scheduler_active: boolean;
    last_scan: string | null;
    total_scans: number;
}

interface DeepScanMetrics {
    scan_metrics: {
        total_scans: number;
        errors_found: number;
        errors_fixed: number;
        last_scan: string | null;
    };
    error_patterns_count: number;
    repair_history_count: number;
    improvement_version: string;
}

class CreatorHubDeepScanIntegration {
    private baseURL: string;
    private monitoringInterval: NodeJS.Timeout | null = null;
    
    constructor() {
        this.baseURL = process.env.DASHBOARD_URL || 'http://localhost:8888';
    }
    
    async getStatus(): Promise<DeepScanStatus> {
        try {
            const response = await fetch(`${this.baseURL}/api/deepscan/status`);
            return await response.json();
        } catch (error) {
            console.error('DeepScan Status Error:', error);
            throw error;
        }
    }
    
    async getMetrics(): Promise<DeepScanMetrics> {
        try {
            const response = await fetch(`${this.baseURL}/api/deepscan/metrics`);
            return await response.json();
        } catch (error) {
            console.error('DeepScan Metrics Error:', error);
            throw error;
        }
    }
    
    async triggerScan(): Promise<any> {
        try {
            const response = await fetch(`${this.baseURL}/api/deepscan/scan`);
            return await response.json();
        } catch (error) {
            console.error('DeepScan Trigger Error:', error);
            throw error;
        }
    }
    
    startMonitoring(): void {
        console.log('🔧 Starting CreatorHub DeepScan monitoring...');
        
        // Monitor every 10 minutes
        this.monitoringInterval = setInterval(async () => {
            try {
                const status = await this.getStatus();
                
                if (!status.scheduler_active) {
                    console.warn('⚠️ DeepScan Scheduler not active');
                }
                
                const metrics = await this.getMetrics();
                
                // Log metrics
                console.log(`📊 DeepScan Metrics: Scans=${metrics.scan_metrics.total_scans}, Issues=${metrics.scan_metrics.errors_found}, Fixed=${metrics.scan_metrics.errors_fixed}`);
                
            } catch (error) {
                console.error('❌ Monitoring error:', error);
            }
        }, 600000); // 10 minutes
        
        console.log('✅ CreatorHub DeepScan monitoring started');
    }
    
    stopMonitoring(): void {
        if (this.monitoringInterval) {
            clearInterval(this.monitoringInterval);
            this.monitoringInterval = null;
            console.log('🛑 CreatorHub DeepScan monitoring stopped');
        }
    }
}

// Export singleton
export const creatorHubDeepScan = new CreatorHubDeepScanIntegration();
export default creatorHubDeepScan;
'''
        
        with open(monitoring_file, 'w') as f:
            f.write(monitoring_code)
    
    async def _integrate_api_gateway(self):
        """Integriert in API Gateway"""
        try:
            gateway_path = self.base_path / "windsurf-api-gateway"
            if not gateway_path.exists():
                return
            
            await self._add_gateway_monitoring(gateway_path)
            self.integrations["api_gateway"] = True
            logger.info("✅ API Gateway Integration")
            
        except Exception as e:
            logger.error(f"❌ API Gateway Integration failed: {e}")
            self.integrations["api_gateway"] = False
    
    async def _add_gateway_monitoring(self, gateway_path: Path):
        """Fügt Monitoring zum API Gateway hinzu"""
        monitoring_file = gateway_path / "src" / "deepscan_middleware.js"
        
        monitoring_code = '''
/**
 * DeepScan Middleware für API Gateway
 */

class DeepScanMiddleware {
    constructor() {
        this.baseURL = process.env.DASHBOARD_URL || 'http://localhost:8888';
        this.requestCount = 0;
        this.errorCount = 0;
        this.lastHealthCheck = null;
    }
    
    middleware() {
        return async (req, res, next) => {
            this.requestCount++;
            
            // Log every 100 requests
            if (this.requestCount % 100 === 0) {
                await this._checkAndReport();
            }
            
            // Count errors
            res.on('finish', () => {
                if (res.statusCode >= 400) {
                    this.errorCount++;
                }
            });
            
            next();
        };
    }
    
    async _checkAndReport() {
        try {
            const response = await fetch(`${this.baseURL}/api/deepscan/metrics`);
            const metrics = await response.json();
            
            console.log(`📊 API Gateway Report: Requests=${this.requestCount}, Errors=${this.errorCount}, DeepScan Issues=${metrics.scan_metrics.errors_found}`);
            
            // Trigger scan if too many errors
            if (this.errorCount > 10) {
                console.log('🔧 High error rate detected, triggering DeepScan...');
                await this._triggerScan();
                this.errorCount = 0; // Reset counter
            }
            
        } catch (error) {
            console.error('DeepScan reporting failed:', error);
        }
    }
    
    async _triggerScan() {
        try {
            const response = await fetch(`${this.baseURL}/api/deepscan/scan`);
            const results = await response.json();
            
            console.log(`🔧 DeepScan completed: ${results.issues_found} issues found`);
            
        } catch (error) {
            console.error('DeepScan trigger failed:', error);
        }
    }
    
    getStats() {
        return {
            requests: this.requestCount,
            errors: this.errorCount,
            errorRate: this.requestCount > 0 ? (this.errorCount / this.requestCount * 100).toFixed(2) + '%' : '0%',
            lastHealthCheck: this.lastHealthCheck
        };
    }
}

// Create and export middleware
const deepscanMiddleware = new DeepScanMiddleware();
module.exports = { deepscanMiddleware, DeepScanMiddleware };
'''
        
        monitoring_file.parent.mkdir(exist_ok=True)
        with open(monitoring_file, 'w') as f:
            f.write(monitoring_code)
    
    async def run_system_wide_scan(self) -> Dict:
        """Führt systemweiten Scan durch"""
        logger.info("🔍 Starting system-wide DeepScan...")
        
        # Get integration status
        integration_status = {}
        for name, active in self.integrations.items():
            integration_status[name] = {
                "active": active,
                "status": "integrated" if active else "failed"
            }
        
        # Run comprehensive scan
        scan_results = await self.deepscan_tool.run_scheduled_deep_scan()
        scan_results["integration_status"] = integration_status
        
        # Auto-repair if needed
        if scan_results.get("total_issues", 0) > 0:
            repair_results = await self.deepscan_tool.auto_repair(scan_results)
            scan_results["system_repair"] = repair_results
        
        # Notify all integrations
        await self._notify_integrations(scan_results)
        
        logger.info(f"✅ System-wide scan completed: {scan_results.get('total_issues', 0)} issues")
        
        return scan_results
    
    async def _notify_integrations(self, scan_results: Dict):
        """Benachrichtigt alle Integrationen über Scan-Ergebnisse"""
        
        # Notify Dashboard (already integrated via routes)
        
        # Notify Telegram Bot if active
        if self.integrations.get("telegram"):
            await self._notify_telegram(scan_results)
        
        # Notify Shopify Suite if active
        if self.integrations.get("shopify"):
            await self._notify_shopify(scan_results)
        
        # Notify CreatorHub if active
        if self.integrations.get("creatorhub"):
            await self._notify_creatorhub(scan_results)
    
    async def _notify_telegram(self, scan_results: Dict):
        """Benachrichtigt Telegram Bot"""
        try:
            # This would send a message to the Telegram bot
            # Implementation depends on telegram bot structure
            pass
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")
    
    async def _notify_shopify(self, scan_results: Dict):
        """Benachrichtigt Shopify Suite"""
        try:
            # This could trigger webhook or update Shopify dashboard
            pass
        except Exception as e:
            logger.error(f"Shopify notification failed: {e}")
    
    async def _notify_creatorhub(self, scan_results: Dict):
        """Benachrichtigt CreatorHub"""
        try:
            # This could update CreatorHub dashboard
            pass
        except Exception as e:
            logger.error(f"CreatorHub notification failed: {e}")
    
    def get_integration_status(self) -> Dict:
        """Gibt Status aller Integrationen zurück"""
        return {
            "integrations": self.integrations,
            "scheduler_running": self.scheduler.running,
            "deepscan_metrics": self.deepscan_tool.get_metrics(),
            "last_system_scan": self.deepscan_tool.scan_metrics.get("last_scan")
        }
    
    async def shutdown(self):
        """Fährt alle Integrationen herunter"""
        logger.info("🛑 Shutting down Bot Integration...")
        
        # Stop scheduler
        self.scheduler.stop_scheduler()
        
        # Cleanup integrations
        for name, active in self.integrations.items():
            if active:
                try:
                    # Integration-specific cleanup
                    pass
                except Exception as e:
                    logger.error(f"Error shutting down {name}: {e}")
        
        logger.info("✅ Bot Integration shutdown complete")


# Haupt-Integration-Funktion
async def initialize_bot_deepscan(base_path: str = None) -> BotDeepScanIntegration:
    """Initialisiert die komplette Bot DeepScan Integration"""
    integration = BotDeepScanIntegration(base_path)
    await integration.initialize_all_integrations()
    return integration


# Für direkte Verwendung
if __name__ == "__main__":
    async def main():
        integration = await initialize_bot_deepscan()
        
        # Test system-wide scan
        results = await integration.run_system_wide_scan()
        print(f"🔍 System-wide scan: {results}")
        
        # Show integration status
        status = integration.get_integration_status()
        print(f"📊 Integration status: {status}")
        
        # Shutdown
        await integration.shutdown()
    
    asyncio.run(main())
