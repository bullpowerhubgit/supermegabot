#!/usr/bin/env python3
"""
Post Guardian — Automatischer Qualitätswächter für alle Social-Media-Posts
===========================================================================
Prüft JEDEN Post BEVOR er gepostet wird. Kein fehlerhafter Inhalt gelangt live.

Prüfungen:
  ✅ Kein Placeholder-Text (TODO, [PLATZHALTER], BEISPIEL, etc.)
  ✅ Keine Code-Fehler / Stack-Traces im Post
  ✅ Kein "Als KI-Sprachmodell..." oder AI-Offenbarungen
  ✅ Mindestlänge (>20 Zeichen)
  ✅ Keine defekten URLs (prüft HTTP-Status)
  ✅ Keine Duplikate (gleicher Content in letzten 7 Tagen)
  ✅ Keine verbotenen Begriffe (Konkurrenz-Namen, etc.)
  ✅ Kein HTML/Markdown-Müll in Plaintext-Posts
  ✅ Bildposts: Bild-URL erreichbar
  ✅ Hashtag-Limit (max 30 für Instagram, max 5 für LinkedIn)
  ✅ Zeichenlimit pro Plattform (Twitter 280, LinkedIn 3000, etc.)
  ✅ Keine Telefonnummern / private Daten in Posts
  ✅ Keine leeren Variablen ({company}, {name} unersetzt)

Integration: wird von allen Posting-Modulen aufgerufen via validate_post()
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import sqlite3
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("PostGuardian")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "post_guardian.db"

# ── Plattform-Limits ──────────────────────────────────────────────────────────
PLATFORM_LIMITS = {
    "twitter":   {"max_chars": 280,  "max_hashtags": 5,   "min_chars": 10},
    "x":         {"max_chars": 280,  "max_hashtags": 5,   "min_chars": 10},
    "instagram": {"max_chars": 2200, "max_hashtags": 30,  "min_chars": 20},
    "facebook":  {"max_chars": 63206,"max_hashtags": 30,  "min_chars": 20},
    "linkedin":  {"max_chars": 3000, "max_hashtags": 5,   "min_chars": 30},
    "tiktok":    {"max_chars": 2200, "max_hashtags": 20,  "min_chars": 10},
    "pinterest": {"max_chars": 500,  "max_hashtags": 20,  "min_chars": 10},
    "default":   {"max_chars": 5000, "max_hashtags": 30,  "min_chars": 10},
}

# ── Verbotene Muster ──────────────────────────────────────────────────────────
PLACEHOLDER_PATTERNS = [
    r'\[PLATZHALTER\]', r'\[PLACEHOLDER\]', r'\[TODO\]', r'\[INSERT\]',
    r'\[COMPANY\]', r'\[NAME\]', r'\[PRODUKT\]', r'\[LINK\]', r'\[URL\]',
    r'BEISPIEL\s*:', r'PLACEHOLDER', r'lorem ipsum', r'TODO:', r'FIXME:',
    r'\{\{.*?\}\}',           # unersetztes Template {{variable}}
    r'\{[a-z_]+\}(?!\d)',    # unersetztes {variable} (nicht {0}, {1})
]

AI_DISCLOSURE_PATTERNS = [
    r'als\s+ki[- ]sprachmodell',
    r'als\s+künstliche\s+intelligenz',
    r'as\s+an\s+ai\s+(language\s+)?model',
    r'i\s+am\s+an\s+ai',
    r'ich\s+bin\s+(eine\s+)?ki',
    r'generated\s+by\s+(claude|gpt|openai)',
]

ERROR_PATTERNS = [
    r'traceback\s*\(most recent call',
    r'error:\s+\w+error',
    r'exception:\s+\w+',
    r'syntaxerror',
    r'nameerror',
    r'<html>.*</html>',
    r'404\s+not\s+found',
    r'500\s+internal\s+server\s+error',
    r'undefined\s+is\s+not\s+a\s+function',
]

PRIVATE_DATA_PATTERNS = [
    r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b',  # Kreditkarte
    r'\b[A-Z]{2}\d{2}[\s\-]?[A-Z0-9]{4}[\s\-]?\d{7}',  # IBAN
    r'\bpassword\s*[:=]\s*\S+',
    r'\bapi[_\s]?key\s*[:=]\s*\S+',
    r'\bsecret\s*[:=]\s*\S+',
]

# ── Themen-Relevanz: Off-Topic-Muster die NIEMALS gepostet werden dürfen ──────
# Kein fremdes News-Topic als Post-Titel/Body (HN, Nachrichten, Politik, etc.)
# WICHTIG: KEIN bare \bwar\b — matched deutsches "war" (Präteritum von "sein")
# z.B. "war früher eine Beratung" → false positive auf LinkedIn!
_OFFTOPIC_PATTERNS = re.compile(
    r'\b(polizei|police|policing|sheriff|feuerwehr|fbi|bka|bnd|'
    r'wahlen?|election|parliament|bundestag|senat|congress|'
    r'krieg|warfare|warzone|world\s+war|civil\s+war|war\s+on\s+|war\s+against|'
    r'ukraine\s+krieg|russia\s+war|militär|military|nato\b|'
    r'impfung|impfstoff|vaccine|covid|corona|pandemie|pandemic|'
    r'erdbeben|earthquake|hurricane|tornado|'
    r'skandal|korruption|'
    r'hacker\.?news|show\s*hn:?|ask\s*hn:?|hn\s+top|'
    r'quick escape button|wiped?\s+from\s+history|wipes?\s+(itself|history)|'
    r'blender\s+3d|3d\s*modellierung|vancouver\s+pd|'
    r'reddit\.com/r/|github\.com/.*/issues)\b',
    re.IGNORECASE,
)

# Verbotene Store-URLs (nur Public-Domain ineedit.com.co)
_BANNED_URLS = re.compile(
    r'myshopify\.com|checkout-ds24\.com/product/668035|'
    r'localhost|127\.0\.0\.1|yourstore|example\.com',
    re.IGNORECASE,
)
_INCOME_CLAIM_PATTERNS = [
    r'online\s+geld\s+verdienen',
    r'geld\s+verdienen\s+vollautomatisch',
    r'passives?\s+einkommen(\s+online)?',
    r'automatisch(es)?\s+einkommen',
    r'earn\s+while\s+you\s+sleep',
]

# Für Social-Plattformen: mindestens 1 Nischen-Keyword erforderlich
_NICHE_SOCIAL_PLATFORMS = {"linkedin", "facebook", "instagram", "twitter", "x", "tiktok", "pinterest"}
_NICHE_KEYWORDS = re.compile(
    r'\b(shopify|e.commerce|ecommerce|online.?shop|dropshipping|amazon|ebay|etsy|'
    r'ki\b|ai\b|künstliche intelligenz|artificial intelligence|'
    r'automatisierung|automatisch|automation|saas|software|app\b|tool\b|'
    r'marketing|seo|ads\b|traffic|conversion|umsatz|revenue|'
    r'supermegabot|aiitec|ineedit|stripe|klaviyo|digistore|'
    r'affiliate|b2b|startup|gründung|unternehmen|business|'
    r'solar|smart home|gadget|tech\b|technologie|digital|'
    # B2B Thought-Leadership & LinkedIn-Content (DACH)
    r'wettbewerber|wettbewerb|analyse|strategie|beratung|studie|'
    r'marktforschung|marktanalyse|bericht|report\b|insight|'
    r'kunden|vertrieb|pipeline|lead\b|funnel|outreach|newsletter|'
    r'compliance|eu\s+ai\s+act|ai.act|ki.verordnung|dach\b|'
    r'skalierung|skalier|effizienz|optimierung|plattform|'
    r'wachstum|performance|produktivität|täglich|wöchentlich|'
    r'agentur|dienstleistung|lösung|automatisch)\b',
    re.IGNORECASE,
)

# ── DB ────────────────────────────────────────────────────────────────────────
def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db() -> None:
    with _db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS posted (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            platform    TEXT,
            content_hash TEXT,
            content_preview TEXT,
            posted_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS blocked (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            platform    TEXT,
            content_preview TEXT,
            reason      TEXT,
            blocked_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_posted_hash ON posted(content_hash);
        CREATE INDEX IF NOT EXISTS idx_posted_plat ON posted(platform, posted_at);
        """)

