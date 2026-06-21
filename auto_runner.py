#!/usr/bin/env python3
"""
SuperMegaBot Local Auto-Runner — läuft auf dem Mac, wenn Railway offline ist.
Startet mit: python3 auto_runner.py
Läuft endlos und triggert alle Revenue-Engines alle 6 Stunden.
"""
import asyncio, logging, os, sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
log = logging.getLogger("AutoRunner")

INTERVAL_MINUTES = 360  # alle 6 Stunden


async def run_cycle():
    log.info("=== AutoRunner Zyklus gestartet ===")
    results = {}

    # 1. DS24 Affiliate Blast
    try:
        from modules.ds24_affiliate_blaster import blast_own_products
        r = await blast_own_products(limit=20)
        results['ds24_blast'] = r
        log.info("DS24 Blast: %s", r)
    except Exception as e:
        log.error("DS24 Blast Fehler: %s", e)

    # 2. BrutusCore fire — Traffic auf alle Kanäle
    try:
        from modules.brutus_core import fire_from_brutus
        r = await fire_from_brutus()
        results['brutus'] = 'ok'
        log.info("BrutusCore: OK")
    except Exception as e:
        log.error("BrutusCore Fehler: %s", e)

    # 3. Selbstverbesserung
    try:
        from modules.selbstverbesserung import run_platform_check
        r = await run_platform_check()
        results['selbst'] = r
        log.info("Selbstverbesserung: %s Plattformen", r.get('platforms_checked', '?'))
    except Exception as e:
        log.error("Selbstverbesserung Fehler: %s", e)

    # 4. Quantum Self-Fix
    try:
        from modules.quantum_self_fixer import run_full_scan
        r = await run_full_scan()
        results['quantum'] = {'errors': r.get('total_errors', 0), 'fixed': r.get('total_fixed', 0)}
        log.info("QuantumSelfFix: %s", results['quantum'])
    except Exception as e:
        log.error("QuantumSelfFix Fehler: %s", e)

    # 5. Printify neue Produkte erstellen
    try:
        from modules.printify_autonomy import run_printify_cycle
        r = await run_printify_cycle()
        results['printify'] = r
        log.info("Printify: %s", r)
    except Exception as e:
        log.error("Printify Fehler: %s", e)

    # 6. Telegram Zusammenfassung
    try:
        import aiohttp
        msg = f"AutoRunner Zyklus {datetime.now().strftime('%d.%m %H:%M')}\n"
        for k, v in results.items():
            ok = v.get('ok', True) if isinstance(v, dict) else True
            icon = "OK" if ok else "ERR"
            msg += f"  [{icon}] {k}\n"
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN', '8600739487:AAGhByAoKEpbsfco9swoaRYjU2HI_gSt718')}/sendMessage",
                json={'chat_id': os.getenv('TELEGRAM_CHAT_ID', '5088771245'), 'text': msg},
                timeout=aiohttp.ClientTimeout(total=15)
            )
        log.info("Telegram Report gesendet")
    except Exception as e:
        log.error("Telegram Report: %s", e)

    return results


async def main():
    log.info("SuperMegaBot AutoRunner gestartet — alle %d Minuten", INTERVAL_MINUTES)
    while True:
        try:
            await run_cycle()
        except Exception as e:
            log.error("Zyklus-Fehler: %s", e)
        log.info("Naechster Zyklus in %d Minuten...", INTERVAL_MINUTES)
        await asyncio.sleep(INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    asyncio.run(main())
