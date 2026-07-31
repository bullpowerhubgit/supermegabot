#!/usr/bin/env python3
"""
Telegram Post Monitor — Tiefe Inhalts-Analyse alle 5 Minuten
=============================================================
Prüft:
  1. Alle gesendeten + blockierten Posts aus post_gateway.db
  2. Inhalt: Banned Keywords, Prompt-Leaks, Duplikat-Loops, falsche Hashtags
  3. URL-Validierung aller Links in Posts der letzten 24h
  4. DS24-Produkt-Blacklist: Produkte die "nicht genehmigt" zeigen
  5. Bot-Status: Webhook erreichbar, kein Rückstau
  6. Send-Guard: Stuck Cooldowns auto-bereinigen
  7. Fehlerrate: Verhältnis sent / failed / blocked
  8. Telegram-Alert NUR bei Fehlern; Entwarnung wenn wieder OK
"""
from __future__ import annotations

import asyncio
import html as html_mod
import json
import logging
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp

_HTML_TAG_RE = re.compile(r"<[^>]+>")

def _safe(text: str, max_len: int = 80) -> str:
    """Entfernt HTML-Tags + escaped verbleibende Sonderzeichen für Telegram HTML-Mode."""
    clean = _HTML_TAG_RE.sub("", text or "")
    return html_mod.escape(clean[:max_len])

# ── .env laden (LaunchAgent hat keine Shell-Umgebung) ────────────────────────
def _load_dotenv() -> None:
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val

_load_dotenv()

# ── Konfiguration ─────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOG_PATH = DATA_DIR / "telegram_monitor.log"
MONITOR_STATE = DATA_DIR / "telegram_monitor_state.json"

BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "8600739487:AAHk_DEJa7O5HM6oajH8ArNtOmgW_5Jt0O8")
ADMIN_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5088771245")
SHOP_URL      = f"https://{os.getenv('SHOPIFY_PUBLIC_DOMAIN', 'ineedit.com.co')}"

SEND_GUARD_FILE = DATA_DIR / "telegram_send_guard.json"
SMART_POSTER_DB = DATA_DIR / "smart_poster.db"
POST_GATEWAY_DB = DATA_DIR / "post_gateway.db"

# ── Content-Checks ────────────────────────────────────────────────────────────

_BANNED_PATTERNS = [
    (r"geld verdien",               "Einkommensversprechen"),
    (r"passiv.*einkommen",          "Passiveinkommen-Claim"),
    (r"reich werden|schnell.*reich","Reich-werden-Versprechen"),
    (r"t[aä]glich\s*[€$]?\d+",    "Täglicher Verdienst-Claim"),
    (r"\d+\s*[€$]\s*(pro\s*tag)",  "Tagesverdienstversprechen"),
    (r"heute\s+gratis",             "Gratis-Heute-Spam"),
    (r"casino|forex.*signal|crypto.*pump", "Finanz-Spam"),
    (r"\bmlm\b|pyramid",           "MLM/Pyramid-Scheme"),
    (r"nicht im handel erh[aä]ltlich",     "DS24-Fehlertext"),
    (r"zur wunschliste hinzuf[uü]gen",     "DS24-Fehlertext"),
    (r"noch nicht genehmigt|not approved", "Nicht-genehmigt-Text"),
    (r"currently unavailable|not available for sale", "Nicht-verfügbar-Text"),
]

_ERROR_PHRASES = [
    "als ki-sprachmodell", "as an ai", "i cannot", "ich kann nicht",
    "error:", "traceback", "exception:", "sorry, i", "entschuldigung, ich",
    "leider kann ich", "das kann ich nicht", "unfortunately",
]

