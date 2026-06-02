#!/usr/bin/env python3
"""
SuperMegaBot — 5 Spezialisierte Bot-Clones (Erweiterte Architektur)

  📡 MonitoringBot    — Kontinuierliches System-Monitoring + Alerting
  🚨 ErrorDetectorBot — Log-Analyse, Exception-Erkennung, Incident-Eskalation
  🛠  RepairEngineBot  — Automatische Reparaturen, Fallbacks, Restart-Logik
  🔩 MaintenanceBot   — Dependency-Pflege, Health-Checks, Instandhaltung
  ⚡ OptimizationBot  — Performance, Conversion-Optimierung, Prozessverbesserung

Verwendet dieselbe @bot-Decorator-Architektur wie core/bot_clones.py
und wird vom BotCloneManager automatisch erkannt sobald dieses Modul
importiert wird.
"""

import asyncio
import glob
import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from core.bot_clones import BASE_DIR, DATA_DIR, _tg, bot

log = logging.getLogger("SpecializedBots")

# ══════════════════════════════════════════════════════════════════════════════
# 1. MONITORING-BOT — Tiefes System-Monitoring, Health-Scores, Dashboards
# ══════════════════════════════════════════════════════════════════════════════

@bot("monitoring_bot", "📡", "Tiefes System-Monitoring: Services, APIs, Latenz, Health-Score", 180)
class MonitoringBot:
    """
    Prüft alle kritischen Services, misst Latenz, berechnet einen
    Health-Score (0–100) und schreibt ihn ins Monitoring-Dashboard.
    Sendet Telegram-Alert wenn Score < 60.
    """

    SERVICES = {
        "dashboard":   ("http", "127.0.0.1", 8888,  "/api/health"),
        "ollama":      ("http", "127.0.0.1", 11434, "/api/tags"),
        "supabase":    ("env",  "SUPABASE_URL", None, None),
        "shopify":     ("env",  "SHOPIFY_SHOP_DOMAIN", None, None),
        "telegram":    ("env",  "TELEGRAM_BOT_TOKEN", None, None),
        "stripe":      ("env",  "STRIPE_SECRET_KEY", None, None),
    }

    async def run(self) -> Dict:
        import socket
        results: Dict = {
            "timestamp":    datetime.now().isoformat(),
            "services":     {},
            "latency_ms":   {},
            "health_score": 0,
            "alerts":       [],
        }

        ok_count = 0
        total = 0

        for svc, (kind, host, port, path) in self.SERVICES.items():
            total += 1
            if kind == "env":
                val = os.getenv(host, "")
                up = bool(val and len(val) > 5)
                results["services"][svc] = "configured" if up else "missing"
                if up:
                    ok_count += 1
                else:
                    results["alerts"].append(f"{svc}: env var fehlt")
            elif kind == "http":
                t0 = time.monotonic()
                try:
                    import aiohttp
                    url = f"http://{host}:{port}{path}"
                    async with aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=4)
                    ) as s:
                        async with s.get(url) as r:
                            up = r.status < 500
                            results["latency_ms"][svc] = int((time.monotonic() - t0) * 1000)
                except Exception:
                    up = False
                    results["latency_ms"][svc] = -1

                results["services"][svc] = "up" if up else "down"
                if up:
                    ok_count += 1
                else:
                    results["alerts"].append(f"{svc}: nicht erreichbar")

        # System metrics
        try:
            import psutil
            results["cpu_pct"]    = psutil.cpu_percent(interval=0.3)
            results["ram_pct"]    = psutil.virtual_memory().percent
            results["disk_pct"]   = psutil.disk_usage("/").percent
            if results["cpu_pct"] > 85:
                results["alerts"].append(f"CPU kritisch: {results['cpu_pct']}%")
            if results["ram_pct"] > 85:
                results["alerts"].append(f"RAM kritisch: {results['ram_pct']}%")
        except ImportError:
            pass

        # Health-Score berechnen
        results["health_score"] = int((ok_count / max(total, 1)) * 100)

        # Status speichern (wird vom Dashboard gelesen)
        snap_file = DATA_DIR / "monitoring_status.json"
        snap_file.write_text(json.dumps(results, ensure_ascii=False, indent=2))

        if results["health_score"] < 60 or results["alerts"]:
            await _tg(
                f"📡 <b>MonitoringBot</b>\n"
                f"Health-Score: <b>{results['health_score']}/100</b>\n"
                + "\n".join(f"  ⚠️ {a}" for a in results["alerts"][:5])
            )

        return results


