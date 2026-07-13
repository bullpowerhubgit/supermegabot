"""
env_validator.py — Robuste Umgebungsvariablen-Validierung mit Fail-Fast-Modus.
Wird als erstes Modul beim Start geladen.
"""

import os
import logging
import asyncio
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

logger = logging.getLogger(__name__)

ENV_PATH = str(Path(__file__).parent.parent / ".env")

# ─── Key-Kategorien ───────────────────────────────────────────────────────────

CRITICAL_KEYS: list[dict] = [
    {
        "name": "SHOPIFY_ADMIN_API_TOKEN",
        "aliases": ["SHOPIFY_ACCESS_TOKEN"],
        "label": "Shopify Admin API Token",
        "category": "REVENUE",
    },
    {
        "name": "SHOPIFY_SHOP_DOMAIN",
        "aliases": [],
        "label": "Shopify Shop Domain",
        "category": "REVENUE",
    },
    {
        "name": "TELEGRAM_BOT_TOKEN",
        "aliases": [],
        "label": "Telegram Bot Token",
        "category": "REVENUE",
    },
    {
        "name": "TELEGRAM_CHAT_ID",
        "aliases": [],
        "label": "Telegram Chat ID",
        "category": "REVENUE",
    },
    {
        "name": "STRIPE_SECRET_KEY",
        "aliases": [],
        "label": "Stripe Secret Key",
        "category": "REVENUE",
    },
]

# ANTHROPIC_API_KEY ist kritisch aber nur Warnung (kein Fail)
WARN_CRITICAL_KEYS: list[dict] = [
    {
        "name": "ANTHROPIC_API_KEY",
        "aliases": [],
        "label": "Anthropic API Key",
        "category": "AI",
    },
]

IMPORTANT_KEYS: list[dict] = [
    {"name": "DIGISTORE24_API_KEY", "aliases": [], "label": "Digistore24 API Key"},
    {"name": "GMAIL_USER_5", "aliases": [], "label": "Gmail User 5"},
    {"name": "GMAIL_APP_PASSWORD_5", "aliases": [], "label": "Gmail App Password 5"},
    {"name": "SUPABASE_URL", "aliases": [], "label": "Supabase URL"},
    {"name": "SUPABASE_SERVICE_KEY", "aliases": [], "label": "Supabase Service Key"},
    {
        "name": "META_ACCESS_TOKEN",
        "aliases": ["FACEBOOK_PAGE_TOKEN_AIITEC"],
        "label": "Meta/Facebook Access Token",
    },
    {"name": "KLAVIYO_API_KEY", "aliases": [], "label": "Klaviyo API Key"},
]

_INVALID_PATTERNS = {"", "undefined", "null", "none", "false"}


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def reload_env() -> None:
    """Lädt .env neu — täglich aufrufen."""
    if load_dotenv is None:
        logger.warning("python-dotenv nicht installiert — .env wird nicht geladen")
        return
    loaded = load_dotenv(ENV_PATH, override=True)
    if loaded:
        logger.info("env_validator: .env neu geladen von %s", ENV_PATH)
    else:
        logger.warning("env_validator: .env konnte nicht geladen werden (%s)", ENV_PATH)


def _resolve_value(key_def: dict) -> Optional[str]:
    """Gibt den Wert des ersten gesetzten Keys (inkl. Aliases) zurück."""
    for name in [key_def["name"]] + key_def.get("aliases", []):
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return None


def _is_valid_value(value: Optional[str]) -> bool:
    """Prüft ob ein Wert wirklich brauchbar ist (nicht leer, Platzhalter, etc.)."""
    if not value:
        return False
    lower = value.lower()
    if lower in _INVALID_PATTERNS:
        return False
    if lower.startswith("your_") or lower.endswith("_here"):
        return False
    return True


def _check_key_group(key_defs: list[dict]) -> tuple[list[str], list[str]]:
    """
    Gibt (missing, present) als Listen der Key-Namen zurück.
    Bei Aliases: Key gilt als vorhanden wenn mindestens ein Alias gesetzt ist.
    """
    missing = []
    present = []
    for kd in key_defs:
        val = _resolve_value(kd)
        if _is_valid_value(val):
            present.append(kd["name"])
        else:
            missing.append(kd["name"])
    return missing, present


