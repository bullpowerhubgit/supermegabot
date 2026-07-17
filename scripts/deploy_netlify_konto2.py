#!/usr/bin/env python3
"""Deploy High-Ticket Landingpages zu Netlify Konto 2 (aiitecbuuss@gmail.com).
Voraussetzung: Account muss Credits haben (https://netlify.com/billing).
Usage: python3 scripts/deploy_netlify_konto2.py
"""
import requests, hashlib, time
import os
from pathlib import Path

TOKEN2 = os.getenv("NETLIFY_AUTH_TOKEN_AIITEC", "")
ACCOUNT_ID = os.getenv("NETLIFY_ACCOUNT_ID_AIITEC", "")  # aiitecbuuss
BASE = Path(__file__).parent.parent / "netlify-deploy"
H = {"Authorization": f"Bearer {TOKEN2}"} if TOKEN2 else {}

SITES = [
    ("bullpower-ai",              "bullpower-ai-aiitec",        "fbc63f82-726b-43a0-912b-aac197d67432"),
    ("bullpower-hub",             "bullpower-hub-aiitec",       "0bc19c70-c7d2-4bed-949f-04b92d9ab1af"),
    ("autoincome-ai",             "autoincome-ai-aiitec",       "05b572b3-cfc7-464b-86ff-eda19c852032"),
    ("creatorai-ultra",           "creatorai-ultra-aiitec",     "d273722b-ca7c-4b19-b2d2-433034c1b560"),
    ("creatorstudio-pro",         "creatorstudio-pro-aiitec",   "98ef4a07-167d-4ec6-ad23-9c46457f6f26"),
    ("cognitive-symphony",        "cognitive-symphony-aiitec",  "38c0f88a-a7c5-437c-89ec-df0dfffcc409"),
    ("digistore24-suite",         "digistore24-aiitec",         "b0687575-5826-4318-ad16-19ee1b5303fd"),
    ("steuercockpit",             "steuercockpit-aiitec",       "bbd17ffe-e48c-4e1b-870c-e9d8721b4693"),
    ("telegram-bot",              "telegram-aiitec",            "84b54096-c4fa-41d0-9fd4-56e8bbad4826"),
    # Fehlende — werden erstellt
    ("shopify-brutal-tuning",     "shopify-brutal-aiitec",      None),
    ("shopify-acquisition-engine","shopify-acq-aiitec",         None),
    ("shopify-suite",             "shopify-suite-aiitec",       None),
    ("icomeauto",                 "icomeauto-aiitec",           None),
    ("launcher",                  "launcher-aiitec",            None),
    ("lead-capture",              "lead-capture-aiitec",        None),
    ("gumroad-discord",           "gumroad-aiitec",             None),
    ("master-dashboard",          "master-dash-aiitec",         None),
]


def deploy_to_site(site_id, html_bytes):
    sha1 = hashlib.sha1(html_bytes).hexdigest()
    d = requests.post(
        f"https://api.netlify.com/api/v1/sites/{site_id}/deploys",
        headers={**H, "Content-Type": "application/json"},
        json={"files": {"/index.html": sha1}},
        timeout=25,
    )
    if d.status_code not in (200, 201):
        return False, f"Deploy-Init {d.status_code}: {d.text[:100]}"
    data = d.json()
    if sha1 in data.get("required", []):
        u = requests.put(
            f"https://api.netlify.com/api/v1/deploys/{data['id']}/files/index.html",
            headers={**H, "Content-Type": "application/octet-stream"},
            data=html_bytes, timeout=30,
        )
        if u.status_code not in (200, 201):
            return False, f"Upload {u.status_code}"
    return True, "ok"


def main():
    if not TOKEN2 or not ACCOUNT_ID:
        print("❌ NETLIFY_AUTH_TOKEN_AIITEC oder NETLIFY_ACCOUNT_ID_AIITEC fehlt")
        return
    ok = 0
    fail = 0
    for dirname, site_name, site_id in SITES:
        html_path = BASE / dirname / "index.html"
        if not html_path.exists():
            print(f"  ⚠ {dirname}: index.html fehlt — skip")
            continue
        html_bytes = html_path.read_bytes()

        if site_id is None:
            time.sleep(2)
            r = requests.post(
                "https://api.netlify.com/api/v1/sites",
                headers={**H, "Content-Type": "application/json"},
                json={"name": site_name, "account_id": ACCOUNT_ID},
                timeout=25,
            )
            if r.status_code in (200, 201):
                site_id = r.json()["id"]
                print(f"  🆕 Erstellt: {site_name} → {site_id}")
            else:
                print(f"  ❌ {site_name}: Create {r.status_code} — {r.text[:80]}")
                fail += 1
                continue

        time.sleep(1)
        success, msg = deploy_to_site(site_id, html_bytes)
        if success:
            print(f"  ✅ {site_name} → https://{site_name}.netlify.app")
            ok += 1
        else:
            print(f"  ❌ {site_name}: {msg}")
            fail += 1

    print(f"\n📊 Konto 2 (aiitecbuuss): {ok} OK, {fail} FEHLER von {len(SITES)}")


if __name__ == "__main__":
    main()
