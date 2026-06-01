# Top-3 Projekte Audit: Verkaufsfähigkeits-Prüfung

**Datum:** 2026-06-01  
**Status:** Due-Diligence Phase

---

## 1. AutoShop Suite

### Technische Basis
- **Datei:** `components/quick-cash/AutoShopSuite.tsx`
- **Tech Stack:** React, TypeScript, Tailwind CSS
- **API Integration:** GCP Cloud Function (Vertex AI Proxy) via `callClaude()`
- **Modell:** Gemini 1.5 Pro (über Proxy)

### Funktionsumfang
- **Tabs:** Dashboard, POD, Drop, Designs, Workflows, Pricing, Settings, Upload
- **Features:** Niche-Research, Design-Generierung, Listing-Erstellung, Tag-Optimierung
- **API-Proxy:** `https://europe-west1-gen-lang-client-0895465231.cloudfunctions.net/vertexAIProxy`

### API-Status
| API | Status | Konfiguration | Test |
|-----|--------|---------------|------|
| GCP Vertex AI Proxy | ⚠️ Proxy-Abhängigkeit | Hardcoded URL | Nicht getestet |
| Anthropic (Fallback) | ❌ Nicht aktiv | `ANTHROPIC_API_KEY` fehlt | N/A |

### Kritische Blocker
1. **Proxy-Abhängigkeit:** Cloud Function muss laufen und erreichbar sein
2. **Keine Fehlerbehandlung:** `callClaude()` wirft Error ohne Retry-Logik
3. **Keine Auth:** Proxy ist öffentlich erreichbar (kein API-Key Check)
4. **Kein Backend:** Frontend-only, keine Persistenz

### Verkaufsfähigkeit: **30%**
- ✅ UI vollständig implementiert
- ✅ Features klar definiert
- ❌ API-Integration fragil (Proxy-SPOF)
- ❌ Keine Datenbank/Backend
- ❌ Kein Deployment-Setup

### Erforderliche Maßnahmen
1. Backend mit Auth & Rate-Limiting erstellen
2. Retry-Logik für API-Calls implementieren
3. Persistenz (SQLite/Supabase) für generierte Assets
4. Deployment-Script (Vercel/Vite) erstellen
5. Fallback zu Anthropic bei Proxy-Ausfall

---

## 2. QuickCash System

### Technische Basis
- **Datei:** `components/quick-cash/QuickCashSystem.tsx`
- **Tech Stack:** React, Lucide Icons, Tailwind CSS
- **API Integration:** Anthropic Claude (via Backend Proxy)
- **Modell:** claude-sonnet-4-20250514

### Funktionsumfang
- **Tabs:** Dashboard, System Generieren, Tools, Settings
- **Features:** API-Usage Tracking, Cost-Dashboard, Asset-Download
- **Pricing:** $3.00/M Input, $15.00/M Output, $0.50/Tag Limit

### API-Status
| API | Status | Konfiguration | Test |
|-----|--------|---------------|------|
| Anthropic Claude | ⚠️ Backend-Proxy benötigt | `ANTHROPIC_API_KEY` in .env | Nicht getestet |
| Backend API | ❌ Nicht implementiert | `quickcash-backend.js` existiert | N/A |

### Kritische Blocker
1. **Kein laufender Backend:** `quickcash-backend.js` ist Standalone, nicht integriert
2. **Keine Auth:** API-Endpunkte offen
3. **Keine Persistenz:** Session-Stats verloren bei Refresh
4. **Kein Deployment:** Frontend & Backend nicht zusammen deployed

### Verkaufsfähigkeit: **25%**
- ✅ UI vollständig mit Cost-Tracking
- ✅ Pricing-Logik implementiert
- ❌ Backend nicht in Betrieb
- ❌ Keine Auth/User-Management
- ❌ Kein Deployment

### Erforderliche Maßnahmen
1. Backend in `my-shop/backend` integrieren oder standalone deployen
2. Auth (JWT/Session) implementieren
3. Supabase für User-Stats & History
4. Deployment auf Vercel (Frontend) + Railway/Render (Backend)
5. Webhook für Stripe-Payment Integration

---

## 3. My-Shop

### Technische Basis
- **Backend:** `my-shop/backend/index.js` (Express, Node.js)
- **Frontend:** `my-shop/frontend/` (React, Vite)
- **Tech Stack:** Express, React, TypeScript, Tailwind CSS
- **Datenbank:** MongoDB, Supabase (PostgreSQL)

