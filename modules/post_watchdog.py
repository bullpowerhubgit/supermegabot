#!/usr/bin/env python3
"""
Post-Wächter — Qualitätskontrolle vor jedem Social-Media-Post
==============================================================
Verhindert fehlerhafte Posts: Platzhalter, tote Links, Duplikate,
Spam-Wörter, zu kurze Texte, falsche Formatierung.

Verwendung:
    from modules.post_watchdog import validate_post, PostValidationError

    ok, issues = await validate_post(text, url=url, platform="facebook")
    if not ok:
        log.warning("Post abgebrochen: %s", issues)
        return

Oder als Decorator:
    @post_watchdog("twitter")
    async def send_tweet(text):
        ...
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

log = logging.getLogger("PostWatchdog")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "post_watchdog.db"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")


# ── DB (gesendete Posts speichern) ────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_posts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            hash        TEXT UNIQUE NOT NULL,
            platform    TEXT,
            text_short  TEXT,
            sent_at     TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blocked_posts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            platform    TEXT,
            text_short  TEXT,
            reasons     TEXT,
            blocked_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def _post_hash(text: str) -> str:
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


# ── Validierungs-Regeln ───────────────────────────────────────────────────────

# Platzhalter die NIEMALS in einem echten Post vorkommen dürfen
_PLACEHOLDER_PATTERNS = [
    r'\b(TODO|FIXME|PLACEHOLDER|FILL_IN|INSERT_HERE|LOREM|IPSUM)\b',
    r'\{[A-Z_]{3,}\}',          # {COMPANY_NAME}, {PRODUCT}
    r'\[.*?(hier|here|einfügen|insert|placeholder).*?\]',
    r'XXX|YYY|ZZZ',
    r'example\.com|test\.com|yourdomain\.com',
    r'@example|@test\.com',
    r'<[A-Z_]+>',               # <FILL_IN>
]

# Spam-Wörter die auf Plattformen zu Sperren führen
_SPAM_WORDS = [
    r'\bkostenloses\s+geld\b', r'\bschnell\s+reich\b',
    r'\bkein\s+risiko\b', r'\b100%\s+garantiert\b',
    r'\bsofortiger\s+verdienst\b', r'\bgeldmaschine\b',
    r'\bpassives\s+einkommen\s+ohne\s+arbeit\b',
    r'click\s+here\s+now', r'buy\s+now\s+!!',
]

# Mindestlängen pro Plattform
_MIN_LENGTH = {
    "twitter": 20,
    "x": 20,
    "facebook": 30,
    "instagram": 30,
    "telegram": 10,
    "default": 20,
}

# Maximallängen
_MAX_LENGTH = {
    "twitter": 280,
    "x": 280,
    "facebook": 63206,
    "instagram": 2200,
    "telegram": 4096,
    "default": 5000,
}

# Erlaubte Wiederholungsintervalle in Stunden
_MIN_REPEAT_HOURS = {
    "twitter": 24,
    "x": 24,
    "facebook": 6,
    "instagram": 12,
    "telegram": 2,
    "default": 6,
}


async def _check_url_live(url: str) -> Tuple[bool, str]:
    """Prüft ob eine URL erreichbar ist (HEAD-Request)."""
    if not HAS_AIOHTTP or not url:
        return True, ""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.head(url, timeout=aiohttp.ClientTimeout(total=6),
                              allow_redirects=True) as r:
                if r.status < 400:
                    return True, ""
                return False, f"URL {url[:60]} → HTTP {r.status}"
    except Exception as e:
        return False, f"URL {url[:60]} nicht erreichbar: {str(e)[:50]}"


def _check_duplicate(text: str, platform: str, hours: int) -> Tuple[bool, str]:
    """Prüft ob dieser Post bereits kürzlich gesendet wurde."""
    h = _post_hash(text)
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT sent_at FROM sent_posts WHERE hash=? AND sent_at > ?",
                (h, cutoff.isoformat())
            ).fetchone()
        if row:
            return True, f"Duplikat: identischer Post bereits {row['sent_at'][:16]} gesendet"
    except Exception:
        pass
    return False, ""


def _check_similar_recent(text: str, platform: str) -> Tuple[bool, str]:
    """Prüft ob ein sehr ähnlicher Post in den letzten 2h gesendet wurde."""
    words = set(re.findall(r'\b\w{5,}\b', text.lower()))
    if len(words) < 3:
        return False, ""
    cutoff = datetime.utcnow() - timedelta(hours=2)
    try:
        with _db() as conn:
            recent = conn.execute(
                "SELECT text_short FROM sent_posts WHERE platform=? AND sent_at > ?",
                (platform, cutoff.isoformat())
            ).fetchall()
        for row in recent:
            recent_words = set(re.findall(r'\b\w{5,}\b', (row["text_short"] or "").lower()))
            if len(words & recent_words) / max(len(words), 1) > 0.75:
                return True, "Ähnlicher Post bereits in den letzten 2h gesendet (>75% Wort-Überlappung)"
    except Exception:
        pass
    return False, ""


# ── Haupt-Validierung ─────────────────────────────────────────────────────────

async def validate_post(
    text: str,
    platform: str = "default",
    url: Optional[str] = None,
    check_url: bool = True,
    strict: bool = False,
) -> Tuple[bool, List[str]]:
    """
    Validiert einen Post vor dem Senden.

    Returns:
        (ok: bool, issues: List[str])
        ok=True → Post darf gesendet werden
        ok=False → Post abgebrochen, issues enthält Gründe
    """
    platform = platform.lower()
    issues: List[str] = []

    if not text or not text.strip():
        return False, ["Post ist leer"]

    text = text.strip()

    # 0. NEVER-TWICE — gleicher Fehler/Content nie wieder
    try:
        from modules.post_never_twice import check_never_twice, remember_block
        nt_ok, nt_errs = check_never_twice(text, platform)
        if not nt_ok:
            try:
                remember_block(text, platform, nt_errs, source_module="post_watchdog")
            except Exception:
                pass
            return False, nt_errs
    except Exception as e:
        err = str(e).lower()
        if "locked" in err or "unable to open database file" in err or "busy" in err:
            return True, []
        return False, [f"NeverTwice fail-closed: {e}"]

    # 1. Längen-Check
    min_len = _MIN_LENGTH.get(platform, _MIN_LENGTH["default"])
    max_len = _MAX_LENGTH.get(platform, _MAX_LENGTH["default"])
    if len(text) < min_len:
        issues.append(f"Text zu kurz: {len(text)} Zeichen (min {min_len} für {platform})")
    if len(text) > max_len:
        issues.append(f"Text zu lang: {len(text)} Zeichen (max {max_len} für {platform})")

    # 2. Platzhalter-Check
    for pattern in _PLACEHOLDER_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            issues.append(f"Platzhalter erkannt: '{re.search(pattern, text, re.IGNORECASE).group()[:30]}'")
            break

    # 3. Spam-Wörter
    for pattern in _SPAM_WORDS:
        if re.search(pattern, text, re.IGNORECASE):
            issues.append(f"Spam-Wort erkannt: '{re.search(pattern, text, re.IGNORECASE).group()[:30]}'")

    # 4. Mehrfache Ausrufezeichen / übermäßige Emojis
    if re.search(r'[!?]{4,}', text):
        issues.append("Zu viele Ausrufezeichen/Fragezeichen hintereinander")
    emoji_count = len(re.findall(
        r'[\U00010000-\U0010ffff]|[☀-⛿]|[✀-➿]', text
    ))
    if emoji_count > 15:
        issues.append(f"Zu viele Emojis: {emoji_count} (max 15)")

    # 5. Fehlende/kaputte Links prüfen
    urls_in_text = re.findall(r'https?://[^\s<>"\']+', text)
    if check_url and HAS_AIOHTTP:
        all_urls = urls_in_text + ([url] if url else [])
        for u in all_urls[:3]:   # Max 3 URLs prüfen
            live, err = await _check_url_live(u)
            if not live:
                issues.append(f"Tote URL: {err}")

    # 6. Duplikat-Check
    hours = _MIN_REPEAT_HOURS.get(platform, _MIN_REPEAT_HOURS["default"])
    is_dup, dup_msg = _check_duplicate(text, platform, hours)
    if is_dup:
        issues.append(dup_msg)

    # 7. Ähnlichkeits-Check (nur bei strict=True oder Facebook/Instagram)
    if strict or platform in ("facebook", "instagram"):
        is_sim, sim_msg = _check_similar_recent(text, platform)
        if is_sim:
            issues.append(sim_msg)

    # 8. Encoding-Probleme (Sonderzeichen die zu Fragezeichen werden)
    if '???' in text or '�' in text:
        issues.append("Encoding-Fehler im Text erkannt (???, )")

    # 9. HTML-Tags im Text (unerwünscht auf Twitter/Instagram)
    if platform in ("twitter", "x", "instagram") and re.search(r'<[a-z]+[^>]*>', text):
        issues.append("HTML-Tags im Text für {platform} nicht erlaubt")

    ok = len(issues) == 0
    return ok, issues


def record_sent(text: str, platform: str) -> None:
    """Speichert einen erfolgreich gesendeten Post in der DB."""
    h = _post_hash(text)
    short = text[:200]
    try:
        with _db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sent_posts (hash, platform, text_short) VALUES (?,?,?)",
                (h, platform, short)
            )
    except Exception as e:
        log.warning("record_sent error: %s", e)


def record_blocked(text: str, platform: str, reasons: List[str]) -> None:
    """Speichert einen blockierten Post mit Gründen."""
    try:
        from modules.post_never_twice import remember_block
        remember_block(text, platform, reasons or ["blocked"], source_module="post_watchdog")
    except Exception:
        pass
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO blocked_posts (platform, text_short, reasons) VALUES (?,?,?)",
                (platform, text[:200], "; ".join(reasons))
            )
    except Exception as e:
        log.warning("record_blocked error: %s", e)


# ── Telegram Alert ────────────────────────────────────────────────────────────

async def _alert_blocked(text: str, platform: str, issues: List[str]) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT or not HAS_AIOHTTP:
        return
    msg = (
        f"🚫 <b>Post blockiert [{platform.upper()}]</b>\n"
        f"<b>Gründe:</b> {'; '.join(issues[:3])}\n"
        f"<b>Text:</b> <code>{text[:100]}...</code>"
    )
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg,
                      "parse_mode": "HTML", "disable_notification": True},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


# ── Decorator ─────────────────────────────────────────────────────────────────

def post_watchdog(platform: str = "default", strict: bool = False, silent: bool = False):
    """
    Decorator für Post-Funktionen.
    Blockiert fehlerhafte Posts automatisch.

    @post_watchdog("facebook")
    async def post_to_facebook(text: str) -> dict:
        ...
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(text: str, *args, **kwargs):
            ok, issues = await validate_post(text, platform=platform, strict=strict)
            if not ok:
                log.warning("PostWatchdog [%s] — BLOCKIERT: %s", platform, "; ".join(issues))
                record_blocked(text, platform, issues)
                if not silent:
                    await _alert_blocked(text, platform, issues)
                return {"blocked": True, "reasons": issues}
            result = await fn(text, *args, **kwargs)
            record_sent(text, platform)
            return result
        return wrapper
    return decorator


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats() -> Dict:
    try:
        with _db() as conn:
            total_sent = conn.execute("SELECT COUNT(*) FROM sent_posts").fetchone()[0]
            total_blocked = conn.execute("SELECT COUNT(*) FROM blocked_posts").fetchone()[0]
            recent_blocked = conn.execute(
                "SELECT platform, text_short, reasons, blocked_at FROM blocked_posts "
                "ORDER BY blocked_at DESC LIMIT 5"
            ).fetchall()
            return {
                "total_sent": total_sent,
                "total_blocked": total_blocked,
                "recent_blocked": [dict(r) for r in recent_blocked],
            }
    except Exception as e:
        return {"error": str(e)}


