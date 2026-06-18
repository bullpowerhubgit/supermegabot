# Pinterest API — Neueinreichung (nach Ablehnung App 1582389)
# Stand: 2026-06-18

## Problem (Ablehnungsgründe von Nana/Pinterest Support):
1. Beschreibung "Automatisierung eigenes Tool" — zu vage
2. Datenschutz-URL führt zu 404 (Netlify-Credits aufgebraucht)
3. Firmenname "AIITEC" und App-Name "Rudibottttttt" passen nicht zu bullpower-hub-portal.netlify.app

## Lösung (alle 3 gefixt):
1. Professionelle App-Beschreibung geschrieben
2. Neue Datenschutz-URL: https://bullpowerhubgit.github.io/bullpower-legal/datenschutz.html (LIVE ✅)
3. Konsistenter Name: BullPower Hub / BullPower Social Automation

---

## ANLEITUNG: Pinterest Neu einreichen

### Schritt 1: Auf Pinterest antworten
Antwort an Nana (Pinterest Support) senden:

---
Betreff: Re: Ihre App-Anfrage 1582389

Hallo Nana,

vielen Dank für die detaillierte Rückmeldung. Ich habe alle drei Punkte behoben:

1. **Beschreibung verbessert** — klare Erklärung der App-Funktion (siehe neue Einreichung)
2. **Datenschutzrichtlinien-URL repariert** — neue URL ist live: https://bullpowerhubgit.github.io/bullpower-legal/datenschutz.html
3. **Namen konsistent** — Firmenname und App-Name stimmen jetzt überein

Ich reiche die App neu unter App ID [neue ID nach Erstellung] ein.

Mit freundlichen Grüßen,
Rudolf Sarkany
BullPower Hub
bullpowersrtkennels@gmail.com
---

### Schritt 2: Neue Pinterest App erstellen
URL: https://developers.pinterest.com/apps/

Felder:
- **App Name:** BullPower Social Automation
- **Description (EN):** Automation software for Shopify merchants that automatically publishes product images and SEO content as Pinterest Pins. The app posts exclusively on behalf of the authenticated user via OAuth 2.0. Use case: e-commerce product promotion and content marketing automation.
- **Description (DE):** Automatisierungssoftware für Shopify-Händler, die Produktbilder und SEO-Inhalte automatisch als Pinterest-Pins veröffentlicht. Die App postet ausschließlich im Namen des authentifizierten Nutzers über OAuth 2.0.
- **Company Name:** BullPower Hub
- **Website URL:** https://bullpower-hub-portal.netlify.app
- **Privacy Policy URL:** https://bullpowerhubgit.github.io/bullpower-legal/datenschutz.html
- **Redirect URI:** https://dudirudibot-mega-production.up.railway.app/api/pinterest/callback

### Schritt 3: Env-Var setzen sobald App genehmigt
railway variables set PINTEREST_API_KEY=<neue App ID>
railway variables set PINTEREST_API_SECRET=<App Secret>
railway variables set PINTEREST_BOARD_ID=<Board ID>

---

## Status
- [x] Datenschutz-URL erstellt und live
- [ ] Antwort an Nana senden
- [ ] Neue App einreichen (developers.pinterest.com)
- [ ] App-Genehmigung abwarten (1-3 Werktage)
- [ ] Pinterest Deploy in BRUTUS aktivieren
