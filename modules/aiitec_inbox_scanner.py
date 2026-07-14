#!/usr/bin/env python3
"""
AIITEC Inbox Scanner — Gmail-Antworten alle 10 Minuten prüfen
=============================================================
Überwacht aiitecbuuss@gmail.com auf Antworten von Outreach-Targets.

Was es tut (alle 10 Minuten):
  1. IMAP-Login → alle UNSEEN Emails abrufen
  2. Absender mit aiitec_companies (Supabase) abgleichen
  3. Kategorie bestimmen: reply / bounce / ooo / interest / unsubscribe
  4. Supabase: aiitec_campaigns.status aktualisieren
  5. Telegram-Alert bei Reply/Interest/Bounce
  6. Bounce → company.status = 'bounced' (kein Follow-Up mehr)
  7. Interest → company.status = 'hot' (manuell priorisieren)

Starten:
  python3 modules/aiitec_inbox_scanner.py            # Daemon
  python3 modules/aiitec_inbox_scanner.py --check    # Einmalig prüfen
  python3 modules/aiitec_inbox_scanner.py --stats    # Statistik
"""
from __future__ import annotations

import asyncio
import email as email_lib
import imaplib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from email.header import decode_header as _dh
from pathlib import Path
from typing import Optional

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [INBOX] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("AiitecInbox")

_BASE      = Path(__file__).parent.parent
_INTERVAL  = 600  # 10 Minuten

def _load_env():
    ef = _BASE / ".env"
    if ef.exists():
        for line in ef.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

_IMAP_HOST = "imap.gmail.com"
_IMAP_PORT = 993
_GMAIL_USER = lambda: os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")
_GMAIL_PASS = lambda: os.getenv("GMAIL_APP_PASSWORD_AIITEC", "rqcd uzim npsl odgw")
_TG_TOKEN   = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT    = lambda: os.getenv("TELEGRAM_CHAT_ID", "")
_SB_URL     = lambda: os.getenv("SUPABASE_URL", "")
_SB_KEY     = lambda: os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY", ""))

# ── Kategorisierung ────────────────────────────────────────────────────────────

def _categorize(sender: str, subject: str, body: str) -> str:
    text = f"{subject} {body}".lower()
    sender_l = sender.lower()

    # Bounce-Erkennung
    bounce_signals = [
        "mailer-daemon", "delivery failed", "undeliverable",
        "failed to deliver", "mail delivery failed", "bounce",
        "non-delivery", "returned mail", "550 ", "551 ", "552 ",
        "postmaster@", "noreply@bounce", "daemon@",
    ]
    if any(s in sender_l or s in text for s in bounce_signals):
        return "bounce"

    # Out-of-office
    ooo_signals = [
        "out of office", "abwesenheitsnotiz", "im urlaub",
        "außer haus", "on vacation", "on leave", "auto-reply",
        "automatic reply", "automatische antwort", "urlaub",
        "abwesend", "nicht erreichbar",
    ]
    if any(s in text for s in ooo_signals):
        return "ooo"

    # Unsubscribe / Kein Interesse
    unsub_signals = [
        "kein interesse", "not interested", "bitte keine",
        "austragen", "unsubscribe", "stop", "abmelden",
        "bitte entfernen", "please remove", "kündigen",
        "keine weiteren", "no more emails",
    ]
    if any(s in text for s in unsub_signals):
        return "unsubscribe"

    # Interesse / Hot Lead
    interest_signals = [
        "interesse", "interested", "gerne", "termin",
        "meeting", "demo", "präsentation", "angebot",
        "preis", "kosten", "wie viel", "how much",
        "wann", "when can", "können wir", "können sie",
        "mehr informationen", "more info", "tell me more",
        "ich würde", "i would like", "let's talk",
        "gespräch", "anruf", "call", "zoom", "teams",
    ]
    if any(s in text for s in interest_signals):
        return "interest"

    # Neutrale Antwort
    return "reply"

# ── Supabase ──────────────────────────────────────────────────────────────────

