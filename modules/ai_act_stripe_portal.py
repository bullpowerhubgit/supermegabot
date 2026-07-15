#!/usr/bin/env python3
"""
AI Act Stripe Portal — Stub-Modul
Dieses Modul ist noch nicht implementiert.
Alle Aufrufe liefern einen strukturierten Fehler statt ModuleNotFoundError.
"""

import logging

log = logging.getLogger(__name__)


async def create_checkout(email: str, package: str = "basic"):
    """Stub für create_checkout()."""
    log.warning("ai_act_stripe_portal.create_checkout() aufgerufen — Stub")
    return {
        "ok": False,
        "error": "ai_act_stripe_portal nicht implementiert",
        "stub": True,
        "email": email,
        "package": package,
    }
