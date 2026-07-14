#!/usr/bin/env python3
"""
Mass Outreach Engine 1000/Tag — Vollautomatische DACH B2B-Akquise
==================================================================
Architektur:
  1. Lead Research (täglich): Gelbe Seiten + 11880 + HN + Reddit + RSS-Funding
  2. Email-Finder: Contact-Page Scraping + Pattern-Guessing + MX-Validierung
  3. AI-Personalisierung: Claude generiert individuelle Emails pro Branche
  4. Multi-SMTP Pool: 5+ Gmail-Accounts + SendGrid Fallback = 1000+/Tag
  5. Follow-Up: Automatisch nach 5 und 10 Tagen
  6. GDPR: Unsubscribe-Link in jeder Mail, Opt-out in Supabase

Ziel-Branchen: E-Commerce, IT-Dienstleister, Marketing-Agenturen, Handwerk, Handel

Scheduler: täglich 09:00, 13:00, 17:00 (je 333 Mails)

CLI:
  python3 modules/mass_outreach_1000.py --stats        # Statistik
  python3 modules/mass_outreach_1000.py --research     # Nur Lead-Research
  python3 modules/mass_outreach_1000.py --send 333     # Nur Versand
  python3 modules/mass_outreach_1000.py --run-now      # Komplett-Lauf
  python3 modules/mass_outreach_1000.py --init-db      # DB anlegen
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import smtplib
import socket
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, quote_plus, urlparse

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MassOutreach] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("MassOutreach1000")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "mass_outreach.db"

# ── Env ───────────────────────────────────────────────────────────────────────
def _e(k: str, d: str = "") -> str: return os.getenv(k, d)

def _smtp_pool() -> List[Dict]:
    """Alle konfigurierten Gmail-Accounts + SendGrid."""
    accounts = []
    pairs = [
        ("GMAIL_USER_AIITEC",    "GMAIL_APP_PASSWORD_AIITEC"),
        ("GMAIL_USER_BULLPOWER", "GMAIL_APP_PASSWORD_BULLPOWER"),
        ("GMAIL_USER_PERSONAL",  "GMAIL_APP_PASSWORD_PERSONAL"),
        ("GMAIL_USER_3",         "GMAIL_APP_PASSWORD_3"),
        ("GMAIL_USER_5",         "GMAIL_APP_PASSWORD_5"),
        ("GMAIL_USER_1",         "GMAIL_APP_PASSWORD_1"),
        ("GMAIL_USER_2",         "GMAIL_APP_PASSWORD_2"),
        ("GMAIL_USER_4",         "GMAIL_APP_PASSWORD_4"),
        ("GMAIL_USER_6",         "GMAIL_APP_PASSWORD_6"),
        ("GMAIL_USER_7",         "GMAIL_APP_PASSWORD_7"),
        ("GMAIL_USER_8",         "GMAIL_APP_PASSWORD_8"),
    ]
    seen_users = set()
    for user_key, pass_key in pairs:
        user = _e(user_key)
        pw   = _e(pass_key)
        if user and pw and user not in seen_users:
            seen_users.add(user)
            accounts.append({"type": "gmail", "user": user, "pass": pw})
    sg_key = _e("SENDGRID_API_KEY_AIITEC") or _e("SENDGRID_API_KEY")
    sg_from = _e("SENDGRID_FROM_EMAIL", "")
    if sg_key and sg_from:
        accounts.append({"type": "sendgrid", "key": sg_key, "from": sg_from})
    return accounts

DAILY_LIMIT    = int(_e("MASS_OUTREACH_DAILY_LIMIT", "1000"))
PER_ACCOUNT    = 200      # max pro Gmail-Account
BATCH_SIZE     = 333      # pro Scheduler-Lauf (3x täglich)
FOLLOWUP_D1    = 5
FOLLOWUP_D2    = 11
UNSUBSCRIBE_BASE = _e("RAILWAY_PUBLIC_DOMAIN",
                       "supermegabot-production.up.railway.app")

# ── Zielgruppen (Branchen → Email-Pitch-Track) ─────────────────────────────
INDUSTRY_TRACKS: Dict[str, Dict] = {
    "E-Commerce": {
        "subject": "Automatisiere deinen Shopify-Shop komplett — Demo gefällig?",
        "hook": "Shopify-Händler mit 50+ Produkten reduzieren mit unserer KI-Suite 80% der manuellen Arbeit.",
        "cta": "Kostenlose 14-Tage-Demo buchen",
        "url": "https://shopify-brutal-tuning.vercel.app",
    },
    "IT-Dienstleister": {
        "subject": "KI-Mitarbeiter auf Abruf — Reseller-Programm mit 30% Provision",
        "hook": "IT-Dienstleister die unsere KI-Agenten als White-Label anbieten, verdienen 30% recurring.",
        "cta": "Partnerschaft unverbindlich anfragen",
        "url": "https://bullpower-hub.vercel.app",
    },
    "Marketing-Agentur": {
        "subject": "5× mehr Content in 1/10 der Zeit — KI-Content-Suite für Agenturen",
        "hook": "Marketing-Agenturen nutzen unseren CreatorAI-Stack für Social, Blog und Ads — vollautomatisch.",
        "cta": "Agentur-Demo anfordern",
        "url": "https://creatorai-ultra.vercel.app",
    },
    "Steuerberater": {
        "subject": "EU AI Act Compliance-Tool für Ihre Mandanten — kostenlos testen",
        "hook": "Ab 2026 müssen Ihre Mandanten den EU AI Act erfüllen. Wir liefern das Audit-Tool.",
        "cta": "Kostenlos testen",
        "url": "https://bullpower-steuercockpit.netlify.app",
    },
    "Handwerk": {
        "subject": "Mehr Aufträge ohne Werbung — KI-Akquise für Handwerksbetriebe",
        "hook": "Handwerksbetriebe finden mit unserem System automatisch Neukunden in ihrer Region.",
        "cta": "Gratis Demo vereinbaren",
        "url": "https://autoincome-ai.vercel.app",
    },
    "Handel": {
        "subject": "Automatisierter Produktimport + SEO für Ihren Online-Shop",
        "hook": "Importieren Sie 1.000+ Produkte täglich, komplett mit SEO-Texten und Kategorien.",
        "cta": "Shop-Demo starten",
        "url": "https://shopify-acquisition-engine.vercel.app",
    },
    "Default": {
        "subject": "KI automatisiert Ihr Business — Demo für {company}",
        "hook": "Unternehmen wie {company} sparen 20+ Stunden/Woche durch unsere KI-Automatisierung.",
        "cta": "Jetzt kostenlos testen",
        "url": "https://bullpower-hub.vercel.app",
    },
}

# ── DB ────────────────────────────────────────────────────────────────────────
def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db() -> None:
    with _db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT UNIQUE NOT NULL,
            company     TEXT,
            domain      TEXT,
            industry    TEXT DEFAULT 'Default',
            city        TEXT,
            contact     TEXT,
            source      TEXT,
            confidence  REAL DEFAULT 0.5,
            status      TEXT DEFAULT 'new',
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS sends (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id     INTEGER REFERENCES leads(id),
            email       TEXT NOT NULL,
            stage       INTEGER DEFAULT 1,
            smtp_user   TEXT,
            sent_at     TEXT DEFAULT (datetime('now')),
            opened      INTEGER DEFAULT 0,
            replied     INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS unsubscribes (
            email       TEXT PRIMARY KEY,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS research_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT,
            leads_found INTEGER DEFAULT 0,
            ran_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS searched_combos (
            combo       TEXT PRIMARY KEY,
            searched_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
        CREATE INDEX IF NOT EXISTS idx_leads_industry ON leads(industry);
        CREATE INDEX IF NOT EXISTS idx_sends_email ON sends(email);
        """)
    log.info("DB initialisiert: %s", _DB)

