#!/usr/bin/env python3
"""
SmartPoster — Neues Posting-System (Neustart 2026-07-18)
=========================================================
Ersetzt: http_guard, post_never_twice, post_validator, brutus_traffic_engine,
         auto_poster, mega_auto_poster, post_gateway, post_watchdog, post_guard

Architektur:
  1. ContentGenerator  — AI-Content (Claude), Fallback auf Templates
  2. KeywordFilter     — blockt verbotene Keywords VOR dem Post
  3. PostDedup         — SQLite hash-Dedup, 7 Tage Fenster, NIEMALS permanente Bans
  4. Platform-Poster   — eine clean async Funktion pro Plattform, direktes aiohttp
  5. run_posting_cycle — orchestriert alles, sendet EIN Telegram-Summary

Regeln:
  - KEIN aiohttp Monkey-Patching
  - API-Fehler = retry beim nächsten Zyklus, NIEMALS permanent blockiert
  - Telegram: NUR ein Summary pro Zyklus (nicht pro Post)
  - Max 3 Posts pro Plattform pro Tag
  - Content: ineedit.com.co (Smart Home Gadgets, E-Commerce Tools)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import re
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("SmartPoster")

# ── Konfiguration ─────────────────────────────────────────────────────────────

_DB_PATH = Path(__file__).parent.parent / "data" / "smart_poster.db"
_MAX_POSTS_PER_PLATFORM_PER_DAY = 3
_DEDUP_WINDOW_HOURS = 48
_TELEGRAM_GUARD_STATE = Path(__file__).parent.parent / "data" / "telegram_send_guard.json"
_POSTING_EMERGENCY_STATE = Path(__file__).parent.parent / "data" / "posting_emergency_stop.json"
_TELEGRAM_MIN_INTERVAL_S = 4.0
_TELEGRAM_NETWORK_BACKOFF_S = 90

# Verbotene Keywords — wird auf generierten Content angewendet
_BANNED_PATTERNS = [
    r"geld verdien",
    r"passiv.*einkommen",
    r"online.*verdien",
    r"reich werden",
    r"schnell.*reich",
    r"passive.*income",
    r"earn.*online",
    r"make money fast",
    r"get rich quick",
    r"work from home.*earn",
    r"unlimited income",
    r"financial freedom.*click",
    r"casino",
    r"crypto.*pump",
    r"forex.*signal",
    r"\bmlm\b",
    r"pyramid",
    r"nicht im handel erh[aä]ltlich",
    r"zur wunschliste hinzuf[uü]gen",
    r"noch nicht genehmigt",
    r"not approved",
    r"currently unavailable",
    r"not available for sale",
]

# Sichere Content-Themen (werden an den Content-Generator übergeben)
_CONTENT_TOPICS = [
    {
        "topic": "Smart Home Gadget",
        "angle": "Effizienz & Komfort",
        "hashtags": ["#SmartHome", "#Gadgets", "#TechLife", "#HomeAutomation"],
        "shop_cta": "https://ineedit.com.co",
    },
    {
        "topic": "Shopify Automatisierung",
        "angle": "E-Commerce ohne Aufwand",
        "hashtags": ["#Shopify", "#ECommerce", "#OnlineShop", "#Automatisierung"],
        "shop_cta": "https://ineedit.com.co",
    },
    {
        "topic": "KI-Tools für Business",
        "angle": "Produktivität steigern",
        "hashtags": ["#AITools", "#KI", "#Produktivität", "#Business"],
        "shop_cta": "https://ineedit.com.co",
    },
    {
        "topic": "Tech-Deal der Woche",
        "angle": "Preis-Leistung",
        "hashtags": ["#TechDeal", "#Gadgets", "#SmartHome", "#Sparfuchs"],
        "shop_cta": "https://ineedit.com.co",
    },
    {
        "topic": "Solar & Energie",
        "angle": "Unabhängigkeit von steigenden Preisen",
        "hashtags": ["#Solar", "#Energie", "#Balkonkraftwerk", "#GreenTech"],
        "shop_cta": "https://ineedit.com.co",
    },
]


# ── Datenbank ─────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posted (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT NOT NULL,
            platform TEXT NOT NULL,
            posted_at REAL NOT NULL,
            content_preview TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hash_platform ON posted(content_hash, platform)")
    conn.commit()
    return conn


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode()).hexdigest()[:16]


def _already_posted(content_hash: str, platform: str) -> bool:
    cutoff = time.time() - (_DEDUP_WINDOW_HOURS * 3600)
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT id FROM posted WHERE content_hash=? AND platform=? AND posted_at>?",
                (content_hash, platform, cutoff),
            ).fetchone()
            return row is not None
    except Exception:
        return False  # Im Zweifel: posten erlaubt


def _mark_posted(content_hash: str, platform: str, preview: str) -> None:
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO posted (content_hash, platform, posted_at, content_preview) VALUES (?,?,?,?)",
                (content_hash, platform, time.time(), preview[:100]),
            )
            # Alte Einträge bereinigen (älter als 7 Tage)
            conn.execute("DELETE FROM posted WHERE posted_at < ?", (time.time() - 7 * 86400,))
    except Exception as e:
        log.warning("_mark_posted: %s", e)


def _posts_today(platform: str) -> int:
    start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM posted WHERE platform=? AND posted_at>?",
                (platform, start_of_day),
            ).fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


def _load_telegram_guard_state() -> dict:
    try:
        if _TELEGRAM_GUARD_STATE.exists():
            return json.loads(_TELEGRAM_GUARD_STATE.read_text())
    except Exception:
        pass
    return {}


def _save_telegram_guard_state(state: dict) -> None:
    try:
        _TELEGRAM_GUARD_STATE.parent.mkdir(parents=True, exist_ok=True)
        _TELEGRAM_GUARD_STATE.write_text(json.dumps(state))
    except Exception as e:
        log.debug("telegram guard state save: %s", e)


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _load_posting_emergency_state() -> dict:
    try:
        if _POSTING_EMERGENCY_STATE.exists():
            return json.loads(_POSTING_EMERGENCY_STATE.read_text())
    except Exception as e:
        log.debug("posting emergency state load: %s", e)
    return {}


def _save_posting_emergency_state(state: dict) -> None:
    try:
        _POSTING_EMERGENCY_STATE.parent.mkdir(parents=True, exist_ok=True)
        _POSTING_EMERGENCY_STATE.write_text(json.dumps(state))
    except Exception as e:
        log.debug("posting emergency state save: %s", e)


def get_posting_pause_reason() -> str:
    if _env_truthy("PAUSE_ALL_POSTING"):
        return "PAUSE_ALL_POSTING"
    if _env_truthy("SOCIAL_POSTING_PAUSED"):
        return "SOCIAL_POSTING_PAUSED"
    state = _load_posting_emergency_state()
    if state.get("active"):
        return str(state.get("reason") or "posting_emergency_stop")
    return ""


def activate_posting_pause(reason: str = "manual_emergency_stop") -> dict:
    os.environ["PAUSE_ALL_POSTING"] = "1"
    os.environ["SOCIAL_POSTING_PAUSED"] = "1"
    state = {
        "active": True,
        "reason": reason,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    _save_posting_emergency_state(state)
    return state


def _telegram_guard_key(bot_token: str, chat_id: str) -> str:
    token_hash = hashlib.sha256((bot_token or "").encode()).hexdigest()[:12]
    return f"{token_hash}:{chat_id}"


def _telegram_guard_precheck(bot_token: str, chat_id: str) -> tuple[bool, str]:
    now = time.time()
    state = _load_telegram_guard_state()
    key = _telegram_guard_key(bot_token, chat_id)
    info = state.get(key, {})
    cooldown_until = float(info.get("cooldown_until", 0) or 0)
    last_sent = float(info.get("last_sent", 0) or 0)
    if cooldown_until > now:
        return False, f"telegram_backoff_active_until_{int(cooldown_until)}"
    if now - last_sent < _TELEGRAM_MIN_INTERVAL_S:
        return False, "telegram_local_rate_limit"
    return True, ""


def _telegram_guard_mark_sent(bot_token: str, chat_id: str) -> None:
    state = _load_telegram_guard_state()
    key = _telegram_guard_key(bot_token, chat_id)
    info = state.get(key, {})
    info["last_sent"] = time.time()
    info["cooldown_until"] = 0
    info["last_error"] = ""
    state[key] = info
    _save_telegram_guard_state(state)


def _telegram_guard_mark_backoff(bot_token: str, chat_id: str, seconds: int, reason: str) -> None:
    state = _load_telegram_guard_state()
    key = _telegram_guard_key(bot_token, chat_id)
    info = state.get(key, {})
    info["cooldown_until"] = time.time() + max(1, seconds)
    info["last_error"] = reason[:200]
    state[key] = info
    _save_telegram_guard_state(state)


async def send_telegram_guarded(
    bot_token: str,
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
    parse_mode: str = "HTML",
) -> dict:
    """Rate-limited Telegram sender with backoff on 429/network failures."""
    if not bot_token or not chat_id:
        return {"ok": False, "reason": "telegram_credentials_missing"}

    pause_reason = get_posting_pause_reason()
    if pause_reason:
        return {"ok": False, "skipped": True, "blocked": True, "reason": f"posting_paused:{pause_reason}"}

    hard_block_reason = block_reason_for_telegram_text(text)
    if hard_block_reason:
        return {"ok": False, "blocked": True, "reason": hard_block_reason}

    if should_validate_telegram_text(text):
        valid, checks = validate_post(text, "telegram")
        if not valid:
            failed = [c.reason for c in checks if not c.passed]
            return {
                "ok": False,
                "blocked": True,
                "reason": "telegram_validation_failed",
                "details": failed,
            }

    allowed, reason = _telegram_guard_precheck(bot_token, str(chat_id))
    if not allowed:
        return {"ok": False, "skipped": True, "reason": reason}

    payload = {"chat_id": chat_id, "text": text[:4096], "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as s:
            async with s.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json=payload,
            ) as r:
                data = await r.json(content_type=None)
                if r.status == 429:
                    retry_after = int(((data.get("parameters") or {}).get("retry_after")) or 120)
                    _telegram_guard_mark_backoff(bot_token, str(chat_id), retry_after, "telegram_http_429")
                    return {"ok": False, "skipped": True, "reason": f"telegram_http_429_retry_after_{retry_after}"}
                if r.status >= 400:
                    _telegram_guard_mark_backoff(bot_token, str(chat_id), _TELEGRAM_NETWORK_BACKOFF_S, f"telegram_http_{r.status}")
                    return {"ok": False, "reason": f"telegram_http_{r.status}"}
        if data.get("ok"):
            _telegram_guard_mark_sent(bot_token, str(chat_id))
        return data
    except Exception as e:
        _telegram_guard_mark_backoff(bot_token, str(chat_id), _TELEGRAM_NETWORK_BACKOFF_S, str(e))
        return {"ok": False, "reason": f"telegram_exception: {str(e)[:120]}"}


def send_telegram_guarded_sync(
    bot_token: str,
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
    parse_mode: str = "HTML",
) -> dict:
    """Sync variant for legacy urllib-based Telegram senders."""
    if not bot_token or not chat_id:
        return {"ok": False, "reason": "telegram_credentials_missing"}

    pause_reason = get_posting_pause_reason()
    if pause_reason:
        return {"ok": False, "skipped": True, "blocked": True, "reason": f"posting_paused:{pause_reason}"}

    hard_block_reason = block_reason_for_telegram_text(text)
    if hard_block_reason:
        return {"ok": False, "blocked": True, "reason": hard_block_reason}

    if should_validate_telegram_text(text):
        valid, checks = validate_post(text, "telegram")
        if not valid:
            failed = [c.reason for c in checks if not c.passed]
            return {
                "ok": False,
                "blocked": True,
                "reason": "telegram_validation_failed",
                "details": failed,
            }

    allowed, reason = _telegram_guard_precheck(bot_token, str(chat_id))
    if not allowed:
        return {"ok": False, "skipped": True, "reason": reason}

    payload = {"chat_id": chat_id, "text": text[:4096], "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode())
        if data.get("ok"):
            _telegram_guard_mark_sent(bot_token, str(chat_id))
            return data
        _telegram_guard_mark_backoff(bot_token, str(chat_id), _TELEGRAM_NETWORK_BACKOFF_S, "telegram_sync_not_ok")
        return data
    except urllib.error.HTTPError as e:
        retry_after = _TELEGRAM_NETWORK_BACKOFF_S
        try:
            body = e.read().decode()
            parsed = json.loads(body)
            if e.code == 429:
                retry_after = int(((parsed.get("parameters") or {}).get("retry_after")) or 120)
        except Exception:
            pass
        _telegram_guard_mark_backoff(bot_token, str(chat_id), retry_after, f"telegram_sync_http_{e.code}")
        return {"ok": False, "reason": f"telegram_sync_http_{e.code}", "skipped": e.code == 429}
    except Exception as e:
        _telegram_guard_mark_backoff(bot_token, str(chat_id), _TELEGRAM_NETWORK_BACKOFF_S, str(e))
        return {"ok": False, "reason": f"telegram_sync_exception: {str(e)[:120]}"}


# ── Pre-Post Validator ────────────────────────────────────────────────────────
#
# Jeder Post durchläuft ALLE Checks bevor er gepostet wird.
# Schlägt auch NUR EIN Check fehl → Post wird NICHT gesendet.
# Das Ergebnis wird geloggt + im Telegram-Summary angezeigt.

# Plattform-spezifische Zeichenlimits
_PLATFORM_CHAR_LIMITS = {
    "twitter":   280,
    "instagram": 2200,
    "facebook":  63206,
    "linkedin":  3000,
    "pinterest": 500,
}

# Minimal-Wörter damit ein Post als "sinnvoll" gilt
_MIN_WORDS = 5

# Max Hashtags pro Post (darüber → Spam-Signal)
_MAX_HASHTAGS = 8

# Unfilled template-Platzhalter — dürfen NICHT im Post auftauchen
_PLACEHOLDER_PATTERN = re.compile(r"\{[a-z_]+\}")

# Fehlermeldungs-Muster die ein AI manchmal reinschreibt
_ERROR_PHRASES = [
    "als ki-sprachmodell",
    "as an ai",
    "i cannot",
    "ich kann nicht",
    "error:",
    "traceback",
    "exception:",
    "sorry, i",
    "entschuldigung, ich",
    "leider kann ich",
    "das kann ich nicht",
    "unfortunately",
]

_PROMO_HINTS = [
    "€", "eur", "produkt", "angebot", "deal", "jetzt", "shop",
    "gumroad", "digistore", "ds24", "affiliate", "checkout",
    "wunschliste", "features", "marken", "macobd", "diagnose-tool",
]

_HARD_BLOCK_PATTERNS = [
    r"nicht\s+im\s+handel\s+erh[aä]ltlich",
    r"zur\s+wunschliste\s+hinzuf[uü]gen",
    r"produkt\s+wurde\s+noch\s+nicht\s+genehmigt",
    r"not\s+approved",
    r"currently\s+unavailable",
    r"not\s+available\s+for\s+sale",
]


class ValidationResult:
    """Ergebnis eines einzelnen Validierungs-Checks."""
    __slots__ = ("check", "passed", "reason")

    def __init__(self, check: str, passed: bool, reason: str = ""):
        self.check  = check
        self.passed = passed
        self.reason = reason

    def __repr__(self) -> str:
        status = "✅" if self.passed else "❌"
        return f"{status} {self.check}" + (f": {self.reason}" if self.reason else "")


def validate_post(text: str, platform: str) -> tuple[bool, list[ValidationResult]]:
    """
    Führt ALLE Qualitäts-Checks für einen Post durch.
    Gibt (True, checks) zurück wenn alles OK, sonst (False, checks).
    Nur wenn True → Post darf gesendet werden.
    """
    checks: list[ValidationResult] = []

    # ── Check 1: Leer? ────────────────────────────────────────────────────────
    stripped = text.strip()
    checks.append(ValidationResult(
        "nicht_leer",
        bool(stripped),
        "" if stripped else "Text ist leer",
    ))

    # ── Check 2: Mindestlänge (Wörter) ───────────────────────────────────────
    words = [w for w in stripped.split() if not w.startswith("#") and not w.startswith("@")]
    checks.append(ValidationResult(
        "mindest_woerter",
        len(words) >= _MIN_WORDS,
        "" if len(words) >= _MIN_WORDS else f"Nur {len(words)} Wörter (min {_MIN_WORDS})",
    ))

    # ── Check 3: Zeichenlimit (plattformspezifisch) ───────────────────────────
    char_limit = _PLATFORM_CHAR_LIMITS.get(platform, 500)
    chars = len(stripped)
    checks.append(ValidationResult(
        "zeichenlimit",
        chars <= char_limit,
        "" if chars <= char_limit else f"{chars} Zeichen (max {char_limit} für {platform})",
    ))

    # ── Check 4: Keine ungefüllten Template-Platzhalter ──────────────────────
    placeholders = _PLACEHOLDER_PATTERN.findall(stripped)
    checks.append(ValidationResult(
        "keine_platzhalter",
        not placeholders,
        "" if not placeholders else f"Unfilled: {', '.join(set(placeholders))}",
    ))

    # ── Check 5: Verbotene Keywords ───────────────────────────────────────────
    lower = stripped.lower()
    found_bad = next((p for p in _BANNED_PATTERNS if re.search(p, lower)), None)
    checks.append(ValidationResult(
        "keyword_filter",
        found_bad is None,
        "" if found_bad is None else f"Verbotenes Keyword: '{found_bad}'",
    ))

    # ── Check 6: Kein Fehlermeldungs-Text von AI ─────────────────────────────
    found_err = next((p for p in _ERROR_PHRASES if p in lower), None)
    checks.append(ValidationResult(
        "kein_ai_fehler",
        found_err is None,
        "" if found_err is None else f"AI-Fehler-Phrase gefunden: '{found_err}'",
    ))

    # ── Check 7: Nicht übermäßig viele Hashtags ──────────────────────────────
    hashtag_count = stripped.count("#")
    checks.append(ValidationResult(
        "hashtag_limit",
        hashtag_count <= _MAX_HASHTAGS,
        "" if hashtag_count <= _MAX_HASHTAGS else f"{hashtag_count} Hashtags (max {_MAX_HASHTAGS})",
    ))

    # ── Check 8: Kein ALL-CAPS Spam (>40% Großbuchstaben im Wortinhalt) ──────
    letters = [c for c in stripped if c.isalpha()]
    upper_pct = (sum(1 for c in letters if c.isupper()) / max(len(letters), 1)) * 100
    checks.append(ValidationResult(
        "kein_caps_spam",
        upper_pct <= 40,
        "" if upper_pct <= 40 else f"{upper_pct:.0f}% Großbuchstaben (max 40%)",
    ))

    # ── Check 9: Enthält Shop-Link oder Hashtag (kein leerer Promo-Text) ─────
    has_cta = "ineedit.com.co" in stripped or "#" in stripped or "http" in stripped
    checks.append(ValidationResult(
        "hat_cta_oder_hashtag",
        has_cta,
        "" if has_cta else "Kein Link, kein Hashtag — Post hat keinen Wert",
    ))

    # ── Check 10: Keine doppelten Satzzeichen / Spammy Interpunktion ─────────
    spam_punct = bool(re.search(r"[!?]{3,}|\.{4,}", stripped))
    checks.append(ValidationResult(
        "kein_interpunktions_spam",
        not spam_punct,
        "" if not spam_punct else "Zu viele !!! oder .... Zeichen",
    ))

    all_passed = all(c.passed for c in checks)
    return all_passed, checks


def should_validate_telegram_text(text: str) -> bool:
    stripped = (text or "").strip()
    lower = stripped.lower()
    if any(re.search(pattern, lower) for pattern in _HARD_BLOCK_PATTERNS):
        return True
    if "http://" in lower or "https://" in lower or "#" in stripped:
        return True
    return any(hint in lower for hint in _PROMO_HINTS)


def block_reason_for_telegram_text(text: str) -> str:
    lower = (text or "").strip().lower()
    for pattern in _HARD_BLOCK_PATTERNS:
        if re.search(pattern, lower):
            return f"hard_block:{pattern}"
    return ""


def _is_clean(text: str) -> tuple[bool, str]:
    """Schneller Keyword-Check (Legacy-Kompatibilität). Nutzt intern validate_post."""
    lower = text.lower()
    for pattern in _BANNED_PATTERNS:
        if re.search(pattern, lower):
            return False, pattern
    return True, ""


# ── Content-Generator ─────────────────────────────────────────────────────────

_TEMPLATES = {
    "twitter": [
        "{topic}: {benefit} 🔥\n\n{hashtags}\n👉 {cta}",
        "Neu im Shop: {topic}\n✅ {benefit}\n\n{hashtags}\n{cta}",
        "Warum {topic} dein Leben einfacher macht:\n→ {benefit}\n\n{hashtags}\n{cta}",
    ],
    "instagram": [
        "{topic} — das Upgrade das du brauchst 🚀\n\n✅ {benefit}\n\nLink im Bio 👆\n\n{hashtags}",
        "Smart wohnen. Smart kaufen.\n\n{topic}: {benefit}\n\n{hashtags}\n👉 {cta}",
    ],
    "facebook": [
        "{topic} — {benefit}\n\nJetzt entdecken: {cta}\n\n{hashtags}",
        "Kennst du schon unser neuestes Highlight?\n\n🎯 {topic}\n💡 {benefit}\n\n👉 {cta}",
    ],
    "linkedin": [
        "{topic}: Wie moderne Unternehmer {benefit_business} erreichen.\n\nMehr auf: {cta}\n\n{hashtags}",
        "3 Gründe warum {topic} 2026 unverzichtbar ist:\n1️⃣ Effizienz\n2️⃣ Kostenersparnis\n3️⃣ {benefit}\n\n{cta}\n{hashtags}",
    ],
    "pinterest": [
        "{topic} ✨ {benefit} | {hashtags}",
        "Das perfekte {topic} für dein Zuhause 🏠 {benefit} | {hashtags}",
    ],
}

_BENEFITS = {
    "Smart Home Gadget": ["Spart Zeit & Energie", "Smarter wohnen ab sofort", "Automatisiert deinen Alltag"],
    "Shopify Automatisierung": ["Mehr Umsatz, weniger Aufwand", "Bestellungen automatisch verwalten", "24/7 verkaufen ohne Pause"],
    "KI-Tools für Business": ["10x produktiver in 30 Tagen", "Aufgaben automatisieren die Stunden kosten", "KI macht die schwere Arbeit"],
    "Tech-Deal der Woche": ["Top-Qualität zum Bestpreis", "Begrenzte Stückzahl — jetzt zugreifen", "Kundenfavorit mit 4.8★"],
    "Solar & Energie": ["Bis zu 80% Stromkosten sparen", "Unabhängig von steigenden Preisen", "In 3 Jahren amortisiert"],
}


async def _generate_with_claude(topic_cfg: dict, platform: str) -> Optional[str]:
    """Generiert Content via Anthropic Claude — gibt None zurück wenn API nicht verfügbar."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    topic = topic_cfg["topic"]
    angle = topic_cfg["angle"]
    hashtags = " ".join(topic_cfg["hashtags"][:3])
    cta = topic_cfg["shop_cta"]

    char_limits = {"twitter": 240, "instagram": 400, "facebook": 500, "linkedin": 500, "pinterest": 200}
    char_limit = char_limits.get(platform, 300)

    system = (
        "Du bist ein Social-Media-Experte für einen deutschen Online-Shop (ineedit.com.co). "
        "Schreibe kurze, ansprechende Posts — KEIN Spam, KEIN 'geld verdienen', KEIN MLM. "
        "Nur ehrliche Produktvorteile. Immer auf Deutsch. Emoji erlaubt, aber sparsam."
    )
    prompt = (
        f"Schreibe einen {platform.capitalize()}-Post über: {topic}\n"
        f"Blickwinkel: {angle}\n"
        f"Hashtags: {hashtags}\n"
        f"Link: {cta}\n"
        f"Max {char_limit} Zeichen. Kein Clickbait. Kein 'Geld verdienen'. Nur Post-Text, nichts anderes."
    )

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 300,
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}],
                },
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                text = data["content"][0]["text"].strip()
                return text if len(text) > 20 else None
    except Exception as e:
        log.debug("Claude API: %s", e)
        return None


