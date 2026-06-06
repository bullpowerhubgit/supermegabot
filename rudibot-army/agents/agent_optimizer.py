#!/usr/bin/env python3
"""⚡ Optimizer Agent — Analysiert Performance, optimiert täglich, gibt Vorschläge"""
import sys, os, time, json, subprocess, re, datetime
sys.path.insert(0, os.path.expanduser("~/rudibot-army/shared"))
from bus import report, notify_telegram, load_state
from learner_mixin import AgentLearner

ID = "optimizer"
BOT_DIR = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/Documents/GitHub/telegram-automation-bot")

def analyze_performance():
    """Analysiert System-Performance und gibt Optimierungsvorschläge"""
    issues = []
    suggestions = []

    def _run(cmd, timeout=5):
        try:
            return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout).stdout
        except Exception:
            return ""

    # RAM Check via vm_stat
    ram_pct = 50.0
    ram_free_gb = 10.0
    vm_out = _run("vm_stat")
    if vm_out:
        vals = {}
        for line in vm_out.splitlines():
            if ":" in line:
                k = line.split(":")[0].strip().replace('"', '')
                v = line.split(":")[1].strip().rstrip('.')
                try:
                    vals[k] = int(v)
                except ValueError:
                    pass
        page = 16384
        used = vals.get("Pages active", 0) + vals.get("Pages wired down", 0) + vals.get("Pages occupied by compressor", 0)
        free = vals.get("Pages free", 0)
        total = used + free + vals.get("Pages inactive", 0) + vals.get("Pages speculative", 0)
        if total > 0:
            ram_pct = (used / total) * 100
            ram_free_gb = round((free * page) / (1024**3), 1)
    if ram_pct > 85:
        issues.append(f"RAM {ram_pct:.0f}% — bereinige Cache")
        subprocess.run("sync && sudo purge 2>/dev/null || true", shell=True, timeout=10)
        suggestions.append("npm cache clean --force")

    # CPU Check via top
    cpu = 0.0
    top_out = _run("top -l 1 -n 0 -s 0")
    m = re.search(r"CPU usage:\s+([\d.]+)%\s+user,\s+([\d.]+)%\s+sys", top_out)
    if m:
        cpu = float(m.group(1)) + float(m.group(2))
    if cpu > 90:
        issues.append(f"CPU {cpu:.0f}% — prüfe Prozesse")

    # Disk Check via df
    disk_pct = 0.0
    df_out = _run("df -h /")
    lines = df_out.strip().splitlines()
    if len(lines) >= 2:
        parts = lines[1].split()
        if len(parts) >= 5:
            try:
                disk_pct = float(parts[4].replace('%', ''))
            except ValueError:
                pass
    if disk_pct > 80:
        issues.append(f"Disk {disk_pct:.0f}% — bereinige Logs")
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
        "ram_percent": round(ram_pct, 1),
        "cpu_percent": round(cpu, 1),
        "disk_percent": round(disk_pct, 1),
        "ram_free_gb": ram_free_gb,
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
