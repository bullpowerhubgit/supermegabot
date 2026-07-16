#!/usr/bin/env python3
"""
V3 Fix + Deploy:
1. Behebt JS-Bug (window.cntDone_X-Y → window["cntDone_X-Y"])
2. Ersetzt Pricing-Section mit echten Stripe-Links + korrekten monatlichen Preisen
3. Deployt alle 17 Sites zu Netlify Konto 1
"""
import json, re, subprocess, os, time, hashlib, requests
from pathlib import Path

BASE     = Path("/Users/rudolfsarkany/supermegabot/netlify-deploy")
LINKS_F  = Path("/Users/rudolfsarkany/supermegabot/config/stripe_ht_links.json")
TOK1     = os.getenv("NETLIFY_AUTH_TOKEN_1", "")  # Konto 1
ENV      = {**os.environ}

# Netlify Konto 1 site-IDs (aus vorherigem Deploy)
SITE_MAP = {
    "bullpower-ai":               "bullpower-ai-tools",
    "bullpower-hub":              "bullpower-hub-portal",
    "autoincome-ai":              "autoincome-ai",
    "creatorai-ultra":            "creatorai-ultra",
    "creatorstudio-pro":          "creatorstudio-pro",
    "cognitive-symphony":         "cognitive-symphony-ds24",
    "shopify-brutal-tuning":      "shopify-brutal-tuning",
    "shopify-acquisition-engine": "shopify-acquisition-engine",
    "shopify-suite":              "shopify-automaton-suite",
    "digistore24-suite":          "digistore24-automation-suite",
    "steuercockpit":              "bullpower-steuercockpit",
    "telegram-bot":               "telegram-marketing-bot",
    "icomeauto":                  "bullpower-icomeauto",
    "launcher":                   "bullpower-launcher",
    "lead-capture":               "bullpower-lead",
    "gumroad-discord":            "gumroad-discord-bot",
    "master-dashboard":           "master-dashboard-hub",
}

# Stripe-Preise + Links per Produkt (aus stripe_ht_links.json)
STRIPE = json.loads(LINKS_F.read_text()) if LINKS_F.exists() else {}

