"""
mega_health_checker.py — Platform Health Auto-Fixer for SuperMegaBot
=====================================================================
Checks Shopify, Stripe, Supabase, Telegram, SendGrid, Meta Ads, Railway.
Sends Telegram alerts on failures. Saves results to data/health_stats.json.

Dependencies: stdlib only (urllib.request, json, logging, asyncio, os, etc.)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent.parent / "data"
HEALTH_STATS_PATH = _DATA_DIR / "health_stats.json"

_TIMEOUT = 10       # seconds — per check
_RAILWAY_TIMEOUT = 5  # tighter for self-check


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def _env(key: str) -> str:
    return os.getenv(key, "")


# ---------------------------------------------------------------------------
# Low-level urllib helpers
# ---------------------------------------------------------------------------

def _json_get(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = _TIMEOUT,
) -> tuple[int, dict | list]:
    """
    Perform a GET request and decode the JSON body.
    Returns (http_status, parsed_body).
    Raises on network/connection errors.
    """
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read() or b""
    # parse JSON
    try:
        data = json.loads(body)
    except Exception:
        data = {"_raw": body.decode(errors="replace")}
    return status, data


def _json_post(
    url: str,
    payload: dict,
    headers: dict[str, str] | None = None,
    timeout: int = _TIMEOUT,
) -> tuple[int, dict | list]:
    """POST JSON payload, return (status, parsed_body)."""
    data = json.dumps(payload).encode()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read() or b""
    try:
        parsed = json.loads(body)
    except Exception:
        parsed = {"_raw": body.decode(errors="replace")}
    return status, parsed


# ---------------------------------------------------------------------------
# 1. check_shopify
# ---------------------------------------------------------------------------

def check_shopify() -> dict:
    """
    GET /admin/api/2024-01/shop.json
    Returns {ok, name, plan, error}
    """
    domain = _env("SHOPIFY_SHOP_DOMAIN")
    token = _env("SHOPIFY_ADMIN_API_TOKEN")
    if not domain or not token:
        msg = "Missing SHOPIFY_SHOP_DOMAIN or SHOPIFY_ADMIN_API_TOKEN"
        logger.warning("check_shopify: %s", msg)
        return {"ok": False, "error": msg}
    url = f"https://{domain}/admin/api/2024-01/shop.json"
    headers = {"X-Shopify-Access-Token": token}
    try:
        status, data = _json_get(url, headers=headers)
        if status == 200 and isinstance(data, dict) and "shop" in data:
            shop = data["shop"]
            result = {
                "ok": True,
                "name": shop.get("name", ""),
                "plan": shop.get("plan_name", ""),
            }
            logger.info("check_shopify OK: %s (%s)", result["name"], result["plan"])
            return result
        err = f"HTTP {status}: {str(data)[:120]}"
        logger.error("check_shopify failed: %s", err)
        return {"ok": False, "error": err}
    except Exception as exc:
        logger.exception("check_shopify exception")
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# 2. check_stripe
# ---------------------------------------------------------------------------

def check_stripe() -> dict:
    """
    GET https://api.stripe.com/v1/balance
    Returns {ok, currency, error}
    """
    key = _env("STRIPE_SECRET_KEY")
    if not key:
        msg = "Missing STRIPE_SECRET_KEY"
        logger.warning("check_stripe: %s", msg)
        return {"ok": False, "error": msg}
    credentials = b64encode(f"{key}:".encode()).decode()
    headers = {"Authorization": f"Basic {credentials}"}
    try:
        status, data = _json_get("https://api.stripe.com/v1/balance", headers=headers)
        if status == 200 and isinstance(data, dict) and "available" in data:
            available = data["available"]
            currency = available[0].get("currency", "?").upper() if available else "?"
            result = {"ok": True, "currency": currency}
            logger.info("check_stripe OK: currency=%s", currency)
            return result
        err_msg = ""
        if isinstance(data, dict) and "error" in data:
            err_msg = data["error"].get("message", "")
        err = f"HTTP {status}: {err_msg or str(data)[:120]}"
        logger.error("check_stripe failed: %s", err)
        return {"ok": False, "error": err}
    except Exception as exc:
        logger.exception("check_stripe exception")
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# 3. check_supabase
# ---------------------------------------------------------------------------

def check_supabase() -> dict:
    """
    GET {SUPABASE_URL}/rest/v1/scraped_products?limit=1 with apikey header
    Returns {ok, error}
    """
    base_url = _env("SUPABASE_URL").rstrip("/")
    service_key = _env("SUPABASE_SERVICE_KEY")
    if not base_url or not service_key:
        msg = "Missing SUPABASE_URL or SUPABASE_SERVICE_KEY"
        logger.warning("check_supabase: %s", msg)
        return {"ok": False, "error": msg}
    url = f"{base_url}/rest/v1/scraped_products?limit=1"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }
    try:
        status, data = _json_get(url, headers=headers)
        if status in (200, 206):
            logger.info("check_supabase OK: HTTP %s", status)
            return {"ok": True}
        err = f"HTTP {status}: {str(data)[:120]}"
        logger.error("check_supabase failed: %s", err)
        return {"ok": False, "error": err}
    except Exception as exc:
        logger.exception("check_supabase exception")
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# 4. check_telegram
# ---------------------------------------------------------------------------

def check_telegram() -> dict:
    """
    GET https://api.telegram.org/bot{token}/getMe
    Returns {ok, username, error}
    """
    token = _env("TELEGRAM_BOT_TOKEN")
    if not token:
        msg = "Missing TELEGRAM_BOT_TOKEN"
        logger.warning("check_telegram: %s", msg)
        return {"ok": False, "error": msg}
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        status, data = _json_get(url)
        if status == 200 and isinstance(data, dict) and data.get("ok"):
            username = data.get("result", {}).get("username", "")
            logger.info("check_telegram OK: @%s", username)
            return {"ok": True, "username": username}
        err = f"HTTP {status}: {data.get('description', str(data)[:120]) if isinstance(data, dict) else str(data)[:120]}"
        logger.error("check_telegram failed: %s", err)
        return {"ok": False, "error": err}
    except Exception as exc:
        logger.exception("check_telegram exception")
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# 5. check_sendgrid
# ---------------------------------------------------------------------------

def check_sendgrid() -> dict:
    """
    GET https://api.sendgrid.com/v3/user/credits with Bearer auth
    Returns {ok, error}
    """
    api_key = _env("SENDGRID_API_KEY")
    if not api_key:
        msg = "Missing SENDGRID_API_KEY"
        logger.warning("check_sendgrid: %s", msg)
        return {"ok": False, "error": msg}
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        status, data = _json_get("https://api.sendgrid.com/v3/user/credits", headers=headers)
        if status == 200:
            logger.info("check_sendgrid OK: remain=%s total=%s",
                        data.get("remain") if isinstance(data, dict) else "?",
                        data.get("total") if isinstance(data, dict) else "?")
            return {"ok": True}
        err_detail = ""
        if isinstance(data, dict) and "errors" in data:
            err_detail = str(data["errors"])[:100]
        err = f"HTTP {status}: {err_detail or str(data)[:120]}"
        logger.error("check_sendgrid failed: %s", err)
        return {"ok": False, "error": err}
    except Exception as exc:
        logger.exception("check_sendgrid exception")
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# 6. check_meta_ads
# ---------------------------------------------------------------------------

def check_meta_ads() -> dict:
    """
    GET https://graph.facebook.com/v20.0/me?access_token={token}
    Returns {ok, name, error}
    """
    token = _env("META_ADS_TOKEN")
    if not token:
        msg = "Missing META_ADS_TOKEN"
        logger.warning("check_meta_ads: %s", msg)
        return {"ok": False, "error": msg}
    params = urllib.parse.urlencode({"access_token": token})
    url = f"https://graph.facebook.com/v20.0/me?{params}"
    try:
        status, data = _json_get(url)
        if status == 200 and isinstance(data, dict) and "id" in data:
            name = data.get("name", "")
            logger.info("check_meta_ads OK: %s", name)
            return {"ok": True, "name": name}
        err_msg = ""
        if isinstance(data, dict) and "error" in data:
            err_msg = data["error"].get("message", "")
        err = f"HTTP {status}: {err_msg or str(data)[:120]}"
        logger.error("check_meta_ads failed: %s", err)
        return {"ok": False, "error": err}
    except Exception as exc:
        logger.exception("check_meta_ads exception")
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# 7. check_railway_self
# ---------------------------------------------------------------------------

def check_railway_self() -> dict:
    """
    GET https://supermegabot-production.up.railway.app/health with 5s timeout
    Returns {ok, error}
    """
    url = "https://supermegabot-production.up.railway.app/health"
    try:
        status, data = _json_get(url, timeout=_RAILWAY_TIMEOUT)
        status_val = data.get("status", "") if isinstance(data, dict) else ""
        if status == 200 and status_val in ("ok", "healthy", "up"):
            logger.info("check_railway_self OK")
            return {"ok": True}
        err = f"HTTP {status}: {str(data)[:120]}"
        logger.error("check_railway_self failed: %s", err)
        return {"ok": False, "error": err}
    except Exception as exc:
        logger.exception("check_railway_self exception")
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# 8. run_all_checks
# ---------------------------------------------------------------------------

_CHECK_REGISTRY: dict[str, callable] = {
    "shopify":  check_shopify,
    "stripe":   check_stripe,
    "supabase": check_supabase,
    "telegram": check_telegram,
    "sendgrid": check_sendgrid,
    "meta_ads": check_meta_ads,
    "railway":  check_railway_self,
}


def run_all_checks() -> dict:
    """
    Run every platform check sequentially.
    Returns {timestamp, checks: {name: result}, failed: [names], ok_count, fail_count}
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    checks: dict[str, dict] = {}

    for name, fn in _CHECK_REGISTRY.items():
        logger.info("Running health check: %s", name)
        try:
            checks[name] = fn()
        except Exception as exc:
            logger.exception("Unhandled error in check %s", name)
            checks[name] = {"ok": False, "error": f"Unhandled: {exc}"}

    failed = [name for name, result in checks.items() if not result.get("ok")]
    ok_count = len(checks) - len(failed)
    fail_count = len(failed)

    results = {
        "timestamp": timestamp,
        "checks": checks,
        "failed": failed,
        "ok_count": ok_count,
        "fail_count": fail_count,
    }

    _save_health_stats(results)
    logger.info(
        "Health checks complete — %d OK, %d FAILED. Failed: %s",
        ok_count, fail_count, failed,
    )
    return results


