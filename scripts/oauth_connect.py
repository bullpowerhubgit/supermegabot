#!/usr/bin/env python3
"""
Einmaliger OAuth-Verbindungs-Helper für Reddit & Pinterest.
Startet lokalen Server auf Port 9999, öffnet Browser → du autorisierst → Token wird in .env gespeichert.

Nutzung:
    python3 scripts/oauth_connect.py reddit
    python3 scripts/oauth_connect.py pinterest
"""
import os, sys, json, base64, secrets, threading, webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"
CALLBACK_PORT = 9999
CALLBACK_URL  = f"http://localhost:{CALLBACK_PORT}/callback"

_received_code = {}
_server_done   = threading.Event()


class CallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        if "error" in qs:
            _received_code["error"] = qs["error"][0]
        elif "code" in qs:
            _received_code["code"] = qs["code"][0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if "code" in _received_code:
            self.wfile.write(b"<h2>\xe2\x9c\x85 Autorisiert! Dieses Fenster kannst du schlie\xc3\x9fen.</h2>")
        else:
            self.wfile.write(b"<h2>\xe2\x9d\x8c Fehler bei der Autorisierung.</h2>")
        _server_done.set()


def save_env_var(key: str, value: str):
    """Add/update key in .env file."""
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(new_lines) + "\n")
    print(f"  → .env gespeichert: {key}={value[:20]}...")


# ─────────────────────────────────────────── REDDIT ────

def reddit_connect():
    client_id     = os.getenv("REDDIT_CLIENT_ID", "hqgJAQe6Qiu5s5r1Vqc0Og")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "xsH99P7iCQAPeknbAXe5F9Nd9fV7aA")
    state = secrets.token_urlsafe(16)

    auth_url = (
        "https://www.reddit.com/api/v1/authorize?"
        + urlencode({
            "client_id":    client_id,
            "response_type": "code",
            "state":        state,
            "redirect_uri": CALLBACK_URL,
            "duration":     "permanent",
            "scope":        "submit read identity",
        })
    )
    print(f"\n🔑 Reddit OAuth starten...")
    print(f"   Öffne Browser: {auth_url[:80]}...")
    webbrowser.open(auth_url)

    httpd = HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    t = threading.Thread(target=lambda: httpd.handle_request())
    t.daemon = True
    t.start()
    print(f"   Warte auf Reddit-Autorisierung (Port {CALLBACK_PORT})...")
    _server_done.wait(timeout=120)
    httpd.server_close()

    if "error" in _received_code:
        print(f"❌ Reddit Fehler: {_received_code['error']}")
        return

    code = _received_code.get("code", "")
    if not code:
        print("❌ Kein Code empfangen")
        return

    # Exchange code for refresh token
    import urllib.request
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data  = urlencode({
        "grant_type":   "authorization_code",
        "code":         code,
        "redirect_uri": CALLBACK_URL,
    }).encode()
    req = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Basic {creds}",
            "User-Agent":    "SuperMegaBot:v2.0 (by /u/bullpowersrtkennels)",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        result = json.load(r)

    refresh_token = result.get("refresh_token", "")
    if not refresh_token:
        print(f"❌ Kein Refresh Token: {result}")
        return

    save_env_var("REDDIT_REFRESH_TOKEN", refresh_token)
    print(f"✅ Reddit verbunden! Refresh Token gespeichert.")
    print(f"   Account: {result.get('scope', 'OK')}")


# ──────────────────────────────────────── PINTEREST ────

