#!/usr/bin/env python3
"""
Dodge Challenger 2010 V6 (3.5L EGJ/EGT) - Open Source Diagnose Tool
Mac-kompatibel, benoetigt ELM327 Dongle
"""

import sys

print("=" * 65)
print("  DODGE CHALLENGER 2010 V6 - KFZ DIAGNOSE")
print("  Open Source Tool - Mac kompatibel")
print("=" * 65)

# 1. VIN Decoder
print("\n[1] VIN-DECODER")
print("-" * 65)
try:
    from vininfo import Vin
    print("    VIN Beispiel: 2B3CJ4DV5AH123456")
    vin = Vin("2B3CJ4DV5AH123456")
    print(f"    Hersteller:    {vin.manufacturer}")
    print(f"    Jahr:          {vin.years}")
    print(f"    Region:        {vin.region}")
    print(f"    WMI:           {vin.wmi}")
    print("    [INFO] Dodge VINs beginnen mit '1B3', '2B3', '3B3'")
except Exception as e:
    print(f"    [INFO] vininfo installiert: {e}")

# 2. DTC-Fehlercodes
print("\n[2] DTC-FEHLERCODES (Dodge/Chrysler spezifisch)")
print("-" * 65)

dtc_codes = {
    "P0300": "Random/Multiple Cylinder Misfire Detected",
    "P0301": "Cylinder 1 Misfire Detected",
    "P0302": "Cylinder 2 Misfire Detected", 
    "P0303": "Cylinder 3 Misfire Detected",
    "P0304": "Cylinder 4 Misfire Detected",
    "P0305": "Cylinder 5 Misfire Detected",
    "P0306": "Cylinder 6 Misfire Detected",
    "P0420": "Catalyst System Efficiency Below Threshold (Bank 1)",
    "P0432": "Main Catalyst Efficiency Below Threshold (Bank 2)",
    "P0456": "Evaporative Emission System Small Leak Detected",
    "P0457": "Evaporative Emission System Leak Detected (Fuel Cap)",
    "P0700": "Transmission Control System (MIL Request)",
    "P0731": "Gear 1 Incorrect Ratio",
    "P0732": "Gear 2 Incorrect Ratio",
    "P0733": "Gear 3 Incorrect Ratio",
    "P0868": "Line Pressure Low",
    "P0882": "TCM Power Input Signal Low",
    "P0884": "TCM Power Input Signal Intermittent",
    "P1004": "Short Runner Valve Control Performance (3.5L V6!)",
    "P1005": "Short Runner Valve Control Circuit (3.5L V6!)",
    "P1006": "Short Runner Valve Control Circuit Low",
    "P1007": "Short Runner Valve Control Circuit High",
    "P1521": "Incorrect Engine Oil Type",
    "P2004": "Intake Manifold Runner Control Stuck Open (Bank 1)",
    "P2008": "Intake Manifold Runner Control Circuit Open (Bank 1)",
    "P2017": "Intake Manifold Runner Position Sensor Circuit High",
    "P2122": "Throttle/Pedal Position Sensor/Switch D Circuit Low",
    "P2127": "Throttle/Pedal Position Sensor/Switch E Circuit Low",
    "P2138": "Throttle/Pedal Position Sensor/Switch D/E Voltage Correlation",
    "B1502": "Fuel Level Sensor Circuit Low",
    "B1503": "Fuel Level Sensor Circuit High",
    "C121C": "Torque Request Signal Denied",
    "C2200": "Steering Angle Sensor Internal",
    "U0100": "Lost Communication With ECM/PCM",
    "U0101": "Lost Communication With TCM",
    "U0140": "Lost Communication With Body Control Module (BCM)",
    "U110C": "Lost Fuel Level Message (Chrysler/Dodge spezifisch!)",
    "U1110": "Lost Vehicle Speed Message",
    "U1411": "Implausible Fuel Volume Signal Received",
    "U1412": "Implausible Vehicle Speed Signal",
}

print(f"    Dodge/Chrysler DTC Datenbank: {len(dtc_codes)} Codes geladen")
print("\n    HAUFFIGE CODES Challenger 3.5L V6:")
for code, desc in list(dtc_codes.items())[:8]:
    print(f"      {code}: {desc}")

# 3. Spezifische PIDs fuer 3.5L V6
print("\n[3] DODGE CHALLENGER 3.5L V6 SPEZIFISCHE PIDs")
print("-" * 65)

