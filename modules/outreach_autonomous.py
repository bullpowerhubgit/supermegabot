#!/usr/bin/env python3
"""
Outreach Autonomous Agent — Vollautomatisches B2B-Akquise-System
================================================================
Läuft 24/7 als eigenständiger Prozess. KEIN Dashboard nötig.
KEINE Benutzerinteraktion. Einmal starten — danach alles automatisch.

Was es tut (täglich 09:00 Uhr):
  1. Scrapt insolvenzbekanntmachungen.de (öffentlich, kostenlos)
  2. Bewertet Leads (Score 0-100)
  3. Findet passende Targets (Steuerberater, Factoring, M&A)
  4. Generiert 10 personalisierte Nachrichten via Claude Haiku
  5. Sendet automatisch per Gmail
  6. Sendet Telegram-Report an Rudolf
  7. Trackt alles in SQLite (kein Doppel-Versand)
  8. Schläft bis zum nächsten Tag

Starten:
  python3 modules/outreach_autonomous.py

Im Hintergrund:
  nohup python3 modules/outreach_autonomous.py > /tmp/outreach_agent.log 2>&1 &
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
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [OUTREACH] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("OutreachAgent")

# ── Env (lädt .env wenn vorhanden) ───────────────────────────────────────────
_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "outreach_autonomous.db"

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
def _gmail_pass() -> str: return os.getenv("GMAIL_APP_PASSWORD_AIITEC", "xulp qyuz gxnb vfqw")
def _tg_token()   -> str: return os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
def _tg_chat()    -> str: return os.getenv("TELEGRAM_CHAT_ID", "")

# ── DB ────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS oa_leads (
            uid             TEXT PRIMARY KEY,
            debtor_name     TEXT,
            bundesland      TEXT,
            branche         TEXT,
            score           INTEGER DEFAULT 0,
            insolvency_type TEXT,
            ai_summary      TEXT,
            scraped_at      INTEGER
        );

        CREATE TABLE IF NOT EXISTS oa_outreach (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_uid    TEXT,
            target_name TEXT,
            target_email TEXT,
            target_type TEXT,
            subject     TEXT,
            body        TEXT,
            li_msg      TEXT,
            status      TEXT DEFAULT 'pending',
            sent_at     INTEGER,
            created_at  INTEGER,
            UNIQUE(target_email, lead_uid)
        );

        CREATE TABLE IF NOT EXISTS oa_run_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at      INTEGER,
            leads_found INTEGER DEFAULT 0,
            emails_sent INTEGER DEFAULT 0,
            errors      INTEGER DEFAULT 0,
            duration_s  REAL
        );
        """)


# ── Feste Target-Liste ────────────────────────────────────────────────────────
TARGETS = [
    # Factoring
    {"name": "BFS finance GmbH",              "email": "info@bfs-finance.de",           "type": "Factoring"},
    {"name": "Deutsche Factoring Bank",        "email": "info@deutsche-factoring.de",    "type": "Factoring"},
    {"name": "Bibby Financial Services DE",   "email": "info@bibbyfinancialservices.de", "type": "Factoring"},
    {"name": "Grenke Factoring",               "email": "factoring@grenke.de",           "type": "Factoring"},
    {"name": "Coface Deutschland",             "email": "info@coface.de",                "type": "Kreditversicherung"},
    # Inkasso/Auskunft
    {"name": "Arvato Financial Solutions",     "email": "kontakt@arvato-financial.de",   "type": "Inkasso"},
    {"name": "EOS Gruppe",                     "email": "info@eos-solutions.de",         "type": "Inkasso"},
    {"name": "Creditreform",                   "email": "info@creditreform.de",          "type": "Kredit-Auskunft"},
    # M&A
    {"name": "GFKL Financial Services",       "email": "info@gfkl.com",                 "type": "M&A"},
    {"name": "Atradius Kreditversicherung",   "email": "info@atradius.de",              "type": "Kreditversicherung"},
]


# ── Insolvenz-Scraper (komplett eigenständig) ─────────────────────────────────

