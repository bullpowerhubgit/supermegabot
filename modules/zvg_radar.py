#!/usr/bin/env python3
"""
ZVG Zwangsversteigerung Radar — Vollautomatischer B2B Lead-Agent
===============================================================
80.000+ Zwangsversteigerungen/Jahr in Deutschland. Öffentliches Portal.
Wir scrapen täglich alle neuen Verfahren und verkaufen Leads an:
  - Rechtsanwälte (€30-100/Lead)
  - Banken/Kreditinstitute (€50-150/Lead)
  - Immobilienmakler (€20-50/Lead)
  - Investoren/Fix&Flip (€30-80/Lead)

90% der Code-Basis kommt aus insolvenz_radar.py — Bruder-Tool.

Starten:
  python3 modules/zvg_radar.py          # Dauerbetrieb (tägl. 07:00)
  python3 modules/zvg_radar.py --now    # Sofortiger Test-Run
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
    format="%(asctime)s [ZVG-RADAR] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("ZVGRadar")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "zvg_radar.db"


def _load_env():
    env_file = _BASE / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

def _gmail_user() -> str: return os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")
def _gmail_pass() -> str: return os.getenv("GMAIL_APP_PASSWORD_AIITEC", "rqcd uzim npsl odgw")
def _tg_token()   -> str: return os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
def _tg_chat()    -> str: return os.getenv("TELEGRAM_CHAT_ID", "")


# ── Lead-Käufer ───────────────────────────────────────────────────────────────
LEAD_BUYERS = [
    {"name": "DVAG Rechtsschutz-Partner",         "email": "recht@dvag.de",                 "type": "Rechtsanwalt",  "preis": 50},
    {"name": "Sparkasse Immobilien Zentrale",      "email": "immobilien@sparkasse.de",        "type": "Bank",          "preis": 80},
    {"name": "Volksbank Gewerbeinvestment",        "email": "investment@volksbank.de",         "type": "Bank",          "preis": 80},
    {"name": "ImmobilienScout24 Makler-Partner",  "email": "makler@immobilienscout24.de",    "type": "Makler",        "preis": 35},
    {"name": "Engel & Völkers Investment",         "email": "investment@engelvoelkers.com",   "type": "Makler",        "preis": 45},
    {"name": "Deutsche Zwangsversteigerungs-GmbH","email": "info@deutsche-zvg.de",            "type": "Spezialist",    "preis": 100},
]

# ── Objekt-Typen Scoring ──────────────────────────────────────────────────────
OBJEKT_WERTUNG = {
    "Einfamilienhaus":   85, "Mehrfamilienhaus":  95, "Gewerbeobjekt":    90,
    "Eigentumswohnung":  75, "Grundstück":        70, "Gewerbe":          88,
    "Industrie":         80, "Bürogebäude":       85, "Gastronomie":      72,
    "Hotel":             88, "Wohnung":           75, "Haus":             80,
}


# ── DB ────────────────────────────────────────────────────────────────────────

def init_db():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(_DB_PATH)) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS zvg_leads (
            uid          TEXT PRIMARY KEY,
            gericht      TEXT,
            aktenzeichen TEXT,
            objekt_typ   TEXT,
            objekt_adresse TEXT,
            bundesland   TEXT,
            verkehrswert TEXT,
            termin_datum TEXT,
            score        INTEGER DEFAULT 0,
            ai_summary   TEXT,
            scraped_at   INTEGER
        );
        CREATE TABLE IF NOT EXISTS zvg_outreach (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_uid     TEXT,
            buyer_name   TEXT,
            buyer_email  TEXT,
            status       TEXT DEFAULT 'pending',
            sent_at      INTEGER,
            created_at   INTEGER,
            UNIQUE(lead_uid, buyer_email)
        );
        CREATE TABLE IF NOT EXISTS zvg_run_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at       INTEGER,
            leads_found  INTEGER DEFAULT 0,
            high_value   INTEGER DEFAULT 0,
            emails_sent  INTEGER DEFAULT 0,
            duration_s   REAL
        );
        """)


# ── Scraper ───────────────────────────────────────────────────────────────────
# zvg-portal.de Bundesland-Codes
BUNDESLAENDER_ZVG = {
    "Bayern":              "BY",
    "Nordrhein-Westfalen": "NW",
    "Baden-Württemberg":   "BW",
    "Hessen":              "HE",
    "Hamburg":             "HH",
    "Berlin":              "BE",
}

