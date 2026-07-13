"""
affiliate_system.py — Affiliate / Referral Tracking System
Generates unique links, tracks clicks/conversions, sends invites, runs outreach.
"""
import os
import logging
import sqlite3
import smtplib
import random
import string
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import aiohttp

log = logging.getLogger(__name__)

DB_PATH   = "data/affiliates.db"
SHOP_URL  = "https://ineedit.com.co"
COMMISSION_PCT = 20  # default 20%

# SMTP settings from env
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER") or os.getenv("EMAIL_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS") or os.getenv("EMAIL_PASS") or os.getenv("GMAIL_APP_PASSWORD", "")

SHOPIFY_SHOP_DOMAIN     = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_ADMIN_API_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_API_VERSION     = os.getenv("SHOPIFY_API_VERSION", "2024-01")

SUPABASE_URL         = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _db_init():
    conn = _db_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS affiliates (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            code           TEXT    UNIQUE NOT NULL,
            email          TEXT    NOT NULL,
            name           TEXT    DEFAULT '',
            commission_pct INTEGER DEFAULT 20,
            status         TEXT    DEFAULT 'active',
            created_at     TEXT    NOT NULL,
            total_earned   REAL    DEFAULT 0.0
        );
        CREATE TABLE IF NOT EXISTS clicks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            code       TEXT NOT NULL,
            ip         TEXT DEFAULT '',
            clicked_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS conversions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT NOT NULL,
            order_id    TEXT NOT NULL,
            order_value REAL NOT NULL,
            commission  REAL NOT NULL,
            status      TEXT DEFAULT 'pending',
            created_at  TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def _gen_code() -> str:
    """Generate a unique 8-char alphanumeric referral code."""
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=8))


def _unique_code() -> str:
    conn = _db_conn()
    for _ in range(20):
        code = _gen_code()
        if not conn.execute("SELECT 1 FROM affiliates WHERE code=?", (code,)).fetchone():
            conn.close()
            return code
    conn.close()
    raise RuntimeError("Could not generate unique affiliate code after 20 tries")


# ── Core functions ─────────────────────────────────────────────────────────────

