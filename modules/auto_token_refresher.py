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


async def refresh_tiktok_token() -> dict:
    """Refresht TikTok Access Token via API v2. Hinweis: benötigt passende Client-Credentials."""
    refresh_token = await _load_token("tiktok", "refresh_token")
    # Alle verfügbaren Client-Key-Paare versuchen
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

            if data.get("access_token"):
                new_token   = data["access_token"]
                new_refresh = data.get("refresh_token", refresh_token)
                await _save_token("tiktok", "access_token",  new_token)
                await _save_token("tiktok", "refresh_token", new_refresh)
                log.info("TikTok token refreshed with client_key=%s", app_key[:10])
                return {"ok": True, "platform": "tiktok", "refreshed": True}
        except Exception as e:
            log.debug("TikTok refresh attempt failed (key=%s): %s", app_key[:10], e)

    log.warning("TikTok: alle Refresh-Versuche fehlgeschlagen — neue OAuth-Credentials nötig")
    return {"ok": False, "platform": "tiktok", "reason": "invalid_client — fresh OAuth required"}


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
