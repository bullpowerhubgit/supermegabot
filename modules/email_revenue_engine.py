"""
EMAIL REVENUE ENGINE v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━
Unified email revenue automation for ineedit.com.co / AiiteC

5 Subsystems:
  1. KLAVIYO_ACTIVATOR      — Creates/activates all flows + sends First-Purchase campaign
  2. ABANDONED_CART_FIXER   — Shopify 24h carts → SendGrid recovery email
  3. LEAD_EMAIL_BLASTER     — SQLite leads → Claude Haiku personalisation → SMTP pool
  4. WELCOME_SEQUENCE_TRIGGER — Late welcome for Klaviyo subscribers without orders
  5. DAILY_STATS            — Aggregated email KPIs from all channels

Routes (register in dashboard/server.py):
  GET  /api/email/stats
  POST /api/email/blast-now
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import smtplib
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

log = logging.getLogger("EmailRevenueEngine")

# ── Paths ──────────────────────────────────────────────────────────────────────
_BASE    = Path(__file__).parent.parent
DATA_DIR = _BASE / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
_DB      = DATA_DIR / "email_revenue.db"

# ── Env helpers ────────────────────────────────────────────────────────────────

def _e(key: str, default: str = "") -> str:
    return os.getenv(key, default)

SHOP_DOMAIN     = _e("SHOPIFY_CUSTOM_DOMAIN", _e("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co"))
SHOP_URL        = f"https://{SHOP_DOMAIN}"
SHOP_NAME       = _e("SHOP_NAME", "I Need It")
KLAVIYO_KEY     = _e("KLAVIYO_API_KEY")
KLAVIYO_BASE    = "https://a.klaviyo.com/api"
KLAVIYO_REV     = "2024-10-15"
SENDGRID_KEY    = _e("SENDGRID_API_KEY")
ANTHROPIC_KEY   = _e("ANTHROPIC_API_KEY")
FROM_EMAIL      = _e("EMAIL_FROM", "noreply@ineedit.com.co")
FROM_NAME       = _e("EMAIL_FROM_NAME", SHOP_NAME)
KLAVIYO_LIST_ID = _e("KLAVIYO_LIST_ID", "Xwxq6V")

# ── Klaviyo headers ────────────────────────────────────────────────────────────

def _klv_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
        "revision":      KLAVIYO_REV,
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }

# ── SQLite state DB ────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ere_sends (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        email       TEXT NOT NULL,
        channel     TEXT DEFAULT 'smtp',   -- smtp | sendgrid | klaviyo
        campaign    TEXT DEFAULT '',
        subject     TEXT DEFAULT '',
        status      TEXT DEFAULT 'sent',   -- sent | failed | bounced
        sent_at     TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS ere_flows (
        flow_name   TEXT PRIMARY KEY,
        flow_id     TEXT DEFAULT '',
        status      TEXT DEFAULT 'draft',  -- draft | live
        created_at  TEXT DEFAULT (datetime('now')),
        activated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS ere_stats (
        stat_date   TEXT PRIMARY KEY,
        sent        INTEGER DEFAULT 0,
        opened      INTEGER DEFAULT 0,
        clicked     INTEGER DEFAULT 0,
        conversions INTEGER DEFAULT 0,
        revenue_eur REAL    DEFAULT 0.0
    );
    CREATE TABLE IF NOT EXISTS ere_cart_recoveries (
        checkout_id TEXT PRIMARY KEY,
        email       TEXT NOT NULL,
        sent_at     TEXT DEFAULT (datetime('now')),
        status      TEXT DEFAULT 'sent'
    );
    CREATE TABLE IF NOT EXISTS ere_welcome_triggered (
        profile_id  TEXT PRIMARY KEY,
        email       TEXT,
        triggered_at TEXT DEFAULT (datetime('now'))
    );
    """)
    conn.commit()
    return conn


def _record_send(email: str, channel: str, campaign: str, subject: str, status: str = "sent"):
    today = date.today().isoformat()
    conn = _db()
    conn.execute(
        "INSERT INTO ere_sends (email,channel,campaign,subject,status) VALUES (?,?,?,?,?)",
        (email, channel, campaign, subject, status),
    )
    conn.execute("""
        INSERT INTO ere_stats (stat_date, sent) VALUES (?,1)
        ON CONFLICT(stat_date) DO UPDATE SET sent=sent+1
    """, (today,))
    conn.commit()
    conn.close()


def _already_recovered(checkout_id: str) -> bool:
    conn = _db()
    row = conn.execute("SELECT 1 FROM ere_cart_recoveries WHERE checkout_id=?", (checkout_id,)).fetchone()
    conn.close()
    return bool(row)


def _mark_recovered(checkout_id: str, email: str):
    conn = _db()
    conn.execute(
        "INSERT OR IGNORE INTO ere_cart_recoveries (checkout_id, email) VALUES (?,?)",
        (checkout_id, email),
    )
    conn.commit()
    conn.close()


def _welcome_already_triggered(profile_id: str) -> bool:
    conn = _db()
    row = conn.execute("SELECT 1 FROM ere_welcome_triggered WHERE profile_id=?", (profile_id,)).fetchone()
    conn.close()
    return bool(row)


def _mark_welcome_triggered(profile_id: str, email: str):
    conn = _db()
    conn.execute(
        "INSERT OR IGNORE INTO ere_welcome_triggered (profile_id, email) VALUES (?,?)",
        (profile_id, email),
    )
    conn.commit()
    conn.close()


def _get_flow_id(flow_name: str) -> Optional[str]:
    conn = _db()
    row = conn.execute("SELECT flow_id FROM ere_flows WHERE flow_name=?", (flow_name,)).fetchone()
    conn.close()
    return row["flow_id"] if row else None


def _save_flow(flow_name: str, flow_id: str, status: str = "draft"):
    conn = _db()
    conn.execute("""
        INSERT INTO ere_flows (flow_name, flow_id, status) VALUES (?,?,?)
        ON CONFLICT(flow_name) DO UPDATE SET flow_id=excluded.flow_id, status=excluded.status
    """, (flow_name, flow_id, status))
    conn.commit()
    conn.close()


# ── SMTP pool (mirrors mega_acquisition_engine pool) ──────────────────────────

