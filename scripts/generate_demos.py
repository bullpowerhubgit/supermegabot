#!/usr/bin/env python3
"""Generiert interaktive demo.html für alle High-Ticket Landing Pages."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = ROOT / "netlify-deploy"

DEMOS = [
    {
        "dir": "bullpower-ai",
        "name": "BullPower AI",
        "color": "#6c63ff",
        "color2": "#00d4ff",
        "tabs": ["Content Generator", "Lead Radar", "Revenue Dashboard", "Social Autopilot"],
        "demo_content": {
            "Content Generator": {
                "title": "KI Content Generator — Live Demo",
                "desc": "Gib ein Thema ein und sieh wie BullPower AI in Sekunden professionellen Content erstellt.",
                "input_label": "Thema / Keyword",
                "input_placeholder": "z.B. Shopify Automatisierung 2026",
                "output_title": "Generierter Content (Instagram Post)",
                "output": """🚀 Shopify Automatisierung 2026 — So verdienen Top-Seller 10x mehr ohne mehr zu arbeiten

Die Realität: 87% aller Shopify-Stores lassen täglich Geld auf dem Tisch liegen. Nicht wegen schlechter Produkte — sondern wegen fehlender Automatisierung.

Was passiert wenn du automatisierst:
✅ Produkte werden 24/7 optimiert
✅ Preise passen sich dem Markt an
✅ Kunden erhalten personalisierte E-Mails
✅ Neue Trends werden sofort erkannt

Das Ergebnis? Durchschnittlich +340% Conversion-Rate in 30 Tagen.

Welcher dieser Punkte kostet dich gerade am meisten? 👇

