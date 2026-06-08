#!/usr/bin/env python3
"""
Dodge Challenger 2010 V6 - Verbindungs-Test
Prueft alle moeglichen Wege zum ELM327 Dongle
"""

import sys
import glob
import subprocess

print("=" * 65)
print("  DODGE CHALLENGER 2010 V6 - VERBINDUNGS-TEST")
print("=" * 65)
print()

# 1. USB-Ports pruefen
print("[1] USB SERIAL PORTS")
print("-" * 65)

usb_patterns = [
    '/dev/tty.usbserial*',
    '/dev/cu.usbserial*',
    '/dev/tty.SLAB_USBtoUART*',
    '/dev/cu.SLAB_USBtoUART*',
    '/dev/tty.wchusbserial*',
    '/dev/cu.wchusbserial*',
    '/dev/tty.usbmodem*',
    '/dev/cu.usbmodem*',
]

found_ports = []
for pattern in usb_patterns:
    ports = glob.glob(pattern)
    found_ports.extend(ports)

if found_ports:
    print("    [OK] Gefunden:")
    for p in found_ports:
        print(f"      -> {p}")
else:
    print("    [FEHLER] Keine USB-Serial Ports gefunden!")
    print()
    print("    Moegliche Ursachen:")
    print("      - Dongle nicht am Mac angeschlossen")
    print("      - Dongle im Auto OBD2-Port, nicht am Mac")
    print("      - Treiber fehlt (FTDI/CH340/CP210x)")
    print("      - Billiger China-Klon ohne Mac-Treiber")
    print()
    print("    Loesungen:")
    print("      - FTDI Treiber: https://ftdichip.com/drivers/")
    print("      - CH340 Treiber: brew install --cask wch-ch34x-usb-serial-driver")
    print("      - CP210x Treiber: https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers")

print()

# 2. Bluetooth pruefen
print("[2] BLUETOOTH GERAETE")
print("-" * 65)

try:
    result = subprocess.run(['system_profiler', 'SPBluetoothDataType'], 
                          capture_output=True, text=True, timeout=10)
    bt_output = result.stdout
    # Suche nach OBD/ELM Geraeten
    lines = bt_output.split('\n')
    found_bt = False
    for line in lines:
        if any(x in line.lower() for x in ['obd', 'elm', 'car', 'scan']):
            print(f"    [OK] Gefunden: {line.strip()}")
            found_bt = True
    if not found_bt:
        print("    [INFO] Keine OBD Bluetooth-Geraete gefunden")
        print("    Tip: OBDLink LX oder Veepeak Bluetooth pairen")
except Exception as e:
    print(f"    [INFO] Bluetooth-Check nicht moeglich: {e}")

print()

# 3. WiFi Netzwerke pruefen
print("[3] WIFI NETZWERKE")
print("-" * 65)

try:
    result = subprocess.run(['/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport', '-s'], 
                          capture_output=True, text=True, timeout=10)
    wifi_output = result.stdout
    found_wifi = False
    for line in wifi_output.split('\n'):
        if any(x in line.lower() for x in ['obd', 'elm', 'car', 'wifi', 'veepeak', 'vgate']):
            print(f"    [OK] Gefunden: {line.strip()}")
            found_wifi = True
    if not found_wifi:
        print("    [INFO] Keine OBD WiFi-Netzwerke gefunden")
        print("    Tip: WiFi-Dongle muss Strom haben (im Auto + Zündung ON)")
except Exception as e:
    print(f"    [INFO] WiFi-Check nicht moeglich: {e}")

print()

# 4. python-OBD Verbindungstest
print("[4] PYTHON-OBD VERBINDUNGSTEST")
print("-" * 65)

try:
    import obd
    print("    [OK] python-OBD Modul geladen")
    print()
    
    # Teste alle gefundenen Ports
    if found_ports:
        for port in found_ports:
            print(f"    Teste {port}...")
            try:
                conn = obd.OBD(port, baudrate=38400, fast=False, timeout=5)
                if conn.is_connected():
                    print(f"      [OK] VERBUNDEN! Protokoll: {conn.protocol_name()}")
                    # Versuche RPM zu lesen
                    rpm = conn.query(obd.commands.RPM)
                    if not rpm.is_null():
                        print(f"      [OK] RPM gelesen: {rpm.value}")
                    else:
                        print(f"      [INFO] Verbindung OK, aber kein RPM (Zündung AUS?)")
                    conn.close()
                    break
                else:
                    print(f"      [FEHL] Verbindung nicht moeglich")
                conn.close()
            except Exception as e:
                print(f"      [FEHL] {str(e)[:50]}")
    else:
        print("    [INFO] Keine Ports zum Testen verfuegbar")
        print("    Versuche automatische Suche (obd.OBD())...")
        try:
            conn = obd.OBD(fast=False, timeout=5)
            if conn.is_connected():
                print(f"    [OK] Automatisch verbunden! Protokoll: {conn.protocol_name()}")
                conn.close()
            else:
                print("    [FEHL] Automatische Suche fehlgeschlagen")
        except Exception as e:
            print(f"    [FEHL] {str(e)[:60]}")
except ImportError:
    print("    [FEHL] python-OBD nicht installiert")
    print("    Installiere: pip3 install obd pyserial")

print()

# 5. Zusammenfassung
print("=" * 65)
print("  ZUSAMMENFASSUNG")
print("=" * 65)
print()
print("  Schritt-fuer-Schritt zum Verbinden:")
print()
print("  1. Dongle in OBD2-Port des Challengers stecken")
print("     (unter dem Lenkrad, linker Fussraum)")
print()
print("  2. Zündung auf ON (nicht starten!)")
print("     -> Dashboard leuchtet auf")
print()
print("  3. Je nach Dongle-Typ:")
print()
print("     USB-Kabel:")
print("       -> Kabel vom Dongle in Mac USB stecken")
print("       -> Treiber pruefen (siehe oben)")
print("       -> Port sollte als /dev/tty.usbserial* erscheinen")
print()
print("     Bluetooth:")
print("       -> Dongle muss gepaart sein (System Preferences)")
print("       -> Geraetename oft 'OBDLink', 'Veepeak', 'ELM327'")
print("       -> python-OBD findet es automatisch")
print()
print("     WiFi:")
print("       -> Dongle erstellt eigenes WLAN (z.B. 'Veepeak')")
print("       -> Mac mit diesem WLAN verbinden")
print("       -> IP meist 192.168.0.10:35000")
print()
print("  4. Auto-Scan starten:")
print("     Doppelklick auf Desktop/OBD-Tools/10-dodge-autoscan.app")
print()
print("=" * 65)

print("\nDruecke ENTER zum Beenden")
input()