_PROMPT_LEAK_PATTERNS = [
    (r"\*\s*topic\s*:", "Prompt-Leak: * Topic:"),
    (r"\*\s*product\s*:", "Prompt-Leak: * Product:"),
    (r"\*\s*format\s*:", "Prompt-Leak: * Format:"),
    (r"\*\s*style\s*:", "Prompt-Leak: * Style:"),
    (r"\*\s*link\s*:", "Prompt-Leak: * Link:"),
    (r"\*\s*constraints?\s*:", "Prompt-Leak: * Constraints:"),
    (r"translate only descriptive", "Prompt-Leak: translate-instruction"),
    (r"keep brand names", "Prompt-Leak: brand-instruction"),
    (r"tone:\s*modern", "Prompt-Leak: tone-instruction"),
    (r"max\.?\s*2\s*sentences", "Prompt-Leak: length-instruction"),
]

# Falsche Hashtags bei digitalen Produkten
_DIGITAL_PRODUCTS_KEYWORDS = ["gumroad", "ki-automation", "ki-marketing", "autopilot",
                               "kurs", "mastery", "bundle", "digital", "ebook", "online-kurs"]
_WRONG_HASHTAGS_FOR_DIGITAL = ["#smarthome", "#homeautomation", "#iot", "#smart_home"]

# DS24 Produkte die geblockt werden
_DS24_BLOCKED_IDS = {"704330", "668035", "669750", "704677"}

_URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+")

_BAD_PAGE_PATTERNS = [
    "noch nicht genehmigt", "nicht genehmigt", "produkt nicht verfügbar",
    "page not found", "404 not found", "error 404", "not available",
    "product unavailable", "seite nicht gefunden",
]

# ── Logging ───────────────────────────────────────────────────────────────────

DATA_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_PATH)),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("TelegramMonitor")


# ── Zustand ───────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    defaults = {"last_run": 0, "errors_found": 0, "last_error_summary": "",
                "known_issues": {}, "last_alert_key": ""}
    try:
        saved = json.loads(MONITOR_STATE.read_text())
        # Fehlende Keys aus defaults ergänzen (Rückwärtskompatibilität)
        for k, v in defaults.items():
            saved.setdefault(k, v)
        return saved
    except Exception:
        return defaults

def _save_state(state: dict) -> None:
    MONITOR_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


# ── Post-Gateway DB: Haupt-Datenquelle ───────────────────────────────────────

def _read_gateway_posts(hours: int = 24) -> list[dict]:
    """Liest alle Posts der letzten N Stunden aus post_gateway.db."""
    posts = []
    since_ts = time.time() - hours * 3600
    since_str = datetime.fromtimestamp(since_ts).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = sqlite3.connect(str(POST_GATEWAY_DB), timeout=5)
        rows = conn.execute(
            "SELECT platform, status, preview, errors, ts FROM posts "
            "WHERE platform='telegram' AND ts >= ? ORDER BY ts DESC",
            (since_str,)
        ).fetchall()
        conn.close()
        for plat, status, preview, errors_json, ts in rows:
            try:
                errs = json.loads(errors_json) if errors_json else []
            except Exception:
                errs = [errors_json] if errors_json else []
            posts.append({
                "source": "gateway_posts",
                "platform": plat,
                "status": status,
                "text": preview or "",
                "errors": errs,
                "ts": ts,
            })
    except Exception as e:
        log.debug("gateway_posts Lesefehler: %s", e)
    return posts


def _read_gateway_blocked(hours: int = 24) -> list[dict]:
    """Liest alle blockierten Posts der letzten N Stunden."""
    blocked = []
    since_ts = time.time() - hours * 3600
    since_str = datetime.fromtimestamp(since_ts).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = sqlite3.connect(str(POST_GATEWAY_DB), timeout=5)
        rows = conn.execute(
            "SELECT platform, reason, preview, ts FROM blocked "
            "WHERE platform='telegram' AND ts >= ? ORDER BY ts DESC",
            (since_str,)
        ).fetchall()
        conn.close()
        for plat, reason, preview, ts in rows:
            blocked.append({
                "source": "gateway_blocked",
                "platform": plat,
                "status": "blocked",
                "reason": reason or "",
                "text": preview or "",
                "ts": ts,
            })
    except Exception as e:
        log.debug("gateway_blocked Lesefehler: %s", e)
    return blocked


