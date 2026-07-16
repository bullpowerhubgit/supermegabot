#!/usr/bin/env python3
"""
fix_infra_everywhere.py — DAUERHAFT ALLE kritischen Infra-Fixes
================================================================
Ein Script. Alle Stellen. Nie wieder nur lokal.

1) Facebook: ALLE AiiteC-Token-Aliase in Railway = AiiteC Page Token
2) Groq: Key aus .env → Railway + Live-Check (fail wenn 403)
3) Vercel: Deployment Protection (SSO + Password) AUS auf ALLEN Projekten
4) Prozess: MetaTokenResolver apply aliases

Usage:
  python3 scripts/fix_infra_everywhere.py
  python3 scripts/fix_infra_everywhere.py --skip-vercel
  python3 scripts/fix_infra_everywhere.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    # minimal .env loader
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from modules.meta_token_resolver import (  # noqa: E402
    AIITEC_TOKEN_ALIASES,
    apply_aiitec_aliases_to_process,
    audit_aliases,
    get_aiitec_page_token,
)


def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
    return r.returncode, r.stdout or "", r.stderr or ""


def fix_facebook_railway(dry_run: bool = False) -> dict:
    token = get_aiitec_page_token()
    if not token:
        return {"ok": False, "error": "no AiiteC token in .env"}

    apply_aiitec_aliases_to_process(token)
    pairs = [f"{k}={token}" for k in AIITEC_TOKEN_ALIASES]
    # page ids
    pairs.append("FACEBOOK_PAGE_ID=1016738738178786")
    pairs.append("FACEBOOK_ASSET_ID=1016738738178786")
    pairs.append("META_PAGE_ID=1016738738178786")

    if dry_run:
        return {"ok": True, "dry_run": True, "vars": len(pairs), "prefix": token[:20]}

    # railway variables set KEY=VAL ... --skip-deploys
    cmd = ["railway", "variables", "set", *pairs, "--skip-deploys"]
    code, out, err = _run(cmd, timeout=180)
    ok = code == 0
    return {
        "ok": ok,
        "vars_set": len(pairs),
        "prefix": token[:20],
        "stdout": out[-400:],
        "stderr": err[-400:],
        "code": code,
    }


def fix_groq_railway(dry_run: bool = False) -> dict:
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not key:
        return {"ok": False, "error": "GROQ_API_KEY missing in .env", "needs_new_key": True}

    # Live API check
    live = {"models": None, "chat": None}
    try:
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            live["models"] = r.status
    except urllib.error.HTTPError as e:
        live["models"] = e.code
    except Exception as e:
        live["models"] = str(e)

    try:
        body = json.dumps(
            {
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": "ok"}],
                "max_tokens": 3,
            }
        ).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            live["chat"] = r.status
    except urllib.error.HTTPError as e:
        live["chat"] = e.code
    except Exception as e:
        live["chat"] = str(e)

    models_ok = live["models"] == 200
    chat_ok = live["chat"] == 200
    if not models_ok or not chat_ok:
        return {
            "ok": False,
            "error": "Groq API rejected key",
            "live": live,
            "needs_new_key": True,
            "hint": "console.groq.com → API Keys → Create new key → set GROQ_API_KEY in .env then re-run",
        }

    if dry_run:
        return {"ok": True, "dry_run": True, "live": live, "prefix": key[:12]}

    code, out, err = _run(
        ["railway", "variables", "set", f"GROQ_API_KEY={key}", "--skip-deploys"],
        timeout=90,
    )
    return {
        "ok": code == 0,
        "live": live,
        "prefix": key[:12],
        "code": code,
        "stderr": err[-200:],
    }


def _vercel_token() -> str:
    # Prefer env
    t = (os.getenv("VERCEL_TOKEN") or "").strip()
    if t:
        return t
    auth = Path.home() / "Library/Application Support/com.vercel.cli/auth.json"
    if auth.exists():
        return json.loads(auth.read_text()).get("token", "")
    return ""


def fix_vercel_public(dry_run: bool = False) -> dict:
    token = _vercel_token()
    if not token:
        return {"ok": False, "error": "no Vercel token (VERCEL_TOKEN or CLI auth.json)"}

    def api(url: str, method: str = "GET", body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    teams = api("https://api.vercel.com/v2/teams?limit=20").get("teams", [])
    team = next(
        (t for t in teams if "bullpower" in (t.get("slug") or "").lower()),
        teams[0] if teams else None,
    )
    if not team:
        return {"ok": False, "error": "no Vercel team"}
    team_id = team["id"]

    projects = []
    url = f"https://api.vercel.com/v9/projects?teamId={team_id}&limit=100"
    while url:
        data = api(url)
        projects.extend(data.get("projects", []))
        nxt = data.get("pagination", {}).get("next")
        url = (
            f"https://api.vercel.com/v9/projects?teamId={team_id}&limit=100&until={nxt}"
            if nxt
            else None
        )

    if dry_run:
        return {"ok": True, "dry_run": True, "projects": len(projects), "team": team.get("slug")}

    results = []
    for p in projects:
        name = p["name"]
        pid = p["id"]
        try:
            out = api(
                f"https://api.vercel.com/v9/projects/{pid}?teamId={team_id}",
                method="PATCH",
                body={"ssoProtection": None, "passwordProtection": None},
            )
            results.append(
                {
                    "name": name,
                    "ok": True,
                    "sso": out.get("ssoProtection"),
                    "pw": out.get("passwordProtection"),
                }
            )
        except Exception as e:
            results.append({"name": name, "ok": False, "error": str(e)[:120]})

    ok_n = sum(1 for r in results if r.get("ok"))
    return {
        "ok": ok_n == len(results) and len(results) > 0,
        "public": ok_n,
        "total": len(results),
        "team": team.get("slug"),
        "failed": [r for r in results if not r.get("ok")],
    }


def probe_landing_urls() -> dict:
    urls = [
        "https://shopify-brutal-tuning.vercel.app",
        "https://creatorai-ultra.vercel.app",
        "https://autoincome-ai.vercel.app",
        "https://bullpower-hub.vercel.app",
        "https://bullpower-ai.vercel.app",
        "https://creatorstudio-pro.vercel.app",
        "https://digistore24-suite.vercel.app",
        "https://aiitec-all.vercel.app",
        "https://steuercockpit.vercel.app",
        "https://cognitive-symphony.vercel.app",
        "https://launcher-ten-livid.vercel.app",
        "https://shopify-acquisition-engine.vercel.app",
    ]
    out = []
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "SuperMegaBot-PublicProbe/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read(8000).decode("utf-8", errors="ignore")
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
            try:
                body = e.read(4000).decode("utf-8", errors="ignore")
            except Exception:
                body = ""
        except Exception as e:
            out.append({"url": u, "code": 0, "public": False, "error": str(e)[:80]})
            continue
        wall = any(
            x in body.lower()
            for x in (
                "authentication required",
                "deployment protection",
                "vercel login",
                "login to continue",
                "sso protection",
            )
        )
        out.append({"url": u, "code": code, "public": code == 200 and not wall, "wall": wall})
    public_n = sum(1 for x in out if x.get("public"))
    return {"ok": public_n == len(out), "public": public_n, "total": len(out), "pages": out}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-vercel", action="store_true")
    ap.add_argument("--skip-railway", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    report = {"local_audit": audit_aliases()}

    if not args.skip_railway:
        report["facebook_railway"] = fix_facebook_railway(dry_run=args.dry_run)
        report["groq_railway"] = fix_groq_railway(dry_run=args.dry_run)
    else:
        report["facebook_railway"] = {"skipped": True}
        report["groq_railway"] = {"skipped": True}

    if not args.skip_vercel:
        report["vercel_public"] = fix_vercel_public(dry_run=args.dry_run)
        report["landing_probe"] = probe_landing_urls()
    else:
        report["vercel_public"] = {"skipped": True}

    report["ok"] = all(
        bool(report.get(k, {}).get("ok", True) or report.get(k, {}).get("skipped"))
        for k in ("facebook_railway", "groq_railway", "vercel_public", "landing_probe")
        if k in report and not report[k].get("skipped")
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("=== FIX INFRA EVERYWHERE ===")
        for k, v in report.items():
            if k == "ok":
                continue
            status = "PASS" if v.get("ok") or v.get("skipped") else "FAIL"
            print(f"{status:4}  {k}: {json.dumps(v, ensure_ascii=False)[:200]}")
        print("---")
        print("OVERALL", "OK" if report["ok"] else "FAILED")
        if report.get("groq_railway", {}).get("needs_new_key"):
            print("ACTION: Create new Groq key at console.groq.com and set GROQ_API_KEY in .env")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
