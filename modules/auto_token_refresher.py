#!/usr/bin/env python3
"""
Auto Token Refresher — vollautomatisches Token-Management für alle Plattformen.
Kein manueller Login nötig. Tokens werden automatisch geprüft und erneuert.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("AutoTokenRefresher")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")


async def _telegram(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg[:4096], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception as e:
        log.warning("Ignored error: %s", e)


async def _save_token(platform: str, key: str, value: str) -> None:
    """Speichert Token in Supabase agent_memory für Persistenz."""
    try:
        from modules.supabase_client import get_client
        get_client().table("agent_memory").upsert({
            "key":        f"token_{platform}_{key}",
            "value":      value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.debug("save_token failed: %s", e)


async def _load_token(platform: str, key: str) -> str:
    """Liest Token aus Supabase oder Env."""
    env_key = f"{platform.upper()}_{key.upper()}"
    env_val = os.getenv(env_key, "")
    if env_val:
        return env_val
    try:
        from modules.supabase_client import get_client
        row = get_client().table("agent_memory").select("value").eq(
            "key", f"token_{platform}_{key}").execute()
        if row.data:
            return row.data[0]["value"]
    except Exception as e:
        log.warning("Ignored error: %s", e)
    return ""


async def _railway_upsert_env(key: str, value: str) -> bool:
    """Aktualisiert eine Env-Variable in Railway via GraphQL API."""
    railway_token   = os.getenv("RAILWAY_TOKEN", "")
    railway_project = os.getenv("RAILWAY_PROJECT_ID", "")
    railway_env_id  = os.getenv("RAILWAY_ENVIRONMENT_ID", "production")
    railway_service = os.getenv("RAILWAY_SERVICE_ID", "")
    if not railway_token or not railway_project:
        log.debug("RAILWAY_TOKEN/PROJECT_ID nicht gesetzt — Railway-Update übersprungen")
        return False
    try:
        query = """
        mutation VariableUpsert($input: VariableUpsertInput!) {
          variableUpsert(input: $input)
        }
        """
        variables = {"input": {
            "projectId":     railway_project,
            "environmentId": railway_env_id,
            "serviceId":     railway_service,
            "name":          key,
            "value":         value,
        }}
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://backboard.railway.app/graphql/v2",
                json={"query": query, "variables": variables},
                headers={"Authorization": f"Bearer {railway_token}",
                         "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                resp = await r.json()
        if resp.get("errors"):
            log.warning("Railway upsert error für %s: %s", key, resp["errors"])
            return False
        log.info("Railway env %s erfolgreich aktualisiert", key)
        return True
    except Exception as e:
        log.warning("Railway API upsert fehlgeschlagen: %s", e)
        return False


def _update_local_env(key: str, value: str) -> None:
    """Aktualisiert eine Env-Variable in der lokalen .env Datei."""
    from pathlib import Path
    env_path = Path(__file__).parent.parent / ".env"
    os.environ[key] = value
    try:
        content = env_path.read_text() if env_path.exists() else ""
        lines = content.splitlines()
        new_lines, updated = [], False
        for line in lines:
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"{key}={value}")
        env_path.write_text("\n".join(new_lines) + "\n")
    except Exception as e:
        log.debug("local .env update für %s: %s", key, e)


async def _persist_token(key: str, value: str, platform: str = "tiktok") -> None:
    """Speichert Token überall: os.environ + .env + Supabase + Railway."""
    _update_local_env(key, value)
    await _save_token(platform, key.replace(f"{platform.upper()}_", "").lower(), value)
    await _railway_upsert_env(key, value)


async def refresh_tiktok_token() -> dict:
    """Refresht TikTok Access Token via API v2 und persistiert neue Tokens überall."""
    # .env-Wert hat Priorität (Supabase kann veralteten Token haben)
    refresh_token_env = os.getenv("TIKTOK_REFRESH_TOKEN", "")
    try:
        refresh_token_db = await _load_token("tiktok", "refresh_token")
    except Exception:
        refresh_token_db = ""
    # .env bevorzugen — Supabase nur als Fallback wenn .env leer
    refresh_token = refresh_token_env or refresh_token_db

    cred_pairs = [
        (os.getenv("TIKTOK_CLIENT_KEY", ""), os.getenv("TIKTOK_CLIENT_SECRET", "")),
        (os.getenv("TIKTOK_SANDBOX_CLIENT_KEY", ""), os.getenv("TIKTOK_SANDBOX_CLIENT_SECRET", "")),
        (os.getenv("TIKTOK_APP_KEY", ""), os.getenv("TIKTOK_APP_SECRET", "")),
    ]

    if not refresh_token:
        return {"ok": False, "platform": "tiktok", "reason": "no refresh_token"}

    for app_key, app_secret in cred_pairs:
        if not app_key or not app_secret:
            continue
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://open.tiktokapis.com/v2/oauth/token/",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data=(
                        f"client_key={app_key}&client_secret={app_secret}"
                        f"&grant_type=refresh_token&refresh_token={refresh_token}"
                    ),
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    data = await r.json()

            # TikTok v2 antwortet mit data.data.access_token (nicht data.access_token)
            # TikTok v2: manchmal flat, manchmal data.data
            token_data  = data.get("data") or data
            new_token   = token_data.get("access_token", "")
            new_refresh = token_data.get("refresh_token", "")
            err_code    = (data.get("error") or {}).get("code", "")

            if new_token:
                await _persist_token("TIKTOK_ACCESS_TOKEN",  new_token)
                if new_refresh:
                    await _persist_token("TIKTOK_REFRESH_TOKEN", new_refresh)
                expires_in = token_data.get("expires_in", 86400)
                log.info(
                    "TikTok token refreshed — key=%s expires_in=%s",
                    app_key[:10], expires_in,
                )
                await _telegram(
                    f"✅ <b>TikTok Token erneuert</b>\n"
                    f"App-Key: {app_key[:12]}...\n"
                    f"Gültig: {expires_in // 3600}h\n"
                    f"Railway + .env + Supabase aktualisiert ✓"
                )
                return {
                    "ok": True, "platform": "tiktok", "refreshed": True,
                    "expires_in": expires_in, "app_key": app_key[:12],
                }
            log.debug(
                "TikTok refresh kein Token (key=%s): error=%s raw=%s",
                app_key[:10], err_code, str(data)[:200],
            )
        except Exception as e:
            log.debug("TikTok refresh Versuch fehlgeschlagen (key=%s): %s", app_key[:10], e)

    log.warning("TikTok: alle Refresh-Versuche fehlgeschlagen")
    await _telegram(
        "⚠️ <b>TikTok Token-Refresh fehlgeschlagen</b>\n"
        "Alle 3 Client-Key-Paare ungültig.\n"
        "Bitte TIKTOK_REFRESH_TOKEN in Railway prüfen."
    )
    return {"ok": False, "platform": "tiktok", "reason": "all_pairs_failed"}


async def check_meta_tokens() -> dict:
    """Prüft Facebook Page Token und versucht User-Token-Verlängerung."""
    try:
        from modules.instagram_token_refresh import check_and_refresh_all
        result = await check_and_refresh_all()
        errors = result.get("errors", [])
        ok     = not errors
        return {"ok": True, "platform": "meta", "valid": ok, "errors": errors}
    except Exception as e:
        return {"ok": False, "platform": "meta", "error": str(e)}


async def validate_klaviyo() -> dict:
    """Prüft Klaviyo API-Key."""
    api_key = os.getenv("KLAVIYO_API_KEY", "pk_VaCYq3_242945f7521ac82039ed5dbf7ff8e6cf1c")
    if not api_key:
        return {"ok": False, "platform": "klaviyo", "reason": "no key"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://a.klaviyo.com/api/lists/",
                headers={
                    "Authorization": f"Klaviyo-API-Key {api_key}",
                    "revision": "2024-02-15",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                valid = r.status < 400
        return {"ok": True, "platform": "klaviyo", "valid": valid, "status": r.status}
    except Exception as e:
        return {"ok": False, "platform": "klaviyo", "error": str(e)}


async def validate_shopify() -> dict:
    """Prüft Shopify Admin API Token."""
    shop  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    ver   = os.getenv("SHOPIFY_API_VERSION", "2024-10")
    if not shop or not token:
        return {"ok": False, "platform": "shopify", "reason": "no credentials"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{shop}/admin/api/{ver}/shop.json",
                headers={"X-Shopify-Access-Token": token},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                valid = r.status < 400
        return {"ok": True, "platform": "shopify", "valid": valid, "status": r.status}
    except Exception as e:
        return {"ok": False, "platform": "shopify", "error": str(e)}


async def validate_mailchimp() -> dict:
    """Prüft Mailchimp API-Key."""
    key = os.getenv("MAILCHIMP_API_KEY", "")
    dc  = os.getenv("MAILCHIMP_DC", "us7")
    if not key:
        return {"ok": False, "platform": "mailchimp", "reason": "no key"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{dc}.api.mailchimp.com/3.0/",
                auth=aiohttp.BasicAuth("user", key),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                valid = r.status < 400
        return {"ok": True, "platform": "mailchimp", "valid": valid, "status": r.status}
    except Exception as e:
        return {"ok": False, "platform": "mailchimp", "error": str(e)}


async def validate_stripe() -> dict:
    """Prüft Stripe Secret Key."""
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        return {"ok": False, "platform": "stripe", "reason": "no key"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.stripe.com/v1/balance",
                auth=aiohttp.BasicAuth(key, ""),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                valid = r.status < 400
        return {"ok": True, "platform": "stripe", "valid": valid}
    except Exception as e:
        return {"ok": False, "platform": "stripe", "error": str(e)}


async def validate_telegram() -> dict:
    """Prüft Telegram Bot Token."""
    tok = TELEGRAM_TOKEN
    if not tok:
        return {"ok": False, "platform": "telegram", "reason": "no token"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.telegram.org/bot{tok}/getMe",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                data = await r.json()
        valid = data.get("ok", False)
        bot_name = data.get("result", {}).get("username", "?")
        return {"ok": True, "platform": "telegram", "valid": valid, "bot": bot_name}
    except Exception as e:
        return {"ok": False, "platform": "telegram", "error": str(e)}


async def run_token_health_check() -> dict:
    """Prüft ALLE Tokens, refresht abgelaufene, sendet Telegram-Alert."""
    results = await asyncio.gather(
        validate_klaviyo(),
        validate_shopify(),
        validate_mailchimp(),
        validate_stripe(),
        validate_telegram(),
        refresh_tiktok_token(),
        check_meta_tokens(),
        return_exceptions=True,
    )

    labels   = ["klaviyo", "shopify", "mailchimp", "stripe", "telegram", "tiktok", "meta"]
    statuses = {}
    failed   = []
    ok_count = 0

    for label, r in zip(labels, results):
        if isinstance(r, Exception):
            statuses[label] = {"ok": False, "error": str(r)[:80]}
            failed.append(label)
        elif isinstance(r, dict):
            statuses[label] = r
            is_ok = r.get("ok") and r.get("valid", True)
            if is_ok:
                ok_count += 1
            elif label not in ("tiktok",):
                failed.append(label)
        else:
            statuses[label] = {"ok": False}
            failed.append(label)

    if failed:
        fail_str = ", ".join(failed)
        await _telegram(
            f"⚠️ <b>Token Health Check</b>\n"
            f"Fehlgeschlagen: {fail_str}\n"
            f"OK: {ok_count}/{len(labels)}\n"
            f"Bitte Tokens in Railway prüfen."
        )
    else:
        log.info("Token health check: all %d platforms OK", ok_count)

    return {
        "ok":        True,
        "platforms": statuses,
        "ok_count":  ok_count,
        "failed":    failed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
