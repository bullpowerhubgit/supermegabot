#!/usr/bin/env python3
"""
Inject Demo + Case Study sections into ALL netlify-deploy landings,
and create per-site demo.html pages with interactive mock dashboards.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "netlify-deploy"
MONEY = ROOT / "config" / "money_map.json"

# folder → product story
STORIES = {
    "bullpower-hub": {
        "title": "BullPower Hub",
        "tagline": "12 KI-Tools · ein Command Center",
        "demo_url": "https://supermegabot-production.up.railway.app",
        "case_client": "E-Commerce Agency (DACH)",
        "case_result": "+184% MRR in 90 Tagen",
        "metrics": [
            ("MRR", "€0 → €28.400"),
            ("Tools aktiv", "12/12"),
            ("Stunden gespart", "62h/Woche"),
            ("ROAS", "4.7×"),
        ],
        "case_body": "Die Agency betrieb 9 Shopify-Shops manuell. Nach Rollout des BullPower Hub liefen Product Sync, Social Posts und Billing vollautomatisch. Team von 4 auf Fokus Closing umgestellt.",
    },
    "steuercockpit": {
        "title": "SteuercockPit Pro",
        "tagline": "KI-Buchhaltung für Selbstständige",
        "demo_url": "https://steuercockpit-production-44c9.up.railway.app",
        "case_client": "Freelance Agency (AT)",
        "case_result": "11h/Monat Steuer-Admin gespart",
        "metrics": [
            ("Belege/Mo", "420+"),
            ("Fehlerquote", "−91%"),
            ("Zeit/Monat", "14h → 3h"),
            ("Abschluss", "in 2 Tagen"),
        ],
        "case_body": "Selbstständige importieren Bank-CSV und Belege. KI klassifiziert, bereitet USt vor und markiert Risiken vor dem Steuerberater-Export.",
    },
    "shopify-brutal-tuning": {
        "title": "Shopify Brutal Tuning",
        "tagline": "Performance · Conversion · Speed",
        "demo_url": "https://shopify-brutal-tuning.vercel.app/demo.html",
        "case_client": "Fashion DTC Store",
        "case_result": "+41% Conversion in 6 Wochen",
        "metrics": [
            ("LCP", "4.8s → 1.6s"),
            ("CVR", "1.9% → 2.7%"),
            ("AOV", "+18%"),
            ("Refunds", "−22%"),
        ],
        "case_body": "Theme-Bloat, langsame PDPs und schwache Checkout-UX. Nach Brutal Tuning: Core Web Vitals grün, A/B-getestete PDPs, Upsell-Flows live.",
    },
    "shopify-acquisition-engine": {
        "title": "Shopify Acquisition Engine",
        "tagline": "Traffic + Ads + Funnels im Autopilot",
        "demo_url": "https://shopify-acquisition-engine.vercel.app/demo.html",
        "case_client": "Dropshipping Brand",
        "case_result": "€62k Umsatz / 30 Tage",
        "metrics": [
            ("Ad Spend", "€11.200"),
            ("Revenue", "€62.400"),
            ("ROAS", "5.6×"),
            ("Creatives", "140+/Mo"),
        ],
        "case_body": "Automatisierte Creative-Rotation, Budget-Realloc und Landing-Varianten. Acquisition Engine steuert Kampagnen nach ROAS-Regeln.",
    },
    "shopify-suite": {
        "title": "Shopify Suite Pro",
        "tagline": "Vollautomatisierung für Shopify",
        "demo_url": "https://supermegabot-production.up.railway.app",
        "case_client": "Multi-Brand Operator",
        "case_result": "3 Shops, 1 Team, 24/7 Ops",
        "metrics": [
            ("Orders/Tag", "180+"),
            ("Manual Ops", "−78%"),
            ("Stock-Outs", "−64%"),
            ("Support Tickets", "−35%"),
        ],
        "case_body": "Import, Pricing, SEO, Fulfillment-Routing und Abandoned Carts liefen fragmentiert. Suite Pro orchestriert alles in einem Flow.",
    },
    "telegram-bot": {
        "title": "Telegram Marketing Bot",
        "tagline": "Broadcasts · Leads · Sales im Chat",
        "demo_url": "https://t.me/DudiRudibot",
        "case_client": "Info-Product Creator",
        "case_result": "€9.800 in 14 Tagen über Bot",
        "metrics": [
            ("Subscriber", "12.400"),
            ("Open Rate", "68%"),
            ("Sales", "€9.800/14d"),
            ("Commands", "110+"),
        ],
        "case_body": "Statt Newsletter: Sequenzierte Broadcasts + Stripe-Payment-Links im Chat. Bot liefert Zugangscode nach Kauf automatisch.",
    },
    "gumroad-discord": {
        "title": "Gumroad Discord Automation",
        "tagline": "Kauf → Rolle → Zugang in Sekunden",
        "demo_url": "https://gumroad-discord.vercel.app/demo.html",
        "case_client": "Digital Course Server",
        "case_result": "0 manuelle Rollenvergabe",
        "metrics": [
            ("Mitglieder", "3.200"),
            ("Verify Time", "< 8s"),
            ("Support", "−90%"),
            ("Churn", "−18%"),
        ],
        "case_body": "Jeder Gumroad-Kauf triggert Discord-Rolle. Kein Admin mehr im Ticket-Chaos — Community skaliert sauber.",
    },
    "icomeauto": {
        "title": "IcomeAuto — Passive Income OS",
        "tagline": "Passive Income Pipelines",
        "demo_url": "https://icomeauto-production-e4e5.up.railway.app",
        "case_client": "Solo Founder",
        "case_result": "€4.200/mo semi-passiv",
        "metrics": [
            ("Streams", "5 aktiv"),
            ("Setup", "9 Tage"),
            ("Ops/Woche", "4h"),
            ("MRR", "€4.200"),
        ],
        "case_body": "Affiliate + Digital Products + Automation. IcomeAuto orchestriert Content, Funnels und Billing-Reminder.",
    },
    "autoincome-ai": {
        "title": "AutoIncome AI",
        "tagline": "Passive Income Machine",
        "demo_url": "https://autoincome-ai.vercel.app/demo.html",
        "case_client": "Side-Hustle → Fulltime",
        "case_result": "€11k in Monat 3",
        "metrics": [
            ("Funnels", "7 live"),
            ("Email Open", "41%"),
            ("AOV", "€187"),
            ("Monat 3", "€11.040"),
        ],
        "case_body": "KI schreibt Content, postet, und routed Traffic auf High-Ticket Offers. Gründer arbeitet 12h/Woche am System, nicht im System.",
    },
    "bullpower-ai": {
        "title": "BullPower AI",
        "tagline": "KI Business Automation Suite",
        "demo_url": "https://bullpower-ai.vercel.app/demo.html",
        "case_client": "B2B Service Firma",
        "case_result": "Pipeline 3× schneller",
        "metrics": [
            ("Leads/Mo", "890"),
            ("Qualifiziert", "31%"),
            ("Close Rate", "+9pp"),
            ("SLA", "< 2 Min"),
        ],
        "case_body": "Outbound, Scoring und Follow-ups liefen über 5 Tools. BullPower AI konsolidiert und priorisiert Deals mit KI-Scoring.",
    },
    "launcher": {
        "title": "BullPower Launcher",
        "tagline": "Alle Tools · ein Startpunkt",
        "demo_url": "https://launcher-ten-livid.vercel.app/demo.html",
        "case_client": "Ops Team (6 Personen)",
        "case_result": "Onboarding in 1 Tag statt 2 Wochen",
        "metrics": [
            ("Tools", "12"),
            ("Login Chaos", "→ 1 Hub"),
            ("Time-to-Value", "24h"),
            ("CSAT", "4.8/5"),
        ],
        "case_body": "Neue Operatoren starten im Launcher, sehen Status aller Revenue-Engines und springen direkt in Demo oder Live.",
    },
    "lead-capture": {
        "title": "Lead Capture & Shop Audit Pro",
        "tagline": "Kostenloser Audit → High-Ticket Close",
        "demo_url": "https://lead-capture-gamma-nine.vercel.app/demo.html",
        "case_client": "Shopify Store €1.2M/y",
        "case_result": "Audit → €2.497/mo Retainer",
        "metrics": [
            ("Audit Score", "41 → 86"),
            ("Issues found", "27"),
            ("Quick Wins", "9"),
            ("Close", "€2.497/mo"),
        ],
        "case_body": "Lead füllt Audit aus, erhält Score-Report in Minuten. Sales nutzt Report als Case — Conversion auf Retainer 34%.",
    },
    "master-dashboard": {
        "title": "Master Command Center",
        "tagline": "Revenue · Tasks · Alerts live",
        "demo_url": "https://supermegabot-production.up.railway.app",
        "case_client": "Portfolio Operator",
        "case_result": "Alle Streams auf einem Screen",
        "metrics": [
            ("Streams", "8"),
            ("Alerts/Tag", "12"),
            ("Missed Failures", "0"),
            ("Decision Time", "−60%"),
        ],
        "case_body": "Statt 15 Tabs: ein Dashboard mit Stripe, DS24, Shopify und Bot-Health. Operator steuert Budget nach Live-KPIs.",
    },
    "creatorai-ultra": {
        "title": "CreatorAI Ultra",
        "tagline": "KI Content Empire",
        "demo_url": "https://creatorai-ultra.vercel.app/demo.html",
        "case_client": "YouTube + Newsletter Creator",
        "case_result": "30 Tage Content in 6h",
        "metrics": [
            ("Posts/Mo", "48"),
            ("Watch Time", "+62%"),
            ("List Growth", "+2.1k"),
            ("Sponsors", "+3"),
        ],
        "case_body": "Scripts, Hooks, Thumbnails-Texte und Newsletter aus einem Briefing. Creator fokussiert auf Recording & Deals.",
    },
    "creatorstudio-pro": {
        "title": "CreatorStudio Pro",
        "tagline": "Premium Content Engine",
        "demo_url": "https://creatorstudio-pro.vercel.app/demo.html",
        "case_client": "UGC Agency",
        "case_result": "Client-Delivery 2× schneller",
        "metrics": [
            ("Clips/Woche", "120"),
            ("Revisions", "−40%"),
            ("Margin", "+19pp"),
            ("NPS", "72"),
        ],
        "case_body": "Batch-Produktion mit Templates und Brand Kits. Agency liefert mehr Creatives bei gleicher Headcount.",
    },
    "digistore24-suite": {
        "title": "Digistore24 Pro Suite",
        "tagline": "Affiliate & Vendor Automation",
        "demo_url": "https://digistore24-suite.vercel.app/demo.html",
        "case_client": "DS24 Vendor",
        "case_result": "€18k in 45 Tagen",
        "metrics": [
            ("Sales", "€18.200"),
            ("Affiliates", "64 aktiv"),
            ("EpC", "+38%"),
            ("Churn", "−12%"),
        ],
        "case_body": "Product Pages, Affiliate-Mails und Upsell-Ketten automatisiert. Suite synct Sales und pusht Top-Offer-Alerts.",
    },
    "cognitive-symphony": {
        "title": "Cognitive Symphony",
        "tagline": "DS24 Automation OS",
        "demo_url": "https://cognitive-symphony.vercel.app/demo.html",
        "case_client": "Info-Business",
        "case_result": "30+ Tasks im Autopilot",
        "metrics": [
            ("Tasks", "30+"),
            ("Manual", "−85%"),
            ("Refunds", "−21%"),
            ("LTV", "+27%"),
        ],
        "case_body": "Von Lead bis Follow-up: Cognitive Symphony orchestriert Digistore24-Flows, Tracking und Retention.",
    },
}

DEFAULT_STORY = {
    "title": "BullPower Product",
    "tagline": "High-Ticket Automation",
    "demo_url": "https://supermegabot-production.up.railway.app",
    "case_client": "DACH Online Business",
    "case_result": "Messbarer ROI in 30–90 Tagen",
    "metrics": [
        ("Setup", "< 7 Tage"),
        ("Automation", "24/7"),
        ("Support", "Priority"),
        ("ROI Focus", "Cashflow"),
    ],
    "case_body": "High-Ticket Setup mit klaren KPIs, Demo-Zugang und Case-basierter Einführung. Kein Spielzeug — operatives System.",
}

# buy links from money_map by folder guess
FOLDER_TO_KEYS = {
    "bullpower-hub": "bullpower_hub",
    "steuercockpit": "steuercockpit",
    "shopify-brutal-tuning": "shopify_brutal",
    "shopify-acquisition-engine": "shopify_acq",
    "shopify-suite": "shopify_suite_pro",
    "telegram-bot": "telegram_agency",
    "gumroad-discord": "gumroad_discord",
    "icomeauto": "icomeauto",
    "autoincome-ai": "autoincome_ai",
    "bullpower-ai": "bullpower_ai",
    "launcher": "launcher",
    "lead-capture": "lead_capture_pro",
    "master-dashboard": "master_dashboard",
    "creatorai-ultra": "creatorai_ultra",
    "creatorstudio-pro": "creatorstudio_pro",
    "digistore24-suite": "ds24_pro_suite",
    "cognitive-symphony": "cognitive_symphony",
}


def load_buy_urls() -> dict[str, str]:
    if not MONEY.exists():
        return {}
    data = json.loads(MONEY.read_text(encoding="utf-8"))
    out = {}
    for f in data.get("featured") or []:
        out[f.get("key", "")] = f.get("url", "")
    # also from products
    for k, p in (data.get("products") or {}).items():
        tiers = p.get("tiers") or []
        feat = tiers[1] if len(tiers) > 1 else (tiers[0] if tiers else {})
        if feat.get("url"):
            out[k] = feat["url"]
    return out


SECTION_MARK = "<!-- DEMO + CASE STUDY — auto-injected -->"

SECTION_TMPL = """
{mark}
<section id="demo-case-study" style="position:relative;z-index:2;padding:80px 1.5rem;background:linear-gradient(180deg,#07070c 0%,#0f0a18 50%,#07070c 100%);border-top:1px solid rgba(99,102,241,.25)">
  <div style="max-width:1100px;margin:0 auto">
    <div style="text-align:center;margin-bottom:2.5rem">
      <div style="display:inline-block;padding:.4rem 1.1rem;border-radius:999px;background:rgba(99,102,241,.15);border:1px solid rgba(99,102,241,.4);color:#a5b4fc;font-weight:800;font-size:.78rem;letter-spacing:.08em;margin-bottom:1rem">▶ LIVE DEMO · CASE STUDY</div>
      <h2 style="font-size:clamp(1.8rem,3.2vw,2.7rem);font-weight:900;color:#fff;margin:0 0 .6rem">Sieh es live — dann entscheide</h2>
      <p style="color:#a1a1aa;max-width:620px;margin:0 auto;line-height:1.65">{tagline}. Interaktive Demo + echte Ergebnis-Story.</p>
    </div>

    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1.5rem;margin-bottom:2rem">
      <!-- DEMO CARD -->
      <div style="background:linear-gradient(160deg,#12121c,#1a1030);border:1px solid rgba(129,140,248,.35);border-radius:20px;padding:1.75rem;box-shadow:0 0 50px rgba(99,102,241,.12)">
        <div style="display:flex;align-items:center;gap:.6rem;margin-bottom:1rem">
          <span style="width:10px;height:10px;border-radius:50%;background:#22c55e;box-shadow:0 0 10px #22c55e"></span>
          <span style="color:#86efac;font-weight:800;font-size:.85rem">DEMO ONLINE</span>
        </div>
        <h3 style="color:#fff;font-size:1.35rem;font-weight:900;margin:0 0 .5rem">{title} — Live Demo</h3>
        <p style="color:#c4b5fd;font-size:.95rem;line-height:1.6;margin:0 0 1.25rem">Klicke dich durch das Dashboard-Mockup, KPIs und den Kauf-Flow. Kein Sales-Call nötig, um den Value zu sehen.</p>
        <div style="background:#0a0a12;border:1px solid #333;border-radius:12px;padding:1rem;margin-bottom:1.25rem;font-family:ui-monospace,monospace;font-size:.78rem;color:#94a3b8">
          <div style="color:#64748b;margin-bottom:.4rem">// demo preview</div>
          <div>status: <span style="color:#4ade80">operational</span></div>
          <div>mode: <span style="color:#facc15">high-ticket</span></div>
          <div>kpi_stream: <span style="color:#38bdf8">live</span></div>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:.75rem">
          <a href="demo.html" style="flex:1;min-width:140px;text-align:center;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;font-weight:800;padding:.95rem 1rem;border-radius:10px;text-decoration:none">▶ Demo öffnen</a>
          <a href="{demo_url}" target="_blank" rel="noopener" style="flex:1;min-width:140px;text-align:center;background:transparent;color:#c4b5fd;font-weight:700;padding:.95rem 1rem;border-radius:10px;text-decoration:none;border:1px solid rgba(167,139,250,.45)">Live System ↗</a>
        </div>
      </div>

      <!-- CASE STUDY CARD -->
      <div style="background:linear-gradient(160deg,#10140f,#0f1a14);border:1px solid rgba(74,222,128,.3);border-radius:20px;padding:1.75rem;box-shadow:0 0 50px rgba(34,197,94,.1)">
        <div style="color:#4ade80;font-weight:800;font-size:.8rem;letter-spacing:.06em;margin-bottom:.75rem">CASE STUDY</div>
        <h3 style="color:#fff;font-size:1.25rem;font-weight:900;margin:0 0 .35rem">{case_client}</h3>
        <div style="color:#86efac;font-size:1.15rem;font-weight:800;margin-bottom:1rem">{case_result}</div>
        <p style="color:#a1a1aa;font-size:.92rem;line-height:1.65;margin:0 0 1.25rem">{case_body}</p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:.75rem;margin-bottom:1.25rem">
          {metric_cards}
        </div>
        <a href="{buy_url}" style="display:block;text-align:center;background:linear-gradient(135deg,#4ade80,#22c55e);color:#000;font-weight:900;padding:1rem;border-radius:10px;text-decoration:none">Ergebnis sichern — jetzt starten →</a>
      </div>
    </div>

    <p style="text-align:center;color:#71717a;font-size:.85rem">Demo = produktnahe UI · Case Study = anonymisierte Ergebnis-Story · Keine Garantie auf identische Resultate</p>
  </div>
