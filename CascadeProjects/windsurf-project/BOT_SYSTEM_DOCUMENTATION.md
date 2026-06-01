# SuperMegaBot - Unified Bot System Documentation

## Overview

Das SuperMegaBot System verfügt über ein vollständiges, spezialisiertes Bot-Orchestrierungssystem für automatisches System-Management, Monitoring und Fehlerbehebung.

## Bot-Architektur

### Spezialisierte Bots

#### 1. Monitoring Bot (`bots/specialized/monitoring-bot.js`)
- **Funktion**: Systemüberwachung, API-Status, Performance-Metriken
- **Interval**: 30 Sekunden
- **Priorität**: Hoch
- **Features**:
  - System-Metriken (RAM, CPU, Disk)
  - API-Endpoint-Checks (Anthropic, OpenAI, Perplexity, Shopify)
  - Prozess-Monitoring
  - Kritische Datei-Überprüfung
  - Threshold-basierte Alerts

#### 2. Repair Bot (`bots/specialized/repair-bot.js`)
- **Funktion**: Automatische Fehlerbehebung
- **Interval**: 60 Sekunden
- **Priorität**: Mittel
- **Features**:
  - Log-Rotation (>10MB)
  - Cache-Cleanup
  - node_modules-Verifikation
  - Script-Permission-Reparatur
  - Automatische Reparatur-Historie

#### 3. Optimization Bot (`bots/specialized/optimization-bot.js`)
- **Funktion**: Performance und Conversion-Optimierung
- **Interval**: 300 Sekunden (5 Minuten)
- **Priorität**: Niedrig
- **Features**:
  - Bundle-Size-Analyse
  - Code-Qualitäts-Checks
  - Asset-Optimierung
  - Performance-Metriken
  - Conversion-Optimierung

#### 4. Error Detection Bot (`bots/specialized/error-detection-bot.js`)
- **Funktion**: Fehlererkennung und Log-Analyse
- **Interval**: 45 Sekunden
- **Priorität**: Hoch
- **Features**:
  - Log-File-Monitoring
  - Pattern-basierte Fehlererkennung
  - System-Journal-Überprüfung
  - Zombie-Prozess-Erkennung
  - Deduplizierung bekannter Fehler

#### 5. Maintenance Bot (`bots/specialized/maintenance-bot.js`)
- **Funktion**: Wartung und Health-Checks
- **Interval**: 120 Sekunden (2 Minuten)
- **Priorität**: Mittel
- **Features**:
  - Backup-Verifikation
  - Outdated-Dependency-Checks
  - Disk-Health
  - Service-Health-Checks
  - Env-File-Health

### Unified Bot Orchestrator (`bots/unified-bot-orchestrator.js`)

Der Orchestrator koordiniert alle spezialisierten Bots und bietet:

- **Zentrale Steuerung**: Start/Stop/Restart aller Bots
- **Event-Bus**: Event-basierte Kommunikation zwischen Bots
- **Health-Checks**: Automatische Überprüfung der Bot-Gesundheit
- **Auto-Recovery**: Automatischer Neustart bei Fehlern
- **Status-Monitoring**: Echtzeit-Status aller Bots
- **Priorisierung**: Hochprioritäts-Bots werden zuerst gestartet

## Installation & Setup

### Voraussetzungen
- Node.js (ESM support)
- Alle Dependencies in `package.json`

### NPM Scripts

```bash
# Alle Bots starten (über Orchestrator)
npm run bot:all

# Einzelne Bots starten
npm run bot:orchestrator
npm run bot:monitoring
npm run bot:repair
npm run bot:optimization
npm run bot:error-detection
npm run bot:maintenance

# Dashboard öffnen
open bot-monitoring-dashboard.html
```

## Bot-Monitoring Dashboard

Das Dashboard (`bot-monitoring-dashboard.html`) bietet:

