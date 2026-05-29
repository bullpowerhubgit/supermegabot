#!/usr/bin/env python3
"""
Deep Scan Fix für Mac - Integrierte Systemdiagnose und Reparatur
Basiert auf deep-scan-fix-enhanced.js, angepasst für macOS
"""

import os
import subprocess
import json
import time
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import argparse
import hashlib
import psutil
import asyncio

# Import GCP configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from gcp_config import gcp_config

class DeepScanFixMac:
    def __init__(self):
        self.gcp_project_id = gcp_config.project_id
        self.gcp_apis = gcp_config.api_list
        self.scan_results = {}
        self.repair_log = []
        self.scan_start_time = None
        self.issues = {
            'critical': [],
            'warning': [],
            'info': []
        }
        self.error_history = {}
        self.function_tests = {}
        self.improvement_metrics = {}
        self.extensibility_points = {}
        
        # Mac-spezifische Pfade
        self.home_dir = Path.home()
        self.config_dir = self.home_dir / ".mac-optimizer"
        self.log_file = self.config_dir / "deep-scan-fix.log"
        self.history_file = self.config_dir / "scan-history.json"
        
        self.ensure_directories()
        self.load_history()
    
    def ensure_directories(self):
        """Erstellt notwendige Verzeichnisse"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def load_history(self):
        """Lädt Scan-Historie"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    self.error_history = json.load(f)
            except Exception:
                self.error_history = {}
    
    def save_history(self):
        """Speichert Scan-Historie"""
        with open(self.history_file, 'w') as f:
            json.dump(self.error_history, f, indent=2)
    
    def log(self, message, level="INFO"):
        """Loggt Nachricht"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}\n"
        print(log_entry.strip())
        with open(self.log_file, 'a') as f:
            f.write(log_entry)
    
    async def perform_deep_scan(self):
        """Führt vollständigen Deep Scan durch"""
        self.log("🔍 Starting enhanced deep scan and repair for macOS...")
        self.scan_start_time = datetime.now().isoformat()
        
        try:
            # Phase 1: System Health Check
            await self.check_system_health()
            
            # Phase 2: File System Integrity
            await self.scan_file_system()
            
            # Phase 3: Process Analysis
            await self.scan_running_processes()
            
            # Phase 4: Memory Analysis
            await self.scan_memory_usage()
            
            # Phase 5: Disk Analysis
            await self.scan_disk_usage()
            
            # Phase 6: Network Analysis
            await self.scan_network_status()
            
            # Phase 7: Security Analysis
            await self.scan_security_issues()
            
            # Phase 8: Performance Analysis
            await self.scan_performance_issues()
            
            # Phase 9: Application Analysis
            await self.scan_applications()
            
            # Phase 10: Check recurring errors
            await self.check_recurring_errors()
            
            # Generate report
            await self.generate_scan_report()
            
            # Auto-repair
            await self.perform_auto_repair()
            
            self.log("✅ Enhanced deep scan and repair completed")
            return self.generate_final_report()
            
        except Exception as error:
            self.log(f"❌ Deep scan failed: {str(error)}", "ERROR")
            self.learn_from_error('deep_scan_failure', str(error))
            return {'success': False, 'error': str(error)}
    
    async def check_system_health(self):
        """Prüft Systemgesundheit"""
        self.log("🏥 Checking system health...")
        
        # CPU Check
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > 80:
            self.issues['critical'].append({
                'type': 'high_cpu',
                'value': cpu_percent,
                'message': f'High CPU usage: {cpu_percent:.1f}%'
            })
        elif cpu_percent > 60:
            self.issues['warning'].append({
                'type': 'moderate_cpu',
                'value': cpu_percent,
                'message': f'Moderate CPU usage: {cpu_percent:.1f}%'
            })
        
        # Memory Check
        memory = psutil.virtual_memory()
        if memory.percent > 85:
            self.issues['critical'].append({
                'type': 'high_memory',
                'value': memory.percent,
                'message': f'High memory usage: {memory.percent:.1f}%'
            })
        elif memory.percent > 70:
            self.issues['warning'].append({
                'type': 'moderate_memory',
                'value': memory.percent,
                'message': f'Moderate memory usage: {memory.percent:.1f}%'
            })
        
        # Temperature Check (wenn verfügbar)
        try:
            temp_result = subprocess.run(['sudo', 'powermetrics', '--samplers', 'cpu_power', '-i', '1000'], 
                                      capture_output=True, text=True, timeout=5)
            # Temperature parsing würde hier implementiert
        except Exception:
            pass
        
        self.log(f"✅ System health check completed")
    
    async def scan_file_system(self):
        """Scannt Dateisystem-Integrität"""
        self.log("📁 Scanning file system integrity...")
        
        # Wichtige Verzeichnisse prüfen
        critical_dirs = [
            self.home_dir / "Library",
            self.home_dir / "Documents",
            self.home_dir / "Desktop",
            self.home_dir / "Downloads",
            Path("/Applications"),
            Path("/Library"),
            Path("/System")
        ]
        
        for directory in critical_dirs:
            if not directory.exists():
                self.issues['critical'].append({
                    'type': 'missing_directory',
                    'path': str(directory),
                    'message': f'Critical directory missing: {directory}'
                })
            else:
                # Prüfe Berechtigungen
                if not os.access(directory, os.R_OK):
                    self.issues['warning'].append({
                        'type': 'permission_issue',
                        'path': str(directory),
                        'message': f'Read permission issue: {directory}'
                    })
        
        # Prüfe auf beschädigte Dateien
        await self.check_corrupted_files()
        
        self.log("✅ File system scan completed")
    
    async def check_corrupted_files(self):
        """Prüft auf beschädigte Dateien"""
        critical_files = [
            self.home_dir / "Library" / "Preferences" / ".GlobalPreferences.plist",
            self.home_dir / "Library" / "Keychains" / "login.keychain-db"
        ]
        
        for file_path in critical_files:
            if file_path.exists():
                try:
                    # Versuche Datei zu lesen
                    with open(file_path, 'rb') as f:
                        f.read(1024)  # Erste 1KB lesen
                except Exception as e:
                    self.issues['critical'].append({
                        'type': 'corrupted_file',
                        'path': str(file_path),
                        'message': f'Corrupted file detected: {file_path}'
                    })
    
    async def scan_running_processes(self):
        """Analysiert laufende Prozesse"""
        self.log("⚙️ Scanning running processes...")
        
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Finde ressourcenintensive Prozesse
        high_cpu_processes = [p for p in processes if p['cpu_percent'] and p['cpu_percent'] > 50]
        high_mem_processes = [p for p in processes if p['memory_percent'] and p['memory_percent'] > 10]
        
        for proc in high_cpu_processes:
            self.issues['warning'].append({
                'type': 'high_cpu_process',
                'pid': proc['pid'],
                'name': proc['name'],
                'cpu': proc['cpu_percent'],
                'message': f'High CPU process: {proc["name"]} ({proc["cpu_percent"]:.1f}%)'
            })
        
        for proc in high_mem_processes:
            self.issues['warning'].append({
                'type': 'high_memory_process',
                'pid': proc['pid'],
                'name': proc['name'],
                'memory': proc['memory_percent'],
                'message': f'High memory process: {proc["name"]} ({proc["memory_percent"]:.1f}%)'
            })
        
        self.log(f"✅ Process scan completed - {len(processes)} processes analyzed")
    
    async def scan_memory_usage(self):
        """Analysiert Speichernutzung"""
        self.log("🧠 Scanning memory usage...")
        
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        memory_info = {
            'total': memory.total,
            'available': memory.available,
            'used': memory.used,
            'percent': memory.percent,
            'swap_total': swap.total,
            'swap_used': swap.used,
            'swap_percent': swap.percent
        }
        
        self.scan_results['memory'] = memory_info
        
        # Memory Pressure Analyse
        if memory.percent > 90:
            self.issues['critical'].append({
                'type': 'critical_memory_pressure',
                'percent': memory.percent,
                'message': f'Critical memory pressure: {memory.percent:.1f}%'
            })
        
        if swap.percent > 50:
            self.issues['warning'].append({
                'type': 'high_swap_usage',
                'percent': swap.percent,
                'message': f'High swap usage: {swap.percent:.1f}%'
            })
        
        self.log("✅ Memory scan completed")
    
    async def scan_disk_usage(self):
        """Analysiert Festplattennutzung"""
        self.log("💾 Scanning disk usage...")
        
        disk_info = {}
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_info[partition.mountpoint] = {
                    'total': usage.total,
                    'used': usage.used,
                    'free': usage.free,
                    'percent': (usage.used / usage.total) * 100
                }
                
                # Prüfe auf vollen Speicher
                if usage.percent > 90:
                    self.issues['critical'].append({
                        'type': 'critical_disk_usage',
                        'mountpoint': partition.mountpoint,
                        'percent': usage.percent,
                        'message': f'Critical disk usage: {partition.mountpoint} ({usage.percent:.1f}%)'
                    })
                elif usage.percent > 80:
                    self.issues['warning'].append({
                        'type': 'high_disk_usage',
                        'mountpoint': partition.mountpoint,
                        'percent': usage.percent,
                        'message': f'High disk usage: {partition.mountpoint} ({usage.percent:.1f}%)'
                    })
                
            except PermissionError:
                continue
        
        self.scan_results['disk'] = disk_info
        self.log("✅ Disk scan completed")
    
    async def scan_network_status(self):
        """Prüft Netzwerkstatus"""
        self.log("🌐 Scanning network status...")
        
        # Netzwerk-Interfaces prüfen
        network_info = {}
        for name, stats in psutil.net_if_addrs().items():
            network_info[name] = {
                'addresses': [addr.address for addr in stats]
            }
        
        # Netzwerk-I/O prüfen
        net_io = psutil.net_io_counters()
        self.scan_results['network'] = {
            'interfaces': network_info,
            'io': {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv
            }
        }
        
        # DNS-Verbindung prüfen
        try:
            import socket
            socket.gethostbyname('google.com')
        except socket.gaierror:
            self.issues['critical'].append({
                'type': 'dns_resolution_failed',
                'message': 'DNS resolution failed'
            })
        
        self.log("✅ Network scan completed")
    
    async def scan_security_issues(self):
        """Prüft auf Sicherheitsprobleme"""
        self.log("🔒 Scanning security issues...")
        
        # Firewall Status prüfen
        try:
            firewall_result = subprocess.run(['sudo', '/usr/libexec/ApplicationFirewall/socketfilterfw', '--getglobalstate'], 
                                          capture_output=True, text=True)
            if firewall_result.stdout.strip() != 'enabled':
                self.issues['warning'].append({
                    'type': 'firewall_disabled',
                    'message': 'Firewall is disabled'
                })
        except Exception:
            pass
        
        # System Integrity Protection prüfen
        try:
            sip_result = subprocess.run(['csrutil', 'status'], capture_output=True, text=True)
            if 'disabled' in sip_result.stdout:
                self.issues['warning'].append({
                    'type': 'sip_disabled',
                    'message': 'System Integrity Protection is disabled'
                })
        except Exception:
            pass
        
        # Prüfe auf verdächtige Prozesse
        suspicious_processes = ['malware', 'virus', 'trojan', 'backdoor']
        for proc in psutil.process_iter(['name']):
            try:
                proc_name = proc.info['name'].lower()
                if any(susp in proc_name for susp in suspicious_processes):
                    self.issues['critical'].append({
                        'type': 'suspicious_process',
                        'name': proc.info['name'],
                        'message': f'Suspicious process detected: {proc.info["name"]}'
                    })
            except Exception:
                continue
        
        self.log("✅ Security scan completed")
    
    async def scan_performance_issues(self):
        """Prüft auf Performance-Probleme"""
        self.log("⚡ Scanning performance issues...")
        
        # Boot Time prüfen
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        
        if uptime.days > 30:
            self.issues['info'].append({
                'type': 'long_uptime',
                'days': uptime.days,
                'message': f'System uptime: {uptime.days} days (consider restart)'
            })
        
        # Load Average prüfen
        load_avg = os.getloadavg()
        if load_avg[0] > 2.0:
            self.issues['warning'].append({
                'type': 'high_load_average',
                'load_1min': load_avg[0],
                'message': f'High load average: {load_avg[0]:.2f}'
            })
        
        self.scan_results['performance'] = {
            'boot_time': boot_time.isoformat(),
            'uptime_hours': uptime.total_seconds() / 3600,
            'load_average': list(load_avg)
        }
        
        self.log("✅ Performance scan completed")
    
    async def scan_applications(self):
        """Analysiert installierte Anwendungen"""
        self.log("📱 Scanning applications...")
        
        applications_dir = Path("/Applications")
        if applications_dir.exists():
            app_count = 0
            large_apps = []
            
            for app in applications_dir.glob("*.app"):
                app_count += 1
                try:
                    # Prüfe App-Größe
                    size_result = subprocess.run(['du', '-s', str(app)], capture_output=True, text=True)
                    if size_result.returncode == 0:
                        size_kb = int(size_result.stdout.split()[0])
                        size_mb = size_kb / 1024
                        
                        if size_mb > 1000:  # > 1GB
                            large_apps.append({
                                'name': app.name,
                                'size_mb': size_mb
                            })
                except Exception:
                    pass
            
            self.scan_results['applications'] = {
                'total_count': app_count,
                'large_apps': large_apps
            }
            
            if len(large_apps) > 10:
                self.issues['info'].append({
                    'type': 'many_large_applications',
                    'count': len(large_apps),
                    'message': f'Found {len(large_apps)} applications > 1GB'
                })
        
        self.log("✅ Application scan completed")
    
    async def check_recurring_errors(self):
        """Prüft auf wiederkehrende Fehler"""
        self.log("🧠 Checking for recurring error patterns...")
        
        recurring_errors = []
        
        for error_type, occurrences in self.error_history.items():
            if len(occurrences) >= 3:
                last_occurrence = occurrences[-1]
                time_span = time.time() - last_occurrence['timestamp']
                
                recurring_errors.append({
                    'type': error_type,
                    'occurrences': len(occurrences),
                    'last_occurrence': last_occurrence['timestamp'],
                    'time_span': time_span
                })
                
                severity = 'critical' if time_span < 3600 else 'warning'
                self.issues[severity].append({
                    'type': 'recurring_error',
                    'error_type': error_type,
                    'occurrences': len(occurrences),
                    'message': f'Recurring error: {error_type} occurred {len(occurrences)} times'
                })
        
        return recurring_errors
    
    def learn_from_error(self, error_type, context, error_message=None):
        """Lernt aus Fehlern"""
        if error_type not in self.error_history:
            self.error_history[error_type] = []
        
        self.error_history[error_type].append({
            'timestamp': time.time(),
            'context': context,
            'error_message': error_message
        })
        
        self.save_history()
    
    def analyzePerformancePatterns(self, performance_issues):
        """Analysiert Performance-Muster über alle gefundenen Issues"""
        patterns = {
            'total_issues': len(performance_issues),
            'by_type': {},
            'by_severity': {},
            'by_category': {},
            'recommendations': []
        }
        
        # Gruppiere nach Typ
        for issue in performance_issues:
            issue_type = issue.get('type', 'unknown')
            severity = issue.get('severity', 'info')
            category = issue.get('category', 'general')
            
            if issue_type not in patterns['by_type']:
                patterns['by_type'][issue_type] = 0
            patterns['by_type'][issue_type] += 1
            
            if severity not in patterns['by_severity']:
                patterns['by_severity'][severity] = 0
            patterns['by_severity'][severity] += 1
            
            if category not in patterns['by_category']:
                patterns['by_category'][category] = 0
            patterns['by_category'][category] += 1
        
        # Generiere Empfehlungen basierend auf Mustern
        if patterns['by_type'].get('high_cpu_process', 0) > 3:
            patterns['recommendations'].append({
                'type': 'cpu-optimization',
                'priority': 'high',
                'message': 'Mehrere CPU-intensive Prozesse gefunden - Speicher-Optimierung empfohlen'
            })
        
        if patterns['by_type'].get('high_memory_process', 0) > 3:
            patterns['recommendations'].append({
                'type': 'memory-optimization',
                'priority': 'high',
                'message': 'Mehrere speicherintensive Prozesse gefunden - Browser-Cache leeren empfohlen'
            })
        
        if patterns['by_severity'].get('critical', 0) > 2:
            patterns['recommendations'].append({
                'type': 'immediate-action',
                'priority': 'critical',
                'message': 'Kritische Probleme erkannt - Sofortige Systemoptimierung empfohlen'
            })
        
        if patterns['by_type'].get('recurring_error', 0) > 0:
            patterns['recommendations'].append({
                'type': 'error-investigation',
                'priority': 'medium',
                'message': 'Wiederkehrende Fehler erkannt - Deep Scan empfohlen'
            })
        
        return patterns
    
    async def generate_scan_report(self):
        """Generiert Scan-Report"""
        self.log("📋 Generating comprehensive scan report...")
        
        report = {
            'scan_info': {
                'start_time': self.scan_start_time,
                'end_time': datetime.now().isoformat(),
                'duration': (datetime.now() - datetime.fromisoformat(self.scan_start_time)).total_seconds()
            },
            'summary': {
                'total_issues': len(self.issues['critical']) + len(self.issues['warning']) + len(self.issues['info']),
                'critical': len(self.issues['critical']),
                'warning': len(self.issues['warning']),
                'info': len(self.issues['info'])
            },
            'issues': self.issues,
            'scan_results': self.scan_results,
            'function_tests': list(self.function_tests.values()),
            'repairs': self.repair_log
        }
        
        report_file = self.config_dir / "deep-scan-report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.log("✅ Scan report generated")
    
    async def perform_auto_repair(self):
        """Führt automatische Reparaturen durch"""
        self.log("🔧 Performing auto-repair...")
        
        repairs_made = 0
        
        # Memory Pressure reduzieren
        if any(issue['type'] == 'critical_memory_pressure' for issue in self.issues['critical']):
            await self.repair_memory_pressure()
            repairs_made += 1
        
        # Disk Cleanup bei hohem Speicherverbrauch
        if any(issue['type'] in ['critical_disk_usage', 'high_disk_usage'] for issue in self.issues['critical'] + self.issues['warning']):
            await self.repair_disk_usage()
            repairs_made += 1
        
        # Prozesse beenden bei hoher CPU-Auslastung
        high_cpu_processes = [issue for issue in self.issues['warning'] if issue['type'] == 'high_cpu_process']
        if high_cpu_processes:
            await self.repair_high_cpu_processes(high_cpu_processes)
            repairs_made += len(high_cpu_processes)
        
        self.log(f"✅ Auto-repair completed - {repairs_made} repairs made")
    
    async def repair_memory_pressure(self):
        """Repariert Memory Pressure"""
        self.log("🧠 Repairing memory pressure...")
        
        try:
            # Memory freigeben
            subprocess.run(['purge'], capture_output=True)
            
            # Cache leeren
            cache_dirs = [
                self.home_dir / "Library" / "Caches",
                Path("/tmp")
            ]
            
            for cache_dir in cache_dirs:
                if cache_dir.exists():
                    for item in cache_dir.iterdir():
                        if item.is_file() and time.time() - item.stat().st_mtime > 86400:  # älter als 1 Tag
                            try:
                                item.unlink()
                            except Exception:
                                pass
            
            self.repair_log.append({
                'type': 'memory_pressure_repair',
                'timestamp': datetime.now().isoformat(),
                'success': True
            })
            
        except Exception as e:
            self.log(f"Memory pressure repair failed: {e}", "ERROR")
    
    async def repair_disk_usage(self):
        """Repariert hohe Festplattennutzung"""
        self.log("💾 Repairing disk usage...")
        
        try:
            # Downloads aufräumen
            downloads_dir = self.home_dir / "Downloads"
            if downloads_dir.exists():
                deleted_count = 0
                for item in downloads_dir.iterdir():
                    if item.is_file() and time.time() - item.stat().st_mtime > 2592000:  # älter als 30 Tage
                        try:
                            item.unlink()
                            deleted_count += 1
                        except Exception:
                            pass
                
                self.repair_log.append({
                    'type': 'disk_cleanup',
                    'timestamp': datetime.now().isoformat(),
                    'files_deleted': deleted_count,
                    'success': True
                })
            
        except Exception as e:
            self.log(f"Disk usage repair failed: {e}", "ERROR")
    
    async def repair_high_cpu_processes(self, processes):
        """Beendet High-CPU-Prozesse"""
        self.log("⚙️ Repairing high CPU processes...")
        
        for proc_info in processes:
            try:
                proc = psutil.Process(proc_info['pid'])
                proc.terminate()
                
                self.repair_log.append({
                    'type': 'process_termination',
                    'timestamp': datetime.now().isoformat(),
                    'pid': proc_info['pid'],
                    'name': proc_info['name'],
                    'success': True
                })
                
            except Exception as e:
                self.log(f"Failed to terminate process {proc_info['pid']}: {e}", "ERROR")
    
    def generate_final_report(self):
        """Generiert finalen Report"""
        return {
            'success': True,
            'scan_results': self.scan_results,
            'issues': self.issues,
            'repairs': self.repair_log,
            'summary': {
                'total_issues': len(self.issues['critical']) + len(self.issues['warning']) + len(self.issues['info']),
                'critical': len(self.issues['critical']),
                'warning': len(self.issues['warning']),
                'info': len(self.issues['info']),
                'repairs_made': len(self.repair_log)
            }
        }
    
    def print_summary(self):
        """Gibt Zusammenfassung aus"""
        print("\n" + "="*60)
        print("🔍 DEEP SCAN FIX MAC - SUMMARY")
        print("="*60)
        
        critical = len(self.issues['critical'])
        warning = len(self.issues['warning'])
        info = len(self.issues['info'])
        repairs = len(self.repair_log)
        
        print(f"📊 Issues Found: {critical + warning + info}")
        print(f"   Critical: {critical}")
        print(f"   Warnings: {warning}")
        print(f"   Info: {info}")
        print(f"🔧 Repairs Made: {repairs}")
        
        if critical > 0:
            print("\n🚨 CRITICAL ISSUES:")
            for issue in self.issues['critical'][:5]:  # Zeige nur erste 5
                print(f"   • {issue['message']}")
        
        if warning > 0:
            print("\n⚠️ WARNINGS:")
            for issue in self.issues['warning'][:5]:  # Zeige nur erste 5
                print(f"   • {issue['message']}")
        
        print("\n" + "="*60)

async def main():
    parser = argparse.ArgumentParser(description='Deep Scan Fix für macOS')
    parser.add_argument('--scan', action='store_true', help='Vollständigen Deep Scan durchführen')
    parser.add_argument('--quick', action='store_true', help='Schneller System-Check')
    parser.add_argument('--repair', action='store_true', help='Nur Reparatur durchführen')
    parser.add_argument('--report', action='store_true', help='Letzten Report anzeigen')
    
    args = parser.parse_args()
    
    scanner = DeepScanFixMac()
    
    if args.scan:
        result = await scanner.perform_deep_scan()
        scanner.print_summary()
    elif args.quick:
        # Schneller Check
        await scanner.check_system_health()
        await scanner.scan_memory_usage()
        await scanner.scan_disk_usage()
        scanner.print_summary()
    elif args.repair:
        await scanner.perform_auto_repair()
    elif args.report:
        report_file = scanner.config_dir / "deep-scan-report.json"
        if report_file.exists():
            with open(report_file, 'r') as f:
                report = json.load(f)
            print(json.dumps(report, indent=2))
        else:
            print("Kein Report gefunden. Führe zuerst einen Scan durch.")
    else:
        # Standard: Vollständiger Scan
        result = await scanner.perform_deep_scan()
        scanner.print_summary()

if __name__ == "__main__":
    asyncio.run(main())
