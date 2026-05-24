#!/usr/bin/env python3
"""🔴 Monitor Agent — Überwacht alle Services, Ports und Prozesse"""
import sys, os, time, socket, subprocess, urllib.request
sys.path.insert(0, os.path.expanduser("~/rudibot-army/shared"))
from bus import report, notify_telegram, load_state

ID = "monitor"
SERVICES = [
    ("RudiBot Server",   3200, "http://localhost:3200/api/status"),
    ("SuperMegaBot",     8888, "http://localhost:8888/health"),
    ("Ollama LLM",      11434, "http://localhost:11434/api/tags"),
    ("Redis",            6379, None),
    ("OpenClaw",        18789, None),
]

def check(port, url=None):
    if url:
        try:
            urllib.request.urlopen(url, timeout=3)
            return True
        except: pass
    try:
        s = socket.socket(); s.settimeout(1); s.connect(("127.0.0.1", port)); s.close(); return True
    except: return False

def fix_service(name, port):
    BOT_DIR = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/Documents/GitHub/telegram-automation-bot")
    MEGA_DIR = os.path.expanduser("~/supermegabot")
    cmds = {
        "RudiBot Server":  f"cd \"{BOT_DIR}\" && nohup node server.js >> /tmp/bot-server.log 2>&1 &",
        "SuperMegaBot":    f"cd {MEGA_DIR} && nohup python3 dashboard/server.py >> /tmp/mega.log 2>&1 &",
        "Ollama LLM":      "ollama serve >> /tmp/ollama.log 2>&1 &",
    }
    cmd = cmds.get(name)
    if cmd:
        subprocess.run(cmd, shell=True, timeout=10)
        time.sleep(3)
        return check(port)
    return False

def run():
    print(f"[{ID}] 🔴 Monitor Agent gestartet")
    fail_count = {s[0]: 0 for s in SERVICES}
    while True:
        summary = {}
        for name, port, url in SERVICES:
            ok = check(port, url)
            summary[name] = ok
            if not ok:
                fail_count[name] += 1
                if fail_count[name] >= 2:
                    print(f"[{ID}] 🔧 Repariere {name}...")
                    fixed = fix_service(name, port)
                    if fixed:
                        fail_count[name] = 0
                        notify_telegram(f"✅ <b>{name}</b> automatisch repariert")
                        report(ID, "repaired", f"{name} repariert", summary)
            else:
                fail_count[name] = 0
        ok_count = sum(summary.values())
        report(ID, "ok" if ok_count == len(SERVICES) else "warning",
               f"Services: {ok_count}/{len(SERVICES)} OK", summary)
        time.sleep(30)

if __name__ == "__main__":
    run()