def pinterest_connect():
    app_id     = os.getenv("PINTEREST_APP_ID", os.getenv("PINTEREST_CLIENT_ID", ""))
    app_secret = os.getenv("PINTEREST_APP_SECRET", os.getenv("PINTEREST_CLIENT_SECRET", ""))

    if not app_id:
        print("❌ PINTEREST_APP_ID fehlt in .env")
        print("   Gehe zu: https://developers.pinterest.com/apps/")
        print("   Erstelle eine App (kostenlos), kopiere App ID + App Secret")
        print("   Setze in .env: PINTEREST_APP_ID=... und PINTEREST_APP_SECRET=...")
        return

    auth_url = (
        "https://www.pinterest.com/oauth/?"
        + urlencode({
            "client_id":    app_id,
            "redirect_uri": CALLBACK_URL,
            "response_type": "code",
            "scope":        "boards:read,pins:read,pins:write",
        })
    )
    print(f"\n🔑 Pinterest OAuth starten...")
    webbrowser.open(auth_url)

    httpd = HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    t = threading.Thread(target=lambda: httpd.handle_request())
    t.daemon = True
    t.start()
    print(f"   Warte auf Pinterest-Autorisierung...")
    _server_done.wait(timeout=120)
    httpd.server_close()

    code = _received_code.get("code", "")
    if not code:
        print(f"❌ Fehler: {_received_code.get('error', 'kein Code')}")
        return

    import urllib.request
    creds = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()
    data  = urlencode({
        "grant_type":   "authorization_code",
        "code":         code,
        "redirect_uri": CALLBACK_URL,
    }).encode()
    req = urllib.request.Request(
        "https://api.pinterest.com/v5/oauth/token",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        result = json.load(r)

    token = result.get("access_token", "")
    if not token:
        print(f"❌ Fehler: {result}")
        return

    save_env_var("PINTEREST_ACCESS_TOKEN", token)
    refresh = result.get("refresh_token", "")
    if refresh:
        save_env_var("PINTEREST_REFRESH_TOKEN", refresh)
    print(f"✅ Pinterest verbunden!")


# ─────────────────────────────────────── YOUTUBE / GOOGLE ────

def youtube_connect():
    client_id     = os.getenv("GOOGLE_CLIENT_ID_AIITEC", os.getenv("GOOGLE_CLIENT_ID", ""))
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET_AIITEC", os.getenv("GOOGLE_CLIENT_SECRET", ""))

    if not client_id:
        print("❌ GOOGLE_CLIENT_ID_AIITEC nicht in .env")
        return

    scopes = " ".join([
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/userinfo.email",
        "openid",
    ])

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode({
            "client_id":     client_id,
            "redirect_uri":  CALLBACK_URL,
            "response_type": "code",
            "scope":         scopes,
            "access_type":   "offline",
            "prompt":        "consent",
        })
    )
    print(f"\n🔑 YouTube / Google OAuth starten...")
    print(f"   Melde dich mit dem AiiteC Google-Konto an")
    webbrowser.open(auth_url)

    httpd = HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    t = threading.Thread(target=lambda: httpd.handle_request())
    t.daemon = True
    t.start()
    print(f"   Warte auf Google-Autorisierung...")
    _server_done.wait(timeout=120)
    httpd.server_close()

    code = _received_code.get("code", "")
    if not code:
        print(f"❌ Fehler: {_received_code.get('error', 'kein Code')}")
        return

    import urllib.request
    data = urlencode({
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  CALLBACK_URL,
        "client_id":     client_id,
        "client_secret": client_secret,
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        result = json.load(r)

    refresh_token = result.get("refresh_token", "")
    if not refresh_token:
        print(f"❌ Kein Refresh Token — versuche erneut mit prompt=consent")
        print(f"   Antwort: {result}")
        return

    save_env_var("YOUTUBE_REFRESH_TOKEN", refresh_token)
    save_env_var("GOOGLE_REFRESH_TOKEN_AIITEC", refresh_token)
    print(f"✅ YouTube verbunden! Refresh Token gespeichert.")
    print(f"   Scopes: youtube.upload, youtube.force-ssl (Community Posts)")


# ─────────────────────────────────────── MAIN ────

if __name__ == "__main__":
    platform = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if platform == "reddit":
        print("ℹ️  Reddit benötigt 'web app' App-Typ mit redirect http://localhost:9999/callback")
        print("   Gehe zu reddit.com/prefs/apps → bearbeite App → setze redirect_uri auf:")
        print("   http://localhost:9999/callback")
        print("   Dann: python3 scripts/oauth_connect.py reddit")
        reddit_connect()
    elif platform == "pinterest":
        pinterest_connect()
    elif platform == "youtube":
        youtube_connect()
    else:
        print("Nutzung: python3 scripts/oauth_connect.py [reddit|pinterest|youtube]")
        print()
        print("  reddit    → Reddit Refresh Token holen (einmalig autorisieren)")
        print("  pinterest → Pinterest Access Token (erst PINTEREST_APP_ID in .env setzen)")
        print("  youtube   → YouTube/Google OAuth für Community Posts + Analytics")
        print()
        print("⚠️  Reddit: App muss 'web app' Typ haben mit redirect http://localhost:9999/callback")
        sys.exit(1)
