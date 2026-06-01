# API Key Erneuerungs-Anleitungen
**Erstellt:** 2026-05-30

## 🔑 Shopify API Token Erneuern

### Schritt-für-Schritt Anleitung

1. **Login bei Shopify Admin**
   - Gehe zu: https://admin.shopify.com/store/suite-8091/
   - Login mit deinen Shopify Admin Credentials

2. **Private App erstellen/verwalten**
   - Navigiere zu: Apps > Manage private apps
   - Klicke auf "Create an app" oder wähle eine existierende App
   - App Name: `SuperMegaBot Integration` (oder ähnlich)
   - App developer email: Deine E-Mail

3. **Admin API Scopes konfigurieren**
   Aktiviere folgende Scopes für volle Funktionalität:
   - `read_products` - Produkte lesen
   - `write_products` - Produkte erstellen/bearbeiten
   - `read_orders` - Bestellungen lesen
   - `write_orders` - Bestellungen erstellen/bearbeiten
   - `read_inventory` - Inventar lesen
   - `write_inventory` - Inventar verwalten
   - `read_locations` - Standorte lesen
   - `read_content` - Inhalte lesen
   - `write_content` - Inhalte erstellen

4. **Access Token generieren**
   - Scrolle nach unten zu "Admin API access token"
   - Klicke auf "Configure Admin API scopes"
   - Wähle die oben genannten Scopes
   - Klicke auf "Install app"
   - Kopiere den generierten **Admin API access token**

5. **Token in System aktualisieren**
   - Öffne `api-config.json`
   - Ersetze den alten Token unter `shopify.apiKey`
   - Öffne `RudiBot-Secure-API/api-keys.txt`
   - Ersetze `SHOPIFY_ACCESS_TOKEN` mit dem neuen Token
   - Speichere beide Dateien

6. **Testen**
   - Führe aus: `node api-validator.cjs`
   - Shopify sollte jetzt Status 200 zurückgeben

### Wichtige Hinweise
- Shopify Tokens haben kein Ablaufdatum, aber können widerrufen werden
- Bewahre den Token sicher auf (nicht in Git committen)
- Der Token sollte mit `shpat_` beginnen

---

## 🎨 Etsy API Key Erneuern

### Schritt-für-Schritt Anleitung

1. **Login bei Etsy Developer Portal**
   - Gehe zu: https://developer.etsy.com/my-apps
   - Login mit deinem Etsy Account

2. **App Status prüfen**
   - Suche nach deine existierende App
   - Prüfe ob der Status "Active" ist
   - Wenn nicht, reaktiviere die App

3. **API Key String erneuern**
   - Klicke auf deine App
   - Scrolle zu "API Key (Keystring)"
   - Klicke auf "Regenerate Key String" falls verfügbar
   - Oder notiere den aktuellen Key String

4. **Shared Secret prüfen**
   - Notiere auch das "Shared Secret"
   - Beide werden für OAuth Signatur benötigt

5. **Key in System aktualisieren**
   - Öffne `api-config.json`
   - Ersetze unter `etsy.apiKey` den neuen Key String
   - Ersetze unter `etsy.sharedSecret` das neue Secret
   - Speichere die Datei

6. **Testen**
   - Führe aus: `node api-validator.cjs`
   - Etsy sollte jetzt Status 200 zurückgeben

### Wichtige Hinweise
- Etsy API Keys können ablaufen - regelmäßig prüfen
- Key String und Shared Secret müssen zusammenpassen
- Die App muss im "Production" Status sein für Live-Zugriff

---

## 🤖 Perplexity API Endpoint Korrigieren

### Problem
Der aktuelle Test verwendet `/models` Endpoint, der möglicherweise nicht existiert.

### Lösung

1. **Korrekten Endpoint verwenden**
   - Perplexity verwendet standardmäßig `/chat/completions`
   - Für Model-Informationen gibt es keinen öffentlichen Endpoint

2. **Validator-Skript aktualisieren**
   - Öffne `api-validator.cjs`
   - Suche die `testPerplexity()` Funktion
   - Ersetze den Endpoint von `/models` mit `/chat/completions`
   - Füge einen einfachen Test-Request hinzu