dodge_pids = {
    "010C": ("Engine RPM", "U/min", "Drehzahl"),
    "010D": ("Vehicle Speed", "km/h", "Geschwindigkeit"),
    "0105": ("Engine Coolant Temp", "°C", "Kuehlmitteltemperatur"),
    "0104": ("Calculated Load Value", "%", "Motorauslastung"),
    "010B": ("Intake Manifold Pressure", "kPa", "Ansaugdruck"),
    "010F": ("Intake Air Temperature", "°C", "Ansauglufttemperatur"),
    "0110": ("MAF Air Flow Rate", "g/s", "Luftmassenmesser"),
    "0111": ("Throttle Position", "%", "Drosselklappenstellung"),
    "011C": ("OBD Standards", "-", "OBD Norm"),
    "012F": ("Fuel Level Input", "%", "Tankfuellstand"),
    "0133": ("Barometric Pressure", "kPa", "Luftdruck"),
    "014E": ("Commanded Throttle Actuator", "%", "Drosselklappe Sollwert"),
    "21":   ("Distance with MIL", "km", "Strecke mit Fehlerlampe"),
    "015C": ("Engine Oil Temperature", "°C", "Oeltemperatur (3.5L!)"),
}

print(f"    Spezifische PIDs: {len(dodge_pids)}")
for pid, (name, unit, german) in list(dodge_pids.items())[:6]:
    print(f"      PID {pid}: {name} ({german}) [{unit}]")

# 4. python-OBD Verbindung
print("\n[4] python-OBD VERBINDUNG")
print("-" * 65)
try:
    import obd
    print("    [OK] python-OBD geladen")
    print("    Verfuegbare Verbindungen:")
    print("      - Bluetooth: obd.OBD('/dev/rfcomm0')")
    print("      - USB/WiFi: obd.OBD('/dev/ttyUSB0')")
    print("      - Mac USB: obd.OBD('/dev/tty.usbserial-*')")
    print("\n    Beispiel-Code fuer Challenger:")
    print("      connection = obd.OBD()")
    print("      cmd = obd.commands.RPM")
    print("      response = connection.query(cmd)")
    print("      print(response.value)")
except ImportError:
    print("    [FEHLER] python-OBD nicht installiert")

# 5. Challenger-spezifische Infos
print("\n[5] DODGE CHALLENGER 2010 3.5L V6 TECHNISCHE DATEN")
print("-" * 65)
print("    Motor:        Chrysler EGJ/EGT 3.5L V6 SOHC")
print("    Leistung:     250 PS / 184 kW bei 6400 U/min")
print("    Drehmoment:   339 Nm bei 3800 U/min")
print("    OBD Protokoll: CAN 11-bit (500 kbaud)")
print("    Bus-Systeme:  CAN-C (High Speed) + CAN-B (Low Speed)")
print("    PCM:          NGC3 (Next Generation Controller)")
print("    Getriebe:     W5A580 5-Gang Automatik / TR-6060 6-Gang")
print("    Oelsorte:     5W-20 (Chrysler MS-6395)")
print("    Oelmenge:     5.7 Liter (mit Filter)")

# 6. Empfohlene ELM327 Adapter
print("\n[6] EMPFOHLENE ELM327 ADAPTER fuer Mac")
print("-" * 65)
print("    [USB] OBDLink SX / MX - sehr zuverlaessig")
print("    [USB] ELM327 USB mit FTDI Chip")
print("    [BT]  OBDLink LX (Bluetooth Low Energy)")
print("    [WiFi] Veepeak WiFi OBD2 (kein Bluetooth noetig)")
print("    [INFO] Vermeide billige China-Klone mit PIC18F25K80")

# 7. Wartungsintervalle
print("\n[7] WARTUNGSINTERVALLE Challenger 3.5L")
print("-" * 65)
print("    Oelwechsel:       8.000 km / 6 Monate")
print("    Luftfilter:       24.000 km")
print("    Zuendkerzen:      48.000 km (Copper) / 160.000 km (Iridium)")
print("    Getriebeoel:      80.000 km (Automatik)")
print("    Kuehlmittel:      5 Jahre / 240.000 km")
print("    Zahnriemen:       Kette - kein Wechsel noetig!")

print("\n" + "=" * 65)
print("  BEREIT fuer Dodge Challenger 2010 Diagnose!")
print("  Verbinde ELM327 und starte python-OBD oder obd-node")
print("=" * 65)

print("\nDruecke ENTER zum Beenden")
input()
