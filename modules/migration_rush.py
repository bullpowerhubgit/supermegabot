"""
migration_rush.py — Platform Migration Rush Monitor fuer SuperMegaBot
Monitoring von Plattform-Krisen (TikTok-Ban, Reddit-API-Krise, Twitter/X-Chaos, Instagram-Abwanderung).
Bei Trigger (Score >= 75): Massenverkauf des 'Creator Emergency Kit' fuer EUR 49 in 48h.

ANTI-DUPLIKAT: State-Persistenz in data/migration_rush_state.json
Gleiche Plattform wird innerhalb 48h nicht erneut getriggert.
"""

import asyncio
import json
import logging
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("migration_rush")

# -------------------------------------------------------------------------
# Konfiguration
# -------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_ADMIN_API_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")
DS24_API_KEY = os.getenv("DS24_API_KEY", "1581233-")  # IMMER aiitec-Key!
DS24_API_URL = os.getenv("DS24_API_URL", "https://www.digistore24.com/api/call")
KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID", "")
STATE_FILE = os.getenv("MIGRATION_RUSH_STATE", "data/migration_rush_state.json")
LANDING_PAGE_DIR = os.getenv("MIGRATION_LANDING_DIR", "data/landing_pages")
TRIGGER_SCORE = 75
COOLDOWN_HOURS = 48
SCAN_INTERVAL_HOURS = 4

PLATFORMS = {
    "TIKTOK": {
        "name": "TikTok",
        "queries": [
            "TikTok Ban Deutschland",
            "TikTok Verbot EU",
            "TikTok gesperrt Creator",
            "TikTok shutdown alternative",
            "TikTok Abwanderung Instagram",
        ],
    },
    "REDDIT": {
        "name": "Reddit",
        "queries": [
            "Reddit API Krise Creator",
            "Reddit gesperrt Deutschland",
            "Reddit Abwanderung alternative",
            "Reddit shutdown Communities",
            "Reddit Premium Zwang",
        ],
    },
    "TWITTER": {
        "name": "Twitter/X",
        "queries": [
            "Twitter X Krise Creator verlassen",
            "Twitter Abwanderung Bluesky",
            "X Elon Musk Abonnement Pflicht",
            "Twitter shutdown Deutschland",
            "X API teuer Creator",
        ],
    },
    "INSTAGRAM": {
        "name": "Instagram",
        "queries": [
            "Instagram Reichweite Einbruch Creator",
            "Instagram Algorithm Change Abwanderung",
            "Instagram gesperrt Accounts",
            "Instagram Alternative Threads",
            "Instagram Krise Influencer",
        ],
    },
}

# -------------------------------------------------------------------------
# Produkt-Inhalte (eingebettet, keine externe Abhaengigkeit)
# -------------------------------------------------------------------------
EMERGENCY_KIT_GUIDE = """
CREATOR EMERGENCY KIT — 7-Schritte-PDF

Schritt 1: Sofort-Sicherung aller Content-Assets (Bilder, Videos, Texte)
Schritt 2: Export deiner Follower-Daten und Community-Informationen
Schritt 3: E-Mail-Liste aufbauen — dein einziger plattform-unabhaengiger Kanal
Schritt 4: Multi-Plattform-Strategie einrichten (3 Plattformen minimum)
Schritt 5: Eigene Website / Landing Page als Content-Hub
Schritt 6: Monetarisierungs-Backup (Gumroad, Digistore24, eigener Shop)
Schritt 7: Community-Migration — Telegram/Discord als Rueckzugsort

CHECKLISTE:
[ ] Alle Posts heruntergeladen
[ ] Analytics-Daten exportiert
[ ] Newsletter-System aktiv (mind. 500 Abonnenten)
[ ] Backup-Plattform eingerichtet
[ ] Eigene Domain registriert
[ ] Zahlungsabwicklung unabhaengig von Plattform

EMPFOHLENE TOOLS:
- E-Mail: Klaviyo, Mailchimp, ConvertKit
- Community: Circle, Discord, Telegram
- Monetarisierung: Gumroad, Digistore24, Shopify
- Backup-Hosting: Cloudflare Pages, Netlify
- Video-Backup: Vimeo, Bunny.net

EMAIL-TEMPLATES:
--- Announcement ---
Betreff: Wichtige Nachricht zu meinem Content
Ich migriere gerade auf neue Plattformen. Abonniere meinen Newsletter,
um nichts zu verpassen: [LINK]

--- Follow-up ---
Betreff: Mein neues Zuhause im Internet
Ab sofort findest du mich hauptsaechlich unter: [PLATTFORM/LINK]
"""


