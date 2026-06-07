#!/usr/bin/env python3
"""Dashboard Data Server — Schreibt Live-Daten für das HTML-Dashboard"""
import os, sys, time, json, subprocess, re
from pathlib import Path
from datetime import datetime

ARMY_DIR = Path(__file__).parent
DASHBOARD_DATA = ARMY_DIR / "dashboard_data.json"
CENTRAL_LOG = ARMY_DIR / "logs" / "central_errors.log"

def get_system_stats():
    stats = {"ram_pct": 0, "disk_pct": 0, "processes": 0}
    try:
        out = subprocess.run("vm_stat", shell=True, capture_output=True, text=True, timeout=5).stdout
        vals = {}
        for line in out.splitlines():
            if ":" in line:
                k = line.split(":")[0].strip().replace('"', '')
                v = line.split(":")[1].strip().rstrip('.')
                try:
                    vals[k] = int(v)
                except ValueError:
                    pass
        used = vals.get("Pages active", 0) + vals.get("Pages wired down", 0) + vals.get("Pages occupied by compressor", 0)
        total = used + vals.get("Pages free", 0) + vals.get("Pages inactive", 0) + vals.get("Pages speculative", 0)
        stats["ram_pct"] = round((used / total) * 100, 1) if total > 0 else 0
    except Exception:
        pass

    try:
        df_out = subprocess.run("df -h /", shell=True, capture_output=True, text=True, timeout=5).stdout
        lines = df_out.strip().splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 4:
                stats["disk_pct"] = float(parts[4].replace('%', ''))
                # Parse available space
                avail_str = parts[3]
                if avail_str.endswith('Gi'):
                    stats["disk_free_gb"] = float(avail_str[:-2])
                elif avail_str.endswith('Mi'):
                    stats["disk_free_gb"] = round(float(avail_str[:-2]) / 1024, 1)
                elif avail_str.endswith('Ti'):
                    stats["disk_free_gb"] = float(avail_str[:-2]) * 1024
    except Exception:
        pass

    try:
        result = subprocess.run(["pgrep", "-f", "rudibot-army"], capture_output=True, text=True, timeout=3)
        stats["processes"] = len(result.stdout.strip().splitlines()) if result.returncode == 0 else 0
    except Exception:
        pass

    return stats

def get_agent_status():
    agents = []
    agent_scripts = [
        ("resource_manager", "🌡️", "Resource Manager"),
        ("monitor", "🔴", "Service Monitor"),
        ("shopify", "🛒", "Shopify Watcher"),
        ("social", "📱", "Social Autopilot"),
        ("finance", "💰", "Finance Tracker"),
        ("monetization", "📈", "Revenue Tracker"),
        ("learner", "🧠", "Auto Learner"),
        ("security", "🔐", "Security Guard"),
        ("optimizer", "⚡", "Optimizer"),
    ]
    for aid, icon, name in agent_scripts:
        try:
            result = subprocess.run(["pgrep", "-f", f"agent_{aid}.py"], capture_output=True, text=True, timeout=2)
            running = result.returncode == 0 and result.stdout.strip()
            agents.append({"id": aid, "icon": icon, "name": name, "running": bool(running)})
        except Exception:
            agents.append({"id": aid, "icon": icon, "name": name, "running": False})
    return agents

def get_recent_errors(count=20):
    errors = []
    try:
        if CENTRAL_LOG.exists():
            lines = CENTRAL_LOG.read_text(errors='ignore').strip().splitlines()
            for line in lines[-count:]:
                # Parse [timestamp] [source] message
                match = re.match(r'\[(.+?)\] \[(.+?)\] (.+)', line)
                if match:
                    errors.append({"ts": match.group(1), "source": match.group(2), "msg": match.group(3)})
                else:
                    errors.append({"ts": "?", "source": "?", "msg": line[:100]})
    except Exception:
        pass
    return errors

def get_account_data():
    accounts = [
        {"email": "dragonadnp@gmail.com", "platforms": ["Google Cloud"], "status": "limited"},
        {"email": "nikolestimi@gmail.com", "platforms": [], "status": "missing"},
        {"email": "bullpowersrtkennels@gmail.com", "platforms": [
            "Shopify", "Stripe", "Klaviyo", "Twitter", "Airtable", "Google Cloud", "HubSpot",
            "Intercom", "Jira", "Mailchimp", "Notion", "OpenAI", "Perplexity", "Pipedrive",
            "SendGrid", "Slack", "Zendesk", "AWS", "Cloudflare", "Heroku"
        ], "status": "active"},
        {"email": "looopwave@gmail.com", "platforms": [], "status": "missing"},
        {"email": "aitecbuuss@gmail.com", "platforms": [], "status": "missing"},
        {"email": "rudolf.sarkany@aitec.de", "platforms": [], "status": "missing"},
        {"email": "rudolf.sarkany.aiitec@gmail.com", "platforms": [], "status": "missing"},
    ]
    return accounts

def get_revenue_data():
    return {
        "daily": 0.0,
        "weekly": 0.0,
        "monthly": 0.0,
        "sources": [],
        "recommendations": [
            "🚀 Starte eine Email-Kampagne über SendGrid/Mailchimp",
            "🛒 Prüfe Shopify-Cart-Abbruch — retargeting nötig",
            "💳 Stripe nicht konfiguriert — Zahlungen nicht trackbar",
            "👥 Nutze ungenutzte Konten für mehr Shopify/Shops",
        ]
    }

def update_dashboard():
    data = {
        "timestamp": datetime.now().isoformat(),
        "system": get_system_stats(),
        "agents": get_agent_status(),
        "accounts": get_account_data(),
        "revenue": get_revenue_data(),
        "errors": get_recent_errors(20),
    }
    DASHBOARD_DATA.write_text(json.dumps(data, indent=2))
    return data

def main():
    print("[dashboard] 📊 Dashboard Data Server gestartet")
    print(f"[dashboard] Schreibt nach: {DASHBOARD_DATA}")

    while True:
        try:
            data = update_dashboard()
            print(f"[dashboard] {data['timestamp']} | RAM {data['system']['ram_pct']}% | "
                  f"Disk {data['system']['disk_pct']}% | Prozesse {data['system']['processes']} | "
                  f"Agents {sum(1 for a in data['agents'] if a['running'])}/{len(data['agents'])}")
        except Exception as e:
            print(f"[dashboard] ERROR: {e}")

        time.sleep(30)

if __name__ == "__main__":
    main()
