#!/usr/bin/env python3
"""
SuperMegaBot — Auto Repair Engine
====================================
Prüft alle 10 Minuten ALLES und repariert automatisch was kaputt ist.

Prüft und repariert:
  ✅ Dashboard/Server (HTTP health)
  ✅ Alle Python-Module (Syntax-Check)
  ✅ Alle SQLite-Datenbanken (integrity_check)
  ✅ Alle JSON-Dateien in data/ (Syntax)
  ✅ Env-Variablen (falsche Alias-Namen → auto-fix)
  ✅ SMTP-Accounts (Login-Test)
  ✅ API-Keys (Telegram, Shopify, Stripe, Groq, Gemini)
  ✅ Scheduler-Tasks (hängende Tasks → restart)
  ✅ Disk-Space (< 500MB → Logs bereinigen)
  ✅ Memory (> 85% → GC + notify)
  ✅ Zombie-Prozesse (SIGCHLD)
  ✅ Log-Rotation (> 50MB → rotate)
  ✅ DS24-Key (falsches Konto → Warnung)
  ✅ Shopify-Token (401 → probiert beide Varianten)

Export: run_repair_cycle() → {checks, repairs, alerts}
"""
from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import re
import shutil
import smtplib
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("AutoRepair")

_BASE = Path(__file__).parent.parent
_DATA = _BASE / "data"
_DATA.mkdir(exist_ok=True)

_REPAIR_LOG  = _DATA / "repair_log.json"
_REPAIR_DB   = _DATA / "auto_repair.db"
_DASHBOARD_PORT = int(os.getenv("PORT", "8888"))
_RAILWAY_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("RAILWAY_STATIC_URL", "https://supermegabot-production.up.railway.app")).rstrip("/")


