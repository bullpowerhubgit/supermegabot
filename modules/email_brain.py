#!/usr/bin/env python3
"""EmailBrain — IMAP-Monitoring + Konto-Health für alle Gmail-Konten."""
from __future__ import annotations

import email
import imaplib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import aiohttp

from modules.gmail_accounts import configured_accounts, list_accounts, test_all_accounts

log = logging.getLogger("EmailBrain")

STATE_FILE = Path(__file__).parent.parent / "data" / "email_brain_state.json"
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            import json
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"seen_ids": {}}


def _save_state(state: dict) -> None:
    import json
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _check_imap(account, seen_ids: List[str]) -> List[dict]:
    alerts = []
    if not account.password:
        return alerts
    try:
        mail = imaplib.IMAP4_SSL(account.imap_host, 993)
        mail.login(account.email, account.password.replace(" ", ""))
        mail.select("INBOX")
        _, data = mail.search(None, "UNSEEN")
        ids = data[0].split() if data[0] else []
        for uid in ids[-20:]:
            uid_str = uid.decode()
            if uid_str in seen_ids:
                continue
            _, msg_data = mail.fetch(uid, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            alerts.append({
                "account": account.email,
                "sender": (msg.get("From") or "")[:80],
                "subject": (msg.get("Subject") or "")[:100],
            })
            seen_ids.append(uid_str)
        mail.logout()
    except Exception as e:
        log.warning("IMAP %s: %s", account.email, e)
    return alerts


async def check_and_process_emails() -> Dict[str, Any]:
    """IMAP-Poll aller konfigurierten Konten."""
    state = _load_state()
    seen: Dict[str, List[str]] = state.setdefault("seen_ids", {})
    all_alerts: List[dict] = []
    checked = 0

    for acc in configured_accounts():
        key = acc.email
        ids = seen.setdefault(key, [])
        alerts = _check_imap(acc, ids)
        if alerts:
            all_alerts.extend(alerts)
        checked += 1
        seen[key] = ids[-200:]

    state["last_check"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    return {
        "ok": True,
        "checked": checked,
        "new_messages": len(all_alerts),
        "alerts": all_alerts[:20],
        "replied": 0,
    }


async def send_daily_summary() -> Dict[str, Any]:
    """Tägliche Konto-Zusammenfassung → Telegram."""
    health = test_all_accounts()
    working = [a for a in health["accounts"] if a.get("ok")]
    broken = [a for a in health["accounts"] if not a.get("ok")]

    lines = [
        f"📧 EmailBrain — {health['working']}/{health['total']} Konten OK",
        f"Konfiguriert: {health['configured']}/{health['total']}",
    ]
    for a in working:
        lines.append(f"✅ {a['email']}")
    for a in broken:
        err = a.get("error", "?")
        lines.append(f"{'⏳' if err == 'no_password' else '❌'} {a['email']}: {err}")

    text = "\n".join(lines)
    if TG_TOKEN and TG_CHAT:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                await s.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    json={"chat_id": TG_CHAT, "text": text[:4096]},
                )
        except Exception as e:
            log.warning("Telegram summary: %s", e)

    return {"ok": True, "summary": health, "telegram_sent": bool(TG_TOKEN and TG_CHAT)}


async def setup_accounts() -> Dict[str, Any]:
    """Health-Check aller Konten (API + Scheduler)."""
    return test_all_accounts()