#!/usr/bin/env python3
"""💾 Micro-Backup — Täglicher Auto-Commit + GitHub Push"""
import sys, os, time, subprocess, datetime
from pathlib import Path

ARMY_DIR = Path(__file__).resolve().parent.parent
SHARED_DIR = ARMY_DIR / "shared"
sys.path.insert(0, str(SHARED_DIR))
from bus import report, notify_telegram

ID = "micro_backup"
INTERVAL = 86400  # Täglich
MEGA_DIR = str(ARMY_DIR.parent)

REPOS = [
    {
        "path": MEGA_DIR,
        "name": "supermegabot",
        "remote": "git@github.com:bullpowerhubgit/supermegabot.git",
    }
]

def git_backup(repo: dict) -> str:
    path = repo["path"]
    name = repo["name"]
    if not os.path.exists(path):
        return f"❌ {name}: Pfad nicht gefunden"

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        # Stage alle Änderungen (keine Secrets)
        subprocess.run(["git", "-C", path, "add",
                        "modules/", "core/", "dashboard/",
                        "ecosystem.config.js", "start_all.sh",
                        "rudibot-army/"],
                       capture_output=True, timeout=30)

        # Prüfe ob es etwas zu committen gibt
        r = subprocess.run(["git", "-C", path, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=10)
        if not r.stdout.strip():
            return f"✅ {name}: Nichts zu committen"

        # Commit
        msg = f"Auto-Backup {ts}"
        subprocess.run(["git", "-C", path, "commit", "-m", msg],
                       capture_output=True, timeout=30)

        # Push
        pr = subprocess.run(["git", "-C", path, "push", "origin", "main"],
                            capture_output=True, text=True, timeout=60)
        if pr.returncode == 0:
            return f"✅ {name}: Backup OK ({ts})"
        else:
            return f"⚠️ {name}: Push-Fehler: {pr.stderr[:100]}"
    except Exception as e:
        return f"❌ {name}: {e}"

def run():
    print(f"[{ID}] 💾 Micro-Backup gestartet — {len(REPOS)} Repos")
    # Erster Backup direkt nach Start (nach 5min Verzögerung)
    time.sleep(300)

    while True:
        results = [git_backup(r) for r in REPOS]
        summary = "\n".join(results)
        all_ok = all("✅" in r for r in results)

        notify_telegram(f"💾 <b>Auto-Backup</b>\n{summary}")
        report(ID, "ok" if all_ok else "warning", summary[:100], {"results": results})
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
