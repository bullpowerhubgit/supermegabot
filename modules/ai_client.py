#!/usr/bin/env python3
"""
Zentraler AI-Client — OpenClaw(Ollama) → Anthropic → OpenAI → Groq → OpenRouter → Gemini → Perplexity → Fallback.
Einheitlicher Zugang für alle Module: from modules.ai_client import ai_complete
OpenClaw (lokales Ollama) ist IMMER der erste Provider — kostenlos, kein Rate-Limit!
"""
from __future__ import annotations
import logging
import os

log = logging.getLogger("AIClient")

_ANTHROPIC  = lambda: os.getenv("ANTHROPIC_API_KEY", "")
_OPENAI     = lambda: os.getenv("OPENAI_API_KEY", "")
_GROQ       = lambda: os.getenv("GROQ_API_KEY", "")
_OPENROUTER = lambda: os.getenv("OPENROUTER_API_KEY", "")
_PERPLEXITY = lambda: os.getenv("PERPLEXITY_API_KEY", "")
_GEMINI     = lambda: os.getenv("GEMINI_API_KEY", "") or os.getenv("GCP_API_KEY", "")

_OPENROUTER_MODEL   = "google/gemma-4-26b-a4b-it:free"   # verified working 2026-07-14
_GROQ_MODEL         = "llama-3.1-8b-instant"
_OPENROUTER_REFERER = "https://supermegabot-production.up.railway.app"
_GEMINI_URLS        = [
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-8b:generateContent",
]
_OLLAMA_BASE        = lambda: os.getenv("OLLAMA_BASE", "http://localhost:11434")
_OLLAMA_MODEL       = lambda: os.getenv("OLLAMA_CLAW_MODEL", "llama3.2:latest")
_OLLAMA_FAST        = lambda: os.getenv("OLLAMA_FAST_MODEL", "llama3.2:latest")
_OLLAMA_FIRST       = os.getenv("OLLAMA_FIRST", "true").lower() != "false"
_OLLAMA_TIMEOUT     = int(os.getenv("OLLAMA_TIMEOUT", "5"))  # short timeout so cloud fallback is fast


def _enabled(name: str) -> bool:
    return os.getenv(f"{name}_ENABLED", "true").lower() not in ("false", "0", "off")


async def ai_complete(prompt: str, system: str = "", model_hint: str = "fast", max_tokens: int = 1200) -> str:
    """Full fallback chain: OpenClaw(Ollama) → Anthropic → OpenAI → OpenRouter → Groq → Gemini → Perplexity → empty."""
    import aiohttp

    messages = [{"role": "user", "content": f"{system}\n\n{prompt}" if system else prompt}]

    # 0. OpenClaw — lokales Ollama, kostenlos (kurzer Timeout damit Cloud-Fallback schnell greift)
    if _OLLAMA_FIRST:
        chosen = _OLLAMA_FAST() if model_hint == "fast" else _OLLAMA_MODEL()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=_OLLAMA_TIMEOUT)) as s:
                msg_list = []
                if system:
                    msg_list.append({"role": "system", "content": system})
                msg_list.append({"role": "user", "content": prompt})
                async with s.post(
                    f"{_OLLAMA_BASE()}/api/chat",
                    json={"model": chosen, "messages": msg_list,
                          "stream": False, "options": {"num_predict": max_tokens}},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        text = d.get("message", {}).get("content", "")
                        if text:
                            log.info("OpenClaw OK model=%s", chosen)
                            return text
                    log.debug("OpenClaw %s — falling to cloud", r.status)
        except Exception as e:
            log.debug("OpenClaw offline: %s — using cloud fallback", e)

    primary = os.getenv("AI_PROVIDER_PRIMARY", "").lower()

    # 1. Anthropic (skip on 529 = no credits, 401 = invalid)
    if _ANTHROPIC() and _enabled("ANTHROPIC") and primary not in ("openai", "groq", "gemini"):
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

    # 1b. OpenRouter — PRIORITY FALLBACK (when Anthropic/OpenAI have no credits)
    if _OPENROUTER():
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
                async with s.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_OPENROUTER()}", "Content-Type": "application/json",
                             "HTTP-Referer": _OPENROUTER_REFERER},
                    json={"model": _OPENROUTER_MODEL, "max_tokens": max_tokens, "messages": messages},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        content = d.get("choices", [{}])[0].get("message", {}).get("content")
                        if content:
                            log.debug("OpenRouter OK model=%s", _OPENROUTER_MODEL)
                            return content
                    log.debug("OpenRouter %s", r.status)
        except Exception as e:
            log.debug("OpenRouter error: %s", e)

    # 2. OpenAI (primary when AI_PROVIDER_PRIMARY=openai)
    if _OPENAI() and primary in ("", "openai"):
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

    # 3. Groq (free tier: llama-3.1-8b-instant — set GROQ_API_KEY from console.groq.com)
    if _GROQ():
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                async with s.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_GROQ()}", "Content-Type": "application/json"},
                    json={"model": _GROQ_MODEL, "max_tokens": max_tokens, "messages": messages},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        text = d["choices"][0]["message"]["content"]
                        if text:
                            return text
                    if r.status in (401, 403):
                        log.debug("Groq skip (%s) — invalid key", r.status)
                    else:
                        log.debug("Groq %s", r.status)
        except Exception as e:
            log.debug("Groq error: %s", e)

    # 4. Gemini (try 3 free models — 2.0-flash-lite → 1.5-flash → 1.5-flash-8b)
    if _GEMINI():
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        for gemini_url in _GEMINI_URLS:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                    async with s.post(
                        f"{gemini_url}?key={_GEMINI()}",
                        headers={"Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": full_prompt}]}],
                              "generationConfig": {"maxOutputTokens": max_tokens}},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = d.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            if text:
                                model_name = gemini_url.split("models/")[1].split(":")[0]
                                log.debug("Gemini OK via %s", model_name)
                                return text
                        if r.status in (400, 401, 403):
                            log.debug("Gemini skip (%s) — invalid key", r.status)
                            break  # key invalid, don't try other models
                        log.debug("Gemini %s on %s — try next model", r.status, gemini_url.split("models/")[1].split(":")[0])
            except Exception as e:
                log.debug("Gemini error: %s", e)
                break

    # 5. OpenRouter (free models available — any valid API key)
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

    # 6. Perplexity (min 16 tokens required by API)
    if _PERPLEXITY() and _enabled("PERPLEXITY"):
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

    # Local Ollama fallback (works when running locally or when OLLAMA_BASE is set)
    _ollama_base = os.getenv("OLLAMA_BASE", "http://localhost:11434")
    _ollama_model = os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2:latest")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
            async with s.post(
                f"{_ollama_base}/api/chat",
                json={"model": _ollama_model, "messages": messages, "stream": False},
            ) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    text = d.get("message", {}).get("content", "")
                    if text:
                        log.debug("Ollama OK: %d chars", len(text))
                        return text
    except Exception as e:
        log.debug("Ollama skip: %s", e)

    log.warning("ai_complete: all providers failed")
    return ""