def _read_send_guard_posts() -> list[dict]:
    """Liest zuletzt gesendete Texte aus send_guard.json."""
    posts = []
    try:
        guard = json.loads(SEND_GUARD_FILE.read_text())
        for key, val in guard.items():
            if isinstance(val, dict) and val.get("last_text"):
                posts.append({
                    "source": "send_guard",
                    "key": key,
                    "text": val["last_text"],
                    "status": "sent",
                    "sent_at": val.get("last_sent", 0),
                    "last_error": val.get("last_error", ""),
                })
    except Exception:
        pass
    return posts


# ── Tiefe Inhalts-Analyse ─────────────────────────────────────────────────────

def _analyze_content(text: str, source: str = "", errors: list = None) -> list[str]:
    """Vollständige Inhalts-Analyse. Gibt Liste von Fehlern zurück."""
    issues = []
    if not text or len(text.strip()) < 5:
        return []

    stripped = text.strip()
    lower = stripped.lower()

    # 1. Banned Keywords
    for pattern, label in _BANNED_PATTERNS:
        if re.search(pattern, lower):
            issues.append(f"🚫 {label}: '{pattern[:40]}'")
            break

    # 2. AI-Fehlerphrases
    for phrase in _ERROR_PHRASES:
        if phrase in lower:
            issues.append(f"🤖 AI-Fehlerphrase: '{phrase}'")
            break

    # 3. Prompt-Leaks
    for pattern, label in _PROMPT_LEAK_PATTERNS:
        if re.search(pattern, lower):
            issues.append(f"📋 {label}")
            break

    # 4. Ungefüllte Platzhalter
    placeholders = re.findall(r"\{[a-z_]+\}", stripped)
    if placeholders:
        issues.append(f"📝 Ungefüllte Platzhalter: {', '.join(set(placeholders[:3]))}")

    # 5. Localhost/Admin-Links
    if "localhost" in lower or "127.0.0.1" in lower:
        issues.append("🔗 Localhost-Link im Post!")
    if "myshopify.com/admin" in lower:
        issues.append("🔗 Shopify-Admin-Link im Post!")

    # 6. Geblockte DS24-Produkte
    for blocked_id in _DS24_BLOCKED_IDS:
        if f"/product/{blocked_id}" in lower:
            issues.append(f"🛑 Geblockte DS24-Produkt-ID: {blocked_id} (nicht genehmigt)")
            break

    # 7. Falsche Hashtags für digitale Produkte
    is_digital = any(kw in lower for kw in _DIGITAL_PRODUCTS_KEYWORDS)
    if is_digital:
        wrong_tags = [t for t in _WRONG_HASHTAGS_FOR_DIGITAL if t in lower]
        if wrong_tags:
            issues.append(f"🏷️ Falsche Hashtags für Digitalprodukt: {', '.join(wrong_tags)}")

    # 8. Zu viele Ausrufezeichen
    if re.search(r"[!?]{4,}", stripped):
        issues.append("❗ Interpunktions-Spam: zu viele !!!! oder ????")

    # 9. Mehr als 60% Großbuchstaben
    letters = [c for c in stripped if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6:
        issues.append("🔊 Zu viele Großbuchstaben (>60%) — sieht nach Spam aus")

    # 10. Bekannte Fehler aus post_gateway.db errors-Feld analysieren
    if errors:
        for err in errors:
            e = str(err).lower()
            if "noch nicht genehmigt" in e or "nicht genehmigt" in e:
                issues.append("🛑 DS24: Produkt nicht genehmigt — Link muss entfernt werden")
            elif "hard_block" in e and "product:" in e:
                issues.append("📋 Prompt-Instruktion im Text gefunden (hard_block)")
            elif "telegram_validation_failed" in e:
                issues.append("⚠️ Telegram Validation failed — Markdown/HTML-Konflikt im Text")
            elif "link_check_failed" in e and "timeout" in e:
                issues.append("⏱️ Link-Timeout: URL antwortet zu langsam")

    # 11. Post zu kurz (< 25 Zeichen) — wahrscheinlich unvollständig
    if len(stripped) < 25:
        issues.append(f"✂️ Post zu kurz ({len(stripped)} Zeichen) — wahrscheinlich unvollständig")

    # 12. Post überschreitet Telegram-Limit (4096 Zeichen)
    if len(stripped) > 4096:
        issues.append(f"📏 Post zu lang ({len(stripped)} Zeichen > 4096 Telegram-Limit) — wird abgeschnitten")

    # 13. Lorem ipsum / Dummy-Text / Test-Inhalt
    dummy_patterns = ["lorem ipsum", "dummy text", "test post", "platzhalter", "sample text",
                      "hier text", "insert text", "your text here"]
    if any(d in lower for d in dummy_patterns):
        issues.append("🗑️ Dummy-Text / Platzhalter-Inhalt im Post!")

    # 14. Wiederholung innerhalb des Posts (gleicher Satz 2+ mal)
    sentences = [s.strip() for s in re.split(r'[.!?\n]', stripped) if len(s.strip()) > 15]
    if len(sentences) != len(set(sentences)):
        dup_sentence = next((s for s in sentences if sentences.count(s) > 1), "")
        issues.append(f"🔁 Satz doppelt im Post: '{dup_sentence[:40]}'")

    # 15. CTA ohne Link — ruft zum Klicken auf aber kein URL im Text
    cta_phrases = ["jetzt klicken", "hier klicken", "starte jetzt", "jetzt starten",
                   "jetzt kaufen", "mehr erfahren", "link in bio", "hier anmelden"]
    has_cta = any(p in lower for p in cta_phrases)
    has_url = "http" in lower
    if has_cta and not has_url:
        issues.append("🔗 CTA ohne URL — Call-to-Action aber kein Link im Text!")

    return issues


# ── Fehlerrate & Trends analysieren ──────────────────────────────────────────

def _compute_stats(gateway_posts: list, gateway_blocked: list) -> dict:
    """Berechnet Fehlerrate und häufigste Fehler."""
    total = len(gateway_posts) + len(gateway_blocked)
    sent = sum(1 for p in gateway_posts if p["status"] == "sent")
    failed = sum(1 for p in gateway_posts if p["status"] == "failed")
    blocked = len(gateway_blocked)

    # Häufigste Fehlerursachen
    error_counter: Counter = Counter()
    for p in gateway_posts:
        for err in (p.get("errors") or []):
            short = str(err)[:60].replace('"', "")
            if short:
                error_counter[short] += 1
    for b in gateway_blocked:
        reason = b.get("reason", "")[:60]
        if reason:
            error_counter[reason] += 1

    # Duplikat-Loop erkennen (gleicher Preview 5+ mal in 6h)
    preview_counter: Counter = Counter()
    for p in gateway_posts + gateway_blocked:
        preview = p.get("text", "")[:80]
        if preview:
            preview_counter[preview] += 1
    dupl_loops = [(text, cnt) for text, cnt in preview_counter.items() if cnt >= 5]

    return {
        "total": total,
        "sent": sent,
        "failed": failed,
        "blocked": blocked,
        "fail_rate_pct": int((failed + blocked) / max(total, 1) * 100),
        "top_errors": error_counter.most_common(5),
        "duplikat_loops": dupl_loops[:3],
    }


# ── URL-Validierung ───────────────────────────────────────────────────────────

async def _check_url(session: aiohttp.ClientSession, url: str) -> tuple[bool, str]:
    trusted = ["t.me", "telegram.me", "github.com", "stripe.com",
               "railway.app", "supabase.co", "klaviyo.com"]
    if any(t in url for t in trusted):
        return True, ""
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SuperMegaBot-Monitor/1.0)"}
        try:
            async with session.head(url, allow_redirects=True,
                                    timeout=timeout, headers=headers) as r:
                if r.status == 405:
                    raise Exception("HEAD blocked")
                if r.status >= 400:
                    return False, f"HTTP {r.status}"
                return True, ""
        except Exception:
            pass
        async with session.get(url, allow_redirects=True,
                               timeout=timeout, headers=headers) as r:
            if r.status >= 400:
                return False, f"HTTP {r.status}"
            body = (await r.text(errors="ignore"))[:4000].lower()
            for pattern in _BAD_PAGE_PATTERNS:
                if pattern in body:
                    return False, f"Fehlerseite: '{pattern}'"
            return True, ""
    except asyncio.TimeoutError:
        return False, "Timeout"
    except Exception as e:
        return False, f"{str(e)[:50]}"