async def _sb(method: str, path: str, body=None, params=None):
    url = _SB_URL().rstrip("/") + path
    headers = {
        "apikey": _SB_KEY(),
        "Authorization": f"Bearer {_SB_KEY()}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    async with aiohttp.ClientSession() as s:
        fn = getattr(s, method.lower())
        kw: dict = {"headers": headers}
        if body:   kw["json"] = body
        if params: kw["params"] = params
        async with fn(url, **kw) as r:
            text = await r.text()
            if r.status >= 400:
                log.debug("SB %s %s → %s", method, path, r.status)
                return None
            try:
                return json.loads(text)
            except Exception:
                return text

async def _find_company_by_email(sender_email: str):
    domain = sender_email.split("@")[-1] if "@" in sender_email else sender_email
    res = await _sb("GET", "/rest/v1/aiitec_companies",
                    params={"domain": f"eq.{domain}", "limit": "1"})
    if res:
        return res[0]
    res = await _sb("GET", "/rest/v1/aiitec_companies",
                    params={"email": f"ilike.%@{domain}", "limit": "1"})
    return res[0] if res else None

async def _update_company_status(company_id: int, status: str):
    await _sb("PATCH", f"/rest/v1/aiitec_companies?id=eq.{company_id}",
              body={"status": status})

async def _log_inbox_event(company_id: Optional[int], sender: str,
                           subject: str, category: str, snippet: str):
    await _sb("POST", "/rest/v1/aiitec_email_events",
              body={
                  "campaign_id": None,
                  "event_type": f"inbox_{category}",
                  "detail": json.dumps({
                      "sender": sender,
                      "subject": subject,
                      "snippet": snippet[:300],
                      "company_id": company_id,
                  }),
              })

# ── Telegram ──────────────────────────────────────────────────────────────────

# Private Domains — keine Benachrichtigung, kein Update
PRIVATE_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.de",
    "hotmail.com", "hotmail.de", "outlook.com", "outlook.de",
    "web.de", "gmx.de", "gmx.net", "gmx.at", "gmx.ch",
    "t-online.de", "freenet.de", "mail.de", "icloud.com",
    "me.com", "aol.com", "live.com", "live.de", "msn.com",
    "protonmail.com", "proton.me", "posteo.de", "tutanota.com",
}

# Absender-Prefixes die NIEMALS automatisch beantwortet werden
_NO_AUTO_REPLY_PREFIXES = (
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "bounce", "bounces",
    "newsletter", "marketing", "info-", "bulk", "auto-",
    "notifications", "alerts", "system", "admin", "support",
)

# Eigene AIITEC-Adressen nie antworten
_OWN_EMAILS = {"aiitecbuuss@gmail.com", "dragonadnp@gmail.com",
               "bullpowersrtkennels@gmail.com", "looopwave@gmail.com",
               "rudolf.sarkany.aiitec@gmail.com", "rudolfsarkany1984@gmail.com"}

def _is_private_email(email_addr: str) -> bool:
    if not email_addr or "@" not in email_addr:
        return True
    local, _, domain = email_addr.lower().partition("@")
    # Private Domains
    if domain in PRIVATE_DOMAINS:
        return True
    # Eigene Accounts
    if email_addr.lower() in _OWN_EMAILS:
        return True
    # System/Newsletter-Prefixes
    if any(local.startswith(p) for p in _NO_AUTO_REPLY_PREFIXES):
        return True
    return False

def _is_safe_to_auto_reply(email_addr: str) -> bool:
    """Nur B2B-Unternehmensemails bekommen Auto-Antworten."""
    if _is_private_email(email_addr):
        return False
    local = email_addr.lower().split("@")[0]
    # Zusätzliche Sicherheit: generische Unternehmens-Infos nicht auto-antworten
    if local in ("info", "kontakt", "contact", "hello", "hallo"):
        return False
    return True

CATEGORY_EMOJI = {
    "interest":    "🔥",
    "reply":       "📩",
    "bounce":      "❌",
    "ooo":         "🏖️",
    "unsubscribe": "🚫",
}

async def _tg(text: str):
    token = _TG_TOKEN()
    chat  = _TG_CHAT()
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram: %s", e)

# ── IMAP Helpers ──────────────────────────────────────────────────────────────

def _decode_header_str(raw) -> str:
    if not raw:
        return ""
    parts = _dh(raw)
    result = []
    for b, enc in parts:
        if isinstance(b, bytes):
            try:
                result.append(b.decode(enc or "utf-8", errors="replace"))
            except Exception:
                result.append(b.decode("utf-8", errors="replace"))
        else:
            result.append(str(b))
    return " ".join(result).strip()

def _get_body(msg) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                try:
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                    break
                except Exception:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            pass
    return body[:2000]

def _extract_email_addr(raw: str) -> str:
    m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", raw or "")
    return m.group(0).lower() if m else (raw or "").lower()

async def _send_auto_response(to_email: str, company_name: str, checkout_url: str) -> bool:
    """Sendet automatische Antwort mit Stripe-Checkout an interessierte Leads."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    subject = "Re: AIITEC Lead-Agent — Ihr nächster Schritt"
    body = f"""Hallo,

vielen Dank für Ihr Interesse an AIITEC!