#Shopify #Ecommerce #Automatisierung #OnlineShop #DigitalBusiness""",
            },
            "Lead Radar": {
                "title": "Lead Radar — Live Demo",
                "desc": "Der Lead Radar scannt täglich 50.000+ Quellen und liefert kaufbereite Kontakte.",
                "input_label": "Zielgruppe",
                "input_placeholder": "z.B. Shopify Merchant, Deutschland, 1M+ Umsatz",
                "output_title": "Gefundene Leads (letzte 24h)",
                "output": """LEAD RADAR — 1.247 neue Leads gefunden ✅

Kontakt 1: Thomas M. — CEO @ AutoShop GmbH
Intent-Signale: "Shopify Skalierung", "Automatisierung suche"
Kontakt: thomas.m@autoshop-gmbh.de | LinkedIn: /in/thomasm
Score: 94/100 (SEHR HEISS)

Kontakt 2: Sandra K. — Gründerin @ FashionBoutique
Intent-Signale: "Shopify App", "mehr Umsatz", "Zeit sparen"
Kontakt: sk@fashionboutique.de | Tel: +49 172 xxx xxxx
Score: 87/100 (HEISS)

Kontakt 3: Marcus W. — E-Commerce Manager
Intent-Signale: B2B-Einkauf, "Automatisierung evaluiert"
Kontakt: m.weber@techstore-ag.de
Score: 81/100 (WARM)

[... + 1.244 weitere Leads]
Ø Cost per Lead: €0,39""",
            },
            "Revenue Dashboard": {
                "title": "Revenue Dashboard — Live Demo",
                "desc": "Dein kompletter Revenue-Überblick in Echtzeit. Alle Streams, ein Dashboard.",
                "input_label": "Zeitraum",
                "input_placeholder": "Diese Woche",
                "output_title": "Revenue Übersicht",
                "output": """REVENUE DASHBOARD — Diese Woche

💰 Gesamt-Revenue: €14.820
├─ Shopify Store: €8.240 (+34% ggü. Vorwoche)
├─ Affiliate (DS24): €3.120 (+18%)
├─ E-Mail Liste: €2.180 (+41%)
└─ Telegram Subs: €1.280 (+22%)

📈 Top-Produkte:
1. Smart Home Hub Set — €3.420 (41 Verkäufe)
2. Solar Powerstation — €2.180 (7 Verkäufe)
3. DS24 Affiliate: KI-Kurs — €1.840 (23 Sales)

🎯 KI-Empfehlung:
Produkt "Smart Home Hub" zeigt 3x Conversion-Peak
Di-Do 18-22h → Erhöhe Budget in diesem Slot um €200/Tag
Erwarteter Effekt: +€1.400/Woche

⚡ Auto-Aktionen heute:
• 47 Produkte preisoptimiert
• 312 Abandoned Carts zurückgeholt
• 8.400 SEO-Keywords aktualisiert""",
            },
            "Social Autopilot": {
                "title": "Social Autopilot — Live Demo",
                "desc": "Automatische Posts auf 7 Plattformen — abgestimmt auf Peak-Zeiten deiner Zielgruppe.",
                "input_label": "Plattform + Ziel",
                "input_placeholder": "Instagram — Produkt bewerben",
                "output_title": "Geplante Posts diese Woche",
                "output": """SOCIAL AUTOPILOT — 34 Posts geplant ✅

📅 MONTAG 09:15
Instagram: "Warum 87% der Shopify-Stores scheitern..."
Predicted Reach: 4.200 | Engagement: 6.8%

📅 MONTAG 18:30
Facebook: Produktvorstellung Smart Home Hub
Ad Budget: €12 | Expected ROAS: 4.2x

📅 DIENSTAG 07:45
LinkedIn: Thought Leadership "Automatisierung 2026"
Target: 2.400 Impressions | 180 Klicks

📅 DIENSTAG 19:00
TikTok: Behind-the-Scenes Automatisierung (30s)
Predicted Views: 8.000 | Saves: 340

[... + 30 weitere Posts]

Performance letzte 7 Tage:
• 128.000 Gesamtreichweite
• 6.240 Website-Klicks
• 312 Leads generiert""",
            },
        },
    },
    {
        "dir": "bullpower-hub",
        "name": "BullPower Hub",
        "color": "#00d4ff",
        "color2": "#6c63ff",
        "tabs": ["E-Commerce Control", "Shopify Sync", "DS24 Blast", "Analytics"],
        "demo_content": {
            "E-Commerce Control": {
                "title": "E-Commerce Control Center — Live",
                "desc": "Alle Revenue-Streams auf einem Blick. Vollständige Kontrolle, null manueller Aufwand.",
                "input_label": "Store / Kanal auswählen",
                "input_placeholder": "Alle Kanäle",
                "output_title": "Control Center Übersicht",
                "output": """E-COMMERCE CONTROL CENTER — Live

🏪 SHOPIFY STORE (ineedit.com.co)
Status: ✅ Aktiv | 9.847 Produkte live
Today: €2.840 | Orders: 33 | AOV: €86
Trending: Solar Sets (+280%), Smart Home (+180%)

📦 DIGISTORE24 AFFILIATE
Status: ✅ Aktiv | 449 Produkte bewirbt
Today: €480 | Conversions: 12 | CR: 2.1%
Top: KI-Kurs €240, Shopify Guide €180

📧 E-MAIL MARKETING (Klaviyo)
Status: ✅ Aktiv | 14.200 Subscriber
Today: 3 Kampagnen versendet | OR: 31%
Revenue attributed: €620

📱 TELEGRAM BOTS
Status: ✅ Aktiv | 847 Premium-Subscriber
MRR: €24.563 | Churn: 3.2%

🤖 HEUTE AUTO-AUSGEFÜHRT:
• 1.247 Leads qualifiziert
• 89 Produkte SEO-optimiert
• 3 A/B-Tests gestartet
• 12 Abandoned Carts zurückgewonnen""",
            },
            "Shopify Sync": {
                "title": "Shopify Vollsync — Live Demo",
                "desc": "10.000+ Produkte werden automatisch synchronisiert, optimiert und für SEO vorbereitet.",
                "input_label": "Sync-Typ",
                "input_placeholder": "Vollsync aller Produkte",
                "output_title": "Sync Status",
                "output": """SHOPIFY SYNC — Läuft ⚡

Fortschritt: 8.492 / 9.847 Produkte ████████░░ 86%

Letzte Aktionen:
✅ Smart Home Hub Set — Preis optimiert: €89 → €94
✅ Solar Powerstation 1000W — SEO-Tags hinzugefügt
✅ LED Strip Premium — Beschreibung KI-verbessert
✅ Smart Lock Pro — Auf Seite 1 von 3 Collections
✅ Wireless Charger Set — Bilder komprimiert (98→72kb)

SEO-Verbesserungen heute:
• 847 Produkttitel keyword-optimiert
• 1.240 Meta-Descriptions neu geschrieben
• 312 fehlende Alt-Texte ergänzt
• 89 Produkte in neue Collections einsortiert

Performance:
• Organischer Traffic: +28% diese Woche
• Indexed URLs: 9.847 → 9.909 (+62 neu)
• Avg. Position: 4.8 (war 7.2)""",
            },
            "DS24 Blast": {
                "title": "Digistore24 Affiliate Blast — Live",
                "desc": "449 DS24-Produkte werden automatisch beworben — maximale Provision, null Aufwand.",
                "input_label": "Kategorie",
                "input_placeholder": "Alle Kategorien",
                "output_title": "Blast Ergebnisse",
                "output": """DS24 AFFILIATE BLAST — Ergebnisse

🚀 HEUTE DEPLOYED: 34 Content-Pieces

Top-Performer diese Woche:
1. "KI-Automatisierung Masterclass" (ID: 487231)
   Provision: 50% × €197 = €98,50
   Verkäufe: 8 | Revenue: €788

2. "Shopify Dropshipping Guide 2026" (ID: 392847)
   Provision: 40% × €147 = €58,80
   Verkäufe: 12 | Revenue: €706

3. "Passive Income Blueprint" (ID: 291038)
   Provision: 50% × €97 = €48,50
   Verkäufe: 14 | Revenue: €679

GESAMT DIESE WOCHE:
├─ Affiliate Revenue: €3.847
├─ Aktive Produkte: 449/449
├─ Content deployed: 238 Pieces
└─ Traffic generiert: 24.200 Klicks""",
            },
            "Analytics": {
                "title": "Analytics Dashboard — Live",
                "desc": "Vollständige Attribution aller Revenue-Quellen mit KI-Empfehlungen.",
                "input_label": "Zeitraum",
                "input_placeholder": "Letzte 30 Tage",
                "output_title": "Analytics Report",
                "output": """ANALYTICS — Letzte 30 Tage

📊 REVENUE ATTRIBUTION
├─ Organischer SEO-Traffic: 41% (€21.840)
├─ E-Mail-Marketing: 28% (€14.920)
├─ Social Media: 18% (€9.580)
├─ Paid Ads: 9% (€4.790)
└─ Direkt: 4% (€2.130)

🎯 CONVERSION FUNNEL
Besucher: 84.200
→ Produktseite: 31.400 (37%)
→ Warenkorb: 4.710 (5.6%)
→ Kauf: 1.884 (2.24%)

💡 KI-EMPFEHLUNGEN:
1. E-Mail-Sequenz verlängern (CR +0.3% erwartet)
2. Solar-Kategorie hat 3x höheres ROAS → Budget ++
3. Abandoned Cart nach 2h senden (jetzt: 6h)
4. Dienstag 18-21h = Peak → automatisch erhöht

ROI dieser Periode: 847%
Nächste Empfehlung: Preistest Kategorie "Smart Home" (+€12 AOV möglich)""",
            },
        },
    },
    {
        "dir": "shopify-brutal-tuning",
        "name": "Shopify Brutal Tuning",
        "color": "#ff6b35",
        "color2": "#ffd700",
        "tabs": ["A/B Tester", "Speed Optimizer", "Checkout Flow", "CRO Report"],
        "demo_content": {
            "A/B Tester": {
                "title": "A/B Tester — Live Demo",
                "desc": "50+ Elemente werden gleichzeitig getestet. Kein manuelles Eingreifen nötig.",
                "input_label": "Seite zum Testen",
                "input_placeholder": "Produktseite Smart Home Hub",
                "output_title": "Laufende A/B-Tests",
                "output": """A/B TESTER — 47 aktive Tests ⚡

TEST #1 — Produkttitel (Signifikanz: 94%)
A: "Smart Home Hub Set" — CR: 2.1%
B: "Smart Home Hub Set — Komplett-Set mit App" — CR: 3.4%
→ Gewinner: B (+62% CR) | Deploye in 2h

TEST #2 — CTA Button Farbe (Signifikanz: 87%)
A: Blau "#0066CC" — CR: 2.8%
B: Orange "#FF6B35" — CR: 4.1%
→ Gewinner: B (+46%) | Deploye morgen

TEST #3 — Preis-Anzeige (Signifikanz: 91%)
A: "€89,00" — CR: 3.2%
B: "€89,00 (statt €129,00)" — CR: 4.8%
→ Gewinner: B (+50%) | Deploye heute Nacht

TEST #4 — Bewertungen Position (läuft...)
A: Unten — CR: bisher 2.9%
B: Direkt unter Titel — CR: bisher 4.2%
→ Noch 2 Tage bis Signifikanz

IMPACT DIESE WOCHE:
• 8 Tests abgeschlossen → alle B gewonnen
• Conversion-Steigerung: +2.1 Prozentpunkte
• Umsatz-Impact: +€3.840/Woche""",
            },
            "Speed Optimizer": {
                "title": "Speed Optimizer — Live Analyse",
                "desc": "Core Web Vitals auf 95+ optimiert. Jede Sekunde Ladezeit = 7% CR-Verlust.",
                "input_label": "URL zum Analysieren",
                "input_placeholder": "deinshop.myshopify.com",
                "output_title": "Speed Score Analyse",
                "output": """SPEED OPTIMIZER — Analyse abgeschlossen

VORHER:
├─ PageSpeed Score: 42/100 ⚠️
├─ LCP (Largest Contentful Paint): 6.2s
├─ FID (First Input Delay): 340ms
├─ CLS (Cumulative Layout Shift): 0.42
└─ Total Blocking Time: 1.840ms

NACHHER (nach Brutal Tuning):
├─ PageSpeed Score: 96/100 ✅
├─ LCP: 1.1s (-82%)
├─ FID: 28ms (-92%)
├─ CLS: 0.04 (-90%)
└─ Total Blocking Time: 180ms (-90%)

WAS OPTIMIERT WURDE:
✅ 47 Bilder WebP-konvertiert (58% kleiner)
✅ CSS/JS minifiziert und lazy-loaded
✅ Third-Party Scripts verzögert
✅ Kritischer CSS inline eingefügt
✅ CDN-Caching konfiguriert (24h TTL)
✅ Fonts subseted und preloaded

ERWARTETE CR-VERBESSERUNG: +23%
(Basierend auf Google: -1s Ladezeit = +7% CR)""",
            },
            "Checkout Flow": {
                "title": "Checkout Flow Optimierung",
                "desc": "Jeder Schritt im Checkout wird analysiert und optimiert — weniger Abbrüche, mehr Käufe.",
                "input_label": "Shop Domain",
                "input_placeholder": "deinshop.myshopify.com",
                "output_title": "Checkout Analyse",
                "output": """CHECKOUT FLOW — Analyse & Optimierung

AKTUELLER FUNNEL (IST):
Produktseite → 100%
→ Warenkorb: 48% (52% verlassen)
→ Checkout-Start: 31%
→ Lieferadresse: 24%
→ Zahlung: 18%
→ Kauf abgeschlossen: 12%

HAUPTABBRUCHGRÜNDE (KI-Analyse):
1. "Versandkosten Überraschung" — 38% der Abbrüche
2. "Zu viele Pflichtfelder" — 24%
3. "Kein Trust-Signal bei Zahlung" — 18%
4. "Nur 1 Zahlmethode" — 12%

BRUTAL TUNING FIXES (SOLL):
✅ Versandkosten auf Produktseite zeigen
✅ Guest Checkout als Standard
✅ PayPal + Klarna hinzugefügt
✅ SSL-Badge + Bewertungen im Checkout
✅ 1-Click-Reorder für Stammkunden

ERWARTETES ERGEBNIS:
Checkout-CR: 12% → 21% (+75%)
Umsatz-Impact: +€4.800/Monat""",
            },
            "CRO Report": {
                "title": "CRO Report — Diese Woche",
                "desc": "Vollständiger Conversion-Rate-Optimization Report mit konkreten Zahlen.",
                "input_label": "Report-Zeitraum",
                "input_placeholder": "Diese Woche",
                "output_title": "CRO Zusammenfassung",
                "output": """CRO WEEKLY REPORT ━━━━━━━━━━━━━━

CONVERSION RATE ENTWICKLUNG:
KW28 (Vorwoche): 1.8%
KW29 (Diese Woche): 3.4% (+88%) ✅

UMSATZ-IMPACT:
Traffic: 18.400 Besucher (unverändert)
Käufe vorher: 331 Orders × €84 AOV = €27.804
Käufe jetzt: 626 Orders × €87 AOV = €54.462
MEHRUMSATZ: +€26.658 Diese Woche 🚀

TOP 5 MASSNAHMEN DIESE WOCHE:
1. Bewertungen unter Titel → +0.4% CR
2. "Kostenloser Versand ab €49" Banner → +0.3%
3. Farb-A/B-Test (Orange CTA) → +0.3%
4. Mobile Checkout vereinfacht → +0.2%
5. Trust-Badges Checkout → +0.2%

NÄCHSTE WOCHE GEPLANT:
• Upsell nach Purchase testen
• Countdown-Timer für "Nur noch 3 auf Lager"
• Personalisierte Startseite (Wiederkehrende)

ROI des Brutal Tuning Pakets: 2.847%""",
            },
        },
    },
]

