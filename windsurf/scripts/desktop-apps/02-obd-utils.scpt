tell application "Terminal"
	do script "cd /Users/rudolfsarkany/windsurf && node -e \"const u=require('obd-utils'); console.log('========================================'); console.log('  obd-utils v'+require('obd-utils/package.json').version); console.log('  PID-Liste & Decoder'); console.log('========================================'); console.log('PIDs verfuegbar:', Object.keys(u.getAllPIDs()).length); console.log('RPM-Beispiel:', u.parseOBDResponse('410C1B56')); console.log('Schliesse Terminal zum Beenden.'); setTimeout(()=>{},999999)\""
end tell
