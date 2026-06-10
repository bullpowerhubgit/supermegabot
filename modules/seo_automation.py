#!/usr/bin/env python3
"""SEO Automation — Vollautomatische SEO-Optimierung für Shopify"""
import asyncio
import html as _html_escape_module
import json
import logging
import os
from typing import Dict, List

log = logging.getLogger("SEOAutomation")

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

# Minimum character thresholds for "good" SEO
_MIN_TITLE_LEN        = 30
_MAX_TITLE_LEN        = 70
_MIN_DESC_LEN         = 150
_MIN_TAGS             = 3
_MIN_META_DESC_LEN    = 50

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _shopify_rest_patch(endpoint: str, payload: Dict) -> Dict:
    """
    PATCH a Shopify Admin REST endpoint.
    e.g. endpoint = "products/12345678.json"
    """
    from modules.shopify_client import _get_best_token, _store_url, _client_session  # type: ignore
    auth    = await _get_best_token()
    url     = f"{_store_url()}/admin/api/2024-10/{endpoint}"
    headers = {"Content-Type": "application/json", **auth}
    if not HAS_AIOHTTP:
        log.error("aiohttp not installed — cannot PATCH Shopify")
        return {"error": "aiohttp not installed"}
    try:
        async with _client_session(20) as session:
            async with session.patch(url, json=payload, headers=headers) as resp:
                return await resp.json(content_type=None)
    except Exception as exc:
        log.error("Shopify PATCH %s failed: %s", endpoint, exc)
        return {"error": str(exc)}


def _extract_numeric_id(gid: str) -> str:
    """Convert Shopify GID 'gid://shopify/Product/12345' → '12345'."""
    if gid.startswith("gid://"):
        return gid.rstrip("/").split("/")[-1]
    return gid


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def optimize_all_shopify_products(limit: int = 50) -> Dict:
    """
    Fetch up to *limit* Shopify products and generate SEO copy for each one
    that has a missing or short description. Updates the product via REST.

    Returns:
        {processed: int, updated: int, skipped: int, errors: List[str]}
    """
    from modules.shopify_client import get_products  # type: ignore
    from modules.ai_content_pipeline import generate_product_seo  # type: ignore

    processed = 0
    updated   = 0
    skipped   = 0
    errors: List[str] = []

    try:
        products = await get_products(limit=limit)
    except Exception as exc:
        log.error("Could not fetch Shopify products: %s", exc)
        return {"processed": 0, "updated": 0, "skipped": 0,
                "errors": [f"Fetch failed: {exc}"]}

    tasks = []
    for product in products:
        gid         = product.get("id", "")
        numeric_id  = _extract_numeric_id(gid)
        title       = product.get("title", "")
        tags        = product.get("tags", [])
        tags_str    = ", ".join(tags) if isinstance(tags, list) else str(tags)
        price_range = product.get("priceRangeV2", {})
        min_price   = (price_range.get("minVariantPrice", {}).get("amount", "0")
                       if isinstance(price_range, dict) else "0")
        category    = product.get("productType", "")

        product_dict = {
            "title":       title,
            "description": "",  # GraphQL basic query doesn't include body; treat as empty
            "price":       min_price,
            "category":    category,
        }
        tasks.append((numeric_id, title, tags_str, product_dict))

    # Process up to 5 concurrently to avoid hammering Ollama
    semaphore = asyncio.Semaphore(5)

    async def _process_one(numeric_id: str, title: str, tags_str: str,
                            product_dict: Dict) -> None:
        nonlocal processed, updated, skipped

        processed += 1
        # Skip if title is already long and there are tags
        tag_count = len([t for t in tags_str.split(",") if t.strip()])
        if len(title) >= _MIN_TITLE_LEN and tag_count >= _MIN_TAGS:
            log.debug("Skipping product %s — already has SEO content", numeric_id)
            skipped += 1
            return

        async with semaphore:
            try:
                seo = await generate_product_seo(product_dict)
            except Exception as exc:
                log.error("SEO generation failed for product %s: %s", numeric_id, exc)
                errors.append(f"Product {numeric_id}: SEO generation failed — {exc}")
                return

        # Build the REST update payload
        update_payload: Dict = {"product": {}}
        if seo.get("title") and len(seo["title"]) > len(title):
            update_payload["product"]["title"] = seo["title"]
        if seo.get("description"):
            update_payload["product"]["body_html"] = seo["description"]
        if seo.get("meta_description"):
            update_payload["product"]["metafields_global_description_tag"] = (
                seo["meta_description"]
            )
        if seo.get("tags"):
            existing_tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            merged_tags   = list(dict.fromkeys(existing_tags + seo["tags"]))
            update_payload["product"]["tags"] = ", ".join(merged_tags)

        if len(update_payload["product"]) == 0:
            skipped += 1
            return

        result = await _shopify_rest_patch(f"products/{numeric_id}.json", update_payload)
        if "error" in result or "errors" in result:
            err_msg = result.get("error") or str(result.get("errors"))
            log.warning("Shopify update failed for %s: %s", numeric_id, err_msg)
            errors.append(f"Product {numeric_id}: update failed — {err_msg}")
        else:
            log.info("SEO updated for product %s (%s)", numeric_id, title)
            updated += 1

    await asyncio.gather(*[
        _process_one(nid, t, tags, pd) for nid, t, tags, pd in tasks
    ])

    return {
        "processed": processed,
        "updated":   updated,
        "skipped":   skipped,
        "errors":    errors,
    }


