#!/usr/bin/env python3
"""🔐 Security Agent — VPN-Status, API-Keys, verdächtige Aktivitäten"""
import sys, os
import pathlib, pathlib, time, subprocess, json
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'shared'))
from bus import report, notify_telegram, get_env

ID = "security"
WARNED_VPN = False
WARNED_KEYS = set()

def check_vpn():
    """Prüft Mullvad VPN Status"""
    try:
        r = subprocess.run(["mullvad","status"], capture_output=True, text=True, timeout=5)
        connected = "connected" in r.stdout.lower()
        location = r.stdout.strip()
        return connected, location
    except:
        return None, "Mullvad nicht installiert/erreichbar"

def check_api_keys():
    """Prüft ob alle kritischen Keys gesetzt sind"""
    critical = ["TELEGRAM_BOT_TOKEN","ANTHROPIC_API_KEY","SHOPIFY_ACCESS_TOKEN","PRINTIFY_API_TOKEN"]
    missing = []
    for k in critical:
        v = get_env(k)
        if not v or v in ("","YOUR_TOKEN_HERE","APP_TOKEN_REQUIRED"):
            missing.append(k)
    return missing

def check_failed_logins():
    """Prüft Bot-Logs auf verdächtige Aktivität"""
    try:
        log = open("/tmp/bot-full.log", errors="ignore").read()[-5000:]
        suspicious = log.count("Unauthorized") + log.count("403") + log.count("blocked")
        return suspicious
    except: return 0

def run():
    global WARNED_VPN, WARNED_KEYS
    print(f"[{ID}] 🔐 Security Agent gestartet")
    while True:
        issues = []
        # VPN Check
        vpn_ok, vpn_loc = check_vpn()
        if vpn_ok is False and not WARNED_VPN:
            issues.append("⚠️ VPN GETRENNT — sensible Operationen pausieren")
            WARNED_VPN = True
        elif vpn_ok is True:
            WARNED_VPN = False
        
        # API Keys Check
        missing = check_api_keys()
        for k in missing:
            if k not in WARNED_KEYS:
                issues.append(f"⚠️ Key fehlt: {k}")
                WARNED_KEYS.add(k)
        WARNED_KEYS = WARNED_KEYS.intersection(set(missing))
        
        # Suspicious Activity
        suspicious = check_failed_logins()
        if suspicious > 10:
            issues.append(f"🚨 {suspicious} verdächtige Login-Versuche in Logs!")
        
        if issues:
            notify_telegram("🔐 <b>Security Alert:</b>\n" + "\n".join(issues))
        
        vpn_status = "verbunden" if vpn_ok else ("getrennt" if vpn_ok is False else "unbekannt")
        report(ID, "warning" if issues else "ok", 
               f"VPN:{vpn_status} | Keys:{len(missing)} fehlend | Suspicious:{suspicious}", {
                   "vpn": vpn_status, "vpn_location": vpn_loc,
                   "missing_keys": missing, "suspicious_count": suspicious, "issues": issues
               })
        time.sleep(60)

if __name__ == "__main__":
    run()
