#!/usr/bin/env python3
"""CLI-Einstieg — delegiert an modules.claude_automation."""
from modules.claude_automation import (
    ask, classify, extract, is_configured, ping, batch_ordner, MODEL, FAST_MODEL,
)

if __name__ == "__main__":
    import json
    import logging
    logging.basicConfig(level=logging.INFO)
    if not is_configured():
        print("ANTHROPIC_API_KEY fehlt — export ANTHROPIC_API_KEY=sk-ant-...")
        raise SystemExit(1)
    ok, detail = ping()
    print(f"Ping: {'OK' if ok else 'FAIL'} — {detail}")
    if not ok:
        raise SystemExit(1)
    print(ask("Schreibe eine kurze Terminbestätigung per E-Mail."))