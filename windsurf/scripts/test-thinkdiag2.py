#!/usr/bin/env python3
"""
ThinkDiag 2 - Verbindungs-Test
Suche Bluetooth und versuche Verbindung
"""

import subprocess
import sys

print("=" * 65)
print("  THINKDIAG 2 - VERBINDUNGS-TEST")
print("=" * 65)
print()

# 1. Bluetooth Geraete suchen
print("[1] Suche Bluetooth Geraete...")
print("-" * 65)

try:
    result = subprocess.run(
        ['system_profiler', 'SPBluetoothDataType'],
        capture_output=True, text=True, timeout=10
    )
    bt_output = result.stdout
    
    # Suche nach ThinkDiag, OBD, oder aehnlichen Namen
    lines = bt_output.split('\n')
    found_devices = []
    for i, line in enumerate(lines):
        if any(x in line.lower() for x in ['think', 'diag', 'obd', 'elm', 'car', 'scan']):
            found_devices.append(line.strip())
            # Auch die naechsten Zeilen zeigen (Adresse etc.)
            for j in range(i+1, min(i+5, len(lines))):
                if lines[j].strip().startswith('Address') or lines[j].strip().startswith('Connected'):
                    found_devices.append("    " + lines[j].strip())
    
    if found_devices:
        print("    [OK] Moegliche Geraete gefunden:")
        for d in found_devices:
            print(f"      {d}")
    else:
        print("    [INFO] Keine ThinkDiag/OBD Geraete in Bluetooth-Liste")
        print()
        print("    Pruefe:")
        print("      1. Ist ThinkDiag 2 eingeschaltet?")
        print("      2. Blinkt die LED? (Pairing-Modus)")
        print("      3. Ist er bereits mit dem Mac gepaart?")
        
except Exception as e:
    print(f"    [FEHLER] Bluetooth-Check: {e}")

print()

# 2. RFCOMM / Serial Ports pruefen
print("[2] Pruefe serielle Ports...")
print("-" * 65)

import glob
bt_ports = glob.glob('/dev/tty.*') + glob.glob('/dev/cu.*')
obd_ports = [p for p in bt_ports if any(x in p.lower() for x in ['think', 'diag', 'obd', 'elm', 'car'])]

if obd_ports:
    print("    [OK] Gefunden:")
    for p in obd_ports:
        print(f"      -> {p}")
else:
    print("    [INFO] Keine OBD-spezifischen Ports")
    print("    Alle seriellen Ports:")
    for p in bt_ports[:10]:
        if 'bluetooth' in p.lower() or 'usb' in p.lower():
            print(f"      -> {p}")

print()

# 3. python-OBD Test
print("[3] Teste python-OBD Verbindung...")
print("-" * 65)

try:
    import obd
    print("    [OK] python-OBD geladen")
    
    # Versuche automatische Verbindung
    print("    Versuche: obd.OBD()...")
    try:
        connection = obd.OBD()
        if connection.is_connected():
            print(f"    [OK] VERBUNDEN! Protokoll: {connection.protocol_name()}")
            
            # Teste RPM
            print()
            print("    [4] Lese RPM...")
            response = connection.query(obd.commands.RPM)
            if not response.is_null():
                print(f"    [OK] RPM: {response.value}")
            else:
                print("    [INFO] Keine RPM (Zündung AUS?)")
            
            # Teste Fehlercodes
            print()
            print("    [5] Lese Fehlercodes...")
            dtc = connection.query(obd.commands.GET_DTC)
            if dtc and dtc.value:
                print(f"    [INFO] {len(dtc.value)} Codes gefunden")
                for code, desc in dtc.value:
                    print(f"      -> {code}: {desc}")
            else:
                print("    [OK] Keine Fehlercodes")
            
            connection.close()
        else:
            print("    [FEHL] Automatisch nicht verbunden")
    except Exception as e:
        print(f"    [FEHL] {str(e)[:60]}")
        print()
        print("    Moegliche Gruende:")
        print("      - ThinkDiag 2 ist nicht gepaart")
        print("      - Zündung ist AUS")
        print("      - Dongle ist ausser Reichweite")
        
except ImportError:
    print("    [FEHLER] python-OBD nicht installiert")

print()
print("=" * 65)
print("  ANLEITUNG THINKDIAG 2")
print("=" * 65)
print()
print("  1. ThinkDiag 2 in OBD2-Port stecken (im Auto)")
print("  2. Zündung auf ON (nicht starten)")
print("  3. Auf Mac: System Preferences -> Bluetooth")
print("  4. ThinkDiag 2 pairen (Name: 'ThinkDiag' oder 'TD2')")
print("  5. Doppelklick auf '10-dodge-autoscan.app'")
print()
print("  Alternativ: python-OBD automatisch suchen lassen:")
print("    connection = obd.OBD()  # Sucht alle Ports")
print("=" * 65)

print("\nENTER zum Beenden")
input()
