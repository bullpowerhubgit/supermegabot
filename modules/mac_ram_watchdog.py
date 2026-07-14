"""
Mac RAM + Swap + Prozess Watchdog — Permanent immer aktiv
==========================================================
• Swap-Auslastung überwachen → bei >80% auto-bereinigen
• Runaway-Prozesse killen (Comet, Chrome-Renderer, etc.)
• Disk-Cleaner triggern wenn <20 GB frei
• TM-Snapshots auto-löschen wenn Disk <15 GB frei
• Telegram-Alarm bei kritischen Zuständen
• Läuft alle 10 Minuten via LaunchAgent

Dieser Watchdog ergänzt mac_watchdog.py (alle 5 Min) und
mac_disk_cleaner.py (täglich 3:00 Uhr).
"""

import os
import sys
import subprocess
import logging
import json
import psutil
import shutil
from datetime import datetime, timezone
from pathlib import Path

# Logging
log = logging.getLogger("RamWatchdog")

HOME = Path.home()
PROJECT_DIR = HOME / "supermegabot"
STATE_FILE  = PROJECT_DIR / "data" / "ram_watchdog_state.json"

# Credentials
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

# Schwellenwerte
SWAP_WARN_PCT      = 75   # % Swap belegt → Warnung
SWAP_CRIT_PCT      = 88   # % Swap belegt → kritisch + auto-kill
RAM_WARN_PCT       = 85   # % RAM belegt → Warnung
DISK_CLEAN_GB      = 20   # GB frei → Disk-Cleaner triggern
DISK_CRIT_GB       = 10   # GB frei → TM-Snapshots löschen
COMET_MAX_PROCS    = 20   # Comet-Prozesse: über diesem Limit → killen
CHROME_MAX_PROCS   = 25   # Chrome/Brave Renderer über Limit → killen
ALERT_COOLDOWN_MIN = 20   # Minuten zwischen gleichen Alerts


# ── State ──────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"alerted": {}, "actions": [], "last_run": ""}


def _save_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False))


def _cooldown_ok(state: dict, key: str, minutes: int = ALERT_COOLDOWN_MIN) -> bool:
    last = state.get("alerted", {}).get(key)
    if not last:
        return True
    delta = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds()
    return delta > minutes * 60


def _mark_alerted(state: dict, key: str) -> None:
    state.setdefault("alerted", {})[key] = datetime.now(timezone.utc).isoformat()


# ── Telegram ────────────────────────────────────────────────────────────────