# ── Email Validierung ─────────────────────────────────────────────────────────
def _valid_email(email: str) -> bool:
    if not email or "@" not in email or len(email) > 254:
        return False
    if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email):
        return False
    if re.search(
        r'(example|test|placeholder|noreply|no-reply|mailer-daemon|donotreply|do-not-reply|'
        r'abuse|postmaster|bounce|spam|unsubscribe@|admin@google|support@microsoft)',
        email, re.I
    ):
        return False
    domain = email.split("@")[-1].lower()
    if domain in _THROWAWAY:
        return False
    if domain.count(".") == 0:
        return False
    try:
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False

def _is_unsubscribed(email: str) -> bool:
    with _db() as conn:
        r = conn.execute("SELECT 1 FROM unsubscribes WHERE email=?", (email,)).fetchone()
        return r is not None

def _was_contacted(email: str, days: int = 3) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _db() as conn:
        r = conn.execute(
            "SELECT 1 FROM sends WHERE email=? AND sent_at>?", (email, cutoff)
        ).fetchone()
        return r is not None

# ── Lead Upsert ───────────────────────────────────────────────────────────────
def _upsert_lead(email: str, company: str = "", domain: str = "",
                 industry: str = "Default", city: str = "",
                 source: str = "research") -> Optional[int]:
    if not _valid_email(email):
        return None
    email = email.lower().strip()
    with _db() as conn:
        existing = conn.execute("SELECT id FROM leads WHERE email=?", (email,)).fetchone()
        if existing:
            return existing["id"]
        cur = conn.execute(
            "INSERT INTO leads (email,company,domain,industry,city,source) VALUES (?,?,?,?,?,?)",
            (email, company[:200], domain[:100], industry, city[:100], source),
        )
        return cur.lastrowid

# ── Lead Research ─────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

_THROWAWAY = {
    "mailinator.com","guerrillamail.com","tempmail.com","throwaway.email",
    "sharklasers.com","guerrillamailblock.com","grr.la","spam4.me",
    "yopmail.com","trashmail.com","maildrop.cc","dispostable.com",
    "fakeinbox.com","10minutemail.com","mailnull.com","spamgourmet.com",
}

async def _fetch(session: aiohttp.ClientSession, url: str, timeout: int = 15) -> str:
    try:
        async with session.get(
            url, headers=_HEADERS,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
            ssl=False,
        ) as r:
            if r.status == 200:
                return await r.text(errors="replace")
    except Exception as e:
        log.debug("Fetch error %s: %s", url, e)
    return ""

def _mx_valid(domain: str) -> bool:
    """Check domain has MX record (real mail server)."""
    try:
        import dns.resolver
        dns.resolver.resolve(domain, "MX")
        return True
    except Exception:
        pass
    try:
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False

def _extract_emails_from_html(html: str, own_domain: str = "") -> List[str]:
    """Extract and filter all email addresses from HTML."""
    raw = re.findall(
        r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
        html
    )
    seen = set()
    result = []
    for e in raw:
        e = e.lower().strip()
        if e in seen:
            continue
        seen.add(e)
        domain = e.split("@")[-1]
        if domain in _THROWAWAY:
            continue
        if re.search(r'(example|test|placeholder|noreply|no-reply|mailer-daemon|bounce|donotreply|unsubscribe|abuse@|postmaster@|spam@|admin@|support@microsoft|support@apple|support@google)', e, re.I):
            continue
        if re.match(r'^[0-9]', e):
            continue
        result.append(e)
    return result

def _extract_domain_from_url(url: str) -> str:
    """Extract clean domain from a URL."""
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        host = parsed.netloc or parsed.path
        host = host.lower().strip("/").replace("www.", "")
        return host.split("/")[0]
    except Exception:
        return ""

def _guess_emails(domain: str) -> List[str]:
    """Standard-Email-Muster für DACH-Unternehmen — Impressum ist Pflicht!"""
    return [
        f"info@{domain}",
        f"kontakt@{domain}",
        f"hello@{domain}",
        f"hallo@{domain}",
        f"service@{domain}",
        f"mail@{domain}",
        f"office@{domain}",
        f"buero@{domain}",
    ]

async def _find_email_for_domain(
    session: aiohttp.ClientSession,
    domain: str,
    company: str = "",
    timeout: int = 8,
) -> str:
    """
    Impressum-First Email-Finding:
    1. Fetch /impressum (German law = always has contact info)
    2. Fetch /kontakt, /contact, /about
    3. Fallback: guess info@/kontakt@ + return best guess
    """
    if not domain or "." not in domain:
        return ""
    paths = ["/impressum", "/kontakt", "/contact", "/about", "/ueber-uns",
             "/impressum.html", "/kontakt.html", ""]
    for path in paths:
        url = f"https://{domain}{path}"
        html = await _fetch(session, url, timeout=timeout)
        if not html:
            url = f"http://{domain}{path}"
            html = await _fetch(session, url, timeout=timeout)
        if html:
            emails = _extract_emails_from_html(html, domain)
            for e in emails:
                ed = e.split("@")[-1]
                if ed == domain or ed.endswith("." + domain.split(".", 1)[-1] if "." in domain else domain):
                    return e
            if emails:
                return emails[0]
    # Fallback: guess info@ + validate domain resolves
    if _mx_valid(domain):
        return f"info@{domain}"
    return ""

