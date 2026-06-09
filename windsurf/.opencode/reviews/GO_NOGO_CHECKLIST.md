# RudiBot Go/No-Go Checkliste

> Regel: **GO** nur, wenn alle kritischen Punkte erfüllt sind. **NO-GO** sofort, wenn Auth, Secrets, Health Checks, Rollback oder kritische Kernflüsse ungeklärt sind.

---

## 1. Scope & Freigabe

- [ ] Der genaue Release-Umfang ist dokumentiert.
- [ ] Alle betroffenen Services sind aufgelistet.
- [ ] Bekannte Risiken sind dokumentiert.
- [ ] Es gibt eine klare Owner-Zuordnung pro Service.
- [ ] Entscheidungsträger für Go/No-Go sind benannt.

**NO-GO wenn:**
- Unklar ist, was genau ausgerollt wird
- Kein Owner für einen kritischen Service existiert

---

## 2. Code & Build

- [ ] Letzter Stand ist committed und versioniert.
- [ ] Build/Start funktioniert lokal oder in Staging reproduzierbar.
- [ ] Es gibt keine offenen kritischen Fehler mit Severity "kritisch".
- [ ] Konfigurationsdateien sind konsistent.
- [ ] Keine offensichtlichen toten oder verwaisten Deploy-Artefakte blockieren den Rollout.

**NO-GO wenn:**
- Unversionierte Hotfixes existieren
- Build oder Start nicht reproduzierbar ist
- Kritische Findings ungefixt sind

---

## 3. Security & Secrets

- [ ] Keine Secrets sind hart im Code hinterlegt.
- [ ] Alle `.env`-Variablen sind vorhanden.
- [ ] Secret-Werte sind für Production gesetzt.
- [ ] Admin- und API-Zugriffe sind geschützt.
- [ ] Webhooks sind mit Secret oder Signatur abgesichert.
- [ ] Rate Limiting ist dort aktiv, wo öffentliche Endpunkte erreichbar sind.

**NO-GO wenn:**
- Secrets fehlen oder hartcodiert sind
- Auth für Admin- oder API-Endpunkte fehlt
- Öffentliche Endpunkte ohne Schutz live gehen würden

---

## 4. Services & Health

- [ ] Eternal Guardian startet fehlerfrei.
- [ ] Army Commander startet fehlerfrei.
- [ ] Meta-Supervisor startet fehlerfrei.
- [ ] RudiBot Master startet fehlerfrei.
- [ ] Alle relevanten Health Checks antworten korrekt.
- [ ] Abhängigkeiten zwischen den Services sind geprüft.

**Pflicht-Checks:**
- [ ] `GET /api/v1/health` liefert erfolgreich Antwort
- [ ] `GET /api/v1/status` liefert plausiblen Status
- [ ] Dashboard ist erreichbar
- [ ] Dashboard-Daten werden korrekt geladen

**NO-GO wenn:**
- Ein Kerndienst nicht stabil startet
- Health Checks fehlschlagen
- Dashboard keine Live-Daten zeigt

---

## 5. Kernflüsse

- [ ] Guardian kann Events/Notifications verarbeiten.
- [ ] Commander führt seine Kernjobs ohne Crash aus.
- [ ] Meta-Supervisor erkennt und behandelt Fehlerfälle.
- [ ] Master zeigt den aggregierten Zustand korrekt an.
- [ ] Telegram-/Webhook-Flows funktionieren für kritische Events.
- [ ] Restart-Verhalten wurde mindestens einmal getestet.

**NO-GO wenn:**
- Kritische Automationsflüsse ungetestet sind
- Crash-Recovery nicht nachgewiesen wurde
- Alarmierung bei Fehlern nicht funktioniert

---

## 6. UI & Button Tests

- [ ] Jeder sichtbare Button hat eine echte Funktion.
- [ ] Jeder kritische Button zeigt Benutzerfeedback.
- [ ] Loading-, Success- oder Error-States sind vorhanden.
- [ ] Fehlerfälle sind sichtbar und verständlich.
- [ ] Formulareingaben sind validiert.
- [ ] Leere oder ungültige Inputs führen nicht zu stillen Fehlern.
- [ ] Keyboard-Navigation funktioniert.
- [ ] Mobile-Nutzung für kritische UI-Aktionen ist geprüft.

**NO-GO wenn:**
- Kritische Aktionen kein Feedback geben
- Buttons sichtbar, aber funktionslos sind
- Fehler still scheitern

