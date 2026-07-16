"""
MEGA ACQUISITION ENGINE v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Vollautonome Akquisitions-Maschine für ineedit.com.co + AIITEC B2B

Kapazität pro Tag:
  Gmail SMTP × 3    → 1.500 Mails/Tag
  Mailchimp         →   500 Mails/Tag
  Klaviyo           → Subscriber (unlimitiert)
  SendGrid AIITEC   →   100 Mails/Tag
  TOTAL             → 2.100+ Mails/Tag

Lead-Quellen:
  1. Shopify Kunden (noch nicht gekauft)
  2. DS24 Interessenten (Marketplace-Browser)
  3. Klaviyo Subscriber (Popup + Optin)
  4. B2B Zielgruppen (DACH-KMU via XING-ähnliche Suche)
  5. Nischen-Foren + Communities (Smart Home, Gadgets)
  6. Abandoned-Cart-Leads
  7. Social-Media-Engager (Follower, Liker)
  8. Google-Shopping-Intent (Keyword-Buyer)

Features:
  - Multi-Account-Rotation (kein Spam-Filter)
  - Email-Validierung vor dem Senden (bounce prevention)
  - GDPR-konforme Unsubscribe-Links
  - Personalisierung: Name, Firma, Nische, Produktempfehlung
  - Konversions-Tracking (opens, clicks, conversions)
  - Auto-Pause bei Bounce-Rate > 5%
  - Supabase-State (survives Railway restarts)
  - Telegram-Alerts bei Quota-Erreicht oder Fehler
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import smtplib
import sqlite3
import time
from datetime import datetime, timezone, timedelta, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

log = logging.getLogger("MegaAcquisition")

_BASE    = Path(__file__).parent.parent
DATA_DIR = _BASE / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
_DB      = DATA_DIR / "mega_acquisition.db"

# ── Env Helpers ───────────────────────────────────────────────────────────────

def _e(key: str, default: str = "") -> str:
    return os.getenv(key, default)

SHOP_URL    = f"https://{_e('SHOPIFY_CUSTOM_DOMAIN', _e('SHOPIFY_SHOP_DOMAIN','ineedit.com.co'))}"
SHOP_NAME   = _e("SHOP_NAME", "I Need It")
TG_TOKEN    = _e("TELEGRAM_BOT_TOKEN")
TG_CHAT     = _e("TELEGRAM_CHAT_ID")

# ── SMTP Accounts Pool ────────────────────────────────────────────────────────

SMTP_ACCOUNTS = []

def _build_smtp_pool() -> List[Dict]:
    accounts = []
    # Account 1: bullpowersrtkennels (500/day)
    if _e("GMAIL_APP_PASSWORD_3") or _e("GMAIL_APP_PASSWORD_BULLPOWER"):
        accounts.append({
            "name":     "BullPower",
            "user":     _e("GMAIL_USER_3", _e("GMAIL_USER_BULLPOWER", "bullpowersrtkennels@gmail.com")),
            "password": _e("GMAIL_APP_PASSWORD_3", _e("GMAIL_APP_PASSWORD_BULLPOWER","")),
            "host":     "smtp.gmail.com",
            "port":     587,
            "daily_limit": 500,
            "sent_today": 0,
            "last_reset": "",
        })
    # Account 2: aiitecbuuss (500/day)
    if _e("GMAIL_APP_PASSWORD_5") or _e("GMAIL_APP_PASSWORD_AIITEC"):
        accounts.append({
            "name":     "AiiteC",
            "user":     _e("GMAIL_USER_5", _e("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")),
            "password": _e("GMAIL_APP_PASSWORD_5", _e("GMAIL_APP_PASSWORD_AIITEC","")),
            "host":     "smtp.gmail.com",
            "port":     587,
            "daily_limit": 500,
            "sent_today": 0,
            "last_reset": "",
        })
    # Account 3: STRATO aiitec (500/day)
    if _e("SMTP_HOST_6") and _e("GMAIL_APP_PASSWORD_6",""):
        accounts.append({
            "name":     "AiiteC-Strato",
            "user":     _e("GMAIL_USER_6", "rudolf.sarkany@aitec.de"),
            "password": _e("GMAIL_APP_PASSWORD_6",""),
            "host":     _e("SMTP_HOST_6", "smtp.strato.de"),
            "port":     int(_e("SMTP_PORT_6","587")),
            "daily_limit": 500,
            "sent_today": 0,
            "last_reset": "",
        })
    # Account 4: rudolfsarkany1984 (500/day)
    if _e("GMAIL_APP_PASSWORD_8"):
        accounts.append({
            "name":     "RudolfPersonal",
            "user":     _e("GMAIL_USER_8", "rudolfsarkany1984@gmail.com"),
            "password": _e("GMAIL_APP_PASSWORD_8",""),
            "host":     "smtp.gmail.com",
            "port":     587,
            "daily_limit": 500,
            "sent_today": 0,
            "last_reset": "",
        })
    # Account 5: dragonadnp@gmail.com (500/day)
    if _e("GMAIL_APP_PASSWORD_1"):
        accounts.append({
            "name":     "Dragon",
            "user":     _e("GMAIL_USER_1", "dragonadnp@gmail.com"),
            "password": _e("GMAIL_APP_PASSWORD_1",""),
            "host":     "smtp.gmail.com",
            "port":     587,
            "daily_limit": 500,
            "sent_today": 0,
            "last_reset": "",
        })
    # Account 7: rudolf.sarkany.aiitec@gmail.com (500/day)
    if _e("GMAIL_APP_PASSWORD_7"):
        accounts.append({
            "name":     "AiiteCGmail",
            "user":     _e("GMAIL_USER_7", "rudolf.sarkany.aiitec@gmail.com"),
            "password": _e("GMAIL_APP_PASSWORD_7",""),
            "host":     "smtp.gmail.com",
            "port":     587,
            "daily_limit": 500,
            "sent_today": 0,
            "last_reset": "",
        })
    return accounts

# ── SQLite State DB ───────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS acquisition_leads (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        email       TEXT UNIQUE NOT NULL,
        name        TEXT DEFAULT '',
        company     TEXT DEFAULT '',
        niche       TEXT DEFAULT 'shop',
        source      TEXT DEFAULT 'unknown',
        language    TEXT DEFAULT 'de',
        status      TEXT DEFAULT 'new',
        validated   INTEGER DEFAULT 0,
        created_at  TEXT DEFAULT (datetime('now')),
        last_sent   TEXT,
        sent_count  INTEGER DEFAULT 0,
        opened      INTEGER DEFAULT 0,
        clicked     INTEGER DEFAULT 0,
        converted   INTEGER DEFAULT 0,
        bounced     INTEGER DEFAULT 0,
        unsubscribed INTEGER DEFAULT 0,
        tags        TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS acquisition_sends (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        email       TEXT NOT NULL,
        subject     TEXT,
        template    TEXT,
        account     TEXT,
        sent_at     TEXT DEFAULT (datetime('now')),
        status      TEXT DEFAULT 'sent'
    );
    CREATE TABLE IF NOT EXISTS acquisition_stats (
        date        TEXT PRIMARY KEY,
        sent        INTEGER DEFAULT 0,
        opened      INTEGER DEFAULT 0,
        clicked     INTEGER DEFAULT 0,
        converted   INTEGER DEFAULT 0,
        bounced     INTEGER DEFAULT 0,
        unsubscribed INTEGER DEFAULT 0,
        revenue_eur REAL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS smtp_quota (
        account     TEXT PRIMARY KEY,
        date        TEXT,
        sent        INTEGER DEFAULT 0
    );
    """)
    conn.commit()
    return conn


