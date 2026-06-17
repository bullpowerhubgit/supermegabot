"""
Hermes API routes — /api/hermes/*
Job queue + event stream via Supabase.
"""
import os
import logging

import aiohttp
from aiohttp import web

log = logging.getLogger("HermesRoutes")

_SB_URL = ""
_SB_KEY = ""
_SB_HEADERS: dict = {}


def _init_sb():
    global _SB_URL, _SB_KEY, _SB_HEADERS
    _SB_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
    _SB_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
    _SB_HEADERS = {
        "apikey": _SB_KEY,
        "Authorization": f"Bearer {_SB_KEY}",
        "Content-Type": "application/json",
        "Accept-Profile": "public",
        "Content-Profile": "public",
    }


async def _sb_get(path: str, params: str = "") -> list:
    _init_sb()
    if not _SB_URL or not _SB_KEY:
        return []
    url = f"{_SB_URL}/rest/v1/{path}"
    if params:
        url += f"?{params}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=_SB_HEADERS,
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                return await r.json()
    except Exception as exc:
        log.warning("hermes_routes sb_get error: %s", exc)
        return []


async def _sb_post(path: str, data: dict) -> dict:
    _init_sb()
    if not _SB_URL or not _SB_KEY:
        return {"error": "no supabase"}
    headers = {**_SB_HEADERS, "Prefer": "return=representation"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{_SB_URL}/rest/v1/{path}",
                json=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                result = await r.json()
                if isinstance(result, list) and result:
                    return result[0]
                return result
    except Exception as exc:
        log.warning("hermes_routes sb_post error: %s", exc)
        return {"error": str(exc)}


async def handle_hermes_jobs(req: web.Request) -> web.Response:
    """GET /api/hermes/jobs?status=pending&service=supermegabot&limit=50"""
    status = req.rel_url.query.get("status", "")
    service = req.rel_url.query.get("service", "")
    limit = req.rel_url.query.get("limit", "50")

    filters = [f"order=created_at.desc", f"limit={limit}"]
    if status:
        filters.append(f"status=eq.{status}")
    if service:
        filters.append(f"service=eq.{service}")

    data = await _sb_get("hermes_jobs", "&".join(filters))
    return web.json_response({"ok": True, "count": len(data), "jobs": data})


async def handle_hermes_events(req: web.Request) -> web.Response:
    """GET /api/hermes/events?service=supermegabot&channel=general&limit=50"""
    service = req.rel_url.query.get("service", "")
    channel = req.rel_url.query.get("channel", "")
    limit = req.rel_url.query.get("limit", "50")

    filters = [f"order=created_at.desc", f"limit={limit}"]
    if service:
        filters.append(f"service=eq.{service}")
    if channel:
        filters.append(f"channel=eq.{channel}")

    data = await _sb_get("hermes_events", "&".join(filters))
    return web.json_response({"ok": True, "count": len(data), "events": data})


async def handle_hermes_enqueue(req: web.Request) -> web.Response:
    """POST /api/hermes/enqueue — enqueue job in Supabase + local Hermes queue"""
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

    job_name = (body.get("name") or body.get("job_name") or "").strip()
    if not job_name:
        return web.json_response({"ok": False, "error": "name required"}, status=400)

    payload = body.get("payload") or {}
    priority = int(body.get("priority", 5))
    service = body.get("service", "supermegabot")

    # Enqueue in Supabase for cross-service visibility
    from core.job_queue import enqueue_remote
    remote_id = await enqueue_remote(job_name, payload, service, priority)

    # Also enqueue locally if service matches
    local_id = None
    if service == "supermegabot":
        from core.job_queue import HermesQueue
        local_id = await HermesQueue.get().enqueue(job_name, payload, priority)

    return web.json_response({
        "ok": True,
        "job_name": job_name,
        "remote_id": remote_id,
        "local_id": local_id,
        "priority": priority,
    })


async def handle_hermes_notify(req: web.Request) -> web.Response:
    """POST /api/hermes/notify — push event to Slack/Telegram + Supabase"""
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

    message = (body.get("message") or "").strip()
    if not message:
        return web.json_response({"ok": False, "error": "message required"}, status=400)

    service = body.get("service", "supermegabot")
    event_type = body.get("event_type", "manual")
    channel = body.get("channel", "general")
    metadata = body.get("metadata") or {}

    from modules.slack_client import push_event
    delivered = await push_event(service, event_type, message, channel, metadata)

    return web.json_response({
        "ok": True,
        "delivered": delivered,
        "service": service,
        "event_type": event_type,
        "channel": channel,
    })


async def handle_hermes_stats(req: web.Request) -> web.Response:
    """GET /api/hermes/stats — queue stats + Supabase counts"""
    from core.job_queue import HermesQueue
    local_stats = HermesQueue.get().stats()

    # Counts per status from Supabase
    counts: dict = {}
    for status in ("pending", "running", "done", "failed", "retry"):
        rows = await _sb_get("hermes_jobs", f"status=eq.{status}&select=id")
        counts[status] = len(rows)

    return web.json_response({
        "ok": True,
        "local_queue": local_stats,
        "supabase_jobs": counts,
    })
