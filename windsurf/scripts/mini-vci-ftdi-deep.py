#!/usr/bin/env python3
"""
MINI-VCI FTDI Deep Access
Versucht FTDI MPSSE und BitBang Modus
Kann versteckte Modi aufdecken
"""

import sys

try:
    from pyftdi.ftdi import Ftdi
    from pyftdi.usbtools import UsbTools
    print("[OK] pyftdi geladen")
except ImportError:
    print("[INFO] pyftdi nicht installiert, versuche...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "pyftdi"], 
                   capture_output=True)
    from pyftdi.ftdi import Ftdi
    from pyftdi.usbtools import UsbTools
    print("[OK] pyftdi installiert und geladen")

print("=" * 65)
print("  MINI-VCI FTDI DEEP ACCESS")
print("  Suche versteckte Modi...")
print("=" * 65)
print()

# 1. Finde FTDI Geraete
print("[1] Suche FTDI Geraete...")
try:
    devices = UsbTools.find_all([(0x0403, 0x6001)])
    print(f"    [OK] {len(list(devices))} FT232 Geraete gefunden")
except Exception as e:
    print(f"    [FEHLER] {e}")
    input("\nENTER")
    sys.exit(1)

# Versuche direkten Zugriff
print()
print("[2] Versuche direkten FTDI Zugriff...")

try:
    # Oeffne mit Default URL
    ftdi = Ftdi()
    ftdi.open(vendor=0x0403, product=0x6001, serial="A6007dAe")
    print("    [OK] FTDI geoeffnet (Serial: A6007dAe)")
    
    # Pruefe aktuellen Modus
    print(f"    Baudrate: {ftdi.baudrate}")
    print(f"    Device ID: {hex(ftdi.device_id)}")
    
    # Versuche BitBang Modus
    print()
    print("[3] Teste BitBang Modus...")
    try:
        ftdi.set_bitmode(0xFF, Ftdi.BITMODE_BITBANG)
        print("    [OK] BitBang aktiviert!")
        
        # Lese Pins
        pins = ftdi.read_pins()
        print(f"    Pin-Status: {bin(pins)}")
        
        # Versuche verschiedene Pin-Kombinationen
        print()
        print("[4] Teste Pin-Kombinationen...")
        for val in [0x00, 0xFF, 0x55, 0xAA]:
            ftdi.write_data(bytes([val]))
            import time
            time.sleep(0.1)
            r = ftdi.read_pins()
            print(f"    Geschrieben: {hex(val)} -> Gelesen: {bin(r)}")
        
        # Zurueck zu UART
        ftdi.set_bitmode(0x00, Ftdi.BITMODE_RESET)
        print("    [OK] Zurueck zu UART")
        
    except Exception as e:
        print(f"    [FEHLER] BitBang: {e}")
    
    # Versuche MPSSE Modus
    print()
    print("[5] Teste MPSSE Modus...")
    try:
        ftdi.set_bitmode(0x00, Ftdi.BITMODE_MPSSE)
        print("    [OK] MPSSE aktiviert!")
        print("    JTAG/SPI ueber MPSSE theoretisch moeglich")
        print("    ABER: Pin-Zuordnung unbekannt!")
        ftdi.set_bitmode(0x00, Ftdi.BITMODE_RESET)
    except Exception as e:
        print(f"    [FEHLER] MPSSE: {e}")
    
    # Versuche Sync-BBM Modus
    print()
    print("[6] Teste Sync-BBM Modus...")
    try:
        ftdi.set_bitmode(0x00, Ftdi.BITMODE_SYNCBB)
        print("    [OK] Sync-BBM aktiviert!")
        ftdi.set_bitmode(0x00, Ftdi.BITMODE_RESET)
    except Exception as e:
        print(f"    [FEHLER] Sync-BBM: {e}")
    
    ftdi.close()
    print()
    print("[OK] FTDI geschlossen")
    
except Exception as e:
    print(f"    [FEHLER] FTDI Zugriff: {e}")
    print()
    print("    Moeglicher Grund:")
    print("    - Der Port /dev/tty.usbserial-A6007dAe ist belegt")
    print("    - Ein anderes Programm nutzt den Adapter")
    print("    - Mac blockiert direkten USB-Zugriff")

print()
print("=" * 65)
print("  ANALYSE:")
print("  Selbst wenn BitBang/MPSSE funktionieren:")
print("  - Pin-Zuordnung zum internen Chip UNBEKANNT")
print("  - Ohne Schaltplan: Keine Chance JTAG zu finden")
print("  - Der interne Chip koennte gesperrt sein (RDP)")
print("=" * 65)

print("\nENTER zum Beenden")
input()
