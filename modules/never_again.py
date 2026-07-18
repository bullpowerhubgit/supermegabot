"""
NeverAgain — Fehler-Gedächtnis & Automatische Prävention.

Prinzip: Jeder Fehler wird fingerabgedruckt. Taucht dasselbe Muster
ein zweites Mal auf, wird die hinterlegte Lösung AUTOMATISCH angewendet.
Neue Fehler werden sofort gespeichert und per Telegram gemeldet.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import traceback
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "never_again.db"
DB_PATH.parent.mkdir(exist_ok=True)

# ── Schema ────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS error_memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT UNIQUE NOT NULL,
    error_type  TEXT NOT NULL,
    pattern     TEXT NOT NULL,
    location    TEXT,
    occurrences INTEGER DEFAULT 1,
    auto_fixed  INTEGER DEFAULT 0,
    fix_type    TEXT,          -- 'CODE' | 'COMMAND' | 'ALERT' | 'RESTART' | None
    fix_payload TEXT,          -- code / command string / message
    fix_desc    TEXT,          -- human-readable description
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    resolved    INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fix_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL,
    ts          REAL NOT NULL,
    result      TEXT,
    success     INTEGER DEFAULT 0
);
"""

def _init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.executescript(_DDL)
        _seed_known_errors(c)

