"""
BrutusCore — Redirect-Shim (ersetzt durch brutal_ads_engine.py)
===============================================================
Alle bisherigen Imports wie `from modules.brutus_core import fire` funktionieren
weiterhin — leiten aber auf das neue, sichere BrutalAdsEngine weiter.

WARUM SHIM STATT DELETE:
  Brutus-Core wird von 20+ anderen Modulen importiert.
  Dieser Shim verhindert ImportError ohne alle Module anfassen zu müssen.

NEUE ENGINE: modules/brutal_ads_engine.py
  - Pre-Flight URL-Check (kein kaputtes Link je gepostet)
  - Expanded Content-Blocklist (30+ Einträge)
  - Rate-Limits pro Platform
  - 12 Kanäle statt 10
"""
import logging
import os

log = logging.getLogger("BrutusCore")
log.info("BrutusCore → leitet weiter an brutal_ads_engine.py")

# ── Alle öffentlichen Symbole aus neuer Engine re-exportieren ────────────────
from modules.brutal_ads_engine import (   # noqa: F401
    fire,
    get_status,
    run_brutal_cycle as fire_from_brutus,
)


class BrutusCore:
    """Kompatibilitäts-Wrapper — intern läuft brutal_ads_engine."""

    async def fire(self, message: str, channels: list = None,
                   link: str = "", title: str = "") -> dict:
        from modules.brutal_ads_engine import fire as _fire
        return await _fire(
            title=title or message[:60],
            body=message,
            link=link or os.getenv("DS24_AFFILIATE_LINK", ""),
            channels=channels,
        )