def _is_valid_url(url: str) -> bool:
    """Filtert abgeschnittene/ungültige URLs (passiert wenn DB-Preview bei 100 Zeichen endet)."""
    if len(url) < 16:
        return False
    try:
        after_scheme = url.split("//", 1)[1] if "//" in url else url
        domain = after_scheme.split("/")[0].split("?")[0]
        # Muss einen Punkt haben UND nach dem letzten Punkt mind. 2 Chars (echte TLD)
        parts = domain.lstrip("www.").split(".")
        if len(parts) < 2:
            return False
        tld = parts[-1]
        return len(tld) >= 2 and len(tld) <= 8  # echte TLD: .com, .de, .io etc.
    except Exception:
        return False


async def _validate_urls_in_posts(posts: list[dict]) -> list[dict]:
    """Prüft URLs in Posts der letzten 12h. Gibt Fehler zurück."""
    url_errors = []
    cutoff = time.time() - 12 * 3600
    checked = set()

    async with aiohttp.ClientSession() as session:
        tasks = []
        for post in posts:
            ts_str = post.get("ts") or post.get("sent_at")
            try:
                if isinstance(ts_str, str):
                    ts = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S").timestamp()
                else:
                    ts = float(ts_str or 0)
            except Exception:
                ts = 0

            if ts < cutoff:
                continue

            text = post.get("text", "")
            urls = [u for u in _URL_RE.findall(text)[:5] if _is_valid_url(u)]
            for url in urls:
                if url in checked:
                    continue
                checked.add(url)
                # DS24 Produkt 704330 sofort flaggen ohne HTTP-Call
                if "checkout-ds24.com/product/704330" in url:
                    url_errors.append({
                        "url": url[:80],
                        "reason": "BEKANNT: Produkt 704330 nicht genehmigt (Blacklist)",
                        "post_preview": text[:60],
                    })
                    continue
                tasks.append((url, text, _check_url(session, url)))

        for url, text, coro in tasks:
            ok, reason = await coro
            if not ok:
                url_errors.append({
                    "url": url[:80],
                    "reason": reason,
                    "post_preview": text[:60],
                })

    return url_errors


