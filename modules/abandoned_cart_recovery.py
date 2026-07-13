#!/usr/bin/env python3
"""
Abandoned Cart Recovery — ineedit.com.co
3-stufige E-Mail-Sequenz: sofort / +1h / +24h mit Rabattcode.
State-Tracking in SQLite: data/abandoned_cart.db
E-Mail-Versand via GMAIL_USER_5 / GMAIL_APP_PASSWORD_5 (aiitecbuuss@gmail.com).
Telegram-Alerts nach jedem Lauf.
"""

import asyncio
import logging
import os
import smtplib
import sqlite3
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp

# Env-Datei laden (muss vor os.getenv-Aufrufen stehen)
try:
    from dotenv import load_dotenv
    load_dotenv("/Users/rudolfsarkany/supermegabot/.env")
except ImportError:
    pass  # dotenv optional — Railway liefert Vars direkt

log = logging.getLogger("AbandonedCartRecovery")

# ── Konstanten ────────────────────────────────────────────────────────────────
_DB_PATH = Path(os.getenv("DATA_DIR", "/Users/rudolfsarkany/supermegabot/data")) / "abandoned_cart.db"
_SHOP_NAME = "I Want That! I Need It!"
_SHOP_DOMAIN = "ineedit.com.co"
_DISCOUNT_CODE = "RESCUE10"

# Mindest-Alter eines Warenkorbs bevor Stage-1 gesendet wird (Standard: 60 Min.)
_STAGE1_DELAY_MIN  = int(os.getenv("CART_STAGE1_DELAY_MIN", "60"))
# Stage-2 nach X Minuten nach Stage-1
_STAGE2_DELAY_MIN  = int(os.getenv("CART_STAGE2_DELAY_MIN", "60"))
# Stage-3 nach X Minuten nach Stage-1
_STAGE3_DELAY_MIN  = int(os.getenv("CART_STAGE3_DELAY_MIN", "1440"))  # 24h
# Carts älter als X Stunden werden nicht mehr verarbeitet
_MAX_AGE_HOURS     = int(os.getenv("CART_MAX_AGE_HOURS", "72"))


