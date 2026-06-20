# SuperMegaBot CURRENT STATUS — 2026-06-20

## System Health
- Railway: ✅ ONLINE (dudirudibot-mega-production.up.railway.app)
- Health: /health → {"status":"ok"}
- Circuits: ALL CLOSED (auto-reset nach 30 min)
- Scheduler: 191 Tasks registriert

## BRUTUS Traffic Engine
- **Status: AKTIV** — 9 Kanäle pro Run (Telegram, Shopify Blog, Klaviyo Events, LinkedIn, Pinterest, Reddit, YouTube, Discord, Video Script)
- Fallback-Templates: 5x AIITEC/DS24 Templates wenn AI nicht verfügbar
- DS24 Affiliate Link: https://www.digistore24.com/redir/669750/user37405262/ ✅

## AI Providers (alle aktuell offline — BRUTUS nutzt Templates)
- Anthropic: ❌ Guthaben leer → anthropic.com → Top-up
- OpenAI: ❌ Rate limit / Quota
- Groq: ⏳ Key fehlt → console.groq.com → kostenlos → `railway variables set GROQ_API_KEY=...`
- OpenRouter: ❌ Ungültiger Key-Format (braucht sk-or-v1-...) → openrouter.ai
- Gemini: ❌ YouTube-Key kann nicht Gemini — braucht GEMINI_API_KEY von aistudio.google.com
- DeepSeek: ❌ Guthaben leer

## Revenue (aktuell: €0.00)
- Shopify: 630+ Produkte, 1 all-time Order
- DS24 AIITEC: ✅ API verbunden (user37405262), 0 Produkte im Konto noch
- Stripe: ✅ API verbunden, €0
- GMC: 624 Produkte BLOCKED — identity_verification_pending
  → **WICHTIG: merchants.google.com verifizieren!**

## Email Marketing
- Klaviyo: ✅ Subscriber-Sync + Flow-Events aktiv
- Mailchimp: ❌ Account DISABLED (DragonApp-Konto gesperrt → reaktivieren)
- SMTP: Konfiguriert

## Social Media
- LinkedIn: ✅ API Token gesetzt (auto-posting aktiv)
- Twitter/X: ✅ ALLE 4 Keys vorhanden — aber 402 CreditsDepleted (Basic Plan $100/mo nötig)
- Discord: ✅ BOT_TOKEN vorhanden — aber Bot in keinem Server (einladen!)
- Pinterest: ✅ OAuth-Flow bereit
- Reddit: ❌ Credentials fehlen (CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD)
- TikTok: ❌ Credentials fehlen
- WhatsApp: ❌ Credentials fehlen

## Print-on-Demand
- Printify: ✅ AKTIV — Shop 27975583 "you need", 1 Produkt live, Autonomy läuft (2 Produkte erstellt)
- Printful: ⚠️ API Key (AIITEC) — aber kein Store verbunden
  → Manuell: printful.com → Stores → Add Shopify → autopilot-store-suite-fmbka.myshopify.com

## Marktplätze (alle autonomy module laufen)
- Amazon: ✅ Autonomy aktiv (3 Blasts, 5 Produkte), Associates Tag: bullpowerhub-21
- eBay: ✅ Autonomy aktiv (3 Blasts, 5 Produkte), Client ID gesetzt
- AliExpress: ✅ Autonomy aktiv (3 Produkte importiert), App Key 536860
- Gumroad: ❌ GUMROAD_ACCESS_TOKEN fehlt → gumroad.com → Settings → Advanced → API

## Offene Tasks (Manuell durch Rudolf)
1. **DRINGEND**: GMC Identity → merchants.google.com → verifizieren → 624 Produkte live
2. **WICHTIG**: Groq Key → console.groq.com → Free → `railway variables set GROQ_API_KEY=gsk_...`
3. Printful: Store verbinden (printful.com → Stores → Shopify)
4. Mailchimp: DragonApp-Konto reaktivieren
5. Discord: Bot einladen → discord.com/oauth2/authorize?client_id=1515460691664965672&permissions=2048&scope=bot
6. Reddit: App erstellen auf reddit.com/prefs/apps → CLIENT_ID + CLIENT_SECRET
7. Gumroad: API Token → gumroad.com → Settings → Advanced
8. TikTok: TikTok for Business → App erstellen
9. WhatsApp: Meta Business Portal → WhatsApp setup

## DS24 AIITEC Account
- API Key: 1682000-T8KjTRJ... (korrekt gesetzt)
- User ID: user37405262
- Affiliate URL: https://www.digistore24.com/redir/669750/user37405262/