3. **Alternativ: Perplexity API Key prüfen**
   - Gehe zu: https://www.perplexity.ai/settings/api
   - Prüfe ob dein API Key noch aktiv ist
   - Generiere bei Bedarf einen neuen Key

4. **Testen**
   - Führe aus: `node api-validator.cjs`
   - Perplexity sollte jetzt Status 200 zurückgeben

### Korrigierter Code für api-validator.cjs

```javascript
async function testPerplexity() {
  logSection('Testing Perplexity API');
  
  const apiKey = apiConfig.perplexity.apiKey;
  
  log(`API Key: ${apiKey.substring(0, 10)}...`, 'blue');
  
  try {
    // Use chat completions endpoint instead of models
    const response = await makeRequest('https://api.perplexity.ai/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      }
    });
    
    // Since we can't send a body in makeRequest, we'll just check auth
    // A 401 means invalid key, 422 means missing body (expected), 200+ means key is valid
    if (response.statusCode === 401) {
      log('❌ Perplexity API key is invalid', 'red');
      return false;
    } else if (response.statusCode === 422 || response.statusCode === 400) {
      log('✅ Perplexity API key is valid (endpoint accessible)', 'green');
      log(`Status: ${response.statusCode} (expected - missing request body)`, 'green');
      return true;
    } else {
      log(`⚠️ Perplexity API returned status ${response.statusCode}`, 'yellow');
      return false;
    }
  } catch (error) {
    log(`❌ Perplexity API test failed: ${error.message}`, 'red');
    return false;
  }
}
```

---

## 📦 Printful API Key Erneuern

### Schritt-für-Schritt Anleitung

1. **Login bei Printful Dashboard**
   - Gehe zu: https://www.printful.com/dashboard
   - Login mit deinen Printful Credentials

2. **API Settings öffnen**
   - Klicke auf "Store" im Menü
   - Wähle deinen Store aus
   - Navigiere zu "Settings" > "API"

3. **API Key erneuern**
   - Scrolle zu "API Key"
   - Klicke auf "Regenerate" oder "Create new key"
   - Gib dem Key einen Namen: `SuperMegaBot Integration`
   - Kopiere den generierten API Key

4. **Key in System aktualisieren**
   - Öffne `api-config.json`
   - Ersetze unter `printful.apiKey` den neuen Key
   - Der Key sollte mit `pplx-` beginnen
   - Speichere die Datei

5. **Testen**
   - Führe aus: `node api-validator.cjs`
   - Printful sollte jetzt Status 200 zurückgeben

### Wichtige Hinweise
- Printful API Keys können jederzeit neu generiert werden
- Der alte Key wird sofort ungültig nach Generierung eines neuen
- Bewahre den Key sicher auf

---

## 🚀 Schnell-Update-Skript

Nachdem du die neuen Keys besorgt hast, kannst du das Update-Skript verwenden:

```bash
node api-update-helper.cjs
```

Dieses Skript wird:
1. Alle API-Keys in `api-config.json` aktualisieren
2. Die Keys in `RudiBot-Secure-API/api-keys.txt` synchronisieren
3. Einen Validierungstest durchführen
4. Bericht über den Status generieren

---

## 📋 Checkliste

- [ ] Shopify Token erneuert und in beiden Dateien aktualisiert
- [ ] Etsy API Key String erneuert und aktualisiert
- [ ] Perplexity Endpoint im Validator korrigiert
- [ ] Printful API Key erneuert und aktualisiert
- [ ] `node api-validator.cjs` ausgeführt - alle APIs zeigen 200
- [ ] System bereit für Nutzung

---

## 🔗 Nützliche Links

- Shopify Admin: https://admin.shopify.com/store/suite-8091/
- Etsy Developer Portal: https://developer.etsy.com/my-apps
- Perplexity Settings: https://www.perplexity.ai/settings/api
- Perplexity Docs: https://docs.perplexity.ai/
- Printful Dashboard: https://www.printful.com/dashboard
