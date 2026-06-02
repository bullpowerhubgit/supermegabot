#!/usr/bin/env python3
"""
SuperMegaBot Desktop Monitor - Professionelles System-Monitoring
Real-time Überwachung mit DeepScan Integration
"""

import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import threading
import json
import time
import psutil
from datetime import datetime
from pathlib import Path
import sys
import os

# Add modules path
sys.path.append(str(Path(__file__).parent / "modules"))

try:
    from deepscan_repair_tool import DeepScanRepairTool
except ImportError:
    print("DeepScan Tool nicht verfügbar")
    DeepScanRepairTool = None

class SystemMetrics:
    """System-Metriken Sammlung"""
    
    def __init__(self):
        self.cpu_history = []
        self.memory_history = []
        self.disk_history = []
        self.max_history = 100
        
    def collect_metrics(self):
        """Sammelt aktuelle System-Metriken"""
        try:
            # CPU Metriken
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            # Memory Metriken
            memory = psutil.virtual_memory()
            
            # Disk Metriken
            disk = psutil.disk_usage('/')
            
            # Process Metriken
            process_count = len(psutil.pids())
            running_processes = len([p for p in psutil.process_iter(['status']) 
                                   if p.info['status'] == 'running'])
            
            # Network Metriken
            network = psutil.net_io_counters()
            
            metrics = {
                "timestamp": datetime.now().isoformat(),
                "cpu": {
                    "percent": cpu_percent,
                    "count": cpu_count,
                    "frequency": cpu_freq.current if cpu_freq else 0,
                    "load_avg": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0]
                },
                "memory": {
                    "percent": memory.percent,
                    "available_gb": memory.available / (1024**3),
                    "used_gb": memory.used / (1024**3),
                    "total_gb": memory.total / (1024**3)
                },
                "disk": {
                    "percent": disk.percent,
                    "free_gb": disk.free / (1024**3),
                    "used_gb": disk.used / (1024**3),
                    "total_gb": disk.total / (1024**3)
                },
                "processes": {
                    "total": process_count,
                    "running": running_processes
                },
                "network": {
                    "bytes_sent": network.bytes_sent,
                    "bytes_recv": network.bytes_recv,
                    "packets_sent": network.packets_sent,
                    "packets_recv": network.packets_recv
                }
            }
            
            # History aktualisieren
            self.cpu_history.append(cpu_percent)
            self.memory_history.append(memory.percent)
            self.disk_history.append(disk.percent)
            
            # History begrenzen
            if len(self.cpu_history) > self.max_history:
                self.cpu_history.pop(0)
                self.memory_history.pop(0)
                self.disk_history.pop(0)
            
            return metrics
            
        except Exception as e:
            return {"error": str(e)}

