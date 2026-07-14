"""
Agent Coordinator — verhindert doppelte Arbeit zwischen Agenten
===============================================================
Jeder Agent meldet sich vor Start an und nach Ende ab.
Läuft ein Task bereits → anderen Agenten sofort mit Ergebnis versorgen.

Nutzung:
    async with coordinator.run("traffic_blast", ttl=300) as ctx:
        if ctx.already_running:
            return ctx.last_result  # Ergebnis vom bereits laufenden Agenten nutzen
        result = await do_the_work()
        ctx.result = result

Oder als Dekorator:
    @coordinator.task("email_batch", ttl=3600)
    async def send_emails():
        ...
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("AgentCoordinator")

_DB_PATH = Path(__file__).parent.parent / "data" / "agent_coordinator.db"

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


# ─── DB ───────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS running_tasks (
            task_key   TEXT PRIMARY KEY,
            agent_name TEXT NOT NULL,
            started_at REAL NOT NULL,
            ttl        REAL NOT NULL DEFAULT 300,
            meta       TEXT DEFAULT '{}'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_results (
            task_key    TEXT NOT NULL,
            finished_at REAL NOT NULL,
            duration    REAL,
            success     INTEGER DEFAULT 1,
            result_json TEXT DEFAULT '{}',
            agent_name  TEXT,
            PRIMARY KEY (task_key, finished_at)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            from_agent  TEXT NOT NULL,
            to_agent    TEXT DEFAULT 'all',
            msg_type    TEXT NOT NULL,
            payload     TEXT DEFAULT '{}',
            created_at  REAL NOT NULL,
            read_at     REAL
        )
    """)
    conn.commit()
    # Abgelaufene Locks bereinigen
    conn.execute("DELETE FROM running_tasks WHERE started_at + ttl < ?", (time.time(),))
    conn.commit()
    return conn


# ─── Öffentliche API ──────────────────────────────────────────────────────────

def is_running(task_key: str) -> bool:
    """True wenn ein Task mit diesem Key gerade läuft."""
    with _db() as conn:
        row = conn.execute(
            "SELECT started_at, ttl FROM running_tasks WHERE task_key=?", (task_key,)
        ).fetchone()
        if not row:
            return False
        return (row["started_at"] + row["ttl"]) > time.time()


def claim(task_key: str, agent_name: str, ttl: float = 300, meta: dict | None = None) -> bool:
    """
    Versucht den Task zu beanspruchen.
    Gibt True zurück wenn erfolgreich, False wenn bereits belegt.
    """
    now = time.time()
    try:
        with _db() as conn:
            # Abgelaufene Locks für diesen Key zuerst löschen
            conn.execute(
                "DELETE FROM running_tasks WHERE task_key=? AND started_at + ttl < ?",
                (task_key, now)
            )
            conn.execute(
                """INSERT OR IGNORE INTO running_tasks (task_key, agent_name, started_at, ttl, meta)
                   VALUES (?, ?, ?, ?, ?)""",
                (task_key, agent_name, now, ttl, json.dumps(meta or {}))
            )
            conn.commit()
            row = conn.execute(
                "SELECT agent_name FROM running_tasks WHERE task_key=?", (task_key,)
            ).fetchone()
            return row and row["agent_name"] == agent_name
    except Exception as e:
        log.warning("claim() Fehler: %s", e)
        return True  # Im Zweifel erlauben


