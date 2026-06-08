#!/usr/bin/env python3
"""AI Content Pipeline — Vollautomatische Content-Erstellung via Ollama"""
import json
import logging
import os
from typing import Dict, List, Optional

log = logging.getLogger("AIContent")

OLLAMA_HOST  = os.getenv("OLLAMA_HOST", "http://localhost:11434")
SMART_MODEL  = os.getenv("OLLAMA_SMART_MODEL", "gemma2:latest")
FAST_MODEL   = os.getenv("OLLAMA_FAST_MODEL",  "llama3.2:latest")

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

# ---------------------------------------------------------------------------
# Core Ollama helper
# ---------------------------------------------------------------------------

async def _ollama(prompt: str, model: Optional[str] = None) -> str:
    """POST to Ollama /api/generate. Returns response text or a fallback string."""
    if model is None:
        model = SMART_MODEL
    if not HAS_AIOHTTP:
        log.warning("aiohttp not installed — Ollama unavailable")
        return f"[AI unavailable — aiohttp missing] Prompt: {prompt[:80]}..."

    payload = {"model": model, "prompt": prompt, "stream": False}
    try:
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{OLLAMA_HOST}/api/generate", json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.warning("Ollama returned %d: %s", resp.status, body[:200])
                    return f"[Ollama error {resp.status}]"
                data = await resp.json(content_type=None)
                return data.get("response", "")
    except Exception as exc:
        log.warning("Ollama not available (%s) — returning fallback", exc)
        return f"[Ollama unavailable: {exc}]"


# ---------------------------------------------------------------------------
# Public async functions
# ---------------------------------------------------------------------------

async def generate_product_seo(product: Dict) -> Dict:
    """
    Generate SEO-optimised title, description, meta_description, tags, and slug
    for a Shopify product.

    Args:
        product: dict with keys title, description, price, category

    Returns:
        dict: {title, description, meta_description, tags: List[str], slug}
    """
    prompt = (
        "Du bist SEO-Experte. Optimiere dieses Shopify-Produkt für maximale Sichtbarkeit.\n"
        f"Produkt: {json.dumps(product, ensure_ascii=False)}\n"
        'Antworte NUR als JSON: {"title": "...", "description": "...", '
        '"meta_description": "...", "tags": ["...", "..."], "slug": "..."}'
    )
    raw = await _ollama(prompt, model=SMART_MODEL)

    # Try to extract JSON from the response
    try:
        # Find the first { ... } block in the response
        start = raw.index("{")
        end   = raw.rindex("}") + 1
        result = json.loads(raw[start:end])
        # Ensure required keys exist
        result.setdefault("title",            product.get("title", ""))
        result.setdefault("description",      product.get("description", ""))
        result.setdefault("meta_description", "")
        result.setdefault("tags",             [])
        result.setdefault("slug",             "")
        return result
    except (ValueError, json.JSONDecodeError) as exc:
        log.warning("Could not parse SEO JSON (%s): %s", exc, raw[:200])
        title = product.get("title", "Product")
        return {
            "title":            title,
            "description":      product.get("description", ""),
            "meta_description": f"Buy {title} — best price & fast shipping.",
            "tags":             [product.get("category", "shop"), "sale", "trending"],
            "slug":             title.lower().replace(" ", "-"),
        }


async def generate_social_post(product: Dict, platform: str) -> str:
    """
    Generate a platform-specific social media post with hashtags.

    Args:
        product:  dict with keys title, description, price, category
        platform: one of tiktok / instagram / pinterest / facebook / twitter / reddit

    Returns:
        Ready-to-post text with hashtags.
    """
    platform = platform.lower()
    char_limits = {
        "twitter":   280,
        "tiktok":   2200,
    }
    char_limit = char_limits.get(platform, 2000)

    tone_hints = {
        "tiktok":    "energetisch, jung, mit Emojis und viralen Hooks",
        "instagram": "ästhetisch, inspirierend, mit relevanten Hashtags",
        "pinterest": "beschreibend, keyword-reich, mit Call-to-Action",
        "facebook":  "freundlich, informativ, community-orientiert",
        "twitter":   "knapp, prägnant, mit 2–3 Hashtags",
        "reddit":    "authentisch, ehrlich, ohne übertriebenes Marketing",
    }
    tone = tone_hints.get(platform, "professionell")

    prompt = (
        f"Du bist Social-Media-Experte für {platform.capitalize()}.\n"
        f"Schreibe einen {tone} Post für folgendes Produkt:\n"
        f"Produkt: {json.dumps(product, ensure_ascii=False)}\n"
        f"Zeichenlimit: {char_limit} Zeichen.\n"
        "Füge passende Hashtags ein. Antworte NUR mit dem fertigen Post-Text."
    )
    text = await _ollama(prompt, model=FAST_MODEL)
    # Trim to char limit as safety measure
    if len(text) > char_limit:
        text = text[:char_limit - 3] + "..."
    return text


