#!/usr/bin/env python3
"""🧠 Learner Agent — Sammelt Patterns aus allen Agenten, schlägt Verbesserungen vor"""
import sys, os, time, json
sys.path.insert(0, os.path.expanduser("~/rudibot-army/shared"))
from bus import report, notify_telegram, load_state
from learner_mixin import AgentLearner

ID = "learner"


def run():
    print(f"[{ID}] 🧠 Learner Agent gestartet")
    learner = AgentLearner(ID)

    while True:
        try:
            state = load_state()
            agents = state.get("agents", {})
            events = state.get("events", [])[-50:]

            # Zähle Fehler pro Agent
            error_counts = {}
            warning_counts = {}
            for ev in events:
                agent = ev.get("agent", "?")
                info = agents.get(agent, {})
                st = info.get("status", "?")
                if st == "error":
                    error_counts[agent] = error_counts.get(agent, 0) + 1
                elif st == "warning":
                    warning_counts[agent] = warning_counts.get(agent, 0) + 1

            insights = []
            if error_counts:
                insights.append("Fehler: " + ", ".join(f"{k}({v})" for k, v in error_counts.items()))
            if warning_counts:
                insights.append("Warnings: " + ", ".join(f"{k}({v})" for k, v in warning_counts.items()))

            msg = "; ".join(insights) if insights else "Keine neuen Patterns"
            status = "warning" if error_counts else "ok"

            report(ID, status, msg, {
                "agents_tracked": len(agents),
                "errors": error_counts,
                "warnings": warning_counts,
            })
            learner.log_cycle(status, msg, {"tracked": len(agents)})

        except Exception as e:
            report(ID, "error", str(e)[:80])

        time.sleep(300)


if __name__ == "__main__":
    run()
