#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  ACCOUNT SETUP MASTER — Automatisiert Konto-Registrierung          ║
║  Öffnet Registrierungs-URLs, generiert Configs, trackt Fortschritt ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import os, sys, time, subprocess, json, webbrowser
from pathlib import Path

# Basis-Verzeichnis
BASE = Path.home() / "supermegabot" / "rudibot-army"
ACCOUNTS_FILE = BASE / ".env.accounts"
PROGRESS_FILE = BASE / "account_setup_progress.json"

EMAILS = [
    "dragonadnp@gmail.com",
    "nikolestimi@gmail.com",
    "bullpowersrtkennels@gmail.com",
    "looopwave@gmail.com",
    "aitecbuuss@gmail.com",
    "rudolf.sarkany@aitec.de",
    "rudolf.sarkany.aiitec@gmail.com",
]

# Plattform-Zuordnung: welches Konto bekommt welche Plattformen
# bullpowersrtkennels hat schon fast alles — verteile den Rest
PLATFORM_ASSIGNMENTS = {
    "dragonadnp@gmail.com": [
        ("stripe", "https://dashboard.stripe.com/register"),
        ("shopify", "https://www.shopify.com/signup"),
        ("sendgrid", "https://signup.sendgrid.com/"),
        ("mailchimp", "https://login.mailchimp.com/signup/"),
        ("github", "https://github.com/signup"),
    ],
    "nikolestimi@gmail.com": [
        ("hubspot", "https://www.hubspot.com/products/crm"),
        ("slack", "https://slack.com/get-started"),
        ("trello", "https://trello.com/signup"),
        ("notion", "https://www.notion.so/signup"),
        ("airtable", "https://airtable.com/create"),
    ],
    "bullpowersrtkennels@gmail.com": [
        ("shopify", "https://www.shopify.com/signup"),
        ("stripe", "https://dashboard.stripe.com/register"),
        ("openai", "https://platform.openai.com/signup"),
        ("aws", "https://aws.amazon.com/free/"),
        ("google_cloud", "https://cloud.google.com/free"),
        ("github", "https://github.com/signup"),
        ("cloudflare", "https://dash.cloudflare.com/sign-up"),
        ("heroku", "https://signup.heroku.com/"),
        ("pipedrive", "https://www.pipedrive.com/signup/"),
        ("zendesk", "https://www.zendesk.com/register/"),
        ("intercom", "https://www.intercom.com/signup"),
        ("jira", "https://www.atlassian.com/software/jira"),
        ("salesforce", "https://www.salesforce.com/de/form/signup/freetrial/sales/"),
        ("hubspot", "https://www.hubspot.com/products/crm"),
        ("slack", "https://slack.com/get-started"),
        ("sendgrid", "https://signup.sendgrid.com/"),
        ("mailchimp", "https://login.mailchimp.com/signup/"),
        ("notion", "https://www.notion.so/signup"),
        ("airtable", "https://airtable.com/create"),
    ],
    "looopwave@gmail.com": [
        ("shopify", "https://www.shopify.com/signup"),
        ("stripe", "https://dashboard.stripe.com/register"),
        ("openai", "https://platform.openai.com/signup"),
        ("google_cloud", "https://cloud.google.com/free"),
        ("github", "https://github.com/signup"),
    ],
    "aitecbuuss@gmail.com": [
        ("aws", "https://aws.amazon.com/free/"),
        ("google_cloud", "https://cloud.google.com/free"),
        ("heroku", "https://signup.heroku.com/"),
        ("cloudflare", "https://dash.cloudflare.com/sign-up"),
        ("github", "https://github.com/signup"),
    ],
    "rudolf.sarkany@aitec.de": [
        ("aws", "https://aws.amazon.com/free/"),
        ("google_cloud", "https://cloud.google.com/free"),
        ("stripe", "https://dashboard.stripe.com/register"),
        ("shopify", "https://www.shopify.com/signup"),
        ("github", "https://github.com/signup"),
    ],
    "rudolf.sarkany.aiitec@gmail.com": [
        ("openai", "https://platform.openai.com/signup"),
        ("stripe", "https://dashboard.stripe.com/register"),
        ("shopify", "https://www.shopify.com/signup"),
        ("google_cloud", "https://cloud.google.com/free"),
        ("github", "https://github.com/signup"),
    ],
}

