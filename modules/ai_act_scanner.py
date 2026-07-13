#!/usr/bin/env python3
"""
EU AI Act Compliance Scanner — Vollautomatischer B2B-Revenue-Agent
=================================================================
Pflicht ab 2. August 2026. Bußgelder bis €35 Mio. oder 7% Jahresumsatz.
3,5 Mio. KMU in DE nutzen irgendeine KI — 99% wissen nicht ob sie betroffen sind.

Was dieser Agent tut (täglich 10:00 Uhr):
  1. Findet KMU aus Handelsregister-DB (oder eigener Ziel-Liste)
  2. Claude Haiku analysiert Branche + Rechtsform → Risiko-Assessment
  3. Sendet personalisierte Email: "Ihr Risiko-Score: HOCH — Bußgeld bis €35 Mio."
  4. Bietet kostenlosen Quick-Check + €299 Full-Report
  5. Telegram-Report an Rudolf

Starten:
  python3 modules/ai_act_scanner.py          # Dauerbetrieb (tägl. 10:00)
  python3 modules/ai_act_scanner.py --now    # Sofortiger Test-Run
  python3 modules/ai_act_scanner.py --scan FIRMA_NAME  # Einzelscan
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import smtplib
import sqlite3
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AI-ACT] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("AIActScanner")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "ai_act_scanner.db"


def _load_env():
    env_file = _BASE / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

def _anthropic() -> str: return os.getenv("ANTHROPIC_API_KEY", "")
def _gmail_user() -> str: return os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")
def _gmail_pass() -> str: return os.getenv("GMAIL_APP_PASSWORD_AIITEC", "rqcd uzim npsl odgw")
def _tg_token()   -> str: return os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
def _tg_chat()    -> str: return os.getenv("TELEGRAM_CHAT_ID", "")
def _dashboard()  -> str: return os.getenv("DASHBOARD_URL", "https://supermegabot-production.up.railway.app")


# ── Bounce-Blacklist (permanent — nach Mailer-Daemon Bounces) ────────────────
BOUNCED_EMAILS: set = {
    "info@autoprod.de",   # misconfigured mail server — bounces every time
    "info@muster-hr.de",  # domain not found — fake placeholder company
    "info@fintech-solutions.de",
    "info@medai.de",
    "info@logiroute.de",
    "info@shopmax.de",
    "info@datamarketing.de",
    "info@cloudcode.de",
    "info@edulearn.de",
    "info@insureai.de",
}

# ── Branchen-Risikomatrix ─────────────────────────────────────────────────────
# Quelle: EU AI Act Annex III (Hochrisiko-KI-Systeme)
BRANCHE_RISIKO = {
    "Personalrekrutierung":   ("HOCH",    "HR-Software, ATS-Systeme, Bewerbungsscreening"),
    "Kreditwesen/Banken":     ("HOCH",    "Kreditscoring, Bonitätsprüfung, Robo-Advisor"),
    "Versicherungen":         ("HOCH",    "Risikomodelle, automatisierte Schadensbewertung"),
    "Gesundheit/Medizin":     ("HOCH",    "Diagnose-KI, medizinische Bildanalyse, Triage"),
    "Bildung":                ("HOCH",    "Lernplattformen mit AI, automatisierte Bewertung"),
    "Kritische Infrastruktur":("HOCH",    "Smart Grid, Wasserversorgung, Verkehrssteuerung"),
    "Logistik/Transport":     ("MITTEL",  "Routenoptimierung, Predictive Maintenance"),
    "E-Commerce/Handel":      ("MITTEL",  "Produktempfehlungen, dynamische Preisgestaltung"),
    "Marketing/Werbung":      ("MITTEL",  "Targeting, Content-Generierung, Kundenanalyse"),
    "Produktion/Industrie":   ("MITTEL",  "Qualitätskontrolle-KI, Predictive Maintenance"),
    "IT/Software":            ("MITTEL",  "Code-Assistenten, automatisierter Support"),
    "Gastronomie/Hotel":      ("NIEDRIG", "Reservierungssysteme, Chatbots"),
    "Handwerk":               ("NIEDRIG", "Terminplanung, einfache Automatisierung"),
    "Sonstige":               ("UNBEKANNT","Prüfung empfohlen"),
}

RISIKO_BUSSGELDER = {
    "HOCH":      ("bis €35 Mio.", "oder 7% des Jahresumsatzes"),
    "MITTEL":    ("bis €15 Mio.", "oder 3% des Jahresumsatzes"),
    "NIEDRIG":   ("bis €7,5 Mio.", "oder 1,5% des Jahresumsatzes"),
    "UNBEKANNT": ("bis €35 Mio.", "je nach Einstufung durch Behörden"),
}

# ── Ziel-Firmen ───────────────────────────────────────────────────────────────
# Nur echte Firmen aus handelsregister_radar.db — KEINE Fake-Platzhalter!
# Wenn DB leer → 0 Emails (besser als Spam an nicht-existente Adressen)
DEFAULT_TARGETS: list = []


# ── DB ────────────────────────────────────────────────────────────────────────

def init_db():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(_DB_PATH)) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS aia_scans (
            uid          TEXT PRIMARY KEY,
            firma        TEXT,
            branche      TEXT,
            ort          TEXT,
            email        TEXT,
            risiko_level TEXT,
            risiko_detail TEXT,
            ai_summary   TEXT,
            scanned_at   INTEGER
        );
        CREATE TABLE IF NOT EXISTS aia_outreach (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_uid     TEXT,
            firma        TEXT,
            target_email TEXT,
            status       TEXT DEFAULT 'pending',
            sent_at      INTEGER,
            created_at   INTEGER,
            UNIQUE(target_email, scan_uid)
        );
        CREATE TABLE IF NOT EXISTS aia_run_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at      INTEGER,
            scanned     INTEGER DEFAULT 0,
            emails_sent INTEGER DEFAULT 0,
            duration_s  REAL
        );
        """)


