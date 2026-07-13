"""
Persistente Task-Deduplication via Supabase.
Verhindert dass Email-Tasks nach Railway-Restarts erneut feuern.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta

import aiohttp

log = logging.getLogger("TaskGuard")

_SB_URL: str = os.getenv("SUPABASE_URL", "")
_SB_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY", ""))


def _headers() -> dict:
    return {
        "apikey": _SB_KEY,
        "Authorization": f"Bearer {_SB_KEY}",
        "Content-Type": "application/json",
    }


async def task_ran_recently(task_name: str, min_interval_hours: float) -> bool:
    """True wenn der Task innerhalb der letzten min_interval_hours lief."""
    if not _SB_URL or not _SB_KEY:
        return False
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=min_interval_hours)).isoformat()
    try:
        async with aiohttp.ClientSession(headers=_headers()) as s:
            async with s.get(
                f"{_SB_URL}/rest/v1/agent_memory",
                params={
                    "agent_role": "eq.task_guard",
                    "type": f"eq.{task_name}",
                    "created_at": f"gt.{cutoff}",
                    "select": "created_at",
                    "limit": "1",
                },
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    if data:
                        log.info("TaskGuard: %s lief vor <%.0fh — überspringe", task_name, min_interval_hours)
                        return True
    except Exception as exc:
        log.warning("TaskGuard.check Fehler: %s", exc)
    return False


async def record_task_run(task_name: str) -> None:
    """Speichert aktuellen Zeitstempel als letzten Task-Lauf in Supabase."""
    if not _SB_URL or not _SB_KEY:
        return
    now = datetime.now(timezone.utc)
    payload = {
        "agent_role": "task_guard",
        "type": task_name,
        "content": now.isoformat(),
        "context": {"task_name": task_name, "ran_at": now.isoformat()},
        "confidence": 100,
        "expires_at": (now + timedelta(hours=48)).isoformat(),
    }
    try:
        async with aiohttp.ClientSession(headers=_headers()) as s:
            await s.post(f"{_SB_URL}/rest/v1/agent_memory", json=payload)
        log.info("TaskGuard: %s — Lauf gespeichert", task_name)
    except Exception as exc:
        log.warning("TaskGuard.record Fehler: %s", exc)