### Funktionsumfang
- **Backend Routes:** Produkte, Bestellungen, Marketing, Analytics, System, Claude
- **Frontend Pages:** Dashboard, Produkte, Bestellungen, Marketing, SEO
- **Integrationen:** Shopify, GitHub, Telegram, Anthropic, Perplexity

### API-Status
| API | Status | Konfiguration | Test |
|-----|--------|---------------|------|
| Shopify Store 1 | ✅ Konfiguriert | `SHOPIFY_ACCESS_TOKEN` | Nicht getestet |
| Shopify Store 2 | ⚠️ Token fehlt | `shpat_REPLACE_WITH_NEW_TOKEN` | N/A |
| GitHub | ✅ Konfiguriert | `GITHUB_TOKEN` | Nicht getestet |
| Anthropic | ✅ Konfiguriert | `ANTHROPIC_API_KEY` | Nicht getestet |
| Perplexity | ✅ Konfiguriert | `PERPLEXITY_API_KEY` | Nicht getestet |
| MongoDB | ⚠️ URI vorhanden | `mongodb://mongo:27017/...` | Nicht getestet |
| Supabase | ⚠️ Service-Key fehlt | `YOUR_SUPABASE_KEY_HERE` | N/A |

### Kritische Blocker
1. **Controller fehlen:** Routes importieren Controller, aber Implementierung unklar
2. **Keine Datenbank-Verbindung:** MongoDB/Supabase nicht verbunden
3. **Frontend nicht gebaut:** `npm run build` nicht ausgeführt
4. **Deployment nicht definiert:** Kein Dockerfile, keine Vercel/Railway Config

### Verkaufsfähigkeit: **40%**
- ✅ Backend-Struktur vollständig
- ✅ Frontend-Struktur vollständig
- ✅ API-Keys in .env vorhanden
- ❌ Controller-Implementierung unklar
- ❌ Keine Datenbank-Verbindung
- ❌ Kein Deployment

### Erforderliche Maßnahmen
1. Controller-Implementierung prüfen/vervollständigen
2. MongoDB/Supabase Connection implementieren
3. Frontend build & deploy (Vercel)
4. Backend deploy (Railway/Render)
5. Shopify-Webhook-Handler implementieren
6. Stripe-Payment Integration für Checkout

---

## Zusammenfassung: Verkaufsfähigkeit

| Projekt | Verkaufsfähigkeit | Kritische Blocker | Aufwand (Tage) |
|---------|------------------|-------------------|----------------|
| AutoShop Suite | 30% | Proxy-SPOF, kein Backend | 5-7 |
| QuickCash System | 25% | Backend nicht in Betrieb, kein Auth | 7-10 |
| My-Shop | 40% | Controller unklar, keine DB-Verbindung | 10-14 |

## Priorisierte Maßnahmen

### Phase 1 (Kritisch - 3-5 Tage)
1. **My-Shop Controller prüfen** - Implementierung verifizieren
2. **QuickCash Backend starten** - `quickcash-backend.js` in Betrieb nehmen
3. **AutoShop Proxy testen** - Cloud Function Verfügbarkeit prüfen

### Phase 2 (Stabilisierung - 5-7 Tage)
1. **Datenbank-Verbindung** - MongoDB/Supabase für My-Shop
2. **Auth implementieren** - JWT für QuickCash & My-Shop
3. **Retry-Logik** - API-Calls resilient machen

### Phase 3 (Deployment - 3-5 Tage)
1. **Frontend Deploy** - Vercel für alle 3 Projekte
2. **Backend Deploy** - Railway/Render für APIs
3. **Monitoring** - Bot-System für Health-Checks

## Risikomatrix

| Risiko | Eintrittswahrscheinlichkeit | Auswirkung | Priorität |
|--------|---------------------------|------------|-----------|
| Proxy-Ausfall (AutoShop) | Hoch | Kritisch | P0 |
| Backend nicht startet (QuickCash) | Mittel | Kritisch | P0 |
| Datenbank-Verbindung fehlt (My-Shop) | Hoch | Hoch | P0 |
| API-Keys ablaufen | Mittel | Mittel | P1 |
| Deployment fehlschlägt | Mittel | Mittel | P1 |
| XSS in Dashboards | Niedrig | Mittel | P2 |

---

**Nächster Schritt:** Controller-Implementierung von My-Shop prüfen und QuickCash Backend starten.
