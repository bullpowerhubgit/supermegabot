#!/usr/bin/env python3
"""📱 Social Agent — Autopilot für Social Media, plant Posts, überwacht Plattformen"""
import sys, os, time, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from bus import report, notify_telegram

ID = "social"

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8888")
AUTOPOST_INTERVAL = int(os.getenv("SOCIAL_AUTOPOST_INTERVAL", str(6 * 3600)))  # 6h default


def call_api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    import urllib.request
    try:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(f"{DASHBOARD_URL}{path}", data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        r = urllib.request.urlopen(req, timeout=15)
        return json.loads(r.read())
    except Exception:
        return {}


def run():
    print(f"[{ID}] 📱 Social Agent gestartet")
    last_autopost = 0

    while True:
        try:
            status = call_api("/api/telegram/status")
            connected = 1 if status.get("ok") or status.get("connected") else 0
            total = 1

            now = time.time()
            if connected >= 1 and (now - last_autopost) > AUTOPOST_INTERVAL:
                result = call_api("/api/geheimwaffe/run", "POST",
                                  {"task": "social_autopost", "platforms": ["instagram", "facebook"]})
                if result.get("ok") or result.get("product") or result.get("message"):
                    msg = result.get("product") or result.get("message") or "Post erstellt"
                    notify_telegram(f"📱 <b>Social Autopilot:</b> {msg}")
                    last_autopost = now

            last_str = time.strftime("%H:%M", time.localtime(last_autopost)) if last_autopost else "nie"
            report(ID, "ok",
                   f"Social: Telegram {'online' if connected else 'offline'} | Letzter Post: {last_str}",
                   {"connected": connected, "total": total, "last_autopost": last_str})

        except Exception as e:
            report(ID, "error", f"Fehler: {str(e)[:80]}")

        time.sleep(300)


if __name__ == "__main__":
    run()
