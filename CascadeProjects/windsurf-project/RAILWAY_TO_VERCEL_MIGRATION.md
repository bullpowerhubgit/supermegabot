# Railway → Vercel Migration Guide

## Status: ✅ Vorbereitet

Die AutoShop Suite ist bereits für Vercel optimiert. Die API-Route wurde erstellt und der Code verwendet bereits die korrekte URL-Struktur.

---

## Was wurde gemacht

### 1. Vercel API Route erstellt
**Datei:** `api/claude.ts`

Diese Datei fungiert als Proxy zur Anthropic API und ist Vercel-kompatibel.

### 2. Code-Analyse
- Die AutoShop Suite verwendet bereits `/api/claude` als Standard-Proxy-URL
- Keine Railway-URLs im Code gefunden (bereits Vercel-ready)
- Der Code in `AutoShopSuite_fixed.tsx` ist bereits korrekt konfiguriert

---

## Nächste Schritte

### Schritt 1: Vercel Projekt Setup

1. **GitHub Repository vorbereiten**
   - Stelle sicher, dass `api/claude.ts` in deinem GitHub Repo ist
   - Die Datei muss im Root-Verzeichnis oder in `pages/api/` liegen (je nach Vercel-Konfiguration)

2. **Vercel Projekt erstellen**
   - Gehe zu [vercel.com](https://vercel.com)
   - "Add New Project" → Import dein GitHub Repo
   - Wähle "Next.js" als Framework (oder "Other" für reine API)

3. **Environment Variables setzen**
   - In Vercel Dashboard: Settings → Environment Variables
   - Füge hinzu: `ANTHROPIC_API_KEY` = dein Anthropic API Key
   - Wichtig: Wähle "Production", "Preview", und "Development"

### Schritt 2: Deployen

```bash
# Option A: Über Vercel CLI
npm install -g vercel
vercel

# Option B: Über GitHub (automatisch bei Push)
git add api/claude.ts
git commit -m "Add Vercel API route for Claude proxy"
git push
```

### Schritt 3: URL aktualisieren (falls nötig)

Wenn deine AutoShop Suite eine andere URL als `/api/claude` verwendet:

1. Öffne `AutoShopSuite_fixed.tsx`
2. Suche nach `proxyUrl: '/api/claude'` (Zeile 202)
3. Falls eine andere URL verwendet wird, ersetze sie mit deiner Vercel-URL:
   ```
   proxyUrl: 'https://dein-vercel-projekt.vercel.app/api/claude'
   ```

### Schritt 4: Railway kündigen

Sobald die Vercel-App läuft:

1. Gehe zu [railway.app/account/billing](https://railway.app/account/billing)
2. Kündige das `shopify-automation-api` Projekt
3. Lösche das `postgres-optimizer` Projekt (falls nicht mehr benötigt)

---

## Verification Steps

### 1. API testen

```bash
# Teste die Vercel API direkt
curl -X POST https://dein-vercel-projekt.vercel.app/api/claude \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Test"}]
  }'
```

### 2. AutoShop Suite testen

1. Öffne deine deployed AutoShop Suite
2. Gehe zu "Settings" Tab
3. Klicke "API Verbindung testen"
4. Sollte ✅ anzeigen

### 3. CORS prüfen

Die API Route hat bereits CORS-Header:
- `Access-Control-Allow-Origin: *`
- `Access-Control-Allow-Methods: POST, OPTIONS`
- `Access-Control-Allow-Headers: Content-Type`

---

## Troubleshooting

### Fehler: "ANTHROPIC_API_KEY not found"
- Prüfe Vercel Environment Variables
- Stelle sicher, dass die Variable in allen Umgebungen gesetzt ist

### Fehler: "CORS error"
- Die API Route hat bereits CORS-Header
- Prüfe ob die Frontend-URL korrekt ist

### Fehler: "502 Bad Gateway"
- Anthropic API könnte down sein
- Prüfe deinen API Key Gültigkeit

---

## Kostensparen

### Railway Kosten (aktuell)
- ~$5-10/Monat für crashende Services

### Vercel Kosten (nach Migration)
- **Hobby Plan: $0/Monat** (für API Routes)
- Gratis Bandbreite: 100GB/Monat
- Gratis Serverless Functions: 100GB-Hours/Monat

**Ersparnis: ~$60-120/Jahr**

---

## Datei-Übersicht

```
windsurf-project/
├── api/
│   └── claude.ts          # ✅ Neu erstellt - Vercel API Route
├── AutoShopSuite_fixed.tsx  # ✅ Bereit für Vercel
└── RAILWAY_TO_VERCEL_MIGRATION.md  # Diese Datei
```

---

## Zusammenfassung

✅ **Vercel API Route erstellt**  
✅ **Code bereits Vercel-kompatibel**  
⏳ **Vercel Projekt deployen**  
⏳ **Environment Variables setzen**  
⏳ **Railway kündigen**

Die Migration ist technisch vorbereitet. Du musst nur noch auf Vercel deployen und die Environment Variables setzen.
