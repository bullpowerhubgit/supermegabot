#!/usr/bin/env python3
"""
Netlify Deploy — Beide Accounts
================================
Account 1 (bullpowerhubgit): Bestehende Sites updaten
Account 2 (aiitecbuuss): Neue Sites erstellen + deployen
"""
from __future__ import annotations
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = ROOT / "netlify-deploy"

# ── Tokens ────────────────────────────────────────────────────────────────────
TOKEN_BULLPOWER = os.getenv("NETLIFY_AUTH_TOKEN_BULLPOWER") or os.getenv("NETLIFY_AUTH_TOKEN", "")
TOKEN_AIITEC    = os.getenv("NETLIFY_AUTH_TOKEN_AIITEC", "")

# ── Account 1: bekannte Site-IDs (bullpowerhubgit) ───────────────────────────
ACCOUNT1_SITES = {
    "bullpower-ai":              "2f993068-69c5-4948-902c-6886a18fea02",  # bullpower-ai-tools
    "bullpower-hub":             "b724d9cd-e19e-4d15-9747-059e8148368f",  # bullpower-hub-portal
    "cognitive-symphony":        "478872de-d571-4e81-b3fe-4d9b12dd697a",  # cognitive-symphony-ds24
    "creatorai-ultra":           "0d38840f-35ef-4ac3-8e39-a0edde921562",  # creatorai-ultra
    "creatorstudio-pro":         "251bd945-2fc2-40b2-bff5-35d49a5a6c3f",  # creatorstudio-pro
    "autoincome-ai":             "4d792fed-3c4c-4fd7-8737-46d027365e5e",  # autoincome-ai
    "shopify-brutal-tuning":     "2dba2775-a068-4e4c-9d9f-2a37d48f5761",  # shopify-brutal-tuning
    "shopify-acquisition-engine":"cc660686-8075-4f3c-bc8e-07ac7d2eca05",  # shopify-acquisition-engine
    "shopify-suite":             "1859ba2f-66de-4012-b912-52b46e847810",  # shopify-automaton-suite
    "steuercockpit":             "3a80f111-7a16-48c4-bb9c-ad4b7fbf907f",  # bullpower-steuercockpit
    "telegram-bot":              "5fdbef63-e63e-4f57-ab27-770328ac9461",  # telegram-marketing-bot
    "launcher":                  "5ea6c29b-c012-47c0-96d1-e1fcd9e813fa",  # bullpower-launcher
    "digistore24-suite":         "0d99546c-1813-4820-af6e-8c108968f17b",  # digistore24-automation-suite
    "icomeauto":                 "713b6e9f-4388-4c5a-a339-29ba8b5cfb2b",  # bullpower-icomeauto
    "gumroad-discord":           "b5bcb0f0-cd2f-463e-9c7d-bd87afca4ad1",  # gumroad-discord-bot
    "lead-capture":              "2c73aa5c-26b3-409f-b0d2-3e62ad441c12",  # bullpower-lead
}

# ── Account 2: Site-Namen für neue Sites (aiitecbuuss) ────────────────────────
ACCOUNT2_SITE_NAMES = {
    "bullpower-ai":              "aiitec-bullpower-ai",
    "bullpower-hub":             "aiitec-bullpower-hub",
    "cognitive-symphony":        "aiitec-ds24-suite",
    "creatorai-ultra":           "aiitec-creatorai",
    "creatorstudio-pro":         "aiitec-creatorstudio",
    "autoincome-ai":             "aiitec-autoincome",
    "shopify-brutal-tuning":     "aiitec-shopify-tuning",
    "shopify-acquisition-engine":"aiitec-shopify-acq",
    "shopify-suite":             "aiitec-shopify-suite",
    "steuercockpit":             "aiitec-steuercockpit",
    "telegram-bot":              "aiitec-telegram-bot",
    "launcher":                  "aiitec-launcher",
    "digistore24-suite":         "aiitec-digistore24",
    "icomeauto":                 "aiitec-icomeauto",
    "gumroad-discord":           "aiitec-gumroad",
    "lead-capture":              "aiitec-lead-capture",
}


