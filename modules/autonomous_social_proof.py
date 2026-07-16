#!/usr/bin/env python3
"""
Autonomous Sales Assets Engine
==============================
Generates, rotates and injects Testimonials + Case Studies + Demos everywhere:

  • config/testimonials.json + case_studies.json + demos.json
  • All netlify-deploy/*/index.html (social proof + demo CTA)
  • All netlify-deploy/*/demo.html (interactive mock dashboards)
  • demo-hub/index.html
  • Public API: /api/testimonials, /api/case-studies, /api/demos, /api/social-proof
  • Scheduler: full cycle every 6h

No external AI required (template engine).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("AutoSocialProof")

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config"
DEPLOY = ROOT / "netlify-deploy"
T_PATH = CFG / "testimonials.json"
C_PATH = CFG / "case_studies.json"
D_PATH = CFG / "demos.json"
MONEY = CFG / "money_map.json"
STATE_PATH = ROOT / "data" / "social_proof_state.json"

# ── Product verticals ────────────────────────────────────────────────────────
VERTICALS = {
    "bullpower-hub": "BullPower Hub",
    "bullpower-ai": "BullPower AI",
    "steuercockpit": "SteuercockPit Pro",
    "shopify-brutal-tuning": "Shopify Brutal Tuning",
    "shopify-acquisition-engine": "Shopify Acquisition Engine",
    "shopify-suite": "Shopify Suite Pro",
    "telegram-bot": "Telegram Marketing Bot",
    "gumroad-discord": "Gumroad Discord Automation",
    "icomeauto": "IcomeAuto",
    "autoincome-ai": "AutoIncome AI",
    "launcher": "BullPower Launcher",
    "lead-capture": "Lead Capture Pro",
    "master-dashboard": "Master Command Center",
    "creatorai-ultra": "CreatorAI Ultra",
    "creatorstudio-pro": "CreatorStudio Pro",
    "digistore24-suite": "Digistore24 Pro Suite",
    "cognitive-symphony": "Cognitive Symphony",
}

FIRST = [
    "Markus", "Anna", "Timo", "Sarah", "Felix", "Lisa", "Klaus", "Julia",
    "Stefan", "Nina", "Thomas", "Laura", "Daniel", "Sophie", "Patrick",
    "Elena", "Michael", "Katharina", "Andreas", "Maria", "Lukas", "Vanessa",
]
LAST = ["M.", "K.", "R.", "L.", "B.", "S.", "H.", "T.", "W.", "P.", "G.", "F."]
CITIES = [
    "Wien", "München", "Berlin", "Hamburg", "Zürich", "Frankfurt", "Graz",
    "Köln", "Stuttgart", "Linz", "Salzburg", "Düsseldorf", "Leipzig", "Basel",
]
ROLES = [
    "Shopify Store-Inhaber", "E-Commerce Managerin", "Agency Owner",
    "Dropshipping Operator", "Digital Creator", "SaaS Founder",
    "Affiliate Marketer", "DTC Brand Lead", "Freelance Consultant",
    "Info-Product Vendor", "Performance Marketer", "Ops Lead",
]

QUOTE_TEMPLATES = [
    "Seit {product} spare ich {hours}h/Woche und mein Umsatz stieg um {pct}%.",
    "In {weeks} Wochen von Chaos auf Autopilot. {product} war der Gamechanger.",
    "ROI nach {weeks} Wochen klar messbar: {result}. Würde sofort wieder buchen.",
    "Wir haben {metric} verdoppelt — ohne Extra-Headcount. Danke {product}.",
    "Setup in Tagen, nicht Monaten. {result} ist real, kein Marketing-Blabla.",
    "Endlich ein System das liefert: {result}. Support top, Automation brutal.",
    "Vorher 5 Tools, jetzt eins: {product}. {pct}% weniger manuelle Arbeit.",
    "High-Ticket hat sich gelohnt. {result} und Team fokussiert nur noch Closing.",
]

CASE_RESULTS = [
    "+{pct}% Conversion in {weeks} Wochen",
    "€{eur}k Zusatzumsatz / Monat",
    "{hours}h/Woche Zeitersparnis",
    "ROAS {roas}× nach Optimierung",
    "MRR €{mrr} in {weeks} Wochen",
    "Refunds −{pct}% · LTV +{ltv}%",
    "Pipeline 3× schneller qualifiziert",
    "Onboarding von 14 Tagen auf 48h",
]

CASE_BODIES = [
    "Ausgangslage: fragmentierte Tools, manuelle Ops, unklare KPIs. Nach Rollout von {product} liefen Kernprozesse automatisiert. Team fokussiert Closing statt Firefighting.",
    "{client_type} skalierte mit {product}. Entscheidend: klare Demo, messbare KPIs und High-Ticket Support. Ergebnis nach {weeks} Wochen: {result}.",
    "Vorher: Excel + Bauchgefühl. Nachher: Live-Dashboards, automatisierte Sequenz und Stripe-Billing. {product} wurde zum Operating System.",
    "Der Engpass war Content/Ops, nicht Traffic. {product} entlastete das Team um {hours}h/Woche — Kapazität ging in Sales.",
]


def _rng(seed: str) -> random.Random:
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16)
    return random.Random(h)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_testimonials(n: int = 80, seed: str | None = None) -> list[dict]:
    """Generate a large rotating pool of social-proof testimonials."""
    base = seed or datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
    out = []
    folders = list(VERTICALS.keys())
    for i in range(n):
        r = _rng(f"{base}:t:{i}")
        folder = folders[i % len(folders)]
        product = VERTICALS[folder]
        first = r.choice(FIRST)
        last = r.choice(LAST)
        city = r.choice(CITIES)
        role = r.choice(ROLES)
        hours = r.choice([6, 8, 10, 12, 15, 20, 25])
        pct = r.choice([24, 31, 34, 41, 48, 52, 67, 84])
        weeks = r.choice([3, 4, 6, 8, 10, 12])
        metric = r.choice(["Leads", "AOV", "Open Rate", "ROAS", "Subscriber"])
        result = r.choice([
            f"+€{r.randint(2, 18)}.000/Monat",
            f"Conversion {r.choice(['1.1% → 2.8%', '1.4% → 3.1%', '0.9% → 2.4%'])}",
            f"ROAS {r.choice(['3.2', '4.1', '5.6', '6.8'])}×",
            f"{hours}h/Woche frei",
        ])
        quote = r.choice(QUOTE_TEMPLATES).format(
            product=product, hours=hours, pct=pct, weeks=weeks,
            result=result, metric=metric,
        )
        stars = 5 if r.random() > 0.12 else 4
        out.append({
            "id": f"t_{folder}_{i}_{base.replace(':', '')}",
            "folder": folder,
            "product": product,
            "name": f"{first} {last}",
            "role": f"{role}, {city}",
            "avatar": f"{first[0]}{last[0]}",
            "stars": stars,
            "quote": quote,
            "result": result,
            "created_at": _now(),
        })
    return out


def generate_case_studies(n: int = 50, seed: str | None = None) -> list[dict]:
    base = seed or datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
    out = []
    folders = list(VERTICALS.keys())
    for i in range(n):
        r = _rng(f"{base}:c:{i}")
        folder = folders[i % len(folders)]
        product = VERTICALS[folder]
        weeks = r.choice([4, 6, 8, 10, 12])
        pct = r.choice([28, 34, 41, 52, 67, 84, 120, 184])
        hours = r.choice([8, 11, 14, 18, 22])
        eur = r.choice([4, 6, 8, 12, 18, 28, 42])
        roas = r.choice(["3.4", "4.2", "5.1", "6.3"])
        mrr = r.choice([4200, 7800, 12400, 18400, 28400])
        ltv = r.choice([18, 22, 27, 34])
        result = r.choice(CASE_RESULTS).format(
            pct=pct, weeks=weeks, hours=hours, eur=eur,
            roas=roas, mrr=f"{mrr:,}".replace(",", "."), ltv=ltv,
        )
        client_type = r.choice([
            "DACH E-Commerce Agency", "DTC Fashion Brand", "Info-Product Vendor",
            "Shopify Plus Operator", "Solo Founder", "Performance Team",
        ])
        body = r.choice(CASE_BODIES).format(
            product=product, client_type=client_type, weeks=weeks,
            result=result, hours=hours,
        )
        metrics = [
            {"label": "Zeitraum", "value": f"{weeks} Wochen"},
            {"label": "Ergebnis", "value": result.split("·")[0].strip()[:28]},
            {"label": "Ops-Last", "value": f"−{r.choice([45, 60, 72, 85])}%"},
            {"label": "Empfehlung", "value": f"{r.choice([9, 10])}/10"},
        ]
        out.append({
            "id": f"c_{folder}_{i}_{base.replace(':', '')}",
            "folder": folder,
            "product": product,
            "client": client_type,
            "result": result,
            "body": body,
            "metrics": metrics,
            "created_at": _now(),
        })
    return out


def save_catalogs(
    testimonials: list[dict],
    cases: list[dict],
    demos: list[dict] | None = None,
) -> dict:
    CFG.mkdir(parents=True, exist_ok=True)
    payloads = [
        (T_PATH, {"updated": _now(), "count": len(testimonials), "items": testimonials}),
        (C_PATH, {"updated": _now(), "count": len(cases), "items": cases}),
    ]
    if demos is not None:
        payloads.append((D_PATH, {"updated": _now(), "count": len(demos), "items": demos}))
    for path, payload in payloads:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        data_mirror = ROOT / "data" / path.name
        try:
            data_mirror.parent.mkdir(parents=True, exist_ok=True)
            data_mirror.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    out = {"testimonials": len(testimonials), "case_studies": len(cases)}
    if demos is not None:
        out["demos"] = len(demos)
    return out


def load_catalogs() -> tuple[list[dict], list[dict], list[dict]]:
    t, c, d = [], [], []
    if T_PATH.exists():
        t = json.loads(T_PATH.read_text(encoding="utf-8")).get("items") or []
    if C_PATH.exists():
        c = json.loads(C_PATH.read_text(encoding="utf-8")).get("items") or []
    if D_PATH.exists():
        d = json.loads(D_PATH.read_text(encoding="utf-8")).get("items") or []
    return t, c, d


def _load_buy_urls() -> dict[str, str]:
    if not MONEY.exists():
        return {}
    try:
        data = json.loads(MONEY.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for f in data.get("featured") or []:
        if f.get("key") and f.get("url"):
            out[f["key"]] = f["url"]
    for k, p in (data.get("products") or {}).items():
        tiers = p.get("tiers") or []
        feat = tiers[1] if len(tiers) > 1 else (tiers[0] if tiers else {})
        if feat.get("url"):
            out[k] = feat["url"]
    return out


# folder → money_map product key
FOLDER_KEYS = {
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

DEMO_LIVE = {
    "bullpower-hub": "https://supermegabot-production.up.railway.app",
    "steuercockpit": "https://steuercockpit-production-44c9.up.railway.app",
    "shopify-brutal-tuning": "https://shopify-brutal-tuning.vercel.app",
    "shopify-acquisition-engine": "https://shopify-acquisition-engine.vercel.app",
    "shopify-suite": "https://supermegabot-production.up.railway.app",
    "telegram-bot": "https://t.me/DudiRudibot",
    "gumroad-discord": "https://gumroad-discord.vercel.app",
    "icomeauto": "https://icomeauto-production-e4e5.up.railway.app",
    "autoincome-ai": "https://autoincome-ai.vercel.app",
    "bullpower-ai": "https://bullpower-ai.vercel.app",
    "launcher": "https://launcher-ten-livid.vercel.app",
    "lead-capture": "https://lead-capture-gamma-nine.vercel.app",
    "master-dashboard": "https://supermegabot-production.up.railway.app",
    "creatorai-ultra": "https://creatorai-ultra.vercel.app",
    "creatorstudio-pro": "https://creatorstudio-pro.vercel.app",
    "digistore24-suite": "https://digistore24-suite.vercel.app",
    "cognitive-symphony": "https://cognitive-symphony.vercel.app",
}

TAGLINES = {
    "bullpower-hub": "12 KI-Tools · ein Command Center",
    "steuercockpit": "KI-Buchhaltung für Selbstständige",
    "shopify-brutal-tuning": "Performance · Conversion · Speed",
    "shopify-acquisition-engine": "Traffic + Ads + Funnels im Autopilot",
    "shopify-suite": "Vollautomatisierung für Shopify",
    "telegram-bot": "Broadcasts · Leads · Sales im Chat",
    "gumroad-discord": "Kauf → Rolle → Zugang in Sekunden",
    "icomeauto": "Passive Income Pipelines",
    "autoincome-ai": "Passive Income Machine",
    "bullpower-ai": "KI Business Automation Suite",
    "launcher": "Alle Tools · ein Startpunkt",
    "lead-capture": "Audit → High-Ticket Close",
    "master-dashboard": "Revenue · Tasks · Alerts live",
    "creatorai-ultra": "KI Content Empire",
    "creatorstudio-pro": "Premium Content Engine",
    "digistore24-suite": "Affiliate & Vendor Automation",
    "cognitive-symphony": "DS24 Automation OS",
}


def generate_demos(cases: list[dict] | None = None) -> list[dict]:
    """Build demo catalog for every product vertical."""
    cases = cases or []
    buys = _load_buy_urls()
    default_buy = "https://buy.stripe.com/fZueVf9jAguu1gc9kO4F42Ev"
    out = []
    for folder, product in VERTICALS.items():
        local_cases = [c for c in cases if c.get("folder") == folder]
        c0 = local_cases[0] if local_cases else None
        metrics = (c0 or {}).get("metrics") or [
            {"label": "Setup", "value": "< 7 Tage"},
            {"label": "Automation", "value": "24/7"},
            {"label": "Support", "value": "Priority"},
            {"label": "ROI", "value": "Cashflow"},
        ]
        # normalize metrics to list of pairs for HTML
        metric_pairs = []
        for m in metrics[:4]:
            if isinstance(m, dict):
                metric_pairs.append((m.get("label", "KPI"), m.get("value", "—")))
            elif isinstance(m, (list, tuple)) and len(m) >= 2:
                metric_pairs.append((m[0], m[1]))
        key = FOLDER_KEYS.get(folder, "")
        buy = buys.get(key) or default_buy
        live = DEMO_LIVE.get(folder, "https://supermegabot-production.up.railway.app")
        out.append({
            "id": f"demo_{folder}",
            "folder": folder,
            "product": product,
            "title": product,
            "tagline": TAGLINES.get(folder, "High-Ticket Automation"),
            "demo_page": f"/demo.html",
            "demo_url": live,
            "buy_url": buy,
            "case_client": (c0 or {}).get("client", "DACH Online Business"),
            "case_result": (c0 or {}).get("result", "Messbarer ROI in 30–90 Tagen"),
            "case_body": (c0 or {}).get("body", "High-Ticket Setup mit Demo und klaren KPIs."),
            "metrics": metric_pairs,
            "created_at": _now(),
        })
    return out


# ── HTML injection ───────────────────────────────────────────────────────────

INJECT_MARK = "<!-- AUTONOMOUS SOCIAL PROOF — auto-injected -->"
DEMO_SECTION_MARK = "<!-- AUTONOMOUS DEMO CTA — auto-injected -->"

DEMO_PAGE_TMPL = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Live Demo</title>
<meta name="description" content="Interaktive Demo von {title}. Testimonials, Case Study und High-Ticket Checkout.">
<meta name="robots" content="index,follow">
<style>
:root{{--bg:#07070c;--card:#12121c;--line:#2a2a3a;--text:#f1f5f9;--muted:#94a3b8;--acc:#818cf8;--ok:#4ade80;--warn:#facc15}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif;min-height:100vh}}
nav{{display:flex;justify-content:space-between;align-items:center;padding:1rem 1.5rem;border-bottom:1px solid var(--line);position:sticky;top:0;background:rgba(7,7,12,.92);backdrop-filter:blur(12px);z-index:10}}
.logo{{font-weight:900;color:var(--acc)}}
.nav a{{color:var(--muted);text-decoration:none;margin-left:1rem;font-weight:600;font-size:.9rem}}
.nav a.cta{{background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;padding:.55rem 1rem;border-radius:8px}}
main{{max-width:1100px;margin:0 auto;padding:2rem 1.25rem 4rem}}
h1{{font-size:clamp(1.8rem,3vw,2.6rem);font-weight:900;margin-bottom:.5rem}}
.sub{{color:var(--muted);margin-bottom:1.5rem;line-height:1.6}}
.grid{{display:grid;grid-template-columns:1.4fr 1fr;gap:1.25rem}}
@media(max-width:860px){{.grid{{grid-template-columns:1fr}}}}
.panel{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:1.25rem}}
.panel h2{{font-size:1rem;margin-bottom:1rem;color:#c7d2fe}}
.kpis{{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}}
.kpi{{background:#0a0a12;border:1px solid var(--line);border-radius:12px;padding:.9rem}}
.kpi b{{display:block;font-size:1.15rem;margin-top:.25rem}}
.kpi span{{color:var(--muted);font-size:.72rem;font-weight:700;text-transform:uppercase}}
.log{{font-family:ui-monospace,monospace;font-size:.8rem;color:#94a3b8;background:#0a0a12;border-radius:10px;padding:1rem;max-height:220px;overflow:auto;line-height:1.55}}
.log .ok{{color:var(--ok)}}
.btn{{display:block;text-align:center;text-decoration:none;font-weight:800;padding:1rem;border-radius:10px;margin-top:.75rem}}
.btn-primary{{background:linear-gradient(135deg,#4ade80,#22c55e);color:#000}}
.btn-ghost{{border:1px solid var(--line);color:var(--text)}}
.tabs{{display:flex;gap:.5rem;margin-bottom:1rem;flex-wrap:wrap}}
.tab{{padding:.45rem .85rem;border-radius:999px;border:1px solid var(--line);color:var(--muted);cursor:pointer;font-size:.82rem;font-weight:700;background:transparent}}
.tab.active{{background:rgba(129,140,248,.2);color:#c7d2fe;border-color:rgba(129,140,248,.5)}}
.case{{margin-top:1.5rem;padding:1.25rem;border-radius:16px;border:1px solid rgba(74,222,128,.3);background:linear-gradient(160deg,#0f1a14,#10140f)}}
.case h3{{color:var(--ok);margin-bottom:.5rem}}
.quote{{margin-top:1rem;padding:1rem;border-radius:12px;border:1px solid rgba(250,204,21,.25);background:#14120a;color:#e4e4e7;font-size:.92rem;line-height:1.55}}
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
  <p class="sub">{tagline}. Mock-Dashboard mit Live-Feel · Case Study · High-Ticket Checkout.</p>
  <div class="grid">
    <div class="panel">
      <div class="tabs" id="tabs">
        <button class="tab active" data-t="overview">Overview</button>
        <button class="tab" data-t="pipeline">Pipeline</button>
        <button class="tab" data-t="billing">Billing</button>
        <button class="tab" data-t="alerts">Alerts</button>
      </div>
      <div id="view-overview"><h2>KPI Stream</h2><div class="kpis">{kpi_blocks}</div></div>
      <div id="view-pipeline" style="display:none"><h2>Automation Pipeline</h2><div class="log" id="pipe-log"></div></div>
      <div id="view-billing" style="display:none"><h2>Billing Preview</h2>
        <div class="log">plan: high-ticket<br>status: <span class="ok">ready_to_charge</span><br>stripe: connected (live)</div>
        <a class="btn btn-primary" href="{buy_url}">Checkout öffnen →</a>
      </div>
      <div id="view-alerts" style="display:none"><h2>System Alerts</h2>
        <div class="log"><span class="ok">[ok]</span> health check passed<br><span class="ok">[ok]</span> webhooks listening<br><span class="ok">[ok]</span> social proof loaded</div>
      </div>
    </div>
    <div>
      <div class="panel">
        <h2>Demo Controls</h2>
        <button class="btn btn-ghost" id="btn-run" style="width:100%;cursor:pointer;background:#1e1e2e;color:#fff;border:1px solid #333">▶ Pipeline simulieren</button>
        <a class="btn btn-primary" href="{buy_url}">High-Ticket Plan wählen</a>
        <a class="btn btn-ghost" href="{demo_url}" target="_blank" rel="noopener">Echtes Live-System ↗</a>
        <a class="btn btn-ghost" href="index.html#autonomous-social-proof">Testimonials & Cases</a>
      </div>
      <div class="case">
        <h3>Case Study · {case_client}</h3>
        <div style="font-weight:800;color:#86efac;margin-bottom:.5rem">{case_result}</div>
        <p style="color:#a1a1aa;line-height:1.6;font-size:.92rem">{case_body}</p>
        <div class="quote">⭐ „{testimonial_quote}"<br><span style="color:#71717a;font-size:.85rem">— {testimonial_name}</span></div>
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
const lines=['[boot] loading automation graph…','[ok] connectors ready','[ok] scheduler online','[run] pipeline queued','[run] social_proof injected','[ok] demo cycle complete'];
const log=document.getElementById('pipe-log');
function typeLines(){{
  log.innerHTML=''; let i=0;
  const t=setInterval(()=>{{
    if(i>=lines.length){{clearInterval(t);return;}}
    const el=document.createElement('div');
    el.innerHTML=lines[i].includes('[ok]')||lines[i].includes('complete')?'<span class="ok">'+lines[i]+'</span>':lines[i];
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
setTimeout(typeLines,400);
</script>
</body>
</html>
"""


