#!/usr/bin/env python3
"""
Dropshipping & Print-on-Demand Automation
Vollautomatischer Workflow: Produkt → SEO → Shopify → Social Media

Integriert:
  - Geheimwaffe: Winning-Product-Research (Perplexity/Ollama)
  - Shopify:     Produkt anlegen via Admin API
  - Printify:    Print-on-Demand Produkte erstellen & veröffentlichen
  - Ollama:      Lokale KI für SEO-Optimierung

Setup:
  Shopify:  SHOPIFY_ACCESS_TOKEN, SHOPIFY_SHOP_DOMAIN
  Printify: https://printify.com/app/account/connections — ENV: PRINTIFY_API_KEY, PRINTIFY_SHOP_ID
  Ollama:   OLLAMA_HOST (default: http://localhost:11434)
  Perplexity (optional): PERPLEXITY_API_KEY
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger("DropshippingAutomation")

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    log.warning("aiohttp nicht installiert — `pip install aiohttp`")

OLLAMA_BASE = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_SMART_MODEL", os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2:latest"))
PERPLEXITY_KEY = os.getenv("PERPLEXITY_API_KEY", "")

_TIMEOUT = aiohttp.ClientTimeout(total=120) if HAS_AIOHTTP else None


def _session(total: int = 120):
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=total))


# ---------------------------------------------------------------------------
# Module-level SEO helpers
# ---------------------------------------------------------------------------

async def _ollama_generate(prompt: str) -> str:
    """Call local Ollama /api/generate and return the response string."""
    if not HAS_AIOHTTP:
        return ""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    try:
        async with _session(120) as s:
            async with s.post(f"{OLLAMA_BASE}/api/generate", json=payload) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("response", "")
                log.warning("Ollama HTTP %d", r.status)
                return ""
    except Exception as e:
        log.warning("Ollama nicht erreichbar: %s", e)
        return ""


async def generate_seo_content(
    title: str,
    description: str,
    platform: str = "shopify",
) -> Dict[str, Any]:
    """
    Generate SEO-optimised content for a product using local Ollama.

    Args:
        title:       original product title
        description: original product description
        platform:    target platform hint ("shopify", "etsy", "gumroad", …)

    Returns:
        {
          "title":            SEO-optimised title,
          "description":      SEO-optimised description (HTML for Shopify),
          "tags":             list of keyword tags,
          "meta_description": short meta description (max 160 chars),
        }
    """
    prompt = (
        f"Du bist ein SEO-Experte für {platform}-Shops. "
        f"Erstelle eine SEO-optimierte Version für folgendes Produkt.\n\n"
        f"Originaltitel: {title}\n"
        f"Originalbeschreibung: {description}\n\n"
        f"Antwort als JSON mit diesen Feldern:\n"
        f"- title: SEO-optimierter Titel (max. 70 Zeichen)\n"
        f"- description: Ausführliche SEO-Produktbeschreibung mit Keywords (HTML erlaubt)\n"
        f"- tags: Array von 10 relevanten Keywords\n"
        f"- meta_description: Kurzbeschreibung für Google (max. 160 Zeichen)\n\n"
        f"Antworte NUR mit validem JSON, kein weiterer Text."
    )

    raw = await _ollama_generate(prompt)

    # Try to parse JSON from Ollama response
    if raw:
        try:
            # Ollama sometimes wraps JSON in markdown code fences
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            result = json.loads(cleaned.strip())
            if isinstance(result, dict):
                result.setdefault("title", title)
                result.setdefault("description", description)
                result.setdefault("tags", [])
                result.setdefault("meta_description", description[:160])
                return result
        except (json.JSONDecodeError, IndexError):
            log.warning("Ollama-Antwort kein valides JSON — Fallback")

    # Fallback: return structured mock with original data
    log.info("SEO-Generierung: Fallback zu Beispieldaten (Ollama nicht verfügbar)")
    return {
        "title": f"{title} | Bestseller {datetime.now().year}",
        "description": (
            f"<p>{description}</p>"
            f"<p><strong>Warum bei uns kaufen?</strong> Schnelle Lieferung, "
            f"geprüfte Qualität, 30 Tage Rückgaberecht.</p>"
        ),
        "tags": [title.lower(), platform, "bestseller", "angebot", "kaufen",
                 "qualität", "schnell", "sicher", "günstig", "empfehlung"],
        "meta_description": description[:160],
        "_demo": True,
    }


async def get_keyword_suggestions(niche: str) -> List[str]:
    """
    Generate keyword suggestions for a niche.

    Uses Perplexity API (real-time web) if PERPLEXITY_API_KEY is set,
    otherwise generates via Ollama locally.

    Args:
        niche: product niche or category (e.g. "fitness", "gaming")

    Returns list of keyword strings.
    """
    if PERPLEXITY_KEY and HAS_AIOHTTP:
        try:
            headers = {
                "Authorization": f"Bearer {PERPLEXITY_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "sonar-pro",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Gib mir 20 SEO-Keywords mit hohem Suchvolumen für die Nische '{niche}' "
                            f"im E-Commerce (Shopify/Etsy). Nur eine kommaseparierte Liste, kein weiterer Text."
                        ),
                    }
                ],
                "max_tokens": 400,
                "temperature": 0.3,
            }
            async with _session(30) as s:
                async with s.post("https://api.perplexity.ai/chat/completions",
                                  headers=headers, json=payload) as r:
                    if r.status == 200:
                        data = await r.json()
                        content = data["choices"][0]["message"]["content"]
                        keywords = [k.strip() for k in content.split(",") if k.strip()]
                        log.info("Perplexity Keywords: %d für '%s'", len(keywords), niche)
                        return keywords
        except Exception as e:
            log.warning("Perplexity Keyword-Fehler: %s — Fallback zu Ollama", e)

    # Ollama fallback
    prompt = (
        f"Gib mir 20 SEO-Keywords mit hohem Suchvolumen für die E-Commerce-Nische '{niche}'. "
        f"Antworte nur mit einer kommaseparierten Liste. Kein weiterer Text."
    )
    raw = await _ollama_generate(prompt)
    if raw:
        keywords = [k.strip() for k in raw.split(",") if k.strip()]
        if keywords:
            return keywords[:20]

    # Static fallback
    base = niche.lower()
    return [
        f"{base} kaufen", f"{base} online", f"bester {base}", f"{base} günstig",
        f"{base} shop", f"{base} angebot", f"{base} bestseller", f"{base} test",
        f"{base} empfehlung", f"{base} vergleich", f"top {base}", f"{base} 2026",
        f"{base} neu", f"{base} preis", f"{base} qualität",
    ]


# ---------------------------------------------------------------------------
# DropshippingWorkflow
# ---------------------------------------------------------------------------

class DropshippingWorkflow:
    """
    End-to-end dropshipping automation:
      1. find_trending_products  — research via Geheimwaffe (Perplexity/Ollama)
      2. optimize_product_seo    — Ollama-powered SEO title/description/tags
      3. create_shopify_product  — publish to Shopify Admin API
      4. promote_to_social       — post to configured social platforms
      5. full_pipeline           — runs all steps and returns a report
    """

    SOCIAL_PLATFORMS = ["Pinterest", "Instagram", "Facebook", "TikTok"]

    async def find_trending_products(
        self,
        niche: str = "",
        limit: int = 10,
    ) -> List[Dict]:
        """
        Find trending/winning products using the Geheimwaffe module.

        Falls back to structured mock data if Geheimwaffe isn't available
        or APIs aren't configured.

        Args:
            niche: product category/niche to focus on (empty = all niches)
            limit: number of products to return
        """
        log.info("[1/4] Suche Trending-Produkte — Nische: '%s'", niche or "allgemein")

        try:
            from modules.geheimwaffe import find_winning_products
            products = await find_winning_products(niche=niche or None)
            if products:
                log.info("Geheimwaffe: %d Produkte gefunden", len(products))
                return products[:limit]
        except ImportError:
            log.warning("Geheimwaffe-Modul nicht verfügbar — Beispieldaten")
        except Exception as e:
            log.warning("Geheimwaffe Fehler: %s — Fallback zu Beispieldaten", e)

        # Mock data fallback
        niche_label = niche or "E-Commerce"
        return [
            {
                "title": f"{niche_label} Produkt {i + 1}",
                "niche": niche_label,
                "trend_score": round(9.5 - i * 0.3, 1),
                "profit_margin": round(45.0 - i * 2, 1),
                "competition": "mittel",
                "price_suggestion_eur": round(29.99 + i * 5, 2),
                "description": (
                    f"Hochwertiges {niche_label}-Produkt mit starker Nachfrage. "
                    f"Ideal für Dropshipping-Shops."
                ),
                "supplier": "AliExpress / CJ Dropshipping",
                "_demo": True,
            }
            for i in range(min(limit, 10))
        ]

    async def optimize_product_seo(self, product_data: Dict) -> Dict:
        """
        Generate SEO-optimised title, description, and tags for a product via Ollama.

        Args:
            product_data: dict with at least 'title' and optionally 'description'

        Returns product_data enriched with 'seo' key containing SEO fields.
        """
        log.info("[2/4] SEO-Optimierung: '%s'", product_data.get("title", "?"))

        title = product_data.get("title", "")
        description = product_data.get("description", "")

        seo = await generate_seo_content(title, description, platform="shopify")
        product_data["seo"] = seo

        log.info(
            "SEO fertig — Titel: '%s' | Tags: %d",
            seo.get("title", title),
            len(seo.get("tags", [])),
        )
        return product_data

    async def create_shopify_product(self, product_data: Dict) -> Dict:
        """
        Create a Shopify product using the project's shopify_client module.

        Falls back to demo mode if Shopify credentials aren't configured.

        Args:
            product_data: dict with 'title', 'description', optionally 'seo', 'price_suggestion_eur'

        Returns Shopify product response (or mock on demo mode).
        """
        log.info("[3/4] Shopify Produkt anlegen: '%s'", product_data.get("title", "?"))

        seo = product_data.get("seo", {})
        title = seo.get("title") or product_data.get("title", "Neues Produkt")
        body_html = seo.get("description") or product_data.get("description", "")
        tags = ", ".join(seo.get("tags", []))
        price = str(product_data.get("price_suggestion_eur", 29.99))

        shopify_payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "tags": tags,
                "status": "draft",
                "variants": [{"price": price, "inventory_management": "shopify"}],
            }
        }

        shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_SUITE_ACCESS_TOKEN", "")
        shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")

        if shopify_token and shopify_domain and HAS_AIOHTTP:
            try:
                url = f"https://{shopify_domain}/admin/api/2024-01/products.json"
                headers = {
                    "X-Shopify-Access-Token": shopify_token,
                    "Content-Type": "application/json",
                }
                async with _session(30) as s:
                    async with s.post(url, headers=headers, json=shopify_payload) as r:
                        if r.status in (200, 201):
                            data = await r.json()
                            product = data.get("product", {})
                            log.info("Shopify Produkt erstellt — ID: %s", product.get("id"))
                            return {"success": True, "shopify_product": product}
                        body = await r.text()
                        log.warning("Shopify HTTP %d: %s", r.status, body[:200])
            except Exception as e:
                log.error("Shopify Fehler: %s — Demo-Modus", e)
        else:
            if not shopify_token:
                log.info("SHOPIFY_ACCESS_TOKEN fehlt — Demo-Modus (kein echter Upload)")
            if not shopify_domain:
                log.info("SHOPIFY_SHOP_DOMAIN fehlt — Demo-Modus")

        # Demo mode
        mock_id = abs(hash(title)) % 1_000_000
        return {
            "success": True,
            "shopify_product": {
                "id": mock_id,
                "title": title,
                "status": "draft",
                "admin_url": f"https://{shopify_domain or 'yourstore.myshopify.com'}/admin/products/{mock_id}",
            },
            "_demo": True,
        }

    async def promote_to_social(self, product_data: Dict) -> Dict[str, Any]:
        """
        Post the product to configured social platforms.

        Checks for platform-specific tokens in ENV; logs a warning and skips
        any platform that isn't configured.

        Supported platforms:
          - Pinterest:  PINTEREST_ACCESS_TOKEN
          - Instagram:  INSTAGRAM_ACCESS_TOKEN
          - Facebook:   FACEBOOK_PAGE_ACCESS_TOKEN
          - TikTok:     TIKTOK_ACCESS_TOKEN

        Args:
            product_data: dict with 'title', 'description', optionally 'seo'

        Returns dict with per-platform status.
        """
        log.info("[4/4] Social-Media-Promotion für: '%s'", product_data.get("title", "?"))

        seo = product_data.get("seo", {})
        title = seo.get("title") or product_data.get("title", "")
        description = seo.get("description") or product_data.get("description", "")
        tags = seo.get("tags", [])
        hashtags = " ".join(f"#{t.replace(' ', '')}" for t in tags[:10])

        platform_tokens = {
            "Pinterest": os.getenv("PINTEREST_ACCESS_TOKEN", ""),
            "Instagram": os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
            "Facebook": os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", ""),
            "TikTok": os.getenv("TIKTOK_ACCESS_TOKEN", ""),
        }

        results: Dict[str, Any] = {}
        for platform, token in platform_tokens.items():
            if not token:
                log.info("%s: Token fehlt — übersprungen", platform)
                results[platform] = {
                    "status": "skipped",
                    "message": f"{platform.upper()}_ACCESS_TOKEN nicht gesetzt",
                }
                continue

            # Actual API calls would go here per platform.
            # For now, we log the attempt and return a demo result since each
            # platform's posting API requires different OAuth flows and endpoints.
            log.info("%s: würde posten — '%s' %s", platform, title[:50], hashtags[:80])
            results[platform] = {
                "status": "demo",
                "message": f"Demo-Modus: Post für '{title[:50]}' vorbereitet",
                "caption": f"{title}\n\n{description[:200]}\n\n{hashtags}",
            }

        posted = sum(1 for v in results.values() if v.get("status") not in ("skipped",))
        log.info("Social-Promotion: %d/%d Plattformen aktiv", posted, len(platform_tokens))
        return results

    async def full_pipeline(self, niche: str = "", count: int = 3) -> Dict[str, Any]:
        """
        Run the complete dropshipping pipeline end-to-end.

        Steps:
          1. find_trending_products
          2. optimize_product_seo
          3. create_shopify_product
          4. promote_to_social

        Args:
            niche: product niche to target (empty = all niches)
            count: number of products to process

        Returns:
            {
              "niche":     niche string,
              "processed": number of products completed,
              "products":  list of per-product results,
              "summary":   human-readable summary string,
            }
        """
        log.info("=== Dropshipping Full Pipeline START — Nische: '%s', Count: %d ===",
                 niche or "allgemein", count)
        started_at = datetime.now()

        products = await self.find_trending_products(niche=niche, limit=count)
        results = []

        for i, product in enumerate(products[:count]):
            log.info("--- Produkt %d/%d: '%s' ---", i + 1, count, product.get("title", "?"))
            try:
                product = await self.optimize_product_seo(product)
                shopify_result = await self.create_shopify_product(product)
                social_result = await self.promote_to_social(product)

                results.append({
                    "title": product.get("seo", {}).get("title") or product.get("title"),
                    "niche": product.get("niche", niche),
                    "shopify": shopify_result,
                    "social": social_result,
                    "seo_tags": product.get("seo", {}).get("tags", []),
                    "demo": product.get("_demo", False),
                })
            except Exception as e:
                log.error("Pipeline-Fehler für Produkt %d: %s", i + 1, e)
                results.append({"title": product.get("title", "?"), "error": str(e)})

        elapsed = (datetime.now() - started_at).total_seconds()
        success_count = sum(1 for r in results if "error" not in r)
        summary = (
            f"Pipeline abgeschlossen in {elapsed:.1f}s | "
            f"{success_count}/{len(results)} Produkte erfolgreich verarbeitet"
        )
        log.info("=== Dropshipping Full Pipeline ENDE — %s ===", summary)

        # BrutusCore: Dropshipping Produkte auf allen Kanälen promoten
        if success_count > 0:
            try:
                from modules.brutus_core import fire as brutus_fire
                await brutus_fire(
                    title=f"🛒 {success_count} neue Dropshipping-Produkte live!",
                    body=f"Frisch importiert in der Nische '{niche or 'Trending'}' — direkt verfügbar im Shop.",
                    link="https://ineedit.com.co/collections/trending-now",
                    niche=f"dropshipping {niche}",
                    tags=["dropshipping", "neu", niche.replace(" ", "-") if niche else "trending"]
                )
            except Exception:
                pass

        return {
            "niche": niche or "allgemein",
            "processed": success_count,
            "total": len(results),
            "products": results,
            "elapsed_seconds": round(elapsed, 1),
            "summary": summary,
        }


# ---------------------------------------------------------------------------
# PrintOnDemandWorkflow
# ---------------------------------------------------------------------------

class PrintOnDemandWorkflow:
    """
    End-to-end Print-on-Demand automation:
      1. create_pod_product  — create Printify product with AI-generated description
      2. publish_to_shopify  — publish via printify_automation.publish_product_to_shopify
      3. full_pipeline       — for each design: create → publish → promote

    Setup:
      Printify: https://printify.com/app/account/connections
               ENV: PRINTIFY_API_KEY, PRINTIFY_SHOP_ID
    """

    # Printify blueprint IDs for common base products
    BLUEPRINT_MAP = {
        "t-shirt": 5,          # Bella+Canvas 3001
        "hoodie": 9,           # Gildan 18500
        "mug": 366,            # White Mug 11oz
        "poster": 43,          # Enhanced Matte Paper Poster
        "tote": 292,           # Canvas Tote Bag
        "phone-case": 370,     # Tough Case
    }

    # Default print provider IDs (Printify)
    PRINT_PROVIDER_MAP = {
        "t-shirt": 29,   # Monster Digital (US)
        "hoodie": 29,
        "mug": 27,       # Printify Express
        "poster": 30,    # Printify
        "tote": 29,
        "phone-case": 27,
    }

    def __init__(self):
        self._ds_workflow = DropshippingWorkflow()

    async def create_pod_product(
        self,
        design_name: str,
        design_description: str,
        base_product: str = "t-shirt",
    ) -> Dict[str, Any]:
        """
        Create a Printify product with an AI-generated description.

        Args:
            design_name:        name/theme of the design (e.g. "Cosmic Cat")
            design_description: short design description for AI prompt
            base_product:       base product type — one of:
                                 t-shirt, hoodie, mug, poster, tote, phone-case

        Returns Printify product response dict (or demo dict if API unavailable).

        Setup: https://printify.com/app/account/connections
        """
        log.info("[POD 1/3] Erstelle POD-Produkt: '%s' auf %s", design_name, base_product)

        # Generate AI description
        seo = await generate_seo_content(
            title=f"{design_name} {base_product.capitalize()}",
            description=design_description,
            platform="shopify",
        )

        blueprint_id = self.BLUEPRINT_MAP.get(base_product, 5)
        print_provider_id = self.PRINT_PROVIDER_MAP.get(base_product, 29)

        printify_payload = {
            "title": seo.get("title", f"{design_name} {base_product.capitalize()}"),
            "description": seo.get("description", design_description),
            "blueprint_id": blueprint_id,
            "print_provider_id": print_provider_id,
            "variants": [],  # Caller must populate with variant IDs from Printify catalogue
            "print_areas": [],
            "tags": seo.get("tags", []),
        }

        printify_token = os.getenv("PRINTIFY_API_KEY", "")
        printify_shop = os.getenv("PRINTIFY_SHOP_ID", "")

        if printify_token and printify_shop and HAS_AIOHTTP:
            try:
                url = f"https://api.printify.com/v1/shops/{printify_shop}/products.json"
                headers = {
                    "Authorization": f"Bearer {printify_token}",
                    "Content-Type": "application/json",
                }
                async with _session(30) as s:
                    async with s.post(url, headers=headers, json=printify_payload) as r:
                        if r.status in (200, 201):
                            data = await r.json()
                            pid = data.get("id", "unknown")
                            log.info("Printify Produkt erstellt — ID: %s", pid)
                            return {"success": True, "printify_product": data, "product_id": pid}
                        body = await r.text()
                        log.warning("Printify HTTP %d: %s", r.status, body[:200])
            except Exception as e:
                log.error("Printify Fehler: %s — Demo-Modus", e)
        else:
            if not printify_token:
                log.info(
                    "PRINTIFY_API_KEY fehlt — Demo-Modus. "
                    "Zugangsdaten: https://printify.com/app/account/connections"
                )

        # Demo mode
        mock_id = f"demo_{abs(hash(design_name)) % 1_000_000}"
        return {
            "success": True,
            "product_id": mock_id,
            "printify_product": {
                "id": mock_id,
                "title": seo.get("title"),
                "blueprint_id": blueprint_id,
                "print_provider_id": print_provider_id,
            },
            "seo": seo,
            "_demo": True,
        }

    async def publish_to_shopify(self, printify_product_id: str) -> Dict[str, Any]:
        """
        Publish an existing Printify product to the connected Shopify store.

        Delegates to printify_automation.publish_product_to_shopify().

        Args:
            printify_product_id: Printify product ID string

        Returns Printify publish response.
        """
        log.info("[POD 2/3] Veröffentliche Printify Produkt %s auf Shopify", printify_product_id)

        if str(printify_product_id).startswith("demo_"):
            log.info("Demo-Produkt — echter Shopify-Upload übersprungen")
            return {
                "success": True,
                "message": f"Demo-Modus: Produkt {printify_product_id} würde veröffentlicht",
                "_demo": True,
            }

        try:
            from modules.printify_automation import publish_product_to_shopify
            result = await publish_product_to_shopify(printify_product_id)
            log.info("Printify → Shopify veröffentlicht: %s", printify_product_id)
            return {"success": True, "result": result}
        except ImportError:
            log.warning("printify_automation nicht verfügbar — Demo-Modus")
        except Exception as e:
            log.error("Printify publish Fehler: %s", e)
            return {"success": False, "error": str(e)}

        return {
            "success": True,
            "message": f"Demo-Modus: Produkt {printify_product_id} würde veröffentlicht",
            "_demo": True,
        }

    async def full_pipeline(self, designs: List[Dict]) -> Dict[str, Any]:
        """
        Run the complete POD pipeline for a list of designs.

        Each design dict should have:
          - name:          design name/theme (required)
          - description:   short design description (required)
          - base_product:  "t-shirt" | "hoodie" | "mug" | "poster" | "tote" | "phone-case"
                           (default: "t-shirt")

        Steps per design:
          1. create_pod_product  — Printify product + AI description
          2. publish_to_shopify  — push to Shopify
          3. promote_to_social   — social media post

        Returns:
            {
              "processed": count of designs completed,
              "designs":   list of per-design results,
              "summary":   human-readable summary,
            }
        """
        log.info("=== POD Full Pipeline START — %d Designs ===", len(designs))
        started_at = datetime.now()
        results = []

        for i, design in enumerate(designs):
            name = design.get("name", f"Design {i + 1}")
            desc = design.get("description", "")
            base = design.get("base_product", "t-shirt")

            log.info("--- POD %d/%d: '%s' auf %s ---", i + 1, len(designs), name, base)
            try:
                pod_result = await self.create_pod_product(name, desc, base)
                product_id = pod_result.get("product_id", "")

                publish_result = await self.publish_to_shopify(product_id)

                # Prepare product_data for social promotion
                product_data = {
                    "title": name,
                    "description": desc,
                    "seo": pod_result.get("seo", {}),
                }
                social_result = await self._ds_workflow.promote_to_social(product_data)

                results.append({
                    "design_name": name,
                    "base_product": base,
                    "product_id": product_id,
                    "pod": pod_result,
                    "publish": publish_result,
                    "social": social_result,
                    "demo": pod_result.get("_demo", False),
                })
            except Exception as e:
                log.error("POD-Pipeline-Fehler für '%s': %s", name, e)
                results.append({"design_name": name, "error": str(e)})

        elapsed = (datetime.now() - started_at).total_seconds()
        success_count = sum(1 for r in results if "error" not in r)
        summary = (
            f"POD Pipeline abgeschlossen in {elapsed:.1f}s | "
            f"{success_count}/{len(results)} Designs erfolgreich verarbeitet"
        )
        log.info("=== POD Full Pipeline ENDE — %s ===", summary)

        # BrutusCore: neue POD Produkte überall promoten
        if success_count > 0:
            try:
                from modules.brutus_core import fire as brutus_fire
                names = [r.get("design_name","Design") for r in results if "error" not in r][:2]
                for name in names:
                    await brutus_fire(
                        title=f"🎨 Neu: {name} — Print on Demand",
                        body=f"Frisch designt und sofort bestellbar: {name}. Individuell bedruckt, direkt zu dir geliefert.",
                        link="https://ineedit.com.co",
                        niche="print on demand geschenke design",
                        tags=["pod", "neu", "geschenk", "printify"]
                    )
            except Exception:
                pass

        return {
            "processed": success_count,
            "total": len(results),
            "designs": results,
            "elapsed_seconds": round(elapsed, 1),
            "summary": summary,
        }


# ---------------------------------------------------------------------------
# Quick demo runner
# ---------------------------------------------------------------------------

async def _demo():
    """Quick smoke-test for both workflows."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(name)s  %(levelname)s  %(message)s")
    print("\n=== Dropshipping Workflow Demo ===")
    ds = DropshippingWorkflow()
    ds_report = await ds.full_pipeline(niche="fitness", count=2)
    print(json.dumps(ds_report, indent=2, ensure_ascii=False, default=str))

    print("\n=== Print-on-Demand Workflow Demo ===")
    pod = PrintOnDemandWorkflow()
    pod_report = await pod.full_pipeline([
        {"name": "Cosmic Cat", "description": "Cute cat in space design", "base_product": "t-shirt"},
        {"name": "Mountain Sunrise", "description": "Minimalist mountain peak at sunrise", "base_product": "mug"},
    ])
    print(json.dumps(pod_report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(_demo())
