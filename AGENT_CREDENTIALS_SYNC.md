# Agent Credentials Sync — Stand 2026-06-18

## Neue / aktualisierte Credentials

### Twilio SMS
- TWILIO_ACCOUNT_SID=AC2b92fc8e5af02a27604a964cb241b021
- TWILIO_AUTH_TOKEN=54511038fba02a2dbac1a0ef28b704a5
- TWILIO_API_KEY_SID=SKe45ad37f109f52168e9b4bb6cd9da477
- TWILIO_API_KEY_SECRET=RikVTimlOqQmWeOd0yQYFSlOjsbGRJ0Q
- Modul: modules/twilio_sms.py → send_sms(to, body)

### Klaviyo
- KLAVIYO_API_KEY=pk_VaCYq3_242945f7521ac82039ed5dbf7ff8e6cf1c  ← NEU (alte Keys ungültig)
- KLAVIYO_LIST_ID=Xwxq6V  (E-Mail-Liste)
- Listen: TiEAtk (Vorschau), U2iTrm (SMS), Xwxq6V (Email)

### Mailchimp  
- MAILCHIMP_API_KEY=1d35dd606aad1a9f1bbd10d2dd2e2ea7-us7  ← NEU (alter us18 Key deaktiviert)
- MAILCHIMP_SERVER_PREFIX=us7
- MAILCHIMP_LIST_ID=606e45a6b0  (AiiteC — 4 Members)
- MAILCHIMP_CLIENT_ID=533625521597
- MAILCHIMP_CLIENT_SECRET=c4c6423524cdb5ce7c53a415a03a0668f18adcfd79d760d628

### Digistore24
- DIGISTORE24_API_KEY=1581233-eOOUB4qRJJybjVb9z4q5tO68wtEQmt9h9l8t3s1N  ← Vollzugriff
- DIGISTORE24_API_KEY_READONLY=1583143-rKrkcndqBDL52N5kmX36wZXeFTNbCyI8R8gkVgIJ
- 3 Transaktionen, €111 gesamt (Feb 2026)
- Buyer-Email: order["buyer"]["email"] (verschachtelt!)

## Neue Module (modules/)
- twilio_sms.py — SMS senden
- ds24_funnel_automation.py — DS24 Käufer → Mailchimp + Klaviyo + Telegram
- traffic_seo_engine.py — AI SEO Content Generator

## Scheduler (alle 15 Min)
- ds24_funnel_sync: neue Käufer sofort in alle Mailing-Plattformen
- traffic_seo_run: alle 6h AI-SEO für DS24+Shopify

## Pending
- Pinterest: App review ausstehend (App ID: 1582363)
- Twilio FROM Number: kaufen unter console.twilio.com → Phone Numbers
