#!/usr/bin/env python3
"""
Ollama Manager — Lokales KI-Model-Management
============================================
Zentrale Schnittstelle für:
- Model-Verwaltung (pull, delete, list, info)
- Streaming-Chat (Server-Sent Events)
- Generate-Endpoint
- Status + Health

Nutzung:
    from modules.ollama_manager import OllamaManager
    mgr = OllamaManager()
    text = await mgr.chat("Erkläre mir den Shopify-Umsatz")
    async for chunk in mgr.stream("Schreibe einen Post über KI"):
        print(chunk, end="", flush=True)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import AsyncGenerator

import aiohttp

log = logging.getLogger("OllamaManager")

OLLAMA_BASE    = os.getenv("OLLAMA_BASE", "http://localhost:11434")
DEFAULT_MODEL  = os.getenv("OLLAMA_CLAW_MODEL", "llama3.2:latest")
FAST_MODEL     = os.getenv("OLLAMA_FAST_MODEL",  "llama3.2:latest")
TIMEOUT_CHAT   = int(os.getenv("OLLAMA_TIMEOUT_CHAT",   "120"))
TIMEOUT_PULL   = int(os.getenv("OLLAMA_TIMEOUT_PULL",  "1800"))

# Empfohlene Modelle (werden beim ersten Pull-Aufruf angeboten)
RECOMMENDED_MODELS = {
    "llama3.2:latest":        {"size": "1.9 GB", "use": "Allgemein, schnell"},
    "llama3.2:3b":            {"size": "2.0 GB", "use": "Allgemein, Deutsch"},
    "mistral:latest":         {"size": "4.1 GB", "use": "Business-Analyse, Strategie"},
    "codellama:7b":           {"size": "3.8 GB", "use": "Code-Review, Bugfixing"},
    "gemma2:2b":              {"size": "1.6 GB", "use": "Leicht, schnell"},
    "phi3:mini":              {"size": "2.2 GB", "use": "Effizient, Microsoft"},
    "qwen2.5:3b":             {"size": "1.9 GB", "use": "Chinesisch/DE, gut"},
    "nomic-embed-text":       {"size": "0.3 GB", "use": "Embeddings für Supabase"},
}


class OllamaManager:
    """Vollständige Ollama-Schnittstelle."""

    def __init__(self) -> None:
        self.base = OLLAMA_BASE
        self._model_cache: list[dict] = []
        self._cache_ts: float = 0

    # ── Health & Status ───────────────────────────────────────────────────────

    async def is_online(self) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as s:
                async with s.get(f"{self.base}/") as r:
                    return r.status == 200
        except Exception:
            return False

    async def status(self) -> dict:
        """Detaillierter Status: online, Modelle, Speicher."""
        online = await self.is_online()
        if not online:
            return {"online": False, "models": [], "default_model": DEFAULT_MODEL, "base": self.base}

        models = await self.list_models()
        running = await self._running_models()
        return {
            "online": True,
            "base": self.base,
            "default_model": DEFAULT_MODEL,
            "fast_model": FAST_MODEL,
            "models": models,
            "running": running,
            "model_count": len(models),
            "recommended": RECOMMENDED_MODELS,
        }

    async def _running_models(self) -> list[dict]:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
                async with s.get(f"{self.base}/api/ps") as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        return d.get("models", [])
        except Exception:
            pass
        return []

    # ── Model-Verwaltung ──────────────────────────────────────────────────────

    async def list_models(self, force_refresh: bool = False) -> list[dict]:
        """Liste aller installierten Modelle mit Details."""
        if not force_refresh and self._model_cache and time.time() - self._cache_ts < 30:
            return self._model_cache
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
                async with s.get(f"{self.base}/api/tags") as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        models = []
                        for m in d.get("models", []):
                            size_gb = round(m.get("size", 0) / 1024**3, 2)
                            rec = RECOMMENDED_MODELS.get(m["name"], {})
                            models.append({
                                "name": m["name"],
                                "size_gb": size_gb,
                                "size_str": f"{size_gb:.1f} GB",
                                "modified": m.get("modified_at", "")[:10],
                                "use": rec.get("use", ""),
                                "is_default": m["name"] == DEFAULT_MODEL,
                                "is_fast": m["name"] == FAST_MODEL,
                            })
                        self._model_cache = sorted(models, key=lambda x: x["name"])
                        self._cache_ts = time.time()
                        return self._model_cache
        except Exception as e:
            log.warning("Ollama list_models: %s", e)
        return []

    async def pull(self, model: str) -> AsyncGenerator[str, None]:
        """Pull-Modell mit Fortschritts-Stream (yields JSON-Zeilen)."""
        log.info("Ollama pull: %s", model)
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_PULL)
            ) as s:
                async with s.post(
                    f"{self.base}/api/pull",
                    json={"name": model, "stream": True},
                ) as r:
                    if r.status != 200:
                        err = await r.text()
                        yield json.dumps({"error": f"HTTP {r.status}: {err[:200]}"})
                        return
                    async for raw in r.content:
                        line = raw.decode().strip()
                        if line:
                            yield line
        except Exception as e:
            yield json.dumps({"error": str(e)})
        finally:
            self._cache_ts = 0  # Cache invalidieren

    async def delete(self, model: str) -> dict:
        """Löscht ein installiertes Modell."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                async with s.delete(
                    f"{self.base}/api/delete",
                    json={"name": model},
                ) as r:
                    self._cache_ts = 0
                    if r.status == 200:
                        log.info("Ollama delete OK: %s", model)
                        return {"ok": True, "model": model}
                    err = await r.text()
                    return {"ok": False, "error": err[:200]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def model_info(self, model: str) -> dict:
        """Details zu einem Modell (Parameter, Quantisierung, etc.)."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.post(
                    f"{self.base}/api/show",
                    json={"name": model},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        info = d.get("modelfile", "")
                        details = d.get("details", {})
                        return {
                            "ok": True,
                            "model": model,
                            "family": details.get("family", ""),
                            "params": details.get("parameter_size", ""),
                            "quantization": details.get("quantization_level", ""),
                            "format": details.get("format", ""),
                            "modelfile_preview": info[:300],
                        }
                    return {"ok": False, "error": f"HTTP {r.status}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Chat & Generate ───────────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict] | str,
        model: str | None = None,
        system: str = "",
        max_tokens: int = 1500,
    ) -> str:
        """Einzel-Antwort Chat. Gibt leeren String bei Ollama-Offline zurück."""
        if isinstance(messages, str):
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": messages})
        else:
            msgs = messages

        chosen = model or DEFAULT_MODEL
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_CHAT)
            ) as s:
                async with s.post(
                    f"{self.base}/api/chat",
                    json={"model": chosen, "messages": msgs, "stream": False,
                          "options": {"num_predict": max_tokens}},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        text = d.get("message", {}).get("content", "")
                        log.debug("Ollama chat OK model=%s len=%d", chosen, len(text))
                        return text
                    log.warning("Ollama chat HTTP %s", r.status)
        except Exception as e:
            log.debug("Ollama chat error: %s", e)
        return ""

    async def stream(
        self,
        prompt: str,
        model: str | None = None,
        system: str = "",
    ) -> AsyncGenerator[str, None]:
        """Streaming-Chat — yields Text-Chunks."""
        chosen = model or DEFAULT_MODEL
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_CHAT)
            ) as s:
                async with s.post(
                    f"{self.base}/api/chat",
                    json={"model": chosen, "messages": messages, "stream": True},
                ) as r:
                    if r.status != 200:
                        yield f"[Ollama HTTP {r.status}]"
                        return
                    async for raw in r.content:
                        line = raw.decode().strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            chunk = d.get("message", {}).get("content", "")
                            if chunk:
                                yield chunk
                            if d.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield f"[Fehler: {e}]"

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 800,
    ) -> str:
        """Einfache Text-Generierung (kein Chat-History)."""
        chosen = model or FAST_MODEL
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_CHAT)
            ) as s:
                async with s.post(
                    f"{self.base}/api/generate",
                    json={"model": chosen, "prompt": prompt, "stream": False,
                          "options": {"num_predict": max_tokens}},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        return d.get("response", "")
        except Exception as e:
            log.debug("Ollama generate: %s", e)
        return ""


# Singleton
_manager: OllamaManager | None = None


def get_manager() -> OllamaManager:
    global _manager
    if _manager is None:
        _manager = OllamaManager()
    return _manager