# ── Targets laden ─────────────────────────────────────────────────────────────

def load_targets() -> List[Dict]:
    """Erst aus Handelsregister-DB, dann DEFAULT_TARGETS als Fallback."""
    hr_db = _BASE / "data" / "handelsregister_radar.db"
    targets = []
    if hr_db.exists():
        try:
            with sqlite3.connect(str(hr_db)) as c:
                c.row_factory = sqlite3.Row
                rows = c.execute("SELECT firma, bundesland AS ort FROM hr_leads WHERE score >= 50 ORDER BY scraped_at DESC LIMIT 20").fetchall()
                for r in rows:
                    targets.append({"firma": r["firma"], "branche": "Sonstige", "ort": r["ort"], "email": None})
        except Exception:
            pass
    if len(targets) < 5:
        targets.extend(DEFAULT_TARGETS)
    return targets[:10]


# ── AI Risiko-Analyse ─────────────────────────────────────────────────────────

async def analyze_ai_risk(firma: str, branche: str, ort: str) -> Dict:
    """Claude Haiku analysiert EU AI Act Risiko für diese Firma."""
    risiko, detail = BRANCHE_RISIKO.get(branche, BRANCHE_RISIKO["Sonstige"])
    bussgelder = RISIKO_BUSSGELDER.get(risiko, RISIKO_BUSSGELDER["UNBEKANNT"])

    if not _anthropic():
        return {
            "risiko_level": risiko,
            "risiko_detail": detail,
            "bussgelder":   bussgelder[0],
            "ai_summary":   f"Für Unternehmen in der Branche '{branche}' gelten unter dem EU AI Act (Anhang III) erhöhte Anforderungen. Handlungsbedarf bis August 2026.",
            "empfehlung":   "EU AI Act Compliance-Audit empfohlen",
        }

    prompt = f"""Analysiere kurz das EU AI Act Risiko für dieses Unternehmen:

Firma: {firma}
Branche: {branche}
Standort: {ort}
Risiko-Einschätzung: {risiko} (Branche typischerweise: {detail})

Schreibe 2 Sätze (max 80 Wörter) auf Deutsch:
1. Warum ist diese Branche unter EU AI Act relevant?
2. Was droht konkret wenn sie nicht compliant sind?

Antwort als JSON: {{"summary": "...", "empfehlung": "..."}}"""

    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            timeout=aiohttp.ClientTimeout(total=15)
        ) as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": _anthropic(), "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 300,
                      "messages": [{"role": "user", "content": prompt}]}
            ) as r:
                if r.status == 200:
                    d    = await r.json()
                    text = d.get("content", [{}])[0].get("text", "")
                    m    = re.search(r"\{.*\}", text, re.DOTALL)
                    if m:
                        parsed = json.loads(m.group())
                        return {
                            "risiko_level":  risiko,
                            "risiko_detail": detail,
                            "bussgelder":    bussgelder[0],
                            "ai_summary":    parsed.get("summary", ""),
                            "empfehlung":    parsed.get("empfehlung", "Compliance-Audit empfohlen"),
                        }
    except Exception as e:
        log.debug("AI: %s", e)

    return {
        "risiko_level": risiko, "risiko_detail": detail,
        "bussgelder": bussgelder[0],
        "ai_summary": f"Branche '{branche}': erhöhter Handlungsbedarf unter EU AI Act.",
        "empfehlung": "EU AI Act Compliance-Audit empfohlen",
    }


