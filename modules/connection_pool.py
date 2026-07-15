#!/usr/bin/env python3
"""
Connection Pool — Globale aiohttp Session für alle Module
=========================================================
Statt pro-Request `async with aiohttp.ClientSession() as s:` → globaler Pool.
Reduziert TCP-Handshakes und DNS-Lookups drastisch.

Nutzung in jedem Modul:
    from modules.connection_pool import get_session, close_pool

    async def my_func():
        s = await get_session()
        async with s.get("https://...") as r:
            ...
        # Session NICHT schließen — wird vom Pool verwaltet

Lebenszyklus:
    - get_session() gibt immer dieselbe Session zurück (erstellt sie beim ersten Aufruf)
    - close_pool() wird beim Server-Shutdown aufgerufen (server.py app.on_cleanup)
    - Bei Fehler (session closed) wird automatisch neu erstellt
"""
from __future__ import annotations

import asyncio
import logging
import os

import aiohttp

log = logging.getLogger("ConnectionPool")

# ── Konfiguration ─────────────────────────────────────────────────────────────
_LIMIT         = int(os.getenv("POOL_CONNECTIONS",    "200"))  # Gesamte Verbindungen
_LIMIT_PER_HOST= int(os.getenv("POOL_PER_HOST",        "30"))  # Pro Host
_KEEPALIVE_SEC = int(os.getenv("POOL_KEEPALIVE",       "60"))  # TCP Keepalive
_TIMEOUT_TOTAL = float(os.getenv("POOL_TIMEOUT",       "30"))  # Default Timeout
_OLLAMA_TIMEOUT= float(os.getenv("POOL_OLLAMA_TIMEOUT","120")) # Ollama braucht länger

_connector: aiohttp.TCPConnector | None = None
_session:   aiohttp.ClientSession | None = None
_lock = asyncio.Lock()


async def get_session(timeout: float | None = None) -> aiohttp.ClientSession:
    """
    Gibt die globale gepoolte aiohttp-Session zurück.
    Thread-safe, erstellt sie beim ersten Aufruf.
    """
    global _connector, _session

    if _session is not None and not _session.closed:
        if timeout is not None:
            _session._timeout = aiohttp.ClientTimeout(total=timeout)
        return _session

    async with _lock:
        if _session is not None and not _session.closed:
            return _session

        _connector = aiohttp.TCPConnector(
            limit=_LIMIT,
            limit_per_host=_LIMIT_PER_HOST,
            keepalive_timeout=_KEEPALIVE_SEC,
            enable_cleanup_closed=True,
            ssl=False,       # SSL wird per-Request gesetzt wenn nötig
            force_close=False,
        )
        _session = aiohttp.ClientSession(
            connector=_connector,
            timeout=aiohttp.ClientTimeout(total=_TIMEOUT_TOTAL),
            connector_owner=True,
        )
        log.info(
            "ConnectionPool gestartet: limit=%d per_host=%d keepalive=%ds",
            _LIMIT, _LIMIT_PER_HOST, _KEEPALIVE_SEC,
        )
    return _session


async def close_pool() -> None:
    """Pool sauber schließen — beim Server-Shutdown aufrufen."""
    global _session, _connector
    if _session and not _session.closed:
        await _session.close()
        log.info("ConnectionPool geschlossen")
    _session = None
    _connector = None


def get_timeout(seconds: float = _TIMEOUT_TOTAL) -> aiohttp.ClientTimeout:
    """Hilfsfunktion für einfache Timeout-Konfiguration."""
    return aiohttp.ClientTimeout(total=seconds)


# Vorfertige Timeouts für häufige Use-Cases
TIMEOUT_FAST   = aiohttp.ClientTimeout(total=5)    # Health-Checks
TIMEOUT_NORMAL = aiohttp.ClientTimeout(total=30)   # API-Calls
TIMEOUT_SLOW   = aiohttp.ClientTimeout(total=60)   # Scraping
TIMEOUT_AI     = aiohttp.ClientTimeout(total=120)  # KI-Generierung
TIMEOUT_PULL   = aiohttp.ClientTimeout(total=1800) # Model-Downloads
