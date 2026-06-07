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

COMMANDER_SCRIPT = ARMY_DIR / "army_commander.py"

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

def kill_all_commanders():
    """Killt ALLE army_commander Prozesse außer diesem Supervisor"""
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
                        os.kill(pid, signal.SIGTERM)
                        time.sleep(1)
                        try:
                            os.kill(pid, 0)
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        log(f"🛑 Killed old commander PID {pid}")
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
    except Exception as e:
        log(f"⚠️ kill_all_commanders error: {e}")

def get_commander_pid():
    """Gibt PID des laufenden commanders zurück oder None"""
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
    """Startet den Army Commander frisch"""
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

def system_health_snapshot():
    """Gibt einen System-Health-Snapshot zurück"""
    health = {}
    # RAM
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
        health["ram_pct"] = round((used / total) * 100, 1) if total > 0 else 0
    except Exception:
        health["ram_pct"] = 0

    # Disk
    try:
        df_out = subprocess.run("df -h /", shell=True, capture_output=True, text=True, timeout=5).stdout
        lines = df_out.strip().splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 5:
                health["disk_pct"] = float(parts[4].replace('%', ''))
    except Exception:
        health["disk_pct"] = 0

    # Laufende Prozesse
    try:
        result = subprocess.run(["pgrep", "-f", "rudibot-army"], capture_output=True, text=True, timeout=3)
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
    log("="*60)
    log("🛡️  META-SUPERVISOR gestartet")
    log("   Aufgaben: Commander überwachen | Duplikate verhindern |")
    log("   Konten prüfen | Umsatz tracken | Fehler verhindern")
    log("="*60)

    # Startup: Alles aufräumen
    log("🧹 Startup-Cleanup...")
    kill_all_commanders()
    time.sleep(2)

    # Starte Commander
    commander_proc = start_commander()
    time.sleep(5)

    last_health_check = 0
    last_duplicate_check = 0
    last_monetization_check = 0
    last_system_check = 0
    last_disk_check = 0
    commander_restart_count = 0
    last_restart_time = time.time()

    while True:
        now = time.time()

        # 0. Disk Space überwachen (alle 5 Min)
        if now - last_disk_check > 300:
            status, avail = check_disk_space()
            if status == "ok":
                log(f"💾 Disk: {avail:.1f} GB frei")
            last_disk_check = now

        # 1. Prüfe ob Commander läuft
        commander_pid = get_commander_pid()
        if commander_pid is None:
            log("🔴 Commander nicht gefunden! Neustart...")
            commander_restart_count += 1
            last_restart_time = now

            # Backoff bei zu vielen Restarts
            if commander_restart_count >= 5 and (now - last_restart_time) < 300:
                wait = min(60 * commander_restart_count, 300)
                log(f"⏳ Backoff: Warte {wait}s vor Restart #{commander_restart_count}")
                time.sleep(wait)

            kill_all_commanders()
            time.sleep(2)
            commander_proc = start_commander()

            if commander_restart_count % 3 == 0:
                send_critical_alert(f"Commander ist {commander_restart_count}× neu gestartet worden. Prüfe System!")
        else:
            # Reset counter wenn lange stabil
            if now - last_restart_time > 1800:
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

if __name__ == "__main__":
    main()
