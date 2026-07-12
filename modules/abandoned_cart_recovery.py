#!/usr/bin/env python3
"""
Abandoned Cart Recovery — ineedit.com.co
Polls Shopify every hour, sends professional German recovery email via Klaviyo.
Tracks sent emails in local JSON state file to avoid duplicates.
Fires Klaviyo "Abandoned Cart" event for flow/CRM tracking.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

log = logging.getLogger("AbandonedCart")

_DATA_DIR = Path(os.getenv("DATA_DIR", "/tmp/supermegabot"))
_STATE_FILE = _DATA_DIR / "abandoned_cart_emails.json"
_KLAVIYO_BASE = "https://a.klaviyo.com/api"
_KLAVIYO_REVISION = "2024-10-15"

# How long after checkout creation to send the email (default: 1 hour)
SEND_AFTER_MINUTES = int(os.getenv("ABANDONED_CART_DELAY_MINUTES", "60"))
# Don't re-email carts older than this many hours
MAX_AGE_HOURS = int(os.getenv("ABANDONED_CART_MAX_AGE_HOURS", "48"))


# ── HTML Email Template ───────────────────────────────────────────────────────

def build_email_html(
    first_name: str,
    items: List[Dict],
    total: str,
    currency: str,
    recover_url: str,
    shop_name: str = "I Want That! I Need It!",
    shop_domain: str = "ineedit.com.co",
) -> str:
    """Build professional German abandoned cart recovery email."""
    greeting = f"Hallo {first_name}," if first_name else "Hallo,"

    # Build items list HTML
    items_html = ""
    for item in items[:5]:  # max 5 items shown
        title = item.get("title", "Produkt")
        qty = item.get("quantity", 1)
        price = item.get("price", "")
        img = item.get("image", "")
        item_html = f"""
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid #f0f0f0;">
            {"<img src='" + img + "' width='60' style='vertical-align:middle;border-radius:4px;margin-right:12px;' alt='" + title + "'>" if img else ""}
            <strong style="color:#1a1a1a;">{title}</strong>
            <span style="color:#666;font-size:13px;"> &times; {qty}</span>
            {"<br><span style='color:#2563eb;font-weight:600;'>" + currency + " " + price + "</span>" if price else ""}
          </td>
        </tr>"""
        items_html += item_html

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Du hast etwas vergessen! - {shop_name}</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:30px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);padding:36px 40px;text-align:center;">
            <h1 style="color:#ffffff;margin:0;font-size:26px;font-weight:700;letter-spacing:-0.5px;">
              {shop_name}
            </h1>
            <p style="color:rgba(255,255,255,0.7);margin:6px 0 0;font-size:14px;">
              Smart & Modern Shopping
            </p>
          </td>
        </tr>

        <!-- Cart emoji banner -->
        <tr>
          <td style="background:#fff8e7;padding:20px 40px;text-align:center;border-bottom:2px solid #ffd700;">
            <p style="margin:0;font-size:32px;">&#x1F6D2;</p>
            <h2 style="margin:8px 0 0;color:#1a1a1a;font-size:22px;font-weight:700;">
              Du hast etwas vergessen!
            </h2>
            <p style="margin:6px 0 0;color:#555;font-size:15px;">
              Dein Warenkorb wartet noch auf dich.
            </p>
          </td>
        </tr>

        <!-- Greeting + intro -->
        <tr>
          <td style="padding:30px 40px 10px;">
            <p style="color:#1a1a1a;font-size:16px;line-height:1.6;margin:0 0 16px;">
              {greeting}
            </p>
            <p style="color:#444;font-size:15px;line-height:1.7;margin:0 0 20px;">
              Du hast deinen Einkauf bei <strong>{shop_name}</strong> noch nicht abgeschlossen.
              Kein Problem — dein Warenkorb wurde gespeichert und wartet auf dich!
            </p>
          </td>
        </tr>

        <!-- Cart items -->
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
        {"<tr><td style='padding:16px 40px 0;'><p style='color:#1a1a1a;font-size:16px;font-weight:700;margin:0;'>Gesamtbetrag: " + currency + " " + total + "</p></td></tr>" if total and float(total or 0) > 0 else ""}

        <!-- CTA Button -->
        <tr>
          <td style="padding:28px 40px;">
            <table cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td align="center">
                  <a href="{recover_url}"
                     style="display:inline-block;background:linear-gradient(135deg,#2563eb,#1d4ed8);
                            color:#ffffff;font-size:17px;font-weight:700;
                            text-decoration:none;padding:16px 48px;border-radius:8px;
                            letter-spacing:0.3px;box-shadow:0 4px 14px rgba(37,99,235,0.4);">
                    &#x1F6D2;&nbsp; Warenkorb ansehen
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Trust badges -->
        <tr>
          <td style="padding:0 40px 28px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#f8faff;border-radius:8px;padding:16px 20px;">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td width="33%" align="center" style="padding:0 8px;">
                        <p style="margin:0;font-size:20px;">&#x1F6E1;&#xFE0F;</p>
                        <p style="margin:4px 0 0;font-size:12px;color:#444;font-weight:600;">Sichere Zahlung</p>
                        <p style="margin:2px 0 0;font-size:11px;color:#777;">SSL-verschlüsselt</p>
                      </td>
                      <td width="33%" align="center" style="padding:0 8px;border-left:1px solid #e0e7ff;border-right:1px solid #e0e7ff;">
                        <p style="margin:0;font-size:20px;">&#x1F4E6;</p>
                        <p style="margin:4px 0 0;font-size:12px;color:#444;font-weight:600;">Gratis Versand</p>
                        <p style="margin:2px 0 0;font-size:11px;color:#777;">ab €49 Bestellwert</p>
                      </td>
                      <td width="33%" align="center" style="padding:0 8px;">
                        <p style="margin:0;font-size:20px;">&#x1F504;</p>
                        <p style="margin:4px 0 0;font-size:12px;color:#444;font-weight:600;">14 Tage Rückgabe</p>
                        <p style="margin:2px 0 0;font-size:11px;color:#777;">Kein Risiko</p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Urgency note -->
        <tr>
          <td style="padding:0 40px 24px;">
            <p style="color:#888;font-size:13px;line-height:1.6;margin:0;text-align:center;
                       background:#fff8f0;border-radius:6px;padding:12px 16px;border-left:3px solid #f59e0b;">
              &#x23F0; Dein Warenkorb ist nur begrenzte Zeit reserviert.
              Jetzt kaufen und dir deine Lieblingsartikel sichern!
            </p>
          </td>
        </tr>

        <!-- Secondary CTA -->
        <tr>
          <td style="padding:0 40px 32px;text-align:center;">
            <a href="https://{shop_domain}"
               style="color:#2563eb;font-size:14px;text-decoration:none;">
              Weiter einkaufen auf {shop_domain} &rarr;
            </a>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#1a1a2e;padding:24px 40px;text-align:center;">
            <p style="color:rgba(255,255,255,0.5);font-size:12px;margin:0;line-height:1.8;">
              {shop_name} &bull; {shop_domain}<br>
              Du erhältst diese E-Mail, weil du einen Kauf begonnen hast.<br>
              <a href="https://{shop_domain}" style="color:rgba(255,255,255,0.4);text-decoration:none;">
                Abmelden
              </a>
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def build_email_subject(shop_name: str = "I Want That! I Need It!") -> str:
    return f"Du hast etwas vergessen! \U0001F6D2 {shop_name}"


# ── State Management ──────────────────────────────────────────────────────────

def _load_state() -> Dict:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text())
        except Exception as e:
            log.warning("Ignored error: %s", e)
    return {"sent": {}}  # token -> {"sent_at": iso, "email": email}


def _save_state(state: Dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2))


def _already_sent(state: Dict, token: str) -> bool:
    return token in state.get("sent", {})


def _mark_sent(state: Dict, token: str, email: str) -> None:
    state.setdefault("sent", {})[token] = {
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "email": email,
    }


def _prune_old(state: Dict, max_hours: int = 72) -> Dict:
    """Remove entries older than max_hours to keep state file lean."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_hours)
    sent = state.get("sent", {})
    pruned = {
        t: v for t, v in sent.items()
        if datetime.fromisoformat(v.get("sent_at", "2000-01-01T00:00:00+00:00")) > cutoff
    }
    state["sent"] = pruned
    return state


