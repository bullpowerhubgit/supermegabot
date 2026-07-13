#!/usr/bin/env python3
"""
Instagram / Facebook Token Health Monitor & Auto-Refresher
==========================================================
- Prüft täglich alle Meta-Tokens (Page, User, IG)
- Sendet Telegram-Alert bei < 14 Tage bis Ablauf
- Versucht META_USER_TOKEN via fb_exchange_token zu erneuern
- Versucht IG-User-Token via graph.instagram.com zu erneuern
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [IG-REFRESH] %(levelname)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("IGTokenRefresh")

_BASE = Path(__file__).parent.parent

def _load_env():
    ef = _BASE / ".env"
    if ef.exists():
        for line in ef.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

TG_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT        = os.getenv("TELEGRAM_CHAT_ID", "")
FB_APP_ID      = os.getenv("FACEBOOK_APP_ID", "1535442684079797")
FB_APP_SECRET  = os.getenv("FACEBOOK_APP_SECRET", "b613acc6d413eee849cf7d4814b68376")


async def _tg(msg: str):
    if TG_TOKEN and TG_CHAT:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"},
            )


async def _debug_token(token: str, session: aiohttp.ClientSession) -> dict:
    app_access = f"{FB_APP_ID}|{FB_APP_SECRET}"
    url = f"https://graph.facebook.com/debug_token?input_token={token}&access_token={app_access}"
    async with session.get(url) as r:
        data = (await r.json()).get("data", {})
    return data


async def _check_page_token(token: str, name: str, session: aiohttp.ClientSession) -> dict:
    """Prüft Page Token via /me Endpoint."""
    try:
        async with session.get(
            f"https://graph.facebook.com/v19.0/me",
            params={"access_token": token, "fields": "id,name"}
        ) as r:
            data = await r.json()
        if "error" in data:
            return {"name": name, "valid": False, "error": data["error"].get("message", "unknown")}
        return {"name": name, "valid": True, "id": data.get("id"), "page_name": data.get("name"), "expires": "never"}
    except Exception as e:
        return {"name": name, "valid": False, "error": str(e)}


async def _try_refresh_user_token(old_token: str, session: aiohttp.ClientSession) -> str | None:
    """Versucht, einen User-Token via fb_exchange_token zu verlängern."""
    try:
        async with session.get(
            "https://graph.facebook.com/v19.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": FB_APP_ID,
                "client_secret": FB_APP_SECRET,
                "fb_exchange_token": old_token,
            }
        ) as r:
            data = await r.json()
        if "access_token" in data:
            return data["access_token"]
        log.warning(f"User-Token-Refresh fehlgeschlagen: {data.get('error', {}).get('message', data)}")
        return None
    except Exception as e:
        log.error(f"User-Token-Refresh Exception: {e}")
        return None


async def _try_refresh_ig_user_token(ig_token: str, session: aiohttp.ClientSession) -> str | None:
    """Verlängert einen Instagram Basic Display API Long-Lived-Token."""
    try:
        async with session.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": ig_token}
        ) as r:
            data = await r.json()
        if "access_token" in data:
            expires_in = data.get("expires_in", 0)
            log.info(f"IG-Token erneuert. Gültig für {expires_in // 86400} Tage.")
            return data["access_token"]
        log.warning(f"IG-Token-Refresh fehlgeschlagen: {data}")
        return None
    except Exception as e:
        log.error(f"IG-Token-Refresh Exception: {e}")
        return None


async def check_and_refresh_all() -> dict:
    results = {"ok": [], "warnings": [], "errors": [], "refreshed": []}
    now_ts = int(time.time())
    WARNING_THRESHOLD = 14 * 86400  # 14 Tage

    async with aiohttp.ClientSession() as session:

        # ── 1. Page Token (nie abläuft) ──────────────────────────────────────
        page_token = os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC") or os.getenv("FACEBOOK_PAGE_TOKEN") or ""
        if page_token:
            result = await _check_page_token(page_token, "FACEBOOK_PAGE_TOKEN_AIITEC", session)
            if result["valid"]:
                results["ok"].append(f"✅ {result['name']}: gültig (Page '{result.get('page_name')}', nie ablaufend)")
                log.info(result["ok"][-1])
            else:
                results["errors"].append(f"❌ {result['name']}: UNGÜLTIG — {result.get('error')}")
                log.error(results["errors"][-1])
        else:
            results["warnings"].append("⚠️ FACEBOOK_PAGE_TOKEN_AIITEC: nicht gesetzt!")

        # ── 2. META_USER_TOKEN via debug_token ───────────────────────────────
        user_token = os.getenv("META_USER_TOKEN", "")
        if user_token:
            dbg = await _debug_token(user_token, session)
            if dbg.get("is_valid"):
                exp = dbg.get("expires_at", 0)
                if exp and exp > 0:
                    days_left = (exp - now_ts) // 86400
                    if days_left < 14:
                        # Versuche Verlängerung
                        new_token = await _try_refresh_user_token(user_token, session)
                        if new_token:
                            _update_env_var("META_USER_TOKEN", new_token)
                            results["refreshed"].append(f"🔄 META_USER_TOKEN erneuert (war noch {days_left} Tage gültig)")
                        else:
                            results["warnings"].append(f"⚠️ META_USER_TOKEN läuft in {days_left} Tagen ab — manuelle Erneuerung nötig!")
                    else:
                        results["ok"].append(f"✅ META_USER_TOKEN: gültig noch {days_left} Tage")
                else:
                    results["ok"].append("✅ META_USER_TOKEN: läuft nie ab")
            else:
                # Token ungültig — versuche Erneuerung
                new_token = await _try_refresh_user_token(user_token, session)
                if new_token:
                    _update_env_var("META_USER_TOKEN", new_token)
                    results["refreshed"].append("🔄 META_USER_TOKEN war abgelaufen — erneuert!")
                else:
                    results["errors"].append("❌ META_USER_TOKEN: ungültig, Erneuerung fehlgeschlagen — Login erforderlich!")
        else:
            results["warnings"].append("⚠️ META_USER_TOKEN: nicht gesetzt!")

        # ── 3. Instagram Basic Display Token (falls vorhanden) ────────────────
        ig_token = os.getenv("FACEBOOK_IG_ACCESS_TOKEN", "")
        if ig_token:
            dbg = await _debug_token(ig_token, session)
            if dbg.get("is_valid"):
                exp = dbg.get("expires_at", 0)
                if exp and exp > 0:
                    days_left = (exp - now_ts) // 86400
                    if days_left < 14:
                        new_token = await _try_refresh_ig_user_token(ig_token, session)
                        if new_token:
                            _update_env_var("FACEBOOK_IG_ACCESS_TOKEN", new_token)
                            results["refreshed"].append(f"🔄 FACEBOOK_IG_ACCESS_TOKEN erneuert (60 Tage verlängert)")
                        else:
                            results["warnings"].append(f"⚠️ FACEBOOK_IG_ACCESS_TOKEN läuft in {days_left} Tagen ab!")
                    else:
                        results["ok"].append(f"✅ FACEBOOK_IG_ACCESS_TOKEN: gültig noch {days_left} Tage")
                else:
                    results["ok"].append("✅ FACEBOOK_IG_ACCESS_TOKEN: läuft nie ab (Page Token)")
            else:
                new_token = await _try_refresh_ig_user_token(ig_token, session)
                if new_token:
                    _update_env_var("FACEBOOK_IG_ACCESS_TOKEN", new_token)
                    results["refreshed"].append("🔄 FACEBOOK_IG_ACCESS_TOKEN war abgelaufen — erneuert!")
                else:
                    results["errors"].append("❌ FACEBOOK_IG_ACCESS_TOKEN: ungültig, Erneuerung fehlgeschlagen!")

    # ── Telegram-Report ───────────────────────────────────────────────────────
    if results["errors"] or results["warnings"] or results["refreshed"]:
        lines = ["🔐 <b>Meta Token Health Check</b>"]
        lines += results["errors"]
        lines += results["warnings"]
        lines += results["refreshed"]
        if results["ok"]:
            lines += ["", "Auch OK:"] + results["ok"][:3]
        await _tg("\n".join(lines))

    log.info(f"Health Check: {len(results['ok'])} OK, {len(results['warnings'])} Warnungen, {len(results['errors'])} Fehler, {len(results['refreshed'])} erneuert")
    return results


def _update_env_var(key: str, value: str):
    """Aktualisiert eine Env-Variable in der .env Datei."""
    env_path = _BASE / ".env"
    try:
        content = env_path.read_text()
        lines = content.splitlines()
        new_lines = []
        updated = False
        for line in lines:
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
                updated = True
                log.info(f"Env-Variable {key} in .env aktualisiert")
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"{key}={value}")
        env_path.write_text("\n".join(new_lines) + "\n")
        os.environ[key] = value
    except Exception as e:
        log.error(f"Env-Update für {key} fehlgeschlagen: {e}")


async def main():
    log.info("IG Token Refresh startet")
    while True:
        try:
            await check_and_refresh_all()
        except Exception as e:
            log.error(f"Fehler: {e}")
        await asyncio.sleep(86400)  # Täglich prüfen


if __name__ == "__main__":
    asyncio.run(main())
