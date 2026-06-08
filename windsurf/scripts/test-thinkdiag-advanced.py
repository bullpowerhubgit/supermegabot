#!/usr/bin/env python3
"""
ThinkDiag 2 - Advanced Test
Versucht verschiedene Modi, Init-Sequenzen, Baudraten
"""

import serial
import time

PORT = "/dev/cu.988430957800"
BAUDS = [9600, 19200, 38400, 57600, 115200, 230400, 500000, 1000000]

print("=" * 65)
print("  THINKDIAG 2 - ADVANCED TEST")
print("  Versuche ALLE Moeglichkeiten...")
print("=" * 65)
print()

found_anything = False

for baud in BAUDS:
    print(f"\n[BAUDRATE: {baud}]")
    print("-" * 50)
    
    try:
        ser = serial.Serial(PORT, baud, timeout=1.5)
    except Exception as e:
        print(f"  [FEHLER] {e}")
        continue
    
    # Teste: DTR/RTS Toggle (manchmal noetig fuer Wake-up)
    ser.dtr = False
    ser.rts = False
    time.sleep(0.1)
    ser.dtr = True
    ser.rts = True
    time.sleep(0.1)
    
    tests = [
        # Standard ELM327
        (b"ATZ\r", "ELM327 Reset"),
        (b"AT\r", "ELM327 AT"),
        (b"ATI\r", "ELM327 Info"),
        (b"ATE0\r", "Echo Off"),
        (b"ATL1\r", "Linefeed"),
        (b"ATH1\r", "Headers"),
        (b"ATDP\r", "Protocol"),
        (b"ATRV\r", "Voltage"),
        
        # OBD direkt
        (b"0100\r", "OBD Supported"),
        (b"010C\r", "OBD RPM"),
        (b"010D\r", "OBD Speed"),
        (b"03\r", "OBD DTCs"),
        (b"03\n", "OBD DTCs LF"),
        
        # ThinkDiag spezifisch?
        (b"\x55\x55\x55\x55", "Sync 55"),
        (b"\x00\x00\x00\x00", "Null"),
        (b"\xFF\xFF\xFF\xFF", "FF"),
        (b"TD\r", "ThinkDiag"),
        (b"DIAG\r", "Diag"),
        (b"LAUNCH\r", "Launch"),
        (b"\x02\x01\x0C\x00\x00\x00\x00", "ISO-TP RPM"),
        
        # Binary OBD
        (b"\x68\x6A\xF1\x01\x0C\xD0", "K-Line RPM"),
        (b"\xC1\x33\xF1\x81\x66", "KW1281"),
        
        # CAN Frames
        (b"t7DF802010C\r", "SLCAN RPM"),
        (b"T07DF802010C\r", "SLCAN Ext"),
        (b"O\r", "SLCAN Open"),
        (b"S6\r", "SLCAN 500k"),
        
        # Leerzeilen / CRLF Varianten
        (b"\r", "Nur CR"),
        (b"\n", "Nur LF"),
        (b"\r\n", "CRLF"),
        (b"", "Leer"),
    ]
    
    for cmd, name in tests:
        try:
            ser.reset_input_buffer()
            ser.write(cmd)
            time.sleep(0.8)
            r = ser.read(ser.in_waiting or 50)
        except:
            break
        
        if len(r) > 0:
            r_hex = r.hex()[:40]
            r_str = r.decode('utf-8', errors='replace').strip()[:40]
            print(f"  [!!!] {name:20s} -> Hex:{r_hex}  Text:'{r_str}'")
            found_anything = True
    
    ser.close()

print()
print("=" * 65)
if found_anything:
    print("  [ERFOLG] Antwort erhalten!")
    print("  Weitere Analyse moeglich...")
else:
    print("  [KEIN ERFOLG] Keine Antwort bei KEINER Einstellung.")
    print()
    print("  Der ThinkDiag 2 ist APP-GEBUNDEN.")
    print("  Er antwortet nur auf verschluesselte Befehle")
    print("  aus der offiziellen ThinkDiag-App.")
    print()
    print("  DU BRAUCHST EINEN ECHTEN ELM327 ADAPTER!")
print("=" * 65)

print("\nENTER zum Beenden")
input()
