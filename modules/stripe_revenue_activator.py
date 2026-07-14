"""
stripe_revenue_activator.py — Stripe Revenue Engine
====================================================
Activates all Stripe payment links, manages subscription checkout sessions,
tracks 24h revenue, and ensures webhooks are configured.

Auto-runs on import: creates payment links if fewer than 3 are stored locally.
Routes:
  GET  /api/stripe/revenue           — 24h revenue summary
  POST /api/stripe/activate-all      — trigger full payment-link creation
"""

import asyncio
import base64
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote as urlquote

import aiohttp
from aiohttp import web

log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_API_BASE   = "https://api.stripe.com/v1"
WEBHOOK_URL       = "https://supermegabot-production.up.railway.app/api/stripe/webhook"
THANK_YOU_BASE    = os.getenv("STRIPE_THANK_YOU_URL", "https://ineedit.com.co/pages/danke")

DB_PATH = Path(__file__).parent.parent / "data" / "stripe_links.db"

# SaaS tier definitions (used by create_subscription_checkout)
SAAS_TIERS = [
    {"name": "SuperMegaBot Starter", "amount": 4900,  "interval": "month", "trial_days": 7},
    {"name": "SuperMegaBot Pro",     "amount": 9900,  "interval": "month", "trial_days": 7},
    {"name": "SuperMegaBot Enterprise", "amount": 29900, "interval": "month", "trial_days": 7},
]

WEBHOOK_EVENTS = [
    "payment_intent.succeeded",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "checkout.session.completed",
]


# ── Database ────────────────────────────────────────────────────────────────────