def _tg(text: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        log.info("TG (kein Token): %s", text[:80])
        return
    try:
        subprocess.run([
            "curl", "-s", "-X", "POST",
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            "-d", f"chat_id={TG_CHAT}&parse_mode=Markdown&text={text}"
        ], timeout=10, capture_output=True)
    except Exception as e:
        log.debug("TG Fehler: %s", e)


# ── RAM + Swap Monitoring ───────────────────────────────────────────────────

def get_swap_usage() -> dict:
    """Liefert Swap-Statistiken via sysctl."""
    try:
        import re
        out = subprocess.check_output(
            ["sysctl", "vm.swapusage"], text=True, timeout=5
        )
        # Format: vm.swapusage: total = 50176,00M  used = 49017,00M  free = 1159,00M
        nums = re.findall(r"[\d,\.]+M", out)
        def parse_mb(s): return float(s.replace("M", "").replace(",", "."))
        total = parse_mb(nums[0]) if len(nums) > 0 else 0
        used  = parse_mb(nums[1]) if len(nums) > 1 else 0
        free  = parse_mb(nums[2]) if len(nums) > 2 else 0
        pct   = (used / total * 100) if total > 0 else 0
        return {"total_gb": total/1024, "used_gb": used/1024,
                "free_gb": free/1024, "pct": round(pct, 1)}
    except Exception as e:
        log.debug("swap_usage: %s", e)
        return {"total_gb": 0, "used_gb": 0, "free_gb": 99, "pct": 0}


def get_ram_usage() -> dict:
    """Liefert RAM-Statistiken."""
    try:
        vm = psutil.virtual_memory()
        return {
            "total_gb": vm.total / 1024**3,
            "used_gb":  vm.used  / 1024**3,
            "free_gb":  vm.available / 1024**3,
            "pct":      vm.percent,
        }
    except Exception as e:
        log.debug("ram_usage: %s", e)
        return {"total_gb": 48, "used_gb": 0, "free_gb": 48, "pct": 0}


def get_disk_free_gb() -> float:
    try:
        return shutil.disk_usage("/").free / 1024**3
    except Exception:
        return 999.0


# ── Prozess-Management ──────────────────────────────────────────────────────

def _count_and_kill_runaway(name_pattern: str, max_procs: int, keep_main: bool = True) -> int:
    """
    Findet alle Prozesse die name_pattern enthalten.
    Wenn mehr als max_procs laufen, werden die ältesten Helper-Prozesse gekillt.
    Gibt Anzahl der gekillten Prozesse zurück.
    """
    procs = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "memory_info"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if name_pattern.lower() in cmd.lower():
                procs.append({
                    "pid": p.pid,
                    "cmd": cmd[:80],
                    "age": p.info["create_time"],
                    "rss": p.info["memory_info"].rss if p.info.get("memory_info") else 0,
                    "is_helper": any(x in cmd for x in ["Helper", "Renderer", "GPU", "Worker", "crashpad"]),
                })
        except Exception:
            pass

    if len(procs) <= max_procs:
        return 0

    # Nur Helper-Prozesse killen, nicht den Haupt-Prozess
    helpers = [p for p in procs if p["is_helper"]]
    to_kill = sorted(helpers, key=lambda x: x["rss"], reverse=True)
    to_kill = to_kill[:len(procs) - max_procs]

    killed = 0
    for p in to_kill:
        try:
            proc = psutil.Process(p["pid"])
            proc.terminate()
            killed += 1
            log.info("Prozess gekillt: PID %d (%s, RSS %.0f MB)",
                     p["pid"], p["cmd"][:40], p["rss"]/1024**2)
        except Exception as e:
            log.debug("Kill PID %d: %s", p["pid"], e)

    return killed


def kill_runaway_processes() -> dict:
    """Killt überzählige Helper-Prozesse von bekannten RAM-Fressern."""
    killed = {}

    # Comet-Browser (häufig 90+ Prozesse)
    n = _count_and_kill_runaway("Comet", COMET_MAX_PROCS)
    if n > 0:
        killed["Comet"] = n

    # Chrome Renderer
    n = _count_and_kill_runaway("Google Chrome", CHROME_MAX_PROCS)
    if n > 0:
        killed["Chrome"] = n

    # Brave Renderer
    n = _count_and_kill_runaway("Brave Browser", CHROME_MAX_PROCS)
    if n > 0:
        killed["Brave"] = n

    return killed


# ── Disk Cleanup ─────────────────────────────────────────────────────────────

def trigger_disk_cleanup(force: bool = False) -> dict:
    """Ruft mac_disk_cleaner.run_full_cleanup auf."""
    try:
        sys.path.insert(0, str(PROJECT_DIR))
        from modules.mac_disk_cleaner import run_full_cleanup
        return run_full_cleanup(force=force)
    except Exception as e:
        log.error("Disk cleanup Fehler: %s", e)
        return {"error": str(e)}


def delete_tm_snapshots() -> int:
    """Löscht lokale Time Machine Snapshots."""
    try:
        result = subprocess.run(
            ["tmutil", "deletelocalsnapshots", "/"],
            capture_output=True, text=True, timeout=60
        )
        lines = result.stdout.strip().split("\n")
        count = len([l for l in lines if "Deleted" in l or ".local" in l])
        log.info("TM-Snapshots gelöscht: %d", count)
        return count
    except Exception as e:
        log.error("TM-Snapshot-Löschung: %s", e)
        return 0


def evict_icloud_cache() -> None:
    """Startet iCloud-Eviction im Hintergrund."""
    icloud = HOME / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    targets = [
        str(icloud / "ARCHIVES" / "MacOffload"),
        str(icloud / "ARCHIVES" / ".git-home-backup-2026-07-12"),
        str(icloud / "Downloads"),
    ]
    for target in targets:
        if os.path.exists(target):
            subprocess.Popen(
                f'find "{target}" -type f -size +0c | head -2000 | xargs -P 4 -n 50 brctl evict 2>/dev/null',
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )


# ── Haupt-Watchdog-Loop ─────────────────────────────────────────────────────

def run_ram_watchdog() -> dict:
    """
    Vollständiger RAM/Swap/Prozess-Check.
    Wird alle 10 Minuten via LaunchAgent aufgerufen.
    """
    state   = _load_state()
    result  = {"actions": [], "alerts": [], "ok": True}
    now     = datetime.now(timezone.utc).isoformat()

    swap = get_swap_usage()
    ram  = get_ram_usage()
    disk_gb = get_disk_free_gb()

    log.info("Status: Swap %.1f%% (%.1f/%.1f GB) | RAM %.1f%% | Disk %.1f GB frei",
             swap["pct"], swap["used_gb"], swap["total_gb"],
             ram["pct"], disk_gb)

    # ── 1. Swap-Überwachung ──────────────────────────────────────────────────
    if swap["pct"] >= SWAP_CRIT_PCT:
        result["ok"] = False

        if _cooldown_ok(state, "swap_crit", 30):
            # Prozesse killen
            killed = kill_runaway_processes()
            if killed:
                kill_txt = ", ".join(f"{k}: {v} Prozesse gekillt" for k, v in killed.items())
                msg = (f"🔴 *Swap Kritisch: {swap['pct']:.0f}%* "
                       f"({swap['used_gb']:.1f}/{swap['total_gb']:.1f} GB)\n"
                       f"Auto-Fix:\n{kill_txt}")
                result["actions"].append(f"Prozesse gekillt: {killed}")
            else:
                msg = (f"🔴 *Swap Kritisch: {swap['pct']:.0f}%* "
                       f"({swap['used_gb']:.1f}/{swap['total_gb']:.1f} GB)\n"
                       f"⚠️ Comet / Chrome schließen!")

            _tg(msg)
            _mark_alerted(state, "swap_crit")
            result["alerts"].append(f"swap_crit:{swap['pct']:.0f}%")

    elif swap["pct"] >= SWAP_WARN_PCT:
        if _cooldown_ok(state, "swap_warn", 60):
            killed = kill_runaway_processes()
            if killed:
                kill_txt = ", ".join(f"{k}: {v} gekillt" for k, v in killed.items())
                _tg(f"⚠️ *Swap {swap['pct']:.0f}%* ({swap['used_gb']:.1f} GB) — {kill_txt}")
                result["actions"].append(f"Prozesse gekillt: {killed}")
            else:
                _tg(f"⚠️ *Swap {swap['pct']:.0f}%* — Bitte Comet/Chrome schließen")
            _mark_alerted(state, "swap_warn")
            result["alerts"].append(f"swap_warn:{swap['pct']:.0f}%")

    # ── 2. RAM-Überwachung ───────────────────────────────────────────────────
    if ram["pct"] >= RAM_WARN_PCT and _cooldown_ok(state, "ram_warn", 45):
        killed = kill_runaway_processes()
        msg = (f"⚠️ *RAM {ram['pct']:.0f}%* "
               f"({ram['used_gb']:.1f}/{ram['total_gb']:.1f} GB)")
        if killed:
            kill_txt = ", ".join(f"{k}: {v}" for k, v in killed.items())
            msg += f"\nAuto-Fix: {kill_txt}"
            result["actions"].append(f"RAM-Fix Prozesse gekillt: {killed}")
        _tg(msg)
        _mark_alerted(state, "ram_warn")
        result["alerts"].append(f"ram:{ram['pct']:.0f}%")

    # ── 3. Disk-Überwachung + Auto-Cleanup ──────────────────────────────────
    if disk_gb < DISK_CRIT_GB:
        result["ok"] = False
        if _cooldown_ok(state, "disk_crit", 60):
            _tg(f"🔴 *Disk Kritisch: nur {disk_gb:.1f} GB frei!*\nLösche TM-Snapshots...")
            snaps = delete_tm_snapshots()
            cleanup = trigger_disk_cleanup(force=True)
            evict_icloud_cache()
            freed  = cleanup.get("freed_mb", 0)
            after  = cleanup.get("free_after_gb", disk_gb)
            _tg(f"🧹 Disk-Notfall-Cleanup:\n"
                f"TM-Snapshots gelöscht: {snaps}\n"
                f"Caches befreit: {freed:.0f} MB\n"
                f"Jetzt frei: {after:.1f} GB")
            _mark_alerted(state, "disk_crit")
            result["actions"].append(f"disk_crit_cleanup: {freed:.0f}MB + {snaps} snapshots")

    elif disk_gb < DISK_CLEAN_GB:
        if _cooldown_ok(state, "disk_clean", 90):
            cleanup = trigger_disk_cleanup(force=False)
            if not cleanup.get("skipped"):
                freed = cleanup.get("freed_mb", 0)
                after = cleanup.get("free_after_gb", disk_gb)
                _tg(f"🧹 *Auto Disk Cleanup* ({disk_gb:.1f} GB frei)\n"
                    f"Befreit: {freed:.0f} MB → {after:.1f} GB frei")
                _mark_alerted(state, "disk_clean")
                result["actions"].append(f"disk_cleanup: {freed:.0f}MB")

    # ── 4. Prozess-Watchdog (immer, kein Cooldown für Count-Checks) ─────────
    comet_count = sum(1 for p in psutil.process_iter(["cmdline"])
                      if any("Comet" in (c or "") for c in (p.info.get("cmdline") or [])))
    if comet_count > COMET_MAX_PROCS * 2:
        killed = kill_runaway_processes()
        if killed and _cooldown_ok(state, "proc_kill", 15):
            kill_txt = ", ".join(f"{k}: {v}" for k, v in killed.items())
            _tg(f"🤖 *Runaway-Prozesse gekillt*\n{kill_txt}\n"
                f"(Comet hatte {comet_count} Prozesse)")
            _mark_alerted(state, "proc_kill")
            result["actions"].append(f"proc_kill: {killed}")

    state["last_run"] = now
    state.setdefault("actions", [])
    state["actions"] = (result["actions"] + state["actions"])[:50]
    _save_state(state)

    log.info("Watchdog fertig: %d Alerts, %d Aktionen",
             len(result["alerts"]), len(result["actions"]))
    return result


if __name__ == "__main__":
    # .env laden wenn vorhanden
    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )
    import json as _json
    r = run_ram_watchdog()
    print(_json.dumps(r, indent=2, ensure_ascii=False))
