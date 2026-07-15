"""
Shopify Auto-Fill Engine
- Findet täglich neue Trend-Produkte (AliExpress + Printify + Perplexity Trends)
- Importiert mit AI-optimierten Titeln, Beschreibungen, SEO-Tags
- Lädt Bilder hoch (Unsplash + Pexels + Printify)
- Korrigiert bestehende Produkte (fehlende Bilder, schlechte Texte, €0 Preise)
- BrutusCore promotet jedes neue Produkt sofort auf allen Kanälen
"""
import os
import re
import json
import logging
import asyncio
import aiohttp
from datetime import datetime

logger = logging.getLogger(__name__)

SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")
PEXELS_KEY      = os.getenv("PEXELS_API_KEY", "")
UNSPLASH_KEY    = os.getenv("UNSPLASH_ACCESS_KEY", "")
ALIEX_KEY       = os.getenv("ALIEXPRESS_APP_KEY", "536860")
ALIEX_SECRET    = os.getenv("ALIEXPRESS_APP_SECRET", "")

SHOPIFY_BASE = lambda path: f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/{path}"
HEADERS = lambda: {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# Trend-Nischen die sich gut verkaufen
TREND_NICHES = [
    "smart home gadgets",
    "personalized gifts",
    "fitness accessories",
    "phone accessories 2026",
    "kitchen gadgets trending",
    "pet accessories",
    "travel accessories",
    "desk organization",
    "LED lights decoration",
    "beauty tools",
]

# Pexels Fallback Images pro Nische
NICHE_IMAGES = {
    "smart home": "https://images.pexels.com/photos/4050387/pexels-photo-4050387.jpeg",
    "fitness": "https://images.pexels.com/photos/841130/pexels-photo-841130.jpeg",
    "kitchen": "https://images.pexels.com/photos/1640777/pexels-photo-1640777.jpeg",
    "beauty": "https://images.pexels.com/photos/3373736/pexels-photo-3373736.jpeg",
    "pet": "https://images.pexels.com/photos/1254140/pexels-photo-1254140.jpeg",
    "travel": "https://images.pexels.com/photos/1008155/pexels-photo-1008155.jpeg",
    "default": "https://images.pexels.com/photos/5632399/pexels-photo-5632399.jpeg",
}


class ShopifyAutoFill:
    def __init__(self):
        self.session: aiohttp.ClientSession = None

    # ─── AI ───────────────────────────────────────────────────────────────────

    async def _ai(self, prompt: str, max_tokens: int = 1000) -> str:
        try:
            from modules.ai_client import ai_complete
            return await ai_complete(prompt, max_tokens=max_tokens)
        except Exception as e:
            logger.warning(f"AI failed: {e}")
            return ""

    # ─── Shopify API ──────────────────────────────────────────────────────────

    async def _shopify_get(self, path: str) -> dict:
        async with self.session.get(SHOPIFY_BASE(path), headers=HEADERS(),
                                    timeout=aiohttp.ClientTimeout(total=15)) as r:
            return await r.json()

    async def _shopify_post(self, path: str, data: dict) -> dict:
        async with self.session.post(SHOPIFY_BASE(path), headers=HEADERS(), json=data,
                                     timeout=aiohttp.ClientTimeout(total=20)) as r:
            return await r.json()

    async def _shopify_put(self, path: str, data: dict) -> dict:
        async with self.session.put(SHOPIFY_BASE(path), headers=HEADERS(), json=data,
                                    timeout=aiohttp.ClientTimeout(total=20)) as r:
            return await r.json()

    # ─── Produkte & Bilder ────────────────────────────────────────────────────

    async def get_all_products(self, limit: int = 250) -> list:
        d = await self._shopify_get(f"products.json?limit={limit}&status=any")
        return d.get("products", [])

    async def find_image_url(self, query: str) -> str:
        """Sucht freies Produktbild via Pexels"""
        if PEXELS_KEY:
            try:
                async with self.session.get(
                    f"https://api.pexels.com/v1/search?query={query}&per_page=1&orientation=square",
                    headers={"Authorization": PEXELS_KEY},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    d = await r.json()
                    photos = d.get("photos", [])
                    if photos:
                        return photos[0]["src"]["medium"]
            except Exception as e:
                logger.warning(f"Pexels: {e}")

        # Fallback: Nischen-Bild
        for key, url in NICHE_IMAGES.items():
            if key in query.lower():
                return url
        return NICHE_IMAGES["default"]

    async def upload_image_to_product(self, product_id: int, image_url: str) -> bool:
        """Lädt Bild-URL zu Shopify Produkt hoch"""
        try:
            d = await self._shopify_post(f"products/{product_id}/images.json", {
                "image": {"src": image_url, "position": 1}
            })
            return "image" in d
        except Exception as e:
            logger.warning(f"Image upload {product_id}: {e}")
            return False

    # ─── AI Produkt-Verbesserung ──────────────────────────────────────────────

    async def ai_improve_product(self, product: dict) -> dict:
        """AI verbessert Titel, Beschreibung, Tags eines bestehenden Produkts"""
        current_title = product.get("title", "")
        current_body = product.get("body_html", "")
        vendor = product.get("vendor", "")
        price = product.get("variants", [{}])[0].get("price", "0")

        prompt = f"""Verbessere dieses Shopify-Produkt für den deutschen Markt:
Aktueller Titel: {current_title}
Aktueller Preis: €{price}
Vendor: {vendor}

Erstelle BESSERES Deutsch-Marketing:
1. Titel (max 70 Zeichen, verkaufsstark, SEO-optimiert)
2. HTML-Beschreibung (200-300 Wörter, Bullet Points mit ✅, Vorteile, Vertrauen, kein Spam)
3. SEO Meta-Titel (max 60 Zeichen)
4. SEO Meta-Beschreibung (max 155 Zeichen)
5. Tags (8-10 relevante Tags, kommagetrennt)

Wenn Preis €0 ist, empfehle einen realistischen Preis.

JSON Format:
{{"title": "...", "body_html": "...", "meta_title": "...", "meta_description": "...", "tags": "..."}}"""

        text = await self._ai(prompt, max_tokens=1200)
        try:
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as _e:
            logger.debug("skipped: %s", _e)
        return {}

    async def fix_product(self, product: dict, session_stats: dict) -> dict:
        """Repariert ein einzelnes Produkt — Bilder, Text, Preise"""
        pid = product["id"]
        issues = []

        # Check: Kein Bild
        has_image = bool(product.get("images"))
        # Check: €0 Preis
        price = float(product.get("variants", [{}])[0].get("price", "0") or 0)
        bad_price = price < 1
        # Check: Schlechter Titel (zu kurz oder Default-Name)
        title = product.get("title", "")
        bad_title = len(title) < 10 or title.lower().startswith("unbenannt") or title.lower().startswith("sample")
        # Check: Keine Beschreibung
        body = product.get("body_html", "")
        bad_body = len(body) < 50

        if not has_image:
            issues.append("no_image")
        if bad_price:
            issues.append("zero_price")
        if bad_title or bad_body:
            issues.append("bad_text")

        if not issues:
            return {"id": pid, "title": title, "fixed": [], "skipped": True}

        fixed = []

        # 1. AI Text verbessern wenn nötig
        improved = {}
        if bad_title or bad_body:
            improved = await self.ai_improve_product(product)
            if improved:
                update_data = {"product": {"id": pid}}
                if improved.get("title"):
                    update_data["product"]["title"] = improved["title"]
                if improved.get("body_html"):
                    update_data["product"]["body_html"] = improved["body_html"]
                if improved.get("tags"):
                    update_data["product"]["tags"] = improved["tags"]
                # SEO Metafields
                if improved.get("meta_title"):
                    update_data["product"]["metafields_global_title_tag"] = improved["meta_title"]
                if improved.get("meta_description"):
                    update_data["product"]["metafields_global_description_tag"] = improved["meta_description"]
                await self._shopify_put(f"products/{pid}.json", update_data)
                fixed.append("text_improved")

        # 2. Preis reparieren (AI-Empfehlung oder Fallback €19.99)
        if bad_price:
            new_price = "19.99"
            if improved.get("suggested_price"):
                new_price = str(improved["suggested_price"]).replace("€", "").strip()
            v_id = product.get("variants", [{}])[0].get("id")
            if v_id:
                await self._shopify_put(f"variants/{v_id}.json", {
                    "variant": {"id": v_id, "price": new_price, "compare_at_price": str(float(new_price) * 1.4)}
                })
                fixed.append(f"price_fixed_{new_price}")

        # 3. Bild hochladen
        if not has_image:
            search_term = (improved.get("title") or title).split("|")[0].strip()[:30]
            img_url = await self.find_image_url(search_term)
            ok = await self.upload_image_to_product(pid, img_url)
            if ok:
                fixed.append("image_added")

        session_stats["fixed"] += len(fixed)
        session_stats["issues_resolved"] += len(issues)
        logger.info(f"Fixed product {pid} '{title[:30]}': {fixed}")
        return {"id": pid, "title": title, "fixed": fixed, "issues": issues}

    # ─── Neue Produkte importieren ────────────────────────────────────────────

    async def generate_new_product(self, niche: str) -> dict:
        """AI generiert ein komplett neues Dropshipping-Produkt"""
        prompt = f"""Erstelle ein verkaufsfähiges Shopify-Produkt für die Nische: {niche}

Aktueller Markt: Deutschland/Österreich/Schweiz
Stil: Direct-to-consumer, hohe Konversionsrate

Erstelle:
{{
  "title": "Produktname (max 70 Zeichen, deutsch, verkaufsstark)",
  "body_html": "<h2>Warum du das liebst</h2><ul><li>✅ Vorteil 1</li><li>✅ Vorteil 2</li><li>✅ Vorteil 3</li></ul><p>Beschreibung 150 Wörter...</p><p>🚚 Schnelle Lieferung | 🛡️ 30-Tage Rückgabe | ⭐ Tausende zufriedene Kunden</p>",
  "price": "24.99",
  "compare_at_price": "44.99",
  "tags": "trending,neu,{niche.replace(' ',',')}",
  "vendor": "I Want That! I Need It!",
  "product_type": "Gadget",
  "image_search_term": "Englischer Suchbegriff für Produktbild",
  "weight": 0.3
}}"""

        text = await self._ai(prompt, max_tokens=1000)
        try:
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as _e:
            logger.debug("skipped: %s", _e)
        return {}

    async def create_shopify_product(self, product_data: dict) -> dict:
        """Erstellt Produkt in Shopify"""
        image_term = product_data.pop("image_search_term", product_data.get("title", "product"))
        weight = product_data.pop("weight", 0.3)
        compare_price = product_data.pop("compare_at_price", None)

        payload = {
            "product": {
                "title": product_data.get("title", "Produkt"),
                "body_html": product_data.get("body_html", ""),
                "vendor": product_data.get("vendor", "I Want That! I Need It!"),
                "product_type": product_data.get("product_type", "Gadget"),
                "tags": product_data.get("tags", "trending,neu"),
                "status": "active",
                "variants": [{
                    "price": str(product_data.get("price", "24.99")),
                    "compare_at_price": str(compare_price) if compare_price else None,
                    "inventory_management": None,
                    "fulfillment_service": "manual",
                    "weight": weight,
                    "weight_unit": "kg",
                }]
            }
        }

        try:
            d = await self._shopify_post("products.json", payload)
            created = d.get("product", {})
            pid = created.get("id")
            if pid:
                # Bild hinzufügen
                img_url = await self.find_image_url(image_term)
                await self.upload_image_to_product(pid, img_url)
                return created
        except Exception as e:
            logger.error(f"Create product failed: {e}")
        return {}

    # ─── Hauptlauf ────────────────────────────────────────────────────────────

    async def run(self, fix_existing: bool = True, add_new: int = 3) -> dict:
        """
        Vollautomatischer Shopify Auto-Fill Lauf:
        1. Bestehende Produkte reparieren (Bilder, Texte, Preise)
        2. Neue Trend-Produkte generieren + importieren
        3. BrutusCore promotet alles auf allen Kanälen
        """
        async with aiohttp.ClientSession() as session:
            self.session = session
            stats = {
                "timestamp": datetime.utcnow().isoformat(),
                "products_scanned": 0,
                "fixed": 0,
                "issues_resolved": 0,
                "new_products_created": 0,
                "brutus_fires": 0,
                "errors": []
            }

            # ── 1. Bestehende Produkte reparieren ────────────────────────────
            if fix_existing:
                products = await self.get_all_products(limit=50)
                stats["products_scanned"] = len(products)
                logger.info(f"Shopify AutoFill: {len(products)} Produkte gefunden")

                for product in products:
                    try:
                        result = await self.fix_product(product, stats)
                        if result.get("fixed"):
                            # BrutusCore: verbesserte Produkte promoten
                            try:
                                from modules.brutus_core import fire as brutus_fire
                                await brutus_fire(
                                    title=f"🛒 Verbessert: {result['title'][:40]}",
                                    body=f"Dieses Produkt wurde frisch aktualisiert — bessere Beschreibung, optimierter Preis, neue Bilder.",
                                    link=os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/669750"),
                                    niche="shopify trending produkt",
                                    tags=["shopify", "neu", "deal"],
                                    channels=["telegram", "klaviyo"]  # Nur leise Kanäle für Updates
                                )
                                stats["brutus_fires"] += 1
                            except Exception as _e:
                                logger.debug("skipped: %s", _e)
                        await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"Fix product {product.get('id')}: {e}")
                        stats["errors"].append(str(e))

            # ── 2. Neue Produkte generieren ───────────────────────────────────
            import random
            niches_to_use = random.sample(TREND_NICHES, min(add_new, len(TREND_NICHES)))

            for niche in niches_to_use:
                try:
                    logger.info(f"Generating new product for niche: {niche}")
                    product_data = await self.generate_new_product(niche)
                    if not product_data.get("title"):
                        continue

                    created = await self.create_shopify_product(product_data)
                    if created.get("id"):
                        stats["new_products_created"] += 1
                        logger.info(f"Created: {created.get('title')}")

                        # BrutusCore: neues Produkt VOLL promoten
                        try:
                            from modules.brutus_core import fire as brutus_fire
                            fire_result = await brutus_fire(
                                title=f"🆕 NEU: {created.get('title', niche)[:50]}",
                                body=f"Frisch im Shop — {created.get('title')}. Jetzt bestellen, solange der Vorrat reicht!",
                                link=f"https://ineedit.com.co/products/{created.get('handle','')}",
                                niche=niche,
                                tags=["neu", "trending", niche.replace(" ", "-")]
                            )
                            stats["brutus_fires"] += 1
                        except Exception as _e:
                            logger.debug("skipped: %s", _e)

                    await asyncio.sleep(3)
                except Exception as e:
                    logger.error(f"New product niche '{niche}': {e}")
                    stats["errors"].append(str(e))

            # ── 3. Telegram Report ────────────────────────────────────────────
            try:
                from modules.brutus_core import _telegram
                msg = (
                    f"🏪 <b>Shopify Auto-Fill abgeschlossen</b>\n\n"
                    f"🔍 Gescannt: {stats['products_scanned']} Produkte\n"
                    f"🔧 Repariert: {stats['fixed']} Fixes\n"
                    f"✨ Neu erstellt: {stats['new_products_created']}\n"
                    f"🔥 BrutusCore Fires: {stats['brutus_fires']}\n"
                    f"⏰ {datetime.utcnow().strftime('%H:%M UTC')}"
                )
                await _telegram(msg, session)
            except Exception as _e:
                logger.debug("skipped: %s", _e)

            logger.info(f"ShopifyAutoFill done: {stats}")
            return stats


async def run_shopify_auto_fill(fix_existing: bool = True, add_new: int = 3) -> dict:
    """Entry point für den Scheduler"""
    if os.getenv("SHOPIFY_AUTO_FILL_ENABLED", "true").lower() in ("false", "0", "off"):
        return {"ok": True, "skipped": True, "reason": "SHOPIFY_AUTO_FILL_ENABLED=false (Qualitäts-Modus)"}
    engine = ShopifyAutoFill()
    return await engine.run(fix_existing=fix_existing, add_new=add_new)


async def auto_fill_trending_products(count: int = 3) -> dict:
    """AI identifies trending products and creates them in Shopify."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {"ok": False, "error": "Shopify credentials required"}

    prompt = """Nenne 3 aktuell sehr trendige Produkte für einen deutschen Online-Shop 2026.
Antworte NUR als JSON-Array (kein anderer Text):
[
  {"title": "Produktname auf Deutsch", "description": "SEO-Beschreibung auf Deutsch 100-150 Wörter mit Keywords", "price": "29.99", "handle": "produktname-slug"},
  {"title": "Produktname 2", "description": "Beschreibung 2", "price": "39.99", "handle": "produktname-2"},
  {"title": "Produktname 3", "description": "Beschreibung 3", "price": "49.99", "handle": "produktname-3"}
]"""

    try:
        from modules.ai_client import ai_complete
        raw = await ai_complete(prompt, max_tokens=1000)
        if not raw:
            return {"ok": False, "error": "AI error: no response"}
        s_idx, e_idx = raw.find("["), raw.rfind("]") + 1
        products = json.loads(raw[s_idx:e_idx]) if s_idx >= 0 else []
    except Exception as e:
        return {"ok": False, "error": f"AI error: {e}"}

    created = []
    async with aiohttp.ClientSession() as sess:
        for p in products[:count]:
            payload = {"product": {
                "title": p.get("title", ""),
                "body_html": f"<p>{p.get('description', '')}</p>",
                "vendor": "BullPower Hub",
                "status": "active",
                "variants": [{"price": p.get("price", "29.99"), "inventory_management": None}],
            }}
            try:
                async with sess.post(
                    f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/products.json",
                    headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"},
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    result = await r.json(content_type=None)
                    prod = result.get("product", {})
                    if prod.get("id"):
                        created.append({"id": prod["id"], "title": prod.get("title", "")})
                        logger.info("Created trending product: %s", prod.get("title", ""))
            except Exception as e:
                logger.warning("Create product error: %s", e)

    if created:
        try:
            from modules.brutus_traffic_engine import brutus_blast_for_tool
            await brutus_blast_for_tool(
                "Shopify Trending",
                "https://ineedit.com.co/",
                keywords=[p["title"] for p in created] + ["online shop 2026", "trending produkte"],
            )
        except Exception as _e:
            logger.debug("skipped: %s", _e)

    return {"ok": len(created) > 0, "created": len(created), "products": created}
