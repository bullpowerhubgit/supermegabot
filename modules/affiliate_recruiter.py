"""
Affiliate Recruiter — automatische Rekrutierung von DS24-Affiliates
====================================================================
Findet Blogger, YouTuber, E-Commerce-Berater und sendet personalisierte
Affiliate-Pitches. 30% Lifetime-Provision auf €49-299/Monat.

Affiliate-Link: https://www.checkout-ds24.com/product/669750?affiliate=user37405262
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import smtplib
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp

log = logging.getLogger("AffiliateRecruiter")

_DB_PATH = Path(__file__).parent.parent / "data" / "affiliate_recruiter.db"

AFFILIATE_LINK = "https://www.checkout-ds24.com/product/669750?affiliate=user37405262"
AFFILIATE_ID   = "user37405262"
STRIPE_STARTER = "https://buy.stripe.com/7sYeVf53k5PQ7EA2Wq4F203"

PER_ACCOUNT_HOURLY = 10
DAILY_AFFILIATE_LIMIT = 30

def _e(key: str, default: str = "") -> str:
    return os.getenv(key, default)

# ── Database ──────────────────────────────────────────────────────────────────
def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS targets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,
            email       TEXT UNIQUE,
            platform    TEXT,
            url         TEXT,
            category    TEXT,
            found_at    REAL DEFAULT 0,
            status      TEXT DEFAULT 'new'
        );
        CREATE TABLE IF NOT EXISTS sent (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id   INTEGER,
            email       TEXT,
            smtp_user   TEXT,
            sent_at     TEXT,
            stage       INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS responses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT,
            message     TEXT,
            received_at TEXT
        );
    """)
    conn.commit()
    return conn

# ── SMTP pool (same pattern as mass_outreach_1000) ────────────────────────────
def _smtp_pool() -> List[Dict]:
    pairs = [
        ("GMAIL_USER_AIITEC",    "GMAIL_APP_PASSWORD_AIITEC"),
        ("GMAIL_USER_BULLPOWER", "GMAIL_APP_PASSWORD_BULLPOWER"),
        ("GMAIL_USER_3",         "GMAIL_APP_PASSWORD_3"),
        ("GMAIL_USER_5",         "GMAIL_APP_PASSWORD_5"),
        ("GMAIL_USER_1",         "GMAIL_APP_PASSWORD_1"),
        ("GMAIL_USER_7",         "GMAIL_APP_PASSWORD_7"),
        ("GMAIL_USER_8",         "GMAIL_APP_PASSWORD_8"),
    ]
    seen = set()
    accounts = []
    for uk, pk in pairs:
        u, p = _e(uk), _e(pk)
        if u and p and u not in seen:
            seen.add(u)
            accounts.append({"user": u, "pass": p})
    return accounts

_pool_idx = 0
_hourly_sends: Dict[str, int] = {}

def _send_gmail(user: str, password: str, to: str, subject: str, body: str) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Rudolf Sarkany | SuperMegaBot <{user}>"
        msg["To"]      = to
        msg["Reply-To"] = user
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(user, password)
            s.sendmail(user, [to], msg.as_string())
        return True
    except smtplib.SMTPAuthenticationError:
        log.warning("Gmail Auth fehlgeschlagen: %s", user)
        return False
    except Exception as e:
        log.error("Gmail error (%s → %s): %s", user, to, e)
        return False

def _send_email(to: str, subject: str, body: str) -> Tuple[bool, str]:
    global _pool_idx
    # FAIL-CLOSED: Guard darf nie still übersprungen werden
    from modules.email_guard import require_valid_email, register_sent
    ok, errs = require_valid_email(subject, body, to)
    if not ok:
        log.warning("EmailGuard blockiert [%s]: %s", to, errs)
        return False, ""
    pool = _smtp_pool()
    if not pool:
        log.error("Kein SMTP-Account konfiguriert")
        return False, ""
    hour_key = datetime.now().strftime("%Y-%m-%d-%H")
    for _ in range(len(pool)):
        acct = pool[_pool_idx % len(pool)]
        _pool_idx += 1
        key = f"{acct['user']}_{hour_key}"
        if _hourly_sends.get(key, 0) >= PER_ACCOUNT_HOURLY:
            continue
        ok = _send_gmail(acct["user"], acct["pass"], to, subject, body)
        if ok:
            _hourly_sends[key] = _hourly_sends.get(key, 0) + 1
            try:
                register_sent(to, subject, body)
            except Exception:
                pass
            return True, acct["user"]
    return False, ""

# ── Email templates ───────────────────────────────────────────────────────────
def _pitch_subject(name: str) -> str:
    return f"30% Provision auf €49-299/Monat — Partnerschaft für {name}?"

