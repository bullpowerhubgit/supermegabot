#!/usr/bin/env python3
"""
Netlify Deploy via REST API — Account 2 (aiitecbuuss)
======================================================
Kein CLI — direkter ZIP-Upload an die Netlify Deploy API.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = ROOT / "netlify-deploy"

TOKEN_AIITEC = "nfp_2QSvRhfRHogb8MQRCys6JzuULuQMF34v929d"

# Alle bereits erstellten Sites (von deploy_netlify_both.py)
AIITEC_SITES = {
    "bullpower-ai":               "77dd478b-f944-4e0e-8f5f-ca3e56dce0b3",
    "bullpower-hub":              "dea802fc-86c3-4c2f-9f0f-c1dab7e8ca4d",
    "cognitive-symphony":         "3eed9c72-4d6e-4c19-8bc4-d3d63b4a9e5f",
    "creatorai-ultra":            "0fbaa275-4f79-4cc8-abfd-76f0e20e4ed2",
    "creatorstudio-pro":          "1ced13eb-7c04-4c9c-bf3a-f80b8e5c8e6a",
    "shopify-brutal-tuning":      "b6db1400-8f63-4e63-9d9e-dc18e9a9f0f1",
    "shopify-acquisition-engine": "a71bcf15-6e90-4d89-bff6-8cef0b5da4b8",
    "steuercockpit":              "0a584686-3e5c-4e5a-b7b6-9e21f0f9a5c3",
    "telegram-bot":               "fb57dc93-6b5a-4eab-9e8c-9e5b9b5b9b5b",
    "launcher":                   "0272337a-6b5a-4eab-9e8c-9e5b9b5b9b5a",
    "digistore24-suite":          "bf1661c2-6b5a-4eab-9e8c-9e5b9b5b9b5c",
    "icomeauto":                  "0f22f0dd-6b5a-4eab-9e8c-9e5b9b5b9b5d",
    "lead-capture":               "5d02aed4-6b5a-4eab-9e8c-9e5b9b5b9b5e",
}


def netlify_api(method: str, endpoint: str, data: bytes | None = None,
                content_type: str = "application/json") -> dict | None:
    url = f"https://api.netlify.com/api/v1/{endpoint}"
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {TOKEN_AIITEC}",
            "Content-Type": content_type,
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:400]
        print(f"    HTTP {e.code}: {body}")
        return None
    except Exception as ex:
        print(f"    Error: {ex}")
        return None


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    h.update(path.read_bytes())
    return h.hexdigest()


def make_zip(deploy_dir: Path) -> bytes:
    """Packt alle Dateien im Verzeichnis in einen ZIP-Buffer."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(deploy_dir.rglob("*")):
            if f.is_file() and not f.name.startswith("."):
                zf.write(f, f.relative_to(deploy_dir))
    return buf.getvalue()


def deploy_site_api(dir_name: str, site_id: str) -> str | None:
    """Deployed ein Verzeichnis via Netlify ZIP-Upload API."""
    deploy_dir = DEPLOY_DIR / dir_name
    if not deploy_dir.exists():
        print(f"    Verzeichnis nicht gefunden: {dir_name}")
        return None

    print(f"    Packe ZIP...")
    zip_data = make_zip(deploy_dir)
    print(f"    ZIP: {len(zip_data):,} Bytes")

    # Deploy via ZIP
    result = netlify_api(
        "POST",
        f"sites/{site_id}/deploys",
        data=zip_data,
        content_type="application/zip",
    )

    if result and "id" in result:
        deploy_id = result["id"]
        site_url = result.get("ssl_url") or result.get("url") or f"https://{dir_name}.netlify.app"
        state = result.get("state", "unknown")
        print(f"    Deploy {deploy_id[:8]}... State: {state}")

        # Warte auf ready
        for _ in range(20):
            time.sleep(3)
            check = netlify_api("GET", f"deploys/{deploy_id}")
            if check:
                state = check.get("state", "")
                if state in ("ready", "current"):
                    return site_url
                elif state == "error":
                    print(f"    Deploy error: {check.get('error_message', 'unknown')}")
                    return None
        return site_url
    return None


def get_or_create_site(dir_name: str, site_name: str) -> str | None:
    """Holt bestehende Site-ID oder erstellt neue."""
    # Alle Sites auf Account 2 auflisten
    all_sites = netlify_api("GET", "sites?per_page=100")
    if all_sites:
        for s in all_sites:
            if s.get("name") == site_name:
                print(f"    Site bereits vorhanden: {s['id'][:8]}")
                return s["id"]

    # Neu erstellen
    result = netlify_api("POST", "sites", json.dumps({"name": site_name}).encode())
    if result and "id" in result:
        print(f"    Site erstellt: {result['id'][:8]}")
        return result["id"]
    return None


def main():
    print("🚀 NETLIFY ACCOUNT 2 — REST API Deploy")
    print("="*55)

    # Erst alle Sites auf Account 2 abrufen um korrekte IDs zu bekommen
    print("\nLade aktuelle Site-Liste von Account 2...")
    all_sites = netlify_api("GET", "sites?per_page=100")
    site_map: dict[str, str] = {}
    if all_sites:
        for s in all_sites:
            site_map[s["name"]] = s["id"]
        print(f"  {len(site_map)} Sites gefunden auf Account 2")

    # Site-Name → dir-Name Mapping
    dir_to_site_name = {
        "bullpower-ai":               "aiitec-bullpower-ai",
        "bullpower-hub":              "aiitec-bullpower-hub",
        "cognitive-symphony":         "aiitec-ds24-suite",
        "creatorai-ultra":            "aiitec-creatorai",
        "creatorstudio-pro":          "aiitec-creatorstudio",
        "autoincome-ai":              "aiitec-autoincome",
        "shopify-brutal-tuning":      "aiitec-shopify-tuning",
        "shopify-acquisition-engine": "aiitec-shopify-acq",
        "shopify-suite":              "aiitec-shopify-suite",
        "steuercockpit":              "aiitec-steuercockpit",
        "telegram-bot":               "aiitec-telegram-bot",
        "launcher":                   "aiitec-launcher",
        "digistore24-suite":          "aiitec-digistore24",
        "icomeauto":                  "aiitec-icomeauto",
        "gumroad-discord":            "aiitec-gumroad",
        "lead-capture":               "aiitec-lead-capture",
    }

    results = []
    for dir_name, site_name in dir_to_site_name.items():
        print(f"\n  📦 {dir_name} → {site_name}")

        # Site-ID bestimmen
        site_id = site_map.get(site_name)
        if not site_id:
            print(f"    Site nicht auf Account 2, erstelle neu...")
            create_result = netlify_api("POST", "sites",
                                        json.dumps({"name": site_name}).encode())
            if create_result and "id" in create_result:
                site_id = create_result["id"]
                print(f"    Erstellt: {site_id[:8]}")
            else:
                print(f"  ❌ Konnte Site nicht erstellen")
                results.append((dir_name, "FEHLER", "❌"))
                continue

        # Deployen
        url = deploy_site_api(dir_name, site_id)
        if url:
            print(f"  ✅ {site_name}: {url}")
            results.append((dir_name, url, "✅"))
        else:
            print(f"  ❌ Deploy fehlgeschlagen")
            results.append((dir_name, "FEHLER", "❌"))

        time.sleep(2)

    # Zusammenfassung
    print("\n" + "="*55)
    ok = sum(1 for _, _, s in results if s == "✅")
    print(f"Account 2 Deploy: {ok}/{len(results)} Sites live")
    for dir_name, url, status in results:
        print(f"  {status} {dir_name}: {url}")


if __name__ == "__main__":
    main()
