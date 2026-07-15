#!/usr/bin/env python3
"""
Streetwear Email Engine — Mailchimp + Klaviyo + DS24 cross-promo
Fetches latest Printify T-shirts from Shopify → sends beautiful HTML emails
"""
import asyncio
import logging
import os
import random
from base64 import b64encode
from datetime import datetime
from typing import List, Dict, Optional

import aiohttp

log = logging.getLogger("StreetEmail")

SHOP_DOMAIN     = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
MC_API_KEY      = os.getenv("MAILCHIMP_API_KEY", "")
MC_LIST_ID      = os.getenv("MAILCHIMP_LIST_ID", "606e45a6b0")
MC_SERVER       = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")
KL_API_KEY      = os.getenv("KLAVIYO_API_KEY", "")
KL_LIST_ID      = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
DS24_AFFILIATE  = os.getenv("DS24_AFFILIATE_ID", "user37405262")
STORE_URL       = f"https://{SHOP_DOMAIN}" if SHOP_DOMAIN else "https://ineedit.com.co"


# ── Shopify: fetch latest Printify products ───────────────────────────────────

async def get_latest_printify_products(limit: int = 12) -> List[Dict]:
    """Fetch the newest active Printify products with images."""
    if not SHOP_DOMAIN or not SHOPIFY_TOKEN:
        return []
    url = f"https://{SHOP_DOMAIN}/admin/api/2024-10/products.json"
    params = {
        "limit": limit * 2,
        "status": "active",
        "vendor": "Printify",
        "fields": "id,title,handle,images,variants,body_html",
    }
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    return []
                data = await r.json()
        products = data.get("products", [])
        # Only keep products with images
        with_images = [p for p in products if p.get("images")]
        return with_images[:limit]
    except Exception as e:
        log.error("Shopify fetch error: %s", e)
        return []


# ── HTML email builder ────────────────────────────────────────────────────────

def _product_card_html(product: Dict) -> str:
    title = product.get("title", "New Design")[:60]
    handle = product.get("handle", "")
    img_src = product.get("images", [{}])[0].get("src", "")
    # Get lowest price from variants
    variants = product.get("variants", [{}])
    price = variants[0].get("price", "29.99") if variants else "29.99"
    url = f"{STORE_URL}/products/{handle}"
    return f"""
    <td style="width:200px;padding:10px;text-align:center;vertical-align:top;">
      <a href="{url}" style="text-decoration:none;">
        <img src="{img_src}" width="180" height="180"
             style="border-radius:8px;object-fit:cover;border:2px solid #1a1a2e;" alt="{title}"/>
        <p style="color:#e94560;font-family:Arial,sans-serif;font-size:13px;font-weight:bold;margin:8px 0 4px;">{title}</p>
        <p style="color:#0f3460;font-size:14px;font-weight:bold;margin:0;">€{price}</p>
        <span style="display:inline-block;background:#e94560;color:white;padding:6px 14px;border-radius:20px;font-size:12px;margin-top:8px;">Shop Now</span>
      </a>
    </td>"""


def build_email_html(products: List[Dict], subject: str, campaign_type: str = "new_arrivals") -> str:
    rows = []
    row_html = ""
    for i, p in enumerate(products):
        row_html += _product_card_html(p)
        if (i + 1) % 3 == 0 or i == len(products) - 1:
            rows.append(f'<tr>{row_html}</tr>')
            row_html = ""

    product_grid = "\n".join(rows)

    headlines = {
        "new_arrivals":    "🔥 Neue Streetwear Designs — Jetzt verfügbar!",
        "weekly_drops":    "⚡ Weekly Drop — Street Edition",
        "cyber_collection": "🤖 Cybersonic Collection — Limited Styles",
    }
    headline = headlines.get(campaign_type, headlines["new_arrivals"])

    ds24_url = os.getenv("DS24_AFFILIATE_LINK", "")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{subject}</title></head>