def _pitch_body(name: str, platform: str) -> str:
    return f"""Hallo {name},

ich habe {platform} verfolgt — sehr hilfreiche Inhalte für E-Commerce Betreiber.

Ich biete dir 30% Lifetime-Provision auf alle SuperMegaBot-Abonnements (€49-299/Monat).
Das bedeutet: Ein Kunde = €15-90 pro Monat, dauerhaft.

SuperMegaBot automatisiert Shopify-Shops komplett: Preise, Bestellungen, Marketing, Social Media.

Dein persönlicher Affiliate-Link:
{AFFILIATE_LINK}

Interesse? Ich schicke dir gerne Werbematerialien + kostenlosen Demo-Zugang.

Viele Grüße,
Rudolf Sarkany
SuperMegaBot — aiitec GmbH
https://supermegabot-production.up.railway.app"""

def _followup_body(name: str) -> str:
    return f"""Hallo {name},

kurze Nachfrage zu meiner Affiliate-Anfrage von letzter Woche.

Falls du SuperMegaBot selbst testen möchtest, bevor du es empfiehlst — ich gebe dir 30 Tage kostenlos.

Dein Affiliate-Link: {AFFILIATE_LINK}
(30% auf jede Zahlung, monatlich wiederkehrend)

Viele Grüße,
Rudolf Sarkany"""

# ── Lead finding via DuckDuckGo ───────────────────────────────────────────────
SEARCH_QUERIES = [
    "shopify blog deutschland email kontakt",
    "shopify österreich blogger newsletter",
    "amazon fba youtube deutschland kanal",
    "e-commerce podcast deutsch kontakt",
    "online shop berater deutschland email",
    "shopify agentur österreich schweiz",
    "dropshipping kurs deutsch affiliate",
    "woocommerce blog deutschland",
    "e-commerce newsletter deutsch abonnieren",
    "digital marketing agentur shopify dach",
    "shopify experte freelancer email",
    "ecommerce consultant deutschland xing",
]

# Manually curated seed targets (high-confidence, real niches)
SEED_TARGETS = [
    {"name": "Shopify Insider", "email": "info@shopify-insider.de",
     "platform": "shopify-insider.de", "category": "blog"},
    {"name": "E-Commerce Insights", "email": "kontakt@ecommerce-insights.de",
     "platform": "ecommerce-insights.de", "category": "blog"},
    {"name": "Online-Haendler-News", "email": "redaktion@onlinehaendler-news.de",
     "platform": "onlinehaendler-news.de", "category": "news"},
    {"name": "Handelskraft Redaktion", "email": "redaktion@handelskraft.de",
     "platform": "handelskraft.de", "category": "blog"},
    {"name": "Shop Usability Award", "email": "info@shop-usability-award.de",
     "platform": "shop-usability-award.de", "category": "award"},
    {"name": "Kassenzone Podcast", "email": "info@kassenzone.de",
     "platform": "kassenzone.de", "category": "podcast"},
    {"name": "OMR Redaktion", "email": "redaktion@omr.com",
     "platform": "omr.com", "category": "media"},
    {"name": "Saupe Communication", "email": "info@saupe-communication.com",
     "platform": "saupe-communication.com", "category": "agency"},
    {"name": "Uptain GmbH", "email": "hello@uptain.de",
     "platform": "uptain.de", "category": "saas"},
    {"name": "Trusted Shops Partner", "email": "partner@trustedshops.de",
     "platform": "trustedshops.de", "category": "platform"},
    {"name": "EHI Retail Institute", "email": "info@ehi.org",
     "platform": "ehi.org", "category": "institute"},
    {"name": "Shopbetreiber Blog", "email": "info@shopbetreiber-blog.de",
     "platform": "shopbetreiber-blog.de", "category": "blog"},
    {"name": "Afterbuy Partner", "email": "partner@afterbuy.de",
     "platform": "afterbuy.de", "category": "platform"},
    {"name": "Billbee Partner", "email": "partner@billbee.io",
     "platform": "billbee.io", "category": "saas"},
    {"name": "Shopware Partner", "email": "partner@shopware.com",
     "platform": "shopware.com", "category": "platform"},
    {"name": "Elopage Partner", "email": "partner@elopage.com",
     "platform": "elopage.com", "category": "platform"},
    {"name": "Digistore24 Blog", "email": "affiliates@digistore24.com",
     "platform": "digistore24.com", "category": "platform"},
    {"name": "Copecart Partner", "email": "partner@copecart.com",
     "platform": "copecart.com", "category": "platform"},
    {"name": "Klick-Tipp Affiliates", "email": "affiliate@klick-tipp.com",
     "platform": "klick-tipp.com", "category": "saas"},
    {"name": "Digicoach Austria", "email": "kontakt@digicoach.at",
     "platform": "digicoach.at", "category": "coach"},
    {"name": "Online Business Austria", "email": "office@onlinebusiness.at",
     "platform": "onlinebusiness.at", "category": "blog"},
    {"name": "Shopify Schweiz", "email": "info@shopify-schweiz.ch",
     "platform": "shopify-schweiz.ch", "category": "blog"},
    {"name": "FBA Millionaires DE", "email": "kontakt@fba-millionaires.de",
     "platform": "fba-millionaires.de", "category": "course"},
    {"name": "Dropshipping Profi", "email": "info@dropshipping-profi.de",
     "platform": "dropshipping-profi.de", "category": "blog"},
    {"name": "E-Commerce Germany", "email": "info@ecommercegermany.com",
     "platform": "ecommercegermany.com", "category": "media"},
    {"name": "JTL Software Partner", "email": "partner@jtl-software.de",
     "platform": "jtl-software.de", "category": "platform"},
    {"name": "Xentral Partner", "email": "partner@xentral.com",
     "platform": "xentral.com", "category": "saas"},
    {"name": "Plentymarkets Partner", "email": "partner@plentymarkets.com",
     "platform": "plentymarkets.com", "category": "platform"},
    {"name": "Wix Partner DACH", "email": "partner@wix.com",
     "platform": "wix.com", "category": "platform"},
    {"name": "Ecwid Partner", "email": "partner@ecwid.com",
     "platform": "ecwid.com", "category": "platform"},
]

