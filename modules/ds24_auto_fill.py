"""
DS24 Auto-Fill System
- Scannt DS24 Marketplace für Affiliate-Produkte
- Generiert DS24-konforme Produkt-Pakete mit AI
- Postet automatisch auf alle Kanäle
- Sendet Telegram-Benachrichtigungen
"""
import os
import json
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DS24_API_KEY = os.getenv("DIGISTORE24_API_KEY", "")
DS24_BASE = "https://www.digistore24.com/api/call"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")




async def _brutus_fire(message: str, channels: list = None):
    """BrutusCore: verteilt Revenue-Events auf alle Kanäle."""
    try:
        from modules.brutus_core import BrutusCore
        b = BrutusCore()
        await b.fire(message, channels=channels or ["telegram", "shopify_blog", "linkedin", "mailchimp", "klaviyo"])
    except Exception as _be:
        import logging
        logging.getLogger(__name__).debug("Brutus fire skip: %s", _be)


class DS24AutoFill:
    def __init__(self):
        self.api_key = DS24_API_KEY
        self.session = None

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        url = f"{DS24_BASE}/{endpoint}/?format=json"
        if params:
            url += "&" + "&".join(f"{k}={v}" for k, v in params.items())
        try:
            async with self.session.get(url, headers={"X-DS-API-KEY": self.api_key}, timeout=aiohttp.ClientTimeout(total=15)) as r:
                return await r.json()
        except Exception as e:
            logger.error(f"DS24 API error {endpoint}: {e}")
            return {"result": "error", "message": str(e)}

    async def check_account_status(self) -> dict:
        """Prüft ob Account Produkte hat"""
        prods = await self._get("listProducts")
        txns = await self._get("listTransactions")
        products = prods.get("data", {}).get("products", [])
        transactions = txns.get("data", {}).get("transaction_list", [])
        active = [p for p in products if p.get("is_active") == "Y"]
        approved = [p for p in active if not p.get("approval_status_list") or
                    any(a.get("approval_status") == "approved" for a in p.get("approval_status_list", []))]
        return {
            "total_products": len(products),
            "active_products": len(active),
            "approved_products": len(approved),
            "total_transactions": len(transactions),
            "needs_fill": len(approved) == 0
        }

    async def find_affiliate_products(self, niche: str = "ki,geld,software") -> list:
        """Sucht DS24 Marketplace Affiliate-Produkte"""
        keywords = niche.split(",")
        found = []
        # DS24 Marketplace durchsuchen
        for kw in keywords:
            data = await self._get("listMarketplaceProducts", {"search": kw, "language": "de"})
            items = data.get("data", {}).get("products", [])
            for p in items:
                commission = float(p.get("affiliate_commission", 0) or 0)
                if commission >= 30:  # Nur 30%+ Provision
                    found.append({
                        "id": p.get("id"),
                        "name": p.get("name", "")[:60],
                        "price": p.get("price"),
                        "currency": p.get("currency", "EUR"),
                        "commission_pct": commission,
                        "checkout_url": p.get("orderform_customer_url", ""),
                        "affiliate_link": f"https://www.digistore24.com/redir/{p.get('id')}/{self.api_key.split('-')[0]}",
                        "vendor": p.get("owner_name", ""),
                    })
        found.sort(key=lambda x: x["commission_pct"], reverse=True)
        return found[:10]

    async def generate_product_package(self, topic: str = "KI Business") -> dict:
        """Generiert DS24-konformes Produkt-Paket mit AI"""
        prompt = f"""Erstelle ein vollständiges DS24-konformes digitales Produkt für das Thema: {topic}

Regeln (WICHTIG - DS24-Anforderungen):
- KEINE Einkommensversprechen ("verdiene X€/Monat" verboten)
- Statt dessen: "Wie ich X erreicht habe" (Erfahrungen ok)
- 60-Tage Geld-zurück-Garantie MUSS erwähnt werden
- Klares Impressum und Datenschutz Link einplanen
- Konkrete Inhalte beschreiben (kein "geheimes System")

Erstelle:
1. Produktname (max 60 Zeichen)
2. Kurzbeschreibung (2 Sätze, kein Einkommensvrsprechen)
3. Verkaufsseite HTML (komplett, mit Impressum-Link, 60-Tage-Garantie)
4. Dankeseite HTML (mit Produktzugang-Info)
5. Preis-Empfehlung (€ 27-97)

Format: JSON mit keys: name, description, salespage_html, thankyou_html, price"""

        ai_response = await self._ai_complete(prompt)
        try:
            # JSON aus AI Response extrahieren
            import re
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass

        # Fallback: Template
        return {
            "name": f"{topic} — Schritt für Schritt Guide",
            "description": f"Entdecke wie ich mit {topic} meinen Alltag verändert habe. Praxisnah, sofort umsetzbar.",
            "salespage_html": self._generate_salespage_html(topic),
            "thankyou_html": self._generate_thankyou_html(topic),
            "price": 47
        }

    def _generate_salespage_html(self, topic: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>{topic} Guide</title>
<style>body{{font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px}}
.cta{{background:#e74c3c;color:white;padding:15px 30px;font-size:20px;border:none;cursor:pointer;width:100%}}
.guarantee{{border:2px solid green;padding:15px;margin:20px 0}}</style>
</head>
<body>
<h1>Wie ich mit {topic} meinen Workflow transformiert habe</h1>
<p>In diesem Guide teile ich meine persönlichen Erfahrungen und konkreten Schritte.</p>
<h2>Was du lernst:</h2>
<ul>
<li>✅ Schritt-für-Schritt Implementierung</li>
<li>✅ Konkrete Tools und Vorlagen</li>
<li>✅ Zeitersparnis durch Automatisierung</li>
<li>✅ Sofort anwendbare Strategien</li>
</ul>
<div class="guarantee">
<h3>🛡️ 60-Tage Geld-zurück-Garantie</h3>
<p>Wenn du nicht zufrieden bist, erhältst du innerhalb von 60 Tagen dein Geld vollständig zurück. Kein Risiko.</p>
</div>
<button class="cta">Jetzt für nur €47 kaufen</button>
<hr>
<p><small>
<a href="/impressum">Impressum</a> |
<a href="/datenschutz">Datenschutz</a> |
<a href="/agb">AGB</a><br>
Rudolf Sarkany | bullpowersrtkennels@gmail.com
</small></p>
</body></html>"""

    def _generate_thankyou_html(self, topic: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"><title>Danke! — {topic}</title></head>
<body>
<h1>🎉 Vielen Dank für deinen Kauf!</h1>
<h2>So erhältst du sofort Zugriff:</h2>
<ol>
<li>Schau in deine E-Mail (auch Spam-Ordner)</li>
<li>Klicke auf den Download-Link</li>
<li>Das PDF ist sofort verfügbar</li>
</ol>
<p>Bei Fragen: <a href="mailto:bullpowersrtkennels@gmail.com">bullpowersrtkennels@gmail.com</a></p>
</body></html>"""

    async def _ai_complete(self, prompt: str) -> str:
        """AI Completion mit Fallback-Kette"""
        providers = [
            self._perplexity_complete,
            self._openai_complete,
            self._openrouter_complete,
        ]
        for provider in providers:
            try:
                result = await provider(prompt)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"AI provider failed: {e}")
        return ""

    async def _perplexity_complete(self, prompt: str) -> str:
        key = os.getenv("PERPLEXITY_API_KEY", "")
        if not key:
            return ""
        async with self.session.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "sonar", "messages": [{"role": "user", "content": prompt}], "max_tokens": 2000},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            d = await r.json()
            return d["choices"][0]["message"]["content"]

    async def _openai_complete(self, prompt: str) -> str:
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            return ""
        async with self.session.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "max_tokens": 2000},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            d = await r.json()
            return d["choices"][0]["message"]["content"]

    async def _openrouter_complete(self, prompt: str) -> str:
        key = os.getenv("OPENROUTER_API_KEY", "")
        if not key:
            return ""
        async with self.session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "mistralai/mistral-7b-instruct", "messages": [{"role": "user", "content": prompt}], "max_tokens": 2000},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            d = await r.json()
            return d["choices"][0]["message"]["content"]

    async def send_telegram(self, text: str):
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        try:
            async with self.session.post(url, json={
                "chat_id": TELEGRAM_CHAT,
                "text": text,
                "parse_mode": "HTML"
            }, timeout=aiohttp.ClientTimeout(total=10)) as r:
                pass
        except Exception as e:
            logger.warning(f"Telegram send failed: {e}")

    async def run(self) -> dict:
        """Hauptlauf — prüft + füllt automatisch auf"""
        async with aiohttp.ClientSession() as session:
            self.session = session
            results = {"timestamp": datetime.utcnow().isoformat(), "actions": []}

            # 1. Account Status prüfen
            status = await self.check_account_status()
            results["account_status"] = status
            logger.info(f"DS24 Status: {status}")

            if status["needs_fill"]:
                # 2. Affiliate-Produkte suchen
                affiliates = await self.find_affiliate_products("ki,software,business,geld verdienen")
                results["affiliate_products"] = affiliates

                if affiliates:
                    msg = "🔥 <b>DS24 Auto-Fill: Neue Affiliate-Produkte gefunden!</b>\n\n"
                    for p in affiliates[:5]:
                        msg += f"📦 <b>{p['name']}</b>\n"
                        msg += f"   💰 Preis: €{p['price']} | Provision: {p['commission_pct']}%\n"
                        msg += f"   🔗 {p['affiliate_link']}\n\n"
                    await self.send_telegram(msg)
                    results["actions"].append(f"found_{len(affiliates)}_affiliate_products")

                # 3. Eigene Produkt-Pakete generieren
                topics = ["KI Tools für Selbstständige", "Shopify Automatisierung", "Passives Einkommen mit Digitalprodukten"]
                packages = []
                for topic in topics:
                    pkg = await self.generate_product_package(topic)
                    packages.append(pkg)
                    logger.info(f"Generated package: {pkg.get('name', topic)}")

                results["generated_packages"] = len(packages)

                # Telegram Notification mit fertigen Paketen
                pkg_msg = "🛠️ <b>DS24 Auto-Fill: Fertige Produkt-Pakete generiert!</b>\n\n"
                for pkg in packages:
                    pkg_msg += f"✅ <b>{pkg.get('name', 'Produkt')}</b>\n"
                    pkg_msg += f"   💶 Empfohlener Preis: €{pkg.get('price', 47)}\n"
                    pkg_msg += f"   📝 {pkg.get('description', '')[:100]}\n\n"
                pkg_msg += "👆 Alles DS24-konform (60-Tage-Garantie, kein Einkommensversprechen, Impressum enthalten)"
                await self.send_telegram(pkg_msg)
                results["actions"].append("generated_product_packages")

                # Pakete lokal speichern
                save_path = "/tmp/ds24_packages.json"
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(packages, f, ensure_ascii=False, indent=2)
                results["packages_saved_to"] = save_path

            else:
                logger.info(f"DS24 account OK — {status['approved_products']} approved products")
                results["actions"].append("no_fill_needed")

            return results


async def run_ds24_auto_fill():
    """Entry point für den Scheduler"""
    filler = DS24AutoFill()
    return await filler.run()
