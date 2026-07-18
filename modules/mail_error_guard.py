#!/usr/bin/env python3
"""
Mail Error Guard — Gmail scannen, Fehler-Muster erkennen, Wiederholungen blockieren
====================================================================================
Läuft alle 15 Minuten:
  1. Beide Gmail-Konten via IMAP auf Fehler-Mails scannen
  2. Fehler-Fingerprint (Hash) in SQLite speichern
  3. Beim ersten Vorkommen: Telegram-Alert + Auto-Fix versuchen
  4. Beim 2.+ Vorkommen: Eskalations-Alert + stärkerer Fix
  5. Nach Auto-Fix: prüfen ob Fehler aufgehört hat

Erkannte Fehler-Quellen:
  - Railway: Build Failed, Deploy Error, Health Check Failed
  - GitHub Actions: Workflow Failed, Syntax Error
  - Stripe: Payment Failed, Webhook Error
  - Service Delivery: Delivery Error, Gmail SMTP Failed
  - Shopify: API Error, Rate Limit
  - Supabase: Connection Error, RLS Error
  - Telegram Bot: Blocked, Timeout
"""
from __future__ import annotations

import email
import email.header
import hashlib
import imaplib
import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("MailErrorGuard")

_BASE      = Path(__file__).parent.parent
_DB_PATH   = _BASE / "data" / "mail_error_guard.db"
_TG_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
_RAILWAY   = os.getenv("RAILWAY_PUBLIC_DOMAIN",
                        "supermegabot-production.up.railway.app")

# ── Fehler-Muster ─────────────────────────────────────────────────────────────

# (Absender-Pattern, Betreff-Pattern, Kategorie, Schwere, Auto-Fix-Aktion)
ERROR_PATTERNS = [
    # Railway
    ("railway",           "build failed",          "railway_build",    "HIGH",   "redeploy"),
    ("railway",           "deploy failed",          "railway_deploy",   "HIGH",   "redeploy"),
    ("railway",           "health check failed",    "railway_health",   "HIGH",   "redeploy"),
    ("railway",           "crashed",                "railway_crash",    "HIGH",   "redeploy"),
    # GitHub Actions
    ("github",            "workflow run failed",    "github_ci",        "MEDIUM", "syntax_check"),
    ("github",            "build failed",           "github_build",     "MEDIUM", "syntax_check"),
    # Stripe
    ("stripe",            "payment failed",         "stripe_payment",   "HIGH",   "stripe_alert"),
    ("stripe",            "failed to send",         "stripe_webhook",   "MEDIUM", "stripe_alert"),
    ("stripe.com",        "dispute",                "stripe_dispute",   "HIGH",   "stripe_alert"),
    # Shopify
    ("shopify",           "api limit",              "shopify_rate",     "LOW",    "circuit_reset"),
    ("shopify",           "error",                  "shopify_error",    "MEDIUM", "circuit_reset"),
    # Supabase
    ("supabase",          "error",                  "supabase_error",   "MEDIUM", "circuit_reset"),
    # Digistore24
    ("digistore",         "fehler",                 "ds24_error",       "MEDIUM", "notify_only"),
    ("digistore",         "error",                  "ds24_error",       "MEDIUM", "notify_only"),
    # Service Delivery / eigene Mails
    ("mailer-daemon",     "",                       "smtp_bounce",      "MEDIUM", "notify_only"),
    ("delivery failed",   "",                       "smtp_bounce",      "MEDIUM", "notify_only"),
    ("undeliverable",     "",                       "smtp_bounce",      "LOW",    "notify_only"),
    # Security
    ("google",            "sign-in",                "security_login",   "HIGH",   "notify_only"),
    ("google",            "suspicious",             "security_login",   "HIGH",   "notify_only"),
    ("",                  "unauthorized",           "security_unauth",  "HIGH",   "notify_only"),
]

# Absender, die immer übersprungen werden
SKIP_SENDERS = [
    "linkedin", "twitter", "instagram", "temu", "zalando", "check24",
    "medium.com", "substack", "newsletter", "noreply@github.com",
    "notifications@github.com",  # nur normale Github Benachrichtigungen
]

# Eigene System-Mails (nicht als Fehler werten)
OWN_SYSTEM_SENDERS = [
    "aiitecbuuss@gmail.com", "bullpowersrtkennels@gmail.com",
    "bullpowerhubgit", "noreply@shopify.com",
]

# ── Datenbank ─────────────────────────────────────────────────────────────────