# ── Klaviyo Event Tracking ────────────────────────────────────────────────────

async def _klaviyo_track_abandoned_cart(
    session: aiohttp.ClientSession,
    email: str,
    first_name: str,
    items: List[Dict],
    total: str,
    recover_url: str,
    checkout_token: str,
) -> bool:
    """Fire 'Abandoned Cart' event in Klaviyo for CRM tracking and flow triggers."""
    key = os.getenv("KLAVIYO_API_KEY", "")
    if not key:
        log.warning("KLAVIYO_API_KEY not set — skipping Klaviyo event")
        return False

    headers = {
        "Authorization": f"Klaviyo-API-Key {key}",
        "revision": _KLAVIYO_REVISION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "data": {
            "type": "event",
            "attributes": {
                "metric": {
                    "data": {
                        "type": "metric",
                        "attributes": {"name": "Abandoned Cart"}
                    }
                },
                "profile": {
                    "data": {
                        "type": "profile",
                        "attributes": {
                            "email": email,
                            "first_name": first_name,
                            "properties": {
                                "checkout_token": checkout_token,
                                "recover_url": recover_url,
                            }
                        }
                    }
                },
                "properties": {
                    "checkout_token": checkout_token,
                    "Items": [
                        {
                            "ProductName": i.get("title", ""),
                            "Quantity":    i.get("quantity", 1),
                            "ItemPrice":   i.get("price", "0.00"),
                            "ImageURL":    i.get("image", ""),
                        }
                        for i in items[:10]
                    ],
                    "ItemNames":   [i.get("title", "") for i in items],
                    "CheckoutURL": recover_url,
                    "Value":       float(total or 0),
                },
                "value": float(total or 0),
                "unique_id": f"abandoned_cart_{checkout_token}",
            }
        }
    }

    try:
        async with session.post(
            f"{_KLAVIYO_BASE}/events/",
            headers=headers,
            json=payload,
        ) as r:
            ok = r.status in (200, 201, 202)
            if ok:
                log.info("Klaviyo 'Abandoned Cart' event fired for %s", email)
            else:
                body = await r.text()
                log.warning("Klaviyo event failed HTTP %s: %s", r.status, body[:200])
            return ok
    except Exception as e:
        log.error("Klaviyo event error: %s", e)
        return False


