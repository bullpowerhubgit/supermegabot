"""
Shopify Max Tuner — 10-function Shopify conversion machine.
All functions autonomous, scheduled, no human input needed.
"""
import os
import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", os.getenv("SHOPIFY_ACCESS_TOKEN", ""))
SHOPIFY_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-10")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

_BASE = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}"


# ── Low-level helpers ─────────────────────────────────────────────────────────

async def _shopify_get(path: str, params: str = "") -> dict:
    try:
        import aiohttp
        url = f"{_BASE}/{path}{'?' + params if params else ''}"
        headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.get(url, headers=headers) as r:
                return await r.json()
    except Exception as e:
        return {"error": str(e)}


async def _shopify_put(path: str, data: dict) -> dict:
    try:
        import aiohttp
        url = f"{_BASE}/{path}"
        headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.put(url, headers=headers, json=data) as r:
                return await r.json()
    except Exception as e:
        return {"error": str(e)}


async def _shopify_post(path: str, data: dict) -> dict:
    try:
        import aiohttp
        url = f"{_BASE}/{path}"
        headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(url, headers=headers, json=data) as r:
                return await r.json()
    except Exception as e:
        return {"error": str(e)}


async def _claude(prompt: str, max_tokens: int = 1024) -> str:
    if not ANTHROPIC_KEY:
        return ""
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": max_tokens,
                      "messages": [{"role": "user", "content": prompt}]},
            ) as r:
                data = await r.json()
                return data.get("content", [{}])[0].get("text", "")
    except Exception as e:
        logger.error(f"Claude error: {e}")
        return ""


async def _telegram(msg: str) -> None:
    if not TELEGRAM_BOT or not TELEGRAM_CHAT:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg[:4096]},
            )
    except Exception:
        pass


# ── 1. PRODUCT SEO MAXIMIZER ──────────────────────────────────────────────────

async def optimize_all_products_seo() -> dict:
    """Fetch all products, AI-optimize titles/descriptions/tags, update via API."""
    result = await _shopify_get("products.json", "limit=250&fields=id,title,body_html,tags,images")
    products = result.get("products", [])
    if not products:
        return {"optimized": 0, "error": result.get("error", "no products")}

    updated = 0
    errors = 0
    for p in products[:10]:  # batch 10 per run to respect rate limits
        try:
            prompt = (
                f"Product: {p['title']}\nCurrent description: {p.get('body_html','')[:300]}\n\n"
                "Return JSON with keys: title (keyword-rich, max 60 chars, German), "
                "body_html (300+ words, HTML, benefits-focused, German), "
                "tags (comma-separated list of 15 SEO tags, German+English). "
                "JSON only, no markdown."
            )
            raw = await _claude(prompt, max_tokens=800)
            try:
                optimized = json.loads(raw.strip().strip("```json").strip("```"))
            except Exception:
                continue
            update_data = {"product": {
                "id": p["id"],
                "title": optimized.get("title", p["title"])[:60],
                "body_html": optimized.get("body_html", p.get("body_html", "")),
                "tags": optimized.get("tags", p.get("tags", "")),
            }}
            r = await _shopify_put(f"products/{p['id']}.json", update_data)
            if "product" in r:
                updated += 1
            else:
                errors += 1
        except Exception as e:
            logger.error(f"SEO optimize product {p['id']}: {e}")
            errors += 1
        await asyncio.sleep(0.6)  # Shopify rate limit: 2 req/s

    return {"optimized": updated, "errors": errors, "total": len(products)}


# ── 2. AUTO PRODUCT DESCRIPTION WRITER ───────────────────────────────────────

async def rewrite_product_descriptions(style: str = "conversion") -> dict:
    """Rewrite all product descriptions in chosen style."""
    style_prompts = {
        "conversion": "sales-focused, benefit-first, urgency, German",
        "luxury": "premium, exclusive, aspirational tone, German",
        "minimal": "clean, concise, key facts only, German",
        "story": "narrative, emotional, customer journey, German",
        "technical": "specs-first, detailed, expert audience, German",
    }
    tone = style_prompts.get(style, style_prompts["conversion"])
    result = await _shopify_get("products.json", "limit=50&fields=id,title,body_html")
    products = result.get("products", [])
    updated = 0
    for p in products[:5]:
        prompt = (
            f"Product: {p['title']}\nStyle: {tone}\n"
            "Write a complete product description (min 250 words) as HTML. "
            "Structure: <h2>benefit headline</h2>, 3 <strong>key benefits</strong>, "
            "use cases, <h3>FAQ</h3> with 3 Q&A, strong CTA. German only. HTML only."
        )
        html = await _claude(prompt, max_tokens=1200)
        if html:
            await _shopify_put(f"products/{p['id']}.json",
                               {"product": {"id": p["id"], "body_html": html}})
            updated += 1
        await asyncio.sleep(0.7)
    return {"rewritten": updated, "style": style}


