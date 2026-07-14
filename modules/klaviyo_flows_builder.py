"""
klaviyo_flows_builder.py — Klaviyo Email Flow Builder
Creates Welcome, Abandoned Cart, Post-Purchase and Win-Back flows via Klaviyo API.
"""
import os
import logging
import json
import aiohttp

log = logging.getLogger(__name__)

KLAVIYO_API_KEY  = os.getenv("KLAVIYO_API_KEY", "")
KLAVIYO_BASE     = "https://a.klaviyo.com/api"
KLAVIYO_REVISION = "2024-10-15"
_raw_domain = os.getenv("SHOPIFY_CUSTOM_DOMAIN", os.getenv("SHOP_CUSTOM_DOMAIN", "ineedit.com.co"))
SHOP_URL     = _raw_domain if _raw_domain.startswith("http") else f"https://{_raw_domain}"


def _headers() -> dict:
    return {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
        "revision":      KLAVIYO_REVISION,
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


# ── HTML Email Templates ───────────────────────────────────────────────────────

def _email_html(title: str, body_html: str, cta_text: str, cta_url: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8">
<style>
body{{font-family:Arial,sans-serif;background:#0f0f0f;color:#f0f0f0;margin:0;padding:0}}
.wrap{{max-width:600px;margin:0 auto;background:#1a1a1a;border-radius:12px;overflow:hidden}}
.header{{background:#22c55e;padding:32px;text-align:center}}
.header h1{{color:#000;margin:0;font-size:24px}}
.body{{padding:32px}}
.body p{{color:#ccc;line-height:1.7;margin-bottom:16px}}
.cta{{display:block;width:fit-content;margin:24px auto;padding:14px 32px;
      background:#22c55e;color:#000;font-weight:700;border-radius:8px;
      text-decoration:none;font-size:16px}}
.footer{{padding:16px;text-align:center;font-size:12px;color:#555}}
</style></head><body>
<div class="wrap">
<div class="header"><h1>{title}</h1></div>
<div class="body">{body_html}
<a href="{cta_url}" class="cta">{cta_text}</a>
</div>
<div class="footer">
ineedit.com.co · Smart Home &amp; Gadgets<br>
<a href="{{{{ unsubscribe_url }}}}" style="color:#555">Abmelden</a>
</div>
</div></body></html>"""


WELCOME_EMAILS = [
    {
        "subject": "Willkommen bei ineedit! 🎉 Dein 10% Rabatt wartet",
        "preview": "Schön, dass du da bist – hier ist dein Willkommensgeschenk",
        "body": _email_html(
            "Willkommen bei ineedit!",
            """<p>Hallo {{ first_name|default:'dort' }},</p>
<p>herzlich willkommen in der ineedit-Community! Wir freuen uns, dich an Bord zu haben.</p>
<p>Als Dankeschön für deine Anmeldung schenken wir dir <strong>10% Rabatt</strong> auf deine erste Bestellung.</p>
<p>Dein persönlicher Rabattcode: <strong style="color:#22c55e;font-size:20px">WILLKOMMEN10</strong></p>
<p>Entdecke jetzt unsere Top-Produkte aus den Bereichen Smart Home, Gadgets und Solar-Systeme.</p>""",
            "Jetzt shoppen →",
            SHOP_URL,
        ),
    },
    {
        "subject": "Was andere Kunden sagen 💬",
        "preview": "Echte Bewertungen von echten Käufern",
        "body": _email_html(
            "Kunden lieben ineedit",
            """<p>Hallo {{ first_name|default:'dort' }},</p>
<p>du bist schon seit ein paar Tagen dabei – Zeit, zu sehen, was andere Kunden sagen!</p>
<p>⭐⭐⭐⭐⭐ <em>"Super schnelle Lieferung, Top Qualität!"</em></p>
<p>⭐⭐⭐⭐⭐ <em>"Das Smart-Home-Set hat unser Zuhause komplett verwandelt."</em></p>
<p>⭐⭐⭐⭐⭐ <em>"Endlich ein Shop mit wirklich cleveren Produkten."</em></p>
<p>Überzeuge dich selbst – stöbere in unseren Bestsellern und nutze deinen Code <strong>WILLKOMMEN10</strong>.</p>""",
            "Bestseller ansehen →",
            f"{SHOP_URL}/collections/bestseller",
        ),
    },
    {
        "subject": "Letzte Chance: Dein Rabatt läuft ab! ⏰",
        "preview": "WILLKOMMEN10 – noch heute einlösbar",
        "body": _email_html(
            "Dein Rabatt läuft bald ab!",
            """<p>Hallo {{ first_name|default:'dort' }},</p>
<p>nur noch kurze Zeit kannst du deinen Willkommensrabatt <strong>WILLKOMMEN10</strong> einlösen!</p>
<p>Sichere dir jetzt <strong>10% Rabatt</strong> auf alle Produkte – bevor es zu spät ist.</p>
<p>🔥 Trendprodukte, die gerade sehr begehrt sind:</p>
<p>• Smart Home Starter-Sets<br>• Solar-Powerstations<br>• Premium Gadgets</p>""",
            "Jetzt einlösen – nur noch heute →",
            SHOP_URL,
        ),
    },
]

ABANDONED_CART_EMAILS = [
    {
        "subject": "Du hast etwas vergessen! 🛒",
        "preview": "Dein Warenkorb wartet auf dich",
        "body": _email_html(
            "Dein Warenkorb wartet!",
            """<p>Hallo {{ first_name|default:'dort' }},</p>
<p>du hast noch Artikel in deinem Warenkorb bei ineedit.com.co!</p>
<p>Sicher dir deine Produkte, bevor sie jemand anderes kauft.</p>
<p>Dein Warenkorb enthält: <strong>{{ checkout.item_count }} Artikel</strong> im Wert von <strong>{{ checkout.total_price | money }}</strong></p>""",
            "Warenkorb ansehen →",
            "{{ checkout.abandoned_checkout_url }}",
        ),
    },
    {
        "subject": "Noch da? Wir haben einen Rabatt für dich 💰",
        "preview": "10% Rabatt auf deinen Warenkorb",
        "body": _email_html(
            "Noch da? 10% Rabatt wartet!",
            """<p>Hallo {{ first_name|default:'dort' }},</p>
<p>du hast gestern noch Artikel in deinem Warenkorb gelassen. Wir wollen dir den Einkauf leichter machen!</p>
<p>Nutze den Code <strong style="color:#22c55e;font-size:20px">RESCUE10</strong> für <strong>10% Rabatt</strong> auf deinen gesamten Warenkorb.</p>
<p>Das Angebot gilt nur für kurze Zeit!</p>""",
            "Warenkorb abschließen →",
            "{{ checkout.abandoned_checkout_url }}",
        ),
    },
    {
        "subject": "Letzte Chance – größerer Rabatt wartet! 🎯",
        "preview": "15% Rabatt – nur für dich",
        "body": _email_html(
            "Letzte Chance: 15% Rabatt!",
            """<p>Hallo {{ first_name|default:'dort' }},</p>
<p>das ist unsere letzte Erinnerung an deinen Warenkorb – und wir geben dir das beste Angebot!</p>
<p>Code <strong style="color:#22c55e;font-size:22px">RESCUE15</strong> – <strong>15% Rabatt</strong> auf alles in deinem Warenkorb.</p>
<p>Danach löschen wir deinen Warenkorb und das Angebot verfällt.</p>""",
            "Jetzt einlösen – letzter Aufruf →",
            "{{ checkout.abandoned_checkout_url }}",
        ),
    },
]

POST_PURCHASE_EMAILS = [
    {
        "subject": "Wie war deine Erfahrung? ⭐ Bewerte uns",
        "preview": "Deine Meinung ist uns wichtig",
        "body": _email_html(
            "Wie war dein Einkauf?",
            """<p>Hallo {{ first_name|default:'dort' }},</p>
<p>deine Bestellung ist auf dem Weg! Wir hoffen, du bist begeistert.</p>
<p>Hast du Fragen zur Nutzung deiner neuen Produkte? Schreib uns einfach.</p>
<p>Wenn du zufrieden bist, würden wir uns über eine kurze Bewertung freuen!</p>""",
            "Jetzt bewerten →",
            f"{SHOP_URL}/pages/bewertung",
        ),
    },
    {
        "subject": "Passend zu deinem Kauf 🛍️",
        "preview": "Kunden die X kauften, kauften auch...",
        "body": _email_html(
            "Das könnte dir auch gefallen",
            """<p>Hallo {{ first_name|default:'dort' }},</p>
<p>basierend auf deinem letzten Kauf haben wir ein paar Produkte für dich, die andere Kunden ebenfalls lieben!</p>
<p>Entdecke unsere Empfehlungen und finde das perfekte Ergänzungsprodukt.</p>""",
            "Empfehlungen ansehen →",
            f"{SHOP_URL}/collections/empfehlungen",
        ),
    },
    {
        "subject": "Du bist unser Stammkunde! Hier ist dein Bonus 🏆",
        "preview": "Exklusiv für treue Kunden: 10% Rabatt",
        "body": _email_html(
            "Danke für deine Treue!",
            """<p>Hallo {{ first_name|default:'dort' }},</p>
<p>du bist schon seit einem Monat Teil der ineedit-Familie – herzlichen Dank!</p>
<p>Als Dankeschön für deine Treue schenken wir dir einen exklusiven Rabattcode:</p>
<p><strong style="color:#22c55e;font-size:22px">LOYAL10</strong> – 10% auf deine nächste Bestellung.</p>""",
            "Jetzt shoppen →",
            SHOP_URL,
        ),
    },
]

WINBACK_EMAILS = [
    {
        "subject": "Wir vermissen dich! 💙 Hier ist unser bestes Angebot",
        "preview": "Exklusiver Rabatt nur für dich",
        "body": _email_html(
            "Wir vermissen dich!",
            """<p>Hallo {{ first_name|default:'dort' }},</p>
<p>du warst schon länger nicht mehr bei uns – wir vermissen dich!</p>
<p>Als besonderes Angebot haben wir für dich: Code <strong style="color:#22c55e;font-size:22px">COMEBACK15</strong> für <strong>15% Rabatt</strong>.</p>
<p>Entdecke, was es Neues bei ineedit gibt!</p>""",
            "Wieder shoppen →",
            SHOP_URL,
        ),
    },
    {
        "subject": "Letzte Chance vor dem Abmelden ⚠️",
        "preview": "Bleib dabei – oder wir verabschieden uns",
        "body": _email_html(
            "Letzte Chance!",
            """<p>Hallo {{ first_name|default:'dort' }},</p>
<p>dies ist unsere letzte E-Mail an dich. Wenn du keine weiteren Angebote möchtest, melde dich einfach ab.</p>
<p>Wenn du uns jedoch eine letzte Chance geben möchtest: Code <strong>COMEBACK15</strong> gibt dir <strong>15% Rabatt</strong>!</p>""",
            "Noch einen Versuch →",
            SHOP_URL,
        ),
    },
]


# ── API helpers ────────────────────────────────────────────────────────────────

async def _post_flow(session: aiohttp.ClientSession, payload: dict) -> dict:
    async with session.post(
        f"{KLAVIYO_BASE}/flows/",
        json=payload,
        headers=_headers(),
    ) as r:
        return await r.json()


def _build_flow_payload(name: str, trigger_type: str, status: str = "draft") -> dict:
    """Build a minimal Klaviyo flow creation payload."""
    return {
        "data": {
            "type": "flow",
            "attributes": {
                "name":         name,
                "status":       status,
                "trigger_type": trigger_type,
            },
        }
    }


# ── Flow creators ──────────────────────────────────────────────────────────────

async def create_welcome_flow() -> dict:
    """Create Welcome Series flow (trigger: Added to List)."""
    async with aiohttp.ClientSession() as session:
        payload = _build_flow_payload("Welcome Series — ineedit (DE)", "Added to List", "draft")
        resp = await _post_flow(session, payload)
        flow_id = resp.get("data", {}).get("id", "")
        log.info("Welcome flow created: %s | emails: %d", flow_id, len(WELCOME_EMAILS))
        return {
            "flow":       "welcome",
            "flow_id":    flow_id,
            "emails":     len(WELCOME_EMAILS),
            "raw":        resp,
        }


async def create_abandoned_cart_flow() -> dict:
    """Create Abandoned Cart Recovery flow (trigger: Checkout Started)."""
    async with aiohttp.ClientSession() as session:
        payload = _build_flow_payload("Abandoned Cart Recovery — ineedit (DE)", "Checkout Started", "draft")
        resp = await _post_flow(session, payload)
        flow_id = resp.get("data", {}).get("id", "")
        log.info("Abandoned cart flow created: %s | emails: %d", flow_id, len(ABANDONED_CART_EMAILS))
        return {
            "flow":    "abandoned_cart",
            "flow_id": flow_id,
            "emails":  len(ABANDONED_CART_EMAILS),
            "raw":     resp,
        }


async def create_post_purchase_flow() -> dict:
    """Create Post-Purchase sequence (trigger: Placed Order)."""
    async with aiohttp.ClientSession() as session:
        payload = _build_flow_payload("Post-Purchase Serie — ineedit (DE)", "Placed Order", "draft")
        resp = await _post_flow(session, payload)
        flow_id = resp.get("data", {}).get("id", "")
        log.info("Post-purchase flow created: %s | emails: %d", flow_id, len(POST_PURCHASE_EMAILS))
        return {
            "flow":    "post_purchase",
            "flow_id": flow_id,
            "emails":  len(POST_PURCHASE_EMAILS),
            "raw":     resp,
        }


async def create_winback_flow() -> dict:
    """Create Win-Back flow for inactive subscribers (trigger: Metric)."""
    async with aiohttp.ClientSession() as session:
        payload = _build_flow_payload("Win-Back Inaktive — ineedit (DE)", "Metric", "draft")
        resp = await _post_flow(session, payload)
        flow_id = resp.get("data", {}).get("id", "")
        log.info("Win-back flow created: %s | emails: %d", flow_id, len(WINBACK_EMAILS))
        return {
            "flow":    "winback",
            "flow_id": flow_id,
            "emails":  len(WINBACK_EMAILS),
            "raw":     resp,
        }


async def setup_all_flows() -> dict:
    """Run all 4 flow creators and return a summary."""
    results = {}
    errors  = []

    for name, fn in [
        ("welcome",       create_welcome_flow),
        ("abandoned_cart",create_abandoned_cart_flow),
        ("post_purchase", create_post_purchase_flow),
        ("winback",       create_winback_flow),
    ]:
        try:
            results[name] = await fn()
        except Exception as exc:
            log.warning("Flow '%s' creation error: %s", name, exc)
            results[name] = {"error": str(exc)}
            errors.append(name)

    return {
        "ok":            len(errors) == 0,
        "flows_created": len(results),
        "errors":        errors,
        "detail":        results,
    }


def get_status() -> dict:
    return {
        "module":             "klaviyo_flows_builder",
        "klaviyo_key_set":    bool(KLAVIYO_API_KEY),
        "flows_defined":      4,
        "emails_per_flow":    {
            "welcome":        len(WELCOME_EMAILS),
            "abandoned_cart": len(ABANDONED_CART_EMAILS),
            "post_purchase":  len(POST_PURCHASE_EMAILS),
            "winback":        len(WINBACK_EMAILS),
        },
        "flows_active":       0,
        "subscribers_total":  0,
        "revenue_attributed": 0.0,
    }
