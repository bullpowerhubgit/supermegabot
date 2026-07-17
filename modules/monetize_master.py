#!/usr/bin/env python3
"""
Monetize Master — Startet ALLE Revenue-Streams sofort parallel.
Orchestriert: Klaviyo-Campaigns, Email-Blast, Social-Posts, Affiliate-Blast,
              Shopify Cart-Recovery, DS24-Funnel, Stripe-Auto-Billing.
"""
from __future__ import annotations

import asyncio
import logging
import os
import json
from datetime import datetime, timezone
from typing import Any

import aiohttp

log = logging.getLogger("MonetizeMaster")

KLAVIYO_KEY  = os.getenv("KLAVIYO_API_KEY", "pk_VaCYq3_cf5a87a914f94f3f6ad6b12de8b8876722")
KLAVIYO_LIST = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
FROM_EMAIL   = os.getenv("FROM_EMAIL", "aiitecbuuss@gmail.com")
FROM_NAME    = os.getenv("FROM_NAME", "AiiteC Team")
SHOP_URL     = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
TG_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN_RUDICLONE", "")
TG_CHAT      = os.getenv("TELEGRAM_CHAT_ID", "")

# High-Ticket Produkte mit Payment-Links
HIGH_TICKET_PRODUCTS = [
    {"name": "BullPower Hub",         "starter": "https://buy.stripe.com/14AcN7cvM1zA6Aw8gK4F42uA", "price": "€997/mo"},
    {"name": "CreatorAI Ultra",       "starter": "https://buy.stripe.com/dRmfZj0N44LMbUQ9kO4F42uV", "price": "€297/mo"},
    {"name": "RudiBot AutoPilot",     "starter": "https://buy.stripe.com/7sYdRbcvM9221gccx04F42uI", "price": "€297/mo"},
    {"name": "AutoIncome AI",         "starter": "https://buy.stripe.com/8x228tgM27XY8IEfJc4F42uM", "price": "€997 einmalig"},
    {"name": "Shopify Suite Pro",     "starter": "https://buy.stripe.com/fZu14pfHYfqq3ok68C4F42uE", "price": "€397/mo"},
    {"name": "SuperMegaBot SaaS",     "starter": "https://buy.stripe.com/9B63cxanE4LMgb6fJc4F42Do", "price": "€49/mo"},
    {"name": "SteuercockPit Pro",     "starter": "https://buy.stripe.com/cNi4gBgM23HI1gcfJc4F42Dr", "price": "€497/mo"},
    {"name": "Monetization Hub",      "starter": "https://buy.stripe.com/8x2aEZ2Vc1zA1gceF84F42uR", "price": "€497/mo"},
    {"name": "CreatorStudio Pro",     "starter": "https://buy.stripe.com/fZu14p8fw7XY4so1Sm4F42uN", "price": "€197/mo"},
    {"name": "DS24 Pro Suite",        "starter": "https://buy.stripe.com/14A14p9jA0vwf7268C4F42ft", "price": "€497/mo"},
]

SOCIAL_CAPTION_TEMPLATES = [
    "🚀 {name} — Jetzt {price} starten!\n\nAutomatisiere dein Business mit KI. Link in Bio!\n\n#KIBusiness #Automatisierung #OnlineBusiness",
    "💰 Mit {name} verdienen während du schläfst!\n\nNur {price} · Sofort loslegen!\n\n#PassivesEinkommen #KI #DigitalBusiness",
    "⚡ {name}: Die schnellste Methode dein Business zu skalieren!\n\nAb {price} · Jetzt starten!\n\n#Skalierung #KITools #BusinessWachstum",
]


# ── Klaviyo Helpers ────────────────────────────────────────────────────────────