class DesktopMonitorApp:
    """Hauptanwendung für Desktop Monitor"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🤖 SuperMegaBot Desktop Monitor")
        self.root.geometry("1200x800")
        self.root.configure(bg='#0a0a0f')
        
        # System-Metriken
        self.metrics = SystemMetrics()
        
        # DeepScan Tool
        self.deepscan_tool = None
        if DeepScanRepairTool:
            self.deepscan_tool = DeepScanRepairTool("DesktopMonitor")
        
        # UI State
        self.monitoring_active = False
        self.auto_refresh = True
        self.refresh_interval = 2000  # 2 Sekunden
        
        # UI erstellen
        self.create_ui()
        
        # Monitoring starten
        self.start_monitoring()
    
    def create_ui(self):
        """Erstellt die Benutzeroberfläche"""
        
        # Header
        self.create_header()
        
        # Hauptcontainer
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Linke Seite - System-Metriken
        left_frame = ttk.Frame(main_container)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.create_system_metrics(left_frame)
        
        # Rechte Seite - DeepScan & Alerts
        right_frame = ttk.Frame(main_container)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.create_deepscan_panel(right_frame)
        self.create_alerts_panel(right_frame)
        
        # Footer
        self.create_footer()
    
    def create_header(self):
        """Erstellt den Header"""
        header_frame = tk.Frame(self.root, bg='#1a1a26', height=60)
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        header_frame.pack_propagate(False)
        
        # Titel
        title_label = tk.Label(
            header_frame,
            text="🤖 SuperMegaBot Desktop Monitor",
            font=('SF Pro Display', 18, 'bold'),
            bg='#1a1a26',
            fg='#e8e8f0'
        )
        title_label.pack(side=tk.LEFT, padx=20, pady=15)
        
        # Status-Indikator
        self.status_label = tk.Label(
            header_frame,
            text="● Monitoring Active",
            font=('SF Pro Display', 12),
            bg='#1a1a26',
            fg='#43d98c'
        )
        self.status_label.pack(side=tk.RIGHT, padx=20, pady=15)
        
        # Zeit
        self.time_label = tk.Label(
            header_frame,
            text="",
            font=('SF Pro Display', 12),
            bg='#1a1a26',
            fg='#7070a0'
        )
        self.time_label.pack(side=tk.RIGHT, padx=20, pady=15)
    
    def create_system_metrics(self, parent):
        """Erstellt System-Metriken Panel"""
        
        # Metriken-Container
        metrics_frame = tk.LabelFrame(
            parent,
            text="📊 System Metriken",
            font=('SF Pro Display', 14, 'bold'),
            bg='#1a1a26',
            fg='#e8e8f0',
            relief=tk.RIDGE,
            borderwidth=2
        )
        metrics_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # CPU Metriken
        cpu_frame = tk.Frame(metrics_frame, bg='#1a1a26')
        cpu_frame.pack(fill=tk.X, padx=15, pady=10)
        
        tk.Label(cpu_frame, text="CPU", font=('SF Pro Display', 12, 'bold'), 
                bg='#1a1a26', fg='#e8e8f0').pack(side=tk.LEFT)
        
        self.cpu_label = tk.Label(cpu_frame, text="0%", font=('SF Pro Display', 12),
                                bg='#1a1a26', fg='#43d98c')
        self.cpu_label.pack(side=tk.RIGHT)
        
        self.cpu_progress = ttk.Progressbar(cpu_frame, length=200, mode='determinate')
        self.cpu_progress.pack(side=tk.RIGHT, padx=10)
        
        # Memory Metriken
        mem_frame = tk.Frame(metrics_frame, bg='#1a1a26')
        mem_frame.pack(fill=tk.X, padx=15, pady=10)
        
        tk.Label(mem_frame, text="Memory", font=('SF Pro Display', 12, 'bold'),
                bg='#1a1a26', fg='#e8e8f0').pack(side=tk.LEFT)
        
        self.memory_label = tk.Label(mem_frame, text="0%", font=('SF Pro Display', 12),
                                    bg='#1a1a26', fg='#43d98c')
        self.memory_label.pack(side=tk.RIGHT)
        
        self.memory_progress = ttk.Progressbar(mem_frame, length=200, mode='determinate')
        self.memory_progress.pack(side=tk.RIGHT, padx=10)
        
        # Disk Metriken
        disk_frame = tk.Frame(metrics_frame, bg='#1a1a26')
        disk_frame.pack(fill=tk.X, padx=15, pady=10)
        
        tk.Label(disk_frame, text="Disk", font=('SF Pro Display', 12, 'bold'),
                bg='#1a1a26', fg='#e8e8f0').pack(side=tk.LEFT)
        
        self.disk_label = tk.Label(disk_frame, text="0%", font=('SF Pro Display', 12),
                                   bg='#1a1a26', fg='#43d98c')
        self.disk_label.pack(side=tk.RIGHT)
        
        self.disk_progress = ttk.Progressbar(disk_frame, length=200, mode='determinate')
        self.disk_progress.pack(side=tk.RIGHT, padx=10)
        
        # Prozess-Metriken
        process_frame = tk.Frame(metrics_frame, bg='#1a1a26')
        process_frame.pack(fill=tk.X, padx=15, pady=10)
        
        tk.Label(process_frame, text="Processes", font=('SF Pro Display', 12, 'bold'),
                bg='#1a1a26', fg='#e8e8f0').pack(side=tk.LEFT)
        
        self.processes_label = tk.Label(process_frame, text="0 running", font=('SF Pro Display', 12),
                                      bg='#1a1a26', fg='#43d98c')
        self.processes_label.pack(side=tk.RIGHT)
        
        # Details-Text
        self.details_text = tk.Text(
            metrics_frame,
            height=10,
            bg='#0a0a0f',
            fg='#e8e8f0',
            font=('Monaco', 10),
            relief=tk.SUNKEN,
            borderwidth=2
        )
        self.details_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
    
    def create_deepscan_panel(self, parent):
        """Erstellt DeepScan Panel"""
        
        deepscan_frame = tk.LabelFrame(
            parent,
            text="🔍 DeepScan Control",
            font=('SF Pro Display', 14, 'bold'),
            bg='#1a1a26',
            fg='#e8e8f0',
            relief=tk.RIDGE,
            borderwidth=2
        )
        deepscan_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # DeepScan Status
        status_frame = tk.Frame(deepscan_frame, bg='#1a1a26')
        status_frame.pack(fill=tk.X, padx=15, pady=10)
        
        tk.Label(status_frame, text="Status:", font=('SF Pro Display', 12, 'bold'),
                bg='#1a1a26', fg='#e8e8f0').pack(side=tk.LEFT)
        
        self.deepscan_status_label = tk.Label(status_frame, text="Ready", font=('SF Pro Display', 12),
                                            bg='#1a1a26', fg='#43d98c')
        self.deepscan_status_label.pack(side=tk.RIGHT)
        
        # DeepScan Buttons
        button_frame = tk.Frame(deepscan_frame, bg='#1a1a26')
        button_frame.pack(fill=tk.X, padx=15, pady=10)
        
        self.scan_button = tk.Button(
            button_frame,
            text="🔍 Run DeepScan",
            command=self.run_deepscan,
            bg='#6c63ff',
            fg='white',
            font=('SF Pro Display', 11, 'bold'),
            relief=tk.RAISED,
            borderwidth=2,
            padx=10,
            pady=5
        )
        self.scan_button.pack(side=tk.LEFT, padx=5)
        
        self.repair_button = tk.Button(
            button_frame,
            text="🔧 Auto Repair",
            command=self.run_auto_repair,
            bg='#ff6584',
            fg='white',
            font=('SF Pro Display', 11, 'bold'),
            relief=tk.RAISED,
            borderwidth=2,
            padx=10,
            pady=5
        )
        self.repair_button.pack(side=tk.LEFT, padx=5)
        
        self.patterns_button = tk.Button(
            button_frame,
            text="📈 Analyze Patterns",
            command=self.analyze_patterns,
            bg='#43d98c',
            fg='white',
            font=('SF Pro Display', 11, 'bold'),
            relief=tk.RAISED,
            borderwidth=2,
            padx=10,
            pady=5
        )
        self.patterns_button.pack(side=tk.LEFT, padx=5)
        
        # DeepScan Results
        self.deepscan_text = tk.Text(
            deepscan_frame,
            height=8,
            bg='#0a0a0f',
            fg='#e8e8f0',
            font=('Monaco', 9),
            relief=tk.SUNKEN,
            borderwidth=2
        )
        self.deepscan_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
    
    def create_alerts_panel(self, parent):
        """Erstellt Alerts Panel"""
        
        alerts_frame = tk.LabelFrame(
            parent,
            text="🚨 System Alerts",
            font=('SF Pro Display', 14, 'bold'),
            bg='#1a1a26',
            fg='#e8e8f0',
            relief=tk.RIDGE,
            borderwidth=2
        )
        alerts_frame.pack(fill=tk.BOTH, expand=True)
        
        # Alerts-Liste
        self.alerts_text = tk.Text(
            alerts_frame,
            height=8,
            bg='#0a0a0f',
            fg='#e8e8f0',
            font=('Monaco', 9),
            relief=tk.SUNKEN,
            borderwidth=2
        )
        self.alerts_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        # Clear Button
        clear_button = tk.Button(
            alerts_frame,
            text="🗑️ Clear Alerts",
            command=self.clear_alerts,
            bg='#ff4757',
            fg='white',
            font=('SF Pro Display', 10),
            relief=tk.RAISED,
            borderwidth=1,
            padx=8,
            pady=3
        )
        clear_button.pack(pady=5)
    
    def create_footer(self):
        """Erstellt den Footer"""
        footer_frame = tk.Frame(self.root, bg='#1a1a26', height=40)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=(5, 10))
        footer_frame.pack_propagate(False)
        
        # Auto-Refresh Checkbox
        self.auto_refresh_var = tk.BooleanVar(value=True)
        auto_refresh_check = tk.Checkbutton(
            footer_frame,
            text="Auto Refresh",
            variable=self.auto_refresh_var,
            command=self.toggle_auto_refresh,
            bg='#1a1a26',
            fg='#e8e8f0',
            font=('SF Pro Display', 10),
            selectcolor='#1a1a26'
        )
        auto_refresh_check.pack(side=tk.LEFT, padx=20, pady=10)
        
        # Refresh-Interval
        tk.Label(footer_frame, text="Interval:", bg='#1a1a26', fg='#e8e8f0',
                font=('SF Pro Display', 10)).pack(side=tk.LEFT, padx=5)
        
        self.interval_var = tk.StringVar(value="2s")
        interval_combo = ttk.Combobox(
            footer_frame,
            textvariable=self.interval_var,
            values=["1s", "2s", "5s", "10s"],
            width=5,
            state="readonly"
        )
        interval_combo.pack(side=tk.LEFT, padx=5)
        interval_combo.bind("<<ComboboxSelected>>", self.change_interval)
        
        # Exit Button
        exit_button = tk.Button(
            footer_frame,
            text="❌ Exit",
            command=self.on_closing,
            bg='#ff4757',
            fg='white',
            font=('SF Pro Display', 10),
            relief=tk.RAISED,
            borderwidth=1,
            padx=8,
            pady=3
        )
        exit_button.pack(side=tk.RIGHT, padx=20, pady=5)
    
    def start_monitoring(self):
        """Startet das Monitoring"""
        self.monitoring_active = True
        self.update_display()
        self.add_alert("🚀 System Monitoring Started", "info")
    
    def update_display(self):
        """Aktualisiert die Anzeige"""
        if not self.monitoring_active:
            return
        
        try:
            # Metriken sammeln
            metrics = self.metrics.collect_metrics()
            
            if "error" in metrics:
                self.add_alert(f"❌ Error collecting metrics: {metrics['error']}", "error")
                return
            
            # Zeit aktualisieren
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.time_label.config(text=current_time)
            
            # CPU aktualisieren
            cpu_percent = metrics["cpu"]["percent"]
            self.cpu_label.config(text=f"{cpu_percent:.1f}%")
            self.cpu_progress['value'] = cpu_percent
            
            # Memory aktualisieren
            memory_percent = metrics["memory"]["percent"]
            self.memory_label.config(text=f"{memory_percent:.1f}%")
            self.memory_progress['value'] = memory_percent
            
            # Disk aktualisieren
            disk_percent = metrics["disk"]["percent"]
            self.disk_label.config(text=f"{disk_percent:.1f}%")
            self.disk_progress['value'] = disk_percent
            
            # Processes aktualisieren
            processes = metrics["processes"]["running"]
            self.processes_label.config(text=f"{processes} running")
            
            # Details aktualisieren
            self.update_details(metrics)
            
            # Alerts prüfen
            self.check_alerts(metrics)
            
            # Farben basierend auf Werten aktualisieren
            self.update_colors(cpu_percent, memory_percent, disk_percent)
            
        except Exception as e:
            self.add_alert(f"❌ Display update error: {e}", "error")
        
        # Nächstes Update planen
        if self.auto_refresh:
            self.root.after(self.refresh_interval, self.update_display)
    
    def update_details(self, metrics):
        """Aktualisiert Details-Text"""
        self.details_text.delete(1.0, tk.END)
        
        details = f"""📊 System Details - {datetime.now().strftime('%H:%M:%S')}

