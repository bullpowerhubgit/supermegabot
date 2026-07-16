#!/usr/bin/env python3
"""API pre-check gate — MUST pass before writing credentials to .env / Railway.

Usage:
  python3 scripts/api_precheck.py
  python3 scripts/api_precheck.py --from-env
  python3 scripts/api_precheck.py --json

Rule: NEVER install a secret that fails its probe.
Exit 0 only if all *required* probes pass; optional probes may fail with WARN.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class ProbeResult:
    name: str
    ok: bool
    status: str
    detail: str
    required: bool = True


def _load_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def _http(
    url: str,
    headers: dict | None = None,
    data: bytes | None = None,
    method: str | None = None,
    timeout: int = 20,
) -> tuple[int | None, bytes]:
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers or {},
        method=method or ("POST" if data else "GET"),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()[:800]
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:800]
    except Exception as e:
        return None, str(e).encode()


def probe_youtube(api_key: str) -> ProbeResult:
    if not api_key:
        return ProbeResult("youtube_api_key", False, "empty", "missing key")
    code, body = _http(
        "https://www.googleapis.com/youtube/v3/channels"
        f"?part=snippet&id=UC_x5XG1OV2P6uZZ5FSM9Ttw&key={api_key}"
    )
    ok = code == 200
    return ProbeResult(
        "youtube_api_key",
        ok,
        str(code),
        body[:120].decode("utf-8", "replace"),
    )


def probe_youtube_sa(path: str) -> ProbeResult:
    if not path or not Path(path).exists():
        return ProbeResult(
            "youtube_service_account",
            False,
            "missing",
            f"file not found: {path}",
            required=False,
        )
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            path,
            scopes=[
                "https://www.googleapis.com/auth/youtube.readonly",
                "https://www.googleapis.com/auth/cloud-platform",
            ],
        )
        creds.refresh(Request())
        ok = bool(creds.token)
        return ProbeResult(
            "youtube_service_account",
            ok,
            "200" if ok else "0",
            f"token ok email={creds.service_account_email}",
            required=False,
        )
    except Exception as e:
        return ProbeResult(
            "youtube_service_account", False, "error", str(e)[:200], required=False
        )


def probe_gemini(api_key: str) -> ProbeResult:
    if not api_key:
        return ProbeResult("gemini_api_key", False, "empty", "missing key")
    code, body = _http(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": api_key},
    )
    ok = code == 200
    return ProbeResult(
        "gemini_api_key",
        ok,
        str(code),
        body[:140].decode("utf-8", "replace"),
    )


def probe_telegram(token: str, label: str = "telegram") -> ProbeResult:
    if not token:
        return ProbeResult(label, False, "empty", "missing token")
    code, body = _http(f"https://api.telegram.org/bot{token}/getMe")
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        data = {}
    ok = code == 200 and bool(data.get("ok"))
    uname = (data.get("result") or {}).get("username", "")
    return ProbeResult(
        label,
        ok,
        str(code),
        f"@{uname}" if ok else body[:120].decode("utf-8", "replace"),
    )


def probe_resend(api_key: str) -> ProbeResult:
    if not api_key:
        return ProbeResult("resend", False, "empty", "missing", required=False)
    code, body = _http(
        "https://api.resend.com/domains",
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "SuperMegaBot-precheck/1.0",
        },
    )
    ok = code == 200
    return ProbeResult(
        "resend",
        ok,
        str(code),
        body[:120].decode("utf-8", "replace"),
        required=False,
    )


def probe_twitter_oauth1(
    api_key: str, api_secret: str, access: str, access_secret: str
) -> ProbeResult:
    if not all([api_key, api_secret, access, access_secret]):
        return ProbeResult("twitter_oauth1", False, "empty", "missing oauth1 fields")
    try:
        import requests
        from requests_oauthlib import OAuth1

        auth = OAuth1(api_key, api_secret, access, access_secret)
        r = requests.get(
            "https://api.twitter.com/2/users/me", auth=auth, timeout=20
        )
        ok = r.status_code == 200
        return ProbeResult(
            "twitter_oauth1",
            ok,
            str(r.status_code),
            r.text[:140],
        )
    except Exception as e:
        return ProbeResult("twitter_oauth1", False, "error", str(e)[:200])


def run_from_env(env: dict[str, str]) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    results.append(probe_youtube(env.get("YOUTUBE_API_KEY", "")))
    results.append(
        probe_youtube_sa(
            env.get("YOUTUBE_SERVICE_ACCOUNT_PATH")
            or env.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        )
    )
    results.append(probe_gemini(env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY", "")))
    results.append(
        probe_telegram(env.get("TELEGRAM_BOT_TOKEN", ""), "telegram_main")
    )
    results.append(
        probe_telegram(env.get("TELEGRAM_BOT_TOKEN_2", ""), "telegram_2")
    )
    results.append(probe_resend(env.get("RESEND_API_KEY", "")))
    results.append(
        probe_twitter_oauth1(
            env.get("TWITTER_API_KEY", ""),
            env.get("TWITTER_API_SECRET", ""),
            env.get("TWITTER_ACCESS_TOKEN", ""),
            env.get("TWITTER_ACCESS_TOKEN_SECRET", ""),
        )
    )
    return results


def run_candidates(candidates: dict[str, Any]) -> list[ProbeResult]:
    """Probe raw candidate secrets before install."""
    results: list[ProbeResult] = []
    if "YOUTUBE_API_KEY" in candidates:
        results.append(probe_youtube(candidates["YOUTUBE_API_KEY"]))
    if "YOUTUBE_SERVICE_ACCOUNT_PATH" in candidates:
        results.append(probe_youtube_sa(candidates["YOUTUBE_SERVICE_ACCOUNT_PATH"]))
    if "GEMINI_API_KEY" in candidates:
        results.append(probe_gemini(candidates["GEMINI_API_KEY"]))
    for label, key in (
        ("telegram_main", "TELEGRAM_BOT_TOKEN"),
        ("telegram_2", "TELEGRAM_BOT_TOKEN_2"),
        ("telegram_rudiclone", "TELEGRAM_BOT_TOKEN_RUDICLONE"),
    ):
        if key in candidates:
            results.append(probe_telegram(candidates[key], label))
    if "RESEND_API_KEY" in candidates:
        results.append(probe_resend(candidates["RESEND_API_KEY"]))
    if all(
        k in candidates
        for k in (
            "TWITTER_API_KEY",
            "TWITTER_API_SECRET",
            "TWITTER_ACCESS_TOKEN",
            "TWITTER_ACCESS_TOKEN_SECRET",
        )
    ):
        results.append(
            probe_twitter_oauth1(
                candidates["TWITTER_API_KEY"],
                candidates["TWITTER_API_SECRET"],
                candidates["TWITTER_ACCESS_TOKEN"],
                candidates["TWITTER_ACCESS_TOKEN_SECRET"],
            )
        )
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="API pre-check before credential install")
    ap.add_argument("--from-env", action="store_true", help="Probe keys from .env")
    ap.add_argument("--env-file", default=str(ROOT / ".env"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any required probe fails (default)",
        default=True,
    )
    args = ap.parse_args()

    env = _load_dotenv(Path(args.env_file))
    # merge process env
    for k, v in os.environ.items():
        env.setdefault(k, v)

    results = run_from_env(env)

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        print("=" * 64)
        print("API PRE-CHECK (install only if PASS)")
        print("=" * 64)
        for r in results:
            flag = "PASS" if r.ok else ("WARN" if not r.required else "FAIL")
            print(f"[{flag}] {r.name}: HTTP {r.status} | {r.detail[:100]}")
        print("=" * 64)
        req_fail = [r for r in results if r.required and not r.ok]
        opt_fail = [r for r in results if not r.required and not r.ok]
        print(
            f"required_fail={len(req_fail)} optional_fail={len(opt_fail)} total={len(results)}"
        )
        if req_fail:
            print("DO NOT INSTALL failing required keys:", ", ".join(r.name for r in req_fail))

    req_fail = [r for r in results if r.required and not r.ok]
    return 1 if req_fail else 0


if __name__ == "__main__":
    sys.exit(main())
