#!/usr/bin/env python3
"""
Zentraler AI-Client — Anthropic → OpenAI → DeepSeek → Groq → Fallback.
Einheitlicher Zugang für alle Module: from modules.ai_client import ai_complete
"""
from __future__ import annotations
import logging
import os

log = logging.getLogger("AIClient")

_ANTHROPIC  = lambda: os.getenv("ANTHROPIC_API_KEY", "")
_OPENAI     = lambda: os.getenv("OPENAI_API_KEY", "")
_DEEPSEEK   = lambda: os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
_GROQ       = lambda: os.getenv("GROQ_API_KEY", "")
_PERPLEXITY = lambda: os.getenv("PERPLEXITY_API_KEY", "")

_GROQ_MODELS = {"fast": "llama-3.1-8b-instant", "smart": "llama-3.3-70b-versatile", "default": "llama-3.1-8b-instant"}


async def ai_complete(prompt: str, system: str = "", model_hint: str = "fast", max_tokens: int = 1200) -> str:
    """Full fallback chain: Anthropic → OpenAI → DeepSeek → Groq → Perplexity → empty."""
    import aiohttp

    messages = [{"role": "user", "content": f"{system}\n\n{prompt}" if system else prompt}]

    # 1. Anthropic
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
                          "messages": [{"role": "system", "content": system}] + [{"role": "user", "content": prompt}] if system else messages},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        return d["choices"][0]["message"]["content"]
                    log.debug("OpenAI %s", r.status)
        except Exception as e:
            log.debug("OpenAI error: %s", e)

    # 3. DeepSeek
    ds_key = os.getenv("DEEPSEEK_API_KEY", "")
    if ds_key:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {ds_key}", "Content-Type": "application/json"},
                    json={"model": "deepseek-chat", "max_tokens": max_tokens, "messages": messages},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        return d["choices"][0]["message"]["content"]
                    log.debug("DeepSeek %s", r.status)
        except Exception as e:
            log.debug("DeepSeek error: %s", e)

    # 4. Groq (free)
    if _GROQ():
        try:
            model = _GROQ_MODELS.get(model_hint, _GROQ_MODELS["default"])
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                async with s.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_GROQ()}", "Content-Type": "application/json"},
                    json={"model": model, "max_tokens": max_tokens, "messages": messages},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        return d["choices"][0]["message"]["content"]
                    log.debug("Groq %s", r.status)
        except Exception as e:
            log.debug("Groq error: %s", e)

    # 5. Perplexity
    if _PERPLEXITY():
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                async with s.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={"Authorization": f"Bearer {_PERPLEXITY()}", "Content-Type": "application/json"},
                    json={"model": "sonar", "max_tokens": max_tokens, "messages": messages},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        return d["choices"][0]["message"]["content"]
                    log.debug("Perplexity %s", r.status)
        except Exception as e:
            log.debug("Perplexity error: %s", e)

    log.warning("ai_complete: all providers failed")
    return ""