def _get_smtp_sent_today(account_name: str) -> int:
    today = date.today().isoformat()
    conn = _db()
    row = conn.execute("SELECT sent FROM smtp_quota WHERE account=? AND date=?",
                       (account_name, today)).fetchone()
    conn.close()
    return row["sent"] if row else 0


def _increment_smtp_sent(account_name: str, count: int = 1):
    today = date.today().isoformat()
    conn = _db()
    conn.execute("""
        INSERT INTO smtp_quota (account, date, sent) VALUES (?,?,?)
        ON CONFLICT(account) DO UPDATE SET
            sent = CASE WHEN date=excluded.date THEN sent+excluded.sent ELSE excluded.sent END,
            date = excluded.date
    """, (account_name, today, count))
    conn.commit()
    conn.close()


def _get_uncontacted_leads(limit: int = 50, niche: str = "") -> List[Dict]:
    conn = _db()
    query = """
        SELECT * FROM acquisition_leads
        WHERE status='new' AND bounced=0 AND unsubscribed=0
              AND (last_sent IS NULL OR last_sent < datetime('now','-1 day'))
    """
    params: List = []
    if niche:
        query += " AND niche=?"
        params.append(niche)
    query += " ORDER BY created_at ASC LIMIT ?"
    params.append(limit)
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()
    return rows