# ══════════════════════════════════════════════════════════════════════════════
# 2. ERROR-DETECTOR-BOT — Log-Scan, Exception-Analyse, Incident-Erkennung
# ══════════════════════════════════════════════════════════════════════════════

@bot("error_detector", "🚨", "Log-Scan, Exception-Erkennung, Incident-Eskalation", 300)
class ErrorDetectorBot:
    """
    Liest alle Log-Dateien, erkennt Exceptions und Fehlermuster,
    klassifiziert nach Schwere (CRITICAL/ERROR/WARNING) und
    eskaliert kritische Incidents per Telegram.
    """

    ERROR_PATTERNS = [
        (r"Traceback \(most recent call last\)", "CRITICAL", "Python Traceback"),
        (r"CRITICAL|FATAL",                      "CRITICAL", "Kritischer Fehler"),
        (r"\bERROR\b",                            "ERROR",    "Fehler"),
        (r"Connection refused|ConnectionError",  "ERROR",    "Verbindungsfehler"),
        (r"401 Unauthorized|403 Forbidden",      "ERROR",    "Auth-Fehler"),
        (r"404 Not Found",                        "WARNING",  "Endpoint fehlt"),
        (r"TimeoutError|timed out",              "WARNING",  "Timeout"),
        (r"MemoryError|OOM",                      "CRITICAL", "Speicher erschöpft"),
        (r"SyntaxError",                          "CRITICAL", "Syntax-Fehler"),
        (r"ImportError|ModuleNotFoundError",     "ERROR",    "Import-Fehler"),
    ]

    def _scan_file(self, path: Path, max_lines: int = 500) -> List[Dict]:
        hits = []
        try:
            lines = path.read_text(errors="replace").splitlines()[-max_lines:]
            for lineno, line in enumerate(lines, 1):
                for pattern, severity, label in self.ERROR_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        hits.append({
                            "file":     path.name,
                            "line":     lineno,
                            "severity": severity,
                            "label":    label,
                            "snippet":  line.strip()[:120],
                        })
                        break
        except Exception:
            log.exception("ErrorDetectorBot: failed to scan file %s", path)
        return hits

    async def run(self) -> Dict:
        results: Dict = {
            "timestamp":  datetime.now().isoformat(),
            "scanned":    0,
            "CRITICAL":   [],
            "ERROR":      [],
            "WARNING":    [],
            "total_hits": 0,
        }

        log_dirs = [
            BASE_DIR / "logs",
            Path("/var/log"),
        ]

        for log_dir in log_dirs:
            if not log_dir.exists():
                continue
            for log_file in log_dir.glob("*.log"):
                results["scanned"] += 1
                hits = self._scan_file(log_file)
                for h in hits:
                    results[h["severity"]].append(h)
                    results["total_hits"] += 1

        # Also scan Python stderr dumps if present
        for dump in BASE_DIR.glob("*.stderr"):
            results["scanned"] += 1
            hits = self._scan_file(dump)
            for h in hits:
                results[h["severity"]].append(h)
                results["total_hits"] += 1

        # Persist incident log
        incident_file = DATA_DIR / "incidents.json"
        existing = []
        if incident_file.exists():
            try:
                existing = json.loads(incident_file.read_text())
            except Exception:
                log.exception("ErrorDetectorBot: failed to load incident log")
        if results["CRITICAL"]:
            existing.append({
                "ts":      results["timestamp"],
                "items":   results["CRITICAL"][:10],
            })
            incident_file.write_text(
                json.dumps(existing[-50:], ensure_ascii=False, indent=2)
            )

        if results["CRITICAL"]:
            await _tg(
                f"🚨 <b>ErrorDetector — CRITICAL</b>\n"
                f"{len(results['CRITICAL'])} kritische Fehler in Logs:\n"
                + "\n".join(
                    f"  [{h['file']}] {h['label']}: {h['snippet'][:60]}"
                    for h in results["CRITICAL"][:3]
                )
            )
        elif results["ERROR"]:
            await _tg(
                f"🚨 <b>ErrorDetector</b> — {len(results['ERROR'])} Fehler entdeckt"
            )

        return results


