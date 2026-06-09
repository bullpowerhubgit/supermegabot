#!/usr/bin/env python3
"""
Self-Learner Bridge for SuperMegaBot
Integrates the shared Self-Learner core into SuperMegaBot.
"""

import sys
import os
import logging

log = logging.getLogger("SelfLearnerBridge")

sys.path.insert(0, os.path.expanduser("~"))

try:
    from self_learner_core import SelfLearner
    _HAS_LEARNER = True
except ImportError:
    _HAS_LEARNER = False
    log.warning("self_learner_core nicht verfügbar — Bridge im Stub-Modus")


class _StubLearner:
    """Fallback wenn self_learner_core nicht installiert ist."""
    def load_learned_skills(self): pass
    def register_skill(self, *a, **kw): pass
    def handle_command(self, cmd: str) -> str:
        return f"ℹ️ Self-Learner nicht verfügbar (self_learner_core fehlt). Befehl: {cmd}"
    def send_telegram(self, msg: str) -> None: pass


_learner = None


def get_learner():
    global _learner
    if _learner is None:
        if _HAS_LEARNER:
            _learner = SelfLearner("supermegabot", telegram_notify=True)
            _learner.load_learned_skills()
            _register_supermegabot_skills()
        else:
            _learner = _StubLearner()
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
