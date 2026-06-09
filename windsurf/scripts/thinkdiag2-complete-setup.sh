#!/bin/bash
# ThinkDiag 2 Komplett-Setup fuer MacOS
# Laedt BlueStacks herunter, installiert ThinkDiag+, richtet alles ein

set -e

echo "=========================================="
echo "  ThinkDiag 2 - macOS Setup"
echo "  Automatische Installation"
echo "=========================================="
echo ""

# Farben fuer Ausgabe
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. Pruefe ob BlueStacks installiert
if [ -d "/Applications/BlueStacks.app" ]; then
    echo -e "${GREEN}[OK] BlueStacks ist bereits installiert${NC}"
    BLUESTACKS_INSTALLED=true
else
    echo -e "${YELLOW}[INFO] BlueStacks ist NICHT installiert${NC}"
    BLUESTACKS_INSTALLED=false
fi

# 2. Pruefe System
ARCH=$(uname -m)
echo "[INFO] System-Architektur: $ARCH"

if [ "$ARCH" = "arm64" ]; then
    echo "[INFO] Apple Silicon (M1/M2/M3/M4) erkannt"
    BLUESTACKS_URL="https://cdn3.bluestacks.com/downloads/mac/5.21.650.7432/625b8f713612c7fa3ee5b4f5/BlueStacksInstaller_5.21.650.7432.dmg"
    echo "[INFO] ARM64 Version wird benoetigt"
else
    echo "[INFO] Intel Mac erkannt"
    BLUESTACKS_URL="https://cdn3.bluestacks.com/downloads/mac/5.21.650.7432/625b8f713612c7fa3ee5b4f5/BlueStacksInstaller_5.21.650.7432.dmg"
fi

# 3. BlueStacks Download und Installation
if [ "$BLUESTACKS_INSTALLED" = false ]; then
    echo ""
    echo "=========================================="
    echo "  BLUESTACKS DOWNLOAD & INSTALLATION"
    echo "=========================================="
    echo ""
    
    DOWNLOAD_DIR="$HOME/Downloads"
    DMG_FILE="$DOWNLOAD_DIR/BlueStacks.dmg"
    
    # Pruefe ob DMG schon existiert
    if [ -f "$DMG_FILE" ]; then
        echo -e "${GREEN}[OK] BlueStacks.dmg bereits heruntergeladen${NC}"
    else
        echo "[1] Lade BlueStacks herunter..."
        echo "    Dies kann 2-5 Minuten dauern (~600MB)"
        echo "    URL: $BLUESTACKS_URL"
        echo ""
        
        # Versuche Download
        if command -v curl &> /dev/null; then
            curl -L -o "$DMG_FILE" "$BLUESTACKS_URL" --progress-bar || {
                echo -e "${RED}[FEHLER] Download fehlgeschlagen${NC}"
                echo "    Bitte manuell herunterladen:"
                echo "    https://www.bluestacks.com/download.html"
                echo ""
                read -p "ENTER wenn manuell heruntergeladen..."
            }
        else
            echo "[INFO] Oeffne Download-Seite im Browser..."
            open "https://www.bluestacks.com/download.html"
            echo ""
            echo "    BITTE MANUELL HERUNTERLADEN:"
            echo "    1. Warte bis Download fertig ist"
            echo "    2. DMG Datei oeffnen"
            echo "    3. BlueStacks in Applications ziehen"
            echo ""
            read -p "ENTER wenn Installation abgeschlossen..."
        fi
    fi
    
    # Versuche automatische Installation
    if [ -f "$DMG_FILE" ]; then
        echo ""
        echo "[2] Installiere BlueStacks..."
        
        # Mounte DMG
        MOUNT_POINT=$(hdiutil attach "$DMG_FILE" -nobrowse | grep "/Volumes" | awk '{print $3}')
        
        if [ -n "$MOUNT_POINT" ]; then
            echo "    [OK] DMG gemountet: $MOUNT_POINT"
            
            # Kopiere zu Applications
            if [ -d "$MOUNT_POINT/BlueStacks.app" ]; then
                echo "    [OK] BlueStacks.app gefunden"
                echo "    Kopiere zu Applications..."
                cp -R "$MOUNT_POINT/BlueStacks.app" /Applications/
                echo -e "${GREEN}[OK] BlueStacks installiert!${NC}"
            fi
            
            # Unmount
            hdiutil detach "$MOUNT_POINT" -force &> /dev/null
        fi
    fi
    
    # Pruefe nochmal
    if [ ! -d "/Applications/BlueStacks.app" ]; then
        echo -e "${RED}[FEHLER] Automatische Installation fehlgeschlagen${NC}"
        echo ""
        echo "    MANUELLE INSTALLATION:"
        echo "    1. Oeffne $DMG_FILE (oder lade neu herunter)"
        echo "    2. Ziehe BlueStacks in Applications"
        echo "    3. Starte BlueStacks"
        echo ""
        read -p "ENTER wenn manuell installiert..."
    fi
