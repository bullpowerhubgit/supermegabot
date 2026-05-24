#!/usr/bin/env python3
"""
Self-Learner Bridge for SuperMegaBot
Integrates the shared Self-Learner core into SuperMegaBot.
"""

import sys
import os

# Add home directory to path for self_learner_core
sys.path.insert(0, os.path.expanduser("~"))

from self_learner_core import SelfLearner

# Singleton instance
_learner = None


def get_learner():
    """Get or create the SelfLearner instance for supermegabot."""
    global _learner
    if _learner is None:
        _learner = SelfLearner("supermegabot", telegram_notify=True)
        _learner.load_learned_skills()
        _register_supermegabot_skills()
    return _learner


def _register_supermegabot_skills():
    """Register SuperMegaBot-specific skills."""
    learner = _learner

    def cmd_status(*_):
        import subprocess
        try:
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
            procs = result.stdout.count("python")
            return f"📊 *SuperMegaBot Status*\n\nPython Prozesse: {procs}\nLearner aktiv: ✅"
        except Exception:
            return "SuperMegaBot laeuft."

    def cmd_modules(*_):
        core_dir = os.path.join(os.path.dirname(__file__), "modules")
        if not os.path.exists(core_dir):
            return "Keine Module gefunden."
        modules = [f for f in os.listdir(core_dir) if f.endswith(".py")]
        return "📦 *Module*\n\n" + "\n".join(f"  • {m}" for m in modules)

    def cmd_services(*_):
        return (
            "🔧 *SuperMegaBot Services*\n\n"
            "  • Dashboard (Port 8888)\n"
            "  • Browser Extension\n"
            "  • AutoPilot\n"
            "  • Shopify Client\n"
            "  • Trading Bot\n"
            "  • GMC Monitor"
        )

    learner.register_skill("status", cmd_status,
                           desc="Zeigt SuperMegaBot Systemstatus", source="built-in")
    learner.register_skill("modules", cmd_modules,
                           desc="Listet alle geladenen Module", source="built-in")
    learner.register_skill("services", cmd_services,
                           desc="Zeigt verfuegbare Services", source="built-in")


def handle_command(command: str) -> str:
    """Process a Self-Learner command."""
    learner = get_learner()
    return learner.handle_command(command)


def notify(message: str):
    """Send Telegram notification via Self-Learner."""
    learner = get_learner()
    return learner.send_telegram(message)


def register_skill(name: str, handler, desc: str = "", source: str = "learned"):
    """Register a new skill from any module."""
    learner = get_learner()
    return learner.register_skill(name, handler, desc, source)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 self_learner_bridge.py <command>")
        print("Examples:")
        print("  python3 self_learner_bridge.py /skills")
        print("  python3 self_learner_bridge.py /status")
        sys.exit(1)

    cmd = ' '.join(sys.argv[1:])
    print(handle_command(cmd))
