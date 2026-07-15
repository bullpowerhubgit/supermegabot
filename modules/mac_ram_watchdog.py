"""
Mac RAM + Swap Watchdog — Browser-SAFE Version
===============================================
WICHTIG: Browser (Comet, Chrome, Brave, Safari) werden NIEMALS gekillt.
Nur echte RAM/CPU-Fresser: grok, Streamlit-Dashboards, orphane Python-Prozesse.

Läuft als Endlos-Loop alle 60 Sekunden.
"""

import os
import re
import subprocess
import logging
import json
import psutil
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("RamWatchdog")

HOME = Path.home()
PROJECT_DIR = HOME / "supermegabot"
STATE_FILE  = PROJECT_DIR / "data" / "ram_watchdog_state.json"

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

# Schwellenwerte
SWAP_ACT_PCT       = 65   # % Swap → RAM-Fresser killen
SWAP_CRIT_PCT      = 82   # % Swap → Telegram-Alarm + purge
ALERT_COOLDOWN_MIN = 20

# Diese Prozesse werden gekillt wenn Swap > SWAP_ACT_PCT
# NIEMALS Browser hier eintragen!
KILL_PATTERNS = [
    "grok",                            # X.ai App — frisst 100%+ CPU
    "geldmaschine_skalieren_10k",      # Streamlit — 2.6 GB RAM
    "geldmaschine_autonom_final",      # Streamlit
    "geldmaschine_vollautonom",        # Streamlit
    "geldmaschine_klaviyo",            # Streamlit-Varianten
    "geldmaschine_marketing",          # Streamlit
    "geldmaschine_flow",               # Streamlit
    "geldmaschine_storefront",         # Streamlit
    "geldmaschine_live",               # Streamlit
    "geldmaschine_einnahmen",          # Streamlit
    "geldmaschine_roas",               # Streamlit
    "geldmaschine_creative",           # Streamlit
    "geldmaschine_ugc",                # Streamlit
    "geldmaschine_hook",               # Streamlit
    "geldmaschine_ab_test",            # Streamlit
    "geldmaschine_ab_planer",          # Streamlit
    "geldmaschine_produktforschung",   # Streamlit
    "geldmaschine_komplett",           # Streamlit
    "geldmaschine_einnahmen_skalieren",# Streamlit
    "geldmaschine_digistore",          # Streamlit
    "geldmaschine_shopify",            # Streamlit
    "subsaver_app",                    # Streamlit
]

# Diese Prozesse werden NIEMALS angefasst — auch nicht wenn RAM voll
NEVER_KILL_PATTERNS = [
    "Comet", "Google Chrome", "Brave Browser", "Safari", "Firefox",
    "Claude", "claude", "Terminal", "iTerm",
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
        return
    try:
        subprocess.run([
            "curl", "-s", "-X", "POST",
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            "-d", f"chat_id={TG_CHAT}&parse_mode=Markdown&text={text}"
        ], timeout=10, capture_output=True)
    except Exception:
        pass


def get_swap_pct() -> float:
    try:
        out = subprocess.check_output(["sysctl", "vm.swapusage"], text=True, timeout=5)
        nums = re.findall(r"[\d,\.]+M", out)
        def to_mb(s): return float(s.replace("M", "").replace(",", "."))
        total = to_mb(nums[0]) if len(nums) > 0 else 1
        used  = to_mb(nums[1]) if len(nums) > 1 else 0
        return round((used / total * 100) if total > 0 else 0, 1)
    except Exception:
        return 0.0


def kill_memory_hogs() -> dict:
    """
    Killt nur bekannte RAM/CPU-Fresser aus KILL_PATTERNS.
    Browser und kritische Apps werden NIEMALS angefasst.
    """
    killed = {}
    for p in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
        try:
            name = p.info.get("name") or ""
            cmd  = " ".join(p.info.get("cmdline") or [])
            full = f"{name} {cmd}"

            # Schutzliste zuerst prüfen
            if any(prot.lower() in full.lower() for prot in NEVER_KILL_PATTERNS):
                continue

            for pattern in KILL_PATTERNS:
                if pattern.lower() in cmd.lower() or pattern.lower() in name.lower():
                    rss_mb = (p.info.get("memory_info") or type("", (), {"rss": 0})()).rss / 1024**2
                    try:
                        psutil.Process(p.pid).terminate()
                        killed[pattern] = killed.get(pattern, 0) + 1
                        log.info("Gekillt: %s PID %d (%.0f MB)", pattern, p.pid, rss_mb)
                    except Exception:
                        pass
                    break
        except Exception:
            pass
    return killed


def delete_tm_snapshots() -> int:
    try:
        result = subprocess.run(
            ["tmutil", "deletelocalsnapshots", "/"],
            capture_output=True, text=True, timeout=60
        )
        lines = result.stdout.strip().split("\n")
        count = len([l for l in lines if "Deleted" in l or ".local" in l])
        if count > 0:
            log.info("TM-Snapshots gelöscht: %d", count)
        return count
    except Exception:
        return 0


def get_disk_free_gb() -> float:
    try:
        return shutil.disk_usage("/").free / 1024**3
    except Exception:
        return 999.0


def run_once() -> dict:
    state  = _load_state()
    result = {"actions": [], "ok": True}
    now    = datetime.now(timezone.utc).isoformat()

    swap_pct = get_swap_pct()
    disk_gb  = get_disk_free_gb()

    log.info("Swap %.1f%% | Disk %.1f GB frei", swap_pct, disk_gb)

    # ── RAM-Fresser killen wenn Swap zu hoch ──────────────────────────────
    if swap_pct >= SWAP_ACT_PCT:
        killed = kill_memory_hogs()
        if killed:
            result["actions"].append(f"killed: {killed}")
            log.info("RAM-Fresser gekillt: %s", killed)

        # purge wenn sehr kritisch
        if swap_pct >= SWAP_CRIT_PCT:
            try:
                subprocess.run(["purge"], timeout=30, capture_output=True)
                result["actions"].append("purge")
            except Exception:
                pass

        # Telegram-Alarm
        if swap_pct >= SWAP_CRIT_PCT and _cooldown_ok(state, "swap_crit", 30):
            killed_str = str(result["actions"]) or "—"
            _tg(f"🔴 *Swap Kritisch: {swap_pct:.0f}%*\nAktionen: {killed_str}")
            _mark_alerted(state, "swap_crit")
            result["ok"] = False

    # ── TM-Snapshots alle 2h löschen ─────────────────────────────────────
    if _cooldown_ok(state, "tm_snapshots", 120):
        snaps = delete_tm_snapshots()
        if snaps > 0:
            _mark_alerted(state, "tm_snapshots")
            result["actions"].append(f"tm_snapshots:{snaps}")

    state["last_run"] = now
    state["actions"] = (result["actions"] + state.get("actions", []))[:50]
    _save_state(state)

    return result


if __name__ == "__main__":
    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [RamWatchdog] %(levelname)s: %(message)s"
    )

    log.info("=== RAM Watchdog gestartet (Browser-safe) ===")
    while True:
        try:
            run_once()
        except Exception as e:
            log.exception("Loop-Fehler: %s", e)
        time.sleep(60)
