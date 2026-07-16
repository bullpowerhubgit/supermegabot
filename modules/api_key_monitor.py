#!/usr/bin/env python3
"""
API Key Monitor — Dauerhafter Wächter für alle kritischen API-Keys
==================================================================
Läuft alle 2 Stunden via automation_scheduler.
Wenn ein Key stirbt → sofort Telegram-Alert + Supabase-Log.
Nie mehr silent fail. Nie mehr Credits verbrennen durch toten Key.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.request
from pathlib import Path
from typing import Callable

log = logging.getLogger("APIKeyMonitor")

_SB_URL = os.getenv("SUPABASE_URL", "")
_SB_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")

# ── Key-Definitionen ───────────────────────────────────────────────────────────

def _test_anthropic() -> tuple[bool, str]:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return False, "ANTHROPIC_API_KEY fehlt"
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({"model": "claude-haiku-4-5-20251001", "max_tokens": 1,
                             "messages": [{"role": "user", "content": "hi"}]}).encode(),
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return True, "OK"
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:100]
        if "credit balance" in body.lower():
            return False, f"CREDITS LEER (HTTP {e.code})"
        if e.code == 401:
            return False, f"KEY UNGÜLTIG (HTTP {e.code})"
        return False, f"HTTP {e.code}: {body[:60]}"
    except Exception as ex:
        return False, f"Netzwerkfehler: {ex}"


def _test_openai() -> tuple[bool, str]:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return False, "OPENAI_API_KEY fehlt"
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps({"model": "gpt-4o-mini", "max_tokens": 1,
                             "messages": [{"role": "user", "content": "hi"}]}).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return True, "OK"
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:100]
        if e.code in (401, 403):
            return False, f"KEY UNGÜLTIG (HTTP {e.code})"
        if "billing" in body.lower() or "quota" in body.lower():
            return False, f"CREDITS LEER (HTTP {e.code})"
        return False, f"HTTP {e.code}"
    except Exception as ex:
        return False, f"Netzwerkfehler: {ex}"


def _test_perplexity() -> tuple[bool, str]:
    key = os.getenv("PERPLEXITY_API_KEY", "")
    if not key:
        return False, "PERPLEXITY_API_KEY fehlt"
    try:
        req = urllib.request.Request(
            "https://api.perplexity.ai/chat/completions",
            data=json.dumps({"model": "sonar", "max_tokens": 1,
                             "messages": [{"role": "user", "content": "hi"}]}).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return True, "OK"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, f"KEY UNGÜLTIG — neu generieren: perplexity.ai/settings/api"
        return False, f"HTTP {e.code}"
    except Exception as ex:
        return False, f"Netzwerkfehler: {ex}"


def _test_groq() -> tuple[bool, str]:
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return False, "GROQ_API_KEY fehlt"
    try:
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps({"model": "llama-3.1-8b-instant", "max_tokens": 1,
                             "messages": [{"role": "user", "content": "hi"}]}).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return True, "OK"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, f"KEY UNGÜLTIG — neu: console.groq.com → API Keys"
        return False, f"HTTP {e.code}"
    except Exception as ex:
        return False, f"Netzwerkfehler: {ex}"


def _test_openrouter() -> tuple[bool, str]:
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        return False, "OPENROUTER_API_KEY fehlt"
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return True, "OK"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as ex:
        return False, f"Netzwerkfehler: {ex}"


def _test_telegram() -> tuple[bool, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return False, "TELEGRAM_BOT_TOKEN fehlt"
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
            if data.get("ok"):
                return True, f"@{data['result']['username']}"
            return False, str(data)
    except Exception as ex:
        return False, f"Fehler: {ex}"


def _test_facebook() -> tuple[bool, str]:
    token = os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC") or os.getenv("FACEBOOK_PAGE_TOKEN", "")
    if not token:
        return False, "FACEBOOK_PAGE_TOKEN fehlt"
    try:
        url = f"https://graph.facebook.com/v21.0/me?access_token={token}&fields=id,name"
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
            return True, f"{data.get('name', '?')} ({data.get('id', '?')})"
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:100]
        return False, f"HTTP {e.code}: {body[:60]}"
    except Exception as ex:
        return False, f"Fehler: {ex}"


# ── Key-Registry ───────────────────────────────────────────────────────────────

KEYS: dict[str, Callable[[], tuple[bool, str]]] = {
    "Anthropic":   _test_anthropic,
    "OpenAI":      _test_openai,
    "Perplexity":  _test_perplexity,
    "Groq":        _test_groq,
    "OpenRouter":  _test_openrouter,
    "Telegram":    _test_telegram,
    "Facebook":    _test_facebook,
}

# Renewal-Anleitung für jeden Provider
RENEWAL_LINKS = {
    "Anthropic":  "console.anthropic.com → Plans & Billing",
    "OpenAI":     "platform.openai.com → API Keys → Create new",
    "Perplexity": "perplexity.ai/settings/api → New API Key",
    "Groq":       "console.groq.com → API Keys → Create new",
    "OpenRouter": "openrouter.ai/keys → Create new",
    "Telegram":   "@BotFather → /newbot oder /mybots",
    "Facebook":   "developers.facebook.com → App → Access Tokens",
}


# ── Supabase: Status speichern ─────────────────────────────────────────────────

def _save_status(results: dict[str, dict]) -> None:
    if not _SB_URL or not _SB_KEY:
        return
    try:
        role = "api_key_monitor_status"
        content = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "results": results})

        url_check = f"{_SB_URL}/rest/v1/agent_memory?select=id&agent_role=eq.{role}&type=eq.api_monitor&limit=1"
        req = urllib.request.Request(url_check, headers={
            "apikey": _SB_KEY, "Authorization": f"Bearer {_SB_KEY}"
        })
        with urllib.request.urlopen(req, timeout=5) as r:
            existing = json.loads(r.read())

        if existing:
            body = json.dumps({"content": content}).encode()
            req2 = urllib.request.Request(
                f"{_SB_URL}/rest/v1/agent_memory?id=eq.{existing[0]['id']}",
                data=body,
                headers={"apikey": _SB_KEY, "Authorization": f"Bearer {_SB_KEY}",
                         "Content-Type": "application/json"},
                method="PATCH",
            )
        else:
            body = json.dumps({"agent_role": role, "type": "api_monitor",
                               "content": content}).encode()
            req2 = urllib.request.Request(
                f"{_SB_URL}/rest/v1/agent_memory",
                data=body,
                headers={"apikey": _SB_KEY, "Authorization": f"Bearer {_SB_KEY}",
                         "Content-Type": "application/json", "Prefer": "return=minimal"},
                method="POST",
            )
        with urllib.request.urlopen(req2, timeout=5) as _:
            pass
    except Exception as e:
        log.debug("APIKeyMonitor Supabase save: %s", e)


# ── Telegram Alert ─────────────────────────────────────────────────────────────

def _send_telegram(msg: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        body = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as _:
            pass
    except Exception as e:
        log.warning("Telegram alert failed: %s", e)


# ── Hauptfunktion ──────────────────────────────────────────────────────────────

def run_check(send_alert: bool = True) -> dict:
    """Alle Keys testen. Gibt Ergebnis-Dict zurück."""
    results: dict[str, dict] = {}
    failed: list[str] = []

    for name, test_fn in KEYS.items():
        try:
            ok, detail = test_fn()
        except Exception as e:
            ok, detail = False, f"Exception: {e}"

        results[name] = {"ok": ok, "detail": detail}
        status = "✅" if ok else "❌"
        log.info("APIKeyMonitor: %s %s — %s", status, name, detail)

        if not ok:
            failed.append(name)

    # Supabase Log
    _save_status(results)

    # Telegram Alert bei Fehlern
    if send_alert and failed:
        lines = ["🚨 <b>API KEY ALERT</b> — SuperMegaBot\n"]
        for name in failed:
            detail = results[name]["detail"]
            renewal = RENEWAL_LINKS.get(name, "Provider-Dashboard")
            lines.append(f"❌ <b>{name}</b>: {detail}")
            lines.append(f"   🔑 Neu erstellen: {renewal}\n")

        ok_names = [n for n in results if results[n]["ok"]]
        if ok_names:
            lines.append(f"✅ OK: {', '.join(ok_names)}")

        _send_telegram("\n".join(lines))
        log.warning("APIKeyMonitor: %d Keys tot → Alert gesendet", len(failed))

    return {
        "checked": len(results),
        "ok": len(results) - len(failed),
        "failed": failed,
        "results": results,
    }


async def async_run_check(send_alert: bool = True) -> dict:
    return await asyncio.get_event_loop().run_in_executor(None, run_check, send_alert)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    result = run_check(send_alert=False)
    print(f"\nErgebnis: {result['ok']}/{result['checked']} OK")
    for name, r in result["results"].items():
        icon = "✅" if r["ok"] else "❌"
        print(f"  {icon} {name}: {r['detail']}")
    sys.exit(0 if not result["failed"] else 1)
