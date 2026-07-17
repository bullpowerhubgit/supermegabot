#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], cwd: Path) -> tuple[bool, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    output = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode == 0, output[-4000:]


def deploy_railway(path: str, project: str, service: str, environment: str) -> dict:
    token = os.getenv("RAILWAY_TOKEN") or os.getenv("RAILWAY_API_TOKEN") or ""
    if not token:
        return {"ok": False, "skipped": True, "reason": "RAILWAY_TOKEN/RAILWAY_API_TOKEN missing"}
    cwd = ROOT / path
    cmd = [
        "railway",
        "up",
        "--detach",
        "--ci",
        "--project",
        project,
        "--service",
        service,
        "--environment",
        environment,
    ]
    ok, output = _run(cmd, cwd)
    return {"ok": ok, "provider": "railway", "output": output}


def _vercel_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.getenv('VERCEL_TOKEN', '')}", "Content-Type": "application/json"}


def _vercel_team_id() -> str:
    return os.getenv("VERCEL_TEAM_ID") or os.getenv("VERCEL_ORG_ID") or ""


def _resolve_vercel_project_id(project: str) -> str:
    token = os.getenv("VERCEL_TOKEN") or ""
    team_id = _vercel_team_id()
    if not token or not team_id:
        return ""
    url = f"https://api.vercel.com/v9/projects/{urllib.parse.quote(project)}?teamId={urllib.parse.quote(team_id)}"
    req = urllib.request.Request(url, headers=_vercel_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return str(data.get("id") or "")
    except Exception:
        return ""


def deploy_vercel(path: str, project: str, production: bool) -> dict:
    token = os.getenv("VERCEL_TOKEN") or ""
    team_id = _vercel_team_id()
    if not token or not team_id:
        return {"ok": False, "skipped": True, "reason": "VERCEL_TOKEN + VERCEL_TEAM_ID/VERCEL_ORG_ID missing"}
    project_id = _resolve_vercel_project_id(project)
    if not project_id:
        return {"ok": False, "skipped": True, "reason": f"Vercel project not found: {project}"}

    cwd = ROOT / path
    vercel_dir = cwd / ".vercel"
    vercel_dir.mkdir(exist_ok=True)
    (vercel_dir / "project.json").write_text(json.dumps({"projectId": project_id, "orgId": team_id}))

    cmd = ["vercel", "deploy", "--yes", "--token", token, "--cwd", str(cwd)]
    if production:
        cmd.insert(2, "--prod")
    ok, output = _run(cmd, cwd)
    return {"ok": ok, "provider": "vercel", "output": output, "production": production}


def _netlify_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.getenv('NETLIFY_AUTH_TOKEN', '')}", "Content-Type": "application/json"}


def _resolve_netlify_site_id(site_name: str, account_id: str = "") -> str:
    token = os.getenv("NETLIFY_AUTH_TOKEN") or ""
    if not token or not site_name:
        return ""
    req = urllib.request.Request("https://api.netlify.com/api/v1/sites", headers=_netlify_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        for site in data if isinstance(data, list) else []:
            if account_id and str(site.get("account_id") or "") != str(account_id):
                continue
            if str(site.get("name") or "") == site_name:
                return str(site.get("id") or "")
    except Exception:
        return ""
    return ""


def deploy_netlify(path: str, site_id: str, site_name: str, account_id: str, production: bool) -> dict:
    token = os.getenv("NETLIFY_AUTH_TOKEN") or ""
    if not token:
        return {"ok": False, "skipped": True, "reason": "NETLIFY_AUTH_TOKEN missing"}
    resolved_site_id = site_id or _resolve_netlify_site_id(site_name, account_id)
    if not resolved_site_id:
        return {
            "ok": False,
            "skipped": True,
            "reason": f"Netlify site not found: {site_name or path}",
        }
    cwd = ROOT / path
    cmd = ["netlify", "deploy", "--dir", str(cwd), "--site", resolved_site_id, "--message", f"Autonomous deploy {path}"]
    if production:
        cmd.insert(2, "--prod")
    ok, output = _run(cmd, cwd)
    return {
        "ok": ok,
        "provider": "netlify",
        "output": output,
        "production": production,
        "site_id": resolved_site_id,
        "site_name": site_name,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deploy one autonomous target to Railway, Vercel, or Netlify")
    ap.add_argument("--provider", required=True, choices=["railway", "vercel", "netlify"])
    ap.add_argument("--path", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--service", default="")
    ap.add_argument("--environment", default="production")
    ap.add_argument("--site-id", default="")
    ap.add_argument("--site-name", default="")
    ap.add_argument("--account-id", default="")
    ap.add_argument("--production", action="store_true")
    args = ap.parse_args(argv)

    if args.provider == "railway":
        result = deploy_railway(args.path, args.project, args.service or args.project, args.environment)
    elif args.provider == "vercel":
        result = deploy_vercel(args.path, args.project, args.production)
    else:
        result = deploy_netlify(args.path, args.site_id, args.site_name or args.project, args.account_id, args.production)
    print(json.dumps(result))
    return 0 if result.get("ok") or result.get("skipped") else 1


if __name__ == "__main__":
    sys.exit(main())