async def optimize_single_product(product_id: str) -> Dict:
    """
    Fetch a single product by ID and run SEO optimisation on it.

    Args:
        product_id: numeric Shopify product ID or full GID

    Returns:
        {processed: int, updated: int, skipped: int, errors: List[str]}
    """
    from modules.shopify_client import graphql  # type: ignore
    from modules.ai_content_pipeline import generate_product_seo  # type: ignore

    numeric_id = _extract_numeric_id(product_id)
    gid        = f"gid://shopify/Product/{numeric_id}"

    query = """
    query GetProduct($id: ID!) {
        product(id: $id) {
            id title tags productType
            priceRangeV2 { minVariantPrice { amount currencyCode } }
        }
    }
    """
    try:
        result = await graphql(query, {"id": gid})
        product = result.get("data", {}).get("product")
        if not product:
            return {"processed": 0, "updated": 0, "skipped": 0,
                    "errors": [f"Product {product_id} not found"]}
    except Exception as exc:
        return {"processed": 0, "updated": 0, "skipped": 0,
                "errors": [f"Fetch failed: {exc}"]}

    title       = product.get("title", "")
    tags        = product.get("tags", [])
    tags_str    = ", ".join(tags) if isinstance(tags, list) else str(tags)
    price_range = product.get("priceRangeV2", {})
    min_price   = (price_range.get("minVariantPrice", {}).get("amount", "0")
                   if isinstance(price_range, dict) else "0")
    category    = product.get("productType", "")

    product_dict = {
        "title":       title,
        "description": "",
        "price":       min_price,
        "category":    category,
    }

    tag_count = len([t for t in tags_str.split(",") if t.strip()])
    if len(title) >= _MIN_TITLE_LEN and tag_count >= _MIN_TAGS:
        return {"processed": 1, "updated": 0, "skipped": 1, "errors": []}

    try:
        seo = await generate_product_seo(product_dict)
    except Exception as exc:
        return {"processed": 1, "updated": 0, "skipped": 0,
                "errors": [f"SEO generation failed: {exc}"]}

    update_payload: Dict = {"product": {}}
    if seo.get("title") and len(seo["title"]) > len(title):
        update_payload["product"]["title"] = seo["title"]
    if seo.get("description"):
        update_payload["product"]["body_html"] = seo["description"]
    if seo.get("meta_description"):
        update_payload["product"]["metafields_global_description_tag"] = seo["meta_description"]
    if seo.get("tags"):
        existing_tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        merged_tags   = list(dict.fromkeys(existing_tags + seo["tags"]))
        update_payload["product"]["tags"] = ", ".join(merged_tags)

    if not update_payload["product"]:
        return {"processed": 1, "updated": 0, "skipped": 1, "errors": []}

    result = await _shopify_rest_patch(f"products/{numeric_id}.json", update_payload)
    if "error" in result or "errors" in result:
        err_msg = result.get("error") or str(result.get("errors"))
        return {"processed": 1, "updated": 0, "skipped": 0,
                "errors": [f"Update failed: {err_msg}"]}

    return {"processed": 1, "updated": 1, "skipped": 0, "errors": []}


