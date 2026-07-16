# SuperMegaBot — Current Status
**Stand: 2026-07-16**

## System Health
- Production: ✅ https://supermegabot-production.up.railway.app/health → OK
- Circuits: alle geschlossen (0 offene)
- Tasks: 356 registriert, 2 mit kleinen Fehlerraten (unkritisch)
- Uptime: frisch deployed (2026-07-16 ~04:52 UTC)

## Stripe ✅ VOLLSTÄNDIG LIVE — KEIN HANDLUNGSBEDARF
- **STRIPE_SECRET_KEY**: rotiert + neu gesetzt (sk_live_51Tg1U0...) ✅ lokal + Railway
- **STRIPE_PUBLISHABLE_KEY**: aktualisiert ✅ lokal + Railway
- **STRIPE_RESTRICTED_KEY**: gespeichert (rk_live_51Tg1U0...) ✅ lokal + Railway
- **36 PLINK_ Vars**: alle auf Railway ✅ (waren zuvor 0 — war Hauptblocker)
- **18 STRIPE_PAYMENT_LINK_* Vars**: auf Railway ✅
- **15 Webhooks**: alle `enabled` ✅
- **API-Test bestanden**: charges_enabled=True, payouts_enabled=True ✅
- **Stripe Connect v2**: deployed ✅ (Accounts, Onboarding, Event Destinations, Checkout)
- **Frontend /connect**: implementiert ✅
- Subscription Pläne:
  - Starter €49/mo: price_1TtfRvRJECiV6vSmX3T1Kjn2 ✅
  - Pro €99/mo: price_1TtfRwRJECiV6vSmbNBlDUzo ✅
  - Enterprise €299/mo: price_1TtfRyRJECiV6vSmwUgvoj0x ✅
  - Telegram Starter €29/mo: price_1TjodoRJECiV6vSmL726jLd3 ✅
  - Telegram Pro €79/mo: price_1TjodoRJECiV6vSmcWkhHtWz ✅
  - Telegram Agency €199/mo: price_1TjodpRJECiV6vSmFVtPj8yb ✅

## URL-Fix (Posts) ✅
- Alle myshopify.com URLs in Posts → ineedit.com.co ersetzt (44 Dateien)
- DS24 Affiliate Link: 669750 korrekt (war 668035)
- PUBLIC_SHOP_URL default in allen Posting-Modulen gesetzt

## TelegramGuard ✅
- Globales Rate-Limiting: min. 3s zwischen sendMessage-Calls
- Beide Transports abgedeckt: aiohttp + urllib
- Verhindert 429-Flood → Railway-Crash (war Ursache für Browser-Neustarts)

## Offene Punkte (niedrige Priorität)
- DeepSeek 402, Anthropic 400, Perplexity 401: API Credits/Keys erneuern nötig
- Gmail Accounts: Tageslimit 80/Account — kein Fehler heute
- Google API Key: benötigt gültiges `AIza...`-Format (letzter Versuch war `AQ.`-Format)
- WhatsApp Token: manuell regenerieren auf business.facebook.com/settings/system-users
- Google Merchant Center: Identity Verification ausstehend
