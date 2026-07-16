#!/usr/bin/env python3
"""
HT Master Script — Stripe + HTML + Deploy (parallel)
1. Stripe: HT-Produkte + Preise + Payment Links erstellen
2. HTML: alle Sites mit project-spezifischen Links updaten
3. Deploy: Netlify + Vercel parallel
"""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import urllib.request, urllib.parse, urllib.error

BASE    = Path(__file__).parent.parent / "netlify-deploy"
ENV     = Path(__file__).parent.parent / ".env"

# ─── ENV LADEN ──────────────────────────────────────────────
def _env():
    e = {}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            e[k.strip()] = v.strip().strip('"')
    return e

ENV_VARS = _env()
STRIPE_KEY = ENV_VARS.get("STRIPE_SECRET_KEY", "")

# ─── STRIPE HELPER ──────────────────────────────────────────
def stripe(method, path, data=None):
    url = f"https://api.stripe.com/v1{path}"
    auth = (STRIPE_KEY + ":").encode()
    import base64
    headers = {
        "Authorization": "Basic " + base64.b64encode(auth).decode(),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

# ─── PROJEKT-DEFINITIONEN ────────────────────────────────────
PROJECTS = [
    # key, name, dir, netlify_site_id, vercel_proj, category
    ("autoincome-ai",           "AutoIncome AI — Passive Income Machine",       "autoincome-ai",              "4d792fed-3c4c-4fd7-8737-46d027365e5e", "autoincome-ai",           "income"),
    ("bullpower-hub",           "BullPower Hub — B2B Growth Command Center",    "bullpower-hub",              "b724d9cd-e19e-4d15-9747-059e8148368f", "bullpower-hub",           "b2b"),
    ("shopify-acquisition-engine","Shopify Acquisition Engine — Growth OS",     "shopify-acquisition-engine", "cc660686-8075-4f3c-bc8e-07ac7d2eca05", "shopify-acquisition-engine","shopify"),
    ("shopify-brutal-tuning",   "Shopify Brutal Tuning — Performance Empire",   "shopify-brutal-tuning",      "2dba2775-a068-4e4c-9d9f-2a37d48f5761", "shopify-brutal-tuning",   "shopify"),
    ("shopify-suite",           "Shopify Automation Suite — Full OS",           "shopify-suite",              "1859ba2f-66de-4012-b912-52b46e847810", "shopify-suite",           "shopify"),
    ("cognitive-symphony",      "Cognitive Symphony — KI Automation OS",        "cognitive-symphony",         "478872de-d571-4e81-b3fe-4d9b12dd697a", "cognitive-symphony",      "ai"),
    ("creatorai-ultra",         "CreatorAI Ultra — KI Content Empire",          "creatorai-ultra",            "0d38840f-35ef-4ac3-8e39-a0edde921562", "creatorai-ultra",         "creator"),
    ("creatorstudio-pro",       "CreatorStudio Pro — Premium Content Engine",   "creatorstudio-pro",          "251bd945-2fc2-40b2-bff5-35d49a5a6c3f", "creatorstudio-pro",       "creator"),
    ("digistore24-suite",       "Digistore24 Suite — Affiliate Empire",         "digistore24-suite",          "0d99546c-1813-4820-af6e-8c108968f17b", "digistore24-suite",       "ds24"),
    ("gumroad-discord",         "Gumroad Discord Bot — Community Monetization", "gumroad-discord",            "b5bcb0f0-cd2f-463e-9c7d-bd87afca4ad1", "gumroad-discord",         "community"),
    ("telegram-bot",            "Telegram Marketing Bot — Agency Suite",        "telegram-bot",               "5fdbef63-e63e-4f57-ab27-770328ac9461", "telegram-bot",            "marketing"),
    ("launcher",                "BullPower Launcher — Launch Command Center",   "launcher",                   "5ea6c29b-c012-47c0-96d1-e1fcd9e813fa", "launcher",                "launch"),
    ("lead-capture",            "Lead Capture Pro — High-Ticket Pipeline",      "lead-capture",               "2c73aa5c-26b3-409f-b0d2-3e62ad441c12", "lead-capture",            "b2b"),
    ("steuercockpit",           "Steuer-Cockpit Pro — KI Buchhaltung DACH",     "steuercockpit",              "3a80f111-7a16-48c4-bb9c-ad4b7fbf907f", "steuercockpit",           "finance"),
    ("icomeauto",               "IcomeAuto — Passive Income OS",                "icomeauto",                  "d43a1ef5-bce6-4792-95a6-03711233c02e", "icomeauto",               "income"),
    ("bullpower-ai",            "BullPower AI Tools — KI Business Suite",       "bullpower-ai",               "2f993068-69c5-4948-902c-6886a18fea02", "bullpower-ai",            "ai"),
    ("aiitec-all",              "AIITEC All-in-One — Full Stack Automation",    "aiitec-all",                 None,                                    "aiitec-all",              "b2b"),
    ("aiitec-pinterest-portal", "AIITEC Pinterest Portal — Traffic Engine",     "aiitec-pinterest-portal",    "78eae41d-6e24-4648-9ebe-9b30ed95dd84", "aiitec-pinterest-portal", "marketing"),
]

# Tier-Preise in Cent
TIERS = [
    ("Starter",         99700,  "Einstieg"),
    ("Pro",             299700, "Beliebteste Wahl"),
    ("Enterprise DFY",  499700, "Done-For-You"),
]

# ─── STRIPE: PRODUKTE + LINKS ERSTELLEN ──────────────────────
def stripe_create_ht_products(proj_key, prod_name):
    """Erstellt 3 HT-Produkte + Preise + Payment Links für ein Projekt."""
    links = {}
    for tier, cents, tagline in TIERS:
        full_name = f"{prod_name} — {tier}"
        # Produkt erstellen
        prod = stripe("POST", "/products", {
            "name": full_name,
            "description": f"{tagline} · High-Ticket E-Commerce Automation",
            "metadata[project]": proj_key,
            "metadata[tier]": tier.lower().replace(" ", "_"),
            "metadata[ht_version]": "2",
        })
        prod_id = prod.get("id", "")
        if not prod_id:
            print(f"    ⚠️  Produkt fehlgeschlagen: {full_name}")
            continue

        # Preis erstellen
        price = stripe("POST", "/prices", {
            "product": prod_id,
            "unit_amount": cents,
            "currency": "eur",
            "metadata[tier]": tier.lower().replace(" ", "_"),
        })
        price_id = price.get("id", "")
        if not price_id:
            print(f"    ⚠️  Preis fehlgeschlagen: {full_name}")
            continue

        # Payment Link erstellen
        pl = stripe("POST", "/payment_links", {
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "after_completion[type]": "redirect",
            "after_completion[redirect][url]": f"https://bullpower-hub-portal.netlify.app/danke",
            "metadata[project]": proj_key,
            "metadata[tier]": tier.lower().replace(" ", "_"),
        })
        pl_url = pl.get("url", "")
        if pl_url:
            links[tier] = pl_url
            price_eur = f"€{cents//100:,}".replace(",", ".")
            print(f"    ✅ {tier} {price_eur} → {pl_url}")
        else:
            print(f"    ⚠️  Payment Link fehlgeschlagen: {tier} | {pl.get('error', {}).get('message','')}")

    return links

# ─── HTML PATCH: PRICING LINKS ERSETZEN ──────────────────────

PRICING_BLOCK_TPL = """
        <div class="tier-card">
            <div class="tier-name">Starter</div>
            <div class="tier-price">€997<span class="tier-period"> einmalig</span></div>
            <ul class="tier-features">
                <li>✓ Vollzugang — sofort startklar</li>
                <li>✓ Onboarding-Call (60 Min)</li>
                <li>✓ Alle Core-Automatisierungen aktiv</li>
                <li>✓ KI-Analyse deines Business</li>
                <li>✓ Dashboard + Echtzeit-Reporting</li>
                <li>✓ Telegram-Alerts für alle Events</li>
                <li>✓ E-Mail Support (48h Antwortzeit)</li>
                <li>✓ 30 Tage Geld-zurück-Garantie</li>
                <li>✓ Lebenslanger Zugang (einmalig)</li>
            </ul>
            <a href="{starter_url}" class="tier-cta" target="_blank">Jetzt starten →</a>
        </div>

        <div class="tier-card popular">
            <div class="popular-badge">⭐ Beliebteste Wahl</div>
            <div class="tier-name">Pro</div>
            <div class="tier-price">€2.997<span class="tier-period"> einmalig</span></div>
            <ul class="tier-features">
                <li>✓ Alles aus Starter</li>
                <li>✓ Onboarding-Call (90 Min)</li>
                <li>✓ Monatliche Strategy-Calls</li>
                <li>✓ Alle Premium-Features freigeschaltet</li>
                <li>✓ Autonome KI-Agenten aktiv</li>
                <li>✓ Multi-Kanal Automation (7+ Kanäle)</li>
                <li>✓ A/B Testing Engine</li>
                <li>✓ Competitor Intelligence</li>
                <li>✓ Priority Support (12h Antwortzeit)</li>
                <li>✓ Bonus-Stack ({bonus_val} Wert) kostenlos</li>
                <li>✓ 30 Tage Geld-zurück-Garantie</li>
            </ul>
            <a href="{pro_url}" class="tier-cta" target="_blank">Pro sichern →</a>
        </div>

        <div class="tier-card">
            <div class="tier-name">Enterprise DFY</div>
            <div class="tier-price">€4.997<span class="tier-period"> einmalig</span></div>
            <ul class="tier-features">
                <li>✓ Alles aus Pro</li>
                <li>✓ Done-For-You Setup (5 Tage)</li>
                <li>✓ Dedicated Success Manager</li>
                <li>✓ Wöchentliche Strategy-Calls</li>
                <li>✓ Custom KI-Agenten für dein Business</li>
                <li>✓ Custom API-Integrationen</li>
                <li>✓ 4h Emergency Support SLA</li>
                <li>✓ Unbegrenzte User + Shops</li>
                <li>✓ White-Label Option verfügbar</li>
                <li>✓ EU AI Act Compliance Paket</li>
                <li>✓ 30 Tage Geld-zurück-Garantie</li>
            </ul>
            <a href="{enterprise_url}" class="tier-cta" target="_blank">Enterprise anfragen →</a>
        </div>"""

BONUS_VALS = {
    "income":    "€1.191",
    "b2b":       "€2.191",
    "shopify":   "€1.491",
    "ai":        "€1.491",
    "creator":   "€1.491",
    "ds24":      "€1.491",
    "community": "€888",
    "marketing": "€1.191",
    "launch":    "€1.388",
    "finance":   "€1.388",
    "default":   "€1.491",
}

def patch_html_pricing(html, links, category="default"):
    """Ersetzt die pricing-grid Inhalte mit neuen Links + Features."""
    starter_url    = links.get("Starter",        "#preise")
    pro_url        = links.get("Pro",            "#preise")
    enterprise_url = links.get("Enterprise DFY", "#preise")
    bonus_val      = BONUS_VALS.get(category, BONUS_VALS["default"])

    new_block = PRICING_BLOCK_TPL.format(
        starter_url=starter_url, pro_url=pro_url,
        enterprise_url=enterprise_url, bonus_val=bonus_val,
    )

    # Ersetze Inhalt innerhalb <div class="pricing-grid">...</div>
    html = re.sub(
        r'(<div class="pricing-grid">)(.*?)(</div>\s*(?:</div>\s*)?<div class="pricing-guarantee">)',
        lambda m: m.group(1) + new_block + "\n" + m.group(3),
        html, flags=re.DOTALL, count=1,
    )
    return html

# ─── DEPLOY ─────────────────────────────────────────────────

def _run(cmd, timeout=300):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stderr[:200] if r.returncode != 0 else ""
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)