CPU: {metrics['cpu']['percent']:.1f}% ({metrics['cpu']['count']} cores)
Frequency: {metrics['cpu']['frequency']:.0f} MHz
Load Average: {', '.join(f'{x:.2f}' for x in metrics['cpu']['load_avg'])}

Memory: {metrics['memory']['used_gb']:.1f}GB / {metrics['memory']['total_gb']:.1f}GB
Available: {metrics['memory']['available_gb']:.1f}GB

Disk: {metrics['disk']['used_gb']:.1f}GB / {metrics['disk']['total_gb']:.1f}GB
Free: {metrics['disk']['free_gb']:.1f}GB

Processes: {metrics['processes']['total']} total, {metrics['processes']['running']} running

Network:
Sent: {metrics['network']['bytes_sent'] / (1024**2):.1f} MB
Received: {metrics['network']['bytes_recv'] / (1024**2):.1f} MB
"""
        
        self.details_text.insert(1.0, details)
    
    def update_colors(self, cpu, memory, disk):
        """Aktualisiert Farben basierend auf Werten"""
        # CPU Farbe
        if cpu > 80:
            self.cpu_label.config(fg='#ff4757')
        elif cpu > 60:
            self.cpu_label.config(fg='#ffd700')
        else:
            self.cpu_label.config(fg='#43d98c')
        
        # Memory Farbe
        if memory > 85:
            self.memory_label.config(fg='#ff4757')
        elif memory > 70:
            self.memory_label.config(fg='#ffd700')
        else:
            self.memory_label.config(fg='#43d98c')
        
        # Disk Farbe
        if disk > 90:
            self.disk_label.config(fg='#ff4757')
        elif disk > 80:
            self.disk_label.config(fg='#ffd700')
        else:
            self.disk_label.config(fg='#43d98c')
    
    def check_alerts(self, metrics):
        """Prüft auf Alerts"""
        cpu = metrics["cpu"]["percent"]
        memory = metrics["memory"]["percent"]
        disk = metrics["disk"]["percent"]
        
        # CPU Alerts
        if cpu > 90:
            self.add_alert(f"🔥 CRITICAL: CPU usage {cpu:.1f}%", "critical")
        elif cpu > 80:
            self.add_alert(f"⚠️ WARNING: CPU usage {cpu:.1f}%", "warning")
        
        # Memory Alerts
        if memory > 95:
            self.add_alert(f"🔥 CRITICAL: Memory usage {memory:.1f}%", "critical")
        elif memory > 85:
            self.add_alert(f"⚠️ WARNING: Memory usage {memory:.1f}%", "warning")
        
        # Disk Alerts
        if disk > 95:
            self.add_alert(f"🔥 CRITICAL: Disk usage {disk:.1f}%", "critical")
        elif disk > 90:
            self.add_alert(f"⚠️ WARNING: Disk usage {disk:.1f}%", "warning")
    
    def add_alert(self, message, level="info"):
        """Fügt einen Alert hinzu"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Farbe basierend auf Level
        colors = {
            "info": "#43d98c",
            "warning": "#ffd700", 
            "critical": "#ff4757",
            "error": "#ff4757"
        }
        
        color = colors.get(level, "#43d98c")
        
        self.alerts_text.insert(tk.END, f"{timestamp} {message}\n")
        
        # Letzte Zeile färben
        line_start = self.alerts_text.index("end-2c linestart")
        line_end = self.alerts_text.index("end-1c")
        self.alerts_text.tag_add(level, line_start, line_end)
        self.alerts_text.tag_config(level, foreground=color)
        
        # Auto-scroll
        self.alerts_text.see(tk.END)
    
    def clear_alerts(self):
        """Leert die Alerts"""
        self.alerts_text.delete(1.0, tk.END)
        self.add_alert("🗑️ Alerts cleared", "info")
    
    def run_deepscan(self):
        """Führt DeepScan durch"""
        if not self.deepscan_tool:
            self.add_alert("❌ DeepScan Tool nicht verfügbar", "error")
            return
        
        def scan_thread():
            try:
                # UI aktualisieren
                self.root.after(0, lambda: self.deepscan_status_label.config(text="Scanning...", fg='#ffd700'))
                self.root.after(0, lambda: self.scan_button.config(state=tk.DISABLED))
                
                # DeepScan durchführen
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                results = loop.run_until_complete(self.deepscan_tool.run_scheduled_deep_scan())
                
                loop.close()
                
                # Ergebnisse anzeigen
                self.root.after(0, lambda: self.show_deepscan_results(results))
                
            except Exception as e:
                self.root.after(0, lambda: self.add_alert(f"❌ DeepScan failed: {e}", "error"))
                self.root.after(0, lambda: self.deepscan_status_label.config(text="Error", fg='#ff4757'))
            finally:
                self.root.after(0, lambda: self.scan_button.config(state=tk.NORMAL))
        
        thread = threading.Thread(target=scan_thread, daemon=True)
        thread.start()
    
    def show_deepscan_results(self, results):
        """Zeigt DeepScan Ergebnisse"""
        self.deepscan_status_label.config(text="Complete", fg='#43d98c')
        
        self.deepscan_text.delete(1.0, tk.END)
        
        result_text = f"""🔍 DeepScan Results - {datetime.now().strftime('%H:%M:%S')}

Scan ID: {results.get('scan_id', 'N/A')}
Issues Found: {results.get('total_issues', 0)}
Issues Fixed: {results.get('auto_repair', {}).get('repairs_successful', 0)}
Scan Duration: {results.get('scan_duration', 0):.2f}s

Categories:
• Code Quality: {len(results.get('code_quality_issues', []))}
• Performance: {len(results.get('performance_issues', []))}
• Security: {len(results.get('security_issues', []))}
• Button Tests: {len(results.get('button_test_results', []))}
• Functionality: {len(results.get('functionality_tests', []))}

Recommendations: {len(results.get('recommendations', []))}
"""
        
        self.deepscan_text.insert(1.0, result_text)
        
        # Alert hinzufügen
        issues = results.get('total_issues', 0)
        if issues > 0:
            self.add_alert(f"🔍 DeepScan completed: {issues} issues found", "warning")
        else:
            self.add_alert(f"✅ DeepScan completed: No issues found", "info")
    
    def run_auto_repair(self):
        """Führt automatische Reparatur durch"""
        if not self.deepscan_tool:
            self.add_alert("❌ DeepScan Tool nicht verfügbar", "error")
            return
        
        def repair_thread():
            try:
                # UI aktualisieren
                self.root.after(0, lambda: self.deepscan_status_label.config(text="Repairing...", fg='#ffd700'))
                self.root.after(0, lambda: self.repair_button.config(state=tk.DISABLED))
                
                # Reparatur durchführen
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Quick scan
                scan_results = loop.run_until_complete(self.deepscan_tool.perform_deep_scan())
                
                # Auto-repair
                repair_results = loop.run_until_complete(self.deepscan_tool.auto_repair(scan_results))
                
                loop.close()
                
                # Ergebnisse anzeigen
                self.root.after(0, lambda: self.show_repair_results(repair_results))
                
            except Exception as e:
                self.root.after(0, lambda: self.add_alert(f"❌ Auto-repair failed: {e}", "error"))
                self.root.after(0, lambda: self.deepscan_status_label.config(text="Error", fg='#ff4757'))
            finally:
                self.root.after(0, lambda: self.repair_button.config(state=tk.NORMAL))
        
        thread = threading.Thread(target=repair_thread, daemon=True)
        thread.start()
    
    def show_repair_results(self, results):
        """Zeigt Reparatur-Ergebnisse"""
        self.deepscan_status_label.config(text="Repaired", fg='#43d98c')
        
        self.deepscan_text.delete(1.0, tk.END)
        
        result_text = f"""🔧 Auto-Repair Results - {datetime.now().strftime('%H:%M:%S')}

Repairs Attempted: {results.get('repairs_attempted', 0)}
Repairs Successful: {results.get('repairs_successful', 0)}
Repairs Failed: {results.get('repairs_failed', 0)}

Success Rate: {(results.get('repairs_successful', 0) / max(results.get('repairs_attempted', 1), 1) * 100):.1f}%

Fixed Issues:
"""
        
        for repair in results.get('repairs', [])[:10]:  # Show first 10
            if repair.get('success'):
                result_text += f"✅ {repair.get('issue', {}).get('issue', 'Unknown')}\n"
            else:
                result_text += f"❌ {repair.get('issue', {}).get('issue', 'Unknown')}\n"
        
        self.deepscan_text.insert(1.0, result_text)
        
        # Alert hinzufügen
        successful = results.get('repairs_successful', 0)
        if successful > 0:
            self.add_alert(f"🔧 Auto-repair completed: {successful} issues fixed", "info")
        else:
            self.add_alert(f"🔧 Auto-repair completed: No issues fixed", "warning")
    
    def analyze_patterns(self):
        """Analysiert Performance-Muster"""
        if not self.deepscan_tool:
            self.add_alert("❌ DeepScan Tool nicht verfügbar", "error")
            return
        
        def patterns_thread():
            try:
                # UI aktualisieren
                self.root.after(0, lambda: self.deepscan_status_label.config(text="Analyzing...", fg='#ffd700'))
                self.root.after(0, lambda: self.patterns_button.config(state=tk.DISABLED))
                
                # Pattern-Analyse durchführen
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                patterns = loop.run_until_complete(self.deepscan_tool.analyzePerformancePatterns())
                
                loop.close()
                
                # Ergebnisse anzeigen
                self.root.after(0, lambda: self.show_pattern_results(patterns))
                
            except Exception as e:
                self.root.after(0, lambda: self.add_alert(f"❌ Pattern analysis failed: {e}", "error"))
                self.root.after(0, lambda: self.deepscan_status_label.config(text="Error", fg='#ff4757'))
            finally:
                self.root.after(0, lambda: self.patterns_button.config(state=tk.NORMAL))
        
        thread = threading.Thread(target=patterns_thread, daemon=True)
        thread.start()
    
    def show_pattern_results(self, patterns):
        """Zeigt Pattern-Ergebnisse"""
        self.deepscan_status_label.config(text="Analyzed", fg='#43d98c')
        
        self.deepscan_text.delete(1.0, tk.END)
        
        if "error" in patterns:
            self.deepscan_text.insert(1.0, f"❌ {patterns['error']}")
            return
        
        result_text = f"""📈 Performance Patterns - {datetime.now().strftime('%H:%M:%S')}

Memory:
Current: {patterns.get('memory_trends', [{}])[0].get('current', 0):.1f}%
Available: {patterns.get('memory_trends', [{}])[0].get('available_gb', 0):.1f}GB
Pressure: {patterns.get('memory_trends', [{}])[0].get('pressure', 'unknown')}

CPU:
Current: {patterns.get('cpu_trends', [{}])[0].get('current', 0):.1f}%
Cores: {patterns.get('cpu_trends', [{}])[0].get('cores', 0)}
Pressure: {patterns.get('cpu_trends', [{}])[0].get('pressure', 'unknown')}

Disk:
Current: {patterns.get('disk_trends', [{}])[0].get('current', 0):.1f}%
Free: {patterns.get('disk_trends', [{}])[0].get('free_gb', 0):.1f}GB
Pressure: {patterns.get('disk_trends', [{}])[0].get('pressure', 'unknown')}

Bottlenecks: {len(patterns.get('bottlenecks', []))}
Recommendations: {len(patterns.get('recommendations', []))}
"""
        
        self.deepscan_text.insert(1.0, result_text)
        
        # Alert hinzufügen
        bottlenecks = len(patterns.get('bottlenecks', []))
        if bottlenecks > 0:
            self.add_alert(f"📈 Pattern analysis: {bottlenecks} bottlenecks detected", "warning")
        else:
            self.add_alert(f"📈 Pattern analysis: No bottlenecks detected", "info")
    
    def toggle_auto_refresh(self):
        """Schaltet Auto-Refresh um"""
        self.auto_refresh = self.auto_refresh_var.get()
        
        if self.auto_refresh:
            self.add_alert("🔄 Auto-refresh enabled", "info")
            self.update_display()
        else:
            self.add_alert("⏸️ Auto-refresh disabled", "info")
    
    def change_interval(self, event=None):
        """Ändert das Refresh-Interval"""
        interval_map = {"1s": 1000, "2s": 2000, "5s": 5000, "10s": 10000}
        self.refresh_interval = interval_map.get(self.interval_var.get(), 2000)
        
        self.add_alert(f"⏱️ Refresh interval changed to {self.interval_var.get()}", "info")
    
    def on_closing(self):
        """Wird beim Schließen aufgerufen"""
        if messagebox.askokcancel("Quit", "Möchten Sie den Desktop Monitor wirklich beenden?"):
            self.monitoring_active = False
            self.root.destroy()
    
    def run(self):
        """Startet die Anwendung"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

def main():
    """Hauptfunktion"""
    try:
        app = DesktopMonitorApp()
        app.run()
    except KeyboardInterrupt:
        print("\n👋 Desktop Monitor beendet")
    except Exception as e:
        print(f"💥 Fehler: {e}")

if __name__ == "__main__":
    main()
