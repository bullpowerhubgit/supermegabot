#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  RUDIBOT ARMY COMMANDER — Verwaltet alle Agenten                   ║
║  Startet, überwacht und koordiniert die komplette Bot-Army          ║
║  6 spezialisierte Agenten + Self-Healing + Telegram Reports        ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import os, sys, time, subprocess, signal, json, datetime
from pathlib import Path

ARMY_DIR = Path(__file__).parent
AGENTS_DIR = ARMY_DIR / "agents"
LOGS_DIR = ARMY_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(ARMY_DIR / "shared"))
from bus import report, notify_telegram, load_state, get_env

AGENTS = [
    {"id": "monitor",   "file": "agent_monitor.py",   "icon": "🔴", "desc": "Service Monitor"},
    {"id": "shopify",   "file": "agent_shopify.py",   "icon": "🛒", "desc": "Shopify Watcher"},
    {"id": "social",    "file": "agent_social.py",    "icon": "📱", "desc": "Social Autopilot"},
    {"id": "finance",   "file": "agent_finance.py",   "icon": "💰", "desc": "Finance Tracker"},
    {"id": "learner",   "file": "agent_learner.py",   "icon": "🧠", "desc": "Auto Learner"},
    {"id": "security",  "file": "agent_security.py",  "icon": "🔐", "desc": "Security Guard"},
    {"id": "optimizer", "file": "agent_optimizer.py", "icon": "⚡", "desc": "Optimizer"},
]

# ── Micro Bots ────────────────────────────────────────────────────────────────
MICRO_DIR = ARMY_DIR / "micro"
MICRO_BOTS = [
    {"id": "micro_ping",    "file": "micro_ping.py",    "icon": "🏓", "desc": "Service Ping"},
    {"id": "micro_revenue", "file": "micro_revenue.py", "icon": "💸", "desc": "Revenue Tracker"},
    {"id": "micro_backup",  "file": "micro_backup.py",  "icon": "💾", "desc": "Auto Backup"},
    {"id": "micro_clean",   "file": "micro_clean.py",   "icon": "🧹", "desc": "Log Cleaner"},
    {"id": "micro_ai",      "file": "micro_ai.py",      "icon": "🤖", "desc": "KI-Tipp Daily"},
]

running_procs = {}

def start_agent(agent, base_dir=None):
    base_dir = base_dir or AGENTS_DIR
    aid = agent["id"]
    script = base_dir / agent["file"]
    log = LOGS_DIR / f"{aid}.log"

    # Prüfe ob schon läuft
    if aid in running_procs:
        p = running_procs[aid]
        if p.poll() is None:
            return True  # läuft noch

    print(f"  {agent['icon']} Starte {agent['desc']} ({aid})...")
    with open(log, "a") as lf:
        env = os.environ.copy()
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH","")
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            stdout=lf, stderr=lf,
            start_new_session=True, env=env
        )
        running_procs[aid] = proc
        return True

def stop_all():
    print("🛑 Stoppe alle Agenten...")
    for aid, proc in running_procs.items():
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except: proc.kill()
    print("✅ Alle gestoppt")

def status_report():
    state = load_state()
    agents = state.get("agents", {})
    lines = []
    for a in AGENTS:
        aid = a["id"]
        info = agents.get(aid, {})
        status_icon = {"ok":"✅","warning":"⚠️","error":"❌","repaired":"🔧"}.get(info.get("status","?"),"❓")
        msg = info.get("message","Keine Daten")[:60]
        ts = info.get("ts","?")
        lines.append(f"{a['icon']} <b>{a['desc']}</b>: {status_icon} {msg}")
    return "\n".join(lines)

def run():
    print("╔══════════════════════════════════════╗")
    print("║   🤖 RUDIBOT ARMY COMMANDER          ║")
    print(f"║   {len(AGENTS)} Agenten werden gestartet       ║")
    print("╚══════════════════════════════════════╝")
    print()
    
    # Alle Agenten starten
    for agent in AGENTS:
        start_agent(agent, AGENTS_DIR)
        time.sleep(1)

    # Micro Bots starten
    print("\n  ── Micro Bots ──")
    for bot in MICRO_BOTS:
        start_agent(bot, MICRO_DIR)
        time.sleep(0.5)

    total = len(AGENTS) + len(MICRO_BOTS)
    print(f"\n✅ {len(AGENTS)} Agenten + {len(MICRO_BOTS)} Micro Bots = {total} gesamt\n")
    notify_telegram(
        f"🤖 <b>RudiBot Army online!</b>\n"
        f"{len(AGENTS)} Agenten + {len(MICRO_BOTS)} Micro Bots:\n" +
        "\n".join(f"{a['icon']} {a['desc']}" for a in AGENTS + MICRO_BOTS)
    )
    
    def shutdown(sig, frame):
        stop_all()
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    last_report = time.time()
    all_workers = AGENTS + MICRO_BOTS
    crash_counts = {a["id"]: 0 for a in all_workers}

    while True:
        # Watchdog für Agenten + Micro Bots
        for agent in AGENTS:
            aid = agent["id"]
            proc = running_procs.get(aid)
            if proc and proc.poll() is not None:
                crash_counts[aid] += 1
                print(f"⚠️  {agent['icon']} {aid} gecrasht (#{crash_counts[aid]}), neustart...")
                start_agent(agent, AGENTS_DIR)
                if crash_counts[aid] % 5 == 0:
                    notify_telegram(f"⚠️ Agent <b>{aid}</b> ist {crash_counts[aid]}× gecrasht")

        for bot in MICRO_BOTS:
            bid = bot["id"]
            proc = running_procs.get(bid)
            if proc and proc.poll() is not None:
                crash_counts[bid] += 1
                start_agent(bot, MICRO_DIR)
                if crash_counts[bid] % 10 == 0:
                    notify_telegram(f"⚠️ MicroBot <b>{bid}</b> ist {crash_counts[bid]}× gecrasht")
        
        # Stündlicher Status-Report
        if time.time() - last_report > 3600:
            report_txt = status_report()
            notify_telegram(f"📊 <b>Army Status</b>\n{report_txt}")
            last_report = time.time()
        
        time.sleep(15)

if __name__ == "__main__":
    run()
