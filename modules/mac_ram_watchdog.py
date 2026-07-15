"""
Mac RAM + Swap + Prozess Watchdog — Permanent immer aktiv
==========================================================
• Swap-Auslastung überwachen → bei >60% auto-bereinigen
• Runaway-Prozesse killen (Comet, grok, Streamlit, Chrome, Brave)
• Browser NIEMALS killen — nur die echten RAM/CPU-Fresser
• Disk-Cleaner triggern wenn <20 GB frei
• TM-Snapshots auto-löschen wenn Disk <15 GB frei
• Telegram-Alarm bei kritischen Zuständen
• Läuft alle 60 Sekunden via LaunchAgent (KeepAlive)

Läuft als dauerhafter Daemon (KeepAlive=true, throtlle 60s).
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

log = logging.getLogger("RamWatchdog")

HOME = Path.home()
PROJECT_DIR = HOME / "supermegabot"
STATE_FILE  = PROJECT_DIR / "data" / "ram_watchdog_state.json"

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

# Schwellenwerte
SWAP_ACT_PCT       = 60   # % Swap → aktiv killen (war 70%)
SWAP_CRIT_PCT      = 80   # % Swap → kritisch + Telegram-Alarm (war 85%)
RAM_WARN_PCT       = 85   # % RAM belegt → killen
DISK_CLEAN_GB      = 20
DISK_CRIT_GB       = 10
COMET_MAX_PROCS    = 10   # Comet-Renderer max (war 12)
CHROME_MAX_PROCS   = 12   # Chrome Renderer max
BRAVE_MAX_PROCS    = 12   # Brave Renderer max
ALERT_COOLDOWN_MIN = 20

# Prozesse die IMMER gekillt werden wenn Swap > SWAP_ACT_PCT
# (nicht-kritische RAM/CPU-Fresser die sich von selbst neu starten können)
ALWAYS_KILL_WHEN_HIGH = [
    "grok",                           # X.ai Grok App — 101% CPU, 500 MB
    "geldmaschine_skalieren_10k.py",  # Streamlit — 2.6 GB RAM
]

# Streamlit-Prozesse die gekillt werden (hängen oft nach Session)
STREAMLIT_KILL_SCRIPTS = [
    "geldmaschine",
]


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


def get_swap_usage() -> dict:
    try:
        import re
        out = subprocess.check_output(
            ["sysctl", "vm.swapusage"], text=True, timeout=5
        )
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
    try:
        vm = psutil.virtual_memory()
        return {
            "total_gb": vm.total / 1024**3,
            "used_gb":  vm.used  / 1024**3,
            "free_gb":  vm.available / 1024**3,
            "pct":      vm.percent,
        }
    except Exception:
        return {"total_gb": 48, "used_gb": 0, "free_gb": 48, "pct": 0}


def get_disk_free_gb() -> float:
    try:
        return shutil.disk_usage("/").free / 1024**3
    except Exception:
        return 999.0


def kill_always_kill_list() -> dict:
    """Killt Prozesse aus ALWAYS_KILL_WHEN_HIGH (grok, Streamlit etc.)"""
    killed = {}
    for p in psutil.process_iter(["pid", "name", "cmdline", "memory_info", "cpu_percent"]):
        try:
            name = p.info.get("name") or ""
            cmd  = " ".join(p.info.get("cmdline") or [])
            for pattern in ALWAYS_KILL_WHEN_HIGH:
                if pattern.lower() in name.lower() or pattern.lower() in cmd.lower():
                    rss_mb = (p.info.get("memory_info") or type("", (), {"rss": 0})()).rss / 1024**2
                    log.info("Kill always-list: PID %d (%s, %.0f MB)", p.pid, pattern, rss_mb)
                    try:
                        psutil.Process(p.pid).terminate()
                        killed[pattern] = killed.get(pattern, 0) + 1
                    except Exception:
                        pass
                    break
        except Exception:
            pass
    return killed


def _count_and_kill_runaway(name_pattern: str, max_procs: int) -> int:
    """
    Findet alle Prozesse die name_pattern enthalten.
    Wenn mehr als max_procs laufen, werden die RAM-intensivsten Helper gekillt.
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
                    "is_helper": any(x in cmd for x in
                                     ["Helper", "Renderer", "GPU", "Worker", "crashpad"]),
                })
        except Exception:
            pass

    if len(procs) <= max_procs:
        return 0

    helpers = [p for p in procs if p["is_helper"]]
    to_kill = sorted(helpers, key=lambda x: x["rss"], reverse=True)
    to_kill = to_kill[:len(procs) - max_procs]

    killed = 0
    for p in to_kill:
        try:
            psutil.Process(p["pid"]).terminate()
            killed += 1
            log.info("Helper gekillt: PID %d (%.0f MB)", p["pid"], p["rss"]/1024**2)
        except Exception:
            pass
    return killed


def kill_runaway_browser_helpers() -> dict:
    """Killt überzählige Helper-Prozesse — NIEMALS den Browser selbst."""
    killed = {}
    n = _count_and_kill_runaway("Comet", COMET_MAX_PROCS)
    if n > 0:
        killed["Comet"] = n
    n = _count_and_kill_runaway("Google Chrome", CHROME_MAX_PROCS)
    if n > 0:
        killed["Chrome"] = n
    n = _count_and_kill_runaway("Brave Browser", BRAVE_MAX_PROCS)
    if n > 0:
        killed["Brave"] = n
    return killed


