#!/usr/bin/env python3
"""
Autonomer Klaviyo Kampagnen-Sender.
Wählt automatisch das nächste Template aus einer Rotation und sendet an Liste Xwxq6V.
Läuft via GitHub Actions Mo + Do 08:00 UTC.
"""
import os, requests, time, json, hashlib
from datetime import datetime, timezone

KLAVIYO_KEY = os.environ["KLAVIYO_API_KEY"]
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
LIST_ID = "Xwxq6V"

H = {
    "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
    "revision": "2024-10-15",
    "Content-Type": "application/json",
}

CAMPAIGNS = [
    {
        "name": "KI-Einkommenssystem — Wochenbeginn Motivation",
        "subject": "🚀 Diese Woche startest du durch — KI-Einkommen 2026",
        "preview": "Ein System. Vollautomatisch. Ab €37.",
        "html": """<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#f4f4f4;">
<div style="background:white;border-radius:10px;padding:30px;">
<h2 style="color:#FF6B00;">Diese Woche wird anders 🚀</h2>
<p>Hallo,</p>
<p>Was waere wenn du ab <strong>heute</strong> anfaengst, passiv Geld zu verdienen — ohne Chef, ohne feste Arbeitszeiten?</p>
<p>Das AI Income Machine 90-Day Blueprint gibt dir genau das:</p>
<ul>
<li>✅ KI-Tools die wirklich Geld bringen (nicht nur hype)</li>
<li>✅ Schritt-fuer-Schritt auf Deutsch erklaert</li>
<li>✅ In 90 Tagen zum ersten passiven Einkommen</li>
<li>✅ Einmalig 37 Euro — kein Abo, kein Risiko</li>
</ul>
<p><strong>Die 3 Verkäufe dieses Produkts zeigen: Es funktioniert.</strong></p>
<p style="text-align:center;margin:30px 0;">
<a href="https://www.checkout-ds24.com/product/668035" style="background:#FF6B00;color:white;padding:16px 40px;text-decoration:none;border-radius:8px;font-size:1.1rem;font-weight:700;">
Jetzt fuer 37 Euro starten →
</a>
</p>
<p>Hast du Fragen? Antworte einfach auf diese Email.</p>
<p>Rudolf Sarkany<br>AiiteC KI-Automation</p>
</div></body></html>""",
        "text": "KI-Einkommen starten: AI Income Machine 90-Day Blueprint fuer 37 Euro. 14 Tage Garantie. https://www.checkout-ds24.com/product/668035",
    },
    {
        "name": "Wochenabschluss — KI-Tipp + Produktempfehlung",
        "subject": "💡 KI-Tipp der Woche: So verdienst du mit ChatGPT",
        "preview": "Tipp #1: Prompts vermieten. Tipp #2: Automatisch skalieren.",
        "html": """<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#f4f4f4;">
<div style="background:white;border-radius:10px;padding:30px;">
<h2>💡 KI-Tipp der Woche</h2>
<p>Hallo,</p>
<p><strong>Tipp #1: ChatGPT-Prompts verkaufen</strong><br>
Gut formulierte Prompts fuer spezifische Branchen werden auf Etsy, Gumroad und DS24 verkauft. Einmalig erstellen, immer wieder verkaufen.</p>
<p><strong>Tipp #2: KI-Texte automatisieren</strong><br>
Mit den richtigen Workflows schreibt deine KI taeglich Produktbeschreibungen, Blogartikel und Social-Media-Posts — ohne dein Zutun.</p>
<p><strong>Tipp #3: Das komplette System kaufen</strong><br>
Alle Tipps, 50+ weitere Strategien und das vollstaendige 90-Tage-System gibt es im AI Income Machine Blueprint.</p>
<p style="text-align:center;margin:30px 0;">
<a href="https://www.checkout-ds24.com/product/668035" style="background:#1e40af;color:white;padding:16px 40px;text-decoration:none;border-radius:8px;font-size:1.1rem;font-weight:700;">
Komplettes System ansehen →
</a>
</p>
<p>Bis naechste Woche,<br>Rudolf</p>
</div></body></html>""",
        "text": "KI-Tipp der Woche: Prompts verkaufen, KI-Texte automatisieren. Komplettes System: https://www.checkout-ds24.com/product/668035",
    },
    {
        "name": "Dringlichkeit — Zeitlimit Angebot",
        "subject": "⏰ Nur noch heute: AI Income Machine zum Einsteiger-Preis",
        "preview": "37 Euro statt 97 Euro — nur fuer Newsletter-Abonnenten",
        "html": """<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#f4f4f4;">
<div style="background:white;border-radius:10px;padding:30px;">
<div style="background:#FF6B00;color:white;padding:15px;border-radius:8px;text-align:center;margin-bottom:20px;">
<strong>⏰ NEWSLETTER-EXKLUSIV: Heute gueltig</strong>
</div>
<h2>Als Subscriber kriegst du den besten Preis</h2>
<p>Hallo,</p>
<p>Weil du unseren Newsletter abonniert hast, bekommst du heute das AI Income Machine Blueprint zum Launch-Preis von <strong>nur 37 Euro</strong> (Normalpreis: 97 Euro).</p>
<p>Was du bekommst:</p>
<ul>
<li>Das 90-Tage-System fuer passives KI-Einkommen</li>
<li>5 KI-Tool-Anleitungen auf Deutsch</li>
<li>3 Einkommensstrategien die sofort funktionieren</li>
<li>14 Tage volle Geld-zurueck-Garantie</li>
</ul>
<p style="text-align:center;margin:30px 0;">
<a href="https://www.checkout-ds24.com/product/668035" style="background:#FF6B00;color:white;padding:18px 50px;text-decoration:none;border-radius:8px;font-size:1.2rem;font-weight:700;">
Jetzt fuer 37 Euro sichern →
</a>
</p>
<p><small>Nur heute gueltig. Digistore24 sichere Zahlung.</small></p>
<p>Rudolf Sarkany</p>
</div></body></html>""",
        "text": "Newsletter-Exklusiv: AI Income Machine fuer 37 Euro. 14 Tage Garantie. https://www.checkout-ds24.com/product/668035",
    },
    {
        "name": "Social Proof — Testimonials und Zahlen",
        "subject": "📊 Diese Zahlen sprechen fuer sich (KI-Einkommen 2026)",
        "preview": "3 Kaeufer. 37 Euro. Was haben sie gemeinsam?",
        "html": """<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#f4f4f4;">
<div style="background:white;border-radius:10px;padding:30px;">
<h2>📊 Die Zahlen, die du kennen solltest</h2>
<p>Hallo,</p>
<p>Fakten zum AI Income Machine 90-Day Blueprint:</p>
<div style="background:#f8f9fa;border-left:4px solid #FF6B00;padding:15px;margin:15px 0;">
<strong>✅ 3 zahlende Kunden</strong> — haben fuer 37 Euro gekauft<br>
<strong>✅ 0 Rueckgaben</strong> — 14-Tage-Garantie aber niemand hat zurueckgeschickt<br>
<strong>✅ Sofortzugang</strong> — direkt nach Zahlung verfuegbar<br>
<strong>✅ Auf Deutsch</strong> — fuer DACH-Markt optimiert
</div>
<p>Der durchschnittliche Käufer verdient laut unserem System nach 60 Tagen erste Einnahmen.</p>
<p style="text-align:center;margin:30px 0;">
<a href="https://www.checkout-ds24.com/product/668035" style="background:#10b981;color:white;padding:16px 40px;text-decoration:none;border-radius:8px;font-size:1.1rem;font-weight:700;">
Jetzt Kaeufer #4 werden — 37 Euro
</a>
</p>
<p>Rudolf Sarkany<br>AiiteC</p>
</div></body></html>""",
        "text": "3 Kaeufer, 0 Rueckgaben. AI Income Machine fuer 37 Euro: https://www.checkout-ds24.com/product/668035",
    },
    {
        "name": "SuperMegaBot Upsell — Fuer Fortgeschrittene",
        "subject": "🤖 Du bist bereit fuer Level 2: SuperMegaBot System",
        "preview": "Wenn dir 37 Euro zu wenig sind — hier das Pro-System",
        "html": """<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#f4f4f4;">
<div style="background:white;border-radius:10px;padding:30px;">
<h2>🤖 Bereit fuer das naechste Level?</h2>
<p>Hallo,</p>
<p>Du hast bereits unser AI Income Machine Blueprint. Oder du weisst was du willst: das vollstaendige System.</p>
<p>Der <strong>SuperMegaBot KI-Automation System</strong> (97 Euro einmalig) ist fuer dich wenn:</p>
<ul>
<li>Du einen Shopify-Store hast oder aufbauen willst</li>
<li>Du E-Commerce vollautomatisch betreiben willst</li>
<li>Du mehrere Einkommensstroeme gleichzeitig aufbauen willst</li>
<li>Du bereit bist fuer ernsthaftes Online-Business</li>
</ul>
<p>Enthält: Shopify-Automation, Email-Marketing, Social Media, Revenue-Tracking — alles in einem.</p>
<p style="text-align:center;margin:20px 0;">
<a href="https://www.checkout-ds24.com/product/704677" style="background:#1e40af;color:white;padding:14px 36px;text-decoration:none;border-radius:8px;font-size:1rem;font-weight:700;">
SuperMegaBot System — 97 Euro →
</a>
</p>
<p>Oder starte klein mit dem Grundsystem:</p>
<p style="text-align:center;">
<a href="https://www.checkout-ds24.com/product/668035" style="color:#FF6B00;font-weight:700;">AI Income Machine — 37 Euro →</a>
</p>
<p>Rudolf</p>
</div></body></html>""",
        "text": "Upsell: SuperMegaBot System 97 Euro https://www.checkout-ds24.com/product/704677 oder Einsteiger 37 Euro https://www.checkout-ds24.com/product/668035",
    },
]


