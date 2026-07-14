"""
Distributed Lock — verhindert Duplikate über alle Terminals/Agenten hinweg.
Nutzt Supabase als gemeinsamen Backend (nicht SQLite — das ist nur lokal!).

Nutzung:
    async with acquire_lock("shopify_import", ttl=300) as locked:
        if not locked:
            return "Läuft bereits in anderem Terminal"
        # Arbeit hier

    # Oder mit Dedup-Key (einmalige Ausführung pro Zeitfenster):
    if await already_done("email_blast", window_hours=1):
        return "Bereits in letzter Stunde ausgeführt"
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import socket
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Optional

log = logging.getLogger("DistributedLock")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
AGENT_ID = f"{socket.gethostname()}-{os.getpid()}"


def _client():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


async def _run(fn, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


@asynccontextmanager
async def acquire_lock(lock_key: str, ttl: int = 300):
    """
    Distributed Lock über Supabase.
    Gibt True zurück wenn Lock erworben, False wenn bereits aktiv.
    Lock wird automatisch nach ttl Sekunden freigegeben.
    """
    acquired = False
    try:
        client = _client()
        expires_at = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() + ttl)
        )

        # Abgelaufene Locks zuerst löschen
        await _run(
            lambda: client.table("agent_locks")
            .delete()
            .lt("expires_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            .execute()
        )

        # Lock versuchen zu erwerben (Primary Key = lock_key → nur einer gewinnt)
        try:
            await _run(
                lambda: client.table("agent_locks").insert({
                    "lock_key":    lock_key,
                    "agent_id":    AGENT_ID,
                    "hostname":    socket.gethostname(),
                    "expires_at":  expires_at,
                    "meta":        {"pid": os.getpid()},
                }).execute()
            )
            acquired = True
            log.debug(f"Lock erworben: {lock_key} (TTL={ttl}s)")
        except Exception as e:
            if "duplicate" in str(e).lower() or "unique" in str(e).lower() or "23505" in str(e):
                log.info(f"Lock '{lock_key}' bereits aktiv in anderem Terminal/Agenten")
                acquired = False
            else:
                log.warning(f"Lock-Fehler ({lock_key}): {e}")
                acquired = True  # Bei unbekanntem Fehler: trotzdem ausführen

        yield acquired

    finally:
        if acquired:
            try:
                client = _client()
                await _run(
                    lambda: client.table("agent_locks")
                    .delete()
                    .eq("lock_key", lock_key)
                    .eq("agent_id", AGENT_ID)
                    .execute()
                )
                log.debug(f"Lock freigegeben: {lock_key}")
            except Exception as e:
                log.warning(f"Lock-Release-Fehler ({lock_key}): {e}")


async def already_done(task_name: str, dedup_key: str = "", window_hours: float = 1.0) -> bool:
    """
    Prüft ob Task bereits in letzten window_hours ausgeführt wurde.
    dedup_key: optionaler Zusatz (z.B. Produkt-ID, E-Mail-Adresse)
    """
    try:
        client = _client()
        key = f"{task_name}:{dedup_key}" if dedup_key else task_name
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:32]
        window_key = f"{key_hash}:{int(time.time() // (window_hours * 3600))}"

        result = await _run(
            lambda: client.table("agent_dedup_log")
            .select("id,executed_at")
            .eq("dedup_key", window_key)
            .execute()
        )
        if result.data:
            log.info(f"Dedup: '{task_name}' bereits ausgeführt (window={window_hours}h)")
            return True
        return False
    except Exception as e:
        log.warning(f"Dedup-Check-Fehler: {e}")
        return False


async def mark_done(task_name: str, dedup_key: str = "",
                    window_hours: float = 1.0, result: Any = None) -> None:
    """Task als erledigt markieren (für already_done Prüfung)."""
    try:
        client = _client()
        key = f"{task_name}:{dedup_key}" if dedup_key else task_name
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:32]
        window_key = f"{key_hash}:{int(time.time() // (window_hours * 3600))}"

        await _run(
            lambda: client.table("agent_dedup_log").upsert({
                "dedup_key":   window_key,
                "task_name":   task_name,
                "agent_id":    AGENT_ID,
                "result":      result or {},
            }, on_conflict="dedup_key").execute()
        )
    except Exception as e:
        log.warning(f"mark_done-Fehler: {e}")


def make_dedup_hash(*args) -> str:
    """Erstellt reproduzierbaren Hash aus beliebigen Werten (für DB-Einträge)."""
    raw = "|".join(str(a) for a in args)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def safe_insert(table: str, data: dict, dedup_fields: list[str]) -> bool:
    """
    Upsert statt Insert — verhindert Duplikate in Supabase-Tabellen.
    dedup_fields: Felder die zusammen eindeutig sein müssen.
    Gibt True zurück wenn neu eingefügt, False wenn Duplikat.
    """
    try:
        client = _client()
        dedup_key = make_dedup_hash(*[data.get(f, "") for f in dedup_fields])
        data["dedup_hash"] = dedup_key

        result = await _run(
            lambda: client.table(table)
            .upsert(data, on_conflict="dedup_hash")
            .execute()
        )
        return bool(result.data)
    except Exception as e:
        log.warning(f"safe_insert({table}): {e}")
        return False
