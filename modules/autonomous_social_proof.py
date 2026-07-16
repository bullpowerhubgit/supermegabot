#!/usr/bin/env python3
"""
Autonomous Social Proof Engine
==============================
Generates, rotates and injects Testimonials + Case Studies everywhere:

  • config/testimonials.json + config/case_studies.json (source of truth)
  • All netlify-deploy/*/index.html (inject carousels + case grids)
  • Public API: GET /api/testimonials, /api/case-studies, /api/social-proof
  • Scheduler task: regenerate + reinject every 6h
  • Telegram social-proof posts (best rotating quote)

No external AI required (template engine). Optional AI polish if available.
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


def save_catalogs(testimonials: list[dict], cases: list[dict]) -> dict:
    CFG.mkdir(parents=True, exist_ok=True)
    # also mirror to data for runtime
    for path, payload in (
        (T_PATH, {"updated": _now(), "count": len(testimonials), "items": testimonials}),
        (C_PATH, {"updated": _now(), "count": len(cases), "items": cases}),
    ):
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        data_mirror = ROOT / "data" / path.name
        try:
            data_mirror.parent.mkdir(parents=True, exist_ok=True)
            data_mirror.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    return {"testimonials": len(testimonials), "case_studies": len(cases)}


def load_catalogs() -> tuple[list[dict], list[dict]]:
    t, c = [], []
    if T_PATH.exists():
        t = json.loads(T_PATH.read_text(encoding="utf-8")).get("items") or []
    if C_PATH.exists():
        c = json.loads(C_PATH.read_text(encoding="utf-8")).get("items") or []
    return t, c


# ── HTML injection ───────────────────────────────────────────────────────────

INJECT_MARK = "<!-- AUTONOMOUS SOCIAL PROOF — auto-injected -->"


def _stars(n: int) -> str:
    return "★" * n + "☆" * (5 - n)


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


def inject_all_landings(testimonials: list[dict], cases: list[dict]) -> dict:
    updated = 0
    for folder in sorted(DEPLOY.iterdir()):
        if not folder.is_dir():
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
        section = build_section(name, testimonials, cases)
        # insert before demo/case or pricing or </body>
        inserted = False
        for marker in (
            "<!-- DEMO + CASE STUDY",
            "<!-- DEMO + CASE STUDY — auto-injected -->",
            "id=\"demo-case-study\"",
            "<!-- HIGH-TICKET WAVE",
            "<!-- AUTONOMOUS SOCIAL PROOF",
            "</body>",
        ):
            if marker == "id=\"demo-case-study\"":
                m = re.search(r'<section[^>]*id="demo-case-study"', html)
                if m:
                    html = html[: m.start()] + section + "\n" + html[m.start() :]
                    inserted = True
                    break
                continue
            idx = html.find(marker) if not marker.startswith("</") else html.lower().rfind(marker)
            if idx >= 0:
                html = html[:idx] + section + "\n" + html[idx:]
                inserted = True
                break
        if not inserted:
            html += section
        index.write_text(html, encoding="utf-8")
        updated += 1
    return {"landings_updated": updated}


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
    """Full autonomous cycle: generate → save → inject → optional telegram."""
    log.info("Social proof cycle starting…")
    testimonials = generate_testimonials(96)
    cases = generate_case_studies(51)
    counts = save_catalogs(testimonials, cases)
    inject = inject_all_landings(testimonials, cases)
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
            "social_proof": "/api/social-proof",
        },
    }
    write_state(result)
    log.info(
        "Social proof: %d testimonials, %d cases, %d landings, tg=%s",
        counts["testimonials"], counts["case_studies"], inject["landings_updated"], tg.get("posted"),
    )
    return result


def get_social_proof_bundle(folder: str | None = None, limit_t: int = 12, limit_c: int = 6) -> dict:
    t, c = load_catalogs()
    if not t or not c:
        t = generate_testimonials(48)
        c = generate_case_studies(24)
        save_catalogs(t, c)
    if folder:
        tf = [x for x in t if x.get("folder") == folder] or t
        cf = [x for x in c if x.get("folder") == folder] or c
    else:
        tf, cf = t, c
    return {
        "ok": True,
        "updated": _now(),
        "testimonials": tf[:limit_t],
        "case_studies": cf[:limit_c],
        "count_t": len(tf),
        "count_c": len(cf),
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