def _kv_headers() -> dict:
    return {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
        "revision": "2024-02-15",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _kv_post(session: aiohttp.ClientSession, path: str, data: dict) -> dict:
    url = f"https://a.klaviyo.com/api{path}"
    async with session.post(url, headers=_kv_headers(), json=data,
                            timeout=aiohttp.ClientTimeout(total=20)) as r:
        try:
            return await r.json(content_type=None)
        except Exception:
            return {"status": r.status}


async def _kv_get(session: aiohttp.ClientSession, path: str) -> dict:
    url = f"https://a.klaviyo.com/api{path}"
    async with session.get(url, headers=_kv_headers(),
                           timeout=aiohttp.ClientTimeout(total=15)) as r:
        try:
            return await r.json(content_type=None) if r.status < 400 else {}
        except Exception:
            return {}


# ── 1. Klaviyo High-Ticket Campaigns ──────────────────────────────────────────

async def _create_send_campaign(session: aiohttp.ClientSession,
                                subject: str, preview: str, html: str) -> dict:
    """3-Schritt Klaviyo Campaign: create → add-message → send-job."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Step 1: bare campaign
    r1 = await _kv_post(session, "/campaigns/", {"data": {"type": "campaign", "attributes": {
        "name": f"MM_{ts}_{subject[:30]}",
        "audiences": {"included": [KLAVIYO_LIST], "excluded": []},
        "send_strategy": {"method": "immediate"},
        "tracking_options": {"is_tracking_opens": True, "is_tracking_clicks": True},
    }}})
    cid = (r1.get("data") or {}).get("id")
    if not cid:
        return {"ok": False, "step": "campaign", "error": str(r1)[:200]}

    # Step 2: add message
    r2 = await _kv_post(session, "/campaign-messages/", {"data": {
        "type": "campaign-message",
        "attributes": {
            "channel": "email",
            "label": subject[:50],
            "content": {
                "subject": subject,
                "preview_text": preview,
                "from_email": FROM_EMAIL,
                "from_label": FROM_NAME,
                "body": html,
            },
        },
        "relationships": {"campaign": {"data": {"type": "campaign", "id": cid}}},
    }})

    # Step 3: send-job (fire even if message had issues — best effort)
    r3 = await _kv_post(session, "/campaign-send-jobs/", {"data": {
        "type": "campaign-send-job",
        "attributes": {},
        "relationships": {"campaign": {"data": {"type": "campaign", "id": cid}}},
    }})
    sent = "error" not in r3 and (r3.get("data") or {}).get("id") is not None

    return {"ok": True, "campaign_id": cid, "subject": subject, "sent": sent}


async def _track_klaviyo_events(products: list) -> int:
    """Klaviyo Event-Tracking → löst Flow-basierte E-Mails aus."""
    tracked = 0
    async with aiohttp.ClientSession() as session:
        for prod in products:
            try:
                resp = await _kv_post(session, "/events/", {"data": {"type": "event", "attributes": {
                    "metric": {"data": {"type": "metric", "attributes": {"name": "High Ticket Product View"}}},
                    "profile": {"data": {"type": "profile", "attributes": {
                        "email": FROM_EMAIL,
                        "properties": {"product": prod["name"], "price": prod["price"]},
                    }}},
                    "properties": {"product": prod["name"], "price": prod["price"],
                                   "link": prod["starter"], "source": "MonetizeMaster"},
                }}})
                if resp.get("errors") is None:
                    tracked += 1
                await asyncio.sleep(0.5)
            except Exception as exc:
                log.debug("event track: %s", exc)
    return tracked


async def run_klaviyo_campaigns() -> dict:
    """Klaviyo: Event-Tracking → Flow-E-Mails; kein direktes Campaign-API nötig."""
    tracked = await _track_klaviyo_events(HIGH_TICKET_PRODUCTS)
    log.info("Klaviyo events tracked: %d", tracked)

    # Sekundär: versuche masse-kampagne via bestehendem Modul
    campaign_result = {"created": 0, "campaigns": []}
    try:
        from modules.klaviyo_mass_campaigns import create_campaign_from_template, CAMPAIGN_TEMPLATES
        chosen = [t for t in CAMPAIGN_TEMPLATES if t.get("theme") == "flash_sale"][:2]
        for tmpl in chosen:
            res = await create_campaign_from_template(tmpl)
            if res.get("ok"):
                campaign_result["created"] += 1
                campaign_result["campaigns"].append({"subject": tmpl["subject"]})
    except Exception as exc:
        log.debug("mass campaign: %s", exc)

    return {
        "created":   campaign_result["created"],
        "campaigns": campaign_result["campaigns"],
        "events_tracked": tracked,
        "errors": [],
    }


async def run_klaviyo_campaigns_DISABLED_OLD() -> dict:
    """Erstellt und versendet 3 High-Ticket Kampagnen (korrekter 3-Schritt-Flow)."""
    campaigns_cfg = [
        {
            "subject": "🚀 KI-Business-Suite ab €297/mo — Komplett automatisiert",
            "preview": "Dein Business läuft 24/7 — ohne dich",
            "products": HIGH_TICKET_PRODUCTS[:3],
            "title": "KI-Business-Automation Suite",
            "body": (
                "Stell dir vor, dein Business läuft vollautomatisch — "
                "Shopify, Stripe, Telegram, Content, Ads — alles KI-gesteuert.<br><br>"
                "BullPower Hub, CreatorAI Ultra, RudiBot AutoPilot — "
                "drei mächtige Tools, ein Ziel: <b>Mehr Umsatz, weniger Arbeit.</b>"
            ),
        },
        {
            "subject": "💰 Passives Einkommen 2026: Die 3 besten Systeme",
            "preview": "Automatisiert · Skalierbar · Ab heute",
            "products": [p for p in HIGH_TICKET_PRODUCTS if p["name"] in
                         ("AutoIncome AI", "Monetization Hub", "DS24 Pro Suite")],
            "title": "Top 3 Passive Income Systeme 2026",
            "body": (
                "Kein aktiver Verkauf mehr. Unsere KI-Systeme arbeiten für dich — "
                "24 Stunden, 7 Tage die Woche.<br><br>"
                "<b>AutoIncome AI</b> (€997 einmalig), <b>Monetization Hub</b> (€497/mo) "
                "und <b>DS24 Pro Suite</b> (€497/mo) sind dein Fundament."
            ),
        },
        {
            "subject": "⚡ Shopify automatisieren — 10.000+ Produkte, 0 manuelle Arbeit",
            "preview": "ineedit.com.co läuft auf Autopilot — du auch?",
            "products": [p for p in HIGH_TICKET_PRODUCTS
                         if "Shopify" in p["name"] or "SteuercockPit" in p["name"]],
            "title": "Shopify Vollautomatisierung",
            "body": (
                "ineedit.com.co hat über 10.000 echte Produkte — vollautomatisch importiert, "
                "kategorisiert, SEO-optimiert.<br><br>"
                "Mit <b>Shopify Suite Pro</b> (€397/mo) baust du deinen eigenen "
                "automatischen Shop — ohne Programmierkenntnisse."
            ),
        },
    ]

    created, errors = [], []
    async with aiohttp.ClientSession() as session:
        for cfg in campaigns_cfg:
            try:
                html = _build_campaign_html(cfg["title"], cfg["body"], cfg["products"])
                res  = await _create_send_campaign(session, cfg["subject"], cfg["preview"], html)
                if res.get("ok"):
                    created.append(res)
                    log.info("Klaviyo: %s (%s)", res["campaign_id"], res["subject"][:40])
                else:
                    errors.append(f'{cfg["subject"][:40]}: {res.get("error","")}')
            except Exception as exc:
                errors.append(str(exc))
                log.warning("Kampagne Fehler: %s", exc)

    log.info("Klaviyo: %d Kampagnen erstellt, %d Fehler", len(created), len(errors))
    return {"created": len(created), "campaigns": created, "errors": errors}


def _build_campaign_html(title: str, body: str, products: list) -> str:
    rows = ""
    for p in products:
        rows += f"""
        <tr>
          <td style="padding:12px 16px;border-bottom:1px solid #222;">
            <b style="color:#fff">{p['name']}</b>
            <span style="color:#a78bfa;margin-left:8px">{p['price']}</span>
          </td>
          <td style="padding:12px 16px;border-bottom:1px solid #222;text-align:right">
            <a href="{p['starter']}" style="background:#7c3aed;color:#fff;padding:8px 18px;
               border-radius:6px;text-decoration:none;font-weight:700;font-size:13px">
              Jetzt starten →
            </a>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#070d1c;font-family:-apple-system,BlinkMacSystemFont,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:40px 20px">
<table width="600" cellpadding="0" cellspacing="0"
       style="background:#0f1729;border-radius:12px;overflow:hidden;border:1px solid #1e2d4a">
  <!-- Header -->
  <tr><td style="background:linear-gradient(135deg,#130a2e,#0a1628);padding:32px 40px">
    <h1 style="color:#fff;margin:0;font-size:24px;font-weight:800">{title}</h1>
    <p style="color:#7c3aed;margin:8px 0 0;font-size:14px">AiiteC · KI-Automation für dein Business</p>
  </td></tr>
  <!-- Body -->
  <tr><td style="padding:32px 40px">
    <p style="color:#94a3b8;font-size:15px;line-height:1.7;margin:0 0 24px">{body}</p>
    <!-- Products table -->
    <table width="100%" style="border:1px solid #1e2d4a;border-radius:8px;overflow:hidden">
      <thead><tr style="background:#182036">
        <th style="padding:10px 16px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">Produkt</th>
        <th style="padding:10px 16px;text-align:right;color:#64748b;font-size:11px;text-transform:uppercase">Aktion</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </td></tr>
  <!-- Footer -->
  <tr><td style="padding:24px 40px;background:#0a0e1a;border-top:1px solid #1e2d4a">
    <p style="color:#334155;font-size:12px;margin:0;text-align:center">
      AiiteC · Alle Produkte: <a href="{SHOP_URL}" style="color:#7c3aed">{SHOP_URL}</a><br>
      Du erhältst diese E-Mail weil du dich für AiiteC-Updates angemeldet hast.
    </p>
  </td></tr>
</table>
</td></tr>
</table>
</body></html>"""


# ── 2. Shopify Abandoned Cart Recovery ────────────────────────────────────────

async def run_cart_recovery() -> dict:
    try:
        from modules.abandoned_cart_emails import run_cart_recovery_cycle
        result = await run_cart_recovery_cycle()
        return {"ok": True, "result": result}
    except ImportError:
        pass
    try:
        from modules.shopify_cart_recovery import run_abandoned_cart_recovery
        return await run_abandoned_cart_recovery()
    except Exception as exc:
        log.warning("Cart recovery: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── 3. DS24 Affiliate Blast ────────────────────────────────────────────────────

async def run_ds24_blast() -> dict:
    try:
        from modules.ds24_affiliate_blaster import blast_all_approved
        return await blast_all_approved()
    except Exception as exc:
        log.warning("DS24 blast: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── 4. Social Auto-Post ────────────────────────────────────────────────────────

async def run_social_posts() -> dict:
    posted = []
    errors = []
    try:
        from modules.mega_auto_poster import run_full_auto_post
        result = await run_full_auto_post()
        posted = result.get("posted", result.get("channels_posted", []))
    except Exception as exc:
        errors.append(f"social: {exc}")
        log.warning("Social post: %s", exc)

    # Telegram broadcast
    if TG_TOKEN and TG_CHAT:
        try:
            import aiohttp as _aiohttp
            for prod in HIGH_TICKET_PRODUCTS[:3]:
                msg = (
                    f"🚀 *{prod['name']}* — {prod['price']}\n\n"
                    f"Starte jetzt: {prod['starter']}\n\n_AiiteC KI-Suite_"
                )
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                async with _aiohttp.ClientSession() as s:
                    await s.post(url, json={
                        "chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown",
                        "disable_web_page_preview": False,
                    })
                await asyncio.sleep(4)
            posted.append("telegram_broadcast")
        except Exception as exc:
            errors.append(f"telegram: {exc}")

    return {"ok": True, "posted": posted, "errors": errors}


# ── 5. Email Revenue Blast ─────────────────────────────────────────────────────

async def run_email_blast() -> dict:
    try:
        from modules.email_revenue_engine import lead_email_blaster
        return await lead_email_blaster(max_per_run=50)
    except Exception as exc:
        log.warning("Email blast: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── 6. Affiliate Mega Engine ───────────────────────────────────────────────────

async def run_affiliate_mega() -> dict:
    results = []
    try:
        from modules.affiliate_mega_engine import (
            blast_amazon_affiliates, blast_ds24_affiliates
        )
        r1 = await blast_amazon_affiliates(count=3)
        r2 = await blast_ds24_affiliates(count=2)
        results = [r1, r2]
        return {"ok": True, "results": results}
    except Exception as exc:
        log.warning("Affiliate mega: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── 7. Stripe Revenue Check ────────────────────────────────────────────────────

async def run_stripe_billing() -> dict:
    try:
        from modules.stripe_revenue_activator import get_revenue_24h
        return await get_revenue_24h()
    except Exception as exc:
        log.warning("Stripe billing: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── 8. Shopify SEO Auto ────────────────────────────────────────────────────────

async def run_shopify_seo() -> dict:
    try:
        from modules.mega_seo_engine import run_mega_seo_cycle
        return await run_mega_seo_cycle()
    except Exception as exc:
        log.warning("Shopify SEO: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Master Orchestrator ────────────────────────────────────────────────────────

async def run_monetize_master() -> dict:
    """Startet alle Revenue-Streams parallel."""
    log.info("MonetizeMaster gestartet — alle Streams aktiviert")
    start = datetime.now(timezone.utc)

    results = await asyncio.gather(
        run_klaviyo_campaigns(),
        run_cart_recovery(),
        run_ds24_blast(),
        run_social_posts(),
        run_email_blast(),
        run_affiliate_mega(),
        run_stripe_billing(),
        run_shopify_seo(),
        return_exceptions=True,
    )

    labels = ["klaviyo", "cart_recovery", "ds24_blast", "social",
              "email_blast", "affiliate", "stripe_billing", "shopify_seo"]

    summary = {}
    for label, res in zip(labels, results):
        if isinstance(res, Exception):
            summary[label] = {"ok": False, "error": str(res)}
        else:
            summary[label] = res if isinstance(res, dict) else {"ok": True, "result": str(res)}

    duration = (datetime.now(timezone.utc) - start).total_seconds()
    log.info("MonetizeMaster fertig in %.1fs: %s", duration, list(summary.keys()))

    return {
        "ok":      True,
        "streams": len(labels),
        "duration_s": round(duration, 1),
        "summary": summary,
    }


# ── Sync Entry Point ───────────────────────────────────────────────────────────

def run_all():
    return asyncio.run(run_monetize_master())


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(name)s %(message)s")
    result = run_all()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
