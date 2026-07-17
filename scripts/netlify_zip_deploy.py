#!/usr/bin/env python3
"""
Netlify Direct Zip Deploy — KEINE Build-Minutes, funktioniert auf Free Plan.
Deployt pre-built HTML direkt via Netlify Files API.
"""
import os, sys, json, hashlib, zipfile, tempfile, time
from pathlib import Path
import urllib.request, urllib.error

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_DIR = ROOT / "netlify-deploy"

def _env(*names):
    for n in names:
        v = os.getenv(n, "")
        if v: return v
    return ""

def api(token, method, path, data=None, headers=None):
    url = f"https://api.netlify.com/api/v1{path}"
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if headers: h.update(headers)
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "msg": e.read().decode()[:300]}

def deploy_folder(token, site_id, folder):
    """Deploy a folder as a zip file — no build, no build minutes consumed."""
    folder = Path(folder)
    if not folder.exists():
        return {"ok": False, "reason": f"Folder not found: {folder}"}

    # Zip erstellen
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = tmp.name

    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in folder.rglob("*"):
            if f.is_file() and ".netlify" not in str(f):
                zf.write(f, f.relative_to(folder))

    zip_size = os.path.getsize(tmp_path)
    if zip_size < 100:
        os.unlink(tmp_path)
        return {"ok": False, "reason": "Zip too small (no files?)"}

    # Deploy via zip upload
    url = f"https://api.netlify.com/api/v1/sites/{site_id}/deploys"
    h = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/zip",
    }
    with open(tmp_path, "rb") as f:
        zip_data = f.read()
    os.unlink(tmp_path)

    req = urllib.request.Request(url, data=zip_data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read())
            return {"ok": True, "url": result.get("deploy_ssl_url") or result.get("url", ""), "id": result.get("id", "")}
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:300]
        return {"ok": False, "error": e.code, "msg": msg}

def get_or_create_site(token, account_id, site_name):
    """Get existing site by name or create it."""
    sites = api(token, "GET", f"/sites?per_page=100&filter=own")
    if isinstance(sites, list):
        for s in sites:
            if s.get("name") == site_name:
                return s["id"], False
    # Create
    result = api(token, "POST", "/sites", {
        "name": site_name,
        "account_slug": account_id,
    })
    if "id" in result:
        return result["id"], True
    return None, False

SITES = {
    # Konto 1: bullpowerhubgit (Token 1)
    "konto1": [
        ("bullpower-ai-tools",            "bullpower-ai"),
        ("bullpower-hub-portal",          "bullpower-hub"),
        ("autoincome-ai",                 "autoincome-ai"),
        ("creatorai-ultra",               "creatorai-ultra"),
        ("creatorstudio-pro",             "creatorstudio-pro"),
        ("cognitive-symphony-ds24",       "cognitive-symphony"),
        ("shopify-brutal-tuning",         "shopify-brutal-tuning"),
        ("shopify-acquisition-engine",    "shopify-acquisition-engine"),
        ("shopify-automaton-suite",       "shopify-suite"),
        ("digistore24-automation-suite",  "digistore24-suite"),
        ("bullpower-steuercockpit",       "steuercockpit"),
        ("telegram-marketing-bot",        "telegram-bot"),
        ("bullpower-icomeauto",           "icomeauto"),
        ("bullpower-launcher",            "launcher"),
        ("bullpower-lead",                "lead-capture"),
        ("gumroad-discord-bot",           "gumroad-discord"),
    ],
    # Konto 2: aiitecbuuss (Token 2) — master-dashboard hier deployen
    "konto2": [
        ("master-dashboard-hub",          "master-dashboard"),
    ]
}

def main():
    token1 = _env("NETLIFY_AUTH_TOKEN")
    token2 = _env("NETLIFY_AUTH_TOKEN_2")

    if not token1:
        print("❌ NETLIFY_AUTH_TOKEN fehlt in .env")
        sys.exit(1)

    # Account IDs holen
    accs1 = api(token1, "GET", "/accounts")
    accs2 = api(token2, "GET", "/accounts") if token2 else []
    acc1_slug = accs1[0]["slug"] if isinstance(accs1, list) and accs1 else "bullpowerhubgit"
    acc2_slug = accs2[0]["slug"] if isinstance(accs2, list) and accs2 else "aiitecbuuss"

    total_ok = 0
    total_fail = 0

    for konto, sites in SITES.items():
        token = token1 if konto == "konto1" else token2
        acc_slug = acc1_slug if konto == "konto1" else acc2_slug
        if not token:
            print(f"\n⚠️  {konto}: kein Token — übersprungen")
            continue

        print(f"\n{'='*60}")
        print(f"🔑 {konto} ({acc_slug}) — {len(sites)} Sites")
        print(f"{'='*60}")

        for site_name, folder_name in sites:
            folder = DEPLOY_DIR / folder_name
            if not folder.exists():
                print(f"  ⚠️  {site_name} — Ordner fehlt: {folder_name}/")
                continue

            print(f"  📦 {site_name} → {folder_name}/", end=" ", flush=True)

            site_id, created = get_or_create_site(token, acc_slug, site_name)
            if not site_id:
                print(f"❌ Site nicht erstellbar")
                total_fail += 1
                continue

            if created:
                time.sleep(1)  # Netlify braucht kurz nach Creation

            result = deploy_folder(token, site_id, folder)
            if result.get("ok"):
                url = result.get("url", f"https://{site_name}.netlify.app")
                print(f"✅ {url}")
                total_ok += 1
            else:
                print(f"❌ {result.get('msg') or result.get('reason','?')[:80]}")
                total_fail += 1

    print(f"\n{'='*60}")
    print(f"✅ {total_ok} Sites deployed | ❌ {total_fail} Fehler")

if __name__ == "__main__":
    # .env laden
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    main()
