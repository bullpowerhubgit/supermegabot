#!/usr/bin/env python3
"""
BullPower MEGA Command Center — Platform Health Checker
=======================================================
Tests all 14 platform APIs in parallel, auto-heals failures, sends TG report.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

log = logging.getLogger("MegaHealthChecker")

# ── paths ─────────────────────────────────────────────────────────────────────
_DATA = Path(__file__).parent.parent / "data"
HEALTH_REPORT = _DATA / "health_report.json"
HEALTH_FAILURES = _DATA / "health_failures.json"

# ── env helpers ───────────────────────────────────────────────────────────────
def _e(key: str, default: str = "") -> str:
    return os.getenv(key, default) or default


def _reload_env() -> None:
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)


# ── individual check builders ─────────────────────────────────────────────────
async def _get(session: aiohttp.ClientSession, url: str, headers: dict | None = None,
               params: dict | None = None, timeout: int = 10) -> tuple[int, dict | str]:
    try:
        async with session.get(url, headers=headers or {}, params=params or {},
                               timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            try:
                body = await r.json(content_type=None)
            except Exception:
                body = await r.text()
            return r.status, body
    except asyncio.TimeoutError:
        return 0, "timeout"
    except Exception as exc:
        return 0, str(exc)


async def _post(session: aiohttp.ClientSession, url: str, headers: dict,
                payload: dict, timeout: int = 10) -> tuple[int, dict | str]:
    try:
        async with session.post(url, headers=headers, json=payload,
                                timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            try:
                body = await r.json(content_type=None)
            except Exception:
                body = await r.text()
            return r.status, body
    except asyncio.TimeoutError:
        return 0, "timeout"
    except Exception as exc:
        return 0, str(exc)


def _result(platform: str, ok: bool, latency_ms: int, detail: str) -> dict:
    return {
        "platform": platform,
        "ok": ok,
        "latency_ms": latency_ms,
        "detail": str(detail)[:200],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── platform checks ───────────────────────────────────────────────────────────
async def _check_shopify(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    domain = _e("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")
    token = _e("SHOPIFY_ADMIN_API_TOKEN") or _e("SHOPIFY_ACCESS_TOKEN")
    url = f"https://{domain}/admin/api/2026-04/shop.json"
    status, body = await _get(session, url, headers={"X-Shopify-Access-Token": token})
    ok = status == 200 and isinstance(body, dict) and "shop" in body
    detail = body.get("shop", {}).get("name", str(body)[:100]) if ok else str(body)[:100]
    return _result("shopify", ok, int((time.monotonic() - t0) * 1000), detail)


async def _check_stripe(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    key = _e("STRIPE_SECRET_KEY")
    status, body = await _get(session, "https://api.stripe.com/v1/balance",
                              headers={"Authorization": f"Bearer {key}"})
    ok = status == 200 and isinstance(body, dict) and "available" in body
    detail = f"available={body.get('available', '?')}" if ok else str(body)[:100]
    return _result("stripe", ok, int((time.monotonic() - t0) * 1000), detail)


async def _check_anthropic(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    key = _e("ANTHROPIC_API_KEY")
    status, body = await _post(
        session,
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        payload={"model": "claude-haiku-4-5-20251001", "max_tokens": 1, "messages": [{"role": "user", "content": "Hi"}]},
    )
    ok = status == 200 and isinstance(body, dict) and "content" in body
    detail = body.get("model", str(body)[:100]) if ok else str(body)[:100]
    return _result("anthropic", ok, int((time.monotonic() - t0) * 1000), detail)


async def _check_openai(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    key = _e("OPENAI_API_KEY")
    status, body = await _post(
        session,
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        payload={"model": "gpt-4o-mini", "max_tokens": 1, "messages": [{"role": "user", "content": "Hi"}]},
    )
    ok = status == 200 and isinstance(body, dict) and "choices" in body
    detail = body.get("model", str(body)[:100]) if ok else str(body)[:100]
    return _result("openai", ok, int((time.monotonic() - t0) * 1000), detail)


async def _check_facebook(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    token = _e("FACEBOOK_PAGE_TOKEN_AIITEC") or _e("META_ACCESS_TOKEN")
    page_id = _e("FACEBOOK_PAGE_ID", "1016738738178786")
    status, body = await _get(session,
        f"https://graph.facebook.com/v19.0/{page_id}",
        params={"fields": "name,fan_count", "access_token": token})
    ok = status == 200 and isinstance(body, dict) and "name" in body
    detail = body.get("name", str(body)[:100]) if ok else str(body)[:100]
    return _result("facebook", ok, int((time.monotonic() - t0) * 1000), detail)


async def _check_instagram(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    token = _e("FACEBOOK_PAGE_TOKEN_AIITEC") or _e("META_ACCESS_TOKEN")
    ig_id = _e("INSTAGRAM_ACCOUNT_ID", "17841478315197796")
    status, body = await _get(session,
        f"https://graph.facebook.com/v19.0/{ig_id}",
        params={"fields": "username,followers_count", "access_token": token})
    ok = status == 200 and isinstance(body, dict) and "username" in body
    detail = f"@{body.get('username')} {body.get('followers_count',0)} followers" if ok else str(body)[:100]
    return _result("instagram", ok, int((time.monotonic() - t0) * 1000), detail)


async def _check_telegram(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    token = _e("TELEGRAM_BOT_TOKEN")
    status, body = await _get(session, f"https://api.telegram.org/bot{token}/getMe")
    ok = status == 200 and isinstance(body, dict) and body.get("ok")
    detail = body.get("result", {}).get("username", str(body)[:100]) if ok else str(body)[:100]
    return _result("telegram", ok, int((time.monotonic() - t0) * 1000), detail)


async def _check_supabase(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    url = _e("SUPABASE_URL", "").rstrip("/")
    key = _e("SUPABASE_ANON_KEY")
    if not url:
        return _result("supabase", False, 0, "SUPABASE_URL not set")
    status, body = await _get(session, f"{url}/rest/v1/scraped_products",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        params={"limit": "1"})
    ok = status in (200, 206)
    detail = f"rows={len(body) if isinstance(body, list) else '?'}" if ok else str(body)[:100]
    return _result("supabase", ok, int((time.monotonic() - t0) * 1000), detail)


async def _check_klaviyo(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    key = _e("KLAVIYO_API_KEY_AIITEC") or _e("KLAVIYO_API_KEY")
    status, body = await _get(session, "https://a.klaviyo.com/api/accounts/",
        headers={"Authorization": f"Klaviyo-API-Key {key}", "revision": "2024-02-15"})
    ok = status == 200 and isinstance(body, dict)
    detail = str(body.get("data", {}))[: 80] if ok else str(body)[:100]
    return _result("klaviyo", ok, int((time.monotonic() - t0) * 1000), detail)


async def _check_youtube(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    api_key = _e("YOUTUBE_API_KEY")
    channel = _e("YOUTUBE_CHANNEL_ID", "UCy5U7UGOMNkvUR2-5Qm4yiA")
    status, body = await _get(session,
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "statistics", "id": channel, "key": api_key})
    ok = status == 200 and isinstance(body, dict) and body.get("items")
    detail = f"subs={body['items'][0]['statistics'].get('subscriberCount','?')}" if ok else str(body)[:100]
    return _result("youtube", ok, int((time.monotonic() - t0) * 1000), detail)


async def _check_linkedin(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    token = _e("LINKEDIN_ACCESS_TOKEN")
    status, body = await _get(session, "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {token}"})
    ok = status == 200 and isinstance(body, dict) and "name" in body
    detail = body.get("name", str(body)[:100]) if ok else str(body)[:100]
    return _result("linkedin", ok, int((time.monotonic() - t0) * 1000), detail)


async def _check_digistore24(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    ds_key = _e("DIGISTORE24_API_KEY")
    status, body = await _get(session,
        "https://www.digistore24.com/api/call/listProducts/JSON/",
        headers={"X-DS-API-KEY": ds_key})
    ok = status == 200 and isinstance(body, dict) and body.get("result") != "error"
    detail = f"products={len(body.get('data', {}).get('products', []))}" if ok else str(body)[:100]
    return _result("digistore24", ok, int((time.monotonic() - t0) * 1000), detail)


async def _check_printify(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    token = _e("PRINTIFY_API_KEY") or _e("PRINTIFY_TOKEN")
    status, body = await _get(session, "https://api.printify.com/v1/shops.json",
        headers={"Authorization": f"Bearer {token}"})
    ok = status == 200 and isinstance(body, list)
    detail = f"shops={len(body)}" if ok else str(body)[:100]
    return _result("printify", ok, int((time.monotonic() - t0) * 1000), detail)


async def _check_railway(session: aiohttp.ClientSession) -> dict:
    t0 = time.monotonic()
    status, body = await _get(session,
        os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("RAILWAY_STATIC_URL", "https://supermegabot-production.up.railway.app")).rstrip("/") + "/health", timeout=15)
    ok = status == 200 and (
        (isinstance(body, dict) and body.get("status") == "ok") or
        (isinstance(body, str) and "ok" in body.lower())
    )
    detail = str(body)[:100]
    return _result("railway", ok, int((time.monotonic() - t0) * 1000), detail)


# ── orchestration ─────────────────────────────────────────────────────────────
_CHECKERS = [
    _check_shopify, _check_stripe, _check_anthropic, _check_openai,
    _check_facebook, _check_instagram, _check_telegram, _check_supabase,
    _check_klaviyo, _check_youtube, _check_linkedin, _check_digistore24,
    _check_printify, _check_railway,
]


async def check_all() -> dict:
    """Run all platform checks in parallel."""
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[fn(session) for fn in _CHECKERS], return_exceptions=True
        )
    cleaned: list[dict] = []
    for r in results:
        if isinstance(r, Exception):
            cleaned.append(_result("unknown", False, 0, str(r)))
        else:
            cleaned.append(r)
    ok_count = sum(1 for r in cleaned if r["ok"])
    return {
        "results": cleaned,
        "ok_count": ok_count,
        "total": len(cleaned),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def auto_heal(results: list[dict]) -> list[dict]:
    """Attempt platform-specific recovery for failed checks."""
    failed = [r for r in results if not r["ok"]]
    if not failed:
        return results

    # Log failures
    _DATA.mkdir(parents=True, exist_ok=True)
    failures_log: list = []
    if HEALTH_FAILURES.exists():
        try:
            failures_log = json.loads(HEALTH_FAILURES.read_text())
        except Exception:
            failures_log = []
    failures_log.extend(failed)
    failures_log = failures_log[-500:]  # keep last 500
    HEALTH_FAILURES.write_text(json.dumps(failures_log, indent=2))

    healed: list[dict] = []
    async with aiohttp.ClientSession() as session:
        for r in failed:
            platform = r["platform"]
            if platform == "shopify":
                _reload_env()
                new_r = await _check_shopify(session)
                new_r["detail"] = "(healed) " + new_r["detail"]
                healed.append(new_r)
            elif platform == "supabase":
                # Try with service key
                url = _e("SUPABASE_URL", "").rstrip("/")
                svc_key = _e("SUPABASE_SERVICE_KEY")
                if url and svc_key:
                    t0 = time.monotonic()
                    status, body = await _get(session, f"{url}/rest/v1/scraped_products",
                        headers={"apikey": svc_key, "Authorization": f"Bearer {svc_key}"},
                        params={"limit": "1"})
                    ok = status in (200, 206)
                    healed.append(_result("supabase", ok,
                        int((time.monotonic() - t0) * 1000),
                        f"(svc-key) {str(body)[:80]}"))
            elif platform == "telegram":
                # Try reloading token
                _reload_env()
                new_r = await _check_telegram(session)
                new_r["detail"] = "(healed) " + new_r["detail"]
                healed.append(new_r)

    # Merge healed results back
    healed_map = {r["platform"]: r for r in healed}
    final = []
    for r in results:
        if r["platform"] in healed_map:
            final.append(healed_map[r["platform"]])
        else:
            final.append(r)
    return final


async def send_telegram_report(results: list[dict]) -> None:
    """Send formatted health report to Telegram."""
    token = _e("TELEGRAM_BOT_TOKEN")
    chat_id = _e("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    lines = ["🔍 *Platform Health Report*\n"]
    for r in results:
        icon = "✅" if r["ok"] else "❌"
        plat = r["platform"].upper()
        ms = r["latency_ms"]
        detail = r["detail"][:60]
        lines.append(f"{icon} `{plat}` ({ms}ms) — {detail}")

    ok_count = sum(1 for r in results if r["ok"])
    lines.append(f"\n*{ok_count}/{len(results)} OK* — {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    msg = "\n".join(lines)

    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as exc:
        log.warning("TG report failed: %s", exc)


async def run_health_cycle() -> dict:
    """Full cycle: check → heal → report → save."""
    log.info("Starting health cycle")
    report = await check_all()
    results = report["results"]
    results = await auto_heal(results)
    report["results"] = results
    report["ok_count"] = sum(1 for r in results if r["ok"])

    _DATA.mkdir(parents=True, exist_ok=True)
    HEALTH_REPORT.write_text(json.dumps(report, indent=2))

    await send_telegram_report(results)
    log.info("Health cycle done: %d/%d OK", report["ok_count"], report["total"])
    return report


def get_status() -> dict:
    """Return last saved health report for dashboard integration."""
    if HEALTH_REPORT.exists():
        try:
            return json.loads(HEALTH_REPORT.read_text())
        except Exception:
            pass
    return {"results": [], "ok_count": 0, "total": 0, "timestamp": None}
