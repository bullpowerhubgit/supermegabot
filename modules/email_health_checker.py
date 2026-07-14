#!/usr/bin/env python3
"""Email-System Health Checker — prüft alle SMTP-Konten, Klaviyo, Mailchimp,
Queue-Größen und sendet Telegram-Alerts bei Problemen."""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

log = logging.getLogger("EmailHealthChecker")

# ── Projekt-Root & .env laden ────────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent
_ENV_FILE = _ROOT / ".env"
_DATA_DIR = _ROOT / "data"


def _load_env(path: Path = _ENV_FILE) -> None:
    """Lädt .env-Datei in os.environ (kein python-dotenv erforderlich)."""
    if not path.exists():
        log.warning(".env nicht gefunden: %s", path)
        return
    try:
        import dotenv  # type: ignore
        dotenv.load_dotenv(str(path), override=False)
        return
    except ImportError:
        pass
    # Fallback: manuelle .env-Verarbeitung
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


# Env beim Modulimport laden
_load_env()


# ── Telegram-Alert ───────────────────────────────────────────────────────────

async def _send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log.debug("Telegram nicht konfiguriert — Alert übersprungen")
        return
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=12),
            )
    except Exception as exc:
        log.warning("Telegram-Alert fehlgeschlagen: %s", exc)


# ── SMTP-Tests (parallel) ────────────────────────────────────────────────────

def _test_smtp_sync(account) -> Dict[str, Any]:
    """Synchroner SMTP-Test — läuft im ThreadPoolExecutor."""
    from modules.gmail_accounts import test_smtp  # lokaler Import
    return test_smtp(account)


async def _test_all_smtp() -> List[Dict[str, Any]]:
    """Testet alle 8 Gmail-Konten parallel im Thread-Pool."""
    from modules.gmail_accounts import list_accounts

    accounts = list_accounts()
    if not accounts:
        log.warning("Keine Gmail-Konten konfiguriert")
        return []

    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, _test_smtp_sync, acc)
        for acc in accounts
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    results: List[Dict[str, Any]] = []
    for acc, res in zip(accounts, raw_results):
        if isinstance(res, Exception):
            results.append({
                "index": acc.index,
                "email": acc.email,
                "ok": False,
                "error": str(res)[:120],
                "host": acc.smtp_host,
            })
        else:
            entry = {
                "index": acc.index,
                "email": acc.email,
                "ok": bool(res.get("ok")),
                "host": acc.smtp_host,
            }
            if not res.get("ok"):
                entry["error"] = res.get("error", "unbekannt")[:120]
            results.append(entry)
    return results


# ── Klaviyo-Test ─────────────────────────────────────────────────────────────

async def _test_klaviyo() -> Dict[str, Any]:
    try:
        from modules.klaviyo_automation import ping as klaviyo_ping
        ok, detail = await klaviyo_ping()
        return {"ok": ok, "detail": str(detail)[:120]}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)[:120]}


# ── Mailchimp-Test ───────────────────────────────────────────────────────────

async def _test_mailchimp() -> Dict[str, Any]:
    try:
        from modules.mailchimp_automation import ping as mc_ping
        ok, detail = await mc_ping()
        return {"ok": ok, "detail": str(detail)[:120]}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)[:120]}


# ── Queue-Größen ─────────────────────────────────────────────────────────────

# Alle SQLite-DBs, die E-Mail-Warteschlangen enthalten könnten
_QUEUE_DBS: List[Dict[str, Any]] = [
    {"file": "email_queue.db",        "table": "queue",          "col": "status", "val": "pending"},
    {"file": "email_conversations.db","table": "conversations",   "col": None,     "val": None},
    {"file": "mail_error_guard.db",   "table": "errors",         "col": None,     "val": None},
    {"file": "bulk_outreach.db",      "table": "outreach",       "col": "status", "val": "pending"},
    {"file": "mass_outreach.db",      "table": "outreach",       "col": "status", "val": "pending"},
    {"file": "shoptext.db",           "table": "messages",       "col": "status", "val": "pending"},
    {"file": "outreach_engine.db",    "table": "outreach",       "col": "status", "val": "pending"},
]


def _count_queue_rows(db_info: Dict[str, Any]) -> int:
    """Zählt Zeilen in einer SQLite-Tabelle (filtert optional nach Status)."""
    db_path = _DATA_DIR / db_info["file"]
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        cur = conn.cursor()
        # Tabellen in der DB ermitteln
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        table = db_info.get("table", "")
        if table not in tables:
            # Erste verfügbare Tabelle verwenden
            if not tables:
                conn.close()
                return 0
            table = next(iter(tables))
        if db_info.get("col") and db_info.get("val"):
            col, val = db_info["col"], db_info["val"]
            # Spalte prüfen ob sie existiert
            cur.execute(f"PRAGMA table_info({table})")
            cols = {row[1] for row in cur.fetchall()}
            if col in cols:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col}=?", (val,))
            else:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
        else:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        conn.close()
        return int(count)
    except Exception as exc:
        log.debug("Queue-DB %s Fehler: %s", db_info["file"], exc)
        return 0


