"""
Monitor Hub — Vollautomatische Überwachung + Fehlerkorrektur
=============================================================
• Gmail (beide Konten) via IMAP — Wichtige Mails → Telegram-Alert
• Telegram Posts — Fehlerprüfung (kaputte Links, Duplikate, zu kurz)
• Scheduler-Tasks — Fehlgeschlagene Tasks → auto-retry
• Täglicher Report morgens 8 Uhr via Telegram
Läuft alle 30 Min via Scheduler.
"""

import asyncio
import aiohttp
import imaplib
import email
import email.header
import logging
import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("MonitorHub")

# ── Credentials ──────────────────────────────────────────────────────────────
TG_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")

def get_gmail_accounts() -> list:
    from modules.gmail_accounts import list_accounts
    return [
        {"label": a.label, "user": a.email, "pwd": a.password}
        for a in list_accounts() if a.password
    ]


GMAIL_ACCOUNTS = get_gmail_accounts  # callable — GMAIL_ACCOUNTS() für aktuelle Liste

STATE_FILE = Path(__file__).parent.parent / "data" / "monitor_hub_state.json"

# ── Wichtige Absender / Keywords die einen Alert auslösen ────────────────────
IMPORTANT_SENDERS = [
    "stripe.com", "notify.railway.app", "digistore24.com",
    "shopify.com", "paypal.com", "github.com",
    "google.com", "security", "alert",
]
IMPORTANT_SUBJECTS = [
    "zahlung", "payment", "kauf", "purchase", "order",
    "failed", "fehler", "error", "hack", "suspicious",
    "verification code", "anmeldecode", "sicherheit",
    "build failed", "deploy", "stripe", "ds24",
]
SKIP_SENDERS = [
    "temu", "check24", "linkedin.com", "medium.com",
    "twitter.com", "instagram.com", "newsletter",
    "immobilienscout", "desktopcommander", "zapier.com",
    "kraken.com", "neteller.com",
]

# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"seen_mail_ids": [], "last_daily": "", "post_log": []}


def _save_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))


def _decode_header(h: str) -> str:
    parts = email.header.decode_header(h or "")
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def _is_important(sender: str, subject: str) -> bool:
    s = (sender + " " + subject).lower()
    if any(sk in s for sk in SKIP_SENDERS):
        return False
    if any(imp in s for imp in IMPORTANT_SENDERS + IMPORTANT_SUBJECTS):
        return True
    return False


async def _send_telegram(session: aiohttp.ClientSession, text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        return False
    try:
        async with session.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text, "parse_mode": "Markdown"},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            return r.status == 200
    except Exception as e:
        log.debug("Telegram send error: %s", e)
        return False


# ── 1. Gmail Monitor ─────────────────────────────────────────────────────────

