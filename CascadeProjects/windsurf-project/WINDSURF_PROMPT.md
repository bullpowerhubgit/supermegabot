# RUDIBOT MASTER SYSTEM — WINDSURF CASCADE PROMPT
# Kopiere alles zwischen den ═══ Linien direkt in Windsurf Cascade

═══════════════════════════════════════════════════════════════════
Du arbeitest an RudiBot — einem produktiven Multi-System-Projekt
mit 30 vollautomatischen Einkommenssystemen.

KONTEXT:
- Stack: Node.js 20+, Express, Supabase, Vercel, Telegram Bot API,
  Shopify Admin API, Anthropic Claude API, Printify, Digistore24,
  Perplexity, Resend, Rainforest API, eBay API, Google Cloud Vision,
  Stripe, Twilio WhatsApp
- Hauptdateien: systems.js (Sys 01-20), systems-21-30.js (Sys 21-30)
- Deploy: Vercel (vercel.json mit Cron Jobs)
- DB: Supabase (alle Tabellen in setup-supabase.js definiert)

SCHRITT 1 — ANALYSE (mache das ZUERST, ändere noch nichts):
1. Lies ALLE Dateien im Projekt
2. Lies die .env Datei und identifiziere welche Keys vorhanden/fehlen
3. Analysiere jeden der 30 Systeme auf:
   - Ist die API-Integration vollständig?
   - Fehlt Error Handling?
   - Fehlt Retry-Logik?
   - Gibt es Race Conditions?
   - Sind Cron Jobs korrekt konfiguriert?
4. Analysiere die Supabase-Schema auf fehlende Tabellen/Indexes
5. Prüfe vercel.json auf korrekte Routing und Cron-Konfiguration
6. Liste ALLE Probleme, Risiken und fehlende Implementierungen auf

SCHRITT 2 — PLAN (präsentiere vor Umsetzung):
Erstelle einen priorisierten Umsetzungsplan:
- Phase 1: Kritische Fixes (blockieren den Betrieb)
- Phase 2: Fehlende Integrationen (APIs nicht vollständig)
- Phase 3: Stabilität (Error Handling, Retry, Logging)
- Phase 4: Performance (Caching, Rate Limiting, Batching)
- Phase 5: Zentrales Dashboard (1 professionelles Admin-Dashboard)

SCHRITT 3 — UMSETZUNG (nach meiner Bestätigung):

A) PRODUKTIONSREGELN — keine Ausnahmen:
   - Kein Mock-Data, keine Demo-Responses, keine Fake-APIs
   - Jede Funktion muss mit echten APIs funktionieren
   - Error Handling überall: try/catch + Telegram Alert bei Fehlern
   - Retry-Logik für alle externen API-Calls (3 Versuche, exponential backoff)
   - Rate Limiting respektieren (Shopify: 2 req/s, Telegram: 30/s)
   - Alle Secrets aus process.env, niemals hardcoded
   - Structured Logging in Supabase logs-Tabelle

B) SYSTEM-FIXES die ich erwarte:
   01. Shopify Kundenservice: Conversation History in Supabase speichern
   02. Telegram SaaS: Stripe Webhook vollständig implementieren
   03. Content Farm: Keyword-Rotation damit keine Duplikate entstehen
   04. Dropship: Rate Limiting für Rainforest API (100 req/day limit)
   05. Preis-Monitor: Nur updaten wenn Produkt in Shopify existiert
   06. GMC Optimierer: Google OAuth Token Refresh implementieren
   07. Lead Gen: Email-Validierung vor dem Senden
   08. eBay Arbitrage: Finding API korrekte Endpoint-URL
   09. Review Requests: 14-Tage-Check korrekt implementieren
   10. Cart Recovery: Shopify Abandoned Checkout API korrekt nutzen
   11. Social Media: Buffer/Later API oder manueller Queue
   12. Newsletter: Batch-Size auf max 100 limitieren (Resend Limit)
   13. SEO Optimizer: Shopify Metafields API korrekt nutzen
   14. BI Report: Echte Umsatzdaten aus Shopify Orders
   15. Upsell Bot: Duplicate-Check vor Email-Versand
   16. Competitor Spy: Perplexity Rate Limit beachten
   17. Influencer: Email-Validierung + Blacklist
   18. Inventory: Alle Varianten eines Produkts prüfen
   19. FAQ Generator: Bestehende Seite updaten statt neu erstellen
   20. Control Bot: Admin-Auth über AUTHORIZED_USER_ID absichern
   21. Printify: Shop-ID aus API holen, nicht hardcoden
   22. Digistore: Fallback wenn API nicht erreichbar
   23. YouTube: OAuth Token Refresh für Upload
   24. WhatsApp: Twilio Webhook Validation
   25. TikTok: Content in Queue, nicht direkt posten
   26. Reddit: OAuth implementieren für echtes Posting
   27. Vision AI: Google Cloud API Key aus env
   28. Stripe Links: Duplicate-Check für bestehende Links
   29. Chat Widget: CORS korrekt konfigurieren
   30. Master Control: Rate Limiting für Commands

C) ZENTRALES DASHBOARD bauen:
   Eine einzige HTML-Seite (/dashboard) mit:
   - Real-time Stats (Umsatz heute, Bestellungen, aktive Abos)
   - Status aller 30 Systeme (grün/gelb/rot)
   - Letzte 20 Log-Einträge
   - Quick-Action Buttons für alle manuellen Trigger
   - Letzte Fehler mit Stack Trace
   - Revenue Chart (letzte 30 Tage)
   - Auth: Basic Auth mit DASHBOARD_PASSWORD aus .env

D) SUPABASE SCHEMA vervollständigen:
   - Alle fehlenden Tabellen anlegen
   - Indexes für Performance
   - Row Level Security korrekt konfigurieren
   - Backup-Strategy dokumentieren

E) VERCEL CONFIG finalisieren:
   - Alle Cron Jobs korrekt
   - Environment Variables dokumentieren
   - Edge Functions wo sinnvoll

SCHRITT 4 — TESTING:
Nach jeder Phase:
- Jeden API-Endpoint mit echten Daten testen
- Jeden Cron Job manuell triggern und Ergebnis prüfen
- Telegram Admin Notification testen
- Supabase Logs auf Fehler prüfen
- Vercel Deployment Logs prüfen

SCHRITT 5 — DEPLOYMENT:
1. npm install — alle Dependencies installieren
2. Supabase Schema deployen
3. Vercel deployen: vercel --prod
4. Alle Webhooks setzen:
   - Telegram Bot Webhook
   - Telegram Control Bot Webhook  
   - Stripe Webhook
   - Shopify Webhooks
   - WhatsApp/Twilio Webhook
5. Alle Cron Jobs verifizieren
6. End-to-End Test aller 30 Systeme
7. Monitoring bestätigen

DEFINITION OF DONE:
✅ Alle 30 Systeme laufen mit echten APIs
✅ Kein einziger Mock oder Placeholder
✅ Jeder Fehler wird geloggt + Telegram Alert
✅ Dashboard zeigt Real-time Daten
✅ Alle Webhooks aktiv
✅ Alle Cron Jobs laufen
✅ Deployment auf Vercel stabil
✅ Supabase Schema vollständig

WICHTIG — ARBEITSWEISE:
- Fange mit Analyse an, nicht mit Code
- Zeige Plan bevor du umsetzt
- Kleine Schritte, nach jedem Step bestätigen
- Bei Unklarheiten fragen, nicht raten
- Wenn ein API-Key fehlt: genau sagen welcher und wo zu finden
═══════════════════════════════════════════════════════════════════
