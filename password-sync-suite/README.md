# Password Sync Suite

Zentrale Passwort-Verwaltung und Gmail-Konto-Synchronisation.

## Features

- **Browser-Extension** (Chrome / Edge / Firefox)
  - Passwörter sicher im Browser speichern
  - AutoFill auf Webseiten mit Picker
  - Synchronisation mit der Web-App alle 15 Minuten
  - Unterstützung für alle 3 Gmail-Konten

- **Web-App** (Node.js / Express)
  - Google OAuth Login für die vordefinierten Gmail-Konten
  - Dashboard mit Sync-Status
  - REST API für Extension-Kommunikation

## Vordefinierte Gmail-Konten

- `dragonadnp@gmail.com`
- `aiitecbuuss@gmail.com`
- `bullpowersrtkennels@gmail.com`

## Installation

### 1. Web-App starten

```bash
cd password-sync-suite/web-app
cp .env.example .env
# .env anpassen: GOOGLE_CLIENT_ID und GOOGLE_CLIENT_SECRET eintragen
npm install
npm start
```

Die Web-App läuft dann auf `http://localhost:3005`.

### 2. Google OAuth einrichten

1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials) öffnen
2. Neues Projekt erstellen
3. "OAuth 2.0 Client ID" anlegen (Web-Anwendung)
4. Autorisierte Weiterleitungs-URI: `http://localhost:3005/auth/google/callback`
5. Client ID & Secret in `.env` eintragen

### 3. Browser-Extension laden

1. Chrome/Edge: `chrome://extensions` öffnen
2. "Entwicklermodus" aktivieren
3. "Entpackte Erweiterung laden" → `password-sync-suite/browser-extension` auswählen
4. Extension-Pin an die Toolbar anheften

## Verwendung

1. Klicke auf das Extension-Icon → "Konto hinzufügen"
2. Melde dich mit einem der erlaubten Gmail-Konten an
3. Speichere Passwörter über das Extension-Popup
4. Auf Login-Seiten erscheint automatisch ein 🔑-Button zum Ausfüllen

## Sicherheit

- Passwörter werden **nur lokal** im Browser-Storage gehalten
- Die Web-App speichert **keine** Passwörter (nur Metadaten für das Dashboard)
- OAuth über Google mit minimalen Scopes
- Session-Cookies mit `httpOnly` und `secure` (produktion)
