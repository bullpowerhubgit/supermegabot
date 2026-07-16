#!/usr/bin/env python3
"""
sync_railway_env.py — Standalone Railway environment sync script.

Usage:
    python3 scripts/sync_railway_env.py [--dry-run] [--validate-only] [--keys KEY1,KEY2,...]

Options:
    --dry-run           Validate and check sync status, but do NOT push vars to Railway
    --validate-only     Only run local validation, skip Railway entirely
    --keys KEY1,KEY2    Comma-separated list of specific keys to sync (default: all)
    --env-file PATH     Path to .env file (default: .env in project root)
    --json              Output machine-readable JSON instead of colored text
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make sure the project root is on sys.path so 'modules' is importable
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent          # .../supermegabot/scripts/
_PROJECT_ROOT = _SCRIPT_DIR.parent                     # .../supermegabot/
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

from modules.env_health_check import (  # noqa: E402
    REQUIRED_KEYS,
    validate_env,
    check_railway_sync,
    sync_to_railway,
)

# ---------------------------------------------------------------------------
# ANSI colour helpers (disabled when --json or non-TTY)
# ---------------------------------------------------------------------------

_USE_COLOUR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not _USE_COLOUR:
        return text
    CODES = {
        "green":  "\033[92m",
        "red":    "\033[91m",
        "yellow": "\033[93m",
        "cyan":   "\033[96m",
        "bold":   "\033[1m",
        "reset":  "\033[0m",
    }
    return f"{CODES.get(code, '')}{text}{CODES['reset']}"


def _ok(msg: str) -> str:
    return _c("green", "OK") + f"  {msg}"


def _fail(msg: str) -> str:
    return _c("red", "ERR") + f" {msg}"


def _warn(msg: str) -> str:
    return _c("yellow", "WRN") + f" {msg}"


def _info(msg: str) -> str:
    return _c("cyan", "---") + f" {msg}"


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and sync .env to Railway",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true", help="Check only, do not push")
    parser.add_argument("--validate-only", action="store_true", help="Local validation only")
    parser.add_argument("--keys", type=str, default="", help="Comma-separated keys to sync")
    parser.add_argument("--env-file", type=str, default=None, help="Path to .env file")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Pretty-print sections
# ---------------------------------------------------------------------------

def _print_header(title: str) -> None:
    if _USE_COLOUR:
        width = 60
        line = "=" * width
        print(f"\n{_c('bold', line)}")
        print(_c("bold", f"  {title}"))
        print(_c("bold", line))
    else:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print("="*60)


def _print_validation(result: dict) -> None:
    _print_header("LOCAL ENVIRONMENT VALIDATION")

    missing = result["missing"]
    invalid = result["invalid"]
    warnings = result["warnings"]

    # Show all required keys with status
    for key in REQUIRED_KEYS:
        is_missing = key in missing
        inv_entry = next((e for e in invalid if e["key"] == key), None)

        if is_missing:
            print(f"  {_fail(key)}")
        elif inv_entry:
            print(f"  {_warn(key + '  (' + inv_entry['issue'] + ')')}")
        else:
            print(f"  {_ok(key)}")

    print()

    if missing:
        print(_c("red", f"  MISSING ({len(missing)}): ") + ", ".join(missing))
    if invalid:
        for entry in invalid:
            print(_c("yellow", f"  FORMAT  ({entry['key']}): ") + entry["issue"] +
                  f"  [got: {entry['value_preview']}]")
    if warnings:
        for w in warnings:
            print(f"  {_warn(w)}")

    status_label = _c("green", "PASS") if result["ok"] else _c("red", "FAIL")
    print(f"\n  Status: {status_label}  —  {result['summary']}")


def _print_sync_check(result: dict) -> None:
    _print_header("RAILWAY SYNC STATUS")

    if result.get("errors"):
        for err in result["errors"]:
            print(f"  {_fail(err)}")
        return

    missing = result["missing_on_railway"]
    stale = result["stale_on_railway"]

    if not missing and not stale:
        print(f"  {_ok('All required keys match Railway')}")
    else:
        if missing:
            print(_c("red", f"  Missing on Railway ({len(missing)}): ") + ", ".join(missing))
        if stale:
            print(_c("yellow", f"  Stale on Railway  ({len(stale)}): ") + ", ".join(stale))

    status_label = _c("green", "IN SYNC") if result["in_sync"] else _c("red", "OUT OF SYNC")
    print(f"\n  Railway: {status_label}")


def _print_sync_result(result: dict) -> None:
    _print_header("RAILWAY SYNC RESULT")

    print(f"  {_ok(str(result['synced']) + ' vars synced to Railway')}")

    if result.get("protected"):
        print(f"  {_c('cyan', 'PROTECTED')} ({len(result['protected'])} vars never pushed — set in Railway manually): "
              + ", ".join(result["protected"]))

    if result["skipped"]:
        print(f"  {_warn(str(result['skipped']) + ' vars skipped (errors)')}")

    if result["errors"]:
        print(f"\n  {_c('red', 'Errors:')}")
        for err in result["errors"][:20]:   # cap display
            print(f"    - {err}")
        if len(result["errors"]) > 20:
            print(f"    ... and {len(result['errors']) - 20} more")

    status_label = _c("green", "DONE") if not result["errors"] else _c("yellow", "PARTIAL")
    print(f"\n  Status: {status_label}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _main(args: argparse.Namespace) -> int:
    """
    Returns 0 on success, 1 on validation failure, 2 on sync failure.
    """

    # ---- Locate and load .env -----------------------------------------------
    if args.env_file:
        env_path = Path(args.env_file).resolve()
    else:
        # Walk up from script dir to find .env
        env_path = _PROJECT_ROOT / ".env"
        if not env_path.exists():
            env_path = Path.cwd() / ".env"

    if not env_path.exists():
        msg = f"Cannot find .env file at {env_path}"
        if args.json_output:
            print(json.dumps({"error": msg}))
        else:
            print(_fail(msg))
        return 1

    load_dotenv(str(env_path), override=True)
    env = dict(os.environ)

    if not args.json_output:
        print(_info(f"Loaded: {env_path}"))

    # ---- Validation ---------------------------------------------------------
    validation = validate_env(env)

    if args.json_output:
        output: dict = {"validation": validation}
    else:
        _print_validation(validation)

    # Abort on missing critical keys (not on invalid format — those are warnings)
    if validation["missing"]:
        if not args.json_output:
            print(_c("red", "\nAborting: fix missing keys before syncing.\n"))
        if args.json_output:
            print(json.dumps(output, indent=2))
        return 1

    if args.validate_only:
        if args.json_output:
            print(json.dumps(output, indent=2))
        else:
            print(_c("cyan", "\n--validate-only flag set — skipping Railway.\n"))
        return 0 if validation["ok"] else 1

    # ---- Sync check ---------------------------------------------------------
    if not args.json_output:
        print(_info("Checking Railway sync status ..."))

    sync_check = await check_railway_sync(env)

    if args.json_output:
        output["railway_sync_check"] = sync_check
    else:
        _print_sync_check(sync_check)

    if args.dry_run:
        if not args.json_output:
            print(_c("cyan", "\n--dry-run flag set — no vars pushed to Railway.\n"))
        if args.json_output:
            print(json.dumps(output, indent=2))
        return 0 if (validation["ok"] and sync_check["in_sync"]) else 1

    # ---- Skip sync if already in sync --------------------------------------
    if sync_check["in_sync"] and not sync_check.get("errors"):
        if not args.json_output:
            print(_c("green", "\nAll vars already in sync — nothing to push.\n"))
        if args.json_output:
            output["sync_result"] = {"synced": 0, "skipped": 0, "errors": [], "note": "already_in_sync"}
            print(json.dumps(output, indent=2))
        return 0

    # ---- Perform sync -------------------------------------------------------
    keys_to_sync: list[str] | None = None
    if args.keys:
        keys_to_sync = [k.strip() for k in args.keys.split(",") if k.strip()]

    if not args.json_output:
        n = len(keys_to_sync) if keys_to_sync else "all"
        print(_info(f"Syncing {n} vars to Railway ..."))

    sync_result = await sync_to_railway(env, keys_to_sync=keys_to_sync)

    if args.json_output:
        output["sync_result"] = sync_result
        print(json.dumps(output, indent=2))
    else:
        _print_sync_result(sync_result)
        print()

    if sync_result["errors"] and sync_result["synced"] == 0:
        return 2  # total failure
    return 0


def main() -> None:
    args = _parse_args()
    if args.json_output:
        global _USE_COLOUR
        _USE_COLOUR = False

    exit_code = asyncio.run(_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
