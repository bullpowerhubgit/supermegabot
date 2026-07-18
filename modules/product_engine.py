"""
ProductEngine — Autonomous product builder and manager.
Handles: description generation, Stripe billing, usage tracking, feedback loop.
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import aiohttp

from modules.ai_client import ai_complete

logger = logging.getLogger(__name__)

REGISTRY = json.loads(
    (Path(__file__).parent.parent / "config" / "products_registry.json").read_text()
)
PRODUCTS = {p["id"]: p for p in REGISTRY["products"]}

STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


# ─── Core AI Calls ─────────────────────────────────────────────────────────────

async def ai_generate(prompt: str, max_tokens: int = 800) -> str:
    """KI-Generierung mit automatischem Fallback (Groq → DeepSeek → OpenRouter → Anthropic)."""
    return await ai_complete(prompt=prompt, max_tokens=max_tokens)


# ─── Product 1: ShopifyDescriber ───────────────────────────────────────────────

async def generate_product_description(
    title: str, product_type: str = "", tags: list = None,
    lang: str = "de", tone: str = "verkaufend", length: str = "mittel"
) -> dict:
    """Generiert SEO-Produktbeschreibung für Shopify."""
    length_map = {"kurz": "80-120 Wörter", "mittel": "150-250 Wörter", "lang": "300-500 Wörter"}
    tags_str = ", ".join(tags or [])
    prompt = f"""Du bist ein Top-Copywriter für E-Commerce.
Produkt: {title}
Typ: {product_type or 'Allgemein'}
Tags/Keywords: {tags_str or 'keine'}
Sprache: {'Deutsch' if lang == 'de' else 'Englisch'}
Ton: {tone}
Länge: {length_map.get(length, '150-250 Wörter')}

Schreibe:
1. TITEL (SEO-optimiert, max 70 Zeichen)
2. META-DESCRIPTION (max 155 Zeichen)
3. PRODUKTBESCHREIBUNG (HTML mit <p>, <ul>, <strong>)
4. 5 TAGS (kommagetrennt)

Format: JSON mit keys: title, meta, description, tags"""

    raw = await ai_generate(prompt, max_tokens=600)
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        return {"title": title, "meta": "", "description": raw, "tags": []}


async def bulk_describe_shopify(products: list, lang: str = "de") -> list:
    """Batch-Generierung für mehrere Produkte (max 20 gleichzeitig)."""
    tasks = [generate_product_description(p.get("title", ""), p.get("type", ""),
                                          p.get("tags", []), lang) for p in products[:20]]
    return await asyncio.gather(*tasks)


# ─── Product 2: MarginRadar ────────────────────────────────────────────────────

def calculate_margin(buy_price: float, sell_price: float,
                     platform_fee_pct: float = 13.0, shipping: float = 0) -> dict:
    """Berechnet Nettomarge für Dropshipping."""
    platform_fee = sell_price * (platform_fee_pct / 100)
    net = sell_price - buy_price - platform_fee - shipping
    margin_pct = (net / sell_price * 100) if sell_price > 0 else 0
    roi = (net / buy_price * 100) if buy_price > 0 else 0
    return {
        "buy": round(buy_price, 2),
        "sell": round(sell_price, 2),
        "platform_fee": round(platform_fee, 2),
        "shipping": round(shipping, 2),
        "net_profit": round(net, 2),
        "margin_pct": round(margin_pct, 1),
        "roi_pct": round(roi, 1),
        "verdict": "✅ Gut" if margin_pct >= 25 else "⚠ Grenzwertig" if margin_pct >= 10 else "❌ Zu gering",
    }


async def analyze_product_opportunity(url: str) -> dict:
    """KI-Analyse ob ein Produkt profitabel ist."""
    prompt = f"""Analysiere dieses Produkt für Dropshipping:
URL: {url}

