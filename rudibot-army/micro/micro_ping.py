#!/usr/bin/env python3
"""🏓 Micro-Ping — Überwacht alle Services, sofort-Alert per Telegram"""
import sys, os
import pathlib, time, socket, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'shared'))
from bus import report, notify_telegram

ID = "micro_ping"
INTERVAL = 60  # Sekunden

SERVICES = [
    ("SuperMegaBot",     "http://localhost:8888/health"),
    ("Telegram Bot",     "http://localhost:3200/api/status"),
    ("Ollama",           "http://localhost:11434/api/tags"),
    ("Password-Sync",    "http://localhost:3005/health"),
    ("API-Gateway",      "http://localhost:8080/health"),
    ("Autoheal",         "http://localhost:9000/health"),
]

_was_down = set()

def check_service(name, url):
    try:
        req = urllib.request.urlopen(url, timeout=5)
        return req.getcode() < 500
    except:
        return False

def run():
    print(f"[{ID}] 🏓 Micro-Ping gestartet — {len(SERVICES)} Services")
    while True:
        down = []
        recovered = []
        for name, url in SERVICES:
            up = check_service(name, url)
            if not up and name not in _was_down:
                down.append(name)
                _was_down.add(name)
            elif up and name in _was_down:
                recovered.append(name)
                _was_down.discard(name)

        if down:
            notify_telegram("🔴 <b>DOWN:</b> " + ", ".join(down))
        if recovered:
            notify_telegram("🟢 <b>RECOVERED:</b> " + ", ".join(recovered))

        total = len(SERVICES)
        up_count = total - len(_was_down)
        report(ID, "warning" if _was_down else "ok",
               f"{up_count}/{total} Services UP",
               {"down": list(_was_down)})
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