def _stars(n: int) -> str:
    return "★" * n + "☆" * (5 - n)


def build_demo_cta_section(demo: dict) -> str:
    metrics = demo.get("metrics") or []
    mhtml = "".join(
        f'<div style="background:rgba(0,0,0,.35);border:1px solid rgba(99,102,241,.25);border-radius:10px;padding:.65rem">'
        f'<div style="color:#64748b;font-size:.68rem;font-weight:700;text-transform:uppercase">{a}</div>'
        f'<div style="color:#fff;font-weight:800">{b}</div></div>'
        for a, b in metrics[:4]
    )
    return f'''
{DEMO_SECTION_MARK}
<section id="autonomous-demo" style="position:relative;z-index:2;padding:64px 1.25rem;background:linear-gradient(180deg,#0a0a12 0%,#12101c 100%);border-top:1px solid rgba(129,140,248,.25)">
  <div style="max-width:1100px;margin:0 auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.25rem;align-items:center">
    <div>
      <div style="display:inline-block;padding:.35rem 1rem;border-radius:999px;background:rgba(99,102,241,.15);border:1px solid rgba(99,102,241,.4);color:#a5b4fc;font-weight:800;font-size:.78rem;letter-spacing:.07em;margin-bottom:.85rem">▶ LIVE DEMO</div>
      <h2 style="font-size:clamp(1.6rem,3vw,2.3rem);font-weight:900;color:#fff;margin:0 0 .5rem">{demo.get("title","Demo")}</h2>
      <p style="color:#a1a1aa;line-height:1.65;margin:0 0 1.25rem">{demo.get("tagline","")} — interaktiv testen, dann High-Ticket starten.</p>
      <div style="display:flex;flex-wrap:wrap;gap:.75rem">
        <a href="demo.html" style="background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;font-weight:800;padding:.95rem 1.25rem;border-radius:10px;text-decoration:none">▶ Demo öffnen</a>
        <a href="{demo.get("demo_url","#")}" target="_blank" rel="noopener" style="border:1px solid rgba(167,139,250,.45);color:#c4b5fd;font-weight:700;padding:.95rem 1.25rem;border-radius:10px;text-decoration:none">Live System ↗</a>
        <a href="{demo.get("buy_url","#")}" style="background:linear-gradient(135deg,#4ade80,#22c55e);color:#000;font-weight:900;padding:.95rem 1.25rem;border-radius:10px;text-decoration:none">Jetzt kaufen →</a>
      </div>
    </div>
    <div style="background:#12121c;border:1px solid rgba(129,140,248,.3);border-radius:18px;padding:1.25rem">
      <div style="color:#86efac;font-weight:800;font-size:.8rem;margin-bottom:.5rem">CASE · {demo.get("case_client","")}</div>
      <div style="color:#fff;font-weight:900;font-size:1.15rem;margin-bottom:.75rem">{demo.get("case_result","")}</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:.55rem">{mhtml}</div>
    </div>
  </div>
</section>
'''


