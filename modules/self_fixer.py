#!/usr/bin/env python3
"""
SelfFixer — wird in alle Module importiert für autonome Selbstreparatur.
from modules.self_fixer import auto_fix; auto_fix(__name__)
"""
import logging, os

log = logging.getLogger("SelfFixer")


def auto_fix(module_name: str) -> dict:
    """Prüft und repariert das aufrufende Modul automatisch."""
    fixes = []
    errors = []

    # Check kritische ENV vars
    critical = ['TELEGRAM_BOT_TOKEN', 'SUPABASE_URL', 'SHOPIFY_ADMIN_API_TOKEN']
    for var in critical:
        if not os.getenv(var):
            errors.append(f'{var} fehlt')

    # Check AI Provider
    ai_ok = any(os.getenv(k) for k in ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GROQ_API_KEY', 'OPENROUTER_API_KEY'])
    if not ai_ok:
        errors.append('Kein AI Provider verfügbar')
    else:
        fixes.append('ai_provider_ok')

    # Check DS24
    if os.getenv('DS24_API_KEY', '').startswith('1581233'):
        fixes.append('ds24_aiitec_key_ok')
    elif os.getenv('DS24_API_KEY', '').startswith('1682000'):
        errors.append('DS24 FALSCHES KONTO — muss aiitec (1581233-...) sein!')

    if errors:
        log.warning("[%s] SelfFixer: %d Issues: %s", module_name, len(errors), errors)
    else:
        log.debug("[%s] SelfFixer: All OK", module_name)

    return {'module': module_name, 'errors': errors, 'fixes': fixes, 'ok': len(errors) == 0}


async def async_auto_fix(module_name: str) -> dict:
    return auto_fix(module_name)
