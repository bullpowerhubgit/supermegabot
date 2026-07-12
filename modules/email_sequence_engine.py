"""Email sequence engine — drip sequences: welcome, post-purchase, VIP, winback."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("EmailSequenceEngine")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))

SEQUENCES: dict[str, list[dict]] = {
    "welcome": [
        {"day": 0,  "subject": "Willkommen bei SuperMegaBot! 🚀", "template": "welcome_day0"},
        {"day": 3,  "subject": "Dein Shop automatisiert — so geht's", "template": "welcome_day3"},
        {"day": 7,  "subject": "Top 5 Features die dein Umsatz steigern", "template": "welcome_day7"},
    ],
    "post_purchase": [
        {"day": 0,  "subject": "Deine Bestellung ist bestätigt ✅", "template": "order_confirm"},
        {"day": 7,  "subject": "Wie war deine Erfahrung?", "template": "review_request"},
        {"day": 30, "subject": "Exklusives Angebot nur für dich 💎", "template": "upsell"},
    ],
    "vip": [
        {"day": 0, "subject": "Du bist jetzt VIP — Vorteile warten!", "template": "vip_welcome"},
        {"day": 14, "subject": "VIP-Exklusiv: 20% auf alles 🎁",      "template": "vip_discount"},
    ],
    "winback": [
        {"day": 0,  "subject": "Wir vermissen dich 💫",              "template": "winback_soft"},
        {"day": 7,  "subject": "Letzter Versuch: 20% Rabatt für dich", "template": "winback_hard"},
    ],
    "saas_onboarding": [
        {"day": 0,  "subject": "SuperMegaBot aktiviert! So startest du", "template": "saas_day0"},
        {"day": 1,  "subject": "Schritt 1: Shopify verbinden",           "template": "saas_day1"},
        {"day": 3,  "subject": "Schritt 2: Automatisierung starten",     "template": "saas_day3"},
        {"day": 7,  "subject": "Woche 1 Review — dein Fortschritt",      "template": "saas_week1"},
        {"day": 14, "subject": "Pro-Upgrade: mehr Power für deinen Shop","template": "saas_upsell"},
    ],
}

TEMPLATES: dict[str, str] = {
    "welcome_day0": """
<h2>Willkommen bei SuperMegaBot! 🚀</h2>
<p>Hallo {first_name},</p>
<p>danke dass du dabei bist! SuperMegaBot automatisiert deinen Shopify-Shop komplett — Bestellungen, Marketing, SEO und mehr.</p>
<p><a href='{dashboard_url}' style='background:#6366f1;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;display:inline-block'>Dashboard öffnen →</a></p>
<p>Bei Fragen antworte einfach auf diese E-Mail.<br>Rudolf &amp; das SuperMegaBot-Team</p>
""",
    "welcome_day3": """
<h2>So automatisierst du deinen Shop in 10 Minuten</h2>
<p>Hallo {first_name},</p>
<p>3 Schritte zur vollen Automatisierung:</p>
<ol>
<li><strong>Shopify verbinden</strong> — API-Token eingeben, fertig</li>
<li><strong>Kampagne starten</strong> — ein Klick, läuft automatisch</li>
<li><strong>Umsatz beobachten</strong> — Live-Dashboard im Browser</li>
</ol>
<p><a href='{dashboard_url}'>Jetzt starten →</a></p>
""",
    "welcome_day7": """
<h2>Top 5 Features: So verdienst du mehr mit SuperMegaBot</h2>
<p>Hallo {first_name},</p>
<ul>
<li>🤖 <strong>AI-Preisoptimierung</strong> — automatisch beste Preise</li>
<li>📧 <strong>Winback-Emails</strong> — verlorene Kunden zurückholen</li>
<li>📊 <strong>Revenue-Analyse</strong> — täglich per Telegram</li>
<li>🛒 <strong>Warenkorb-Recovery</strong> — bis 15% mehr Umsatz</li>
<li>🌐 <strong>SEO-Autopilot</strong> — Google-Ranking automatisch verbessern</li>
</ul>
<p><a href='{dashboard_url}'>Alle Features aktivieren →</a></p>
""",
    "order_confirm": """