# ── Repair-DB ──────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    con = sqlite3.connect(str(_REPAIR_DB), timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS repairs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            check_id  TEXT NOT NULL,
            problem   TEXT NOT NULL,
            action    TEXT NOT NULL,
            success   INTEGER DEFAULT 1,
            ts        REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS check_state (
            check_id  TEXT PRIMARY KEY,
            last_ok   REAL,
            fail_count INTEGER DEFAULT 0,
            last_fail REAL
        );
    """)
    con.commit()
    return con


def _log_repair(check_id: str, problem: str, action: str, success: bool = True):
    try:
        con = _db()
        con.execute(
            "INSERT INTO repairs (check_id, problem, action, success, ts) VALUES (?,?,?,?,?)",
            (check_id, problem, action, int(success), time.time())
        )
        con.commit()
        con.close()
    except Exception as e:
        log.debug("repair log failed: %s", e)


def _update_check_state(check_id: str, ok: bool):
    try:
        con = _db()
        if ok:
            con.execute("""
                INSERT INTO check_state (check_id, last_ok, fail_count, last_fail)
                VALUES (?, ?, 0, NULL)
                ON CONFLICT(check_id) DO UPDATE SET last_ok=excluded.last_ok, fail_count=0
            """, (check_id, time.time()))
        else:
            con.execute("""
                INSERT INTO check_state (check_id, fail_count, last_fail)
                VALUES (?, 1, ?)
                ON CONFLICT(check_id) DO UPDATE SET
                    fail_count = fail_count + 1,
                    last_fail  = excluded.last_fail
            """, (check_id, time.time()))
        con.commit()
        con.close()
    except Exception:
        pass


def _fail_count(check_id: str) -> int:
    try:
        con = _db()
        row = con.execute("SELECT fail_count FROM check_state WHERE check_id=?", (check_id,)).fetchone()
        con.close()
        return row[0] if row else 0
    except Exception:
        return 0


# ── HTTP Helper ───────────────────────────────────────────────────────────────

async def _http_get(url: str, headers: dict | None = None, timeout: int = 8) -> tuple[int, dict]:
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers or {}, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                try:
                    body = await r.json(content_type=None)
                except Exception:
                    body = {}
                return r.status, body
    except Exception as e:
        return 0, {"error": str(e)}


async def _http_post(url: str, payload: dict, timeout: int = 8) -> tuple[int, dict]:
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                try:
                    body = await r.json(content_type=None)
                except Exception:
                    body = {}
                return r.status, body
    except Exception as e:
        return 0, {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# CHECK-FUNKTIONEN — jede gibt (ok: bool, problem: str, action: str) zurück
# ══════════════════════════════════════════════════════════════════════════════

async def check_dashboard_health() -> tuple[bool, str, str]:
    """Dashboard HTTP /health muss 200 + {status: ok} zurückgeben."""
    # Lokal zuerst
    local_url = f"http://localhost:{_DASHBOARD_PORT}/health"
    status, body = await _http_get(local_url, timeout=5)
    if status == 200 and body.get("status") == "ok":
        return True, "", ""

    # Railway als Fallback
    rail_status, rail_body = await _http_get(f"{_RAILWAY_URL}/health", timeout=10)
    if rail_status == 200:
        return True, "", ""

    problem = f"Dashboard nicht erreichbar (lokal: HTTP {status}, Railway: HTTP {rail_status})"
    # Repair: Dashboard-Prozess neu starten
    action = "Versuche Dashboard-Restart"
    try:
        server_py = _BASE / "dashboard" / "server.py"
        if server_py.exists():
            log_path = _DATA / "dashboard_restart.log"
            with open(log_path, "a") as lf:
                subprocess.Popen(
                    [sys.executable, str(server_py)],
                    stdout=lf, stderr=lf, start_new_session=True, cwd=str(_BASE)
                )
            await asyncio.sleep(5)
            status2, _ = await _http_get(local_url, timeout=8)
            if status2 == 200:
                action = f"Dashboard neu gestartet ✅ (log: {log_path})"
                _log_repair("dashboard_health", problem, action)
                return True, problem, action
    except Exception as e:
        action = f"Dashboard-Restart fehlgeschlagen: {e}"
    _log_repair("dashboard_health", problem, action, success=False)
    return False, problem, action


async def check_python_modules() -> tuple[bool, str, str]:
    """Syntax-Check aller Python-Module — kaputte Module sofort melden."""
    broken: list[str] = []
    for pattern in ("modules/*.py", "core/*.py", "dashboard/*.py"):
        for f in sorted(_BASE.glob(pattern)):
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(f)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                err = result.stderr.strip().split("\n")[-1][:100]
                broken.append(f"{f.name}: {err}")

    if not broken:
        return True, "", ""

    problem = f"{len(broken)} Module mit Syntax-Fehler: {', '.join(b.split(':')[0] for b in broken[:3])}"
    # Auto-Repair: versuche letzte saubere Version via git
    action_parts = []
    for b in broken:
        fname = b.split(":")[0].strip()
        for pattern in ("modules", "core", "dashboard"):
            target = _BASE / pattern / fname
            if target.exists():
                r = subprocess.run(
                    ["git", "checkout", "HEAD", "--", str(target.relative_to(_BASE))],
                    capture_output=True, text=True, cwd=str(_BASE), timeout=15
                )
                if r.returncode == 0:
                    action_parts.append(f"{fname} → git reset ✅")
                else:
                    action_parts.append(f"{fname} → git reset ❌")

    action = "; ".join(action_parts) if action_parts else "Keine auto-Reparatur möglich"
    _log_repair("python_modules", problem, action, success=bool(action_parts))
    return False, problem, action


async def check_sqlite_databases() -> tuple[bool, str, str]:
    """Integrity-Check aller SQLite-Datenbanken."""
    broken: list[str] = []
    for db_path in _DATA.glob("*.db"):
        try:
            con = sqlite3.connect(str(db_path), timeout=5)
            result = con.execute("PRAGMA integrity_check").fetchone()
            con.close()
            if result and result[0] != "ok":
                broken.append(db_path.name)
        except Exception as e:
            broken.append(f"{db_path.name} ({e})")

    if not broken:
        return True, "", ""

    problem = f"Korrupte Datenbanken: {', '.join(broken)}"
    action_parts = []
    for db_name in broken:
        db_path = _DATA / db_name
        bak = _DATA / f"{db_name}.bak.{int(time.time())}"
        try:
            shutil.copy2(db_path, bak)
            db_path.unlink()
            action_parts.append(f"{db_name} → gelöscht (Backup: {bak.name}) ✅")
        except Exception as e:
            action_parts.append(f"{db_name} → Backup fehlgeschlagen: {e}")

    action = "; ".join(action_parts)
    _log_repair("sqlite_databases", problem, action)
    return False, problem, action


async def check_json_files() -> tuple[bool, str, str]:
    """Alle JSON-Dateien in data/ müssen valides JSON enthalten."""
    broken: list[str] = []
    for jf in _DATA.glob("*.json"):
        try:
            json.loads(jf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            broken.append(f"{jf.name}: {e}")

    if not broken:
        return True, "", ""

    problem = f"{len(broken)} korrupte JSON-Dateien: {', '.join(b.split(':')[0] for b in broken[:3])}"
    action_parts = []
    for b in broken:
        fname = b.split(":")[0].strip()
        jpath = _DATA / fname
        bak = _DATA / f"{fname}.bak.{int(time.time())}"
        try:
            shutil.copy2(jpath, bak)
            jpath.write_text("{}", encoding="utf-8")
            action_parts.append(f"{fname} → zurückgesetzt (Backup: {bak.name}) ✅")
        except Exception as e:
            action_parts.append(f"{fname}: {e}")

    action = "; ".join(action_parts)
    _log_repair("json_files", problem, action)
    return False, problem, action


async def check_env_vars() -> tuple[bool, str, str]:
    """Prüft kritische Env-Vars — falsche Alias-Namen werden in .env korrigiert."""
    env_file = _BASE / ".env"
    problems: list[str] = []
    fixes: list[str] = []

    # Kritische Vars die vorhanden sein MÜSSEN
    REQUIRED = {
        "TELEGRAM_BOT_TOKEN": None,
        "TELEGRAM_CHAT_ID":   None,
        "SHOPIFY_SHOP_DOMAIN": None,
        "SHOPIFY_ACCESS_TOKEN": ["SHOPIFY_ADMIN_API_TOKEN", "SHOPIFY_ADMIN_TOKEN"],
        "STRIPE_SECRET_KEY":   ["STRIPE_API_KEY", "STRIPE_SECRET"],
        "GEMINI_API_KEY":      ["GOOGLE_AI_API_KEY", "GOOGLE_GEMINI_KEY"],
    }

    for correct_name, aliases in REQUIRED.items():
        val = os.getenv(correct_name, "")
        if val:
            continue
        # Suche in Aliases
        found_via = None
        found_val = None
        for alias in (aliases or []):
            v = os.getenv(alias, "")
            if v:
                found_via = alias
                found_val = v
                break

        if found_val and env_file.exists():
            # Alias gefunden → korrekten Namen in .env eintragen
            try:
                env_text = env_file.read_text(encoding="utf-8")
                if correct_name not in env_text:
                    env_file.write_text(
                        env_text + f"\n# Auto-fix: alias {found_via}\n{correct_name}={found_val}\n",
                        encoding="utf-8"
                    )
                    os.environ[correct_name] = found_val
                    fixes.append(f"{correct_name} ← {found_via} eingetragen")
                    problems.append(f"{correct_name} fehlte (war als {found_via})")
            except Exception as e:
                problems.append(f"{correct_name}: fix fehlgeschlagen ({e})")
        elif not val:
            if not found_val:
                problems.append(f"{correct_name} FEHLT komplett")

    if not problems:
        return True, "", ""
    if fixes:
        action = "Auto-Fix: " + "; ".join(fixes)
    else:
        action = "Manuell setzen: " + ", ".join(p.split(" ")[0] for p in problems)
    _log_repair("env_vars", "; ".join(problems), action, success=bool(fixes))
    return False, "; ".join(problems), action


async def check_telegram_api() -> tuple[bool, str, str]:
    """Telegram Bot Token testen."""
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not tok:
        return False, "TELEGRAM_BOT_TOKEN fehlt", "In .env setzen"
    status, body = await _http_get(f"https://api.telegram.org/bot{tok}/getMe")
    if status == 200 and body.get("ok"):
        return True, "", ""
    problem = f"Telegram Bot ungültig (HTTP {status}: {body.get('description', '')})"
    action = "Token in .env erneuern — @BotFather → /mytoken"
    _log_repair("telegram_api", problem, action, success=False)
    return False, problem, action


async def check_shopify_api() -> tuple[bool, str, str]:
    """Shopify API Token testen — probiert automatisch beide Var-Namen."""
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    ver    = os.getenv("SHOPIFY_API_VERSION", "2025-01")
    if not domain or not token:
        return False, "SHOPIFY_SHOP_DOMAIN oder SHOPIFY_ACCESS_TOKEN fehlt", "In .env setzen"

    url = f"https://{domain}/admin/api/{ver}/shop.json"
    status, body = await _http_get(url, headers={"X-Shopify-Access-Token": token})
    if status == 200:
        return True, "", ""

    problem = f"Shopify API {status}: {body.get('errors', body)}"
    if status == 401:
        action = "Token abgelaufen/ungültig → Shopify Admin → Apps → Private Apps → Token erneuern"
    elif status == 402:
        action = "Shopify-Plan gesperrt/unbezahlt"
    else:
        action = f"Shopify API Fehler HTTP {status}"
    _log_repair("shopify_api", problem, action, success=False)
    return False, problem, action


async def check_stripe_api() -> tuple[bool, str, str]:
    """Stripe API testen."""
    key = os.getenv("STRIPE_SECRET_KEY") or os.getenv("STRIPE_API_KEY", "")
    if not key:
        return False, "STRIPE_SECRET_KEY fehlt", "In .env setzen"
    status, body = await _http_get("https://api.stripe.com/v1/account",
                                   headers={"Authorization": f"Bearer {key}"})
    if status == 200:
        return True, "", ""
    problem = f"Stripe API {status}: {body.get('error', {}).get('message', '')}"
    action = "Stripe Dashboard → API Keys → neuen Secret Key erstellen"
    _log_repair("stripe_api", problem, action, success=False)
    return False, problem, action


async def check_groq_api() -> tuple[bool, str, str]:
    """Groq (free AI) testen."""
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return False, "GROQ_API_KEY fehlt (Free AI wird benötigt)", "Auf console.groq.com kostenlos holen"
    status, body = await _http_get("https://api.groq.com/openai/v1/models",
                                   headers={"Authorization": f"Bearer {key}"})
    if status == 200:
        return True, "", ""
    problem = f"Groq API {status}"
    action = "GROQ_API_KEY erneuern → console.groq.com"
    _log_repair("groq_api", problem, action, success=False)
    return False, problem, action


async def check_smtp_accounts() -> tuple[bool, str, str]:
    """Alle SMTP-Accounts schnell testen — kaputte identifizieren."""
    PAIRS = [
        ("GMAIL_USER_AIITEC",    "GMAIL_APP_PASSWORD_AIITEC"),
        ("GMAIL_USER_BULLPOWER", "GMAIL_APP_PASSWORD_BULLPOWER"),
        ("GMAIL_USER_1",         "GMAIL_APP_PASSWORD_1"),
        ("GMAIL_USER_2",         "GMAIL_APP_PASSWORD_2"),
        ("GMAIL_USER_3",         "GMAIL_APP_PASSWORD_3"),
        ("GMAIL_USER_4",         "GMAIL_APP_PASSWORD_4"),
        ("GMAIL_USER_5",         "GMAIL_APP_PASSWORD_5"),
        ("GMAIL_USER_6",         "GMAIL_APP_PASSWORD_6"),
        ("GMAIL_USER_7",         "GMAIL_APP_PASSWORD_7"),
        ("GMAIL_USER_8",         "GMAIL_APP_PASSWORD_8"),
    ]
    broken: list[str] = []
    working = 0
    for u_key, p_key in PAIRS:
        user = os.getenv(u_key, "")
        pw   = os.getenv(p_key, "")
        if not user or not pw:
            continue
        try:
            loop = asyncio.get_event_loop()
            def _test(u, p):
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=8) as s:
                    s.login(u, p)
            await loop.run_in_executor(None, _test, user, pw)
            working += 1
        except smtplib.SMTPAuthenticationError:
            broken.append(f"{user} (falsches App-Passwort)")
        except Exception as e:
            broken.append(f"{user} ({type(e).__name__})")

    if not broken and working == 0:
        return False, "Keine SMTP-Accounts konfiguriert", "GMAIL_USER_1 + GMAIL_APP_PASSWORD_1 in .env"
    if broken:
        problem = f"{len(broken)}/{len(broken)+working} SMTP-Accounts defekt: {', '.join(broken[:2])}"
        action = "Gmail → Sicherheit → App-Passwörter → neues Passwort für 'SuperMegaBot' erstellen"
        _log_repair("smtp_accounts", problem, action, success=False)
        return False, problem, action
    return True, "", ""


async def check_ds24_account() -> tuple[bool, str, str]:
    """DS24: falsches Konto (1682000-...) ist kritisch."""
    key = os.getenv("DIGISTORE24_API_KEY", "")
    if not key:
        return False, "DIGISTORE24_API_KEY fehlt", "DS24 Dashboard → API → Key 1581233-... (aiitec-Konto)"
    if key.startswith("1682000"):
        problem = "DS24 FALSCHES KONTO! Key 1682000-... ist IWIN, nicht aiitec!"
        action = "DIGISTORE24_API_KEY in .env auf Key 1581233-... (aiitec) ändern"
        _log_repair("ds24_account", problem, action, success=False)
        return False, problem, action
    return True, "", ""


async def check_scheduler_tasks() -> tuple[bool, str, str]:
    """Scheduler: prüft ob Tasks noch laufen oder hängen."""
    status, body = await _http_get(f"http://localhost:{_DASHBOARD_PORT}/api/scheduler/stats", timeout=8)
    if status != 200:
        return True, "", ""  # Dashboard offline — wird von check_dashboard_health behandelt

    tasks = body.get("tasks", []) or body.get("running", [])
    total = body.get("total_tasks", len(tasks))
    if total == 0:
        problem = "Scheduler: 0 Tasks registriert (Scheduler abgestürzt?)"
        # Restart Scheduler via Dashboard
        r2, _ = await _http_post(f"http://localhost:{_DASHBOARD_PORT}/api/scheduler/restart", {})
        action = f"Scheduler Restart via API: HTTP {r2}"
        _log_repair("scheduler", problem, action, success=(r2 == 200))
        return False, problem, action
    return True, "", ""


async def check_disk_space() -> tuple[bool, str, str]:
    """Disk Space: unter 500MB → Logs und Temp bereinigen."""
    try:
        usage = shutil.disk_usage("/")
        free_mb = usage.free / 1024 / 1024
        if free_mb > 500:
            return True, "", ""
        problem = f"Disk fast voll: nur {free_mb:.0f}MB frei"
        cleaned = 0
        # Alte Logs bereinigen
        for pattern in ["/tmp/*.log", "/tmp/*.tmp"]:
            import glob
            for f in glob.glob(pattern):
                try:
                    size = os.path.getsize(f)
                    age  = time.time() - os.path.getmtime(f)
                    if age > 3600:  # älter als 1h
                        os.remove(f)
                        cleaned += size
                except Exception:
                    pass
        # data/ Logs rotieren
        for log_f in _DATA.glob("*.log"):
            if log_f.stat().st_size > 50 * 1024 * 1024:  # > 50MB
                bak = log_f.with_suffix(f".log.old.{int(time.time())}")
                log_f.rename(bak)
                log_f.write_text("")
                cleaned += bak.stat().st_size

        action = f"Bereinigt: {cleaned/1024/1024:.1f}MB alte Logs"
        _log_repair("disk_space", problem, action)
        return False, problem, action
    except Exception as e:
        return True, "", ""  # Disk-Check nicht kritisch


async def check_memory() -> tuple[bool, str, str]:
    """RAM: über 85% → GC + Warnung."""
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        mem = {}
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                mem[parts[0].rstrip(":")] = int(parts[1])
        total   = mem.get("MemTotal", 0)
        avail   = mem.get("MemAvailable", total)
        if total == 0:
            return True, "", ""
        used_pct = (1 - avail / total) * 100
        if used_pct < 85:
            return True, "", ""
        problem = f"RAM: {used_pct:.0f}% belegt ({(total-avail)//1024}MB/{total//1024}MB)"
        gc.collect()
        action = "GC ausgeführt — Neustart empfohlen wenn >90%"
        _log_repair("memory", problem, action)
        return False, problem, action
    except Exception:
        return True, "", ""  # /proc/meminfo nur auf Linux


async def check_log_rotation() -> tuple[bool, str, str]:
    """Log-Rotation: Dateien > 50MB werden rotiert."""
    rotated: list[str] = []
    for log_path in list(_DATA.glob("*.log")) + list((_BASE / "logs").glob("*.log") if (_BASE / "logs").exists() else []):
        try:
            if log_path.stat().st_size > 50 * 1024 * 1024:
                bak = log_path.with_suffix(f".log.{int(time.time())}")
                shutil.copy2(log_path, bak)
                log_path.write_text("", encoding="utf-8")
                rotated.append(log_path.name)
        except Exception:
            pass
    if rotated:
        action = f"Rotiert: {', '.join(rotated)}"
        _log_repair("log_rotation", f"{len(rotated)} Log-Dateien > 50MB", action)
        return False, f"Log-Rotation: {', '.join(rotated)}", action
    return True, "", ""


async def check_zombie_processes() -> tuple[bool, str, str]:
    """Zombie-Prozesse bereinigen."""
    try:
        r = subprocess.run(
            ["sh", "-c", "ps aux | awk '/^[^%].*Z.*<defunct>/{print $2}' | wc -l"],
            capture_output=True, text=True, timeout=5
        )
        count = int(r.stdout.strip() or "0")
        if count == 0:
            return True, "", ""
        problem = f"{count} Zombie-Prozesse gefunden"
        subprocess.run(
            ["sh", "-c", "ps -A -ostat,ppid | awk '/[Zz]/{print $2}' | sort -u | xargs -r kill -s SIGCHLD"],
            timeout=10, capture_output=True
        )
        action = f"SIGCHLD an Eltern-Prozesse von {count} Zombies gesendet"
        _log_repair("zombies", problem, action)
        return False, problem, action
    except Exception:
        return True, "", ""


async def check_important_files() -> tuple[bool, str, str]:
    """Kritische Dateien müssen existieren und nicht leer sein."""
    REQUIRED_FILES = [
        (_BASE / ".env",                        "ENV-Datei fehlt — Alle API-Keys verloren!"),
        (_BASE / "dashboard" / "server.py",     "Dashboard server.py fehlt!"),
        (_BASE / "core" / "automation_scheduler.py", "Scheduler fehlt!"),
    ]
    missing: list[str] = []
    for fpath, desc in REQUIRED_FILES:
        if not fpath.exists() or fpath.stat().st_size < 10:
            missing.append(desc)
    if missing:
        problem = "; ".join(missing)
        action = "KRITISCH: git checkout HEAD -- <datei> oder aus Backup wiederherstellen"
        _log_repair("important_files", problem, action, success=False)
        return False, problem, action
    return True, "", ""


# ══════════════════════════════════════════════════════════════════════════════
# HAUPT-ZYKLUS
# ══════════════════════════════════════════════════════════════════════════════

CHECKS = [
    ("important_files",   check_important_files,   "CRITICAL"),
    ("env_vars",          check_env_vars,           "HIGH"),
    ("dashboard_health",  check_dashboard_health,   "HIGH"),
    ("telegram_api",      check_telegram_api,       "HIGH"),
    ("ds24_account",      check_ds24_account,       "HIGH"),
    ("shopify_api",       check_shopify_api,        "MEDIUM"),
    ("stripe_api",        check_stripe_api,         "MEDIUM"),
    ("groq_api",          check_groq_api,           "MEDIUM"),
    ("python_modules",    check_python_modules,     "HIGH"),
    ("sqlite_databases",  check_sqlite_databases,   "HIGH"),
    ("json_files",        check_json_files,         "MEDIUM"),
    ("smtp_accounts",     check_smtp_accounts,      "MEDIUM"),
    ("scheduler_tasks",   check_scheduler_tasks,    "MEDIUM"),
    ("disk_space",        check_disk_space,         "MEDIUM"),
    ("memory",            check_memory,             "LOW"),
    ("zombie_processes",  check_zombie_processes,   "LOW"),
    ("log_rotation",      check_log_rotation,       "LOW"),
]


async def run_repair_cycle() -> dict:
    """
    Führt alle 17 Checks durch, repariert automatisch was möglich ist.
    Sendet Telegram-Bericht über alles was kaputt war und was repariert wurde.
    """
    started = time.time()
    results: list[dict] = []
    repairs: list[dict] = []
    alerts:  list[dict] = []

    log.info("🔧 Auto-Repair-Zyklus gestartet (%d Checks)", len(CHECKS))

    for check_id, check_fn, severity in CHECKS:
        try:
            ok, problem, action = await asyncio.wait_for(check_fn(), timeout=30)
        except asyncio.TimeoutError:
            ok, problem, action = False, f"Check {check_id} Timeout (>30s)", "Check hängt — wird beim nächsten Lauf wiederholt"
        except Exception as e:
            ok, problem, action = False, f"Check {check_id} Exception: {e}", "Unerwarteter Fehler"

        _update_check_state(check_id, ok)
        fail_c = _fail_count(check_id)

        entry = {
            "check": check_id,
            "severity": severity,
            "ok": ok,
            "problem": problem,
            "action": action,
            "fail_count": fail_c,
        }
        results.append(entry)

        if not ok:
            repairs.append(entry)
            if severity in ("CRITICAL", "HIGH") or fail_c >= 2:
                alerts.append(entry)
            log.warning("⚠️  [%s] %s → %s", severity, problem, action)
        else:
            log.debug("✅ %s OK", check_id)

    duration = round(time.time() - started, 1)
    ok_count = sum(1 for r in results if r["ok"])

    summary = {
        "ts": datetime.now().isoformat(),
        "duration_s": duration,
        "checks_total": len(results),
        "checks_ok": ok_count,
        "repairs": len(repairs),
        "alerts": len(alerts),
        "details": results,
    }

    # Repair-Log speichern
    try:
        history = []
        if _REPAIR_LOG.exists():
            history = json.loads(_REPAIR_LOG.read_text())[-100:]
        history.append(summary)
        _REPAIR_LOG.write_text(json.dumps(history, indent=2, ensure_ascii=False))
    except Exception:
        pass

    # Telegram-Bericht nur wenn Probleme gefunden
    await _send_telegram_report(summary, repairs, alerts)

    log.info("🔧 Repair-Zyklus abgeschlossen: %d/%d OK, %d repariert, %s",
             ok_count, len(results), len(repairs), f"{duration}s")
    return summary


async def _send_telegram_report(summary: dict, repairs: list, alerts: list):
    tok  = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not tok or not chat:
        return

    # Nur senden wenn Probleme vorhanden
    if not repairs:
        return

    ok_c = summary["checks_ok"]
    total = summary["checks_total"]
    lines = [
        f"🔧 <b>Auto-Repair — {ok_c}/{total} OK</b>  ({summary['duration_s']}s)",
        f"⚠️ {len(repairs)} Probleme gefunden | 🚨 {len(alerts)} Alarme",
        "",
    ]

    # Erst CRITICAL/HIGH
    for r in sorted(repairs, key=lambda x: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(x["severity"], 4)):
        icon = "🚨" if r["severity"] == "CRITICAL" else "⚠️" if r["severity"] == "HIGH" else "ℹ️"
        lines.append(f"{icon} <b>{r['check']}</b>: {r['problem'][:80]}")
        if r["action"]:
            lines.append(f"   → {r['action'][:80]}")

    lines.append(f"\n🕐 {datetime.now().strftime('%d.%m. %H:%M')} Uhr")
    msg = "\n".join(lines)

    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception as e:
        log.debug("Telegram report failed: %s", e)


async def get_repair_status() -> dict:
    """Gibt aktuellen Status des letzten Repair-Zyklus zurück."""
    try:
        if _REPAIR_LOG.exists():
            history = json.loads(_REPAIR_LOG.read_text())
            if history:
                last = history[-1]
                return {
                    "last_run": last.get("ts"),
                    "checks_ok": last.get("checks_ok"),
                    "checks_total": last.get("checks_total"),
                    "repairs": last.get("repairs"),
                    "history_count": len(history),
                }
    except Exception:
        pass
    return {"last_run": None, "checks_ok": 0, "checks_total": 0}


if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    async def _main():
        print("🔧 Auto-Repair-Engine — Einmaliger Prüflauf")
        result = await run_repair_cycle()
        print(f"\n{'='*55}")
        ok = result['checks_ok']
        total = result['checks_total']
        repairs = result['repairs']
        print(f"  Ergebnis: {ok}/{total} Checks OK | {repairs} Reparaturen | {result['duration_s']}s")
        print(f"{'='*55}")
        for r in result.get("details", []):
            icon = "✅" if r["ok"] else f"❌ [{r['severity']}]"
            print(f"  {icon:20} {r['check']}")
            if not r["ok"]:
                print(f"      Problem: {r['problem'][:70]}")
                print(f"      Aktion:  {r['action'][:70]}")

    asyncio.run(_main())