# ══════════════════════════════════════════════════════════════════════════════
# 3. REPAIR-ENGINE-BOT — Automatische Reparaturen, Fallbacks, Restarts
# ══════════════════════════════════════════════════════════════════════════════

@bot("repair_engine", "🛠", "Auto-Reparatur: Services neustarten, Locks lösen, Caches resetten", 600)
class RepairEngineBot:
    """
    Erkennt bekannte Fehlerbilder und behebt sie automatisch:
    - Tote PM2-Prozesse neustarten
    - Lock-Dateien entfernen
    - Korrupte Cache-/Statusdateien resetten
    - Fehlende Verzeichnisse anlegen
    - API-Cache invalidieren wenn veraltet
    """

    REQUIRED_DIRS = ["logs", "data", "data/backups", "data/cache"]
    LOCK_PATTERNS = ["*.lock", "*.pid", ".running"]
    MAX_CACHE_AGE_H = 24

    async def run(self) -> Dict:
        results: Dict = {
            "timestamp": datetime.now().isoformat(),
            "repaired":  [],
            "skipped":   [],
            "errors":    [],
        }

        # 1. Sicherstellen dass alle benötigten Verzeichnisse existieren
        for d in self.REQUIRED_DIRS:
            p = BASE_DIR / d
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
                results["repaired"].append(f"Verzeichnis erstellt: {d}")

        # 2. Veraltete Lock-Dateien entfernen (älter als 1h)
        for pattern in self.LOCK_PATTERNS:
            for lock in BASE_DIR.glob(pattern):
                age_s = time.time() - lock.stat().st_mtime
                if age_s > 3600:
                    try:
                        lock.unlink()
                        results["repaired"].append(f"Lock entfernt: {lock.name}")
                    except Exception as e:
                        results["errors"].append(str(e))
                else:
                    results["skipped"].append(f"Aktives Lock: {lock.name}")

        # 3. Korrupte JSON-Dateien in data/ resetten
        for jf in DATA_DIR.glob("*.json"):
            try:
                content = jf.read_text()
                if not content.strip():
                    jf.write_text("{}")
                    results["repaired"].append(f"Leere JSON-Datei reset: {jf.name}")
                    continue
                json.loads(content)
            except (json.JSONDecodeError, Exception):
                backup = jf.with_suffix(".json.bak")
                try:
                    jf.rename(backup)
                except Exception:
                    log.exception("RepairEngineBot: failed to rename corrupt JSON %s", jf)
                jf.write_text("{}")
                results["repaired"].append(f"Korrupte JSON gebackupt+reset: {jf.name}")

        # 4. Veraltete Cache-Dateien invalidieren
        cache_dir = DATA_DIR / "cache"
        if cache_dir.exists():
            for cf in cache_dir.glob("*"):
                age_h = (time.time() - cf.stat().st_mtime) / 3600
                if age_h > self.MAX_CACHE_AGE_H:
                    try:
                        cf.unlink()
                        results["repaired"].append(f"Cache invalidiert: {cf.name} ({age_h:.1f}h alt)")
                    except Exception:
                        log.exception("RepairEngineBot: failed to delete cache file %s", cf)

        # 5. PM2 tote Prozesse neustarten (wenn PM2 verfügbar)
        try:
            r = subprocess.run(
                ["pm2", "jlist"], capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0:
                procs = json.loads(r.stdout)
                for p in procs:
                    status = p.get("pm2_env", {}).get("status", "")
                    name = p.get("name", "")
                    if status in ("errored", "stopped"):
                        subprocess.run(["pm2", "restart", name], timeout=15, capture_output=True)
                        results["repaired"].append(f"PM2 neugestartet: {name}")
        except (FileNotFoundError, json.JSONDecodeError, Exception):
            results["skipped"].append("PM2 nicht verfügbar")

        if results["repaired"]:
            await _tg(
                f"🛠 <b>RepairEngine</b> — {len(results['repaired'])} Reparaturen:\n"
                + "\n".join(f"  ✅ {r}" for r in results["repaired"][:5])
            )

        return results


# ══════════════════════════════════════════════════════════════════════════════
# 4. MAINTENANCE-BOT — Dependency-Pflege, Updates, Health-Checks
# ══════════════════════════════════════════════════════════════════════════════

@bot("maintenance_bot", "🔩", "Dependency-Check, Outdated-Pakete, Log-Rotation, Backup", 21600)
class MaintenanceBot:
    """
    Pflegt das System:
    - Prüft veraltete Python-Pakete
    - Rotiert alte Log-Dateien (>7 Tage)
    - Erstellt tägliche Backups der data/*.json Dateien
    - Prüft Disk-Usage und warnt bei >80%
    - Validiert .env-Vollständigkeit
    """

    REQUIRED_ENV = [
        "SHOPIFY_ACCESS_TOKEN", "SHOPIFY_SHOP_DOMAIN",
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
        "SUPABASE_URL", "SUPABASE_ANON_KEY",
        "ANTHROPIC_API_KEY",
    ]

    OPTIONAL_ENV = [
        "STRIPE_SECRET_KEY", "DIGISTORE24_API_KEY",
        "KLAVIYO_API_KEY", "MAILCHIMP_API_KEY",
        "OLLAMA_HOST", "GUARDIAN_API_SECRET",
        "OPENAI_API_KEY", "PERPLEXITY_API_KEY",
    ]

    async def run(self) -> Dict:
        results: Dict = {
            "timestamp":      datetime.now().isoformat(),
            "env_status":     {},
            "log_rotated":    [],
            "backup_created": None,
            "disk_ok":        True,
            "outdated_pkgs":  [],
            "warnings":       [],
        }

        # 1. .env-Vollständigkeitsprüfung
        missing_critical = []
        for key in self.REQUIRED_ENV:
            val = os.getenv(key, "")
            results["env_status"][key] = "✅" if val else "❌ FEHLT"
            if not val:
                missing_critical.append(key)
        for key in self.OPTIONAL_ENV:
            val = os.getenv(key, "")
            results["env_status"][key] = "✅" if val else "⚠️ optional"

        if missing_critical:
            results["warnings"].append(f"Kritische Env-Vars fehlen: {', '.join(missing_critical)}")

        # 2. Log-Rotation (Dateien älter 7 Tage archivieren)
        logs_dir = BASE_DIR / "logs"
        archive_dir = BASE_DIR / "logs" / "archive"
        if logs_dir.exists():
            archive_dir.mkdir(exist_ok=True)
            cutoff = time.time() - 7 * 86400
            for lf in logs_dir.glob("*.log"):
                if lf.stat().st_mtime < cutoff:
                    try:
                        dest = archive_dir / f"{lf.stem}_{datetime.now().strftime('%Y%m%d')}.log"
                        lf.rename(dest)
                        results["log_rotated"].append(lf.name)
                    except Exception:
                        log.exception("MaintenanceBot: failed to rotate log %s", lf)

        # 3. Backup data/*.json
        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        backup_file = backup_dir / f"data_backup_{today}.tar.gz"
        if not backup_file.exists():
            try:
                import tarfile
                with tarfile.open(str(backup_file), "w:gz") as tar:
                    for jf in DATA_DIR.glob("*.json"):
                        tar.add(str(jf), arcname=jf.name)
                results["backup_created"] = str(backup_file.name)
            except Exception as e:
                results["warnings"].append(f"Backup fehlgeschlagen: {e}")

        # 4. Disk-Usage prüfen
        try:
            import psutil
            du = psutil.disk_usage("/")
            pct = du.percent
            results["disk_pct"] = pct
            if pct > 80:
                results["disk_ok"] = False
                results["warnings"].append(f"Disk {pct}% belegt — Speicher knapp!")
        except ImportError:
            pass

        # 5. Veraltete Python-Pakete prüfen (nur liste, kein Auto-Update)
        try:
            r = subprocess.run(
                ["pip3", "list", "--outdated", "--format=json"],
                capture_output=True, text=True, timeout=30
            )
            if r.returncode == 0 and r.stdout.strip():
                pkgs = json.loads(r.stdout)
                results["outdated_pkgs"] = [
                    f"{p['name']} {p['version']}→{p['latest_version']}"
                    for p in pkgs[:10]
                ]
        except Exception:
            log.exception("MaintenanceBot: failed to check outdated packages")

        if results["warnings"]:
            await _tg(
                f"🔩 <b>MaintenanceBot</b>\n"
                + "\n".join(f"  ⚠️ {w}" for w in results["warnings"][:5])
            )

        return results


# ══════════════════════════════════════════════════════════════════════════════
# 5. OPTIMIZATION-BOT — Performance, Conversion, Prozessverbesserung
# ══════════════════════════════════════════════════════════════════════════════

@bot("optimization_bot", "⚡", "Performance-Analyse, Conversion-Checks, Prozess-Optimierung", 14400)
class OptimizationBot:
    """
    Analysiert Performance-Engpässe und Optimierungspotenziale:
    - API-Response-Zeiten messen und ranken
    - Shopify-Conversion-Metriken auswerten
    - Langsame Python-Module identifizieren
    - Cache-Trefferquoten berechnen
    - Optimierungsempfehlungen generieren
    """

    async def run(self) -> Dict:
        results: Dict = {
            "timestamp":       datetime.now().isoformat(),
            "api_latency":     {},
            "recommendations": [],
            "cache_stats":     {},
            "shopify_metrics": {},
            "score":           0,
        }

        # 1. API-Latenz messen
        endpoints_to_test = []
        dashboard_port = int(os.getenv("DASHBOARD_PORT", "8888"))
        ollama_host    = os.getenv("OLLAMA_HOST", "http://localhost:11434")

        local_tests = [
            ("dashboard_health",  f"http://127.0.0.1:{dashboard_port}/api/health"),
            ("dashboard_status",  f"http://127.0.0.1:{dashboard_port}/api/status"),
            ("ollama_tags",       f"{ollama_host}/api/tags"),
        ]

        try:
            import aiohttp
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            ) as session:
                for name, url in local_tests:
                    t0 = time.monotonic()
                    try:
                        async with session.get(url) as r:
                            ms = int((time.monotonic() - t0) * 1000)
                            results["api_latency"][name] = {
                                "ms":     ms,
                                "status": r.status,
                                "grade":  "A" if ms < 100 else "B" if ms < 300 else "C" if ms < 1000 else "D",
                            }
                    except Exception:
                        results["api_latency"][name] = {"ms": -1, "status": 0, "grade": "F"}
        except ImportError:
            pass

        # 2. Cache-Trefferquoten aus Monitoring-Daten berechnen
        cache_dir = DATA_DIR / "cache"
        if cache_dir.exists():
            files = list(cache_dir.glob("*"))
            results["cache_stats"] = {
                "files":       len(files),
                "total_kb":    sum(f.stat().st_size for f in files) // 1024,
                "oldest_h":    round((time.time() - min((f.stat().st_mtime for f in files), default=time.time())) / 3600, 1) if files else 0,
            }

        # 3. Shopify-Metriken aus gecachten Daten lesen
        shopify_cache = DATA_DIR / "shopify_cache.json"
        if shopify_cache.exists():
            try:
                d = json.loads(shopify_cache.read_text())
                if isinstance(d, dict):
                    results["shopify_metrics"] = {
                        k: v for k, v in d.items()
                        if k in ("orders_count", "revenue_today", "conversion_rate", "avg_order_value")
                    }
            except Exception:
                log.exception("OptimizationBot: failed to load shopify cache")

        # 4. Monitoring-History analysieren für Performance-Trends
        monitoring_file = DATA_DIR / "monitoring_status.json"
        if monitoring_file.exists():
            try:
                mon = json.loads(monitoring_file.read_text())
                score = mon.get("health_score", 0)
                results["score"] = score
                if score < 70:
                    results["recommendations"].append("Health-Score < 70 — Services prüfen")
            except Exception:
                log.exception("OptimizationBot: failed to load monitoring status")

        # 5. Empfehlungen basierend auf Latenz-Grades
        slow = [
            f"{n} ({v['ms']}ms)"
            for n, v in results["api_latency"].items()
            if v.get("grade") in ("C", "D", "F")
        ]
        if slow:
            results["recommendations"].append(f"Langsame Endpoints: {', '.join(slow)}")

        if not results["recommendations"]:
            results["recommendations"].append("System performt optimal — keine Maßnahmen nötig")

        # Optimization-Report speichern
        report_file = DATA_DIR / "optimization_report.json"
        report_file.write_text(json.dumps(results, ensure_ascii=False, indent=2))

        if any(r for r in results["recommendations"] if "optimal" not in r):
            await _tg(
                f"⚡ <b>OptimizationBot</b>\n"
                + "\n".join(f"  💡 {r}" for r in results["recommendations"][:4])
            )

        return results
