"""
SHOP SCALING ENGINE v1.0
━━━━━━━━━━━━━━━━━━━━━━━━
Vollautonome Shop-Skalierungsmaschine für ineedit.com.co

Funktionen:
  1. Produkt-Optimierung (Beschreibungen via Claude Haiku)
  2. Trust-Signals & Discount-Codes
  3. Abandoned-Cart-Recovery (Email)
  4. Lead-Email-Blast (alle Datenbanken)
  5. SEO-Blogartikel (täglich 1)
  6. Social-Media-Posts (Facebook + Instagram + Telegram)
  7. Tages-Skalierungs-Zyklus (Master-Orchestrator)
  8. Stats-Endpoint für Dashboard
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import smtplib
import sqlite3
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from modules.ai_client import ai_complete

log = logging.getLogger("ShopScalingEngine")

# ── Pfade ──────────────────────────────────────────────────────────────────────
_BASE    = Path(__file__).parent.parent
DATA_DIR = _BASE / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
_DB      = DATA_DIR / "shop_scaling.db"

# ── Env-Helpers ────────────────────────────────────────────────────────────────
def _e(key: str, default: str = "") -> str:
    return os.getenv(key, default)

SHOP_DOMAIN    = _e("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")
SHOP_TOKEN     = _e("SHOPIFY_ADMIN_API_TOKEN") or _e("SHOPIFY_ACCESS_TOKEN", "")
API_VER        = _e("SHOPIFY_API_VERSION", "2026-04")
SHOP_URL       = _e("SHOPIFY_STORE_URL", f"https://{SHOP_DOMAIN}")
if not SHOP_URL.startswith("http"):
    SHOP_URL = "https://" + SHOP_URL
SHOP_NAME      = _e("SHOP_NAME", "I Need It")

ANTHROPIC_KEY  = _e("ANTHROPIC_API_KEY")

TG_TOKEN       = _e("TELEGRAM_BOT_TOKEN")
TG_CHAT        = _e("TELEGRAM_CHAT_ID")

FB_BASE        = "https://graph.facebook.com/v21.0"
FB_PAGE_ID     = _e("FACEBOOK_PAGE_ID_AIITEC", "1016738738178786")
FB_PAGE_TOKEN  = _e("FACEBOOK_PAGE_TOKEN_AIITEC") or _e("FACEBOOK_PAGE_TOKEN", "")
IG_USER_ID     = _e("INSTAGRAM_ACCOUNT_ID", "17841478315197796")

INDEXNOW_KEY   = _e("INDEXNOW_KEY", "aiitec2026")

# ── SQLite State ───────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS cart_recovery (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        checkout_id     TEXT UNIQUE NOT NULL,
        email           TEXT NOT NULL,
        products        TEXT DEFAULT '',
        total           TEXT DEFAULT '0',
        recovered       INTEGER DEFAULT 0,
        email_sent      INTEGER DEFAULT 0,
        sent_at         TEXT,
        created_at      TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS scaling_runs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        run_at          TEXT DEFAULT (datetime('now')),
        products_optimized  INTEGER DEFAULT 0,
        carts_recovered     INTEGER DEFAULT 0,
        emails_sent         INTEGER DEFAULT 0,
        articles_published  INTEGER DEFAULT 0,
        social_posts        INTEGER DEFAULT 0,
        duration_sec        REAL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS seo_articles (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT,
        slug        TEXT UNIQUE,
        article_id  TEXT,
        published_at TEXT DEFAULT (datetime('now'))
    );
    """)
    conn.commit()
    return conn


# ── Shopify REST-Helper ────────────────────────────────────────────────────────

def _shopify_headers() -> Dict[str, str]:
    return {
        "X-Shopify-Access-Token": SHOP_TOKEN,
        "Content-Type": "application/json",
    }

def _shopify_base() -> str:
    return f"https://{SHOP_DOMAIN}/admin/api/{API_VER}"