def deploy_netlify(site_id, dir_path):
    if not site_id:
        return False, "no site_id"
    ok, err = _run(["netlify", "deploy", "--prod",
                    f"--dir={dir_path}", f"--site={site_id}"], timeout=120)
    return ok, err

def deploy_vercel(vercel_proj, dir_path):
    ok, err = _run(["vercel", "--prod", "--yes", "--cwd", str(dir_path)], timeout=300)
    return ok, err

def deploy_site(proj_key, netlify_id, vercel_proj, dir_name):
    d = BASE / dir_name
    results = {}
    if netlify_id:
        ok, err = deploy_netlify(netlify_id, d)
        results["netlify"] = (ok, err)
    ok, err = deploy_vercel(vercel_proj, d)
    results["vercel"] = (ok, err)
    return proj_key, results

# ─── MAIN ────────────────────────────────────────────────────

def main():
    do_stripe = "--stripe" in sys.argv or "-s" in sys.argv or "--all" in sys.argv
    do_html   = "--html"   in sys.argv or "-h" in sys.argv or "--all" in sys.argv
    do_deploy = "--deploy" in sys.argv or "-d" in sys.argv or "--all" in sys.argv

    if not any([do_stripe, do_html, do_deploy]):
        print("Usage: python3 ht_master.py [--stripe] [--html] [--deploy] [--all]")
        print("  --stripe   Stripe HT-Produkte + Payment Links erstellen")
        print("  --html     HTML mit Links updaten")
        print("  --deploy   Netlify + Vercel parallel deployen")
        print("  --all      Alles")
        sys.exit(0)

    # ── STRIPE ──
    all_links = {}  # proj_key → {tier: url}
    if do_stripe:
        print(f"\n{'='*60}\nSTRIPE — HT-Produkte + Payment Links\n{'='*60}")
        if not STRIPE_KEY.startswith("sk_live_51Tg1U"):
            print("❌ STRIPE_SECRET_KEY fehlt oder falsches Konto!")
            sys.exit(1)
        for (key, name, dir_name, nlfy_id, vcl, cat) in PROJECTS:
            print(f"\n🔧 {name}")
            links = stripe_create_ht_products(key, name)
            all_links[key] = links
        # Speichere Links als JSON für HTML-Step
        links_file = Path(__file__).parent / "ht_payment_links.json"
        links_file.write_text(json.dumps(all_links, indent=2, ensure_ascii=False))
        print(f"\n✅ Payment Links gespeichert → {links_file}")

    # ── HTML ──
    if do_html:
        print(f"\n{'='*60}\nHTML — Pricing mit Payment Links updaten\n{'='*60}")
        # Links laden falls nur --html
        if not all_links:
            lf = Path(__file__).parent / "ht_payment_links.json"
            if lf.exists():
                all_links = json.loads(lf.read_text())
        for (key, name, dir_name, nlfy_id, vcl, cat) in PROJECTS:
            html_path = BASE / dir_name / "index.html"
            if not html_path.exists():
                print(f"  ⚠️  {dir_name}/index.html fehlt")
                continue
            html = html_path.read_text(encoding="utf-8")
            links = all_links.get(key, {})
            html = patch_html_pricing(html, links, cat)
            html_path.write_text(html, encoding="utf-8")
            has_links = len(links) > 0
            print(f"  ✅ {name[:45]} {'(echte Links)' if has_links else '(Fallback-Links)'}")

    # ── DEPLOY (parallel) ──
    if do_deploy:
        print(f"\n{'='*60}\nDEPLOY — Netlify + Vercel parallel\n{'='*60}")
        tasks = [(k, nid, vcl, d) for k, _, d, nid, vcl, _ in PROJECTS]
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(deploy_site, k, nid, vcl, d): k
                       for k, nid, vcl, d in tasks}
            for fut in as_completed(futures):
                proj_key, res = fut.result()
                name = next(n for k, n, *_ in PROJECTS if k == proj_key)
                n_ok, n_err = res.get("netlify", (None, ""))
                v_ok, v_err = res.get("vercel",  (False, ""))
                n_sym = "✅" if n_ok else ("⚪" if n_ok is None else f"❌({n_err[:30]})")
                v_sym = "✅" if v_ok else f"❌({v_err[:30]})"
                print(f"  {name[:40]:42} Netlify:{n_sym}  Vercel:{v_sym}")

    print("\n✅ Fertig.")

if __name__ == "__main__":
    main()
