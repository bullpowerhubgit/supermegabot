#!/usr/bin/env python3
"""
GEHEIMWAFFE - Automated Shopify Expansion & Marketing Engine
Winning Products + AI Content + Auto-Ads + SEO + Viral Growth
100% lokal via Ollama + Shopify APIs
"""

import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from modules.ai_client import ai_complete

log = logging.getLogger("Geheimwaffe")

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "geheimwaffe.db"
OLLAMA_BASE = os.getenv("OLLAMA_HOST", "http://localhost:11434")
SHOPIFY_URL = os.getenv("SHOPIFY_STORE_URL", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


_DB_MAX_ROWS = {
    "winning_products":  500,
    "generated_content": 1000,
    "campaigns":         200,
}

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS winning_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            niche TEXT,
            trend_score REAL,
            profit_margin REAL,
            competition TEXT,
            source TEXT,
            data TEXT,
            found_at TEXT
        );
        CREATE TABLE IF NOT EXISTS generated_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            product TEXT,
            content TEXT,
            platform TEXT,
            generated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            type TEXT,
            status TEXT DEFAULT 'draft',
            content TEXT,
            results TEXT,
            created_at TEXT
        );
    """)
    conn.commit()
    # Alte Einträge löschen wenn Tabellen zu groß werden
    for table, max_rows in _DB_MAX_ROWS.items():
        conn.execute(
            f"DELETE FROM {table} WHERE id IN "
            f"(SELECT id FROM {table} ORDER BY id ASC LIMIT MAX(0, (SELECT COUNT(*) FROM {table}) - ?))",
            (max_rows,)
        )
    conn.commit()
    return conn


async def _ai(prompt: str, system: str = "", task: str = "smart") -> str:
    """Local Ollama AI call"""
    if not HAS_AIOHTTP:
        return "aiohttp nicht installiert"
    model_map = {
        "fast": os.getenv("OLLAMA_FAST_MODEL", "llama3.2:latest"),
        "smart": os.getenv("OLLAMA_SMART_MODEL", "gemma2:latest"),
        "code": os.getenv("OLLAMA_CODE_MODEL", "codellama:latest"),
    }
    model = model_map.get(task, os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2:latest"))
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
            async with s.post(f"{OLLAMA_BASE}/api/chat", json={"model": model, "messages": messages, "stream": False}) as r:
                if r.status == 200:
                    d = await r.json()
                    return d.get("message", {}).get("content", "")
    except Exception as e:
        return f"AI Fehler: {e}"
    return "Keine Antwort"


async def _perplexity(query: str, system: str = "") -> str:
    """AI-Recherche via ai_complete() — automatischer Provider-Fallback."""
    return await ai_complete(query, system=system, model_hint="smart", max_tokens=2000)


# ---------------------------------------------------------------------------
# 1. Winning Product Finder
# ---------------------------------------------------------------------------

async def find_winning_products(niche: str = None) -> List[Dict]:
    """Winning Product Research — Perplexity (Echtzeit-Web) oder Ollama (lokal)"""
    niche_str = niche or "allgemein profitable Nischen 2026"

    system = "Du bist ein E-Commerce-Experte für Shopify Dropshipping und Winning Products. Antworte auf Deutsch."

    prompt = f"""Recherchiere aktuelle Winning Products für Shopify Dropshipping in der Nische: {niche_str}

