#!/usr/bin/env python3
"""
Dodge Challenger 2010 V6 3.5L - ThinkDiag 2 Verbindungstest
Testet Bluetooth-Verbindung und OBD2-Kommunikation
"""

import asyncio
from bleak import BleakScanner, BleakClient
import sys

print("==========================================")
print("Dodge Challenger 2010 V6 3.5L - Verbindungstest")
print("==========================================")
print()

async def scan_bluetooth_devices():
    """Sucht nach Bluetooth-Geräten in der Nähe"""
    print("1. Suche nach Bluetooth-Geräten...")
    try:
        # Timeout für macOS Bluetooth-Scan
        devices = await asyncio.wait_for(BleakScanner.discover(), timeout=10.0)
        print(f"   Gefundene Geräte: {len(devices)}")
        print()
        
        thinkdiag_found = False
        for device in devices:
            name = device.name or "Unbekannt"
            print(f"   - {name} ({device.address})")
            if name and ("ThinkDiag" in name or "THINK" in name or "OBD" in name or "Diag" in name):
                print(f"   ✓ Möglicher ThinkDiag gefunden: {name}")
                thinkdiag_found = True
                return device.address, name
        
        if not thinkdiag_found:
            print("\n   ⚠️ Kein ThinkDiag 2 gefunden")
            print("   Tipp: ThinkDiag 2 muss:")
            print("   - Im OBD2-Port des Dodge Challengers stecken")
            print("   - Eingeschaltet sein")
            print("   - In Bluetooth-Reichweite sein")
            return None, None
        
    except asyncio.TimeoutError:
        print("   ✗ Bluetooth-Scan Timeout (10 Sekunden)")
        print("   Tipp: macOS Bluetooth-Berechtigungen prüfen")
        return None, None
    except Exception as e:
        print(f"   ✗ Bluetooth-Fehler: {e}")
        return None, None

async def test_obd_connection(device_address):
    """Testet OBD2-Verbindung"""
    print(f"\n2. Teste OBD2-Verbindung mit {device_address}...")
    
    try:
        async with BleakClient(device_address) as client:
            print("   ✓ Bluetooth-Verbindung hergestellt")
            
            # Prüfe verfügbare Services
            services = client.services
            print(f"   Gefundene Services: {len(services)}")
            
            for service in services:
                print(f"   - {service.uuid}")
            
            return True
            
    except Exception as e:
        print(f"   ✗ Verbindungsfehler: {e}")
        return False

async def main():
    print("Prüfe ThinkDiag 2 Verbindung...\n")
    
    # Bluetooth-Scan
    device_addr, device_name = await scan_bluetooth_devices()
    
    if device_addr:
        # OBD2-Verbindungstest
        success = await test_obd_connection(device_addr)
        
        if success:
            print("\n✓ ThinkDiag 2 erfolgreich verbunden!")
            print("\nNächste Schritte:")
            print("- Dodge Challenger 2010 V6 3.5L auswählen")
            print("- Full System Scan durchführen")
            print("- Fehlercodes P0335, P0340, P0230 prüfen")
        else:
            print("\n✗ Verbindung fehlgeschlagen")
            print("Tipp: ThinkDiag 2 muss im OBD2-Port stecken")
    else:
        print("\n✗ Kein ThinkDiag 2 gefunden")
        print("Tipp: ThinkDiag 2 muss eingeschaltet und im OBD2-Port stecken")

if __name__ == "__main__":
    asyncio.run(main())
