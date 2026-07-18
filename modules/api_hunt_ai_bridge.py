"""
APIHunt AI Bridge — Nil wieder ohne API.

Verwaltet ALLE kostenlosen AI-Provider automatisch.
Wenn ein Key fehlt, wird der Anbieter übersprungen.
Wenn alle bezahlten Provider leer sind → Pollinations.ai (kein Key nötig).

Neue Provider werden vom free_api_hunt_daemon.py in discovered_apis gespeichert
und hier automatisch als Fallback eingebunden.

Provider-Übersicht (alle kostenlos / free-tier):
  0. OpenAI (OPENAI_API_KEY)
  1. Together AI (TOGETHER_API_KEY)   — $25 Gratis-Credit beim Signup
  2. Fireworks AI (FIREWORKS_API_KEY) — $1/Monat free
  3. Google Gemini (GOOGLE_API_KEY)   — 15 RPM free
  4. Cohere (COHERE_API_KEY)          — 1000 req/Monat free
  5. AI21 Labs (AI21_API_KEY)         — free tier
  6. Lepton AI (LEPTON_API_KEY)       — kostenlose Modelle
  7. Cloudflare AI (CF_API_TOKEN + CF_ACCOUNT_ID)  — Workers AI gratis
  8. Pollinations.ai                  — KEIN KEY NÖTIG (absoluter Notfall)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

# ── Env-Key-Getter ─────────────────────────────────────────────────────────────
def _openai()      -> str: return os.getenv("OPENAI_API_KEY", "")
def _together()    -> str: return os.getenv("TOGETHER_API_KEY", "")
def _fireworks()   -> str: return os.getenv("FIREWORKS_API_KEY", "")
def _gemini()      -> str: return os.getenv("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))
def _cohere()      -> str: return os.getenv("COHERE_API_KEY", "")
def _ai21()        -> str: return os.getenv("AI21_API_KEY", "")
def _lepton()      -> str: return os.getenv("LEPTON_API_KEY", "")
def _cf_token()    -> str: return os.getenv("CF_API_TOKEN", os.getenv("CLOUDFLARE_API_TOKEN", ""))
def _cf_account()  -> str: return os.getenv("CF_ACCOUNT_ID", os.getenv("CLOUDFLARE_ACCOUNT_ID", ""))

# ── Modell-Listen ──────────────────────────────────────────────────────────────
_OPENAI_MODELS = ["gpt-4o-mini", "gpt-3.5-turbo"]
_TOGETHER_MODELS = [
    "meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
    "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    "mistralai/Mixtral-8x7B-Instruct-v0.1",
]
_FIREWORKS_MODELS = [
    "accounts/fireworks/models/llama-v3p1-8b-instruct",
    "accounts/fireworks/models/mixtral-8x7b-instruct",
]
_GEMINI_MODELS = ["gemini-1.5-flash-latest", "gemini-1.5-pro-latest"]
_COHERE_MODELS = ["command-r", "command-light"]
_AI21_MODELS = ["jamba-1.5-mini", "jamba-1.5-large"]
_LEPTON_MODELS = ["llama3-1-8b", "mixtral-8x7b"]

# ── No-Auth Notfall-Providers ─────────────────────────────────────────────────
_POLLINATIONS_URL = "https://text.pollinations.ai/openai/chat/completions"
_CLOUDFLARE_BASE  = "https://api.cloudflare.com/client/v4/accounts/{}/ai/run"
_CF_MODEL         = "@cf/meta/llama-3.1-8b-instruct"

# ── Circuit-Breaker (lokal, teilt Status mit ai_client._CB wenn importiert) ───
_LOCAL_CB: dict = {}

def _cb_ok(name: str) -> bool:
    s = _LOCAL_CB.get(name)
    if s and s.get("until", 0) > time.time():
        return False
    return True

def _cb_fail(name: str, seconds: int = 300) -> None:
    _LOCAL_CB[name] = {"until": time.time() + seconds}

def _cb_ok_shared(name: str) -> bool:
    try:
        from modules.ai_client import _CB
        s = _CB.get(name)
        if s and s.get("until", 0) > time.time():
            return False
    except Exception:
        pass
    return _cb_ok(name)


async def try_bridge_providers(messages: list, max_tokens: int = 800) -> str:
    """
    Probiert alle fehlenden AI-Provider durch.
    Rückgabe: generierter Text oder "" wenn alle scheitern.
    """
    import aiohttp

    # ── 0. OpenAI ──────────────────────────────────────────────────────────────
    if _openai() and _cb_ok_shared("OpenAI"):
        for model in _OPENAI_MODELS:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {_openai()}", "Content-Type": "application/json"},
                        json={"model": model, "messages": messages, "max_tokens": max_tokens},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
                            if text:
                                log.info("Bridge: OpenAI OK model=%s", model)
                                return text
                        elif r.status == 402:
                            _cb_fail("OpenAI", 86400)
                            break
                        elif r.status == 429:
                            _cb_fail("OpenAI", 90)
                            break
            except Exception as e:
                log.debug("Bridge OpenAI %s: %s", model, e)

    # ── 1. Together AI ─────────────────────────────────────────────────────────
    if _together() and _cb_ok_shared("Together"):
        for model in _TOGETHER_MODELS:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(
                        "https://api.together.xyz/v1/chat/completions",
                        headers={"Authorization": f"Bearer {_together()}", "Content-Type": "application/json"},
                        json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
                            if text:
                                log.info("Bridge: Together AI OK model=%s", model)
                                return text
                        elif r.status in (401, 402, 429):
                            _cb_fail("Together", 300)
                            break
            except Exception as e:
                log.debug("Bridge Together %s: %s", model, e)

    # ── 2. Fireworks AI ────────────────────────────────────────────────────────
    if _fireworks() and _cb_ok_shared("Fireworks"):
        for model in _FIREWORKS_MODELS:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(
                        "https://api.fireworks.ai/inference/v1/chat/completions",
                        headers={"Authorization": f"Bearer {_fireworks()}", "Content-Type": "application/json"},
                        json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
                            if text:
                                log.info("Bridge: Fireworks OK model=%s", model)
                                return text
                        elif r.status in (401, 402, 429):
                            _cb_fail("Fireworks", 300)
                            break
            except Exception as e:
                log.debug("Bridge Fireworks %s: %s", model, e)

    # ── 3. Google Gemini ───────────────────────────────────────────────────────
    if _gemini() and _cb_ok_shared("Gemini"):
        for model in _GEMINI_MODELS:
            try:
                # Konvertiere OpenAI-Format → Gemini-Format
                user_text = ""
                for m in messages:
                    if m.get("role") == "user":
                        user_text = m.get("content", "")
                sys_text = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
                if sys_text:
                    user_text = f"{sys_text}\n\n{user_text}"

                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={_gemini()}",
                        json={
                            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
                            "generationConfig": {"maxOutputTokens": max_tokens},
                        },
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = ""
                            for cand in d.get("candidates", []):
                                for part in cand.get("content", {}).get("parts", []):
                                    text += part.get("text", "")
                            if text:
                                log.info("Bridge: Gemini OK model=%s", model)
                                return text
                        elif r.status in (429, 503):
                            _cb_fail("Gemini", 60)
                            break
                        elif r.status in (401, 403):
                            _cb_fail("Gemini", 3600)
                            break
            except Exception as e:
                log.debug("Bridge Gemini %s: %s", model, e)

    # ── 4. Cohere ──────────────────────────────────────────────────────────────
    if _cohere() and _cb_ok_shared("Cohere"):
        for model in _COHERE_MODELS:
            try:
                user_msgs = [m for m in messages if m.get("role") == "user"]
                prompt = user_msgs[-1].get("content", "") if user_msgs else ""
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(
                        "https://api.cohere.com/v1/chat",
                        headers={"Authorization": f"Bearer {_cohere()}", "Content-Type": "application/json"},
                        json={"model": model, "message": prompt, "max_tokens": max_tokens},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = d.get("text", "")
                            if text:
                                log.info("Bridge: Cohere OK model=%s", model)
                                return text
                        elif r.status in (401, 429):
                            _cb_fail("Cohere", 300)
                            break
            except Exception as e:
                log.debug("Bridge Cohere %s: %s", model, e)

    # ── 5. AI21 Labs ───────────────────────────────────────────────────────────
    if _ai21() and _cb_ok_shared("AI21"):
        for model in _AI21_MODELS:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(
                        "https://api.ai21.com/studio/v1/chat/completions",
                        headers={"Authorization": f"Bearer {_ai21()}", "Content-Type": "application/json"},
                        json={"model": model, "messages": messages, "max_tokens": max_tokens},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
                            if text:
                                log.info("Bridge: AI21 OK model=%s", model)
                                return text
                        elif r.status in (401, 429):
                            _cb_fail("AI21", 300)
                            break
            except Exception as e:
                log.debug("Bridge AI21 %s: %s", model, e)

    # ── 6. Lepton AI ───────────────────────────────────────────────────────────
    if _lepton() and _cb_ok_shared("Lepton"):
        for model in _LEPTON_MODELS:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(
                        f"https://{model}.lepton.run/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {_lepton()}", "Content-Type": "application/json"},
                        json={"model": model, "messages": messages, "max_tokens": max_tokens},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
                            if text:
                                log.info("Bridge: Lepton OK model=%s", model)
                                return text
            except Exception as e:
                log.debug("Bridge Lepton %s: %s", model, e)

    # ── 7. Cloudflare Workers AI (Key nötig, aber kostenlos bis 10k req/Tag) ──
    if _cf_token() and _cf_account() and _cb_ok_shared("Cloudflare"):
        try:
            user_msgs = [m for m in messages if m.get("role") == "user"]
            prompt = user_msgs[-1].get("content", "") if user_msgs else ""
            url = _CLOUDFLARE_BASE.format(_cf_account()) + "/" + _CF_MODEL
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                async with s.post(
                    url,
                    headers={"Authorization": f"Bearer {_cf_token()}", "Content-Type": "application/json"},
                    json={"messages": messages},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        text = d.get("result", {}).get("response", "")
                        if text:
                            log.info("Bridge: Cloudflare Workers AI OK")
                            return text
        except Exception as e:
            log.debug("Bridge Cloudflare: %s", e)

    # ── 8. Pollinations.ai — KEIN KEY, absoluter Notfall ──────────────────────
    if _cb_ok("Pollinations"):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(
                    _POLLINATIONS_URL,
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": "openai",
                        "messages": messages,
                        "max_tokens": min(max_tokens, 500),
                        "private": True,
                    },
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        text = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
                        if text:
                            log.info("Bridge: Pollinations.ai (no-auth) OK")
                            return text
                    elif r.status == 429:
                        _cb_fail("Pollinations", 60)
        except Exception as e:
            log.debug("Bridge Pollinations: %s", e)
            _cb_fail("Pollinations", 30)

    return ""


def get_bridge_status() -> dict:
    """Zeigt welche Bridge-Provider verfügbar sind (Keys vorhanden)."""
    providers = {
        "OpenAI":      bool(_openai()),
        "Together":    bool(_together()),
        "Fireworks":   bool(_fireworks()),
        "Gemini":      bool(_gemini()),
        "Cohere":      bool(_cohere()),
        "AI21":        bool(_ai21()),
        "Lepton":      bool(_lepton()),
        "Cloudflare":  bool(_cf_token() and _cf_account()),
        "Pollinations": True,  # kein Key nötig
    }
    active = [p for p, ok in providers.items() if ok]
    blocked = [p for p, v in _LOCAL_CB.items() if v.get("until", 0) > time.time()]
    return {
        "available": active,
        "blocked_until": blocked,
        "total_active": len(active),
        "no_auth_fallback": "Pollinations.ai",
    }
