# RudiBot Test Checklist

> Ausführbare Testfälle für UI, API, Dashboard und Fehlerfälle.

---

## 1. Button Tests (RudiBot Master Dashboard)

### BT-001: Dashboard Refresh Button
- [ ] Button ist sichtbar und korrekt beschriftet
- [ ] Klick lädt neue Daten von `/dashboard_data.json`
- [ ] Loading-State wird angezeigt während des Requests
- [ ] Bei Erfolg: Daten werden aktualisiert ohne Seitenreload
- [ ] Bei Fehler: Fehlermeldung wird angezeigt (nicht stillschweigend)
- [ ] Button ist während Loading deaktiviert (Anti-Double-Click)
- [ ] Keyboard-Navigation funktioniert (Tab + Enter)

### BT-002: Service Restart Button
- [ ] Button nur sichtbar für autorisierte User
- [ ] Klick öffnet Bestätigungsdialog
- [ ] Bei "Ja": Restart-Request wird an API gesendet
- [ ] Bei "Nein": Dialog schließt ohne Aktion
- [ ] Erfolg: Toast/Success-Message
- [ ] Fehler: API-Error wird angezeigt
- [ ] Button ist während Request deaktiviert

### BT-003: Telegram Test Notification
- [ ] Button sendet Test-Nachricht an Telegram
- [ ] Erfolg: "Nachricht gesendet" Feedback
- [ ] Fehler: Telegram-Error wird angezeigt
- [ ] Kein Spam bei Mehrfachklick

---

## 2. Formular Tests

### FT-001: API-Schlüssel Konfiguration
- [ ] Formular lädt bestehende Werte
- [ ] Leere Pflichtfelder zeigen Fehlermeldung
- [ ] Ungültiges Format wird validiert (z.B. Stripe Key mit regex `^sk_(live|test)_`)
- [ ] Speichern schreibt in `.env` oder Config-Datei
- [ ] Erfolg: "Gespeichert" Feedback
- [ ] Fehler: "Speichern fehlgeschlagen" mit Details

### FT-002: Zielwerte (Monetarisierung)
- [ ] Tägliches Ziel: Nur Zahlen, Min 0, Max 100000
- [ ] Wochenziel: Automatisch = Tagesziel * 7 (oder manuell überschreibbar)
- [ ] Monatsziel: Automatisch = Tagesziel * 30 (oder manuell überschreibbar)
- [ ] Ungültige Werte zeigen Inline-Fehler
- [ ] Speichern persistiert sofort

---

## 3. API Endpoint Tests

### AE-001: Guardian Health Check
```bash
curl -s http://localhost:3201/api/v1/health | jq .
```
- [ ] HTTP 200
- [ ] Response enthält `status: "healthy"`
- [ ] Response enthält `timestamp` (Unix epoch)
- [ ] Responsezeit < 500ms
- [ ] Bei gestopptem Service: Connection refused

### AE-002: Guardian Status
```bash
curl -s http://localhost:3201/api/v1/status | jq .
```
- [ ] HTTP 200
- [ ] Response enthält alle erwarteten Felder
- [ ] Keine sensiblen Daten im Response (Secrets, Tokens)

### AE-003: Dashboard Data
```bash
curl -s http://localhost:9900/dashboard_data.json | jq .
```
- [ ] HTTP 200
- [ ] Valides JSON
- [ ] Alle Services haben Status-Felder
- [ ] Monetarisierungs-Daten sind Zahlen

### AE-004: Guardian Notify
```bash
curl -X POST http://localhost:3201/api/v1/notify \
  -H "Content-Type: application/json" \
  -d '{"message":"Test","level":"info"}'
```
- [ ] HTTP 200 bei valider Authentifizierung
- [ ] HTTP 401 ohne Auth-Header
- [ ] HTTP 400 bei ungültigem JSON
- [ ] Telegram-Nachricht wird tatsächlich gesendet

---

## 4. Dashboard Aktionen

### DA-001: Live-Status-Anzeige
- [ ] Alle 4 Services zeigen grün bei Running
- [ ] Service zeigt rot bei Stopped
- [ ] Service zeigt gelb bei Warning
- [ ] Status aktualisiert sich automatisch (Polling oder SSE)

### DA-002: Systemmetriken
- [ ] RAM-Nutzung wird angezeigt
- [ ] CPU-Nutzung wird angezeigt
- [ ] Disk-Nutzung wird angezeigt
- [ ] Werte sind in menschlich lesbarer Form (GB, %)
- [ ] Werte plausibel (0-100% für CPU/Disk)

### DA-003: Event-Log
- [ ] Events werden chronologisch angezeigt
- [ ] Neueste Events oben
- [ ] Pagination oder Infinite Scroll vorhanden
- [ ] Event-Typen haben unterschiedliche Farben (Error=rot, Info=blau)

---

## 5. Fehlerfall Tests

### EF-001: Guardian nicht erreichbar
- [ ] Dashboard zeigt "Guardian Offline"
- [ ] Kein Crash im Dashboard
- [ ] Retry-Logik versucht Wiederherstellung

### EF-002: Telegram nicht erreichbar
- [ ] Services laufen weiter
- [ ] Fehler wird geloggt
- [ ] Kein endloser Retry-Loop
- [ ] Nach Wiederherstellung: Nachrichten werden wieder gesendet

### EF-003: Ungültige Konfiguration
- [ ] Service startet nicht mit ungültigem Port ("abc")
- [ ] Klare Fehlermeldung im Log
- [ ] Service startet mit Default-Wert bei fehlender Env-Var

### EF-004: Disk voll
- [ ] Log-Rotation greift
- [ ] Kein Crash bei Schreibversuch
- [ ] Warnung wird an Telegram gesendet

---

## 6. Restart-Verhalten

### RV-001: PM2 Restart
```bash
pm2 restart rudibot-eternal
```
- [ ] Service startet innerhalb 10 Sekunden
- [ ] Kein Datenverlust
- [ ] Dashboard zeigt nach 15 Sekunden wieder grün
- [ ] Logs zeigen sauberen Restart

### RV-002: Kill -9 Recovery
```bash
kill -9 $(pgrep -f eternal_guardian)
```
- [ ] PM2 erkennt Crash und restartet
- [ ] Max Restarts wird beachtet
- [ ] Nach 10 Restarts: Status "errored"

### RV-003: Graceful Shutdown
```bash
pm2 stop rudibot-eternal
```
- [ ] Service beendet offene Verbindungen
- [ ] Keine hängigen Prozesse
- [ ] State wird persistiert

---

## 7. Telegram / Webhook Tests

### TW-001: Telegram-Bot-Start
- [ ] `/start` Antwortet mit Willkommensnachricht
- [ ] `/status` Zeigt Systemstatus
- [ ] `/restart <service>` Restartet Service
- [ ] Unbekannter Befehl: Hilfe-Text

### TW-002: Webhook-Integration
- [ ] Externer Webhook wird empfangen
- [ ] Signatur wird validiert
- [ ] Ungültige Signatur: HTTP 401
- [ ] Timeout bei langsamen Webhooks

---

## 8. Regression Tests

### REG-001: Neue Änderung bricht Dashboard nicht
- [ ] Dashboard lädt nach Code-Änderung
- [ ] Alle Buttons funktionieren
- [ ] API-Responses bleiben kompatibel

### REG-002: PM2 Config gültig
```bash
pm2 start ecosystem.config.js --dry-run
```
- [ ] Keine Syntaxfehler
- [ ] Alle Pfade existieren
- [ ] Interpreter ist verfügbar