def generate_affiliate_link(affiliate_email: str, product_url: str = SHOP_URL) -> dict:
    """
    Create or retrieve a unique tracking link for an affiliate.
    Returns {code, link, email}.
    """
    _db_init()
    conn = _db_conn()
    existing = conn.execute(
        "SELECT code FROM affiliates WHERE email=?", (affiliate_email,)
    ).fetchone()

    if existing:
        code = existing["code"]
        conn.close()
    else:
        code = _unique_code()
        conn.execute(
            "INSERT INTO affiliates (code, email, commission_pct, created_at) VALUES (?,?,?,?)",
            (code, affiliate_email, COMMISSION_PCT, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
        log.info("New affiliate code %s for %s", code, affiliate_email)

    link = f"{SHOP_URL}/?ref={code}"
    return {"code": code, "link": link, "email": affiliate_email}


def track_click(ref_code: str, ip_address: str = "") -> bool:
    """Record a click for the given referral code. Returns True if code exists."""
    _db_init()
    conn = _db_conn()
    exists = conn.execute("SELECT 1 FROM affiliates WHERE code=?", (ref_code,)).fetchone()
    if not exists:
        conn.close()
        return False
    conn.execute(
        "INSERT INTO clicks (code, ip, clicked_at) VALUES (?,?,?)",
        (ref_code, ip_address, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return True


def track_conversion(ref_code: str, order_id: str, order_value: float) -> dict:
    """
    Record a conversion and calculate commission.
    Returns {ok, commission, order_id}.
    """
    _db_init()
    conn = _db_conn()
    affiliate = conn.execute(
        "SELECT commission_pct, total_earned FROM affiliates WHERE code=?", (ref_code,)
    ).fetchone()
    if not affiliate:
        conn.close()
        return {"ok": False, "error": "affiliate_not_found"}

    commission = round(order_value * affiliate["commission_pct"] / 100, 2)
    conn.execute(
        "INSERT INTO conversions (code, order_id, order_value, commission, created_at) VALUES (?,?,?,?,?)",
        (ref_code, order_id, order_value, commission, datetime.now(timezone.utc).isoformat()),
    )
    conn.execute(
        "UPDATE affiliates SET total_earned=total_earned+? WHERE code=?",
        (commission, ref_code),
    )
    conn.commit()
    conn.close()
    log.info("Conversion tracked: code=%s order=%s value=%.2f commission=%.2f",
             ref_code, order_id, order_value, commission)
    return {"ok": True, "commission": commission, "order_id": order_id}


def get_affiliate_stats(affiliate_email: str) -> dict:
    """Return click/conversion/earnings stats for an affiliate."""
    _db_init()
    conn = _db_conn()
    aff = conn.execute(
        "SELECT code, commission_pct, total_earned, status FROM affiliates WHERE email=?",
        (affiliate_email,)
    ).fetchone()
    if not aff:
        conn.close()
        return {"error": "not_found"}

    code   = aff["code"]
    clicks = conn.execute("SELECT COUNT(*) FROM clicks WHERE code=?", (code,)).fetchone()[0]
    convs  = conn.execute(
        "SELECT COUNT(*), SUM(commission) FROM conversions WHERE code=?", (code,)
    ).fetchone()
    conn.close()

    return {
        "email":            affiliate_email,
        "code":             code,
        "link":             f"{SHOP_URL}/?ref={code}",
        "clicks":           clicks,
        "conversions":      convs[0] or 0,
        "commission_earned": float(convs[1] or 0),
        "pending_payout":   float(aff["total_earned"]),
        "commission_pct":   aff["commission_pct"],
        "status":           aff["status"],
    }


# ── Email invite ───────────────────────────────────────────────────────────────

def _build_invite_html(name: str, email: str, link: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8">
<style>
body{{font-family:Arial,sans-serif;background:#0f0f0f;color:#f0f0f0;margin:0;padding:24px}}
.card{{max-width:580px;margin:0 auto;background:#1a1a1a;border-radius:12px;padding:40px}}
h1{{color:#22c55e;margin-bottom:16px}}p{{color:#ccc;line-height:1.7}}
.code{{background:#111;border:1px solid #22c55e;border-radius:8px;padding:16px;
       font-size:22px;font-weight:700;color:#22c55e;text-align:center;
       letter-spacing:2px;margin:24px 0}}
.btn{{display:block;width:fit-content;margin:0 auto;padding:14px 32px;
      background:#22c55e;color:#000;font-weight:700;border-radius:8px;
      text-decoration:none;font-size:16px}}
</style></head>
<body><div class="card">
<h1>Hallo {name}! 👋</h1>
<p>Wir laden dich herzlich zu unserem <strong>Affiliate-Programm</strong> bei ineedit.com.co ein.</p>
<p>Als Partner erhältst du <strong>20% Provision</strong> auf jeden Verkauf, der über deinen persönlichen Link kommt.</p>
<p>Dein persönlicher Empfehlungslink:</p>
<div class="code">{link}</div>
<p>Teile diesen Link auf deinen Kanälen und verdiene mit jedem Verkauf passives Einkommen!</p>
<a href="{link}" class="btn">Jetzt starten →</a>
<p style="margin-top:24px;font-size:13px;color:#555">
Fragen? Schreib uns an info@ineedit.com.co<br>
ineedit.com.co · Smart Home &amp; Gadgets
</p>
</div></body></html>"""


async def send_affiliate_invite(email: str, name: str = "Partner") -> dict:
    """
    Generate an affiliate link for email and send a welcome invite.
    Returns {ok, code, link}.
    """
    entry = generate_affiliate_link(email)
    code  = entry["code"]
    link  = entry["link"]

    if not SMTP_USER or not SMTP_PASS:
        log.warning("SMTP not configured — affiliate invite not sent to %s", email)
        return {"ok": False, "error": "smtp_not_configured", "code": code, "link": link}

    html  = _build_invite_html(name, email, link)
    msg   = MIMEMultipart("alternative")
    msg["Subject"] = f"Du bist eingeladen: 20% Provision als ineedit Partner 🎉"
    msg["From"]    = SMTP_USER
    msg["To"]      = email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.sendmail(SMTP_USER, [email], msg.as_string())
        log.info("Affiliate invite sent to %s (code=%s)", email, code)
        return {"ok": True, "code": code, "link": link, "email": email}
    except Exception as exc:
        log.error("Affiliate invite SMTP error for %s: %s", email, exc)
        return {"ok": False, "error": str(exc), "code": code, "link": link}


# ── Outreach ───────────────────────────────────────────────────────────────────

async def _get_top_shopify_customers(limit: int = 20) -> list:
    """Fetch top repeat customers from Shopify."""
    if not SHOPIFY_SHOP_DOMAIN or not SHOPIFY_ADMIN_API_TOKEN:
        return []
    url = (
        f"https://{SHOPIFY_SHOP_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}"
        f"/customers.json?limit={limit}&order=orders_count+desc"
    )
    headers = {"X-Shopify-Access-Token": SHOPIFY_ADMIN_API_TOKEN}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as r:
                data = await r.json()
                return [
                    {
                        "email":  c.get("email", ""),
                        "name":   c.get("first_name") or c.get("last_name") or "Kunde",
                        "orders": c.get("orders_count", 0),
                    }
                    for c in data.get("customers", [])
                    if c.get("email") and c.get("orders_count", 0) >= 2
                ]
    except Exception as exc:
        log.error("Shopify customer fetch error: %s", exc)
        return []


async def run_affiliate_outreach() -> dict:
    """
    Automatically invite top Shopify customers to the affiliate program
    if not already invited.
    Returns {invited, skipped, errors}.
    """
    _db_init()
    customers = await _get_top_shopify_customers(50)
    invited   = 0
    skipped   = 0
    errors    = 0

    conn = _db_conn()
    existing_emails = {
        row[0] for row in conn.execute("SELECT email FROM affiliates").fetchall()
    }
    conn.close()

    for c in customers:
        email = c["email"]
        if email in existing_emails:
            skipped += 1
            continue
        result = await send_affiliate_invite(email, c["name"])
        if result.get("ok"):
            invited += 1
        else:
            # Still generate the link even if email failed
            generate_affiliate_link(email)
            errors += 1

    log.info("Affiliate outreach: invited=%d skipped=%d errors=%d", invited, skipped, errors)
    return {"invited": invited, "skipped": skipped, "errors": errors}


# ── Status ─────────────────────────────────────────────────────────────────────

def get_status() -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        _db_init()
        conn = _db_conn()
        affiliates_active = conn.execute(
            "SELECT COUNT(*) FROM affiliates WHERE status='active'"
        ).fetchone()[0]
        conversions_today = conn.execute(
            "SELECT COUNT(*), SUM(commission) FROM conversions WHERE created_at LIKE ?",
            (f"{today}%",)
        ).fetchone()
        conn.close()
        conv_count = conversions_today[0] or 0
        commissions = float(conversions_today[1] or 0)
    except Exception:
        affiliates_active = 0
        conv_count        = 0
        commissions       = 0.0

    return {
        "module":              "affiliate_system",
        "smtp_set":            bool(SMTP_USER and SMTP_PASS),
        "affiliates_active":   affiliates_active,
        "conversions_today":   conv_count,
        "commissions_pending": commissions,
    }
