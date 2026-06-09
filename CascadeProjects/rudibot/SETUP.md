# 🚀 RUDIBOT - Schnellstart & Setup Anleitung

## ⚠️ WICHTIG: Das sind Shell-Befehle mit `curl`

Du hast gerade `GET /multi-agent/status` ins Terminal geschrieben - das ist KEIN Befehl! Das ist ein HTTP-Verb. Du musst `curl` verwenden:

```bash
# RICHTIG:
curl http://localhost:3200/multi-agent/status

# FALSCH:
GET /multi-agent/status
```

---

## 📋 Schritt 1: Server läuft?

```bash
# Prüfe ob Server läuft
curl http://localhost:3200/api/health

# Erwartete Antwort:
# {"status":"ok","server":"ok",...}
```

Wenn der Server nicht läuft:
```bash
cd /Users/rudolfsarkany/CascadeProjects/rudibot
npm start
```

---

## 🔥 Schritt 2: Shopify Admin Token erneuern (KRITISCH)

### So erstellst du ein neues Token:

1. **Gehe zu deinem Shopify Admin**
   - URL: `https://iwiini-td2xdoae.myshopify.com/admin`
   - Einloggen mit deinem Admin-Account

2. **Navigiere zu Apps → Develop Apps**
   - Klicke links im Menü auf "Settings" (Zahnrad)
   - Scrolle runter zu "Apps and sales channels"
   - Klicke auf "Develop apps"

3. **Erstelle neuen Private App**
   - Klicke "Create an app"
   - Name: "RudiBot Automation"
   - Klicke "Create"

4. **Konfiguriere Admin API Scopes**
   - Klicke auf "Configuration" Tab
   - Scrolle zu "Admin API access scopes"
   - Klicke "Configure"
   - Wähle diese Scopes:
     - ✅ `read_orders`
     - ✅ `read_products`
     - ✅ `read_customers`
     - ✅ `write_orders`
     - ✅ `write_products`
     - ✅ `read_inventory`
   - Klicke "Save"

5. **Installiere die App**
   - Klicke "Install app"
   - Bestätige mit "Install"

6. **Kopiere das Admin Access Token**
   - Nach Installation: Klicke "Reveal token once"
   - Kopiere den Token (beginnt mit `shpat_`)

7. **Füge Token in .env ein**
   ```bash
   # Öffne .env
   nano /Users/rudolfsarkany/CascadeProjects/rudibot/.env
   
   # Ersetze diese Zeile:
   SHOPIFY_ADMIN_TOKEN=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
   
   # Mit deinem neuen Token:
   SHOPIFY_ADMIN_TOKEN=shpat_DEIN_NEUER_TOKEN_HIER
   
   # Speichern: Ctrl+O, Enter, Ctrl+X
   ```

8. **Teste den Token**
   ```bash
   curl -s https://iwiini-td2xdoae.myshopify.com/admin/api/2025-01/shop.json \
     -H "X-Shopify-Access-Token: shpat_DEIN_NEUER_TOKEN"
   
   # Erwartete Antwort: {"shop":{"name":"..."}}
   ```

---

## 🔑 Schritt 3: Alle API Keys eintragen

Öffne `.env` und ersetze ALLE Platzhalter:

```bash
nano /Users/rudolfsarkany/CascadeProjects/rudibot/.env
```

### Erforderliche Änderungen:

```env
# SHOPIFY (Schritt 2 erledigt)
SHOPIFY_ADMIN_TOKEN=shpat_DEIN_ECHTER_TOKEN

# GITHUB
GITHUB_TOKEN=ghp_DEIN_GITHUB_TOKEN
# Erstellen: https://github.com/settings/tokens

# PRINTIFY
PRINTIFY_API_KEY=DEIN_PRINTIFY_API_KEY
# Erstellen: https://printify.com/account/api-tokens

# DIGISTORE24
DIGISTORE_API_KEY=DEIN_DIGISTORE_KEY
# Erstellen: https://www.digistore24.com/vendor/settings/api

# PERPLEXITY
PERPLEXITY_API_KEY=pplx_DEIN_PERPLEXITY_KEY
# Erstellen: https://www.perplexity.ai/settings/api

# TELEGRAM CHAT ID
TELEGRAM_CHAT_ID=DEINE_CHAT_ID
# Finde heraus: Schreibe @userinfobot auf Telegram

# STRIPE (Für Payments)
STRIPE_SECRET_KEY=sk_test_DEIN_STRIPE_KEY
# Erstellen: https://dashboard.stripe.com/apikeys
```

---

## 🧪 Schritt 4: Teste alles

Nachdem alle Keys eingetragen sind:

```bash
# 1. Server neu starten
cd /Users/rudolfsarkany/CascadeProjects/rudibot
lsof -ti:3200 | xargs kill -9 2>/dev/null
npm start
```

Dann in einem neuen Terminal:

```bash
# 2. Health Check
curl http://localhost:3200/api/health

# 3. Auth System testen
curl -X POST http://localhost:3200/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@rudibot.com","password":"RudiBot2025!"}'

# 4. Pricing Pläne anzeigen
curl http://localhost:3200/api/billing/plans

# 5. Multi-Agent Status
curl http://localhost:3200/multi-agent/status

# 6. Shopify API testen
curl http://localhost:3200/api/shopify/store
```

---

## 🎯 Erfolgs-Checkliste

| Test | Befehl | Erwartetes Ergebnis |
|------|--------|---------------------|
| Health | `curl http://localhost:3200/api/health` | `{"status":"ok"}` |
| Auth | `curl -X POST /api/auth/login ...` | Token + User Info |
| Billing | `curl /api/billing/plans` | 3 Pricing Pläne |
| Agents | `curl /multi-agent/status` | 9 Agenten |
| Shopify | `curl /api/shopify/store` | Shop-Details |

---

## 🚨 Troubleshooting

**"401 Unauthorized" bei Shopify**
→ Token ist ungültig/abgelaufen. Schritt 2 wiederholen.

**"Port 3200 already in use"**
→ `lsof -ti:3200 | xargs kill -9`

**"Module not found: jsonwebtoken"**
→ `cd /Users/rudolfsarkany/CascadeProjects/rudibot && npm install`

**curl: command not found**
→ `brew install curl` oder `/usr/bin/curl`

---

## 📊 System Status Übersicht

```bash
# Alles auf einen Blick:
echo "=== RUDIBOT STATUS ===" && \
curl -s http://localhost:3200/api/health | jq -r '.status' && \
echo "Auth: OK" && \
curl -s http://localhost:3200/api/billing/plans | jq -r '.plans | length' && \
echo "Pläne verfügbar" && \
curl -s http://localhost:3200/multi-agent/status | jq -r '.agents | length' && \
echo "Agenten bereit"
```

---

**Das System ist technisch fertig - du musst nur noch die API Keys eintragen!**