def build_section(folder: str, testimonials: list[dict], cases: list[dict]) -> str:
    t_local = [x for x in testimonials if x.get("folder") == folder][:6]
    if len(t_local) < 3:
        t_local = (t_local + testimonials)[:6]
    c_local = [x for x in cases if x.get("folder") == folder][:3]
    if len(c_local) < 2:
        c_local = (c_local + cases)[:3]

    t_cards = []
    for t in t_local:
        t_cards.append(
            f'''<div style="background:#12121c;border:1px solid rgba(250,204,21,.2);border-radius:16px;padding:1.25rem;min-width:260px">
  <div style="color:#facc15;letter-spacing:1px;margin-bottom:.5rem">{_stars(int(t.get("stars",5)))}</div>
  <p style="color:#e4e4e7;font-size:.95rem;line-height:1.55;margin:0 0 1rem">"{t.get("quote","")}"</p>
  <div style="display:flex;align-items:center;gap:.75rem">
    <div style="width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#6366f1,#8b5cf6);display:flex;align-items:center;justify-content:center;font-weight:800;color:#fff;font-size:.85rem">{t.get("avatar","BP")}</div>
    <div>
      <div style="color:#fff;font-weight:800;font-size:.9rem">{t.get("name","")}</div>
      <div style="color:#71717a;font-size:.78rem">{t.get("role","")}</div>
      <div style="color:#4ade80;font-weight:700;font-size:.8rem;margin-top:.15rem">{t.get("result","")}</div>
    </div>
  </div>
</div>'''
        )

    c_cards = []
    for c in c_local:
        metrics = c.get("metrics") or []
        mhtml = "".join(
            f'<div style="background:rgba(0,0,0,.3);border-radius:8px;padding:.55rem .7rem">'
            f'<div style="color:#64748b;font-size:.68rem;font-weight:700;text-transform:uppercase">{m.get("label","")}</div>'
            f'<div style="color:#fff;font-weight:800;font-size:.88rem">{m.get("value","")}</div></div>'
            for m in metrics[:4]
        )
        c_cards.append(
            f'''<div style="background:linear-gradient(160deg,#0f1a14,#10140f);border:1px solid rgba(74,222,128,.28);border-radius:16px;padding:1.35rem">
  <div style="color:#4ade80;font-weight:800;font-size:.75rem;letter-spacing:.06em;margin-bottom:.4rem">CASE STUDY</div>
  <div style="color:#fff;font-weight:900;font-size:1.05rem;margin-bottom:.25rem">{c.get("client","")}</div>
  <div style="color:#86efac;font-weight:800;margin-bottom:.75rem">{c.get("result","")}</div>
  <p style="color:#a1a1aa;font-size:.9rem;line-height:1.6;margin:0 0 1rem">{c.get("body","")}</p>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:.5rem">{mhtml}</div>
</div>'''
        )

    product = VERTICALS.get(folder, "BullPower")
    return f'''
{INJECT_MARK}
<section id="autonomous-social-proof" style="position:relative;z-index:2;padding:72px 1.25rem;background:linear-gradient(180deg,#06060a 0%,#0c0a14 100%);border-top:1px solid rgba(250,204,21,.18)">
  <div style="max-width:1100px;margin:0 auto">
    <div style="text-align:center;margin-bottom:2rem">
      <div style="display:inline-block;padding:.35rem 1rem;border-radius:999px;background:rgba(250,204,21,.12);border:1px solid rgba(250,204,21,.35);color:#facc15;font-weight:800;font-size:.78rem;letter-spacing:.07em;margin-bottom:.85rem">⭐ TESTIMONIALS · CASE STUDIES · AUTO-UPDATED</div>
      <h2 style="font-size:clamp(1.7rem,3vw,2.5rem);font-weight:900;color:#fff;margin:0 0 .5rem">Echte Ergebnisse mit {product}</h2>
      <p style="color:#a1a1aa;max-width:560px;margin:0 auto">Autonom generierte & rotierende Social Proofs — immer frisch auf der Seite.</p>
    </div>
    <h3 style="color:#e4e4e7;font-size:1.05rem;margin:0 0 1rem">Kundenstimmen</h3>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem;margin-bottom:2.25rem">
      {"".join(t_cards)}
    </div>
    <h3 style="color:#e4e4e7;font-size:1.05rem;margin:0 0 1rem">Case Studies</h3>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem">
      {"".join(c_cards)}
    </div>
    <p style="text-align:center;color:#52525b;font-size:.8rem;margin-top:1.5rem">Social Proof Engine · updates autonom · Ergebnisse variieren je Setup</p>
  </div>
</section>
'''


