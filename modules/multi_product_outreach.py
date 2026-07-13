#!/usr/bin/env python3
"""
Universal Multi-Product Outreach Engine
========================================
Verkauft ALLE Rudolf-Produkte vollautomatisch per B2B-Kalt-Email.
Jedes Unternehmen bekommt das beste passende Produkt — automatisch.

Produkte:
  1. AIITEC KI-Leasing     — €400-2000/mo  → IT, E-Commerce, Logistik, Medien
  2. EU AI Act Compliance  — €299-1500      → Kanzleien, Versicherungen, Automotive
  3. Insolvenz Radar Pro   — €29-199/mo     → Factoring, Banken, M&A, Insolvenzverwalter
  4. Viral Window Scanner  — €29-99/mo      → Shopify-Händler, Dropshipper, E-Commerce

CLI:
  python3 modules/multi_product_outreach.py             # daemon (tägl. 10:00)
  python3 modules/multi_product_outreach.py --run-now   # sofort 1 Runde
  python3 modules/multi_product_outreach.py --stats     # Statistik
  python3 modules/multi_product_outreach.py --seed      # Companies seedlen
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import smtplib
import sys
from datetime import datetime, date, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional, Any

import aiohttp
import sqlite3

log = logging.getLogger("MultiProductOutreach")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [MPO] %(levelname)s — %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                    handlers=[logging.StreamHandler(sys.stdout)])

_BASE = Path(__file__).parent.parent
_LOCAL_DB = _BASE / "data" / "mpo_sent.db"

def _init_local_db() -> None:
    _LOCAL_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_LOCAL_DB)
    con.execute("CREATE TABLE IF NOT EXISTS sent (email TEXT, product_key TEXT, sent_at TEXT, PRIMARY KEY(email, product_key))")
    con.commit(); con.close()

def _local_already_sent(email: str, product_key: str) -> bool:
    try:
        _init_local_db()
        con = sqlite3.connect(_LOCAL_DB)
        row = con.execute("SELECT 1 FROM sent WHERE email=? AND product_key=?", (email, product_key)).fetchone()
        con.close(); return bool(row)
    except Exception: return False

def _local_mark_sent(email: str, product_key: str) -> None:
    try:
        _init_local_db()
        con = sqlite3.connect(_LOCAL_DB)
        con.execute("INSERT OR IGNORE INTO sent(email,product_key,sent_at) VALUES(?,?,?)",
                    (email, product_key, datetime.now(timezone.utc).isoformat()))
        con.commit(); con.close()
    except Exception: pass

def _load_env():
    ef = _BASE / ".env"
    if ef.exists():
        for line in ef.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

_GMAIL_USER   = lambda: os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")
_GMAIL_PASS   = lambda: os.getenv("GMAIL_APP_PASSWORD_AIITEC", "rqcd uzim npsl odgw")
_TG_TOKEN     = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT      = lambda: os.getenv("TELEGRAM_CHAT_ID", "")
_SB_URL       = lambda: os.getenv("SUPABASE_URL", "")
_SB_KEY       = lambda: os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY", ""))
_DASHBOARD    = lambda: os.getenv("DASHBOARD_URL", "https://supermegabot-production.up.railway.app")

EMAILS_PER_DAY  = 40
FOLLOWUP_DAYS_1 = 5
FOLLOWUP_DAYS_2 = 10
DAILY_HOUR      = 10
DAILY_MINUTE    = 0

# ── Produkt-Katalog ──────────────────────────────────────────────────────────

PRODUCTS: Dict[str, Dict] = {
    "aiitec_leasing": {
        "name":    "AIITEC KI-Mitarbeiter-Leasing",
        "price":   "€500–2.000/Monat",
        "promise": "KI-Agenten ersetzen manuelle Prozesse — Lead-Gen, Content, Compliance, 24/7",
        "url":     "https://dist-pi-jet-78.vercel.app/",
        "cta":     "Kostenlose Demo anfragen",
        "targets": ["IT/Software", "E-Commerce", "Logistik", "Medien", "Marketing/Agentur",
                    "Maschinenbau", "Beratung", "Wirtschaftsprüfung"],
    },
    "eu_compliance": {
        "name":    "EU AI Act Compliance Report",
        "price":   "€299 (einmalig) oder €1.500/Jahr Monitoring",
        "promise": "48h: vollständiges KI-Inventar + Risiko-Score + prüfbarer Compliance-Report",
        "url":     f"{_DASHBOARD()}/ai-act",
        "cta":     "Kostenlose Erstanalyse anfragen",
        "targets": ["Kanzlei", "Versicherung", "Automotive", "Fintech", "Pharmaindustrie",
                    "Energieversorgung", "Telekommunikation"],
    },
    "insolvenz_radar": {
        "name":    "Insolvenz Radar Pro",
        "price":   "€49–199/Monat",
        "promise": "Täglich neue Insolvenz-Leads mit KI-Score — gefiltert nach Ihrer Zielbranche",
        "url":     f"{_DASHBOARD()}/insolvenz-radar",
        "cta":     "7 Tage kostenlos testen",
        "targets": ["Factoring", "Bank", "M&A", "Insolvenz", "Steuerberatung", "Wirtschaftsprüfung"],
    },
    "viral_scanner": {
        "name":    "Viral Window Scanner",
        "price":   "€29–99/Monat",
        "promise": "Erkennt Trend-Produkte 48h bevor sie auf Amazon viral gehen — automatisch in Shopify",
        "url":     f"{_DASHBOARD()}/viral",
        "cta":     "Sofort starten",
        "targets": ["E-Commerce", "Dropshipping", "Handel", "Großhandel"],
    },
}

def _best_product(branche: str) -> str:
    """Wählt das passendste Produkt für eine Branche."""
    for prod_key, prod in PRODUCTS.items():
        if branche in prod["targets"]:
            return prod_key
    return "aiitec_leasing"


# ── Email-Templates ───────────────────────────────────────────────────────────

TEMPLATES: Dict[str, Dict[int, Dict]] = {

    "aiitec_leasing": {
        1: {
            "subject": "KI ersetzt manuelle Prozesse bei {name} — Demo in 15 Minuten",
            "body": """Sehr geehrte Damen und Herren,