# ── Bot-Status ────────────────────────────────────────────────────────────────

async def _check_bot_status() -> dict:
    result = {"ok": False, "bot_name": "", "webhook_url": "", "pending": 0}
    _timeout = aiohttp.ClientTimeout(total=15)

    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getMe",
                timeout=_timeout, ssl=True,
            ) as r:
                data = await r.json(content_type=None)
                if data.get("ok"):
                    result["ok"] = True
                    result["bot_name"] = data["result"].get("username", "")
                else:
                    log.warning("getMe nicht ok: %s", data)
                    return result
    except Exception as e:
        log.warning("Bot-Status getMe Fehler: %s", e)
        return result

    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo",
                timeout=_timeout, ssl=True,
            ) as r:
                data = await r.json(content_type=None)
                if data.get("ok"):
                    wi = data["result"]
                    result["webhook_url"]  = wi.get("url", "")
                    result["pending"]      = wi.get("pending_update_count", 0)
                    result["last_error"]   = wi.get("last_error_message", "")
                    result["last_error_date"] = wi.get("last_error_date", 0)
    except Exception as e:
        log.debug("getWebhookInfo Fehler (unkritisch): %s", e)

    return result


# ── Telegram-Alert ────────────────────────────────────────────────────────────

async def _tg_alert(text: str) -> bool:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as s:
            async with s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": ADMIN_CHAT_ID, "text": text[:4096],
                      "parse_mode": "HTML", "disable_web_page_preview": True},
            ) as r:
                data = await r.json(content_type=None)
                return data.get("ok", False)
    except Exception as e:
        log.error("Alert-Fehler: %s", e)
        return False


