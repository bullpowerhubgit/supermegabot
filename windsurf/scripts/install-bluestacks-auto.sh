#!/bin/bash
# BlueStacks Auto-Install für Mac

set -e

echo "=========================================="
echo "  BLUESTACKS AUTO-INSTALL"
echo "=========================================="
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Pruefe ob BlueStacks schon installiert ist
if [ -d "/Applications/BlueStacks.app" ]; then
    echo -e "${GREEN}[OK] BlueStacks ist bereits installiert${NC}"
    open -a BlueStacks
    exit 0
fi

echo -e "${YELLOW}[INFO] BlueStacks wird heruntergeladen...${NC}"
echo ""

# Download BlueStacks
cd ~/Downloads
curl -L -o BlueStacks.dmg "https://cdn3.bluestacks.com/mac/downloads/Bluestacks.dmg" 2>&1 | tail -20

echo ""
echo -e "${GREEN}[OK] Download abgeschlossen${NC}"
echo ""

# Mount DMG
echo "Mounting DMG..."
hdiutil attach BlueStacks.dmg -nobrowse -quiet

# Installiere
echo "Installiere BlueStacks..."
cp -R /Volumes/BlueStacks/BlueStacks.app /Applications/

# Unmount
hdiutil detach /Volumes/BlueStacks -quiet

echo ""
echo -e "${GREEN}[OK] BlueStacks installiert${NC}"
echo ""

# Starte BlueStacks
echo "Starte BlueStacks..."
open -a BlueStacks

echo ""
echo "=========================================="
echo -e "${GREEN}  BLUESTACKS BEREIT!${NC}"
echo "=========================================="
echo ""
echo "Warte 30-60 Sekunden bis BlueStacks geladen ist."
echo "Dann öffne den Play Store und installiere:"
echo "  - X-Diag Pro (oder ThinkDiag+)"
echo ""