async def generate_sitemap_data() -> List[Dict]:
    """
    Return a list of all Shopify product URLs with SEO metadata, suitable
    for building an XML sitemap.

    Returns:
        List of {url, title, updated_at, priority, changefreq}
    """
    from modules.shopify_client import graphql, _store_domain  # type: ignore

    query = """
    query GetAllProducts($first: Int!, $after: String) {
        products(first: $first, after: $after) {
            pageInfo { hasNextPage endCursor }
            edges { node {
                id title handle updatedAt
                status
                images(first: 1) { edges { node { url } } }
            }}
        }
    }
    """
    all_products = []
    after: str | None = None

    while True:
        variables = {"first": 100}
        if after:
            variables["after"] = after
        result = await graphql(query, variables)
        edges = result.get("data", {}).get("products", {}).get("edges", [])
        page_info = result.get("data", {}).get("products", {}).get("pageInfo", {})

        all_products.extend([e["node"] for e in edges])

        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")

    domain = _store_domain()
    sitemap: List[Dict] = []
    for p in all_products:
        if p.get("status", "").upper() != "ACTIVE":
            continue
        handle     = p.get("handle", "")
        updated_at = p.get("updatedAt", "")[:10]  # YYYY-MM-DD
        image_url  = ""
        images     = p.get("images", {}).get("edges", [])
        if images:
            image_url = images[0]["node"].get("url", "")
        sitemap.append({
            "url":        f"https://{domain}/products/{handle}",
            "title":      p.get("title", ""),
            "updated_at": updated_at,
            "priority":   "0.8",
            "changefreq": "weekly",
            "image_url":  image_url,
        })

    log.info("Sitemap data: %d active products", len(sitemap))
    return sitemap


async def get_seo_score(product: Dict) -> Dict:
    """
    Score a product's SEO quality from 0–100.

    Args:
        product: dict with at least title, description, tags, images keys.
                 (Accepts both raw Shopify API dicts and plain dicts.)

    Returns:
        {score: int, issues: List[str], suggestions: List[str]}
    """
    issues:      List[str] = []
    suggestions: List[str] = []
    score = 100

    # ── Title ────────────────────────────────────────────────────────────────
    title = product.get("title", "")
    title_len = len(title)
    if title_len < _MIN_TITLE_LEN:
        penalty = 20
        score  -= penalty
        issues.append(f"Titel zu kurz ({title_len} Zeichen, Minimum: {_MIN_TITLE_LEN})")
        suggestions.append("Titel auf mindestens 30 Zeichen verlängern und Keywords einbauen.")
    elif title_len > _MAX_TITLE_LEN:
        penalty = 5
        score  -= penalty
        issues.append(f"Titel zu lang ({title_len} Zeichen, Maximum: {_MAX_TITLE_LEN})")
        suggestions.append("Titel kürzen — Google zeigt nur die ersten 70 Zeichen an.")

    # ── Description ─────────────────────────────────────────────────────────
    # Accept body_html, description, or body
    description = (
        product.get("body_html")
        or product.get("description")
        or product.get("body")
        or ""
    )
    # Strip simple HTML tags for length check
    import re
    desc_text = re.sub(r"<[^>]+>", "", description)
    desc_len  = len(desc_text.strip())
    if desc_len < _MIN_DESC_LEN:
        penalty = 25
        score  -= penalty
        issues.append(f"Beschreibung zu kurz ({desc_len} Zeichen, Minimum: {_MIN_DESC_LEN})")
        suggestions.append(
            "Produktbeschreibung auf mindestens 150 Zeichen ausbauen. "
            "Nutze /seo optimize um KI-Texte zu generieren."
        )

    # ── Tags ─────────────────────────────────────────────────────────────────
    raw_tags = product.get("tags", [])
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    elif isinstance(raw_tags, list):
        tags = raw_tags
    else:
        tags = []

    if len(tags) < _MIN_TAGS:
        penalty = 15
        score  -= penalty
        issues.append(f"Zu wenig Tags ({len(tags)}, Minimum: {_MIN_TAGS})")
        suggestions.append(f"Mindestens {_MIN_TAGS} relevante Tags hinzufügen.")

    # ── Images ───────────────────────────────────────────────────────────────
    # Support multiple formats of image data
    images = (
        product.get("images")
        or product.get("media")
        or []
    )
    has_images = bool(images)
    if not has_images:
        penalty = 20
        score  -= penalty
        issues.append("Keine Produktbilder vorhanden")
        suggestions.append("Mindestens 1 hochwertiges Produktbild hochladen.")
    elif isinstance(images, (list, dict)):
        # Check count
        img_count = len(images) if isinstance(images, list) else 0
        if img_count == 1:
            suggestions.append(
                "Mehr Produktbilder hinzufügen (mind. 3) für bessere Conversion."
            )

    # ── Meta description (Shopify metafields) ────────────────────────────────
    meta_desc = (
        product.get("metafields_global_description_tag")
        or product.get("seo", {}).get("description", "")
        if isinstance(product.get("seo"), dict)
        else ""
    )
    if not meta_desc or len(str(meta_desc)) < _MIN_META_DESC_LEN:
        penalty = 10
        score  -= penalty
        issues.append("Meta-Description fehlt oder zu kurz")
        suggestions.append("Meta-Description mit 120–160 Zeichen und primärem Keyword hinzufügen.")

    score = max(0, min(100, score))

    return {
        "score":       score,
        "issues":      issues,
        "suggestions": suggestions,
    }


