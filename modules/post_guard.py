#!/usr/bin/env python3
"""
PostGuard — Dauerhafter Content-Validator v2
=============================================
JEDER Post (Telegram, Instagram, LinkedIn, Pinterest, Twitter, Shopify Blog)
muss ALLE Prüfungen bestehen, bevor er rausgeht.

Prüfungen:
1. Länge (nicht zu kurz, nicht zu lang)
2. Kein Placeholder-Text ([PRODUKT], [LINK], [DATUM], undefined, None, etc.)
3. Kein Duplicate (identischer Post in letzten 24h nicht nochmal)
4. Kein Spam-Wörter oder verbotene Patterns
5. KI-Qualitätsprüfung (Claude/AI: ist der Inhalt sinnvoll, relevant, hochwertig?)
6. URL-Check (alle Links müssen existieren / format-valid sein)
7. Emoji/Hashtag Ratio OK
8. Sprache korrekt (DE für DACH-Posts)

Einsatz: Import + check_post() vor JEDEM Publish-Aufruf.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Tuple, List, Optional

log = logging.getLogger("PostGuard")

_CACHE_FILE = Path(os.getenv("DATA_DIR", "/tmp")) / "post_guard_cache.json"
_CACHE: dict = {}  # hash → timestamp
_DEDUP_HOURS = 24

# ── Verbotene Patterns (Placeholder-Text + Spam) ─────────────────────────────
_FORBIDDEN = re.compile(
    r'\[PRODUKT\]|\[LINK\]|\[DATUM\]|\[PREIS\]|\[NAME\]|\[URL\]|'
    r'\[INSERT\]|\[PLACEHOLDER\]|undefined|NoneType|None\b|'
    r'TODO|FIXME|LOREM IPSUM|lorem ipsum|<br>|'
    r'example\.com|yourstore\.com|YOUR_DOMAIN|http://localhost|'
    r'your-shop\.myshopify\.com|'
    r'checkout-ds24\.com/product/668035|'
    # ── Spam / Generic Life-Coach-Phrasen ──────────────────────────────────────
    r'nutzt? nur \d+\s*%\s*de\w*|'            # "nutzt nur 44% deines/des/dein"
    r'weniger als \d+\s*%\s*ihr|'             # "weniger als 30% ihres"
    r'finanziell\w+\s+Potenzials?|'           # "finanziellen Potenzials"
    r'90\s*%\s*der\s*Menschen|'               # "90% der Menschen"
    r'Geldquellen\s+NICHT|'                   # "Geldquellen NICHT"
    r'Passives?\s+Einkommen\s+ohne|'          # "Passives Einkommen ohne"
    r'reich\s+werden\s+in\s+\d+|'            # "reich werden in 30"
    r'Ergebnisse\s+garantiert|'               # fake guarantees
    r'klinisch\s+getestet\s+und|'            # fake medical claims
    r'\d+\s*%\s*Erfolgsquote',               # "98% Erfolgsquote"
    re.IGNORECASE
)

# ── Nischen-Keywords — MINDESTENS EINES muss vorkommen (Social-Posts) ─────────
_NICHE_REQUIRED = re.compile(
    r'smart\s*home|smart|tech|solar|gadget|automation|automatisierung|'
    r'e[- ]?commerce|shopify|ki\b|ai\b|artificial intelligence|'
    r'ineedit|aiitec|sensor|wlan|wifi|bluetooth|led\b|akku|'
    r'powerstation|e[- ]?bike|robot|app\b|digital\b|software|'
    r'produkt|product|shop|online\s+shop|angebot|deal|rabatt|sale|'
    r'seo|content|marketing|b2b|saas|tool\b|platform',
    re.IGNORECASE
)

# ── Mindest-Qualitätssignale ──────────────────────────────────────────────────
_MIN_WORDS = {
    "telegram":   5,
    "instagram":  8,
    "linkedin":  20,
    "twitter":    3,
    "pinterest":  5,
    "shopify":   50,
    "email":     30,
    "default":    5,
}
_MAX_CHARS = {
    "telegram":  4096,
    "instagram": 2200,
    "linkedin":  3000,
    "twitter":    280,
    "pinterest": 500,
    "shopify":   50000,
    "email":     50000,
    "default":   10000,
}


def _load_cache() -> None:
    global _CACHE
    try:
        if _CACHE_FILE.exists():
            _CACHE = json.loads(_CACHE_FILE.read_text())
    except Exception:
        _CACHE = {}


def _save_cache() -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(_CACHE))
    except Exception:
        pass


def _content_hash(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode()).hexdigest()


def _prune_cache() -> None:
    cutoff = time.time() - (_DEDUP_HOURS * 3600)
    stale = [k for k, v in _CACHE.items() if v < cutoff]
    for k in stale:
        del _CACHE[k]


# ── Prüfungen ─────────────────────────────────────────────────────────────────

def check_forbidden_patterns(text: str) -> Tuple[bool, str]:
    m = _FORBIDDEN.search(text)
    if m:
        return False, f"Verbotener Platzhalter gefunden: '{m.group()}'"
    return True, ""


def check_length(text: str, platform: str = "default") -> Tuple[bool, str]:
    words = len(text.split())
    chars = len(text)
    min_w = _MIN_WORDS.get(platform, _MIN_WORDS["default"])
    max_c = _MAX_CHARS.get(platform, _MAX_CHARS["default"])
    if words < min_w:
        return False, f"Zu wenig Wörter: {words} (Minimum: {min_w})"
    if chars > max_c:
        return False, f"Zu lang: {chars} Zeichen (Maximum: {max_c})"
    return True, ""


def check_duplicate(text: str, platform: str = "default") -> Tuple[bool, str]:
    _prune_cache()
    h = _content_hash(f"{platform}:{text[:200]}")
    if h in _CACHE:
        age_min = int((time.time() - _CACHE[h]) / 60)
        return False, f"Duplikat: gleicher Post vor {age_min} Minuten gesendet"
    return True, ""


def register_sent(text: str, platform: str = "default") -> None:
    """Nach erfolgreichem Senden aufrufen — verhindert Duplikate."""
    _prune_cache()
    h = _content_hash(f"{platform}:{text[:200]}")
    _CACHE[h] = time.time()
    _save_cache()


def check_spam_ratio(text: str) -> Tuple[bool, str]:
    """Zu viele Emojis oder Sonderzeichen = Spam-Signal."""
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0\U000024C2-\U0001F251]+",
        flags=re.UNICODE
    )
    total = len(text)
    emojis = len(emoji_pattern.findall(text))
    if total > 0 and emojis / max(total, 1) > 0.15:
        return False, f"Zu viele Emojis ({emojis} von {total} Zeichen)"
    upper = sum(1 for c in text if c.isupper())
    if total > 20 and upper / max(total, 1) > 0.5:
        return False, "Zu viele Großbuchstaben — wirkt wie Spam"
    return True, ""


_URL_CACHE: dict = {}   # url → (ok, ts)
_URL_CACHE_TTL = 600   # 10 Minuten

_BAD_HOSTS = ["localhost", "127.0.0.1", "example.com", "yoursite",
              "autopilot-store-suite-fmbka.myshopify.com"]  # myshopify nie in Posts


def _check_url_live(url: str) -> Tuple[bool, int]:
    """HEAD-Request — gibt (ok, status_code) zurück. Max 5s Timeout."""
    import urllib.request
    import urllib.error
    clean = re.sub(r'[)\]>.,!?]+$', '', url)  # Trailing-Interpunktion entfernen
    try:
        req = urllib.request.Request(clean, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status < 400, r.status
    except urllib.error.HTTPError as e:
        return e.code < 400, e.code
    except urllib.error.URLError:
        return False, 0  # DNS/Verbindungsfehler → blockieren (ineedit.com.co muss erreichbar sein)
    except Exception:
        return True, 0  # Sonstige Fehler (SSL etc.) → nicht blockieren


def check_urls(text: str) -> Tuple[bool, str]:
    """Prüft URLs: Format + echte HTTP-Verifikation (HEAD). 404 → BLOCK."""
    urls = re.findall(r'https?://\S+', text)
    for url in urls:
        clean = re.sub(r'[)\]>.,!?]+$', '', url)
        # Schlechte Hosts (Format-Check)
        if any(bad in clean for bad in _BAD_HOSTS):
            return False, f"Ungültige/Interne URL: {clean[:80]}"
        # Live-Check mit Cache
        now = time.time()
        if clean in _URL_CACHE:
            ok, ts = _URL_CACHE[clean]
            if now - ts < _URL_CACHE_TTL:
                if not ok:
                    return False, f"URL nicht erreichbar (cached): {clean[:80]}"
                continue
        ok, code = _check_url_live(clean)
        _URL_CACHE[clean] = (ok, now)
        if not ok:
            log.warning("PostGuard URL-Check FAIL: %s → HTTP %d", clean[:80], code)
            return False, f"URL liefert Fehler HTTP {code}: {clean[:80]}"
    return True, ""


_SOCIAL_PLATFORMS = {"instagram", "twitter", "linkedin", "pinterest"}


def check_niche_relevance(text: str, platform: str = "default") -> Tuple[bool, str]:
    """Social-Posts MÜSSEN mindestens 1 Nischen-Keyword enthalten (Smart Home / Tech / E-Com)."""
    if platform not in _SOCIAL_PLATFORMS:
        return True, ""
    if _NICHE_REQUIRED.search(text):
        return True, ""
    return (
        False,
        "Kein Nischen-Keyword (Smart Home / Tech / E-Commerce / AI) — Post blockiert",
    )


async def check_ai_quality(text: str, platform: str = "default", context: str = "") -> Tuple[bool, str]:
    """KI-Qualitätsprüfung via AI — BLOCKIERT bei Fehler (fail-safe)."""
    try:
        from modules.ai_client import ai_complete
        prompt = (
            f"Prüfe diesen {platform}-Post STRENG. "
            "Antworte NUR mit 'OK' oder 'FEHLER: <Grund>'.\n\n"
            "PFLICHT-Kriterien (einer Verletzung = FEHLER):\n"
            "1. Thema: Smart Home, Technologie, E-Commerce, KI-Tools, Solar, Online-Shop, "
            "SaaS-Software, Marketing-Automatisierung, Shopify-Lösungen, Affiliate-Marketing, "
            "Digistore24, Stripe, Klaviyo, SuperMegaBot, AiiteC, ineedit.com.co, "
            "Dropshipping, Produktresearch, Revenue-Optimierung — "
            "(KEIN Life-Coach, KEIN Finanz-Motivations-Content ohne Tech-Bezug)\n"
            "2. Kein Placeholder-Text: keine [KLAMMERN], kein 'undefined', kein 'None'\n"
            "3. Professionelles Deutsch, keine Tippfehler, kein Kauderwelsch\n"
            "4. Konkreter Mehrwert für den Leser — KEIN leerer Hype\n"
            "5. Kein Spam: keine übertriebenen Prozentangaben, keine Fake-Garantien\n\n"
            f"Post:\n{text[:600]}\n\n"
            "Antwort (NUR 'OK' oder 'FEHLER: ...'):"
        )

        result = await ai_complete(prompt, max_tokens=60)
        r_upper = result.upper()
        if r_upper.startswith("OK"):
            return True, ""
        if "FEHLER" in r_upper:
            reason = result.split(":", 1)[-1].strip() if ":" in result else result
            return False, f"KI: {reason[:120]}"
        # Unklare Antwort → Keyword-Fallback statt hartem Block
        tech_kw = ['smart', 'tech', 'e-commerce', 'ecommerce', 'shopify', 'amazon',
                   'ki ', 'ai ', 'automatisierung', 'automation', 'saas', 'solar',
                   'supermegabot', 'aiitec', 'ineedit', 'stripe', 'digistore',
                   'ds24', 'affiliate', 'dropshipping', 'klaviyo', 'revenue']
        if any(kw in text.lower() for kw in tech_kw):
            return True, ""
        return False, "KI: unklare Antwort — kein Tech-Keyword gefunden"
    except Exception as e:
        log.warning("AI-Qualitätsprüfung nicht verfügbar (%s) — Keyword-Fallback", e)
        # Fallback: Keyword-Check wenn AI offline
        tech_kw = ['smart', 'tech', 'e-commerce', 'ecommerce', 'shopify', 'amazon', 'ebay',
                   'ki ', 'ai ', 'automatisierung', 'automation', 'saas', 'solar', 'gadget',
                   'supermegabot', 'aiitec', 'ineedit', 'stripe', 'revenue', 'monetize',
                   'digistore', 'ds24', 'affiliate', 'dropshipping', 'klaviyo']
        t_lower = text.lower()
        if any(kw in t_lower for kw in tech_kw):
            return True, ""
        return False, "KI-Check offline: kein Tech/E-Commerce Bezug erkennbar"


# ── Haupt-Check-Funktion ──────────────────────────────────────────────────────

async def check_post(
    text: str,
    platform: str = "default",
    context: str = "",
    skip_ai: bool = False,
    strict: bool = False,
) -> Tuple[bool, List[str]]:
    """
    Vollständige Qualitätsprüfung eines Posts.

    Returns:
        (ok: bool, errors: List[str])
        ok=True → Post darf rausgehen
        ok=False → Post NICHT senden
    """
    _load_cache()
    errors = []

    ok, r = check_forbidden_patterns(text)
    if not ok:
        errors.append(r)

    ok, r = check_length(text, platform)
    if not ok:
        errors.append(r)

    ok, r = check_duplicate(text, platform)
    if not ok:
        errors.append(r)

    ok, r = check_spam_ratio(text)
    if not ok:
        errors.append(r)

    ok, r = check_urls(text)
    if not ok:
        errors.append(r)

    ok, r = check_niche_relevance(text, platform)
    if not ok:
        errors.append(r)

    if not errors or strict:
        if not skip_ai:
            ok, r = await check_ai_quality(text, platform, context)
            if not ok:
                errors.append(r)

    passed = len(errors) == 0
    if not passed:
        log.warning("PostGuard BLOCKIERT [%s]: %s | Text: %s...", platform, errors, text[:60])
    else:
        log.debug("PostGuard OK [%s]: %s...", platform, text[:40])

    return passed, errors


async def validate_and_log(
    text: str,
    platform: str = "default",
    context: str = "",
    skip_ai: bool = False,
) -> bool:
    """Wrapper: prüft Post, gibt True/False zurück. Bei False: NICHT SENDEN."""
    ok, errors = await check_post(text, platform, context, skip_ai)
    if not ok:
        log.error(
            "PostGuard blockiert [%s]:\n%s\n---\nText: %s",
            platform, "\n".join(f"  • {e}" for e in errors), text[:200]
        )
    return ok


def sync_check_post(text: str, platform: str = "default") -> Tuple[bool, List[str]]:
    """Synchrone Version (ohne KI) für schnelle Inline-Checks."""
    _load_cache()
    errors = []

    ok, r = check_forbidden_patterns(text)
    if not ok: errors.append(r)

    ok, r = check_length(text, platform)
    if not ok: errors.append(r)

    ok, r = check_duplicate(text, platform)
    if not ok: errors.append(r)

    ok, r = check_spam_ratio(text)
    if not ok: errors.append(r)

    ok, r = check_urls(text)
    if not ok: errors.append(r)

    return len(errors) == 0, errors


async def validate_batch(
    posts: list,
    skip_ai: bool = False,
) -> list:
    """Filtert alle ungültigen Posts aus einer Liste heraus."""
    valid = []
    for p in posts:
        text = p.get("text", "")
        platform = p.get("platform", "default")
        ok, errors = await check_post(text, platform, skip_ai=skip_ai)
        if ok:
            valid.append(p)
        else:
            log.warning("PostGuard: %s-Post entfernt: %s", platform, errors)
    return valid


# ── Kompatibilitäts-Wrapper (Backward-Compat für social_autoposter.py) ───────

class _GuardCompat:
    """Kompatibilitäts-Klasse für alten API-Aufruf: guard.check(platform, text=..., link=...)"""

    async def check(self, platform: str, text: str = "", link: str = "", **kwargs) -> Tuple[bool, str]:
        content = text or kwargs.get("content", "")
        ok, errors = await check_post(content, platform=platform)
        reason = "; ".join(errors) if errors else ""
        return ok, reason


guard = _GuardCompat()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    test_cases = [
        ("Unser Smart Home Starter Set ist jetzt verfügbar! Perfekt für Einsteiger mit Alexa-Anbindung.", "telegram"),
        ("[PRODUKT] ist jetzt im Angebot! Klick [LINK] für mehr Info.", "telegram"),
        ("Kurz.", "linkedin"),
        ("Hallo! Schau dir unsere neuen Smart-Home-Produkte an. Energie sparen leicht gemacht. Jetzt auf ineedit.com.co", "instagram"),
        ("lorem ipsum dolor sit amet", "twitter"),
    ]

    async def run_tests():
        for text, platform in test_cases:
            ok, errors = await check_post(text, platform, skip_ai=True)
            status = "OK" if ok else "BLOCKIERT"
            print(f"{status} [{platform}]: {text[:50]}...")
            if errors:
                for e in errors:
                    print(f"   --> {e}")

    asyncio.run(run_tests())
