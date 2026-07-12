#!/usr/bin/env python3
"""
Hermes Job Queue — zentrales asynchrones Job-System für SuperMegaBot.

- Priority-Queue (asyncio.PriorityQueue)
- Retry mit exponentiellem Backoff (max 3 Versuche)
- Persistent via SQLite (jobs überleben Neustarts)
- Telegram-Alert bei dauerhaftem Fehler
- Jobs werden von allen Modulen via enqueue() dispatcht
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, Optional

log = logging.getLogger("HermesQueue")

DB_PATH = Path(os.getenv("DATA_DIR", str(Path.home() / "supermegabot" / "data"))) / "hermes.db"
MAX_RETRIES = 3
BASE_BACKOFF = 5   # seconds


@dataclass(order=True)
class Job:
    priority: int                           # lower = higher priority (0=critical, 5=normal, 9=low)
    name: str = field(compare=False)
    payload: Dict[str, Any] = field(compare=False, default_factory=dict)
    retries: int = field(compare=False, default=0)
    created_at: float = field(compare=False, default_factory=time.time)
    job_id: str = field(compare=False, default="")

    def __post_init__(self):
        if not self.job_id:
            import uuid
            self.job_id = str(uuid.uuid4())[:8]


# ── Registry: Job-Handler per Name ───────────────────────────────────────────
_registry: Dict[str, Callable] = {}


def job_handler(name: str):
    """Decorator: @job_handler('send_telegram') async def fn(payload): ..."""
    def decorator(fn: Callable):
        _registry[name] = fn
        return fn
    return decorator


# ── Persistence ───────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
        job_id TEXT PRIMARY KEY,
        name TEXT, priority INTEGER, payload TEXT,
        retries INTEGER, created_at REAL, status TEXT DEFAULT 'pending'
    )""")
    conn.commit()
    return conn


def _persist_job(job: Job, status: str = "pending"):
    try:
        with _db() as conn:
            conn.execute("""INSERT OR REPLACE INTO jobs
                (job_id, name, priority, payload, retries, created_at, status)
                VALUES (?,?,?,?,?,?,?)""",
                (job.job_id, job.name, job.priority,
                 json.dumps(job.payload), job.retries, job.created_at, status))
    except Exception as e:
        log.warning("Hermes DB write failed: %s", e)


def _mark_done(job_id: str, status: str = "done"):
    try:
        with _db() as conn:
            conn.execute("UPDATE jobs SET status=? WHERE job_id=?", (status, job_id))
    except Exception as e:
        log.debug("_mark_done failed for %s: %s", job_id, e)


def _load_pending() -> list[Job]:
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT name,priority,payload,retries,created_at,job_id FROM jobs WHERE status='pending'"
            ).fetchall()
        jobs = []
        for name, prio, payload, retries, created_at, job_id in rows:
            jobs.append(Job(priority=prio, name=name,
                            payload=json.loads(payload or "{}"),
                            retries=retries, created_at=created_at, job_id=job_id))
        return jobs
    except Exception as e:
        log.debug("_load_pending failed: %s", e)
        return []


# ── Queue Singleton ───────────────────────────────────────────────────────────

class HermesQueue:
    _instance: Optional["HermesQueue"] = None

    def __init__(self):
        self._q: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._running = False
        self._workers: list[asyncio.Task] = []

    @classmethod
    def get(cls) -> "HermesQueue":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def enqueue(self, name: str, payload: dict | None = None,
                      priority: int = 5) -> str:
        job = Job(priority=priority, name=name, payload=payload or {})
        _persist_job(job)
        await self._q.put(job)
        log.debug("Hermes enqueue: %s [%s] prio=%d", name, job.job_id, priority)
        return job.job_id

    async def start(self, workers: int = 3):
        if self._running:
            return
        self._running = True
        # Recover pending jobs from DB
        for job in _load_pending():
            await self._q.put(job)
        for i in range(workers):
            t = asyncio.create_task(self._worker(f"worker-{i}"))
            self._workers.append(t)
        log.info("Hermes started with %d workers", workers)

    async def stop(self):
        self._running = False
        for t in self._workers:
            t.cancel()

    async def _worker(self, name: str):
        while self._running:
            try:
                job: Job = await asyncio.wait_for(self._q.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            await self._execute(job)

    async def _execute(self, job: Job):
        handler = _registry.get(job.name)
        if not handler:
            log.warning("Hermes: no handler for '%s'", job.name)
            _mark_done(job.job_id, "no_handler")
            return

        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(job.payload)
            else:
                handler(job.payload)
            _mark_done(job.job_id, "done")
            log.debug("Hermes done: %s [%s]", job.name, job.job_id)

        except Exception as exc:
            job.retries += 1
            if job.retries <= MAX_RETRIES:
                backoff = BASE_BACKOFF * (2 ** (job.retries - 1))
                log.warning("Hermes retry %d/%d for '%s' in %ds: %s",
                            job.retries, MAX_RETRIES, job.name, backoff, exc)
                _persist_job(job, "pending")
                await asyncio.sleep(backoff)
                await self._q.put(job)
            else:
                log.error("Hermes FAILED permanently: %s [%s] — %s",
                          job.name, job.job_id, exc)
                _mark_done(job.job_id, "failed")
                try:
                    from modules.notify_hub import notify_error
                    notify_error("HermesQueue", f"Job '{job.name}' permanent failed",
                                 traceback.format_exc()[-500:])
                except Exception:
                    pass

    def stats(self) -> dict:
        return {"queue_size": self._q.qsize(), "running": self._running,
                "workers": len(self._workers)}


# ── Remote Enqueue (Supabase cross-service visibility) ────────────────────────

async def enqueue_remote(
    job_name: str,
    payload: dict,
    service: str = "supermegabot",
    priority: int = 5,
) -> str | None:
    """Push a job record to Supabase hermes_jobs for cross-service visibility."""
    import aiohttp as _aio
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        log.warning("enqueue_remote: no Supabase credentials")
        return None
    row = {
        "service": service,
        "job_name": job_name,
        "payload": payload,
        "priority": priority,
        "status": "pending",
    }
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept-Profile": "public",
        "Content-Profile": "public",
        "Prefer": "return=representation",
    }
    try:
        async with _aio.ClientSession() as s:
            async with s.post(
                f"{url}/rest/v1/hermes_jobs",
                json=row,
                headers=headers,
                timeout=_aio.ClientTimeout(total=8),
            ) as r:
                data = await r.json()
                if isinstance(data, list) and data:
                    job_id = data[0].get("id")
                    log.debug("enqueue_remote: %s → %s", job_name, job_id)
                    return job_id
    except Exception as exc:
        log.warning("enqueue_remote failed: %s", exc)
    return None


# ── Convenience shortcut ──────────────────────────────────────────────────────

async def enqueue(name: str, payload: dict | None = None, priority: int = 5) -> str:
    return await HermesQueue.get().enqueue(name, payload, priority)


# ── Built-in handlers ─────────────────────────────────────────────────────────

@job_handler("notify")
async def _handle_notify(payload: dict):
    from modules.notify_hub import notify
    notify(payload.get("title", ""), payload.get("body", ""), payload.get("type", "info"))


@job_handler("shopify_sync")
async def _handle_shopify_sync(payload: dict):
    from modules.shopify_client import test_connection
    await test_connection()


@job_handler("telegram_send")
async def _handle_telegram_send(payload: dict):
    from modules.notify_hub import _tg_send
    _tg_send(payload.get("text", ""))
