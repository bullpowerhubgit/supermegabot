"""
DS24 Traffic Engine — Vollautomatischer Mailing + Traffic + Posting Stack
Kombiniert: Affiliate-Suche → AI Content → Mailing → Posting → Traffic
"""
import os
import json
import logging
import asyncio
import aiohttp
from datetime import datetime

logger = logging.getLogger(__name__)

DS24_KEY = os.getenv("DIGISTORE24_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-10")
KLAVIYO_KEY = os.getenv("KLAVIYO_API_KEY", "")
KLAVIYO_LIST = os.getenv("KLAVIYO_LIST_ID", "")
MAILCHIMP_KEY = os.getenv("MAILCHIMP_API_KEY", "")
MAILCHIMP_LIST = os.getenv("MAILCHIMP_LIST_ID", "")
MAILCHIMP_SERVER = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")

# Fest definierte Top-Nischen für DS24 DE Markt
DS24_NICHES = [
    {"keyword": "ki", "label": "KI & ChatGPT", "emoji": "🤖"},
    {"keyword": "geld verdienen", "label": "Geld verdienen", "emoji": "💰"},
    {"keyword": "affiliate", "label": "Affiliate Marketing", "emoji": "🔗"},
    {"keyword": "shopify", "label": "E-Commerce", "emoji": "🛒"},
    {"keyword": "krypto", "label": "Krypto", "emoji": "₿"},
    {"keyword": "fitness", "label": "Fitness & Gesundheit", "emoji": "💪"},
    {"keyword": "coaching", "label": "Online Coaching", "emoji": "🎯"},
]

# Bekannte gut-konvertierende DS24 Produkte (Fallback wenn API leer)
DS24_KNOWN_PRODUCTS = [
    {
        "id": "392814",
        "name": "Affiliate Marketing Masterclass",
        "commission_pct": 50,
        "price": "97",
        "niche": "affiliate",
        "affiliate_link": "https://www.digistore24.com/redir/392814/bullpowerhubgit/"
    },
    {
        "id": "561822",
        "name": "ChatGPT & KI Masterclass",
        "commission_pct": 40,
        "price": "197",
        "niche": "ki",
        "affiliate_link": "https://www.digistore24.com/redir/561822/bullpowerhubgit/"
    },
]


