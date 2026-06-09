tell application "Terminal"
	do script "cd /Users/rudolfsarkany/windsurf && node -e \"const p=require('obd-parser'); console.log('========================================'); console.log('  obd-parser v'+require('obd-parser/package.json').version); console.log('  OBD-II Nachrichten-Parser'); console.log('========================================'); console.log('Modul geladen und bereit.'); console.log('Schliesse Terminal zum Beenden.'); setTimeout(()=>{},999999)\""
end tell
