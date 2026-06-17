#!/usr/bin/env python3
"""
MINI-VCI FTDI v3 - Mit korrekter URL
"""

from pyftdi.ftdi import Ftdi
import time

print("=" * 65)
print("  MINI-VCI FTDI v3 - Direct USB Access")
print("=" * 65)
print()

# XHorse MINI-VCI hat FTDI FT232
# Vendor: 0x0403, Product: 0x6001
vendor = 0x0403
product = 0x6001
serial = "A6007dAe"

ftdi = Ftdi()

try:
    print("[1] Oeffne FTDI...")
    ftdi.open(vendor, product, serial=serial)
    print("    [OK] FTDI geoeffnet!")
    print(f"    Chip: {ftdi.ic_name}")
    print(f"    Baudrate: {ftdi.baudrate}")
    
    # Teste UART Lesen
    print()
    print("[2] Teste UART Lesen...")
    ftdi.purge_rx_buffer()
    time.sleep(0.5)
    data = ftdi.read_data(64)
    if data:
        print(f"    Daten: {data.hex()}")
    else:
        print("    Keine Daten im UART Puffer")
    
    # BitBang Test
    print()
    print("[3] Teste BITBANG...")
    ftdi.set_bitmode(0xFF, Ftdi.BITMODE_BITBANG)
    print("    [OK] BitBang aktiviert")
    
    # Teste Output/Input
    for val in [0x00, 0xFF]:
        ftdi.write_data(bytes([val]))
        time.sleep(0.1)
        pins = ftdi.read_pins()
        print(f"    Output {val:02X} -> Read {pins:08b}")
    
    # Zurueck zu UART
    ftdi.set_bitmode(0, Ftdi.BITMODE_RESET)
    print("    [OK] Reset zu UART")
    
    # CBUS Test (falls vorhanden)
    print()
    print("[4] Teste CBUS...")
    try:
        ftdi.set_bitmode(0xF0, Ftdi.BITMODE_CBUS)
        print("    [OK] CBUS aktiviert")
        ftdi.set_bitmode(0, Ftdi.BITMODE_RESET)
    except Exception as e:
        print(f"    [INFO] CBUS nicht verfuegbar: {e}")
    
    ftdi.close()
    print()
    print("[OK] FTDI geschlossen")
    
except Exception as e:
    print(f"[FEHLER] {e}")
    print()
    print("Moegliche Ursachen:")
    print("- MacOS blockiert direkten USB Zugriff")
    print("- Serieller Port ist belegt")
    print("- Treiber Konflikt")

print()
print("=" * 65)
input("ENTER zum Beenden")
