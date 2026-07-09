"""
Reddit OAuth2 Helper — einmalig ausführen um REDDIT_REFRESH_TOKEN zu holen.

Schritt 1: reddit.com/prefs/apps → App "SuperMegaBot" → redirect URI auf
           http://localhost:9191/callback setzen (oder neue "web app" erstellen)
Schritt 2: python3 modules/reddit_oauth_helper.py
Schritt 3: Refresh Token wird automatisch in .env gespeichert
"""
import asyncio
import base64
import json
import os
import pathlib
import secrets
import sys
import urllib.parse
import webbrowser

from aiohttp import web

REDIRECT_PORT = 9191
REDIRECT_URI  = f"http://localhost:{REDIRECT_PORT}/callback"

ENV_FILE = pathlib.Path(__file__).parent.parent / ".env"

_state    = ""
_token_received: asyncio.Event = None
_result: dict = {}


def _load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _save_token_to_env(refresh_token: str):
    """Inject / replace REDDIT_REFRESH_TOKEN in .env."""
    if not ENV_FILE.exists():
        ENV_FILE.write_text(f"REDDIT_REFRESH_TOKEN={refresh_token}\n")
        return

    lines = ENV_FILE.read_text().splitlines()
    replaced = False
    new_lines = []
    for line in lines:
        if line.startswith("REDDIT_REFRESH_TOKEN") or line.startswith("# REDDIT_REFRESH_TOKEN"):
            new_lines.append(f"REDDIT_REFRESH_TOKEN={refresh_token}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"REDDIT_REFRESH_TOKEN={refresh_token}")
    ENV_FILE.write_text("\n".join(new_lines) + "\n")


async def _exchange_code(code: str, client_id: str, client_secret: str) -> dict:
    import aiohttp
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://www.reddit.com/api/v1/access_token",
            headers={
                "Authorization": f"Basic {creds}",
                "User-Agent": "SuperMegaBot/2.0",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            return await r.json(content_type=None)


async def handle_callback(req: web.Request) -> web.Response:
    global _result
    error = req.rel_url.query.get("error", "")
    code  = req.rel_url.query.get("code", "")
    state = req.rel_url.query.get("state", "")

    if error:
        _result = {"ok": False, "error": error}
        _token_received.set()
        return web.Response(
            content_type="text/html",
            text=f"<h2>❌ Fehler: {error}</h2><p>Fenster schließen und nochmal versuchen.</p>",
        )

    if state != _state:
        _result = {"ok": False, "error": "state mismatch — CSRF check failed"}
        _token_received.set()
        return web.Response(
            content_type="text/html",
            text="<h2>❌ State mismatch</h2>",
        )

    env = _load_env()
    client_id     = env.get("REDDIT_CLIENT_ID", "")
    client_secret = env.get("REDDIT_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        _result = {"ok": False, "error": "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET fehlen in .env"}
        _token_received.set()
        return web.Response(content_type="text/html", text="<h2>❌ Credentials fehlen in .env</h2>")

    d = await _exchange_code(code, client_id, client_secret)
    refresh_token = d.get("refresh_token", "")
    access_token  = d.get("access_token", "")

    if not refresh_token:
        _result = {"ok": False, "error": "kein refresh_token", "detail": d}
        _token_received.set()
        return web.Response(
            content_type="text/html",
            text=f"<h2>❌ Kein refresh_token</h2><pre>{json.dumps(d, indent=2)}</pre>",
        )

    _save_token_to_env(refresh_token)
    _result = {"ok": True, "refresh_token": refresh_token, "access_token": access_token}
    _token_received.set()

    return web.Response(
        content_type="text/html",
        text=(
            "<h2 style='color:green'>✅ Reddit autorisiert!</h2>"
            "<p>Refresh Token gespeichert in .env</p>"
            f"<p><code>REDDIT_REFRESH_TOKEN={refresh_token[:30]}...</code></p>"
            "<p>Dieses Fenster kann geschlossen werden.</p>"
        ),
    )


async def main():
    global _state, _token_received

    env = _load_env()
    client_id = env.get("REDDIT_CLIENT_ID", "")
    if not client_id:
        print("❌ REDDIT_CLIENT_ID fehlt in .env")
        sys.exit(1)

    existing_rt = env.get("REDDIT_REFRESH_TOKEN", "")
    if existing_rt and not existing_rt.startswith("#"):
        print(f"ℹ️  REDDIT_REFRESH_TOKEN bereits gesetzt: {existing_rt[:20]}...")
        ans = input("Nochmal neu holen? [j/N]: ").strip().lower()
        if ans != "j":
            print("Abbruch.")
            return

    _state = secrets.token_urlsafe(16)
    _token_received = asyncio.Event()

    app = web.Application()
    app.router.add_get("/callback", handle_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", REDIRECT_PORT)
    await site.start()

    params = urllib.parse.urlencode({
        "client_id":     client_id,
        "response_type": "code",
        "state":         _state,
        "redirect_uri":  REDIRECT_URI,
        "duration":      "permanent",
        "scope":         "submit read identity flair",
    })
    auth_url = f"https://www.reddit.com/api/v1/authorize?{params}"

    print()
    print("=" * 60)
    print("REDDIT OAUTH2 SETUP")
    print("=" * 60)
    print()
    print("VORAUSSETZUNG:")
    print(f"  reddit.com/prefs/apps → App 'SuperMegaBot' → Edit")
    print(f"  redirect URI: {REDIRECT_URI}")
    print()
    print("Browser wird geöffnet...")
    print(f"  URL: {auth_url[:80]}...")
    print()

    webbrowser.open(auth_url)

    print("Warte auf Reddit-Autorisierung...")
    await asyncio.wait_for(_token_received.wait(), timeout=300)

    await runner.cleanup()

    if _result.get("ok"):
        rt = _result["refresh_token"]
        print()
        print("✅ ERFOLG!")
        print(f"   Refresh Token: {rt[:30]}...")
        print(f"   Gespeichert in: {ENV_FILE}")
        print()
        print("Railway: Füge den Token manuell in Railway → Variables hinzu:")
        print(f"   REDDIT_REFRESH_TOKEN = {rt}")
        print()
        print("Oder per CLI:")
        print(f"   railway variables set REDDIT_REFRESH_TOKEN={rt} --service supermegabot")
        print()
        print("Danach läuft Reddit-Posting vollautomatisch alle 6h!")
    else:
        print()
        print(f"❌ FEHLER: {_result.get('error')}")
        if "detail" in _result:
            print(f"   Detail: {_result['detail']}")
        print()
        print("Häufige Ursachen:")
        print("  1. redirect URI in Reddit App stimmt nicht:")
        print(f"     Muss exakt sein: {REDIRECT_URI}")
        print("  2. App-Typ ist 'script' statt 'web app'")
        print("     → Lösung: Neues App mit Typ 'web app' erstellen")


if __name__ == "__main__":
    asyncio.run(main())
