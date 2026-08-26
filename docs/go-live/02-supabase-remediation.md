# 02 — Supabase-Remediation (Projekt qyrjeckzacjaazkpvnjk)

> **Status: FREIGABE ERFORDERLICH.** Kein Live-SQL wird ohne deine ausdrückliche Freigabe angewendet. Dieses Dokument zeigt das vollständige SQL, erklärt jede Anweisung, den Staging-Test, Rollback und den anonymen Negativtest.

## Befund (per Live-Read-Query am 2026-08-26 bestätigt)

`has_schema_privilege` + `information_schema.role_table_grants` ergaben:

| Objekt | anon | authenticated | Bewertung |
|---|---|---|---|
| Schema `api` (USAGE) | ✅ ja | ✅ ja | anon darf ins Schema |
| `api.ds24_purchases` | SELECT | SELECT | **Kauf-/Käuferdaten anonym lesbar** |
| `api.leads` | SELECT | SELECT | **Leads anonym lesbar** |
| `api.aiitec_contacts` | SELECT | SELECT | **Kontakte anonym lesbar** |
| `api.aiitec_email_events` | SELECT | SELECT | **16.689 E-Mail-Events anonym lesbar** |
| `api.revenue_snapshots` | SELECT | SELECT | **Umsatzdaten anonym lesbar** |
| `api.pipeline_results` | **INSERT, UPDATE, DELETE, TRUNCATE, SELECT** | — | **anonymes Schreiben/Löschen** |

Diese Views sind `SECURITY DEFINER` — RLS auf den Basistabellen greift dabei **nicht**. Der Zugriff läuft über die öffentliche PostgREST/GraphQL-API mit dem anon-Key.

## Das vollständige Remediation-SQL — mit Wirkung je Statement

```sql
-- (1) anon/authenticated der Zugriff auf das gesamte api-Schema entziehen.
--     Wirkung: PostgREST/GraphQL kann mit anon-Key nicht mehr ins api-Schema.
--     service_role (Backend) behält Zugriff, da nicht widerrufen.
REVOKE USAGE ON SCHEMA api FROM anon, authenticated;

-- (2) Alle Tabellen-/View-Rechte im api-Schema entziehen (deckt auch die
--     Schreibrechte auf pipeline_results ab: INSERT/UPDATE/DELETE/TRUNCATE).
--     Wirkung: selbst bei versehentlich verbleibendem USAGE kein SELECT/Write.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA api FROM anon, authenticated;

-- (3) Künftige Objekte im api-Schema erben keine anon/authenticated-Rechte mehr.
--     Wirkung: neue Views/Tabellen sind nicht automatisch wieder offen.
ALTER DEFAULT PRIVILEGES IN SCHEMA api REVOKE ALL ON TABLES FROM anon, authenticated;

-- (4) RLS auf der einzigen ungeschützten Basistabelle aktivieren.
--     Wirkung: Zugriff nur noch über explizite Policies (oder service_role).
ALTER TABLE api.pipeline_results ENABLE ROW LEVEL SECURITY;

-- (5) function_search_path_mutable härten (verhindert search_path-Hijack).
ALTER FUNCTION public.increment                     SET search_path = '';
ALTER FUNCTION public.update_updated_at             SET search_path = '';
ALTER FUNCTION public.update_updated_at_seo_content SET search_path = '';
ALTER FUNCTION public.get_mpo_stats                 SET search_path = '';
ALTER FUNCTION public.get_aiitec_outreach_stats     SET search_path = '';
ALTER FUNCTION public.cleanup_expired_locks         SET search_path = '';
```

**Nicht per SQL (Dashboard):**
- Authentication → Policies → **Leaked Password Protection = ON** (Advisor `auth_leaked_password_protection`).
- Settings → API → **Exposed schemas**: prüfen, ob `api` überhaupt exponiert sein muss. Wird es von keinem legitimen Frontend gebraucht → ganz aus der Exposure nehmen (stärkste Lösung, ersetzt (1)–(3)).