# ── 3. COLLECTION ORGANIZER ───────────────────────────────────────────────────

async def auto_organize_collections() -> dict:
    """Create AI-suggested collections and assign products."""
    products_r = await _shopify_get("products.json", "limit=250&fields=id,title,product_type,tags")
    products = products_r.get("products", [])
    colls_r = await _shopify_get("custom_collections.json", "limit=50&fields=id,title")
    existing = {c["title"].lower() for c in colls_r.get("custom_collections", [])}

    product_list = "\n".join(f"- {p['title']} (type: {p.get('product_type','')}, tags: {p.get('tags','')})"
                             for p in products[:50])
    prompt = (
        f"Products:\n{product_list}\n\n"
        "Suggest 5 new collection names in German that don't exist yet. "
        f"Existing: {', '.join(list(existing)[:20])}. "
        "Return JSON array: [{\"title\": \"...\", \"description\": \"...\", \"product_keywords\": [\"kw1\",\"kw2\"]}]. "
        "JSON only."
    )
    raw = await _claude(prompt, max_tokens=600)
    created = 0
    try:
        suggestions = json.loads(raw.strip().strip("```json").strip("```"))
        for s in suggestions:
            if s["title"].lower() not in existing:
                r = await _shopify_post("custom_collections.json", {
                    "custom_collection": {
                        "title": s["title"],
                        "body_html": s.get("description", ""),
                        "published": True,
                    }
                })
                if "custom_collection" in r:
                    created += 1
                await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"Collection organize: {e}")
    return {"created_collections": created}


# ── 4. REVIEW AUTOMATION ──────────────────────────────────────────────────────

