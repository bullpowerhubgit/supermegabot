#!/usr/bin/env python3
"""
RudiBot Cloud Backup & Sync
Automatisches Backup zu allen verbundenen Cloud-Speichern
"""

import os
import sys
import shutil
import json
import subprocess
from datetime import datetime
from pathlib import Path

# Import GCP configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from gcp_config import gcp_config

class RudiBotBackup:
    def __init__(self):
        self.home = os.path.expanduser('~')
        self.project_dir = '/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project'
        self.backup_dir = os.path.join(self.project_dir, 'backups')
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.gcp_project_id = gcp_config.project_id
        self.gcp_apis = gcp_config.api_list
        
        # Cloud-Backup-Ziele finden
        self.cloud_targets = self.find_cloud_storage()
        
    def find_cloud_storage(self):
        """Finde alle verbundenen Cloud-Speicher"""
        targets = {}
        
        # iCloud Drive
        icloud = os.path.join(self.home, 'Library/Mobile Documents/com~apple~CloudDocs')
        if os.path.exists(icloud):
            targets['icloud'] = icloud
            
        # Google Drive
        gdrive = os.path.join(self.home, 'Library/CloudStorage')
        if os.path.exists(gdrive):
            # Suche Google Drive Ordner
            for item in os.listdir(gdrive) if os.path.isdir(gdrive) else []:
                if 'GoogleDrive' in item or 'google' in item.lower():
                    targets['google'] = os.path.join(gdrive, item)
                    break
                    
        # Dropbox
        dropbox = os.path.join(self.home, 'Dropbox')
        if os.path.exists(dropbox):
            targets['dropbox'] = dropbox
            
        # OneDrive
        onedrive = os.path.join(self.home, 'Library/CloudStorage/OneDrive')
        if os.path.exists(onedrive):
            targets['onedrive'] = onedrive
            
        return targets
    
    def create_local_backup(self):
        """Erstelle lokales Backup"""
        print(f"📦 Erstelle Backup vom {self.timestamp}...")
        
        backup_path = os.path.join(self.backup_dir, f'backup_{self.timestamp}')
        os.makedirs(backup_path, exist_ok=True)
        
        # Wichtige Dateien kopieren
        files_to_backup = [
            'watchdog.js',
            'mega-server.py',
            'mega-dashboard.html',
            'API_CONFIG_TEMPLATE.env',
            'package.json',
            'docker-compose.yml',
            'auto-start.sh',
            'com.supermegabot.watchdog.plist',
            'com.supermegabot.launcher.plist'
        ]
        
        for file in files_to_backup:
            src = os.path.join(self.project_dir, file)
            if os.path.exists(src):
                shutil.copy2(src, backup_path)
                print(f"  ✅ {file}")
        
        # Services Ordner
        services_src = os.path.join(self.project_dir, 'services')
        if os.path.exists(services_src):
            services_dst = os.path.join(backup_path, 'services')
            shutil.copytree(services_src, services_dst, dirs_exist_ok=True)
            print(f"  ✅ services/")
        
        # Templates
        templates_src = os.path.join(self.project_dir, 'templates')
        if os.path.exists(templates_src):
            templates_dst = os.path.join(backup_path, 'templates')
            shutil.copytree(templates_src, templates_dst, dirs_exist_ok=True)
            print(f"  ✅ templates/")
        
        # Backup-Info erstellen
        info = {
            'timestamp': self.timestamp,
            'date': datetime.now().isoformat(),
            'files_backed_up': len(files_to_backup),
            'cloud_targets': list(self.cloud_targets.keys())
        }
        
        with open(os.path.join(backup_path, 'backup-info.json'), 'w') as f:
            json.dump(info, f, indent=2)
        
        print(f"📁 Lokales Backup: {backup_path}")
        return backup_path
    
    def sync_to_cloud(self, backup_path):
        """Synchronisiere Backup zu allen Cloud-Speichern"""
        results = {}
        
        for cloud_name, cloud_path in self.cloud_targets.items():
            try:
                cloud_backup_dir = os.path.join(cloud_path, 'RudiBot-Backups')
                os.makedirs(cloud_backup_dir, exist_ok=True)
                
                # Kopiere Backup
                cloud_backup = os.path.join(cloud_backup_dir, f'backup_{self.timestamp}')
                shutil.copytree(backup_path, cloud_backup, dirs_exist_ok=True)
                
                # Erstelle auch "latest" Link
                latest_link = os.path.join(cloud_backup_dir, 'latest')
                if os.path.exists(latest_link):
                    if os.path.islink(latest_link):
                        os.remove(latest_link)
                    else:
                        shutil.rmtree(latest_link)
                
                # Kopiere als latest
                latest_copy = os.path.join(cloud_backup_dir, 'latest')
                if os.path.exists(latest_copy):
                    shutil.rmtree(latest_copy)
                shutil.copytree(backup_path, latest_copy, dirs_exist_ok=True)
                
                results[cloud_name] = {
                    'status': 'success',
                    'path': cloud_backup
                }
                print(f"  ☁️  {cloud_name.upper()}: ✅ Synchronisiert")
                
            except Exception as e:
                results[cloud_name] = {
                    'status': 'failed',
                    'error': str(e)
                }
                print(f"  ☁️  {cloud_name.upper()}: ❌ Fehler - {e}")
        
        return results
    
    def cleanup_old_backups(self, keep_count=5):
        """Lösche alte Backups, behalte die neuesten"""
        print("\n🧹 Bereinige alte Backups...")
        
        if not os.path.exists(self.backup_dir):
            return
            
        backups = sorted([d for d in os.listdir(self.backup_dir) 
                         if d.startswith('backup_')], reverse=True)
        
        for old_backup in backups[keep_count:]:
            old_path = os.path.join(self.backup_dir, old_backup)
            try:
                shutil.rmtree(old_path)
                print(f"  🗑️  Gelöscht: {old_backup}")
            except Exception as e:
                print(f"  ⚠️  Konnte nicht löschen: {old_backup} - {e}")
    
    def run(self):
        """Führe komplettes Backup durch"""
        print("=" * 50)
        print("🤖 RudiBot Cloud Backup")
        print("=" * 50)
        
        # Zeige verfügbare Cloud-Speicher
        print(f"\n☁️  Gefundene Cloud-Speicher:")
        if self.cloud_targets:
            for name in self.cloud_targets:
                print(f"  ✅ {name.upper()}")
        else:
            print(f"  ⚠️  Keine Cloud-Speicher gefunden")
            print(f"     Installiere: iCloud, Google Drive, Dropbox oder OneDrive")
        
        # Lokales Backup
        backup_path = self.create_local_backup()
        
        # Cloud-Sync
        if self.cloud_targets:
            print(f"\n🔄 Synchronisiere zu Cloud...")
            results = self.sync_to_cloud(backup_path)
            
            successful = sum(1 for r in results.values() if r['status'] == 'success')
            print(f"\n📊 Ergebnis: {successful}/{len(results)} Cloud-Speicher synchronisiert")
        
        # Cleanup
        self.cleanup_old_backups()
        
        print("\n✅ Backup abgeschlossen!")
        print(f"📁 Lokales Backup: {backup_path}")
        
        return backup_path

if __name__ == '__main__':
    backup = RudiBotBackup()
    backup.run()