async def _get_queue_sizes() -> Dict[str, int]:
    """Liefert Queue-Größen für alle bekannten E-Mail-DBs."""
    loop = asyncio.get_event_loop()
    results: Dict[str, int] = {}
    tasks = {
        db["file"]: loop.run_in_executor(None, _count_queue_rows, db)
        for db in _QUEUE_DBS
    }
    for name, task in tasks.items():
        try:
            results[name] = await task
        except Exception:
            results[name] = 0
    return results


# ── Tägliche Kapazität ───────────────────────────────────────────────────────

_GMAIL_SAFE_DAILY = 200   # konservative Grenze pro Gmail-Konto
_SENDGRID_DAILY = 100     # SendGrid Free-Tier Basis


def _compute_daily_capacity(smtp_results: List[Dict[str, Any]]) -> int:
    working_gmail = sum(1 for r in smtp_results if r.get("ok"))
    sendgrid_key = os.getenv("SENDGRID_API_KEY", "")
    sendgrid_cap = _SENDGRID_DAILY if sendgrid_key else 0
    return working_gmail * _GMAIL_SAFE_DAILY + sendgrid_cap


# ── Telegram-Alert für defekte Konten ────────────────────────────────────────

async def _alert_broken(
    smtp_results: List[Dict[str, Any]],
    klaviyo: Dict[str, Any],
    mailchimp: Dict[str, Any],
) -> None:
    broken_smtp = [r for r in smtp_results if not r.get("ok")]
    problems: List[str] = []

    if broken_smtp:
        problems.append(f"*SMTP defekt ({len(broken_smtp)} Konten):*")
        for r in broken_smtp:
            err = r.get("error", "unbekannt")
            problems.append(f"  ❌ `{r['email']}` — {err[:80]}")

    if not klaviyo.get("ok"):
        problems.append(f"*Klaviyo:* ❌ {klaviyo.get('detail','?')[:80]}")

    if not mailchimp.get("ok"):
        problems.append(f"*Mailchimp:* ❌ {mailchimp.get('detail','?')[:80]}")

    if not problems:
        return  # Alles OK → kein Alert nötig

    ts = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    header = f"📧 *Email-Health-Alert* — {ts}\n"
    await _send_telegram(header + "\n".join(problems))


# ── Haupt-Funktion ───────────────────────────────────────────────────────────

async def run_email_health_check() -> Dict[str, Any]:
    """
    Prüft alle E-Mail-Systeme und gibt einen strukturierten Health-Report zurück.

    Returns:
        {
            "smtp_accounts": [{"email": str, "ok": bool, "error": str|None}],
            "klaviyo_ok": bool,
            "mailchimp_ok": bool,
            "queue_size": int,          # Summe aller Queue-Einträge
            "daily_capacity": int,      # Schätzung E-Mails/Tag
            "timestamp": str,
            "summary": str,
        }
    """
    log.info("Email-Health-Check gestartet")
    ts = datetime.now(timezone.utc).isoformat()

    # Alle Tests parallel starten
    smtp_task = asyncio.create_task(_test_all_smtp())
    klaviyo_task = asyncio.create_task(_test_klaviyo())
    mailchimp_task = asyncio.create_task(_test_mailchimp())
    queue_task = asyncio.create_task(_get_queue_sizes())

    smtp_results, klaviyo_res, mailchimp_res, queue_sizes = await asyncio.gather(
        smtp_task, klaviyo_task, mailchimp_task, queue_task
    )

    # Queue-Gesamtgröße
    total_queue = sum(queue_sizes.values())

    # Tägliche Kapazität
    daily_cap = _compute_daily_capacity(smtp_results)

    # Telegram-Alert senden (nur bei Problemen)
    await _alert_broken(smtp_results, klaviyo_res, mailchimp_res)

    # Zusammenfassung
    smtp_ok = sum(1 for r in smtp_results if r.get("ok"))
    smtp_total = len(smtp_results)
    summary_parts = [
        f"SMTP: {smtp_ok}/{smtp_total} OK",
        f"Klaviyo: {'OK' if klaviyo_res.get('ok') else 'FEHLER'}",
        f"Mailchimp: {'OK' if mailchimp_res.get('ok') else 'FEHLER'}",
        f"Queue: {total_queue}",
        f"Kapazität: {daily_cap}/Tag",
    ]
    summary = " | ".join(summary_parts)
    log.info("Email-Health-Check abgeschlossen: %s", summary)

    report: Dict[str, Any] = {
        "smtp_accounts": smtp_results,
        "klaviyo_ok": bool(klaviyo_res.get("ok")),
        "klaviyo_detail": klaviyo_res.get("detail", ""),
        "mailchimp_ok": bool(mailchimp_res.get("ok")),
        "mailchimp_detail": mailchimp_res.get("detail", ""),
        "queue_size": total_queue,
        "queue_breakdown": queue_sizes,
        "daily_capacity": daily_cap,
        "timestamp": ts,
        "summary": summary,
    }
    return report


# ── CLI-Einstiegspunkt ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    async def _main() -> None:
        report = await run_email_health_check()
        print(json.dumps(report, indent=2, ensure_ascii=False))

    asyncio.run(_main())