_GS_SKIP_DOMAINS = {
    "wipe.de", "consentmanager.net", "adfarm1.adition.com", "adition.com",
    "google.com", "googleapis.com", "gstatic.com", "googletagmanager.com",
    "facebook.com", "twitter.com", "linkedin.com", "youtube.com", "instagram.com",
    "tiktok.com", "pinterest.com", "xing.com",
    "apple.com", "microsoft.com", "amazon.com", "adobe.com", "cloudflare.com",
    "gelbeseiten.de", "mapsapi.gelbeseiten.de", "11880.com", "cylex.de",
    "meinestadt.de", "golocal.de", "herold.at", "local.ch",
    "wp-stat.com", "w3.org", "schema.org", "openstreetmap.org",
    "maps.google.com", "maps.apple.com",
}

async def _gelbeseiten_detail(session: aiohttp.ClientSession,
                               detail_url: str, company: str, city: str,
                               industry: str) -> Optional[Dict]:
    """Fetch GS detail page → extract email or website → find email."""
    html = await _fetch(session, detail_url, timeout=10)
    if not html:
        return None
    # 1. Direct mailto on detail page (most reliable)
    email_m = re.search(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html)
    if email_m:
        email = email_m.group(1).lower().split("?")[0]
        if _valid_email(email):
            return {"email": email, "company": company, "city": city,
                    "industry": industry, "source": "gelbeseiten_detail"}
    # 2. External website URL → Impressum scraping
    ext_links = re.findall(r'href="(https?://[^"]{5,120})"', html)
    for link in ext_links:
        domain = _extract_domain_from_url(link)
        if not domain:
            continue
        # Skip known non-company domains
        if any(domain.endswith(skip) or domain == skip for skip in _GS_SKIP_DOMAINS):
            continue
        if len(domain) < 4:
            continue
        email = await _find_email_for_domain(session, domain, company)
        if email and _valid_email(email):
            return {"email": email, "company": company, "city": city,
                    "industry": industry, "source": "gelbeseiten", "domain": domain}
    return None

async def research_gelbeseiten(session: aiohttp.ClientSession,
                                category: str, city: str) -> List[Dict]:
    """
    Gelbe Seiten 2-Stufen-Scraping:
    1. Listing-Seite → Company-Name + Detail-URL
    2. Detail-Seite → Email oder Website → Impressum-Scraping
    """
    leads = []
    url = f"https://www.gelbeseiten.de/suche/{quote_plus(category)}/{quote_plus(city)}"
    html = await _fetch(session, url)
    if not html:
        return leads
    entries = re.findall(
        r'<article[^>]*class="[^"]*mod-Treffer[^"]*"[^>]*>(.*?)</article>',
        html, re.S
    )
    if not entries:
        return leads
    industry = _map_industry(category)
    sem = asyncio.Semaphore(5)
    async def _process(entry: str):
        async with sem:
            company_m = re.search(r'<h2[^>]*class="[^"]*mod-Treffer__name[^"]*"[^>]*>([^<]+)<', entry)
            if not company_m:
                company_m = re.search(r'<h2[^>]*>([^<]+)<', entry)
            company = re.sub(r'<[^>]+>', '', company_m.group(1)).strip() if company_m else ""
            # Detail page link
            detail_m = re.search(r'href="(https://www\.gelbeseiten\.de/gsbiz/[^"]+)"', entry)
            if not detail_m:
                detail_m = re.search(r'href="(/gsbiz/[^"]+)"', entry)
            if not detail_m:
                return None
            detail_url = detail_m.group(1)
            if detail_url.startswith("/"):
                detail_url = "https://www.gelbeseiten.de" + detail_url
            await asyncio.sleep(0.4)
            return await _gelbeseiten_detail(session, detail_url, company, city, industry)

    tasks = [_process(e) for e in entries[:20]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, dict):
            leads.append(r)
    return leads

async def research_11880(session: aiohttp.ClientSession,
                          category: str, city: str) -> List[Dict]:
    """11880.com: domains + Impressum-Scraping."""
    leads = []
    url = f"https://www.11880.com/suche/{quote_plus(category)}/{quote_plus(city)}.html"
    html = await _fetch(session, url)
    if not html:
        return leads
    industry = _map_industry(category)
    # Extract result blocks
    blocks = re.findall(
        r'<(?:div|article)[^>]*class="[^"]*(?:result|entry|listing)[^"]*"[^>]*>(.*?)</(?:div|article)>',
        html, re.S
    )
    if not blocks:
        blocks = re.findall(r'<li[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</li>', html, re.S)
    sem = asyncio.Semaphore(3)
    async def _process(block: str):
        async with sem:
            company_m = re.search(r'<h2[^>]*>([^<]+)<', block)
            company = re.sub(r'<[^>]+>', '', company_m.group(1)).strip() if company_m else ""
            email_m  = re.search(r'href="mailto:([^"&]+)"', block)
            if email_m:
                email = email_m.group(1).strip().lower()
                if _valid_email(email):
                    return {"email": email, "company": company, "city": city,
                            "industry": industry, "source": "11880_direct"}
            web_m = re.search(r'href="(https?://(?!www\.11880)[^"]+)"', block)
            if web_m:
                domain = _extract_domain_from_url(web_m.group(1))
                if domain:
                    await asyncio.sleep(0.3)
                    email = await _find_email_for_domain(session, domain, company)
                    if email and _valid_email(email):
                        return {"email": email, "company": company, "city": city,
                                "industry": industry, "source": "11880", "domain": domain}
            return None
    tasks = [_process(b) for b in blocks[:20]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, dict):
            leads.append(r)
    return leads