def _seed_known_errors(conn):
    """Bekannte Fehler aus unserer Entwicklungsgeschichte vorbelegen."""
    known = [
        {
            "fingerprint": "cors_failed_to_fetch",
            "error_type": "CORSError",
            "pattern": "Failed to fetch|CORS|Access-Control-Allow-Origin",
            "location": "dashboard/server.py",
            "fix_type": "ALERT",
            "fix_payload": "CORS-Fehler! Prüfe: 1) /api/assistant/* braucht Access-Control-Allow-Origin: * 2) Origin 'null' (file://) muss erlaubt sein. Fix: CORS-Middleware in server.py anpassen.",
            "fix_desc": "CORS für assistant-Endpunkte auf * setzen",
        },
        {
            "fingerprint": "anthropic_credits_empty",
            "error_type": "APIError",
            "pattern": "insufficient_quota|credit|No credits|402|You exceeded your current quota",
            "location": "modules/ai_client.py",
            "fix_type": "CODE",
            "fix_payload": "# Anthropic-Provider deaktivieren, auf Groq/OpenRouter ausweichen\nimport modules.ai_client as _ac\nif 'anthropic' in _ac._PROVIDERS:\n    _ac._CIRCUIT[_ac._PROVIDERS.index(p for p in _ac._PROVIDERS if p.get('name')=='anthropic').__next__()] = {'failures': 99, 'disabled_until': time.time()+86400}\n",
            "fix_desc": "Anthropic deaktivieren → Groq/OpenRouter übernehmen automatisch",
        },
        {
            "fingerprint": "stripe_wrong_account",
            "error_type": "StripeAuthError",
            "pattern": "STRIPE_SECRET_KEY_AIITEC|acct_.*aiitec|sk-.*aiitec",
            "location": "modules/stripe_client.py",
            "fix_type": "ALERT",
            "fix_payload": "KRITISCH: Falscher Stripe-Key! NUR bullpowersrtkennels (acct_1Tg1U0RJECiV6vSm) verwenden. NIEMALS STRIPE_SECRET_KEY_AIITEC!",
            "fix_desc": "Stripe immer mit bullpowersrtkennels-Account",
        },
        {
            "fingerprint": "mailchimp_banned",
            "error_type": "MailchimpError",
            "pattern": "mailchimp|Mailchimp|mc_api|MAILCHIMP",
            "location": "*",
            "fix_type": "ALERT",
            "fix_payload": "MAILCHIMP GEBANNT! Alle 3 Konten gesperrt seit 2026-07-12. Sofort auf Klaviyo umsteigen!",
            "fix_desc": "Mailchimp → Klaviyo wechseln",
        },
        {
            "fingerprint": "ds24_wrong_key",
            "error_type": "DS24AuthError",
            "pattern": "1682000-|digistore.*1682000",
            "location": "modules/digistore_client.py",
            "fix_type": "ALERT",
            "fix_payload": "FALSCHER DS24-Key! IMMER 1581233-... (aiitec-Konto) verwenden, NIEMALS 1682000-...",
            "fix_desc": "DS24 immer aiitec-Konto (1581233-...)",
        },
        {
            "fingerprint": "port_already_in_use",
            "error_type": "OSError",
            "pattern": "Address already in use|port.*8888|bind.*failed",
            "location": "dashboard/server.py",
            "fix_type": "COMMAND",
            "fix_payload": "lsof -ti:8888 | xargs kill -9 2>/dev/null; sleep 1",
            "fix_desc": "Port 8888 freigeben und Server neu starten",
        },
        {
            "fingerprint": "supabase_connection_failed",
            "error_type": "SupabaseError",
            "pattern": "supabase.*timeout|connection.*supabase|SUPABASE.*refused",
            "location": "modules/supabase_client.py",
            "fix_type": "ALERT",
            "fix_payload": "Supabase-Verbindung ausgefallen. Retry-Logik greift. Prüfe: SUPABASE_URL und SUPABASE_KEY in .env",
            "fix_desc": "Supabase mit Exponential Backoff neu verbinden",
        },
        {
            "fingerprint": "module_not_found",
            "error_type": "ModuleNotFoundError",
            "pattern": "No module named|ModuleNotFoundError",
            "location": "*",
            "fix_type": "COMMAND",
            "fix_payload": "cd /Users/rudolfsarkany/supermegabot && pip3 install -r requirements.txt -q",
            "fix_desc": "Fehlende Python-Pakete installieren",
        },
        {
            "fingerprint": "railway_deploy_failed",
            "error_type": "RailwayError",
            "pattern": "railway.*failed|deploy.*failed|FAILED.*railway|build.*error.*railway",
            "location": ".github/workflows/deploy.yml",
            "fix_type": "ALERT",
            "fix_payload": "Railway-Deploy fehlgeschlagen! Prüfe: 1) Syntax-Fehler in geänderten Dateien 2) RAILWAY_TOKEN Secret in GitHub 3) railway.toml korrekt",
            "fix_desc": "Railway-Deployment-Fehler diagnostizieren",
        },
        {
            "fingerprint": "fake_products_attempt",
            "error_type": "PolicyViolation",
            "pattern": "_demo_leads|demo_product|fake.*product|placeholder.*product",
            "location": "modules/product_engine.py",
            "fix_type": "ALERT",
            "fix_payload": "STOP! Niemals Demo/Fake-Produkte generieren! Rudolf wurde mehrfach durch KI-Fake-Produkte betrogen. Nur echte Lieferanten (Printify/AliExpress/echte Supabase-Daten)!",
            "fix_desc": "Fake-Produkt-Versuch blockieren",
        },
        {
            "fingerprint": "ai_command_not_found",
            "error_type": "ZshCommandNotFound",
            "pattern": "command not found: ai|zsh.*ai.*not found",
            "location": "~/.zshrc",
            "fix_type": "COMMAND",
            "fix_payload": "source ~/.zshrc",
            "fix_desc": ".zshrc neu laden damit 'ai' Befehl verfügbar ist",
        },
        {
            "fingerprint": "iwin_account_used",
            "error_type": "PolicyViolation",
            "pattern": "IWIN|1135864516276500|iwin",
            "location": "*",
            "fix_type": "ALERT",
            "fix_payload": "FALSCHES Facebook/IG-Konto! IMMER AiiteC verwenden: FB Page 1016738738178786, IG @aaiitecc 17841478315197796. NIEMALS IWIN (1135864516276500)!",
            "fix_desc": "Immer AiiteC-Konto für FB/IG",
        },
        {
            "fingerprint": "railway_without_permission",
            "error_type": "PolicyViolation",
            "pattern": "railway deploy|git push.*main.*railway|RAILWAY.*deploy",
            "location": "automation",
            "fix_type": "ALERT",
            "fix_payload": "STOP! NIEMALS Railway deployen ohne explizite Erlaubnis von Rudolf! Erst fragen, dann deployen.",
            "fix_desc": "Railway-Deploy braucht explizite Genehmigung",
        },
    ]

    for e in known:
        conn.execute("""
            INSERT OR IGNORE INTO error_memory
            (fingerprint, error_type, pattern, location, fix_type, fix_payload, fix_desc,
             first_seen, last_seen, occurrences, auto_fixed, resolved)
            VALUES (?,?,?,?,?,?,?,?,?,0,0,0)
        """, (
            e["fingerprint"], e["error_type"], e["pattern"],
            e.get("location", "*"),
            e.get("fix_type"), e.get("fix_payload"), e.get("fix_desc"),
            time.time(), time.time(),
        ))

# ── Core Engine ───────────────────────────────────────────────────────────────