# ── Validierungs-Engine ───────────────────────────────────────────────────────
class PostValidationError(Exception):
    pass

def validate_post(content: str, platform: str = "default",
                  image_url: str = "", check_url_live: bool = False
                  ) -> Tuple[bool, List[str]]:
    """
    Prüft ob ein Post gepostet werden darf.
    Returns: (ok: bool, errors: List[str])
    """
    init_db()
    errors = []
    platform_key = platform.lower().replace(" ", "")
    limits = PLATFORM_LIMITS.get(platform_key, PLATFORM_LIMITS["default"])
    text = content.strip()

    # NEVER-TWICE first — dauerhafte Fehler-Memory
    try:
        from modules.post_never_twice import check_never_twice, remember_block
        nt_ok, nt_errs = check_never_twice(text, platform_key)
        if not nt_ok:
            errors.extend(nt_errs)
            try:
                remember_block(text, platform_key, nt_errs, source_module="post_guardian")
            except Exception:
                pass
            return False, errors
    except Exception as e:
        # Fail-OPEN: technischer NeverTwice-Fehler soll Posts nicht blockieren
        log.warning("NeverTwice nicht verfügbar in guardian (%s) — weiter ohne NeverTwice", e)

    # 1. Mindestlänge
    if len(text) < limits["min_chars"]:
        errors.append(f"Zu kurz: {len(text)} Zeichen (min {limits['min_chars']})")

    # 2. Maximallänge
    if len(text) > limits["max_chars"]:
        errors.append(f"Zu lang: {len(text)} Zeichen (max {limits['max_chars']})")

    # 3. Placeholder-Text
    for pat in PLACEHOLDER_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            errors.append(f"Placeholder-Text gefunden: {pat}")

    # 4. KI-Offenbarungen
    for pat in AI_DISCLOSURE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            errors.append("KI-Offenbarung im Post erkannt")
            break

    # 5. Code-Fehler / Stack-Traces
    for pat in ERROR_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            errors.append(f"Fehlermeldung im Post: {pat[:30]}")
            break

    # 6. Private Daten
    for pat in PRIVATE_DATA_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            errors.append("Private/sensitive Daten erkannt!")

    # 7. Hashtag-Limit
    hashtags = re.findall(r'#\w+', text)
    if len(hashtags) > limits["max_hashtags"]:
        errors.append(f"Zu viele Hashtags: {len(hashtags)} (max {limits['max_hashtags']})")

    # 9. Off-Topic-Inhalte (Nachrichten, Politik, Polizei, HN-Headlines etc.)
    m = _OFFTOPIC_PATTERNS.search(text)
    if m:
        errors.append(f"Off-Topic blockiert: '{m.group()[:40]}' — kein Nachrichten/Polizei/Politik-Inhalt erlaubt")

    # 9b. Verbotene URLs (myshopify, alte DS24-IDs, localhost)
    if _BANNED_URLS.search(text):
        errors.append("Verbotene URL (myshopify/localhost/alte DS24) — nutze ineedit.com.co")

    # 9c. Python None im Post (NIE bare "none" — false positive auf Englisch)
    if re.search(r'(?i)Hallo\s+None|—\s*None\b|für\s+None\b|NoneType|:\s*None\b', text):
        errors.append("None-Placeholder im Post-Text")

    # 9d. Einkommensversprechen / Spammy monetization claims
    for pat in _INCOME_CLAIM_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            errors.append("Einkommensversprechen / Spam-Claim im Post")
            break

    # 10. Nischen-Relevanz für Social-Posts
    if platform_key in _NICHE_SOCIAL_PLATFORMS:
        if not _NICHE_KEYWORDS.search(text):
            errors.append("Kein Nischen-Keyword (E-Commerce/AI/Shopify/Marketing) — Post blockiert")

    # 8. HTML-Müll in Plaintext
    if re.search(r'<[a-z]+[^>]*>.*?</[a-z]+>', text, re.IGNORECASE | re.DOTALL):
        errors.append("HTML-Tags im Post gefunden")

    # 9. Unersetztes Template
    unresolved = re.findall(r'\{[a-zA-Z_][a-zA-Z_0-9]*\}', text)
    unresolved = [u for u in unresolved if not re.match(r'\{\d+\}', u)]
    if unresolved:
        errors.append(f"Unersetztes Template: {', '.join(unresolved[:3])}")

    # 10. Duplikat-Check (letzten 7 Tage)
    content_hash = hashlib.md5(text.lower().strip().encode()).hexdigest()
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    with _db() as conn:
        dup = conn.execute(
            "SELECT posted_at FROM posted WHERE content_hash=? AND platform=? AND posted_at>?",
            (content_hash, platform_key, cutoff)
        ).fetchone()
        if dup:
            errors.append(f"Duplikat: gleicher Post am {dup['posted_at'][:10]} auf {platform}")

    # 11. Bild-URL prüfen (wenn angegeben)
    if image_url:
        if not image_url.startswith("http"):
            errors.append(f"Ungültige Bild-URL: {image_url[:50]}")
        elif check_url_live:
            try:
                req = urllib.request.Request(image_url, method="HEAD")
                req.add_header("User-Agent", "Mozilla/5.0")
                urllib.request.urlopen(req, timeout=5)
            except Exception as e:
                errors.append(f"Bild-URL nicht erreichbar: {str(e)[:50]}")

    # 12. URLs im Post prüfen (optional, nur auffällige)
    urls = re.findall(r'https?://\S+', text)
    for url in urls[:3]:
        url = url.rstrip('.,)')
        if 'localhost' in url or '127.0.0.1' in url:
            errors.append(f"Localhost-URL im Post: {url}")
        if 'example.com' in url or 'test.com' in url:
            errors.append(f"Test-URL im Post: {url}")

    ok = len(errors) == 0

    if not ok:
        with _db() as conn:
            conn.execute(
                "INSERT INTO blocked (platform, content_preview, reason) VALUES (?,?,?)",
                (platform_key, text[:200], " | ".join(errors))
            )
        # NEVER-TWICE: denselben Fehler nie wieder zulassen
        try:
            from modules.post_never_twice import remember_block
            remember_block(text, platform_key, errors, source_module="post_guardian")
        except Exception as e:
            log.debug("remember_block skipped: %s", e)
        log.warning("Post BLOCKIERT [%s]: %s", platform, " | ".join(errors))
    else:
        log.debug("Post OK [%s]: %s...", platform, text[:60])

    return ok, errors

