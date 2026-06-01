# API Integration Setup Guide

## Overview
Alle drei Systeme (QuickCashSystem, AutoShopSuite, ArbitrageSystem) sind jetzt mit einer zentralen API-Konfiguration verbunden. Die Systeme laden automatisch die API-Keys aus `api-config.json` und verwenden diese für direkte API-Calls.

## Dateien

### 1. api-config.json
Zentrale Konfigurationsdatei für alle API-Keys. Enthält Konfigurationen für:
- **Anthropic/Claude**: Haupt-AI-Modell für alle Systeme
- **OpenAI**: Alternative AI-Modelle
- **Fiverr**: Freelance-Plattform API
- **Upwork**: Freelance-Plattform API
- **Etsy**: E-Commerce API
- **Shopify**: E-Commerce API
- **Printful**: Print-on-Demand API
- **AliExpress**: Dropshipping API

### 2. api-client.js
Unified API Client für alle Systeme. Unterstützt:
- Rate Limiting
- Caching
- Fehlerbehandlung
- Multi-API-Unterstützung

### 3. React-Komponenten
- **QuickCashSystem_1.jsx**: AI Service Arbitrage Tools
- **AutoShopSuite_fixed.tsx**: POD & Dropshipping Suite
- **arbitrage_system_1.jsx**: AI Service Arbitrage System

## Konfiguration

### Schritt 1: API-Keys eintragen

Öffne `api-config.json` und trage deine API-Keys ein:

```json
{
  "anthropic": {
    "apiKey": "sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "baseUrl": "https://api.anthropic.com/v1",
    "version": "2023-06-01",
    "model": "claude-sonnet-4-5",
    "maxTokens": 4096
  }
}
```

### Schritt 2: API-Keys erhalten

**Anthropic Claude:**
1. Gehe zu https://console.anthropic.com/
2. Erstelle ein Konto oder logge dich ein
3. Gehe zu API Keys → Create Key
4. Kopiere den Key und füge ihn in `api-config.json` ein

**OpenAI:**
1. Gehe zu https://platform.openai.com/api-keys
2. Erstelle einen neuen API Key
3. Kopiere den Key in `api-config.json`

**Andere APIs:**
- Fiverr: https://developers.fiverr.com/
- Upwork: https://developers.upwork.com/
- Etsy: https://developers.etsy.com/
- Shopify: https://partners.shopify.com/
- Printful: https://developers.printful.com/
- AliExpress: https://developers.aliexpress.com/

## Verwendung

### QuickCashSystem
1. Öffne `QuickCashSystem_1.jsx` im Browser
2. Das System lädt automatisch `api-config.json`
3. Wähle ein Tool (z.B. AI Service Arbitrage)
4. Klicke auf "Generieren"
5. Die API-Antwort wird angezeigt mit Token- und Kosten-Tracking

### AutoShopSuite
1. Öffne `AutoShopSuite_fixed.tsx` im Browser
2. Das System lädt automatisch `api-config.json`
3. Wähle einen Workflow (Nischenanalyse, Design-Prompt, etc.)
4. Klicke auf "Generieren"
5. Die API-Antwort wird angezeigt

### ArbitrageSystem
1. Öffne `arbitrage_system_1.jsx` im Browser
2. Das System lädt automatisch `api-config.json`
3. Wähle ein Modul (Fiverr Gig, Upwork Proposal, etc.)
4. Fülle die Felder aus
5. Klicke auf "Starten"
6. Die API-Antwort wird angezeigt

## Kosten-Tracking

Alle Systeme tracken automatisch:
- **Input Tokens**: Anzahl der Eingabe-Tokens
- **Output Tokens**: Anzahl der Ausgabe-Tokens
- **Kosten**: Berechnet nach Anthropic-Preisen ($3/1M Input, $15/1M Output)

## Fehlerbehandlung

### API-Key nicht gefunden
Wenn der API-Key fehlt, wird eine Fehlermeldung angezeigt:
```
Bitte zuerst Anthropic API-Key eingeben
```

### API-Fehler
Wenn die API einen Fehler zurückgibt, wird die Fehlermeldung angezeigt:
```
API-Fehler: [Fehlermeldung]
```

### Fallback-Verhalten
Wenn `api-config.json` nicht gefunden wird oder kein API-Key enthält, verwenden die Systeme ihre Standardwerte oder zeigen eine Fehlermeldung an.

## Sicherheit

- **NIEMALS** API-Keys in Git-Repositories committen
- `api-config.json` sollte in `.gitignore` stehen
- Teile API-Keys nicht öffentlich
- Rotiere API-Keys regelmäßig

## Erweiterte Konfiguration

### Model-Auswahl
Ändere das Modell in `api-config.json`:
```json
{
  "anthropic": {
    "model": "claude-sonnet-4-5"  // oder "claude-3-opus", "claude-3-haiku"
  }
}
```

### Token-Limits
Ändere die maximalen Tokens:
```json
{
  "anthropic": {
    "maxTokens": 8192  // für längere Antworten
  }
}
```

## Support

Bei Problemen:
1. Prüfe, ob `api-config.json` im selben Verzeichnis liegt wie die React-Komponenten
2. Prüfe, ob der API-Key korrekt ist
3. Prüfe, ob du genügend Guthaben auf der API-Plattform hast
4. Prüfe die Browser-Konsole auf Fehlermeldungen

## Lizenz

Diese Integration ist für den persönlichen Gebrauch bestimmt. Beachte die Nutzungsbedingungen der jeweiligen API-Plattformen.