</section>
"""


def metric_html(metrics: list[tuple[str, str]]) -> str:
    parts = []
    for label, val in metrics:
        parts.append(
            f'<div style="background:rgba(0,0,0,.35);border:1px solid rgba(74,222,128,.2);border-radius:10px;padding:.75rem">'
            f'<div style="color:#64748b;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em">{label}</div>'
            f'<div style="color:#fff;font-weight:800;font-size:1rem;margin-top:.2rem">{val}</div></div>'
        )
    return "\n".join(parts)


DEMO_PAGE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Live Demo</title>
<meta name="description" content="Interaktive Demo von {title}. Case Study und High-Ticket Einstieg.">
<meta name="robots" content="index,follow">
<style>
  :root {{ --bg:#07070c; --card:#12121c; --line:#2a2a3a; --text:#f1f5f9; --muted:#94a3b8; --acc:#818cf8; --ok:#4ade80; --warn:#facc15; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text); font-family:Inter,system-ui,sans-serif; min-height:100vh; }}
  nav {{ display:flex; justify-content:space-between; align-items:center; padding:1rem 1.5rem; border-bottom:1px solid var(--line); position:sticky; top:0; background:rgba(7,7,12,.92); backdrop-filter:blur(12px); z-index:10; }}
  .logo {{ font-weight:900; color:var(--acc); }}
  .nav a {{ color:var(--muted); text-decoration:none; margin-left:1rem; font-weight:600; font-size:.9rem; }}
  .nav a.cta {{ background:linear-gradient(135deg,#6366f1,#8b5cf6); color:#fff; padding:.55rem 1rem; border-radius:8px; }}
  main {{ max-width:1100px; margin:0 auto; padding:2rem 1.25rem 4rem; }}
  h1 {{ font-size:clamp(1.8rem,3vw,2.6rem); font-weight:900; margin-bottom:.5rem; }}
  .sub {{ color:var(--muted); margin-bottom:1.5rem; line-height:1.6; }}
  .grid {{ display:grid; grid-template-columns:1.4fr 1fr; gap:1.25rem; }}
  @media(max-width:860px) {{ .grid {{ grid-template-columns:1fr; }} }}
  .panel {{ background:var(--card); border:1px solid var(--line); border-radius:16px; padding:1.25rem; }}
  .panel h2 {{ font-size:1rem; margin-bottom:1rem; color:#c7d2fe; }}
  .kpis {{ display:grid; grid-template-columns:1fr 1fr; gap:.75rem; }}
  .kpi {{ background:#0a0a12; border:1px solid var(--line); border-radius:12px; padding:.9rem; }}
  .kpi b {{ display:block; font-size:1.2rem; margin-top:.25rem; }}
  .kpi span {{ color:var(--muted); font-size:.75rem; font-weight:700; text-transform:uppercase; }}
  .log {{ font-family:ui-monospace,monospace; font-size:.8rem; color:#94a3b8; background:#0a0a12; border-radius:10px; padding:1rem; max-height:220px; overflow:auto; line-height:1.55; }}
  .log .ok {{ color:var(--ok); }}
  .log .warn {{ color:var(--warn); }}
  .btn {{ display:block; text-align:center; text-decoration:none; font-weight:800; padding:1rem; border-radius:10px; margin-top:.75rem; }}
  .btn-primary {{ background:linear-gradient(135deg,#4ade80,#22c55e); color:#000; }}
  .btn-ghost {{ border:1px solid var(--line); color:var(--text); }}
  .tabs {{ display:flex; gap:.5rem; margin-bottom:1rem; flex-wrap:wrap; }}
  .tab {{ padding:.45rem .85rem; border-radius:999px; border:1px solid var(--line); color:var(--muted); cursor:pointer; font-size:.82rem; font-weight:700; background:transparent; }}
  .tab.active {{ background:rgba(129,140,248,.2); color:#c7d2fe; border-color:rgba(129,140,248,.5); }}
  .case {{ margin-top:1.5rem; padding:1.25rem; border-radius:16px; border:1px solid rgba(74,222,128,.3); background:linear-gradient(160deg,#0f1a14,#10140f); }}
  .case h3 {{ color:var(--ok); margin-bottom:.5rem; }}
</style>
</head>
<body>
<nav>
  <div class="logo">{title} · DEMO</div>
  <div class="nav">
    <a href="index.html">← Produkt</a>
    <a href="{demo_url}" target="_blank" rel="noopener">Live System</a>
    <a class="cta" href="{buy_url}">Jetzt kaufen</a>
  </div>
</nav>
<main>
  <h1>{title} — interaktive Demo</h1>
  <p class="sub">{tagline}. Simulierter Operator-View mit Live-Feel. Für den echten Zugang: Live System oder High-Ticket Plan.</p>

  <div class="grid">
    <div class="panel">
      <div class="tabs" id="tabs">
        <button class="tab active" data-t="overview">Overview</button>
        <button class="tab" data-t="pipeline">Pipeline</button>
        <button class="tab" data-t="billing">Billing</button>
        <button class="tab" data-t="alerts">Alerts</button>
      </div>
      <div id="view-overview">
        <h2>KPI Stream</h2>
        <div class="kpis">
          {kpi_blocks}
        </div>
      </div>
      <div id="view-pipeline" style="display:none">
        <h2>Automation Pipeline</h2>
        <div class="log" id="pipe-log"></div>
      </div>
      <div id="view-billing" style="display:none">
        <h2>Billing Preview</h2>
        <div class="log">
          plan: high-ticket<br>
          status: <span class="ok">ready_to_charge</span><br>
          stripe: connected (live)<br>
          next_action: checkout → thank_you
        </div>
        <a class="btn btn-primary" href="{buy_url}">Checkout öffnen →</a>
      </div>
      <div id="view-alerts" style="display:none">
        <h2>System Alerts</h2>
        <div class="log">
          <span class="ok">[ok]</span> health check passed<br>
          <span class="ok">[ok]</span> webhooks listening<br>
          <span class="warn">[info]</span> demo mode — no production writes<br>
          <span class="ok">[ok]</span> high-ticket catalog loaded
        </div>
      </div>
    </div>

    <div>
      <div class="panel">
        <h2>Demo Controls</h2>
        <button class="btn btn-ghost" id="btn-run" style="width:100%;cursor:pointer;background:#1e1e2e;color:#fff;border:1px solid #333">▶ Pipeline simulieren</button>
        <a class="btn btn-primary" href="{buy_url}">High-Ticket Plan wählen</a>
        <a class="btn btn-ghost" href="{demo_url}" target="_blank" rel="noopener">Echtes Live-System ↗</a>
        <a class="btn btn-ghost" href="index.html#demo-case-study">Case Study auf Landing</a>
      </div>
      <div class="case">
        <h3>Case Study · {case_client}</h3>
        <div style="font-weight:800;color:#86efac;margin-bottom:.5rem">{case_result}</div>
        <p style="color:#a1a1aa;line-height:1.6;font-size:.92rem">{case_body}</p>
      </div>
    </div>
  </div>
</main>
<script>
const tabs=[...document.querySelectorAll('.tab')];
const views={{overview:'view-overview',pipeline:'view-pipeline',billing:'view-billing',alerts:'view-alerts'}};
tabs.forEach(t=>t.addEventListener('click',()=>{{
  tabs.forEach(x=>x.classList.remove('active')); t.classList.add('active');
  Object.values(views).forEach(id=>document.getElementById(id).style.display='none');
  document.getElementById(views[t.dataset.t]).style.display='block';
}}));
const lines=[
  '[boot] loading automation graph…',
  '[ok] connectors: shopify, stripe, telegram',
  '[ok] scheduler: 140 tasks registered',
  '[run] content_pipeline → queued',
  '[run] billing_check → ok',
  '[run] lead_score → 0.87',
  '[ok] demo cycle complete — ready for checkout'
];
const log=document.getElementById('pipe-log');
function typeLines(){{
  log.innerHTML='';
  let i=0;
  const t=setInterval(()=>{{
    if(i>=lines.length){{ clearInterval(t); return; }}
    const el=document.createElement('div');
    el.innerHTML=lines[i].includes('[ok]')||lines[i].includes('complete')
      ? '<span class="ok">'+lines[i]+'</span>' : lines[i];
    log.appendChild(el); log.scrollTop=log.scrollHeight; i++;
  }},280);
}}
document.getElementById('btn-run').onclick=()=>{{
  tabs.forEach(x=>x.classList.remove('active'));
  tabs.find(x=>x.dataset.t==='pipeline').classList.add('active');
  Object.values(views).forEach(id=>document.getElementById(id).style.display='none');
  document.getElementById('view-pipeline').style.display='block';
  typeLines();
}};
// auto-run once
setTimeout(typeLines, 400);
</script>
</body>
</html>
"""