async def generate_email_subject(context: str) -> str:
    """
    Generate a compelling email subject line for Mailchimp campaigns.

    Args:
        context: description of the campaign / product / offer

    Returns:
        Subject line string.
    """
    prompt = (
        "Du bist E-Mail-Marketing-Experte. Schreibe eine klickstarke Betreffzeile "
        f"für folgenden Kampagnen-Kontext:\n{context}\n"
        "Die Betreffzeile soll maximal 60 Zeichen lang sein und Neugier wecken. "
        "Antworte NUR mit der Betreffzeile, ohne Anführungszeichen."
    )
    subject = await _ollama(prompt, model=FAST_MODEL)
    # Strip quotes / extra whitespace
    subject = subject.strip().strip('"').strip("'")
    if len(subject) > 60:
        subject = subject[:57] + "..."
    if not subject or subject.startswith("["):
        subject = f"🔥 Nicht verpassen: {context[:30]}..."
    return subject


async def generate_content_calendar(niche: str, days: int = 7) -> List[Dict]:
    """
    Generate a content calendar for the given niche.

    Args:
        niche: target niche / industry (e.g. "Print-on-Demand T-Shirts")
        days:  number of days to plan (default 7)

    Returns:
        List of dicts: [{day, platform, content_type, topic, caption, hashtags}]
    """
    prompt = (
        f"Du bist Content-Stratege. Erstelle einen {days}-Tage Content-Kalender "
        f"für die Nische: {niche}\n"
        "Antworte NUR als JSON-Array:\n"
        '[{"day": 1, "platform": "instagram", "content_type": "Reel", '
        '"topic": "...", "caption": "...", "hashtags": ["...", "..."]}]'
    )
    raw = await _ollama(prompt, model=SMART_MODEL)

    try:
        start = raw.index("[")
        end   = raw.rindex("]") + 1
        calendar = json.loads(raw[start:end])
        return calendar
    except (ValueError, json.JSONDecodeError) as exc:
        log.warning("Could not parse content calendar JSON (%s)", exc)
        # Return a sensible fallback calendar
        platforms = ["instagram", "tiktok", "pinterest", "facebook", "twitter", "instagram", "reddit"]
        content_types = ["Reel", "Video", "Pin", "Post", "Tweet", "Story", "Discussion"]
        return [
            {
                "day":          d + 1,
                "platform":     platforms[d % len(platforms)],
                "content_type": content_types[d % len(content_types)],
                "topic":        f"{niche} — Tag {d + 1} Tipp",
                "caption":      f"Entdecke die besten {niche}-Produkte! Tag {d + 1} 🔥",
                "hashtags":     [f"#{niche.replace(' ', '')}", "#trending", "#sale"],
            }
            for d in range(days)
        ]


async def generate_product_description(title: str, features: List[str]) -> Dict:
    """
    Generate short/long descriptions, bullet points, and FAQ for a product.

    Args:
        title:    product title
        features: list of product features

    Returns:
        dict: {short_description, long_description, bullet_points: List[str],
               faq: List[{question, answer}]}
    """
    features_str = "\n".join(f"- {f}" for f in features)
    prompt = (
        f"Du bist Copywriter. Erstelle überzeugende Produktbeschreibungen für:\n"
        f"Produkt: {title}\n"
        f"Features:\n{features_str}\n\n"
        "Antworte NUR als JSON:\n"
        '{"short_description": "...", "long_description": "...", '
        '"bullet_points": ["...", "..."], "faq": [{"question": "...", "answer": "..."}]}'
    )
    raw = await _ollama(prompt, model=SMART_MODEL)

    try:
        start = raw.index("{")
        end   = raw.rindex("}") + 1
        result = json.loads(raw[start:end])
        result.setdefault("short_description", f"{title} — hochwertige Qualität.")
        result.setdefault("long_description",  f"Entdecken Sie {title}. {' '.join(features)}")
        result.setdefault("bullet_points",     features[:5])
        result.setdefault("faq", [
            {"question": "Wie lange dauert die Lieferung?", "answer": "3–5 Werktage."},
            {"question": "Gibt es eine Garantie?",          "answer": "30 Tage Rückgaberecht."},
        ])
        return result
    except (ValueError, json.JSONDecodeError) as exc:
        log.warning("Could not parse product description JSON (%s)", exc)
        return {
            "short_description": f"{title} — hochwertige Qualität zum besten Preis.",
            "long_description":  (
                f"Entdecken Sie {title}. Dieses Produkt überzeugt durch "
                f"{', '.join(features[:3])} und viele weitere Vorteile."
            ),
            "bullet_points": features,
            "faq": [
                {"question": "Wie lange dauert die Lieferung?", "answer": "3–5 Werktage."},
                {"question": "Gibt es eine Garantie?",          "answer": "30 Tage Rückgaberecht."},
                {"question": "Welche Zahlungsmethoden werden akzeptiert?",
                 "answer": "Kreditkarte, PayPal, Klarna."},
            ],
        }
