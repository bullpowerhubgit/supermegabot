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
SHOPIFY_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")
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


async def get_products_page(since_id: int = 0, limit: int = 250) -> tuple[list, int]:
    """Fetch one page of products using since_id cursor. Returns (products, last_id)."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return [], 0
    try:
        import aiohttp
        params = {
            "limit": limit,
            "since_id": since_id,
            "fields": "id,title,body_html,vendor,product_type,tags,status",
            "status": "active",
        }
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/products.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                data = await r.json(content_type=None)
        products = data.get("products", [])
        last_id = products[-1]["id"] if products else 0
        return products, last_id
    except Exception as e:
        log.error("Shopify products fetch error: %s", e)
        return [], 0


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
                # Echte Shopify SEO-Felder (erscheinen in Google-Suchergebnissen)
                "metafields_global_title_tag": seo.get("seo_title", "")[:70],
                "metafields_global_description_tag": seo.get("meta_description", "")[:155],
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


async def run_seo_batch(batch_size: int = 100) -> dict:
    """
    Main entry: process next batch of un-optimized Shopify products.
    Uses since_id cursor to iterate through ALL products (not just first 50).
    Batch size 100 @ every 2h = 1200/day → all 10k products in ~8 days.
    """
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {"ok": False, "error": "Shopify not configured"}

    updated_state = _load_updated()
    # Resume from last cursor position
    since_id = updated_state.get("__cursor__", 0)

    products, last_id = await get_products_page(since_id=since_id, limit=250)

    if not products:
        # Reached end — reset cursor for next full cycle
        updated_state["__cursor__"] = 0
        updated_state["__cycle_completed__"] = datetime.now().isoformat()
        _save_updated(updated_state)
        total = len([k for k in updated_state if not k.startswith("__")])
        log.info("SEO cycle complete — %d products optimized total, restarting", total)
        return {"ok": True, "message": f"Full cycle done ({total} products) — cursor reset", "count": 0}

    # Skip already updated in this cycle, take batch
    todo = [p for p in products if str(p["id"]) not in updated_state][:batch_size]

    if not todo:
        # All on this page already done — advance cursor
        updated_state["__cursor__"] = last_id
        _save_updated(updated_state)
        return {"ok": True, "message": "Page already done, cursor advanced", "count": 0}

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
        else:
            results["failed"] += 1

    # Advance cursor past last processed product
    updated_state["__cursor__"] = last_id
    _save_updated(updated_state)

    total_done = len([k for k in updated_state if not k.startswith("__")])
    log.info("SEO batch: %d updated, %d failed, cursor=%d, total=%d",
             results["updated"], results["failed"], last_id, total_done)

    if results["updated"] > 0:
        product_list = "\n".join(f"• {p}" for p in results["products"][:10])
        await _tg(
            f"🔍 <b>Shopify SEO Auto-Update</b>\n"
            f"✅ {results['updated']} Produkte optimiert\n"
            f"📊 Gesamt: {total_done} | Cursor: {last_id}\n\n"
            f"{product_list}"
        )

    results["total_done"] = total_done
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
    token = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    affiliate = os.getenv("DS24_AFFILIATE_LINK", "")
    
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
    version = os.getenv("SHOPIFY_API_VERSION", "2026-04")
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
