# 01 — Credential-Rotation-Checkliste (verbindlich)

Alle unten genannten Secrets standen im Klartext im Code und **bleiben in der Git-History sichtbar**, bis die History bereinigt ist (Abschnitt B). Das Entfernen aus dem Arbeitsstand (erledigt in den PRs) genügt **nicht** — jedes Secret muss rotiert werden.

Reihenfolge pro Secret: **1. neu erzeugen → 2. neuen Wert im Zielsystem setzen → 3. alten Schlüssel widerrufen → 4. validieren, dass der alte tot ist.**

## A. Rotationstabelle

| # | Dienst | Env-Variable | Leaked in (Git-History) | Neuen Wert setzen in | Neu erzeugen bei | Validierung: alter Key ungültig? |
|---|---|---|---|---|---|---|
| 1 | Telegram Bot | `TELEGRAM_BOT_TOKEN` | supermegabot, digistore24-automation, rudimaster-bot | Railway (alle 3 Services) | @BotFather → `/revoke` → neuer Token | `curl https://api.telegram.org/bot<ALT>/getMe` → muss 401 |
| 2 | Resend | `RESEND_API_KEY` | supermegabot | Railway (supermegabot); autoincome-ai nutzt es → Netlify | resend.com → API Keys → alten löschen | `curl -H "Authorization: Bearer <ALT>" https://api.resend.com/domains` → 401 |
| 3 | SendGrid | `SENDGRID_API_KEY` | supermegabot | Railway (supermegabot), digistore24 | app.sendgrid.com → API Keys → Delete | `curl -H "Authorization: Bearer <ALT>" https://api.sendgrid.com/v3/scopes` → 401 |
| 4 | Klaviyo | `KLAVIYO_API_KEY` | supermegabot | Railway (supermegabot, digistore24, adposter, analytics) | klaviyo.com → Settings → API Keys → revoke | `curl -H "Authorization: Klaviyo-API-Key <ALT>" https://a.klaviyo.com/api/lists/` → 401/403 |
| 5 | Twilio | `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` | supermegabot | Railway (supermegabot) | Twilio Console → Auth Token → **Secondary → Promote → old primary rotieren** | `curl -u <SID>:<ALT> https://api.twilio.com/2010-04-01/Accounts.json` → 401 |
| 6 | Printful | `PRINTFUL_API_KEY` | supermegabot | Railway (supermegabot); autoincome-ai → Netlify | printful.com → Settings → API → Token neu | `curl -H "Authorization: Bearer <ALT>" https://api.printful.com/store` → 401 |
| 7 | Pipedrive | `PIPEDRIVE_API_TOKEN` | supermegabot | Railway (supermegabot) | Pipedrive → Personal prefs → API → regenerate | `curl "https://api.pipedrive.com/v1/users/me?api_token=<ALT>"` → 401 |
| 8 | Facebook App | `FACEBOOK_APP_SECRET` | supermegabot | Railway (supermegabot) | developers.facebook.com → App → Settings → Reset Secret | alter Secret: Graph-API-Call mit `appsecret_proof` schlägt fehl |
| 9 | Discord | `DISCORD_CLIENT_SECRET` (+ `DISCORD_PUBLIC_KEY` prüfen) | supermegabot | Railway (supermegabot) | discord.com/developers → App → OAuth2 → Reset Secret | Token-Exchange mit altem Secret → `invalid_client` |
| 10 | AliExpress | `ALIEXPRESS_APP_SECRET` (+ Dropship-Variante) | supermegabot | Railway (supermegabot) | AliExpress Open Platform → App → Secret neu | signierter API-Call mit altem Secret → Signaturfehler |
| 11 | Reddit | `REDDIT_CLIENT_SECRET` | supermegabot | Railway (supermegabot, adposter) | reddit.com/prefs/apps → edit → generate secret | OAuth `access_token`-Request mit altem Secret → 401 |
| 12 | Google API | `GOOGLE_API_KEY` (gcp-config.json) | supermegabot | Railway (supermegabot) | console.cloud.google.com → Credentials → Key regenerate/restrict | API-Call mit altem Key → `API_KEY_INVALID` |
| 13 | OpenAI | `OPENAI_API_KEY` | aiitec-system | Vercel (aiitec-system); autoincome-ai, supermegabot falls genutzt | platform.openai.com → API keys → Revoke | `curl -H "Authorization: Bearer <ALT>" https://api.openai.com/v1/models` → 401 |
| 14 | DS24-Dankeseite | `DS24_DANKESEITE_KEY` | supermegabot | Railway (supermegabot) | selbst gewählter Zufallswert (`openssl rand -hex 24`) | alter Key im `/api/ds24/dankeseite`-Aufruf → 403 |