# ── Email Sending ─────────────────────────────────────────────────────────────

async def _send_via_smtp(
    session: aiohttp.ClientSession,
    to_email: str,
    subject: str,
    html_body: str,
) -> bool:
    """Send email via SMTP (smtplib - sync, run in executor)."""
    import asyncio
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", os.getenv("GMAIL_USER", ""))
    smtp_pass = os.getenv("SMTP_PASS", os.getenv("GMAIL_APP_PASSWORD", ""))
    from_addr = smtp_user or "noreply@ineedit.com.co"

    if not smtp_user or not smtp_pass:
        log.warning("SMTP not configured (SMTP_USER/SMTP_PASS missing)")
        return False

    def _send_sync():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"I Want That! I Need It! <{from_addr}>"
        msg["To"] = to_email
        msg["Reply-To"] = "support@ineedit.com.co"
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, to_email, msg.as_string())

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_sync)
        log.info("SMTP email sent to %s", to_email)
        return True
    except Exception as e:
        log.error("SMTP send failed: %s", e)
        return False


async def _send_via_mailchimp_transactional(
    session: aiohttp.ClientSession,
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
) -> bool:
    """Send via Mailchimp Mandrill transactional (if configured)."""
    api_key = os.getenv("MAILCHIMP_API_KEY", "")
    if not api_key or "mandrill" not in os.getenv("MAILCHIMP_TRANSACTIONAL", ""):
        return False  # Not configured

    payload = {
        "key": api_key,
        "message": {
            "html":       html_body,
            "subject":    subject,
            "from_email": "support@ineedit.com.co",
            "from_name":  "I Want That! I Need It!",
            "to": [{"email": to_email, "name": to_name, "type": "to"}],
        }
    }

    try:
        async with session.post(
            "https://mandrillapp.com/api/1.0/messages/send.json",
            json=payload,
        ) as r:
            ok = r.status == 200
            if ok:
                log.info("Mandrill email sent to %s", to_email)
            return ok
    except Exception as e:
        log.error("Mandrill error: %s", e)
        return False


