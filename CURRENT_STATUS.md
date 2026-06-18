# SuperMegaBot — Aktueller Status (Auto-Update)
> Zuletzt aktualisiert: 2026-06-19 | Wenn Claude neu startet → Diese Datei zuerst lesen!

## System-Status
- **Railway**: `dudirudibot-mega-production.up.railway.app` — LIVE ✅
- **Master Dashboard**: `/master` — läuft ✅
- **EmailBrain**: 6 Konten aktiv, Emails werden verarbeitet ✅
- **BRUTUS v2**: 6-Kanal-Deployment aktiv (Telegram, Shopify, Klaviyo, Facebook, Instagram, YouTube) ✅
- **CRO Engine**: aktiv (stündlich) ✅
- **Auto Funnel**: aktiv (alle 30 Min) ✅
- **DS24 Funnel Sync**: aktiv (alle 15 Min) ✅

## Letzter Commit
`f9fbe5c` — Master Control Dashboard at /master

## EmailBrain — Status (8 Konten)
| # | Account | App PW | IMAP Host | Status |
|---|---------|--------|-----------|--------|
| 1 | dragonadnp@gmail.com | ✅ gesetzt | gmail | AKTIV |
| 2 | nikolestimi@gmail.com | ✅ gesetzt | gmail | AKTIV |
| 3 | bullpowersrtkennels@gmail.com | ✅ gesetzt | gmail | AKTIV |
| 4 | looopwave@gmail.com | ❌ FEHLT | gmail | WARTET AUF APP-PW |
| 5 | aiitecbuuss@gmail.com | ✅ gesetzt | gmail | AKTIV |
| 6 | rudolf.sarkany@aitec.de | ❌ FEHLT | ssl0.ovh.net | WARTET AUF PW |
| 7 | rudolf.sarkany.aiitec@gmail.com | ✅ gesetzt | gmail | AKTIV |
| 8 | rudolfsarkany1984@gmail.com | ✅ gesetzt | gmail | AKTIV |

**Fehlende App Passwords:**
- `GMAIL_APP_PASSWORD_4` für looopwave@gmail.com
- `GMAIL_APP_PASSWORD_6` für rudolf.sarkany@aitec.de (OVH Mailpasswort)

## Offene Punkte
| Prio | Task | Details |
|------|------|---------|
| 🔴 HOCH | looopwave App PW | User muss in Gmail → 2FA → App-Passwörter generieren |
| 🔴 HOCH | aitec.de Email PW | OVH Mail-Passwort für rudolf.sarkany@aitec.de in Railway |
| 🟡 MITTEL | Pinterest Resubmit | Details in PINTEREST_RESUBMIT.md, App 1582389 abgelehnt |
| 🟡 MITTEL | gh auth refresh -s workflow | Für workflow-Files pushen. User: `! gh auth refresh -s workflow` |
| 🟡 MITTEL | Twilio FROM Number | In console.twilio.com kaufen → TWILIO_FROM_NUMBER in Railway |
| 🟢 NIEDRIG | DS24 IPN URL | In DS24 → Produkt 669750 → IPN: https://dudirudibot-mega-production.up.railway.app/api/digistore24/ipn |
| 🟢 NIEDRIG | YouTube OAuth | Braucht OAuth, derzeit graceful fail |
| 🟢 NIEDRIG | Shopify Meta Connect | Business Manager 26699880109605857 restricted, muss manuell in Shopify UI |

## Live-Infrastruktur
- SuperMegaBot: https://dudirudibot-mega-production.up.railway.app
- Brutal Traffic Engine: Auf Railway (separates Service)
- Meta Social Engine: Auf Railway
- Netlify Sites: 6x (einige Credits exhausted)
- GitHub Pages: https://bullpowerhubgit.github.io/bullpower-legal/ (Datenschutz + BRUTUS Pixel)

## Neue Module (alle committed & deployed)
- `modules/brutus_traffic_engine.py` — 7-Phasen Traffic Engine
- `modules/cro_engine.py` — Conversion Rate Optimization
- `modules/auto_funnel.py` — Lead-Nurturing-Funnel
- `modules/ds24_funnel_automation.py` — DS24 → Mailing Auto-Sync
- `modules/traffic_seo_engine.py` — AI SEO Content Generator
- `modules/email_brain.py` — Autonomes Gmail Management (8 Konten)
- `modules/twilio_sms.py` — SMS via Twilio
- `dashboard/master.html` — Master Control Dashboard

## BRUTUS Instagram Fix
- Pixel PNG war 1x1px → ersetzt durch 1080x1080 BRUTUS-Bild
- Live: https://bullpowerhubgit.github.io/bullpower-legal/brutus_pixel.png ✅

## API-Keys (in Railway gesetzt)
- Digistore24: Key 1581233 (Vollzugriff) ✅
- Klaviyo: pk_VaCYq3_... ✅
- Mailchimp: us7 ✅
- SendGrid: SG.nbniKd3-... ✅
- Twilio: AC2b92fc... ✅
- Facebook: App 1225412136200609 (Token läuft ab — periodisch erneuern) ⚠️

## Wie Claude beim nächsten Start weitermacht
1. Diese Datei lesen (`cat CURRENT_STATUS.md`)
2. `railway variables | grep GMAIL` für Email-Status
3. `curl .../health` für System-Status
4. Offene Punkte oben abarbeiten
