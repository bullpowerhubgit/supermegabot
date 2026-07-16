#!/usr/bin/env python3
"""
Facebook / Instagram Token Auto-Refresher
==========================================
Erneuert automatisch den 60-Tage Long-Lived User Access Token
via Facebook Graph API, bevor er abläuft.

Flow:
  1. Token aus Supabase lesen
  2. Prüfen ob < 15 Tage bis Ablauf
  3. Neuen Token von FB Graph API holen (grant_type=fb_exchange_token)
  4. Neuen Token in Supabase + os.environ + Railway speichern
  5. Telegram-Benachrichtigung senden

Scheduler: täglich prüfen, alle 45 Tage wirklich refreshen
"""

import asyncio
import logging
import os
import json
from datetime import datetime, timezone, timedelta

import aiohttp

log = logging.getLogger("FBTokenRefresher")

SUPABASE_URL    = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
TG_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID      = os.getenv("TELEGRAM_CHAT_ID", "")
FB_APP_ID       = os.getenv("FACEBOOK_APP_ID", "1066218829402806")
FB_APP_SECRET   = os.getenv("FACEBOOK_APP_SECRET", "")
RAILWAY_TOKEN   = os.getenv("RAILWAY_TOKEN", "") or os.getenv("RAILWAY_API_TOKEN", "")
RAILWAY_SVC_ID  = "fd111f3a-0bbc-407c-9e0d-1d77974b4de0"  # supermegabot service ID

SUPA_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Content-Profile": "public",
    "Accept-Profile": "public",
}

DAYS_BEFORE_EXPIRY_TO_REFRESH = 15  # Refresh wenn < 15 Tage bis Ablauf


# ── Supabase helpers ──────────────────────────────────────────────────────────

async def _supa_get_token() -> dict:
    """Liest aktuellen Facebook-Token aus Supabase oauth_tokens."""
    url = f"{SUPABASE_URL}/rest/v1/oauth_tokens?platform=eq.facebook&limit=1"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=SUPA_HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    rows = await r.json()
                    return rows[0] if rows else {}
    except Exception as e:
        log.warning(f"Supabase get token error: {e}")
    return {}