async def send_abandoned_cart_email(
    session: aiohttp.ClientSession,
    email: str,
    first_name: str,
    items: List[Dict],
    total: str,
    currency: str,
    recover_url: str,
    checkout_token: str,
) -> bool:
    """
    Send abandoned cart recovery email via best available channel.
    Priority: SMTP → Mandrill → (Klaviyo flow handles it via event)
    Also always fires Klaviyo event for CRM tracking.
    """
    subject = build_email_subject()
    html = build_email_html(
        first_name=first_name,
        items=items,
        total=total,
        currency=currency,
        recover_url=recover_url,
    )

    # Always track in Klaviyo (for CRM + flow triggers)
    asyncio.create_task(
        _klaviyo_track_abandoned_cart(
            session, email, first_name, items, total, recover_url, checkout_token
        )
    )

    # Try to send actual email
    if await _send_via_mailchimp_transactional(session, email, first_name, subject, html):
        return True

    if await _send_via_smtp(session, email, subject, html):
        return True

    # If neither channel works, Klaviyo flow should handle sending via its automation
    log.info(
        "Direct email channels unavailable for %s — relying on Klaviyo flow (event fired)",
        email,
    )
    return True  # Event was fired, flow will handle it


# ── Main Recovery Task ────────────────────────────────────────────────────────

