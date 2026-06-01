# GCP Cloud Function Deployment Guide

## Project: gen-lang-client-0895465231

### Voraussetzungen

```bash
# gcloud CLI installiert und authentifiziert
gcloud auth login
gcloud config set project gen-lang-client-0895465231
```

### Deployment

```bash
cd gcp-cloud-function
npm install

# Environment Variable setzen
export ANTHROPIC_API_KEY=sk-ant-api03-DEIN_KEY_HIER

# Deploy
npm run deploy
```

### Alternative: Vertex AI Integration

Da Vertex AI bereits aktiviert ist, kannst du auch direkt Vertex AI Modelle verwenden:

```javascript
const { VertexAI } = require('@google-cloud/vertexai');

const vertexAI = new VertexAI({
  project: 'gen-lang-client-0895465231',
  location: 'us-central1'
});

const model = vertexAI.preview.getGenerativeModel({
  model: 'gemini-1.5-pro'
});
```

### Vorteile GCP vs Vercel

- **GCP**: Vertex AI bereits aktiviert, bessere Integration mit Google Services
- **Vercel**: Einfacheres Deployment, kostenlos für Hobby-Plan

### Empfehlung

Wenn du Vertex AI Modelle verwenden willst → GCP Cloud Function  
Wenn du bei Anthropic bleiben willst → Vercel (einfacher)