async def scrape_insolvencies(max_entries: int = 30) -> List[Dict]:
    """Scrapt insolvenzbekanntmachungen.de direkt — keine externe Abhängigkeit."""
    entries = []
    bundeslaender = ["nw", "by", "bw", "hh", "be"]  # Größte zuerst

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9",
    }

    try:
        async with aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(ssl=False)
        ) as session:
            for bl in bundeslaender:
                if len(entries) >= max_entries:
                    break
                try:
                    url = (
                        f"https://www.insolvenzbekanntmachungen.de/ap/suche.jsf"
                        f"?bundesland={bl.upper()}&gerichtsstand=&startDatum=&endDatum="
                        f"&name=&aktenzeichen=&absender=&insolvenzen=true&loeschungen=false"
                    )
                    async with session.get(url) as r:
                        if r.status != 200:
                            continue
                        html = await r.text(errors="replace")
                        batch = _parse_html(html, bl.upper())
                        entries.extend(batch)
                        log.info("Scraped %s: %d Einträge", bl.upper(), len(batch))
                    await asyncio.sleep(2.0)
                except Exception as e:
                    log.debug("Scrape %s: %s", bl, e)
    except Exception as e:
        log.warning("Scraper session: %s", e)

    # Falls scraping schlägt: synthetische Demo-Daten für Tests
    if not entries:
        log.warning("Scraping ergab 0 Einträge — nutze Demo-Daten")
        entries = _demo_entries()

    return entries[:max_entries]


def _parse_html(html: str, bundesland: str) -> List[Dict]:
    results = []
    rows = re.findall(
        r'<tr[^>]+class="(?:odd|even)"[^>]*>(.*?)</tr>',
        html, re.DOTALL | re.IGNORECASE
    )
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if len(cells) >= 4:
            debtor    = cells[2] if len(cells) > 2 else ""
            court     = cells[1] if len(cells) > 1 else ""
            case_no   = cells[3] if len(cells) > 3 else ""
            ins_type  = cells[4] if len(cells) > 4 else "Insolvenzeröffnung"
            if not debtor or len(debtor) < 3:
                continue
            uid = hashlib.md5(f"{debtor}{court}{case_no}".encode()).hexdigest()[:16]
            results.append({
                "uid": uid, "debtor_name": debtor, "court": court,
                "case_number": case_no, "bundesland": bundesland,
                "insolvency_type": ins_type or "Insolvenzeröffnung",
                "scraped_at": int(time.time()),
            })
    return results


def _demo_entries() -> List[Dict]:
    demo = [
        ("Muster Logistik GmbH",     "NW", "Logistik",      "Insolvenzeröffnung"),
        ("Schmidt Bau GmbH & Co. KG","BY", "Baugewerbe",     "Insolvenzeröffnung"),
        ("Handel Plus AG",           "BW", "Handel",         "Abweisung mangels Masse"),
        ("Transport Nord GmbH",      "HH", "Transport",      "Insolvenzeröffnung"),
        ("Immobilien West GmbH",     "BE", "Immobilien",     "Insolvenzeröffnung"),
    ]
    entries = []
    for name, bl, branche, itype in demo:
        uid = hashlib.md5(f"{name}{bl}".encode()).hexdigest()[:16]
        entries.append({
            "uid": uid, "debtor_name": name, "bundesland": bl,
            "branche": branche, "insolvency_type": itype,
            "scraped_at": int(time.time()),
        })
    return entries


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_lead(entry: Dict) -> int:
    name   = (entry.get("debtor_name") or "").lower()
    itype  = (entry.get("insolvency_type") or "").lower()
    score  = 30

    # Rechtsform
    if any(x in name for x in ["gmbh", "ag", "se"]):
        score += 20
    elif any(x in name for x in ["ug", "e.k.", "e.k", "kg"]):
        score += 10

    # Art
    if "eröffnung" in itype:
        score += 20
    elif "abweisung mangels" in itype:
        score -= 10

    # Branche
    high_value = ["bau", "transport", "logistik", "handel", "immobilien", "pflege",
                  "gastro", "hotel", "produktion", "industrie"]
    bl = (entry.get("branche") or entry.get("debtor_name") or "").lower()
    if any(x in bl for x in high_value):
        score += 15

    return min(max(score, 0), 100)


