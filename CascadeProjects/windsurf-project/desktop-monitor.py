#!/usr/bin/env python3
"""
Mac Desktop Monitor - Professionelles Live-System-Monitoring
Kompakt, uebersichtlich, immer im Blick

MIT OPENCLAW BRIDGE INTEGRATION
"""

import os
import sys
import time
import subprocess
import psutil
import json
import socket
import threading
from datetime import datetime

# Import GCP configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from gcp_config import gcp_config

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    END = '\033[0m'
    CLEAR = '\033[2J\033[H'

class OpenCLAWBridge:
    """OpenCLAW Bridge Integration fuer Desktop Monitor"""
    
    def __init__(self):
        self.bridge_port = 3003
        self.bridge_host = 'localhost'
        self.connected = False
        self.last_data = {}
        
    def send_system_data(self, system_data):
        """Sende System-Daten an OpenCLAW Bridge"""
        try:
            data = {
                'timestamp': datetime.now().isoformat(),
                'source': 'desktop-monitor',
                'system': system_data,
                'alerts': self.generate_alerts(system_data)
            }
            
            # Sende via Socket (einfachste Methode)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((self.bridge_host, self.bridge_port))
            sock.send(json.dumps(data).encode())
            sock.close()
            self.connected = True
            return True
            
        except Exception as e:
            self.connected = False
            return False
    
    def generate_alerts(self, system_data):
        """Generiere Alerts basierend auf System-Daten"""
        alerts = []
        
        if system_data.get('cpu', 0) > 80:
            alerts.append({
                'type': 'high_cpu',
                'severity': 'high' if system_data['cpu'] > 90 else 'medium',
                'message': f"CPU Auslastung: {system_data['cpu']:.1f}%"
            })
        
        if system_data.get('memory', {}).get('percent', 0) > 85:
            alerts.append({
                'type': 'high_memory',
                'severity': 'high' if system_data['memory']['percent'] > 95 else 'medium',
                'message': f"RAM Auslastung: {system_data['memory']['percent']:.1f}%"
            })
        
        if system_data.get('disk', {}).get('percent', 0) > 90:
            alerts.append({
                'type': 'high_disk',
                'severity': 'high',
                'message': f"Festplatte: {system_data['disk']['percent']:.1f}% voll"
            })
        
        return alerts

def get_bar(percent, width=20):
    filled = int(percent / 100 * width)
    empty = width - filled
    if percent < 60:
        color = Colors.GREEN
    elif percent < 80:
        color = Colors.YELLOW
    else:
        color = Colors.RED
    bar = '█' * filled + '░' * empty
    return f"{color}{bar}{Colors.END}"

def get_status_color(percent):
    if percent < 60:
        return Colors.GREEN
    elif percent < 80:
        return Colors.YELLOW
    else:
        return Colors.RED

def get_temp():
    try:
        result = subprocess.run(
            ['osx-cpu-temp'], capture_output=True, text=True, timeout=2
        )
        return result.stdout.strip()
    except:
        return "N/A"

def get_top_processes(n=5):
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            info = proc.info
            if info['cpu_percent'] and info['cpu_percent'] > 0.1:
                processes.append(info)
        except:
            continue
    processes.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
    return processes[:n]

def get_network():
    try:
        net = psutil.net_io_counters()
        return {
            'sent': f"{net.bytes_sent / (1024**2):.1f} MB",
            'recv': f"{net.bytes_recv / (1024**2):.1f} MB"
        }
    except:
        return {'sent': 'N/A', 'recv': 'N/A'}

def get_disk_io():
    try:
        disk = psutil.disk_io_counters()
        return {
            'read': f"{disk.read_bytes / (1024**2):.1f} MB",
            'write': f"{disk.write_bytes / (1024**2):.1f} MB"
        }
    except:
        return {'read': 'N/A', 'write': 'N/A'}