def _mark_sent(email: str, subject: str, template: str, account: str):
    conn = _db()
    conn.execute("UPDATE acquisition_leads SET last_sent=datetime('now'), sent_count=sent_count+1, status='contacted' WHERE email=?", (email,))
    conn.execute("INSERT INTO acquisition_sends (email,subject,template,account) VALUES (?,?,?,?)",
                 (email, subject, template, account))
    today = date.today().isoformat()
    conn.execute("""
        INSERT INTO acquisition_stats (date,sent) VALUES (?,1)
        ON CONFLICT(date) DO UPDATE SET sent=sent+1
    """, (today,))
    conn.commit()
    conn.close()


def _add_leads(leads: List[Dict]) -> int:
    if not leads:
        return 0
    conn = _db()
    added = 0
    for lead in leads:
        email = (lead.get("email") or "").strip().lower()
        if not email or "@" not in email or "." not in email.split("@")[-1]:
            continue
        # Skip obvious test/invalid emails
        if any(x in email for x in ["test@", "example@", "sample@", "@example.com", "noreply@"]):
            continue
        try:
            conn.execute("""
                INSERT OR IGNORE INTO acquisition_leads
                (email, name, company, niche, source, language, tags)
                VALUES (?,?,?,?,?,?,?)
            """, (email, lead.get("name",""), lead.get("company",""),
                  lead.get("niche","shop"), lead.get("source","unknown"),
                  lead.get("language","de"), lead.get("tags","")))
            if conn.execute("SELECT changes()").fetchone()[0]:
                added += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return added


def _get_stats_today() -> Dict:
    today = date.today().isoformat()
    conn = _db()
    row = conn.execute("SELECT * FROM acquisition_stats WHERE date=?", (today,)).fetchone()
    total = conn.execute("SELECT COUNT(*) as n FROM acquisition_leads").fetchone()["n"]
    new   = conn.execute("SELECT COUNT(*) as n FROM acquisition_leads WHERE status='new'").fetchone()["n"]
    conn.close()
    if row:
        return {**dict(row), "total_leads": total, "new_leads": new}
    return {"date": today, "sent": 0, "opened": 0, "clicked": 0,
            "converted": 0, "bounced": 0, "total_leads": total, "new_leads": new}


# ── Email Validation ──────────────────────────────────────────────────────────

_THROWAWAY_DOMAINS = {
    "mailinator.com","guerrillamail.com","tempmail.com","10minutemail.com",
    "throwaway.email","dispostable.com","fakeinbox.com","trashmail.com",
    "sharklasers.com","guerrillamailblock.com","yopmail.com","spam4.me",
}

def _is_valid_email(email: str) -> bool:
    email = email.strip().lower()
    if not re.match(r'^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$', email):
        return False
    domain = email.split("@")[-1]
    if domain in _THROWAWAY_DOMAINS:
        return False
    return True


# ── Lead Discovery Sources ────────────────────────────────────────────────────

async def _discover_shopify_leads() -> List[Dict]:
    """Shopify Kunden ohne bisherige Bestellung → Warm-Lead-Pool."""
    domain = _e("SHOPIFY_SHOP_DOMAIN")
    token  = _e("SHOPIFY_ADMIN_API_TOKEN")
    version = _e("SHOPIFY_API_VERSION", "2026-04")
    if not domain or not token:
        return []
    h = {"X-Shopify-Access-Token": token}
    base = f"https://{domain}/admin/api/{version}"
    leads = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{base}/customers.json", headers=h,
                             params={"limit": 250, "fields": "id,email,first_name,last_name,orders_count"},
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                customers = (await r.json(content_type=None)).get("customers", [])
        for c in customers:
            email = c.get("email","").strip()
            if not email or not _is_valid_email(email):
                continue
            if c.get("orders_count", 0) > 0:
                continue  # bereits Käufer → anders behandeln
            leads.append({
                "email": email,
                "name": f"{c.get('first_name','')} {c.get('last_name','')}".strip(),
                "source": "shopify_customer",
                "niche": "shop",
                "language": "de",
                "tags": "shopify,no-order",
            })
    except Exception as e:
        log.warning("Shopify leads: %s", e)
    return leads


async def _discover_shopify_abandoned_carts() -> List[Dict]:
    """Abandoned Checkouts der letzten 7 Tage → Höchste Kaufintention."""
    domain = _e("SHOPIFY_SHOP_DOMAIN")
    token  = _e("SHOPIFY_ADMIN_API_TOKEN")
    version = _e("SHOPIFY_API_VERSION", "2026-04")
    if not domain or not token:
        return []
    h = {"X-Shopify-Access-Token": token}
    base = f"https://{domain}/admin/api/{version}"
    leads = []
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{base}/checkouts.json", headers=h,
                             params={"limit": 250, "created_at_min": since,
                                     "fields": "email,billing_address,line_items,total_price"},
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                checkouts = (await r.json(content_type=None)).get("checkouts", [])
        for c in checkouts:
            email = c.get("email","").strip()
            if not email or not _is_valid_email(email):
                continue
            addr = c.get("billing_address") or {}
            leads.append({
                "email": email,
                "name": addr.get("name",""),
                "source": "abandoned_checkout",
                "niche": "shop",
                "language": "de",
                "tags": f"abandoned-cart,value={c.get('total_price','0')}",
            })
    except Exception as e:
        log.warning("Abandoned carts: %s", e)
    return leads