# ---------------------------------------------------------------------------
# 9. send_health_alert
# ---------------------------------------------------------------------------

def send_health_alert(results: dict) -> bool:
    """
    If any services failed, send a Telegram message listing every service
    with ❌ (failed) or ✅ (ok).
    Returns True if the message was sent, False otherwise.
    """
    bot_token = _env("TELEGRAM_BOT_TOKEN")
    chat_id = _env("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        logger.warning("send_health_alert: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        return False

    failed: list[str] = results.get("failed", [])
    if not failed:
        logger.info("send_health_alert: all services healthy — no alert sent")
        return False

    checks: dict[str, dict] = results.get("checks", {})
    timestamp = results.get("timestamp", datetime.now(timezone.utc).isoformat())

    lines: list[str] = [
        "🚨 *SuperMegaBot Health Alert*",
        f"🕐 `{timestamp}`",
        "",
    ]

    for name, result in checks.items():
        label = name.upper().replace("_", " ")
        if result.get("ok"):
            extra = ""
            for field in ("name", "username", "currency", "plan"):
                if field in result and result[field]:
                    extra = f" — {result[field]}"
                    break
            lines.append(f"✅ {label}{extra}")
        else:
            error = result.get("error", "unknown error")
            if len(error) > 120:
                error = error[:117] + "..."
            lines.append(f"❌ {label}: `{error}`")

    lines += [
        "",
        f"*{results.get('ok_count', 0)} OK* | *{results.get('fail_count', 0)} FAILED*",
    ]

    text = "\n".join(lines)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        status, resp_data = _json_post(url, payload)
        if isinstance(resp_data, dict) and resp_data.get("ok"):
            logger.info("send_health_alert: Telegram alert sent successfully")
            return True
        logger.error("send_health_alert: Telegram returned non-ok: HTTP %s %s", status, resp_data)
        return False
    except Exception as exc:
        logger.exception("send_health_alert: failed to send Telegram alert")
        return False


# ---------------------------------------------------------------------------
# 10. async run_health_cycle
# ---------------------------------------------------------------------------

async def run_health_cycle() -> dict:
    """
    Async entry point: run all checks in a thread-pool executor (keeps the
    event loop free) and send a Telegram alert if any failures are found.
    Returns the results dict.
    """
    loop = asyncio.get_event_loop()
    results: dict = await loop.run_in_executor(None, run_all_checks)
    if results.get("fail_count", 0) > 0:
        await loop.run_in_executor(None, send_health_alert, results)
    return results


# ---------------------------------------------------------------------------
# 11. get_health_stats
# ---------------------------------------------------------------------------

def get_health_stats() -> dict:
    """
    Return the latest health check results previously saved to
    data/health_stats.json.  Call run_all_checks() first to populate it.
    """
    if not HEALTH_STATS_PATH.exists():
        logger.warning("get_health_stats: %s not found — run run_all_checks() first", HEALTH_STATS_PATH)
        return {"error": "No health stats available. Run run_all_checks() first."}
    try:
        with open(HEALTH_STATS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.exception("get_health_stats: failed to read %s", HEALTH_STATS_PATH)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Internal: persist to data/health_stats.json
# ---------------------------------------------------------------------------

def _save_health_stats(results: dict) -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(HEALTH_STATS_PATH, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2, ensure_ascii=False)
        logger.debug("Health stats saved to %s", HEALTH_STATS_PATH)
    except Exception:
        logger.exception("_save_health_stats: could not write %s", HEALTH_STATS_PATH)


# ---------------------------------------------------------------------------
# Backward-compat aliases (for any existing callers using the old names)
# ---------------------------------------------------------------------------

def check_all_sync() -> dict:          # alias → run_all_checks
    return run_all_checks()

def get_status() -> dict:              # alias → get_health_stats
    return get_health_stats()


# ---------------------------------------------------------------------------
# CLI entry-point: python -m modules.mega_health_checker
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _results = run_all_checks()
    send_health_alert(_results)
    print(json.dumps(_results, indent=2, ensure_ascii=False))
