#!/usr/bin/env python3
"""
WAVE 3 — Monetize EVERY remaining property at high-ticket prices.
Creates Stripe Live products + payment links + injects CTAs.
Also builds a mega money map for master-dashboard + config/money_map.json.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "config" / "high_ticket_wave3.json"
ENV_OUT = ROOT / "config" / "high_ticket_wave3.env"
MONEY_MAP = ROOT / "config" / "money_map.json"

for p in (ROOT / ".env",):
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

KEY = (os.getenv("STRIPE_SECRET_KEY_FULL") or os.getenv("STRIPE_SECRET_KEY") or "").strip()
if not KEY.startswith("sk_live_"):
    sys.exit("need sk_live_")

THANK_YOU = os.getenv("STRIPE_THANK_YOU_URL", "https://ineedit.com.co/pages/danke")

# Remaining + upgrades + meta-bundles
CATALOG = [
    {
        "key": "bullpower_hub",
        "folder": "bullpower-hub",
        "product": "BullPower Hub — 12 KI-Tools Empire",
        "tiers": [("Pro", 99700, "month"), ("Business", 299700, "month"), ("Empire", 499700, "month")],
    },
    {
        "key": "creatorai_ultra",
        "folder": "creatorai-ultra",
        "product": "CreatorAI Ultra — KI Content Empire",
        "tiers": [("Starter", 49700, "month"), ("Pro", 99700, "month"), ("Agency", 249700, "month")],
    },
    {
        "key": "creatorstudio_pro",
        "folder": "creatorstudio-pro",
        "product": "CreatorStudio Pro — Premium Content Engine",
        "tiers": [("Starter", 29700, "month"), ("Pro", 79700, "month"), ("Agency", 199700, "month")],
    },
    {
        "key": "ds24_pro_suite",
        "folder": "digistore24-suite",
        "product": "Digistore24 Pro Suite — Affiliate Empire",
        "tiers": [("Starter", 49700, "month"), ("Pro", 99700, "month"), ("Agency", 299700, "month")],
    },
    {
        "key": "cognitive_symphony",
        "folder": "cognitive-symphony",
        "product": "Cognitive Symphony — DS24 Automation OS",
        "tiers": [("Starter", 49700, "month"), ("Pro", 99700, "month"), ("Agency", 299700, "month")],
    },
    {
        "key": "shopify_suite_pro",
        "folder": "shopify-suite",
        "product": "Shopify Suite Pro — Full Automaton",
        "tiers": [("Starter", 49700, "month"), ("Pro", 99700, "month"), ("Enterprise", 249700, "month")],
    },
    {
        "key": "master_dashboard",
        "folder": "master-dashboard",
        "product": "BullPower Master Command Center",
        "tiers": [("Operator", 99700, "month"), ("Agency", 249700, "month"), ("White-Label", 499700, "month")],
    },
    {
        "key": "eu_compliance",
        "folder": None,  # no netlify folder required
        "product": "EU Compliance SaaS — DSGVO & AI Act Pack",
        "tiers": [("Starter", 49700, "month"), ("Pro", 99700, "month"), ("Enterprise", 249700, "month")],
    },
    {
        "key": "stripe_connect_saas",
        "folder": None,
        "product": "Stripe Connect SaaS — Multi-Vendor Platform",
        "tiers": [("Starter", 49700, "month"), ("Pro", 149700, "month"), ("Scale", 299700, "month")],
    },
    {
        "key": "seo_turbo",
        "folder": None,
        "product": "SEO Turbo Tools — Traffic & Ranking Engine",
        "tiers": [("Starter", 29700, "month"), ("Pro", 79700, "month"), ("Agency", 199700, "month")],
    },
    {
        "key": "analytics_mkt",
        "folder": None,
        "product": "Analytics Marketing Intelligence Suite",
        "tiers": [("Starter", 39700, "month"), ("Pro", 99700, "month"), ("Agency", 249700, "month")],
    },
    {
        "key": "aiitec_agency",
        "folder": None,
        "product": "AiiteC Agency OS — Full Stack Automation",
        "tiers": [("Starter", 99700, "month"), ("Pro", 249700, "month"), ("Enterprise", 499700, "month")],
    },
    # MEGA BUNDLES — highest ARPU
    {
        "key": "bundle_full_stack",
        "folder": "launcher",
        "product": "BullPower Full-Stack Empire Bundle",
        "tiers": [
            ("All Access", 199700, "month"),
            ("Agency White-Label", 499700, "month"),
            ("DFY Setup", 999700, None),
        ],
    },
    {
        "key": "bundle_shopify_empire",
        "folder": "shopify-suite",
        "product": "Shopify Empire Bundle — Acq+Brutal+Suite",
        "tiers": [
            ("Growth", 149700, "month"),
            ("Scale", 299700, "month"),
            ("DFY Launch", 499700, None),
        ],
    },
    {
        "key": "bundle_content_empire",
        "folder": "creatorai-ultra",
        "product": "Content Empire Bundle — CreatorAI+Studio",
        "tiers": [
            ("Creator", 99700, "month"),
            ("Studio Pro", 199700, "month"),
            ("Agency", 349700, "month"),
        ],
    },
]


def stripe(method: str, path: str, data: dict | None = None) -> dict:
    url = f"https://api.stripe.com/v1{path}"
    headers = {"Authorization": f"Bearer {KEY}"}
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data, doseq=True).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} HTTP {e.code}: {e.read().decode()[:400]}") from e


def ensure_product(name: str, key: str) -> str:
    listed = stripe("GET", "/products?active=true&limit=100")
    for p in listed.get("data", []):
        if p.get("name") == name:
            return p["id"]
    return stripe(
        "POST",
        "/products",
        {"name": name, "metadata[wave]": "wave3", "metadata[key]": key},
    )["id"]


def ensure_price(product_id: str, amount: int, interval: str | None, nick: str) -> str:
    listed = stripe("GET", f"/prices?product={product_id}&active=true&limit=100")
    for p in listed.get("data", []):
        if p.get("unit_amount") != amount:
            continue
        rec = p.get("recurring") or {}
        if interval and rec.get("interval") == interval:
            return p["id"]
        if not interval and not p.get("recurring"):
            return p["id"]
    data = {
        "product": product_id,
        "unit_amount": str(amount),
        "currency": "eur",
        "nickname": nick,
        "metadata[wave]": "wave3",
    }
    if interval:
        data["recurring[interval]"] = interval
        data["recurring[interval_count]"] = "1"
    return stripe("POST", "/prices", data)["id"]


def ensure_plink(price_id: str, product_name: str, tier: str) -> tuple[str, str]:
    safe = urllib.parse.quote(f"{product_name} — {tier}", safe="")[:120]
    data = {
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "after_completion[type]": "redirect",
        "after_completion[redirect][url]": f"{THANK_YOU}?product={safe}",
        "allow_promotion_codes": "true",
        "billing_address_collection": "auto",
        "metadata[wave]": "wave3",
        "metadata[tier]": tier,
    }
    link = stripe("POST", "/payment_links", data)
    return link["id"], link.get("url", "")


def fmt(cents: int, interval: str | None) -> str:
    e = cents // 100
    s = f"€{e:,}".replace(",", ".")
    return f"{s}/mo" if interval else f"{s} einmalig"


PRICING_BLOCK = """
<!-- HIGH-TICKET WAVE3 PRICING — auto-injected -->
<section id="high-ticket-pricing-w3" style="position:relative;z-index:2;padding:72px 1.5rem;background:linear-gradient(180deg,#050508 0%,#12101a 100%);border-top:1px solid rgba(250,204,21,.2)">
  <div style="max-width:1100px;margin:0 auto;text-align:center">
    <div style="display:inline-block;padding:.35rem 1rem;border-radius:999px;background:rgba(34,197,94,.15);border:1px solid rgba(34,197,94,.4);color:#4ade80;font-weight:800;font-size:.8rem;letter-spacing:.06em;margin-bottom:1rem">💰 HIGH-TICKET · JETZT KAUFEN</div>
    <h2 style="font-size:clamp(1.8rem,3vw,2.6rem);font-weight:900;color:#fff;margin:0 0 .75rem">Premium Pläne — sofort starten</h2>
    <p style="color:#a1a1aa;max-width:560px;margin:0 auto 2rem">Sichere Stripe-Zahlung · Rechnung · EU-ready · Keine Billig-Preise</p>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1.25rem;text-align:left">{cards}</div>
  </div>