def _build_smtp_pool() -> List[Dict]:
    """Build SMTP account pool from environment variables (same pool as MegaAcquisitionEngine)."""
    accounts = []
    specs = [
        ("BullPower",     _e("GMAIL_USER_3", _e("GMAIL_USER_BULLPOWER", "bullpowersrtkennels@gmail.com")),
                          _e("GMAIL_APP_PASSWORD_3", _e("GMAIL_APP_PASSWORD_BULLPOWER")),
                          "smtp.gmail.com", 587),
        ("AiiteC",        _e("GMAIL_USER_5", _e("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")),
                          _e("GMAIL_APP_PASSWORD_5", _e("GMAIL_APP_PASSWORD_AIITEC")),
                          "smtp.gmail.com", 587),
        ("AiiteC-Strato", _e("GMAIL_USER_6", "rudolf.sarkany@aitec.de"),
                          _e("GMAIL_APP_PASSWORD_6"),
                          _e("SMTP_HOST_6", "smtp.strato.de"), int(_e("SMTP_PORT_6", "587"))),
        ("RudolfPersonal",_e("GMAIL_USER_8", "rudolfsarkany1984@gmail.com"),
                          _e("GMAIL_APP_PASSWORD_8"),
                          "smtp.gmail.com", 587),
        # dragonadnp + rudolf.sarkany.aiitec: Reputation beschädigt — dauerhaft gesperrt 2026-07-20
    ]
    for name, user, pw, host, port in specs:
        if pw:
            accounts.append({
                "name": name, "user": user, "password": pw,
                "host": host, "port": port,
                "daily_limit": 200,  # conservative per-account limit for revenue engine
            })
    return accounts


_SMTP_POOL: List[Dict] = []
_SMTP_INDEX: int = 0


def _get_next_smtp_account() -> Optional[Dict]:
    global _SMTP_POOL, _SMTP_INDEX
    if not _SMTP_POOL:
        _SMTP_POOL = _build_smtp_pool()
    if not _SMTP_POOL:
        return None
    today = date.today().isoformat()
    # rotate through accounts that still have quota
    for _ in range(len(_SMTP_POOL)):
        acc = _SMTP_POOL[_SMTP_INDEX % len(_SMTP_POOL)]
        _SMTP_INDEX += 1
        sent = _get_smtp_sent_today_ere(acc["name"])
        if sent < acc["daily_limit"]:
            return acc
    return None  # all accounts exhausted


def _get_smtp_sent_today_ere(account_name: str) -> int:
    today = date.today().isoformat()
    conn = _db()
    row = conn.execute(
        "SELECT COUNT(*) as n FROM ere_sends WHERE channel='smtp' AND campaign LIKE ? "
        "AND date(sent_at)=?", (f"%{account_name}%", today)
    ).fetchone()
    conn.close()
    return row["n"] if row else 0


