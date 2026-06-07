#!/usr/bin/env python3
"""Mini HTTP Server für das Dashboard — serviert HTML + JSON + platform-links"""
import http.server, socketserver, json, os, subprocess
from pathlib import Path
from datetime import datetime

ARMY_DIR = Path(__file__).parent
PORT = 8765

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ARMY_DIR), **kwargs)

    def do_GET(self):
        # CORS headers für fetch()
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

        if self.path == "/" or self.path == "/dashboard.html":
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = (ARMY_DIR / "dashboard.html").read_text()
            self.wfile.write(html.encode())
        elif self.path == "/dashboard_data.json" or self.path.startswith("/dashboard_data.json?"):
            self.send_header("Content-type", "application/json")
            self.end_headers()
            data_file = ARMY_DIR / "dashboard_data.json"
            if data_file.exists():
                self.wfile.write(data_file.read_bytes())
            else:
                self.wfile.write(b'{}')
        elif self.path == "/platform-links":
            self.send_header("Content-type", "text/html")
            self.end_headers()
            links_file = Path.home() / "windsurf" / "platform-links-20.html"
            if links_file.exists():
                self.wfile.write(links_file.read_bytes())
            else:
                self.wfile.write(b'<h1>platform-links-20.html nicht gefunden</h1>')
        else:
            self.end_headers()
            self.wfile.write(b'Not Found')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {args[0]}")

def main():
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"="*50)
        print(f"🌐 Dashboard Server läuft auf http://localhost:{PORT}")
        print(f"   Dashboard: http://localhost:{PORT}/dashboard.html")
        print(f"   JSON Data: http://localhost:{PORT}/dashboard_data.json")
        print(f"   Platform Links: http://localhost:{PORT}/platform-links")
        print(f"="*50)
        httpd.serve_forever()

if __name__ == "__main__":
    main()
