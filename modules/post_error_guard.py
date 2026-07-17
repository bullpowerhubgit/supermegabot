"""
Post Error Guard — PERMANENTES SCHUTZSYSTEM
============================================
Jeder bekannte Post-Fehler wird hier blockiert. Für immer.

Fehlerklassen (hardcoded, NIE entfernen):
  1. myshopify.com URL in Post  → immer ineedit.com.co verwenden
  2. Leerer Post / None          → Kein leerer Content
  3. "None" als String           → Python-Platzhalter im Text
  4. Hacker-News-Headline        → Keine HN-Scrapes als Produkt
  5. DS24 falsches Konto         → Key 1682000 ist FALSCH (1581233 = aiitec)
  6. IWIN Facebook-Account       → Niemals Page 1135864516276500 (IWIN)

Aufruf vor JEDEM Post:
    from modules.post_error_guard import guard_post
    ok, reason = guard_post(text, url=product_url, platform="instagram")
    if not ok:
        log.warning("POST BLOCKED: %s — %s", platform, reason)
        return {"blocked": True, "reason": reason}

Alle Blöcke werden in post_never_twice.db gespeichert → self-learning.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger("PostErrorGuard")

# ─── Hardcoded kritische Regeln (NIEMALS entfernen) ───────────────────────────
_CRITICAL_RULES: list[tuple[str, re.Pattern, str]] = [
    (
        "myshopify_in_post",
        re.compile(r"myshopify\.com", re.I),
        "myshopify.com URL im Post — muss ineedit.com.co sein",
    ),
    (
        "none_placeholder",
        re.compile(r"(?:Hallo|für|von|—)\s*None\b|NoneType|\bNone\b", re.I),
        "Python None-Platzhalter im Post-Text",
    ),
    (
        "placeholder_text",
        re.compile(r"\[PLACEHOLDER\]|\[TODO\]|\[PRODUKT\]|\[LINK\]|TODO:|FIXME:", re.I),
        "Platzhalter-Text im Post",
    ),
    (
        "traceback_in_post",
        re.compile(r'Traceback\s*\(most recent|File\s+".*",\s+line\s+\d+', re.I),
        "Python-Traceback im Post-Text",
    ),
    (
        "hn_headline",
        re.compile(r"(?:Show|Ask)\s+HN\s*:", re.I),
        "Hacker-News-Headline als Post-Content",
    ),
    (
        "wrong_ds24_product",
        re.compile(r"checkout-ds24\.com/product/668035", re.I),
        "Falsches DS24-Konto (668035) — immer 1581233/aiitec verwenden",
    ),
    (
        "wrong_fb_account",
        re.compile(r"1135864516276500", re.I),
        "IWIN Facebook-Page im Post — immer AiiteC (1016738738178786) verwenden",
    ),
    (
        "localhost_url",
        re.compile(r"localhost|127\.0\.0\.1|yourstore\.myshopify|example\.com", re.I),
        "Localhost oder Test-URL im Post",
    ),
    (
        "ai_disclosure",
        re.compile(r"als\s+ki[- ]sprachmodell|as\s+an\s+ai\s+model|ich\s+bin\s+(?:eine\s+)?ki\b", re.I),
        "KI-Selbstoffenbarung im Post",
    ),
]


def _check_url(url: str) -> Optional[str]:
    """Prüft eine URL auf bekannte Fehler. Gibt Fehlertext oder None zurück."""
    if not url:
        return None
    if "myshopify.com" in url.lower():
        return f"myshopify.com URL wird als öffentlicher Link gepostet: {url[:80]}"
    if "localhost" in url.lower() or "127.0.0.1" in url:
        return f"Localhost-URL: {url[:80]}"
    return None


def guard_post(
    text: str,
    url: str = "",
    platform: str = "unknown",
    source_module: str = "",
) -> tuple[bool, str]:
    """
    Synchrone Vor-Flug-Prüfung für jeden Post.

    Returns:
        (True, "") wenn OK
        (False, grund) wenn blockiert
    """
    combined = (text or "") + " " + (url or "")

    # 1. Leerer Content
    if not text or not text.strip():
        _log_block(platform, "empty_content", "Leerer Post-Text", text, source_module)
        return False, "Leerer Post-Text"

    # 2. Hardcoded kritische Regeln
    for rule_id, pattern, desc in _CRITICAL_RULES:
        if pattern.search(combined):
            _log_block(platform, rule_id, desc, text, source_module)
            return False, desc

    # 3. URL-spezifische Prüfung
    if url:
        url_err = _check_url(url)
        if url_err:
            _log_block(platform, "bad_url", url_err, text, source_module)
            return False, url_err

    # 4. Post-Never-Twice (lernend, DB-backed)
    try:
        from modules.post_never_twice import check_never_twice, remember_block
        nt_ok, nt_errs = check_never_twice(combined, platform)
        if not nt_ok:
            try:
                remember_block(combined, platform, nt_errs, source_module=source_module or "post_error_guard")
            except Exception:
                pass
            desc = "; ".join(nt_errs) if nt_errs else "NeverTwice block"
            _log_block(platform, "never_twice", desc, text, source_module)
            return False, f"NeverTwice: {desc}"
    except Exception as e:
        if "locked" in str(e).lower():
            log.warning("PostErrorGuard NeverTwice locked — fail-open")
        else:
            _log_block(platform, "never_twice_error", str(e), text, source_module)
            return False, f"NeverTwice Fehler (fail-closed): {e}"

    # 5. PostGuardian (sync, inkl. Länge, Spam, Duplikat)
    try:
        from modules.post_guardian import validate_post
        pg_ok, pg_errs = validate_post(combined, platform)
        if not pg_ok:
            desc = "; ".join(pg_errs) if pg_errs else "PostGuardian block"
            _log_block(platform, "post_guardian", desc, text, source_module)
            return False, f"PostGuardian: {desc}"
    except Exception as e:
        log.warning("PostGuardian import/check Fehler (nicht fail-closed): %s", e)
        # PostGuardian-Fehler → NICHT fail-closed (um Import-Probleme zu vermeiden)

    return True, ""


async def guard_post_async(
    text: str,
    url: str = "",
    platform: str = "unknown",
    source_module: str = "",
) -> tuple[bool, str]:
    """
    Async Version — führt sync guard_post + async PostGuard AI-Check aus.
    """
    ok, reason = guard_post(text, url, platform, source_module)
    if not ok:
        return False, reason

    # Async AI-Qualitätsprüfung
    try:
        from modules.post_guard import validate_and_log
        ai_ok = await validate_and_log(text, platform=platform)
        if not ai_ok:
            _log_block(platform, "post_guard_ai", "PostGuard AI-Qualitätsprüfung", text, source_module)
            return False, "PostGuard AI: Qualitätsprüfung nicht bestanden"
    except Exception as e:
        log.warning("PostGuard AI Fehler (nicht fail-closed): %s", e)

    return True, ""


def _log_block(platform: str, rule_id: str, reason: str, text: str, source: str) -> None:
    """Loggt jeden Block → post_never_twice.db via remember_block."""
    log.warning("[BLOCK] %s | %s | %s | Modul:%s | '%s'",
                platform, rule_id, reason, source or "?", text[:60])
    try:
        from modules.post_never_twice import remember_block
        remember_block(text or "", platform, [f"{rule_id}: {reason}"],
                       source_module=source or "post_error_guard")
    except Exception:
        pass  # Logging darf nie einen Post-Flow crashen


def audit_post_modules() -> dict:
    """
    Prüft alle bekannten Social-Posting-Module auf korrekte URL-Konfiguration.
    Gibt einen Bericht zurück.
    """
    import os
    report = {"ok": [], "warnings": [], "checked_at": __import__("datetime").datetime.utcnow().isoformat()}

    shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    public_domain = os.getenv("SHOPIFY_PUBLIC_DOMAIN", "ineedit.com.co")

    if "myshopify" in shop_domain.lower():
        if public_domain == "ineedit.com.co" or "myshopify" not in public_domain.lower():
            report["ok"].append(f"SHOPIFY_PUBLIC_DOMAIN korrekt: {public_domain}")
        else:
            report["warnings"].append(f"SHOPIFY_PUBLIC_DOMAIN enthält myshopify: {public_domain}")
    else:
        report["ok"].append(f"SHOPIFY_SHOP_DOMAIN hat kein myshopify: {shop_domain}")

    # Bekannte Module mit URL-Fixes prüfen
    modules_to_check = [
        ("mega_auto_poster", "PUBLIC_SHOP_URL", "modules/mega_auto_poster.py"),
        ("marketplace_auto_poster", "PUBLIC_DOMAIN", "modules/marketplace_auto_poster.py"),
        ("full_revenue_expansion", "SHOPIFY_PUBLIC_DOMAIN", "modules/full_revenue_expansion.py"),
        ("meta_roas_max", "SHOPIFY_PUBLIC_DOMAIN", "modules/meta_roas_max.py"),
        ("social_autoposter", "SHOPIFY_PUBLIC_DOMAIN", "modules/social_autoposter.py"),
        ("telegram_safe", "SHOPIFY_PUBLIC_DOMAIN", "modules/telegram_safe.py"),
    ]
    from pathlib import Path
    root = Path(__file__).parent.parent
    for name, expected_var, rel_path in modules_to_check:
        fpath = root / rel_path
        if fpath.exists():
            content = fpath.read_text()
            if expected_var in content:
                report["ok"].append(f"{name}: enthält {expected_var} ✓")
            elif "myshopify" in content.lower() and "SHOPIFY_PUBLIC" not in content:
                report["warnings"].append(f"{name}: verwendet möglicherweise myshopify-Domain für Posts!")
        else:
            report["warnings"].append(f"{name}: Datei nicht gefunden ({rel_path})")

    return report


if __name__ == "__main__":
    # Schnell-Test
    tests = [
        ("Neues Produkt auf https://autopilot-store-suite-fmbka.myshopify.com/products/test", "facebook"),
        ("Hallo None, hier ist dein Angebot!", "email"),
        ("Top Smart-Home Produkte bei ineedit.com.co 🚀 #SmartHome", "twitter"),
        ("Show HN: My startup is now profitable", "linkedin"),
        ("", "telegram"),
    ]
    for text, plat in tests:
        ok, reason = guard_post(text, platform=plat)
        status = "✓ OK" if ok else f"✗ BLOCK: {reason}"
        print(f"[{plat}] {status}")
        print(f"  Text: {text[:60]!r}")
