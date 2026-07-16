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
def _gmail_pass() -> str: return os.getenv("GMAIL_APP_PASSWORD_AIITEC", "rqcd uzim npsl odgw")
def _tg_token()   -> str: return os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
def _tg_chat()    -> str: return os.getenv("TELEGRAM_CHAT_ID", "")


# ── Subscriber-Liste (wer kauft unsere Leads) ─────────────────────────────────
LEAD_BUYERS = [
    # kontakt@stbv.de ENTFERNT — Bounce 2026-07-13
    # vertrieb@datev.de ENTFERNT — Bounce 2026-07-13
    # partner@lexware.de ENTFERNT — Bounce 2026-07-13
    {"name": "SevDesk Partnerteam",           "email": "partner@sevdesk.de",            "type": "Buchh-SaaS",      "preis": 12},
    # HDI/Allianz generische Adressen oft nicht zustellbar — deaktiviert
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
    "Berlin":            "BE",
}

_HR_BASE        = "https://www.handelsregister.de"
_HR_WELCOME_URL = "https://www.handelsregister.de/rp_web/welcome.xhtml"
_HR_BKM_URL     = "https://www.handelsregister.de/rp_web/bekanntmachungen/welcome.xhtml"
# Kategorien die KEINE Leads sind (Löschungen)
_SKIP_KATEGORIEN = {"Löschungsankündigung"}

async def _get_bkm_session() -> tuple:
    """Gibt (session, bkm_url, vs) zurück — vollständige JSF-Navigation zu Bekanntmachungen."""
    H_BASE = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
        "Accept-Language": "de-DE,de;q=0.9",
    }
    session = aiohttp.ClientSession(
        headers=H_BASE,
        timeout=aiohttp.ClientTimeout(total=45),
        cookie_jar=aiohttp.CookieJar(),
    )
    # Schritt 1: Welcome → JSESSIONID + headerForm ViewState
    async with session.get(_HR_WELCOME_URL) as r:
        html = await r.text(errors="replace")

    hf_action_m = re.search(r'id="headerForm"[^>]+action="([^"]+)"', html)
    vs_m = re.search(r'name="javax\.faces\.ViewState"[^>]+value="([^"]+)"', html)
    bkm_m = re.search(r"Registerbekanntmachungen.*?addSubmitParam\([^)]+\{([^}]+)\}", html, re.DOTALL)
    if not (hf_action_m and vs_m and bkm_m):
        await session.close()
        return None, None, None

    full_hf = _HR_BASE + hf_action_m.group(1)
    vs = vs_m.group(1)
    bkm_params = dict(re.findall(r"'([^']+)':'([^']+)'", bkm_m.group(1)))

    await asyncio.sleep(0.5)

    # Schritt 2: navigate to Bekanntmachungen
    async with session.post(full_hf,
                            data={"headerForm": "headerForm", "javax.faces.ViewState": vs, **bkm_params},
                            headers={"Content-Type": "application/x-www-form-urlencoded",
                                     "Origin": _HR_BASE}) as r:
        html2 = await r.text(errors="replace")
        bkm_url = str(r.url)

    vs2_m = re.search(r'name="javax\.faces\.ViewState"[^>]+value="([^"]+)"', html2)
    if not vs2_m:
        await session.close()
        return None, None, None

    return session, bkm_url, vs2_m.group(1)


async def scrape_neugründungen(max_per_land: int = 20) -> List[Dict]:
    """Scrapt Registerbekanntmachungen von heute via JSF-AJAX (3-Schritt-Flow)."""
    from datetime import date
    today = date.today().strftime("%d.%m.%Y")
    results = []

    for bl_name, bl_code in list(BUNDESLAENDER_HR.items())[:3]:
        session = None
        try:
            for _attempt in range(2):
                session, bkm_url, vs = await _get_bkm_session()
                if session:
                    break
                await asyncio.sleep(2)
            if not session:
                log.warning("HR %s: Session-Aufbau fehlgeschlagen", bl_name)
                continue

            await asyncio.sleep(0.5)

            # Schritt 3: AJAX-Filter POST
            ajax_data = {
                "bekanntMachungenForm": "bekanntMachungenForm",
                "bekanntMachungenForm:datum_von_input": today,
                "bekanntMachungenForm:datum_bis_input": today,
                "bekanntMachungenForm:land_input": bl_code,
                "bekanntMachungenForm:land_focus": "",
                "bekanntMachungenForm:registergericht_input": "",
                "bekanntMachungenForm:registergericht_focus": "",
                "bekanntMachungenForm:registergericht_filter": "",
                "bekanntMachungenForm:sitz": "",
                "bekanntMachungenForm:kategorie_input": "",
                "bekanntMachungenForm:kategorie_focus": "",
                "bekanntMachungenForm:kategorie_filter": "",
                "javax.faces.partial.ajax": "true",
                "javax.faces.source": "bekanntMachungenForm:rrbSuche",
                "javax.faces.partial.execute": "bekanntMachungenForm",
                "javax.faces.partial.render": "bekanntMachungenForm",
                "bekanntMachungenForm:rrbSuche": "bekanntMachungenForm:rrbSuche",
                "javax.faces.ViewState": vs,
            }
            ajax_headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Accept": "application/xml, text/xml, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Faces-Request": "partial/ajax",
                "Origin": _HR_BASE,
                "Referer": bkm_url,
            }
            async with session.post(bkm_url, data=ajax_data, headers=ajax_headers) as r:
                xml_resp = await r.text(errors="replace")
                log.info("HR %s: AJAX %d", bl_name, r.status)

            batch = _parse_bkm_xml(xml_resp, bl_name, today)
            results.extend(batch[:max_per_land])
            log.info("HR %s: %d Bekanntmachungen heute", bl_name, len(batch))

        except Exception as e:
            log.warning("HR %s: %s", bl_name, e)
        finally:
            if session:
                await session.close()

        await asyncio.sleep(3)

    if not results:
        log.warning("Handelsregister: Scraping ergab 0 Ergebnisse — kein Outreach heute")
    return results


