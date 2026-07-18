#!/usr/bin/env python3
"""
Email Inbox Monitor — alle 5 Minuten: Eingang UND Ausgang überwachen
====================================================================
Scannt Gmail IMAP alle 5 Minuten auf neue ungelesene E-Mails.
Kategorisiert: Bestellung, Anfrage, Antwort, Bounce, Spam.
Sendet Telegram-Alert bei neuen wichtigen Emails.
Speichert History in SQLite.
"""

from __future__ import annotations

import asyncio
import email as email_lib
import imaplib
import logging
import os
import re
import sqlite3
import time
from email.header import decode_header as _dh
from pathlib import Path
from typing import Dict, List

import aiohttp

log = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "data" / "inbox_monitor.db"

# Kategorisierungs-Signale
_CATEGORY_RULES = [
    ("bestellung",  ["zahlung", "payment", "order", "kauf", "stripe", "checkout", "invoice", "rechnung", "subscription"]),
    ("anfrage",     ["anfrage", "interest", "ich hätte", "ich würde", "would like", "information", "interested", "kontakt"]),
    ("antwort",     ["re:", "aw:", "antwort", "reply", "danke", "thank", "vielen dank", "verstanden"]),
    ("bounce",      ["mailer-daemon", "delivery failed", "undeliverable", "failed to deliver", "bounced", "non-delivery"]),
    ("pinterest",   ["pinterest.com", "pinterest api", "domain claim", "domain verify", "p:domain_verify"]),
    ("api_alert",   ["openai.com", "resend.com", "anthropic.com", "api key", "access denied", "unauthorized", "api access"]),
    ("spam",        ["unsubscribe", "casino", "crypto", "bitcoin", "invest now", "million dollar", "click here"]),
]

# Pinterest-Email-Patterns
_PINTEREST_VERIFY_RE = re.compile(r'content="([A-Za-z0-9_-]{10,})"', re.IGNORECASE)
_PINTEREST_CODE_RE   = re.compile(r'verification.*?(?:code|token)[:\s]+([A-Za-z0-9_-]{8,})', re.IGNORECASE)


def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inbox_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uid         TEXT UNIQUE,
            account     TEXT,
            sender      TEXT,
            subject     TEXT,
            category    TEXT,
            seen_at     INTEGER,
            alerted     INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def _decode_str(s: str) -> str:
    parts = []
    for chunk, enc in _dh(s or ""):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return " ".join(parts).strip()


def _categorize(subject: str, sender: str) -> str:
    text = (subject + " " + sender).lower()
    for cat, signals in _CATEGORY_RULES:
        if any(sig in text for sig in signals):
            return cat
    return "sonstige"


def _imap_accounts() -> list:
    accounts = []
    user1 = os.getenv("GMAIL_USER_BULLPOWER", "bullpowersrtkennels@gmail.com")
    pass1 = os.getenv("GMAIL_APP_PASSWORD_BULLPOWER", "")
    if user1 and pass1:
        accounts.append({"user": user1, "password": pass1, "label": "BullPower"})
    user2 = os.getenv("GMAIL_USER_PERSONAL", os.getenv("EMAIL_FROM", ""))
    pass2 = os.getenv("GMAIL_APP_PASSWORD_PERSONAL", os.getenv("EMAIL_PASSWORD", ""))
    if user2 and pass2 and user2 != user1:
        accounts.append({"user": user2, "password": pass2, "label": "Personal"})
    return accounts


