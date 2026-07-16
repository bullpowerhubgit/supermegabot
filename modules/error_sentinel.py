"""
Error Sentinel — Permanentes Anti-Wiederholungs-Fehlersystem.
Verfolgt bekannte Fehler-Fingerprints und blockiert sie dauerhaft.
Sendet Telegram-Alert bei jedem Wiederholungsversuch.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("ErrorSentinel")

_DB_PATH = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data")) / "error_sentinel.db"
_lock = threading.Lock()

# ── Bekannte verbotene Fingerprints (NIEMALS erlaubt, sofort blockiert) ───────
KNOWN_VIOLATIONS: dict[str, str] = {
    "fake_product_import":            "Fake-Produkt importiert (HN/Reddit-Posts als Shopify-Produkte)",
    "wrong_ds24_account":             "Falscher DS24-Account verwendet (Key 1682000-... statt 1581233-...)",
    "wrong_fb_account":               "Falsches FB-Konto (IWIN statt AiiteC Page 1016738738178786)",
    "mailchimp_usage":                "Mailchimp verwendet — ALLE 3 Konten gesperrt, nur Klaviyo!",
    "mass_delete_without_confirm":    "Massen-Löschung ohne Bestätigung ('JA') von Rudolf",
    "bulk_activate":                  "shopify_bulk_activate aufgerufen — dauerhaft deaktiviert!",
    "demo_data_generation":           "Demo-Daten/_demo_leads() generiert statt echte 0-Ergebnis-Warnung",
    "railway_deploy_without_permission": "Railway-Deploy ohne explizite Erlaubnis von Rudolf",
    "gatekeeper_bypass":              "Shopify-Produkt ohne Gatekeeper-Check erstellt",
}

# ── Dynamische Fingerprints blockieren nach 2 Wiederholungen ─────────────────
_DYNAMIC_THRESHOLD = 2


def _init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sentinel_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL,
                description TEXT,
                module TEXT,
                ts TEXT NOT NULL,
                blocked INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fp ON sentinel_log(fingerprint)")
        conn.commit()


def _get_count(fingerprint: str) -> int:
    try:
        with sqlite3.connect(str(_DB_PATH)) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM sentinel_log WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
            return row[0] if row else 0
    except Exception as e:
        log.error("Sentinel DB read error: %s", e)
        return 0


def sentinel_check(fingerprint: str) -> bool:
    """
    Prüft ob eine Aktion erlaubt ist.
    Returns True = erlaubt, False = BLOCKIERT (bekannte Violation oder > 2x aufgetreten).
    """
    try:
        _init_db()
    except Exception as e:
        log.error("Sentinel init error — BLOCK: %s", e)
        return False

    if fingerprint in KNOWN_VIOLATIONS:
        log.critical("SENTINEL BLOCK (known violation): %s — %s",
                     fingerprint, KNOWN_VIOLATIONS[fingerprint])
        return False

    count = _get_count(fingerprint)
    if count >= _DYNAMIC_THRESHOLD:
        log.critical("SENTINEL BLOCK (repeated %dx): %s", count, fingerprint)
        return False

    return True


def sentinel_record(
    fingerprint: str,
    description: str = "",
    module: str = "unknown",
    blocked: bool = False,
) -> None:
    """
    Zeichnet einen Fehler-Fingerprint auf.
    Sendet Telegram-Alert wenn Fingerprint zum 2. Mal auftritt (oder bekannte Violation).
    """
    try:
        _init_db()
        ts = datetime.now(timezone.utc).isoformat()
        with _lock:
            with sqlite3.connect(str(_DB_PATH)) as conn:
                conn.execute(
                    "INSERT INTO sentinel_log (fingerprint, description, module, ts, blocked) VALUES (?,?,?,?,?)",
                    (fingerprint, description[:500], module[:100], ts, int(blocked)),
                )
                conn.commit()
        count = _get_count(fingerprint)

        is_known = fingerprint in KNOWN_VIOLATIONS
        if is_known or count >= _DYNAMIC_THRESHOLD:
            _send_telegram_alert(fingerprint, description, module, count, is_known)
    except Exception as e:
        log.error("Sentinel record error: %s", e)


def _send_telegram_alert(
    fingerprint: str, description: str, module: str, count: int, is_known: bool
) -> None:
    import asyncio
    import aiohttp

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return

    kind   = "🔴 BEKANNTE VIOLATION" if is_known else f"🟠 WIEDERHOLUNG #{count}"
    detail = KNOWN_VIOLATIONS.get(fingerprint, description or fingerprint)
    text   = (
        f"🚨 <b>ERROR SENTINEL</b>\n"
        f"{kind}: <code>{fingerprint}</code>\n"
        f"📋 {detail}\n"
        f"📦 Modul: <code>{module}</code>\n"
        f"🔢 Aufgetreten: {count}×\n"
        f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )

    async def _post() -> None:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as sess:
                await sess.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
                )
        except Exception as exc:
            log.warning("Sentinel Telegram alert failed: %s", exc)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_post())
        else:
            loop.run_until_complete(_post())
    except Exception as exc:
        log.warning("Sentinel alert dispatch failed: %s", exc)


def get_sentinel_status() -> dict:
    """Gibt Status-Übersicht zurück (für /health-Endpoint)."""
    try:
        _init_db()
        with sqlite3.connect(str(_DB_PATH)) as conn:
            total = conn.execute("SELECT COUNT(*) FROM sentinel_log").fetchone()[0]
            blocked = conn.execute(
                "SELECT COUNT(*) FROM sentinel_log WHERE blocked=1"
            ).fetchone()[0]
            recent = conn.execute(
                "SELECT fingerprint, ts FROM sentinel_log ORDER BY id DESC LIMIT 5"
            ).fetchall()
        return {
            "ok": True,
            "total_recorded": total,
            "total_blocked": blocked,
            "known_violations": list(KNOWN_VIOLATIONS.keys()),
            "recent": [{"fingerprint": r[0], "ts": r[1]} for r in recent],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
