#!/usr/bin/env python3
"""
AIITEC B2B Outreach Machine — Vollautomatisches KI-Leasing Verkaufssystem
=========================================================================
Verkauft automatisch AIITEC KI-Mitarbeiter-Leasing an große DACH-Unternehmen.
Tool: https://dist-pi-jet-78.vercel.app/

Was es tut (täglich 09:30 Uhr):
  1. Wählt nächste 30 Unternehmen aus Queue (Supabase)
  2. Bestimmt besten AIITEC-Service per Branche/Track
  3. Generiert personalisierte Emails (Stage 1/2/3)
  4. Sendet per Gmail (aiitecbuuss@gmail.com)
  5. Follow-Up nach 5 Tagen, 10 Tagen automatisch
  6. Telegram-Report nach jedem Lauf
  7. Trackt alles in Supabase (no duplicates)

3 Verkaufs-Tracks:
  A — Corporate-IT / Innovation / E-Commerce  → Lead-Agent, Content-Agent, Trend Velocity, AI-Citation SEO
  B — Compliance / Legal / EU AI Act          → Compliance-Wächter, Förder-Scout, Intelligence Broker
  C — Finance / Factoring / Insolvenz         → Intelligence Broker, Lead-Agent

CLI:
  python3 modules/aiitec_outreach_machine.py              # daemon (09:30 tägl.)
  python3 modules/aiitec_outreach_machine.py --run-now    # sofort 1 Runde
  python3 modules/aiitec_outreach_machine.py --stats      # Statistik
  python3 modules/aiitec_outreach_machine.py --init-db    # Supabase-Tabellen anlegen
  python3 modules/aiitec_outreach_machine.py --seed       # Unternehmen laden
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import smtplib
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional, Any

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AIITEC] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("AiitecOutreach")

_BASE     = Path(__file__).parent.parent
_TOOL_URL = "https://dist-pi-jet-78.vercel.app/"
_FROM_NAME = "Rudolf Sarkany | AiiteC"

def _load_env():
    ef = _BASE / ".env"
    if ef.exists():
        for line in ef.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

_GMAIL_USER = lambda: os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")
_GMAIL_PASS = lambda: os.getenv("GMAIL_APP_PASSWORD_AIITEC", "")
_TG_TOKEN   = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT    = lambda: os.getenv("TELEGRAM_CHAT_ID", "")
_SB_URL     = lambda: os.getenv("SUPABASE_URL", "")
_SB_KEY     = lambda: os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY", ""))

# ── SMTP-Pool (Round-Robin über alle Gmail-Accounts) ──────────────────────────

_smtp_pool_cache:   List[tuple] = []
_smtp_pool_idx:     int = 0
_smtp_blocked_today: set = set()
_smtp_blocked_date:  str = ""

def _get_smtp_pool() -> List[tuple]:
    """Baut den SMTP-Pool einmalig aus Env-Vars auf."""
    global _smtp_pool_cache
    if _smtp_pool_cache:
        return _smtp_pool_cache
    for suffix in ["_1", "_3", "_4", "_5", "_7", "_8"]:
        u = os.getenv(f"GMAIL_USER{suffix}", "")
        p = os.getenv(f"GMAIL_APP_PASSWORD{suffix}", "")
        if u and p:
            _smtp_pool_cache.append((u, p))
    if not _smtp_pool_cache:
        # Fallback auf AIITEC-Account
        u = _GMAIL_USER()
        p = _GMAIL_PASS()
        if u and p:
            _smtp_pool_cache.append((u, p))
    log.info("SMTP-Pool: %d Accounts geladen", len(_smtp_pool_cache))
    return _smtp_pool_cache

def _reset_smtp_if_new_day() -> None:
    global _smtp_blocked_today, _smtp_blocked_date
    today = datetime.now().strftime("%Y-%m-%d")
    if _smtp_blocked_date != today:
        if _smtp_blocked_today:
            log.info("[SMTP] Neuer Tag — %d blockierte Accounts freigegeben", len(_smtp_blocked_today))
        _smtp_blocked_today = set()
        _smtp_blocked_date = today

def _send_via_sendgrid(to: str, subject: str, body: str) -> bool:
    """SendGrid REST-API als Fallback wenn alle Gmail-Limits erreicht."""
    api_key = os.getenv("SENDGRID_API_KEY_AIITEC", "")
    if not api_key:
        return False
    try:
        payload = json.dumps({
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": "aiitecbuuss@gmail.com", "name": _FROM_NAME},
            "reply_to": {"email": "aiitecbuuss@gmail.com"},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }).encode()
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 202):
                log.info("  ✉  [SendGrid] Gesendet → %s", to)
                return True
    except Exception as e:
        log.error("  ✗  SendGrid → %s: %s", to, e)
    return False

EMAILS_PER_DAY    = 30
FOLLOWUP_DAYS_1   = 5
FOLLOWUP_DAYS_2   = 10
DAILY_HOUR        = 9
DAILY_MINUTE      = 30

# ── Produkte ──────────────────────────────────────────────────────────────────

PRODUCTS = {
    "lead_agent": {
        "name": "Lead-Agent",
        "price": "€500/Monat",
        "promise": "10 vorqualifizierte B2B-Leads täglich — vollautomatisch",
        "url": _TOOL_URL,
    },
    "compliance_waechter": {
        "name": "Compliance-Wächter",
        "price": "€1.500/Monat",
        "promise": "EU AI Act Risiko-Inventar + laufendes Monitoring",
        "url": _TOOL_URL,
    },
    "content_agent": {
        "name": "Content-Agent",
        "price": "€400–700/Monat",
        "promise": "8 SEO-Artikel + Social Posts monatlich, vollautomatisch",
        "url": _TOOL_URL,
    },
    "foerder_scout": {
        "name": "Förder-Scout",
        "price": "ab €99",
        "promise": "Automatischer Scan aller KfW-, BAFA- und EU-Förderprogramme",
        "url": _TOOL_URL,
    },
    "intelligence_broker": {
        "name": "Intelligence Broker",
        "price": "€500–2.000/Monat",
        "promise": "Handelsregister + Insolvenz-Daten + KI-Risiko-Scoring in Echtzeit",
        "url": _TOOL_URL,
    },
    "trend_velocity": {
        "name": "Trend Velocity",
        "price": "€999 + €499/Monat",
        "promise": "Virale Trends erkennen → Auto-Listing + Meta-Ads",
        "url": _TOOL_URL,
    },
    "ai_citation_seo": {
        "name": "AI-Citation SEO",
        "price": "€499 + €799/Monat",
        "promise": "Inhalte für ChatGPT/Perplexity-Zitierungen optimieren",
        "url": _TOOL_URL,
    },
}

# ── Track→Produkt Mapping ─────────────────────────────────────────────────────

TRACK_PRODUCTS = {
    "A": ["lead_agent", "content_agent", "trend_velocity", "ai_citation_seo"],
    "B": ["compliance_waechter", "foerder_scout", "intelligence_broker"],
    "C": ["intelligence_broker", "lead_agent"],
}

BRANCHE_TRACK = {
    "IT/Software":         "B",
    "Beratung":            "B",
    "Kanzlei":             "B",
    "Versicherung":        "B",
    "Bank":                "C",
    "Factoring":           "C",
    "Insolvenz":           "C",
    "M&A":                 "C",
    "Wirtschaftsprüfung":  "C",
    "E-Commerce":          "A",
    "Marketing/Agentur":   "A",
    "Maschinenbau":        "A",
    "Automotive":          "B",
    "Chemie":              "A",
    "Pharma":              "B",
    "Logistik":            "A",
    "Handel":              "A",
    "Immobilien":          "C",
    "Energie":             "B",
    "Medien":              "A",
}

# ── Unternehmen Seed-Datenbank ────────────────────────────────────────────────
# Format: name, domain, email, branche, umsatzklasse, land

COMPANIES_SEED = [
    # ── TRACK B: Compliance / Legal / EU AI Act ───────────────────────────────
    {"name": "Freshfields Bruckhaus Deringer",  "domain": "freshfields.com",     "email": "info@freshfields.com",       "branche": "Kanzlei",     "umsatz": "L", "land": "DE"},
    {"name": "Linklaters LLP",                  "domain": "linklaters.com",      "email": "info@linklaters.com",        "branche": "Kanzlei",     "umsatz": "L", "land": "DE"},
    {"name": "Hogan Lovells",                    "domain": "hoganlovells.com",    "email": "info@hoganlovells.com",      "branche": "Kanzlei",     "umsatz": "L", "land": "DE"},
    {"name": "CMS Hasche Sigle",                "domain": "cms.law",             "email": "info@cms.law",               "branche": "Kanzlei",     "umsatz": "L", "land": "DE"},
    {"name": "Luther Rechtsanwaltsgesellschaft","domain": "luther-lawfirm.com",  "email": "info@luther-lawfirm.com",    "branche": "Kanzlei",     "umsatz": "M", "land": "DE"},
    {"name": "Noerr Partnerschaftsgesellschaft","domain": "noerr.com",           "email": "info@noerr.com",             "branche": "Kanzlei",     "umsatz": "M", "land": "DE"},
    {"name": "Osborne Clarke",                  "domain": "osborneclarke.com",   "email": "info@osborneclarke.com",     "branche": "Kanzlei",     "umsatz": "M", "land": "DE"},
    {"name": "Bird & Bird",                     "domain": "twobirds.com",        "email": "info@twobirds.com",          "branche": "Kanzlei",     "umsatz": "M", "land": "DE"},
    {"name": "Gleiss Lutz",                     "domain": "gleisslutz.com",      "email": "info@gleisslutz.com",        "branche": "Kanzlei",     "umsatz": "M", "land": "DE"},
    {"name": "Hengeler Mueller",                "domain": "hengeler.com",        "email": "info@hengeler.com",          "branche": "Kanzlei",     "umsatz": "M", "land": "DE"},
    {"name": "Roland Berger GmbH",              "domain": "rolandberger.com",    "email": "info@rolandberger.com",      "branche": "Beratung",    "umsatz": "L", "land": "DE"},
    {"name": "McKinsey & Company",              "domain": "mckinsey.de",         "email": "presse@mckinsey.com",        "branche": "Beratung",    "umsatz": "L", "land": "DE"},
    {"name": "BCG Boston Consulting Group",     "domain": "bcg.com",             "email": "info@bcg.com",               "branche": "Beratung",    "umsatz": "L", "land": "DE"},
    {"name": "Deloitte Deutschland",            "domain": "deloitte.com",        "email": "info@deloitte.de",           "branche": "Wirtschaftsprüfung", "umsatz": "L", "land": "DE"},
    {"name": "KPMG Deutschland",                "domain": "kpmg.de",             "email": "info@kpmg.de",               "branche": "Wirtschaftsprüfung", "umsatz": "L", "land": "DE"},
    {"name": "PwC Deutschland",                 "domain": "pwc.de",              "email": "info@pwc.de",                "branche": "Wirtschaftsprüfung", "umsatz": "L", "land": "DE"},
    {"name": "EY Deutschland",                  "domain": "ey.com",              "email": "info@de.ey.com",             "branche": "Wirtschaftsprüfung", "umsatz": "L", "land": "DE"},
    {"name": "BDO AG",                          "domain": "bdo.de",              "email": "info@bdo.de",                "branche": "Wirtschaftsprüfung", "umsatz": "M", "land": "DE"},
    {"name": "Mazars GmbH",                     "domain": "mazars.de",           "email": "info@mazars.de",             "branche": "Wirtschaftsprüfung", "umsatz": "M", "land": "DE"},
    {"name": "TÜV SÜD AG",                     "domain": "tuvsud.com",          "email": "info@tuvsud.com",            "branche": "Beratung",    "umsatz": "L", "land": "DE"},
    {"name": "TÜV Rheinland AG",                "domain": "tuv.com",             "email": "info@de.tuv.com",            "branche": "Beratung",    "umsatz": "L", "land": "DE"},
    {"name": "TÜV NORD AG",                     "domain": "tuvnord.de",          "email": "info@tuevnord.de",           "branche": "Beratung",    "umsatz": "M", "land": "DE"},
    {"name": "Allianz SE",                      "domain": "allianz.de",          "email": "info@allianz.de",            "branche": "Versicherung","umsatz": "L", "land": "DE"},
    {"name": "Munich Re",                       "domain": "munichre.com",        "email": "info@munichre.com",          "branche": "Versicherung","umsatz": "L", "land": "DE"},
    {"name": "Hannover Rück SE",                "domain": "hannover-re.com",     "email": "info@hannover-re.com",       "branche": "Versicherung","umsatz": "L", "land": "DE"},
    {"name": "Zurich Insurance Deutschland",    "domain": "zurich.de",           "email": "info@zurich.de",             "branche": "Versicherung","umsatz": "L", "land": "DE"},
    {"name": "Generali Deutschland AG",         "domain": "generali.de",         "email": "info@generali.de",           "branche": "Versicherung","umsatz": "L", "land": "DE"},
    {"name": "HDI Global SE",                   "domain": "hdi.de",              "email": "info@hdi.de",                "branche": "Versicherung","umsatz": "M", "land": "DE"},
    {"name": "R+V Versicherung AG",             "domain": "ruv.de",              "email": "info@ruv.de",                "branche": "Versicherung","umsatz": "M", "land": "DE"},
    {"name": "Signal Iduna Gruppe",             "domain": "signal-iduna.de",     "email": "info@signal-iduna.de",       "branche": "Versicherung","umsatz": "M", "land": "DE"},
    {"name": "SAP SE",                          "domain": "sap.com",             "email": "info@sap.com",               "branche": "IT/Software",  "umsatz": "L", "land": "DE"},
    {"name": "Software AG",                     "domain": "softwareag.com",      "email": "info@softwareag.com",        "branche": "IT/Software",  "umsatz": "L", "land": "DE"},
    {"name": "Atoss Software AG",               "domain": "atoss.com",           "email": "info@atoss.com",             "branche": "IT/Software",  "umsatz": "M", "land": "DE"},
    {"name": "Nemetschek SE",                   "domain": "nemetschek.com",      "email": "info@nemetschek.com",        "branche": "IT/Software",  "umsatz": "M", "land": "DE"},
    {"name": "Teamviewer AG",                   "domain": "teamviewer.com",      "email": "info@teamviewer.com",        "branche": "IT/Software",  "umsatz": "M", "land": "DE"},
    {"name": "Bechtle AG",                      "domain": "bechtle.com",         "email": "info@bechtle.com",           "branche": "IT/Software",  "umsatz": "L", "land": "DE"},
    {"name": "Datagroup SE",                    "domain": "datagroup.de",        "email": "info@datagroup.de",          "branche": "IT/Software",  "umsatz": "M", "land": "DE"},
    {"name": "Cancom SE",                       "domain": "cancom.de",           "email": "info@cancom.de",             "branche": "IT/Software",  "umsatz": "M", "land": "DE"},
    {"name": "Freudenberg Group",               "domain": "freudenberg.com",     "email": "info@freudenberg.com",       "branche": "Automotive",   "umsatz": "L", "land": "DE"},
    {"name": "Bosch GmbH",                      "domain": "bosch.de",            "email": "presse@bosch.de",            "branche": "Automotive",   "umsatz": "L", "land": "DE"},
    {"name": "Continental AG",                  "domain": "continental.com",     "email": "presse@conti.de",            "branche": "Automotive",   "umsatz": "L", "land": "DE"},
    {"name": "ZF Friedrichshafen AG",           "domain": "zf.com",              "email": "info@zf.com",                "branche": "Automotive",   "umsatz": "L", "land": "DE"},
    {"name": "Hella GmbH",                      "domain": "hella.com",           "email": "info@hella.com",             "branche": "Automotive",   "umsatz": "L", "land": "DE"},
    {"name": "Mahle GmbH",                      "domain": "mahle.com",           "email": "info@mahle.com",             "branche": "Automotive",   "umsatz": "M", "land": "DE"},
    {"name": "Brose SE",                        "domain": "brose.com",           "email": "info@brose.com",             "branche": "Automotive",   "umsatz": "M", "land": "DE"},
    {"name": "Webasto Group",                   "domain": "webasto.com",         "email": "info@webasto.com",           "branche": "Automotive",   "umsatz": "M", "land": "DE"},
    {"name": "Schaeffler AG",                   "domain": "schaeffler.com",      "email": "info@schaeffler.com",        "branche": "Automotive",   "umsatz": "L", "land": "DE"},
    {"name": "Knorr-Bremse AG",                 "domain": "knorr-bremse.com",    "email": "info@knorr-bremse.com",      "branche": "Automotive",   "umsatz": "L", "land": "DE"},
    {"name": "Evonik Industries AG",            "domain": "evonik.com",          "email": "info@evonik.com",            "branche": "Pharma",       "umsatz": "L", "land": "DE"},
    {"name": "Merck KGaA",                      "domain": "merckgroup.com",      "email": "info@merck.de",              "branche": "Pharma",       "umsatz": "L", "land": "DE"},
    {"name": "Fresenius SE",                    "domain": "fresenius.com",       "email": "info@fresenius.com",         "branche": "Pharma",       "umsatz": "L", "land": "DE"},
    {"name": "Stada Arzneimittel AG",           "domain": "stada.de",            "email": "info@stada.de",              "branche": "Pharma",       "umsatz": "M", "land": "DE"},
    {"name": "Siemens Healthineers AG",         "domain": "siemens-healthineers.com","email":"info@siemens-healthineers.com","branche":"Pharma",   "umsatz": "L", "land": "DE"},
    {"name": "Draeger Safety AG",               "domain": "draeger.com",         "email": "info@draeger.com",           "branche": "Pharma",       "umsatz": "M", "land": "DE"},
    {"name": "Innio Group GmbH",                "domain": "innio.com",           "email": "info@innio.com",             "branche": "Energie",      "umsatz": "M", "land": "DE"},
    {"name": "E.ON SE",                         "domain": "eon.com",             "email": "info@eon.com",               "branche": "Energie",      "umsatz": "L", "land": "DE"},
    {"name": "RWE AG",                          "domain": "rwe.com",             "email": "info@rwe.com",               "branche": "Energie",      "umsatz": "L", "land": "DE"},
    {"name": "EnBW Energie Baden-Württemberg",  "domain": "enbw.com",            "email": "info@enbw.com",              "branche": "Energie",      "umsatz": "L", "land": "DE"},
    {"name": "MVV Energie AG",                  "domain": "mvv.de",              "email": "info@mvv.de",                "branche": "Energie",      "umsatz": "M", "land": "DE"},
    # ── TRACK C: Finance / Factoring / Insolvenz ─────────────────────────────
    {"name": "Deutsche Bank AG",               "domain": "db.com",              "email": "info@db.com",                "branche": "Bank",         "umsatz": "L", "land": "DE"},
    {"name": "Commerzbank AG",                 "domain": "commerzbank.de",      "email": "info@commerzbank.de",        "branche": "Bank",         "umsatz": "L", "land": "DE"},
    {"name": "DZ Bank AG",                     "domain": "dzbank.de",           "email": "info@dzbank.de",             "branche": "Bank",         "umsatz": "L", "land": "DE"},
    {"name": "Landesbank Baden-Württemberg",   "domain": "lbbw.de",             "email": "info@lbbw.de",               "branche": "Bank",         "umsatz": "L", "land": "DE"},
    {"name": "Helaba Landesbank Hessen",       "domain": "helaba.de",           "email": "info@helaba.de",             "branche": "Bank",         "umsatz": "L", "land": "DE"},
    {"name": "Bayern LB",                      "domain": "bayernlb.de",         "email": "info@bayernlb.de",           "branche": "Bank",         "umsatz": "L", "land": "DE"},
    {"name": "NordLB",                         "domain": "nordlb.de",           "email": "info@nordlb.de",             "branche": "Bank",         "umsatz": "M", "land": "DE"},
    {"name": "DekaBank Deutsche Girozentrale", "domain": "deka.de",             "email": "info@deka.de",               "branche": "Bank",         "umsatz": "L", "land": "DE"},
    {"name": "SV SparkassenVersicherung",      "domain": "sparkassenversicherung.de","email":"info@sparkassenversicherung.de","branche":"Versicherung","umsatz":"M","land":"DE"},
    {"name": "Coface Deutschland AG",          "domain": "coface.de",           "email": "info@coface.de",             "branche": "Factoring",    "umsatz": "M", "land": "DE"},
    {"name": "Euler Hermes Deutschland AG",    "domain": "allianz-trade.com",   "email": "info@allianz-trade.com",     "branche": "Factoring",    "umsatz": "L", "land": "DE"},
    {"name": "Creditreform AG",                "domain": "creditreform.de",     "email": "info@creditreform.de",       "branche": "Factoring",    "umsatz": "M", "land": "DE"},
    {"name": "Atradius Credit Insurance",      "domain": "atradius.de",         "email": "info@atradius.de",           "branche": "Factoring",    "umsatz": "L", "land": "DE"},
    {"name": "BNP Paribas Factor GmbH",        "domain": "bnpparibas.de",       "email": "info@bnpparibas.de",         "branche": "Factoring",    "umsatz": "L", "land": "DE"},
    {"name": "GE Capital Factoring GmbH",      "domain": "bibby-factor.de",     "email": "info@bibby-factor.de",       "branche": "Factoring",    "umsatz": "M", "land": "DE"},
    {"name": "Bibby Financial Services",       "domain": "bibbyfinancialservices.de","email":"info@bibby-factor.de",   "branche": "Factoring",    "umsatz": "M", "land": "DE"},
    {"name": "Deutsche Factoring Bank",        "domain": "deutschefactoring.de","email": "info@deutschefactoring.de", "branche": "Factoring",    "umsatz": "M", "land": "DE"},
    {"name": "Grenke AG",                      "domain": "grenke.de",           "email": "info@grenke.de",             "branche": "Factoring",    "umsatz": "M", "land": "DE"},
    {"name": "Houlihan Lokey GmbH",            "domain": "hl.com",              "email": "info@hl.com",                "branche": "M&A",          "umsatz": "L", "land": "DE"},
    {"name": "KPMG Deal Advisory",             "domain": "kpmg.de",             "email": "dealadvisory@kpmg.de",       "branche": "M&A",          "umsatz": "L", "land": "DE"},
    {"name": "Rödl & Partner GmbH",            "domain": "roedl.de",            "email": "info@roedl.de",              "branche": "M&A",          "umsatz": "M", "land": "DE"},
    {"name": "Görg Partnerschaft mbB",         "domain": "goerg.de",            "email": "info@goerg.de",              "branche": "Insolvenz",    "umsatz": "M", "land": "DE"},
    {"name": "Schultze & Braun GmbH",          "domain": "schultze-braun.de",   "email": "info@schultze-braun.de",     "branche": "Insolvenz",    "umsatz": "M", "land": "DE"},
    {"name": "Pluta Rechtsanwalts GmbH",       "domain": "pluta.de",            "email": "info@pluta.de",              "branche": "Insolvenz",    "umsatz": "M", "land": "DE"},
    {"name": "Flick Gocke Schaumburg",         "domain": "fgs.de",              "email": "info@fgs.de",                "branche": "Insolvenz",    "umsatz": "M", "land": "DE"},
    {"name": "White & Case LLP",               "domain": "whitecase.com",       "email": "info@whitecase.com",         "branche": "M&A",          "umsatz": "L", "land": "DE"},
    {"name": "Freshfields Insolvenzteam",      "domain": "freshfields.com",     "email": "restructuring@freshfields.com","branche":"Insolvenz",  "umsatz": "L", "land": "DE"},
    {"name": "Immobilien Zeitung Verlag GmbH", "domain": "iz.de",               "email": "info@iz.de",                 "branche": "Immobilien",   "umsatz": "S", "land": "DE"},
    {"name": "Patrizia AG",                    "domain": "patrizia.ag",         "email": "info@patrizia.ag",           "branche": "Immobilien",   "umsatz": "L", "land": "DE"},
    {"name": "Vonovia SE",                     "domain": "vonovia.de",          "email": "info@vonovia.de",            "branche": "Immobilien",   "umsatz": "L", "land": "DE"},
    {"name": "Deutsche Wohnen SE",             "domain": "deutsche-wohnen.com", "email": "info@deutsche-wohnen.com",   "branche": "Immobilien",   "umsatz": "L", "land": "DE"},
    {"name": "LEG Immobilien SE",              "domain": "leg.de",              "email": "info@leg.de",                "branche": "Immobilien",   "umsatz": "M", "land": "DE"},
    # ── TRACK A: Corporate-IT / E-Commerce / Marketing ───────────────────────
    {"name": "ABOUT YOU GmbH",                 "domain": "aboutyou.de",         "email": "info@aboutyou.de",           "branche": "E-Commerce",   "umsatz": "L", "land": "DE"},
    {"name": "Zalando SE",                     "domain": "zalando.de",          "email": "press@zalando.de",           "branche": "E-Commerce",   "umsatz": "L", "land": "DE"},
    {"name": "Mytheresa Group GmbH",           "domain": "mytheresa.com",       "email": "info@mytheresa.com",         "branche": "E-Commerce",   "umsatz": "L", "land": "DE"},
    {"name": "windeln.de SE",                  "domain": "windeln.de",          "email": "info@windeln.de",            "branche": "E-Commerce",   "umsatz": "S", "land": "DE"},
    {"name": "Westwing Group AG",              "domain": "westwing.de",         "email": "info@westwing.de",           "branche": "E-Commerce",   "umsatz": "M", "land": "DE"},
    {"name": "Flaconi GmbH",                   "domain": "flaconi.de",          "email": "info@flaconi.de",            "branche": "E-Commerce",   "umsatz": "M", "land": "DE"},
    {"name": "MediaMarktSaturn",               "domain": "mediamarkt.de",       "email": "info@mediamarkt.de",         "branche": "E-Commerce",   "umsatz": "L", "land": "DE"},
    {"name": "Conrad Electronic SE",           "domain": "conrad.de",           "email": "info@conrad.de",             "branche": "E-Commerce",   "umsatz": "M", "land": "DE"},
    {"name": "Cyberport GmbH",                 "domain": "cyberport.de",        "email": "info@cyberport.de",          "branche": "E-Commerce",   "umsatz": "M", "land": "DE"},
    {"name": "Alternate GmbH",                 "domain": "alternate.de",        "email": "info@alternate.de",          "branche": "E-Commerce",   "umsatz": "M", "land": "DE"},
    {"name": "Notebooksbilliger.de AG",        "domain": "notebooksbilliger.de","email": "info@notebooksbilliger.de",  "branche": "E-Commerce",   "umsatz": "M", "land": "DE"},
    {"name": "Home24 SE",                      "domain": "home24.de",           "email": "info@home24.de",             "branche": "E-Commerce",   "umsatz": "M", "land": "DE"},
    {"name": "Baur Versand GmbH",              "domain": "baur.de",             "email": "info@baur.de",               "branche": "E-Commerce",   "umsatz": "M", "land": "DE"},
    {"name": "REWE Group Digital",            "domain": "rewe.de",             "email": "digital@rewe.de",            "branche": "E-Commerce",   "umsatz": "L", "land": "DE"},
    {"name": "Edeka Digital GmbH",             "domain": "edeka.de",            "email": "digital@edeka.de",           "branche": "E-Commerce",   "umsatz": "L", "land": "DE"},
    {"name": "dm-drogerie markt GmbH",         "domain": "dm.de",               "email": "info@dm.de",                 "branche": "E-Commerce",   "umsatz": "L", "land": "DE"},
    {"name": "Rossmann GmbH",                  "domain": "rossmann.de",         "email": "info@rossmann.de",           "branche": "E-Commerce",   "umsatz": "L", "land": "DE"},
    {"name": "SinnerSchrader AG",              "domain": "sinnerschrader.com",  "email": "info@sinnerschrader.com",    "branche": "Marketing/Agentur","umsatz":"M","land":"DE"},
    {"name": "Serviceplan Group",              "domain": "serviceplan.com",     "email": "info@serviceplan.com",       "branche": "Marketing/Agentur","umsatz":"M","land":"DE"},
    {"name": "Jung von Matt AG",               "domain": "jvm.com",             "email": "info@jvm.com",               "branche": "Marketing/Agentur","umsatz":"M","land":"DE"},
    {"name": "Scholz & Friends Group",         "domain": "s-f.com",             "email": "info@s-f.com",               "branche": "Marketing/Agentur","umsatz":"M","land":"DE"},
    {"name": "pilot Hamburg GmbH",             "domain": "pilot.de",            "email": "info@pilot.de",              "branche": "Marketing/Agentur","umsatz":"M","land":"DE"},
    {"name": "Ströer SE & Co. KGaA",           "domain": "stroeer.de",          "email": "info@stroeer.de",            "branche": "Medien",       "umsatz": "L", "land": "DE"},
    {"name": "ProSiebenSat.1 Media SE",        "domain": "prosiebensat1.com",   "email": "info@prosiebensat1.com",     "branche": "Medien",       "umsatz": "L", "land": "DE"},
    {"name": "Axel Springer SE",               "domain": "axelspringer.com",    "email": "info@axelspringer.com",      "branche": "Medien",       "umsatz": "L", "land": "DE"},
    {"name": "Burda GmbH",                     "domain": "burda.com",           "email": "info@burda.com",             "branche": "Medien",       "umsatz": "L", "land": "DE"},
    {"name": "Gruner + Jahr GmbH",             "domain": "guj.de",              "email": "info@guj.de",                "branche": "Medien",       "umsatz": "M", "land": "DE"},
    {"name": "Frankfurter Allgemeine Zeitung", "domain": "faz.net",             "email": "redaktion@faz.de",           "branche": "Medien",       "umsatz": "M", "land": "DE"},
    {"name": "Haufe Group",                    "domain": "haufe.de",            "email": "info@haufe.de",              "branche": "Medien",       "umsatz": "M", "land": "DE"},
    {"name": "Krones AG",                      "domain": "krones.com",          "email": "info@krones.com",            "branche": "Maschinenbau", "umsatz": "L", "land": "DE"},
    {"name": "Trumpf GmbH + Co. KG",          "domain": "trumpf.com",          "email": "kontakt@trumpf.com",         "branche": "Maschinenbau", "umsatz": "L", "land": "DE"},
    {"name": "Festo AG & Co. KG",             "domain": "festo.com",           "email": "info@festo.com",             "branche": "Maschinenbau", "umsatz": "L", "land": "DE"},
    {"name": "Wacker Neuson SE",              "domain": "wackerneuson.com",    "email": "info@wackerneuson.com",      "branche": "Maschinenbau", "umsatz": "M", "land": "DE"},
    {"name": "Linde AG",                      "domain": "linde.com",           "email": "info@linde.com",             "branche": "Chemie",       "umsatz": "L", "land": "DE"},
    {"name": "Covestro AG",                   "domain": "covestro.com",        "email": "info@covestro.com",          "branche": "Chemie",       "umsatz": "L", "land": "DE"},
    {"name": "Brenntag SE",                   "domain": "brenntag.com",        "email": "info@brenntag.com",          "branche": "Chemie",       "umsatz": "L", "land": "DE"},
    {"name": "Dachser GmbH & Co. KG",         "domain": "dachser.com",         "email": "info@dachser.com",           "branche": "Logistik",     "umsatz": "L", "land": "DE"},
    {"name": "DB Schenker GmbH",              "domain": "dbschenker.com",      "email": "info@dbschenker.com",        "branche": "Logistik",     "umsatz": "L", "land": "DE"},
    {"name": "Kühne+Nagel International AG",  "domain": "kuehne-nagel.com",    "email": "info@kuehne-nagel.com",      "branche": "Logistik",     "umsatz": "L", "land": "DE"},
    {"name": "Rhenus SE & Co. KG",            "domain": "rhenus.com",          "email": "info@rhenus.com",            "branche": "Logistik",     "umsatz": "L", "land": "DE"},
    {"name": "GLS Group GmbH",                "domain": "gls-group.eu",        "email": "info@gls-group.eu",          "branche": "Logistik",     "umsatz": "M", "land": "DE"},
    {"name": "Meyer & Meyer Transport SE",     "domain": "meyer-meyer.de",      "email": "info@meyer-meyer.de",        "branche": "Logistik",     "umsatz": "M", "land": "DE"},
    # Österreich & Schweiz
    {"name": "Erste Group Bank AG",           "domain": "erstegroup.com",      "email": "info@erstegroup.com",        "branche": "Bank",         "umsatz": "L", "land": "AT"},
    {"name": "Raiffeisen Bank International", "domain": "rbinternational.com",  "email": "info@rbinternational.com",   "branche": "Bank",         "umsatz": "L", "land": "AT"},
    {"name": "OMV AG",                         "domain": "omv.com",             "email": "info@omv.com",               "branche": "Energie",      "umsatz": "L", "land": "AT"},
    {"name": "voestalpine AG",                 "domain": "voestalpine.com",     "email": "info@voestalpine.com",       "branche": "Maschinenbau", "umsatz": "L", "land": "AT"},
    {"name": "Andritz AG",                     "domain": "andritz.com",         "email": "info@andritz.com",           "branche": "Maschinenbau", "umsatz": "L", "land": "AT"},
    {"name": "UBS Group AG",                   "domain": "ubs.com",             "email": "info@ubs.com",               "branche": "Bank",         "umsatz": "L", "land": "CH"},
    {"name": "Credit Suisse Group AG",         "domain": "credit-suisse.com",   "email": "info@credit-suisse.com",     "branche": "Bank",         "umsatz": "L", "land": "CH"},
    {"name": "Zurich Insurance Group",         "domain": "zurich.com",          "email": "info@zurich.com",            "branche": "Versicherung", "umsatz": "L", "land": "CH"},
    {"name": "Swiss Re Group",                 "domain": "swissre.com",         "email": "info@swissre.com",           "branche": "Versicherung", "umsatz": "L", "land": "CH"},
    {"name": "Novartis AG",                    "domain": "novartis.com",        "email": "info@novartis.com",          "branche": "Pharma",       "umsatz": "L", "land": "CH"},
    {"name": "Roche Holding AG",               "domain": "roche.com",           "email": "info@roche.com",             "branche": "Pharma",       "umsatz": "L", "land": "CH"},
    {"name": "ABB Ltd",                        "domain": "abb.com",             "email": "info@abb.com",               "branche": "Maschinenbau", "umsatz": "L", "land": "CH"},
]

# ── Email Templates (3 Tracks × 3 Stages) ────────────────────────────────────

def _get_track(branche: str) -> str:
    return BRANCHE_TRACK.get(branche, "A")

def _get_product(track: str, branche: str) -> Dict:
    key = TRACK_PRODUCTS[track][0]
    if branche in ("IT/Software", "Beratung", "Versicherung") and track == "B":
        key = "compliance_waechter"
    elif branche in ("Kanzlei",) and track == "B":
        key = "intelligence_broker"
    elif branche in ("E-Commerce", "Medien") and track == "A":
        key = "content_agent"
    elif branche in ("Maschinenbau", "Logistik", "Handel") and track == "A":
        key = "lead_agent"
    elif branche in ("Factoring", "Bank", "M&A") and track == "C":
        key = "intelligence_broker"
    return PRODUCTS.get(key, PRODUCTS["lead_agent"])

TEMPLATES = {
    "A": {
        1: {
            "subject": "10 B2B-Leads täglich ohne Vertrieb — für {name}",
            "body": """Sehr geehrte Damen und Herren,