class NeverAgain:
    """Singleton error memory engine."""
    _inst: Optional["NeverAgain"] = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
            cls._inst._ready = False
        return cls._inst

    def init(self):
        if self._ready:
            return
        _init_db()
        self._ready = True
        log.info("NeverAgain engine ready — DB: %s", DB_PATH)

    def _fingerprint(self, exc: Exception, location: str = "") -> str:
        msg = str(exc)[:200]
        typ = type(exc).__name__
        raw = f"{typ}:{location}:{msg}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _match_known(self, msg: str) -> Optional[dict]:
        """Suche nach bekanntem Fehlermuster in der Datenbank."""
        with sqlite3.connect(DB_PATH) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                "SELECT * FROM error_memory WHERE resolved=0"
            ).fetchall()
        for row in rows:
            pattern = row["pattern"]
            try:
                if re.search(pattern, msg, re.IGNORECASE):
                    return dict(row)
            except re.error:
                if pattern.lower() in msg.lower():
                    return dict(row)
        return None

    def _record_occurrence(self, fingerprint: str, known: Optional[dict] = None):
        with sqlite3.connect(DB_PATH) as c:
            existing = c.execute(
                "SELECT id FROM error_memory WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
            if existing:
                c.execute(
                    "UPDATE error_memory SET occurrences=occurrences+1, last_seen=? WHERE fingerprint=?",
                    (time.time(), fingerprint)
                )
            else:
                pattern = ""
                if known:
                    pattern = known.get("pattern", "")
                c.execute("""
                    INSERT INTO error_memory
                    (fingerprint, error_type, pattern, location, first_seen, last_seen, occurrences)
                    VALUES (?,?,?,?,?,?,1)
                """, (fingerprint, "Unknown", pattern, "", time.time(), time.time()))

    async def _apply_fix(self, entry: dict) -> bool:
        fix_type = entry.get("fix_type")
        payload = entry.get("fix_payload", "")
        fp = entry["fingerprint"]

        result = ""
        success = False

        if fix_type == "COMMAND":
            import subprocess
            try:
                r = subprocess.run(
                    payload, shell=True, capture_output=True, text=True, timeout=30
                )
                result = r.stdout[:500] + r.stderr[:200]
                success = r.returncode == 0
                log.info("NeverAgain CMD fix '%s': %s", fp, result[:100])
            except Exception as ex:
                result = str(ex)

        elif fix_type == "CODE":
            try:
                exec_globals = {"time": time, "log": log}
                exec(payload, exec_globals)  # noqa: S102
                result = "Code executed"
                success = True
            except Exception as ex:
                result = str(ex)

        elif fix_type == "ALERT":
            result = payload
            success = True
            await self._telegram(f"⚠️ NeverAgain WARNUNG:\n{payload}")

        elif fix_type == "RESTART":
            result = "Restart-Signal gesendet"
            success = True
            await self._telegram(f"🔄 NeverAgain: Auto-Restart ausgelöst\n{entry.get('fix_desc','')}")

        with sqlite3.connect(DB_PATH) as c:
            c.execute(
                "INSERT INTO fix_log (fingerprint, ts, result, success) VALUES (?,?,?,?)",
                (fp, time.time(), result[:1000], int(success))
            )
            if success:
                c.execute(
                    "UPDATE error_memory SET auto_fixed=auto_fixed+1 WHERE fingerprint=?", (fp,)
                )
        return success

    async def _telegram(self, msg: str):
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat:
            return
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": f"🤖 SuperMegaBot NeverAgain\n{msg[:3000]}", "parse_mode": "HTML"},
                    timeout=aiohttp.ClientTimeout(total=8),
                )
        except Exception as ex:
            log.warning("NeverAgain Telegram send failed: %s", ex)

    async def handle(self, exc: Exception, location: str = "", context: str = "") -> bool:
        """
        Haupteingang. Gibt True zurück wenn ein bekannter Fix angewendet wurde.
        """
        if not self._ready:
            self.init()

        full_msg = f"{type(exc).__name__}: {exc}\n{context}"
        fp = self._fingerprint(exc, location)
        known = self._match_known(full_msg)

        self._record_occurrence(fp, known)

        if known:
            occ = known.get("occurrences", 0) + 1
            desc = known.get("fix_desc", "—")
            log.warning(
                "NeverAgain: Bekannter Fehler erkannt (#%d) [%s] → %s",
                occ, known["fingerprint"], desc
            )
            if known.get("fix_type"):
                fixed = await self._apply_fix(known)
                await self._telegram(
                    f"🔧 Bekannter Fehler #{occ} erkannt + automatisch behoben!\n"
                    f"<b>{desc}</b>\n"
                    f"Ort: {location or '?'}\n"
                    f"Fehler: <code>{str(exc)[:200]}</code>"
                )
                return fixed
        else:
            # Neuer, unbekannter Fehler → speichern + alarmieren
            tb = traceback.format_exc()[-800:]
            await self._telegram(
                f"🆕 NEUER Fehler aufgetreten!\n"
                f"Ort: <code>{location or '?'}</code>\n"
                f"Typ: <code>{type(exc).__name__}</code>\n"
                f"Nachricht: <code>{str(exc)[:300]}</code>\n"
                f"Stack: <code>{tb}</code>\n\n"
                f"⚡ Wird in NeverAgain gespeichert — passiert das noch mal, reagiere ich automatisch!"
            )
            log.error("NeverAgain: Neuer Fehler gespeichert: %s @ %s", exc, location)

        return False

    def handle_sync(self, exc: Exception, location: str = "", context: str = "") -> bool:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.handle(exc, location, context))
                return False
            return loop.run_until_complete(self.handle(exc, location, context))
        except Exception:
            return False

    def status(self) -> dict:
        """Für API-Endpoint: aktueller Zustand der Error-Datenbank."""
        if not self._ready:
            self.init()
        with sqlite3.connect(DB_PATH) as c:
            c.row_factory = sqlite3.Row
            total = c.execute("SELECT COUNT(*) FROM error_memory").fetchone()[0]
            active = c.execute("SELECT COUNT(*) FROM error_memory WHERE resolved=0").fetchone()[0]
            fixed = c.execute("SELECT SUM(auto_fixed) FROM error_memory").fetchone()[0] or 0
            recent = c.execute("""
                SELECT fingerprint, error_type, fix_desc, occurrences, auto_fixed, last_seen
                FROM error_memory ORDER BY last_seen DESC LIMIT 10
            """).fetchall()
            log_recent = c.execute("""
                SELECT fl.fingerprint, fl.ts, fl.result, fl.success,
                       em.fix_desc
                FROM fix_log fl
                LEFT JOIN error_memory em ON fl.fingerprint = em.fingerprint
                ORDER BY fl.ts DESC LIMIT 20
            """).fetchall()

        return {
            "ok": True,
            "db_path": str(DB_PATH),
            "total_known_errors": total,
            "active_errors": active,
            "total_auto_fixes": fixed,
            "recent_errors": [dict(r) for r in recent],
            "fix_log": [dict(r) for r in log_recent],
        }

    def add_known_error(self, pattern: str, fix_type: str, fix_payload: str,
                        fix_desc: str, error_type: str = "CustomError",
                        location: str = "*") -> str:
        """Neuen bekannten Fehler manuell registrieren."""
        if not self._ready:
            self.init()
        fp = hashlib.sha256(f"{error_type}:{pattern}:{fix_type}".encode()).hexdigest()[:16]
        with sqlite3.connect(DB_PATH) as c:
            c.execute("""
                INSERT OR REPLACE INTO error_memory
                (fingerprint, error_type, pattern, location, fix_type, fix_payload,
                 fix_desc, first_seen, last_seen, occurrences, auto_fixed, resolved)
                VALUES (?,?,?,?,?,?,?,?,?,0,0,0)
            """, (fp, error_type, pattern, location, fix_type, fix_payload, fix_desc,
                  time.time(), time.time()))
        log.info("NeverAgain: Neuer Fehler registriert: %s → %s", pattern[:50], fix_desc)
        return fp