Analysiere aktuelle Trends (TikTok, Amazon, AliExpress, Google Trends).
Gib eine Liste von 5 profitablen Produkten als JSON zurück:
[{{
  "title": "Produktname",
  "niche": "Nische",
  "why_winning": "Warum dieses Produkt viral geht",
  "target_audience": "Zielgruppe",
  "selling_price": "25-45€",
  "profit_margin": "60-80%",
  "trend_score": 8.5,
  "marketing_angle": "Hauptmarketing-Aussage",
  "competition": "niedrig/mittel/hoch",
  "source": "TikTok/Amazon/Google Trends"
}}]
Fokus auf: Lösung eines Problems, emotionalen Nutzen, Viralitätspotenzial.
Nur JSON ausgeben."""
    log.info(f"Winning Product Suche für Nische: {niche_str}")
    result = await _perplexity(prompt, system=system)

    products = []
    try:
        import re
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            products = json.loads(json_match.group())
    except Exception:
        products = [{"title": "AI Analyse", "result": result}]

    # Save to DB
    conn = _db()
    for p in products:
        conn.execute(
            "INSERT INTO winning_products (title,niche,trend_score,profit_margin,competition,source,data,found_at) VALUES (?,?,?,?,?,?,?,?)",
            (p.get("title",""), p.get("niche",""), p.get("trend_score",0), 0, p.get("competition",""), "ai", json.dumps(p), datetime.now().isoformat())
        )
    conn.commit()
    conn.close()
    return products


# ---------------------------------------------------------------------------
# 2. AI Content Generator
# ---------------------------------------------------------------------------

async def generate_product_listing(product_name: str, niche: str = "") -> Dict:
    """Generate complete Shopify product listing"""
    prompt = f"""Erstelle ein vollständiges Shopify-Produkt-Listing für: {product_name}
{f'Nische: {niche}' if niche else ''}

Format (JSON):
{{
  "title": "Catchy Produkttitel mit Keyword",
  "description_html": "<p>Ansprechende HTML-Beschreibung mit Bullet Points...</p>",
  "seo_title": "SEO-optimierter Titel (max 70 Zeichen)",
  "seo_description": "Meta-Beschreibung (max 160 Zeichen)",
  "tags": ["tag1", "tag2", "tag3"],
  "price_suggestion": "39.99",
  "compare_at_price": "79.99"
}}

Schreibe überzeugend, emotional, mit klarem Nutzen. Auf Deutsch."""

    result = await _ai(prompt, task="smart")

    content = {}
    try:
        import re
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            content = json.loads(json_match.group())
    except Exception:
        content = {"title": product_name, "description_html": result}

    # Save
    conn = _db()
    conn.execute("INSERT INTO generated_content (type,product,content,platform,generated_at) VALUES (?,?,?,?,?)",
                 ("product_listing", product_name, json.dumps(content), "shopify", datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return content


async def generate_social_content(product_name: str, platform: str = "tiktok") -> Dict:
    """Generate viral social media content"""
    platform_prompts = {
        "tiktok": "TikTok-Video-Script (15-30 Sek) mit Hook, Problem, Lösung, CTA. Viral-optimiert.",
        "instagram": "Instagram-Post mit Caption, Hashtags und Story-Ideen.",
        "facebook": "Facebook-Ad-Text mit Headline, Primary Text und Description.",
        "email": "E-Mail-Marketing mit Betreff, Preview-Text und vollständigem E-Mail-Text.",
    }

    prompt = f"""Erstelle {platform_prompts.get(platform, 'Marketing-Content')} für: {product_name}

Format (JSON):
{{
  "headline": "Hauptüberschrift",
  "content": "Haupttext/Script",
  "hashtags": ["#tag1", "#tag2"],
  "cta": "Call-to-Action",
  "viral_hook": "Was macht es viral?",
  "target_emotion": "Welche Emotion wird angesprochen?"
}}

Auf Deutsch, für deutschen Markt optimiert."""

    result = await _ai(prompt, task="smart")

    content = {}
    try:
        import re
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            content = json.loads(json_match.group())
    except Exception:
        content = {"headline": product_name, "content": result}

    conn = _db()
    conn.execute("INSERT INTO generated_content (type,product,content,platform,generated_at) VALUES (?,?,?,?,?)",
                 ("social_content", product_name, json.dumps(content), platform, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return content


async def generate_ad_copy(product_name: str, budget: str = "niedrig") -> Dict:
    """Generate complete ad campaigns"""
    prompt = f"""Erstelle komplette Werbekampagne für: {product_name}