async def _shopify_get(session: aiohttp.ClientSession, endpoint: str) -> Dict:
    url = f"{_shopify_base()}/{endpoint}"
    try:
        async with session.get(url, headers=_shopify_headers(),
                               timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status == 200:
                return await r.json()
            text = await r.text()
            log.warning("Shopify GET %s → %d: %s", endpoint, r.status, text[:200])
            return {}
    except Exception as e:
        log.warning("Shopify GET %s error: %s", endpoint, e)
        return {}

async def _shopify_put(session: aiohttp.ClientSession, endpoint: str, data: Dict) -> Dict:
    url = f"{_shopify_base()}/{endpoint}"
    try:
        async with session.put(url, headers=_shopify_headers(), json=data,
                               timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status in (200, 201):
                return await r.json()
            text = await r.text()
            log.warning("Shopify PUT %s → %d: %s", endpoint, r.status, text[:200])
            return {}
    except Exception as e:
        log.warning("Shopify PUT %s error: %s", endpoint, e)
        return {}

async def _shopify_post(session: aiohttp.ClientSession, endpoint: str, data: Dict) -> Dict:
    url = f"{_shopify_base()}/{endpoint}"
    try:
        async with session.post(url, headers=_shopify_headers(), json=data,
                                timeout=aiohttp.ClientTimeout(total=20)) as r:
            resp = await r.json()
            if r.status in (200, 201):
                return resp
            log.warning("Shopify POST %s → %d: %s", endpoint, r.status, str(resp)[:200])
            return {}
    except Exception as e:
        log.warning("Shopify POST %s error: %s", endpoint, e)
        return {}


# ── AI Helper (multi-provider via ai_client) ───────────────────────────────────

async def _claude(prompt: str, max_tokens: int = 600) -> str:
    """Generates text via ai_complete (multi-provider fallback). Returns empty string on failure."""
    try:
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception as e:
        log.warning("ai_complete error: %s", e)
        return ""


# ── Telegram Notify ────────────────────────────────────────────────────────────

async def _tg(text: str) -> None:
    token = TG_TOKEN
    chat  = TG_CHAT
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram notify error: %s", e)


# ── SMTP Pool ──────────────────────────────────────────────────────────────────

def _build_smtp_pool() -> List[Dict]:
    accounts = []
    pairs = [
        ("GMAIL_USER_1", "GMAIL_APP_PASSWORD_1", "dragonadnp@gmail.com"),
        ("GMAIL_USER_5", "GMAIL_APP_PASSWORD_5", "aiitecbuuss@gmail.com"),
        ("GMAIL_USER_7", "GMAIL_APP_PASSWORD_7", "rudolf.sarkany.aiitec@gmail.com"),
        ("GMAIL_USER_3", "GMAIL_APP_PASSWORD_3", "bullpowersrtkennels@gmail.com"),
    ]
    for user_key, pass_key, default_user in pairs:
        pw = _e(pass_key)
        if pw:
            accounts.append({
                "name": _e(user_key, default_user).split("@")[0],
                "user": _e(user_key, default_user),
                "password": pw,
                "host": "smtp.gmail.com",
                "port": 587,
                "daily_limit": 50,
                "sent_today": 0,
            })
    return accounts

_smtp_pool: List[Dict] = []
_smtp_idx: int = 0

def _get_smtp_account() -> Optional[Dict]:
    global _smtp_pool, _smtp_idx
    if not _smtp_pool:
        _smtp_pool = _build_smtp_pool()
    if not _smtp_pool:
        return None
    account = _smtp_pool[_smtp_idx % len(_smtp_pool)]
    _smtp_idx += 1
    return account


def _send_email_sync(account: Dict, to_email: str, subject: str,
                     html_body: str, from_name: str = "") -> bool:
    """Synchroner SMTP-Versand via TLS."""
    try:
        msg = MIMEMultipart("alternative")
        fname = from_name or SHOP_NAME
        msg["From"]    = f"{fname} <{account['user']}>"
        msg["To"]      = to_email
        msg["Subject"] = subject
        msg["List-Unsubscribe"] = f"<{SHOP_URL}/pages/abmelden?email={to_email}>"
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        with smtplib.SMTP(account["host"], account["port"], timeout=20) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(account["user"], account["password"])
            srv.sendmail(account["user"], [to_email], msg.as_bytes())
        return True
    except Exception as e:
        log.warning("SMTP send to %s via %s: %s", to_email, account["name"], e)
        return False


async def _send_email(to_email: str, subject: str, html_body: str,
                      from_name: str = "") -> bool:
    account = _get_smtp_account()
    if not account:
        log.warning("Kein SMTP-Account verfügbar")
        return False
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _send_email_sync, account, to_email, subject, html_body, from_name
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: SHOPIFY PRODUCT OPTIMIZER
# ═══════════════════════════════════════════════════════════════════════════════

async def optimize_product_catalog() -> Dict:
    """
    Fetches products with issues and auto-fixes them:
    - Empty / short descriptions → Claude Haiku generates 200-word German description
    - Missing vendor → fills from tags
    - Price = 0 → flags for review
    - No images → logs warning
    Returns: {optimized: int, skipped: int, errors: int, flagged: int}
    """
    if not SHOP_TOKEN:
        return {"error": "SHOPIFY_ADMIN_API_TOKEN fehlt", "optimized": 0}

    optimized = 0
    skipped   = 0
    errors    = 0
    flagged   = 0
    page      = 1
    processed_ids = set()

    log.info("Produkt-Optimierung gestartet…")

    async with aiohttp.ClientSession() as session:
        since_id = None
        while True:
            if since_id:
                ep = f"products.json?limit=50&since_id={since_id}&fields=id,title,body_html,vendor,tags,images,variants&status=active"
            else:
                ep = f"products.json?limit=50&fields=id,title,body_html,vendor,tags,images,variants&status=active"

            data = await _shopify_get(session, ep)
            products = data.get("products", [])
            if not products:
                break

            for product in products:
                pid   = product.get("id")
                if pid in processed_ids:
                    continue
                processed_ids.add(pid)

                title     = product.get("title", "")
                body_html = product.get("body_html") or ""
                vendor    = product.get("vendor", "")
                tags_str  = product.get("tags", "")
                images    = product.get("images", [])
                variants  = product.get("variants", [])

                needs_update = False
                update_data: Dict[str, Any] = {"id": pid}

                # — Preis = 0 flaggen —
                for v in variants:
                    try:
                        price = float(v.get("price", "0") or "0")
                        if price == 0.0:
                            flagged += 1
                            log.warning("Produkt %s (%s): Preis = 0 — Review nötig", pid, title[:40])
                            break
                    except (ValueError, TypeError):
                        pass

                # — Kein Bild —
                if not images:
                    log.warning("Produkt %s (%s): Kein Bild vorhanden", pid, title[:40])

                # — Beschreibung fehlt / zu kurz (<100 Zeichen) —
                clean_body = re.sub(r"<[^>]+>", "", body_html).strip()
                if len(clean_body) < 100:
                    if not title:
                        skipped += 1
                        continue
                    try:
                        prompt = (
                            f"Schreibe eine professionelle 200-Wort Produktbeschreibung auf Deutsch für: {title}. "
                            f"Ton: modern, vertrauenswürdig, überzeugend. "
                            f"Betone: Qualität, Nutzen, Lieferung. Kein Preis nennen. "
                            f"Format: kurze HTML-Paragraphen mit <p>-Tags, keine Überschriften."
                        )
                        generated = await _claude(prompt, max_tokens=500)
                        if generated and len(generated) > 80:
                            update_data["body_html"] = generated
                            needs_update = True
                            log.info("Beschreibung generiert für: %s", title[:40])
                        else:
                            skipped += 1
                            continue
                    except Exception as e:
                        log.warning("Claude-Fehler für %s: %s", pid, e)
                        errors += 1
                        continue

                # — Vendor leer → aus Tags ableiten —
                if not vendor and tags_str:
                    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
                    brand_tags = [t for t in tags if t.startswith("brand-") or t.startswith("vendor-")]
                    if brand_tags:
                        inferred = brand_tags[0].replace("brand-", "").replace("vendor-", "").strip().title()
                        if inferred:
                            update_data["vendor"] = inferred
                            needs_update = True

                if needs_update:
                    try:
                        resp = await _shopify_put(session, f"products/{pid}.json",
                                                  {"product": update_data})
                        if resp.get("product"):
                            optimized += 1
                        else:
                            errors += 1
                    except Exception as e:
                        log.warning("PUT-Fehler Produkt %s: %s", pid, e)
                        errors += 1
                    await asyncio.sleep(0.5)  # Rate-limit Shopify (2 req/s)
                else:
                    skipped += 1

            # Pagination via since_id — update cursor to last product ID
            since_id = products[-1].get("id") if products else None
            if len(products) < 50:
                break
            # Safety cap — stop after 500 products
            if len(processed_ids) >= 500:
                break
            page += 1
            await asyncio.sleep(1)

    result = {
        "optimized": optimized,
        "skipped":   skipped,
        "errors":    errors,
        "flagged":   flagged,
        "total_checked": len(processed_ids),
    }
    log.info("Produkt-Optimierung abgeschlossen: %s", result)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: TRUST & SOCIAL PROOF INJECTOR
# ═══════════════════════════════════════════════════════════════════════════════

async def inject_trust_signals() -> Dict:
    """
    1. Erstellt/aktualisiert Shopify-Seite 'vertrauen' mit Trust-Content
    2. Erstellt Discount WILLKOMMEN10 (10% Erstbestellung)
    3. Erstellt Discount SAVE10 (10% jede Bestellung)
    Returns: {page_created: bool, discounts_created: int}
    """
    if not SHOP_TOKEN:
        return {"error": "SHOPIFY_ADMIN_API_TOKEN fehlt", "page_created": False, "discounts_created": 0}

    page_created      = False
    discounts_created = 0

    trust_html = """
<div class="trust-container" style="font-family:sans-serif;max-width:800px;margin:0 auto;padding:20px">
  <h2 style="color:#1a1a2e;border-bottom:2px solid #e0e0e0;padding-bottom:10px">
    Warum Kunden uns vertrauen
  </h2>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;margin:20px 0">
    <div style="text-align:center;padding:15px;border:1px solid #e0e0e0;border-radius:8px">
      <div style="font-size:2rem">🔒</div>
      <strong>SSL-verschlüsselt</strong>
      <p style="color:#666;font-size:0.9rem;margin:5px 0">Alle Daten sicher übertragen (256-Bit)</p>
    </div>
    <div style="text-align:center;padding:15px;border:1px solid #e0e0e0;border-radius:8px">
      <div style="font-size:2rem">🔄</div>
      <strong>30 Tage Rückgabe</strong>
      <p style="color:#666;font-size:0.9rem;margin:5px 0">Keine Fragen gestellt — volle Erstattung</p>
    </div>
    <div style="text-align:center;padding:15px;border:1px solid #e0e0e0;border-radius:8px">
      <div style="font-size:2rem">🚚</div>
      <strong>Versand ab €50 gratis</strong>
      <p style="color:#666;font-size:0.9rem;margin:5px 0">Schnelle Lieferung 3–7 Werktage</p>
    </div>
    <div style="text-align:center;padding:15px;border:1px solid #e0e0e0;border-radius:8px">
      <div style="font-size:2rem">💳</div>
      <strong>Sichere Zahlung</strong>
      <p style="color:#666;font-size:0.9rem;margin:5px 0">Visa · Mastercard · PayPal · Klarna</p>
    </div>
  </div>
  <div style="background:#f8f9fa;border-left:4px solid #28a745;padding:15px;border-radius:4px;margin:20px 0">
    <strong>Unser Versprechen:</strong> 30 Tage Rückgabe · Kostenloser Versand ab €50 · Sichere Zahlung · Schnelle Lieferung
  </div>
  <h3 style="color:#1a1a2e">Kundenstimmen</h3>
  <div style="background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:15px;margin:10px 0">
    <div style="color:#f39c12">★★★★★</div>
    <p style="margin:5px 0;font-style:italic">"Schnelle Lieferung, super Qualität! Bin begeistert."</p>
    <small style="color:#888">— Verified Buyer, Mai 2026</small>
  </div>
  <div style="background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:15px;margin:10px 0">
    <div style="color:#f39c12">★★★★★</div>
    <p style="margin:5px 0;font-style:italic">"Tolles Produkt, genau wie beschrieben. Gerne wieder!"</p>
    <small style="color:#888">— Verified Buyer, Juni 2026</small>
  </div>
</div>
""".strip()

    async with aiohttp.ClientSession() as session:
        # — Seite 'vertrauen' erstellen / aktualisieren —
        try:
            pages_data = await _shopify_get(session, "pages.json?limit=50")
            existing = next(
                (p for p in pages_data.get("pages", []) if p.get("handle") == "vertrauen"),
                None
            )
            page_payload = {
                "page": {
                    "title":       "Warum uns vertrauen?",
                    "handle":      "vertrauen",
                    "body_html":   trust_html,
                    "published":   True,
                }
            }
            if existing:
                resp = await _shopify_put(session, f"pages/{existing['id']}.json", page_payload)
            else:
                resp = await _shopify_post(session, "pages.json", page_payload)

            if resp.get("page"):
                page_created = True
                log.info("Trust-Seite 'vertrauen' erstellt/aktualisiert")
        except Exception as e:
            log.warning("Trust-Seite Fehler: %s", e)

        await asyncio.sleep(0.5)

        # — Discount-Codes erstellen —
        discount_configs = [
            {
                "name":    "WILLKOMMEN10",
                "value":   "-10.0",
                "title":   "Willkommen — 10% Rabatt auf die Erstbestellung",
                "once":    True,
                "min_amount": "0.0",
            },
            {
                "name":    "SAVE10",
                "value":   "-10.0",
                "title":   "10% Rabatt auf jede Bestellung",
                "once":    False,
                "min_amount": "0.0",
            },
        ]

        for dc in discount_configs:
            try:
                # Prüfen ob schon vorhanden
                existing_rules = await _shopify_get(
                    session, "price_rules.json?limit=50"
                )
                already = any(
                    pr.get("title", "").upper() == dc["name"].upper()
                    for pr in existing_rules.get("price_rules", [])
                )
                if already:
                    log.info("Discount %s existiert bereits", dc["name"])
                    discounts_created += 1
                    continue

                # Preis-Regel anlegen
                rule_payload = {
                    "price_rule": {
                        "title":              dc["title"],
                        "target_type":        "line_item",
                        "target_selection":   "all",
                        "allocation_method":  "across",
                        "value_type":         "percentage",
                        "value":              dc["value"],
                        "customer_selection":  "all",
                        "starts_at":          datetime.now(timezone.utc).isoformat(),
                        "usage_limit":        None,
                        "once_per_customer":  dc["once"],
                    }
                }
                rule_resp = await _shopify_post(session, "price_rules.json", rule_payload)
                rule_id = rule_resp.get("price_rule", {}).get("id")
                if not rule_id:
                    log.warning("Preis-Regel %s konnte nicht erstellt werden", dc["name"])
                    continue

                await asyncio.sleep(0.5)

                # Discount-Code anlegen
                code_payload = {
                    "discount_code": {"code": dc["name"]}
                }
                code_resp = await _shopify_post(
                    session, f"price_rules/{rule_id}/discount_codes.json", code_payload
                )
                if code_resp.get("discount_code"):
                    discounts_created += 1
                    log.info("Discount-Code %s erstellt (Rule-ID: %s)", dc["name"], rule_id)
                else:
                    log.warning("Discount-Code %s: Antwort=%s", dc["name"], code_resp)
            except Exception as e:
                log.warning("Discount %s Fehler: %s", dc["name"], e)

    result = {"page_created": page_created, "discounts_created": discounts_created}
    if page_created or discounts_created:
        await _tg(
            f"✅ <b>Trust-Signale injiziert</b>\n"
            f"• Trust-Seite: {'erstellt' if page_created else 'Fehler'}\n"
            f"• Discount-Codes erstellt: {discounts_created}"
        )
    log.info("Trust-Signale: %s", result)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: ABANDONED CART EMAIL RECOVERY
# ═══════════════════════════════════════════════════════════════════════════════

async def run_abandoned_cart_recovery() -> Dict:
    """
    Ruft Shopify Abandoned Checkouts ab und sendet Recovery-Emails.
    Carts, die >2h alt und noch nicht recovered sind, bekommen eine Email.
    Returns: {carts_found: int, emails_sent: int, already_recovered: int}
    """
    if not SHOP_TOKEN:
        return {"error": "SHOPIFY_ADMIN_API_TOKEN fehlt", "carts_found": 0,
                "emails_sent": 0, "already_recovered": 0}

    carts_found      = 0
    emails_sent      = 0
    already_recovered = 0

    cutoff_min = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_str = cutoff_min.strftime("%Y-%m-%dT%H:%M:%SZ")

    log.info("Abandoned-Cart-Recovery: Checkouts seit %s prüfen…", cutoff_str)

    try:
        async with aiohttp.ClientSession() as session:
            data = await _shopify_get(
                session,
                f"checkouts.json?limit=50&created_at_min={cutoff_str}&status=open"
            )
            checkouts = data.get("checkouts", [])
            carts_found = len(checkouts)

            for checkout in checkouts:
                email       = (checkout.get("email") or "").strip()
                checkout_id = str(checkout.get("id", ""))
                updated_at  = checkout.get("updated_at", "")
                completed   = bool(checkout.get("completed_at"))

                if not email or completed:
                    continue

                # Nur Carts, die >2h nicht mehr aktualisiert wurden
                try:
                    updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    age_hours = (datetime.now(timezone.utc) - updated_dt).total_seconds() / 3600
                    if age_hours < 2:
                        continue
                except Exception as e:
                    log.debug("age parse skip: %s", e)

                # DB-Check: bereits Email gesendet?
                conn = _db()
                row = conn.execute(
                    "SELECT email_sent, recovered FROM cart_recovery WHERE checkout_id=?",
                    (checkout_id,)
                ).fetchone()

                if row and (row["email_sent"] or row["recovered"]):
                    already_recovered += 1
                    conn.close()
                    continue

                # Produktliste aus Checkout
                line_items = checkout.get("line_items", [])
                product_names = [li.get("title", "") for li in line_items[:3]]
                products_str  = ", ".join(p for p in product_names if p) or "deinen Artikel"
                total_price   = checkout.get("total_price", "0")
                currency      = checkout.get("currency", "EUR")
                recovery_url  = checkout.get("abandoned_checkout_url", SHOP_URL)

                # Email-Inhalt generieren
                subject = f"Du hast etwas vergessen 🛒 — {products_str[:40]}"
                html_body = _cart_recovery_email_html(
                    email=email,
                    products_str=products_str,
                    total_price=total_price,
                    currency=currency,
                    recovery_url=recovery_url,
                )

                # Email senden
                sent = await _send_email(email, subject, html_body, from_name=SHOP_NAME)

                # DB aktualisieren
                conn.execute("""
                    INSERT INTO cart_recovery (checkout_id, email, products, total, email_sent, sent_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(checkout_id) DO UPDATE SET
                      email_sent=excluded.email_sent, sent_at=excluded.sent_at
                """, (checkout_id, email, products_str, total_price, 1 if sent else 0))
                conn.commit()
                conn.close()

                if sent:
                    emails_sent += 1
                    log.info("Cart-Recovery Email gesendet an: %s (Cart: %s)", email, checkout_id)
                    await asyncio.sleep(0.3)

    except Exception as e:
        log.error("Abandoned-Cart-Recovery Fehler: %s", e)

    result = {
        "carts_found":       carts_found,
        "emails_sent":       emails_sent,
        "already_recovered": already_recovered,
    }
    log.info("Cart-Recovery: %s", result)
    return result


def _cart_recovery_email_html(email: str, products_str: str, total_price: str,
                               currency: str, recovery_url: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>Dein Warenkorb wartet!</title></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f9f9f9;padding:20px">
  <div style="background:#fff;border-radius:8px;padding:30px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
    <h2 style="color:#1a1a2e;margin-bottom:10px">🛒 Dein Warenkorb wartet auf dich!</h2>
    <p style="color:#555;line-height:1.6">
      Du hast <strong>{products_str}</strong> in deinem Warenkorb gelassen.
      Sichere dir deinen Kauf jetzt — bevor die Artikel vergriffen sind!
    </p>
    <div style="background:#f0f9f0;border:1px solid #28a745;border-radius:6px;padding:15px;margin:20px 0;text-align:center">
      <strong style="color:#28a745;font-size:1.2rem">🎁 Exklusiver Rabatt: SAVE10</strong><br>
      <span style="color:#555">10% Rabatt auf deine Bestellung — nur für kurze Zeit!</span>
    </div>
    <div style="text-align:center;margin:25px 0">
      <a href="{recovery_url}" style="background:#e63946;color:#fff;padding:14px 32px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:1.1rem;display:inline-block">
        Jetzt kaufen →
      </a>
    </div>
    <p style="color:#888;font-size:0.85rem;margin-top:20px">
      Gesamtbetrag im Warenkorb: <strong>{total_price} {currency}</strong><br>
      🔒 Sichere Zahlung · 🚚 Schnelle Lieferung · 🔄 30 Tage Rückgabe
    </p>
    <hr style="border:none;border-top:1px solid #eee;margin:20px 0">
    <p style="color:#aaa;font-size:0.75rem;text-align:center">
      {SHOP_NAME} · <a href="{SHOP_URL}/pages/abmelden?email={email}" style="color:#aaa">Abmelden</a>
    </p>
  </div>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: LEAD EMAIL BLASTER
# ═══════════════════════════════════════════════════════════════════════════════

async def blast_all_queued_leads(max_per_run: int = 100) -> Dict:
    """
    Sendet Emails an alle wartenden Leads aus allen Datenbanken.
    Datenbanken: industrie_outreach.db, mass_outreach.db, mega_acquisition.db
    Returns: {sent: int, failed: int, databases_checked: list}
    """
    sent_total   = 0
    failed_total = 0
    dbs_checked  = []

    db_configs = [
        {
            "path":        DATA_DIR / "industrie_outreach.db",
            "table":       "industrie_outreach",
            "email_col":   "email",
            "name_col":    "name",
            "company_col": "company",
            "niche_col":   "branche",
            "status_col":  "status",
            "status_val":  "queued",
            "id_col":      "id",
        },
        {
            "path":        DATA_DIR / "mass_outreach.db",
            "table":       "leads",
            "email_col":   "email",
            "name_col":    "name",
            "company_col": "company",
            "niche_col":   "niche",
            "status_col":  "status",
            "status_val":  "new",
            "id_col":      "id",
        },
        {
            "path":        DATA_DIR / "mega_acquisition.db",
            "table":       "acquisition_leads",
            "email_col":   "email",
            "name_col":    "name",
            "company_col": "company",
            "niche_col":   "niche",
            "status_col":  "status",
            "status_val":  "new",
            "id_col":      "id",
        },
    ]

    log.info("Lead-Blast gestartet (max %d pro Lauf)…", max_per_run)
    remaining = max_per_run

    for cfg in db_configs:
        db_path = cfg["path"]
        if not db_path.exists():
            log.info("DB nicht vorhanden: %s", db_path.name)
            continue

        dbs_checked.append(db_path.name)
        if remaining <= 0:
            break

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")

            # Flexibles Query — prüft ob Tabelle existiert
            table = cfg["table"]
            tables_in_db = [
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            if table not in tables_in_db:
                # Fallback: erste Tabelle mit "lead" im Namen suchen
                lead_tables = [t for t in tables_in_db if "lead" in t.lower()]
                if not lead_tables:
                    conn.close()
                    continue
                table = lead_tables[0]

            # Spalten der Tabelle ermitteln
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            email_col   = cfg["email_col"]   if cfg["email_col"]   in cols else "email"
            name_col    = cfg["name_col"]    if cfg["name_col"]    in cols else None
            company_col = cfg["company_col"] if cfg["company_col"] in cols else None
            niche_col   = cfg["niche_col"]   if cfg["niche_col"]   in cols else None
            status_col  = cfg["status_col"]  if cfg["status_col"]  in cols else None
            id_col      = cfg["id_col"]      if cfg["id_col"]      in cols else "id"

            if email_col not in cols:
                log.warning("Keine email-Spalte in %s.%s", db_path.name, table)
                conn.close()
                continue

            # Leads laden
            where_clauses = []
            params: List[Any] = []
            if status_col:
                where_clauses.append(f"{status_col} IN ('queued', 'new', 'pending')")
            if "sent" in cols:
                where_clauses.append("(sent IS NULL OR sent = 0)")
            elif "sent_count" in cols:
                where_clauses.append("(sent_count IS NULL OR sent_count = 0)")

            sql = f"SELECT * FROM {table}"
            if where_clauses:
                sql += " WHERE " + " OR ".join(where_clauses)
            sql += f" LIMIT {remaining}"

            rows = conn.execute(sql, params).fetchall()

            for row in rows:
                email = (row[email_col] if email_col in dict(zip(cols, row)) else "").strip()
                # row is a Row object
                row_dict = dict(row)
                email = row_dict.get(email_col, "").strip()
                if not email or "@" not in email:
                    continue

                name    = row_dict.get(name_col,    "") if name_col    else ""
                company = row_dict.get(company_col, "") if company_col else ""
                niche   = row_dict.get(niche_col,   "smart home") if niche_col else "smart home"
                lead_id = row_dict.get(id_col, 0)

                # Email generieren
                subject, html_body = await _generate_lead_email(email, name, company, niche)

                # Senden
                ok = await _send_email(email, subject, html_body)

                # DB aktualisieren
                try:
                    update_parts = []
                    upd_params   = []
                    if status_col and status_col in cols:
                        update_parts.append(f"{status_col}='sent'")
                    if "sent" in cols:
                        update_parts.append("sent=1")
                    if "sent_count" in cols:
                        update_parts.append("sent_count=COALESCE(sent_count,0)+1")
                    if "last_sent" in cols:
                        update_parts.append("last_sent=datetime('now')")
                    if update_parts:
                        conn.execute(
                            f"UPDATE {table} SET {', '.join(update_parts)} WHERE {id_col}=?",
                            (lead_id,)
                        )
                        conn.commit()
                except Exception as ue:
                    log.warning("DB-Update Fehler: %s", ue)

                if ok:
                    sent_total += 1
                    remaining  -= 1
                else:
                    failed_total += 1

                await asyncio.sleep(0.2)
                if remaining <= 0:
                    break

            conn.close()

        except Exception as e:
            log.error("Lead-Blast DB %s Fehler: %s", db_path.name, e)

    result = {
        "sent":              sent_total,
        "failed":            failed_total,
        "databases_checked": dbs_checked,
    }
    log.info("Lead-Blast abgeschlossen: %s", result)
    return result


async def _generate_lead_email(email: str, name: str, company: str,
                                niche: str) -> Tuple[str, str]:
    """Generiert eine personalisierte Lead-Email via Claude Haiku oder Template."""
    subject = f"Smarte Lösungen für {company or 'Ihr Unternehmen'} — {SHOP_NAME}"
    anrede  = f"Liebe/r {name}" if name else "Liebes Team"
    company_str = company or "Ihr Unternehmen"

    if ANTHROPIC_KEY:
        prompt = (
            f"Schreibe eine kurze, professionelle B2B-Akquise-Email auf Deutsch "
            f"für ein Unternehmen aus der Branche '{niche}'. "
            f"Absender: {SHOP_NAME} (Online-Shop für Smart-Home & Tech-Produkte). "
            f"Empfänger: {company_str}. "
            f"Ton: freundlich, professionell, keine aufdringliche Werbung. "
            f"Erwähne konkret: Smart-Home-Lösungen, schnelle Lieferung, Qualität. "
            f"Am Ende: Einladung zu {SHOP_URL}. "
            f"Nur den Email-Body als Plain Text ausgeben (kein HTML, keine Überschriften)."
        )
        body_text = await _claude(prompt, max_tokens=300)
    else:
        body_text = (
            f"vielen Dank für Ihr Interesse an modernen Smart-Home-Lösungen.\n\n"
            f"Bei {SHOP_NAME} finden Sie hochwertige Produkte für {niche} — "
            f"von intelligenten Beleuchtungssystemen bis hin zu Energie-Monitoring.\n\n"
            f"Entdecken Sie unser Sortiment: {SHOP_URL}\n\n"
            f"Mit freundlichen Grüßen,\nDas {SHOP_NAME}-Team"
        )

    html = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:580px;margin:0 auto;padding:20px;color:#333">
  <div style="border-top:3px solid #2563eb;padding-top:15px;margin-bottom:20px">
    <strong style="color:#2563eb;font-size:1.1rem">{SHOP_NAME}</strong>
  </div>
  <p>{anrede},</p>
  <div style="line-height:1.7;white-space:pre-line">{body_text}</div>
  <div style="margin:25px 0">
    <a href="{SHOP_URL}" style="background:#2563eb;color:#fff;padding:12px 28px;border-radius:5px;text-decoration:none;font-weight:bold;display:inline-block">
      Jetzt entdecken →
    </a>
  </div>
  <hr style="border:none;border-top:1px solid #eee;margin:20px 0">
  <p style="color:#aaa;font-size:0.75rem">
    {SHOP_NAME} · <a href="{SHOP_URL}/pages/abmelden?email={email}" style="color:#aaa">Abmelden</a>
  </p>
</body></html>"""

    return subject, html


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: SEO AUTO-BLOGGER
# ═══════════════════════════════════════════════════════════════════════════════

_SEO_TOPICS = [
    "Smart Home Einsteiger-Guide 2026",
    "Die besten Smart-Home-Gadgets für Energiesparen",
    "Balkonkraftwerk kaufen — Ratgeber 2026",
    "Smart Home Sicherheitssysteme Vergleich",
    "Powerstation für Camping und Outdoor",
    "Smarte Beleuchtung: Tipps und Produkte",
    "IoT-Geräte im Alltag — Was wirklich nützlich ist",
    "Off-Grid leben mit Solar und Powerstation",
    "Smart Home für Mieter — was ist erlaubt?",
    "Gadgets als Geschenkidee — Tech-Highlights",
    "Energiekosten senken mit Smart-Home-Technologie",
    "WiFi-Steckdosen im Test — Welche lohnt sich?",
    "Smarte Thermostate — Heizkosten sparen",
    "Solarmodul-Sets für den Balkon — Komplett-Guide",
    "Überwachungskamera smart: Was man beachten muss",
]

async def publish_seo_article() -> Dict:
    """
    Publiziert 1 SEO-Artikel pro Tag auf dem Shopify-Blog.
    Returns: {article_id: str, title: str, indexed: bool}
    """
    if not SHOP_TOKEN:
        return {"error": "SHOPIFY_ADMIN_API_TOKEN fehlt", "article_id": "", "indexed": False}

    # Thema wählen — noch nicht veröffentlicht
    conn = _db()
    published_slugs = {
        row[0] for row in conn.execute("SELECT slug FROM seo_articles").fetchall()
    }
    conn.close()

    available = [
        t for t in _SEO_TOPICS
        if _slugify(t) not in published_slugs
    ]
    if not available:
        # Alle Themen durch → zufällig wiederholen
        available = _SEO_TOPICS
    topic = random.choice(available)
    slug  = _slugify(topic)

    log.info("SEO-Artikel: '%s'", topic)

    # Artikel generieren
    title     = topic
    body_html = ""

    if ANTHROPIC_KEY:
        prompt = (
            f"Schreibe einen deutschen SEO-Blogartikel (600 Wörter) über '{topic}'. "
            f"Format: HTML mit <h2>/<h3>/<p>/<ul>/<li> Tags. Keine Markdown-Syntax. "
            f"Natürlicher Ton, praktische Tipps, Smart-Home / Tech-Fokus. "
            f"Am Ende ein kurzer CTA mit Link zu {SHOP_URL}. "
            f"Nur HTML-Body-Inhalt ausgeben, kein <html>/<head>/<body>-Tag."
        )
        body_html = await _claude(prompt, max_tokens=1200)

    if not body_html:
        # Fallback-Template
        body_html = f"""
<h2>Warum {topic} wichtig ist</h2>
<p>Smart-Home-Technologie verändert unseren Alltag grundlegend. Immer mehr Haushalte setzen auf
intelligente Lösungen, die Komfort, Sicherheit und Energieeffizienz vereinen.</p>
<h2>Die wichtigsten Vorteile</h2>
<ul>
  <li>Energie sparen durch intelligente Steuerung</li>
  <li>Mehr Komfort durch Automatisierung</li>
  <li>Sicherheit durch smarte Überwachung</li>
  <li>Einfache Installation, kein Fachmann nötig</li>
</ul>
<h2>Unsere Empfehlung</h2>
<p>Bei {SHOP_NAME} finden Sie eine große Auswahl an hochwertigen Smart-Home-Produkten
zu günstigen Preisen — mit schneller Lieferung und 30 Tagen Rückgaberecht.</p>
<p><a href="{SHOP_URL}">Jetzt entdecken →</a></p>
""".strip()

    article_id = ""
    indexed    = False

    async with aiohttp.ClientSession() as session:
        # Blog-ID holen / erstellen
        blog_id = await _get_or_create_blog(session)
        if not blog_id:
            return {"error": "Blog-ID nicht gefunden", "article_id": "", "indexed": False}

        # Artikel erstellen
        payload = {
            "article": {
                "title":      title,
                "body_html":  body_html,
                "published":  True,
                "tags":       "smart-home, ratgeber, technik, 2026",
                "handle":     slug,
            }
        }
        resp = await _shopify_post(session, f"blogs/{blog_id}/articles.json", payload)
        article = resp.get("article", {})
        article_id = str(article.get("id", ""))

        if article_id:
            log.info("SEO-Artikel veröffentlicht: %s (ID: %s)", title, article_id)

            # State speichern
            conn = _db()
            conn.execute(
                "INSERT OR IGNORE INTO seo_articles (title, slug, article_id) VALUES (?,?,?)",
                (title, slug, article_id)
            )
            conn.commit()
            conn.close()

            # IndexNow ping
            article_url = f"{SHOP_URL}/blogs/news/{slug}"
            indexed = await _indexnow_ping(article_url)
        else:
            log.warning("SEO-Artikel konnte nicht veröffentlicht werden: %s", resp)

    result = {"article_id": article_id, "title": title, "indexed": indexed, "slug": slug}
    log.info("SEO-Artikel: %s", result)
    return result


async def _get_or_create_blog(session: aiohttp.ClientSession) -> Optional[str]:
    """Gibt erste Blog-ID zurück oder erstellt einen neuen Blog."""
    data = await _shopify_get(session, "blogs.json")
    blogs = data.get("blogs", [])
    if blogs:
        return str(blogs[0]["id"])

    # Blog erstellen
    resp = await _shopify_post(session, "blogs.json",
                               {"blog": {"title": "Smart Home & Tech Blog", "commentable": "no"}})
    blog = resp.get("blog", {})
    bid = str(blog.get("id", ""))
    if bid:
        log.info("Blog erstellt: ID=%s", bid)
        return bid
    return None


async def _indexnow_ping(url: str) -> bool:
    """Sendet URL an IndexNow (Bing + allgemein)."""
    key = _e("INDEXNOW_KEY", INDEXNOW_KEY)
    endpoints = [
        "https://api.indexnow.org/indexnow",
        "https://www.bing.com/indexnow",
    ]
    payload = {"host": SHOP_DOMAIN, "key": key, "urlList": [url]}
    success = False
    try:
        async with aiohttp.ClientSession() as s:
            for ep in endpoints:
                try:
                    async with s.post(ep, json=payload,
                                      timeout=aiohttp.ClientTimeout(total=10)) as r:
                        if r.status in (200, 202):
                            success = True
                            log.info("IndexNow ping OK (%s): %s", ep, url)
                except Exception as ie:
                    log.debug("IndexNow %s Fehler: %s", ep, ie)
    except Exception as e:
        log.warning("IndexNow Fehler: %s", e)
    return success


def _slugify(text: str) -> str:
    text = text.lower()
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:60]


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: SOCIAL TRAFFIC BOOSTER
# ═══════════════════════════════════════════════════════════════════════════════

async def post_product_to_all_platforms() -> Dict:
    """
    Holt ein zufälliges aktives Shopify-Produkt und postet auf:
    1. Facebook Page (FACEBOOK_PAGE_TOKEN_AIITEC)
    2. Instagram (via Facebook Graph API)
    3. Telegram Channel (TELEGRAM_CHAT_ID)
    Returns: {platforms_posted: list, product: str}
    """
    platforms_posted = []
    product_title    = ""

    if not SHOP_TOKEN:
        return {"error": "SHOPIFY_ADMIN_API_TOKEN fehlt", "platforms_posted": [], "product": ""}

    # Zufälliges aktives Produkt holen
    try:
        async with aiohttp.ClientSession() as session:
            data = await _shopify_get(
                session,
                "products.json?limit=250&status=active&fields=id,title,handle,images,variants,body_html"
            )
            products = data.get("products", [])

        products_with_img = [p for p in products if p.get("images")]
        if not products_with_img:
            products_with_img = products

        if not products_with_img:
            return {"error": "Keine aktiven Produkte gefunden", "platforms_posted": [], "product": ""}

        product = random.choice(products_with_img)
        product_title  = product.get("title", "")
        product_handle = product.get("handle", "")
        product_url    = f"{SHOP_URL}/products/{product_handle}"
        image_url      = (product.get("images") or [{}])[0].get("src", "")
        price          = ""
        variants       = product.get("variants", [])
        if variants:
            price = variants[0].get("price", "")

    except Exception as e:
        log.error("Produkt-Abruf für Social-Post Fehler: %s", e)
        return {"error": str(e), "platforms_posted": [], "product": ""}

    # Caption generieren
    caption = await _generate_social_caption(product_title, product_url, price)

    # ── 1. Telegram ──
    try:
        tg_text = (
            f"🛍️ <b>{product_title}</b>\n\n"
            f"{caption}\n\n"
            f"👉 <a href='{product_url}'>Jetzt kaufen</a>"
        )
        await _tg(tg_text)
        platforms_posted.append("telegram")
    except Exception as e:
        log.warning("Telegram Social-Post Fehler: %s", e)

    # ── 2. Facebook ──
    if FB_PAGE_TOKEN and FB_PAGE_ID:
        try:
            fb_message = (
                f"{product_title}\n\n{caption}\n\nJetzt kaufen: {product_url}"
            )
            fb_payload: Dict[str, Any] = {
                "message": fb_message,
                "access_token": FB_PAGE_TOKEN,
            }
            if image_url:
                fb_payload["link"] = product_url

            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{FB_BASE}/{FB_PAGE_ID}/feed",
                    params=fb_payload,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    fb_resp = await r.json()
                    if fb_resp.get("id"):
                        platforms_posted.append("facebook")
                        log.info("Facebook Post veröffentlicht: %s", fb_resp["id"])
                    else:
                        log.warning("Facebook Post Fehler: %s", fb_resp)
        except Exception as e:
            log.warning("Facebook Post Fehler: %s", e)

    # ── 3. Instagram (nur wenn Bild vorhanden) ──
    if FB_PAGE_TOKEN and IG_USER_ID and image_url:
        try:
            ig_caption = f"{product_title}\n\n{caption}\n\n{product_url}\n\n#SmartHome #Gadgets #Tech #IoT #Smart #Technik"
            async with aiohttp.ClientSession() as s:
                # Schritt 1: Media Container erstellen
                async with s.post(
                    f"{FB_BASE}/{IG_USER_ID}/media",
                    params={
                        "image_url":    image_url,
                        "caption":      ig_caption,
                        "access_token": FB_PAGE_TOKEN,
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as r:
                    container = await r.json()
                    container_id = container.get("id")

                if container_id:
                    await asyncio.sleep(5)  # Instagram braucht kurz
                    # Schritt 2: Veröffentlichen
                    async with s.post(
                        f"{FB_BASE}/{IG_USER_ID}/media_publish",
                        params={
                            "creation_id":  container_id,
                            "access_token": FB_PAGE_TOKEN,
                        },
                        timeout=aiohttp.ClientTimeout(total=20),
                    ) as r2:
                        ig_resp = await r2.json()
                        if ig_resp.get("id"):
                            platforms_posted.append("instagram")
                            log.info("Instagram Post veröffentlicht: %s", ig_resp["id"])
                        else:
                            log.warning("Instagram Publish Fehler: %s", ig_resp)
        except Exception as e:
            log.warning("Instagram Post Fehler: %s", e)

    result = {"platforms_posted": platforms_posted, "product": product_title}
    log.info("Social-Post: %s → %s", product_title, platforms_posted)
    return result


async def _generate_social_caption(title: str, url: str, price: str) -> str:
    """Generiert eine plattformoptimierte deutsche Caption."""
    price_str = f"Ab €{price} " if price else ""
    if ANTHROPIC_KEY:
        prompt = (
            f"Schreibe eine kurze, ansprechende Social-Media-Caption auf Deutsch (max. 2 Sätze) "
            f"für das Produkt: '{title}'. {price_str}"
            f"Ton: modern, begeistert, smart. Keine Hashtags einfügen. Kein Link-Text."
        )
        caption = await _claude(prompt, max_tokens=120)
        if caption:
            return caption

    # Fallback
    templates = [
        f"Upgrade dein Smart Home — {title} ist jetzt verfügbar! {price_str}Sichere Zahlung · Schnelle Lieferung.",
        f"Entdecke {title} — Qualität für moderne Haushalte! {price_str}Jetzt bestellen.",
        f"Smart, effizient, stylish: {title}. {price_str}Kostenloser Versand ab €50.",
    ]
    return random.choice(templates)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7: DAILY SCALING CYCLE
# ═══════════════════════════════════════════════════════════════════════════════

async def run_daily_scaling_cycle() -> Dict:
    """
    Master-Funktion — führt alle Skalierungsaktionen nacheinander aus:
    1. optimize_product_catalog()
    2. run_abandoned_cart_recovery()
    3. blast_all_queued_leads(80)
    4. publish_seo_article()
    5. post_product_to_all_platforms()
    6. inject_trust_signals()
    Returns: {cycle_started: str, results: dict, revenue_estimate: float}
    """
    cycle_started = datetime.now(timezone.utc).isoformat()
    t0 = asyncio.get_event_loop().time()
    results: Dict[str, Any] = {}

    await _tg("🚀 <b>Shop-Skalierungszyklus gestartet</b>\nAlle 6 Aktionen werden ausgeführt…")

    # 1. Produkt-Optimierung
    log.info("[1/6] Produkt-Optimierung…")
    try:
        r = await optimize_product_catalog()
        results["product_optimization"] = r
        results["products_optimized"]   = r.get("optimized", 0)
    except Exception as e:
        log.error("Produkt-Optimierung Fehler: %s", e)
        results["product_optimization"] = {"error": str(e)}

    await asyncio.sleep(2)

    # 2. Abandoned-Cart-Recovery
    log.info("[2/6] Cart-Recovery…")
    try:
        r = await run_abandoned_cart_recovery()
        results["cart_recovery"] = r
        results["emails_sent"]   = r.get("emails_sent", 0)
    except Exception as e:
        log.error("Cart-Recovery Fehler: %s", e)
        results["cart_recovery"] = {"error": str(e)}

    await asyncio.sleep(2)

    # 3. Lead-Blast
    log.info("[3/6] Lead-Blast…")
    try:
        r = await blast_all_queued_leads(max_per_run=80)
        results["lead_blast"]   = r
        prev_sent = results.get("emails_sent", 0)
        results["emails_sent"]  = prev_sent + r.get("sent", 0)
    except Exception as e:
        log.error("Lead-Blast Fehler: %s", e)
        results["lead_blast"] = {"error": str(e)}

    await asyncio.sleep(2)

    # 4. SEO-Artikel
    log.info("[4/6] SEO-Artikel…")
    try:
        r = await publish_seo_article()
        results["seo_article"] = r
    except Exception as e:
        log.error("SEO-Artikel Fehler: %s", e)
        results["seo_article"] = {"error": str(e)}

    await asyncio.sleep(2)

    # 5. Social-Post
    log.info("[5/6] Social-Post…")
    try:
        r = await post_product_to_all_platforms()
        results["social_post"] = r
    except Exception as e:
        log.error("Social-Post Fehler: %s", e)
        results["social_post"] = {"error": str(e)}

    await asyncio.sleep(2)

    # 6. Trust-Signale
    log.info("[6/6] Trust-Signale…")
    try:
        r = await inject_trust_signals()
        results["trust_signals"] = r
    except Exception as e:
        log.error("Trust-Signale Fehler: %s", e)
        results["trust_signals"] = {"error": str(e)}

    duration = asyncio.get_event_loop().time() - t0

    # DB-Log
    try:
        conn = _db()
        conn.execute("""
            INSERT INTO scaling_runs
              (products_optimized, carts_recovered, emails_sent, articles_published,
               social_posts, duration_sec)
            VALUES (?,?,?,?,?,?)
        """, (
            results.get("products_optimized", 0),
            results.get("cart_recovery", {}).get("emails_sent", 0),
            results.get("emails_sent", 0),
            1 if results.get("seo_article", {}).get("article_id") else 0,
            len(results.get("social_post", {}).get("platforms_posted", [])),
            round(duration, 1),
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("Scaling-Run DB-Log Fehler: %s", e)

    # Revenue-Schätzung (grob: 1% Conversion, AOV €45)
    emails_sent   = results.get("emails_sent", 0)
    revenue_est   = round(emails_sent * 0.01 * 45, 2)

    # Telegram-Zusammenfassung
    optimized   = results.get("products_optimized", 0)
    cart_emails = results.get("cart_recovery", {}).get("emails_sent", 0)
    lead_emails = results.get("lead_blast", {}).get("sent", 0)
    seo_title   = results.get("seo_article", {}).get("title", "–")
    seo_ok      = bool(results.get("seo_article", {}).get("article_id"))
    platforms   = results.get("social_post", {}).get("platforms_posted", [])
    discounts   = results.get("trust_signals", {}).get("discounts_created", 0)

    summary = (
        f"✅ <b>Skalierungszyklus abgeschlossen</b> ({round(duration)}s)\n\n"
        f"• 🛍️ Produkte optimiert: <b>{optimized}</b>\n"
        f"• 🛒 Cart-Recovery Emails: <b>{cart_emails}</b>\n"
        f"• 📧 Lead-Emails gesendet: <b>{lead_emails}</b>\n"
        f"• 📝 SEO-Artikel: {'✅ ' + seo_title[:40] if seo_ok else '❌ fehlgeschlagen'}\n"
        f"• 📱 Social-Posts: <b>{', '.join(platforms) or '–'}</b>\n"
        f"• 💳 Discount-Codes: <b>{discounts}</b>\n\n"
        f"💰 Potenzielle Revenue-Schätzung: ~€{revenue_est}"
    )
    await _tg(summary)

    return {
        "cycle_started":    cycle_started,
        "results":          results,
        "revenue_estimate": revenue_est,
        "duration_sec":     round(duration, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8: STATS ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════════

async def get_scaling_stats() -> Dict:
    """Gibt aktuelle Metriken für das Dashboard zurück."""
    stats: Dict[str, Any] = {
        "engine":   "ShopScalingEngine v1.0",
        "shop_url": SHOP_URL,
        "smtp_accounts": len(_build_smtp_pool()),
        "anthropic_configured": bool(ANTHROPIC_KEY),
        "fb_configured":        bool(FB_PAGE_TOKEN),
        "last_runs":            [],
        "seo_articles_total":   0,
        "cart_recovery_total":  0,
        "cart_recovery_sent":   0,
    }

    try:
        conn = _db()

        # Letzte Scaling-Runs
        runs = conn.execute(
            "SELECT * FROM scaling_runs ORDER BY id DESC LIMIT 5"
        ).fetchall()
        stats["last_runs"] = [dict(r) for r in runs]

        # SEO-Artikel Zähler
        row = conn.execute("SELECT COUNT(*) FROM seo_articles").fetchone()
        stats["seo_articles_total"] = row[0] if row else 0

        # Cart-Recovery Statistiken
        row2 = conn.execute("SELECT COUNT(*), SUM(email_sent) FROM cart_recovery").fetchone()
        if row2:
            stats["cart_recovery_total"] = row2[0] or 0
            stats["cart_recovery_sent"]  = int(row2[1] or 0)

        # Gesamt-Emails aus allen Runs
        row3 = conn.execute(
            "SELECT SUM(emails_sent), SUM(products_optimized) FROM scaling_runs"
        ).fetchone()
        if row3:
            stats["total_emails_sent_all_time"]      = int(row3[0] or 0)
            stats["total_products_optimized_all_time"] = int(row3[1] or 0)

        conn.close()
    except Exception as e:
        log.warning("Stats DB Fehler: %s", e)
        stats["db_error"] = str(e)

    # Shopify Produkt-Überblick
    if SHOP_TOKEN:
        try:
            async with aiohttp.ClientSession() as session:
                pd = await _shopify_get(session, "products/count.json?status=active")
                stats["shopify_active_products"] = pd.get("count", "?")
        except Exception as e:
            stats["shopify_products_error"] = str(e)

    stats["generated_at"] = datetime.now(timezone.utc).isoformat()
    return stats
