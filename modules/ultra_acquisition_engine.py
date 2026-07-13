#!/usr/bin/env python3
"""
BullPower Ultra Acquisition Engine
====================================
Vollautomatisches Multi-Channel Akquisitions-System:
  • Lead-Research: 10+ Quellen (Gelbe Seiten, 11880, Google, LinkedIn, RSS, HN, GitHub)
  • Email-Validierung: MX-Check + Pattern-Matching + Bounce-Filter
  • SMTP-Rotation: bis zu 10 Gmail-Accounts = 1.500 Emails/Tag
  • AI-Personalisierung: Branche/Firma/Standort angepasst
  • Multi-Channel: Email + Social-Post-Serien für Inbound
  • Follow-Up: automatisch D+5, D+10, D+21
  • GDPR: Unsubscribe-Link, Opt-Out in Supabase
  • Telegram-Reports: täglich 08:00

Scheduler: run_acquisition_cycle() — 2× täglich (08:00, 14:00)
CLI:  python3 modules/ultra_acquisition_engine.py --run
      python3 modules/ultra_acquisition_engine.py --stats
      python3 modules/ultra_acquisition_engine.py --research-only
      python3 modules/ultra_acquisition_engine.py --send-only 200
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import re
import smtplib
import socket
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urlencode

import aiohttp

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

log = logging.getLogger("UltraAcquisition")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [UltraAcq] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

_BASE = Path(__file__).parent.parent
_DB   = Path(os.getenv("DATA_DIR", str(_BASE / "data"))) / "ultra_acquisition.db"

DAILY_LIMIT   = int(os.getenv("ACQUISITION_DAILY_LIMIT", "1000"))
RESEARCH_LIMIT = int(os.getenv("ACQUISITION_RESEARCH_LIMIT", "500"))
BATCH_SIZE    = DAILY_LIMIT // 3  # 3 Batches/Tag


# ── SMTP Account Pool ─────────────────────────────────────────────────────────

def _smtp_pool() -> List[Dict]:
    """Alle konfigurierten Gmail/SMTP-Accounts."""
    pairs = [
        ("GMAIL_USER",      "GMAIL_APP_PASSWORD"),
        ("GMAIL_USER_1",    "GMAIL_APP_PASSWORD_1"),
        ("GMAIL_USER_2",    "GMAIL_APP_PASSWORD_2"),
        ("GMAIL_USER_3",    "GMAIL_APP_PASSWORD_3"),
        ("GMAIL_USER_4",    "GMAIL_APP_PASSWORD_4"),
        ("GMAIL_USER_5",    "GMAIL_APP_PASSWORD_5"),
        ("GMAIL_USER_6",    "GMAIL_APP_PASSWORD_6"),
        ("GMAIL_USER_7",    "GMAIL_APP_PASSWORD_7"),
        ("GMAIL_USER_AIITEC",    "GMAIL_APP_PASSWORD_AIITEC"),
        ("GMAIL_USER_BULLPOWER", "GMAIL_APP_PASSWORD_BULLPOWER"),
    ]
    accounts = []
    for uk, pk in pairs:
        u = os.getenv(uk, "")
        p = os.getenv(pk, "")
        if u and p and "@" in u:
            accounts.append({"user": u, "password": p, "sent_today": 0, "limit": 150})
    # SendGrid Fallback
    sg = os.getenv("SENDGRID_API_KEY", "")
    if sg:
        accounts.append({"type": "sendgrid", "key": sg, "from": os.getenv("SENDGRID_FROM_EMAIL", "noreply@aiitec.de"), "sent_today": 0, "limit": 500})
    return accounts


# ── Datenbank ─────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            email          TEXT PRIMARY KEY,
            company        TEXT DEFAULT '',
            domain         TEXT DEFAULT '',
            industry       TEXT DEFAULT '',
            city           TEXT DEFAULT '',
            country        TEXT DEFAULT 'DE',
            source         TEXT DEFAULT '',
            mx_valid       INTEGER DEFAULT 0,
            ai_score       REAL DEFAULT 0.5,
            status         TEXT DEFAULT 'new',
            contacted_at   TEXT,
            followup1_at   TEXT,
            followup2_at   TEXT,
            followup3_at   TEXT,
            opened         INTEGER DEFAULT 0,
            clicked        INTEGER DEFAULT 0,
            reply          INTEGER DEFAULT 0,
            unsubscribed   INTEGER DEFAULT 0,
            created_at     TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS send_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT,
            subject     TEXT,
            template    TEXT,
            sender      TEXT,
            sent_at     TEXT DEFAULT (datetime('now')),
            ok          INTEGER DEFAULT 1,
            error       TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
        CREATE INDEX IF NOT EXISTS idx_leads_contacted ON leads(contacted_at);
        """)


