#!/usr/bin/env python3
"""
Anthropic SDK Drop-in Shim — routet alle Calls durch ai_client.py
==================================================================
Statt `from anthropic import Anthropic` → `from modules.anthropic_compat import Anthropic`

Vorteil: Groq → DeepSeek → OpenRouter → Gemini → Anthropic → Ollama Fallback-Kette
         automatisch aktiv — kein API-Ausfall bricht mehr den Code.

Unterstützte SDK-API:
  client.messages.create(model, max_tokens, messages, system=...)
  await async_client.messages.create(...)
  content[0].text  (Antwort-Objekt)
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, List, Optional

log = logging.getLogger("anthropic_compat")


# ── Antwort-Objekte (kompatibel mit Anthropic SDK) ────────────────────────────

@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Message:
    content: List[TextBlock]
    model: str = ""
    role: str = "assistant"
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)
    id: str = "msg_compat"
    type: str = "message"


# ── Internes Helper ────────────────────────────────────────────────────────────

def _extract_system(messages: list, system: str = "") -> tuple[str, list]:
    """Extrahiert system-Message aus messages-Liste (Anthropic-Format)."""
    sys_text = system
    user_msgs = []
    for m in messages:
        if m.get("role") == "system":
            sys_text = sys_text or m.get("content", "")
        else:
            user_msgs.append(m)
    return sys_text, user_msgs or messages


def _last_user_prompt(messages: list) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content", "")
            if isinstance(c, list):
                return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
            return str(c)
    return ""


# ── Synchroner Client ──────────────────────────────────────────────────────────

class _Messages:
    def create(
        self,
        model: str = "",
        max_tokens: int = 1024,
        messages: Optional[list] = None,
        system: str = "",
        **kwargs: Any,
    ) -> Message:
        from modules.ai_client import ai_complete_sync
        msgs = messages or []
        sys_text, user_msgs = _extract_system(msgs, system)
        prompt = _last_user_prompt(user_msgs)
        text = ai_complete_sync(prompt, system=sys_text, max_tokens=max_tokens)
        log.debug("anthropic_compat (sync): %d chars", len(text))
        return Message(content=[TextBlock(text=text)], model=model or "compat")


class Anthropic:
    """Drop-in Ersatz für anthropic.Anthropic() — routet durch ai_client.py."""

    def __init__(self, api_key: str = "", **kwargs: Any):
        self.messages = _Messages()
        if not api_key and not os.getenv("ANTHROPIC_API_KEY"):
            log.debug("anthropic_compat: kein API-Key — Fallback-Kette aktiv")


# ── Asynchroner Client ─────────────────────────────────────────────────────────

class _AsyncMessages:
    async def create(
        self,
        model: str = "",
        max_tokens: int = 1024,
        messages: Optional[list] = None,
        system: str = "",
        **kwargs: Any,
    ) -> Message:
        from modules.ai_client import ai_complete
        msgs = messages or []
        sys_text, user_msgs = _extract_system(msgs, system)
        prompt = _last_user_prompt(user_msgs)
        text = await ai_complete(prompt, system=sys_text, max_tokens=max_tokens)
        log.debug("anthropic_compat (async): %d chars", len(text))
        return Message(content=[TextBlock(text=text)], model=model or "compat")


class AsyncAnthropic:
    """Drop-in Ersatz für anthropic.AsyncAnthropic() — routet durch ai_client.py."""

    def __init__(self, api_key: str = "", **kwargs: Any):
        self.messages = _AsyncMessages()


# ── Convenience — direkte Import-Kompatibilität ────────────────────────────────

def create_client(async_mode: bool = False):
    """Erstellt sync oder async Client."""
    return AsyncAnthropic() if async_mode else Anthropic()


async def ai_ask(prompt: str, system: str = "", max_tokens: int = 1024) -> str:
    """Direkter async Helper — kein Client nötig."""
    from modules.ai_client import ai_complete
    return await ai_complete(prompt, system=system, max_tokens=max_tokens)


def ai_ask_sync(prompt: str, system: str = "", max_tokens: int = 1024) -> str:
    """Direkter sync Helper — kein Client nötig."""
    from modules.ai_client import ai_complete_sync
    return ai_complete_sync(prompt, system=system, max_tokens=max_tokens)


# ── Exception-Stubs (kompatibel mit anthropic SDK) ────────────────────────────

class APIError(Exception):
    status_code: int = 0
    message: str = ""


class RateLimitError(APIError):
    status_code = 429


class APIStatusError(APIError):
    def __init__(self, message: str = "", *, status_code: int = 500, **kwargs):
        super().__init__(message)
        self.status_code = status_code


class APIConnectionError(APIError):
    pass


class AuthenticationError(APIError):
    status_code = 401


# Stream-Stub (compat, falls Streaming verwendet wird)
class _StreamManager:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def text_stream(self):
        return iter([])

    def get_final_message(self) -> Message:
        return Message(content=[TextBlock(text="")])