# ── Backoff helper ────────────────────────────────────────────────────────────

async def _ai_post_with_backoff(session, method: str, url: str, **kwargs) -> "aiohttp.ClientResponse":
    """Execute an aiohttp request with exponential backoff on HTTP 429 (rate-limit).

    Retries up to 4 times: waits 2, 4, 8, 16 seconds.
    Raises the last response on persistent failure.
    """
    for attempt in range(5):
        resp = await session.request(method, url, **kwargs)
        if resp.status != 429:
            return resp
        retry_after = int(resp.headers.get("Retry-After", 2 ** attempt * 2))
        log.warning("AI API rate-limited (429) — retrying in %ds (attempt %d/5)", retry_after, attempt + 1)
        await resp.release()
        await asyncio.sleep(retry_after)
    return resp  # return last response even if still 429


# ── Maximum-Setup Additions ───────────────────────────────────────────────────

_MIN_BLOG_WORDS = 300   # Retry blog post generation if output is shorter than this

async def generate_blog_post(topic: str, product_context: str = "", language: str = "de") -> Dict:
    """Generate an SEO-optimised blog post about a topic or product using Claude.

    Args:
        topic:            Blog post topic or keyword (e.g. "Dropshipping Tipps 2026")
        product_context:  Optional product name/description to tie the post to
        language:         Target language ("de" or "en")

    Returns:
        {"ok": True, "title": str, "content": str, "meta_description": str,
         "slug": str, "word_count": int, "keywords": List[str]}
    """
    import re
    import os

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openai_key    = os.getenv("OPENAI_API_KEY", "")

    if not HAS_AIOHTTP:
        return {"ok": False, "error": "aiohttp not installed"}
    if not anthropic_key and not openai_key:
        return {"ok": False, "error": "No AI API key configured (ANTHROPIC_API_KEY or OPENAI_API_KEY)"}

    lang_instruction = "auf Deutsch" if language == "de" else "in English"
    product_hint = f"\nDas Produkt/Kontext: {product_context}" if product_context else ""

    prompt = (
        f"Schreibe einen SEO-optimierten Blog-Artikel {lang_instruction} zum Thema: \"{topic}\".{product_hint}\n\n"
        f"Anforderungen:\n"
        f"- Genau 1 H1 (Titel), 3-5 H2-Abschnitte\n"
        f"- 600-800 Wörter\n"
        f"- Primäres Keyword natürlich 5-7 mal eingebaut\n"
        f"- Am Ende: 3-5 FAQs als H2\n"
        f"- Klarer Call-to-Action am Ende\n\n"
        f"Antworte als JSON:\n"
        f'{{"title": "...", "meta_description": "...(120-160 Zeichen)", '
        f'"keywords": ["kw1", "kw2", "kw3"], '
        f'"content": "... (HTML mit h1, h2, p Tags)"}}'
    )

    raw_response = ""
    try:
        # Retry up to 2 times if word count is below threshold
        for _attempt in range(3):
            if anthropic_key:
                async with aiohttp.ClientSession() as session:
                    resp = await _ai_post_with_backoff(
                        session, "POST",
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key":         anthropic_key,
                            "anthropic-version": "2023-06-01",
                            "content-type":      "application/json",
                        },
                        json={
                            "model":      "claude-3-5-haiku-20241022",
                            "max_tokens": 2048,
                            "messages":   [{"role": "user", "content": prompt}],
                        },
                        timeout=aiohttp.ClientTimeout(total=60),
                    )
                    data = await resp.json(content_type=None)
                raw_response = data.get("content", [{}])[0].get("text", "")
            else:
                async with aiohttp.ClientSession() as session:
                    resp = await _ai_post_with_backoff(
                        session, "POST",
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                        json={
                            "model":       "gpt-4o-mini",
                            "messages":    [{"role": "user", "content": prompt}],
                            "max_tokens":  2048,
                            "temperature": 0.7,
                        },
                        timeout=aiohttp.ClientTimeout(total=60),
                    )
                    data = await resp.json(content_type=None)
                raw_response = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', raw_response)
            if not json_match:
                log.warning("Blog post attempt %d: no JSON in AI response", _attempt + 1)
                continue

            import json as _json
            parsed = _json.loads(json_match.group())
            content = parsed.get("content", "")
            word_count = len(re.sub(r"<[^>]+>", "", content).split())

            if word_count < _MIN_BLOG_WORDS:
                log.warning(
                    "Blog post attempt %d: only %d words (min %d) — retrying",
                    _attempt + 1, word_count, _MIN_BLOG_WORDS
                )
                continue  # retry

            # Sufficient length — build slug and return
            slug = re.sub(r"[^\w\s-]", "", topic.lower()).strip()
            slug = re.sub(r"[\s_]+", "-", slug)[:60]

            log.info("Blog post generated: topic='%s', words=%d (attempt %d)", topic, word_count, _attempt + 1)
            return {
                "ok":              True,
                "title":           parsed.get("title", topic),
                "content":         content,
                "meta_description": parsed.get("meta_description", ""),
                "slug":            slug,
                "keywords":        parsed.get("keywords", []),
                "word_count":      word_count,
                "language":        language,
            }

        # All attempts exhausted
        return {
            "ok":    False,
            "error": f"Blog post too short after 3 attempts (last: {word_count if raw_response else 0} words < {_MIN_BLOG_WORDS})",
        }
    except Exception as exc:
        log.error("generate_blog_post: %s", exc)
        return {"ok": False, "error": str(exc)}