# ── Email ─────────────────────────────────────────────────────────────────────

def build_compliance_email(firma: str, ort: str, branche: str, analysis: Dict) -> tuple[str, str]:
    risiko    = analysis["risiko_level"]
    bussgelder = analysis["bussgelder"]
    summary   = analysis["ai_summary"]
    dashboard = _dashboard()

    risiko_emoji = {"HOCH": "🔴", "MITTEL": "🟡", "NIEDRIG": "🟢"}.get(risiko, "⚪")

    subject = f"EU AI Act 2026: Ihr Unternehmen riskiert {bussgelder} Bußgeld — Kostenloser Check"

    body = f"""Guten Tag,

mein KI-System hat {firma} in {ort} als potenziell vom EU AI Act betroffenes Unternehmen identifiziert.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RISIKO-EINSCHÄTZUNG: {risiko_emoji} {risiko}
Branche: {branche}
Mögliches Bußgeld: {bussgelder}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{summary}

Der EU AI Act ist seit August 2026 in Kraft. Unternehmen die KI-Tools nutzen
(Chatbots, Empfehlungssysteme, automatisierte Entscheidungen, HR-Software)
können ohne Compliance-Nachweis Bußgelder bis {bussgelder} riskieren.

Was Sie jetzt tun sollten:
✅ Kostenloser 5-Minuten Quick-Check: Sind Sie betroffen?
✅ Vollständiger Compliance-Report: €299 (einmalig)
✅ Laufendes Monitoring: €99/Monat

Kostenloser Quick-Check (keine Kreditkarte):
{dashboard}/ai-act-check?firma={firma.replace(' ', '+')}

Fragen? Antworten Sie einfach auf diese Email.

Mit freundlichen Grüßen,
Rudolf Sarkany
AiiteC — EU AI Act Compliance Solutions
aiitecbuuss@gmail.com

P.S. Über 3,5 Millionen KMU in Deutschland sind potenziell betroffen.
Die meisten wissen es noch nicht.

Abmeldung: Antworten Sie mit "Abmeldung"
"""
    return subject, body


def send_email(to: str, subject: str, body: str) -> bool:
    from modules.gmail_accounts import send_email as ga_send
    ok, via = ga_send(to, subject, body)
    if ok:
        log.info("Email → %s via %s: %s", to, via, subject[:60])
    return ok