<body style="margin:0;padding:0;background:#0a0a1a;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a1a;">
<tr><td align="center" style="padding:30px 10px;">
<table width="620" cellpadding="0" cellspacing="0"
       style="background:#111132;border-radius:16px;overflow:hidden;border:1px solid #1a1a4e;">

  <!-- Header -->
  <tr><td style="background:linear-gradient(135deg,#1a1a4e,#e94560);padding:30px;text-align:center;">
    <h1 style="color:white;font-family:Arial,sans-serif;font-size:28px;margin:0;letter-spacing:3px;">
      AIITEC STREETWEAR
    </h1>
    <p style="color:rgba(255,255,255,0.8);margin:8px 0 0;font-size:14px;letter-spacing:1px;">
      PREMIUM STREET CULTURE
    </p>
  </td></tr>

  <!-- Headline -->
  <tr><td style="padding:25px 30px 10px;text-align:center;">
    <h2 style="color:#e94560;font-family:Arial,sans-serif;font-size:22px;margin:0;">{headline}</h2>
    <p style="color:#aaa;font-size:14px;margin:10px 0 0;">
      Frische Designs — Bella+Canvas Premium Qualität — Print-on-Demand
    </p>
  </td></tr>

  <!-- Product grid -->
  <tr><td style="padding:20px 15px;">
    <table width="100%" cellpadding="0" cellspacing="0">
      {product_grid}
    </table>
  </td></tr>

  <!-- CTA Button -->
  <tr><td style="padding:15px 30px 25px;text-align:center;">
    <a href="{STORE_URL}/collections/all"
       style="display:inline-block;background:linear-gradient(135deg,#e94560,#c23152);
              color:white;padding:14px 40px;border-radius:30px;font-size:16px;
              font-weight:bold;text-decoration:none;font-family:Arial,sans-serif;
              letter-spacing:1px;">
      ALLE DESIGNS ENTDECKEN →
    </a>
  </td></tr>

  <!-- DS24 cross-promo banner -->
  <tr><td style="background:#0f3460;padding:20px 30px;text-align:center;">
    <p style="color:#16213e;background:#f5c518;display:inline-block;padding:3px 10px;
              border-radius:4px;font-size:11px;font-weight:bold;margin:0 0 8px;">
      DIGITAL BONUS
    </p>
    <p style="color:white;font-size:15px;font-family:Arial,sans-serif;margin:0 0 12px;">
      🤖 KI Automation Kurs — Passives Einkommen mit AI-Tools
    </p>
    <a href="{ds24_url}"
       style="background:#f5c518;color:#0a0a1a;padding:10px 28px;border-radius:20px;
              font-size:13px;font-weight:bold;text-decoration:none;">
      JETZT ANSEHEN
    </a>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:20px;text-align:center;border-top:1px solid #1a1a4e;">
    <p style="color:#555;font-size:12px;font-family:Arial,sans-serif;margin:0;">
      AIITEC Store · Automatisch generiert ·
      <a href="*|UNSUB|*" style="color:#e94560;">Abmelden</a>
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""


# ── Mailchimp sender ──────────────────────────────────────────────────────────