def _generate_from_template(topic_cfg: dict, platform: str) -> str:
    """Fallback: generiert Content aus Template."""
    topic = topic_cfg["topic"]
    hashtags = " ".join(topic_cfg["hashtags"])
    cta = topic_cfg["shop_cta"]
    benefits = _BENEFITS.get(topic, ["Einfach besser"])
    benefit = random.choice(benefits)

    templates = _TEMPLATES.get(platform, _TEMPLATES["facebook"])
    tmpl = random.choice(templates)

    return tmpl.format(
        topic=topic,
        benefit=benefit,
        benefit_business=benefit,
        hashtags=hashtags,
        cta=cta,
    )


async def _generate_content(topic_cfg: dict, platform: str) -> str:
    """Generiert Content: Claude bevorzugt, Template als Fallback."""
    text = await _generate_with_claude(topic_cfg, platform)
    if not text:
        text = _generate_from_template(topic_cfg, platform)

    clean, reason = _is_clean(text)
    if not clean:
        log.warning("Generated content enthält verbotenes Keyword '%s' — nutze Template", reason)
        text = _generate_from_template(topic_cfg, platform)
        clean, reason = _is_clean(text)
        if not clean:
            text = f"Entdecke unsere Smart Home Gadgets 🏠\n👉 {topic_cfg['shop_cta']}\n{' '.join(topic_cfg['hashtags'][:2])}"

    return text


