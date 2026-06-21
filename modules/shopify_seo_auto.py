"""
Shopify SEO Auto-Updater
========================
Optimiert automatisch alle Shopify-Produkte mit AI-generierten
SEO-Titeln, Metabeschreibungen und Produkttexten.
Läuft täglich, verarbeitet max. 20 Produkte pro Lauf.
"""
import os
import json
import logging
import hashlib
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ShopifySEO")

SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")
ANTHROPIC       = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
SEO_STATE_FILE = DATA_DIR / "shopify_seo_updated.json"


def _load_updated() -> dict:
    try:
        return json.loads(SEO_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_updated(state: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SEO_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


async def _tg(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


async def get_products_batch(page: int = 1, limit: int = 20) -> list:
    """Fetch products from Shopify."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return []
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/products.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                params={"limit": limit, "fields": "id,title,body_html,vendor,product_type,tags,status"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        return data.get("products", [])
    except Exception as e:
        log.error("Shopify products fetch error: %s", e)
        return []


async def generate_seo_content(product: dict) -> dict | None:
    """Use AI to generate SEO-optimized content for a product."""
    try:
        from modules.ai_client import ai_complete
        title = product.get("title", "")
        product_type = product.get("product_type", "")
        vendor = product.get("vendor", "")
        tags = ", ".join((product.get("tags") or "").split(",")[:5])

        prompt = f"""Erstelle SEO-optimierten Content für dieses Shopify-Produkt auf Deutsch:
Produktname: {title}
Kategorie: {product_type}
Marke: {vendor}
Tags: {tags}

Gib NUR valides JSON zurück (kein anderer Text):
{{
  "seo_title": "60-Zeichen-SEO-Titel mit Hauptkeyword",
  "meta_description": "150-Zeichen-Metabeschreibung mit CTA",
  "body_html": "<p>2-3 Absätze HTML-Produktbeschreibung. Vorteile, Features, Kaufgrund. SEO-optimiert.</p><ul><li>Feature 1</li><li>Feature 2</li><li>Feature 3</li></ul>",
  "tags": "keyword1, keyword2, keyword3, keyword4, keyword5"
}}"""

        raw = await ai_complete(prompt, max_tokens=600)
        if not raw:
            return None
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as e:
        log.warning("SEO gen error for %s: %s", product.get("title"), e)
        return None


async def update_shopify_product(product_id: int, seo: dict) -> bool:
    """Update a Shopify product with SEO content."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return False
    try:
        import aiohttp
        payload = {
            "product": {
                "id": product_id,
                "body_html": seo.get("body_html", ""),
                "tags": seo.get("tags", ""),
                "metafields": [
                    {"namespace": "seo", "key": "title",       "value": seo.get("seo_title", ""),       "type": "single_line_text_field"},
                    {"namespace": "seo", "key": "description", "value": seo.get("meta_description", ""), "type": "single_line_text_field"},
                ],
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.put(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/products/{product_id}.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status in (200, 201):
                    return True
                body = await r.text()
                log.warning("Shopify update %s failed: %s %s", product_id, r.status, body[:100])
                return False
    except Exception as e:
        log.error("Shopify update error: %s", e)
        return False


async def run_seo_batch(batch_size: int = 15) -> dict:
    """
    Main entry: process next batch of un-optimized Shopify products.
    Skips products already updated to avoid re-doing work.
    """
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {"ok": False, "error": "Shopify not configured"}

    updated_state = _load_updated()
    products = await get_products_batch(limit=50)

    if not products:
        return {"ok": False, "error": "No products found"}

    # Filter out already updated
    todo = [p for p in products if str(p["id"]) not in updated_state][:batch_size]

    if not todo:
        return {"ok": True, "message": "All products already SEO-optimized", "count": 0}

    results = {"ok": True, "updated": 0, "failed": 0, "products": []}

    for product in todo:
        pid = product["id"]
        title = product.get("title", "?")

        seo = await generate_seo_content(product)
        if not seo:
            results["failed"] += 1
            continue

        success = await update_shopify_product(pid, seo)
        if success:
            updated_state[str(pid)] = {
                "title": title,
                "updated_at": datetime.now().isoformat(),
                "seo_title": seo.get("seo_title", ""),
            }
            results["updated"] += 1
            results["products"].append(title[:40])
            log.info("SEO updated: %s", title)
        else:
            results["failed"] += 1

    _save_updated(updated_state)

    if results["updated"] > 0:
        product_list = "\n".join(f"• {p}" for p in results["products"][:10])
        await _tg(
            f"🔍 *Shopify SEO Auto-Update*\n"
            f"✅ {results['updated']} Produkte optimiert\n\n"
            f"{product_list}"
        )

    return results


async def reset_seo_state():
    """Reset state so all products get re-optimized."""
    SEO_STATE_FILE.unlink(missing_ok=True)
    return {"ok": True, "message": "SEO state reset — all products will be re-optimized"}


async def auto_publish_blog_post(keyword: str, shop_domain: str = "") -> dict:
    """Auto-generate and publish an SEO blog post for a keyword to Shopify."""
    import os
    from modules.ai_client import ai_complete
    
    domain = shop_domain or os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    affiliate = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
    
    if not domain or not token:
        return {"ok": False, "reason": "SHOPIFY_SHOP_DOMAIN or SHOPIFY_ADMIN_API_TOKEN not set"}
    
    # Generate blog content via AI (or use template fallback)
    title = await ai_complete(f"Write a catchy SEO blog post title for keyword: '{keyword}'. Max 70 chars.", max_tokens=80)
    if not title:
        title = f"Top Produkte für {keyword} — AIITEC Shop 2026"
    
    body_prompt = f"Write a 400-word SEO blog post about '{keyword}' for an e-commerce store. Include product recommendations, tips, and a CTA. Mention AIITEC brand."
    body_html = await ai_complete(body_prompt, max_tokens=600)
    if not body_html:
        body_html = f"<h2>{title}</h2><p>Entdecke die besten Produkte für {keyword} in unserem AIITEC Shop. Qualität, Innovation und hervorragender Service warten auf dich.</p><p><a href='{affiliate}'>Jetzt entdecken →</a></p>"
    else:
        body_html = f"<h2>{title}</h2>{body_html}<p><a href='{affiliate}'>Jetzt einkaufen →</a></p>"
    
    import aiohttp
    version = os.getenv("SHOPIFY_API_VERSION", "2024-01")
    url = f"https://{domain}/admin/api/{version}/blogs/{{blog_id}}/articles.json"
    
    # Get first blog ID
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{domain}/admin/api/{version}/blogs.json",
                headers={"X-Shopify-Access-Token": token},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                blogs = (await r.json()).get("blogs", [])
                if not blogs:
                    return {"ok": False, "reason": "No Shopify blogs found"}
                blog_id = blogs[0]["id"]
            
            async with s.post(
                f"https://{domain}/admin/api/{version}/blogs/{blog_id}/articles.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json={"article": {"title": title.strip('"').strip(), "body_html": body_html, "tags": keyword}},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                if r.status == 201:
                    art = (await r.json()).get("article", {})
                    return {"ok": True, "article_id": art.get("id"), "title": art.get("title"), "keyword": keyword}
                return {"ok": False, "status": r.status, "error": await r.text()}
    except Exception as e:
        return {"ok": False, "error": str(e)}