async def _supabase_email_sent(email: str) -> bool:
    """Prüft Supabase ob diese Email schon gesendet wurde (Railway-Restart-sicher)."""
    sb_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    sb_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
    if not sb_url or not sb_key:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                f"{sb_url}/rest/v1/aia_email_sent?target_email=eq.{email}&select=id",
                headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"},
                timeout=aiohttp.ClientTimeout(total=5),
            )
            if r.status == 200:
                data = await r.json()
                return bool(data)
    except Exception:
        pass
    return False


async def _supabase_mark_sent(email: str, firma: str) -> None:
    """Speichert gesendete Email in Supabase (überlebt Railway-Restarts)."""
    sb_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    sb_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
    if not sb_url or not sb_key:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"{sb_url}/rest/v1/aia_email_sent",
                json={"target_email": email, "firma": firma},
                headers={
                    "apikey": sb_key,
                    "Authorization": f"Bearer {sb_key}",
                    "Prefer": "return=minimal",
                },
                timeout=aiohttp.ClientTimeout(total=5),
            )
    except Exception:
        pass


# ── Telegram ──────────────────────────────────────────────────────────────────

async def tg(msg: str):
    token = _tg_token(); chat = _tg_chat()
    if not token or not chat: return
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False),
                                         timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat, "text": msg, "parse_mode": "HTML"})
    except Exception: pass


# ── Einzelfirmen-Scan (für CLI) ───────────────────────────────────────────────

async def scan_single(firma: str, branche: str = "Sonstige", ort: str = "Deutschland") -> Dict:
    """Einzelscan einer Firma."""
    init_db()
    log.info("Scanne: %s (%s)", firma, branche)
    analysis = await analyze_ai_risk(firma, branche, ort)
    log.info("Risiko: %s | Bußgeld: %s", analysis["risiko_level"], analysis["bussgelder"])
    log.info("Summary: %s", analysis["ai_summary"])
    return analysis


# ── Haupt-Run ─────────────────────────────────────────────────────────────────

