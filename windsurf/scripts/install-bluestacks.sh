#!/bin/bash
# BlueStacks Installer fuer Mac + ThinkDiag+ App Setup

echo "=========================================="
echo "  BlueStacks + ThinkDiag+ Setup"
echo "=========================================="
echo ""

# Pruefe ob BlueStacks schon installiert ist
if [ -d "/Applications/BlueStacks.app" ]; then
    echo "[OK] BlueStacks ist bereits installiert"
else
    echo "[1] Lade BlueStacks herunter..."
    echo "    URL: https://cdn3.bluestacks.com/downloads/mac/5.21.650.7432/625b8f713612c7fa3ee5b4f5/BlueStacksInstaller_5.21.650.7432.dmg"
    echo ""
    echo "    MANUELL herunterladen:"
    echo "    1. https://www.bluestacks.com/download.html"
    echo "    2. .dmg Datei oeffnen"
    echo "    3. BlueStacks in Applications ziehen"
    echo ""
    read -p "Druecke ENTER wenn BlueStacks installiert ist..."
fi

echo ""
echo "[2] Starte BlueStacks..."
open -a BlueStacks

echo ""
echo "[3] Naechste Schritte MANUELL in BlueStacks:"
echo "    1. Google-Konto einrichten"
echo "    2. Play Store oeffnen"
echo "    3. 'ThinkDiag+' suchen"
echo "    4. App installieren"
echo "    5. App starten"
echo ""
echo "[4] Bluetooth in BlueStacks aktivieren:"
echo "    - BlueStacks Einstellungen (Zahnrad)"
echo "    - 'Bluetooth' aktivieren"
echo "    - ThinkDiag 2 pairen"
echo ""

echo "=========================================="
echo "  ThinkDiag+ in BlueStacks nutzen:"
echo "=========================================="
echo ""
echo "  1. ThinkDiag 2 in OBD-Port stecken"
echo "  2. Auto-Zuendung auf ON"
echo "  3. In ThinkDiag+ App:"
echo "     - 'Dodge' waehlen"
echo "     - 'Challenger' waehlen"
echo "     - '2010' waehlen"
echo "     - 'Diagnose' starten"
echo ""
echo "  Du kannst dann Fehlercodes lesen!"
echo "=========================================="
echo ""
read -p "ENTER zum Beenden"