async def scrape_zvg(max_per_land: int = 15) -> List[Dict]:
    """Scrapt zvg-portal.de für neue Zwangsversteigerungen."""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept":     "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9",
        "Referer":    "https://www.zvg-portal.de/",
    }

    try:
        async with aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(ssl=False)
        ) as session:
            for bl_name, bl_code in list(BUNDESLAENDER_ZVG.items())[:4]:
                try:
                    # Formular POST für Suche
                    data = {
                        "button": "Suchen",
                        "land_abk":        bl_code,
                        "gericht":         "",
                        "strasse":         "",
                        "hnr":             "",
                        "plz":             "",
                        "ort":             "",
                        "aktenzeichen":    "",
                        "objekt":          "",
                        "von":             "",
                        "bis":             "",
                        "TerminDatumVon":  "",
                        "TerminDatumBis":  "",
                    }
                    async with session.post(
                        "https://www.zvg-portal.de/index.php?button=Suchen",
                        data=data
                    ) as r:
                        if r.status == 200:
                            html = await r.text(errors="replace")
                            batch = _parse_zvg_html(html, bl_name)
                            results.extend(batch[:max_per_land])
                            log.info("ZVG %s: %d Objekte", bl_name, len(batch))
                    await asyncio.sleep(2.5)
                except Exception as e:
                    log.debug("ZVG %s: %s", bl_name, e)
    except Exception as e:
        log.warning("ZVG Session: %s", e)

    if not results:
        log.warning("ZVG-Portal: Scraping ergab 0 Ergebnisse — kein Outreach heute")
    return results


