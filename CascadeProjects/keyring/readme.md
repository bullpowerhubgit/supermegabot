# Keyring CLI

Ein CLI-Tool zum Verwalten und Rotieren deiner API-Keys. Alle Keys werden verschlüsselt in `~/.keyring/` gespeichert.

## Installation

```bash
cd keyring
npm link        # macht "keyring" global verfügbar
# oder direkt:
node cli.js <command>
```

## Erste Schritte

```bash
keyring init    # Master-Passwort festlegen
```

## Commands

| Command | Beschreibung |
|---------|-------------|
| `keyring add` | Neuen API-Key hinzufügen (interaktiv) |
| `keyring list` | Alle Keys auflisten (Werte sind maskiert) |
| `keyring show <name>` | Einen Key im Klartext anzeigen |
| `keyring remove <name>` | Einen Key löschen |
| `keyring rotate <name>` | Einen einzelnen Key rotieren |
| `keyring rotate-all` | **ALLE Keys auf einmal rotieren** |
| `keyring validate [name]` | Key(s) auf Gültigkeit testen |
| `keyring health` | Health-Check für alle Keys |
| `keyring export [project] [file]` | `.env` Datei erstellen |
| `keyring generate` | Alle Keys als `.env`-Format ausgeben |
| `keyring import <file>` | Keys aus `.env`-Datei importieren |
| `keyring log` | Rotations-Log anzeigen |

## Beispiele

```bash
# Keys hinzufügen
keyring add
# Name: OPENAI_API_KEY
# Wert: sk-...
# Provider: OpenAI
# Projekt: rudibot

# .env Datei für ein Projekt erstellen
keyring export rudibot .env

# ALLE Keys rotieren (z.B. wenn Projekt fertig ist)
keyring rotate-all

# Keys validieren
keyring validate              # Alle Keys validieren
keyring validate OPENAI_API_KEY  # Nur einen Key validieren

# Health-Check
keyring health
```

## Validierung & Testing

Das Tool kann API-Keys auf zwei Ebenen testen:

### 1. Format-Validierung
Prüft ob der Key dem erwarteten Format des jeweiligen Providers entspricht:
- OpenAI: `sk-[A-Za-z0-9]{48}`
- GitHub: `ghp_[A-Za-z0-9]{36}`
- Stripe: `sk_test_[A-Za-z0-9]{24}` oder `sk_live_[A-Za-z0-9]{24}`
- etc.

### 2. API-Tests
Für unterstützte Provider werden echte API-Anfragen durchgeführt:
- **OpenAI**: Listet verfügbare Models
- **GitHub**: Holt Benutzerprofil
- **Slack**: Testet Bot-Token
- **Stripe**: Prüft Account-Balance
- etc.

### Unterstützte Provider
OpenAI, Anthropic, Google, GitHub, Vercel, Slack, Discord, Stripe, Twilio, HuggingFace, Resend, SendGrid, Notion, Airtable

### Health-Reports
`keyring health` erstellt einen detaillierten Health-Report in `~/.keyring/health-report.json` mit Status für jeden Key:
- `healthy`: Key funktioniert
- `unhealthy`: Key fehlerhaft
- `unknown`: Kein Test verfügbar

## Sicherheit

- Verschlüsselung: AES-256-GCM
- Key-Ableitung: PBKDF2 mit 100.000 Iterationen
- Dateirechte: `~/.keyring/` mit `700`, Dateien mit `600`

## Hinweis zur Rotation

`rotate-all` generiert neue Platzhalter-Keys. Da die meisten Provider keine API zum Rotieren anbieten, musst du anschließend die **echten Keys** in den Provider-Dashboards (OpenAI, Vercel, etc.) neu erstellen und mit `keyring add` aktualisieren.
