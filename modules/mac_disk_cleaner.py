"""
Mac Disk Cleaner — Automatische Speicherbereinigung
====================================================
• Library/Caches, Browser-Caches, App-Caches leeren
• Claude Code Sessions + VM-Cache bereinigen
• Alte Log-Dateien löschen
• iCloud-Dateien lokal evicten (bleiben in iCloud)
• Temp-Dateien aufräumen
• npm / pip / go Cache leeren
• Gerettete GB per Telegram melden

Wird vom Watchdog aufgerufen wenn Disk < 20 GB frei.
Auch täglich um 3:00 Uhr über separaten LaunchAgent.
"""

import os
import shutil
import subprocess
import logging
import glob
from pathlib import Path
from datetime import datetime, timedelta

log = logging.getLogger("DiskCleaner")

HOME = Path.home()
LIBRARY = HOME / "Library"

# Mindest-Alter in Tagen für Log-Datei-Bereinigung
LOG_MAX_DAYS = 14


def _rmtree_safe(p: Path) -> int:
    """Löscht Verzeichnis, gibt freie Bytes zurück. Ignoriert Fehler."""
    try:
        if not p.exists():
            return 0
        size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        shutil.rmtree(str(p), ignore_errors=True)
        return size
    except Exception as e:
        log.debug("rmtree %s: %s", p, e)
        return 0


def _rm_files_in(p: Path, pattern: str = "*", recursive: bool = False) -> int:
    """Löscht Dateien in einem Ordner, gibt freie Bytes zurück."""
    freed = 0
    try:
        if not p.exists():
            return 0
        if recursive:
            files = list(p.rglob(pattern))
        else:
            files = list(p.glob(pattern))
        for f in files:
            if f.is_file():
                try:
                    freed += f.stat().st_size
                    f.unlink()
                except Exception:
                    pass
    except Exception as e:
        log.debug("rm_files_in %s: %s", p, e)
    return freed


def _evict_icloud_dir(path: Path, max_files: int = 5000) -> int:
    """
    Evictet Dateien aus iCloud Drive local Cache via brctl.
    Dateien bleiben in iCloud — nur lokale Kopie wird entfernt.
    """
    freed = 0
    if not path.exists():
        return 0
    try:
        files = [f for f in path.rglob("*") if f.is_file() and not f.name.startswith(".")]
        files = files[:max_files]
        if not files:
            return 0
        # Batch-Eviction: 200 Dateien auf einmal
        batch_size = 200
        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            sizes = sum(f.stat().st_size for f in batch if f.exists())
            str_batch = [str(f) for f in batch]
            result = subprocess.run(
                ["brctl", "evict"] + str_batch,
                capture_output=True, timeout=30
            )
            if result.returncode == 0:
                freed += sizes
    except Exception as e:
        log.debug("evict_icloud %s: %s", path, e)
    return freed


def _clean_old_logs(base: Path, max_days: int = LOG_MAX_DAYS) -> int:
    """Löscht Logdateien älter als max_days Tage."""
    freed = 0
    cutoff = datetime.now().timestamp() - (max_days * 86400)
    try:
        for pattern in ["*.log", "*.log.*", "*.out", "*.err"]:
            for f in base.rglob(pattern):
                if f.is_file():
                    try:
                        if f.stat().st_mtime < cutoff:
                            freed += f.stat().st_size
                            f.unlink()
                    except Exception:
                        pass
    except Exception as e:
        log.debug("clean_logs %s: %s", base, e)
    return freed


def clean_system_caches() -> int:
    """Library/Caches komplett leeren."""
    freed = 0
    cache_dir = LIBRARY / "Caches"
    if cache_dir.exists():
        for item in cache_dir.iterdir():
            try:
                size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file()) if item.is_dir() else item.stat().st_size
                if item.is_dir():
                    shutil.rmtree(str(item), ignore_errors=True)
                else:
                    item.unlink()
                freed += size
            except Exception:
                pass
    log.info("System Caches: +%.1f MB", freed / 1024**2)
    return freed