def _parse_zvg_html(html: str, bundesland: str) -> List[Dict]:
    entries = []
    # Suche nach typischen ZVG-Portal Tabellenzeilen
    rows = re.findall(r'<tr[^>]*class="[^"]*(?:odd|even|zeile)[^"]*"[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    if not rows:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)

    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        cells = [re.sub(r'\s+', ' ', c) for c in cells]
        if len(cells) >= 4:
            gericht  = cells[0] if cells else ""
            aktenzeichen = cells[1] if len(cells) > 1 else ""
            objekt   = cells[2] if len(cells) > 2 else ""
            termin   = cells[3] if len(cells) > 3 else ""
            wert     = cells[4] if len(cells) > 4 else ""

            if not gericht or len(gericht) < 3:
                continue
            if not re.search(r'[A-Z]', gericht[:3]):
                continue

            uid = hashlib.md5(f"{gericht}{aktenzeichen}{objekt}".encode()).hexdigest()[:16]
            entries.append({
                "uid": uid, "gericht": gericht, "aktenzeichen": aktenzeichen,
                "objekt_typ": _detect_objekt_typ(objekt),
                "objekt_adresse": objekt, "bundesland": bundesland,
                "verkehrswert": wert, "termin_datum": termin,
                "scraped_at": int(time.time()),
            })
    return entries[:30]


def _detect_objekt_typ(text: str) -> str:
    text_low = text.lower()
    if any(w in text_low for w in ["einfamilienhaus", "efh", "einf."]):
        return "Einfamilienhaus"
    if any(w in text_low for w in ["mehrfamilienhaus", "mfh", "mehrfam."]):
        return "Mehrfamilienhaus"
    if any(w in text_low for w in ["eigentumswohnung", "etw", "wohnung"]):
        return "Eigentumswohnung"
    if any(w in text_low for w in ["gewerbe", "laden", "büro", "praxis"]):
        return "Gewerbeobjekt"
    if any(w in text_low for w in ["grundstück", "flurstück"]):
        return "Grundstück"
    if any(w in text_low for w in ["industrie", "halle", "lager"]):
        return "Industrie"
    if any(w in text_low for w in ["hotel", "pension"]):
        return "Hotel"
    if any(w in text_low for w in ["restaurant", "gastro", "gaststätte"]):
        return "Gastronomie"
    return "Immobilie"


def _score(entry: Dict) -> int:
    return OBJEKT_WERTUNG.get(entry.get("objekt_typ",""), 60)


# ── AI Analyse ────────────────────────────────────────────────────────────────

async def enrich_with_ai(entry: Dict) -> str:
    from modules.ai_client import ai_complete
    prompt = f"""Zwangsversteigerung in Deutschland.
Objekt: {entry['objekt_typ']} in {entry['objekt_adresse']}
Gericht: {entry['gericht']} | Az: {entry['aktenzeichen']}
Verkehrswert: {entry.get('verkehrswert','unbekannt')} | Termin: {entry.get('termin_datum','?')}

Schreibe 1 Satz (max 50 Wörter) auf Deutsch: Warum ist das für Investoren/Banken/Anwälte interessant?
Nur den Satz, kein JSON."""
    text = await ai_complete(prompt, system="", max_tokens=100)
    if text:
        return text.strip()
    return f"{entry['objekt_typ']} — Verkehrswert {entry.get('verkehrswert','?')}, Termin {entry.get('termin_datum','?')}"


# ── Email ─────────────────────────────────────────────────────────────────────

def build_zvg_email(leads: List[Dict], buyer: Dict) -> tuple[str, str]:
    lead_lines = ""
    for l in leads[:8]:
        wert = l.get("verkehrswert","?")
        lead_lines += f"\n  • {l['objekt_typ']} | {l.get('objekt_adresse','?')} | Verkehrswert: {wert} | Termin: {l.get('termin_datum','?')} | Az: {l.get('aktenzeichen','')}"

    subject = f"[ZVG-Radar] {len(leads)} neue Zwangsversteigerungen heute — {datetime.now().strftime('%d.%m.%Y')}"
    body = f"""Guten Tag,

hier sind die heutigen Neuzugänge im ZVG-Portal — aufbereitet für {buyer['type']}:
{lead_lines}

Gesamt: {len(leads)} neue Verfahren heute | Hochwertige Objekte (Score≥80): {sum(1 for l in leads if l.get('score',0)>=80)}

---
Täglicher ZVG-Lead-Service:
https://supermegabot-production.up.railway.app/insolvenz-radar

Preismodelle: €{buyer['preis']}/Lead einzeln | €199/mo unbegrenzt | €499/mo mit AI-Analyse

Mit freundlichen Grüßen,
Rudolf Sarkany — AiiteC Business Intelligence
aiitecbuuss@gmail.com

Abmeldung: Antworten Sie mit "Abmeldung"
"""
    return subject, body


def send_email(to: str, subject: str, body: str) -> bool:
    from modules.gmail_accounts import send_email as ga_send
    ok, via = ga_send(to, subject, body)
    if ok:
        log.info("Email → %s via %s", to, via)
    return ok


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


# ── Haupt-Run ─────────────────────────────────────────────────────────────────

async def run_cycle() -> Dict:
    init_db()
    start   = time.time()
    results = {"leads_found": 0, "high_value": 0, "emails_sent": 0}

    log.info("═══ ZVG Radar — Zyklus startet ═══")
    await tg("🏚 <b>ZVG Radar</b> — scrappe Zwangsversteigerungsportal...")

    raw = await scrape_zvg(max_per_land=15)
    now = int(time.time())
    new_leads = []

    for entry in raw:
        entry["score"] = _score(entry)
        with sqlite3.connect(str(_DB_PATH)) as conn:
            existing = conn.execute("SELECT uid FROM zvg_leads WHERE uid=?", (entry["uid"],)).fetchone()
            if not existing:
                # AI Summary nur für hochwertige Objekte
                if entry["score"] >= 75:
                    entry["ai_summary"] = await enrich_with_ai(entry)
                    await asyncio.sleep(0.3)
                else:
                    entry["ai_summary"] = ""
                conn.execute(
                    "INSERT OR IGNORE INTO zvg_leads (uid,gericht,aktenzeichen,objekt_typ,objekt_adresse,bundesland,verkehrswert,termin_datum,score,ai_summary,scraped_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (entry["uid"], entry["gericht"], entry["aktenzeichen"], entry["objekt_typ"],
                     entry["objekt_adresse"], entry["bundesland"], entry["verkehrswert"],
                     entry["termin_datum"], entry["score"], entry.get("ai_summary",""), now)
                )
                new_leads.append(entry)

    new_leads.sort(key=lambda x: x["score"], reverse=True)
    results["leads_found"] = len(new_leads)
    results["high_value"]  = sum(1 for l in new_leads if l["score"] >= 80)

    log.info("Neue Objekte: %d (davon %d hochwertig)", len(new_leads), results["high_value"])

    # Sofort-Alert für sehr hochwertige Objekte (Score ≥ 90)
    premium = [l for l in new_leads if l["score"] >= 90]
    if premium:
        lines = ["🏆 <b>ZVG PREMIUM-ALERTS</b> — hochwertige Objekte:\n"]
        for p in premium[:5]:
            lines.append(f"• {p['objekt_typ']} | {p.get('objekt_adresse','?')}")
            lines.append(f"  Verkehrswert: {p.get('verkehrswert','?')} | Termin: {p.get('termin_datum','?')}")
            if p.get("ai_summary"):
                lines.append(f"  💡 {p['ai_summary']}")
            lines.append("")
        await tg("\n".join(lines))

    if not new_leads:
        await tg("ℹ️ ZVG Radar: Keine neuen Objekte heute.")
        return results

    # Lead-Emails senden
    for buyer in LEAD_BUYERS[:2]:
        subject, body = build_zvg_email(new_leads, buyer)
        with sqlite3.connect(str(_DB_PATH)) as conn:
            already = conn.execute(
                "SELECT id FROM zvg_outreach WHERE buyer_email=? AND lead_uid=?",
                (buyer["email"], new_leads[0]["uid"])
            ).fetchone()
        if not already:
            ok = send_email(buyer["email"], subject, body)
            if ok:
                results["emails_sent"] += 1
                with sqlite3.connect(str(_DB_PATH)) as conn:
                    for lead in new_leads[:5]:
                        conn.execute(
                            "INSERT OR IGNORE INTO zvg_outreach (lead_uid,buyer_name,buyer_email,status,sent_at,created_at) VALUES (?,?,?,?,?,?)",
                            (lead["uid"], buyer["name"], buyer["email"], "sent", now, now)
                        )
            await asyncio.sleep(5)

    duration = round(time.time() - start, 1)
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.execute("INSERT INTO zvg_run_log (run_at,leads_found,high_value,emails_sent,duration_s) VALUES (?,?,?,?,?)",
                     (now, results["leads_found"], results["high_value"], results["emails_sent"], duration))

    lines = [
        "🏚 <b>ZVG Radar — Zyklus fertig</b>",
        f"⏱ {duration}s | 📊 {results['leads_found']} Objekte | 🏆 {results['high_value']} hochwertig",
        f"✉️ {results['emails_sent']} Lead-Emails gesendet",
        "\n🕖 Nächster Lauf: morgen 07:00 Uhr",
    ]
    await tg("\n".join(lines))

    log.info("═══ Fertig: %d Leads, %d hochwertig, %.1fs ═══",
             results["leads_found"], results["high_value"], duration)
    return results