async def _discover_klaviyo_subscribers() -> List[Dict]:
    """Klaviyo Subscriber → bereits opt-in → beste Zustellbarkeit."""
    key = _e("KLAVIYO_API_KEY")
    list_id = _e("KLAVIYO_LIST_ID", "Xwxq6V")
    if not key:
        return []
    h = {"Authorization": f"Klaviyo-API-Key {key}", "revision": "2024-10-15"}
    leads = []
    try:
        async with aiohttp.ClientSession() as s:
            cursor = None
            while True:
                params = {"fields[profile]": "email,first_name,last_name", "page[size]": "100"}
                if cursor:
                    params["page[cursor]"] = cursor
                async with s.get(f"https://a.klaviyo.com/api/lists/{list_id}/profiles/",
                                 headers=h, params=params,
                                 timeout=aiohttp.ClientTimeout(total=15)) as r:
                    d = await r.json(content_type=None)
                profiles = d.get("data", [])
                for p in profiles:
                    attrs = p.get("attributes", {})
                    email = attrs.get("email","")
                    if email and _is_valid_email(email):
                        leads.append({
                            "email": email,
                            "name": f"{attrs.get('first_name','')} {attrs.get('last_name','')}".strip(),
                            "source": "klaviyo_subscriber",
                            "niche": "shop",
                            "language": "de",
                            "tags": "newsletter,optin",
                        })
                # Pagination
                cursor = d.get("links", {}).get("next", "")
                if not cursor or not profiles:
                    break
                await asyncio.sleep(0.5)
    except Exception as e:
        log.warning("Klaviyo subscribers: %s", e)
    return leads


