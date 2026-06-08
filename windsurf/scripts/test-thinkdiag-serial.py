#!/usr/bin/env python3
"""
ThinkDiag 2 - Serieller Port Test
Testet ob der Port ELM327-Kommandos versteht
"""

import serial
import time

PORT = "/dev/cu.988430957800"  # Der neue Port
BAUD = 38400  # OBD Standard

print("=" * 65)
print("  THINKDIAG 2 - SERIELLER PORT TEST")
print(f"  Port: {PORT}")
print("=" * 65)
print()

try:
    print("[1] Oeffne seriellen Port...")
    ser = serial.Serial(PORT, BAUD, timeout=2)
    print(f"    [OK] Port geoeffnet ({BAUD} baud)")
    print(f"    Status: DSR={ser.dsr} DTR={ser.dtr} CTS={ser.cts} RTS={ser.rts}")
    
    # Teste verschiedene Init-Sequenzen
    tests = [
        (b"ATZ\r", "ELM327 Reset", b"ELM"),
        (b"ATI\r", "ELM327 Info", None),
        (b"ATE0\r", "Echo Off", b"OK"),
        (b"ATL1\r", "Linefeed On", b"OK"),
        (b"ATSP0\r", "Auto Protocol", b"OK"),
        (b"010C\r", "OBD RPM", b"41"),
        (b"0100\r", "OBD Supported PID", b"41"),
        (b"03\r", "OBD Trouble Codes", b"43"),
    ]
    
    print()
    print("[2] Sende ELM327 Test-Befehle...")
    print("-" * 65)
    
    found_elm = False
    for cmd, name, expected in tests:
        print(f"    {name}...")
        ser.reset_input_buffer()
        ser.write(cmd)
        time.sleep(1)
        r = ser.read(ser.in_waiting or 100)
        
        if len(r) > 0:
            r_str = r.decode('utf-8', errors='replace').strip()
            print(f"      [DATA] {r_str[:60]}")
            
            if expected and expected in r:
                print(f"      [OK] ELM327 erkannt!")
                found_elm = True
        else:
            print(f"      [KEINE ANTWORT]")
    
    # Wenn ELM327 erkannt, versuche mehr
    if found_elm:
        print()
        print("[3] ELM327 erkannt! Lese erweiterte Daten...")
        
        ser.write(b"0105\r")  # Coolant Temp
        time.sleep(1)
        r = ser.read(100)
        print(f"    Coolant: {r.decode('utf-8', errors='replace').strip()[:50]}")
        
        ser.write(b"010D\r")  # Speed
        time.sleep(1)
        r = ser.read(100)
        print(f"    Speed: {r.decode('utf-8', errors='replace').strip()[:50]}")
        
        ser.write(b"03\r")  # DTCs
        time.sleep(1)
        r = ser.read(200)
        print(f"    DTCs: {r.decode('utf-8', errors='replace').strip()[:50]}")
    
    ser.close()
    print()
    print("[OK] Port geschlossen")
    
except serial.SerialException as e:
    print(f"    [FEHLER] {e}")
    print()
    print("    Moegliche Gruende:")
    print("      - Port ist belegt (andere App offen)")
    print("      - ThinkDiag 2 nicht richtig verbunden")
    print("      - Adapter ist aus")

print()
print("=" * 65)
if found_elm:
    print("  [ERFOLG] ThinkDiag 2 ist ELM327-kompatibel!")
    print("  Du kannst jetzt '10-dodge-autoscan.app' nutzen!")
else:
    print("  [INFO] Keine ELM327-Antwort erhalten.")
    print("  Moegliche Gruende:")
    print("    - ThinkDiag 2 braucht App fuer Initialisierung")
    print("    - Fahrzeug-Zündung ist AUS")
    print("    - Protokoll ist proprietär (nicht ELM327)")
print("=" * 65)

print("\nENTER zum Beenden")
input()
