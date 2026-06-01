# Railway → Vercel Migration - Vollständige Anleitung

## ✅ Status: Bereit für Deployment

Alle Dateien sind erstellt und konfiguriert. Du kannst jetzt deployen.

---

## 📋 Was wurde erstellt

### 1. API Route mit Fehlerbehandlung
**Datei:** `api/claude.ts`
- CORS Headers konfiguriert
- API Key Validierung
- Detaillierte Fehlerbehandlung
- Logging für Debugging

### 2. Vercel Konfiguration
**Datei:** `vercel.json`
- Function Settings (1024MB Memory, 10s Timeout)
- CORS Headers global
- Rewrites für API Routes

### 3. Environment Template
**Datei:** `.env.example`
- Alle benötigten API Keys aufgelistet
- Kommentare für jede Variable
- Einfach zu kopieren und auszufüllen

### 4. Deploy Script
**Datei:** `deploy-vercel.sh`
- Automatische Vercel CLI Installation
- Environment Check
- Ein-Klick Deployment

---

## 🚀 Deployment (3 Wege)

### Weg A: Automatisches Script (Empfohlen)

```bash
# Script ausführbar machen
chmod +x deploy-vercel.sh

# Ausführen
./deploy-vercel.sh
```

Das Script:
- Installiert Vercel CLI automatisch
- Prüft ob .env.local existiert
- Validiert ANTHROPIC_API_KEY
- Deployt auf Vercel

### Weg B: Manuelles Deployment

```bash
# 1. Vercel CLI installieren
npm install -g vercel

# 2. Environment Variables setzen
cp .env.example .env.local
# .env.local mit deinen echten Keys bearbeiten

# 3. Deployen
vercel --prod
```

### Weg C: Über GitHub (Automatisch bei Push)

1. `.env.example` zu `.env.local` kopieren und ausfüllen
2. GitHub Repo pushen
3. Auf vercel.com → "Add New Project" → Import Repo
4. Environment Variables im Vercel Dashboard setzen

---

## 🔑 Environment Variables (WICHTIG)

In Vercel Dashboard (Settings → Environment Variables) setzen:

```
ANTHROPIC_API_KEY=sk-ant-api03-DEIN_KEY_HIER
```

**Optional (für erweiterte Funktionen):**
```
PERPLEXITY_API_KEY=pplx-DEIN_KEY_HIER
SHOPIFY_ACCESS_TOKEN=shpat_DEIN_TOKEN_HIER
TELEGRAM_BOT_TOKEN=DEIN_BOT_TOKEN_HIER
```

---

## ✅ Verification

### 1. API testen

```bash
# Ersetze DEINE-URL mit deiner Vercel URL
curl -X POST https://DEINE-URL.vercel.app/api/claude \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Hallo"}]
  }'
```

Erwartete Antwort:
```json
{
  "id": "...",
  "type": "message",
  "role": "assistant",
  "content": [...]
}
```

### 2. AutoShop Suite testen

1. Öffne deine AutoShop Suite
2. Settings Tab
3. API Verbindung testen
4. Sollte ✅ anzeigen

---

## 🗑️ Railway Kündigen

**NACHDEM Vercel API funktioniert:**

1. Gehe zu [railway.app/account/billing](https://railway.app/account/billing)
2. Projekte auflisten:
   - `shopify-automation-api` → kündigen
   - `postgres-optimizer` → löschen (falls nicht mehr benötigt)
3. Bestätige die Kündigung

---

## 💰 Kostensparen

### Railway (vorher)
- ~$5-10/Monat für crashende Services
- Beide Projekte crashen seit Wochen

### Vercel (nachher)
- **Hobby Plan: $0/Monat**
- 100GB Bandbreite/Monat
- 100GB-Hours Serverless Functions/Monat
- Unbegrenzte API Calls (innerhalb Limits)

**Ersparnis: ~$60-120/Jahr**

---

## 📁 Datei-Struktur

```
windsurf-project/
├── api/
│   └── claude.ts              # ✅ API Route (verbessert)
├── vercel.json                # ✅ Vercel Konfiguration
├── .env.example               # ✅ Environment Template
├── deploy-vercel.sh           # ✅ Deploy Script
├── DEPLOY_VERCEL_GUIDE.md     # ✅ Diese Anleitung
└── RAILWAY_TO_VERCEL_MIGRATION.md  # ✅ Ursprüngliche Migration Doku
```

---

## 🐛 Troubleshooting

### Fehler: "ANTHROPIC_API_KEY not configured"
- Prüfe Vercel Environment Variables
- Stelle sicher, dass die Variable in allen Umgebungen gesetzt ist (Production, Preview, Development)

### Fehler: "CORS error"
- Die API Route hat bereits CORS Headers
- Prüfe ob die Frontend-URL korrekt ist

### Fehler: "502 Bad Gateway"
- Anthropic API könnte temporär down sein
- Prüfe deinen API Key Gültigkeit auf console.anthropic.com

### Fehler: "404 Not Found"
- Prüfe ob `api/claude.ts` im Root-Verzeichnis liegt
- Bei Next.js: sollte in `pages/api/claude.ts` oder `app/api/claude/route.ts` liegen

---

## 🎯 Zusammenfassung

✅ **Vercel API Route erstellt** (mit Fehlerbehandlung)  
✅ **Vercel Konfiguration erstellt**  
✅ **Environment Template erstellt**  
✅ **Deploy Script erstellt**  
✅ **Anleitung erstellt**  

⏳ **Deploy auf Vercel** (nutze `deploy-vercel.sh`)  
⏳ **Environment Variables setzen** (ANTHROPIC_API_KEY)  
⏳ **API testen**  
⏳ **Railway kündigen**

---

## 📞 Support

Falls Probleme:
1. Vercel Logs checken: `vercel logs`
2. Environment Variables prüfen
3. API Key auf console.anthropic.com validieren

Viel Erfolg! 🚀
