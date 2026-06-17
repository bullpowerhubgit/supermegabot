#!/usr/bin/env python3
"""
MINI-VCI FTDI Final - Mit korrekter API
"""

from pyftdi.ftdi import Ftdi
from pyftdi.eeprom import FtdiEeprom
import time

print("=" * 65)
print("  MINI-VCI FTDI FINAL - Direct USB Access")
print("=" * 65)
print()

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
    print(f"    Modus: {ftdi.is_mpsse}")
    
    # Pruefe ob MPSSE unterstuetzt
    print()
    print("[2] Pruefe MPSSE Faehigkeit...")
    print(f"    MPSSE: {ftdi.has_mpsse}")
    
    # BitBang
    print()
    print("[3] Teste BitBang...")
    try:
        ftdi.set_bitmode(0xFF, 0x01)  # BITMODE_BITBANG = 0x01
        print("    [OK] BitBang aktiviert")
        pins = ftdi.read_pins()
        print(f"    Pins: {pins:08b}")
        ftdi.write_data(bytes([0x55]))
        time.sleep(0.1)
        pins = ftdi.read_pins()
        print(f"    Nach 0x55: {pins:08b}")
        ftdi.set_bitmode(0, 0x00)  # Reset
        print("    [OK] Reset")
    except Exception as e:
        print(f"    [FEHLER] BitBang: {e}")
    
    # Versuche EEPROM auszulesen
    print()
    print("[4] Lese EEPROM...")
    try:
        eeprom = FtdiEeprom()
        eeprom.connect(ftdi)
        print(f"    [OK] EEPROM verbunden")
        print(f"    Hersteller: {eeprom.manufacturer}")
        print(f"    Produkt: {eeprom.product}")
        print(f"    Seriennummer: {eeprom.serial}")
        
        # Versuche Vendor/Product ID
        vid = eeprom.vendor_id
        pid = eeprom.product_id
        print(f"    VID:PID = {vid:04X}:{pid:04X}")
        
    except Exception as e:
        print(f"    [FEHLER] EEPROM: {e}")
    
    # CBUS
    print()
    print("[5] Teste CBUS...")
    try:
        ftdi.set_bitmode(0xF0, 0x20)  # BITMODE_CBUS = 0x20
        print("    [OK] CBUS aktiviert")
        ftdi.set_bitmode(0, 0x00)
    except Exception as e:
        print(f"    [FEHLER] CBUS: {e}")
    
    ftdi.close()
    print()
    print("[OK] FTDI geschlossen")
    
except Exception as e:
    print(f"[FEHLER] {e}")

print()
print("=" * 65)
print("  ANALYSE:")
print("  Der FTDI Chip ist erreichbar, aber ohne Schaltplan")
print("  koennen wir nicht wissen, welche Pins zum internen")
print("  Chip fuehren. BitBang ist nutzlos ohne Pinout.")
print("=" * 65)
input("\nENTER zum Beenden")
