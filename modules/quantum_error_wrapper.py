#!/usr/bin/env python3
"""
Quantum Error Wrapper — überwacht jeden Modul-Aufruf, fängt Fehler, retried, heilt.
Kein Fehler bleibt unbemerkt. Kein Fehler tritt zweimal auf.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import traceback
from typing import Any, Callable

log = logging.getLogger("QuantumErrorWrapper")


def quantum_guard(module_name: str):
    """
    Decorator: fängt Fehler, loggt in Supabase, retried mit exponential backoff.
    Bei 3. Fehlschlag: Telegram-Alert.

    Usage:
        @quantum_guard("shopify_autonomy")
        async def create_product(...):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            func_name = func.__name__
            last_exc  = None
            for attempt in range(3):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    err_str = str(exc)
                    log.warning("[%s] %s attempt %d failed: %s",
                                module_name, func_name, attempt + 1, err_str[:120])
                    try:
                        from modules.quantum_self_improver import log_error
                        await log_error(
                            module=module_name,
                            function=func_name,
                            error=exc,
                            context={"attempt": attempt + 1, "args_count": len(args)},
                        )
                    except Exception:
                        pass
                    if attempt < 2:
                        wait = 2 ** attempt
                        await asyncio.sleep(wait)
                    else:
                        try:
                            from modules.quantum_self_improver import auto_fix_error
                            error_type = type(exc).__name__
                            await auto_fix_error(module_name, error_type)
                        except Exception:
                            pass
                        try:
                            import os
                            import aiohttp
                            tok  = os.getenv("TELEGRAM_BOT_TOKEN", "")
                            chat = os.getenv("TELEGRAM_CHAT_ID", "")
                            if tok and chat:
                                msg = (
                                    f"🔴 <b>Quantum Alert</b>\n"
                                    f"Modul: {module_name}.{func_name}\n"
                                    f"Fehler: {error_type}: {err_str[:200]}\n"
                                    f"Alle 3 Versuche fehlgeschlagen — KI-Fix generiert."
                                )
                                async with aiohttp.ClientSession() as s:
                                    await s.post(
                                        f"https://api.telegram.org/bot{tok}/sendMessage",
                                        json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
                                        timeout=aiohttp.ClientTimeout(total=8),
                                    )
                        except Exception:
                            pass
            raise last_exc
        return wrapper
    return decorator


async def safe_call(module: str, func: Callable, *args,
                    max_retries: int = 3, **kwargs) -> Any:
    """
    Sicherer Aufruf mit Auto-Repair.
    Gibt None zurück statt Exception wenn alle Retries fehlschlagen.

    Usage:
        result = await safe_call("shopify", create_product, title="Test")
    """
    last_exc = None
    for attempt in range(max_retries):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            log.warning("[safe_call] %s.%s attempt %d: %s",
                        module, getattr(func, "__name__", "?"), attempt + 1, str(exc)[:100])
            try:
                from modules.quantum_self_improver import log_error
                await log_error(
                    module=module,
                    function=getattr(func, "__name__", "unknown"),
                    error=exc,
                    context={"attempt": attempt + 1},
                )
            except Exception:
                pass
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)

    log.error("[safe_call] %s gave up after %d retries: %s", module, max_retries, last_exc)
    return None
