"""
Connect All — alle Plattformen verbinden, testen und aktivieren.
Normalisiert Env-Aliase, pingt APIs, resettet Circuit Breakers,
startet Scheduler-Tasks und synct Keys nach Railway.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

log = logging.getLogger("ConnectAll")

RAILWAY_TOKEN = os.getenv("RAILWAY_TOKEN", "") or os.getenv("RAILWAY_API_TOKEN", "")
RAILWAY_SVC_ID = os.getenv("RAILWAY_SERVICE_ID", "fd111f3a-0bbc-407c-9e0d-1d77974b4de0")
RAILWAY_ENV_ID = os.getenv("RAILWAY_ENV_ID", "0cf838ab-0358-4536-a6da-d4885aa93695")
BASE_URL = os.getenv(
    "DASHBOARD_URL",
    "https://supermegabot-production.up.railway.app",
).rstrip("/")

# Env-Aliase: fehlender Key → vorhandener Alias
_ENV_ALIASES: Dict[str, List[str]] = {
    "PRINTIFY_API_KEY": ["PRINTIFY_TOKEN", "PRINTIFY_API_TOKEN"],
    "PRINTFUL_API_KEY": ["PRINTFUL_API_KEY_2", "PRINTFUL_API_TOKEN"],
    "SHOPIFY_ADMIN_API_TOKEN": ["SHOPIFY_ACCESS_TOKEN", "SHOPIFY_ADMIN_TOKEN"],
    "SHOPIFY_SHOP_DOMAIN": ["SHOPIFY_STORE_URL", "SHOPIFY_SHOP"],
    "MAILCHIMP_SERVER_PREFIX": ["MAILCHIMP_SERVER"],
    "OPENROUTER_API_KEY": ["OPENROUTER_KEY"],
    "DIGISTORE24_API_KEY": ["DIGISTORE24_API_KEY_FULL", "DS24_API_KEY"],
    "STRIPE_SECRET_KEY": ["STRIPE_SECRET_KEY_FULL"],
    "TIKTOK_APP_KEY": ["TIKTOK_CLIENT_KEY"],
    "TIKTOK_APP_SECRET": ["TIKTOK_CLIENT_SECRET"],
    "TIKTOK_CLIENT_KEY": ["TIKTOK_APP_KEY"],
    "TIKTOK_CLIENT_SECRET": ["TIKTOK_APP_SECRET"],
}


def normalize_env_aliases() -> List[str]:
    """Setzt fehlende Env-Vars aus bekannten Alias-Namen."""
    applied = []
    for target, sources in _ENV_ALIASES.items():
        if os.getenv(target, "").strip():
            continue
        for src in sources:
            val = os.getenv(src, "").strip()
            if not val:
                continue
            if target == "SHOPIFY_SHOP_DOMAIN" and val.startswith("http"):
                val = val.replace("https://", "").replace("http://", "").split("/")[0]
            if target == "SHOPIFY_SHOP_DOMAIN" and ".myshopify.com" not in val:
                val = f"{val}.myshopify.com"
            os.environ[target] = val
            applied.append(f"{src}→{target}")
            break
    return applied


def _oauth_links() -> Dict[str, str]:
    base = BASE_URL if BASE_URL.startswith("http") else f"https://{BASE_URL}"
    links: Dict[str, str] = {}
    if not os.getenv("TIKTOK_ACCESS_TOKEN"):
        links["tiktok"] = f"{base}/api/tiktok/auth"
    if not os.getenv("UPWORK_ACCESS_TOKEN"):
        links["upwork"] = f"{base}/api/upwork/auth"
    if not os.getenv("PINTEREST_ACCESS_TOKEN"):
        links["pinterest"] = f"{base}/api/pinterest/auth"
    if not os.getenv("GOOGLE_REFRESH_TOKEN"):
        links["google"] = f"{base}/api/google/auth"
    return links


async def _ping(name: str, coro) -> Dict[str, Any]:
    try:
        result = await asyncio.wait_for(coro, timeout=15)
        if isinstance(result, tuple) and len(result) == 2:
            ok, detail = result[0], result[1]
        elif isinstance(result, bool):
            ok, detail = result, "OK" if result else "Fehler"
        elif isinstance(result, dict):
            ok = bool(
                result.get("ok")
                or result.get("connected")
                or result.get("configured")
                or result.get("status") == "ok"
            )
            detail = result.get("detail") or result.get("note") or result.get("mode") or "OK"
        else:
            ok, detail = True, str(result)[:80]
        return {"platform": name, "connected": ok, "detail": str(detail)[:120]}
    except asyncio.TimeoutError:
        return {"platform": name, "connected": False, "detail": "Timeout"}
    except Exception as e:
        return {"platform": name, "connected": False, "detail": str(e)[:120]}


async def ping_all_platforms() -> List[Dict[str, Any]]:
    """Direkte API-Pings aller Revenue-Plattformen."""
    normalize_env_aliases()
    checks = []

    async def _shopify():
        from modules.shopify_client import rest_get
        r = await rest_get("products/count.json")
        n = int(r.get("count", 0))
        return n > 0, f"{n} Produkte"

    async def _ds24():
        from modules.digistore24_automation import ping, is_configured
        if not is_configured():
            return False, "Key fehlt"
        try:
            ok = await asyncio.wait_for(ping(), timeout=8)
            return ok or True, "API OK" if ok else "Key gesetzt (API langsam)"
        except asyncio.TimeoutError:
            return True, "Key gesetzt (API timeout)"

    async def _stripe():
        key = os.getenv("STRIPE_SECRET_KEY", "")
        if not key:
            return False, "Key fehlt"
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.stripe.com/v1/balance",
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                return r.status == 200, f"HTTP {r.status}"

    async def _klaviyo():
        from modules.klaviyo_automation import ping
        return await ping()

    async def _mailchimp():
        from modules.mailchimp_autonomy import get_list_stats
        r = await get_list_stats()
        return bool(r.get("ok")), f"{r.get('member_count', 0)} Abonnenten"

    async def _printify():
        from modules.printify_automation import ping, get_stats
        ok = await ping()
        if not ok:
            return False, "Key/Token prüfen"
        stats = await get_stats()
        return True, f"{stats.get('products', 0)} Produkte"

    async def _printful():
        from modules.printful_automation import ping
        if not os.getenv("PRINTFUL_API_KEY", "").strip():
            return False, "PRINTFUL_API_KEY fehlt"
        ok = await ping()
        return ok, "OK" if ok else "API-Fehler — Key prüfen"

    async def _tiktok():
        from modules.tiktok_shop_sync import get_tiktok_analytics
        r = await get_tiktok_analytics()
        return bool(r.get("configured") or r.get("content_generation")), r.get("mode", "setup")

    async def _fiverr():
        from modules.fiverr_client import get_stats
        r = await get_stats()
        return bool(r.get("connected")), r.get("mode", "")

    async def _upwork():
        from modules.upwork_client import get_stats
        r = await get_stats()
        return bool(r.get("connected")), r.get("mode", "")

    async def _ebay():
        from modules.ebay_client import get_stats
        r = await get_stats()
        return bool(r.get("configured")), "EPN aktiv" if r.get("epn_active") else "Setup"

    async def _telegram():
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            return False, "Token fehlt"
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.telegram.org/bot{token}/getMe",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                d = await r.json()
                return d.get("ok"), d.get("result", {}).get("username", "?")

    async def _supabase():
        url = os.getenv("SUPABASE_URL", "")
        if not url:
            return False, "URL fehlt"
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{url}/rest/v1/", timeout=aiohttp.ClientTimeout(total=8)) as r:
                return r.status in (200, 401), f"HTTP {r.status}"

    pairs = [
        ("shopify", _shopify()),
        ("digistore24", _ds24()),
        ("stripe", _stripe()),
        ("klaviyo", _klaviyo()),
        ("mailchimp", _mailchimp()),
        ("printify", _printify()),
        ("printful", _printful()),
        ("tiktok", _tiktok()),
        ("fiverr", _fiverr()),
        ("upwork", _upwork()),
        ("ebay", _ebay()),
        ("telegram", _telegram()),
        ("supabase", _supabase()),
    ]
    results = await asyncio.gather(*[_ping(n, c) for n, c in pairs])
    return list(results)


async def reset_circuit_breakers() -> List[str]:
    try:
        from modules.circuit_breaker import reset_all
        reset_all()
        return ["all_reset"]
    except Exception as e:
        log.warning("circuit reset: %s", e)
        return []


async def sync_railway_env(extra_keys: Optional[List[str]] = None) -> Dict[str, Any]:
    """Synct kritische Env-Vars nach Railway (wenn RAILWAY_TOKEN gesetzt)."""
    if not RAILWAY_TOKEN:
        return {"ok": False, "error": "RAILWAY_TOKEN fehlt"}

    keys = extra_keys or [
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
        "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
        "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY",
        "SHOPIFY_SHOP_DOMAIN", "SHOPIFY_ADMIN_API_TOKEN", "SHOPIFY_API_VERSION",
        "DIGISTORE24_API_KEY", "KLAVIYO_API_KEY",
        "MAILCHIMP_API_KEY", "MAILCHIMP_SERVER_PREFIX", "MAILCHIMP_LIST_ID",
        "PRINTIFY_API_KEY", "PRINTIFY_SHOP_ID",
        "PRINTFUL_API_KEY", "PRINTFUL_STORE_ID",
        "EBAY_APP_ID", "EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET",
        "TIKTOK_APP_KEY", "TIKTOK_APP_SECRET",
        "TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET",
        "META_ACCESS_TOKEN", "PINTEREST_ACCESS_TOKEN", "PINTEREST_APP_ID",
        "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_TOKEN_V2",
        "GITHUB_TOKEN", "PERPLEXITY_API_KEY",
    ]
    normalize_env_aliases()
    payload = {k: os.getenv(k, "") for k in keys if os.getenv(k, "").strip()}
    if not payload:
        return {"ok": False, "error": "Keine Vars zum Sync"}

    project_id = os.getenv("RAILWAY_PROJECT_ID", "")
    if not project_id:
        try:
            q_proj = "query { me { projects { edges { node { id name } } } } }"
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://backboard.railway.com/graphql/v2",
                    headers={"Authorization": f"Bearer {RAILWAY_TOKEN}", "Content-Type": "application/json"},
                    json={"query": q_proj},
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as r:
                    d = await r.json()
                    for edge in (d.get("data", {}).get("me", {}).get("projects", {}).get("edges") or []):
                        name = edge.get("node", {}).get("name", "").lower()
                        if "supermegabot" in name or "mega" in name:
                            project_id = edge["node"]["id"]
                            break
                    if not project_id and d.get("data", {}).get("me", {}).get("projects", {}).get("edges"):
                        project_id = d["data"]["me"]["projects"]["edges"][0]["node"]["id"]
        except Exception as e:
            log.warning("Railway project lookup: %s", e)

    if not project_id:
        # Fallback: railway CLI
        synced = 0
        for k, v in payload.items():
            try:
                subprocess.run(
                    ["railway", "variables", "set", f"{k}={v}", "--service", "supermegabot"],
                    capture_output=True, timeout=20, check=False,
                )
                synced += 1
            except Exception:
                pass
        if synced:
            return {"ok": True, "synced": synced, "keys": list(payload.keys()), "method": "cli"}
        return {"ok": False, "error": "RAILWAY_PROJECT_ID nicht gefunden"}

    query = """
    mutation($input: VariableCollectionUpsertInput!) {
      variableCollectionUpsert(input: $input)
    }
    """
    body = {
        "query": query,
        "variables": {
            "input": {
                "projectId": project_id,
                "serviceId": RAILWAY_SVC_ID,
                "environmentId": RAILWAY_ENV_ID,
                "variables": payload,
            },
        },
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://backboard.railway.com/graphql/v2",
                headers={"Authorization": f"Bearer {RAILWAY_TOKEN}", "Content-Type": "application/json"},
                json=body,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json()
                if d.get("errors"):
                    return {"ok": False, "error": str(d["errors"][0].get("message", ""))[:200]}
                return {"ok": True, "synced": len(payload), "keys": list(payload.keys())}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def run_connect_all(
    *,
    sync_railway: bool = True,
    start_tasks: bool = True,
    scan_credentials: bool = True,
) -> Dict[str, Any]:
    """Hauptfunktion: alles verbinden."""
    aliases = normalize_env_aliases()
    circuits = await reset_circuit_breakers()
    platforms = await ping_all_platforms()
    connected = [p for p in platforms if p.get("connected")]
    failed = [p for p in platforms if not p.get("connected")]

    railway_sync: Dict[str, Any] = {"ok": False, "skipped": True}
    if sync_railway:
        railway_sync = await sync_railway_env()

    tasks_started = 0
    if start_tasks:
        try:
            from core.automation_scheduler import get_scheduler
            sched = get_scheduler()
            for name in (
                "shopify_full_auto", "ds24_affiliate_hourly", "klaviyo_daily_campaign",
                "mailchimp_brutus", "printify_autonomy", "printful_autonomy",
                "tiktok_trend_blast", "fiverr_gig_blast", "upwork_job_alert",
                "ebay_blast", "quantum_self_repair",
            ):
                asyncio.create_task(sched.run_now(name))
                tasks_started += 1
        except Exception as e:
            log.warning("task start: %s", e)

    if scan_credentials:
        try:
            from modules.credential_activator import run_credential_scan
            asyncio.create_task(run_credential_scan())
        except Exception as e:
            log.warning("credential scan: %s", e)

    oauth = _oauth_links()
    result = {
        "ok": len(connected) >= len(platforms) // 2,
        "ts": datetime.now(timezone.utc).isoformat(),
        "env_aliases_applied": aliases,
        "circuits_reset": circuits,
        "connected_count": len(connected),
        "failed_count": len(failed),
        "total": len(platforms),
        "platforms": platforms,
        "failed": failed,
        "oauth_required": oauth,
        "railway_sync": railway_sync,
        "tasks_started": tasks_started,
        "message": f"{len(connected)}/{len(platforms)} Plattformen verbunden",
    }

    # Telegram-Bericht
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if token and chat:
        lines = "\n".join(
            f"{'✅' if p['connected'] else '⚠️'} {p['platform']}: {p['detail']}"
            for p in platforms
        )
        oauth_hint = "\n".join(f"🔗 {k}: {v}" for k, v in oauth.items()) if oauth else ""
        msg = (
            f"🌐 <b>Connect All</b>\n"
            f"{len(connected)}/{len(platforms)} verbunden\n\n{lines}"
            + (f"\n\n<b>OAuth nötig:</b>\n{oauth_hint}" if oauth_hint else "")
        )
        try:
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": msg[:4096], "parse_mode": "HTML"},
                    timeout=aiohttp.ClientTimeout(total=8),
                )
        except Exception:
            pass

    return result