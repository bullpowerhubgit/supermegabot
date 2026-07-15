#!/usr/bin/env python3
"""
Migration Rush Engine — Stub-Modul
Dieses Modul ist noch nicht implementiert.
Alle Aufrufe liefern einen strukturierten Fehler statt ModuleNotFoundError.
"""

import logging

log = logging.getLogger(__name__)


class MigrationRushEngine:
    """Stub — echte Implementierung ausstehend."""

    def __init__(self):
        log.warning("MigrationRushEngine: Stub-Implementierung — keine echten Daten verfügbar")

    async def scan(self):
        return {"ok": False, "error": "MigrationRushEngine nicht implementiert", "stub": True}

    def get_signals(self):
        return {"ok": False, "error": "MigrationRushEngine nicht implementiert", "stub": True}


async def run_scan():
    """Stub für run_scan()."""
    log.warning("migration_rush_engine.run_scan() aufgerufen — Stub")
    return {"ok": False, "error": "migration_rush_engine nicht implementiert", "stub": True}


def get_signals():
    """Stub für get_signals()."""
    return {"ok": False, "error": "migration_rush_engine nicht implementiert", "stub": True}