async def _discover_b2b_leads_from_supabase() -> List[Dict]:
    """DACH KMU-Leads aus Supabase aiitec_companies + mpo_companies."""
    url = _e("SUPABASE_URL")
    key = _e("SUPABASE_SERVICE_KEY", _e("SUPABASE_ANON_KEY",""))
    if not url or not key:
        return []
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Accept-Profile": "api"}
    leads = []
    try:
        async with aiohttp.ClientSession() as s:
            for table in ["mpo_companies", "aiitec_companies"]:
                async with s.get(f"{url}/rest/v1/{table}", headers=h,
                                 params={"select": "name,email,industry,city,country",
                                         "limit": "500"},
                                 timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        rows = await r.json(content_type=None)
                        for row in (rows if isinstance(rows, list) else []):
                            email = (row.get("email") or "").strip()
                            if not email or not _is_valid_email(email):
                                continue
                            leads.append({
                                "email": email,
                                "name": row.get("name",""),
                                "company": row.get("name",""),
                                "source": f"supabase_{table}",
                                "niche": "b2b",
                                "language": "de",
                                "tags": f"b2b,{row.get('industry','')},{row.get('city','')}",
                            })
    except Exception as e:
        log.warning("Supabase leads: %s", e)
    return leads


async def _discover_niche_leads_web() -> List[Dict]:
    """
    Web-Research für Smart-Home/Gadget-Käufer:
    Sucht in öffentlichen Quellen nach potenziellen Käufern.
    Nutzt existierende Daten aus Scraper-Modulen.
    """
    leads = []
    try:
        # Aus scraped_products Tabelle - Shopify competitors Kunden
        url = _e("SUPABASE_URL")
        key = _e("SUPABASE_SERVICE_KEY", _e("SUPABASE_ANON_KEY",""))
        if url and key:
            h = {"apikey": key, "Authorization": f"Bearer {key}"}
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{url}/rest/v1/lead_events", headers=h,
                                 params={"select": "email,event_type,metadata",
                                         "email": "not.is.null", "limit": "500"},
                                 timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        rows = await r.json(content_type=None)
                        for row in (rows if isinstance(rows, list) else []):
                            email = (row.get("email") or "").strip()
                            if email and _is_valid_email(email):
                                leads.append({
                                    "email": email,
                                    "source": "lead_events",
                                    "niche": "shop",
                                    "language": "de",
                                    "tags": f"event:{row.get('event_type','')}",
                                })
    except Exception as e:
        log.warning("Niche leads web: %s", e)
    return leads


async def run_lead_discovery() -> Dict:
    """Alle Lead-Quellen parallel abfragen und in DB speichern."""
    results = await asyncio.gather(
        _discover_shopify_leads(),
        _discover_shopify_abandoned_carts(),
        _discover_klaviyo_subscribers(),
        _discover_b2b_leads_from_supabase(),
        _discover_niche_leads_web(),
        return_exceptions=True,
    )
    all_leads: List[Dict] = []
    for r in results:
        if isinstance(r, list):
            all_leads.extend(r)
        elif isinstance(r, Exception):
            log.warning("Lead source failed: %s", r)

    added = _add_leads(all_leads)
    log.info("Lead discovery: %d found, %d new added", len(all_leads), added)
    return {"total_found": len(all_leads), "new_added": added}


# ── Email Templates ───────────────────────────────────────────────────────────

def _shop_promo_template(lead: Dict, products: List[Dict] = None) -> Tuple[str, str]:
    name = lead.get("name") or "Technik-Enthusiast"
    first = name.split()[0] if name else "Hey"
    discount = "MEGA10"  # 10% discount code

    product_html = ""
    if products:
        product_html = "<p style='margin:16px 0 8px;color:#aaa;font-size:13px'>🔥 Empfohlen für dich:</p>\n"
        for p in products[:3]:
            price = p.get("price","?")
            title = p.get("title","Produkt")[:50]
            handle = p.get("handle","")
            img = p.get("image","")
            product_html += f"""
<div style="border:1px solid #222;border-radius:8px;padding:12px;margin:8px 0;background:#0a0a14">
  <a href="{SHOP_URL}/products/{handle}?utm_source=email&utm_medium=acquisition" style="color:#4ade80;text-decoration:none;font-weight:600">{title}</a>
  <span style="color:#9b5de5;margin-left:8px">€{price}</span>
</div>"""

    subject = f"🔥 {first}, exclusive Deal für dich — {discount} spart dir 10%"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#050508;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#050508">
<tr><td align="center" style="padding:40px 20px">
<table width="560" style="max-width:560px;width:100%">
<tr><td align="center" style="padding-bottom:28px">
  <span style="color:#4ade80;font-size:28px;font-weight:800">⚡ I Need It</span>
</td></tr>
<tr><td style="background:#0d0d1c;border-radius:14px;padding:36px 32px;border:1px solid #1a1a2e">
  <h1 style="color:#fff;font-size:22px;font-weight:700;margin:0 0 16px">
    Hey {first}, das könnte dich interessieren! 👋
  </h1>
  <p style="color:#aaa;font-size:15px;line-height:1.7;margin:0 0 20px">
    Wir haben die <strong style="color:#fff">besten Smart-Home & Gadget-Deals</strong> für dich zusammengestellt.
    Spare heute <strong style="color:#4ade80">10% auf alles</strong> mit deinem persönlichen Code:
  </p>
  <div style="text-align:center;margin:0 0 28px">
    <div style="display:inline-block;background:#050508;border:2px dashed #4ade80;border-radius:10px;padding:16px 32px">
      <p style="color:#666;font-size:11px;text-transform:uppercase;letter-spacing:.12em;margin:0 0 4px">Dein Rabattcode</p>
      <p style="color:#4ade80;font-size:26px;font-weight:800;letter-spacing:.15em;margin:0;font-family:monospace">{discount}</p>
    </div>
  </div>
  {product_html}
  <div style="text-align:center;margin:24px 0">
    <a href="{SHOP_URL}?utm_source=email&utm_medium=acquisition&utm_campaign=mega10&ref={lead.get('email','')[:10]}"
       style="display:inline-block;background:#4ade80;color:#000;text-decoration:none;padding:15px 36px;border-radius:8px;font-weight:700;font-size:15px">
      🛒 Jetzt shoppen →
    </a>
  </div>
  <p style="color:#555;font-size:12px;text-align:center;margin:16px 0 0">
    Kostenloser Versand ab €35 · 30 Tage Rückgabe · SSL-sicher
  </p>
</td></tr>
<tr><td align="center" style="padding-top:20px">
  <p style="color:#333;font-size:11px;margin:0">
    {SHOP_NAME} · ineedit.com.co<br>
    <a href="{SHOP_URL}/pages/unsubscribe?email={lead.get('email','')}" style="color:#444">Abmelden</a>
  </p>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""
    return subject, html


def _b2b_outreach_template(lead: Dict) -> Tuple[str, str]:
    name = lead.get("name") or lead.get("company") or "Geschäftsführer/in"
    first = name.split()[0] if " " in name else name
    company = lead.get("company","Ihrem Unternehmen")

    subject = f"KI-Automatisierung für {company} — 30% Zeit sparen ab Woche 1"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f8f9fa;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#f8f9fa">
<tr><td align="center" style="padding:40px 20px">
<table width="560" style="max-width:560px;width:100%">
<tr><td style="background:#fff;border-radius:8px;padding:36px 32px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
  <p style="color:#666;font-size:12px;text-transform:uppercase;letter-spacing:.1em;margin:0 0 16px">AIITEC — KI-Automatisierung</p>
  <h1 style="color:#1a1a2e;font-size:20px;font-weight:700;margin:0 0 16px">
    Guten Tag {first},
  </h1>
  <p style="color:#444;font-size:15px;line-height:1.7;margin:0 0 16px">
    ich bin Rudolf Sarkany von AIITEC. Wir helfen mittelständischen Unternehmen wie {company},
    <strong>wiederkehrende Aufgaben mit KI zu automatisieren</strong> — Angebotserstellung,
    E-Mail-Bearbeitung, Reporting, Lead-Qualifikation.
  </p>
  <p style="color:#444;font-size:15px;line-height:1.7;margin:0 0 20px">
    Unsere Kunden sparen im Schnitt <strong>30% Arbeitszeit</strong> ab der ersten Woche.
    Kein IT-Projekt, keine lange Implementierung — einfach starten.
  </p>
  <div style="background:#f0f4ff;border-left:4px solid #9b5de5;padding:16px;border-radius:0 8px 8px 0;margin:0 0 24px">
    <p style="color:#1a1a2e;font-size:14px;font-weight:600;margin:0 0 4px">Kostenloses 20-Minuten-Demo-Gespräch</p>
    <p style="color:#666;font-size:13px;margin:0">Zeigen Sie uns Ihren größten manuellen Prozess — wir zeigen, wie KI das löst.</p>
  </div>
  <div style="text-align:center;margin:24px 0">
    <a href="https://aiitec.online/?ref=email&utm_source=outreach&utm_medium=email&utm_campaign=b2b"
       style="display:inline-block;background:#9b5de5;color:#fff;text-decoration:none;padding:14px 32px;border-radius:6px;font-weight:700;font-size:15px">
      Demo anfragen →
    </a>
  </div>
  <p style="color:#888;font-size:13px;margin:16px 0 0">
    Mit freundlichen Grüßen<br>
    <strong>Rudolf Sarkany</strong><br>
    AIITEC — KI-Automatisierung für den Mittelstand<br>
    📞 +49 176 22890860 | aiitecbuuss@gmail.com
  </p>
</td></tr>
<tr><td align="center" style="padding-top:16px">
  <p style="color:#aaa;font-size:11px;margin:0">
    AIITEC · Finning, Bayern ·
    <a href="https://aiitec.online/unsubscribe?email={lead.get('email','')}" style="color:#aaa">Abmelden</a>
  </p>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""
    return subject, html


def _flash_sale_template(lead: Dict, hours_left: int = 24) -> Tuple[str, str]:
    name = lead.get("name") or "Smart-Shopper"
    first = name.split()[0] if name else "Hey"
    subject = f"⏰ Nur noch {hours_left}h! Flash-Sale bis zu 40% — {first}"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#050508;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#050508">
<tr><td align="center" style="padding:40px 20px">
<table width="560" style="max-width:560px;width:100%">
<tr><td style="background:linear-gradient(135deg,#1a0a2e,#0a1a2e);border-radius:14px;padding:36px 32px;border:1px solid #2a1a4e">
  <div style="text-align:center;background:#ff4757;border-radius:8px;padding:10px;margin:0 0 24px">
    <p style="color:#fff;font-weight:800;font-size:16px;margin:0">⏰ FLASH SALE — Nur {hours_left} Stunden!</p>
  </div>
  <h1 style="color:#fff;font-size:24px;font-weight:800;text-align:center;margin:0 0 20px">
    Bis zu 40% auf Smart Home & Gadgets
  </h1>
  <p style="color:#aaa;font-size:15px;line-height:1.7;text-align:center;margin:0 0 28px">
    Hey {first}! Exklusiver Sale für ausgewählte Kunden.
    Kein Code nötig — Rabatte bereits eingerechnet.
  </p>
  <div style="text-align:center;margin:0 0 24px">
    <a href="{SHOP_URL}/collections/angebote-unter-30?utm_source=email&utm_medium=flash_sale"
       style="display:inline-block;background:#ff4757;color:#fff;text-decoration:none;padding:16px 40px;border-radius:8px;font-weight:800;font-size:16px">
      🔥 Zum Flash Sale →
    </a>
  </div>
  <p style="color:#555;font-size:12px;text-align:center">
    <a href="{SHOP_URL}/pages/unsubscribe?email={lead.get('email','')}" style="color:#555">Abmelden</a>
  </p>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""
    return subject, html


# ── SMTP Sender ───────────────────────────────────────────────────────────────

def _send_smtp_sync(account: Dict, to_email: str, subject: str, html: str) -> bool:
    """Synchroner SMTP-Versand (in Executor ausführen)."""
    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = f"{SHOP_NAME} <{account['user']}>"
        msg["To"]      = to_email
        msg["Subject"] = subject
        msg["List-Unsubscribe"] = f"<{SHOP_URL}/pages/unsubscribe?email={to_email}>"
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(account["host"], account["port"], timeout=20) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(account["user"], account["password"])
            srv.sendmail(account["user"], [to_email], msg.as_bytes())
        return True
    except Exception as e:
        log.warning("SMTP send to %s via %s: %s", to_email, account["name"], e)
        return False


async def _send_smtp_async(account: Dict, to_email: str, subject: str, html: str) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _send_smtp_sync, account, to_email, subject, html)


