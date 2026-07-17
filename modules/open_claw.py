#!/usr/bin/env python3
"""
OpenClaw — Lokales KI-System via Ollama.
Primäre kostenlose AI für alle Module: from modules.open_claw import claw_complete, CLAW

Nutzung:
    from modules.open_claw import claw_complete, ai_or_claw

    # Lokal (kein Internet, kein Rate-Limit)
    text = await claw_complete("Schreibe einen Post über KI")

    # Lokal zuerst → Cloud-Fallback automatisch
    text = await ai_or_claw("Analysiere diese Daten")

Performance:
    - Globaler Connection-Pool (kein TCP-Handshake pro Request)
    - Response-Cache (LRU, 256 Einträge, 10 min TTL)
    - Modell warm halten (keep_alive=300s)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from typing import Any

import aiohttp

log = logging.getLogger("OpenClaw")

OLLAMA_BASE  = os.getenv("OLLAMA_BASE",         "http://localhost:11434")
CLAW_MODEL   = os.getenv("OLLAMA_CLAW_MODEL",   "llama3.2:latest")
FAST_MODEL   = os.getenv("OLLAMA_FAST_MODEL",   "llama3.2:latest")
SMART_MODEL  = os.getenv("OLLAMA_SMART_MODEL",  "llama3.2:latest")

_THINKING_MODELS = {"qwen3", "qwen3.6", "qwen3:"}

# ── Response-Cache (prompt-hash → (timestamp, text)) ─────────────────────────
_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL  = int(os.getenv("CLAW_CACHE_TTL",  "600"))   # 10 Minuten
_CACHE_SIZE = int(os.getenv("CLAW_CACHE_SIZE",  "256"))
_CACHE_ENABLED = os.getenv("CLAW_CACHE", "true").lower() != "false"

# ── Shared aiohttp-Session — nutzt globalen Connection-Pool wenn verfügbar ────
_session: aiohttp.ClientSession | None = None
_session_lock = asyncio.Lock()


async def _get_session() -> aiohttp.ClientSession:
    try:
        from modules.connection_pool import get_session
        return await get_session(timeout=float(os.getenv("OLLAMA_TIMEOUT", "120")))
    except ImportError:
        pass

    global _session
    if _session and not _session.closed:
        return _session
    async with _session_lock:
        if _session and not _session.closed:
            return _session
        connector = aiohttp.TCPConnector(
            limit=50, limit_per_host=10, keepalive_timeout=60,
            enable_cleanup_closed=True,
        )
        _session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=120),
        )
    return _session


async def close_session() -> None:
    global _session
    try:
        from modules.connection_pool import close_pool
        await close_pool()
    except ImportError:
        pass
    if _session and not _session.closed:
        await _session.close()
    _session = None


def _cache_key(prompt: str, system: str, model: str) -> str:
    return hashlib.md5(f"{model}|{system}|{prompt}".encode()).hexdigest()


def _cache_get(key: str) -> str | None:
    if not _CACHE_ENABLED:
        return None
    entry = _CACHE.get(key)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    _CACHE.pop(key, None)
    return None


def _cache_set(key: str, value: str) -> None:
    if not _CACHE_ENABLED or not value:
        return
    if len(_CACHE) >= _CACHE_SIZE:
        oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
        _CACHE.pop(oldest, None)
    _CACHE[key] = (time.time(), value)


# ── Core: claw_complete ───────────────────────────────────────────────────────

async def claw_complete(
    prompt: str,
    system: str = "",
    fast: bool = False,
    model: str | None = None,
    max_tokens: int = 1500,
    use_cache: bool = True,
) -> str:
    """
    Lokale Ollama-Completion. Gibt leeren String zurück wenn Ollama offline.
    Cache: identische Prompts werden 10 Minuten gecacht.
    """
    chosen = model or (FAST_MODEL if fast else CLAW_MODEL)
    ck = _cache_key(prompt[:200], system[:100], chosen)
    if use_cache:
        cached = _cache_get(ck)
        if cached:
            log.debug("OpenClaw cache-hit model=%s", chosen)
            return cached

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    is_thinking  = any(t in chosen for t in _THINKING_MODELS)
    actual_tokens= (max_tokens + 2000) if is_thinking else max_tokens
    actual_to    = 180 if is_thinking else 120

    try:
        s = await _get_session()
        async with s.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": chosen, "messages": messages, "stream": False,
                "keep_alive": 300,   # Modell 5 min warm halten
                "options": {"num_predict": actual_tokens},
            },
            timeout=aiohttp.ClientTimeout(total=actual_to),
            ssl=False,
        ) as r:
            if r.status == 200:
                d = await r.json(content_type=None)
                msg  = d.get("message", {})
                text = msg.get("content", "")
                if not text and msg.get("thinking"):
                    text = msg["thinking"][:500]
                log.info("OpenClaw OK model=%s chars=%d", chosen, len(text))
                _cache_set(ck, text)
                return text
            body = await r.text()
            log.warning("OpenClaw %s: %s", r.status, body[:120])
    except Exception as e:
        log.debug("OpenClaw offline: %s", e)
    return ""


async def ai_or_claw(
    prompt: str,
    system: str = "",
    fast: bool = False,
    max_tokens: int = 1200,
) -> str:
    """
    Lokal zuerst (OpenClaw), dann Cloud-Fallback (ai_client.ai_complete).
    Für Module die IMMER eine Antwort brauchen.
    """
    text = await claw_complete(prompt, system=system, fast=fast, max_tokens=max_tokens)
    if text:
        return text
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, system=system, max_tokens=max_tokens)
    except Exception as e:
        log.debug("ai_or_claw fallback: %s", e)
    return ""


# ── Convenience-Funktionen ────────────────────────────────────────────────────

async def get_models() -> list[dict]:
    try:
        s = await _get_session()
        async with s.get(f"{OLLAMA_BASE}/api/tags",
                         timeout=aiohttp.ClientTimeout(total=5), ssl=False) as r:
            if r.status == 200:
                d = await r.json(content_type=None)
                return [{"name": m["name"],
                         "size_gb": round(m.get("size", 0) / 1024**3, 1)}
                        for m in d.get("models", [])]
    except Exception:
        pass
    return []


async def is_online() -> bool:
    try:
        s = await _get_session()
        async with s.get(f"{OLLAMA_BASE}/",
                         timeout=aiohttp.ClientTimeout(total=3), ssl=False) as r:
            return r.status == 200
    except Exception:
        return False


async def claw_generate_content(topic: str, content_type: str = "post") -> dict:
    system = "Du bist ein KI-Marketing-Experte. Erstelle verkaufsstarken deutschen Content."
    prompts = {
        "post":     f"Erstelle einen kurzen viralen Social-Media-Post (max 150 Wörter) über: {topic}. Mit Call-to-Action.",
        "email":    f"Erstelle eine Verkaufs-E-Mail Betreff + Body (max 200 Wörter) für: {topic}.",
        "seo":      f"Erstelle SEO-optimierten Produkttitel + Beschreibung (150 Wörter) für: {topic}.",
        "telegram": f"Erstelle eine Telegram-Nachricht (max 100 Wörter) mit Emojis für: {topic}.",
        "blog":     f"Erstelle einen Blog-Artikel (300 Wörter) mit H2-Überschriften über: {topic}.",
    }
    prompt = prompts.get(content_type, prompts["post"])
    text = await claw_complete(prompt, system=system, fast=(content_type == "post"))
    return {
        "ok":          bool(text),
        "content_type": content_type,
        "topic":       topic,
        "text":        text,
        "model":       FAST_MODEL if content_type == "post" else CLAW_MODEL,
        "source":      "OpenClaw-Local",
    }


async def claw_analyze_product(product_title: str, current_description: str = "") -> dict:
    system = "Du bist ein E-Commerce-Experte. Optimiere Produkte für maximale Konversion."
    prompt = f"""Produkt: {product_title}
