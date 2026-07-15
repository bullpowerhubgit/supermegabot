"""
AI Content Factory — SuperMegaBot Revolution Engine
One topic → complete multi-platform, multilingual content package.
All generation runs in parallel via asyncio.gather().
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import aiohttp

log = logging.getLogger(__name__)

BRAND_URL    = os.getenv("BRAND_URL", "https://bullpower-hub-portal.netlify.app")
BRAND_NAME   = os.getenv("BRAND_NAME", "BullPower Hub")
DS24_LINK    = os.getenv("DS24_AFFILIATE_LINK", "")
DATA_DIR = Path(os.getenv("DATA_DIR", "/tmp/content_factory"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Core AI helper — vollständige Fallback-Chain via ai_client ────────────────

async def _claude(prompt: str, system: str = "", max_tokens: int = 2000) -> str:
    """AI mit Fallback: Anthropic → OpenAI → OpenRouter → Perplexity"""
    try:
        from modules.ai_client import ai_complete
        result = await ai_complete(prompt, system=system, max_tokens=max_tokens)
        if result:
            return result
    except Exception as e:
        log.warning(f"ai_complete failed: {e}")
    return f"[FALLBACK: {prompt[:80]}]"


# ── 1. BLOG POST GENERATOR ────────────────────────────────────────────────────

async def generate_blog_post(topic: str, keywords: list = None, language: str = "de") -> dict:
    """Full SEO blog post: H1, meta, 5-7 H2 sections, FAQ, CTA."""
    kws = ", ".join(keywords or [topic])
    lang_name = {"de": "German", "en": "English", "fr": "French", "es": "Spanish", "it": "Italian"}.get(language, "German")
    sys = (f"You are an expert SEO content writer. Write in {lang_name}. "
           f"Brand: {BRAND_NAME} ({BRAND_URL}). Be specific, actionable, no fluff.")
    prompt = f"""Write a complete SEO-optimized blog post about: {topic}
Keywords to include: {kws}

Format as JSON:
{{
  "title": "H1 title (60 chars max, keyword first)",
  "meta_description": "155 chars exactly, includes primary keyword + CTA",
  "slug": "url-slug-format",
  "introduction": "150-word hook paragraph",
  "sections": [
    {{"h2": "Section Title", "content": "200+ word section body with keyword naturally placed"}},
    ... (5-7 sections total)
  ],
  "faq": [
    {{"question": "People Also Ask question", "answer": "50-word answer"}},
    ... (5 questions)
  ],
  "cta": "Strong call-to-action paragraph with link to {BRAND_URL}",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "category": "primary category"
}}"""
    raw = await _claude(prompt, sys, max_tokens=4000)
    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        data = json.loads(match.group()) if match else {}
    except Exception:
        data = {"title": topic, "content": raw}
    # Build HTML + markdown + stats
    word_count = sum(len(s.get("content", "").split()) for s in data.get("sections", []))
    word_count += len(data.get("introduction", "").split())
    reading_time = max(1, word_count // 200)
    data["word_count"] = word_count
    data["reading_time"] = f"{reading_time} min read"
    data["language"] = language
    data["generated_at"] = datetime.utcnow().isoformat()
    return data


# ── 2. SOCIAL MEDIA BATCH ────────────────────────────────────────────────────

async def generate_social_batch(core_message: str, brand_url: str = BRAND_URL) -> dict:
    """30 days of social posts for ALL platforms in one call."""
    sys = f"Expert social media strategist for {BRAND_NAME}. Brand URL: {brand_url}. Write in German."
    platforms = {
        "twitter": ("Twitter/X", "280 chars max, punchy, 1-2 hashtags, hook in first 10 words", 30),
        "linkedin": ("LinkedIn", "1300 chars, professional, data-driven, ends with question", 20),
        "instagram": ("Instagram", "emotional, storytelling, 30 relevant hashtags at end", 30),
        "facebook": ("Facebook", "conversational, question-based, encourages comments, 500 chars", 20),
        "pinterest": ("Pinterest", "keyword-rich, benefit-focused, 300 chars, no hashtags", 20),
        "tiktok": ("TikTok", "hook (first 3 words stop scroll), script for 30s video, trendy", 15),
    }

    async def gen_platform(key: str, name: str, style: str, count: int) -> tuple:
        prompt = f"""Topic: {core_message}