# Simple demo for products not in detailed list above
SIMPLE_DEMO_PRODUCTS = [
    ("cognitive-symphony", "DS24 Pro Suite", "#7c3aed", "#06b6d4"),
    ("creatorai-ultra", "CreatorAI Ultra", "#059669", "#10b981"),
    ("creatorstudio-pro", "CreatorStudio Pro", "#dc2626", "#f59e0b"),
    ("autoincome-ai", "AutoIncome AI", "#d97706", "#fbbf24"),
    ("shopify-acquisition-engine", "Shopify Acquisition Engine", "#2563eb", "#3b82f6"),
    ("shopify-suite", "Shopify Suite Pro", "#7c3aed", "#a78bfa"),
    ("steuercockpit", "SteuercockPit Pro", "#16a34a", "#4ade80"),
    ("telegram-bot", "Telegram Agency Bot", "#0284c7", "#38bdf8"),
    ("lead-capture", "Lead Capture Pro", "#dc2626", "#f97316"),
    ("launcher", "BullPower Launcher", "#7c3aed", "#c026d3"),
    ("digistore24-suite", "Digistore24 Full Suite", "#b45309", "#f59e0b"),
    ("icomeauto", "IcomeAuto OS", "#0f766e", "#14b8a6"),
    ("gumroad-discord", "Gumroad & Discord Suite", "#7e22ce", "#9333ea"),
]


