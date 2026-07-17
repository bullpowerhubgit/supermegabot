#!/usr/bin/env python3
"""
Sales Call Process + Case Studies — shared by bots, agents, landings.
"""
from __future__ import annotations

import os
from typing import Any

# Primary CTAs (env-overridable)
STRIPE_STARTER = os.getenv(
    "STRIPE_CHECKOUT_STARTER",
    "https://buy.stripe.com/3cIfZjgM26TUgb60Oi4F434D",
)
STRIPE_PRO = os.getenv(
    "STRIPE_CHECKOUT_PRO",
    "https://buy.stripe.com/aFa9AVanE0vwe2YdB44F434C",
)
SALES_CALL_URL = os.getenv("SALES_CALL_URL", "https://t.me/DudiRudibot")
SALES_CALL_FALLBACK = os.getenv("SALES_CALL_FALLBACK", "https://t.me/rudisarkany")
DEMO_URL = os.getenv(
    "DEMO_DASHBOARD_URL", "https://supermegabot-production.up.railway.app"
)

CASE_STUDIES: list[dict[str, str]] = [
    {
        "id": "cs_shopify_recovery",
        "title": "Shopify Support + Recovery",
        "persona": "Shopify Solo / DTC",
        "result": "−40% Support-Zeit · +€2.1k Recovery",
        "duration": "45 Tage",
        "quote": "Weniger Tickets, mehr Checkout-Nachfassen — ohne neues Team.",
        "body": "Manuelle FAQs und ungenutzte Abandoned Checkouts. Nach Automation: Bot übernimmt Order-Status/FAQ, Recovery-Flow über Telegram + Email.",
    },
    {
        "id": "cs_agency_hub",
        "title": "Multi-Shop Command Center",
        "persona": "Agency / Multi-Brand",
        "result": "+Ops-Effizienz · 1 Hub statt 12 Tools",
        "duration": "90 Tage",
        "quote": "Team verkauft wieder — statt Firefighting.",
        "body": "9 Shops, fragmentierte Tools. Rollout eines zentralen Hubs: Sync, Social, Billing im Autopilot.",
    },
    {
        "id": "cs_telegram_sub",
        "title": "Telegram Subscription",
        "persona": "Creator / Community",
        "result": "Follower → Paid Abo im Bot",
        "duration": "60 Tage",
        "quote": "Recurring Revenue direkt im Chat.",
        "body": "Kostenlose Gruppe ohne Monetarisierung. Bot + Stripe: Zugang nach Zahlung, Broadcasts, Auto-Reminders.",
    },
    {
        "id": "cs_tax_compliance",
        "title": "Steuer & Compliance DACH",
        "persona": "Online-Händler DE/AT",
        "result": "Stunden → Minuten · weniger Risiko",
        "duration": "erster Monat",
        "quote": "Compliance im Autopilot — du prüfst nur noch.",
        "body": "USt/OSS und Belege manuell. Tool klassifiziert, erinnert und bereitet Meldungen vor.",
    },
]

PROCESS_STEPS: list[dict[str, str]] = [
    {
        "n": "1",
        "title": "Qualifizieren",
        "desc": "Business-Typ, Schmerz, Umsatz-Band, Budget-Fit (Starter/Pro/Scale).",
    },
    {
        "n": "2",
        "title": "Discovery Call (15–30 Min)",
        "desc": "3–4 Fragen: Zeitfresser, Umsatz-Leak, 30-Tage-Ziel, Entscheidungsweg.",
    },
    {
        "n": "3",
        "title": "Case Study matchen",
        "desc": "1 passende Erfolgsgeschichte mit Messzahl + Zeitraum zeigen.",
    },
    {
        "n": "4",
        "title": "Demo / Solution Map",
        "desc": "Max 3 Features live — Dashboard, Bot oder Automation die den Schmerz löst.",
    },
    {
        "n": "5",
        "title": "Close",
        "desc": "Trial €49 Sofort · Pro/Scale + Setup · oder Follow-up 48h mit Case-PDF.",
    },
]


def pick_case(persona_hint: str = "") -> dict[str, str]:
    h = (persona_hint or "").lower()
    if any(x in h for x in ("agency", "multi", "hub")):
        return CASE_STUDIES[1]
    if any(x in h for x in ("telegram", "creator", "community", "bot")):
        return CASE_STUDIES[2]
    if any(x in h for x in ("steuer", "tax", "compliance", "oss")):
        return CASE_STUDIES[3]
    return CASE_STUDIES[0]


def cta_block(lang: str = "de") -> dict[str, str]:
    if lang.startswith("en"):
        return {
            "primary_label": "Start 7-day free trial",
            "primary_url": STRIPE_STARTER,
            "secondary_label": "Book 15-min strategy call",
            "secondary_url": SALES_CALL_URL,
            "tertiary_label": "View case studies",
            "tertiary_url": "#case-studies",
            "pro_url": STRIPE_PRO,
            "demo_url": DEMO_URL,
        }
    return {
        "primary_label": "7 Tage kostenlos testen",
        "primary_url": STRIPE_STARTER,
        "secondary_label": "15-Min Strategy Call buchen",
        "secondary_url": SALES_CALL_URL,
        "tertiary_label": "Case Studies ansehen",
        "tertiary_url": "#case-studies",
        "pro_url": STRIPE_PRO,
        "demo_url": DEMO_URL,
    }


def telegram_book_script() -> str:
    return (
        "Perfekt — 15-Min Strategy Call.\n"
        "Schreib kurz: 1) Shopify/DS24/Agency 2) größter Schmerz 3) Ziel in 30 Tagen.\n"
        f"Dann Agenda + nächster Schritt. Oder direkt Trial: {STRIPE_STARTER}"
    )


