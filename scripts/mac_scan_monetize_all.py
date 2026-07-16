#!/usr/bin/env python3
"""
Mac Scan + Instant Monetize — NUR bullpowersrtkennels Stripe
=============================================================
1) Scannt bekannte Pfade nach monetarisierbaren Assets
2) Erstellt fehlende Products/Prices/Payment Links auf Stripe
3) Schreibt Fundliste + Live-Links nach data/
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from modules.stripe_key_resolver import (  # noqa: E402
    assert_bullpower_only,
    enforce_bullpower_only,
)

DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

# Catalog: name, cents, interval, description, landing
CATALOG = [
    ("SteuercockPit Pro Monthly", 2900, "month", "KI-Steuer & Abo-Audit DE/AT", "https://steuercockpit.vercel.app/"),
    ("SteuercockPit Lifetime", 14900, "one_time", "Lifetime SteuercockPit", "https://steuercockpit.vercel.app/"),
    ("iComeAuto Starter", 2900, "month", "Passive Income Automation", "https://autoincome-ai.vercel.app/"),
    ("iComeAuto Pro", 7900, "month", "Passive Income Pro", "https://autoincome-ai.vercel.app/"),
    ("Shopify Acquisition Starter", 4900, "month", "Shopify Produkt-Acquisition", "https://shopify-acquisition-engine.vercel.app/"),
    ("Shopify Acquisition Pro", 9900, "month", "Shopify Acquisition Pro", "https://shopify-acquisition-engine.vercel.app/"),
    ("Shopify Acquisition Enterprise", 29900, "month", "Shopify Acquisition Enterprise", "https://shopify-acquisition-engine.vercel.app/"),
    ("SEO Turbo Tools Starter", 2900, "month", "SEO Traffic Engine", "https://seo-turbo-tools-production.up.railway.app/"),
    ("SEO Turbo Tools Pro", 7900, "month", "SEO Turbo Pro", "https://seo-turbo-tools-production.up.railway.app/"),
    ("CreatorAI Ultra Creator", 1900, "month", "KI Content Creator", "https://creatorai-ultra.vercel.app/"),
    ("CreatorAI Ultra Pro", 4900, "month", "KI Content Pro", "https://creatorai-ultra.vercel.app/"),
    ("CreatorAI Ultra Agency", 9900, "month", "KI Content Agency", "https://creatorai-ultra.vercel.app/"),
    ("BullPower Hub Portal", 9900, "month", "BullPower Hub Bundle Entry", "https://bullpower-hub.vercel.app/"),
    ("E-Commerce Autopilot Stack", 14900, "month", "SAE+SEO+Analytics Bundle", "https://bullpower-hub.vercel.app/"),
    ("Digistore24 Pro Suite Monthly", 3900, "month", "DS24 Affiliate Automation", "https://digistore24-suite.vercel.app/"),
    ("Cognitive Symphony Monthly", 2900, "month", "DS24 Automation OS", "https://cognitive-symphony.vercel.app/"),
    ("Analytics Marketing Pro Monthly", 4900, "month", "Marketing Intelligence", "https://bullpower-ai.vercel.app/"),
    ("RudiMaster Bot Premium", 1900, "month", "Telegram Command Center", "https://supermegabot-production.up.railway.app/"),
    ("EU Compliance SaaS Starter", 4900, "month", "EU AI Act Shopify", "https://eu-compliance-saas-production.up.railway.app/"),
    ("EU Compliance SaaS Pro", 14900, "month", "EU AI Act Pro", "https://eu-compliance-saas-production.up.railway.app/"),
    ("AdPoster Engine Access", 3900, "month", "KI Ads Engine", "https://supermegabot-production.up.railway.app/"),
    ("Freelance Gig Engine Pro", 4900, "month", "Fiverr Upwork Automation", "https://supermegabot-production.up.railway.app/"),
    ("CreatorStudio Pro Monthly", 1900, "month", "Creator Studio Pro", "https://creatorstudio-pro.vercel.app/"),
    ("Shopify Brutal Tuning Starter Monthly", 49700, "month", "Shopify Brutal Tuning", "https://shopify-brutal-tuning.vercel.app/"),
]


def stripe_get(key: str, path: str, params: dict | None = None) -> dict:
    url = f"https://api.stripe.com/v1{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


def stripe_post(key: str, path: str, data: dict) -> tuple[dict | None, str | None]:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        f"https://api.stripe.com/v1{path}",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, e.read().decode(errors="ignore")[:400]


def scan_findings() -> dict:
    findings = {
        "sources_checked": [],
        "projects": [],
        "notes": [],
    }
    paths = {
        "supermegabot": ROOT,
        "CascadeProjects": Path.home() / "CascadeProjects",
        "Desktop": Path.home() / "Desktop",
        "Downloads": Path.home() / "Downloads",
        "iCloud": Path.home() / "Library/Mobile Documents/com~apple~CloudDocs",
        "GoogleDrive": Path.home()
        / "Library/CloudStorage/GoogleDrive-bullpowersrtkennels@gmail.com",
        "Maxtor1": Path("/Volumes/Maxtor 1. "),
        "Maxtor2": Path("/Volumes/Maxtor .2"),
        "Maxtor3": Path("/Volumes/Maxtor.3"),
        "claude": Path.home() / ".claude",
        "grok_sessions": Path.home() / ".grok/sessions",
    }
    for label, p in paths.items():
        exists = p.exists()
        findings["sources_checked"].append({"name": label, "path": str(p), "exists": exists})
        if not exists:
            continue
        if label == "CascadeProjects":
            for sub in (
                "01-active-revenue",
                "02-near-monetizable",
                "06-launch-today-priority",
                "MONETIZATION-MAP.md",
                "MONETIZATION_AUDIT_2026.md",
            ):
                sp = p / sub
                findings["projects"].append(
                    {"path": str(sp), "exists": sp.exists(), "tier": "cascade_map"}
                )
        if label == "supermegabot":
            for f in (
                "config/money_map.json",
                "config/high_ticket_wave2.json",
                "config/high_ticket_wave3.json",
            ):
                findings["projects"].append(
                    {"path": str(p / f), "exists": (p / f).exists(), "tier": "catalog"}
                )
    findings["notes"] = [
        "Stripe account locked: bullpowersrtkennels@gmail.com only",
        "Pinterest API still blocked (manual re-submit)",
        "Telegram flood wait may delay blasts",
        "External Maxtor volumes present — generic OS folders, no auto product extract",
    ]
    return findings


def main() -> int:
    enforce_bullpower_only()
    key = assert_bullpower_only()
    print("Stripe key OK:", key[:16], "…")

    findings = scan_findings()
    print("Sources:", sum(1 for s in findings["sources_checked"] if s["exists"]), "/", len(findings["sources_checked"]))

    prods = stripe_get(key, "/products", {"limit": "100", "active": "true"}).get("data", [])
    names = {(p.get("name") or "").lower() for p in prods}
    print("Existing products (page1):", len(prods))

    created = []
    for name, cents, interval, desc, landing in CATALOG:
        if name.lower() in names:
            print("SKIP", name)
            continue
        prod, err = stripe_post(
            key,
            "/products",
            {
                "name": name,
                "description": desc,
                "metadata[source]": "mac_scan_monetize",
                "metadata[account]": "bullpowersrtkennels",
                "metadata[landing]": landing,
            },
        )
        if not prod:
            print("FAIL product", name, err)
            continue
        pr = {
            "product": prod["id"],
            "currency": "eur",
            "unit_amount": str(cents),
        }
        if interval != "one_time":
            pr["recurring[interval]"] = interval
        price, err = stripe_post(key, "/prices", pr)
        if not price:
            print("FAIL price", name, err)
            continue
        plink, err = stripe_post(
            key,
            "/payment_links",
            {
                "line_items[0][price]": price["id"],
                "line_items[0][quantity]": "1",
                "after_completion[type]": "redirect",
                "after_completion[redirect][url]": landing,
                "allow_promotion_codes": "true",
                "metadata[product]": name,
                "metadata[account]": "bullpowersrtkennels",
            },
        )
        if not plink:
            print("FAIL plink", name, err)
            continue
        item = {
            "name": name,
            "url": plink.get("url"),
            "price_id": price["id"],
            "product_id": prod["id"],
            "eur": cents / 100,
            "interval": interval,
            "landing": landing,
        }
        created.append(item)
        names.add(name.lower())
        print("OK", name, plink.get("url"))

    links = stripe_get(key, "/payment_links", {"limit": "100", "active": "true"}).get("data", [])
    report = {
        "account": "bullpowersrtkennels@gmail.com",
        "account_id": "acct_1Tg1U0RJECiV6vSm",
        "findings": findings,
        "created_this_run": created,
        "live_payment_links": [L.get("url") for L in links],
        "live_products": [p.get("name") for p in prods],
        "counts": {
            "created": len(created),
            "products_page": len(prods),
            "links_page": len(links),
        },
    }
    (DATA / "MONETIZE_FINDINGS_AND_LINKS.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    md = [
        "# MONETIZE SCAN + LIVE STRIPE",
        "",
        f"**Konto:** bullpowersrtkennels@gmail.com · `acct_1Tg1U0RJECiV6vSm`",
        f"**Neu erstellt:** {len(created)}",
        f"**Payment Links (Seite):** {len(links)}",
        "",
        "## Neu erstellte Checkouts",
        "",
    ]
    for c in created:
        md.append(f"- **{c['name']}** — €{c['eur']}/{c['interval']} — {c['url']}")
    md += ["", "## Alle aktiven Payment Links (API)", ""]
    for u in report["live_payment_links"]:
        md.append(f"- {u}")
    md += ["", "## Quellen geprüft", ""]
    for s in findings["sources_checked"]:
        mark = "✅" if s["exists"] else "—"
        md.append(f"- {mark} {s['name']}: `{s['path']}`")
    (DATA / "MONETIZE_SCAN_REPORT.md").write_text("\n".join(md), encoding="utf-8")

    print("CREATED", len(created))
    print("REPORT", DATA / "MONETIZE_SCAN_REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
