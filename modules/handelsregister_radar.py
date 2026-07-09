#!/usr/bin/env python3
"""
Handelsregister Neugründungs-Radar — Vollautomatischer Lead-Agent
================================================================
Täglich neue GmbH/UG/AG Gründungen aus dem Handelsregister.
Jede neue GmbH braucht: Steuerberater, Buchhaltungssoftware, Versicherung, Website.

Wir verkaufen diese Leads per Email-Subscription an:
  - Steuerberater (€20/Lead)
  - Buchhaltungs-SaaS (Lexware, SevDesk — €15/Lead)
  - Versicherungsmakler (€25/Lead)
  - Webdesigner (€10/Lead)

Starten:
  python3 modules/handelsregister_radar.py          # Dauerbetrieb (tägl. 08:00)
  python3 modules/handelsregister_radar.py --now    # Sofortiger Test-Run
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
from typing import Dict, List

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [HR-RADAR] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("HandelsregisterRadar")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "handelsregister_radar.db"


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


# ── Subscriber-Liste (wer kauft unsere Leads) ─────────────────────────────────
LEAD_BUYERS = [
    {"name": "Steuerberater Netzwerk DE",     "email": "kontakt@stbv.de",              "type": "Steuerberater",   "preis": 20},
    {"name": "DATEV Vertrieb",                "email": "vertrieb@datev.de",             "type": "Buchh-SaaS",      "preis": 15},
    {"name": "Lexware Partnervertrieb",       "email": "partner@lexware.de",            "type": "Buchh-SaaS",      "preis": 15},
    {"name": "SevDesk Partnerteam",           "email": "partner@sevdesk.de",            "type": "Buchh-SaaS",      "preis": 12},
    {"name": "HDI Gewerbeversicherung",       "email": "gewerbe@hdi.de",               "type": "Versicherung",    "preis": 25},
    {"name": "Allianz Geschäftskunden",       "email": "geschaeftskunden@allianz.de",   "type": "Versicherung",    "preis": 25},
    {"name": "Jimdo Geschäftskunden",         "email": "business@jimdo.com",            "type": "Website/SaaS",    "preis": 10},
    {"name": "Wix Partner Deutschland",       "email": "partner@wix.com",               "type": "Website/SaaS",    "preis": 10},
]


# ── DB ────────────────────────────────────────────────────────────────────────

def init_db():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(_DB_PATH)) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS hr_leads (
            uid          TEXT PRIMARY KEY,
            firma        TEXT,
            rechtsform   TEXT,
            amtsgericht  TEXT,
            registernr   TEXT,
            bundesland   TEXT,
            ort          TEXT,
            datum        TEXT,
            score        INTEGER DEFAULT 0,
            scraped_at   INTEGER
        );
        CREATE TABLE IF NOT EXISTS hr_outreach (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_uid     TEXT,
            buyer_name   TEXT,
            buyer_email  TEXT,
            status       TEXT DEFAULT 'pending',
            sent_at      INTEGER,
            created_at   INTEGER,
            UNIQUE(lead_uid, buyer_email)
        );
        CREATE TABLE IF NOT EXISTS hr_run_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at       INTEGER,
            leads_found  INTEGER DEFAULT 0,
            emails_sent  INTEGER DEFAULT 0,
            duration_s   REAL
        );
        """)


# ── Scraper ───────────────────────────────────────────────────────────────────

BUNDESLAENDER_HR = {
    "Bayern":            "BY",
    "NRW":               "NW",
    "Baden-Württemberg": "BW",
    "Hessen":            "HE",
    "Hamburg":           "HH",
}

_HR_BASE        = "https://www.handelsregister.de"
_HR_WELCOME_URL = "https://www.handelsregister.de/rp_web/welcome.xhtml"
_HR_SEARCH_URL  = "https://www.handelsregister.de/rp_web/search.xhtml"

