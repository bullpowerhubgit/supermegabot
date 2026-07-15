#!/usr/bin/env python3
"""
Email Guardian — Pflicht-Prüfung für ALLE ausgehenden E-Mails
=============================================================
Kein einziger Email verlässt das System ohne diese 6 Prüfungen:

  1. Empfänger-Check: keine privaten/internen Adressen ohne Erlaubnis
  2. Template-Prüfung: keine ungefüllten {variable} oder [PLATZHALTER]
  3. localhost/IP-URLs blockieren: niemals http://localhost an Kunden
  4. Mindestlänge: kein leerer/zu kurzer Emailtext
  5. Spam-Pattern: kein übermäßiges GROSSSCHREIBEN, keine Pfeile >>>
  6. Duplicate-Check: gleiche Email in 24h nicht zweimal senden

Integration:
    from modules.email_guardian import validate_email, safe_send_email
    ok, errors = validate_email(to_email, subject, html_body)
    if not ok:
        log.warning("Email blockiert: %s", errors)
        return
"""
from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("EmailGuardian")

_ROOT = Path(__file__).parent.parent
_DB = _ROOT / "data" / "email_guardian.db"

# ── System/Platform Domains — NIEMALS auto-antworten ─────────────────────────
# WICHTIG: gmail.com hier NICHT drin — Kunden können Gmail-Adressen haben!
_INTERNAL_DOMAINS = {
    # Hosting/Infrastructure (nie Kunden)
    "railway.app", "netlify.com", "vercel.com", "heroku.com",
    # Shop/Payment Platforms (nie Kunden)
    "shopify.com", "myshopify.com", "stripe.com", "supabase.com",
    "paypal.com", "paypalcorp.com",
    # Email Marketing Systems
    "mailchimp.com", "klaviyo.com", "brevo.com", "sendgrid.com",
    "activecampaign.com", "sendinblue.com", "constantcontact.com",
    # Dev-Platforms
    "github.com", "githubusercontent.com", "gitlab.com",
    # Social Media (System-Emails, nie Kunden)
    "facebookmail.com", "linkedin.com", "bounce.twitter.com",
}

# Rudolf's eigene Adressen — NIEMALS auto-antworten (kein Loop!)
_OWN_EMAILS = {
    "bullpowersrtkennels@gmail.com",
    "aiitecbuuss@gmail.com",
    "rudolfsarkany1984@gmail.com",
    "dragonadnp@gmail.com",
    "rudolf.sarkany.aiitec@gmail.com",
    "rudolfsarkany1984@gmail.com",
}

# Whitelist für explizit erlaubte Empfänger (für Tests, interne Reports)
_WHITELIST_EMAILS: set = set()

_PLACEHOLDER = re.compile(
    r'\{[a-z_]{2,}\}(?!\d)'   # {variable} aber nicht {0}
    r'|\[PLATZHALTER\]|\[PLACEHOLDER\]|\[NAME\]|\[EMAIL\]|\[LINK\]'
    r'|\[TODO\]|BEISPIELTEXT|lorem ipsum',
    re.IGNORECASE
)
_LOCALHOST = re.compile(r'https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?')
_EXCESS_CAPS = re.compile(r'[A-ZÄÖÜ]{8,}')  # 8+ Großbuchstaben in Folge
_SPAM_ARROWS = re.compile(r'>{3,}|»{3,}')


