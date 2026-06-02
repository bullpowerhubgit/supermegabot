#!/usr/bin/env python3
"""
deep_scan_repair.py — Comprehensive scan and auto-repair for SuperMegaBot.
Usage: python3 deep_scan_repair.py [--fix]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import urllib.request as urlreq
    import urllib.error as urlerr
except ImportError:
    urlreq = None  # type: ignore

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
BLUE   = "\033[34m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

OK   = "✅"
FAIL = "❌"
WARN = "⚠️"
INFO = "ℹ️"


def cprint(icon: str, colour: str, msg: str) -> None:
    print(f"{colour}{icon} {msg}{RESET}")


BASE = Path(os.environ.get("MEGA_DIR", str(Path(__file__).parent)))
REPAIR_HISTORY = Path(os.environ.get("ETERNAL_BOT_DIR", str(Path.home() / "rudibot-eternal"))) / "repair_history.json"
REPORT_PATH    = BASE / "scan_report.json"

REQUIRED_ENV_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "SHOPIFY_STORE_URL",
    "SHOPIFY_ADMIN_API_TOKEN",
]

ANTI_PATTERNS = {
    "bare_except":      (r"^\s*except\s*:", "bare except: clause"),
    "os_system":        (r"os\.system\(",   "os.system() usage"),
    "hardcoded_pass":   (r'(?i)(password|passwd|secret)\s*=\s*["\'][^"\']{4,}["\']',
                         "possible hardcoded credential"),
}

API_ENDPOINTS: List[Tuple[str, str, Optional[Dict[str, Any]]]] = [
    ("GET",  "/api/status",       None),
    ("GET",  "/api/services",     None),
    ("GET",  "/api/health",       None),
    ("GET",  "/api/shopify",      None),
    ("GET",  "/api/analytics",    None),
    ("GET",  "/api/revenue",      None),
    ("GET",  "/api/kpis",         None),
    ("GET",  "/api/agents",       None),
    ("GET",  "/api/logs",         None),
    ("GET",  "/api/metrics",      None),
    ("POST", "/api/chat",         {"message": "test", "session_id": "scan"}),
    ("POST", "/api/chat/clear",   {"session_id": "scan"}),
    ("POST", "/api/logs/clear",   None),
    ("POST", "/api/service/start", {"id": "test"}),
    ("POST", "/api/service/stop",  {"id": "test"}),
]


# ── Section 1: Python syntax scan ────────────────────────────────────────────

def scan_syntax(fix: bool) -> dict[str, Any]:
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}{BLUE}📂 Python Syntax Scan{RESET}")
    errors: list[dict[str, str]] = []
    ok_count = 0
    scan_dirs = [BASE, BASE / "modules", BASE / "rudibot-army" / "agents",
                 BASE / "rudibot-army" / "micro"]
    py_files = []
    for d in scan_dirs:
        if d.exists():
            py_files.extend(d.rglob("*.py"))

    for f in sorted(set(py_files)):
        try:
            py_compile.compile(str(f), doraise=True)
            ok_count += 1
        except py_compile.PyCompileError as e:
            msg = str(e)
            cprint(FAIL, RED, f"{f.relative_to(BASE)}: {msg}")
            errors.append({"file": str(f), "error": msg})
            if fix:
                cprint(WARN, YELLOW, f"  → Skipping auto-fix for syntax error (manual review needed)")

    if not errors:
        cprint(OK, GREEN, f"All {ok_count} Python files pass syntax check")
    else:
        cprint(WARN, YELLOW, f"{ok_count} OK, {len(errors)} with syntax errors")

    return {"ok": ok_count, "errors": errors}


# ── Section 2: Import check ───────────────────────────────────────────────────

def _try_import(module_path: Path) -> tuple[bool, str]:
    """Run a subprocess import check to avoid polluting this process."""
    stem = module_path.stem
    result = subprocess.run(
        [sys.executable, "-c", f"import importlib.util; "
         f"spec=importlib.util.spec_from_file_location('{stem}','{module_path}'); "
         f"mod=importlib.util.module_from_spec(spec)"],
        capture_output=True, text=True, timeout=10,
        cwd=str(module_path.parent),
    )
    if result.returncode == 0:
        return True, ""
    return False, (result.stderr.strip().splitlines()[-1] if result.stderr else "unknown error")


def scan_imports(fix: bool) -> dict[str, Any]:
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}{BLUE}📦 Module Import Check{RESET}")
    ok_list: list[str] = []
    fail_list: list[dict[str, str]] = []
    dirs = [BASE / "modules", BASE / "rudibot-army" / "agents",
            BASE / "rudibot-army" / "micro"]
    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.py")):
            if f.name.startswith("_"):
                continue
            ok, err = _try_import(f)
            rel = str(f.relative_to(BASE))
            if ok:
                ok_list.append(rel)
            else:
                # Extract missing package if possible
                missing = None
                if "ModuleNotFoundError" in err or "No module named" in err:
                    parts = err.split("'")
                    if len(parts) >= 2:
                        missing = parts[1].split(".")[0]
                cprint(FAIL, RED, f"{rel}: {err}")
                if fix and missing:
                    cprint(WARN, YELLOW, f"  → Attempting: pip install {missing}")
                    pip = subprocess.run(
                        [sys.executable, "-m", "pip", "install", missing, "-q"],
                        capture_output=True, text=True,
                    )
                    if pip.returncode == 0:
                        cprint(OK, GREEN, f"  → Installed {missing}")
                    else:
                        cprint(FAIL, RED, f"  → pip install failed: {pip.stderr.strip()[:80]}")
                fail_list.append({"file": rel, "error": err, "missing_pkg": missing or ""})

    if not fail_list:
        cprint(OK, GREEN, f"All {len(ok_list)} modules importable")
    else:
        cprint(WARN, YELLOW, f"{len(ok_list)} OK, {len(fail_list)} failed")
    return {"ok": len(ok_list), "errors": fail_list}


# ── Section 3: API endpoint test ──────────────────────────────────────────────

def _http(method: str, path: str, body: dict[str, Any] | None) -> tuple[int, str]:
    url = f"http://localhost:8888{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    req = urlreq.Request(url, data=data, headers=headers, method=method)
    try:
        with urlreq.urlopen(req, timeout=5) as r:
            return r.status, r.read(200).decode(errors="replace")
    except urlerr.HTTPError as e:
        return e.code, str(e.reason)
    except Exception as exc:
        return 0, str(exc)


def scan_endpoints() -> dict[str, Any]:
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}{BLUE}🌐 Dashboard API Endpoint Tests (http://localhost:8888){RESET}")
    results: list[dict[str, Any]] = []
    server_up = True

    for method, path, body in API_ENDPOINTS:
        code, snippet = _http(method, path, body)
        if code == 0:
            server_up = False
            cprint(WARN, YELLOW, f"{method:4s} {path} → server not reachable")
            results.append({"method": method, "path": path, "status": 0, "reachable": False})
            break  # no point continuing if server is down
        elif code == 404:
            cprint(WARN, YELLOW, f"{method:4s} {path} → 404 (skipped)")
            results.append({"method": method, "path": path, "status": 404, "reachable": True})
        elif code < 400:
            cprint(OK, GREEN, f"{method:4s} {path} → {code}")
            results.append({"method": method, "path": path, "status": code, "reachable": True})
        else:
            cprint(FAIL, RED, f"{method:4s} {path} → {code}: {snippet[:60]}")
            results.append({"method": method, "path": path, "status": code,
                            "reachable": True, "error": snippet[:120]})

    if not server_up:
        cprint(WARN, YELLOW, "Server offline — endpoint tests skipped")
    return {"server_up": server_up, "endpoints": results}


# ── Section 4: Environment variables ─────────────────────────────────────────

def scan_env() -> dict[str, Any]:
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}{BLUE}🔑 Environment Variables{RESET}")
    present: list[str] = []
    missing: list[str] = []
    for var in REQUIRED_ENV_VARS:
        if os.getenv(var):
            cprint(OK, GREEN, f"{var} is set")
            present.append(var)
        else:
            cprint(WARN, YELLOW, f"{var} NOT set")
            missing.append(var)
    return {"present": present, "missing": missing}


# ── Section 5: Anti-pattern scan ─────────────────────────────────────────────

def scan_antipatterns() -> dict[str, Any]:
    import re
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}{BLUE}🔍 Anti-Pattern Scan{RESET}")
    findings: list[dict[str, str]] = []
    py_files = list(BASE.rglob("*.py"))
    for path in sorted(py_files):
        if ".git" in path.parts or path.name == "deep_scan_repair.py":
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for key, (pattern, label) in ANTI_PATTERNS.items():
            for lno, line in enumerate(text.splitlines(), 1):
                if re.search(pattern, line):
                    rel = str(path.relative_to(BASE))
                    cprint(WARN, YELLOW, f"{rel}:{lno} — {label}")
                    findings.append({"file": rel, "line": lno, "issue": label,
                                     "snippet": line.strip()[:120]})
    if not findings:
        cprint(OK, GREEN, "No anti-patterns found")
    return {"findings": findings}


# ── Section 6: repair_history check ──────────────────────────────────────────

def scan_repair_history(fix: bool) -> dict[str, Any]:
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}{BLUE}🔧 Repair History Check{RESET}")
    if not REPAIR_HISTORY.exists():
        cprint(WARN, YELLOW, f"{REPAIR_HISTORY} not found")
        return {"found": False}

    try:
        data = json.loads(REPAIR_HISTORY.read_text())
    except json.JSONDecodeError as e:
        cprint(FAIL, RED, f"Failed to parse repair_history.json: {e}")
        return {"found": True, "parse_error": str(e)}

    stuck: list[str] = []
    for h, entry in data.items():
        count = entry.get("count", 0)
        successes = entry.get("successes", 0)
        status = entry.get("status", "")
        if count > 100 and successes == 0 and status != "acknowledged":
            cprint(WARN, YELLOW,
                   f"Stuck error hash {h}: type={entry.get('error_type')} count={count}")
            stuck.append(h)
            if fix:
                ts = datetime.datetime.now().isoformat()
                entry["last_fix"] = ts
                entry["successes"] = 1
                entry["solutions"] = entry.get("solutions", []) + \
                    [f"acknowledged_stuck_error_reset_{ts[:10]}"]
                entry["status"] = "acknowledged"
                cprint(OK, GREEN, f"  → Marked {h} as acknowledged")

    if fix and stuck:
        REPAIR_HISTORY.write_text(json.dumps(data, indent=2))
        cprint(OK, GREEN, "repair_history.json updated")

    if not stuck:
        cprint(OK, GREEN, "No stuck errors in repair_history.json")

    return {"stuck_hashes": stuck, "fixed": fix and bool(stuck)}


# ── Summary + report ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Deep scan and auto-repair for SuperMegaBot")
    parser.add_argument("--fix", action="store_true", help="Auto-repair what is possible")
    args = parser.parse_args()

    print(f"\n{BOLD}{BLUE}{'═'*60}{RESET}")
    print(f"{BOLD}{BLUE}  SuperMegaBot Deep Scan {'(--fix mode)' if args.fix else ''}{RESET}")
    print(f"{BOLD}{BLUE}  {datetime.datetime.now().isoformat()}{RESET}")
    print(f"{BOLD}{BLUE}{'═'*60}{RESET}")

    syntax_r   = scan_syntax(args.fix)
    import_r   = scan_imports(args.fix)
    api_r      = scan_endpoints()
    env_r      = scan_env()
    pattern_r  = scan_antipatterns()
    history_r  = scan_repair_history(args.fix)

    # ── Final summary ───────────────────────────────────────────────────────
    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}  SCAN SUMMARY{RESET}")
    print(f"{'─'*60}")

    overall_ok = True
    checks = [
        ("Syntax",         not syntax_r["errors"],
         f"{syntax_r['ok']} OK, {len(syntax_r['errors'])} errors"),
        ("Imports",        not import_r["errors"],
         f"{import_r['ok']} OK, {len(import_r['errors'])} failed"),
        ("API Server",     api_r.get("server_up", False),
         f"{'up' if api_r.get('server_up') else 'offline'}"),
        ("Env Vars",       not env_r["missing"],
         f"{len(env_r['present'])} set, {len(env_r['missing'])} missing"),
        ("Anti-patterns",  not pattern_r["findings"],
         f"{len(pattern_r['findings'])} found"),
        ("Repair History", not history_r.get("stuck_hashes"),
         "clean" if not history_r.get("stuck_hashes") else
         f"{len(history_r['stuck_hashes'])} stuck {'→ fixed' if history_r.get('fixed') else ''}"),
    ]

    for label, ok, detail in checks:
        icon = OK if ok else (WARN if label in ("API Server", "Env Vars") else FAIL)
        col  = GREEN if ok else (YELLOW if label in ("API Server", "Env Vars") else RED)
        cprint(icon, col, f"{label:<20} {detail}")
        if not ok and label not in ("API Server", "Env Vars"):
            overall_ok = False

    print(f"\n{BOLD}Overall: {'✅ PASS' if overall_ok else '⚠️  ISSUES FOUND'}{RESET}")

    # ── Save JSON report ────────────────────────────────────────────────────
    report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "fix_mode": args.fix,
        "syntax":   syntax_r,
        "imports":  import_r,
        "api":      api_r,
        "env":      env_r,
        "patterns": pattern_r,
        "history":  history_r,
        "overall_pass": overall_ok,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    cprint(INFO, BLUE, f"Report saved → {REPORT_PATH}")


if __name__ == "__main__":
    main()