**Zusätzlich neu zu setzende Betriebs-Secrets (waren nie geleakt, aber jetzt Pflicht durch die Fixes):**
`DIGISTORE24_IPN_PASSPHRASE`, `SHOPIFY_WEBHOOK_SECRET`, `TELEGRAM_WEBHOOK_SECRET`, `ADMIN_API_KEY`, `GUMROAD_DOWNLOAD_KEY` (supermegabot); `INGEST_SECRET`, `CRON_SECRET`, `MARKETING_OPTIN_ENABLED` (digistore24); `DASHBOARD_API_TOKEN`, `STRIPE_WEBHOOK_SECRET`, `AUTO_PUBLISH_ENABLED` (adposter); `ADMIN_API_KEY`, `TRACK_API_KEY`, `STRIPE_WEBHOOK_SECRET` (analytics); `ENCRYPTION_KEY` (autoincome-ai).

## B. Git-History-Bereinigung (Rewrite-Plan — NICHT ohne Backup ausführen)

> **Kein History-Rewrite auf `main` ohne Backup + Team-Migrationsplan.** Rotation (Abschnitt A) hat Vorrang und macht die alten Werte wertlos; der Rewrite entfernt sie zusätzlich aus der Historie.

**Voraussetzungen**
1. **Backup:** vollständigen Mirror-Clone sichern — `git clone --mirror <repo> repo-backup-$(date +%F).git` und extern ablegen.
2. **Team-Migration ankündigen:** nach dem Rewrite müssen alle offenen Branches/Forks neu geklont oder rebased werden (die Commit-Hashes ändern sich). Offene PRs vorher mergen oder notieren.
3. Rotation aus Abschnitt A **abgeschlossen** (falls der Rewrite scheitert, sind die Keys trotzdem tot).

**Durchführung mit `git filter-repo`** (empfohlen, nicht `filter-branch`):
```bash
# pro betroffenem Repo, auf dem Mirror-Backup arbeiten
pip install git-filter-repo
# 1) Datei-basierte Leaks entfernen (Session-/Config-Dateien)
git filter-repo --path gcp-config.json --path telegram_export_session.session \
                --path telegram_export_session_copy.session --invert-paths
# 2) Werte-basierte Leaks schwärzen: replacements.txt mit "ALT==>REDACTED" je Secret
git filter-repo --replace-text replacements.txt
```
`replacements.txt` enthält je Zeile einen alten Secret-Wert → `REDACTED`. Alternativ **BFG Repo-Cleaner** (`bfg --replace-text replacements.txt`).

**Danach**
- `git push --force-with-lease` auf alle Branches (nur nach Team-Freigabe; GitHub-Branch-Protection auf `main` ggf. kurz lösen).
- Alle Kollaboratoren: frisch klonen (alte lokale Clones enthalten die Secrets weiter).
- GitHub-Support um Cache-/Fork-Invalidierung bitten, falls das Repo öffentlich war.

## C. Abnahme
- [ ] Alle 14 Secrets rotiert, alter Wert per Validierungs-Call als 401/ungültig bestätigt.
- [ ] Neue Betriebs-Secrets in den jeweiligen Zielsystemen gesetzt.
- [ ] Backups der betroffenen Repos gesichert.
- [ ] History-Rewrite (falls durchgeführt) mit Team abgestimmt, alle neu geklont.
