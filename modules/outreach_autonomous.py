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
import xml.etree.ElementTree as ET
from urllib.parse import unquote

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

def _gmail_user() -> str: return os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")
def _gmail_pass() -> str: return os.getenv("GMAIL_APP_PASSWORD_AIITEC", "rqcd uzim npsl odgw")
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
    # ── Factoring Deutschland ─────────────────────────────────────────────────
    {"name": "BFS finance GmbH",                  "email": "info@bfs-finance.de",                "type": "Factoring"},
    {"name": "Deutsche Factoring Bank",            "email": "info@deutsche-factoring.de",         "type": "Factoring"},
    {"name": "Bibby Financial Services DE",        "email": "info@bibbyfinancialservices.de",     "type": "Factoring"},
    {"name": "Grenke Factoring",                   "email": "factoring@grenke.de",               "type": "Factoring"},
    {"name": "abcfinance GmbH",                    "email": "info@abcfinance.de",                "type": "Factoring"},
    {"name": "Eurofactor AG",                      "email": "info@eurofactor.de",                "type": "Factoring"},
    {"name": "Dresdner Factoring AG",              "email": "info@dresdner-factoring.de",        "type": "Factoring"},
    {"name": "GE Capital Factoring",               "email": "info@gecapital.de",                 "type": "Factoring"},
    {"name": "TARGO Commercial Finance",           "email": "info@targo-cf.de",                  "type": "Factoring"},
    {"name": "Volksbank Factoring GmbH",           "email": "factoring@volksbank.de",            "type": "Factoring"},
    {"name": "Axa Factoring",                      "email": "kontakt@axa-factoring.de",          "type": "Factoring"},
    {"name": "SüdFactoring GmbH",                  "email": "info@suedfactoring.de",             "type": "Factoring"},
    {"name": "Coface Deutschland",                 "email": "info@coface.de",                    "type": "Kreditversicherung"},
    {"name": "Euler Hermes Deutschland",           "email": "info@eulerhermes.de",               "type": "Kreditversicherung"},
    {"name": "Atradius Kreditversicherung",        "email": "info@atradius.de",                  "type": "Kreditversicherung"},
    {"name": "R+V Kreditversicherung",             "email": "kreditversicherung@ruv.de",         "type": "Kreditversicherung"},
    {"name": "HDI Global SE",                      "email": "info@hdi.global",                   "type": "Kreditversicherung"},
    # ── Inkasso / Forderungsmanagement ───────────────────────────────────────
    {"name": "Arvato Financial Solutions",         "email": "kontakt@arvato-financial.de",       "type": "Inkasso"},
    {"name": "EOS Gruppe",                         "email": "info@eos-solutions.de",             "type": "Inkasso"},
    {"name": "Creditreform",                       "email": "info@creditreform.de",              "type": "Kredit-Auskunft"},
    {"name": "SCHUFA Holding AG",                  "email": "info@schufa.de",                    "type": "Kredit-Auskunft"},
    {"name": "Boniversum GmbH",                    "email": "info@boniversum.de",                "type": "Kredit-Auskunft"},
    {"name": "CRIF Bürgel GmbH",                   "email": "info@crifbuergel.de",               "type": "Kredit-Auskunft"},
    {"name": "Intrum GmbH",                        "email": "info@intrum.de",                    "type": "Inkasso"},
    {"name": "Lowell Financial Services",          "email": "info@lowell.de",                    "type": "Inkasso"},
    {"name": "Hoist Finance Germany",              "email": "info@hoistfinance.de",              "type": "Inkasso"},
    {"name": "PRA Group Deutschland",              "email": "info@pragroup.de",                  "type": "Inkasso"},
    {"name": "PAIR Finance GmbH",                  "email": "hello@pairfinance.com",             "type": "Inkasso"},
    {"name": "Riverty Group GmbH",                 "email": "info@riverty.com",                  "type": "Inkasso"},
    # ── Insolvenzverwalter / Restrukturierung ────────────────────────────────
    {"name": "Pluta Rechtsanwalts GmbH",           "email": "info@pluta.net",                    "type": "Insolvenzverwalter"},
    {"name": "Anchor Rechtsanwälte",               "email": "info@anchor.de",                    "type": "Insolvenzverwalter"},
    {"name": "Schultze & Braun GmbH",              "email": "info@schultze-braun.de",            "type": "Insolvenzverwalter"},
    {"name": "Görg Partnerschaft",                 "email": "info@goerg.de",                     "type": "Insolvenzverwalter"},
    {"name": "hww Unternehmensberatung",            "email": "info@hww-unternehmensberatung.de",  "type": "Restrukturierung"},
    {"name": "Roland Berger GmbH",                 "email": "munich@rolandberger.com",           "type": "Restrukturierung"},
    {"name": "FTI-Andersch AG",                    "email": "info@fti-andersch.com",             "type": "Restrukturierung"},
    {"name": "Alvarez & Marsal Germany",           "email": "frankfurt@alvarezandmarsal.com",    "type": "Restrukturierung"},
    {"name": "Buchalik Brömmekamp",               "email": "info@buchalik-broemmekamp.de",       "type": "Insolvenzverwalter"},
    {"name": "Jaffé Rechtsanwälte",               "email": "muenchen@jaffe.de",                  "type": "Insolvenzverwalter"},
    # ── M&A / Distress-Investoren ────────────────────────────────────────────
    {"name": "GFKL Financial Services",            "email": "info@gfkl.com",                     "type": "M&A"},
    {"name": "Deutsche Beteiligungs AG",           "email": "info@dbag.de",                      "type": "M&A"},
    {"name": "Mutares SE & Co. KGaA",             "email": "ir@mutares.de",                      "type": "M&A"},
    {"name": "Aurelius Equity Opportunities",      "email": "info@aurelius-group.com",           "type": "M&A"},
    {"name": "Triton Partners",                    "email": "info@triton-partners.com",          "type": "M&A"},
    {"name": "Silverfleet Capital",               "email": "info@silverfleetcapital.com",        "type": "M&A"},
    {"name": "IK Partners GmbH",                  "email": "germany@ikpartners.com",            "type": "M&A"},
    # ── Steuerberater mit Insolvenz-Fokus ────────────────────────────────────
    {"name": "Rödl & Partner GmbH",               "email": "info@roedl.de",                     "type": "Steuerberatung"},
    {"name": "PKF Deutschland GmbH",              "email": "info@pkf.de",                       "type": "Steuerberatung"},
    {"name": "TPA Gruppe",                        "email": "deutschland@tpa-group.com",         "type": "Steuerberatung"},
    {"name": "Ebner Stolz GmbH",                  "email": "info@ebnerstolz.de",               "type": "Steuerberatung"},
    {"name": "Baker Tilly GmbH",                  "email": "info@bakertilly.de",               "type": "Steuerberatung"},
    {"name": "Mazars GmbH",                       "email": "info@mazars.de",                   "type": "Steuerberatung"},
    {"name": "Forvis Mazars Germany",             "email": "kontakt@forvismazars.com",         "type": "Steuerberatung"},
    {"name": "Warth & Klein Grant Thornton",      "email": "info@wkgt.com",                    "type": "Steuerberatung"},
]


