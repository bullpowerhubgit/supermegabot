# SuperMegaBot CURRENT STATUS — 2026-06-22 v22

## SYSTEM STATUS
- Railway Server: **LÄUFT** (deployed 2026-06-20 23:39 — alter Stand!)
- Railway Trial: **ABGELAUFEN** → neue Features nicht deployed
- Shopify Store: **LIVE** — ineedit.com.co — 2003 Produkte
- Bestellungen: **0** (Payment noch nicht aktiviert!)

## KRITISCHER BLOCKER — Railway Trial
Letzter erfolgreicher Deploy: 2026-06-20 23:39
Ausstehende Commits (NICHT auf Server):
- `9ab60f1` — Telegram-Spam fix (kein Marketing in privaten Chat)
- `bd7b20d` — Store-URLs fix (ineedit.com.co)
- `056bb3b` — Google OAuth Refresh Token speichern
- `6e0cbae` — Ollama qwen3.6 thinking-mode fix
- `995fd79` — GMC Feed Uploader
- `59052cf` — Instagram Pipeline

**→ Rudolf muss Railway upgraden: railway.app → Hobby Plan ($5/mo)**

## HEUTE ERLEDIGT (2026-06-22)
- ✅ 103+ Shopify Produkte mit Ollama SEO-optimiert (läuft weiter)
- ✅ Telegram Routing fix — Marketing → TELEGRAM_CHANNEL_ID (nicht private chat)
- ✅ Social Scheduler URLs → ineedit.com.co
- ✅ PayPal REST API Keys gespeichert in .env
- ✅ Google Auth Link an Rudolf gesendet (aiitecbuuss@gmail.com)

## OFFENE PUNKTE FÜR RUDOLF
| Aktion | Wo | Priorität |
|--------|-----|-----------|
| Railway Hobby Plan | railway.app → Plan | 🔴 JETZT |
| PayPal aktivieren | Shopify Admin → Zahlungen → PayPal | 🔴 JETZT |
| Facebook Token (korrekte Scopes) | developers.facebook.com/tools/explorer | 🟡 BALD |
| Shopify Blog-Scopes | Admin → Apps → Private Apps | 🟡 BALD |
| Google Merchant Center SA | merchants.google.com/mc/settings/users?a=5813214419 | 🟡 BALD |
| Google OAuth klicken | dudirudibot-mega-production.up.railway.app/api/google/auth | 🟡 BALD |

## LIVE REVENUE ENGINES
| System | Status | Details |
|--------|--------|---------|
| DS24 | ✅ LIVE | Key: 1581233-eOOUB4... (IMMER aiitec!) |
| Shopify | ✅ LIVE | 2003 Produkte aktiv, 0 Bestellungen |
| Klaviyo | ✅ LIVE | E-Mail-Sequenzen aktiv |
| Mailchimp | ✅ LIVE | AIITEC Konto |
| Stripe | ✅ LIVE | Billing-Check alle 30min |
| PayPal | 🔴 SETUP | Credentials gespeichert, Shopify-Link fehlt |
| Facebook | 🟡 TOKEN | Falscher Token (Scopes fehlen) |
| Instagram | 🟡 TOKEN | Wie Facebook |
| GMC | 🔴 SETUP | SA muss zu Merchant Center hinzugefügt werden |

## PRODUKT-OPTIMIERUNG (Ollama laufend)
- 2003 Produkte gesamt, 1410 ohne SEO-Beschreibung
- 103+ bereits optimiert (heute)
- Nächste Batch: script/optimize_products.py ausführen

## PAYPAL CREDENTIALS
- Client ID: AUVWqlbyslaRH... (in .env gespeichert)
- Secret: EPvkTEt3Zx150Q... (in .env gespeichert)
- Mode: live
- NVP Classic: bullpowersrtkennels_api1.gmail.com (auch in .env)

## FACEBOOK / INSTAGRAM
- Page: AIITEC (1016738738178786) — IMMER!
- IG: @aaiitecc (17841478315197796)
- Token FACEBOOK_PAGE_TOKEN_AIITEC braucht Scopes: pages_manage_posts + instagram_content_publish

## GOOGLE MERCHANT CENTER
- Merchant ID: 5813214419
- SA: rudibot-ai@gen-lang-client-0895465231.iam.gserviceaccount.com
- Feed URL: dudirudibot-mega-production.up.railway.app/api/gmc/feed.xml (LIVE, 200 OK)
- → SA als Admin in GMC hinzufügen → /api/gmc/setup aufrufen

## DS24 WICHTIG
IMMER Key 1581233-eOOUB4qRJJybjVb9z4q5tO68wtEQmt9h9l8t3s1N verwenden!
NIEMALS 1682000-... (falsches Konto!)
