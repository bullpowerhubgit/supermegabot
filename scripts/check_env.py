#!/usr/bin/env python3
"""
SuperMegaBot — Startup ENV Validation Script
Liest alle Variablen aus .env.example, prüft ob sie gesetzt sind,
und validiert Formate für bekannte Token-Typen.

Exit-Code: 0 = OK (alle kritischen gesetzt), 1 = kritische Vars fehlen
"""

import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

CRITICAL_VARS = {
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "SHOPIFY_ACCESS_TOKEN",
    "SHOPIFY_SHOP_DOMAIN",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
}

# Format-Validierungsregeln: variable -> (beschreibung, prüffunktion)
FORMAT_CHECKS = {
    "SHOPIFY_ACCESS_TOKEN": (
        'muss mit "shpat_" beginnen',
        lambda v: v.startswith("shpat_"),
    ),
    "SUPABASE_URL": (
        'muss "supabase" enthalten',
        lambda v: "supabase" in v.lower(),
    ),
    "TELEGRAM_BOT_TOKEN": (
        'muss ":" enthalten',
        lambda v: ":" in v,
    ),
}

# ---------------------------------------------------------------------------
# .env.example einlesen und alle definierten Variablen sammeln
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent.parent
ENV_EXAMPLE = BASE_DIR / ".env.example"

# Auch .env laden, falls vorhanden
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())


def parse_env_example(path: Path) -> list[str]:
    """Extrahiert alle Variablennamen aus .env.example (Kommentare ignorieren)."""
    names = []
    if not path.exists():
        print(f"FEHLER: {path} nicht gefunden!", file=sys.stderr)
        sys.exit(1)
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            var_name = line.split("=", 1)[0].strip()
            if re.match(r"^[A-Z][A-Z0-9_]*$", var_name):
                names.append(var_name)
    return names


# ---------------------------------------------------------------------------
# Hauptprüfung
# ---------------------------------------------------------------------------

def check_env() -> int:
    """
    Prüft alle ENV-Variablen aus .env.example.
    Gibt 0 zurück wenn alle kritischen gesetzt, sonst 1.
    """
    all_vars = parse_env_example(ENV_EXAMPLE)

    ok_vars = []
    optional_missing = []
    critical_missing = []
    format_errors = []

    for var in all_vars:
        value = os.getenv(var, "")
        is_set = bool(value)
        is_critical = var in CRITICAL_VARS

        if is_set:
            # Format-Validierung für bekannte Token-Typen
            if var in FORMAT_CHECKS:
                desc, check_fn = FORMAT_CHECKS[var]
                try:
                    if not check_fn(value):
                        format_errors.append((var, desc))
                except Exception:
                    pass
            ok_vars.append(var)
        else:
            if is_critical:
                critical_missing.append(var)
            else:
                optional_missing.append(var)

    # ---------------------------------------------------------------------------
    # Ausgabe
    # ---------------------------------------------------------------------------

    total = len(all_vars)
    print("=" * 70)
    print("  SuperMegaBot — ENV Startup-Validierung")
    print("=" * 70)
    print(f"  Gelesen aus: {ENV_EXAMPLE}")
    print(f"  Variablen gesamt: {total}")
    print()

    # Gesetzte Variablen
    if ok_vars:
        print(f"✅  GESETZT ({len(ok_vars)}):")
        for v in ok_vars:
            crit_mark = " [KRITISCH]" if v in CRITICAL_VARS else ""
            print(f"    ✅ {v}{crit_mark}")
        print()

    # Format-Fehler (gesetzt, aber falsch formatiert)
    if format_errors:
        print(f"⚠️   FORMAT-FEHLER ({len(format_errors)}):")
        for v, desc in format_errors:
            print(f"    ⚠️  {v} — Wert {desc}")
        print()

    # Optionale fehlende Variablen
    if optional_missing:
        print(f"⚠️   FEHLT (optional) ({len(optional_missing)}):")
        for v in optional_missing:
            print(f"    ⚠️  {v}")
        print()

    # Kritische fehlende Variablen
    if critical_missing:
        print(f"❌  FEHLT (KRITISCH) ({len(critical_missing)}):")
        for v in critical_missing:
            print(f"    ❌ {v}")
        print()

    # ---------------------------------------------------------------------------
    # Zusammenfassung
    # ---------------------------------------------------------------------------

    print("=" * 70)
    all_critical_ok = len(critical_missing) == 0

    if all_critical_ok and not format_errors:
        print("  ERGEBNIS: ✅  PASS — Alle kritischen ENV-Variablen sind gesetzt.")
        print("=" * 70)
        return 0
    else:
        print("  ERGEBNIS: ❌  FAIL")
        if critical_missing:
            print(f"  Fehlende kritische Variablen: {', '.join(critical_missing)}")
        if format_errors:
            bad = [v for v, _ in format_errors]
            print(f"  Format-Fehler: {', '.join(bad)}")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(check_env())
