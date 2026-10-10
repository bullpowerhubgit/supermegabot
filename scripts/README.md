# One-Click Project Completion

Zentraler Prüf-Workflow über alle Schwester-Projekte neben diesem Repo.

## Startbefehl

```bash
./scripts/complete-projects.sh
```

Optional nur bestimmte Projekte:

```bash
./scripts/complete-projects.sh adposter-engine digistore24-automation
```

Anderer Workspace-Pfad:

```bash
WORKSPACE=/pfad/zu/projekten ./scripts/complete-projects.sh
```

## Was der Workflow tut

Pro Projekt wird der Stack automatisch erkannt (Next.js / Node / Python / statisches HTML)
und die passende Kette ausgeführt:

1. Abhängigkeiten installieren (`pnpm`/`yarn`/`npm install` bzw. `pip install -r requirements.txt`)
2. Lint (falls `lint`-Script vorhanden)
3. Typecheck (Node: `typecheck`-Script; Python: `py_compile` über alle Dateien)
4. Production-Build (falls `build`-Script; statische Projekte: Existenz von `index.html`)
5. Healthcheck (nur wenn `HEALTH_URL_<REPO>` gesetzt ist)

Ergebnis landet in `completion-report.md` mit Ampel-Status ✅ / ⚠️ / ❌.

## Healthchecks aktivieren

Healthchecks laufen nur gegen explizit gesetzte URLs (Repo-Name in GROSSBUCHSTABEN,
`-` → `_`):

```bash
HEALTH_URL_SUPERMEGABOT=https://supermegabot-production.up.railway.app/health \
HEALTH_URL_DIGISTORE24_AUTOMATION=https://digistore24-automation-production.up.railway.app/api/health \
./scripts/complete-projects.sh
```

## Bewusste Grenzen (ohne explizite Freigabe)

Der Workflow löst **nie** aus:

- Deployment auf Produktion
- Live-Datenbankmigrationen
- echte Zahlungen (nur Stripe-/Sandbox-Testmodus)
- echte Kundenmails oder öffentliche Social-Posts

Diese Schritte bleiben manuell und benötigen deine ausdrückliche Freigabe.