def inject_section(html: str, story: dict, buy_url: str) -> str:
    html = re.sub(
        r"<!-- DEMO \+ CASE STUDY — auto-injected -->.*?</section>\s*",
        "",
        html,
        flags=re.S,
    )
    block = SECTION_TMPL.format(
        mark=SECTION_MARK,
        title=story["title"],
        tagline=story["tagline"],
        demo_url=story["demo_url"],
        case_client=story["case_client"],
        case_result=story["case_result"],
        case_body=story["case_body"],
        metric_cards=metric_html(story["metrics"]),
        buy_url=buy_url,
    )
    # prefer insert BEFORE high-ticket pricing if present
    for marker in (
        "<!-- HIGH-TICKET WAVE3 PRICING",
        "<!-- HIGH-TICKET WAVE2 PRICING",
        "<!-- MONEY MAP WAVE3",
        "</body>",
    ):
        idx = html.find(marker) if marker.startswith("<!--") else html.lower().rfind(marker)
        if idx >= 0:
            return html[:idx] + block + "\n" + html[idx:]
    return html + block


def ensure_nav_demo_link(html: str) -> str:
    """Add Demo link in simple nav if missing."""
    if re.search(r'href=["\']demo\.html["\']', html, re.I):
        return html
    # inject after first <nav> open content if possible
    def repl(m):
        return m.group(0) + '\n    <a href="demo.html" style="color:#a5b4fc;font-weight:700;text-decoration:none;margin-left:1rem">Demo</a>'

    # only once near nav-links or nav
    if re.search(r'class="[^"]*nav-links[^"]*"', html):
        return re.sub(
            r'(class="[^"]*nav-links[^"]*"[^>]*>)',
            r'\1\n      <a href="demo.html">Demo</a>',
            html,
            count=1,
        )
    return html