# ── SQLite DB ─────────────────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cart_recoveries (
            checkout_token  TEXT PRIMARY KEY,
            email           TEXT NOT NULL,
            first_name      TEXT DEFAULT '',
            total_price     TEXT DEFAULT '0.00',
            currency        TEXT DEFAULT 'EUR',
            recover_url     TEXT DEFAULT '',
            items_json      TEXT DEFAULT '[]',
            cart_created_at TEXT NOT NULL,
            stage1_sent_at  TEXT,
            stage2_sent_at  TEXT,
            stage3_sent_at  TEXT,
            is_completed    INTEGER DEFAULT 0,
            inserted_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
    """)
    conn.commit()
    return conn


def _upsert_cart(conn: sqlite3.Connection, checkout_token: str, email: str,
                 first_name: str, total_price: str, currency: str,
                 recover_url: str, items_json: str, cart_created_at: str) -> None:
    conn.execute("""
        INSERT INTO cart_recoveries
            (checkout_token, email, first_name, total_price, currency,
             recover_url, items_json, cart_created_at)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(checkout_token) DO NOTHING
    """, (checkout_token, email, first_name, total_price, currency,
          recover_url, items_json, cart_created_at))
    conn.commit()


def _mark_stage(conn: sqlite3.Connection, checkout_token: str, stage: int) -> None:
    col = {1: "stage1_sent_at", 2: "stage2_sent_at", 3: "stage3_sent_at"}.get(stage)
    if not col:
        return
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(f"UPDATE cart_recoveries SET {col}=? WHERE checkout_token=?",
                 (now_iso, checkout_token))
    conn.commit()


def _mark_completed(conn: sqlite3.Connection, checkout_token: str) -> None:
    conn.execute("UPDATE cart_recoveries SET is_completed=1 WHERE checkout_token=?",
                 (checkout_token,))
    conn.commit()


def _get_total_db_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM cart_recoveries").fetchone()
    return row[0] if row else 0


def _get_pending_stage2(conn: sqlite3.Connection, now: datetime) -> List[sqlite3.Row]:
    cutoff = (now - timedelta(minutes=_STAGE2_DELAY_MIN)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return conn.execute("""
        SELECT * FROM cart_recoveries
        WHERE is_completed=0
          AND stage1_sent_at IS NOT NULL
          AND stage2_sent_at IS NULL
          AND stage1_sent_at <= ?
    """, (cutoff,)).fetchall()


def _get_pending_stage3(conn: sqlite3.Connection, now: datetime) -> List[sqlite3.Row]:
    cutoff = (now - timedelta(minutes=_STAGE3_DELAY_MIN)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return conn.execute("""
        SELECT * FROM cart_recoveries
        WHERE is_completed=0
          AND stage1_sent_at IS NOT NULL
          AND stage3_sent_at IS NULL
          AND stage1_sent_at <= ?
    """, (cutoff,)).fetchall()


# ── E-Mail-Templates ──────────────────────────────────────────────────────────

def _subject_stage1() -> str:
    return f"Dein Warenkorb wartet auf dich! \U0001F6D2 {_SHOP_NAME}"

def _subject_stage2() -> str:
    return f"Nur noch wenige auf Lager! ⚠️ {_SHOP_NAME}"

def _subject_stage3() -> str:
    return f"10% Rabatt nur fuer dich: {_DISCOUNT_CODE} \U0001F381 {_SHOP_NAME}"


def _html_base(header_title: str, header_sub: str, greeting: str,
               intro_html: str, items_html: str, total: str, currency: str,
               cta_url: str, cta_label: str, badge_html: str,
               note_html: str) -> str:
    total_row = ""
    try:
        if float(total or "0") > 0:
            total_row = f"""
            <tr>
              <td style="padding:16px 40px 0;">
                <p style="color:#1a1a1a;font-size:16px;font-weight:700;margin:0;">
                  Gesamtbetrag: {currency}&nbsp;{total}
                </p>
              </td>
            </tr>"""
    except ValueError:
        pass

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{header_title} - {_SHOP_NAME}</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;
             font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0"
       style="background:#f5f5f5;padding:30px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0"
           style="background:#fff;border-radius:12px;overflow:hidden;
                  box-shadow:0 2px 12px rgba(0,0,0,.08);">

      <!-- Header -->
      <tr>
        <td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,
                   #0f3460 100%);padding:36px 40px;text-align:center;">
          <h1 style="color:#fff;margin:0;font-size:26px;font-weight:700;
                     letter-spacing:-.5px;">{_SHOP_NAME}</h1>
          <p style="color:rgba(255,255,255,.7);margin:6px 0 0;font-size:14px;">
            Smart &amp; Modern Shopping
          </p>
        </td>
      </tr>

      <!-- Banner -->
      <tr>
        <td style="background:#fff8e7;padding:20px 40px;text-align:center;
                   border-bottom:2px solid #ffd700;">
          <h2 style="margin:8px 0 0;color:#1a1a1a;font-size:22px;
                     font-weight:700;">{header_title}</h2>
          <p style="margin:6px 0 0;color:#555;font-size:15px;">{header_sub}</p>
        </td>
      </tr>

      <!-- Greeting -->
      <tr>
        <td style="padding:30px 40px 10px;">
          <p style="color:#1a1a1a;font-size:16px;line-height:1.6;margin:0 0 16px;">
            {greeting}
          </p>
          {intro_html}
        </td>
      </tr>

      <!-- Items -->
      <tr>
        <td style="padding:0 40px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding-bottom:8px;">
                <strong style="color:#1a1a1a;font-size:15px;">Deine Artikel:</strong>
              </td>
            </tr>
            {items_html}
          </table>
        </td>
      </tr>

      <!-- Total -->
      {total_row}

      <!-- CTA -->
      <tr>
        <td style="padding:28px 40px;">
          <table cellpadding="0" cellspacing="0" width="100%">
            <tr>
              <td align="center">
                <a href="{cta_url}"
                   style="display:inline-block;
                          background:linear-gradient(135deg,#2563eb,#1d4ed8);
                          color:#fff;font-size:17px;font-weight:700;
                          text-decoration:none;padding:16px 48px;
                          border-radius:8px;letter-spacing:.3px;
                          box-shadow:0 4px 14px rgba(37,99,235,.4);">
                  {cta_label}
                </a>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- Badge / Promo -->
      {badge_html}

      <!-- Note -->
      {note_html}

      <!-- Footer link -->
      <tr>
        <td style="padding:0 40px 32px;text-align:center;">
          <a href="https://{_SHOP_DOMAIN}"
             style="color:#2563eb;font-size:14px;text-decoration:none;">
            Weiter einkaufen auf {_SHOP_DOMAIN} &rarr;
          </a>
        </td>
      </tr>

      <!-- Footer -->
      <tr>
        <td style="background:#1a1a2e;padding:24px 40px;text-align:center;">
          <p style="color:rgba(255,255,255,.5);font-size:12px;
                    margin:0;line-height:1.8;">
            {_SHOP_NAME} &bull; {_SHOP_DOMAIN}<br>
            Du erhaeltst diese E-Mail, weil du einen Kauf begonnen hast.
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


def _build_items_rows(items: List[Dict]) -> str:
    rows = ""
    for item in items[:5]:
        title = item.get("title", "Produkt")
        qty   = item.get("quantity", 1)
        price = item.get("price", "")
        img   = item.get("image", "")
        img_tag = (f"<img src='{img}' width='60' alt='{title}' "
                   "style='vertical-align:middle;border-radius:4px;"
                   "margin-right:12px;'>") if img else ""
        price_tag = (f"<br><span style='color:#2563eb;font-weight:600;'>"
                     f"{price}</span>") if price else ""
        rows += f"""
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid #f0f0f0;">
            {img_tag}
            <strong style="color:#1a1a1a;">{title}</strong>
            <span style="color:#666;font-size:13px;"> &times; {qty}</span>
            {price_tag}
          </td>
        </tr>"""
    return rows


def _trust_badges() -> str:
    return """
    <tr>
      <td style="padding:0 40px 28px;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="background:#f8faff;border-radius:8px;padding:16px 20px;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td width="33%" align="center" style="padding:0 8px;">
                    <p style="margin:0;font-size:20px;">&#x1F6E1;&#xFE0F;</p>
                    <p style="margin:4px 0 0;font-size:12px;color:#444;
                               font-weight:600;">Sichere Zahlung</p>
                    <p style="margin:2px 0 0;font-size:11px;color:#777;">
                      SSL-verschluesselt</p>
                  </td>
                  <td width="33%" align="center"
                      style="padding:0 8px;border-left:1px solid #e0e7ff;
                             border-right:1px solid #e0e7ff;">
                    <p style="margin:0;font-size:20px;">&#x1F4E6;</p>
                    <p style="margin:4px 0 0;font-size:12px;color:#444;
                               font-weight:600;">Gratis Versand</p>
                    <p style="margin:2px 0 0;font-size:11px;color:#777;">
                      ab &euro;49 Bestellwert</p>
                  </td>
                  <td width="33%" align="center" style="padding:0 8px;">
                    <p style="margin:0;font-size:20px;">&#x1F504;</p>
                    <p style="margin:4px 0 0;font-size:12px;color:#444;
                               font-weight:600;">14 Tage Rueckgabe</p>
                    <p style="margin:2px 0 0;font-size:11px;color:#777;">
                      Kein Risiko</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def _build_stage1_email(first_name: str, items: List[Dict], total: str,
                         currency: str, recover_url: str) -> str:
    greeting = f"Hallo {first_name}," if first_name else "Hallo,"
    intro = """<p style="color:#444;font-size:15px;line-height:1.7;margin:0 0 20px;">
      Du hast deinen Einkauf bei <strong>I Want That! I Need It!</strong>
      noch nicht abgeschlossen. Kein Problem &mdash; dein Warenkorb wurde
      gespeichert und wartet auf dich!
    </p>"""
    note = """<tr>
      <td style="padding:0 40px 24px;">
        <p style="color:#888;font-size:13px;line-height:1.6;margin:0;
                   text-align:center;background:#fff8f0;border-radius:6px;
                   padding:12px 16px;border-left:3px solid #f59e0b;">
          &#x23F0; Dein Warenkorb ist nur begrenzt reserviert &mdash;
          jetzt kaufen und Lieblingsartikel sichern!
        </p>
      </td>
    </tr>"""
    return _html_base(
        header_title="Dein Warenkorb wartet!",
        header_sub="Du hast deinen Einkauf noch nicht abgeschlossen.",
        greeting=greeting,
        intro_html=intro,
        items_html=_build_items_rows(items),
        total=total,
        currency=currency,
        cta_url=recover_url,
        cta_label="&#x1F6D2;&nbsp; Warenkorb ansehen",
        badge_html=_trust_badges(),
        note_html=note,
    )