class DS24TrafficEngine:
    def __init__(self):
        self.session = None

    async def _ai(self, prompt: str, max_tokens: int = 800) -> str:
        """AI mit Fallback-Kette"""
        for key_env, url, model in [
            ("PERPLEXITY_API_KEY", "https://api.perplexity.ai/chat/completions", "sonar"),
            ("OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions", "gpt-4o-mini"),
            ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions", "mistralai/mistral-7b-instruct"),
        ]:
            key = os.getenv(key_env, "")
            if not key:
                continue
            try:
                async with self.session.post(
                    url,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
                    timeout=aiohttp.ClientTimeout(total=25)
                ) as r:
                    d = await r.json()
                    return d["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning(f"{key_env} failed: {e}")
        return ""

    async def find_ds24_products(self) -> list:
        """DS24 Marketplace Produkte finden"""
        products = []
        try:
            for niche in DS24_NICHES[:4]:
                url = f"https://www.digistore24.com/api/call/listMarketplaceProducts/?format=json&search={niche['keyword']}&language=de"
                async with self.session.get(url, headers={"X-DS-API-KEY": DS24_KEY}, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    d = await r.json()
                    items = d.get("data", {}).get("products", [])
                    for p in items:
                        comm = float(p.get("affiliate_commission", 0) or 0)
                        if comm >= 25:
                            products.append({
                                "id": p.get("id"),
                                "name": p.get("name", "")[:50],
                                "price": p.get("price", "?"),
                                "commission_pct": comm,
                                "niche": niche["label"],
                                "emoji": niche["emoji"],
                                "affiliate_link": f"https://www.digistore24.com/redir/{p.get('id')}/{DS24_KEY.split('-')[0]}/",
                            })
        except Exception as e:
            logger.warning(f"DS24 marketplace search failed: {e}")

        if not products:
            products = DS24_KNOWN_PRODUCTS  # Fallback

        products.sort(key=lambda x: x["commission_pct"], reverse=True)
        return products[:8]

    async def generate_promo_content(self, product: dict) -> dict:
        """AI-generierter Promo-Content für ein Produkt"""
        name = product.get("name", "Top Produkt")
        niche = product.get("niche", "Online Business")
        price = product.get("price", "97")
        commission = product.get("commission_pct", 40)
        link = product.get("affiliate_link", "")

        prompt = f"""Erstelle viralen deutschen Marketing-Content für dieses Affiliate-Produkt:
Produkt: {name}
Nische: {niche}
Preis: €{price}

Erstelle:
1. Telegram Post (2-3 Zeilen, Emoji, kein Spam-Feeling, echte Mehrwert-Story, Link am Ende)
2. Email Betreff (max 50 Zeichen, neugierig machend)
3. Email Body (150 Wörter, persönlich, Story-based, CTA am Ende)
4. Blog-Titel SEO (max 60 Zeichen)
5. Blog-Intro (100 Wörter)

JSON Format:
{{"telegram": "...", "email_subject": "...", "email_body": "...", "blog_title": "...", "blog_intro": "..."}}"""

        text = await self._ai(prompt, max_tokens=1200)

        # JSON extrahieren
        import re
        try:
            m = re.search(r'\{[^{}]*"telegram"[^{}]*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception:
            pass

        # Fallback Template
        return {
            "telegram": f"{product.get('emoji','🔥')} <b>{name}</b>\n\nWie ich mit {niche} meinen Workflow verändert habe — und du es auch kannst.\n\n👉 {link}",
            "email_subject": f"Neu: {name[:40]}",
            "email_body": f"Hey,\n\nichmal ehrlich: {name} hat mir wirklich geholfen.\n\nFalls du in der {niche}-Nische unterwegs bist — das hier lohnt sich.\n\n→ {link}\n\nViele Grüße\nRudolf",
            "blog_title": f"{name} — Meine ehrliche Erfahrung",
            "blog_intro": f"Heute teile ich meine Erfahrungen mit {name}. Als jemand der sich intensiv mit {niche} beschäftigt, war dieses Produkt eine echte Überraschung."
        }

    async def post_telegram(self, text: str) -> bool:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
            return False
        try:
            async with self.session.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                d = await r.json()
                return d.get("ok", False)
        except Exception as e:
            logger.warning(f"Telegram post failed: {e}")
            return False

    async def post_shopify_blog(self, title: str, body: str, product: dict) -> bool:
        if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
            return False
        link = product.get("affiliate_link", "")
        commission = product.get("commission_pct", 40)
        full_body = f"""{body}

<h2>Meine Empfehlung</h2>
<p>Nach ausgiebigem Testen empfehle ich <strong>{product.get('name','')}</strong> besonders für alle die in der {product.get('niche','')} Nische aktiv sind.</p>
<p><a href="{link}" rel="nofollow" target="_blank">👉 Hier klicken und mehr erfahren</a></p>
<p><small>*Affiliate-Link — bei Kauf erhalte ich eine Provision von {commission}%. Der Preis für dich ändert sich nicht.</small></p>"""

        mutation = """mutation {
  blogCreate(blog: {title: "DS24 Empfehlungen"}) {
    blog { id }
    userErrors { field message }
  }
}"""
        # Blog ID holen oder erstellen
        blog_id = "gid://shopify/Blog/127011258755"  # Bekannte Blog ID

        article_mutation = f"""mutation {{
  articleCreate(article: {{
    blogId: "{blog_id}",
    title: "{title.replace('"', "'")}",
    author: {{name: "Rudolf S."}},
    body: "{full_body.replace(chr(10), ' ').replace('"', "'")}",
    tags: ["ds24", "affiliate", "empfehlung"],
    isPublished: true
  }}) {{
    article {{ id title handle }}
    userErrors {{ field message }}
  }}
}}"""
        try:
            async with self.session.post(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/graphql.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"},
                json={"query": article_mutation},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                d = await r.json()
                errors = d.get("data", {}).get("articleCreate", {}).get("userErrors", [])
                return len(errors) == 0
        except Exception as e:
            logger.warning(f"Shopify blog post failed: {e}")
            return False

    async def send_klaviyo_campaign(self, product: dict, content: dict) -> bool:
        if not KLAVIYO_KEY or not KLAVIYO_LIST:
            return False
        try:
            # Track Event für alle Subscriber
            async with self.session.post(
                "https://a.klaviyo.com/api/events/",
                headers={
                    "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
                    "revision": "2024-10-15",
                    "Content-Type": "application/json"
                },
                json={
                    "data": {
                        "type": "event",
                        "attributes": {
                            "metric": {"data": {"type": "metric", "attributes": {"name": "DS24 Promo Sent"}}},
                            "properties": {
                                "product_name": product.get("name"),
                                "affiliate_link": product.get("affiliate_link"),
                                "commission": product.get("commission_pct"),
                                "email_subject": content.get("email_subject"),
                            },
                            "profile": {"data": {"type": "profile", "attributes": {"email": "bullpowersrtkennels@gmail.com"}}}
                        }
                    }
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                return r.status in (200, 201, 202)
        except Exception as e:
            logger.warning(f"Klaviyo event failed: {e}")
            return False

    async def send_mailchimp_campaign(self, product: dict, content: dict) -> bool:
        if not MAILCHIMP_KEY or not MAILCHIMP_LIST:
            return False
        try:
            auth = aiohttp.BasicAuth("anystring", MAILCHIMP_KEY)
            base = f"https://{MAILCHIMP_SERVER}.api.mailchimp.com/3.0"

            # Campaign erstellen
            async with self.session.post(f"{base}/campaigns", auth=auth, json={
                "type": "regular",
                "recipients": {"list_id": MAILCHIMP_LIST},
                "settings": {
                    "subject_line": content.get("email_subject", f"Empfehlung: {product.get('name','')}"),
                    "from_name": "Rudolf Sarkany",
                    "reply_to": "bullpowersrtkennels@gmail.com",
                    "title": f"DS24 Promo — {datetime.utcnow().strftime('%Y-%m-%d')}"
                }
            }, timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = await r.json()
                campaign_id = d.get("id")

            if not campaign_id:
                return False

            # Content setzen
            email_html = f"""<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
<h2>{content.get('email_subject','')}</h2>
<p>{content.get('email_body','').replace(chr(10),'<br>')}</p>
<p><a href="{product.get('affiliate_link','')}" style="background:#e74c3c;color:white;padding:12px 24px;text-decoration:none;border-radius:4px">👉 Jetzt ansehen</a></p>
<hr><p><small>Rudolf Sarkany | <a href="*|UNSUB|*">Abmelden</a></small></p>
</body></html>"""

            async with self.session.put(f"{base}/campaigns/{campaign_id}/content", auth=auth,
                json={"html": email_html}, timeout=aiohttp.ClientTimeout(total=10)) as r:
                pass

            # Senden
            async with self.session.post(f"{base}/campaigns/{campaign_id}/actions/send", auth=auth,
                timeout=aiohttp.ClientTimeout(total=10)) as r:
                return r.status == 204

        except Exception as e:
            logger.warning(f"Mailchimp campaign failed: {e}")
            return False

    async def run(self) -> dict:
        """Vollautomatischer Lauf — sucht, generiert, postet, mailt"""
        async with aiohttp.ClientSession() as session:
            self.session = session
            results = {
                "timestamp": datetime.utcnow().isoformat(),
                "products_found": 0,
                "telegram_sent": 0,
                "blog_posts": 0,
                "emails_sent": 0,
                "errors": []
            }

            # 1. Produkte finden
            products = await self.find_ds24_products()
            results["products_found"] = len(products)
            logger.info(f"DS24 Traffic: {len(products)} Produkte gefunden")

            if not products:
                return results

            # 2. Pro Produkt Content generieren + posten
            for i, product in enumerate(products[:3]):  # max 3 pro Lauf
                try:
                    content = await self.generate_promo_content(product)

                    # Telegram
                    tg_text = content.get("telegram", "")
                    if tg_text:
                        ok = await self.post_telegram(tg_text)
                        if ok:
                            results["telegram_sent"] += 1
                        await asyncio.sleep(2)

                    # Shopify Blog (nur erstes Produkt)
                    if i == 0:
                        blog_ok = await self.post_shopify_blog(
                            content.get("blog_title", product["name"]),
                            content.get("blog_intro", ""),
                            product
                        )
                        if blog_ok:
                            results["blog_posts"] += 1

                    # Klaviyo
                    await self.send_klaviyo_campaign(product, content)

                    # Mailchimp (nur erstes Produkt)
                    if i == 0:
                        mail_ok = await self.send_mailchimp_campaign(product, content)
                        if mail_ok:
                            results["emails_sent"] += 1

                    await asyncio.sleep(3)

                except Exception as e:
                    logger.error(f"Product {product.get('name')} error: {e}")
                    results["errors"].append(str(e))

            # 3. Summary Telegram
            summary = (
                f"✅ <b>DS24 Traffic Engine — Lauf abgeschlossen</b>\n\n"
                f"📦 Produkte gefunden: {results['products_found']}\n"
                f"📱 Telegram Posts: {results['telegram_sent']}\n"
                f"📝 Blog Posts: {results['blog_posts']}\n"
                f"📧 E-Mails gesendet: {results['emails_sent']}\n"
                f"⏰ {datetime.utcnow().strftime('%H:%M UTC')}"
            )
            await self.post_telegram(summary)

            logger.info(f"DS24 Traffic done: {results}")
            return results


async def run_ds24_traffic():
    """Entry point für den Scheduler"""
    engine = DS24TrafficEngine()
    return await engine.run()
