"""
Lead Capture Machine — baut die E-Mail-Liste von 0 auf 500+ Subscriber.
=======================================================================
Täglich aufrufen: run_lead_capture_cycle()

Kanäle:
  - Reddit (Shopify/E-Commerce-Threads)
  - ProductHunt neue Launches
  - Lead-Magnet Email (Shopify Automation Guide 2026)
  - Klaviyo + Mailchimp Sync
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

log = logging.getLogger("LeadCaptureMachine")

_DB = Path(__file__).parent.parent / "data" / "lead_capture.db"

KLAVIYO_KEY       = os.getenv("KLAVIYO_API_KEY", "")
MC_KEY            = os.getenv("MAILCHIMP_API_KEY", "")
MC_LIST_ID        = os.getenv("MAILCHIMP_LIST_ID", "")
MC_SERVER         = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")

LEAD_MAGNET_TITLE = "Shopify Automation Guide 2026"
LEAD_MAGNET_TEXT  = """
SHOPIFY AUTOMATION GUIDE 2026
10 Schritte zum vollautomatisierten Online-Shop
================================================

Schritt 1: Produktrecherche automatisieren
------------------------------------------
Nutze Tools wie AliExpress Trending, Google Trends und TikTok Shop, um täglich
neue Bestseller zu identifizieren. Importiere sie per API direkt in deinen Shopify-Shop —
ohne manuelle Arbeit.

Schritt 2: Produktbeschreibungen mit KI
---------------------------------------
ChatGPT/Claude generiert SEO-optimierte Produkttexte in Sekunden.
Erstelle Templates pro Kategorie und lass die KI automatisch variieren.
Ergebnis: 100 Produkte/Tag statt 5.

Schritt 3: Preisoptimierung mit Dynamic Pricing
-------------------------------------------------
Automatische Preisanpassung basierend auf:
- Wettbewerb (eBay, Amazon, Google Shopping)
- Lagermenge (wenig Bestand = höherer Preis)
- Tageszeit (Abends höhere Conversion = leicht höhere Preise)

Schritt 4: E-Mail-Marketing mit Klaviyo
----------------------------------------
5 Flows die du JETZT einrichten musst:
1. Welcome Series (5 Emails über 7 Tage)
2. Abandoned Cart Recovery (1h, 24h, 72h)
3. Post-Purchase Upsell (Tag 3, Tag 14)
4. Win-Back (nach 90 Tagen Inaktivität)
5. VIP-Programm (Top 10% Käufer)

Schritt 5: Social Media auf Autopilot
--------------------------------------
Täglich automatisch posten auf:
- Facebook Page (Produkt-Posts + Blog-Artikel)
- Instagram (Reels aus Produktfotos)
- Pinterest (Produkt-Pins mit Preis)
- TikTok Shop (Video-Clips)
Werkzeug: Buffer, Hootsuite oder eigene API-Automation.

Schritt 6: SEO-Content-Maschine
---------------------------------
3 Blog-Artikel pro Woche, KI-generiert, auf Keywords optimiert:
- "Bestes [Produkt] 2026 Test"
- "[Produkt] kaufen Deutschland"
- "[Produkt] Erfahrungen"
Automatisch veröffentlicht, automatisch bei Google indexiert.

Schritt 7: Facebook & Instagram Ads skalieren
-----------------------------------------------
ROAS-basierte Auto-Skalierung:
- ROAS > 3: Budget +25% alle 3 Tage
- ROAS > 5: Lookalike Audience erstellen
- ROAS < 1: Anzeige pausieren nach €20 Ausgaben

Schritt 8: Kundensupport mit KI
---------------------------------
ChatGPT beantwortet 80% aller Anfragen automatisch:
- Lieferzeiten, Rücksendungen, Produktfragen
- Integration via Gorgias oder Tidio
- Eskalation nur bei komplexen Fällen

