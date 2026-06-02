#!/usr/bin/env python3
"""⚡ Optimizer Agent — Analysiert Performance, optimiert täglich, gibt Vorschläge"""
import sys, os, time, json, subprocess, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from bus import report, notify_telegram

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

ID = "optimizer"
ARMY_DIR = Path(__file__).parent.parent
MEGA_DIR = ARMY_DIR.parent


def free_ram_linux():
    """Linux: Dropped caches freigeben (ohne sudo nicht möglich, aber sync hilft)."""
    try:
        subprocess.run(["sync"], timeout=5)
    except Exception:
        pass


def analyze_performance() -> tuple[list, list, dict]:
    issues: list[str] = []
    suggestions: list[str] = []
    metrics: dict = {}

    if not HAS_PSUTIL:
        return issues, ["psutil nicht installiert — pip3 install psutil"], metrics

    # RAM
    mem = psutil.virtual_memory()
    metrics["ram_percent"] = mem.percent
    metrics["ram_free_gb"] = round(mem.available / 1e9, 1)
    if mem.percent > 85:
        issues.append(f"RAM {mem.percent:.0f}%")
        free_ram_linux()
        suggestions.append(f"RAM bei {mem.percent:.0f}% — sync ausgeführt")

    # CPU
    cpu = psutil.cpu_percent(interval=2)
    metrics["cpu_percent"] = cpu
    if cpu > 90:
        issues.append(f"CPU {cpu:.0f}%")
        suggestions.append(f"CPU-Last hoch: {cpu:.0f}%")

    # Disk
    disk = psutil.disk_usage("/")
    metrics["disk_percent"] = disk.percent
    if disk.percent > 80:
        issues.append(f"Disk {disk.percent:.0f}%")
        # Alte /tmp Logs löschen (sicher)
        subprocess.run(
            "find /tmp -name '*.log' -mtime +7 -delete 2>/dev/null || true",
            shell=True, timeout=20,
        )
        suggestions.append(f"Disk {disk.percent:.0f}% — alte /tmp Logs bereinigt")

    # Log-Rotation für bekannte Log-Dateien
    log_paths = [
        "/tmp/supermegabot.log",
        "/tmp/mega.log",
        "/tmp/ollama.log",
        "/tmp/rudibot-army.log",
    ]
    for logfile in log_paths:
        try:
            size_mb = os.path.getsize(logfile) / 1_048_576
            if size_mb > 50:
                lines = open(logfile, errors="ignore").readlines()[-5000:]
                open(logfile, "w").writelines(lines)
                suggestions.append(f"Log rotiert: {os.path.basename(logfile)} ({size_mb:.0f}MB → 5000 Zeilen)")
        except Exception:
            pass

    return issues, suggestions, metrics


def run():
    print(f"[{ID}] ⚡ Optimizer Agent gestartet")
    last_report_day = None

    while True:
        try:
            issues, suggestions, metrics = analyze_performance()
            today = datetime.date.today()

            if today != last_report_day and suggestions:
                notify_telegram(
                    f"⚡ <b>Optimizer:</b> {len(suggestions)} Optimierungen\n"
                    + "\n".join(f"• {s}" for s in suggestions[:5])
                )
                last_report_day = today

            status = "warning" if issues else "ok"
            cpu_p  = metrics.get("cpu_percent", 0)
            ram_p  = metrics.get("ram_percent", 0)
            disk_p = metrics.get("disk_percent", 0)
            msg = f"CPU:{cpu_p:.0f}% RAM:{ram_p:.0f}% Disk:{disk_p:.0f}%"
            report(ID, status, msg, {**metrics, "issues": issues, "suggestions": suggestions})

        except Exception as e:
            report(ID, "error", str(e)[:80])

        time.sleep(120)


if __name__ == "__main__":
    run()
