#!/usr/bin/env python3
"""Multi-Service Bridge — verbindet alle Railway-Services für Cross-Service-Automation."""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger("MultiServiceBridge")

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

_BRIDGE_STATUS_FILE = DATA_DIR / "bridge_status.json"

# ── Service Registry ─────────────────────────────────────────────────────────

_SERVICE_URLS: Dict[str, str] = {
    "supermegabot": "https://supermegabot-production.up.railway.app",
    "adposter":     "https://adposter-engine-production.up.railway.app",
    "icomeauto":    "https://icomeauto-production-e4e5.up.railway.app",
    "steuercockpit":"https://steuercockpit-production-44c9.up.railway.app",
}

# Cached status (updated by run_bridge_cycle)
_last_status: Dict = {}


# ── Telegram helper ──────────────────────────────────────────────────────────

async def _tg_alert(msg: str) -> None:
    """Sendet System-Alert an Rudolf's privaten Telegram-Chat."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        import aiohttp
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            await s.post(url, json={
                "chat_id": chat,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
    except Exception as e:
        log.debug(f"TG alert failed: {e}")


# ── Core Functions ───────────────────────────────────────────────────────────

async def ping_all_services() -> Dict:
    """
    Pingt alle 4 Services /health.
    Gibt {"ok": n_ok, "services": {"name": {"ok": bool, "uptime": ..., "latency_ms": ...}}} zurück.
    """
    import aiohttp

    results: Dict[str, Dict] = {}

    async def _ping_one(name: str, base_url: str) -> None:
        start = time.monotonic()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get(f"{base_url}/health") as r:
                    latency_ms = int((time.monotonic() - start) * 1000)
                    if r.status == 200:
                        try:
                            data = await r.json(content_type=None)
                        except Exception:
                            data = {}
                        results[name] = {
                            "ok": True,
                            "latency_ms": latency_ms,
                            "uptime": data.get("uptime", data.get("uptime_seconds", None)),
                            "status": data.get("status", "ok"),
                        }
                    else:
                        results[name] = {
                            "ok": False,
                            "latency_ms": latency_ms,
                            "error": f"HTTP {r.status}",
                        }
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            results[name] = {
                "ok": False,
                "latency_ms": latency_ms,
                "error": str(e)[:120],
            }

    await asyncio.gather(*[_ping_one(n, u) for n, u in _SERVICE_URLS.items()])

    n_ok = sum(1 for v in results.values() if v.get("ok"))
    return {"ok": n_ok, "total": len(_SERVICE_URLS), "services": results}


async def trigger_on_service(service: str, command: str, params: Optional[Dict] = None) -> Dict:
    """
    Sendet POST /api/bot/execute an einen anderen Service.
    service: einer von "adposter", "icomeauto", "steuercockpit" (auch "supermegabot" möglich).
    Gibt Response-Dict zurück oder {"ok": False, "error": ...}.
    """
    import aiohttp

    if params is None:
        params = {}

    base_url = _SERVICE_URLS.get(service.lower())
    if not base_url:
        return {"ok": False, "error": f"Unbekannter Service: {service}. Erlaubt: {list(_SERVICE_URLS.keys())}"}

    payload = {"command": command, "params": params}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(f"{base_url}/api/bot/execute", json=payload) as r:
                try:
                    data = await r.json(content_type=None)
                except Exception:
                    text = await r.text()
                    data = {"raw": text[:500]}
                data["_http_status"] = r.status
                data["_service"] = service
                data["ok"] = r.status < 400
                return data
    except Exception as e:
        log.warning(f"trigger_on_service({service}, {command}): {e}")
        return {"ok": False, "error": str(e)[:200], "service": service, "command": command}


async def broadcast_command(command: str, params: Optional[Dict] = None) -> Dict:
    """
    Sendet denselben Command an alle Services parallel.
    Gibt {"results": {"service": result}} zurück.
    """
    if params is None:
        params = {}

    tasks = {
        name: asyncio.create_task(trigger_on_service(name, command, params))
        for name in _SERVICE_URLS
    }
    await asyncio.gather(*tasks.values(), return_exceptions=True)

    results: Dict[str, Dict] = {}
    for name, task in tasks.items():
        try:
            results[name] = task.result() if not task.exception() else {"ok": False, "error": str(task.exception())}
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}

    n_ok = sum(1 for v in results.values() if v.get("ok"))
    return {
        "command": command,
        "ok_count": n_ok,
        "total": len(_SERVICE_URLS),
        "results": results,
    }


async def _get_revenue_snapshot(name: str, base_url: str) -> Dict:
    """Holt Revenue-Snapshot von einem Service (GET /api/revenue oder /api/stats)."""
    import aiohttp

    for endpoint in ["/api/revenue", "/api/stats", "/api/revenue/snapshot"]:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get(f"{base_url}{endpoint}") as r:
                    if r.status == 200:
                        try:
                            data = await r.json(content_type=None)
                            return {"ok": True, "endpoint": endpoint, "data": data}
                        except Exception:
                            pass
        except Exception:
            pass

    return {"ok": False, "error": "no revenue endpoint available"}


async def run_bridge_cycle() -> Dict:
    """
    Haupt-Zyklus:
    1. Ping alle Services
    2. Wenn Service down → Telegram Alert
    3. Revenue-Snapshot von jedem Service holen
    4. Status in data/bridge_status.json speichern
    5. Gibt {"ok": True, "services_up": n, "services_down": n, "total_revenue": ...} zurück
    """
    global _last_status

    # 1. Ping
    ping_result = await ping_all_services()
    services    = ping_result["services"]
    n_ok        = ping_result["ok"]
    n_down      = ping_result["total"] - n_ok

    # 2. Alert für down services
    down_services = [name for name, info in services.items() if not info.get("ok")]
    if down_services:
        names_str = ", ".join(down_services)
        await _tg_alert(
            f"🔴 <b>Multi-Service Bridge Alert</b>\n"
            f"Service(s) DOWN: <code>{names_str}</code>\n"
            f"Zeit: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
        log.warning(f"Services DOWN: {down_services}")

    # 3. Revenue snapshots (nur für live services)
    revenue_snapshots: Dict[str, Dict] = {}
    up_services = [name for name, info in services.items() if info.get("ok")]

    if up_services:
        snap_tasks = {
            name: asyncio.create_task(_get_revenue_snapshot(name, _SERVICE_URLS[name]))
            for name in up_services
        }
        await asyncio.gather(*snap_tasks.values(), return_exceptions=True)
        for name, task in snap_tasks.items():
            try:
                revenue_snapshots[name] = task.result() if not task.exception() else {"ok": False}
            except Exception:
                revenue_snapshots[name] = {"ok": False}

    # 4. Gesamtrevenue zusammenrechnen (best-effort)
    total_revenue: float = 0.0
    for snap in revenue_snapshots.values():
        if snap.get("ok"):
            data = snap.get("data", {})
            for key in ("total", "total_revenue", "revenue", "amount", "stripe_revenue"):
                if isinstance(data.get(key), (int, float)):
                    total_revenue += float(data[key])
                    break

    # 5. Status persistieren
    status = {
        "last_ping": datetime.now(timezone.utc).isoformat(),
        "services_up": n_ok,
        "services_down": n_down,
        "services": services,
        "revenue_snapshots": revenue_snapshots,
        "total_revenue": round(total_revenue, 2),
    }
    _last_status = status

    try:
        _BRIDGE_STATUS_FILE.write_text(json.dumps(status, indent=2, ensure_ascii=False))
    except Exception as e:
        log.warning(f"bridge_status.json write error: {e}")

    log.info(
        f"BridgeCycle: up={n_ok}/{ping_result['total']} "
        f"down={n_down} revenue=€{total_revenue:.2f}"
    )

    return {
        "ok": True,
        "services_up": n_ok,
        "services_down": n_down,
        "total_revenue": round(total_revenue, 2),
        "down_services": down_services,
    }


async def get_bridge_status() -> Dict:
    """
    Gibt aktuellen Status zurück (letzter Ping, Services up/down).
    Liest aus data/bridge_status.json falls _last_status leer ist.
    """
    global _last_status

    if not _last_status and _BRIDGE_STATUS_FILE.exists():
        try:
            _last_status = json.loads(_BRIDGE_STATUS_FILE.read_text())
        except Exception:
            pass

    if not _last_status:
        return {
            "ok": False,
            "error": "Kein Status vorhanden — run_bridge_cycle() noch nicht ausgeführt.",
        }

    return {
        "ok": True,
        **_last_status,
    }
