#!/usr/bin/env python3
"""
Backup RudiBot Konfiguration zu GCP Cloud Storage
Verwendet die aktivierte storage-component.googleapis.com API
"""

import os
import sys
import json
import zipfile
from datetime import datetime
from pathlib import Path

# Import GCP configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from gcp_config import gcp_config

PROJECT_ID = gcp_config.project_id
BUCKET_NAME = f"rudibot-backups-{PROJECT_ID}"

def create_backup_archive():
    """Erstellt ein ZIP-Backup des Projekts"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"rudibot-backup-{timestamp}.zip"
    
    # Backup-Verzeichnis
    backup_dir = Path.home() / "RudiBot-Backups"
    backup_dir.mkdir(exist_ok=True)
    
    backup_path = backup_dir / backup_name
    
    # Projekt-Verzeichnis
    project_dir = Path("/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project")
    
    print(f"📦 Erstelle Backup: {backup_name}")
    print(f"📁 Projekt: {project_dir}")
    
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Wichtige Dateien sichern
        for pattern in [
            "RudiBot-Secure-API/**/*",
            "*.js",
            "*.py",
            "*.json",
            "*.md",
            "services/**/*",
            "templates/**/*"
        ]:
            for file_path in project_dir.glob(pattern):
                if file_path.is_file():
                    arcname = str(file_path.relative_to(project_dir))
                    zipf.write(file_path, arcname)
                    print(f"  ✅ {arcname}")
    
    size = backup_path.stat().st_size
    print(f"\n📊 Backup-Größe: {size / 1024:.2f} KB")
    
    return backup_path

def upload_to_gcs(backup_path):
    """Lädt Backup zu GCP Cloud Storage hoch"""
    print(f"\n☁️ Lade zu Cloud Storage hoch...")
    print(f"📦 Bucket: gs://{BUCKET_NAME}")
    print(f"🆔 Projekt: {PROJECT_ID}")
    
    # Bucket erstellen (falls nicht existiert)
    print(f"\n🔧 Erstelle/Prüfe Bucket...")
    os.system(f"gcloud storage buckets create gs://{BUCKET_NAME} --project={PROJECT_ID} --location=europe-west3 2>/dev/null || echo 'Bucket existiert bereits'")
    
    # Backup hochladen
    print(f"\n📤 Upload gestartet...")
    cmd = f"gcloud storage cp {backup_path} gs://{BUCKET_NAME}/backups/"
    result = os.system(cmd)
    
    if result == 0:
        print(f"\n✅ Backup erfolgreich hochgeladen!")
        print(f"🔗 gs://{BUCKET_NAME}/backups/{backup_path.name}")
        return True
    else:
        print(f"\n❌ Upload fehlgeschlagen")
        return False

def list_backups():
    """Zeigt alle Backups im Bucket an"""
    print(f"\n📋 Backups in gs://{BUCKET_NAME}/backups/:")
    os.system(f"gcloud storage ls gs://{BUCKET_NAME}/backups/")

def main():
    print("=" * 60)
    print("🚀 RudiBot Cloud Storage Backup")
    print("=" * 60)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"☁️ Projekt: {PROJECT_ID}")
    print()
    
    # Backup erstellen
    backup_path = create_backup_archive()
    
    # Zu Cloud Storage hochladen
    upload_to_gcs(backup_path)
    
    # Liste anzeigen
    list_backups()
    
    print("\n" + "=" * 60)
    print("✅ Backup abgeschlossen!")
    print("=" * 60)

if __name__ == "__main__":
    main()
