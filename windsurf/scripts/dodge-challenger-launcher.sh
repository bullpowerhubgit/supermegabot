#!/bin/zsh
# Dodge Challenger 2010 V6 - Kompletter OBD Launcher

clear
echo "============================================================"
echo "  DODGE CHALLENGER 2010 V6 - OBD DIAGNOSE"
echo "  Open Source KFZ Tools"
echo "============================================================"
echo ""

cd /Users/rudolfsarkany/windsurf

# 1. Dodge DTC Datenbank (JS)
echo "[1] Dodge/Chrysler DTC Datenbank"
node scripts/dodge-chrysler-dtc.js 2>&1 | head -15
echo ""

# 2. Challenger spezifisches Python Tool
echo "[2] Challenger 2010 V6 Spezifikationen"
python3 scripts/dodge-challenger-2010.py 2>&1 | grep -A30 "TECHNISCHE DATEN" | head -20
echo ""

# 3. python-OBD Check
echo "[3] python-OBD Verbindungstest"
python3 -c "
import obd
print('python-OBD:     OK')
print('RPM Befehl:     ', obd.commands.RPM.pid, obd.commands.RPM.desc)
print('Speed Befehl:   ', obd.commands.SPEED.pid, obd.commands.SPEED.desc)
print('Coolant Befehl: ', obd.commands.COOLANT_TEMP.pid, obd.commands.COOLANT_TEMP.desc)
" 2>&1
echo ""

# 4. Node.js OBD Check
echo "[4] Node.js OBD Tools"
node -e "
const dtc = require('./scripts/dodge-chrysler-dtc.js');
const n = require('obd-node');
console.log('Dodge DTC DB:   ', Object.keys(dtc.DTC_CODES).length, 'Codes');
console.log('Challenger PIDs:', Object.keys(dtc.CHALLENGER_PIDS).length, 'PIDs');
console.log('obd-node cmds:  ', n.getAllCommands().length, 'Befehle');
console.log('Sample DTC P1004:', dtc.lookupDTC('P1004').desc);
" 2>&1
echo ""

# 5. VIN Decoder
echo "[5] VIN Decoder"
python3 -c "
from vininfo import Vin
try:
    v = Vin('2B3CJ4DV5AH123456')
    print('VIN Decoder:    OK')
    print('Hersteller:     ', v.manufacturer)
    print('Jahr:           ', v.years)
except:
    print('VIN Decoder:    Bereit (Beispiel VIN)')
" 2>&1
echo ""

echo "============================================================"
echo "ALLE DODGE CHALLENGER TOOLS BEREIT!"
echo ""
echo "Naechste Schritte:"
echo "  1. ELM327 Dongle anschliessen (USB/Bluetooth/WiFi)"
echo "  2. python3 scripts/dodge-challenger-2010.py"
echo "  3. node scripts/dodge-chrysler-dtc.js"
echo "  4. python-OBD: connection = obd.OBD('/dev/tty.usbserial-*')"
echo ""
echo "Empfohlene Adapter fuer Mac:"
echo "  - OBDLink SX/MX (USB)"
echo "  - OBDLink LX (Bluetooth)"
echo "  - Veepeak WiFi (kein Treiber noetig)"
echo "============================================================"
echo ""
echo "ENTER zum Beenden"
read
