#!/usr/bin/env python3
"""
BrutusClone Integrator — Universal Blast-System
================================================
Integriert BrutusCore.fire() in JEDEN Modul.
Zentrale Koordination aller Broadcast-Kanäle:
telegram, shopify_blog, linkedin, mailchimp, klaviyo,
indexnow, discord, slack, twitter, pinterest

Nutzt BrutusClone (modules/rudiclone.py) für KI-Content-Optimierung.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("BrutusCloneIntegrator")

SHOP_URL     = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
TELEGRAM_ID  = os.getenv("TELEGRAM_CHAT_ID", "")


async def _fire(title: str, content: str, link: str = "",
                channels: Optional[list] = None) -> dict:
    """Wrapper um brutus_core.fire() mit Fehlertoleranz."""
    if channels is None:
        channels = ["telegram", "shopify_blog", "linkedin",
                    "mailchimp", "klaviyo", "indexnow", "discord", "slack"]
    try:
        from modules.brutus_core import fire
        result = await fire(title, content, link=link or SHOP_URL, channels=channels)
        return result if isinstance(result, dict) else {"ok": True, "channels": channels}
    except ImportError:
        log.warning("brutus_core not available, using fallback")
        return await _fallback_fire(title, content, channels)
    except Exception as e:
        log.warning("BrutusCore fire error: %s", e)
        return {"ok": False, "error": str(e)}


async def _fallback_fire(title: str, content: str, channels: list) -> dict:
    """Fallback: direkt via Telegram wenn BrutusCore nicht verfügbar."""
    sent = []
    if "telegram" in channels and TELEGRAM_ID:
        try:
            from modules.telegram_notifier import send_message
            await send_message(f"🔥 *{title}*\n\n{content}")
            sent.append("telegram")
        except Exception:
            pass
    return {"ok": bool(sent), "sent": sent, "fallback": True}


async def _ai_enhance(title: str, content: str, platform: str) -> tuple[str, str]:
    """KI optimiert Titel/Content für jeweilige Plattform."""
    try:
        from modules.ai_client import ai_complete
        prompt = f"""Optimiere diesen Content für {platform}:
Titel: {title}
Content: {content[:200]}