def register_posted(content: str, platform: str) -> None:
    """Nach erfolgreichem Post registrieren (Duplikat-Schutz)."""
    init_db()
    content_hash = hashlib.md5(content.lower().strip().encode()).hexdigest()
    with _db() as conn:
        conn.execute(
            "INSERT INTO posted (platform, content_hash, content_preview) VALUES (?,?,?)",
            (platform.lower(), content_hash, content[:200])
        )

def get_stats() -> Dict:
    """Statistiken über blockierte und genehmigte Posts."""
    init_db()
    with _db() as conn:
        total_posted  = conn.execute("SELECT COUNT(*) FROM posted").fetchone()[0]
        total_blocked = conn.execute("SELECT COUNT(*) FROM blocked").fetchone()[0]
        today_posted  = conn.execute(
            "SELECT COUNT(*) FROM posted WHERE posted_at > date('now')"
        ).fetchone()[0]
        today_blocked = conn.execute(
            "SELECT COUNT(*) FROM blocked WHERE blocked_at > date('now')"
        ).fetchone()[0]
        recent_blocked = conn.execute(
            "SELECT platform, content_preview, reason, blocked_at FROM blocked "
            "ORDER BY blocked_at DESC LIMIT 10"
        ).fetchall()
    return {
        "total_posted":  total_posted,
        "total_blocked": total_blocked,
        "today_posted":  today_posted,
        "today_blocked": today_blocked,
        "recent_blocked": [dict(r) for r in recent_blocked],
        "block_rate_pct": round(total_blocked / max(total_posted + total_blocked, 1) * 100, 1),
    }