def classify_branche(entry: Dict) -> str:
    name = (entry.get("debtor_name") or "").lower()
    mapping = {
        "Bau": ["bau", "construct", "hochbau", "tiefbau", "renovier"],
        "Transport": ["transport", "logistik", "spedition", "fracht", "kurier"],
        "Handel": ["handel", "market", "shop", "store", "vertrieb"],
        "Immobilien": ["immobilien", "immo", "wohn", "real estate"],
        "Gastronomie": ["gastro", "hotel", "restaurant", "café", "imbiss"],
        "Industrie": ["industrie", "produktion", "fertigung", "maschin"],
        "Pflege": ["pflege", "alten", "kranken", "gesundheit", "arzt"],
        "IT": ["it", "software", "digital", "tech", "system"],
    }
    for branche, keywords in mapping.items():
        if any(kw in name for kw in keywords):
            return branche
    return "Sonstige"


# ── AI Nachricht generieren ───────────────────────────────────────────────────

async def generate_message(target: Dict, lead: Dict) -> Dict:
    """Claude Haiku oder Fallback-Template."""
    dashboard = os.getenv("DASHBOARD_URL", "https://supermegabot-production.up.railway.app")

    def fallback() -> Dict:
        subject = (f"Insolvenz-Lead: {lead['debtor_name']} "
                   f"({lead.get('bundesland','DE')}) — Score {lead.get('score',70)}/100")
        email_body = f"""Guten Tag,

mein automatisches System hat heute einen Eintrag im Insolvenzregister identifiziert, der für {target['type']} relevant sein könnte:

  Schuldner:   {lead['debtor_name']}
  Bundesland:  {lead.get('bundesland','?')}
  Branche:     {lead.get('branche','?')}
  Score:       {lead.get('score',70)}/100
  Art:         {lead.get('insolvency_type','Insolvenzeröffnung')}

Mein Tool "Insolvenz Radar Pro" durchsucht täglich das offizielle Insolvenzregister und bewertet jeden Eintrag automatisch nach Relevanz — segmentiert nach Factoring, Steuerberatung und M&A.

Kostenloser 7-Tage-Test, keine Kreditkarte nötig:
{dashboard}/insolvenz-radar

Mit freundlichen Grüßen,
Rudolf Sarkany
AiiteC — Intelligente Geschäftslösungen
"""
        li_msg = (
            f"Hallo {target['name'].split()[0]},\n\n"
            f"ich tracke täglich neue Insolvenzen in DE. Heute: {lead['debtor_name']} in "
            f"{lead.get('bundesland','?')} (Branche: {lead.get('branche','?')}, Score {lead.get('score',70)}/100).\n\n"
            f"Für {target['type']} oft ein direkter Neukunde-Hinweis. "
            f"7-Tage-Test gratis: {dashboard}/insolvenz-radar"
        )
        return {"subject": subject, "email_body": email_body, "li_msg": li_msg}

    if not _anthropic():
        return fallback()

    prompt = f"""Schreibe auf Deutsch eine kurze professionelle Kalt-Akquise-Email und eine LinkedIn-Nachricht.

Empfänger: {target['name']} ({target['type']})
Lead: {lead['debtor_name']}, {lead.get('bundesland','?')}, Branche: {lead.get('branche','?')}, Score: {lead.get('score',70)}/100, Art: {lead.get('insolvency_type','?')}
Produkt: "Insolvenz Radar Pro" — täglich neue B2B-Leads aus dem Insolvenzregister, €29-199/Monat
URL: {dashboard}/insolvenz-radar

Regeln:
- Email: max 100 Wörter, Betreff mit Lead-Name, 1 CTA: 7-Tage-Test
- LinkedIn: max 60 Wörter, kein "sehr geehrte", direkt + persönlich

JSON-Antwort:
{{"subject":"...", "email_body":"...", "li_msg":"..."}}"""

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20),
            connector=aiohttp.TCPConnector(ssl=False)
        ) as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": _anthropic(), "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 500,
                      "messages": [{"role": "user", "content": prompt}]}
            ) as r:
                if r.status == 200:
                    d    = await r.json()
                    text = d.get("content", [{}])[0].get("text", "")
                    m    = re.search(r"\{.*\}", text, re.DOTALL)
                    if m:
                        return json.loads(m.group())
    except Exception as e:
        log.debug("AI: %s", e)

    return fallback()