def _build_stage2_email(first_name: str, items: List[Dict], total: str,
                         currency: str, recover_url: str) -> str:
    greeting = f"Hallo {first_name}," if first_name else "Hallo,"
    intro = """<p style="color:#444;font-size:15px;line-height:1.7;margin:0 0 20px;">
      Wir wollten dich noch einmal daran erinnern: Einige Artikel in deinem
      Warenkorb sind sehr beliebt und koennen bald ausverkauft sein.
      Sicher dir deine Produkte jetzt!
    </p>"""
    note = """<tr>
      <td style="padding:0 40px 24px;">
        <p style="color:#888;font-size:13px;line-height:1.6;margin:0;
                   text-align:center;background:#fff0f0;border-radius:6px;
                   padding:12px 16px;border-left:3px solid #ef4444;">
          &#x26A0;&#xFE0F; Hohe Nachfrage! Nur noch wenige Stueck auf Lager &mdash;
          nicht verpassen!
        </p>
      </td>
    </tr>"""
    return _html_base(
        header_title="Nur noch wenige auf Lager!",
        header_sub="Deine Artikel sind sehr beliebt &mdash; schnell sichern!",
        greeting=greeting,
        intro_html=intro,
        items_html=_build_items_rows(items),
        total=total,
        currency=currency,
        cta_url=recover_url,
        cta_label="&#x26A0;&#xFE0F;&nbsp; Jetzt sichern",
        badge_html=_trust_badges(),
        note_html=note,
    )


