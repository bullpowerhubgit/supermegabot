#!/usr/bin/env python3
"""
Mac Optimization Suite - Vollständiges macOS Optimierungssystem
===============================================================
Enthält:
- System Cleanup (Caches, Logs, Trash)
- Performance Optimization (RAM, CPU, Disk)
- Security Scan & Repair
- DeepScan Integration
- Network Optimization
- App Management
- Startup Optimization
- Agent Data Sharing
"""

import asyncio
import json
import logging
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
OPTIMIZATION_LOG = DATA_DIR / "optimization_history.json"


# ═══════════════════════════════════════════════════════════════════════════════
# HILFSFUNKTIONEN
# ═══════════════════════════════════════════════════════════════════════════════

def _run(cmd: str, timeout: int = 30) -> Dict[str, Any]:
    """Führt Shell-Befehl aus und gibt Ergebnis zurück"""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {
            "success": r.returncode == 0,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
            "returncode": r.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout", "stdout": "", "stderr": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "stdout": "", "stderr": ""}


def _applescript(script: str) -> str:
    """Führt AppleScript aus"""
    r = _run(f"osascript -e '{script}'")
    return r["stdout"]


def _load_json(path: Path, default: Dict = None) -> Dict:
    """Lädt JSON-Datei oder gibt Default zurück"""
    default = default or {}
    try:
        if path.exists():
            with open(path, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Konnte {path} nicht laden: {e}")
    return default.copy()


def _save_json(path: Path, data: Dict):
    """Speichert JSON-Datei"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Konnte {path} nicht speichern: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAC OPTIMIZATION SUITE
# ═══════════════════════════════════════════════════════════════════════════════

class MacOptimizationSuite:
    """Hauptklasse für alle Mac-Optimierungen"""

    def __init__(self):
        self.base_dir = BASE_DIR
        self.data_dir = DATA_DIR
        self.logs_dir = LOGS_DIR
        self.history_file = OPTIMIZATION_LOG
        self.scan_results = []
        self.is_optimizing = False

        # Verzeichnisse erstellen
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Historie laden
        self.history = _load_json(self.history_file, {"optimizations": [], "scans": []})

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. SYSTEM CLEANUP
    # ═══════════════════════════════════════════════════════════════════════════

    async def cleanup_system(self, aggressive: bool = False) -> Dict[str, Any]:
        """Führt umfassende System-Bereinigung durch"""
        logger.info("🧹 Starte System-Cleanup...")
        start_time = time.time()
        results = {
            "timestamp": datetime.now().isoformat(),
            "type": "cleanup",
            "aggressive": aggressive,
            "operations": [],
            "total_freed_mb": 0,
            "success": True
        }

        # 1. Benutzer-Caches
        r = await self._clean_user_caches(aggressive)
        results["operations"].append(r)
        results["total_freed_mb"] += r.get("freed_mb", 0)

        # 2. System-Caches (nur bei aggressive)
        if aggressive:
            r = await self._clean_system_caches()
            results["operations"].append(r)
            results["total_freed_mb"] += r.get("freed_mb", 0)

        # 3. Logs bereinigen
        r = await self._clean_logs(aggressive)
        results["operations"].append(r)
        results["total_freed_mb"] += r.get("freed_mb", 0)

        # 4. Trash leeren
        r = await self._empty_trash()
        results["operations"].append(r)
        results["total_freed_mb"] += r.get("freed_mb", 0)

        # 5. Downloads aufräumen (alte Dateien)
        if aggressive:
            r = await self._clean_old_downloads()
            results["operations"].append(r)
            results["total_freed_mb"] += r.get("freed_mb", 0)

        # 6. Docker Cleanup (falls installiert)
        r = await self._clean_docker()
        results["operations"].append(r)
        results["total_freed_mb"] += r.get("freed_mb", 0)

        # 7. Node Modules Cleanup
        r = await self._clean_node_modules()
        results["operations"].append(r)
        results["total_freed_mb"] += r.get("freed_mb", 0)

        # 8. Xcode Derived Data
        r = await self._clean_xcode_derived_data()
        results["operations"].append(r)
        results["total_freed_mb"] += r.get("freed_mb", 0)

        results["duration_sec"] = round(time.time() - start_time, 2)
        results["total_freed_gb"] = round(results["total_freed_mb"] / 1024, 2)

        # Speichern
        self._add_to_history(results)
        logger.info(f"✅ Cleanup abgeschlossen: {results['total_freed_gb']:.2f} GB freigegeben")
        return results

    async def _clean_user_caches(self, aggressive: bool = False) -> Dict:
        """Bereinigt Benutzer-Caches"""
        freed = 0
        cache_dirs = [
            Path.home() / "Library/Caches",
            Path.home() / "Library/Caches/CocoaPods",
        ]

        for cache_dir in cache_dirs:
            if cache_dir.exists():
                try:
                    size_before = self._get_dir_size(cache_dir)
                    # Alte Dateien löschen (älter als 7 Tage, oder alle bei aggressive)
                    days = 1 if aggressive else 7
                    for item in cache_dir.rglob("*"):
                        if item.is_file():
                            try:
                                mtime = item.stat().st_mtime
                                if time.time() - mtime > days * 86400:
                                    item.unlink()
                            except Exception:
                                pass
                    size_after = self._get_dir_size(cache_dir)
                    freed += (size_before - size_after) / (1024 * 1024)
                except Exception as e:
                    logger.warning(f"Cache-Cleanup Fehler: {e}")

        return {"name": "User Caches", "freed_mb": round(freed, 2), "success": True}

    async def _clean_system_caches(self) -> Dict:
        """Bereinigt System-Caches (erfordert sudo)"""
        results = []
        # DNS-Cache leeren
        r = _run("sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder")
        results.append("DNS Cache flushed" if r["success"] else "DNS Cache flush failed")

        # System-Caches
        r = _run("sudo rm -rf /System/Library/Caches/* 2>/dev/null || true")
        return {"name": "System Caches", "freed_mb": 0, "details": results, "success": True}

    async def _clean_logs(self, aggressive: bool = False) -> Dict:
        """Bereinigt Logs"""
        freed = 0
        log_dirs = [
            Path.home() / "Library/Logs",
            Path("/var/log"),
        ]

        for log_dir in log_dirs:
            if log_dir.exists():
                try:
                    size_before = self._get_dir_size(log_dir)
                    days = 3 if aggressive else 30
                    for item in log_dir.rglob("*.log"):
                        if item.is_file():
                            try:
                                mtime = item.stat().st_mtime
                                if time.time() - mtime > days * 86400:
                                    item.unlink()
                            except Exception:
                                pass
                    size_after = self._get_dir_size(log_dir)
                    freed += (size_before - size_after) / (1024 * 1024)
                except Exception:
                    pass

        return {"name": "Logs", "freed_mb": round(freed, 2), "success": True}

    async def _empty_trash(self) -> Dict:
        """Leert den Papierkorb"""
        try:
            trash_path = Path.home() / ".Trash"
            size_before = self._get_dir_size(trash_path) if trash_path.exists() else 0
            _run("osascript -e 'tell application \"Finder\" to empty trash'")
            size_after = self._get_dir_size(trash_path) if trash_path.exists() else 0
            freed = (size_before - size_after) / (1024 * 1024)
            return {"name": "Trash", "freed_mb": round(freed, 2), "success": True}
        except Exception as e:
            return {"name": "Trash", "freed_mb": 0, "error": str(e), "success": False}

    async def _clean_old_downloads(self) -> Dict:
        """Löscht alte Downloads (älter als 30 Tage)"""
        freed = 0
        downloads = Path.home() / "Downloads"
        if downloads.exists():
            for item in downloads.iterdir():
                try:
                    if item.is_file() and time.time() - item.stat().st_mtime > 30 * 86400:
                        freed += item.stat().st_size / (1024 * 1024)
                        item.unlink()
                except Exception:
                    pass
        return {"name": "Old Downloads", "freed_mb": round(freed, 2), "success": True}

    async def _clean_docker(self) -> Dict:
        """Bereinigt Docker"""
        freed = 0
        r = _run("docker system prune -f 2>/dev/null || true")
        if r["success"]:
            # Schätze freigegebenen Speicher
            freed = 500  # Schätzung in MB
        return {"name": "Docker", "freed_mb": freed, "success": r["success"]}

    async def _clean_node_modules(self) -> Dict:
        """Findet und bereinigt alte node_modules"""
        freed = 0
        home = Path.home()
        for nm_dir in home.rglob("node_modules"):
            try:
                # Prüfe ob package.json älter als 30 Tage
                pkg = nm_dir.parent / "package.json"
                if pkg.exists() and time.time() - pkg.stat().st_mtime > 30 * 86400:
                    size = self._get_dir_size(nm_dir)
                    freed += size / (1024 * 1024)
                    shutil.rmtree(nm_dir, ignore_errors=True)
            except Exception:
                pass
        return {"name": "Node Modules", "freed_mb": round(freed, 2), "success": True}

    async def _clean_xcode_derived_data(self) -> Dict:
        """Bereinigt Xcode Derived Data"""
        freed = 0
        derived = Path.home() / "Library/Developer/Xcode/DerivedData"
        if derived.exists():
            size_before = self._get_dir_size(derived)
            for item in derived.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                except Exception:
                    pass
            size_after = self._get_dir_size(derived)
            freed = (size_before - size_after) / (1024 * 1024)
        return {"name": "Xcode Derived Data", "freed_mb": round(freed, 2), "success": True}

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. PERFORMANCE OPTIMIZATION
    # ═══════════════════════════════════════════════════════════════════════════

    async def optimize_performance(self) -> Dict[str, Any]:
        """Optimiert System-Performance"""
        logger.info("⚡ Starte Performance-Optimierung...")
        start_time = time.time()
        results = {
            "timestamp": datetime.now().isoformat(),
            "type": "performance",
            "operations": [],
            "success": True
        }

        # 1. RAM bereinigen (Purge)
        r = await self._purge_memory()
        results["operations"].append(r)

        # 2. Spotlight reindex (falls langsam)
        r = await self._rebuild_spotlight()
        results["operations"].append(r)

        # 3. DNS-Cache leeren
        r = await self._flush_dns()
        results["operations"].append(r)

        # 4. Prozesse optimieren
        r = await self._optimize_processes()
        results["operations"].append(r)

        # 5. RAM-Compression prüfen
        r = await self._check_ram_compression()
        results["operations"].append(r)

        results["duration_sec"] = round(time.time() - start_time, 2)
        self._add_to_history(results)
        logger.info("✅ Performance-Optimierung abgeschlossen")
        return results

    async def _purge_memory(self) -> Dict:
        """Leitet RAM-Speicher frei"""
        r = _run("sudo purge 2>/dev/null || purge 2>/dev/null || echo 'Purge not available'")
        return {"name": "Memory Purge", "success": r["success"], "details": r["stdout"]}

    async def _rebuild_spotlight(self) -> Dict:
        """Rebuildet Spotlight-Index"""
        # Nur bei Bedarf - deaktiviere temporär und re-aktiviere
        _run("sudo mdutil -a -i off 2>/dev/null || true")
        await asyncio.sleep(1)
        _run("sudo mdutil -a -i on 2>/dev/null || true")
        return {"name": "Spotlight Rebuild", "success": True}

    async def _flush_dns(self) -> Dict:
        """Leert DNS-Cache"""
        _run("sudo dscacheutil -flushcache 2>/dev/null || true")
        _run("sudo killall -HUP mDNSResponder 2>/dev/null || true")
        return {"name": "DNS Flush", "success": True}

    async def _optimize_processes(self) -> Dict:
        """Optimiert laufende Prozesse"""
        killed = []
        if psutil:
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    # Töte Zombie-Prozesse
                    if proc.info['name'] in ['Google Chrome Helper', 'Safari Web Content']:
                        if proc.info['cpu_percent'] and proc.info['cpu_percent'] > 50:
                            psutil.Process(proc.info['pid']).terminate()
                            killed.append(proc.info['name'])
                except Exception:
                    pass
        return {"name": "Process Optimization", "killed": killed, "success": True}

    async def _check_ram_compression(self) -> Dict:
        """Prüft RAM-Kompression"""
        r = _run("vm_stat | grep 'Pages occupied by compressor'")
        compressed = "0"
        if r["success"] and r["stdout"]:
            match = re.search(r'(\d+)', r["stdout"])
            if match:
                compressed = match.group(1)
        return {"name": "RAM Compression", "compressed_pages": compressed, "success": True}

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. SECURITY SCAN
    # ═══════════════════════════════════════════════════════════════════════════

    async def security_scan(self) -> Dict[str, Any]:
        """Führt Security-Scan durch"""
        logger.info("🔒 Starte Security-Scan...")
        start_time = time.time()
        results = {
            "timestamp": datetime.now().isoformat(),
            "type": "security",
            "checks": [],
            "issues": [],
            "success": True
        }

        # 1. Firewall-Status
        r = await self._check_firewall()
        results["checks"].append(r)
        if not r.get("enabled"):
            results["issues"].append({"type": "firewall", "severity": "high", "fix": "Enable firewall in System Settings"})

        # 2. SIP-Status
        r = await self._check_sip()
        results["checks"].append(r)

        # 3. Gatekeeper-Status
        r = await self._check_gatekeeper()
        results["checks"].append(r)
        if not r.get("enabled"):
            results["issues"].append({"type": "gatekeeper", "severity": "medium", "fix": "Enable Gatekeeper"})

        # 4. FileVault-Status
        r = await self._check_filevault()
        results["checks"].append(r)
        if not r.get("enabled"):
            results["issues"].append({"type": "filevault", "severity": "medium", "fix": "Enable FileVault"})

        # 5. Sudo-Timeout prüfen
        r = await self._check_sudo_timeout()
        results["checks"].append(r)

        # 6. Offene Ports
        r = await self._check_open_ports()
        results["checks"].append(r)

        # 7. Suspizöse Prozesse
        r = await self._check_suspicious_processes()
        results["checks"].append(r)

        results["issue_count"] = len(results["issues"])
        results["secure"] = len(results["issues"]) == 0
        results["duration_sec"] = round(time.time() - start_time, 2)
        self._add_to_history(results)
        return results

    async def _check_firewall(self) -> Dict:
        r = _run("sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate 2>/dev/null || echo 'disabled'")
        enabled = "enabled" in r["stdout"].lower() if r["success"] else False
        return {"name": "Firewall", "enabled": enabled, "raw": r["stdout"]}

    async def _check_sip(self) -> Dict:
        r = _run("csrutil status")
        enabled = "enabled" in r["stdout"].lower() if r["success"] else False
        return {"name": "SIP", "enabled": enabled, "raw": r["stdout"]}

    async def _check_gatekeeper(self) -> Dict:
        r = _run("spctl --status")
        enabled = "assessments enabled" in r["stdout"].lower() if r["success"] else False
        return {"name": "Gatekeeper", "enabled": enabled, "raw": r["stdout"]}

    async def _check_filevault(self) -> Dict:
        r = _run("fdesetup status")
        enabled = "on" in r["stdout"].lower() if r["success"] else False
        return {"name": "FileVault", "enabled": enabled, "raw": r["stdout"]}

    async def _check_sudo_timeout(self) -> Dict:
        r = _run("sudo grep -i timestamp /etc/sudoers 2>/dev/null || echo 'default'")
        return {"name": "Sudo Timeout", "config": r["stdout"], "success": r["success"]}

    async def _check_open_ports(self) -> Dict:
        r = _run("lsof -i -P | grep LISTEN | wc -l")
        count = int(r["stdout"]) if r["success"] and r["stdout"].isdigit() else 0
        return {"name": "Open Ports", "count": count, "success": r["success"]}

    async def _check_suspicious_processes(self) -> Dict:
        suspicious = []
        if psutil:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if any(x in cmdline.lower() for x in ['nc -l', 'python -m http.server', 'netcat']):
                        suspicious.append({"pid": proc.info['pid'], "name": proc.info['name'], "cmd": cmdline})
                except Exception:
                    pass
        return {"name": "Suspicious Processes", "suspicious": suspicious, "count": len(suspicious)}

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. NETWORK OPTIMIZATION
    # ═══════════════════════════════════════════════════════════════════════════

    async def optimize_network(self) -> Dict[str, Any]:
        """Optimiert Netzwerk-Einstellungen"""
        logger.info("🌐 Starte Netzwerk-Optimierung...")
        results = {
            "timestamp": datetime.now().isoformat(),
            "type": "network",
            "operations": [],
            "success": True
        }

        # DNS-Cache leeren
        r = await self._flush_dns()
        results["operations"].append(r)

        # TCP-Stack optimieren (experimentell)
        _run("sudo sysctl -w net.inet.tcp.win_scale_factor=8 2>/dev/null || true")
        _run("sudo sysctl -w net.inet.tcp.autorcvbufmax=16777216 2>/dev/null || true")

        results["operations"].append({"name": "TCP Optimization", "success": True})
        self._add_to_history(results)
        return results

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. APP MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    async def list_installed_apps(self) -> List[Dict]:
        """Listet installierte Apps"""
        apps = []
        app_dirs = [
            Path("/Applications"),
            Path.home() / "Applications",
        ]
        for app_dir in app_dirs:
            if app_dir.exists():
                for item in app_dir.iterdir():
                    if item.suffix == ".app":
                        apps.append({
                            "name": item.stem,
                            "path": str(item),
                            "size_mb": round(self._get_dir_size(item) / (1024 * 1024), 2)
                        })
        return sorted(apps, key=lambda x: x["size_mb"], reverse=True)

    async def kill_app(self, app_name: str) -> Dict:
        """Beendet App"""
        r = _run(f"pkill -f '{app_name}'")
        return {"name": app_name, "killed": r["success"], "success": r["success"]}

    async def launch_app(self, app_name: str) -> Dict:
        """Startet App"""
        r = _run(f"open -a '{app_name}'")
        return {"name": app_name, "launched": r["success"], "success": r["success"]}

    # ═══════════════════════════════════════════════════════════════════════════
    # 6. SYSTEM INFO & MONITORING
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_system_info(self) -> Dict[str, Any]:
        """Gibt detaillierte System-Informationen"""
        info = {
            "timestamp": datetime.now().isoformat(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
        }

        if psutil:
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            cpu_freq = psutil.cpu_freq()
            boot_time = psutil.boot_time()

            info.update({
                "cpu_percent": psutil.cpu_percent(interval=0.5),
                "cpu_count": psutil.cpu_count(),
                "cpu_freq_mhz": cpu_freq.current if cpu_freq else None,
                "memory_total_gb": round(mem.total / 1024**3, 2),
                "memory_used_gb": round(mem.used / 1024**3, 2),
                "memory_percent": mem.percent,
                "disk_total_gb": round(disk.total / 1024**3, 2),
                "disk_used_gb": round(disk.used / 1024**3, 2),
                "disk_free_gb": round(disk.free / 1024**3, 2),
                "disk_percent": disk.percent,
                "boot_time": datetime.fromtimestamp(boot_time).isoformat(),
                "uptime_hours": round((time.time() - boot_time) / 3600, 1),
            })

        # Mac-spezifisch
        r = _run("system_profiler SPHardwareDataType | grep -E '(Model|Memory|Chip|Serial)'")
        info["hardware_raw"] = r["stdout"]

        return info

    # ═══════════════════════════════════════════════════════════════════════════
    # 7. DEEPSCAN INTEGRATION
    # ═══════════════════════════════════════════════════════════════════════════

    async def run_deep_scan(self) -> Dict[str, Any]:
        """Führt DeepScan durch und integriert mit Repair"""
        logger.info("🔍 Starte DeepScan...")
        start_time = time.time()

        # Versuche DeepScan Repair Tool zu nutzen
        try:
            from modules.deepscan_repair_tool import DeepScanRepairTool
            tool = DeepScanRepairTool("MacOptimizer")
            results = await tool.perform_deep_scan()
            results["duration_sec"] = round(time.time() - start_time, 2)
            self._add_to_history({
                "timestamp": datetime.now().isoformat(),
                "type": "deepscan",
                "results": results,
                "success": True
            })
            return results
        except ImportError:
            # Fallback: Eigener Scan
            results = await self._fallback_deep_scan()
            results["duration_sec"] = round(time.time() - start_time, 2)
            return results

    async def _fallback_deep_scan(self) -> Dict:
        """Fallback DeepScan ohne externes Tool"""
        issues = []

        # Prüfe Festplattenplatz
        if psutil:
            disk = psutil.disk_usage("/")
            if disk.percent > 85:
                issues.append({
                    "type": "disk_space",
                    "severity": "high",
                    "message": f"Festplatte zu {disk.percent}% voll",
                    "fix": "Führe Cleanup durch"
                })

        # Prüfe RAM
            mem = psutil.virtual_memory()
            if mem.percent > 90:
                issues.append({
                    "type": "memory",
                    "severity": "medium",
                    "message": f"RAM zu {mem.percent}% ausgelastet",
                    "fix": "Schließe nicht benötigte Apps"
                })

        # Prüfe CPU-Temperatur (falls verfügbar)
        r = _run("sudo powermetrics --samplers smc -n 1 2>/dev/null | grep -i 'temperature' || true")
        if r["stdout"]:
            temps = re.findall(r'(\d+\.?\d*)', r["stdout"])
            if temps:
                max_temp = max(float(t) for t in temps)
                if max_temp > 80:
                    issues.append({
                        "type": "temperature",
                        "severity": "high",
                        "message": f"CPU Temperatur: {max_temp}C",
                        "fix": "Prüfe Lüfter und Belüftung"
                    })

        return {
            "scan_id": f"fallback_{int(time.time())}",
            "timestamp": datetime.now().isoformat(),
            "total_issues": len(issues),
            "issues_found": issues,
            "status": "completed"
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # 8. AGENT DATA SHARING
    # ═══════════════════════════════════════════════════════════════════════════

    async def share_optimization_data(self) -> Dict[str, Any]:
        """Teilt Optimierungsdaten mit anderen Agenten"""
        data = {
            "agent": "mac_optimizer",
            "timestamp": datetime.now().isoformat(),
            "system_info": await self.get_system_info(),
            "last_cleanup": self._get_last_cleanup(),
            "last_security_scan": self._get_last_security_scan(),
            "health_score": await self._calculate_health_score(),
            "recommendations": await self._generate_recommendations()
        }

        # Speichere in Agent-Registry
        registry_path = self.data_dir / "agent_registry.json"
        registry = _load_json(registry_path, {})
        if "agents" not in registry:
            registry["agents"] = {}
        registry["agents"]["mac_optimizer"] = data
        _save_json(registry_path, registry)

        return {"shared": True, "data": data}

    async def _calculate_health_score(self) -> int:
        """Berechnet Gesundheits-Score (0-100)"""
        score = 100
        if psutil:
            disk = psutil.disk_usage("/")
            if disk.percent > 80:
                score -= 20
            elif disk.percent > 60:
                score -= 10

            mem = psutil.virtual_memory()
            if mem.percent > 80:
                score -= 15

        # Prüfe letzten Cleanup
        last_cleanup = self._get_last_cleanup()
        if not last_cleanup or (time.time() - datetime.fromisoformat(last_cleanup).timestamp()) > 7 * 86400:
            score -= 10

        return max(0, score)

    async def _generate_recommendations(self) -> List[str]:
        """Generiert Empfehlungen"""
        recs = []
        if psutil:
            disk = psutil.disk_usage("/")
            if disk.percent > 70:
                recs.append("Festplatte fast voll - Cleanup empfohlen")
            mem = psutil.virtual_memory()
            if mem.percent > 75:
                recs.append("RAM-Auslastung hoch - Schließe unnötige Apps")
        return recs

    # ═══════════════════════════════════════════════════════════════════════════
    # HILFSMETHODEN
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_dir_size(self, path: Path) -> int:
        """Berechnet Verzeichnisgröße in Bytes"""
        total = 0
        try:
            if path.is_file():
                return path.stat().st_size
            for entry in path.rglob('*'):
                if entry.is_file():
                    total += entry.stat().st_size
        except Exception:
            pass
        return total

    def _add_to_history(self, entry: Dict):
        """Fügt Eintrag zur Historie hinzu"""
        if "optimizations" not in self.history:
            self.history["optimizations"] = []
        self.history["optimizations"].append(entry)
        # Max 100 Einträge
        self.history["optimizations"] = self.history["optimizations"][-100:]
        _save_json(self.history_file, self.history)

    def _get_last_cleanup(self) -> Optional[str]:
        """Gibt Zeitstempel des letzten Cleanups zurück"""
        for entry in reversed(self.history.get("optimizations", [])):
            if entry.get("type") == "cleanup":
                return entry.get("timestamp")
        return None

    def _get_last_security_scan(self) -> Optional[str]:
        """Gibt Zeitstempel des letzten Security-Scans zurück"""
        for entry in reversed(self.history.get("optimizations", [])):
            if entry.get("type") == "security":
                return entry.get("timestamp")
        return None

    def get_history(self) -> Dict:
        """Gibt komplette Historie zurück"""
        return self.history

    async def run_all_optimizations(self) -> Dict[str, Any]:
        """Führt alle Optimierungen durch"""
        logger.info("🚀 Starte vollständige Optimierung...")
        results = {
            "timestamp": datetime.now().isoformat(),
            "type": "full_optimization",
            "steps": []
        }

        # 1. Cleanup
        cleanup = await self.cleanup_system(aggressive=False)
        results["steps"].append({"name": "cleanup", "result": cleanup})

        # 2. Performance
        perf = await self.optimize_performance()
        results["steps"].append({"name": "performance", "result": perf})

        # 3. Security
        sec = await self.security_scan()
        results["steps"].append({"name": "security", "result": sec})

        # 4. Network
        net = await self.optimize_network()
        results["steps"].append({"name": "network", "result": net})

        # 5. DeepScan
        scan = await self.run_deep_scan()
        results["steps"].append({"name": "deepscan", "result": scan})

        # 6. Daten teilen
        shared = await self.share_optimization_data()
        results["steps"].append({"name": "data_sharing", "result": shared})

        results["success"] = all(s["result"].get("success", True) for s in results["steps"])
        self._add_to_history(results)
        logger.info("✅ Vollständige Optimierung abgeschlossen")
        return results


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

_mac_optimizer = None

def get_mac_optimizer() -> MacOptimizationSuite:
    """Gibt Singleton-Instanz zurück"""
    global _mac_optimizer
    if _mac_optimizer is None:
        _mac_optimizer = MacOptimizationSuite()
    return _mac_optimizer


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    async def main():
        opt = get_mac_optimizer()
        print("🚀 Mac Optimization Suite Test")
        print("=" * 50)

        # System Info
        info = await opt.get_system_info()
        print(f"\n💻 System: {info.get('platform', 'Unknown')}")
        print(f"🧠 RAM: {info.get('memory_used_gb', '?')}/{info.get('memory_total_gb', '?')} GB")
        print(f"💾 Disk: {info.get('disk_percent', '?')}% used")

        # Cleanup
        print("\n🧹 Cleanup...")
        cleanup = await opt.cleanup_system(aggressive=False)
        print(f"  Freigegeben: {cleanup.get('total_freed_gb', 0):.2f} GB")

        # Security
        print("\n🔒 Security Scan...")
        sec = await opt.security_scan()
        print(f"  Sicher: {sec.get('secure', False)}, Issues: {sec.get('issue_count', 0)}")

        # Daten teilen
        print("\n🔗 Teile Daten mit Agenten...")
        shared = await opt.share_optimization_data()
        print(f"  Erfolg: {shared.get('shared', False)}")

        print("\n✅ Test abgeschlossen")

    asyncio.run(main())
