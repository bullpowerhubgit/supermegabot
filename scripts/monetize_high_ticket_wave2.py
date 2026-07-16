#!/usr/bin/env python3
"""
High-Ticket Wave 2 — create Stripe Live products/prices/payment links
and inject buy CTAs into netlify-deploy landing pages.

Minimum tier: €297/mo · Target: €997–€4.997
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
OUT = ROOT / "config" / "high_ticket_wave2.json"
ENV_SNIPPET = ROOT / "config" / "high_ticket_wave2.env"
# also mirror into data/ for local runtime if present
OUT_DATA = ROOT / "data" / "high_ticket_wave2.json"
ENV_DATA = ROOT / "data" / "high_ticket_wave2.env"

# ── Load .env ────────────────────────────────────────────────────────────────
for p in (ROOT / ".env", ROOT.parent / ".env"):
    if not p.exists():
        continue
    for line in p.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

KEY = (os.getenv("STRIPE_SECRET_KEY_FULL") or os.getenv("STRIPE_SECRET_KEY") or "").strip()
if not KEY.startswith("sk_live_"):
    print("ERROR: need sk_live_ key", file=sys.stderr)
    sys.exit(1)

THANK_YOU = os.getenv("STRIPE_THANK_YOU_URL", "https://ineedit.com.co/pages/danke")

# folder → high-ticket catalog (amount in cents)
CATALOG = [
    {
        "key": "steuercockpit",
        "folder": "steuercockpit",
        "product": "SteuercockPit Pro — KI-Steuer & Buchhaltung",
        "tiers": [
            ("Starter", 49700, "month"),
            ("Business", 99700, "month"),
            ("Agency", 249700, "month"),
        ],
    },
    {
        "key": "shopify_brutal",
        "folder": "shopify-brutal-tuning",
        "product": "Shopify Brutal Tuning — Performance Empire",
        "tiers": [
            ("Starter", 49700, "month"),
            ("Pro", 99700, "month"),
            ("Enterprise", 249700, "month"),
        ],
    },
    {
        "key": "shopify_acq",
        "folder": "shopify-acquisition-engine",
        "product": "Shopify Acquisition Engine — Growth OS",
        "tiers": [
            ("Starter", 49700, "month"),
            ("Pro", 99700, "month"),
            ("Scale", 249700, "month"),
        ],
    },
    {
        "key": "telegram_agency",
        "folder": "telegram-bot",
        "product": "Telegram Marketing Bot — Agency Suite",
        "tiers": [
            ("Starter", 29700, "month"),
            ("Pro", 79700, "month"),
            ("Agency", 199700, "month"),
        ],
    },
    {
        "key": "gumroad_discord",
        "folder": "gumroad-discord",
        "product": "Gumroad Discord Automation Suite",
        "tiers": [
            ("Starter", 29700, "month"),
            ("Pro", 79700, "month"),
            ("Agency", 149700, "month"),
        ],
    },
    {
        "key": "icomeauto",
        "folder": "icomeauto",
        "product": "IcomeAuto — Passive Income OS",
        "tiers": [
            ("Starter", 49700, "month"),
            ("Pro", 99700, "month"),
            ("Empire", 299700, "month"),
        ],
    },
    {
        "key": "launcher",
        "folder": "launcher",
        "product": "BullPower Launcher — All-Tools Command Center",
        "tiers": [
            ("Pro", 99700, "month"),
            ("Business", 299700, "month"),
            ("Empire", 499700, "month"),
        ],
    },
    {
        "key": "lead_capture_pro",
        "folder": "lead-capture",
        "product": "Lead Capture & Shop Audit Pro",
        "tiers": [
            ("Audit DFY", 49700, None),  # one-time
            ("Retainer", 99700, "month"),
            ("Agency", 249700, "month"),
        ],
    },
    {
        "key": "autoincome_ai",
        "folder": "autoincome-ai",
        "product": "AutoIncome AI — Passive Income Machine",
        "tiers": [
            ("Starter", 99700, None),
            ("Pro", 299700, None),
            ("Empire", 499700, None),
        ],
    },
    {
        "key": "bullpower_ai",
        "folder": "bullpower-ai",
        "product": "BullPower AI — KI Business Automation",
        "tiers": [
            ("Starter", 49700, "month"),
            ("Pro", 99700, "month"),
            ("Enterprise", 299700, "month"),
        ],
    },
]


def stripe(method: str, path: str, data: dict | None = None) -> dict:
    url = f"https://api.stripe.com/v1{path}"
    headers = {"Authorization": f"Bearer {KEY}"}
    body = None
    if data is not None:
        # flatten nested for form encoding not needed — flat keys only
        body = urllib.parse.urlencode(data, doseq=True).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:500]
        raise RuntimeError(f"{method} {path} → HTTP {e.code}: {err}") from e


def ensure_product(name: str, metadata: dict) -> str:
    # search active products by name (list first 100)
    listed = stripe("GET", "/products?active=true&limit=100")
    for p in listed.get("data", []):
        if p.get("name") == name:
            return p["id"]
    data = {"name": name, "metadata[wave]": "high_ticket_wave2"}
    for k, v in metadata.items():
        data[f"metadata[{k}]"] = v
    prod = stripe("POST", "/products", data)
    return prod["id"]


def ensure_price(product_id: str, amount: int, interval: str | None, nickname: str) -> str:
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
        "nickname": nickname,
        "metadata[wave]": "high_ticket_wave2",
    }
    if interval:
        data["recurring[interval]"] = interval
        data["recurring[interval_count]"] = "1"
    price = stripe("POST", "/prices", data)
    return price["id"]


def ensure_payment_link(price_id: str, product_name: str, tier: str) -> tuple[str, str]:
    # Always create a fresh payment link (idempotent enough via local cache)
    from urllib.parse import quote

    safe = quote(f"{product_name} — {tier}", safe="")[:120]
    redirect = f"{THANK_YOU}?product={safe}"
    data = {
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "after_completion[type]": "redirect",
        "after_completion[redirect][url]": redirect,
        "allow_promotion_codes": "true",
        "billing_address_collection": "auto",
        "metadata[wave]": "high_ticket_wave2",
        "metadata[tier]": tier,
    }
    link = stripe("POST", "/payment_links", data)
    return link["id"], link.get("url", "")


def fmt_price(cents: int, interval: str | None) -> str:
    euros = cents // 100
    if interval:
        return f"€{euros:,}/mo".replace(",", ".")
    return f"€{euros:,}".replace(",", ".") + " einmalig"


PRICING_BLOCK = """
<!-- HIGH-TICKET WAVE2 PRICING — auto-injected -->
<section id="high-ticket-pricing" style="position:relative;z-index:2;padding:72px 1.5rem;background:linear-gradient(180deg,#0a0a0f 0%,#12101c 100%);border-top:1px solid rgba(255,255,255,.08)">
  <div style="max-width:1100px;margin:0 auto;text-align:center">
    <div style="display:inline-block;padding:.35rem 1rem;border-radius:999px;background:rgba(250,204,21,.12);border:1px solid rgba(250,204,21,.35);color:#facc15;font-weight:800;font-size:.8rem;letter-spacing:.06em;margin-bottom:1rem">PREMIUM · HIGH-TICKET</div>
    <h2 style="font-size:clamp(1.8rem,3vw,2.6rem);font-weight:900;color:#fff;margin:0 0 .75rem">Wähle deinen Plan</h2>
    <p style="color:#a1a1aa;max-width:560px;margin:0 auto 2rem;line-height:1.6">Keine Billig-Preise. Premium Setup, Support und Automatisierung — für ernsthafte Betreiber.</p>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1.25rem;text-align:left">
      {cards}
    </div>
    <p style="margin-top:1.5rem;color:#71717a;font-size:.85rem">Sichere Zahlung via Stripe · 30-Tage Fair-Use · Rechnung / EU-VAT ready</p>
  </div>
