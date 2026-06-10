#!/usr/bin/env python3
"""
Email Sequence Engine — Automatische E-Mail-Sequenzen

Manages welcome, post-purchase, win-back, and VIP email sequences.
Enrolls customers, generates personalized AI content, sends via Mailchimp,
tracks stats in Supabase.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

log = logging.getLogger("EmailSequenceEngine")

# ── Sequence definitions ──────────────────────────────────────────────────────

SEQUENCES: Dict[str, List[Dict]] = {
    "welcome": [
        {"day": 0, "subject": "Willkommen! Dein 10% Rabatt wartet", "template": "welcome_discount"},
        {"day": 3, "subject": "Bestseller die andere lieben", "template": "bestsellers"},
        {"day": 7, "subject": "Exklusiv für dich: Neue Arrivals", "template": "new_arrivals"},
    ],
    "post_purchase": [
        {"day": 1, "subject": "Deine Bestellung ist unterwegs!", "template": "shipping_update"},
        {"day": 7, "subject": "Wie gefällt dir dein Kauf?", "template": "review_request"},
        {"day": 14, "subject": "Passend dazu empfehlen wir...", "template": "upsell"},
    ],
    "win_back": [
        {"day": 0, "subject": "Wir vermissen dich — 20% Comeback-Rabatt", "template": "winback_1"},
        {"day": 7, "subject": "Letzte Chance: Dein Rabatt läuft ab", "template": "winback_final"},
    ],
    "vip": [
        {"day": 0, "subject": "Du bist jetzt VIP! Exklusive Vorteile warten", "template": "vip_welcome"},
        {"day": 30, "subject": "Dein monatlicher VIP-Report", "template": "vip_monthly"},
    ],
}

# ── Lazy env helpers ──────────────────────────────────────────────────────────

def _anthropic_key() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "")

def _mailchimp_key() -> str:
    return os.getenv("MAILCHIMP_API_KEY", "")

def _mailchimp_server() -> str:
    return os.getenv("MAILCHIMP_SERVER_PREFIX", "us1")

def _mailchimp_list_id() -> str:
    return os.getenv("MAILCHIMP_LIST_ID", "")

def _shopify_domain() -> str:
    return os.getenv("SHOPIFY_SHOP_DOMAIN", "")

def _shopify_token() -> str:
    return (
        os.getenv("SHOPIFY_ADMIN_API_TOKEN")
        or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    )

def _shopify_api_version() -> str:
    return os.getenv("SHOPIFY_API_VERSION", "2026-04")

def _telegram_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN_2") or os.getenv("TELEGRAM_BOT_TOKEN", "")

def _telegram_chat() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")

# ── aiohttp guard ─────────────────────────────────────────────────────────────

try:
    import aiohttp as _aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    _HAS_AIOHTTP = False


def _session(timeout: int = 20) -> "_aiohttp.ClientSession":
    return _aiohttp.ClientSession(timeout=_aiohttp.ClientTimeout(total=timeout))


# ── Supabase helper ───────────────────────────────────────────────────────────

def _supabase():
    from modules.supabase_client import get_client
    return get_client()


# ── Telegram notification ─────────────────────────────────────────────────────

async def _tg(msg: str) -> None:
    token = _telegram_token()
    chat  = _telegram_chat()
    if not token or not chat or not _HAS_AIOHTTP:
        return
    try:
        async with _session(8) as sess:
            await sess.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            )
    except Exception as exc:
        log.warning("Telegram send error: %s", exc)


# ── Customer Enrollment ───────────────────────────────────────────────────────

async def enroll_customer(
    email: str,
    name: str,
    sequence_type: str,
    metadata: Optional[Dict] = None,
) -> Dict:
    """
    Enroll a customer in an email sequence.
    If already enrolled in same sequence with status='active', skip duplicate.
    """
    if sequence_type not in SEQUENCES:
        return {"ok": False, "error": f"Unknown sequence type: {sequence_type}"}

    steps = SEQUENCES[sequence_type]
    if not steps:
        return {"ok": False, "error": "Sequence has no steps"}

    # Calculate next_email_at based on first step's day offset
    first_day_offset = steps[0]["day"]
    next_email_at = (
        datetime.now(timezone.utc) + timedelta(days=first_day_offset)
    ).isoformat()

    try:
        sb = _supabase()

        # Check for existing active enrollment
        existing = (
            sb.table("email_sequences")
            .select("id, status")
            .eq("customer_email", email)
            .eq("sequence_type", sequence_type)
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        if existing.data:
            return {
                "ok": True,
                "skipped": True,
                "reason": "Already enrolled in this sequence",
                "email": email,
                "sequence_type": sequence_type,
            }

        sb.table("email_sequences").insert({
            "customer_email": email,
            "customer_name": name,
            "sequence_type": sequence_type,
            "current_step": 0,
            "enrolled_at": datetime.now(timezone.utc).isoformat(),
            "next_email_at": next_email_at,
            "metadata": metadata or {},
            "status": "active",
        }).execute()

        log.info("Customer %s enrolled in %s sequence", email, sequence_type)
        return {
            "ok": True,
            "email": email,
            "sequence_type": sequence_type,
            "next_email_at": next_email_at,
        }

    except Exception as exc:
        log.error("enroll_customer error for %s: %s", email, exc)
        return {"ok": False, "error": str(exc)}


# ── Email Content Generation ──────────────────────────────────────────────────

async def generate_email_content(
    template: str,
    customer_name: str,
    metadata: Optional[Dict] = None,
) -> Dict:
    """
    Generate personalized email content via Claude AI.
    Falls back to static templates if AI is unavailable.
    """
    metadata = metadata or {}
    api_key  = _anthropic_key()

    # Template-specific context
    template_context: Dict[str, str] = {
        "welcome_discount": "a warm welcome and a 10% discount code (use code WELCOME10)",
        "bestsellers": "our current bestselling products and why customers love them",
        "new_arrivals": "exclusive new product arrivals available only to subscribers",
        "shipping_update": "confirmation that their order is being prepared and shipped",
        "review_request": "a friendly request to leave a product review with a direct link",
        "upsell": "complementary products that pair well with their recent purchase",
        "winback_1": "a win-back message with a 20% comeback discount code COMEBACK20",
        "winback_final": "final reminder that their 20% discount expires in 24 hours",
        "vip_welcome": "VIP membership welcome with exclusive benefits and early access",
        "vip_monthly": "monthly VIP report with stats, exclusive offers, and loyalty rewards",
    }

    context = template_context.get(template, f"a {template} email")

    prompt = (
        f"Write a professional German e-commerce email for {customer_name or 'customer'}. "
        f"The email should contain: {context}. "
        "Brand tone: friendly, professional, conversion-focused. "
        "Return ONLY valid JSON with these exact fields: "
        "{\"subject\": \"...\", \"html_body\": \"...\", \"text_body\": \"...\"}. "
        "The html_body must be a complete HTML email template (inline CSS, responsive). "
        "The text_body is a plain text fallback version. No markdown, just JSON."
    )

    if api_key and _HAS_AIOHTTP:
        try:
            content = await _generate_via_claude(prompt, api_key)
            if content:
                return content
        except Exception as exc:
            log.warning("Claude content generation failed, using fallback: %s", exc)

    # Static fallback
    return _static_fallback_content(template, customer_name, metadata)


async def _generate_via_claude(prompt: str, api_key: str) -> Optional[Dict]:
    payload = {
        "model": "claude-haiku-4-5",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
        "system": "You are an expert email marketer. Respond with valid JSON only, no markdown fences.",
    }
    async with _session(30) as sess:
        async with sess.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=payload,
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Anthropic HTTP {resp.status}")
            data = await resp.json()

    raw = data["content"][0]["text"].strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    parsed = json.loads(raw)
    return {
        "subject":   str(parsed.get("subject", "")),
        "html_body": str(parsed.get("html_body", "")),
        "text_body": str(parsed.get("text_body", "")),
    }


def _static_fallback_content(template: str, customer_name: str, metadata: Dict) -> Dict:
    """Static fallback email templates in German."""
    name  = customer_name or "Kunde"
    shop  = os.getenv("SHOPIFY_SHOP_DOMAIN", "unser Shop").replace(".myshopify.com", "")

    templates: Dict[str, Dict] = {
        "welcome_discount": {
            "subject": "Willkommen! Dein 10% Rabatt wartet auf dich",
            "text_body": f"Hallo {name},\n\nwillkommen bei {shop}! Als Dankeschön für deine Anmeldung erhältst du 10% Rabatt auf deine erste Bestellung.\n\nDein Code: WELCOME10\n\nViel Spaß beim Stöbern!\n",
        },
        "bestsellers": {
            "subject": "Diese Bestseller liebt jeder",
            "text_body": f"Hallo {name},\n\nentdecke unsere beliebtesten Produkte, die tausende Kunden begeistern!\n\nJetzt shoppen: https://{shop}.myshopify.com\n",
        },
        "new_arrivals": {
            "subject": "Exklusiv für dich: Neue Arrivals",
            "text_body": f"Hallo {name},\n\nals Abonnent bekommst du als Erster Zugang zu unseren neuesten Produkten!\n\nJetzt entdecken: https://{shop}.myshopify.com\n",
        },
        "shipping_update": {
            "subject": "Deine Bestellung ist unterwegs!",
            "text_body": f"Hallo {name},\n\ndeine Bestellung wird gerade vorbereitet und bald auf dem Weg zu dir sein. Wir halten dich auf dem Laufenden!\n",
        },
        "review_request": {
            "subject": "Wie gefällt dir dein Kauf?",
            "text_body": f"Hallo {name},\n\nwie zufrieden bist du mit deinem Kauf? Dein Feedback hilft uns und anderen Käufern. Bitte hinterlasse eine kurze Bewertung!\n",
        },
        "upsell": {
            "subject": "Passend dazu empfehlen wir...",
            "text_body": f"Hallo {name},\n\nbasierend auf deinem letzten Kauf haben wir einige perfekte Ergänzungen für dich!\n\nJetzt entdecken: https://{shop}.myshopify.com\n",
        },
        "winback_1": {
            "subject": "Wir vermissen dich — 20% Comeback-Rabatt",
            "text_body": f"Hallo {name},\n\nwir haben dich vermisst! Als Dankeschön für deine Treue schenken wir dir 20% Rabatt auf deinen nächsten Einkauf.\n\nDein Code: COMEBACK20\n\nGültig für 7 Tage!\n",
        },
        "winback_final": {
            "subject": "Letzte Chance: Dein 20% Rabatt läuft ab",
            "text_body": f"Hallo {name},\n\ndein persönlicher 20% Rabattcode COMEBACK20 läuft in 24 Stunden ab. Jetzt einlösen!\n\nZum Shop: https://{shop}.myshopify.com\n",
        },
        "vip_welcome": {
            "subject": "Du bist jetzt VIP! Exklusive Vorteile warten",
            "text_body": f"Hallo {name},\n\nherzlichen Glückwunsch! Du hast VIP-Status erreicht. Ab sofort genießt du exklusive Angebote, frühen Zugang zu neuen Produkten und priority Support.\n\nDein VIP-Team\n",
        },
        "vip_monthly": {
            "subject": "Dein monatlicher VIP-Report",
            "text_body": f"Hallo {name},\n\nhier ist dein persönlicher VIP-Report für diesen Monat mit exklusiven Angeboten und Neuigkeiten speziell für dich!\n",
        },
    }

    fallback = templates.get(template, {
        "subject": f"Nachricht von {shop}",
        "text_body": f"Hallo {name},\n\nvielen Dank für deine Treue!\n",
    })

    text_body = fallback["text_body"]
    subject   = fallback["subject"]

    html_body = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{subject}</title>
</head>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px;">
<div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
  <div style="background:#1a1a2e;padding:30px;text-align:center;">
    <h1 style="color:#ffffff;margin:0;font-size:24px;">{shop.upper()}</h1>
  </div>
  <div style="padding:30px;">
    <p style="font-size:16px;color:#333333;line-height:1.6;">{text_body.replace(chr(10), '<br>')}</p>
  </div>
  <div style="background:#f8f8f8;padding:20px;text-align:center;font-size:12px;color:#999999;">
    <p>Du erhältst diese E-Mail weil du dich für unseren Newsletter angemeldet hast.<br>
    <a href="{{{{unsubscribe_url}}}}" style="color:#999999;">Abmelden</a></p>
  </div>
</div>
</body>
</html>"""

    return {"subject": subject, "html_body": html_body, "text_body": text_body}


