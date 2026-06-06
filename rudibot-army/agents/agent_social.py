#!/usr/bin/env python3
"""📱 Social Agent — Prüft Social-Media APIs auf Erreichbarkeit"""
import sys, os, time, urllib.request
sys.path.insert(0, os.path.expanduser("~/supermegabot/rudibot-army/shared"))
from bus import report, notify_telegram, get_env
from learner_mixin import AgentLearner

ID = "social"

PLATFORMS = [
    {"name": "Meta", "url": "https://graph.facebook.com/v18.0/me", "check": lambda r: r.get("error") is None or r.get("error", {}).get("code") == 190},
    {"name": "TikTok", "url": "https://business-api.tiktok.com/open_api/v1.3/user/info/", "check": lambda r: True},  # Nur Erreichbarkeit
]


def check_platform(name, url, check_fn):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RudiBot-Checker/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read().decode()
            try:
                import json
                json_data = json.loads(data)
                ok = check_fn(json_data)
            except Exception:
                ok = resp.status == 200
            return ok, resp.status
    except Exception as e:
        return False, str(e)[:40]


def run():
    print(f"[{ID}] 📱 Social Agent gestartet")
    learner = AgentLearner(ID)

    while True:
        try:
            results = []
            any_down = False

            for plat in PLATFORMS:
                ok, detail = check_platform(plat["name"], plat["url"], plat["check"])
                icon = "✅" if ok else "❌"
                results.append(f"{icon} {plat['name']} ({detail})")
                if not ok:
                    any_down = True

            status = "warning" if any_down else "ok"
            msg = "Social APIs OK" if not any_down else f"{sum(1 for r in results if r.startswith('❌'))} Platformen down"
            report(ID, status, msg, {"platforms": results})
            learner.log_cycle(status, msg, {"platform_count": len(PLATFORMS)})

        except Exception as e:
            report(ID, "error", str(e)[:80])

        time.sleep(600)


if __name__ == "__main__":
    run()
