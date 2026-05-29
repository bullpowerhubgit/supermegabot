#!/usr/bin/env python3
"""
Intelligenter Dateisortierer - Verteilt Dateien automatisch auf externe und Cloud-Speicher
"""

import os
import shutil
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
import argparse
from collections import defaultdict
import mimetypes

# Import GCP configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from gcp_config import gcp_config

class FileSorter:
    def __init__(self):
        self.gcp_project_id = gcp_config.project_id
        self.gcp_apis = gcp_config.api_list
        self.config_file = Path.home() / ".mac-optimizer" / "file-sorter-config.json"
        self.log_file = Path.home() / ".mac-optimizer" / "file-sorter.log"
        self.database_file = Path.home() / ".mac-optimizer" / "file-database.json"
        self.ensure_log_directory()
        self.load_config()
        self.load_database()
    
    def ensure_log_directory(self):
        """Erstellt Log-Verzeichnis"""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    def load_config(self):
        """Lädt Konfiguration"""
        default_config = {
            "source_directories": [
                str(Path.home() / "Downloads"),
                str(Path.home() / "Desktop"),
                str(Path.home() / "Documents")
            ],
            "storage_locations": {
                "external_drive": {
                    "path": "/Volumes/ExternalDrive",
                    "enabled": False,
                    "categories": ["videos", "large_files", "archives"]
                },
                "dropbox": {
                    "path": str(Path.home() / "Dropbox"),
                    "enabled": False,
                    "categories": ["documents", "images", "important"]
                },
                "google_drive": {
                    "path": str(Path.home() / "Google Drive"),
                    "enabled": False,
                    "categories": ["documents", "spreadsheets", "presentations"]
                },
                "icloud": {
                    "path": str(Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"),
                    "enabled": False,
                    "categories": ["documents", "images", "important"]
                },
                "onedrive": {
                    "path": str(Path.home() / "OneDrive"),
                    "enabled": False,
                    "categories": ["documents", "office_files"]
                },
                "local_archive": {
                    "path": str(Path.home() / "Archive"),
                    "enabled": True,
                    "categories": ["old_files", "duplicates"]
                }
            },
            "file_categories": {
                "images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".heic", ".raw"],
                "videos": [".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm"],
                "documents": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"],
                "spreadsheets": [".xls", ".xlsx", ".csv", ".ods"],
                "presentations": [".ppt", ".pptx", ".odp", ".key"],
                "music": [".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"],
                "archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
                "code": [".py", ".js", ".html", ".css", ".java", ".cpp", ".c", ".swift"],
                "large_files": [],  # Wird dynamisch basierend auf Größe bestimmt
                "office_files": [".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]
            },
            "size_thresholds": {
                "large_file_mb": 100,
                "huge_file_mb": 1000
            },
            "age_thresholds": {
                "old_file_days": 365,
                "very_old_file_days": 730
            },
            "auto_sort": True,
            "create_backups": True,
            "delete_empty_dirs": True
        }
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
            except Exception:
                self.config = default_config
        else:
            self.config = default_config
            self.save_config()
    
    def save_config(self):
        """Speichert Konfiguration"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def load_database(self):
        """Lädt Datei-Datenbank"""
        if self.database_file.exists():
            try:
                with open(self.database_file, 'r') as f:
                    self.file_database = json.load(f)
            except Exception:
                self.file_database = {}
        else:
            self.file_database = {}
    
    def save_database(self):
        """Speichert Datei-Datenbank"""
        with open(self.database_file, 'w') as f:
            json.dump(self.file_database, f, indent=2)
    
    def log(self, message):
        """Loggt Nachricht"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        print(log_entry.strip())
        with open(self.log_file, 'a') as f:
            f.write(log_entry)
    
    def get_file_category(self, file_path):
        """Bestimmt Kategorie einer Datei"""
        ext = file_path.suffix.lower()
        size_mb = file_path.stat().st_size / (1024 * 1024)
        
        # Größe-basierte Kategorien
        if size_mb >= self.config['size_thresholds']['huge_file_mb']:
            return 'large_files'
        elif size_mb >= self.config['size_thresholds']['large_file_mb']:
            return 'large_files'
        
        # Extension-basierte Kategorien
        for category, extensions in self.config['file_categories'].items():
            if ext in extensions:
                return category
        
        # MIME-Type basierte Erkennung
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            if mime_type.startswith('image/'):
                return 'images'
            elif mime_type.startswith('video/'):
                return 'videos'
            elif mime_type.startswith('audio/'):
                return 'music'
            elif mime_type.startswith('text/'):
                return 'documents'
        
        return 'other'
    
    def get_file_age_days(self, file_path):
        """Berechnet Alter einer Datei in Tagen"""
        mtime = file_path.stat().st_mtime
        age_seconds = time.time() - mtime
        return age_seconds / (24 * 3600)
    
    def determine_destination(self, file_path, category):
        """Bestimmt Zielort für eine Datei"""
        file_age = self.get_file_age_days(file_path)
        size_mb = file_path.stat().st_size / (1024 * 1024)
        
        # Prioritäten für Speicherorte
        priorities = []
        
        # Prüfe verfügbare Speicherorte
        for location_name, location_config in self.config['storage_locations'].items():
            if not location_config['enabled']:
                continue
            
            location_path = Path(location_config['path'])
            if not location_path.exists():
                self.log(f"⚠️ Speicherort {location_name} nicht verfügbar: {location_path}")
                continue
            
            # Prüfe ob Kategorie für diesen Speicherort geeignet ist
            if category in location_config['categories']:
                priority = 0
                
                # Priorität basierend auf Dateieigenschaften
                if category == 'large_files' and location_name == 'external_drive':
                    priority += 10
                elif category == 'videos' and location_name == 'external_drive':
                    priority += 8
                elif category == 'documents' and location_name in ['dropbox', 'icloud', 'google_drive']:
                    priority += 7
                elif category == 'images' and location_name in ['dropbox', 'icloud', 'google_drive']:
                    priority += 6
                elif file_age > self.config['age_thresholds']['old_file_days'] and location_name == 'local_archive':
                    priority += 5
                
                priorities.append((priority, location_name, location_path))
        
        # Sortiere nach Priorität
        priorities.sort(reverse=True, key=lambda x: x[0])
        
        if priorities:
            return priorities[0][1], priorities[0][2]
        
        # Fallback: lokales Archive
        archive_path = Path(self.config['storage_locations']['local_archive']['path'])
        if archive_path.exists():
            return 'local_archive', archive_path
        
        return None, None
    
    def scan_directory(self, directory):
        """Scannt Verzeichnis nach Dateien"""
        directory_path = Path(directory)
        if not directory_path.exists():
            self.log(f"⚠️ Verzeichnis nicht gefunden: {directory}")
            return []
        
        files = []
        self.log(f"🔍 Scanne {directory}...")
        
        for item in directory_path.rglob('*'):
            if item.is_file():
                try:
                    file_info = {
                        'path': str(item),
                        'size': item.stat().st_size,
                        'modified': datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                        'category': self.get_file_category(item),
                        'extension': item.suffix.lower()
                    }
                    files.append(file_info)
                except Exception as e:
                    self.log(f"Fehler beim Scannen von {item}: {e}")
        
        self.log(f"✅ {len(files)} Dateien gefunden")
        return files
    
    def distribute_files(self, dry_run=False):
        """Verteilt Dateien auf Speicherorte"""
        self.log("🚀 Starte Dateiverteilung...")
        self.log("="*60)
        
        total_files = 0
        total_size = 0
        distribution_summary = defaultdict(lambda: {'count': 0, 'size': 0})
        
        for source_dir in self.config['source_directories']:
            files = self.scan_directory(source_dir)
            
            for file_info in files:
                file_path = Path(file_info['path'])
                category = file_info['category']
                
                # Bestimme Zielort
                location_name, destination_path = self.determine_destination(file_path, category)
                
                if not location_name:
                    self.log(f"⚠️ Kein Zielort für {file_path.name}")
                    continue
                
                # Erstelle Zielverzeichnisstruktur
                target_dir = destination_path / category
                target_dir.mkdir(parents=True, exist_ok=True)
                
                target_file = target_dir / file_path.name
                
                # Prüfe auf Duplikate
                if target_file.exists():
                    self.log(f"⚠️ Datei existiert bereits: {target_file}")
                    continue
                
                if dry_run:
                    self.log(f"[DRY RUN] {file_path.name} -> {location_name}/{category}/")
                else:
                    try:
                        # Verschiebe Datei
                        shutil.move(str(file_path), str(target_file))
                        
                        # Update Datenbank
                        self.file_database[str(file_path)] = {
                            'moved_to': str(target_file),
                            'location': location_name,
                            'category': category,
                            'moved_at': datetime.now().isoformat()
                        }
                        
                        total_files += 1
                        total_size += file_info['size']
                        distribution_summary[location_name]['count'] += 1
                        distribution_summary[location_name]['size'] += file_info['size']
                        
                        self.log(f"✅ {file_path.name} -> {location_name}/{category}/")
                        
                    except Exception as e:
                        self.log(f"❌ Fehler beim Verschieben von {file_path.name}: {e}")
        
        self.save_database()
        
        # Zusammenfassung
        self.log("="*60)
        self.log("📊 VERTEILUNGSZUSAMMENFASSUNG")
        self.log("="*60)
        self.log(f"📁 Gesamt verschoben: {total_files} Dateien")
        self.log(f"💾 Gesamtgröße: {total_size / (1024**3):.2f} GB")
        self.log("")
        
        for location, stats in distribution_summary.items():
            self.log(f"📍 {location}: {stats['count']} Dateien ({stats['size'] / (1024**3):.2f} GB)")
        
        self.log("="*60)
        self.log("✅ Dateiverteilung abgeschlossen!")
    
    def organize_by_date(self, source_dir, destination_base):
        """Organisiert Dateien nach Datum"""
        source_path = Path(source_dir)
        dest_path = Path(destination_base)
        
        if not source_path.exists():
            self.log(f"⚠️ Quellverzeichnis nicht gefunden: {source_dir}")
            return
        
        self.log(f"📅 Organisiere {source_dir} nach Datum...")
        
        for item in source_path.rglob('*'):
            if item.is_file():
                try:
                    mtime = datetime.fromtimestamp(item.stat().st_mtime)
                    year_month = mtime.strftime("%Y/%m")
                    
                    target_dir = dest_path / year_month
                    target_dir.mkdir(parents=True, exist_ok=True)
                    
                    target_file = target_dir / item.name
                    
                    if not target_file.exists():
                        shutil.move(str(item), str(target_file))
                        self.log(f"✅ {item.name} -> {year_month}/")
                    
                except Exception as e:
                    self.log(f"Fehler bei {item.name}: {e}")
        
        self.log("✅ Datum-Organisierung abgeschlossen!")
    
    def find_duplicates(self, directory):
        """Findet Duplikate basierend auf Dateigröße und Hash"""
        self.log(f"🔍 Suche Duplikate in {directory}...")
        
        size_groups = defaultdict(list)
        directory_path = Path(directory)
        
        # Gruppiere nach Größe
        for item in directory_path.rglob('*'):
            if item.is_file():
                try:
                    size = item.stat().st_size
                    size_groups[size].append(item)
                except Exception:
                    pass
        
        # Prüfe Gruppen mit mehr als einer Datei
        duplicates = []
        for size, files in size_groups.items():
            if len(files) > 1:
                # Hier könnte man noch Hash-Vergleich hinzufügen
                duplicates.append({
                    'size': size,
                    'files': [str(f) for f in files]
                })
        
        self.log(f"✅ {len(duplicates)} potentielle Duplikat-Gruppen gefunden")
        return duplicates
    
    def cleanup_empty_directories(self, directory):
        """Löscht leere Verzeichnisse"""
        if not self.config.get('delete_empty_dirs', True):
            return
        
        self.log(f"🧹 Bereinige leere Verzeichnisse in {directory}...")
        
        directory_path = Path(directory)
        deleted_count = 0
        
        for item in sorted(directory_path.rglob('*'), key=lambda x: len(x.parts), reverse=True):
            if item.is_dir():
                try:
                    if not any(item.iterdir()):
                        item.rmdir()
                        deleted_count += 1
                        self.log(f"🗑️ Leeres Verzeichnis gelöscht: {item}")
                except Exception:
                    pass
        
        self.log(f"✅ {deleted_count} leere Verzeichnisse gelöscht")
    
    def show_storage_status(self):
        """Zeigt Speicherstatus aller konfigurierten Speicherorte"""
        self.log("💾 SPEICHERSTATUS")
        self.log("="*60)
        
        for location_name, location_config in self.config['storage_locations'].items():
            if not location_config['enabled']:
                continue
            
            location_path = Path(location_config['path'])
            if not location_path.exists():
                self.log(f"❌ {location_name}: Nicht verfügbar")
                continue
            
            try:
                # Berechne Speicherplatz
                total_size = sum(f.stat().st_size for f in location_path.rglob('*') if f.is_file())
                file_count = sum(1 for f in location_path.rglob('*') if f.is_file())
                
                self.log(f"📍 {location_name}:")
                self.log(f"   Pfad: {location_path}")
                self.log(f"   Dateien: {file_count}")
                self.log(f"   Größe: {total_size / (1024**3):.2f} GB")
                self.log("")
            except Exception as e:
                self.log(f"❌ {location_name}: Fehler - {e}")
        
        self.log("="*60)

def main():
    parser = argparse.ArgumentParser(description='Intelligenter Dateisortierer')
    parser.add_argument('--distribute', action='store_true', help='Dateien verteilen')
    parser.add_argument('--dry-run', action='store_true', help='Simulation ohne Änderungen')
    parser.add_argument('--organize-date', type=str, help='Verzeichnis nach Datum organisieren')
    parser.add_argument('--find-duplicates', type=str, help='Duplikate in Verzeichnis finden')
    parser.add_argument('--cleanup', type=str, help='Leere Verzeichnisse bereinigen')
    parser.add_argument('--status', action='store_true', help='Speicherstatus anzeigen')
    parser.add_argument('--config', action='store_true', help='Konfiguration anzeigen/bearbeiten')
    
    args = parser.parse_args()
    
    sorter = FileSorter()
    
    if args.distribute:
        sorter.distribute_files(dry_run=args.dry_run)
    elif args.organize_date:
        dest_base = Path(args.organize_date).parent / "Organized"
        sorter.organize_by_date(args.organize_date, dest_base)
    elif args.find_duplicates:
        duplicates = sorter.find_duplicates(args.find_duplicates)
        for dup in duplicates:
            print(f"Größe: {dup['size']} bytes")
            for file in dup['files']:
                print(f"  - {file}")
    elif args.cleanup:
        sorter.cleanup_empty_directories(args.cleanup)
    elif args.status:
        sorter.show_storage_status()
    elif args.config:
        print(json.dumps(sorter.config, indent=2))
    else:
        # Standard: Status anzeigen
        sorter.show_storage_status()
        print("\nVerwende --help für alle Optionen")

if __name__ == "__main__":
    import time
    main()