def _insert_before_markers(html: str, block: str, markers: tuple[str, ...]) -> str:
    for marker in markers:
        if marker.startswith("id="):
            mid = marker.split("=", 1)[1].strip('"')
            m = re.search(rf'<section[^>]*id="{re.escape(mid)}"', html)
            if m:
                return html[: m.start()] + block + "\n" + html[m.start() :]
            continue
        idx = html.find(marker) if not marker.startswith("</") else html.lower().rfind(marker)
        if idx >= 0:
            return html[:idx] + block + "\n" + html[idx:]
    return html + block


def inject_all_landings(
    testimonials: list[dict],
    cases: list[dict],
    demos: list[dict] | None = None,
) -> dict:
    demos = demos or []
    demo_by_folder = {d.get("folder"): d for d in demos}
    updated = 0
    demos_written = 0
    for folder in sorted(DEPLOY.iterdir()):
        if not folder.is_dir() or folder.name in ("demo-hub",):
            continue
        index = folder / "index.html"
        if not index.exists():
            continue
        name = folder.name
        html = index.read_text(encoding="utf-8", errors="replace")
        html = re.sub(
            r"<!-- AUTONOMOUS SOCIAL PROOF — auto-injected -->.*?</section>\s*",
            "",
            html,
            flags=re.S,
        )
        html = re.sub(
            r"<!-- AUTONOMOUS DEMO CTA — auto-injected -->.*?</section>\s*",
            "",
            html,
            flags=re.S,
        )
        demo = demo_by_folder.get(name)
        demo_block = build_demo_cta_section(demo) if demo else ""
        proof_block = build_section(name, testimonials, cases)
        combined = demo_block + "\n" + proof_block
        html = _insert_before_markers(
            html,
            combined,
            (
                "id=\"demo-case-study\"",
                "<!-- DEMO + CASE STUDY",
                "<!-- HIGH-TICKET WAVE",
                "</body>",
            ),
        )
        # nav demo link
        if "demo.html" not in html:
            html = re.sub(
                r'(class="[^"]*nav-links[^"]*"[^>]*>)',
                r'\1\n      <a href="demo.html">Demo</a>',
                html,
                count=1,
            )
        index.write_text(html, encoding="utf-8")
        updated += 1

        # write interactive demo.html
        if demo:
            t_local = [x for x in testimonials if x.get("folder") == name]
            t0 = t_local[0] if t_local else (testimonials[0] if testimonials else {})
            kpis = "".join(
                f'<div class="kpi"><span>{a}</span><b>{b}</b></div>'
                for a, b in (demo.get("metrics") or [])[:4]
            )
            page = DEMO_PAGE_TMPL.format(
                title=demo.get("title", name),
                tagline=demo.get("tagline", ""),
                demo_url=demo.get("demo_url", "#"),
                buy_url=demo.get("buy_url", "#"),
                case_client=demo.get("case_client", ""),
                case_result=demo.get("case_result", ""),
                case_body=demo.get("case_body", ""),
                kpi_blocks=kpis,
                testimonial_quote=(t0 or {}).get("quote", "Setup war schnell, Ergebnisse messbar."),
                testimonial_name=(t0 or {}).get("name", "Kunde"),
            )
            (folder / "demo.html").write_text(page, encoding="utf-8")
            demos_written += 1

    # demo hub
    hub = DEPLOY / "demo-hub"
    hub.mkdir(exist_ok=True)
    cards = []
    for d in demos:
        cards.append(
            f'<a href="../{d.get("folder")}/demo.html" style="display:block;padding:1.2rem;border:1px solid #333;'
            f'border-radius:14px;background:#12121c;color:#fff;text-decoration:none">'
            f'<div style="font-weight:900;margin-bottom:.35rem">{d.get("title")}</div>'
            f'<div style="color:#94a3b8;font-size:.9rem;margin-bottom:.5rem">{d.get("tagline")}</div>'
            f'<div style="color:#4ade80;font-weight:700">{d.get("case_result")}</div></a>'
        )
    (hub / "index.html").write_text(
        "<!DOCTYPE html><html lang='de'><head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Demo Hub — Alle Live Demos</title>"
        "<style>body{background:#07070c;color:#fff;font-family:system-ui;padding:2rem}"
        "h1{margin-bottom:.5rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));"
        "gap:1rem;margin-top:1.5rem}p{color:#94a3b8}</style></head><body>"
        "<h1>▶ Demo Hub</h1><p>Autonom aktualisierte Demos · Testimonials · Case Studies</p>"
        f"<div class='grid'>{''.join(cards)}</div></body></html>",
        encoding="utf-8",
    )
    return {"landings_updated": updated, "demos_written": demos_written, "demo_hub": True}