---

## 7. Monitoring & Alerts

- [ ] Logs werden zentral oder reproduzierbar erfasst.
- [ ] PM2-Logs sind erreichbar.
- [ ] Kritische Fehler landen in Logs.
- [ ] Alerts für Crash/Warnung sind eingerichtet.
- [ ] Telegram-Benachrichtigungen funktionieren.
- [ ] Dashboard-Metriken sind plausibel.
- [ ] Nach dem Deploy gibt es einen Beobachtungszeitraum.

**NO-GO wenn:**
- Keine Beobachtbarkeit existiert
- Alerts für kritische Ausfälle fehlen
- Niemand den Post-Deploy-Zustand überwacht

---

## 8. Deployment-Pfad

- [ ] Zielumgebung ist festgelegt: lokal, PM2, Railway, Vercel oder Docker.
- [ ] Deployment-Schritte sind dokumentiert.
- [ ] Reihenfolge der Services ist definiert.
- [ ] Externe Abhängigkeiten sind erreichbar.
- [ ] DNS, SSL, Firewall oder Proxy-Konfiguration sind vorbereitet, falls nötig.
- [ ] CI/CD oder manuelle Deploy-Schritte sind verifiziert.

**NO-GO wenn:**
- Das tatsächliche Zielsystem unklar ist
- Deployment nur theoretisch dokumentiert, aber nicht verifiziert ist
- Externe Abhängigkeiten ungeprüft sind

---

## 9. Daten & Konfiguration

- [ ] Produktionspfade stimmen mit der Zielumgebung überein.
- [ ] Ports kollidieren nicht.
- [ ] JSON-/State-Dateien sind vorhanden oder werden sauber erzeugt.
- [ ] Schreibrechte auf Logs, State und Runtime-Dateien sind geprüft.
- [ ] Fallback-Verhalten bei fehlenden Dateien ist getestet.

**NO-GO wenn:**
- Dateipfade nur lokal auf deinem Mac funktionieren
- Zielumgebung andere Pfade braucht und nicht angepasst wurde
- State-Dateien still fehlen oder korrupt sein können

---

## 10. Rollback

- [ ] Vorherige stabile Version ist identifiziert.
- [ ] Rückroll-Schritte sind dokumentiert.
- [ ] PM2/Docker/Railway Rollback ist konkret beschrieben.
- [ ] Kritische Konfigurationsänderungen sind reversibel.
- [ ] Nach Rollback existieren Verifikationsschritte.
- [ ] Verantwortlicher für den Rollback ist benannt.

**NO-GO wenn:**
- Kein klarer Rückweg existiert
- Unklare Migrationen oder irreversible Änderungen enthalten sind

---

## 11. Post-Deploy

- [ ] Smoke Test direkt nach Deploy ist definiert.
- [ ] Health Checks werden sofort geprüft.
- [ ] Logs werden 15–30 Minuten aktiv beobachtet.
- [ ] Telegram-/Alerting-Kanal wird überprüft.
- [ ] Kritische User-Flows werden erneut manuell getestet.
- [ ] Issues werden dokumentiert und priorisiert.

**NO-GO wenn:**
- Kein Post-Deploy-Check eingeplant ist
- Niemand die Stabilisierung überwacht

---

## Harte Stop-Regeln

Diese fünf Punkte sind sofortige **NO-GO** Kriterien:

1. **Ein Kerndienst startet nicht stabil.**
2. **Health Check oder Dashboard-Daten sind fehlerhaft.**
3. **Secrets/Auth sind unvollständig oder unsicher.**
4. **Rollback ist nicht klar definiert.**
5. **Alerts/Monitoring fehlen für kritische Ausfälle.**

---

## Schneller 10-Minuten-Run

Wenn du kurz vor dem Deploy bist, prüfe in dieser Reihenfolge:

1. [ ] CI/Build/Start okay.
2. [ ] Health Checks und Dashboard okay.
3. [ ] Secrets/Auth/Rate Limits okay.
4. [ ] Rollback bereit und vorige Version bekannt.
5. [ ] Monitoring, Alerts und Beobachtungsphase gesichert.

---

## Go/No-Go Entscheidung

- [ ] **GO** — Alle kritischen Punkte erfüllt. System ist bereit für Production.
- [ ] **NO-GO** — Blocker existieren. Siehe Issues: ___________

**Entscheidung getroffen am:** ___________
**Entscheidung durch:** ___________