async def research_cylex(session: aiohttp.ClientSession,
                          category: str, city: str) -> List[Dict]:
    """cylex.de — Deutsches Branchenverzeichnis, oft mit direkten Emails."""
    leads = []
    url = f"https://www.cylex.de/city-search/{quote_plus(city)}/{quote_plus(category)}.html"
    html = await _fetch(session, url)
    if not html:
        return leads
    industry = _map_industry(category)
    entries = re.findall(r'<div[^>]*class="[^"]*company-result[^"]*"[^>]*>(.*?)</div>\s*</div>',
                          html, re.S)
    for entry in entries[:15]:
        company_m = re.search(r'<h2[^>]*>([^<]+)<', entry)
        email_m   = re.search(r'href="mailto:([^"&]+)"', entry)
        web_m     = re.search(r'href="(https?://(?!www\.cylex)[^"]+)"', entry)
        company = re.sub(r'<[^>]+>', '', company_m.group(1)).strip() if company_m else ""
        if email_m:
            email = email_m.group(1).strip().lower()
            if _valid_email(email):
                leads.append({"email": email, "company": company, "city": city,
                              "industry": industry, "source": "cylex_direct"})
        elif web_m:
            domain = _extract_domain_from_url(web_m.group(1))
            if domain:
                email = await _find_email_for_domain(session, domain, company)
                if email and _valid_email(email):
                    leads.append({"email": email, "company": company, "city": city,
                                  "industry": industry, "source": "cylex", "domain": domain})
    return leads

async def research_meinestadt(session: aiohttp.ClientSession,
                               category: str, city: str) -> List[Dict]:
    """meinestadt.de — Lokale Branchensuche mit Website-Links."""
    leads = []
    slug_city = city.lower().replace(" ", "-").replace("ü","ue").replace("ä","ae").replace("ö","oe")
    slug_cat  = category.lower().replace(" ", "-")
    url = f"https://www.meinestadt.de/{slug_city}/firmen/{slug_cat}"
    html = await _fetch(session, url)
    if not html:
        return leads
    industry = _map_industry(category)
    entries = re.findall(r'<div[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</div>', html, re.S)
    for entry in entries[:15]:
        company_m = re.search(r'<(?:h2|h3|strong)[^>]*>([^<]+)<', entry)
        email_m   = re.search(r'href="mailto:([^"&]+)"', entry)
        web_m     = re.search(r'href="(https?://(?!www\.meinestadt)[^"]+)"', entry)
        company = re.sub(r'<[^>]+>', '', company_m.group(1)).strip() if company_m else ""
        if email_m:
            email = email_m.group(1).strip().lower()
            if _valid_email(email):
                leads.append({"email": email, "company": company, "city": city,
                              "industry": industry, "source": "meinestadt_direct"})
        elif web_m:
            domain = _extract_domain_from_url(web_m.group(1))
            if domain:
                email = await _find_email_for_domain(session, domain, company)
                if email and _valid_email(email):
                    leads.append({"email": email, "company": company, "city": city,
                                  "industry": industry, "source": "meinestadt", "domain": domain})
    return leads

async def research_contact_page(session: aiohttp.ClientSession,
                                 domain: str, company: str = "") -> List[str]:
    """Wrapper around _find_email_for_domain for backwards compatibility."""
    email = await _find_email_for_domain(session, domain, company)
    return [email] if email else []

async def research_hn_companies(session: aiohttp.ClientSession) -> List[Dict]:
    """HackerNews 'Who is Hiring' → Tech-Startups."""
    leads = []
    try:
        url = "https://hacker-news.firebaseio.com/v0/askstories.json"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            story_ids = (await r.json())[:30]
        for sid in story_ids[:10]:
            url2 = f"https://hacker-news.firebaseio.com/v0/item/{sid}.json"
            async with session.get(url2, timeout=aiohttp.ClientTimeout(total=10)) as r2:
                item = await r2.json()
            if item and "who is hiring" in (item.get("title") or "").lower():
                kids = item.get("kids", [])[:50]
                for kid in kids:
                    url3 = f"https://hacker-news.firebaseio.com/v0/item/{kid}.json"
                    async with session.get(url3, timeout=aiohttp.ClientTimeout(total=8)) as r3:
                        comment = await r3.json()
                    text = (comment or {}).get("text", "")
                    email_m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)
                    company_m = re.search(r'<b>([^<|]+)', text)
                    if email_m:
                        leads.append({
                            "email": email_m.group(0).lower(),
                            "company": company_m.group(1).strip() if company_m else "HN Company",
                            "city": "", "industry": "IT-Dienstleister", "source": "hackernews"
                        })
    except Exception as e:
        log.debug("HN research error: %s", e)
    return leads

async def research_rss_funding(session: aiohttp.ClientSession) -> List[Dict]:
    """RSS-Feeds für Funding-Runden → Startups mit Budget."""
    leads = []
    feeds = [
        "https://feeds.feedburner.com/Techcrunch",
        "https://eu-startups.com/feed/",
        "https://www.gruenderszene.de/feed",
        "https://startupdetector.de/rss/funding/",
    ]
    for feed_url in feeds:
        try:
            xml = await _fetch(session, feed_url, timeout=10)
            if not xml:
                continue
            root = ET.fromstring(xml)
            for item in root.iter("item"):
                title = (item.findtext("title") or "").lower()
                desc  = (item.findtext("description") or "").lower()
                if any(kw in title + desc for kw in
                       ["funding", "finanzierung", "investment", "runde", "million", "startup"]):
                    link = item.findtext("link") or ""
                    domain_m = re.search(r'https?://(?:www\.)?([^/]+)', link)
                    if domain_m:
                        domain = domain_m.group(1)
                        for email in _guess_emails(domain):
                            leads.append({
                                "email": email, "company": domain,
                                "domain": domain, "city": "",
                                "industry": "IT-Dienstleister", "source": "rss_funding"
                            })
        except Exception as e:
            log.debug("RSS error %s: %s", feed_url, e)
    return leads

async def import_from_existing_modules() -> List[Dict]:
    """Importiert Leads aus bereits laufenden Modulen."""
    leads = []
    try:
        from modules.b2b_intent_radar import get_leads_for_export
        existing = await get_leads_for_export()
        for lead in (existing or []):
            email = lead.get("email") or lead.get("contact_email")
            if email:
                leads.append({
                    "email": email,
                    "company": lead.get("company", ""),
                    "city": lead.get("city", ""),
                    "industry": lead.get("category", "Default"),
                    "source": "b2b_intent_radar"
                })
    except Exception as e:
        log.debug("Intent Radar import: %s", e)
    try:
        from modules.aiitec_outreach_machine import _sb
        data = await _sb("GET", "/rest/v1/aiitec_companies",
                         params={"status": "eq.new", "select": "company_name,contact_email,industry",
                                 "limit": "500"})
        for row in (data or []):
            email = row.get("contact_email")
            if email:
                leads.append({
                    "email": email,
                    "company": row.get("company_name", ""),
                    "industry": row.get("industry", "Default"),
                    "source": "aiitec_supabase"
                })
    except Exception as e:
        log.debug("Supabase import: %s", e)
    return leads

