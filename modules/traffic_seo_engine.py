#!/usr/bin/env python3
"""
Traffic & SEO Engine — vollautonomer Content + SEO:
  - AI-generierte Blog-Posts für DS24 Produkte
  - Shopify Produkt-SEO Optimierung (Titles, Meta, Tags)
  - YouTube Beschreibungen
  - Social Media Posts (Telegram, Facebook, Pinterest wenn verfügbar)
  Läuft alle 6h via Scheduler.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("TrafficSEO")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY    = os.getenv("OPENAI_API_KEY", "")


async def _ai_generate(prompt: str, max_tokens: int = 800) -> str:
    """Generate content via Claude. Falls back to OpenAI if needed."""
    if ANTHROPIC_KEY:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": max_tokens,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    data = await resp.json(content_type=None)
                    return data["content"][0]["text"]
        except Exception as exc:
            log.warning("Claude generation failed: %s", exc)

    if OPENAI_KEY:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o-mini",
                        "max_tokens": max_tokens,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    data = await resp.json(content_type=None)
                    return data["choices"][0]["message"]["content"]
        except Exception as exc:
            log.warning("OpenAI generation failed: %s", exc)

    return ""


async def generate_seo_content_for_product(product_name: str, product_desc: str = "") -> dict:
    """Generate SEO-optimized content package for a DS24/Shopify product."""
    prompt = f"""Du bist ein SEO-Experte und Content-Marketer. Erstelle für dieses Produkt ein komplettes SEO-Paket auf Deutsch:

Produkt: {product_name}
{f'Beschreibung: {product_desc}' if product_desc else ''}

Erstelle im JSON-Format:
{{
  "seo_title": "Optimierter Title Tag (50-60 Zeichen, Keyword vorne)",
  "meta_description": "Meta Description (150-160 Zeichen, Call-to-Action)",
  "h1": "H1 Überschrift",
  "blog_intro": "Einleitungsabsatz für Blog-Post (150 Wörter)",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "social_post": "Social Media Post (150 Zeichen) mit Hashtags",
  "youtube_description": "YouTube Video Beschreibung (200 Wörter)",
  "email_subject": "Email Betreff (A/B Test Variante)",
  "cta": "Call-to-Action Text"
}}

Nur JSON zurückgeben, kein anderer Text."""

    raw = await _ai_generate(prompt, max_tokens=1200)
    try:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        log.warning("SEO content parse failed, raw: %s", raw[:200])
        return {}


async def optimize_ds24_products_seo() -> list:
    """Fetch DS24 products and generate SEO content for each."""
    from modules.digistore24_automation import get_products
    products = await get_products()
    results = []

    for p in products[:5]:  # max 5 per run to save API costs
        name = p.get("name") or p.get("product_name") or ""
        desc = p.get("description") or p.get("short_description") or ""
        if not name:
            continue

        log.info("Generating SEO for DS24 product: %s", name)
        seo = await generate_seo_content_for_product(name, desc)
        if seo:
            result = {"product": name, "seo": seo, "generated_at": datetime.now(timezone.utc).isoformat()}
            results.append(result)

    if results:
        out = DATA_DIR / "ds24_seo_content.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
        log.info("DS24 SEO content saved: %d products", len(results))

    return results


async def optimize_shopify_seo_auto() -> dict:
    """AI-optimize Shopify product titles, descriptions, tags automatically."""
    shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    shop_token  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    api_ver     = os.getenv("SHOPIFY_API_VERSION", "2024-10")

    if not shop_domain or not shop_token:
        return {"error": "Shopify not configured"}

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url = f"https://{shop_domain}/admin/api/{api_ver}/products.json?limit=10&fields=id,title,body_html,tags"
            async with session.get(url, headers={"X-Shopify-Access-Token": shop_token},
                                   timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json(content_type=None)

        products = data.get("products", [])
        updated = 0

        for p in products:
            title = p.get("title", "")
            if not title or len(title) > 60:
                continue

            seo = await generate_seo_content_for_product(title, p.get("body_html", "")[:300])
            if not seo:
                continue

            update_payload = {}
            if seo.get("seo_title"):
                update_payload["metafields_global_title_tag"] = seo["seo_title"]
            if seo.get("meta_description"):
                update_payload["metafields_global_description_tag"] = seo["meta_description"]
            if seo.get("keywords"):
                existing_tags = [t.strip() for t in p.get("tags", "").split(",") if t.strip()]
                new_tags = list(set(existing_tags + seo["keywords"][:3]))
                update_payload["tags"] = ", ".join(new_tags)

            if not update_payload:
                continue

            patch_url = f"https://{shop_domain}/admin/api/{api_ver}/products/{p['id']}.json"
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    patch_url,
                    headers={"X-Shopify-Access-Token": shop_token, "Content-Type": "application/json"},
                    json={"product": update_payload},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        updated += 1
                        log.info("Shopify SEO updated: %s", title)

        return {"products_updated": updated, "total_found": len(products)}

    except Exception as exc:
        log.error("Shopify SEO error: %s", exc)
        return {"error": str(exc)}


async def post_content_to_telegram(content: dict):
    """Post generated SEO content as Telegram message for review."""
    try:
        from modules.notify_hub import send_telegram
        product = content.get("product", "")
        seo = content.get("seo", {})
        msg = (
            f"🔍 *SEO Content generiert*\n\n"
            f"Produkt: {product}\n"
            f"Title: {seo.get('seo_title','')}\n"
            f"Keywords: {', '.join(seo.get('keywords',[])[:3])}\n\n"
            f"📱 Social: {seo.get('social_post','')}"
        )
        await send_telegram(msg)
    except Exception as exc:
        log.warning("Telegram post failed: %s", exc)


async def run_full_traffic_seo() -> dict:
    """Full run: DS24 SEO + Shopify SEO + Telegram notifications."""
    log.info("Starting full traffic/SEO automation run")

    ds24_results = await optimize_ds24_products_seo()
    for r in ds24_results:
        await post_content_to_telegram(r)

    shopify_result = await optimize_shopify_seo_auto()

    return {
        "ds24_products_optimized": len(ds24_results),
        "shopify_result": shopify_result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
