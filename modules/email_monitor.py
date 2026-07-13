#!/usr/bin/env python3
"""
E-Mail Monitor — prüft Gmail alle 5 Minuten auf wichtige Mails.
Wichtige Mails → sofort Telegram-Benachrichtigung.
Kategorien: Bestellungen, Ablehnungen, Fehler, B2B-Antworten, Zahlungen.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
log = logging.getLogger("EmailMonitor")

TG_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
GMAIL_USER = os.getenv("GMAIL_USER", "bullpowersrtkennels@gmail.com")

STATE_FILE = Path(__file__).parent.parent / "data" / "email_monitor_state.json"

# ── Wichtigkeits-Filter ───────────────────────────────────────────────
CRITICAL_SENDERS = [
    "stripe.com", "notify.railway.app", "github.com",
    "shop.tiktok.com", "digistore24.com", "shopify.com",
    "paypal.com", "netlify.com", "anthropic.com",
]

CRITICAL_SUBJECTS = [
    "zahlung", "payment", "bestellung", "order", "kauf", "purchase",
    "abgelehnt", "rejected", "failed", "fehler", "error", "build failed",
    "abonnement", "subscription", "stripe", "invoice", "rechnung",
    "verifizier", "verify", "kündigung", "cancel", "chargeback",
    "antwort", "reply", "interesse", "anfrage", "inquiry",
    "railway", "deploy", "webhook",
]

IGNORE_SENDERS = [
    "eventim.de", "temuemail.com", "etoro.com", "kraken.com",
    "bitpanda.com", "alibaba.com", "tcm-sec.com", "rundown.ai",
    "positivepsychology.com", "salesangels.org",
]

PRIORITY_EMOJI = {
    "stripe":      "💰",
    "railway":     "🚂",
    "github":      "🐙",
    "tiktok":      "🎵",
    "digistore":   "🛒",
    "shopify":     "📦",
    "zahlung":     "💶",
    "bestellung":  "📬",
    "abgelehnt":   "❌",
    "failed":      "🔴",
    "fehler":      "⚠️",
    "abonnement":  "🔄",
    "default":     "📧",
}


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_check": 0, "seen_ids": [], "stats": {"total_checked": 0, "alerts_sent": 0}}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _is_important(sender: str, subject: str) -> tuple[bool, str]:
    sender_l  = sender.lower()
    subject_l = subject.lower()

    for ignore in IGNORE_SENDERS:
        if ignore in sender_l:
            return False, ""

    for s in CRITICAL_SENDERS:
        if s in sender_l:
            emoji = next((v for k, v in PRIORITY_EMOJI.items() if k in sender_l), PRIORITY_EMOJI["default"])
            return True, emoji

    for kw in CRITICAL_SUBJECTS:
        if kw in subject_l:
            emoji = next((v for k, v in PRIORITY_EMOJI.items() if k in subject_l or k in sender_l), PRIORITY_EMOJI["default"])
            return True, emoji

    return False, ""


async def _fetch_unread_since(since_ts: int, session: aiohttp.ClientSession) -> list[dict]:
    """Liest neue ungelesene Mails via Gmail API (IMAP-Alternative)."""
    gmail_user = GMAIL_USER
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", os.getenv("GMAIL_PASSWORD", ""))

    if not gmail_pass:
        log.warning("GMAIL_APP_PASSWORD nicht gesetzt — nutze IMAP-Fallback")
        return []

    try:
        import imaplib
        import email as email_lib
        from email.header import decode_header

        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(gmail_user, gmail_pass)
        mail.select("INBOX")

        # Suche nach ungelesenen Mails von heute
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(UNSEEN SINCE "{today}")')
        mail_ids = data[0].split() if data[0] else []

        results = []
        for mid in mail_ids[-20:]:  # Max 20 neueste
            _, msg_data = mail.fetch(mid, "(RFC822.HEADER)")
            raw = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw)

            subject_parts = decode_header(msg.get("Subject", ""))
            subject = ""
            for part, enc in subject_parts:
                if isinstance(part, bytes):
                    subject += part.decode(enc or "utf-8", errors="replace")
                else:
                    subject += str(part)

            sender = msg.get("From", "")
            date   = msg.get("Date", "")
            msg_id = msg.get("Message-ID", str(mid))

            results.append({
                "id":      msg_id,
                "sender":  sender,
                "subject": subject,
                "date":    date,
                "snippet": "",
            })

        mail.logout()
        return results
    except Exception as e:
        log.error("IMAP Fehler: %s", e)
        return []


async def _tg(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


async def check_emails_once() -> dict:
    """Einmalige Mail-Prüfung — gibt wichtige neue Mails zurück."""
    state = _load_state()
    now   = int(time.time())
    seen  = set(state.get("seen_ids", []))

    async with aiohttp.ClientSession() as session:
        mails = await _fetch_unread_since(state["last_check"], session)

    important = []
    for m in mails:
        mid = m.get("id", "")
        if mid in seen:
            continue
        seen.add(mid)

        is_imp, emoji = _is_important(m.get("sender", ""), m.get("subject", ""))
        if is_imp:
            important.append({**m, "emoji": emoji})

    # Alerts senden
    for m in important:
        msg = (
            f"{m['emoji']} *Neue wichtige Mail*\n"
            f"Von: `{m['sender'][:60]}`\n"
            f"Betreff: *{m['subject'][:80]}*\n"
            f"Zeit: {m['date'][:25] if m['date'] else '—'}"
        )
        await _tg(msg)
        log.info("Alert: %s — %s", m["sender"], m["subject"])

    # State speichern
    seen_list = list(seen)[-500:]  # Max 500 IDs merken
    state.update({
        "last_check": now,
        "seen_ids": seen_list,
        "stats": {
            "total_checked": state.get("stats", {}).get("total_checked", 0) + len(mails),
            "alerts_sent":   state.get("stats", {}).get("alerts_sent", 0) + len(important),
            "last_run":      now,
        }
    })
    _save_state(state)

    return {
        "ok":        True,
        "checked":   len(mails),
        "important": len(important),
        "alerts":    [f"{m['emoji']} {m['subject'][:50]}" for m in important],
    }


async def run_email_monitor_loop(interval_seconds: int = 300):
    """Dauerhafter Loop: alle 5 Minuten prüfen."""
    log.info("E-Mail Monitor gestartet (alle %ds)", interval_seconds)
    while True:
        try:
            result = await check_emails_once()
            if result.get("important", 0) > 0:
                log.info("Neue wichtige Mails: %d", result["important"])
            else:
                log.debug("Keine neuen wichtigen Mails")
        except Exception as e:
            log.error("Monitor-Fehler: %s", e)
        await asyncio.sleep(interval_seconds)


async def get_status() -> dict:
    state = _load_state()
    return {
        "gmail": GMAIL_USER,
        "last_check": state.get("stats", {}).get("last_run", 0),
        "total_checked": state.get("stats", {}).get("total_checked", 0),
        "total_alerts": state.get("stats", {}).get("alerts_sent", 0),
        "seen_count": len(state.get("seen_ids", [])),
        "interval": "5 Minuten",
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_email_monitor_loop())