Generate {count} unique {name} posts about this topic.
Style: {style}
Return JSON array: [{{"day": 1, "post": "...", "best_time": "HH:MM"}}, ...]
Vary the angle each day: educational, emotional, promotional, storytelling, controversial, inspirational."""
        raw = await _claude(prompt, sys, max_tokens=3000)
        try:
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            posts = json.loads(match.group()) if match else []
        except Exception:
            posts = [{"day": i + 1, "post": raw[i*50:(i+1)*50], "best_time": "09:00"} for i in range(count)]
        return key, posts

    results = await asyncio.gather(
        *[gen_platform(k, n, s, c) for k, (n, s, c) in platforms.items()],
        return_exceptions=True,
    )
    batch = {}
    for item in results:
        if isinstance(item, Exception):
            log.warning(f"generate_social_batch: gen_platform failed: {item}")
        else:
            k, v = item
            batch[k] = v
    batch["generated_at"] = datetime.utcnow().isoformat()
    batch["topic"] = core_message
    # Cache to disk
    cache_path = DATA_DIR / f"social_batch_{hashlib.md5(core_message.encode()).hexdigest()[:8]}.json"
    cache_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2))
    return batch


# ── 3. EMAIL SEQUENCE GENERATOR ───────────────────────────────────────────────

async def generate_email_sequence(product: str, audience: str, sequence_length: int = 7) -> list:
    """7-email nurture/welcome sequence with full HTML + plain text."""
    email_types = [
        ("Welcome + Value Bomb", "emotional welcome, deliver massive free value, no selling"),
        ("Story + Problem", "personal story revealing the problem your audience faces"),
        ("Solution Reveal", "introduce the solution, not the product yet"),
        ("Social Proof", "case studies, testimonials, specific numbers and results"),
        ("FAQ + Objections", "answer top 5 objections, build trust and credibility"),
        ("Urgency + Offer", "limited time offer, scarcity, clear price and benefit"),
        ("Final CTA", "last chance, summarize all benefits, strong single CTA"),
    ]

    async def gen_email(index: int, email_type: str, instructions: str) -> dict:
        prompt = f"""Write email #{index + 1} of 7 for a sequence about: {product}
Target audience: {audience}
Email type: {email_type}
Instructions: {instructions}
Brand: {BRAND_NAME} ({BRAND_URL})

Return JSON:
{{
  "subject": "email subject line (under 50 chars)",
  "preview_text": "preview text (under 90 chars)",
  "body_plain": "full plain text email body (300-500 words)",
  "body_html": "<p>HTML version of same email</p>",
  "cta_text": "button text",
  "cta_url": "{BRAND_URL}"
}}"""
        raw = await _claude(prompt, max_tokens=2000)
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            data = json.loads(match.group()) if match else {}
        except Exception:
            data = {"subject": f"Email {index+1}", "body_plain": raw}
        data["sequence_position"] = index + 1
        data["send_day"] = [0, 1, 3, 5, 7, 9, 11][index] if index < 7 else index * 2
        return data

    raw_emails = await asyncio.gather(
        *[gen_email(i, et, ins) for i, (et, ins) in enumerate(email_types[:sequence_length])],
        return_exceptions=True,
    )
    emails = []
    for i, item in enumerate(raw_emails):
        if isinstance(item, Exception):
            log.warning(f"generate_email_sequence: gen_email #{i+1} failed: {item}")
            emails.append({"subject": f"Email {i+1}", "body_plain": "", "sequence_position": i + 1, "send_day": i * 2})
        else:
            emails.append(item)
    return emails


# ── 4. MULTILINGUAL TRANSLATOR ────────────────────────────────────────────────

async def translate_content(content: str, target_languages: list = None) -> dict:
    """Translate + culturally adapt content to 5 languages in parallel."""
    langs = target_languages or ["de", "en", "fr", "es", "it"]
    lang_names = {"de": "German (DACH market)", "en": "English (US/UK)",
                  "fr": "French (France)", "es": "Spanish (Spain/LATAM)", "it": "Italian"}

    async def translate_one(lang: str) -> tuple:
        name = lang_names.get(lang, lang)
        prompt = f"""Translate and culturally adapt this content to {name}.
Don't just translate — adapt idioms, examples, and tone for the {name} market.
Keep URLs and brand names unchanged.

Content: {content}

