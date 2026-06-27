"""
EmailBrain — Vollautonomes Email-Management für alle 7 Konten.

Konten:
  dragonadnp@gmail.com         (Sarkany Timea)
  nikolestimi@gmail.com
  bullpowersrtkennels@gmail.com
  looopwave@gmail.com
  aitecbuuss@gmail.com
  rudolf.sarkany@aitec.de      (custom domain — IMAP_HOST_6 konfigurierbar)
  rudolf.sarkany.aiitec@gmail.com
  rudolfsarkany1984@gmail.com      (LinkedIn-Konto)

Env-Vars Schema:
  GMAIL_USER_1 … GMAIL_USER_8
  GMAIL_APP_PASSWORD_1 … GMAIL_APP_PASSWORD_7
  GMAIL_DISPLAY_NAME_1 … GMAIL_DISPLAY_NAME_7   (optional)
  IMAP_HOST_1 … IMAP_HOST_7                     (optional, default: imap.gmail.com)
  SMTP_HOST_1 … SMTP_HOST_7                     (optional, default: smtp.gmail.com)
"""

from __future__ import annotations

import asyncio
import email
import imaplib
import json
import logging
import os
import smtplib
import ssl
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from pathlib import Path
from typing import Any

import aiohttp

log = logging.getLogger("EmailBrain")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

REPLIED_FILE = DATA_DIR / "email_replied_ids.json"
STATS_FILE   = DATA_DIR / "email_stats.json"

# ── Account config ────────────────────────────────────────────────────────────

# Default display names per known address
_DEFAULT_NAMES = {
    "dragonadnp@gmail.com":              "Sarkany Timea",
    "nikolestimi@gmail.com":             "Nikole Stimi",
    "bullpowersrtkennels@gmail.com":     "Rudolf Sarkany — BullPower Hub",
    "looopwave@gmail.com":               "Loopwave — BullPower Hub",
    "aiitecbuuss@gmail.com":             "AIITEC — BullPower Hub",
    "rudolf.sarkany@aitec.de":           "Rudolf Sarkany — AIITEC",
    "rudolf.sarkany.aiitec@gmail.com":   "Rudolf Sarkany — AIITEC",
    "rudolfsarkany1984@gmail.com":       "Rudolf Sarkany",
}


def _accounts() -> list[dict]:
    """Return configured email accounts from GMAIL_USER_1..8, deduplicated by address."""
    seen: set = set()
    accounts = []
    for i in range(1, 9):
        user = os.getenv(f"GMAIL_USER_{i}", "").strip().lower()
        pw   = os.getenv(f"GMAIL_APP_PASSWORD_{i}", "").strip()
        if not user or not pw:
            continue
        if user in seen:
            continue  # skip duplicate accounts
        seen.add(user)
        name      = os.getenv(f"GMAIL_DISPLAY_NAME_{i}", _DEFAULT_NAMES.get(user, "Rudolf Sarkany"))
        imap_host = os.getenv(f"IMAP_HOST_{i}", "imap.gmail.com")
        smtp_host = os.getenv(f"SMTP_HOST_{i}", "smtp.gmail.com")
        accounts.append({
            "user": user,
            "password": pw,
            "name": name,
            "imap_host": imap_host,
            "smtp_host": smtp_host,
        })
    if not accounts:
        log.warning("No email accounts configured. Set GMAIL_USER_1..7 + GMAIL_APP_PASSWORD_1..7 in Railway.")
    return accounts


# ── IMAP helpers ──────────────────────────────────────────────────────────────

def _imap_connect(user: str, password: str, host: str = "imap.gmail.com") -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(host, 993)
    mail.login(user, password)
    return mail


