#!/usr/bin/env python3
"""
Google OAuth2 Flow
Handles authorization, token exchange, refresh, and .env auto-update.
Scopes: Drive, Sheets, YouTube, GMC
"""

import asyncio
import json
import logging
import os
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import aiohttp

log = logging.getLogger("GoogleOAuth")

BASE_DIR = Path(__file__).parent.parent
_TOKEN_FILE = BASE_DIR / "data" / "google_tokens.json"

_AUTH_URL    = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL   = "https://oauth2.googleapis.com/token"
_REVOKE_URL  = "https://oauth2.googleapis.com/revoke"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # write: community posts, playlists
    "https://www.googleapis.com/auth/youtube.upload",     # upload videos
    "https://www.googleapis.com/auth/content",   # GMC Merchant Center
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def _client_id() -> str:
    return os.getenv("GOOGLE_CLIENT_ID", "")


def _client_secret() -> str:
    return os.getenv("GOOGLE_CLIENT_SECRET", "")


def _public_base_url() -> str:
    explicit = (
        os.getenv("APP_BASE_URL", "").strip()
        or os.getenv("DASHBOARD_URL", "").strip()
        or os.getenv("PUBLIC_BASE_URL", "").strip()
    )
    if explicit:
        return explicit.rstrip("/")
    public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if public_domain:
        return f"https://{public_domain}".rstrip("/")
    return ""


def _redirect_uri() -> str:
    explicit = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    public_base = _public_base_url()
    if public_base:
        return f"{public_base}/api/google/callback"
    port = os.getenv("DASHBOARD_PORT", "8888")
    return f"http://localhost:{port}/api/google/callback"


# ── Token persistence ─────────────────────────────────────────────────────────

