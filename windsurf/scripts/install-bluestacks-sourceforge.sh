#!/bin/bash
# BlueStacks Air for Mac - SourceForge Download

set -e

echo "=========================================="
echo "  BLUESTACKS AIR DOWNLOAD (SourceForge)"
echo "=========================================="
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ -d "/Applications/BlueStacks.app" ]; then
    echo -e "${GREEN}[OK] BlueStacks ist bereits installiert${NC}"
    open -a BlueStacks
    exit 0
fi

echo -e "${YELLOW}[INFO] BlueStacks Air wird heruntergeladen...${NC}"
echo "Dies kann 5-10 Minuten dauern (ca. 600MB)"
echo ""

cd ~/Downloads
curl -L -o BlueStacks_Air.dmg "https://sourceforge.net/projects/bluestacks-air/files/BlueStacks_5.21.670.7509.dmg/download" 2>&1 | tail -30

echo ""
echo -e "${GREEN}[OK] Download abgeschlossen${NC}"
echo ""

# Pruefe Dateigroesse
SIZE=$(stat -f%z BlueStacks_Air.dmg 2>/dev/null || echo "0")
if [ "$SIZE" -lt 100000000 ]; then
    echo -e "${YELLOW}[WARNUNG] Datei ist zu klein ($SIZE Bytes)${NC}"
    echo "Bitte manuell herunterladen:"
    echo "https://sourceforge.net/projects/bluestacks-air/files/"
    exit 1
fi

# Mount und Install
echo "Mounting DMG..."
hdiutil attach BlueStacks_Air.dmg -nobrowse -quiet

echo "Installiere..."
cp -R /Volumes/BlueStacks*/BlueStacks*.app /Applications/ 2>/dev/null || cp -R /Volumes/BlueStacks*/BlueStacks.app /Applications/

hdiutil detach /Volumes/BlueStacks* -quiet

echo ""
echo -e "${GREEN}[OK] BlueStacks installiert${NC}"
echo ""

open -a BlueStacks

echo ""
echo "=========================================="
echo -e "${GREEN}  BLUESTACKS BEREIT!${NC}"
echo "=========================================="
echo ""
echo "Warte 30-60 Sekunden bis BlueStacks geladen ist."
echo "Dann:"
echo "  1. Play Store öffnen"
echo "  2. 'X-Diag' oder 'ThinkDiag+' suchen"
echo "  3. Installieren"
echo "  4. Dodge Challenger 2010 auswählen"
echo ""
