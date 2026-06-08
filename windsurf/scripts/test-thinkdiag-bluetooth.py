#!/usr/bin/env python3
"""
ThinkDiag 2 - Bluetooth Verbindungstest
"""

import asyncio
from bleak import BleakClient

ADDRESS = "DC:0D:30:84:4F:C2"

print("=" * 70)
print("  THINKDIAG 2 - BLUETOOTH TEST")
print("=" * 70)
print()

async def scan():
    print("[1] Scanne Bluetooth Geräte...")
    from bleak import BleakScanner
    devices = await BleakScanner.discover()
    for d in devices:
        name = d.name if d.name else "Unknown"
        if "98843" in str(d.address) or "Think" in name or "TD" in name:
            print(f"  [!!!] GEFUNDEN: {name} - {d.address}")
    print()

async def connect():
    print(f"[2] Verbinde mit ThinkDiag 2 ({ADDRESS})...")
    try:
        async with BleakClient(ADDRESS) as client:
            print(f"  [OK] Verbunden!")
            print(f"  Services: {client.services}")
            
            # Lese Services
            for service in client.services:
                print(f"  Service: {service.uuid}")
                for char in service.characteristics:
                    print(f"    Char: {char.uuid} - {char.properties}")
            
            # Versuche zu lesen
            print()
            print("[3] Versuche Daten zu lesen...")
            for service in client.services:
                for char in service.characteristics:
                    if "read" in char.properties:
                        try:
                            value = await client.read_gatt_char(char.uuid)
                            print(f"  [DATA] {char.uuid}: {value.hex()}")
                        except:
                            pass
                            
    except Exception as e:
        print(f"  [FEHLER] {e}")

print("Starte Bluetooth Test...")
asyncio.run(scan())
asyncio.run(connect())

print()
print("=" * 70)