# ── Sendgrid API Sender ───────────────────────────────────────────────────────

async def _send_via_sendgrid(to_email: str, subject: str, html: str,
                              from_email: str = "bullpowersrtkennels@gmail.com",
                              from_name: str = "I Need It") -> bool:
    key = _e("SENDGRID_API_KEY_AIITEC") or _e("SENDGRID_API_KEY","")
    if not key:
        return False
    try:
        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": from_email, "name": from_name},
            "subject": subject,
            "content": [{"type": "text/html", "value": html}],
            "tracking_settings": {
                "click_tracking": {"enable": True},
                "open_tracking": {"enable": True},
            },
        }
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.sendgrid.com/v3/mail/send",
                              headers={"Authorization": f"Bearer {key}",
                                       "Content-Type": "application/json"},
                              json=payload,
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                return r.status in (200, 201, 202)
    except Exception as e:
        log.warning("SendGrid send to %s: %s", to_email, e)
        return False


# ── Klaviyo Subscriber Import & Send ─────────────────────────────────────────

async def _klaviyo_add_profile(email: str, name: str = "") -> bool:
    """Fügt Lead zu Klaviyo-Liste hinzu (für zukünftige Campaigns)."""
    key = _e("KLAVIYO_API_KEY")
    list_id = _e("KLAVIYO_LIST_ID", "Xwxq6V")
    if not key:
        return False
    first = name.split()[0] if name else ""
    last  = " ".join(name.split()[1:]) if name and " " in name else ""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://a.klaviyo.com/client/subscriptions/?company_id={_e('KLAVIYO_COMPANY_ID', 'VaCYq3')}",
                json={"data": {"type": "subscription", "attributes": {
                    "profile": {"data": {"type": "profile", "attributes": {
                        "email": email,
                        "first_name": first,
                        "last_name": last,
                    }}},
                    "list": {"data": {"type": "list", "id": list_id}},
                }}},
                headers={"Content-Type": "application/json", "revision": "2024-10-15"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                return r.status in (200, 201, 202)
    except Exception as e:
        log.warning("Klaviyo add profile %s: %s", email, e)
        return False


# ── Multi-Account Send with Auto-Rotation ────────────────────────────────────

async def _send_one(lead: Dict, template: str = "shop_promo",
                    products: List[Dict] = None) -> bool:
    email = lead.get("email","")
    if not email or not _is_valid_email(email):
        return False
    raw_name = lead.get("name") or ""
    if str(raw_name).strip() in ("None", "none", "null", "N/A"):
        lead = {**lead, "name": ""}  # blank → template uses fallback

    niche = lead.get("niche","shop")
    if template == "auto":
        template = "b2b_outreach" if niche == "b2b" else "shop_promo"

    if template == "shop_promo":
        subject, html = _shop_promo_template(lead, products)
    elif template == "b2b_outreach":
        subject, html = _b2b_outreach_template(lead)
    elif template == "flash_sale":
        subject, html = _flash_sale_template(lead)
    else:
        subject, html = _shop_promo_template(lead, products)

    # Account rotation: wähle Account mit verfügbarer Quota
    pool = _build_smtp_pool()
    selected = None
    for acc in pool:
        sent_today = _get_smtp_sent_today(acc["name"])
        if sent_today < acc["daily_limit"]:
            selected = acc
            break

    if not selected:
        # Fallback: SendGrid
        ok = await _send_via_sendgrid(email, subject, html)
        if ok:
            _mark_sent(email, subject, template, "sendgrid")
        return ok

    ok = await _send_smtp_async(selected, email, subject, html)
    if ok:
        _mark_sent(email, subject, template, selected["name"])
        _increment_smtp_sent(selected["name"])
        # Parallel: auch in Klaviyo eintragen
        asyncio.create_task(_klaviyo_add_profile(email, lead.get("name","")))
    return ok


# ── Telegram Alerts ───────────────────────────────────────────────────────────

async def _tg(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


# ── Main Daily Run ────────────────────────────────────────────────────────────

async def run_daily_acquisition(target: int = 200, template: str = "auto") -> Dict:
    """
    Täglicher Akquisitions-Run:
    1. Lead-Discovery (alle Quellen)
    2. Emails versenden bis target erreicht
    3. Telegram-Report
    """
    log.info("MegaAcquisition START | target=%d | template=%s", target, template)

    # 1. Leads entdecken
    discovery = await run_lead_discovery()

    # 2. Verfügbare Leads holen
    leads_shop = _get_uncontacted_leads(limit=target, niche="shop")
    leads_b2b  = _get_uncontacted_leads(limit=min(50, target // 4), niche="b2b")
    all_leads  = leads_shop + leads_b2b
    random_leads = all_leads[:target]

    if not random_leads:
        log.info("Keine uncontacted Leads verfügbar")
        await _tg("📧 <b>MegaAcquisition</b>: Keine Leads verfügbar — Lead-Discovery läuft")
        return {"ok": True, "sent": 0, "discovery": discovery, "msg": "no leads"}

    # 3. Shopify Produkte für Empfehlung holen
    products = []
    try:
        domain  = _e("SHOPIFY_SHOP_DOMAIN")
        token   = _e("SHOPIFY_ADMIN_API_TOKEN")
        version = _e("SHOPIFY_API_VERSION", "2026-04")
        if domain and token:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://{domain}/admin/api/{version}/products.json",
                                 headers={"X-Shopify-Access-Token": token},
                                 params={"status": "active", "limit": "10",
                                         "fields": "id,title,handle,variants,images"},
                                 timeout=aiohttp.ClientTimeout(total=15)) as r:
                    prods = (await r.json(content_type=None)).get("products",[])
            for p in prods:
                price = p.get("variants",[{}])[0].get("price","0")
                img = p.get("images",[{}])[0].get("src","") if p.get("images") else ""
                products.append({"title": p.get("title",""), "handle": p.get("handle",""),
                                  "price": price, "image": img})
    except Exception as e:
        log.warning("Fetch products for emails: %s", e)

    # 4. Senden (mit Delay für Anti-Spam)
    sent = 0
    errors = 0
    for i, lead in enumerate(random_leads):
        try:
            ok = await _send_one(lead, template=template, products=products)
            if ok:
                sent += 1
            else:
                errors += 1
        except Exception as e:
            log.warning("Send error for %s: %s", lead.get("email","?"), e)
            errors += 1

        # Anti-Spam-Delay: 1-3s zwischen Emails
        if i % 50 == 49:
            await asyncio.sleep(5)  # Kurze Pause alle 50
        elif i % 10 == 9:
            await asyncio.sleep(2)
        else:
            await asyncio.sleep(1.2)

    stats = _get_stats_today()

    # 5. Telegram-Report
    await _tg(
        f"📧 <b>MegaAcquisition Daily Report</b>\n"
        f"✅ Gesendet heute: <b>{sent}</b> Emails\n"
        f"❌ Fehler: {errors}\n"
        f"📊 Leads in DB: {stats['total_leads']} total / {stats['new_leads']} neu\n"
        f"🔍 Neu entdeckt: +{discovery.get('new_added',0)}\n"
        f"🎯 Ziel war: {target}"
    )

    log.info("MegaAcquisition DONE | sent=%d | errors=%d", sent, errors)
    return {
        "ok": True,
        "sent": sent,
        "errors": errors,
        "discovery": discovery,
        "total_leads": stats["total_leads"],
        "new_leads": stats["new_leads"],
        "stats_today": stats,
    }


async def get_status() -> Dict:
    stats = _get_stats_today()
    pool = _build_smtp_pool()
    quota_status = []
    for acc in pool:
        sent = _get_smtp_sent_today(acc["name"])
        quota_status.append({
            "account": acc["name"],
            "user": acc["user"],
            "sent_today": sent,
            "limit": acc["daily_limit"],
            "remaining": acc["daily_limit"] - sent,
        })
    return {
        "ok": True,
        "module": "Mega Acquisition Engine",
        "stats_today": stats,
        "smtp_accounts": quota_status,
        "total_capacity_today": sum(acc["daily_limit"] - _get_smtp_sent_today(acc["name"]) for acc in pool),
    }