Aktuelle Beschreibung: {current_description[:200] if current_description else 'keine'}

Erstelle:
1. SEO-Titel (max 70 Zeichen)
2. Meta-Description (max 155 Zeichen)
3. Verkaufs-Description (100 Wörter, HTML mit <strong> und Bulletpoints)
4. 5 Tags (kommasepariert)"""
    text = await claw_complete(prompt, system=system)
    return {"ok": bool(text), "analysis": text, "product": product_title}


async def claw_revenue_strategy() -> str:
    system = "Du bist ein Revenue-Stratege für digitale Produkte. Sei konkret und handlungsorientiert."
    prompt = """Erstelle eine Tages-Revenue-Strategie für:
- Shopify Store (Dropshipping + Print-on-Demand)
- Digistore24 Affiliate
- Telegram Bot Subscription

Fokus: Schnelle Einnahmen in 24h. Konkrete Schritte, keine Theorie."""
    return await claw_complete(prompt, system=system)


async def claw_self_improve(module_name: str, error_log: str = "") -> str:
    system = "Du bist ein Python-Senior-Entwickler. Analysiere und verbessere Code-Module."
    prompt = f"""Modul: {module_name}
Fehler-Log: {error_log[:500] if error_log else 'keine Fehler'}

Schlage 3 konkrete Verbesserungen vor."""
    return await claw_complete(prompt, system=system, fast=True)


def cache_stats() -> dict:
    now = time.time()
    valid = sum(1 for ts, _ in _CACHE.values() if now - ts < _CACHE_TTL)
    return {"entries": len(_CACHE), "valid": valid, "ttl": _CACHE_TTL,
            "enabled": _CACHE_ENABLED}


# ── Sync-Wrapper ──────────────────────────────────────────────────────────────

class OpenClaw:
    """Sync-Wrapper für non-async Kontexte."""

    def __init__(self) -> None:
        self.base          = OLLAMA_BASE
        self.default_model = CLAW_MODEL

    def complete(self, prompt: str, system: str = "", fast: bool = False) -> str:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, claw_complete(prompt, system, fast)).result(120)
            return loop.run_until_complete(claw_complete(prompt, system, fast))
        except Exception as e:
            log.debug("OpenClaw sync: %s", e)
            return ""

    def generate(self, topic: str, content_type: str = "post") -> dict:
        try:
            return asyncio.run(claw_generate_content(topic, content_type))
        except Exception as e:
            return {"ok": False, "error": str(e)}


CLAW = OpenClaw()
