# AGENT CREDENTIALS SYNC — Stand 2026-06-18
# =========================================================
# WICHTIG: Diese Datei wird von ALLEN Agenten gelesen.
# Enthält alle aktiven Credentials und Modul-Übersicht.
# Keine Änderungen ohne gleichzeitigen Railway-Sync!
# =========================================================

## AKTIVE API KEYS (alle in Railway + .env gespeichert)

### AI
- ANTHROPIC_API_KEY: sk-ant-api03-1SdOyuwr1xyzSxZl967gY...  (Claude Haiku/Sonnet)
- OPENAI_API_KEY: sk-proj-V9uGQrulIitGZrr9w...  (GPT-4o)
- DEEPSEEK_API_KEY: sk-3e1d91cc3a1645d19189ed76bcec9e21
- OPENROUTER_API_KEY: 454d05c2d3a8290e024e0fbbb130735e5a847729...

### Telegram
- TELEGRAM_BOT_TOKEN: 8600739487:AAGhByAoKEpbsfco9swoaRYjU2HI_gSt718
- TELEGRAM_CHAT_ID: 5088771245

### Shopify
- SHOPIFY_SHOP_DOMAIN: autopilot-store-suite-fmbka.myshopify.com
- SHOPIFY_ACCESS_TOKEN: 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
- SHOPIFY_API_VERSION: 2024-10

### Stripe
- STRIPE_SECRET_KEY: sk_live_51Tg1U0RJECiV6vSm...
- STRIPE_PRICE_STARTER: price_1TiiBiRJECiV6vSmXsPlGDRd
- STRIPE_PRICE_PRO: price_1TiiBjRJECiV6vSmCrcv0kHF
- STRIPE_PRICE_ENTERPRISE: price_1TiiBkRJECiV6vSmiCRZPmL1

### Supabase
- SUPABASE_URL: https://qyrjeckzacjaazkpvnjk.supabase.co
- Project ID: qyrjeckzacjaazkpvnjk

### Digistore24
- DIGISTORE24_API_KEY: 1581233-eOOUB4qRJJybjVb9z4q5tO68wtEQmt9h9l8t3s1N  ← Vollzugriff
- DIGISTORE24_API_KEY_READONLY: 1583143-rKrkcndqBDL52N5kmX36wZXeFTNbCyI8R8gkVgIJ
- WICHTIG: buyer Email ist verschachtelt → order["buyer"]["email"]
- 3 Transaktionen, €111 gesamt (Feb 2026)

### Mailchimp (NEU 2026-06-18 — alter us18 Key war deaktiviert)
- MAILCHIMP_API_KEY: 1d35dd606aad1a9f1bbd10d2dd2e2ea7-us7
- MAILCHIMP_SERVER_PREFIX: us7
- MAILCHIMP_LIST_ID: 606e45a6b0  (Liste "AiiteC", 4 Members)
- MAILCHIMP_CLIENT_ID: 533625521597
- MAILCHIMP_CLIENT_SECRET: c4c6423524cdb5ce7c53a415a03a0668f18adcfd79d760d628

### Klaviyo (NEU 2026-06-18 — alte pk_ Keys waren ungültig)
- KLAVIYO_API_KEY: pk_VaCYq3_242945f7521ac82039ed5dbf7ff8e6cf1c
- KLAVIYO_LIST_ID: Xwxq6V  (E-Mail Hauptliste)
- Weitere Listen: TiEAtk (Vorschau), U2iTrm (SMS)

### Twilio SMS (NEU 2026-06-18)
- TWILIO_ACCOUNT_SID: AC2b92fc8e5af02a27604a964cb241b021
- TWILIO_AUTH_TOKEN: 54511038fba02a2dbac1a0ef28b704a5  (verifiziert, Account "active")
- TWILIO_API_KEY_SID: SKe45ad37f109f52168e9b4bb6cd9da477
- TWILIO_API_KEY_SECRET: RikVTimlOqQmWeOd0yQYFSlOjsbGRJ0Q
- FEHLT: TWILIO_FROM_NUMBER → kaufen unter console.twilio.com → Phone Numbers

