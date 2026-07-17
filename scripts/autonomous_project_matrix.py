#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.autonomous_projects import filter_targets_by_changes, get_changed_files, list_targets


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Emit GitHub Actions matrix for autonomous project targets")
    ap.add_argument("--provider", choices=["all", "railway", "vercel"], default="all")
    ap.add_argument("--base-ref", default="")
    ap.add_argument("--head-ref", default="")
    ap.add_argument("--changed-only", action="store_true")
    args = ap.parse_args(argv)

    targets = list_targets(provider=args.provider)
    changed_files: list[str] = []
    if args.changed_only and args.base_ref and args.head_ref:
        changed_files = get_changed_files(args.base_ref, args.head_ref)
        targets = filter_targets_by_changes(targets, changed_files)

    print(json.dumps({"include": targets}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