def draw_monitor(openclaw_bridge=None):
    print(Colors.CLEAR, end='')
    
    now = datetime.now().strftime("%H:%M:%S")
    
    print(f"{Colors.CYAN}{Colors.BOLD}┌────────────────────────────────────────┐{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}│{Colors.END}  🖥️  MAC DESKTOP MONITOR              {Colors.CYAN}{Colors.BOLD}│{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}│{Colors.END}  {Colors.DIM}{now}{Colors.END}                         {Colors.CYAN}{Colors.BOLD}│{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}├────────────────────────────────────────┤{Colors.END}")
    
    # CPU
    cpu = psutil.cpu_percent(interval=0.5)
    freq = psutil.cpu_freq()
    cpu_color = get_status_color(cpu)
    print(f"{Colors.CYAN}│{Colors.END}  {Colors.BOLD}CPU{Colors.END}  {get_bar(cpu)} {cpu_color}{cpu:5.1f}%{Colors.END}     {Colors.CYAN}│{Colors.END}")
    if freq:
        print(f"{Colors.CYAN}│{Colors.END}  {Colors.DIM}Freq: {freq.current/1000:.2f} GHz | Cores: {psutil.cpu_count()}{Colors.END}        {Colors.CYAN}│{Colors.END}")
    
    # RAM
    mem = psutil.virtual_memory()
    mem_color = get_status_color(mem.percent)
    print(f"{Colors.CYAN}│{Colors.END}  {Colors.BOLD}RAM{Colors.END}  {get_bar(mem.percent)} {mem_color}{mem.percent:5.1f}%{Colors.END}     {Colors.CYAN}│{Colors.END}")
    used_gb = mem.used / (1024**3)
    total_gb = mem.total / (1024**3)
    print(f"{Colors.CYAN}│{Colors.END}  {Colors.DIM}{used_gb:.1f}/{total_gb:.1f} GB | Frei: {mem.available/(1024**3):.1f} GB{Colors.END}       {Colors.CYAN}│{Colors.END}")
    
    # Festplatte
    disk = psutil.disk_usage('/')
    disk_percent = disk.percent
    disk_color = get_status_color(disk_percent)
    print(f"{Colors.CYAN}│{Colors.END}  {Colors.BOLD}SSD{Colors.END}  {get_bar(disk_percent)} {disk_color}{disk_percent:5.1f}%{Colors.END}     {Colors.CYAN}│{Colors.END}")
    print(f"{Colors.CYAN}│{Colors.END}  {Colors.DIM}Frei: {disk.free/(1024**3):.1f} GB | Total: {disk.total/(1024**3):.1f} GB{Colors.END}      {Colors.CYAN}│{Colors.END}")
    
    # Netzwerk
    net = get_network()
    print(f"{Colors.CYAN}├────────────────────────────────────────┤{Colors.END}")
    print(f"{Colors.CYAN}│{Colors.END}  {Colors.BOLD}NET{Colors.END}  ↓ {net['recv']}  ↑ {net['sent']}          {Colors.CYAN}│{Colors.END}")
    
    # Disk IO
    dio = get_disk_io()
    print(f"{Colors.CYAN}│{Colors.END}  {Colors.BOLD}I/O{Colors.END}  R: {dio['read']}  W: {dio['write']}        {Colors.CYAN}│{Colors.END}")
    
    # Top Prozesse
    print(f"{Colors.CYAN}├────────────────────────────────────────┤{Colors.END}")
    print(f"{Colors.CYAN}│{Colors.END}  {Colors.BOLD}TOP PROZESSE (CPU):{Colors.END}                  {Colors.CYAN}│{Colors.END}")
    procs = get_top_processes(4)
    for p in procs:
        name = p['name'][:18]
        cpu_val = p['cpu_percent'] or 0
        mem_val = p['memory_percent'] or 0
        print(f"{Colors.CYAN}│{Colors.END}  {name:18s} {cpu_val:5.1f}% {mem_val:5.1f}%    {Colors.CYAN}│{Colors.END}")
    
    # Alerts
    print(f"{Colors.CYAN}├────────────────────────────────────────┤{Colors.END}")
    alerts = []
    if cpu > 80:
        alerts.append(f"{Colors.RED}🚨 CPU KRITISCH: {cpu:.1f}%{Colors.END}")
    elif cpu > 60:
        alerts.append(f"{Colors.YELLOW}⚠️ CPU hoch: {cpu:.1f}%{Colors.END}")
    
    if mem.percent > 90:
        alerts.append(f"{Colors.RED}🚨 RAM KRITISCH: {mem.percent:.1f}%{Colors.END}")
    elif mem.percent > 75:
        alerts.append(f"{Colors.YELLOW}⚠️ RAM hoch: {mem.percent:.1f}%{Colors.END}")
    
    if disk_percent > 90:
        alerts.append(f"{Colors.RED}🚨 SSD KRITISCH: {disk_percent:.1f}%{Colors.END}")
    elif disk_percent > 80:
        alerts.append(f"{Colors.YELLOW}⚠️ SSD fast voll: {disk_percent:.1f}%{Colors.END}")
    
    if alerts:
        for alert in alerts:
            print(f"{Colors.CYAN}│{Colors.END}  {alert:34s}  {Colors.CYAN}│{Colors.END}")
    else:
        print(f"{Colors.CYAN}│{Colors.END}  {Colors.GREEN}✅ System OK{Colors.END}                           {Colors.CYAN}│{Colors.END}")
    
    # OpenCLAW Bridge Status
    bridge_status = "🤖 CONNECTED" if openclaw_bridge and openclaw_bridge.connected else "⚠️ DISCONNECTED"
    bridge_color = Colors.GREEN if openclaw_bridge and openclaw_bridge.connected else Colors.YELLOW
    
    print(f"{Colors.CYAN}├────────────────────────────────────────┤{Colors.END}")
    print(f"{Colors.CYAN}│{Colors.END}  {Colors.BOLD}OPENCLAW BRIDGE{Colors.END}                      {Colors.CYAN}│{Colors.END}")
    print(f"{Colors.CYAN}│{Colors.END}  {bridge_color}{bridge_status}{Colors.END}                        {Colors.CYAN}│{Colors.END}")
    print(f"{Colors.CYAN}├────────────────────────────────────────┤{Colors.END}")
    print(f"{Colors.CYAN}│{Colors.END}  {Colors.DIM}[Ctrl+C] zum Beenden{Colors.END}                {Colors.CYAN}│{Colors.END}")
    print(f"{Colors.CYAN}│{Colors.END}  {Colors.DIM}[1] Optimieren starten{Colors.END}                {Colors.CYAN}│{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}└────────────────────────────────────────┘{Colors.END}")