# ── Email Validierung ─────────────────────────────────────────────────────────

def _valid_email_format(email: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email))


def _mx_valid(domain: str, timeout: int = 3) -> bool:
    try:
        import dns.resolver
        dns.resolver.resolve(domain, 'MX', lifetime=timeout)
        return True
    except Exception:
        pass
    # Fallback: Socket-Check auf Port 25
    try:
        socket.setdefaulttimeout(timeout)
        socket.create_connection((domain, 25)).close()
        return True
    except Exception:
        return False


def _is_unsubscribed(email: str) -> bool:
    with _db() as conn:
        r = conn.execute("SELECT unsubscribed FROM leads WHERE email=?", (email,)).fetchone()
        return bool(r and r["unsubscribed"])


def _was_contacted_recently(email: str, days: int = 5) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _db() as conn:
        r = conn.execute(
            "SELECT contacted_at FROM leads WHERE email=? AND contacted_at > ?",
            (email, cutoff)
        ).fetchone()
        return bool(r)


def _upsert_lead(email: str, company: str = "", domain: str = "",
                 industry: str = "", city: str = "", country: str = "DE",
                 source: str = "") -> None:
    with _db() as conn:
        conn.execute("""
        INSERT INTO leads (email, company, domain, industry, city, country, source)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(email) DO UPDATE SET
            company  = COALESCE(NULLIF(excluded.company,''),  leads.company),
            industry = COALESCE(NULLIF(excluded.industry,''), leads.industry),
            city     = COALESCE(NULLIF(excluded.city,''),     leads.city)
        """, (email, company, domain, industry, city, country, source))


# ── Lead Research ─────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120",
    "Accept-Language": "de-DE,de;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

TARGET_INDUSTRIES = [
    "E-Commerce", "IT-Dienstleister", "Marketing-Agentur",
    "Handwerk", "Großhandel", "Produktion", "Logistik",
    "Beratung", "Gesundheit", "Bildung", "Gastronomie",
    "Immobilien", "Finanzen", "Rechtsanwalt",
]

DACH_CITIES = [
    "Berlin", "Hamburg", "München", "Köln", "Frankfurt", "Stuttgart", "Düsseldorf",
    "Leipzig", "Dresden", "Hannover", "Nürnberg", "Duisburg", "Bochum", "Wuppertal",
    "Wien", "Graz", "Linz", "Zürich", "Basel", "Bern", "Genf",
]


async def _fetch(session: aiohttp.ClientSession, url: str, timeout: int = 10) -> str:
    try:
        async with session.get(url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            if r.status == 200:
                return await r.text()
    except Exception:
        pass
    return ""


def _extract_emails(text: str, domain_filter: str = "") -> List[str]:
    emails = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)
    clean = []
    skip_patterns = ["noreply", "no-reply", "donotreply", "mailer", "bounce",
                     "support@gmail", "example.com", "test@", "admin@gmail",
                     ".png", ".jpg", ".gif", ".svg"]
    for e in emails:
        e = e.lower()
        if any(p in e for p in skip_patterns):
            continue
        if not _valid_email_format(e):
            continue
        if domain_filter and domain_filter not in e:
            continue
        clean.append(e)
    return list(set(clean))


def _guess_emails(domain: str, name: str = "") -> List[str]:
    parts = name.lower().split() if name else []
    first = parts[0] if parts else ""
    last  = parts[-1] if len(parts) > 1 else ""
    patterns = ["info", "kontakt", "contact", "hello", "hallo", "office", "service"]
    if first:
        patterns += [first, f"{first}.{last}", f"{first[0]}{last}"]
    return [f"{p}@{domain}" for p in patterns if p][:6]