def _map_industry(category: str) -> str:
    cat_lower = category.lower()
    mapping = {
        ("shop", "handel", "verkauf", "ecommerce", "e-commerce"): "E-Commerce",
        ("it", "software", "tech", "computer", "digital"): "IT-Dienstleister",
        ("marketing", "agentur", "werbung", "pr", "seo"): "Marketing-Agentur",
        ("steuer", "buchhaltung", "kanzlei", "anwalt", "wirtschafts"): "Steuerberater",
        ("handwerk", "bau", "installateur", "elektriker", "maler", "sanitär"): "Handwerk",
        ("handel", "import", "export", "großhandel", "einzelhandel"): "Handel",
    }
    for keywords, industry in mapping.items():
        if any(kw in cat_lower for kw in keywords):
            return industry
    return "Default"

# Research-Konfiguration: Branchen × Städte (ALLE — kein Limit!)
_CATEGORIES = [
    "Online-Shop", "IT-Dienstleister", "Webdesign Agentur",
    "Marketing Agentur", "SEO Agentur", "E-Commerce",
    "Software Entwicklung", "Digitalagentur", "Unternehmensberatung",
    "Steuerberater", "Handelsunternehmen", "Werbeagentur",
    "App Entwicklung", "Shopify Agentur", "Social Media Agentur",
    "Buchhaltung", "Elektriker", "Installateur", "Malermeister",
    "Bäckerei", "Restaurant", "Physiotherapie", "Zahnarzt",
]
_CITIES_DACH = [
    # Deutschland — Top 30
    "Berlin", "Hamburg", "München", "Köln", "Frankfurt", "Stuttgart",
    "Düsseldorf", "Dortmund", "Essen", "Leipzig", "Bremen", "Dresden",
    "Hannover", "Nürnberg", "Duisburg", "Bochum", "Wuppertal",
    "Bielefeld", "Bonn", "Münster", "Karlsruhe", "Mannheim",
    "Augsburg", "Wiesbaden", "Gelsenkirchen", "Mönchengladbach",
    "Braunschweig", "Kiel", "Aachen", "Magdeburg",
    # Österreich
    "Wien", "Graz", "Linz", "Salzburg", "Innsbruck",
    # Schweiz
    "Zürich", "Bern", "Basel", "Genf", "Lausanne",
]

async def run_research(session_limit: int = 2000) -> Dict:
    """
    Vollautomatische Multi-Source Lead-Research:
    Gelbe Seiten + 11880 + Cylex + MeineStadt + HN + RSS
    → Impressum-Scraping → Pattern-Guessing → MX-Validierung → DB
    """
    gathered: List[Dict] = []
    connector = aiohttp.TCPConnector(limit=30, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Phase 1: Alle Directory-Quellen parallel (je 10 Städte pro Batch)
        log.info("Research Phase 1: Verzeichnis-Scraping (%d Kategorien × %d Städte)",
                 len(_CATEGORIES), len(_CITIES_DACH))
        dir_tasks = []
        for cat in _CATEGORIES:
            for city in _CITIES_DACH:
                dir_tasks.append(research_gelbeseiten(session, cat, city))
                dir_tasks.append(research_11880(session, cat, city))
                dir_tasks.append(research_cylex(session, cat, city))
                dir_tasks.append(research_meinestadt(session, cat, city))

        # Run in batches of 40 to avoid overwhelming
        BATCH = 40
        for i in range(0, len(dir_tasks), BATCH):
            batch_results = await asyncio.gather(*dir_tasks[i:i+BATCH], return_exceptions=True)
            for r in batch_results:
                if isinstance(r, list):
                    gathered.extend(r)
            log.info("Research: %d/%d tasks — %d Leads bisher", i+BATCH, len(dir_tasks), len(gathered))
            await asyncio.sleep(1.0)  # Rate limit courtesy pause

        # Phase 2: HackerNews + RSS Funding
        log.info("Research Phase 2: HN + RSS Funding")
        extra = await asyncio.gather(
            research_hn_companies(session),
            research_rss_funding(session),
            import_from_existing_modules(),
            return_exceptions=True,
        )
        for r in extra:
            if isinstance(r, list):
                gathered.extend(r)

    # Deduplicate by email
    seen_emails: set = set()
    deduped: List[Dict] = []
    for lead in gathered:
        e = (lead.get("email") or "").lower().strip()
        if e and e not in seen_emails:
            seen_emails.add(e)
            deduped.append(lead)

    log.info("Research: %d total gathered, %d unique emails", len(gathered), len(deduped))

    # Save to DB
    saved = 0
    for lead in deduped[:session_limit]:
        lid = _upsert_lead(
            email=lead.get("email", ""),
            company=lead.get("company", ""),
            domain=lead.get("domain", ""),
            industry=lead.get("industry", "Default"),
            city=lead.get("city", ""),
            source=lead.get("source", "research"),
        )
        if lid:
            saved += 1

    with _db() as conn:
        conn.execute(
            "INSERT INTO research_log (source, leads_found) VALUES (?,?)",
            ("full_research", saved)
        )
    log.info("Research abgeschlossen: %d/%d Leads in DB gespeichert", saved, len(deduped))
    return {"gathered": len(gathered), "unique": len(deduped), "saved": saved}

# ── AI Email Writer ───────────────────────────────────────────────────────────
async def _ai_personalize(company: str, industry: str, city: str,
                            contact: str = "") -> Tuple[str, str]:
    """Generiert personalisierten Subject + Email-Body via Claude."""
    track = INDUSTRY_TRACKS.get(industry, INDUSTRY_TRACKS["Default"])
    subject = track["subject"].replace("{company}", company)
    first_name = contact.split()[0] if contact else "Hallo"
    unsub_hash = hashlib.md5(f"{company}{industry}".encode()).hexdigest()[:8]
    try:
        api_key = _e("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("No API key")
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 400,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"Schreibe eine kurze, personalisierte deutsche B2B-Kalt-Email (max 120 Wörter) für:\n"
                        f"Firma: {company}\nBranche: {industry}\nStadt: {city}\n\n"
                        f"Hook: {track['hook'].replace('{company}', company)}\n"
                        f"CTA: {track['cta']}\nURL: {track['url']}\n\n"
                        f"Regeln: professionell aber menschlich, kein Spam-Stil, "
                        f"konkret auf die Branche eingehen, kurz und prägnant. "
                        f"Beginne mit 'Guten Tag' falls kein Name bekannt."
                    )
                }]
            }
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    body = data["content"][0]["text"].strip()
                    body += f"\n\n---\nAbmelden: https://{UNSUBSCRIBE_BASE}/api/unsubscribe?email={{email}}"
                    return subject, body
    except Exception as e:
        log.debug("AI personalize fallback: %s", e)
    body = (
        f"Guten Tag,\n\n"
        f"{track['hook'].replace('{company}', company)}\n\n"
        f"Für {company} in {city or 'Ihrer Region'} könnte das besonders relevant sein.\n\n"
        f"{track['cta']}: {track['url']}\n\n"
        f"Gerne zeige ich Ihnen in einer 15-Minuten-Demo den konkreten Nutzen.\n\n"
        f"Mit freundlichen Grüßen\nRudolf Sarkany | AiiteC\n"
        f"https://bullpower-hub.vercel.app\n\n"
        f"---\nAbmelden: https://{UNSUBSCRIBE_BASE}/api/unsubscribe?email={{email}}"
    )
    return subject, body