# ─── Live-API-Tests ───────────────────────────────────────────────────────────

async def _test_shopify() -> dict:
    """Testet die Shopify-API mit einem leichtgewichtigen GET-Request."""
    if not _AIOHTTP_AVAILABLE:
        return {"ok": None, "error": "aiohttp nicht verfügbar"}

    token = _resolve_value({"name": "SHOPIFY_ADMIN_API_TOKEN", "aliases": ["SHOPIFY_ACCESS_TOKEN"]})
    domain = _resolve_value({"name": "SHOPIFY_SHOP_DOMAIN", "aliases": []})
    api_version = os.getenv("SHOPIFY_API_VERSION", "2026-04")

    if not token or not domain:
        return {"ok": False, "error": "Token oder Domain fehlt"}

    url = f"https://{domain}/admin/api/{api_version}/shop.json"
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    shop_name = data.get("shop", {}).get("name", "?")
                    return {"ok": True, "shop": shop_name, "status": resp.status}
                else:
                    text = await resp.text()
                    return {"ok": False, "status": resp.status, "error": text[:200]}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Timeout (10s)"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def _test_telegram() -> dict:
    """Testet die Telegram-API via getMe."""
    if not _AIOHTTP_AVAILABLE:
        return {"ok": None, "error": "aiohttp nicht verfügbar"}

    token = _resolve_value({"name": "TELEGRAM_BOT_TOKEN", "aliases": []})
    if not token:
        return {"ok": False, "error": "Token fehlt"}

    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    bot_name = data.get("result", {}).get("username", "?")
                    return {"ok": True, "bot": bot_name, "status": resp.status}
                else:
                    return {"ok": False, "status": resp.status}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Timeout (10s)"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def _test_stripe() -> dict:
    """Testet Stripe via /v1/balance (read-only)."""
    if not _AIOHTTP_AVAILABLE:
        return {"ok": None, "error": "aiohttp nicht verfügbar"}

    key = _resolve_value({"name": "STRIPE_SECRET_KEY", "aliases": []})
    if not key:
        return {"ok": False, "error": "Key fehlt"}

    url = "https://api.stripe.com/v1/balance"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, auth=aiohttp.BasicAuth(key, "")) as resp:
                if resp.status == 200:
                    return {"ok": True, "status": resp.status}
                else:
                    data = await resp.json()
                    err = data.get("error", {}).get("message", "Unbekannter Fehler")
                    return {"ok": False, "status": resp.status, "error": err}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Timeout (10s)"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def _test_anthropic() -> dict:
    """Schnelltest: prüft ob der Key vorhanden und korrekt formatiert ist."""
    key = _resolve_value({"name": "ANTHROPIC_API_KEY", "aliases": []})
    if not key:
        return {"ok": False, "error": "Key fehlt"}
    # sk-ant- Prefix als einfacher Sanity-Check
    if key.startswith("sk-ant-"):
        return {"ok": True, "format": "valid"}
    return {"ok": False, "error": "Unerwartetes Key-Format (erwartet sk-ant-...)"}


async def _run_api_tests() -> dict:
    """Führt alle API-Tests parallel aus."""
    results = await asyncio.gather(
        _test_shopify(),
        _test_telegram(),
        _test_stripe(),
        _test_anthropic(),
        return_exceptions=True,
    )
    labels = ["shopify", "telegram", "stripe", "anthropic"]
    api_tests = {}
    for label, result in zip(labels, results):
        if isinstance(result, Exception):
            api_tests[label] = {"ok": False, "error": str(result)}
        else:
            api_tests[label] = result
    return api_tests


# ─── Score-Berechnung ─────────────────────────────────────────────────────────