def run_optimizer():
    os.system("cd /Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project && python3 mac-optimizer.py --optimize")
    input("Druecke Enter zum Fortfahren...")

def main():
    import select
    import termios
    import tty
    
    # OpenCLAW Bridge initialisieren
    openclaw_bridge = OpenCLAWBridge()
    
    # Terminal auf non-blocking setzen
    old_settings = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        
        while True:
            draw_monitor(openclaw_bridge)
            
            # System-Daten sammeln und an OpenCLAW senden
            system_data = collect_system_data()
            openclaw_bridge.send_system_data(system_data)
            
            # Warte 2 Sekunden, pruefe auf Tastendruck
            start = time.time()
            while time.time() - start < 2:
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    key = sys.stdin.read(1)
                    if key == '\x03':  # Ctrl+C
                        raise KeyboardInterrupt
                    elif key == '1':
                        # Terminal zuruecksetzen fuer Optimizer
                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                        run_optimizer()
                        tty.setcbreak(sys.stdin.fileno())
                        break
                time.sleep(0.1)
                
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        print(f"\n{Colors.GREEN}✅ Monitor beendet{Colors.END}")

def collect_system_data():
    """Sammle alle System-Daten fuer OpenCLAW Bridge"""
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Top Prozesse
        procs = get_top_processes(5)
        
        # System-Daten zusammenstellen
        system_data = {
            'cpu': cpu,
            'memory': {
                'percent': mem.percent,
                'used_gb': mem.used / (1024**3),
                'total_gb': mem.total / (1024**3),
                'available_gb': mem.available / (1024**3)
            },
            'disk': {
                'percent': disk.percent,
                'free_gb': disk.free / (1024**3),
                'total_gb': disk.total / (1024**3)
            },
            'processes': procs,
            'network': get_network(),
            'disk_io': get_disk_io(),
            'timestamp': datetime.now().isoformat()
        }
        
        return system_data
        
    except Exception as e:
        return {
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

if __name__ == "__main__":
    main()
