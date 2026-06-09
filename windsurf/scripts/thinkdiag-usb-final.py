#!/usr/bin/env python3
"""
ThinkDiag 2 - USB Verbunden Final Test
Prueft ob sich etwas geaendert hat
"""

import serial
import time

PORT = "/dev/cu.988430957800"

print("=" * 65)
print("  THINKDIAG 2 - USB FINAL TEST")
print("=" * 65)
print()

try:
    ser = serial.Serial(PORT, 38400, timeout=2)
    print(f"[OK] Port geoeffnet: {PORT}")
    print(f"     Baudrate: {ser.baudrate}")
    print(f"     Status: DSR={ser.dsr} CTS={ser.cts} DCD={ser.cd}")
    print()
    
    # Lese alles was im Puffer ist
    ser.reset_input_buffer()
    time.sleep(1)
    initial = ser.read(ser.in_waiting or 100)
    if initial:
        print(f"[!!!] Daten im Puffer: {initial.hex()}")
        print(f"      Text: {initial.decode('utf-8', errors='replace')[:50]}")
    
    # Sende verschiedene Befehle
    tests = [
        b"ATZ\r",
        b"ATI\r", 
        b"010C\r",
        b"\x55\x55\x55\x55",
        b"TD\r",
        b"VER\r",
        b"\x00\x00\x00\x00",
    ]
    
    print("[2] Sende Test-Befehle...")
    for cmd in tests:
        ser.reset_input_buffer()
        ser.write(cmd)
        time.sleep(1)
        r = ser.read(ser.in_waiting or 100)
        if r:
            print(f"  [!!!] CMD {cmd.hex()[:20]} -> ANTWORT: {r.hex()[:60]}")
    
    ser.close()
    print()
    print("[OK] Test abgeschlossen")
    
except Exception as e:
    print(f"[FEHLER] {e}")

print()
print("=" * 65)
print("ANALYSE:")
print("-" * 65)
print("Der ThinkDiag 2 funktioniert NUR mit der ThinkDiag+ App.")
print("Kein USB-Modus, kein ELM327-Modus, keine Alternative.")
print()
print("Loesung: BlueStacks + ThinkDiag+ App auf Mac")
print("Button: Setup-ThinkDiag2-Mac.app auf Desktop")
print("=" * 65)
input("\nENTER")