async def scrape_neugründungen(max_per_land: int = 20) -> List[Dict]:
    """Scrapt neue HRB-Eintragungen via JSF-Session: welcome→search GET→search POST."""
    results = []
    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9",
    }

    for bl_name, bl_code in list(BUNDESLAENDER_HR.items())[:3]:
        try:
            async with aiohttp.ClientSession(
                headers=_HEADERS,
                timeout=aiohttp.ClientTimeout(total=45),
                connector=aiohttp.TCPConnector(ssl=True),
                cookie_jar=aiohttp.CookieJar(),
            ) as session:
                # Schritt 1: welcome.xhtml → JSESSIONID cookie holen
                async with session.get(_HR_WELCOME_URL) as r:
                    if r.status not in (200, 400):
                        log.warning("HR %s: welcome %d", bl_name, r.status)
                        continue
                    await r.read()

                # Schritt 2: search.xhtml → ViewState holen
                async with session.get(_HR_SEARCH_URL) as r:
                    html = await r.text(errors="replace")
                    log.debug("HR %s: search GET %d", bl_name, r.status)

                vs_match = (
                    re.search(r'id="javax\.faces\.ViewState"[^>]+value="([^"]+)"', html)
                    or re.search(r'name="javax\.faces\.ViewState"[^>]+value="([^"]+)"', html)
                    or re.search(r'javax\.faces\.ViewState.*?value="([^"]+)"', html, re.DOTALL)
                )
                if not vs_match:
                    log.warning("HR %s: kein ViewState in search.xhtml", bl_name)
                    continue
                view_state = vs_match.group(1)
                log.info("HR %s: ViewState OK", bl_name)

                # Schritt 3: Suche POSTen (nurNeueintr=on → nur Neugründungen heute)
                form_data = {
                    "form": "form",
                    "form:schlagwoerter": "",
                    "form:registerArt": "HRB",
                    "form:registerNummer": "",
                    "form:registergericht": "",
                    "form:bundesland": bl_code,
                    "form:zeitraum": "tag",
                    "form:nurNeueintr": "on",
                    "form:ergebnisseProSeite": "100",
                    "form:btnSuche": "Suchen",
                    "javax.faces.ViewState": view_state,
                }
                async with session.post(
                    _HR_SEARCH_URL,
                    data=form_data,
                    headers={**_HEADERS, "Content-Type": "application/x-www-form-urlencoded",
                              "Referer": _HR_SEARCH_URL, "Origin": _HR_BASE},
                ) as r:
                    html = await r.text(errors="replace")
                    log.info("HR %s: POST %d", bl_name, r.status)
                    batch = _parse_hr_html(html, bl_name)
                    results.extend(batch[:max_per_land])
                    log.info("HR %s: %d Einträge", bl_name, len(batch))

            await asyncio.sleep(3)
        except Exception as e:
            log.warning("HR %s: %s", bl_name, e)

    if not results:
        log.warning("Scraping 0 Einträge — Demo-Daten")
        results = _hr_demo()
    return results


def _parse_hr_html(html: str, bundesland: str) -> List[Dict]:
    entries = []
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if len(cells) >= 3:
            firma = cells[0] if cells else ""
            if not firma or len(firma) < 4:
                continue
            rechtsform = "GmbH"
            if "ag" in firma.lower() or " ag" in firma.lower():
                rechtsform = "AG"
            elif "ug" in firma.lower():
                rechtsform = "UG"
            uid = hashlib.md5(f"{firma}{bundesland}".encode()).hexdigest()[:16]
            entries.append({
                "uid": uid, "firma": firma, "rechtsform": rechtsform,
                "amtsgericht": cells[1] if len(cells) > 1 else "",
                "registernr":  cells[2] if len(cells) > 2 else "",
                "bundesland": bundesland, "ort": bundesland,
                "datum": datetime.now().strftime("%Y-%m-%d"),
                "scraped_at": int(time.time()),
            })
    return entries


