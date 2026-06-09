# RudiBot Repair Plan

> Konkrete, ausführbare Repair-Empfehlungen mit Priorität und Aufwand.

---

## P0 - Kritisch (Sofort fixen)

### RP-001: Port-Konfiguration externalisieren
**Dateien:** `eternal_guardian.py`, `server.py`
**Problem:** Ports 3201 und 9900 sind hardcoded.
**Fix:**
```python
import os
PORT = int(os.getenv('GUARDIAN_PORT', '3201'))
# bzw.
PORT = int(os.getenv('MASTER_PORT', '9900'))
```
**Aufwand:** 5 Minuten pro Datei
**Test:** Starte mit anderem Port, prüfe ob Service erreichbar.

### RP-002: File-Locking für Shared State
**Dateien:** `army_commander.py`, `meta_supervisor.py`
**Problem:** Race Conditions bei File-basiertem State-Sharing.
**Fix:**
```python
import fcntl

with open(state_file, 'r+') as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    state = json.load(f)
    # ... modify ...
    f.seek(0)
    json.dump(state, f)
    f.truncate()
    fcntl.flock(f, fcntl.LOCK_UN)
```
**Aufwand:** 30 Minuten
**Test:** Starte Commander und Supervisor parallel, prüfe State-Konsistenz.

### RP-003: Retry-Logik für Telegram
**Dateien:** Alle mit `requests.post` zu Telegram
**Problem:** Kein Retry bei Netzwerkfehlern.
**Fix:**
```python
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retry))
```
**Aufwand:** 20 Minuten pro Datei
**Test:** Simuliere Netzwerkfehler (z.B. via `toxiproxy`), prüfe ob Nachricht trotzdem ankommt.

---

## P1 - Wichtig (Diese Woche)

### RP-004: Graceful Shutdown
**Dateien:** Alle `*.py` mit `if __name__ == '__main__':`
**Fix:**
```python
import signal
import sys

def shutdown_handler(signum, frame):
    logger.info("Shutting down gracefully...")
    # cleanup
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)
```
**Aufwand:** 15 Minuten pro Datei

### RP-005: JSON-Validierung Dashboard
**Dateien:** `server.py`
**Fix:**
```python
from jsonschema import validate

DASHBOARD_SCHEMA = {
    "type": "object",
    "required": ["status", "timestamp"],
    "properties": {
        "status": {"type": "string"},
        "timestamp": {"type": "number"}
    }
}

def get_dashboard_data():
    with open('dashboard_data.json') as f:
        data = json.load(f)
    validate(instance=data, schema=DASHBOARD_SCHEMA)
    return data
```
**Aufwand:** 30 Minuten

### RP-006: Health-Check Endpoints
**Dateien:** `army_commander.py`, `meta_supervisor.py`
**Fix:** Einfachen HTTP-Health-Check hinzufügen oder zumindest ein `health` File schreiben.
```python
def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "pid": os.getpid()
    }
```
**Aufwand:** 20 Minuten pro Service

---

## P2 - Mittelfristig (Diesen Monat)

### RP-007: Structured Logging
**Dateien:** Alle `*.py`
**Fix:** Ersetze `print()` durch JSON-Logging:
```python
import logging
import json

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module
        })
```
**Aufwand:** 1-2 Stunden

### RP-008: Circuit Breaker
**Dateien:** Externe API-Clients
**Fix:** Einfacher Circuit Breaker:
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = "CLOSED"
```
**Aufwand:** 1 Stunde

---

## Repair Matrix

| ID | Priorität | Aufwand | Risiko reduziert | Dateien |
|----|-----------|---------|------------------|---------|
| RP-001 | P0 | 10min | Hoch | 2 |
| RP-002 | P0 | 30min | Hoch | 2 |
| RP-003 | P0 | 60min | Mittel | 3+ |
| RP-004 | P1 | 60min | Mittel | 4 |
| RP-005 | P1 | 30min | Mittel | 1 |
| RP-006 | P1 | 40min | Mittel | 2 |
| RP-007 | P2 | 2h | Niedrig | Alle |
| RP-008 | P2 | 1h | Mittel | 3+ |
