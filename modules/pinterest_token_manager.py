#!/usr/bin/env python3
"""
Pinterest Token Manager
=======================
Verwaltet Pinterest Access Tokens:
- Token-Validierung (GET /v5/user_account)
- Automatisches Refresh via Refresh-Token
- Railway-Sync des neuen Tokens
- Board-Initialisierung beim ersten Start
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("PinterestTokenManager")

PINTEREST_BASE    = "https://api.pinterest.com/v5"
PINTEREST_TOKEN   = lambda: os.getenv("PINTEREST_ACCESS_TOKEN", "")
PINTEREST_REFRESH = lambda: os.getenv("PINTEREST_REFRESH_TOKEN", "")
APP_ID            = os.getenv("PINTEREST_APP_ID", "")
APP_SECRET        = lambda: os.getenv("PINTEREST_APP_SECRET", "")

BOARDS_TO_CREATE = [
    "Smart Home Gadgets",
    "Solar & Energie",
    "Smart Home Deutschland",
    "E-Bike & Elektromobilität",
    "Tech Gadgets 2026",
]


def _headers(token: str | None = None) -> dict:
    t = token or PINTEREST_TOKEN()
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


async def validate_token(token: str | None = None) -> dict:
    """Prüft ob Token gültig ist. Gibt {ok, username, plan} zurück."""
    t = token or PINTEREST_TOKEN()
    if not t:
        return {"ok": False, "error": "no_token"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(f"{PINTEREST_BASE}/user_account", headers=_headers(t)) as r:
                data = await r.json(content_type=None)
                if r.status == 200:
                    return {
                        "ok": True,
                        "username": data.get("username", ""),
                        "account_type": data.get("account_type", ""),
                        "website_url": data.get("website_url", ""),
                        "profile_image": data.get("profile_image", ""),
                    }
                return {"ok": False, "error": data.get("message", "auth_failed"), "status": r.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def refresh_token() -> dict:
    """Tauscht Refresh-Token gegen neuen Access-Token."""
    refresh = PINTEREST_REFRESH()
    app_id = APP_ID
    app_secret = APP_SECRET()

    if not refresh:
        return {"ok": False, "error": "no PINTEREST_REFRESH_TOKEN in env"}
    if not app_id or not app_secret:
        return {"ok": False, "error": "no PINTEREST_APP_ID or PINTEREST_APP_SECRET"}

    creds = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                "https://api.pinterest.com/v5/oauth/token",
                headers={
                    "Authorization": f"Basic {creds}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=f"grant_type=refresh_token&refresh_token={refresh}&scope=boards:read,pins:read,pins:write",
            ) as r:
                data = await r.json(content_type=None)

        if "access_token" in data:
            new_token = data["access_token"]
            new_refresh = data.get("refresh_token", refresh)
            log.info("Pinterest token refreshed successfully")

            try:
                import subprocess
                subprocess.run(
                    ["railway", "variables", "set", f"PINTEREST_ACCESS_TOKEN={new_token}"],
                    capture_output=True, timeout=30
                )
                if new_refresh != refresh:
                    subprocess.run(
                        ["railway", "variables", "set", f"PINTEREST_REFRESH_TOKEN={new_refresh}"],
                        capture_output=True, timeout=30
                    )
                log.info("Pinterest token saved to Railway")
            except Exception as re:
                log.warning("Railway sync skipped: %s", re)

            return {"ok": True, "new_token": new_token[:12] + "...", "refreshed_at": datetime.now(timezone.utc).isoformat()}

        return {"ok": False, "error": data.get("message", str(data)[:200])}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def ensure_boards_exist() -> dict:
    """Erstellt alle 5 Standard-Boards falls sie nicht existieren."""
    token = PINTEREST_TOKEN()
    if not token:
        return {"ok": False, "error": "no token"}

    from modules.pinterest_traffic import get_or_create_board

    created = []
    existing = []
    errors = []

    for board_name in BOARDS_TO_CREATE:
        board_id = await get_or_create_board(board_name)
        if board_id:
            created.append({"name": board_name, "id": board_id})
        else:
            errors.append(board_name)
        await asyncio.sleep(0.5)

    log.info("Pinterest boards: %d ready, %d errors", len(created), len(errors))
    return {
        "ok": len(errors) == 0,
        "boards_ready": len(created),
        "board_ids": created,
        "errors": errors,
    }


async def get_board_count() -> int:
    """Gibt Anzahl der Pinterest Boards zurück."""
    token = PINTEREST_TOKEN()
    if not token:
        return 0
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"{PINTEREST_BASE}/boards",
                headers=_headers(),
                params={"page_size": 100},
            ) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    return len(data.get("items", []))
    except Exception:
        pass
    return 0


async def get_pin_count() -> int:
    """Gibt Gesamtzahl der erstellten Pins zurück."""
    from pathlib import Path
    import json
    dedup_file = Path("data/pinterest_posted.json")
    try:
        return len(json.loads(dedup_file.read_text()))
    except Exception:
        return 0


async def full_status() -> dict:
    """Kompletter Pinterest Status für Dashboard."""
    token_check = await validate_token()
    board_count = await get_board_count() if token_check["ok"] else 0
    pin_count = await get_pin_count()

    return {
        "ok": token_check["ok"],
        "token_valid": token_check["ok"],
        "username": token_check.get("username", ""),
        "account_type": token_check.get("account_type", ""),
        "board_count": board_count,
        "pins_posted": pin_count,
        "has_refresh_token": bool(PINTEREST_REFRESH()),
        "has_app_secret": bool(APP_SECRET()),
        "error": token_check.get("error", "") if not token_check["ok"] else "",
        "setup_needed": not token_check["ok"],
        "oauth_url": (
            f"https://www.pinterest.com/oauth/"
            f"?client_id={APP_ID}"
            f"&redirect_uri=https://supermegabot-production.up.railway.app/api/pinterest/callback"
            f"&response_type=code"
            f"&scope=boards:read,pins:read,pins:write,user_accounts:read"
        ) if APP_ID else "",
    }


async def run_token_health_check() -> str:
    """Scheduler-Task: Token validieren + ggf. refreshen."""
    check = await validate_token()
    if check["ok"]:
        log.info("Pinterest token valid: @%s", check.get("username", "?"))
        return f"Pinterest Token OK: @{check.get('username', '?')} | Boards: {await get_board_count()}"

    log.warning("Pinterest token invalid (%s), attempting refresh...", check.get("error"))
    refresh_result = await refresh_token()
    if refresh_result["ok"]:
        return f"Pinterest Token erneuert — {refresh_result['new_token']}"

    return f"Pinterest Token ABGELAUFEN — manuelles Renewal nötig: /api/pinterest/auth"
