"""
DeepScan Initializer - Automatische Initialisierung und Start
Startet das DeepScan System beim Bot-Start
"""

import asyncio
import logging
from pathlib import Path
try:
    from .deepscan_repair_tool import DeepScanRepairTool, DeepScanScheduler
    from .bot_integration import BotDeepScanIntegration
    from .cloud_backup_manager import CloudBackupManager, BackupScheduler
except ImportError:
    # Fallback for direct execution
    from deepscan_repair_tool import DeepScanRepairTool, DeepScanScheduler
    from bot_integration import BotDeepScanIntegration
    try:
        from cloud_backup_manager import CloudBackupManager, BackupScheduler
    except ImportError:
        CloudBackupManager = None
        BackupScheduler = None

logger = logging.getLogger(__name__)

class DeepScanInitializer:
    """Initialisiert und startet das komplette DeepScan System"""
    
    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path) if base_path else Path(__file__).parent.parent
        self.integration = None
        self.scheduler = None
        self.backup_scheduler = None
        self.initialized = False
    
    async def initialize(self):
        """Initialisiert das komplette DeepScan System"""
        if self.initialized:
            logger.info("🔧 DeepScan bereits initialisiert")
            return
        
        try:
            logger.info("🚀 Initialisiere DeepScan System...")
            
            # 1. Bot Integration initialisieren
            self.integration = BotDeepScanIntegration(str(self.base_path))
            await self.integration.initialize_all_integrations()
            
            # 2. Scheduler starten
            self.scheduler = self.integration.scheduler
            
            # 2.5 Backup Scheduler starten
            if BackupScheduler and self.integration.deepscan_tool.backup_manager:
                self.backup_scheduler = BackupScheduler(self.integration.deepscan_tool.backup_manager)
                asyncio.create_task(self.backup_scheduler.start_scheduler())
                logger.info("✅ Backup Scheduler gestartet")
            
            # 3. Initialen Scan durchführen
            logger.info("🔍 Führe initialen DeepScan durch...")
            initial_results = await self.integration.run_system_wide_scan()
            
            # 4. Status loggen
            status = self.integration.get_integration_status()
            logger.info(f"✅ DeepScan System initialisiert: {status}")
            
            self.initialized = True
            
            return {
                "success": True,
                "initial_scan": initial_results,
                "integration_status": status
            }
            
        except Exception as e:
            logger.error(f"❌ DeepScan Initialisierung fehlgeschlagen: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def shutdown(self):
        """Fährt das DeepScan System herunter"""
        if not self.initialized:
            return
        
        try:
            logger.info("🛑 Fahre DeepScan System herunter...")
            
            # Backup Scheduler stoppen
            if self.backup_scheduler:
                self.backup_scheduler.stop_scheduler()
                logger.info("✅ Backup Scheduler gestoppt")
            
            if self.integration:
                await self.integration.shutdown()
            
            self.initialized = False
            logger.info("✅ DeepScan System heruntergefahren")
            
        except Exception as e:
            logger.error(f"❌ DeepScan Shutdown fehlgeschlagen: {e}")
    
    def get_status(self):
        """Gibt aktuellen Status zurück"""
        if not self.initialized:
            return {"status": "not_initialized"}
        
        return self.integration.get_integration_status() if self.integration else {"status": "error"}

# Global instance
_deepscan_initializer = None

async def get_deepscan_initializer(base_path: str = None) -> DeepScanInitializer:
    """Gibt oder erstellt die DeepScan Initializer Instanz"""
    global _deepscan_initializer
    
    if _deepscan_initializer is None:
        _deepscan_initializer = DeepScanInitializer(base_path)
        await _deepscan_initializer.initialize()
    
    return _deepscan_initializer

async def initialize_deepscan_on_startup():
    """Initialisiert DeepScan beim Bot-Start"""
    try:
        initializer = await get_deepscan_initializer()
        logger.info("🎯 DeepScan erfolgreich beim Start initialisiert")
        return initializer
    except Exception as e:
        logger.error(f"💥 DeepScan Start-Initialisierung fehlgeschlagen: {e}")
        return None

# Für Import in anderen Modulen
__all__ = [
    'DeepScanInitializer',
    'get_deepscan_initializer', 
    'initialize_deepscan_on_startup'
]
