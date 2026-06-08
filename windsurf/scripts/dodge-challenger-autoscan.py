#!/usr/bin/env python3
"""
Dodge Challenger 2010 V6 - AUTO SCAN
Verbindet automatisch mit ELM327 und liest alle wichtigen Daten aus
"""

import sys
import glob

print("=" * 65)
print("  DODGE CHALLENGER 2010 V6 - AUTO SCAN")
print("  ELM327 Verbindung & Live-Daten")
print("=" * 65)
print()

try:
    import obd
    import serial.tools.list_ports
except ImportError as e:
    print("[FEHLER] python-OBD nicht installiert:", e)
    print("Installiere mit: pip3 install obd pyserial")
    input("\nENTER zum Beenden")
    sys.exit(1)

# 1. Port automatisch finden
print("[1] Suche ELM327 Dongle...")
ports = []
try:
    ports = list(serial.tools.list_ports.comports())
except:
    pass

# Mac-spezifische Ports
mac_ports = glob.glob('/dev/tty.usbserial-*') + glob.glob('/dev/tty.SLAB_USBtoUART*') + glob.glob('/dev/tty.wchusbserial*') + glob.glob('/dev/cu.usbserial-*')

all_ports = [p.device for p in ports] + mac_ports
all_ports = list(set(all_ports))  # Duplikate entfernen

if not all_ports:
    print("    [FEHLER] Kein ELM327 Dongle gefunden!")
    print("    Schliesse USB-Dongle an oder paire Bluetooth/WiFi Adapter")
    print()
    print("    Empfohlene Ports pruefen:")
    for p in ['/dev/tty.usbserial-*', '/dev/cu.usbserial-*', '/dev/tty.SLAB_USBtoUART']:
        print(f"      {p}")
    input("\nENTER zum Beenden")
    sys.exit(1)

print(f"    Gefundene Ports: {len(all_ports)}")
for p in all_ports:
    print(f"      -> {p}")
print()

# 2. Verbindung herstellen
connection = None
for port in all_ports:
    print(f"[2] Versuche Verbindung mit {port}...")
    try:
        connection = obd.OBD(port, baudrate=38400, fast=False)
        if connection.is_connected():
            print(f"    [OK] Verbunden mit {port}!")
            print(f"    Protokoll: {connection.protocol_name()}")
            break
    except Exception as e:
        print(f"    [FEHL] {str(e)[:50]}")
        continue

if not connection or not connection.is_connected():
    print("\n[FEHLER] Konnte keine Verbindung herstellen!")
    print("Pruefe:")
    print("  - ELM327 ist eingesteckt im OBD2-Port (unterm Lenkrad)")
    print("  - Zündung ist auf ON (nicht unbedingt Motor laufen)")
    print("  - Dongle ist korrekt angeschlossen/paired")
    input("\nENTER zum Beenden")
    sys.exit(1)

print()

# 3. Live-Daten auslesen
print("[3] LIVE-DATEN AUSLESEN")
print("-" * 65)

cmds = [
    (obd.commands.RPM, "Drehzahl (RPM)"),
    (obd.commands.SPEED, "Geschwindigkeit"),
    (obd.commands.COOLANT_TEMP, "Kuehlmitteltemperatur"),
    (obd.commands.INTAKE_TEMP, "Ansauglufttemperatur"),
    (obd.commands.MAF, "Luftmassenmesser (MAF)"),
    (obd.commands.THROTTLE_POS, "Drosselklappenstellung"),
    (obd.commands.ENGINE_LOAD, "Motorlast"),
    (obd.commands.FUEL_LEVEL, "Tankfuellstand"),
    (obd.commands.BAROMETRIC_PRESSURE, "Luftdruck"),
    (obd.commands.OIL_TEMP, "Oeltemperatur"),
]

for cmd, name in cmds:
    try:
        response = connection.query(cmd)
        if response.is_null():
            print(f"    {name:30s}: --- (nicht unterstuetzt)")
        else:
            val = response.value
            if hasattr(val, 'magnitude'):
                unit = str(val.units) if hasattr(val, 'units') else ''
                print(f"    {name:30s}: {val.magnitude:.1f} {unit}")
            else:
                print(f"    {name:30s}: {val}")
    except Exception as e:
        print(f"    {name:30s}: [FEHLER] {str(e)[:30]}")

print()

# 4. Fehlercodes auslesen
print("[4] FEHLERCODES (DTC)")
print("-" * 65)

try:
    dtc_response = connection.query(obd.commands.GET_DTC)
    if dtc_response and dtc_response.value:
        print(f"    Gefundene Codes: {len(dtc_response.value)}")
        for code, desc in dtc_response.value:
            print(f"    -> {code}: {desc}")
            # Dodge-spezifische Hinweise
            if code in ['P1004', 'P1005', 'P1006', 'P1007']:
                print(f"       [!] Short Runner Valve - typisch fuer 3.5L V6!")
            elif code in ['P0300', 'P0301', 'P0302', 'P0303', 'P0304', 'P0305', 'P0306']:
                print(f"       [!] Zuendspule/Kerze pruefen - haeufige Ursache!")
            elif code in ['P0335', 'P0339']:
                print(f"       [!] Kurbelwellensensor defekt - Motor springt nicht an!")
            elif code in ['U110C', 'U1110', 'U1411', 'U1412']:
                print(f"       [!] Chrysler/Dodge Netzwerk-Code")
    else:
        print("    [OK] Keine Fehlercodes gespeichert!")
except Exception as e:
    print(f"    [FEHLER] DTC auslesen fehlgeschlagen: {e}")

print()

# 5. VIN auslesen
print("[5] FAHRZEUG-IDENTIFIKATION (VIN)")
print("-" * 65)
try:
    vin_response = connection.query(obd.commands.VIN_NUMBER)
    if vin_response and not vin_response.is_null():
        vin = str(vin_response.value)
        print(f"    VIN: {vin}")
        try:
            from vininfo import Vin
            v = Vin(vin)
            print(f"    Hersteller: {v.manufacturer}")
            print(f"    Jahr: {v.years}")
        except:
            pass
    else:
        print("    [INFO] VIN nicht verfuegbar")
except Exception as e:
    print(f"    [INFO] VIN nicht verfuegbar: {e}")

print()
print("=" * 65)
print("  AUTO SCAN ABGESCHLOSSEN")
print("  Verbindung wird geschlossen...")
print("=" * 65)

connection.close()

print("\nDruecke ENTER zum Beenden")
input()
