#!/usr/bin/env python3
"""
Speicher-Überwacher — vollständige Kontrolle über RAM, internen und externen Speicher.

Funktionen:
- RAM-Überwachung (gesamt, verwendet, verfügbar, Swap)
- Interner Speicher (alle Partitionen, Dateisystemnutzung)
- Externer Speicher (USB, Netzwerk-Mounts, externe Festplatten)
- Auto-Cleanup: Temp-Dateien, alte Logs, Python-Cache löschen
- Auto-Auslagerung: Dateien auf externen Speicher verschieben wenn intern kritisch
- Telegram-Benachrichtigungen bei kritischen Schwellenwerten
- Hintergrund-Daemon mit konfigurierbaren Intervallen
- SQLite-Protokollierung aller Speicher-Events
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

log = logging.getLogger("StorageMonitor")

# ── Konfiguration ─────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
DB_PATH  = BASE_DIR / "data" / "storage_monitor.db"
LOG_DIR  = BASE_DIR / "logs"

# Schwellenwerte (Prozent)
WARN_THRESHOLD     = float(os.getenv("STORAGE_WARN_PCT",     "80"))
CRITICAL_THRESHOLD = float(os.getenv("STORAGE_CRITICAL_PCT", "90"))
RAM_WARN_THRESHOLD = float(os.getenv("RAM_WARN_PCT",         "85"))

# Check-Intervall in Sekunden
CHECK_INTERVAL = int(os.getenv("STORAGE_CHECK_INTERVAL", "60"))

# Bekannte externe Mount-Präfixe (cross-platform)
EXTERNAL_MOUNT_PREFIXES = [
    "/media/", "/mnt/", "/Volumes/", "/run/media/",
    "/var/media/", "/external/",
]

# Verzeichnisse die sicher geleert werden können
SAFE_CLEANUP_DIRS = [
    Path("/tmp"),
    Path("/var/tmp"),
    Path.home() / ".cache",
    BASE_DIR / "logs",
]

# Dateierweiterungen die als "groß aber verschiebbar" gelten
MOVEABLE_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".mp3", ".wav", ".flac",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".iso", ".img", ".dmg", ".bak", ".backup",
    ".log", ".csv", ".parquet", ".pkl", ".pt", ".ckpt",
}

# Schutzverzeichnisse — niemals anfassen
PROTECTED_DIRS = {
    "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/lib", "/lib64",
    "/boot", "/etc", "/proc", "/sys", "/dev",
}


# ── Datenstrukturen ───────────────────────────────────────────────────────────

@dataclass
class PartitionInfo:
    device:      str
    mountpoint:  str
    fstype:      str
    total_gb:    float
    used_gb:     float
    free_gb:     float
    percent:     float
    is_external: bool
    label:       str = ""

    @property
    def status(self) -> str:
        if self.percent >= CRITICAL_THRESHOLD:
            return "critical"
        if self.percent >= WARN_THRESHOLD:
            return "warning"
        return "ok"


@dataclass
class RamInfo:
    total_gb:     float
    used_gb:      float
    available_gb: float
    percent:      float
    swap_total_gb: float
    swap_used_gb:  float
    swap_percent:  float

    @property
    def status(self) -> str:
        if self.percent >= RAM_WARN_THRESHOLD:
            return "critical"
        if self.percent >= RAM_WARN_THRESHOLD - 10:
            return "warning"
        return "ok"


@dataclass
class StorageStatus:
    timestamp:   str
    ram:         RamInfo
    partitions:  List[PartitionInfo]
    alerts:      List[str] = field(default_factory=list)
    last_cleanup: Optional[str] = None
    last_move:    Optional[str] = None

    @property
    def internal_partitions(self) -> List[PartitionInfo]:
        return [p for p in self.partitions if not p.is_external]

    @property
    def external_partitions(self) -> List[PartitionInfo]:
        return [p for p in self.partitions if p.is_external]

    @property
    def critical_internal(self) -> List[PartitionInfo]:
        return [p for p in self.internal_partitions if p.status == "critical"]


# ── Datenbank ─────────────────────────────────────────────────────────────────

def _init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS storage_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT    NOT NULL,
            event_type  TEXT    NOT NULL,
            mountpoint  TEXT,
            percent     REAL,
            details     TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS storage_snapshots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT NOT NULL,
            data_json TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


_db_lock = threading.Lock()
_db_conn: Optional[sqlite3.Connection] = None


def _db() -> sqlite3.Connection:
    global _db_conn
    if _db_conn is None:
        _db_conn = _init_db()
    return _db_conn


def _log_event(event_type: str, mountpoint: str = "", percent: float = 0.0, details: str = ""):
    try:
        with _db_lock:
            _db().execute(
                "INSERT INTO storage_events (ts, event_type, mountpoint, percent, details) VALUES (?,?,?,?,?)",
                (datetime.now().isoformat(), event_type, mountpoint, percent, details)
            )
            _db().commit()
    except Exception as e:
        log.warning("DB log failed: %s", e)


def _save_snapshot(status: StorageStatus):
    try:
        data = {
            "timestamp": status.timestamp,
            "ram": asdict(status.ram),
            "partitions": [asdict(p) for p in status.partitions],
            "alerts": status.alerts,
        }
        with _db_lock:
            _db().execute(
                "INSERT INTO storage_snapshots (ts, data_json) VALUES (?,?)",
                (status.timestamp, json.dumps(data))
            )
            # Nur letzte 1440 Snapshots behalten (≈ 24h bei 1-Minuten-Intervall)
            _db().execute(
                "DELETE FROM storage_snapshots WHERE id NOT IN (SELECT id FROM storage_snapshots ORDER BY id DESC LIMIT 1440)"
            )
            _db().commit()
    except Exception as e:
        log.warning("Snapshot save failed: %s", e)


def get_event_history(limit: int = 50) -> List[Dict]:
    try:
        with _db_lock:
            rows = _db().execute(
                "SELECT ts, event_type, mountpoint, percent, details FROM storage_events ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"ts": r[0], "type": r[1], "mountpoint": r[2], "percent": r[3], "details": r[4]} for r in rows]
    except Exception:
        return []


# ── Kern: Speicher auslesen ───────────────────────────────────────────────────

def _is_external(mountpoint: str) -> bool:
    for prefix in EXTERNAL_MOUNT_PREFIXES:
        if mountpoint.startswith(prefix):
            return True
    return False


def _get_label(device: str, mountpoint: str) -> str:
    """Versucht einen lesbaren Namen für das Gerät zu ermitteln."""
    name = Path(mountpoint).name or mountpoint
    if mountpoint == "/":
        name = "Intern (Root)"
    elif mountpoint.startswith("/home"):
        name = "Home"
    elif mountpoint.startswith("/boot"):
        name = "Boot"
    elif _is_external(mountpoint):
        name = f"Extern: {Path(mountpoint).name}"
    return name


def get_ram_info() -> RamInfo:
    if not HAS_PSUTIL:
        return RamInfo(0, 0, 0, 0, 0, 0, 0)
    m = psutil.virtual_memory()
    s = psutil.swap_memory()
    return RamInfo(
        total_gb=round(m.total / 1e9, 2),
        used_gb=round(m.used / 1e9, 2),
        available_gb=round(m.available / 1e9, 2),
        percent=m.percent,
        swap_total_gb=round(s.total / 1e9, 2),
        swap_used_gb=round(s.used / 1e9, 2),
        swap_percent=s.percent,
    )


def get_partitions() -> List[PartitionInfo]:
    if not HAS_PSUTIL:
        return []
    partitions = []
    seen_devices: set = set()

    for part in psutil.disk_partitions(all=False):
        # Virtuelle/Pseudo-Dateisysteme überspringen
        if part.fstype in ("tmpfs", "devtmpfs", "devfs", "squashfs",
                           "proc", "sysfs", "cgroup", "cgroup2",
                           "pstore", "securityfs", "debugfs", "tracefs",
                           "hugetlbfs", "mqueue", "fusectl", "overlay"):
            continue
        # Doppelte Geräte überspringen
        if part.device in seen_devices:
            continue
        seen_devices.add(part.device)

        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue

        partitions.append(PartitionInfo(
            device=part.device,
            mountpoint=part.mountpoint,
            fstype=part.fstype,
            total_gb=round(usage.total / 1e9, 2),
            used_gb=round(usage.used / 1e9, 2),
            free_gb=round(usage.free / 1e9, 2),
            percent=usage.percent,
            is_external=_is_external(part.mountpoint),
            label=_get_label(part.device, part.mountpoint),
        ))

    return partitions


def get_full_status() -> StorageStatus:
    ram = get_ram_info()
    partitions = get_partitions()
    alerts: List[str] = []

    if ram.status != "ok":
        alerts.append(f"RAM kritisch: {ram.percent:.1f}% belegt ({ram.used_gb:.1f}/{ram.total_gb:.1f} GB)")

    for p in partitions:
        if p.status == "critical":
            alerts.append(f"KRITISCH: {p.label} ({p.mountpoint}) — {p.percent:.1f}% voll, nur {p.free_gb:.1f} GB frei")
        elif p.status == "warning":
            alerts.append(f"Warnung: {p.label} ({p.mountpoint}) — {p.percent:.1f}% voll")

    status = StorageStatus(
        timestamp=datetime.now().isoformat(),
        ram=ram,
        partitions=partitions,
        alerts=alerts,
    )
    return status


# ── Auto-Cleanup ──────────────────────────────────────────────────────────────

@dataclass
class CleanupResult:
    freed_bytes: int = 0
    deleted_files: int = 0
    errors: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)

    @property
    def freed_mb(self) -> float:
        return round(self.freed_bytes / 1e6, 2)


def cleanup_temp_files(max_age_hours: int = 24) -> CleanupResult:
    """Löscht temporäre Dateien, alte Logs und Python-Cache."""
    result = CleanupResult()
    cutoff = datetime.now() - timedelta(hours=max_age_hours)

    for base_dir in SAFE_CLEANUP_DIRS:
        if not base_dir.exists():
            continue
        try:
            for item in base_dir.rglob("*"):
                if not item.is_file():
                    continue
                # Niemals Konfigurationsdateien löschen
                if item.suffix in (".env", ".key", ".pem", ".cfg", ".conf", ".json", ".py"):
                    continue
                try:
                    mtime = datetime.fromtimestamp(item.stat().st_mtime)
                    if mtime < cutoff:
                        size = item.stat().st_size
                        item.unlink()
                        result.freed_bytes += size
                        result.deleted_files += 1
                except (PermissionError, OSError):
                    continue
        except Exception as e:
            result.errors.append(f"{base_dir}: {e}")

    # Python __pycache__ bereinigen
    for cache_dir in BASE_DIR.rglob("__pycache__"):
        try:
            size = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file())
            shutil.rmtree(cache_dir)
            result.freed_bytes += size
            result.deleted_files += 1
            result.actions.append(f"__pycache__ gelöscht: {cache_dir}")
        except Exception as e:
            result.errors.append(str(e))

    # Alte .pyc Dateien
    for pyc in BASE_DIR.rglob("*.pyc"):
        try:
            size = pyc.stat().st_size
            pyc.unlink()
            result.freed_bytes += size
            result.deleted_files += 1
        except Exception:
            pass

    result.actions.append(f"{result.deleted_files} Dateien gelöscht, {result.freed_mb} MB freigegeben")
    _log_event("cleanup", details=f"Freed {result.freed_mb} MB, {result.deleted_files} files")
    log.info("Cleanup: %d Dateien, %.2f MB freigegeben", result.deleted_files, result.freed_mb)
    return result


def cleanup_old_logs(max_age_days: int = 7) -> CleanupResult:
    """Komprimiert/löscht alte Log-Dateien."""
    result = CleanupResult()
    cutoff = datetime.now() - timedelta(days=max_age_days)
    log_dirs = [LOG_DIR, Path("/tmp")]

    for log_dir in log_dirs:
        if not log_dir.exists():
            continue
        for f in log_dir.glob("*.log"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    size = f.stat().st_size
                    f.unlink()
                    result.freed_bytes += size
                    result.deleted_files += 1
                    result.actions.append(f"Log gelöscht: {f.name}")
            except Exception as e:
                result.errors.append(str(e))

    _log_event("log_cleanup", details=f"Freed {result.freed_mb} MB")
    return result


def find_large_files(directory: Path, min_size_mb: float = 100.0, limit: int = 20) -> List[Dict]:
    """Findet große Dateien die ausgelagert werden könnten."""
    min_bytes = int(min_size_mb * 1e6)
    candidates = []

    protected = any(str(directory).startswith(p) for p in PROTECTED_DIRS)
    if protected:
        return []

    try:
        for f in directory.rglob("*"):
            if not f.is_file():
                continue
            try:
                size = f.stat().st_size
                if size >= min_bytes:
                    candidates.append({
                        "path": str(f),
                        "size_mb": round(size / 1e6, 2),
                        "ext": f.suffix.lower(),
                        "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                        "moveable": f.suffix.lower() in MOVEABLE_EXTENSIONS,
                    })
            except (PermissionError, OSError):
                continue
    except Exception as e:
        log.warning("find_large_files error: %s", e)

    candidates.sort(key=lambda x: x["size_mb"], reverse=True)
    return candidates[:limit]


# ── Auto-Auslagerung ──────────────────────────────────────────────────────────

@dataclass
class MoveResult:
    moved_files: int = 0
    moved_bytes: int = 0
    errors: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)

    @property
    def moved_gb(self) -> float:
        return round(self.moved_bytes / 1e9, 3)


def auto_offload_to_external(
    source_partition: PartitionInfo,
    target_partition: PartitionInfo,
    target_free_pct: float = 75.0,
    min_file_mb: float = 50.0,
) -> MoveResult:
    """
    Verschiebt große Dateien vom internen auf den externen Speicher,
    bis der interne Speicher wieder unter target_free_pct fällt.
    """
    result = MoveResult()

    if not target_partition.is_external:
        result.errors.append("Ziel ist kein externer Speicher — abgebrochen")
        return result

    target_dir = Path(target_partition.mountpoint) / "supermegabot_offload"
    target_dir.mkdir(parents=True, exist_ok=True)

    # Große verschiebbare Dateien finden
    search_root = Path(source_partition.mountpoint)
    candidates = find_large_files(search_root, min_size_mb=min_file_mb, limit=50)
    moveable = [c for c in candidates if c["moveable"]]

    for candidate in moveable:
        # Prüfen ob wir schon genug freigegeben haben
        try:
            current = psutil.disk_usage(source_partition.mountpoint)
            current_pct = current.percent
        except Exception:
            break

        if current_pct < target_free_pct:
            break

        # Prüfen ob genug Platz auf Ziel
        try:
            target_usage = psutil.disk_usage(target_partition.mountpoint)
            file_size = int(candidate["size_mb"] * 1e6)
            if target_usage.free < file_size * 1.1:
                result.errors.append(f"Kein Platz auf {target_partition.label} für {candidate['path']}")
                continue
        except Exception:
            continue

        src = Path(candidate["path"])
        dst = target_dir / src.name

        # Namenskonflikt lösen
        if dst.exists():
            dst = target_dir / f"{src.stem}_{int(time.time())}{src.suffix}"

        try:
            shutil.move(str(src), str(dst))
            result.moved_files += 1
            result.moved_bytes += int(candidate["size_mb"] * 1e6)
            action = f"Verschoben: {src.name} ({candidate['size_mb']} MB) -> {target_partition.label}"
            result.actions.append(action)
            log.info(action)
        except Exception as e:
            result.errors.append(f"{src.name}: {e}")

    _log_event(
        "offload",
        mountpoint=source_partition.mountpoint,
        percent=source_partition.percent,
        details=f"Moved {result.moved_files} files, {result.moved_gb} GB to {target_partition.label}"
    )
    return result


# ── Telegram-Benachrichtigungen ───────────────────────────────────────────────

_last_alert_times: Dict[str, float] = {}
_ALERT_COOLDOWN = 1800  # 30 Minuten zwischen gleichen Alerts


def _send_telegram(message: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        import urllib.request
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log.warning("Telegram send failed: %s", e)


def _maybe_alert(key: str, message: str):
    """Sendet Telegram-Alert maximal einmal pro Cooldown-Periode."""
    now = time.time()
    if now - _last_alert_times.get(key, 0) > _ALERT_COOLDOWN:
        _last_alert_times[key] = now
        _send_telegram(f"🔴 <b>Speicher-Alarm</b>\n{message}")


# ── Hintergrund-Daemon ────────────────────────────────────────────────────────

_daemon_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_last_status: Optional[StorageStatus] = None
_last_cleanup_ts: Optional[str] = None
_last_move_ts: Optional[str] = None


def _daemon_loop():
    global _last_status, _last_cleanup_ts, _last_move_ts
    log.info("StorageMonitor Daemon gestartet (Intervall: %ds)", CHECK_INTERVAL)

    while not _stop_event.wait(timeout=CHECK_INTERVAL):
        try:
            status = get_full_status()
            status.last_cleanup = _last_cleanup_ts
            status.last_move = _last_move_ts
            _last_status = status
            _save_snapshot(status)

            # Alerts senden
            for alert in status.alerts:
                _maybe_alert(alert[:50], alert)

            # Auto-Cleanup wenn interne Partition kritisch ist
            if status.critical_internal:
                for part in status.critical_internal:
                    log.warning("Auto-Cleanup ausgelöst für %s (%.1f%%)", part.mountpoint, part.percent)
                    cleanup_result = cleanup_temp_files(max_age_hours=12)
                    cleanup_result2 = cleanup_old_logs(max_age_days=3)
                    freed = cleanup_result.freed_mb + cleanup_result2.freed_mb
                    _last_cleanup_ts = datetime.now().isoformat()
                    _log_event("auto_cleanup", mountpoint=part.mountpoint, percent=part.percent,
                               details=f"Auto-triggered, freed {freed:.1f} MB")

                    # Auto-Auslagerung wenn externer Speicher verfügbar
                    if status.external_partitions:
                        target = max(status.external_partitions, key=lambda p: p.free_gb)
                        if target.free_gb > 1.0:
                            move_result = auto_offload_to_external(part, target)
                            if move_result.moved_files > 0:
                                _last_move_ts = datetime.now().isoformat()
                                _send_telegram(
                                    f"📦 <b>Auto-Auslagerung</b>\n"
                                    f"{move_result.moved_files} Dateien ({move_result.moved_gb} GB) "
                                    f"von {part.label} nach {target.label} verschoben"
                                )

        except Exception as e:
            log.error("Daemon-Fehler: %s", e)

    log.info("StorageMonitor Daemon beendet")


def start_daemon():
    """Startet den Hintergrund-Überwachungs-Thread."""
    global _daemon_thread
    if _daemon_thread and _daemon_thread.is_alive():
        return
    _stop_event.clear()
    _daemon_thread = threading.Thread(target=_daemon_loop, name="StorageMonitorDaemon", daemon=True)
    _daemon_thread.start()


def stop_daemon():
    _stop_event.set()
    if _daemon_thread:
        _daemon_thread.join(timeout=5)


def get_cached_status() -> Optional[StorageStatus]:
    return _last_status


# ── Public API ────────────────────────────────────────────────────────────────

def get_status_dict() -> Dict[str, Any]:
    """Gibt vollständigen Speicher-Status als Dictionary zurück (für API)."""
    status = get_full_status()
    return {
        "timestamp": status.timestamp,
        "alerts": status.alerts,
        "ram": asdict(status.ram) | {"status": status.ram.status},
        "internal": [asdict(p) | {"status": p.status} for p in status.internal_partitions],
        "external": [asdict(p) | {"status": p.status} for p in status.external_partitions],
        "summary": {
            "total_internal_gb": round(sum(p.total_gb for p in status.internal_partitions), 2),
            "used_internal_gb": round(sum(p.used_gb for p in status.internal_partitions), 2),
            "free_internal_gb": round(sum(p.free_gb for p in status.internal_partitions), 2),
            "total_external_gb": round(sum(p.total_gb for p in status.external_partitions), 2),
            "free_external_gb": round(sum(p.free_gb for p in status.external_partitions), 2),
            "has_external": bool(status.external_partitions),
            "critical_count": len(status.critical_internal),
        },
        "history": get_event_history(20),
        "last_cleanup": _last_cleanup_ts,
        "last_move": _last_move_ts,
        "daemon_running": _daemon_thread is not None and _daemon_thread.is_alive(),
    }


def run_cleanup(max_age_hours: int = 24) -> Dict[str, Any]:
    global _last_cleanup_ts
    r1 = cleanup_temp_files(max_age_hours=max_age_hours)
    r2 = cleanup_old_logs(max_age_days=max_age_hours // 24 + 1)
    _last_cleanup_ts = datetime.now().isoformat()
    return {
        "ok": True,
        "freed_mb": round(r1.freed_mb + r2.freed_mb, 2),
        "deleted_files": r1.deleted_files + r2.deleted_files,
        "actions": r1.actions + r2.actions,
        "errors": r1.errors + r2.errors,
        "timestamp": _last_cleanup_ts,
    }


def run_offload(source_mountpoint: str = "/", min_file_mb: float = 50.0) -> Dict[str, Any]:
    global _last_move_ts
    partitions = get_partitions()
    source = next((p for p in partitions if p.mountpoint == source_mountpoint), None)
    externals = [p for p in partitions if p.is_external]

    if not source:
        return {"ok": False, "error": f"Partition {source_mountpoint} nicht gefunden"}
    if not externals:
        return {"ok": False, "error": "Kein externer Speicher verbunden"}

    target = max(externals, key=lambda p: p.free_gb)
    result = auto_offload_to_external(source, target, min_file_mb=min_file_mb)
    _last_move_ts = datetime.now().isoformat()
    return {
        "ok": True,
        "moved_files": result.moved_files,
        "moved_gb": result.moved_gb,
        "target": target.label,
        "actions": result.actions,
        "errors": result.errors,
        "timestamp": _last_move_ts,
    }


# Daemon beim Import starten
start_daemon()
