#!/usr/bin/env python3
"""
Dodge Challenger 2010 V6 - Startprobleme Diagnose
Anlasser dreht, Motor springt nicht an
Chrysler EGJ/EGT 3.5L V6 SOHC
"""

print("=" * 65)
print("  DODGE CHALLENGER 2010 V6")
print("  STARTPROBLEM: Anlasser dreht, Motor springt nicht an")
print("=" * 65)
print()

# Checkliste
steps = [
    ("1. FEHLERCODES AUSLESEN (Prioritaet #1)", [
        "OBD2 Dongle anschliessen",
        "Zuendung auf ON (nicht starten)",
        "Fehlercodes mit python-OBD oder obd-node auslesen",
        "-> Wenn P0300-P0306: Zuendspulen/Kerzen pruefen",
        "-> Wenn P0335/P0339: Kurbelwellensensor (CKP) defekt!",
        "-> Wenn P0340/P0344: Nockenwellensensor (CMP) defekt!",
        "-> Wenn P1004-P1007: Saugrohrklappe (IMRC) blockiert",
        "-> Wenn P0456/P0457: Tankdeckel/EVAP (kein Startgrund)",
        "-> Wenn U110C: Kraftstoffpumpe/Sensor pruefen",
    ]),
    ("2. KRAFTSTOFFVERSORGUNG PRUEFEN", [
        "Zuendung auf ON, Ohren an Tank halten",
        "-> Hoert ihr ein leises Surren fuer 2-3 Sekunden?",
        "   JA = Kraftstoffpumpe laeuft",
        "   NEIN = Pumpe defekt, Relais oder Sicherung",
        "",
        "Kraftstoffdruck pruefen (wenn moeglich):",
        "-> Sollwert: ca. 3.5 bar (50 psi) bei Zuendung ON",
        "-> Am Spritleitung-Testanschluss (Schrader Valve)",
        "-> KEIN DRUCK = Pumpe, Filter oder Leitung verstopft",
    ]),
    ("3. ZUENDUNG PRUEFEN (3.5L V6 sehr anfaellig!)", [
        "ZUENDSPULEN (sehr haeufige Ursache beim 3.5L!):",
        "-> Motor laufen lassen, eine Zuendspule nach der anderen abziehen",
        "-> Wenn Motor schlechter laeuft = Spule OK",
        "-> Wenn KEIN Unterschied = Spule DEFEKT",
        "-> 6 Zylinder = 6 Zuendspulen (Coil-on-Plug)",
        "",
        "ZUENDKERZEN:",
        "-> Zustand pruefen (weiss/braun = normal, schwarz/fett = Problem)",
        "-> Electrodenabstand: 1.0 - 1.1 mm",
        "-> Wechselintervall: 48.000 km Copper / 160.000 km Iridium",
        "",
        "Zuendfunken testen (VORSICHT!):",
        "-> Kerze raus, an Masse halten, Anlasser betaetigen",
        "-> Blauer Funke = gut, Gelber/keiner = Zuendproblem",
    ]),
    ("4. SENSOREN PRUEFEN (PCM braucht Signale)", [
        "KURBELWELLENSENSOR (CKP) - Position: Kurbelgehaeuse unten",
        "-> Defekt = PCM weiss nicht, dass Motor dreht = KEIN Start",
        "-> OBD Code: P0335, P0339",
        "-> Testen mit Multimeter: 200-900 Ohm (bei 20°C)",
        "",
        "NOCKENWELLENSENSOR (CMP) - Position: Zylinderkopf hinten",
        "-> Defekt = falsche Zuendzeitpunkt",
        "-> OBD Code: P0340, P0344",
        "-> Sehr schwierig zu erreichen beim 3.5L!",
        "",
        "SAUGROHRKLAPPE (IMRC / Short Runner Valve)",
        "-> Typisch fuer 3.5L V6: P1004, P1005, P2004",
        "-> Wenn blockiert: falscher Luft/Fuel Mix = kein Start",
        "-> IMRC-Aktuator am Saugrohr pruefen (Kabel ziehen)",
    ]),
    ("5. SICHERUNGEN & RELAIS", [
        "SICHERUNGSBOX MOTORRAUM (PDM - Power Distribution Module):",
        "-> Sicherung #18: Kraftstoffpumpe (20A)",
        "-> Sicherung #19: Motorsteuerung (20A)",
        "-> Sicherung #20: Zuendspulen (15A)",
        "-> Sicherung #25: Anlasser (10A)",
        "",
        "RELAIS:",
        "-> Relais K1: Kraftstoffpumpe",
        "-> Relais K3: Anlasser",
        "-> Relais K11: Zusaetzliche Luftpumpe (sekundaer)",
        "",
        "WICHTIG: PDM ist bekannt fuer KORROSION!",
        "-> Sicherungskasten oeffnen, Kontakte pruefen",
        "-> Gruene/gelbe Korrosion = saubern oder ersetzen",
    ]),
    ("6. KOMPRESSION TESTEN", [
        "Wenn Zündung + Kraftstoff OK:",
        "-> Alle Zuendkerzen raus",
        "-> Kompressionsmesser in Zylinder 1",
        "-> Anlasser betaetigen (Gaspedal ganz durchgedrückt)",
        "-> Sollwerte 3.5L V6:",
        "   - Neu:      12-14 bar (170-200 psi)",
        "   - Minimal:   9 bar (130 psi)",
        "   - Max Diff:  25% zwischen Zylindern",
        "-> NIEDRIG = Ventile, Kolbenringe oder Kopfdichtung",
    ]),
    ("7. MOTOR STEUERKETTE (3.5L V6)", [
        "Die 3.5L V6 hat eine STEUERKETTE (kein Riemen):",
        "-> Sollte eigentlich HALTEN (Kettenantrieb)",
        "-> Bei Kettensprung: Motor dreht schneller (frei)",
        "-> Kompressionstest zeigt 0 bei betroffenen Zylindern",
        "-> Selten, aber moeglich bei hoher Laufleistung",
    ]),
]

for title, items in steps:
    print(title)
    print("-" * 65)
    for item in items:
        print("  " + item)
    print()

# Haeufige Startprobleme 3.5L V6
print("=" * 65)
print("  TOP 5 URSACHEN fuer 'Anlasser dreht, Motor springt nicht an'")
print("  bei Dodge Challenger 2010 3.5L V6")
print("=" * 65)
print()

top5 = [
    ("#1", "Zuendspulen (Coil-on-Plug)", "40%", "P0301-P0306, ruckelnder Lauf"),
    ("#2", "Kurbelwellensensor (CKP)", "20%", "P0335, P0339, Motor dreht normal"),
    ("#3", "Kraftstoffpumpe / Relais", "15%", "Kein Surren beim Zuendung ON"),
    ("#4", "Saugrohrklappe (IMRC)", "10%", "P1004-P1007, P2004"),
    ("#5", "Sicherungskasten Korrosion (PDM)", "10%", "Intermittierend, zufaellige Codes"),
]

for rank, name, pct, hint in top5:
    print(f"  {rank} {name}")
    print(f"      Wahrscheinlichkeit: ~{pct}")
    print(f"      Hinweis: {hint}")
    print()

print("=" * 65)
print("  EMPFEHLUNG: Starte mit Fehlercode-Auslese!")
print("  python-OBD:  connection = obd.OBD('/dev/tty.usbserial-*')")
print("  Oder:        Doppelklick auf Dodge-Challenger-2010-OBD.app")
print("=" * 65)
print()
print("Druecke ENTER zum Beenden")
input()