def _build_stage3_email(first_name: str, items: List[Dict], total: str,
                         currency: str, recover_url: str) -> str:
    greeting = f"Hallo {first_name}," if first_name else "Hallo,"
    intro = f"""<p style="color:#444;font-size:15px;line-height:1.7;margin:0 0 16px;">
      Als kleines Dankeschoen haben wir exklusiv fuer dich einen
      <strong>10&nbsp;% Rabattcode</strong> vorbereitet:
    </p>
    <div style="background:#f0fdf4;border:2px dashed #22c55e;border-radius:10px;
                padding:20px;text-align:center;margin:0 0 20px;">
      <p style="margin:0;font-size:13px;color:#555;font-weight:600;
                letter-spacing:.5px;text-transform:uppercase;">Dein Rabattcode</p>
      <p style="margin:8px 0 0;font-size:32px;font-weight:900;color:#16a34a;
                letter-spacing:4px;">{_DISCOUNT_CODE}</p>
      <p style="margin:6px 0 0;font-size:13px;color:#777;">
        10&nbsp;% auf deinen gesamten Warenkorb &bull; einmalig gueltig
      </p>
    </div>
    <p style="color:#444;font-size:15px;line-height:1.7;margin:0 0 20px;">
      Gib den Code einfach an der Kasse ein. Das Angebot gilt nur fuer
      kurze Zeit!
    </p>"""
    note = """<tr>
      <td style="padding:0 40px 24px;">
        <p style="color:#888;font-size:13px;line-height:1.6;margin:0;
                   text-align:center;background:#f0fdf4;border-radius:6px;
                   padding:12px 16px;border-left:3px solid #22c55e;">
          &#x1F381; Dein exklusiver Rabatt laeuft bald ab &mdash;
          jetzt einloesen und sparen!
        </p>
      </td>
    </tr>"""
    return _html_base(
        header_title="10 % Rabatt nur fuer dich!",
        header_sub=f"Exklusiver Code: {_DISCOUNT_CODE}",
        greeting=greeting,
        intro_html=intro,
        items_html=_build_items_rows(items),
        total=total,
        currency=currency,
        cta_url=recover_url,
        cta_label=f"&#x1F381;&nbsp; Code {_DISCOUNT_CODE} einloesen",
        badge_html=_trust_badges(),
        note_html=note,
    )