# ── Mailchimp Send ────────────────────────────────────────────────────────────

async def _send_via_mailchimp(
    email: str,
    subject: str,
    html_body: str,
    text_body: str,
    list_id: Optional[str] = None,
) -> bool:
    """
    Send a transactional email via Mailchimp Transactional (Mandrill) API.
    Falls back to Mailchimp campaigns if Mandrill key is unavailable.
    """
    mc_key = _mailchimp_key()
    if not mc_key or not _HAS_AIOHTTP:
        log.warning("Mailchimp not configured; email to %s not sent", email)
        return False

    # Try Mailchimp Transactional (Mandrill)
    mandrill_key = os.getenv("MANDRILL_API_KEY", mc_key)
    try:
        return await _mandrill_send(mandrill_key, email, subject, html_body, text_body)
    except Exception as exc:
        log.warning("Mandrill send failed: %s", exc)
        return False


async def _mandrill_send(
    api_key: str,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> bool:
    from_email = os.getenv("FROM_EMAIL", f"noreply@{_shopify_domain()}")
    from_name  = os.getenv("FROM_NAME", "SuperMegaBot")

    payload = {
        "key": api_key,
        "message": {
            "html": html_body,
            "text": text_body,
            "subject": subject,
            "from_email": from_email,
            "from_name": from_name,
            "to": [{"email": to_email, "type": "to"}],
            "auto_html": False,
            "auto_text": False,
        },
    }

    async with _session(20) as sess:
        async with sess.post(
            "https://mandrillapp.com/api/1.0/messages/send.json",
            json=payload,
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Mandrill HTTP {resp.status}")
            data = await resp.json()

    if isinstance(data, list) and data:
        status = data[0].get("status", "")
        if status in ("sent", "queued", "scheduled"):
            return True
        raise RuntimeError(f"Mandrill status: {status} — {data[0].get('reject_reason','')}")
    return False


# ── Due Email Processing ──────────────────────────────────────────────────────

async def process_due_emails() -> Dict:
    """
    Process all customers with emails due now:
    1. Fetch due enrollments from Supabase
    2. Generate personalized AI content
    3. Send via Mailchimp
    4. Advance sequence step or mark complete
    """
    now = datetime.now(timezone.utc)
    sent    = 0
    failed  = 0
    skipped = 0
    sequence_counts: Dict[str, int] = {}

    try:
        sb = _supabase()
        result = (
            sb.table("email_sequences")
            .select("*")
            .eq("status", "active")
            .lte("next_email_at", now.isoformat())
            .limit(100)
            .execute()
        )
        enrollments = result.data or []
    except Exception as exc:
        log.error("Failed to fetch due emails: %s", exc)
        return {"sent": 0, "failed": 0, "error": str(exc)}

    for enrollment in enrollments:
        seq_type     = enrollment.get("sequence_type", "")
        current_step = int(enrollment.get("current_step", 0))
        email        = enrollment.get("customer_email", "")
        name         = enrollment.get("customer_name", "")
        metadata     = enrollment.get("metadata") or {}
        enroll_id    = enrollment.get("id")

        if seq_type not in SEQUENCES:
            skipped += 1
            continue

        steps = SEQUENCES[seq_type]
        if current_step >= len(steps):
            # Sequence complete — mark done
            await _mark_sequence_done(enroll_id)
            skipped += 1
            continue

        step = steps[current_step]
        template_name = step.get("template", "")
        subject_base  = step.get("subject", "")

        try:
            # Generate personalized content
            content = await asyncio.wait_for(
                generate_email_content(template_name, name, metadata),
                timeout=20.0,
            )
            subject  = content.get("subject") or subject_base
            html_body = content.get("html_body", "")
            text_body = content.get("text_body", "")

            # Send email
            ok = await asyncio.wait_for(
                _send_via_mailchimp(email, subject, html_body, text_body),
                timeout=15.0,
            )

            if ok:
                sent += 1
                sequence_counts[seq_type] = sequence_counts.get(seq_type, 0) + 1

                # Log send
                await _log_email_send(
                    email, seq_type, current_step, subject, "sent"
                )

                # Advance to next step
                next_step = current_step + 1
                if next_step >= len(steps):
                    await _mark_sequence_done(enroll_id)
                else:
                    next_day_offset = steps[next_step]["day"] - step["day"]
                    next_at = (now + timedelta(days=max(next_day_offset, 1))).isoformat()
                    await _advance_sequence(enroll_id, next_step, next_at)
            else:
                failed += 1
                await _log_email_send(email, seq_type, current_step, subject, "failed")

        except asyncio.TimeoutError:
            log.warning("Timeout sending to %s (seq=%s step=%s)", email, seq_type, current_step)
            failed += 1
        except Exception as exc:
            log.error("Error sending to %s: %s", email, exc)
            failed += 1

    if sent > 0:
        await _tg(
            f"<b>Email Sequences — Cycle Done</b>\n"
            f"Sent: {sent} | Failed: {failed} | Skipped: {skipped}\n"
            + "\n".join(f"  {k}: {v}" for k, v in sequence_counts.items())
        )

    return {
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "sequences": sequence_counts,
    }


async def _mark_sequence_done(enrollment_id: int) -> None:
    try:
        _supabase().table("email_sequences").update({
            "status": "completed",
        }).eq("id", enrollment_id).execute()
    except Exception as exc:
        log.warning("Failed to mark sequence %s done: %s", enrollment_id, exc)


async def _advance_sequence(enrollment_id: int, next_step: int, next_at: str) -> None:
    try:
        _supabase().table("email_sequences").update({
            "current_step": next_step,
            "next_email_at": next_at,
        }).eq("id", enrollment_id).execute()
    except Exception as exc:
        log.warning("Failed to advance sequence %s: %s", enrollment_id, exc)


async def _log_email_send(
    email: str,
    seq_type: str,
    step: int,
    subject: str,
    status: str,
) -> None:
    try:
        _supabase().table("email_sends").insert({
            "customer_email": email,
            "sequence_type": seq_type,
            "step": step,
            "subject": subject,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
        }).execute()
    except Exception as exc:
        log.warning("email_sends insert failed: %s", exc)


# ── Stats ─────────────────────────────────────────────────────────────────────

async def get_sequence_stats() -> Dict:
    """Return open/send/completion stats per sequence type."""
    try:
        sb = _supabase()

        # Enrollment counts by sequence + status
        enroll_result = (
            sb.table("email_sequences")
            .select("sequence_type, status")
            .execute()
        )
        enrollments = enroll_result.data or []

        # Send counts by sequence
        sends_result = (
            sb.table("email_sends")
            .select("sequence_type, status")
            .execute()
        )
        sends = sends_result.data or []

        stats: Dict[str, Dict] = {}
        for seq_type in SEQUENCES:
            seq_enrolls = [e for e in enrollments if e.get("sequence_type") == seq_type]
            seq_sends   = [s for s in sends if s.get("sequence_type") == seq_type]
            stats[seq_type] = {
                "total_enrolled":   len(seq_enrolls),
                "active":           sum(1 for e in seq_enrolls if e.get("status") == "active"),
                "completed":        sum(1 for e in seq_enrolls if e.get("status") == "completed"),
                "total_emails_sent": sum(1 for s in seq_sends if s.get("status") == "sent"),
                "total_failed":     sum(1 for s in seq_sends if s.get("status") == "failed"),
            }

        return {"ok": True, "sequences": stats, "total_sends": len(sends)}

    except Exception as exc:
        log.error("get_sequence_stats error: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Auto-Enrollment: New Customers ───────────────────────────────────────────

async def auto_enroll_new_customers() -> Dict:
    """
    Fetch new Shopify customers from last 24h and enroll them in the welcome sequence.
    """
    domain  = _shopify_domain()
    token   = _shopify_token()
    version = _shopify_api_version()

    if not domain or not token:
        return {"ok": False, "error": "Shopify not configured"}
    if not _HAS_AIOHTTP:
        return {"ok": False, "error": "aiohttp not installed"}

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    base  = f"https://{domain}" if not domain.startswith("http") else domain
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }

    enrolled = 0
    skipped  = 0
    errors   = 0

    try:
        async with _session(20) as sess:
            async with sess.get(
                f"{base}/admin/api/{version}/customers.json"
                f"?created_at_min={since}&limit=50",
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    return {"ok": False, "error": f"Shopify HTTP {resp.status}"}
                data = await resp.json()

        customers = data.get("customers", [])
        for customer in customers:
            email      = customer.get("email", "")
            first_name = customer.get("first_name", "")
            last_name  = customer.get("last_name", "")
            name       = f"{first_name} {last_name}".strip() or email

            if not email:
                skipped += 1
                continue

            result = await enroll_customer(
                email=email,
                name=name,
                sequence_type="welcome",
                metadata={
                    "shopify_customer_id": str(customer.get("id", "")),
                    "currency": customer.get("currency", "EUR"),
                },
            )
            if result.get("ok") and not result.get("skipped"):
                enrolled += 1
            elif result.get("skipped"):
                skipped += 1
            else:
                errors += 1

        log.info("Auto-enroll new customers: %s enrolled, %s skipped", enrolled, skipped)
        return {
            "ok": True,
            "enrolled": enrolled,
            "skipped": skipped,
            "errors": errors,
            "total_customers": len(customers),
        }

    except Exception as exc:
        log.error("auto_enroll_new_customers error: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Auto-Enrollment: Post-Purchase ───────────────────────────────────────────

async def auto_enroll_post_purchase() -> Dict:
    """
    Fetch new Shopify orders from last 24h and enroll buyers in post_purchase sequence.
    """
    domain  = _shopify_domain()
    token   = _shopify_token()
    version = _shopify_api_version()

    if not domain or not token:
        return {"ok": False, "error": "Shopify not configured"}
    if not _HAS_AIOHTTP:
        return {"ok": False, "error": "aiohttp not installed"}

    since   = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    base    = f"https://{domain}" if not domain.startswith("http") else domain
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }

    enrolled = 0
    skipped  = 0
    errors   = 0

    try:
        async with _session(20) as sess:
            async with sess.get(
                f"{base}/admin/api/{version}/orders.json"
                f"?created_at_min={since}&status=any&limit=50",
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    return {"ok": False, "error": f"Shopify HTTP {resp.status}"}
                data = await resp.json()

        orders = data.get("orders", [])
        for order in orders:
            email = (
                order.get("email")
                or (order.get("customer") or {}).get("email", "")
            )
            if not email:
                skipped += 1
                continue

            customer   = order.get("customer") or {}
            first_name = customer.get("first_name", "")
            last_name  = customer.get("last_name", "")
            name       = f"{first_name} {last_name}".strip() or email

            result = await enroll_customer(
                email=email,
                name=name,
                sequence_type="post_purchase",
                metadata={
                    "order_id": str(order.get("id", "")),
                    "order_number": order.get("order_number"),
                    "total_price": order.get("total_price"),
                    "currency": order.get("currency", "EUR"),
                },
            )
            if result.get("ok") and not result.get("skipped"):
                enrolled += 1
            elif result.get("skipped"):
                skipped += 1
            else:
                errors += 1

        log.info("Auto-enroll post-purchase: %s enrolled, %s skipped", enrolled, skipped)
        return {
            "ok": True,
            "enrolled": enrolled,
            "skipped": skipped,
            "errors": errors,
            "total_orders": len(orders),
        }

    except Exception as exc:
        log.error("auto_enroll_post_purchase error: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── VIP Promotion ─────────────────────────────────────────────────────────────

async def promote_to_vip(min_orders: int = 3, min_revenue: float = 200.0) -> Dict:
    """
    Promote Shopify customers meeting order/revenue thresholds to VIP sequence.
    Uses Shopify customer data to evaluate eligibility.
    """
    domain  = _shopify_domain()
    token   = _shopify_token()
    version = _shopify_api_version()

    if not domain or not token:
        return {"ok": False, "error": "Shopify not configured"}
    if not _HAS_AIOHTTP:
        return {"ok": False, "error": "aiohttp not installed"}

    base    = f"https://{domain}" if not domain.startswith("http") else domain
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }

    promoted = 0
    skipped  = 0

    try:
        # Fetch customers sorted by total spent
        async with _session(20) as sess:
            async with sess.get(
                f"{base}/admin/api/{version}/customers.json"
                f"?limit=100&order=total_spent+desc",
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    return {"ok": False, "error": f"Shopify HTTP {resp.status}"}
                data = await resp.json()

        customers = data.get("customers", [])
        for customer in customers:
            orders_count  = int(customer.get("orders_count", 0))
            total_spent   = float(customer.get("total_spent", 0) or 0)
            email         = customer.get("email", "")

            if not email:
                skipped += 1
                continue

            if orders_count >= min_orders and total_spent >= min_revenue:
                first_name = customer.get("first_name", "")
                last_name  = customer.get("last_name", "")
                name       = f"{first_name} {last_name}".strip() or email

                result = await enroll_customer(
                    email=email,
                    name=name,
                    sequence_type="vip",
                    metadata={
                        "shopify_customer_id": str(customer.get("id", "")),
                        "orders_count": orders_count,
                        "total_spent": total_spent,
                    },
                )
                if result.get("ok") and not result.get("skipped"):
                    promoted += 1
                else:
                    skipped += 1
            else:
                skipped += 1

        if promoted > 0:
            await _tg(
                f"<b>VIP Promotion</b>\n"
                f"{promoted} customer(s) promoted to VIP "
                f"(min {min_orders} orders, min €{min_revenue:.0f} spent)"
            )

        log.info("VIP promotion: %s promoted, %s skipped", promoted, skipped)
        return {"ok": True, "promoted": promoted, "skipped": skipped}

    except Exception as exc:
        log.error("promote_to_vip error: %s", exc)
        return {"ok": False, "error": str(exc)}