Return only the translated content, no explanation."""
        result = await _claude(prompt, max_tokens=2000)
        return lang, result

    raw_results = await asyncio.gather(
        *[translate_one(l) for l in langs],
        return_exceptions=True,
    )
    translations = {}
    for item in raw_results:
        if isinstance(item, Exception):
            log.warning(f"translate_content: translate_one failed: {item}")
        else:
            lang, result = item
            translations[lang] = result
    return {"translations": translations, "source_length": len(content),
            "languages": langs, "generated_at": datetime.utcnow().isoformat()}


# ── 5. IMAGE PROMPT GENERATOR ────────────────────────────────────────────────

async def generate_image_prompts(topic: str, platform: str = "all", count: int = 5) -> dict:
    """Generate optimized DALL-E/SD prompts for every platform format."""
    specs = {
        "instagram": ("1:1 square 1080x1080px", "vibrant, lifestyle, aspirational, warm colors"),
        "pinterest": ("2:3 vertical 1000x1500px", "beautiful, inspirational, text overlay space at top"),
        "blog": ("16:9 header 1200x630px", "professional, clean, article header style"),
        "youtube": ("16:9 thumbnail 1280x720px", "CLICKBAIT thumbnail, shocked face, bright colors, bold text"),
        "facebook": ("1.91:1 ad 1200x628px", "attention-grabbing, clear value proposition"),
        "story": ("9:16 vertical 1080x1920px", "full-bleed, bold, mobile-first design"),
    }
    target_specs = {k: v for k, v in specs.items()} if platform == "all" else {platform: specs.get(platform, specs["instagram"])}

    async def gen_for_platform(plat: str, size: str, style: str) -> tuple:
        prompt = f"""Generate {count} unique image prompts for: {topic}
Platform: {plat} ({size})
Visual style: {style}
Brand: {BRAND_NAME} — colors: dark blue, gold, white

Each prompt should be 50-100 words, photorealistic or digital art, highly detailed.
Return JSON array: ["prompt 1", "prompt 2", ...]"""
        raw = await _claude(prompt, max_tokens=1000)
        try:
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            prompts = json.loads(match.group()) if match else [raw]
        except Exception:
            prompts = [raw]
        return plat, {"size": size, "style": style, "prompts": prompts}

    raw_results = await asyncio.gather(
        *[gen_for_platform(p, s, st) for p, (s, st) in target_specs.items()],
        return_exceptions=True,
    )
    platforms_out = {}
    for item in raw_results:
        if isinstance(item, Exception):
            log.warning(f"generate_image_prompts: gen_for_platform failed: {item}")
        else:
            plat, data = item
            platforms_out[plat] = data
    return {"topic": topic, "platforms": platforms_out, "generated_at": datetime.utcnow().isoformat()}


# ── 6. AD COPY GENERATOR ─────────────────────────────────────────────────────

async def generate_ad_copy(product: str, audience: str, budget_level: str = "low") -> dict:
    """Complete ad copy package — Google, Facebook/Instagram, YouTube, TikTok."""
    sys = f"Expert direct response copywriter. Brand: {BRAND_NAME}. Write in German. Be specific and benefit-focused."

    async def gen_google_ads() -> dict:
        prompt = f"""Product: {product} | Audience: {audience}
Generate Google Ads copy. Return JSON:
{{
  "headlines": ["headline 1 (30 chars max)", ...] (15 unique headlines),
  "descriptions": ["description 1 (90 chars max)", ...] (4 descriptions),
  "callouts": ["Free shipping", ...] (6 callouts),
  "sitelinks": [{{"text": "...", "description": "..."}}] (4 sitelinks)
}}"""
        raw = await _claude(prompt, sys, max_tokens=1500)
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            return json.loads(match.group()) if match else {}
        except Exception:
            return {"raw": raw}

    async def gen_meta_ads() -> dict:
        prompt = f"""Product: {product} | Audience: {audience}
Generate Facebook/Instagram ad copy using these angles: pain, desire, fear, social proof, aspiration.
Return JSON:
{{
  "primary_texts": ["angle 1 (125 chars)", ...] (5 texts, one per angle),
  "headlines": ["headline", ...] (5, under 40 chars each),
  "descriptions": ["description", ...] (5, under 30 chars),
  "link_descriptions": ["...", ...] (5 variants)
}}"""
        raw = await _claude(prompt, sys, max_tokens=1500)
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            return json.loads(match.group()) if match else {}
        except Exception:
            return {"raw": raw}

    async def gen_video_scripts() -> dict:
        prompt = f"""Product: {product} | Audience: {audience}
