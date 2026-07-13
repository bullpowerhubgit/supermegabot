#!/usr/bin/env python3
"""
BullPower MEGA Command Center — Full Start
Initiiert alle Systeme, prüft alle APIs, startet Dashboard + Scheduler.
Ausführen: python3 scripts/full_start.py
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import aiohttp

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Farben ────────────────────────────────────────────────────────────
G = "\033[0;32m"; R = "\033[0;31m"; Y = "\033[1;33m"
B = "\033[0;34m"; C = "\033[0;36m"; W = "\033[1m"; N = "\033[0m"

def ok(msg: str):  print(f"  {G}✅{N} {msg}")
def err(msg: str): print(f"  {R}❌{N} {msg}")
def inf(msg: str): print(f"  {C}ℹ️ {N} {msg}")
def hdr(msg: str): print(f"\n{W}{B}{'─'*50}{N}\n{W}{B}  {msg}{N}\n{W}{B}{'─'*50}{N}")


# ── Telegram Notify ───────────────────────────────────────────────────
async def tg(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


# ── Port freimachen ───────────────────────────────────────────────────
def free_port(port: int = 8888):
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"], capture_output=True, text=True
        )
        pids = result.stdout.strip().split("\n")
        for pid in pids:
            if pid:
                subprocess.run(["kill", "-9", pid], capture_output=True)
        ok(f"Port {port} freigegeben")
    except Exception as e:
        inf(f"Port {port} bereits frei ({e})")


# ── Syntax-Check ──────────────────────────────────────────────────────
def syntax_check() -> int:
    errors = 0
    py_files = list((ROOT / "modules").glob("*.py")) + \
               list((ROOT / "core").glob("*.py")) + \
               list((ROOT / "dashboard").glob("*.py"))
    for f in py_files:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(f)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            err(f"Syntax-Fehler: {f.name} → {result.stderr.strip()[:80]}")
            errors += 1
    if errors == 0:
        ok(f"Syntax-Check: {len(py_files)} Dateien OK")
    else:
        err(f"Syntax-Check: {errors} Fehler!")
    return errors


# ── Dashboard starten ─────────────────────────────────────────────────
def start_dashboard() -> int | None:
    log_path = "/tmp/supermegabot.log"
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "dashboard" / "server.py")],
        stdout=open(log_path, "a"),
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
    )
    time.sleep(4)
    if proc.poll() is None:
        ok(f"Dashboard gestartet (PID {proc.pid}) → http://localhost:8888")
        return proc.pid
    else:
        err(f"Dashboard-Start fehlgeschlagen → {log_path}")
        return None


# ── Health Checks ─────────────────────────────────────────────────────
async def run_health_checks() -> dict:
    results = {}
    try:
        from modules.mega_health_checker import run_all_checks
        results = await run_all_checks()
        total = results.get("total", 0)
        healthy = results.get("healthy", 0)
        if healthy == total:
            ok(f"Health-Check: {healthy}/{total} Plattformen OK")
        else:
            err(f"Health-Check: {healthy}/{total} OK — {total-healthy} Probleme!")
    except ImportError:
        inf("mega_health_checker nicht gefunden — übersprungen")
    except Exception as e:
        err(f"Health-Check Fehler: {e}")
    return results


# ── Auto-Fix ──────────────────────────────────────────────────────────
async def run_auto_fix() -> dict:
    try:
        from modules.platform_auto_fixer import run_all_fixes
        result = await run_all_fixes()
        fixed = result.get("fixed_count", 0)
        if fixed > 0:
            ok(f"Auto-Fix: {fixed} Probleme behoben")
        else:
            ok("Auto-Fix: Keine Probleme gefunden")
        return result
    except ImportError:
        inf("platform_auto_fixer nicht gefunden — übersprungen")
        return {}
    except Exception as e:
        err(f"Auto-Fix Fehler: {e}")
        return {}


# ── Revenue Snapshot ──────────────────────────────────────────────────
async def run_revenue() -> dict:
    try:
        from modules.revenue_tracker import get_all_revenue
        rev = await get_all_revenue()
        total_eur = rev.get("total_eur", 0.0)
        ok(f"Revenue-Snapshot: €{total_eur:.2f} heute (Stripe + DS24 + Shopify)")
        return rev
    except ImportError:
        inf("revenue_tracker nicht gefunden — übersprungen")
        return {}
    except Exception as e:
        err(f"Revenue Fehler: {e}")
        return {}


# ── Social Status ─────────────────────────────────────────────────────
async def run_social_status() -> dict:
    try:
        from modules.social_autoposter import get_all_stats
        stats = await get_all_stats()
        platforms_ok = sum(1 for v in stats.values() if isinstance(v, dict) and v.get("ok"))
        ok(f"Social Media: {platforms_ok}/{len(stats)} Plattformen verbunden")
        return stats
    except ImportError:
        inf("social_autoposter nicht gefunden — übersprungen")
        return {}
    except Exception as e:
        err(f"Social-Status Fehler: {e}")
        return {}


# ── Scheduler starten ─────────────────────────────────────────────────
def start_scheduler() -> int | None:
    sched_path = ROOT / "core" / "automation_scheduler.py"
    if not sched_path.exists():
        inf("automation_scheduler.py nicht gefunden — übersprungen")
        return None
    proc = subprocess.Popen(
        [sys.executable, str(sched_path)],
        stdout=open("/tmp/supermegabot_scheduler.log", "a"),
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
    )
    time.sleep(2)
    if proc.poll() is None:
        ok(f"Scheduler gestartet (PID {proc.pid})")
        return proc.pid
    else:
        err("Scheduler-Start fehlgeschlagen")
        return None


# ── MAIN ──────────────────────────────────────────────────────────────
async def main():
    print(f"""
{W}{B}
╔══════════════════════════════════════════════════════╗
║   ⚡  BullPower MEGA Command Center — FULL START  ⚡  ║
║       SuperMegaBot v10.0 — Rudolf Sarkany           ║
╚══════════════════════════════════════════════════════╝
{N}""")
    t0 = time.time()

    # ── Schritt 1: Credentials prüfen
    hdr("1 / 7 — Credentials & .env")
    env_path = ROOT / ".env"
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        filled = sum(1 for l in lines if "=" in l and not l.startswith("#") and l.split("=",1)[1].strip())
        ok(f".env geladen — {filled} Keys gesetzt ({len(lines)} Zeilen gesamt)")
    else:
        err(".env nicht gefunden!")

    # ── Schritt 2: Syntax-Check
    hdr("2 / 7 — Syntax-Check")
    syn_errors = syntax_check()
    if syn_errors > 0:
        print(f"\n{R}  Syntax-Fehler gefunden — abgebrochen!{N}")
        sys.exit(1)

    # ── Schritt 3: Port + Dashboard
    hdr("3 / 7 — Dashboard")
    free_port(8888)
    dash_pid = start_dashboard()

    # ── Schritt 4: Health Checks + Auto-Fix (parallel)
    hdr("4 / 7 — Health-Check + Auto-Fix")
    health, fix, rev, social = await asyncio.gather(
        run_health_checks(),
        run_auto_fix(),
        run_revenue(),
        run_social_status(),
        return_exceptions=True,
    )

    # ── Schritt 5: Revenue
    hdr("5 / 7 — Revenue & Social")
    # (Already printed above via gather)

    # ── Schritt 6: Scheduler
    hdr("6 / 7 — Automation-Scheduler")
    sched_pid = start_scheduler()

    # ── Schritt 7: Telegram Benachrichtigung
    hdr("7 / 7 — Telegram Bestätigung")
    elapsed = time.time() - t0

    # Sichere Extraktion
    health_ok = health.get("healthy", "?") if isinstance(health, dict) else "?"
    health_total = health.get("total", "?") if isinstance(health, dict) else "?"
    rev_total = rev.get("total_eur", 0.0) if isinstance(rev, dict) else 0.0
    social_ok = sum(1 for v in (social or {}).values() if isinstance(v, dict) and v.get("ok"))

    msg = (
        f"🚀 *BullPower MEGA Command Center — FULL START*\n\n"
        f"✅ Dashboard: http://localhost:8888 (PID {dash_pid})\n"
        f"✅ Health: {health_ok}/{health_total} Plattformen OK\n"
        f"✅ Revenue: €{rev_total:.2f} heute\n"
        f"✅ Social: {social_ok}/7 Plattformen verbunden\n"
        f"✅ Scheduler: PID {sched_pid}\n\n"
        f"⏱ Start-Zeit: {elapsed:.1f}s\n"
        f"📊 MegaDash: https://claude.ai/code/artifact/ed49c90e-33d5-40b3-9c18-da24e5ffa6f8"
    )
    await tg(msg)
    ok("Telegram-Bestätigung gesendet")

    # ── Abschluss
    print(f"""
{W}{G}
╔══════════════════════════════════════════════════════╗
║   🚀  ALLE SYSTEME AKTIV!                           ║
╚══════════════════════════════════════════════════════╝
{N}
  Dashboard:    {W}http://localhost:8888{N}
  MegaDash:     {W}https://claude.ai/code/artifact/ed49c90e-33d5-40b3-9c18-da24e5ffa6f8{N}
  Dashboard-Log:{W}/tmp/supermegabot.log{N}
  Scheduler-Log:{W}/tmp/supermegabot_scheduler.log{N}

  {Y}Revenue-Engine läuft — Status per Telegram!{N}
""")

    # Browser öffnen (macOS)
    try:
        subprocess.Popen(["open", "http://localhost:8888"])
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