# ── Standalone Test-Post ──────────────────────────────────────────────────────

async def run_test_posts() -> Dict:
    """Führt Test-Validierungen durch — zeigt was blockiert/erlaubt würde."""
    results = []
    test_cases = [
        ("Guter Post: KI-Automatisierung für Shopify — spare 5h/Woche! 🚀 Kostenlos testen: https://bullpower-hub.vercel.app", "facebook", True),
        ("TODO: hier Text einfügen", "twitter", False),
        ("a", "instagram", False),
        ("Schnell reich werden ohne Arbeit!!! Garantiert 100% passives Einkommen!!!", "twitter", False),
        ("Super Produkt für dein Business! Jetzt kaufen und sparen! ✅", "telegram", True),
        ("{COMPANY_NAME} braucht dich jetzt!", "facebook", False),
        ("X" * 300, "twitter", False),
    ]
    for text, platform, expect_ok in test_cases:
        ok, issues = await validate_post(text, platform=platform, check_url=False)
        status = "✅ OK" if ok else f"🚫 BLOCKIERT ({'; '.join(issues[:2])})"
        expected = "✅" if expect_ok else "🚫"
        match = "✓" if ok == expect_ok else "✗ FALSCH"
        results.append({
            "text": text[:50],
            "platform": platform,
            "ok": ok,
            "issues": issues,
            "expected": expect_ok,
            "match": match,
        })
    return {"test_results": results, "passed": sum(1 for r in results if r["match"] == "✓")}


if __name__ == "__main__":
    import asyncio
    import json
    r = asyncio.run(run_test_posts())
    for t in r["test_results"]:
        print(f"{'✓' if t['match']=='✓' else '✗'} [{t['platform']}] {t['text'][:40]}")
        if t["issues"]:
            print(f"   Issues: {t['issues'][:2]}")
    print(f"\n{r['passed']}/{len(r['test_results'])} Tests bestanden")