async def request_reviews_automation() -> dict:
    """Email review requests to customers 7 days after fulfilled order."""
    since = (datetime.utcnow() - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = (datetime.utcnow() - timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = await _shopify_get(
        "orders.json",
        f"status=any&fulfillment_status=fulfilled&created_at_min={since}&created_at_max={until}&limit=50&fields=id,email,line_items,customer"
    )
    orders = result.get("orders", [])
    sent = 0
    for o in orders:
        email = o.get("email", "")
        if not email:
            continue
        name = (o.get("customer") or {}).get("first_name", "Kunde")
        product = (o.get("line_items") or [{}])[0].get("title", "Ihr Produkt")
        try:
            from modules.email_brain import send_email
            subject = f"Wie war Ihre Erfahrung mit {product}?"
            body = (
                f"Hallo {name},\n\n"
                f"wir hoffen, Sie sind begeistert von '{product}'!\n\n"
                "Würden Sie uns kurz mitteilen, wie Ihre Erfahrung war? "
                "Ihre Bewertung hilft anderen Kunden und uns, besser zu werden.\n\n"
                "⭐ Jetzt bewerten: https://bullpower-hub-portal.netlify.app/review\n\n"
                "Herzlichen Dank!\nIhr BullPower Hub Team"
            )
            await send_email(to=email, subject=subject, body=body)
            sent += 1
        except Exception as e:
            logger.error(f"Review email to {email}: {e}")
        await asyncio.sleep(0.5)
    return {"review_requests_sent": sent, "orders_checked": len(orders)}


# ── 5. INVENTORY INTELLIGENCE ─────────────────────────────────────────────────

async def manage_inventory_ai() -> dict:
    """Detect low stock, predict stockouts, alert via Telegram."""
    result = await _shopify_get(
        "products.json",
        "limit=250&fields=id,title,variants"
    )
    products = result.get("products", [])
    alerts = []
    for p in products:
        for v in p.get("variants", []):
            qty = v.get("inventory_quantity", 0)
            if v.get("inventory_management") == "shopify" and qty is not None:
                if qty <= 3:
                    alerts.append(f"⚠️ LOW STOCK: {p['title']} — nur noch {qty} Stück!")
                elif qty == 0:
                    alerts.append(f"🚨 OUT OF STOCK: {p['title']} — sofort nachbestellen!")
    if alerts:
        msg = "📦 Lagerstand-Alert:\n" + "\n".join(alerts[:20])
        await _telegram(msg)
    return {"low_stock_alerts": len(alerts), "products_checked": len(products)}


# ── 6. PRICE OPTIMIZATION ─────────────────────────────────────────────────────

async def optimize_shopify_pricing() -> dict:
    """Apply psychological pricing and auto-flag slow movers for flash sales."""
    result = await _shopify_get("products.json", "limit=250&fields=id,title,variants")
    products = result.get("products", [])
    updated = 0
    for p in products:
        for v in p.get("variants", []):
            try:
                price = float(v.get("price", 0))
                if price <= 0:
                    continue
                # Psychological pricing: round to .99
                new_price = float(int(price)) - 0.01 if price == int(price) else price
                # Round up to nearest .99 if not already
                if not str(price).endswith(".99") and not str(price).endswith(".95"):
                    new_price = float(int(price) + 0.99) if price < int(price) + 0.5 else float(int(price) - 0.01)
                    new_price = max(new_price, 0.99)
                if abs(new_price - price) > 0.005:
                    r = await _shopify_put(f"variants/{v['id']}.json", {
                        "variant": {"id": v["id"], "price": f"{new_price:.2f}"}
                    })
                    if "variant" in r:
                        updated += 1
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Price optimize variant {v.get('id')}: {e}")
    return {"prices_optimized": updated}


# ── 7. ABANDONED CHECKOUT RECOVERY ───────────────────────────────────────────

async def recover_abandoned_checkouts() -> dict:
    """Fetch open checkouts and trigger multi-channel recovery."""
    since = (datetime.utcnow() - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = await _shopify_get(
        "checkouts.json",
        f"status=open&created_at_min={since}&created_at_max={until}&limit=50"
    )
    checkouts = result.get("checkouts", [])
    recovered = 0
    for c in checkouts:
        email = c.get("email", "")
        if not email:
            continue
        name = (c.get("billing_address") or {}).get("first_name", "Kunde")
        total = c.get("total_price", "0")
        items = ", ".join(li.get("title", "") for li in (c.get("line_items") or [])[:2])
        try:
            from modules.email_brain import send_email
            subject = f"🛒 {name}, du hast etwas vergessen!"
            body = (
                f"Hallo {name},\n\n"
                f"Du hast noch Artikel im Warenkorb: {items}\n"
                f"Gesamtbetrag: €{total}\n\n"
                "Schließe deinen Kauf ab und spare 5% mit Code: COMEBACK5\n"
                "(Gültig für 2 Stunden)\n\n"
                "➡️ Zum Warenkorb: https://autopilot-store-suite-fmbka.myshopify.com/cart\n\n"
                "BullPower Hub Team"
            )
            await send_email(to=email, subject=subject, body=body)
            recovered += 1
        except Exception as e:
            logger.error(f"Cart recovery email {email}: {e}")
        await asyncio.sleep(0.3)
    return {"recovery_emails_sent": recovered, "open_checkouts": len(checkouts)}


# ── 8. SHOPIFY BLOG AUTO-PUBLISHER ───────────────────────────────────────────

async def publish_to_shopify_blog(article: dict) -> dict:
    """Publish a pre-generated article dict to the Shopify blog."""
    blogs_r = await _shopify_get("blogs.json", "limit=1&fields=id")
    blogs = blogs_r.get("blogs", [])
    if not blogs:
        return {"error": "no blog found"}
    blog_id = blogs[0]["id"]
    payload = {
        "article": {
            "title": article.get("title", "Neuer Artikel"),
            "body_html": article.get("content_html", article.get("body_html", "")),
            "author": "BullPower Hub",
            "tags": article.get("tags", "shopify,automation,ecommerce"),
            "published": True,
            "published_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    }
    result = await _shopify_post(f"blogs/{blog_id}/articles.json", payload)
    art = result.get("article", {})
    if art.get("id"):
        url = f"https://{SHOPIFY_DOMAIN}/blogs/news/{art.get('handle','')}"
        # Ping Google
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                await s.get(f"https://www.google.com/ping?sitemap={url}")
        except Exception:
            pass
        return {"published": True, "article_id": art["id"], "url": url}
    return {"error": result.get("errors", "unknown")}


async def auto_publish_seo_blog() -> dict:
    """Generate and publish one SEO article to Shopify blog."""
    topics = [
        "Shopify SEO Tipps für 2026",
        "E-Commerce Automation mit KI",
        "Mehr Umsatz im Onlineshop",
        "Dropshipping für Anfänger",
        "Shopify vs WooCommerce 2026",
    ]
    import random
    topic = random.choice(topics)
    prompt = (
        f"Schreibe einen SEO-optimierten Blogartikel über: {topic}\n"
        "Format: <h1>Titel</h1> dann <h2>Abschnitte</h2> mit Text. Min 800 Wörter. "
        "Sprache: Deutsch. Enthält 1x CTA zu https://bullpower-hub-portal.netlify.app"
    )
    html = await _claude(prompt, max_tokens=2000)
    if not html:
        return {"error": "claude returned empty"}
    return await publish_to_shopify_blog({
        "title": topic,
        "content_html": html,
        "tags": "seo,shopify,automation",
    })


# ── 9. UPSELL WIDGETS ─────────────────────────────────────────────────────────

async def inject_upsell_widgets() -> dict:
    """Generate upsell metafield HTML and save to top products."""
    result = await _shopify_get("products.json", "limit=10&fields=id,title,variants")
    products = result.get("products", [])
    injected = 0
    trust_badge_html = (
        '<div class="trust-badges" style="display:flex;gap:12px;margin:16px 0;">'
        '<span>🔒 Sicherer Checkout</span>'
        '<span>🚚 Schneller Versand</span>'
        '<span>↩️ 30 Tage Rückgabe</span>'
        '</div>'
    )
    for p in products[:5]:
        price = float((p.get("variants") or [{}])[0].get("price", 0))
        upsell_html = (
            f'{trust_badge_html}'
            f'<div class="volume-discount" style="background:#f5f5f5;padding:12px;border-radius:8px;margin:12px 0;">'
            f'<strong>💰 Mengenrabatt:</strong><br>'
            f'2x = 5% Rabatt | 3x = 10% Rabatt | 5x = 15% Rabatt'
            f'</div>'
            f'<div class="urgency" style="color:#c00;font-weight:bold;">'
            f'⏰ Nur noch wenige Stück verfügbar!</div>'
        )
        r = await _shopify_post(f"products/{p['id']}/metafields.json", {
            "metafield": {
                "namespace": "bullpower",
                "key": "upsell_widget",
                "value": upsell_html,
                "type": "multi_line_text_field",
            }
        })
        if "metafield" in r:
            injected += 1
        await asyncio.sleep(0.5)
    return {"widgets_injected": injected}


# ── 10. SHOPIFY ANALYTICS INTELLIGENCE ───────────────────────────────────────

async def shopify_daily_intelligence() -> dict:
    """Pull Shopify analytics, generate Telegram briefing."""
    since_7d = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    orders_r = await _shopify_get(
        "orders.json",
        f"status=any&created_at_min={since_7d}&limit=250&fields=id,total_price,line_items,created_at"
    )
    orders = orders_r.get("orders", [])
    revenue_7d = sum(float(o.get("total_price", 0)) for o in orders)
    order_count = len(orders)
    aov = revenue_7d / order_count if order_count else 0

    # Top products by order count
    product_counts: dict = {}
    for o in orders:
        for li in o.get("line_items", []):
            t = li.get("title", "")
            product_counts[t] = product_counts.get(t, 0) + 1
    top_products = sorted(product_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_str = "\n".join(f"  {i+1}. {t} ({c}x)" for i, (t, c) in enumerate(top_products))

    msg = (
        f"📊 Shopify Tagesbericht\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Umsatz (7 Tage): €{revenue_7d:.2f}\n"
        f"📦 Bestellungen: {order_count}\n"
        f"🛒 Ø Bestellwert: €{aov:.2f}\n\n"
        f"🏆 Top Produkte:\n{top_str}\n\n"
        f"🤖 BullPower Shopify Intelligence"
    )
    await _telegram(msg)
    return {
        "revenue_7d": revenue_7d,
        "orders_7d": order_count,
        "aov": round(aov, 2),
        "top_products": top_products[:3],
    }


# ── Scheduler task wrappers ───────────────────────────────────────────────────

async def task_shopify_seo_optimize() -> str:
    r = await optimize_all_products_seo()
    return f"SEO: {r.get('optimized',0)} products optimized"

async def task_shopify_cart_recovery() -> str:
    r = await recover_abandoned_checkouts()
    return f"Cart recovery: {r.get('recovery_emails_sent',0)} emails sent"

async def task_shopify_pricing() -> str:
    r = await optimize_shopify_pricing()
    return f"Pricing: {r.get('prices_optimized',0)} prices set to .99"

async def task_shopify_intelligence() -> str:
    r = await shopify_daily_intelligence()
    return f"Intelligence: €{r.get('revenue_7d',0):.2f} revenue 7d, {r.get('orders_7d',0)} orders"

async def task_shopify_blog_publish() -> str:
    r = await auto_publish_seo_blog()
    return f"Blog: {'published ' + r.get('url','') if r.get('published') else r.get('error','failed')}"

async def task_shopify_inventory() -> str:
    r = await manage_inventory_ai()
    return f"Inventory: {r.get('low_stock_alerts',0)} alerts sent"

async def task_shopify_reviews() -> str:
    r = await request_reviews_automation()
    return f"Reviews: {r.get('review_requests_sent',0)} review requests sent"