> ⚠️ **Vor (1)–(3) prüfen:** Nutzt ein legitimes Frontend das `api`-Schema mit dem anon-Key? Falls ja, brechen dessen Reads. Dann stattdessen gezielte RLS-Policies auf den betroffenen Views/Tabellen statt pauschalem REVOKE. Der Read-Test unten hilft, das zu entscheiden.

## Staging-Test (vor Live)

Supabase-**Branch** als sichere Kopie nutzen (kostenpflichtige Ressource → separate Freigabe):
1. `create_branch` (Kostenbestätigung nötig) → Migrations werden auf den Branch angewendet.
2. Remediation-SQL auf dem Branch ausführen (`apply_migration`).
3. Advisor erneut laufen lassen (`get_advisors type=security`) → ERROR/WARN zu `api`-Exposure und `security_definer_view` müssen verschwinden.
4. Negativtest (unten) mit dem **Branch**-anon-Key.
5. Erst nach grünem Branch: `merge_branch` bzw. dieselbe Migration auf Production — **nach deiner Freigabe**.

Alternativ ohne Branch: Migration in einem Wartungsfenster auf Production mit sofortiger Verifikation + bereitliegendem Rollback.

## Anonymer Negativtest (Beleg, dass es dicht ist)

Mit dem **anon/publishable Key** (nicht service_role!) gegen die REST-API. Ziel-Ref = `qyrjeckzacjaazkpvnjk` (bzw. Branch-Host).

**Vorher (erwartet: Daten kommen zurück — Leck):**
```bash
ANON="<anon-key>"
BASE="https://qyrjeckzacjaazkpvnjk.supabase.co/rest/v1"
for t in ds24_purchases leads aiitec_contacts aiitec_email_events; do
  echo "== $t =="
  curl -s "$BASE/$t?select=*&limit=1" -H "apikey: $ANON" -H "Authorization: Bearer $ANON"
done
```

**Nachher (erwartet: KEINE Daten):** jeder Aufruf muss `permission denied` / `42501` bzurückgeben oder ein leeres `[]` — **niemals** eine Datenzeile. Zusätzlich der Schreibtest auf `pipeline_results`:
```bash
curl -s -X POST "$BASE/pipeline_results" -H "apikey: $ANON" \
  -H "Authorization: Bearer $ANON" -H "Content-Type: application/json" \
  -d '{"probe":"neg-test"}'   # muss abgelehnt werden (permission denied), KEIN Insert
```
Abnahme: alle vier Read-Ziele liefern keine Zeile, der Insert wird abgelehnt, `get_advisors` meldet die `api`-Exposure nicht mehr.

## Rollback

Falls ein legitimer Client bricht, Zugriff kontrolliert zurückgeben:
```sql
-- minimal, nur was der Client wirklich braucht (Beispiel: nur Lesen einer Sicht)
GRANT USAGE ON SCHEMA api TO authenticated;          -- nur authenticated, nicht anon
GRANT SELECT ON api.<konkrete_view> TO authenticated; -- gezielt statt pauschal
```
Vollständiger Rollback (nur wenn nötig, stellt das Leck wieder her — nicht empfohlen):
```sql
GRANT USAGE ON SCHEMA api TO anon, authenticated;
GRANT SELECT ON ALL TABLES IN SCHEMA api TO anon, authenticated;
```
Der Branch-Ansatz macht Rollback trivial: Branch verwerfen, Production bleibt unberührt.

## Abnahme
- [ ] Staging/Branch: SQL angewendet, `get_advisors` sauber.
- [ ] Negativtest mit anon-Key: keine Purchases/Leads/Kontakte/E-Mail-Events lesbar, kein Insert auf pipeline_results.
- [ ] Kein legitimer Client gebrochen (oder gezielte Policy statt REVOKE gewählt).
- [ ] Freigabe erteilt → Migration auf Production.