def _db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _db_init():
    with _db_connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS payment_links (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                price_id     TEXT NOT NULL UNIQUE,
                product_name TEXT NOT NULL,
                amount_eur   INTEGER NOT NULL,
                currency     TEXT NOT NULL DEFAULT 'eur',
                billing_type TEXT NOT NULL DEFAULT 'one_time',
                link_id      TEXT NOT NULL,
                link_url     TEXT NOT NULL,
                created_at   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkout_sessions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tier_name    TEXT NOT NULL,
                amount_eur   INTEGER NOT NULL,
                session_id   TEXT,
                session_url  TEXT,
                created_at   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS revenue_snapshots (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                period       TEXT NOT NULL,
                total_eur    INTEGER NOT NULL,
                count        INTEGER NOT NULL,
                successful   INTEGER NOT NULL,
                failed       INTEGER NOT NULL,
                recorded_at  TEXT NOT NULL
            );
        """)


# ── Stripe HTTP helpers ─────────────────────────────────────────────────────────

def _auth_header() -> dict:
    token = base64.b64encode(f"{STRIPE_SECRET_KEY}:".encode()).decode()
    return {"Authorization": f"Basic {token}"}


async def _get(session: aiohttp.ClientSession, path: str, params: dict = None) -> dict:
    async with session.get(
        f"{STRIPE_API_BASE}{path}",
        params=params,
        headers=_auth_header(),
    ) as resp:
        body = await resp.json()
        if resp.status >= 400:
            log.warning("Stripe GET %s → %d: %s", path, resp.status, body.get("error", {}).get("message"))
        return body


async def _post(session: aiohttp.ClientSession, path: str, data: dict) -> dict:
    async with session.post(
        f"{STRIPE_API_BASE}{path}",
        data=data,
        headers=_auth_header(),
    ) as resp:
        body = await resp.json()
        if resp.status >= 400:
            log.warning("Stripe POST %s → %d: %s", path, resp.status, body.get("error", {}).get("message"))
        return body


async def _paginate_all(session: aiohttp.ClientSession, path: str, params: dict = None) -> list:
    """Collect all items from a paginated Stripe list endpoint."""
    items = []
    p = dict(params or {})
    p.setdefault("limit", "100")
    while True:
        result = await _get(session, path, p)
        page = result.get("data", [])
        items.extend(page)
        if not result.get("has_more"):
            break
        p["starting_after"] = page[-1]["id"]
    return items


# ── Core functions ──────────────────────────────────────────────────────────────

async def create_all_payment_links() -> list:
    """
    Create a Stripe Payment Link for every active price that isn't already stored.

    Returns list of {product_name, price_id, amount_eur, link_url} for newly created links.
    """
    if not STRIPE_SECRET_KEY:
        log.error("STRIPE_SECRET_KEY not set — cannot create payment links")
        return []

    _db_init()

    # Load price_ids we already have stored
    with _db_connect() as conn:
        stored = {row["price_id"] for row in conn.execute("SELECT price_id FROM payment_links")}
        existing_link_count = conn.execute("SELECT COUNT(*) FROM payment_links").fetchone()[0]

    log.info("stripe_revenue_activator: %d links already stored in DB", existing_link_count)

    created = []
    skipped = 0
    errors  = 0

    async with aiohttp.ClientSession() as session:
        # Fetch all active prices with expanded product info
        prices = await _paginate_all(session, "/prices", {
            "active": "true",
            "expand[]": "data.product",
        })

        log.info("stripe_revenue_activator: %d active prices found", len(prices))

        for price in prices:
            pid = price["id"]
            if pid in stored:
                skipped += 1
                continue

            product = price.get("product", {})
            if not isinstance(product, dict) or not product.get("active"):
                skipped += 1
                continue

            product_name = product.get("name", "Produkt")
            amount       = price.get("unit_amount", 0) or 0
            currency     = price.get("currency", "eur")
            recurring    = price.get("recurring") or {}
            billing_type = recurring.get("interval", "one_time") if recurring else "one_time"

            safe_name    = urlquote(product_name, safe="")[:120]
            redirect_url = f"{THANK_YOU_BASE}?product={safe_name}"

            payload = {
                "line_items[0][price]":            pid,
                "line_items[0][quantity]":         "1",
                "after_completion[type]":          "redirect",
                "after_completion[redirect][url]": redirect_url,
                "allow_promotion_codes":           "true",
                "billing_address_collection":      "auto",
            }

            resp = await _post(session, "/payment_links", payload)

            if resp.get("id"):
                entry = {
                    "product_name": product_name,
                    "price_id":     pid,
                    "amount_eur":   amount // 100,
                    "billing_type": billing_type,
                    "link_id":      resp["id"],
                    "link_url":     resp.get("url", ""),
                }
                created.append(entry)
                now = datetime.now(timezone.utc).isoformat()
                with _db_connect() as conn:
                    conn.execute(
                        """INSERT OR REPLACE INTO payment_links
                           (price_id, product_name, amount_eur, currency, billing_type,
                            link_id, link_url, created_at)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (pid, product_name, amount // 100, currency,
                         billing_type, resp["id"], resp.get("url", ""), now),
                    )
                log.info("Created payment link for '%s': %s", product_name, resp.get("url"))
            else:
                errors += 1
                err_msg = resp.get("error", {}).get("message", "unknown")
                log.warning("Failed to create link for price %s (%s): %s", pid, product_name, err_msg)

    log.info(
        "create_all_payment_links: %d created, %d skipped, %d errors",
        len(created), skipped, errors,
    )
    return created


