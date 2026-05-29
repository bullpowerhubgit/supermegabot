#!/usr/bin/env python3
"""
🚀 PROFESSIONAL DESKTOP MONITORING SERVER
==========================================

Ultimate RudiBot System - Professional Desktop Monitoring with Web Dashboard
Real-time System Performance & Bot Health Monitoring

Features:
- Real-time CPU, Memory, Disk Monitoring
- Network Performance Tracking
- Bot Health & Status Monitoring
- Automated Alert System
- Beautiful Web Dashboard Interface
- Historical Data Analysis
- WebSocket Real-time Updates
- REST API for Integration
"""

import psutil
import time
import json
import os
import subprocess
import threading
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import platform

# Import GCP configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from gcp_config import gcp_config
import socket
from flask import Flask, render_template, jsonify, Response
from flask_socketio import SocketIO, emit
import eventlet

# Initialize Flask with SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'supermegabot-monitor-secret-key-2024'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Configuration
MONITORING_CONFIG = {
    'update_interval': 1,  # seconds
    'history_length': 3600,  # 1 hour of data
    'alert_thresholds': {
        'cpu': 90,  # percent
        'memory': 85,  # percent
        'disk': 90,  # percent
        'network': 100,  # MB/s
    },
    'server_port': 8888
}

@dataclass
class SystemMetrics:
    """System performance metrics"""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    network_sent_mb: float
    network_recv_mb: float
    network_speed_up: float
    network_speed_down: float
    active_processes: int
    bot_processes: int
    system_load: float
    uptime_hours: float
    temperature: str

@dataclass
class BotMetrics:
    """Bot-specific metrics"""
    timestamp: float
    bot_name: str
    status: str
    cpu_usage: float
    memory_usage: float
    response_time: float
    interactions: int
    errors: int
    uptime: float