# API-Key Dashboard URLs (zum Kopieren der Keys)
API_KEY_URLS = {
    "shopify": "https://partners.shopify.com/",
    "stripe": "https://dashboard.stripe.com/apikeys",
    "openai": "https://platform.openai.com/api-keys",
    "sendgrid": "https://app.sendgrid.com/settings/api_keys",
    "mailchimp": "https://us1.admin.mailchimp.com/account/api/",
    "aws": "https://console.aws.amazon.com/iam/",
    "google_cloud": "https://console.cloud.google.com/apis/credentials",
    "github": "https://github.com/settings/tokens",
    "notion": "https://www.notion.so/my-integrations",
    "airtable": "https://airtable.com/create/tokens",
    "heroku": "https://dashboard.heroku.com/account",
    "cloudflare": "https://dash.cloudflare.com/profile/api-tokens",
    "pipedrive": "https://app.pipedrive.com/settings/api",
    "zendesk": "https://support.zendesk.com/hc/en-us/articles/203663866",
    "intercom": "https://app.intercom.com/a/apps/",
    "jira": "https://id.atlassian.com/manage-profile/security/api-tokens",
    "salesforce": "https://developer.salesforce.com/",
    "hubspot": "https://developers.hubspot.com/",
    "slack": "https://api.slack.com/apps",
    "trello": "https://trello.com/app-key",
}

def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {}

def save_progress(progress):
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))

def generate_env_accounts():
    """Generiert die zentrale .env.accounts Datei"""
    lines = [
        "# ═══════════════════════════════════════════════════════════════",
        "# RUDIBOT ARMY — Account Configuration",
        "# Automatisch generiert von setup_accounts.py",
        "# ═══════════════════════════════════════════════════════════════",
        "",
        "# Multi-Account Setup",
        "TOTAL_ACCOUNTS=7",
        "ACTIVE_ACCOUNT_PRIMARY=bullpowersrtkennels@gmail.com",
        "",
    ]

    for email in EMAILS:
        safe = email.replace("@", "_at_").replace(".", "_dot_")
        plats = PLATFORM_ASSIGNMENTS.get(email, [])
        lines.append(f"# ── {email} ──")
        lines.append(f"ACCOUNT_{safe}=active")
        if plats:
            lines.append(f"ACCOUNT_{safe}_PLATFORMS={','.join(p[0] for p in plats)}")
        lines.append("")

    lines.extend([
        "# ── API Endpoints ──",
        "STRIPE_API_URL=https://api.stripe.com/v1",
        "SHOPIFY_API_URL=https://{shop}.myshopify.com/admin/api/2024-01",
        "OPENAI_API_URL=https://api.openai.com/v1",
        "",
        "# ── Monitoring ──",
        "DAILY_REVENUE_TARGET=500",
        "WEEKLY_REVENUE_TARGET=3500",
        "MONTHLY_REVENUE_TARGET=15000",
        "",
        "# ── Health Check ──",
        "HEALTH_CHECK_INTERVAL=300",
        "ACCOUNT_SCAN_INTERVAL=1800",
        "MEMORY_CHECK_INTERVAL=60",
    ])

    ACCOUNTS_FILE.write_text("\n".join(lines))
    print(f"✅ Config geschrieben: {ACCOUNTS_FILE}")

def open_registration_urls(email):
    """Öffnet Registrierungs-URLs für ein Konto im Browser"""
    plats = PLATFORM_ASSIGNMENTS.get(email, [])
    if not plats:
        print(f"⚠️ Keine Plattformen zugewiesen für {email}")
        return

    print(f"\n🌐 Öffne Registrierungs-URLs für {email}...")
    for i, (platform, url) in enumerate(plats):
        print(f"   {i+1}. {platform}: {url}")
        # Öffne im Browser (macOS)
        subprocess.run(["open", "-g", url], capture_output=True)
        time.sleep(0.5)

    print(f"   ✅ {len(plats)} URLs geöffnet")