Affiliate/checkout link to include in CTAs: {DS24_LINK}
Write video ad scripts. Return JSON:
{{
  "youtube_15s": "15-second pre-roll script (hook in first 5s, end with CTA link)",
  "youtube_30s": "30-second pre-roll script (include affiliate link in CTA)",
  "youtube_60s": "60-second TrueView script with clear CTA pointing to {DS24_LINK}",
  "tiktok_15s": "TikTok 15s spark ad (trendy, native-feeling, strong hook, link in bio)",
  "tiktok_30s": "TikTok 30s with trend audio reference, CTA to link in bio: {DS24_LINK}"
}}"""
        raw = await _claude(prompt, sys, max_tokens=1500)
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            return json.loads(match.group()) if match else {}
        except Exception:
            return {"raw": raw}

    ad_results = await asyncio.gather(
        gen_google_ads(), gen_meta_ads(), gen_video_scripts(),
        return_exceptions=True,
    )
    ad_names = ["gen_google_ads", "gen_meta_ads", "gen_video_scripts"]
    google, meta, video = [
        item if not isinstance(item, Exception)
        else (log.warning(f"generate_ad_copy: {ad_names[i]} failed: {item}") or {})
        for i, item in enumerate(ad_results)
    ]
    return {
        "product": product, "audience": audience, "budget": budget_level,
        "google_ads": google, "meta_ads": meta, "video_scripts": video,
        "generated_at": datetime.utcnow().isoformat()
    }


# ── 7. CONTENT CALENDAR BUILDER ───────────────────────────────────────────────

async def build_content_calendar(month: str = None, topics: list = None) -> dict:
    """30-day content calendar for all platforms with DACH holidays."""
    if not month:
        month = datetime.utcnow().strftime("%Y-%m")
    dach_holidays = {
        "01": ["Neujahr (1.1)", "Heilige Drei Könige AT (6.1)"],
        "02": ["Valentinstag (14.2)", "Karneval/Fasching"],
        "03": ["Weltfrauentag (8.3)", "Frühlingsanfang (20.3)"],
        "04": ["Ostern", "Tag der Arbeit Vorbereitung"],
        "05": ["Tag der Arbeit (1.5)", "Muttertag (2. Sonntag)", "Christi Himmelfahrt"],
        "06": ["Pfingsten", "Vatertag"],
        "07": ["Sommerschlussverkauf"],
        "08": ["Sommerpause", "Back-to-School"],
        "09": ["Herbstanfang (23.9)", "Oktoberfest"],
        "10": ["Tag der Deutschen Einheit (3.10)", "Nationalfeiertag AT (26.10)", "Halloween"],
        "11": ["Allerheiligen (1.11)", "Black Friday / Cyber Monday"],
        "12": ["Nikolaus (6.12)", "Weihnachten (24-26.12)", "Silvester (31.12)"],
    }
    month_num = month.split("-")[1] if "-" in month else "06"
    events = dach_holidays.get(month_num, [])
    default_topics = topics or [
        "Shopify Automation", "E-Commerce Trends", "KI Tools für Händler",
        "Umsatz steigern", "Social Media Marketing", "Email Marketing",
        "Conversion Optimierung", "Dropshipping 2024",
    ]
    prompt = f"""Create a 30-day content calendar for {month} for brand: {BRAND_NAME}.
Key events/holidays this month: {', '.join(events)}
Topic rotation: {', '.join(default_topics)}

Mix of content types each week: 40% educational, 30% promotional, 20% entertaining, 10% user-generated/polls.