def generate_simple_demo(dir_name: str, name: str, color: str, color2: str) -> str:
    metrics = [
        ("€12.400", "Ø Mehrumsatz/Monat"),
        ("87%", "Zeitersparnis"),
        ("30 Min", "Setup-Zeit"),
        ("30 Tage", "bis ROI"),
    ]
    metrics_html = "\n".join(
        f'<div class="metric"><div class="metric-val">{v}</div><div class="metric-lbl">{l}</div></div>'
        for v, l in metrics
    )

    features = [
        "✅ Vollautomatischer Betrieb 24/7",
        "✅ KI-optimierte Ergebnisse",
        "✅ DSGVO-konform",
        "✅ Echtzeit-Analytics Dashboard",
        "✅ Dedizierter Onboarding Support",
        "✅ 30-Tage Geld-zurück-Garantie",
    ]
    features_html = "\n".join(f"<li>{f}</li>" for f in features)

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} — Interaktive Demo</title>
<style>
:root {{ --bg:#0a0a0f; --s:#13131a; --s2:#1a1a24; --bd:#2a2a3d; --a:{color}; --a2:{color2}; --t:#e8e8f0; --m:#888899; --g:#00ff88; }}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--t);font-family:-apple-system,'Inter','Segoe UI',sans-serif;min-height:100vh;}}
.header{{background:rgba(10,10,15,0.95);border-bottom:1px solid var(--bd);padding:1rem 5%;display:flex;align-items:center;justify-content:space-between;}}
.logo{{font-size:1.2rem;font-weight:900;background:linear-gradient(135deg,var(--a),var(--a2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}}
.back-btn{{color:var(--m);text-decoration:none;font-size:0.9rem;}}
.back-btn:hover{{color:var(--t);}}
.hero{{padding:60px 5% 40px;text-align:center;}}
.demo-badge{{display:inline-block;background:rgba(108,99,255,0.15);border:1px solid rgba(108,99,255,0.4);color:var(--a2);padding:0.4rem 1.2rem;border-radius:50px;font-size:0.85rem;font-weight:600;margin-bottom:1.5rem;text-transform:uppercase;letter-spacing:0.05em;}}
h1{{font-size:clamp(1.8rem,4vw,3rem);font-weight:900;margin-bottom:1rem;}}
h1 span{{background:linear-gradient(135deg,var(--a),var(--a2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}}
.hero p{{color:var(--m);max-width:600px;margin:0 auto 2rem;font-size:1.05rem;}}
.metrics{{display:flex;gap:1.5rem;justify-content:center;flex-wrap:wrap;margin-bottom:3rem;}}
.metric{{background:var(--s);border:1px solid var(--bd);border-radius:12px;padding:1.2rem 2rem;text-align:center;min-width:140px;}}
.metric-val{{font-size:1.8rem;font-weight:900;background:linear-gradient(135deg,var(--a),var(--a2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}}
.metric-lbl{{color:var(--m);font-size:0.8rem;margin-top:0.3rem;}}
.demo-container{{max-width:900px;margin:0 auto;padding:0 5% 60px;}}
.demo-screen{{background:var(--s);border:1px solid var(--bd);border-radius:20px;overflow:hidden;}}
.screen-bar{{background:var(--s2);padding:0.8rem 1.5rem;display:flex;align-items:center;gap:0.5rem;border-bottom:1px solid var(--bd);}}
.dot{{width:12px;height:12px;border-radius:50%;}}
.dot.r{{background:#ff5f57;}} .dot.y{{background:#febc2e;}} .dot.g{{background:#28c840;}}
.screen-title{{margin-left:auto;margin-right:auto;color:var(--m);font-size:0.85rem;}}
.screen-body{{padding:2rem;}}
.screen-body h3{{font-size:1.2rem;font-weight:700;margin-bottom:1rem;}}
.feature-list{{list-style:none;}}
.feature-list li{{padding:0.7rem 0;border-bottom:1px solid var(--bd);color:var(--m);font-size:0.95rem;}}
.feature-list li:last-child{{border-bottom:none;}}
.live-indicator{{display:flex;align-items:center;gap:0.5rem;color:var(--g);font-size:0.85rem;font-weight:600;margin-bottom:1.5rem;}}
.live-dot{{width:8px;height:8px;border-radius:50%;background:var(--g);animation:pulse 1.5s infinite;}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.3}}}}
.cta-section{{text-align:center;padding:2rem 5% 4rem;}}
.cta-section h2{{font-size:1.6rem;font-weight:800;margin-bottom:1rem;}}
.btn{{display:inline-block;background:linear-gradient(135deg,var(--a),#5b52ef);color:white;padding:1rem 2.5rem;border-radius:12px;text-decoration:none;font-weight:700;font-size:1.05rem;transition:all 0.3s;box-shadow:0 8px 30px rgba(108,99,255,0.3);}}
.btn:hover{{transform:translateY(-3px);box-shadow:0 12px 40px rgba(108,99,255,0.4);}}
</style>
</head>
<body>
<header class="header">
  <div class="logo">{name}</div>
  <a href="index.html" class="back-btn">← Zurück zur Übersicht</a>
</header>
<section class="hero">
  <div class="demo-badge">🎯 Interaktive Demo</div>
  <h1><span>{name}</span><br>Live erleben</h1>
  <p>Sieh in Echtzeit was {name} für dein Business leisten kann — ohne Anmeldung, ohne Kreditkarte.</p>
  <div class="metrics">
    {metrics_html}
  </div>
</section>
<div class="demo-container">
  <div class="demo-screen">
    <div class="screen-bar">
      <div class="dot r"></div>
      <div class="dot y"></div>
      <div class="dot g"></div>
      <div class="screen-title">{name} Dashboard</div>
    </div>
    <div class="screen-body">
      <div class="live-indicator"><div class="live-dot"></div> Live System aktiv</div>
      <h3>🚀 Was {name} gerade für dich tut:</h3>
      <ul class="feature-list">
        {features_html}
      </ul>
    </div>
  </div>
</div>
<div class="cta-section">
  <h2>Bereit loszulegen?</h2>
  <p style="color:var(--m);margin-bottom:2rem;">30 Tage Geld-zurück-Garantie. Setup in 30 Minuten.</p>
  <a href="index.html#preise" class="btn">Jetzt starten →</a>
</div>
</body>
</html>"""


def generate_full_demo(p: dict) -> str:
    name = p["name"]
    color = p["color"]
    color2 = p["color2"]
    tabs = p["tabs"]
    content = p["demo_content"]

    tabs_html = "\n".join(
        f'<button class="tab-btn {"active" if i == 0 else ""}" onclick="showTab(\'{t.replace(" ", "_")}\', this)">{t}</button>'
        for i, t in enumerate(tabs)
    )

    panels_html = ""
    for i, (tab, data) in enumerate(content.items()):
        panel_id = tab.replace(" ", "_")
        display = "block" if i == 0 else "none"
        panels_html += f"""
        <div id="panel_{panel_id}" class="panel" style="display:{display}">
          <div class="panel-header">
            <h3>{data["title"]}</h3>
            <p>{data["desc"]}</p>
          </div>
          <div class="input-row">
            <label>{data["input_label"]}:</label>
            <input type="text" value="{data["input_placeholder"]}" class="demo-input" onchange="simulateAction(this)" />
            <button class="run-btn" onclick="simulateAction(this.previousElementSibling)">▶ Ausführen</button>
          </div>
          <div class="output-box">
            <div class="output-header">
              <span class="live-dot"></span> {data["output_title"]}
            </div>
            <pre class="output-text">{data["output"].strip()}</pre>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} — Interaktive Demo</title>
<style>
:root {{ --bg:#0a0a0f; --s:#13131a; --s2:#1a1a24; --bd:#2a2a3d; --a:{color}; --a2:{color2}; --t:#e8e8f0; --m:#888899; --g:#00ff88; }}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--t);font-family:-apple-system,'Inter','Segoe UI',sans-serif;min-height:100vh;}}
.header{{background:rgba(10,10,15,0.95);border-bottom:1px solid var(--bd);padding:1rem 5%;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;}}
.logo{{font-size:1.2rem;font-weight:900;background:linear-gradient(135deg,var(--a),var(--a2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}}
.back-btn{{color:var(--m);text-decoration:none;font-size:0.9rem;border:1px solid var(--bd);padding:0.4rem 1rem;border-radius:8px;transition:all 0.2s;}}
.back-btn:hover{{color:var(--t);border-color:var(--a);}}
.hero{{padding:50px 5% 30px;text-align:center;}}
.demo-badge{{display:inline-block;background:rgba(108,99,255,0.15);border:1px solid rgba(108,99,255,0.4);color:var(--a2);padding:0.4rem 1.2rem;border-radius:50px;font-size:0.85rem;font-weight:600;margin-bottom:1.5rem;text-transform:uppercase;letter-spacing:0.05em;animation:fadein 0.5s ease;}}
@keyframes fadein{{from{{opacity:0;transform:translateY(-10px)}}to{{opacity:1;transform:translateY(0)}}}}
h1{{font-size:clamp(1.8rem,4vw,3rem);font-weight:900;margin-bottom:0.8rem;}}
h1 span{{background:linear-gradient(135deg,var(--a),var(--a2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}}
.hero-sub{{color:var(--m);max-width:600px;margin:0 auto 2rem;font-size:1.05rem;}}
.demo-area{{max-width:1000px;margin:0 auto;padding:0 5% 60px;}}
.tab-bar{{display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:1.5rem;background:var(--s);border-radius:12px;padding:0.5rem;border:1px solid var(--bd);}}
.tab-btn{{background:transparent;border:none;color:var(--m);padding:0.7rem 1.2rem;border-radius:8px;cursor:pointer;font-size:0.9rem;font-weight:600;transition:all 0.2s;}}
.tab-btn:hover{{color:var(--t);background:var(--s2);}}
.tab-btn.active{{background:linear-gradient(135deg,var(--a),var(--a2));color:white;}}
.panel{{background:var(--s);border:1px solid var(--bd);border-radius:16px;overflow:hidden;}}
.panel-header{{padding:1.5rem 2rem;border-bottom:1px solid var(--bd);}}
.panel-header h3{{font-size:1.1rem;font-weight:700;margin-bottom:0.4rem;}}
.panel-header p{{color:var(--m);font-size:0.9rem;}}
.input-row{{padding:1.2rem 2rem;display:flex;gap:0.8rem;align-items:flex-end;flex-wrap:wrap;border-bottom:1px solid var(--bd);}}
.input-row label{{color:var(--m);font-size:0.85rem;display:block;margin-bottom:0.4rem;width:100%;}}
.demo-input{{flex:1;min-width:200px;background:var(--s2);border:2px solid var(--bd);border-radius:10px;padding:0.8rem 1.2rem;color:var(--t);font-size:0.95rem;outline:none;transition:border-color 0.2s;}}
.demo-input:focus{{border-color:var(--a);}}
.run-btn{{background:linear-gradient(135deg,var(--a),var(--a2));color:white;border:none;padding:0.8rem 1.5rem;border-radius:10px;cursor:pointer;font-weight:700;font-size:0.9rem;transition:all 0.2s;white-space:nowrap;}}
.run-btn:hover{{transform:translateY(-2px);box-shadow:0 6px 20px rgba(108,99,255,0.3);}}
.output-box{{padding:1.5rem 2rem;}}
.output-header{{display:flex;align-items:center;gap:0.5rem;margin-bottom:1rem;color:var(--g);font-size:0.85rem;font-weight:600;}}
.live-dot{{width:8px;height:8px;border-radius:50%;background:var(--g);animation:pulse 1.5s infinite;flex-shrink:0;}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.3}}}}
.output-text{{background:var(--s2);border:1px solid var(--bd);border-radius:12px;padding:1.5rem;font-size:0.85rem;line-height:1.7;white-space:pre-wrap;font-family:'SF Mono','Fira Code',monospace;color:var(--t);max-height:350px;overflow-y:auto;}}
.cta-section{{text-align:center;padding:2rem 5% 4rem;border-top:1px solid var(--bd);}}
.cta-section h2{{font-size:1.6rem;font-weight:800;margin-bottom:1rem;}}
.btn{{display:inline-block;background:linear-gradient(135deg,var(--a),var(--a2));color:white;padding:1rem 2.5rem;border-radius:12px;text-decoration:none;font-weight:700;font-size:1.05rem;transition:all 0.3s;box-shadow:0 8px 30px rgba(108,99,255,0.3);}}
.btn:hover{{transform:translateY(-3px);box-shadow:0 12px 40px rgba(108,99,255,0.4);}}
</style>
</head>
<body>
<header class="header">
  <div class="logo">{name} Demo</div>
  <a href="index.html" class="back-btn">← Zur Hauptseite</a>
</header>
<section class="hero">
  <div class="demo-badge">🎯 Interaktive Live-Demo — Kein Account nötig</div>
  <h1><span>{name}</span><br>in Aktion erleben</h1>
  <p class="hero-sub">Teste alle Features direkt im Browser. Echte Funktionen, echte Daten-Simulation.</p>
</section>
<div class="demo-area">
  <div class="tab-bar">
    {tabs_html}
  </div>
  {panels_html}
</div>
<div class="cta-section">
  <h2>Überzeugt? Starte noch heute.</h2>
  <p style="color:var(--m);margin-bottom:2rem;max-width:500px;margin-left:auto;margin-right:auto;">30 Tage Geld-zurück-Garantie. Setup in 30 Minuten. Erste Ergebnisse in 7-14 Tagen.</p>
  <a href="index.html#preise" class="btn">Jetzt starten — Preise ansehen →</a>
</div>
<script>
function showTab(id, btn) {{
  document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('panel_' + id).style.display = 'block';
  btn.classList.add('active');
}}
function simulateAction(input) {{
  const output = input.closest('.panel').querySelector('.output-text');
  const orig = output.textContent;
  output.textContent = '⏳ KI verarbeitet...';
  setTimeout(() => {{ output.textContent = orig; }}, 1200);
}}
</script>
</body>
</html>"""


def generate_all_demos():
    count = 0
    for p in DEMOS:
        d = DEPLOY_DIR / p["dir"]
        d.mkdir(exist_ok=True)
        html = generate_full_demo(p)
        (d / "demo.html").write_text(html, encoding="utf-8")
        print(f"✅ Demo: {p['dir']}/demo.html ({len(html):,} Bytes)")
        count += 1

    for dir_name, name, color, color2 in SIMPLE_DEMO_PRODUCTS:
        d = DEPLOY_DIR / dir_name
        d.mkdir(exist_ok=True)
        html = generate_simple_demo(dir_name, name, color, color2)
        (d / "demo.html").write_text(html, encoding="utf-8")
        print(f"✅ Demo: {dir_name}/demo.html ({len(html):,} Bytes)")
        count += 1

    print(f"\n✅ {count} Demo-Seiten generiert!")


if __name__ == "__main__":
    generate_all_demos()