### Google / YouTube
- YOUTUBE_API_KEY: AIzaSyC6obwPIq7hxRrxSyzdpn41vnSSDcOQzcA
- YOUTUBE_CHANNEL_ID: UCy5U7UGOMNkvUR2-5Qm4yiA  (~4.000 Follower)
- GCP_PROJECT_ID: gen-lang-client-0895465231
- GCP_REGION: europe-west3
- GOOGLE_API_KEY: AQ.Ab8RN6IeIIZjAUUeRzaM5jOlUdQzyxW36z1wuOLrMAcMVeSJYw

### Meta / Facebook (3 Pages + Instagram)
- FACEBOOK_BUSINESS_ID: 1709197847127997  (ACHTUNG: restricted seit 22.04.2026!)
- FACEBOOK_PAGE_ID: 1135864516276500  (IWIN Page)
- FACEBOOK_ACCESS_TOKEN: EAARagX8U6aEBRqr0bfek...  (User Token, 60 Tage, ~Aug 2026)
- FACEBOOK_PAGE_TOKEN: EAARagX8U6aEBRkdQySs...  (IWIN Page Token)
- FACEBOOK_PAGE_TOKEN_IWIN: EAARagX8U6aEBRoAcI5...  (Page ID: 1135864516276500)
- FACEBOOK_PAGE_TOKEN_I_NEED_IT: EAARagX8U6aEBRu8lW...  (Page ID: 1058648427339278)
- FACEBOOK_PAGE_TOKEN_AIITEC: EAARagX8U6aEBRjUpmL...  (Page ID: 1016738738178786)
- INSTAGRAM_ID_AIITEC: 17841478315197796  (4.939 Follower, @aaiitecc)
- INSTAGRAM_USER_AIITEC: aaiitecc

### Gmail EmailBrain (NEU 2026-06-18 — 6/8 Konten aktiv)
| Nr | Account | App-Password (Spaces entfernen für SMTP) | Status |
|----|---------|----------------------------------------|--------|
| 1 | dragonadnp@gmail.com | emnm bawd adqe lvbu | ✅ aktiv |
| 2 | nikolestimi@gmail.com | bcgp vjuv dkgl qmxt | ✅ aktiv |
| 3 | bullpowersrtkennels@gmail.com | xvmm vqzm gpft wvzn | ✅ aktiv |
| 4 | looopwave@gmail.com | — | ⏳ ausstehend |
| 5 | aiitecbuuss@gmail.com | huyy xlln dovc smtu | ✅ aktiv |
| 6 | rudolf.sarkany@aitec.de | — (braucht IMAP_HOST_6=imap.strato.de) | ⏳ ausstehend |
| 7 | rudolf.sarkany.aiitec@gmail.com | erea dgvd ubxa yuwx | ✅ aktiv |
| 8 | rudolfsarkany1984@gmail.com | adso mjrc fgud bcby | ✅ aktiv |
- Railway Env Vars: GMAIL_USER_1..8 + GMAIL_APP_PASSWORD_1..8
- Modul: modules/email_brain.py — IMAP polling alle 15 Min, Claude Haiku Classification, Auto-Reply
- WICHTIG: aiitecbuuss hat 2 i's (aiitecbuuss, nicht aitecbuuss)!

### GitHub
- GITHUB_TOKEN: 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
- GITHUB_USER: bullpowerhubgit
- REPO: bullpowerhubgit/supermegabot

### Pinterest (PENDING)
- App ID: 1582363 (alte Anfrage)
- App ID: 1582389 (neue Anfrage — abgelehnt wegen: schlechter Description, 404 Datenschutz-URL, falscher Name)
- Status: MUSS NEU EINGEREICHT WERDEN (Fix: Datenschutz-Seite, professionelle App-Beschreibung)

---

## NEUE MODULE (seit 2026-06-17)

### modules/brutus_traffic_engine.py — BRUTUS v1.0
Das brutalste Traffic-Tool das je gebaut wurde.
- `brutus_run(niche, custom_keywords)` — Vollautomatischer 7-Phasen-Durchlauf
- Phase 1 SCAN: YouTube Trends + Google Trends RSS + Reddit Hot
- Phase 2 PREDICT: Claude Haiku bewertet Trends (pre-peak score >= 7)
- Phase 3 SWARM: 10 parallele Agenten → 10 Content-Formate gleichzeitig
  → blog_post, youtube_desc, email_subject_lines, social_post, product_seo,
     ad_copy, pinterest_pins, faq_seo, reddit_post, press_release
