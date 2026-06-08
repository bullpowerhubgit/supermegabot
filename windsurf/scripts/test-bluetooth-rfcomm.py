#!/usr/bin/env python3
"""
ThinkDiag 2 - Bluetooth RFCOMM Test
"""

import serial
import time
import subprocess
import re

ADDRESS = "DC:0D:30:84:4F:C2"

print("=" * 70)
print("  THINKDIAG 2 - BLUETOOTH RFCOMM TEST")
print("=" * 70)
print()

# Pruefe ob RFCOMM Port existiert
print("[1] Pruefe RFCOMM Ports...")
try:
    result = subprocess.run(['rfcomm'], capture_output=True, text=True)
    print(result.stdout)
except:
    print("rfcomm nicht verfügbar")

print()

# Versuche, RFCOMM zu verbinden
print("[2] Versuche RFCOMM Verbindung...")
try:
    # Finde freien Channel
    for channel in range(1, 10):
        try:
            # Verbinde
            subprocess.run(['rfcomm', 'connect', f'rfcomm{channel}', ADDRESS, str(channel)], 
                          capture_output=True, timeout=2)
            print(f"  [OK] Verbunden auf rfcomm{channel}")
            port = f"/dev/rfcomm{channel}"
            
            # Teste serielle Verbindung
            ser = serial.Serial(port, 115200, timeout=2)
            print(f"  [OK] Port geöffnet: {port}")
            
            # Lese initial
            ser.reset_input_buffer()
            time.sleep(1)
            r = ser.read(ser.in_waiting or 100)
            if r:
                print(f"  [!!!] DATEN: {r.hex()}")
            
            # Sende ATZ
            ser.write(b"ATZ\r")
            time.sleep(2)
            r = ser.read(ser.in_waiting or 100)
            if r:
                print(f"  [!!!] ANTWORT: {r.hex()}")
            
            ser.close()
            break
            
        except:
            continue
            
except Exception as e:
    print(f"  [FEHLER] {e}")

print()
print("[3] Pruefe alternative Methode (pybluez)...")
try:
    import bluetooth
    print("  [OK] pybluez verfügbar")
    
    # Finde Services
    services = bluetooth.find_service(address=ADDRESS)
    print(f"  [INFO] Gefundene Services: {len(services)}")
    for svc in services:
        print(f"    - Port: {svc['port']}, Name: {svc.get('name', 'Unknown')}, Protocol: {svc.get('protocol', 'Unknown')}")
        
except ImportError:
    print("  [INFO] pybluez nicht installiert")

print()
print("=" * 70)