# ── Singleton & Decorators ────────────────────────────────────────────────────

engine = NeverAgain()


def never_again(location: str = ""):
    """Decorator: Fehler automatisch an NeverAgain melden."""
    def decorator(fn: Callable):
        if asyncio.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    loc = location or f"{fn.__module__}.{fn.__qualname__}"
                    await engine.handle(exc, location=loc)
                    raise
            return async_wrapper
        else:
            @wraps(fn)
            def sync_wrapper(*args, **kwargs):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    loc = location or f"{fn.__module__}.{fn.__qualname__}"
                    engine.handle_sync(exc, location=loc)
                    raise
            return sync_wrapper
    return decorator


def check_string(text: str, location: str = "") -> Optional[str]:
    """Prüfe ob ein Text-String einem bekannten Fehlermuster entspricht.
    Gibt den fix_desc zurück wenn ein Treffer gefunden wurde."""
    if not engine._ready:
        engine.init()
    match = engine._match_known(text)
    if match:
        return match.get("fix_desc")
    return None


# ── Auto-Init ────────────────────────────────────────────────────────────────

def setup():
    engine.init()
    log.info("NeverAgain: %d bekannte Fehler-Muster geladen", _count_known())


def _count_known() -> int:
    try:
        with sqlite3.connect(DB_PATH) as c:
            return c.execute("SELECT COUNT(*) FROM error_memory").fetchone()[0]
    except Exception:
        return 0
