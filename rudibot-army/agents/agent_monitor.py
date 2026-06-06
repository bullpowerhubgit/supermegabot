#!/usr/bin/env python3
"""🔴 Monitor Agent — Überwacht Services, Ports, meldet Ausfälle"""
import sys, os, time, socket, urllib.request
sys.path.insert(0, os.path.expanduser("~/supermegabot/rudibot-army/shared"))
from bus import report, notify_telegram, load_state
from learner_mixin import AgentLearner

ID = "monitor"
SERVICES = [
    {"name": "RudiBot", "host": "127.0.0.1", "port": 3200, "url": "http://127.0.0.1:3200/api/health"},
    {"name": "SuperMegaBot", "host": "127.0.0.1", "port": 8888, "url": "http://127.0.0.1:8888/api/health"},
    {"name": "Ollama", "host": "127.0.0.1", "port": 11434, "url": "http://127.0.0.1:11434/api/tags"},
    {"name": "PasswordSync", "host": "127.0.0.1", "port": 3005, "url": "http://127.0.0.1:3005/health"},
]


def check_port(host, port, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def check_http(url, timeout=5):
    try:
        req = urllib.request.Request(url, method="HEAD")
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        try:
            req = urllib.request.Request(url, method="GET")
            urllib.request.urlopen(req, timeout=timeout)
            return True
        except Exception:
            return False


def run():
    print(f"[{ID}] 🔴 Monitor Agent gestartet")
    learner = AgentLearner(ID)
    down_history = {}

    while True:
        try:
            statuses = []
            down_now = []

            for svc in SERVICES:
                port_ok = check_port(svc["host"], svc["port"])
                http_ok = check_http(svc["url"]) if svc.get("url") else port_ok
                ok = port_ok and http_ok
                icon = "✅" if ok else "❌"
                statuses.append(f"{icon} {svc['name']}")
                if not ok:
                    down_now.append(svc["name"])
                    down_history[svc["name"]] = down_history.get(svc["name"], 0) + 1

            status = "warning" if down_now else "ok"
            msg = f"{len(down_now)}/{len(SERVICES)} down" if down_now else "alle Services OK"
            report(ID, status, msg, {"checks": statuses, "down": down_now})
            learner.log_cycle(status, msg, {"down_count": len(down_now)})

            # Telegram nur bei Neu-Ausfall oder Wiederherstellung
            for svc_name in down_now:
                if down_history.get(svc_name, 0) == 1:
                    notify_telegram(f"🔴 <b>Monitor:</b> {svc_name} ist DOWN")

        except Exception as e:
            report(ID, "error", str(e)[:80])

        time.sleep(60)


if __name__ == "__main__":
    run()