def _compute_score(
    critical_missing: list[str],
    warn_critical_missing: list[str],
    important_missing: list[str],
    api_tests: dict,
) -> int:
    """
    Berechnet einen Gesamtscore von 0–100.
    - Kritische Keys: je 15 Punkte
    - Warn-Kritische Keys: je 5 Punkte
    - Wichtige Keys: je 3 Punkte
    - API-Tests: je 5 Punkte
    """
    score = 100

    # Kritische Keys (5 Keys × 15 = 75)
    per_critical = 15
    score -= len(critical_missing) * per_critical

    # Warn-kritische Keys (1 Key × 5 = 5)
    per_warn_critical = 5
    score -= len(warn_critical_missing) * per_warn_critical

    # Wichtige Keys (7 Keys × 3 = 21 — aber wir deckeln)
    per_important = 3
    score -= len(important_missing) * per_important

    # API-Tests: je fehlgeschlagener Test -4 Punkte
    for result in api_tests.values():
        if isinstance(result, dict) and result.get("ok") is False:
            score -= 4

    return max(0, min(100, score))


# ─── Öffentliche API ──────────────────────────────────────────────────────────

def validate_env(fail_fast: bool = False) -> dict:
    """
    Prüft alle Umgebungsvariablen synchron (ohne API-Tests).

    Args:
        fail_fast: Wenn True, wird SystemExit ausgelöst sobald kritische Keys fehlen.

    Returns:
        {
            ok: bool,
            critical_missing: list[str],
            warn_critical_missing: list[str],
            important_missing: list[str],
            api_tests: {},   # leer — wird durch run_env_health_cycle befüllt
            score: int,      # 0–100 (nur statische Checks)
        }
    """
    reload_env()

    critical_missing, _ = _check_key_group(CRITICAL_KEYS)
    warn_critical_missing, _ = _check_key_group(WARN_CRITICAL_KEYS)
    important_missing, _ = _check_key_group(IMPORTANT_KEYS)

    ok = len(critical_missing) == 0

    score = _compute_score(critical_missing, warn_critical_missing, important_missing, {})

    if critical_missing:
        logger.error(
            "env_validator: KRITISCHE Keys fehlen: %s",
            ", ".join(critical_missing),
        )
    if warn_critical_missing:
        logger.warning(
            "env_validator: Wichtige Keys fehlen (Warnung): %s",
            ", ".join(warn_critical_missing),
        )
    if important_missing:
        logger.warning(
            "env_validator: Wichtige Keys fehlen: %s",
            ", ".join(important_missing),
        )

    if fail_fast and not ok:
        raise SystemExit(
            f"[env_validator] FAIL-FAST: Kritische Keys fehlen: {', '.join(critical_missing)}"
        )

    return {
        "ok": ok,
        "critical_missing": critical_missing,
        "warn_critical_missing": warn_critical_missing,
        "important_missing": important_missing,
        "api_tests": {},
        "score": score,
    }


def get_missing_critical() -> list[str]:
    """Gibt die Namen aller fehlenden kritischen Keys zurück."""
    reload_env()
    missing, _ = _check_key_group(CRITICAL_KEYS)
    # Anthropic als Warnung mitliefern
    warn_missing, _ = _check_key_group(WARN_CRITICAL_KEYS)
    return missing + warn_missing


def get_env_report() -> str:
    """Erstellt einen kompakten Telegram-Report (Markdown-kompatibel)."""
    result = validate_env(fail_fast=False)

    lines = ["*ENV Health Report*"]
    score = result["score"]
    emoji = "✅" if score >= 80 else ("⚠️" if score >= 50 else "🔴")
    lines.append(f"{emoji} Score: {score}/100")

    if result["critical_missing"]:
        lines.append("\n🔴 *KRITISCH (fehlt)*:")
        for key in result["critical_missing"]:
            lines.append(f"  • `{key}`")
    else:
        lines.append("\n✅ Alle kritischen Keys vorhanden")

    if result["warn_critical_missing"]:
        lines.append("\n⚠️ *Warnung (AI)*:")
        for key in result["warn_critical_missing"]:
            lines.append(f"  • `{key}`")

    if result["important_missing"]:
        lines.append("\n⚠️ *Wichtige Keys fehlen*:")
        for key in result["important_missing"]:
            lines.append(f"  • `{key}`")
    else:
        lines.append("\n✅ Alle wichtigen Keys vorhanden")

    api_tests = result.get("api_tests", {})
    if api_tests:
        lines.append("\n*API-Tests*:")
        for service, res in api_tests.items():
            if res.get("ok"):
                detail = res.get("shop") or res.get("bot") or ""
                lines.append(f"  ✅ {service.capitalize()}" + (f" ({detail})" if detail else ""))
            elif res.get("ok") is None:
                lines.append(f"  ⚪ {service.capitalize()}: übersprungen")
            else:
                err = res.get("error", f"HTTP {res.get('status', '?')}")
                lines.append(f"  ❌ {service.capitalize()}: {err}")

    return "\n".join(lines)


