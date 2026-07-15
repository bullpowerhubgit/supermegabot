"""
Ollama Client — lokaler KI-Fallback für aiitec-saas.

Nutzung:
  from modules.ollama_client import ollama_chat, ollama_available

  if await ollama_available():
      reply = await ollama_chat(messages, model="mistral:7b-instruct")
"""
import os
import logging
import aiohttp

log = logging.getLogger(__name__)

OLLAMA_URL  = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")
_FALLBACK_MODEL = "llama3.2:latest"


async def ollama_available() -> bool:
    """Prüft ob Ollama erreichbar ist."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{OLLAMA_URL}/api/tags",
                             timeout=aiohttp.ClientTimeout(total=3)) as r:
                return r.status == 200
    except Exception:
        return False


async def list_models() -> list[dict]:
    """Gibt alle lokal verfügbaren Modelle zurück."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{OLLAMA_URL}/api/tags",
                             timeout=aiohttp.ClientTimeout(total=5)) as r:
                d = await r.json(content_type=None)
                return d.get("models", [])
    except Exception:
        return []


async def _get_best_model() -> str:
    """Wählt das beste verfügbare Modell."""
    models = await list_models()
    names = [m["name"] for m in models]
    preferred = [
        "mistral:7b-instruct", "mistral:latest",
        "llama3.1:8b", "llama3.1:latest",
        "qwen2.5-coder:7b",
        "llama3.2:latest", "llama3.2:3b",
        "gemma2:latest",
    ]
    for p in preferred:
        if p in names:
            return p
    return names[0] if names else _FALLBACK_MODEL


async def ollama_chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 800,
) -> str | None:
    """
    Chat-Completion via Ollama — OpenAI-kompatibles messages-Format.
    Gibt den Antworttext zurück oder None bei Fehler.
    """
    m = model or OLLAMA_MODEL
    if not await ollama_available():
        log.debug("Ollama nicht verfügbar")
        return None

    # Prüfe ob gewünschtes Modell vorhanden, sonst Fallback
    models = await list_models()
    names = [mm["name"] for mm in models]
    if m not in names:
        m = await _get_best_model()
        log.info("Ollama: Modell nicht gefunden, nutze %s", m)

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": m,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
                timeout=aiohttp.ClientTimeout(total=120),
            ) as r:
                d = await r.json(content_type=None)

        if "error" in d:
            log.warning("Ollama error: %s", d["error"])
            return None

        return d.get("message", {}).get("content", "").strip() or None

    except Exception as e:
        log.warning("Ollama chat failed: %s", e)
        return None


async def ollama_generate(prompt: str, model: str | None = None) -> str | None:
    """Einfaches Text-Generate (kein Chat-Format)."""
    m = model or OLLAMA_MODEL
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": m, "prompt": prompt, "stream": False},
                timeout=aiohttp.ClientTimeout(total=120),
            ) as r:
                d = await r.json(content_type=None)
        return d.get("response", "").strip() or None
    except Exception as e:
        log.warning("Ollama generate failed: %s", e)
        return None


async def pull_model(model: str) -> bool:
    """Zieht ein Modell von ollama.com (läuft im Hintergrund)."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{OLLAMA_URL}/api/pull",
                json={"name": model, "stream": False},
                timeout=aiohttp.ClientTimeout(total=600),
            ) as r:
                d = await r.json(content_type=None)
        return d.get("status") == "success"
    except Exception as e:
        log.warning("Ollama pull %s failed: %s", model, e)
        return False