def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


def get_campaign_index() -> int:
    week = datetime.now(timezone.utc).isocalendar().week
    day = datetime.now(timezone.utc).weekday()
    return (week * 7 + day) % len(CAMPAIGNS)


def create_and_send_campaign(camp: dict) -> bool:
    # 1. Create template
    r = requests.post(
        "https://a.klaviyo.com/api/templates/",
        headers=H,
        json={
            "data": {
                "type": "template",
                "attributes": {
                    "name": f"AutoCampaign-{camp['name'][:40]}",
                    "editor_type": "CODE",
                    "html": camp["html"],
                    "text": camp["text"],
                },
            }
        },
    )
    if r.status_code != 201:
        print(f"Template create failed: {r.status_code} {r.text[:200]}")
        return False
    tmpl_id = r.json()["data"]["id"]
    print(f"Template created: {tmpl_id}")

    time.sleep(1)

    # 2. Create campaign
    r2 = requests.post(
        "https://a.klaviyo.com/api/campaigns/",
        headers=H,
        json={
            "data": {
                "type": "campaign",
                "attributes": {
                    "name": f"{camp['name']} [{datetime.now(timezone.utc).strftime('%Y-%m-%d')}]",
                    "audiences": {"included": [LIST_ID], "excluded": []},
                    "send_strategy": {"method": "immediate"},
                    "campaign-messages": {
                        "data": [
                            {
                                "type": "campaign-message",
                                "attributes": {
                                    "channel": "email",
                                    "label": camp["name"],
                                    "content": {
                                        "subject": camp["subject"],
                                        "preview_text": camp["preview"],
                                        "from_email": "newsletter@aiitec.de",
                                        "from_label": "AiiteC KI-Automation",
                                        "reply_to_email": "support@aiitec.de",
                                    },
                                },
                            }
                        ]
                    },
                },
            }
        },
    )
    if r2.status_code not in (200, 201):
        print(f"Campaign create failed: {r2.status_code} {r2.text[:200]}")
        return False
    camp_id = r2.json()["data"]["id"]
    print(f"Campaign created: {camp_id}")

    time.sleep(1)

    # 3. Get message ID
    r3 = requests.get(f"https://a.klaviyo.com/api/campaigns/{camp_id}/campaign-messages/", headers=H)
    if r3.status_code != 200 or not r3.json().get("data"):
        print("Could not get message ID")
        return False
    msg_id = r3.json()["data"][0]["id"]

    # 4. Assign template
    r4 = requests.post(
        "https://a.klaviyo.com/api/campaign-message-assign-template/",
        headers=H,
        json={
            "data": {
                "type": "campaign-message",
                "id": msg_id,
                "relationships": {"template": {"data": {"type": "template", "id": tmpl_id}}},
            }
        },
    )
    if r4.status_code not in (200, 201, 202):
        print(f"Template assign failed: {r4.status_code} {r4.text[:200]}")
        return False
    print(f"Template assigned to message {msg_id}")

    time.sleep(1)

    # 5. Send campaign
    r5 = requests.post(
        "https://a.klaviyo.com/api/campaign-send-jobs/",
        headers=H,
        json={"data": {"type": "campaign-send-job", "attributes": {"id": camp_id}}},
    )
    if r5.status_code not in (200, 201, 202):
        print(f"Send failed: {r5.status_code} {r5.text[:200]}")
        return False
    print(f"Campaign sent: {camp_id}")
    return True


if __name__ == "__main__":
    idx = get_campaign_index()
    camp = CAMPAIGNS[idx]
    print(f"Sending campaign #{idx}: {camp['name']}")

    success = create_and_send_campaign(camp)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if success:
        send_telegram(
            f"✅ <b>Auto-Kampagne gesendet</b> [{date}]\n\n"
            f"📧 <b>{camp['name']}</b>\n"
            f"Betreff: {camp['subject']}\n"
            f"An: Liste Xwxq6V (20 Subscriber)\n\n"
            f"Nächste Kampagne: in 3-4 Tagen"
        )
        print("SUCCESS")
    else:
        send_telegram(
            f"⚠️ <b>Auto-Kampagne FEHLGESCHLAGEN</b> [{date}]\n"
            f"Kampagne: {camp['name']}\n"
            f"→ Manuell prüfen: app.klaviyo.com"
        )
        print("FAILED")
        exit(1)
