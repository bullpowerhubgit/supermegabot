#!/usr/bin/env python3
"""
MINI-VCI J2534 -> Raw CAN Wrapper fuer Dodge Challenger 2010
Versucht verschiedene Protokolle auf der seriellen Schnittstelle
"""

import serial
import time
import struct

PORT = "/dev/tty.usbserial-A6007dAe"
BAUDS = [38400, 115200, 9600, 57600, 500000]

print("=" * 65)
print("  MINI-VCI -> RAW CAN WRAPPER")
print("  Dodge Challenger 2010 V6 kompatibel machen")
print("=" * 65)
print()

# 1. Serielle Verbindung testen
print("[1] Serielle Ports pruefen...")

ser = None
for baud in BAUDS:
    try:
        ser = serial.Serial(PORT, baud, timeout=2)
        print(f"    [OK] Port geoeffnet bei {baud} baud")
        break
    except Exception as e:
        print(f"    [FEHL] {baud} baud: {e}")
        continue

if not ser:
    print("\n[FEHLER] Keine serielle Verbindung moeglich!")
    input("ENTER zum Beenden")
    exit(1)

# 2. Versuche verschiedene Init-Sequenzen
print()
print("[2] Teste Init-Sequenzen...")
print("-" * 65)

init_tests = [
    ("ELM327 Reset (ATZ)", b"ATZ\r", b"ELM"),
    ("ELM327 Echo Off", b"ATE0\r", b"OK"),
    ("SLCAN Open (can0)", b"O\r", b"z"),
    ("SLCAN Speed 500k (S6)", b"S6\r", b"\r"),
    ("J2534 raw ping", b"\x00\x00\x00\x00", None),
    ("FTDI direct", b"\x00\x00\x00\x00\x00", None),
]

working_mode = None
for name, cmd, expected in init_tests:
    print(f"    Teste: {name}...")
    ser.reset_input_buffer()
    ser.write(cmd)
    time.sleep(0.5)
    r = ser.read(ser.in_waiting or 50)
    r_str = r.decode('utf-8', errors='replace').strip()
    r_hex = r.hex()[:60]
    
    if expected and expected in r:
        print(f"      [OK] Antwort: {r_str[:50]}")
        working_mode = name
        break
    elif len(r) > 0:
        print(f"      [DATA] Hex: {r_hex}")
    else:
        print(f"      [NO RESP] Keine Antwort")

if not working_mode:
    print()
    print("=" * 65)
    print("  [FEHLER] Kein kompatibles Protokoll gefunden!")
    print()
    print("  Der MINI-VCI spricht ein proprietäres Protokoll")
    print("  (J2534 PassThru Binary), das auf Mac nicht")
    print("  ohne Windows-Treiber funktioniert.")
    print()
    print("  Loesungsmoeglichkeiten:")
    print("  -----------------------")
    print("  A) ELM327 Adapter kaufen (~15-50€)")
    print("     -> Sofort kompatibel mit allen Tools")
    print("  B) Windows-PC/VM + Techstream verwenden")
    print("     -> Original Software fuer MINI-VCI")
    print("  C) Alternative Firmware flashen (riskant!)")
    print("     -> z.B. canable/candleLight firmware")
    print("=" * 65)
    ser.close()
    input("\nENTER zum Beenden")
    exit(1)

# 3. Falls ELM327-Modus gefunden
if "ELM327" in working_mode:
    print()
    print("[3] ELM327 Modus erkannt! Teste OBD-II...")
    
    # Setze CAN Protokoll
    ser.write(b"ATSP6\r")  # ISO 15765-4 CAN (11-bit, 500 kbit/s)
    time.sleep(0.3)
    ser.read(ser.in_waiting)
    
    # Sende RPM Request
    ser.write(b"010C\r")
    time.sleep(1)
    r = ser.read(ser.in_waiting or 100)
    r_str = r.decode('utf-8', errors='replace').strip()
    print(f"    RPM Antwort: {r_str}")
    
    if "41 0C" in r_str or "410C" in r_str:
        print("    [OK] OBD-II Kommunikation funktioniert!")
    else:
        print("    [INFO] Keine RPM Antwort (Zündung pruefen)")

# 4. Falls SLCAN Modus gefunden
elif "SLCAN" in working_mode:
    print()
    print("[3] SLCAN Modus erkannt! Teste CAN...")
    
    # OBD-II CAN Request: ID 0x7DF, Data 02 01 0C
    can_frame = "t7DF802010C\r"
    ser.write(can_frame.encode())
    time.sleep(0.5)
    r = ser.read(ser.in_waiting or 100)
    r_str = r.decode('utf-8', errors='replace').strip()
    print(f"    CAN Antwort: {r_str}")

# 5. Aufraeumen
print()
print("[4] Schliesse Verbindung...")
ser.close()
print("    [OK] Verbindung geschlossen")

print()
print("=" * 65)
print("  TEST ABGESCHLOSSEN")
print("=" * 65)
input("\nENTER zum Beenden")
