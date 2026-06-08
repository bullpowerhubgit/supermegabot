#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  META-SUPERVISOR — Überwacht den Army Commander                     ║
║  Nie wieder: Commander crasht unbemerkt, doppelte Prozesse,        ║
║  verlorene Fehler, ungenutzte Konten, verpasste Umsätze            ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import os, sys, time, subprocess, signal, json, datetime
from pathlib import Path

ARMY_DIR = Path(__file__).parent
LOGS_DIR = ARMY_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
SUPERVISOR_LOG = LOGS_DIR / "meta_supervisor.log"
LOCK_FILE = ARMY_DIR / ".meta_supervisor.lock"
PID_FILE = ARMY_DIR / ".commander.pid"

COMMANDER_SCRIPT = ARMY_DIR / "army_commander.py"

# ═══════════════════════════════════════════════════════════════════════
# SINGLETON LOCK — Verhindert doppelte Supervisor-Instanzen
# ═══════════════════════════════════════════════════════════════════════
def acquire_lock():
    """File-basiertes Lock — nur EIN Supervisor darf laufen"""
    import fcntl
    try:
        fd = open(LOCK_FILE, 'w')
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except (IOError, OSError):
        log("🔒 Meta-Supervisor läuft bereits — beende mich")
        sys.exit(1)

def release_lock(lock_fd):
    import fcntl
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass

EMAILS = [
    "dragonadnp@gmail.com",
    "nikolestimi@gmail.com",
    "bullpowersrtkennels@gmail.com",
    "looopwave@gmail.com",
    "aitecbuuss@gmail.com",
    "rudolf.sarkany@aitec.de",
    "rudolf.sarkany.aiitec@gmail.com",
]

MONETIZATION_GOALS = {
    "daily_target": 500.0,
    "weekly_target": 3500.0,
    "monthly_target": 15000.0,
    "stripe_check_interval": 300,
}

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(SUPERVISOR_LOG, "a") as f:
        f.write(line + "\n")