# ── Auto-Fix ──────────────────────────────────────────────────────────────────

def _auto_fix_cooldowns() -> list[str]:
    """Bereinigt abgelaufene Cooldowns aus send_guard.json."""
    fixes = []
    try:
        guard = json.loads(SEND_GUARD_FILE.read_text())
        changed = False
        for key, val in guard.items():
            if not isinstance(val, dict):
                continue
            cd = val.get("cooldown_until", 0)
            if 0 < cd < time.time() - 86400:
                guard[key]["cooldown_until"] = 0
                fixes.append(f"Abgelaufenen Cooldown bereinigt: {key}")
                changed = True
            if (key.endswith(":123") or key.endswith(":999")) and cd > time.time():
                guard[key]["cooldown_until"] = 0
                fixes.append(f"Test-Cooldown zurückgesetzt: {key}")
                changed = True
        if changed:
            SEND_GUARD_FILE.write_text(json.dumps(guard, indent=2, ensure_ascii=False))
    except Exception as e:
        log.debug("Cooldown-Bereinigung: %s", e)
    return fixes


# ── Haupt-Analyse ─────────────────────────────────────────────────────────────

async def run_monitor() -> dict:
    now = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info("TELEGRAM MONITOR START — %s", now.strftime("%Y-%m-%d %H:%M:%S UTC"))

    results = {
        "timestamp": now.isoformat(),
        "gateway_posts": [],
        "content_issues": [],
        "url_errors": [],
        "stats": {},
        "bot_status": {},
        "webhook_errors": [],
    }

    # 1. Daten sammeln
    gateway_posts   = _read_gateway_posts(hours=24)
    gateway_blocked = _read_gateway_blocked(hours=24)
    guard_posts     = _read_send_guard_posts()
    all_posts       = gateway_posts + gateway_blocked + guard_posts
    results["gateway_posts"] = gateway_posts  # für Report-Vorschau

    log.info("Posts geladen: %d sent/failed + %d blocked + %d guard",
             len(gateway_posts), len(gateway_blocked), len(guard_posts))

    # 2. Tiefe Inhalts-Analyse
    for post in all_posts:
        text = post.get("text", "")
        errors = post.get("errors", [])
        issues = _analyze_content(text, source=post.get("source", ""), errors=errors)
        if issues:
            results["content_issues"].append({
                "source": post.get("source"),
                "status": post.get("status"),
                "preview": text[:100],
                "issues": issues,
                "ts": post.get("ts") or post.get("sent_at"),
            })
            for iss in issues:
                log.warning("Content-Fehler [%s|%s]: %s | %s",
                            post.get("source"), post.get("status"), iss, text[:50])

    # 3. Statistiken
    results["stats"] = _compute_stats(gateway_posts, gateway_blocked)
    s = results["stats"]
    log.info("Stats 6h: sent=%d failed=%d blocked=%d fail_rate=%d%%",
             s["sent"], s["failed"], s["blocked"], s["fail_rate_pct"])
    if s["duplikat_loops"]:
        for text, cnt in s["duplikat_loops"]:
            log.warning("DUPLIKAT-LOOP: %dx — %s", cnt, text[:60])

    # 4. URL-Validierung (Posts der letzten 12h mit Status failed/sent)
    recent_for_url = [p for p in all_posts if p.get("status") in ("sent", "failed")][:20]
    if recent_for_url:
        results["url_errors"] = await _validate_urls_in_posts(recent_for_url)
        for err in results["url_errors"]:
            log.warning("URL-Fehler: %s (%s)", err["url"][:60], err["reason"])

    # 5. Bot-Status
    results["bot_status"] = await _check_bot_status()
    bs = results["bot_status"]
    if not bs.get("ok"):
        log.error("Bot-Token ungültig oder nicht erreichbar!")
        results["webhook_errors"].append("Bot-Token ungültig")
    else:
        log.info("Bot OK: @%s | Webhook: %s | Pending: %d",
                 bs.get("bot_name"), bs.get("webhook_url", "")[:50], bs.get("pending", 0))
        if bs.get("last_error"):
            age = time.time() - bs.get("last_error_date", 0)
            if age < 3600:
                log.warning("Webhook-Fehler (letzte 1h): %s", bs["last_error"])
                results["webhook_errors"].append(bs["last_error"])
        if bs.get("pending", 0) > 10:
            results["webhook_errors"].append(f"Zu viele pending Updates: {bs['pending']}")

    log.info("Analyse abgeschlossen")
    return results


