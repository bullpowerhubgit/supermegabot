"""
Dodge Challenger 3.5L V6 — OBD2 Diagnose Tool
ELM327 Bluetooth
"""

import obd
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Zylinder-Layout 3.5L V6 ──────────────────────────────────────────────────
CYLINDER_MAP = {
    1: "Vorne Links  (Bank 1)",
    2: "Vorne Mitte  (Bank 1)",
    3: "Vorne Rechts (Bank 1)",
    4: "Hinten Links  (Bank 2)",
    5: "Hinten Mitte  (Bank 2)",
    6: "Hinten Rechts (Bank 2)",
}

# ── Bekannte Fehlercodes für Challenger 3.5L V6 ──────────────────────────────
CHALLENGER_DTCS = {
    "P0201": ("Injektor Zylinder 1 — Stromkreis offen",      "KRITISCH"),
    "P0202": ("Injektor Zylinder 2 — Stromkreis offen",      "KRITISCH"),
    "P0203": ("Injektor Zylinder 3 — Stromkreis offen",      "KRITISCH"),
    "P0204": ("Injektor Zylinder 4 — Stromkreis offen",      "KRITISCH"),
    "P0205": ("Injektor Zylinder 5 — Stromkreis offen",      "KRITISCH"),
    "P0206": ("Injektor Zylinder 6 — Stromkreis offen",      "KRITISCH"),
    "P0219": ("Motordrehzahl zu hoch",                        "WARNUNG"),
    "P0220": ("Drosselklappen-Sensor B — Fehler",             "WARNUNG"),
    "P0300": ("Zündaussetzer — mehrere Zylinder",             "KRITISCH"),
    "P0301": ("Zündaussetzer Zylinder 1",                     "KRITISCH"),
    "P0302": ("Zündaussetzer Zylinder 2",                     "KRITISCH"),
    "P0303": ("Zündaussetzer Zylinder 3",                     "KRITISCH"),
    "P0304": ("Zündaussetzer Zylinder 4",                     "KRITISCH"),
    "P0305": ("Zündaussetzer Zylinder 5",                     "KRITISCH"),
    "P0306": ("Zündaussetzer Zylinder 6",                     "KRITISCH"),
    "P0335": ("Kurbelwellensensor A — kein Signal",           "KRITISCH"),
    "P0340": ("Nockenwellensensor A — kein Signal",           "KRITISCH"),
    "P0341": ("Nockenwellensensor A — Bereich/Performance",   "WARNUNG"),
    "P0344": ("Nockenwellensensor A — Signal unterbrochen",   "WARNUNG"),
    "P0562": ("Systemspannung zu niedrig",                    "WARNUNG"),
    "P0601": ("PCM Speicherfehler",                           "KRITISCH"),
    "P0700": ("Getriebesteuerung — Fehler",                   "WARNUNG"),
    "P1128": ("Closed Loop — Bank 1 zu mager",                "WARNUNG"),
    "P1129": ("Closed Loop — Bank 2 zu mager",                "WARNUNG"),
}

# ── Live-Daten Kanäle ─────────────────────────────────────────────────────────
LIVE_COMMANDS = [
    (obd.commands.RPM,              "Drehzahl (RPM)"),
    (obd.commands.SPEED,            "Geschwindigkeit"),
    (obd.commands.COOLANT_TEMP,     "Kühlmittel Temp"),
    (obd.commands.INTAKE_TEMP,      "Ansaugluft Temp"),
    (obd.commands.THROTTLE_POS,     "Drosselklappe %"),
    (obd.commands.ENGINE_LOAD,      "Motorlast %"),
    (obd.commands.SHORT_FUEL_TRIM_1,"Kraftstoff Trim Bank1"),
    (obd.commands.SHORT_FUEL_TRIM_2,"Kraftstoff Trim Bank2"),
    (obd.commands.O2_B1S1,          "Lambda Bank1 Sensor1"),
    (obd.commands.O2_B2S1,          "Lambda Bank2 Sensor1"),
    (obd.commands.TIMING_ADVANCE,   "Zündzeitpunkt"),
    (obd.commands.MAF,              "Luftmassenmesser"),
]