# ── Insolvenz-Scraper (Multi-Source: Google News RSS + HR-DB + Northdata) ──────

async def scrape_insolvencies(max_entries: int = 30) -> List[Dict]:
    """Echte Daten aus 3 Quellen — kein Demo-Fallback."""
    entries: List[Dict] = []

    # Quelle 1: Google News RSS — aktuelle Insolvenzmeldungen DE
    try:
        gnews = await _scrape_google_news_rss()
        entries.extend(gnews)
        log.info("Google News RSS: %d Einträge", len(gnews))
    except Exception as e:
        log.warning("Google News: %s", e)

    # Quelle 2: Handelsregister-DB — neue GmbH-Gründungen (immer Lead-Potenzial)
    try:
        hr = _read_handelsregister_db(limit=15)
        entries.extend(hr)
        log.info("Handelsregister-DB: %d Einträge", len(hr))
    except Exception as e:
        log.warning("HR-DB: %s", e)

    # Quelle 3: Northdata Web-Suche — Insolvenz-Firmen
    if len(entries) < 5:
        try:
            nd = await _scrape_northdata()
            entries.extend(nd)
            log.info("Northdata: %d Einträge", len(nd))
        except Exception as e:
            log.warning("Northdata: %s", e)

    # Dedup via UID
    seen: set = set()
    unique: List[Dict] = []
    for e in entries:
        if e["uid"] not in seen:
            seen.add(e["uid"])
            unique.append(e)

    if not unique:
        log.warning("Alle Quellen leer — heute kein Outreach-Lauf möglich")

    return unique[:max_entries]


