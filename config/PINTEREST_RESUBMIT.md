# Pinterest API — App 1582363 (AIITEC / rodibot)

## Screenshot-Status (Developer Portal)

| Feld | Wert |
|------|------|
| App-ID | **1582363** |
| Geheimer Schlüssel | **Nicht verfügbar: trial-Zugriff verweigert** |
| Token-Umgebung | „Produktion begrenzt“ (read-only scopes) |
| Token-Scopes | `pins:read`, `boards:read`, `user_accounts:read`, `ads:read`, `catalogs:read` |
| Token-Laufzeit | 24h (Portal-Hinweis) |
| Write-Scopes | **fehlen** (kein pins:write / boards:write bis Trial approve) |

**API-Pre-Check der letzten `pina_…` Tokens:**

| Error | Bedeutung |
|-------|-----------|
| 401 code 2 Authentication failed | Token tot/ungültig |
| 401 code 3 *consumer type is not supported* | Trial denied → App darf Production-API nicht nutzen |

→ **Kein Token installieren**, bis Trial freigeschaltet ist (Pre-check Gate).

## ✅ Compliance-Portal (LIVE, clean)

| Item | URL / Value |
|------|-------------|
| **Company** | AIITEC |
| **App name** | rodibot |
| **Website** | https://aiitec-pinterest-portal.vercel.app/ |
| **Privacy** | https://aiitec-pinterest-portal.vercel.app/privacy.html |
| **Datenschutz** | https://aiitec-pinterest-portal.vercel.app/datenschutz |
| **Data deletion** | https://aiitec-pinterest-portal.vercel.app/data-deletion.html |
| **Kontakt** | aiitecbuuss@gmail.com |
| Netlify (stale/BP-leak, deploy forbidden) | https://aiitec-pinterest-portal.netlify.app/ — **nicht für Resubmit nutzen** |

2026-07-16: BullPower-Marketing-Injection von der Startseite entfernt (hätte Nana wieder abgelehnt).

## ⚠️ NUR im Browser (Rudolf) — Resubmit Checklist

1. https://developers.pinterest.com → **Meine Apps** → App **1582363**
2. App-Einstellungen prüfen/setzen:
   - Company: **AIITEC**
   - App name: **rodibot** (nicht Rudibot, nicht BullPower)
   - Website: `https://aiitec-pinterest-portal.vercel.app/`
   - Privacy: `https://aiitec-pinterest-portal.vercel.app/privacy.html`
   - Data deletion: `https://aiitec-pinterest-portal.vercel.app/data-deletion.html`
3. Redirect URI (falls gefragt): `https://aiitec-pinterest-portal.vercel.app/` oder `http://localhost`
4. **Trial Access erneut einreichen** (vorher abgelehnt — Tickets 16593704 / 16593708)
5. Nach Approve:
   - App Secret kopieren → `PINTEREST_APP_SECRET`
   - Neues Token (ideal mit write scopes) → hier pasten
   - Optional Refresh Token → `PINTEREST_REFRESH_TOKEN`
6. Agent macht: `api_precheck` → nur bei PASS in `.env` + Railway

### Optional: Sandbox testen (ohne Trial)

Im Portal unter „Umgebung“ **Sandbox** wählen → Token generieren → pasten.  
Sandbox-Tokens laufen oft trotz denied Trial; Production „begrenzt“ mit code 3 nicht.

## Was SuperMegaBot schon hat

- Portal + Privacy live
- `PINTEREST_APP_ID=1582363`
- `PINTEREST_COMPANY_NAME=AIITEC`
- `PINTEREST_APP_NAME=rodibot`
- Pre-check Script: `python3 scripts/api_precheck.py`
- Dead tokens werden **nicht** mehr geschrieben

## Blocker

**Pinterest Trial muss approved werden.** Solange der Screenshot „trial-Zugriff verweigert“ zeigt, bleiben Secret + Production-API blockiert.
