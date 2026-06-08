#!/usr/bin/env python3
"""
ThinkDiag 2 - ULTIMATIVER USB TEST
Alle möglichen Kombinationen
"""

import serial
import time

PORT = "/dev/cu.988430957800"

print("=" * 70)
print("  THINKDIAG 2 - ULTIMATIVER USB TEST")
print("=" * 70)
print()

# Alle möglichen Konfigurationen
configs = [
    # (baud, bytesize, parity, stopbits, name)
    (9600, 8, 'N', 1, "9600-8N1"),
    (19200, 8, 'N', 1, "19200-8N1"),
    (38400, 8, 'N', 1, "38400-8N1"),
    (57600, 8, 'N', 1, "57600-8N1"),
    (115200, 8, 'N', 1, "115200-8N1"),
    (230400, 8, 'N', 1, "230400-8N1"),
    (460800, 8, 'N', 1, "460800-8N1"),
    (921600, 8, 'N', 1, "921600-8N1"),
    (9600, 7, 'E', 1, "9600-7E1"),
    (9600, 7, 'O', 1, "9600-7O1"),
    (9600, 8, 'N', 2, "9600-8N2"),
]

# Alle möglichen Befehle
commands = [
    b"ATZ\r",
    b"ATI\r",
    b"010C\r",
    b"AT\r",
    b"\x00",
    b"\xFF",
    b"TD\r",
    b"VER\r",
    b"INIT\r",
    b"START\r",
    b"CONNECT\r",
    b"MODE\r",
    b"\x02\x01\x0C",
    b"t7DF802010C\r",
    b"\x55\x55\x55\x55",
]

parity_map = {'N': serial.PARITY_NONE, 'E': serial.PARITY_EVEN, 'O': serial.PARITY_ODD}

found = False

for baud, bytesize, parity, stopbits, name in configs:
    try:
        ser = serial.Serial(
            PORT,
            baudrate=baud,
            bytesize=bytesize,
            parity=parity_map[parity],
            stopbits=stopbits,
            timeout=1,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        )
        
        # Lese initial
        ser.reset_input_buffer()
        time.sleep(0.5)
        r = ser.read(ser.in_waiting or 50)
        if r:
            print(f"[!!!] {name} - INITIAL DATA: {r.hex()}")
            found = True
        
        # Sende alle Befehle
        for cmd in commands:
            ser.reset_input_buffer()
            ser.write(cmd)
            time.sleep(0.5)
            r = ser.read(ser.in_waiting or 50)
            if r:
                print(f"[!!!] {name} - CMD {cmd.hex()[:10]} -> {r.hex()[:40]}")
                found = True
        
        ser.close()
        
    except Exception as e:
        pass

print()
if found:
    print("[!!!] DATEN GEFUNDEN!")
else:
    print("[!!!] KEINE DATEN - ThinkDiag 2 antwortet nicht über USB")

print()
print("=" * 70)
print("  LÖSUNG: iPhone/iPad + ThinkDiag+ App")
print("=" * 70)
