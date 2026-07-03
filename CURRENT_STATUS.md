# SuperMegaBot — Aktueller Status
> Zuletzt aktualisiert: 2026-07-03 | Session v9

## System-Status
| Service | URL | Status |
|---------|-----|--------|
| SuperMegaBot Railway | dudirudibot-mega-production.up.railway.app | 🔴 OFFLINE — Abo unbezahlt |
| Supabase Autopost | pg_cron 8x täglich | ✅ LIVE (FB ✅ TG ✅ getestet 2026-07-03) |
| Shopify Store | ineedit.com.co | ✅ 2449 Produkte, alle €29.99 |
| Stripe | Live-Modus | ✅ Key rotiert 2026-07-02 |
| GitHub Actions | bullpowerhubgit/supermegabot | 🔴 GESPERRT — Billing Lock |

## HEUTE ERLEDIGT (2026-07-03)
- ✅ **Shopify Bulk Update** — 2449 Produkte, 2573 Varianten auf €29.99, 359 Inventar auf 10
- ✅ **Shopify Passwortschutz** — bereits deaktiviert (enabled: false)
- ✅ **Autopost Edge Function** — getestet: FB ✅ TG ✅ (läuft 8x täglich)
- ✅ **Shopify OAuth Callback** — Route `/api/shopify/oauth/callback` in server.py (Commit 2449971)
- ✅ **pg_cron** — aktiv: `0 6,9,12,15,18,21,0,3 * * *`

## KRITISCHE BLOCKER (nur mit Zahlung lösbar)
| # | Problem | Wo bezahlen |
|---|---------|-------------|
| 🔴 | Railway Abo unbezahlt → Server down | railway.app → Billing |
| 🔴 | GitHub Actions locked → kein Auto-Deploy | github.com/settings/billing |
| 🟡 | SendGrid Trial abgelaufen 04.01.2026 | sendgrid.com → Abrechnung (Free reicht) |

## SHOPIFY TOKEN (blockiert Python-Scripts)
**Status:** Alle 12 Tokens ungültig — App neu installiert, alter Token weg
**Fix:** Shopify Admin → Apps → Apps entwickeln → deine App → API-Anmeldedaten → **"API-Zugriffstoken rotieren"** → sofort kopieren → mir geben
**Workaround bis dahin:** Shopify MCP (claude.ai) direkt nutzbar — keine Scripts nötig

## SOCIAL MEDIA STATUS
| Kanal | Account | Status |
|-------|---------|--------|
| Facebook | AiiteC Page 1016738738178786 | ✅ LIVE — täglich |
| Telegram | Bot aktiv | ✅ LIVE — täglich |
| Instagram | @aaiitecc 4.868 Follower | ⚠️ Braucht Meta App Review |
| YouTube @rudolfsarkani1592 | 9 Subs | ✅ OAuth verbunden |
| YouTube @AIITECrs | 4.160 Subs | ❌ Anderes Google-Konto nötig |
| Reddit /u/bullpowersrtkennels | - | ❌ OAuth ausstehend |
| Pinterest | rudolfsarkany1984@gmail.com | ❌ App-ID fehlt |
| TikTok | - | ❌ Keine Credentials |

## WAS RUDOLF EINMALIG MACHEN MUSS
### 1. Railway bezahlen 🔴 (2 Min)
→ railway.app → Billing → Pay outstanding balance

### 2. GitHub Actions Billing 🔴 (2 Min)
→ github.com/settings/billing → Actions-Minuten

### 3. Shopify Token rotieren 🟡 (1 Klick)
→ Shopify Admin → Apps → Apps entwickeln → App → API-Anmeldedaten → Token rotieren → kopieren

### 4. Reddit Script-App setzen 🟢 (5 Min)
→ reddit.com/prefs/apps → App "hqgJAQe6Qiu5s5r1Vqc0Og" → Edit → Typ: "script"
→ Dann: python3 scripts/oauth_connect.py reddit

### 5. SendGrid Free Plan aktivieren 🟢 (2 Min)
→ app.sendgrid.com/account/billing → Rechnungsadresse + Zahlungsmethode → Free: 100/Tag

## REVENUE
| Quelle | Betrag |
|--------|--------|
| Digistore24 | €111 gesamt |
| Stripe | Live-Modus aktiv |

## NÄCHSTE SCHRITTE (sobald Railway bezahlt)
1. Shopify Preisvariation (nicht alle einheitlich €29.99)
2. Pinterest App erstellen + OAuth
3. Instagram Meta App Review
4. YouTube @AIITECrs — welches Google-Konto?