# ── SMTP E-Mail-Versand ───────────────────────────────────────────────────────

def _send_smtp_sync(to_email: str, subject: str, html_body: str) -> bool:
    """Synchroner SMTP-Versand (wird im Executor ausgeführt)."""
    smtp_user = os.getenv("GMAIL_USER_5", os.getenv("GMAIL_USER", ""))
    smtp_pass = os.getenv("GMAIL_APP_PASSWORD_5", os.getenv("GMAIL_APP_PASSWORD", ""))
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not smtp_user or not smtp_pass:
        log.warning("GMAIL_USER_5 / GMAIL_APP_PASSWORD_5 nicht konfiguriert")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{_SHOP_NAME} <{smtp_user}>"
    msg["To"]      = to_email
    msg["Reply-To"] = f"support@{_SHOP_DOMAIN}"
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as srv:
            srv.starttls()
            srv.login(smtp_user, smtp_pass)
            srv.sendmail(smtp_user, to_email, msg.as_string())
        log.info("SMTP E-Mail gesendet an %s (Betreff: %s)", to_email, subject[:60])
        return True
    except smtplib.SMTPAuthenticationError as exc:
        log.error("SMTP-Authentifizierung fehlgeschlagen: %s", exc)
        return False
    except Exception as exc:
        log.error("SMTP-Fehler bei %s: %s", to_email, exc)
        return False


async def _send_email(to_email: str, subject: str, html_body: str) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _send_smtp_sync, to_email, subject, html_body)


# ── Telegram-Alert ────────────────────────────────────────────────────────────

async def _telegram_alert(session: aiohttp.ClientSession, message: str) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id   = os.getenv("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with session.post(url, json={"chat_id": chat_id,
                                           "text": message,
                                           "parse_mode": "HTML"}) as r:
            if r.status != 200:
                body = await r.text()
                log.warning("Telegram-Alert HTTP %s: %s", r.status, body[:100])
    except Exception as exc:
        log.warning("Telegram-Alert Fehler: %s", exc)


# ── Shopify: Abandoned Checkouts abrufen ──────────────────────────────────────

async def _fetch_shopify_checkouts(session: aiohttp.ClientSession) -> List[Dict]:
    token  = (os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or
              os.getenv("SHOPIFY_ACCESS_TOKEN", ""))
    domain = (os.getenv("SHOPIFY_SHOP_DOMAIN", "") or
              os.getenv("SHOPIFY_STORE_DOMAIN", ""))
    ver    = os.getenv("SHOPIFY_API_VERSION", "2024-10")

    if not token or not domain:
        log.error("SHOPIFY_ADMIN_API_TOKEN / SHOPIFY_SHOP_DOMAIN fehlen")
        return []

    base     = domain if domain.startswith("http") else f"https://{domain}"
    headers  = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    since    = (datetime.now(timezone.utc) - timedelta(hours=_MAX_AGE_HOURS)).strftime(
                "%Y-%m-%dT%H:%M:%SZ")

    url = (f"{base}/admin/api/{ver}/checkouts.json"
           f"?updated_at_min={since}&status=open&limit=250")

    try:
        async with session.get(url, headers=headers) as r:
            if r.status == 200:
                data = await r.json(content_type=None)
                carts = data.get("checkouts", [])
                log.info("Shopify: %d offene Warenkörbe gefunden", len(carts))
                return carts
            body = await r.text()
            log.error("Shopify checkouts HTTP %s: %s", r.status, body[:200])
            return []
    except Exception as exc:
        log.error("Shopify fetch Fehler: %s", exc)
        return []


