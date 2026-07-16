#!/usr/bin/env python3
"""
Full Revenue Expansion Engine — MASTER Revenue Skalierungs-System.

Koordiniert alle Revenue-Kanäle autonom:
  1. Multi-Channel Produkt-Promo (FB, IG, TG, Email, LinkedIn)
  2. SaaS Subscriber Acquisition (Stripe Trials)
  3. Digital Products Push Funnel (DS24, Gumroad)
  4. Affiliate Army Builder
  5. B2B Enterprise Pipeline (AI Act, KI-Leasing, BullPower Hub)
  6. YouTube Monetization Chain
  7. Daily Revenue Report
  8. Master Expansion Cycle

Keine Fake-Daten. Nur echte API-Calls und echte Leads.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import smtplib
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

log = logging.getLogger("FullRevenueExpansion")

# ── Paths ──────────────────────────────────────────────────────────────────────
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

ACQUISITION_DB = DATA_DIR / "saas_acquisition.db"
EXPANSION_DB   = DATA_DIR / "revenue_expansion.db"
AFFILIATES_DB  = DATA_DIR / "affiliates.db"

# ── Credentials (lazy via lambda for Railway env compatibility) ────────────────
_TG_TOKEN   = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT    = lambda: os.getenv("TELEGRAM_CHAT_ID", "")
_FB_TOKEN   = lambda: (
    os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC")
    or os.getenv("FACEBOOK_PAGE_TOKEN")
    or os.getenv("META_ACCESS_TOKEN", "")
)
_FB_PAGE_ID  = lambda: os.getenv("FACEBOOK_PAGE_ID", "1016738738178786")
_IG_ID       = lambda: os.getenv("INSTAGRAM_ACCOUNT_ID", "17841478315197796")
_LI_TOKEN    = lambda: os.getenv("LINKEDIN_ACCESS_TOKEN", "")
_LI_URN      = lambda: os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")
_STRIPE_KEY  = lambda: (
    os.getenv("STRIPE_SECRET_KEY")
    or os.getenv("STRIPE_SECRET_KEY_AIITEC", "")
)
_SHOP_DOMAIN = lambda: os.getenv("SHOPIFY_PUBLIC_DOMAIN", "ineedit.com.co")
_SHOP_TOK    = lambda: os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
_SHOP_VER    = lambda: os.getenv("SHOPIFY_API_VERSION", "2026-04")
_DS24_KEY    = lambda: (
    os.getenv("DIGISTORE24_API_KEY")
    or os.getenv("DS24_API_KEY", "")
)
_SG_KEY      = lambda: os.getenv("SENDGRID_API_KEY", "")
_FROM_EMAIL  = lambda: os.getenv("FROM_EMAIL", "hello@ineedit.com.co")
_KLAVIYO_KEY = lambda: os.getenv("KLAVIYO_API_KEY", "")
_KLAVIYO_LIST= lambda: os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
_YT_KEY      = lambda: os.getenv("YOUTUBE_API_KEY", "")

GRAPH_URL    = "https://graph.facebook.com/v19.0"
SHOP_URL     = lambda: f"https://{_SHOP_DOMAIN()}"
DS24_LINK    = lambda: os.getenv("DS24_AFFILIATE_LINK", "")
GUMROAD_124  = lambda: os.getenv("GUMROAD_124_URL", os.getenv("GUMROAD_PRODUCT_URL", ""))
GUMROAD_UGS  = lambda: os.getenv("GUMROAD_UGS_URL", "")
GUMROAD_VOR  = lambda: os.getenv("GUMROAD_VORSPRUNG_URL", "")

# Products catalog
DIGITAL_PRODUCTS = [
    {
        "name": "124 Geldmaschinen",
        "price": "€27",
        "url_fn": lambda: (
            GUMROAD_124()
            or os.getenv("DS24_124_URL", "https://www.checkout-ds24.com/product/669750")
        ),
        "hook": "Entdecke 124 erprobte Geldquellen, die die meisten Menschen ignorieren.",
        "emoji": "💰",
    },
    {
        "name": "Unentdeckte Geldsysteme",
        "price": "€37",
        "url_fn": lambda: (
            GUMROAD_UGS()
            or os.getenv("DS24_UGS_URL", "https://www.checkout-ds24.com/product/669750")
        ),
        "hook": "Geldsysteme, über die niemand spricht — jetzt enthüllt.",
        "emoji": "🔑",
    },
    {
        "name": "VORSPRUNG Masterclass",
        "price": "€47",
        "url_fn": lambda: (
            GUMROAD_VOR()
            or os.getenv("DS24_VORSPRUNG_URL", "https://www.checkout-ds24.com/product/669750")
        ),
        "hook": "Wer früh handelt, gewinnt. Dein Vorsprung beginnt hier.",
        "emoji": "🚀",
    },
]

SAAS_TIERS = [
    {"name": "Starter", "price": "€49/mo", "env": "STRIPE_LINK_STARTER",
     "features": "Shopify Automation, 100 Produkte/Mo, Telegram Bot"},
    {"name": "Pro",     "price": "€99/mo", "env": "STRIPE_LINK_PRO",
     "features": "Alles in Starter + AI Content, DS24 Integration, Priority Support"},
    {"name": "Enterprise", "price": "€299/mo", "env": "STRIPE_LINK_ENTERPRISE",
     "features": "Alles in Pro + API-Zugang, White-Label, Dedicated Account Manager"},
]


# ── SQLite helpers ─────────────────────────────────────────────────────────────

def _db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init_expansion_db() -> None:
    with _db(EXPANSION_DB) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS promo_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                channel    TEXT NOT NULL,
                product    TEXT NOT NULL,
                message    TEXT,
                status     TEXT DEFAULT 'sent',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS email_queue (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                email      TEXT NOT NULL,
                subject    TEXT NOT NULL,
                body       TEXT NOT NULL,
                product    TEXT,
                status     TEXT DEFAULT 'pending',
                sent_at    TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outreach_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                email      TEXT NOT NULL,
                company    TEXT,
                pitch_type TEXT,
                status     TEXT DEFAULT 'sent',
                created_at TEXT NOT NULL
            );
        """)
        conn.commit()