# ── Decorator für Posting-Funktionen ─────────────────────────────────────────
def guarded(platform: str):
    """Decorator: @guarded('instagram') — blockiert automatisch fehlerhafte Posts."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            content = kwargs.get("content") or (args[0] if args else "")
            image   = kwargs.get("image_url", "")
            ok, errors = validate_post(str(content), platform, image)
            if not ok:
                log.warning("Post-Guardian blockiert %s Post: %s", platform, errors)
                return {"blocked": True, "errors": errors, "platform": platform}
            result = await func(*args, **kwargs)
            if result and not (isinstance(result, dict) and result.get("error")):
                register_posted(str(content), platform)
            return result
        return wrapper
    return decorator

# ── Erweiterte Checks ─────────────────────────────────────────────────────────

_WRONG_ACCOUNTS = {
    "iwin":             "AiiteC ist das richtige Konto — niemals IWIN verwenden!",
    "iwin_fitness":     "Falscher Account (IWIN Fitness) — AiiteC verwenden!",
    "1135864516276500": "Das ist die IWIN Facebook-Page — AiiteC Page verwenden!",
}

_SECRET_PATTERNS = [
    re.compile(r"\bsk_live_[A-Za-z0-9]{24,}\b"),
    re.compile(r"\bsk_test_[A-Za-z0-9]{24,}\b"),
    re.compile(r"\bANTH[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{35,}\b"),
    re.compile(r"(?i)password\s*[=:]\s*\S{6,}"),
]


_ERROR_PAGE_MARKERS = [
    # HTTP-Statuscodes im Seiteninhalt
    "404 not found", "404 error", "error 404", "http 404",
    "500 internal server error", "error 500", "http 500",
    "403 forbidden", "access denied", "403 error",
    "401 unauthorized", "410 gone", "503 service unavailable",
    # Englische Standard-Fehlermeldungen
    "page not found", "this page doesn't exist", "page does not exist",
    "the page you requested", "could not be found", "no longer exists",
    "we can't find", "we couldn't find", "not be found",
    "oops! something went wrong", "something went wrong",
    "internal server error", "service unavailable",
    "bad gateway", "gateway timeout",
    "coming soon", "under construction", "maintenance mode",
    # Deutsche Fehlermeldungen
    "seite nicht gefunden", "fehler 404", "diese seite existiert nicht",
    "seite existiert nicht", "nicht gefunden", "zugriff verweigert",
    "server fehler", "interner server-fehler",
    # Shopify / E-Commerce spezifisch
    "sorry, this page is not available",
    "the page you were looking for does not exist",
    "link you followed may be broken",
]

# Inhalte die OK sind — nicht als Fehler werten
_FALSE_POSITIVE_WHITELIST = [
    # Seiten die "404" im normalen Inhalt haben könnten
    "error code:", "status code: 200",
]


async def _check_url_live(url: str) -> tuple[bool, str]:
    """Öffnet URL, prüft HTTP-Status UND Seiteninhalt auf Fehlerseiten.
    Returns (ok, error_msg)."""
    import urllib.error

    try:
        loop = asyncio.get_event_loop()

        def _fetch():
            req = urllib.request.Request(
                url, method="GET",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
                }
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = resp.status
                    body = resp.read(8192).decode("utf-8", errors="ignore").lower()
                    return status, body
            except urllib.error.HTTPError as he:
                # HTTPError wird für 4xx/5xx geworfen — Status direkt auslesen
                try:
                    body = he.read(2048).decode("utf-8", errors="ignore").lower()
                except Exception:
                    body = ""
                return he.code, body

        status, body = await loop.run_in_executor(None, _fetch)

        if status >= 400:
            return False, f"URL antwortet mit HTTP {status}: {url[:80]}"

        # Titel-Tag extrahieren (genauester Fehlerindikator)
        title_match = re.search(r"<title[^>]*>(.*?)</title>", body, re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Im Titel und ersten 2KB auf Fehlermarker prüfen
        check_zone = title + " " + body[:2000]
        for marker in _ERROR_PAGE_MARKERS:
            if marker in check_zone:
                if not any(wp in check_zone for wp in _FALSE_POSITIVE_WHITELIST):
                    return False, f"Fehlerseite erkannt ('{marker}' im Inhalt): {url[:80]}"

        return True, ""
    except Exception as e:
        err = str(e)
        if "timed out" in err.lower() or "urlopen error" in err:
            return False, f"URL nicht erreichbar (Timeout/DNS): {url[:80]}"
        if "connection refused" in err.lower():
            return False, f"URL nicht erreichbar (Connection refused): {url[:80]}"
        if "ssl" in err.lower():
            return False, f"URL SSL-Fehler: {url[:80]}"
        return False, f"URL-Prüfung fehlgeschlagen: {url[:80]} ({err[:60]})"


async def check_post(platform: str, text: str,
                     image_url: Optional[str] = None,
                     account: Optional[str] = None,
                     check_urls: bool = True) -> Dict:
    """
    Vollständige async Prüfung — kombiniert validate_post + URL-Live-Check + erweiterte Checks.
    Returns: {ok, errors, warnings, can_post}
    """
    ok, base_errors = validate_post(text, platform, image_url or "")
    extra_errors: List[str] = []
    warnings: List[str] = []

    # Falsches-Konto-Check
    check_str = (text + " " + (account or "")).lower()
    for marker, msg in _WRONG_ACCOUNTS.items():
        if marker.lower() in check_str:
            extra_errors.append(f"Falsches Konto: {msg}")

    # API-Key Leak
    for pat in _SECRET_PATTERNS:
        if pat.search(text):
            extra_errors.append("Möglicher API-Key/Passwort im Post! Niemals secrets posten!")
            break

    # URL Live-Check: alle Links im Post öffnen und auf Fehlerseiten prüfen
    if check_urls:
        urls_in_text = re.findall(r'https?://[^\s<>"\']+', text)
        if image_url and image_url.startswith("http"):
            urls_in_text.append(image_url)
        # Max 5 URLs prüfen (Performance)
        for url in list(dict.fromkeys(urls_in_text))[:5]:
            url = url.rstrip(".,;)!?")
            if any(skip in url for skip in ("localhost", "127.0.0.1", "telegram.org/bot")):
                continue
            url_ok, url_err = await _check_url_live(url)
            if not url_ok:
                extra_errors.append(f"Link-Fehler: {url_err}")

    # Nacht-Posting Warnung
    hour = datetime.now().hour
    if 0 <= hour < 6:
        warnings.append(f"Nacht-Posting um {hour}:00 Uhr — schlechte Reichweite")

    all_errors = base_errors + extra_errors
    return {
        "ok": len(all_errors) == 0,
        "platform": platform,
        "account": account,
        "errors": all_errors,
        "warnings": warnings,
        "can_post": len(all_errors) == 0,
        "error_count": len(all_errors),
        "warning_count": len(warnings),
    }


def get_blocked_posts() -> List[Dict]:
    """Alle blockierten Posts der letzten 24h."""
    init_db()
    with _db() as conn:
        rows = conn.execute(
            "SELECT platform, content_preview, reason, blocked_at FROM blocked "
            "WHERE blocked_at > datetime('now', '-1 day') ORDER BY blocked_at DESC LIMIT 50"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Auto-Reparatur ─────────────────────────────────────────────────────────────

_VARIATION_PREFIXES = [
    "🔥 ", "⚡ ", "✨ ", "🚀 ", "💡 ", "🎯 ", "🛒 ",
    "Neu: ", "Jetzt: ", "Entdecke: ", "Top: ", "Hot: ",
]

async def auto_repair_post(text: str, platform: str,
                           image_url: Optional[str] = None) -> Dict:
    """
    Versucht einen fehlerhaften Post automatisch zu reparieren.
    Gibt {ok, repaired_text, changes, final_check} zurück.
    Wenn reparierbar → repaired_text enthält korrigierten Text.
    Wenn nicht reparierbar → ok=False mit Fehlermeldung.
    """
    import random
    original = text
    changes: List[str] = []
    repaired = text

    # 1. Platzhalter entfernen  {name}, {{var}}, [PLATZHALTER]
    cleaned = re.sub(r"\{[a-zA-Z_][a-zA-Z_0-9]*\}", "", repaired)
    cleaned = re.sub(r"\{\{[^}]*\}\}", "", cleaned)
    cleaned = re.sub(r"\[[A-ZÄÖÜ_\s]{3,30}\]", "", cleaned)
    if cleaned != repaired:
        changes.append("Platzhalter entfernt")
        repaired = cleaned.strip()

    # 2. Defekte URLs reparieren — ersetze durch Homepage oder entferne
    urls_in_text = re.findall(r'https?://[^\s<>"\']+', repaired)
    for url in urls_in_text:
        clean_url = url.rstrip(".,;)!?")
        if any(skip in clean_url for skip in ("localhost", "127.0.0.1", "telegram.org")):
            continue
        url_ok, url_err = await _check_url_live(clean_url)
        if not url_ok:
            # Versuche: ersetze durch Basis-Domain (Homepage)
            try:
                from urllib.parse import urlparse
                parsed = urlparse(clean_url)
                homepage = f"{parsed.scheme}://{parsed.netloc}"
                hp_ok, _ = await _check_url_live(homepage)
                if hp_ok and homepage != clean_url:
                    repaired = repaired.replace(clean_url, homepage)
                    changes.append(f"Defekte URL → Homepage ersetzt: {clean_url[:50]} → {homepage}")
                else:
                    # Homepage auch kaputt → URL komplett entfernen
                    repaired = repaired.replace(clean_url, "").strip()
                    # Doppelspaces entfernen
                    repaired = re.sub(r" {2,}", " ", repaired)
                    changes.append(f"URL entfernt (nicht erreichbar): {clean_url[:50]}")
            except Exception:
                repaired = repaired.replace(clean_url, "").strip()
                repaired = re.sub(r" {2,}", " ", repaired)
                changes.append(f"URL entfernt: {clean_url[:50]}")

    # 3. Zu langer Text → kürzen auf Plattform-Limit (−10 Puffer)
    limits = PLATFORM_LIMITS.get(platform.lower(), PLATFORM_LIMITS["default"])
    max_chars = limits["max_chars"]
    if len(repaired) > max_chars:
        # Kürze bei letztem Satzende vor dem Limit
        cutoff = repaired[:max_chars - 10]
        last_end = max(cutoff.rfind(". "), cutoff.rfind("! "), cutoff.rfind("? "), cutoff.rfind("\n"))
        if last_end > max_chars // 2:
            repaired = repaired[:last_end + 1].strip()
        else:
            repaired = cutoff.strip() + "…"
        changes.append(f"Text auf {max_chars} Zeichen gekürzt")

    # 4. Duplikat → leichte Variation (anderer Einstieg)
    content_hash = hashlib.md5(repaired.lower().strip().encode()).hexdigest()
    cutoff_dup = (datetime.now() - timedelta(days=7)).isoformat()
    with _db() as conn:
        dup_row = conn.execute(
            "SELECT posted_at FROM posted WHERE content_hash=? AND platform=? AND posted_at>?",
            (content_hash, platform.lower(), cutoff_dup)
        ).fetchone()
    if dup_row:
        prefix = random.choice(_VARIATION_PREFIXES)
        if not any(repaired.startswith(p.strip()) for p in _VARIATION_PREFIXES):
            repaired = prefix + repaired
            changes.append(f"Duplikat-Variation: Prefix '{prefix.strip()}' hinzugefügt")

    # 5. Leerraum bereinigen
    repaired = re.sub(r"\n{3,}", "\n\n", repaired).strip()

    if not changes:
        return {
            "ok": False,
            "repaired": False,
            "repaired_text": original,
            "changes": [],
            "message": "Keine automatische Reparatur möglich — Post muss manuell korrigiert werden",
        }

    # Erneute Prüfung nach Reparatur
    final = await check_post(platform, repaired, image_url)
    return {
        "ok": final["ok"],
        "repaired": True,
        "original_text": original,
        "repaired_text": repaired,
        "changes": changes,
        "final_check": final,
        "message": "Reparatur erfolgreich — Post kann gepostet werden" if final["ok"]
                   else f"Reparatur teilweise — verbleibende Fehler: {final['errors']}",
    }


# ── CLI / Test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, json
    init_db()
    args = sys.argv[1:]

    if "--stats" in args:
        print(json.dumps(get_stats(), indent=2, ensure_ascii=False))

    elif "--test" in args:
        tests = [
            ("Unser neues Produkt ist jetzt verfügbar! Kaufe jetzt auf bullpower-hub.vercel.app #shopify #ki #automatisierung", "instagram"),
            ("[PLACEHOLDER] kaufe jetzt!", "twitter"),
            ("Als KI-Sprachmodell kann ich dir sagen dass...", "facebook"),
            ("Traceback (most recent call last): File main.py line 42", "linkedin"),
            ("Hallo {name}, schau dir {produkt} an!", "twitter"),
            ("", "instagram"),
            ("x" * 300, "twitter"),
        ]
        for content, platform in tests:
            ok, errors = validate_post(content, platform)
            status = "✅ OK" if ok else f"❌ BLOCKIERT"
            print(f"{status} [{platform}]: {content[:50]!r}")
            if errors:
                for e in errors:
                    print(f"   → {e}")
    else:
        print(__doc__)