async def _scrape_google_news_rss() -> List[Dict]:
    """Google News RSS für deutsche Insolvenzmeldungen — kein JS nötig."""
    results: List[Dict] = []
    queries = [
        "Insolvenz+GmbH+Deutschland",
        "Insolvenzantrag+GmbH+insolvent",
    ]

    for query in queries:
        url = f"https://news.google.com/rss/search?q={query}&hl=de&gl=DE&ceid=DE:de"
        try:
            async with aiohttp.ClientSession(
                headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"},
                timeout=aiohttp.ClientTimeout(total=15),
                connector=aiohttp.TCPConnector(ssl=False)
            ) as s:
                async with s.get(url) as r:
                    if r.status != 200:
                        log.debug("GNews %s → HTTP %s", query, r.status)
                        continue
                    content = await r.text(errors="replace")

            root = ET.fromstring(content)
            channel = root.find("channel")
            if not channel:
                continue

            for item in channel.findall("item")[:15]:
                title = item.findtext("title") or ""
                desc  = item.findtext("description") or ""
                pub   = item.findtext("pubDate") or ""
                full  = title + " " + desc

                company = _extract_company_from_news(full)
                if not company:
                    continue

                uid = hashlib.md5(f"gnews_{company}_{pub[:20]}".encode()).hexdigest()[:16]
                results.append({
                    "uid":             uid,
                    "debtor_name":     company,
                    "court":           "",
                    "case_number":     "",
                    "bundesland":      _extract_bundesland(full),
                    "insolvency_type": "Insolvenzeröffnung",
                    "source":          "google_news",
                    "raw_title":       title[:200],
                    "scraped_at":      int(time.time()),
                })

            await asyncio.sleep(1.0)
        except ET.ParseError as e:
            log.debug("GNews XML-Parse: %s", e)
        except Exception as e:
            log.debug("GNews %s: %s", query, e)

    return results


def _extract_company_from_news(text: str) -> str:
    """Extrahiert Firmenname (GmbH/AG/SE/UG/KG) aus Nachrichtentext."""
    # Require at least one real word (3+ chars) before the legal suffix
    pattern = (
        r'([A-ZÄÖÜ][A-Za-zÄÖÜäöü\-&\.]{2,}(?:\s+[A-Za-zÄÖÜäöü\-&\.]{1,}){0,5}'
        r'\s*(?:GmbH(?:\s*&\s*Co\.?\s*KG)?|Aktiengesellschaft|UG\s*\(haftungsbeschränkt\)|'
        r'(?<![A-Za-z])(?:AG|SE|UG|KG|OHG|eG)(?![A-Za-z])))'
    )
    m = re.search(pattern, text)
    if m:
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        if 10 <= len(name) <= 90:
            return name
    return ""


def _extract_bundesland(text: str) -> str:
    city_bl = {
        "München": "BY", "Nürnberg": "BY", "Augsburg": "BY", "Bayern": "BY",
        "Köln": "NW", "Düsseldorf": "NW", "Dortmund": "NW", "Essen": "NW", "NRW": "NW",
        "Berlin": "BE", "Hamburg": "HH", "Bremen": "HB",
        "Stuttgart": "BW", "Freiburg": "BW", "Baden-Württemberg": "BW",
        "Frankfurt": "HE", "Kassel": "HE", "Hessen": "HE",
        "Hannover": "NI", "Niedersachsen": "NI",
        "Dresden": "SN", "Leipzig": "SN", "Sachsen": "SN",
        "Erfurt": "TH", "Thüringen": "TH",
        "Mainz": "RP", "Rheinland-Pfalz": "RP",
        "Saarbrücken": "SL", "Saarland": "SL",
        "Kiel": "SH", "Schleswig-Holstein": "SH",
        "Rostock": "MV", "Mecklenburg": "MV",
        "Magdeburg": "ST", "Sachsen-Anhalt": "ST",
        "Potsdam": "BB", "Brandenburg": "BB",
    }
    tl = text.lower()
    for city, code in city_bl.items():
        if city.lower() in tl:
            return code
    return "DE"


