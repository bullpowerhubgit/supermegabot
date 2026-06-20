#!/usr/bin/env python3
"""SEO Automation — Vollautomatische SEO-Optimierung für Shopify"""
import asyncio
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



async def _brutus_fire(message: str, channels: list = None):
    """BrutusCore: verteilt Revenue-Events auf alle Kanäle."""
    try:
        from modules.brutus_core import BrutusCore
        b = BrutusCore()
        await b.fire(message, channels=channels or ["telegram", "shopify_blog", "linkedin", "mailchimp", "klaviyo"])
    except Exception as _be:
        import logging
        logging.getLogger(__name__).debug("Brutus fire skip: %s", _be)


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