fi

# 4. Starte BlueStacks
if [ -d "/Applications/BlueStacks.app" ]; then
    echo ""
    echo "=========================================="
    echo "  BLUESTACKS STARTEN"
    echo "=========================================="
    echo ""
    
    echo "[3] Starte BlueStacks..."
    open -a BlueStacks
    echo -e "${GREEN}[OK] BlueStacks gestartet!${NC}"
    echo ""
    echo "    Warte 30-60 Sekunden bis BlueStacks geladen ist..."
    sleep 5
    
    echo ""
    echo "=========================================="
    echo "  THINKDIAG+ APP INSTALLATION"
    echo "=========================================="
    echo ""
    
    echo "[4] Naechste Schritte MANUELL in BlueStacks:"
    echo ""
    echo "    1. Google-Konto einrichten (falls gefragt)"
    echo "    2. Play Store oeffnen (App-Symbol)"
    echo "    3. Suche nach: 'ThinkDiag+'"
    echo "    4. Klicke 'Installieren'"
    echo "    5. Warte bis Installation fertig ist"
    echo ""
    echo "[5] Bluetooth aktivieren in BlueStacks:"
    echo "    1. Klicke das Zahnrad (Einstellungen)"
    echo "    2. Gehe zu 'Advanced' oder 'Geraete'"
    echo "    3. Aktiviere 'Bluetooth'"
    echo "    4. Schliesse Einstellungen"
    echo ""
    
    read -p "ENTER wenn ThinkDiag+ installiert und Bluetooth aktiviert..."
    
    echo ""
    echo "=========================================="
    echo "  FAHRZEUG-DIAGNOSE"
    echo "=========================================="
    echo ""
    
    echo "[6] ThinkDiag+ oeffnen und einrichten:"
    echo ""
    echo "    1. Starte ThinkDiag+ App"
    echo "    2. Akzeptiere AGB / Registriere dich"
    echo "    3. Klicke 'Diagnose' oder 'Scan'"
    echo "    4. Waehle Marke: 'Dodge'"
    echo "    5. Waehle Modell: 'Challenger'"
    echo "    6. Waehle Jahr: '2010'"
    echo "    7. Klicke 'Verbinden' oder 'Diagnose starten'"
    echo ""
    
    echo "[7] ThinkDiag 2 verbinden:"
    echo "    1. Stecke ThinkDiag 2 in OBD-Port (unterm Armaturenbrett)"
    echo "    2. Zündung auf ON (nicht starten!)"
    echo "    3. Warte bis ThinkDiag 2 LED blinkt"
    echo "    4. In App: Klicke 'Bluetooth verbinden'"
    echo "    5. Waehle 'ThinkDiag' oder 'TD2' aus der Liste"
    echo ""
    
    echo "[8] Diagnose durchfuehren:"
    echo "    - Lese Fehlercodes (DTC)"
    echo "    - Pruefe Live-Daten (RPM, Spannung)"
    echo "    - Fuelle-Level, Zündung etc."
    echo ""
    
    echo "=========================================="
    echo -e "${GREEN}  ThinkDiag+ ist DIE Software fuer deinen Adapter!${NC}"
    echo "  Du kannst jetzt deinen Dodge Challenger diagnostizieren."
    echo "=========================================="
else
    echo -e "${RED}[FEHLER] BlueStacks nicht gefunden${NC}"
    echo "    Bitte installiere BlueStacks manuell:"
    echo "    https://www.bluestacks.com/download.html"
fi

echo ""
echo "[INFO] Zusaetzliche Desktop-Buttons erstellt in:"
echo "    ~/Desktop/OBD-Tools/"
echo ""

# Erstelle Desktop-Buttons fuer schnellen Zugriff
DESKTOP_DIR="$HOME/Desktop/OBD-Tools"
mkdir -p "$DESKTOP_DIR"

# Button 1: BlueStacks starten
cat > "$DESKTOP_DIR/Start-BlueStacks.app" << 'EOF'
#!/usr/bin/env bash
open -a BlueStacks
EOF
chmod +x "$DESKTOP_DIR/Start-BlueStacks.app"

echo -e "${GREEN}[OK] Setup abgeschlossen!${NC}"
echo ""
read -p "ENTER zum Beenden"