def _fetch_unread(mail: imaplib.IMAP4_SSL, folder: str = "INBOX", limit: int = 20) -> list[dict]:
    mail.select(folder)
    _, data = mail.search(None, "UNSEEN")
    ids = (data[0].split() if data[0] else [])[-limit:]
    messages = []
    for uid in ids:
        _, raw = mail.fetch(uid, "(RFC822)")
        if not raw or not raw[0]:
            continue
        msg = email.message_from_bytes(raw[0][1])
        body = _extract_body(msg)
        messages.append({
            "uid":     uid.decode(),
            "from":    msg.get("From", ""),
            "to":      msg.get("To", ""),
            "subject": msg.get("Subject", "(kein Betreff)"),
            "date":    msg.get("Date", ""),
            "body":    body[:2000],
            "msg_id":  msg.get("Message-ID", ""),
        })
    return messages


def _extract_body(msg: email.message.Message) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="replace")
    return body.strip()


def _gmail_label(mail: imaplib.IMAP4_SSL, uid: str, label: str):
    """Apply a Gmail label (creates if missing)."""
    try:
        mail.uid("STORE", uid.encode(), "+X-GM-LABELS", f"({label})")
    except Exception:
        pass  # label may not exist — best-effort


def _gmail_archive(mail: imaplib.IMAP4_SSL, uid: str):
    """Archive = move out of INBOX (remove \\Inbox label)."""
    try:
        mail.uid("STORE", uid.encode(), "-X-GM-LABELS", "(\\Inbox)")
    except Exception:
        pass


# ── SMTP helper ───────────────────────────────────────────────────────────────

def _send_reply(sender_user: str, sender_pw: str, sender_name: str,
                to_addr: str, subject: str, body: str,
                in_reply_to: str = "", smtp_host: str = "smtp.gmail.com") -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = f"{sender_name} <{sender_user}>"
        msg["To"]      = to_addr
        msg["Subject"] = subject if subject.startswith("Re:") else f"Re: {subject}"
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"]  = in_reply_to
        msg.attach(MIMEText(body, "plain", "utf-8"))

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, 465, context=ctx) as server:
            server.login(sender_user, sender_pw)
            server.sendmail(sender_user, to_addr, msg.as_string())
        return True
    except Exception as e:
        log.error(f"SMTP send failed ({sender_user}): {e}")
        return False


# ── Claude classification ─────────────────────────────────────────────────────

SYSTEM_CLASSIFY = """Du bist ein Email-Assistent für Rudolf Sarkany (BullPower Hub, aiitec.online).
Klassifiziere die eingehende Email und entscheide ob und wie zu antworten ist.

Antworte NUR als JSON (kein Markdown):
{
  "category": "customer_inquiry|business|support|newsletter|spam|personal|order|payment|legal",
  "priority": "urgent|normal|low",
  "reply_needed": true/false,
  "reply_draft": "...",
  "label": "Priority|Newsletter|Spam|Business|Customer|Support|Order|Legal",
  "archive": true/false,
  "telegram_alert": true/false,
  "summary": "Kurze Zusammenfassung (1 Satz)"
}

Regeln für reply_draft:
- Professionell, kurz, auf Deutsch wenn Deutsch-Email, Englisch wenn Englisch
- Unterschrift: Rudolf Sarkany | BullPower Hub | aiitec.online
- Für Kundenanfragen: hilfreich + konkret
- Für Business: professionell, offen für Kooperation
- Für Newsletter/Spam: kein reply_draft nötig
- reply_needed=false für: Newsletter, Spam, automatische Bestätigungen, Notifications

Kontext über Rudolf:
- Betreibt E-Commerce SaaS: BullPower Hub / aiitec.online
- Produkte: Shopify Automation, SEO Tools, AI Tools
- Bankrott, sucht aktiv Kunden und Kooperationen
- Antwort-Ton: freundlich-professionell, lösungsorientiert"""


