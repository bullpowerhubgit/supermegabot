#!/usr/bin/env python3
"""
OpenClaw — Lokales KI-System via Ollama.
Primäre kostenlose AI für alle Module: from modules.open_claw import claw_complete, CLAW
Modelle: qwen3.6 (best), gemma4 (balanced), llama3.2 (fastest)
"""
from __future__ import annotations
import asyncio
import logging
import os
import aiohttp

log = logging.getLogger("OpenClaw")

OLLAMA_BASE  = os.getenv("OLLAMA_BASE", "http://localhost:11434")
CLAW_MODEL   = os.getenv("OLLAMA_CLAW_MODEL", "qwen3.6:latest")
FAST_MODEL   = os.getenv("OLLAMA_FAST_MODEL", "llama3.2:latest")
SMART_MODEL  = os.getenv("OLLAMA_SMART_MODEL", "qwen3.6:latest")


async def claw_complete(prompt: str, system: str = "", fast: bool = False,
                        model: str | None = None, max_tokens: int = 1500) -> str:
    """Local Ollama AI completion. Returns empty string if Ollama offline."""
    chosen_model = model or (FAST_MODEL if fast else CLAW_MODEL)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
            async with s.post(
                f"{OLLAMA_BASE}/api/chat",
                json={"model": chosen_model, "messages": messages,
                      "stream": False, "options": {"num_predict": max_tokens}},
            ) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    text = d.get("message", {}).get("content", "")
                    log.info("OpenClaw OK model=%s chars=%d", chosen_model, len(text))
                    return text
                body = await r.text()
                log.warning("OpenClaw %s: %s", r.status, body[:120])
    except Exception as e:
        log.debug("OpenClaw offline: %s", e)
    return ""


async def get_models() -> list[dict]:
    """Return list of available Ollama models."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.get(f"{OLLAMA_BASE}/api/tags") as r:
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
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as s:
            async with s.get(f"{OLLAMA_BASE}/") as r:
                return r.status == 200
    except Exception:
        return False


async def claw_generate_content(topic: str, content_type: str = "post") -> dict:
    """Generate marketing content using local AI."""
    system = "Du bist ein KI-Marketing-Experte. Erstelle verkaufsstarken deutschen Content."
    prompts = {
        "post": f"Erstelle einen kurzen viralen Social-Media-Post (max 150 Wörter) über: {topic}. Mit Call-to-Action.",
        "email": f"Erstelle eine Verkaufs-E-Mail Betreff + Body (max 200 Wörter) für: {topic}.",
        "seo": f"Erstelle SEO-optimierten Produkttitel + Beschreibung (150 Wörter) für: {topic}.",
        "telegram": f"Erstelle eine Telegram-Nachricht (max 100 Wörter) mit Emojis für: {topic}.",
        "blog": f"Erstelle einen Blog-Artikel (300 Wörter) mit H2-Überschriften über: {topic}.",
    }
    prompt = prompts.get(content_type, prompts["post"])
    text = await claw_complete(prompt, system=system, fast=(content_type == "post"))
    return {
        "ok": bool(text),
        "content_type": content_type,
        "topic": topic,
        "text": text,
        "model": FAST_MODEL if content_type == "post" else CLAW_MODEL,
        "source": "OpenClaw-Local",
    }


async def claw_analyze_product(product_title: str, current_description: str = "") -> dict:
    """Analyze and improve a Shopify product with local AI."""
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
    """Generate daily revenue strategy using local AI."""
    system = "Du bist ein Revenue-Stratege für digitale Produkte. Sei konkret und handlungsorientiert."
    prompt = """Erstelle eine Tages-Revenue-Strategie für:
- Shopify Store (Dropshipping + Print-on-Demand)
- Digistore24 Affiliate (417 Produkte)
- Telegram Bot Subscription

Fokus: Schnelle Einnahmen in 24h. Konkrete Schritte, keine Theorie."""
    return await claw_complete(prompt, system=system)


async def claw_self_improve(module_name: str, error_log: str = "") -> str:
    """Use local AI to suggest improvements for a module."""
    system = "Du bist ein Python-Senior-Entwickler. Analysiere und verbessere Code-Module."
    prompt = f"""Modul: {module_name}
Fehler-Log: {error_log[:500] if error_log else 'keine Fehler'}

Schlage 3 konkrete Verbesserungen vor um das Modul stabiler und profitabler zu machen."""
    return await claw_complete(prompt, system=system, fast=True)


# Singleton-ähnliche Klasse für einfachen Import
class OpenClaw:
    """Synchron-Wrapper für einfache Nutzung in non-async Kontexten."""

    def __init__(self):
        self.base = OLLAMA_BASE
        self.default_model = CLAW_MODEL

    def complete(self, prompt: str, system: str = "", fast: bool = False) -> str:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, claw_complete(prompt, system, fast))
                    return future.result(timeout=120)
            return loop.run_until_complete(claw_complete(prompt, system, fast))
        except Exception as e:
            log.debug("OpenClaw sync error: %s", e)
            return ""

    def generate(self, topic: str, content_type: str = "post") -> dict:
        try:
            return asyncio.run(claw_generate_content(topic, content_type))
        except Exception as e:
            return {"ok": False, "error": str(e)}


CLAW = OpenClaw()
