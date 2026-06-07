#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  START ALL — Master-Startskript für die gesamte RudiBot Army      ║
║  Startet: Meta-Supervisor + Dashboard-Server + öffnet Dashboard    ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import os, sys, time, subprocess, webbrowser
from pathlib import Path

ARMY_DIR = Path(__file__).parent
LOGS_DIR = ARMY_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

PROCESSES = {
    "meta_supervisor": {
        "script": "meta_supervisor.py",
        "log": "meta_supervisor.log",
    },
    "dashboard_server": {
        "script": "dashboard_server.py",
        "log": "dashboard_server.log",
    },
    "dashboard_http": {
        "script": "dashboard_http_server.py",
        "log": "dashboard_http.log",
    },
}

def is_running(script_name):
    try:
        result = subprocess.run(
            ["pgrep", "-f", script_name],
            capture_output=True, text=True, timeout=3
        )
        return result.returncode == 0 and result.stdout.strip()
    except Exception:
        return False

def kill_all():
    print("🛑 Beende alle RudiBot Prozesse...")
    for name, cfg in PROCESSES.items():
        try:
            subprocess.run(["pkill", "-9", "-f", cfg["script"]], capture_output=True)
        except Exception:
            pass
    # Auch Commander killen (wird vom Supervisor neu gestartet)
    try:
        subprocess.run(["pkill", "-9", "-f", "army_commander.py"], capture_output=True)
    except Exception:
        pass
    time.sleep(2)
    print("✅ Alle Prozesse beendet")

def start_process(name, cfg):
    if is_running(cfg["script"]):
        print(f"✅ {name} läuft bereits")
        return True

    script_path = ARMY_DIR / cfg["script"]
    log_path = LOGS_DIR / cfg["log"]

    print(f"🚀 Starte {name}...")
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")

    proc = subprocess.Popen(
        [sys.executable, str(script_path)],
        stdout=open(log_path, "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=env
    )
    time.sleep(3)

    if is_running(cfg["script"]):
        print(f"✅ {name} gestartet (PID {proc.pid})")
        return True
    else:
        print(f"❌ {name} konnte nicht gestartet werden")
        return False

def open_dashboard():
    url = "http://localhost:8765/dashboard.html"
    print(f"🌐 Öffne Dashboard: {url}")
    webbrowser.open(url)

def show_status():
    print("\n📊 Aktueller Status:")
    print("-" * 50)
    for name, cfg in PROCESSES.items():
        status = "✅ Running" if is_running(cfg["script"]) else "❌ Stopped"
        print(f"  {name}: {status}")

    # Agenten-Status
    agent_scripts = [
        "agent_resource_manager.py", "agent_monitor.py", "agent_optimizer.py",
        "agent_shopify.py", "agent_social.py", "agent_finance.py",
        "agent_monetization.py", "agent_learner.py", "agent_security.py",
    ]
    running_agents = 0
    for script in agent_scripts:
        if is_running(script):
            running_agents += 1
    print(f"  Agents: {running_agents}/{len(agent_scripts)} running")

    # Micro Bots
    micro_scripts = [
        "micro_ping.py", "micro_revenue.py", "micro_backup.py",
        "micro_clean.py", "micro_ai.py",
    ]
    running_micros = 0
    for script in micro_scripts:
        if is_running(script):
            running_micros += 1
    print(f"  Micro Bots: {running_micros}/{len(micro_scripts)} running")
    print("-" * 50)

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "stop":
            kill_all()
            return
        elif cmd == "status":
            show_status()
            return
        elif cmd == "restart":
            kill_all()
            time.sleep(3)
            # Continue to start
        else:
            print(f"Unbekannter Befehl: {cmd}")
            print("Usage: python3 start_all.py [start|stop|restart|status]")
            return

    print("=" * 60)
    print("  🤖 RUDIBOT ARMY — Master Start")
    print("=" * 60)

    # 1. Meta-Supervisor starten (startet automatisch den Commander)
    start_process("meta_supervisor", PROCESSES["meta_supervisor"])

    # 2. Dashboard-Server starten
    start_process("dashboard_server", PROCESSES["dashboard_server"])

    # 3. Warte kurz bis alles läuft
    time.sleep(5)

    # 4. Dashboard öffnen
    open_dashboard()

    # 5. Status anzeigen
    show_status()

    print("\n✅ Alles gestartet! Dashboard ist im Browser geöffnet.")
    print(f"📊 Log-Dateien: {LOGS_DIR}")
    print("🛑 Zum Stoppen: python3 start_all.py stop")

if __name__ == "__main__":
    main()
