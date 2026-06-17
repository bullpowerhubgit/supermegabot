#!/bin/zsh
# OBD-II KFZ Tools - Alle Open-Source Tools Starten
# JS + Python

clear
echo "============================================================"
echo "  OBD-II KFZ DIAGNOSE TOOLS - ALLE OPEN SOURCE"
echo "============================================================"
echo ""
echo "NODE.JS TOOLS:"
echo "  - obd-parser    v0.3.0  (Nachrichten-Parser)"
echo "  - obd-utils     v0.2.1  (PID-Liste & Decode)"
echo "  - obd-node      v1.0.0  (Kommunikation Engine)"
echo "  - obd2-over-serial        (Serial-Verbindung)"
echo ""
echo "PYTHON TOOLS:"
echo "  - python-OBD    v0.7.3  (ELM327 Scanner)"
echo "  - pySerial      v3.5    (Serielle Kommunikation)"
echo "  - Pint          v0.24.4 (Einheiten)"
echo ""
echo "============================================================"
echo ""

cd /Users/rudolfsarkany/windsurf

# JS Tools testen
echo "--- NODE.JS TOOLS CHECK ---"
node -e "
const n = require('obd-node');
const u = require('obd-utils');
console.log('obd-node Befehle:', n.getAllCommands().length);
console.log('obd-utils PIDs:  ', Object.keys(u.getAllPIDs()).length);
console.log('RPM Decoder:     ', u.parseOBDResponse('410C1B56').value, u.parseOBDResponse('410C1B56').unit);
" 2>&1

echo ""
echo "--- PYTHON TOOLS CHECK ---"
python3 -c "
import obd
import serial
print('python-OBD geladen: OK')
print('pySerial geladen:   OK')
print('RPM PID:', obd.commands.RPM.pid, '-', obd.commands.RPM.desc)
" 2>&1

echo ""
echo "============================================================"
echo "ALLE OBD TOOLS SIND BEREIT!"
echo ""
echo "Tipps:"
echo "  - ELM327 Dongle via USB/Bluetooth anschliessen"
echo "  - python3 scripts/obd-python-demo.py  fuer Demo"
echo "  - node scripts/obd-launcher.js      fuer JS Demo"
echo "============================================================"
echo ""
echo "ENTER zum Beenden"
read