def netlify_cli(args: list[str], token: str, cwd: str | None = None) -> tuple[int, str, str]:
    env = {**os.environ, "NETLIFY_AUTH_TOKEN": token}
    result = subprocess.run(
        ["netlify"] + args,
        capture_output=True, text=True, env=env,
        cwd=cwd or str(ROOT), timeout=120
    )
    return result.returncode, result.stdout, result.stderr


def netlify_api(endpoint: str, token: str, method: str = "GET", body: dict | None = None):
    import urllib.request, urllib.error
    url = f"https://api.netlify.com/api/v1/{endpoint}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"    API Error {e.code}: {e.read().decode()[:200]}")
        return None


def deploy_to_account1():
    print("\n" + "="*60)
    print("ACCOUNT 1: bullpowerhubgit — Update bestehender Sites")
    print("="*60)

    results = []
    for dir_name, site_id in ACCOUNT1_SITES.items():
        deploy_dir = DEPLOY_DIR / dir_name
        if not deploy_dir.exists():
            print(f"⚠️  {dir_name}: Verzeichnis nicht gefunden, übersprungen")
            continue

        print(f"\n  🚀 Deploying {dir_name} → Site {site_id[:8]}...")
        code, stdout, stderr = netlify_cli([
            "deploy", "--prod",
            "--dir", str(deploy_dir),
            "--site", site_id,
            "--message", f"High-Ticket Upgrade {dir_name}",
        ], TOKEN_BULLPOWER)

        if code == 0:
            url_line = next((l for l in stdout.split("\n") if "Website URL" in l or "https://" in l and ".netlify.app" in l), "")
            url = url_line.split()[-1] if url_line else f"https://{dir_name}.netlify.app"
            print(f"  ✅ {dir_name} live: {url}")
            results.append((dir_name, url, "✅"))
        else:
            err = (stderr or stdout)[:200]
            print(f"  ❌ {dir_name} fehlgeschlagen: {err}")
            results.append((dir_name, "FEHLER", "❌"))

        time.sleep(1)

    return results


def get_account2_slug() -> str:
    """Hole den Account-Slug für aiitecbuuss."""
    data = netlify_api("accounts", TOKEN_AIITEC)
    if data and isinstance(data, list) and len(data) > 0:
        slug = data[0].get("slug", "")
        name = data[0].get("name", "")
        print(f"  Account 2 gefunden: {name} (slug: {slug})")
        return slug
    return ""