def _extract_body(msg: email_lib.message.Message) -> str:
    """Extrahiert plain-text body (max 2000 Zeichen)."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body += part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass
            if len(body) > 2000:
                break
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            pass
    return body[:2000]


def _scan_inbox(account: dict, conn: sqlite3.Connection) -> List[Dict]:
    new_emails = []
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(account["user"], account["password"])
        imap.select("INBOX")

        _, data = imap.search(None, "UNSEEN")
        uid_list = data[0].split() if data[0] else []

        for uid_bytes in uid_list[-30:]:
            uid = uid_bytes.decode()
            already = conn.execute("SELECT id FROM inbox_log WHERE uid=?", (uid,)).fetchone()
            if already:
                continue

            # Für Pinterest/API-Emails: vollständige Email + Body holen
            _, msg_data = imap.fetch(uid_bytes, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue

            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else b""
            msg = email_lib.message_from_bytes(raw)
            sender  = _decode_str(msg.get("From", ""))
            subject = _decode_str(msg.get("Subject", "(kein Betreff)"))
            cat     = _categorize(subject, sender)
            body    = _extract_body(msg)

            conn.execute(
                "INSERT OR IGNORE INTO inbox_log (uid, account, sender, subject, category, seen_at) "
                "VALUES (?,?,?,?,?,?)",
                (uid, account["label"], sender[:200], subject[:300], cat, int(time.time()))
            )
            conn.commit()
            new_emails.append({
                "uid":      uid,
                "account":  account["label"],
                "sender":   sender,
                "subject":  subject,
                "category": cat,
                "body":     body,
            })

        imap.logout()
    except imaplib.IMAP4.error as e:
        log.warning("IMAP Fehler [%s]: %s", account.get("label"), e)
    except Exception as e:
        log.error("inbox_scan [%s]: %s", account.get("label"), e)
    return new_emails


async def _tg_send(text: str) -> None:
    token   = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text[:4096], "parse_mode": "HTML",
                      "disable_web_page_preview": True},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram send Fehler: %s", e)


def _build_pinterest_alert(email_data: dict) -> str:
    """Baut spezielle Pinterest-Alert-Nachricht mit Verification-Code-Extraktion."""
    subject = email_data["subject"]
    body    = email_data.get("body", "")
    sender  = email_data["sender"]

    lines = [f"📌 <b>Pinterest Email</b> [{email_data['account']}]",
             f"<b>Von:</b> {sender[:80]}",
             f"<b>Betreff:</b> {subject[:100]}"]

    # Verification-Code suchen
    code = None
    m = _PINTEREST_VERIFY_RE.search(body)
    if m:
        code = m.group(1)
    elif "domain" in subject.lower() or "verify" in subject.lower():
        m2 = _PINTEREST_CODE_RE.search(body)
        if m2:
            code = m2.group(1)

    if code:
        lines.append(f"\n🔑 <b>Domain-Verify-Code:</b> <code>{code}</code>")
        lines.append("→ Ausführen:")
        lines.append(f'<code>curl -X POST https://supermegabot-production.up.railway.app/api/pinterest/verify-domain -H "Content-Type: application/json" -d \'{{"code":"{code}"}}\' </code>')

    # API approved/rejected
    body_lower = body.lower()
    if any(w in body_lower for w in ["approved", "approval granted", "access granted"]):
        lines.append("\n✅ <b>Pinterest API APPROVED!</b>")
        lines.append("→ Neuen Token: developers.pinterest.com → rodibot → Generate Access Token")
        lines.append("→ Dann: railway variables set PINTEREST_ACCESS_TOKEN=&lt;token&gt;")
    elif any(w in body_lower for w in ["rejected", "denied", "declined", "not approved", "disapproved"]):
        lines.append("\n❌ <b>Pinterest API ABGELEHNT</b>")
        lines.append("→ Appeal: api-support@pinterest.com")

    # Body-Excerpt
    if body:
        excerpt = body[:300].replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"\n<i>{excerpt}...</i>")

    return "\n".join(lines)


async def _tg_alert(emails: List[Dict], session: aiohttp.ClientSession):
    token   = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return

    # Pinterest-Emails einzeln und detailliert melden
    for e in emails:
        if e["category"] == "pinterest":
            msg = _build_pinterest_alert(e)
            try:
                await session.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML",
                          "disable_web_page_preview": True},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
            except Exception as exc:
                log.warning("Pinterest alert send: %s", exc)
            await asyncio.sleep(0.3)

    # Restliche Emails gruppieren
    other = [e for e in emails if e["category"] not in ("pinterest", "spam")]
    if not other:
        return

    by_cat: Dict[str, List] = {}
    for e in other:
        by_cat.setdefault(e["category"], []).append(e)

    emoji_map = {
        "bestellung": "💰",
        "anfrage":    "📩",
        "antwort":    "↩️",
        "bounce":     "❌",
        "api_alert":  "🔑",
        "sonstige":   "📧",
    }

    lines = ["📬 <b>Neue Emails</b>\n"]
    for cat, items in by_cat.items():
        emoji = emoji_map.get(cat, "📧")
        lines.append(f"{emoji} <b>{cat.upper()}</b> ({len(items)})")
        for e in items[:3]:
            sender_short = e["sender"][:40].split("<")[0].strip()
            subject_short = e["subject"][:60].replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"  • [{e['account']}] {sender_short}")
            lines.append(f"    <i>{subject_short}</i>")
        if len(items) > 3:
            lines.append(f"  <i>...und {len(items)-3} weitere</i>")

    text = "\n".join(lines)
    try:
        await session.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=aiohttp.ClientTimeout(total=10),
        )
    except Exception as e:
        log.warning("Telegram Alert Fehler: %s", e)


async def run_inbox_monitor() -> Dict:
    """Scannt alle Gmail-Postfächer auf neue Emails, schickt Telegram-Alert + Auto-Reply."""
    conn     = _db()
    accounts = _imap_accounts()
    if not accounts:
        conn.close()
        return {"ok": False, "reason": "no_gmail_accounts"}

    all_new: List[Dict] = []
    for acc in accounts:
        new = _scan_inbox(acc, conn)
        all_new.extend(new)

    conn.close()

    # Nur bei neuen, nicht-spam Emails alarmieren
    alert_emails = [e for e in all_new if e["category"] != "spam"]
    if alert_emails:
        async with aiohttp.ClientSession() as session:
            await _tg_alert(alert_emails, session)

    # Auto-Responder DEAKTIVIERT (per Rudolf Sarkany, 2026-07-13)
    responder_result: Dict = {}

    # ── Bounce Auto-Fix: sofort nach Erkennen korrigieren ────────────────────
    bounce_emails = [e for e in all_new if e["category"] == "bounce"]
    bounce_fixed = 0
    if bounce_emails:
        try:
            from modules.email_bounce_fixer import run_bounce_fix_cycle
            fix_result = await run_bounce_fix_cycle()
            bounce_fixed = fix_result.get("fixed", 0)
            log.info("Bounce Auto-Fix: %d gefixed", bounce_fixed)
        except Exception as exc:
            log.error("Bounce Auto-Fix Fehler: %s", exc)

    log.info(
        "Inbox Monitor: %d Konten, %d neu (%d Alerts, %d Bounces gefixed)",
        len(accounts), len(all_new), len(alert_emails), bounce_fixed
    )
    return {
        "ok":         True,
        "accounts":   len(accounts),
        "new_total":  len(all_new),
        "alerted":    len(alert_emails),
        "auto_replied": responder_result.get("replied", 0),
        "bounces_fixed": bounce_fixed,
        "by_category": {
            cat: sum(1 for e in all_new if e["category"] == cat)
            for cat in set(e["category"] for e in all_new)
        },
    }


async def get_inbox_summary(limit: int = 50) -> Dict:
    """Letzte N eingehende Emails für Dashboard."""
    conn = _db()
    rows = conn.execute(
        "SELECT uid, account, sender, subject, category, seen_at FROM inbox_log "
        "ORDER BY seen_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return {
        "emails": [
            {"uid": r[0], "account": r[1], "sender": r[2],
             "subject": r[3], "category": r[4], "ts": r[5]}
            for r in rows
        ]
    }


# ── API-Key Health Check ──────────────────────────────────────────────────────

async def run_api_key_health_check() -> str:
    """Prüft kritische API-Keys auf Gültigkeit. Schickt Telegram-Alert bei kaputten Keys."""
    checks = [
        {
            "name": "OpenAI",
            "key":  os.getenv("OPENAI_API_KEY", ""),
            "url":  "https://api.openai.com/v1/models",
            "method": "GET",
            "auth": "Bearer",
            "renew": "https://platform.openai.com/api-keys",
        },
        {
            "name": "Resend",
            "key":  os.getenv("RESEND_API_KEY", ""),
            "url":  "https://api.resend.com/domains",
            "method": "GET",
            "auth": "Bearer",
            "renew": "https://resend.com/api-keys",
        },
        {
            "name": "Resend-2",
            "key":  os.getenv("RESEND_API_KEY_2", ""),
            "url":  "https://api.resend.com/domains",
            "method": "GET",
            "auth": "Bearer",
            "renew": "https://resend.com/api-keys",
        },
        {
            "name": "Anthropic",
            "key":  os.getenv("ANTHROPIC_API_KEY", ""),
            "url":  "https://api.anthropic.com/v1/messages",
            "method": "POST",
            "auth": "x-api-key",
            "renew": "https://console.anthropic.com/",
        },
        {
            "name": "OpenRouter",
            "key":  os.getenv("OPENROUTER_API_KEY", ""),
            "url":  "https://openrouter.ai/api/v1/models",
            "method": "GET",
            "auth": "Bearer",
            "renew": "https://openrouter.ai/settings/keys",
        },
    ]

    broken = []
    ok_list = []

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
        for check in checks:
            if not check["key"]:
                broken.append(check)
                continue
            try:
                if check["method"] == "POST":
                    # Anthropic: minimal test-call
                    resp = await session.post(
                        check["url"],
                        headers={"x-api-key": check["key"],
                                 "anthropic-version": "2023-06-01",
                                 "content-type": "application/json"},
                        json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1,
                              "messages": [{"role": "user", "content": "hi"}]},
                    )
                else:
                    resp = await session.get(
                        check["url"],
                        headers={"Authorization": f"{check['auth']} {check['key']}"},
                    )
                # 200, 400 (bad request but auth OK), 429 (rate limited = auth OK)
                if resp.status in (200, 400, 429):
                    ok_list.append(check["name"])
                else:
                    broken.append(check)
            except Exception:
                broken.append(check)

    if broken:
        lines = ["🔑 <b>API-Key Alert — Renewal nötig!</b>"]
        for item in broken:
            name = item["name"]
            renew = item.get("renew", "?")
            lines.append(f"❌ <b>{name}</b>: Key ungültig oder fehlt")
            lines.append(f"   → Erneuern: <code>{renew}</code>")
        await _tg_send("\n".join(lines))

    return f"API Health: {len(ok_list)} OK {ok_list}, {len(broken)} kaputt ({[b['name'] for b in broken]})"


# ── Scheduler-Alias ──────────────────────────────────────────────────────────

async def run_email_monitor() -> str:
    """Alias für Scheduler — ruft run_inbox_monitor() auf."""
    result = await run_inbox_monitor()
    return (
        f"Email Monitor: {result.get('accounts', 0)} Konten, "
        f"{result.get('new_total', 0)} neu, "
        f"{result.get('alerted', 0)} Alerts"
    )