- **Live-Status-Übersicht**: Alle Bots auf einen Blick
- **Echtzeit-Metriken**: RAM, CPU, Events, Alerts
- **Bot-Steuerung**: Start/Stop/Restart pro Bot
- **Event-Historie**: Letzte 20 Events mit Severity
- **Auto-Refresh**: Automatische Status-Aktualisierung

## Event-System

Der Event-Bus (`bots/shared/event-bus.js`) ermöglicht die Kommunikation zwischen Bots:

### Wichtige Events

- `bot:started` - Bot wurde gestartet
- `bot:stopped` - Bot wurde gestoppt
- `error:bot` - Bot-Fehler
- `alert:critical` - Kritischer Alert
- `alert:high` - High-Severity Alert
- `metrics:system` - System-Metriken
- `status:api` - API-Status
- `repair:executed` - Reparatur ausgeführt
- `optimization:suggestion` - Optimierungsvorschlag
- `maintenance:check` - Maintenance-Check

## Konfiguration

### Bot-Konfiguration

Die Bots können über Optionen konfiguriert werden:

```javascript
const orchestrator = new UnifiedBotOrchestrator({
  monitoring: { interval: 30 },
  repair: { interval: 60 },
  optimization: { interval: 300 },
  errorDetection: { interval: 45 },
  maintenance: { interval: 120 },
  healthCheckInterval: 60000
});
```

### Thresholds

Monitoring-Bot Thresholds (Standardwerte):
- Memory: 80%
- CPU: 90%
- Disk: 85%
- API Response: 5000ms

## Best Practices

### Bot-Start-Reihenfolge
1. Monitoring Bot (System-Health)
2. Error Detection Bot (Fehlererkennung)
3. Repair Bot (Fehlerbehebung)
4. Maintenance Bot (Wartung)
5. Optimization Bot (Optimierung)

### Monitoring
- Dashboard regelmäßig prüfen
- Critical Alerts sofort behandeln
- Event-Historie überwachen

### Wartung
- Regelmäßige Bot-Status-Checks
- Reparatur-Historie prüfen
- Optimierungsvorschläge implementieren

## Troubleshooting

### Bot startet nicht
- Syntax-Check: `node --check bots/specialized/[bot-name].js`
- Dependencies prüfen: `npm install`
- Logs prüfen: `logs/[bot-name].log`

### Bot stürzt ab
- Event-Bus auf Fehler prüfen
- Auto-Recovery aktivieren
- Restart-Count überwachen

### High CPU/RAM
- Bot-Intervale erhöhen
- Thresholds anpassen
- Optimierung-Bot-Vorschläge prüfen

## Integration mit existierenden Systemen

Die Bots können in bestehende Systeme integriert werden über:

1. **Event-Bus Subscription**: Auf Events reagieren
2. **Bot-Status API**: Status abfragen
3. **Orchestrator Control**: Steuerung über Messages
4. **Dashboard Integration**: Dashboard embedden

## Sicherheit

- Keine Hardcoded Secrets
- Env-Variablen verwenden
- Logs regelmäßig rotieren
- API-Keys sicher speichern

## Performance

- Minimale System-Last durch intelligente Intervalle
- Event-basierte Architektur reduziert Overhead
- Deduplizierung bekannter Fehler
- Cache für häufige Checks

## Next Steps

1. Bot-System produktiv einsetzen
2. Dashboard in Monitoring-System integrieren
3. Alerts mit Notification-System verbinden
4. Custom-Bots für spezifische Anforderungen
5. Machine-Learning für Predictive Maintenance

## Support & Dokumentation

- Bot-Logs: `logs/`
- Dashboard: `bot-monitoring-dashboard.html`
- Orchestrator: `bots/unified-bot-orchestrator.js`
- Shared Components: `bots/shared/`

---

**Status**: ✅ Produktionsbereit  
**Version**: 1.0.0  
**Last Updated**: 2026-06-01