def telegram_after_case(persona: str = "") -> str:
    cs = pick_case(persona)
    return (
        f"Ähnlich wie {cs['persona']}: {cs['result']} in {cs['duration']}.\n"
        f"{cs['quote']}\n"
        f"→ Trial: {STRIPE_STARTER}\n"
        f"→ Call: {SALES_CALL_URL}"
    )


def sales_process_summary() -> dict[str, Any]:
    return {
        "steps": PROCESS_STEPS,
        "cases": CASE_STUDIES,
        "cta": cta_block("de"),
        "book_script": telegram_book_script(),
    }


def html_sections(product_name: str = "SuperMegaBot", accent: str = "#6c63ff") -> str:
    """Reusable HTML block: Case Studies + Sales Call Process + dual CTAs."""
    cases_html = ""
    for cs in CASE_STUDIES:
        cases_html += f"""
        <div class="sc-case-card">
          <div class="sc-case-result">{cs['result']}</div>
          <div class="sc-case-meta">{cs['persona']} · {cs['duration']}</div>
          <h3>{cs['title']}</h3>
          <p>{cs['body']}</p>
          <blockquote>„{cs['quote']}“</blockquote>
        </div>"""

    steps_html = ""
    for s in PROCESS_STEPS:
        steps_html += f"""
        <div class="sc-step">
          <div class="sc-step-n">{s['n']}</div>
          <div>
            <h4>{s['title']}</h4>
            <p>{s['desc']}</p>
          </div>
        </div>"""

    cta = cta_block("de")
    return f"""
<!-- SMB_SALES_CASE_BLOCK -->
<style>
.sc-wrap{{max-width:1100px;margin:0 auto;padding:64px 20px;font-family:Inter,system-ui,sans-serif;color:#e2e8f0}}
.sc-wrap h2{{font-size:clamp(1.6rem,3vw,2.2rem);margin:0 0 .5rem;color:#fff}}
.sc-sub{{color:#94a3b8;margin:0 0 2rem;max-width:640px}}
.sc-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem;margin-bottom:3rem}}
.sc-case-card{{background:#111827;border:1px solid #1f2937;border-radius:14px;padding:1.25rem}}
.sc-case-result{{color:{accent};font-weight:800;font-size:.95rem;margin-bottom:.35rem}}
.sc-case-meta{{color:#64748b;font-size:.8rem;margin-bottom:.75rem}}
.sc-case-card h3{{margin:0 0 .5rem;font-size:1.05rem;color:#f8fafc}}
.sc-case-card p{{color:#94a3b8;font-size:.9rem;line-height:1.55;margin:0 0 .75rem}}
.sc-case-card blockquote{{margin:0;padding:.6rem .8rem;border-left:3px solid {accent};color:#cbd5e1;font-size:.88rem;background:rgba(108,99,255,.08);border-radius:0 8px 8px 0}}
.sc-steps{{display:flex;flex-direction:column;gap:.85rem;margin-bottom:2rem}}
.sc-step{{display:flex;gap:1rem;align-items:flex-start;background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:1rem 1.15rem}}
.sc-step-n{{min-width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,{accent},#00d4ff);color:#fff;font-weight:800;display:flex;align-items:center;justify-content:center}}
.sc-step h4{{margin:0 0 .25rem;color:#f1f5f9;font-size:1rem}}
.sc-step p{{margin:0;color:#94a3b8;font-size:.9rem}}
.sc-ctas{{display:flex;flex-wrap:wrap;gap:.75rem;margin-top:1.5rem}}
.sc-btn{{display:inline-block;padding:.85rem 1.4rem;border-radius:10px;font-weight:700;text-decoration:none;font-size:.92rem}}
.sc-btn-primary{{background:linear-gradient(135deg,{accent},#5b52ef);color:#fff}}
.sc-btn-secondary{{background:transparent;border:1px solid {accent};color:#c4b5fd}}
.sc-btn-ghost{{color:#94a3b8;border:1px solid #334155}}
.sc-badge{{display:inline-block;background:rgba(0,212,255,.12);color:#67e8f9;font-size:.75rem;font-weight:700;padding:.25rem .65rem;border-radius:999px;margin-bottom:1rem}}
</style>
<section class="sc-wrap" id="case-studies" data-smb-sales="1">
  <span class="sc-badge">CASE STUDIES · {product_name}</span>
  <h2>Echte Ergebnisse. Messbare Zahlen.</h2>
  <p class="sc-sub">Social Proof vor dem Checkout — und im Sales-Call die passende Story in 60 Sekunden.</p>
  <div class="sc-grid">{cases_html}
  </div>
</section>
<section class="sc-wrap" id="sales-call-process" data-smb-sales="1" style="padding-top:0">
  <span class="sc-badge">SALES-CALL PROZESS · 15–30 MIN</span>
  <h2>Vom Erstkontakt zum Close</h2>
  <p class="sc-sub">Gleicher Prozess überall: Qualifizieren → Discovery → Case → Demo → Close (Trial oder High-Ticket).</p>
  <div class="sc-steps">{steps_html}
  </div>
  <div class="sc-ctas">
    <a class="sc-btn sc-btn-primary" href="{cta['primary_url']}" target="_blank" rel="noopener">{cta['primary_label']} →</a>
    <a class="sc-btn sc-btn-secondary" href="{cta['secondary_url']}" target="_blank" rel="noopener">{cta['secondary_label']} →</a>
    <a class="sc-btn sc-btn-ghost" href="{cta['demo_url']}" target="_blank" rel="noopener">Live-Demo öffnen</a>
  </div>
</section>
<!-- /SMB_SALES_CASE_BLOCK -->
"""