def kill_all_commanders(own_pid=None):
    """Killt ALLE army_commander Prozesse außer diesem Supervisor und optional own_pid"""
    killed = []
    try:
        result = subprocess.run(
            ["pgrep", "-f", "army_commander.py"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for pid_str in result.stdout.strip().splitlines():
                try:
                    pid = int(pid_str)
                    if pid != os.getpid() and pid != os.getppid() and pid != own_pid:
                        os.kill(pid, signal.SIGTERM)
                        time.sleep(0.5)
                        try:
                            os.kill(pid, 0)
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        killed.append(pid)
                        log(f"🛑 Killed old commander PID {pid}")
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
    except Exception as e:
        log(f"⚠️ kill_all_commanders error: {e}")
    return killed

def get_tracked_commander():
    """Prüft ob der von uns gestartete Commander noch läuft"""
    try:
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            # Prüfe ob Prozess existiert
            os.kill(pid, 0)
            return pid
    except (ValueError, ProcessLookupError, PermissionError):
        pass
    return None

def get_commander_pid():
    """Fallback: Gibt PID eines laufenden commanders zurück oder None"""
    # Priorität: unser getrackter Commander
    tracked = get_tracked_commander()
    if tracked:
        return tracked
    # Fallback: pgrep
    try:
        result = subprocess.run(
            ["pgrep", "-f", "army_commander.py"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for pid_str in result.stdout.strip().splitlines():
                try:
                    pid = int(pid_str)
                    if pid != os.getpid() and pid != os.getppid():
                        return pid
                except ValueError:
                    pass
    except Exception:
        pass
    return None

def start_commander():
    """Startet den Army Commander frisch und trackt PID"""
    log("🚀 Starte Army Commander...")
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")
    proc = subprocess.Popen(
        [sys.executable, str(COMMANDER_SCRIPT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env
    )
    # Speichere PID für Tracking
    PID_FILE.write_text(str(proc.pid))
    log(f"✅ Commander gestartet (PID {proc.pid})")
    return proc

def check_duplicate_agents():
    """Prüft auf doppelte Agenten-Prozesse und killt Duplikate"""
    agents_to_check = [
        "agent_resource_manager.py",
        "agent_monitor.py",
        "agent_optimizer.py",
        "agent_shopify.py",
        "micro_clean.py",
        "micro_ai.py",
    ]
    for script in agents_to_check:
        try:
            result = subprocess.run(
                ["pgrep", "-f", script],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                pids = [int(p) for p in result.stdout.strip().splitlines() if p.strip()]
                if len(pids) > 1:
                    # Älteste behalten, neuere killen
                    pids.sort()
                    for pid in pids[1:]:
                        try:
                            os.kill(pid, signal.SIGTERM)
                            log(f"🧹 Duplikat gekillt: {script} PID {pid}")
                        except ProcessLookupError:
                            pass
        except Exception:
            pass

def check_account_health():
    """Schneller Check: Sind alle 7 Konten in Configs vertreten?"""
    search_paths = [
        Path.home() / "windsurf",
        Path.home() / "supermegabot",
        Path.home() / "windsurf-shopify-suite",
    ]
    found_emails = set()
    for base in search_paths:
        if not base.exists():
            continue
        for env_file in base.rglob(".env*"):
            try:
                text = env_file.read_text(errors='ignore')
                for email in EMAILS:
                    if email in text:
                        found_emails.add(email)
            except Exception:
                pass

    missing = set(EMAILS) - found_emails
    if missing:
        log(f"🔴 Konten NICHT in Configs gefunden: {', '.join(missing)}")
        return False, missing
    return True, set()

def monetization_check():
    """Prüft monetäre Ziele und aktuelle Umsätze"""
    revenue_data = {"stripe": 0.0, "sources": []}
    try:
        stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
        if stripe_key and stripe_key.startswith("sk_"):
            import urllib.request
            req = urllib.request.Request(
                "https://api.stripe.com/v1/charges?limit=100&created[gte]=" + str(int(time.time() - 86400)),
                headers={"Authorization": f"Bearer {stripe_key}"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if data.get("data"):
                    daily_revenue = sum(ch.get("amount", 0) for ch in data["data"]) / 100
                    revenue_data["stripe"] = daily_revenue
                    revenue_data["sources"].append(f"Stripe daily: €{daily_revenue:.2f}")
                    if daily_revenue < MONETIZATION_GOALS["daily_target"]:
                        log(f"💰 Daily Revenue: €{daily_revenue:.2f} (Ziel: €{MONETIZATION_GOALS['daily_target']})")
    except Exception as e:
        log(f"⚠️ Monetization check error: {e}")
    return revenue_data

def check_ram_usage():
    """Prüft RAM-Nutzung — warnt bei > 90%"""
    try:
        result = subprocess.run("vm_stat", shell=True, capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().splitlines()
        vals = {}
        for line in lines:
            if ":" in line:
                k = line.split(":")[0].strip().replace('"', '')
                v = line.split(":")[1].strip().rstrip('.')
                try:
                    vals[k] = int(v)
                except ValueError:
                    pass
        
        used = vals.get("Pages active", 0) + vals.get("Pages wired down", 0) + vals.get("Pages occupied by compressor", 0)
        total = used + vals.get("Pages free", 0) + vals.get("Pages inactive", 0) + vals.get("Pages speculative", 0)
        
        if total > 0:
            ram_pct = round((used / total) * 100, 1)
            if ram_pct > 90:
                return "critical", ram_pct
            elif ram_pct > 80:
                return "warning", ram_pct
            else:
                return "ok", ram_pct
        return "unknown", 0
    except Exception as e:
        log(f"⚠️ RAM check error: {e}")
        return "error", 0

def check_disk_space():
    """Prüft freien Speicher — warnt bei < 5 GB"""
    try:
        result = subprocess.run("df -h /", shell=True, capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 4:
                avail_str = parts[3]
                # Parse z.B. "7.0Gi" oder "500Mi"
                if avail_str.endswith('Gi'):
                    avail_gb = float(avail_str[:-2])
                elif avail_str.endswith('Mi'):
                    avail_gb = float(avail_str[:-2]) / 1024
                elif avail_str.endswith('Ti'):
                    avail_gb = float(avail_str[:-2]) * 1024
                else:
                    avail_gb = float(avail_str) / (1024*1024*1024)

                pct = float(parts[4].replace('%', ''))

                if avail_gb < 2:
                    log(f"🔴 KRITISCH: Nur {avail_gb:.1f} GB frei! Sofort aufräumen!")
                    send_critical_alert(f"🚨 DISK SPACE KRITISCH\nNur {avail_gb:.1f} GB frei auf dem Mac!\nStarte sofort: python3 ~/supermegabot/rudibot-army/cleanup.py")
                    return "critical", avail_gb
                elif avail_gb < 5:
                    log(f"🟠 WARNUNG: Nur {avail_gb:.1f} GB frei")
                    send_critical_alert(f"⚠️ Disk Space niedrig\nNur {avail_gb:.1f} GB frei. Bald aufräumen!")
                    return "warning", avail_gb
                else:
                    return "ok", avail_gb
    except Exception as e:
        log(f"⚠️ Disk check error: {e}")
    return "unknown", 0

def check_ram_usage():
    """Prüft RAM-Nutzung — killt Ollama bei > 90% und warnt bei > 80%"""
    try:
        out = subprocess.run("vm_stat", shell=True, capture_output=True, text=True, timeout=5).stdout
        vals = {}
        for line in out.splitlines():
            if ":" in line:
                k = line.split(":")[0].strip().replace('"', '')
                v = line.split(":")[1].strip().rstrip('.')
                try:
                    vals[k] = int(v)
                except ValueError:
                    pass
        used = vals.get("Pages active", 0) + vals.get("Pages wired down", 0) + vals.get("Pages occupied by compressor", 0)
        total = used + vals.get("Pages free", 0) + vals.get("Pages inactive", 0) + vals.get("Pages speculative", 0)
        if total > 0:
            pct = (used / total) * 100
            if pct > 90:
                log(f"🔴 RAM KRITISCH: {pct:.1f}% — Stoppe Ollama!")
                # Kill Ollama (der RAM-Fresser)
                try:
                    subprocess.run(["pkill", "-f", "ollama"], capture_output=True, timeout=3)
                    log("🛑 Ollama gekillt (RAM-Kritisch)")
                    send_critical_alert(f"🛑 RAM {pct:.1f}% KRITISCH!\nOllama wurde automatisch gestoppt.")
                except Exception:
                    pass
                return "critical", pct
            elif pct > 80:
                log(f"🟠 RAM hoch: {pct:.1f}%")
                send_critical_alert(f"⚠️ RAM {pct:.1f}% hoch!\nSchließe ungenutzte Apps.")
                return "warning", pct
            else:
                return "ok", pct
    except Exception as e:
        log(f"⚠️ RAM check error: {e}")
    return "unknown", 0

def system_health_snapshot():
    """Gibt einen System-Health-Snapshot zurück"""
    health = {}
    # RAM
    try:
        # FIX: vm_stat may require permissions
        try:
            out = subprocess.run("vm_stat", shell=True, capture_output=True, text=True, timeout=5).stdout
        except Exception:
            out = ""  # Graceful fallback
        vals = {}
        for line in out.splitlines():
            if ":" in line:
                k = line.split(":")[0].strip().replace('"', '')
                v = line.split(":")[1].strip().rstrip('.')
                try:
                    vals[k] = int(v)
                except ValueError:
                    pass
        used = vals.get("Pages active", 0) + vals.get("Pages wired down", 0) + vals.get("Pages occupied by compressor", 0)
        total = used + vals.get("Pages free", 0) + vals.get("Pages inactive", 0) + vals.get("Pages speculative", 0)
        health["ram_pct"] = round((used / total) * 100, 1) if total > 0 else 0
    except Exception:
        health["ram_pct"] = 0

    # Disk
    try:
        # FIX: df may require permissions
        try:
            df_out = subprocess.run("df -h /", shell=True, capture_output=True, text=True, timeout=5).stdout
        except Exception:
            df_out = ""  # Graceful fallback
        lines = df_out.strip().splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 5:
                health["disk_pct"] = float(parts[4].replace('%', ''))
    except Exception:
        health["disk_pct"] = 0

    # Laufende Prozesse
    try:
        # FIX: pgrep may fail without permissions
        try:
            result = subprocess.run(["pgrep", "-f", "rudibot-army"], capture_output=True, text=True, timeout=3)
        except Exception:
            result = None  # Graceful fallback
        health["army_processes"] = len(result.stdout.strip().splitlines()) if result.returncode == 0 else 0
    except Exception:
        health["army_processes"] = 0

    return health

def send_critical_alert(message):
    """Sendet kritische Alerts via Telegram wenn verfügbar"""
    try:
        sys.path.insert(0, str(ARMY_DIR / "shared"))
        from bus import notify_telegram
        notify_telegram(f"🚨 <b>META-SUPERVISOR ALERT</b>\n{message}")
    except Exception:
        log(f"Could not send Telegram alert: {message}")

def main():
    # Singleton Lock — verhindert doppelte Instanzen
    lock_fd = acquire_lock()
    try:
        log("="*60)
        log("🛡️  META-SUPERVISOR gestartet")
        log("   Aufgaben: Commander überwachen | Duplikate verhindern |")
        log("   Konten prüfen | Umsatz tracken | Fehler verhindern")
        log("   Lock aktiv — keine doppelten Instanzen möglich")
        log("="*60)

        # Startup: Alles aufräumen (nur fremde commander)
        log("🧹 Startup-Cleanup...")
        kill_all_commanders()
        time.sleep(2)

        # Starte Commander
        commander_proc = start_commander()
        own_commander_pid = commander_proc.pid
        time.sleep(5)

        last_health_check = 0
        last_duplicate_check = 0
        last_monetization_check = 0
        last_system_check = 0
        last_disk_check = 0
        last_ram_check = 0
        commander_restart_count = 0
        last_restart_time = time.time()
        last_restart_attempt = 0  # Grace period tracking
        GRACE_PERIOD = 15  # Sekunden nach Restart

        while True:
            now = time.time()

            # 0. Disk Space überwachen (alle 5 Min)
            if now - last_disk_check > 300:
                status, avail = check_disk_space()
                if status == "ok":
                    log(f"💾 Disk: {avail:.1f} GB frei")
                last_disk_check = now

            # 0b. RAM überwachen (alle 2 Min — schneller als Disk!)
            if now - last_ram_check > 120:
                ram_status, ram_pct = check_ram_usage()
                if ram_status == "ok":
                    log(f"🧠 RAM: {ram_pct:.1f}% — OK")
                last_ram_check = now

            # 1. Prüfe ob Commander läuft (Grace Period beachten)
            if now - last_restart_attempt > GRACE_PERIOD:
                commander_pid = get_commander_pid()
                if commander_pid is None:
                    log("🔴 Commander nicht gefunden! Neustart...")
                    commander_restart_count += 1
                    last_restart_time = now
                    last_restart_attempt = now

                    # Backoff bei zu vielen Restarts
                    if commander_restart_count >= 5 and (now - last_restart_time) < 300:
                        wait = min(60 * commander_restart_count, 300)
                        log(f"⏳ Backoff: Warte {wait}s vor Restart #{commander_restart_count}")
                        time.sleep(wait)

                    # Kill nur fremde commander, nicht unseren eigenen
                    kill_all_commanders(own_pid=own_commander_pid)
                    time.sleep(2)
                    commander_proc = start_commander()
                    own_commander_pid = commander_proc.pid

                    if commander_restart_count % 3 == 0:
                        send_critical_alert(f"Commander ist {commander_restart_count}× neu gestartet worden. Prüfe System!")
                else:
                    # Reset counter wenn lange stabil
                    if now - last_restart_time > 1800:
                        if commander_restart_count > 0:
                            log(f"✅ Commander stabil seit 30min — Reset Restart-Counter")
                        commander_restart_count = 0

            # 2. Alle 60s: Duplikate checken
            if now - last_duplicate_check > 60:
                check_duplicate_agents()
                last_duplicate_check = now

            # 3. Alle 10 Min: Konten-Health
            if now - last_health_check > 600:
                ok, missing = check_account_health()
                if not ok:
                    log(f"🔴 FEHLENDE KONTEN: {missing}")
                    send_critical_alert(f"Konten nicht in Configs: {', '.join(missing)}")
                last_health_check = now

            # 4. Alle 5 Min: Monetarisierung
            if now - last_monetization_check > MONETIZATION_GOALS["stripe_check_interval"]:
                rev = monetization_check()
                log(f"💰 Revenue-Check: {rev['sources']}")
                last_monetization_check = now

            # 5. Alle 2 Min: System-Health
            if now - last_system_check > 120:
                health = system_health_snapshot()
                log(f"🌡️  RAM {health.get('ram_pct', '?')}% | Disk {health.get('disk_pct', '?')}% | Prozesse {health.get('army_processes', '?')}")
                if health.get("ram_pct", 0) > 90:
                    send_critical_alert(f"KRITISCH: RAM bei {health['ram_pct']}%!")
                last_system_check = now

            time.sleep(10)
    finally:
        release_lock(lock_fd)

if __name__ == "__main__":
    main()
