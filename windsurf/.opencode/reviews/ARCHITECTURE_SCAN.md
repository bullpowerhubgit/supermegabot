# RudiBot Architecture Scan

> Scope: High-Level Architektur-Review basierend auf Systemdokumentation.
> Vollständiger Deep-Scan erfordert Zugriff auf Quellcode in rudibot-eternal/, rudibot-army/, rudibot-master/.

---

## 1. Executive Findings

### Stärken
- Klare Rollentrennung: Guardian (Infra), Commander (Ops), Supervisor (Schutz), Master (Sicht)
- Jede Komponente hat definierten Zweck und Source of Truth
- PM2-Betrieb vorbereitet mit Restart-Strategien
- Self-Healing und Deduplication eingeplant

### Schwächen (Dokumentations-Ebene)
- Keine klare Datenfluss-Dokumentation zwischen Python-Services
- Unklar: Wie teilen sich Guardian/Commander/State?
- Keine API-Spezifikation für interne Kommunikation
- Kein zentrales Error-Handling Konzept dokumentiert

---

## 2. Kritische Fehler (Zu prüfen im Code)

| # | Prüfpunkt | Risiko | Wo suchen |
|---|-----------|--------|-----------|
| 1 | Ports 3201 und 9900 hardcoded ohne Fallback | Hoch | `eternal_guardian.py`, `server.py` |
| 2 | File-basierte State-Sharing (Race Conditions) | Hoch | `rudibot-army/*.py`, `rudibot-master/*.py` |
| 3 | Kein Retry bei Telegram-API-Fehlern | Mittel | Alle `*.py` mit Telegram |
| 4 | Python-Subprozess-Spawning ohne Timeout | Mittel | `meta_supervisor.py`, `army_commander.py` |
| 5 | Dashboard liest JSON direkt ohne Validierung | Mittel | `server.py` |
| 6 | Kein Rate-Limiting an externen APIs | Mittel | Shopify, Stripe, Social APIs |
| 7 | Secrets in Environment, keine Rotation-Logik | Niedrig | `.env`, `config.py` |
| 8 | Kein graceful Shutdown Handling | Mittel | Alle `*.py` |

---

## 3. Architekturprobleme

### 3.1 State Management
**Beobachtung:** Army Commander nutzt "Shared State Files" als Schnittstelle.
**Risiko:** File-based IPC ist anfällig für Race Conditions, Lock-Probleme, und Datenverlust bei Crash.
**Empfehlung:** Ersetzen durch SQLite/Redis oder zumindest File-Locking mit `flock`.

### 3.2 Kommunikations-Pattern
**Beobachtung:** Kein dokumentiertes API zwischen Guardian und Commander.
**Risiko:** Tight Coupling durch direkte Imports oder File-Sharing.
**Empfehlung:** Definiere ein Message-Queue Pattern oder HTTP-API-Vertrag.

### 3.3 Monitoring-Lücke
**Beobachtung:** Meta-Supervisor überwacht Commander, aber wer überwacht den Supervisor?
**Risiko:** Single Point of Failure bei Supervisor-Crash.
**Empfehlung:** PM2 als outer Watchdog, Heartbeat-Checks von Guardian zum Supervisor.

### 3.4 Brain/ML Persistence
**Beobachtung:** Eternal Guardian hat "Brain für Learned Fixes".
**Risiko:** Unklar, wo ML-Modelle/Trainingsdaten persistiert werden.
**Empfehlung:** Dokumentiere Model-Path, Versionierung, Backup-Strategie.

---

## 4. Repair Plan

### P0 - Sofort
- [ ] Port-Konfiguration aus Environment lesen mit Fallback
- [ ] File-Locking für Shared State implementieren
- [ ] Retry-Logik für alle externen API-Calls (Telegram, Shopify, Stripe)

### P1 - Kurzfristig
- [ ] Graceful Shutdown Handler für alle Services
- [ ] JSON-Schema-Validierung für Dashboard-Daten
- [ ] Health-Check Endpoints für alle Services

### P2 - Mittelfristig
- [ ] Zentraler Message Bus (Redis/RabbitMQ) statt File-Sharing
- [ ] Structured Logging (JSON) statt Plaintext
- [ ] Circuit Breaker für externe APIs

### P3 - Langfristig
- [ ] API-Spezifikation (OpenAPI) für interne Kommunikation
- [ ] Automated Tests für jeden Agenten
- [ ] Load Testing für Dashboard

---

## 5. Tote Dateien / Verwaiste Komponenten

Zu prüfen (kein Zugriff auf Quellcode):
- [ ] `dashboard_server.py` wird in Troubleshooting erwähnt, aber nicht in Kernkomponenten
- [ ] `logs/` Verzeichnisse — werden sie rotiert?
- [ ] Backup-Dateien oder `.pyc` im Git?
- [ ] Unbenutzte Importe in Python-Dateien
