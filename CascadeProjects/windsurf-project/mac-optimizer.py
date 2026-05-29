#!/usr/bin/env python3
"""
Mac Performance Optimizer - Automatische Systemüberwachung und Optimierung
"""

import os
import subprocess
import time
import json
import shutil
from datetime import datetime
from pathlib import Path
import argparse

# Import GCP configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from gcp_config import gcp_config

class MacOptimizer:
    def __init__(self):
        self.gcp_project_id = gcp_config.project_id
        self.gcp_apis = gcp_config.api_list
        self.log_file = Path.home() / ".mac-optimizer" / "optimizer.log"
        self.config_file = Path.home() / ".mac-optimizer" / "config.json"
        self.ensure_log_directory()
        self.load_config()
    
    def ensure_log_directory(self):
        """Erstellt Log-Verzeichnis wenn nicht vorhanden"""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    def load_config(self):
        """Lädt Konfiguration"""
        default_config = {
            "auto_cleanup": True,
            "cleanup_interval_hours": 24,
            "max_cpu_usage": 80,
            "max_memory_usage": 85,
            "enable_process_monitoring": True,
            "cleanup_cache": True,
            "cleanup_logs": True,
            "cleanup_temp": True
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
    
    def log(self, message):
        """Loggt Nachricht"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        print(log_entry.strip())
        with open(self.log_file, 'a') as f:
            f.write(log_entry)
    
    def get_system_stats(self):
        """Holt Systemstatistiken"""
        stats = {}
        
        # CPU Auslastung
        try:
            cpu_output = subprocess.run(['top', '-l', '1', '-n', '0'], 
                                       capture_output=True, text=True)
            for line in cpu_output.stdout.split('\n'):
                if 'CPU usage:' in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if 'user' in part:
                            stats['cpu_user'] = float(parts[i-1].replace('%', ''))
                        elif 'sys' in part:
                            stats['cpu_sys'] = float(parts[i-1].replace('%', ''))
                        elif 'idle' in part:
                            stats['cpu_idle'] = float(parts[i-1].replace('%', ''))
                    stats['cpu_total'] = 100 - stats.get('cpu_idle', 0)
                    break
        except Exception as e:
            self.log(f"Fehler beim Lesen der CPU: {e}")
            stats['cpu_total'] = 0
        
        # RAM Auslastung
        try:
            mem_output = subprocess.run(['vm_stat'], capture_output=True, text=True)
            mem_info = {}
            page_size = 4096  # Standard page size in bytes
            
            for line in mem_output.stdout.split('\n'):
                if ':' in line:
                    key, value = line.split(':')
                    # Extrahiere page size aus der ersten Zeile
                    if 'page size' in line:
                        try:
                            page_size = int(value.strip().split()[0])
                        except Exception:
                            page_size = 4096
                    else:
                        # Entferne Punkte und konvertiere zu int
                        clean_value = value.strip().replace('.', '')
                        if clean_value.isdigit():
                            mem_info[key.strip()] = int(clean_value)
            
            free_pages = mem_info.get('Pages free', 0)
            active_pages = mem_info.get('Pages active', 0)
            inactive_pages = mem_info.get('Pages inactive', 0)
            wired_pages = mem_info.get('Pages wired', 0)
            speculative_pages = mem_info.get('Pages speculative', 0)
            
            total_pages = free_pages + active_pages + inactive_pages + wired_pages + speculative_pages
            used_pages = total_pages - free_pages
            
            stats['memory_used_percent'] = (used_pages / total_pages * 100) if total_pages > 0 else 0
            stats['memory_free_gb'] = (free_pages * page_size) / (1024**3)
            stats['memory_total_gb'] = (total_pages * page_size) / (1024**3)
        except Exception as e:
            self.log(f"Fehler beim Lesen des RAM: {e}")
            stats['memory_used_percent'] = 0
            stats['memory_free_gb'] = 0
            stats['memory_total_gb'] = 0
        
        # Festplattenspeicher
        try:
            disk_output = subprocess.run(['df', '-h', '/'], capture_output=True, text=True)
            lines = disk_output.stdout.split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                stats['disk_used_percent'] = int(parts[4].replace('%', ''))
                stats['disk_free_gb'] = parts[3]
                stats['disk_total_gb'] = parts[1]
        except Exception as e:
            self.log(f"Fehler beim Lesen der Festplatte: {e}")
            stats['disk_used_percent'] = 0
        
        return stats
    
    def print_system_stats(self, stats):
        """Zeigt Systemstatistiken an"""
        print("\n" + "="*50)
        print("📊 SYSTEM STATUS")
        print("="*50)
        print(f"💻 CPU Auslastung: {stats.get('cpu_total', 0):.1f}%")
        print(f"🧠 RAM Auslastung: {stats.get('memory_used_percent', 0):.1f}%")
        print(f"   Frei: {stats.get('memory_free_gb', 0):.2f} GB / {stats.get('memory_total_gb', 0):.2f} GB")
        print(f"💾 Festplatte: {stats.get('disk_used_percent', 0)}% belegt")
        print(f"   Frei: {stats.get('disk_free_gb', 'N/A')} / {stats.get('disk_total_gb', 'N/A')}")
        print("="*50 + "\n")
    
    def cleanup_cache(self):
        """Bereinigt Cache-Dateien"""
        if not self.config.get('cleanup_cache', True):
            return
        
        self.log("🧹 Bereinige Cache...")
        
        cache_dirs = [
            Path.home() / "Library" / "Caches",
            Path("/Library/Caches"),
            Path("/System/Library/Caches")
        ]
        
        total_freed = 0
        for cache_dir in cache_dirs:
            if cache_dir.exists():
                try:
                    size_before = sum(f.stat().st_size for f in cache_dir.rglob('*') if f.is_file())
                    # Lösche alte Cache-Dateien (älter als 7 Tage)
                    for item in cache_dir.rglob('*'):
                        if item.is_file():
                            try:
                                if (time.time() - item.stat().st_mtime) > (7 * 24 * 3600):
                                    item.unlink()
                            except Exception:
                                pass
                    size_after = sum(f.stat().st_size for f in cache_dir.rglob('*') if f.is_file())
                    total_freed += (size_before - size_after)
                except Exception as e:
                    self.log(f"Fehler beim Bereinigen von {cache_dir}: {e}")
        
        self.log(f"✅ Cache bereinigt: {total_freed / (1024**2):.2f} MB freigegeben")
    
    def cleanup_logs(self):
        """Bereinigt Log-Dateien"""
        if not self.config.get('cleanup_logs', True):
            return
        
        self.log("🧹 Bereinige Logs...")
        
        log_dirs = [
            Path("/var/log"),
            Path.home() / "Library" / "Logs"
        ]
        
        for log_dir in log_dirs:
            if log_dir.exists():
                try:
                    for item in log_dir.rglob('*.log'):
                        if item.is_file():
                            try:
                                if (time.time() - item.stat().st_mtime) > (30 * 24 * 3600):  # 30 Tage
                                    item.unlink()
                            except Exception:
                                pass
                except Exception as e:
                    self.log(f"Fehler beim Bereinigen von {log_dir}: {e}")
        
        self.log("✅ Logs bereinigt")
    
    def cleanup_temp(self):
        """Bereinigt temporäre Dateien"""
        if not self.config.get('cleanup_temp', True):
            return
        
        self.log("🧹 Bereinige temporäre Dateien...")
        
        temp_dirs = [
            Path("/tmp"),
            Path("/var/tmp"),
            Path.home() / "Library" / "Application Support" / "CrashReporter"
        ]
        
        for temp_dir in temp_dirs:
            if temp_dir.exists():
                try:
                    for item in temp_dir.iterdir():
                        if item.is_file():
                            try:
                                if (time.time() - item.stat().st_mtime) > (7 * 24 * 3600):
                                    item.unlink()
                            except Exception:
                                pass
                except Exception as e:
                    self.log(f"Fehler beim Bereinigen von {temp_dir}: {e}")
        
        self.log("✅ Temporäre Dateien bereinigt")
    
    def cleanup_downloads(self):
        """Bereinigt Downloads-Ordner"""
        downloads_dir = Path.home() / "Downloads"
        if not downloads_dir.exists():
            return
        
        self.log("🧹 Bereinige Downloads...")
        
        try:
            deleted_count = 0
            for item in downloads_dir.iterdir():
                if item.is_file():
                    try:
                        if (time.time() - item.stat().st_mtime) > (30 * 24 * 3600):  # 30 Tage
                            item.unlink()
                            deleted_count += 1
                    except Exception:
                        pass
            self.log(f"✅ {deleted_count} alte Dateien aus Downloads gelöscht")
        except Exception as e:
            self.log(f"Fehler beim Bereinigen von Downloads: {e}")
    
    def empty_trash(self):
        """Leert den Papierkorb"""
        self.log("🗑️ Leere Papierkorb...")
        
        try:
            subprocess.run(['rm', '-rf', Path.home() / '.Trash' / '*'], 
                          shell=True, capture_output=True)
            self.log("✅ Papierkorb geleert")
        except Exception as e:
            self.log(f"Fehler beim Leeren des Papierkorbs: {e}")
    
    def flush_dns_cache(self):
        """Leert DNS-Cache"""
        self.log("🌐 Leere DNS-Cache...")
        
        try:
            r1 = subprocess.run(['sudo', '-n', 'dscacheutil', '-flushcache'], capture_output=True, timeout=3)
            r2 = subprocess.run(['sudo', '-n', 'killall', '-HUP', 'mDNSResponder'], capture_output=True, timeout=3)
            if r1.returncode == 0 or r2.returncode == 0:
                self.log("✅ DNS-Cache geleert")
            else:
                self.log("⚠️ DNS-Cache leeren uebersprungen (sudo erforderlich)")
        except Exception as e:
            self.log(f"⚠️ DNS-Cache leeren uebersprungen: {e}")
    
    def get_running_processes(self):
        """Holt laufende Prozesse"""
        try:
            output = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
            processes = []
            for line in output.stdout.split('\n')[1:]:
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    processes.append({
                        'user': parts[0],
                        'pid': parts[1],
                        'cpu': float(parts[2]),
                        'mem': float(parts[3]),
                        'command': parts[10]
                    })
            return processes
        except Exception as e:
            self.log(f"Fehler beim Abrufen der Prozesse: {e}")
            return []
    
    def optimize_memory(self):
        """Optimiert Speicher"""
        self.log("🧠 Optimiere Speicher...")
        
        try:
            # Speicherdruck reduzieren
            subprocess.run(['purge'], capture_output=True)
            self.log("✅ Speicher optimiert")
        except Exception as e:
            self.log(f"Fehler beim Optimieren des Speichers: {e}")
    
    def disable_unnecessary_launch_agents(self):
        """Deaktiviert unnötige Launch Agents"""
        self.log("🚫 Deaktiviere unnötige Launch Agents...")
        
        # Liste von sicheren zu deaktivierenden Launch Agents
        safe_to_disable = [
            "com.apple.advisoryd",  # Apple Advisory
            "com.apple.apsd",  # Apple Push Service
            "com.apple.cloudd",  # iCloud (optional)
        ]
        
        for agent in safe_to_disable:
            try:
                agent_path = Path.home() / "Library" / "LaunchAgents" / f"{agent}.plist"
                if agent_path.exists():
                    subprocess.run(['launchctl', 'unload', str(agent_path)], 
                                  capture_output=True)
                    self.log(f"✅ {agent} deaktiviert")
            except Exception as e:
                pass  # Nicht kritisch
    
    def run_full_optimization(self):
        """Führt vollständige Optimierung durch"""
        self.log("🚀 Starte vollständige Optimierung...")
        self.log("="*50)
        
        # Systemstatus vorher
        stats_before = self.get_system_stats()
        self.print_system_stats(stats_before)
        
        # Bereinigung
        self.cleanup_cache()
        self.cleanup_logs()
        self.cleanup_temp()
        self.cleanup_downloads()
        self.empty_trash()
        self.flush_dns_cache()
        
        # Optimierung
        self.optimize_memory()
        self.disable_unnecessary_launch_agents()
        
        # Systemstatus nachher
        stats_after = self.get_system_stats()
        self.print_system_stats(stats_after)
        
        self.log("="*50)
        self.log("✅ Optimierung abgeschlossen!")
    
    def monitor_mode(self, interval_minutes=5):
        """Überwachungsmodus"""
        self.log(f"👁️ Starte Überwachungsmodus (Intervall: {interval_minutes} Minuten)")
        self.log("Drücke STRG+C zum Beenden")
        
        try:
            while True:
                stats = self.get_system_stats()
                self.print_system_stats(stats)
                
                # Automatische Optimierung bei hoher Auslastung
                if stats.get('cpu_total', 0) > self.config.get('max_cpu_usage', 80):
                    self.log("⚠️ Hohe CPU-Auslastung erkannt - starte Optimierung")
                    self.optimize_memory()
                
                if stats.get('memory_used_percent', 0) > self.config.get('max_memory_usage', 85):
                    self.log("⚠️ Hohe RAM-Auslastung erkannt - starte Optimierung")
                    self.optimize_memory()
                
                time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            self.log("👋 Überwachungsmodus beendet")

def main():
    parser = argparse.ArgumentParser(description='Mac Performance Optimizer')
    parser.add_argument('--monitor', action='store_true', help='Überwachungsmodus')
    parser.add_argument('--interval', type=int, default=5, help='Intervall in Minuten für Überwachung')
    parser.add_argument('--stats', action='store_true', help='Zeige Systemstatistiken')
    parser.add_argument('--optimize', action='store_true', help='Führe vollständige Optimierung durch')
    parser.add_argument('--clean', action='store_true', help='Bereinige nur Cache/Logs/Temp')
    
    args = parser.parse_args()
    
    optimizer = MacOptimizer()
    
    if args.stats:
        stats = optimizer.get_system_stats()
        optimizer.print_system_stats(stats)
    elif args.monitor:
        optimizer.monitor_mode(args.interval)
    elif args.clean:
        optimizer.cleanup_cache()
        optimizer.cleanup_logs()
        optimizer.cleanup_temp()
        optimizer.cleanup_downloads()
        optimizer.empty_trash()
    elif args.optimize:
        optimizer.run_full_optimization()
    else:
        # Standard: Zeige Stats und frage nach Optimierung
        stats = optimizer.get_system_stats()
        optimizer.print_system_stats(stats)
        
        print("\nMöchtest du eine vollständige Optimierung durchführen? (j/n)")
        response = input().lower()
        if response == 'j':
            optimizer.run_full_optimization()

if __name__ == "__main__":
    main()
