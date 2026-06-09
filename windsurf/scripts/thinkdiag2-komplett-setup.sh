#!/bin/bash
# ThinkDiag 2 - KOMPLETT SETUP
# BlueStacks + X-Diag Pro / ThinkDiag+ Installation

set -e

echo "=========================================="
echo "  THINKDIAG 2 - KOMPLETT SETUP"
echo "  BlueStacks + X-Diag Pro / ThinkDiag+"
echo "=========================================="
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 1. Pruefe BlueStacks
if [ -d "/Applications/BlueStacks.app" ]; then
    echo -e "${GREEN}[OK] BlueStacks ist bereits installiert${NC}"
else
    echo -e "${YELLOW}[INFO] BlueStacks wird benoetigt${NC}"
    echo ""
    echo "BlueStacks herunterladen:"
    echo "  https://www.bluestacks.com/download.html"
    echo ""
    echo "Nach Installation ENTER druecken..."
    read
fi

# 2. Starte BlueStacks
echo ""
echo "=========================================="
echo "  BLUESTACKS STARTEN"
echo "=========================================="
echo ""

open -a BlueStacks
echo -e "${GREEN}[OK] BlueStacks gestartet${NC}"
echo ""
echo "Warte 30-60 Sekunden bis BlueStacks geladen ist..."
sleep 5

# 3. Software-Auswahl
echo ""
echo "=========================================="
echo "  SOFTWARE AUSWAHL"
echo "=========================================="
echo ""
echo "Welche Software willst du nutzen?"
echo ""
echo "  [1] X-Diag Pro (Alternative, ThinkDiag 2 kompatibel)"
echo "  [2] ThinkDiag+ (Original Software)"
echo ""
read -p "Deine Wahl (1 oder 2): " choice

if [ "$choice" = "1" ]; then
    SOFTWARE="X-Diag Pro"
    APP_NAME="X-Diag"
    echo ""
    echo "=========================================="
    echo "  X-DIAG PRO INSTALLATION"
    echo "=========================================="
    echo ""
    echo "Schritte in BlueStacks:"
    echo "  1. Play Store oeffnen"
    echo "  2. Suche: 'X-Diag' oder 'Xdiag'"
    echo "  3. Installieren"
    echo "  4. App starten"
    echo "  5. Dodge Challenger 2010 auswaehlen"
    echo ""
elif [ "$choice" = "2" ]; then
    SOFTWARE="ThinkDiag+"
    APP_NAME="ThinkDiag+"
    echo ""
    echo "=========================================="
    echo "  THINKDIAG+ INSTALLATION"
    echo "=========================================="
    echo ""
    echo "Schritte in BlueStacks:"
    echo "  1. Play Store oeffnen"
    echo "  2. Suche: 'ThinkDiag+'"
    echo "  3. Installieren"
    echo "  4. App starten"
    echo "  5. Dodge Challenger 2010 auswaehlen"
    echo ""
else
    echo -e "${RED}[FEHLER] Ungueltige Wahl${NC}"
    exit 1
fi

read -p "ENTER wenn App installiert ist..."

# 4. Bluetooth aktivieren
echo ""
echo "=========================================="
echo "  BLUETOOTH AKTIVIEREN"
echo "=========================================="
echo ""
echo "In BlueStacks:"
echo "  1. Einstellungen (Zahnrad)"
echo "  2. Bluetooth aktivieren"
echo "  3. ThinkDiag 2 pairen"
echo ""
read -p "ENTER wenn Bluetooth aktiviert..."

# 5. Fahrzeug-Diagnose
echo ""
echo "=========================================="
echo "  FAHRZEUG-DIAGNOSE"
echo "=========================================="
echo ""
echo "Vorbereitung im Auto:"
echo "  1. ThinkDiag 2 in OBD-Port stecken"
echo "  2. Zündung auf ON (nicht starten)"
echo "  3. Warte bis LED blinkt"
echo ""
echo "In $SOFTWARE App:"
echo "  1. App starten"
echo "  2. 'Diagnose' oder 'Scan' waehlen"
echo "  3. Marke: Dodge"
echo "  4. Modell: Challenger"
echo "  5. Jahr: 2010"
echo "  6. 'Verbinden' klicken"
echo "  7. ThinkDiag 2 aus Bluetooth-Liste waehlen"
echo "  8. Diagnose starten"
echo ""

# 6. Fertig
echo "=========================================="
echo -e "${GREEN}  ALLES STARTBEREIT!${NC}"
echo "=========================================="
echo ""
echo "Du kannst jetzt:"
echo "  - Fehlercodes lesen"
echo "  - Live-Daten anzeigen"
echo "  - Spezielle Funktionen nutzen"
echo ""
echo "Viel Erfolg mit deinem Dodge Challenger 2010!"
echo "=========================================="

# Erstelle Desktop-Button fuer schnellen Start
DESKTOP_DIR="$HOME/Desktop/OBD-Tools"
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/Start-BlueStacks-$APP_NAME.sh" << EOF
#!/bin/bash
open -a BlueStacks
echo "BlueStacks gestartet"
echo "Oeffne $APP_NAME App"
EOF
chmod +x "$DESKTOP_DIR/Start-BlueStacks-$APP_NAME.sh"

echo ""
echo -e "${GREEN}[OK] Desktop-Button erstellt:${NC}"
echo "  $DESKTOP_DIR/Start-BlueStacks-$APP_NAME.sh"
echo ""

read -p "ENTER zum Beenden"
