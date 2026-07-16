# Pinterest API Resubmit — AIITEC / rodibot (App 1582363)

**Status:** Trial Access REJECTED (Nana, tickets 16593704 / 16593708)  
**Grund:** Company **AIITEC** + App **Rudibot/rodibot** passten nicht zur Website
`https://bullpower-hub-portal.netlify.app/` (BullPower-Branding).

## ✅ Fix (2026-07-16) — AIITEC-only Portal LIVE

| Item | URL / Value |
|------|-------------|
| **Company** | AIITEC |
| **App name** | rodibot |
| **App ID** | 1582363 |
| **Website** | https://aiitec-pinterest-portal.netlify.app/ |
| **Privacy** | https://aiitec-pinterest-portal.netlify.app/privacy.html |
| **Datenschutz** | https://aiitec-pinterest-portal.netlify.app/datenschutz |
| **Data deletion** | https://aiitec-pinterest-portal.netlify.app/data-deletion.html |
| **Kontakt** | aiitecbuuss@gmail.com |
| **Vercel mirror** | https://aiitec-pinterest-portal.vercel.app/ (same pages) |

Kein BullPower / Rudibot-Mismatch mehr auf den Compliance-Seiten.

## ⚠️ Was NUR im Pinterest Developer Portal geht (Browser — Rudolf)

1. https://developers.pinterest.com → App **1582363**
2. Company name: **AIITEC** (lassen / exakt so)
3. App name: **rodibot** (nicht “Rudibot”, nicht BullPower Pins)
4. Website: **https://aiitec-pinterest-portal.netlify.app/**
5. Privacy policy: **https://aiitec-pinterest-portal.netlify.app/privacy.html**
6. Data deletion: **https://aiitec-pinterest-portal.netlify.app/data-deletion.html**
7. **Re-submit Trial Access**
8. Nach Approve: neuen Access Token + Refresh Token + App Secret erzeugen:
   - `PINTEREST_ACCESS_TOKEN`
   - `PINTEREST_REFRESH_TOKEN`
   - `PINTEREST_APP_SECRET`

## Token-Status jetzt

| Check | Result |
|-------|--------|
| `pina_…` in `.env` | **401 Authentication failed** |
| Refresh | unmöglich ohne `PINTEREST_APP_SECRET` + `PINTEREST_REFRESH_TOKEN` |
| Railway | wartet auf neuen Token nach Trial-Approve |

## Env (lokal gesetzt)

```
PINTEREST_COMPANY_NAME=AIITEC
PINTEREST_APP_NAME=rodibot
PINTEREST_APP_ID=1582363
PINTEREST_WEBSITE_URL=https://aiitec-pinterest-portal.netlify.app/
PINTEREST_PRIVACY_URL=https://aiitec-pinterest-portal.netlify.app/privacy.html
PINTEREST_DATA_DELETION_URL=https://aiitec-pinterest-portal.netlify.app/data-deletion.html
```

## Alternativ-Pfad (nicht empfohlen, falls Nana auf BullPower beharrt)

Company+App auf BullPower Hub / BullPower Pins umbenennen und
`https://bullpower-hub-portal.netlify.app/` nutzen — dann müsste Portal-App umbenannt werden.
**Aktueller Default: AIITEC-Pfad** (passt zu Company im Ticket).