Schritt 9: Upsell & Cross-Sell-Automation
------------------------------------------
- Post-Purchase: "Kunden kauften auch..."
- Bundles: 3 Produkte = 15% Rabatt
- After 14 Tage: "Bewertung + 5€ Gutschein"
- After 30 Tage: "VIP-Angebot für treue Kunden"

Schritt 10: Analytics & Reporting
-----------------------------------
Täglich automatisch per Telegram:
- Umsatz (heute vs. gestern vs. letzte Woche)
- Top-Produkte nach Revenue
- Conversion Rate (Ziel: >2%)
- Email Open Rate (Ziel: >20%)
- ROAS aller Kampagnen

Mit diesen 10 Schritten läuft dein Shop auf Autopilot.
Mehr Tools & Automation: https://ineedit.com.co

© 2026 AiiteC / SuperMegaBot
"""


# ── DB ────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            email       TEXT PRIMARY KEY,
            name        TEXT DEFAULT '',
            source      TEXT DEFAULT '',
            klaviyo     INTEGER DEFAULT 0,
            mailchimp   INTEGER DEFAULT 0,
            magnet_sent INTEGER DEFAULT 0,
            created_at  REAL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            date        TEXT PRIMARY KEY,
            new_leads   INTEGER DEFAULT 0,
            emails_sent INTEGER DEFAULT 0,
            kl_added    INTEGER DEFAULT 0,
            mc_added    INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def _save_lead(email: str, name: str = "", source: str = "") -> bool:
    """Returns True if new lead."""
    try:
        with _db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO leads (email, name, source, created_at) VALUES (?,?,?,?)",
                (email.lower().strip(), name[:100], source[:50], time.time())
            )
            conn.commit()
            return conn.total_changes > 0
    except Exception as e:
        log.warning("_save_lead: %s", e)
        return False


def _unsent_leads(limit: int = 50) -> list[dict]:
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT email, name FROM leads WHERE magnet_sent=0 LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []


def _mark_sent(email: str) -> None:
    try:
        with _db() as conn:
            conn.execute("UPDATE leads SET magnet_sent=1 WHERE email=?", (email,))
            conn.commit()
    except Exception:
        pass


def _mark_klaviyo(email: str) -> None:
    try:
        with _db() as conn:
            conn.execute("UPDATE leads SET klaviyo=1 WHERE email=?", (email,))
            conn.commit()
    except Exception:
        pass


def _mark_mailchimp(email: str) -> None:
    try:
        with _db() as conn:
            conn.execute("UPDATE leads SET mailchimp=1 WHERE email=?", (email,))
            conn.commit()
    except Exception:
        pass


# ── Klaviyo ───────────────────────────────────────────────────────────────────

async def add_lead_to_klaviyo(email: str, name: str = "", source: str = "") -> bool:
    if not KLAVIYO_KEY:
        return False
    try:
        parts = name.split(" ", 1)
        payload = {
            "data": {
                "type": "profile",
                "attributes": {
                    "email": email,
                    "first_name": parts[0] if parts else "",
                    "last_name": parts[1] if len(parts) > 1 else "",
                    "properties": {"source": source, "lead_magnet": LEAD_MAGNET_TITLE},
                }
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://a.klaviyo.com/api/profiles/",
                headers={
                    "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
                    "revision": "2024-02-15",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as r:
                ok = r.status in (200, 201, 409)
                if ok:
                    _mark_klaviyo(email)
                else:
                    body = await r.text()
                    log.warning("Klaviyo add_profile %s: %s %s", email, r.status, body[:200])
                return ok
    except Exception as e:
        log.warning("add_lead_to_klaviyo: %s", e)
        return False


# ── Mailchimp ─────────────────────────────────────────────────────────────────

async def add_lead_to_mailchimp(email: str, name: str = "", source: str = "") -> bool:
    if not MC_KEY or not MC_LIST_ID:
        return False
    try:
        parts = name.split(" ", 1)
        auth = base64.b64encode(f"user:{MC_KEY}".encode()).decode()
        payload = {
            "email_address": email,
            "status": "subscribed",
            "merge_fields": {
                "FNAME": parts[0] if parts else "",
                "LNAME": parts[1] if len(parts) > 1 else "",
            },
            "tags": [source, "lead-magnet-2026"],
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://{MC_SERVER}.api.mailchimp.com/3.0/lists/{MC_LIST_ID}/members",
                headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
                json=payload,
            ) as r:
                ok = r.status in (200, 201)
                if ok:
                    _mark_mailchimp(email)
                elif r.status == 400:
                    body = await r.json()
                    if body.get("title") == "Member Exists":
                        _mark_mailchimp(email)
                        ok = True
                return ok
    except Exception as e:
        log.warning("add_lead_to_mailchimp: %s", e)
        return False


# ── Lead Magnet Email ─────────────────────────────────────────────────────────

async def send_lead_magnet_email(email: str, name: str = "") -> bool:
    try:
        from modules.smtp_email import send_email
        first = name.split()[0] if name else "Hi"
        html = f"""
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#222;">
<h2 style="color:#0066cc;">🎁 Dein Shopify Automation Guide 2026 ist da!</h2>
<p>Hey {first},</p>
<p>danke für dein Interesse! Hier ist dein kostenloser Guide:</p>
<div style="background:#f5f5f5;padding:20px;border-radius:8px;white-space:pre-wrap;font-size:13px;line-height:1.6;">{LEAD_MAGNET_TEXT.strip()}</div>
<br>
<p><strong>Bonus:</strong> Teste SuperMegaBot 14 Tage kostenlos →
<a href="https://ineedit.com.co" style="color:#0066cc;">ineedit.com.co</a></p>
<p>Bis bald,<br>Rudolf & das AiiteC-Team</p>
<hr style="border:none;border-top:1px solid #eee;">
<p style="font-size:11px;color:#999;">AiiteC | <a href="https://ineedit.com.co/unsubscribe">Abmelden</a></p>
</body></html>"""
        result = await send_email(email, f"📚 {LEAD_MAGNET_TITLE} — Dein kostenloses Guide", html)
        if result.get("ok"):
            _mark_sent(email)
            return True
        return False
    except Exception as e:
        log.warning("send_lead_magnet_email %s: %s", email, e)
        return False


# ── Reddit Lead Scraper ───────────────────────────────────────────────────────

async def scrape_leads_from_reddit() -> list[dict]:
    """Holt Reddit-User aus Shopify/E-Commerce-Posts und sucht nach Emails in Profilen."""
    leads: list[dict] = []
    subreddits = ["shopify", "ecommerce", "Entrepreneur", "dropshipping", "WorkOnline"]
    email_re = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]{2,6}")

    headers = {"User-Agent": "SuperMegaBot/2.8 LeadCapture (research only)"}
    try:
        async with aiohttp.ClientSession(headers=headers) as s:
            for sub in subreddits[:3]:
                url = f"https://www.reddit.com/r/{sub}/new.json?limit=25"
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status != 200:
                        continue
                    data = await r.json()
                    posts = data.get("data", {}).get("children", [])
                    for p in posts:
                        post = p.get("data", {})
                        text = f"{post.get('selftext','')} {post.get('title','')}"
                        emails = email_re.findall(text)
                        author = post.get("author", "")
                        for em in emails:
                            if "reddit" not in em and "example" not in em:
                                is_new = _save_lead(em, author, f"reddit_{sub}")
                                if is_new:
                                    leads.append({"email": em, "name": author, "source": f"reddit_{sub}"})
                await asyncio.sleep(1)
    except Exception as e:
        log.warning("scrape_leads_from_reddit: %s", e)

    log.info("Reddit: %d neue Leads", len(leads))
    return leads


# ── ProductHunt Lead Scraper ──────────────────────────────────────────────────

async def scrape_leads_from_producthunt() -> list[dict]:
    """Holt neue E-Commerce/SaaS Launches von ProductHunt."""
    leads: list[dict] = []
    email_re = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]{2,6}")

    try:
        async with aiohttp.ClientSession(
            headers={"User-Agent": "SuperMegaBot/2.8 LeadCapture"}
        ) as s:
            async with s.get(
                "https://www.producthunt.com/feed",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    text = await r.text()
                    emails = email_re.findall(text)
                    for em in set(emails):
                        if not any(x in em for x in ["producthunt", "example", "noreply"]):
                            is_new = _save_lead(em, "", "producthunt")
                            if is_new:
                                leads.append({"email": em, "name": "", "source": "producthunt"})
    except Exception as e:
        log.warning("scrape_leads_from_producthunt: %s", e)

    log.info("ProductHunt: %d neue Leads", len(leads))
    return leads


# ── Hauptzyklus ───────────────────────────────────────────────────────────────

async def run_lead_capture_cycle() -> dict:
    """Täglich aufrufen. Scrapet Leads, fügt zu CRMs hinzu, sendet Lead-Magnet."""
    log.info("Lead Capture Cycle startet...")
    result = {
        "new_leads": 0, "kl_added": 0, "mc_added": 0,
        "emails_sent": 0, "errors": []
    }

    # 1. Leads scrapen
    try:
        reddit_leads = await scrape_leads_from_reddit()
        ph_leads     = await scrape_leads_from_producthunt()
        all_new = reddit_leads + ph_leads
        result["new_leads"] = len(all_new)
        log.info("  %d neue Leads gesammelt", len(all_new))
    except Exception as e:
        result["errors"].append(f"scrape: {e}")
        all_new = []

    # 2. Leads zu Klaviyo + Mailchimp hinzufügen
    for lead in all_new:
        em, nm, src = lead["email"], lead.get("name",""), lead.get("source","")
        if await add_lead_to_klaviyo(em, nm, src):
            result["kl_added"] += 1
        if await add_lead_to_mailchimp(em, nm, src):
            result["mc_added"] += 1
        await asyncio.sleep(0.3)

    # 3. Lead-Magnet an alle noch unversorgten Leads senden (max 50/Zyklus)
    unsent = _unsent_leads(50)
    for lead in unsent:
        if await send_lead_magnet_email(lead["email"], lead.get("name","")):
            result["emails_sent"] += 1
        await asyncio.sleep(0.5)

    # Stats in DB
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with _db() as conn:
            conn.execute(
                """INSERT INTO daily_stats (date, new_leads, emails_sent, kl_added, mc_added)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(date) DO UPDATE SET
                     new_leads=new_leads+excluded.new_leads,
                     emails_sent=emails_sent+excluded.emails_sent,
                     kl_added=kl_added+excluded.kl_added,
                     mc_added=mc_added+excluded.mc_added""",
                (today, result["new_leads"], result["emails_sent"],
                 result["kl_added"], result["mc_added"])
            )
            conn.commit()
    except Exception:
        pass

    log.info("Lead Capture fertig: %s", result)
    return result


def get_stats() -> dict:
    """Zeigt gesammelte Leads, Conversion-Rate und letzte 7 Tage."""
    try:
        with _db() as conn:
            total   = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            sent    = conn.execute("SELECT COUNT(*) FROM leads WHERE magnet_sent=1").fetchone()[0]
            kl_ok   = conn.execute("SELECT COUNT(*) FROM leads WHERE klaviyo=1").fetchone()[0]
            mc_ok   = conn.execute("SELECT COUNT(*) FROM leads WHERE mailchimp=1").fetchone()[0]
            recent  = conn.execute(
                "SELECT date, new_leads, emails_sent, kl_added, mc_added FROM daily_stats ORDER BY date DESC LIMIT 7"
            ).fetchall()
            return {
                "total_leads": total,
                "magnet_sent": sent,
                "klaviyo_added": kl_ok,
                "mailchimp_added": mc_ok,
                "magnet_open_rate": f"{sent/total*100:.1f}%" if total else "0%",
                "last_7_days": [dict(r) for r in recent],
            }
    except Exception as e:
        return {"error": str(e)}
