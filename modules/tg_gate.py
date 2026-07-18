"""
TgGate — Globaler Telegram-Gatekeeper.

Intercept für ALLE ausgehenden sendMessage-Calls aus ALLEN Modulen.
Einmalig beim Server-Start aktiviert via install_global_intercept().

Schutzmechanismen:
  1. Pattern-Filter  — bestimmte Spam-Texte werden permanent blockiert
  2. Dedup           — gleiche Nachricht innerhalb von TG_DEDUP_SECONDS ignoriert
  3. Rate-Limit      — max TG_MAX_PER_HOUR Nachrichten pro Stunde

Railway Env Vars (alle optional):
  TG_SPAM_GUARD     = true/false   (Default: true)
  TG_MAX_PER_HOUR   = 50           (Default: 50)
  TG_DEDUP_SECONDS  = 300          (Default: 5 Minuten)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Dict, Tuple

log = logging.getLogger("TgGate")

_ENABLED      = os.getenv("TG_SPAM_GUARD",    "true").lower() != "false"
_MAX_PER_HOUR = int(os.getenv("TG_MAX_PER_HOUR",   "50"))
_DEDUP_SECS   = int(os.getenv("TG_DEDUP_SECONDS", "300"))

# ── Spam-Patterns: Nachrichten die NIEMALS gesendet werden dürfen ─────────────
_SPAM_PATTERNS = [
    # Viral Window Scanner
    "Viral Window Scanner",
    "VIRAL WINDOW ALERT",
    "Pro-Tier für Auto-Import",
    # eBay Arbitrage 0-Ergebnis
    "Gefunden: 0 Chancen | Importiert: 0",
    # Money Machine 0-Ergebnis
    "0 Alerts, 0 Imports",
    # EmailValidator Blocks
    "EmailValidator BLOCKIERT",
    # Insolvenz Radar einzelne Leads
    "InsolvenzRadar — Score",
    # Autonomer Loop / MRR €0
    "MRR €0.0",
    # Shop Scaling 0
    "Skalierungszyklus abgeschlossen",
    # Fake Trends
    "Trending NOW",
    # Conversion Optimizer 0-Bericht
    "Beschreibungen repariert: 0",
    "Produkte aktiviert: 0",
    # Revoked Bot-References
    "DudiRudibot",
    "RudiCludiBot",
    "t.me/DudiRudi",
    # Test-Orders
    "TEST PRODUKT",
    "BITTE IGNORIEREN",
    "test@supermegabot",
]

# ── State (in-memory, per Prozess) ────────────────────────────────────────────
_sent_times:   list     = []
_sent_hashes:  Dict     = {}
_blocked_count: int     = 0
_allowed_count: int     = 0


def _hash(text: str) -> str:
    return hashlib.md5(text[:500].encode("utf-8", errors="replace")).hexdigest()


def gate_check(text: str) -> Tuple[bool, str]:
    """
    Prüft ob eine Telegram-Nachricht gesendet werden darf.
    Returns (allowed: bool, reason: str).
    """
    global _blocked_count, _allowed_count

    if not _ENABLED:
        _allowed_count += 1
        return True, "gate_disabled"

    # 1. Pattern-Filter
    for p in _SPAM_PATTERNS:
        if p in text:
            _blocked_count += 1
            log.debug("TgGate BLOCK [pattern] '%s…': %.60s", p[:25], text)
            return False, f"pattern:{p[:25]}"

    now = time.time()

    # 2. Dedup-Check
    h = _hash(text)
    if h in _sent_hashes:
        age = now - _sent_hashes[h]
        if age < _DEDUP_SECS:
            _blocked_count += 1
            log.debug("TgGate BLOCK [dedup %.0fs ago]: %.60s", age, text)
            return False, f"dedup:{age:.0f}s"

    # 3. Rate-Limit
    global _sent_times
    _sent_times = [t for t in _sent_times if now - t < 3600]
    if len(_sent_times) >= _MAX_PER_HOUR:
        _blocked_count += 1
        log.warning("TgGate BLOCK [rate_limit %d/h]: %.60s", _MAX_PER_HOUR, text)
        return False, f"rate_limit:{len(_sent_times)}/h"

    # ✅ Erlaubt
    _sent_times.append(now)
    _sent_hashes[h] = now
    _allowed_count += 1
    return True, "ok"


def get_stats() -> dict:
    return {
        "enabled": _ENABLED,
        "allowed": _allowed_count,
        "blocked": _blocked_count,
        "sent_last_hour": len([t for t in _sent_times if time.time() - t < 3600]),
        "max_per_hour": _MAX_PER_HOUR,
        "dedup_seconds": _DEDUP_SECS,
    }


# ── aiohttp Fake-Response ─────────────────────────────────────────────────────

class _FakeResponse:
    """Fake aiohttp Response — gibt 200 OK ohne echten API-Call."""
    status = 200

    async def json(self, **_):
        return {"ok": True, "result": {"message_id": 0}}

    async def text(self, **_):
        return '{"ok":true}'

    def raise_for_status(self):
        pass


class _FakeContextManager:
    """
    Fake aiohttp context manager.
    Unterstützt beide Patterns:
      - await session.post(...)
      - async with session.post(...) as resp:
    """
    def __await__(self):
        return self._coro().__await__()

    async def _coro(self):
        return _FakeResponse()

    async def __aenter__(self):
        return _FakeResponse()

    async def __aexit__(self, *_):
        pass


# ── Globaler Intercept ────────────────────────────────────────────────────────

_installed = False


def install_global_intercept() -> None:
    """
    Monkey-patcht aiohttp.ClientSession.post + urllib.request.urlopen.
    Einmalig beim Server-Start aufrufen.
    """
    global _installed
    if _installed:
        return
    _installed = True

    _patch_aiohttp()
    _patch_urllib()
    log.info(
        "TgGate: globaler Intercept aktiv — max %d/h, dedup %ds, %d Spam-Patterns",
        _MAX_PER_HOUR, _DEDUP_SECS, len(_SPAM_PATTERNS),
    )


def _patch_aiohttp() -> None:
    try:
        import aiohttp

        _orig = aiohttp.ClientSession.post

        def _guarded_post(self, url, **kwargs):
            url_str = str(url)
            if "api.telegram.org" in url_str and "/sendMessage" in url_str:
                json_body = kwargs.get("json") or {}
                if isinstance(json_body, dict):
                    text = json_body.get("text", "")
                elif isinstance(json_body, (str, bytes)):
                    try:
                        text = json.loads(json_body).get("text", "")
                    except Exception:
                        text = ""
                else:
                    text = ""
                allowed, reason = gate_check(text)
                if not allowed:
                    return _FakeContextManager()

            return _orig(self, url, **kwargs)

        aiohttp.ClientSession.post = _guarded_post
        log.debug("TgGate: aiohttp.ClientSession.post gepatcht")

    except Exception as e:
        log.warning("TgGate: aiohttp-Patch fehlgeschlagen: %s", e)


def _patch_urllib() -> None:
    try:
        import urllib.request as _ur
        import io

        _orig_urlopen = _ur.urlopen

        def _guarded_urlopen(url, data=None, **kwargs):
            url_str = str(getattr(url, "full_url", url))
            if "api.telegram.org" in url_str and "/sendMessage" in url_str and data:
                try:
                    body = json.loads(
                        data.decode("utf-8") if isinstance(data, bytes) else data
                    )
                    text = body.get("text", "")
                    allowed, reason = gate_check(text)
                    if not allowed:
                        fake = io.BytesIO(b'{"ok":true,"result":{"message_id":0}}')
                        fake.status = 200
                        fake.reason = "OK"
                        return fake
                except Exception:
                    pass
            return _orig_urlopen(url, data=data, **kwargs)

        _ur.urlopen = _guarded_urlopen
        log.debug("TgGate: urllib.request.urlopen gepatcht")

    except Exception as e:
        log.warning("TgGate: urllib-Patch fehlgeschlagen: %s", e)