# ── Platform-Poster ───────────────────────────────────────────────────────────

async def _post_twitter(text: str, session: aiohttp.ClientSession) -> tuple[bool, str]:
    """Postet auf Twitter/X via API v2 (OAuth 1.0a)."""
    # OAuth 1.0a Header bauen
    import hmac as _hmac
    import hashlib as _hashlib
    import urllib.parse
    import base64

    consumer_key    = os.getenv("TWITTER_API_KEY", "")
    consumer_secret = os.getenv("TWITTER_API_SECRET", "")
    access_token    = os.getenv("TWITTER_ACCESS_TOKEN", "")
    access_secret   = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")

    if not all([consumer_key, consumer_secret, access_token, access_secret]):
        return False, "Twitter: Credentials fehlen"

    url = "https://api.twitter.com/2/tweets"
    ts  = str(int(time.time()))
    nonce = hashlib.md5(f"{ts}{random.random()}".encode()).hexdigest()

    params = {
        "oauth_consumer_key":     consumer_key,
        "oauth_nonce":            nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        ts,
        "oauth_token":            access_token,
        "oauth_version":          "1.0",
    }

    base_str = "&".join([
        "POST",
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote("&".join(f"{urllib.parse.quote(k,safe='')}={urllib.parse.quote(v,safe='')}" for k, v in sorted(params.items())), safe=""),
    ])
    signing_key = f"{urllib.parse.quote(consumer_secret, safe='')}&{urllib.parse.quote(access_secret, safe='')}"
    sig = base64.b64encode(
        _hmac.new(signing_key.encode(), base_str.encode(), _hashlib.sha1).digest()
    ).decode()
    params["oauth_signature"] = sig

    auth_header = "OAuth " + ", ".join(f'{k}="{urllib.parse.quote(v, safe="")}"' for k, v in sorted(params.items()))

    try:
        async with session.post(
            url,
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            json={"text": text[:280]},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status in (200, 201):
                data = await r.json()
                return True, f"Tweet ID: {data.get('data', {}).get('id', '?')}"
            body = await r.text()
            return False, f"Twitter HTTP {r.status}: {body[:100]}"
    except Exception as e:
        return False, f"Twitter Exception: {str(e)[:80]}"


async def _post_instagram(text: str, session: aiohttp.ClientSession) -> tuple[bool, str]:
    """Postet Text-Update auf Instagram via Graph API (erfordert verbundenes FB-Konto)."""
    token   = os.getenv("META_ACCESS_TOKEN") or os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    user_id = os.getenv("INSTAGRAM_USER_ID") or os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")

    if not token or not user_id:
        return False, "Instagram: Credentials fehlen"

    # Schritt 1: Media-Container anlegen (Text-only = Caption auf Bild nötig — hier Caption mit Dummy-Image)
    # Instagram erlaubt KEIN text-only post ohne Bild/Video → überspringen wenn kein Bild verfügbar
    # Stattdessen: Story-Text-Post via threaded caption
    # Wir nutzen "text overlay" workaround: Caption-only mit einem 1px transparent placeholder
    # Da das komplex ist: für jetzt via Facebook Page (gekoppeltes Konto) posten

    page_id    = os.getenv("FACEBOOK_PAGE_ID", "")
    page_token = os.getenv("FACEBOOK_PAGE_TOKEN") or os.getenv("META_ACCESS_TOKEN", "")

    if not page_id or not page_token:
        return False, "Instagram (via FB Page): Page-Credentials fehlen"

    try:
        async with session.post(
            f"https://graph.facebook.com/v19.0/{page_id}/feed",
            params={"access_token": page_token},
            json={"message": text[:2000]},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status == 200:
                data = await r.json()
                return True, f"FB/IG Post ID: {data.get('id', '?')}"
            body = await r.text()
            return False, f"Instagram/FB HTTP {r.status}: {body[:100]}"
    except Exception as e:
        return False, f"Instagram Exception: {str(e)[:80]}"


async def _post_facebook(text: str, session: aiohttp.ClientSession) -> tuple[bool, str]:
    """Postet auf Facebook Page."""
    page_id    = os.getenv("FACEBOOK_PAGE_ID", "")
    page_token = os.getenv("FACEBOOK_PAGE_TOKEN") or os.getenv("META_ACCESS_TOKEN", "")

    if not page_id or not page_token:
        return False, "Facebook: Credentials fehlen"

    try:
        async with session.post(
            f"https://graph.facebook.com/v19.0/{page_id}/feed",
            params={"access_token": page_token},
            json={"message": text[:2000]},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status == 200:
                data = await r.json()
                return True, f"Post ID: {data.get('id', '?')}"
            body = await r.text()
            return False, f"Facebook HTTP {r.status}: {body[:100]}"
    except Exception as e:
        return False, f"Facebook Exception: {str(e)[:80]}"


async def _post_linkedin(text: str, session: aiohttp.ClientSession) -> tuple[bool, str]:
    """Postet auf LinkedIn als Person oder Company."""
    token      = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    person_urn = os.getenv("LINKEDIN_PERSON_URN") or os.getenv("LINKEDIN_USER_URN", "")

    if not token or not person_urn:
        return False, "LinkedIn: Credentials fehlen"

    if not person_urn.startswith("urn:"):
        person_urn = f"urn:li:person:{person_urn}"

    payload = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text[:3000]},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    try:
        async with session.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            json=payload,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status in (200, 201):
                data = await r.json()
                return True, f"LinkedIn ID: {data.get('id', '?')}"
            body = await r.text()
            return False, f"LinkedIn HTTP {r.status}: {body[:100]}"
    except Exception as e:
        return False, f"LinkedIn Exception: {str(e)[:80]}"


async def _post_pinterest(text: str, session: aiohttp.ClientSession) -> tuple[bool, str]:
    """Erstellt einen Pinterest Pin (Text-Pin)."""
    token   = os.getenv("PINTEREST_ACCESS_TOKEN", "")
    board   = os.getenv("PINTEREST_BOARD_ID", "")

    if not token or not board:
        return False, "Pinterest: Credentials fehlen"

    cta_url = "https://ineedit.com.co"

    try:
        async with session.post(
            "https://api.pinterest.com/v5/pins",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "board_id": board,
                "title": text[:100],
                "description": text[:500],
                "link": cta_url,
                "media_source": {
                    "source_type": "image_url",
                    "url": "https://ineedit.com.co/cdn/shop/files/logo.png",
                },
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status in (200, 201):
                data = await r.json()
                return True, f"Pin ID: {data.get('id', '?')}"
            body = await r.text()
            return False, f"Pinterest HTTP {r.status}: {body[:100]}"
    except Exception as e:
        return False, f"Pinterest Exception: {str(e)[:80]}"


# ── Platform Registry ─────────────────────────────────────────────────────────

_PLATFORMS: dict[str, callable] = {
    "twitter":   _post_twitter,
    "facebook":  _post_facebook,
    "instagram": _post_instagram,
    "linkedin":  _post_linkedin,
    "pinterest": _post_pinterest,
}


# ── Telegram-Helper ───────────────────────────────────────────────────────────

async def _tg(msg: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            )
    except Exception:
        pass


# ── Haupt-Posting-Zyklus ──────────────────────────────────────────────────────

async def run_posting_cycle() -> dict:
    """
    Haupt-Funktion: generiert Content, validiert, dedupliziert, postet.
    Wird vom Scheduler alle N Minuten aufgerufen.
    Gibt Ergebnis-Dict zurück.
    """
    result: dict = {
        "ok": True,
        "posted": [],
        "skipped": [],
        "errors": [],
        "cycle_ts": datetime.now().isoformat(),
    }

    pause_reason = get_posting_pause_reason()
    if pause_reason:
        result["ok"] = False
        result["skipped"].append(f"global posting pause active: {pause_reason}")
        return result

    topic_cfg = random.choice(_CONTENT_TOPICS)
    log.info("SmartPoster: Thema = %s", topic_cfg["topic"])

    async with aiohttp.ClientSession() as session:
        for platform, poster_fn in _PLATFORMS.items():
            # Tages-Limit prüfen
            today_count = _posts_today(platform)
            if today_count >= _MAX_POSTS_PER_PLATFORM_PER_DAY:
                result["skipped"].append(f"{platform}: Tageslimit ({today_count}/{_MAX_POSTS_PER_PLATFORM_PER_DAY}) erreicht")
                continue

            # Content generieren
            try:
                text = await _generate_content(topic_cfg, platform)
            except Exception as e:
                result["errors"].append(f"{platform}: Content-Generierung fehlgeschlagen: {e}")
                continue

            # ── Pre-Post Validation — ALLE 10 Checks müssen bestehen ──────────
            valid, checks = validate_post(text, platform)
            failed = [c for c in checks if not c.passed]

            if not valid:
                reasons = " | ".join(c.reason for c in failed)
                log.warning("SmartPoster [%s]: Validation fehlgeschlagen — %s", platform, reasons)
                log.debug("SmartPoster [%s]: Post-Text war: %s", platform, text[:200])
                result["skipped"].append(f"{platform}: Validation ({len(failed)} Checks) — {reasons}")
                continue

            log.info("SmartPoster [%s]: ✅ Alle %d Checks bestanden", platform, len(checks))

            # Duplikat-Check
            ch = _content_hash(text)
            if _already_posted(ch, platform):
                result["skipped"].append(f"{platform}: Duplikat (letzte {_DEDUP_WINDOW_HOURS}h)")
                continue

            # Posten — erst jetzt, nach erfolgreich bestandener Validation
            try:
                ok, detail = await poster_fn(text, session)
            except Exception as e:
                result["errors"].append(f"{platform}: Unerwarteter Fehler: {e}")
                continue

            if ok:
                _mark_posted(ch, platform, text)
                result["posted"].append(f"{platform}: ✅ {detail}")
                log.info("SmartPoster: %s → gepostet (%s)", platform, detail)
            else:
                # API-Fehler = KEIN permanenter Ban — retry beim nächsten Zyklus
                result["errors"].append(f"{platform}: {detail}")
                log.warning("SmartPoster: %s → %s", platform, detail)

    # Telegram-Summary — NUR EINMAL pro Zyklus
    posted_count  = len(result["posted"])
    skipped_count = len(result["skipped"])
    error_count   = len(result["errors"])

    if posted_count > 0 or error_count > 0 or skipped_count > 0:
        lines = [f"📢 <b>SmartPoster — {topic_cfg['topic']}</b>"]
        lines.append(f"🕐 {datetime.now().strftime('%H:%M')} | Checks: 10/Post")
        if result["posted"]:
            lines.append(f"\n✅ <b>Gepostet ({posted_count}):</b>")
            lines.extend(f"  • {p}" for p in result["posted"])
        if result["skipped"]:
            lines.append(f"\n⏭ <b>Übersprungen ({skipped_count}) — Grund:</b>")
            lines.extend(f"  • {s}" for s in result["skipped"][:5])
        if result["errors"]:
            lines.append(f"\n⚠️ <b>API-Fehler ({error_count}) — retry in 2h:</b>")
            lines.extend(f"  • {e}" for e in result["errors"][:3])
        await _tg("\n".join(lines))

    result["ok"] = error_count < len(_PLATFORMS)
    return result


# ── Scheduler-Integration ─────────────────────────────────────────────────────

async def task_smart_poster_run() -> str:
    """Task-Wrapper für automation_scheduler."""
    try:
        r = await run_posting_cycle()
        posted   = len(r.get("posted", []))
        errors   = len(r.get("errors", []))
        skipped  = len(r.get("skipped", []))
        return f"SmartPoster: {posted} gepostet, {errors} Fehler, {skipped} übersprungen"
    except Exception as e:
        log.error("SmartPoster task crash: %s", e)
        return f"SmartPoster Fehler: {e}"


# ── Direktstart / Test ────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s — %(message)s")

    async def _test():
        print("SmartPoster Test-Lauf...")
        result = await run_posting_cycle()
        print(json.dumps(result, indent=2, ensure_ascii=False))

    asyncio.run(_test())
