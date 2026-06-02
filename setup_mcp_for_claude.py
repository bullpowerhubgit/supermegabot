#!/usr/bin/env python3
"""
Konfiguriert den SuperMegaBot MCP-Server für Claude Desktop und Claude Code.
"""

import json
import os
import sys
from pathlib import Path

SERVER_PATH = Path(__file__).resolve().parent / "mcp_server.py"

# macOS Claude Desktop Config
CLAUDE_DESKTOP_CONFIG = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"

# Claude Code / Windsurf projektspezifisch
PROJECT_MCP = Path(__file__).resolve().parent / ".mcp.json"


def setup_claude_desktop():
    """Trägt den STDIO-MCP-Server in die Claude Desktop Config ein."""
    if not CLAUDE_DESKTOP_CONFIG.parent.exists():
        print("⚠️  Claude Desktop Config-Verzeichnis nicht gefunden.")
        print("   Installiere zuerst Claude Desktop: https://claude.ai/download")
        return False

    config = {"mcpServers": {}}
    if CLAUDE_DESKTOP_CONFIG.exists():
        try:
            with open(CLAUDE_DESKTOP_CONFIG) as f:
                config = json.load(f)
        except json.JSONDecodeError:
            print("⚠️  Bestehende Config war ungültig, starte neu.")

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    config["mcpServers"]["supermegabot"] = {
        "command": sys.executable,
        "args": [str(SERVER_PATH)]
    }

    CLAUDE_DESKTOP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(CLAUDE_DESKTOP_CONFIG, "w") as f:
        json.dump(config, f, indent=2)

    print(f"✅ Claude Desktop Config aktualisiert:")
    print(f"   {CLAUDE_DESKTOP_CONFIG}")
    print(f"   Server: {SERVER_PATH}")
    return True


def print_manual_instructions():
    """Falls automatisches Setup nicht klappt."""
    print("\n📋 Manuelle Konfiguration für Claude Desktop:")
    print("-" * 50)
    print(f'1. Öffne: {CLAUDE_DESKTOP_CONFIG}')
    print("2. Füge Folgendes ein:")
    print(json.dumps({
        "mcpServers": {
            "supermegabot": {
                "command": sys.executable,
                "args": [str(SERVER_PATH)]
            }
        }
    }, indent=2))
    print("-" * 50)
    print("\n3. Claude Desktop neu starten")
    print("4. Im Chat nach 'supermegabot' fragen oder Tools testen:")
    print("   'Was ist der Status meiner Services?'")


if __name__ == "__main__":
    print("🔧 SuperMegaBot MCP → Claude Setup\n")

    if not SERVER_PATH.exists():
        print(f"❌ MCP-Server nicht gefunden: {SERVER_PATH}")
        sys.exit(1)

    ok = setup_claude_desktop()
    if not ok:
        print_manual_instructions()
    else:
        print("\n🚀 Nächster Schritt:")
        print("   1. Claude Desktop neu starten (Cmd+Q, dann neu öffnen)")
        print("   2. In einem Chat prüfen, ob der 🔧-Button erscheint")
        print("   3. Testen mit: 'Zeige mir den Systemstatus'")