async def optimize_meta_tags(limit: int = 50) -> Dict:
    """Improve Shopify product meta titles and descriptions for all products.

    Uses Claude/OpenAI to rewrite short or missing meta tags, then PATCH via REST.

    Returns:
        {"ok": True, "processed": int, "updated": int, "skipped": int, "errors": List[str]}
    """
    import os, re
    from modules.shopify_client import get_products  # type: ignore

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openai_key    = os.getenv("OPENAI_API_KEY", "")
    if not anthropic_key and not openai_key:
        return {"ok": False, "error": "No AI key (ANTHROPIC_API_KEY / OPENAI_API_KEY)"}

    try:
        products = await get_products(limit=limit)
    except Exception as exc:
        return {"ok": False, "error": f"Product fetch failed: {exc}"}

    processed = updated = skipped = 0
    errors: List[str] = []

    async def _ai_meta(title: str, description: str) -> Dict:
        prompt = (
            f"Produkt: {title}\nBeschreibung: {description[:300] or 'keine'}\n\n"
            f"Generiere:\n"
            f'1. SEO Meta-Title (50-60 Zeichen, inkl. Hauptkeyword)\n'
            f'2. Meta-Description (120-155 Zeichen, mit Call-to-Action)\n\n'
            f'Antworte als JSON: {{"meta_title": "...", "meta_description": "..."}}'
        )
        try:
            if anthropic_key:
                async with aiohttp.ClientSession() as s:
                    r = await _ai_post_with_backoff(
                        s, "POST",
                        "https://api.anthropic.com/v1/messages",
                        headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                        json={"model": "claude-3-5-haiku-20241022", "max_tokens": 256, "messages": [{"role": "user", "content": prompt}]},
                        timeout=aiohttp.ClientTimeout(total=20),
                    )
                    d = await r.json(content_type=None)
                raw = d.get("content", [{}])[0].get("text", "")
            else:
                async with aiohttp.ClientSession() as s:
                    r = await _ai_post_with_backoff(
                        s, "POST",
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "max_tokens": 256},
                        timeout=aiohttp.ClientTimeout(total=20),
                    )
                    d = await r.json(content_type=None)
                raw = d.get("choices", [{}])[0].get("message", {}).get("content", "")
            m = re.search(r'\{[\s\S]*\}', raw)
            if m:
                import json
                return json.loads(m.group())
        except Exception as exc:
            log.warning("_ai_meta error: %s", exc)
        return {}

    semaphore = asyncio.Semaphore(3)

    async def _process(product: Dict) -> None:
        nonlocal processed, updated, skipped
        processed += 1
        gid        = product.get("id", "")
        numeric_id = _extract_numeric_id(gid)
        title      = product.get("title", "")
        desc       = product.get("description") or product.get("body_html") or ""
        seo        = product.get("seo", {}) or {}
        existing_meta_title = seo.get("title", "")
        existing_meta_desc  = seo.get("description", "")

        # Skip if meta tags are already good
        if len(existing_meta_title) >= 40 and len(existing_meta_desc) >= 100:
            skipped += 1
            return

        async with semaphore:
            meta = await _ai_meta(title, re.sub(r"<[^>]+>", "", desc))

        if not meta:
            errors.append(f"Product {numeric_id}: AI meta generation failed")
            return

        payload: Dict = {"product": {}}
        if meta.get("meta_title"):
            payload["product"]["metafields_global_title_tag"] = meta["meta_title"]
        if meta.get("meta_description"):
            payload["product"]["metafields_global_description_tag"] = meta["meta_description"]

        if not payload["product"]:
            skipped += 1
            return

        result = await _shopify_rest_patch(f"products/{numeric_id}.json", payload)
        if "error" in result or "errors" in result:
            err = result.get("error") or str(result.get("errors"))
            errors.append(f"Product {numeric_id}: {err}")
        else:
            log.info("Meta tags updated for product %s (%s)", numeric_id, title)
            updated += 1

    await asyncio.gather(*[_process(p) for p in products])

    return {"ok": True, "processed": processed, "updated": updated, "skipped": skipped, "errors": errors}