def clean_claude_caches() -> int:
    """Claude App Caches + Session-Daten bereinigen."""
    freed = 0
    claude_base = LIBRARY / "Application Support" / "Claude"
    targets = [
        claude_base / "Cache",
        claude_base / "Code Cache",
        claude_base / "GPUCache",
        claude_base / "local-agent-mode-sessions",
        claude_base / "Partitions",
        claude_base / "claude-code-sessions",
    ]
    for t in targets:
        freed += _rmtree_safe(t)
        t.mkdir(parents=True, exist_ok=True)

    # Alte claude-code Logdateien
    freed += _clean_old_logs(claude_base / "claude-code", max_days=7)
    freed += _clean_old_logs(claude_base / "claude-code-vm", max_days=7)

    log.info("Claude Caches: +%.1f MB", freed / 1024**2)
    return freed


def clean_browser_caches() -> int:
    """Chrome, Brave, Safari Caches leeren."""
    freed = 0
    app_support = LIBRARY / "Application Support"

    browser_caches = [
        app_support / "Google" / "Chrome" / "Default" / "Cache",
        app_support / "Google" / "Chrome" / "Default" / "Code Cache",
        app_support / "Google" / "Chrome" / "Default" / "GPUCache",
        app_support / "Google" / "Chrome" / "Default" / "Service Worker" / "CacheStorage",
        app_support / "BraveSoftware" / "Brave-Browser" / "Default" / "Cache",
        app_support / "BraveSoftware" / "Brave-Browser" / "Default" / "Code Cache",
        app_support / "BraveSoftware" / "Brave-Browser" / "Default" / "GPUCache",
        LIBRARY / "Caches" / "com.apple.Safari",
        LIBRARY / "Safari" / "LocalStorage",
    ]
    for bc in browser_caches:
        freed += _rmtree_safe(bc)

    log.info("Browser Caches: +%.1f MB", freed / 1024**2)
    return freed


def clean_npm_cache() -> int:
    """npm Cache leeren."""
    try:
        result = subprocess.run(
            ["npm", "cache", "clean", "--force"],
            capture_output=True, timeout=60
        )
        if result.returncode == 0:
            log.info("npm cache geleert")
            return 200 * 1024 * 1024  # Schätzwert
    except Exception as e:
        log.debug("npm cache: %s", e)
    return 0


def clean_pip_cache() -> int:
    """pip Cache leeren."""
    freed = 0
    pip_cache = HOME / "Library" / "Caches" / "pip"
    freed += _rmtree_safe(pip_cache)

    # Homebrew Cache
    try:
        result = subprocess.run(
            ["/opt/homebrew/bin/brew", "cleanup", "--prune=7"],
            capture_output=True, timeout=120
        )
        if result.returncode == 0:
            freed += 100 * 1024 * 1024  # Schätzwert
    except Exception:
        pass

    log.info("pip/brew Caches: +%.1f MB", freed / 1024**2)
    return freed


def clean_app_logs() -> int:
    """Alte Logdateien bereinigen."""
    freed = 0
    log_dirs = [
        LIBRARY / "Logs",
        HOME / "supermegabot" / "data",
    ]
    for ld in log_dirs:
        freed += _clean_old_logs(ld, max_days=LOG_MAX_DAYS)

    log.info("Alte Logs: +%.1f MB", freed / 1024**2)
    return freed


def clean_downloads_folder() -> int:
    """Alte Downloads-Dateien (>30 Tage) auf externe Drive verschieben."""
    freed = 0
    downloads = HOME / "Downloads"
    cutoff = datetime.now().timestamp() - (30 * 86400)

    # Externe Drive für alte Downloads
    external_targets = [
        Path("/Volumes/Untitled"),
        Path("/Volumes/Maxtor 1. "),
        Path("/Volumes/Maxtor .2"),
    ]
    target_drive = None
    for d in external_targets:
        if d.exists() and shutil.disk_usage(str(d)).free > 5 * 1024**3:
            target_drive = d / "MacOffload_Downloads"
            target_drive.mkdir(exist_ok=True)
            break

    if not downloads.exists():
        return 0

    for f in downloads.iterdir():
        try:
            if f.stat().st_mtime < cutoff and f.is_file():
                size = f.stat().st_size
                if target_drive:
                    shutil.move(str(f), str(target_drive / f.name))
                    freed += size
        except Exception:
            pass

    log.info("Alte Downloads verschoben: +%.1f MB", freed / 1024**2)
    return freed


