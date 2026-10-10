# 03 — Merge-Readiness-Checkliste je PR

Alle 10 PRs liegen auf Branch `claude/projects-audit-completion-xsc2gq`. Legende:
**✔** erledigt/verifiziert · **○** offen, braucht dich (Preview-Deploy/Secrets) · **—** nicht zutreffend.

Spalten: Diff geprüft · Build/Typecheck · Migration · Env dokumentiert · keine Secrets im Diff · Preview-Deploy · Healthcheck · kritische E2E.

> Preview-Deploy, Live-Healthcheck und echte E2E-Zahlungen konnten in der Build-Session **nicht** ausgeführt werden (kein Netzugang zu Railway/Vercel/Stripe). Sie sind als **○** markiert und in deiner Umgebung nachzuholen — Anleitung je PR unten.

| PR | Repo | Diff | Build/TC | Migr. | Env | keine Secrets | Preview | Health | E2E |
|---|---|---|---|---|---|---|---|---|---|
| [#113](https://github.com/bullpowerhubgit/supermegabot/pull/113) | supermegabot | ✔ | ✔ py_compile | — | ✔ | ✔ | ○ | ○ | ○ |
| [#15](https://github.com/bullpowerhubgit/digistore24-automation/pull/15) | digistore24-automation | ✔ | ✔ build | ○ SQL bereit | ✔ | ✔ | ○ | ○ | ○ Protokoll da |
| [#2](https://github.com/bullpowerhubgit/adposter-engine/pull/2) | adposter-engine | ✔ | ✔ build | — | ✔ | ✔ | ○ | ○ | ○ |
| [#5](https://github.com/bullpowerhubgit/autoincome-ai/pull/5) | autoincome-ai | ✔ | ✔ build | — | ✔ | ✔ | ○ | ○ | ○ |
| [#1](https://github.com/bullpowerhubgit/aiitec-high-ticket/pull/1) | aiitec-high-ticket | ✔ | ✔ Link-Verifier | — | — | ✔ | ○ | — | ○ 29 Links offen |
| [#9](https://github.com/bullpowerhubgit/analytics-marketing-service/pull/9) | analytics-marketing-service | ✔ | ✔ build | — | ✔ | ✔ | ○ | ○ | ○ |
| [#1](https://github.com/bullpowerhubgit/aiitec-system/pull/1) | aiitec-system | ✔ | ✔ node --check | — | ✔ | ✔ | ○ | ○ | — |
| [#2](https://github.com/bullpowerhubgit/rudimaster-bot/pull/2) | rudimaster-bot | ✔ | ✔ py_compile | — | ✔ | ✔ | ○ | ○ | — |
| [#6](https://github.com/bullpowerhubgit/nextjs-ai-chatbot/pull/6) | nextjs-ai-chatbot | ✔ | ✔ typecheck+build | ○ vorhanden | ✔ | ✔ | ○ | ○ | ○ |
| [#2](https://github.com/bullpowerhubgit/autosuiterudibot/pull/2) | autosuiterudibot | ✔ | ✔ build | ○ SQLite→PG nötig | ✔ | ✔ | ✗ blockiert | ○ | ✗ |

## Was je PR vor dem Merge noch zu tun ist

**supermegabot #113** — Credential-Rotation (Doc 01) muss vor Merge/Deploy laufen; neue Env-Vars in Railway setzen (`DIGISTORE24_IPN_PASSPHRASE`, `SHOPIFY_WEBHOOK_SECRET`, `TELEGRAM_WEBHOOK_SECRET`, `ADMIN_API_KEY`, `GUMROAD_DOWNLOAD_KEY`, `DS24_DANKESEITE_KEY`). Preview: Railway-PR-Environment → `curl /health` erwartet 200 (503 = degraded, Grund im Body).

**digistore24-automation #15** — SQL-Migration `supabase/migrations/20260826120000_*` auf Test-Supabase anwenden; Sandbox-Testprotokoll `docs/SANDBOX_TESTPROTOKOLL.md` (T1–T8) durchlaufen; Deploy-Ziel Railway (siehe `DEPLOYMENT.md`).

**adposter-engine #2** — `DASHBOARD_API_TOKEN` + `STRIPE_WEBHOOK_SECRET` setzen; `AUTO_PUBLISH_ENABLED` bewusst auf `true` erst nach Freigabe (Spam-/Sperr-Risiko). E2E: Stripe-Test-Webhook (`stripe trigger checkout.session.completed`).

**autoincome-ai #5** — `ENCRYPTION_KEY`, Stripe-Keys/Price-IDs, `RESEND_API_KEY`, `APP_URL` in Netlify. E2E: Checkout-Redirect im Testmodus (jetzt repariert). Blocker offen: echtes Auth + Webhook-Fulfillment (kein Merge-Blocker, aber vor Live nötig).

**aiitec-high-ticket #1** — `node scripts/verify-checkout-links.mjs` ist rot (29/48). Vor Live: fehlende Stripe-Links laut `STRIPE_CHECKLIST.md` anlegen, in `checkout-links.json` als `new_link` + im HTML eintragen, Verifier grün. Rechtstexte-Platzhalter füllen.

**analytics-marketing-service #9** — `STRIPE_WEBHOOK_SECRET`, `ADMIN_API_KEY`, `TRACK_API_KEY`, Stripe-Keys in Railway. E2E: Checkout + `stripe listen`.

**aiitec-system #1** — OpenAI-Key rotieren (Doc 01, #13); `OPENAI_API_KEY` + `CORS_ORIGIN` in Vercel. Preview: Vercel-Preview-Deploy → `/api/health` = ok.

**rudimaster-bot #2** — Telegram-Token rotieren (Doc 01, #1); `TELEGRAM_BOT_TOKEN` in Railway. Health-only-Fallback getestet (kein Crash ohne Token).

**nextjs-ai-chatbot #6** — DB-Migration vorhanden; `POSTGRES_URL`, `AUTH_SECRET`, `AI_GATEWAY_API_KEY`, `BLOB_READ_WRITE_TOKEN` setzen; für Non-Vercel zusätzlich `AUTH_URL`/`AUTH_TRUST_HOST`. CI läuft (Typecheck+Build). E2E: Login/Gast + Chat + `/api/health`.

**autosuiterudibot #2** — **Merge, aber noch nicht deploybar:** SQLite → Postgres (`DATABASE_URL`) migrieren und Deploy-Ziel (Vercel-URL vs. Dockerfile) klären, sonst gehen bei jedem Deploy alle Shop-Sessions verloren. Billing fehlt komplett.

## Generischer Preview/Health/E2E-Ablauf (je PR)
1. PR-Branch in Preview-Environment deployen (Railway PR-Env / Vercel Preview / Netlify Deploy Preview).
2. `curl -fsS https://<preview>/<healthpfad>` → 200.
3. Zahlungen ausschließlich im Stripe-/DS24-**Testmodus** (Testkarten, Test-Webhook-Events).
4. Ergebnisse (Logs/DB-Screenshots) im PR dokumentieren → dann Merge/Deploy freigeben.