Return JSON:
{{
  "month": "{month}",
  "days": [
    {{
      "day": 1,
      "date": "2024-{month_num}-01",
      "theme": "content theme",
      "platforms": {{
        "instagram": "post idea",
        "linkedin": "post idea",
        "facebook": "post idea",
        "twitter": "post idea",
        "email": "newsletter topic or null",
        "blog": "blog post title or null"
      }},
      "hook": "attention-grabbing hook sentence",
      "goal": "awareness|engagement|conversion|retention"
    }}
  ]
}}"""
    raw = await _claude(prompt, max_tokens=4000)
    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        cal = json.loads(match.group()) if match else {"month": month, "raw": raw}
    except Exception:
        cal = {"month": month, "raw": raw}
    cal["generated_at"] = datetime.utcnow().isoformat()
    # Cache
    (DATA_DIR / f"calendar_{month}.json").write_text(json.dumps(cal, ensure_ascii=False, indent=2))
    return cal


# ── 8. TRENDING TOPIC FINDER ──────────────────────────────────────────────────

async def find_trending_topics(niche: str = "shopify ecommerce automation") -> list:
    """Find trending topics via Google RSS + Reddit + AI analysis."""
    topics_found = []

    # Google Trends RSS
    rss_urls = [
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=DE",
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=AT",
    ]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        for url in rss_urls:
            try:
                async with s.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
                    if r.status == 200:
                        text = await r.text()
                        titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', text)
                        topics_found.extend(titles[:10])
            except Exception as e:
                log.warning(f"RSS fetch {url}: {e}")

        # Reddit hot posts
        reddit_url = "https://www.reddit.com/r/shopify+ecommerce+dropshipping/hot.json?limit=10"
        try:
            async with s.get(reddit_url, headers={"User-Agent": "SuperMegaBot/1.0"}) as r:
                if r.status == 200:
                    data = await r.json()
                    posts = data.get("data", {}).get("children", [])
                    for p in posts:
                        title = p.get("data", {}).get("title", "")
                        if title:
                            topics_found.append(title)
        except Exception as e:
            log.warning(f"Reddit fetch: {e}")

    # AI analysis: find content opportunities in found topics
    if topics_found:
        prompt = f"""Niche: {niche}
Trending topics found today: {json.dumps(topics_found[:20])}

Identify the TOP 10 content opportunities relevant to our niche.
Return JSON array:
[{{
  "topic": "specific topic",
  "angle": "our unique content angle",
  "urgency": "high|medium|low",
  "platforms": ["best", "platforms"],
  "estimated_reach": "rough reach estimate",
  "content_type": "blog|video|thread|carousel"
}}, ...]"""
        raw = await _claude(prompt, max_tokens=1500)
        try:
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            opportunities = json.loads(match.group()) if match else []
        except Exception:
            opportunities = [{"topic": t, "angle": t, "urgency": "medium",
                              "platforms": ["instagram", "linkedin"], "content_type": "post"}
                             for t in topics_found[:10]]
    else:
        # Static fallback — no AI needed, always returns content opportunities
        opportunities = [
            {"topic": "KI-Automatisierung für Shopify 2026", "angle": "10 Tools die deinen Shop automatisieren", "urgency": "high", "platforms": ["linkedin", "instagram", "telegram"], "content_type": "carousel"},
            {"topic": "Passives Einkommen mit Dropshipping", "angle": "So startest du ohne Lager und Investition", "urgency": "high", "platforms": ["tiktok", "instagram", "youtube"], "content_type": "video"},
            {"topic": "Email-Marketing ROI 3600%", "angle": "Warum Email noch immer der beste Kanal ist", "urgency": "medium", "platforms": ["linkedin", "blog"], "content_type": "blog"},
            {"topic": "TikTok Shop Strategie 2026", "angle": "Wie DACH-Händler TikTok Shop nutzen", "urgency": "high", "platforms": ["tiktok", "instagram"], "content_type": "video"},
            {"topic": "Affiliate Marketing mit Digistore24", "angle": "Schritt-für-Schritt zum ersten Affiliate-Verkauf", "urgency": "high", "platforms": ["blog", "youtube", "telegram"], "content_type": "blog"},
            {"topic": "Print-on-Demand Produkte verkaufen", "angle": "Null Risiko, maximaler Profit mit POD", "urgency": "medium", "platforms": ["instagram", "pinterest"], "content_type": "carousel"},
            {"topic": "Shopify SEO Checkliste 2026", "angle": "87 Punkte für mehr organischen Traffic", "urgency": "medium", "platforms": ["blog", "linkedin"], "content_type": "blog"},
            {"topic": "Klaviyo vs Mailchimp — welches ist besser?", "angle": "Ehrlicher Vergleich für E-Commerce", "urgency": "medium", "platforms": ["blog", "linkedin"], "content_type": "blog"},
            {"topic": "Fiverr Gigs für Shopify-Experten", "angle": "So verdienst du €50-500 pro Gig", "urgency": "low", "platforms": ["linkedin", "twitter"], "content_type": "thread"},
            {"topic": "Upwork Profil optimieren — E-Commerce", "angle": "Wie ich meinen Stundensatz auf €75 erhöht habe", "urgency": "low", "platforms": ["linkedin", "reddit"], "content_type": "thread"},
        ]

    # Cache
    cache = {"niche": niche, "topics": opportunities,
             "fetched_raw": topics_found[:20], "generated_at": datetime.utcnow().isoformat()}
    (DATA_DIR / "trending_topics.json").write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    return opportunities


# ── 9. CONTENT PERFORMANCE PREDICTOR ─────────────────────────────────────────

async def predict_content_performance(content: str, platform: str) -> dict:
    """AI-powered performance prediction with improvement suggestions."""
    prompt = f"""Analyze this {platform} content and predict performance:

Content: {content[:500]}

Return JSON:
{{
  "engagement_score": 7,
  "viral_potential": 5,
  "seo_value": 8,
  "best_posting_time": "Tuesday 10:00 CET",
  "best_posting_day": "Tuesday",
  "estimated_reach": "500-2000",
  "estimated_engagement_rate": "3.2%",
  "strengths": ["strength 1", "strength 2"],
  "weaknesses": ["weakness 1", "weakness 2"],
  "improvements": [
    "Specific improvement 1",
    "Specific improvement 2",
    "Specific improvement 3"
  ],
  "optimized_version": "Rewritten version with all improvements applied"
}}"""
    raw = await _claude(prompt, max_tokens=1500)
    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(match.group()) if match else {}
    except Exception:
        result = {"raw": raw}
    result["platform"] = platform
    result["analyzed_at"] = datetime.utcnow().isoformat()
    return result


# ── 10. MASTER CONTENT PACKAGE ────────────────────────────────────────────────

async def generate_content_package(topic: str, product_url: str = "", languages: list = None) -> dict:
    """
    ONE topic → COMPLETE multi-platform, multilingual content package.
    All components generated in parallel.
    """
    langs = languages or ["de", "en"]
    log.info(f"Content Factory: generating full package for '{topic}'")
    t0 = time.monotonic()

    # Stage 1: Generate all base content in parallel
    _stage1_names = ["blog_de", "blog_en", "social_batch", "emails", "ad_copy", "image_prompts", "trending"]
    _stage1_fallbacks = [
        {"word_count": 0, "introduction": ""},  # blog_de
        {"word_count": 0, "introduction": ""},  # blog_en
        {},                                      # social_batch
        [],                                      # emails
        {},                                      # ad_copy
        {},                                      # image_prompts
        [],                                      # trending
    ]
    _stage1_raw = await asyncio.gather(
        generate_blog_post(topic, language="de"),
        generate_blog_post(topic, language="en"),
        generate_social_batch(topic),
        generate_email_sequence(topic, "Shopify-Händler und E-Commerce Unternehmer"),
        generate_ad_copy(topic, "Shopify store owners, 25-45, German-speaking"),
        generate_image_prompts(topic),
        find_trending_topics(topic),
        return_exceptions=True,
    )
    _stage1 = []
    for i, item in enumerate(_stage1_raw):
        if isinstance(item, Exception):
            log.warning(f"Content Factory Stage 1 '{_stage1_names[i]}' failed: {item}")
            _stage1.append(_stage1_fallbacks[i])
        else:
            _stage1.append(item)
    blog_de, blog_en, social_batch, emails, ad_copy, image_prompts, trending = _stage1

    # Stage 2: Quick social-specific content
    async def gen_youtube_script() -> dict:
        raw = await _claude(
            f"""Write a YouTube video script about: {topic}
Return JSON: {{
  "title": "SEO title (under 60 chars)",
  "description": "500-word video description with keywords + chapters",
  "script": "full 5-minute video script with [INTRO] [HOOK] [CONTENT] [CTA] markers",
  "tags": ["tag1", "tag2"] (10 tags),
  "thumbnail_text": "6-word thumbnail text",
  "chapters": ["0:00 - Intro", "1:30 - Topic", ...]
}}""", max_tokens=2000)
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            return json.loads(match.group()) if match else {"raw": raw}
        except Exception:
            return {"raw": raw}

    async def gen_press_release() -> str:
        return await _claude(
            f"""Write a professional German press release about: {topic}