aktive Neukundengewinnung im B2B-Bereich kostet Zeit und Budget — besonders in einem Markt wie {branche}.

Unser Lead-Agent liefert täglich 10 vorqualifizierte DACH-Entscheider-Kontakte, automatisch recherchiert und validiert. Kein manueller Aufwand. Kein CRM-Chaos.

Preis: {product_price}. Monatlich kündbar. 14 Tage Geld-zurück-Garantie.

Direkt testen: {url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC
aiitecbuuss@gmail.com"""
        },
        2: {
            "subject": "Re: KI-Lead-Agent — kurze Rückfrage für {name}",
            "body": """Sehr geehrte Damen und Herren,

ich hatte Ihnen vor einigen Tagen geschrieben. Ich wollte kurz nachfragen, ob unser {product_name} für {name} relevant wäre.

Kurz zusammengefasst: {product_promise}.

Viele unserer {branche}-Kunden berichten von 3–5 qualifizierten Terminen pro Woche — vollautomatisch, ohne zusätzliche Vertriebskosten.

Interesse? Hier geht's direkt zum Start: {url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC
aiitecbuuss@gmail.com"""
        },
        3: {
            "subject": "Letzter Hinweis: KI-Vertrieb für {name} (14 Tage kostenlos)",
            "body": """Sehr geehrte Damen und Herren,

dies ist meine letzte Nachricht zu diesem Thema — ich möchte Ihre Inbox nicht unnötig belasten.

Falls {name} in den nächsten Wochen den Vertrieb skalieren möchte, ohne neue Mitarbeiter einzustellen: unser {product_name} läuft 24/7, kostet {product_price} und ist monatlich kündbar.

Erster Monat: 14 Tage kostenlos testen.

{url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC"""
        },
    },
    "B": {
        1: {
            "subject": "EU AI Act: Ihr Compliance-Risiko als {branche}-Unternehmen",
            "body": """Sehr geehrte Damen und Herren,

ab August 2026 erzwingt der EU AI Act vollständige Transparenz über eingesetzte KI-Systeme — mit Bußgeldern bis €35 Millionen oder 7% des weltweiten Umsatzes.

Für {branche}-Unternehmen wie {name} bedeutet das: KI-Systeme in HR, Risikobewertung, Kundenkommunikation und Entscheidungsunterstützung fallen in die Hochrisiko-Kategorie.

Unser {product_name} erstellt in 48h ein vollständiges KI-System-Inventar, bewertet Ihr Risikoprofil und liefert einen prüfbaren Compliance-Report.

Preis: {product_price}. Erste Analyse unverbindlich.

Details und Demo: {url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC Compliance GmbH
aiitecbuuss@gmail.com"""
        },
        2: {
            "subject": "Re: EU AI Act — 6 Wochen bis zur nächsten Prüfwelle",
            "body": """Sehr geehrte Damen und Herren,

der EU AI Act-Durchsetzungsplan sieht ab Q4 2026 erste behördliche Prüfungen vor — besonders im Finanz- und {branche}-Sektor.

Unternehmen ohne dokumentiertes KI-Register riskieren nicht nur Bußgelder, sondern auch Reputationsschäden bei institutionellen Investoren und Aufsichtsbehörden.

Unser {product_name} ist bei {name} in 48h einsatzbereit: automatisches KI-Inventar, Risiko-Scoring, laufendes Monitoring.

Demo anfragen: {url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC
aiitecbuuss@gmail.com"""
        },
        3: {
            "subject": "Abschließende Nachricht: KI-Compliance für {name}",
            "body": """Sehr geehrte Damen und Herren,

ich melde mich ein letztes Mal zum Thema EU AI Act Compliance.

Falls {name} die regulatorischen Anforderungen noch nicht vollständig dokumentiert hat: unser {product_name} für {product_price} liefert in 48h alles, was Behörden und Investoren erwarten.

{url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC"""
        },
    },
    "C": {
        1: {
            "subject": "Handelsregister + Insolvenz-Intelligence für {name}",
            "body": """Sehr geehrte Damen und Herren,

als {branche}-Unternehmen treffen Sie täglich Entscheidungen auf Basis von Firmendaten — aber manuelles Monitoring von Handelsregister-Änderungen, Insolvenzanmeldungen und Kapitalveränderungen kostet zu viel Zeit.

Unser {product_name} überwacht automatisch alle relevanten DACH-Einträge in Ihrem Zielmarkt: neue GmbH-Gründungen, ZVG-Objekte, Insolvenzanmeldungen, Bonitätsänderungen — mit KI-Risiko-Scoring und Sofort-Telegram-Alerts.

Preis: {product_price}. Erste 7 Tage kostenlos.

Demo: {url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC Intelligence GmbH
aiitecbuuss@gmail.com"""
        },
        2: {
            "subject": "Re: B2B-Intelligence — Konkrete Zahlen für {branche}",
            "body": """Sehr geehrte Damen und Herren,

ich hatte Ihnen bereits geschrieben. Hier kurz konkrete Zahlen aus unserem System:

• 120–200 neue GmbH-Gründungen täglich in DACH
• 15–40 neue Insolvenzanmeldungen täglich (Score ≥ 70)
• 8–12 Zwangsversteigerungs-Objekte wöchentlich (Score ≥ 90 = Premium-Leads)

Unser {product_name} liefert diese Daten gefiltert, bewertet und sofort verwertbar an {name} — für {product_price}.

Demo anfragen: {url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC
aiitecbuuss@gmail.com"""
        },
        3: {
            "subject": "Letzte Nachricht: Intelligence-System für {name}",
            "body": """Sehr geehrte Damen und Herren,

dies ist meine letzte Kontaktaufnahme zu diesem Thema.

Falls {name} aktuell oder zukünftig Frühwarnsysteme für Insolvenz-Risiken, M&A-Targets oder Neugründungen sucht: unser {product_name} für {product_price} ist in 24h einsatzbereit.

{url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC"""
        },
    },
}

# ── Supabase Integration ───────────────────────────────────────────────────────

INIT_SQL = """
CREATE TABLE IF NOT EXISTS aiitec_companies (
    id            BIGSERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    domain        TEXT,
    email         TEXT NOT NULL UNIQUE,
    branche       TEXT,
    umsatzklasse  TEXT,
    land          TEXT DEFAULT 'DE',
    track         TEXT,
    product_key   TEXT,
    status        TEXT DEFAULT 'new',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aiitec_contacts (
    id            BIGSERIAL PRIMARY KEY,
    company_id    BIGINT REFERENCES aiitec_companies(id),
    name          TEXT,
    rolle         TEXT,
    email         TEXT NOT NULL UNIQUE,
    opt_out       BOOLEAN DEFAULT FALSE,
    source        TEXT DEFAULT 'seed',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aiitec_campaigns (
    id            BIGSERIAL PRIMARY KEY,
    company_id    BIGINT REFERENCES aiitec_companies(id),
    track         TEXT,
    product_key   TEXT,
    stage         INTEGER DEFAULT 1,
    sent_at       TIMESTAMPTZ,
    subject       TEXT,
    status        TEXT DEFAULT 'queued',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aiitec_email_events (
    id            BIGSERIAL PRIMARY KEY,
    campaign_id   BIGINT REFERENCES aiitec_campaigns(id),
    event_type    TEXT,
    detail        TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
"""

async def _sb(method: str, path: str, body: Optional[dict] = None,
              params: Optional[dict] = None) -> Any:
    url = _SB_URL().rstrip("/") + path
    headers = {
        "apikey": _SB_KEY(),
        "Authorization": f"Bearer {_SB_KEY()}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    async with aiohttp.ClientSession() as s:
        fn = getattr(s, method.lower())
        kw: dict = {"headers": headers}
        if body:
            kw["json"] = body
        if params:
            kw["params"] = params
        async with fn(url, **kw) as r:
            text = await r.text()
            if r.status >= 400:
                log.warning("Supabase %s %s → %s: %s", method, path, r.status, text[:200])
                return None
            try:
                return json.loads(text)
            except Exception:
                return text

async def init_db() -> None:
    log.info("Supabase-Tabellen initialisieren …")
    result = await _sb("POST", "/rest/v1/rpc/exec_sql", {"sql": INIT_SQL})
    if result is None:
        log.warning("init_db: RPC exec_sql nicht verfügbar — bitte SQL manuell ausführen")
        log.info("SQL:\n%s", INIT_SQL)
    else:
        log.info("Tabellen angelegt/verifiziert ✓")

async def seed_companies() -> int:
    log.info("Seed-Unternehmen laden (%d Einträge) …", len(COMPANIES_SEED))
    inserted = 0
    for c in COMPANIES_SEED:
        track = _get_track(c["branche"])
        product = _get_product(track, c["branche"])
        row = {
            "name": c["name"],
            "domain": c["domain"],
            "email": c["email"],
            "branche": c["branche"],
            "umsatzklasse": c.get("umsatz", "M"),
            "land": c.get("land", "DE"),
            "track": track,
            "product_key": list(PRODUCTS.keys())[list(PRODUCTS.values()).index(product)],
            "status": "new",
        }
        res = await _sb("POST", "/rest/v1/aiitec_companies",
                        body=row,
                        params={"on_conflict": "email"})
        if res:
            inserted += 1
    log.info("Seed-Unternehmen: %d geladen", inserted)
    return inserted

async def _get_queue(limit: int = EMAILS_PER_DAY) -> List[dict]:
    data = await _sb("GET", "/rest/v1/aiitec_companies",
                     params={"status": "eq.new", "limit": limit, "order": "id.asc"})
    return data or []

async def _get_followup_queue() -> List[dict]:
    now = datetime.now(timezone.utc)
    cutoff1 = (now - timedelta(days=FOLLOWUP_DAYS_1)).isoformat()
    cutoff2 = (now - timedelta(days=FOLLOWUP_DAYS_2)).isoformat()
    fu1 = await _sb("GET", "/rest/v1/aiitec_campaigns",
                    params={
                        "stage": "eq.1",
                        "status": "eq.sent",
                        "sent_at": f"lt.{cutoff1}",
                        "limit": "15",
                    })
    fu2 = await _sb("GET", "/rest/v1/aiitec_campaigns",
                    params={
                        "stage": "eq.2",
                        "status": "eq.sent",
                        "sent_at": f"lt.{cutoff2}",
                        "limit": "5",
                    })
    return (fu1 or []) + (fu2 or [])

async def _mark_company_sent(company_id: int, stage: int) -> None:
    status = "stage1" if stage == 1 else ("stage2" if stage == 2 else "done")
    await _sb("PATCH", f"/rest/v1/aiitec_companies?id=eq.{company_id}",
              body={"status": status})

async def _log_campaign(company_id: int, track: str, product_key: str,
                        stage: int, subject: str) -> Optional[int]:
    res = await _sb("POST", "/rest/v1/aiitec_campaigns",
                    body={
                        "company_id": company_id,
                        "track": track,
                        "product_key": product_key,
                        "stage": stage,
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                        "subject": subject,
                        "status": "sent",
                    })
    if res and isinstance(res, list):
        return res[0].get("id")
    return None

async def _log_event(campaign_id: int, event_type: str, detail: str = "") -> None:
    await _sb("POST", "/rest/v1/aiitec_email_events",
              body={
                  "campaign_id": campaign_id,
                  "event_type": event_type,
                  "detail": detail,
              })

# ── Email Senden ──────────────────────────────────────────────────────────────

def _send_email(to: str, subject: str, body: str) -> bool:
    """Sendet Email via SMTP-Pool (Round-Robin). Bei 550-Limit → nächster Account → SendGrid."""
    global _smtp_pool_idx
    _reset_smtp_if_new_day()
    pool = _get_smtp_pool()

    if not pool:
        log.error("  ✗  Kein SMTP-Account konfiguriert!")
        return False

    tried = 0
    while tried < len(pool):
        idx = _smtp_pool_idx % len(pool)
        _smtp_pool_idx += 1
        user, pwd = pool[idx]

        if user in _smtp_blocked_today:
            tried += 1
            continue

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = f"{_FROM_NAME} <{user}>"
            msg["To"]      = to
            msg["Reply-To"] = "aiitecbuuss@gmail.com"
            msg.attach(MIMEText(body, "plain", "utf-8"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
                s.login(user, pwd)
                s.sendmail(user, [to], msg.as_string())
            log.info("  ✉  Gesendet → %s [via %s]", to, user.split("@")[0])
            return True
        except Exception as e:
            err = str(e)
            if "550" in err and "limit" in err.lower():
                log.warning("  ⚠  Tageslimit erreicht für %s — weiter", user.split("@")[0])
                _smtp_blocked_today.add(user)
                tried += 1
                continue
            log.error("  ✗  Fehler → %s: %s", to, e)
            return False

    # Alle Gmail-Accounts geblockt → SendGrid-Fallback
    log.warning("  ↪  Alle Gmail-Accounts geblockt — Fallback auf SendGrid")
    return _send_via_sendgrid(to, subject, body)

# ── Personalisierung ──────────────────────────────────────────────────────────

def _personalize(company: dict, stage: int) -> tuple[str, str]:
    track = company.get("track", "A")
    branche = company.get("branche", "")
    product = _get_product(track, branche)
    prod_key = list(PRODUCTS.keys())[list(PRODUCTS.values()).index(product)]

    tpl = TEMPLATES.get(track, TEMPLATES["A"]).get(stage, TEMPLATES["A"][1])
    ctx = {
        "name": company["name"],
        "branche": branche,
        "product_name": product["name"],
        "product_price": product["price"],
        "product_promise": product["promise"],
        "url": _TOOL_URL,
    }
    subject = tpl["subject"].format(**ctx)
    body    = tpl["body"].format(**ctx)
    return subject, body

# ── Outreach Loop ─────────────────────────────────────────────────────────────

async def run_outreach() -> dict:
    stats = {"sent": 0, "failed": 0, "followup": 0}
    log.info("=== AIITEC Outreach gestartet ===")

    # Stage-1: neue Unternehmen
    queue = await _get_queue(EMAILS_PER_DAY - 5)
    for company in queue:
        subject, body = _personalize(company, stage=1)
        ok = _send_email(company["email"], subject, body)
        cid = await _log_campaign(
            company["id"],
            company.get("track", "A"),
            company.get("product_key", "lead_agent"),
            stage=1,
            subject=subject,
        )
        if cid:
            await _log_event(cid, "sent" if ok else "failed")
        await _mark_company_sent(company["id"], stage=1)
        if ok:
            stats["sent"] += 1
        else:
            stats["failed"] += 1
        await asyncio.sleep(3)

    # Follow-Up: Stage 2 & 3
    fu_queue = await _get_followup_queue()
    for campaign in fu_queue:
        cid = campaign["company_id"]
        comp_data = await _sb("GET", f"/rest/v1/aiitec_companies?id=eq.{cid}&limit=1")
        if not comp_data:
            continue
        company = comp_data[0]
        next_stage = campaign["stage"] + 1
        subject, body = _personalize(company, stage=next_stage)
        ok = _send_email(company["email"], subject, body)
        new_cid = await _log_campaign(
            cid,
            campaign.get("track", "A"),
            campaign.get("product_key", "lead_agent"),
            stage=next_stage,
            subject=subject,
        )
        if new_cid:
            await _log_event(new_cid, "followup_sent" if ok else "followup_failed")
        await _sb("PATCH", f"/rest/v1/aiitec_campaigns?id=eq.{campaign['id']}",
                  body={"status": "followed_up"})
        await _mark_company_sent(cid, next_stage)
        if ok:
            stats["followup"] += 1
        await asyncio.sleep(3)

    log.info("=== Lauf abgeschlossen: %s gesendet, %s Follow-Ups, %s Fehler ===",
             stats["sent"], stats["followup"], stats["failed"])
    return stats

# ── Statistik ─────────────────────────────────────────────────────────────────

async def show_stats() -> None:
    total   = await _sb("GET", "/rest/v1/aiitec_companies", params={"select": "count", "count": "exact"})
    sent    = await _sb("GET", "/rest/v1/aiitec_email_events",
                        params={"event_type": "eq.sent", "select": "count", "count": "exact"})
    fu      = await _sb("GET", "/rest/v1/aiitec_email_events",
                        params={"event_type": "eq.followup_sent", "select": "count", "count": "exact"})
    new_q   = await _sb("GET", "/rest/v1/aiitec_companies",
                        params={"status": "eq.new", "select": "count", "count": "exact"})

    def _cnt(r):
        if isinstance(r, list) and r:
            return r[0].get("count", "?")
        return "?"

    print("\n=== AIITEC Outreach Statistik ===")
    print(f"  Unternehmen gesamt : {_cnt(total)}")
    print(f"  In Queue (neu)     : {_cnt(new_q)}")
    print(f"  Emails Stage-1     : {_cnt(sent)}")
    print(f"  Follow-Ups gesendet: {_cnt(fu)}")
    print(f"  Tool-URL           : {_TOOL_URL}")
    print()

# ── Telegram Report ───────────────────────────────────────────────────────────

async def _tg(text: str) -> None:
    token = _TG_TOKEN()
    chat  = _TG_CHAT()
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram: %s", e)

async def _report(stats: dict) -> None:
    total = stats["sent"] + stats["followup"]
    msg = (
        f"🤖 *AIITEC Outreach Report*\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"✉️ Stage-1 gesendet: *{stats['sent']}*\n"
        f"🔄 Follow-Ups: *{stats['followup']}*\n"
        f"❌ Fehler: *{stats['failed']}*\n"
        f"📊 Gesamt heute: *{total}*\n\n"
        f"🔗 Tool: {_TOOL_URL}"
    )
    await _tg(msg)

# ── Daemon ────────────────────────────────────────────────────────────────────

async def daemon() -> None:
    log.info("AIITEC Outreach Machine gestartet — täglich %02d:%02d Uhr",
             DAILY_HOUR, DAILY_MINUTE)
    await _tg(f"🚀 *AIITEC Outreach Machine* gestartet\nLäuft täglich {DAILY_HOUR:02d}:{DAILY_MINUTE:02d} Uhr\nTool: {_TOOL_URL}")
    while True:
        now = datetime.now()
        target = now.replace(hour=DAILY_HOUR, minute=DAILY_MINUTE, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait = (target - now).total_seconds()
        log.info("Nächster Lauf: %s (in %.0f Min.)", target.strftime("%d.%m %H:%M"), wait / 60)
        await asyncio.sleep(wait)
        try:
            stats = await run_outreach()
            await _report(stats)
        except Exception as e:
            log.error("Lauf-Fehler: %s", e)
            await _tg(f"⚠️ AIITEC Outreach Fehler: {e}")

# ── Klasse für Scheduler-Integration ─────────────────────────────────────────

class AiitecOutreachMachine:
    """Wrapper für Scheduler-Integration (task_aiitec_b2b_outreach)."""

    async def run_daily_outreach(self) -> dict:
        await init_db()
        stats = await run_outreach()
        await _report(stats)
        return stats

    async def get_stats(self) -> dict:
        sb_url = _SB_URL()
        sb_key = _SB_KEY()
        if not sb_url or not sb_key:
            return {"ok": False, "error": "no Supabase credentials"}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{sb_url}/rest/v1/aiitec_campaigns",
                    headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"},
                    params={"select": "id,status,stage,sent_at", "limit": "1000"}
                ) as r:
                    rows = await r.json()
                    if not isinstance(rows, list):
                        return {"ok": False, "error": str(rows)}
                    total   = len(rows)
                    sent    = sum(1 for r in rows if r.get("status") == "sent")
                    replied = sum(1 for r in rows if r.get("status") == "replied")
                    failed  = sum(1 for r in rows if r.get("status") == "failed")
                    from datetime import date
                    today_s = str(date.today())
                    today   = sum(1 for r in rows if (r.get("sent_at") or "")[:10] == today_s)
                    return {"ok": True, "total": total, "sent": sent, "replied": replied,
                            "failed": failed, "today": today}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    args = sys.argv[1:]
    if "--init-db" in args:
        await init_db()
    elif "--seed" in args:
        await seed_companies()
    elif "--run-now" in args:
        stats = await run_outreach()
        await _report(stats)
    elif "--stats" in args:
        await show_stats()
    else:
        await daemon()

if __name__ == "__main__":
    asyncio.run(main())
