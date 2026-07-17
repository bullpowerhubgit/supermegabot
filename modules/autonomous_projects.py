#!/usr/bin/env python3
"""
Autonomous Projects — discover and summarize deployable Railway/Vercel targets.

This module gives the autonomous loop and GitHub Actions one consistent source of
truth for cross-project deploy surfaces inside the monorepo.
"""
from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "autonomous_projects.json"
IGNORE_PARTS = {
    ".git",
    ".next",
    ".netlify",
    ".vercel",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


def _norm(path: str | Path) -> str:
    raw = str(path).replace("\\", "/").strip()
    return "." if raw in ("", ".") else raw.rstrip("/")


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORE_PARTS for part in path.parts)


def _load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {"defaults": {}, "overrides": {}}
    return json.loads(CONFIG_PATH.read_text())


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text())
    except Exception:
        return {}


def _guess_runtime(dir_path: Path) -> str:
    if (dir_path / "requirements.txt").exists():
        return "python"
    if any(dir_path.glob("*.py")):
        return "python"
    if (dir_path / "package.json").exists():
        return "node"
    return "static"


def _railway_service_name(data: dict[str, Any], fallback: str) -> str:
    services = data.get("services") or []
    if services and isinstance(services[0], dict):
        name = str(services[0].get("name") or "").strip()
        if name:
            return name
    return fallback


def _watch_paths_for(rel_dir: str, override: dict[str, Any]) -> list[str]:
    watch_paths = override.get("watch_paths")
    if watch_paths:
        return [_norm(p) for p in watch_paths]
    if rel_dir == ".":
        return ["**"]
    return [f"{rel_dir}/**"]


def _verify_paths_for(rel_dir: str, override: dict[str, Any]) -> list[str]:
    verify_paths = override.get("verify_paths")
    if verify_paths:
        return [_norm(p) for p in verify_paths]
    return [rel_dir]


def list_targets(provider: str = "all") -> list[dict[str, Any]]:
    config = _load_config()
    defaults = config.get("defaults") or {}
    overrides = config.get("overrides") or {}
    targets: list[dict[str, Any]] = []

    for railway_file in sorted(ROOT.rglob("railway.toml")):
        if _is_ignored(railway_file):
            continue
        dir_path = railway_file.parent
        rel_dir = _norm(dir_path.relative_to(ROOT))
        override = overrides.get(rel_dir, {})
        if override.get("enabled") is False:
            continue
        railway_cfg = override.get("railway") or {}
        runtime = _guess_runtime(dir_path)
        fallback_name = ROOT.name if rel_dir == "." else dir_path.name
        toml_data = _read_toml(railway_file)
        service_name = railway_cfg.get("service") or _railway_service_name(toml_data, fallback_name)
        project_name = railway_cfg.get("project") or service_name
        targets.append(
            {
                "name": override.get("name") or service_name,
                "provider": "railway",
                "path": rel_dir,
                "runtime": runtime,
                "watch_paths": _watch_paths_for(rel_dir, override),
                "verify_paths": _verify_paths_for(rel_dir, override),
                "railway": {
                    "project": project_name,
                    "service": service_name,
                    "environment": railway_cfg.get("environment") or defaults.get("railway_environment") or "production",
                },
            }
        )

    for vercel_file in sorted(ROOT.rglob("vercel.json")):
        if _is_ignored(vercel_file):
            continue
        dir_path = vercel_file.parent
        rel_dir = _norm(dir_path.relative_to(ROOT))
        override = overrides.get(rel_dir, {})
        if override.get("enabled") is False:
            continue
        vercel_cfg = override.get("vercel") or {}
        targets.append(
            {
                "name": override.get("name") or dir_path.name,
                "provider": "vercel",
                "path": rel_dir,
                "runtime": _guess_runtime(dir_path),
                "watch_paths": _watch_paths_for(rel_dir, override),
                "verify_paths": _verify_paths_for(rel_dir, override),
                "vercel": {
                    "project": vercel_cfg.get("project") or dir_path.name,
                },
            }
        )

    if provider != "all":
        targets = [target for target in targets if target.get("provider") == provider]
    return targets


def get_changed_files(base_ref: str | None = None, head_ref: str | None = None) -> list[str]:
    if not base_ref or not head_ref:
        return []
    proc = subprocess.run(
        ["git", "--no-pager", "diff", "--name-only", base_ref, head_ref],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [_norm(line) for line in proc.stdout.splitlines() if line.strip()]


def _matches_watch(file_path: str, pattern: str) -> bool:
    if pattern == "**":
        return True
    return fnmatch.fnmatch(file_path, pattern)


def filter_targets_by_changes(
    targets: list[dict[str, Any]],
    changed_files: list[str],
) -> list[dict[str, Any]]:
    if not changed_files:
        return targets
    selected: list[dict[str, Any]] = []
    for target in targets:
        watch_paths = target.get("watch_paths") or []
        if any(_matches_watch(changed, pattern) for changed in changed_files for pattern in watch_paths):
            selected.append(target)
    return selected


def get_deploy_surface_summary() -> dict[str, Any]:
    targets = list_targets()
    railway_ready = bool(os.getenv("RAILWAY_TOKEN") or os.getenv("RAILWAY_API_TOKEN"))
    vercel_ready = bool(os.getenv("VERCEL_TOKEN") and (os.getenv("VERCEL_TEAM_ID") or os.getenv("VERCEL_ORG_ID")))
    provider_counts = {"railway": 0, "vercel": 0}
    for target in targets:
        provider_counts[target["provider"]] = provider_counts.get(target["provider"], 0) + 1
    missing: list[str] = []
    if provider_counts.get("railway") and not railway_ready:
        missing.append("RAILWAY_TOKEN/RAILWAY_API_TOKEN")
    if provider_counts.get("vercel") and not vercel_ready:
        missing.append("VERCEL_TOKEN + VERCEL_TEAM_ID/VERCEL_ORG_ID")
    return {
        "ok": True,
        "targets_total": len(targets),
        "provider_counts": provider_counts,
        "railway_ready": railway_ready,
        "vercel_ready": vercel_ready,
        "missing_providers": missing,
        "targets": targets,
    }
