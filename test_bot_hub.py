#!/usr/bin/env python3
"""
test_bot_hub.py — End-to-end smoke test for the SuperMegaBot Hub.

Starts the dashboard, hits every documented endpoint, exercises
`/api/bot/commands` + `/api/bot/execute`, and verifies the bot bridge
script is importable.  Used by `deploy_with_tests.sh` and CI.

Usage:
    python3 test_bot_hub.py
    python3 test_bot_hub.py --no-server   # assume dashboard is already running

Exit codes:
    0  all checks passed
    1  one or more checks failed
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
PORT = int(os.environ.get("DASHBOARD_PORT", "8889"))  # 8889 to avoid clashes
URL = f"http://localhost:{PORT}"

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def _http(method: str, path: str, body: dict | None = None) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:
        return 0, str(e)


CHECKS: list[tuple[str, str, dict | None, int]] = [
    # method, path, body, accepted_status (404 is acceptable for service-unknown)
    ("GET", "/health", None, 200),
    ("GET", "/api/health", None, 200),
    ("GET", "/api/status", None, 200),
    ("GET", "/api/services", None, 200),
    ("GET", "/api/services/status", None, 200),
    ("GET", "/api/metrics", None, 200),
    ("GET", "/api/system", None, 200),
    ("GET", "/api/shopify", None, 200),
    ("GET", "/api/shopify/status", None, 200),
    ("GET", "/api/analytics", None, 200),
    ("GET", "/api/revenue", None, 200),
    ("GET", "/api/kpis", None, 200),
    ("GET", "/api/agents", None, 200),
    ("GET", "/api/army/status", None, 200),
    ("GET", "/api/autopilot/agents", None, 200),
    ("GET", "/api/logs", None, 200),
    ("GET", "/api/bot/commands", None, 200),
    ("POST", "/api/chat", {"text": "/help"}, 200),
    ("POST", "/api/chat", {"message": "/help"}, 200),
    ("POST", "/api/chat/clear", {"session_id": "smoke"}, 200),
    ("POST", "/api/logs/clear", None, 200),
    ("POST", "/api/bot/execute", {"command": "/help"}, 200),
]


def run_checks() -> tuple[int, int]:
    passed = 0
    failed = 0
    for method, path, body, accepted in CHECKS:
        code, snippet = _http(method, path, body)
        if code == accepted:
            print(f"{GREEN}PASS{RESET} {method:4s} {path} → {code}")
            passed += 1
        else:
            print(f"{RED}FAIL{RESET} {method:4s} {path} → {code} (expected {accepted}) {snippet[:120]}")
            failed += 1

    # Verify bot/commands returns a non-empty command list
    code, body = _http("GET", "/api/bot/commands")
    try:
        data = json.loads(body)
        cmds = data.get("all", [])
        if cmds:
            print(f"{GREEN}PASS{RESET} bot/commands count={len(cmds)} (sample: {cmds[:5]})")
            passed += 1
        else:
            print(f"{RED}FAIL{RESET} bot/commands returned empty list")
            failed += 1
    except Exception as e:
        print(f"{RED}FAIL{RESET} bot/commands could not parse: {e}")
        failed += 1

    return passed, failed


def verify_bridge_importable() -> bool:
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "telegram_hub_bridge", BASE / "telegram_hub_bridge.py"
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        # Don't run main loop — just verify imports succeed.
        spec.loader.exec_module(mod)
        assert hasattr(mod, "main_loop")
        print(f"{GREEN}PASS{RESET} telegram_hub_bridge.py imports cleanly")
        return True
    except Exception as e:
        print(f"{RED}FAIL{RESET} telegram_hub_bridge.py import error: {e}")
        return False


def start_server() -> subprocess.Popen:
    log = open("/tmp/test_bot_hub_dashboard.log", "w")
    proc = subprocess.Popen(
        [sys.executable, str(BASE / "dashboard" / "server.py")],
        cwd=str(BASE),
        stdout=log,
        stderr=subprocess.STDOUT,
        env={**os.environ, "DASHBOARD_PORT": str(PORT)},
        start_new_session=True,
    )
    # Wait for server to be reachable
    for _ in range(40):
        code, _ = _http("GET", "/health")
        if code == 200:
            return proc
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("Dashboard server did not become ready within 20 seconds")


def stop_server(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-server", action="store_true",
                    help="Assume dashboard is already running on $DASHBOARD_PORT (default 8889)")
    args = ap.parse_args()

    proc = None
    if not args.no_server:
        print(f"{YELLOW}Starting dashboard on port {PORT}…{RESET}")
        try:
            proc = start_server()
        except Exception as e:
            print(f"{RED}Could not start dashboard: {e}{RESET}")
            return 1

    try:
        passed, failed = run_checks()
        if not verify_bridge_importable():
            failed += 1
        print()
        if failed:
            print(f"{RED}{failed} failed, {passed} passed{RESET}")
            return 1
        print(f"{GREEN}All {passed} checks passed{RESET}")
        return 0
    finally:
        if proc:
            stop_server(proc)


if __name__ == "__main__":
    sys.exit(main())