# ── Cart-zu-Items konvertieren ────────────────────────────────────────────────

import json as _json

def _parse_line_items(checkout: Dict) -> Tuple[List[Dict], str]:
    items = []
    for li in checkout.get("line_items", []):
        img_src = ""
        fi = li.get("featured_image")
        if fi and isinstance(fi, dict):
            img_src = fi.get("url", "")
        items.append({
            "title":    li.get("title", "Produkt"),
            "quantity": li.get("quantity", 1),
            "price":    li.get("price", ""),
            "image":    img_src,
        })
    return items, _json.dumps(items, ensure_ascii=False)


def _recover_url(checkout: Dict) -> str:
    domain = (os.getenv("SHOPIFY_SHOP_DOMAIN", "") or
              os.getenv("SHOPIFY_STORE_DOMAIN", "") or _SHOP_DOMAIN)
    shop_base = domain if domain.startswith("http") else f"https://{domain}"
    return checkout.get("abandoned_checkout_url",
                        f"{shop_base.rstrip('/')}/cart")


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

async def run_abandoned_cart_recovery() -> str:
    """
    Hauptfunktion: Shopify-Warenkörbe holen, 3-stufige E-Mail-Sequenz ausführen.
    Gibt einen Zusammenfassungs-String zurück.
    """
    conn = _get_db()
    now  = datetime.now(timezone.utc)

    recovered_new  = 0  # Neue Carts (Stage 1 gesendet)
    emails_sent    = 0
    stage2_sent    = 0
    stage3_sent    = 0
    errors         = 0

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:

            # ── 1. Shopify: offene Checkouts holen ──────────────────────────
            checkouts = await _fetch_shopify_checkouts(session)

            stage1_cutoff = now - timedelta(minutes=_STAGE1_DELAY_MIN)
            old_cutoff    = now - timedelta(hours=_MAX_AGE_HOURS)

            for c in checkouts:
                email = c.get("email", "")
                completed = c.get("completed_at")
                token_key = c.get("token", "")

                if not email or not token_key or completed:
                    continue

                # Erstellungsdatum parsen
                created_raw = c.get("created_at", "")
                try:
                    created_at = datetime.fromisoformat(
                        created_raw.replace("Z", "+00:00"))
                except Exception:
                    continue

                # Zu alt?
                if created_at < old_cutoff:
                    continue

                # Noch zu frisch?
                if created_at > stage1_cutoff:
                    continue

                # Checkout-Daten extrahieren
                billing    = c.get("billing_address") or {}
                first_name = billing.get("first_name", "")
                total      = c.get("total_price", "0.00")
                currency   = c.get("currency", "EUR")
                rec_url    = _recover_url(c)
                items, items_json = _parse_line_items(c)

                cart_created_str = created_at.strftime("%Y-%m-%dT%H:%M:%SZ")

                # In DB eintragen (ON CONFLICT DO NOTHING)
                _upsert_cart(conn, token_key, email, first_name,
                             total, currency, rec_url, items_json,
                             cart_created_str)

                # Stage-1 noch nicht gesendet?
                row = conn.execute(
                    "SELECT stage1_sent_at FROM cart_recoveries WHERE checkout_token=?",
                    (token_key,)).fetchone()

                if row and row["stage1_sent_at"] is None:
                    subject = _subject_stage1()
                    html    = _build_stage1_email(first_name, items, total, currency, rec_url)
                    ok = await _send_email(email, subject, html)
                    if ok:
                        _mark_stage(conn, token_key, 1)
                        recovered_new += 1
                        emails_sent   += 1
                        log.info("Stage-1 gesendet an %s (Token: %s)", email, token_key[:12])
                    else:
                        errors += 1

                await asyncio.sleep(0.5)  # Rate-Limiting

            # ── 2. Stage-2 (+ 1h nach Stage-1) ─────────────────────────────
            pending2 = _get_pending_stage2(conn, now)
            log.info("%d Carts für Stage-2 bereit", len(pending2))
            for row in pending2:
                items = _json.loads(row["items_json"] or "[]")
                subject = _subject_stage2()
                html    = _build_stage2_email(
                    row["first_name"], items, row["total_price"],
                    row["currency"], row["recover_url"])
                ok = await _send_email(row["email"], subject, html)
                if ok:
                    _mark_stage(conn, row["checkout_token"], 2)
                    stage2_sent += 1
                    emails_sent += 1
                    log.info("Stage-2 gesendet an %s", row["email"])
                else:
                    errors += 1
                await asyncio.sleep(0.5)

            # ── 3. Stage-3 (+ 24h nach Stage-1, Rabattcode) ─────────────────
            pending3 = _get_pending_stage3(conn, now)
            log.info("%d Carts für Stage-3 bereit", len(pending3))
            for row in pending3:
                items = _json.loads(row["items_json"] or "[]")
                subject = _subject_stage3()
                html    = _build_stage3_email(
                    row["first_name"], items, row["total_price"],
                    row["currency"], row["recover_url"])
                ok = await _send_email(row["email"], subject, html)
                if ok:
                    _mark_stage(conn, row["checkout_token"], 3)
                    stage3_sent += 1
                    emails_sent += 1
                    log.info("Stage-3 (Rabatt) gesendet an %s", row["email"])
                else:
                    errors += 1
                await asyncio.sleep(0.5)

            # ── 4. DB-Gesamtcount ────────────────────────────────────────────
            total_db = _get_total_db_count(conn)

            # ── 5. Telegram-Alert ────────────────────────────────────────────
            summary = (
                f"\U0001F6D2 <b>Abandoned Cart Recovery</b>\n"
                f"Neue Carts (Stage 1): {recovered_new}\n"
                f"Stage-2 (1h): {stage2_sent}\n"
                f"Stage-3 (24h / Rabatt): {stage3_sent}\n"
                f"Emails gesamt: {emails_sent}\n"
                f"Fehler: {errors}\n"
                f"DB-Eintraege: {total_db}"
            )
            if emails_sent > 0:
                await _telegram_alert(session, summary)

        result = (
            f"Recovered: {recovered_new} Karts | "
            f"Emails: {emails_sent} versendet | "
            f"DB: {total_db} gesamt"
        )
        log.info("run_abandoned_cart_recovery: %s", result)
        return result

    except Exception as exc:
        log.error("run_abandoned_cart_recovery Fehler: %s", exc, exc_info=True)
        return f"Abandoned Cart Fehler: {exc}"
    finally:
        conn.close()


