# RudiBot Deep-Scan Prompt

> Kopiere diesen Block in Cursor, Claude Code, Windsurf oder einen anderen AI-Coding-Client mit Zugriff auf die RudiBot-Quellcodedateien.

---

```
Bitte führe einen Deep-Scan der RudiBot-Codebasis durch und liefere eine kombinierte Analyse aus:

1. Architektur-Review
2. Fehler- und Risikoanalyse
3. Repair-Vorschläge
4. UI-/Button-/Form-Testplan
5. Readiness-Check für Deployment

Ziele:
- Finde Inkonsistenzen, tote Dateien, doppelte Logik, fragile Stellen und fehlende Absicherungen
- Prüfe, ob die Architektur klar getrennte Verantwortlichkeiten hat
- Erkenne fehlende Error-Handling-, Logging- und Retry-Mechanismen
- Prüfe Konfiguration, Secrets, Ports, API-Aufrufe und Restart-Logik
- Erstelle konkrete Repair-Empfehlungen mit Priorität

Dateien zu scannen:
- /Users/rudolfsarkany/rudibot-eternal/eternal_guardian.py
- /Users/rudolfsarkany/supermegabot/rudibot-army/army_commander.py
- /Users/rudolfsarkany/supermegabot/rudibot-army/meta_supervisor.py
- /Users/rudolfsarkany/rudibot-master/server.py
- /Users/rudolfsarkany/rudibot-master/dashboard_data.json (falls existiert)
- Alle .env Dateien, aber keine Secret-Werte ausgeben
- /Users/rudolfsarkany/supermegabot/rudibot-army/ecosystem.config.js (falls existiert)
- Weitere JSON-, Log- oder State-Dateien berücksichtigen, wenn sie für Monitoring, Recovery oder Runtime relevant sind

Zusätzliche Regeln:
- Phase 1 ist strikt read-only: keine Dateien ändern, keine automatischen Refactors, keine Secrets ausgeben
- Jede wichtige Feststellung muss belegt werden mit:
  - Dateipfad
  - Funktion/Klasse/Bereich
  - kurzer Erklärung
  - Severity: kritisch / hoch / mittel / niedrig
- Wenn möglich, nenne konkrete Zeilenbereiche oder eindeutige Code-Stellen
- Secrets niemals ausschreiben, nur deren Existenz, Risiko oder fehlende Absicherung beschreiben
- Trenne klar zwischen:
  - Beobachtung
  - Risiko
  - empfohlener Repair
- Markiere, was sicher belegt ist und was nur eine Hypothese ist
- Wenn Tests nicht ausführbar sind, erstelle trotzdem reproduzierbare Testschritte
- Für API-Tests bitte konkrete curl-Beispiele liefern
- Für UI-Tests bitte testbare Schritte mit erwartetem Verhalten liefern
- Für Deployment-Readiness bitte klare Go/No-Go-Kriterien definieren

Zusätzlich erstelle bitte eine Test-Checkliste für:
- einzelne Buttons
- Formulareingaben
- API-Endpunkte
- Dashboard-Aktionen
- Health-Checks
- Fehlerfälle
- Restart-Verhalten
- Telegram-/Webhook-Flows

Erwartete Ausgabe:
## 1. Executive Findings
## 2. Kritische Fehler
## 3. Architekturprobleme
## 4. Repair Plan
## 5. UI Test Checklist
## 6. API Test Checklist
## 7. Monitoring & Recovery Checklist
## 8. Deployment Readiness
## 9. Quick Wins
## 10. Offene Risiken

Der AI-Client soll diese Dateien erzeugen:
1. ARCHITECTURE_SCAN.md
2. REPAIR_PLAN.md
3. TEST_CHECKLIST.md
4. DEPLOYMENT_READINESS.md

Wichtige Prüfpunkte:
- Jeder Button hat eine echte Funktion, einen klaren State und Fehlerbehandlung
- Keine UI-Aktion ohne Feedback
- Keine API ohne Timeout, Fehlerbehandlung und Logging
- Keine sensiblen Daten hart codiert
- Keine stillen Fehler ohne sichtbare Meldung
- Keine doppelte oder widersprüchliche Konfiguration
- Keine ungenutzten Services oder verwaisten Dateien
- Prüfe Edge Cases und Regression-Risiken

Button-Testkriterien pro Button:
1. Sichtbar und korrekt beschriftet
2. Klickbar in allen relevanten Zuständen
3. Zeigt Loading-, Success- oder Error-Feedback
4. Löst wirklich die erwartete Aktion aus
5. Ist gegen Doppelklick oder Mehrfachauslösung abgesichert
6. Ist per Keyboard erreichbar
7. Ist auf Mobile nutzbar
8. Bricht nicht bei leerem Input oder Backend-Fehlern
```

---

## Output-Struktur

Der AI-Client sollte diese Dateien erzeugen:

1. `ARCHITECTURE_SCAN.md` — High-Level Architektur-Findings
2. `REPAIR_PLAN.md` — Konkrete, ausführbare Repairs mit Code-Beispielen
3. `TEST_CHECKLIST.md` — Ausführbare Testfälle mit curl-Befehlen
4. `DEPLOYMENT_READINESS.md` — Go/No-Go Kriterien

## Hinweis

Dieser Prompt funktioniert am besten in:
- **Cursor** mit "agent" mode
- **Claude Code** mit `--dangerously-skip-permissions`
- **Windsurf** Cascade mit Zugriff auf das gesamte RudiBot-Verzeichnis
- **OpenCode** selbst (nach Installation)
