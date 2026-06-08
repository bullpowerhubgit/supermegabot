#!/usr/bin/env python3
"""
OBD-II Python Tools Demo
Zeigt alle installierten Open-Source OBD-Tools fuer KFZ.
"""

import sys

print("=" * 56)
print("  OBD-II KFZ TOOLS - PYTHON")
print("=" * 56)

# 1. python-OBD
print("\n[1] python-OBD (obd v0.7.3)")
print("    GitHub: brendan-w/python-OBD")
print("    Lizenz: GPL")
try:
    import obd
    print("    [OK] Modul geladen")
    print("    Verfuegbare OBD-Befehle:")
    cmds = [obd.commands.RPM, obd.commands.SPEED, obd.commands.COOLANT_TEMP,
            obd.commands.MAF, obd.commands.THROTTLE_POS, obd.commands.FUEL_LEVEL]
    for c in cmds:
        print(f"      - {c.name}: PID {c.pid}")
except ImportError as e:
    print(f"    [FEHLER] {e}")

# 2. pyserial
print("\n[2] pySerial v3.5")
print("    Serielle Kommunikation mit ELM327")
try:
    import serial
    print("    [OK] Modul geladen")
except ImportError:
    print("    [FEHLER] Nicht installiert")

# 3. Pint (Einheitenkonvertierung)
print("\n[3] Pint v0.24.4")
print("    Physikalische Einheiten fuer OBD-Daten")
try:
    import pint
    print("    [OK] Modul geladen")
except ImportError:
    print("    [FEHLER] Nicht installiert")

# Demo: VIN-Decoder simulieren
print("\n" + "-" * 56)
print("DEMO: OBD-II Befehlsliste (python-OBD)")
print("-" * 56)
try:
    import obd
    all_cmds = [c for c in dir(obd.commands) if not c.startswith('_')]
    print(f"Verfuegbare Befehle: {len(all_cmds)}")
    sample = [obd.commands.RPM, obd.commands.SPEED, obd.commands.INTAKE_TEMP,
              obd.commands.FUEL_RATE, obd.commands.ENGINE_LOAD]
    for cmd in sample:
        print(f"  PID {cmd.pid}: {cmd.name} ({cmd.desc})")
except Exception as e:
    print(f"Fehler: {e}")

print("\n" + "=" * 56)
print("Druecke ENTER zum Beenden")
print("=" * 56)
input()