Budget-Level: {budget}

JSON Format:
{{
  "facebook_ad": {{
    "headline": "...",
    "primary_text": "...",
    "description": "...",
    "cta": "Jetzt kaufen"
  }},
  "google_ad": {{
    "headline1": "...",
    "headline2": "...",
    "description1": "...",
    "description2": "..."
  }},
  "email_subject": "...",
  "email_preview": "...",
  "target_audience": "Zielgruppen-Beschreibung",
  "targeting_interests": ["Interesse1", "Interesse2"],
  "budget_recommendation": "Tagesbudget-Empfehlung"
}}"""

    result = await _ai(prompt, task="smart")

    campaign = {}
    try:
        import re
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            campaign = json.loads(json_match.group())
    except Exception:
        campaign = {"content": result}

    conn = _db()
    conn.execute("INSERT INTO campaigns (name,type,status,content,created_at) VALUES (?,?,?,?,?)",
                 (product_name, "ad_campaign", "draft", json.dumps(campaign), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return campaign


# ---------------------------------------------------------------------------
# 3. Shopify Auto-Actions
# ---------------------------------------------------------------------------

async def shopify_graphql(query: str, variables: Dict = None) -> Dict:
    if not SHOPIFY_URL or not SHOPIFY_TOKEN or not HAS_AIOHTTP:
        return {"error": "Shopify nicht konfiguriert"}
    store = SHOPIFY_URL.replace("https://", "").replace("http://", "").rstrip("/")
    url = f"https://{store}/admin/api/2024-10/graphql.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(url, json=payload, headers=headers) as r:
                return await r.json()
    except Exception as e:
        return {"error": str(e)}


async def get_store_analytics() -> Dict:
    """Get Shopify store analytics"""
    query = """
    {
      shop {
        name
        email
        myshopifyDomain
      }
      orders(first: 10, sortKey: CREATED_AT, reverse: true) {
        edges {
          node {
            id
            totalPriceSet { shopMoney { amount currencyCode } }
            createdAt
            displayFinancialStatus
          }
        }
      }
      products(first: 5) {
        edges {
          node {
            id
            title
            totalInventory
          }
        }
      }
    }
    """
    return await shopify_graphql(query)


async def create_product_in_shopify(listing: Dict) -> Dict:
    """Create product directly in Shopify"""
    mutation = """
    mutation productCreate($input: ProductInput!) {
      productCreate(input: $input) {
        product {
          id
          title
          handle
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    variables = {
        "input": {
            "title": listing.get("title", ""),
            "descriptionHtml": listing.get("description_html", ""),
            "seo": {
                "title": listing.get("seo_title", ""),
                "description": listing.get("seo_description", ""),
            },
            "tags": listing.get("tags", []),
        }
    }
    return await shopify_graphql(mutation, variables)


# ---------------------------------------------------------------------------
# 4. Auto-SEO Optimizer
# ---------------------------------------------------------------------------

async def optimize_all_products_seo() -> List[Dict]:
    """Auto-optimize SEO for all products"""
    # Get products
    query = "{ products(first: 10) { edges { node { id title description } } } }"
    result = await shopify_graphql(query)

    products = []
    try:
        edges = result.get("data", {}).get("products", {}).get("edges", [])
        for e in edges:
            p = e["node"]
            products.append(p)
    except Exception:
        pass

    if not products:
        return [{"error": "Keine Produkte gefunden oder Shopify nicht verbunden"}]

    results = []
    for product in products[:5]:
        seo_prompt = f"""Optimiere SEO für Shopify-Produkt:
Titel: {product.get('title', '')}
Aktuelle Beschreibung: {product.get('description', '')[:200]}

JSON ausgeben:
{{"seo_title": "optimierter Titel", "seo_description": "optimierte Meta-Beschreibung"}}"""

        seo_content = await _ai(seo_prompt, task="fast")
        results.append({"product": product.get("title"), "seo": seo_content})

    return results


# ---------------------------------------------------------------------------
# 5. Competitor Analysis
# ---------------------------------------------------------------------------

async def analyze_competitors(niche: str) -> Dict:
    """AI competitor analysis"""
    prompt = f"""Analysiere Top-Shopify-Konkurrenten in der Nische: {niche}

JSON Format:
{{
  "top_competitors": ["Store1", "Store2", "Store3"],
  "their_strengths": ["Stärke1", "Stärke2"],
  "their_weaknesses": ["Schwäche1", "Schwäche2"],
  "opportunities": ["Chance1", "Chance2", "Chance3"],
  "differentiation_strategy": "Wie du dich abhebst",
  "winning_angle": "Dein einzigartiger Vorteil",
  "pricing_strategy": "Preisstrategieempfehlung"
}}"""

    result = await _ai(prompt, task="smart")
    analysis = {}
    try:
        import re
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            analysis = json.loads(json_match.group())
    except Exception:
        analysis = {"result": result}

    return analysis


# ---------------------------------------------------------------------------
# 6. Revenue Forecast
# ---------------------------------------------------------------------------

async def generate_revenue_forecast(monthly_visitors: int = 1000, conversion_rate: float = 2.5, avg_order: float = 45.0) -> Dict:
    """Generate revenue forecast and growth plan"""
    monthly_revenue = monthly_visitors * (conversion_rate / 100) * avg_order

    prompt = f"""Erstelle einen 90-Tage-Wachstumsplan für einen Shopify Store:
Aktuelle Metriken:
- Monatliche Besucher: {monthly_visitors}
- Conversion Rate: {conversion_rate}%
- Durchschnittlicher Bestellwert: {avg_order}€
- Aktueller Monatsumsatz: ~{monthly_revenue:.0f}€

JSON Format:
{{
  "current_monthly": {monthly_revenue:.0f},
  "month1_target": "X€",
  "month2_target": "X€",
  "month3_target": "X€",
  "growth_actions": [
    {{"week": 1, "action": "...", "expected_impact": "..."}}
  ],
  "traffic_strategy": "...",
  "conversion_strategy": "...",
  "aov_strategy": "Durchschnittswert steigern durch..."
}}"""

    result = await _ai(prompt, task="smart")
    forecast = {}
    try:
        import re
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            forecast = json.loads(json_match.group())
    except Exception:
        forecast = {"result": result, "current_monthly": monthly_revenue}

    return forecast


# ---------------------------------------------------------------------------
# Main Entry: Full Automation Run
# ---------------------------------------------------------------------------

async def run_full_automation(niche: str = "General") -> Dict:
    """Run complete automation pipeline"""
    log.info(f"[Geheimwaffe] Full automation for niche: {niche}")
    results = {}

    # Step 1: Find winning products
    log.info("Step 1: Finding winning products...")
    products = await find_winning_products(niche)
    results["winning_products"] = products[:3]

    if products:
        top_product = products[0].get("title", niche)

        # Step 2: Generate listing
        log.info("Step 2: Generating product listing...")
        listing = await generate_product_listing(top_product, niche)
        results["listing"] = listing

        # Step 3: Generate social content
        log.info("Step 3: Generating social content...")
        tiktok = await generate_social_content(top_product, "tiktok")
        instagram = await generate_social_content(top_product, "instagram")
        results["social"] = {"tiktok": tiktok, "instagram": instagram}

        # Step 4: Ad campaigns
        log.info("Step 4: Generating ad campaigns...")
        ads = await generate_ad_copy(top_product)
        results["ads"] = ads

    # Step 5: Competitor analysis
    log.info("Step 5: Competitor analysis...")
    competitors = await analyze_competitors(niche)
    results["competitors"] = competitors

    # Step 6: Revenue forecast
    log.info("Step 6: Revenue forecast...")
    forecast = await generate_revenue_forecast()
    results["forecast"] = forecast

    results["timestamp"] = datetime.now().isoformat()
    results["niche"] = niche
    return results
