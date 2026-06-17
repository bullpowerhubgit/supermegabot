#!/usr/bin/env python3
"""
MINI-VCI FTDI v2 - Korrekte pyftdi API
"""

from pyftdi.ftdi import Ftdi
from pyftdi.usbtools import UsbTools
import time

print("=" * 65)
print("  MINI-VCI FTDI v2 - Deep Access")
print("=" * 65)
print()

# URL fuer FTDI
try:
    url = Ftdi.get_identifiers()[0]
    print(f"[OK] FTDI URL: {url}")
except Exception as e:
    print(f"[FEHLER] {e}")
    exit(1)

# Oeffne im UART Modus zuerst
ftdi = Ftdi()
try:
    ftdi.open_from_url(url)
    print("[OK] FTDI geoeffnet")
    print(f"    Modus: {ftdi.bitmode}")
    print(f"    Baudrate: {ftdi.baudrate}")
    
    # Schliesse und oeffne frisch
    ftdi.close()
    time.sleep(0.5)
    
    # Versuche BitBang
    print()
    print("[2] Teste BITBANG Modus...")
    ftdi.open_from_url(url)
    ftdi.set_bitmode(0xFF, Ftdi.BITMODE_BITBANG)
    print("    [OK] BITBANG aktiviert!")
    
    # Lese Pins
    pins = ftdi.read_pins()
    print(f"    Pin-Status: {pins:08b}")
    
    # Schreibe verschiedene Muster
    for val in [0x00, 0xFF, 0x55, 0xAA, 0x0F, 0xF0]:
        ftdi.write_data(bytes([val]))
        time.sleep(0.1)
        pins = ftdi.read_pins()
        print(f"    Out:{val:02X} -> In:{pins:08b}")
    
    ftdi.set_bitmode(0, Ftdi.BITMODE_RESET)
    print("    [OK] Reset zum UART")
    ftdi.close()
    
    # Versuche MPSSE
    print()
    print("[3] Teste MPSSE Modus...")
    ftdi.open_from_url(url)
    try:
        ftdi.set_bitmode(0, Ftdi.BITMODE_MPSSE)
        print("    [OK] MPSSE aktiviert!")
        print("    JTAG/SPI theoretisch moeglich")
        ftdi.set_bitmode(0, Ftdi.BITMODE_RESET)
    except Exception as e:
        print(f"    [FEHLER] MPSSE: {e}")
    ftdi.close()
    
    # Versuche CBUS BitBang
    print()
    print("[4] Teste CBUS BitBang...")
    ftdi.open_from_url(url)
    try:
        ftdi.set_bitmode(0xFF, Ftdi.BITMODE_CBUS)
        print("    [OK] CBUS aktiviert!")
        ftdi.set_bitmode(0, Ftdi.BITMODE_RESET)
    except Exception as e:
        print(f"    [FEHLER] CBUS: {e}")
    ftdi.close()
    
except Exception as e:
    print(f"[FEHLER] {e}")

print()
print("=" * 65)
print("  FTDI Deep Access abgeschlossen")
print("=" * 65)
input("\nENTER")