def _rule_classify(subject: str, sender: str, body: str) -> dict:
    """Rule-based fallback classifier — works without AI credits."""
    s = (subject + " " + body).lower()
    frm = sender.lower()

    # Definite NO-reply — includes newsletter subdomains like news.docmorris.de
    no_reply_signals = ["noreply", "no-reply", "donotreply", "newsletter", "unsubscribe",
                        "notification", "automated", "autoresponder", "bounce", "mailer-daemon",
                        "postmaster", "billing@", "invoice@", "receipt@", "order@",
                        "notification@", "alert@", "support@", "helpdesk@", "tickets@",
                        "@news.", "@mail.", "@mailings.", "@email.",
                        "@lists.", "@em.", "@sg.", "@em2.", "@reply."]
    # Also block support ticket confirmation subjects
    no_reply_subjects = ["we received your request", "your request has been received",
                         "ticket created", "ticket #", "support ticket", "case created",
                         "your case", "thanks for contacting", "thank you for contacting",
                         "support request id", "request id is"]
    if any(sig in frm for sig in no_reply_signals) or any(sig in s for sig in no_reply_subjects):
        return {"category": "newsletter", "priority": "low", "reply_needed": False,
                "reply_draft": "", "label": "Newsletter", "archive": True,
                "telegram_alert": False, "summary": subject[:80]}

    spam_words = ["unsubscribe", "opt out", "click here to unsubscribe", "newsletter",
                  "special offer", "act now", "limited time", "congratulations you won",
                  "free money", "100% guaranteed", "make money fast"]
    if sum(1 for w in spam_words if w in s) >= 2:
        return {"category": "spam", "priority": "low", "reply_needed": False,
                "reply_draft": "", "label": "Spam", "archive": True,
                "telegram_alert": False, "summary": subject[:80]}

    # Payment / order — high priority, alert
    if any(w in s for w in ["zahlung", "payment", "invoice", "rechnung", "bestellung",
                              "order confirmed", "purchase", "stripe", "paypal"]):
        return {"category": "payment", "priority": "urgent", "reply_needed": False,
                "reply_draft": "", "label": "Order", "archive": False,
                "telegram_alert": True, "summary": f"Zahlung/Bestellung: {subject[:60]}"}

    # Customer inquiry — needs reply
    inquiry_words = ["frage", "anfrage", "hilfe", "problem", "support", "question",
                     "help", "issue", "kann ich", "how do i", "wie kann", "kooperation",
                     "zusammenarbeit", "angebot", "partnership", "interested", "interessiert"]
    if any(w in s for w in inquiry_words):
        draft = (
            f"Hallo,\n\nvielen Dank für deine Nachricht!\n\n"
            f"Ich habe deine Anfrage erhalten und melde mich so schnell wie möglich bei dir.\n\n"
            f"Kurze Antwort auf deine Frage: Ja, wir können dir dabei helfen. "
            f"Schreib mir gerne mehr Details und wir finden die beste Lösung.\n\n"
            f"Beste Grüße,\nRudolf Sarkany | BullPower Hub | aiitec.online"
        )
        return {"category": "customer_inquiry", "priority": "normal", "reply_needed": True,
                "reply_draft": draft, "label": "Customer", "archive": False,
                "telegram_alert": False, "summary": f"Kundenanfrage: {subject[:60]}"}

    # Business / cooperation
    biz_words = ["business", "kooperation", "partnership", "collaboration", "proposal",
                 "offer", "deal", "angebot", "zusammenarbeit", "investor", "funding"]
    if any(w in s for w in biz_words):
        draft = (
            f"Hallo,\n\nvielen Dank für deine Nachricht und das Interesse an einer Zusammenarbeit!\n\n"
            f"Gerne möchte ich mehr Details erfahren. "
            f"Könntest du mir dein Angebot/deine Idee kurz näher beschreiben?\n\n"
            f"Ich freue mich auf deine Antwort.\n\n"
            f"Beste Grüße,\nRudolf Sarkany | BullPower Hub | aiitec.online"
        )
        return {"category": "business", "priority": "normal", "reply_needed": True,
                "reply_draft": draft, "label": "Business", "archive": False,
                "telegram_alert": True, "summary": f"Business: {subject[:60]}"}

    # Default — unknown but potentially important: alert via Telegram, don't auto-reply
    return {"category": "unknown", "priority": "normal", "reply_needed": False,
            "reply_draft": "", "label": "Priority", "archive": False,
            "telegram_alert": True, "summary": f"Unbekannte Email: {subject[:70]}"}