Gib zurück als JSON: {{"title": "...", "content": "..."}}
Max 3 Sätze, {platform}-typische Sprache, 1-2 relevante Emojis."""
        raw = await ai_complete(prompt, max_tokens=150)
        import json
        s, e = raw.find("{"), raw.rfind("}") + 1
        if s != -1:
            data = json.loads(raw[s:e])
            return data.get("title", title), data.get("content", content)
    except Exception:
        pass
    return title, content


# ─── Produkt-Blast ────────────────────────────────────────────────────────────

async def blast_new_product(product: dict, channels: Optional[list] = None) -> dict:
    """Blast ein neues Produkt auf alle Kanäle."""
    title    = product.get("title", "Neues Produkt")
    price    = product.get("price", "")
    url      = product.get("url", SHOP_URL)
    handle   = product.get("handle", "")
    niche    = product.get("niche", "")
    tags     = product.get("tags", "")

    if channels is None:
        channels = ["telegram", "shopify_blog", "linkedin", "mailchimp",
                    "klaviyo", "indexnow", "discord", "slack"]

    price_str = f"€{price}" if price else ""
    content   = (f"🛍️ {title}\n"
                 f"{price_str}\n"
                 f"Kategorie: {niche or 'Allgemein'}\n"
                 f"Tags: {tags}\n\n"
                 f"Jetzt bestellen: {url}")

    result = await _fire(title, content, link=url, channels=channels)
    log.info("Blast new product: %s → channels=%s", title[:40], channels)
    return result


async def blast_ds24_product(product: dict) -> dict:
    """Blast ein DS24-Produkt: Telegram + LinkedIn + Discord."""
    title   = product.get("title", "Neues Digitales Produkt")
    price   = product.get("price", "")
    aff_url = product.get("affiliate_url", SHOP_URL)
    desc    = product.get("description", "")[:100]

    content = (f"💰 *{title}*\n"
               f"Preis: €{price}\n"
               f"{desc}\n\n"
               f"👉 Affiliate-Link: {aff_url}")

    return await _fire(title, content, link=aff_url,
                       channels=["telegram", "linkedin", "discord", "slack"])


async def blast_klaviyo_campaign(campaign: dict) -> dict:
    """Bestätigungs-Blast nach Klaviyo-Kampagne."""
    name    = campaign.get("name", "Klaviyo Kampagne")
    cid     = campaign.get("campaign_id", "")
    subject = campaign.get("subject", "")
    content = f"📧 Klaviyo-Kampagne gesendet!\n🔖 '{name}'\n📩 Subject: {subject}\nID: {cid}"
    return await _fire(f"📧 {name}", content, channels=["telegram", "slack"])


async def blast_mailchimp_campaign(campaign: dict) -> dict:
    """Bestätigungs-Blast nach Mailchimp-Kampagne."""
    title   = campaign.get("title", "Mailchimp Kampagne")
    cid     = campaign.get("campaign_id", "")
    subject = campaign.get("subject", "")
    content = f"📬 Mailchimp-Kampagne gesendet!\n📧 '{title}'\n📩 Subject: {subject}\nID: {cid}"
    return await _fire(f"📬 {title}", content, channels=["telegram", "slack"])


async def blast_revenue_milestone(milestone: dict) -> dict:
    """Blast bei Umsatz-Meilenstein."""
    amount   = milestone.get("amount", 0)
    currency = milestone.get("currency", "EUR")
    source   = milestone.get("source", "all")
    msg      = milestone.get("message", f"🎯 €{amount} {currency} Umsatz von {source}!")
    content  = (f"💰 *Umsatz-Meilenstein erreicht!*\n"
                f"€{amount:,.2f} {currency}\n"
                f"Quelle: {source}\n\n{msg}")
    return await _fire(f"🏆 €{amount:.0f} Meilenstein!", content,
                       channels=["telegram", "discord", "slack"])


async def blast_trend_alert(trend: dict) -> dict:
    """Blast bei neuem Trend-Alert."""
    keyword = trend.get("keyword", "")
    score   = trend.get("score", 0)
    content = (f"📈 *Trend Alert: {keyword}*\n"
               f"Score: {score}/100\n"
               f"Jetzt agieren: {SHOP_URL}")
    return await _fire(f"📈 Trend: {keyword}", content,
                       channels=["telegram", "slack", "discord"])


# ─── Batch-Blast für Mass-Creator ─────────────────────────────────────────────

async def blast_mass_creation_complete(stats: dict) -> dict:
    """Blast nach Mass-Creation von Produkten/Kampagnen."""
    what    = stats.get("what", "Einheiten")
    created = stats.get("created", 0)
    failed  = stats.get("failed", 0)
    source  = stats.get("source", "System")

    content = (f"✅ *Mass-Creation abgeschlossen!*\n"
               f"System: {source}\n"
               f"✅ Erstellt: {created}\n"
               f"❌ Fehler: {failed}\n"
               f"🕐 {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC")

    return await _fire(f"✅ {source}: {created} erstellt", content,
                       channels=["telegram", "slack"])


async def blast_daily_summary(summary: dict) -> dict:
    """Täglicher Summary-Blast aller Systeme."""
    lines = [f"📊 *Tages-Summary {datetime.now(timezone.utc).strftime('%d.%m.%Y')}*\n"]

    for key, val in summary.items():
        lines.append(f"• {key}: {val}")

    content = "\n".join(lines)
    return await _fire("📊 Tages-Summary", content,
                       channels=["telegram", "slack", "discord"])


# ─── Universal Integration Hooks ──────────────────────────────────────────────

async def on_shopify_product_created(product: dict) -> None:
    """Hook: nach Shopify-Produkt-Erstellung."""
    try:
        await blast_new_product(product, channels=["telegram", "shopify_blog"])
    except Exception as e:
        log.warning("on_shopify_product_created error: %s", e)


async def on_ds24_product_created(product: dict) -> None:
    """Hook: nach DS24-Produkt-Erstellung."""
    try:
        await blast_ds24_product(product)
    except Exception as e:
        log.warning("on_ds24_product_created error: %s", e)


async def on_klaviyo_campaign_sent(campaign: dict) -> None:
    """Hook: nach Klaviyo-Kampagne."""
    try:
        await blast_klaviyo_campaign(campaign)
    except Exception as e:
        log.warning("on_klaviyo_campaign_sent error: %s", e)


async def on_mailchimp_campaign_sent(campaign: dict) -> None:
    """Hook: nach Mailchimp-Kampagne."""
    try:
        await blast_mailchimp_campaign(campaign)
    except Exception as e:
        log.warning("on_mailchimp_campaign_sent error: %s", e)


async def on_revenue_milestone(amount: float, source: str = "all") -> None:
    """Hook: bei Umsatz-Meilenstein (z.B. jede €100)."""
    try:
        await blast_revenue_milestone({"amount": amount, "source": source})
    except Exception as e:
        log.warning("on_revenue_milestone error: %s", e)


# ─── System-Status Blast ───────────────────────────────────────────────────────

async def blast_system_status() -> dict:
    """Stündlicher System-Status-Blast."""
    lines = [f"🤖 *System Status {datetime.now(timezone.utc).strftime('%H:%M')} UTC*\n"]

    modules = [
        ("shopify_mass_creator", "Shopify Mass"),
        ("klaviyo_mass_campaigns", "Klaviyo Mass"),
        ("mailchimp_mass_campaigns", "Mailchimp Mass"),
        ("ds24_mass_creator", "DS24 Mass"),
        ("revenue_mega_tracker", "Revenue Tracker"),
    ]
    for mod_name, label in modules:
        try:
            import importlib
            mod = importlib.import_module(f"modules.{mod_name}")
            if hasattr(mod, f"get_{mod_name.split('_')[0]}_mass_stats"):
                pass
            lines.append(f"✅ {label}: aktiv")
        except Exception:
            lines.append(f"⚠️ {label}: nicht geladen")

    content = "\n".join(lines)
    return await _fire("🤖 System Status", content, channels=["telegram"])


async def run_brutus_clone_cycle() -> dict:
    """Scheduler-Task: stündlich alle aktiven Systeme pingen."""
    status = await blast_system_status()
    return {"ok": True, "status_blast": status}


async def get_integrator_stats() -> dict:
    """Status-Endpoint für Dashboard."""
    return {
        "ok": True,
        "channels": ["telegram", "shopify_blog", "linkedin", "mailchimp",
                     "klaviyo", "indexnow", "discord", "slack"],
        "hooks": ["on_shopify_product_created", "on_ds24_product_created",
                  "on_klaviyo_campaign_sent", "on_mailchimp_campaign_sent",
                  "on_revenue_milestone"],
        "blast_functions": ["blast_new_product", "blast_ds24_product",
                            "blast_klaviyo_campaign", "blast_mailchimp_campaign",
                            "blast_revenue_milestone", "blast_daily_summary"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
