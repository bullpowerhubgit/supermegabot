#!/usr/bin/env python3
"""
J2534 API Test - Versucht MINI-VCI als PassThru Device anzusprechen
Mac/Linux kompatibel
"""

import sys

print("=" * 65)
print("  J2534 API TEST - MINI-VCI")
print("  Versuche J2534 PassThru auf Mac")
print("=" * 65)
print()

try:
    from J2534 import (
        get_list_j2534_devices,
        set_j2534_device_to_connect,
        pt_open, pt_close,
        pt_connect, pt_disconnect,
        pt_read_msgs, pt_write_msgs,
        pt_start_msg_filter, pt_stop_msg_filter,
        ProtocolFlags, BaudRates, PassThruFlags, FilterFlags
    )
    print("[OK] J2534 API geladen")
except ImportError as e:
    print(f"[FEHLER] J2534 API nicht verfuegbar: {e}")
    print("Installiert mit: pip3 install -e /tmp/Python-J2534-Interface")
    input("\nENTER zum Beenden")
    sys.exit(1)

print()

# 1. Geraete auflisten
print("[1] Suche J2534 Geraete...")
try:
    devices = get_list_j2534_devices()
    if devices:
        print(f"    [OK] {len(devices)} Geraete gefunden:")
        for i, dev in enumerate(devices):
            print(f"      [{i}] {dev}")
    else:
        print("    [FEHLER] Keine J2534 Geraete gefunden!")
        print("    Der MINI-VCI hat wahrscheinlich keinen Mac-Treiber.")
        print("    J2534 benoetigt eine .dylib oder .so vom Hersteller.")
        print()
        print("    Moegliche Loesungen:")
        print("      1. ELM327 Adapter kaufen (empfohlen)")
        print("      2. Windows-VM mit Techstream verwenden")
        print("      3. Alternative Firmware auf MINI-VCI flashen")
        input("\nENTER zum Beenden")
        sys.exit(1)
except Exception as e:
    print(f"    [FEHLER] {e}")
    input("\nENTER zum Beenden")
    sys.exit(1)

# 2. Mit erstem Geraet verbinden
print()
print("[2] Verbinde mit J2534 Geraet...")
try:
    set_j2534_device_to_connect(devices[0])
    pt_open()
    print("    [OK] PassThru Interface geoeffnet")
except Exception as e:
    print(f"    [FEHLER] {e}")
    input("\nENTER zum Beenden")
    sys.exit(1)

# 3. CAN Verbindung fuer Dodge Challenger
print()
print("[3] Verbinde mit Dodge Challenger CAN...")
print("    Protokoll: ISO 15765-4 CAN (11-bit, 500 kbit/s)")

try:
    # CAN 11-bit, 500 kbps - Dodge Challenger 2010
    channel_id = pt_connect(
        ProtocolFlags.CAN,
        BaudRates.CAN_500KBPS,
        PassThruFlags.CAN_11BIT_ID
    )
    print(f"    [OK] CAN Kanal geoeffnet (ID: {channel_id})")
except Exception as e:
    print(f"    [FEHLER] {e}")
    pt_close()
    input("\nENTER zum Beenden")
    sys.exit(1)

# 4. OBD-II Request senden
print()
print("[4] Sende OBD-II Request (RPM = 010C)...")
try:
    # OBD-II CAN Frame: ID 0x7DF, Daten: 02 01 0C (RPM Request)
    msg = {
        'TxFlags': 0,
        'ProtocolID': ProtocolFlags.CAN,
        'Data': [0x02, 0x01, 0x0C],
        'ExtraDataIndex': 0,
        'RxStatus': 0,
    }
    pt_write_msgs(channel_id, [msg], timeout=1000)
    print("    [OK] Request gesendet")
    
    # Antwort lesen
    responses = pt_read_msgs(channel_id, num_msgs=10, timeout=2000)
    if responses:
        print(f"    [OK] {len(responses)} Antwort(en) erhalten:")
        for r in responses:
            print(f"      -> {r}")
    else:
        print("    [INFO] Keine Antwort (Zündung AUS oder kein ECU)")
except Exception as e:
    print(f"    [FEHLER] {e}")

# 5. Aufräumen
print()
print("[5] Schliesse Verbindung...")
try:
    pt_disconnect(channel_id)
    pt_close()
    print("    [OK] Verbindung geschlossen")
except Exception as e:
    print(f"    [FEHLER] {e}")

print()
print("=" * 65)
print("  J2534 TEST ABGESCHLOSSEN")
print("=" * 65)
input("\nENTER zum Beenden")
