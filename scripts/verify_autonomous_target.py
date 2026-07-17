#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORE_PARTS = {".git", ".next", ".netlify", ".vercel", "__pycache__", "build", "dist", "node_modules"}


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORE_PARTS for part in path.parts)


def _iter_python_files(base: Path):
    if base.is_file() and base.suffix == ".py":
        yield base
        return
    for path in sorted(base.rglob("*.py")):
        if path.is_file() and not _is_ignored(path):
            yield path


def verify_python(paths: list[str]) -> dict:
    checked: list[str] = []
    errors: list[str] = []
    for rel_path in paths:
        target = (ROOT / rel_path).resolve()
        if not target.exists():
            errors.append(f"missing: {rel_path}")
            continue
        for py_file in _iter_python_files(target):
            try:
                py_compile.compile(str(py_file), doraise=True)
                checked.append(str(py_file.relative_to(ROOT)))
            except Exception as exc:
                errors.append(f"{py_file.relative_to(ROOT)}: {exc}")
    return {"ok": not errors, "checked": len(checked), "errors": errors[:50]}


def verify_static(paths: list[str]) -> dict:
    checked = []
    errors = []
    for rel_path in paths:
        target = (ROOT / rel_path).resolve()
        if not target.exists():
            errors.append(f"missing: {rel_path}")
            continue
        if target.is_dir():
            expected = [target / "index.html", target / "vercel.json", target / "package.json"]
            if not any(item.exists() for item in expected):
                errors.append(f"{rel_path}: no index.html/vercel.json/package.json")
            else:
                checked.append(rel_path)
        else:
            checked.append(rel_path)
    return {"ok": not errors, "checked": len(checked), "errors": errors[:50]}


def verify_node(paths: list[str]) -> dict:
    result = verify_static(paths)
    if not result["ok"]:
        return result
    if os.getenv("AUTONOMOUS_ENABLE_NODE_BUILD") != "1":
        result["build_skipped"] = True
        return result
    build_errors = []
    for rel_path in paths:
        target = (ROOT / rel_path).resolve()
        package_json = target / "package.json" if target.is_dir() else None
        if not package_json or not package_json.exists():
            continue
        install_cmd = ["npm", "ci", "--ignore-scripts"] if (target / "package-lock.json").exists() else ["npm", "install", "--ignore-scripts"]
        install = subprocess.run(install_cmd, cwd=target, capture_output=True, text=True, check=False)
        if install.returncode != 0:
            build_errors.append(f"{rel_path}: {' '.join(install_cmd)} failed")
            continue
        build = subprocess.run(["npm", "run", "build"], cwd=target, capture_output=True, text=True, check=False)
        if build.returncode != 0:
            build_errors.append(f"{rel_path}: npm run build failed")
    result["ok"] = result["ok"] and not build_errors
    result["errors"].extend(build_errors[:20])
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify one autonomous deploy target")
    ap.add_argument("--runtime", required=True, choices=["python", "node", "static"])
    ap.add_argument("--verify-paths-json", required=True)
    args = ap.parse_args(argv)

    paths = json.loads(args.verify_paths_json)
    if args.runtime == "python":
        result = verify_python(paths)
    elif args.runtime == "node":
        result = verify_node(paths)
    else:
        result = verify_static(paths)

    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