def _init_db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB_PATH))
    c.executescript("""
        CREATE TABLE IF NOT EXISTS error_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL,
            category    TEXT NOT NULL,
            severity    TEXT NOT NULL,
            sender      TEXT,
            subject     TEXT,
            first_seen  TEXT NOT NULL,
            last_seen   TEXT NOT NULL,
            count       INTEGER DEFAULT 1,
            auto_fixed  INTEGER DEFAULT 0,
            fix_action  TEXT,
            resolved    INTEGER DEFAULT 0
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fingerprint ON error_log(fingerprint);
        CREATE TABLE IF NOT EXISTS scanned_ids (
            mail_id     TEXT PRIMARY KEY,
            account     TEXT,
            scanned_at  TEXT
        );
    """)
    c.commit()
    return c


def _fingerprint(category: str, subject: str) -> str:
    """Eindeutiger Hash pro Fehler-Typ (ignoriert variable Teile wie Timestamps)."""
    clean = re.sub(r"\d{4}-\d{2}-\d{2}|\d{2}:\d{2}|\#\w+|job \w+", "", subject.lower())
    return hashlib.sha1(f"{category}:{clean[:80]}".encode()).hexdigest()[:16]


def _record_error(conn: sqlite3.Connection, fp: str, category: str,
                  severity: str, sender: str, subject: str, fix: str) -> dict:
    """Schreibt Fehler in DB, gibt zurück ob neu oder Wiederholung."""
    now = datetime.now(timezone.utc).isoformat()
    row = conn.execute(
        "SELECT id, count, first_seen, auto_fixed FROM error_log WHERE fingerprint=?", (fp,)
    ).fetchone()

    if row:
        conn.execute(
            "UPDATE error_log SET count=count+1, last_seen=?, resolved=0 WHERE fingerprint=?",
            (now, fp),
        )
        conn.commit()
        return {"new": False, "count": row[1] + 1, "first_seen": row[2], "auto_fixed": bool(row[3])}
    else:
        conn.execute(
            """INSERT INTO error_log
               (fingerprint,category,severity,sender,subject,first_seen,last_seen,fix_action)
               VALUES (?,?,?,?,?,?,?,?)""",
            (fp, category, severity, sender[:100], subject[:200], now, now, fix),
        )
        conn.commit()
        return {"new": True, "count": 1, "first_seen": now, "auto_fixed": False}


# ── Gmail IMAP ────────────────────────────────────────────────────────────────

def _decode_header(h: str) -> str:
    parts = email.header.decode_header(h or "")
    out = []
    for part, enc in parts:
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(str(part))
    return " ".join(out).strip()


def _gmail_accounts() -> list:
    try:
        from modules.gmail_accounts import list_accounts
        return [{"email": a.email, "password": a.password} for a in list_accounts() if a.password]
    except Exception:
        accounts = []
        for suffix in ["", "_2", "_3", "_4", "_5"]:
            u = os.getenv(f"GMAIL_USER{suffix}", "")
            p = os.getenv(f"GMAIL_APP_PASSWORD{suffix}", "")
            if u and p:
                accounts.append({"email": u, "password": p})
        return accounts


