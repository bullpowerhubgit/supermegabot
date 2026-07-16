# Pinterest API Resubmit — READY (BullPower Hub)

**Status (2026-07-16 mail):** Trial Access REJECTED for App 1582363
**Grund Nana (Pinterest):** Company "AIITEC" + App "Rudibot" passen nicht zu
`https://bullpower-hub-portal.netlify.app/` + Datenschutzerklärung.

## ✅ Was wir gefixt haben (ohne dich)
- Privacy/Datenschutz: **nur BullPower Hub** (kein AIITEC/Rudibot)
- Live: https://bullpower-hub-portal.netlify.app/datenschutz
- Live: https://bullpower-hub-portal.netlify.app/privacy.html
- Live: https://bullpower-hub-portal.netlify.app/data-deletion.html
- Netlify + Vercel deployed

## ⚠️ Was NUR im Pinterest Developer Portal geht (Browser)
1. https://developers.pinterest.com → App **1582363**
2. Company name: **BullPower Hub**
3. App name: **BullPower Pins**
4. Website: **https://bullpower-hub-portal.netlify.app/**
5. Privacy: **https://bullpower-hub-portal.netlify.app/datenschutz**
6. Re-submit Trial Access
7. Nach Approve: neuen Access Token erzeugen → `PINTEREST_ACCESS_TOKEN` setzen

## Ticket
- 16593704 / 16593708
- Antwort: **nicht akzeptiert**, Resubmit mit korrekten Namen nötig
- Auto-Reply per Gmail heute **blockiert** (Daily sending limit 550)

## Token jetzt
- `pina_…` → API **401 Authentication failed**
- Kein App-Secret / Refresh-Token in .env → kein Auto-Refresh möglich