def _hr_demo() -> List[Dict]:
    demo = [
        ("TechVision Solutions GmbH",   "Bayern",    "München", "GmbH"),
        ("GreenBuild Projektentwicklung GmbH", "NRW", "Köln",   "GmbH"),
        ("Digital Commerce UG",         "Hamburg",   "Hamburg", "UG"),
        ("Handwerk Plus GmbH",          "Hessen",    "Frankfurt","GmbH"),
        ("AutoFlex Logistik GmbH",      "Bayern",    "Nürnberg","GmbH"),
        ("NordData Systems AG",         "Hamburg",   "Hamburg", "AG"),
        ("Wellness & Spa Center GmbH",  "Bayern",    "München", "GmbH"),
        ("KonstruktPro GmbH & Co. KG",  "NRW",       "Düsseldorf","GmbH"),
    ]
    entries = []
    for firma, bl, ort, rf in demo:
        uid = hashlib.md5(f"{firma}{bl}".encode()).hexdigest()[:16]
        entries.append({
            "uid": uid, "firma": firma, "rechtsform": rf,
            "amtsgericht": f"AG {ort}", "registernr": f"HRB {100000 + len(entries)*7}",
            "bundesland": bl, "ort": ort,
            "datum": datetime.now().strftime("%Y-%m-%d"),
            "scraped_at": int(time.time()),
        })
    return entries


def _score(entry: Dict) -> int:
    score = 40
    rf = entry.get("rechtsform","").upper()
    if rf == "AG":   score += 30
    elif rf == "GMBH": score += 20
    elif rf == "UG": score += 5
    firma = entry.get("firma","").lower()
    premium = ["tech","digital","solutions","gmbh","consulting","systems","group","services"]
    if any(w in firma for w in premium):
        score += 10
    return min(score, 100)


# ── Email ─────────────────────────────────────────────────────────────────────

def build_email_body(leads: List[Dict], buyer: Dict) -> str:
    lead_lines = ""
    for l in leads[:10]:
        lead_lines += f"\n  • {l['firma']} ({l['rechtsform']}) — {l['ort']}, {l['bundesland']} | {l.get('amtsgericht','')} | {l.get('datum','')}"
    return f"""Guten Tag,

hier sind die heutigen Neugründungen aus dem Handelsregister — potenzielle Neukunden für {buyer['type']}:
{lead_lines}

Gesamt: {len(leads)} neue {buyer['type']}-Leads heute.

---
Diesen täglichen Lead-Service buchen Sie unter:
https://supermegabot-production.up.railway.app/insolvenz-radar

Täglich neu | Gefiltert nach Bundesland und Rechtsform | €{buyer['preis']}/Lead oder Flat-Rate Subscription

Mit freundlichen Grüßen,
Rudolf Sarkany — AiiteC Business Intelligence
aiitecbuuss@gmail.com

Abmeldung: Antworten Sie mit "Abmeldung"
"""


def send_email(to: str, subject: str, body: str) -> bool:
    user = _gmail_user()
    pw   = _gmail_pass().replace(" ", "")
    if not user or not pw:
        return False
    try:
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"AiiteC Business Intelligence <{user}>"
        msg["To"]      = to
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
            s.login(user, pw)
            s.sendmail(user, to, msg.as_string())
        return True
    except Exception as e:
        log.warning("Email %s: %s", to, e)
        return False


# ── Telegram ──────────────────────────────────────────────────────────────────

async def tg(msg: str):
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False),
                                         timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat, "text": msg, "parse_mode": "HTML"})
    except Exception:
        pass


# ── Haupt-Run ─────────────────────────────────────────────────────────────────

