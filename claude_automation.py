#!/usr/bin/env python3
"""CLI-Einstieg — delegiert an modules.claude_automation."""
from modules.claude_automation import *  # noqa: F401,F403

if __name__ == "__main__":
    import runpy
    runpy.run_module("modules.claude_automation", run_name="__main__")