Gib zurück (JSON):
- profitability_score: 1-10
- competition_level: "niedrig"/"mittel"/"hoch"
- trend_direction: "steigend"/"stagnierend"/"fallend"
- recommended_price_range: {{min, max}} in EUR
- target_audience: string
- key_selling_points: [list]
- risks: [list]
- verdict: kurze Zusammenfassung"""
    raw = await ai_generate(prompt, max_tokens=400)
    try:
        start = raw.find("{"); end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        return {"verdict": raw[:200], "profitability_score": 5}


# ─── Product 3: AIDescAPI ──────────────────────────────────────────────────────

async def api_generate_content(
    content_type: str, subject: str, extra: dict = None, lang: str = "de"
) -> dict:
    """Pay-per-use Content Generation API."""
    type_prompts = {
        "product_description": f"SEO-Produktbeschreibung (200 Wörter, HTML) für: {subject}",
        "ad_copy": f"Facebook/Instagram Ad Copy (Headline + Body + CTA) für: {subject}",
        "email_subject": f"5 Email-Betreffzeilen für: {subject} (jede max 50 Zeichen)",
        "seo_title": f"10 SEO-Titel-Varianten (max 60 Zeichen je) für: {subject}",
        "blog_outline": f"Blog-Outline (H2s + Bullet Points) für Artikel über: {subject}",
        "tiktok_hook": f"5 TikTok/Reels Opening-Hooks (max 3 Sekunden Lesezeit) für: {subject}",
    }
    prompt_text = type_prompts.get(content_type, f"Schreibe Content über: {subject}")
    if extra:
        prompt_text += f"\nZusatz-Kontext: {json.dumps(extra, ensure_ascii=False)}"
    if lang == "en":
        prompt_text += "\n(Write in English)"

    result = await ai_generate(prompt_text, max_tokens=500)
    return {
        "content_type": content_type,
        "subject": subject,
        "result": result,
        "tokens_used": len(result.split()) * 1.3,
        "cost_eur": 0.05,
    }


# ─── Product 4: TrendHunter AI ────────────────────────────────────────────────

async def analyze_trends(niche: str, timeframe: str = "this week") -> dict:
    """KI-Trend-Analyse für eine Nische."""
    prompt = f"""Du bist ein Trend-Analyst für E-Commerce und Social Media.

Nische: {niche}
Zeitraum: {timeframe}

Analysiere aktuelle Trends (basierend auf deinem Wissen bis 2025):
Gib zurück (JSON):
- top_trends: [{{name, trend_score: 1-10, why_trending, platforms: []}}] (max 5)
- emerging_products: [{{name, potential: 1-10, target_audience}}] (max 3)
- content_angles: [string] (3 Ideen)
- competitor_moves: string
- recommendation: string
- action_items: [string] (3 konkrete Schritte)"""
    raw = await ai_generate(prompt, max_tokens=700)
    try:
        start = raw.find("{"); end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        return {"recommendation": raw[:300], "top_trends": [], "emerging_products": []}


async def generate_daily_trend_report(niches: list) -> dict:
    """Täglicher Trend-Report für mehrere Nischen."""
    tasks = [analyze_trends(n) for n in niches[:10]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        "date": time.strftime("%Y-%m-%d"),
        "niches": {niche: (res if not isinstance(res, Exception) else {"error": str(res)})
                   for niche, res in zip(niches, results)},
    }


# ─── Product 5: AutoScript Pro ────────────────────────────────────────────────

async def generate_video_script(
    topic: str, platform: str = "youtube", duration_min: int = 10,
    style: str = "educational", cta: str = ""
) -> dict:
    """Generiert vollständiges Video-Script."""
    platform_config = {
        "youtube": {"hook_secs": 30, "words_per_min": 130, "structure": "Hook→Problem→Solution→CTA"},
        "tiktok": {"hook_secs": 3, "words_per_min": 150, "structure": "Hook→Value→CTA"},
        "instagram_reel": {"hook_secs": 5, "words_per_min": 140, "structure": "Hook→Twist→CTA"},
        "podcast": {"hook_secs": 60, "words_per_min": 120, "structure": "Intro→Content→Recap→CTA"},
    }
    cfg = platform_config.get(platform, platform_config["youtube"])
    target_words = duration_min * cfg["words_per_min"]
    cta_text = cta or "Abonniere für mehr → Link in Bio / Beschreibung"

    prompt = f"""Du bist ein Top-Content-Stratege für {platform.upper()}.

Thema: {topic}
Stil: {style}
Länge: ~{duration_min} Minuten ({target_words} Wörter)
Struktur: {cfg['structure']}
CTA am Ende: {cta_text}

Schreibe ein vollständiges Script mit:
- HOOK ({cfg['hook_secs']} Sekunden - sofort fesseln)
- HAUPTTEIL (strukturiert mit [PAUSE]-Markierungen)
- B-ROLL Hinweise in [BRACKETS]
- CTA-SEGMENT am Ende