def _load_tokens() -> Dict:
    if _TOKEN_FILE.exists():
        try:
            return json.loads(_TOKEN_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_tokens(tokens: Dict):
    _TOKEN_FILE.parent.mkdir(exist_ok=True)
    _TOKEN_FILE.write_text(json.dumps(tokens, indent=2, ensure_ascii=False))


def _update_env_token(access_token: str):
    """Write GOOGLE_ACCESS_TOKEN into .env (gitignored)."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    lines = env_path.read_text().splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith("GOOGLE_ACCESS_TOKEN="):
            lines[i] = f"GOOGLE_ACCESS_TOKEN={access_token}"
            found = True
            break
    if not found:
        # Insert after GOOGLE_CLIENT_SECRET line
        for i, line in enumerate(lines):
            if line.startswith("GOOGLE_CLIENT_SECRET="):
                lines.insert(i + 1, f"GOOGLE_ACCESS_TOKEN={access_token}")
                found = True
                break
        if not found:
            lines.append(f"GOOGLE_ACCESS_TOKEN={access_token}")
    env_path.write_text("\n".join(lines) + "\n")
    os.environ["GOOGLE_ACCESS_TOKEN"] = access_token


# ── Authorization URL ─────────────────────────────────────────────────────────

def get_auth_url(state: str = "smb", scopes: list = None) -> str:
    """Generate the Google OAuth2 authorization URL."""
    cid = _client_id()
    if not cid:
        raise ValueError("GOOGLE_CLIENT_ID nicht gesetzt")
    params = {
        "client_id":     cid,
        "redirect_uri":  _redirect_uri(),
        "response_type": "code",
        "scope":         " ".join(scopes or SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    }
    return f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"


def get_youtube_auth_url() -> str:
    """Generate OAuth2 URL scoped specifically for YouTube write access."""
    return get_auth_url(state="youtube", scopes=YOUTUBE_SCOPES)


# ── Token Exchange ────────────────────────────────────────────────────────────

async def exchange_code(code: str) -> Dict:
    """Exchange authorization code for access + refresh tokens."""
    data = {
        "code":          code,
        "client_id":     _client_id(),
        "client_secret": _client_secret(),
        "redirect_uri":  _redirect_uri(),
        "grant_type":    "authorization_code",
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(_TOKEN_URL, data=data) as r:
                result = await r.json()
                if r.status != 200:
                    return {"ok": False, "error": result.get("error_description", str(result))}

                tokens = {
                    "access_token":  result["access_token"],
                    "refresh_token": result.get("refresh_token", ""),
                    "expires_in":    result.get("expires_in", 3600),
                    "expires_at":    int(time.time()) + result.get("expires_in", 3600),
                    "token_type":    result.get("token_type", "Bearer"),
                    "scope":         result.get("scope", ""),
                    "obtained_at":   datetime.now().isoformat(),
                }
                _save_tokens(tokens)
                _update_env_token(tokens["access_token"])
                # Persist refresh_token to Railway so it survives restarts
                if tokens.get("refresh_token"):
                    try:
                        import subprocess
                        subprocess.run(
                            ["railway", "variables", "set",
                             f"GOOGLE_REFRESH_TOKEN={tokens['refresh_token']}",
                             f"GOOGLE_ACCESS_TOKEN={tokens['access_token']}",
                             "--service", "dudirudibot-mega"],
                            capture_output=True, timeout=30
                        )
                    except Exception:
                        pass
                log.info("Google OAuth2 Token erhalten und gespeichert")
                return {"ok": True, **tokens}
    except Exception as e:
        log.error(f"exchange_code: {e}")
        return {"ok": False, "error": str(e)}


# ── Token Refresh ─────────────────────────────────────────────────────────────

async def refresh_token() -> Dict:
    """Use the stored refresh token to get a new access token."""
    tokens = _load_tokens()
    refresh = tokens.get("refresh_token", "") or os.getenv("GOOGLE_REFRESH_TOKEN", "")
    if not refresh:
        return {"ok": False, "error": "Kein refresh_token gespeichert — bitte neu einloggen"}

    data = {
        "refresh_token": refresh,
        "client_id":     _client_id(),
        "client_secret": _client_secret(),
        "grant_type":    "refresh_token",
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(_TOKEN_URL, data=data) as r:
                result = await r.json()
                if r.status != 200:
                    return {"ok": False, "error": result.get("error_description", str(result))}

                tokens["access_token"] = result["access_token"]
                tokens["expires_in"]   = result.get("expires_in", 3600)
                tokens["expires_at"]   = int(time.time()) + result.get("expires_in", 3600)
                tokens["refreshed_at"] = datetime.now().isoformat()
                _save_tokens(tokens)
                _update_env_token(tokens["access_token"])
                log.info("Google OAuth2 Token erneuert")
                return {"ok": True, "access_token": tokens["access_token"], "expires_in": tokens["expires_in"]}
    except Exception as e:
        log.error(f"refresh_token: {e}")
        return {"ok": False, "error": str(e)}


# ── Auto-refresh if needed ────────────────────────────────────────────────────

async def ensure_valid_token() -> Optional[str]:
    """Return a valid access token, refreshing automatically if expired."""
    tokens = _load_tokens()
    expires_at = tokens.get("expires_at", 0)

    # If expires in < 5 minutes, refresh
    if expires_at and time.time() > expires_at - 300:
        result = await refresh_token()
        if result.get("ok"):
            return result["access_token"]
        return None

    # Try env var first (may have been set manually)
    token = tokens.get("access_token") or os.getenv("GOOGLE_ACCESS_TOKEN", "")
    return token or None


# ── User Info ─────────────────────────────────────────────────────────────────

async def get_user_info() -> Dict:
    token = await ensure_valid_token()
    if not token:
        return {"ok": False, "error": "Nicht eingeloggt"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(_USERINFO_URL, headers={"Authorization": f"Bearer {token}"}) as r:
                if r.status == 200:
                    d = await r.json()
                    return {"ok": True, "email": d.get("email", ""), "name": d.get("name", ""), "picture": d.get("picture", "")}
                return {"ok": False, "error": f"HTTP {r.status}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Status ────────────────────────────────────────────────────────────────────

async def get_status() -> Dict:
    tokens = _load_tokens()
    if not tokens:
        cid = _client_id()
        return {
            "ok":           False,
            "logged_in":    False,
            "error":        "Nicht eingeloggt",
            "auth_url":     get_auth_url() if cid else None,
            "client_id_ok": bool(cid),
        }

    expires_at = tokens.get("expires_at", 0)
    is_expired = time.time() > expires_at - 60 if expires_at else True
    has_refresh = bool(tokens.get("refresh_token"))

    user = await get_user_info()
    return {
        "ok":           True,
        "logged_in":    True,
        "email":        user.get("email", ""),
        "name":         user.get("name", ""),
        "expires_at":   datetime.fromtimestamp(expires_at).isoformat() if expires_at else None,
        "is_expired":   is_expired,
        "has_refresh":  has_refresh,
        "scope":        tokens.get("scope", ""),
        "obtained_at":  tokens.get("obtained_at", ""),
        "refreshed_at": tokens.get("refreshed_at", ""),
    }


# ── YouTube-specific status ───────────────────────────────────────────────────

async def get_youtube_status() -> Dict:
    """Return YouTube connection status, including channel info if authenticated."""
    import os as _os
    tokens = _load_tokens()
    yt_key  = _os.getenv("YOUTUBE_API_KEY", "")
    chan_id = _os.getenv("YOUTUBE_CHANNEL_ID", "")
    has_oauth = bool(tokens and tokens.get("access_token"))
    has_upload_scope = "youtube.upload" in tokens.get("scope", "") if tokens else False

    base = {
        "ok":               has_oauth,
        "has_oauth":        has_oauth,
        "has_api_key":      bool(yt_key),
        "has_channel_id":   bool(chan_id),
        "has_upload_scope": has_upload_scope,
        "auth_url":         get_youtube_auth_url() if _client_id() and not has_oauth else None,
    }

    if not has_oauth:
        base["error"] = "Nicht eingeloggt — OAuth2 Flow starten"
        return base

    token = await ensure_valid_token()
    if not token:
        base["ok"] = False
        base["error"] = "Token abgelaufen und Refresh fehlgeschlagen"
        return base

    if chan_id:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={"part": "snippet,statistics", "id": chan_id},
                    headers={"Authorization": f"Bearer {token}"},
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        items = data.get("items", [])
                        if items:
                            snippet = items[0].get("snippet", {})
                            stats   = items[0].get("statistics", {})
                            base["channel_title"]      = snippet.get("title", "")
                            base["subscriber_count"]   = stats.get("subscriberCount", "?")
                            base["video_count"]        = stats.get("videoCount", "?")
                    else:
                        base["channel_error"] = f"HTTP {r.status}"
        except Exception as exc:
            base["channel_error"] = str(exc)

    return base


# ── Revoke ────────────────────────────────────────────────────────────────────

async def revoke() -> bool:
    tokens = _load_tokens()
    token = tokens.get("access_token", "")
    if not token:
        return False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(_REVOKE_URL, params={"token": token}) as r:
                _TOKEN_FILE.unlink(missing_ok=True)
                return r.status == 200
    except Exception:
        return False