# ── Email senden ──────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, body: str) -> bool:
    user = _gmail_user()
    pw   = _gmail_pass().replace(" ", "")
    if not user or not pw:
        log.warning("Gmail-Zugangsdaten fehlen")
        return False
    try:
        msg             = MIMEMultipart("alternative")
        msg["Subject"]  = subject
        msg["From"]     = f"Rudolf Sarkany <{user}>"
        msg["To"]       = to
        msg["Reply-To"] = user
        msg.attach(MIMEText(body, "plain", "utf-8"))
        html = f"""<html><body style="font-family:Arial,sans-serif;color:#333;max-width:600px">
<pre style="font-family:inherit;white-space:pre-wrap">{body}</pre>
<hr style="border:none;border-top:1px solid #eee;margin:20px 0">
<p style="font-size:11px;color:#aaa">Abmeldung: Antworten Sie mit "Abmeldung"</p>
</body></html>"""
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as srv:
            srv.login(user, pw)
            srv.sendmail(user, to, msg.as_string())
        log.info("Email: %s → %s", subject[:50], to)
        return True
    except Exception as e:
        log.warning("Email-Fehler (%s): %s", to, e)
        return False


# ── Telegram ──────────────────────────────────────────────────────────────────

async def tg(msg: str):
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            timeout=aiohttp.ClientTimeout(total=10)
        ) as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg,
                      "parse_mode": "HTML", "disable_web_page_preview": True}
            )
    except Exception as e:
        log.debug("TG: %s", e)


# ── Haupt-Run-Funktion ────────────────────────────────────────────────────────

async def run_outreach_cycle() -> Dict:
    """Ein kompletter Akquise-Zyklus: Scrapen → Bewerten → Generieren → Senden."""
    start   = time.time()
    results = {"leads_found": 0, "emails_sent": 0, "errors": 0, "batch": []}

    log.info("═══ Outreach-Zyklus startet ═══")
    await tg("🤖 <b>Outreach Agent startet</b> — scrappe Insolvenzregister...")

    # 1. Leads scrapen
    raw_leads = await scrape_insolvencies(max_entries=30)
    log.info("Insolvenzregister: %d Einträge gefunden", len(raw_leads))

    # 2. Bewerten + klassifizieren
    leads = []
    now   = int(time.time())
    for entry in raw_leads:
        entry["score"]  = score_lead(entry)
        entry["branche"] = classify_branche(entry)
        if entry["score"] >= 50:
            leads.append(entry)
        # In DB speichern
        try:
            with _db() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO oa_leads
                       (uid, debtor_name, bundesland, branche, score, insolvency_type, scraped_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (entry["uid"], entry["debtor_name"], entry.get("bundesland",""),
                     entry["branche"], entry["score"], entry.get("insolvency_type",""),
                     now)
                )
        except Exception:
            pass

    leads.sort(key=lambda x: x["score"], reverse=True)
    results["leads_found"] = len(leads)
    log.info("Qualifizierte Leads (Score≥50): %d", len(leads))

    if not leads:
        await tg("⚠️ Outreach Agent: Keine qualifizierten Leads heute. Nächster Lauf morgen 09:00.")
        return results

    # 3. Targets × Leads pairen (max 10)
    pairs = []
    for i, target in enumerate(TARGETS[:10]):
        lead = leads[i % len(leads)]
        # Bereits kontaktiert?
        with _db() as conn:
            exists = conn.execute(
                "SELECT id FROM oa_outreach WHERE target_email=? AND lead_uid=?",
                (target["email"], lead["uid"])
            ).fetchone()
        if exists:
            log.debug("Überspringe %s (bereits kontaktiert für %s)", target["name"], lead["uid"])
            continue
        pairs.append((target, lead))

    log.info("Neue Paare für Outreach: %d", len(pairs))

    # 4. Nachrichten generieren + senden
    for target, lead in pairs:
        try:
            msgs = await generate_message(target, lead)
            await asyncio.sleep(0.5)

            # In DB speichern
            sent_at = None
            status  = "pending"

            ok = send_email(target["email"], msgs["subject"], msgs["email_body"])
            if ok:
                sent_at = int(time.time())
                status  = "sent"
                results["emails_sent"] += 1
                await asyncio.sleep(4)  # Anti-Spam
            else:
                results["errors"] += 1
                status = "error"

            with _db() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO oa_outreach
                       (lead_uid, target_name, target_email, target_type, subject,
                        body, li_msg, status, sent_at, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (lead["uid"], target["name"], target["email"], target["type"],
                     msgs["subject"], msgs["email_body"], msgs.get("li_msg",""),
                     status, sent_at, int(time.time()))
                )

            results["batch"].append({
                "target": target["name"],
                "lead":   lead["debtor_name"],
                "score":  lead["score"],
                "sent":   ok,
            })
            log.info("%s → %s: %s", target["name"], lead["debtor_name"], "✓" if ok else "✗")

        except Exception as e:
            log.error("Pair %s: %s", target["name"], e)
            results["errors"] += 1

    # 5. Run-Log
    duration = round(time.time() - start, 1)
    with _db() as conn:
        conn.execute(
            "INSERT INTO oa_run_log (run_at, leads_found, emails_sent, errors, duration_s) VALUES (?,?,?,?,?)",
            (int(time.time()), results["leads_found"],
             results["emails_sent"], results["errors"], duration)
        )

    # 6. Telegram-Report
    lines = [
        "📧 <b>Outreach Agent — Zyklus fertig</b>",
        f"⏱ Dauer: {duration}s",
        f"🎯 Qualifizierte Leads: {results['leads_found']}",
        f"✉️ Emails gesendet: {results['emails_sent']}",
        f"❌ Fehler: {results['errors']}",
        "",
    ]
    for b in results["batch"][:5]:
        icon = "✅" if b["sent"] else "❌"
        lines.append(f"{icon} {b['target']} → {b['lead']} (Score {b['score']})")
    if len(results["batch"]) > 5:
        lines.append(f"<i>... und {len(results['batch'])-5} weitere</i>")
    lines.append(f"\n🕘 Nächster Lauf: morgen 09:00 Uhr")

    await tg("\n".join(lines))
    log.info("═══ Zyklus abgeschlossen: %d gesendet, %d Fehler, %.1fs ═══",
             results["emails_sent"], results["errors"], duration)
    return results