- Phase 4 DEPLOY: 4 Kanäle gleichzeitig
  → Telegram Bot (sofort)
  → Shopify Blog (SEO-Artikel publizieren)
  → Klaviyo Campaign (Email-Kampagne)
  → Facebook Page IWIN (Social Post)
- Phase 5+6 AMPLIFY: Winners erkennen und extra pushen
- Phase 7 UTM: Revenue-Attribution per Kanal
- Läuft alle 3h via automation_scheduler.py

### modules/ds24_funnel_automation.py
- `run_sync()` — DS24 Neue Käufer → Mailchimp + Klaviyo + Telegram
- Buyer-Email: order["buyer"]["email"] (verschachtelt!)
- State-File: data/brutus/ds24_synced_buyers.json
- Läuft alle 15 Min via automation_scheduler.py

### modules/traffic_seo_engine.py
- `run_full_traffic_seo()` — AI-SEO für DS24 + Shopify Produkte
- `generate_seo_content_for_product()` → JSON: seo_title, meta_description, h1, blog_intro, keywords, social_post, youtube_description, email_subject, cta
- Läuft alle 6h via automation_scheduler.py

### modules/twilio_sms.py
- `send_sms(to, body)` — SMS über Twilio REST API
- `get_account_info()` — Account-Status prüfen
- BasicAuth: TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN

---

## GESAMTREICHWEITE RUDOLF (17.500+ Follower)
| Kanal | Account | Follower | BRUTUS Status |
|-------|---------|----------|---------------|
| Facebook | IWIN (1135864516276500) | ~500 | ✅ Auto-Post aktiv |
| Facebook | I Need It (1058648427339278) | ~500 | ✅ Token bereit |
| Facebook | Aiitec (1016738738178786) | ~500 | ✅ Token bereit |
| Instagram | @aaiitecc (17841478315197796) | 4.939 | ✅ Auto-Post aktiv (pixel: bullpowerhubgit.github.io/bullpower-legal/brutus_pixel.png) |
| YouTube | UCy5U7UGOMNkvUR2-5Qm4yiA | ~4.000 | ✅ API Key aktiv |
| Telegram | Bot (Chat 5088771245) | direkt | ✅ Notifications |
| Shopify Blog | autopilot-store-suite | SEO | ✅ Auto-Publish |
| Klaviyo Email | Xwxq6V | wächst | ✅ Campaigns |
| Pinterest | App ID 1582363 | - | ⏳ Review pending |

---

## SCHEDULER TASKS (automation_scheduler.py)
| Task | Intervall | Funktion |
|------|-----------|---------|
| shopify_sync | 30 Min | Produkte synchronisieren |
| digistore_sync | 1h | Revenue-Daten holen |
| health_check | 2h | Telegram Health Alert |
| ai_trend | 6h | AI Trend-Analyse |
| ds24_funnel_sync | 15 Min | Neue Käufer → Mailing |
| traffic_seo_run | 6h | SEO Content generieren |
| brutus_run | 3h | Vollautomatisches Traffic-System |
| daily_backup | 24h | GitHub Backup |

---

## PENDING / NÄCHSTE SCHRITTE
1. Pinterest neu einreichen (fix: Datenschutz-URL, professionelle Beschreibung)
2. ✅ Instagram @aaiitecc Auto-Posting in BRUTUS Phase 4 aktiv (pixel live)
3. YouTube Community Posts zu BRUTUS Phase 4 hinzufügen
4. Twilio FROM Number kaufen → SMS-Marketing aktivieren
5. Meta Ads Appeal oder TikTok Ads Alternative
6. 2. Instagram-Konto (6000 Follower) noch nicht verbunden

---

## WICHTIGE HINWEISE FÜR ANDERE AGENTEN
- Business Manager Meta ist restricted seit 22.04.2026 → KEINE Meta Ads möglich
- DS24 buyer email ist VERSCHACHTELT: order["buyer"]["email"] — nicht order["buyer_email"]!
- Klaviyo Header: Authorization: "Klaviyo-API-Key {key}" + revision: "2024-06-15"
- Mailchimp: BasicAuth username="any", password=API_KEY
- Facebook Graph API: v19.0, Page Posts: POST /{page_id}/feed mit page_token
- BRUTUS läuft alle 3h autonom — kein manueller Eingriff nötig
