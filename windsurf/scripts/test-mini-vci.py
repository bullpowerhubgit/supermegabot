#!/usr/bin/env python3
"""
MINI-VCI J2534 Test am Dodge Challenger
Versucht Verbindung und sendet ELM327 AT-Befehle
"""

import serial
import time

PORT = "/dev/tty.usbserial-A6007dAe"
BAUD = 38400

print("=" * 65)
print("  MINI-VCI J2534 - VERBINDUNGSTEST")
print("  Port:", PORT)
print("=" * 65)
print()

try:
    ser = serial.Serial(PORT, BAUD, timeout=2)
    print("[OK] Serielle Verbindung geoeffnet")
    print(f"     Baudrate: {BAUD}")
    print()

    # ELM327 ATZ (Reset)
    print("[1] Sende ELM327 Reset (ATZ)...")
    ser.write(b"ATZ\r")
    time.sleep(2)
    r = ser.read(ser.in_waiting or 100)
    print(f"     Antwort: {r.decode('utf-8', errors='replace').strip()}")
    print()

    # AT E0 (Echo off)
    print("[2] Sende AT E0 (Echo off)...")
    ser.write(b"AT E0\r")
    time.sleep(0.5)
    r = ser.read(ser.in_waiting or 100)
    print(f"     Antwort: {r.decode('utf-8', errors='replace').strip()}")
    print()

    # AT I (Version)
    print("[3] Sende AT I (Version)...")
    ser.write(b"AT I\r")
    time.sleep(0.5)
    r = ser.read(ser.in_waiting or 100)
    print(f"     Antwort: {r.decode('utf-8', errors='replace').strip()}")
    print()

    # 0100 (PID support)
    print("[4] Sende 0100 (PID support request)...")
    ser.write(b"0100\r")
    time.sleep(1)
    r = ser.read(ser.in_waiting or 200)
    print(f"     Antwort: {r.decode('utf-8', errors='replace').strip()}")
    print()

    ser.close()
    print("[OK] Verbindung geschlossen")

except serial.SerialException as e:
    print(f"[FEHLER] Seriell: {e}")
except Exception as e:
    print(f"[FEHLER] {e}")

print()
print("=" * 65)
print("ERKLAERUNG:")
print("- ELM327 gibt 'ELM327 v1.5' oder aehnlich zurueck")
print("- J2534 Adapter (MINI-VCI) antwortet meist GAR NICHT")
print("  oder mit eigenem Protokoll (nicht lesbar)")
print("- Falls keine ELM327-Antwort -> Adapter NICHT kompatibel")
print("=" * 65)
print("\nDruecke ENTER zum Beenden")
input()
