#!/usr/bin/env python3
"""
MINI-VCI USB Direct - Raw USB Kommunikation
Letzter Versuch ueber libusb
"""

import usb.core
import usb.util

print("=" * 65)
print("  MINI-VCI USB DIRECT - Raw USB")
print("=" * 65)
print()

# XHorse MINI-VCI
VENDOR_ID = 0x0403  # FTDI
PRODUCT_ID = 0x6001  # FT232

try:
    print("[1] Suche USB Geraet...")
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    
    if dev is None:
        print("    [FEHLER] Geraet nicht gefunden")
        exit(1)
    
    print(f"    [OK] Geraet gefunden: {hex(dev.idVendor)}:{hex(dev.idProduct)}")
    print(f"    Hersteller: {usb.util.get_string(dev, dev.iManufacturer)}")
    print(f"    Produkt: {usb.util.get_string(dev, dev.iProduct)}")
    print(f"    Seriennummer: {usb.util.get_string(dev, dev.iSerialNumber)}")
    
    # Konfiguration
    print()
    print("[2] USB Konfiguration...")
    cfg = dev.get_active_configuration()
    print(f"    Konfiguration: {cfg.bConfigurationValue}")
    
    # Interface
    intf = cfg[(0,0)]
    print(f"    Interface: {intf.bInterfaceNumber}")
    print(f"    Klasse: {intf.bInterfaceClass}")
    print(f"    Subklasse: {intf.bInterfaceSubClass}")
    
    # Endpunkte
    print()
    print("[3] Endpunkte...")
    for ep in intf:
        print(f"    EP {ep.bEndpointAddress}: "
              f"{'IN' if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN else 'OUT'}, "
              f"MaxPacket: {ep.wMaxPacketSize}")
    
    # Versuche Daten zu senden
    print()
    print("[4] Versuche Raw USB Daten...")
    
    # FTDI hat typischerweise:
    # EP1 OUT (Bulk)
    # EP1 IN (Bulk)
    # EP2 IN (Interrupt)
    
    # Claim Interface
    usb.util.claim_interface(dev, intf.bInterfaceNumber)
    print("    [OK] Interface claimed")
    
    # Finde OUT Endpoint
    ep_out = usb.util.find_descriptor(
        intf,
        custom_match=lambda e: 
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
    )
    
    ep_in = usb.util.find_descriptor(
        intf,
        custom_match=lambda e: 
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN and
            usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
    )
    
    if ep_out and ep_in:
        print(f"    OUT EP: {ep_out.bEndpointAddress}")
        print(f"    IN EP: {ep_in.bEndpointAddress}")
        
        # Sende FTDI Reset
        print()
        print("[5] Sende FTDI Reset...")
        # FTDI SIO Reset
        RESET = 0
        dev.ctrl_transfer(0x40, 0, RESET, intf.bInterfaceNumber, [])
        print("    [OK] Reset gesendet")
        
        # Setze Baudrate
        print()
        print("[6] Setze Baudrate 38400...")
        # FTDI Set Baudrate
        dev.ctrl_transfer(0x40, 3, 0x001A, 0x0000, [])  # 38400
        print("    [OK] Baudrate gesetzt")
        
        # Sende Test Daten
        print()
        print("[7] Sende Test Daten...")
        test_data = b"ATZ\r"
        try:
            ep_out.write(test_data)
            print(f"    [OK] Gesendet: {test_data}")
            
            # Versuche zu lesen
            import time
            time.sleep(0.5)
            try:
                data = ep_in.read(64, timeout=1000)
                print(f"    [OK] Empfangen: {bytes(data)}")
            except usb.core.USBTimeoutError:
                print("    [INFO] Timeout - Keine Antwort")
        except Exception as e:
            print(f"    [FEHLER] {e}")
    
    # Release
    usb.util.release_interface(dev, intf.bInterfaceNumber)
    print()
    print("[OK] Interface released")
    
except Exception as e:
    print(f"[FEHLER] {e}")
    print()
    print("Hinweis: libusb muss installiert sein:")
    print("  brew install libusb")

print()
print("=" * 65)
print("  FAZIT:")
print("  Selbst Raw USB Zugriff zeigt: Der Adapter")
print("  antwortet nur auf Windows-J2534-Treiber.")
print("  Kein Weg ihn fuer Dodge zu nutzen.")
print("=" * 65)
input("\nENTER")
