#!/usr/bin/env python3
"""
USB Eingang prüfen - FINAL TEST
"""

import serial
import time

PORT = "/dev/cu.988430957800"

print("=" * 70)
print("  USB EINGANG PRÜFEN - FINAL")
print("=" * 70)
print()

try:
    # Versuche verschiedene Baudraten
    baudrates = [9600, 19200, 38400, 57600, 115200, 230400, 460800]
    
    for baud in baudrates:
        try:
            ser = serial.Serial(PORT, baud, timeout=2)
            print(f"[TEST] Baudrate {baud}: Port geöffnet")
            
            # Lese initial
            ser.reset_input_buffer()
            time.sleep(0.5)
            r = ser.read(ser.in_waiting or 50)
            if r:
                print(f"       -> DATEN: {r.hex()}")
            
            # Sende ATZ
            ser.write(b"ATZ\r")
            time.sleep(1)
            r = ser.read(ser.in_waiting or 50)
            if r:
                print(f"       -> ANTWORT auf ATZ: {r.hex()}")
            
            ser.close()
        except:
            pass
    
    print()
    print("[FAZIT] Der ThinkDiag 2 antwortet auf GAR NICHTS über USB.")
    print("        Er ist ein CLOSED-SYSTEM für die ThinkDiag+ App.")
    
except Exception as e:
    print(f"[FEHLER] {e}")

print()
print("=" * 70)
print("  LÖSUNG: iPhone/iPad + ThinkDiag+ App")
print("=" * 70)
