#!/usr/bin/env python3
"""
SuperMegaBot — Einmaliges Setup-Skript
Erstellt Stripe-Produkte + Preise und setzt Railway als GitHub Secret.

Ausführen:
  cd supermegabot
  python3 scripts/setup_stripe_and_railway.py

Voraussetzungen:
  .env muss gesetzt sein: STRIPE_SECRET_KEY, GITHUB_TOKEN
  Railway-Token muss bereitliegen (aus Railway Dashboard → Settings → Tokens)
"""
import json
import os
import sys
import subprocess
import urllib.request
import urllib.parse
import urllib.error
import base64
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"

# ── Lade .env ────────────────────────────────────────────────────────────────
env_vars = {}
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env_vars[k.strip()] = v.strip()

STRIPE_KEY = env_vars.get("STRIPE_SECRET_KEY") or os.getenv("STRIPE_SECRET_KEY", "")
GITHUB_TOKEN = env_vars.get("GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN", "")
GITHUB_USER = env_vars.get("GITHUB_USER", "bullpowerhubgit")
GITHUB_REPO = "supermegabot"


def _stripe(method: str, path: str, data: dict = None) -> dict:
    if not STRIPE_KEY:
        print("❌ STRIPE_SECRET_KEY fehlt in .env")
        sys.exit(1)
    url = f"https://api.stripe.com/v1{path}"
    token = base64.b64encode(f"{STRIPE_KEY}:".encode()).decode()
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Stripe-Version", "2024-12-18.acacia")
    if body:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        msg = json.loads(e.read()).get("error", {}).get("message", str(e))
        print(f"❌ Stripe {e.code}: {msg}")
        sys.exit(1)