async def _supa_save_token(token: str, expires_at: datetime) -> bool:
    """Speichert neuen Token in Supabase oauth_tokens."""
    url = f"{SUPABASE_URL}/rest/v1/oauth_tokens?platform=eq.facebook"
    payload = {
        "access_token": token,
        "expires_at": expires_at.isoformat(),
        "last_refreshed_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    # Increment refresh_count via raw SQL not possible with REST — do via separate call
    try:
        async with aiohttp.ClientSession() as s:
            patch_headers = {**SUPA_HEADERS, "Prefer": "return=minimal"}
            async with s.patch(url, headers=patch_headers, json=payload,
                               timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status in (200, 204):
                    log.info("Token in Supabase gespeichert ✅")
                    return True
                log.warning(f"Supabase save token status: {r.status} — {await r.text()}")
    except Exception as e:
        log.warning(f"Supabase save token error: {e}")
    return False


# ── Facebook Graph API ────────────────────────────────────────────────────────

async def _fb_exchange_token(current_token: str) -> dict:
    """
    Tauscht kurz/lang-lebigen Token gegen neuen 60-Tage-Token aus.
    Endpoint: GET /oauth/access_token?grant_type=fb_exchange_token
    """
    url = "https://graph.facebook.com/v21.0/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": FB_APP_ID,
        "client_secret": FB_APP_SECRET,
        "fb_exchange_token": current_token,
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json()
                if "access_token" in data:
                    expires_in = data.get("expires_in", 5184000)  # ~60 Tage default
                    return {
                        "ok": True,
                        "token": data["access_token"],
                        "expires_in_seconds": expires_in,
                        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
                    }
                err = data.get("error", {})
                return {"ok": False, "error": err.get("message", str(data))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _fb_debug_token(token: str) -> dict:
    """Prüft Token-Gültigkeit und Ablaufdatum via debug_token."""
    url = "https://graph.facebook.com/v21.0/debug_token"
    params = {
        "input_token": token,
        "access_token": f"{FB_APP_ID}|{FB_APP_SECRET}",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = await r.json()
                data = d.get("data", {})
                expires_at = data.get("expires_at", 0)
                if expires_at:
                    exp_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
                    days_left = (exp_dt - datetime.now(timezone.utc)).days
                    return {
                        "valid": data.get("is_valid", False),
                        "expires_at": exp_dt.isoformat(),
                        "days_left": days_left,
                        "scopes": data.get("scopes", []),
                        "app_id": data.get("app_id", ""),
                    }
    except Exception as e:
        log.warning(f"FB debug_token error: {e}")
    return {"valid": False, "days_left": 0}


# ── Railway env var update ────────────────────────────────────────────────────

async def _update_railway_vars(token: str) -> bool:
    """Aktualisiert Railway Umgebungsvariablen via Railway API v2."""
    if not RAILWAY_TOKEN:
        log.warning("RAILWAY_TOKEN fehlt — Railway-Vars nicht aktualisiert")
        return False

    # Railway GraphQL API
    url = "https://backboard.railway.com/graphql/v2"
    headers = {
        "Authorization": f"Bearer {RAILWAY_TOKEN}",
        "Content-Type": "application/json",
    }
    var_names = [
        "FACEBOOK_ACCESS_TOKEN",
        "FACEBOOK_PAGE_TOKEN",
        "FACEBOOK_PAGE_TOKEN_AIITEC",
        "META_ACCESS_TOKEN",
        "INSTAGRAM_ACCESS_TOKEN",
        "INSTAGRAM_TOKEN_AIITEC",
    ]
    # Build upsert variables
    variables_input = {k: token for k in var_names}
    query = """
    mutation UpsertVariables($serviceId: String!, $environmentId: String!, $variables: Json!) {
      variableCollectionUpsert(
        input: {
          serviceId: $serviceId,
          environmentId: "0cf838ab-0358-4536-a6da-d4885aa93695",
          variables: $variables
        }
      )
    }
    """
    payload = {
        "query": query,
        "variables": {
            "serviceId": RAILWAY_SVC_ID,
            "environmentId": "0cf838ab-0358-4536-a6da-d4885aa93695",
            "variables": variables_input,
        },
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, headers=headers, json=payload,
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                d = await r.json()
                if "errors" not in d:
                    log.info("Railway Variablen aktualisiert ✅")
                    return True
                log.warning(f"Railway API error: {d['errors']}")
    except Exception as e:
        log.warning(f"Railway update error: {e}")
    return False


# ── Telegram notification ─────────────────────────────────────────────────────

async def _tg(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(url, json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
                         timeout=aiohttp.ClientTimeout(total=10))
    except Exception as e:
        log.warning("Ignored error: %s", e)


# ── Main entry point ──────────────────────────────────────────────────────────

async def check_and_refresh() -> dict:
    """
    Prüft ob Facebook-Token erneuert werden muss und führt Refresh durch.
    Gibt Status-Dict zurück.
    """
    result = {"action": "none", "ok": True}

    # 1. Aktuellen Token aus Supabase lesen
    row = await _supa_get_token()
    current_token = row.get("access_token") or os.getenv("FACEBOOK_ACCESS_TOKEN", "")
    expires_at_str = row.get("expires_at", "")

    if not current_token:
        msg = "❌ VORSPRUNG: Kein Facebook-Token in Supabase oder .env gefunden!"
        log.error(msg)
        await _tg(msg)
        return {"action": "error", "ok": False, "error": "No token found"}

    # 2. Ablaufdatum prüfen
    days_left = 999
    if expires_at_str:
        try:
            exp = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            days_left = (exp - datetime.now(timezone.utc)).days
            log.info(f"Facebook-Token läuft ab in {days_left} Tagen ({exp.date()})")
        except Exception as e:
            log.warning("Ignored error: %s", e)
    else:
        # Kein Ablaufdatum bekannt → via debug_token prüfen
        debug = await _fb_debug_token(current_token)
        days_left = debug.get("days_left", 999)
        log.info(f"Token debug: {days_left} Tage verbleibend, gültig: {debug.get('valid')}")

    result["days_left"] = days_left
    result["token_preview"] = current_token[:20] + "..."

    # 3. Refresh wenn nötig
    if days_left > DAYS_BEFORE_EXPIRY_TO_REFRESH:
        log.info(f"Token OK — {days_left} Tage verbleibend, kein Refresh nötig")
        result["action"] = "skipped"
        result["reason"] = f"{days_left} Tage bis Ablauf — kein Refresh nötig"
        return result

    log.info(f"Token läuft in {days_left} Tagen ab — starte Refresh...")
    result["action"] = "refresh_started"

    # 4. Neuen Token von Facebook holen
    if not FB_APP_SECRET:
        return {"action": "error", "ok": False, "error": "FACEBOOK_APP_SECRET fehlt"}

    fb_result = await _fb_exchange_token(current_token)
    if not fb_result.get("ok"):
        err = fb_result.get("error", "?")
        msg = f"❌ Facebook Token Refresh FEHLGESCHLAGEN: {err}"
        log.error(msg)
        await _tg(msg)
        return {"action": "refresh_failed", "ok": False, "error": err}

    new_token = fb_result["token"]
    new_expires = fb_result["expires_at"]
    new_days = (new_expires - datetime.now(timezone.utc)).days

    log.info(f"Neuer Token erhalten — läuft ab in {new_days} Tagen ({new_expires.date()})")

    # 5. In laufendem Prozess sofort aktiv setzen
    for var in ["FACEBOOK_ACCESS_TOKEN", "FACEBOOK_PAGE_TOKEN", "FACEBOOK_PAGE_TOKEN_AIITEC",
                "META_ACCESS_TOKEN", "INSTAGRAM_ACCESS_TOKEN"]:
        os.environ[var] = new_token

    # 6. Supabase updaten
    supa_ok = await _supa_save_token(new_token, new_expires)

    # 7. Railway Variablen updaten (optional — braucht RAILWAY_TOKEN)
    railway_ok = await _update_railway_vars(new_token)

    # 8. Telegram-Benachrichtigung
    status_parts = []
    status_parts.append("✅ Supabase" if supa_ok else "❌ Supabase fehl.")
    status_parts.append("✅ Railway" if railway_ok else "⚠️ Railway manuell nötig")

    msg = (
        f"🔄 *Facebook Token automatisch erneuert!*\n"
        f"Neues Ablaufdatum: *{new_expires.strftime('%d.%m.%Y')}*\n"
        f"Gültig für: *{new_days} Tage*\n"
        f"Gespeichert: {', '.join(status_parts)}"
    )
    await _tg(msg)
    log.info(msg.replace("*", ""))

    return {
        "action": "refreshed",
        "ok": True,
        "old_days_left": days_left,
        "new_days": new_days,
        "new_expires": new_expires.isoformat(),
        "supabase_saved": supa_ok,
        "railway_updated": railway_ok,
    }


async def get_status() -> dict:
    """Status-Übersicht für Dashboard-Route."""
    row = await _supa_get_token()
    token = row.get("access_token", "")
    expires_at_str = row.get("expires_at", "")
    days_left = None

    if expires_at_str:
        try:
            exp = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            days_left = (exp - datetime.now(timezone.utc)).days
        except Exception as e:
            log.warning("Ignored error: %s", e)

    if not days_left and token:
        debug = await _fb_debug_token(token)
        days_left = debug.get("days_left")

    status = "ok" if (days_left or 0) > DAYS_BEFORE_EXPIRY_TO_REFRESH else "needs_refresh"
    return {
        "ok": True,
        "platform": "facebook_instagram",
        "token_set": bool(token),
        "token_preview": (token[:15] + "...") if token else None,
        "expires_at": expires_at_str,
        "days_left": days_left,
        "status": status,
        "auto_refresh_threshold_days": DAYS_BEFORE_EXPIRY_TO_REFRESH,
        "last_refreshed": row.get("last_refreshed_at"),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(check_and_refresh())