<h2>Bestellung bestätigt ✅</h2>
<p>Hallo {first_name},</p>
<p>deine Bestellung #{order_id} wurde erfolgreich aufgenommen und wird bald bearbeitet.</p>
<p>Viele Grüße,<br>Das Team</p>
""",
    "review_request": """
<h2>Wie war deine Erfahrung?</h2>
<p>Hallo {first_name},</p>
<p>Wir hoffen, du bist 100% zufrieden! Eine kurze Bewertung hilft uns sehr.</p>
<p><a href='{review_url}'>Jetzt bewerten (1 Minute) →</a></p>
""",
    "upsell": """
<h2>Exklusiv für dich: 10% auf deinen nächsten Einkauf</h2>
<p>Hallo {first_name},</p>
<p>Als Dankeschön: Code <strong>DANKE10</strong> für 10% Rabatt.</p>
<p><a href='{shop_url}'>Jetzt einkaufen →</a></p>
""",
    "vip_welcome": """
<h2>🎉 Du bist jetzt VIP!</h2>
<p>Hallo {first_name},</p>
<p>Deine Treue hat sich ausgezahlt! Als VIP erhältst du:</p>
<ul><li>Exklusive Früh-Zugänge</li><li>Gratis Versand</li><li>Persönlicher Support</li></ul>
""",
    "vip_discount": """
<h2>VIP-Exklusiv: 20% auf alles 💎</h2>
<p>Hallo {first_name},</p>
<p>Nur für VIP-Mitglieder: <strong>20% Rabatt</strong> mit Code <strong>VIP20</strong>.</p>
<p>Gültig bis {expiry_date}.</p>
<p><a href='{shop_url}'>Jetzt einlösen →</a></p>
""",
    "winback_soft": """
<h2>Wir haben dich vermisst, {first_name}! 💫</h2>
<p>Es ist eine Weile her — wir haben neue Produkte die dich interessieren könnten.</p>
<p><a href='{shop_url}'>Neuheiten entdecken →</a></p>
""",
    "winback_hard": """
<h2>Letztes Angebot: 20% exklusiv für dich</h2>
<p>Hallo {first_name},</p>
<p>Code <strong>ZURUECK20</strong> — 20% auf alles. Nur diese Woche!</p>
<p><a href='{shop_url}'>Jetzt sparen →</a></p>
""",
    "saas_day0": """
<h2>SuperMegaBot ist aktiviert! 🚀</h2>
<p>Hallo {first_name},</p>
<p>Willkommen an Bord! Dein Dashboard ist bereit.</p>
<p><a href='{dashboard_url}'>Dashboard öffnen →</a></p>
<p>Morgen schicken wir dir Schritt 1: Shopify verbinden.</p>
""",
    "saas_day1": """
<h2>Schritt 1: Shopify verbinden (5 Minuten)</h2>
<p>Hallo {first_name},</p>
<ol>
<li>Gehe zu <em>Shopify Admin → Apps → Private Apps</em></li>
<li>Erstelle einen API-Token mit Admin-Rechten</li>
<li>Trage ihn in SuperMegaBot Dashboard → Einstellungen → Shopify ein</li>
</ol>
<p><a href='{dashboard_url}'>Jetzt verbinden →</a></p>
""",
    "saas_day3": """
<h2>Schritt 2: Erste Automatisierung starten</h2>
<p>Hallo {first_name},</p>
<p>Dein erstes automatisches System: <strong>Winback-E-Mails</strong> — holt inaktive Kunden zurück.</p>
<p>Aktiviere es in 1 Klick:</p>
<p><a href='{dashboard_url}/autopilot'>Autopilot aktivieren →</a></p>
""",
    "saas_week1": """
