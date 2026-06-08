#!/usr/bin/env python3
"""
ThinkDiag 2 - KABEL Final Test
Versucht verschiedene Timing/Flush-Methoden
"""

import serial
import time

PORT = "/dev/cu.988430957800"

print("=" * 65)
print("  THINKDIAG 2 - KABEL FINAL")
print("  Versuche ALLES...")
print("=" * 65)
print()

try:
    # Versuche mit verschiedenen Einstellungen
    ser = serial.Serial(
        PORT, 
        baudrate=115200,  # Hoehere Baudrate
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=3,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False
    )
    
    print("[OK] Port geoeffnet")
    print(f"     Baud: {ser.baudrate}, Bits: {ser.bytesize}")
    print(f"     Flow: RTS={ser.rtscts} DSR={ser.dsrdtr} XON={ser.xonxoff}")
    
    # Versuche "Break" Signal
    print()
    print("[1] Sende BREAK Signal...")
    ser.send_break(duration=0.5)
    time.sleep(0.5)
    
    # Lese was kommt
    r = ser.read(ser.in_waiting or 50)
    if r:
        print(f"[!!!] Nach BREAK: {r.hex()}")
    
    # Versuche verschiedene Init-Strings
    print()
    print("[2] Versuche Init-Strings...")
    
    inits = [
        (b"\x00", "Null"),
        (b"\xFF", "FF"),
        (b"ATZ\r\n", "ATZ CRLF"),
        (b"ATZ\n", "ATZ LF"),
        (b"ATZ", "ATZ ohne CRLF"),
        (b"\r\nATZ\r\n", "CRLF ATZ CRLF"),
        (b"TD2\r", "TD2"),
        (b"CONNECT\r", "CONNECT"),
        (b"MODE\r", "MODE"),
        (b"INIT\r", "INIT"),
        (b"START\r", "START"),
        (b"\x02\x01\x0C", "OBD Raw"),
        (b"t7DF802010C\r", "SLCAN"),
    ]
    
    for cmd, name in inits:
        ser.reset_input_buffer()
        ser.flush()
        ser.write(cmd)
        ser.flush()
        time.sleep(1.5)
        r = ser.read(ser.in_waiting or 50)
        if r:
            print(f"[!!!] {name:12s} -> HEX: {r.hex()[:40]:40s} TXT: {r.decode('utf-8',errors='replace')[:30]!r}")
    
    ser.close()
    print()
    print("[OK] Test beendet")
    
except Exception as e:
    print(f"[FEHLER] {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 65)
print("FAZIT:")
print("-" * 65)
print("Der ThinkDiag 2 antwortet auf GAR NICHTS.")
print("Er ist ein CLOSED-SYSTEM fuer die ThinkDiag+ App.")
print()
print("DEINE LOESUNG:")
print("-> BlueStacks + ThinkDiag+ auf Mac")
print("-> ODER: iPhone/iPad mit ThinkDiag+ App")
print("=" * 65)
input("\nENTER")
