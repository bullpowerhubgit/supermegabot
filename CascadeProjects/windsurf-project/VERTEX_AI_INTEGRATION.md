# Vertex AI Integration Guide

## Warum Vertex AI statt Anthropic?

### Vorteile
- **Keine Anthropic API Kosten** → Google Cloud Billing bereits aktiviert
- **Vertex AI bereits aktiviert** in deinem Projekt (gen-lang-client-0895465231)
- **Bessere Integration** mit Google Services (Storage, Logging, etc.)
- **Höhere Limits** für Enterprise-Features

### Nachteile
- **Code Anpassung** nötig (API Format unterschiedlich)
- **Andere Modelle** (Gemini statt Claude)

---

## Deployment

### Schritt 1: Dependencies installieren

```bash
cd gcp-cloud-function
npm install
```

### Schritt 2: Vertex AI Cloud Function deployen

```bash
npm run deploy
```

Dies deployt `vertex-ai-proxy.js` mit:
- Model: gemini-1.5-pro
- Location: us-central1
- Project: gen-lang-client-0895465231

### Schritt 3: URL erhalten

Nach Deployment erhältst du eine URL wie:
```
https://europe-west1-gen-lang-client-0895465231.cloudfunctions.net/vertexAIProxy
```

---

## AutoShop Suite anpassen

### In AutoShopSuite_fixed.tsx:

```typescript
// Vorher (Anthropic)
const proxyUrl = '/api/claude';

// Nachher (Vertex AI)
const proxyUrl = 'https://europe-west1-gen-lang-client-0895465231.cloudfunctions.net/vertexAIProxy';
```

### Model Konfiguration:

```typescript
// Vorher
model: 'claude-sonnet-4-20250514'

// Nachher
model: 'gemini-1.5-pro'
```

---

## Kostenvergleich

### Anthropic API
- ~$3/Million Input Tokens
- ~$15/Million Output Tokens
- Monatliche Kosten: ~$20-50 (je nach Nutzung)

### Vertex AI (Gemini 1.5 Pro)
- ~$1/Million Input Tokens
- ~$3/Million Output Tokens
- Monatliche Kosten: ~$5-15 (je nach Nutzung)

**Ersparnis: ~75%**

---

## Verfügbare Modelle

```javascript
// Gemini 1.5 Pro (Balanced)
'gemini-1.5-pro'

// Gemini 1.5 Flash (Faster, Cheaper)
'gemini-1.5-flash'

// Gemini 1.0 Pro (Legacy)
'gemini-1.0-pro'
```

---

## Testing

```bash
# Test mit curl
curl -X POST https://DEINE-URL.cloudfunctions.net/vertexAIProxy \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hallo"}],
    "max_tokens": 100
  }'
```

---

## Fallback zu Anthropic

Falls du wieder zu Anthropic wechseln willst:

```bash
npm run deploy-anthropic
```

Dies deployt die ursprüngliche Anthropic Version.

---

## Railway Kündigung

Nach erfolgreicher Vertex AI Integration:

1. Railway Projekte löschen (siehe RAILWAY_CANCELLATION_GUIDE.md)
2. Vercel nicht nötig (Vertex AI läuft auf GCP)
3. Ersparnis: ~$100/Jahr (Railway) + ~75% API Kosten

---

## Zusammenfassung

✅ Vertex AI bereits aktiviert  
✅ Cloud Function erstellt  
✅ Anthropic-kompatibles Format  
✅ Kostenersparnis ~75%  

⏳ Deploy auf GCP  
⏳ AutoShop Suite URL anpassen  
⏳ Railway kündigen