</section>
"""

CARD = """
      <div style="background:#16161f;border:1px solid {border};border-radius:18px;padding:1.75rem;position:relative;{extra}">
        {badge}
        <div style="color:#a1a1aa;font-weight:700;font-size:.85rem;margin-bottom:.4rem">{tier}</div>
        <div style="font-size:2rem;font-weight:900;color:#fff;margin-bottom:.75rem">{price_label}</div>
        <a href="{url}" style="display:block;text-align:center;background:{btn_bg};color:#000;font-weight:800;padding:.95rem 1rem;border-radius:10px;text-decoration:none">Jetzt starten →</a>
      </div>
"""


def inject_pricing(html_path: Path, tiers_data: list[dict]) -> bool:
    if not html_path.exists():
        return False
    html = html_path.read_text(encoding="utf-8", errors="replace")
    # remove previous injection
    html = re.sub(
        r"<!-- HIGH-TICKET WAVE2 PRICING — auto-injected -->.*?</section>\s*",
        "",
        html,
        flags=re.S,
    )
    cards = []
    for i, t in enumerate(tiers_data):
        featured = i == 1 or (len(tiers_data) == 1)
        cards.append(
            CARD.format(
                tier=t["tier"],
                price_label=t["price_label"],
                url=t["url"],
                border="rgba(250,204,21,.55)" if featured else "rgba(255,255,255,.1)",
                extra="box-shadow:0 0 40px rgba(250,204,21,.12)" if featured else "",
                badge=(
                    '<div style="position:absolute;top:-12px;right:16px;background:linear-gradient(135deg,#facc15,#f59e0b);color:#000;font-size:.72rem;font-weight:900;padding:.25rem .7rem;border-radius:999px">BELIEBT</div>'
                    if featured
                    else ""
                ),
                btn_bg="linear-gradient(135deg,#facc15,#f59e0b)" if featured else "#e4e4e7",
            )
        )
    block = PRICING_BLOCK.format(cards="\n".join(cards))
    if "</body>" in html.lower():
        # case-sensitive replace last body
        idx = html.lower().rfind("</body>")
        html = html[:idx] + block + "\n" + html[idx:]
    else:
        html += "\n" + block
    # also rewrite cheap CTA hrefs that point to old low-ticket or #pricing
    for t in tiers_data:
        # first tier as default CTA if href is # or empty buy
        pass
    # Default primary CTA: middle tier url
    primary = tiers_data[1]["url"] if len(tiers_data) > 1 else tiers_data[0]["url"]
    # Replace common placeholder CTAs
    html = re.sub(
        r'href="https://buy\.stripe\.com/[^"]+"',
        f'href="{primary}"',
        html,
        count=3,
    )
    html_path.write_text(html, encoding="utf-8")
    return True


def main() -> int:
    results = {"wave": "high_ticket_wave2", "products": {}, "mrr_potential": 0, "one_time_potential": 0}
    env_lines = ["# High-Ticket Wave 2 — auto-generated", ""]

    for item in CATALOG:
        print(f"\n=== {item['product']} ===")
        pid = ensure_product(item["product"], {"key": item["key"], "folder": item["folder"]})
        print(f"  product {pid}")
        tier_out = []
        for tier_name, amount, interval in item["tiers"]:
            nickname = f"{item['key']}_{tier_name.lower().replace(' ', '_')}"
            price_id = ensure_price(pid, amount, interval, nickname)
            link_id, url = ensure_payment_link(price_id, item["product"], tier_name)
            label = fmt_price(amount, interval)
            print(f"  {tier_name:12} {label:18} {price_id} → {url}")
            tier_out.append(
                {
                    "tier": tier_name,
                    "amount_cents": amount,
                    "interval": interval or "one_time",
                    "price_label": label,
                    "price_id": price_id,
                    "link_id": link_id,
                    "url": url,
                }
            )
            env_key = f"PLINK_{item['key'].upper()}_{tier_name.upper().replace(' ', '_')}"
            env_lines.append(f"{env_key}={url}")
            env_lines.append(f"STRIPE_PRICE_{item['key'].upper()}_{tier_name.upper().replace(' ', '_')}={price_id}")
            if interval == "month":
                results["mrr_potential"] += amount // 100
            else:
                results["one_time_potential"] += amount // 100

        results["products"][item["key"]] = {
            "name": item["product"],
            "folder": item["folder"],
            "product_id": pid,
            "tiers": tier_out,
        }

        # inject into landing page
        html_path = ROOT / "netlify-deploy" / item["folder"] / "index.html"
        ok = inject_pricing(html_path, tier_out)
        print(f"  html inject: {'OK' if ok else 'SKIP'} ({html_path.name if ok else 'missing'})")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(results, indent=2, ensure_ascii=False)
    env_body = "\n".join(env_lines) + "\n"
    OUT.write_text(payload, encoding="utf-8")
    ENV_SNIPPET.write_text(env_body, encoding="utf-8")
    try:
        OUT_DATA.parent.mkdir(parents=True, exist_ok=True)
        OUT_DATA.write_text(payload, encoding="utf-8")
        ENV_DATA.write_text(env_body, encoding="utf-8")
    except Exception:
        pass
    print(f"\nWrote {OUT}")
    print(f"Wrote {ENV_SNIPPET}")
    print(f"MRR potential (sum of all monthly tiers): €{results['mrr_potential']}")
    print(f"One-time potential: €{results['one_time_potential']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
