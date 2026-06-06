#!/usr/bin/env python3
"""💰 Finance Agent — Trackt Umsatz, Kosten, gibt täglichen Report"""
import sys, os, time, json
sys.path.insert(0, os.path.expanduser("~/supermegabot/rudibot-army/shared"))
from bus import report, notify_telegram, get_env
from learner_mixin import AgentLearner

ID = "finance"


def run():
    print(f"[{ID}] 💰 Finance Agent gestartet")
    learner = AgentLearner(ID)
    daily_reported = None

    while True:
        try:
            now = time.localtime()
            today = time.strftime("%Y-%m-%d", now)

            # Dummy-Metriken (könnten später aus Shopify/Stripe gezogen werden)
            metrics = {
                "day": today,
                "timestamp": time.strftime("%H:%M"),
            }

            status = "ok"
            msg = f"Finance check {today} {metrics['timestamp']}"

            # Täglicher Report um 08:00
            if now.tm_hour == 8 and daily_reported != today:
                notify_telegram(f"💰 <b>Finance Daily:</b> {today} — System läuft")
                daily_reported = today

            report(ID, status, msg, metrics)
            learner.log_cycle(status, msg, metrics)

        except Exception as e:
            report(ID, "error", str(e)[:80])

        time.sleep(3600)


if __name__ == "__main__":
    run()
