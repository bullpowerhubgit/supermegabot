tell application "Terminal"
	do script "cd /Users/rudolfsarkany/windsurf && python3 -c \"from vininfo import Vin; print('='*50); print('  VIN Decoder'); print('='*50); v=Vin('2B3CJ4DV5AH123456'); print('Hersteller:', v.manufacturer); print('Jahr:', v.years); print('Region:', v.region); print('WMI:', v.wmi); print('Schliesse Terminal zum Beenden.')\""
end tell