async def find_affiliate_targets(limit: int = 50) -> List[Dict]:
    """Kombiniert Seed-Targets + DuckDuckGo-Suche nach Affiliates."""
    targets = list(SEED_TARGETS)

    async with aiohttp.ClientSession(
        headers={"User-Agent": "Mozilla/5.0 SuperMegaBot/2.8"},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as session:
        for query in random.sample(SEARCH_QUERIES, min(5, len(SEARCH_QUERIES))):
            try:
                encoded = urllib.parse.quote(query)
                url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1"
                async with session.get(url) as r:
                    if r.status != 200:
                        continue
                    data = await r.json(content_type=None)
                    for topic in data.get("RelatedTopics", [])[:5]:
                        if not isinstance(topic, dict):
                            continue
                        first_url = topic.get("FirstURL", "")
                        text = topic.get("Text", "")
                        if first_url and text:
                            domain = urllib.parse.urlparse(first_url).netloc
                            if domain and "." in domain:
                                targets.append({
                                    "name": domain.replace("www.", "").split(".")[0].title(),
                                    "email": f"info@{domain.replace('www.','')}",
                                    "platform": domain,
                                    "category": "web",
                                    "url": first_url,
                                })
                await asyncio.sleep(0.5)
            except Exception as e:
                log.debug("DDG search error: %s", e)

    # Deduplizieren nach Email
    seen_emails: set = set()
    unique = []
    for t in targets:
        email = t.get("email", "").lower().strip()
        if email and email not in seen_emails:
            seen_emails.add(email)
            unique.append(t)

    return unique[:limit]

async def send_affiliate_pitch(email: str, name: str, platform: str,
                               stage: int = 1) -> bool:
    if not name or str(name).strip() in ("None", "none", "null", "", "N/A"):
        log.warning("Affiliate-Pitch abgebrochen — kein Name für %s", email)
        return False
    """Sendet personalisierten Affiliate-Pitch oder Follow-up."""
    with _db() as conn:
        already = conn.execute(
            "SELECT id FROM sent WHERE email=? AND stage=?", (email, stage)
        ).fetchone()
        if already:
            log.debug("Bereits gesendet (stage %d): %s", stage, email)
            return False

    if stage == 1:
        subject = _pitch_subject(name)
        body    = _pitch_body(name, platform)
    else:
        subject = f"Kurze Nachfrage — Affiliate-Partnerschaft SuperMegaBot"
        body    = _followup_body(name)

    ok, smtp_user = _send_email(email, subject, body)
    if ok:
        with _db() as conn:
            target_row = conn.execute(
                "SELECT id FROM targets WHERE email=?", (email,)
            ).fetchone()
            target_id = target_row["id"] if target_row else 0
            conn.execute(
                "INSERT INTO sent (target_id, email, smtp_user, sent_at, stage) VALUES (?,?,?,?,?)",
                (target_id, email, smtp_user, datetime.now(timezone.utc).isoformat(), stage),
            )
        log.info("Affiliate-Pitch gesendet: %s (%s) via %s", name, email, smtp_user)
    return ok

async def run_affiliate_campaign(limit: int = DAILY_AFFILIATE_LIMIT) -> Dict:
    """Hauptfunktion: Findet Affiliates und sendet sofort Pitches."""
    from modules.agent_coordinator import run as coord_run
    async with coord_run("affiliate_campaign", "affiliate_recruiter", ttl=7200, reuse_result_age=3600) as ctx:
        if ctx.already_running:
            log.info("Affiliate Campaign läuft bereits — übersprungen")
            return ctx.last_result.get("result", {}) if ctx.last_result else {}
        result = await _run_affiliate_campaign_inner(limit)
        ctx.result = result
        return result


async def _run_affiliate_campaign_inner(limit: int = DAILY_AFFILIATE_LIMIT) -> Dict:
    log.info("Affiliate-Recruiter startet — Ziel: %d Pitches", limit)

    # Targets finden
    targets = await find_affiliate_targets(limit=limit * 2)
    log.info("  %d potenzielle Affiliates gefunden", len(targets))

    # In DB speichern
    with _db() as conn:
        for t in targets:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO targets (name, email, platform, url, category, found_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (t["name"], t.get("email",""), t.get("platform",""),
                     t.get("url",""), t.get("category",""), time.time()),
                )
            except Exception:
                pass

    # Pitches senden
    sent = 0
    skipped = 0
    for t in targets:
        if sent >= limit:
            break
        email = t.get("email", "").strip()
        name  = t.get("name", "Partner")
        platform = t.get("platform", "Ihrer Plattform")
        if not email or "@" not in email:
            skipped += 1
            continue
        ok = await send_affiliate_pitch(email, name, platform, stage=1)
        if ok:
            sent += 1
        else:
            skipped += 1
        await asyncio.sleep(random.uniform(2, 5))

    summary = {
        "status":  "done",
        "sent":    sent,
        "skipped": skipped,
        "targets": len(targets),
        "affiliate_link": AFFILIATE_LINK,
    }
    log.info("Affiliate-Kampagne abgeschlossen: %d gesendet / %d gesamt", sent, len(targets))

    # Telegram-Bericht
    try:
        tg_token = _e("TELEGRAM_BOT_TOKEN")
        tg_chat  = _e("TELEGRAM_CHAT_ID")
        if tg_token and tg_chat:
            msg = (
                f"🤝 <b>Affiliate Recruiter</b>\n"
                f"✅ {sent} Pitches gesendet\n"
                f"🎯 Provision: 30% Lifetime (€15-90/Kunde/Monat)\n"
                f"🔗 Link: {AFFILIATE_LINK}"
            )
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat, "text": msg, "parse_mode": "HTML"},
                    timeout=aiohttp.ClientTimeout(total=8),
                )
    except Exception as e:
        log.debug("Telegram error: %s", e)

    return summary