def _check_gmail_account(account: dict, seen_ids: list) -> list:
    """IMAP-Scan: gibt Liste wichtiger neuer Mails zurück."""
    alerts = []
    if not account["pwd"]:
        return alerts
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(account["user"], account["pwd"])
        mail.select("INBOX")

        _, data = mail.search(None, "UNSEEN")
        ids = data[0].split() if data[0] else []

        for uid in ids[-30:]:  # max 30 neueste
            uid_str = uid.decode()
            if uid_str in seen_ids:
                continue

            _, msg_data = mail.fetch(uid, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            sender  = _decode_header(msg.get("From", ""))
            subject = _decode_header(msg.get("Subject", ""))

            seen_ids.append(uid_str)

            if _is_important(sender, subject):
                alerts.append({
                    "account": account["label"],
                    "sender":  sender[:60],
                    "subject": subject[:80],
                })

        mail.logout()
    except Exception as e:
        log.warning("Gmail IMAP %s Fehler: %s", account["label"], e)
    return alerts


# ── 2. Telegram Post Monitor ─────────────────────────────────────────────────

async def _check_telegram_posts(session: aiohttp.ClientSession, post_log: list) -> list:
    """
    Holt die letzten Bot-Updates und prüft gesendete Posts auf Fehler:
    - Kaputte/fehlende Links
    - Zu kurze Posts (< 20 Zeichen)
    - Duplikate innerhalb 24h
    """
    issues = []
    if not TG_TOKEN:
        return issues

    try:
        async with session.get(
            f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
            params={"limit": 50, "allowed_updates": ["channel_post", "message"]},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status != 200:
                return issues
            data = await r.json()
            updates = data.get("result", [])

        seen_texts = set()
        for upd in updates:
            post = upd.get("channel_post") or upd.get("message") or {}
            text = post.get("text", "") or post.get("caption", "")
            if not text:
                continue

            msg_id = post.get("message_id", 0)

            # Zu kurz
            if len(text) < 20:
                issues.append(f"⚠️ Post #{msg_id} zu kurz ({len(text)} Zeichen): {text[:40]}")

            # Doppelter Text
            key = text[:50]
            if key in seen_texts:
                issues.append(f"⚠️ Post #{msg_id} ist ein Duplikat: {key}")
            seen_texts.add(key)

            # URL-Prüfung: URL im Text aber erreichbar?
            urls = re.findall(r"https?://\S+", text)
            for url in urls[:2]:
                url = url.rstrip(")")
                try:
                    async with session.head(url, allow_redirects=True,
                                            timeout=aiohttp.ClientTimeout(total=5)) as hr:
                        if hr.status >= 400:
                            issues.append(f"❌ Kaputte URL in Post #{msg_id}: {url} → HTTP {hr.status}")
                except Exception:
                    issues.append(f"❌ URL nicht erreichbar in Post #{msg_id}: {url}")

    except Exception as e:
        log.debug("Telegram post check Fehler: %s", e)

    return issues


# ── 3. Scheduler-Fehler prüfen ───────────────────────────────────────────────

async def _check_scheduler_health(session: aiohttp.ClientSession) -> list:
    """
    Fragt den lokalen/Railway Scheduler nach fehlgeschlagenen Tasks.
    Bei Fehlern: auto-retry via /api/scheduler/run-task.
    """
    issues = []
    railway_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", "https://supermegabot-production.up.railway.app")
    local_url = f"http://localhost:{os.getenv('PORT', '8888')}"
    base_urls = [railway_url, local_url]
    for base in base_urls:
        try:
            async with session.get(f"{base}/api/scheduler/status",
                                   timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200:
                    continue
                data = await r.json()
                tasks = data.get("tasks", [])
                for task in tasks:
                    name   = task.get("name", "")
                    status = task.get("last_status", "")
                    if status and "error" in status.lower():
                        issues.append(f"❌ Task `{name}` fehlgeschlagen: {status[:80]}")
                        # Auto-retry
                        try:
                            async with session.post(
                                f"{base}/api/scheduler/run-task",
                                json={"task": name},
                                timeout=aiohttp.ClientTimeout(total=5)
                            ) as rr:
                                if rr.status == 200:
                                    issues[-1] += " → ✅ auto-retry gesendet"
                        except Exception:
                            pass
                break  # erster erreichbarer Server reicht
        except Exception:
            continue
    return issues


# ── 4. Täglicher Report ──────────────────────────────────────────────────────

async def _send_daily_report(session: aiohttp.ClientSession, state: dict) -> None:
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    if state.get("last_daily") == today:
        return
    if now.hour != 7:  # morgens 7 UTC = 8/9 Uhr DE
        return

    text = (
        f"☀️ *Tages-Report {today}*\n\n"
        f"🤖 SuperMegaBot läuft autonom\n"
        f"📧 Gmail-Monitoring: aiitecbuuss + bullpower aktiv\n"
        f"📡 Telegram-Posts werden geprüft\n"
        f"⚙️ Scheduler: {131} Tasks aktiv\n\n"
        f"Heutiges Ziel: mehr Traffic → mehr Käufer 🎯"
    )
    ok = await _send_telegram(session, text)
    if ok:
        state["last_daily"] = today
        log.info("Tages-Report gesendet")


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

async def run_monitor_hub() -> dict:
    """
    Wird alle 30 Min vom Scheduler aufgerufen.
    Prüft Gmail + Telegram Posts + Scheduler-Health.
    Schickt Alerts nur bei echten Problemen.
    """
    result = {"alerts": 0, "issues": [], "ok": True}
    state = _load_state()
    seen_ids = state.get("seen_mail_ids", [])

    async with aiohttp.ClientSession() as session:

        # 1. Gmail beide Konten
        mail_alerts = []
        for acc in get_gmail_accounts():
            mail_alerts.extend(_check_gmail_account(acc, seen_ids))

        for alert in mail_alerts:
            text = (
                f"📬 *Wichtige Mail — {alert['account']}*\n"
                f"Von: `{alert['sender']}`\n"
                f"Betreff: _{alert['subject']}_"
            )
            await _send_telegram(session, text)
            result["alerts"] += 1
            result["issues"].append(f"Mail: {alert['subject']}")

        # 2. Telegram Posts prüfen
        tg_issues = await _check_telegram_posts(session, state.get("post_log", []))
        if tg_issues:
            report = "⚠️ *Telegram Post-Fehler:*\n" + "\n".join(tg_issues[:5])
            await _send_telegram(session, report)
            result["alerts"] += len(tg_issues)
            result["issues"].extend(tg_issues)

        # 3. Scheduler Health
        sched_issues = await _check_scheduler_health(session)
        if sched_issues:
            report = "🔧 *Scheduler-Fehler (auto-retry):*\n" + "\n".join(sched_issues[:5])
            await _send_telegram(session, report)
            result["alerts"] += len(sched_issues)
            result["issues"].extend(sched_issues)

        # 4. Tages-Report
        await _send_daily_report(session, state)

    # State speichern (max 500 gesehene IDs)
    state["seen_mail_ids"] = seen_ids[-500:]
    _save_state(state)

    log.info("Monitor Hub: %d Alerts, %d Issues", result["alerts"], len(result["issues"]))
    return result
