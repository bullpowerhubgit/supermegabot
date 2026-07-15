#!/usr/bin/env python3
"""
AI Act Compliance — Stub-Modul
Dieses Modul ist noch nicht implementiert.
Alle Aufrufe liefern einen strukturierten Fehler statt ModuleNotFoundError.
"""

import logging

log = logging.getLogger(__name__)


class AIActCompliance:
    """Stub — echte Implementierung ausstehend."""

    def __init__(self):
        log.warning("AIActCompliance: Stub-Implementierung — keine echten Daten verfügbar")

    async def run_check(self):
        return {"ok": False, "error": "AIActCompliance nicht implementiert", "stub": True}


async def run_quick_check(system_description: str = ""):
    """Stub für run_quick_check()."""
    log.warning("ai_act_compliance.run_quick_check() aufgerufen — Stub")
    return {
        "ok": False,
        "error": "ai_act_compliance nicht implementiert",
        "stub": True,
        "system": system_description,
    }