Dann noch:
- 5 THUMBNAIL-IDEEN
- 3 TITEL-VARIANTEN
- VIDEO-TAGS (10 Stück)

Format: Markdown mit klaren Sections"""

    script = await ai_generate(prompt, max_tokens=1200)
    word_count = len(script.split())
    return {
        "topic": topic,
        "platform": platform,
        "duration_min": duration_min,
        "script": script,
        "word_count": word_count,
        "estimated_duration_min": round(word_count / cfg["words_per_min"], 1),
    }


async def generate_content_calendar(niche: str, weeks: int = 4) -> list:
    """Erstellt Content-Kalender für mehrere Wochen."""
    prompt = f"""Erstelle einen {weeks}-Wochen Content-Kalender für die Nische: {niche}

Für jede Woche, 5 Video-Ideen (Mo-Fr):
JSON-Array: [{{week: 1, day: "Mo", platform: "youtube"/"tiktok", topic: str, hook: str, type: "educational"/"entertainment"/"sales"}}]
Nur JSON, keine Erklärungen."""
    raw = await ai_generate(prompt, max_tokens=800)
    try:
        start = raw.find("["); end = raw.rfind("]") + 1
        return json.loads(raw[start:end])
    except Exception:
        return []


# ─── Stripe Billing ────────────────────────────────────────────────────────────

async def create_stripe_subscription_session(
    product_id: str, tier_name: str, customer_email: str = ""
) -> dict:
    """Erstellt Stripe Checkout Session für Subscription."""
    product = PRODUCTS.get(product_id)
    if not product:
        return {"error": "Produkt nicht gefunden"}
    tier = next((t for t in product["tiers"] if t["name"].lower() == tier_name.lower()), None)
    if not tier:
        return {"error": "Tier nicht gefunden"}

    price_cents = int(tier["price"] * 100)
    mode = "subscription" if tier.get("period") in ["mo", "year"] else "payment"

    payload = {
        "mode": mode,
        "success_url": f"https://{product['netlify_site']}.netlify.app/success",
        "cancel_url": f"https://{product['netlify_site']}.netlify.app/#preise",
        "line_items[0][price_data][currency]": "eur",
        "line_items[0][price_data][unit_amount]": str(price_cents),
        "line_items[0][price_data][product_data][name]": f"{product['name']} — {tier['name']}",
        "line_items[0][quantity]": "1",
        "metadata[product_id]": product_id,
        "metadata[tier]": tier_name,
    }
    if mode == "subscription":
        payload["line_items[0][price_data][recurring][interval]"] = "month"
    if customer_email:
        payload["customer_email"] = customer_email

    async with aiohttp.ClientSession() as s:
        r = await s.post(
            "https://api.stripe.com/v1/checkout/sessions",
            headers={"Authorization": f"Bearer {STRIPE_KEY}"},
            data=payload, timeout=aiohttp.ClientTimeout(total=15)
        )
        data = await r.json()
        return {"checkout_url": data.get("url", ""), "session_id": data.get("id", "")}


# ─── Usage Tracking ────────────────────────────────────────────────────────────

async def track_usage(product_id: str, user_id: str, action: str, metadata: dict = None):
    """Trackt Nutzung in Supabase für Billing + Analytics."""
    if not SUPABASE_URL:
        return
    async with aiohttp.ClientSession() as s:
        await s.post(
            f"{SUPABASE_URL}/rest/v1/product_usage",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"product_id": product_id, "user_id": user_id, "action": action,
                  "metadata": metadata or {}, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ")},
            timeout=aiohttp.ClientTimeout(total=5)
        )


async def get_product_stats(product_id: str, days: int = 7) -> dict:
    """Holt Produkt-Nutzungsstatistiken aus Supabase."""
    if not SUPABASE_URL:
        return {}
    async with aiohttp.ClientSession() as s:
        r = await s.get(
            f"{SUPABASE_URL}/rest/v1/product_usage",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"product_id": f"eq.{product_id}", "select": "action,ts",
                    "order": "ts.desc", "limit": "1000"},
            timeout=aiohttp.ClientTimeout(total=10)
        )
        rows = await r.json()
        actions = {}
        for row in (rows if isinstance(rows, list) else []):
            a = row.get("action", "")
            actions[a] = actions.get(a, 0) + 1
        return {"product_id": product_id, "period_days": days, "actions": actions,
                "total_events": sum(actions.values())}
