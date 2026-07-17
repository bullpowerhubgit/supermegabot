#!/usr/bin/env python3
"""
Loop Commit Engine — KI-Plan → GitHub Branch + PR (vollautomatisch).

Liest data/autonomous_loop/latest.json
Wenn ai_plan enthält deploy_safe=true → Branch erstellen + PR öffnen.

Kein git-subprocess — nur GitHub REST API via aiohttp.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

log = logging.getLogger("LoopCommitEngine")

_BASE     = Path(__file__).resolve().parents[1]
_LOOP_DIR = _BASE / "data" / "autonomous_loop"
_BACKLOG  = _BASE / "BACKLOG.md"

GITHUB_API = "https://api.github.com"


def _github_token() -> str:
    return os.getenv("GITHUB_TOKEN", "")

def _repo() -> str:
    return os.getenv("GITHUB_REPO", "bullpowerhubgit/supermegabot")

def _tg_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")

def _tg_chat() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


def _headers() -> dict:
    return {
        "Authorization": f"token {_github_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ── GitHub API Calls ─────────────────────────────────────────────────────────

async def _get_default_branch_sha() -> str | None:
    repo = _repo()
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"{GITHUB_API}/repos/{repo}/git/refs/heads/main",
            headers=_headers(),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status != 200:
                return None
            data = await r.json()
            return data.get("object", {}).get("sha")


async def _create_branch(branch: str, sha: str) -> bool:
    repo = _repo()
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{GITHUB_API}/repos/{repo}/git/refs",
            headers=_headers(),
            json={"ref": f"refs/heads/{branch}", "sha": sha},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            return r.status in (200, 201, 422)  # 422 = branch already exists


async def _push_file(branch: str, path: str, content: str, message: str) -> bool:
    """Erstellt/aktualisiert eine Datei im Branch via GitHub API."""
    import base64
    repo    = _repo()
    encoded = base64.b64encode(content.encode()).decode()

    async with aiohttp.ClientSession() as s:
        # Bestehenden SHA holen (für Update)
        existing_sha = None
        async with s.get(
            f"{GITHUB_API}/repos/{repo}/contents/{path}?ref={branch}",
            headers=_headers(),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status == 200:
                existing_sha = (await r.json()).get("sha")

        payload: dict[str, Any] = {
            "message": message,
            "content": encoded,
            "branch": branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha

        async with s.put(
            f"{GITHUB_API}/repos/{repo}/contents/{path}",
            headers=_headers(),
            json=payload,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            return r.status in (200, 201)


async def _create_pr(branch: str, title: str, body: str) -> str | None:
    repo = _repo()
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{GITHUB_API}/repos/{repo}/pulls",
            headers=_headers(),
            json={
                "title": title,
                "body": body,
                "head": branch,
                "base": "main",
                "draft": True,
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status in (200, 201):
                data = await r.json()
                return data.get("html_url")
            text = await r.text()
            log.warning("PR-Erstellung fehlgeschlagen: %s — %s", r.status, text[:200])
            return None


async def _notify_telegram(msg: str) -> None:
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg[:4000], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram Fehler: %s", e)


# ── KI-Plan auslesen ─────────────────────────────────────────────────────────

def _parse_ai_plan(report: dict) -> dict | None:
    """Extrahiert strukturierten Plan aus dem Loop-Report."""
    raw = report.get("claude_iterate", {}).get("ai_plan") or ""
    if not raw:
        return None
    # JSON aus dem Plan extrahieren (Claude gibt manchmal Fließtext + JSON)
    for start_char in ["{", "```json\n{"]:
        idx = raw.find(start_char.replace("```json\n", ""))
        if idx != -1:
            try:
                return json.loads(raw[idx:raw.rfind("}") + 1])
            except Exception:
                pass
    # Fallback: plan als Text
    return {
        "summary": raw[:200],
        "deploy_safe": False,
        "code_changes": [],
        "expected_revenue_impact": "unbekannt",
    }


# ── Haupt-Funktion ───────────────────────────────────────────────────────────

async def run_commit_cycle(report: dict | None = None) -> dict[str, Any]:
    """
    Liest den neuesten Loop-Report, erstellt Branch + PR wenn deploy_safe=True.
    Kann auch direkt mit einem report-dict aufgerufen werden.
    """
    if not _github_token():
        return {"ok": False, "skipped": True, "reason": "GITHUB_TOKEN fehlt"}

    # Report laden
    if report is None:
        latest = _LOOP_DIR / "latest.json"
        if not latest.exists():
            return {"ok": False, "skipped": True, "reason": "Kein Loop-Report vorhanden"}
        report = json.loads(latest.read_text())

    plan = _parse_ai_plan(report)
    if not plan:
        return {"ok": True, "skipped": True, "reason": "Kein KI-Plan im Report"}

    if not plan.get("deploy_safe"):
        log.info("Plan nicht deploy-safe — kein Auto-Commit")
        return {"ok": True, "skipped": True, "reason": "deploy_safe=False", "plan_summary": plan.get("summary", "")[:100]}

    summary = plan.get("summary", "Autonomous optimization")[:80]
    ts      = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch  = f"autonomous/loop-{ts}"

    # BACKLOG.md aktualisieren
    backlog_content = (
        f"# Autonomous Loop — Backlog\n\n"
        f"**Letzte Iteration:** {datetime.now(timezone.utc).isoformat()}\n\n"
        f"## Aktueller Plan\n\n"
        f"**Zusammenfassung:** {summary}\n\n"
        f"**Revenue Impact:** {plan.get('expected_revenue_impact', '?')}\n\n"
        f"## Code-Änderungen\n\n"
    )
    for change in plan.get("code_changes") or []:
        if isinstance(change, dict):
            backlog_content += f"- `{change.get('file', '?')}`: {change.get('intent', '?')}\n"
        else:
            backlog_content += f"- {change}\n"

    # next_iteration.json
    next_iter = json.dumps({
        "plan": plan,
        "branch": branch,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2)

    try:
        sha = await _get_default_branch_sha()
        if not sha:
            return {"ok": False, "error": "main branch SHA nicht abrufbar"}

        await _create_branch(branch, sha)
        await _push_file(branch, "BACKLOG.md", backlog_content, f"🤖 autonomous: update backlog — {summary[:50]}")
        await _push_file(branch, "data/next_iteration.json", next_iter, "🤖 autonomous: next iteration plan")

        pr_title = f"🤖 Autonomous: {summary[:60]}"
        pr_body  = (
            f"## Autonomer Loop — Auto-PR\n\n"
            f"**Plan:** {summary}\n\n"
            f"**Revenue Impact:** {plan.get('expected_revenue_impact', '?')}\n\n"
            f"**Erstellt:** {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}\n\n"
            f"*Generiert vom Autonomous Loop — bitte prüfen vor Merge.*"
        )
        pr_url = await _create_pr(branch, pr_title, pr_body)

        if pr_url:
            await _notify_telegram(
                f"🚀 <b>Auto-PR erstellt</b>\n"
                f"📋 {summary}\n"
                f"🔗 {pr_url}\n"
                f"<i>Deploy nach Merge → Railway auto-deploy</i>"
            )
            return {"ok": True, "branch": branch, "pr_url": pr_url, "summary": summary}
        return {"ok": False, "error": "PR-Erstellung fehlgeschlagen", "branch": branch}

    except Exception as e:
        log.error("Commit-Cycle Fehler: %s", e)
        return {"ok": False, "error": str(e)[:200]}


async def get_recent_prs() -> dict[str, Any]:
    """Gibt die letzten autonomen PRs zurück."""
    if not _github_token():
        return {"ok": False, "prs": []}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{GITHUB_API}/repos/{_repo()}/pulls?state=open&per_page=10",
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                prs = await r.json()
        auto_prs = [
            {"title": p["title"], "url": p["html_url"], "created": p["created_at"]}
            for p in prs if p.get("title", "").startswith("🤖")
        ]
        return {"ok": True, "prs": auto_prs}
    except Exception as e:
        return {"ok": False, "error": str(e)}
