# 🚀 Mac Performance Optimizer

Automatische Systemüberwachung und Optimierung für macOS, um deinen Mac schnell und effizient zu halten.

## Features

- **📊 Systemüberwachung**: CPU, RAM und Festplattenspeicher in Echtzeit
- **🧹 Automatische Bereinigung**: Cache, Logs, temporäre Dateien, Downloads
- **🧠 Speicheroptimierung**: RAM freigeben und optimieren
- **🗑️ Papierkorb leeren**: Automatisch leeren
- **🌐 DNS-Cache leeren**: Netzwerkgeschwindigkeit verbessern
- **👁️ Überwachungsmodus**: Kontinuierliche Überwachung mit automatischer Optimierung
- **⏰ Geplante Ausführung**: Automatische tägliche Optimierung via LaunchAgent

## Installation

1. Stelle sicher, dass Python 3 installiert ist:
```bash
python3 --version
```

2. Mache das Skript ausführbar:
```bash
chmod +x mac-optimizer.py
```

## Nutzung

### Systemstatus anzeigen
```bash
python3 mac-optimizer.py --stats
```

### Vollständige Optimierung durchführen
```bash
python3 mac-optimizer.py --optimize
```

### Nur Bereinigung (Cache, Logs, Temp)
```bash
python3 mac-optimizer.py --clean
```

### Überwachungsmodus starten (überwacht alle 5 Minuten)
```bash
python3 mac-optimizer.py --monitor
```

### Benutzerdefinierter Überwachungsintervall (z.B. alle 10 Minuten)
```bash
python3 mac-optimizer.py --monitor --interval 10
```

## Automatische tägliche Optimierung einrichten

1. Kopiere die LaunchAgent-Datei:
```bash
cp com.macoptimizer.plist ~/Library/LaunchAgents/
```

2. Lade den LaunchAgent:
```bash
launchctl load ~/Library/LaunchAgents/com.macoptimizer.plist
```

3. Der Optimizer läuft jetzt täglich automatisch!

Um den automatischen Dienst zu stoppen:
```bash
launchctl unload ~/Library/LaunchAgents/com.macoptimizer.plist
```

## Konfiguration

Die Konfiguration wird hier gespeichert: `~/.mac-optimizer/config.json`

Standardkonfiguration:
```json
{
  "auto_cleanup": true,
  "cleanup_interval_hours": 24,
  "max_cpu_usage": 80,
  "max_memory_usage": 85,
  "enable_process_monitoring": true,
  "cleanup_cache": true,
  "cleanup_logs": true,
  "cleanup_temp": true
}
```

## Was wird optimiert?

### Cache-Bereinigung
- User Library Caches
- System Library Caches
- Cache-Dateien älter als 7 Tage

### Log-Bereinigung
- System Logs
- Application Logs
- Log-Dateien älter als 30 Tage

### Temporäre Dateien
- /tmp
- /var/tmp
- Crash Reporter Files
- Dateien älter als 7 Tage

### Downloads-Bereinigung
- Dateien im Downloads-Ordner älter als 30 Tage

### Speicheroptimierung
- RAM freigeben mit `purge` Befehl
- Speicherdruck reduzieren

### Netzwerk-Optimierung
- DNS-Cache leeren
- mDNSResponder neu starten

## Logs

Alle Aktivitäten werden protokolliert in: `~/.mac-optimizer/optimizer.log`

## Sicherheit

- Nur sichere Launch Agents werden deaktiviert
- Keine Systemdateien werden gelöscht
- Alle Aktionen werden protokolliert
- Backup-freundlich

## Häufige Fragen

**Ist das sicher?**
Ja, das Tool löscht nur Cache- und temporäre Dateien, keine wichtigen System- oder Benutzerdaten.

**Wie oft sollte ich optimieren?**
Für die meisten Benutzer reicht eine tägliche oder wöchentliche Optimierung. Der Überwachungsmodus kann bei hoher Auslastung automatisch optimieren.

**Kann ich bestimmte Bereinigungen deaktivieren?**
Ja, bearbeite einfach die `~/.mac-optimizer/config.json` Datei.

## Anforderungen

- macOS 10.14 oder höher
- Python 3.6 oder höher
- Administratorrechte für einige Funktionen (DNS-Cache, Launch Agents)

## Troubleshooting

**Fehler: Permission denied**
```bash
sudo python3 mac-optimizer.py --optimize
```

**LaunchAgent wird nicht geladen**
Stelle sicher, dass der Pfad in der plist-Datei korrekt ist und passe ihn an deinen Pfad an.

## Support

Logs prüfen: `cat ~/.mac-optimizer/optimizer.log`
