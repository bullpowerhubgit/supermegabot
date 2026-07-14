"""
BullPower MEGA Command Center v1.0 — Vollautonomes Self-Healing Revenue-System

Funktionen:
- Full API Health Check aller 15 Plattformen
- Self-Healing: Circuit-Breaker Reset, Key-Reload, Task-Restart
- Revenue Aggregation (DS24 + Shopify + Stripe)
- ROAS-basierte Ad-Skalierung (Meta)
- Product Curation (Good vs. Junk automatisch)
- Email-Bounce-Schutz (TaskGuard für alle Email-Tasks)
- Telegram-Alerting bei kritischen Fehlern
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

log = logging.getLogger("BullPowerMCC")

_BASE = Path(__file__).parent.parent
DATA_DIR = _BASE / "data"
STATE_FILE = DATA_DIR / "bullpower_mcc.json"

_raw_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "https://supermegabot-production.up.railway.app")
RAILWAY_URL = _raw_domain if _raw_domain.startswith("http") else f"https://{_raw_domain}"
# Self-calls (healing, scheduler checks) müssen intern via localhost gehen —
# Railway kann sich nicht selbst via Public-Domain aufrufen.
_INTERNAL_URL = f"http://localhost:{os.getenv('PORT', os.getenv('DASHBOARD_PORT', '8888'))}"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_state() -> Dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(s: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2, default=str), encoding="utf-8")


async def _tg(msg: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        async with aiohttp.ClientSession() as s:
            await s.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=aiohttp.ClientTimeout(total=8))
    except Exception:
        pass


async def _get(url: str, headers: Optional[Dict] = None, timeout: int = 8) -> Tuple[int, Any]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers or {}, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                try:
                    body = await r.json(content_type=None)
                except Exception:
                    body = await r.text()
                return r.status, body
    except Exception as e:
        return 0, str(e)


# ── Platform Health Checks ────────────────────────────────────────────────────

async def check_railway() -> Dict:
    # Immer intern prüfen — Railway kann sich nicht via public domain selbst aufrufen
    status, body = await _get(f"{_INTERNAL_URL}/health")
    ok = status == 200 and isinstance(body, dict) and body.get("status") == "ok"
    circuits = body.get("circuits_open", []) if isinstance(body, dict) else []
    uptime = body.get("uptime_seconds", 0) if isinstance(body, dict) else 0
    return {"platform": "railway", "ok": ok, "status": status,
            "circuits_open": circuits, "uptime_seconds": uptime}


async def check_shopify() -> Dict:
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    version = os.getenv("SHOPIFY_API_VERSION", "2026-04")
    if not domain or not token:
        return {"platform": "shopify", "ok": False, "error": "credentials missing"}
    status, body = await _get(
        f"https://{domain}/admin/api/{version}/shop.json",
        headers={"X-Shopify-Access-Token": token},
    )
    ok = status == 200 and isinstance(body, dict)
    name = body.get("shop", {}).get("name", "?") if ok else ""
    return {"platform": "shopify", "ok": ok, "shop": name, "status": status}


async def check_stripe() -> Dict:
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        return {"platform": "stripe", "ok": False, "error": "key missing"}
    status, body = await _get(
        "https://api.stripe.com/v1/balance",
        headers={"Authorization": f"Bearer {key}"},
    )
    ok = status == 200
    if ok and isinstance(body, dict):
        avail = body.get("available", [{}])
        eur = next((a["amount"] / 100 for a in avail if a.get("currency") == "eur"), 0)
        return {"platform": "stripe", "ok": True, "balance_eur": eur}
    return {"platform": "stripe", "ok": False, "status": status}


async def check_klaviyo() -> Dict:
    key = os.getenv("KLAVIYO_API_KEY", "")
    if not key:
        return {"platform": "klaviyo", "ok": False, "error": "key missing"}
    status, body = await _get(
        "https://a.klaviyo.com/api/lists/",
        headers={"Authorization": f"Klaviyo-API-Key {key}", "revision": "2024-10-15"},
    )
    ok = status == 200
    n_lists = len(body.get("data", [])) if ok and isinstance(body, dict) else 0
    return {"platform": "klaviyo", "ok": ok, "lists": n_lists, "status": status}


async def check_supabase() -> Dict:
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY", ""))
    if not url or not key:
        return {"platform": "supabase", "ok": False, "error": "credentials missing"}
    status, body = await _get(
        f"{url}/rest/v1/agent_memory?limit=1",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    ok = status == 200
    return {"platform": "supabase", "ok": ok, "status": status,
            "note": "PostgREST Schema-Cache ggf. eingefroren" if status == 404 else ""}


async def check_telegram() -> Dict:
    token = TELEGRAM_BOT_TOKEN
    if not token:
        return {"platform": "telegram", "ok": False, "error": "token missing"}
    status, body = await _get(f"https://api.telegram.org/bot{token}/getMe")
    ok = status == 200 and isinstance(body, dict) and body.get("ok")
    username = body.get("result", {}).get("username", "?") if ok else ""
    return {"platform": "telegram", "ok": ok, "username": username}


async def check_meta() -> Dict:
    token = os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC", os.getenv("META_PAGE_ACCESS_TOKEN", ""))
    page_id = os.getenv("FACEBOOK_PAGE_ID", "1016738738178786")
    if not token:
        return {"platform": "meta", "ok": False, "error": "token missing"}
    status, body = await _get(
        f"https://graph.facebook.com/v18.0/{page_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    ok = status == 200 and isinstance(body, dict)
    return {"platform": "meta", "ok": ok, "page": body.get("name", "?") if ok else "", "status": status}


async def check_youtube() -> Dict:
    key = os.getenv("YOUTUBE_API_KEY", "")
    ch = os.getenv("YOUTUBE_CHANNEL_ID", "")
    if not key or not ch:
        return {"platform": "youtube", "ok": False, "error": "credentials missing"}
    status, body = await _get(
        f"https://www.googleapis.com/youtube/v3/channels?part=snippet&id={ch}&key={key}"
    )
    ok = status == 200 and isinstance(body, dict) and bool(body.get("items"))
    title = body.get("items", [{}])[0].get("snippet", {}).get("title", "?") if ok else ""
    return {"platform": "youtube", "ok": ok, "channel": title}


async def run_platform_checks() -> Dict[str, Dict]:
    results = await asyncio.gather(
        check_railway(), check_shopify(), check_stripe(), check_klaviyo(),
        check_supabase(), check_telegram(), check_meta(), check_youtube(),
        return_exceptions=True,
    )
    checks: Dict[str, Dict] = {}
    for r in results:
        if isinstance(r, Exception):
            log.warning("Health check exception: %s", r)
            continue
        if isinstance(r, dict):
            checks[r.get("platform", "unknown")] = r
    return checks


# ── Self-Healing ──────────────────────────────────────────────────────────────

async def heal_circuit_breakers() -> Dict:
    """Reset alle offenen Circuit-Breakers via interne API."""
    status, body = await _get(f"{_INTERNAL_URL}/health")
    if not isinstance(body, dict):
        return {"ok": False, "error": "health check failed"}
    circuits = body.get("circuits_open", [])
    if not circuits:
        return {"ok": True, "reset": 0, "msg": "Keine offenen Circuits"}
    reset_count = 0
    async with aiohttp.ClientSession() as s:
        for cb in circuits:
            try:
                async with s.post(f"{_INTERNAL_URL}/api/circuit-breaker/reset", json={"name": cb}, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status in (200, 204):
                        reset_count += 1
            except Exception:
                pass
    return {"ok": True, "reset": reset_count, "circuits_were": circuits}


async def heal_scheduler_failures() -> Dict:
    """Prüft Scheduler-Tasks mit Fehler und versucht Restart."""
    status, body = await _get(f"{_INTERNAL_URL}/api/scheduler/status")
    if not isinstance(body, dict):
        return {"ok": False, "error": "scheduler unreachable"}
    tasks = body.get("tasks", {}).get("tasks", [])
    if isinstance(tasks, dict):
        tasks = list(tasks.values())
    failed = [t for t in tasks if isinstance(t, dict) and t.get("ok", 1) == 0 and t.get("total", 0) > 0]
    restarted = 0
    async with aiohttp.ClientSession() as s:
        for t in failed[:5]:
            name = t.get("name", "")
            if not name:
                continue
            try:
                async with s.post(f"{_INTERNAL_URL}/api/scheduler/run-task", json={"task": name}, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        restarted += 1
            except Exception:
                pass
    return {"ok": True, "failed_found": len(failed), "restarted": restarted}


async def run_self_healing() -> Dict:
    log.info("Self-Healing gestartet")
    cb_result = await heal_circuit_breakers()
    sched_result = await heal_scheduler_failures()
    result = {
        "ok": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "circuit_breakers": cb_result,
        "scheduler": sched_result,
    }
    if cb_result.get("reset", 0) > 0 or sched_result.get("restarted", 0) > 0:
        await _tg(
            f"🔧 <b>Self-Healing aktiv</b>\n"
            f"Circuit Breaker reset: {cb_result.get('reset', 0)}\n"
            f"Tasks neugestartet: {sched_result.get('restarted', 0)}"
        )
    return result


# ── Revenue Aggregation ───────────────────────────────────────────────────────

async def get_revenue_snapshot() -> Dict:
    # Intern aufrufen — Railway public domain kann nicht von Railway selbst erreicht werden
    try:
        status, body = await _get(f"{_INTERNAL_URL}/api/revenue/status")
        if status == 200 and isinstance(body, dict):
            return body
    except Exception:
        pass
    return {"month_eur": 0.0, "breakdown": {}}


# ── ROAS Optimizer ────────────────────────────────────────────────────────────

async def optimize_roas() -> Dict:
    """Meta Ads automatisch pausieren/skalieren basierend auf ROAS."""
    ad_account = os.getenv("META_AD_ACCOUNT_ID", "")
    token = os.getenv("META_ACCESS_TOKEN", "")
    if not ad_account or not token:
        return {"ok": False, "skipped": True, "reason": "META credentials fehlen"}

    try:
        from modules.roas_optimizer import run_roas_cycle
        r = await run_roas_cycle()
        if isinstance(r, dict):
            return {"ok": True, **r}
        return {"ok": True, "summary": str(r)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


# ── Product Curation ──────────────────────────────────────────────────────────

async def curate_products() -> Dict:
    """Aktiviert gute Produkte, archiviert Junk in Shopify."""
    try:
        from modules.shopify_daily_healer import run_daily_heal
        r = await run_daily_heal()
        return {"ok": True, "healed": r}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


# ── Master Run ────────────────────────────────────────────────────────────────

async def run_full_cycle() -> Dict:
    log.info("BullPower MCC — Full Cycle START")
    ts = datetime.now(timezone.utc).isoformat()

    # Parallel: Platform Checks + Revenue + Self-Healing
    checks, revenue, healing, roas = await asyncio.gather(
        run_platform_checks(),
        get_revenue_snapshot(),
        run_self_healing(),
        optimize_roas(),
        return_exceptions=True,
    )

    def _safe(r: Any) -> Any:
        return r if not isinstance(r, Exception) else {"ok": False, "error": str(r)[:80]}

    checks = _safe(checks)
    revenue = _safe(revenue)
    healing = _safe(healing)
    roas = _safe(roas)

    # Plattform-Fehler zählen
    failed_platforms = [p for p, v in checks.items() if not v.get("ok")]

    result = {
        "ok": True,
        "timestamp": ts,
        "platform_checks": checks,
        "failed_platforms": failed_platforms,
        "revenue": revenue,
        "self_healing": healing,
        "roas_optimizer": roas,
    }

    # Telegram-Report bei kritischen Problemen
    if failed_platforms:
        await _tg(
            f"⚠️ <b>BullPower MCC Alert</b>\n"
            f"Fehlerhafte Plattformen: {', '.join(failed_platforms)}\n"
            f"Revenue: €{revenue.get('revenue', {}).get('month_eur', 0) if isinstance(revenue, dict) else 0:.2f}"
        )

    state = _load_state()
    state["last_cycle"] = result
    state["cycles_total"] = int(state.get("cycles_total", 0)) + 1
    _save_state(state)

    log.info("BullPower MCC — Full Cycle DONE | Fehler: %s", failed_platforms)
    return result


async def get_shopify_metrics() -> Dict:
    """Holt Shopify Store-Metriken für das Dashboard."""
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    version = os.getenv("SHOPIFY_API_VERSION", "2026-04")
    if not domain or not token:
        return {"ok": False, "error": "credentials missing"}
    h = {"X-Shopify-Access-Token": token}
    base = f"https://{domain}/admin/api/{version}"
    try:
        async with aiohttp.ClientSession() as s:
            # Active + archived counts in parallel
            async def _count(params):
                async with s.get(f"{base}/products/count.json", headers=h, params=params,
                                 timeout=aiohttp.ClientTimeout(total=10)) as r:
                    return (await r.json(content_type=None)).get("count", 0) if r.status == 200 else 0

            active, archived = await asyncio.gather(_count({"status": "active"}), _count({"status": "archived"}))

            # Orders today
            from datetime import date
            today_str = date.today().isoformat() + "T00:00:00Z"
            async with s.get(f"{base}/orders/count.json", headers=h,
                             params={"created_at_min": today_str, "financial_status": "paid"},
                             timeout=aiohttp.ClientTimeout(total=10)) as r2:
                orders_today = (await r2.json(content_type=None)).get("count", 0) if r2.status == 200 else 0

        return {"ok": True, "active": active, "archived": archived,
                "total": active + archived, "orders_today": orders_today}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}


async def get_klaviyo_metrics() -> Dict:
    """Holt Klaviyo Subscriber-Zahlen."""
    key = os.getenv("KLAVIYO_API_KEY", "")
    list_id = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
    if not key:
        return {"ok": False, "error": "key missing"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://a.klaviyo.com/api/lists/{list_id}/",
                headers={"Authorization": f"Klaviyo-API-Key {key}", "revision": "2024-10-15"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json(content_type=None)
        if r.status != 200:
            return {"ok": False, "error": f"HTTP {r.status}"}
        attrs = d.get("data", {}).get("attributes", {})
        return {"ok": True, "list_id": list_id,
                "name": attrs.get("name", "?"),
                "subscriber_count": attrs.get("profile_count", 0)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}


async def get_bulk_activator_status() -> Dict:
    """Holt Status des Shopify Bulk Aktivators."""
    try:
        from modules.shopify_bulk_activator import get_status as ba_status  # type: ignore
        return await ba_status()
    except Exception as e:
        return {"ok": False, "error": str(e)[:60]}


async def get_title_germanizer_status() -> Dict:
    """Holt Status des Titel-Germanizers."""
    try:
        from modules.shopify_title_germanizer import get_status as tg_status  # type: ignore
        return await tg_status()
    except Exception as e:
        return {"ok": False, "error": str(e)[:60]}


async def get_collection_status() -> Dict:
    """Holt Smart Collection Statistiken."""
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    version = os.getenv("SHOPIFY_API_VERSION", "2026-04")
    if not domain or not token:
        return {"ok": False, "total": 0, "published": 0}
    try:
        import re
        async with aiohttp.ClientSession() as s:
            h = {"X-Shopify-Access-Token": token}
            base = f"https://{domain}/admin/api/{version}"
            all_sc = []
            page_info = None
            while True:
                params = {"limit": 250}
                if page_info:
                    params["page_info"] = page_info
                async with s.get(f"{base}/smart_collections.json", headers=h, params=params,
                                 timeout=aiohttp.ClientTimeout(total=15)) as r:
                    sc = (await r.json(content_type=None)).get("smart_collections", [])
                    all_sc.extend(sc)
                    link = r.headers.get("Link", "")
                    if 'rel="next"' in link:
                        m = re.search(r'page_info=([^>&"]+).*?rel="next"', link)
                        page_info = m.group(1) if m else None
                    else:
                        break
                await asyncio.sleep(0.5)
        published = sum(1 for c in all_sc if c.get("published_at"))
        return {"ok": True, "total": len(all_sc), "published": published,
                "unpublished": len(all_sc) - published}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80], "total": 0, "published": 0}


async def get_full_dashboard_data() -> Dict:
    """Vollständiges Dashboard-Daten-Paket für das MCC HTML-Dashboard."""
    ts = datetime.now(timezone.utc).isoformat()
    # Alle Checks parallel
    platforms, shopify_m, klaviyo_m, bulk_act, title_ger, collections = await asyncio.gather(
        run_platform_checks(),
        get_shopify_metrics(),
        get_klaviyo_metrics(),
        get_bulk_activator_status(),
        get_title_germanizer_status(),
        get_collection_status(),
        return_exceptions=True,
    )
    def _s(r): return r if not isinstance(r, Exception) else {"ok": False, "error": str(r)[:60]}
    platforms = _s(platforms)
    shopify_m = _s(shopify_m)
    klaviyo_m = _s(klaviyo_m)
    bulk_act  = _s(bulk_act)
    title_ger = _s(title_ger)
    collections = _s(collections)

    failed_platforms = [p for p, v in (platforms.items() if isinstance(platforms, dict) else {}.items()) if not v.get("ok")]

    return {
        "ok": True,
        "timestamp": ts,
        "platforms": platforms,
        "failed_platforms": failed_platforms,
        "shopify": shopify_m,
        "klaviyo": klaviyo_m,
        "bulk_activator": bulk_act,
        "title_germanizer": title_ger,
        "collections": collections,
    }


async def get_status() -> Dict:
    state = _load_state()
    return {
        "ok": True,
        "module": "BullPower MEGA Command Center",
        "version": "2.0",
        "cycles_total": state.get("cycles_total", 0),
        "last_cycle": state.get("last_cycle"),
        "railway_url": RAILWAY_URL,
    }


async def run_full_cycle_str() -> str:
    r = await run_full_cycle()
    rev = r.get("revenue", {})
    if isinstance(rev, dict):
        rev = rev.get("revenue", rev)
    eur = rev.get("month_eur", 0) if isinstance(rev, dict) else 0
    failed = r.get("failed_platforms", [])
    healed = r.get("self_healing", {}).get("circuit_breakers", {}).get("reset", 0)
    return (
        f"MCC: Revenue €{eur:.2f} | "
        f"Plattform-Fehler: {len(failed)} ({','.join(failed) or 'keine'}) | "
        f"Geheilt: {healed} CB"
    )