def purge_memory() -> None:
    """Versucht Speicher-Purge (braucht ggf. sudo — schlägt still fehl)."""
    try:
        subprocess.run(["purge"], timeout=30, capture_output=True)
        log.info("purge ausgeführt")
    except Exception:
        pass


def delete_tm_snapshots() -> int:
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


def trigger_disk_cleanup(force: bool = False) -> dict:
    try:
        sys.path.insert(0, str(PROJECT_DIR))
        from modules.mac_disk_cleaner import run_full_cleanup
        return run_full_cleanup(force=force)
    except Exception as e:
        log.error("Disk cleanup Fehler: %s", e)
        return {"error": str(e)}


def evict_icloud_cache() -> None:
    icloud = HOME / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    targets = [
        str(icloud / "ARCHIVES" / "MacOffload"),
        str(icloud / "Downloads"),
    ]
    for target in targets:
        if os.path.exists(target):
            subprocess.Popen(
                f'find "{target}" -type f -size +0c | head -2000 '
                f'| xargs -P 4 -n 50 brctl evict 2>/dev/null',
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )


def run_ram_watchdog() -> dict:
    """
    Vollständiger RAM/Swap/Prozess-Check.
    Wird alle 60 Sekunden via LaunchAgent (KeepAlive+ThrottleInterval) aufgerufen.
    """
    import time
    while True:
        state  = _load_state()
        result = {"actions": [], "alerts": [], "ok": True}
        now    = datetime.now(timezone.utc).isoformat()

        swap    = get_swap_usage()
        ram     = get_ram_usage()
        disk_gb = get_disk_free_gb()

        log.info("Swap %.1f%% (%.1f/%.1f GB) | RAM %.1f%% | Disk %.1f GB",
                 swap["pct"], swap["used_gb"], swap["total_gb"], ram["pct"], disk_gb)

        # ── 1. Always-Kill-Liste: grok, Streamlit etc. wenn Swap > Schwelle ──
        if swap["pct"] >= SWAP_ACT_PCT or ram["pct"] >= RAM_WARN_PCT:
            ak = kill_always_kill_list()
            if ak:
                result["actions"].append(f"always_kill: {ak}")
                log.info("Always-Kill: %s", ak)

        # ── 2. Browser-Helper killen wenn zu viele Prozesse ──────────────────
        bh = kill_runaway_browser_helpers()
        if bh:
            result["actions"].append(f"browser_helpers: {bh}")

        # ── 3. purge wenn Swap > 80% ──────────────────────────────────────────
        if swap["pct"] >= SWAP_CRIT_PCT:
            purge_memory()
            result["actions"].append("purge")

        # ── 4. Swap-Alarm ─────────────────────────────────────────────────────
        if swap["pct"] >= SWAP_CRIT_PCT:
            result["ok"] = False
            if _cooldown_ok(state, "swap_crit", 30):
                ak_txt = str(result["actions"]) if result["actions"] else "—"
                _tg(f"🔴 *Swap Kritisch: {swap['pct']:.0f}%* "
                    f"({swap['used_gb']:.1f}/{swap['total_gb']:.1f} GB)\n"
                    f"Aktionen: {ak_txt}")
                _mark_alerted(state, "swap_crit")
                result["alerts"].append(f"swap_crit:{swap['pct']:.0f}%")

        elif swap["pct"] >= SWAP_ACT_PCT:
            if _cooldown_ok(state, "swap_warn", 60):
                _tg(f"⚠️ *Swap {swap['pct']:.0f}%* — Auto-Cleanup aktiv")
                _mark_alerted(state, "swap_warn")
                result["alerts"].append(f"swap_warn:{swap['pct']:.0f}%")

        # ── 5. TM-Snapshots alle 2h löschen ──────────────────────────────────
        if _cooldown_ok(state, "tm_snapshots", 120):
            snaps = delete_tm_snapshots()
            if snaps > 0:
                _mark_alerted(state, "tm_snapshots")
                result["actions"].append(f"tm_snapshots:{snaps}")

        # ── 6. Disk-Überwachung ───────────────────────────────────────────────
        if disk_gb < DISK_CRIT_GB:
            result["ok"] = False
            if _cooldown_ok(state, "disk_crit", 60):
                _tg(f"🔴 *Disk Kritisch: {disk_gb:.1f} GB frei!*")
                delete_tm_snapshots()
                trigger_disk_cleanup(force=True)
                evict_icloud_cache()
                _mark_alerted(state, "disk_crit")
                result["actions"].append("disk_crit_cleanup")

        elif disk_gb < DISK_CLEAN_GB:
            if _cooldown_ok(state, "disk_clean", 90):
                cleanup = trigger_disk_cleanup(force=False)
                if not cleanup.get("skipped"):
                    _mark_alerted(state, "disk_clean")
                    result["actions"].append(f"disk_cleanup:{cleanup.get('freed_mb',0):.0f}MB")

        state["last_run"] = now
        state["actions"] = (result["actions"] + state.get("actions", []))[:50]
        _save_state(state)

        if result["actions"]:
            log.info("Aktionen: %s", result["actions"])

        # 60 Sekunden warten bis zum nächsten Check
        time.sleep(60)


if __name__ == "__main__":
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
    run_ram_watchdog()