async def maybe_telegram_post(testimonials: list[dict]) -> dict:
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "") or os.getenv("TELEGRAM_CHANNEL_ID", "")
    if not tok or not chat or not testimonials:
        return {"posted": False, "reason": "no_creds_or_empty"}
    t = random.choice(testimonials)
    text = (
        f"⭐ <b>Kundenstimme · {t.get('product')}</b>\n\n"
        f"\"{t.get('quote')}\"\n\n"
        f"— {t.get('name')}, {t.get('role')}\n"
        f"<b>{t.get('result')}</b>\n\n"
        f"→ https://supermegabot-production.up.railway.app/api/social-proof"
    )
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as r:
                ok = r.status == 200
                return {"posted": ok, "status": r.status}
    except Exception as e:
        return {"posted": False, "error": str(e)[:120]}


def write_state(result: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


async def run_social_proof_cycle(post_telegram: bool = True) -> dict:
    """Full autonomous cycle: testimonials + cases + demos everywhere."""
    log.info("Sales assets cycle starting (testimonials + cases + demos)…")
    testimonials = generate_testimonials(96)
    cases = generate_case_studies(51)
    demos = generate_demos(cases)
    counts = save_catalogs(testimonials, cases, demos)
    inject = inject_all_landings(testimonials, cases, demos)
    tg = await maybe_telegram_post(testimonials) if post_telegram else {"posted": False, "skipped": True}
    result = {
        "ok": True,
        "ts": _now(),
        **counts,
        **inject,
        "telegram": tg,
        "api": {
            "testimonials": "/api/testimonials",
            "case_studies": "/api/case-studies",
            "demos": "/api/demos",
            "social_proof": "/api/social-proof",
        },
    }
    write_state(result)
    log.info(
        "Assets: %d testimonials, %d cases, %d demos, %d landings, demos_html=%s, tg=%s",
        counts["testimonials"],
        counts["case_studies"],
        counts.get("demos", 0),
        inject["landings_updated"],
        inject.get("demos_written"),
        tg.get("posted"),
    )
    return result


# alias
run_sales_assets_cycle = run_social_proof_cycle


def get_social_proof_bundle(
    folder: str | None = None,
    limit_t: int = 12,
    limit_c: int = 6,
    limit_d: int = 20,
) -> dict:
    t, c, d = load_catalogs()
    if not t or not c:
        t = generate_testimonials(48)
        c = generate_case_studies(24)
        d = generate_demos(c)
        save_catalogs(t, c, d)
    elif not d:
        d = generate_demos(c)
        save_catalogs(t, c, d)
    if folder:
        tf = [x for x in t if x.get("folder") == folder] or t
        cf = [x for x in c if x.get("folder") == folder] or c
        df = [x for x in d if x.get("folder") == folder] or d
    else:
        tf, cf, df = t, c, d
    return {
        "ok": True,
        "updated": _now(),
        "testimonials": tf[:limit_t] if limit_t else [],
        "case_studies": cf[:limit_c] if limit_c else [],
        "demos": df[:limit_d] if limit_d else [],
        "count_t": len(tf),
        "count_c": len(cf),
        "count_d": len(df),
        "folder": folder,
    }


# Sync entry for scripts / __main__
def run_sync(post_telegram: bool = False) -> dict:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(run_social_proof_cycle(post_telegram=post_telegram))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import asyncio
    r = asyncio.run(run_social_proof_cycle(post_telegram=False))
    print(json.dumps(r, indent=2, ensure_ascii=False))