async def run_cycle() -> Dict:
    init_db()
    start   = time.time()
    results = {"scanned": 0, "emails_sent": 0, "high_risk": 0}

    log.info("═══ EU AI Act Scanner — Zyklus startet ═══")
    await tg("🤖 <b>EU AI Act Scanner</b> — starte tägliche Compliance-Scan-Runde...")

    targets = load_targets()
    log.info("Targets: %d Firmen", len(targets))
    now = int(time.time())

    for target in targets:
        firma   = target.get("firma", "")
        branche = target.get("branche", "Sonstige")
        ort     = target.get("ort", "Deutschland")
        email   = target.get("email")

        uid = hashlib.md5(f"{firma}{branche}".encode()).hexdigest()[:16]

        # Bereits gescannt?
        with sqlite3.connect(str(_DB_PATH)) as conn:
            existing = conn.execute("SELECT uid FROM aia_scans WHERE uid=?", (uid,)).fetchone()
            if existing:
                log.debug("Bereits gescannt: %s", firma)
                continue

        analysis = await analyze_ai_risk(firma, branche, ort)
        await asyncio.sleep(0.5)

        with sqlite3.connect(str(_DB_PATH)) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO aia_scans (uid,firma,branche,ort,email,risiko_level,risiko_detail,ai_summary,scanned_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (uid, firma, branche, ort, email, analysis["risiko_level"],
                 analysis["risiko_detail"], analysis["ai_summary"], now)
            )

        results["scanned"] += 1
        if analysis["risiko_level"] == "HOCH":
            results["high_risk"] += 1

        # Email senden wenn Adresse bekannt
        if email:
            if email.lower() in BOUNCED_EMAILS:
                log.warning("Email geblockt (Bounce-Liste): %s", email)
                continue
            subject, body = build_compliance_email(firma, ort, branche, analysis)
            # Dedup: erst SQLite prüfen, dann Supabase (überlebt Railway-Restarts)
            already_sent = False
            with sqlite3.connect(str(_DB_PATH)) as conn:
                already_sent = bool(conn.execute(
                    "SELECT id FROM aia_outreach WHERE target_email=?",
                    (email,)
                ).fetchone())
            if not already_sent:
                already_sent = await _supabase_email_sent(email)
            if not already_sent:
                ok = send_email(email, subject, body)
                if ok:
                    results["emails_sent"] += 1
                    with sqlite3.connect(str(_DB_PATH)) as conn:
                        conn.execute(
                            "INSERT OR IGNORE INTO aia_outreach (scan_uid,firma,target_email,status,sent_at,created_at) VALUES (?,?,?,?,?,?)",
                            (uid, firma, email, "sent", now, now)
                        )
                    await _supabase_mark_sent(email, firma)
                await asyncio.sleep(5)

    duration = round(time.time() - start, 1)
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.execute("INSERT INTO aia_run_log (run_at,scanned,emails_sent,duration_s) VALUES (?,?,?,?)",
                     (now, results["scanned"], results["emails_sent"], duration))

    lines = [
        "🤖 <b>EU AI Act Scanner — Fertig</b>",
        f"⏱ {duration}s | 📊 {results['scanned']} Firmen gescannt | 🔴 {results['high_risk']} HOCH-Risiko",
        f"✉️ {results['emails_sent']} Compliance-Emails gesendet",
        "",
        "💰 <b>Revenue-Potenzial:</b>",
        f"  {results['high_risk']} × €299 Full-Report = <b>€{results['high_risk']*299}</b>",
        f"  {results['scanned']} × €99/mo Monitoring = <b>€{results['scanned']*99}/mo</b>",
        "\n🕙 Nächster Lauf: morgen 10:00 Uhr",
    ]
    await tg("\n".join(lines))

    log.info("═══ Fertig: %d gescannt, %d Emails, %.1fs ═══",
             results["scanned"], results["emails_sent"], duration)
    return results


# ── Scheduler ─────────────────────────────────────────────────────────────────

async def scheduler_loop():
    log.info("╔══════════════════════════════════════════════════╗")
    log.info("║  EU AI ACT SCANNER — GESTARTET                  ║")
    log.info("║  Täglich 10:00 Uhr — vollautomatisch            ║")
    log.info("╚══════════════════════════════════════════════════╝")
    init_db()
    await tg("🚀 <b>EU AI Act Scanner gestartet!</b>\nTäglich 10:00 Uhr — scannt KMU, sendet Compliance-Emails.")
    while True:
        now = datetime.now()
        if now.hour == 10 and now.minute == 0:
            try:
                await run_cycle()
            except Exception as e:
                log.error("Fehler: %s", e)
                await tg(f"⚠️ AI Act Scanner Fehler: {e}")
            await asyncio.sleep(61)
        else:
            secs = ((10 - now.hour) % 24) * 3600 - now.minute * 60 - now.second
            if secs <= 0: secs = 86400
            log.info("Warte %.0f min bis 10:00...", secs / 60)
            await asyncio.sleep(secs)


try:
    init_db()
except Exception as _e:
    import logging as _log; _log.getLogger("AIActScanner").warning("init_db at import: %s", _e)

if __name__ == "__main__":
    if "--now" in sys.argv or "--test" in sys.argv:
        asyncio.run(run_cycle())
    elif "--scan" in sys.argv:
        idx = sys.argv.index("--scan")
        if idx + 1 >= len(sys.argv) or sys.argv[idx + 1].startswith("-"):
            print("Usage: ai_act_scanner.py --scan <firma> [branche]")
            sys.exit(1)
        firma = sys.argv[idx + 1]
        branche = sys.argv[idx + 2] if idx + 2 < len(sys.argv) and not sys.argv[idx + 2].startswith("-") else "Sonstige"
        asyncio.run(scan_single(firma, branche))
    else:
        asyncio.run(scheduler_loop())