async def run_env_health_cycle() -> str:
    """
    Vollständiger Health-Cycle für den Scheduler:
    1. .env neu laden
    2. Statische Prüfung
    3. API-Tests
    4. Report zurückgeben

    Returns:
        Telegram-kompatibler Report-String
    """
    reload_env()

    critical_missing, _ = _check_key_group(CRITICAL_KEYS)
    warn_critical_missing, _ = _check_key_group(WARN_CRITICAL_KEYS)
    important_missing, _ = _check_key_group(IMPORTANT_KEYS)

    logger.info("env_validator: Starte API-Tests...")
    api_tests = await _run_api_tests()

    score = _compute_score(critical_missing, warn_critical_missing, important_missing, api_tests)

    ok = len(critical_missing) == 0

    result = {
        "ok": ok,
        "critical_missing": critical_missing,
        "warn_critical_missing": warn_critical_missing,
        "important_missing": important_missing,
        "api_tests": api_tests,
        "score": score,
    }

    # Report bauen (wie get_env_report, aber mit API-Testergebnissen)
    lines = ["*ENV Health Report (vollständig)*"]
    emoji = "✅" if score >= 80 else ("⚠️" if score >= 50 else "🔴")
    lines.append(f"{emoji} Score: {score}/100")

    if critical_missing:
        lines.append("\n🔴 *KRITISCH (fehlt)*:")
        for key in critical_missing:
            lines.append(f"  • `{key}`")
    else:
        lines.append("\n✅ Alle kritischen Keys vorhanden")

    if warn_critical_missing:
        lines.append("\n⚠️ *Warnung (AI)*:")
        for key in warn_critical_missing:
            lines.append(f"  • `{key}`")

    if important_missing:
        lines.append("\n⚠️ *Wichtige Keys fehlen*:")
        for key in important_missing:
            lines.append(f"  • `{key}`")
    else:
        lines.append("\n✅ Alle wichtigen Keys vorhanden")

    lines.append("\n*API-Tests*:")
    for service, res in result["api_tests"].items():
        if res.get("ok"):
            detail = res.get("shop") or res.get("bot") or ""
            lines.append(f"  ✅ {service.capitalize()}" + (f" ({detail})" if detail else ""))
        elif res.get("ok") is None:
            lines.append(f"  ⚪ {service.capitalize()}: übersprungen")
        else:
            err = res.get("error", f"HTTP {res.get('status', '?')}")
            lines.append(f"  ❌ {service.capitalize()}: {err}")

    report = "\n".join(lines)
    logger.info("env_validator: Health-Cycle abgeschlossen. Score=%d ok=%s", score, ok)
    return report


# ─── CLI-Schnelltest ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print("=== Statische Prüfung ===")
    res = validate_env(fail_fast=False)
    print(f"OK: {res['ok']}  Score: {res['score']}/100")
    if res["critical_missing"]:
        print(f"KRITISCH fehlend: {res['critical_missing']}")
    if res["important_missing"]:
        print(f"Wichtige fehlend: {res['important_missing']}")

    if "--full" in sys.argv:
        print("\n=== Vollstaendiger Health-Cycle (inkl. API-Tests) ===")
        report = asyncio.run(run_env_health_cycle())
        print(report)