# ── Webhook-Handler (kompatibel mit dashboard/server.py) ─────────────────────

async def handle_checkout_webhook(payload: Dict, event_type: str = "create") -> Dict:
    """
    Shopify checkout/create oder checkout/update Webhook.
    Markiert abgeschlossene Checkouts in der DB.
    """
    token_key = payload.get("token", "")
    email     = payload.get("email", "")
    completed = payload.get("completed_at")

    if not token_key:
        return {"ok": True, "msg": "no token"}

    try:
        conn = _get_db()
        if completed:
            _mark_completed(conn, token_key)
            log.info("Checkout %s abgeschlossen — als completed markiert", token_key[:12])
        elif event_type == "create" and email:
            log.info("Neuer Checkout: token=%s email=%s", token_key[:12], email)
        conn.close()
    except Exception as exc:
        log.error("handle_checkout_webhook Fehler: %s", exc)

    return {"ok": True, "msg": f"{event_type} verarbeitet"}


async def handle_order_webhook(payload: Dict) -> Dict:
    """
    Shopify orders/create Webhook.
    Markiert den zugehörigen Checkout als abgeschlossen.
    """
    checkout_token = payload.get("checkout_token", "")
    order_number   = payload.get("order_number", "?")

    if checkout_token:
        try:
            conn = _get_db()
            _mark_completed(conn, checkout_token)
            conn.close()
            log.info("Bestellung #%s — Checkout %s als completed markiert",
                     order_number, checkout_token[:12])
        except Exception as exc:
            log.error("handle_order_webhook Fehler: %s", exc)

    return {"ok": True, "order": order_number}


# ── Standalone-Test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    result = asyncio.run(run_abandoned_cart_recovery())
    print(result)