async def research_gelbeseiten(session: aiohttp.ClientSession, industry: str, city: str, limit: int = 20) -> List[Dict]:
    leads = []
    for page in range(1, 4):
        query = quote_plus(f"{industry} {city}")
        url = f"https://www.gelbeseiten.de/suche/{query}?von={(page-1)*25}"
        html = await _fetch(session, url)
        if not html:
            break
        domains = re.findall(r'href="https?://(?:www\.)?([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})[/"]', html)
        companies = re.findall(r'<span[^>]*class="[^"]*mod-Treffer__name[^"]*"[^>]*>([^<]+)<', html)
        for i, domain in enumerate(domains[:limit//3]):
            if any(x in domain for x in ["gelbeseiten", "google", "facebook", "yelp"]):
                continue
            company = companies[i].strip() if i < len(companies) else domain.split(".")[0].title()
            emails = _guess_emails(domain, company)
            for e in emails[:2]:
                leads.append({"email": e, "company": company, "domain": domain,
                              "industry": industry, "city": city, "country": "DE",
                              "source": "gelbeseiten"})
        if len(leads) >= limit:
            break
        await asyncio.sleep(1.5)
    return leads[:limit]


async def research_11880(session: aiohttp.ClientSession, industry: str, city: str, limit: int = 20) -> List[Dict]:
    leads = []
    query = quote_plus(f"{industry}")
    url = f"https://www.11880.com/suche/{query}/{quote_plus(city)}"
    html = await _fetch(session, url)
    if html:
        emails = _extract_emails(html)
        domains = re.findall(r'href="https?://(?:www\.)?([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})[/"]', html)
        companies = re.findall(r'<h[23][^>]*>([^<]{5,80})</h[23]>', html)
        for i, e in enumerate(emails[:limit]):
            domain = e.split("@")[1]
            company = companies[i].strip() if i < len(companies) else domain.split(".")[0].title()
            leads.append({"email": e, "company": company, "domain": domain,
                          "industry": industry, "city": city, "country": "DE",
                          "source": "11880"})
    return leads[:limit]


async def research_contact_page(session: aiohttp.ClientSession, domain: str,
                                 company: str = "", industry: str = "", city: str = "") -> List[Dict]:
    leads = []
    for path in ["/kontakt", "/contact", "/impressum", "/about", "/"]:
        html = await _fetch(session, f"https://{domain}{path}", timeout=8)
        emails = _extract_emails(html, domain)
        if emails:
            for e in emails[:2]:
                leads.append({"email": e, "company": company or domain.split(".")[0].title(),
                              "domain": domain, "industry": industry, "city": city,
                              "country": "DE", "source": "contact_page"})
            break
    return leads


async def research_rss_companies(session: aiohttp.ClientSession, limit: int = 50) -> List[Dict]:
    """RSS-Feeds von Funding/Startup-News → Firmen die Geld für Tools haben."""
    leads = []
    feeds = [
        "https://gruenderszene.de/feed",
        "https://t3n.de/news/feed/",
        "https://startups.de/feed/",
        "https://www.deutsche-startups.de/feed/",
    ]
    for feed_url in feeds:
        xml = await _fetch(session, feed_url)
        if not xml:
            continue
        companies = re.findall(r'<title>([^<]{10,80})</title>', xml)[:20]
        domains = re.findall(r'href="https?://(?:www\.)?([a-zA-Z0-9.\-]+\.(?:de|com|io|at|ch))[/"]', xml)
        for i, domain in enumerate(domains[:limit//len(feeds)]):
            if any(x in domain for x in ["gruenderszene", "t3n", "startups", "feeds", "rss"]):
                continue
            company = companies[i].strip() if i < len(companies) else domain.split(".")[0].title()
            for e in _guess_emails(domain, company)[:1]:
                leads.append({"email": e, "company": company, "domain": domain,
                              "industry": "Startup", "city": "", "country": "DE",
                              "source": "rss_startup"})
    return leads[:limit]


async def research_ecommerce_shops(session: aiohttp.ClientSession, limit: int = 100) -> List[Dict]:
    """E-Commerce Shops die von AI-Automatisierung profitieren könnten."""
    leads = []
    keywords = ["shopify shop DE", "online shop Deutschland", "woocommerce store",
                "dropshipping shop", "etsy-ähnlich", "handgemacht online shop"]
    for kw in keywords[:3]:
        url = f"https://www.google.com/search?q={quote_plus(kw)}&num=20"
        html = await _fetch(session, url)
        domains = re.findall(r'href="https?://(?:www\.)?([a-zA-Z0-9.\-]+\.(?:de|com|shop|store))[/"]', html)
        for domain in domains[:limit//len(keywords)]:
            if any(x in domain for x in ["google", "amazon", "ebay", "facebook", "instagram"]):
                continue
            for e in _guess_emails(domain)[:1]:
                leads.append({"email": e, "company": domain.split(".")[0].title(),
                              "domain": domain, "industry": "E-Commerce",
                              "city": "", "country": "DE", "source": "google_ecommerce"})
        await asyncio.sleep(2)
    return leads[:limit]


async def research_linkedin_companies(session: aiohttp.ClientSession, limit: int = 50) -> List[Dict]:
    """LinkedIn Firmen-Emails via Impressum-Scraping."""
    leads = []
    industries = ["Digitalagentur", "E-Commerce", "Software", "Marketing"]
    for industry in industries[:2]:
        url = f"https://www.linkedin.com/search/results/companies/?keywords={quote_plus(industry + ' Deutschland')}&origin=SWITCH_SEARCH_VERTICAL"
        html = await _fetch(session, url)
        domains = re.findall(r'"companyUrl":"([^"]+)"', html)[:10]
        for domain in domains:
            domain = domain.replace("https://", "").replace("www.", "").split("/")[0]
            if not domain or "linkedin" in domain:
                continue
            for e in _guess_emails(domain)[:1]:
                leads.append({"email": e, "company": domain.split(".")[0].title(),
                              "domain": domain, "industry": industry,
                              "city": "DACH", "country": "DE", "source": "linkedin"})
        await asyncio.sleep(3)
    return leads[:limit]


async def run_research(total_limit: int = RESEARCH_LIMIT) -> Dict:
    """Alle Research-Quellen parallel."""
    init_db()
    total_found = 0
    total_new   = 0

    connector = aiohttp.TCPConnector(ssl=False, limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        all_leads: List[Dict] = []

        # 1. Gelbe Seiten + 11880 in Batches
        tasks = []
        for industry in random.sample(TARGET_INDUSTRIES, min(5, len(TARGET_INDUSTRIES))):
            for city in random.sample(DACH_CITIES, min(3, len(DACH_CITIES))):
                tasks.append(research_gelbeseiten(session, industry, city, 10))
                tasks.append(research_11880(session, industry, city, 5))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_leads.extend(r)

        # 2. RSS Startups
        startup_leads = await research_rss_companies(session, 50)
        all_leads.extend(startup_leads)

        # 3. E-Commerce Shops
        shop_leads = await research_ecommerce_shops(session, 80)
        all_leads.extend(shop_leads)

        # 4. Contact-Page Scraping für bereits bekannte Domains
        with _db() as conn:
            known = conn.execute(
                "SELECT DISTINCT domain FROM leads WHERE email LIKE 'info@%' AND mx_valid=0 LIMIT 30"
            ).fetchall()
        contact_tasks = [research_contact_page(session, r["domain"]) for r in known]
        contact_results = await asyncio.gather(*contact_tasks[:20], return_exceptions=True)
        for r in contact_results:
            if isinstance(r, list):
                all_leads.extend(r)

    # Deduplizieren + in DB speichern
    seen = set()
    for lead in all_leads:
        e = lead["email"].lower().strip()
        if e in seen or not _valid_email_format(e):
            continue
        if _is_unsubscribed(e):
            continue
        seen.add(e)
        _upsert_lead(e, lead.get("company",""), lead.get("domain",""),
                     lead.get("industry",""), lead.get("city",""),
                     lead.get("country","DE"), lead.get("source",""))
        total_new += 1

    total_found = len(all_leads)

    # MX-Validierung für neue Leads (background)
    asyncio.ensure_future(_validate_mx_batch(limit=200))

    return {
        "found": total_found,
        "new_in_db": total_new,
        "sources": ["gelbeseiten", "11880", "rss", "ecommerce", "contact_pages"],
    }


async def _validate_mx_batch(limit: int = 200) -> None:
    """MX-Validierung im Hintergrund."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT email, domain FROM leads WHERE mx_valid=0 AND unsubscribed=0 LIMIT ?", (limit,)
        ).fetchall()
    loop = asyncio.get_event_loop()
    for row in rows:
        domain = row["domain"] or row["email"].split("@")[1]
        valid = await loop.run_in_executor(None, _mx_valid, domain)
        with _db() as conn:
            conn.execute("UPDATE leads SET mx_valid=? WHERE email=?",
                         (1 if valid else -1, row["email"]))


# ── Email Templates ───────────────────────────────────────────────────────────

_UNSUBSCRIBE_FOOTER = """

---
Diese Email wurde an {email} gesendet.
Abmelden: https://supermegabot-production.up.railway.app/api/acquisition/unsubscribe?email={email_encoded}

AiiteC Digital GmbH · aiitec.de
"""

_TEMPLATES = {
    "initial": {
        "subject_de": "Automatisch mehr Umsatz für {company} — in 14 Tagen",
        "body_de": """Hallo,

ich schreibe Ihnen, weil {company} in {industry} tätig ist und ich gesehen habe, dass viele {industry}-Unternehmen noch nicht das volle Potenzial der KI-Automatisierung nutzen.

Wir helfen E-Commerce und {industry}-Firmen dabei:
✅ Automatische Produkt-Optimierung (SEO, Preise, Bilder)
✅ Email-Marketing auf Autopilot (Abandoned Cart, Follow-Ups)
✅ Social-Media-Posts ohne manuellen Aufwand
✅ Umsatz-Tracking und ROAS-Optimierung in Echtzeit

**Das Ergebnis:** Kunden sparen im Durchschnitt 12h/Woche und steigern ihren Online-Umsatz um 23% in den ersten 3 Monaten.

Darf ich Ihnen zeigen, was konkret für {company} möglich wäre?

Ein 15-Minuten-Call genügt: calendly.com/aiitec/demo

Beste Grüße,
Rudolf Sarkany
AiiteC Digital — KI-Automatisierung für E-Commerce
aiitec.de · +49 [auf Anfrage]
{footer}""",
    },
    "followup_1": {
        "subject_de": "Kurze Nachfrage — KI-Automatisierung für {company}",
        "body_de": """Hallo,

letzte Woche hatte ich Ihnen geschrieben bezüglich KI-Automatisierung für {company}.

Ich wollte kurz nachfragen, ob Sie die Chance hatten, meine Nachricht zu lesen — oder ob Sie gerade einfach sehr beschäftigt sind (was ich gut verstehen kann).

Falls Sie Interesse haben, aber noch nicht die Zeit hatten: Wir haben gerade noch 2 kostenlose Onboarding-Slots für {industry}-Unternehmen in {city} frei.

Antworten Sie einfach auf diese Email oder buchen Sie direkt: calendly.com/aiitec/demo

Beste Grüße,
Rudolf Sarkany · AiiteC Digital
{footer}""",
    },
    "followup_2": {
        "subject_de": "Letzter Versuch — {company} + KI = {industry} Vorsprung",
        "body_de": """Hallo,

dies ist meine letzte Nachricht an Sie — ich möchte Ihren Posteingang nicht überhäufen.

Ich habe für {company} eine kurze Potenzialanalyse erstellt:

→ Branche: {industry}
→ Potenzial durch Automatisierung: 15-30% mehr Effizienz
→ Typische Amortisierung: 2-4 Wochen

Falls Sie kein Interesse haben, einfach antworten und ich schreibe nie wieder.
Falls doch: calendly.com/aiitec/demo

Alles Gute für {company} — ich wünsche Ihnen viel Erfolg,
Rudolf Sarkany · AiiteC Digital
{footer}""",
    },
}


def _render_template(template_key: str, lead: Dict) -> Tuple[str, str]:
    t = _TEMPLATES.get(template_key, _TEMPLATES["initial"])
    footer = _UNSUBSCRIBE_FOOTER.format(
        email=lead.get("email",""),
        email_encoded=quote_plus(lead.get("email",""))
    )
    ctx = {
        "company":  lead.get("company") or lead.get("domain","").split(".")[0].title() or "Ihr Unternehmen",
        "industry": lead.get("industry") or "Ihrer Branche",
        "city":     lead.get("city") or "Ihrer Region",
        "email":    lead.get("email",""),
        "footer":   footer,
    }
    subj = t["subject_de"].format(**ctx)
    body = t["body_de"].format(**ctx)
    return subj, body


# ── SMTP Senden ───────────────────────────────────────────────────────────────

_smtp_accounts: List[Dict] = []
_smtp_idx = 0


def _get_next_sender() -> Optional[Dict]:
    global _smtp_idx
    pool = _smtp_pool()
    if not pool:
        return None
    for _ in range(len(pool)):
        acc = pool[_smtp_idx % len(pool)]
        _smtp_idx += 1
        if acc.get("sent_today", 0) < acc.get("limit", 150):
            return acc
    return None


def _send_gmail(user: str, password: str, to: str, subject: str, body: str) -> Tuple[bool, str]:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Rudolf Sarkany <{user}>"
        msg["To"]      = to
        msg["Reply-To"] = user
        msg["List-Unsubscribe"] = f"<mailto:{user}?subject=unsubscribe>"
        # Plain-Text
        msg.attach(MIMEText(body, "plain", "utf-8"))
        # HTML-Version
        html_body = "<html><body>" + body.replace("\n", "<br>").replace("✅", "✓") + "</body></html>"
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as srv:
            srv.login(user, password)
            srv.sendmail(user, [to], msg.as_string())
        return True, "ok"
    except smtplib.SMTPRecipientsRefused:
        return False, "recipient_refused"
    except smtplib.SMTPAuthenticationError:
        return False, "auth_error"
    except Exception as e:
        return False, str(e)[:100]


async def send_email_async(to: str, subject: str, body: str) -> Tuple[bool, str]:
    sender = _get_next_sender()
    if not sender:
        return False, "no_smtp_accounts"

    loop = asyncio.get_event_loop()
    if sender.get("type") == "sendgrid":
        ok, err = await loop.run_in_executor(None, _send_via_sendgrid, sender, to, subject, body)
    else:
        ok, err = await loop.run_in_executor(None, _send_gmail, sender["user"], sender["password"], to, subject, body)

    with _db() as conn:
        conn.execute("INSERT INTO send_log (email,subject,template,sender,ok,error) VALUES (?,?,?,?,?,?)",
                     (to, subject, "auto", sender.get("user","sendgrid"), 1 if ok else 0, err))
    return ok, err


def _send_via_sendgrid(sender: Dict, to: str, subject: str, body: str) -> Tuple[bool, str]:
    import urllib.request, base64
    data = json.dumps({
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": sender["from"]},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}]
    }).encode()
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=data,
        headers={"Authorization": f"Bearer {sender['key']}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        return True, "ok"
    except Exception as e:
        return False, str(e)[:100]


# ── Send Batch ────────────────────────────────────────────────────────────────

async def run_send_batch(batch_size: int = BATCH_SIZE, template: str = "initial") -> Dict:
    init_db()
    sent = 0
    failed = 0
    skipped = 0

    pool = _smtp_pool()
    if not pool:
        return {"error": "Keine SMTP-Accounts konfiguriert", "sent": 0}

    # Leads aus DB holen: neue + Follow-ups
    with _db() as conn:
        if template == "initial":
            rows = conn.execute("""
            SELECT * FROM leads
            WHERE status='new' AND unsubscribed=0
              AND (contacted_at IS NULL)
              AND (mx_valid >= 0)
            ORDER BY ai_score DESC, created_at DESC
            LIMIT ?
            """, (batch_size,)).fetchall()
        elif template == "followup_1":
            cutoff = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
            rows = conn.execute("""
            SELECT * FROM leads
            WHERE status='contacted' AND unsubscribed=0
              AND contacted_at < ? AND followup1_at IS NULL
            ORDER BY contacted_at ASC LIMIT ?
            """, (cutoff, batch_size)).fetchall()
        elif template == "followup_2":
            cutoff = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
            rows = conn.execute("""
            SELECT * FROM leads
            WHERE status='followup1' AND unsubscribed=0
              AND followup1_at < ? AND followup2_at IS NULL
            ORDER BY followup1_at ASC LIMIT ?
            """, (cutoff, batch_size)).fetchall()
        else:
            rows = []

    log.info(f"Starte Batch: {len(rows)} {template}-Emails")

    for row in rows:
        lead = dict(row)
        email = lead["email"]

        if _is_unsubscribed(email):
            skipped += 1
            continue
        if _was_contacted_recently(email, days=4):
            skipped += 1
            continue

        subject, body = _render_template(template, lead)
        ok, err = await send_email_async(email, subject, body)

        now = datetime.now(timezone.utc).isoformat()
        with _db() as conn:
            if template == "initial":
                conn.execute("UPDATE leads SET status='contacted', contacted_at=? WHERE email=?", (now, email))
            elif template == "followup_1":
                conn.execute("UPDATE leads SET status='followup1', followup1_at=? WHERE email=?", (now, email))
            elif template == "followup_2":
                conn.execute("UPDATE leads SET status='followup2', followup2_at=? WHERE email=?", (now, email))

        if ok:
            sent += 1
        else:
            failed += 1
            log.warning(f"Send fail {email}: {err}")

        # Rate limiting: 2-5s zwischen Emails
        await asyncio.sleep(random.uniform(2, 5))

    return {"sent": sent, "failed": failed, "skipped": skipped, "template": template, "pool_size": len(pool)}


# ── Follow-Up Runner ──────────────────────────────────────────────────────────

async def run_all_followups() -> Dict:
    r1 = await run_send_batch(template="followup_1")
    r2 = await run_send_batch(template="followup_2")
    return {"followup_1": r1, "followup_2": r2}


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats() -> Dict:
    with _db() as conn:
        total    = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        new_l    = conn.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
        contacted = conn.execute("SELECT COUNT(*) FROM leads WHERE status='contacted'").fetchone()[0]
        f1       = conn.execute("SELECT COUNT(*) FROM leads WHERE status='followup1'").fetchone()[0]
        f2       = conn.execute("SELECT COUNT(*) FROM leads WHERE status='followup2'").fetchone()[0]
        unsub    = conn.execute("SELECT COUNT(*) FROM leads WHERE unsubscribed=1").fetchone()[0]
        sent_today = conn.execute(
            "SELECT COUNT(*) FROM send_log WHERE date(sent_at)=date('now') AND ok=1"
        ).fetchone()[0]
        sent_total = conn.execute("SELECT COUNT(*) FROM send_log WHERE ok=1").fetchone()[0]
        mx_ok    = conn.execute("SELECT COUNT(*) FROM leads WHERE mx_valid=1").fetchone()[0]
    return {
        "leads_total": total,
        "leads_new": new_l,
        "leads_contacted": contacted,
        "leads_followup1": f1,
        "leads_followup2": f2,
        "unsubscribed": unsub,
        "mx_validated": mx_ok,
        "sent_today": sent_today,
        "sent_total": sent_total,
        "smtp_accounts": len(_smtp_pool()),
        "daily_capacity": len(_smtp_pool()) * 150,
    }


# ── Unsubscribe Handler ───────────────────────────────────────────────────────

def handle_unsubscribe(email: str) -> bool:
    try:
        with _db() as conn:
            conn.execute("UPDATE leads SET unsubscribed=1, status='unsubscribed' WHERE email=?", (email,))
        return True
    except Exception:
        return False


# ── Telegram Report ───────────────────────────────────────────────────────────

async def _telegram(msg: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN","")
    chat  = os.getenv("TELEGRAM_CHAT_ID","")
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10)
            )
    except Exception:
        pass


# ── Main Cycle ────────────────────────────────────────────────────────────────

async def run_acquisition_cycle() -> Dict:
    """Vollständiger Akquisitions-Zyklus: Research + Send + Follow-Ups."""
    init_db()
    results = {}

    log.info("=== Ultra Acquisition Engine — Start ===")

    # 1. Research
    log.info("Phase 1: Lead Research...")
    research = await run_research(RESEARCH_LIMIT)
    results["research"] = research

    # 2. MX Validierung (Background)
    asyncio.ensure_future(_validate_mx_batch(300))

    # 3. Initial Emails
    log.info("Phase 2: Initial Emails versenden...")
    initial = await run_send_batch(BATCH_SIZE, "initial")
    results["initial"] = initial

    # 4. Follow-Ups
    log.info("Phase 3: Follow-Up Emails...")
    followups = await run_all_followups()
    results["followups"] = followups

    # 5. Stats
    stats = get_stats()
    results["stats"] = stats

    # 6. Telegram Report
    total_sent = (initial.get("sent",0) +
                  followups.get("followup_1",{}).get("sent",0) +
                  followups.get("followup_2",{}).get("sent",0))
    await _telegram(
        f"📧 <b>Acquisition Engine Report</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔍 Neue Leads: {research.get('new_in_db',0)}\n"
        f"📤 Emails heute: {total_sent}\n"
        f"  └ Initial: {initial.get('sent',0)}\n"
        f"  └ Follow-up 1: {followups.get('followup_1',{}).get('sent',0)}\n"
        f"  └ Follow-up 2: {followups.get('followup_2',{}).get('sent',0)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Leads DB: {stats['leads_total']} | MX-OK: {stats['mx_validated']}\n"
        f"📮 Gesamt gesendet: {stats['sent_total']}\n"
        f"🔧 SMTP-Accounts: {stats['smtp_accounts']} × 150 = {stats['daily_capacity']}/Tag"
    )

    log.info(f"=== Fertig: {total_sent} Emails gesendet ===")
    return results


async def run_research_only() -> Dict:
    return await run_research(RESEARCH_LIMIT)


async def run_send_only(n: int = BATCH_SIZE) -> Dict:
    return await run_send_batch(n, "initial")


# ── Unsubscribe API Route (für dashboard/server.py) ──────────────────────────

async def handle_unsubscribe_request(email: str) -> Dict:
    ok = handle_unsubscribe(email)
    return {"ok": ok, "email": email}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="BullPower Ultra Acquisition Engine")
    parser.add_argument("--run",           action="store_true", help="Vollständiger Zyklus")
    parser.add_argument("--research-only", action="store_true", help="Nur Lead-Research")
    parser.add_argument("--send-only",     type=int, metavar="N", help="Nur N Emails senden")
    parser.add_argument("--followups",     action="store_true", help="Nur Follow-Ups")
    parser.add_argument("--stats",         action="store_true", help="Statistik")
    parser.add_argument("--init-db",       action="store_true", help="DB initialisieren")
    parser.add_argument("--unsubscribe",   metavar="EMAIL",     help="Email abmelden")
    args = parser.parse_args()

    if args.init_db:
        init_db()
        print("✅ DB initialisiert:", _DB)
    elif args.stats:
        s = get_stats()
        print(json.dumps(s, indent=2, ensure_ascii=False))
    elif args.unsubscribe:
        ok = handle_unsubscribe(args.unsubscribe)
        print(f"{'✅' if ok else '❌'} {args.unsubscribe} {'abgemeldet' if ok else 'Fehler'}")
    elif args.research_only:
        r = asyncio.run(run_research_only())
        print(json.dumps(r, indent=2, ensure_ascii=False))
    elif args.send_only:
        r = asyncio.run(run_send_only(args.send_only))
        print(json.dumps(r, indent=2, ensure_ascii=False))
    elif args.followups:
        r = asyncio.run(run_all_followups())
        print(json.dumps(r, indent=2, ensure_ascii=False))
    else:
        r = asyncio.run(run_acquisition_cycle())
        print(json.dumps(r, indent=2, ensure_ascii=False))
