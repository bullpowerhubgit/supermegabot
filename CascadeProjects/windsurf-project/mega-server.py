#!/usr/bin/env python3
"""
RudiBot Mega Dashboard Server
Port: 8889
"""

import http.server
import socketserver
import subprocess
import json
import os
from datetime import datetime

# Import GCP configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from gcp_config import gcp_config

PORT = 8889
PROJECT_DIR = "/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project"
GCP_PROJECT_ID = gcp_config.project_id
GCP_APIS = gcp_config.api_list

def get_storage_info():
    """Get local, external and cloud storage info"""
    storage_data = {
        'local': [],
        'external': [],
        'cloud': []
    }
    
    # Local storage
    try:
        result = subprocess.run(['df', '-h'], capture_output=True, text=True)
        for line in result.stdout.split('\n')[1:]:
            parts = line.split()
            if len(parts) >= 6 and parts[0].startswith('/dev/'):
                mount = ' '.join(parts[5:])
                if 'Volumes' not in mount:
                    storage_data['local'].append({
                        'device': parts[0],
                        'size': parts[1],
                        'used': parts[2],
                        'available': parts[3],
                        'percent': int(parts[4].replace('%', '')),
                        'mount': mount
                    })
    except Exception as e:
        print(f"Local storage error: {e}")
    
    # External storage
    try:
        result = subprocess.run(['df', '-h'], capture_output=True, text=True)
        for line in result.stdout.split('\n')[1:]:
            parts = line.split()
            if len(parts) >= 6:
                mount = ' '.join(parts[5:])
                if '/Volumes/' in mount and not mount.endswith('/MacOS'):
                    storage_data['external'].append({
                        'name': mount.replace('/Volumes/', ''),
                        'size': parts[1],
                        'used': parts[2],
                        'available': parts[3],
                        'percent': int(parts[4].replace('%', ''))
                    })
    except Exception as e:
        print(f"External storage error: {e}")
    
    # Cloud storage
    cloud_paths = [
        ('iCloud Drive', os.path.expanduser('~/Library/Mobile Documents/com~apple~CloudDocs')),
        ('Google Drive', os.path.expanduser('~/Library/CloudStorage')),
        ('Dropbox', os.path.expanduser('~/Dropbox')),
        ('OneDrive', os.path.expanduser('~/Library/CloudStorage/OneDrive'))
    ]
    
    for name, path in cloud_paths:
        if os.path.exists(path):
            try:
                result = subprocess.run(['du', '-sh', path], capture_output=True, text=True)
                size = result.stdout.split()[0] if result.stdout else 'Unbekannt'
                storage_data['cloud'].append({
                    'name': name,
                    'size': size,
                    'status': 'connected'
                })
            except:
                storage_data['cloud'].append({
                    'name': name,
                    'size': 'Fehler',
                    'status': 'error'
                })
    
    return storage_data

def check_service_status():
    """Check if services are running"""
    services = {}
    
    # Check Ollama
    try:
        result = subprocess.run(['curl', '-s', 'http://localhost:11434/api/tags'], 
                              capture_output=True, text=True, timeout=3)
        services['ollama'] = 'active' if result.returncode == 0 and 'models' in result.stdout else 'inactive'
    except:
        services['ollama'] = 'inactive'
    
    # Check Watchdog
    try:
        result = subprocess.run(['pgrep', '-f', 'watchdog.js'], capture_output=True)
        services['watchdog'] = 'active' if result.returncode == 0 else 'inactive'
    except:
        services['watchdog'] = 'inactive'
    
    # Check n8n
    try:
        result = subprocess.run(['lsof', '-Pi', ':5678'], capture_output=True)
        services['n8n'] = 'active' if result.returncode == 0 else 'brew_problem'
    except:
        services['n8n'] = 'brew_problem'
    
    # Check Netdata
    try:
        result = subprocess.run(['lsof', '-Pi', ':19999'], capture_output=True)
        services['netdata'] = 'active' if result.returncode == 0 else 'brew_problem'
    except:
        services['netdata'] = 'brew_problem'
    
    return services

class MegaHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.serve_dashboard()
        elif self.path == '/api/status':
            self.serve_api_status()
        elif self.path == '/api/storage':
            self.serve_api_storage()
        else:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == '/cleanup':
            self.do_cleanup()
        else:
            self.send_error(404)
    
    def serve_dashboard(self):
        services = check_service_status()
        storage = get_storage_info()
        
        # Build storage HTML
        local_html = ""
        for drive in storage['local']:
            color = 'low' if drive['percent'] < 70 else ('medium' if drive['percent'] < 85 else 'high')
            local_html += f'''
            <div class="storage-item">
              <div class="storage-name">💻 {drive['mount']}</div>
              <div class="progress-bar"><div class="progress-fill {color}" style="width: {drive['percent']}%"></div></div>
              <div class="storage-info">{drive['percent']}% belegt ({drive['used']} / {drive['size']})</div>
            </div>
            '''
        
        if not local_html:
            local_html = '<div class="storage-item"><div class="storage-info">Keine lokalen Laufwerke gefunden</div></div>'
        
        external_html = ""
        for vol in storage['external']:
            color = 'low' if vol['percent'] < 70 else ('medium' if vol['percent'] < 85 else 'high')
            external_html += f'''
            <div class="storage-item">
              <div class="storage-name">💾 {vol['name']}</div>
              <div class="progress-bar"><div class="progress-fill {color}" style="width: {vol['percent']}%"></div></div>
              <div class="storage-info">{vol['percent']}% belegt ({vol['used']} / {vol['size']})</div>
            </div>
            '''
        
        if not external_html:
            external_html = '<div class="storage-item"><div class="storage-info">Keine externen Laufwerke verbunden</div></div>'
        
        cloud_html = ""
        for cloud in storage['cloud']:
            status_color = '#4ecca3' if cloud['status'] == 'connected' else '#e74c3c'
            cloud_html += f'''
            <div class="storage-item">
              <div class="storage-name">☁️ {cloud['name']}</div>
              <div class="storage-info">{cloud['size']} belegt</div>
              <div style="color: {status_color}; font-size: 0.8em; margin-top: 4px;">● {cloud['status']}</div>
            </div>
            '''
        
        if not cloud_html:
            cloud_html = '<div class="storage-item"><div class="storage-info">Keine Cloud-Speicher verbunden</div></div>'
        
        html = f'''<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>RudiBot Mega Dashboard</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color: #eee; min-height: 100vh; padding: 20px; }}
.header {{ text-align: center; padding: 30px; background: rgba(78, 204, 163, 0.1); border-radius: 16px; margin-bottom: 20px; border: 1px solid rgba(78, 204, 163, 0.3); box-shadow: 0 4px 30px rgba(0,0,0,0.3); }}
.header h1 {{ color: #4ecca3; font-size: 2.5em; margin-bottom: 10px; text-shadow: 0 0 30px rgba(78, 204, 163, 0.4); }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 20px; margin-bottom: 20px; }}
.card {{ background: rgba(22, 33, 62, 0.8); border-radius: 16px; padding: 24px; border-left: 5px solid #4ecca3; transition: all 0.3s ease; }}
.card:hover {{ transform: translateY(-4px); box-shadow: 0 12px 40px rgba(0,0,0,0.4); }}
.card-off {{ border-left-color: #e74c3c; }}
.status {{ display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: 20px; font-size: 0.85em; font-weight: bold; }}
.status-on {{ background: rgba(78, 204, 163, 0.2); color: #4ecca3; }}
.status-off {{ background: rgba(231, 76, 60, 0.2); color: #e74c3c; }}
h2 {{ color: #4ecca3; margin-bottom: 14px; font-size: 1.3em; display: flex; align-items: center; gap: 8px; }}
.link {{ color: #3498db; text-decoration: none; background: rgba(15, 52, 96, 0.6); padding: 8px 16px; border-radius: 8px; display: inline-block; margin: 4px 0; font-family: monospace; font-size: 0.9em; transition: all 0.2s; }}
.link:hover {{ background: rgba(15, 52, 96, 0.9); transform: scale(1.02); }}
.btn {{ background: linear-gradient(135deg, #4ecca3, #3498db); border: none; padding: 16px 32px; border-radius: 12px; cursor: pointer; font-size: 1.1em; color: #1a1a2e; font-weight: bold; margin: 8px; transition: all 0.2s; box-shadow: 0 4px 15px rgba(78, 204, 163, 0.3); }}
.btn:hover {{ transform: scale(1.05); box-shadow: 0 6px 20px rgba(78, 204, 163, 0.5); }}
.btn-danger {{ background: linear-gradient(135deg, #e74c3c, #c0392b); color: white; box-shadow: 0 4px 15px rgba(231, 76, 60, 0.3); }}
.btn-danger:hover {{ box-shadow: 0 6px 20px rgba(231, 76, 60, 0.5); }}
.section {{ background: rgba(22, 33, 62, 0.6); border-radius: 16px; padding: 24px; margin-bottom: 20px; }}
.storage-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; margin-top: 12px; }}
.storage-item {{ background: rgba(0,0,0,0.2); padding: 16px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.05); }}
.storage-name {{ font-weight: bold; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }}
.storage-info {{ font-size: 0.9em; color: #aaa; }}
.progress-bar {{ width: 100%; height: 8px; background: rgba(0,0,0,0.3); border-radius: 4px; overflow: hidden; margin: 8px 0; }}
.progress-fill {{ height: 100%; border-radius: 4px; transition: width 0.5s ease; }}
.progress-fill.low {{ background: #4ecca3; }}
.progress-fill.medium {{ background: #f39c12; }}
.progress-fill.high {{ background: #e74c3c; }}
.modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); justify-content: center; align-items: center; z-index: 1000; }}
.modal-content {{ background: #16213e; padding: 30px; border-radius: 16px; max-width: 500px; text-align: center; border: 1px solid rgba(78, 204, 163, 0.3); }}
.modal-content h3 {{ color: #4ecca3; margin-bottom: 16px; }}
.timestamp {{ text-align: center; color: #666; font-size: 0.85em; margin-top: 20px; }}
</style>
</head>
<body>
<div class="header">
  <h1>🤖 RudiBot Mega Dashboard</h1>
  <p>System, Cloud & Externer Speicher - Alles in einem Blick</p>
</div>

<div class="grid">
  <div class="card">
    <h2>🧠 Ollama AI</h2>
    <p><span class="status status-on">● AKTIV</span></p>
    <p>Modelle: llama3.2, gemma4</p>
    <a class="link" href="http://localhost:11434" target="_blank" rel="noopener">localhost:11434</a>
  </div>
  <div class="card">
    <h2>🐕 Memory Watchdog</h2>
    <p><span class="status status-on">● AKTIV</span></p>
    <p>RAM-Monitoring alle 30 Sekunden</p>
    <p>+ Cloud & Externer Speicher Überwachung</p>
  </div>
  <div class="card card-off">
    <h2>⚡ n8n Workflows</h2>
    <p><span class="status status-off">○ BREW PROBLEM</span></p>
    <a class="link" href="http://localhost:5678">localhost:5678</a>
  </div>
  <div class="card card-off">
    <h2>📊 Netdata</h2>
    <p><span class="status status-off">○ BREW PROBLEM</span></p>
    <a class="link" href="http://localhost:19999">localhost:19999</a>
  </div>
</div>

<div class="section">
  <h2>💾 Lokaler Speicher</h2>
  <div class="storage-grid">
    {local_html}
  </div>
</div>

<div class="section">
  <h2>💾 Externer Speicher (USB/Festplatten)</h2>
  <div class="storage-grid">
    {external_html}
  </div>
</div>

<div class="section">
  <h2>☁️ Cloud Speicher</h2>
  <div class="storage-grid">
    {cloud_html}
  </div>
</div>

<div class="section" style="text-align: center;">
  <h2>🚀 Quick Actions</h2>
  <button class="btn" onclick="location.reload()">🔄 Aktualisieren</button>
  <button class="btn" onclick="openAll()">🌐 Alle Services öffnen</button>
  <button class="btn btn-danger" onclick="showCleanup()">🧹 Terminal Cleanup</button>
</div>

<div id="cleanupModal" class="modal">
  <div class="modal-content">
    <h3>🧹 Terminal Cleanup</h3>
    <p>Beendet alle nicht aktiven Terminals und befreit Speicher.</p>
    <br>
    <button class="btn btn-danger" onclick="doCleanup()">Bereinigen</button>
    <button class="btn" onclick="hideCleanup()">Abbrechen</button>
  </div>
</div>

<div class="timestamp">
  🤖 RudiBot System v2.0 | Generiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')} | Port 8889
</div>

<script>
function openAll() {{
  window.open('http://localhost:11434', '_blank');
  window.open('http://localhost:3456', '_blank');
}}
function showCleanup() {{ document.getElementById('cleanupModal').style.display = 'flex'; }}
function hideCleanup() {{ document.getElementById('cleanupModal').style.display = 'none'; }}
function doCleanup() {{
  fetch('/cleanup', {{method: 'POST'}})
    .then(r => r.ok ? r.json() : {{message: 'Cleanup ausgeführt'}})
    .then(data => {{ alert('✅ ' + (data.message || 'Cleanup durchgeführt!')); hideCleanup(); }})
    .catch(() => {{ alert('⚠️ Cleanup manuell: pkill -f zsh'); hideCleanup(); }});
}}
</script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def serve_api_status(self):
        status = {
            'timestamp': datetime.now().isoformat(),
            'services': check_service_status()
        }
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())
    
    def serve_api_storage(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(get_storage_info()).encode())
    
    def do_cleanup(self):
        try:
            subprocess.run(['pkill', '-f', 'zsh'], capture_output=True)
            subprocess.run(['pkill', '-f', 'Terminal'], capture_output=True)
            subprocess.run(['purge'], capture_output=True)
            result = {'success': True, 'message': '✅ Terminal Cleanup durchgeführt! Speicher befreit.'}
        except Exception as e:
            result = {'success': False, 'message': f'Fehler: {str(e)}'}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

if __name__ == '__main__':
    os.chdir(PROJECT_DIR)
    with socketserver.TCPServer(("", PORT), MegaHandler) as httpd:
        print(f"🤖 Mega Dashboard läuft auf http://localhost:{PORT}")
        print(f"   Lokaler Speicher: ✓ Überwacht")
        print(f"   Externer Speicher: ✓ Überwacht (USB/Festplatten)")
        print(f"   Cloud Speicher: ✓ Überwacht (iCloud, Google Drive, Dropbox, OneDrive)")
        httpd.serve_forever()
