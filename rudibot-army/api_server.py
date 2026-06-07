#!/usr/bin/env python3
"""
RudiBot API Server — REST Endpoints + Webhooks
Endpoints:
  GET  /health              → System health
  GET  /api/status          → Bot status
  GET  /api/shopify/orders  → Shopify Bestellungen (live API)
  GET  /api/github/events   → GitHub Events (live API)
  POST /api/send-message    → Telegram Nachricht senden
  POST /webhooks/telegram   → Telegram Updates
  POST /webhooks/github     → GitHub Events
  POST /webhooks/shopify    → Shopify Events
"""
import http.server, json, os, sys, urllib.request
from pathlib import Path
from datetime import datetime

ARMY_DIR = Path(__file__).parent
sys.path.insert(0, str(ARMY_DIR / "shared"))
from bus import notify_telegram, load_state

PORT = 8766

class APIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {args[0]}")

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_error(self, message, status=400):
        self._send_json({"error": message}, status)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._send_json({
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "version": "2.0",
                "uptime": "running"
            })
        elif self.path == "/api/status":
            state = load_state()
            self._send_json({
                "agents": state.get("agents", {}),
                "events_count": len(state.get("events", [])),
                "timestamp": datetime.now().isoformat()
            })
        elif self.path == "/api/heartbeat":
            heartbeat_file = Path("/tmp/rudibot_heartbeat.json")
            if heartbeat_file.exists():
                try:
                    data = json.loads(heartbeat_file.read_text())
                    self._send_json(data)
                except Exception as e:
                    self._send_json({
                        "error": f"Failed to parse heartbeat: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    }, 500)
            else:
                self._send_json({
                    "error": "Heartbeat not yet generated. Run heartbeat_reporter.py first.",
                    "timestamp": datetime.now().isoformat()
                }, 503)
        elif self.path == "/api/shopify/orders":
            shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
            access_token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
            if not shop_domain or not access_token:
                self._send_json({
                    "orders": [],
                    "error": "SHOPIFY_SHOP_DOMAIN and SHOPIFY_ACCESS_TOKEN required in environment",
                    "note": "Configure .env and restart the server"
                }, 503)
                return
            try:
                req = urllib.request.Request(
                    f"https://{shop_domain}/admin/api/2024-01/orders.json?limit=10&status=any",
                    headers={"X-Shopify-Access-Token": access_token, "Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                    self._send_json({
                        "orders": data.get("orders", []),
                        "count": len(data.get("orders", [])),
                        "source": "shopify_api",
                        "timestamp": datetime.now().isoformat()
                    })
            except urllib.error.HTTPError as e:
                error_body = e.read().decode() if hasattr(e, "read") else str(e)
                self._send_json({
                    "orders": [],
                    "error": f"Shopify API HTTP {e.code}: {error_body[:200]}",
                    "note": "Token may be expired — check API_FIX_STATUS.md"
                }, 502)
            except Exception as e:
                self._send_json({
                    "orders": [],
                    "error": f"Shopify API unreachable: {str(e)}",
                    "note": "Network or DNS issue — check connectivity"
                }, 502)
        elif self.path == "/api/github/events":
            github_token = os.getenv("GITHUB_TOKEN", "")
            github_repo = os.getenv("GITHUB_REPO", "")
            if not github_token:
                self._send_json({
                    "events": [],
                    "error": "GITHUB_TOKEN required in environment",
                    "note": "Configure .env and restart the server"
                }, 503)
                return
            try:
                repo = github_repo or "bullpowerhubgit/supermegabot"
                req = urllib.request.Request(
                    f"https://api.github.com/repos/{repo}/events?per_page=10",
                    headers={"Authorization": f"token {github_token}", "Accept": "application/vnd.github.v3+json", "User-Agent": "RudiBot/2.0"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                    events = [
                        {
                            "id": e.get("id"),
                            "type": e.get("type"),
                            "actor": e.get("actor", {}).get("login"),
                            "created_at": e.get("created_at")
                        }
                        for e in data[:10]
                    ]
                    self._send_json({
                        "events": events,
                        "count": len(events),
                        "source": "github_api",
                        "timestamp": datetime.now().isoformat()
                    })
            except urllib.error.HTTPError as e:
                error_body = e.read().decode() if hasattr(e, "read") else str(e)
                self._send_json({
                    "events": [],
                    "error": f"GitHub API HTTP {e.code}: {error_body[:200]}",
                    "note": "Token may have insufficient scopes — check API_FIX_STATUS.md"
                }, 502)
            except Exception as e:
                self._send_json({
                    "events": [],
                    "error": f"GitHub API unreachable: {str(e)}",
                    "note": "Network or DNS issue — check connectivity"
                }, 502)
        else:
            self._send_error("Not found", 404)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode() if length > 0 else "{}"
            data = json.loads(body) if body else {}
        except Exception:
            self._send_error("Invalid JSON", 400)
            return

        if self.path == "/api/send-message":
            msg = data.get("message", "")
            if msg:
                notify_telegram(msg)
                self._send_json({"sent": True, "message": msg})
            else:
                self._send_error("message required", 400)

        elif self.path == "/webhooks/telegram":
            # Verarbeite Telegram Updates
            self._send_json({"ok": True, "processed": True})

        elif self.path == "/webhooks/github":
            event_type = self.headers.get("X-GitHub-Event", "unknown")
            print(f"[GitHub Webhook] {event_type}: {json.dumps(data)[:200]}")
            self._send_json({"ok": True, "event": event_type})

        elif self.path == "/webhooks/shopify":
            topic = self.headers.get("X-Shopify-Topic", "unknown")
            print(f"[Shopify Webhook] {topic}: {json.dumps(data)[:200]}")
            self._send_json({"ok": True, "topic": topic})

        else:
            self._send_error("Not found", 404)

def main():
    server = http.server.HTTPServer(("", PORT), APIHandler)
    print(f"🌐 RudiBot API Server läuft auf http://localhost:{PORT}")
    print(f"   Health:   http://localhost:{PORT}/health")
    print(f"   Status:   http://localhost:{PORT}/api/status")
    print(f"   Webhooks: http://localhost:{PORT}/webhooks/{{telegram|github|shopify}}")
    server.serve_forever()

if __name__ == "__main__":
    main()