def _github_set_secret(secret_name: str, secret_value: str):
    """Setzt ein GitHub Actions Repository Secret via API."""
    if not GITHUB_TOKEN:
        print(f"⚠️  GITHUB_TOKEN fehlt — Secret {secret_name} manuell setzen")
        return False

    # Public key holen (nötig für Verschlüsselung)
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/actions/secrets/public-key"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=10) as r:
        pub = json.loads(r.read())

    # Verschlüsseln mit libsodium (PyNaCl)
    try:
        from nacl import encoding, public
        pub_key = public.PublicKey(pub["key"].encode(), encoding.Base64Encoder())
        sealed = public.SealedBox(pub_key).encrypt(secret_value.encode())
        encrypted = base64.b64encode(sealed).decode()
    except ImportError:
        # Fallback: gh CLI
        result = subprocess.run(
            ["gh", "secret", "set", secret_name, "--body", secret_value,
             "--repo", f"{GITHUB_USER}/{GITHUB_REPO}"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"⚠️  gh CLI fehlgeschlagen: {result.stderr.strip()}")
            print(f"   Manuell setzen: gh secret set {secret_name} --body <token>")
            return False
        return True

    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/actions/secrets/{secret_name}"
    data = json.dumps({"encrypted_value": encrypted, "key_id": pub["key_id"]}).encode()
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as r:
        pass
    return True


def _update_env(key: str, value: str):
    """Schreibt/überschreibt einen Key in .env."""
    content = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    lines = content.splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n")


def create_stripe_plans():
    print("\n📦 Erstelle Stripe-Produkte und Preise...\n")
    plans = [
        {
            "key": "STRIPE_PRICE_STARTER",
            "product_name": "SuperMegaBot Starter",
            "description": "Shopify Sync, Basic AI, Telegram Bot",
            "amount": 4900,  # €49.00 in Cent
            "metadata": {"plan": "starter"},
        },
        {
            "key": "STRIPE_PRICE_PRO",
            "product_name": "SuperMegaBot Pro",
            "description": "Alle Integrationen, erweiterte KI, SEO, Analytics",
            "amount": 9900,
            "metadata": {"plan": "pro"},
        },
        {
            "key": "STRIPE_PRICE_ENTERPRISE",
            "product_name": "SuperMegaBot Enterprise",
            "description": "Unbegrenzt, White-Label, Priority Support",
            "amount": 29900,
            "metadata": {"plan": "enterprise"},
        },
    ]

    price_ids = {}
    for plan in plans:
        # Produkt erstellen
        prod_data = {"name": plan["product_name"], "description": plan["description"]}
        for k, v in plan["metadata"].items():
            prod_data[f"metadata[{k}]"] = v
        prod = _stripe("POST", "/products", prod_data)
        print(f"  ✅ Produkt erstellt: {prod['name']} ({prod['id']})")

        # Preis erstellen
        price_data = {
            "product": prod["id"],
            "unit_amount": plan["amount"],
            "currency": "eur",
            "recurring[interval]": "month",
        }
        price = _stripe("POST", "/prices", price_data)
        price_id = price["id"]
        print(f"     💰 Preis: €{plan['amount']//100}/mo → {price_id}")

        price_ids[plan["key"]] = price_id
        _update_env(plan["key"], price_id)

    print(f"\n✅ Alle Price IDs in .env geschrieben:\n")
    for k, v in price_ids.items():
        print(f"   {k}={v}")
    return price_ids


def set_railway_token():
    print("\n🚂 Railway Token Setup...\n")
    railway_token = env_vars.get("RAILWAY_TOKEN", "").strip()
    if not railway_token:
        print("  Railway-Token nicht in .env gefunden.")
        railway_token = input("  Bitte RAILWAY_TOKEN eingeben (Railway → Settings → Tokens): ").strip()
        if not railway_token:
            print("  ⚠️  Übersprungen — später manuell als GitHub Secret setzen")
            return

    _update_env("RAILWAY_TOKEN", railway_token)

    print(f"  🔐 Setze GitHub Secret RAILWAY_TOKEN...")
    ok = _github_set_secret("RAILWAY_TOKEN", railway_token)
    if ok:
        print(f"  ✅ GitHub Secret RAILWAY_TOKEN gesetzt → Auto-Deploy aktiv!")
    else:
        print(f"  ⚠️  Manuell: GitHub → Repo → Settings → Secrets → New secret")
        print(f"      Name: RAILWAY_TOKEN | Value: {railway_token[:8]}...")


def _railway_graphql(query: str, variables: dict, token: str) -> dict:
    """Railway GraphQL API call."""
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request("https://backboard.railway.app/graphql/v2", data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"errors": [{"message": f"HTTP {e.code}: {e.read()[:200].decode()}"}]}
    except Exception as e:
        return {"errors": [{"message": str(e)}]}


def push_env_vars_to_railway(price_ids: dict):
    """Setzt alle wichtigen Env Vars direkt auf Railway via GraphQL API."""
    railway_token = env_vars.get("RAILWAY_TOKEN", "").strip()
    if not railway_token or len(railway_token) < 10:
        print("\n⚠️  Railway Token fehlt oder unvollständig — Env Vars nicht gesetzt")
        return

    print("\n🚂 Setze Env Vars auf Railway...\n")

    # Projekt-ID holen
    q_projects = """
    query { me { projects { edges { node { id name } } } } }
    """
    resp = _railway_graphql(q_projects, {}, railway_token)
    if resp.get("errors"):
        print(f"  ❌ Railway Auth fehlgeschlagen: {resp['errors'][0]['message'][:100]}")
        print(f"  → Env Vars manuell im Railway Dashboard eintragen")
        return

    projects = resp.get("data", {}).get("me", {}).get("projects", {}).get("edges", [])
    if not projects:
        print("  ⚠️  Keine Railway-Projekte gefunden")
        return

    # Suche supermegabot-Projekt
    project = None
    for p in projects:
        if "supermegabot" in p["node"]["name"].lower() or "super" in p["node"]["name"].lower():
            project = p["node"]
            break
    if not project:
        project = projects[0]["node"]

    print(f"  📦 Projekt: {project['name']} ({project['id']})")

    # Service-ID holen
    q_services = """
    query($projectId: String!) {
      project(id: $projectId) {
        services { edges { node { id name } } }
        environments { edges { node { id name } } }
      }
    }
    """
    resp = _railway_graphql(q_services, {"projectId": project["id"]}, railway_token)
    proj_data = resp.get("data", {}).get("project", {})
    services = proj_data.get("services", {}).get("edges", [])
    environments = proj_data.get("environments", {}).get("edges", [])

    if not services or not environments:
        print("  ⚠️  Keine Services/Environments gefunden")
        return

    service_id = services[0]["node"]["id"]
    env_id = next((e["node"]["id"] for e in environments if e["node"]["name"] == "production"), environments[0]["node"]["id"])
    print(f"  🔧 Service: {services[0]['node']['name']} | Env: {environments[0]['node']['name']}")

    # Wichtige Vars aus .env
    KEYS_TO_PUSH = [
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN_1", "TELEGRAM_BOT_TOKEN_2", "TELEGRAM_CHAT_ID",
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
        "STRIPE_SECRET_KEY", "STRIPE_PRICE_STARTER", "STRIPE_PRICE_PRO", "STRIPE_PRICE_ENTERPRISE",
        "SUPABASE_URL", "SUPABASE_ANON_KEY",
        "SHOPIFY_SHOP_DOMAIN", "SHOPIFY_ADMIN_API_TOKEN", "SHOPIFY_API_VERSION",
        "SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET",
        "GITHUB_TOKEN", "GITHUB_USER",
        "DASHBOARD_PORT", "DASHBOARD_URL",
        "PERPLEXITY_API_KEY",
    ]

    # Merge mit aktuellen price_ids
    vars_to_set = {**env_vars, **price_ids}

    q_upsert = """
    mutation($input: VariableCollectionUpsertInput!) {
      variableCollectionUpsert(input: $input)
    }
    """
    variables_payload = {k: vars_to_set[k] for k in KEYS_TO_PUSH if vars_to_set.get(k)}

    resp = _railway_graphql(q_upsert, {
        "input": {
            "projectId": project["id"],
            "serviceId": service_id,
            "environmentId": env_id,
            "variables": variables_payload,
        }
    }, railway_token)

    if resp.get("errors"):
        print(f"  ❌ Fehler: {resp['errors'][0]['message'][:100]}")
    else:
        print(f"  ✅ {len(variables_payload)} Env Vars auf Railway gesetzt!")
        for k in variables_payload:
            print(f"     • {k}")


def set_stripe_secrets(price_ids: dict):
    print("\n🔐 Setze Stripe Keys als GitHub Secrets...\n")
    stripe_secrets = {
        "STRIPE_SECRET_KEY": STRIPE_KEY,
        **price_ids,
    }
    webhook_secret = env_vars.get("STRIPE_WEBHOOK_SECRET", "")
    if webhook_secret:
        stripe_secrets["STRIPE_WEBHOOK_SECRET"] = webhook_secret

    for name, value in stripe_secrets.items():
        if value:
            ok = _github_set_secret(name, value)
            status = "✅" if ok else "⚠️ "
            print(f"  {status} {name}")


if __name__ == "__main__":
    print("=" * 60)
    print("  SuperMegaBot — Stripe + Railway Setup")
    print("=" * 60)

    if not STRIPE_KEY:
        print("\n❌ STRIPE_SECRET_KEY fehlt in .env")
        print("   Stripe Dashboard → Developers → API Keys → Secret key")
        print("   In .env eintragen: STRIPE_SECRET_KEY=sk_live_...")
        sys.exit(1)

    price_ids = create_stripe_plans()
    set_railway_token()
    push_env_vars_to_railway(price_ids)
    set_stripe_secrets(price_ids)

    print("\n" + "=" * 60)
    print("  ✅ Setup abgeschlossen!")
    print("  Nächste Schritte:")
    print("  1. git checkout main && git merge claude/blissful-noether-eoEVy")
    print("  2. git push origin main → Railway auto-deploy startet")
    print("  3. Stripe Webhook: Dashboard → Webhooks → Endpoint hinzufügen")
    print("     URL: https://<deine-railway-url>/api/stripe/webhook")
    print("=" * 60)
