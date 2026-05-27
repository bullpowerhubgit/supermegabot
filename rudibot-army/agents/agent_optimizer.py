#!/usr/bin/env python3
"""⚡ Optimizer Agent — Analysiert Performance, optimiert täglich, gibt Vorschläge"""
import sys, os, time, json, subprocess, psutil, datetime
from pathlib import Path

ARMY_DIR = Path(__file__).resolve().parent.parent
SHARED_DIR = ARMY_DIR / "shared"
sys.path.insert(0, str(SHARED_DIR))
from bus import report, notify_telegram, load_state
from learner_mixin import AgentLearner

ID = "optimizer"
BOT_DIR = os.path.expanduser(
    os.getenv(
        "RUDIBOT_MAIN_DIR",
        "~/Library/Mobile Documents/com~apple~CloudDocs/Documents/GitHub/telegram-automation-bot",
    )
)

def analyze_performance():
    """Analysiert System-Performance und gibt Optimierungsvorschläge"""
    issues = []
    suggestions = []
    
    # RAM Check
    mem = psutil.virtual_memory()
    if mem.percent > 85:
        issues.append(f"RAM {mem.percent:.0f}% — bereinige Cache")
        subprocess.run("sync && sudo purge 2>/dev/null || true", shell=True, timeout=10)
        suggestions.append("npm cache clean --force")
    
    # CPU Check
    cpu = psutil.cpu_percent(interval=2)
    if cpu > 90:
        issues.append(f"CPU {cpu:.0f}% — prüfe Prozesse")
    
    # Disk Check
    disk = psutil.disk_usage("/")
    if disk.percent > 80:
        issues.append(f"Disk {disk.percent:.0f}% — bereinige Logs")
        subprocess.run("find /tmp -name '*.log' -mtime +7 -delete 2>/dev/null", shell=True, timeout=20)
    
    # Log-Größen
    for logfile in ["/tmp/bot-server.log", "/tmp/bot-full.log", "/tmp/supermegabot.log"]:
        try:
            size_mb = os.path.getsize(logfile) / 1048576
            if size_mb > 50:
                content = open(logfile, errors="ignore").readlines()[-5000:]
                open(logfile, "w").writelines(content)
                suggestions.append(f"Log rotiert: {os.path.basename(logfile)} ({size_mb:.0f}MB → 5000 Zeilen)")
        except: pass
    
    return issues, suggestions, {
        "ram_percent": mem.percent,
        "cpu_percent": cpu,
        "disk_percent": disk.percent,
        "ram_free_gb": round(mem.available / 1e9, 1)
    }

def run():
    print(f"[{ID}] ⚡ Optimizer Agent gestartet")
    learner = AgentLearner(ID)
    learner.register("performance", lambda: str(analyze_performance()[2]), "Aktuelle System-Metriken")

    last_report_day = None
    while True:
        try:
            issues, suggestions, metrics = analyze_performance()
            today = datetime.date.today()

            if today != last_report_day and suggestions:
                notify_telegram(f"⚡ <b>Optimizer:</b> {len(suggestions)} Optimierungen\n" + "\n".join(f"• {s}" for s in suggestions[:5]))
                last_report_day = today

            status = "warning" if issues else "ok"
            cpu_p  = metrics["cpu_percent"]
            ram_p  = metrics["ram_percent"]
            disk_p = metrics["disk_percent"]
            msg = f"CPU:{cpu_p:.0f}% RAM:{ram_p:.0f}% Disk:{disk_p:.0f}%"
            report(ID, status, msg, {**metrics, "issues": issues, "suggestions": suggestions})
            learner.log_cycle(status, msg, metrics)
        except Exception as e:
            report(ID, "error", str(e)[:80])
        time.sleep(120)

if __name__ == "__main__":
    run()
