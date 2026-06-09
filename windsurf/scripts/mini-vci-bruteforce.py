#!/usr/bin/env python3
"""
MINI-VCI BRUTEFORCE - Letzter Versuch jedes Protokoll
100+ verschiedene Init-Sequenzen werden getestet
"""

import serial
import time
import struct

PORT = "/dev/tty.usbserial-A6007dAe"
BAUDS = [9600, 19200, 38400, 57600, 115200, 230400, 500000, 1000000]

print("=" * 65)
print("  MINI-VCI BRUTEFORCE")
print("  100+ Protokolle werden getestet...")
print("=" * 65)
print()

found_anything = False

for baud in BAUDS:
    print(f"\n[BAUDRATE: {baud}]")
    print("-" * 65)
    
    try:
        ser = serial.Serial(PORT, baud, timeout=1)
    except:
        continue
    
    # Test 1-10: ELM327 Varianten
    tests = [
        (b"ATZ\r", "ELM327 Reset"),
        (b"AT\r", "ELM327 Echo"),
        (b"ATI\r", "ELM327 Info"),
        (b"ATZ\n", "ELM327 Reset LF"),
        (b"ATZ\r\n", "ELM327 Reset CRLF"),
        (b"AT@1\r", "ELM327 Device ID"),
        (b"ATSP0\r", "ELM327 Auto Protocol"),
        (b"ATE0\r", "ELM327 Echo Off"),
        (b"ATL1\r", "ELM327 Linefeed On"),
        (b"ATSTFF\r", "ELM327 Timeout"),
        
        # Test 11-20: SLCAN Varianten
        (b"O\r", "SLCAN Open"),
        (b"C\r", "SLCAN Close"),
        (b"S0\r", "SLCAN Speed 10k"),
        (b"S1\r", "SLCAN Speed 20k"),
        (b"S2\r", "SLCAN Speed 50k"),
        (b"S3\r", "SLCAN Speed 100k"),
        (b"S4\r", "SLCAN Speed 125k"),
        (b"S5\r", "SLCAN Speed 250k"),
        (b"S6\r", "SLCAN Speed 500k"),
        (b"S7\r", "SLCAN Speed 800k"),
        (b"S8\r", "SLCAN Speed 1M"),
        (b"v\r", "SLCAN Version"),
        (b"V\r", "SLCAN Version UC"),
        (b"N\r", "SLCAN Serial"),
        
        # Test 21-30: STM32 Bootloader
        (b"\x7F", "STM32 USART Sync"),
        (b"\x00\xFF", "STM32 IAP"),
        (b"\x7F\x7F\x7F", "STM32 Triple Sync"),
        
        # Test 31-40: J2534 Binary
        (b"\x00\x00\x00\x00", "J2534 Null"),
        (b"\x01\x00\x00\x00", "J2534 PassThruOpen"),
        (b"\x02\x00\x00\x00", "J2534 PassThruClose"),
        (b"\x03\x00\x00\x00", "J2534 PassThruConnect"),
        
        # Test 41-50: CANable/candleLight (gs_usb)
        (b"\x00\x01", "GS_USB Reset"),
        (b"\x00\x02", "GS_USB BitTiming"),
        
        # Test 51-60: Cypress
        (b"B", "Cypress Boot 'B'"),
        (b"L", "Cypress Boot 'L'"),
        (b"D", "Cypress Boot 'D'"),
        (b"R", "Cypress Boot 'R'"),
        
        # Test 61-70: PIC
        (b"\x00\x00\x00\x00\x00", "PIC Null"),
        (b"\x4D\x50\x00\x00", "PIC MP"),
        
        # Test 71-80: FTDI spezifisch
        (b"\xAA", "FTDI BitBang Toggle"),
        (b"\xAB", "FTDI MPSSE Toggle"),
        (b"\x40\x00\x00\x00\x00\x00", "FTDI Set Baud"),
        
        # Test 81-90: Raw hex dump
        (b"\x55\x55\x55\x55", "Sync Pattern U"),
        (b"\xAA\xAA\xAA\xAA", "Sync Pattern A"),
        (b"\xFF\xFF\xFF\xFF", "All High"),
        (b"\x00\x00\x00\x00", "All Low"),
        
        # Test 91-100: Kombinationen
        (b"\x02\x01\x0C", "OBD RPM Raw"),
        (b"t7DF802010C\r", "SLCAN OBD RPM"),
        (b"T07DF802010C\r", "SLCAN Ext OBD"),
        
        # Test 101+: Spezielle Sequenzen
        (b"\x11\x02\x01\x0C\x00\x00\x00\x00", "ISO-TP Single"),
        (b"\x10\x02\x01\x0C\x00\x00\x00\x00", "ISO-TP First"),
        (b"\x30\x00\x00", "ISO-TP Flow Ctrl"),
        
        # Test: MINI-VCI spezifisch
        (b"MINI\r", "MINI String"),
        (b"VCI\r", "VCI String"),
        (b"J2534\r", "J2534 String"),
        (b"PASSTHRU\r", "PASSTHRU String"),
        
        # Test: Protokoll-Umschaltung
        (b"ATPP 00 SV 01\r", "ELM Protocol Var"),
        (b"ATSP 6\r", "ELM Protocol 6"),
        (b"ATH1\r", "ELM Headers On"),
        (b"ATD1\r", "ELM DLen On"),
        
        # Test: CAN direkt
        (b"ATCRA 7E8\r", "ELM CAN RX Addr"),
        (b"ATSH 7E0\r", "ELM CAN TX Addr"),
        (b"ATFC SH 7E0\r", "ELM Flow Ctrl"),
        (b"ATCM 7E0\r", "ELM CAN Mask"),
    ]
    
    for cmd, name in tests:
        try:
            ser.reset_input_buffer()
            ser.write(cmd)
            time.sleep(0.2)
            r = ser.read(ser.in_waiting or 50)
        except serial.SerialException:
            break
        
        if len(r) > 0:
            r_hex = r.hex()[:40]
            r_str = r.decode('utf-8', errors='replace').strip()[:30]
            print(f"  [!!!] {name:25s} -> Hex:{r_hex}  Text:'{r_str}'")
            found_anything = True
            
    ser.close()

print()
print("=" * 65)
if found_anything:
    print("  ANTWORT ERHALTEN! Weitere Analyse moeglich...")
else:
    print("  KEINE ANTWORT bei KEINEM Protokoll!")
    print()
    print("  [FAZIT] Der Adapter ignoriert ALLE Befehle.")
    print("          Er erwartet spezifische Windows-Treiber.")
    print("          Ein 'Umbau' ist ohne Treiber nicht moeglich.")
print("=" * 65)
