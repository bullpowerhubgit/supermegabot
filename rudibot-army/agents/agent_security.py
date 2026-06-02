#!/usr/bin/env python3
"""🔐 Security Agent — Prüft auf Failed Logins, ungewöhnliche Aktivität"""
import sys, os, time, glob, re
sys.path.insert(0, os.path.expanduser("~/rudibot-army/shared"))
from bus import report, notify_telegram
from learner_mixin import AgentLearner

ID = "security"
SUSPICIOUS_PATTERNS = [
    re.compile(r"failed login|authentication failed|unauthorized", re.I),
    re.compile(r"error.*password|invalid.*credentials", re.I),
    re.compile(r"port scan|intrusion attempt|suspicious", re.I),
]
LOG_PATHS = [
    os.path.expanduser("~/supermegabot/dashboard/server.log"),
    os.path.expanduser("~/supermegabot/logs/*.log"),
    "/tmp/supermegabot.log",
    "/tmp/rudibot-army.log",
]


def scan_logs():
    findings = []
    for pattern in LOG_PATHS:
        for logfile in glob.glob(pattern) if "*" in pattern else [pattern]:
            if not os.path.exists(logfile):
                continue
            try:
                with open(logfile, "r", errors="ignore") as f:
                    lines = f.readlines()
                for i, line in enumerate(lines[-500:], start=max(0, len(lines) - 500)):
                    for pat in SUSPICIOUS_PATTERNS:
                        if pat.search(line):
                            findings.append(f"{os.path.basename(logfile)}:{i+1}: {line.strip()[:80]}")
                            if len(findings) >= 10:
                                return findings
            except Exception:
                continue
    return findings


def run():
    print(f"[{ID}] 🔐 Security Agent gestartet")
    learner = AgentLearner(ID)
    last_alerted = 0

    while True:
        try:
            findings = scan_logs()
            status = "warning" if findings else "ok"
            msg = f"{len(findings)} verdächtige Einträge" if findings else "Logs sauber"

            report(ID, status, msg, {"findings": findings[:5]})
            learner.log_cycle(status, msg, {"findings_count": len(findings)})

            # Alert nur alle 30 min max
            if findings and time.time() - last_alerted > 1800:
                notify_telegram(f"🔐 <b>Security:</b> {len(findings)} verdächtige Log-Einträge gefunden")
                last_alerted = time.time()

        except Exception as e:
            report(ID, "error", str(e)[:80])

        time.sleep(300)


if __name__ == "__main__":
    run()