# ── run_zvg_cycle: Wrapper mit normiertem Rückgabe-Dict ───────────────────────

async def run_zvg_cycle() -> dict:
    """
    Normierter Wrapper um run_cycle() — gibt standardisiertes Dict zurück
    für den Scheduler-Task task_zvg_radar.

    Returns:
        {new_leads, total_scanned, high_value, emails_sent, status}
    """
    try:
        result = await run_cycle()
        return {
            "new_leads":     result.get("leads_found", 0),
            "total_scanned": result.get("leads_found", 0),
            "high_value":    result.get("high_value", 0),
            "emails_sent":   result.get("emails_sent", 0),
            "status":        "ok",
        }
    except Exception as exc:
        log.error("run_zvg_cycle: %s", exc)
        return {
            "new_leads":     0,
            "total_scanned": 0,
            "high_value":    0,
            "emails_sent":   0,
            "status":        f"error: {exc}",
        }


# ── Scheduler ─────────────────────────────────────────────────────────────────

async def scheduler_loop():
    log.info("╔══════════════════════════════════════════════════╗")
    log.info("║  ZVG RADAR — GESTARTET                          ║")
    log.info("║  Täglich 07:00 Uhr — vollautomatisch            ║")
    log.info("╚══════════════════════════════════════════════════╝")
    init_db()
    await tg("🚀 <b>ZVG Radar gestartet!</b>\nTäglich 07:00 Uhr — neue Zwangsversteigerungen → Lead-Emails.")
    while True:
        now = datetime.now()
        if now.hour == 7 and now.minute == 0:
            try:
                await run_cycle()
            except Exception as e:
                log.error("Fehler: %s", e)
                await tg(f"⚠️ ZVG Radar Fehler: {e}")
            await asyncio.sleep(61)
        else:
            secs = ((7 - now.hour) % 24) * 3600 - now.minute * 60 - now.second
            if secs <= 0: secs = 86400
            log.info("Warte %.0f min bis 07:00...", secs / 60)
            await asyncio.sleep(secs)


try:
    init_db()
except Exception as _e:
    import logging as _log; _log.getLogger("ZVGRadar").warning("init_db at import: %s", _e)

if __name__ == "__main__":
    if "--now" in sys.argv or "--test" in sys.argv:
        asyncio.run(run_cycle())
    else:
        asyncio.run(scheduler_loop())