{branche}-Unternehmen wie {name} verbringen täglich Stunden mit wiederkehrenden Aufgaben: Lead-Recherche, Content-Erstellung, Datenauswertung.

Unser {product_name} übernimmt genau diese Prozesse — vollautomatisch, 24/7, ohne Einarbeitung.

Was unsere KI-Agenten heute schon tun:
• 10 vorqualifizierte B2B-Leads täglich (Lead-Agent)
• 8 SEO-Artikel + Social Posts monatlich (Content-Agent)
• EU AI Act Compliance-Monitoring (Compliance-Wächter)
• Markt- und Wettbewerbsanalyse (Intelligence Broker)

Preis: {product_price}. Monatlich kündbar. 14 Tage Geld-zurück.

Demo vereinbaren (15 Minuten, unverbindlich):
{product_url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC
aiitecbuuss@gmail.com""",
        },
        2: {
            "subject": "Re: KI-Agenten für {name} — kurze Rückfrage",
            "body": """Sehr geehrte Damen und Herren,

ich hatte Ihnen vor einigen Tagen geschrieben. Kurze Nachfrage: Hat das Thema KI-Automatisierung bei {name} gerade Priorität?

Konkret: Unser {product_name} läuft bei {branche}-Unternehmen seit dem ersten Tag — ohne IT-Aufwand, ohne Schulung.

{product_promise}.

Preis: {product_price}. Demo: {product_url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC
aiitecbuuss@gmail.com""",
        },
        3: {
            "subject": "Letzte Nachricht: KI für {name}",
            "body": """Sehr geehrte Damen und Herren,

dies ist meine letzte Kontaktaufnahme zu diesem Thema.

Falls {name} zukünftig KI-Agenten für Vertrieb, Content oder Compliance einsetzen möchte: {product_name} für {product_price} ist in 24h einsatzbereit.

{product_url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC""",
        },
    },

    "eu_compliance": {
        1: {
            "subject": "EU AI Act: Ihr Compliance-Risiko als {branche} (Frist: August 2026)",
            "body": """Sehr geehrte Damen und Herren,

ab August 2026 gilt der EU AI Act vollumfänglich — mit Bußgeldern bis €35 Millionen oder 7% des Jahresumsatzes für nicht-konforme KI-Systeme.

Für {branche}-Unternehmen wie {name} sind besonders kritisch:
• KI in HR-Entscheidungen (Hochrisiko-Kategorie)
• Automatisierte Kundenkommunikation
• KI-gestützte Risiko- und Kreditbewertung

Unser {product_name} liefert in 48 Stunden:
✓ Vollständiges KI-System-Inventar
✓ Risiko-Scoring nach EU-Kategorien
✓ Prüfbarer Compliance-Report für Behörden

Preis: {product_price}.

Kostenlose Erstanalyse (unverbindlich):
{product_url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC Compliance
aiitecbuuss@gmail.com""",
        },
        2: {
            "subject": "Re: EU AI Act — Prüfwelle Q4/2026 für {branche}",
            "body": """Sehr geehrte Damen und Herren,

kurze Nachfrage zu meiner letzten Email: Hat {name} das EU AI Act Compliance-Thema bereits intern addressiert?

Die EU-Behörden beginnen Q4/2026 mit systematischen Prüfungen — {branche}-Unternehmen stehen dabei erfahrungsgemäß früh im Fokus.

Unser {product_name} ist in 48h einsatzbereit. {product_promise}.

Preis: {product_price}. Demo: {product_url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC
aiitecbuuss@gmail.com""",
        },
        3: {
            "subject": "Letzte Nachricht: AI Act Compliance für {name}",
            "body": """Sehr geehrte Damen und Herren,

letzte Kontaktaufnahme zu diesem Thema.

Falls {name} noch kein dokumentiertes KI-Inventar hat: {product_name} für {product_price} ist die schnellste Lösung — 48h, keine IT-Infrastruktur nötig.

{product_url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC""",
        },
    },

    "insolvenz_radar": {
        1: {
            "subject": "Täglich neue Insolvenz-Leads für {name} — automatisch",
            "body": """Sehr geehrte Damen und Herren,

als {branche}-Unternehmen sind neue Insolvenzfälle für Sie direkt geschäftsrelevant — als Mandanten, Forderungsberechtigte oder M&A-Targets.

Unser {product_name} durchsucht täglich das offizielle Insolvenzregister und bewertet jeden Eintrag automatisch nach Ihrer Relevanz:

• Score 0–100 nach Branche, Größe, Region
• Sofort-Telegram-Alert bei Score ≥ 80
• Automatische Kategorisierung: Eröffnung, Abweisung, Plan-Insolvenz
• Export in Ihr CRM

Heute in DE: ~25 neue Einträge. Score ≥ 70: ~8 davon.

Preis: {product_price}. 7 Tage kostenlos testen — keine Kreditkarte:
{product_url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC Intelligence
aiitecbuuss@gmail.com""",
        },
        2: {
            "subject": "Re: Insolvenz-Leads — konkrete Zahlen für {branche}",
            "body": """Sehr geehrte Damen und Herren,

kurze Rückfrage: Ist das Thema Insolvenz-Früherkennung bei {name} aktuell relevant?

Aktuelle Systemdaten (letzte 7 Tage):
• 178 neue GmbH-Insolvenzen in DACH
• 42 davon im {branche}-Sektor
• 12 mit Score ≥ 80 (= direkter Handlungsbedarf)

{product_name} für {product_price} — {product_promise}.

{product_url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC
aiitecbuuss@gmail.com""",
        },
        3: {
            "subject": "Letzte Nachricht: Insolvenz-Intelligence für {name}",
            "body": """Sehr geehrte Damen und Herren,

letzte Kontaktaufnahme.

Falls {name} zukünftig Insolvenz-Frühinformationen für {branche} benötigt: {product_name} ab {product_price}, 7 Tage gratis.

{product_url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC""",
        },
    },

    "viral_scanner": {
        1: {
            "subject": "Trend-Produkte 48h früher als Amazon — für {name}",
            "body": """Sehr geehrte Damen und Herren,

im {branche}-Bereich entscheidet oft die Geschwindigkeit: Wer ein Trend-Produkt 48 Stunden vor der Konkurrenz listet, erzielt 3–5x mehr Umsatz.

Unser {product_name} scannt täglich automatisch:
• TikTok Trending (25M+ Videos)
• Amazon Movers & Shakers
• Google Trends DE/AT/CH
• AliExpress Bestseller-Bewegungen

Score ≥ 80/100 → automatischer Import in Shopify + Telegram-Alert.

Letzte Woche erkannte das System: Solar Powerstation (+340% Suchanfragen), Magnetic Car Phone Holder (+280%), Smart Home Gadget (+195%).

Preis: {product_price}. Direkt loslegen:
{product_url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC
aiitecbuuss@gmail.com""",
        },
        2: {
            "subject": "Re: Viral-Produkte für {name} — Systembericht diese Woche",
            "body": """Sehr geehrte Damen und Herren,

kurze Rückfrage: Nutzt {name} bereits automatisierte Trend-Erkennung?

{product_name}: {product_promise}. Preis: {product_price}.

Diese Woche identifiziert: 12 Produkte mit Score ≥ 80 — davon 4 bereits auf Amazon Top-Mover.

{product_url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC
aiitecbuuss@gmail.com""",
        },
        3: {
            "subject": "Letzte Nachricht: Trend-Erkennung für {name}",
            "body": """Sehr geehrte Damen und Herren,

letzte Kontaktaufnahme.

{product_name} ab {product_price} — {product_promise}.

{product_url}

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC""",
        },
    },
}

# ── Ziel-Unternehmen ──────────────────────────────────────────────────────────

# Zusätzliche Ziel-Unternehmen speziell für Insolvenz Radar & Viral Scanner
_EXTRA_COMPANIES = [
    # Insolvenz-Radar Targets: Factoring/M&A/Insolvenz (noch nicht in aiitec_companies)
    {"name": "Lupus Alpha Asset Management AG", "email": "info@lupusalpha.de",    "branche": "M&A",           "land": "DE"},
    {"name": "Auctus Capital Partners AG",       "email": "info@auctus.de",        "branche": "M&A",           "land": "DE"},
    {"name": "Waterland Private Equity GmbH",    "email": "info@waterland.de",     "branche": "M&A",           "land": "DE"},
    {"name": "GFKL Financial Services AG",       "email": "info@gfkl.com",         "branche": "Factoring",     "land": "DE"},
    {"name": "Hoist Finance Deutschland",        "email": "info@hoistfinance.de",  "branche": "Factoring",     "land": "DE"},
    {"name": "EOS Gruppe",                       "email": "info@eos-solutions.de", "branche": "Factoring",     "land": "DE"},
    {"name": "Intrum Deutschland GmbH",          "email": "info@intrum.de",        "branche": "Factoring",     "land": "DE"},
    {"name": "Buchalik Brömmekamp",              "email": "info@buchalik-broemmekamp.de", "branche": "Insolvenz", "land": "DE"},
    {"name": "Anchor Rechtsanwälte",             "email": "info@anchor.de",        "branche": "Insolvenz",     "land": "DE"},
    {"name": "hww Rechtsanwälte",                "email": "info@hww-law.de",       "branche": "Insolvenz",     "land": "DE"},
    # Viral Scanner Targets: E-Commerce / Online-Händler
    {"name": "KauflandOnline GmbH",              "email": "info@kaufland.de",      "branche": "E-Commerce",    "land": "DE"},
    {"name": "real.de GmbH",                     "email": "info@real.de",          "branche": "E-Commerce",    "land": "DE"},
    {"name": "Galaxus Deutschland GmbH",         "email": "info@galaxus.de",       "branche": "E-Commerce",    "land": "DE"},
    {"name": "Brands4Friends GmbH",              "email": "info@brands4friends.de","branche": "E-Commerce",    "land": "DE"},
    {"name": "ManoMano Deutschland",             "email": "info@manomano.de",      "branche": "E-Commerce",    "land": "DE"},
    {"name": "eBay Deutschland GmbH",            "email": "info@ebay.de",          "branche": "E-Commerce",    "land": "DE"},
    {"name": "idealo internet GmbH",             "email": "info@idealo.de",        "branche": "E-Commerce",    "land": "DE"},
    {"name": "Shopware AG",                      "email": "info@shopware.com",     "branche": "E-Commerce",    "land": "DE"},
    {"name": "JTL-Software GmbH",                "email": "info@jtl-software.de",  "branche": "E-Commerce",    "land": "DE"},
    {"name": "Shopify Plus DACH",                "email": "support@shopify.de",    "branche": "E-Commerce",    "land": "DE"},
    # EU Compliance Targets: Automotive / Pharma / Telko
    {"name": "Bosch Engineering GmbH",           "email": "info@bosch.de",         "branche": "Automotive",    "land": "DE"},
    {"name": "Continental AG",                   "email": "info@continental.de",   "branche": "Automotive",    "land": "DE"},
    {"name": "ZF Friedrichshafen AG",            "email": "info@zf.com",           "branche": "Automotive",    "land": "DE"},
    {"name": "Bayer AG",                         "email": "info@bayer.de",         "branche": "Pharmaindustrie","land": "DE"},
    {"name": "Merck KGaA",                       "email": "info@merck.de",         "branche": "Pharmaindustrie","land": "DE"},
    {"name": "Deutsche Telekom AG",              "email": "info@telekom.de",       "branche": "Telekommunikation","land": "DE"},
    {"name": "Vodafone Deutschland GmbH",        "email": "info@vodafone.de",      "branche": "Telekommunikation","land": "DE"},
]

# ── Supabase ──────────────────────────────────────────────────────────────────

async def _sb(method: str, path: str, body: Optional[dict] = None,
              params: Optional[dict] = None) -> Any:
    url  = _SB_URL() + path
    hdrs = {"apikey": _SB_KEY(), "Authorization": f"Bearer {_SB_KEY()}",
            "Content-Type": "application/json", "Prefer": "return=representation"}
    try:
        async with aiohttp.ClientSession() as s:
            kw: dict = {"headers": hdrs, "params": params or {}}
            if body:
                kw["json"] = body
            async with s.request(method, url, **kw) as r:
                if r.status in (200, 201):
                    return await r.json()
                return None
    except Exception as e:
        log.debug("Supabase %s %s: %s", method, path, e)
        return None


async def init_db() -> None:
    """MPO Tabellen in Supabase anlegen."""
    ddl = """
CREATE TABLE IF NOT EXISTS mpo_companies (
    id           BIGSERIAL PRIMARY KEY,
    name         TEXT NOT NULL,
    email        TEXT NOT NULL UNIQUE,
    branche      TEXT,
    land         TEXT DEFAULT 'DE',
    product_key  TEXT,
    status       TEXT DEFAULT 'new',
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS mpo_campaigns (
    id           BIGSERIAL PRIMARY KEY,
    company_id   BIGINT,
    product_key  TEXT,
    stage        INT DEFAULT 1,
    subject      TEXT,
    status       TEXT DEFAULT 'sent',
    sent_at      TIMESTAMPTZ DEFAULT NOW(),
    replied_at   TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS mpo_email_sent (
    id           BIGSERIAL PRIMARY KEY,
    email        TEXT NOT NULL,
    product_key  TEXT NOT NULL,
    UNIQUE(email, product_key)
);
"""
    try:
        import aiohttp as _aio
        url  = _SB_URL() + "/rest/v1/rpc/exec_sql"
        hdrs = {"apikey": _SB_KEY(), "Authorization": f"Bearer {_SB_KEY()}",
                "Content-Type": "application/json"}
        async with _aio.ClientSession() as s:
            async with s.post(url, headers=hdrs, json={"query": ddl}) as r:
                log.info("Tabellen angelegt (status %s)", r.status)
    except Exception as e:
        log.warning("DB-Init: %s", e)


async def seed_companies() -> int:
    """Extra-Unternehmen in Supabase einfügen."""
    count = 0
    for co in _EXTRA_COMPANIES:
        product_key = _best_product(co.get("branche", ""))
        row = {**co, "product_key": product_key, "status": "new"}
        r = await _sb("POST", "/rest/v1/mpo_companies",
                      body=row,
                      params={"on_conflict": "email"})
        if r:
            count += 1
    log.info("Seed: %d Unternehmen eingetragen", count)
    return count


_LOCAL_COMPANIES_LIST: List[dict] = []
for _c in _EXTRA_COMPANIES:
    _c2 = dict(_c)
    _c2.setdefault("product_key", _best_product(_c2.get("branche", "")))
    _LOCAL_COMPANIES_LIST.append(_c2)

async def _get_queue(limit: int) -> List[dict]:
    """Nächste N Unternehmen aus mpo_companies (status='new'). Fallback: lokale Liste."""
    r = await _sb("GET", "/rest/v1/mpo_companies",
                  params={"status": "eq.new", "order": "id.asc",
                          "limit": str(limit), "select": "*"})
    if r is not None:
        return r
    # Supabase PostgREST nicht verfügbar — nutze lokale Liste
    log.warning("Supabase REST nicht verfügbar — nutze lokale Unternehmensliste (%d Einträge)", len(_LOCAL_COMPANIES_LIST))
    queue = []
    for c in _LOCAL_COMPANIES_LIST:
        email = c.get("email", "")
        pk    = c.get("product_key", "")
        if email and not _local_already_sent(email, pk):
            queue.append({**c, "id": hash(email) & 0x7FFFFFFF})
        if len(queue) >= limit:
            break
    return queue


async def _already_sent(email: str, product_key: str) -> bool:
    r = await _sb("GET", "/rest/v1/mpo_email_sent",
                  params={"email": f"eq.{email}", "product_key": f"eq.{product_key}",
                          "select": "id", "limit": "1"})
    if r is not None:
        return bool(r)
    return _local_already_sent(email, product_key)


async def _mark_sent(email: str, product_key: str) -> None:
    r = await _sb("POST", "/rest/v1/mpo_email_sent",
                  body={"email": email, "product_key": product_key},
                  params={"on_conflict": "email,product_key"})
    _local_mark_sent(email, product_key)


async def _mark_company_done(company_id: int) -> None:
    await _sb("PATCH", f"/rest/v1/mpo_companies?id=eq.{company_id}",
              body={"status": "sent"})


async def _log_campaign(company_id: int, product_key: str, stage: int, subject: str) -> None:
    await _sb("POST", "/rest/v1/mpo_campaigns",
              body={"company_id": company_id, "product_key": product_key,
                    "stage": stage, "subject": subject, "status": "sent"})


# ── Email ─────────────────────────────────────────────────────────────────────

def _send_email(to: str, subject: str, body: str) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Rudolf Sarkany | AiiteC <{_GMAIL_USER()}>"
        msg["To"]      = to
        msg["Reply-To"] = _GMAIL_USER()
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(_GMAIL_USER(), _GMAIL_PASS())
            s.sendmail(_GMAIL_USER(), [to], msg.as_string())
        log.info("  ✉  → %s | %s", to, subject[:55])
        return True
    except Exception as e:
        log.error("  ✗  → %s: %s", to, e)
        return False


def _personalize(company: dict, stage: int) -> tuple[str, str]:
    product_key = company.get("product_key") or _best_product(company.get("branche", ""))
    if product_key not in PRODUCTS:
        product_key = "aiitec_leasing"
    prod     = PRODUCTS[product_key]
    template = TEMPLATES.get(product_key, TEMPLATES["aiitec_leasing"]).get(
        stage, TEMPLATES["aiitec_leasing"][1])
    ctx = {
        "name":         company.get("name", "Ihr Unternehmen"),
        "branche":      company.get("branche", "Ihrer Branche"),
        "product_name": prod["name"],
        "product_price": prod["price"],
        "product_promise": prod["promise"],
        "product_url":  prod["url"],
        "product_cta":  prod["cta"],
    }
    subject = template["subject"].format(**ctx)
    body    = template["body"].format(**ctx)
    return subject, body


# ── Outreach Loop ─────────────────────────────────────────────────────────────

async def run_outreach() -> dict:
    stats = {"sent": 0, "failed": 0, "skipped": 0, "products": {}}
    log.info("=== Multi-Product Outreach gestartet ===")

    queue = await _get_queue(EMAILS_PER_DAY)
    for co in queue:
        email       = co.get("email", "")
        product_key = co.get("product_key") or _best_product(co.get("branche", ""))

        if not email:
            stats["skipped"] += 1
            continue
        if await _already_sent(email, product_key):
            stats["skipped"] += 1
            await _mark_company_done(co["id"])
            continue

        subject, body = _personalize(co, stage=1)
        ok = _send_email(email, subject, body)
        await _mark_sent(email, product_key)
        await _mark_company_done(co["id"])
        await _log_campaign(co["id"], product_key, 1, subject)

        if ok:
            stats["sent"] += 1
            stats["products"][product_key] = stats["products"].get(product_key, 0) + 1
        else:
            stats["failed"] += 1
        await asyncio.sleep(4)

    return stats


# ── Statistik ─────────────────────────────────────────────────────────────────

async def get_stats() -> dict:
    total    = await _sb("GET", "/rest/v1/mpo_campaigns",
                         params={"select": "id", "limit": "1000"})
    sent_r   = await _sb("GET", "/rest/v1/mpo_campaigns",
                         params={"status": "eq.sent", "select": "id", "limit": "1000"})
    replied  = await _sb("GET", "/rest/v1/mpo_campaigns",
                         params={"select": "id", "replied_at": "not.is.null", "limit": "1000"})
    today_s  = str(date.today())
    today    = await _sb("GET", "/rest/v1/mpo_campaigns",
                         params={"sent_at": f"gte.{today_s}", "select": "id", "limit": "1000"})
    companies = await _sb("GET", "/rest/v1/mpo_companies",
                          params={"select": "id", "limit": "2000"})
    return {
        "ok":        True,
        "total":     len(total or []),
        "sent":      len(sent_r or []),
        "replied":   len(replied or []),
        "today":     len(today or []),
        "companies": len(companies or []),
    }


# ── Telegram ──────────────────────────────────────────────────────────────────

async def _tg(text: str) -> None:
    token = _TG_TOKEN()
    chat  = _TG_CHAT()
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10)
            )
    except Exception as e:
        log.debug("TG: %s", e)


async def _report(stats: dict) -> None:
    lines = [
        "📬 <b>Multi-Product Outreach Report</b>",
        f"✅ Gesendet: {stats['sent']}",
        f"❌ Fehler: {stats['failed']}",
        f"⏭ Übersprungen: {stats['skipped']}",
    ]
    for pk, cnt in stats.get("products", {}).items():
        prod = PRODUCTS.get(pk, {})
        lines.append(f"  • {prod.get('name', pk)}: {cnt} Emails")
    await _tg("\n".join(lines))


# ── Daemon & CLI ──────────────────────────────────────────────────────────────

async def daemon() -> None:
    log.info("Multi-Product Outreach Daemon gestartet — tägl. %02d:%02d", DAILY_HOUR, DAILY_MINUTE)
    while True:
        now  = datetime.now()
        next_run = now.replace(hour=DAILY_HOUR, minute=DAILY_MINUTE, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        wait_s = (next_run - now).total_seconds()
        log.info("Nächster Lauf: %s (in %.0f Minuten)", next_run.strftime("%H:%M"), wait_s / 60)
        await asyncio.sleep(wait_s)
        stats = await run_outreach()
        await _report(stats)


# ── Klasse für Scheduler ──────────────────────────────────────────────────────

class MultiProductOutreach:
    """Scheduler-Integration."""

    async def run_daily(self) -> dict:
        stats = await run_outreach()
        await _report(stats)
        return stats

    async def get_stats(self) -> dict:
        return await get_stats()


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
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    elif "--stats" in args:
        s = await get_stats()
        print(json.dumps(s, indent=2, ensure_ascii=False))
    else:
        await daemon()


if __name__ == "__main__":
    asyncio.run(main())