<h2>Woche 1 Review: So läuft dein SuperMegaBot</h2>
<p>Hallo {first_name},</p>
<p>Nach einer Woche läuft bei dir bereits:</p>
<ul>
<li>✅ Shopify-Synchronisation (stündlich)</li>
<li>✅ Revenue-Reporting (täglich per Telegram)</li>
<li>✅ SEO-Optimierung (wöchentlich)</li>
</ul>
<p><a href='{dashboard_url}'>Vollständigen Report sehen →</a></p>
""",
    "saas_upsell": """
<h2>Pro-Upgrade: 3x mehr Automatisierungen</h2>
<p>Hallo {first_name},</p>
<p>Du nutzt SuperMegaBot seit 2 Wochen — hier was das Pro-Paket zusätzlich bietet:</p>
<ul>
<li>Priority Support (1h Antwortzeit)</li>
<li>Unlimited Shopify-Produkte</li>
<li>Facebook/Instagram Ads Automation</li>
<li>B2B Pipeline mit AI-Prospecting</li>
</ul>
<p><a href='https://buy.stripe.com/plink_1Ti4nvRJECiV6vSmFHKXWjbz'>Jetzt upgraden (€99/mo) →</a></p>
""",
}


def _render(template_key: str, ctx: dict) -> str:
    html = TEMPLATES.get(template_key, "<p>E-Mail-Inhalt nicht gefunden.</p>")
    for k, v in ctx.items():
        html = html.replace(f"{{{k}}}", str(v))
    return html


async def _send_via_klaviyo(email: str, first_name: str, subject: str, html_body: str) -> bool:
    try:
        import aiohttp
        key = os.getenv("KLAVIYO_API_KEY", "")
        if not key:
            return False
        payload = {"data": {"type": "profile", "attributes": {
            "email": email, "first_name": first_name,
            "properties": {"last_email_subject": subject}
        }}}
        headers = {"Authorization": f"Klaviyo-API-Key {key}", "revision": "2024-10-15",
                   "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as s:
            async with s.post("https://a.klaviyo.com/api/profiles/", json=payload, headers=headers) as r:
                return r.status in (200, 201, 409)
    except Exception as e:
        log.warning("Klaviyo send error: %s", e)
        return False


def _db_path() -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / "email_sequences.json"


def _load_db() -> dict:
    p = _db_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception as e:
            log.warning("Ignored error: %s", e)
    return {"enrollments": [], "sent": []}


def _save_db(db: dict) -> None:
    _db_path().write_text(json.dumps(db, indent=2, default=str))


async def enroll(email: str, sequence: str, first_name: str = "", metadata: dict | None = None) -> dict:
    if sequence not in SEQUENCES:
        return {"ok": False, "error": f"Unknown sequence: {sequence}"}
    db = _load_db()
    for e in db["enrollments"]:
        if e["email"] == email and e["sequence"] == sequence and e.get("active", True):
            return {"ok": False, "already": True, "sequence": sequence}
    enrollment = {
        "id": f"{email}_{sequence}_{int(datetime.now().timestamp())}",
        "email": email, "first_name": first_name or email.split("@")[0],
        "sequence": sequence, "enrolled_at": datetime.now(timezone.utc).isoformat(),
        "active": True, "metadata": metadata or {}
    }
    db["enrollments"].append(enrollment)
    _save_db(db)
    log.info("Enrolled %s in sequence: %s", email, sequence)
    return {"ok": True, "enrollment_id": enrollment["id"], "sequence": sequence, "steps": len(SEQUENCES[sequence])}


async def process_due_emails() -> dict:
    db = _load_db()
    now = datetime.now(timezone.utc)
    sent_count = 0
    shop_url = f"https://{os.getenv('SHOPIFY_SHOP_DOMAIN', 'your-store.myshopify.com')}"
    dashboard_url = os.getenv("DASHBOARD_URL", f"http://localhost:{os.getenv('PORT', '8888')}")
    review_url = os.getenv("REVIEW_URL", f"{shop_url}/pages/bewertung")
    sent_ids = {(s["enrollment_id"], s["step_day"]) for s in db.get("sent", [])}

    for enrollment in db["enrollments"]:
        if not enrollment.get("active", True):
            continue
        sequence_name = enrollment["sequence"]
        steps = SEQUENCES.get(sequence_name, [])
        enrolled_at = datetime.fromisoformat(enrollment["enrolled_at"].replace("Z", "+00:00"))
        for step in steps:
            key = (enrollment["id"], step["day"])
            if key in sent_ids:
                continue
            due_at = enrolled_at + timedelta(days=step["day"])
            if now >= due_at:
                ctx = {
                    "first_name": enrollment.get("first_name", ""),
                    "email": enrollment["email"],
                    "shop_url": shop_url,
                    "dashboard_url": dashboard_url,
                    "review_url": review_url,
                    "order_id": enrollment.get("metadata", {}).get("order_id", ""),
                    "expiry_date": (now + timedelta(days=7)).strftime("%d.%m.%Y"),
                }
                html = _render(step["template"], ctx)
                ok = await _send_via_klaviyo(enrollment["email"], ctx["first_name"], step["subject"], html)
                if ok:
                    sent_count += 1
                    db["sent"].append({
                        "enrollment_id": enrollment["id"],
                        "step_day": step["day"],
                        "template": step["template"],
                        "sent_at": now.isoformat(),
                        "email": enrollment["email"],
                    })
                    log.info("Sent %s day%d to %s", sequence_name, step["day"], enrollment["email"])
    _save_db(db)
    return {"sent": sent_count, "active_enrollments": sum(1 for e in db["enrollments"] if e.get("active", True))}


async def enroll_new_customers() -> dict:
    """Auto-enroll new Shopify customers in welcome sequence."""
    try:
        import aiohttp
        shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        token = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        api_ver = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        if not shop_domain:
            return {"enrolled": 0, "error": "SHOPIFY_SHOP_DOMAIN not set"}
        since = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        url = f"https://{shop_domain}/admin/api/{api_ver}/customers.json?created_at_min={since}&limit=50&fields=id,email,first_name,last_name"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"X-Shopify-Access-Token": token}) as r:
                d = await r.json()
        customers = d.get("customers", [])
        enrolled = 0
        for c in customers:
            if not c.get("email"):
                continue
            first_name = c.get("first_name", "") or c["email"].split("@")[0]
            result = await enroll(c["email"], "welcome", first_name)
            if result.get("ok"):
                enrolled += 1
        return {"enrolled": enrolled, "checked": len(customers)}
    except Exception as e:
        return {"enrolled": 0, "error": str(e)}


async def get_stats() -> dict:
    db = _load_db()
    enrollments = db.get("enrollments", [])
    sent_list = db.get("sent", [])
    by_seq: dict[str, int] = {}
    for e in enrollments:
        seq = e.get("sequence", "unknown")
        by_seq[seq] = by_seq.get(seq, 0) + 1
    return {
        "total_enrollments": len(enrollments),
        "active_enrollments": sum(1 for e in enrollments if e.get("active", True)),
        "total_emails_sent": len(sent_list),
        "by_sequence": by_seq,
        "sequences_available": list(SEQUENCES.keys()),
        "last_run": sent_list[-1].get("sent_at") if sent_list else None,
    }


async def run_with_brutus_traffic() -> dict:
    """Process due emails then fire BRUTUS traffic for email funnel."""
    result = {}
    try:
        result["emails"] = await process_due_emails()
    except Exception as e:
        result["emails_error"] = str(e)
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        result["brutus"] = await run_brutus_swarm(
            keywords=["Email Funnel Automation 2026", "automatische Email Sequenz Geld verdienen", "Online Verkaufstrichter automatisieren"],
            max_keywords=3,
        )
    except Exception as e:
        result["brutus_error"] = str(e)
    return result


# Aliases for dashboard compatibility
async def get_sequence_stats() -> dict:
    return await get_stats()


async def enroll_customer(email: str, sequence: str = "welcome", first_name: str = "", metadata: dict = None) -> dict:
    return await enroll(email=email, sequence=sequence, first_name=first_name, metadata=metadata or {})


async def auto_enroll_new_customers() -> dict:
    return await enroll_new_customers()