class ChallengerOBD:
    def __init__(self, port=None, baudrate=38400):
        """
        port=None → automatische Suche
        port='/dev/tty.OBDII' → manuell (Mac Bluetooth)
        port='COM5' → Windows
        """
        self.port = port
        self.baudrate = baudrate
        self.connection = None

    def connect(self):
        print("\n🔌 Verbinde mit ELM327 Bluetooth...")
        try:
            if self.port:
                self.connection = obd.OBD(self.port, baudrate=self.baudrate)
            else:
                self.connection = obd.OBD(baudrate=self.baudrate)

            if self.connection.is_connected():
                print("✅ Verbunden mit ELM327!")
                print(f"   Port: {self.connection.port_name()}")
                return True
            else:
                print("❌ Verbindung fehlgeschlagen")
                return False
        except Exception as e:
            print(f"❌ Fehler: {e}")
            return False

    def disconnect(self):
        if self.connection:
            self.connection.close()
            print("🔌 Getrennt")

    # ── Fehlercodes ──────────────────────────────────────────────────────────

    def read_dtcs(self):
        print("\n🔍 Lese Fehlercodes...")
        response = self.connection.query(obd.commands.GET_DTC)
        if response.is_null():
            print("✅ Keine Fehlercodes!")
            return []

        dtcs = response.value
        results = []
        for code, description in dtcs:
            code_str = str(code)
            known = CHALLENGER_DTCS.get(code_str, (description or "Unbekannt", "INFO"))
            results.append({
                "code": code_str,
                "description": known[0],
                "severity": known[1],
                "raw": description,
            })

        self._print_dtcs(results)
        return results

    def clear_dtcs(self):
        print("\n🗑️  Lösche Fehlercodes...")
        response = self.connection.query(obd.commands.CLEAR_DTC)
        if response.is_null():
            print("✅ Fehlercodes gelöscht!")
            return True
        print("⚠️  Löschen möglicherweise fehlgeschlagen")
        return False

    def _print_dtcs(self, dtcs):
        if not dtcs:
            print("✅ Keine Fehlercodes!")
            return
        print(f"\n{'='*55}")
        print(f"  ⚠️  {len(dtcs)} FEHLERCODE(S) GEFUNDEN")
        print(f"{'='*55}")
        for d in dtcs:
            icon = "🔴" if d["severity"] == "KRITISCH" else "🟡"
            print(f"\n  {icon} {d['code']} [{d['severity']}]")
            print(f"     {d['description']}")
            # Spezifische Tipps für bekannte Codes
            if d["code"] in ("P0335", "P0340", "P0341"):
                print("     → Tipp: Kurbelwellen/Nockenwellen Relearn durchführen!")
            elif d["code"].startswith("P020"):
                zyl = int(d["code"][-1])
                print(f"     → Zylinder {zyl}: {CYLINDER_MAP.get(zyl, '?')}")
                print("     → Stecker prüfen, Kabel auf Beschädigung kontrollieren")
        print(f"\n{'='*55}")

    # ── Live Daten ───────────────────────────────────────────────────────────

    def live_data(self, interval=2, duration=30):
        print(f"\n📊 Live-Daten für {duration}s (Intervall: {interval}s)")
        print(f"   Dodge Challenger 3.5L V6")
        print(f"{'='*55}")

        start = time.time()
        while time.time() - start < duration:
            print(f"\n  ⏱️  {datetime.now().strftime('%H:%M:%S')}")
            for cmd, label in LIVE_COMMANDS:
                try:
                    resp = self.connection.query(cmd)
                    if not resp.is_null():
                        print(f"  {label:30s}: {resp.value}")
                except Exception:
                    pass
            print(f"  {'─'*50}")
            time.sleep(interval)

    # ── Relearn Assistent ────────────────────────────────────────────────────

    def relearn_assistant(self):
        print("""
╔══════════════════════════════════════════════════╗
║   KURBELWELLEN RELEARN — Dodge Challenger 3.5L   ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  SCHRITT 1: Motor kalt starten                   ║
║  SCHRITT 2: 10 Min im Leerlauf warmlaufen        ║
║  SCHRITT 3: 3x von 0 auf 100 km/h (Vollgas)     ║
║  SCHRITT 4: Motor aus → 30 Sek → starten         ║
║  SCHRITT 5: Fehlercodes prüfen                   ║
║                                                  ║
║  ACHTUNG: Auf freier Strecke durchführen!        ║
╚══════════════════════════════════════════════════╝
        """)
        input("  Drücke ENTER wenn bereit für Schritt 1...")
        print("  ✅ Starte Motor und warte 10 Minuten...")
        input("  Drücke ENTER nach 10 Min Leerlauf...")
        print("  ✅ Jetzt 3x Vollgas 0→100 km/h!")
        input("  Drücke ENTER nach Fahrprozedur...")
        print("  ✅ Motor aus → 30 Sek warten → starten")
        input("  Drücke ENTER nach Neustart...")
        print("\n  🔍 Prüfe Fehlercodes nach Relearn...")
        self.read_dtcs()

    # ── Injektor Test ────────────────────────────────────────────────────────

    def injector_check(self):
        print("""
╔══════════════════════════════════════════════════╗
║   INJEKTOR CHECK — 3.5L V6                       ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  Zylinder Layout:                                ║
║                                                  ║
║  VORNE                                           ║
║  [1] [2] [3]  ← linke Bank                      ║
║  [4] [5] [6]  ← rechte Bank                     ║
║                                                  ║
║  P0201 → Zylinder 1 (Vorne Links)               ║
║  Stecker: Schwarzer 2-poliger Stecker            ║
║  Widerstand Injektor: 12-16 Ohm                 ║
║                                                  ║
╚══════════════════════════════════════════════════╝
        """)
        dtcs = self.read_dtcs()
        injektor_codes = [d for d in dtcs if d["code"].startswith("P020")]
        if injektor_codes:
            print(f"\n  ⚠️  {len(injektor_codes)} Injektor-Fehler gefunden!")
            for d in injektor_codes:
                zyl = int(d["code"][-1])
                print(f"\n  🔴 Zylinder {zyl} — {CYLINDER_MAP[zyl]}")
                print("     → Stecker abziehen und fest wieder einstecken")
                print("     → Kabel auf Risse/Quetschungen prüfen")
                print("     → Widerstand messen: 12-16 Ohm (Multimeter)")
        else:
            print("  ✅ Keine Injektor-Fehler!")

    # ── Schnell-Diagnose ─────────────────────────────────────────────────────

    def full_diagnosis(self):
        print("""
╔══════════════════════════════════════════════════╗
║   DODGE CHALLENGER 3.5L V6 — VOLLDIAGNOSE       ║
╚══════════════════════════════════════════════════╝
        """)
        print(f"  Datum: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        print(f"  Fahrzeug: Dodge Challenger 2010 — 3.5L V6\n")

        dtcs = self.read_dtcs()

        print("\n📊 Basis Live-Daten:")
        for cmd, label in LIVE_COMMANDS[:5]:
            try:
                resp = self.connection.query(cmd)
                if not resp.is_null():
                    print(f"  {label:30s}: {resp.value}")
            except Exception:
                pass

        print(f"\n{'='*55}")
        print(f"  ZUSAMMENFASSUNG:")
        print(f"  Fehlercodes: {len(dtcs)}")
        kritisch = [d for d in dtcs if d["severity"] == "KRITISCH"]
        if kritisch:
            print(f"  🔴 Kritisch: {len(kritisch)}")
        print(f"{'='*55}\n")


# ── Interaktives Menü ────────────────────────────────────────────────────────

def main():
    print("""
╔══════════════════════════════════════════════════╗
║   🚗 DODGE CHALLENGER OBD DIAGNOSE TOOL         ║
║      3.5L V6 — ELM327 Bluetooth                 ║
╚══════════════════════════════════════════════════╝
    """)

    car = ChallengerOBD()
    if not car.connect():
        print("\n  Tipp: Bluetooth koppeln → PIN 1234 oder 0000")
        print("  Mac: /dev/tty.OBDII oder /dev/tty.ELM327")
        return

    while True:
        print("""
  ┌─────────────────────────────────┐
  │  MENÜ                           │
  │  1. Fehlercodes lesen           │
  │  2. Fehlercodes löschen         │
  │  3. Live-Daten anzeigen         │
  │  4. Volldiagnose                │
  │  5. Relearn Assistent           │
  │  6. Injektor Check              │
  │  0. Beenden                     │
  └─────────────────────────────────┘
        """)
        choice = input("  Auswahl: ").strip()

        if choice == "1":
            car.read_dtcs()
        elif choice == "2":
            car.clear_dtcs()
        elif choice == "3":
            car.live_data()
        elif choice == "4":
            car.full_diagnosis()
        elif choice == "5":
            car.relearn_assistant()
        elif choice == "6":
            car.injector_check()
        elif choice == "0":
            car.disconnect()
            break
        else:
            print("  Ungültige Auswahl")


if __name__ == "__main__":
    main()
