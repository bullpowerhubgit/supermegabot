#!/usr/bin/env python3
"""
API Hunt — Autonomes KI-Fallback-System (IMMER AN)
Kette: OpenClaw/Ollama (lokal) → Groq → DeepSeek → OpenRouter (5 Modelle) → Gemini → Anthropic → OpenAI → Perplexity → Ollama
Circuit Breaker: nach 3 Fehlern 10 min deaktiviert, dann auto-re-enable
Background Health Monitor: alle 5 min alle Provider testen
Telegram-Alert bei Provider-Wechsel und Ausfällen
OpenClaw ist IMMER Schritt 0 — kostenlos, kein Rate-Limit, kein Datenschutzproblem
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

log = logging.getLogger("APIHunt")

# ── Env-Getter ─────────────────────────────────────────────────────────────────
def _groq():        return os.getenv("GROQ_API_KEY", "")
def _deepseek():    return os.getenv("DEEPSEEK_API_KEY", "")
def _openrouter():  return os.getenv("OPENROUTER_API_KEY", "")
def _gemini():      return os.getenv("GEMINI_API_KEY", "") or os.getenv("GCP_API_KEY", "")
def _anthropic():   return os.getenv("ANTHROPIC_API_KEY", "")
def _openai():      return os.getenv("OPENAI_API_KEY", "")
def _perplexity():  return os.getenv("PERPLEXITY_API_KEY", "")
def _tg_bot():      return os.getenv("TELEGRAM_BOT_TOKEN", "")
def _tg_chat():     return os.getenv("TELEGRAM_CHAT_ID", "")
# Neue kostenlose Provider
def _cerebras():    return os.getenv("CEREBRAS_API_KEY", "")
def _together():    return os.getenv("TOGETHER_API_KEY", "")
def _sambanova():   return os.getenv("SAMBANOVA_API_KEY", "")
def _mistral():     return os.getenv("MISTRAL_API_KEY", "")

# ── OpenClaw / Ollama Konfiguration ────────────────────────────────────────────
def _ollama_base()  : return os.getenv("OLLAMA_BASE", "http://localhost:11434")
def _ollama_model() : return os.getenv("OLLAMA_CLAW_MODEL", os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2:latest"))
def _ollama_fast()  : return os.getenv("OLLAMA_FAST_MODEL", _ollama_model())
def _ollama_smart() : return os.getenv("OLLAMA_SMART_MODEL", os.getenv("OLLAMA_CLAW_MODEL", "llama3.2:latest"))

# OpenClaw online-Status (wird beim ersten Aufruf gecacht, alle 60s aktualisiert)
_openclaw_online: bool = False
_openclaw_last_check: float = 0.0
_OPENCLAW_CHECK_INTERVAL = 60  # Sekunden zwischen Checks

_OPENROUTER_REFERER = "https://supermegabot-production.up.railway.app"

# ── Kostenlose OpenRouter-Modelle (Fallback-Rotation) ──────────────────────────
_OR_FREE_MODELS = [
    "google/gemma-4-26b-a4b-it:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "qwen/qwen3-0.6b:free",
    "microsoft/phi-3-mini-128k-instruct:free",
    "google/gemma-3-12b-it:free",
    "deepseek/deepseek-r1-0528:free",
    "tngtech/deepseek-r1t-chimera:free",
]

# ── Cerebras Modelle (kostenlos, sehr schnell) ─────────────────────────────────
_CEREBRAS_MODELS = ["llama-4-scout-17b-16e-instruct", "llama-3.3-70b"]
_CEREBRAS_BASE   = "https://api.cerebras.ai/v1/chat/completions"

# ── SambaNova Modelle (kostenlos) ──────────────────────────────────────────────
_SAMBANOVA_MODELS = ["Meta-Llama-3.3-70B-Instruct", "Meta-Llama-3.1-405B-Instruct"]
_SAMBANOVA_BASE   = "https://api.sambanova.ai/v1/chat/completions"

# ── Together AI Modelle (kostenlos-Tier) ───────────────────────────────────────
_TOGETHER_MODELS = ["meta-llama/Llama-3-8b-chat-hf", "mistralai/Mistral-7B-Instruct-v0.3"]
_TOGETHER_BASE   = "https://api.together.xyz/v1/chat/completions"

# ── Mistral API (kostenlos-Tier) ───────────────────────────────────────────────
_MISTRAL_MODELS = ["mistral-small-latest", "open-mistral-7b"]
_MISTRAL_BASE   = "https://api.mistral.ai/v1/chat/completions"

# ── Gemini Modelle (kostenlos) ─────────────────────────────────────────────────
_GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# ── Circuit Breaker State ──────────────────────────────────────────────────────
# {provider_name: {"fails": int, "until": float, "total_fails": int}}
_CB: dict[str, dict] = {}

_CB_THRESHOLD   = 5      # Fehler bis Deaktivierung (erhöht von 3)
_CB_BACKOFF_1   = 600    # 10 min nach 1. Deaktivierung
_CB_BACKOFF_2   = 1800   # 30 min nach 2. Deaktivierung
_CB_BACKOFF_MAX = 3600   # 1h max

# Letzter aktiver Provider für Wechsel-Detection
_last_provider: str = ""
_monitor_running: bool = False
_last_all_failed_log: float = 0.0

# Globales Semaphore: max. 8 gleichzeitige AI-Calls (erhöht da 4 Groq + 9 OR Modelle verfügbar)
_AI_SEM: Optional[asyncio.Semaphore] = None

def _get_sem() -> asyncio.Semaphore:
    global _AI_SEM
    if _AI_SEM is None:
        _AI_SEM = asyncio.Semaphore(8)
    return _AI_SEM


def _cb_ok(provider: str) -> bool:
    """Ist der Provider gerade verfügbar? (Circuit Breaker Check)"""
    s = _CB.get(provider)
    if not s:
        return True
    if s.get("until", 0) > time.time():
        return False
    # Timeout abgelaufen → re-enable
    s["fails"] = 0
    return True


def _cb_rate_limit(provider: str, seconds: int = 90) -> None:
    """Rate-Limit-Pause OHNE CB-Threshold-Erhöhung (kein Ausfall, nur kurze Pause)."""
    if provider not in _CB:
        _CB[provider] = {"fails": 0, "until": 0.0, "total_fails": 0, "deactivations": 0}
    s = _CB[provider]
    new_until = time.time() + seconds
    if new_until > s.get("until", 0):
        s["until"] = new_until
    log.debug("APIHunt: %s Rate-Limit-Pause für %ds", provider, seconds)


def _cb_fail(provider: str) -> None:
    """Fehler für Provider registrieren — Circuit Breaker aktualisieren."""
    if provider not in _CB:
        _CB[provider] = {"fails": 0, "until": 0.0, "total_fails": 0, "deactivations": 0}
    s = _CB[provider]
    s["fails"] = s.get("fails", 0) + 1
    s["total_fails"] = s.get("total_fails", 0) + 1
    if s["fails"] >= _CB_THRESHOLD:
        deact = s.get("deactivations", 0)
        if deact == 0:
            backoff = _CB_BACKOFF_1
        elif deact == 1:
            backoff = _CB_BACKOFF_2
        else:
            backoff = _CB_BACKOFF_MAX
        s["until"] = time.time() + backoff
        s["deactivations"] = deact + 1
        s["fails"] = 0
        log.warning(
            "APIHunt: %s DEAKTIVIERT für %ds (Deaktivierung #%d, gesamt %d Fehler)",
            provider, backoff, s["deactivations"], s["total_fails"],
        )
        asyncio.ensure_future(_alert_provider_down(provider, backoff))


def _cb_success(provider: str) -> None:
    """Erfolg registrieren — Fehler-Zähler zurücksetzen."""
    global _last_provider
    if provider not in _CB:
        _CB[provider] = {"fails": 0, "until": 0.0, "total_fails": 0, "deactivations": 0}
    s = _CB[provider]
    if s.get("fails", 0) > 0:
        s["fails"] = 0

    if _last_provider and _last_provider != provider:
        log.info("APIHunt: Provider gewechselt %s → %s", _last_provider, provider)
        asyncio.ensure_future(_alert_provider_switch(_last_provider, provider))
    _last_provider = provider


# ── Telegram Alerts ────────────────────────────────────────────────────────────
async def _tg_send(text: str) -> None:
    """Sendet Telegram-Nachricht (best effort, kein Fehler wenn offline)."""
    bot = _tg_bot()
    chat = _tg_chat()
    if not bot or not chat:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            await s.post(
                f"https://api.telegram.org/bot{bot}/sendMessage",
                json={"chat_id": chat, "text": text[:4000]},
            )
    except Exception:
        pass


async def _alert_provider_down(provider: str, backoff: int) -> None:
    await _tg_send(
        f"⚠️ API Hunt: {provider} AUSGEFALLEN\n"
        f"Deaktiviert für {backoff//60} Minuten.\n"
        f"Automatisch auf nächsten Provider gewechselt."
    )


async def _alert_provider_switch(old: str, new: str) -> None:
    await _tg_send(
        f"🔄 API Hunt: Provider-Wechsel\n"
        f"{old} → {new}\n"
        f"Automatisch umgeschaltet."
    )


async def _alert_all_failed() -> None:
    await _tg_send(
        "🚨 API Hunt KRITISCH: ALLE Provider ausgefallen!\n"
        "Prüfe API-Keys und Guthaben. System läuft auf Template-Fallback."
    )


# ── Health Monitor (Background Task) ──────────────────────────────────────────
async def _health_monitor() -> None:
    """Läuft permanent — testet alle deaktivierten Provider.
    Normal: alle 5 min. Wenn alle ausgefallen: alle 60s (Schnell-Recovery)."""
    global _monitor_running
    _monitor_running = True
    log.info("APIHunt: Health Monitor gestartet")
    while True:
        try:
            # Schnell-Recovery wenn alle Provider deaktiviert
            all_blocked = all(
                _CB.get(p, {}).get("until", 0) > time.time()
                for p in ["Groq", "DeepSeek", "OpenRouter", "Gemini", "Anthropic", "OpenAI", "Perplexity"]
            )
            interval = 60 if all_blocked else 300
            await asyncio.sleep(interval)
            await _probe_all_providers()
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.debug("APIHunt monitor error: %s", e)


async def _probe_all_providers() -> None:
    """Testet jeden Provider mit einem Mini-Prompt."""
    import aiohttp
    probe = [{"role": "user", "content": "Say OK"}]

    async def try_groq():
        if not _groq() or _cb_ok("Groq"):
            return
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
                async with s.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_groq()}", "Content-Type": "application/json"},
                    json={"model": "llama-3.1-8b-instant", "max_tokens": 5, "messages": probe},
                ) as r:
                    if r.status == 200:
                        _CB["Groq"] = {"fails": 0, "until": 0.0, "total_fails": _CB.get("Groq", {}).get("total_fails", 0), "deactivations": 0}
                        log.info("APIHunt: Groq wieder ONLINE")
                        await _tg_send("✅ API Hunt: Groq wieder online!")
        except Exception:
            pass

    async def try_deepseek():
        if not _deepseek() or _cb_ok("DeepSeek"):
            return
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
                async with s.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_deepseek()}", "Content-Type": "application/json"},
                    json={"model": "deepseek-chat", "max_tokens": 5, "messages": probe},
                ) as r:
                    if r.status == 200:
                        _CB["DeepSeek"] = {"fails": 0, "until": 0.0, "total_fails": _CB.get("DeepSeek", {}).get("total_fails", 0), "deactivations": 0}
                        log.info("APIHunt: DeepSeek wieder ONLINE")
                        await _tg_send("✅ API Hunt: DeepSeek wieder online!")
        except Exception:
            pass

    async def try_openrouter():
        if not _openrouter() or _cb_ok("OpenRouter"):
            return
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_openrouter()}", "Content-Type": "application/json",
                             "HTTP-Referer": _OPENROUTER_REFERER},
                    json={"model": _OR_FREE_MODELS[0], "max_tokens": 5, "messages": probe},
                ) as r:
                    if r.status == 200:
                        _CB["OpenRouter"] = {"fails": 0, "until": 0.0, "total_fails": _CB.get("OpenRouter", {}).get("total_fails", 0), "deactivations": 0}
                        log.info("APIHunt: OpenRouter wieder ONLINE")
                        await _tg_send("✅ API Hunt: OpenRouter wieder online!")
        except Exception:
            pass

    async def try_anthropic():
        if not _anthropic() or _cb_ok("Anthropic"):
            return
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": _anthropic(), "anthropic-version": "2023-06-01",
                             "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": 5,
                          "messages": probe},
                ) as r:
                    if r.status == 200:
                        _CB["Anthropic"] = {"fails": 0, "until": 0.0, "total_fails": _CB.get("Anthropic", {}).get("total_fails", 0), "deactivations": 0}
                        log.info("APIHunt: Anthropic wieder ONLINE (Credits aufgeladen!)")
                        await _tg_send("✅ API Hunt: Anthropic wieder online — Credits aufgeladen!")
        except Exception:
            pass

    async def try_openclaw():
        """OpenClaw/Ollama Recheck — war offline, jetzt wieder versuchen."""
        global _openclaw_online, _openclaw_last_check
        if _openclaw_online:
            return
        if time.time() - _openclaw_last_check < _OPENCLAW_CHECK_INTERVAL:
            return
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
                async with s.post(
                    f"{_ollama_base()}/api/chat",
                    json={"model": _ollama_fast(), "messages": [{"role": "user", "content": "OK"}],
                          "stream": False, "options": {"num_predict": 3}},
                ) as r:
                    if r.status == 200:
                        _openclaw_online = True
                        _openclaw_last_check = time.time()
                        log.info("APIHunt: OpenClaw wieder ONLINE (%s)", _ollama_fast())
                        await _tg_send(f"✅ OpenClaw wieder online! Modell: {_ollama_fast()}")
                    else:
                        _openclaw_last_check = time.time()
        except Exception:
            _openclaw_last_check = time.time()

    async def try_cerebras():
        if not _cerebras() or not _cb_ok("Cerebras"):
            return
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.post(_CEREBRAS_BASE, headers={"Authorization": f"Bearer {_cerebras()}", "Content-Type": "application/json"},
                    json={"model": _CEREBRAS_MODELS[0], "messages": [{"role": "user", "content": "ok"}], "max_tokens": 5}) as r:
                    if r.status == 200:
                        _cb_reset("Cerebras")
        except Exception:
            _cb_fail("Cerebras")

    async def try_sambanova():
        if not _sambanova() or not _cb_ok("SambaNova"):
            return
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.post(_SAMBANOVA_BASE, headers={"Authorization": f"Bearer {_sambanova()}", "Content-Type": "application/json"},
                    json={"model": _SAMBANOVA_MODELS[0], "messages": [{"role": "user", "content": "ok"}], "max_tokens": 5}) as r:
                    if r.status == 200:
                        _cb_reset("SambaNova")
        except Exception:
            _cb_fail("SambaNova")

    async def try_mistral():
        if not _mistral() or not _cb_ok("Mistral"):
            return
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.post(_MISTRAL_BASE, headers={"Authorization": f"Bearer {_mistral()}", "Content-Type": "application/json"},
                    json={"model": _MISTRAL_MODELS[0], "messages": [{"role": "user", "content": "ok"}], "max_tokens": 5}) as r:
                    if r.status == 200:
                        _cb_reset("Mistral")
        except Exception:
            _cb_fail("Mistral")

    await asyncio.gather(try_openclaw(), try_groq(), try_deepseek(), try_openrouter(), try_anthropic(),
                         try_cerebras(), try_sambanova(), try_mistral())


def start_health_monitor() -> None:
    """Startet den Background Health Monitor (einmalig aufrufen beim Server-Start)."""
    global _monitor_running
    if not _monitor_running:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_health_monitor())
            else:
                log.debug("APIHunt: kein laufender Event-Loop für Monitor")
        except Exception as e:
            log.debug("APIHunt: Monitor start error: %s", e)


# ── Status-Endpoint ────────────────────────────────────────────────────────────
def api_status() -> dict:
    """Gibt aktuellen Status aller Provider zurück (für Dashboard-Anzeige)."""
    now = time.time()
    providers = {
        "OpenClaw":   True,   # Ollama lokal — immer Key vorhanden (kein Key nötig)
        "Groq":       bool(_groq()),
        "DeepSeek":   bool(_deepseek()),
        "OpenRouter":  bool(_openrouter()),
        "Gemini":     bool(_gemini()),
        "Anthropic":  bool(_anthropic()),
        "OpenAI":     bool(_openai()),
        "Perplexity": bool(_perplexity()),
    }
    result = {}
    for name, has_key in providers.items():
        if not has_key:
            result[name] = {"status": "no_key", "active": False}
            continue
        s = _CB.get(name, {})
        disabled_until = s.get("until", 0)
        if disabled_until > now:
            result[name] = {
                "status": "circuit_open",
                "active": False,
                "retry_in": int(disabled_until - now),
                "total_fails": s.get("total_fails", 0),
            }
        else:
            provider_key = "Ollama" if name == "OpenClaw" else name
            is_active = (provider_key == _last_provider) or (name == _last_provider)
            result[name] = {
                "status": "ok" if is_active else "standby",
                "active": is_active,
                "total_fails": s.get("total_fails", 0),
                "deactivations": s.get("deactivations", 0),
            }

    # OpenClaw extras
    result["OpenClaw"]["model"]  = _ollama_model()
    result["OpenClaw"]["base"]   = _ollama_base()
    result["OpenClaw"]["online"] = _openclaw_online
    result["OpenClaw"]["fast_model"]  = _ollama_fast()
    result["OpenClaw"]["smart_model"] = _ollama_smart()

    result["current_provider"] = _last_provider or "unknown"
    result["monitor_running"]  = _monitor_running
    return result


# ── Haupt-Funktion ─────────────────────────────────────────────────────────────
async def ai_complete(
    prompt: str,
    system: str = "",
    model_hint: str = "fast",
    max_tokens: int = 1200,
) -> str:
    """
    Vollautomatischer API Hunt mit Circuit Breaker.
    Kette: Groq → DeepSeek → OpenRouter (5 Modelle) → Gemini (3 Modelle)
           → Anthropic → OpenAI → Perplexity → Ollama → Template-Fallback
    """
    async with _get_sem():
        return await _ai_complete_inner(prompt=prompt, system=system, model_hint=model_hint, max_tokens=max_tokens)


async def _ai_complete_inner(
    prompt: str,
    system: str = "",
    model_hint: str = "fast",
    max_tokens: int = 1200,
) -> str:
    import aiohttp

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # ── 0. OpenClaw / Ollama LOKAL — IMMER ERSTE WAHL ────────────────────────────
    # Kostenlos, kein Rate-Limit, kein Datenschutzproblem, läuft auf Rudolfs Rechner.
    # Kurzer Timeout (5s default) damit Cloud-Fallback sofort greift wenn offline.
    global _openclaw_online, _openclaw_last_check
    _ollama_timeout = int(os.getenv("OLLAMA_TIMEOUT", "5"))
    _ollama_first   = os.getenv("OLLAMA_FIRST", "true").lower() != "false"

    if _ollama_first:
        # Modell-Auswahl je nach Aufgabe:
        # model_hint="fast"   → OLLAMA_FAST_MODEL (schnelles kleines Modell)
        # model_hint="smart"  → OLLAMA_SMART_MODEL (größeres Modell für komplexe Tasks)
        # model_hint="code"   → OLLAMA_CODE_MODEL (Code-Modell)
        # sonst               → Standard-Claw-Modell
        if model_hint == "fast":
            chosen_model = _ollama_fast()
        elif model_hint in ("smart", "large", "quality"):
            chosen_model = _ollama_smart()
        elif model_hint == "code":
            chosen_model = os.getenv("OLLAMA_CODE_MODEL", _ollama_model())
        else:
            chosen_model = _ollama_model()

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=_ollama_timeout)) as s:
                async with s.post(
                    f"{_ollama_base()}/api/chat",
                    json={
                        "model": chosen_model,
                        "messages": messages,
                        "stream": False,
                        "options": {"num_predict": max_tokens, "temperature": 0.7},
                    },
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        text = d.get("message", {}).get("content", "")
                        if text:
                            _cb_success("Ollama")
                            _openclaw_online = True
                            _openclaw_last_check = time.time()
                            log.debug("OpenClaw OK model=%s len=%d", chosen_model, len(text))
                            return text
                    log.debug("OpenClaw: HTTP %s — Cloud-Fallback", r.status)
        except Exception as e:
            log.debug("OpenClaw offline: %s — Cloud greift", e)
            _openclaw_online = False
            _openclaw_last_check = time.time()

    # ── 1. Groq (4-Modell-Rotation: llama/gemma/mixtral — alle kostenlos) ────────
    _GROQ_ROTATION = [
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "gemma2-9b-it",
        "mixtral-8x7b-32768",
    ]
    if _groq() and _cb_ok("Groq"):
        for _gm in _GROQ_ROTATION:
            _gm_cb = f"Groq:{_gm}"
            if not _cb_ok(_gm_cb):
                continue
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as s:
                    async with s.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {_groq()}", "Content-Type": "application/json"},
                        json={"model": _gm, "max_tokens": max_tokens, "messages": messages},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = d.get("choices", [{}])[0].get("message", {}).get("content", "")
                            if text:
                                _cb_success("Groq")
                                if _gm_cb in _CB:
                                    _CB[_gm_cb]["fails"] = 0
                                return text
                        elif r.status in (401, 403):
                            log.warning("Groq: Key ungültig (%s)", r.status)
                            _cb_fail("Groq")
                            break
                        elif r.status == 429:
                            log.debug("Groq/%s: Rate-Limit — 120s Pause, nächstes Modell", _gm)
                            _cb_rate_limit(_gm_cb, 120)
                            continue
                        else:
                            log.debug("Groq/%s: HTTP %s", _gm, r.status)
                            _cb_fail(_gm_cb)
            except Exception as e:
                log.debug("Groq/%s error: %s", _gm, e)
                _cb_fail(_gm_cb)

    # ── 2. DeepSeek (günstig, gut) ─────────────────────────────────────────────
    if _deepseek() and _cb_ok("DeepSeek"):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                async with s.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_deepseek()}", "Content-Type": "application/json"},
                    json={"model": "deepseek-chat", "max_tokens": max_tokens, "messages": messages},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        text = d.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if text:
                            _cb_success("DeepSeek")
                            return text
                    if r.status in (401, 403, 402):
                        log.warning("DeepSeek: Key/Credits Problem (%s) — dauerhaft deaktiviert", r.status)
                        if "DeepSeek" not in _CB:
                            _CB["DeepSeek"] = {"fails": 0, "until": 0.0, "total_fails": 0, "deactivations": 0}
                        _CB["DeepSeek"]["until"] = time.time() + 3600
                    elif r.status == 429:
                        log.debug("DeepSeek: Rate-Limit — 90s Pause")
                        _cb_rate_limit("DeepSeek", 90)
                    else:
                        _cb_fail("DeepSeek")
        except Exception as e:
            log.debug("DeepSeek error: %s", e)
            _cb_fail("DeepSeek")

    # ── 3. OpenRouter — 5 kostenlose Modelle rotation ──────────────────────────
    if _openrouter() and _cb_ok("OpenRouter"):
        or_fail_count = 0
        for model in _OR_FREE_MODELS:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {_openrouter()}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": _OPENROUTER_REFERER,
                        },
                        json={"model": model, "max_tokens": max_tokens, "messages": messages},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = d.get("choices", [{}])[0].get("message", {}).get("content", "")
                            if text:
                                _cb_success("OpenRouter")
                                log.debug("OpenRouter OK: %s", model)
                                return text
                        elif r.status in (401, 403):
                            log.warning("OpenRouter: Key ungültig")
                            _cb_fail("OpenRouter")
                            break
                        elif r.status == 429:
                            _cb_rate_limit("OpenRouter", 60)
                            or_fail_count = 0  # Rate-Limit ≠ harter Fehler
                            break
                        else:
                            log.debug("OpenRouter %s auf %s — nächstes Modell", r.status, model)
                            or_fail_count += 1
            except Exception as e:
                log.debug("OpenRouter %s error: %s", model, e)
                or_fail_count += 1
        if or_fail_count >= len(_OR_FREE_MODELS):
            _cb_fail("OpenRouter")

    # ── 4. Gemini (3 kostenlose Modelle) ──────────────────────────────────────
    if _gemini() and _cb_ok("Gemini"):
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        gemini_hard_fail = False
        for model in _GEMINI_MODELS:
            try:
                url = f"{_GEMINI_BASE}/{model}:generateContent?key={_gemini()}"
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(
                        url,
                        headers={"Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": full_prompt}]}],
                              "generationConfig": {"maxOutputTokens": max_tokens}},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = (d.get("candidates") or [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            if text:
                                _cb_success("Gemini")
                                log.debug("Gemini OK: %s", model)
                                return text
                        elif r.status in (400, 401, 403):
                            log.warning("Gemini: Key ungültig/gesperrt (%s) — 1h deaktiviert", r.status)
                            if "Gemini" not in _CB:
                                _CB["Gemini"] = {"fails": 0, "until": 0.0, "total_fails": 0, "deactivations": 0}
                            _CB["Gemini"]["until"] = time.time() + 3600
                            gemini_hard_fail = True
                            break
                        elif r.status == 429:
                            log.debug("Gemini Rate-Limit auf %s — nächstes Modell", model)
                        else:
                            log.debug("Gemini %s auf %s — nächstes Modell", r.status, model)
            except Exception as e:
                log.debug("Gemini %s error: %s", model, e)
        if not gemini_hard_fail and not _cb_ok("Gemini"):
            pass  # bereits gesetzt

    # ── 5. Anthropic Claude Haiku ─────────────────────────────────────────────
    if _anthropic() and _cb_ok("Anthropic"):
        try:
            msg_list = [m for m in messages if m.get("role") != "system"]
            sys_text = system or next((m["content"] for m in messages if m.get("role") == "system"), "")
            payload = {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": max_tokens,
                "messages": msg_list or [{"role": "user", "content": prompt}],
            }
            if sys_text:
                payload["system"] = sys_text
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
                async with s.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": _anthropic(), "anthropic-version": "2023-06-01",
                             "content-type": "application/json"},
                    json=payload,
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        text = (d.get("content") or [{"text": ""}])[0].get("text", "")
                        if text:
                            _cb_success("Anthropic")
                            return text
                    if r.status in (400, 402, 529):
                        body = await r.json(content_type=None)
                        is_credit = "credit balance" in str(body).lower() or "too low" in str(body).lower()
                        if is_credit:
                            log.warning("Anthropic: CREDITS LEER — 24h deaktiviert. Bitte auf console.anthropic.com aufladen!")
                            asyncio.ensure_future(_tg_send(
                                "🚨 ANTHROPIC CREDITS LEER!\n"
                                "Alle AI-Anfragen laufen über Groq/OpenRouter/OpenAI.\n"
                                "Bitte auf console.anthropic.com Guthaben aufladen."
                            ))
                            if "Anthropic" not in _CB:
                                _CB["Anthropic"] = {"fails": _CB_THRESHOLD, "until": 0.0, "total_fails": 0, "deactivations": 0}
                            _CB["Anthropic"]["until"] = time.time() + 86400  # 24h statt 1h
                        else:
                            log.warning("Anthropic: Fehler %s — 1h deaktiviert", r.status)
                            if "Anthropic" not in _CB:
                                _CB["Anthropic"] = {"fails": _CB_THRESHOLD, "until": 0.0, "total_fails": 0, "deactivations": 0}
                            _CB["Anthropic"]["until"] = time.time() + 3600
                    elif r.status in (401, 403):
                        log.warning("Anthropic: Key ungültig (%s)", r.status)
                        _cb_fail("Anthropic")
                    else:
                        _cb_fail("Anthropic")
        except Exception as e:
            log.debug("Anthropic error: %s", e)
            _cb_fail("Anthropic")

    # ── 6. OpenAI GPT-4o-mini ─────────────────────────────────────────────────
    if _openai() and _cb_ok("OpenAI"):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
                async with s.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_openai()}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini", "max_tokens": max_tokens, "messages": messages},
                ) as r:
                    if r.status == 200:
                        d = await r.json(content_type=None)
                        text = d.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if text:
                            _cb_success("OpenAI")
                            return text
                        # leere 200-Antwort → kein _cb_fail
                    elif r.status == 429:
                        log.debug("OpenAI: Rate-Limit — 120s Pause")
                        _cb_rate_limit("OpenAI", 120)
                    elif r.status in (401, 403):
                        _cb_fail("OpenAI")
                    else:
                        _cb_fail("OpenAI")
        except Exception as e:
            log.debug("OpenAI error: %s", e)
            _cb_fail("OpenAI")

    # ── 7. Perplexity ─────────────────────────────────────────────────────────
    if _perplexity() and _cb_ok("Perplexity"):
        pplx_enabled = os.getenv("PERPLEXITY_ENABLED", "true").lower() not in ("false", "0", "off")
        if pplx_enabled:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(
                        "https://api.perplexity.ai/chat/completions",
                        headers={"Authorization": f"Bearer {_perplexity()}", "Content-Type": "application/json"},
                        json={"model": "sonar", "max_tokens": max(max_tokens, 16), "messages": messages},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = d.get("choices", [{}])[0].get("message", {}).get("content", "")
                            if text:
                                _cb_success("Perplexity")
                                return text
                        elif r.status == 429:
                            _cb_rate_limit("Perplexity", 90)
                        elif r.status in (401, 403):
                            log.warning("Perplexity: Key ungültig (%s) — 24h deaktiviert", r.status)
                            if "Perplexity" not in _CB:
                                _CB["Perplexity"] = {"fails": 0, "until": 0.0, "total_fails": 0, "deactivations": 0}
                            _CB["Perplexity"]["until"] = time.time() + 86400
                        elif r.status == 402:
                            _cb_fail("Perplexity")
                        else:
                            _cb_fail("Perplexity")
            except Exception as e:
                log.debug("Perplexity error: %s", e)
                _cb_fail("Perplexity")

    # ── 8. Cerebras (kostenlos, sehr schnell) ──────────────────────────────────
    if _cerebras() and _cb_ok("Cerebras"):
        for model in _CEREBRAS_MODELS:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(_CEREBRAS_BASE,
                        headers={"Authorization": f"Bearer {_cerebras()}", "Content-Type": "application/json"},
                        json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
                            if text:
                                _cb_success("Cerebras")
                                log.info("APIHunt: Cerebras OK model=%s", model)
                                return text
            except Exception as e:
                log.debug("Cerebras %s: %s", model, e)
        _cb_fail("Cerebras")

    # ── 9. SambaNova (kostenlos) ────────────────────────────────────────────────
    if _sambanova() and _cb_ok("SambaNova"):
        for model in _SAMBANOVA_MODELS:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
                    async with s.post(_SAMBANOVA_BASE,
                        headers={"Authorization": f"Bearer {_sambanova()}", "Content-Type": "application/json"},
                        json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
                            if text:
                                _cb_success("SambaNova")
                                log.info("APIHunt: SambaNova OK model=%s", model)
                                return text
            except Exception as e:
                log.debug("SambaNova %s: %s", model, e)
        _cb_fail("SambaNova")

    # ── 10. Mistral API ─────────────────────────────────────────────────────────
    if _mistral() and _cb_ok("Mistral"):
        for model in _MISTRAL_MODELS:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                    async with s.post(_MISTRAL_BASE,
                        headers={"Authorization": f"Bearer {_mistral()}", "Content-Type": "application/json"},
                        json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7},
                    ) as r:
                        if r.status == 200:
                            d = await r.json(content_type=None)
                            text = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
                            if text:
                                _cb_success("Mistral")
                                log.info("APIHunt: Mistral OK model=%s", model)
                                return text
            except Exception as e:
                log.debug("Mistral %s: %s", model, e)
        _cb_fail("Mistral")

    # ── 11. Ollama (lokal / OpenClaw) ───────────────────────────────────────────
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(
                f"{_ollama_base()}/api/chat",
                json={"model": _ollama_model(), "messages": messages, "stream": False,
                      "options": {"num_predict": max_tokens}},
            ) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    text = d.get("message", {}).get("content", "")
                    if text:
                        _cb_success("Ollama")
                        log.info("APIHunt: Ollama als letzter Ausweg OK")
                        return text
    except Exception as e:
        log.debug("Ollama error: %s", e)

    # ── Alle Provider ausgefallen — Log-Throttling: max 1× alle 5 Minuten ────────
    global _last_all_failed_log
    now = time.time()
    if now - _last_all_failed_log >= 300:
        _last_all_failed_log = now
        log.error("APIHunt: ALLE Provider ausgefallen!")
        asyncio.ensure_future(_alert_all_failed())
        # Notfall: alle CB-States sofort zurücksetzen damit nächster Call Provider neu versucht
        for p in list(_CB.keys()):
            _CB[p]["until"] = 0.0
            _CB[p]["fails"] = 0
        log.warning("APIHunt: CB-Reset erzwungen — alle Provider reaktiviert für nächsten Versuch")
    return ""


# ── Synchroner Wrapper (für Module die kein async haben) ──────────────────────
def ai_complete_sync(prompt: str, system: str = "", max_tokens: int = 800) -> str:
    """Synchroner Wrapper um ai_complete() für nicht-async Module."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, ai_complete(prompt, system, max_tokens=max_tokens))
                return future.result(timeout=45)
        else:
            return loop.run_until_complete(ai_complete(prompt, system, max_tokens=max_tokens))
    except Exception as e:
        log.error("ai_complete_sync error: %s", e)
        return ""


# ── Beim Import: Provider-Status einmalig loggen ───────────────────────────────
def _log_startup_status() -> None:
    providers = [
        ("Groq",       _groq()),
        ("DeepSeek",   _deepseek()),
        ("OpenRouter",  _openrouter()),
        ("Gemini",     _gemini()),
        ("Anthropic",  _anthropic()),
        ("OpenAI",     _openai()),
        ("Perplexity", _perplexity()),
    ]
    available = [name for name, key in providers if key]
    missing   = [name for name, key in providers if not key]
    log.info(
        "APIHunt: %d Provider verfügbar: %s | Fehlende Keys: %s",
        len(available), ", ".join(available) or "keine", ", ".join(missing) or "keine",
    )


_log_startup_status()