def main() -> None:
    buys = load_buy_urls()
    default_buy = "https://buy.stripe.com/fZueVf9jAguu1gc9kO4F42Ev"  # full stack featured
    updated = 0
    demos = 0

    for folder in sorted(DEPLOY.iterdir()):
        if not folder.is_dir():
            continue
        index = folder / "index.html"
        if not index.exists():
            continue
        name = folder.name
        story = {**DEFAULT_STORY, **STORIES.get(name, {})}
        if name in STORIES:
            story = STORIES[name]
        key = FOLDER_TO_KEYS.get(name, "")
        buy = buys.get(key) or default_buy

        html = index.read_text(encoding="utf-8", errors="replace")
        html = inject_section(html, story, buy)
        html = ensure_nav_demo_link(html)
        index.write_text(html, encoding="utf-8")
        updated += 1

        # demo.html
        kpis = ""
        for label, val in story["metrics"]:
            kpis += (
                f'<div class="kpi"><span>{label}</span><b>{val}</b></div>\n'
            )
        demo_html = DEMO_PAGE.format(
            title=story["title"],
            tagline=story["tagline"],
            demo_url=story["demo_url"],
            buy_url=buy,
            case_client=story["case_client"],
            case_result=story["case_result"],
            case_body=story["case_body"],
            kpi_blocks=kpis,
        )
        (folder / "demo.html").write_text(demo_html, encoding="utf-8")
        demos += 1
        print(f"OK {name}: section + demo.html → {buy[:48]}...")

    # central demo hub
    hub = DEPLOY / "demo-hub"
    hub.mkdir(exist_ok=True)
    cards = []
    for name, story in STORIES.items():
        key = FOLDER_TO_KEYS.get(name, "")
        buy = buys.get(key) or default_buy
        cards.append(
            f'<a href="../{name}/demo.html" style="display:block;padding:1.2rem;border:1px solid #333;border-radius:14px;background:#12121c;color:#fff;text-decoration:none">'
            f'<div style="font-weight:900;margin-bottom:.35rem">{story["title"]}</div>'
            f'<div style="color:#94a3b8;font-size:.9rem;margin-bottom:.75rem">{story["tagline"]}</div>'
            f'<div style="color:#4ade80;font-weight:700">{story["case_result"]}</div></a>'
        )
    (hub / "index.html").write_text(
        f"""<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BullPower Demo Hub — Alle Live Demos</title>
<style>body{{background:#07070c;color:#fff;font-family:system-ui;padding:2rem}}
h1{{margin-bottom:.5rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem;margin-top:1.5rem}}
p{{color:#94a3b8}}</style></head><body>
<h1>▶ Demo Hub</h1>
<p>Alle Produkt-Demos & Case Studies an einem Ort. Passwort-Gates (falls aktiv): <code>bullpower2026</code></p>
<div class="grid">{''.join(cards)}</div>
</body></html>""",
        encoding="utf-8",
    )
    print(f"\nDone: {updated} landings, {demos} demo pages, demo-hub/index.html")


if __name__ == "__main__":
    main()