# ── Report-Builder ────────────────────────────────────────────────────────────

def _build_report(results: dict, state: dict) -> Optional[str]:
    """Erstellt HTML-Telegram-Report. None wenn alles OK."""
    stats         = results["stats"]
    content_iss   = results["content_issues"]
    url_errs      = results["url_errors"]
    webhook_errs  = results["webhook_errors"]
    bot_ok        = results["bot_status"].get("ok", False)
    dupl_loops    = stats.get("duplikat_loops", [])
    fail_rate     = stats.get("fail_rate_pct", 0)

    # Schwellwerte: erst ab >30% Fehlerrate oder konkreten Problemen melden
    has_critical = (
        not bot_ok
        or webhook_errs
        or any(
            any("DS24" in i or "Prompt-Leak" in i or "nicht genehmigt" in i
                or "Banned" in i or "Spam" in i or "Falscher" in i
                for i in p["issues"])
            for p in content_iss
        )
        or any(
            "704330" in e.get("url", "") or "nicht genehmigt" in e.get("reason", "")
            for e in url_errs
        )
    )
    has_warnings = (
        fail_rate > 30
        or len(dupl_loops) > 0
        or len(url_errs) > 0
        or len(content_iss) > 0
    )

    known = state.get("known_issues", {})

    if not has_critical and not has_warnings:
        return None

    # Neue Probleme vs bekannte (nicht jedes Mal melden)
    issue_key = f"{fail_rate}_{len(dupl_loops)}_{len(url_errs)}"
    if not has_critical and issue_key == known.get("last_key") and not dupl_loops:
        return None  # Keine Änderung — kein neuer Report

    lines = [
        f"🔍 <b>TELEGRAM MONITOR — {'🚨 KRITISCH' if has_critical else '⚠️ Warnung'}</b>",
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"📊 6h: <b>{stats['sent']}</b> gesendet | "
        f"<b>{stats['failed']}</b> failed | <b>{stats['blocked']}</b> blockiert "
        f"| Fehlerrate: <b>{fail_rate}%</b>",
        "",
    ]

    if not bot_ok:
        lines += ["🚨 <b>BOT-TOKEN UNGÜLTIG!</b>", "→ Token prüfen", ""]

    if webhook_errs:
        lines.append("⚠️ <b>Webhook-Fehler:</b>")
        for e in webhook_errs[:3]:
            lines.append(f"  • {e}")
        lines.append("")

    # Duplikat-Loops (kritisch — verschwendet Posting-Kapazität)
    if dupl_loops:
        lines.append(f"🔄 <b>Duplikat-Loops ({len(dupl_loops)}):</b>")
        for text, cnt in dupl_loops[:3]:
            lines.append(f"  • {cnt}x in 24h: {_safe(text, 60)}...")
        lines.append("")

    # Content-Fehler (nur neue/kritische anzeigen)
    critical_content = [p for p in content_iss
                        if any("DS24" in i or "Prompt" in i or "nicht genehmigt" in i
                               or "Passiv" in i or "Gratis" in i
                               for i in p["issues"])]
    if critical_content:
        lines.append(f"🚫 <b>Kritische Content-Fehler ({len(critical_content)}):</b>")
        seen_issues = set()
        for item in critical_content[:4]:
            for issue in item["issues"][:2]:
                clean_issue = _HTML_TAG_RE.sub("", issue)
                if clean_issue not in seen_issues:
                    lines.append(f"  {html_mod.escape(clean_issue)}")
                    seen_issues.add(clean_issue)
            lines.append(f"  → {_safe(item['preview'], 70)}")
        lines.append("")

    # URL-Fehler
    if url_errs:
        lines.append(f"🔗 <b>Kaputte URLs ({len(url_errs)}):</b>")
        seen_urls = set()
        for err in url_errs[:4]:
            url_short = _safe(err["url"], 60)
            if url_short not in seen_urls:
                lines.append(f"  • <code>{url_short}</code>")
                lines.append(f"    → {_safe(err['reason'], 60)}")
                seen_urls.add(url_short)
        lines.append("")

    # Top-Fehler aus dem System
    top_errs = stats.get("top_errors", [])
    if top_errs and fail_rate > 30:
        lines.append(f"📋 <b>Häufigste Fehler:</b>")
        for err, cnt in top_errs[:3]:
            lines.append(f"  • {cnt}x: {_safe(err, 80)}")
        lines.append("")

    # Letzte gesendete Posts (Inhalts-Vorschau — immer anzeigen)
    gateway_posts = results.get("gateway_posts", [])
    recent_sent = [p for p in gateway_posts if p.get("status") == "sent"][:3]
    if recent_sent:
        lines.append("📨 <b>Letzte gesendete Posts:</b>")
        for p in recent_sent:
            preview = _safe(p.get("text", ""), 80)
            ts = p.get("ts", "")[:16] if p.get("ts") else ""
            lines.append(f"  [{ts}] {preview}{'…' if len(p.get('text',''))>80 else ''}")
        lines.append("")

    lines.append("✅ Nächste Prüfung in 5 Min")
    return "\n".join(lines)


