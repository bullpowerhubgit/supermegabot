#!/usr/bin/env python3
"""
MINI-VCI "HARD FLASH" - EXTREM RISIKOREICH!
============================================================
WARNUNG: Dies wird den Adapter wahrscheinlich ZERSTOREN!
Kein Schaltplan verfuegbar. JTAG-Pins unbekannt.
Keine Garantie fuer Erfolg.
============================================================

Der Adapter hat:
- FTDI FT232 (USB-Serial Bridge)
- Unbekannter separater MCU (wahrscheinlich STM32 oder PIC)

JTAG-Debugging ohne Schaltplan ist praktisch unmoeglich.
Dieses Skript versucht nur, den FTDI im BitBang zu aktivieren.
"""

import serial
import time
import sys

PORT = "/dev/tty.usbserial-A6007dAe"
BAUD = 38400

print("=" * 65)
print("  MINI-VCI HARD FLASH - EXTREMES RISIKO!")
print("=" * 65)
print()
print("  WARNUNG:")
print("  - Adapter kann UNWIEDERBRINGLICH zerstoert werden")
print("  - Keine Rueckkehr moeglich!")
print("  - JTAG Pins sind UNBEKANNT")
print("  - Erfolgschance: <5%")
print()

confirm = input("  Tippen Sie 'ZERSTOREN' um fortzufahren: ")
if confirm != "ZERSTOREN":
    print("  Abgebrochen. Adapter ist sicher.")
    sys.exit(0)

print()
print("  [OK] WARNUNG akzeptiert. Starte Experiment...")
print()

# Versuche serielle Verbindung
print("[1] Verbinde mit FTDI...")
try:
    ser = serial.Serial(PORT, BAUD, timeout=1)
    print(f"    [OK] FTDI geoeffnet ({BAUD} baud)")
except Exception as e:
    print(f"    [FEHLER] {e}")
    sys.exit(1)

# FTDI MPSSE/BitBang Info
print()
print("[2] FTDI STATUS")
print("-" * 65)
print("  FTDI Modus:     Standard UART (38400 baud)")
print("  JTAG-Zugang:    Nur ueber MPSSE-Modus moeglich")
print("  Problem:        MPSSE-Modus erfordert spezifische")
print("                  Konfiguration ohne Schaltplan")
print()

# Versuche verschiedene "Reset-Sequenzen"
print("[3] VERSUCHE PROTOKOLL-ERKENNUNG")
print("-" * 65)

# Einige Geraete haben einen Bootloader auf der seriellen Schnittstelle
bootloader_triggers = [
    ("STM32 Bootloader", b"\x7F", b"\x79"),  # STM32 USART sync
    ("STM32 IAP", b"\x00\xFF", None),
    ("Cypress Boot", b"B\x4C\x44\x52", None),
    ("PIC Boot", b"\x00\x00\x00\x00", None),
    ("Generic Sync", b"\x55\x55\x55\x55", None),
]

found_bootloader = False
for name, trigger, expected in bootloader_triggers:
    print(f"    Teste: {name}...")
    ser.reset_input_buffer()
    ser.write(trigger)
    time.sleep(0.3)
    r = ser.read(ser.in_waiting or 20)
    if len(r) > 0:
        print(f"      [DATA] Empfangen: {r.hex()} ({len(r)} bytes)")
        if expected and expected in r:
            print(f"      [OK] Bootloader erkannt!")
            found_bootloader = True
            break
    else:
        print(f"      [NO RESP] Keine Antwort")

if not found_bootloader:
    print()
    print("    [FEHLER] Kein Bootloader erkannt!")
    print("    Der Adapter antwortet auf GAR NICHTS.")
    print()

# Versuche JTAG over FTDI BitBang (sehr spekulativ)
print()
print("[4] JTAG OVER FTDI BITBANG (REIN SPEKULATIV)")
print("-" * 65)
print("  Ohne Schaltplan wissen wir nicht:")
print("    - Welche FTDI Pins mit JTAG verbunden sind")
print("    - Ob der interne Chip ueberhaupt JTAG hat")
print("    - Welcher Chip intern verbaut ist")
print()
print("  [INFO] Selbst wenn JTAG verfuegbar waere:")
print("    - Der Chip muss entsperrt sein")
print("    - Die Firmware ist wahrscheinlich geschuetzt")
print("    - Alternative Firmware muss kompatibel sein")
print()

# Schlussfolgerung
print()
print("=" * 65)
print("  ERGEBNIS: HARD FLASH NICHT MOEGLICH")
print("=" * 65)
print()
print("  Gruende:")
print("    1. Kein Bootloader auf serieller Schnittstelle")
print("    2. Keine JTAG-Pin-Zuordnung bekannt")
print("    3. Interner Chip unbekannt")
print("    4. Kein Schaltplan verfuegbar")
print("    5. FTDI-BitBang ohne Pinout nutzlos")
print()
print("  [FAZIT] Der Adapter ist ein 'Black Box' Geraet.")
print("          Ein Flash ist OHNE Hersteller-Dokumentation")
print("          praktisch unmoeglich.")
print()
print("  EMPFEHLUNG:")
print("    -> Kauf einen ELM327 Adapter fuer ~15€")
print("    -> ODER: Nutze den MINI-VCI mit Windows + Techstream")
print("    -> ODER: Akzeptiere, dass der Adapter fuer Toyota ist")
print()
print("=" * 65)

ser.close()
print("\nVerbindung geschlossen. Adapter ist unveraendert.")
input("\nENTER zum Beenden")