async def send_mailchimp_campaign(subject: str, html: str, list_id: str = "") -> Dict:
    if not MC_API_KEY:
        return {"ok": False, "error": "MAILCHIMP_API_KEY not set"}
    lid = list_id or MC_LIST_ID
    base = f"https://{MC_SERVER}.api.mailchimp.com/3.0"
    auth = b64encode(f"any:{MC_API_KEY}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            # 1. Create campaign
            payload = {
                "type": "regular",
                "recipients": {"list_id": lid},
                "settings": {
                    "subject_line": subject,
                    "from_name": "AIITEC Streetwear",
                    "reply_to": "aiitecbuuss@gmail.com",
                    "title": f"Streetwear {datetime.now().strftime('%Y-%m-%d')}",
                },
            }
            async with s.post(f"{base}/campaigns", headers=headers, json=payload,
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status not in (200, 201):
                    txt = await r.text()
                    return {"ok": False, "error": f"Create {r.status}: {txt[:200]}"}
                camp = await r.json()
            campaign_id = camp["id"]

            # 2. Set content
            async with s.put(f"{base}/campaigns/{campaign_id}/content",
                             headers=headers,
                             json={"html": html},
                             timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status not in (200, 204):
                    txt = await r.text()
                    return {"ok": False, "error": f"Content {r.status}: {txt[:200]}"}

            # 3. Send
            async with s.post(f"{base}/campaigns/{campaign_id}/actions/send",
                              headers=headers,
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 204:
                    log.info("Mailchimp campaign sent: %s", campaign_id)
                    return {"ok": True, "campaign_id": campaign_id}
                txt = await r.text()
                return {"ok": False, "error": f"Send {r.status}: {txt[:200]}"}

    except Exception as e:
        log.error("Mailchimp error: %s", e)
        return {"ok": False, "error": str(e)}


# ── Klaviyo sender ────────────────────────────────────────────────────────────

async def send_klaviyo_campaign(subject: str, html: str, list_id: str = "") -> Dict:
    if not KL_API_KEY:
        return {"ok": False, "error": "KLAVIYO_API_KEY not set"}
    lid = list_id or KL_LIST_ID
    headers = {
        "Authorization": f"Klaviyo-API-Key {KL_API_KEY}",
        "revision": "2024-10-15",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    base = "https://a.klaviyo.com/api"

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            # 1. Create campaign
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            payload = {
                "data": {
                    "type": "campaign",
                    "attributes": {
                        "name": f"Streetwear Drop {now_str}",
                        "audiences": {"included": [lid]},
                        "send_strategy": {"method": "immediate"},
                        "channel": "email",
                    },
                }
            }
            async with s.post(f"{base}/campaigns/", headers=headers, json=payload,
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status not in (200, 201, 202):
                    txt = await r.text()
                    return {"ok": False, "error": f"Create {r.status}: {txt[:200]}"}
                camp_data = await r.json()
            campaign_id = camp_data["data"]["id"]

            # 2. Get message ID
            async with s.get(f"{base}/campaigns/{campaign_id}/campaign-messages/",
                             headers=headers,
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                msg_data = await r.json()
            messages = msg_data.get("data", [])
            if not messages:
                return {"ok": False, "error": "No campaign messages found"}
            msg_id = messages[0]["id"]

            # 3. Update message content + subject
            msg_payload = {
                "data": {
                    "type": "campaign-message",
                    "id": msg_id,
                    "attributes": {
                        "definition": {
                            "channel": "email",
                            "content": {
                                "subject": subject,
                                "preview_text": "Neue Streetwear Designs jetzt verfügbar!",
                                "from_email": "aiitecbuuss@gmail.com",
                                "from_label": "AIITEC Streetwear",
                                "reply_to_email": "aiitecbuuss@gmail.com",
                                "html": html,
                            },
                        }
                    },
                }
            }
            async with s.patch(f"{base}/campaign-messages/{msg_id}/",
                               headers=headers, json=msg_payload,
                               timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status not in (200, 204):
                    txt = await r.text()
                    return {"ok": False, "error": f"Message {r.status}: {txt[:200]}"}

            # 4. Send
            async with s.post(f"{base}/campaigns/{campaign_id}/campaign-send-job/",
                              headers=headers,
                              json={"data": {"type": "campaign-send-job", "attributes": {}}},
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status in (200, 201, 202, 204):
                    log.info("Klaviyo campaign sent: %s", campaign_id)
                    return {"ok": True, "campaign_id": campaign_id}
                txt = await r.text()
                return {"ok": False, "error": f"Send {r.status}: {txt[:200]}"}

    except Exception as e:
        log.error("Klaviyo error: %s", e)
        return {"ok": False, "error": str(e)}


# ── Main orchestrator ─────────────────────────────────────────────────────────

CAMPAIGN_TYPES = ["new_arrivals", "weekly_drops", "cyber_collection"]
SUBJECTS = {
    "new_arrivals":      "🔥 Neue Streetwear Drops — jetzt im Shop!",
    "weekly_drops":      "⚡ Dein wöchentlicher Street-Drop ist da",
    "cyber_collection":  "🤖 Cybersonic Collection — Limitierte Designs",
}

async def run_streetwear_email_blast(campaign_type: str = "") -> Dict:
    """Fetch latest products → send via Mailchimp + Klaviyo."""
    if not campaign_type:
        campaign_type = random.choice(CAMPAIGN_TYPES)

    subject = SUBJECTS.get(campaign_type, SUBJECTS["new_arrivals"])
    products = await get_latest_printify_products(limit=9)

    if not products:
        return {"ok": False, "error": "Keine Printify-Produkte gefunden"}

    html = build_email_html(products, subject, campaign_type)

    mc_result  = await send_mailchimp_campaign(subject, html)
    kl_result  = await send_klaviyo_campaign(subject, html)

    mc_ok = mc_result.get("ok", False)
    kl_ok = kl_result.get("ok", False)

    log.info("Email blast: MC=%s KL=%s products=%d type=%s",
             "OK" if mc_ok else mc_result.get("error", "?")[:30],
             "OK" if kl_ok else kl_result.get("error", "?")[:30],
             len(products), campaign_type)

    return {
        "ok":           mc_ok or kl_ok,
        "mailchimp":    mc_result,
        "klaviyo":      kl_result,
        "products_sent": len(products),
        "campaign_type": campaign_type,
        "subject":      subject,
    }