# ── Entry Point ───────────────────────────────────────────────────────────────

async def main() -> None:
    state = _load_state()

    # Auto-Fix
    fixes = _auto_fix_cooldowns()
    for fix in fixes:
        log.info("AUTO-FIX: %s", fix)

    # Analyse
    results = await run_monitor()

    # Report
    report = _build_report(results, state)

    stats  = results["stats"]
    issues = (len(results["content_issues"]) + len(results["url_errors"]) +
              len(results["webhook_errors"]) +
              (0 if results["bot_status"].get("ok") else 1) +
              len(stats.get("duplikat_loops", [])))

    # Alert-Key: fasst aktuelle Fehlersituation zusammen
    current_key = (
        f"{stats['fail_rate_pct']}_"
        f"{len(stats.get('duplikat_loops', []))}_"
        f"{len(results['url_errors'])}_"
        f"{len(results['content_issues'])}_"
        f"{1 if not results['bot_status'].get('ok') else 0}"
    )

    if report:
        log.warning("PROBLEME GEFUNDEN: %d | Fehlerrate %d%%",
                    issues, stats.get("fail_rate_pct", 0))

        # Alert nur senden wenn neu oder Situation sich geändert hat
        last_key = state.get("last_alert_key", "")
        if current_key != last_key:
            sent = await _tg_alert(report)
            log.info("Alert gesendet (neue Situation): %s", sent)
            state["last_alert_key"] = current_key
        else:
            log.info("Situation unverändert — kein Duplikat-Alert (nächste Prüfung in 5 Min)")

        state["errors_found"] = issues
    else:
        log.info("✅ ALLES OK — %d Posts analysiert, Fehlerrate %d%%",
                 stats.get("total", 0), stats.get("fail_rate_pct", 0))
        if state.get("errors_found", 0) > 0:
            await _tg_alert(
                "✅ <b>TELEGRAM MONITOR — Entwarnung</b>\n"
                f"System läuft wieder normal.\n"
                f"📊 24h: {stats['sent']} gesendet | {stats['blocked']} blockiert\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
            state["last_alert_key"] = ""
        state["errors_found"] = 0

    state["last_run"] = time.time()
    _save_state(state)
    log.info("Monitor-Lauf fertig — nächste Prüfung in 5 Min")
    log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
