# SuperMegaBot CURRENT STATUS — 2026-06-20

## System Health
- Railway: ✅ ONLINE (dudirudibot-mega-production.up.railway.app)
- Health: /health → {"status":"ok"}
- Circuits: ALL CLOSED (auto-reset nach 30 min)
- Scheduler: 215 Task-Funktionen, 0 Import-Fehler
- Code Quality: Dashboard 276 OK, Scheduler 175 OK, Core 191 OK — alle 0 Fehler

## BRUTUS Traffic Engine
- **Status: AKTIV** — 6-9 Kanäle (Telegram ✅, Klaviyo ✅, LinkedIn ✅, Pinterest ✅, YouTube, Discord, Reddit, Shopify Blog*)
- *Shopify Blog: scheitert an fehlendem `write_content` Scope (see below)
- DS24 Affiliate: https://www.digistore24.com/redir/669750/user37405262/ ✅ in allen Templates

## WICHTIG: Shopify Token Scopes fehlen für Blog
  Aktuell: read_products, write_products, read_orders, write_orders, read_customers, write_customers
  FEHLT:   **read_content, write_content** (für Blog-Posts nötig)
  → Fix: Shopify Admin → Einstellungen → Apps → SuperMegaBot → Konfiguration → Scopes hinzufügen → Neu installieren

## AI Providers (BRUTUS läuft mit Template-Fallback)
- Anthropic: ❌ Kein Guthaben → anthropic.com/dashboard → Top-up
- **Groq (NEU)**: ⏳ Key fehlt → console.groq.com → Free → `railway variables set GROQ_API_KEY=gsk_...`
- OpenRouter: ❌ Ungültiger Key (braucht sk-or-v1-... Format)
- Gemini: ❌ Braucht eigenen GEMINI_API_KEY (nicht YouTube-Key)
- OpenAI/DeepSeek/Perplexity: ❌ Quota/Credits leer

## Revenue (aktuell: €0.00)
- Shopify: 630+ Produkte, Shop "I Want That! I Need It!" (Basic Plan)
- DS24 AIITEC: ✅ API verbunden (user37405262), 0 Produkte/Transaktionen
  → **IPN URL einrichten**: digistore24.com → Einstellungen → Webhooks → URL: https://dudirudibot-mega-production.up.railway.app/api/digistore24/ipn
- Stripe: ✅ API verbunden, €0
- GMC: 624 Produkte BLOCKED → **WICHTIG: merchants.google.com Identity verifizieren!**

## Email Marketing
- Klaviyo: ✅ 4 Listen, Subscriber-Sync + Flow-Events aktiv
- Mailchimp: ❌ DragonApp-Konto DISABLED → reaktivieren
- Twilio: ✅ Konfiguriert (SID + Auth Token + From-Number), Verified TO: +4917622890860

## Social Media
- LinkedIn: ✅ **AKTIV** — Token gültig (Rudolf Sarkany), Auto-Posting
- Twitter/X: ✅ Alle 4 Keys vorhanden — 402 CreditsDepleted (Basic Plan $100/mo nötig)
- Discord: ✅ BOT_TOKEN gesetzt — Bot muss in Server:
  **→ https://discord.com/oauth2/authorize?client_id=1515460691664965672&permissions=2048&scope=bot**
  Dann DISCORD_CHANNEL_ID in Railway setzen
- Pinterest: ✅ OAuth-Flow bereit
- Reddit: ❌ Credentials fehlen
- TikTok: ❌ Credentials fehlen
- WhatsApp: ❌ Credentials fehlen

## Print-on-Demand
- Printify: ✅ **AKTIV** — Shop 27975583, 3 Produkte, Autonomy läuft
- Printful: ⚠️ API Key (AIITEC) — kein Store verbunden
  → printful.com → Stores → Add Shopify → autopilot-store-suite-fmbka.myshopify.com

## Marktplätze (alle Autonomy-Module laufen vollautomatisch)
- Amazon: ✅ Autonomy (3 Blasts), Associates Tag: bullpowerhub-21
- eBay: ✅ Autonomy (3 Blasts), Client ID: IRV7wFsqtKC76...
- AliExpress: ✅ Autonomy (3 Produkte), App Key: 536860
- Gumroad: ❌ GUMROAD_ACCESS_TOKEN fehlt → gumroad.com → Settings → Advanced

## Offene Tasks (Manuell durch Rudolf — WICHTIG)
| Prio | Task | Aktion |
|------|------|--------|
| 🔴 | GMC Identity | merchants.google.com → verifizieren → 624 Produkte live |
| 🔴 | Groq AI Key | console.groq.com → Free → `railway variables set GROQ_API_KEY=gsk_...` |
| 🟠 | DS24 IPN URL | digistore24.com → Einstellungen → IPN → URL oben eintragen |
| 🟠 | Shopify Blog | Admin → Apps → SuperMegaBot → read_content + write_content Scope |
| 🟡 | Discord | Bot-Link oben klicken → dann DISCORD_CHANNEL_ID setzen |
| 🟡 | Printful | printful.com → Stores → Shopify verbinden |
| 🟡 | Mailchimp | DragonApp-Konto reaktivieren |
| 🟡 | Gumroad | gumroad.com → Settings → Advanced → API Token |
| ⚪ | Reddit | reddit.com/prefs/apps → App erstellen |
| ⚪ | TikTok | TikTok for Business → App erstellen |
| ⚪ | WhatsApp | Meta Business Portal → WhatsApp |

## DS24 AIITEC Account
- API Key: 1682000-T8KjTRJ... (X-DS-API-KEY Header, /JSON/ URL-Suffix) ✅
- User ID: user37405262
- Affiliate URL: https://www.digistore24.com/redir/669750/user37405262/

## Session v13 Fixes (2026-06-20)
- DS24 API auth fix (X-DS-API-KEY header)
- Printify neuer API Key + Shop 27975583 aktiv
- BrutusCore class hinzugefügt
- LinkedIn Status-Fix (/v2/userinfo statt ugcPosts)
- 11 fehlende Funktionen in Modulen hinzugefügt
- Groq als neuer AI-Provider integriert
- Gumroad/Etsy Tuple-Bug fix
- 3 neue Status-Routen (aliexpress, tiktok, whatsapp)
- 100+ Railway Environment-Variables synchronisiert
