#!/usr/bin/env python3
"""
Zentraler AI-Client — Anthropic → OpenAI → OpenRouter → DeepSeek → Perplexity → Fallback.
Einheitlicher Zugang für alle Module: from modules.ai_client import ai_complete
"""
from __future__ import annotations
import logging
import os

log = logging.getLogger("AIClient")

_ANTHROPIC  = lambda: os.getenv("ANTHROPIC_API_KEY", "")
_OPENAI     = lambda: os.getenv("OPENAI_API_KEY", "")
_OPENROUTER = lambda: os.getenv("OPENROUTER_API_KEY", "")
_PERPLEXITY = lambda: os.getenv("PERPLEXITY_API_KEY", "")
_GEMINI     = lambda: os.getenv("GCP_API_KEY", "")

_OPENROUTER_MODEL   = "liquid/lfm-2.5-1.2b-instruct:free"  # confirmed working free model 2026-06
_OPENROUTER_REFERER = "https://dudirudibot-mega-production.up.railway.app"
_GEMINI_URL         = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


async def ai_complete(prompt: str, system: str = "", model_hint: str = "fast", max_tokens: int = 1200) -> str:
    """Full fallback chain: Anthropic → OpenAI → OpenRouter → DeepSeek → Perplexity → empty."""
    import aiohttp

    messages = [{"role": "user", "content": f"{system}\n\n{prompt}" if system else prompt}]

    # 1. Anthropic (skip on 529 = no credits, 401 = invalid)
    if _ANTHROPIC():
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": _ANTHROPIC(), "anthropic-version": "2023-06-01",
                             "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": max_tokens,
                          "messages": messages},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        return d["content"][0]["text"]
                    if r.status in (400, 401, 402, 429, 529):
                        log.debug("Anthropic skip (%s) — trying next provider", r.status)
                    else:
                        log.debug("Anthropic %s", r.status)
        except Exception as e:
            log.debug("Anthropic error: %s", e)

    # 2. OpenAI
    if _OPENAI():
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_OPENAI()}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini", "max_tokens": max_tokens,
                          "messages": ([{"role": "system", "content": system}] + [{"role": "user", "content": prompt}]) if system else messages},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        return d["choices"][0]["message"]["content"]
                    if r.status in (401, 403):
                        log.debug("OpenAI skip (%s) — invalid key", r.status)
                    else:
                        log.debug("OpenAI %s", r.status)
        except Exception as e:
            log.debug("OpenAI error: %s", e)

    # 3. Gemini 1.5 Flash (GCP API Key — kostenlos bis 1500 req/Tag)
    if _GEMINI():
        try:
            full_prompt = f"{system}\n\n{prompt}" if system else prompt
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(
                    f"{_GEMINI_URL}?key={_GEMINI()}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": full_prompt}]}],
                          "generationConfig": {"maxOutputTokens": max_tokens}},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        text = d.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text:
                            return text
                    if r.status in (400, 401, 403):
                        log.debug("Gemini skip (%s)", r.status)
                    else:
                        log.debug("Gemini %s", r.status)
        except Exception as e:
            log.debug("Gemini error: %s", e)

    # 4. OpenRouter (free models available)
    if _OPENROUTER():
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_OPENROUTER()}",
                             "HTTP-Referer": _OPENROUTER_REFERER,
                             "Content-Type": "application/json"},
                    json={"model": _OPENROUTER_MODEL, "max_tokens": max_tokens, "messages": messages},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        text = d["choices"][0]["message"]["content"]
                        if text:
                            return text
                    log.debug("OpenRouter %s", r.status)
        except Exception as e:
            log.debug("OpenRouter error: %s", e)

    # 4. Perplexity (min 16 tokens required by API)
    if _PERPLEXITY():
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                async with s.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={"Authorization": f"Bearer {_PERPLEXITY()}", "Content-Type": "application/json"},
                    json={"model": "sonar", "max_tokens": max(max_tokens, 16), "messages": messages},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        return d["choices"][0]["message"]["content"]
                    log.debug("Perplexity %s", r.status)
        except Exception as e:
            log.debug("Perplexity error: %s", e)

    log.warning("ai_complete: all providers failed")
    return ""
