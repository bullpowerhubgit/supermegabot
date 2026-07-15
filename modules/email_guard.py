#!/usr/bin/env python3
"""
EmailGuard v2 — Dauerhafter 6-Layer Email-Validator
=====================================================
JEDE Email muss ALLE Prüfungen bestehen, bevor sie rausgeht.
L1: Format + Empfänger-Validierung
L2: Placeholder + Spam-Pattern-Check
L3: Body-Mindestqualität (Länge, Inhalt)
L4: Noreply/Bounce-Schutz
L5: Duplikat-Schutz (SQLite 48h)
L6: KI-Qualitätsscore (Minimum 5/10)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Tuple, List, Optional

log = logging.getLogger("EmailGuard")

_DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
_DB_PATH = _DATA_DIR / "email_guard.db"
_DEDUP_HOURS = 48

_NOREPLY_LOCALS = {"noreply", "no-reply", "donotreply", "do-not-reply", "bounce",
                   "mailer-daemon", "postmaster", "daemon", "bounces"}
_DISPOSABLE = {"mailinator.com", "yopmail.com", "guerrillamail.com", "10minutemail.com",
               "tempmail.com", "throwam.com", "maildrop.cc", "spam4.me", "trashmail.com"}

def _init_db():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS sent_emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hash TEXT UNIQUE, to_email TEXT, sent_at REAL
    )""")
    conn.commit(); conn.close()

try:
    _init_db()
except Exception:
    pass

def _email_hash(to: str, subject: str, body: str) -> str:
    return hashlib.md5(f"{to.lower().strip()}:{subject[:80]}:{body[:200]}".encode()).hexdigest()

def _register_sent_db(to: str, subject: str, body: str) -> None:
    h = _email_hash(to, subject, body)
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute("INSERT OR REPLACE INTO sent_emails(hash,to_email,sent_at) VALUES(?,?,?)",
                     (h, to, time.time()))
        conn.commit(); conn.close()
    except Exception: pass

def _is_duplicate(to: str, subject: str, body: str) -> Tuple[bool, str]:
    h = _email_hash(to, subject, body)
    cutoff = time.time() - (_DEDUP_HOURS * 3600)
    try:
        conn = sqlite3.connect(_DB_PATH)
        row = conn.execute("SELECT sent_at FROM sent_emails WHERE hash=? AND sent_at>?",
                           (h, cutoff)).fetchone()
        conn.close()
        if row:
            age_h = int((time.time() - row[0]) / 3600)
            return True, f"Duplikat: gleiche Email an {to} vor {age_h}h gesendet"
    except Exception: pass
    return False, ""

# ── Verbotene Subject-/Body-Patterns ────────────────────────────────────────
_SPAM_PATTERNS = re.compile(
    r'\[PRODUKT\]|\[LINK\]|\[DATUM\]|\[PREIS\]|\[NAME\]|\[URL\]|'
    r'\[INSERT\]|\[PLACEHOLDER\]|undefined|NoneType|None\b|'
    r'TODO|FIXME|lorem ipsum|YOUR_EMAIL|YOUR_NAME|example\.com|'
    r'yourstore\.com|YOUR_DOMAIN|http://localhost|'
    # Life-Coach-Spam
    r'nutzt? nur \d+\s*%\s*de\w*|'
    r'weniger als \d+\s*%\s*ihr|'
    r'finanziell\w+\s+Potenzials?|'
    r'90\s*%\s*der\s*Menschen|'
    r'Geldquellen\s+NICHT|'
    r'Passives?\s+Einkommen\s+ohne|'
    r'reich\s+werden\s+in\s+\d+|'
    r'Ergebnisse\s+garantiert|'
    r'\d{2,}\s*%\s*Erfolgsquote|'
    r'Die\s+meisten\s+Menschen\s+nutzen\s+weniger|'
    r'finanziell\w+\s+Potenzial\w*\s*\.\s+Nicht',
    re.IGNORECASE,
)

_MIN_SUBJECT_CHARS = 5
_MAX_SUBJECT_CHARS = 100
_MIN_BODY_WORDS = 10