async def run_followups() -> Dict:
    """Sendet Follow-up-Emails an alle die vor 7 Tagen Pitch erhalten haben."""
    cutoff = time.time() - 7 * 86400
    with _db() as conn:
        due = conn.execute(
            "SELECT t.name, t.email, t.platform FROM targets t "
            "JOIN sent s ON s.target_id=t.id "
            "WHERE s.stage=1 AND s.target_id NOT IN "
            "  (SELECT DISTINCT target_id FROM sent WHERE stage=2) "
            "AND t.found_at < ?",
            (cutoff,),
        ).fetchall()

    sent = 0
    for row in due:
        ok = await send_affiliate_pitch(row["email"], row["name"], row["platform"], stage=2)
        if ok:
            sent += 1
        await asyncio.sleep(random.uniform(3, 6))

    return {"status": "done", "followups_sent": sent}

def get_stats() -> Dict:
    with _db() as conn:
        total_targets = conn.execute("SELECT COUNT(*) FROM targets").fetchone()[0]
        total_sent    = conn.execute("SELECT COUNT(*) FROM sent WHERE stage=1").fetchone()[0]
        followups     = conn.execute("SELECT COUNT(*) FROM sent WHERE stage=2").fetchone()[0]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_sent    = conn.execute(
            "SELECT COUNT(*) FROM sent WHERE sent_at LIKE ?", (f"{today}%",)
        ).fetchone()[0]
        responses     = conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
    return {
        "total_targets": total_targets,
        "pitches_sent":  total_sent,
        "followups_sent": followups,
        "today_sent":    today_sent,
        "responses":     responses,
        "affiliate_link": AFFILIATE_LINK,
        "commission":    "30% Lifetime",
        "potential_mrr": f"€{total_sent * 0.02 * 49:.0f}-€{total_sent * 0.02 * 299:.0f}/Monat",
    }
