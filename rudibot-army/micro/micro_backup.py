#!/usr/bin/env python3
"""💾 Micro-Backup — Täglicher Auto-Commit + GitHub Push"""
import sys, os, time, subprocess, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from bus import report, notify_telegram

ID = "micro_backup"
INTERVAL = 86400  # Täglich

# Projekt-Root dynamisch
ARMY_DIR = Path(__file__).parent.parent
MEGA_DIR = ARMY_DIR.parent

REPOS = [
    {
        "path": str(MEGA_DIR),
        "name": "supermegabot",
    }
]


def git_backup(repo: dict) -> str:
    path = repo["path"]
    name = repo["name"]

    if not os.path.exists(path):
        return f"❌ {name}: Pfad nicht gefunden ({path})"

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        # Stage relevante Verzeichnisse (keine Secrets/data)
        subprocess.run(
            ["git", "-C", path, "add",
             "modules/", "core/", "dashboard/",
             "ecosystem.config.js", "start_all.sh", "rudibot-army/"],
            capture_output=True, timeout=30,
        )

        # Prüfen ob etwas zu committen ist
        r = subprocess.run(
            ["git", "-C", path, "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if not r.stdout.strip():
            return f"✅ {name}: Nichts zu committen"

        # Commit
        subprocess.run(
            ["git", "-C", path, "commit", "-m", f"Auto-Backup {ts}"],
            capture_output=True, timeout=30,
        )

        # Push (Branch aus aktuell geladenem Branch)
        branch_r = subprocess.run(
            ["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        branch = branch_r.stdout.strip() or "main"

        pr = subprocess.run(
            ["git", "-C", path, "push", "origin", branch],
            capture_output=True, text=True, timeout=60,
        )
        if pr.returncode == 0:
            return f"✅ {name}: Backup OK ({ts})"
        else:
            return f"⚠️ {name}: Push-Fehler: {pr.stderr[:100]}"

    except Exception as e:
        return f"❌ {name}: {e}"


def run():
    print(f"[{ID}] 💾 Micro-Backup gestartet — {len(REPOS)} Repos")
    time.sleep(300)  # 5 Minuten warten damit andere Services zuerst starten

    while True:
        results = [git_backup(r) for r in REPOS]
        summary = "\n".join(results)
        all_ok = all("✅" in r for r in results)

        notify_telegram(f"💾 <b>Auto-Backup</b>\n{summary}")
        report(ID, "ok" if all_ok else "warning", summary[:100], {"results": results})
        time.sleep(INTERVAL)


if __name__ == "__main__":
    run()