async def generate_faq_schema(product: Dict) -> Dict:
    """Generate FAQ Schema Markup (JSON-LD) for a Shopify product.

    Uses Claude/OpenAI to create 5 realistic FAQs about the product,
    then returns structured JSON-LD ready to embed in the page <head>.

    Args:
        product: dict with at least "title" and optionally "description", "price", "category"

    Returns:
        {"ok": True, "schema_json": str, "faqs": [{"question": ..., "answer": ...}]}
    """
    import os, re, json

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openai_key    = os.getenv("OPENAI_API_KEY", "")
    if not anthropic_key and not openai_key:
        return {"ok": False, "error": "No AI key configured"}

    title = product.get("title", "Produkt")
    desc  = product.get("description") or product.get("body_html") or ""
    desc_plain = re.sub(r"<[^>]+>", "", desc)[:400]
    price = product.get("price") or product.get("priceRangeV2", {})
    if isinstance(price, dict):
        price = price.get("minVariantPrice", {}).get("amount", "")

    prompt = (
        f"Erstelle 5 realistische FAQs für dieses Produkt als JSON.\n"
        f"Produkt: {title}\n"
        f"Beschreibung: {desc_plain or 'keine'}\n"
        f"Preis: {price or 'unbekannt'}\n\n"
        f'Format: {{"faqs": [{{"question": "...", "answer": "..."}}]}}\n'
        f"Fragen sollen kaufrelevant sein: Versand, Material, Garantie, Anwendung, Rückgabe."
    )

    try:
        if anthropic_key:
            async with aiohttp.ClientSession() as s:
                r = await _ai_post_with_backoff(
                    s, "POST",
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": "claude-3-5-haiku-20241022", "max_tokens": 1024, "messages": [{"role": "user", "content": prompt}]},
                    timeout=aiohttp.ClientTimeout(total=30),
                )
                d = await r.json(content_type=None)
            raw = d.get("content", [{}])[0].get("text", "")
        else:
            async with aiohttp.ClientSession() as s:
                r = await _ai_post_with_backoff(
                    s, "POST",
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "max_tokens": 1024},
                    timeout=aiohttp.ClientTimeout(total=30),
                )
                d = await r.json(content_type=None)
            raw = d.get("choices", [{}])[0].get("message", {}).get("content", "")

        m = re.search(r'\{[\s\S]*\}', raw)
        if not m:
            return {"ok": False, "error": "No JSON in AI response"}

        parsed = json.loads(m.group())
        faqs = parsed.get("faqs", [])

        # Build JSON-LD schema — HTML-escape special characters in question/answer
        # to prevent XSS and broken JSON-LD when embedded in page <head>
        schema = {
            "@context": "https://schema.org",
            "@type":    "FAQPage",
            "mainEntity": [
                {
                    "@type":          "Question",
                    "name":           _html_escape_module.escape(faq.get("question", ""), quote=False),
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text":  _html_escape_module.escape(faq.get("answer", ""), quote=False),
                    },
                }
                for faq in faqs
            ],
        }
        schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
        script_tag  = f'<script type="application/ld+json">\n{schema_json}\n</script>'

        log.info("FAQ schema generated for product '%s': %d FAQs", title, len(faqs))
        return {
            "ok":         True,
            "faqs":       faqs,
            "schema_json": schema_json,
            "script_tag": script_tag,
            "product":    title,
        }
    except Exception as exc:
        log.error("generate_faq_schema: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── SEO Report ────────────────────────────────────────────────────────────────

async def get_seo_report(limit: int = 50) -> Dict:
    """Generate an SEO health report across all Shopify products.

    Scores every product, then returns:
      - Average SEO score (0–100)
      - Top 5 worst-scoring products (with issues + suggestions)
      - Breakdown by issue type

    Returns:
        {"ok": True, "avg_score": float, "total_products": int,
         "worst_products": [...], "issue_breakdown": {...}}
    """
    from modules.shopify_client import get_products  # type: ignore

    try:
        products = await get_products(limit=limit)
    except Exception as exc:
        log.error("get_seo_report: product fetch failed: %s", exc)
        return {"ok": False, "error": f"Product fetch failed: {exc}"}

    if not products:
        return {"ok": True, "avg_score": 0, "total_products": 0, "worst_products": [], "issue_breakdown": {}}

    scored: List[Dict] = []
    issue_counts: Dict[str, int] = {}

    for product in products:
        result = await get_seo_score(product)
        score  = result.get("score", 0)
        issues = result.get("issues", [])
        scored.append({
            "id":          product.get("id", ""),
            "title":       product.get("title", ""),
            "score":       score,
            "issues":      issues,
            "suggestions": result.get("suggestions", []),
        })
        for issue in issues:
            # Bucket issues by first keyword for summary breakdown
            key = issue.split("(")[0].strip()
            issue_counts[key] = issue_counts.get(key, 0) + 1

    avg_score = round(sum(p["score"] for p in scored) / len(scored), 1)
    worst_five = sorted(scored, key=lambda p: p["score"])[:5]

    log.info("SEO Report: %d products, avg score %.1f", len(scored), avg_score)
    return {
        "ok":              True,
        "avg_score":       avg_score,
        "total_products":  len(scored),
        "worst_products":  worst_five,
        "issue_breakdown": issue_counts,
    }