def _parse_bkm_xml(xml_resp: str, bundesland: str, datum: str) -> List[Dict]:
    """Parst die PrimeFaces AJAX-XML-Antwort aus Registerbekanntmachungen."""
    entries = []
    # CDATA aus partial-response extrahieren
    cdata_m = re.search(r'<!\[CDATA\[(.*?)\]\]>', xml_resp, re.DOTALL)
    if not cdata_m:
        return entries
    html = cdata_m.group(1)

    # Label-Elemente = ein Eintrag pro Bekanntmachung
    # Nur Labels mit Amtsgericht/HRB-Inhalt (nicht Form-Feld-Labels)
    labels = [l for l in re.findall(r'<label[^>]+class="ui-outputlabel[^"]*"[^>]*>(.*?)</label>', html, re.DOTALL)
              if re.search(r'Amtsgericht|HR[ABCGPVR]|Sonstige|Einreichung|Bekanntmachung|Löschung', l)]
    for raw in labels:
        # <br> → \n vor dem Tag-Stripping, sonst alles auf einer Zeile
        normalized = re.sub(r'<br\s*/?>', '\n', raw, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', normalized).strip()
        parts = [p.strip() for p in text.split('\n') if p.strip()]
        if len(parts) < 2:
            continue

        kategorie = parts[0].strip()
        if kategorie in _SKIP_KATEGORIEN:
            continue

        # Zeile 2: "Bayern Amtsgericht München HRB 226327"
        reg_line = parts[1] if len(parts) > 1 else ""
        reg_m = re.search(r'(HR[ABCGPV]|GnR|VR|PR)\s+(\d+)', reg_line)
        registernr = f"{reg_m.group(1)} {reg_m.group(2)}" if reg_m else ""
        ag_m = re.search(r'Amtsgericht\s+(\S+)', reg_line)
        amtsgericht = ag_m.group(1) if ag_m else ""

        # Zeile 3: "Firma – Ort"
        firma_line = parts[2] if len(parts) > 2 else parts[1]
        if ' – ' in firma_line:
            firma, ort = firma_line.split(' – ', 1)
        elif ' - ' in firma_line:
            firma, ort = firma_line.split(' - ', 1)
        else:
            firma, ort = firma_line, bundesland
        firma = firma.strip()
        ort = ort.strip()

        if not firma or len(firma) < 3:
            continue

        rechtsform = "GmbH"
        fl = firma.lower()
        if " ag" in fl or fl.endswith(" ag"):
            rechtsform = "AG"
        elif "ug " in fl or "ug (" in fl:
            rechtsform = "UG"
        elif "kg" in fl:
            rechtsform = "KG"

        uid = hashlib.md5(f"{firma}{bundesland}{registernr}".encode()).hexdigest()[:16]
        entries.append({
            "uid": uid, "firma": firma, "rechtsform": rechtsform,
            "amtsgericht": amtsgericht, "registernr": registernr,
            "bundesland": bundesland, "ort": ort,
            "datum": datum, "kategorie": kategorie,
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
    from modules.gmail_accounts import send_email as ga_send
    ok, via = ga_send(to, subject, body)
    if ok:
        log.info("Email → %s via %s", to, via)
    return ok


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
    init_db()
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

    # An Lead-Käufer senden (max 3 Käufer pro Tag, jeder Buyer NUR 1x pro Tag)
    today_start = int(datetime.combine(date.today(), datetime.min.time()).timestamp())
    for buyer in LEAD_BUYERS[:3]:
        # Tages-Dedup: buyer bereits heute kontaktiert?
        with sqlite3.connect(str(_DB_PATH)) as conn:
            already = conn.execute(
                "SELECT 1 FROM hr_outreach WHERE buyer_email=? AND sent_at>=? LIMIT 1",
                (buyer["email"], today_start)
            ).fetchone()
        if already:
            log.info("HR-Radar: %s heute bereits kontaktiert — überspringe", buyer["email"])
            continue
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
