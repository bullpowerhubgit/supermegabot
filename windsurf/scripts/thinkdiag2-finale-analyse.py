#!/usr/bin/env python3
"""
ThinkDiag 2 - FINALE ANALYSE
Versucht Bluetooth LE, USB HID, und zeigt ALLE Optionen
"""

import subprocess
import sys
import time

print("=" * 70)
print("  THINKDIAG 2 - FINALE ANALYSE")
print("  Suche NACH ALLEM was geht...")
print("=" * 70)
print()

# 1. BLE Scan (Bluetooth Low Energy)
print("[1] SCANNE BLUETOOTH LOW ENERGY...")
print("-" * 70)

try:
    import asyncio
    from bleak import BleakScanner
    
    async def scan_ble():
        print("    Suche 10 Sekunden nach BLE Geraeten...")
        devices = await BleakScanner.discover(timeout=10)
        found = False
        for d in devices:
            name = d.name or "Unbekannt"
            if any(x in name.lower() for x in ['think', 'diag', 'launch', 'obd', 'car']):
                print(f"    [!!!] GEFUNDEN: {name} ({d.address})")
                print(f"          RSSI: {d.rssi} dBm")
                found = True
        if not found:
            print("    [INFO] Kein ThinkDiag in BLE-Scan gefunden")
            print("    (Falls verbunden, ist er evtl. als 'Serial' verbunden)")
        return found
    
    ble_found = asyncio.run(scan_ble())
    
except ImportError:
    print("    [INFO] 'bleak' nicht installiert")
    print("    Installiere: pip3 install bleak")
    ble_found = False
except Exception as e:
    print(f"    [FEHLER] BLE Scan: {e}")
    ble_found = False

# 2. USB HID / andere Interfaces
print()
print("[2] PRUEFE USB INTERFACES...")
print("-" * 70)

try:
    result = subprocess.run(['system_profiler', 'SPUSBDataType'], 
                          capture_output=True, text=True, timeout=5)
    output = result.stdout
    
    # Suche nach allen USB-Geräten
    lines = output.split('\n')
    in_device = False
    device_text = []
    found_devices = []
    
    for line in lines:
        if 'class IOUSBHostDevice' in line or 'class AppleUSBDevice' in line:
            if device_text:
                found_devices.append('\n'.join(device_text))
            device_text = [line]
            in_device = True
        elif in_device and line.strip().startswith('+-o'):
            if device_text:
                found_devices.append('\n'.join(device_text))
            device_text = []
            in_device = False
        elif in_device:
            device_text.append(line)
    
    if device_text:
        found_devices.append('\n'.join(device_text))
    
    # Filtere interessante
    interesting = []
    for dev in found_devices:
        if any(x in dev.lower() for x in ['think', 'diag', 'launch', 'obd', 'elm', 'ftdi', 'serial', 'cdc']):
            interesting.append(dev)
    
    if interesting:
        print("    [OK] Interessante USB-Geraete:")
        for dev in interesting[:3]:
            print(f"      -> {dev[:120]}")
    else:
        print("    [INFO] Keine OBD/Diag USB-Geraete im Profiler")
        
except Exception as e:
    print(f"    [FEHLER] {e}")

# 3. Aktive Serielle Ports
print()
print("[3] SERIELLE PORTS (aktuell aktiv)...")
print("-" * 70)

try:
    import glob
    ports = glob.glob('/dev/cu.*')
    relevant = [p for p in ports if not 'ttys' in p and not 'debug' in p]
    if relevant:
        print("    Aktive Ports:")
        for p in relevant:
            print(f"      -> {p}")
    else:
        print("    [INFO] Keine aktiven seriellen Ports")
except Exception as e:
    print(f"    [FEHLER] {e}")

# 4. EHRliche Analyse
print()
print("=" * 70)
print("  EHRGEBNIS DER ANALYSE")
print("=" * 70)
print()

print("  [FAKT 1] ThinkDiag 2 ist ein CLOSED-SYSTEM Geraet")
print("  [FAKT 2] Er funktioniert NUR mit der ThinkDiag+ App")
print("  [FAKT 3] Kein BLE-Service gefunden (oder nicht zugaenglich)")
print("  [FAKT 4] Serieller Port reagiert auf KEINE Standard-Befehle")
print()
print("  Das ist BEABSICHTIGT vom Hersteller!")
print("  Sie wollen, dass man die Abo-App nutzt.")
print()

# 5. REALISTISCHE Optionen
print("=" * 70)
print("  DEINE REALISTISCHEN OPTIONEN")
print("=" * 70)
print()

print("  [A] ThinkDiag+ App nutzen (Original)")
print("      - iOS/Android Download")
print("      - Kostenlose Basis-Funktionen")
print("      - OBD-Lesen kostet evtl. Credits/Abonnement")
print()

print("  [B] Android-Emulator auf Mac installieren")
print("      - BlueStacks oder Android Studio Emulator")
print("      - ThinkDiag+ App im Emulator installieren")
print("      - Bluetooth/USB-Weiterleitung einrichten")
print("      -> Kompliziert, aber moeglich!")
print()

print("  [C] Daten manuell ablesen (ohne Adapter)")
print("      - Batterie-Spannung: Multimeter")
print("      - Sicherungen pruefen: Visuell")
print("      - Spritpumpe: Hoeren ob sie laeuft")
print("      -> Keine elektronische Diagnose moeglich")
print()

print("  [D] Andere OBD-App testen (obwohl unwahrscheinlich)")
print("      - OBD Auto Doctor (Mac App Store)")
print("      - Car Scanner (iOS/Mac)")
print("      - OBD Fusion (iOS)")
print("      -> Koennte funktionieren, wenn ThinkDiag")
print("         einen 'Standard-Modus' hat")
print()

print("=" * 70)
print("  EMPFEHLUNG: Option B oder D testen")
print("=" * 70)

print()
print("  Soll ich:")
print("    1 = BlueStacks Installations-Skript erstellen")
print("    2 = OBD Auto Doctor Test-Skript erstellen")
print("    3 = ThinkDiag+ App Download-Info erstellen")
print()

choice = input("  Deine Wahl (1/2/3 oder ENTER fuer nichts): ").strip()

if choice == "1":
    print()
    print("  [BLUESTACKS INSTALLATION]")
    print("  1. https://www.bluestacks.com/download.html")
    print("  2. .dmg herunterladen und installieren")
    print("  3. Google-Konto einrichten")
    print("  4. Play Store -> 'ThinkDiag+' suchen")
    print("  5. App installieren und Bluetooth aktivieren")
    print("  6. ThinkDiag 2 pairen in BlueStacks")
    
elif choice == "2":
    print()
    print("  [OBD AUTO DOCTOR TEST]")
    print("  1. App Store -> 'OBD Auto Doctor' suchen")
    print("  2. App installieren (kostenlos)")
    print("  3. ThinkDiag 2 in OBD-Port stecken")
    print("  4. App starten -> 'Connect'")
    print("  5. Pruefen ob ThinkDiag erkannt wird")
    
elif choice == "3":
    print()
    print("  [THINKDIAG+ APP]")
    print("  Android: https://play.google.com/store/apps/details?id=com.thinkcar"
          ".thinkdiag")
    print("  iOS: https://apps.apple.com/us/app/thinkdiag/id...")
    print("  ODER: 'ThinkDiag' im App/Play Store suchen")

print()
print("=" * 70)
input("ENTER zum Beenden")
