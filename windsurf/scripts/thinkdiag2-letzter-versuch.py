#!/usr/bin/env python3
"""
ThinkDiag 2 - LETZTER VERSUCH
Spezielle Init-Sequenzen fuer versteckte Modi
"""

import serial
import time

PORT = "/dev/cu.988430957800"
BAUDS = [38400, 115200, 9600, 57600]

print("=" * 70)
print("  THINKDIAG 2 - LETZTER VERSUCH")
print("  Spezielle Sequenzen / versteckte Modi")
print("=" * 70)
print()

found_anything = False

for baud in BAUDS:
    print(f"[BAUDRATE: {baud}]")
    print("-" * 70)
    
    try:
        ser = serial.Serial(PORT, baud, timeout=2)
    except:
        continue
    
    # Manche Dongles brauchen DTR/RTS spezielle Signale
    print("  [1] Teste DTR/RTS Wake-up...")
    
    sequences = [
        # Normale Wake-up
        ("DTR Low 2s", lambda: (ser.dtr(False), time.sleep(2), ser.dtr(True))),
        ("RTS Toggle", lambda: (ser.rts(False), time.sleep(0.5), ser.rts(True))),
        ("Beide Low", lambda: (ser.dtr(False), ser.rts(False), time.sleep(1), ser.dtr(True), ser.rts(True))),
    ]
    
    for name, wake_fn in sequences:
        wake_fn()
        time.sleep(0.5)
        ser.reset_input_buffer()
        
        # Teste nach Wake-up
        ser.write(b"ATZ\r")
        time.sleep(1)
        r = ser.read(ser.in_waiting or 50)
        if len(r) > 0:
            print(f"    [!!!] {name}: ANTWORT! {r.hex()}")
            found_anything = True
        else:
            print(f"    {name}: keine Antwort")
    
    # Spezielle Initialisierungs-Sequenzen
    print()
    print("  [2] Spezielle Init-Sequenzen...")
    
    inits = [
        (b"\x00\x00\x00\x00\x00\x00\x00\x00", "8x Null"),
        (b"\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF", "8x FF"),
        (b"\x55\xAA\x55\xAA\x55\xAA\x55\xAA", "Sync Toggle"),
        (b"\x7F\x7F\x7F\x7F", "STM32 Boot"),
        (b"\xC0\x00", "SLCAN Init"),
        (b"\x01\x00\x00\x00", "J2534 Open"),
        (b"TD2INIT\r", "ThinkDiag Init"),
        (b"LAUNCH\r", "Launch String"),
        (b"MODE 0\r", "Mode String"),
        (b"DIAG\r", "Diag String"),
        (b"CONNECT\r", "Connect String"),
        (b"\x10\x03", "Modem Escape"),
        (b"+++\r", "Modem Escape++"),
        (b"AT\rAT\rAT\r", "Triple AT"),
        (b"\r\r\r", "Triple CR"),
        (b"?\r", "Question Mark"),
        (b"HELP\r", "Help"),
        (b"VER\r", "Version"),
        (b"ID\r", "ID"),
        (b"INFO\r", "Info"),
        (b"STATUS\r", "Status"),
    ]
    
    for cmd, name in inits:
        ser.reset_input_buffer()
        ser.write(cmd)
        time.sleep(0.8)
        r = ser.read(ser.in_waiting or 50)
        
        if len(r) > 0:
            r_hex = r.hex()[:40]
            r_str = r.decode('utf-8', errors='replace').strip()[:40]
            print(f"    [!!!] {name:15s} -> Hex:{r_hex}  Text:'{r_str}'")
            found_anything = True
    
    ser.close()
    print()

print("=" * 70)
if found_anything:
    print("  [ERFOLG] Antwort erhalten! Weitere Analyse...")
else:
    print("  [KEIN ERFOLG]")
    print()
    print("  Der ThinkDiag 2 ist ein CLOSED-SYSTEM.")
    print("  Er funktioniert NUR mit der offiziellen ThinkDiag+ App.")
    print()
    print("  OFFIZIELLE SOFTWARE:")
    print("    Android: https://play.google.com/store/apps/details?id=com.us.thinkdiag.plus")
    print("    iOS: App Store -> 'ThinkDiag+'")
    print()
    print("  Keine Alternative-Software existiert!")
print("=" * 70)

print("\nENTER zum Beenden")
input()
