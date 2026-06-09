#!/usr/bin/env python3
import serial
import time

PORT = "/dev/cu.988430957800"

print("USB Port:", PORT)
print()

try:
    ser = serial.Serial(PORT, 115200, timeout=3)
    print("Port geöffnet")
    
    # Lese alles
    ser.reset_input_buffer()
    time.sleep(1)
    r = ser.read(ser.in_waiting or 100)
    if r:
        print(f"DATEN: {r.hex()}")
    else:
        print("KEINE DATEN")
    
    # Sende ATZ
    ser.write(b"ATZ\r")
    time.sleep(2)
    r = ser.read(ser.in_waiting or 100)
    if r:
        print(f"ANTWORT: {r.hex()}")
    else:
        print("KEINE ANTWORT")
    
    ser.close()
except Exception as e:
    print(f"FEHLER: {e}")

print()
print("FAZIT: ThinkDiag 2 antwortet nicht über USB")
