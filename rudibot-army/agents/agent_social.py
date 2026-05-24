#!/usr/bin/env python3
"""📱 Social Agent — Autopilot für Social Media, plant Posts, überwacht Plattformen"""
import sys, os, time, json
sys.path.insert(0, os.path.expanduser("~/rudibot-army/shared"))
from bus import report, notify_telegram, load_state

ID = "social"

def call_api(path, method="GET", body=None):
    import urllib.request
    try:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(f"http://localhost:3200{path}", data=data, method=method)
        if data: req.add_header("Content-Type","application/json")
        r = urllib.request.urlopen(req, timeout=15)
        return json.loads(r.read())
    except: return {}

def run():
    print(f"[{ID}] 📱 Social Agent gestartet")
    last_autopost = 0
    AUTOPOST_INTERVAL = 21600  # 6h
    while True:
        try:
            status = call_api("/api/social/platform-status")
            connected = status.get("connected", 0)
            total = status.get("total", 8)
            
            # Auto-Post alle 6h wenn mehr als 2 Plattformen verbunden
            now = time.time()
            if connected >= 2 and (now - last_autopost) > AUTOPOST_INTERVAL:
                result = call_api("/api/social/autopost", "POST",
                                  {"platforms":["instagram","facebook","pinterest"]})
                if result.get("product") or result.get("message"):
                    notify_telegram(f"📱 <b>Social Autopilot:</b> {result.get('product','Post erstellt')}")
                    last_autopost = now
            
            report(ID, "ok", f"Social: {connected}/{total} Plattformen verbunden", {
                "connected": connected, "total": total,
                "last_autopost": time.strftime("%H:%M", time.localtime(last_autopost)) if last_autopost else "nie"
            })
        except Exception as e:
            report(ID, "error", f"Fehler: {str(e)[:80]}")
        time.sleep(300)  # alle 5 Minuten

if __name__ == "__main__":
    run()