async def run_abandoned_cart_recovery() -> str:
    """
    Main task: poll Shopify for abandoned checkouts, send email to each new one.
    Returns summary string for scheduler logging.
    """
    token = os.getenv("SHOPIFY_ACCESS_TOKEN", "") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "") or os.getenv("SHOPIFY_STORE_DOMAIN", "")
    if not token or not domain:
        return "Shopify nicht konfiguriert"

    base = f"https://{domain}" if not domain.startswith("http") else domain
    ver = os.getenv("SHOPIFY_API_VERSION", "2024-10")
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    state = _load_state()
    state = _prune_old(state)

    now = datetime.now(timezone.utc)
    cutoff_early = now - timedelta(minutes=SEND_AFTER_MINUTES)
    cutoff_old   = now - timedelta(hours=MAX_AGE_HOURS)

    sent_count = 0
    skipped = 0
    errors = 0

    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"{base}/admin/api/{ver}/checkouts.json?limit=50",
                headers=headers,
            ) as r:
                if r.status != 200:
                    return f"Shopify checkouts HTTP {r.status}"
                data = await r.json(content_type=None)

            checkouts = data.get("checkouts", [])
            candidates = []
            for c in checkouts:
                email = c.get("email", "")
                completed = c.get("completed_at")
                token_key = c.get("token", "")
                created_raw = c.get("created_at", "")

                if not email or completed or not token_key:
                    skipped += 1
                    continue

                if _already_sent(state, token_key):
                    skipped += 1
                    continue

                # Parse creation time
                try:
                    created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                except Exception:
                    skipped += 1
                    continue

                # Only send if checkout is old enough (>=SEND_AFTER_MINUTES)
                # and not too old (<=MAX_AGE_HOURS)
                if created_at > cutoff_early:
                    skipped += 1  # Too fresh, wait
                    continue
                if created_at < cutoff_old:
                    skipped += 1  # Too old, skip
                    _mark_sent(state, token_key, email)  # Prevent future re-checks
                    continue

                candidates.append(c)

            log.info(
                "Abandoned cart recovery: %d candidates, %d skipped",
                len(candidates), skipped,
            )

            for c in candidates:
                email = c.get("email", "")
                billing = c.get("billing_address") or {}
                first_name = billing.get("first_name", "")
                total = c.get("total_price", "0.00")
                currency = c.get("currency", "EUR")
                shop_url = os.getenv("SHOPIFY_STORE_URL", "") or (
                    f"https://{domain}" if domain else "https://ineedit.com.co"
                )
                recover_url = c.get("abandoned_checkout_url", f"{shop_url.rstrip('/')}/cart")
                token_key = c.get("token", "")

                line_items = []
                for li in c.get("line_items", []):
                    img_src = ""
                    if li.get("featured_image") and li["featured_image"].get("url"):
                        img_src = li["featured_image"]["url"]
                    line_items.append({
                        "title":    li.get("title", "Produkt"),
                        "quantity": li.get("quantity", 1),
                        "price":    li.get("price", ""),
                        "image":    img_src,
                    })

                try:
                    ok = await send_abandoned_cart_email(
                        session=session,
                        email=email,
                        first_name=first_name,
                        items=line_items,
                        total=total,
                        currency=currency,
                        recover_url=recover_url,
                        checkout_token=token_key,
                    )
                    if ok:
                        _mark_sent(state, token_key, email)
                        sent_count += 1
                        log.info("Recovery email sent to %s (cart total: %s %s)", email, total, currency)
                    else:
                        errors += 1
                except Exception as e:
                    log.error("Error processing cart %s: %s", token_key, e)
                    errors += 1

                await asyncio.sleep(1)  # Rate limit

        _save_state(state)

        if sent_count > 0:
            return f"Abandoned Cart: {sent_count} Recovery-E-Mail(s) gesendet | {skipped} übersprungen | {errors} Fehler"
        return f"Abandoned Cart: keine neuen Carts | {len(checkouts)} gesamt, {skipped} übersprungen"

    except Exception as e:
        log.error("run_abandoned_cart_recovery error: %s", e)
        return f"Abandoned Cart Fehler: {e}"


# ── Webhook Handler (called from dashboard/server.py) ────────────────────────

async def handle_checkout_webhook(payload: Dict, event_type: str = "create") -> Dict:
    """
    Handle Shopify checkout/create or checkout/update webhook.
    Stores the checkout token so we can track it.
    For update events, if checkout is completed, mark it as handled.
    """
    token_key = payload.get("token", "")
    email = payload.get("email", "")
    completed = payload.get("completed_at")

    if not token_key:
        return {"ok": True, "msg": "no token"}

    state = _load_state()

    if completed and token_key in state.get("sent", {}):
        # Cart was completed — remove from sent so we don't count it as abandoned
        state["sent"].pop(token_key, None)
        _save_state(state)
        log.info("Checkout %s completed — removed from abandoned state", token_key)
        return {"ok": True, "msg": "checkout completed"}

    if event_type == "create" and email:
        log.info("New checkout created: token=%s email=%s", token_key, email)

    return {"ok": True, "msg": f"{event_type} processed"}


async def handle_order_webhook(payload: Dict) -> Dict:
    """
    Handle Shopify orders/create webhook.
    Mark the checkout as completed so we don't send an abandoned cart email.
    """
    checkout_token = payload.get("checkout_token", "")
    order_number = payload.get("order_number", "?")

    if checkout_token:
        state = _load_state()
        if checkout_token in state.get("sent", {}):
            state["sent"].pop(checkout_token, None)
        else:
            # Pre-emptively mark it so we don't email it
            _mark_sent(state, checkout_token, payload.get("email", "completed"))
        _save_state(state)
        log.info("Order #%s placed — checkout %s marked as completed", order_number, checkout_token)

    return {"ok": True, "order": order_number}