def _smtp_send(acc: Dict, to_email: str, subject: str, html_body: str, text_body: str = "") -> bool:
    """Send one email via SMTP. Returns True on success."""
    from modules.email_guard import validate_email
    ok_g, errs = validate_email(subject, html_body, to_email)
    if not ok_g:
        log.warning("EmailGuard BLOCK in _smtp_send: %s", errs)
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{FROM_NAME} <{acc['user']}>"
        msg["To"]      = to_email
        msg["List-Unsubscribe"] = f"<{SHOP_URL}/pages/unsubscribe?email={to_email}>"
        if text_body:
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        with smtplib.SMTP(acc["host"], acc["port"], timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(acc["user"], acc["password"])
            server.sendmail(acc["user"], [to_email], msg.as_string())
        return True
    except Exception as exc:
        log.warning("SMTP send failed (%s → %s): %s", acc["name"], to_email, exc)
        return False


# ── SendGrid helper ────────────────────────────────────────────────────────────

async def _sendgrid_send(
    session: aiohttp.ClientSession,
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    text_body: str = "",
) -> bool:
    if not SENDGRID_KEY:
        log.warning("SendGrid key not set — falling back to SMTP")
        return False
    payload = {
        "personalizations": [{"to": [{"email": to_email, "name": to_name}]}],
        "from": {"email": FROM_EMAIL, "name": FROM_NAME},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text_body or "Bitte aktiviere HTML-E-Mails."},
            {"type": "text/html",  "value": html_body},
        ],
        "tracking_settings": {
            "click_tracking": {"enable": True},
            "open_tracking":  {"enable": True},
        },
    }
    try:
        async with session.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={"Authorization": f"Bearer {SENDGRID_KEY}", "Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            if r.status in (200, 202):
                return True
            body = await r.text()
            log.warning("SendGrid error %d: %s", r.status, body[:200])
            return False
    except Exception as exc:
        log.warning("SendGrid exception: %s", exc)
        return False


# ── HTML email builder ─────────────────────────────────────────────────────────

def _build_email_html(
    title: str,
    body_html: str,
    cta_text: str,
    cta_url: str,
    unsubscribe_email: str = "",
) -> str:
    unsub_url = f"{SHOP_URL}/pages/unsubscribe?email={unsubscribe_email}"
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:Arial,sans-serif;background:#050508;color:#f0f0f0;margin:0;padding:0}}
.wrap{{max-width:600px;margin:0 auto;background:#0d0d1c;border-radius:12px;overflow:hidden;border:1px solid #1a1a2e}}
.header{{background:linear-gradient(135deg,#22c55e,#16a34a);padding:28px 32px;text-align:center}}
.header h1{{color:#000;margin:0;font-size:22px;font-weight:800}}
.body{{padding:32px}}
.body p{{color:#ccc;line-height:1.7;margin-bottom:16px;font-size:15px}}
.cta{{display:block;width:fit-content;margin:28px auto;padding:15px 36px;
      background:#22c55e;color:#000;font-weight:700;border-radius:8px;
      text-decoration:none;font-size:16px}}
.footer{{padding:16px 32px;text-align:center;font-size:11px;color:#444;border-top:1px solid #1a1a2e}}
.footer a{{color:#555;text-decoration:none}}
</style></head><body>
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#050508">
<tr><td align="center" style="padding:32px 16px">
<div class="wrap">
<div class="header"><h1>⚡ {title}</h1></div>
<div class="body">{body_html}
<a href="{cta_url}" class="cta">{cta_text}</a>
</div>
<div class="footer">
{SHOP_NAME} · {SHOP_DOMAIN}<br>
<a href="{unsub_url}">Abmelden</a> &nbsp;·&nbsp;
<a href="{SHOP_URL}">Shop besuchen</a>
</div>
</div>
</td></tr>
</table>
</body></html>"""


# ── Cart recovery template ─────────────────────────────────────────────────────

def _build_cart_recovery_html(
    first_name: str,
    items: List[Dict],
    total: str,
    checkout_url: str,
    email: str,
) -> Tuple[str, str]:
    subject = "Du hast etwas vergessen! \U0001f6d2 Spare 10% mit Code SAVE10"
    item_rows = ""
    for item in items[:3]:
        img   = item.get("image", "")
        title = item.get("title", "Produkt")[:55]
        price = item.get("price", "?")
        img_tag = f'<img src="{img}" width="60" height="60" style="border-radius:6px;object-fit:cover;margin-right:12px" alt="{title}">' if img else ""
        item_rows += f"""
<tr>
  <td style="padding:10px 0;border-bottom:1px solid #1a1a2e">
    <table cellpadding="0" cellspacing="0"><tr>
      <td>{img_tag}</td>
      <td style="vertical-align:middle">
        <strong style="color:#fff;font-size:14px">{title}</strong><br>
        <span style="color:#22c55e;font-size:13px">€{price}</span>
      </td>
    </tr></table>
  </td>
</tr>"""

    body_html = f"""
<p>Hallo {first_name or "dort"},</p>
<p>du hast noch Artikel im Wert von <strong style="color:#22c55e">€{total}</strong> in deinem Warenkorb!</p>
<table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0">{item_rows}</table>
<p>Heute nur: Schließe deinen Kauf ab und spare mit Code:</p>
<div style="text-align:center;margin:20px 0">
  <div style="display:inline-block;background:#050508;border:2px dashed #22c55e;border-radius:10px;padding:14px 28px">
    <p style="color:#666;font-size:11px;text-transform:uppercase;letter-spacing:.1em;margin:0 0 4px">Rabattcode</p>
    <p style="color:#22c55e;font-size:24px;font-weight:800;letter-spacing:.15em;margin:0;font-family:monospace">SAVE10</p>
  </div>
</div>
<p style="color:#888;font-size:13px">Der Code ist für kurze Zeit gültig — sichere dir jetzt 10% Rabatt!</p>"""

    html = _build_email_html(
        title="Dein Warenkorb wartet!",
        body_html=body_html,
        cta_text="Warenkorb abschließen →",
        cta_url=f"{checkout_url}&discount=SAVE10",
        unsubscribe_email=email,
    )
    text = (
        f"Hallo {first_name or 'dort'},\n\n"
        f"du hast noch Artikel (€{total}) in deinem Warenkorb!\n"
        f"Spare 10% mit Code SAVE10.\n\n"
        f"Warenkorb abschließen: {checkout_url}\n\n"
        f"Abmelden: {SHOP_URL}/pages/unsubscribe?email={email}"
    )
    return subject, html, text


# ═════════════════════════════════════════════════════════════════════════════
# 1. KLAVIYO ACTIVATOR
# ═════════════════════════════════════════════════════════════════════════════

async def klaviyo_activator() -> Dict[str, Any]:
    """
    1. Calls klaviyo_flows_builder.setup_all_flows() if flows not yet created.
    2. Verifies flows are LIVE (not draft) and marks them live in local DB.
    3. Creates a "First Purchase Incentive" campaign to all subscribers
       with discount code WILLKOMMEN10 via Klaviyo Campaigns API.
    """
    if not KLAVIYO_KEY:
        return {"ok": False, "error": "KLAVIYO_API_KEY not set"}

    result: Dict[str, Any] = {
        "flows": {},
        "campaign": {},
        "errors": [],
    }

    # -- 1a. ensure flows are created --
    flow_names_map = {
        "welcome":       "Welcome Series — ineedit (DE)",
        "abandoned_cart":"Abandoned Cart Recovery — ineedit (DE)",
        "post_purchase": "Post-Purchase Serie — ineedit (DE)",
        "winback":       "Win-Back Inaktive — ineedit (DE)",
    }
    missing = [k for k, _ in flow_names_map.items() if not _get_flow_id(k)]
    if missing:
        try:
            from modules.klaviyo_flows_builder import setup_all_flows
            flow_result = await setup_all_flows()
            for name, detail in flow_result.get("detail", {}).items():
                fid = detail.get("flow_id", "")
                if fid:
                    _save_flow(name, fid, "draft")
            result["flows"]["setup"] = flow_result
            log.info("Klaviyo flows setup: %s", flow_result)
        except Exception as exc:
            log.warning("Flows setup error: %s", exc)
            result["errors"].append(f"flows_setup: {exc}")
    else:
        result["flows"]["setup"] = {"skipped": True, "reason": "all flows already exist"}

    # -- 1b. verify / activate flows (PATCH status to live) --
    async with aiohttp.ClientSession() as session:
        conn = _db()
        rows = conn.execute("SELECT flow_name, flow_id, status FROM ere_flows").fetchall()
        conn.close()
        activated = []
        for row in rows:
            fid = row["flow_id"]
            if not fid or row["status"] == "live":
                continue
            try:
                async with session.patch(
                    f"{KLAVIYO_BASE}/flows/{fid}/",
                    json={"data": {"type": "flow", "id": fid, "attributes": {"status": "live"}}},
                    headers=_klv_headers(),
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    if r.status in (200, 204):
                        _save_flow(row["flow_name"], fid, "live")
                        activated.append(row["flow_name"])
                    else:
                        err = await r.text()
                        log.warning("Flow activate %s HTTP %d: %s", row["flow_name"], r.status, err[:120])
            except Exception as exc:
                log.warning("Flow activate error %s: %s", row["flow_name"], exc)
        result["flows"]["activated"] = activated

        # -- 1c. First Purchase Incentive campaign (Dedup: max 1x pro Tag) --
        today_iso = date.today().isoformat()
        conn = _db()
        already_today = conn.execute(
            "SELECT 1 FROM ere_flows WHERE flow_name='campaign_first_purchase_today' "
            "AND date(created_at)=?", (today_iso,)
        ).fetchone()
        conn.close()
        if already_today:
            result["campaign"] = {"ok": True, "skipped": True, "reason": "bereits heute erstellt"}
            log.info("First Purchase Campaign heute bereits erstellt — übersprungen")
        else:
            try:
                campaign_result = await _create_first_purchase_campaign(session)
                result["campaign"] = campaign_result
                if campaign_result.get("ok"):
                    # Merke: heute bereits erstellt
                    _save_flow("campaign_first_purchase_today",
                               campaign_result.get("campaign_id", "today"), "live")
            except Exception as exc:
                log.warning("Campaign creation error: %s", exc)
                result["errors"].append(f"campaign: {exc}")

    result["ok"] = len(result["errors"]) == 0
    return result


async def _create_first_purchase_campaign(session: aiohttp.ClientSession) -> Dict:
    """Create & schedule a First-Purchase Incentive campaign via Klaviyo Campaigns API."""
    # Build campaign
    campaign_payload = {
        "data": {
            "type": "campaign",
            "attributes": {
                "name": f"First Purchase Incentive — WILLKOMMEN10 — {date.today().isoformat()}",
                "status": "draft",
                "audiences": {
                    "included": [KLAVIYO_LIST_ID],
                },
                "send_options": {"use_smart_sending": True},
                "tracking_options": {
                    "is_add_utm": True,
                    "utm_params": [
                        {"name": "utm_source",   "value": "klaviyo"},
                        {"name": "utm_medium",   "value": "email"},
                        {"name": "utm_campaign", "value": "first_purchase_incentive"},
                    ],
                },
                "send_strategy": {"method": "immediate"},
            },
        }
    }
    async with session.post(
        f"{KLAVIYO_BASE}/campaigns/",
        json=campaign_payload,
        headers=_klv_headers(),
        timeout=aiohttp.ClientTimeout(total=20),
    ) as r:
        resp_data = await r.json(content_type=None)
        if r.status not in (200, 201, 202):
            return {"ok": False, "error": f"HTTP {r.status}", "detail": resp_data}

    campaign_id = resp_data.get("data", {}).get("id", "")
    log.info("Klaviyo campaign created: %s", campaign_id)

    # Attach message to campaign
    welcome_html = _build_email_html(
        title="Dein exklusiver Willkommensrabatt",
        body_html="""
<p>Hallo {{ first_name|default:"dort" }},</p>
<p>herzlich willkommen bei <strong>I Need It</strong>! Wir freuen uns, dich dabei zu haben.</p>
<p>Als Dankeschön für dein Vertrauen schenken wir dir <strong>10% Rabatt</strong> auf deine erste Bestellung.</p>
<div style="text-align:center;margin:20px 0">
  <div style="display:inline-block;background:#050508;border:2px dashed #22c55e;border-radius:10px;padding:14px 28px">
    <p style="color:#666;font-size:11px;text-transform:uppercase;letter-spacing:.1em;margin:0 0 4px">Dein Rabattcode</p>
    <p style="color:#22c55e;font-size:26px;font-weight:800;letter-spacing:.15em;margin:0;font-family:monospace">WILLKOMMEN10</p>
  </div>
</div>
<p>Entdecke Smart Home, Solar-Systeme, Premium Gadgets &amp; mehr.</p>""",
        cta_text="Jetzt shoppen →",
        cta_url=f"{SHOP_URL}?discount=WILLKOMMEN10&utm_source=klaviyo&utm_medium=email&utm_campaign=first_purchase",
        unsubscribe_email="{{ email }}",
    )
    if campaign_id:
        msg_payload = {
            "data": {
                "type": "campaign-message",
                "attributes": {
                    "channel": "email",
                    "content": {
                        "subject":      "Willkommen! \U0001f381 10% Rabatt mit WILLKOMMEN10",
                        "preview_text": "Schon heute shoppen und sparen — dein Code wartet",
                        "from_email":   FROM_EMAIL,
                        "from_label":   FROM_NAME,
                        "body":         welcome_html,
                    },
                },
            }
        }
        async with session.post(
            f"{KLAVIYO_BASE}/campaigns/{campaign_id}/campaign-messages/",
            json=msg_payload,
            headers=_klv_headers(),
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r2:
            msg_data = await r2.json(content_type=None)
            msg_id   = msg_data.get("data", {}).get("id", "")

        # Send campaign
        if msg_id:
            async with session.post(
                f"{KLAVIYO_BASE}/campaign-send-jobs/",
                json={"data": {"type": "campaign-send-job", "attributes": {"campaign_id": campaign_id}}},
                headers=_klv_headers(),
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r3:
                send_data = await r3.json(content_type=None)
                log.info("Campaign send job: %s", send_data)
                return {
                    "ok":          True,
                    "campaign_id": campaign_id,
                    "message_id":  msg_id,
                    "send_status": send_data,
                }

    return {"ok": bool(campaign_id), "campaign_id": campaign_id}


# ═════════════════════════════════════════════════════════════════════════════
# 2. ABANDONED CART FIXER
# ═════════════════════════════════════════════════════════════════════════════

async def abandoned_cart_fixer() -> Dict[str, Any]:
    """
    Fetches Shopify checkouts abandoned in the last 24h and sends
    a recovery email via SendGrid (with SAVE10 code) to each unique lead.
    Falls back to SMTP pool if SendGrid is unavailable.
    """
    domain  = _e("SHOPIFY_SHOP_DOMAIN")
    token   = _e("SHOPIFY_ADMIN_API_TOKEN")
    version = _e("SHOPIFY_API_VERSION", "2026-04")

    if not domain or not token:
        return {"ok": False, "error": "SHOPIFY_SHOP_DOMAIN / SHOPIFY_ADMIN_API_TOKEN not set"}

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    h     = {"X-Shopify-Access-Token": token}
    base  = f"https://{domain}/admin/api/{version}"

    sent = 0
    skipped = 0
    failed  = 0

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                f"{base}/checkouts.json",
                headers=h,
                params={
                    "limit":            250,
                    "created_at_min":   since,
                    "fields":           "id,email,billing_address,line_items,total_price,abandoned_checkout_url",
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                if r.status != 200:
                    return {"ok": False, "error": f"Shopify HTTP {r.status}"}
                checkouts = (await r.json(content_type=None)).get("checkouts", [])
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        for checkout in checkouts:
            email = (checkout.get("email") or "").strip().lower()
            if not email or "@" not in email:
                skipped += 1
                continue

            checkout_id = str(checkout.get("id", ""))
            if _already_recovered(checkout_id):
                skipped += 1
                continue

            addr          = checkout.get("billing_address") or {}
            first_name    = addr.get("first_name", "")
            total         = str(checkout.get("total_price", "0"))
            checkout_url  = checkout.get("abandoned_checkout_url", f"{SHOP_URL}/cart")
            raw_items     = checkout.get("line_items", [])

            items = []
            for li in raw_items[:3]:
                items.append({
                    "title": li.get("title", "Produkt"),
                    "price": li.get("price", "?"),
                    "image": (li.get("image", {}) or {}).get("src", "") if isinstance(li.get("image"), dict) else "",
                })

            subject, html_body, text_body = _build_cart_recovery_html(
                first_name=first_name,
                items=items,
                total=total,
                checkout_url=checkout_url,
                email=email,
            )

            # Try SendGrid first, fall back to SMTP
            ok = await _sendgrid_send(session, email, first_name, subject, html_body, text_body)
            if not ok:
                acc = _get_next_smtp_account()
                if acc:
                    ok = await asyncio.get_event_loop().run_in_executor(
                        None, _smtp_send, acc, email, subject, html_body, text_body
                    )

            if ok:
                _mark_recovered(checkout_id, email)
                _record_send(email, "sendgrid" if SENDGRID_KEY else "smtp",
                             "abandoned_cart_recovery", subject)
                sent += 1
                log.info("Cart recovery sent → %s (checkout %s)", email, checkout_id)
            else:
                failed += 1
                log.warning("Cart recovery failed → %s", email)

            await asyncio.sleep(0.3)  # gentle rate limiting

    return {
        "ok":      True,
        "sent":    sent,
        "skipped": skipped,
        "failed":  failed,
        "window":  "last_24h",
    }


# ═════════════════════════════════════════════════════════════════════════════
# 3. LEAD EMAIL BLASTER
# ═════════════════════════════════════════════════════════════════════════════

async def _generate_personalized_email(lead: Dict) -> Tuple[str, str]:
    """
    Calls Claude Haiku to produce a personalised subject + short intro paragraph.
    Falls back to a template if ANTHROPIC_API_KEY is not set or Haiku fails.
    """
    name    = lead.get("name", "").strip() or "Technik-Enthusiast"
    niche   = lead.get("niche", "shop")
    company = lead.get("company", "").strip()
    source  = lead.get("source", "")

    prompt = (
        f"Du bist E-Mail-Texter für den deutschen Online-Shop ineedit.com.co (Smart Home, Solar, Gadgets, KI-Tools).\n"
        f"Schreibe eine kurze, authentische Betreffzeile (max 65 Zeichen) und einen Intro-Absatz (2-3 Sätze, max 120 Wörter) "
        f"für diese Person:\n"
        f"Name: {name}\nFirma: {company or '—'}\nInteressen/Nische: {niche}\nQuelle: {source}\n\n"
        f"VERBOTEN (NIEMALS verwenden):\n"
        f"- Phrasen wie 'Du nutzt nur X% deines Potenzials', 'Die meisten Menschen nutzen weniger als...'\n"
        f"- Life-Coach- oder Finanz-Motivations-Content\n"
        f"- Fake-Garantien, übertriebene Versprechen\n"
        f"- Placeholder-Text wie [NAME], [LINK], TODO, undefined\n\n"
        f"Format (nur JSON, keine Erklärung):\n"
        f'{{ "subject": "...", "intro": "..." }}'
    )
    try:
        from modules.ai_client import ai_complete
        raw = await ai_complete(prompt, system="", max_tokens=256)
        if raw:
            parsed = json.loads(raw)
            subject = parsed.get("subject", "")
            intro   = parsed.get("intro", "")
            if subject and intro:
                return subject, intro
    except Exception as exc:
        log.warning("AI personalization failed: %s", exc)

    return _fallback_subject_body(name, niche, company)


def _fallback_subject_body(name: str, niche: str, company: str) -> Tuple[str, str]:
    first = name.split()[0] if name else "Hey"
    if niche == "b2b":
        subj = f"KI-Automatisierung für {company or 'Ihr Unternehmen'} — 30% Zeit sparen"
        intro = (
            f"Guten Tag {first},<br><br>"
            f"wir helfen mittelständischen Unternehmen, wiederkehrende Prozesse mit KI zu automatisieren "
            f"und durchschnittlich 30% Arbeitszeit einzusparen — ab Woche 1."
        )
    else:
        subj  = f"{first}, dein persönlicher 10% Rabatt bei ineedit"
        intro = (
            f"Hallo {first},<br><br>"
            f"wir haben die besten Smart Home & Gadget-Deals für dich. "
            f"Spare heute <strong>10% auf alles</strong> mit deinem persönlichen Code <strong>MEGA10</strong>."
        )
    return subj, intro


def _build_lead_email_html(lead: Dict, intro_html: str) -> str:
    name  = lead.get("name", "").strip() or "Technik-Enthusiast"
    niche = lead.get("niche", "shop")
    code  = "MEGA10" if niche != "b2b" else ""
    email = lead.get("email", "")

    code_block = ""
    if code:
        code_block = f"""
<div style="text-align:center;margin:24px 0">
  <div style="display:inline-block;background:#050508;border:2px dashed #22c55e;
              border-radius:10px;padding:14px 28px">
    <p style="color:#666;font-size:11px;text-transform:uppercase;letter-spacing:.1em;margin:0 0 4px">Dein Rabattcode</p>
    <p style="color:#22c55e;font-size:26px;font-weight:800;letter-spacing:.15em;margin:0;
              font-family:monospace">{code}</p>
  </div>
</div>"""

    cta_url  = f"{SHOP_URL}?discount={code}&utm_source=email&utm_medium=acquisition" if code else f"{SHOP_URL}?utm_source=email&utm_medium=acquisition"
    cta_text = "Jetzt shoppen →" if niche != "b2b" else "Demo vereinbaren →"
    cta_dest = cta_url if niche != "b2b" else "https://calendly.com/aiitec"

    body_html = f"<p>{intro_html}</p>{code_block}"

    return _build_email_html(
        title="I Need It — Exklusives Angebot" if niche != "b2b" else "AiiteC — KI-Automatisierung",
        body_html=body_html,
        cta_text=cta_text,
        cta_url=cta_dest,
        unsubscribe_email=email,
    )


def _collect_leads_from_all_dbs(max_per_db: int = 200) -> List[Dict]:
    """
    Scans known SQLite databases for uncontacted leads.
    Merges: mega_acquisition.db, industrie_outreach.db, any mass_outreach_*.db, email_conversations.db
    """
    leads: List[Dict] = []
    seen_emails: set  = set()

    # ── mega_acquisition.db (acquisition_leads) ────────────────────────────
    acq_db = DATA_DIR / "mega_acquisition.db"
    if acq_db.exists():
        try:
            conn = sqlite3.connect(str(acq_db))
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT email, name, company, niche, source, language, tags
                FROM acquisition_leads
                WHERE status='new' AND bounced=0 AND unsubscribed=0
                  AND (last_sent IS NULL OR last_sent < datetime('now','-24 hours'))
                ORDER BY created_at ASC LIMIT ?
            """, (max_per_db,)).fetchall()
            conn.close()
            for r in rows:
                e = (r["email"] or "").lower().strip()
                if e and e not in seen_emails:
                    seen_emails.add(e)
                    leads.append(dict(r))
        except Exception as exc:
            log.warning("mega_acquisition.db read error: %s", exc)

    # ── industrie_outreach.db ──────────────────────────────────────────────
    outreach_db = DATA_DIR / "industrie_outreach.db"
    if outreach_db.exists():
        try:
            conn = sqlite3.connect(str(outreach_db))
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT email, company as name, company, 'b2b' as niche,
                       'industrie_outreach' as source, 'de' as language, branche as tags
                FROM industrie_outreach
                WHERE status='new' OR status='pending'
                LIMIT ?
            """, (max_per_db,)).fetchall()
            conn.close()
            for r in rows:
                e = (r["email"] or "").lower().strip()
                if e and e not in seen_emails:
                    seen_emails.add(e)
                    leads.append(dict(r))
        except Exception as exc:
            log.warning("industrie_outreach.db read error: %s", exc)

    # ── mass_outreach_*.db files ───────────────────────────────────────────
    for db_file in sorted(DATA_DIR.glob("mass_outreach_*.db")):
        try:
            conn = sqlite3.connect(str(db_file))
            conn.row_factory = sqlite3.Row
            # Try common table patterns
            for tbl in ["leads", "contacts", "outreach", "emails"]:
                try:
                    rows = conn.execute(f"""
                        SELECT email,
                               COALESCE(name, first_name||' '||last_name, '') as name,
                               COALESCE(company, '') as company,
                               COALESCE(niche, 'shop') as niche,
                               '{db_file.stem}' as source,
                               COALESCE(language, 'de') as language,
                               COALESCE(tags, '') as tags
                        FROM {tbl}
                        WHERE (status IS NULL OR status='new' OR status='pending')
                        LIMIT ?
                    """, (max_per_db,)).fetchall()
                    for r in rows:
                        e = (r["email"] or "").lower().strip()
                        if e and e not in seen_emails:
                            seen_emails.add(e)
                            leads.append(dict(r))
                    break  # found a valid table
                except Exception:
                    continue
            conn.close()
        except Exception as exc:
            log.warning("%s read error: %s", db_file.name, exc)

    # ── email_conversations.db ─────────────────────────────────────────────
    conv_db = DATA_DIR / "email_conversations.db"
    if conv_db.exists():
        try:
            conn = sqlite3.connect(str(conv_db))
            conn.row_factory = sqlite3.Row
            for tbl in ["conversations", "leads", "contacts"]:
                try:
                    rows = conn.execute(f"""
                        SELECT email,
                               COALESCE(name,'') as name,
                               COALESCE(company,'') as company,
                               COALESCE(niche,'shop') as niche,
                               'email_conversations' as source,
                               'de' as language,
                               COALESCE(tags,'') as tags
                        FROM {tbl}
                        WHERE (contacted IS NULL OR contacted=0)
                        LIMIT ?
                    """, (max_per_db,)).fetchall()
                    for r in rows:
                        e = (r["email"] or "").lower().strip()
                        if e and e not in seen_emails:
                            seen_emails.add(e)
                            leads.append(dict(r))
                    break
                except Exception:
                    continue
            conn.close()
        except Exception as exc:
            log.warning("email_conversations.db read error: %s", exc)

    log.info("Collected %d unique leads from all databases", len(leads))
    return leads


async def lead_email_blaster(max_per_run: int = 200) -> Dict[str, Any]:
    """
    Collects leads from all SQLite databases, generates personalised emails
    via Claude Haiku, and sends via rotating SMTP pool.
    Hard cap: max_per_run (default 200) = ≤200/hour.
    """
    leads = _collect_leads_from_all_dbs(max_per_db=100)
    if not leads:
        return {"ok": True, "sent": 0, "failed": 0, "reason": "no_uncontacted_leads"}

    # Already sent in this run — check ere_sends for today
    today = date.today().isoformat()
    conn  = _db()
    already_today = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT email FROM ere_sends WHERE date(sent_at)=? AND campaign='lead_blast'",
            (today,)
        ).fetchall()
    }
    conn.close()

    leads = [l for l in leads if l.get("email","") not in already_today][:max_per_run]

    sent   = 0
    failed = 0
    start  = time.monotonic()

    for lead in leads:
        # Rate-limit: 200/hour = 18 seconds per email minimum
        elapsed = time.monotonic() - start
        if sent > 0:
            min_interval = 3600 / max_per_run  # seconds between sends
            sleep_needed = (sent * min_interval) - elapsed
            if sleep_needed > 0:
                await asyncio.sleep(min(sleep_needed, 5))

        email = lead.get("email", "").strip().lower()
        if not email or "@" not in email:
            continue

        # Generate personalised content
        subject, intro_html = await _generate_personalized_email(lead)
        html_body = _build_lead_email_html(lead, intro_html)

        # Rotate SMTP accounts
        acc = _get_next_smtp_account()
        if not acc:
            log.warning("All SMTP accounts exhausted — stopping blast at %d sent", sent)
            break

        ok = await asyncio.get_event_loop().run_in_executor(
            None, _smtp_send, acc, email, subject, html_body, ""
        )

        if ok:
            _record_send(email, f"smtp:{acc['name']}", "lead_blast", subject)
            sent += 1
            log.info("Lead blast sent → %s via %s", email, acc["name"])
        else:
            failed += 1
            _record_send(email, f"smtp:{acc['name']}", "lead_blast", subject, "failed")

    return {
        "ok":            True,
        "sent":          sent,
        "failed":        failed,
        "leads_fetched": len(leads),
        "duration_s":    round(time.monotonic() - start, 1),
    }


# ═════════════════════════════════════════════════════════════════════════════
# 4. WELCOME SEQUENCE TRIGGER
# ═════════════════════════════════════════════════════════════════════════════

async def welcome_sequence_trigger() -> Dict[str, Any]:
    """
    Finds Klaviyo subscribers created more than 7 days ago with no orders,
    who haven't received a welcome email yet.
    Triggers the welcome sequence by adding them to the welcome list / event.
    """
    if not KLAVIYO_KEY:
        return {"ok": False, "error": "KLAVIYO_API_KEY not set"}

    since_str = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    triggered = 0
    skipped   = 0

    async with aiohttp.ClientSession() as session:
        # Paginate through all profiles in the list
        cursor = None
        while True:
            params: Dict = {
                "fields[profile]":  "email,first_name,last_name,properties",
                "page[size]":       "100",
                "filter":           f"less-than(created,{since_str})",
            }
            if cursor:
                params["page[cursor]"] = cursor
            try:
                async with session.get(
                    f"{KLAVIYO_BASE}/lists/{KLAVIYO_LIST_ID}/profiles/",
                    headers=_klv_headers(),
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    if r.status != 200:
                        log.warning("Klaviyo profiles HTTP %d", r.status)
                        break
                    data = await r.json(content_type=None)
            except Exception as exc:
                log.warning("Klaviyo profiles fetch error: %s", exc)
                break

            profiles  = data.get("data", [])
            next_link = data.get("links", {}).get("next", "")

            for profile in profiles:
                pid   = profile.get("id", "")
                attrs = profile.get("attributes", {})
                email = attrs.get("email", "").strip()

                if not pid or not email:
                    continue
                if _welcome_already_triggered(pid):
                    skipped += 1
                    continue

                # Check if they have made any orders (via properties or Shopify)
                props = attrs.get("properties", {}) or {}
                orders = int(props.get("$shopify_orders_count", props.get("orders_count", 0)) or 0)
                if orders > 0:
                    skipped += 1
                    continue

                # Trigger welcome: create an "ineedit Welcome" event for this profile
                event_payload = {
                    "data": {
                        "type": "event",
                        "attributes": {
                            "profile": {
                                "data": {
                                    "type":       "profile",
                                    "attributes": {
                                        "email":      email,
                                        "first_name": attrs.get("first_name", ""),
                                        "last_name":  attrs.get("last_name", ""),
                                    },
                                }
                            },
                            "metric": {
                                "data": {
                                    "type":       "metric",
                                    "attributes": {"name": "ineedit Welcome Trigger"},
                                }
                            },
                            "properties": {"source": "welcome_sequence_trigger"},
                            "time":       datetime.now(timezone.utc).isoformat(),
                        },
                    }
                }
                try:
                    async with session.post(
                        f"{KLAVIYO_BASE}/events/",
                        json=event_payload,
                        headers=_klv_headers(),
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as ev_r:
                        if ev_r.status in (200, 201, 202):
                            _mark_welcome_triggered(pid, email)
                            triggered += 1
                            log.info("Welcome triggered for %s (profile %s)", email, pid)
                        else:
                            err = await ev_r.text()
                            log.warning("Welcome event HTTP %d for %s: %s", ev_r.status, email, err[:100])
                except Exception as exc:
                    log.warning("Welcome event error for %s: %s", email, exc)

                await asyncio.sleep(0.2)  # rate limit

            cursor = next_link
            if not cursor or not profiles:
                break

    return {
        "ok":        True,
        "triggered": triggered,
        "skipped":   skipped,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 5. DAILY STATS
# ═════════════════════════════════════════════════════════════════════════════

async def daily_stats() -> Dict[str, Any]:
    """
    Aggregates email KPIs from:
    - ere_stats (this engine's local SQLite)
    - mega_acquisition_stats (acquisition engine SQLite)
    - Klaviyo Campaign Stats API (last 7 days)
    Returns: emails_sent_today, open_rate, click_rate, conversions, revenue_from_email
    """
    today = date.today().isoformat()

    # ── local engine stats ─────────────────────────────────────────────────
    conn = _db()
    row  = conn.execute("SELECT * FROM ere_stats WHERE stat_date=?", (today,)).fetchone()
    conn.close()
    local = dict(row) if row else {"sent": 0, "opened": 0, "clicked": 0, "conversions": 0, "revenue_eur": 0.0}

    # ── mega_acquisition stats ─────────────────────────────────────────────
    acq_sent = 0
    acq_db   = DATA_DIR / "mega_acquisition.db"
    if acq_db.exists():
        try:
            conn2 = sqlite3.connect(str(acq_db))
            conn2.row_factory = sqlite3.Row
            r2 = conn2.execute("SELECT * FROM acquisition_stats WHERE date=?", (today,)).fetchone()
            conn2.close()
            if r2:
                acq_sent = r2["sent"] or 0
        except Exception:
            pass

    total_sent = local.get("sent", 0) + acq_sent

    # ── Klaviyo campaign stats (last 7 days) ───────────────────────────────
    klv_stats: Dict[str, Any] = {}
    if KLAVIYO_KEY:
        try:
            since_klv = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{KLAVIYO_BASE}/campaigns/",
                    headers=_klv_headers(),
                    params={
                        "filter":         f"greater-than(created_at,{since_klv})",
                        "fields[campaign]":"name,status,send_time",
                        "page[size]":     "10",
                    },
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    if r.status == 200:
                        data = await r.json(content_type=None)
                        klv_stats["recent_campaigns"] = len(data.get("data", []))
                        klv_stats["campaign_list"]    = [
                            {
                                "name":   c.get("attributes", {}).get("name"),
                                "status": c.get("attributes", {}).get("status"),
                            }
                            for c in data.get("data", [])[:5]
                        ]
        except Exception as exc:
            log.warning("Klaviyo stats error: %s", exc)

    # ── compute rates ──────────────────────────────────────────────────────
    opened      = local.get("opened", 0)
    clicked     = local.get("clicked", 0)
    conversions = local.get("conversions", 0)
    revenue     = local.get("revenue_eur", 0.0)

    open_rate  = round((opened  / total_sent * 100), 1) if total_sent > 0 else 0.0
    click_rate = round((clicked / total_sent * 100), 1) if total_sent > 0 else 0.0
    conv_rate  = round((conversions / total_sent * 100), 1) if total_sent > 0 else 0.0

    return {
        "date":               today,
        "emails_sent_today":  total_sent,
        "open_rate":          f"{open_rate}%",
        "click_rate":         f"{click_rate}%",
        "conversions":        conversions,
        "conversion_rate":    f"{conv_rate}%",
        "revenue_from_email": f"€{revenue:.2f}",
        "breakdown": {
            "engine_sends":     local.get("sent", 0),
            "acquisition_sends":acq_sent,
        },
        "klaviyo":            klv_stats,
        "smtp_pool_size":     len(_build_smtp_pool()),
    }


# ═════════════════════════════════════════════════════════════════════════════
# FULL BLAST — runs all 5 subsystems sequentially
# ═════════════════════════════════════════════════════════════════════════════

async def run_full_blast() -> Dict[str, Any]:
    """Execute all revenue engine subsystems and return a combined report."""
    log.info("EmailRevenueEngine: starting full blast")
    results: Dict[str, Any] = {}

    # 1. Klaviyo flows + campaign
    try:
        results["klaviyo_activator"] = await klaviyo_activator()
    except Exception as exc:
        results["klaviyo_activator"] = {"ok": False, "error": str(exc)}

    # 2. Abandoned cart recovery (time-sensitive — run early)
    try:
        results["abandoned_cart_fixer"] = await abandoned_cart_fixer()
    except Exception as exc:
        results["abandoned_cart_fixer"] = {"ok": False, "error": str(exc)}

    # 3. Welcome sequence for late subscribers
    try:
        results["welcome_sequence_trigger"] = await welcome_sequence_trigger()
    except Exception as exc:
        results["welcome_sequence_trigger"] = {"ok": False, "error": str(exc)}

    # 4. Lead blast (most volume — run last so SMTP quota is preserved for recovery)
    try:
        results["lead_email_blaster"] = await lead_email_blaster(max_per_run=200)
    except Exception as exc:
        results["lead_email_blaster"] = {"ok": False, "error": str(exc)}

    # 5. Stats summary
    try:
        results["daily_stats"] = await daily_stats()
    except Exception as exc:
        results["daily_stats"] = {"ok": False, "error": str(exc)}

    total_sent = (
        results.get("abandoned_cart_fixer", {}).get("sent", 0)
        + results.get("lead_email_blaster", {}).get("sent", 0)
    )
    log.info("EmailRevenueEngine: blast complete — %d emails sent", total_sent)
    results["total_sent"] = total_sent
    return results


# ═════════════════════════════════════════════════════════════════════════════
# AIOHTTP ROUTE HANDLERS (register in dashboard/server.py)
# ═════════════════════════════════════════════════════════════════════════════

async def handle_email_stats(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """GET /api/email/stats"""
    try:
        stats = await daily_stats()
        return aiohttp.web.json_response({"ok": True, "data": stats})
    except Exception as exc:
        log.error("handle_email_stats error: %s", exc)
        return aiohttp.web.json_response({"ok": False, "error": str(exc)}, status=500)


async def handle_sendgrid_webhook(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """POST /api/webhooks/sendgrid
    Verarbeitet SendGrid Event-Webhooks: bounce, unsubscribe, spam_report.
    Schreibt bounced-Status in ere_sends und markiert Leads in mass_outreach.
    """
    try:
        events = await request.json()
    except Exception:
        return aiohttp.web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

    if not isinstance(events, list):
        events = [events]

    processed = 0
    for ev in events:
        email_addr = (ev.get("email") or "").lower().strip()
        event_type = (ev.get("event") or "").lower()
        if not email_addr:
            continue

        if event_type in ("bounce", "blocked", "dropped"):
            # Mark in ere_sends
            try:
                conn = _db()
                conn.execute(
                    "UPDATE ere_sends SET status='bounced' WHERE email=? AND status='sent'",
                    (email_addr,),
                )
                conn.commit()
                conn.close()
            except Exception as exc:
                log.warning("Bounce DB update error (%s): %s", email_addr, exc)

            # Mark in mass_outreach leads table
            try:
                from pathlib import Path as _Path
                _mo_db = DATA_DIR / "mass_outreach.db"
                if _mo_db.exists():
                    import sqlite3 as _sq
                    _c = _sq.connect(str(_mo_db))
                    _c.execute(
                        "UPDATE leads SET status='bounced' WHERE email=?", (email_addr,)
                    )
                    _c.commit()
                    _c.close()
            except Exception as exc:
                log.warning("mass_outreach bounce update error (%s): %s", email_addr, exc)

            log.info("Bounce recorded for %s (event=%s)", email_addr, event_type)
            processed += 1

        elif event_type in ("unsubscribe", "spamreport"):
            # Unified unsubscribe across all systems
            try:
                from modules.mass_outreach_1000 import handle_unsubscribe as _mo_unsub
                _mo_unsub(email_addr)
            except Exception as exc:
                log.warning("Unified unsubscribe error (%s): %s", email_addr, exc)
            # Also mark ere_sends
            try:
                conn = _db()
                conn.execute(
                    "UPDATE ere_sends SET status='unsubscribed' WHERE email=? AND status='sent'",
                    (email_addr,),
                )
                conn.commit()
                conn.close()
            except Exception as exc:
                log.warning("ere_sends unsubscribe update error (%s): %s", email_addr, exc)
            log.info("Unsubscribe recorded for %s (event=%s)", email_addr, event_type)
            processed += 1

    return aiohttp.web.json_response({"ok": True, "processed": processed})


async def handle_email_blast(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """POST /api/email/blast-now
    Optional JSON body: { "subsystem": "all|cart|leads|klaviyo|welcome", "max": 200 }
    """
    try:
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass

        subsystem = body.get("subsystem", "all")
        max_sends  = int(body.get("max", 200))

        if subsystem == "cart":
            result = await abandoned_cart_fixer()
        elif subsystem == "leads":
            result = await lead_email_blaster(max_per_run=max_sends)
        elif subsystem == "klaviyo":
            result = await klaviyo_activator()
        elif subsystem == "welcome":
            result = await welcome_sequence_trigger()
        else:
            result = await run_full_blast()

        return aiohttp.web.json_response({"ok": True, "result": result})
    except Exception as exc:
        log.error("handle_email_blast error: %s", exc)
        return aiohttp.web.json_response({"ok": False, "error": str(exc)}, status=500)


# ── Module status helper ───────────────────────────────────────────────────────

def get_status() -> Dict[str, Any]:
    """Returns module health status — called by dashboard /health endpoint."""
    smtp_count  = len(_build_smtp_pool())
    conn        = _db()
    send_today  = conn.execute(
        "SELECT COUNT(*) as n FROM ere_sends WHERE date(sent_at)=?",
        (date.today().isoformat(),)
    ).fetchone()["n"]
    flows_live  = conn.execute(
        "SELECT COUNT(*) as n FROM ere_flows WHERE status='live'"
    ).fetchone()["n"]
    conn.close()
    return {
        "module":           "email_revenue_engine",
        "version":          "1.0",
        "klaviyo_key_set":  bool(KLAVIYO_KEY),
        "sendgrid_key_set": bool(SENDGRID_KEY),
        "anthropic_key_set":bool(ANTHROPIC_KEY),
        "smtp_accounts":    smtp_count,
        "flows_live":       flows_live,
        "sends_today":      send_today,
    }
