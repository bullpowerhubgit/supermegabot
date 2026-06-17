tell application "Terminal"
	do script "cd /Users/rudolfsarkany/windsurf && node -e \"const n=require('obd-node'); console.log('========================================'); console.log('  obd-node v'+require('obd-node/package.json').version); console.log('  OBD-II Kommunikations-Engine'); console.log('========================================'); console.log('Befehle verfuegbar:', n.getAllCommands().length); console.log('RPM Command:', n.getCommandByPid('010C')); console.log('Schliesse Terminal zum Beenden.'); setTimeout(()=>{},999999)\""
end tell
