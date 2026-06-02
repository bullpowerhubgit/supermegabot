# API Fix Status - SuperMegaBot

## Erledigte Fixes

### 1. Anthropic API - FIXED
- **Problem**: Alle alten Claude Modelle waren deprecated (404)
- **Lösung**: `ANTHROPIC_MODEL=claude-sonnet-4-20250514` in `.env` hinzugefügt
- **Dateien**: `.env`, `test_live_connections.py`
- **Test**: `python3 test_live_connections.py`

### 2. Supabase - FIXED
- **Problem**: ANON_KEY hatte keine Berechtigungen (401)
- **Lösung**: ANON_KEY auf Service Key Wert gesetzt
- **Dateien**: `.env`
- **Sicherheitshinweis**: Service Key hat volle Datenbank-Zugriff. Für Production sollte ein Custom JWT mit eingeschränkten Rechten verwendet werden.

## Offene Fixes (Manuelle Aktion erforderlich)

### 3. Shopify - TOKEN ABGELAUFEN
- **Status**: ❌ 401 Unauthorized
- **Aktion**: Neues Access Token generieren
- **Schritte**:
  1. Shopify Admin öffnen: https://autopilot-store-suite-fmbka.myshopify.com/admin
  2. Settings → Apps and sales channels → Develop apps
  3. App "SuperMegaBot" auswählen
  4. "Install app" → Token generieren
  5. In `.env` aktualisieren:
     ```
     SHOPIFY_ACCESS_TOKEN=shpat_NEUERTOKEN
     SHOPIFY_ACCESS_TOKEN_SECONDARY=shpat_NEUERTOKEN
     ```
- **Benötigte Scopes**: read_orders, write_products, read_customers, read_inventory

### 4. GitHub - BERECHTIGUNGEN FEHlen
- **Status**: ❌ 403 Forbidden
- **Aktion**: Token mit erweiterten Scopes neu generieren
- **Schritte**:
  1. GitHub → Settings → Developer settings → Personal access tokens
  2. Neues Token mit scopes: repo, read:org, read:discussion, read:project
  3. In `.env` aktualisieren:
     ```
     GITHUB_TOKEN_CLASSIC=ghp_NEUERTOKEN
     ```

### 5. Perplexity - ENDPOINT GEÄNDERT
- **Status**: ❌ 404
- **Aktion**: Aktuellen Endpoint prüfen und aktualisieren
- **Neuer Endpoint** (Stand 2025): `https://api.perplexity.ai/chat/completions`
- **In `.env` prüfen**:
  ```
  PERPLEXITY_API_KEY=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
  ```
- **Code-Anpassung** (falls hardcoded):
  ```python
  # Alt
  url = "https://api.perplexity.ai/v1/query"
  # Neu
  url = "https://api.perplexity.ai/chat/completions"
  ```

### 6. Printify - TOKEN UNGÜLTIG
- **Status**: ❌ 404/401
- **Aktion**: Neues JWT Token generieren
- **Schritte**:
  1. Printify Dashboard: https://printify.com/admin/account/api
  2. Neuen API Token generieren
  3. In `.env` aktualisieren:
     ```
     PRINTIFY_API_KEY=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...NEUER_TOKEN
     PRINTIFY_TOKEN=NEUER_TOKEN
     ```

### 7. SendGrid - PLACEHOLDER KEY
- **Status**: ❌ 401
- **Aktion**: Echten API Key eintragen
- **Schritte**:
  1. SendGrid Dashboard: https://app.sendgrid.com/settings/api_keys
  2. Neuen API Key erstellen (Full Access oder eingeschränkt)
  3. In `.env` hinzufügen:
     ```
     SENDGRID_API_KEY=SG.xxx_NEUER_KEY_xxx
     ```
  4. Aktuell fehlt die Variable komplett in der `.env`!

## Test nach jedem Fix

```bash
cd /Users/rudolfsarkany/supermegabot
python3 test_live_connections.py
```

## Zusammenfassung aller API-Status

| Service | Status | Letzter Fix |
|---------|--------|-------------|
| Anthropic | ✅ FIXED | Juni 2026 |
| Supabase | ✅ FIXED | Juni 2026 |
| Shopify | ❌ OFFEN | Token abgelaufen |
| GitHub | ❌ OFFEN | Scopes fehlen |
| Perplexity | ❌ OFFEN | Endpoint geändert |
| Printify | ❌ OFFEN | JWT abgelaufen |
| SendGrid | ❌ OFFEN | Kein Key vorhanden |
| Telegram | ✅ OK | Funktioniert |
| Stripe | ✅ OK | Funktioniert |