def create_and_deploy_account2():
    print("\n" + "="*60)
    print("ACCOUNT 2: aiitecbuuss — Neue Sites erstellen + deployen")
    print("="*60)

    # Account Slug holen
    slug = get_account2_slug()
    if not slug:
        print("⚠️  Account Slug nicht gefunden — versuche ohne slug...")
        slug = None

    results = []
    deployed_urls = {}

    for dir_name, site_name in ACCOUNT2_SITE_NAMES.items():
        deploy_dir = DEPLOY_DIR / dir_name
        if not deploy_dir.exists():
            print(f"⚠️  {dir_name}: Verzeichnis nicht gefunden")
            continue

        print(f"\n  🏗️  Erstelle Site '{site_name}'...")

        # Site via API erstellen
        body = {"name": site_name}
        if slug:
            body["account_slug"] = slug

        site_data = netlify_api("sites", TOKEN_AIITEC, "POST", body)

        if not site_data or "id" not in site_data:
            # Fallback: Versuch mit Netlify CLI
            print(f"     API fehlgeschlagen, versuche CLI...")
            code, stdout, stderr = netlify_cli(
                ["sites:create", "--name", site_name, "--disable-linking"],
                TOKEN_AIITEC
            )
            # Parse site ID from output
            site_id = None
            for line in stdout.split("\n"):
                if "Site ID" in line or "id:" in line.lower():
                    parts = line.split()
                    for p in parts:
                        if len(p) == 36 and p.count("-") == 4:
                            site_id = p
                            break

            if not site_id:
                print(f"  ❌ {site_name}: Site-Erstellung fehlgeschlagen")
                results.append((dir_name, "FEHLER", "❌"))
                continue
        else:
            site_id = site_data["id"]
            live_url = site_data.get("ssl_url") or site_data.get("url") or f"https://{site_name}.netlify.app"
            print(f"     Site erstellt: {live_url} (ID: {site_id[:8]})")

        # Deployen
        print(f"     Deploying {dir_name}...")
        code, stdout, stderr = netlify_cli([
            "deploy", "--prod",
            "--dir", str(deploy_dir),
            "--site", site_id,
            "--message", f"High-Ticket Launch {dir_name}",
        ], TOKEN_AIITEC)

        if code == 0:
            url_line = next(
                (l for l in stdout.split("\n")
                 if ("Website URL" in l or ("https://" in l and ".netlify.app" in l))),
                ""
            )
            url = url_line.split()[-1] if url_line else f"https://{site_name}.netlify.app"
            print(f"  ✅ {site_name} live: {url}")
            results.append((dir_name, url, "✅"))
            deployed_urls[dir_name] = url
        else:
            err = (stderr or stdout)[:300]
            print(f"  ❌ {site_name} fehlgeschlagen: {err}")
            results.append((dir_name, "FEHLER", "❌"))

        time.sleep(2)

    return results, deployed_urls


def update_deployed_urls(account1_results, account2_results):
    """Aktualisiert DEPLOYED_URLS.md mit den neuen Netlify-URLs."""
    urls_file = DEPLOY_DIR / "DEPLOYED_URLS.md"
    content = urls_file.read_text(encoding="utf-8")

    # Füge Account 2 Sektion hinzu falls nicht vorhanden
    if "aiitecbuuss" not in content:
        new_section = "\n\n## Netlify Sites — Account 2 (aiitecbuuss) — High-Ticket Launch\n\n"
        new_section += "| Tool | URL | Status |\n|------|-----|--------|\n"
        for dir_name, url, status in account2_results:
            new_section += f"| {dir_name} | {url} | {status} LIVE — High-Ticket |\n"
        content += new_section

    urls_file.write_text(content, encoding="utf-8")
    print("\n✅ DEPLOYED_URLS.md aktualisiert")


def main():
    if not TOKEN_BULLPOWER:
        print("❌ NETLIFY_AUTH_TOKEN_BULLPOWER oder NETLIFY_AUTH_TOKEN fehlt")
        return
    if not TOKEN_AIITEC:
        print("❌ NETLIFY_AUTH_TOKEN_AIITEC fehlt")
        return
    print("🚀 NETLIFY HIGH-TICKET DEPLOY — Beide Accounts")
    print("=" * 60)

    # Account 1 — Update
    a1_results = deploy_to_account1()

    # Account 2 — Neue Sites
    a2_results, a2_urls = create_and_deploy_account2()

    # URLs updaten
    update_deployed_urls(a1_results, a2_results)

    # Zusammenfassung
    print("\n" + "="*60)
    print("DEPLOY ZUSAMMENFASSUNG")
    print("="*60)

    a1_ok = sum(1 for _, _, s in a1_results if s == "✅")
    a2_ok = sum(1 for _, _, s in a2_results if s == "✅")

    print(f"\nAccount 1 (bullpowerhubgit): {a1_ok}/{len(a1_results)} erfolgreich")
    print(f"Account 2 (aiitecbuuss):     {a2_ok}/{len(a2_results)} erfolgreich")
    print(f"\nGesamt: {a1_ok + a2_ok}/{len(a1_results) + len(a2_results)} Sites live")

    if a2_urls:
        print("\n📋 Neue Account 2 URLs:")
        for dir_name, url in a2_urls.items():
            print(f"   {dir_name}: {url}")


if __name__ == "__main__":
    main()
