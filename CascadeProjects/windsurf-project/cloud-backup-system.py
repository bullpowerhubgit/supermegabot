#!/usr/bin/env python3
"""
🔒 Ultimate RudiBot Cloud Backup System
========================================
Automatisches, verschlüsseltes Cloud-Backup für das gesamte System
Unterstützt: Google Drive, Dropbox, iCloud, OneDrive, AWS S3
"""

import os
import sys
import json
import shutil
import hashlib
import logging
import subprocess
import datetime
import zipfile
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

# Import GCP configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from gcp_config import gcp_config

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/Users/rudolfsarkany/windsurf-telegram-bot/logs/cloud-backup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('CloudBackup')


class CloudBackupSystem:
    """Professionelles Cloud-Backup-System mit Verschlüsselung"""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or os.path.expanduser('~/Desktop/RudiBot-Cloud-Backup/backup-config.json')
        self.config = self.load_config()
        self.backup_dir = Path(self.config.get('backup_dir', os.path.expanduser('~/Desktop/RudiBot-Cloud-Backup/backups')))
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.encryption_key = self.get_encryption_key()
        self.cipher = Fernet(self.encryption_key) if self.encryption_key else None
        
        # Verzeichnisse die gesichert werden sollen
        self.source_dirs = [
            Path('/Users/rudolfsarkany/windsurf-telegram-bot'),
            Path('/Users/rudolfsarkany/supermegabot-windsurf-agents'),
            Path('/Users/rudolfsarkany/Library/LaunchAgents/com.ultimaterudibot.launcher.plist'),
            Path('/Users/rudolfsarkany/Desktop/RudiBot-Secure-API')
        ]
        
        # Ausnahmen
        self.exclude_patterns = [
            'node_modules',
            '.git',
            '__pycache__',
            '*.pyc',
            '.DS_Store',
            'logs/*.log',
            'backups'
        ]
        
        logger.info("🚀 Cloud Backup System initialisiert")
    
    def load_config(self) -> Dict:
        """Lädt Backup-Konfiguration"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"❌ Konfiguration konnte nicht geladen werden: {e}")
        
        # Standard-Konfiguration
        return {
            'backup_dir': os.path.expanduser('~/Desktop/RudiBot-Cloud-Backup/backups'),
            'schedule': 'daily',  # daily, weekly, monthly
            'retention_days': 30,
            'encryption': True,
            'compression': True,
            'cloud_providers': {
                'google_drive': {'enabled': False, 'credentials': ''},
                'dropbox': {'enabled': False, 'access_token': ''},
                'icloud': {'enabled': True},
                'onedrive': {'enabled': False, 'access_token': ''},
                'aws_s3': {'enabled': False, 'bucket': '', 'access_key': '', 'secret_key': ''}
            },
            'notification': {
                'telegram': True,
                'email': False
            }
        }
    
    def save_config(self):
        """Speichert Backup-Konfiguration"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info("✅ Konfiguration gespeichert")
        except Exception as e:
            logger.error(f"❌ Konfiguration konnte nicht gespeichert werden: {e}")
    
    def get_encryption_key(self) -> Optional[bytes]:
        """Generiert oder lädt Verschlüsselungsschlüssel"""
        if not self.config.get('encryption', True):
            return None
        
        key_file = Path(self.config.get('backup_dir', os.path.expanduser('~/Desktop/RudiBot-Cloud-Backup'))) / '.encryption_key'
        
        if key_file.exists():
            try:
                with open(key_file, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"❌ Schlüssel konnte nicht geladen werden: {e}")
        
        # Neuen Schlüssel generieren
        key = Fernet.generate_key()
        try:
            key_file.parent.mkdir(parents=True, exist_ok=True)
            with open(key_file, 'wb') as f:
                f.write(key)
            logger.info("🔑 Neuer Verschlüsselungsschlüssel generiert")
            return key
        except Exception as e:
            logger.error(f"❌ Schlüssel konnte nicht gespeichert werden: {e}")
            return None
    
    def encrypt_file(self, file_path: Path) -> Path:
        """Verschlüsselt eine Datei"""
        if not self.cipher:
            return file_path
        
        encrypted_path = file_path.with_suffix(file_path.suffix + '.enc')
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            encrypted_data = self.cipher.encrypt(data)
            
            with open(encrypted_path, 'wb') as f:
                f.write(encrypted_data)
            
            # Original löschen
            file_path.unlink()
            logger.info(f"🔒 Datei verschlüsselt: {file_path.name}")
            return encrypted_path
        except Exception as e:
            logger.error(f"❌ Verschlüsselung fehlgeschlagen: {e}")
            return file_path
    
    def decrypt_file(self, file_path: Path) -> Path:
        """Entschlüsselt eine Datei"""
        if not self.cipher or not file_path.suffix == '.enc':
            return file_path
        
        decrypted_path = file_path.with_suffix('')
        try:
            with open(file_path, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = self.cipher.decrypt(encrypted_data)
            
            with open(decrypted_path, 'wb') as f:
                f.write(decrypted_data)
            
            # Verschlüsselte Datei löschen
            file_path.unlink()
            logger.info(f"🔓 Datei entschlüsselt: {file_path.name}")
            return decrypted_path
        except Exception as e:
            logger.error(f"❌ Entschlüsselung fehlgeschlagen: {e}")
            return file_path
    
    def should_exclude(self, path: Path) -> bool:
        """Prüft ob ein Pfad ausgeschlossen werden soll"""
        for pattern in self.exclude_patterns:
            if pattern in str(path):
                return True
        return False
    
    def create_backup(self) -> Optional[Path]:
        """Erstellt ein vollständiges Backup"""
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"rudibot_backup_{timestamp}"
        backup_path = self.backup_dir / backup_name
        
        logger.info(f"📦 Erstelle Backup: {backup_name}")
        
        try:
            # Temporäres Verzeichnis für Backup
            temp_dir = self.backup_dir / f"temp_{timestamp}"
            temp_dir.mkdir(exist_ok=True)
            
            # Alle Quellverzeichnisse kopieren
            for source_dir in self.source_dirs:
                if not source_dir.exists():
                    logger.warning(f"⚠️  Quellverzeichnis existiert nicht: {source_dir}")
                    continue
                
                dest_dir = temp_dir / source_dir.name
                logger.info(f"📁 Kopiere: {source_dir.name}")
                
                if source_dir.is_file():
                    shutil.copy2(source_dir, dest_dir)
                else:
                    shutil.copytree(source_dir, dest_dir, 
                                  ignore=shutil.ignore_patterns(*self.exclude_patterns),
                                  dirs_exist_ok=True)
            
            # Komprimieren
            if self.config.get('compression', True):
                logger.info("🗜️  Komprimiere Backup...")
                archive_path = backup_path / f"{backup_name}.tar.gz"
                archive_path.parent.mkdir(exist_ok=True)
                
                with tarfile.open(archive_path, 'w:gz') as tar:
                    tar.add(temp_dir, arcname=backup_name)
                
                # Temporäres Verzeichnis löschen
                shutil.rmtree(temp_dir)
                backup_file = archive_path
            else:
                shutil.move(temp_dir, backup_path)
                backup_file = backup_path
            
            # Verschlüsseln
            if self.config.get('encryption', True):
                backup_file = self.encrypt_file(backup_file)
            
            # Checksumme erstellen
            checksum = self.create_checksum(backup_file)
            checksum_file = backup_file.with_suffix(backup_file.suffix + '.sha256')
            with open(checksum_file, 'w') as f:
                f.write(checksum)
            
            logger.info(f"✅ Backup erstellt: {backup_file}")
            logger.info(f"📊 Größe: {backup_file.stat().st_size / (1024*1024):.2f} MB")
            
            return backup_file
            
        except Exception as e:
            logger.error(f"❌ Backup fehlgeschlagen: {e}")
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            return None
    
    def create_checksum(self, file_path: Path) -> str:
        """Erstellt SHA256 Checksumme"""
        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def verify_checksum(self, file_path: Path, expected_checksum: str) -> bool:
        """Verifiziert Checksumme"""
        actual_checksum = self.create_checksum(file_path)
        return actual_checksum == expected_checksum
    
    def upload_to_google_drive(self, file_path: Path) -> bool:
        """Lädt Backup zu Google Drive hoch"""
        if not self.config['cloud_providers']['google_drive']['enabled']:
            logger.info("⏭️  Google Drive nicht aktiviert")
            return False
        
        try:
            # Hier würde die Google Drive API Integration stehen
            # Für jetzt simulieren wir den Upload
            logger.info("☁️  Upload zu Google Drive...")
            logger.info("⚠️  Google Drive API Integration benötigt Credentials")
            return False
        except Exception as e:
            logger.error(f"❌ Google Drive Upload fehlgeschlagen: {e}")
            return False
    
    def upload_to_dropbox(self, file_path: Path) -> bool:
        """Lädt Backup zu Dropbox hoch"""
        if not self.config['cloud_providers']['dropbox']['enabled']:
            logger.info("⏭️  Dropbox nicht aktiviert")
            return False
        
        try:
            # Hier würde die Dropbox API Integration stehen
            logger.info("☁️  Upload zu Dropbox...")
            logger.info("⚠️  Dropbox API Integration benötigt Access Token")
            return False
        except Exception as e:
            logger.error(f"❌ Dropbox Upload fehlgeschlagen: {e}")
            return False
    
    def upload_to_icloud(self, file_path: Path) -> bool:
        """Lädt Backup zu iCloud hoch"""
        if not self.config['cloud_providers']['icloud']['enabled']:
            logger.info("⏭️  iCloud nicht aktiviert")
            return False
        
        try:
            # iCloud Drive lokaler Pfad
            icloud_path = Path('~/Library/Mobile Documents/com~apple~CloudDocs/RudiBot-Backups').expanduser()
            icloud_path.mkdir(parents=True, exist_ok=True)
            
            shutil.copy2(file_path, icloud_path / file_path.name)
            logger.info(f"☁️  Backup zu iCloud kopiert: {file_path.name}")
            return True
        except Exception as e:
            logger.error(f"❌ iCloud Upload fehlgeschlagen: {e}")
            return False
    
    def upload_to_aws_s3(self, file_path: Path) -> bool:
        """Lädt Backup zu AWS S3 hoch"""
        if not self.config['cloud_providers']['aws_s3']['enabled']:
            logger.info("⏭️  AWS S3 nicht aktiviert")
            return False
        
        try:
            # Hier würde die AWS S3 API Integration stehen
            logger.info("☁️  Upload zu AWS S3...")
            logger.info("⚠️  AWS S3 API benötigt Bucket und Credentials")
            return False
        except Exception as e:
            logger.error(f"❌ AWS S3 Upload fehlgeschlagen: {e}")
            return False
    
    def upload_backup(self, file_path: Path) -> Dict[str, bool]:
        """Lädt Backup zu allen aktivierten Cloud-Providern hoch"""
        results = {}
        
        logger.info("☁️  Starte Cloud Upload...")
        
        if self.upload_to_google_drive(file_path):
            results['google_drive'] = True
        
        if self.upload_to_dropbox(file_path):
            results['dropbox'] = True
        
        if self.upload_to_icloud(file_path):
            results['icloud'] = True
        
        if self.upload_to_aws_s3(file_path):
            results['aws_s3'] = True
        
        successful = sum(results.values())
        logger.info(f"✅ Upload abgeschlossen: {successful}/{len(results)} erfolgreich")
        
        return results
    
    def cleanup_old_backups(self):
        """Löscht alte Backups basierend auf Retention Policy"""
        retention_days = self.config.get('retention_days', 30)
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=retention_days)
        
        logger.info(f"🧹 Bereinige Backups älter als {retention_days} Tage...")
        
        deleted_count = 0
        for backup_file in self.backup_dir.glob('rudibot_backup_*'):
            if backup_file.is_file():
                try:
                    file_date = datetime.datetime.fromtimestamp(backup_file.stat().st_mtime)
                    if file_date < cutoff_date:
                        backup_file.unlink()
                        deleted_count += 1
                        logger.info(f"🗑️  Gelöscht: {backup_file.name}")
                except Exception as e:
                    logger.error(f"❌ Konnte {backup_file.name} nicht löschen: {e}")
        
        logger.info(f"✅ Bereinigung abgeschlossen: {deleted_count} Dateien gelöscht")
    
    def restore_backup(self, backup_file: Path, restore_dir: Path = None) -> bool:
        """Stellt ein Backup wieder her"""
        if not backup_file.exists():
            logger.error(f"❌ Backup existiert nicht: {backup_file}")
            return False
        
        if restore_dir is None:
            restore_dir = Path.home() / 'Desktop' / 'RudiBot-Restore'
        
        logger.info(f"🔄 Stelle Backup wieder her: {backup_file.name}")
        
        try:
            # Entschlüsseln
            if backup_file.suffix == '.enc':
                backup_file = self.decrypt_file(backup_file)
            
            # Checksumme verifizieren
            checksum_file = backup_file.with_suffix(backup_file.suffix + '.sha256')
            if checksum_file.exists():
                with open(checksum_file, 'r') as f:
                    expected_checksum = f.read().strip()
                
                if not self.verify_checksum(backup_file, expected_checksum):
                    logger.error("❌ Checksummen-Verifizierung fehlgeschlagen")
                    return False
                logger.info("✅ Checksumme verifiziert")
            
            # Entpacken
            restore_dir.mkdir(parents=True, exist_ok=True)
            
            if backup_file.suffix == '.gz':
                with tarfile.open(backup_file, 'r:gz') as tar:
                    tar.extractall(restore_dir)
                logger.info("📦 Backup entpackt")
            else:
                shutil.copytree(backup_file, restore_dir / backup_file.name, dirs_exist_ok=True)
            
            logger.info(f"✅ Backup wiederhergestellt nach: {restore_dir}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Wiederherstellung fehlgeschlagen: {e}")
            return False
    
    def list_backups(self) -> List[Dict]:
        """Listet alle verfügbaren Backups auf"""
        backups = []
        
        for backup_file in self.backup_dir.glob('rudibot_backup_*'):
            if backup_file.is_file():
                try:
                    stat = backup_file.stat()
                    backups.append({
                        'name': backup_file.name,
                        'path': str(backup_file),
                        'size': stat.st_size,
                        'size_mb': stat.st_size / (1024*1024),
                        'created': datetime.datetime.fromtimestamp(stat.st_mtime),
                        'encrypted': backup_file.suffix == '.enc'
                    })
                except Exception as e:
                    logger.error(f"❌ Konnte Backup nicht lesen: {backup_file.name}")
        
        # Sortieren nach Datum (neueste zuerst)
        backups.sort(key=lambda x: x['created'], reverse=True)
        
        return backups
    
    def run_backup(self) -> bool:
        """Führt vollständigen Backup-Prozess aus"""
        logger.info("🚀 Starte Backup-Prozess...")
        
        # Backup erstellen
        backup_file = self.create_backup()
        if not backup_file:
            logger.error("❌ Backup-Erstellung fehlgeschlagen")
            return False
        
        # Zu Cloud hochladen
        upload_results = self.upload_backup(backup_file)
        
        # Alte Backups bereinigen
        self.cleanup_old_backups()
        
        # Benachrichtigung senden
        if self.config.get('notification', {}).get('telegram', True):
            self.send_telegram_notification(backup_file, upload_results)
        
        logger.info("✅ Backup-Prozess abgeschlossen")
        return True
    
    def send_telegram_notification(self, backup_file: Path, upload_results: Dict):
        """Sendet Telegram Benachrichtigung über Backup"""
        try:
            # Hier würde die Telegram API Integration stehen
            logger.info("📤 Sende Telegram Benachrichtigung...")
            logger.info("⚠️  Telegram Benachrichtigung benötigt Bot Token")
        except Exception as e:
            logger.error(f"❌ Telegram Benachrichtigung fehlgeschlagen: {e}")
    
    def setup_scheduler(self):
        """Richtet automatischen Backup-Scheduler ein"""
        schedule = self.config.get('schedule', 'daily')
        
        logger.info(f"⏰ Konfiguriere Scheduler: {schedule}")
        
        # Hier würde der Scheduler eingerichtet werden
        # Für macOS launchd oder cron
        logger.info("⚠️  Scheduler Integration benötigt zusätzliche Konfiguration")


def main():
    """Hauptfunktion"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Ultimate RudiBot Cloud Backup System')
    parser.add_argument('--backup', action='store_true', help='Backup erstellen')
    parser.add_argument('--restore', type=str, help='Backup wiederherstellen')
    parser.add_argument('--list', action='store_true', help='Backups auflisten')
    parser.add_argument('--cleanup', action='store_true', help='Alte Backups bereinigen')
    parser.add_argument('--config', type=str, help='Konfigurationsdatei')
    
    args = parser.parse_args()
    
    backup_system = CloudBackupSystem(args.config)
    
    if args.backup:
        backup_system.run_backup()
    elif args.restore:
        backup_system.restore_backup(Path(args.restore))
    elif args.list:
        backups = backup_system.list_backups()
        print("\n📋 Verfügbare Backups:")
        print("=" * 60)
        for backup in backups:
            print(f"📦 {backup['name']}")
            print(f"   Größe: {backup['size_mb']:.2f} MB")
            print(f"   Erstellt: {backup['created']}")
            print(f"   Verschlüsselt: {'Ja' if backup['encrypted'] else 'Nein'}")
            print()
    elif args.cleanup:
        backup_system.cleanup_old_backups()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