Company: {BRAND_NAME} ({product_url or BRAND_URL})
Format: standard PR format with Headline, Subheadline, Lead paragraph, Body (3 paragraphs), Quote, Boilerplate
Length: 400-500 words""", max_tokens=1000)

    async def gen_tiktok_scripts() -> list:
        raw = await _claude(
            f"""Write 3 TikTok video scripts about: {topic}
Each script: hook (3 words that stop scroll) + 30-second script + trending audio suggestion
Return JSON array: [{{"hook": "...", "script": "...", "audio": "...", "hashtags": [...]}}]""",
            max_tokens=1000)
        try:
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            return json.loads(match.group()) if match else []
        except Exception:
            return []

    async def gen_product_description() -> str:
        if not product_url:
            return ""
        return await _claude(
            f"""Write a compelling product description for: {topic}
Product URL: {product_url}
Include: benefit-led headline, 3 key benefits (bullet points), social proof placeholder, urgency CTA
Length: 200 words. Language: German.""", max_tokens=500)

    _stage2_names = ["youtube", "press_release", "tiktok_scripts", "product_desc"]
    _stage2_fallbacks = [{}, "", [], ""]
    _stage2_raw = await asyncio.gather(
        gen_youtube_script(), gen_press_release(), gen_tiktok_scripts(), gen_product_description(),
        return_exceptions=True,
    )
    _stage2 = []
    for i, item in enumerate(_stage2_raw):
        if isinstance(item, Exception):
            log.warning(f"Content Factory Stage 2 '{_stage2_names[i]}' failed: {item}")
            _stage2.append(_stage2_fallbacks[i])
        else:
            _stage2.append(item)
    youtube, press_release, tiktok_scripts, product_desc = _stage2

    # Stage 3: Translate to additional languages
    blog_intro_de = blog_de.get("introduction", "")
    translations = {}
    if "fr" in langs or "es" in langs or "it" in langs:
        extra_langs = [l for l in langs if l not in ("de", "en")]
        if extra_langs and blog_intro_de:
            translations = await translate_content(blog_intro_de, extra_langs)

    elapsed = round(time.monotonic() - t0, 1)
    package = {
        "topic": topic,
        "generated_at": datetime.utcnow().isoformat(),
        "generation_time_s": elapsed,
        "blog": {"de": blog_de, "en": blog_en},
        "social": social_batch,
        "email_sequence": emails,
        "ad_copy": ad_copy,
        "image_prompts": image_prompts,
        "youtube": youtube,
        "tiktok_scripts": tiktok_scripts,
        "press_release_de": press_release,
        "product_description": product_desc,
        "trending_hooks": trending[:3],
        "translations": translations,
        "stats": {
            "blog_words_de": blog_de.get("word_count", 0),
            "blog_words_en": blog_en.get("word_count", 0),
            "social_posts_total": sum(len(v) for v in social_batch.items() if isinstance(v, list)),
            "email_count": len(emails),
            "ad_variations": 15 + 5 + 3,
            "languages": langs,
            "platforms": 9,
        }
    }

    # Save to disk
    safe_topic = re.sub(r'[^\w]', '_', topic)[:40]
    out_path = DATA_DIR / f"package_{safe_topic}_{int(time.time())}.json"
    out_path.write_text(json.dumps(package, ensure_ascii=False, indent=2))
    log.info(f"Content Factory: package done in {elapsed}s → {out_path}")

    # Telegram notification
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if token and chat_id:
            msg = (f"🏭 Content Factory fertig!\n"
                   f"📌 Topic: {topic}\n"
                   f"⏱ {elapsed}s\n"
                   f"📊 {package['stats']['blog_words_de']} Wörter Blog DE\n"
                   f"📱 {len(social_batch.get('instagram', []))}x Instagram Posts\n"
                   f"✉️ {len(emails)}x Email Sequenz\n"
                   f"🎯 {package['stats']['ad_variations']} Ad Varianten")
            async with aiohttp.ClientSession() as s:
                await s.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             json={"chat_id": chat_id, "text": msg},
                             timeout=aiohttp.ClientTimeout(total=10))
    except Exception as e:
        log.warning(f"Telegram notify: {e}")

    return package
