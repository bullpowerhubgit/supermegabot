# RudiBot Deployment Readiness

> Checkliste für Release-Readiness: Was muss passieren, bevor RudiBot deployed wird.

---

## 1. Pre-Deployment Checklist

### Code-Qualität
- [ ] Keine `print()` Statements (nur Logging)
- [ ] Keine hartcodierten Secrets
- [ ] Keine Debug-Modi aktiv
- [ ] Alle TODOs sind abgearbeitet oder in Issues verfolgt
- [ ] Code-Review durchgeführt

### Konfiguration
- [ ] `.env.example` ist aktuell und vollständig
- [ ] `.env` ist in `.gitignore`
- [ ] Alle Ports sind konfigurierbar via Environment
- [ ] Logging-Level ist auf `INFO` oder `WARNING`
- [ ] Debug-Mode ist aus

### Dependencies
- [ ] `requirements.txt` ist aktuell
- [ ] `package.json` (falls Node.js Tools) ist aktuell
- [ ] Keine ungenutzten Dependencies
- [ ] Keine veralteten Packages mit CVEs

### Sicherheit
- [ ] API-Keys haben minimale Rechte (Principle of Least Privilege)
- [ ] Webhook-Secrets sind konfiguriert
- [ ] Rate-Limits sind aktiviert
- [ ] CORS ist korrekt konfiguriert
- [ ] Keine sensiblen Daten in Logs

---

## 2. Environment Readiness

### Lokal
- [ ] Python 3.9+ installiert
- [ ] `pip3 install -r requirements.txt` läuft durch
- [ ] Alle Ports sind frei (3201, 9900)
- [ ] `.env` ist korrekt befüllt

### PM2
- [ ] `pm2` ist global installiert
- [ ] `pm2 startup` wurde ausgeführt
- [ ] `ecosystem.config.js` ist validiert
- [ ] Log-Rotation ist konfiguriert (`pm2 install pm2-logrotate`)

### Railway
- [ ] Railway CLI ist installiert und authentifiziert
- [ ] Projekt ist erstellt
- [ ] Services sind definiert
- [ ] Environment Variables sind gesetzt
- [ ] `railway up` deployt erfolgreich

---

## 3. Monitoring Setup

### Dashboard
- [ ] Dashboard ist erreichbar
- [ ] Alle Services zeigen grün
- [ ] Event-Log zeigt Einträge
- [ ] Monetarisierungs-Tracking funktioniert

### Alerts
- [ ] Telegram-Bot antwortet auf `/status`
- [ ] Critical Alerts kommen an
- [ ] Warning Alerts kommen an
- [ ] Test-Alert wurde gesendet

### Health Checks
- [ ] Guardian Health-Check: `curl http://localhost:3201/api/v1/health`
- [ ] Master Dashboard Data: `curl http://localhost:9900/dashboard_data.json`
- [ ] Alle Endpoints antworten in < 2 Sekunden

---

## 4. Rollback Plan

### Vor jedem Deployment
- [ ] Aktueller Stand ist getaggt (`git tag v1.x.x`)
- [ ] Backup der Datenbank/State-Files
- [ ] Rollback-Befehl ist dokumentiert:
  ```bash
  pm2 stop all
  git checkout v1.x.x
  pm2 start ecosystem.config.js
  ```

### Bei Fehlern
- [ ] Automatisches Rollback nach 3 fehlgeschlagenen Health-Checks
- [ ] Manueller Rollback-Befehl ist getestet
- [ ] Datenverlust ist dokumentiert und akzeptiert

---

## 5. Post-Deployment Verification

### Sofort nach Deploy
- [ ] Alle Services sind `online` in PM2
- [ ] Dashboard zeigt alle Services grün
- [ ] Keine Error-Logs in den ersten 5 Minuten
- [ ] Telegram-Test-Nachricht wurde gesendet

### Nach 1 Stunde
- [ ] Keine Crash-Restarts in PM2
- [ ] Dashboard zeigt aktuelle Daten
- [ ] Event-Log zeigt normale Aktivität
- [ ] CPU/RAM Nutzung ist stabil

### Nach 24 Stunden
- [ ] Uptime > 99%
- [ ] Keine Memory-Leaks (RAM konstant)
- [ ] Log-Dateien sind rotiert
- [ ] Backup wurde erfolgreich erstellt

---

## 6. Go-Live Kriterien

| Kriterium | Akzeptanz | Status |
|-----------|-----------|--------|
| Alle Services laufen stabil > 24h | ✅ | [ ] |
| Keine kritischen Fehler in Logs | ✅ | [ ] |
| Dashboard zeigt korrekte Daten | ✅ | [ ] |
| Alerts funktionieren | ✅ | [ ] |
| Rollback getestet | ✅ | [ ] |
| Dokumentation ist aktuell | ✅ | [ ] |
| Secrets sind sicher hinterlegt | ✅ | [ ] |

**Go/No-Go Entscheidung:**
- [ ] GO - System ist bereit für Production
- [ ] NO-GO - Blocker existieren, siehe Issues: ___