@dataclass
class PlatformSignal:
    platform: str
    crisis_score: int
    top_headlines: list
    trigger_reached: bool
    scanned_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class MigrationRush:
    def __init__(self):
        os.makedirs("data", exist_ok=True)
        os.makedirs(LANDING_PAGE_DIR, exist_ok=True)
        self._state = self._load_state()

    # -------------------------------------------------------------------------
    # State-Management (Anti-Duplikat)
    # -------------------------------------------------------------------------
    def _load_state(self) -> dict:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self._state, f, indent=2)

    def _is_in_cooldown(self, platform: str) -> bool:
        last = self._state.get(platform, {}).get("last_triggered")
        if not last:
            return False
        last_dt = datetime.fromisoformat(last)
        return datetime.utcnow() - last_dt < timedelta(hours=COOLDOWN_HOURS)

    def _mark_triggered(self, platform: str):
        self._state[platform] = {"last_triggered": datetime.utcnow().isoformat()}
        self._save_state()

    # -------------------------------------------------------------------------
    # 1. scan_platform (Google News RSS)
    # -------------------------------------------------------------------------
    async def scan_platform(self, platform_key: str) -> PlatformSignal:
        cfg = PLATFORMS[platform_key]
        queries = cfg["queries"]
        total_score = 0
        all_headlines = []

        async with aiohttp.ClientSession() as session:
            for query in queries:
                try:
                    encoded = query.replace(" ", "+")
                    url = (
                        f"https://news.google.com/rss/search?q={encoded}"
                        f"&hl=de&gl=DE&ceid=DE:de"
                    )
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            continue
                        text = await resp.text()
                        root = ET.fromstring(text)
                        items = root.findall(".//item")
                        count = len(items)
                        score_increment = min(count * 5, 25)
                        total_score += score_increment

                        for item in items[:3]:
                            title_el = item.find("title")
                            if title_el is not None and title_el.text:
                                all_headlines.append(title_el.text.strip())
                except Exception as e:
                    logger.warning("RSS-Fehler fuer '%s': %s", query, e)

        final_score = min(total_score, 100)
        trigger = final_score >= TRIGGER_SCORE

        logger.info(
            "Plattform %s: Score=%d, Headlines=%d, Trigger=%s",
            platform_key, final_score, len(all_headlines), trigger
        )
        return PlatformSignal(
            platform=platform_key,
            crisis_score=final_score,
            top_headlines=all_headlines[:10],
            trigger_reached=trigger,
        )

    # -------------------------------------------------------------------------
    # 2. scan_all_platforms
    # -------------------------------------------------------------------------
    async def scan_all_platforms(self) -> list:
        tasks = [self.scan_platform(pk) for pk in PLATFORMS]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        signals = []
        for r in results:
            if isinstance(r, Exception):
                logger.error("Scan-Fehler: %s", r)
            else:
                signals.append(r)
        return signals

    # -------------------------------------------------------------------------
    # 3. create_ds24_product
    # -------------------------------------------------------------------------
    async def create_ds24_product(self, platform_key: str) -> Optional[str]:
        platform_name = PLATFORMS[platform_key]["name"]
        payload = {
            "api_key": DS24_API_KEY,
            "product_name": f"Creator Emergency Kit – {platform_name} Migration",
            "description": (
                f"Komplettes 7-Schritte-System fuer Creator, die von {platform_name} "
                f"abwandern. Sofort-Download, inkl. Checkliste, E-Mail-Templates und Tool-Liste."
            ),
            "price": "49.00",
            "currency": "EUR",
            "product_type": "digital",
            "delivery_type": "instant_download",
        }
        url = f"{DS24_API_URL}/CREATE_PRODUCT/format/json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    data = await resp.json()
                    product_id = data.get("data", {}).get("product_id") or data.get("product_id")
                    if product_id:
                        logger.info("DS24 Produkt erstellt: %s", product_id)
                        return str(product_id)
                    logger.error("DS24 kein product_id in Antwort: %s", data)
                    return None
        except Exception as e:
            logger.error("DS24-Fehler: %s", e)
            return None

    # -------------------------------------------------------------------------
    # 4. create_shopify_product
    # -------------------------------------------------------------------------
    async def create_shopify_product(self, platform_key: str) -> Optional[str]:
        platform_name = PLATFORMS[platform_key]["name"]
        title = f"Creator Emergency Kit – {platform_name} Migration"
        body = (
            f"<p><strong>Dein Rettungsplan fuer die {platform_name}-Krise.</strong></p>"
            f"<p>7-Schritte-PDF + Checkliste + E-Mail-Templates. Sofort-Download.</p>"
            f"<ul>"
            f"<li>Content-Assets sichern</li>"
            f"<li>E-Mail-Liste aufbauen</li>"
            f"<li>Multi-Plattform-Strategie</li>"
            f"<li>Monetarisierungs-Backup</li>"
            f"</ul>"
        )
        payload = {
            "product": {
                "title": title,
                "body_html": body,
                "vendor": "SuperMegaBot",
                "product_type": "Digital Download",
                "status": "active",
                "tags": f"migration,creator,{platform_key.lower()},emergency-kit,digital",
                "variants": [
                    {
                        "price": "49.00",
                        "requires_shipping": False,
                        "inventory_management": None,
                    }
                ],
            }
        }
        url = (
            f"https://{SHOPIFY_SHOP_DOMAIN}/admin/api/"
            f"{SHOPIFY_API_VERSION}/products.json"
        )
        headers = {
            "X-Shopify-Access-Token": SHOPIFY_ADMIN_API_TOKEN,
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        pid = str(data["product"]["id"])
                        logger.info("Shopify-Produkt erstellt: %s", pid)
                        return pid
                    text = await resp.text()
                    logger.error("Shopify-Fehler %d: %s", resp.status, text[:300])
                    return None
        except Exception as e:
            logger.error("Shopify-Verbindungsfehler: %s", e)
            return None

    # -------------------------------------------------------------------------
    # 5. create_klaviyo_campaign
    # -------------------------------------------------------------------------
    async def create_klaviyo_campaign(self, platform_key: str) -> Optional[str]:
        if not KLAVIYO_API_KEY:
            logger.warning("KLAVIYO_API_KEY nicht gesetzt")
            return None
        platform_name = PLATFORMS[platform_key]["name"]
        headers = {
            "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
            "Content-Type": "application/json",
            "revision": "2024-02-15",
        }
        campaign_payload = {
            "data": {
                "type": "campaign",
                "attributes": {
                    "name": f"Migration Rush – {platform_name} Krise {datetime.utcnow().strftime('%Y-%m-%d')}",
                    "channel": "email",
                    "audiences": {"included": [], "excluded": []},
                    "send_strategy": {"method": "immediate"},
                    "tracking_options": {"is_tracking_opens": True, "is_tracking_clicks": True},
                },
            }
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://a.klaviyo.com/api/campaigns/",
                    headers=headers,
                    json=campaign_payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status in (200, 201, 202):
                        data = await resp.json()
                        cid = data.get("data", {}).get("id")
                        if cid:
                            await self._klaviyo_send_job(cid, headers, session)
                        return cid
                    text = await resp.text()
                    logger.error("Klaviyo-Fehler %d: %s", resp.status, text[:300])
                    return None
        except Exception as e:
            logger.error("Klaviyo-Verbindungsfehler: %s", e)
            return None

    async def _klaviyo_send_job(self, campaign_id: str, headers: dict, session: aiohttp.ClientSession):
        payload = {"data": {"type": "campaign-send-job", "id": campaign_id}}
        try:
            async with session.post(
                f"https://a.klaviyo.com/api/campaign-send-jobs/",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (200, 201, 202):
                    logger.info("Klaviyo Send-Job gestartet fuer Kampagne %s", campaign_id)
                else:
                    logger.warning("Klaviyo Send-Job Fehler %d", resp.status)
        except Exception as e:
            logger.warning("Klaviyo Send-Job Verbindungsfehler: %s", e)

    # -------------------------------------------------------------------------
    # 6. create_meta_ad
    # -------------------------------------------------------------------------
    async def create_meta_ad(self, platform_key: str, shopify_product_id: Optional[str] = None) -> Optional[str]:
        if not META_ACCESS_TOKEN or not META_AD_ACCOUNT_ID:
            logger.warning("META_ACCESS_TOKEN oder META_AD_ACCOUNT_ID nicht gesetzt")
            return None
        platform_name = PLATFORMS[platform_key]["name"]
        base_url = "https://graph.facebook.com/v18.0"
        headers = {"Content-Type": "application/json"}

        # Campaign
        camp_payload = {
            "name": f"Migration Rush – {platform_name}",
            "objective": "OUTCOME_SALES",
            "status": "ACTIVE",
            "access_token": META_ACCESS_TOKEN,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/act_{META_AD_ACCOUNT_ID}/campaigns",
                    headers=headers,
                    json=camp_payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    data = await resp.json()
                    campaign_id = data.get("id")
                    if not campaign_id:
                        logger.error("Meta Campaign-Fehler: %s", data)
                        return None

                # AdSet mit Creator-Targeting 18-45 DE/AT/CH
                adset_payload = {
                    "name": f"Creator 18-45 DACH – {platform_name}",
                    "campaign_id": campaign_id,
                    "daily_budget": 1000,
                    "billing_event": "IMPRESSIONS",
                    "optimization_goal": "CONVERSIONS",
                    "targeting": {
                        "age_min": 18,
                        "age_max": 45,
                        "geo_locations": {
                            "countries": ["DE", "AT", "CH"]
                        },
                        "interests": [
                            {"id": "6003107902433", "name": "Content creation"},
                            {"id": "6003200426935", "name": "Social media"},
                        ],
                    },
                    "status": "ACTIVE",
                    "access_token": META_ACCESS_TOKEN,
                }
                async with session.post(
                    f"{base_url}/act_{META_AD_ACCOUNT_ID}/adsets",
                    headers=headers,
                    json=adset_payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    data = await resp.json()
                    adset_id = data.get("id")
                    if not adset_id:
                        logger.error("Meta AdSet-Fehler: %s", data)
                        return campaign_id

                # Creative
                product_url = (
                    f"https://{SHOPIFY_SHOP_DOMAIN}/products/{shopify_product_id}"
                    if shopify_product_id else f"https://{SHOPIFY_SHOP_DOMAIN}"
                )
                creative_payload = {
                    "name": f"Creator Emergency Kit – {platform_name}",
                    "object_story_spec": {
                        "page_id": os.getenv("META_PAGE_ID", ""),
                        "link_data": {
                            "link": product_url,
                            "message": (
                                f"Die {platform_name}-Krise trifft Creator hart. "
                                f"Sicher dich jetzt ab mit dem Creator Emergency Kit – "
                                f"7-Schritte-System fuer EUR 49. Sofort-Download!"
                            ),
                            "name": f"Creator Emergency Kit – {platform_name} Migration",
                            "call_to_action": {"type": "SHOP_NOW", "value": {"link": product_url}},
                        },
                    },
                    "access_token": META_ACCESS_TOKEN,
                }
                async with session.post(
                    f"{base_url}/act_{META_AD_ACCOUNT_ID}/adcreatives",
                    headers=headers,
                    json=creative_payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    data = await resp.json()
                    creative_id = data.get("id")
                    if not creative_id:
                        logger.warning("Meta Creative-Fehler: %s", data)
                        return campaign_id

                # Ad
                ad_payload = {
                    "name": f"Emergency Kit Ad – {platform_name}",
                    "adset_id": adset_id,
                    "creative": {"creative_id": creative_id},
                    "status": "ACTIVE",
                    "access_token": META_ACCESS_TOKEN,
                }
                async with session.post(
                    f"{base_url}/act_{META_AD_ACCOUNT_ID}/ads",
                    headers=headers,
                    json=ad_payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    data = await resp.json()
                    ad_id = data.get("id")
                    logger.info("Meta Ad erstellt: %s", ad_id)
                    return campaign_id

        except Exception as e:
            logger.error("Meta-Ad-Fehler: %s", e)
            return None

    # -------------------------------------------------------------------------
    # 7. post_social
    # -------------------------------------------------------------------------
    async def post_social(self, platform_key: str, product_url: str = ""):
        platform_name = PLATFORMS[platform_key]["name"]
        text = (
            f"ACHTUNG: {platform_name}-Krise! Schuetze jetzt deinen Content und deine Community.\n"
            f"Creator Emergency Kit – 7-Schritte-System fuer sofortige Plattform-Migration.\n"
            f"EUR 49, Sofort-Download: {product_url}\n"
            f"#CreatorEmergency #{platform_key} #Migration #ContentCreator"
        )

        # Telegram
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            await self._send_telegram(text)

        # Weitere Social-Plattformen koennen hier ueber viral_promo_poster integriert werden
        logger.info("Social-Post fuer %s versendet", platform_key)

    # -------------------------------------------------------------------------
    # 8. generate_landing_page
    # -------------------------------------------------------------------------
    async def generate_landing_page(self, platform_key: str, product_url: str = "") -> str:
        platform_name = PLATFORMS[platform_key]["name"]
        klaviyo_form = os.getenv("KLAVIYO_FORM_ID", "")
        html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Creator Emergency Kit – {platform_name} Migration</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #0a0a0a; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }}
.hero {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 80px 20px; text-align: center; }}
.hero h1 {{ font-size: 2.5rem; color: #e94560; margin-bottom: 20px; }}
.hero p {{ font-size: 1.2rem; color: #a0a0c0; max-width: 600px; margin: 0 auto 40px; }}
.cta {{ display: inline-block; background: #e94560; color: #fff; padding: 18px 48px;
        border-radius: 4px; font-size: 1.2rem; font-weight: bold; text-decoration: none; }}
.cta:hover {{ background: #c73652; }}
.section {{ padding: 60px 20px; max-width: 800px; margin: 0 auto; }}
.section h2 {{ font-size: 1.8rem; color: #e94560; margin-bottom: 20px; }}
.steps {{ list-style: none; }}
.steps li {{ padding: 12px 0; border-bottom: 1px solid #222; color: #b0b0c0; }}
.steps li::before {{ content: "✓ "; color: #e94560; font-weight: bold; }}
.optin {{ background: #111; padding: 40px 20px; text-align: center; }}
.optin h3 {{ color: #e94560; margin-bottom: 20px; }}
.optin input {{ width: 300px; padding: 12px; background: #222; border: 1px solid #333;
               color: #fff; border-radius: 4px; margin-right: 10px; }}
.optin button {{ padding: 12px 24px; background: #e94560; color: #fff; border: none;
                border-radius: 4px; cursor: pointer; font-size: 1rem; }}
footer {{ background: #050505; padding: 20px; text-align: center; color: #444; font-size: 0.8rem; }}
</style>
</head>
<body>
<div class="hero">
  <h1>Die {platform_name}-Krise trifft Creator hart.</h1>
  <p>Sicher dich jetzt ab. 7-Schritte-System fuer sofortige Plattform-Migration.
     Behalte deine Community – egal was passiert.</p>
  <a href="{product_url}" class="cta">Creator Emergency Kit – EUR 49 Sofort-Download</a>
</div>
<div class="section">
  <h2>Was du bekommst</h2>
  <ul class="steps">
    <li>7-Schritte-PDF: Content-Assets sichern & migrieren</li>
    <li>Checkliste: Nichts vergessen beim Plattformwechsel</li>
    <li>E-Mail-Templates: Community informieren & mitnehmen</li>
    <li>Tool-Liste: Beste Alternativen fuer jeden Use-Case</li>
    <li>Bonus: Multi-Plattform-Strategie fuer die Zukunft</li>
  </ul>
</div>
<div class="optin">
  <h3>Newsletter: Erfahre zuerst von Krisen & Loesungen</h3>
  {"<div class='klaviyo-form-" + klaviyo_form + "'></div>" if klaviyo_form else
   "<p>Trage dich in unsere Liste ein und bleibe informiert.</p>"}
</div>
<footer>
  &copy; {datetime.utcnow().year} SuperMegaBot | Kein Teil dieser Seite stellt Finanz- oder Rechtsberatung dar.
</footer>
</body>
</html>"""

        filename = os.path.join(LANDING_PAGE_DIR, f"migration_{platform_key.lower()}.html")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("Landing Page erstellt: %s", filename)
        return filename

    # -------------------------------------------------------------------------
    # 9. alert_telegram
    # -------------------------------------------------------------------------
    async def alert_telegram(self, signal: PlatformSignal, extras: dict = None) -> bool:
        platform_name = PLATFORMS[signal.platform]["name"]
        extras = extras or {}
        headlines_text = "\n".join([f"  - {h[:80]}" for h in signal.top_headlines[:5]]) or "  (keine)"

        msg = (
            f"MIGRATION RUSH ALERT\n\n"
            f"Plattform: {platform_name}\n"
            f"Krisen-Score: {signal.crisis_score}/100\n"
            f"Trigger: {'JA' if signal.trigger_reached else 'NEIN'}\n\n"
            f"Top Headlines:\n{headlines_text}\n"
        )
        if extras.get("ds24_id"):
            msg += f"\nDS24 Produkt: {extras['ds24_id']}"
        if extras.get("shopify_id"):
            msg += f"\nShopify Produkt: {extras['shopify_id']}"
        if extras.get("meta_campaign"):
            msg += f"\nMeta Kampagne: {extras['meta_campaign']}"
        if extras.get("landing_page"):
            msg += f"\nLanding Page: {extras['landing_page']}"

        return await self._send_telegram(msg)

    # -------------------------------------------------------------------------
    # 10. run_trigger_workflow
    # -------------------------------------------------------------------------
    async def run_trigger_workflow(self, signal: PlatformSignal):
        platform_key = signal.platform
        if self._is_in_cooldown(platform_key):
            logger.info("Plattform %s in Cooldown – uebersprungen", platform_key)
            return

        logger.info("Trigger-Workflow gestartet fuer %s (Score=%d)", platform_key, signal.crisis_score)

        ds24_id = await self.create_ds24_product(platform_key)
        shopify_id = await self.create_shopify_product(platform_key)

        product_url = ""
        if shopify_id and SHOPIFY_SHOP_DOMAIN:
            product_url = f"https://{SHOPIFY_SHOP_DOMAIN}/products/{shopify_id}"

        await self.create_klaviyo_campaign(platform_key)
        meta_campaign = await self.create_meta_ad(platform_key, shopify_id)
        await self.post_social(platform_key, product_url)
        landing_page = await self.generate_landing_page(platform_key, product_url)

        await self.alert_telegram(signal, extras={
            "ds24_id": ds24_id,
            "shopify_id": shopify_id,
            "meta_campaign": meta_campaign,
            "landing_page": landing_page,
        })

        self._mark_triggered(platform_key)
        logger.info("Trigger-Workflow fuer %s abgeschlossen", platform_key)

    # -------------------------------------------------------------------------
    # Hilfsmethoden
    # -------------------------------------------------------------------------
    async def _send_telegram(self, text: str) -> bool:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.warning("Telegram nicht konfiguriert")
            return False
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text[:4096],
            "parse_mode": "HTML",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    ok = resp.status == 200
                    if not ok:
                        logger.error("Telegram-Fehler %d", resp.status)
                    return ok
        except Exception as e:
            logger.error("Telegram-Verbindungsfehler: %s", e)
            return False


# =============================================================================
# Main / CLI
# =============================================================================
async def _run_once(mr: MigrationRush):
    signals = await mr.scan_all_platforms()
    for signal in signals:
        if signal.trigger_reached:
            await mr.run_trigger_workflow(signal)
        else:
            logger.info(
                "Plattform %s: Score %d – kein Trigger (Schwelle %d)",
                signal.platform, signal.crisis_score, TRIGGER_SCORE
            )


async def _daemon(mr: MigrationRush):
    logger.info("Daemon gestartet — Scan alle %dh", SCAN_INTERVAL_HOURS)
    while True:
        await _run_once(mr)
        await asyncio.sleep(SCAN_INTERVAL_HOURS * 3600)


async def main():
    mr = MigrationRush()

    if "--now" in sys.argv:
        await _run_once(mr)
    elif "--test" in sys.argv:
        idx = sys.argv.index("--test")
        platform_key = sys.argv[idx + 1].upper() if len(sys.argv) > idx + 1 else "TIKTOK"
        if platform_key not in PLATFORMS:
            print(f"Unbekannte Plattform: {platform_key}. Verfuegbar: {list(PLATFORMS.keys())}")
            sys.exit(1)
        signal = PlatformSignal(
            platform=platform_key,
            crisis_score=85,
            top_headlines=["Test-Headline 1", "Test-Headline 2"],
            trigger_reached=True,
        )
        await mr.run_trigger_workflow(signal)
    elif "--landing" in sys.argv:
        idx = sys.argv.index("--landing")
        platform_key = sys.argv[idx + 1].upper() if len(sys.argv) > idx + 1 else "TIKTOK"
        if platform_key not in PLATFORMS:
            print(f"Unbekannte Plattform: {platform_key}. Verfuegbar: {list(PLATFORMS.keys())}")
            sys.exit(1)
        path = await mr.generate_landing_page(platform_key)
        print(f"Landing Page erstellt: {path}")
    else:
        await _daemon(mr)


if __name__ == "__main__":
    asyncio.run(main())