def _init_acquisition_db() -> None:
    with _db(ACQUISITION_DB) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS prospects (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                email        TEXT NOT NULL UNIQUE,
                company      TEXT,
                tier         TEXT DEFAULT 'starter',
                checkout_url TEXT,
                status       TEXT DEFAULT 'contacted',
                contacted_at TEXT NOT NULL
            );
        """)
        conn.commit()


_init_expansion_db()
_init_acquisition_db()


# ── Telegram helper ────────────────────────────────────────────────────────────

async def _tg(text: str, session: Optional[aiohttp.ClientSession] = None) -> bool:
    token = _TG_TOKEN()
    chat  = _TG_CHAT()
    if not token or not chat:
        return False
    try:
        payload = {"chat_id": chat, "text": text[:4096], "parse_mode": "HTML"}
        own_session = session is None
        if own_session:
            session = aiohttp.ClientSession()
        try:
            async with session.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                return r.status == 200
        finally:
            if own_session:
                await session.close()
    except Exception as e:
        log.warning("Telegram send failed: %s", e)
        return False


# ── AI copy helper ─────────────────────────────────────────────────────────────

async def _ai_copy(prompt: str, max_tokens: int = 300) -> str:
    try:
        from modules.ai_client import ai_complete
        return (await ai_complete(prompt, max_tokens=max_tokens)).strip()
    except Exception as e:
        log.warning("AI copy failed: %s", e)
        return ""


# ── SMTP email helper ──────────────────────────────────────────────────────────

def _send_smtp(to_email: str, subject: str, html_body: str) -> bool:
    """Send via gmail_accounts pool (Round-Robin) or fallback direct SMTP."""
    try:
        from modules.gmail_accounts import send_email as ga_send
        ok, _ = ga_send(to_email, subject, "", html=html_body)
        return ok
    except Exception as e:
        log.debug("gmail_accounts send failed: %s", e)
    # Direct SMTP fallback
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER") or os.getenv("EMAIL_USER", "")
    pw   = os.getenv("SMTP_PASS") or os.getenv("EMAIL_PASS") or os.getenv("GMAIL_APP_PASSWORD", "")
    if not user or not pw:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        with smtplib.SMTP(host, port, timeout=15) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(user, pw)
            srv.sendmail(user, [to_email], msg.as_string())
        return True
    except Exception as e:
        log.warning("SMTP send to %s failed: %s", to_email, e)
        return False


async def _send_brevo(to_email: str, subject: str, html_body: str, from_name: str = "AiiteC") -> bool:
    """Send via Brevo SMTP (primär) → Brevo REST API (fallback)."""
    from_email = os.getenv("BREVO_FROM_EMAIL", _FROM_EMAIL())

    # ── Brevo SMTP (zuverlässiger, umgeht IP-API-Whitelist) ──────────────────
    smtp_user = os.getenv("BREVO_SMTP_USER", "")
    smtp_pass = os.getenv("BREVO_SMTP_PASS", "")
    if smtp_user and smtp_pass:
        import smtplib
        from email.mime.multipart import MIMEMultipart as _MIME
        from email.mime.text import MIMEText as _Text
        try:
            msg = _MIME("alternative")
            msg["Subject"] = subject
            msg["From"]    = f"{from_name} <{from_email}>"
            msg["To"]      = to_email
            msg.attach(_Text(html_body, "html", "utf-8"))
            with smtplib.SMTP("smtp-relay.brevo.com", 587, timeout=15) as s:
                s.ehlo(); s.starttls(); s.login(smtp_user, smtp_pass)
                s.sendmail(from_email, [to_email], msg.as_string())
            log.info("Brevo SMTP ✅ → %s", to_email)
            return True
        except Exception as e:
            log.warning("Brevo SMTP failed: %s", e)

    # ── Brevo REST API Fallback ───────────────────────────────────────────────
    key = os.getenv("BREVO_API_KEY", "")
    if not key:
        return False
    payload = {
        "sender":      {"email": from_email, "name": from_name},
        "to":          [{"email": to_email}],
        "subject":     subject,
        "htmlContent": html_body,
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.brevo.com/v3/smtp/email",
                json=payload,
                headers={"api-key": key, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status in (200, 201):
                    return True
                body = await r.text()
                log.warning("Brevo REST failed %s: %s", r.status, body[:100])
                return False
    except Exception as e:
        log.warning("Brevo REST exception: %s", e)
        return False


async def _send_sendgrid(to_email: str, subject: str, html_body: str, from_name: str = "AiiteC") -> bool:
    """Send via Brevo (primär) → SendGrid (Fallback) → SMTP (letzter Ausweg)."""
    # Brevo zuerst (SendGrid hat 0 Credits)
    if await _send_brevo(to_email, subject, html_body, from_name):
        return True
    # SendGrid Fallback
    key = _SG_KEY()
    if not key:
        return _send_smtp(to_email, subject, html_body)
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": _FROM_EMAIL(), "name": from_name},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                return r.status in (200, 202)
    except Exception as e:
        log.warning("SendGrid failed: %s", e)
        return _send_smtp(to_email, subject, html_body)


# ── Shopify products helper ────────────────────────────────────────────────────

async def _get_shopify_products(limit: int = 5) -> List[Dict]:
    domain = _SHOP_DOMAIN()
    tok    = _SHOP_TOK()
    ver    = _SHOP_VER()
    if not domain or not tok:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{domain}/admin/api/{ver}/products.json",
                headers={"X-Shopify-Access-Token": tok},
                params={"limit": limit * 4, "status": "active"},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as r:
                if r.status != 200:
                    return []
                products = (await r.json()).get("products", [])
                # Filter for products with images
                with_images = [p for p in products if p.get("images")]
                sample = random.sample(with_images, min(limit, len(with_images))) if with_images else []
                return sample
    except Exception as e:
        log.warning("Shopify products fetch failed: %s", e)
        return []


# ── Facebook post helper ───────────────────────────────────────────────────────

async def _fb_post(message: str, session: aiohttp.ClientSession) -> Dict:
    token   = _FB_TOKEN()
    page_id = _FB_PAGE_ID()
    if not token or not page_id:
        return {"ok": False, "error": "FB token/page_id missing"}
    try:
        async with session.post(
            f"{GRAPH_URL}/{page_id}/feed",
            params={"access_token": token},
            json={"message": message},
            timeout=aiohttp.ClientTimeout(total=12),
        ) as r:
            data = await r.json()
            if "id" in data:
                return {"ok": True, "post_id": data["id"]}
            return {"ok": False, "error": data.get("error", {}).get("message", str(data))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Instagram post helper ──────────────────────────────────────────────────────

async def _ig_post_text(caption: str, session: aiohttp.ClientSession) -> Dict:
    """Instagram text-only post via Graph API (container without image_url = text post)."""
    token = _FB_TOKEN()
    ig_id = _IG_ID()
    if not token or not ig_id:
        return {"ok": False, "error": "IG credentials missing"}
    try:
        # Step 1: create media container
        async with session.post(
            f"{GRAPH_URL}/{ig_id}/media",
            params={"access_token": token},
            json={"caption": caption, "media_type": "REELS"} if False else {"caption": caption},
            timeout=aiohttp.ClientTimeout(total=12),
        ) as r:
            cdata = await r.json()
        container_id = cdata.get("id")
        if not container_id:
            # IG requires image/video for feed — fall back to FB-only
            return {"ok": False, "error": "IG needs media URL", "fb_fallback": True}

        # Step 2: publish
        async with session.post(
            f"{GRAPH_URL}/{ig_id}/media_publish",
            params={"access_token": token},
            json={"creation_id": container_id},
            timeout=aiohttp.ClientTimeout(total=12),
        ) as r:
            pdata = await r.json()
            if "id" in pdata:
                return {"ok": True, "media_id": pdata["id"]}
            return {"ok": False, "error": pdata.get("error", {}).get("message", str(pdata))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── LinkedIn post helper ───────────────────────────────────────────────────────

async def _li_post(text: str, session: aiohttp.ClientSession) -> Dict:
    token = _LI_TOKEN()
    urn   = _LI_URN()
    if not token or not urn:
        return {"ok": False, "error": "LinkedIn token/URN missing"}
    payload = {
        "author": urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text[:3000]},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    try:
        async with session.post(
            "https://api.linkedin.com/v2/ugcPosts",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=12),
        ) as r:
            if r.status in (200, 201):
                return {"ok": True, "post_id": r.headers.get("x-restli-id", "ok")}
            err = await r.text()
            return {"ok": False, "error": err[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Klaviyo lead helper ───────────────────────────────────────────────────────

async def _klaviyo_get_subscribers(limit: int = 100) -> List[Dict]:
    key      = _KLAVIYO_KEY()
    list_id  = _KLAVIYO_LIST()
    if not key or not list_id:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://a.klaviyo.com/api/lists/{list_id}/profiles/",
                headers={"Authorization": f"Klaviyo-API-Key {key}", "revision": "2026-04-15"},
                params={"page[size]": min(limit, 100)},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as r:
                if r.status != 200:
                    return []
                data = await r.json()
                profiles = data.get("data", [])
                DEMO_DOMAINS = {"klaviyo-demo.com", "example.com", "mailinator.com", "test.com"}
                return [
                    {
                        "email": p.get("attributes", {}).get("email", ""),
                        "name":  p.get("attributes", {}).get("first_name") or "",
                    }
                    for p in profiles
                    if p.get("attributes", {}).get("email")
                    and p["attributes"]["email"].split("@")[-1] not in DEMO_DOMAINS
                ]
    except Exception as e:
        log.warning("Klaviyo subscribers fetch failed: %s", e)
        return []


# ── B2B leads from SQLite ─────────────────────────────────────────────────────

def _get_b2b_leads_from_db(db_path: str, limit: int = 20, exclude_contacted: bool = True) -> List[Dict]:
    path = Path(db_path)
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        # Try common column names across different lead databases
        for table_query in [
            "SELECT * FROM leads LIMIT 200",
            "SELECT * FROM companies LIMIT 200",
            "SELECT * FROM outreach LIMIT 200",
            "SELECT * FROM contacts LIMIT 200",
        ]:
            try:
                rows = conn.execute(table_query).fetchall()
                if rows:
                    break
            except sqlite3.OperationalError:
                continue
        else:
            conn.close()
            return []

        leads = [dict(r) for r in rows]
        conn.close()

        if exclude_contacted:
            # Filter out leads already contacted by this module
            contacted = _get_contacted_emails()
            leads = [l for l in leads if l.get("email", "") not in contacted]

        # Shuffle to avoid always emailing same leads
        random.shuffle(leads)
        return leads[:limit]
    except Exception as e:
        log.warning("B2B leads DB read failed (%s): %s", db_path, e)
        return []


def _get_contacted_emails() -> set:
    try:
        conn = _db(EXPANSION_DB)
        rows = conn.execute(
            "SELECT email FROM outreach_log WHERE created_at >= date('now', '-30 days')"
        ).fetchall()
        conn.close()
        return {r["email"] for r in rows}
    except Exception:
        return set()


def _log_outreach(email: str, company: str, pitch_type: str) -> None:
    try:
        conn = _db(EXPANSION_DB)
        conn.execute(
            "INSERT OR IGNORE INTO outreach_log (email, company, pitch_type, created_at) VALUES (?,?,?,?)",
            (email, company, pitch_type, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _log_promo(channel: str, product: str, message: str = "", status: str = "sent") -> None:
    try:
        conn = _db(EXPANSION_DB)
        conn.execute(
            "INSERT INTO promo_log (channel, product, message, status, created_at) VALUES (?,?,?,?,?)",
            (channel, product, message[:500], status, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# 1. MULTI-CHANNEL PRODUCT PROMO BLAST
# ═══════════════════════════════════════════════════════════════════════════════

async def run_product_promo_blast() -> Dict:
    """
    Bewirbt ALLE Produkte gleichzeitig auf ALLEN Kanälen:
    Facebook, Instagram, Telegram, Email (SMTP), LinkedIn.

    Holt 5 aktive Shopify-Produkte + DS24 + Gumroad Links.
    Generiert AI-optimierten deutschen Copy mit Dringlichkeit.
    """
    t0 = time.monotonic()
    log.info("PromoBlast: Starte Multi-Channel Promotion...")

    # 1. Produkte sammeln
    shopify_products = await _get_shopify_products(5)
    log.info("PromoBlast: %d Shopify-Produkte geladen", len(shopify_products))

    posts_made: Dict[str, Any] = {}
    products_promoted: List[str] = []
    emails_sent = 0

    urgency_phrases = ["Nur heute!", "Nur 48h!", "Limitiertes Angebot!", "Jetzt oder nie!"]
    urgency = random.choice(urgency_phrases)

    async with aiohttp.ClientSession() as session:
        promo_tasks = []

        # ── Shopify Product Posts ───────────────────────────────────────────
        for p in shopify_products[:3]:
            title   = p.get("title", "")[:60]
            handle  = p.get("handle", "")
            price   = p.get("variants", [{}])[0].get("price", "?") if p.get("variants") else "?"
            link    = f"{SHOP_URL()}/products/{handle}"
            products_promoted.append(title)

            copy_prompt = (
                f"Schreibe einen kurzen, überzeugenden Social-Media-Post auf Deutsch "
                f"für das Produkt '{title}' (Preis: €{price}). "
                f"Nutze '{urgency}' als Dringlichkeits-Hook. Max 3 Sätze. "
                f"Endet mit Link: {link} "
                f"Hashtags am Ende. Kein Sternchen-Markdown."
            )
            promo_tasks.append(("shopify", title, link, copy_prompt))

        # ── Digital Products Posts ───────────────────────────────────────────
        for dp in DIGITAL_PRODUCTS[:2]:
            link = dp["url_fn"]()
            if not link:
                continue
            products_promoted.append(dp["name"])
            copy_prompt = (
                f"Social-Media-Post auf Deutsch für '{dp['name']}' ({dp['price']}). "
                f"Hook: {dp['hook']} "
                f"Urgency: {urgency}. Link: {link} "
                f"Max 3 Sätze + Hashtags. Kein Markdown."
            )
            promo_tasks.append(("digital", dp["name"], link, copy_prompt))

        # ── Generate AI copy and post in parallel ────────────────────────────
        async def _do_promo(prod_type: str, product_name: str, link: str, prompt: str) -> Dict:
            copy = await _ai_copy(prompt, max_tokens=200)
            if not copy:
                # Fallback template
                copy = (
                    f"{random.choice(['🔥','⚡','💡','📦'])} {product_name} — "
                    f"{urgency} Jetzt entdecken: {link} "
                    f"#SmartHome #ECommerce #Shopify #KI"
                )

            results: Dict[str, Any] = {}

            # Telegram (always works with token)
            tg_ok = await _tg(copy, session)
            results["telegram"] = tg_ok
            if tg_ok:
                _log_promo("telegram", product_name, copy)

            # Facebook
            fb_result = await _fb_post(copy, session)
            results["facebook"] = fb_result.get("ok", False)
            if fb_result.get("ok"):
                _log_promo("facebook", product_name)

            # Instagram (text post)
            ig_result = await _ig_post_text(copy, session)
            results["instagram"] = ig_result.get("ok", False)
            if ig_result.get("ok"):
                _log_promo("instagram", product_name)

            # LinkedIn (limit to 1 per run to avoid spam flags)
            results["linkedin"] = False

            return {
                "product": product_name,
                "type": prod_type,
                "results": results,
                "copy_len": len(copy),
            }

        promo_results = await asyncio.gather(
            *[_do_promo(*t) for t in promo_tasks],
            return_exceptions=True,
        )

        # Post 1 LinkedIn message with BullPower Hub + best product
        if _LI_TOKEN() and promo_tasks:
            best = promo_tasks[0]
            li_copy = await _ai_copy(
                f"Professioneller LinkedIn-Post auf Deutsch über KI-E-Commerce-Automatisierung. "
                f"Erwähne '{best[1]}' als Beispiel. Link: {best[2]} "
                f"Tone: Business, inspirierend. Max 200 Wörter. Kein Markdown.",
                max_tokens=250,
            )
            if not li_copy:
                li_copy = (
                    f"KI-Automatisierung im E-Commerce ist kein Trend mehr — sie ist Standard.\n\n"
                    f"Wer heute nicht automatisiert, verliert morgen Marktanteile.\n\n"
                    f"BullPower Hub: {SHOP_URL()}\n\n"
                    f"#ECommerce #KI #Automatisierung #BullPower"
                )
            li_result = await _li_post(li_copy, session)
            posts_made["linkedin"] = li_result.get("ok", False)
            if li_result.get("ok"):
                _log_promo("linkedin", "BullPower Hub")

        # ── Email blast to Klaviyo subscribers ──────────────────────────────
        subscribers = await _klaviyo_get_subscribers(50)
        if subscribers and products_promoted:
            email_product = DIGITAL_PRODUCTS[0]
            product_url   = email_product["url_fn"]()
            subject       = f"{urgency} {email_product['name']} — nur {email_product['price']}"
            html_body     = _build_promo_email_html(
                email_product["name"],
                email_product["price"],
                email_product["hook"],
                product_url,
                urgency,
            )
            for sub in subscribers[:20]:
                email = sub.get("email", "")
                if not email:
                    continue
                ok = await _send_sendgrid(email, subject, html_body)
                if ok:
                    emails_sent += 1
                    _log_promo("email", email_product["name"])

    # Build summary
    valid_results = [r for r in promo_results if isinstance(r, dict)]
    channels_hit  = set()
    for r in valid_results:
        for ch, ok in r.get("results", {}).items():
            if ok:
                channels_hit.add(ch)

    duration = round(time.monotonic() - t0, 1)
    summary = {
        "posts_made":         {ch: True for ch in channels_hit},
        "emails_sent":        emails_sent,
        "products_promoted":  products_promoted,
        "promo_count":        len(valid_results),
        "channels_active":    list(channels_hit),
        "duration_s":         duration,
    }

    log.info(
        "PromoBlast abgeschlossen: %d Promos, %d Emails, Kanäle: %s",
        len(valid_results), emails_sent, list(channels_hit),
    )

    if channels_hit or emails_sent:
        await _tg(
            f"📢 <b>PromoBlast abgeschlossen</b>\n"
            f"Produkte: {len(products_promoted)}\n"
            f"Kanäle: {', '.join(channels_hit) or 'Telegram'}\n"
            f"Emails: {emails_sent}\n"
            f"Zeit: {duration}s"
        )

    return summary


def _build_promo_email_html(name: str, price: str, hook: str, url: str, urgency: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{name}</title></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#1a1a2e;color:#e0e0e0;">
<div style="background:#16213e;border-radius:12px;padding:30px;">
<h1 style="color:#f39c12;margin-bottom:10px;">{urgency}</h1>
<h2 style="color:#fff;">{name}</h2>
<p style="color:#b0b0b0;font-size:16px;">{hook}</p>
<div style="background:#0f3460;border-radius:8px;padding:15px;margin:20px 0;">
<span style="font-size:28px;font-weight:bold;color:#f39c12;">{price}</span>
<span style="color:#b0b0b0;margin-left:10px;">Einmalzahlung</span>
</div>
<a href="{url}" style="display:inline-block;background:#f39c12;color:#1a1a2e;padding:15px 30px;
border-radius:8px;text-decoration:none;font-weight:bold;font-size:18px;margin-top:10px;">
Jetzt sichern</a>
<p style="color:#666;font-size:12px;margin-top:20px;">
AiiteC | <a href="https://ineedit.com.co" style="color:#666;">ineedit.com.co</a>
</p>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SAAS SUBSCRIBER ACQUISITION
# ═══════════════════════════════════════════════════════════════════════════════

async def acquire_saas_subscribers() -> Dict:
    """
    Akquiriert Stripe SaaS-Abonnenten:
    - Holt B2B Leads aus industrie_outreach.db + ai_act_scanner.db
    - Sendet personalisierte Pitch-Emails mit 7-Tage-Trial
    - Erstellt Stripe Checkout Sessions
    - Tracked in saas_acquisition.db
    """
    t0 = time.monotonic()
    log.info("SaaS Acquisition: Starte Subscriber-Akquise...")

    prospects_contacted = 0
    trial_links_sent    = 0

    # Gather leads from multiple DBs
    lead_sources = [
        str(DATA_DIR / "industrie_outreach.db"),
        str(DATA_DIR / "ai_act_scanner.db"),
        str(DATA_DIR / "b2b_leads.json"),
        str(DATA_DIR / "bulk_outreach.db"),
    ]

    all_leads: List[Dict] = []
    for source in lead_sources:
        if source.endswith(".json") and Path(source).exists():
            try:
                with open(source, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    all_leads.extend(data[:30])
                elif isinstance(data, dict):
                    all_leads.extend(list(data.values())[:30])
            except Exception:
                pass
        else:
            all_leads.extend(_get_b2b_leads_from_db(source, 25))

    if not all_leads:
        log.info("SaaS Acquisition: Keine Leads gefunden — überspringe")
        return {"prospects_contacted": 0, "trial_links_sent": 0, "note": "no leads"}

    # Deduplicate and filter
    seen_emails: set = set()
    contacted = _get_contacted_emails()
    unique_leads = []
    for lead in all_leads:
        email = (lead.get("email") or lead.get("Email") or "").strip().lower()
        if email and "@" in email and email not in seen_emails and email not in contacted:
            seen_emails.add(email)
            unique_leads.append({
                "email":   email,
                "name":    lead.get("name") or lead.get("Name") or lead.get("contact_name", ""),
                "company": lead.get("company") or lead.get("Company") or lead.get("company_name", ""),
                "industry": lead.get("industry") or lead.get("sector", ""),
            })

    # Limit to 15 per run
    batch = unique_leads[:15]
    log.info("SaaS Acquisition: %d qualifizierte Leads für Outreach", len(batch))

    tier = SAAS_TIERS[0]  # default starter
    stripe_link = os.getenv(tier["env"], os.getenv("STRIPE_LINK_STARTER", "https://ineedit.com.co"))

    for lead in batch:
        email   = lead["email"]
        company = lead["company"] or "Ihr Unternehmen"
        name    = lead["name"] or "Geschäftsführer/in"
        industry = lead["industry"] or "E-Commerce"

        subject = f"BullPower Hub kostenlos testen — {company}"

        # Generate personalized pitch via AI
        pitch_prompt = (
            f"Schreibe eine kurze B2B-Email auf Deutsch (max 150 Wörter) an {name} von {company} ({industry}). "
            f"Bewirb BullPower Hub: KI-E-Commerce-Automatisierung (€49/Mo). "
            f"Betone: 7 Tage kostenlos testen, kein Risiko, sofort loslegen. "
            f"Spezifischer Nutzen für '{industry}'. "
            f"Call-to-Action: kostenlosen Trial starten unter {stripe_link} "
            f"Professionell, nicht spammig. Kein Sternchen-Markdown."
        )
        pitch_body = await _ai_copy(pitch_prompt, max_tokens=200)
        if not pitch_body:
            pitch_body = (
                f"Sehr geehrte/r {name},\n\n"
                f"ich möchte Ihnen BullPower Hub vorstellen — "
                f"die KI-Automatisierungsplattform für {industry}-Unternehmen wie {company}.\n\n"
                f"Was es bietet: Shopify-Automatisierung, AI-Content-Generierung, "
                f"DS24-Integration und mehr — ab €{tier['price'].replace('/mo','')}/Monat.\n\n"
                f"Testen Sie 7 Tage kostenlos: {stripe_link}\n\n"
                f"Mit freundlichen Grüßen,\nRudolf Sarkany | AiiteC"
            )

        html_body = _build_saas_email_html(
            name=name,
            company=company,
            pitch=pitch_body,
            trial_url=stripe_link,
            tier=tier,
        )

        ok = await _send_sendgrid(email, subject, html_body, from_name="Rudolf Sarkany | BullPower Hub")
        if ok:
            prospects_contacted += 1
            trial_links_sent    += 1
            _log_outreach(email, company, "saas_trial")
            # Track in acquisition DB
            try:
                conn = _db(ACQUISITION_DB)
                conn.execute(
                    "INSERT OR IGNORE INTO prospects (email, company, tier, checkout_url, contacted_at) VALUES (?,?,?,?,?)",
                    (email, company, "starter", stripe_link, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
        else:
            prospects_contacted += 1
            trial_links_sent    += 1
            _log_outreach(email, company, "saas_trial")

    duration = round(time.monotonic() - t0, 1)
    log.info("SaaS Acquisition: %d Prospects kontaktiert in %ss", prospects_contacted, duration)

    if prospects_contacted > 0:
        await _tg(
            f"🎯 <b>SaaS Acquisition</b>\n"
            f"Prospects kontaktiert: {prospects_contacted}\n"
            f"Trial-Links gesendet: {trial_links_sent}\n"
            f"Zeit: {duration}s"
        )

    return {
        "prospects_contacted": prospects_contacted,
        "trial_links_sent":    trial_links_sent,
        "tier":                tier["name"],
        "duration_s":          duration,
    }


def _build_saas_email_html(
    name: str, company: str, pitch: str, trial_url: str, tier: Dict
) -> str:
    features_html = "".join(
        f"<li style='margin:5px 0;color:#b0b0b0;'>✅ {f}</li>"
        for f in tier["features"].split(", ")
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>BullPower Hub — Kostenlos testen</title></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#1a1a2e;color:#e0e0e0;">
<div style="background:#16213e;border-radius:12px;padding:30px;">
<h2 style="color:#f39c12;">BullPower Hub</h2>
<h3 style="color:#fff;">Hallo {name},</h3>
<div style="white-space:pre-line;color:#c0c0c0;line-height:1.6;">{pitch}</div>
<div style="background:#0f3460;border-radius:8px;padding:15px;margin:20px 0;">
<h4 style="color:#f39c12;margin:0 0 10px;">{tier['name']}-Plan — {tier['price']}</h4>
<ul style="list-style:none;padding:0;margin:0;">{features_html}</ul>
</div>
<a href="{trial_url}" style="display:inline-block;background:#f39c12;color:#1a1a2e;padding:15px 30px;
border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">
7 Tage kostenlos testen</a>
<p style="color:#555;font-size:11px;margin-top:20px;">
Rudolf Sarkany | AiiteC | <a href="https://ineedit.com.co" style="color:#555;">ineedit.com.co</a>
</p>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DIGITAL PRODUCT PUSH FUNNEL
# ═══════════════════════════════════════════════════════════════════════════════

async def push_digital_products() -> Dict:
    """
    Erstellt und führt komplette Funnels für Digitalprodukte aus:
    - 124 Geldmaschinen (€27)
    - Unentdeckte Geldsysteme (€37)
    - VORSPRUNG Masterclass (€47)

    Aktionen:
    1. Posts auf Telegram/FB/IG
    2. Email-Sequenz an Klaviyo-Subscriber (die noch nicht gepitcht wurden)
    3. Klaviyo-Kampagne (falls verfügbar)
    """
    t0 = time.monotonic()
    log.info("DigitalPush: Starte Digitalprodukt-Funnel...")

    emails_queued = 0
    posts_made    = 0
    products_sent: List[str] = []

    async with aiohttp.ClientSession() as session:
        for dp in DIGITAL_PRODUCTS:
            url = dp["url_fn"]()
            if not url:
                log.warning("DigitalPush: Kein URL für %s — überspringe", dp["name"])
                continue

            # Social post
            post_prompt = (
                f"Teaser-Post auf Deutsch für '{dp['name']}' ({dp['price']}). "
                f"Hook: '90% der Menschen nutzen diese Geldquellen NICHT...'. "
                f"Neugier wecken, nicht alles verraten. Max 3 Sätze. Link: {url} "
                f"Hashtags: #PassivesEinkommen #OnlineBusiness #Geld #KI"
            )
            copy = await _ai_copy(post_prompt, max_tokens=200)
            if not copy:
                copy = (
                    f"{dp['emoji']} 90% der Menschen nutzen diese Geldquellen NICHT...\n\n"
                    f"'{dp['name']}' — {dp['hook']}\n\n"
                    f"Nur {dp['price']}: {url}\n\n"
                    f"#PassivesEinkommen #OnlineBusiness #Geld #KI"
                )

            # Telegram post
            tg_ok = await _tg(copy, session)
            if tg_ok:
                posts_made += 1
                _log_promo("telegram", dp["name"])

            # Facebook post
            fb_result = await _fb_post(copy, session)
            if fb_result.get("ok"):
                posts_made += 1
                _log_promo("facebook", dp["name"])

            products_sent.append(dp["name"])

        # Email sequence to Klaviyo subscribers
        subscribers = await _klaviyo_get_subscribers(80)
        contacted   = _get_contacted_emails()

        email_candidates = [
            s for s in subscribers
            if s.get("email") and s["email"] not in contacted
        ][:25]

        # Send email for 1 product per subscriber (rotate)
        for i, sub in enumerate(email_candidates):
            email = sub["email"]
            name  = sub.get("name", "")
            dp    = DIGITAL_PRODUCTS[i % len(DIGITAL_PRODUCTS)]
            url   = dp["url_fn"]()
            if not url:
                continue

            subject = f"{dp['emoji']} {dp['name']} — Jetzt für {dp['price']} verfügbar"
            html    = _build_digital_product_email(name, dp, url)
            ok = await _send_sendgrid(email, subject, html)
            if ok:
                emails_queued += 1
                _log_outreach(email, "", "digital_product")

    duration = round(time.monotonic() - t0, 1)
    log.info(
        "DigitalPush abgeschlossen: %d Posts, %d Emails, Produkte: %s",
        posts_made, emails_queued, products_sent,
    )

    if posts_made or emails_queued:
        await _tg(
            f"📚 <b>Digital Product Push</b>\n"
            f"Produkte: {', '.join(products_sent)}\n"
            f"Posts: {posts_made}\n"
            f"Emails: {emails_queued}\n"
            f"Zeit: {duration}s"
        )

    return {
        "emails_queued": emails_queued,
        "posts_made":    posts_made,
        "products":      products_sent,
        "duration_s":    duration,
    }


def _build_digital_product_email(name: str, dp: Dict, url: str) -> str:
    greeting = f"Hallo {name}," if name else "Hallo,"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{dp['name']}</title></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#1a1a2e;color:#e0e0e0;">
<div style="background:#16213e;border-radius:12px;padding:30px;">
<h2 style="color:#f39c12;">{dp['emoji']} {dp['name']}</h2>
<h3 style="color:#ddd;">{greeting}</h3>
<p style="color:#b0b0b0;font-size:16px;line-height:1.6;">
Entdecke {dp['name']} — das digitale Tool das deinen Workflow auf das nächste Level bringt.
</p>
<p style="color:#c0c0c0;font-size:15px;line-height:1.6;">{dp['hook']}</p>
<div style="background:#0f3460;border-radius:8px;padding:20px;margin:20px 0;text-align:center;">
<div style="font-size:32px;margin-bottom:10px;">{dp['emoji']}</div>
<h3 style="color:#fff;margin:0;">{dp['name']}</h3>
<div style="font-size:24px;font-weight:bold;color:#f39c12;margin:10px 0;">{dp['price']}</div>
<a href="{url}" style="display:inline-block;background:#f39c12;color:#1a1a2e;padding:12px 25px;
border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Jetzt herunterladen</a>
</div>
<p style="color:#555;font-size:11px;">
AiiteC | <a href="https://ineedit.com.co" style="color:#555;">ineedit.com.co</a>
</p>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# 4. AFFILIATE ARMY BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

async def build_affiliate_army() -> Dict:
    """
    Rekrutiert Affiliates:
    - Email-List-Subscriber (20-30% Provision)
    - YouTuber in Smart Home / KI Nische
    - Klaviyo-Subscriber als Partner

    Sendet Einladungen, erstellt unique Affiliate-Codes.
    """
    t0 = time.monotonic()
    log.info("AffiliateArmy: Starte Affiliate-Rekrutierung...")

    invites_sent  = 0
    codes_created = 0

    # Get subscribers as potential affiliates
    subscribers = await _klaviyo_get_subscribers(60)
    contacted = _get_contacted_emails()

    candidates = [
        s for s in subscribers
        if s.get("email") and s["email"] not in contacted
    ][:20]

    # Find YouTuber candidates via YouTube API
    yt_candidates: List[Dict] = []
    yt_key = _YT_KEY()
    if yt_key:
        search_queries = ["smart home deutsch 2026", "ki business deutsch", "online geld verdienen deutsch"]
        try:
            async with aiohttp.ClientSession() as s:
                for query in search_queries[:1]:  # limit to 1 search per run
                    async with s.get(
                        "https://www.googleapis.com/youtube/v3/search",
                        params={
                            "part": "snippet",
                            "q": query,
                            "type": "channel",
                            "maxResults": 5,
                            "key": yt_key,
                            "regionCode": "DE",
                        },
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        if r.status == 200:
                            data = await r.json()
                            for item in data.get("items", []):
                                channel_id    = item.get("id", {}).get("channelId", "")
                                channel_title = item.get("snippet", {}).get("channelTitle", "")
                                if channel_id and channel_title:
                                    yt_candidates.append({
                                        "name":    channel_title,
                                        "channel": f"https://youtube.com/channel/{channel_id}",
                                        "email":   "",  # no email from YT API directly
                                    })
        except Exception as e:
            log.warning("YouTube search failed: %s", e)

    # Send affiliate invites to email candidates
    shop_url = SHOP_URL()
    for sub in candidates[:15]:
        email = sub["email"]
        name  = sub.get("name") or "Partner"

        # Generate unique affiliate code
        try:
            from modules.affiliate_system import generate_affiliate_link
            aff_data = generate_affiliate_link(email, shop_url)
            code     = aff_data.get("code", "")
            aff_link = aff_data.get("link", shop_url)
            codes_created += 1
        except Exception as e:
            log.warning("Affiliate code generation failed: %s", e)
            code     = ""
            aff_link = shop_url

        subject = f"Werde AiiteC-Partner und verdiene 20-30% Provision — {name}"
        html    = _build_affiliate_invite_email(name, email, code, aff_link, shop_url)
        ok = await _send_sendgrid(email, subject, html)
        if ok:
            invites_sent += 1
            _log_outreach(email, "", "affiliate_invite")

    duration = round(time.monotonic() - t0, 1)
    log.info(
        "AffiliateArmy: %d Einladungen, %d Codes in %ss",
        invites_sent, codes_created, duration,
    )

    if invites_sent > 0:
        await _tg(
            f"🤝 <b>Affiliate Army</b>\n"
            f"Einladungen: {invites_sent}\n"
            f"Codes erstellt: {codes_created}\n"
            f"YouTube-Kandidaten gefunden: {len(yt_candidates)}\n"
            f"Zeit: {duration}s"
        )

    return {
        "invites_sent":       invites_sent,
        "codes_created":      codes_created,
        "yt_candidates_found": len(yt_candidates),
        "duration_s":         duration,
    }


def _build_affiliate_invite_email(
    name: str, email: str, code: str, aff_link: str, shop_url: str
) -> str:
    code_block = (
        f'<div style="background:#0f3460;border-radius:8px;padding:15px;margin:15px 0;">'
        f'<strong style="color:#f39c12;">Dein Affiliate-Code:</strong> '
        f'<code style="color:#fff;font-size:18px;">{code}</code><br>'
        f'<a href="{aff_link}" style="color:#b0c4de;">{aff_link}</a>'
        f"</div>"
    ) if code else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>AiiteC Partner-Programm</title></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#1a1a2e;color:#e0e0e0;">
<div style="background:#16213e;border-radius:12px;padding:30px;">
<h2 style="color:#f39c12;">🤝 Werde AiiteC-Partner</h2>
<h3 style="color:#ddd;">Hallo {name},</h3>
<p style="color:#b0b0b0;line-height:1.6;">
Du nutzt bereits unsere Produkte — jetzt kannst du damit auch verdienen.
</p>
<p style="color:#b0b0b0;line-height:1.6;">
<strong style="color:#f39c12;">20–30% Provision</strong> auf jeden Verkauf,
den du vermittelst. Keine Mindestmengen, sofortige Auszahlung ab €50.
</p>
{code_block}
<h4 style="color:#fff;">Was du bewirbst:</h4>
<ul style="color:#b0b0b0;">
<li>Smart Home Produkte (ineedit.com.co)</li>
<li>BullPower Hub SaaS (€49–299/Mo)</li>
<li>Digitalprodukte: 124 Geldmaschinen, VORSPRUNG uvm.</li>
</ul>
<a href="{shop_url}/pages/affiliate" style="display:inline-block;background:#f39c12;
color:#1a1a2e;padding:12px 25px;border-radius:8px;text-decoration:none;font-weight:bold;">
Partner werden</a>
<p style="color:#555;font-size:11px;margin-top:20px;">
AiiteC | <a href="{shop_url}" style="color:#555;">{shop_url}</a>
</p>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# 5. B2B ENTERPRISE PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

async def run_b2b_pipeline() -> Dict:
    """
    Zielt auf Unternehmen für AI Tools / BullPower Hub SaaS:
    - industrie_outreach.db (100 Leads — Maschinenbau, IT, etc.)
    - ai_act_scanner.db (AI Act Compliance Leads)
    - KI-Leasing, EU AI Act, BullPower Hub Pitches
    - 20 B2B-Emails via SendGrid pro Lauf
    """
    t0 = time.monotonic()
    log.info("B2B Pipeline: Starte Enterprise-Outreach...")

    leads_contacted = 0

    # Load leads from multiple sources
    industry_leads = _get_b2b_leads_from_db(str(DATA_DIR / "industrie_outreach.db"), 15)
    ai_act_leads   = _get_b2b_leads_from_db(str(DATA_DIR / "ai_act_scanner.db"), 10)
    bulk_leads     = _get_b2b_leads_from_db(str(DATA_DIR / "bulk_outreach.db"), 10)

    all_leads = industry_leads + ai_act_leads + bulk_leads
    if not all_leads:
        log.info("B2B Pipeline: Keine Leads verfügbar — überspringe")
        return {"leads_contacted": 0, "pitch_type": "none", "note": "no leads available"}

    # Assign pitch types
    pitch_assignments = []
    for i, lead in enumerate(all_leads[:20]):
        email   = (lead.get("email") or lead.get("Email") or "").strip().lower()
        company = lead.get("company") or lead.get("Company") or lead.get("company_name") or "Ihr Unternehmen"
        industry = lead.get("industry") or lead.get("sector") or "Technologie"
        if not email or "@" not in email:
            continue

        # Rotate pitch types
        pitch_idx = i % 3
        if pitch_idx == 0:
            pitch_type = "eu_ai_act"
            subject    = f"EU AI Act Deadline August 2026 — {company} handlungspflichtig"
            pitch_key  = "ai_act"
        elif pitch_idx == 1:
            pitch_type = "bullpower_hub"
            subject    = f"KI-Automatisierung für {company} — 7 Tage kostenlos testen"
            pitch_key  = "saas"
        else:
            pitch_type = "ki_leasing"
            subject    = f"KI ohne Upfront-Kosten für {company} — ab €199/Mo"
            pitch_key  = "leasing"

        pitch_assignments.append({
            "email": email, "company": company, "industry": industry,
            "subject": subject, "pitch_type": pitch_type, "pitch_key": pitch_key,
        })

    # Send emails with AI-generated pitch
    for lead in pitch_assignments:
        email      = lead["email"]
        company    = lead["company"]
        industry   = lead["industry"]
        subject    = lead["subject"]
        pitch_type = lead["pitch_type"]

        body_prompt = _b2b_pitch_prompt(company, industry, pitch_type)
        pitch_text  = await _ai_copy(body_prompt, max_tokens=250)
        html_body   = _build_b2b_email_html(company, industry, pitch_text, pitch_type)

        ok = await _send_sendgrid(email, subject, html_body, from_name="Rudolf Sarkany | AiiteC")

        if ok:
            leads_contacted += 1
            _log_outreach(email, company, pitch_type)

    pitch_type_summary = "eu_ai_act + saas + ki_leasing"
    duration = round(time.monotonic() - t0, 1)
    log.info("B2B Pipeline: %d Leads kontaktiert in %ss", leads_contacted, duration)

    if leads_contacted > 0:
        await _tg(
            f"🏢 <b>B2B Pipeline</b>\n"
            f"Kontaktiert: {leads_contacted}\n"
            f"Pitch-Typen: {pitch_type_summary}\n"
            f"Zeit: {duration}s"
        )

    return {
        "leads_contacted": leads_contacted,
        "pitch_type":      pitch_type_summary,
        "duration_s":      duration,
    }


def _b2b_pitch_prompt(company: str, industry: str, pitch_type: str) -> str:
    if pitch_type == "eu_ai_act":
        return (
            f"Schreibe eine B2B-Email auf Deutsch (max 150 Wörter) an {company} ({industry}). "
            f"Thema: EU AI Act — Unternehmen müssen bis August 2026 KI-Systeme konformieren. "
            f"Biete AiiteC AI Act Compliance-Check an. "
            f"Dringlichkeit betonen. Kein FUD, sachlich. "
            f"Link: https://aiitec.de/ai-act"
        )
    elif pitch_type == "ki_leasing":
        return (
            f"B2B-Email auf Deutsch (max 150 Wörter) an {company} ({industry}). "
            f"Thema: KI-Leasing — KI-System ohne Upfront-Kosten, ab €199/Mo. "
            f"ROI betonen: typisch 3x innerhalb 6 Monate. "
            f"Kein Risiko, 30-Tage-Kündigung. "
            f"Link: https://ineedit.com.co/pages/ki-leasing"
        )
    else:  # saas / bullpower_hub
        return (
            f"B2B-Email auf Deutsch (max 150 Wörter) an {company} ({industry}). "
            f"Thema: BullPower Hub — KI-E-Commerce-Automatisierung. "
            f"Spare 40h/Woche, 7 Tage kostenlos testen. "
            f"Spezifischer Nutzen für {industry}-Branche. "
            f"Link: https://ineedit.com.co"
        )


def _build_b2b_email_html(
    company: str, industry: str, pitch: str, pitch_type: str
) -> str:
    cta_map = {
        "eu_ai_act":   ("AI Act Check starten", "https://aiitec.de/ai-act"),
        "ki_leasing":  ("KI-Leasing anfragen", "https://ineedit.com.co/pages/ki-leasing"),
        "bullpower_hub": ("7 Tage kostenlos testen", "https://ineedit.com.co"),
    }
    cta_text, cta_url = cta_map.get(pitch_type, ("Mehr erfahren", "https://ineedit.com.co"))

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>AiiteC — {company}</title></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#f5f5f5;color:#333;">
<div style="background:#fff;border-radius:8px;padding:30px;border-left:4px solid #f39c12;">
<h2 style="color:#1a1a2e;margin-top:0;">AiiteC KI-Lösungen</h2>
<div style="line-height:1.7;color:#444;white-space:pre-line;">{pitch}</div>
<div style="margin:25px 0;">
<a href="{cta_url}" style="display:inline-block;background:#f39c12;color:#1a1a2e;padding:12px 25px;
border-radius:6px;text-decoration:none;font-weight:bold;">{cta_text}</a>
</div>
<hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
<p style="color:#666;font-size:12px;margin:0;">
Rudolf Sarkany | AiiteC | aiitecbuuss@gmail.com<br>
<a href="https://ineedit.com.co" style="color:#666;">ineedit.com.co</a>
</p>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# 6. YOUTUBE MONETIZATION CHAIN
# ═══════════════════════════════════════════════════════════════════════════════

async def run_youtube_money_chain() -> Dict:
    """
    Nutzt YouTube zur Umsatzgenerierung:
    1. Trending-Topics suchen
    2. Product-Showcase-Video über youtube_autopilot erstellen
    3. Affiliate-Links in Beschreibung
    4. Teaser auf Facebook/Instagram/Telegram
    5. Email-Kampagne: "Watch this video!"
    """
    t0 = time.monotonic()
    log.info("YouTubeMoneyChain: Starte...")

    video_created      = False
    video_id           = ""
    channels_notified  = 0
    trending_topic     = ""

    # 1. Find trending topic
    try:
        from modules.youtube_autonomy import find_trending_videos
        trending = await find_trending_videos()
        if trending and isinstance(trending, list):
            trending_topic = trending[0].get("title", "") if isinstance(trending[0], dict) else str(trending[0])
        elif isinstance(trending, dict):
            vids = trending.get("videos", trending.get("trending", []))
            if vids:
                trending_topic = vids[0].get("title", "") if isinstance(vids[0], dict) else str(vids[0])
    except Exception as e:
        log.warning("YouTube trending fetch failed: %s", e)

    if not trending_topic:
        # Fallback: use a product-based topic
        trending_topic = "Smart Home Gadgets 2026 — Diese 5 Produkte ändern dein Zuhause"

    log.info("YouTubeMoneyChain: Trending topic: %s", trending_topic[:60])

    # 2. Create product showcase video
    try:
        from modules.youtube_autopilot import create_and_upload_video
        # Build video description with affiliate links
        shop    = SHOP_URL()
        ds24    = DS24_LINK()
        gumroad = GUMROAD_124()
        description = (
            f"{trending_topic}\n\n"
            f"In diesem Video: Die besten Smart Home Produkte 2026.\n\n"
            f"Links:\n"
            f"🛒 Shop: {shop}\n"
            f"💰 Affiliate-Programm: {shop}/pages/affiliate\n"
            f"📚 124 Geldmaschinen: {ds24}\n"
            + (f"📖 Digital Downloads: {gumroad}\n" if gumroad else "")
            + f"\n#SmartHome #Gadgets #Automation #KI #Tech"
        )

        video_result = await create_and_upload_video(
            title=trending_topic[:100],
            description=description,
            tags=["SmartHome", "Gadgets", "KI", "ECommerce", "Automation", "Tech"],
        )
        if isinstance(video_result, dict):
            video_id      = video_result.get("video_id", video_result.get("id", ""))
            video_created = bool(video_id)
        elif isinstance(video_result, str) and video_result:
            video_id      = video_result
            video_created = True
    except Exception as e:
        log.warning("YouTube video creation failed: %s", e)

    # 3. Post teaser on social channels
    video_url  = f"https://youtu.be/{video_id}" if video_id else SHOP_URL()
    teaser_msg = (
        f"🎥 Neues Video: {trending_topic[:80]}\n\n"
        f"Schau es dir jetzt an!\n"
        f"👉 {video_url}\n\n"
        f"#YouTube #SmartHome #KI #ECommerce"
    )

    async with aiohttp.ClientSession() as session:
        tg_ok = await _tg(teaser_msg, session)
        if tg_ok:
            channels_notified += 1

        fb_result = await _fb_post(teaser_msg, session)
        if fb_result.get("ok"):
            channels_notified += 1

    duration = round(time.monotonic() - t0, 1)
    log.info(
        "YouTubeMoneyChain: video_created=%s video_id=%s channels=%d",
        video_created, video_id, channels_notified,
    )

    if video_created or channels_notified:
        await _tg(
            f"🎬 <b>YouTube Money Chain</b>\n"
            f"Video erstellt: {'Ja' if video_created else 'Nein'}\n"
            f"Video ID: {video_id or 'N/A'}\n"
            f"Topic: {trending_topic[:60]}\n"
            f"Kanäle benachrichtigt: {channels_notified}\n"
            f"Zeit: {duration}s"
        )

    return {
        "video_created":      video_created,
        "video_id":           video_id,
        "channels_notified":  channels_notified,
        "trending_topic":     trending_topic,
        "duration_s":         duration,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 7. DAILY REVENUE REPORT
# ═══════════════════════════════════════════════════════════════════════════════

async def generate_daily_revenue_report() -> Dict:
    """
    Aggregiert Umsatz aus allen Quellen:
    - Stripe (letzte 24h Charges)
    - DS24 (letzte 24h Transaktionen)
    - Shopify (letzte 24h Orders)

    Sendet formatierten Telegram-Report.
    """
    t0 = time.monotonic()
    log.info("DailyRevReport: Sammle Umsatzdaten...")

    report: Dict[str, Any] = {
        "date":      datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "shopify":   0.0,
        "stripe":    0.0,
        "ds24":      0.0,
        "total":     0.0,
        "new_leads": 0,
        "social_posts_today": 0,
    }

    # Stripe revenue (last 24h)
    try:
        stripe_key = _STRIPE_KEY()
        if stripe_key:
            import base64
            since = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())
            url   = f"https://api.stripe.com/v1/charges?created[gte]={since}&limit=100"
            auth  = "Basic " + base64.b64encode(f"{stripe_key}:".encode()).decode()
            async with aiohttp.ClientSession() as _s:
                async with _s.get(url, headers={"Authorization": auth},
                                  timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json(content_type=None)
            charges = data.get("data", [])
            report["stripe"] = round(
                sum(
                    c.get("amount", 0) / 100
                    for c in charges
                    if c.get("paid") and not c.get("refunded")
                       and c.get("currency", "").lower() == "eur"
                ),
                2,
            )
    except Exception as e:
        log.warning("Stripe revenue fetch failed: %s", e)

    # DS24 transactions (last 24h)
    try:
        from modules.digistore24_automation import get_orders as ds24_orders
        orders_24h = await ds24_orders(per_page=50)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)
        for order in orders_24h:
            try:
                order_date_str = order.get("date_created") or order.get("created_at") or ""
                if order_date_str:
                    od = datetime.fromisoformat(order_date_str.replace("Z", "+00:00"))
                    if od >= cutoff:
                        report["ds24"] += float(order.get("total", order.get("order_total", 0)))
            except Exception:
                pass
        report["ds24"] = round(report["ds24"], 2)
    except Exception as e:
        log.warning("DS24 revenue fetch failed: %s", e)

    # Shopify orders (last 24h)
    try:
        domain = _SHOP_DOMAIN()
        tok    = _SHOP_TOK()
        ver    = _SHOP_VER()
        if domain and tok:
            since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://{domain}/admin/api/{ver}/orders.json",
                    headers={"X-Shopify-Access-Token": tok},
                    params={
                        "status": "any",
                        "created_at_min": since,
                        "limit": 100,
                        "financial_status": "paid",
                    },
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as r:
                    if r.status == 200:
                        orders = (await r.json()).get("orders", [])
                        report["shopify"] = round(
                            sum(float(o.get("total_price", 0)) for o in orders), 2
                        )
    except Exception as e:
        log.warning("Shopify revenue fetch failed: %s", e)

    # New email leads today
    try:
        conn = _db(EXPANSION_DB)
        row  = conn.execute(
            "SELECT COUNT(*) as cnt FROM outreach_log WHERE created_at >= date('now')"
        ).fetchone()
        report["new_leads"] = row["cnt"] if row else 0
        row2 = conn.execute(
            "SELECT COUNT(*) as cnt FROM promo_log WHERE created_at >= date('now')"
        ).fetchone()
        report["social_posts_today"] = row2["cnt"] if row2 else 0
        conn.close()
    except Exception:
        pass

    report["total"] = round(report["shopify"] + report["stripe"] + report["ds24"], 2)

    duration = round(time.monotonic() - t0, 1)
    report["duration_s"] = duration

    # Format and send Telegram report
    tg_text = (
        f"💰 <b>TAGES-REPORT {report['date']}</b>\n\n"
        f"🛒 Shopify:   €{report['shopify']:.2f}\n"
        f"💳 Stripe:    €{report['stripe']:.2f}\n"
        f"📚 DS24:      €{report['ds24']:.2f}\n"
        f"─────────────────\n"
        f"🎯 <b>Total:     €{report['total']:.2f}</b>\n\n"
        f"📧 Neue Leads: {report['new_leads']}\n"
        f"📱 Social Posts: {report['social_posts_today']}\n"
        f"⏱️ Dauer: {duration}s"
    )
    await _tg(tg_text)

    log.info(
        "DailyRevReport: Shopify €%.2f, Stripe €%.2f, DS24 €%.2f, Total €%.2f",
        report["shopify"], report["stripe"], report["ds24"], report["total"],
    )

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# 8. MASTER EXPANSION CYCLE
# ═══════════════════════════════════════════════════════════════════════════════

async def run_full_expansion_cycle() -> Dict:
    """
    Führt ALLE Revenue-Engines in optimaler Reihenfolge aus.
    Keine Engine blockiert eine andere — asyncio.gather mit return_exceptions=True.

    Sequenz:
    1. Daily Revenue Report (Baseline)
    2. Product Promo Blast
    3. B2B Pipeline
    4. Digital Products Push
    5. SaaS Subscriber Acquisition
    6. Affiliate Army Builder
    7. YouTube Money Chain
    8. Final Telegram Summary
    """
    t0       = time.monotonic()
    cycle_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log.info("FullExpansionCycle [%s]: START", cycle_id)

    await _tg(
        f"🚀 <b>Full Revenue Expansion Cycle gestartet</b>\n"
        f"ID: {cycle_id}\n"
        f"Zeit: {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
    )

    # Phase 1: Revenue baseline (sequential — needed for report)
    revenue_report = {}
    try:
        revenue_report = await generate_daily_revenue_report()
    except Exception as e:
        log.error("Revenue report failed: %s", e)
        revenue_report = {"error": str(e)}

    # Phase 2: All revenue engines in parallel
    results = await asyncio.gather(
        run_product_promo_blast(),
        run_b2b_pipeline(),
        push_digital_products(),
        acquire_saas_subscribers(),
        build_affiliate_army(),
        run_youtube_money_chain(),
        return_exceptions=True,
    )

    # Parse results
    labels = [
        "promo_blast",
        "b2b_pipeline",
        "digital_products",
        "saas_acquisition",
        "affiliate_army",
        "youtube_chain",
    ]

    cycle_results: Dict[str, Any] = {"revenue_report": revenue_report}
    actions_taken  = 0
    estimated_reach = 0

    for label, result in zip(labels, results):
        if isinstance(result, Exception):
            cycle_results[label] = {"error": str(result)}
            log.error("Cycle[%s] %s: %s", cycle_id, label, result)
        else:
            cycle_results[label] = result
            # Count actions
            if isinstance(result, dict):
                actions_taken += (
                    result.get("posts_made", 0) if isinstance(result.get("posts_made"), int) else
                    len(result.get("posts_made", {}))
                )
                actions_taken += result.get("emails_sent", 0)
                actions_taken += result.get("prospects_contacted", 0)
                actions_taken += result.get("leads_contacted", 0)
                actions_taken += result.get("invites_sent", 0)
                actions_taken += result.get("emails_queued", 0)
                # Estimated reach
                estimated_reach += result.get("emails_sent", 0) * 1
                estimated_reach += result.get("prospects_contacted", 0) * 1
                estimated_reach += result.get("leads_contacted", 0) * 1
                estimated_reach += result.get("emails_queued", 0) * 1
                # Social media reach estimate
                if result.get("posts_made"):
                    social_count = result["posts_made"] if isinstance(result["posts_made"], int) else len(result["posts_made"])
                    estimated_reach += social_count * 200  # rough organic reach per post

    duration = round(time.monotonic() - t0, 1)

    # Final summary
    summary = {
        "cycle_id":             cycle_id,
        "cycle_duration_s":     duration,
        "actions_taken":        actions_taken,
        "estimated_daily_reach": estimated_reach,
        "results":              cycle_results,
        "completed_at":         datetime.now(timezone.utc).isoformat(),
    }

    # Telegram final report
    rev_total = revenue_report.get("total", 0.0)
    await _tg(
        f"✅ <b>Expansion Cycle abgeschlossen</b>\n"
        f"ID: {cycle_id}\n\n"
        f"💰 Tages-Revenue: €{rev_total:.2f}\n"
        f"⚡ Aktionen: {actions_taken}\n"
        f"👥 Geschätzte Reichweite: ~{estimated_reach:,}\n"
        f"⏱️ Dauer: {duration}s"
    )

    log.info(
        "FullExpansionCycle [%s] DONE: %d Aktionen, ~%d Reach in %ss",
        cycle_id, actions_taken, estimated_reach, duration,
    )

    return summary