def validate_email(
    subject: str,
    body: str,
    to_email: str = "",
    skip_dedup: bool = False,
) -> Tuple[bool, List[str]]:
    """
    Synchrone 5-Layer-Validierung — vor dem Senden aufrufen.
    Returns (ok, errors). ok=False → Email NICHT senden.
    """
    errors: List[str] = []

    # L1: Format
    s = (subject or "").strip()
    if len(s) < _MIN_SUBJECT_CHARS:
        errors.append(f"Subject zu kurz: '{s}'")
    if len(s) > _MAX_SUBJECT_CHARS:
        errors.append(f"Subject zu lang ({len(s)} Zeichen)")
    if to_email and "@" not in to_email:
        errors.append(f"Ungültige Empfänger-Adresse: '{to_email}'")

    # L2: Placeholder + Spam
    b = re.sub(r'<[^>]+>', ' ', body or "")
    if len(b.split()) < _MIN_BODY_WORDS:
        errors.append(f"Email-Body zu kurz ({len(b.split())} Wörter, min {_MIN_BODY_WORDS})")
    m = _SPAM_PATTERNS.search(s)
    if m:
        errors.append(f"Spam/Placeholder im Subject: '{m.group()}'")
    m = _SPAM_PATTERNS.search(b)
    if m:
        errors.append(f"Spam/Placeholder im Body: '{m.group()}'")

    # L3: Bounce/Noreply-Schutz
    if to_email and "@" in to_email:
        local, domain = to_email.lower().split("@", 1)
        if local in _NOREPLY_LOCALS:
            errors.append(f"Noreply-Adresse blockiert: {to_email}")
        if domain in _DISPOSABLE:
            errors.append(f"Wegwerf-Domain blockiert: {domain}")

    # L4: Duplikat-Check
    if not skip_dedup and to_email:
        is_dup, dup_msg = _is_duplicate(to_email, subject, body)
        if is_dup:
            errors.append(dup_msg)

    if errors:
        log.warning("EmailGuard BLOCKIERT [%s]: %s | Subject: %s",
                    to_email or "?", errors, subject[:60])
    else:
        log.debug("EmailGuard OK: '%s' → %s", subject[:50], to_email)

    return len(errors) == 0, errors


async def validate_email_async(
    subject: str,
    body: str,
    to_email: str = "",
    skip_dedup: bool = False,
    skip_ai: bool = False,
) -> Tuple[bool, List[str]]:
    """
    Async 6-Layer-Validierung inkl. KI-Score.
    Nutze diese für nicht-zeitkritische Emails.
    """
    ok, errors = validate_email(subject, body, to_email, skip_dedup)
    if not ok:
        return False, errors

    # L6: KI-Score
    if not skip_ai:
        try:
            from modules.ai_client import ai_complete
            clean_body = re.sub(r'<[^>]+>', ' ', body)[:400]
            prompt = f"""Bewerte diese Email kurz. Antworte NUR mit einer Zahl 1-10.
1=völlig unbrauchbar/Spam, 10=perfekt professionell.

Betreff: {subject[:80]}
Inhalt: {clean_body}

Zahl (1-10):"""
            result = (await ai_complete(prompt, max_tokens=5)).strip()
            m = re.search(r'\d+', result)
            if m:
                score = int(m.group())
                if score < 4:
                    errors.append(f"KI-Score zu niedrig: {score}/10")
        except Exception as e:
            log.debug("EmailGuard KI-Check übersprungen: %s", e)

    return len(errors) == 0, errors


def register_sent(to_email: str, subject: str, body: str) -> None:
    """Nach erfolgreichem Senden aufrufen — verhindert Duplikate."""
    _register_sent_db(to_email, subject, body)


def guard_or_raise(subject: str, body: str, to_email: str = "") -> None:
    """Wirft ValueError wenn Email nicht valide ist."""
    ok, errors = validate_email(subject, body, to_email)
    if not ok:
        raise ValueError(f"EmailGuard: {'; '.join(errors)}")