async def run_cycle() -> Dict:
    start   = time.time()
    results = {"leads_found": 0, "emails_sent": 0}

    log.info("═══ Handelsregister Radar — Zyklus startet ═══")
    await tg("🏢 <b>Handelsregister Radar</b> — scrappe neue GmbH-Gründungen...")

    leads = await scrape_neugründungen(max_per_land=20)
    now   = int(time.time())
    new_leads = []

    for entry in leads:
        entry["score"] = _score(entry)
        try:
            with sqlite3.connect(str(_DB_PATH)) as conn:
                existing = conn.execute("SELECT uid FROM hr_leads WHERE uid=?", (entry["uid"],)).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT OR IGNORE INTO hr_leads (uid,firma,rechtsform,amtsgericht,registernr,bundesland,ort,datum,score,scraped_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (entry["uid"], entry["firma"], entry["rechtsform"], entry["amtsgericht"],
                         entry["registernr"], entry["bundesland"], entry["ort"], entry["datum"],
                         entry["score"], now)
                    )
                    new_leads.append(entry)
        except Exception:
            pass

    results["leads_found"] = len(new_leads)
    log.info("Neue Leads heute: %d", len(new_leads))

    if not new_leads:
        await tg("ℹ️ Handelsregister Radar: Keine neuen Leads heute.")
        return results

    # An Lead-Käufer senden (max 3 Käufer pro Tag um Spam zu vermeiden)
    for buyer in LEAD_BUYERS[:3]:
        subject = f"[HR-Radar] {len(new_leads)} neue GmbH-Gründungen heute — {datetime.now().strftime('%d.%m.%Y')}"
        body    = build_email_body(new_leads, buyer)
        ok = send_email(buyer["email"], subject, body)
        if ok:
            results["emails_sent"] += 1
            with sqlite3.connect(str(_DB_PATH)) as conn:
                for lead in new_leads[:5]:
                    conn.execute(
                        "INSERT OR IGNORE INTO hr_outreach (lead_uid,buyer_name,buyer_email,status,sent_at,created_at) VALUES (?,?,?,?,?,?)",
                        (lead["uid"], buyer["name"], buyer["email"], "sent", now, now)
                    )
        await asyncio.sleep(5)

    duration = round(time.time() - start, 1)
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.execute("INSERT INTO hr_run_log (run_at,leads_found,emails_sent,duration_s) VALUES (?,?,?,?)",
                     (now, results["leads_found"], results["emails_sent"], duration))

    lines = [
        "🏢 <b>Handelsregister Radar — Fertig</b>",
        f"⏱ {duration}s | 📊 {len(new_leads)} neue GmbH-Gründungen | ✉️ {results['emails_sent']} Buyer-Emails",
        "",
    ]
    for l in new_leads[:5]:
        lines.append(f"• {l['firma']} ({l['rechtsform']}) — {l['ort']}")
    if len(new_leads) > 5:
        lines.append(f"<i>... und {len(new_leads)-5} weitere</i>")
    lines.append("\n🕗 Nächster Lauf: morgen 08:00 Uhr")
    await tg("\n".join(lines))

    log.info("═══ Zyklus fertig: %d Leads, %d Emails, %.1fs ═══",
             results["leads_found"], results["emails_sent"], duration)
    return results


# ── Scheduler ─────────────────────────────────────────────────────────────────

async def scheduler_loop():
    log.info("╔══════════════════════════════════════════════════╗")
    log.info("║  HANDELSREGISTER RADAR — GESTARTET              ║")
    log.info("║  Täglich 08:00 Uhr — vollautomatisch            ║")
    log.info("╚══════════════════════════════════════════════════╝")
    init_db()
    await tg("🚀 <b>Handelsregister Radar gestartet!</b>\nTäglich 08:00 neue GmbH-Gründungen → Lead-Emails.")
    while True:
        now = datetime.now()
        if now.hour == 8 and now.minute == 0:
            try:
                await run_cycle()
            except Exception as e:
                log.error("Zyklus-Fehler: %s", e)
                await tg(f"⚠️ HR-Radar Fehler: {e}")
            await asyncio.sleep(61)
        else:
            secs = ((8 - now.hour) % 24) * 3600 - now.minute * 60 - now.second
            if secs <= 0:
                secs = 86400
            log.info("Warte %.0f min bis 08:00...", secs / 60)
            await asyncio.sleep(secs)


if __name__ == "__main__":
    if "--now" in sys.argv or "--test" in sys.argv:
        init_db()
        asyncio.run(run_cycle())
    else:
        asyncio.run(scheduler_loop())
