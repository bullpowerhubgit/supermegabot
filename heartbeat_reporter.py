#!/usr/bin/env python3
"""
RudiBot Heartbeat Reporter — Konsistente Status-Erfassung für alle Agenten
Schreibt ein sauberes JSON-Status-File ohne fehlerhafte Datenbasis.
"""
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# ── Konfiguration ──────────────────────────────────────────────────
_STATUS_FILE = Path("/tmp/rudibot_heartbeat.json")
_LOG_FILE = Path("/tmp/rudibot_heartbeat.log")

# Services mit Port und Health-Path
_SERVICES = {
    "guardian": {"port": 3201, "path": "/api/v1/health"},
    "telegram_bot": {"port": 3200, "path": "/health"},
    "api_gateway": {"port": 8080, "path": "/health"},
    "windsurf_api": {"port": 3001, "path": "/health"},
    "shopify_ai": {"port": 3002, "path": "/health"},
    "github_app": {"port": 3000, "path": "/health"},
    "rudibot_army": {"port": 8766, "path": "/health"},
    "ollama": {"port": 11434, "path": "/api/version", "optional": True},
}

# ── Helpers ────────────────────────────────────────────────────────
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    with open(_LOG_FILE, "a") as f:
        f.write(line + "\n")

def http_get(host, port, path, timeout=5):
    try:
        req = urllib.request.Request(f"http://{host}:{port}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return 0, str(e)

def check_openclaw():
    try:
        result = subprocess.run(
            ["nc", "-z", "localhost", "18789"],
            capture_output=True, timeout=2
        )
        return result.returncode == 0
    except Exception:
        return False

def check_vpn():
    """Prüfe Mullvad VPN Status (graceful, keine Admin-Rechte nötig)."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "mullvad"],
            capture_output=True, timeout=2
        )
        running = result.returncode == 0
        return {
            "status": "connected" if running else "disconnected",
            "running": running,
            "source": "pgrep",
            "note": "Last known location logged if previously connected"
        }
    except Exception as e:
        return {
            "status": "unknown",
            "running": False,
            "error": str(e),
            "source": "pgrep"
        }

# ── Haupt-Check ────────────────────────────────────────────────────
def run_checklist():
    log("=== RudiBot Heartbeat Checklist Start ===")
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "version": "2.1",
        "overall": "checking",
        "services": {},
        "system": {},
        "agents": {}
    }
    
    healthy_count = 0
    total_count = 0
    
    # 1. Service Health Checks
    for name, cfg in _SERVICES.items():
        total_count += 1
        is_optional = cfg.get("optional", False)
        status, body = http_get("localhost", cfg["port"], cfg["path"])
        healthy = status == 200
        
        if healthy:
            healthy_count += 1
            level = "OK"
        elif is_optional:
            level = "INFO"
        else:
            level = "WARN"
        
        log(f"{name}: {'HEALTHY' if healthy else 'UNREACHABLE'} (HTTP {status})", level)
        
        results["services"][name] = {
            "port": cfg["port"],
            "healthy": healthy,
            "status_code": status,
            "optional": is_optional,
            "state": "STABIL" if healthy else ("INFO" if is_optional else "UNSTABIL")
        }
    
    # 2. OpenClaw Check (graceful, keine Admin-Rechte)
    openclaw_ok = check_openclaw()
    results["services"]["openclaw"] = {
        "port": 18789,
        "healthy": openclaw_ok,
        "status_code": 200 if openclaw_ok else 0,
        "optional": True,
        "state": "STABIL" if openclaw_ok else "BLOCKIERT",
        "note": "Requires admin rights to start; skipped gracefully if unavailable"
    }
    log(f"openclaw: {'RUNNING' if openclaw_ok else 'BLOCKIERT (no admin rights)'}", 
        "OK" if openclaw_ok else "INFO")
    
    # 3. VPN Status
    vpn = check_vpn()
    results["agents"]["vpn"] = vpn
    log(f"vpn: {vpn['status']}", "OK" if vpn['running'] else "INFO")
    
    # 4. System Resources (graceful, keine Admin-Rechte)
    try:
        mem = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=3)
        disk = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=3)
        results["system"] = {
            "memory_raw": mem.stdout[:500] if mem.returncode == 0 else "unavailable",
            "disk_raw": disk.stdout[:500] if disk.returncode == 0 else "unavailable",
            "state": "STABIL"
        }
        log("system_resources: OK", "OK")
    except Exception as e:
        results["system"] = {
            "error": str(e),
            "state": "BLOCKIERT",
            "note": "Some system commands may fail without elevated permissions"
        }
        log(f"system_resources: BLOCKIERT ({e})", "INFO")
    
    # 5. Overall Status
    critical = sum(1 for s in results["services"].values() 
                   if not s.get("optional") and not s.get("healthy"))
    
    if critical == 0:
        results["overall"] = "HEARTBEAT_OK"
    elif critical <= 2:
        results["overall"] = "HEARTBEAT_DEGRADED"
    else:
        results["overall"] = "HEARTBEAT_CRITICAL"
    
    results["summary"] = {
        "healthy": healthy_count,
        "total": total_count + 2,  # + openclaw + vpn
        "critical_failures": critical
    }
    
    # 6. Persistiere saubere Datenbasis
    _STATUS_FILE.write_text(json.dumps(results, indent=2, default=str))
    log(f"Status written to {_STATUS_FILE}")
    log(f"Overall: {results['overall']}")
    log("=== RudiBot Heartbeat Checklist Ende ===\n")
    
    return results

if __name__ == "__main__":
    run_checklist()
