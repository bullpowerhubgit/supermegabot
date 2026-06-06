#!/usr/bin/env python3
"""🧹 Micro-Clean — Stündliche Log-Rotation + Disk-Schutz"""
import sys, os, subprocess
import pathlib, time, glob
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'shared'))
from bus import report, notify_telegram

ID = "micro_clean"
INTERVAL = 3600  # Stündlich
MAX_LOG_MB = 30
KEEP_LINES = 3000

LOG_FILES = [
    "/tmp/supermegabot.log",
    "/tmp/bot-server.log",
    "/tmp/bot-full.log",
    "/tmp/telegram-bot-pm2.log",
    "/tmp/mega-orchestrator-pm2.log",
    "/tmp/rudibot-army-pm2.log",
    "/tmp/rudibot-eternal-pm2.log",
    "/tmp/cratorhub-pm2.log",
    "/tmp/windsurf-shopify-pm2.log",
    "/tmp/windsurf-autoheal-pm2.log",
    "/tmp/windsurf-api-gateway-pm2.log",
    "/tmp/windsurf-telegram-bot-pm2.log",
    "/tmp/windsurf-monitor-pm2.log",
    "/tmp/ollama.log",
]

def clean_logs() -> tuple:
    cleaned = []
    total_saved_mb = 0.0

    for path in LOG_FILES:
        try:
            if not os.path.exists(path):
                continue
            size_mb = os.path.getsize(path) / 1_048_576
            if size_mb > MAX_LOG_MB:
                with open(path, errors="ignore") as f:
                    lines = f.readlines()[-KEEP_LINES:]
                with open(path, "w") as f:
                    f.writelines(lines)
                saved = size_mb - (os.path.getsize(path) / 1_048_576)
                total_saved_mb += saved
                cleaned.append(f"{os.path.basename(path)}: {size_mb:.0f}MB→{KEEP_LINES} Zeilen")
        except Exception:
            pass

    # /tmp alte .log Dateien (>7 Tage) löschen
    subprocess.run("find /tmp -name '*.log' -mtime +7 -delete 2>/dev/null",
                   shell=True, timeout=15)

    # Army-eigene Logs
    army_logs = glob.glob(str(pathlib.Path(__file__).parent.parent / "logs" / "*.log"))
    for path in army_logs:
        try:
            size_mb = os.path.getsize(path) / 1_048_576
            if size_mb > 10:
                with open(path, errors="ignore") as f:
                    lines = f.readlines()[-1000:]
                with open(path, "w") as f:
                    f.writelines(lines)
                cleaned.append(f"army/{os.path.basename(path)}: rotiert")
        except Exception:
            pass

    return cleaned, total_saved_mb

def run():
    print(f"[{ID}] 🧹 Micro-Clean gestartet")
    daily_saves = 0.0

    while True:
        cleaned, saved_mb = clean_logs()
        daily_saves += saved_mb

        if cleaned:
            notify_telegram(
                f"🧹 <b>Log-Rotation</b>\n" +
                "\n".join(f"• {c}" for c in cleaned[:6]) +
                f"\n💾 {saved_mb:.1f} MB freigegeben"
            )

        # Disk check via df (no psutil dependency)
        disk_pct = 0.0
        try:
            df_out = subprocess.run("df -h /", shell=True, capture_output=True, text=True, timeout=5).stdout
            lines = df_out.strip().splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    disk_pct = float(parts[4].replace('%', ''))
        except Exception:
            pass
        status = "warning" if disk_pct > 85 else "ok"
        report(ID, status,
               f"Disk: {disk_pct:.0f}% | Rotiert: {len(cleaned)} Logs | Gespart: {daily_saves:.1f}MB",
               {"disk_percent": round(disk_pct, 1), "cleaned": len(cleaned), "saved_mb": round(saved_mb, 1)})

        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
