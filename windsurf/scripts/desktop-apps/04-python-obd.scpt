tell application "Terminal"
	do script "cd /Users/rudolfsarkany/windsurf && python3 -c \"import obd; print('='*50); print('  python-OBD v0.7.3'); print('  ELM327 Scanner'); print('='*50); print('Verfuegbare Befehle:'); print('  RPM:', obd.commands.RPM.desc); print('  Speed:', obd.commands.SPEED.desc); print('  Coolant:', obd.commands.COOLANT_TEMP.desc); print('Verbinde mit: obd.OBD()'); print('Schliesse Terminal zum Beenden.')\""
end tell