</section>
"""

CARD = """
<div style="background:#16161f;border:1px solid {border};border-radius:18px;padding:1.75rem;{extra}">
  {badge}
  <div style="color:#a1a1aa;font-weight:700;font-size:.85rem;margin-bottom:.4rem">{tier}</div>
  <div style="font-size:2rem;font-weight:900;color:#fff;margin-bottom:.75rem">{price}</div>
  <a href="{url}" style="display:block;text-align:center;background:{btn};color:#000;font-weight:800;padding:.95rem 1rem;border-radius:10px;text-decoration:none">Jetzt kaufen →</a>
</div>
"""


def inject(folder: str | None, tiers: list[dict]) -> bool:
    if not folder:
        return False
    path = ROOT / "netlify-deploy" / folder / "index.html"
    if not path.exists():
        return False
    html = path.read_text(encoding="utf-8", errors="replace")
    html = re.sub(
        r"<!-- HIGH-TICKET WAVE3 PRICING — auto-injected -->.*?</section>\s*",
        "",
        html,
        flags=re.S,
    )
    cards = []
    for i, t in enumerate(tiers):
        feat = i == min(1, len(tiers) - 1)
        cards.append(
            CARD.format(
                tier=t["tier"],
                price=t["price_label"],
                url=t["url"],
                border="rgba(34,197,94,.55)" if feat else "rgba(255,255,255,.1)",
                extra="box-shadow:0 0 40px rgba(34,197,94,.15)" if feat else "",
                badge=(
                    '<div style="color:#4ade80;font-size:.72rem;font-weight:900;margin-bottom:.5rem">★ BESTSELLER</div>'
                    if feat
                    else ""
                ),
                btn="linear-gradient(135deg,#4ade80,#22c55e)" if feat else "#e4e4e7",
            )
        )
    block = PRICING_BLOCK.format(cards="\n".join(cards))
    idx = html.lower().rfind("</body>")
    if idx >= 0:
        html = html[:idx] + block + "\n" + html[idx:]
    else:
        html += block
    primary = tiers[1]["url"] if len(tiers) > 1 else tiers[0]["url"]
    html = re.sub(r'href="https://buy\.stripe\.com/[^"]+"', f'href="{primary}"', html, count=2)
    path.write_text(html, encoding="utf-8")
    return True


def load_wave2() -> dict:
    p = ROOT / "config" / "high_ticket_wave2.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


def build_money_map(wave2: dict, wave3: dict) -> dict:
    products = {}
    for src in (wave2.get("products") or {}, wave3.get("products") or {}):
        products.update(src)
    featured = []
    for k, p in products.items():
        tiers = p.get("tiers") or []
        feat = tiers[1] if len(tiers) > 1 else (tiers[0] if tiers else {})
        if not feat:
            continue
        featured.append(
            {
                "key": k,
                "name": p.get("name"),
                "price": feat.get("price_label"),
                "url": feat.get("url"),
                "price_id": feat.get("price_id"),
            }
        )
    featured.sort(key=lambda x: x.get("name") or "")
    return {
        "updated": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "count": len(featured),
        "featured": featured,
        "products": products,
    }


def inject_master_dashboard(money_map: dict) -> None:
    path = ROOT / "netlify-deploy" / "master-dashboard" / "index.html"
    if not path.exists():
        return
    html = path.read_text(encoding="utf-8", errors="replace")
    html = re.sub(
        r"<!-- MONEY MAP WAVE3 -->.*?</section>\s*",
        "",
        html,
        flags=re.S,
    )
    rows = []
    for f in money_map.get("featured") or []:
        rows.append(
            f'<a href="{f["url"]}" style="display:flex;justify-content:space-between;gap:1rem;padding:.9rem 1rem;background:#111;border:1px solid #333;border-radius:10px;color:#fff;text-decoration:none;margin-bottom:.5rem">'
            f'<span style="font-weight:700">{f["name"]}</span>'
            f'<span style="color:#4ade80;font-weight:800;white-space:nowrap">{f["price"]} → KAUFEN</span></a>'
        )
    block = (
        '<!-- MONEY MAP WAVE3 -->\n'
        '<section id="money-map" style="padding:48px 1.5rem;background:#0a0a0a">'
        '<div style="max-width:900px;margin:0 auto">'
        '<h2 style="color:#fff;margin-bottom:1rem">💰 Alle High-Ticket Angebote — Jetzt verkaufen</h2>'
        + "\n".join(rows)
        + "</div></section>\n"
    )
    idx = html.lower().rfind("</body>")
    if idx >= 0:
        html = html[:idx] + block + html[idx:]
    else:
        html += block
    path.write_text(html, encoding="utf-8")
    print("master-dashboard money map injected", len(rows), "offers")


def main() -> int:
    results = {"wave": "high_ticket_wave3", "products": {}, "mrr_potential": 0, "one_time_potential": 0}
    env_lines = ["# High-Ticket Wave 3", ""]

    for item in CATALOG:
        print(f"\n=== {item['product']} ===")
        pid = ensure_product(item["product"], item["key"])
        tiers_out = []
        for tier_name, amount, interval in item["tiers"]:
            nick = f"w3_{item['key']}_{tier_name.lower().replace(' ', '_').replace('-', '_')}"
            price_id = ensure_price(pid, amount, interval, nick)
            lid, url = ensure_plink(price_id, item["product"], tier_name)
            label = fmt(amount, interval)
            print(f"  {tier_name:18} {label:18} {url}")
            tiers_out.append(
                {
                    "tier": tier_name,
                    "amount_cents": amount,
                    "interval": interval or "one_time",
                    "price_label": label,
                    "price_id": price_id,
                    "link_id": lid,
                    "url": url,
                }
            )
            env_lines.append(f"PLINK_W3_{item['key'].upper()}_{tier_name.upper().replace(' ','_').replace('-','_')}={url}")
            if interval == "month":
                results["mrr_potential"] += amount // 100
            else:
                results["one_time_potential"] += amount // 100
        results["products"][item["key"]] = {
            "name": item["product"],
            "folder": item.get("folder"),
            "product_id": pid,
            "tiers": tiers_out,
        }
        ok = inject(item.get("folder"), tiers_out)
        print("  inject:", "OK" if ok else "skip")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    ENV_OUT.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    w2 = load_wave2()
    money = build_money_map(w2, results)
    MONEY_MAP.write_text(json.dumps(money, indent=2, ensure_ascii=False), encoding="utf-8")
    inject_master_dashboard(money)

    print(f"\nWave3 MRR sum €{results['mrr_potential']} | one-time €{results['one_time_potential']}")
    print(f"Money map: {money['count']} featured offers → {MONEY_MAP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
