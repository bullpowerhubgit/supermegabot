# SuperMegaBot — Zentrales Steuerungs-Hub

**Ein Bot. Alle Steuerungen.** Dieses Repo bündelt Dashboard, Bot-Logik und
Service-Integration in einem Hub. Jede Dashboard-Funktion ist gleichzeitig als
Telegram-Bot-Command verfügbar.

```
                     ┌──────────────────────────┐
                     │      Telegram User       │
                     └─────────────┬────────────┘
                                   │
                                   ▼
                ┌─────────────────────────────────────┐
                │  telegram_hub_bridge.py             │
                │  (long-polls Telegram, forwards     │
                │   every message to /api/bot/execute)│
                └─────────────────┬───────────────────┘
                                  │
                                  ▼
        ┌─────────────────────────────────────────────────┐
        │   SuperMegaBot Dashboard (aiohttp, Port 8888)   │
        │   ┌────────────────┐  ┌──────────────────────┐  │
        │   │  HTML Frontend │  │  /api/bot/execute    │  │
        │   │ (Buttons →     │  │  /api/bot/commands   │  │
        │   │  /api/*)       │  │  → CommandRouter     │  │
        │   └────────────────┘  └──────────┬───────────┘  │
        │                                  ▼              │
        │          ┌───────────────────────────────────┐  │
        │          │  MegaOrchestrator + CommandRouter │  │
        │          │  107+ commands                    │  │
        │          └───────────┬───────────────────────┘  │
        └──────────────────────┼──────────────────────────┘
                               ▼
           Shopify, Telegram-API, Ollama, RudiBot Army,
           Trading-Bot, Storage-Monitor, Self-Learner, …
```

## Schnellstart

```bash
# 1. Dependencies
pip install aiohttp psutil python-dotenv

# 2. Konfiguration
cp .env.example .env
# → TELEGRAM_BOT_TOKEN, ggf. weitere Werte eintragen

# 3. Dashboard starten
python3 dashboard/server.py
# → http://localhost:8888

# 4. Telegram-Hub-Bridge starten (neues Terminal)
python3 telegram_hub_bridge.py
# Jede Telegram-Nachricht → /api/bot/execute → CommandRouter → Antwort.

# 5. Komplettes End-to-End-Smoketest
python3 test_bot_hub.py
```

### Mit PM2 (empfohlen für Dauerbetrieb)

```bash
pm2 start ecosystem.config.js
pm2 logs
pm2 save
```

Die Konfiguration startet u. a. `supermegabot`, `mega-orchestrator`,
`rudibot-army` und die neue `tg-hub-bridge`.

## API-Endpunkte

Alle Endpunkte sind unter `http://localhost:8888` erreichbar.

### System / Health
| Endpoint              | Methode | Beschreibung                              |
| --------------------- | ------- | ----------------------------------------- |
| `/health`             | GET     | Basic-Health-Check                        |
| `/api/health`         | GET     | Alias zu `/health`                        |
| `/api/status`         | GET     | Service-Status aller Module               |
| `/api/services`       | GET     | Legacy-Service-Liste                      |
| `/api/services/status`| GET     | Aktueller Status aller Services           |
| `/api/system`         | GET     | CPU / RAM / Disk                          |
| `/api/metrics`        | GET     | Alias zu `/api/system`                    |
| `/api/processes`      | GET     | Top-Prozesse                              |
| `/api/logs`           | GET     | Letzte Log-Zeilen                         |
| `POST /api/logs/clear`| POST    | Leert das lokale Dashboard-Log            |

### Bot Hub
| Endpoint                | Methode | Beschreibung                                  |
| ----------------------- | ------- | --------------------------------------------- |
| `/api/bot/commands`     | GET     | Liste aller registrierten Commands (107+)     |
| `POST /api/bot/execute` | POST    | Führt einen Command via CommandRouter aus     |
| `POST /api/chat`        | POST    | Chat-Endpunkt (akzeptiert `text` oder `message`) |
| `POST /api/chat/clear`  | POST    | Löscht die Chat-Historie einer Session        |

### Business / Analytics
| Endpoint            | Methode | Beschreibung                                   |
| ------------------- | ------- | ---------------------------------------------- |
| `/api/shopify`      | GET     | Alias zu `/api/shopify/status`                 |
| `/api/shopify/status` | GET   | Shopify-Connection-Test                        |
| `/api/analytics`    | GET     | Aggregierte Analytics (System + Shopify + Trading) |
| `/api/revenue`      | GET     | Revenue-Snapshot (Shopify + lokale Cache-Datei) |
| `/api/kpis`         | GET     | KPI-Rollup (system + revenue + agents)         |
| `/api/agents`       | GET     | Army + Autopilot Agents kombiniert             |

### Service Management
| Endpoint                    | Methode | Beschreibung                          |
| --------------------------- | ------- | ------------------------------------- |
| `/api/services/action`      | POST    | `{id, action: start\|stop}`           |
| `/api/service/start`        | POST    | Convenience-Alias, `{id}`             |
| `/api/service/stop`         | POST    | Convenience-Alias, `{id}`             |

### Trading / Telegram / Ollama
| Endpoint                  | Methode | Beschreibung               |
| ------------------------- | ------- | -------------------------- |
| `/api/trading/prices`     | GET     | Aktuelle Crypto-Preise     |
| `/api/trading/arbitrage`  | GET     | Arbitrage-Scan             |
| `/api/telegram/status`    | GET     | Bot-Konfiguration prüfen   |
| `/api/telegram/send`      | POST    | Telegram-Nachricht senden  |
| `/api/ollama/models`      | GET     | Lokale Ollama-Modelle      |

… plus alle Endpunkte für **RudiBot Army**, **Self-Learner**, **Storage**,
**Backup**, **Geheimwaffe**, **Autopilot**, **GMC**, **Mac-Controller**.

## Deep-Scan-Repair

```bash
python3 deep_scan_repair.py            # Scan ausführen
python3 deep_scan_repair.py --fix      # Scan + Auto-Repair
```

Der Scanner ist **portabel** — er verwendet `Path(__file__).resolve().parent`,
funktioniert also auf jeder Maschine, nicht nur auf Rudolfs Mac.

## Bot-Bridge: Wie der Bot zum Hub wird

`telegram_hub_bridge.py` ist ein dependency-armer Python-Script, der:

1. Telegram via Long-Polling abfragt (kein Webhook nötig).
2. **Jede** Nachricht an `POST /api/bot/execute` weiterleitet.
3. Die Antwort 1:1 zurück nach Telegram schickt (mit 4096-Byte-Chunking).
4. Optionalen Single-Chat-Modus über `TELEGRAM_CHAT_ID` unterstützt.

`/commands` oder `/befehle` liefert die komplette Command-Liste vom Dashboard.

## Tests

```bash
python3 test_bot_hub.py
```

Startet den Dashboard-Server auf Port 8889, testet 23 Endpunkte +
Bridge-Import, beendet den Server sauber und liefert Exit-Code 0 bei Erfolg.

## Sicherheit

- Keine Hardcoded-Secrets. Alle Tokens kommen aus `.env`.
- Bare-`except:` wurde durch konkrete Exception-Typen ersetzt.
- `GuardianClient` wird lazy initialisiert — fehlendes
  `GUARDIAN_API_SECRET` blockiert nicht mehr den Dashboard-Start.
- Bridge erlaubt Restriktion auf einzelne Chat-IDs.
