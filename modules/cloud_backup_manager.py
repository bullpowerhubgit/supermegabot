"""
Cloud Backup Manager - Automatisches Cloud-Backup für DeepScan Daten
Unterstützt verschiedene Cloud-Provider und Backup-Strategien
"""

import os
import json
import logging
import asyncio
import shutil
import hashlib
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import subprocess

logger = logging.getLogger(__name__)

class CloudBackupManager:
    """Cloud-Backup Manager für DeepScan Daten"""
    
    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path) if base_path else Path(__file__).parent.parent
        self.data_dir = self.base_path / "data"
        self.backup_dir = self.base_path / "backups"
        self.cloud_backup_dir = self.base_path / "cloud_backups"
        
        # Backup-Konfiguration
        self.backup_config = {
            "enabled": True,
            "interval_hours": 6,  # Alle 6 Stunden
            "max_backups": 30,  # Max 30 Backups behalten
            "compression": True,
            "encryption": False,
            "providers": {
                "local": True,
                "github": True,  # GitHub automatisch aktivieren
                "dropbox": False,
                "google_drive": False
            }
        }
        
        # Initialisierung
        self._initialize_directories()
        self._load_backup_config()
    
    def _initialize_directories(self):
        """Initialisiert Backup-Verzeichnisse"""
        for dir_path in [self.backup_dir, self.cloud_backup_dir]:
            dir_path.mkdir(exist_ok=True)
    
    def _load_backup_config(self):
        """Lädt Backup-Konfiguration"""
        config_file = self.data_dir / "backup_config.json"
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    saved_config = json.load(f)
                    self.backup_config.update(saved_config)
            except Exception as e:
                logger.error(f"Error loading backup config: {e}")
    
    def _save_backup_config(self):
        """Speichert Backup-Konfiguration"""
        config_file = self.data_dir / "backup_config.json"
        try:
            with open(config_file, 'w') as f:
                json.dump(self.backup_config, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving backup config: {e}")
    
    async def create_backup(self, backup_name: str = None) -> Dict:
        """Erstellt ein Backup aller wichtigen Daten"""
        if not self.backup_config["enabled"]:
            return {"success": False, "error": "Backup disabled"}
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = backup_name or f"deepscan_backup_{timestamp}"
        
        backup_path = self.backup_dir / backup_name
        backup_path.mkdir(exist_ok=True)
        
        logger.info(f"📦 Creating backup: {backup_name}")
        
        try:
            # 1. DeepScan Daten sichern
            await self._backup_deepscan_data(backup_path)
            
            # 2. Backup-Metadaten erstellen
            metadata = await self._create_backup_metadata(backup_path, backup_name)
            
            # 3. Komprimieren wenn aktiviert
            if self.backup_config["compression"]:
                archive_path = await self._compress_backup(backup_path, backup_name)
                backup_path = archive_path
            
            # 4. Cloud-Backup durchführen
            cloud_results = await self._perform_cloud_backup(backup_path, backup_name)
            
            # 5. Alte Backups aufräumen
            await self._cleanup_old_backups()
            
            logger.info(f"✅ Backup completed: {backup_name}")
            
            return {
                "success": True,
                "backup_name": backup_name,
                "backup_path": str(backup_path),
                "metadata": metadata,
                "cloud_results": cloud_results,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Backup failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "backup_name": backup_name
            }
    
    async def _backup_deepscan_data(self, backup_path: Path):
        """Sichert DeepScan-Daten"""
        deepscan_data = {
            "error_patterns.json": self.data_dir / "error_patterns.json",
            "repair_history.json": self.data_dir / "repair_history.json",
            "improvements.json": self.data_dir / "improvements.json",
            "scan_results.json": self.data_dir / "scan_results.json"
        }
        
        for name, source_path in deepscan_data.items():
            if source_path.exists():
                shutil.copy2(source_path, backup_path / name)
                logger.debug(f"✓ Backed up {name}")
    
    async def _create_backup_metadata(self, backup_path: Path, backup_name: str) -> Dict:
        """Erstellt Backup-Metadaten"""
        metadata = {
            "backup_name": backup_name,
            "created_at": datetime.now().isoformat(),
            "files_backed_up": [],
            "total_size": 0,
            "deepscan_version": "1.0",
            "system_info": await self._get_system_info()
        }
        
        # Dateien auflisten
        for file_path in backup_path.rglob("*"):
            if file_path.is_file():
                file_size = file_path.stat().st_size
                metadata["files_backed_up"].append({
                    "path": str(file_path.relative_to(backup_path)),
                    "size": file_size,
                    "hash": self._calculate_file_hash(file_path)
                })
                metadata["total_size"] += file_size
        
        # Metadaten speichern
        metadata_file = backup_path / "backup_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return metadata
    
    async def _compress_backup(self, backup_path: Path, backup_name: str) -> Path:
        """Komprimiert Backup zu ZIP"""
        archive_name = f"{backup_name}.zip"
        archive_path = self.backup_dir / archive_name
        
        logger.info(f"🗜️ Compressing backup to {archive_name}")
        
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in backup_path.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(backup_path)
                    zipf.write(file_path, arcname)
        
        # Original Verzeichnis löschen
        shutil.rmtree(backup_path)
        
        logger.info(f"✓ Compressed to {archive_path.stat().st_size / (1024*1024):.1f}MB")
        
        return archive_path
    
    async def _perform_cloud_backup(self, backup_path: Path, backup_name: str) -> Dict:
        """Führt Cloud-Backup durch"""
        results = {}
        
        # Local Backup (immer aktiv)
        if self.backup_config["providers"]["local"]:
            results["local"] = await self._backup_to_local(backup_path, backup_name)
        
        # GitHub Backup
        if self.backup_config["providers"]["github"]:
            results["github"] = await self._backup_to_github(backup_path, backup_name)
        
        # Dropbox Backup
        if self.backup_config["providers"]["dropbox"]:
            results["dropbox"] = await self._backup_to_dropbox(backup_path, backup_name)
        
        # Google Drive Backup
        if self.backup_config["providers"]["google_drive"]:
            results["google_drive"] = await self._backup_to_google_drive(backup_path, backup_name)
        
        return results
    
    async def _backup_to_local(self, backup_path: Path, backup_name: str) -> Dict:
        """Lokales Backup"""
        try:
            local_backup_path = self.cloud_backup_dir / backup_name
            if backup_path.is_file():
                shutil.copy2(backup_path, local_backup_path)
            else:
                shutil.copytree(backup_path, local_backup_path)
            
            return {
                "success": True,
                "path": str(local_backup_path),
                "size": local_backup_path.stat().st_size if local_backup_path.exists() else 0
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _backup_to_github(self, backup_path: Path, backup_name: str) -> Dict:
        """GitHub Backup via Git"""
        try:
            # Prüfen ob Git Repository
            git_dir = self.base_path / ".git"
            if not git_dir.exists():
                return {"success": False, "error": "Not a git repository"}
            
            # Backup Datei zum Repository hinzufügen
            backup_dest = self.base_path / "backups" / backup_name
            if backup_path.is_file():
                shutil.copy2(backup_path, backup_dest)
            else:
                shutil.copytree(backup_path, backup_dest)
            
            # Git commands
            commands = [
                ["git", "add", str(backup_dest)],
                ["git", "commit", "-m", f"DeepScan backup: {backup_name}"],
                ["git", "push"]
            ]
            
            for cmd in commands:
                result = subprocess.run(cmd, cwd=str(self.base_path), capture_output=True, text=True)
                if result.returncode != 0:
                    return {"success": False, "error": f"Git command failed: {result.stderr}"}
            
            return {"success": True, "repository": "GitHub"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _backup_to_dropbox(self, backup_path: Path, backup_name: str) -> Dict:
        """Dropbox Backup (Platzhalter)"""
        # Hier Dropbox API Integration implementieren
        return {"success": False, "error": "Dropbox API not configured"}
    
    async def _backup_to_google_drive(self, backup_path: Path, backup_name: str) -> Dict:
        """Google Drive Backup (Platzhalter)"""
        # Hier Google Drive API Integration implementieren
        return {"success": False, "error": "Google Drive API not configured"}
    
    async def _cleanup_old_backups(self):
        """Räumt alte Backups auf"""
        try:
            # Lokale Backups
            local_backups = sorted(self.backup_dir.glob("deepscan_backup_*.zip"), 
                                  key=lambda x: x.stat().st_mtime, reverse=True)
            
            for old_backup in local_backups[self.backup_config["max_backups"]:]:
                old_backup.unlink()
                logger.info(f"🗑️ Removed old backup: {old_backup.name}")
            
            # Cloud Backups
            cloud_backups = sorted(self.cloud_backup_dir.glob("*"), 
                                  key=lambda x: x.stat().st_mtime, reverse=True)
            
            for old_backup in cloud_backups[self.backup_config["max_backups"]:]:
                if old_backup.is_file():
                    old_backup.unlink()
                else:
                    shutil.rmtree(old_backup)
                logger.info(f"🗑️ Removed old cloud backup: {old_backup.name}")
            
        except Exception as e:
            logger.error(f"Error cleaning up old backups: {e}")
    
    async def restore_backup(self, backup_name: str) -> Dict:
        """Stellt ein Backup wieder her"""
        try:
            # Backup finden
            backup_path = self.backup_dir / f"{backup_name}.zip"
            if not backup_path.exists():
                backup_path = self.cloud_backup_dir / backup_name
            
            if not backup_path.exists():
                return {"success": False, "error": "Backup not found"}
            
            logger.info(f"📥 Restoring backup: {backup_name}")
            
            # Backup entpacken
            restore_dir = self.data_dir / "restore_temp"
            restore_dir.mkdir(exist_ok=True)
            
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall(restore_dir)
            
            # Daten wiederherstellen
            for file_path in restore_dir.rglob("*.json"):
                dest_path = self.data_dir / file_path.name
                shutil.copy2(file_path, dest_path)
                logger.info(f"✓ Restored {file_path.name}")
            
            # Temporäres Verzeichnis aufräumen
            shutil.rmtree(restore_dir)
            
            logger.info(f"✅ Backup restored: {backup_name}")
            
            return {
                "success": True,
                "backup_name": backup_name,
                "restored_files": list(self.data_dir.glob("*.json"))
            }
            
        except Exception as e:
            logger.error(f"❌ Restore failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def list_backups(self) -> Dict:
        """Listet alle verfügbaren Backups"""
        try:
            local_backups = []
            for backup_path in self.backup_dir.glob("deepscan_backup_*.zip"):
                stat = backup_path.stat()
                local_backups.append({
                    "name": backup_path.name,
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "location": "local"
                })
            
            cloud_backups = []
            for backup_path in self.cloud_backup_dir.glob("*"):
                if backup_path.is_file():
                    stat = backup_path.stat()
                    cloud_backups.append({
                        "name": backup_path.name,
                        "size": stat.st_size,
                        "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "location": "cloud"
                    })
            
            return {
                "success": True,
                "local_backups": sorted(local_backups, key=lambda x: x["created"], reverse=True),
                "cloud_backups": sorted(cloud_backups, key=lambda x: x["created"], reverse=True),
                "total_backups": len(local_backups) + len(cloud_backups)
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _get_system_info(self) -> Dict:
        """Sammelt System-Informationen"""
        try:
            import platform
            import psutil
            
            return {
                "os": platform.system(),
                "os_version": platform.version(),
                "python_version": platform.python_version(),
                "hostname": platform.node(),
                "cpu_count": psutil.cpu_count(),
                "memory_total": psutil.virtual_memory().total,
                "disk_total": psutil.disk_usage('/').total
            }
        except ImportError:
            return {"error": "System info not available"}
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Berechnet SHA256 Hash einer Datei"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def configure_backup(self, config: Dict):
        """Konfiguriert Backup-Einstellungen"""
        self.backup_config.update(config)
        self._save_backup_config()
        logger.info(f"🔧 Backup configuration updated")
    
    def get_backup_status(self) -> Dict:
        """Gibt Backup-Status zurück"""
        try:
            backups = self.backup_dir.glob("deepscan_backup_*.zip")
            latest_backup = max(backups, key=lambda x: x.stat().st_mtime) if backups else None
            
            return {
                "enabled": self.backup_config["enabled"],
                "last_backup": latest_backup.stat().st_mtime if latest_backup else None,
                "total_backups": len(list(backups)),
                "config": self.backup_config,
                "storage_used": sum(b.stat().st_size for b in backups) / (1024**3)  # GB
            }
        except Exception as e:
            return {"error": str(e)}


class BackupScheduler:
    """Scheduler für automatische Backups"""
    
    def __init__(self, backup_manager: CloudBackupManager):
        self.backup_manager = backup_manager
        self.running = False
        self.interval_hours = backup_manager.backup_config["interval_hours"]
    
    async def start_scheduler(self):
        """Startet den Backup-Scheduler"""
        self.running = True
        logger.info(f"📅 Backup Scheduler started - Interval: {self.interval_hours}h")
        
        while self.running:
            try:
                # Backup durchführen
                result = await self.backup_manager.create_backup()
                
                if result["success"]:
                    logger.info(f"✅ Scheduled backup completed: {result['backup_name']}")
                else:
                    logger.error(f"❌ Scheduled backup failed: {result.get('error')}")
                
                # Warten bis zum nächsten Backup
                await asyncio.sleep(self.interval_hours * 3600)
                
            except Exception as e:
                logger.error(f"Backup scheduler error: {e}")
                await asyncio.sleep(300)  # 5 Minuten bei Fehler
    
    def stop_scheduler(self):
        """Stoppt den Backup-Scheduler"""
        self.running = False
        logger.info("📅 Backup Scheduler stopped")


# Integration mit DeepScan
def integrate_cloud_backup(deepscan_tool):
    """Integriert Cloud-Backup in DeepScan Tool"""
    backup_manager = CloudBackupManager()
    
    # Backup nach jedem DeepScan
    original_scan = deepscan_tool.run_scheduled_deep_scan
    
    async def scan_with_backup():
        results = await original_scan()
        
        # Backup nach erfolgreichem Scan
        if results.get("total_issues", 0) > 0:
            backup_result = await backup_manager.create_backup()
            results["backup"] = backup_result
        
        return results
    
    deepscan_tool.run_scheduled_deep_scan = scan_with_backup
    deepscan_tool.backup_manager = backup_manager
    
    return backup_manager


# Für direkte Verwendung
if __name__ == "__main__":
    async def main():
        manager = CloudBackupManager()
        
        # Test Backup
        result = await manager.create_backup("test_backup")
        print(f"Backup result: {result}")
        
        # Backups auflisten
        backups = await manager.list_backups()
        print(f"Available backups: {backups}")
    
    asyncio.run(main())
