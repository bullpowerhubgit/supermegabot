#!/usr/bin/env python3
"""
Ersetzt alte Stripe-Links (4F42u) in allen 17 Netlify-Seiten
mit den neuen High-Ticket Links (4F465) aus stripe_ht_links.json.
Deployt danach via netlify CLI zu Konto 1.
"""
import json, re, subprocess, time
from pathlib import Path

BASE  = Path("/Users/rudolfsarkany/supermegabot/netlify-deploy")
LINKS = json.loads(Path("/Users/rudolfsarkany/supermegabot/config/stripe_ht_links.json").read_text())

# dirname → (netlify_site_id, stripe_key)
SITES = [
    ("bullpower-ai",               "2f993068-69c5-4948-902c-6886a18fea02", "BullPower AI"),
    ("bullpower-hub",              "b724d9cd-e19e-4d15-9747-059e8148368f", "BullPower Hub"),
    ("autoincome-ai",              "4d792fed-3c4c-4fd7-8737-46d027365e5e", "AutoIncome AI"),
    ("creatorai-ultra",            "0d38840f-35ef-4ac3-8e39-a0edde921562", "CreatorAI Ultra"),
    ("creatorstudio-pro",          "251bd945-2fc2-40b2-bff5-35d49a5a6c3f", "CreatorStudio Pro"),
    ("cognitive-symphony",         "478872de-d571-4e81-b3fe-4d9b12dd697a", "Cognitive Symphony"),
    ("shopify-brutal-tuning",      "2dba2775-a068-4e4c-9d9f-2a37d48f5761", "Shopify Brutal"),
    ("shopify-acquisition-engine", "cc660686-8075-4f3c-bc8e-07ac7d2eca05", "Shopify Acq Engine"),
    ("shopify-suite",              "1859ba2f-66de-4012-b912-52b46e847810", "Shopify Suite"),
    ("digistore24-suite",          "0d99546c-1813-4820-af6e-8c108968f17b", "Digistore24 Suite"),
    ("steuercockpit",              "3a80f111-7a16-48c4-bb9c-ad4b7fbf907f", "SteuercockPit"),
    ("telegram-bot",               "5fdbef63-e63e-4f57-ab27-770328ac9461", "Telegram Bot"),
    ("icomeauto",                  "713b6e9f-4388-4c5a-a339-29ba8b5cfb2b", "IcomeAuto"),
    ("launcher",                   "5ea6c29b-c012-47c0-96d1-e1fcd9e813fa", "Launcher"),
    ("lead-capture",               "2c73aa5c-26b3-409f-b0d2-3e62ad441c12", "Lead Capture"),
    ("gumroad-discord",            "b5bcb0f0-cd2f-463e-9c7d-bd87afca4ad1", "Gumroad Discord"),
    ("master-dashboard",           None,                                     "Master Dashboard"),
]


def get_new_links(stripe_key):
    """Neue Stripe-Links für ein Produkt (T1, T2, T3)."""
    tiers = LINKS.get(stripe_key, [])
    return [url for _, url in tiers][:3]


def extract_pricing_links(html):
    """Extrahiert die 3 alten Stripe-Links aus der Pricing-Section in Reihenfolge."""
    section_match = re.search(r'<section class="pricing-section".*?</section>', html, re.DOTALL)
    if not section_match:
        return []
    section = section_match.group(0)
    return re.findall(r'https://buy\.stripe\.com/[a-zA-Z0-9]+', section)


def update_links(html, old_links, new_links):
    """Ersetzt alte Links global durch neue (alle Vorkommen: Header, Hero, Pricing, Footer)."""
    for old, new in zip(old_links, new_links):
        html = html.replace(old, new)
    return html


def netlify_deploy(dirname, site_id):
    """Deployt das Verzeichnis zu Netlify."""
    cmd = ["netlify", "deploy", "--prod", "--dir", str(BASE / dirname), "--site", site_id]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode == 0:
        url_match = re.search(r'Website URL:\s+(https://[^\s]+)', r.stdout + r.stderr)
        url = url_match.group(1) if url_match else "deployed"
        return True, url
    return False, (r.stderr or r.stdout)[:200]


def create_site_and_deploy(dirname):
    """Erstellt neue Netlify-Site und deployt."""
    name = f"master-dashboard-hub"
    r = subprocess.run(
        ["netlify", "sites:create", "--name", name, "--account-slug", "bullpowerhubgit"],
        capture_output=True, text=True, timeout=30
    )
    site_id_match = re.search(r'Site ID:\s*([a-f0-9-]{36})', r.stdout + r.stderr)
    if site_id_match:
        sid = site_id_match.group(1)
        return netlify_deploy(dirname, sid)
    return False, f"Site-Erstellung fehlgeschlagen: {(r.stdout+r.stderr)[:200]}"


def main():
    updated = 0
    deployed = 0
    errors = []

    for dirname, site_id, stripe_key in SITES:
        html_path = BASE / dirname / "index.html"
        if not html_path.exists():
            print(f"  ⚠ {dirname}: index.html fehlt — skip")
            continue

        html = html_path.read_text(encoding="utf-8")
        new_links = get_new_links(stripe_key)
        if len(new_links) < 3:
            print(f"  ⚠ {dirname}: weniger als 3 neue Links in JSON")
            continue

        old_links = extract_pricing_links(html)
        if not old_links:
            print(f"  ⚠ {dirname}: keine Stripe-Links in Pricing-Section gefunden")
            # trotzdem deployen mit bestehendem HTML
        else:
            # Duplikate entfernen, Reihenfolge bewahren
            seen = set()
            unique_old = [l for l in old_links if not (l in seen or seen.add(l))]

            already_new = all("4F465" in l or "4F466" in l for l in unique_old)
            if already_new:
                print(f"  ✓ {dirname}: Links bereits aktuell")
            else:
                html_new = update_links(html, unique_old, new_links)
                if html_new != html:
                    html_path.write_text(html_new, encoding="utf-8")
                    print(f"  ✅ {dirname}: {len(unique_old)} Links aktualisiert")
                    updated += 1
                else:
                    print(f"  ℹ {dirname}: keine Änderungen (Links schon korrekt?)")

        # Deploy
        print(f"     🚀 Deploy {dirname} → ", end="", flush=True)
        if site_id:
            ok, info = netlify_deploy(dirname, site_id)
        else:
            ok, info = create_site_and_deploy(dirname)

        if ok:
            print(f"{info}")
            deployed += 1
        else:
            print(f"❌ {info}")
            errors.append((dirname, info))
        time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"📊 Ergebnis: {updated} Links aktualisiert, {deployed}/{len(SITES)} Sites deployed")
    if errors:
        print(f"\n❌ Fehler ({len(errors)}):")
        for d, e in errors:
            print(f"   {d}: {e}")
    else:
        print("✅ Alle Sites erfolgreich deployed!")


if __name__ == "__main__":
    main()
