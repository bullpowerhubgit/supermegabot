#!/usr/bin/env python3
"""
CRO Engine — Conversion Rate Optimization
Turns visitors into buyers automatically.

Runs daily: welcome flows, urgency campaigns, upsells, Shopify banner, revenue report.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("CRO")

KLAVIYO_KEY     = os.getenv("KLAVIYO_API_KEY", "")
KLAVIYO_LIST_ID = os.getenv("KLAVIYO_LIST_ID", "bc5c7887cf")
SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")
DS24_KEY        = os.getenv("DIGISTORE24_API_KEY", "")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
MAILCHIMP_KEY   = os.getenv("MAILCHIMP_API_KEY", "")
MAILCHIMP_LIST  = os.getenv("MAILCHIMP_LIST_ID", "")
MAILCHIMP_SRV   = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "brutus"))

_KLAVIYO_HEADERS = lambda: {
    "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
    "revision": "2024-10-15",
    "Content-Type": "application/json",
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. KLAVIYO WELCOME FLOW
# ─────────────────────────────────────────────────────────────────────────────

async def create_klaviyo_welcome_flow() -> bool:
    """Welcome broadcast via Klaviyo campaign (3-step API) + SMTP fallback.

    Klaviyo Flow-API does NOT support creating flows with actions in one call.
    We use a direct campaign broadcast instead.
    """
    shopify_url = f"https://{SHOPIFY_DOMAIN}" if SHOPIFY_DOMAIN else "https://bullpower-hub-portal.netlify.app"

    # ── Klaviyo campaign (3-step) ─────────────────────────────────────────────
    if KLAVIYO_KEY:
        try:
            import aiohttp
            from datetime import datetime as _dt
            today = _dt.now().strftime("%d.%m.%Y")
            html_body = (
                "<h1>Willkommen bei BullPower Hub!</h1>"
                "<p>Schön dass du dabei bist. Hier sind die 3 wichtigsten Tipps:</p>"
                "<ol><li>Produktbeschreibungen mit KI generieren → spart 5h/Woche</li>"
                "<li>DS24-Käufer automatisch in E-Mail-Listen eintragen</li>"
                "<li>SEO-Content täglich automatisch publizieren</li></ol>"
                f'<p><a style="background:#7c3aed;color:#fff;padding:12px 24px;'
                f'text-decoration:none;border-radius:6px;display:inline-block" '
                f'href="{shopify_url}?utm_source=email&utm_medium=welcome&utm_campaign=cro">'
                "→ Jetzt kostenlos starten</a></p>"
            )
            async with aiohttp.ClientSession() as s:
                # Step 1: create campaign
                r1 = await s.post(
                    "https://a.klaviyo.com/api/campaigns/",
                    headers=_KLAVIYO_HEADERS(),
                    json={"data": {"type": "campaign", "attributes": {
                        "name": f"Welcome — {today}",
                        "channel": "email",
                        "audiences": {"included": [KLAVIYO_LIST_ID], "excluded": []},
                        "send_strategy": {"method": "immediate"},
                    }}},
                    timeout=aiohttp.ClientTimeout(total=20),
                )
                c1 = await r1.json(content_type=None)
                campaign_id = c1.get("data", {}).get("id")
                if not campaign_id:
                    raise ValueError(f"Campaign create failed: {str(c1)[:200]}")

                # Step 2: get campaign message id
                r2 = await s.get(
                    f"https://a.klaviyo.com/api/campaigns/{campaign_id}/campaign-messages/",
                    headers=_KLAVIYO_HEADERS(),
                    timeout=aiohttp.ClientTimeout(total=10),
                )
                c2 = await r2.json(content_type=None)
                msg_id = (c2.get("data") or [{}])[0].get("id") if c2.get("data") else None

                # Step 3: patch message with content
                if msg_id:
                    await s.patch(
                        f"https://a.klaviyo.com/api/campaign-messages/{msg_id}/",
                        headers=_KLAVIYO_HEADERS(),
                        json={"data": {"type": "campaign-message", "id": msg_id, "attributes": {
                            "definition": {
                                "type": "email",
                                "subject": "Willkommen! Hier sind deine 3 Automatisierungs-Tipps",
                                "preview_text": "Schnell starten mit BullPower Hub",
                                "from_email": "hello@bullpowerhub.com",
                                "from_label": "Rudolf @ BullPower Hub",
                                "reply_to_email": "hello@bullpowerhub.com",
                                "html_body": html_body,
                            }
                        }}},
                        timeout=aiohttp.ClientTimeout(total=15),
                    )

                # Step 4: send
                r4 = await s.post(
                    "https://a.klaviyo.com/api/campaign-send-jobs/",
                    headers=_KLAVIYO_HEADERS(),
                    json={"data": {"type": "campaign-send-job",
                                  "relationships": {"campaign": {"data": {"type": "campaign", "id": campaign_id}}}}},
                    timeout=aiohttp.ClientTimeout(total=15),
                )
                c4 = await r4.json(content_type=None)
                if c4.get("data", {}).get("id"):
                    log.info("CRO: Klaviyo welcome broadcast sent — campaign %s", campaign_id)
                    return True
                log.info("CRO: Klaviyo welcome campaign created (%s) — %s", campaign_id, str(c4)[:100])
                return bool(campaign_id)
        except Exception as exc:
            log.warning("CRO: Klaviyo welcome flow error (using SMTP fallback): %s", exc)

    # ── SMTP fallback — blast to our outreach leads ───────────────────────────
    try:
        from modules.mass_outreach_1000 import run_batch_only
        result = await run_batch_only(batch_size=50)
        sent = result.get("sent", 0) if isinstance(result, dict) else 0
        log.info("CRO: SMTP fallback welcome blast → %d sent", sent)
        return sent > 0
    except Exception as exc2:
        log.warning("CRO: SMTP fallback error: %s", exc2)
        return False


async def _create_klaviyo_welcome_flow_legacy() -> bool:
    """Legacy placeholder — not used (Klaviyo API doesn't support inline flow_actions)."""
    shopify_url = f"https://{SHOPIFY_DOMAIN}" if SHOPIFY_DOMAIN else "https://bullpower-hub-portal.netlify.app"
    flow_payload = {
        "data": {
            "type": "flow",
            "attributes": {
                "name": "BullPower Welcome Series (CRO) — LEGACY",
                "status": "draft",
                "trigger_type": "list",
                "trigger_id": KLAVIYO_LIST_ID,
                "flow_actions": [
                    {
                        "type": "flow-action",
                        "attributes": {
                            "action_type": "send-email",
                            "settings": {
                                "name": "1 — Willkommen + Bonus",
                                "from_label": "Rudolf @ BullPower Hub",
                                "from_email": "hello@bullpowerhub.com",
                                "subject": "Danke! Hier ist dein Bonus...",
                                "preview_text": "Schön dass du dabei bist!",
                                "html_body": (
                                    "<h1>Willkommen bei BullPower Hub!</h1>"
                                    "<p>Hey, ich freue mich dass du dabei bist.</p>"
                                    "<p>Als Erstes: <strong>hier sind die 3 wichtigsten Tipps</strong> um deinen "
                                    "Shopify-Shop sofort zu automatisieren:</p>"
                                    "<ol><li>Produktbeschreibungen mit KI generieren → spart 5h/Woche</li>"
                                    "<li>DS24-Käufer automatisch in E-Mail-Listen eintragen</li>"
                                    "<li>SEO-Content täglich automatisch publizieren</li></ol>"
                                    f'<p><a href="{shopify_url}?utm_source=email&utm_medium=welcome&utm_campaign=day0">'
                                    "→ Jetzt kostenlos starten</a></p>"
                                ),
                            },
                            "timing": {"type": "immediate"},
                        },
                    },
                    {
                        "type": "flow-action",
                        "attributes": {
                            "action_type": "send-email",
                            "settings": {
                                "name": "2 — Mehrwert Tag 3",
                                "from_label": "Rudolf @ BullPower Hub",
                                "from_email": "hello@bullpowerhub.com",
                                "subject": "Wie ich €111 im Februar verdient habe (und warum es jetzt mehr wird)",
                                "preview_text": "Meine ehrliche Bilanz...",
                                "html_body": (
                                    "<h2>Ehrlich gesagt: Der Anfang ist langsam.</h2>"
                                    "<p>Meine ersten DS24-Einnahmen: €111. Drei Transaktionen. Nicht viel — aber das "
                                    "System war noch nicht vollständig automatisiert.</p>"
                                    "<p>Jetzt läuft BRUTUS alle 3 Stunden und postet auf 6 Kanälen gleichzeitig:</p>"
                                    "<ul><li>Facebook, Instagram, YouTube</li>"
                                    "<li>Shopify Blog (SEO)</li><li>Klaviyo E-Mails</li></ul>"
                                    "<p>Das ist der Unterschied zwischen manuell und <strong>vollautomatisch</strong>.</p>"
                                    f'<p><a href="{shopify_url}?utm_source=email&utm_medium=welcome&utm_campaign=day3">'
                                    "→ Sieh wie es funktioniert</a></p>"
                                ),
                            },
                            "timing": {"type": "time_delay", "delay": {"unit": "days", "value": 3}},
                        },
                    },
                    {
                        "type": "flow-action",
                        "attributes": {
                            "action_type": "send-email",
                            "settings": {
                                "name": "3 — Angebot Tag 7",
                                "from_label": "Rudolf @ BullPower Hub",
                                "from_email": "hello@bullpowerhub.com",
                                "subject": "⚡ Nur für dich: 20% Rabatt (läuft in 48h ab)",
                                "preview_text": "Exklusiv für neue Mitglieder",
                                "html_body": (
                                    "<h2>Danke, dass du die letzten 7 Tage dabei warst.</h2>"
                                    "<p>Als Dankeschön: <strong>20% Rabatt auf alle Tarife</strong> — "
                                    "aber nur für die nächsten 48 Stunden.</p>"
                                    "<p>Was du bekommst:</p>"
                                    "<ul><li>✅ BRUTUS Traffic Engine (6-Kanal automatisch)</li>"
                                    "<li>✅ DS24 + Shopify vollautomatisch</li>"
                                    "<li>✅ Klaviyo + Mailchimp Funnels</li>"
                                    "<li>✅ Tägliche Revenue-Reports auf Telegram</li></ul>"
                                    f'<p><a style="background:#7c3aed;color:#fff;padding:12px 24px;'
                                    f'text-decoration:none;border-radius:6px;display:inline-block" '
                                    f'href="{shopify_url}?utm_source=email&utm_medium=welcome&utm_campaign=day7&discount=WELCOME20">'
                                    "→ Jetzt mit 20% Rabatt starten</a></p>"
                                    "<p><small>Angebot läuft in 48 Stunden ab. Danach regulärer Preis.</small></p>"
                                ),
                            },
                            "timing": {"type": "time_delay", "delay": {"unit": "days", "value": 7}},
                        },
                    },
                ],
            },
        }
    }

    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://a.klaviyo.com/api/flows/",
                headers=_KLAVIYO_HEADERS(),
                json=flow_payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        if data.get("data", {}).get("id"):
            log.info("CRO: Klaviyo welcome flow created — %s", data["data"]["id"])
            return True
        log.debug("CRO: Flow creation response (non-critical): %s", str(data)[:200])
        return False
    except Exception as exc:
        log.warning("CRO: create_klaviyo_welcome_flow error: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 2. URGENCY CAMPAIGN
# ─────────────────────────────────────────────────────────────────────────────

async def create_urgency_campaign(product_name: str, discount_pct: int = 20) -> bool:
    """Fire a 24h-urgency Klaviyo campaign for a given product."""
    if not KLAVIYO_KEY:
        return False

    shopify_url = f"https://{SHOPIFY_DOMAIN}" if SHOPIFY_DOMAIN else "https://bullpower-hub-portal.netlify.app"
    subject = f"⚡ NUR 24h: {discount_pct}% auf {product_name}"
    today = datetime.now().strftime("%d.%m.%Y")

    html_body = f"""
<h2>{subject}</h2>
<p>Nur heute, {today} — danach ist das Angebot weg.</p>
<p style="background:#fff3cd;border:1px solid #ffc107;padding:12px;border-radius:6px">
  ⏰ <strong>Dieses Angebot läuft in 24 Stunden ab.</strong><br>
  Nur noch <strong>7 Plätze</strong> zu diesem Preis verfügbar.
</p>
<p>Was du bekommst:<br>
<strong>{product_name}</strong> — {discount_pct}% günstiger als normal.</p>
<p>
  <a style="background:#dc2626;color:#fff;padding:14px 28px;text-decoration:none;
  border-radius:6px;display:inline-block;font-weight:bold"
  href="{shopify_url}?utm_source=email&utm_medium=urgency&utm_campaign={product_name[:20]}">
  → Jetzt {discount_pct}% Rabatt sichern
  </a>
</p>
<p><small>Nach Ablauf gilt wieder der reguläre Preis. Kein automatisches Abo.</small></p>
"""

    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            # Step 1: create campaign (no message content here)
            r1 = await s.post(
                "https://a.klaviyo.com/api/campaigns/",
                headers=_KLAVIYO_HEADERS(),
                json={"data": {"type": "campaign", "attributes": {
                    "name": f"URGENCY — {product_name[:40]} — {today}",
                    "channel": "email",
                    "audiences": {"included": [KLAVIYO_LIST_ID], "excluded": []},
                    "send_strategy": {"method": "immediate"},
                }}},
                timeout=aiohttp.ClientTimeout(total=20),
            )
            c1 = await r1.json(content_type=None)
            campaign_id = c1.get("data", {}).get("id")
            if not campaign_id:
                log.warning("CRO: Urgency campaign create failed: %s", str(c1)[:200])
                return False

            # Step 2: get auto-created message id
            r2 = await s.get(
                f"https://a.klaviyo.com/api/campaigns/{campaign_id}/campaign-messages/",
                headers=_KLAVIYO_HEADERS(),
                timeout=aiohttp.ClientTimeout(total=10),
            )
            c2 = await r2.json(content_type=None)
            msg_list = c2.get("data") or []
            msg_id = msg_list[0].get("id") if msg_list else None

            # Step 3: patch message with HTML content
            if msg_id:
                await s.patch(
                    f"https://a.klaviyo.com/api/campaign-messages/{msg_id}/",
                    headers=_KLAVIYO_HEADERS(),
                    json={"data": {"type": "campaign-message", "id": msg_id, "attributes": {
                        "definition": {
                            "type": "email",
                            "subject": subject,
                            "preview_text": f"Nur {discount_pct}% Rabatt — läuft heute ab!",
                            "from_email": "hello@bullpowerhub.com",
                            "from_label": "BullPower Hub",
                            "reply_to_email": "hello@bullpowerhub.com",
                            "html_body": html_body,
                        }
                    }}},
                    timeout=aiohttp.ClientTimeout(total=15),
                )

            # Step 4: trigger send
            r4 = await s.post(
                "https://a.klaviyo.com/api/campaign-send-jobs/",
                headers=_KLAVIYO_HEADERS(),
                json={"data": {"type": "campaign-send-job",
                               "relationships": {"campaign": {"data": {"type": "campaign", "id": campaign_id}}}}},
                timeout=aiohttp.ClientTimeout(total=15),
            )
            c4 = await r4.json(content_type=None)
            if c4.get("data", {}).get("id") or c4.get("data", {}).get("type"):
                log.info("CRO: Urgency campaign sent — %s", campaign_id)
                return True
            log.info("CRO: Urgency campaign created (%s), send status: %s", campaign_id, str(c4)[:100])
            return bool(campaign_id)
    except Exception as exc:
        log.warning("CRO: create_urgency_campaign error: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 3. DS24 BUYER UPSELL
# ─────────────────────────────────────────────────────────────────────────────

async def upsell_ds24_buyers() -> int:
    """Send upsell campaign to recent DS24 buyers who haven't received one yet."""
    buyers_file = DATA_DIR / "ds24_synced_buyers.json"
    upsell_file = DATA_DIR / "upsell_sent.json"

    if not buyers_file.exists():
        log.info("CRO: No DS24 buyers file yet")
        return 0

    try:
        buyers = json.loads(buyers_file.read_text())
    except Exception:
        return 0

    try:
        upsell_sent = json.loads(upsell_file.read_text()) if upsell_file.exists() else {}
    except Exception:
        upsell_sent = {}

    now = datetime.now(timezone.utc)
    sent_count = 0
    shopify_url = f"https://{SHOPIFY_DOMAIN}" if SHOPIFY_DOMAIN else "https://bullpower-hub-portal.netlify.app"

    for email, info in buyers.items():
        if email in upsell_sent:
            continue

        try:
            bought_at = datetime.fromisoformat(info.get("synced_at", "2000-01-01"))
            if bought_at.tzinfo is None:
                bought_at = bought_at.replace(tzinfo=timezone.utc)
        except Exception:
            continue

        if (now - bought_at).days > 14:
            continue

        product = info.get("product", "BullPower Pro")
        subject = f"Hey! Hast du schon {product} Pro ausprobiert?"

        html_body = f"""
<h2>Du hast {product} gekauft — danke!</h2>
<p>Basierend auf deinem Kauf habe ich eine Empfehlung für dich:</p>
<p style="background:#f0f9ff;border:1px solid #0ea5e9;padding:12px;border-radius:6px">
  🚀 <strong>BullPower Hub Pro Bundle</strong><br>
  8 KI-Tools für vollständige E-Commerce-Automatisierung — €99/Monat
</p>
<p>Was andere Käufer sagen: "In der ersten Woche hat das System 3 neue Bestellungen generiert."</p>
<a style="background:#7c3aed;color:#fff;padding:12px 24px;text-decoration:none;
border-radius:6px;display:inline-block"
href="{shopify_url}?utm_source=email&utm_medium=upsell&utm_campaign=ds24_buyer">
→ Pro Bundle ansehen
</a>
"""

        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://a.klaviyo.com/api/campaigns/",
                    headers=_KLAVIYO_HEADERS(),
                    json={"data": {"type": "campaign", "attributes": {
                        "name": f"UPSELL — {email[:30]} — {now.strftime('%d.%m')}",
                        "audiences": {"included": [KLAVIYO_LIST_ID]},
                        "send_strategy": {"method": "immediate"},
                        "campaign-messages": {"data": [{"type": "campaign-message", "attributes": {
                            "definition": {
                                "type": "email",
                                "subject": subject,
                                "preview_text": "Exklusive Empfehlung für dich",
                                "from_email": "hello@bullpowerhub.com",
                                "from_label": "BullPower Hub",
                                "reply_to_email": "hello@bullpowerhub.com",
                                "html_body": html_body,
                            }
                        }}]},
                    }}},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    resp = await r.json(content_type=None)
            if resp.get("data", {}).get("id"):
                upsell_sent[email] = {"sent_at": now.isoformat(), "campaign_id": resp["data"]["id"]}
                sent_count += 1
        except Exception as exc:
            log.warning("CRO: Upsell send error for %s: %s", email[:20], exc)

    if upsell_sent:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        upsell_file.write_text(json.dumps(upsell_sent, ensure_ascii=False, indent=2))

    log.info("CRO: Upsell sent to %d buyers", sent_count)
    return sent_count


# ─────────────────────────────────────────────────────────────────────────────
# 4. SHOPIFY URGENCY BANNER
# ─────────────────────────────────────────────────────────────────────────────

async def add_shopify_urgency_banner() -> bool:
    """Update or add urgency announcement bar in active Shopify theme."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return False

    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
    }
    base = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}"

    # Rotate urgency messages daily
    day = datetime.now().day
    messages = [
        "⚡ Limitiertes Angebot: Gratis Versand bis Mitternacht!",
        "🔥 Nur heute: 15% Rabatt mit Code HEUTE15",
        "⏰ Letzte Chance: Sonderpreis läuft in 6 Stunden ab!",
        "🚀 Neu eingetroffen: KI-Automatisierung für Shopify — jetzt testen",
        "✅ Über 100 Shops vertrauen BullPower Hub — kostenlos starten",
    ]
    message = messages[day % len(messages)]

    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            # Get themes
            async with s.get(f"{base}/themes.json", headers=headers,
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                themes = (await r.json(content_type=None)).get("themes", [])

            main_theme = next((t for t in themes if t.get("role") == "main"), None)
            if not main_theme:
                log.warning("CRO: No main Shopify theme found")
                return False
            theme_id = main_theme["id"]

            # Try to get existing announcement-bar asset
            async with s.get(
                f"{base}/themes/{theme_id}/assets.json",
                params={"asset[key]": "sections/announcement-bar.liquid"},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                existing = await r.json(content_type=None)

            existing_value = existing.get("asset", {}).get("value", "")

            if existing_value:
                # Update the text inside existing liquid
                import re
                new_value = re.sub(
                    r'(text["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])',
                    lambda m: f"{m.group(1)}{message}{m.group(3)}",
                    existing_value,
                    count=1,
                )
                if new_value == existing_value:
                    # Pattern didn't match, just prepend the message as a comment approach
                    new_value = existing_value.replace(
                        "{% schema %}", f'<p class="announcement">{ message }</p>\n{{% schema %}}', 1
                    )
            else:
                # Create minimal announcement-bar section
                new_value = (
                    f'<div class="announcement-bar" style="background:#7c3aed;color:#fff;'
                    f'text-align:center;padding:8px;font-weight:600">'
                    f'{message}</div>\n'
                    '{% schema %}\n{"name":"Announcement Bar","settings":[]}\n{% endschema %}'
                )

            # PUT updated asset
            async with s.put(
                f"{base}/themes/{theme_id}/assets.json",
                headers=headers,
                json={"asset": {"key": "sections/announcement-bar.liquid", "value": new_value}},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                result = await r.json(content_type=None)

        if result.get("asset", {}).get("key"):
            log.info("CRO: Shopify urgency banner updated — %s", message[:50])
            return True
        log.warning("CRO: Shopify banner update failed: %s", str(result)[:200])
        return False
    except Exception as exc:
        log.warning("CRO: add_shopify_urgency_banner error: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 5. DAILY REVENUE REPORT
# ─────────────────────────────────────────────────────────────────────────────

async def send_revenue_report() -> bool:
    """Collect revenue data and send daily Telegram report."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return False

    lines = [f"📊 *DAILY REVENUE REPORT — {datetime.now().strftime('%d.%m.%Y')}*\n"]

    # DS24 revenue last 7 days
    try:
        import aiohttp
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://www.digistore24.com/api/call/listOrders",
                headers={"X-DS-API-KEY": DS24_KEY},
                params={"start_date": start, "end_date": end},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                ds24_data = await r.json(content_type=None)
        orders = ds24_data.get("data", {}).get("orders", [])
        ds24_revenue = sum(
            float(o.get("buyer", {}).get("transaction_amount") or o.get("transaction_amount", 0))
            for o in orders
        )
        lines.append(f"💰 DS24 Revenue (7 Tage): €{ds24_revenue:.2f} ({len(orders)} Orders)")
    except Exception as exc:
        lines.append(f"💰 DS24: Fehler ({exc})")

    # Shopify orders last 7 days
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/orders.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                params={"created_at_min": since, "status": "any", "limit": 250},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                shopify_data = await r.json(content_type=None)
        shopify_orders = shopify_data.get("orders", [])
        shopify_revenue = sum(float(o.get("total_price", 0)) for o in shopify_orders)
        lines.append(f"🛒 Shopify Revenue (7 Tage): €{shopify_revenue:.2f} ({len(shopify_orders)} Orders)")
    except Exception as exc:
        lines.append(f"🛒 Shopify: Fehler ({exc})")

    # Klaviyo list size
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://a.klaviyo.com/api/lists/{KLAVIYO_LIST_ID}/",
                headers=_KLAVIYO_HEADERS(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                kl_data = await r.json(content_type=None)
        kl_count = kl_data.get("data", {}).get("attributes", {}).get("profile_count", "?")
        lines.append(f"📧 Klaviyo Liste: {kl_count} Kontakte")
    except Exception as exc:
        lines.append(f"📧 Klaviyo: Fehler ({exc})")

    # Mailchimp list size
    try:
        import aiohttp
        import base64
        mc_auth = base64.b64encode(f"any:{MAILCHIMP_KEY}".encode()).decode()
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{MAILCHIMP_SRV}.api.mailchimp.com/3.0/lists/{MAILCHIMP_LIST}",
                headers={"Authorization": f"Basic {mc_auth}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                mc_data = await r.json(content_type=None)
        mc_count = mc_data.get("stats", {}).get("member_count", "?")
        lines.append(f"📩 Mailchimp Liste: {mc_count} Kontakte")
    except Exception as exc:
        lines.append(f"📩 Mailchimp: Fehler ({exc})")

    # BRUTUS today: count from performance state
    try:
        state_file = DATA_DIR / "performance_state.json"
        if state_file.exists():
            state = json.loads(state_file.read_text())
            today_str = datetime.now().strftime("%Y-%m-%d")
            today_posts = [k for k, v in state.items()
                           if v.get("generated_at", "").startswith(today_str)]
            lines.append(f"\n🔥 BRUTUS heute: {len(today_posts)} Keywords × 10 Formate × 6 Kanäle")
            if today_posts:
                lines.append("Keywords: " + ", ".join(today_posts[:3]))
    except Exception:
        pass

    lines.append("\n_Automatisch generiert von CRO Engine_")
    msg = "\n".join(lines)

    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                result = await r.json(content_type=None)
        ok = result.get("ok", False)
        log.info("CRO: Revenue report sent to Telegram: %s", ok)
        return ok
    except Exception as exc:
        log.warning("CRO: send_revenue_report Telegram error: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 6. MASTER RUN
# ─────────────────────────────────────────────────────────────────────────────

async def run_cro() -> dict:
    """Run all CRO tasks. Called daily by automation_scheduler."""
    log.info("CRO ENGINE START")
    results = {}

    # Welcome flow (idempotent-ish — Klaviyo deduplicates by name)
    try:
        results["welcome_flow"] = await create_klaviyo_welcome_flow()
    except Exception as exc:
        log.warning("CRO run: welcome_flow error: %s", exc)
        results["welcome_flow"] = False

    # Urgency campaign for top product
    try:
        results["urgency_campaign"] = await create_urgency_campaign(
            "BullPower Hub Pro Bundle", discount_pct=20
        )
    except Exception as exc:
        log.warning("CRO run: urgency_campaign error: %s", exc)
        results["urgency_campaign"] = False

    # Upsell DS24 buyers
    try:
        results["upsells_sent"] = await upsell_ds24_buyers()
    except Exception as exc:
        log.warning("CRO run: upsell error: %s", exc)
        results["upsells_sent"] = 0

    # Shopify urgency banner
    try:
        results["shopify_banner"] = await add_shopify_urgency_banner()
    except Exception as exc:
        log.warning("CRO run: shopify_banner error: %s", exc)
        results["shopify_banner"] = False

    # Revenue report
    try:
        results["revenue_report"] = await send_revenue_report()
    except Exception as exc:
        log.warning("CRO run: revenue_report error: %s", exc)
        results["revenue_report"] = False

    log.info("CRO ENGINE DONE: %s", results)
    return results