async def create_subscription_checkout() -> list:
    """
    Create Stripe Checkout Sessions for SuperMegaBot SaaS tiers
    (Starter €49/mo, Pro €99/mo, Enterprise €299/mo) with 7-day free trial.

    Returns list of {tier_name, amount_eur, session_url}.
    """
    if not STRIPE_SECRET_KEY:
        log.error("STRIPE_SECRET_KEY not set")
        return []

    _db_init()
    results = []

    async with aiohttp.ClientSession() as session:
        # Get or create a product+price for each tier
        all_products = await _paginate_all(session, "/products", {"active": "true"})
        product_map  = {p["name"]: p["id"] for p in all_products}

        all_prices = await _paginate_all(session, "/prices", {
            "active": "true",
            "type":   "recurring",
        })

        for tier in SAAS_TIERS:
            tier_name   = tier["name"]
            amount      = tier["amount"]       # in cents
            interval    = tier["interval"]
            trial_days  = tier["trial_days"]

            # Find existing price for this tier (matching product name + amount + interval)
            price_id = None
            prod_id  = product_map.get(tier_name)

            if prod_id:
                for p in all_prices:
                    if (p.get("product") == prod_id
                            and p.get("unit_amount") == amount
                            and p.get("recurring", {}).get("interval") == interval):
                        price_id = p["id"]
                        break

            # Create product+price if not found
            if not price_id:
                if not prod_id:
                    prod_resp = await _post(session, "/products", {
                        "name":        tier_name,
                        "description": f"SuperMegaBot SaaS — {tier_name} Plan",
                        "metadata[tier]": tier_name.lower().split()[-1],
                    })
                    if prod_resp.get("id"):
                        prod_id = prod_resp["id"]
                        log.info("Created Stripe product: %s (%s)", tier_name, prod_id)
                    else:
                        log.error("Failed to create product %s: %s", tier_name, prod_resp)
                        continue

                price_resp = await _post(session, "/prices", {
                    "product":                   prod_id,
                    "unit_amount":               str(amount),
                    "currency":                  "eur",
                    "recurring[interval]":       interval,
                    "recurring[interval_count]": "1",
                    "metadata[tier]":            tier_name.lower().split()[-1],
                })
                if price_resp.get("id"):
                    price_id = price_resp["id"]
                    log.info("Created Stripe price: %s — €%d/%s", tier_name, amount // 100, interval)
                else:
                    log.error("Failed to create price for %s: %s", tier_name, price_resp)
                    continue

            # Create Checkout Session with trial
            success_url = f"{THANK_YOU_BASE}?tier={tier_name.lower().split()[-1]}&session_id={{CHECKOUT_SESSION_ID}}"
            cancel_url  = "https://supermegabot-production.up.railway.app/pricing"

            sess_resp = await _post(session, "/checkout/sessions", {
                "mode":                                "subscription",
                "line_items[0][price]":                price_id,
                "line_items[0][quantity]":             "1",
                "subscription_data[trial_period_days]": str(trial_days),
                "success_url":                         success_url,
                "cancel_url":                          cancel_url,
                "allow_promotion_codes":               "true",
                "billing_address_collection":          "auto",
            })

            if sess_resp.get("id"):
                entry = {
                    "tier_name":   tier_name,
                    "amount_eur":  amount // 100,
                    "session_id":  sess_resp["id"],
                    "session_url": sess_resp.get("url", ""),
                }
                results.append(entry)
                now = datetime.now(timezone.utc).isoformat()
                with _db_connect() as conn:
                    conn.execute(
                        """INSERT INTO checkout_sessions
                           (tier_name, amount_eur, session_id, session_url, created_at)
                           VALUES (?,?,?,?,?)""",
                        (tier_name, amount // 100, sess_resp["id"], sess_resp.get("url", ""), now),
                    )
                log.info("Created checkout session for %s: %s", tier_name, sess_resp.get("url", ""))
            else:
                err = sess_resp.get("error", {}).get("message", "unknown")
                log.error("Failed to create session for %s: %s", tier_name, err)

    return results


async def get_revenue_24h() -> dict:
    """
    Fetch all Stripe charges from the last 24 hours.

    Returns {count, total_eur, successful, failed, charges_list}.
    """
    if not STRIPE_SECRET_KEY:
        return {"ok": False, "error": "STRIPE_SECRET_KEY not set"}

    since = int(time.time()) - 86400  # 24 hours ago

    async with aiohttp.ClientSession() as session:
        charges = await _paginate_all(session, "/charges", {
            "created[gte]": str(since),
            "limit":        "100",
        })

    total_cents  = 0
    successful   = 0
    failed       = 0
    charge_list  = []

    for ch in charges:
        is_paid  = ch.get("paid", False)
        status   = ch.get("status", "")
        amount   = ch.get("amount", 0) or 0
        currency = ch.get("currency", "eur")

        if status == "succeeded" and is_paid:
            successful  += 1
            total_cents += amount
        else:
            failed += 1

        charge_list.append({
            "id":         ch.get("id"),
            "amount_eur": amount / 100,
            "currency":   currency,
            "status":     status,
            "paid":       is_paid,
            "created":    datetime.fromtimestamp(ch.get("created", 0), tz=timezone.utc).isoformat(),
            "description": ch.get("description") or ch.get("statement_descriptor") or "",
        })

    result = {
        "ok":           True,
        "period":       "last_24h",
        "since":        datetime.fromtimestamp(since, tz=timezone.utc).isoformat(),
        "count":        len(charges),
        "total_eur":    round(total_cents / 100, 2),
        "successful":   successful,
        "failed":       failed,
        "charges":      charge_list[:50],  # cap response size
    }

    # Persist snapshot
    _db_init()
    now = datetime.now(timezone.utc).isoformat()
    with _db_connect() as conn:
        conn.execute(
            """INSERT INTO revenue_snapshots
               (period, total_eur, count, successful, failed, recorded_at)
               VALUES (?,?,?,?,?,?)""",
            ("last_24h", total_cents // 100, len(charges), successful, failed, now),
        )

    log.info("get_revenue_24h: €%.2f from %d charges (%d ok, %d failed)",
             total_cents / 100, len(charges), successful, failed)
    return result


async def setup_stripe_webhooks() -> dict:
    """
    Ensure the supermegabot webhook endpoint exists in Stripe.
    Creates it if missing. Returns {ok, action, webhook_id}.
    """
    if not STRIPE_SECRET_KEY:
        return {"ok": False, "error": "STRIPE_SECRET_KEY not set"}

    async with aiohttp.ClientSession() as session:
        endpoints = await _paginate_all(session, "/webhook_endpoints")

        # Check if our canonical URL already exists
        for ep in endpoints:
            if ep.get("url") == WEBHOOK_URL and ep.get("status") == "enabled":
                log.info("Webhook already configured: %s (%s)", WEBHOOK_URL, ep["id"])
                return {"ok": True, "action": "already_exists", "webhook_id": ep["id"], "url": WEBHOOK_URL}

        # Create the webhook
        payload: dict = {"url": WEBHOOK_URL}
        for i, ev in enumerate(WEBHOOK_EVENTS):
            payload[f"enabled_events[{i}]"] = ev

        resp = await _post(session, "/webhook_endpoints", payload)

        if resp.get("id"):
            wh_secret = resp.get("secret", "")
            log.info("Created Stripe webhook: %s (%s)", WEBHOOK_URL, resp["id"])
            if wh_secret:
                log.info("Webhook signing secret (store as STRIPE_WEBHOOK_SECRET): %s", wh_secret)
            return {
                "ok":          True,
                "action":      "created",
                "webhook_id":  resp["id"],
                "url":         WEBHOOK_URL,
                "secret":      wh_secret,
                "events":      WEBHOOK_EVENTS,
            }
        else:
            err = resp.get("error", {}).get("message", "unknown")
            log.error("Failed to create webhook: %s", err)
            return {"ok": False, "action": "failed", "error": err}


async def get_stored_links() -> list:
    """Return all payment links stored in the local SQLite DB."""
    _db_init()
    with _db_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM payment_links ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


async def activate_all() -> dict:
    """
    Master activation: create links, setup webhook, return summary.
    Called by POST /api/stripe/activate-all.
    """
    log.info("stripe_revenue_activator: full activation started")
    new_links  = await create_all_payment_links()
    webhook    = await setup_stripe_webhooks()
    sessions   = await create_subscription_checkout()
    revenue    = await get_revenue_24h()
    stored     = await get_stored_links()

    return {
        "ok":              True,
        "new_links":       len(new_links),
        "total_stored":    len(stored),
        "webhook":         webhook,
        "saas_sessions":   sessions,
        "revenue_24h":     revenue,
        "links_sample":    new_links[:10],
    }


# ── Bootstrap on import ─────────────────────────────────────────────────────────

async def _bootstrap_if_needed():
    """Create payment links if we have fewer than 3 stored."""
    try:
        _db_init()
        with _db_connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM payment_links").fetchone()[0]

        if count < 3:
            log.info("stripe_revenue_activator: only %d links stored — bootstrapping", count)
            created = await create_all_payment_links()
            await setup_stripe_webhooks()
            log.info("stripe_revenue_activator: bootstrap complete — %d new links", len(created))
        else:
            log.debug("stripe_revenue_activator: %d links already stored — skipping bootstrap", count)
    except Exception as exc:
        log.exception("stripe_revenue_activator bootstrap error: %s", exc)


def _run_bootstrap_in_thread():
    """Run the async bootstrap in its own thread+event loop (safe at import time)."""
    def _worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_bootstrap_if_needed())
        except Exception as exc:
            log.warning("stripe_revenue_activator thread bootstrap: %s", exc)
        finally:
            loop.close()

    t = threading.Thread(target=_worker, name="stripe-bootstrap", daemon=True)
    t.start()


# ── Route handlers ──────────────────────────────────────────────────────────────

async def handle_revenue_24h(req: web.Request) -> web.Response:
    """GET /api/stripe/revenue — last-24h revenue stats."""
    try:
        data = await get_revenue_24h()
        return web.json_response(data)
    except Exception as exc:
        log.exception("handle_revenue_24h")
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def handle_activate_all(req: web.Request) -> web.Response:
    """POST /api/stripe/activate-all — trigger full payment-link creation + webhook setup."""
    try:
        result = await activate_all()
        return web.json_response(result)
    except Exception as exc:
        log.exception("handle_activate_all")
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def handle_stored_links(req: web.Request) -> web.Response:
    """GET /api/stripe/links — list payment links from local DB."""
    try:
        links = await get_stored_links()
        return web.json_response({"ok": True, "count": len(links), "links": links})
    except Exception as exc:
        log.exception("handle_stored_links")
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


def register_routes(app: web.Application):
    """Register all routes on the aiohttp app. Call from dashboard/server.py."""
    app.router.add_get("/api/stripe/revenue-24h", handle_revenue_24h)
    app.router.add_get("/api/stripe/links",       handle_stored_links)
    app.router.add_post("/api/stripe/activate-all", handle_activate_all)
    log.info("stripe_revenue_activator routes registered")


def get_status() -> dict:
    """Quick sync status for health checks."""
    try:
        _db_init()
        with _db_connect() as conn:
            link_count = conn.execute("SELECT COUNT(*) FROM payment_links").fetchone()[0]
            sess_count = conn.execute("SELECT COUNT(*) FROM checkout_sessions").fetchone()[0]
            snap       = conn.execute(
                "SELECT total_eur, recorded_at FROM revenue_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return {
            "module":         "stripe_revenue_activator",
            "stripe_key_set": bool(STRIPE_SECRET_KEY),
            "links_stored":   link_count,
            "sessions_stored": sess_count,
            "last_revenue_eur": snap["total_eur"] if snap else 0,
            "last_snapshot":    snap["recorded_at"] if snap else None,
        }
    except Exception as exc:
        return {"module": "stripe_revenue_activator", "error": str(exc)}


# ── Auto-activate on import ─────────────────────────────────────────────────────
# Runs in a background daemon thread so it never blocks the importing module.
if STRIPE_SECRET_KEY:
    _run_bootstrap_in_thread()
else:
    log.warning("stripe_revenue_activator: STRIPE_SECRET_KEY not set — skipping auto-bootstrap")