def _init_db():
    _DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(_DB)) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS sent_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            to_email TEXT, subject TEXT, content_hash TEXT,
            ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS blocked_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            to_email TEXT, subject TEXT, reason TEXT,
            ts TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_hash ON sent_log(content_hash, to_email);
        """)


def _is_duplicate(to_email: str, content_hash: str, hours: int = 24) -> bool:
    _init_db()
    with sqlite3.connect(str(_DB)) as c:
        row = c.execute(
            "SELECT id FROM sent_log WHERE to_email=? AND content_hash=? "
            "AND ts > datetime('now', ?)",
            (to_email, content_hash, f"-{hours} hours")
        ).fetchone()
    return row is not None


def _log_sent(to_email: str, subject: str, content_hash: str):
    _init_db()
    with sqlite3.connect(str(_DB)) as c:
        c.execute("INSERT INTO sent_log(to_email,subject,content_hash) VALUES(?,?,?)",
                  (to_email, subject, content_hash))


def _log_blocked(to_email: str, subject: str, reason: str):
    _init_db()
    with sqlite3.connect(str(_DB)) as c:
        c.execute("INSERT INTO blocked_log(to_email,subject,reason) VALUES(?,?,?)",
                  (to_email, subject, reason))


def validate_email(
    to_email: str,
    subject: str,
    html_body: str,
    allow_private: bool = False,
) -> tuple[bool, list[str]]:
    """
    Prüft ob eine Email versendet werden darf.
    Returns: (ok: bool, errors: list[str])
    """
    errors = []
    body_plain = re.sub(r'<[^>]+>', ' ', html_body)  # HTML→Plaintext für Checks

    # 1. Empfänger-Check
    if not to_email or "@" not in to_email:
        errors.append(f"Ungültige Email-Adresse: {to_email!r}")

    if not allow_private:
        domain = to_email.split("@")[-1].lower() if "@" in to_email else ""
        # Blockiere eigene Adressen (vermeidet Auto-Reply-Loops)
        if to_email.lower() in _OWN_EMAILS:
            errors.append(f"Eigene Adresse blockiert: {to_email}")
        # Blockiere bekannte System/Platform-Domains
        elif domain in _INTERNAL_DOMAINS:
            errors.append(f"System-Domain blockiert: {domain}")

    # 2. Betreff-Check
    if not subject or len(subject.strip()) < 3:
        errors.append("Betreff leer oder zu kurz")
    if _PLACEHOLDER.search(subject):
        errors.append(f"Placeholder im Betreff: {subject!r}")

    # 3. Inhalt-Checks
    if len(body_plain.strip()) < 50:
        errors.append(f"Email-Text zu kurz: {len(body_plain)} Zeichen (min 50)")
    unfilled = _PLACEHOLDER.findall(html_body + " " + subject)
    if unfilled:
        errors.append(f"Ungefüllte Variablen: {unfilled[:5]}")
    if _LOCALHOST.search(html_body):
        errors.append("localhost-URL im Email-HTML — würde bei Kunden nicht funktionieren")

    # 4. Spam-Patterns
    excess_caps = _EXCESS_CAPS.findall(body_plain)
    if len(excess_caps) > 3:
        errors.append(f"Zu viele GROSSBUCHSTABEN ({len(excess_caps)}x) — Spam-Risiko")
    if _SPAM_ARROWS.search(body_plain):
        errors.append("Spam-Pattern: >>> Pfeile im Text")

    # 5. Duplikat-Check
    content_hash = hashlib.md5(f"{to_email}:{subject}:{html_body[:500]}".encode()).hexdigest()
    if _is_duplicate(to_email, content_hash):
        errors.append("Duplikat: gleiche Email an diese Adresse in letzten 24h bereits gesendet")

    return len(errors) == 0, errors


def mark_sent(to_email: str, subject: str, html_body: str):
    """Nach erfolgreichen Send aufrufen um Duplikat-Check zu aktivieren."""
    content_hash = hashlib.md5(f"{to_email}:{subject}:{html_body[:500]}".encode()).hexdigest()
    _log_sent(to_email, subject, content_hash)


def mark_blocked(to_email: str, subject: str, reason: str):
    """Blockierte Email protokollieren."""
    _log_blocked(to_email, subject, reason)


def get_guardian_stats(hours: int = 24) -> dict:
    """Statistik der letzten X Stunden."""
    _init_db()
    with sqlite3.connect(str(_DB)) as c:
        sent = c.execute(
            "SELECT COUNT(*) FROM sent_log WHERE ts > datetime('now', ?)",
            (f"-{hours} hours",)
        ).fetchone()[0]
        blocked = c.execute(
            "SELECT COUNT(*) FROM blocked_log WHERE ts > datetime('now', ?)",
            (f"-{hours} hours",)
        ).fetchone()[0]
        recent_blocked = c.execute(
            "SELECT to_email, subject, reason, ts FROM blocked_log "
            "WHERE ts > datetime('now', ?) ORDER BY ts DESC LIMIT 10",
            (f"-{hours} hours",)
        ).fetchall()
    return {
        "period_hours": hours,
        "sent": sent,
        "blocked": blocked,
        "recent_blocked": [dict(zip(["to","subject","reason","ts"], r)) for r in recent_blocked],
    }


# ── Wrapper für alle Email-Sender ─────────────────────────────────────────────
async def safe_send_email(
    to_email: str,
    subject: str,
    html_body: str,
    send_fn,
    allow_private: bool = False,
    source_module: str = "unknown",
) -> dict:
    """
    Wrapper der validate_email() ausführt und bei OK send_fn() aufruft.
    send_fn muss async sein und True/False oder dict zurückgeben.

    Verwendung:
        result = await safe_send_email(
            to_email, subject, html,
            send_fn=lambda: klaviyo_send(to_email, subject, html),
            source_module="email_blast_engine"
        )
    """
    ok, errors = validate_email(to_email, subject, html_body, allow_private=allow_private)
    if not ok:
        mark_blocked(to_email, subject, " | ".join(errors))
        log.warning("Email blockiert [%s → %s]: %s", source_module, to_email, errors)
        return {"ok": False, "blocked": True, "errors": errors}

    try:
        result = await send_fn()
        success = result is True or (isinstance(result, dict) and result.get("ok"))
        if success:
            mark_sent(to_email, subject, html_body)
            log.info("Email gesendet [%s → %s]: %s", source_module, to_email, subject)
            return {"ok": True}
        err = result.get("error", "Unbekannter Fehler") if isinstance(result, dict) else "send_fn returned False"
        mark_blocked(to_email, subject, err)
        return {"ok": False, "error": err}
    except Exception as e:
        mark_blocked(to_email, subject, str(e))
        log.error("Email-Send-Fehler [%s → %s]: %s", source_module, to_email, e)
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    import sys, json
    logging.basicConfig(level=logging.INFO)
    if "--stats" in sys.argv:
        print(json.dumps(get_guardian_stats(), indent=2, ensure_ascii=False))
    elif "--test" in sys.argv:
        tests = [
            ("kunde@beispiel.de", "Ihre Bestellung", "<p>Hallo Max, danke für Ihre Bestellung bei ineedit.com.co!</p>", False),
            ("", "Betreff", "<p>Body</p>", False),
            ("test@example.com", "", "<p>Body</p>", False),
            ("test@example.com", "Hallo {first_name}", "<p>Hallo {first_name}, danke!</p>", False),
            ("test@example.com", "Dashboard", "<p>Klick hier: http://localhost:8888/dashboard</p>", False),
            ("test@example.com", "Test", "<p>" + "x" * 30 + "</p>", False),
        ]
        for to, subj, body, priv in tests:
            ok, errors = validate_email(to, subj, body, allow_private=priv)
            status = "✅ OK" if ok else f"🚫 BLOCKIERT ({len(errors)} Fehler)"
            print(f"[{to[:20]}] {status}")
            for e in errors:
                print(f"   → {e}")