Ich freue mich sehr über Ihre Rückmeldung. Wie besprochen möchte ich Ihnen
ermöglichen, direkt loszulegen:

👉 Jetzt AIITEC Lead-Agent freischalten:
{checkout_url}

Was Sie erhalten:
• 10 vorqualifizierte B2B-Leads täglich — vollautomatisch
• KI-gestützte Zielgruppen-Analyse für DACH-Markt
• Monatlich kündbar ab €500/Monat
• Setup in unter 24 Stunden

Bei Fragen stehe ich jederzeit zur Verfügung.

Mit freundlichen Grüßen,
Rudolf Sarkany
AIITEC — AI Business Automation
https://dist-pi-jet-78.vercel.app/
"""

    # Sende über aiitecbuuss@gmail.com
    gmail_user = os.getenv("GMAIL_USER_4", "aiitecbuuss@gmail.com")
    gmail_pwd  = os.getenv("GMAIL_APP_PASSWORD_4", "")
    if not gmail_pwd:
        log.warning("[AUTO-RESPONDER] Kein Gmail-Passwort für %s", gmail_user)
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"]  = subject
        msg["From"]     = f"Rudolf Sarkany — AIITEC <{gmail_user}>"
        msg["To"]       = to_email
        msg["Reply-To"] = gmail_user
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
            s.login(gmail_user, gmail_pwd)
            s.sendmail(gmail_user, [to_email], msg.as_string())
        log.info("[AUTO-RESPONDER] ✉ Gesendet → %s", to_email)
        return True
    except Exception as e:
        log.error("[AUTO-RESPONDER] Fehler → %s: %s", to_email, e)
        return False


# ── Haupt-Scan ────────────────────────────────────────────────────────────────

_SEEN_UIDS: set = set()

async def scan_inbox() -> dict:
    stats = {"total": 0, "interest": 0, "bounce": 0, "ooo": 0,
             "unsubscribe": 0, "reply": 0, "errors": 0}
    try:
        mail = imaplib.IMAP4_SSL(_IMAP_HOST, _IMAP_PORT)
        mail.login(_GMAIL_USER(), _GMAIL_PASS())
        mail.select("INBOX")
        _, data = mail.search(None, "UNSEEN")
        uids = data[0].split() if data[0] else []
        log.info("INBOX: %d ungelesene Emails", len(uids))

        for uid in uids:
            if uid in _SEEN_UIDS:
                continue
            _SEEN_UIDS.add(uid)
            try:
                _, raw = mail.fetch(uid, "(RFC822)")
                if not raw or not raw[0]:
                    continue
                msg = email_lib.message_from_bytes(raw[0][1])
                sender_raw = msg.get("From", "")
                subject    = _decode_header_str(msg.get("Subject", ""))
                sender_addr = _extract_email_addr(sender_raw)

                # Private Emails (gmail, gmx, etc.) — kein Alert, kein Update
                if _is_private_email(sender_addr):
                    log.debug("  [SKIP-PRIVATE] %s", sender_addr)
                    continue

                body       = _get_body(msg)
                category   = _categorize(sender_addr, subject, body)
                snippet    = body.replace("\n", " ").strip()[:200]

                stats["total"] += 1
                stats[category] = stats.get(category, 0) + 1

                log.info("  [%s] %s | %s", category.upper(), sender_addr, subject[:60])

                # Supabase-Lookup
                company = await _find_company_by_email(sender_addr)
                company_id = company["id"] if company else None
                company_name = company["name"] if company else sender_addr

                # Status update
                if company_id:
                    status_map = {
                        "interest":    "hot",
                        "reply":       "replied",
                        "bounce":      "bounced",
                        "unsubscribe": "unsubscribed",
                        "ooo":         "ooo",
                    }
                    await _update_company_status(company_id, status_map[category])

                await _log_inbox_event(company_id, sender_addr, subject, category, snippet)

                # Telegram-Alert
                emoji = CATEGORY_EMOJI.get(category, "📧")
                if category in ("interest", "bounce", "unsubscribe", "reply"):
                    tg_msg = (
                        f"{emoji} *AIITEC Inbox — {category.upper()}*\n\n"
                        f"*Von:* {company_name}\n"
                        f"*Betreff:* {subject}\n"
                    )
                    if snippet:
                        tg_msg += f"*Inhalt:* _{snippet[:200]}_\n"
                    if category == "interest":
                        checkout_url = "https://buy.stripe.com/7sYeVf53k5PQ7EA2Wq4F203"
                        # Auto-Responder NUR an echte B2B-Adressen
                        if _is_safe_to_auto_reply(sender_addr):
                            tg_msg += (
                                f"\n🎯 *HOT LEAD — Auto-Responder gesendet!*\n"
                                f"💳 Checkout: {checkout_url}"
                            )
                            asyncio.create_task(
                                _send_auto_response(sender_addr, company_name, checkout_url)
                            )
                        else:
                            tg_msg += "\n🎯 *HOT LEAD — Bitte manuell antworten!*"
                    elif category == "bounce":
                        tg_msg += "\n_→ Firma als 'bounced' markiert_"
                    elif category == "unsubscribe":
                        tg_msg += "\n_→ Firma als 'unsubscribed' markiert_"
                    await _tg(tg_msg)

            except Exception as e:
                log.error("Email-Fehler UID %s: %s", uid, e)
                stats["errors"] += 1

        mail.logout()
    except Exception as e:
        log.error("IMAP-Fehler: %s", e)
        stats["errors"] += 1
    return stats

async def show_stats():
    total = await _sb("GET", "/rest/v1/aiitec_companies",
                      params={"select": "count", "count": "exact"})
    hot   = await _sb("GET", "/rest/v1/aiitec_companies",
                      params={"status": "eq.hot", "select": "count", "count": "exact"})
    replied = await _sb("GET", "/rest/v1/aiitec_companies",
                        params={"status": "eq.replied", "select": "count", "count": "exact"})
    bounced = await _sb("GET", "/rest/v1/aiitec_companies",
                        params={"status": "eq.bounced", "select": "count", "count": "exact"})

    def _c(r): return r[0].get("count", "?") if r else "?"
    print("\n=== AIITEC Inbox Statistik ===")
    print(f"  Unternehmen gesamt : {_c(total)}")
    print(f"  Hot Leads (replied): {_c(hot)}")
    print(f"  Replied            : {_c(replied)}")
    print(f"  Bounced            : {_c(bounced)}")
    print()

# ── Daemon ────────────────────────────────────────────────────────────────────

async def _run_self_repair() -> None:
    """Ruft health_check() aus outreach_machine auf — repariert automatisch."""
    try:
        # Lazy import um zirkuläre Importe zu vermeiden
        import sys as _sys
        base_str = str(_BASE)
        if base_str not in _sys.path:
            _sys.path.insert(0, base_str)
        from modules.aiitec_outreach_machine import health_check
        hc = await health_check()
        status_lines = [
            f"🔧 *AIITEC Self-Repair Report*",
            f"📊 Queue: {hc.get('queue_size', '?')} Firmen",
            f"📧 SMTP: {hc.get('smtp_available', '?')}/{hc.get('smtp_total', '?')} verfügbar",
        ]
        if hc.get("repairs"):
            status_lines.append("✅ Reparaturen: " + " | ".join(hc["repairs"]))
        if hc.get("issues"):
            status_lines.append("⚠️ Probleme: " + " | ".join(hc["issues"]))
        if not hc["ok"] or hc.get("repairs"):
            await _tg("\n".join(status_lines))
        log.info("[SELF-REPAIR] Health OK=%s Queue=%s SMTP=%s/%s",
                 hc["ok"], hc.get("queue_size"), hc.get("smtp_available"), hc.get("smtp_total"))
    except Exception as e:
        log.error("[SELF-REPAIR] Fehler: %s", e)


async def daemon():
    log.info("AIITEC Inbox Scanner gestartet — alle %d Sek. (%d Min.)",
             _INTERVAL, _INTERVAL // 60)
    await _tg(f"📬 *AIITEC Inbox Scanner* gestartet\nPrüft alle {_INTERVAL//60} Min. auf Antworten")
    check_count = 0
    while True:
        try:
            stats = await scan_inbox()
            check_count += 1
            if stats["total"] > 0:
                log.info("Scan #%d: %d Emails verarbeitet", check_count, stats["total"])
            # Stündlicher Status-Report + Self-Repair
            if check_count % 6 == 0:
                await _tg(
                    f"📊 *AIITEC Inbox — Stunden-Report*\n"
                    f"Letzte Runde: {stats['total']} Emails\n"
                    f"🔥 Interest: {stats.get('interest',0)} | "
                    f"❌ Bounce: {stats.get('bounce',0)} | "
                    f"📩 Reply: {stats.get('reply',0)}"
                )
                await _run_self_repair()
        except Exception as e:
            log.error("Daemon-Fehler: %s", e)
        await asyncio.sleep(_INTERVAL)

async def main():
    args = sys.argv[1:]
    if "--check" in args:
        stats = await scan_inbox()
        print(json.dumps(stats, indent=2))
    elif "--stats" in args:
        await show_stats()
    else:
        await daemon()

if __name__ == "__main__":
    asyncio.run(main())