def _read_handelsregister_db(limit: int = 15) -> List[Dict]:
    """Liest neue GmbH-Gründungen aus handelsregister_radar.db (letzte 7 Tage)."""
    hr_db = _BASE / "data" / "handelsregister_radar.db"
    if not hr_db.exists():
        log.debug("HR-DB nicht gefunden: %s", hr_db)
        return []

    results: List[Dict] = []
    cutoff = int(time.time()) - 7 * 86400
    try:
        conn = sqlite3.connect(str(hr_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM hr_leads WHERE scraped_at > ? ORDER BY scraped_at DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()
        conn.close()

        for row in rows:
            r = dict(row)
            firma = r.get("firma") or ""
            if not firma:
                continue
            uid = r.get("uid") or hashlib.md5(f"hr_{firma}".encode()).hexdigest()[:16]
            results.append({
                "uid":             uid,
                "debtor_name":     firma,
                "court":           r.get("amtsgericht", ""),
                "case_number":     r.get("registernr", ""),
                "bundesland":      r.get("bundesland", "") or r.get("ort", "DE"),
                "insolvency_type": "Neugründung",
                "source":          "handelsregister",
                "scraped_at":      r.get("scraped_at", int(time.time())),
            })
    except Exception as e:
        log.warning("HR-DB Lesen: %s", e)

    return results


async def _scrape_northdata() -> List[Dict]:
    """Northdata.de — Firmen mit Insolvenz-Keywords (Fallback-Quelle)."""
    results: List[Dict] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
        "Accept-Language": "de-DE,de;q=0.9",
    }

    urls = [
        "https://www.northdata.de/?q=Insolvenz+GmbH&geo=Deutschland",
        "https://www.northdata.de/?q=insolvenzverfahren+GmbH",
    ]

    for url in urls:
        try:
            async with aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
                connector=aiohttp.TCPConnector(ssl=False)
            ) as s:
                async with s.get(url) as r:
                    if r.status != 200:
                        continue
                    html = await r.text(errors="replace")

            # Links im Format /FIRMENNAME,%20Stadt/HRB12345
            links = re.findall(
                r'/([A-ZÄÖÜ][^/\s"<>]{2,60}(?:GmbH|AG|SE|UG|KG)[^/\s"<>]{0,30})/HR[AB]\d+',
                html
            )
            for raw in links[:10]:
                name = unquote(raw).replace("+", " ").replace(",", "").strip()
                name = re.sub(r"\s+", " ", name)
                if len(name) < 4:
                    continue
                uid = hashlib.md5(f"nd_{name}".encode()).hexdigest()[:16]
                results.append({
                    "uid":             uid,
                    "debtor_name":     name,
                    "court":           "",
                    "case_number":     "",
                    "bundesland":      "DE",
                    "insolvency_type": "Insolvenzeröffnung",
                    "source":          "northdata",
                    "scraped_at":      int(time.time()),
                })

            await asyncio.sleep(1.5)
        except Exception as e:
            log.debug("Northdata %s: %s", url, e)

    return results


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
        from modules.ai_client import ai_complete
        text = await ai_complete(prompt, system="", max_tokens=500)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        log.debug("AI: %s", e)

    return fallback()


# ── Email senden ──────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, body: str) -> bool:
    from modules.gmail_accounts import send_email as ga_send
    html = f"""<html><body style="font-family:Arial,sans-serif;color:#333;max-width:600px">
<pre style="font-family:inherit;white-space:pre-wrap">{body}</pre>
<hr style="border:none;border-top:1px solid #eee;margin:20px 0">
<p style="font-size:11px;color:#aaa">Abmeldung: Antworten Sie mit "Abmeldung"</p>
</body></html>"""
    ok, via = ga_send(to, subject, body, html=html)
    if ok:
        log.info("Email: %s → %s via %s", subject[:50], to, via)
    else:
        log.warning("Email-Fehler (%s)", to)
    return ok


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
    init_db()  # Tabellen erstellen falls noch nicht vorhanden
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