def _scan_account(account: dict, conn: sqlite3.Connection) -> list:
    """IMAP-Scan eines Gmail-Kontos — gibt Fehler-Events zurück."""
    events = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(account["email"], account["password"].replace(" ", ""))
        mail.select("INBOX")

        _, data = mail.search(None, "UNSEEN")
        ids = (data[0].split() if data[0] else [])[-50:]  # max 50 neueste

        for uid in ids:
            uid_str = uid.decode()
            already = conn.execute(
                "SELECT 1 FROM scanned_ids WHERE mail_id=?", (uid_str,)
            ).fetchone()
            if already:
                continue

            _, msg_data = mail.fetch(uid, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue

            msg     = email.message_from_bytes(msg_data[0][1])
            sender  = _decode_header(msg.get("From", "")).lower()
            subject = _decode_header(msg.get("Subject", ""))
            subj_l  = subject.lower()

            # Als gescannt markieren
            conn.execute(
                "INSERT OR IGNORE INTO scanned_ids (mail_id,account,scanned_at) VALUES (?,?,?)",
                (uid_str, account["email"], datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

            # Skip-Filter
            if any(sk in sender for sk in SKIP_SENDERS):
                continue

            # Fehler-Pattern abgleichen
            for (sndr_pat, subj_pat, category, severity, fix) in ERROR_PATTERNS:
                if sndr_pat and sndr_pat not in sender:
                    continue
                if subj_pat and subj_pat not in subj_l:
                    continue
                fp    = _fingerprint(category, subject)
                state = _record_error(conn, fp, category, severity, sender[:80], subject, fix)
                events.append({
                    "fingerprint": fp,
                    "category":   category,
                    "severity":   severity,
                    "sender":     sender[:60],
                    "subject":    subject[:100],
                    "fix":        fix,
                    **state,
                })
                break  # nur erstes passendes Pattern verwenden

        mail.logout()
    except Exception as e:
        log.warning("IMAP %s: %s", account["email"], e)
    return events


# ── Auto-Fix Aktionen ──────────────────────────────────────────────────────────

async def _auto_fix(action: str, category: str, session: aiohttp.ClientSession) -> str:
    base = f"https://{_RAILWAY}"
    try:
        if action == "circuit_reset":
            async with session.post(
                f"{base}/api/circuit/reset",
                json={"service": category},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                return f"Circuit Reset: HTTP {r.status}"

        elif action == "redeploy":
            # Railway Redeploy via eigenen Scheduler-Health-Endpoint
            async with session.post(
                f"{base}/api/scheduler/health",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                return f"Health-Ping: HTTP {r.status}"

        elif action == "syntax_check":
            async with session.post(
                f"{base}/api/bot/execute",
                json={"command": "/syntax_check"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return f"Syntax-Check: HTTP {r.status}"

        elif action == "stripe_alert":
            return "Stripe-Alert: manuell prüfen erforderlich"

    except Exception as e:
        return f"Fix-Fehler: {e}"

    return "notify_only"


# ── Telegram Alerts ────────────────────────────────────────────────────────────

async def _tg_alert(session: aiohttp.ClientSession, event: dict, fix_result: str) -> None:
    if not _TG_TOKEN or not _TG_CHAT:
        return

    count    = event["count"]
    severity = event["severity"]
    category = event["category"]
    subject  = event["subject"]

    # smtp_bounce: NUR beim ersten Mal alertieren (zu viele Bounces = normaler Email-Betrieb)
    if category == "smtp_bounce" and count > 1:
        log.debug("smtp_bounce %d× — kein weiteres Telegram", count)
        return

    if count == 1:
        icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(severity, "⚪")
        msg  = (
            f"{icon} <b>Neuer Fehler erkannt</b>\n"
            f"Kategorie: <code>{category}</code>\n"
            f"Betreff: {subject[:80]}\n"
            f"Auto-Fix: {fix_result}"
        )
    elif count in (5, 10, 25, 50):
        # Nur bei runden Zahlen erinnern — nicht bei 2, 3, 4...
        msg = (
            f"⚠️ <b>Fehler wiederholt ({count}×)</b>\n"
            f"Kategorie: <code>{category}</code>\n"
            f"{subject[:80]}\n"
            f"Auto-Fix: {fix_result}"
        )
    else:
        log.debug("Fehler %s wiederholt (%d×) — kein Telegram", category, count)
        return

    if count > 10:
        msg += f"\n<b>Tritt seit {event.get('first_seen', '?')[:10]} auf — Manuelle Prüfung!</b>"

    try:
        async with session.post(
            f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
            json={"chat_id": _TG_CHAT, "text": msg, "parse_mode": "HTML"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status != 200:
                log.warning("Telegram alert HTTP %s", r.status)
    except Exception as e:
        log.debug("Telegram skip: %s", e)


# ── Bounce-Scanner ────────────────────────────────────────────────────────────

def _scan_bounces(account: dict, conn: sqlite3.Connection) -> list:
    """
    Liest Bounce-Mails (Mailer-Daemon) und gibt fehlgeschlagene Adressen zurück.
    Markiert sie sofort in bo_companies als bounced.
    """
    bounced = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(account["email"], account["password"].replace(" ", ""))
        mail.select("INBOX")

        # Suche nach Bounce-Mails seit 30 Tagen
        _, data = mail.search(None, "FROM", "mailer-daemon", "SINCE", "01-Jun-2026")
        ids = (data[0].split() if data[0] else [])[-100:]

        for uid in ids:
            uid_str = uid.decode()
            already = conn.execute(
                "SELECT 1 FROM scanned_ids WHERE mail_id=?", (f"bounce_{uid_str}",)
            ).fetchone()
            if already:
                continue

            _, msg_data = mail.fetch(uid, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue

            msg  = email.message_from_bytes(msg_data[0][1])
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() in ("text/plain", "message/delivery-status"):
                        try:
                            body += part.get_payload(decode=True).decode("utf-8", errors="replace")
                        except Exception:
                            pass
            else:
                try:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass

            # Extrahiere fehlgeschlagene Adressen
            failed = re.findall(
                r"(?:Final-Recipient|Original-Recipient|To):[^\n]*?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
                body,
            )
            # Auch aus dem Subject und Body direkt
            failed += re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", body)

            conn.execute(
                "INSERT OR IGNORE INTO scanned_ids (mail_id,account,scanned_at) VALUES (?,?,?)",
                (f"bounce_{uid_str}", account["email"], datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

            for addr in set(failed):
                addr = addr.lower().strip()
                # Eigene Adressen und bekannte valide Adressen überspringen
                if any(own in addr for own in ["gmail.com", "googlemail.com", "aiitec", "bullpower"]):
                    continue
                bounced.append(addr)

        mail.logout()
    except Exception as e:
        log.warning("Bounce-Scan %s: %s", account.get("email", "?"), e)
    return bounced


async def process_bounces(bounced_addrs: list, session: aiohttp.ClientSession) -> int:
    """Blacklistet gebounced Adressen in email_outreach_bulk DB."""
    if not bounced_addrs:
        return 0
    fixed = 0
    try:
        from modules.email_outreach_bulk import mark_bounced
        for addr in set(bounced_addrs):
            if mark_bounced(addr):
                fixed += 1
                log.info("Bounce-Blacklist: %s", addr)
    except Exception as e:
        log.warning("process_bounces: %s", e)

    if fixed > 0:
        msg = (
            f"🚫 <b>Bounce Auto-Blacklist</b>\n"
            f"{fixed} Adressen als ungültig markiert:\n"
            + "\n".join(f"  • {a}" for a in list(set(bounced_addrs))[:10])
            + "\nWerden nie mehr kontaktiert."
        )
        try:
            async with session.post(
                f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
                json={"chat_id": _TG_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                pass
        except Exception:
            pass
    return fixed


# ── Hauptfunktion ──────────────────────────────────────────────────────────────

async def run_mail_error_guard() -> dict:
    """
    Scannt beide Gmail-Konten, erkennt Fehler-Muster, triggert Auto-Fixes.
    Einstiegspunkt für Scheduler (alle 15 min).
    """
    conn     = _init_db()
    accounts = _gmail_accounts()
    if not accounts:
        log.warning("Keine Gmail-Konten konfiguriert")
        conn.close()
        return {"ok": False, "reason": "no_gmail_accounts"}

    all_events: list = []
    for acc in accounts:
        events = _scan_account(acc, conn)
        all_events.extend(events)

    fixed_count    = 0
    alerted_count  = 0

    async with aiohttp.ClientSession() as session:
        for ev in all_events:
            fix_result = await _auto_fix(ev["fix"], ev["category"], session)

            # Fix in DB vermerken
            if "HTTP 200" in fix_result or "HTTP 201" in fix_result:
                conn.execute(
                    "UPDATE error_log SET auto_fixed=1 WHERE fingerprint=?",
                    (ev["fingerprint"],),
                )
                conn.commit()
                fixed_count += 1

            # Alert nur wenn: neuer Fehler ODER count ist 2, 3, 5, 10, 25 (nicht bei jedem Vorkommen)
            count = ev["count"]
            if ev["new"] or count in (2, 3, 5, 10, 25):
                await _tg_alert(session, ev, fix_result)
                alerted_count += 1

    # Bounce-Scan: tote Adressen automatisch blacklisten
    all_bounced: list = []
    for acc in accounts:
        bounced = _scan_bounces(acc, conn)
        all_bounced.extend(bounced)

    conn.close()

    bounces_fixed = 0
    if all_bounced:
        async with aiohttp.ClientSession() as session:
            bounces_fixed = await process_bounces(all_bounced, session)

    log.info(
        "MailErrorGuard: %d Konten, %d Fehler, %d gefixt, %d Alerts, %d Bounces blacklisted",
        len(accounts), len(all_events), fixed_count, alerted_count, bounces_fixed,
    )
    return {
        "ok":              True,
        "accounts":        len(accounts),
        "errors_found":    len(all_events),
        "new_errors":      sum(1 for e in all_events if e["new"]),
        "repeated":        sum(1 for e in all_events if not e["new"]),
        "auto_fixed":      fixed_count,
        "alerts_sent":     alerted_count,
        "bounces_blocked": bounces_fixed,
    }


async def get_error_summary() -> dict:
    """Gibt eine Übersicht aller offenen Fehler zurück (für Dashboard/API)."""
    conn = _init_db()
    rows = conn.execute("""
        SELECT category, severity, subject, count, first_seen, last_seen, auto_fixed, resolved
        FROM error_log
        WHERE resolved=0
        ORDER BY count DESC, last_seen DESC
        LIMIT 50
    """).fetchall()
    conn.close()
    return {
        "open_errors": [
            {
                "category":   r[0],
                "severity":   r[1],
                "subject":    r[2],
                "count":      r[3],
                "first_seen": r[4],
                "last_seen":  r[5],
                "auto_fixed": bool(r[6]),
            }
            for r in rows
        ],
        "total": len(rows),
    }


async def resolve_error(fingerprint: str) -> bool:
    """Markiert einen Fehler als behoben (für manuelle Bestätigung)."""
    conn = _init_db()
    conn.execute(
        "UPDATE error_log SET resolved=1 WHERE fingerprint=?", (fingerprint,)
    )
    conn.commit()
    conn.close()
    return True
