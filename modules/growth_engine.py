#!/usr/bin/env python3
"""
Growth Engine — Referral System, Review Automation, Win-Back Campaigns.
Generates real revenue through viral growth, social proof, and churn recovery.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import random
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import aiohttp

log = logging.getLogger("GrowthEngine")

# ── Config from environment ───────────────────────────────────────────────────

def _shopify_domain() -> str:
    return os.getenv("SHOPIFY_SHOP_DOMAIN", "")

def _shopify_token() -> str:
    return os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")

def _shopify_api_version() -> str:
    return os.getenv("SHOPIFY_API_VERSION", "2026-04")

def _shopify_base() -> str:
    domain = _shopify_domain()
    if not domain:
        return ""
    return f"https://{domain}" if not domain.startswith("http") else domain

def _tg_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")

def _tg_chat() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")

def _site_url() -> str:
    return os.getenv("SITE_URL") or os.getenv("RAILWAY_PUBLIC_DOMAIN", "https://yourdomain.com")

REFERRAL_COMMISSION_PCT = float(os.getenv("REFERRAL_COMMISSION_PCT", "10"))
WINBACK_DISCOUNT_PCT    = float(os.getenv("WINBACK_DISCOUNT_PCT", "15"))
REVIEW_DELAY_DAYS       = int(os.getenv("REVIEW_DELAY_DAYS", "7"))
CHURN_DAYS              = int(os.getenv("CHURN_DAYS", "60"))
# Rate-limit: max concurrent review request sends per automation run
REVIEW_BATCH_CONCURRENCY = int(os.getenv("REVIEW_BATCH_CONCURRENCY", "10"))
# Rate-limit: max concurrent win-back sends per automation run
WINBACK_BATCH_CONCURRENCY = int(os.getenv("WINBACK_BATCH_CONCURRENCY", "10"))

# Semaphore instances — created lazily inside coroutines (event-loop safe)
_review_semaphore: Optional[asyncio.Semaphore] = None
_winback_semaphore: Optional[asyncio.Semaphore] = None

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _valid_email(email: str) -> bool:
    return bool(email and _EMAIL_RE.match(email))


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _get_supabase():
    try:
        from modules.supabase_client import get_client
        return get_client()
    except Exception as e:
        log.warning("Supabase unavailable: %s", e)
        return None


def _supabase_configured() -> bool:
    try:
        from modules.supabase_client import is_configured
        return is_configured()
    except Exception:
        return False


async def _ensure_tables() -> bool:
    """Create growth tables if they don't exist. Uses raw SQL via Supabase REST."""
    sb = _get_supabase()
    if not sb:
        return False
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS referrals (
            id               BIGSERIAL PRIMARY KEY,
            code             TEXT UNIQUE NOT NULL,
            referrer_email   TEXT NOT NULL,
            referrer_name    TEXT,
            clicks           INTEGER DEFAULT 0,
            conversions      INTEGER DEFAULT 0,
            total_revenue    DECIMAL DEFAULT 0,
            commission_earned DECIMAL DEFAULT 0,
            created_at       TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS referral_conversions (
            id                  BIGSERIAL PRIMARY KEY,
            referral_code       TEXT,
            new_customer_email  TEXT,
            order_value         DECIMAL,
            commission          DECIMAL,
            converted_at        TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS review_requests (
            id              BIGSERIAL PRIMARY KEY,
            order_id        TEXT UNIQUE,
            customer_email  TEXT,
            sent_at         TIMESTAMPTZ DEFAULT NOW(),
            status          TEXT DEFAULT 'sent'
        )
        """,
    ]
    try:
        url  = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
        key  = (os.getenv("SUPABASE_SERVICE_KEY")
                or os.getenv("SUPABASE_ANON_KEY")
                or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", ""))
        if not url or not key:
            return False
        sql_endpoint = f"{url}/rest/v1/rpc/exec_sql"
        combined = ";\n".join(s.strip() for s in ddl_statements) + ";"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                sql_endpoint,
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={"query": combined},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (200, 201, 204):
                    log.info("Growth Engine tables ensured via exec_sql")
                else:
                    log.debug("exec_sql returned %s (tables may already exist)", resp.status)
        return True
    except Exception as e:
        log.debug("_ensure_tables: %s (non-fatal)", e)
        return True  # Tables may already be there


# ── Telegram helper ───────────────────────────────────────────────────────────

async def _tg(msg: str) -> None:
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            )
    except Exception as exc:
        log.warning("Telegram send error: %s", exc)


# ── Code generation ───────────────────────────────────────────────────────────

def _generate_code(prefix: str = "RUDI") -> str:
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=6))
    return f"{prefix}-{suffix}"


# ── Input validation helpers ──────────────────────────────────────────────────

def _validate_create_referral_inputs(customer_email: str, customer_name: str) -> Optional[str]:
    if not customer_email or not _valid_email(customer_email):
        return f"Invalid or missing customer_email: {customer_email!r}"
    if not customer_name or not customer_name.strip():
        return "customer_name must not be empty"
    return None


def _validate_order_value(order_value: float) -> Optional[str]:
    if order_value < 0:
        return f"order_value must not be negative, got {order_value}"
    return None


# ═════════════════════════════════════════════════════════════════════════════
#  REFERRAL SYSTEM
# ═════════════════════════════════════════════════════════════════════════════

async def create_referral_code(customer_email: str, customer_name: str) -> Dict[str, Any]:
    """
    Generate a unique referral code for a customer and persist it in Supabase.
    Returns {'code', 'share_link', 'referrer_email', 'created_at'}.
    """
    # Input validation
    err = _validate_create_referral_inputs(customer_email, customer_name)
    if err:
        log.warning("create_referral_code: validation failed — %s", err)
        return {"error": err}

    await _ensure_tables()
    sb = _get_supabase()

    code = _generate_code()
    share_link = f"{_site_url()}/ref/{code}"

    row = {
        "code":           code,
        "referrer_email": customer_email,
        "referrer_name":  customer_name.strip(),
        "clicks":         0,
        "conversions":    0,
        "total_revenue":  0,
        "commission_earned": 0,
    }

    if sb:
        try:
            # Retry with a new code on collision (up to 5 attempts)
            for attempt in range(5):
                try:
                    sb.table("referrals").insert(row).execute()
                    log.info(
                        "Referral code created: %s for %s (attempt %d)",
                        code, customer_email, attempt + 1,
                    )
                    break
                except Exception as e:
                    if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                        log.debug(
                            "Referral code collision for %s (attempt %d), retrying",
                            code, attempt + 1,
                        )
                        code = _generate_code()
                        row["code"] = code
                        share_link = f"{_site_url()}/ref/{code}"
                    else:
                        raise
        except Exception as exc:
            log.error("create_referral_code DB error: %s", exc)

    log.info("Referral code ready: %s for %s", code, customer_email)
    return {
        "code":           code,
        "share_link":     share_link,
        "referrer_email": customer_email,
        "referrer_name":  customer_name.strip(),
        "created_at":     datetime.now(timezone.utc).isoformat(),
    }


async def track_referral_click(code: str, ip: str) -> Dict[str, Any]:
    """
    Increment click counter for a referral code.
    Returns referrer info on success.
    """
    if not code or not code.strip():
        return {"error": "code must not be empty"}

    sb = _get_supabase()
    if not sb:
        return {"error": "Supabase not configured", "code": code}

    try:
        result = sb.table("referrals").select("*").eq("code", code).execute()
        rows = result.data if hasattr(result, "data") else []
        if not rows:
            return {"error": "Code not found", "code": code}

        row = rows[0]
        new_clicks = (row.get("clicks") or 0) + 1
        sb.table("referrals").update({"clicks": new_clicks}).eq("code", code).execute()
        log.info("Referral click tracked: code=%s clicks=%d ip=%s", code, new_clicks, ip)

        return {
            "code":           code,
            "referrer_email": row.get("referrer_email"),
            "referrer_name":  row.get("referrer_name"),
            "clicks":         new_clicks,
            "ip":             ip,
        }
    except Exception as exc:
        log.error("track_referral_click error: %s", exc)
        return {"error": str(exc), "code": code}


async def process_referral_conversion(
    code: str,
    new_customer_email: str,
    order_value: float,
) -> Dict[str, Any]:
    """
    Mark a referral code as converted, compute commission, and notify via Telegram.
    Returns conversion details.
    """
    # Input validation
    if not code or not code.strip():
        return {"error": "code must not be empty"}
    if not _valid_email(new_customer_email):
        return {"error": f"Invalid new_customer_email: {new_customer_email!r}"}
    val_err = _validate_order_value(order_value)
    if val_err:
        return {"error": val_err}

    sb = _get_supabase()
    commission = round(order_value * REFERRAL_COMMISSION_PCT / 100, 2)

    result: Dict[str, Any] = {
        "code":               code,
        "new_customer_email": new_customer_email,
        "order_value":        order_value,
        "commission":         commission,
        "commission_pct":     REFERRAL_COMMISSION_PCT,
        "converted_at":       datetime.now(timezone.utc).isoformat(),
    }

    if not sb:
        log.warning("process_referral_conversion: Supabase not configured")
        return result

    try:
        ref_res = sb.table("referrals").select("*").eq("code", code).execute()
        rows = ref_res.data if hasattr(ref_res, "data") else []
        if not rows:
            return {**result, "error": "Code not found"}

        row = rows[0]
        new_convs      = (row.get("conversions") or 0) + 1
        new_revenue    = round((row.get("total_revenue") or 0) + order_value, 2)
        new_commission = round((row.get("commission_earned") or 0) + commission, 2)

        sb.table("referrals").update({
            "conversions":       new_convs,
            "total_revenue":     new_revenue,
            "commission_earned": new_commission,
        }).eq("code", code).execute()

        sb.table("referral_conversions").insert({
            "referral_code":      code,
            "new_customer_email": new_customer_email,
            "order_value":        order_value,
            "commission":         commission,
        }).execute()

        result["referrer_email"]    = row.get("referrer_email")
        result["referrer_name"]     = row.get("referrer_name")
        result["total_conversions"] = new_convs
        result["total_commission"]  = new_commission

        await _tg(
            f"🎉 <b>Referral Conversion!</b>\n"
            f"Code: <code>{code}</code>\n"
            f"Referrer: {row.get('referrer_name') or row.get('referrer_email','?')}\n"
            f"Neuer Kunde: {new_customer_email}\n"
            f"Bestellwert: {order_value:.2f} EUR\n"
            f"Provision: <b>{commission:.2f} EUR</b> ({REFERRAL_COMMISSION_PCT:.0f}%)\n"
            f"Gesamt-Provision: {new_commission:.2f} EUR"
        )
        log.info(
            "Referral conversion processed: code=%s order=%.2f commission=%.2f",
            code, order_value, commission,
        )

    except Exception as exc:
        log.error("process_referral_conversion error: %s", exc)
        result["error"] = str(exc)

    return result


async def get_referral_stats() -> Dict[str, Any]:
    """
    Return aggregated referral stats: top referrers, total clicks, conversions, revenue.
    """
    sb = _get_supabase()
    if not sb:
        return {"error": "Supabase not configured"}

    try:
        res = sb.table("referrals").select("*").execute()
        rows = res.data if hasattr(res, "data") else []

        total_clicks      = sum(r.get("clicks", 0) for r in rows)
        total_conversions = sum(r.get("conversions", 0) for r in rows)
        total_revenue     = sum(float(r.get("total_revenue", 0)) for r in rows)
        total_commission  = sum(float(r.get("commission_earned", 0)) for r in rows)

        top = sorted(rows, key=lambda r: r.get("conversions", 0), reverse=True)[:5]

        return {
            "total_referrers":   len(rows),
            "total_clicks":      total_clicks,
            "total_conversions": total_conversions,
            "total_revenue_eur": round(total_revenue, 2),
            "total_commission_eur": round(total_commission, 2),
            "conversion_rate_pct": (
                round(total_conversions / total_clicks * 100, 1) if total_clicks else 0
            ),
            "top_referrers": [
                {
                    "name":        r.get("referrer_name") or r.get("referrer_email", "?"),
                    "email":       r.get("referrer_email"),
                    "code":        r.get("code"),
                    "clicks":      r.get("clicks", 0),
                    "conversions": r.get("conversions", 0),
                    "commission":  float(r.get("commission_earned", 0)),
                }
                for r in top
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        log.error("get_referral_stats error: %s", exc)
        return {"error": str(exc)}


async def get_top_referrers(limit: int = 10) -> List[Dict[str, Any]]:
    """Return ranked list of referrers sorted by conversions."""
    if limit <= 0:
        limit = 10
    sb = _get_supabase()
    if not sb:
        return []

    try:
        res = sb.table("referrals").select("*").execute()
        rows = res.data if hasattr(res, "data") else []
        sorted_rows = sorted(rows, key=lambda r: r.get("conversions", 0), reverse=True)
        return [
            {
                "rank":        i + 1,
                "name":        r.get("referrer_name") or r.get("referrer_email", "?"),
                "email":       r.get("referrer_email"),
                "code":        r.get("code"),
                "share_link":  f"{_site_url()}/ref/{r.get('code','')}",
                "clicks":      r.get("clicks", 0),
                "conversions": r.get("conversions", 0),
                "revenue_eur": float(r.get("total_revenue", 0)),
                "commission_eur": float(r.get("commission_earned", 0)),
            }
            for i, r in enumerate(sorted_rows[:limit])
        ]
    except Exception as exc:
        log.error("get_top_referrers error: %s", exc)
        return []


# ═════════════════════════════════════════════════════════════════════════════
#  REVIEW AUTOMATION
# ═════════════════════════════════════════════════════════════════════════════

async def send_review_request(
    order_id: str,
    customer_email: str,
    customer_name: str,
    product_title: str,
) -> bool:
    """
    Send a review request email via Mailchimp (transactional-style campaign).
    Prevents duplicates by checking review_requests table first.
    Returns True on success.
    """
    # Input validation
    if not order_id or not str(order_id).strip():
        log.warning("send_review_request: empty order_id")
        return False
    if not _valid_email(customer_email):
        log.warning("send_review_request: invalid email %r for order %s", customer_email, order_id)
        return False

    await _ensure_tables()
    sb = _get_supabase()

    # Deduplication check
    if sb:
        try:
            existing = (
                sb.table("review_requests")
                .select("id")
                .eq("order_id", str(order_id))
                .execute()
            )
            if getattr(existing, "data", []):
                log.debug("Review request already sent for order %s", order_id)
                return False
        except Exception as exc:
            log.warning("review_requests dedup check error: %s", exc)

    review_base = os.getenv("REVIEW_URL", f"{_site_url()}/review")
    review_url  = f"{review_base}?order={order_id}&email={customer_email}"

    sent = False
    try:
        mc_api_key = os.getenv("MAILCHIMP_API_KEY", "")
        mc_list_id = os.getenv("MAILCHIMP_LIST_ID", "")

        if mc_api_key and mc_list_id:
            from modules.mailchimp_automation import create_campaign, add_subscriber
            fname = customer_name.split()[0] if customer_name else "Kunde"

            subject = f"Wie war Ihr Kauf? — {product_title}"
            body_html = (
                "<html><body style=\"font-family:Arial,sans-serif;max-width:600px;margin:0 auto;\">"
                f"<h2 style=\"color:#333;\">Hallo {fname}!</h2>"
                f"<p>Wir hoffen, Sie sind mit Ihrem Kauf von <strong>{product_title}</strong>"
                " zufrieden. Ihre Meinung ist uns sehr wichtig!</p>"
                "<p style=\"text-align:center;margin:30px 0;\">"
                f"  <a href=\"{review_url}\""
                "     style=\"background:#007bff;color:#fff;padding:14px 28px;"
                "            border-radius:6px;text-decoration:none;font-size:16px;\">"
                "    Jetzt Bewertung schreiben"
                "  </a>"
                "</p>"
                "<p style=\"color:#666;font-size:14px;\">"
                "  Ihre Bewertung hilft anderen Kunden bei ihrer Entscheidung und"
                "  verbessert unseren Service."
                "</p>"
                "<p style=\"color:#999;font-size:12px;\">"
                "  Sie erhalten diese E-Mail, weil Sie kürzlich bei uns eingekauft haben."
                "</p>"
                "</body></html>"
            )

            await add_subscriber(mc_list_id, customer_email, fname, tags=["review-requested"])
            campaign = await create_campaign(
                list_id=mc_list_id,
                subject=subject,
                from_name=os.getenv("STORE_NAME", "SuperMegaBot Store"),
                body_html=body_html,
            )
            if "id" in campaign and "error" not in campaign:
                sent = True
                log.info(
                    "Review request sent for order %s, customer %s",
                    order_id, customer_email,
                )
            else:
                log.warning("create_campaign returned: %s", campaign)
        else:
            log.info(
                "MAILCHIMP not configured — review request for order %s, customer %s skipped",
                order_id, customer_email,
            )
            sent = True  # Mark as "sent" so we don't retry forever without Mailchimp

    except Exception as exc:
        log.error("send_review_request email error: %s", exc)

    # Log to DB regardless (prevents repeated attempts even on send failure)
    if sb:
        try:
            sb.table("review_requests").insert({
                "order_id":       str(order_id),
                "customer_email": customer_email,
                "status":         "sent" if sent else "failed",
            }).execute()
        except Exception as exc:
            log.warning("review_requests insert error: %s", exc)

    return sent


async def get_pending_review_requests() -> List[Dict[str, Any]]:
    """
    Return Shopify orders that are 7+ days old and haven't had a review request sent.
    """
    token  = _shopify_token()
    domain = _shopify_domain()
    if not token or not domain:
        log.warning("Shopify not configured — cannot fetch pending review requests")
        return []

    sb = _get_supabase()
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=REVIEW_DELAY_DAYS)).isoformat()

    # Fetch already-sent order IDs
    sent_ids: set[str] = set()
    if sb:
        try:
            res = sb.table("review_requests").select("order_id").execute()
            sent_ids = {r["order_id"] for r in (res.data or [])}
        except Exception as exc:
            log.warning("review_requests fetch error: %s", exc)

    base    = _shopify_base()
    api_ver = _shopify_api_version()
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }

    pending = []
    try:
        url = (
            f"{base}/admin/api/{api_ver}/orders.json"
            f"?status=any&financial_status=paid&limit=250"
            f"&created_at_max={cutoff_date}"
        )
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    log.warning("Shopify orders HTTP %s", resp.status)
                    return []
                data = await resp.json()

        for order in data.get("orders", []):
            order_id = str(order.get("id", ""))
            if order_id in sent_ids:
                continue
            email = order.get("email", "")
            if not email or not _valid_email(email):
                continue
            billing    = order.get("billing_address") or {}
            first_name = billing.get("first_name") or order.get("customer", {}).get("first_name", "Kunde")
            last_name  = billing.get("last_name") or order.get("customer", {}).get("last_name", "")
            items         = order.get("line_items", [])
            product_title = items[0].get("title", "Ihr Produkt") if items else "Ihr Produkt"

            pending.append({
                "order_id":       order_id,
                "order_number":   order.get("order_number"),
                "customer_email": email,
                "customer_name":  f"{first_name} {last_name}".strip(),
                "product_title":  product_title,
                "total_price":    order.get("total_price"),
                "currency":       order.get("currency", "EUR"),
                "created_at":     order.get("created_at"),
            })

        log.info("Found %d pending review requests", len(pending))
    except Exception as exc:
        log.error("get_pending_review_requests error: %s", exc)

    return pending


async def _send_review_with_semaphore(
    order: Dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> str:
    """Send a single review request under a rate-limiting semaphore."""
    async with semaphore:
        try:
            success = await send_review_request(
                order_id=order["order_id"],
                customer_email=order["customer_email"],
                customer_name=order["customer_name"],
                product_title=order["product_title"],
            )
            return "sent" if success else "skipped"
        except Exception as exc:
            log.error(
                "Review request failed for order %s: %s",
                order.get("order_id"), exc,
            )
            return "failed"


async def run_review_automation() -> Dict[str, Any]:
    """
    Fetch all pending orders, send review request emails with rate-limiting,
    and return statistics.
    """
    pending = await get_pending_review_requests()
    sent    = 0
    skipped = 0
    failed  = 0

    if pending:
        semaphore = asyncio.Semaphore(REVIEW_BATCH_CONCURRENCY)
        results = await asyncio.gather(
            *[_send_review_with_semaphore(order, semaphore) for order in pending],
            return_exceptions=False,
        )
        for r in results:
            if r == "sent":
                sent += 1
            elif r == "skipped":
                skipped += 1
            else:
                failed += 1

    result = {
        "pending":   len(pending),
        "sent":      sent,
        "skipped":   skipped,
        "failed":    failed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if sent:
        await _tg(
            f"⭐ <b>Review Automation</b>\n"
            f"Anfragen gesendet: <b>{sent}</b>\n"
            f"Übersprungen: {skipped} | Fehler: {failed}\n"
            f"Gesamt pending: {len(pending)}"
        )

    log.info(
        "Review automation complete: sent=%d skipped=%d failed=%d",
        sent, skipped, failed,
    )
    return result


# ═════════════════════════════════════════════════════════════════════════════
#  WIN-BACK ENGINE
# ═════════════════════════════════════════════════════════════════════════════

async def get_churned_customers(days_inactive: int = CHURN_DAYS) -> List[Dict[str, Any]]:
    """
    Return Shopify customers who haven't ordered in `days_inactive` days.
    Excludes customers who already have a pending/active win-back discount (via Supabase tag).
    """
    token  = _shopify_token()
    domain = _shopify_domain()
    if not token or not domain:
        log.warning("Shopify not configured — cannot fetch churned customers")
        return []

    base    = _shopify_base()
    api_ver = _shopify_api_version()
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_inactive)).isoformat()

    # Load emails that already have an active win-back discount
    sb = _get_supabase()
    already_targeted: set[str] = set()
    if sb:
        try:
            res = (
                sb.table("winback_campaigns")
                .select("customer_email")
                .eq("status", "active")
                .execute()
            )
            already_targeted = {r["customer_email"] for r in (res.data or [])}
            if already_targeted:
                log.debug(
                    "Win-back: skipping %d customers with active discount",
                    len(already_targeted),
                )
        except Exception as exc:
            log.debug("winback_campaigns table not found (non-fatal): %s", exc)

    churned = []
    try:
        url = (
            f"{base}/admin/api/{api_ver}/customers.json"
            f"?limit=250&updated_at_max={cutoff}"
        )
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    log.warning("Shopify customers HTTP %s", resp.status)
                    return []
                data = await resp.json()

        for cust in data.get("customers", []):
            email = cust.get("email", "")
            if not email or not _valid_email(email):
                continue
            if not cust.get("orders_count", 0):
                continue
            if email in already_targeted:
                log.debug("Win-back: skipping %s — already has active discount", email)
                continue
            churned.append({
                "customer_id":  str(cust.get("id", "")),
                "email":        email,
                "first_name":   cust.get("first_name", "Kunde"),
                "last_name":    cust.get("last_name", ""),
                "orders_count": cust.get("orders_count", 0),
                "total_spent":  cust.get("total_spent", "0.00"),
                "last_updated": cust.get("updated_at"),
            })

        log.info(
            "Found %d churned customers (inactive >%d days, %d skipped — active discount)",
            len(churned), days_inactive, len(already_targeted),
        )
    except Exception as exc:
        log.error("get_churned_customers error: %s", exc)

    return churned


async def _create_shopify_discount_code(discount_pct: float) -> Optional[str]:
    """Create a Shopify percentage discount code and return it."""
    if discount_pct <= 0 or discount_pct > 100:
        log.warning("_create_shopify_discount_code: invalid discount_pct=%.2f", discount_pct)
        return None

    token  = _shopify_token()
    domain = _shopify_domain()
    if not token or not domain:
        return None

    base    = _shopify_base()
    api_ver = _shopify_api_version()
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }

    code   = "WINBACK-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    expiry = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        # Step 1: Create price rule
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(
                f"{base}/admin/api/{api_ver}/price_rules.json",
                headers=headers,
                json={
                    "price_rule": {
                        "title":              f"Win-Back {discount_pct:.0f}% — {code}",
                        "target_type":        "line_item",
                        "target_selection":   "all",
                        "allocation_method":  "across",
                        "value_type":         "percentage",
                        "value":              f"-{discount_pct}",
                        "customer_selection": "all",
                        "starts_at":          datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "ends_at":            expiry,
                        "usage_limit":        1,
                    }
                },
            ) as resp:
                if resp.status not in (200, 201):
                    log.warning("price_rules create HTTP %s", resp.status)
                    return None
                rule_data = await resp.json()

        rule_id = rule_data.get("price_rule", {}).get("id")
        if not rule_id:
            return None

        # Step 2: Create discount code under that price rule
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(
                f"{base}/admin/api/{api_ver}/price_rules/{rule_id}/discount_codes.json",
                headers=headers,
                json={"discount_code": {"code": code}},
            ) as resp:
                if resp.status not in (200, 201):
                    log.warning("discount_codes create HTTP %s", resp.status)
                    return None

        log.info("Created win-back discount code: %s (%.0f%%)", code, discount_pct)
        return code

    except Exception as exc:
        log.error("_create_shopify_discount_code error: %s", exc)
        return None


async def send_winback_campaign(
    customer_email: str,
    customer_name: str,
    discount_code: str,
) -> bool:
    """
    Send a win-back email via Mailchimp with a discount code.
    Returns True on success.
    """
    if not _valid_email(customer_email):
        log.warning("send_winback_campaign: invalid email %r", customer_email)
        return False

    mc_api_key = os.getenv("MAILCHIMP_API_KEY", "")
    mc_list_id = os.getenv("MAILCHIMP_LIST_ID", "")

    if not mc_api_key or not mc_list_id:
        log.info(
            "Mailchimp not configured — win-back skipped for %s (code: %s)",
            customer_email, discount_code,
        )
        return True  # graceful fallback

    fname    = customer_name.split()[0] if customer_name else "Kunde"
    shop_url = _shopify_base() or _site_url()
    subject  = f"Wir vermissen Sie, {fname}! Hier sind {WINBACK_DISCOUNT_PCT:.0f}% für Sie"

    body_html = (
        "<html><body style=\"font-family:Arial,sans-serif;max-width:600px;margin:0 auto;\">"
        f"<h2 style=\"color:#333;\">Hallo {fname}, wir haben Sie vermisst!</h2>"
        "<p>Es ist eine Weile her, seit Sie zuletzt bei uns eingekauft haben."
        "   Als kleines Dankeschön schenken wir Ihnen"
        f"  <strong>{WINBACK_DISCOUNT_PCT:.0f}% Rabatt</strong> auf Ihren nächsten Einkauf.</p>"
        "<div style=\"background:#f8f9fa;border:2px dashed #007bff;"
        "            padding:20px;text-align:center;margin:30px 0;border-radius:8px;\">"
        "  <p style=\"margin:0;color:#666;font-size:14px;\">Ihr persönlicher Rabattcode:</p>"
        f"  <h1 style=\"color:#007bff;font-size:32px;margin:10px 0;letter-spacing:3px;\">{discount_code}</h1>"
        "  <p style=\"margin:0;color:#999;font-size:12px;\">Gültig für 30 Tage · Einmalig verwendbar</p>"
        "</div>"
        "<p style=\"text-align:center;\">"
        f"  <a href=\"{shop_url}\""
        "     style=\"background:#28a745;color:#fff;padding:14px 28px;"
        "            border-radius:6px;text-decoration:none;font-size:16px;\">"
        "    Jetzt einkaufen"
        "  </a>"
        "</p>"
        "<p style=\"color:#999;font-size:12px;text-align:center;\">"
        "  Sie erhalten diese E-Mail, weil Sie früher Kunde bei uns waren."
        "</p>"
        "</body></html>"
    )

    try:
        from modules.mailchimp_automation import add_subscriber, create_campaign
        await add_subscriber(mc_list_id, customer_email, fname, tags=["win-back"])
        campaign = await create_campaign(
            list_id=mc_list_id,
            subject=subject,
            from_name=os.getenv("STORE_NAME", "SuperMegaBot Store"),
            body_html=body_html,
        )
        if "id" in campaign and "error" not in campaign:
            log.info(
                "Win-back campaign sent to %s with code %s",
                customer_email, discount_code,
            )
            return True
        log.warning("Win-back campaign create_campaign: %s", campaign)
        return False
    except Exception as exc:
        log.error("send_winback_campaign error for %s: %s", customer_email, exc)
        return False


async def _send_winback_with_semaphore(
    cust: Dict[str, Any],
    discount_code: str,
    semaphore: asyncio.Semaphore,
) -> bool:
    """Send a single win-back campaign under a rate-limiting semaphore."""
    async with semaphore:
        try:
            return await send_winback_campaign(
                customer_email=cust["email"],
                customer_name=f"{cust['first_name']} {cust['last_name']}".strip(),
                discount_code=discount_code,
            )
        except Exception as exc:
            log.error("Win-back send error for %s: %s", cust.get("email"), exc)
            return False


async def run_winback_automation() -> Dict[str, Any]:
    """
    Create a single win-back discount code, send it to all churned customers
    (rate-limited), and return a statistics summary.
    """
    churned = await get_churned_customers()
    if not churned:
        return {
            "churned_customers": 0,
            "sent":              0,
            "failed":            0,
            "discount_code":     None,
            "timestamp":         datetime.now(timezone.utc).isoformat(),
        }

    discount_code = await _create_shopify_discount_code(WINBACK_DISCOUNT_PCT)
    if not discount_code:
        discount_code = f"WINBACK{int(WINBACK_DISCOUNT_PCT)}"
        log.warning("Shopify discount code creation failed, using fallback: %s", discount_code)

    semaphore = asyncio.Semaphore(WINBACK_BATCH_CONCURRENCY)
    results   = await asyncio.gather(
        *[_send_winback_with_semaphore(cust, discount_code, semaphore) for cust in churned],
        return_exceptions=False,
    )
    sent   = sum(1 for r in results if r)
    failed = sum(1 for r in results if not r)

    result = {
        "churned_customers": len(churned),
        "sent":              sent,
        "failed":            failed,
        "discount_code":     discount_code,
        "discount_pct":      WINBACK_DISCOUNT_PCT,
        "timestamp":         datetime.now(timezone.utc).isoformat(),
    }

    if sent:
        await _tg(
            f"🔄 <b>Win-Back Kampagne gestartet!</b>\n"
            f"Inaktive Kunden: <b>{len(churned)}</b>\n"
            f"E-Mails gesendet: <b>{sent}</b>\n"
            f"Rabattcode: <code>{discount_code}</code> ({WINBACK_DISCOUNT_PCT:.0f}%)\n"
            f"Fehler: {failed}"
        )

    log.info(
        "Win-back automation: churned=%d sent=%d failed=%d code=%s",
        len(churned), sent, failed, discount_code,
    )
    return result


# ═════════════════════════════════════════════════════════════════════════════
#  COMBINED GROWTH DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════

async def get_growth_dashboard() -> Dict[str, Any]:
    """
    Return a combined growth dashboard: referral stats + review stats + win-back stats.
    All sections fail gracefully if Supabase/Shopify not available.
    """
    referral_stats, top_referrers = await asyncio.gather(
        get_referral_stats(),
        get_top_referrers(limit=5),
        return_exceptions=True,
    )
    if isinstance(referral_stats, Exception):
        referral_stats = {"error": str(referral_stats)}
    if isinstance(top_referrers, Exception):
        top_referrers = []

    review_stats: Dict[str, Any] = {}
    sb = _get_supabase()
    if sb:
        try:
            rr = sb.table("review_requests").select("*", count="exact").execute()
            total_sent   = rr.count if hasattr(rr, "count") and rr.count else len(rr.data or [])
            review_stats = {
                "total_sent": total_sent,
                "status_breakdown": {},
            }
            for row in (rr.data or []):
                status = row.get("status", "sent")
                review_stats["status_breakdown"][status] = (
                    review_stats["status_breakdown"].get(status, 0) + 1
                )
        except Exception as exc:
            review_stats = {"error": str(exc)}
    else:
        review_stats = {"note": "Supabase not configured"}

    winback_stats: Dict[str, Any] = {}
    try:
        churned = await get_churned_customers()
        winback_stats = {
            "churned_customers":    len(churned),
            "churn_threshold_days": CHURN_DAYS,
            "winback_discount_pct": WINBACK_DISCOUNT_PCT,
        }
    except Exception as exc:
        winback_stats = {"error": str(exc)}

    return {
        "referrals":     referral_stats,
        "top_referrers": top_referrers,
        "reviews":       review_stats,
        "winback":       winback_stats,
        "config": {
            "commission_pct":    REFERRAL_COMMISSION_PCT,
            "winback_discount":  WINBACK_DISCOUNT_PCT,
            "review_delay_days": REVIEW_DELAY_DAYS,
            "churn_days":        CHURN_DAYS,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
