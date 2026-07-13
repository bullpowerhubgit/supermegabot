#!/usr/bin/env python3
"""
SuperRevenueBlitz — Maximaler simultaner Revenue-Push.
Alle Kanäle gleichzeitig: Telegram + LinkedIn + IndexNow + Klaviyo + GitHub SEO + AliExpress + Printify.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

log = logging.getLogger("RevenueBlitz")

TG_TOKEN   = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT    = lambda: os.getenv("TELEGRAM_CHAT_ID", "")
KLAVIYO    = lambda: os.getenv("KLAVIYO_API_KEY", "")
KLAVIYO_LIST = lambda: os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
SHOPIFY_DOMAIN = lambda: os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN  = lambda: os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER    = lambda: os.getenv("SHOPIFY_API_VERSION", "2024-01")
PRINTIFY_KEY   = lambda: os.getenv("PRINTIFY_API_KEY", "")
PRINTIFY_SHOP  = lambda: os.getenv("PRINTIFY_SHOP_ID", "27975583")
DS24_LINK      = lambda: os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/668035")


# ── Telegram ──────────────────────────────────────────────────────────────────

async def _tg_send(text: str) -> bool:
    if not TG_TOKEN() or not TG_CHAT():
        return False
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{TG_TOKEN()}/sendMessage",
                json={"chat_id": TG_CHAT(), "text": text[:4096], "parse_mode": "HTML",
                      "disable_web_page_preview": False},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json(content_type=None)
                return d.get("ok", False)
    except Exception as e:
        log.debug("TG send error: %s", e)
        return False


# ── Klaviyo ──────────────────────────────────────────────────────────────────

async def _klaviyo_event(event_name: str, properties: dict) -> bool:
    if not KLAVIYO():
        return False
    try:
        import aiohttp
        payload = {
            "data": {
                "type": "event",
                "attributes": {
                    "metric": {"data": {"type": "metric", "attributes": {"name": event_name}}},
                    "properties": properties,
                    "profile": {"data": {"type": "profile", "attributes": {"email": "broadcast@bullpowerhub.com"}}},
                }
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://a.klaviyo.com/api/events/",
                headers={"Authorization": f"Klaviyo-API-Key {KLAVIYO()}",
                         "revision": "2024-02-15", "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return r.status in (200, 201, 202)
    except Exception as e:
        log.debug("Klaviyo event error: %s", e)
        return False


# ── LinkedIn ──────────────────────────────────────────────────────────────────

async def _linkedin_post(text: str) -> bool:
    try:
        from modules.traffic_blitz import post_linkedin
        r = await post_linkedin(text)
        return r.get("ok", False)
    except Exception as e:
        log.debug("LinkedIn post error: %s", e)
        return False


# ── IndexNow ─────────────────────────────────────────────────────────────────

async def _indexnow() -> int:
    try:
        from modules.traffic_blitz import indexnow_blast
        r = await indexnow_blast()
        return r.get("submitted", 0)
    except Exception as e:
        log.debug("IndexNow error: %s", e)
        return 0


# ── GitHub SEO Blog ──────────────────────────────────────────────────────────

async def _github_seo_post(topic: str) -> Optional[str]:
    try:
        from modules.traffic_blitz import create_github_seo_post
        r = await create_github_seo_post(topic)
        return r.get("url") if r.get("ok") else None
    except Exception as e:
        log.debug("GitHub SEO post error: %s", e)
        return None


# ── Main Functions ────────────────────────────────────────────────────────────

async def revenue_blast_now() -> dict:
    """Triggert SOFORT alle Revenue-Kanäle gleichzeitig."""
    if os.getenv("SOCIAL_POSTING_PAUSED", "").lower() in ("1", "true", "yes"):
        log.warning("RevenueBlitz: SOCIAL_POSTING_PAUSED=true — übersprungen")
        return {"ok": False, "skipped": True, "reason": "SOCIAL_POSTING_PAUSED"}
    link = DS24_LINK()
    offer_text = (
        f"🔥 <b>SuperMegaBot — Vollautomatisches Online-Business</b>\n\n"
        f"💰 Während du schläfst verdient das System für dich:\n"
        f"• BRUTUS postet auf 10 Kanälen gleichzeitig\n"
        f"• KI generiert täglich neuen SEO-Content\n"
        f"• DS24 + Shopify vollautomatisch\n"
        f"• Klaviyo + Mailchimp Funnels\n\n"
        f"👉 <a href='{link}'>Jetzt starten — {datetime.now().strftime('%d.%m.%Y')}</a>"
    )

    tg_task     = _tg_send(offer_text)
    klaviyo_task = _klaviyo_event("revenue_blast", {"link": link, "ts": datetime.now().isoformat()})
    linkedin_text = (
        f"🚀 Vollautomatisches Online-Business 2026\n\n"
        f"BRUTUS postet gleichzeitig auf 10 Kanälen während du schläfst.\n"
        f"KI-Content, Shopify-Automation, DS24-Funnel — alles vollautomatisch.\n\n"
        f"👉 {link}\n\n"
        f"#PassivesEinkommen #Ecommerce #KI #OnlineBusiness #Shopify"
    )
    linkedin_task = _linkedin_post(linkedin_text)
    indexnow_task = _indexnow()

    tg, kl, li, idx = await asyncio.gather(
        tg_task, klaviyo_task, linkedin_task, indexnow_task,
        return_exceptions=True,
    )

    result = {
        "telegram":  bool(tg) if not isinstance(tg, Exception) else False,
        "klaviyo":   bool(kl) if not isinstance(kl, Exception) else False,
        "linkedin":  bool(li) if not isinstance(li, Exception) else False,
        "indexnow":  int(idx) if not isinstance(idx, Exception) else 0,
        "ts":        datetime.now().isoformat(),
    }
    log.info("Revenue Blitz: tg=%s kl=%s li=%s idx=%s",
             result["telegram"], result["klaviyo"], result["linkedin"], result["indexnow"])
    return result


async def aliexpress_import_trending(keywords: List[str] = None, max_products: int = 5) -> dict:
    """AliExpress trending Produkte → Shopify importieren mit AI-Beschreibungen."""
    if not SHOPIFY_DOMAIN() or not SHOPIFY_TOKEN():
        log.debug("aliexpress_import: Shopify not configured")
        return {"imported": 0, "skipped": 0, "error": "shopify_not_configured"}

    if keywords is None:
        keywords = ["trending ecommerce", "passive income tools", "dropshipping 2026"]

    imported = 0
    skipped = 0

    try:
        from modules.aliexpress_downloader import search_products
        from modules.ai_client import ai_complete
        import aiohttp

        base = f"https://{SHOPIFY_DOMAIN()}"
        headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN(), "Content-Type": "application/json"}

        for kw in keywords[:2]:  # max 2 keyword batches per run
            try:
                products = await search_products(kw, page_size=max_products)
            except Exception as e:
                log.debug("AliExpress search '%s' error: %s", kw, e)
                continue

            for p in products[:max_products]:
                try:
                    title = p.get("product_title", "")[:255] or "Trending Product"
                    price = float(p.get("sale_price", "9.99") or "9.99")
                    img   = p.get("product_main_image_url", "")
                    ali_url = p.get("product_detail_url", "")

                    ai_prompt = (
                        f"Erstelle eine überzeugende Shopify-Produktbeschreibung auf Deutsch für:\n"
                        f"Produkt: {title}\nPreis: €{price:.2f}\n"
                        f"Schreibe 3 Bullet-Points + 1 kurzen Überzeugungstext (max 150 Wörter). Kein HTML."
                    )
                    description = await ai_complete(ai_prompt, max_tokens=300)
                    if not description:
                        description = f"{title} — Jetzt zum Sonderpreis verfügbar."

                    shopify_product = {
                        "product": {
                            "title": title,
                            "body_html": f"<p>{description}</p>",
                            "vendor": "AliExpress Import",
                            "product_type": "Import",
                            "status": "draft",
                            "variants": [{"price": f"{price:.2f}", "inventory_management": None}],
                        }
                    }
                    if img:
                        shopify_product["product"]["images"] = [{"src": img}]

                    async with aiohttp.ClientSession() as s:
                        async with s.post(
                            f"{base}/admin/api/{SHOPIFY_VER()}/products.json",
                            headers=headers,
                            json=shopify_product,
                            timeout=aiohttp.ClientTimeout(total=15),
                        ) as r:
                            if r.status in (200, 201):
                                imported += 1
                                log.info("AliExpress→Shopify: imported '%s'", title[:50])
                            else:
                                skipped += 1
                                log.debug("AliExpress→Shopify skip (%s): %s", r.status, title[:40])

                except Exception as e:
                    log.debug("AliExpress product import error: %s", e)
                    skipped += 1

    except Exception as e:
        log.debug("aliexpress_import_trending error: %s", e)

    return {"imported": imported, "skipped": skipped}


async def printify_seo_blast() -> dict:
    """Alle Printify Produkte → AI-SEO Beschreibungen → Update via Printify API."""
    if not PRINTIFY_KEY():
        log.debug("printify_seo_blast: PRINTIFY_API_KEY not set")
        return {"updated": 0, "skipped": 0}

    shop_id = PRINTIFY_SHOP()
    updated = 0
    skipped = 0

    try:
        import aiohttp
        from modules.ai_client import ai_complete

        _pf_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        pf_headers = {"Authorization": f"Bearer {PRINTIFY_KEY()}", "Content-Type": "application/json", "User-Agent": _pf_ua}

        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.printify.com/v1/shops/{shop_id}/products.json?limit=20&page=1",
                headers=pf_headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                if r.status == 403:
                    log.debug("Printify products: 403 — scope issue, skip")
                    return {"updated": 0, "skipped": 0, "notice": "403_scope"}
                if r.status != 200:
                    log.debug("Printify products: %s", r.status)
                    return {"updated": 0, "skipped": 0}
                data = await r.json(content_type=None)

        products = data.get("data", [])
        log.info("Printify SEO blast: %d products found", len(products))

        for product in products[:10]:  # max 10 per run
            pid   = product.get("id", "")
            title = product.get("title", "")
            if not pid or not title:
                skipped += 1
                continue

            try:
                seo_prompt = (
                    f"Erstelle eine SEO-optimierte Produktbeschreibung auf Deutsch für:\n"
                    f"Produkt: {title}\n"
                    f"- H1-Titel (max 60 Zeichen, keyword-reich)\n"
                    f"- Beschreibung (150-200 Wörter, überzeugend, mit Keywords)\n"
                    f"- 5 Bullet-Points (Vorteile)\n"
                    f"Antworte als JSON: {{\"seo_title\": \"...\", \"description\": \"...\", \"bullets\": [...]}}"
                )
                raw = await ai_complete(seo_prompt, max_tokens=500)
                if not raw:
                    skipped += 1
                    continue

                s_idx = raw.find("{")
                e_idx = raw.rfind("}") + 1
                seo = json.loads(raw[s_idx:e_idx]) if s_idx >= 0 else {}
                desc = seo.get("description", "")
                bullets = seo.get("bullets", [])
                if not desc:
                    skipped += 1
                    continue

                bullets_html = "".join(f"<li>{b}</li>" for b in bullets[:5])
                body_html = f"<p>{desc}</p><ul>{bullets_html}</ul>"

                async with aiohttp.ClientSession() as s:
                    async with s.put(
                        f"https://api.printify.com/v1/shops/{shop_id}/products/{pid}.json",
                        headers=pf_headers,
                        json={"description": body_html},
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as r:
                        if r.status in (200, 201):
                            updated += 1
                            log.info("Printify SEO updated: %s", title[:50])
                        else:
                            skipped += 1
                            log.debug("Printify SEO skip (%s): %s", r.status, title[:40])

            except Exception as e:
                log.debug("Printify product SEO error: %s", e)
                skipped += 1

    except Exception as e:
        log.debug("printify_seo_blast error: %s", e)

    return {"updated": updated, "skipped": skipped}


async def multi_platform_post(topic: str, offer_url: str = "") -> dict:
    """Postet auf Telegram + LinkedIn + GitHub Pages Blog + IndexNow blast."""
    link = offer_url or DS24_LINK()

    tg_text = (
        f"📢 <b>{topic}</b>\n\n"
        f"Vollautomatisch und 24/7 aktiv — SuperMegaBot macht es möglich.\n\n"
        f"👉 <a href='{link}'>Mehr erfahren</a>"
    )
    li_text = (
        f"{topic}\n\n"
        f"SuperMegaBot automatisiert dein Online-Business komplett — "
        f"Shopify, DS24, Klaviyo, Social Media, SEO.\n\n"
        f"👉 {link}\n\n"
        f"#PassivesEinkommen #OnlineBusiness #Automatisierung #KI #Shopify"
    )

    tg_task     = _tg_send(tg_text)
    li_task     = _linkedin_post(li_text)
    blog_task   = _github_seo_post(topic)
    idx_task    = _indexnow()

    tg, li, blog_url, idx = await asyncio.gather(
        tg_task, li_task, blog_task, idx_task,
        return_exceptions=True,
    )

    result = {
        "telegram":  bool(tg) if not isinstance(tg, Exception) else False,
        "linkedin":  bool(li) if not isinstance(li, Exception) else False,
        "blog_url":  blog_url if isinstance(blog_url, str) else None,
        "indexnow":  int(idx) if not isinstance(idx, Exception) else 0,
    }
    log.info("MultiPlatform post '%s': %s", topic[:40], result)
    return result


# ── Klaviyo Campaign Sender ───────────────────────────────────────────────────

async def send_klaviyo_campaign(subject: str, html_body: str, campaign_name: str = "") -> bool:
    """Sendet eine Klaviyo Email-Kampagne. Nutzt klaviyo_autonomy.create_campaign (mit Mailchimp-Fallback)."""
    try:
        name = campaign_name or f"AutoBlitz {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        from modules.klaviyo_autonomy import create_campaign
        result = await create_campaign(name, subject, html_body)
        ok = result.get("ok", False)
        log.info("Klaviyo campaign '%s': %s via %s", subject[:50], "sent" if ok else "draft", result.get("channel", "?"))
        return ok
    except Exception as e:
        log.debug("Klaviyo campaign error: %s", e)
        return False


async def send_mailchimp_campaign(subject: str, html_body: str) -> bool:
    """Sendet eine Mailchimp-Kampagne an die gesamte Liste."""
    mc_key = os.getenv("MAILCHIMP_API_KEY", "")
    mc_list = os.getenv("MAILCHIMP_LIST_ID", "606e45a6b0")
    mc_server = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")
    if not mc_key:
        return False
    try:
        import aiohttp, base64
        auth = base64.b64encode(f"any:{mc_key}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
        base_url = f"https://{mc_server}.api.mailchimp.com/3.0"

        async with aiohttp.ClientSession() as s:
            async with s.post(f"{base_url}/campaigns", headers=headers,
                json={"type": "regular",
                      "recipients": {"list_id": mc_list},
                      "settings": {"subject_line": subject, "from_name": "Rudolf | AIITEC",
                                   "reply_to": "bullpowersrtkennels@gmail.com",
                                   "title": f"AutoBlitz {datetime.now().strftime('%Y-%m-%d')}"}},
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = await r.json(content_type=None)
            cid = d.get("id", "")
            if not cid:
                return False

            async with s.put(f"{base_url}/campaigns/{cid}/content", headers=headers,
                json={"html": html_body}, timeout=aiohttp.ClientTimeout(total=10)) as r:
                pass

            async with s.post(f"{base_url}/campaigns/{cid}/actions/send", headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                ok = r.status == 204
        log.info("Mailchimp campaign '%s': %s", subject[:50], "sent" if ok else "failed")
        return ok
    except Exception as e:
        log.debug("Mailchimp campaign error: %s", e)
        return False


async def announce_new_products(products: list) -> dict:
    """Nach AliExpress/Printify Import: Telegram + Klaviyo + Mailchimp + IndexNow."""
    if not products:
        return {"ok": False}

    link = DS24_LINK()
    names = ", ".join(p.get("title", p.get("name", "Produkt"))[:30] for p in products[:3])

    tg_text = (
        f"🛒 <b>Neue Produkte im Shop!</b>\n\n"
        f"Gerade importiert: {names}\n\n"
        f"👉 Jetzt ansehen + KI-Income starten: <a href='{link}'>{link}</a>"
    )

    items_html = "".join(
        f"<li>{p.get('title', p.get('name', 'Produkt'))[:60]}</li>"
        for p in products[:5]
    )
    _html_base = (
        f"<html><body style='font-family:Arial;max-width:600px;margin:0 auto;padding:20px'>"
        f"<h2>🛒 Neue Produkte jetzt verfügbar!</h2>"
        f"<p>Wir haben gerade <b>{len(products)} neue Produkte</b> in den Shop geladen:</p>"
        f"<ul>{items_html}</ul>"
        f"<p><a href='{link}' style='background:#7c3aed;color:#fff;padding:12px 24px;"
        f"text-decoration:none;border-radius:6px'>👉 Jetzt entdecken</a></p>"
        f"<hr><p><small>Rudolf | AIITEC | "
    )
    html_klaviyo = _html_base + "<a href='{{ unsubscribe_link }}'>Abmelden</a></small></p></body></html>"
    html_mc      = _html_base + "<a href='*|UNSUB|*'>Abmelden</a></small></p></body></html>"
    subject = f"🛒 {len(products)} neue Produkte — jetzt im Shop!"

    tg, kl, mc, idx = await asyncio.gather(
        _tg_send(tg_text),
        send_klaviyo_campaign(subject, html_klaviyo, f"NewProducts {datetime.now().strftime('%m-%d')}"),
        send_mailchimp_campaign(subject, html_mc),
        _indexnow(),
        return_exceptions=True,
    )

    return {
        "telegram": bool(tg) if not isinstance(tg, Exception) else False,
        "klaviyo":  bool(kl) if not isinstance(kl, Exception) else False,
        "mailchimp": bool(mc) if not isinstance(mc, Exception) else False,
        "indexnow": int(idx) if not isinstance(idx, Exception) else 0,
    }


async def brutus_blast_for_tool(tool_name: str, tool_url: str, keywords: list = None) -> dict:
    """BRUTUS Traffic für ein spezifisches Tool/Modul — postet auf alle Kanäle."""
    try:
        from modules.brutus_traffic_engine import brutus_run
        niche = f"{tool_name} automation {keywords[0] if keywords else '2026'}"
        result = await brutus_run(niche=niche, custom_keywords=keywords)
        return result
    except Exception as e:
        log.debug("BRUTUS blast error for %s: %s", tool_name, e)
        # Fallback: direct Telegram post
        try:
            import aiohttp as _ah
            tg_tok  = os.getenv("TELEGRAM_BOT_TOKEN", "")
            tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
            if tg_tok and tg_chat and tool_url:
                msg = f"🚀 {tool_name}\n\n👉 {tool_url}"
                async with _ah.ClientSession() as s:
                    async with s.post(f"https://api.telegram.org/bot{tg_tok}/sendMessage",
                        json={"chat_id": tg_chat, "text": msg},
                        timeout=_ah.ClientTimeout(total=8)) as r:
                        d = await r.json(content_type=None)
                if d.get("ok"):
                    return {"channels_hit": 1, "content_pieces": 1}
        except Exception:
            pass
        return {"channels_hit": 0, "content_pieces": 0}