async def _classify_email(subject: str, sender: str, body: str) -> dict:
    # Try AI first
    try:
        from modules.ai_client import ai_complete
        raw = await ai_complete(
            f"Von: {sender}\nBetreff: {subject}\n\n{body[:800]}",
            system=SYSTEM_CLASSIFY, max_tokens=400
        )
        if raw:
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw)
            if isinstance(result, dict) and "category" in result:
                return result
    except Exception:
        pass

    # Rule-based fallback — always works even without AI credits
    return _rule_classify(subject, sender, body)


# ── Telegram ──────────────────────────────────────────────────────────────────

async def _tg(text: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


# ── Replied-ID guard ──────────────────────────────────────────────────────────

def _load_replied() -> set:
    try:
        return set(json.loads(REPLIED_FILE.read_text()))
    except Exception:
        return set()


def _save_replied(ids: set):
    REPLIED_FILE.write_text(json.dumps(list(ids)))


# ── Core: process one account ─────────────────────────────────────────────────

async def _process_account(account: dict, replied: set) -> dict:
    user      = account["user"]
    pw        = account["password"]
    name      = account["name"]
    imap_host = account.get("imap_host", "imap.gmail.com")
    smtp_host = account.get("smtp_host", "smtp.gmail.com")
    stats = {"processed": 0, "replied": 0, "labeled": 0, "archived": 0, "alerts": 0}

    try:
        mail = _imap_connect(user, pw, imap_host)
    except Exception as e:
        log.error(f"IMAP login failed for {user}: {e}")
        return stats

    try:
        messages = _fetch_unread(mail, "INBOX", limit=15)
        log.info(f"{user}: {len(messages)} unread emails")

        for m in messages:
            msg_id   = m["msg_id"] or f"{user}:{m['uid']}"
            if msg_id in replied:
                continue

            stats["processed"] += 1
            classification = await _classify_email(m["subject"], m["from"], m["body"])

            label    = classification.get("label", "Priority")
            do_reply = classification.get("reply_needed", False)
            do_arch  = classification.get("archive", False)
            do_alert = classification.get("telegram_alert", False)
            priority = classification.get("priority", "normal")
            summary  = classification.get("summary", m["subject"])
            draft    = classification.get("reply_draft", "")

            # Apply Gmail label
            _gmail_label(mail, m["uid"], label)
            stats["labeled"] += 1

            # Mark read for newsletters/spam
            if classification.get("category") in ("newsletter", "spam"):
                try:
                    mail.uid("STORE", m["uid"].encode(), "+FLAGS", "(\\Seen)")
                except Exception:
                    pass

            # Archive if needed
            if do_arch:
                _gmail_archive(mail, m["uid"])
                stats["archived"] += 1

            # Auto-reply — never reply to newsletter/mailing subdomains
            _, from_addr = parseaddr(m["from"])
            _frm_lower = from_addr.lower()
            _newsletter_domain = any(sig in _frm_lower for sig in [
                "noreply", "no-reply", "donotreply", "@news.", "@mail.", "@mailings.",
                "@email.", "@lists.", "@em.", "@sg.", "@em2.", "@reply.", "newsletter",
                "mailer-daemon", "postmaster", "bounce", "unsubscribe"
            ])
            if do_reply and draft and from_addr and from_addr != user and not _newsletter_domain:
                sent = _send_reply(user, pw, name, from_addr,
                                   m["subject"], draft, m["msg_id"], smtp_host)
                if sent:
                    stats["replied"] += 1
                    replied.add(msg_id)
                    _gmail_label(mail, m["uid"], "Beantwortet")
                    log.info(f"Auto-replied to {from_addr}: {m['subject'][:50]}")

            # Telegram alert for urgent mails
            if do_alert or priority == "urgent":
                stats["alerts"] += 1
                _, clean_from = parseaddr(m["from"])
                await _tg(
                    f"📧 *Dringende Email* [{user}]\n\n"
                    f"Von: `{clean_from}`\n"
                    f"Betreff: {m['subject'][:60]}\n"
                    f"Kategorie: {classification.get('category','?')}\n\n"
                    f"{summary}\n\n"
                    f"{'✅ Auto-beantwortet' if do_reply else '⚠️ Antwort nötig'}"
                )

    except Exception as e:
        log.error(f"Error processing {user}: {e}")
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    return stats


# ── Daily summary ─────────────────────────────────────────────────────────────

async def send_email_daily_summary():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Once-per-day guard — prevents duplicates on scheduler restart
    lock_file = DATA_DIR / f"email_summary_{today}.lock"
    if lock_file.exists():
        log.info("Email daily summary already sent today (%s) — skipping duplicate", today)
        return
    lock_file.touch()

    try:
        stats = json.loads(STATS_FILE.read_text()) if STATS_FILE.exists() else {}
    except Exception:
        stats = {}

    day_stats = stats.get(today, {})
    accounts = _accounts()

    lines = [f"📧 *Email Daily Report — {today}*\n"]
    for acc in accounts:
        user = acc["user"]
        s = day_stats.get(user, {})
        lines.append(
            f"*{user}*\n"
            f"  Verarbeitet: {s.get('processed', 0)}\n"
            f"  Auto-beantwortet: {s.get('replied', 0)}\n"
            f"  Archiviert: {s.get('archived', 0)}\n"
            f"  Alerts gesendet: {s.get('alerts', 0)}"
        )

    # Chunk at 3500 chars to stay under Telegram's 4096 limit
    full = "\n\n".join(lines)
    while full:
        if len(full) <= 3500:
            await _tg(full)
            break
        split_at = full.rfind("\n\n", 0, 3500)
        if split_at == -1:
            split_at = 3500
        await _tg(full[:split_at])
        full = full[split_at:].lstrip()


def _update_stats(user: str, result: dict):
    try:
        stats = json.loads(STATS_FILE.read_text()) if STATS_FILE.exists() else {}
    except Exception:
        stats = {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today not in stats:
        stats[today] = {}
    prev = stats[today].get(user, {})
    for k, v in result.items():
        prev[k] = prev.get(k, 0) + v
    stats[today][user] = prev
    # Keep only last 30 days
    keys = sorted(stats.keys())
    if len(keys) > 30:
        for old in keys[:-30]:
            del stats[old]
    STATS_FILE.write_text(json.dumps(stats, indent=2))


# ── Public entry points ───────────────────────────────────────────────────────

def get_email_stats() -> dict:
    """Return aggregated email stats for today and last 7 days (used by dashboard/IndexNow)."""
    try:
        raw = json.loads(STATS_FILE.read_text()) if STATS_FILE.exists() else {}
    except Exception:
        raw = {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_stats = raw.get(today, {})
    totals: dict = {"processed": 0, "replied": 0, "labeled": 0, "archived": 0, "alerts": 0}
    for _user, day in raw.items():
        if isinstance(day, dict):
            for k in totals:
                totals[k] += day.get(k, 0)
    return {
        "today": today_stats,
        "all_time": totals,
        "days_tracked": len(raw),
        "accounts": len(_accounts()),
        "status": "ok",
    }


async def run_email_check() -> str:
    """Check all Gmail accounts, classify, reply, label. Called by scheduler."""
    accounts = _accounts()
    if not accounts:
        return "No email accounts configured (set GMAIL_USER + GMAIL_APP_PASSWORD)"

    replied = _load_replied()
    totals  = {"processed": 0, "replied": 0, "labeled": 0, "archived": 0, "alerts": 0}

    for acc in accounts:
        result = await _process_account(acc, replied)
        _update_stats(acc["user"], result)
        for k in totals:
            totals[k] += result.get(k, 0)

    _save_replied(replied)
    log.info(f"EmailBrain done: {totals}")
    return (
        f"processed={totals['processed']} replied={totals['replied']} "
        f"labeled={totals['labeled']} archived={totals['archived']} alerts={totals['alerts']}"
    )


async def send_outreach_batch(leads: list) -> dict:
    """Outreach disabled — caused bounce emails from invalid addresses."""
    log.info("send_outreach_batch: disabled to prevent bounce emails")
    return {"sent": 0, "failed": 0, "disabled": True}

    accounts = _accounts()
    if not accounts:
        log.warning("send_outreach_batch: no email accounts configured")
        return {"sent": 0, "failed": 0}

    sender = accounts[0]
    replied = _load_replied()
    sent = 0
    failed = 0

    subject = "Kostenloser Shopify-Audit für deinen Store | BullPower Hub"
    body_template = (
        "Hallo{name_part},\n\n"
        "ich bin Rudolf von BullPower Hub — wir automatisieren Shopify-Stores mit KI.\n\n"
        "Kurze Frage: Hast du gerade Probleme mit zu niedrigen Konversionsraten, "
        "manuellem Content-Erstellen oder fehlender Sichtbarkeit auf Social Media?\n\n"
        "Ich biete dir einen kostenlosen 15-Minuten-Audit an:\n"
        "→ KI-Content-Analyse deiner Produktseiten\n"
        "→ Konkrete Maßnahmen für sofortige Umsatzsteigerung\n"
        "→ Kein Pitching — nur echter Mehrwert\n\n"
        "Interesse? Einfach kurz antworten.\n\n"
        "Mehr unter: https://bullpower-hub-portal.netlify.app\n\n"
        "Beste Grüße,\n"
        "Rudolf Sarkany | BullPower Hub | aiitec.online"
    )

    for lead in leads:
        email = (lead.get("email") or "").strip().lower()
        if not email or "@" not in email:
            continue
        guard_key = f"outreach:{email}"
        if guard_key in replied:
            continue  # already contacted

        fname = (lead.get("first_name") or "").strip()
        name_part = f" {fname}" if fname else ""
        body = body_template.format(name_part=name_part)

        ok = _send_reply(
            sender_user=sender["user"],
            sender_pw=sender["password"],
            sender_name=sender["name"],
            to_addr=email,
            subject=subject,
            body=body,
            smtp_host=sender.get("smtp_host", "smtp.gmail.com"),
        )
        if ok:
            replied.add(guard_key)
            sent += 1
            log.info("Outreach sent to %s", email)
        else:
            failed += 1

    _save_replied(replied)
    log.info("send_outreach_batch done: sent=%d failed=%d", sent, failed)
    return {"sent": sent, "failed": failed}


async def run_email_setup_check() -> str:
    """One-time: verify IMAP connectivity for all configured accounts."""
    accounts = _accounts()
    if not accounts:
        return "NO_ACCOUNTS — set GMAIL_USER and GMAIL_APP_PASSWORD in .env / Railway"

    results = []
    for acc in accounts:
        user = acc["user"]
        try:
            mail = _imap_connect(user, acc["password"], acc.get("imap_host", "imap.gmail.com"))
            mail.select("INBOX")
            _, data = mail.search(None, "UNSEEN")
            unread = len(data[0].split()) if data[0] else 0
            mail.logout()
            results.append(f"✅ {user}: {unread} unread")
        except Exception as e:
            results.append(f"❌ {user}: {e}")

    summary = " | ".join(results)
    await _tg(f"📧 *EmailBrain Setup Check*\n\n{summary}")
    return summary