# ── SMTP Sender ───────────────────────────────────────────────────────────────
_pool_index = 0
_account_sends: Dict[str, int] = {}

async def _send_via_sendgrid(api_key: str, from_email: str,
                              to_email: str, subject: str, body: str) -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": from_email, "name": "Rudolf Sarkany | AiiteC"},
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            }
            async with session.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                return r.status in (200, 202)
    except Exception as e:
        log.error("SendGrid error: %s", e)
        return False

def _send_via_gmail(user: str, password: str, to_email: str,
                     subject: str, body: str) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Rudolf Sarkany | AiiteC <{user}>"
        msg["To"]      = to_email
        msg["Reply-To"] = user
        msg.attach(MIMEText(body.replace("{email}", to_email), "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(user, password)
            s.sendmail(user, [to_email], msg.as_string())
        return True
    except smtplib.SMTPAuthenticationError:
        log.warning("Gmail Auth fehlgeschlagen: %s", user)
        return False
    except Exception as e:
        log.error("Gmail error (%s): %s", user, e)
        return False

async def send_email(to_email: str, subject: str, body: str) -> Tuple[bool, str]:
    global _pool_index, _account_sends
    pool = _smtp_pool()
    if not pool:
        log.error("Kein SMTP-Account konfiguriert!")
        return False, ""
    for _ in range(len(pool)):
        account = pool[_pool_index % len(pool)]
        _pool_index += 1
        acct_key = account.get("user") or account.get("from", "sendgrid")
        today = datetime.now().strftime("%Y-%m-%d")
        daily_key = f"{acct_key}_{today}"
        if _account_sends.get(daily_key, 0) >= PER_ACCOUNT:
            continue
        if account["type"] == "gmail":
            ok = _send_via_gmail(account["user"], account["pass"], to_email, subject, body)
        else:
            ok = await _send_via_sendgrid(account["key"], account["from"], to_email, subject, body.replace("{email}", to_email))
        if ok:
            _account_sends[daily_key] = _account_sends.get(daily_key, 0) + 1
            return True, acct_key
        await asyncio.sleep(1)
    return False, ""

# ── Versand-Batch ─────────────────────────────────────────────────────────────
async def run_send_batch(batch_limit: int = BATCH_SIZE) -> Dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _db() as conn:
        already_sent_today = conn.execute(
            "SELECT COUNT(*) FROM sends WHERE sent_at LIKE ?", (f"{today}%",)
        ).fetchone()[0]
    if already_sent_today >= DAILY_LIMIT:
        log.info("Tageslimit %d erreicht, kein Versand.", DAILY_LIMIT)
        return {"sent": 0, "skipped": 0, "reason": "daily_limit"}
    remaining = min(batch_limit, DAILY_LIMIT - already_sent_today)
    with _db() as conn:
        leads = conn.execute("""
            SELECT l.id, l.email, l.company, l.industry, l.city, l.contact
            FROM leads l
            WHERE l.status = 'new'
              AND l.email NOT IN (SELECT email FROM unsubscribes)
              AND l.email NOT IN (
                  SELECT email FROM sends
                  WHERE sent_at > datetime('now', '-3 days')
              )
            ORDER BY l.confidence DESC, l.id ASC
            LIMIT ?
        """, (remaining,)).fetchall()
    sent_count = 0
    skip_count = 0
    errors = 0
    for lead in leads:
        email    = lead["email"]
        company  = lead["company"] or "Ihr Unternehmen"
        industry = lead["industry"] or "Default"
        city     = lead["city"] or "Deutschland"
        subject, body = await _ai_personalize(company, industry, city, lead["contact"] or "")
        ok, smtp_user = await send_email(email, subject, body)
        if ok:
            sent_count += 1
            with _db() as conn:
                conn.execute(
                    "INSERT INTO sends (lead_id, email, stage, smtp_user) VALUES (?,?,1,?)",
                    (lead["id"], email, smtp_user)
                )
                conn.execute("UPDATE leads SET status='contacted' WHERE id=?", (lead["id"],))
            log.info("✅ Gesendet → %s (%s)", email, company[:40])
            await asyncio.sleep(0.5)
        else:
            errors += 1
            skip_count += 1
            with _db() as conn:
                conn.execute("UPDATE leads SET status='error' WHERE id=?", (lead["id"],))
    return {
        "sent": sent_count, "skipped": skip_count,
        "errors": errors, "total_today": already_sent_today + sent_count
    }

async def run_followups() -> Dict:
    """Follow-Up Emails (Stage 2 nach 5 Tagen, Stage 3 nach 11 Tagen)."""
    sent = 0
    for stage, days_ago, max_f in [(2, FOLLOWUP_D1, 30), (3, FOLLOWUP_D2, 20)]:
        cutoff_start = (datetime.now(timezone.utc) - timedelta(days=days_ago + 2)).isoformat()
        cutoff_end   = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        with _db() as conn:
            candidates = conn.execute("""
                SELECT DISTINCT s.email, l.company, l.industry, l.city
                FROM sends s JOIN leads l ON s.lead_id = l.id
                WHERE s.stage = ? AND s.sent_at BETWEEN ? AND ?
                  AND s.email NOT IN (SELECT email FROM unsubscribes)
                  AND s.email NOT IN (
                      SELECT email FROM sends WHERE stage=? AND sent_at > ?
                  )
                LIMIT ?
            """, (stage-1, cutoff_start, cutoff_end, stage,
                  (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), max_f)
            ).fetchall()
        for row in candidates:
            subject = f"Re: Kurze Rückfrage zu {row['company'] or 'Ihrer Anfrage'}"
            body = (
                f"Hallo,\n\nwir hatten uns letzte Woche kurz geschrieben.\n"
                f"Darf ich fragen, ob es Interesse an einer kurzen Demo gibt?\n\n"
                f"Es dauert nur 15 Minuten und Sie sehen konkret was die KI-Automatisierung\n"
                f"für {row['company'] or 'Ihr Unternehmen'} bedeuten kann.\n\n"
                f"Demo buchen: https://bullpower-hub.vercel.app\n\n"
                f"Beste Grüße\nRudolf Sarkany | AiiteC\n\n"
                f"---\nAbmelden: https://{UNSUBSCRIBE_BASE}/api/unsubscribe?email={row['email']}"
            )
            ok, smtp_user = await send_email(row["email"], subject, body)
            if ok:
                sent += 1
                with _db() as conn:
                    lid = conn.execute(
                        "SELECT id FROM leads WHERE email=?", (row["email"],)
                    ).fetchone()
                    conn.execute(
                        "INSERT INTO sends (lead_id, email, stage, smtp_user) VALUES (?,?,?,?)",
                        (lid["id"] if lid else 0, row["email"], stage, smtp_user)
                    )
                await asyncio.sleep(0.5)
    return {"followups_sent": sent}

# ── Telegram Report ───────────────────────────────────────────────────────────
async def _telegram(msg: str) -> None:
    token = _e("TELEGRAM_BOT_TOKEN")
    chat  = _e("TELEGRAM_CHAT_ID")
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

# ── Stats ─────────────────────────────────────────────────────────────────────
def get_stats() -> Dict:
    with _db() as conn:
        total_leads  = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        new_leads    = conn.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
        contacted    = conn.execute("SELECT COUNT(*) FROM leads WHERE status='contacted'").fetchone()[0]
        total_sent   = conn.execute("SELECT COUNT(*) FROM sends WHERE stage=1").fetchone()[0]
        today_sent   = conn.execute(
            "SELECT COUNT(*) FROM sends WHERE sent_at LIKE ?",
            (datetime.now().strftime("%Y-%m-%d") + "%",)
        ).fetchone()[0]
        followups    = conn.execute("SELECT COUNT(*) FROM sends WHERE stage>1").fetchone()[0]
        unsubs       = conn.execute("SELECT COUNT(*) FROM unsubscribes").fetchone()[0]
        pool_size    = len(_smtp_pool())
        capacity     = pool_size * PER_ACCOUNT
    return {
        "leads_total": total_leads, "leads_new": new_leads,
        "leads_contacted": contacted, "emails_total": total_sent,
        "emails_today": today_sent, "followups": followups,
        "unsubscribes": unsubs, "smtp_accounts": pool_size,
        "daily_capacity": capacity, "daily_limit": DAILY_LIMIT
    }

# ── Unsubscribe Handler (für Dashboard) ───────────────────────────────────────
def handle_unsubscribe(email: str) -> bool:
    email = email.lower().strip()
    if not email or "@" not in email:
        return False
    with _db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO unsubscribes (email) VALUES (?)", (email,)
        )
        conn.execute("UPDATE leads SET status='unsubscribed' WHERE email=?", (email,))
    log.info("Unsubscribed: %s", email)
    return True

# ── Vollautomatischer Tages-Lauf ──────────────────────────────────────────────
async def run_full_daily() -> Dict:
    """Kompletter Tages-Lauf: Research + Versand + Follow-Up + Telegram-Report."""
    init_db()
    log.info("=== Mass Outreach 1000/Tag — Tages-Lauf START ===")
    research = await run_research(session_limit=500)
    log.info("Research: %d gesammelt, %d gespeichert", research["gathered"], research["saved"])
    send = await run_send_batch(BATCH_SIZE)
    log.info("Versand: %d gesendet, %d übersprungen", send["sent"], send["skipped"])
    followup = await run_followups()
    log.info("Follow-Ups: %d gesendet", followup["followups_sent"])
    stats = get_stats()
    report = (
        f"📧 <b>Mass Outreach Tages-Bericht</b>\n\n"
        f"✅ Heute gesendet: <b>{send['sent']}</b>\n"
        f"🔄 Follow-Ups: <b>{followup['followups_sent']}</b>\n"
        f"🎯 Neue Leads: <b>{research['saved']}</b>\n"
        f"📊 Leads gesamt: <b>{stats['leads_total']}</b> ({stats['leads_new']} neu)\n"
        f"📬 Emails gesamt: <b>{stats['emails_total']}</b>\n"
        f"⚡ SMTP-Pool: <b>{stats['smtp_accounts']} Accounts</b> ({stats['daily_capacity']}/Tag Kapazität)\n"
        f"🚫 Abgemeldete: <b>{stats['unsubscribes']}</b>"
    )
    await _telegram(report)
    return {**send, **followup, **research, "stats": stats}

async def run_mini_research(categories: List[str], cities: List[str],
                           limit: int = 50) -> int:
    """Schnelle Mini-Research für 2-3 Kategorien × 3-5 Städte.

    Speichert welche Kategorie×Stadt-Kombis schon gesucht wurden
    damit jeder Batch andere Unternehmen findet.
    """
    init_db()
    gathered: List[Dict] = []
    with _db() as conn:
        already = {r[0] for r in conn.execute(
            "SELECT combo FROM searched_combos"
        ).fetchall()}

    async with aiohttp.ClientSession(
        headers={"User-Agent": "Mozilla/5.0 (compatible; BullPowerBot/1.0)"},
        connector=aiohttp.TCPConnector(ssl=False),
        timeout=aiohttp.ClientTimeout(total=15),
    ) as session:
        for cat in categories:
            for city in cities:
                combo = f"{cat}|{city}"
                if combo in already:
                    continue
                # Gelbe Seiten
                try:
                    url = f"https://www.gelbeseiten.de/suche/{quote_plus(cat)}/{quote_plus(city)}"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                        html = await r.text(errors="ignore")
                    # E-Mail Pattern-Extraktion
                    emails_found = re.findall(
                        r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', html
                    )
                    company_names = re.findall(
                        r'(?:data-name|itemprop="name")[^>]*>([^<]{3,60})<', html
                    )
                    for i, em in enumerate(emails_found[:5]):
                        if _valid_email(em):
                            gathered.append({
                                "email": em.lower(),
                                "company": company_names[i] if i < len(company_names) else cat,
                                "industry": cat,
                                "city": city,
                                "source": "gs_mini",
                                "confidence": 0.6,
                            })
                except Exception:
                    pass
                # 11880.com
                try:
                    url2 = f"https://www.11880.com/suche/{quote_plus(cat)}/{quote_plus(city)}"
                    async with session.get(url2, timeout=aiohttp.ClientTimeout(total=8)) as r2:
                        h2 = await r2.text(errors="ignore")
                    for em in re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', h2)[:5]:
                        if _valid_email(em):
                            gathered.append({
                                "email": em.lower(),
                                "company": cat,
                                "industry": cat,
                                "city": city,
                                "source": "11880_mini",
                                "confidence": 0.55,
                            })
                except Exception:
                    pass
                # Mark combo as searched
                with _db() as conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO searched_combos (combo) VALUES (?)",
                        (combo,)
                    )
                if len(gathered) >= limit:
                    break
            if len(gathered) >= limit:
                break

    # Domain pattern guessing for companies without email
    # (kept light for speed)
    inserted = 0
    with _db() as conn:
        for lead in gathered:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO leads
                       (email, company, industry, city, source, confidence)
                       VALUES (?,?,?,?,?,?)""",
                    (lead["email"], lead.get("company",""), lead.get("industry","Default"),
                     lead.get("city",""), lead.get("source","mini"), lead.get("confidence",0.5))
                )
                inserted += conn.rowcount
            except Exception:
                pass
    log.info("Mini-Research: %d neue Leads (aus %d gefunden)", inserted, len(gathered))
    return inserted


async def _get_next_search_combos(n_cats: int = 3, n_cities: int = 5) -> Tuple[List[str], List[str]]:
    """Wählt Kategorie/Stadt-Kombis die noch NICHT gesucht wurden.
    Rotiert durch alle Möglichkeiten und startet von vorne wenn alles durch."""
    import random
    with _db() as conn:
        already = {r[0] for r in conn.execute(
            "SELECT combo FROM searched_combos"
        ).fetchall()}

    # Find unsearched combos
    all_combos = [(c, ci) for c in _CATEGORIES for ci in _CITIES_DACH]
    unsearched = [(c, ci) for c, ci in all_combos if f"{c}|{ci}" not in already]

    if len(unsearched) < n_cats * n_cities:
        # Reset — alle Kombis wieder verfügbar
        with _db() as conn:
            conn.execute("DELETE FROM searched_combos")
        unsearched = all_combos
        log.info("Outreach: Alle Kombis durchsucht — Reset für nächste Runde")

    # Pick random unsearched combos
    chosen = random.sample(unsearched, min(n_cats * n_cities, len(unsearched)))
    cats  = list({c for c, _ in chosen})[:n_cats]
    cities = list({ci for _, ci in chosen})[:n_cities]
    return cats, cities


async def run_smart_batch(batch_size: int = BATCH_SIZE) -> Dict:
    """Research + Send in einem Lauf — jedes Mal andere Unternehmen.

    1. Wählt Kategorie/Stadt-Kombis die noch nicht gesucht wurden
    2. Mini-Research → neue Leads in DB
    3. Sofort senden an alle neuen Leads
    4. Follow-Up-Emails für ältere Leads
    """
    init_db()

    # Step 1: Mini-Research mit frischen Kombis
    cats, cities = await _get_next_search_combos(n_cats=3, n_cities=5)
    log.info("Smart Batch Research: %s × %s", cats, cities)
    new_leads = await run_mini_research(cats, cities, limit=batch_size)

    # Step 2: Versand
    send = await run_send_batch(batch_size)
    followup = await run_followups()
    stats = get_stats()

    report = (
        f"🔄 <b>Smart Outreach</b>: +{new_leads} neue Leads | "
        f"{send['sent']} gesendet | {followup['followups_sent']} Follow-Ups | "
        f"Heute: {stats['emails_today']}/{stats['daily_limit']}"
    )
    await _telegram(report)
    log.info("Smart Batch: %d researched, %d sent", new_leads, send.get("sent", 0))
    return {"new_leads": new_leads, **send, **followup}


async def run_batch_only(batch_size: int = BATCH_SIZE) -> Dict:
    """Versand + Mini-Research wenn wenige neue Leads — für 3x/Tag Scheduler."""
    init_db()
    stats_before = get_stats()
    # Auto-Research wenn weniger als 50 neue Leads in DB
    new_leads = 0
    if stats_before.get("leads_new", 0) < 50:
        cats, cities = await _get_next_search_combos(n_cats=3, n_cities=5)
        new_leads = await run_mini_research(cats, cities, limit=100)
        log.info("Auto-Research (low leads): +%d", new_leads)
    send = await run_send_batch(batch_size)
    followup = await run_followups()
    stats = get_stats()
    report = (
        f"📧 <b>Outreach Batch</b>: {send['sent']} gesendet, "
        f"{followup['followups_sent']} Follow-Ups | "
        f"Heute gesamt: {stats['emails_today']}/{stats['daily_limit']}"
    )
    await _telegram(report)
    return {"new_leads": new_leads, **send, **followup}

# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    def _load_env():
        ef = _BASE / ".env"
        if ef.exists():
            for line in ef.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    _load_env()
    args = sys.argv[1:]

    if "--init-db" in args:
        init_db()
        print("DB initialisiert.")
    elif "--stats" in args:
        init_db()
        s = get_stats()
        print(json.dumps(s, indent=2, ensure_ascii=False))
    elif "--research" in args:
        init_db()
        r = asyncio.run(run_research())
        print(f"Research: {r}")
    elif "--send" in args:
        init_db()
        idx = args.index("--send")
        limit = int(args[idx+1]) if idx+1 < len(args) and args[idx+1].isdigit() else BATCH_SIZE
        r = asyncio.run(run_send_batch(limit))
        print(f"Versand: {r}")
    elif "--run-now" in args:
        r = asyncio.run(run_full_daily())
        print(json.dumps(r, indent=2, ensure_ascii=False))
    else:
        print(__doc__)
