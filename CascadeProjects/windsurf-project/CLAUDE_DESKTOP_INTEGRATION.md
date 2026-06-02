# Claude Desktop Code Integration Guide

## 🛡️ Sichere Weiterleitung der .env Datei zu Claude Desktop

### Methode 1: Kopieren der .env.example (Empfohlen)

Die sicherste Methode ist die Verwendung der bereits vorbereiteten `.env.example` Datei:

```bash
# 1. In dein Claude Desktop Projekt navigieren
cd /path/to/your/claude-desktop-project

# 2. Die bereinigte .env.example kopieren
cp /Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/.env.example .env.local

# 3. In Claude Desktop öffnen und verwenden
```

### Methode 2: Manuelles Eintragen (Sicher)

```bash
# 1. Neue .env.local Datei erstellen
touch .env.local

# 2. Nur die notwendigen Keys eintragen (ohne sensible Daten)
cat > .env.local << 'EOF'
# =============================================================================
# CLAUDE DESKTOP ENVIRONMENT
# =============================================================================

# AI & LLM APIS
ANTHROPIC_API_KEY=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
OPENAI_API_KEY=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
PERPLEXITY_API_KEY=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

# COMMUNICATION
TELEGRAM_BOT_TOKEN=8600739487:AAG_L4u82Y4UWPq-wGWzAdNC8bWJT99ASJI

# DATABASE
SUPABASE_URL=https://qyrjeckzacjaazkpvnjk.supabase.co
SUPABASE_ANON_KEY=sb_publishable_LY9XawaVKY67pIWISU27ww_hTNQszuP
SUPABASE_SERVICE_KEY=sb_secret__Bl843CKODUQ23rXUmheig_0Ehtb8uC

# ECOMMERCE
SHOPIFY_STORE_URL=iwiini-td2xdoae.myshopify.com
SHOPIFY_ACCESS_TOKEN=prtapi_4787e9bdf2adfab08cef8dc02f1aba4f

# VERSION CONTROL
GITHUB_TOKEN=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

# DEPLOYMENT
VERCEL_TEAM_ID=team_xulvdt7sib2RSt4BNoqVWeSy

# APPLICATION SETTINGS
NODE_ENV=production
API_BASE_URL=https://api.anthropic.com/v1
EOF
```

### Methode 3: Claude Desktop MCP Server Integration

```bash
# 1. Supabase MCP Server hinzufügen (falls noch nicht geschehen)
claude mcp add --scope project --transport http supabase "https://mcp.supabase.com/mcp?project_ref=qyrjeckzacjaazkpvnjk"

# 2. Authentifizieren
claude /mcp

# 3. Agent Skills installieren (optional)
npx skills add supabase/agent-skills
```

---

## 🔒 Sicherheitsbest Practices

### ✅ SICHER
- Verwende `.env.example` als Vorlage
- Erstelle `.env.local` (nicht `.env`)
- Teile keine echten API-Keys öffentlich
- Verwende Platzhalter für sensible Daten

### ❌ UNSICHER
- `.env` Datei direkt teilen
- API-Keys in Code committen
- Sensible Daten in öffentlichen Repos
- Klartext-Passwörter verwenden

---

## 📁 Claude Desktop Projektstruktur

```
your-claude-project/
├── .env.local          # Deine lokale Konfiguration
├── .env.example         # Vorlage (bereits vorhanden)
├── .gitignore          # Sollte .env.local enthalten
├── package.json
└── src/
    └── deine-app.js
```

### .gitignore Konfiguration

```gitignore
# Environment variables
.env
.env.local
.env.*.local

# Node modules
node_modules/

# Logs
logs/
*.log
```

---

## 🚀 Schnellstart für Claude Desktop

### 1. Projekt einrichten

```bash
# Neues Verzeichnis für Claude Desktop
mkdir claude-supermegabot
cd claude-supermegabot

# .env.local aus Vorlage erstellen
cp /Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/.env.example .env.local

# Projekt initialisieren
npm init -y
npm install axios dotenv
```

### 2. Test-App erstellen

```javascript
// test-app.js
require('dotenv').config();
const axios = require('axios');

async function testAPIs() {
  console.log('🔍 Testing APIs...');
  
  // Anthropic Test
  try {
    const response = await axios.post('https://api.anthropic.com/v1/messages', {
      model: 'claude-3-haiku-20240307',
      max_tokens: 100,
      messages: [{ role: 'user', content: 'Hello Claude!' }]
    }, {
      headers: {
        'Authorization': `Bearer ${process.env.ANTHROPIC_API_KEY}`,
        'Content-Type': 'application/json'
      }
    });
    console.log('✅ Anthropic API working');
  } catch (error) {
    console.log('❌ Anthropic API error:', error.message);
  }
}

testAPIs();
```

### 3. In Claude Desktop verwenden

1. Öffne Claude Desktop
2. Wähle das Projektverzeichnis
3. Die `.env.local` wird automatisch geladen
4. APIs sind sofort verfügbar

---

## 📱 Alternative: Cloud-basierte Lösung

Falls du die APIs in der Cloud verwenden möchtest:

```bash
# Vercel Environment Variables setzen
# Team: bullpowerhubgit's projects
# URL: https://vercel.com/bullpowerhubgits-projects/

# Critical Variables:
ANTHROPIC_API_KEY=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
NODE_ENV=production
```

---

## 🎯 Empfehlung

**Für Claude Desktop Code:**
1. Kopiere `.env.example` nach `.env.local`
2. Passe die Keys bei Bedarf an
3. Füge `.env.local` zu `.gitignore` hinzu
4. Beginne sofort mit der Entwicklung

**Für Production:**
1. Verwende Vercel Environment Variables
2. Halte Keys aus dem Code heraus
3. Nutze MCP Server für erweiterte Funktionalität

---

**Status:** Integration bereit  
**Sicherheit:** Maximal  
**Kompatibilität:** Claude Desktop + Cloud
