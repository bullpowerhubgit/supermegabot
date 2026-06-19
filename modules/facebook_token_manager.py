"""Facebook Token Manager — auto-extend tokens, alert when expired."""
import os
import logging
import aiohttp
from datetime import datetime

log = logging.getLogger(__name__)

APP_ID     = os.getenv("FACEBOOK_APP_ID", "1225412136200609")
APP_SECRET = os.getenv("FACEBOOK_APP_SECRET", "bdd22b7b61fcfd9fd8eed1ab8fedf27b")
TG_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT    = os.getenv("TELEGRAM_CHAT_ID", "")
BASE       = "https://graph.facebook.com/v19.0"
CALLBACK_URL = "https://dudirudibot-mega-production.up.railway.app/api/facebook/callback"
RAILWAY_SERVICE = "dudirudibot-mega"
SCOPES = "pages_manage_posts,pages_read_engagement,instagram_basic,instagram_content_publish,pages_show_list,public_profile"


def get_oauth_url() -> str:
    return (
        f"https://www.facebook.com/v19.0/dialog/oauth?"
        f"client_id={APP_ID}"
        f"&redirect_uri={CALLBACK_URL}"
        f"&scope={SCOPES}"
        f"&response_type=code"
    )


def _set_railway_var(key: str, value: str) -> bool:
    """Set Railway env var using correct CLI syntax."""
    try:
        import subprocess
        r = subprocess.run(
            ["railway", "variables", "set", f"{key}={value}", "--service", RAILWAY_SERVICE],
            capture_output=True, timeout=30
        )
        return r.returncode == 0
    except Exception as e:
        log.warning("Railway var set failed %s: %s", key, e)
        return False

PAGE_IDS = {
    "IWIN":       os.getenv("FACEBOOK_PAGE_ID_IWIN", "1135864516276500"),
    "AIITEC":     os.getenv("FACEBOOK_PAGE_ID_AIITEC", "1016738738178786"),
    "I_NEED_IT":  os.getenv("FACEBOOK_PAGE_ID_I_NEED_IT", "1058648427339278"),
}


async def _tg(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


async def check_token(token: str) -> dict:
    """Check if a token is valid via /debug_token."""
    if not token:
        return {"valid": False, "reason": "empty token"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{BASE}/debug_token",
                params={"input_token": token, "access_token": f"{APP_ID}|{APP_SECRET}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json(content_type=None)
        data = d.get("data", {})
        return {
            "valid":   data.get("is_valid", False),
            "expires": data.get("expires_at", 0),
            "type":    data.get("type", "unknown"),
            "scopes":  data.get("scopes", []),
        }
    except Exception as e:
        return {"valid": False, "reason": str(e)}


async def extend_user_token(short_token: str) -> str | None:
    """Exchange short-lived user token for 60-day long-lived token."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{BASE}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": APP_ID,
                    "client_secret": APP_SECRET,
                    "fb_exchange_token": short_token,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        return d.get("access_token")
    except Exception as e:
        log.warning("Token extend failed: %s", e)
        return None


async def get_never_expiring_page_token(page_id: str, long_lived_user_token: str) -> str | None:
    """Get a never-expiring page token from long-lived user token."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{BASE}/{page_id}",
                params={"fields": "access_token", "access_token": long_lived_user_token},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json(content_type=None)
        return d.get("access_token")
    except Exception as e:
        log.warning("Page token get failed for %s: %s", page_id, e)
        return None


async def refresh_all_tokens() -> dict:
    """Try to refresh all Facebook tokens. Returns status per token."""
    results = {}
    user_token = os.getenv("FACEBOOK_USER_TOKEN", "")

    # 1. Check current user token
    user_check = await check_token(user_token)
    results["user_token"] = user_check

    if not user_check.get("valid") or "pages_manage_posts" not in user_check.get("scopes", []):
        oauth_url = get_oauth_url()
        reason = "abgelaufen" if not user_check.get("valid") else "fehlt pages_manage_posts scope"
        msg = (
            f"⚠️ *Facebook Token {reason}!*\n\n"
            "Klick diesen Link → Login → Berechtigung erteilen:\n"
            f"{oauth_url}\n\n"
            "Danach werden alle Page Tokens automatisch gesetzt und Posting funktioniert."
        )
        await _tg(msg)
        results["action_needed"] = True
        results["oauth_url"] = oauth_url
        return results

    # 2. Extend user token to 60-day token
    extended = await extend_user_token(user_token)
    if extended:
        results["extended_user_token"] = extended[:20] + "..."
        log.info("FB: Extended user token obtained")

        # 3. Get never-expiring page tokens for all pages
        for page_name, page_id in PAGE_IDS.items():
            page_token = await get_never_expiring_page_token(page_id, extended)
            if page_token:
                env_key = f"FACEBOOK_PAGE_TOKEN_{page_name}"
                # Update Railway env var
                if _set_railway_var(env_key, page_token):
                    results[f"page_{page_name}"] = "refreshed"
                    log.info("FB: Page token refreshed for %s", page_name)
                else:
                    results[f"page_{page_name}"] = "railway_set_failed"
            else:
                results[f"page_{page_name}"] = "failed"

        # Also update META_ACCESS_TOKEN and FACEBOOK_PAGE_TOKEN aliases
        iwin_token = os.getenv("FACEBOOK_PAGE_TOKEN_IWIN", "")
        if iwin_token:
            _set_railway_var("META_ACCESS_TOKEN", iwin_token)
            _set_railway_var("FACEBOOK_PAGE_TOKEN", iwin_token)

        await _tg(
            f"✅ *Facebook Tokens erfolgreich erneuert!*\n"
            f"Seiten: {', '.join(PAGE_IDS.keys())}\n"
            f"Datum: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
    else:
        results["extend_failed"] = True

    return results


async def handle_facebook_oauth_callback(code: str, redirect_uri: str) -> dict:
    """Exchange OAuth code for access token after user authorizes."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{BASE}/oauth/access_token",
                params={
                    "client_id": APP_ID,
                    "client_secret": APP_SECRET,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)

        short_token = d.get("access_token")
        if not short_token:
            return {"ok": False, "error": d.get("error", {}).get("message", "No token")}

        # Extend to long-lived
        long_token = await extend_user_token(short_token)
        if not long_token:
            return {"ok": False, "error": "Could not extend token"}

        # Save to Railway
        _set_railway_var("FACEBOOK_USER_TOKEN", long_token)

        # Refresh all page tokens
        result = await refresh_all_tokens()
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}