def evict_icloud_archives() -> int:
    """iCloud ARCHIVES lokal evicten — bleiben in iCloud erhalten."""
    freed = 0
    icloud_base = LIBRARY / "Mobile Documents" / "com~apple~CloudDocs"

    evict_targets = [
        icloud_base / "ARCHIVES" / "MacOffload",
        icloud_base / "ARCHIVES" / ".git-home-backup-2026-07-12",
        icloud_base / "Downloads",
    ]

    for target in evict_targets:
        if target.exists():
            log.info("Evicting iCloud: %s", target.name)
            freed += _evict_icloud_dir(target, max_files=3000)

    log.info("iCloud Eviction: +%.1f MB", freed / 1024**2)
    return freed


def move_large_projects_to_external() -> int:
    """Veraltete/inaktive Projekte auf externe Drive verschieben."""
    freed = 0
    external_targets = [
        Path("/Volumes/Untitled"),
        Path("/Volumes/Maxtor 1. "),
    ]
    target_drive = None
    for d in external_targets:
        if d.exists() and shutil.disk_usage(str(d)).free > 10 * 1024**3:
            target_drive = d / "MacProjects_Archive"
            target_drive.mkdir(exist_ok=True)
            break

    if not target_drive:
        log.info("Kein externer Drive verfügbar für Projekt-Archivierung")
        return 0

    # Große inaktive Projekte (>500MB, >60 Tage nicht benutzt)
    cutoff = datetime.now().timestamp() - (60 * 86400)
    min_size_bytes = 500 * 1024 * 1024

    candidates = [
        HOME / "sync-engine-fork",
        HOME / "hydrogen-storefront",
        HOME / "netlify-deploy",
    ]

    for proj in candidates:
        if not proj.exists():
            continue
        try:
            mtime = max(
                (f.stat().st_mtime for f in proj.rglob("*") if f.is_file()),
                default=0
            )
            size = sum(f.stat().st_size for f in proj.rglob("*") if f.is_file())
            if mtime < cutoff and size > min_size_bytes:
                dest = target_drive / proj.name
                if not dest.exists():
                    shutil.move(str(proj), str(dest))
                    freed += size
                    log.info("Projekt %s auf externe Drive verschoben (%.1f GB)", proj.name, size / 1024**3)
        except Exception as e:
            log.debug("move_project %s: %s", proj, e)

    return freed


def get_disk_free_gb() -> float:
    """Gibt freien Speicher in GB zurück."""
    try:
        usage = shutil.disk_usage("/")
        return usage.free / 1024**3
    except Exception:
        return 999.0


def run_full_cleanup(force: bool = False) -> dict:
    """
    Vollständige Bereinigung. Gibt Ergebnis-Dict zurück.
    force=True: immer ausführen; False: nur wenn <20GB frei
    """
    free_before = get_disk_free_gb()

    if not force and free_before > 20:
        return {"skipped": True, "free_gb": free_before, "reason": "Genug Speicher"}

    log.info("Disk Cleanup startet (%.1f GB frei)", free_before)
    total_freed = 0

    steps = [
        ("System Caches",      clean_system_caches),
        ("Claude Caches",      clean_claude_caches),
        ("Browser Caches",     clean_browser_caches),
        ("App Logs",           clean_app_logs),
        ("iCloud Eviction",    evict_icloud_archives),
        ("pip/brew Caches",    clean_pip_cache),
        ("Alte Downloads",     clean_downloads_folder),
        ("Projekt-Archivierung", move_large_projects_to_external),
    ]

    results = {}
    for name, fn in steps:
        try:
            freed = fn()
            total_freed += freed
            results[name] = freed
        except Exception as e:
            log.error("Fehler bei %s: %s", name, e)
            results[name] = 0

    free_after = get_disk_free_gb()

    return {
        "skipped": False,
        "free_before_gb": round(free_before, 1),
        "free_after_gb": round(free_after, 1),
        "freed_mb": round(total_freed / 1024**2, 1),
        "steps": {k: round(v / 1024**2, 1) for k, v in results.items()},
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import json
    result = run_full_cleanup(force=True)
    print(json.dumps(result, indent=2, ensure_ascii=False))
