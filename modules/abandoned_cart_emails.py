"""
abandoned_cart_emails.py — Abandoned Cart Email Recovery Module
SuperMegaBot | Shopify Webhook Integration
3-step email recovery sequence with SQLite state tracking.
"""

import asyncio
import json
import logging
import os
import smtplib
import sqlite3
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data")) / "abandoned_carts.db"

STEP_DELAYS = {
    1: 1 * 3600,       # 1 hour
    2: 24 * 3600,      # 24 hours
    3: 72 * 3600,      # 72 hours
}
STEP3_MIN_EUR = 30.0   # only send step-3 if cart value > €30


# ---------------------------------------------------------------------------
# Database bootstrap
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _bootstrap_db() -> None:
    conn = _get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS carts (
                shopify_checkout_id TEXT PRIMARY KEY,
                email               TEXT NOT NULL,
                customer_name       TEXT,
                total_eur           REAL,
                items_json          TEXT,
                abandon_url         TEXT,
                status              TEXT DEFAULT 'new',
                created_at          REAL,
                emails_sent         INT  DEFAULT 0,
                recovered_at        REAL,
                unsubscribed        INT  DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS cart_emails (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                checkout_id     TEXT    NOT NULL,
                sequence_step   INT     NOT NULL,
                sent_at         REAL    NOT NULL,
                opened          INT     DEFAULT 0,
                clicked         INT     DEFAULT 0,
                recovered       INT     DEFAULT 0,
                FOREIGN KEY (checkout_id) REFERENCES carts (shopify_checkout_id)
            );
            """
        )
        conn.commit()
        # Migrate existing databases that pre-date the unsubscribed column
        try:
            conn.execute("ALTER TABLE carts ADD COLUMN unsubscribed INT DEFAULT 0")
            conn.commit()
            logger.debug("abandoned_cart_emails: migrated carts table — added unsubscribed column")
        except sqlite3.OperationalError:
            pass  # Column already exists
        logger.debug("abandoned_cart_emails: DB schema ready at %s", DB_PATH)
    finally:
        conn.close()


# Initialise on import
_bootstrap_db()


# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------

def _render_step1(name: str, items_summary: str, abandon_url: str, to_email: str = "") -> tuple[str, str, str]:
    subject = "Du hast etwas vergessen 🛒"
    html = f"""
<html><body style="font-family:Arial,sans-serif;color:#222;max-width:600px;margin:0 auto">
  <h2 style="color:#1a1a2e">Hallo {name},</h2>
  <p>Du hattest folgende Artikel in deinem Warenkorb:</p>
  <p style="background:#f5f5f5;padding:12px;border-radius:6px;font-weight:bold">{items_summary}</p>
  <p>Dein Warenkorb ist noch für dich gespeichert — du kannst genau dort weitermachen, wo du aufgehört hast.</p>
  <p style="text-align:center;margin:32px 0">
    <a href="{abandon_url}"
       style="background:#e63946;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-size:16px">
      Warenkorb öffnen →
    </a>
  </p>
  <p style="color:#888;font-size:12px">
    Du erhältst diese E-Mail, weil du einen Kauf begonnen, aber nicht abgeschlossen hast.
  </p>
  <p style="color:#aaa;font-size:11px">
    Keine weiteren Erinnerungen? <a href="https://ineedit.com.co/cart-unsub?email={to_email}" style="color:#aaa">Hier abmelden</a>.
  </p>
</body></html>
"""
    plain = (
        f"Hallo {name},\n\n"
        f"Du hattest folgende Artikel in deinem Warenkorb:\n{items_summary}\n\n"
        f"Klicke hier, um deinen Kauf abzuschließen:\n{abandon_url}\n\n"
        f"Keine weiteren Erinnerungen? Hier abmelden: https://ineedit.com.co/cart-unsub?email={to_email}\n"
    )
    return subject, html, plain


def _render_step2(name: str, items_summary: str, abandon_url: str, to_email: str = "") -> tuple[str, str, str]:
    subject = "Noch 24h: dein Warenkorb wartet"
    html = f"""
<html><body style="font-family:Arial,sans-serif;color:#222;max-width:600px;margin:0 auto">
  <h2 style="color:#1a1a2e">Hallo {name},</h2>
  <p>Wir wollten kurz nachfragen — dein Warenkorb wartet noch auf dich:</p>
  <p style="background:#f5f5f5;padding:12px;border-radius:6px;font-weight:bold">{items_summary}</p>
  <p>
    Tausende zufriedene Kunden vertrauen uns täglich. Unsere Produkte stehen für Qualität,
    schnellen Versand und echten Mehrwert.
  </p>
  <p>Sichere dir jetzt deine Bestellung — bevor der Bestand ausgeht.</p>
  <p style="text-align:center;margin:32px 0">
    <a href="{abandon_url}"
       style="background:#e63946;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-size:16px">
      Jetzt bestellen →
    </a>
  </p>
  <p style="color:#888;font-size:12px">
    Du erhältst diese E-Mail, weil du einen Kauf begonnen, aber nicht abgeschlossen hast.
  </p>
  <p style="color:#aaa;font-size:11px">
    Keine weiteren Erinnerungen? <a href="https://ineedit.com.co/cart-unsub?email={to_email}" style="color:#aaa">Hier abmelden</a>.
  </p>
</body></html>
"""
    plain = (
        f"Hallo {name},\n\n"
        f"Dein Warenkorb wartet noch:\n{items_summary}\n\n"
        f"Tausende zufriedene Kunden vertrauen uns. Schließe jetzt ab:\n{abandon_url}\n\n"
        f"Keine weiteren Erinnerungen? Hier abmelden: https://ineedit.com.co/cart-unsub?email={to_email}\n"
    )
    return subject, html, plain


def _render_step3(name: str, items_summary: str, abandon_url: str, to_email: str = "") -> tuple[str, str, str]:
    subject = "Letzte Chance + 5€ Rabatt: CART5"
    html = f"""
<html><body style="font-family:Arial,sans-serif;color:#222;max-width:600px;margin:0 auto">
  <h2 style="color:#1a1a2e">Hallo {name},</h2>
  <p>Das ist deine letzte Erinnerung — danach löschen wir deinen Warenkorb.</p>
  <p style="background:#f5f5f5;padding:12px;border-radius:6px;font-weight:bold">{items_summary}</p>
  <p>
    Als kleines Dankeschön schenken wir dir <strong>5€ Rabatt</strong> auf deine Bestellung.
    Gib einfach beim Checkout folgenden Code ein:
  </p>
  <p style="text-align:center;margin:20px 0">
    <span style="font-size:24px;font-weight:bold;letter-spacing:4px;
                 background:#fff3cd;padding:10px 20px;border-radius:6px;border:2px dashed #e63946">
      CART5
    </span>
  </p>
  <p style="color:#e63946;font-weight:bold">⚡ Nur heute gültig — danach verfällt der Code.</p>
  <p style="text-align:center;margin:32px 0">
    <a href="{abandon_url}"
       style="background:#e63946;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-size:16px">
      5€ Rabatt sichern →
    </a>
  </p>
  <p style="color:#888;font-size:12px">
    Gutscheincode CART5 gibt 5€ Rabatt auf den Gesamtbetrag (Mindestbestellwert: 30€).
    Du erhältst diese E-Mail, weil du einen Kauf begonnen, aber nicht abgeschlossen hast.
  </p>
  <p style="color:#aaa;font-size:11px">
    Keine weiteren Erinnerungen? <a href="https://ineedit.com.co/cart-unsub?email={to_email}" style="color:#aaa">Hier abmelden</a>.
  </p>
</body></html>
"""
    plain = (
        f"Hallo {name},\n\n"
        f"Letzte Erinnerung an deinen Warenkorb:\n{items_summary}\n\n"
        f"Verwende Gutscheincode CART5 für 5€ Rabatt beim Checkout.\n"
        f"Jetzt abschließen: {abandon_url}\n\n"
        f"Keine weiteren Erinnerungen? Hier abmelden: https://ineedit.com.co/cart-unsub?email={to_email}\n"
    )
    return subject, html, plain


STEP_RENDERERS = {
    1: _render_step1,
    2: _render_step2,
    3: _render_step3,
}


# ---------------------------------------------------------------------------
# SMTP helper
# ---------------------------------------------------------------------------

def _send_email_sync(
    to_addr: str,
    subject: str,
    html_body: str,
    plain_body: str,
    smtp_config: Optional[dict],
) -> bool:
    host = (smtp_config or {}).get("host") or os.getenv("SMTP_HOST", "")
    port = int((smtp_config or {}).get("port") or os.getenv("SMTP_PORT", "587"))
    user = (smtp_config or {}).get("user") or os.getenv("SMTP_USER", "")
    password = (smtp_config or {}).get("password") or os.getenv("SMTP_PASS", "")
    from_name = os.getenv("SMTP_FROM_NAME", "ineedit.com.co")

    if not all([host, user, password]):
        logger.warning("abandoned_cart_emails: SMTP not configured — skipping send to %s", to_addr)
        return False

    try:
        from modules.email_guard import validate_email
        ok, errors = validate_email(subject=subject, body=html_body, to_email=to_addr, skip_dedup=True)
        if not ok:
            logger.warning("abandoned_cart_emails: EmailGuard BLOCKED to=%s reason=%s", to_addr, "; ".join(errors))
            return False
    except ImportError:
        pass

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{user}>"
    msg["To"] = to_addr
    msg["List-Unsubscribe"] = (
        f"<https://ineedit.com.co/cart-unsub?email={to_addr}>,"
        f" <mailto:unsub@ineedit.com.co?subject=unsub>"
    )
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.login(user, password)
            server.sendmail(user, to_addr, msg.as_string())
        logger.info("abandoned_cart_emails: sent to %s (subj: %s)", to_addr, subject)
        return True
    except Exception as exc:
        logger.error("abandoned_cart_emails: SMTP error sending to %s — %s", to_addr, exc)
        return False


# ---------------------------------------------------------------------------
# Helper: parse Shopify checkout payload
# ---------------------------------------------------------------------------

def _parse_checkout(checkout_data: dict) -> Optional[dict]:
    checkout_id = str(checkout_data.get("id", "")).strip()
    email = (checkout_data.get("email") or "").strip().lower()
    if not checkout_id or not email:
        return None

    customer = checkout_data.get("customer") or {}
    first = (customer.get("first_name") or checkout_data.get("billing_address", {}).get("first_name") or "").strip()
    last = (customer.get("last_name") or checkout_data.get("billing_address", {}).get("last_name") or "").strip()
    customer_name = f"{first} {last}".strip() or email.split("@")[0]

    try:
        total_eur = float(checkout_data.get("total_price") or 0.0)
    except (TypeError, ValueError):
        total_eur = 0.0

    line_items = checkout_data.get("line_items") or []
    items_list = []
    for item in line_items:
        title = item.get("title") or item.get("name") or "Artikel"
        qty = item.get("quantity") or 1
        price = item.get("price") or "0.00"
        items_list.append({"title": title, "quantity": qty, "price": price})

    abandon_url = (checkout_data.get("abandoned_checkout_url") or "").strip()
    created_at_str = checkout_data.get("created_at") or ""

    try:
        from datetime import datetime, timezone
        created_at = datetime.fromisoformat(
            created_at_str.replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        created_at = time.time()

    return {
        "checkout_id": checkout_id,
        "email": email,
        "customer_name": customer_name,
        "total_eur": total_eur,
        "items_json": json.dumps(items_list, ensure_ascii=False),
        "abandon_url": abandon_url,
        "created_at": created_at,
    }


def _items_summary(items_json: str) -> str:
    try:
        items = json.loads(items_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return "Deine Artikel"
    parts = []
    for it in items:
        qty = it.get("quantity", 1)
        title = it.get("title", "Artikel")
        price = it.get("price", "")
        price_str = f" — €{price}" if price else ""
        parts.append(f"{qty}× {title}{price_str}")
    return "\n".join(parts) if parts else "Deine Artikel"


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------

async def register_cart(checkout_data: dict) -> bool:
    """
    Called from the Shopify webhook handler.
    Parses checkout payload and upserts into the carts table.
    Returns True if a new cart was registered (email present, new checkout_id).
    """
    parsed = await asyncio.get_event_loop().run_in_executor(
        None, _parse_checkout, checkout_data
    )
    if not parsed:
        logger.debug("abandoned_cart_emails: register_cart skipped — no email or id in payload")
        return False

    def _upsert():
        conn = _get_conn()
        try:
            existing = conn.execute(
                "SELECT shopify_checkout_id, status FROM carts WHERE shopify_checkout_id = ?",
                (parsed["checkout_id"],),
            ).fetchone()

            if existing:
                # Update abandon_url / total if checkout-update fires
                conn.execute(
                    """UPDATE carts SET total_eur=?, items_json=?, abandon_url=?, customer_name=?
                       WHERE shopify_checkout_id=? AND status='new'""",
                    (
                        parsed["total_eur"],
                        parsed["items_json"],
                        parsed["abandon_url"],
                        parsed["customer_name"],
                        parsed["checkout_id"],
                    ),
                )
                conn.commit()
                logger.debug("abandoned_cart_emails: updated existing cart %s", parsed["checkout_id"])
                return False  # not new

            conn.execute(
                """INSERT INTO carts
                   (shopify_checkout_id, email, customer_name, total_eur, items_json,
                    abandon_url, status, created_at, emails_sent, recovered_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'new', ?, 0, NULL)""",
                (
                    parsed["checkout_id"],
                    parsed["email"],
                    parsed["customer_name"],
                    parsed["total_eur"],
                    parsed["items_json"],
                    parsed["abandon_url"],
                    parsed["created_at"],
                ),
            )
            conn.commit()
            logger.info(
                "abandoned_cart_emails: registered new cart %s for %s (€%.2f)",
                parsed["checkout_id"],
                parsed["email"],
                parsed["total_eur"],
            )
            return True
        finally:
            conn.close()

    return await asyncio.get_event_loop().run_in_executor(None, _upsert)


async def cancel_cart_recovery(checkout_id: str) -> bool:
    """
    Called when an order is placed / paid.
    Marks the cart as 'recovered' so no further emails are sent.
    Returns True if the cart was found and updated.
    """
    def _mark():
        conn = _get_conn()
        try:
            cursor = conn.execute(
                "UPDATE carts SET status='recovered', recovered_at=? WHERE shopify_checkout_id=?",
                (time.time(), checkout_id),
            )
            conn.commit()
            found = cursor.rowcount > 0
            if found:
                logger.info("abandoned_cart_emails: cart %s marked as recovered", checkout_id)
            return found
        finally:
            conn.close()

    return await asyncio.get_event_loop().run_in_executor(None, _mark)


async def mark_unsubscribed(email: str) -> bool:
    """
    Called from the /cart-unsub backend route.
    Sets unsubscribed=1 for all carts belonging to this email address so no
    further recovery emails are dispatched for this contact.
    Returns True if at least one row was updated.
    """
    email = email.strip().lower()
    if not email:
        return False

    def _mark():
        conn = _get_conn()
        try:
            cursor = conn.execute(
                "UPDATE carts SET unsubscribed = 1 WHERE email = ?",
                (email,),
            )
            conn.commit()
            found = cursor.rowcount > 0
            if found:
                logger.info("abandoned_cart_emails: unsubscribed %s from cart-recovery emails", email)
            return found
        finally:
            conn.close()

    return await asyncio.get_event_loop().run_in_executor(None, _mark)


async def send_due_cart_emails(smtp_config: Optional[dict] = None) -> dict:
    """
    Checks all active carts, sends the next due email in the 3-step sequence.
    Timing:
      Step 1 — 1 h after abandon
      Step 2 — 24 h after abandon
      Step 3 — 72 h after abandon (only if total_eur > STEP3_MIN_EUR)
    Returns {sent: int, recovered: int, skipped: int}
    """
    now = time.time()
    sent_count = 0
    recovered_count = 0
    skipped_count = 0

    def _fetch_candidates():
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM carts WHERE status='new' AND emails_sent < 3 AND COALESCE(unsubscribed, 0) = 0"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _already_sent(checkout_id: str, step: int) -> bool:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT id FROM cart_emails WHERE checkout_id=? AND sequence_step=?",
                (checkout_id, step),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def _record_sent(checkout_id: str, step: int):
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO cart_emails (checkout_id, sequence_step, sent_at) VALUES (?,?,?)",
                (checkout_id, step, now),
            )
            conn.execute(
                "UPDATE carts SET emails_sent = emails_sent + 1 WHERE shopify_checkout_id=?",
                (checkout_id,),
            )
            conn.commit()
        finally:
            conn.close()

    candidates = await asyncio.get_event_loop().run_in_executor(None, _fetch_candidates)
    logger.info("abandoned_cart_emails: %d active carts to evaluate", len(candidates))

    for cart in candidates:
        checkout_id = cart["shopify_checkout_id"]
        try:
            created_at = cart["created_at"] or now
            elapsed = now - created_at
            total_eur = cart["total_eur"] or 0.0
            cart_email = cart["email"]
            customer_name = cart["customer_name"] or cart_email.split("@")[0]
            items_summary = _items_summary(cart["items_json"])
            abandon_url = cart["abandon_url"] or ""

            # Determine which step to send next
            next_step = None
            for step in [1, 2, 3]:
                delay = STEP_DELAYS[step]
                if elapsed < delay:
                    break  # too early for this step and all later ones
                already = await asyncio.get_event_loop().run_in_executor(
                    None, _already_sent, checkout_id, step
                )
                if not already:
                    if step == 3 and total_eur <= STEP3_MIN_EUR:
                        logger.debug(
                            "abandoned_cart_emails: skip step-3 for %s (€%.2f <= €%.2f)",
                            checkout_id, total_eur, STEP3_MIN_EUR,
                        )
                        skipped_count += 1
                        # Artificially mark step-3 as sent so we don't re-evaluate forever
                        await asyncio.get_event_loop().run_in_executor(
                            None, _record_sent, checkout_id, step
                        )
                        break
                    next_step = step
                    break

            if next_step is None:
                continue

            renderer = STEP_RENDERERS[next_step]
            subject, html_body, plain_body = renderer(customer_name, items_summary, abandon_url, cart_email)

            ok = await asyncio.get_event_loop().run_in_executor(
                None,
                _send_email_sync,
                cart_email,
                subject,
                html_body,
                plain_body,
                smtp_config,
            )

            if ok:
                await asyncio.get_event_loop().run_in_executor(
                    None, _record_sent, checkout_id, next_step
                )
                sent_count += 1
            else:
                skipped_count += 1

        except Exception as err:
            logger.error(
                "abandoned_cart_emails: skipping cart %s due to error: %s", checkout_id, err
            )
            skipped_count += 1
            continue

    logger.info(
        "abandoned_cart_emails: cycle done — sent=%d recovered=%d skipped=%d",
        sent_count, recovered_count, skipped_count,
    )
    return {"sent": sent_count, "recovered": recovered_count, "skipped": skipped_count}


async def run_cart_recovery_cycle() -> str:
    """
    Convenience wrapper: runs one full send cycle and returns a human-readable summary.
    """
    from modules.distributed_lock import acquire_lock
    async with acquire_lock("cart_recovery_cycle", ttl=20 * 60) as locked:
        if not locked:
            return "Cart-Recovery läuft bereits in anderem Terminal — übersprungen."
        result = await send_due_cart_emails()
    return (
        f"Cart-Recovery-Zyklus abgeschlossen: "
        f"{result['sent']} E-Mails gesendet, "
        f"{result['recovered']} wiedergewonnen, "
        f"{result['skipped']} übersprungen."
    )


async def get_cart_stats() -> dict:
    """
    Returns aggregated statistics about abandoned cart recovery.
    """
    def _query():
        conn = _get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM carts").fetchone()[0]
            recovered = conn.execute(
                "SELECT COUNT(*) FROM carts WHERE status='recovered'"
            ).fetchone()[0]
            revenue_row = conn.execute(
                "SELECT COALESCE(SUM(total_eur), 0) FROM carts WHERE status='recovered'"
            ).fetchone()
            revenue = float(revenue_row[0]) if revenue_row else 0.0

            day_start = time.time() - 86400
            emails_today = conn.execute(
                "SELECT COUNT(*) FROM cart_emails WHERE sent_at >= ?", (day_start,)
            ).fetchone()[0]

            rate = round((recovered / total * 100), 2) if total > 0 else 0.0
            return {
                "total_carts": total,
                "recovered": recovered,
                "recovery_rate_pct": rate,
                "revenue_recovered_eur": round(revenue, 2),
                "emails_sent_today": emails_today,
            }
        finally:
            conn.close()

    return await asyncio.get_event_loop().run_in_executor(None, _query)


# ---------------------------------------------------------------------------
# Standalone test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s — %(message)s")

    async def _demo():
        # Simulate a checkout payload
        fake_checkout = {
            "id": "test_checkout_001",
            "email": "test@example.com",
            "customer": {"first_name": "Max", "last_name": "Muster"},
            "total_price": "49.90",
            "line_items": [
                {"title": "Smart LED-Lampe", "quantity": 2, "price": "19.95"},
            ],
            "abandoned_checkout_url": "https://ineedit.com.co/cart/recover?token=abc123",
            "created_at": "2026-07-13T10:00:00Z",
        }

        registered = await register_cart(fake_checkout)
        print(f"Registered: {registered}")

        stats = await get_cart_stats()
        print(f"Stats: {stats}")

        summary = await run_cart_recovery_cycle()
        print(f"Cycle: {summary}")

    asyncio.run(_demo())