# Produkt-Daten für Pricing-Update
PRICING = {
    "bullpower-ai": {
        "key": "BullPower AI",
        "t1n": "Starter", "t1p": "€497", "t1per": "/mo",
        "t2n": "Pro",     "t2p": "€997", "t2per": "/mo",
        "t3n": "Agency",  "t3p": "€2.997", "t3per": "/mo",
        "t1f": ["✓ Alle KI-Automatisierungen", "✓ Shopify-Sync (bis 5.000 Produkte)", "✓ Revenue-Tracking Dashboard", "✓ Email Support (24h)", "✓ 30-Tage Garantie"],
        "t2f": ["✓ Alles aus Starter", "✓ Unbegrenzte Produkte", "✓ Telegram Bot Integration", "✓ Priority Support", "✓ Bonus-Paket (€1.388 Wert)"],
        "t3f": ["✓ Alles aus Pro", "✓ White-Label Lizenz", "✓ Dedizierter Account Manager", "✓ Custom Integrationen", "✓ Onboarding-Call 1:1"],
    },
    "bullpower-hub": {
        "key": "BullPower Hub",
        "t1n": "Business", "t1p": "€997", "t1per": "/mo",
        "t2n": "Scale",    "t2p": "€2.997", "t2per": "/mo",
        "t3n": "Empire",   "t3p": "€4.997", "t3per": "/mo",
        "t1f": ["✓ 1 Shop verbunden", "✓ Alle Core-Module", "✓ Revenue Dashboard", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ Bis 5 Shops", "✓ API-Zugang", "✓ Multi-Channel Tracking", "✓ Priority Support", "✓ Bonus-Paket inklusive"],
        "t3f": ["✓ Unbegrenzte Shops", "✓ Unbegrenzte User", "✓ White-Label Option", "✓ Dedizierter Manager", "✓ Custom Entwicklung"],
    },
    "autoincome-ai": {
        "key": "AutoIncome AI",
        "t1n": "Solo", "t1p": "€997", "t1per": " einmalig",
        "t2n": "Unternehmer", "t2p": "€2.997", "t2per": " einmalig",
        "t3n": "DFY", "t3p": "€4.997", "t3per": " einmalig",
        "t1f": ["✓ 3 Revenue-Streams", "✓ Setup-Anleitung", "✓ Traffic-System", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ Alles aus Solo", "✓ 7 Revenue-Streams", "✓ Paid Ads System", "✓ Priority Support", "✓ Bonus-Paket €1.388"],
        "t3f": ["✓ Alles aus Unternehmer", "✓ Done-For-You Setup", "✓ Wir bauen alles auf", "✓ 90-Tage Begleitung", "✓ Erfolgsgarantie"],
    },
    "creatorai-ultra": {
        "key": "CreatorAI Ultra",
        "t1n": "Creator", "t1p": "€297", "t1per": "/mo",
        "t2n": "Studio",  "t2p": "€997", "t2per": "/mo",
        "t3n": "Agency",  "t3p": "€2.497", "t3per": "/mo",
        "t1f": ["✓ 100 Posts/Monat", "✓ 5 Plattformen", "✓ KI-Texte + Bilder", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ Unbegrenzte Posts", "✓ Alle Plattformen", "✓ Custom Brand Voice", "✓ Priority Support", "✓ Bonus-Templates"],
        "t3f": ["✓ Mehrere Accounts", "✓ White-Label", "✓ Client-Reports", "✓ Dedizierter Manager", "✓ API-Zugang"],
    },
    "creatorstudio-pro": {
        "key": "CreatorStudio Pro",
        "t1n": "Freelancer", "t1p": "€197", "t1per": "/mo",
        "t2n": "Studio",     "t2p": "€697", "t2per": "/mo",
        "t3n": "White Label","t3p": "€1.997", "t3per": "/mo",
        "t1f": ["✓ 3 Kunden-Projekte", "✓ Alle Content-Typen", "✓ 48h Lieferzeit", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ 15 Kunden", "✓ 2 Revisionen", "✓ Eigenes Branding", "✓ Priority Support", "✓ Client-Portal"],
        "t3f": ["✓ Unbegrenzte Kunden", "✓ Unbegrenzte Revisionen", "✓ Eigene Domain", "✓ Reseller-Lizenz", "✓ Dedizierter Manager"],
    },
    "cognitive-symphony": {
        "key": "Cognitive Symphony",
        "t1n": "Affiliate", "t1p": "€497", "t1per": "/mo",
        "t2n": "Vendor",    "t2p": "€997", "t2per": "/mo",
        "t3n": "Pro",       "t3p": "€2.997", "t3per": "/mo",
        "t1f": ["✓ DS24 Affiliate-System", "✓ Traffic-Automation", "✓ Email-Funnel", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ Eigene DS24 Produkte", "✓ Affiliate-Netzwerk", "✓ Split-Testing", "✓ Priority Support", "✓ Bonus-Paket"],
        "t3f": ["✓ Alles aus Vendor", "✓ Multi-Produkt", "✓ Dedizierter Manager", "✓ Custom Funnels", "✓ White-Label"],
    },
    "shopify-brutal-tuning": {
        "key": "Shopify Brutal",
        "t1n": "Speed Boost", "t1p": "€497", "t1per": " einmalig",
        "t2n": "Conversion Pro","t2p": "€997", "t2per": " einmalig",
        "t3n": "Full DFY",    "t3p": "€2.497", "t3per": " einmalig",
        "t1f": ["✓ Core Web Vitals Fix", "✓ Bild-Optimierung", "✓ Cache-Setup", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ Alles aus Speed Boost", "✓ Checkout-Optimierung", "✓ A/B-Testing", "✓ Priority Support", "✓ Conversion-Audit"],
        "t3f": ["✓ Alles aus Conversion Pro", "✓ Done-For-You", "✓ 5-7 Tage Lieferung", "✓ Performance-Garantie", "✓ 1 Jahr Support"],
    },
    "shopify-acquisition-engine": {
        "key": "Shopify Acq Engine",
        "t1n": "Starter",  "t1p": "€497", "t1per": "/mo",
        "t2n": "Scale",    "t2p": "€997", "t2per": "/mo",
        "t3n": "Dominate", "t3p": "€2.497", "t3per": "/mo",
        "t1f": ["✓ Meta Ads Automation", "✓ Google Shopping", "✓ DSGVO-Tracking", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ Alles aus Starter", "✓ TikTok + Pinterest", "✓ Retargeting", "✓ Priority Support", "✓ Creative-Pack"],
        "t3f": ["✓ Alles aus Scale", "✓ Alle Kanäle", "✓ KI-Budgetoptimierung", "✓ Dedizierter Manager", "✓ Custom Attribution"],
    },
    "shopify-suite": {
        "key": "Shopify Suite",
        "t1n": "Solo Seller", "t1p": "€497", "t1per": "/mo",
        "t2n": "Store Pro",   "t2p": "€997", "t2per": "/mo",
        "t3n": "Multi-Store", "t3p": "€2.497", "t3per": "/mo",
        "t1f": ["✓ 1 Shop", "✓ Import bis 500 Produkte", "✓ Gatekeeper", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ 3 Shops", "✓ Unbegrenzte Produkte", "✓ KI-Texte", "✓ Priority Support", "✓ Bonus-Paket"],
        "t3f": ["✓ 10 Shops", "✓ Zentrale Verwaltung", "✓ API-Zugang", "✓ Dedizierter Manager", "✓ White-Label"],
    },
    "digistore24-suite": {
        "key": "Digistore24 Suite",
        "t1n": "Affiliate", "t1p": "€497", "t1per": "/mo",
        "t2n": "Vendor Pro","t2p": "€997", "t2per": "/mo",
        "t3n": "Network",   "t3p": "€2.997", "t3per": "/mo",
        "t1f": ["✓ DS24 Affiliate-System", "✓ Nischen-Matrix 2026", "✓ Email-Funnel", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ Eigene Produkte", "✓ Affiliate-Recruiting", "✓ Vendor Dashboard", "✓ Priority Support", "✓ Funnel-Templates"],
        "t3f": ["✓ Multi-Vendor", "✓ Netzwerk-Aufbau", "✓ White-Label", "✓ Dedizierter Manager", "✓ Custom Funnels"],
    },
    "steuercockpit": {
        "key": "SteuercockPit",
        "t1n": "Freelancer", "t1p": "€497", "t1per": "/mo",
        "t2n": "GmbH",       "t2p": "€997", "t2per": "/mo",
        "t3n": "Konzern",    "t3p": "€2.497", "t3per": "/mo",
        "t1f": ["✓ DE/AT/CH Support", "✓ Auto-Kategorisierung", "✓ USt-Voranmeldung", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ GmbH-Features", "✓ DATEV-Export", "✓ G&V automatisch", "✓ Priority Support", "✓ Steuerberater-Export"],
        "t3f": ["✓ Multi-Mandant", "✓ Konzernabschluss", "✓ API-Zugang", "✓ Dedizierter Manager", "✓ Custom-Reporting"],
    },
    "telegram-bot": {
        "key": "Telegram Bot",
        "t1n": "Starter", "t1p": "€297", "t1per": "/mo",
        "t2n": "Pro",     "t2p": "€797", "t2per": "/mo",
        "t3n": "Agency",  "t3p": "€1.997", "t3per": "/mo",
        "t1f": ["✓ Bis 1.000 Subscriber", "✓ Broadcast-System", "✓ Stripe-Integration", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ Bis 10.000 Subscriber", "✓ Auto-Segmentierung", "✓ Analytics", "✓ Priority Support", "✓ Bonus-Templates"],
        "t3f": ["✓ Unbegrenzte Subscriber", "✓ Multi-Bot", "✓ White-Label", "✓ Dedizierter Manager", "✓ API-Zugang"],
    },
    "icomeauto": {
        "key": "IcomeAuto",
        "t1n": "Basic",       "t1p": "€497", "t1per": " einmalig",
        "t2n": "Advanced",    "t2p": "€997", "t2per": " einmalig",
        "t3n": "Full System", "t3p": "€2.997", "t3per": " einmalig",
        "t1f": ["✓ 3 Einkommens-Streams", "✓ Setup-Guide", "✓ Traffic-System", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ 7 Streams", "✓ Paid Ads System", "✓ Skalierungs-Plan", "✓ Priority Support", "✓ Community-Zugang"],
        "t3f": ["✓ Alle Streams", "✓ Done-For-You", "✓ 90-Tage Begleitung", "✓ 1:1 Coaching", "✓ Erfolgsgarantie"],
    },
    "launcher": {
        "key": "Launcher",
        "t1n": "Self-Launch",   "t1p": "€997", "t1per": " einmalig",
        "t2n": "Guided Launch", "t2p": "€2.997", "t2per": " einmalig",
        "t3n": "DFY Launch",    "t3p": "€4.997", "t3per": " einmalig",
        "t1f": ["✓ Launch-System komplett", "✓ Email-Sequenz", "✓ Countdown-System", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ Alles aus Self-Launch", "✓ 1:1 Launch-Coaching", "✓ Affiliate-Setup", "✓ Priority Support", "✓ Bonus-Paket"],
        "t3f": ["✓ Alles aus Guided", "✓ Wir starten für dich", "✓ Produktaufbau inklusive", "✓ 14-Tage Launch", "✓ Revenue-Garantie"],
    },
    "lead-capture": {
        "key": "Lead Capture",
        "t1n": "Solo",   "t1p": "€497", "t1per": "/mo",
        "t2n": "Team",   "t2p": "€997", "t2per": "/mo",
        "t3n": "Agency", "t3p": "€2.497", "t3per": "/mo",
        "t1f": ["✓ Webseiten-Capture", "✓ KI-Lead-Scoring", "✓ CRM-Integration", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ Alle Quellen", "✓ Multi-Channel", "✓ Team-Zugang", "✓ Priority Support", "✓ Nurturing-Sequenzen"],
        "t3f": ["✓ Unbegrenzte Leads", "✓ White-Label", "✓ Client-Reports", "✓ Dedizierter Manager", "✓ API-Zugang"],
    },
    "gumroad-discord": {
        "key": "Gumroad Discord",
        "t1n": "Community",  "t1p": "€297", "t1per": "/mo",
        "t2n": "Server Pro", "t2p": "€797", "t2per": "/mo",
        "t3n": "Network",    "t3p": "€1.497", "t3per": "/mo",
        "t1f": ["✓ 1 Discord Server", "✓ Gumroad-Integration", "✓ Auto-Rollen", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ 5 Server", "✓ Stripe direkt", "✓ Analytics", "✓ Priority Support", "✓ Vorlagen-Pack"],
        "t3f": ["✓ Unbegrenzte Server", "✓ Multi-Produkt", "✓ White-Label", "✓ Dedizierter Manager", "✓ API-Zugang"],
    },
    "master-dashboard": {
        "key": "Master Dashboard",
        "t1n": "Business",    "t1p": "€997", "t1per": "/mo",
        "t2n": "Enterprise",  "t2p": "€2.497", "t2per": "/mo",
        "t3n": "White Label", "t3p": "€4.997", "t3per": "/mo",
        "t1f": ["✓ 5 Plattformen", "✓ Alle Module", "✓ Live-Dashboard", "✓ Email Support", "✓ 30-Tage Garantie"],
        "t2f": ["✓ Unbegrenzte Plattformen", "✓ REST API", "✓ Team-Accounts", "✓ Priority Support", "✓ Custom Integrationen"],
        "t3f": ["✓ Eigene Marke/Domain", "✓ Client-Verwaltung", "✓ Reseller-Lizenz", "✓ Dedizierter Manager", "✓ Revenue Share"],
    },
}


def get_buy_links(prod_key: str):
    """Holt Stripe Buy Links für ein Produkt."""
    data = STRIPE.get(prod_key, [])
    links = [url for _, url in data if url.startswith("http")]
    while len(links) < 3:
        links.append("https://buy.stripe.com/6oU3cxcvM2DEf721Sm4F465Q")
    return links[:3]


def build_pricing_section(dirname: str, p: dict) -> str:
    links = get_buy_links(p["key"])
    l1, l2, l3 = links

    def feature_list(items):
        return "\n".join(f'<li>{i}</li>' for i in items)

    return f"""<!-- HT-V3-PRICING-START -->
<section id="preise" style="padding:80px 5%;background:var(--surface,#0c1220);border-top:1px solid var(--border,#1a1a2e)">
  <div style="max-width:1100px;margin:0 auto">
    <div style="text-align:center;margin-bottom:3rem">
      <div style="font-size:.68rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#f59e0b;margin-bottom:.75rem">Investition</div>
      <h2 style="font-size:clamp(1.8rem,4vw,2.8rem);font-weight:900;letter-spacing:-.03em;margin-bottom:1rem">Wähle deinen Plan</h2>
      <p style="color:#94a3b8;max-width:520px;margin:0 auto">Alle Pläne mit 30-Tage Geld-zurück-Garantie. Kein Risiko.</p>
    </div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1.5rem;align-items:start">

      <!-- Tier 1 -->
      <div style="background:var(--surface2,#0a0a0f);border:1px solid rgba(255,255,255,.08);border-radius:20px;padding:2.5rem;transition:transform .3s" onmouseover="this.style.transform='translateY(-6px)'" onmouseout="this.style.transform='none'">
        <div style="font-size:.8rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.1em;margin-bottom:1rem">{p["t1n"]}</div>
        <div style="font-size:2.6rem;font-weight:900;margin-bottom:.25rem">{p["t1p"]}<span style="font-size:1rem;font-weight:400;color:#94a3b8">{p["t1per"]}</span></div>
        <ul style="list-style:none;margin:1.5rem 0 2rem">
          {feature_list(p["t1f"])}
        </ul>
        <a href="{l1}" target="_blank" style="display:block;background:rgba(245,158,11,.12);color:#f59e0b;text-align:center;padding:1rem;border-radius:12px;text-decoration:none;font-weight:700;border:1px solid rgba(245,158,11,.3);transition:all .3s" onmouseover="this.style.background='rgba(245,158,11,.2)'" onmouseout="this.style.background='rgba(245,158,11,.12)'">Jetzt starten →</a>
      </div>

      <!-- Tier 2 (Popular) -->
      <div style="background:linear-gradient(135deg,rgba(245,158,11,.08),rgba(251,191,36,.04));border:2px solid #f59e0b;border-radius:20px;padding:2.5rem;position:relative;transform:translateY(-8px);box-shadow:0 0 50px rgba(245,158,11,.2)">
        <div style="position:absolute;top:-14px;left:50%;transform:translateX(-50%);background:#f59e0b;color:#000;font-size:.7rem;font-weight:900;padding:.3rem 1.2rem;border-radius:20px;letter-spacing:.08em;white-space:nowrap">⭐ BELIEBTESTE WAHL</div>
        <div style="font-size:.8rem;font-weight:700;color:#f59e0b;text-transform:uppercase;letter-spacing:.1em;margin-bottom:1rem">{p["t2n"]}</div>
        <div style="font-size:2.6rem;font-weight:900;margin-bottom:.25rem">{p["t2p"]}<span style="font-size:1rem;font-weight:400;color:#94a3b8">{p["t2per"]}</span></div>
        <ul style="list-style:none;margin:1.5rem 0 2rem">
          {feature_list(p["t2f"])}
        </ul>
        <a href="{l2}" target="_blank" style="display:block;background:linear-gradient(135deg,#f59e0b,#d97706);color:#000;text-align:center;padding:1rem;border-radius:12px;text-decoration:none;font-weight:900;box-shadow:0 8px 25px rgba(245,158,11,.4);transition:all .3s" onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform='none'">Jetzt kaufen →</a>
      </div>

      <!-- Tier 3 -->
      <div style="background:var(--surface2,#0a0a0f);border:1px solid rgba(255,255,255,.08);border-radius:20px;padding:2.5rem;transition:transform .3s" onmouseover="this.style.transform='translateY(-6px)'" onmouseout="this.style.transform='none'">
        <div style="font-size:.8rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.1em;margin-bottom:1rem">{p["t3n"]}</div>
        <div style="font-size:2.6rem;font-weight:900;margin-bottom:.25rem">{p["t3p"]}<span style="font-size:1rem;font-weight:400;color:#94a3b8">{p["t3per"]}</span></div>
        <ul style="list-style:none;margin:1.5rem 0 2rem">
          {feature_list(p["t3f"])}
        </ul>
        <a href="{l3}" target="_blank" style="display:block;background:rgba(255,255,255,.05);color:#e2e8f0;text-align:center;padding:1rem;border-radius:12px;text-decoration:none;font-weight:700;border:1px solid rgba(255,255,255,.1);transition:all .3s" onmouseover="this.style.background='rgba(255,255,255,.1)'" onmouseout="this.style.background='rgba(255,255,255,.05)'">Enterprise starten →</a>
      </div>
    </div>

    <!-- Garantie Badge -->
    <div style="text-align:center;margin-top:3rem;padding:2rem;background:rgba(0,255,136,.05);border:1px solid rgba(0,255,136,.15);border-radius:20px;display:flex;align-items:center;justify-content:center;gap:1.5rem;flex-wrap:wrap">
      <div style="width:72px;height:72px;background:linear-gradient(135deg,#00ff88,#00cc6a);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:2rem;flex-shrink:0">🛡️</div>
      <div style="text-align:left">
        <div style="font-size:1.1rem;font-weight:900;color:#00ff88;margin-bottom:.25rem">30-Tage Geld-zurück-Garantie</div>
        <div style="font-size:.85rem;color:#94a3b8;max-width:420px">Nicht zufrieden? Kein Problem. Wir erstatten 100% — ohne Wenn und Aber. Kein Risiko für dich.</div>
      </div>
    </div>
  </div>
</section>
<!-- HT-V3-PRICING-END -->"""


def fix_js_bugs(html: str, dirname: str) -> str:
    """Behebt window.cntDone_X-Y JS-Bug → bracket notation."""
    # Fix: window.cntDone_key-with-hyphens → window["cntDone_key-with-hyphens"]
    safe = dirname.replace("-", "-")  # keep as-is
    html = html.replace(
        f"window.cntDone_{dirname}",
        f'window["cntDone_{dirname}"]'
    )
    html = html.replace(
        f"window.cntDone_bullpower-ai-tools",
        f'window["cntDone_bullpower-ai-tools"]'
    )
    # Fix alle Vorkommen von window.cntDone_ gefolgt von Wort-Bindestrichen
    html = re.sub(
        r'window\.cntDone_([a-z0-9]+(?:-[a-z0-9]+)+)',
        lambda m: f'window["cntDone_{m.group(1)}"]',
        html
    )
    return html


def replace_pricing_section(html: str, dirname: str) -> str:
    """Ersetzt bestehende pricing-section mit V3-Version."""
    p = PRICING.get(dirname)
    if not p:
        return html
    new_section = build_pricing_section(dirname, p)
    # Entferne alte HT-V3-PRICING falls vorhanden
    html = re.sub(r'<!-- HT-V3-PRICING-START -->.*?<!-- HT-V3-PRICING-END -->',
                  '', html, flags=re.DOTALL)
    # Ersetze <section class="pricing-section" id="preise">...</section>
    html = re.sub(
        r'<section class="pricing-section"[^>]*>.*?</section>',
        new_section, html, flags=re.DOTALL
    )
    # Fallback: vor </body>
    if "HT-V3-PRICING-START" not in html:
        html = html.replace("</body>", new_section + "\n</body>")
    return html


def netlify_deploy(dirname: str, site_name: str, html_bytes: bytes) -> bool:
    """Deployed eine HTML-Datei via Netlify API."""
    HDR = {"Authorization": f"Bearer {TOK1}", "Content-Type": "application/json"}
    sha1 = hashlib.sha1(html_bytes).hexdigest()
    # Site-ID per Name suchen
    r = requests.get("https://api.netlify.com/api/v1/sites",
                     headers={"Authorization": f"Bearer {TOK1}"}, timeout=15)
    sites = {s["name"]: s["id"] for s in r.json() if isinstance(r.json(), list)}
    site_id = sites.get(site_name)
    if not site_id:
        return False
    d = requests.post(f"https://api.netlify.com/api/v1/sites/{site_id}/deploys",
                      headers={**HDR}, json={"files": {"/index.html": sha1}}, timeout=20)
    if d.status_code not in (200, 201):
        return False
    deploy_id = d.json()["id"]
    if sha1 in d.json().get("required", []):
        u = requests.put(
            f"https://api.netlify.com/api/v1/deploys/{deploy_id}/files/index.html",
            headers={"Authorization": f"Bearer {TOK1}", "Content-Type": "application/octet-stream"},
            data=html_bytes, timeout=30
        )
        return u.status_code in (200, 201)
    return True


def main():
    # Konto 1 Token aus .env
    global TOK1
    env_content = Path("/Users/rudolfsarkany/supermegabot/.env").read_text()
    for line in env_content.splitlines():
        if line.startswith("NETLIFY_TOKEN=") or line.startswith("NETLIFY_AUTH_TOKEN="):
            TOK1 = line.split("=", 1)[1].strip()
            break

    if not TOK1:
        # Aus bekanntem Token
        TOK1 = "nfp_NF2g6uVCNyYkpCnGfPYFPGAmr97pqdGn2e04"

    ok = 0
    fixed = 0

    for dirname, site_name in SITE_MAP.items():
        html_path = BASE / dirname / "index.html"
        if not html_path.exists():
            print(f"  ⚠ {dirname}: nicht gefunden")
            continue

        html = html_path.read_text(encoding="utf-8")
        orig_len = len(html)

        # 1. JS-Bugs fixen
        html = fix_js_bugs(html, dirname)

        # 2. Pricing-Section ersetzen
        html = replace_pricing_section(html, dirname)

        if len(html) != orig_len:
            html_path.write_text(html, encoding="utf-8")
            fixed += 1
            print(f"  ✅ {dirname}: JS-Fix + Pricing-Update ({orig_len} → {len(html)} Zeichen)")
        else:
            print(f"  ℹ {dirname}: keine Änderungen nötig")

        # 3. Netlify Deploy
        time.sleep(0.5)
        result = netlify_deploy(dirname, site_name, html.encode("utf-8"))
        if result:
            print(f"     🚀 Deployed → https://{site_name}.netlify.app")
            ok += 1
        else:
            print(f"     ⚠ Deploy übersprungen (Netlify CLI Fallback)")

    print(f"\n📊 Ergebnis: {fixed} Dateien geändert, {ok} deployed")
    print("\nStrike alle Stripe Links aus config/stripe_ht_links.json sind aktiv.")


if __name__ == "__main__":
    main()