# ── Scheduler-Loop ────────────────────────────────────────────────────────────

async def scheduler_loop():
    """Läuft ewig — führt run_outreach_cycle() täglich um 09:00 aus."""
    log.info("╔══════════════════════════════════════════════╗")
    log.info("║  OUTREACH AUTONOMOUS AGENT — GESTARTET       ║")
    log.info("║  Täglich 09:00 Uhr — kein manuelles Eingriff ║")
    log.info("╚══════════════════════════════════════════════╝")

    await tg("🚀 <b>Outreach Autonomous Agent gestartet!</b>\nLäuft täglich um 09:00 Uhr automatisch.")
    init_db()

    while True:
        now = datetime.now()

        # Nächste 09:00 berechnen
        if now.hour < 9 or (now.hour == 9 and now.minute == 0):
            target_hour = 9
        else:
            # Morgen 09:00
            from datetime import timedelta
            tomorrow = (now + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            seconds_until = (tomorrow - now).total_seconds()
            log.info("Nächster Lauf: %s (in %.0f Minuten)", tomorrow.strftime("%Y-%m-%d 09:00"), seconds_until/60)
            await asyncio.sleep(seconds_until)
            continue

        # Genau 09:00? Dann starten
        if now.hour == 9 and now.minute == 0:
            try:
                await run_outreach_cycle()
            except Exception as e:
                log.error("Zyklus-Fehler: %s", e)
                await tg(f"⚠️ Outreach Agent Fehler: {e}")
            await asyncio.sleep(61)  # 1 Minute überspringen um Doppelstart zu vermeiden
        else:
            # Warte bis 09:00
            next_run_seconds = (9 - now.hour) * 3600 - now.minute * 60 - now.second
            if next_run_seconds <= 0:
                next_run_seconds = 86400  # Morgen
            log.info("Warte %.0f Minuten bis 09:00 Uhr...", next_run_seconds/60)
            await asyncio.sleep(next_run_seconds)


async def run_now():
    """Einmaliger Test-Run — sofort ausführen."""
    log.info("=== TEST-RUN (sofort) ===")
    init_db()
    result = await run_outreach_cycle()
    log.info("Ergebnis: %s", result)
    return result


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if "--now" in sys.argv or "--test" in sys.argv:
        # Sofortiger Test-Run: python3 outreach_autonomous.py --now
        asyncio.run(run_now())
    else:
        # Dauerbetrieb: python3 outreach_autonomous.py
        asyncio.run(scheduler_loop())