def open_api_key_dashboards(email):
    """Öffnet API-Key Dashboards für bereits registrierte Konten"""
    plats = PLATFORM_ASSIGNMENTS.get(email, [])
    if not plats:
        return

    print(f"\n🔑 Öffne API-Key Dashboards für {email}...")
    for platform, _ in plats:
        url = API_KEY_URLS.get(platform)
        if url:
            print(f"   → {platform}: {url}")
            subprocess.run(["open", "-g", url], capture_output=True)
            time.sleep(0.3)

def show_menu():
    print("\n" + "="*60)
    print("  🚀 RUDIBOT ARMY — Account Setup Master")
    print("="*60)
    print()
    print("1. 📝 Alle Configs generieren (.env.accounts)")
    print("2. 🌐 Registrierungs-URLs für ALLE Konten öffnen")
    print("3. 🌐 Registrierungs-URLs für UNGENUTZTE Konten öffnen")
    print("4. 🔑 API-Key Dashboards öffnen (für API-Keys kopieren)")
    print("5. 📊 Setup-Status anzeigen")
    print("6. 🎯 Empfohlene Registrierungs-Reihenfolge")
    print("0. ❌ Beenden")
    print()

def show_status():
    progress = load_progress()
    print("\n📊 Account Setup Status:")
    print("-" * 50)
    for email in EMAILS:
        plats = PLATFORM_ASSIGNMENTS.get(email, [])
        done = progress.get(email, {}).get("done", [])
        pending = [p[0] for p in plats if p[0] not in done]
        status = "✅" if len(done) == len(plats) and plats else ("🟡" if done else "🔴")
        print(f"{status} {email}")
        print(f"   Erledigt: {len(done)}/{len(plats)}")
        if pending:
            print(f"   Offen: {', '.join(pending[:3])}{'...' if len(pending) > 3 else ''}")
    print("-" * 50)

def show_recommendations():
    print("\n🎯 Empfohlene Registrierungs-Reihenfolge (nach ROI):")
    print("-" * 50)
    print("1. 🛒 Shopify — E-Commerce Basis")
    print("2. 💳 Stripe — Zahlungsabwicklung")
    print("3. 🤖 OpenAI — AI-Automatisierung")
    print("4. 🐙 GitHub — Code & Integrationen")
    print("5. ☁️ Google Cloud — Infrastruktur")
    print("6. 🌐 AWS — Backup-Infrastruktur")
    print("7. 📧 SendGrid — Email Marketing")
    print("8. 👥 HubSpot — CRM & Marketing")
    print("9. 📨 Mailchimp — Newsletter")
    print("10. 💬 Slack — Team-Kommunikation")
    print("-" * 50)

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "generate":
            generate_env_accounts()
            return
        elif cmd == "status":
            show_status()
            return
        elif cmd == "open-unused":
            for email in EMAILS:
                if email != "bullpowersrtkennels@gmail.com":
                    open_registration_urls(email)
            return

    while True:
        show_menu()
        choice = input("Wähle: ").strip()

        if choice == "1":
            generate_env_accounts()
        elif choice == "2":
            for email in EMAILS:
                open_registration_urls(email)
        elif choice == "3":
            print("\n🌐 Öffne URLs für UNGENUTZTE Konten...")
            for email in EMAILS:
                if email != "bullpowersrtkennels@gmail.com":
                    open_registration_urls(email)
        elif choice == "4":
            email = input("Für welches Konto? (oder 'all'): ").strip()
            if email == "all":
                for e in EMAILS:
                    open_api_key_dashboards(e)
            elif email in EMAILS:
                open_api_key_dashboards(email)
            else:
                print("❌ Ungültige E-Mail")
        elif choice == "5":
            show_status()
        elif choice == "6":
            show_recommendations()
        elif choice == "0":
            print("👋 Tschüss!")
            break
        else:
            print("❌ Ungültige Auswahl")

if __name__ == "__main__":
    main()