class ProfessionalDesktopMonitor:
    """Professional Desktop Monitoring System"""
    
    def __init__(self):
        self.running = False
        self.metrics_history = deque(maxlen=MONITORING_CONFIG['history_length'])
        self.bot_metrics = deque(maxlen=MONITORING_CONFIG['history_length'])
        self.alerts = deque(maxlen=100)
        self.last_network_stats = None
        self.start_time = time.time()
        self.monitoring_thread = None
        
        # Initialize monitoring
        self.initialize_monitoring()
        
    def initialize_monitoring(self):
        """Initialize monitoring system"""
        print("🚀 Initializing Professional Desktop Monitor Server...")
        print(f"📊 System: {platform.system()} {platform.release()}")
        print(f"💻 CPU: {platform.processor()}")
        print(f"🧠 Memory: {psutil.virtual_memory().total / (1024**3):.2f} GB")
        print(f"💾 Disk: {psutil.disk_usage('/').total / (1024**3):.2f} GB")
        print(f"🌐 Server Port: {MONITORING_CONFIG['server_port']}")
        print("✅ Monitoring initialized successfully")
        
    def get_system_metrics(self) -> SystemMetrics:
        """Get current system metrics"""
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        
        # Memory metrics
        memory = psutil.virtual_memory()
        memory_used_gb = memory.used / (1024**3)
        memory_total_gb = memory.total / (1024**3)
        
        # Disk metrics
        disk = psutil.disk_usage('/')
        disk_used_gb = disk.used / (1024**3)
        disk_total_gb = disk.total / (1024**3)
        
        # Network metrics
        network = psutil.net_io_counters()
        network_sent_mb = network.bytes_sent / (1024**2)
        network_recv_mb = network.bytes_recv / (1024**2)
        
        # Calculate network speed
        network_speed_up = 0
        network_speed_down = 0
        if self.last_network_stats:
            time_diff = time.time() - self.last_network_stats['timestamp']
            if time_diff > 0:
                sent_diff = network.bytes_sent - self.last_network_stats['bytes_sent']
                recv_diff = network.bytes_recv - self.last_network_stats['bytes_recv']
                network_speed_up = (sent_diff / time_diff) / (1024**2)  # MB/s
                network_speed_down = (recv_diff / time_diff) / (1024**2)  # MB/s
        
        self.last_network_stats = {
            'timestamp': time.time(),
            'bytes_sent': network.bytes_sent,
            'bytes_recv': network.bytes_recv
        }
        
        # Process metrics
        active_processes = len(psutil.pids())
        bot_processes = self.count_bot_processes()
        
        # System load
        system_load = psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else cpu_percent / cpu_count
        
        # Uptime
        uptime_hours = (time.time() - psutil.boot_time()) / 3600
        
        # Temperature
        temperature = self.get_temperature()
        
        return SystemMetrics(
            timestamp=time.time(),
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_used_gb=memory_used_gb,
            memory_total_gb=memory_total_gb,
            disk_percent=disk.percent,
            disk_used_gb=disk_used_gb,
            disk_total_gb=disk_total_gb,
            network_sent_mb=network_sent_mb,
            network_recv_mb=network_recv_mb,
            network_speed_up=network_speed_up,
            network_speed_down=network_speed_down,
            active_processes=active_processes,
            bot_processes=bot_processes,
            system_load=system_load,
            uptime_hours=uptime_hours,
            temperature=temperature
        )
    
    def get_temperature(self) -> str:
        """Get CPU temperature"""
        try:
            result = subprocess.run(['osx-cpu-temp'], capture_output=True, text=True, timeout=2)
            return result.stdout.strip()
        except Exception:
            return "N/A"
    
    def count_bot_processes(self) -> int:
        """Count running bot processes"""
        bot_count = 0
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'bot' in cmdline.lower() or 'telegram' in cmdline.lower() or 'node' in cmdline.lower():
                    bot_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return bot_count
    
    def get_bot_metrics(self) -> List[BotMetrics]:
        """Get metrics for all running bots"""
        bot_metrics = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_info', 'create_time']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'bot' in cmdline.lower() or 'telegram' in cmdline.lower() or 'node' in cmdline.lower():
                    bot_metrics.append(BotMetrics(
                        timestamp=time.time(),
                        bot_name=proc.info['name'],
                        status='running',
                        cpu_usage=proc.info['cpu_percent'] or 0,
                        memory_usage=proc.info['memory_info'].rss / (1024**2) if proc.info['memory_info'] else 0,
                        response_time=0,
                        interactions=0,
                        errors=0,
                        uptime=time.time() - proc.info['create_time']
                    ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return bot_metrics
    
    def check_alerts(self, metrics: SystemMetrics):
        """Check for alert conditions"""
        thresholds = MONITORING_CONFIG['alert_thresholds']
        new_alerts = []
        
        if metrics.cpu_percent > thresholds['cpu']:
            alert = {
                'timestamp': datetime.now().isoformat(),
                'type': 'CPU',
                'severity': 'critical' if metrics.cpu_percent > 95 else 'warning',
                'message': f"CPU usage high: {metrics.cpu_percent:.1f}%"
            }
            self.alerts.append(alert)
            new_alerts.append(alert)
        
        if metrics.memory_percent > thresholds['memory']:
            alert = {
                'timestamp': datetime.now().isoformat(),
                'type': 'Memory',
                'severity': 'critical' if metrics.memory_percent > 95 else 'warning',
                'message': f"Memory usage high: {metrics.memory_percent:.1f}%"
            }
            self.alerts.append(alert)
            new_alerts.append(alert)
        
        if metrics.disk_percent > thresholds['disk']:
            alert = {
                'timestamp': datetime.now().isoformat(),
                'type': 'Disk',
                'severity': 'critical',
                'message': f"Disk usage high: {metrics.disk_percent:.1f}%"
            }
            self.alerts.append(alert)
            new_alerts.append(alert)
        
        if metrics.network_speed_up > thresholds['network']:
            alert = {
                'timestamp': datetime.now().isoformat(),
                'type': 'Network',
                'severity': 'warning',
                'message': f"Network upload speed high: {metrics.network_speed_up:.1f} MB/s"
            }
            self.alerts.append(alert)
            new_alerts.append(alert)
        
        return new_alerts
    
    def monitoring_loop(self):
        """Main monitoring loop"""
        print("🔄 Starting monitoring loop...")
        
        while self.running:
            try:
                # Get system metrics
                metrics = self.get_system_metrics()
                self.metrics_history.append(metrics)
                
                # Get bot metrics
                bot_metrics = self.get_bot_metrics()
                for bot_metric in bot_metrics:
                    self.bot_metrics.append(bot_metric)
                
                # Check for alerts
                new_alerts = self.check_alerts(metrics)
                
                # Emit real-time updates via WebSocket
                socketio.emit('metrics_update', {
                    'system': asdict(metrics),
                    'bots': [asdict(b) for b in bot_metrics],
                    'alerts': new_alerts,
                    'timestamp': datetime.now().isoformat()
                })
                
                time.sleep(MONITORING_CONFIG['update_interval'])
                
            except Exception as e:
                print(f"❌ Monitoring error: {e}")
                time.sleep(5)
    
    def start(self):
        """Start monitoring"""
        if self.running:
            print("⚠️  Monitoring is already running")
            return
        
        self.running = True
        self.monitoring_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        print("✅ Professional Desktop Monitor started")
    
    def stop(self):
        """Stop monitoring"""
        self.running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        print("🛑 Professional Desktop Monitor stopped")

# Global monitor instance
monitor = ProfessionalDesktopMonitor()

# Flask Routes
@app.route('/')
def index():
    """Serve the dashboard"""
    return render_template('dashboard.html')

@app.route('/api/metrics')
def get_metrics():
    """Get current metrics"""
    if monitor.metrics_history:
        latest = monitor.metrics_history[-1]
        return jsonify(asdict(latest))
    return jsonify({'error': 'No metrics available'})

@app.route('/api/history')
def get_history():
    """Get metrics history"""
    history = list(monitor.metrics_history)[-60:]  # Last 60 data points
    return jsonify([asdict(m) for m in history])

@app.route('/api/bots')
def get_bots():
    """Get bot metrics"""
    bots = list(monitor.bot_metrics)[-10:]  # Last 10 bot metrics
    return jsonify([asdict(b) for b in bots])

@app.route('/api/alerts')
def get_alerts():
    """Get recent alerts"""
    alerts = list(monitor.alerts)[-20:]  # Last 20 alerts
    return jsonify(alerts)

@app.route('/api/status')
def get_status():
    """Get monitoring status"""
    return jsonify({
        'running': monitor.running,
        'uptime': time.time() - monitor.start_time,
        'metrics_count': len(monitor.metrics_history),
        'alerts_count': len(monitor.alerts),
        'bot_processes': monitor.count_bot_processes()
    })

@app.route('/api/report')
def get_report():
    """Generate performance report"""
    if not monitor.metrics_history:
        return jsonify({'error': 'No metrics available'})
    
    recent_metrics = list(monitor.metrics_history)[-60:]
    
    avg_cpu = sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics)
    avg_memory = sum(m.memory_percent for m in recent_metrics) / len(recent_metrics)
    max_cpu = max(m.cpu_percent for m in recent_metrics)
    max_memory = max(m.memory_percent for m in recent_metrics)
    
    return jsonify({
        'generated_at': datetime.now().isoformat(),
        'monitoring_duration': (time.time() - monitor.start_time) / 60,
        'average_cpu': avg_cpu,
        'average_memory': avg_memory,
        'peak_cpu': max_cpu,
        'peak_memory': max_memory,
        'total_alerts': len(monitor.alerts),
        'active_bot_processes': recent_metrics[-1].bot_processes if recent_metrics else 0
    })

# SocketIO Events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print(f"🔗 Client connected: {request.sid}")
    emit('connected', {'message': 'Connected to Professional Desktop Monitor'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print(f"🔌 Client disconnected: {request.sid}")

def main():
    """Main function"""
    # Start monitoring
    monitor.start()
    
    # Start Flask server with SocketIO
    port = MONITORING_CONFIG['server_port']
    print(f"🌐 Starting web server on port {port}...")
    print(f"📊 Dashboard available at: http://localhost:{port}")
    
    try:
        socketio.run(app, host='0.0.0.0', port=port, debug=False)
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitor...")
        monitor.stop()

if __name__ == '__main__':
    main()