def release(task_key: str, agent_name: str, result: Any = None, success: bool = True) -> None:
    """Task freigeben und Ergebnis speichern."""
    now = time.time()
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT started_at FROM running_tasks WHERE task_key=? AND agent_name=?",
                (task_key, agent_name)
            ).fetchone()
            duration = now - row["started_at"] if row else 0
            conn.execute("DELETE FROM running_tasks WHERE task_key=? AND agent_name=?",
                         (task_key, agent_name))
            conn.execute(
                """INSERT INTO task_results (task_key, finished_at, duration, success, result_json, agent_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task_key, now, duration, int(success),
                 json.dumps(result if result is not None else {}), agent_name)
            )
            conn.commit()
    except Exception as e:
        log.warning("release() Fehler: %s", e)


def get_last_result(task_key: str, max_age: float = 3600) -> dict | None:
    """Letztes Ergebnis eines Tasks (falls nicht älter als max_age Sekunden)."""
    try:
        with _db() as conn:
            row = conn.execute(
                """SELECT result_json, finished_at, agent_name FROM task_results
                   WHERE task_key=? AND finished_at > ? AND success=1
                   ORDER BY finished_at DESC LIMIT 1""",
                (task_key, time.time() - max_age)
            ).fetchone()
            if row:
                return {
                    "result": json.loads(row["result_json"]),
                    "finished_at": row["finished_at"],
                    "agent": row["agent_name"],
                }
    except Exception as e:
        log.warning("get_last_result() Fehler: %s", e)
    return None


def send_message(from_agent: str, payload: dict, to_agent: str = "all", msg_type: str = "info") -> None:
    """Agenten-zu-Agenten Nachricht senden."""
    try:
        with _db() as conn:
            conn.execute(
                """INSERT INTO agent_messages (from_agent, to_agent, msg_type, payload, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (from_agent, to_agent, msg_type, json.dumps(payload), time.time())
            )
            conn.commit()
    except Exception as e:
        log.warning("send_message() Fehler: %s", e)


def read_messages(agent_name: str, unread_only: bool = True) -> list[dict]:
    """Nachrichten für einen Agenten lesen."""
    try:
        with _db() as conn:
            where = "WHERE (to_agent=? OR to_agent='all')"
            if unread_only:
                where += " AND read_at IS NULL"
            rows = conn.execute(
                f"SELECT * FROM agent_messages {where} ORDER BY created_at DESC LIMIT 50",
                (agent_name,)
            ).fetchall()
            ids = [r["id"] for r in rows]
            if ids and unread_only:
                conn.execute(
                    f"UPDATE agent_messages SET read_at=? WHERE id IN ({','.join('?'*len(ids))})",
                    [time.time()] + ids
                )
                conn.commit()
            return [dict(r) for r in rows]
    except Exception as e:
        log.warning("read_messages() Fehler: %s", e)
        return []


def get_status() -> dict:
    """Vollständiger Status aller laufenden Agenten + letzte 10 Ergebnisse."""
    now = time.time()
    try:
        with _db() as conn:
            running = conn.execute(
                "SELECT * FROM running_tasks WHERE started_at + ttl > ?", (now,)
            ).fetchall()
            recent = conn.execute(
                """SELECT task_key, agent_name, finished_at, duration, success
                   FROM task_results ORDER BY finished_at DESC LIMIT 10"""
            ).fetchall()
            return {
                "running": [
                    {
                        "task_key": r["task_key"],
                        "agent": r["agent_name"],
                        "running_sec": round(now - r["started_at"], 1),
                        "ttl_remaining": round(r["started_at"] + r["ttl"] - now, 0),
                    }
                    for r in running
                ],
                "recent_tasks": [
                    {
                        "task_key": r["task_key"],
                        "agent": r["agent_name"],
                        "ago_sec": round(now - r["finished_at"], 0),
                        "duration": round(r["duration"] or 0, 1),
                        "success": bool(r["success"]),
                    }
                    for r in recent
                ],
                "running_count": len(running),
            }
    except Exception as e:
        log.warning("get_status() Fehler: %s", e)
        return {"running": [], "recent_tasks": [], "running_count": 0}


# ─── Context Manager ──────────────────────────────────────────────────────────

class _TaskContext:
    def __init__(self, task_key: str, agent_name: str):
        self.task_key = task_key
        self.agent_name = agent_name
        self.already_running = False
        self.last_result: dict | None = None
        self.result: Any = None

    def skip(self, msg: str = "") -> None:
        """Task überspringen (kein release nötig)."""
        log.info("⏭️  %s: %s", self.task_key, msg or "übersprungen")
        self.already_running = True


@asynccontextmanager
async def run(task_key: str, agent_name: str = "auto", ttl: float = 300,
              reuse_result_age: float = 0):
    """
    Async Context Manager — beansprucht Task exklusiv.
    Bei already_running=True ist ein anderer Agent dran → last_result nutzen.
    Bei reuse_result_age>0: auch ohne laufenden Agenten altes Ergebnis zurückgeben.
    """
    if agent_name == "auto":
        import inspect
        frame = inspect.stack()[2]
        agent_name = Path(frame.filename).stem

    ctx = _TaskContext(task_key, agent_name)

    # Erst: früheres Ergebnis prüfen (Cache)
    if reuse_result_age > 0:
        cached = get_last_result(task_key, reuse_result_age)
        if cached:
            ctx.already_running = True
            ctx.last_result = cached
            yield ctx
            return

    # Task beanspruchen
    got_it = claim(task_key, agent_name, ttl)
    if not got_it:
        ctx.already_running = True
        ctx.last_result = get_last_result(task_key, ttl)
        log.info("⏭️  %s läuft bereits — Ergebnis wird wiederverwendet", task_key)
        yield ctx
        return

    success = True
    try:
        yield ctx
    except Exception as e:
        success = False
        log.error("Task %s fehlgeschlagen: %s", task_key, e)
        raise
    finally:
        release(task_key, agent_name, ctx.result, success)


# ─── Dekorator ────────────────────────────────────────────────────────────────

def task(task_key: str, agent_name: str = "auto", ttl: float = 300,
         reuse_result_age: float = 0):
    """
    Dekorator für async-Funktionen — verhindert Doppelausführung.

    @coordinator.task("shopify_sync", ttl=1800)
    async def sync():
        ...
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            async with run(task_key, agent_name or fn.__name__, ttl, reuse_result_age) as ctx:
                if ctx.already_running:
                    return ctx.last_result
                result = await fn(*args, **kwargs)
                ctx.result = result
                return result
        return wrapper
    return decorator
